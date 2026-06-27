from models.busineses import Business, BusinessTranslation
from models.app_users import AppUser
from models.reviews import ReviewBusiness, ReviewProduct
from models.interface import LanguageInterface
from models.products import Product
from models.orders import Order
from models.finances import AdCampaignBusinessPromo, PaymentMethod, Payment

from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, and_, exists, func, case
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from config import settings
BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math

from services.error import put_critical_error_into_db
from payments.paypal import get_payment_link_paypal

from constants.payments import PAYMENT_METHOD_PAYPAL, ALLOWED_PAYMENT_METHODS, PAYMENT_METHOD_STARS
from constants.default import DEFAULT_LANGUAGE

from system_i18n.payment_messages import SUCCESSFULL_PAYMENT_INTRO, SUCCESSFULL_PAYMENT_PAYMENT_MADE_, SUCCESSFULL_PAYMENT_CREDITS_RECEIVED_ 

import httpx
import uuid


async def get_payment_methods_for_frontend() -> list:
    async with async_session() as session:
        try:
            methods = (await session.execute(
                    select(PaymentMethod).where(PaymentMethod.show_on_frontend.is_(True)).order_by(PaymentMethod.priority, PaymentMethod.id)
                )).scalars().all()
            list_of_dict = []
            for method in methods:
                list_of_dict.append(method.to_dict())
            return list_of_dict
        except Exception as e:
            logger.exception("get_payment_methods_for_frontend - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db( "get_payment_methods_for_frontend", "main exception error", f"Error text: {str(e)}", {})
            return []
                

async def get_payment_redirect_link(user_id: int, payment_data: dict) -> dict:    
    try:
        async with async_session() as session:
            try:
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
                if not user:
                    await put_critical_error_into_db("get_payment_redirect_link", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False}
            except Exception as user_not_found:
                await put_critical_error_into_db("get_payment_redirect_link", "Exception getting user", f"Exception text: {user_not_found}", {"user_id": user_id})
                return {"status": False}
        payment_method_code = payment_data.get("payment_method")
        raw_amount = payment_data.get("amount")
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError, ValueError):
            return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
        if amount <= 0:
            return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
        if payment_method_code not in ALLOWED_PAYMENT_METHODS:
            return {"status": False, "notify_type": "error", "notify_code": "notify_error_payment_method_not_allowed_now"}    
            
        if payment_method_code == PAYMENT_METHOD_PAYPAL:
            get_link = await get_payment_link_paypal(user_id, amount)
            if get_link["status"]:
                payment_link = get_link.get("payment_link")
                order_id = get_link.get("order_id")
                create_payment = await create_new_payment(user_id=user_id, method_code=payment_method_code, amount=amount, order_id=order_id)
                if create_payment["status"]:
                    return {"status": True, "payment_link": payment_link}
                else:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_getting_payment_link_error"}    
            else:
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_getting_payment_link_error"}        
            
        return {"status": False, "notify_type": "error", "notify_code": "notify_error_payment_method_not_allowed_now"}
            
    except Exception as e:
        logger.exception("get_payment_redirect_link - MAIN EXCEPTION ERROR") 
        await put_critical_error_into_db( "get_payment_redirect_link", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
        return {"status": False}


def decimal_to_str(value: Decimal) -> str:
    # Округляем до 2 знаков
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Если число целое — выводим без дробной части
    if value == value.to_integral():
        return str(int(value))
    # Иначе выводим максимум 2 знака без лишних нулей
    return format(value.normalize(), "f")

async def get_payment_stars_invoice_link(user_id: int, amount_stars: float) -> dict:
    try:
        async with async_session() as session:
            try:
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
                if not user:
                    await put_critical_error_into_db("get_payment_stars_invoice_link", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False}
            except Exception as user_not_found:
                await put_critical_error_into_db("get_payment_stars_invoice_link", "Exception getting user", f"Exception text: {user_not_found}", {"user_id": user_id})
                return {"status": False}
        
        user_telegram_id = user.tg_id
        if not user_telegram_id:
            logger.error(f"User {user_id} has not Telegram account")
            return {"status": False}
        
        try:
            amount = int(str(amount_stars))
        except:
            return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
        if amount <= 0:
            return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
        
        payment_method = (await session.execute(select(PaymentMethod).where(PaymentMethod.code == PAYMENT_METHOD_STARS))).scalars().first()
        if not payment_method:
            return {"status": False, "notify_type": "error", "notify_code": "notify_error_payment_method_not_allowed_now"}    
        credits_per_unit = payment_method.credits_per_unit
        buying_credits_str = decimal_to_str(credits_per_unit * amount)

        invoice_link = None

        payload = f"stars:{user_telegram_id}:{amount}:{uuid.uuid4()}"
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink"
        data = {
            "title": f"{buying_credits_str} FoodEx credits",
            "description": f"Payment of {amount} Telegram Stars",
            "payload": payload,
            "currency": "XTR",
            "provider_token": "",
            "prices": [
                {
                    "label": f"FoodEx credits",
                    "amount": amount
                }
            ]
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=data)

        result = response.json()

        if not result.get("ok"):
            await put_critical_error_into_db("get_payment_stars_invoice_link", "Telegram API error", str(result), {"user_id": user_id, "telegram_id": user_telegram_id})
            return {"status": False}

        invoice_link = result["result"]

        return {"status": True, "invoice_link": invoice_link}
            
    except Exception as e:
        logger.exception("get_payment_stars_invoice_link - MAIN EXCEPTION ERROR") 
        await put_critical_error_into_db( "get_payment_stars_invoice_link", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
        return {"status": False}    


async def create_new_payment(user_id: int, method_code: str, amount: Decimal, order_id: str) -> dict:
    async with async_session() as session:
        try:
            now = int(datetime.now(timezone.utc).timestamp())

            payment_method = (
                await session.execute(
                    select(PaymentMethod).where(
                        PaymentMethod.code == method_code
                    )
                )
            ).scalars().first()

            if not payment_method:
                return {"status": False}

            new_payment = Payment(
                date=now,
                method_code=method_code,
                user_id=user_id,
                amount=amount,
                currency=payment_method.currency,
                order_id=order_id
            )

            session.add(new_payment)

            await session.flush()   # INSERT -> id уже есть
            payment_id = new_payment.id

            await session.commit()

            return {"status": True, "payment_id": payment_id}

        except Exception as e:
            await session.rollback()
            logger.exception(f"create_new_payment - MAIN EXCEPTION ERROR: {e}")
            return {"status": False}


async def process_confirmed_payment(payment_id: int) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                payment = (
                    await session.execute(
                        select(Payment).where(
                            Payment.id == payment_id,
                            Payment.confirmed.is_(True),
                            Payment.processed.is_(False),
                            Payment.deleted.is_(False),
                        ).with_for_update()
                    )
                ).scalars().first()
                if not payment:
                    logger.warning(f"process_confirmed_payment - confirmed payment not found: {payment_id}")
                    return {"status": False}
                                
                user_id = payment.user_id
                user = (
                    await session.execute(
                        select(AppUser).where(
                            AppUser.id == user_id,                            
                        ).with_for_update()
                    )
                ).scalars().first()
                if not user:
                    logger.error(f"process_confirmed_payment - user not found: {user_id}")
                    return {"status": False}
                
                payment_method = (
                    await session.execute(
                        select(PaymentMethod).where(
                            PaymentMethod.code == payment.method_code
                        )
                    )
                ).scalars().first()
                if not payment_method:
                    logger.error(f"process_confirmed_payment - payment method not found: {payment.method_code}")
                    return {"status": False}
                
                payback_info = None
                referrer = None
                if user.referrer_id:
                    referrer = (await session.execute(
                        select(AppUser).where(AppUser.id == user.referrer_id,).with_for_update()
                    )).scalars().first()
                                
                credits_payback = Decimal("0")
                credits_payroll = (payment.amount * payment_method.credits_per_unit).quantize(Decimal("0.01"))
                if payment_method.referrer_payback:
                    credits_payback = ((credits_payroll * payment_method.payback_percent)/100).quantize(Decimal("0.01"))
                
                payment.processed = True
                payment.credits_received = credits_payroll
                user.credits += credits_payroll

                user_settings = getattr(user, "settings", {})
                bot_notify_on = user_settings.get("bot_notify_on", True)

                if referrer and credits_payback > Decimal("0") and payment.credits_payback == Decimal("0"):
                    referrer.referral_bonus += credits_payback
                    payment.credits_payback = credits_payback
                    credits_payback_str = str(credits_payback)
                    payback_info = {
                        "user_id": referrer.id,
                        "referrar_id": user_id,
                        "referrar_username": user.username,
                        "referral_bonus": credits_payback_str                        
                    }
                
                message_intro = SUCCESSFULL_PAYMENT_INTRO.get(user.language, SUCCESSFULL_PAYMENT_INTRO.get(DEFAULT_LANGUAGE))
                message_payment_made = SUCCESSFULL_PAYMENT_PAYMENT_MADE_.get(user.language, SUCCESSFULL_PAYMENT_PAYMENT_MADE_.get(DEFAULT_LANGUAGE))
                message_credits_received = SUCCESSFULL_PAYMENT_CREDITS_RECEIVED_.get(user.language, SUCCESSFULL_PAYMENT_CREDITS_RECEIVED_.get(DEFAULT_LANGUAGE))
                bot_message = f"{message_intro}\n{message_payment_made} {payment.amount} {payment.currency}\n{message_credits_received} {payment.credits_received} 🟡"

                return {"status": True, "user_id": user_id, "payback_info": payback_info, "user_tg_id": user.tg_id, "bot_notify_on": bot_notify_on, "bot_message": bot_message}
            except Exception as e:            
                logger.exception(f"process_confirmed_order - MAIN EXCEPTION ERROR: {e}")
                return {"status": False}