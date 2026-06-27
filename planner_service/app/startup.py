# startup.py

from celery.signals import worker_ready

from .services.orders import start_planner_orders_updating
from .logger_config import get_logger

logger = get_logger(__name__)

@worker_ready.connect
def startup_tasks(sender=None, **kwargs):
    logger.info("PLANNER_SERVICE startup tasks")
    start_planner_orders_updating()