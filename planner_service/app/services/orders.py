from sqlalchemy import select
from datetime import datetime, timezone

from ..models.orders import Order, OrderItem

from ..rabbit.celery_rabbit_sender import broadcast_message, send_direct_message

from ..constants.redis_vars import PRODUCT_ORDERED, UPDATING_ORDERS_NOW, MAX_TIME_UPDATING_ORDERS
from ..constants.orders import REDIS_RELEVANT_ORDERS_STATUSES
from ..constants.system_log import *

from ..rediska.redis_client import redis_client
from ..session_config import sync_session

from ..logger_config import get_logger
logger = get_logger(__name__)

from ..config import settings
THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME
API_SERVICE_NAME = settings.API_SERVICE_NAME
BATCH_SIZE = settings.REQUEST_BATCH_SIZE

from .error import put_critical_error_into_db
from .system_action import put_system_action_into_db_log


def get_orders_updated_data():
    try:
        current_time_unix = int(datetime.now(timezone.utc).timestamp())
        itemlist = []

        with sync_session() as session:
            rows = session.execute(
                select(Order.id, Order.supplier_date, Order.supplier_ttl).where(
                    Order.supplier_ttl > current_time_unix,
                    Order.status.in_(REDIS_RELEVANT_ORDERS_STATUSES)
                )
            ).mappings().all()
            order_ids = []
            order_data = {}
            for row in rows:
                order_id = row["id"]

                order_ids.append(order_id)

                order_data[order_id] = {
                    "supplier_date": row["supplier_date"],
                    "supplier_ttl": row["supplier_ttl"]
                }

            if order_ids:
                start_id = 0
                while True:
                    items = session.scalars(
                        select(OrderItem)
                        .where(
                            OrderItem.id > start_id,
                            OrderItem.order_id.in_(order_ids)
                        )
                        .order_by(OrderItem.id)
                        .limit(BATCH_SIZE)
                    ).all()

                    if not items:
                        break
                    
                    for item in items:
                        order_id = item.order_id
                        product_id = item.product_id
                        order_dict = order_data.get(order_id, {})
                        supplier_date = order_dict.get("supplier_date", None)
                        quantity = float(item.amount)
                        ttl = order_dict.get("supplier_ttl", 0)
                        if supplier_date and ttl:
                            key = f"{PRODUCT_ORDERED}:{product_id}:{supplier_date}"
                            itemlist.append({"key": key, "quantity": quantity, "ttl": ttl})

                    start_id = items[-1].id

        return {"status": True, "itemlist": itemlist}
    except Exception as e:
        logger.exception(f"DEF orders_updating - Exception: {e}")
        put_critical_error_into_db( "orders_updating", "main exception error", f"Error text: {str(e)}", {})
        return {"status": False}

def start_planner_orders_updating():
    logger.info(f"DEF start_planner_orders_updating")
    timestart_float = datetime.now(timezone.utc).timestamp()    
    event = EVENT_REDIS_ORDERS_UPDATING_START
    status = SYSTEM_ACTION_STATUS_UNDEFINED
    description = ""
    meta_json = {}
    try:
        redis_client.set(UPDATING_ORDERS_NOW, 1, ex=MAX_TIME_UPDATING_ORDERS)

        updated_orders_data = get_orders_updated_data()
        if updated_orders_data["status"]:
            
            cursor = 0

            while True:
                cursor, keys = redis_client.scan(
                    cursor=cursor,
                    match=f"{PRODUCT_ORDERED}:*",
                    count=1000
                )
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break

            itemlist = updated_orders_data.get("itemlist", [])
            for itemdata in itemlist:
                key = itemdata.get("key")
                quantity = itemdata.get("quantity")
                ttl = itemdata.get("ttl")
                redis_client.incrbyfloat(key, quantity)
                current_ttl = redis_client.ttl(key)
                if current_ttl == -1:
                    redis_client.expireat(key, ttl)                    
            status = SYSTEM_ACTION_STATUS_SUCCESS
            meta_json["updated_redis_orderitems"] = len(itemlist)
        else:
            status = SYSTEM_ACTION_STATUS_ERROR
            description = f"Cannot getting correct data from DB"
        
    except Exception as e:
        logger.exception(f"DEF start_planner_orders_updating - Exception: {e}")
        put_critical_error_into_db( "start_planner_orders_updating", "main exception error", f"Error text: {str(e)}", {})        
        status = SYSTEM_ACTION_STATUS_ERROR
        description = f"Exception error: {e}"
    finally:
        try:            
            redis_client.delete(UPDATING_ORDERS_NOW)
        except Exception as f_e:
            logger.exception(f"DEF start_planner_orders_updating - Finally exception: {f_e}")
            put_critical_error_into_db( "start_planner_orders_updating", "finally exception error", f"Error text: {str(f_e)}", {})
        timeend_float = datetime.now(timezone.utc).timestamp()
        duration = timeend_float - timestart_float
        put_system_action_into_db_log(event=event, status=status, description=description, meta_json=meta_json, duration=duration)


def daily_live_orders_updating():
    logger.info(f"DEF daily_live_orders_updating")
    timestart_float = datetime.now(timezone.utc).timestamp()
    event = EVENT_REDIS_ORDERS_UPDATING_DAILY
    status = SYSTEM_ACTION_STATUS_UNDEFINED
    description = ""
    meta_json = {}
    try:
        redis_client.set(UPDATING_ORDERS_NOW, 1, ex=MAX_TIME_UPDATING_ORDERS)

        updated_orders_data = get_orders_updated_data()
        if updated_orders_data["status"]:
            
            cursor = 0

            while True:
                cursor, keys = redis_client.scan(
                    cursor=cursor,
                    match=f"{PRODUCT_ORDERED}:*",
                    count=1000
                )
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break

            itemlist = updated_orders_data.get("itemlist", [])
            for itemdata in itemlist:
                key = itemdata.get("key")
                quantity = itemdata.get("quantity")
                ttl = itemdata.get("ttl")
                redis_client.incrbyfloat(key, quantity)
                current_ttl = redis_client.ttl(key)
                if current_ttl == -1:
                    redis_client.expireat(key, ttl)                    
            status = SYSTEM_ACTION_STATUS_SUCCESS
            meta_json["updated_redis_orderitems"] = len(itemlist)
        else:
            status = SYSTEM_ACTION_STATUS_ERROR
            description = f"Cannot getting correct data from DB"
        
    except Exception as e:
        logger.exception(f"DEF daily_live_orders_updating - Exception: {e}")
        put_critical_error_into_db( "daily_live_orders_updating", "main exception error", f"Error text: {str(e)}", {})        
        status = SYSTEM_ACTION_STATUS_ERROR
        description = f"Exception error: {e}"
    finally:
        try:            
            redis_client.delete(UPDATING_ORDERS_NOW)
        except Exception as f_e:
            logger.exception(f"DEF daily_live_orders_updating - Finally exception: {f_e}")
            put_critical_error_into_db( "daily_live_orders_updating", "finally exception error", f"Error text: {str(f_e)}", {})
        timeend_float = datetime.now(timezone.utc).timestamp()
        duration = timeend_float - timestart_float
        put_system_action_into_db_log(event=event, status=status, description=description, meta_json=meta_json, duration=duration)
    
