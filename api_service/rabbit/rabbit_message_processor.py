import os
import socket
from config import settings
LOGOUT_TIMEOUT = settings.LOGOUT_TIMEOUT 
REQUEST_BATCH_SIZE = settings.REQUEST_BATCH_SIZE
RABBIT_MESSAGE_LIST_LIMIT = settings.RABBIT_MESSAGE_LIST_LIMIT
INSTANCE_ID = settings.INSTANCE_ID
THIS_SERVICE_NAME = settings.API_SERVICE_NAME


from session_config import async_session

from models.app_users import AppUser
from sqlalchemy.future import select
from sqlalchemy import exists
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm.attributes import flag_modified

from sqlalchemy.orm import aliased

import asyncio

from logger_config import get_logger
from api_endpoints.ws import sio

from .rabbit_fuctions import *
from .rabbit_sender import broadcast_message_async

from payments.telegram_star import star_payment_processing

from payments.paypal import check_paypal_order, capture_paypal_order

import json

logger = get_logger(__name__)

        
async def message_processing(full_message):
    logger.info(f"RABBIT message_processing - current service: {THIS_SERVICE_NAME} current instance: {INSTANCE_ID}; Received message: {full_message}")

    if not isinstance(full_message, dict):
        logger.error(f"Recieved Rabbit MQ message is incorrect")
        return
    
    if full_message.get("receiver", None) != THIS_SERVICE_NAME:
        logger.debug(f"This Service is not actual. Recieved Rabbit MQ message was ignored...")
        return
    
    if full_message.get("receiver_id", None) != INSTANCE_ID and full_message.get("receiver_id", None) != 'all' and full_message.get("receiver_id", None) != 'any':
        logger.debug(f"This POD ID is not actual. Recieved Rabbit MQ message was ignored...")
        return
    
    message = full_message.get("message", None)
    if message is None or not isinstance(message, dict):
        logger.error(f"Recieved Rabbit MQ sub-message is incorrect")
        return    
    
    msg_type = message.get("type")
    description = message.get("description")

    if msg_type == "execute" and description == "logout_user_frontend_by_sid":    
        sid = message.get("sid", None)
        await new_login_user_logout(sid)
        return                
    
    if msg_type == "execute" and description == "user_notify_business_deleted":
        employee_id = message.get("employee_id", None)
        notification_id = message.get("notification_id", None)
        await execute_user_notify_business_deleted(employee_id=employee_id, notification_id=notification_id)
        return    

    if msg_type == "execute" and description == "user_notify_employee_quit":
        employer_id = message.get("employer_id", None)
        notification_id = message.get("notification_id", None)
        await execute_user_notify_employee_quit(employer_id=employer_id, notification_id=notification_id)
        return

    if msg_type == "execute" and description == "user_notify_employee_staff_request_cancelled":
        employer_id = message.get("employer_id", None)
        notification_id = message.get("notification_id", None)
        business_update = message.get("business_update", {})
        await execute_user_notify_employee_staff_request_cancelled(employer_id=employer_id, notification_id=notification_id, business_update=business_update)
        return

    if msg_type == "execute" and description == "user_notify_incoming_staff_request":
        employer_id = message.get("employer_id", None)
        notification_id = message.get("notification_id", None)
        business_update = message.get("business_update", {})
        await execute_user_notify_incoming_staff_request(employer_id=employer_id, notification_id=notification_id, business_update=business_update)
        return    

    if msg_type == "execute" and description == "user_notify_employee_staff_request_rejected":
        employee_id = message.get("employee_id", None)
        notification_id = message.get("notification_id", None)
        await execute_user_notify_employee_staff_request_rejected(employee_id=employee_id, notification_id=notification_id)
        return
    
    if msg_type == "execute" and description == "user_notify_employee_staff_request_confirmed":
        employee_id = message.get("employee_id", None)
        notification_id = message.get("notification_id", None)
        await execute_user_notify_employee_staff_request_confirmed(employee_id=employee_id, notification_id=notification_id)
        return

    if msg_type == "execute" and description == "user_notify_employee_fired_for_employee":
        employee_id = message.get("employee_id", None)
        notification_id = message.get("notification_id", None)
        await execute_user_notify_employee_fired_for_employee(employee_id=employee_id, notification_id=notification_id)
        return    

    if msg_type == "execute" and description == "push_new_product_to_catalog_supplier":
        user_id = message.get("user_id", None)
        product_id = message.get("product_id", None)
        await execute_push_new_product_to_catalog_supplier(user_id=user_id, product_id=product_id)
        return
    
    if msg_type == "execute" and description == "update_tab_notify":
        user_id = message.get("user_id", None)
        await execute_update_tab_notify(user_id=user_id)
        return
    
    if msg_type == "execute" and description == "user_push_new_order":
        user_id = message.get("user_id", None)
        order_id = message.get("order_id", None)
        await execute_user_push_new_order(user_id=user_id, order_id=order_id)
        return
    
    if msg_type == "execute" and description == "user_update_existed_order":
        user_id = message.get("user_id", None)
        order_id = message.get("order_id", None)
        need_tab_notify = message.get("need_tab_notify", True)
        await execute_user_update_existed_order(user_id=user_id, order_id=order_id, need_tab_notify=need_tab_notify)
        return
    
    if msg_type == "execute" and description == "order_message_broadcast":
        user_id = message.get("user_id", None)
        message_id = message.get("message_id", None)
        need_tab_notify = message.get("need_tab_notify", True)
        await execute_order_message_broadcast(user_id=user_id, message_id=message_id, need_tab_notify=need_tab_notify)
        return
    
    if msg_type == "execute" and description == "user_update_info_after_successfull_payment":        
        user_id = message.get("user_id", None)
        payment_id = message.get("payment_id", None)
        need_tab_notify = message.get("need_tab_notify", True)
        await execute_user_update_info_after_successfull_payment(user_id=user_id, payment_id=payment_id, need_tab_notify=need_tab_notify)
        return
    
    if msg_type == "execute" and description == "user_update_info_after_bonus_accural":        
        user_id = message.get("user_id", None)
        payback_info = message.get("payback_info", None)
        need_tab_notify = message.get("need_tab_notify", True)
        await execute_user_update_info_after_bonus_accural(user_id=user_id, payback_info=payback_info, need_tab_notify=need_tab_notify)
        return
    
    if msg_type == "execute" and description == "logout_inactive_users":
        user_ids = message.get("user_ids", [])
        await execute_logout_inactive_users(user_ids=user_ids)
        return
    
    if msg_type == "push_notification" and description == "business_tariff_plan_changed_to_free":
        print(f"=========== TEMP LOG - business_tariff_plan_changed_to_free ======================\n")
        business_ids = message.get("business_ids", [])
        interested_users = message.get("interested_users", [])
        await send_push_notification_business_tariff_plan_changed_to_free(business_ids=business_ids, interested_users=interested_users)
        return
    
    if msg_type == "execute" and description == "star_payment_processing":
        user_id = message.get("user_id", None)
        charge_id = message.get("charge_id", None)
        star_payment_id = message.get("star_payment_id", None)
        process_payment = await star_payment_processing(user_id=user_id, charge_id=charge_id, star_payment_id=star_payment_id)
        if process_payment["status"]:
            user_id = process_payment.get("user_id")
            updated_credits = str(process_payment.get("updated_credits"))
            added_credits = str(process_payment.get("added_credits"))
            user_is_here = process_payment.get("user_is_here")
            if user_is_here:
                await send_push_notification_and_update_credits_for_stars(user_id=user_id, added_credits=added_credits, updated_credits=updated_credits)
            else:
                message = {
                    "sender": THIS_SERVICE_NAME,
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": "all",
                    "message": { 
                        "type": "push_notification",
                        "description": "update_credits_for_stars",
                        "user_id": user_id,
                        "added_credits": added_credits,
                        "updated_credits": updated_credits
                        
                    }
                }            
                await broadcast_message_async(message=message)
        return    

    if msg_type == "push_notification" and description == "update_credits_for_stars":
        print(f"=========== TEMP LOG - update_credits_for_stars ======================\n {message}")        
        user_id = message.get("user_id")
        updated_credits = message.get("updated_credits")
        added_credits = message.get("added_credits")
        await send_push_notification_and_update_credits_for_stars(user_id=user_id, added_credits=added_credits, updated_credits=updated_credits)
        return
    
    
    print(f"====================================================================================\n")
    if msg_type == "execute" and description == "test_planner":
        data = message.get("test_data", "No test data")
        print(f"====================================================================================\n")
        print(f"====================================================================================\n")
        print(f"=========================== PLANNER SERVICE TEST ===================================\n")
        print(f"====================================================================================\n")
        print(f"====================================================================================\n")
        
        return
    
        





    
    
        



