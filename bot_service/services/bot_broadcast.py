import asyncio
import os
import aiohttp
import tempfile

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from logger_config import get_logger


from models.app_users import AppUser
from sqlalchemy import select, func, asc, desc
from sqlalchemy.exc import SQLAlchemyError

from bot_config import bot
from session_config import async_session

from services.error import put_critical_error_into_db

from config import settings
ADMIN_IDS = settings.ADMIN_TG_IDS


logger = get_logger(__name__)

async def get_all_active_users_from_db_with_notify_on() -> list:
    async with async_session() as session:
        try:
            query = select(AppUser.tg_id, AppUser.settings).where(AppUser.tg_id.is_not(None), AppUser.active.is_(True))
            result = await session.execute(query)
            users = result.mappings().all()
            user_ids = []
            if users:
                for row in users:
                    user_tg_id = row["tg_id"]
                    settings = {}
                    if isinstance(row["settings"], dict):
                        settings = row["settings"]
                    bot_notify_on = settings.get("bot_notify_on", True)
                    if bot_notify_on:
                        user_ids.append(user_tg_id)
            return user_ids
        except Exception as e:
            await put_critical_error_into_db("get_all_active_users_from_db_with_notify_on", "main exception error", str(e), {})
            return []
        
        
async def get_users_from_userlist_with_notify_on(userlist: list) -> list:
    async with async_session() as session:
        try:
            if not isinstance(userlist, list):
                await put_critical_error_into_db("get_users_from_userlist_with_notify_on", "Incorrect incoming data", "Incorrect incoming userlist", {"userlist": userlist})    
            query = select(AppUser.tg_id, AppUser.settings).where(AppUser.tg_id.in_(userlist))
            result = await session.execute(query)
            users = result.mappings().all()
            user_ids = []
            if users:
                for row in users:
                    user_tg_id = row["tg_id"]
                    settings = {}
                    if isinstance(row["settings"], dict):
                        settings = row["settings"]
                    bot_notify_on = settings.get("bot_notify_on", True)
                    if bot_notify_on or user_tg_id in ADMIN_IDS:
                        user_ids.append(user_tg_id)
            return user_ids
        except Exception as e:
            await put_critical_error_into_db("get_users_from_userlist_with_notify_on", "main exception error", str(e), {"userlist": userlist})
            return []


async def broadcast_message(userlist: list, message: dict):
    """
    Mass broadcast of messages to Telegram users.
    userlist — list of Telegram user IDs.
    message — dict with keys:
        image_path, message_text, button_name, button_link, html
    """

    image_path = message.get("image_path")
    message_text = message.get("message_text", "")
    button_name = message.get("button_name")
    button_link = message.get("button_link")
    html_mode = message.get("html", False)

    # Определяем формат текста
    parse_mode = "HTML" if html_mode else "MarkdownV2"

    file_id = None
    temp_file = None  # временный файл, если загружаем из интернета

    # --- Загрузка изображения из URL, если указана ссылка ---
    if image_path:
        if image_path.startswith("http"):
            logger.info(f"Downloading image from URL: {image_path}")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_path) as resp:
                        if resp.status == 200:
                            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                            temp_file.write(await resp.read())
                            temp_file.close()
                            image_path = temp_file.name
                            logger.info(f"Image downloaded to temp file: {image_path}")
                        else:
                            logger.info(f"Failed to download image: HTTP {resp.status}")
            except Exception as e:
                logger.info(f"Error downloading image: {e}")

        abs_path = os.path.abspath(image_path)

    # --- Inline keyboard creation ---
    keyboard = None
    if button_name and button_link:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=button_name, url=button_link)]
            ]
        )

    if userlist and isinstance(userlist, list):
        corrected_userlist = await get_users_from_userlist_with_notify_on(userlist)
    else:
        corrected_userlist = await get_all_active_users_from_db_with_notify_on()
    
    if not corrected_userlist:
        {"total_users": len(corrected_userlist), "sent": 0, "blocked": 0, "bad_request": 0, "unexpected": 0}

    sent_count = 0
    file_id = None

    blocked_count = 0
    bad_request_count = 0
    unexpected_count = 0

    # --- Broadcast loop ---
    for user_id in corrected_userlist:
        try:
            if image_path and file_id:
                logger.info(f"Sending cached photo message to {user_id}")
                await bot.send_photo(
                    chat_id=user_id,
                    photo=file_id,
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode=parse_mode
                )

            elif image_path and os.path.exists(image_path):
                logger.info(f"Sending photo file to {user_id}")
                await bot.send_photo(
                    chat_id=user_id,
                    photo=FSInputFile(image_path),
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode=parse_mode
                )

            else:
                logger.info(f"Sending text message to {user_id}")
                await bot.send_message(
                    chat_id=user_id,
                    text=message_text or "(empty message)",
                    reply_markup=keyboard,
                    parse_mode=parse_mode
                )

            sent_count += 1
            await asyncio.sleep(0.05)  # Avoid Telegram API flood limits

        except TelegramForbiddenError:
            logger.error(f"User {user_id} blocked the bot")
            blocked_count += 1
        except TelegramBadRequest as e:
            logger.error(f"BadRequest while sending to {user_id}: {e}")
            bad_request_count += 1
        except Exception as e:
            logger.error(f"Unexpected error while sending to {user_id}: {e}")
            unexpected_count += 1

    logger.info(f"Broadcast finished: {sent_count}/{len(userlist)} messages sent.")

    # --- Clean up temporary file if created ---
    if temp_file:
        try:
            os.unlink(temp_file.name)
            logger.info("Temporary file deleted.")
        except Exception as e:
            logger.info(f"Failed to delete temp file: {e}")
    
    return {"total_users": len(userlist), "sent": sent_count, "blocked": blocked_count, "bad_request": bad_request_count, "unexpected": unexpected_count}