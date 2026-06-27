from sqlalchemy import select, or_
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone

from ..models.busineses import Business
from ..models.products import Product
from ..models.finances import TariffPlan

from ..rabbit.celery_rabbit_sender import broadcast_message, send_direct_message

from ..constants.system_log import *
from ..constants.ad_campaign import *
from ..constants.tariff import *
from ..constants.business_types import *

from ..session_config import sync_session

from ..logger_config import get_logger
logger = get_logger(__name__)

from ..config import settings
THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME
API_SERVICE_NAME = settings.API_SERVICE_NAME

from .error import put_critical_error_into_db
from .system_action import put_system_action_into_db_log

def check_businesses_paid_subscriptions():
    try:        
        current_time_unix = int(datetime.now(timezone.utc).timestamp())

        with sync_session() as session:
            with session.begin():
                business_ids = session.execute(
                    select(Business.id).where(
                        Business.tariff != TARIFF_FREE,
                        Business.end_tariff_date < current_time_unix,
                        Business.active.is_(True),
                        Business.deleted.is_(False)
                    )
                ).scalars().all()

        if not business_ids:
            print(f"=============================================================================================")
            print(f"======== check_businesses_paid_subscriptions - no business IDs ==============================")
            print(f"=============================================================================================")

        if business_ids:
            print(f"=============================================================================================")
            print(f"check_businesses_paid_subscriptions: {business_ids}")
            print(f"=============================================================================================")
            successful_changed_free_tariff_plan_businesses_ids = []
            interested_users = []
            for business_id in business_ids:
                set_free = set_business_free_tariff_plan(business_id)
                if set_free.get("status"):
                    successful_changed_free_tariff_plan_businesses_ids.append(business_id)
                    user_ids = set_free.get("interested_users", [])
                    interested_users = list(set(interested_users + user_ids))

            if successful_changed_free_tariff_plan_businesses_ids:
                message = {
                    "sender": THIS_SERVICE_NAME,
                    "receiver": API_SERVICE_NAME,
                    "receiver_id": "all",
                    "message": { 
                        "type": "push_notification",
                        "description": "business_tariff_plan_changed_to_free",
                        "business_ids": successful_changed_free_tariff_plan_businesses_ids,
                        "interested_users": interested_users
                    }
                }            
                broadcast_message(message=message)

    except Exception as e:
        logger.exception(f"DEF check_businesses_paid_subscriptions - Exception: {e}")
        put_critical_error_into_db( "check_businesses_paid_subscriptions", "main exception error", f"Error text: {str(e)}", {})        


def set_business_free_tariff_plan(business_id: int):
    try:
        timestart_float = datetime.now(timezone.utc).timestamp()
        event = EVENT_CHANGE_BUSINESS_TARIFF_PLAN_TO_FREE
        status = SYSTEM_ACTION_STATUS_UNDEFINED
        description = ""
        meta_json = {"business_id": business_id}        
        current_time_unix = int(timestart_float)
        interested_users = []

        with sync_session() as session:
            with session.begin():
                business = session.execute(select(Business).where(
                    Business.id == business_id,
                    Business.tariff != TARIFF_FREE,
                    Business.end_tariff_date < current_time_unix,
                    Business.active.is_(True),
                    Business.deleted.is_(False)
                ).with_for_update()).scalars().first()
                if not business:
                    raise ValueError(f"Business {business_id} not found or not meet the required parameters")
                
                tariff_free = session.execute(select(TariffPlan).where(TariffPlan.slug == TARIFF_FREE, TariffPlan.active.is_(True))).scalars().first()
                if not tariff_free:
                    raise ValueError(f"Tariff plan {TARIFF_FREE} not found or inactive")                
                tariff_features = getattr(tariff_free, "features")
                if not isinstance(tariff_features, dict):
                    tariff_features = {}

                business_type_features = {}
                if business.business_type == SUPPLIER:
                    business_type_features = tariff_features.get("supplier", {})
                    product_catalog_limit = business_type_features.get("product_catalog_limit", DEFAULT_FREE_TARIFF_SUPPLIER_PRODUCT_CATALOG_LIMIT)

                    business_products = session.execute(select(Product).where(
                        Product.business_id == business_id,
                        Product.active.is_(True),
                        Product.deleted.is_(False)
                    ).order_by(Product.id).with_for_update()).scalars().all()

                    if len(business_products) > product_catalog_limit:
                        index = 0
                        for product in business_products:
                            if index >= product_catalog_limit:
                                product.active = False
                            index += 1

                elif business.business_type == CUSTOMER:
                    business_type_features = tariff_features.get("customer", {})
                    # Future logic for change customer's tariff plan to TARIFF_FREE

                elif business.business_type == INDIVIDUAL:
                    business_type_features = tariff_features.get("individual", {})
                    # Future logic for change individual's tariff plan to TARIFF_FREE

                business.tariff = TARIFF_FREE
                business.end_tariff_date = 0

                business_staff = business.staff
                if not isinstance(business_staff, list):
                    business_staff = []
                interested_users = [business.owner_id] + business_staff

        status = SYSTEM_ACTION_STATUS_SUCCESS        
        print(f"=============================================================================================")
        print(f"========================== set_business_free_tariff_plan ====================================")
        print(f"interested_users: {interested_users}")
        return {"status": True, "interested_users": interested_users}

    except Exception as e:
        logger.exception(f"DEF set_business_free_tariff_plan - Exception: {e}")
        put_critical_error_into_db( "set_business_free_tariff_plan", "main exception error", f"Error text: {str(e)}", {})
        status = SYSTEM_ACTION_STATUS_ERROR
        return {"status": False}

    finally:
        timeend_float = datetime.now(timezone.utc).timestamp()
        duration = timeend_float - timestart_float
        put_system_action_into_db_log(event=event, status=status, description=description, meta_json=meta_json, duration=duration)
             


