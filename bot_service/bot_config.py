from aiogram import Bot
from config import settings
BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
