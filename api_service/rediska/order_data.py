from rediska.redis_cli import redis_client

from rediska.redis_queue import redis_queue

from datetime import datetime, timedelta, timezone

from logger_config import get_logger
logger = get_logger(__name__)

from constants.redis_vars import PRODUCT_ORDERED
from constants.default import PRODUCTS_ORDERED_FORWARD_DAYS

async def get_product_ordered_quantity(product_id: int, supplier_date: str) -> dict:
    try:
        key = f"{PRODUCT_ORDERED}:{product_id}:{supplier_date}"    
        value = await redis_client.get(key)        
        if value is None:
            ordered = 0
        else:
            ordered = float(value)
        return {"status": True, "ordered": ordered}    
    except Exception as e:
        logger.error(f"get_product_ordered_quantity - MAIN EXCEPTION ERROR: {e}")
        return {"status": False}

"""
async def add_product_ordered_quantity(product_id: int, supplier_date: str, order_quantity: float, ttl_timestamp: int):
    try:
        key = f"{PRODUCT_ORDERED}:{product_id}:{supplier_date}"
        # атомарное увеличение
        new_value = await redis_client.incrbyfloat(key, order_quantity)
        # если ключ только что создан — ставим TTL
        ttl = await redis_client.ttl(key)
        if ttl == -1:
            await redis_client.expireat(key, ttl_timestamp)        
        return {"status": True, "ordered": float(new_value)}
    except Exception as e:
        logger.error(f"add_product_ordered_quantity - MAIN EXCEPTION ERROR: {e}")
        return {"status": False}
"""


async def queue_add_product_ordered_quantity(product_id: int, supplier_date: str, order_quantity: float, ttl_timestamp: int):
    await redis_queue.put({
        "product_id": product_id,
        "supplier_date": supplier_date,
        "order_quantity": order_quantity,
        "ttl_timestamp": ttl_timestamp
    })


async def get_product_ordered_quantity_by_id(product_id: int) -> dict:
    try:
        forward_days = PRODUCTS_ORDERED_FORWARD_DAYS  # например 20

        # 1. Текущая дата (UTC — этого достаточно для твоей логики)
        today = datetime.now(timezone.utc).date()

        # 2. Формируем диапазон: вчера → вперед
        start_date = today - timedelta(days=1)
        total_days = forward_days + 1  # +1 потому что берем вчера

        dates = [
            (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(total_days)
        ]

        # 3. Pipeline в Redis
        pipe = redis_client.pipeline()

        keys = []
        for d in dates:
            key = f"{PRODUCT_ORDERED}:{product_id}:{d}"
            keys.append(key)
            pipe.get(key)

        values = await pipe.execute()

        # 4. Собираем результат (пропускаем пустые)
        result = {}
        for d, v in zip(dates, values):
            if v is not None:
                result[d] = float(v)

        return result

    except Exception as e:
        logger.error(f"get_product_ordered_quantity_by_id - MAIN EXCEPTION ERROR: {e}")
        return {}