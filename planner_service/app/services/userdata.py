
from sqlalchemy import select
from datetime import datetime, timezone

from ..models.app_users import AppUser

from ..rabbit.celery_rabbit_sender import broadcast_message, send_direct_message

from ..constants.redis_vars import TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY
from ..constants.default import INACTIVE_TIME_LOGOUT

from ..rediska.redis_client import redis_client
from ..session_config import sync_session

from ..logger_config import get_logger
logger = get_logger(__name__)

from ..config import settings
THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME
API_SERVICE_NAME = settings.API_SERVICE_NAME

from .error import put_critical_error_into_db

def get_all_online_users():
    logger.info(f"DEF get_all_online_users")    
    try:
        users = redis_client.zrange(
            TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY,
            0,
            -1,
            withscores=True
        )

        logger.info(f"ONLINE USERS: {users}")

        for user_id, last_activity in users:
            logger.info(
                f"user_id={user_id}, "
                f"last_activity_unix={last_activity}"
            )

    except Exception as e:
        logger.exception(
            f"DEF get_all_online_users - Exception: {e}"
        )


def logout_inactive_users():
    logger.info(f"DEF get_inactive_users")
    current_time_unix = int(datetime.now(timezone.utc).timestamp())
    logout_time = current_time_unix - INACTIVE_TIME_LOGOUT    
    try:
        inactive_users_ids_str = redis_client.zrangebyscore(
            TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY,
            0,
            logout_time
        )

        inactive_users_ids = [
            int(user_id)
            for user_id in inactive_users_ids_str
        ]

        if inactive_users_ids:
            message = {
                "sender": THIS_SERVICE_NAME,
                "receiver": API_SERVICE_NAME,
                "receiver_id": "all",
                "message": { 
                    "type": "execute",
                    "description": "logout_inactive_users",
                    "user_ids": inactive_users_ids
                }
            }
            logger.info(f"DEF get_inactive_users - list of users: {inactive_users_ids}")
            broadcast_message(message=message)

    except Exception as e:
        logger.exception(f"DEF get_inactive_users - Exception: {e}")
        put_critical_error_into_db( "logout_inactive_users", "main exceptions error", f"Error text: {str(e)}", {})