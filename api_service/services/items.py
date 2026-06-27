from models.products import Product, Category, Measure, ProductTranslation
from models.busineses import Business, BusinessTranslation
from models.app_users import AppUser
from models.finances import TariffPlan
from models.reviews import ReviewProduct

from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, and_

from fastapi import UploadFile, Query
from decimal import Decimal, InvalidOperation

from .images import save_uploaded_jpeg_product

from config import get_settings
settings = get_settings()

from numbers import Number

from session_config import async_session

from constants.log_entitys import CREATE, UPDATE, DELETE, BUSINESS, PRODUCT
from constants.limit_settings import DEFAULT_PRODUCT_CATALOG_LIMIT
from constants.default import (
    UNCATEGORIZED, CUSTOMER_PRODUCT_CATALOG_FILTERS, CUSTOMER_PRODUCT_CATALOG_BUNDLE, DEFAULT_SEARCH_RADIUS_KM, MINIMAL_SEARCH_RADIUS_KM, 
    INDIVIDUAL_PRODUCT_CATALOG_BUNDLE, INDIVIDUAL_PRODUCT_CATALOG_FILTERS
)
from constants.rate_system import MAX_RATE, MIN_RATE
from constants.business_types import SUPPLIER, CUSTOMER, INDIVIDUAL
from constants.geodata import MAX_LATITUDE, MIN_LATITUDE, MAX_LONGITUDE, MIN_LONGITUDE, AVERAGE_KM_PER_DEGREE_LAT, EQUATOR_KM_PER_DEGREE_LON
from constants.tariff import TARIFF_FREE

from datetime import datetime, timezone, timedelta

from collections import defaultdict

import math

from constants.languages import get_languages

from rediska.order_data import get_product_ordered_quantity_by_id
from constants.redis_vars import PRODUCT_ORDERED

from .error import put_critical_error_into_db
from logger_config import get_logger
logger = get_logger(__name__)

async def get_category_list() -> list:
    async with async_session() as session:
        try:
            query = select(Category).filter(Category.active == True)
            result = await session.execute(query)
            categories = result.scalars().all()            
            category_list = []
            for c in categories:
                category_list.append(c.to_dict())
            return category_list
        except SQLAlchemyError as e:
            logger.error(f"get_category_list - Exception SQLAlchemyError: {e}")
            return []
        except Exception as e:
            logger.error(f"get_category_list - Exception SQLAlchemyError: {e}")
            return []
        

async def get_measures_list() -> list:
    async with async_session() as session:
        try:
            query = select(Measure).filter(Measure.active == True)
            result = await session.execute(query)
            measures = result.scalars().all()            
            measures_list = []
            for m in measures:
                measures_list.append(m.to_dict())
            return measures_list
        except SQLAlchemyError as e:
            logger.error(f"get_measures_list - Exception SQLAlchemyError: {e}")
            return []
        except Exception as e:
            logger.error(f"get_measures_list - Exception SQLAlchemyError: {e}")
            return []
        

async def get_start_app_supplier_all_products_request(user_id) -> dict:
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_start_app_supplier_all_products_request", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False }

            user_common_business_list = user.business_list
            if not isinstance(user_common_business_list, list):
                user_common_business_list = []
            if user.active_business_id != 0 and user.active_business_id not in user_common_business_list:
                user_common_business_list.append(user.active_business_id)
            
            if user.outcoming_employer_business_id != 0 and user.outcoming_employer_business_id != user.active_business_id:                
                employer_business = (await session.execute(select(Business).where(Business.id == user.outcoming_employer_business_id, Business.deleted.is_(False)))).scalars().first()
                if employer_business:
                    if user_id in employer_business.staff and employer_business.id not in user_common_business_list:
                        user_common_business_list.append(employer_business.id)

            if not user_common_business_list:
                products = []
            else:
                products = (await session.execute(
                    select(Product).where(Product.business_id.in_(user_common_business_list), Product.deleted.is_(False))
                )).scalars().all()            

            business_names_native = (await session.execute(
                select(Business.id, Business.name, Business.currency).where(Business.id.in_(user_common_business_list))
            )).mappings().all()  # Возвращает [{'id': ..., 'name': ...}]

            business_names_local = (await session.execute(
                select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                .where(BusinessTranslation.business_id.in_(user_common_business_list))
            )).mappings().all()  # Возвращает [{'business_id': ..., 'name': ..., 'language': ...}]

            all_businesses = {}

            # Native названия
            for row in business_names_native:
                all_businesses[row['id']] = {"native": row['name'], "currency": row['currency']}                

            # Переводы
            for row in business_names_local:
                all_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']
            
            product_ids = []

            products_dict = {}
            for product in products:
                product_ids.append(product.id)
                key = str(product.id)
                products_dict[key] = product.to_dict()
                products_dict[key]["translation"] = {}
                products_dict[key]["business_names"] = all_businesses[product.business_id] or {}
                products_dict[key]["rating"] = 0
                products_dict[key]["rating_count"] = 0
                products_dict[key]["currency"] = all_businesses[product.business_id]["currency"]                

            if product_ids:
                translations = (await session.execute(
                        select(ProductTranslation).where(ProductTranslation.product_id.in_(product_ids))
                    )).scalars().all()                
                if translations:
                    for t in translations:
                        products_dict[str(t.product_id)]["translation"][t.language] = t.to_dict()

                ratings = (await session.execute(
                    select(
                        ReviewProduct.product_id,
                        func.avg(ReviewProduct.rate).label('average'),  # Среднее
                        func.count(ReviewProduct.rate).label('count')   # Количество
                    ).where(
                        ReviewProduct.product_id.in_(product_ids),
                        ReviewProduct.banned_by_admin.is_(False),
                        ReviewProduct.rate != 0,
                        ReviewProduct.rate.between(MIN_RATE, MAX_RATE)  # Фильтр в SQL
                    ).group_by(ReviewProduct.product_id)
                )).all()  # Возвращает список кортежей: [(product_id, avg, count), ...]

                for row in ratings:
                    product_id, average, count = row  # Распаковка кортежа
                    if count > 0:  # На всякий случай, хотя rate != 0 гарантирует
                        str_key = str(product_id)
                        if str_key in products_dict:
                            products_dict[str_key]["rating"] = float(round(average or 0, 1))  # average может быть None, если нет
                            products_dict[str_key]["rating_count"] = count
                
            return { "status": True, "products_dict": products_dict }
        except Exception as e:
                logger.exception("get_start_app_supplier_all_products_request - MAIN EXCEPTION ERROR")
                await put_critical_error_into_db( 
                    "get_start_app_supplier_all_products_request", "main exception error", 
                    f"Error text: {str(e)}", 
                    {"user_id": user_id}
                )
                return { "status": False }
        

async def get_start_app_customer_products_request(user_id) -> dict:
    result = await get_customer_products_request_bundle(user_id, 1)
    return result


async def get_start_app_individual_products_request(user_id) -> dict:
    result = await get_individual_products_request_bundle(user_id, 1)
    return result
    

async def get_customer_products_request_bundle(user_id: int, bundle: int) -> dict:
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_customer_products_request_bundle", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            if not user.active_business_id:
                return {"status": False}
            business = (
                await session.execute(
                    select(Business).where(
                        Business.id == user.active_business_id,
                        Business.active.is_(True),
                        Business.deleted.is_(False),
                        Business.business_type == CUSTOMER
                    )
                )
            ).scalars().first()
            if not business:
                return {"status": False}                    
                    

            default_filter = CUSTOMER_PRODUCT_CATALOG_FILTERS
            user_settings = getattr(user, "settings", {})            
            user_all_filters = user_settings.get("filters_customer_catalog", {})
            user_filter = user_all_filters.get(str(business.id), {})            
            user_currency = business.currency

            
            local_business_ids_query = select(Business.id).where(                
                Business.active.is_(True),
                Business.deleted.is_(False),
                Business.business_type == SUPPLIER,
                Business.currency == user_currency
            )                

            local_business_ids_result = await session.execute(local_business_ids_query)
            local_business_ids = local_business_ids_result.scalars().all()
            if not local_business_ids:
                return {"status": True, "products_dict": {}, "total_count": 0}

            # Слияние для простоты (можно добавить для всех)
            filters_merged = {**default_filter, **user_filter}

            keyword = filters_merged.get("keyword", "")
            hide_without_address = filters_merged.get("hide_without_address", True)
            search_radius_km = filters_merged.get("search_radius_km", DEFAULT_SEARCH_RADIUS_KM)
            all_categories = filters_merged.get("all_categories", True)
            allowed_categories = filters_merged.get("allowed_categories", [])
            only_favorite_products = filters_merged.get("only_favorite_products", False)
            only_favorite_businesses = filters_merged.get("only_favorite_businesses", False)
            hide_without_price = filters_merged.get("hide_without_price", False)
            hide_without_photo = filters_merged.get("hide_without_photo", False)
            supplier_id = filters_merged.get("supplier_id", None)

            total = 0

            if not local_business_ids and not supplier_id:
                return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

            if not bundle or not isinstance(bundle, int) or bundle < 0:
                bundle_number = 1
            else:
                bundle_number = bundle
            bundle_size = CUSTOMER_PRODUCT_CATALOG_BUNDLE
            offset = (bundle_number - 1) * bundle_size

            query = select(Product).order_by(Product.id).limit(bundle_size).offset(offset)
            # Динамически добавляем условия в WHERE
            filters = [
                Product.active.is_(True), # Всегда
                Product.deleted.is_(False) # Всегда                
            ]           

            if supplier_id:
                filters.append(Product.business_id == supplier_id)
            else:
                filters.append(Product.business_id.in_(local_business_ids))

                if keyword:
                    # Один запрос: ID из натив + ID из переводов (с unique)
                    product_ids_query = (
                        select(Product.id)
                        .where(Product.active.is_(True), Product.deleted.is_(False), Product.name.ilike(f"%{keyword}%"))
                        .union(
                            select(ProductTranslation.product_id.label('id'))
                            .join(Product, Product.id == ProductTranslation.product_id)
                            .where(Product.active.is_(True), Product.deleted.is_(False), ProductTranslation.name.ilike(f"%{keyword}%"))
                        )
                    )
                    product_ids_result = await session.execute(product_ids_query)
                    product_ids = list(set(product_ids_result.scalars().all()))  # unique через set/list

                    if product_ids:
                        filters.append(Product.id.in_(product_ids))
                    else:
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

                if hide_without_address and business.geopoint:
                    allowance_km_radius = max(search_radius_km, MINIMAL_SEARCH_RADIUS_KM)
                    km_per_degree_lat = AVERAGE_KM_PER_DEGREE_LAT  # 111.2
                    km_per_degree_lon = EQUATOR_KM_PER_DEGREE_LON * math.cos(math.radians(float(business.latitude)))  # float для Decimal
                    lat_allowance_degree = Decimal(allowance_km_radius / km_per_degree_lat)
                    lon_allowance_degree = Decimal(allowance_km_radius / km_per_degree_lon)
                    min_target_latitude = business.latitude - lat_allowance_degree
                    max_target_latitude = business.latitude + lat_allowance_degree
                    min_target_longitude = business.longitude - lon_allowance_degree
                    max_target_longitude = business.longitude + lon_allowance_degree

                    # Простой clamp (лучше твоего deviation)
                    min_target_latitude = max(min_target_latitude, Decimal(MIN_LATITUDE))
                    max_target_latitude = min(max_target_latitude, Decimal(MAX_LATITUDE))
                    min_target_longitude = max(min_target_longitude, Decimal(MIN_LONGITUDE))
                    max_target_longitude = min(max_target_longitude, Decimal(MAX_LONGITUDE))

                    business_ids_query = select(Business.id).where(
                        Business.active.is_(True),
                        Business.deleted.is_(False),
                        Business.business_type == SUPPLIER,
                        Business.geopoint.is_(True),
                        Business.latitude.between(min_target_latitude, max_target_latitude),
                        Business.longitude.between(min_target_longitude, max_target_longitude)
                    )
                    business_ids_result = await session.execute(business_ids_query)
                    business_ids = business_ids_result.scalars().all()
                    if business_ids:
                        filters.append(Product.business_id.in_(business_ids))
                    else:
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

                if not all_categories and allowed_categories and isinstance(allowed_categories, list):
                    filters.append(Product.category_code.in_(allowed_categories))

                if only_favorite_businesses and isinstance(user.favorite_businesses, list):
                    if not user.favorite_businesses:
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}
                    else:
                        filters.append(Product.business_id.in_(user.favorite_businesses))  # Исправил id → business_id

                if only_favorite_products and isinstance(user.favorite_products, list):
                    if not user.favorite_products:
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}
                    else:
                        filters.append(Product.id.in_(user.favorite_products))

                if hide_without_price:
                    no_price = Decimal(0)
                    filters.append(Product.price > no_price)

                if hide_without_photo:
                    filters.append(Product.avatar_name != "")  # Исправил (предполагая str; или .isnot(None))

            if filters:
                query = query.where(and_(*filters))

            # Выполняем
            result = await session.execute(query)
            products = result.scalars().all()
            # Убрал if not products return False — лучше продолжить

            # Count для total
            count_query = select(func.count()).select_from(Product)
            if filters:
                count_query = count_query.where(and_(*filters))
            total = await session.scalar(count_query) or 0

            if not products:
                return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

            common_business_list = [p.business_id for p in products]  # Улучшил: list comp

            if supplier_id and supplier_id not in common_business_list:
                common_business_list.append(supplier_id)

            business_names_native = (await session.execute(
                select(Business.id, Business.name, Business.currency, Business.timezone, Business.schedule).where(Business.id.in_(common_business_list))
            )).mappings().all()

            business_names_local = (await session.execute(
                select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                .where(BusinessTranslation.business_id.in_(common_business_list))
            )).mappings().all()

            all_businesses = {}
            for row in business_names_native:
                all_businesses[row['id']] = {"native": row['name'], "currency": row['currency'], "timezone": row['timezone'], "schedule": row['schedule']}
                

            for row in business_names_local:
                all_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']

            one_supplier_info = None
            print(f"TEMP LOG 1 --------------------------------- {supplier_id}")
            if supplier_id:
                one_supplier_info = all_businesses.get(supplier_id, None)
                print(f"TEMP LOG 2 --------------------------------- {one_supplier_info}")

            product_ids = [product.id for product in products]

            products_dict = {}
            for product in products:
                key = str(product.id)
                products_dict[key] = product.to_dict()
                products_dict[key]["translation"] = {}
                products_dict[key]["business_names"] = all_businesses.get(product.business_id, {})
                products_dict[key]["rating"] = 0
                products_dict[key]["rating_count"] = 0
                products_dict[key]["currency"] = all_businesses[product.business_id]["currency"]
                products_dict[key]["timezone"] = all_businesses[product.business_id]["timezone"]
                products_dict[key]["schedule"] = all_businesses[product.business_id]["schedule"]

            if product_ids:
                translations = (await session.execute(
                    select(ProductTranslation).where(ProductTranslation.product_id.in_(product_ids))
                )).scalars().all()
                if translations:
                    for t in translations:
                        products_dict[str(t.product_id)]["translation"][t.language] = t.to_dict()

                ratings = (await session.execute(
                    select(
                        ReviewProduct.product_id,
                        func.avg(ReviewProduct.rate).label('average'),
                        func.count(ReviewProduct.rate).label('count')
                    ).where(
                        ReviewProduct.product_id.in_(product_ids),
                        ReviewProduct.banned_by_admin.is_(False),
                        ReviewProduct.rate != 0,
                        ReviewProduct.rate.between(MIN_RATE, MAX_RATE)
                    ).group_by(ReviewProduct.product_id)
                )).all()

                for row in ratings:
                    product_id, average, count = row
                    if count > 0:
                        str_key = str(product_id)
                        if str_key in products_dict:
                            products_dict[str_key]["rating"] = float(round(average or 0, 1))
                            products_dict[str_key]["rating_count"] = count

            return {"status": True, "products_dict": products_dict, "total_count": total, "one_supplier_info": one_supplier_info}

        except Exception as e:
            logger.exception("get_customer_products_request_bundle - MAIN EXCEPTION ERROR")
            await put_critical_error_into_db(
                "get_customer_products_request_bundle", "main exception error",
                f"Error text: {str(e)}",
                {"user_id": user_id, "bundle": bundle}
            )
            return {"status": False}


async def get_individual_products_request_bundle(user_id: int, bundle: int) -> dict:
    async with async_session() as session:        
        try:            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_individual_products_request_bundle", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            if not user.active_business_id or not user.individual_id or user.active_business_id != user.individual_id:
                return {"status": False}
            business = (
                await session.execute(
                    select(Business).where(
                        Business.id == user.active_business_id,
                        Business.active.is_(True),
                        Business.deleted.is_(False),
                        Business.business_type == INDIVIDUAL
                    )
                )
            ).scalars().first()
            if not business:
                return {"status": False}
            
            default_filter = INDIVIDUAL_PRODUCT_CATALOG_FILTERS
            user_settings = getattr(user, "settings", {})
            user_all_filters = user_settings.get("filters_individual_catalog", {})
            user_filter = user_all_filters.get(str(business.id), {})            
            user_currency = business.currency            
            
            local_business_ids_query = select(Business.id).where(                
                Business.active.is_(True),
                Business.deleted.is_(False),
                Business.business_type == SUPPLIER,
                Business.currency == user_currency
            )            
            
            local_business_ids_result = await session.execute(local_business_ids_query)
            local_business_ids = local_business_ids_result.scalars().all()            

            # Слияние для простоты (можно добавить для всех)
            filters_merged = {**default_filter, **user_filter}

            keyword = filters_merged.get("keyword", "")
            hide_without_address = filters_merged.get("hide_without_address", True)
            search_radius_km = filters_merged.get("search_radius_km", DEFAULT_SEARCH_RADIUS_KM)
            all_categories = filters_merged.get("all_categories", True)
            allowed_categories = filters_merged.get("allowed_categories", [])
            only_favorite_products = filters_merged.get("only_favorite_products", False)
            only_favorite_businesses = filters_merged.get("only_favorite_businesses", False)
            hide_without_price = filters_merged.get("hide_without_price", False)
            hide_without_photo = filters_merged.get("hide_without_photo", False)
            supplier_id = filters_merged.get("supplier_id", None)

            total = 0

            if not local_business_ids and not supplier_id:
                return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

            if not bundle or not isinstance(bundle, int) or bundle < 0:
                bundle_number = 1
            else:
                bundle_number = bundle
            bundle_size = INDIVIDUAL_PRODUCT_CATALOG_BUNDLE
            offset = (bundle_number - 1) * bundle_size

            query = select(Product).order_by(Product.id).limit(bundle_size).offset(offset)
            # Динамически добавляем условия в WHERE
            filters = [
                Product.active.is_(True), # Всегда
                Product.deleted.is_(False), # Всегда                
                Product.individual_customer.is_(True) # Всегда
            ]

            if supplier_id:
                filters.append(Product.business_id == supplier_id)
            else:
                filters.append(Product.business_id.in_(local_business_ids))
                if keyword:
                    # Один запрос: ID из натив + ID из переводов (с unique)
                    product_ids_query = (
                        select(Product.id)
                        .where(Product.active.is_(True), Product.deleted.is_(False), Product.name.ilike(f"%{keyword}%"))
                        .union(
                            select(ProductTranslation.product_id.label('id'))
                            .join(Product, Product.id == ProductTranslation.product_id)
                            .where(Product.active.is_(True), Product.deleted.is_(False), ProductTranslation.name.ilike(f"%{keyword}%"))
                        )
                    )
                    product_ids_result = await session.execute(product_ids_query)
                    product_ids = list(set(product_ids_result.scalars().all()))  # unique через set/list

                    if product_ids:
                        filters.append(Product.id.in_(product_ids))
                    else:                        
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

                if hide_without_address and business.geopoint:
                    allowance_km_radius = max(search_radius_km, MINIMAL_SEARCH_RADIUS_KM)
                    km_per_degree_lat = AVERAGE_KM_PER_DEGREE_LAT  # 111.2
                    km_per_degree_lon = EQUATOR_KM_PER_DEGREE_LON * math.cos(math.radians(float(business.latitude)))  # float для Decimal
                    lat_allowance_degree = Decimal(allowance_km_radius / km_per_degree_lat)
                    lon_allowance_degree = Decimal(allowance_km_radius / km_per_degree_lon)
                    min_target_latitude = business.latitude - lat_allowance_degree
                    max_target_latitude = business.latitude + lat_allowance_degree
                    min_target_longitude = business.longitude - lon_allowance_degree
                    max_target_longitude = business.longitude + lon_allowance_degree

                    # Простой clamp (лучше твоего deviation)
                    min_target_latitude = max(min_target_latitude, Decimal(MIN_LATITUDE))
                    max_target_latitude = min(max_target_latitude, Decimal(MAX_LATITUDE))
                    min_target_longitude = max(min_target_longitude, Decimal(MIN_LONGITUDE))
                    max_target_longitude = min(max_target_longitude, Decimal(MAX_LONGITUDE))

                    business_ids_query = select(Business.id).where(
                        Business.active.is_(True),
                        Business.deleted.is_(False),
                        Business.business_type == SUPPLIER,
                        Business.geopoint.is_(True),
                        Business.latitude.between(min_target_latitude, max_target_latitude),
                        Business.longitude.between(min_target_longitude, max_target_longitude)
                    )
                    business_ids_result = await session.execute(business_ids_query)
                    business_ids = business_ids_result.scalars().all()
                    if business_ids:
                        filters.append(Product.business_id.in_(business_ids))
                    else:                        
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

                if not all_categories and allowed_categories and isinstance(allowed_categories, list):
                    filters.append(Product.category_code.in_(allowed_categories))

                if only_favorite_businesses and isinstance(user.favorite_businesses, list):
                    if not user.favorite_businesses:                        
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}
                    else:
                        filters.append(Product.business_id.in_(user.favorite_businesses))  # Исправил id → business_id

                if only_favorite_products and isinstance(user.favorite_products, list):
                    if not user.favorite_products:                        
                        return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}
                    else:
                        filters.append(Product.id.in_(user.favorite_products))

                if hide_without_price:
                    no_price = Decimal(0)
                    filters.append(Product.price > no_price)

                if hide_without_photo:
                    filters.append(Product.avatar_name != "")  # Исправил (предполагая str; или .isnot(None))

            if filters:
                query = query.where(and_(*filters))

            # Выполняем
            result = await session.execute(query)
            products = result.scalars().all()
            # Убрал if not products return False — лучше продолжить

            # Count для total
            count_query = select(func.count()).select_from(Product)
            if filters:
                count_query = count_query.where(and_(*filters))
            total = await session.scalar(count_query) or 0

            if not products:                
                return {"status": True, "products_dict": {}, "total_count": total, "one_supplier_info": None}

            common_business_list = [p.business_id for p in products]  # Улучшил: list comp

            if supplier_id and supplier_id not in common_business_list:
                common_business_list.append(supplier_id)

            business_names_native = (await session.execute(
                select(Business.id, Business.name, Business.currency, Business.timezone, Business.schedule).where(Business.id.in_(common_business_list))
            )).mappings().all()

            business_names_local = (await session.execute(
                select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                .where(BusinessTranslation.business_id.in_(common_business_list))
            )).mappings().all()

            all_businesses = {}
            for row in business_names_native:
                all_businesses[row['id']] = {"native": row['name'], "currency": row['currency'], "timezone": row['timezone'], "schedule": row['schedule']}
                
            for row in business_names_local:
                all_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']

            one_supplier_info = None
            if supplier_id:
                one_supplier_info = all_businesses.get(supplier_id, None)

            product_ids = [product.id for product in products]            

            products_dict = {}
            for product in products:
                key = str(product.id)
                products_dict[key] = product.to_dict()
                products_dict[key]["translation"] = {}
                products_dict[key]["business_names"] = all_businesses.get(product.business_id, {})
                products_dict[key]["rating"] = 0
                products_dict[key]["rating_count"] = 0
                products_dict[key]["currency"] = all_businesses[product.business_id]["currency"]
                products_dict[key]["timezone"] = all_businesses[product.business_id]["timezone"]
                products_dict[key]["schedule"] = all_businesses[product.business_id]["schedule"]

            if product_ids:
                translations = (await session.execute(
                    select(ProductTranslation).where(ProductTranslation.product_id.in_(product_ids))
                )).scalars().all()
                if translations:
                    for t in translations:
                        products_dict[str(t.product_id)]["translation"][t.language] = t.to_dict()

                ratings = (await session.execute(
                    select(
                        ReviewProduct.product_id,
                        func.avg(ReviewProduct.rate).label('average'),
                        func.count(ReviewProduct.rate).label('count')
                    ).where(
                        ReviewProduct.product_id.in_(product_ids),
                        ReviewProduct.banned_by_admin.is_(False),
                        ReviewProduct.rate != 0,
                        ReviewProduct.rate.between(MIN_RATE, MAX_RATE)
                    ).group_by(ReviewProduct.product_id)
                )).all()

                for row in ratings:
                    product_id, average, count = row
                    if count > 0:
                        str_key = str(product_id)
                        if str_key in products_dict:
                            products_dict[str_key]["rating"] = float(round(average or 0, 1))
                            products_dict[str_key]["rating_count"] = count
                                

            return {"status": True, "products_dict": products_dict, "total_count": total, "one_supplier_info": one_supplier_info}

        except Exception as e:
            logger.exception("get_individual_products_request_bundle - MAIN EXCEPTION ERROR")
            await put_critical_error_into_db(
                "get_individual_products_request_bundle", "main exception error",
                f"Error text: {str(e)}",
                {"user_id": user_id, "bundle": bundle}
            )
            return {"status": False}


async def get_product(user_id : int, product_id : int) -> dict:
    async with async_session() as session:
        try:
            product = (await session.execute(select(Product).where(Product.id == product_id, Product.deleted.is_(False)))).scalars().first()
            if not product:
                logger.error(f"get_product: Product ID {product_id} not found")
                return {"status": False}
            product_dict = product.to_dict()

            product_dict["translation"] = {}
            translations = (await session.execute(
                        select(ProductTranslation).where(ProductTranslation.product_id == product_id)
                    )).scalars().all()            
            
            if translations:
                for t in translations:
                    product_dict["translation"][t.language] = t.to_dict()            
                
            business_id = product.business_id

            business = (await session.execute(select(Business).where(Business.id == business_id, Business.deleted.is_(False), Business.active.is_(True)))).scalars().first()
            if not business:
                logger.error(f"get_product: Business of Product {product_id} not found")
                return {"status": False}
            
            staff_ids = business.staff or []
            if not product.active and not (user_id == business.owner_id or user_id in staff_ids):
                logger.error(f"get_product: Product {product_id} is not available for user {user_id}")
                return {"status": False}
            
            business_names_native = {
                'id': business.id,
                'name': business.name
            }

            business_names_local = (await session.execute(
                    select(BusinessTranslation.language, BusinessTranslation.name).where(BusinessTranslation.business_id == business_id)
                )).mappings().all()            

            business_names = {}

            if business_names_native:
                business_names["native"] = business_names_native["name"]

            for row in business_names_local:
                if "native" not in business_names:
                    business_names["native"] = None  # Fallback, если native нет, но переводы есть (редкий случай)
                business_names[row["language"]] = row["name"]
            
            product_dict["business_names"] = business_names
            product_dict["currency"] = business.currency

            product_dict["rating"] = 0
            product_dict["rating_count"] = 0

            ratings = (await session.execute(
                select(
                    func.avg(ReviewProduct.rate).label('average'),
                    func.count(ReviewProduct.rate).label('count')
                ).where(
                    ReviewProduct.product_id == product_id,
                    ReviewProduct.banned_by_admin.is_(False),
                    ReviewProduct.rate != 0,
                    ReviewProduct.rate.between(MIN_RATE, MAX_RATE)
                )
            )).all()

            if ratings:
                row = ratings[0]
                average, count = row
                if count > 0:
                    product_dict["rating"] = float(round(average or 0, 1))
                    product_dict["rating_count"] = count

            return {"status": True, "product_dict": product_dict}

        except Exception as e:
            logger.exception("get_product - MAIN EXCEPTION ERROR")
            await put_critical_error_into_db( 
                "get_product", "main exception error", 
                f"Error text: {str(e)}", 
                {
                    "user_id": user_id,
                    "product_id": product_id
                }
            )
            return { "status": False }        
        

async def add_new_product_to_catalog(user_id : int, business_id : int, product_data : dict, avatar: UploadFile | None = None) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
                if not user:
                    await put_critical_error_into_db("add_new_product_to_catalog", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "message": f"User with ID {user_id} not found"}
                
                business = (await session.execute(select(Business).where(Business.id == business_id, Business.active.is_(True)))).scalars().first()
                if not business:
                    logger.error(f"add_new_product_to_catalog: Business ID {business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"add_new_product_to_catalog: User {user_id} is not owner for business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {business_id}"}
                
                tariff = (await session.execute(select(TariffPlan).where(TariffPlan.slug == business.tariff, TariffPlan.active.is_(True)))).scalars().first()
                if not tariff:
                    tariff = (await session.execute(select(TariffPlan).where(TariffPlan.slug == TARIFF_FREE))).scalars().first()
                
                tariff_features = getattr(tariff, "features", {})
                supplier_features = tariff_features.get("supplier", {})
                product_limit = supplier_features.get("product_catalog_limit", None)
                if not (product_limit and isinstance(product_limit, int)):
                    tariff_slug = getattr(tariff, "slug")
                    await put_critical_error_into_db(
                        "add_new_product_to_catalog", 
                        "cannot to get PRODUCT_CATAOG_LIMIT form tariff", 
                        f"cannot to get PRODUCT_CATAOG_LIMIT form tariff {tariff_slug}", 
                        {"user_id": user_id, "tariff_slug": tariff_slug}
                    )
                    product_limit = DEFAULT_PRODUCT_CATALOG_LIMIT                            

                product_count = await session.scalar(select(func.count(Product.id)).where(Product.business_id == business_id, Product.active.is_(True), Product.deleted.is_(False)))

                if product_count >= product_limit:
                    logger.error(f"add_new_product_to_catalog: Business {business_id} has exceeded its product creation limit.", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_exceeded_product_creation_limit", "message": f"add_new_product_to_catalog: Business {business_id} has exceeded its product creation limit."}

                name = product_data.get("name", None)
                description = product_data.get("description", "")
                measure_code = product_data.get("measure_code", None)
                pack_params = product_data.get("pack_params", "")
                price = product_data.get("price", 0)
                min_order = product_data.get("min_order_quantity", 1)
                max_order = product_data.get("max_order_quantity", 0)
                sku = product_data.get("sku", "")
                category_code = product_data.get("category_code", None)
                daily_limit = product_data.get("daily_limit", 0)
                individual_customer = product_data.get("individual_customer", False)
                shipment_same_day = product_data.get("shipment_same_day", False)
                shipment_hours = product_data.get("shipment_hours", 0)
                shipment_price = product_data.get("shipment_price", 0)

                if shipment_hours is None or not isinstance(shipment_hours, Number):
                    shipment_hours = 0
                if shipment_price is None or not isinstance(shipment_price, Number):
                    shipment_price = 0

                if name is None or measure_code is None:
                    logger.error(f"add_new_product_to_catalog: incorrect incoming data", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"incorrect incoming data"}

                measures_exist = (await session.execute(select(Measure).where(Measure.code == measure_code, Measure.active.is_(True)))).scalars().first()
                if not measures_exist:
                    logger.error(f"add_new_product_to_catalog: incorrect incoming data", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"incorrect incoming data"}
                
                if individual_customer and not shipment_same_day:
                    logger.error(f"add_new_product_to_catalog: incorrect incoming data", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"delivery same day is not specified"}

                if shipment_same_day and (not shipment_hours or not isinstance(shipment_hours, Number)):
                    logger.error(f"add_new_product_to_catalog: incorrect incoming data", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"delivery same day is not specified"}

                category_exist = (await session.execute(select(Category).where(Category.code == category_code, Category.active.is_(True)))).scalars().first()
                if not category_exist:
                    category_code = UNCATEGORIZED

                if not isinstance(min_order, Number) or min_order < 1:
                    min_order = 1
                if not isinstance(max_order, Number) or max_order < 0:
                    max_order = 0
                if not isinstance(daily_limit, Number) or daily_limit < 0:
                    daily_limit = 0
                if not isinstance(price, Number) or price < 0:
                    price = 0
                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                new_product = Product(
                    business_id = business_id,
                    date = current_time_unix,                    
                    name = name,
                    description = description,
                    measure_code = measure_code,
                    pack_params = pack_params,
                    price = Decimal(str(price)),
                    min_order_quantity = Decimal(str(min_order)),
                    max_order_quantity = Decimal(str(max_order)),
                    sku = sku,
                    category_code = category_code,
                    daily_limit = Decimal(str(daily_limit)),
                    language = business.language,
                    individual_customer = individual_customer,
                    shipment_same_day = shipment_same_day,
                    shipment_hours = int(shipment_hours),
                    shipment_price = Decimal(str(shipment_price))
                )

                session.add(new_product)
                await session.flush()

                new_product_id = new_product.id

                filepath=""
                if avatar:                    
                    filename=f"product_{new_product_id}"
                    saved_avatar = await save_uploaded_jpeg_product(avatar=avatar, filename=filename)
                    if saved_avatar["status"]:
                        if saved_avatar.get("webp_path"):
                            filepath = saved_avatar.get("webp_path")
                        elif saved_avatar.get("jpeg_path"):
                            filepath = saved_avatar.get("jpeg_path")                        
                        new_product.avatar_name = filepath

                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": CREATE,
                    "entity_type": PRODUCT,
                    "entity_id": new_product.id,
                    "extra_data": {
                        "business_id": business_id,
                        "product_name": new_product.name
                    }
                }

                # return {"status": True, "log_data": log_data, "new_product": new_product.to_dict()}
                return {"status": True, "log_data": log_data, "new_product_id": new_product.id}
            
            except Exception as e:
                logger.exception("add_new_product_to_catalog - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( 
                    "add_new_product_to_catalog", "main exception error", 
                    f"Error text: {str(e)}", 
                    {
                        "user_id": user_id, 
                        "business_id": business_id, 
                        "product_data": product_data,
                        "avatar": avatar != None
                    }
                )
                return { "status": False }
            

async def get_product_review_list(product_id : int) -> dict:
    async with async_session() as session:
        try:
            reviews_result = await session.execute(
                select(ReviewProduct).where(
                    ReviewProduct.product_id == product_id,
                    ReviewProduct.banned_by_admin == False,                    
                )
            )
            reviews = reviews_result.scalars().all()

            reviews_list = []
            author_user_ids = []
            author_business_ids = []            

            if reviews:
                for review in reviews:
                    review_dict = review.to_dict()
                    reviews_list.append(review_dict)

                    author_user_id = review_dict.get("author_user_id")
                    author_business_id = review_dict.get("author_business_id")

                    if author_user_id is not None:
                        author_user_ids.append(author_user_id)
                    if author_business_id is not None:
                        author_business_ids.append(author_business_id)                    

                # Получаем имена авторов только если есть ID
                author_user_names = {}
                if author_user_ids:
                    user_result = await session.execute(
                        select(AppUser).filter(AppUser.id.in_(author_user_ids))
                    )
                    author_user_names = {u.id: u.username for u in user_result.scalars().all()}

                author_business_names = {}
                if author_business_ids:
                    business_result = await session.execute(
                        select(Business).filter(Business.id.in_(author_business_ids), Business.active.is_(True))
                    )
                    author_business_names = {b.id: b.name for b in business_result.scalars().all()}

                # Добавляем имена в отзывы
                for r in reviews_list:
                    r["author_user_name"] = author_user_names.get(r.get("author_user_id"), "")
                    r["author_business_name"] = author_business_names.get(r.get("author_business_id"), "")

            return { "status": True, "reviews_list": reviews_list }
            
        except Exception as e:
            logger.exception("get_product_review_list - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( 
                "get_product_review_list", "main exception error", 
                f"Error text: {str(e)}", 
                {
                    "product_id": product_id
                }
            )
            return { "status": False }
        

async def update_product(user_id: int, product_id: int, product_data: dict, avatar: UploadFile | None = None) -> dict:
    if isinstance(product_data, dict):
        add_languages = product_data.get("add_languages", [])
        name = product_data.get("name", None)
        description = product_data.get("description", None)
        measure_code = product_data.get("measure_code", None)
        pack_params = product_data.get("pack_params", None)
        price = product_data.get("price", None)
        min_order = product_data.get("min_order", None)
        max_order = product_data.get("max_order", None)
        sku = product_data.get("sku", None)
        active = product_data.get("active", True)
        category_code = product_data.get("category_code", None)
        daily_limit = product_data.get("daily_limit", None)
        local_names = product_data.get("local_names", None)
        individual_customer = product_data.get("individual_customer", None)
        shipment_same_day = product_data.get("shipment_same_day", None)
        shipment_hours = product_data.get("shipment_hours", None)
        shipment_price = product_data.get("shipment_price", None)

    else:
        await put_critical_error_into_db("update_product", "incorrect incoming data", f"incorrect incoming data: look context", {"data": product_data})
        return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": "Internal server error"}    
    async with async_session() as session:
        async with session.begin():
            try:
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
                if not user:
                    await put_critical_error_into_db("update_product", "user not found", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False, "message": f"User with ID {user_id} not found or not active"}
                product = (await session.execute(select(Product).where(Product.id == product_id, Product.deleted.is_(False)).with_for_update())).scalars().first()
                if not product:
                    logger.error(f"update_product: Product ID {product_id} not found")
                    return {"status": False}
                business = (await session.execute(select(Business).where(Business.id == product.business_id, Business.active.is_(True)))).scalars().first()
                if not business:
                    logger.error(f"update_product: Business ID {product.business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {product.business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"update_product: User {user_id} is not owner for business {product.business_id} and product {product_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {product.business_id} and product {product_id}"}

                if active and not product.active:
                    tariff = (await session.execute(select(TariffPlan).where(TariffPlan.slug == business.tariff, TariffPlan.active.is_(True)))).scalars().first()
                    if not tariff:
                        tariff = (await session.execute(select(TariffPlan).where(TariffPlan.slug == TARIFF_FREE))).scalars().first()                
                    tariff_features = getattr(tariff, "features", {})
                    supplier_features = tariff_features.get("supplier", {})
                    product_limit = supplier_features.get("product_catalog_limit", None)
                    if not (product_limit and isinstance(product_limit, int)):
                        tariff_slug = getattr(tariff, "slug")
                        await put_critical_error_into_db(
                            "add_new_product_to_catalog", 
                            "cannot to get PRODUCT_CATAOG_LIMIT form tariff", 
                            f"cannot to get PRODUCT_CATAOG_LIMIT form tariff {tariff_slug}", 
                            {"user_id": user_id, "tariff_slug": tariff_slug}
                        )
                        product_limit = DEFAULT_PRODUCT_CATALOG_LIMIT                            

                    product_count = await session.scalar(select(func.count(Product.id)).where(Product.business_id == business.id, Product.active.is_(True), Product.deleted.is_(False)))

                    if product_count >= product_limit:
                        logger.error(f"update_product: Business {business.id} has exceeded its product creation limit.", user_id=user_id)
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_exceeded_product_limit", "message": f"update_product: Business {business.id} has exceeded its product creation limit."}

                # Validate data

                min_order_quantity = product.min_order_quantity
                max_order_quantity = product.max_order_quantity
                price_dec = product.price
                daily_limit_dec = product.daily_limit
                shipment_price_dec = product.shipment_price
                
                if min_order is not None:
                    try:
                        min_order_quantity = Decimal(str(min_order))
                    except (InvalidOperation, TypeError, ValueError):
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": "min_order must be a valid number or None"}                    
                if max_order is not None:
                    try:
                        max_order_quantity = Decimal(str(max_order))
                    except (InvalidOperation, TypeError, ValueError):
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": "max_order must be a valid number or None"}                    
                if price is not None:
                    try:
                        price_dec = Decimal(str(price))
                    except (InvalidOperation, TypeError, ValueError):
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": "price must be a valid number or None"}
                if daily_limit is not None:
                    try:
                        daily_limit_dec = Decimal(str(daily_limit))
                    except (InvalidOperation, TypeError, ValueError):
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": "daily_limit must be a valid number or None"}                    
                if shipment_price is not None:
                    try:
                        shipment_price_dec = Decimal(str(shipment_price))
                    except (InvalidOperation, TypeError, ValueError):
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": "price must be a valid number or None"}
                
                if max_order_quantity != 0 and min_order_quantity > max_order_quantity:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Incorrect data: max order cannot be less min order"}
                if daily_limit_dec != 0 and min_order_quantity > daily_limit_dec:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Incorrect data: daily limit cannot be less min order"}                                                
                
                if individual_customer is None:
                    individual_customer = product.individual_customer
                if shipment_same_day is None:
                    shipment_same_day = product.shipment_same_day
                if shipment_hours is None:
                    shipment_hours = product.shipment_hours

                if individual_customer and not shipment_same_day:                    
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"delivery same day is not specified 1"}

                if shipment_same_day and (not shipment_hours or not isinstance(shipment_hours, Number)):                    
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"delivery same day is not specified 2"}
                
                if not isinstance(shipment_hours, Number) or shipment_hours < 0 or shipment_hours > 12:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid shipment hours value"}
                
                if name is not None and (not isinstance(name, str) or name == ""):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Incorrect data: Name is empty"}
                
                if sku is not None and not isinstance(sku, str):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid SKU type"}

                if measure_code is not None:
                    if isinstance(measure_code, str):
                        measure = (await session.execute(select(Measure).where(Measure.code == measure_code, Measure.active.is_(True)))).scalars().first()
                        if not measure:                        
                            return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid measure_code"}
                    else:
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid measure_code"}
                
                # Update category_code
                if category_code is not None:
                    if isinstance(category_code, str):
                        category = (await session.execute(select(Category).where(Category.code == category_code, Category.active.is_(True)))).scalars().first()
                        if not category:
                            return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid category_code"}    
                    else:
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid category_code"}

                # Update order limits, price, daily_limit; Update delivery options

                if product.min_order_quantity != min_order_quantity:
                    product.min_order_quantity = min_order_quantity
                if product.max_order_quantity != max_order_quantity:
                    product.max_order_quantity = max_order_quantity
                if product.price != price_dec:
                    product.price = price_dec
                if product.daily_limit != daily_limit_dec:
                    product.daily_limit = daily_limit_dec
                if product.shipment_price != shipment_price_dec:
                    product.shipment_price = shipment_price_dec                
                if product.shipment_hours != shipment_hours:
                    product.shipment_hours = int(shipment_hours)

                # Update avatar
                update_avatar_error = False
                update_avatar = False
                filepath=""
                if avatar:
                    update_avatar = True
                    filename=f"product_{product_id}"
                    saved_avatar = await save_uploaded_jpeg_product(avatar=avatar, filename=filename)
                    if saved_avatar["status"]:
                        if saved_avatar.get("webp_path"):
                            filepath = saved_avatar.get("webp_path")
                        elif saved_avatar.get("jpeg_path"):
                            filepath = saved_avatar.get("jpeg_path")                        
                        product.avatar_name = filepath
                    else:
                        update_avatar_error = True
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_image_processing_error", "message": f"Avatar updating error"}
                
                # Update name
                if name is not None:                    
                    if len(name) > 255:
                        name = name[:255]
                    if name != product.name:
                        product.name = name

                # Update SKU
                if sku is not None:                    
                    if len(sku) > 50:
                        sku = sku[:50]
                    if product.sku != sku:
                        product.sku = sku

                # Update measure_code                
                if measure_code is not None and measure_code != product.measure_code:                    
                    product.measure_code = measure_code                    

                # Update category_code
                if category_code is not None and category_code != product.category_code:
                    product.category_code = category_code

                # Update active status
                if active != product.active:
                    product.active = active

                # Update individual_customer status
                if individual_customer != product.individual_customer:
                    product.individual_customer = individual_customer

                # Update Delivery options
                if shipment_same_day != product.shipment_same_day:
                    product.shipment_same_day = shipment_same_day                                                                                            

                # Update new langages and local names, description and pack params in new languages
                # All languages dict
                all_languages = get_languages()
                # Business languages list
                business_languages_query = select(BusinessTranslation.language).filter(BusinessTranslation.business_id == product.business_id)
                business_languages_result = await session.execute(business_languages_query)
                business_languages_exists = business_languages_result.scalars().all()
                # Add translations models
                # Expected add_languages format: ["en", "ru"]
                # Expected local_names format: {"en": "English name", "ru": "Русское имя"}
                # Expected description format: {"en": "Description ...", "ru": "Описание ..."}
                # Expected pack_params format: {"en": "Package description ...", "ru": "Описание упаковки ..."}
                add_language_error = False

                if len(add_languages) > 0:                    
                    translations_query = select(ProductTranslation.language).filter(ProductTranslation.product_id == product_id)
                    translations_result = await session.execute(translations_query)
                    translations_exists = translations_result.scalars().all()
                    
                    for lang in add_languages:
                        if lang not in translations_exists:                            
                            lang_is_exists = any(l.code == lang for l in all_languages)
                            if not lang_is_exists or not lang in business_languages_exists:
                                add_language_error = True
                                continue
                            else:
                                if local_names and isinstance(local_names, dict):
                                    local_product_name = local_names.get(lang, product.name)                                
                                    local_description = ""
                                    local_pack_params = ""
                                    if description and isinstance(description, dict):
                                        local_description = description.get(lang, "")
                                    if pack_params and isinstance(pack_params, dict):
                                        local_pack_params = pack_params.get(lang, "")
                                    new_translation = ProductTranslation(
                                        product_id = product_id,
                                        name = local_product_name,
                                        description = local_description,
                                        pack_params = local_pack_params,
                                        language = lang
                                    )
                                    session.add(new_translation)
                                    await session.flush()
                
                # Update name in existed languages            
                native_product_language = product.language
                languages_for_update = []
                if local_names and isinstance(local_names, dict):
                    for key, value in local_names.items():
                        language_is_exists = any(l.code == key for l in all_languages)
                        if language_is_exists and key not in add_languages and key not in languages_for_update:
                            languages_for_update.append(key)
                if description and isinstance(description, dict):
                    for key, value in description.items():
                        language_is_exists = any(l.code == key for l in all_languages)
                        if language_is_exists and key not in add_languages and key not in languages_for_update:
                            languages_for_update.append(key)
                if pack_params and isinstance(pack_params, dict):
                    for key, value in pack_params.items():
                        language_is_exists = any(l.code == key for l in all_languages)
                        if language_is_exists and key not in add_languages and key not in languages_for_update:
                            languages_for_update.append(key)
                
                for language in languages_for_update:
                    if language == native_product_language:
                        if description and isinstance(description, dict):
                            new_description = description.get(language, None)
                            if new_description is not None and isinstance(new_description, str):
                                if len(new_description) > 1000:
                                    new_description = new_description[:1000]
                                if product.description != new_description:
                                    product.description = new_description
                        if pack_params and isinstance(pack_params, dict):
                            new_pack_params = pack_params.get(language, None)
                            if new_pack_params is not None and isinstance(new_pack_params, str):
                                if len(new_pack_params) > 255:
                                    new_pack_params = new_pack_params[:255]
                                if product.pack_params != new_pack_params:
                                    product.pack_params = new_pack_params
                    else:
                        translation_query = select(ProductTranslation).where(ProductTranslation.product_id == product_id, ProductTranslation.language == language).with_for_update()
                        translation_result = await session.execute(translation_query)
                        translation = translation_result.scalars().first()
                        if translation:
                            if local_names and isinstance(local_names, dict):
                                new_name = local_names.get(language, None)
                                if new_name and isinstance(new_name, str):
                                    if len(new_name) > 255:
                                        new_name = new_name[:255]
                                    if translation.name != new_name:
                                        translation.name = new_name
                            if description and isinstance(description, dict):
                                new_description = description.get(language, None)
                                if new_description is not None and isinstance(new_description, str):
                                    if len(new_description) > 1000:
                                        new_description = new_description[:1000]
                                    if translation.description != new_description:
                                        translation.description = new_description
                            if pack_params and isinstance(pack_params, dict):
                                new_pack_params = pack_params.get(language, None)
                                if new_pack_params is not None and isinstance(new_pack_params, str):
                                    if len(new_pack_params) > 255:
                                        new_pack_params = new_pack_params[:255]
                                    if translation.pack_params != new_pack_params:
                                        translation.pack_params = new_pack_params
 
                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": UPDATE,
                    "entity_type": PRODUCT,
                    "entity_id": product_id,
                    "extra_data": {
                        "update_data": product_data,
                        "update_avatar": update_avatar,
                        "update_error": {
                            "avatar": update_avatar_error,
                            "add_languages": add_language_error
                        }
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.exception("update_product - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "update_product", "main exception error",
                    f"Error text: {str(e)}", {"data": product_data}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                } 


async def delete_product(user_id: int, product_id: int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
                if not user:
                    await put_critical_error_into_db("delete_product", "user not found", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False, "message": f"User with ID {user_id} not found or not active"}
                product = (await session.execute(select(Product).where(Product.id == product_id, Product.deleted.is_(False)).with_for_update())).scalars().first()
                if not product:
                    logger.error(f"delete_product: Product ID {product_id} not found")
                    return {"status": False}
                business = (await session.execute(select(Business).where(Business.id == product.business_id, Business.active.is_(True)))).scalars().first()
                if not business:
                    logger.error(f"delete_product: Business ID {product.business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {product.business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"delete_product: User {user_id} is not owner for business {product.business_id} and product {product_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {product.business_id} and product {product_id}"}

                # NEED UPDATE - CHECKING FOR CURRENT ORDERS
                # order_types = [ORDER_STATUS_LIVE, ORDER_STATUS_COMPLETED, ORDER_STATUS_DISPUTE]
                # current_orders = await get_business_orders(user_id, business_id, order_types)
                # if len(current_orders) > 0:
                # logger.error(f"delete_business - cannot delete business", user_id=user_id)
                #     return { "status": False, "notify_type": "error", "notify_code": "notify_error_cannot_delete_business_unclosed_orders"}
                # NEED UPDATE - CHECKING FOR CURRENT ORDERS

                product.deleted = True

                log_data = {
                    "user_id": user_id,
                    "action_type": DELETE,
                    "entity_type": PRODUCT,
                    "entity_id": product_id,
                    "extra_data": {                        
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.exception("delete_product - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "delete_product", "main exception error",
                    f"Error text: {str(e)}", {"product_id": product_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }


async def get_product_ordered_from_redis(user_id: int, product_ids: list) -> dict:
    try:
        if not isinstance(product_ids, list):
            return {"status": False}        
        products_ordered = {}
        if len(product_ids) == 0:
            return {"status": True, "products_ordered": products_ordered}
        for p_id in product_ids:
            product_ordered = await get_product_ordered_quantity_by_id(p_id)
            if product_ordered:                
                products_ordered[f"{p_id}"] = product_ordered
        return {"status": True, "products_ordered": products_ordered}
    except Exception as e:
        logger.exception(f"get_product_ordered_from_redis - MAIN EXCEPTION ERROR: {e}") 
        await put_critical_error_into_db("get_product_ordered_from_redis", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "product_ids": product_ids})
        return {"status": False}

