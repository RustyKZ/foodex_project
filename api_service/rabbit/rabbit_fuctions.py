
from config import settings
THIS_INSTANCE_ID = settings.INSTANCE_ID

from session_config import async_session

from models.app_users import AppUser
from models.busineses import Business
from models.messages import Message, Notification
from models.products import Product
from models.finances import Payment

from sqlalchemy.future import select
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm.attributes import flag_modified

from sqlalchemy.orm import aliased

from constants.frontend import TAB_MESSAGE_CENTER, TAB_SUPPLIER_PRODUCT_CATALOG
from constants.default import INACTIVE_TIME_LOGOUT, INACTIVE_TIME_HARD_LOGOUT
from constants.redis_vars import TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY

from rediska.redis_cli import redis_client

from api_endpoints.sio_init import sio

from logger_config import get_logger
logger = get_logger(__name__)

from services.error import put_critical_error_into_db
from services.userdata import get_advanced_userinfo
from services.items import get_product
from services.order_actions import get_order
from services.notifications import get_message

from decimal import Decimal
        

async def new_login_user_logout(sid):
    logger.info(f"new_login_user_logout: Start executing logout for user by SID: {sid}")
    if sid and isinstance(sid, str):
        await sio.emit("new_login_logout", {}, to=sid)        


# ----------------------------------------------------------------------------

async def execute_update_tab_notify(user_id : int):
    logger.info(f"execute_update_tab_notify - User ID: {user_id}")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                logger.error(f"execute_update_tab_notify - User {user_id} not found")
                return                        
            
            await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)

        except Exception as e:
            logger.exception("execute_update_tab_notify - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_update_tab_notify", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id}
            )
            return
        

async def execute_push_new_product_to_catalog_supplier(user_id, product_id):
    logger.info(f"push_new_product_into_product_catalog - User ID: {user_id}; Product ID: {product_id}")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user:
                logger.error(f"push_new_product_into_product_catalog - User {user_id} not found")
                return
                    
            product_query = await get_product(product_id=product_id)
            
            if not product_query["status"]:
                logger.error(f"execute_push_new_product_to_catalog_supplier - Product {product_id} not found")
                return
            
            product_dict = product_query.get("product_dict", None)

            if product_dict:
                await sio.emit("push_new_product_into_catalog", {"new_product": product_dict}, to=user.sid)                
            else:
                logger.error(f"push_new_product_into_product_catalog - Something wrong...")

            return
        
        except Exception as e:
            logger.exception("execute_push_new_product_to_catalog_supplier - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_push_new_product_to_catalog_supplier", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "product_id": product_id}
            )
            return
        

async def execute_user_notify_employee_fired_for_employee(employee_id : int, notification_id : int):
    logger.info(f"execute_user_notify_employee_fired_for_employee - Employee: {employee_id}; Notification ID: {notification_id};")
    async with async_session() as session:        
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == employee_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_notify_employee_fired_for_employee - User {employee_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"execute_user_notify_employee_fired_for_employee - Notification {notification_id} not found")
                return

            updated_userinfo = await get_advanced_userinfo(employee_id)

            if updated_userinfo["status"]:
                userdata = updated_userinfo["userdata"]
                business_list = updated_userinfo["business_list"]
                notification_dict = notification.to_dict()
                if user.id == notification.receiver_user:
                    await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)
                await sio.emit("update_userinfo_and_business_list_hard", {"userdata": userdata, "business_list": business_list}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_notify_employee_fired_for_employee - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_notify_employee_fired_for_employee", "main exception error",
                f"Error text: {str(e)}", {"employee_id": employee_id, "notification_id": notification_id}
            )
            return
        

async def execute_user_notify_employee_staff_request_confirmed(employee_id : int, notification_id : int):
    logger.info(f"execute_user_notify_employee_staff_request_confirmed - Employee: {employee_id}; Notification ID: {notification_id};")
    async with async_session() as session:        
        try:            
            user = (await session.execute(select(AppUser).where(AppUser.id == employee_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_notify_employee_staff_request_confirmed - User {employee_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"execute_user_notify_employee_staff_request_confirmed - Notification {notification_id} not found")
                return

            updated_userinfo = await get_advanced_userinfo(employee_id)

            if updated_userinfo["status"]:
                userdata = updated_userinfo["userdata"]
                business_list = updated_userinfo["business_list"]
                notification_dict = notification.to_dict()
                if user.id == notification.receiver_user:
                    await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)
                await sio.emit("update_userinfo_and_business_list_hard", {"userdata": userdata, "business_list": business_list}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_notify_employee_staff_request_confirmed - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_notify_employee_staff_request_confirmed", "main exception error",
                f"Error text: {str(e)}", {"employee_id": employee_id, "notification_id": notification_id}
            )
            return
        

async def execute_user_notify_employee_staff_request_rejected(employee_id : int, notification_id : int):
    logger.info(f"execute_user_notify_employee_staff_request_rejected - Employee ID: {employee_id}; Notification ID: {notification_id};")
    async with async_session() as session:        
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == employee_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_notify_employee_staff_request_rejected - User {employee_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"execute_user_notify_employee_staff_request_rejected - Notification {notification_id} not found")
                return

            updated_userinfo = await get_advanced_userinfo(employee_id)

            if updated_userinfo["status"]:
                userdata = updated_userinfo["userdata"]
                business_list = updated_userinfo["business_list"]
                notification_dict = notification.to_dict()
                if user.id == notification.receiver_user:
                    await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)
                await sio.emit("update_userinfo_and_business_list_hard", {"userdata": userdata, "business_list": business_list}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_notify_employee_staff_request_rejected - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_notify_employee_staff_request_rejected", "main exception error",
                f"Error text: {str(e)}", {"employee_id": employee_id, "notification_id": notification_id}
            )
            return
        

async def execute_user_notify_incoming_staff_request(employer_id : int, notification_id : int, business_update : dict):
    logger.info(f"execute_user_notify_incoming_staff_request - Employer ID: {employer_id}; Notification ID: {notification_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == employer_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_notify_incoming_staff_request - User {employer_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"execute_user_notify_incoming_staff_request - Notification {notification_id} not found")
                return
            notification_dict = notification.to_dict()
            
            if not business_update or not isinstance(business_update, dict):
                business_update = {}

            if user.id == notification.receiver_user:
                await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)
            await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)            
            await sio.emit("update_business_info_soft", {"business_update": business_update}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_notify_incoming_staff_request - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_notify_incoming_staff_request", "main exception error",
                f"Error text: {str(e)}", {"employer_id": employer_id, "notification_id": notification_id}
            )
            return
        

async def execute_user_notify_employee_staff_request_cancelled(employer_id : int, notification_id : int, business_update : dict):
    logger.info(f"user_notify_employee_staff_request_cancelled - Employer ID: {employer_id};  Notification ID: {notification_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == employer_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"user_notify_employee_staff_request_cancelled - User {employer_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"user_notify_employee_staff_request_cancelled - Notification {notification_id} not found")
                return
            notification_dict = notification.to_dict()
            
            if not business_update or not isinstance(business_update, dict):
                business_update = {}

            if user.id == notification.receiver_user:
                await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)
            await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)
            await sio.emit("update_business_info_soft", {"business_update": business_update}, to=user.sid)

            return

        except Exception as e:
            logger.exception("user_notify_employee_staff_request_cancelled - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "user_notify_employee_staff_request_cancelled", "main exception error",
                f"Error text: {str(e)}", {"employer_id": employer_id, "notification_id": notification_id}
            )
            return
        

async def execute_user_notify_employee_quit(employer_id : int, notification_id : int):
    logger.info(f"execute_user_notify_employee_quit - Employer ID: {employer_id}; Notification ID: {notification_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == employer_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_notify_employee_quit - User {employer_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"execute_user_notify_employee_quit - Notification {notification_id} not found")
                return

            updated_userinfo = await get_advanced_userinfo(employer_id)

            if updated_userinfo["status"]:
                userdata = updated_userinfo["userdata"]
                business_list = updated_userinfo["business_list"]
                notification_dict = notification.to_dict()
                if user.id == notification.receiver_user:
                    await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)                
                await sio.emit("update_userinfo_and_business_list_hard", {"userdata": userdata, "business_list": business_list}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_notify_employee_quit - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_notify_employee_quit", "main exception error",
                f"Error text: {str(e)}", {"employee_id": employer_id, "notification_id": notification_id}
            )
            return


async def execute_user_notify_business_deleted(employee_id : int, notification_id : int):
    logger.info(f"execute_user_notify_business_deleted - Employee ID: {employee_id}; Notification ID: {notification_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == employee_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_notify_business_deleted - User {employee_id} is not online")
                return
            
            notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalars().first()
            if not notification:
                logger.error(f"execute_user_notify_business_deleted - Notification {notification_id} not found")
                return

            updated_userinfo = await get_advanced_userinfo(employee_id)

            if updated_userinfo["status"]:
                userdata = updated_userinfo["userdata"]
                business_list = updated_userinfo["business_list"]
                notification_dict = notification.to_dict()
                if user.id == notification.receiver_user:
                    await sio.emit("add_user_notification", {"new_notification": notification_dict}, to=user.sid)                
                await sio.emit("update_userinfo_and_business_list_hard", {"userdata": userdata, "business_list": business_list}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_notify_business_deleted - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_notify_business_deleted", "main exception error",
                f"Error text: {str(e)}", {"employee_id": employee_id, "notification_id": notification_id}
            )
            return
        

async def execute_user_push_new_order(user_id: int, order_id: int):
    logger.info(f"execute_user_push_new_order - User ID: {user_id}; Order ID: {order_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_push_new_order - User {user_id} is not online")
                return
            
            order_dict_request = await get_order(order_id)
            order_dict = order_dict_request.get("order_dict", None)
            if not order_dict:
                logger.error(f"execute_user_push_new_order - Order {order_id} not found")
                return
            
            await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)
            await sio.emit("push_new_order_to_user_orderlist", {"new_order": order_dict}, to=user.sid)

            return

        except Exception as e:
            logger.exception("execute_user_push_new_order - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_push_new_order", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "order_id": order_id}
            )
            return
        

async def execute_user_update_existed_order(user_id: int, order_id: int, need_tab_notify: bool):
    logger.info(f"execute_user_update_existed_order - User ID: {user_id}; Order ID: {order_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_user_update_existed_order - User {user_id} is not online")
                return
            
            order_dict_request = await get_order(order_id)
            order_dict = order_dict_request.get("order_dict", None)
            if not order_dict:
                logger.error(f"execute_user_update_existed_order - Order {order_id} not found")
                return
            if need_tab_notify:
                await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)
            await sio.emit("push_updated_order_to_user_orderlist", {"updated_order": order_dict}, to=user.sid)
            return

        except Exception as e:
            logger.exception("execute_user_update_existed_order - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_update_existed_order", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "order_id": order_id}
            )
            return
        

async def execute_order_message_broadcast(user_id: int, message_id: int, need_tab_notify: bool):
    logger.info(f"execute_order_message_broadcast - User ID: {user_id}; Message ID: {message_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.error(f"execute_order_message_broadcast - User {user_id} is not online")
                return
                        
            message_dict_request = await get_message(user_id, message_id)
            
            chat_message = message_dict_request.get("chat_message", None)
            active_business_id = message_dict_request.get("active_business_id", None)

            if not chat_message or not active_business_id:
                logger.error(f"execute_order_message_broadcast - Message {message_id} not found")
                return
            order_name_for_messages_dict = message_dict_request.get("order_name_for_messages_dict", {})
            business_avatars_for_messages_dict = message_dict_request.get("business_avatars_for_messages_dict", {})
            
            await sio.emit("push_active_business_message", {
                    "chat_message": chat_message,
                    "order_name_for_messages_dict": order_name_for_messages_dict,
                    "business_avatars_for_messages_dict": business_avatars_for_messages_dict,
                    "active_business_id": active_business_id
                }, to=user.sid)
            
            if need_tab_notify:
                await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)
            
            
            return

        except Exception as e:
            logger.exception("execute_user_push_new_order - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_order_message_broadcast", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "message_id": message_id}
            )
            return
        

async def execute_user_update_info_after_successfull_payment(user_id: int, payment_id: int, need_tab_notify: bool):
    logger.info(f"execute_user_update_info_after_successfull_payment - User ID: {user_id}; Payment ID: {payment_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.info(f"execute_user_update_info_after_successfull_payment - User {user_id} is not online")
                return
            
            payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalars().first()
            if not payment:
                logger.error(f"execute_user_update_info_after_successfull_payment - Payment {payment} not found")
                return
            
            if not payment.processed:
                logger.error(f"execute_user_update_info_after_successfull_payment - Payment {payment} is not processed")
                return
                        
            payment_info = {
                "date": payment.date,
                "method_code": payment.method_code,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "credits_received": str(payment.credits_received)
            }            
                        
            await sio.emit("push_credits_after_successfull_payment", {
                    "payment_info": payment_info
                }, to=user.sid)
            
            if need_tab_notify:
                await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)                        
            return

        except Exception as e:
            logger.exception("execute_user_update_info_after_successfull_payment - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_update_info_after_successfull_payment", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "payment_id": payment_id}
            )
            return        


async def execute_user_update_info_after_successfull_payment(user_id: int, payment_id: int, need_tab_notify: bool):
    logger.info(f"execute_user_update_info_after_successfull_payment - User ID: {user_id}; Payment ID: {payment_id};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.info(f"execute_user_update_info_after_successfull_payment - User {user_id} is not online")
                return
            
            payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalars().first()
            if not payment:
                logger.error(f"execute_user_update_info_after_successfull_payment - Payment {payment} not found")
                return
            
            if not payment.processed:
                logger.error(f"execute_user_update_info_after_successfull_payment - Payment {payment} is not processed")
                return
                        
            payment_info = {
                "date": payment.date,
                "method_code": payment.method_code,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "credits_received": str(payment.credits_received),
                "updated_credits": str(user.credits)
            }            
                        
            await sio.emit("push_credits_after_successfull_payment", {"payment_info": payment_info}, to=user.sid)
            
            if need_tab_notify:
                await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)
                        
            return

        except Exception as e:
            logger.exception("execute_user_update_info_after_successfull_payment - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_update_info_after_successfull_payment", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "payment_id": payment_id}
            )
            return
        

async def execute_user_update_info_after_bonus_accural(user_id: int, payback_info: dict, need_tab_notify: bool):
    logger.info(f"execute_user_update_info_after_bonus_accural - User ID: {user_id}; Payment info: {payback_info};")
    async with async_session() as session:
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active.is_(True)))).scalars().first()
            if not user or not user.sid:
                logger.info(f"execute_user_update_info_after_bonus_accural - User {user_id} is not online")
                return
            
            referrar_id = payback_info.get("referrar_id", 0)
            referral_bonus_str = payback_info.get("referral_bonus", "0")
            referral_bonus = Decimal("0")
            try:
                referral_bonus = Decimal(referral_bonus_str)
            except Exception as not_number:
                logger.info(f"execute_user_update_info_after_bonus_accural - Exception: {not_number}")
                return
            
            if not (isinstance(referrar_id, int) and referrar_id > 0) or not (referral_bonus > Decimal("0")):
                logger.error(f"execute_user_update_info_after_bonus_accural - Payback data is incorrect: {payback_info}")
                return
                        
                        
            await sio.emit("push_referral_bonus_credits", {"payback_info": payback_info}, to=user.sid)
            
            if need_tab_notify:
                await sio.emit("update_user_tab_notify", {"tab_notify": user.tab_notify}, to=user.sid)
                        
            return

        except Exception as e:
            logger.exception("execute_user_update_info_after_bonus_accural - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "execute_user_update_info_after_bonus_accural", "main exception error",
                f"Error text: {str(e)}", {"user_id": user_id, "payback_info": payback_info}
            )
            return
        

async def execute_logout_inactive_users(user_ids: list):
    print(f"================== TEMP LOG - execute_logout_inactive_users ===========================")
    print(f"incoming user ids: {user_ids}")
    current_time_unix = int(datetime.now(timezone.utc).timestamp())
    logout_time = current_time_unix - INACTIVE_TIME_LOGOUT
    try:
        redis_ids_str = await redis_client.zrangebyscore(
            TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY,
            0,
            logout_time
        )
        redis_users_ids = [
            int(user_id)
            for user_id in redis_ids_str
        ]
    except Exception as e:
        logger.exception(f"execute_logout_inactive_users - CANNOT GETTING REDIS DATA: {e}") 
        await put_critical_error_into_db("execute_logout_inactive_users", "redis exception error", f"Error text: {str(e)}", {"user_ids": user_ids})        
        return
    if not redis_users_ids:
        logger.ingo(f"execute_logout_inactive_users - No user ids from Redis: {redis_users_ids}")
        return
    logged_out_user_ids = []    
    async with async_session() as session:
        try:
            users = await session.execute(
                select(AppUser).where(
                    AppUser.id.in_(user_ids),
                    AppUser.active.is_(True),
                    AppUser.instance_id == THIS_INSTANCE_ID
                )
            )

            users = users.scalars().all()            
            
            for user in users:
                if user.id in redis_users_ids:
                    logged_out_user_ids.append(user.id)                            

        except Exception as e:
            logger.exception("execute_logout_inactive_users - READ SESSION EXCEPTION ERROR") 
            await put_critical_error_into_db("execute_logout_inactive_users", "main exception error", f"Error text: {str(e)}", {"user_ids": user_ids})
            return
    if not logged_out_user_ids:
        return
    
    async with async_session() as update_session:
        try:
            sids_to_logout = None
            ids_to_logout = None
            async with update_session.begin():

                users = await update_session.execute(
                    select(AppUser)
                    .where(
                        AppUser.id.in_(logged_out_user_ids),
                        AppUser.instance_id == THIS_INSTANCE_ID,
                        AppUser.active.is_(True)
                    )
                    .with_for_update()
                )

                users = users.scalars().all()

                ids_to_logout = [u.id for u in users]
                sids_to_logout = [u.sid for u in users if u.sid]

                if ids_to_logout:
                    await update_session.execute(
                        update(AppUser)
                        .where(AppUser.id.in_(ids_to_logout), AppUser.instance_id == THIS_INSTANCE_ID)
                        .values(
                            instance_id="",
                            sid=""
                        )
                    )
                    
            if ids_to_logout:
                await redis_client.zrem(TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY, *ids_to_logout)

            if sids_to_logout:
                for sid in sids_to_logout:
                    await sio.emit("logout_inactive_user", {}, to=sid)
            
            return
        except Exception as e:
            logger.exception("execute_logout_inactive_users - UPDATE SESSION EXCEPTION ERROR") 
            await put_critical_error_into_db("execute_logout_inactive_users", "main exception error", f"Error text: {str(e)}", {"user_ids": user_ids})
            return
        

async def send_push_notification_business_tariff_plan_changed_to_free(business_ids: list, interested_users: list):
    print(f"================== TEMP LOG - send_push_notification_business_tariff_plan_changed_to_free ===========================")
    print(f"incoming interested_users ids: {interested_users}; Incoming business_ids: {business_ids}")
    
    async with async_session() as session:
        try:            
            if not isinstance(interested_users, list) or not interested_users:
                return

            users = (
                await session.execute(
                    select(AppUser).where(
                        AppUser.id.in_(interested_users),
                        AppUser.active.is_(True),
                        AppUser.instance_id == THIS_INSTANCE_ID,
                        AppUser.sid != "",
                        AppUser.sid.is_not(None)
                    )
                )
            ).scalars().all()

            actual_businesslist = []
            notifications = []
            set_business_ids = set(business_ids)

            for user in users:                
                if user.active_business_id in business_ids and user.active_business_id in user.business_list:
                    actual_businesslist.append(user.active_business_id)
                    n = {
                        "user_id": user.id,
                        "notification_type": "for_owner_active",
                        "business_id": user.active_business_id,
                        "sid": user.sid
                    }
                    notifications.append(n)
                if len(set(user.business_list) & set_business_ids) > 0:
                    for user_business_id in user.business_list:
                        if user_business_id in business_ids and user_business_id != user.active_business_id:
                            actual_businesslist.append(user_business_id)
                            n = {
                                "user_id": user.id,
                                "notification_type": "for_owner_inactive",
                                "business_id": user_business_id,
                                "sid": user.sid
                            }
                            notifications.append(n)
                if user.active_business_id in business_ids and user.active_business_id not in user.business_list:
                    actual_businesslist.append(user.active_business_id)
                    n = {
                        "user_id": user.id,
                        "notification_type": "for_staff_active",
                        "business_id": user.active_business_id,
                        "sid": user.sid
                    }
                    notifications.append(n)
                    
            actual_businesslist = list(set(actual_businesslist))
            businesses = (
                await session.execute(
                    select(Business).where(
                        Business.id.in_(actual_businesslist)
                    )
                )
            ).scalars().all()

            business_names = {}
            for b in businesses:
                business_names[b.id] = b.name

            for n in notifications:                
                sid = n.get("sid")                
                data = {
                    "type": n.get("notification_type"),
                    "business_id": n.get("business_id"),
                    "business_name": business_names.get(n.get("business_id"))
                }
                await sio.emit("push_notification_paid_subscription_ended", data, to=sid)
            
            return
        except Exception as e:
            logger.exception("send_push_notification_business_tariff_plan_changed_to_free - UPDATE SESSION EXCEPTION ERROR") 
            await put_critical_error_into_db("send_push_notification_business_tariff_plan_changed_to_free", "main exception error", f"Error text: {str(e)}", {"user_ids": interested_users, "business_ids": business_ids})
            return
        

async def send_push_notification_and_update_credits_for_stars(user_id: int, added_credits: str, updated_credits: str):
    async with async_session() as session:
        async with session.begin():
            try:
                user = (await session.execute(select(AppUser).where(
                    AppUser.id == user_id, 
                    AppUser.instance_id == THIS_INSTANCE_ID, 
                    AppUser.active.is_(True),
                    AppUser.sid.is_not(None),
                    AppUser.sid != ""
                ))).scalars().first()                
                if not user:                    
                    return

                await sio.emit("push_notification_and_update_credits_for_stars", {"added_credits": added_credits, "updated_credits": updated_credits}, to=user.sid)
            
                return

            except Exception as e:
                logger.exception("send_push_notification_and_update_credits_for_stars - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db( "send_push_notification_and_update_credits_for_stars", "main exception error", f"Error text: {str(e)}", {"user_id": user_id})
                return
