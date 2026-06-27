import asyncio
import aio_pika
import json
from config import settings
RABBIT_USERNAME = settings.API_SERVICE_RABBIT_USERNAME
RABBIT_PASSWORD = settings.API_SERVICE_RABBIT_PASSWORD
RABBIT_HOST = settings.API_SERVICE_RABBIT_HOST
RABBIT_BROADCAST_MAX_DELAY = settings.RABBIT_BROADCAST_MAX_DELAY

BROADCAST_EXCHANGE_NAME = settings.RABBIT_BROADCAST_EXCHANGE_NAME
DIRECT_EXCHANGE_NAME = settings.RABBIT_DIRECT_EXCHANGE_NAME

BOT_SERVICE_NAME = settings.BOT_SERVICE_NAME

RABBITMQ_URL = f"amqp://{RABBIT_USERNAME}:{RABBIT_PASSWORD}@{RABBIT_HOST}/"

async def broadcast_message_async(message: dict) -> dict:
    timeout = RABBIT_BROADCAST_MAX_DELAY
    timeout_seconds = timeout / 1000  # convert to seconds

    async def _send():
        try:
            serialized = json.dumps(message)
        except (TypeError, ValueError):
            serialized = json.dumps({"error": "Invalid message in broadcast"})

        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange(BROADCAST_EXCHANGE_NAME, aio_pika.ExchangeType.FANOUT)
                await exchange.publish(
                    aio_pika.Message(body=serialized.encode()),
                    routing_key=""
                )
            return {"status": True}
        except Exception as e:
            return {"status": False, "error_message": f"RabbitMQ publish error: {str(e)}"}

    try:
        return await asyncio.wait_for(_send(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return {"status": False, "error_message": f"RabbitMQ broadcast timeout after {timeout} ms"}
    

async def direct_task_async(service_name: str, message: dict):
    ROUTING_KEY = f"{service_name}.task"
    serialized = json.dumps(message)    
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(DIRECT_EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT)
        await exchange.publish(
            aio_pika.Message(body=serialized.encode()),
            routing_key=ROUTING_KEY,
        )
