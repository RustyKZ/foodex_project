from models.finances import TariffPlan
from models.app_users import AppUser
from models.busineses import Business

from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from config import get_settings
settings = get_settings()

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from .error import put_critical_error_into_db

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta

from constants.default import ONE_DAY_SECONDS
from constants.tariff import DURATION_DAY, DURATION_MONTH, DURATION_YEAR, TARIFF_FREE
from constants.log_entitys import TARIFF, CHANGE, RENEW

async def get_tariff_list() -> list:
    async with async_session() as session:
        try:
            query = select(TariffPlan).filter(TariffPlan.active == True)
            result = await session.execute(query)
            tariffs = result.scalars().all()            
            tariff_list = []
            for tariff in tariffs:
                tariff_list.append(tariff.to_dict())
            return tariff_list
        except SQLAlchemyError as e:
            logger.error(f"get_tariff_list - Exception SQLAlchemyError: {e}")
            return []
        except Exception as e:
            logger.error(f"get_tariff_list - Exception SQLAlchemyError: {e}")
            return []
        

async def change_tariff_plan(user_id: int, business_id: int, tariff_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()                
                if not user:
                    await put_critical_error_into_db(
                        "change_tariff_plan", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                                                
                business = (
                    await session.execute(select(Business).
                        where(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False)).with_for_update()
                    )
                ).scalars().first()
                if not business:
                    logger.error(f"change_tariff_plan - business {business_id} not found")
                    return { "status": False }
                if business.owner_id != user_id:
                    logger.error(f"change_tariff_plan - user {user_id} is not owner of  business {business_id}")
                    return { "status": False }
                
                tariff_slug = tariff_data.get("tariff_slug")
                tariff = (
                    await session.execute(select(TariffPlan).
                        where(TariffPlan.slug == tariff_slug, TariffPlan.active.is_(True))
                    )
                ).scalars().first()
                if not tariff:
                    logger.error(f"change_tariff_plan - tariff plan {tariff_slug} not found")
                    return { "status": False }
                
                duration = tariff_data.get("duration")
                if duration not in [DURATION_DAY, DURATION_MONTH, DURATION_YEAR] and not tariff_slug == TARIFF_FREE:
                    logger.error(f"change_tariff_plan - duration {duration} is incorrect")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                tariff_cost = Decimal("0")
                if tariff_slug != TARIFF_FREE:
                    user_common_funds = user.credits + user.referral_bonus
                    tariff_cost = tariff.year_cost
                    if duration == DURATION_DAY:
                        tariff_cost = tariff.day_cost
                    elif duration == DURATION_MONTH:
                        tariff_cost = tariff.month_cost
                
                    if tariff_cost > user_common_funds:
                        logger.error(f"change_tariff_plan - not enough funds for apply selected tariff plan")
                        return {"status": False, "notify_type": "error", "notify_code": "notify_error_not_enough_funds"}

                    if user.referral_bonus >= tariff_cost:
                        user.referral_bonus -= tariff_cost
                    else:
                        tariff_cost_copy = tariff_cost
                        tariff_cost_copy -= user.referral_bonus
                        user.credits -= tariff_cost_copy
                        user.referral_bonus = Decimal("0")

                    current_time_unix = int(datetime.now(timezone.utc).timestamp())
                    business.tariff = tariff_slug
                    business.end_tariff_date = current_time_unix + (ONE_DAY_SECONDS * duration)                
                else:
                    business.tariff = tariff_slug
                    business.end_tariff_date = 0
                    

                update_info = {
                    "user_credits": str(user.credits),
                    "user_referral_bonus": str(user.referral_bonus),
                    "business_id": business.id,
                    "business_tariff": business.tariff,
                    "business_end_tariff_date": business.end_tariff_date
                }
                
                log_data = {
                    "user_id": user_id,
                    "action_type": CHANGE,
                    "entity_type": TARIFF,
                    "entity_id": tariff.id,
                    "extra_data": {
                        "business_id": business_id,
                        "tariff_slug": tariff.slug,
                        "tariff_days": duration,
                        "tariff_cost": str(tariff_cost)
                    }
                }

                return {"status": True, "update_info": update_info, "log_data": log_data}

            except Exception as e:
                logger.exception("change_tariff_plan - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "change_tariff_plan", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def renew_tariff_plan(user_id: int, business_id: int, tariff_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()                
                if not user:
                    await put_critical_error_into_db(
                        "renew_tariff_plan", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                                                
                business = (
                    await session.execute(select(Business).
                        where(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False)).with_for_update()
                    )
                ).scalars().first()
                if not business:
                    logger.error(f"renew_tariff_plan - business {business_id} not found")
                    return { "status": False }
                if business.owner_id != user_id:
                    logger.error(f"renew_tariff_plan - user {user_id} is not owner of  business {business_id}")
                    return { "status": False }
                
                tariff_slug = business.tariff
                if tariff_slug == TARIFF_FREE:
                    logger.error(f"renew_tariff_plan - Current tariff plan can not be renew")
                    return { "status": False }
                
                tariff = (
                    await session.execute(select(TariffPlan).
                        where(TariffPlan.slug == tariff_slug, TariffPlan.active.is_(True))
                    )
                ).scalars().first()
                if not tariff:
                    logger.error(f"renew_tariff_plan - tariff plan {tariff_slug} not found")
                    return { "status": False }
                                                
                duration = tariff_data.get("duration")
                if duration not in [DURATION_DAY, DURATION_MONTH, DURATION_YEAR]:
                    logger.error(f"renew_tariff_plan - duration {duration} is incorrect")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                user_common_funds = user.credits + user.referral_bonus
                tariff_cost = tariff.year_cost
                if duration == DURATION_DAY:
                    tariff_cost = tariff.day_cost
                elif duration == DURATION_MONTH:
                    tariff_cost = tariff.month_cost
                
                if tariff_cost > user_common_funds:
                    logger.error(f"renew_tariff_plan - not enough funds for apply selected tariff plan")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_not_enough_funds"}

                if user.referral_bonus >= tariff_cost:
                    user.referral_bonus -= tariff_cost
                else:
                    tariff_cost_copy = tariff_cost
                    tariff_cost_copy -= user.referral_bonus
                    user.credits -= tariff_cost_copy
                    user.referral_bonus = Decimal("0")

                current_time_unix = int(datetime.now(timezone.utc).timestamp())                
                if current_time_unix > business.end_tariff_date:
                    business.end_tariff_date = current_time_unix + (ONE_DAY_SECONDS * duration)
                else:
                    business.end_tariff_date += (ONE_DAY_SECONDS * duration)

                update_info = {
                    "user_credits": str(user.credits),
                    "user_referral_bonus": str(user.referral_bonus),
                    "business_id": business.id,                    
                    "business_end_tariff_date": business.end_tariff_date
                }
                
                log_data = {
                    "user_id": user_id,
                    "action_type": RENEW,
                    "entity_type": TARIFF,
                    "entity_id": tariff.id,
                    "extra_data": {
                        "business_id": business_id,
                        "tariff_slug": tariff.slug,
                        "tariff_days": duration,
                        "tariff_cost": str(tariff_cost)
                    }
                }

                return {"status": True, "update_info": update_info, "log_data": log_data}

            except Exception as e:
                logger.exception("renew_tariff_plan - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "renew_tariff_plan", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }