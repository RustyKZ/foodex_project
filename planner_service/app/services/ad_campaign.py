from sqlalchemy import select, or_
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone

from ..models.finances import AdCampaignBusinessPromo

from ..constants.system_log import *
from ..constants.ad_campaign import *
from ..constants.default import ONE_DAY_SECONDS

from ..rediska.redis_client import redis_client
from ..session_config import sync_session

from ..logger_config import get_logger
logger = get_logger(__name__)

from ..config import settings
THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME
API_SERVICE_NAME = settings.API_SERVICE_NAME

from .error import put_critical_error_into_db
from .system_action import put_system_action_into_db_log

def get_ad_campaigns_for_daily_fee_charge():
    try:        
        current_time_unix = int(datetime.now(timezone.utc).timestamp())

        with sync_session() as session:
            with session.begin():
                campaign_ids = session.execute(
                    select(AdCampaignBusinessPromo.id).where(
                        AdCampaignBusinessPromo.deleted.is_(False),
                        AdCampaignBusinessPromo.date_next_charge <= current_time_unix
                    )
                ).scalars().all()

        if campaign_ids:
            for campaign_id in campaign_ids:
                ad_campaign_daily_fee_charge(campaign_id)

    except Exception as e:
        logger.exception(f"DEF get_ad_campaigns_for_daily_fee_charge - Exception: {e}")
        put_critical_error_into_db( "get_ad_campaigns_for_daily_fee_charge", "main exception error", f"Error text: {str(e)}", {})        


def ad_campaign_daily_fee_charge(campaign_id: int):
    try:
        timestart_float = datetime.now(timezone.utc).timestamp()
        event = EVENT_DAILY_AD_CAMPAIGNS_FEE_CHARGE
        status = SYSTEM_ACTION_STATUS_UNDEFINED
        description = ""
        meta_json = {"campaign_id": campaign_id}
        
        current_time_unix = int(timestart_float)

        with sync_session() as session:
            with session.begin():
                campaign = session.execute(select(AdCampaignBusinessPromo).where(AdCampaignBusinessPromo.id == campaign_id).with_for_update()).scalars().first()
                if campaign is None:                    
                    raise ValueError(f"Campaign {campaign_id} not found")
                if not isinstance(campaign.log, list):
                    campaign.log = []
                if campaign.date_next_charge == 0:
                    if campaign.remaining_credits >= campaign.daily_credits:
                        campaign.remaining_credits -= campaign.daily_credits
                        campaign.date_next_charge = current_time_unix + ONE_DAY_SECONDS
                        campaign.active = True
                        campaign_log = {
                            "date": current_time_unix,
                            "actions": [
                                {AD_ACTION_DAILY_FEE_CHARGED: str(campaign.daily_credits)}
                            ]
                        }
                        campaign.log.append(campaign_log)
                        flag_modified(campaign, "log")
                        status = SYSTEM_ACTION_STATUS_SUCCESS
                    else:
                        campaign.active = False
                        campaign.deleted = True
                        campaign_log = {
                            "date": current_time_unix,
                            "actions": [
                                {AD_ACTION_CAMPAIGN_DELETED: True}
                            ]
                        }
                        campaign.log.append(campaign_log)
                        flag_modified(campaign, "log")
                        status = SYSTEM_ACTION_STATUS_SKIPPED
                elif campaign.date_next_charge > current_time_unix:
                    campaign_log = {
                        "date": current_time_unix,
                        "actions": [
                            {AD_ACTION_NO_ACTION: True}
                        ]
                    }
                    campaign.log.append(campaign_log)
                    flag_modified(campaign, "log")
                    status = SYSTEM_ACTION_STATUS_SKIPPED
                else:
                    if campaign.remaining_credits >= campaign.daily_credits:
                        campaign.remaining_credits -= campaign.daily_credits
                        campaign.date_next_charge += ONE_DAY_SECONDS
                        campaign.active = True
                        campaign_log = {
                            "date": current_time_unix,
                            "actions": [
                                {AD_ACTION_DAILY_FEE_CHARGED: str(campaign.daily_credits)}
                            ]
                        }
                        campaign.log.append(campaign_log)
                        flag_modified(campaign, "log")
                        status = SYSTEM_ACTION_STATUS_SUCCESS
                    else:
                        campaign.active = False
                        campaign.deleted = True
                        campaign.date_next_charge = 0
                        campaign_log = {
                            "date": current_time_unix,
                            "actions": [
                                {AD_ACTION_CAMPAIGN_DELETED: True}
                            ]
                        }
                        campaign.log.append(campaign_log)
                        flag_modified(campaign, "log")
                        status = SYSTEM_ACTION_STATUS_SKIPPED

    except Exception as e:
        logger.exception(f"DEF ad_campaign_daily_fee_charge - Exception: {e}")
        put_critical_error_into_db( "ad_campaign_daily_fee_charge", "main exception error", f"Error text: {str(e)}", {})
        status = SYSTEM_ACTION_STATUS_ERROR
    finally:
        timeend_float = datetime.now(timezone.utc).timestamp()
        duration = timeend_float - timestart_float
        put_system_action_into_db_log(event=event, status=status, description=description, meta_json=meta_json, duration=duration)


