import asyncio
import aio_pika
import json
from config import settings

RABBIT_USERNAME = settings.BOT_SERVICE_RABBIT_USERNAME
RABBIT_PASSWORD = settings.BOT_SERVICE_RABBIT_PASSWORD
RABBIT_HOST = settings.BOT_SERVICE_RABBIT_HOST
RABBITMQ_URL = f"amqp://{RABBIT_USERNAME}:{RABBIT_PASSWORD}@{RABBIT_HOST}/"
INSTANCE_ID = settings.INSTANCE_ID
THIS_SERVICE_NAME = settings.BOT_SERVICE_NAME

DIRECT_EXCHANGE_NAME = settings.RABBIT_DIRECT_EXCHANGE_NAME
DIRECT_QUEUE_NAME = settings.BOT_SERVICE_RABBIT_DIRECT_QUEUE_NAME
ROUTING_KEY = f"{THIS_SERVICE_NAME}.task"

from services.rabbit_message_processor import message_processing

from logger_config import get_logger
logger = get_logger(__name__)


async def receive_disributed_task():
    logger.info(f"Service {THIS_SERVICE_NAME} - Instance {INSTANCE_ID}: (receive_disributed_task) - RabbitMQ direct listener starting...")
    while True:
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            logger.info("✅ Connected to RabbitMQ direct exchange")
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange(DIRECT_EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT)
                queue = await channel.declare_queue(DIRECT_QUEUE_NAME, durable=True)
                await queue.bind(exchange, routing_key=ROUTING_KEY)

                async def handle_message(message: aio_pika.IncomingMessage):
                    async with message.process():
                        raw_msg = message.body.decode()
                        logger.info(f"Service {THIS_SERVICE_NAME} - Instance {INSTANCE_ID}: (receive_disributed_task) - DIRECT Received message: {raw_msg}")
                        try:
                            msg = json.loads(raw_msg)
                            await message_processing(msg)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Service {THIS_SERVICE_NAME} - Instance {INSTANCE_ID}: (receive_disributed_task) - DIRECT Failed to decode JSON message: {e}")                            

                await queue.consume(handle_message)

                await asyncio.Future()

        except asyncio.CancelledError:
            logger.info(f"Service {THIS_SERVICE_NAME} - Instance {INSTANCE_ID}: (receive_disributed_task) - CANCELLED")
            break
        except Exception as e:
            logger.exception(f"Service {THIS_SERVICE_NAME} - Instance {INSTANCE_ID}: (receive_disributed_task) - receive_fight_tasks Exception error: {e}")            
            logger.info(f"Service {THIS_SERVICE_NAME} - Instance {INSTANCE_ID}: (receive_disributed_task) - DIRECT: Reconnecting to RabbitMQ in 5 seconds...")            
            await asyncio.sleep(5)
