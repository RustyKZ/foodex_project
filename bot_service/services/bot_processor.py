import asyncio

from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from logger_config import get_logger

from session_config import async_session
from bot_config import bot

from models.app_users import AppUser
from models.bot_models import BotMessages, BotCommands

from sqlalchemy import select, not_
from sqlalchemy.exc import SQLAlchemyError


from datetime import datetime, timezone

from services.bot_broadcast import broadcast_message

from services.data_processing import get_orders_excel_file
from services.payment_processing import star_payment_processing
from services.rabbit_sender import broadcast_message_async, direct_task_async
from services.error import put_critical_error_into_db
from services.bot_message_sender import send_app_user_message_text_bot_notify_unknown

from aiogram.types import BufferedInputFile

from config import settings
ADMIN_IDS = settings.ADMIN_TG_IDS
THIS_SERVICE_NAME = settings.BOT_SERVICE_NAME
API_SERVICE_NAME = settings.API_SERVICE_NAME


from constants.default_settings import DEFAULT_LANGUAGE, MAX_ORDER_LIST_EXCEL_FILE_ITEMS

from system_i18n.bot_error_messages import (
    ERROR_GENERATE_ORDER_LIST_FAILURE, ERROR_GENERATE_ORDER_LIST_UNKNOWN, ERROR_GENERATE_ORDER_LIST_EMPTY_LIST, ERROR_GENERATE_ORDER_LIST_TOO_LONG_LIST, 
    ERROR_STAR_PAYMENT_UNKNOWN_PROCESSING_ERROR
)

from system_i18n.bot_success_messages import SUCCESS_STAR_PAYMENT

logger = get_logger(__name__)


async def send_message_to_admin_for_checking(message):
    """
    Sends a preliminary notification to all admins about a message
    that requires confirmation, then broadcasts the message itself
    to admins for review.
    """
    broadcast_date = datetime.fromtimestamp(message.sending_date)
    try:
        # Формируем читаемый текст уведомления
        pre_message_text = (
            f"*ADMIN NOTIFICATION*\n"
            f"Message for broadcast is waiting for your confirmation\n"
            f"Message ID: `{message.id}`\n"
            f"Broadcast date: `{broadcast_date}`\n\n"
            f"• Send `/confirm${message.id}` to confirm this message\n"
            f"• Or fix it in the admin panel before sending"
        )

        for user_id in ADMIN_IDS:
            try:
                logger.info(f"Sending preliminary message to admin {user_id}")
                await bot.send_message(
                    chat_id=user_id,
                    text=pre_message_text,
                    parse_mode="MarkdownV2"
                )
                await asyncio.sleep(0.05)  # Avoid Telegram API flood limits

            except TelegramForbiddenError:
                logger.info(f"User {user_id} blocked the bot")
            except TelegramBadRequest as e:
                logger.info(f"BadRequest while sending to {user_id}: {e}")
            except Exception as e:
                logger.info(f"Unexpected error while sending to {user_id}: {e}")

        # Отправляем пример сообщения админам
        await broadcast_message(ADMIN_IDS, message.message_data)

    except Exception as e:
        logger.exception(f"send_message_to_admin_for_checking - Exception: {e}")


async def send_orders_excel_file(data: dict):
    try:
        user_id = data.get("user_id")
        business_id = data.get("business_id")
        order_ids = data.get("order_ids")
        user_tg_id = data.get("user_tg_id")
        generate_excel_file = await get_orders_excel_file(user_id=user_id, business_id=business_id, order_ids=order_ids)
        language = generate_excel_file.get("language", DEFAULT_LANGUAGE)
        if generate_excel_file["status"]:
            orders_file = generate_excel_file.get("orders_file", None)            
            filename = generate_excel_file.get("filename", "orders.xlsx")
            if orders_file:
                telegram_file = BufferedInputFile(
                    file=orders_file.getvalue(),
                    filename=filename
                )
                await bot.send_document(
                    chat_id=user_tg_id,
                    document=telegram_file
                )
                logger.info(
                    f"Excel file successfully sent to user {user_tg_id}"
                )
            else:
                if generate_excel_file.get("empty_order_list"):
                    error_message = ERROR_GENERATE_ORDER_LIST_EMPTY_LIST.get(language, ERROR_GENERATE_ORDER_LIST_EMPTY_LIST.get(DEFAULT_LANGUAGE))
                elif generate_excel_file.get("too_long_order_list"):
                    error_message = ERROR_GENERATE_ORDER_LIST_TOO_LONG_LIST.get(language, ERROR_GENERATE_ORDER_LIST_TOO_LONG_LIST.get(DEFAULT_LANGUAGE))
                    error_message += str(MAX_ORDER_LIST_EXCEL_FILE_ITEMS)
                else:
                    error_message = ERROR_GENERATE_ORDER_LIST_FAILURE.get(language, ERROR_GENERATE_ORDER_LIST_FAILURE.get(DEFAULT_LANGUAGE))
                await bot.send_message(
                    chat_id=user_tg_id,
                    text=error_message
                )
                logger.info(f"send_orders_excel_file - excel file is empty")
        else:
            await bot.send_message(
                    chat_id=user_tg_id,
                    text=ERROR_GENERATE_ORDER_LIST_UNKNOWN.get(language, ERROR_GENERATE_ORDER_LIST_UNKNOWN.get(DEFAULT_LANGUAGE))                    
                )
            logger.info(f"send_orders_excel_file - excel file was not generated")
    except Exception as e:
        logger.exception(f"send_orders_excel_file - Exception: {e}")


async def send_star_payment_result(payment_data: dict):
    user_tg_id = payment_data.get("user_tg_id")
    amount = payment_data.get("amount")
    language = payment_data.get("language", DEFAULT_LANGUAGE)
    print(f"====================================================================================\n")
    print(f"send_star_payment_result - payment_data: {payment_data}")
    print(f"====================================================================================\n")
    try:        
        payment = await star_payment_processing(payment_data=payment_data)
        if payment["status"]:
            user_id = payment.get("user_id")
            charge_id = payment.get("charge_id")
            star_payment_id = payment.get("star_payment_id")
            message = {
                    "sender": THIS_SERVICE_NAME,
                    "receiver": API_SERVICE_NAME,
                    "receiver_id": "all",
                    "message": { 
                        "type": "execute",
                        "description": "star_payment_processing",
                        "user_id": user_id,
                        "charge_id": charge_id,
                        "star_payment_id": star_payment_id
                    }
                }            
            await direct_task_async(receiver_service_name=API_SERVICE_NAME, message=message)
            language = payment.get("language", DEFAULT_LANGUAGE)
            pre_text = SUCCESS_STAR_PAYMENT.get(language, SUCCESS_STAR_PAYMENT.get(DEFAULT_LANGUAGE))
            message_text=f"{pre_text}{amount} ⭐"
            await send_app_user_message_text_bot_notify_unknown(user_id=user_id, message_text=message_text)
        else:
            await bot.send_message(
                    chat_id=user_tg_id,
                    text=ERROR_STAR_PAYMENT_UNKNOWN_PROCESSING_ERROR.get(language, ERROR_STAR_PAYMENT_UNKNOWN_PROCESSING_ERROR.get(DEFAULT_LANGUAGE))                    
                )
        
    except Exception as e:
        logger.exception(f"star_payment_processing - Exception: {e}")


async def process_bot_message_for_confirm(message_id: int):
    async with async_session() as session:
        try:            
            message = (await session.execute(select(BotMessages).where(BotMessages.id == message_id))).scalars().first()
            if not message:
                put_critical_error_into_db("process_bot_message_for_confirm", "message not found", f"message {message_id} not found", {"message_id": message_id})
                return
            if message.not_actual:
                put_critical_error_into_db("process_bot_message_for_confirm", "incorrect message ID", f"message {message_id} is not actual", {"message_id": message_id})
                return
            if message.sended:
                put_critical_error_into_db("process_bot_message_for_confirm", "incorrect message ID", f"message {message_id} is already sended", {"message_id": message_id})
                return
            if message.confirmed:
                put_critical_error_into_db("process_bot_message_for_confirm", "incorrect message ID", f"message {message_id} is already confirmed", {"message_id": message_id})
                return        

            await send_message_to_admin_for_checking(message=message)

        except Exception as e:
            await put_critical_error_into_db("process_bot_message_for_confirm", "main exception error", str(e), {"message_id": message_id})
            return


async def process_bot_message_for_send(message_id: int):
    async with async_session() as session:
        try:
            current_time = datetime.now(timezone.utc)
            current_time_unix = int(current_time.timestamp())

            message = (await session.execute(select(BotMessages).where(BotMessages.id == message_id, BotMessages.sending_date <= current_time_unix))).scalars().first()
            if not message:
                put_critical_error_into_db("process_bot_message_for_send", "message not found", f"message {message_id} not found", {"message_id": message_id})
                return
            if message.not_actual:
                put_critical_error_into_db("process_bot_message_for_send", "incorrect message ID", f"message {message_id} is not actual", {"message_id": message_id})
                return
            if message.sended:
                put_critical_error_into_db("process_bot_message_for_send", "incorrect message ID", f"message {message_id} is already sended", {"message_id": message_id})
                return
            if not message.confirmed:
                logger.info(f"process_bot_message_for_send - message {message_id} must sended now, but it not confirmed by admin")
                return            
            
            report_data = {}
            try:
                report_data = await broadcast_message(message.userlist, message.message_data)
                message.sended = True
                await session.commit()
            except Exception as sending_error:
                logger.exception(f"process_bot_message_for_send - SENDING BROADCAST exception: {sending_error}")

            try:
                total_users = report_data.get("total_users", 0)
                msg_sent = report_data.get("sent", 0)
                msg_blocked = report_data.get("blocked", 0)
                msg_bad_request = report_data.get("bad_request", 0)
                msg_unexpected = report_data.get("unexpected", 0)
                report_text = (
                    f"*ADMIN NOTIFICATION*\n"
                    f"Message broadcast report\n"
                    f"Message ID: `{message.id}`\n\n"
                    f"Total users: `{total_users}`\n"
                    f"Messages sent: `{msg_sent}`\n"
                    f"Messages blocked: `{msg_blocked}`\n"
                    f"Bad request: `{msg_bad_request}`\n"
                    f"Unexpected errors: `{msg_unexpected}`"
                )

                for admin_id in ADMIN_IDS:
                    try:
                        logger.info(f"Sending report message to admin {admin_id}")
                        await bot.send_message(
                            chat_id=admin_id,
                            text=report_text,
                            parse_mode="MarkdownV2"
                        )
                        await asyncio.sleep(0.05)  # Avoid Telegram API flood limits

                    except TelegramForbiddenError:
                        logger.error(f"process_bot_message_for_send - User {admin_id} blocked the bot")
                    except TelegramBadRequest as e:
                        logger.info(f"process_bot_message_for_send - BadRequest while sending to {admin_id}: {e}")
                    except Exception as e:
                        logger.info(f"process_bot_message_for_send - Unexpected error while sending to {admin_id}: {e}")

            except Exception as report_error:
                logger.exception(f"process_bot_message_for_send - Report exception: {report_error}")
                            

        except Exception as e:
            logger.exception(f"process_bot_message_for_send - Exception: {e}")
            return None
