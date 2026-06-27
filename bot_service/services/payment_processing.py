

from models.app_users import AppUser
from models.finances import StarPaymentData

from sqlalchemy import insert, update, or_, and_, func
from sqlalchemy.future import select

from .error import put_critical_error_into_db
from .user_action_log import add_user_action_log

from datetime import datetime, timezone, timedelta, UTC

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from constants.default_settings import DEFAULT_LANGUAGE, DEFAULT_TIMEZONE, MAX_ORDER_LIST_EXCEL_FILE_ITEMS
from constants.log_entitys import *


async def star_payment_processing(payment_data: dict) -> dict:
    async with async_session() as session:
        try:
            if not isinstance(payment_data, dict):
                await put_critical_error_into_db("star_payment_processing", "incorrect data", f"Incorrect function incoming data", payment_data)
                return {"status": False}
            
            user_tg_id = payment_data.get("user_tg_id")
            charge_id = payment_data.get("charge_id")
            amount = payment_data.get("amount")
            payload = payment_data.get("payload")

            if not user_tg_id:
                await put_critical_error_into_db("star_payment_processing", "incorrect User TG ID", f"TG ID {user_tg_id} is incorrect", payment_data)
                return {"status": False}

            if not charge_id or not isinstance(charge_id, str):
                await put_critical_error_into_db("star_payment_processing", "incorrect charge ID", f"incorrect charge ID", payment_data)
                return {"status": False}
            
            if not amount or not isinstance(amount, int):
                await put_critical_error_into_db("star_payment_processing", "incorrect stars amount", f"incorrect stars amount: {amount}", payment_data)
                return {"status": False}
            
            if not payload or not isinstance(payload, str):
                payload = ""

            user = (await session.execute(select(AppUser).where(AppUser.tg_id == user_tg_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                await put_critical_error_into_db("star_payment_processing", "user not found", f"User with TG ID {user_tg_id} not found", payment_data)
                return {"status": False}
            
            language = user.language
            if not language:
                language = payment_data.get("language", DEFAULT_LANGUAGE)

            current_time_unix = int(datetime.now(timezone.utc).timestamp())

            new_star_payment_data = StarPaymentData(
                date = current_time_unix,
                tg_id = user_tg_id,
                amount = amount,
                charge_id = charge_id,
                payload = payload,
                processed = False,
                payment_id = None
            )
            
            session.add(new_star_payment_data)
            await session.flush()

            new_star_payment_data_id = new_star_payment_data.id

            await session.commit()
            
            return {
                "status": True, 
                "language": language,
                "user_id": user.id,
                "charge_id": charge_id,
                "star_payment_id": new_star_payment_data_id
            }
        

        except Exception as e:
            logger.exception(f"star_payment_processing - MAIN EXCEPTION: {e}")                
            await put_critical_error_into_db("star_payment_processing", "main exception error", str(e), payment_data)
            return {"status": False}