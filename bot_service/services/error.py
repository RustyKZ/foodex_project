
from models.monitoring import AppError
from datetime import datetime, timezone

from config import settings
PUT_ERROR_INTO_DATABASE = settings.PUT_ERROR_INTO_DATABASE
THIS_SERVICE_NAME = settings.BOT_SERVICE_NAME
INSTANCE_ID = settings.INSTANCE_ID

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

async def put_critical_error_into_db(function_name, error_short, error_text, context):
    try:
        if not PUT_ERROR_INTO_DATABASE:
            logger.error(f"put_critical_error_into_db - NOT SAVED - {function_name} - {error_short} - {error_text} - {context}")
            return
        if not function_name or not isinstance(function_name, str):
            function_name = ""
        if not error_short or not isinstance(error_short, str):
            error_short = "" 
        if not error_text or not isinstance(error_text, str):
            error_text = ""
        if not context or not isinstance(context, dict):
            context = {}
        async with async_session() as session:
            current_time_unix = int(datetime.now(timezone.utc).timestamp())
            new_error = AppError(
                date = current_time_unix,
                service = f"{THIS_SERVICE_NAME}/{INSTANCE_ID}",
                function = function_name,
                error_short = error_short,
                error_text = error_text,
                context = context
            )
            session.add(new_error)
            await session.commit()
            logger.error(f"put_critical_error_into_db - SAVED - {function_name} - {error_short} - {error_text} - {context}")
    except Exception as e:
        logger.error(f"put_critical_error_into_db - EXCEPTION ERROR: {e}")
        logger.error(f"put_critical_error_into_db - EXCEPTION - NOT SAVED - {function_name} - {error_short} - {error_text} - {context}")

