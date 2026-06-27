from sqlalchemy import select
from datetime import datetime, timezone

from ..models.bot_models import BotMessage

from ..rabbit.celery_rabbit_sender import broadcast_message, send_direct_message

from ..session_config import sync_session

from ..logger_config import get_logger
logger = get_logger(__name__)

from ..config import settings
THIS_SERVICE_NAME = settings.PLANNER_SERVICE_NAME
BOT_SERVICE_NAME = settings.BOT_SERVICE_NAME

from .error import put_critical_error_into_db
from .system_action import put_system_action_into_db_log


def check_fresh_bot_messages_for_confirm_and_send():
    try:
        with sync_session() as session:
            
            current_time_unix = int(datetime.now(timezone.utc).timestamp())

            bot_messages_for_confirm = session.execute(select(BotMessage).where(
                BotMessage.not_actual.is_(False),
                BotMessage.sended.is_(False),
                BotMessage.confirmed.is_(False)
            )).scalars().all()

            bot_messages_for_send = session.execute(select(BotMessage).where(
                BotMessage.not_actual.is_(False),
                BotMessage.sended.is_(False),
                BotMessage.confirmed.is_(True),
                BotMessage.sending_date <= current_time_unix
            )).scalars().all()
            
            if bot_messages_for_confirm:
                for bm in bot_messages_for_confirm:
                    message = {
                        "sender": THIS_SERVICE_NAME,
                        "receiver": BOT_SERVICE_NAME,
                        "receiver_id": "all",
                        "message": { 
                            "type": "execute",
                            "description": "process_bot_message_for_confirm",
                            "bot_message_id": bm.id                            
                        }
                    }            
                    send_direct_message(service_name=BOT_SERVICE_NAME, message=message)

            if bot_messages_for_send:
                for bm in bot_messages_for_send:
                    message = {
                        "sender": THIS_SERVICE_NAME,
                        "receiver": BOT_SERVICE_NAME,
                        "receiver_id": "all",
                        "message": { 
                            "type": "execute",
                            "description": "process_bot_message_for_send",
                            "bot_message_id": bm.id                            
                        }
                    }            
                    send_direct_message(service_name=BOT_SERVICE_NAME, message=message)
        

            return

    except Exception as e:
        logger.exception(f"DEF check_fresh_bot_messages_for_sending - Exception: {e}")
        put_critical_error_into_db( "check_fresh_bot_messages_for_sending", "main exception error", f"Error text: {str(e)}", {})        
        return


    
