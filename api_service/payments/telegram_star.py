from models.app_users import AppUser
from models.finances import Payment, PaymentMethod, StarPaymentData

from datetime import datetime, timezone, timedelta, UTC

from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified


from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from config import settings
THIS_INSTANCE_ID = settings.INSTANCE_ID

from decimal import Decimal, InvalidOperation

from services.error import put_critical_error_into_db

from constants.payments import PAYMENT_METHOD_STARS

async def star_payment_processing(user_id: int, charge_id: str, star_payment_id: int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                stmt = (select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)).with_for_update())
                user = (await session.execute(stmt)).scalars().first()
                if not user:
                    await put_critical_error_into_db("star_payment_processing", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False}
                
                star_payment = (await session.execute(select(StarPaymentData).where(
                        StarPaymentData.id == star_payment_id,
                        StarPaymentData.charge_id == charge_id                        
                    ).with_for_update())).scalars().first()
                if not star_payment:
                    await put_critical_error_into_db("star_payment_processing", "star payment data not found", f"Star payment with id {star_payment_id} not found", {"user_id": user_id})
                    return {"status": False}
                if star_payment.processed:
                    await put_critical_error_into_db("star_payment_processing", "star payment is already processed", f"Star payment with id {star_payment_id} is already processed", {"user_id": user_id})
                    return {"status": False}
                
                star_amount = star_payment.amount

                if not (isinstance(star_amount, int) and star_amount > 0):
                    await put_critical_error_into_db("star_payment_processing", "incorrect amount value", f"Incorrect amount value in StarPaymentData {star_payment_id} - Value: {star_amount}", {"user_id": user_id})
                    return {"status": False}
                
                amount = Decimal(star_amount)
                
                payment_method = (await session.execute(select(PaymentMethod).where(
                    PaymentMethod.code == PAYMENT_METHOD_STARS, 
                    PaymentMethod.active.is_(True)
                ))).scalars().first()
                if not payment_method:
                    logger.warning(f"star_payment_processing - Payment method '{PAYMENT_METHOD_STARS}' is not allowed now")
                    return {"status": False}
                                
                credits_value = payment_method.credits_per_unit * amount

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                new_payment = Payment(
                    date = current_time_unix,
                    method_code = PAYMENT_METHOD_STARS,
                    user_id = user_id,
                    amount = amount,
                    currency = payment_method.currency,
                    credits_received = credits_value,
                    confirmed = True,
                    details = {
                        "star_payment_id": star_payment_id,
                        "charge_id": charge_id
                    }
                )
                session.add(new_payment)
                await session.flush()

                user.credits += credits_value
                new_payment.processed = True

                star_payment.processed = True

                updated_credits = user.credits

                user_is_here = user.instance_id == THIS_INSTANCE_ID

                return {"status": True, "user_id": user_id, "added_credits": credits_value, "updated_credits": updated_credits, "user_is_here": user_is_here}
            except Exception as e:
                logger.exception("star_payment_processing - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "star_payment_processing", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return {"status": False}