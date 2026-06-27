from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
BOT_USERNAME = settings.TELEGRAM_BOT_USERNAME
TMA_URL = settings.TELEGRAM_MINI_APP_URL
BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
LANDING_URL = settings.LANDING_URL
ADMIN_IDS = settings.ADMIN_TG_IDS
THIS_SERVICE_NAME = settings.BOT_SERVICE_NAME
API_SERVICE_NAME = settings.API_SERVICE_NAME

from bot_config import bot
from session_config import async_session

from logger_config import get_logger

from models.app_users import AppUser
from models.bot_models import BotMessages, BotCommands

from sqlalchemy import select, not_
from sqlalchemy.exc import SQLAlchemyError

from constants.default_settings import DEFAULT_LANGUAGE

from system_i18n.bot_buttons import BOT_BUTTON_START_FOODEX, BOT_BUTTON_VISIT_WEBSITE
from system_i18n.bot_scripts import BOT_ANSWER_START, BOT_ANSWER_ABOUT

from services.rabbit_sender import broadcast_message_async, direct_task_async

logger = get_logger(__name__)

async def handler_start(data):
    chat_id = data["chat_id"]
    language = data.get("language", DEFAULT_LANGUAGE)

    button_text = BOT_BUTTON_START_FOODEX.get(language, BOT_BUTTON_START_FOODEX.get(DEFAULT_LANGUAGE))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=TMA_URL)]
        ]
    )

    text = BOT_ANSWER_START.get(language, BOT_ANSWER_START.get(DEFAULT_LANGUAGE)) 

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def handler_about(data):
    chat_id = data["chat_id"]
    language = data.get("language", DEFAULT_LANGUAGE)

    button_text = BOT_BUTTON_VISIT_WEBSITE.get(language, BOT_BUTTON_VISIT_WEBSITE.get(DEFAULT_LANGUAGE))
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=LANDING_URL)]
        ]
    )

    text = BOT_ANSWER_ABOUT.get(language, BOT_ANSWER_ABOUT.get(DEFAULT_LANGUAGE))

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def handler_confirm(data):
    chat_id = data["chat_id"]
    error_message_not_admin_text = (
        "The command you entered is only available to administrators"
    )
    if data["user_id"] not in ADMIN_IDS:
        await bot.send_message(
            chat_id=chat_id,
            text=error_message_not_admin_text,        
            parse_mode="Markdown"
        )
    else:
        try:
            data_argument = data.get("argument", "")  # на случай, если ключа нет
            try:
                message_id = int(data_argument)
            except (ValueError, TypeError):                
                message_id = None

            if message_id is None:
                logger.error(f"handler_confirm - Bad argument")
                error_message = (
                    "Error: Bad argument"
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=error_message,
                    parse_mode="Markdown"
                )
                return
            
            async with async_session() as session:
                try:
                    message_query = select(BotMessages).filter(BotMessages.id == message_id)
                    messages_result = await session.execute(message_query)
                    message = messages_result.scalars().first()

                    if not message:
                        logger.error(f"handler_confirm - Message {message_id} not found")
                        error_message = (
                            f"Error: Message {message_id} not found"
                        )
                        await bot.send_message(
                            chat_id=chat_id,
                            text=error_message,
                            parse_mode="Markdown"
                        )
                    elif message.confirmed or message.sended or message.not_actual:
                        logger.error(f"handler_confirm - Message {message_id} cannot be confirmed")
                        error_message = (
                            f"Error: Message {message_id} cannot be confirmed"
                        )
                        await bot.send_message(
                            chat_id=chat_id,
                            text=error_message,
                            parse_mode="Markdown"
                        )
                    else:
                        message.confirmed = True
                        await session.commit()
                        logger.info(f"handler_confirm - Message {message_id} confirmed successfully")
                        success_message = (
                            f"Message {message_id} confirmed successfully"
                        )
                        await bot.send_message(
                            chat_id=chat_id,
                            text=success_message,
                            parse_mode="Markdown"
                        )

                except SQLAlchemyError as error:
                    logger.error(f"handler_confirm - Exception SQL Alchemy:\n{error}")
                    error_message_sql = (
                        "Error: Exception SQL Alchemy"
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text=error_message_sql,
                        parse_mode="Markdown"
                    )
        except Exception as e:
            logger.exception(f"handler_confirm - Exception: {e}")



async def handler_test(data):
    print(f"================= HANDLER TEST ======================= ")
    print(f"{data}")
    argument = data.get("argument")
    message = {
        "sender": THIS_SERVICE_NAME,
        "receiver": API_SERVICE_NAME,
        "receiver_id": "all",
        "message": { 
            "type": "execute",
            "description": "test_planner",
            "test_data": argument            
        }
    }
    if argument:
        await direct_task_async(API_SERVICE_NAME, message)
    else:
        await broadcast_message_async(message)