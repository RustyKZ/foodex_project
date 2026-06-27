from models.busineses import Business, BusinessTranslation
from models.app_users import AppUser
from models.reviews import ReviewBusiness, ReviewProduct
from models.interface import LanguageInterface
from models.products import Product
from models.orders import Order
from models.finances import AdCampaignBusinessPromo, Payment

from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, and_, exists, func, case
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from fastapi import UploadFile

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from config import settings
PAYMENT_PAYPAL_CLIENT_ID = settings.PAYMENT_PAYPAL_CLIENT_ID
PAYMENT_PAYPAL_SECRET = settings.PAYMENT_PAYPAL_SECRET
PAYPAL_API_URL = settings.PAYPAL_API_URL
PAYPAL_REDIRECT_AFTER_PAYMENT_SUCCESS = settings.PAYPAL_REDIRECT_AFTER_PAYMENT_SUCCESS
PAYPAL_REDIRECT_AFTER_PAYMENT_CANCEL = settings.PAYPAL_REDIRECT_AFTER_PAYMENT_CANCEL


from services.error import put_critical_error_into_db

from decimal import Decimal
import httpx
import math

from constants.payments import PAYMENT_METHOD_PAYPAL, PAYPAL_MAX_ORDERS_BY_HOUR_FOR_USER, PAYPAL_MINIMAL_PERIOD_FOR_ONE_ORDER


from sqlalchemy import select, func, case
from datetime import datetime, timezone


async def check_user_right_for_create_paypal_new_order(user_id) -> dict:
    async with async_session() as session:
        try:
            now = int(datetime.now(timezone.utc).timestamp())
            one_hour_ago = now - 3600
            cooldown_border = now - PAYPAL_MINIMAL_PERIOD_FOR_ONE_ORDER

            query = select(
                func.count().filter(
                    Payment.date > one_hour_ago
                ).label("hour_count"),

                func.count().filter(
                    Payment.date > cooldown_border
                ).label("recent_count")
            ).where(
                Payment.method_code == PAYMENT_METHOD_PAYPAL,
                Payment.user_id == user_id,
                Payment.confirmed.is_(False),
                Payment.processed.is_(False),
                Payment.deleted.is_(False)
            )

            result = await session.execute(query)
            row = result.one()

            hour_count = row.hour_count
            recent_count = row.recent_count

            if hour_count >= PAYPAL_MAX_ORDERS_BY_HOUR_FOR_USER:
                return {"status": False}

            if recent_count > 0:
                return {"status": False}

            return {"status": True}

        except Exception as e:
            logger.exception(f"check_user_right_for_create_paypal_new_order - MAIN EXCEPTION ERROR: {e}")
            return {"status": False}


async def get_payment_link_paypal(user_id: int, amount: Decimal) -> dict:
    try:
        can_user_get_link = await check_user_right_for_create_paypal_new_order(user_id)
        if not can_user_get_link["status"]:
            logger.error(f"get_payment_link_paypal - Frequent attempts to obtain a payment link by user {user_id}")
            return {"status": False}
        
        amount = amount.quantize(Decimal("0.01"))
        # 1. OAuth token
        async with httpx.AsyncClient(timeout=20) as client:
            token_response = await client.post(
                f"{PAYPAL_API_URL}/v1/oauth2/token",
                auth=(PAYMENT_PAYPAL_CLIENT_ID, PAYMENT_PAYPAL_SECRET),
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                },
                data={"grant_type": "client_credentials"},
            )

            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            # 2. Create order
            order_response = await client.post(
                f"{PAYPAL_API_URL}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [
                        {
                            "amount": {
                                "currency_code": "USD",
                                "value": str(amount),
                            }
                        }
                    ],
                    "application_context": {
                        "return_url": PAYPAL_REDIRECT_AFTER_PAYMENT_SUCCESS,
                        "cancel_url": PAYPAL_REDIRECT_AFTER_PAYMENT_CANCEL,
                        "user_action": "PAY_NOW",
                    },
                },
            )

            order_response.raise_for_status()
            order_data = order_response.json()

        # 3. approve url
        approve_url = next(
            link["href"]
            for link in order_data["links"]
            if link["rel"] == "approve"
        )

        paypal_order_id = order_data["id"]        

        return { "status": True, "payment_link": approve_url, "order_id": paypal_order_id}

    except Exception as e:
        logger.exception("get_payment_link_paypal - MAIN EXCEPTION ERROR")
        await put_critical_error_into_db("get_payment_link_paypal", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
        return {"status": False}
    

async def get_paypal_access_token() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_URL}/v1/oauth2/token",
            auth=(PAYMENT_PAYPAL_CLIENT_ID, PAYMENT_PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def check_paypal_order_api(order_id: str) -> dict:
    token = await get_paypal_access_token()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PAYPAL_API_URL}/v2/checkout/orders/{order_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        if resp.status_code != 200:
            return {"status": False}

        data = resp.json()

        return {
            "status": True,
            "paypal_status": data.get("status"),
            "order_data": data,
        }


async def check_paypal_order_completed(order_id: str) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                payment = (
                    await session.execute(
                        select(Payment).where(
                            Payment.method_code == PAYMENT_METHOD_PAYPAL,
                            Payment.order_id == order_id,
                            Payment.processed.is_(False),
                            Payment.deleted.is_(False),
                        )
                    )
                ).scalars().first()

                if not payment:
                    logger.warning(f"check_paypal_order - payment not found: {order_id}")
                    return {"status": False}
                
                if payment.confirmed:
                    return {"status": True, "payment_id": payment.id}

                paypal_data = await check_paypal_order_api(order_id)

                if not paypal_data["status"]:
                    return {"status": False}

                if paypal_data["paypal_status"] not in ("COMPLETED",):
                    logger.warning(f"PayPal order not completed: {order_id}")
                    return {"status": False}
                
                payment.confirmed = True
                return {"status": True, "payment_id": payment.id}

            except Exception as e:
                logger.exception(f"check_paypal_order - MAIN EXCEPTION ERROR: {e}")
                return {"status": False}

async def check_paypal_order(order_id: str) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                payment = (
                    await session.execute(
                        select(Payment).where(
                            Payment.method_code == PAYMENT_METHOD_PAYPAL,
                            Payment.order_id == order_id,
                            Payment.processed.is_(False),
                            Payment.deleted.is_(False),
                        )
                    )
                ).scalars().first()

                if not payment:
                    logger.warning(f"check_paypal_order - payment not found: {order_id}")
                    return {"status": False}
                
                if payment.confirmed:
                    return {"status": True, "payment_id": payment.id}

                paypal_data = await check_paypal_order_api(order_id)

                if not paypal_data["status"]:
                    return {"status": False}

                if paypal_data["paypal_status"] not in ("COMPLETED", "APPROVED",):
                    logger.warning(f"PayPal order not completed: {order_id}")
                    return {"status": False}
                
                payment.confirmed = True
                return {"status": True, "payment_id": payment.id}

            except Exception as e:
                logger.exception(f"check_paypal_order - MAIN EXCEPTION ERROR: {e}")
                return {"status": False}        


async def check_paypal_order_clone(order_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # OAuth token
            token_response = await client.post(
                f"{PAYPAL_API_URL}/v1/oauth2/token",
                auth=(PAYMENT_PAYPAL_CLIENT_ID, PAYMENT_PAYPAL_SECRET),
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                },
                data={"grant_type": "client_credentials"},
            )

            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            # Get order info
            order_response = await client.get(
                f"{PAYPAL_API_URL}/v2/checkout/orders/{order_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

            order_response.raise_for_status()
            order_data = order_response.json()

            return {
                "status": True,
                "paypal_status": order_data.get("status"),
                "order_data": order_data,
            }

    except Exception as e:
        logger.exception("check_paypal_order - MAIN EXCEPTION ERROR")
        return {
            "status": False,
            "error": str(e),
        }
    

async def capture_paypal_order(order_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # OAuth token
            token_response = await client.post(
                f"{PAYPAL_API_URL}/v1/oauth2/token",
                auth=(PAYMENT_PAYPAL_CLIENT_ID, PAYMENT_PAYPAL_SECRET),
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                },
                data={"grant_type": "client_credentials"},
            )

            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            # Capture order
            capture_response = await client.post(
                f"{PAYPAL_API_URL}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

            capture_response.raise_for_status()

            capture_data = capture_response.json()

            return {
                "status": True,
                "paypal_status": capture_data.get("status"),
                "capture_data": capture_data,
            }

    except Exception as e:
        logger.exception("capture_paypal_order - MAIN EXCEPTION ERROR")

        return {
            "status": False,
            "error": str(e),
        }