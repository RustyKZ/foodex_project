
from models.monitoring import UserAction
from datetime import datetime, timezone

from .error import put_critical_error_into_db

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

async def add_user_action_log(log_data : dict):
    current_time_unix = int(datetime.now(timezone.utc).timestamp())
    user_id = log_data.get("user_id", 0)    
    action_type = log_data.get("action_type", "")
    entity_type = log_data.get("entity_type", "")
    entity_id = log_data.get("entity_id", 0)
    ip_address = log_data.get("ip_address", "")
    extra_data = log_data.get("extra_data", {})
    try:
        async with async_session() as session:            
            new_log = UserAction(
                date = current_time_unix,
                user_id = user_id,
                action_type = action_type,
                entity_type = entity_type,
                entity_id = entity_id,
                ip_address = ip_address,
                extra_data = extra_data
            )
            session.add(new_log)
            await session.commit()
            logger.info(f"add_user_action_log - New UserAction log {new_log.id} added successfully")
    except Exception as e:
        await put_critical_error_into_db("add_user_action_log", "insert log error", f"Exception error occurred while trying to add user {user_id} action to the log entry", {"log_data": log_data})


