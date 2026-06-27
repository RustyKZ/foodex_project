import asyncio
import aio_pika
import json
from config import settings
THIS_SERVICE_NAME = settings.API_SERVICE_NAME
RABBIT_USERNAME = settings.API_SERVICE_RABBIT_USERNAME
RABBIT_PASSWORD = settings.API_SERVICE_RABBIT_PASSWORD
RABBIT_HOST = settings.API_SERVICE_RABBIT_HOST
RABBITMQ_URL = f"amqp://{RABBIT_USERNAME}:{RABBIT_PASSWORD}@{RABBIT_HOST}/"
INSTANCE_ID = settings.INSTANCE_ID
QUEUE_NAME = f"{settings.PROJECT_NAME}_{settings.API_SERVICE_NAME}_{INSTANCE_ID}"
EXCHANGE_NAME = settings.RABBIT_BROADCAST_EXCHANGE_NAME #"broadcast_exchange"
DIRECT_EXCHANGE_NAME = settings.RABBIT_DIRECT_EXCHANGE_NAME
DIRECT_QUEUE_NAME = settings.API_SERVICE_RABBIT_DIRECT_QUEUE_NAME
ROUTING_KEY = f"{THIS_SERVICE_NAME}.task"

from .rabbit_message_processor import message_processing

from logger_config import get_logger
logger = get_logger(__name__)


async def receive_message():
    logger.info("RabbitMQ broadcast listener starting...")

    while True:
        connection = None

        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)

            logger.info("Connected to RabbitMQ broadcast exchange")

            channel = await connection.channel()

            exchange = await channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.FANOUT
            )

            queue = await channel.declare_queue(
                QUEUE_NAME,
                durable=True
            )

            await queue.bind(exchange)

            async def handle_message(message: aio_pika.IncomingMessage):
                async with message.process():
                    raw_msg = message.body.decode()

                    logger.info(f"BROADCAST Received message: {raw_msg}")

                    try:
                        msg = json.loads(raw_msg)
                        await message_processing(msg)

                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON decode error: {e}")

            await queue.consume(handle_message)

            while True:
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("receive_message cancelled")
            break

        except Exception as e:
            logger.exception(f"receive_message exception: {e}")

            logger.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

        finally:
            try:
                if connection and not connection.is_closed:
                    logger.warning(f"!!!!!!!!!!!!!!!!!!!! ------------------- receive_message: CONNECTION CLOSED")
                    await connection.close()
            except Exception as e:
                logger.exception(f"receive_message exception: {e}")
                pass


async def receive_distributed_task():
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
