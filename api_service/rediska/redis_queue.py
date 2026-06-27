import asyncio

redis_queue = asyncio.Queue()

from constants.redis_vars import PRODUCT_ORDERED, UPDATING_ORDERS_NOW

from rediska.redis_cli import redis_client
from logger_config import get_logger

logger = get_logger(__name__)

"""
async def redis_product_ordered_worker():
    while True:
        try:
            task = await redis_queue.get()

            product_id = task["product_id"]
            supplier_date = task["supplier_date"]
            quantity = task["order_quantity"]
            ttl = task["ttl_timestamp"]

            key = f"{PRODUCT_ORDERED}:{product_id}:{supplier_date}"

            await redis_client.incrbyfloat(key, quantity)

            current_ttl = await redis_client.ttl(key)
            if current_ttl == -1:
                await redis_client.expireat(key, ttl)

        except Exception as e:
            logger.error(f"redis_worker error: {e}")

        finally:
            redis_queue.task_done()
"""

async def redis_product_ordered_worker():
    while True:
        try:
            # Проверяем флаг обновления Redis
            updating_now = await redis_client.get(UPDATING_ORDERS_NOW)

            if updating_now:
                updating_now = updating_now.decode() if isinstance(updating_now, bytes) else str(updating_now)

                if updating_now.lower() in ("true", "1", "yes"):
                    await asyncio.sleep(1)
                    continue

            task = await redis_queue.get()

            try:
                product_id = task["product_id"]
                supplier_date = task["supplier_date"]
                quantity = task["order_quantity"]
                ttl = task["ttl_timestamp"]

                key = f"{PRODUCT_ORDERED}:{product_id}:{supplier_date}"

                await redis_client.incrbyfloat(key, quantity)

                current_ttl = await redis_client.ttl(key)
                if current_ttl == -1:
                    await redis_client.expireat(key, ttl)

            finally:
                redis_queue.task_done()

        except Exception as e:
            logger.error(f"redis_worker error: {e}")
            await asyncio.sleep(1)


