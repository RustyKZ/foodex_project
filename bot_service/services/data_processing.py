
from models.busineses import Business, BusinessTranslation
from models.app_users import AppUser
from models.products import Product, ProductTranslation
from models.orders import Order, OrderItem

from sqlalchemy import insert, update, or_, and_, func
from sqlalchemy.future import select

from .error import put_critical_error_into_db
from .user_action_log import add_user_action_log

from datetime import datetime, timezone, timedelta, UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from io import BytesIO
from openpyxl import Workbook

from constants.business_types import SUPPLIER, CUSTOMER, INDIVIDUAL, SUPPLIER_ROLE, CUSTOMER_ROLE
from constants.default_settings import DEFAULT_LANGUAGE, DEFAULT_TIMEZONE, MAX_ORDER_LIST_EXCEL_FILE_ITEMS
from constants.log_entitys import *

from system_i18n.excel_files import TITLE_PAGE_ORDERS, PAGE_ORDERS_FIRST_LINE, PAGE_ORDERS_HEADERS_ROLE_SUPPLIER, PAGE_ORDERS_HEADERS_ROLE_CUSTOMER
from system_i18n.measures import MEASURE_SHORT_DICT
from system_i18n.business_types import BUSINESS_TYPES
from system_i18n.order_statuses import ORDER_STATUSES_DICT

async def get_orders_excel_file(user_id: int, business_id: int, order_ids: list) -> dict:
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_orders_excel_file", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            
            language = user.language
            if not language:
                language = DEFAULT_LANGUAGE
            
            if business_id != user.active_business_id:
                logger.error(f"get_orders_excel_file - business {business_id} is not active business of user {user_id}", user_id=user_id)
                return {"status": False, "language": language}
            
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
                logger.error(f"get_orders_excel_file - business {business_id} not found", user_id=user_id)
                return {"status": False, "language": language}
            
            if business.owner_id != user_id and user not in business.staff:
                logger.error(f"get_orders_excel_file - user {user_id} has not permission for orders of business {business_id}", user_id=user_id)
                return {"status": False, "language": language}
            
            if not isinstance(order_ids, list):
                logger.error(f"get_orders_excel_file - order IDs is not list: {order_ids}", user_id=user_id)
                return {"status": False, "language": language}

            business_type = business.business_type
            query_filters = []
            business_role = None

            if business_type == SUPPLIER:
                query_filters.append(Order.supplier_id == business_id)
                business_role = SUPPLIER_ROLE
            elif business_type == CUSTOMER:
                query_filters.append(Order.customer_id == business_id)
                business_role = CUSTOMER_ROLE
            elif business_type == INDIVIDUAL:
                query_filters.append(Order.individual_id == business_id)
                business_role = CUSTOMER_ROLE
            
            query_filters.append(Order.id.in_(order_ids))

            orders_query = select(Order).where(*query_filters).order_by(Order.id.desc())
            orders_result = await session.execute(orders_query)
            orders = orders_result.scalars().all()

            order_ids = []
            orders_dict = {}

            orders_file = None

            business_ids = set()            

            if not orders:
                logger.info(f"get_orders_excel_file - Actual orders not found...")
                return {
                    "status": True,
                    "orders_file": orders_file,                    
                    "language": language,
                    "empty_order_list": True,
                    "too_long_order_list": False
                }
            
            if len(orders) > MAX_ORDER_LIST_EXCEL_FILE_ITEMS:
                logger.info(f"get_orders_excel_file - Order list limit exceeded - Orders: {len(orders)}; Limit: {MAX_ORDER_LIST_EXCEL_FILE_ITEMS}")
                return {
                    "status": True,
                    "orders_file": orders_file,                    
                    "language": language,
                    "empty_order_list": True,
                    "too_long_order_list": False
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
                select(Business.id, Business.name, Business.address).where(Business.id.in_(business_ids))
            )).mappings().all()

            business_names_local = (await session.execute(
                select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                .where(BusinessTranslation.business_id.in_(business_ids))
            )).mappings().all()

            all_businesses = {}
            for row in business_names_native:
                all_businesses[row['id']] = {"native": row['name'], "address": row['address']}
                
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

            product_ids = []

            for order_item in order_items:
                item_dict = order_item.to_dict()
                orders_dict[f"{order_item.order_id}"]["items"].append(item_dict)
                product_ids.append(order_item.product_id)

            product_names_native = (await session.execute(
                select(Product.id, Product.name).where(Product.id.in_(product_ids))
            )).mappings().all()

            product_names_local = (await session.execute(
                select(ProductTranslation.product_id, ProductTranslation.name, ProductTranslation.language)
                .where(ProductTranslation.product_id.in_(product_ids))
            )).mappings().all()

            all_products = {}
            for row in product_names_native:
                all_products[row['id']] = {"native": row['name']}
                
            for row in product_names_local:
                all_products.setdefault(row['product_id'], {"native": None})[row['language']] = row['name']            

            business_timezone = business.timezone
            try:
                tz = ZoneInfo(business_timezone)
            except ZoneInfoNotFoundError:
                tz = ZoneInfo(DEFAULT_TIMEZONE)            

            wb = Workbook()
            ws = wb.active
            ws.title = TITLE_PAGE_ORDERS.get(language, TITLE_PAGE_ORDERS.get(DEFAULT_LANGUAGE))

            business_name_dict = all_businesses.get(business_id, None)
            business_name = None
            if isinstance(business_name_dict, dict):
                business_name = business_name_dict.get(language, business_name_dict.get("native"))
            if not business_name:
                business_name = business.name

            business_type_str_dict = BUSINESS_TYPES[business.business_type]
            business_type_str = business_type_str_dict.get(language, business_type_str_dict.get(DEFAULT_LANGUAGE))

            first_line = [f"{PAGE_ORDERS_FIRST_LINE.get(language, PAGE_ORDERS_FIRST_LINE.get(DEFAULT_LANGUAGE))}{business_name} ({business_type_str})"]
            ws.append(first_line)
            
            if business_role == SUPPLIER_ROLE:
                headers = PAGE_ORDERS_HEADERS_ROLE_SUPPLIER.get(language, PAGE_ORDERS_HEADERS_ROLE_SUPPLIER.get(DEFAULT_LANGUAGE))
            else:
                headers = PAGE_ORDERS_HEADERS_ROLE_CUSTOMER.get(language, PAGE_ORDERS_HEADERS_ROLE_CUSTOMER.get(DEFAULT_LANGUAGE))                
            ws.append(headers)

            for order in orders_dict.values():    
                delivery_timestamp = order.get("delivery_date")
                delivery_date = ""    
                if delivery_timestamp:
                    delivery_date = (
                        datetime
                        .fromtimestamp(
                            delivery_timestamp,
                            tz=tz
                        )
                        .strftime("%Y-%m-%d")
                    )

                items = order.get("items", [])
                items_parts = []
                for item in items:
                    product_id = item.get("product_id")
                    amount = item.get("amount")
                    measure_code = item.get("measure_code")
                    measure_local = (MEASURE_SHORT_DICT.get(measure_code, {}).get(language, measure_code))
                    item_name_snapshot = (item.get("product_snapshot", {}).get("name"))
                    item_dict = all_products.get(product_id, {})
                    item_name = item_dict.get(language, item_dict.get("native", item_name_snapshot))
                    item_str = f"{item_name} - {amount} {measure_local}"
                    items_parts.append(item_str)

                items_str = "; ".join(items_parts)

                if business_role == SUPPLIER_ROLE:
                    counter_agent = order.get("customer_business", {})
                else:
                    counter_agent = order.get("supplier_business", {})
                counter_agent_name = counter_agent.get(language, counter_agent.get("native"))
                counter_agent_address = counter_agent.get("address", "")
                status = order.get("status")
                status_str_dict = ORDER_STATUSES_DICT.get(status, {})
                status_str = status_str_dict.get(language, status_str_dict.get(DEFAULT_LANGUAGE))
                if not status_str:
                    status_str = status
                ws.append([
                    order.get("id"),
                    order.get("name"),
                    status_str,
                    delivery_date,                    
                    counter_agent_name,
                    counter_agent_address,
                    items_str
                ])
            
            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            date_str = datetime.now(UTC).strftime("%Y-%m-%d %H%M%S")
            filename = f"orders {date_str}.xlsx"

            log_data = {
                "user_id": user_id,
                "action_type": CREATE_EXCEL_ORDER_LIST,
                "entity_type": BUSINESS,
                "entity_id": business_id,
                "extra_data": {
                    "user_id": user_id,
                    "business_id": business_id,
                    "order_ids": order_ids
                }
            }
            await add_user_action_log(log_data)

            
            return {
                "status": True, 
                "orders_file": buffer, 
                "filename": filename, 
                "language": language,
                "empty_order_list": False,
                "too_long_order_list": False
            }
        

        except Exception as e:
            logger.exception(f"get_orders_excel_file - MAIN EXCEPTION: {e}")                
            await put_critical_error_into_db(
                "get_orders_excel_file",
                "main exception error",
                str(e),
                {
                    "user_id": user_id,
                    "business_id": business_id,
                    "order_ids": order_ids
                }
            )
            return {"status": False}