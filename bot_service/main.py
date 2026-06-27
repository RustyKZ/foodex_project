import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram import F
from aiogram.types import PreCheckoutQuery

from logger_config import setup_logger
from services.rabbit_receiver import receive_disributed_task
from services.bot_receiver import receive_bot_command
from services.bot_processor import send_star_payment_result

from config import settings
BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN

setup_logger()
logger = logging.getLogger(__name__)


async def start_telegram_bot():
    """Асинхронный запуск Telegram-бота"""
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        print(f"PRE CHECKOUT: {pre_checkout_query}")
        await pre_checkout_query.answer(ok=True)
    
    @dp.message(F.successful_payment)
    async def successful_payment_handler(message: types.Message):        
        telegram_user_id = message.from_user.id
        payment = message.successful_payment

        charge_id = payment.telegram_payment_charge_id
        amount = payment.total_amount
        payload = payment.invoice_payload

        language = getattr(message.from_user, "language_code", "en")

        payment_data = {
            "user_tg_id": telegram_user_id,
            "charge_id": charge_id,
            "amount": amount,
            "payload": payload,
            "language": language
        }
        await send_star_payment_result(payment_data)
    
    @dp.message()
    async def on_message(message: types.Message):
        """Любое входящее сообщение"""
        data = {
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "text": message.text,
            "chat_id": message.chat.id,
            "message_id": message.message_id,
            "date": message.date.isoformat(),
            "language": message.from_user.language_code,
        }
        await receive_bot_command(data)

    logger.info("🤖 Telegram bot started and polling...")
    await dp.start_polling(bot)


async def start_rabbit_listener():
    """Асинхронный запуск слушателя RabbitMQ"""
    logger.info("📥 Starting RabbitMQ listener...")
    await receive_disributed_task()


async def main():
    logger.info("🚀 BOT service starting...")

    try:
        # Параллельный запуск Telegram и RabbitMQ
        await asyncio.gather(
            start_telegram_bot(),
            start_rabbit_listener()
        )

    except asyncio.CancelledError:
        logger.info("🛑 BOT service shutting down (cancelled)")
    except Exception as e:
        logger.exception(f"❌ Unhandled exception: {e}")
    finally:
        logger.info("🔚 BOT service stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 BOT service stopped by user (KeyboardInterrupt)")
