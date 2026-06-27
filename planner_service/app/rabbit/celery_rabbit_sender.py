import json
import pika
from ..config import settings

RABBIT_USERNAME = settings.PLANNER_SERVICE_RABBIT_USERNAME
RABBIT_PASSWORD = settings.PLANNER_SERVICE_RABBIT_PASSWORD
RABBIT_HOST = settings.PLANNER_SERVICE_RABBIT_HOST

RABBITMQ_URL = f"amqp://{RABBIT_USERNAME}:{RABBIT_PASSWORD}@{RABBIT_HOST}/"

EXCHANGE_NAME = settings.RABBIT_BROADCAST_EXCHANGE_NAME
DIRECT_EXCHANGE_NAME = settings.RABBIT_DIRECT_EXCHANGE_NAME

THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME


def _get_connection():
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def broadcast_message(message: dict):
    try:
        body = json.dumps(message)
    except (TypeError, ValueError):
        body = json.dumps({
            "error": "PLANNER SERVICE trying to send incorrect message"
        })

    connection = _get_connection()
    channel = connection.channel()

    # ❌ УБРАЛИ exchange_declare

    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key="",
        body=body.encode(),
    )

    connection.close()


def send_direct_message(service_name: str, message: dict):
    ROUTING_KEY = f"{service_name}.task"
    body = json.dumps(message)

    connection = _get_connection()
    channel = connection.channel()

    # ❌ УБРАЛИ exchange_declare

    channel.basic_publish(
        exchange=DIRECT_EXCHANGE_NAME,
        routing_key=ROUTING_KEY,
        body=body.encode(),
    )

    connection.close()