from models.busineses import Business, BusinessTranslation
from models.app_users import AppUser
from models.reviews import ReviewBusiness, ReviewProduct
from models.interface import LanguageInterface
from models.products import Product
from models.orders import Order
from models.finances import AdCampaignBusinessPromo


from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, and_, exists, func, case
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from fastapi import UploadFile

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from .error import put_critical_error_into_db
from .images import save_uploaded_jpeg_business, get_avatar_from_telegram
from .interfaces import get_interface
from .geodata import calculate_distance_km
from .ad_campaing import get_ad_campaign_list

from payments.free_promo import get_date_last_free_promo_payment

from constants.log_entitys import CREATE, UPDATE, DELETE, BUSINESS, REPLY, EMPLOYEE, CONFIRM, REJECT, PRODUCT, INDIVIDUAL_CUSTOMER_ACCOUNT

from constants.languages import get_languages
from constants.geodata import MIN_LATITUDE, MAX_LATITUDE, MIN_LONGITUDE, MAX_LONGITUDE, AVERAGE_KM_PER_DEGREE_LAT, EQUATOR_KM_PER_DEGREE_LON
from constants.business_types import SUPPLIER, CUSTOMER, INDIVIDUAL, SUPPLIER_ROLE, CUSTOMER_ROLE
from constants.rate_system import MAX_RATE, MIN_RATE, MAX_COMMENT_LENGTH
from constants.limit_settings import ADDITIONAL_LANGUAGES_LIMIT
from constants.schedule import DEFAULT_SCEDULE
from constants.timers import JOIN_STAFF_REQUEST_UNDELETABLE_PERIOD
from constants.orders import *
from constants.default import (DEFAULT_GEODATA, DEFAULT_LANGUAGE, DEFAULT_TIMEZONE, CUSTOMER_PRODUCT_CATALOG_FILTERS, INDIVIDUAL_PRODUCT_CATALOG_FILTERS, 
    BUSINESS_MESSAGES_DEFAULT_FILTER_SETTINGS, BUSINESS_ORDERS_DEFAULT_FILTER_SETTINGS, SEARCH_COUNTER_AGENT_FILTERS, DEFAULT_SEARCH_RADIUS_KM, SEARCH_COUNTER_AGENT_BUNDLE_SIZE, 
    MINIMAL_SEARCH_RADIUS_KM, MAXIMAL_SEARCH_RADIUS_KM, STRING_LENGTH_255)


from constants.frontend import TAB_MESSAGE_CENTER, TAB_USER_PROFILE

from decimal import Decimal

from shemas.business import BusinessCreate, IndividualCreate, BusinessUpdate, IndividualUpdate
from shemas.filters import IndividualProductCatalogFilters, CustomerProductCatalogFilters, CounterAgentSearchFilters
from pydantic import ValidationError

import math

def get_referrer_id(user_data : dict) -> int:
    try:
        start_param = user_data.get("start_param", {})
        if start_param.get("action") == "invite_referral":
            referrer_id = start_param.get("referrer_id", 0)
        else:
            referrer_id = 0
        return referrer_id
    except Exception as e:
        logger.error(f"get_referrer_id EXCEPTION ERROR: {e}")
        return 0



async def get_advanced_userinfo(user_id):
    async with async_session() as session:
        try:
            
            query = select(AppUser).filter(AppUser.id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            if not user:
                await put_critical_error_into_db("get_advanced_userinfo", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False, "message": f"User {user_id} not found"}
            
            business_ids_list = user.business_list
            if user.active_business_id and user.active_business_id != 0 and not user.active_business_id in user.business_list:
                business_ids_list.append(user.active_business_id)

            if user.individual_id != 0 and not user.individual_id in business_ids_list:
                business_ids_list.append(user.individual_id)
            
            if user.outcoming_employer_business_id != 0 and user.outcoming_employer_business_id != user.active_business_id:                
                employer_business = (await session.execute(select(Business).where(Business.id == user.outcoming_employer_business_id, Business.deleted.is_(False)))).scalars().first()
                if employer_business:
                    if user_id in employer_business.staff and employer_business.id not in business_ids_list:                        
                        business_ids_list.append(employer_business.id)
        
            business_query = (
                select(Business)
                .where(Business.id.in_(business_ids_list), 
                       Business.active.is_(True),
                       Business.deleted.is_(False))
            )
            business_result = await session.execute(business_query)
            businesses = {b.id: b for b in business_result.scalars().all()}

            

            # 3. Загружаем все переводы одним запросом
            translation_query = (
                select(BusinessTranslation)
                .where(BusinessTranslation.business_id.in_(business_ids_list))
            )
            translation_result = await session.execute(translation_query)

            translations_by_business = {}
            for t in translation_result.scalars().all():
                translations_by_business.setdefault(t.business_id, []).append(t.to_dict())

            # 4. Собираем итоговую структуру
            business_list = []
            for business_id in user.business_list:
                business = businesses.get(business_id)
                if not business:
                    continue
                
                business_dict = business.to_dict()

                if business.owner_id == user_id or user_id in business.staff:
                    staff_ids = business.staff or []  # на случай, если staff = None
                    staff_ids = list(set(staff_ids))  # убираем возможные дубликаты
    
                    # Добавляем owner_id, если его ещё нет в списке
                    if business.owner_id not in staff_ids:
                        staff_ids.append(business.owner_id)

                    if staff_ids:
                        # Получаем всех пользователей по ID из staff_ids
                        staff_query = select(AppUser.id, AppUser.username).where(AppUser.id.in_(staff_ids))
                        staff_result = await session.execute(staff_query)
                        staff_dict = {row.id: row.username for row in staff_result.all()}
                        # Формируем список словарей
                        staff_usernames = []
                        # Сначала владелец (owner_id) — всегда на первом месте
                        if business.owner_id in staff_dict:
                            staff_usernames.append({
                                "id": business.owner_id,
                                "username": staff_dict[business.owner_id],
                                "is_owner": True

                            })
                        # Затем все остальные сотрудники
                        for sid in staff_ids:
                            if sid != business.owner_id and sid in staff_dict:
                                staff_usernames.append({
                                    "id": sid,
                                    "username": staff_dict[sid],
                                    "is_owner": False
                                })
                        business_dict["staff_usernames"] = staff_usernames                  

                b_dict = filter_business_info_for_user(business_dict, user_id)
                b_dict["translations"] = translations_by_business.get(business_id, [])
                business_list.append(b_dict)
            
            # Here will getting advanced info logic
            user_dict = user.to_dict()

            last_free_credits_date = await get_date_last_free_promo_payment(user_id=user_id)
            user_dict["last_free_credits_date"] = last_free_credits_date

            ad_campaign_list = await get_ad_campaign_list(user.business_list)            

            return {"status": True, "userdata": user_dict, "business_list": business_list, "ad_campaign_list": ad_campaign_list}
        except Exception as e:
            logger.error(f"get_advanced_userinfo EXCEPTION ERROR: {e}", user_id=user_id)
            return {"status": False, "message": f"EXCEPTION ERROR: {e}"}


async def business_register(user_id: int, data: dict, avatar: UploadFile | None = None) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                user_query = select(AppUser).filter(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("business_register", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"business_register: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                if len(user.business_list) >= user.limit_of_business:
                    logger.error(f"business_register: The limit for creating new businesses has been exceeded.", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_limit_businesses_exceeded", "message": f"The limit for creating new businesses has been exceeded."}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                try:
                    validated = BusinessCreate(**data)
                except ValidationError as e:
                    logger.error(f"business_register: Validation data error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Data validation error"}
                
                geopoint_is_correct = False
                geodata = validated.geodata
                if geodata:                    
                    user_latitude = float(geodata.latitude)
                    user_longitude = float(geodata.longitude)
                else:
                    geodata_dict = DEFAULT_GEODATA
                    user_latitude = float(geodata_dict.get("latitude"))
                    user_longitude = float(geodata_dict.get("longitude"))
                latitude = Decimal(str(user_latitude))
                longitude = Decimal(str(user_longitude))
                if not (latitude == Decimal(0) and longitude == Decimal(0)):
                    geopoint_is_correct = True
                
                all_languages = get_languages()
                business_language = validated.language
                lang_is_exists = any(lang.code == business_language for lang in all_languages)
                if not lang_is_exists:
                    business_language = user.language

                description = validated.description
                if not description:
                    description = ""
                
                address = validated.address
                if not address:
                    address = ""

                business_timezone = validated.timezone
                if not business_timezone:
                    business_timezone = DEFAULT_TIMEZONE
                
                schedule = validated.schedule
                if not schedule:
                    schedule = DEFAULT_SCEDULE

                new_business = Business(
                    business_type = validated.type,
                    owner_id = user_id,
                    name = validated.name,
                    description = description,
                    avatar_name = "",
                    reg_date = current_time_unix,
                    language = business_language,
                    address = address,
                    geopoint = geopoint_is_correct,
                    latitude = latitude,
                    longitude = longitude,
                    timezone = business_timezone,
                    currency = validated.currency,
                    schedule = schedule                    
                )
                session.add(new_business)
                await session.flush()

                new_business_id = new_business.id

                filepath=""
                if avatar:                    
                    filename=f"business_{new_business_id}"
                    saved_avatar = await save_uploaded_jpeg_business(avatar=avatar, filename=filename)
                    if saved_avatar["status"]:
                        if saved_avatar.get("webp_path"):
                            filepath = saved_avatar.get("webp_path")
                        elif saved_avatar.get("jpeg_path"):
                            filepath = saved_avatar.get("jpeg_path")                        
                        new_business.avatar_name = filepath


                user.business_list.append(new_business_id)
                flag_modified(user, "business_list")
                user.active_business_id = new_business_id

                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": CREATE,
                    "entity_type": BUSINESS,
                    "entity_id": new_business.id,
                    "extra_data": {
                        "business_name": new_business.name
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.error(f"business_register EXCEPTION ERROR: {e}", user_id=user_id)
                return {"status": False, "message": f"EXCEPTION ERROR: {e}"}


async def individual_register(user_id: int, data: dict, telegram_avatar_url: str | None = None, avatar: UploadFile | None = None) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                user_query = select(AppUser).filter(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("individual_register", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"individual_register: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                if user.individual_id != 0:
                    logger.error(f"individual_register: User with ID {user_id} is inactive already has individual business account: {user.individual_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"individual_register: User with ID {user_id} is inactive already has individual business account: {user.individual_id}"}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                try:
                    validated = IndividualCreate(**data)
                except ValidationError as e:
                    logger.error(f"individual_register: Validation data error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Data validation error"}
                                                
                business_language = user.language
            
                business_timezone = validated.timezone
                if not business_timezone:
                    business_timezone = DEFAULT_TIMEZONE

                geopoint_is_correct = False
                geodata = validated.geodata
                if geodata:                    
                    user_latitude = float(geodata.latitude)
                    user_longitude = float(geodata.longitude)
                else:
                    geodata_dict = DEFAULT_GEODATA
                    user_latitude = float(geodata_dict.get("latitude"))
                    user_longitude = float(geodata_dict.get("longitude"))
                latitude = Decimal(str(user_latitude))
                longitude = Decimal(str(user_longitude))
                if not (latitude == Decimal(0) and longitude == Decimal(0)):
                    geopoint_is_correct = True

                new_business = Business(
                    business_type = INDIVIDUAL,
                    owner_id = user_id,
                    name = validated.name,                    
                    avatar_name = "",
                    reg_date = current_time_unix,
                    language = business_language,
                    timezone = business_timezone,
                    currency = validated.currency,
                    geopoint = geopoint_is_correct
                )
                session.add(new_business)
                await session.flush()

                new_business_id = new_business.id

                user_avatar = avatar

                if not user_avatar and telegram_avatar_url:
                    making_avatar = await get_avatar_from_telegram(telegram_avatar_url)
                    if making_avatar["status"]:
                        user_avatar = making_avatar["avatar_file"]
                    else:
                        logger.error(f"individual_register - cannot to create avatar from telegram picture", user_id=user_id)

                filepath=""
                if user_avatar:
                    filename=f"business_{new_business_id}"
                    saved_avatar = await save_uploaded_jpeg_business(avatar=user_avatar, filename=filename)
                    if saved_avatar["status"]:
                        if saved_avatar.get("webp_path"):
                            filepath = saved_avatar.get("webp_path")
                        elif saved_avatar.get("jpeg_path"):
                            filepath = saved_avatar.get("jpeg_path")                        
                        new_business.avatar_name = filepath                                
                
                user.active_business_id = new_business_id
                user.individual_id = new_business_id

                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": CREATE,
                    "entity_type": INDIVIDUAL_CUSTOMER_ACCOUNT,
                    "entity_id": new_business.id,
                    "extra_data": {
                        "business_name": new_business.name 
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.error(f"individual_register EXCEPTION ERROR: {e}", user_id=user_id)
                return {"status": False, "message": f"EXCEPTION ERROR: {e}"}


def filter_business_info_for_user(business: dict, user_id: int) -> dict:
    owner_id = business.get("owner_id")
    staff = set(business.get("staff", []))

    if user_id == owner_id:
        return business  # владелец видит всё

    base_fields = {
        "id",
        "business_type",
        "name",
        "description",
        "avatar_name",
        "language",
        "extra_languages",
        "address",
        "geopoint",
        "latitude",
        "longitude",
        "timezone",
        "currency",
        "schedule"
    }

    staff_fields = base_fields | {
        "owner_id",
        "staff",
        "active_orders",
        "closed_orders",
        "contacts_allowed",
        "tariff",

        "staff_usernames"
    }

    public_fields = base_fields

    allowed_fields = (
        staff_fields if user_id in staff else public_fields
    )

    return {k: v for k, v in business.items() if k in allowed_fields}


async def get_business_profile(user_id: int, business_id: int) -> dict:
    async with async_session() as session:
        try:
            # Проверка пользователя
            user = await session.get(AppUser, user_id)
            if not user:
                await put_critical_error_into_db(
                    "get_business_profile", "user not found",
                    f"User {user_id} not found", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"User with ID {user_id} not found"
                }

            if not user.active:
                await put_critical_error_into_db(
                    "get_business_profile", "user is inactive",
                    f"User {user_id} is inactive", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_user_inactive",
                    "message": f"User with ID {user_id} is inactive"
                }

            # Получение бизнеса
            business = await session.get(Business, business_id)
            if not business:
                logger.error("get_business_profile - Business not found", extra={"user_id": user_id, "business_id": business_id})
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_business_not_found",
                    "message": f"Business with ID {business_id} not found"
                }

            business_dict = business.to_dict()

            # Переводы
            translations_result = await session.execute(
                select(BusinessTranslation).filter(BusinessTranslation.business_id == business_id)
            )
            translations_list = [t.to_dict() for t in translations_result.scalars().all()]

            # Отзывы
            reviews_result = await session.execute(
                select(ReviewBusiness).filter(
                    ReviewBusiness.business_id == business_id,
                    ReviewBusiness.banned_by_admin == False,                    
                )
            )
            reviews = reviews_result.scalars().all()

            reviews_list = []
            author_user_ids = []
            author_business_ids = []
            rate_list = []

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

                    rate = review_dict.get("rate")
                    if rate is not None and MIN_RATE <= rate <= MAX_RATE:
                        rate_list.append(rate)

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

            # Проверка словаря по правам доступа пользователя
            business_dict = filter_business_info_for_user(business_dict, user_id)

            # Рейтинг
            business_rating = round(sum(rate_list) / len(rate_list), 1) if rate_list else 0
            business_dict["rating"] = business_rating
            business_dict["reviews_count"] = len(reviews_list)  # Полезно для фронтенда


            # Получаем usernames сотрудников и владельца (только если пользователь имеет доступ)
            if business.owner_id == user_id or user_id in business.staff:
                staff_ids = business.staff or []  # на случай, если staff = None
                staff_ids = list(set(staff_ids))  # убираем возможные дубликаты
    
                # Добавляем owner_id, если его ещё нет в списке
                if business.owner_id not in staff_ids:
                    staff_ids.append(business.owner_id)

                if staff_ids:
                    # Получаем всех пользователей по ID из staff_ids
                    staff_query = select(AppUser.id, AppUser.username).where(AppUser.id.in_(staff_ids))
                    staff_result = await session.execute(staff_query)
                    staff_dict = {row.id: row.username for row in staff_result.all()}

                    # Формируем список словарей
                    staff_usernames = []

                    # Сначала владелец (owner_id) — всегда на первом месте
                    if business.owner_id in staff_dict:
                        staff_usernames.append({
                            "id": business.owner_id,
                            "username": staff_dict[business.owner_id],
                            "is_owner": True

                        })

                    # Затем все остальные сотрудники
                    for sid in staff_ids:
                        if sid != business.owner_id and sid in staff_dict:
                            staff_usernames.append({
                                "id": sid,
                                "username": staff_dict[sid],
                                "is_owner": False
                            })

                    business_dict["staff_usernames"] = staff_usernames
            
            business_role = None
            if business.business_type == SUPPLIER:
                business_role = SUPPLIER_ROLE
            elif business.business_type == CUSTOMER or business.business_type == INDIVIDUAL:
                business_role = CUSTOMER_ROLE

            if business_role:
                consider_statuses = RELIABILITY_STATUSES[business_role]["consider_statuses"]
                successfull_statuses = RELIABILITY_STATUSES[business_role]["successfull_statuses"]
                if business_role == SUPPLIER_ROLE:
                    condition = (Order.supplier_id == business_id)
                else:
                    condition = or_(
                        Order.customer_id == business_id,
                        Order.individual_id == business_id
                    )
                query = select(
                    func.count(case((Order.status.in_(consider_statuses), 1))).label("consider_count"),
                    func.count(case((Order.status.in_(successfull_statuses), 1))).label("success_count")
                ).where(condition)
                result = await session.execute(query)
                counts = result.one()
                consider_count = counts.consider_count
                success_count = counts.success_count
            else:
                consider_count = 0
                success_count = 0

            business_dict["total_orders"] = consider_count
            business_dict["successful_orders"] = success_count

            return {
                "status": True,
                "business_info": business_dict,
                "business_translations": translations_list,
                "business_reviews": reviews_list,
            }

        except Exception as e:
            logger.exception("get_business_profile - MAIN EXCEPTION ERROR")  # Полный traceback в логах
            await put_critical_error_into_db(
                "get_business_profile", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id}
            )
            return {
                "status": False,
                "notify_type": "error",
                "notify_code": "notify_error_unknown_error",
                "message": "Internal server error"
            }
    

async def add_reply_for_business_review(user_id : int, business_id : int, comment_id : int, reply_text : str) -> dict:
    async with async_session() as session:
        try:
            user = await session.get(AppUser, user_id)
            if not user:
                await put_critical_error_into_db(
                    "add_reply_for_business_review", "user not found",
                    f"User {user_id} not found", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"User with ID {user_id} not found"
                }

            if not user.active:
                await put_critical_error_into_db(
                    "add_reply_for_business_review", "user is inactive",
                    f"User {user_id} is inactive", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_user_inactive",
                    "message": f"User with ID {user_id} is inactive"
                }
            
            review = await session.get(ReviewBusiness, comment_id)
            if not review:
                await put_critical_error_into_db(
                    "add_reply_for_business_review", "review not found",
                    f"Review {comment_id} not found", {"review_id": comment_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"Review {comment_id} not found"
                }

            if review.banned_by_admin or review.comment == "" or review.reply != "":
                await put_critical_error_into_db(
                    "add_reply_for_business_review", "review cannot be commented",
                    f"Review {comment_id} cannot be commented", {"review_id": comment_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_review_cannot_be_commented",
                    "message": f"Review {comment_id} cannot be commented"
                }
            
            if review.business_id not in user.business_list or review.business_id != business_id:
                await put_critical_error_into_db(
                    "add_reply_for_business_review", "review cannot be commented by this user",
                    f"Review {comment_id} cannot be commented by user {user_id}", {"user_id": user_id, "review_id": comment_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_review_cannot_be_commented_by_you",
                    "message": f"Review {comment_id} cannot be commented by user {user_id}"
                }

            if isinstance(reply_text, str) and len(reply_text) <= MAX_COMMENT_LENGTH:
                review.reply = reply_text
                await session.commit()

                log_data = {
                    "user_id": user_id,
                    "action_type": REPLY,
                    "entity_type": BUSINESS,
                    "entity_id": business_id,
                    "extra_data": {
                        "comment_id": comment_id
                    }
                }

                return { "status": True, "log_data": log_data }
            
            else:
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"Unknown server error"
                }

        except Exception as e:
            logger.exception("add_reply_for_business_review - MAIN EXCEPTION ERROR")  # Полный traceback в логах
            await put_critical_error_into_db(
                "add_reply_for_business_review", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "review_id": comment_id}
            )
            return {
                "status": False,
                "notify_type": "error",
                "notify_code": "notify_error_unknown_error",
                "message": "Internal server error"
            }    


async def business_update(user_id: int, business_id: int, data: dict, avatar: UploadFile | None = None) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).filter(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("business_update", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"business_update: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                
                # Checking business
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True)).with_for_update() 
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"business_update: Business ID {business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"business_update: User {user_id} is not owner for business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {business_id}"}
                
                add_languages = None
                description = None
                address = None
                timezone = None
                geodata = None
                schedule = None
                local_names = None
                currency = None

                try:
                    if business.business_type == INDIVIDUAL:
                        validated = IndividualUpdate(**data)
                        timezone = validated.timezone
                        currency = validated.currency
                        geodata = validated.geodata
                    else:
                        validated = BusinessUpdate(**data)
                        add_languages = validated.add_languages
                        description = validated.description
                        address = validated.address
                        timezone = validated.timezone
                        geodata = validated.geodata
                        schedule = validated.schedule
                        local_names = validated.local_names
                        if local_names is None:
                            local_names = {}
                        if description is None:
                            description = {}
                        if address is None:
                            address = {}
                        if add_languages is None:
                            add_languages = []
                        
                except ValidationError as e:
                    logger.error(f"business_update: Validation data error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Data validation error"}

                # All languages dict
                all_languages = get_languages()

                # Add translations models
                # Expected add_languages format: ["en", "ru"]
                # Expected local_names format: {"en": "English name", "ru": "Русское имя"}
                add_language_error = False
                if isinstance(add_languages, list) and len(add_languages) > 0 and business.business_type != INDIVIDUAL:
                    translations_query = select(BusinessTranslation.language).filter(BusinessTranslation.business_id == business_id)
                    translations_result = await session.execute(translations_query)
                    translations_exists = translations_result.scalars().all()
                    user_translations_limit = ADDITIONAL_LANGUAGES_LIMIT - len(translations_exists)                    
                    for lang in add_languages:
                        if lang not in translations_exists:
                            if user_translations_limit <= 0:
                                add_language_error = True
                                break
                            else:
                                lang_is_exists = any(l.code == lang for l in all_languages)
                                if not lang_is_exists:
                                    add_language_error = True
                                    continue
                                else:
                                    local_bussiness_name = local_names.get(lang, business.name)
                                    new_translation = BusinessTranslation(
                                        business_id = business_id,
                                        name = local_bussiness_name,
                                        language = lang
                                    )
                                    session.add(new_translation)
                                    await session.flush()
                
                # Update description
                # Expected description format: {"en": "English description text", "ru": "Русский вариант описания"}
                update_description_error = False
                if description and business.business_type != INDIVIDUAL:
                    if not isinstance(description, dict):
                        update_description_error = True
                    else:
                        for lang in description:
                            if lang == business.language:
                                if description[lang] and description[lang] != business.description:
                                    business.description = description[lang]
                            else:
                                trans_query = select(BusinessTranslation).filter(BusinessTranslation.business_id == business_id, BusinessTranslation.language == lang)
                                trans_result = await session.execute(trans_query)
                                translation = trans_result.scalars().first()
                                if not translation:
                                    update_description_error = True
                                    continue
                                else:
                                    lang_is_exists = any(l.code == lang for l in all_languages)
                                    if not lang_is_exists:
                                        update_description_error = True
                                        continue
                                    else:
                                        if description[lang] and description[lang] != translation.description:
                                            translation.description = description[lang]
                
                # Update address
                # Expected address format: {"en": "English address text", "ru": "Русский вариант адреса"}
                update_address_error = False
                if address and business.business_type != INDIVIDUAL:
                    if not isinstance(address, dict):
                        update_address_error = True
                    else:
                        for lang in address:
                            if lang == business.language:
                                if address[lang] and address[lang] != business.address:
                                    business.address = address[lang]
                            else:
                                trans_query = select(BusinessTranslation).filter(BusinessTranslation.business_id == business_id, BusinessTranslation.language == lang)
                                trans_result = await session.execute(trans_query)
                                translation = trans_result.scalars().first()
                                if not translation:
                                    update_address_error = True
                                    continue
                                else:
                                    lang_is_exists = any(l.code == lang for l in all_languages)
                                    if not lang_is_exists:
                                        update_address_error = True
                                        continue
                                    else:
                                        if address[lang] and address[lang] != translation.address:
                                            translation.address = address[lang]

                # Update timezone
                # Expected timezone format: String                
                if timezone:                    
                    business.timezone = timezone

                # Update geodata
                # Expected geodata format: {"latitude": Float(6 symbols after point), "longitude": Float(6 symbols after point)}                
                if geodata:
                    geopoint_is_correct = False
                    user_latitude = float(geodata.latitude)
                    user_longitude = float(geodata.longitude)
                    latitude = Decimal(str(user_latitude))
                    longitude = Decimal(str(user_longitude))
                    if not (latitude == Decimal(0) and longitude == Decimal(0)):
                        geopoint_is_correct = True
                    business.latitude = latitude
                    business.longitude = longitude
                    business.geopoint = geopoint_is_correct
                                                    
                # Update schedule                
                if schedule and business.business_type != INDIVIDUAL:
                    if business.schedule != schedule:
                        business.schedule = schedule

                # Update currency (for INDIVIDUAL only)
                if currency and business.business_type == INDIVIDUAL:
                    if business.currency != currency:
                        business.currency = currency

                # Update avatar
                update_avatar_error = False
                update_avatar = False
                if avatar:
                    update_avatar = True
                    filepath=""                
                    filename=f"business_{business_id}"
                    saved_avatar = await save_uploaded_jpeg_business(avatar=avatar, filename=filename)
                    if saved_avatar["status"]:
                        if saved_avatar.get("webp_path"):
                            filepath = saved_avatar.get("webp_path")
                        elif saved_avatar.get("jpeg_path"):
                            filepath = saved_avatar.get("jpeg_path")                        
                        business.avatar_name = filepath
                    else:
                        update_avatar_error = True
                
                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": UPDATE,
                    "entity_type": BUSINESS,
                    "entity_id": business_id,
                    "extra_data": {
                        "update_data": data,
                        "update_avatar": update_avatar,
                        "update_error": {
                            "add_languages": add_language_error,
                            "description": update_description_error,
                            "address": update_address_error,
                            "avatar": update_avatar_error
                        }
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.exception("business_update - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "business_update", "main exception error",
                    f"Error text: {str(e)}", {"data": data}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }    


async def fire_employee(user_id : int, business_id : int, employee_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).filter(AppUser.id == user_id)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("fire_employee", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"fire_employee: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                
                # Checking business
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True)).with_for_update() 
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"fire_employee: Business ID {business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"fire_employee: User {user_id} is not owner for business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {business_id}"}
                
                # Checking employee
                employee_query = select(AppUser).filter(AppUser.id == employee_id).with_for_update()
                employee_result = await session.execute(employee_query)
                employee = employee_result.scalars().first()
                if not employee:
                    await put_critical_error_into_db("fire_employee", "user not found", f"User (employee) {employee_id} not found", {"user_id": employee_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User (employee) with ID {employee_id} not found"}                
                if not employee_id in business.staff:
                    logger.error(f"fire_employee: User (employee) {employee_id} is not in staff of business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_employee_not_in_staff", "message": f"fire_employee: User (employee) {employee_id} is not in staff of business {business_id}"}
                
                # Removing employee
                if business.staff is not None:
                    business.staff[:] = [eid for eid in business.staff if eid != employee_id]
                flag_modified(business, "staff")
                if employee.active_business_id == business_id:
                    employee.active_business_id = 0
                
                employee.outcoming_employer_business_id = 0
                employee.outcoming_employer_business_name = ""
                employee.outcoming_request_delete_date = 0

                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": DELETE,
                    "entity_type": EMPLOYEE,
                    "entity_id": employee_id,
                    "extra_data": {
                        "business_id": business_id
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.exception("fire_employee - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "fire_employee", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id, "employee_id": employee_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }
            

async def confirm_employee(user_id : int, business_id : int, employee_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).filter(AppUser.id == user_id)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("confirm_employee", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"confirm_employee: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                
                # Checking business
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True)).with_for_update() 
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"confirm_employee: Business ID {business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"confirm_employee: User {user_id} is not owner for business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {business_id}"}
                
                # Checking employee
                employee_query = select(AppUser).filter(AppUser.id == employee_id).with_for_update()
                employee_result = await session.execute(employee_query)
                employee = employee_result.scalars().first()
                if not employee:
                    await put_critical_error_into_db("confirm_employee", "user not found", f"User (employee) {employee_id} not found", {"user_id": employee_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User (employee) with ID {employee_id} not found"}
                if not employee.active:
                    logger.error(f"confirm_employee: User (employee) with ID {employee_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_employee_is_not_active_user", "message": f"User (employee) with ID {user_id} is inactive"}
                
                # Confirming employee
                request_is_exist = False
                updated_business_staff_incoming = []
                for app_user in business.staff_incoming:
                    app_user_id = app_user.get("id")
                    if app_user_id != employee_id:
                        updated_business_staff_incoming.append(app_user)
                    else:
                        request_is_exist = True

                if not request_is_exist:
                    logger.error(f"confirm_employee: User (employee) with ID {employee_id} is not in request list", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_employee_is_not_request_list", "message": f"confirm_employee: User (employee) with ID {employee_id} is not in request list"}
                
                business.staff_incoming = updated_business_staff_incoming
                flag_modified(business, "staff_incoming")                
                business.staff.append(employee_id)
                flag_modified(business, "staff")
                employee.active_business_id = business_id                              
                
                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": CONFIRM,
                    "entity_type": EMPLOYEE,
                    "entity_id": employee_id,
                    "extra_data": {
                        "business_id": business_id
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.exception("confirm_employee - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "confirm_employee", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id, "employee_id": employee_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }
            

async def reject_employee(user_id : int, business_id : int, employee_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).filter(AppUser.id == user_id)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("reject_employee", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"reject_employee: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                
                # Checking business
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True)).with_for_update() 
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"reject_employee: Business ID {business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {business_id} not found"}
                if business.owner_id != user_id:
                    logger.error(f"reject_employee: User {user_id} is not owner for business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner for business {business_id}"}
                
                # Checking employee
                employee_query = select(AppUser).filter(AppUser.id == employee_id).with_for_update()
                employee_result = await session.execute(employee_query)
                employee = employee_result.scalars().first()
                if not employee:
                    await put_critical_error_into_db("reject_employee", "user not found", f"User (employee) {employee_id} not found", {"user_id": employee_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User (employee) with ID {employee_id} not found"}                                

                # Rejecting employee
                request_is_exist = False
                updated_business_staff_incoming = []
                for app_user in business.staff_incoming:
                    app_user_id = app_user.get("id")
                    if app_user_id != employee_id:
                        updated_business_staff_incoming.append(app_user)
                    else:
                        request_is_exist = True

                if not request_is_exist:
                    logger.error(f"reject_employee: User (employee) with ID {employee_id} is not in request list", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_employee_is_not_request_list", "message": f"confirm_employee: User (employee) with ID {employee_id} is not in request list"}
                
                business.staff_incoming = updated_business_staff_incoming
                flag_modified(business, "staff_incoming")                
                
                employee.outcoming_employer_business_id = 0
                employee.outcoming_employer_business_name = ""
                employee.outcoming_request_delete_date = 0

                # User action log preparing
                log_data = {
                    "user_id": user_id,
                    "action_type": REJECT,
                    "entity_type": EMPLOYEE,
                    "entity_id": employee_id,
                    "extra_data": {
                        "business_id": business_id
                    }
                }

                return {"status": True, "log_data": log_data}
            
            except Exception as e:
                logger.exception("reject_employee - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "reject_employee", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id, "employee_id": employee_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }
            

async def change_app_settings(user_id : int, changed_settings : dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).filter(AppUser.id == user_id)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("change_app_settingse", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User with ID {user_id} not found"}


                # languge interface
                interface_updated = False
                new_interface = None

                new_language = changed_settings.get("language", None)
                if new_language and new_language != user.language:
                    new_interface = await get_interface(new_language)
                    if new_interface:                        
                        user.language = new_language
                        interface_updated = True                    

                # settings dict                
                if not isinstance(user.settings, dict):
                    user.settings = {}
                    flag_modified(user, "settings")
                
                # bot nitifications
                if "bot_notify_on" in changed_settings:
                    new_value_bot_notify = changed_settings["bot_notify_on"]
                    bot_notify = user.settings.get("bot_notify_on")

                    if bot_notify != new_value_bot_notify:
                        user.settings["bot_notify_on"] = new_value_bot_notify
                        flag_modified(user, "settings")
                
                # camera is priority
                if "is_camera_priority" in changed_settings:
                    new_value_camera_is_priority = changed_settings["is_camera_priority"]
                    camera_is_priority = user.settings.get("is_camera_priority")

                    if camera_is_priority != new_value_camera_is_priority:
                        user.settings["is_camera_priority"] = new_value_camera_is_priority
                        flag_modified(user, "settings")
                
                return {"status": True, "interface_updated": interface_updated, "user_settings": user.settings, "new_interface": new_interface}
            
            except Exception as e:
                logger.exception("change_app_settings - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "change_app_settings", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }



async def change_active_business(user_id : int, business_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).filter(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("change_active_business", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error", "message": f"User with ID {user_id} not found"}
                if not user.active:
                    logger.error(f"change_active_business: User with ID {user_id} is inactive", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_user_inactive", "message": f"User with ID {user_id} is inactive"}
                
                # Checking business
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"change_active_business: Business ID {business_id} not found", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_business_not_found", "message": f"Business ID {business_id} not found"}
                if user_id != business.owner_id and user_id not in (business.staff or []):
                    logger.error(f"change_active_business: User {user_id} is not owner for business {business_id}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error", "message": f"User {user_id} is not owner of staff for business {business_id}"}

                user.active_business_id = business_id
                
                return {"status": True}
            
            except Exception as e:
                logger.exception("cchange_active_business - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "change_active_business", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": "Internal server error"
                }
            

async def join_staff_request_create(user_id : int, business_id : int, employer_id : int | None) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                if user_id == employer_id:
                    logger.info(f"A user cannot hire himself", user_id=user_id)
                    return { "status": False }
                
                user_query = select(AppUser).where(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                business_query = select(Business).where(Business.id == business_id, Business.deleted.is_(False)).with_for_update()
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()

                if business.owner_id == user_id:
                    logger.info(f"A user cannot hire himself in his business", user_id=user_id)
                    return { "status": False }
                
                if not user or not user.active:
                    await put_critical_error_into_db(
                        "join_staff_request_create", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id, "business_id": business_id}
                    )
                    return { "status": False }
                
                if not business or not business.active:
                    logger.error(f"join_staff_request_create - business is not active", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_business_is_not_exist"}
                
                if business.business_type == INDIVIDUAL:
                    logger.info(f"This type of business cannot hire eployees", user_id=user_id)
                    return { "status": False }
                
                if employer_id and business.owner_id != employer_id:
                    logger.error(f"join_staff_request_create - user {employer_id} is not owner for business {business_id}", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                if user.outcoming_employer_business_id != 0 and user.outcoming_employer_business_id != business_id:
                    logger.error(f"join_staff_request_create - user {user_id} has join request now", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_user_has_join_staff_request" }

                is_request_already_exist = False
                for user_s in business.staff_incoming:
                    u_id = user_s.get("id", 0)
                    if u_id ==user_id:
                        is_request_already_exist = True                            

                user_short = {"id": user_id, "username": user.username}
                if not is_request_already_exist:
                    business.staff_incoming.append(user_short)
                    flag_modified(business, "staff_incoming")
                
                user.outcoming_employer_business_id = business_id
                user.outcoming_employer_business_name = business.name
                user.outcoming_request_delete_date = int(datetime.now(timezone.utc).timestamp()) + JOIN_STAFF_REQUEST_UNDELETABLE_PERIOD
                userdata = user.to_dict()
                
                logger.info(f"join_staff_request_create - Success!")                

                return {"status": True, "userdata": userdata}


            except Exception as e:
                logger.exception("join_staff_request_create - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "join_staff_request_create", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id}
                )
                return { "status": False }
            

async def join_staff_request_delete(user_id: int) -> dict:
    business_id = None
    async with async_session() as session:
        async with session.begin():
            try:
                user = (
                    await session.execute(
                        select(AppUser)
                        .where(AppUser.id == user_id)
                        .with_for_update()
                    )
                ).scalars().first()

                if not user or not user.active:
                    await put_critical_error_into_db(
                        "join_staff_request_delete",
                        "incorrect data",
                        "User not found or inactive",
                        {"user_id": user_id}
                    )
                    return {"status": False}

                current_unixtime = int(datetime.now(timezone.utc).timestamp())
                if current_unixtime < user.outcoming_request_delete_date:
                    logger.error(
                        "join_staff_request_delete - cannot delete yet",
                        user_id=user_id
                    )
                    return {
                        "status": False,
                        "notify_type": "error",
                        "notify_code": "notify_error_cannot_do_yet"
                    }

                business_id = user.outcoming_employer_business_id
                if business_id <= 0:
                    logger.error(
                        "join_staff_request_delete - invalid business_id",
                        user_id=user_id,
                        business_id=business_id
                    )
                    return {
                        "status": False,
                        "notify_type": "error",
                        "notify_code": "notify_error_input_error"
                    }

                business = (
                    await session.execute(
                        select(Business)
                        .where(Business.id == business_id)
                        .with_for_update()
                    )
                ).scalars().first()

                if business:
                    updated_staff = []
                    request_is_exist = False

                    for app_user in business.staff_incoming:
                        if app_user.get("id") == user_id:
                            request_is_exist = True
                        else:
                            updated_staff.append(app_user)

                    if request_is_exist:
                        business.staff_incoming = updated_staff
                        flag_modified(business, "staff_incoming")
                    else:
                        logger.error(
                            "join_staff_request_delete - request not found",
                            user_id=user_id
                        )

                user.outcoming_employer_business_id = 0
                user.outcoming_employer_business_name = ""
                user.outcoming_request_delete_date = 0

                userdata = user.to_dict()

                logger.info(
                    "join_staff_request_delete - success",
                    user_id=user_id
                )

                return {"status": True, "userdata": userdata, "business_id": business_id}

            except Exception as e:
                logger.exception("join_staff_request_delete - MAIN EXCEPTION")
                await put_critical_error_into_db(
                    "join_staff_request_delete",
                    "main exception error",
                    str(e),
                    {"user_id": user_id, "business_id": business_id}
                )
                return {"status": False}



async def self_fire_from_active_business(user_id : int, business_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                user_query = select(AppUser).filter(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                business_query = select(Business).filter(Business.id == business_id).with_for_update()
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()

                if not user or not user.active:
                    await put_critical_error_into_db(
                        "self_fire_from_active_business", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id, "business_id": business_id}
                    )
                    return { "status": False }
                
                if not business or not business.active:
                    logger.error(f"self_fire_from_active_business - business is not active", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_business_is_not_exist"}
                
                if user.active_business_id != business_id or user_id not in business.staff:
                    logger.error(f"self_fire_from_active_business - user {user_id} cannot quit from business {business_id}", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}

                if len(user.business_list) > 0:
                    user.active_business_id = user.business_list[0]
                else:
                    user.active_business_id = 0

                user.outcoming_employer_business_id = 0
                user.outcoming_employer_business_name = ""
                user.outcoming_request_delete_date = 0

                business_staff_updated = []
                for st_id in business.staff:
                    if st_id != 0 and st_id != user_id:
                        business_staff_updated.append(st_id)
                
                business.staff = business_staff_updated
                flag_modified(business, "staff")
                
                return {"status": True}

            except Exception as e:
                logger.exception("self_fire_from_active_business - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "self_fire_from_active_business", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id})
                return { "status": False }
            

async def delete_business(user_id : int, business_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                user_query = select(AppUser).filter(AppUser.id == user_id).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                business_query = select(Business).filter(Business.id == business_id).with_for_update()
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                
                if not user or not user.active:
                    await put_critical_error_into_db(
                        "delete_business", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id, "business_id": business_id}
                    )
                    return { "status": False }
                
                if not business or not business.active:
                    logger.error(f"delete_business - business is not active", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_business_is_not_exist"}
                
                if user_id != business.owner_id:
                    logger.error(f"delete_business - user {user_id} is not owner of business {business_id}", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_access_error"}
                

                
                current_orders_exists = await session.scalar(
                    select(
                        exists().where(
                            Order.deleted.is_(False),
                            or_(
                                and_(Order.supplier_id == business_id, Order.status.in_(ORDER_OPENED_STATUSES_SUPPLIER)),
                                and_(Order.customer_id == business_id, Order.status.in_(ORDER_OPENED_STATUSES_CUSTOMER)),
                                and_(Order.individual_id == business_id, Order.status.in_(ORDER_OPENED_STATUSES_CUSTOMER))
                            )
                        )
                    )
                )

                if current_orders_exists:
                    logger.info(f"delete_business - cannot delete business", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_cannot_delete_business_unclosed_orders"}                
                
                ex_staff = business.staff

                employees_query = (
                    select(AppUser)
                    .where(AppUser.id.in_(ex_staff))
                ).with_for_update()

                employees_result = await session.execute(employees_query)
                employees = employees_result.scalars().all()

                business.staff = []
                flag_modified(business, "staff")
                business.active = False
                business.deleted = True

                products_query = (
                    select(Product)
                    .where(Product.business_id == business_id)
                ).with_for_update()
                products_result = await session.execute(products_query)
                products = products_result.scalars().all()

                if products:
                    for product in products:
                        product.deleted = True

                user_business_list = []
                for b_id in user.business_list:
                    if b_id != business_id:
                        user_business_list.append(b_id)
                user.business_list = user_business_list
                flag_modified(user, "business_list")

                if user.active_business_id == business_id:
                    if len(user.business_list) > 0:
                        user.active_business_id = user.business_list[0]
                    else:
                        user.active_business_id = 0
                
                for employee in employees:
                    if employee.active_business_id == business_id:
                        if len(employee.business_list) > 0:
                            employee.active_business_id = employee.business_list[0]
                        else:
                            employee.active_business_id = 0
                    employee.outcoming_employer_business_id = 0
                    employee.outcoming_employer_business_name = ""
                    employee.outcoming_request_delete_date = 0

                return {"status": True, "ex_staff": ex_staff}

            except Exception as e:
                logger.exception("delete_business - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "delete_business", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id})
                return { "status": False }
            

async def change_business_favorite_status(user_id : int, business_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "change_business_favorite_status", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id, "business_id": business_id}
                    )
                    return { "status": False }
                
                if not business:
                    logger.error(f"change_business_favorite_status - business is not active", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_business_is_not_exist"}
                
                if business.owner_id == user_id:
                    logger.error(f"change_business_favorite_status - user is owner this business", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_impossible_add_own_business"}
                
                if not user.favorite_businesses or not isinstance(user.favorite_businesses, list):
                    user.favorite_businesses = []
                    flag_modified(user, "favorite_businesses")

                is_business_favorite = business_id in user.favorite_businesses

                if not is_business_favorite:
                    user.favorite_businesses.append(business_id)
                else:
                    new_favorite_list = []
                    for b_id in user.favorite_businesses:
                        if b_id != business_id:
                            new_favorite_list.append(b_id)
                    user.favorite_businesses = new_favorite_list
                
                flag_modified(user, "favorite_businesses")

                return {"status": True, "new_favorite_businesses": user.favorite_businesses}

            except Exception as e:
                logger.exception("change_business_favorite_status - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "change_business_favorite_status", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "business_id": business_id})
                return { "status": False }
            

async def change_product_favorite_status(user_id : int, product_id : int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                product_query = select(Product).filter(Product.id == product_id, Product.active.is_(True), Product.deleted.is_(False))
                product_result = await session.execute(product_query)
                product = product_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "change_product_favorite_status", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id, "product_id": product_id}
                    )
                    return { "status": False }
                
                if not product:
                    logger.error(f"change_product_favorite_status - product is not active", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_product_is_not_exist"}
                
                business_query = select(Business).filter(Business.id == product.business_id, Business.active.is_(True), Business.deleted.is_(False))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                
                if business.owner_id == user_id:
                    logger.error(f"change_product_favorite_status - user is owner this business", user_id=user_id)
                    return { "status": False, "notify_type": "error", "notify_code": "notify_error_impossible_add_own_product"}
                
                if not user.favorite_products or not isinstance(user.favorite_products, list):
                    user.favorite_products = []
                    flag_modified(user, "favorite_products")

                is_product_favorite = product_id in user.favorite_products

                if not is_product_favorite:
                    user.favorite_products.append(product_id)
                else:
                    new_favorite_list = []
                    for p_id in user.favorite_products:
                        if p_id != product_id:
                            new_favorite_list.append(p_id)
                    user.favorite_products = new_favorite_list
                
                flag_modified(user, "favorite_products")

                return {"status": True, "new_favorite_products": user.favorite_products}

            except Exception as e:
                logger.exception("change_product_favorite_status - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "change_product_favorite_status", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "product_id": product_id})
                return { "status": False }
            

async def add_reply_for_product_review(user_id : int, product_id : int, comment_id : int, reply_text : str) -> dict:
    async with async_session() as session:
        try:
            user = await session.get(AppUser, user_id)
            if not user:
                await add_reply_for_product_review(
                    "add_reply_for_business_review", "user not found",
                    f"User {user_id} not found", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"User with ID {user_id} not found"
                }

            if not user.active:
                await put_critical_error_into_db(
                    "add_reply_for_business_review", "user is inactive",
                    f"User {user_id} is inactive", {"user_id": user_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_user_inactive",
                    "message": f"User with ID {user_id} is inactive"
                }
            
            review = await session.get(ReviewProduct, comment_id)
            if not review:
                await put_critical_error_into_db(
                    "add_reply_for_product_review", "review not found",
                    f"Review {comment_id} not found", {"review_id": comment_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"Review {comment_id} not found"
                }

            if review.banned_by_admin or review.comment == "" or review.reply != "":
                await put_critical_error_into_db(
                    "add_reply_for_product_review", "review cannot be commented",
                    f"Review {comment_id} cannot be commented", {"review_id": comment_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_review_cannot_be_commented",
                    "message": f"Review {comment_id} cannot be commented"
                }
            
            if review.business_id not in user.business_list:
                await put_critical_error_into_db(
                    "add_reply_for_product_review", "review cannot be commented by this user",
                    f"Review {comment_id} cannot be commented by user {user_id}", {"user_id": user_id, "review_id": comment_id}
                )
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_review_cannot_be_commented_by_you",
                    "message": f"Review {comment_id} cannot be commented by user {user_id}"
                }

            if isinstance(reply_text, str) and len(reply_text) <= MAX_COMMENT_LENGTH:
                review.reply = reply_text
                await session.commit()

                log_data = {
                    "user_id": user_id,
                    "action_type": REPLY,
                    "entity_type": PRODUCT,
                    "entity_id": product_id,
                    "extra_data": {
                        "comment_id": comment_id
                    }
                }

                updated_review = review.to_dict()

                return { "status": True, "log_data": log_data, "updated_review": updated_review }
            
            else:
                return {
                    "status": False,
                    "notify_type": "error",
                    "notify_code": "notify_error_unknown_error",
                    "message": f"Unknown server error"
                }

        except Exception as e:
            logger.exception("add_reply_for_product_review - MAIN EXCEPTION ERROR")  # Полный traceback в логах
            await put_critical_error_into_db(
                "add_reply_for_product_review", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "review_id": comment_id}
            )
            return {
                "status": False,
                "notify_type": "error",
                "notify_code": "notify_error_unknown_error",
                "message": "Internal server error"
            }
        

async def set_filters_supplier_catalog(user_id: int, filter_settings: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "set_filters_supplier_catalog", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                
                if not isinstance(filter_settings, dict):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid settings data"}
                
                if not isinstance(user.settings, dict):
                    user.settings = {}
                
                user.settings["filters_supplier_catalog"] = filter_settings
                
                flag_modified(user, "settings")

                return {"status": True}

            except Exception as e:
                logger.exception("set_filters_supplier_catalog - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "set_filters_supplier_catalog", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def set_filters_customer_catalog(user_id: int, filter_settings: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "set_filters_customer_catalog", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                
                business_id = user.active_business_id
                if not business_id:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"User's active business is incorrect"}

                business_id_str = str(business_id)

                if not isinstance(user.settings, dict):
                    user.settings = {}

                if not user.settings.get("filters_customer_catalog") or not isinstance(user.settings.get("filters_customer_catalog"), dict):
                    user.settings["filters_customer_catalog"] = {}
                
                try:
                    validated = CustomerProductCatalogFilters(**filter_settings)
                except ValidationError as e:
                    logger.error(f"set_filters_customer_catalog: Validation data error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Data validation error"}
                
                user.settings["filters_customer_catalog"][business_id_str] = validated.model_dump()                                
                
                flag_modified(user, "settings")

                return {"status": True}

            except Exception as e:
                logger.exception("set_filters_customer_catalog - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "set_filters_customer_catalog", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def set_filters_individual_catalog(user_id: int, filter_settings: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "set_filters_individual_catalog", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }

                business_id = user.active_business_id
                if not business_id:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"User's active business is incorrect"}

                business_id_str = str(business_id)
                
                if not isinstance(filter_settings, dict):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid settings data"}
                
                if not isinstance(user.settings, dict):
                    user.settings = {}

                if not user.settings.get("filters_individual_catalog") or not isinstance(user.settings.get("filters_individual_catalog"), dict):
                    user.settings["filters_individual_catalog"] = {}
                
                try:
                    validated = IndividualProductCatalogFilters(**filter_settings)
                except ValidationError as e:
                    logger.error(f"set_filters_individual_catalog: Validation data error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Data validation error"}
                
                user.settings["filters_individual_catalog"][business_id_str] = validated.model_dump()                
                
                flag_modified(user, "settings")

                return {"status": True}

            except Exception as e:
                logger.exception("set_filters_individual_catalog - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "set_filters_individual_catalog", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def set_filters_counter_agents_serach(user_id: int, filter_settings: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "set_filters_counter_agents_serach", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                
                if not isinstance(filter_settings, dict):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid settings data"}
                
                business_id = user.active_business_id
                if not business_id:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"User's active business is incorrect"}
                
                business_id_str = str(business_id)
                
                if not isinstance(user.settings, dict):
                    user.settings = {}

                if not user.settings.get("filters_counteragent_search") or not isinstance(user.settings.get("filters_counteragent_search"), dict):
                    user.settings["filters_counteragent_search"] = {}
                
                try:
                    validated = CounterAgentSearchFilters(**filter_settings)
                except ValidationError as e:
                    logger.error(f"set_filters_counter_agents_serach: Validation data error: {e}", user_id=user_id)
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Data validation error"}
                
                user.settings["filters_counteragent_search"][business_id_str] = validated.model_dump()                
                
                flag_modified(user, "settings")

                return {"status": True}

            except Exception as e:
                logger.exception("set_filters_counter_agents_serach - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "set_filters_counter_agents_serach", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def set_filters_business_messages(user_id: int, business_id: int, filter_settings: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "set_filters_business_messages", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }

                if not business_id or user.active_business_id != business_id:
                    logger.error(f"set_filters_business_messages - user active business is not {business_id}")
                    return { "status": False }
                
                if not isinstance(filter_settings, dict):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid settings data"}
                
                if not isinstance(user.settings, dict):
                    user.settings = {}
                                
                if not isinstance(user.settings.get("filters_business_messages"), dict):
                    user.settings["filters_business_messages"] = {}
                
                user.settings["filters_business_messages"][str(business_id)] = filter_settings
                
                flag_modified(user, "settings")

                return {"status": True}

            except Exception as e:
                logger.exception("set_filters_business_messages - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "set_filters_business_messages", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def set_filters_business_orders(user_id: int, business_id: int, filter_settings: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "set_filters_business_orders", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }

                if not business_id or user.active_business_id != business_id:
                    logger.error(f"set_filters_business_orders - user active business is not {business_id}")
                    return { "status": False }
                
                if not isinstance(filter_settings, dict):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error", "message": f"Invalid settings data"}
                
                if not isinstance(user.settings, dict):
                    user.settings = {}
                                
                if not isinstance(user.settings.get("filters_business_orders"), dict):
                    user.settings["filters_business_orders"] = {}
                
                user.settings["filters_business_orders"][str(business_id)] = filter_settings
                
                flag_modified(user, "settings")

                return {"status": True}

            except Exception as e:
                logger.exception("set_filters_business_orders - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "set_filters_business_orders", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def get_counter_agent_businesses_bundle(user_id: int, bundle: int) -> dict:
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_counter_agent_businesses_bundle", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            if not user.active_business_id:
                logger.error(f"get_counter_agent_businesses_bundle - User has not active business", user_id=user_id)
                return {"status": False}
            business_id = user.active_business_id
            business = (
                await session.execute(select(Business).where(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False)))).scalars().first()
            if not business:
                logger.error(f"get_counter_agent_businesses_bundle - User's business not found", user_id=user_id)
                return {"status": False}
            
            searching_business_type = None
            if business.business_type == SUPPLIER:
                searching_business_type = CUSTOMER
            elif business.business_type == CUSTOMER or business.business_type == INDIVIDUAL:
                searching_business_type = SUPPLIER
            if not searching_business_type:
                logger.error(f"get_counter_agent_businesses_bundle - Business type for search is not determinated", user_id=user_id)
                return {"status": False}

            business_id_str_key = str(business_id)
            default_filter = SEARCH_COUNTER_AGENT_FILTERS
            user_settings = getattr(user, "settings", {})
            user_filter_search = user_settings.get("filters_counteragent_search", {})
            user_filter = user_filter_search.get(business_id_str_key, None)
            if user_filter is None or not isinstance(user_filter, dict):
                user_filter = default_filter

            user_currency = business.currency

            current_time_unix = int(datetime.now(timezone.utc).timestamp())

            promoted_businesses_query = (
                select(AdCampaignBusinessPromo.business_id, AdCampaignBusinessPromo.daily_credits)
                .join(
                    Business,
                    AdCampaignBusinessPromo.business_id == Business.id
                )
                .where(
                    Business.currency == user_currency,
                    AdCampaignBusinessPromo.active.is_(True),
                    AdCampaignBusinessPromo.deleted.is_(False),
                    and_(AdCampaignBusinessPromo.date_start <= current_time_unix, AdCampaignBusinessPromo.date_end >= current_time_unix)
                )
            )
            promoted_businesses = (await session.execute(promoted_businesses_query)).mappings().all()

            promoted_businesses_ids = []
            promoted_businesses_daily_credits = {}
            for row in promoted_businesses:
                promoted_businesses_daily_credits[row['business_id']] = row['daily_credits']
                promoted_businesses_ids.append(row['business_id'])

            favorite_businesses_ids = user.favorite_businesses
            if not isinstance(favorite_businesses_ids, list):
                favorite_businesses_ids = []

            filter_keyword = user_filter.get("keyword", "")
            filter_hide_without_geodata = user_filter.get("hide_without_geodata", True)
            filter_search_radius_km = user_filter.get("search_radius_km", DEFAULT_SEARCH_RADIUS_KM)
            filter_only_favorite_businesses = user_filter.get("only_favorite_businesses", False)

            if not bundle or not isinstance(bundle, int) or bundle < 0:
                bundle_id = 1
            else:
                bundle_id = bundle
            
            bundle_size = SEARCH_COUNTER_AGENT_BUNDLE_SIZE            

            counter_agents_list = []
            counter_agents_total_count = 0

            filters = [
                Business.active.is_(True), # Всегда
                Business.deleted.is_(False), # Всегда
                Business.currency == user_currency, # Всегда
                Business.id != business_id, # Всегда
                Business.business_type == searching_business_type
            ]

            if filter_keyword:
                business_ids_keyword_query = (
                    select(Business.id)
                    .where(Business.active.is_(True), Business.deleted.is_(False), Business.name.ilike(f"%{filter_keyword}%"))
                    .union(
                        select(BusinessTranslation.business_id.label('id'))
                        .join(Business, Business.id == BusinessTranslation.business_id)
                        .where(Business.active.is_(True), Business.deleted.is_(False), BusinessTranslation.name.ilike(f"%{filter_keyword}%"))
                    )
                )
                business_ids_keyword_query_result = await session.execute(business_ids_keyword_query)
                keyword_business_ids = list(set(business_ids_keyword_query_result.scalars().all()))  # unique через set/list
                if keyword_business_ids:
                    filters.append(Business.id.in_(keyword_business_ids))
                else:
                    return {"status": True, "counter_agents_list": counter_agents_list, "counter_agents_total_count": counter_agents_total_count, "bundle_id": 0}
            
            if filter_hide_without_geodata and business.geopoint:
                allowance_km_radius = max(filter_search_radius_km, MINIMAL_SEARCH_RADIUS_KM)
                km_per_degree_lat = AVERAGE_KM_PER_DEGREE_LAT  # 111.2
                km_per_degree_lon = EQUATOR_KM_PER_DEGREE_LON * math.cos(math.radians(float(business.latitude)))  # float для Decimal
                lat_allowance_degree = Decimal(allowance_km_radius / km_per_degree_lat)
                lon_allowance_degree = Decimal(allowance_km_radius / km_per_degree_lon)
                min_target_latitude = business.latitude - lat_allowance_degree
                max_target_latitude = business.latitude + lat_allowance_degree
                min_target_longitude = business.longitude - lon_allowance_degree
                max_target_longitude = business.longitude + lon_allowance_degree
                # Простой clamp 
                min_target_latitude = max(min_target_latitude, Decimal(MIN_LATITUDE))
                max_target_latitude = min(max_target_latitude, Decimal(MAX_LATITUDE))
                min_target_longitude = max(min_target_longitude, Decimal(MIN_LONGITUDE))
                max_target_longitude = min(max_target_longitude, Decimal(MAX_LONGITUDE))

                business_ids_geodata_query = select(Business.id).where(
                    Business.active.is_(True),
                    Business.deleted.is_(False),                    
                    Business.geopoint.is_(True),
                    Business.latitude.between(min_target_latitude, max_target_latitude),
                    Business.longitude.between(min_target_longitude, max_target_longitude)
                )
                business_ids_geodata_query_result = await session.execute(business_ids_geodata_query)
                geodata_business_ids = business_ids_geodata_query_result.scalars().all()
                if geodata_business_ids:
                    filters.append(Business.id.in_(geodata_business_ids))
                else:
                    return {"status": True, "counter_agents_list": counter_agents_list, "counter_agents_total_count": counter_agents_total_count, "bundle_id": 0}
                        
            if filter_only_favorite_businesses:
                if not favorite_businesses_ids:
                    return {"status": True, "counter_agents_list": counter_agents_list, "counter_agents_total_count": counter_agents_total_count, "bundle_id": 0}
                else:
                    filters.append(Business.id.in_(favorite_businesses_ids))

            all_businesses_ids_pre_query = select(Business.id)
            if filters:
                all_businesses_ids_pre_query = all_businesses_ids_pre_query.where(and_(*filters))
            result_all_businesses_ids_pre_query = await session.execute(all_businesses_ids_pre_query)
            all_businesses_ids_form_pre_query = result_all_businesses_ids_pre_query.scalars().all()

            if not all_businesses_ids_form_pre_query:
                return {"status": True, "counter_agents_list": counter_agents_list, "counter_agents_total_count": counter_agents_total_count, "bundle_id": 0}

            favorite_ids_set = set(favorite_businesses_ids)
            promoted_ids_set = set(promoted_businesses_ids)

            sorted_business_ids = sorted(
                all_businesses_ids_form_pre_query,
                key=lambda business_id: (
                    # 1. promoted + favorite
                    not (
                        business_id in promoted_ids_set
                        and business_id in favorite_ids_set
                    ),
                    # 2. promoted
                    not (business_id in promoted_ids_set),
                    # 3. favorite
                    not (business_id in favorite_ids_set),
                    # 4. daily credits DESC
                    -promoted_businesses_daily_credits.get(business_id, 0),
                    # 5. business_id ASC
                    business_id
                )
            )

            counter_agents_total_count = len(sorted_business_ids)
            offset = (bundle_id - 1) * bundle_size

            if offset >= counter_agents_total_count:
                bundle_id = math.ceil(counter_agents_total_count / bundle_size)
                offset = (bundle_id - 1) * bundle_size

            bundle_ids = sorted_business_ids[offset:offset + bundle_size]

            businesses_bundle = (
                await session.execute(
                    select(Business).where(Business.id.in_(bundle_ids))
                )
            ).scalars().all()

            business_names_local = (await session.execute(
                select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                .where(BusinessTranslation.business_id.in_(bundle_ids))
            )).mappings().all()
            translations = {}
            for row in business_names_local:
                business_id = row["business_id"]
                language = row["language"]
                name = row["name"]
                if business_id not in translations:
                    translations[business_id] = {}
                translations[business_id][language] = name
            
                        
            businesses_bundle_dict = {}            
            for b in businesses_bundle:
                business_dict = b.to_dict()
                if business.geopoint and b.geopoint:
                    point_1 = {
                        "latitude": business.latitude,
                        "longitude": business.longitude,
                    }
                    point_2 = {
                        "latitude": b.latitude,
                        "longitude": b.longitude,
                    }
                    distance = calculate_distance_km(point_1, point_2)
                    if distance:
                        distance = str(distance)
                else:
                    distance = None
                business_dict["distance"] = distance
                business_dict["promoted"] = b.id in promoted_ids_set
                business_dict["favorite"] = b.id in favorite_ids_set
                local_names = translations.get(b.id, {})
                business_dict["local_names"] = local_names
                business_dict["rating"] = 0
                business_dict["rating_count"] = 0
                businesses_bundle_dict[b.id] = business_dict

            
            ratings = (await session.execute(
                    select(
                        ReviewBusiness.business_id,
                        func.avg(ReviewBusiness.rate).label('average'),
                        func.count(ReviewBusiness.rate).label('count')
                    ).where(
                        ReviewBusiness.business_id.in_(bundle_ids),
                        ReviewBusiness.banned_by_admin.is_(False),
                        ReviewBusiness.rate != 0,
                        ReviewBusiness.rate.between(MIN_RATE, MAX_RATE)
                    ).group_by(ReviewBusiness.business_id)
                )).all()

            for row in ratings:
                business_id, average, count = row
                if count > 0:                    
                    if business_id in businesses_bundle_dict:
                        businesses_bundle_dict[business_id]["rating"] = float(round(average or 0, 1))
                        businesses_bundle_dict[business_id]["rating_count"] = count

            
            for b_id in bundle_ids:
                b_dict = businesses_bundle_dict.get(b_id, None)
                if b_dict:
                    counter_agents_list.append(b_dict)                    
            
            return {
                "status": True, 
                "counter_agents_list": counter_agents_list, 
                "counter_agents_total_count": counter_agents_total_count, 
                "bundle_id": bundle_id
            }
        
        except Exception as e:
            logger.exception("get_counter_agent_businesses_bundle - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "get_counter_agent_businesses_bundle", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "bundle": bundle})
            return { "status": False }
        

async def add_user_phone_number(user_id: int, verified_contact: dict, json_contact: dict) -> dict:
    async with async_session() as session:
        try:            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("add_user_phone_number", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            if not user.active_business_id:
                logger.error(f"add_user_phone_number - User has not active business", user_id=user_id)
                return {"status": False}

            phone_number = verified_contact.get("phone_number", None)
            data_is_correct = ((verified_contact.get("user_id") == json_contact.get("user_id") and verified_contact.get("user_id") == user.tg_id) and 
                               (phone_number and phone_number == json_contact.get("phone_number")) and
                               isinstance(phone_number, str)
                            )
                        
            if not data_is_correct:
                logger.error(f"add_user_phone_number - Incorrect data", user_id=user_id)
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_incorrect_data"}            
            
            user_is_exist = (await session.execute(select(AppUser).where(AppUser.phone == phone_number))).scalars().first()
            if user_is_exist:
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_phone_is_already_exist"}
            
            user.phone = phone_number
            user.is_phone_verified = True
            await session.commit()

            return {
                "status": True, 
                "phone_number": phone_number
            }
        
        except Exception as e:
            logger.exception("add_user_phone_number - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "add_user_phone_number", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def get_user_public_profile(user_id: int, getting_user_id: int) -> dict:
    async with async_session() as session:
        try:
            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_user_public_profile", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
            if not user.active_business_id:
                logger.error(f"get_user_public_profile - User has not active business", user_id=user_id)
                return {"status": False}
            
            getting_user = (await session.execute(select(AppUser).where(AppUser.id == getting_user_id, AppUser.active.is_(True)))).scalars().first()
            if not getting_user:                
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_public_userinfo_not_found"}
            
            user_profile = {
                "id": getting_user.id,
                "username": getting_user.username,
                "reg_date": getting_user.reg_date,
                "last_activity": getting_user.last_activity
            }

            return {
                "status": True, 
                "user_profile": user_profile
            }
        
        except Exception as e:
            logger.exception("add_user_phone_number - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "add_user_phone_number", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def change_user_username(user_id: int, username_data: dict) -> dict:
    async with async_session() as session:
        try:
            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("change_user_username", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}            
                        
            if not isinstance(username_data, dict):
                logger.error(f"change_user_username - Incorrect data", user_id=user_id)
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_incorrect_data"}
            
            updating_user_id = username_data.get("user_id", None)
            updating_username = username_data.get("username", None)

            if not isinstance(updating_user_id, int) or not isinstance(updating_username, str) or updating_user_id <= 0 or not updating_username:
                logger.error(f"change_user_username - Incorrect data", user_id=user_id)
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_incorrect_data"}
            
            updating_username = updating_username.strip()[:STRING_LENGTH_255]

            if updating_user_id == user_id:
                user.username = updating_username
            else:
                if not isinstance(user.dict_of_username, dict):
                    user.dict_of_username = {}
                user.dict_of_username[str(updating_user_id)] = updating_username
                flag_modified(user, 'dict_of_username')
            await session.commit()

            updated_username = {
                "user_id": updating_user_id,
                "username": updating_username                
            }

            return {
                "status": True, 
                "updated_username": updated_username
            }
        
        except Exception as e:
            logger.exception("change_user_username - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "change_user_username", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def update_referral_list(user_id: int) -> dict:
    async with async_session() as session:
        try:
            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("update_referral_list", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
                        
            referral_list = []
            referral_ids = user.referrals

            if not referral_ids:
                return {"status": True, "referral_list": referral_list}
            
            referrals = (
                await session.execute(select(AppUser).where(
                    AppUser.id.in_(referral_ids), 
                    AppUser.active.is_(True)
                ))
            ).scalars().all()
            
            for referral in referrals:
                ref_data = {
                    "id": referral.id,
                    "username": referral.username
                }
                referral_list.append(ref_data)

            return {
                "status": True, 
                "referral_list": referral_list
            }
        
        except Exception as e:
            logger.exception("update_referral_list - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "update_referral_list", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }
        

async def set_user_profile_notify_off(user_id: int) -> dict:
    async with async_session() as session:
        try:            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("set_user_profile_notify_off", "user not found", f"User {user_id} not found", {"user_id": user_id})
                return {"status": False}
                        
            if not isinstance(user.tab_notify, dict):
                user.tab_notify = {}

            user.tab_notify[TAB_USER_PROFILE] = False
            flag_modified(user, "tab_notify")

            await session.commit()

            return {
                "status": True, 
                "updated_tab_notify": user.tab_notify
            }
        
        except Exception as e:
            logger.exception("set_user_profile_notify_off - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "set_user_profile_notify_off", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return { "status": False }