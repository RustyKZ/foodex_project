
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from sqlalchemy.future import select

from models.app_users import AppUser

from session_config import async_session
from bot_config import bot

from services.error import put_critical_error_into_db


from logger_config import get_logger
logger = get_logger(__name__)


async def send_telegram_user_message_text_bot_notify_on(user_tg_id: int, message_text: str):
    try:
        await bot.send_message(
            chat_id=user_tg_id,
            text=message_text,
            parse_mode=None,
        )

        return True

    except Exception as e:
        logger.exception(f"send_telegram_user_message_bot_notify_on ERROR: {e}")

        return False
    

async def send_app_user_message_text_bot_notify_unknown(user_id: int, message_text: str):
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id))).scalars().first()
            if not user:
                await put_critical_error_into_db("send_app_user_message_bot_notify_unknown", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return False
            
            user_tg_id = user.tg_id
            bot_notify_on = user.settings.get("bot_notify_on", True)

            if bot_notify_on:
                await bot.send_message(
                    chat_id=user_tg_id,
                    text=message_text,
                    parse_mode=None,
                )
                return True
            else:
                return False

        except Exception as e:
            await put_critical_error_into_db("send_app_user_message_bot_notify_unknown", "main exception error", str(e), {"user_id": user_id})
            logger.exception(f"send_app_user_message_bot_notify_unknown ERROR: {e}")
            return False