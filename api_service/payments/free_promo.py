from models.app_users import AppUser
from models.finances import Payment, PaymentMethod

from datetime import datetime, timezone, timedelta, UTC

from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified


from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from config import settings

from decimal import Decimal, InvalidOperation


from services.error import put_critical_error_into_db

from constants.payments import PAYMENT_METHOD_FREE_PROMO, MIN_PAYMENT_FREE_PROMO, MAX_PAYMENT_FREE_PROMO


async def get_date_last_free_promo_payment(user_id) -> int:
    async with async_session() as session:
        try:
            stmt = (
                select(Payment.date)
                .where(
                    Payment.user_id == user_id,
                    Payment.method_code == PAYMENT_METHOD_FREE_PROMO,
                    Payment.processed.is_(True),
                )
                .order_by(Payment.date.desc())
                .limit(1)
            )

            result = await session.execute(stmt)
            payment_date = result.scalar_one_or_none()

            return payment_date or 0
        
        except Exception as e:
            logger.exception("get_date_last_free_promo_payment - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "get_date_last_free_promo_payment", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
            return 0
        

async def get_free_credits(user_id: int, payment_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                payment_method_code = payment_data.get("payment_method")
                raw_amount = payment_data.get("amount")
                try:
                    amount = Decimal(str(raw_amount))
                except (InvalidOperation, TypeError, ValueError):
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                if payment_method_code != PAYMENT_METHOD_FREE_PROMO or amount <= 0:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                payment_method = (await session.execute(select(PaymentMethod).where(
                    PaymentMethod.code == payment_method_code, 
                    PaymentMethod.active.is_(True)
                ))).scalars().first()
                if not payment_method:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_payment_method_not_allowed_now"}
                
                stmt = (
                    select(AppUser)
                        .where(AppUser.id == user_id, AppUser.active.is_(True))
                        .with_for_update()
                    )
                user = (await session.execute(stmt)).scalars().first()
                if not user:
                    await put_critical_error_into_db("get_free_credits", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False}
                
                last_date_of_free_credits = await get_date_last_free_promo_payment(user_id)
                last_date = datetime.fromtimestamp(last_date_of_free_credits, UTC).date()
                today = datetime.now(UTC).date()
                if last_date == today:                    
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_free_credits_was_getting_today"}
                
                min_amount = Decimal(str(payment_method.custom_options.get("min_amount", MIN_PAYMENT_FREE_PROMO)))
                max_amount = Decimal(str(payment_method.custom_options.get("max_amount", MAX_PAYMENT_FREE_PROMO)))
                if amount > max_amount:
                    amount = max_amount
                if amount < min_amount:
                    amount = min_amount
                
                credits_value = amount * payment_method.credits_per_unit
                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                new_payment = Payment(
                    date = current_time_unix,
                    method_code = payment_method_code,
                    user_id = user_id,
                    amount = amount,
                    currency = payment_method.currency,
                    credits_received = credits_value,
                    confirmed = True                    
                )
                session.add(new_payment)
                await session.flush()

                user.credits += credits_value
                new_payment.processed = True

                updated_credits = user.credits
                updated_last_free_credits_date = current_time_unix

                return {"status": True, "updated_credits": updated_credits, "updated_last_free_credits_date": updated_last_free_credits_date}
            except Exception as e:
                logger.exception("get_free_credits - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "get_free_credits", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return {"status": False}