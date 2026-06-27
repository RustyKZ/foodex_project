from models.finances import AdCampaignBusinessPromo
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

from constants.ad_campaign import *
from constants.default import ONE_DAY_SECONDS

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta


async def get_ad_campaign_list(business_ids: list) -> list:
    async with async_session() as session:        
        try:
            current_time_unix = int(datetime.now(timezone.utc).timestamp())
            campaigns = (
                await session.execute(select(AdCampaignBusinessPromo).where(
                    AdCampaignBusinessPromo.business_id.in_(business_ids),
                    AdCampaignBusinessPromo.date_start <= current_time_unix,
                    AdCampaignBusinessPromo.date_end > current_time_unix,
                    AdCampaignBusinessPromo.active.is_(True),
                    AdCampaignBusinessPromo.deleted.is_(False)
                ))
            ).scalars().all()
            campaign_list = []
            for campaign in campaigns:
                campaign_list.append(campaign.to_dict())
            return campaign_list

        except Exception as e:
            logger.exception("get_ad_campaign_list - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "get_ad_campaign_list", "main exception error", f"Error text: {str(e)}")
            return []
        

async def start_ad_campaign(user_id: int, campaign_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "start_ad_campaign", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                
                business_id = campaign_data.get("business_id")
                if not business_id or user.active_business_id != business_id:
                    logger.error(f"start_ad_campaign - user active business is not {business_id}")
                    return { "status": False }
                
                business = (
                    await session.execute(select(Business).
                        where(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False)).with_for_update()
                    )
                ).scalars().first()

                if not business:
                    logger.error(f"start_ad_campaign - business {business_id} not found")
                    return { "status": False }
                if business.owner_id != user_id:
                    logger.error(f"start_ad_campaign - user {user_id} is not owner of  business {business_id}")
                    return { "status": False }
                
                daily_credits = campaign_data.get("daily_credits")
                campaign_days = campaign_data.get("campaign_days")

                if not (isinstance(daily_credits, (int, float)) and not isinstance(daily_credits, bool)):
                    logger.error(f"start_ad_campaign - {daily_credits} is not Number")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                if not (isinstance(campaign_days, int) and not isinstance(campaign_days, bool)):
                    logger.error(f"start_ad_campaign - {campaign_days} is not Integer")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                if campaign_days < AD_CAMPAIGN_MINIMAL_CAMPAIGN_DAYS or daily_credits < AD_CAMPAIGN_MINIMAL_DAILY_CREDITS:
                    logger.error(f"start_ad_campaign - incorrect input data")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())
                existed_campaign = (
                    await session.execute(select(AdCampaignBusinessPromo).where(
                        AdCampaignBusinessPromo.business_id == business_id,
                        AdCampaignBusinessPromo.date_end > current_time_unix,
                        AdCampaignBusinessPromo.active.is_(True),
                        AdCampaignBusinessPromo.deleted.is_(False)
                    ))
                ).scalars().first()
                if existed_campaign:
                    logger.error(f"start_ad_campaign - business {business_id} has active adv campaign now")
                    return { "status": False }            
                
                try:
                    daily_credits = Decimal(str(daily_credits))
                except (InvalidOperation, TypeError, ValueError):
                    logger.error(f"start_ad_campaign - incorrect input data")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
               
                try:
                    campaign_cost = Decimal(str(daily_credits * campaign_days))
                except (InvalidOperation, TypeError, ValueError):
                    logger.error(f"start_ad_campaign - incorrect input data")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}

                common_credits = user.credits + user.referral_bonus
                if campaign_cost > common_credits:
                    logger.error(f"start_ad_campaign - not enough credits")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_not_enough_funds"}
                
                if user.referral_bonus >= campaign_cost:
                    user.referral_bonus -= campaign_cost
                else:
                    campaign_cost_copy = campaign_cost
                    campaign_cost_copy -= user.referral_bonus
                    user.credits -= campaign_cost_copy
                    user.referral_bonus = Decimal("0")

                campaign_log = {
                    "date": current_time_unix,
                    "actions": [
                        {AD_ACTION_DEPOSIT_MADE: str(campaign_cost)},
                        {AD_ACTION_DAILY_FEE_CHARGED: str(daily_credits)}
                    ]
                }
            
                new_campaign = AdCampaignBusinessPromo(
                    business_id = business_id,
                    initiator_user_id = user_id,
                    deposit_credits = campaign_cost,
                    daily_credits = daily_credits,
                    remaining_credits = campaign_cost - daily_credits,
                    date_start = current_time_unix,
                    date_end = current_time_unix + (ONE_DAY_SECONDS * campaign_days),
                    date_next_charge = current_time_unix + ONE_DAY_SECONDS,
                    log = [campaign_log]
                )

                session.add(new_campaign)
                await session.flush()

                campaign_dict = new_campaign.to_dict()

                return {"status": True, "new_campaign": campaign_dict, "updated_user_credits": str(user.credits), "updated_referral_bonus": str(user.referral_bonus)}

            except Exception as e:
                logger.exception("start_ad_campaign - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "start_ad_campaign", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }
            

async def delete_ad_campaign(user_id: int, campaign_id: int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True))
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()                
                if not user:
                    await put_critical_error_into_db(
                        "delete_ad_campaign", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                                                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())
                campaign = (
                    await session.execute(select(AdCampaignBusinessPromo).where(
                        AdCampaignBusinessPromo.id == campaign_id,                        
                        AdCampaignBusinessPromo.deleted.is_(False)
                    ).with_for_update())
                ).scalars().first()
                if not campaign:
                    logger.error(f"delete_ad_campaign - Ad campaign {campaign_id} not found")
                    return { "status": False }
                
                business_id = campaign.business_id
                business = (
                    await session.execute(select(Business).
                        where(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False))
                    )
                ).scalars().first()

                if not business:
                    logger.error(f"delete_ad_campaign - business {business_id} not found")
                    return { "status": False }
                if business.owner_id != user_id:
                    logger.error(f"delete_ad_campaign - user {user_id} is not owner of  business {business_id}")
                    return { "status": False }
                

                if not isinstance(campaign.log, list):
                    campaign.log = []

                campaign_log = {
                    "date": current_time_unix,
                    "actions": [
                        {AD_ACTION_CAMPAIGN_DELETED: True}
                    ]
                }
                campaign.log.append(campaign_log)
                flag_modified(campaign, "log")
                campaign.active = False
                campaign.deleted = True                

                return {"status": True}

            except Exception as e:
                logger.exception("delete_ad_campaign - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "delete_ad_campaign", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }


async def prolong_ad_campaign(user_id: int, campaign_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user_query = select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                
                if not user:
                    await put_critical_error_into_db(
                        "prolong_ad_campaign", "user not found or not active",
                        f"User {user_id} not found or not active", {"user_id": user_id}
                    )
                    return { "status": False }
                                
                prolong_days = campaign_data.get("prolong_days")
                if not (isinstance(prolong_days, int) and not isinstance(prolong_days, bool)):
                    logger.error(f"prolong_ad_campaign - incorrect input data")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                if prolong_days < AD_CAMPAIGN_MINIMAL_CAMPAIGN_DAYS:
                    logger.error(f"prolong_ad_campaign - incorrect input data")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}

                campaign_id = campaign_data.get("campaign_id")
                campaign = (
                    await session.execute(select(AdCampaignBusinessPromo).where(
                        AdCampaignBusinessPromo.id == campaign_id,                        
                        AdCampaignBusinessPromo.deleted.is_(False)
                    ).with_for_update())
                ).scalars().first()

                if not campaign:
                    logger.error(f"prolong_ad_campaign - Ad campaign {campaign_id} not found")
                    return { "status": False }

                business_id = campaign.business_id
                business = (
                    await session.execute(select(Business).
                        where(Business.id == business_id, Business.active.is_(True), Business.deleted.is_(False))
                    )
                ).scalars().first()

                if not business:
                    logger.error(f"prolong_ad_campaign - business {business_id} not found")
                    return { "status": False }
                if business.owner_id != user_id:
                    logger.error(f"prolong_ad_campaign - user {user_id} is not owner of  business {business_id}")
                    return { "status": False }
                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                try:
                    prolong_cost = Decimal(str(campaign.daily_credits * prolong_days))
                except (InvalidOperation, TypeError, ValueError):
                    logger.error(f"prolong_ad_campaign - incorrect input data")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}

                common_credits = user.credits + user.referral_bonus
                if prolong_cost > common_credits:
                    logger.error(f"prolong_ad_campaign - not enough credits")
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_not_enough_funds"}
                
                if user.referral_bonus >= prolong_cost:
                    user.referral_bonus -= prolong_cost
                else:
                    prolong_cost_copy = prolong_cost
                    prolong_cost_copy -= user.referral_bonus
                    user.credits -= prolong_cost_copy
                    user.referral_bonus = Decimal("0")

                campaign.remaining_credits += prolong_cost

                if not isinstance(campaign.log, list):
                    campaign.log = []

                if campaign.active and campaign.date_end > current_time_unix:
                    campaign.date_end += ONE_DAY_SECONDS * prolong_days
                    campaign_log = {
                        "date": current_time_unix,
                        "actions": [
                            {AD_ACTION_DEPOSIT_REPLENISHED: str(prolong_cost)}
                        ]
                    }
                    campaign.log.append(campaign_log)
                    flag_modified(campaign, "log")
                else:
                    campaign.date_end = current_time_unix + (ONE_DAY_SECONDS * prolong_days)
                    campaign.active = True
                    campaign.remaining_credits -= campaign.daily_credits
                    campaign.date_next_charge = current_time_unix + ONE_DAY_SECONDS
                    campaign_log = {
                        "date": current_time_unix,
                        "actions": [
                            {AD_ACTION_DEPOSIT_REPLENISHED: str(prolong_cost)},
                            {AD_ACTION_DAILY_FEE_CHARGED: str(campaign.daily_credits)}
                        ]
                    }
                    campaign.log.append(campaign_log)
                    flag_modified(campaign, "log")

                campaign_dict = campaign.to_dict()

                return {"status": True, "updated_campaign": campaign_dict, "updated_user_credits": str(user.credits), "updated_referral_bonus": str(user.referral_bonus)}

            except Exception as e:
                logger.exception("prolong_ad_campaign - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "prolong_ad_campaign", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return { "status": False }