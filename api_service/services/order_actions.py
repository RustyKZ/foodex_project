from models.busineses import Business, BusinessTranslation
from models.app_users import AppUser
from models.reviews import ReviewBusiness, ReviewProduct
from models.interface import LanguageInterface
from models.products import Product, ProductTranslation
from models.orders import Order, OrderItem
from models.messages import Message

from datetime import datetime, timezone, timedelta

from sqlalchemy import insert, update, or_, and_, func

from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from .error import put_critical_error_into_db

from .interfaces import get_interface

from constants.log_entitys import CREATE, UPDATE, DELETE, BUSINESS, REPLY, EMPLOYEE, CONFIRM, REJECT, PRODUCT, INDIVIDUAL_CUSTOMER_ACCOUNT

from constants.languages import get_languages
from constants.geodata import MIN_LATITUDE, MAX_LATITUDE, MIN_LONGITUDE, MAX_LONGITUDE
from constants.business_types import SUPPLIER, CUSTOMER, INDIVIDUAL, SUPPLIER_ROLE, CUSTOMER_ROLE
from constants.rate_system import MAX_RATE, MIN_RATE, MAX_COMMENT_LENGTH
from constants.schedule import DEFAULT_SCEDULE
from constants.orders import *
from constants.default import DEFAULT_GEODATA, DEFAULT_LANGUAGE, DEFAULT_TIMEZONE, CUSTOMER_PRODUCT_CATALOG_FILTERS, INDIVIDUAL_PRODUCT_CATALOG_FILTERS, BUSINESS_ORDERS_DEFAULT_FILTER_SETTINGS
from constants.redis_vars import UPDATING_ORDERS_NOW

from system_i18n.orders import ORDER_MESSAGES_DICT
from system_i18n.measures import MEASURE_SHORT_DICT


from constants.frontend import TAB_MESSAGE_CENTER

from shemas.general import ArrayOfIds
from shemas.orders import MakeOrder, OrderRating

from decimal import Decimal

from pydantic import ValidationError

import pytz

from rediska.order_data import get_product_ordered_quantity
from rediska.redis_cli import redis_client


from io import BytesIO
from openpyxl import Workbook


DAY_SECONDS = 86400
WEEK_SECONDS = 7 * DAY_SECONDS
DAY_KEYS = [str(i) for i in range(7)]

def shift_schedule(schedule: dict, offset_hours: int) -> dict:
    """Сдвигаем расписание на offset_hours относительно начала недели"""
    offset_seconds = offset_hours * 3600
    if schedule.get("without_rest"):
        return {**schedule}
    
    # Шаг 1: строим недельный таймлайн "нерабочих интервалов"
    breaks = []
    for day_str in DAY_KEYS:
        day_data = schedule.get(day_str, {"restday": False, "start": 0, "end": DAY_SECONDS, "breaks": []})
        day_offset = int(day_str) * DAY_SECONDS

        if day_data["restday"]:
            breaks.append({"start": day_offset, "end": day_offset + DAY_SECONDS})
        else:
            # до начала рабочего дня
            if day_data["start"] > 0:
                breaks.append({"start": day_offset, "end": day_offset + day_data["start"]})
            # после окончания рабочего дня
            if day_data["end"] < DAY_SECONDS:
                breaks.append({"start": day_offset + day_data["end"], "end": day_offset + DAY_SECONDS})
            # перерывы
            for br in day_data.get("breaks", []):
                breaks.append({"start": day_offset + br["start"], "end": day_offset + br["end"]})

    # Шаг 2: сдвигаем интервалы и нормализуем по неделе
    def shift_and_wrap(intervals):
        result = []
        for br in intervals:
            new_start = (br["start"] + offset_seconds + WEEK_SECONDS) % WEEK_SECONDS
            new_end = (br["end"] + offset_seconds + WEEK_SECONDS) % WEEK_SECONDS
            if new_start == new_end:
                continue
            if new_end < new_start:
                # пересекает конец недели
                result.append({"start": new_start, "end": WEEK_SECONDS})
                result.append({"start": 0, "end": new_end})
            else:
                result.append({"start": new_start, "end": new_end})
        return result

    shifted_breaks = shift_and_wrap(breaks)
    # Шаг 3: объединяем пересекающиеся интервалы
    shifted_breaks.sort(key=lambda x: x["start"])
    merged = []
    for br in shifted_breaks:
        if not merged or merged[-1]["end"] < br["start"]:
            merged.append(br.copy())
        else:
            merged[-1]["end"] = max(merged[-1]["end"], br["end"])
    shifted_breaks = merged

    # Шаг 4: разбиваем на дни
    daily_schedule = {}
    for day_str in DAY_KEYS:
        daily_schedule[day_str] = {"start": 0, "end": DAY_SECONDS, "breaks": [], "restday": False}

    for br in shifted_breaks:
        start_day = br["start"] // DAY_SECONDS
        end_day = br["end"] // DAY_SECONDS
        for d in range(int(start_day), int(end_day)+1):
            day_str = str(d % 7)
            day_start = br["start"] % DAY_SECONDS if d == start_day else 0
            day_end = br["end"] % DAY_SECONDS if d == end_day else DAY_SECONDS
            daily_schedule[day_str]["breaks"].append({"start": day_start, "end": day_end})

    # Шаг 5: вычисляем start, end, restday
    for day_str in DAY_KEYS:
        day = daily_schedule[day_str]
        if not day["breaks"]:
            day["start"] = 0
            day["end"] = DAY_SECONDS
            day["restday"] = False
            continue
        # объединяем интервалы
        day["breaks"].sort(key=lambda x: x["start"])
        merged = []
        for br in day["breaks"]:
            if not merged or merged[-1]["end"] < br["start"]:
                merged.append(br.copy())
            else:
                merged[-1]["end"] = max(merged[-1]["end"], br["end"])
        day["breaks"] = merged
        # вычисляем start и end рабочего дня
        first_br = merged[0]
        last_br = merged[-1]
        day["start"] = first_br["end"] if first_br["start"] == 0 else 0
        day["end"] = last_br["start"] if last_br["end"] == DAY_SECONDS else DAY_SECONDS
        total_break = sum([br["end"] - br["start"] for br in merged])
        day["restday"] = total_break >= DAY_SECONDS

    daily_schedule["without_rest"] = False
    return daily_schedule


def intersect_schedules(schedule_a: dict, schedule_b: dict) -> dict:
    """Пересечение рабочих интервалов двух расписаний"""
    if schedule_a.get("without_rest") and schedule_b.get("without_rest"):
        return {**DEFAULT_SCEDULE}
    result = {"without_rest": False}
    for day_str in DAY_KEYS:
        a = schedule_a.get(day_str, {"restday": True})
        b = schedule_b.get(day_str, {"restday": True})
        if a["restday"] or b["restday"]:
            result[day_str] = {"restday": True, "start": 0, "end": DAY_SECONDS, "breaks": []}
            continue
        start = max(a["start"], b["start"])
        end = min(a["end"], b["end"])
        if start >= end:
            result[day_str] = {"restday": True, "start": 0, "end": DAY_SECONDS, "breaks": []}
            continue
        breaks = a.get("breaks", []) + b.get("breaks", [])
        # объединяем
        breaks.sort(key=lambda x: x["start"])
        merged = []
        for br in breaks:
            if not merged or merged[-1]["end"] < br["start"]:
                merged.append(br.copy())
            else:
                merged[-1]["end"] = max(merged[-1]["end"], br["end"])
        # ограничиваем по start/end
        final_breaks = [{"start": max(br["start"], start), "end": min(br["end"], end)} for br in merged if br["end"] > br["start"]]
        result[day_str] = {"start": start, "end": end, "breaks": final_breaks, "restday": False}
    return result


def get_order_delivery_date(business, supplier, order_date: str, current_time: int) -> dict:
    try:
        business_tz = pytz.timezone(getattr(business, "timezone", DEFAULT_TIMEZONE))
        supplier_tz = pytz.timezone(getattr(supplier, "timezone", DEFAULT_TIMEZONE))

        tz_offset_hours = int(
            (                
                business_tz.utcoffset(datetime.utcfromtimestamp(current_time)) - 
                supplier_tz.utcoffset(datetime.utcfromtimestamp(current_time))
            ).total_seconds() / 3600
        )

        business_schedule = getattr(business, "schedule", DEFAULT_SCEDULE)
        supplier_schedule = getattr(supplier, "schedule", DEFAULT_SCEDULE)

        if not isinstance(business_schedule, dict) or business_schedule == {}:
            business_schedule = DEFAULT_SCEDULE
        if not isinstance(supplier_schedule, dict) or supplier_schedule == {}:
            supplier_schedule = DEFAULT_SCEDULE

        localized_business_schedule = shift_schedule(business_schedule, tz_offset_hours)
        common_schedule = intersect_schedules(supplier_schedule, localized_business_schedule)

        # ==================== DATE VALIDATION ====================
        order_dt = datetime.strptime(order_date, "%Y-%m-%d")

        # дата в TZ заказчика
        order_dt_business = business_tz.localize(order_dt)

        order_dt_ts = int(order_dt_business.timestamp())

        current_dt = datetime.fromtimestamp(current_time, tz=business_tz)
        
        today_dt = business_tz.localize(
            datetime(
                current_dt.year,
                current_dt.month,
                current_dt.day
            )
        )

        if order_dt_ts < int(today_dt.timestamp()):
            logger.error("get_order_delivery_date - date in past")
            return {"status": False}

        weekday = str(order_dt.weekday())
        day_sched = common_schedule.get(weekday)

        if not day_sched or day_sched["restday"]:
            logger.error("get_order_delivery_date - day off")
            return {"status": False}

        # ==================== DELIVERY TIME (BUSINESS TZ) ====================
        delivery_ts = int(order_dt_business.timestamp()) + day_sched["end"]

        # ==================== SUPPLIER DATE ====================
        # переводим дату в TZ поставщика
        order_dt_supplier = order_dt_business.astimezone(supplier_tz)

        supplier_date_str = order_dt_supplier.strftime("%Y-%m-%d")

        # ==================== TTL (END OF DAY SUPPLIER) ====================
        supplier_day_start = supplier_tz.localize(
            datetime(
                order_dt_supplier.year,
                order_dt_supplier.month,
                order_dt_supplier.day
            )
        )

        supplier_end_of_day_ts = int(supplier_day_start.timestamp()) + 86400

        return {
            "status": True,
            "date": delivery_ts,  # как раньше (для заказчика)
            "supplier_date": supplier_date_str,  # ключ Redis
            "supplier_ttl": supplier_end_of_day_ts  # TTL
        }

    except Exception as e:
        logger.error(f"get_order_delivery_date - MAIN EXCEPTION ERROR: {e}")
        return {"status": False}


def format_quantity(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip('0').rstrip('.')


async def make_order(user_id: int, order: dict) -> dict:
    async with async_session() as session:
        try:
            updating_now = await redis_client.get(UPDATING_ORDERS_NOW)
            if updating_now:
                return {"status": False, "notify_type": "warning", "notify_code": "notify_warning_updating_orders_now"}
            async with session.begin():
                try:
                    validated_order = MakeOrder(**order)
                except ValidationError as e:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True))
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db("make_order", "user not found or not active", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False}
                
                business_id = validated_order.business_id
                cart = validated_order.cart
                order_date = validated_order.order_date
                order_comment = validated_order.order_comment
                request_free_delivery = validated_order.request_free_delivery

                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()

                if not business:
                    logger.error(f"make_order - business is not active", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_is_not_exist"}
                
                if business.owner_id != user_id and not user_id in business.staff:
                    logger.error(f"make_order - user is not owner this business", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error"}
                
                customer_id = 0
                individual_id = 0

                if business.business_type == CUSTOMER:
                    customer_id = business.id
                elif business.business_type == INDIVIDUAL:
                    individual_id = business.id

                if customer_id == 0 and individual_id == 0:
                    logger.error(f"make_order - custome ID and individual ID are both 0", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}

                product_ids = []
                cart_dict = {}
                for cart_item in cart:
                    product_ids.append(cart_item.product_id)
                    cart_dict[cart_item.product_id] = cart_item.quantity

                products_query = select(Product).where(
                    Product.active.is_(True),
                    Product.deleted.is_(False),
                    Product.id.in_(product_ids)
                )
                products_result = await session.execute(products_query)
                products = products_result.scalars().all()

                if len(products) == 0:
                    logger.error(f"make_order - cannot to find actual products", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_actual_products_not_found"}
                
                supplier_id = products[0].business_id

                one_supplier = True                
                for product in products:
                    if product.business_id != supplier_id:
                        one_supplier = False
                
                if not one_supplier:
                    logger.error(f"make_order - incorrect cart", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_incorrect_cart"}
                
                supplier_query = select(Business).where(
                    Business.id == supplier_id, 
                    Business.active.is_(True), 
                    Business.deleted.is_(False),
                    Business.business_type == SUPPLIER
                )
                supplier_result = await session.execute(supplier_query)
                supplier = supplier_result.scalars().first()

                if not supplier:
                    logger.error(f"make_order - supplier {supplier_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_supplier_not_found"}
                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                delivery_date = 0
                supplier_date_str = None
                supplier_ttl = None
                delivery_date_calculation = get_order_delivery_date(business, supplier, order_date, current_time_unix)
                if delivery_date_calculation["status"]:
                    delivery_date = delivery_date_calculation.get("date", 0)
                    supplier_date_str = delivery_date_calculation.get("supplier_date", None)
                    supplier_ttl = delivery_date_calculation.get("supplier_ttl", None)
                
                if delivery_date == 0 or supplier_date_str is None or supplier_ttl is None:
                    logger.error(f"make_order - incorrect order date", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_order_incorrect_delivery_date"}
                
                user_language = user.language or DEFAULT_LANGUAGE

                first_product_translation_query = select(ProductTranslation.name).where(
                    ProductTranslation.language == user_language,
                    ProductTranslation.product_id == products[0].id
                )
                first_product_translation_result = await session.execute(first_product_translation_query)
                first_product_translation_name = first_product_translation_result.scalars().first()                                
                
                if first_product_translation_name:
                    first_product_cutted_name = first_product_translation_name[:100]
                else:
                    first_product_cutted_name = products[0].name[:100]

                measure_short_dict = MEASURE_SHORT_DICT.get(products[0].measure_code, {})
                measure_short = measure_short_dict.get(user_language, None)
                if not measure_short:
                    measure_short = measure_short_dict.get(DEFAULT_LANGUAGE, None)
                if not measure_short:
                    measure_short = products[0].measure_code                
                
                qty = format_quantity(cart_dict[products[0].id])

                if len(products) == 1:
                    order_suffix = f" - {qty} {measure_short}"
                elif len(products) == 2:
                    product_dict = ORDER_MESSAGES_DICT.get("product", {})
                    product_str = product_dict.get(user_language) or product_dict.get(DEFAULT_LANGUAGE, "")
                    order_suffix = f" - {qty} {measure_short} + {len(products) - 1} {product_str}"
                else:
                    products_dict = ORDER_MESSAGES_DICT.get("products", {})
                    products_str = products_dict.get(user_language) or products_dict.get(DEFAULT_LANGUAGE, "")
                    order_suffix = f" - {qty} {measure_short} + {len(products) - 1} {products_str}"

                order_name = first_product_cutted_name + order_suffix
                avatar_path = ""
                if products[0].avatar_name:
                    avatar_path = products[0].avatar_name

                new_order = Order(
                    date = current_time_unix,
                    name = order_name,
                    avatar = avatar_path,
                    supplier_id = supplier_id,
                    customer_id = customer_id,
                    individual_id = individual_id,
                    delivery_date = delivery_date,
                    status = ORDER_STATUS_CREATED,                    
                    cart = [item.model_dump() for item in validated_order.cart],
                    cart_order_date = order_date,
                    customer_comment = order_comment,
                    request_free_delivery = request_free_delivery,
                    currency = supplier.currency,
                    supplier_date = supplier_date_str,
                    supplier_ttl = supplier_ttl
                )

                session.add(new_order)
                await session.flush()

                new_order_id = new_order.id

                order_items_list = []
                delivery_cost = 0
                missed_price = False
                subtotal = 0

                for product in products:
                    can_be_ordered = True

                    order_quantity = cart_dict[product.id] or 0
                    minimal_order = product.min_order_quantity
                    maximal_order = product.max_order_quantity
                    daily_limit = product.daily_limit                    

                    if not (order_quantity is not None and order_quantity >= minimal_order):
                        can_be_ordered = False

                    if (maximal_order is not None and maximal_order > 0) and not (order_quantity is not None and order_quantity <= maximal_order):
                        can_be_ordered = False

                    if daily_limit is not None and daily_limit > 0:
                        get_ordered_data = await get_product_ordered_quantity(product_id=product.id, supplier_date=supplier_date_str)
                        already_ordered = 0
                        if get_ordered_data["status"]:
                            already_ordered = Decimal(get_ordered_data.get("ordered", 0))
                        else:
                            logger.error(f"make order - INCORRECT REDIS GET OPERATION", user_id=user_id)
                        if order_quantity > (daily_limit - already_ordered):
                            can_be_ordered = False
                    
                    if can_be_ordered:
                        if product.shipment_price and product.shipment_price > 0 and product.shipment_price > delivery_cost:
                            # The shipping cost of an order is determined as the maximum shipping cost from the items in the shopping cart.
                            delivery_cost = product.shipment_price
                        if product.price and product.price > 0:
                            subtotal += product.price * Decimal(order_quantity)
                        else:
                            missed_price = True

                        new_order_item = {
                            "order_id": new_order_id,
                            "product_id": product.id,
                            "measure_code": product.measure_code,
                            "amount": Decimal(order_quantity),
                            "price": product.price,
                            "cost": Decimal(order_quantity) * product.price,
                            "confirmed": False,
                            "product_snapshot": product.to_dict()
                        }
                        order_items_list.append(new_order_item)
                    
                    else:
                        logger.error(f"make order - product {product.id} can not be ordered")

                if request_free_delivery:
                    delivery_cost = 0

                new_order.delivery_cost = Decimal(delivery_cost)                
                new_order.subtotal = Decimal(subtotal)
                new_order.total = Decimal(delivery_cost) + Decimal(subtotal)
                new_order.missed_price = missed_price                

                stmt = insert(OrderItem)
                await session.execute(stmt, order_items_list)

                redis_product_add_list = []
                for order_item in order_items_list:                    
                    p = {
                        "product_id": order_item["product_id"], 
                        "supplier_date": supplier_date_str, 
                        "order_quantity": float(order_item["amount"]),
                        "ttl_timestamp": supplier_ttl
                    }
                    redis_product_add_list.append(p)
                
                supplier_staff = supplier.staff or []
                supplier_team = [supplier.owner_id] + supplier_staff

                customer_staff = business.staff or []
                customer_team = [business.owner_id] + customer_staff

                # Добавил сюда создание сообщения
                order_comment_message_id = None                
                if order_comment:
                    names_dict_users = {}
                    names_dict_users[f"{user_id}"] = user.username
                    names_dict_businesses = {
                        business_id: {
                            "native": business.name
                        },
                        supplier_id: {
                            "native": supplier.name
                        }
                    }
                    business_ids = [business_id, supplier_id]
                    business_names_local = (await session.execute(
                        select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                        .where(BusinessTranslation.business_id.in_(business_ids))
                    )).mappings().all()
                                
                    for row in business_names_local:
                        names_dict_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']
                    names_dict_businesses = {
                        str(k): v for k, v in names_dict_businesses.items()
                    }

                    new_message = Message(
                        order_id = new_order_id,
                        date = current_time_unix,
                        sender_business = business_id,
                        sender_user = user_id,
                        receiver_business = supplier_id,
                        text = order_comment,
                        names_dict_users = names_dict_users,
                        names_dict_businesses = names_dict_businesses
                    )
                    session.add(new_message)
                    await session.flush()
                    order_comment_message_id = new_message.id
                    
                return {
                    "status": True, 
                    "redis_product_add_list": redis_product_add_list, 
                    "supplier_team": supplier_team, 
                    "customer_team": customer_team,
                    "order_id": new_order_id, 
                    "order_comment_message_id": order_comment_message_id}

        except Exception as e:
            logger.exception(f"make_order - MAIN EXCEPTION ERROR: {e}") 
            await put_critical_error_into_db("make_order", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def get_business_orders(user_id: int, business_id: int) -> dict:         # Getting non-archived orders
    async with async_session() as session:
        async with session.begin():
            try:
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active == True))).scalars().first()
                if not user:
                    await put_critical_error_into_db("get_business_orders", "incorrect data", "User not found or inactive", {"user_id": user_id})
                    return {"status": False}
                
                business = (await session.execute(select(Business).where(
                    Business.id == business_id, 
                    Business.active.is_(True),
                    Business.deleted.is_(False),
                ))).scalars().first()
                
                if not business:
                    logger.error(f"get_business_orders - business {business_id} not found or inactive or deleted")
                    return {"status": False}
                
                if business_id != user.active_business_id:
                    logger.error(f"get_business_orders - business {business_id} is not active business of user {user_id}")
                    return {"status": False}                                
                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())
                cutoff_time = current_time_unix - ORDER_ARCHIVED_STATE_TIME
                business_type = business.business_type
                filters = []

                if business_type == SUPPLIER:
                    filters.append(Order.supplier_id == business_id)
                elif business_type == CUSTOMER:
                    filters.append(Order.customer_id == business_id)
                elif business_type == INDIVIDUAL:
                    filters.append(Order.individual_id == business_id)

                filters.append(or_(Order.last_update >= cutoff_time, Order.status.in_(ORDER_OPENED_STATUSES)))
                    
                orders_query = select(Order).where(*filters)
                orders_result = await session.execute(orders_query)
                orders = orders_result.scalars().all()

                order_ids = []
                orders_dict = {}

                business_ids = set()

                if not orders:
                    logger.info(f"get_business_orders - Actual orders not found...")
                    return {"status": True, "orders_dict": orders_dict}
                
                for order in orders:
                    order_ids.append(order.id)
                    if order.supplier_id:
                        business_ids.add(order.supplier_id)
                    if order.customer_id:
                        business_ids.add(order.customer_id)
                    if order.individual_id:
                        business_ids.add(order.individual_id)
                
                business_ids = list(business_ids)
                
                order_items_query = select(OrderItem).where(OrderItem.order_id.in_(order_ids))
                order_items_result = await session.execute(order_items_query)
                order_items = order_items_result.scalars().all()

                business_names_native = (await session.execute(
                    select(Business.id, Business.name, Business.avatar_name).where(Business.id.in_(business_ids))
                )).mappings().all()

                business_names_local = (await session.execute(
                    select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                    .where(BusinessTranslation.business_id.in_(business_ids))
                )).mappings().all()

                all_businesses = {}
                for row in business_names_native:
                    all_businesses[row['id']] = {"native": row['name'], "avatar": row['avatar_name']}
                
                for row in business_names_local:
                    all_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']

                for order in orders:
                    key = f"{order.id}"
                    orders_dict[key] = order.to_dict()
                    orders_dict[key]["items"] = []
                    supplier_key = order.supplier_id
                    customer_key = None
                    customer_key = order.customer_id or order.individual_id
                    orders_dict[key]["supplier_business"] = all_businesses.get(supplier_key, {})
                    orders_dict[key]["customer_business"] = all_businesses.get(customer_key, {})
                    orders_dict[key]["archived"] = False
                    if order.status == ORDER_STATUS_SUCCESS:
                        orders_dict[key]["rate_cutoff_date"] = order.last_update + ORDER_ARCHIVED_STATE_TIME
                    else:
                        orders_dict[key]["rate_cutoff_date"] = None
                    

                for order_item in order_items:
                    item_dict = order_item.to_dict()
                    orders_dict[f"{order_item.order_id}"]["items"].append(item_dict)

                return {"status": True, "orders_dict": orders_dict}

            except Exception as e:
                logger.exception(f"get_business_orders - MAIN EXCEPTION: {e}")
                await put_critical_error_into_db("get_business_orders", "main exception error", str(e), {"user_id": user_id})
                return {"status": False}
            

async def get_order(order_id: int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                order = (await session.execute(select(Order).where(Order.id == order_id, Order.deleted.is_(False)))).scalars().first()
                if not order:
                    logger.error(f"get_order - order {order_id} not found")
                    return {"status": False}

                supplier_id = order.supplier_id
                customer_id = None
                if order.customer_id:
                    customer_id = order.customer_id
                elif order.individual_id:
                    customer_id = order.individual_id                
                if order.customer_id and order.individual_id:
                    logger.error(f"get_order - Order {order_id} has both customer_id and individual_id set")
                    return {"status": False}
                if not supplier_id or not customer_id:
                    logger.error(f"get_order - Supplier ID or Customer ID of order {order_id} is incorrect - Supplier ID: {supplier_id}; Customer ID: {customer_id}")
                    return {"status": False}
                
                supplier = (await session.execute(select(Business).where(
                    Business.id == supplier_id
                ))).scalars().first()                
                if not supplier:
                    logger.error(f"get_order - Supplier of order {order_id} not found")
                    return {"status": False}
                
                customer = (await session.execute(select(Business).where(
                    Business.id == customer_id                    
                ))).scalars().first()                
                if not customer:
                    logger.error(f"get_order - Customer of order {order_id} not found")
                    return {"status": False}
                
                business_ids = [supplier_id, customer_id]
                
                order_items_query = select(OrderItem).where(OrderItem.order_id == order_id)
                order_items_result = await session.execute(order_items_query)
                order_items = order_items_result.scalars().all()

                business_names_native = (await session.execute(
                    select(Business.id, Business.name, Business.avatar_name).where(Business.id.in_(business_ids))
                )).mappings().all()

                business_names_local = (await session.execute(
                    select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                    .where(BusinessTranslation.business_id.in_(business_ids))
                )).mappings().all()

                all_businesses = {}
                for row in business_names_native:
                    all_businesses[row['id']] = {"native": row['name'], "avatar": row['avatar_name']}
                
                for row in business_names_local:
                    all_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']

                order_dict = order.to_dict()
                order_dict["items"] = []                
                order_dict["supplier_business"] = all_businesses.get(supplier_id, {})
                order_dict["customer_business"] = all_businesses.get(customer_id, {})

                current_time_unix = int(datetime.now(timezone.utc).timestamp())
                cutoff_time = current_time_unix - ORDER_ARCHIVED_STATE_TIME
                order_dict["rate_cutoff_date"] = None
                if order.last_update >= cutoff_time or order.status in ORDER_OPENED_STATUSES:
                    order_dict["archived"] = False
                    if order.status == ORDER_STATUS_SUCCESS:
                        order_dict["rate_cutoff_date"] = order.last_update + ORDER_ARCHIVED_STATE_TIME
                else:
                    order_dict["archived"] = True

                for order_item in order_items:
                    item_dict = order_item.to_dict()
                    order_dict["items"].append(item_dict)

                return {"status": True, "order_dict": order_dict}

            except Exception as e:
                logger.exception(f"get_order - MAIN EXCEPTION: {e}")                
                await put_critical_error_into_db("get_order", "main exception error", str(e), {"order_id": order_id})
                return {"status": False}


async def get_business_opened_orders_ids(business_id: int) -> dict:
    async with async_session() as session:
        try:            
            order_ids_query = select(Order.id).where(
                or_(
                    Order.supplier_id == business_id,
                    Order.customer_id == business_id,
                    Order.individual_id == business_id
                ),
                Order.status.in_(ORDER_OPENED_STATUSES),
                Order.deleted.is_(False)
            )
            order_ids_result = await session.execute(order_ids_query)
            order_ids = order_ids_result.scalars().all()

            return {"status": True, "order_ids": order_ids}

        except Exception as e:
            logger.exception(f"get_business_opened_orders_ids - MAIN EXCEPTION: {e}")                
            await put_critical_error_into_db(
                "get_business_opened_orders_ids",
                "main exception error",
                str(e),
                {"business_id": business_id}
            )
            return {"status": False}
        

async def get_business_opened_and_just_closed_orders_ids(business_id: int) -> dict:
    async with async_session() as session:
        try:
            current_time_unix = int(datetime.now(timezone.utc).timestamp())
            cutoff_time = current_time_unix - ORDER_ARCHIVED_STATE_TIME
            order_ids_query = select(Order.id).where(
                or_(
                    Order.supplier_id == business_id,
                    Order.customer_id == business_id,
                    Order.individual_id == business_id
                ),
                or_(Order.last_update >= cutoff_time, Order.status.in_(ORDER_OPENED_STATUSES)),                
                Order.deleted.is_(False)
            )
            order_ids_result = await session.execute(order_ids_query)
            order_ids = order_ids_result.scalars().all()

            return {"status": True, "order_ids": order_ids}

        except Exception as e:
            logger.exception(f"get_business_opened_and_just_closed_orders_ids - MAIN EXCEPTION: {e}")                
            await put_critical_error_into_db(
                "get_business_opened_and_just_closed_orders_ids",
                "main exception error",
                str(e),
                {"business_id": business_id}
            )
            return {"status": False}
        

async def do_order_action(user_id: int, business_id: int, order_id: int, action: str) -> dict:
    async with async_session() as session:
        try:
            async with session.begin():                
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True))
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db("do_order_action", "user not found or not active", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False}

                if not isinstance(action, str) or action not in ALL_ORDER_ACTIONS_POSSIBLE:
                    await put_critical_error_into_db("do_order_action", "incorrect order action", f"Incorrect order action - Order ID: {order_id}; Action: {action}", {"user_id": user_id})
                    return {"status": False}                
                                
                order_query = select(Order).where(Order.id == order_id, Order.deleted.is_(False)).with_for_update()
                order_result = await session.execute(order_query)
                order = order_result.scalars().first()                

                if not order:
                    logger.error(f"Order {order_id} not found", user_id=user_id)
                    return {"status": False}
                
                if not (order.supplier_id == business_id or order.customer_id == business_id or order.individual_id == business_id):
                    logger.error(f"Business {business_id} is not in order {order_id}", user_id=user_id)
                    return {"status": False}
                
                business_ids = []
                if order.supplier_id:
                    business_ids.append(order.supplier_id)
                if order.customer_id:
                    business_ids.append(order.customer_id)
                if order.individual_id:
                    business_ids.append(order.individual_id)

                if len(business_ids) != 2:
                    logger.error(f"Order {order_id} has incorrect number of parties", user_id=user_id)
                    return {"status": False}
                
                businesses_query = select(Business).where(Business.id.in_(business_ids), Business.active.is_(True), Business.deleted.is_(False))
                businesses_result = await session.execute(businesses_query)
                businesses = businesses_result.scalars().all()

                if len(businesses) != 2:
                    logger.error(f"Cannot to get both businneses for order {order_id} from database", user_id=user_id)
                    return {"status": False}
                                
                supplier = None
                customer = None
                business_role = None

                permission_error = False

                if businesses[0].id == business_id:
                    if businesses[0].owner_id != user_id and user_id not in businesses[0].staff:
                        permission_error = True
                    if businesses[0].business_type == SUPPLIER:
                        supplier = businesses[0]                        
                        business_role = SUPPLIER_ROLE
                        customer = businesses[1]
                    else:
                        customer = businesses[0]
                        business_role = CUSTOMER_ROLE
                        supplier = businesses[1]
                elif businesses[1].id == business_id:
                    if businesses[1].owner_id != user_id and user_id not in businesses[1].staff:
                        permission_error = True
                    if businesses[1].business_type == SUPPLIER:
                        supplier = businesses[1]
                        business_role = SUPPLIER_ROLE
                        customer = businesses[0]
                    else:
                        customer = businesses[1]
                        business_role = CUSTOMER_ROLE
                        supplier = businesses[0]
                else:
                    logger.error(f"Very strange and almost impossible situation", user_id=user_id)
                    return {"status": False}
                                                    
                if not business_role:
                    logger.error(f"Incorrect type of business - Business ID: {business_id};", user_id=user_id)
                    return {"status": False}
                
                if permission_error:
                    logger.error(f"Permission error - User ID: {user_id}; Business ID: {business_id};", user_id=user_id)
                    return {"status": False}
                
                actions_for_this_role = ORDER_ACTIONS_AVAILABLE.get(business_role, {})
                action_for_this_status = actions_for_this_role.get(order.status, [])
                next_status = None
                for action_dict in action_for_this_status:
                    if isinstance(action_dict, dict):
                        status = action_dict.get(action, None)
                        if status:
                            next_status = status
                
                if not next_status or next_status not in ALL_ORDER_TYPES:
                    logger.error(f"Order {order_id} status update is impossible - Current status: {order.status}; Action: {action}; next status: {next_status}", user_id=user_id)
                    return {"status": False}
                                    
                supplier_team = [supplier.owner_id] + supplier.staff
                customer_team = [customer.owner_id] + customer.staff                
                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                note_for_timeline = {
                    "date": current_time_unix,
                    "user_id": user_id,
                    "business_id": business_id,
                    "action": action,
                    "order_status_prev": order.status,
                    "order_status_next": next_status
                }                

                order.status = next_status
                order.last_update = current_time_unix
                if not isinstance(order.update_timeline, dict):
                    order.update_timeline = {}
                order.update_timeline[f"{current_time_unix}"] = note_for_timeline
                flag_modified(order, "update_timeline")
                    
                return {"status": True, "supplier_team": supplier_team, "customer_team": customer_team}

        except Exception as e:
            logger.exception(f"do_order_action - MAIN EXCEPTION ERROR: {e}") 
            await put_critical_error_into_db("do_order_action", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def rate_order(user_id: int, business_id: int, rating_data: dict) -> dict:    
    async with async_session() as session:
        try:
            async with session.begin():
                try:
                    validated_rating = OrderRating(**rating_data)
                except ValidationError as e:
                    logger.error(f"rate_order - Validation error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True))
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("rate_order", "user not found or not active", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False}
                
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    await put_critical_error_into_db("rate_order", "business not found or not active", f"Business {business_id} not found or not active", {"user_id": user_id})
                    return {"status": False}
                
                order_id = validated_rating.order_id
                business_role = validated_rating.business_role
                order_rate = validated_rating.order_rate
                order_review = validated_rating.order_review
                items_rate_raw = validated_rating.items_rate
                items_review_raw = validated_rating.items_review

                items_rate = {}
                items_review = {}

                for raw_key, value in items_rate_raw.items():
                    try:
                        key = int(raw_key)
                    except:
                        key = None 
                    if isinstance(key, int) and key > 0:
                        items_rate[key] = value
                        items_review[key] = items_review_raw.get(raw_key, "")                        

                order_query = select(Order).where(Order.id == order_id, Order.deleted.is_(False)).with_for_update()
                order_result = await session.execute(order_query)
                order = order_result.scalars().first()

                if not order:
                    logger.error(f"Order {order_id} not found", user_id=user_id)
                    return {"status": False}

                rated_business_id = None
                supplier_team = None
                customer_team = None
                permission_error = False
                already_rated = False
                if business_role == SUPPLIER_ROLE:
                    if order.rated_supplier:
                        already_rated = True
                    if order.customer_id:
                        rated_business_id = order.customer_id
                    if order.individual_id:
                        rated_business_id = order.individual_id
                    supplier_team = [business.owner_id] + business.staff
                    if user_id not in supplier_team:
                        permission_error = True
                else:
                    if order.rated_customer:
                        already_rated = True
                    if order.supplier_id:
                        rated_business_id = order.supplier_id
                    customer_team = [business.owner_id] + business.staff
                    if user_id not in customer_team:
                        permission_error = True
                if not rated_business_id:
                    await put_critical_error_into_db("rate_order", "rated business is not determinated", f"Rated business is not determinated: {rated_business_id}", {"user_id": user_id})
                    return {"status": False}
                if permission_error:
                    logger.error(f"Permission error - User ID: {user_id}; Business ID: {business_id};", user_id=user_id)
                    return {"status": False}            
                if already_rated:
                    logger.error(f"Rate error - Order {order_id} is already rated by {business_role};", user_id=user_id)
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())
                comment = ""
                if order_review:
                    comment = order_review
                                
                new_order_review = ReviewBusiness(
                    date = current_time_unix,
                    order_id = order_id,
                    business_id = rated_business_id,
                    author_user_id = user_id,
                    author_business_id = business_id,
                    comment = comment,                    
                    rate = order_rate
                )
                session.add(new_order_review)                

                rated_items_ids = []
                for key, value in items_rate.items():                    
                    if key not in rated_items_ids and value:
                        rated_items_ids.append(key)

                list_of_items_rating_data = []
                if rated_items_ids:
                    items_rated_already_ids = (
                        await session.execute(select(OrderItem.product_id).where(OrderItem.order_id == order_id, OrderItem.rated.is_(True)))).scalars().all()
                    for item_id in rated_items_ids:
                        item_data = {
                            "banned_by_admin": False,
                            "ban_reason": "",
                            "date": current_time_unix,
                            "product_id": item_id,
                            "order_id": order_id,
                            "business_id": rated_business_id,
                            "author_user_id": user_id,
                            "author_business_id": business_id,
                            "comment": items_review.get(item_id, ""),
                            "reply": "",
                            "rate": items_rate.get(item_id, None)
                        }
                        if item_data["rate"] and item_data["product_id"] not in items_rated_already_ids:
                            list_of_items_rating_data.append(item_data)

                    if list_of_items_rating_data:
                        await session.execute(insert(ReviewProduct), list_of_items_rating_data)
                        await session.execute(update(OrderItem).where(OrderItem.order_id == order.id).values(rated=True)
)
                
                if business_role == SUPPLIER_ROLE:
                    order.rated_supplier = True
                elif business_role == CUSTOMER_ROLE:
                    order.rated_customer = True

                return {"status": True, "supplier_team": supplier_team, "customer_team": customer_team}

        except Exception as e:
            logger.exception(f"rate_order - MAIN EXCEPTION ERROR: {e}") 
            await put_critical_error_into_db("rate_order", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def get_archive_business_orders_bundle(user_id: int, business_id: int, bundle: int | None = None) -> dict:
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_archive_business_orders_bundle", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            
            if business_id != user.active_business_id:
                logger.error(f"get_archive_business_orders_bundle - business {business_id} is not active business of user {user_id}", user_id=user_id)
                return {"status": False}
            
            business = (
                await session.execute(
                    select(Business).where(
                        Business.id == business_id,
                        Business.active.is_(True),
                        Business.deleted.is_(False)                        
                    )
                )
            ).scalars().first()
            if not business:
                logger.error(f"get_archive_business_orders_bundle - business {business_id} not found", user_id=user_id)
                return {"status": False}                        
            
            if not bundle:
                bundle = 1

            default_filter = BUSINESS_ORDERS_DEFAULT_FILTER_SETTINGS
            user_settings = getattr(user, "settings", {})
            user_filter_orders = user_settings.get("filters_business_orders", {})
            user_business_filter_orders = user_filter_orders.get(str(business_id), {})            

            f_orders_hide_order_statuses = user_business_filter_orders.get("orders_hide_order_statuses", default_filter.get("orders_hide_order_statuses"))
            f_orders_bundle_size = user_business_filter_orders.get("orders_bundle_size", default_filter.get("orders_bundle_size"))
            f_orders_date_diapason = user_business_filter_orders.get("orders_date_diapason", default_filter.get("orders_date_diapason"))
            f_orders_date_diapason_start = user_business_filter_orders.get("orders_date_diapason_start", default_filter.get("orders_date_diapason_start"))
            f_orders_date_diapason_end = user_business_filter_orders.get("orders_date_diapason_end", default_filter.get("orders_date_diapason_end"))

            business_type = business.business_type
            current_time_unix = int(datetime.now(timezone.utc).timestamp())
            cutoff_time = current_time_unix - ORDER_ARCHIVED_STATE_TIME

            offset = (bundle - 1) * f_orders_bundle_size

            query_filters = []

            if business_type == SUPPLIER:
                query_filters.append(Order.supplier_id == business_id)
            elif business_type == CUSTOMER:
                query_filters.append(Order.customer_id == business_id)
            elif business_type == INDIVIDUAL:
                query_filters.append(Order.individual_id == business_id)
            
            query_filters.append(and_(Order.last_update < cutoff_time, Order.status.in_(ORDER_CLOSED_STATUSES)))

            if f_orders_hide_order_statuses:
                query_filters.append(Order.status.notin_(f_orders_hide_order_statuses))

            if f_orders_date_diapason:
                query_filters.append(and_(Order.delivery_date >= f_orders_date_diapason_start, Order.delivery_date <= f_orders_date_diapason_end))

            count_query = select(func.count()).select_from(Order).where(*query_filters)
            total_orders = await session.scalar(count_query) or 0

            orders_query = select(Order).where(*query_filters).order_by(Order.id.desc()).limit(f_orders_bundle_size).offset(offset)            
            orders_result = await session.execute(orders_query)
            orders = orders_result.scalars().all()

            order_ids = []
            orders_dict = {}

            business_ids = set()

            if not orders:
                logger.info(f"get_business_orders - Actual orders not found...")
                return {
                    "status": True,
                    "archive_orders_dict": orders_dict,
                    "total_count": total_orders
                }
                
            for order in orders:
                order_ids.append(order.id)
                if order.supplier_id:
                    business_ids.add(order.supplier_id)
                if order.customer_id:
                    business_ids.add(order.customer_id)
                if order.individual_id:
                    business_ids.add(order.individual_id)
                
            business_ids = list(business_ids)
                
            order_items_query = select(OrderItem).where(OrderItem.order_id.in_(order_ids))
            order_items_result = await session.execute(order_items_query)
            order_items = order_items_result.scalars().all()

            business_names_native = (await session.execute(
                select(Business.id, Business.name, Business.avatar_name).where(Business.id.in_(business_ids))
            )).mappings().all()

            business_names_local = (await session.execute(
                select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                .where(BusinessTranslation.business_id.in_(business_ids))
            )).mappings().all()

            all_businesses = {}
            for row in business_names_native:
                all_businesses[row['id']] = {"native": row['name'], "avatar": row['avatar_name']}
                
            for row in business_names_local:
                all_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']

            for order in orders:
                key = f"{order.id}"
                orders_dict[key] = order.to_dict()
                orders_dict[key]["items"] = []
                supplier_key = order.supplier_id
                customer_key = None
                customer_key = order.customer_id or order.individual_id
                orders_dict[key]["supplier_business"] = all_businesses.get(supplier_key, {})
                orders_dict[key]["customer_business"] = all_businesses.get(customer_key, {})
                orders_dict[key]["archived"] = True
                if order.status == ORDER_STATUS_SUCCESS:
                    orders_dict[key]["rate_cutoff_date"] = order.last_update + ORDER_ARCHIVED_STATE_TIME
                else:
                    orders_dict[key]["rate_cutoff_date"] = None
                    

            for order_item in order_items:
                item_dict = order_item.to_dict()
                orders_dict[f"{order_item.order_id}"]["items"].append(item_dict)

            return {"status": True, "archive_orders_dict": orders_dict, "total_count": total_orders}

        except Exception as e:
            logger.exception(f"get_archive_business_orders_bundle - MAIN EXCEPTION: {e}")                
            await put_critical_error_into_db(
                "get_archive_business_orders_bundle",
                "main exception error",
                str(e),
                {
                    "user_id": user_id,
                    "business_id": business_id,
                    "bundle": bundle
                }
            )
            return {"status": False}
        

async def check_permission_for_generate_excel_file(user_id: int, business_id: int, order_ids: list) -> dict:
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("check_permission_for_generate_excel_file", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            
            if business_id != user.active_business_id:
                logger.error(f"check_permission_for_generate_excel_file - business {business_id} is not active business of user {user_id}", user_id=user_id)
                return {"status": False}
            
            business = (
                await session.execute(
                    select(Business).where(
                        Business.id == business_id,
                        Business.active.is_(True),
                        Business.deleted.is_(False)                        
                    )
                )
            ).scalars().first()

            if not business:
                logger.error(f"check_permission_for_generate_excel_file - business {business_id} not found", user_id=user_id)
                return {"status": False}
            
            if business.owner_id != user_id and user not in business.staff:
                logger.error(f"check_permission_for_generate_excel_file - user {user_id} has not permission for orders of business {business_id}", user_id=user_id)
                return {"status": False}
            
            if not isinstance(order_ids, list):
                logger.error(f"check_permission_for_generate_excel_file - order IDs is not list: {order_ids}", user_id=user_id)
                return {"status": False}
            
            unique_order_ids = list(set(order_ids))
            orders_number = len(unique_order_ids)
            
            business_type = business.business_type
            query_filters = []

            if business_type == SUPPLIER:
                query_filters.append(Order.supplier_id == business_id)
            elif business_type == CUSTOMER:
                query_filters.append(Order.customer_id == business_id)
            elif business_type == INDIVIDUAL:
                query_filters.append(Order.individual_id == business_id)
            
            query_filters.append(Order.id.in_(unique_order_ids))

            orders_query = select(Order.id).where(*query_filters)
            orders_result = await session.execute(orders_query)
            orders = orders_result.scalars().all()

            if len(orders) < orders_number:
                logger.error(f"check_permission_for_generate_excel_file - cannot find all orders in database - incoming orderslist: {order_ids}; found orders: {orders}", user_id=user_id)
                return {"status": False}
                        
            return {"status": True, "user_tg_id": user.tg_id}

        except Exception as e:
            logger.exception(f"check_permission_for_generate_excel_file - MAIN EXCEPTION: {e}")                
            await put_critical_error_into_db(
                "check_permission_for_generate_excel_file",
                "main exception error",
                str(e),
                {
                    "user_id": user_id,
                    "business_id": business_id,
                    "order_ids": order_ids
                }
            )
            return {"status": False}