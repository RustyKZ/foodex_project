from .config import settings
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
ENVS_DIR = BASE_DIR.parent.parent / "envs"
RABBIT_USERNAME = settings.PLANNER_SERVICE_RABBIT_USERNAME
RABBIT_PASSWORD = settings.PLANNER_SERVICE_RABBIT_PASSWORD
RABBIT_HOST = settings.PLANNER_SERVICE_RABBIT_HOST

from celery import Celery
import os

RABBITMQ_URL = f"amqp://{RABBIT_USERNAME}:{RABBIT_PASSWORD}@{RABBIT_HOST}/"

print(f"-------------------------- START PLANNER ----------------------------------")
print(f"Base dir: {BASE_DIR}")
print(f"Env dir: {ENVS_DIR}")

# Создаем экземпляр Celery
celery_app = Celery(
    'bm_planner',
    broker=RABBITMQ_URL,
    # backend='rpc://'  # или другой backend для хранения результатов, если нужен
)

# Если есть настройки (например, по конфигу Django/или свой конфиг)
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

celery_app.autodiscover_tasks([
    "app",
])

from app.task_management import *

from app.celery_beat import *

from app.startup import *
