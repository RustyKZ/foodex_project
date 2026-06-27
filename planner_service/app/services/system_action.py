from ..models.monitoring import SystemAction
from datetime import datetime, timezone

from ..config import settings
THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME
INSTANCE_ID = settings.INSTANCE_ID

from ..session_config import sync_session

from ..logger_config import get_logger
logger = get_logger(__name__)

from ..constants.system_log import *

from .error import put_critical_error_into_db


def put_system_action_into_db_log(event: str, status: str, description: str, meta_json: dict, duration: float):    
    try:
        if not event or not isinstance(event, str):
            event = ""

        if not status or not isinstance(status, str):
            status = SYSTEM_ACTION_STATUS_UNDEFINED

        if not description or not isinstance(description, str):
            description = ""

        if not meta_json or not isinstance(meta_json, dict):
            meta_json = {}

        if duration is None or not isinstance(duration, (int, float)):
            duration = 0.0

        with sync_session() as session:
            current_time_unix = int(datetime.now(timezone.utc).timestamp())

            new_note = SystemAction(
                date=current_time_unix,
                service=f"{THIS_SERVICE_NAME}/{INSTANCE_ID}",
                event=event,
                status=status,
                description=description,
                meta_json=meta_json,
                duration=duration
            )

            session.add(new_note)
            session.commit()

            logger.info(
                f"put_system_action_into_db_log - SAVED - "
                f"{event} - {status} - {meta_json} - {duration}"
            )

    except Exception as e:
        logger.error(f"put_system_action_into_db_log - EXCEPTION ERROR: {e}")
        data = {
            "event": event,
            "status": status,
            "description": description,
            "meta_json": meta_json,
            "duration": duration
        }
        put_critical_error_into_db( "put_system_action_into_db_log", "main exception error", f"Error text: {str(e)}", data)