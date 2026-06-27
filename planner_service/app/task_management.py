from .celery_app import celery_app
from .rabbit.celery_rabbit_sender import broadcast_message, send_direct_message

from datetime import datetime, timezone
from psycopg2.extras import DictCursor

from .logger_config import get_logger
logger = get_logger(__name__)

from .services.userdata import get_all_online_users, logout_inactive_users
from .services.error import put_critical_error_into_db
from .services.orders import daily_live_orders_updating
from .services.ad_campaign import get_ad_campaigns_for_daily_fee_charge
from .services.business_tariff import check_businesses_paid_subscriptions
from .services.bot_messages import check_fresh_bot_messages_for_confirm_and_send


@celery_app.task
def every_minute_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF every_minute_task - {current_time}")
    check_businesses_paid_subscriptions()
    check_fresh_bot_messages_for_confirm_and_send()


@celery_app.task
def every_three_minutes_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF every_three_minutes_task - {current_time}")    
        

@celery_app.task
def five_minutes_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF five_minutes_task - {current_time}")
    logout_inactive_users()
    

@celery_app.task
def ten_minutes_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF ten_minutes_task - {current_time}")
    get_ad_campaigns_for_daily_fee_charge()


@celery_app.task
def fifteen_minutes_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF fifteen_minutes_task - {current_time}")


@celery_app.task
def twenty_minutes_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF twenty_minutes_task - {current_time}")


@celery_app.task
def thirty_minutes_task():
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF thirty_minutes_task - {current_time}")


@celery_app.task
def daily_accounting():    
    current_time = datetime.now(timezone.utc)
    logger.info(f"DEF daily_accounting - {current_time}")
    daily_live_orders_updating()






