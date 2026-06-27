from fastapi import APIRouter, UploadFile, File, Form, Request, Response
from pydantic import BaseModel

import json
import base64

from services.auth import tma_boot_application, user_login_tma, user_register_tma
from services.userdata import (
    business_register, individual_register, business_update, get_business_profile, get_advanced_userinfo, add_reply_for_business_review, fire_employee, confirm_employee, 
    reject_employee, change_app_settings, change_active_business, join_staff_request_create, join_staff_request_delete, self_fire_from_active_business, delete_business,
    change_business_favorite_status, change_product_favorite_status, add_reply_for_product_review, set_filters_supplier_catalog, set_filters_customer_catalog,
    set_filters_individual_catalog, set_filters_business_messages, set_filters_business_orders, get_counter_agent_businesses_bundle, set_filters_counter_agents_serach,
    add_user_phone_number, get_user_public_profile, change_user_username, update_referral_list
    )
from services.items import (
    add_new_product_to_catalog, get_product, get_product_review_list, update_product, delete_product, get_start_app_customer_products_request, 
    get_customer_products_request_bundle, get_individual_products_request_bundle
    )
from services.order_actions import make_order, do_order_action, get_order, rate_order, check_permission_for_generate_excel_file
from services.user_action_log import add_user_action_log
from services.interfaces import get_interface
from services.jwt_token import verify_and_refresh_jwt_token_http
from services.verify import verify_phone_payload
from services.ad_campaing import start_ad_campaign, delete_ad_campaign, prolong_ad_campaign
from services.tariff import change_tariff_plan, renew_tariff_plan
from services.guard import bad_verification_fallout

from payments.payments import get_payment_redirect_link, process_confirmed_payment, get_payment_stars_invoice_link
from payments.free_promo import get_free_credits
from payments.paypal import capture_paypal_order, check_paypal_order_completed

from rabbit.rabbit_sender import broadcast_message_async, direct_task_async
from rabbit.send_preparing import (
    preparing_push_new_product_to_catalog_supplier, preparing_user_notify_employee_fired_for_employee, preparing_user_notify_employee_staff_request_confirmed, 
    preparing_user_notify_employee_staff_request_rejected, preparing_user_notify_incoming_staff_request, preparing_user_notify_employee_staff_request_cancelled,
    preparing_user_notify_employee_quit, preparing_users_notify_business_deleted, preparing_push_new_order_to_business_orders, preparing_chat_message_broadcast,
    preparing_push_updated_order_to_users, preparing_user_update_info_after_successfull_payment, preparing_user_update_info_after_bonus_accural
    )

from rediska.redis_cli import redis_client
from rediska.order_data import queue_add_product_ordered_quantity


from constants.log_entitys import USER_LOGIN, USER_REGISTER, TELEGRAM_ID, USER_LOGOUT
from constants.payments import PAYPAL_WEBHOOK_EVENT_ORDER_APPROVED, PAYPAL_WEBHOOK_ALLOWED_EVENTS
from constants.redis_vars import PAYPAL_ORDERS_CAPTURE_ON_AIR

from config import settings
THIS_SERVICE_NAME = settings.API_SERVICE_NAME
BOT_SERVICE_NAME = settings.BOT_SERVICE_NAME


from logger_config import get_logger
logger = get_logger(__name__)

router = APIRouter()

from fastapi.responses import StreamingResponse

from .ws import sio

class StartAppRequest(BaseModel):    
    tg_hash_data: str


@router.post("/api/tma_start_app_request")
async def tma_start_app_request(request: StartAppRequest):
    try:
        decoded = base64.b64decode(request.tg_hash_data).decode()
        logger.info(f"Getting Start request: tg_hash_data:{decoded}")
        boot_application = await tma_boot_application(decoded)
        if boot_application["status"]:
            logger.info(f"Start App response data: STATUS TRUE")
            return boot_application
        else:
            return boot_application
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"status": False, "message": "FUNCTION start_app_request EXCEPTION ERROR"}
    

@router.post("/api/http_tma_user_login")
async def http_tma_user_login(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_tma_user_login - incoming data: {data_obj}")
        tg_hash_data_64 = data_obj["tg_hash_data"]
        ip_address = data_obj["ip_address"]
        sid = data_obj["sid"]
        response = await user_login_tma(sid, ip_address, tg_hash_data_64)

        if response['status']:
            
            user_id = response["userdata"].get("id", None)
            if user_id:
                advanced_userinfo = await get_advanced_userinfo(user_id)
                if advanced_userinfo["status"]:                    
                    response["advanced_info"] = True
                    response["userdata"] = advanced_userinfo["userdata"]
                    response["business_list"] = advanced_userinfo["business_list"]
                    response["ad_campaign_list"] = advanced_userinfo["ad_campaign_list"]
                else:
                    response["advanced_info"] = False
            # User action logging
            log_data = response.get("log_data", {})
            log_data["ip_address"] = data_obj.get("ip_address", "")
            if log_data.get("action_type", None) is None:
                log_data["action_type"] = "ENDPOINT /api/http_tma_user_login"
            await add_user_action_log(log_data)

        return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_tma_user_login EXCEPTION ERROR"}
    

@router.post("/api/http_tma_user_register")
async def http_tma_user_register(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_tma_user_login - incoming data: {data_obj}")
        tg_hash_data_64 = data_obj["tg_hash_data"]
        ip_address = data_obj["ip_address"]
        sid = data_obj["sid"]
        user_register_response = await user_register_tma(ip_address, tg_hash_data_64)

        if user_register_response['status']:
            
            response = await user_login_tma(sid, ip_address, tg_hash_data_64)
            if response['status']:            
                user_id = response["userdata"].get("id", None)
                if user_id:
                    advanced_userinfo = await get_advanced_userinfo(user_id)
                    if advanced_userinfo["status"]:                    
                        response["advanced_info"] = True
                        response["userdata"] = advanced_userinfo["userdata"]
                        response["business_list"] = advanced_userinfo["business_list"]
                    else:
                        response["advanced_info"] = False
                # User action logging
                log_data = response.get("log_data", {})
                log_data["ip_address"] = data_obj.get("ip_address", "")
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/http_tma_user_login"
                await add_user_action_log(log_data)
            return response
        
        else:
            if user_register_response.get("blacklist", False):
                return user_register_response
            else:
                response = {"status": False, "notify_type": "error", "notify_code": "notify_error_registration_error"}
                return response
        
    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_tma_user_register EXCEPTION ERROR"}


@router.post("/api/business_register")
async def http_business_register(
    data: str = Form(...),
    avatar: UploadFile | None = File(None)
):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_business_register - Business data: {data_obj}")                
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]
        register_data = {
            "name": data_obj["name"],
            "description": data_obj["description"],
            "type": data_obj["type"],
            "geodata": data_obj["geodata"],
            "address": data_obj["address"],
            "currency": data_obj["currency"],
            "language": data_obj["language"],
            "timezone": data_obj["timezone"],
            "schedule": data_obj["schedule"]
        }        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:

            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_business_register - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_business_register - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            response = await business_register(user_id, register_data, avatar)
            logger.info(f"http_business_register - business_register returns: {response} ", user_id=user_id)
            
            response["jwt_token"] = new_token

            if response['status']:
                info_for_update = await get_advanced_userinfo(user_id)
                response["info_for_update"] = info_for_update
                # User action logging
                log_data = response.get("log_data", {})
                log_data["ip_address"] = data_obj.get("ip_address", "")
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/business_register"
                await add_user_action_log(log_data)

            return response

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_business_register EXCEPTION ERROR"
        }
    

@router.post("/api/individual_register")
async def http_individual_register(
    data: str = Form(...),
    avatar: UploadFile | None = File(None)
):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_individual_register - Business data: {data_obj}")                
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]

        telegram_avatar_url = data_obj["telegram_avatar_url"]
        
        register_data = {
            "name": data_obj["name"],
            "currency": data_obj["currency"],            
            "timezone": data_obj["timezone"],
            "geodata": data_obj["geodata"]
        }        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_individual_register - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_individual_register - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            response = await individual_register(user_id=user_id, data=register_data, telegram_avatar_url=telegram_avatar_url, avatar=avatar)
            logger.info(f"http_individual_register - individual_register returns: {response} ", user_id=user_id)
            
            response["jwt_token"] = new_token

            if response['status']:
                info_for_update = await get_advanced_userinfo(user_id)
                response["info_for_update"] = info_for_update
                # User action logging
                log_data = response.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/individual_register"
                await add_user_action_log(log_data)

            return response

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_individual_register EXCEPTION ERROR"
        }


@router.post("/api/get_business_profile")
async def http_get_business_profile(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_get_business_profile - incoming data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        ip_address = data_obj["ip_address"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_get_business_profile - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {"status": False, "message": "http_get_business_profile - JWT verify is False"}
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_business = await get_business_profile(user_id, business_id)

            #logger.info(f"http_get_business_profile - business_update returns: {updated_business}", user_id=user_id)
            response = updated_business
            response["jwt_token"] = new_token
                
            return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_get_business_profile EXCEPTION ERROR"}


@router.post("/api/send_reply_for_business_review")
async def http_send_reply_for_business_review(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_send_reply_for_business_review - incoming data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        ip_address = data_obj["ip_address"]
        user_id = data_obj["user_id"]
        comment_id = data_obj["comment_id"]
        reply_text = data_obj["reply_text"]
        business_id = data_obj["business_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_send_reply_for_business_review - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {"status": False, "message": "http_send_reply_for_business_review - JWT verify is False"}
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            reply_added = await add_reply_for_business_review(user_id, business_id, comment_id, reply_text)
            if reply_added["status"]:

                log_data = reply_added.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/send_reply_for_business_review"
                await add_user_action_log(log_data)

                updated_business = await get_business_profile(user_id, business_id)                
                if updated_business["status"]:
                    response = updated_business
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_reply_added_but_not_reloaded"
                    }
            else:
                response = reply_added            
            
            response["jwt_token"] = new_token
            return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_send_reply_for_business_review EXCEPTION ERROR"}
    

@router.post("/api/business_update")
async def http_business_update(
    data: str = Form(...),
    avatar: UploadFile | None = File(None)
):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        #logger.info(f"http_business_update - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]
        ip_address = data_obj["ip_address"]

        update_data = {
            "add_languages": data_obj["add_languages"],
            "description": data_obj["description"],
            "address": data_obj["address"],
            "timezone": data_obj["timezone"],
            "geodata": data_obj["geodata"],
            "schedule": data_obj["schedule"],
            "local_names": data_obj["local_names"],
            "currency": data_obj["currency"]
        }

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_business_update - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_business_update - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            updated_business = await business_update(user_id, business_id, update_data, avatar)
            if updated_business["status"]:

                log_data = updated_business.get("log_data", {})
                log_data["ip_address"] = data_obj.get("ip_address", "")
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/business_update"
                await add_user_action_log(log_data)

                business_refresh = await get_business_profile(user_id, business_id)                
                if business_refresh["status"]:
                    response = business_refresh
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_business_updated_but_not_reloaded"
                    }
            else:
                response = updated_business
            
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_business_update EXCEPTION ERROR"
        }
    

@router.post("/api/fire_employee")
async def http_fire_employee(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_fire_employee - incoming data: {data_obj}")
        
        jwt_token = data_obj["jwt_token"]
        ip_address = data_obj["ip_address"]
        user_id = data_obj["user_id"]        
        business_id = data_obj["business_id"]
        employee_id = data_obj["employee_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_fire_employee - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {"status": False, "message": "http_fire_employee - JWT verify is False"}
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            employee_fired = await fire_employee(user_id, business_id, employee_id)
            
            if employee_fired["status"]:                
                
                log_data = employee_fired.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/fire_employee"
                await add_user_action_log(log_data)

                business_refresh = await get_business_profile(user_id, business_id)                
                if business_refresh["status"]:
                    response = business_refresh
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_employee_fired_but_not_reloaded"
                    }

                preparing = await preparing_user_notify_employee_fired_for_employee(business_id=business_id, employee_id=employee_id)
                if preparing["status"]:
                    rabbit_message = preparing.get("rabbit_message", None)                    
                    if rabbit_message:
                        await broadcast_message_async(rabbit_message)                    
                else:
                    logger.error(f"http_fire_employee - cannot prepare sending message(s) for RABBIT", user_id=user_id)                

            else:
                response = employee_fired
            
            response["jwt_token"] = new_token
            return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_fire_employee EXCEPTION ERROR"}
    

@router.post("/api/confirm_employee")
async def http_confirm_employee(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_confirm_employee - incoming data: {data_obj}")
        
        jwt_token = data_obj["jwt_token"]
        ip_address = data_obj["ip_address"]
        user_id = data_obj["user_id"]        
        business_id = data_obj["business_id"]
        employee_id = data_obj["employee_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_confirm_employee - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {"status": False, "message": "http_confirm_employee - JWT verify is False"}
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            employee_confirmed = await confirm_employee(user_id, business_id, employee_id)
            
            if employee_confirmed["status"]:

                log_data = employee_confirmed.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/confirm_employee"
                await add_user_action_log(log_data)

                business_refresh = await get_business_profile(user_id, business_id)                
                if business_refresh["status"]:
                    response = business_refresh
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_employee_confirmed_but_not_reloaded"
                    }

                preparing = await preparing_user_notify_employee_staff_request_confirmed(employee_id=employee_id, business_id=business_id)
                if preparing["status"]:
                    rabbit_message = preparing.get("rabbit_message", None)
                    if rabbit_message:
                        await broadcast_message_async(rabbit_message)
                else:
                    logger.error(f"http_confirm_employee - cannot prepare sending message(s) for RABBIT", user_id=user_id)

            else:
                response = employee_confirmed
            
            response["jwt_token"] = new_token
            return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_confirm_employee EXCEPTION ERROR"}
    

@router.post("/api/reject_employee")
async def http_reject_employee(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_reject_employee - incoming data: {data_obj}")
        
        jwt_token = data_obj["jwt_token"]
        ip_address = data_obj["ip_address"]
        user_id = data_obj["user_id"]        
        business_id = data_obj["business_id"]
        employee_id = data_obj["employee_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_reject_employee - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {"status": False, "message": "http_reject_employee - JWT verify is False"}
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            employee_rejected = await reject_employee(user_id, business_id, employee_id)
            
            if employee_rejected["status"]:

                log_data = employee_rejected.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/reject_employee"
                await add_user_action_log(log_data)

                business_refresh = await get_business_profile(user_id, business_id)
                if business_refresh["status"]:
                    response = business_refresh
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_employee_rejected_but_not_reloaded"
                    }

                preparing = await preparing_user_notify_employee_staff_request_rejected(employee_id=employee_id, business_id=business_id)
                if preparing["status"]:
                    rabbit_message = preparing.get("rabbit_message", None)
                    if rabbit_message:
                        await broadcast_message_async(rabbit_message)
                else:
                    logger.error(f"http_reject_employee - cannot prepare sending message(s) for RABBIT", user_id=user_id)                

            else:
                response = employee_rejected
            
            response["jwt_token"] = new_token
            return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_reject_employee EXCEPTION ERROR"}
    

@router.post("/api/change_app_settings")
async def http_change_app_settings(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        #logger.info(f"http_business_update - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        changed_settings = data_obj["changed_settings"]
        ip_address = data_obj["ip_address"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_change_app_settings - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_change_app_settings - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_settings = await change_app_settings(user_id, changed_settings)
            if updated_settings["status"]:                                
                response = updated_settings
            else:
                response = updated_settings
            
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_business_update EXCEPTION ERROR"
        }
    

@router.post("/api/change_active_business")
async def http_change_active_business(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_change_active_business - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]
        ip_address = data_obj["ip_address"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_change_active_business - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_change_active_business - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_business = await change_active_business(user_id, business_id)
            if updated_business["status"]:                                
                response = updated_business
            else:
                response = updated_business
            
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_change_active_business EXCEPTION ERROR"
        }


@router.post("/api/join_staff_self_request")
async def http_join_staff_self_request(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_join_staff_self_request - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]
        ip_address = data_obj["ip_address"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:

            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_join_staff_self_request - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_join_staff_self_request - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            request_created = await join_staff_request_create(user_id=user_id, business_id=business_id, employer_id=None)
            if request_created["status"]:                                
                response = request_created

                preparing = await preparing_user_notify_incoming_staff_request(business_id=business_id, employee_id=user_id)
                if preparing["status"]:
                    rabbit_message = preparing.get("rabbit_message", None)
                    if rabbit_message:
                        await broadcast_message_async(rabbit_message)
                else:
                    logger.error(f"http_join_staff_self_request - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
            else:
                response = request_created                
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_join_staff_self_request EXCEPTION ERROR"
        }
    

@router.post("/api/join_staff_self_request_delete")
async def http_join_staff_self_request_delete(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_join_staff_self_request_delete - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_join_staff_self_request_delete - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_join_staff_self_request_delete - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            request_deleted = await join_staff_request_delete(user_id=user_id)
            if request_deleted["status"]:                                
                response = request_deleted
                business_id = request_deleted.get("business_id", 0)

                preparing = await preparing_user_notify_employee_staff_request_cancelled(employee_id=user_id, business_id=business_id)
                if preparing["status"]:
                    rabbit_message = preparing.get("rabbit_message", None)
                    if rabbit_message:
                        await broadcast_message_async(rabbit_message)
                else:
                    logger.error(f"http_join_staff_self_request - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
            else:
                response = request_deleted                
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_join_staff_self_request_delete EXCEPTION ERROR"
        }



@router.post("/api/self_fire_from_active_business")
async def http_self_fire_from_active_business(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_self_fire_from_active_business - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]
        ip_address = data_obj["ip_address"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_self_fire_from_active_business - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_self_fire_from_active_business - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            quit_successful = await self_fire_from_active_business(user_id=user_id, business_id=business_id)
            
            if quit_successful["status"]:                
                info_for_update = await get_advanced_userinfo(user_id)
                if info_for_update["status"]:
                    response = info_for_update
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_qiut_successfull_but_not_updated"
                    }

                preparing = await preparing_user_notify_employee_quit(business_id=business_id, employee_id=user_id)
                if preparing["status"]:
                    rabbit_message = preparing.get("rabbit_message", None)
                    if rabbit_message:
                        await broadcast_message_async(rabbit_message)
                else:
                    logger.error(f"http_self_fire_from_active_business - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
            else:
                response = quit_successful
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_self_fire_from_active_business EXCEPTION ERROR"
        }
    

@router.post("/api/delete_business")
async def http_delete_business(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_delete_business - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]
        ip_address = data_obj["ip_address"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_delete_business - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_delete_business - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            business_deleted = await delete_business(user_id=user_id, business_id=business_id)
            
            if business_deleted["status"]:                
                info_for_update = await get_advanced_userinfo(user_id)
                if info_for_update["status"]:
                    response = info_for_update
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_delete_business_successfull_but_not_updated"
                    }

                ex_staff = business_deleted.get("ex_staff", [])

                preparing = await preparing_users_notify_business_deleted(business_id=business_id, employees=ex_staff)
                if preparing["status"]:
                    rabbit_messages = preparing.get("rabbit_messages", None)
                    if rabbit_messages:
                        for message in rabbit_messages:
                            await broadcast_message_async(message)
                else:
                    logger.error(f"http_delete_business - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
            else:
                response = business_deleted
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_delete_business EXCEPTION ERROR"
        }
    


@router.post("/api/add_new_product_to_catalog")
async def http_add_new_product_to_catalog(
    data: str = Form(...),
    avatar: UploadFile | None = File(None)
):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_add_new_product_to_catalog - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        business_id = data_obj["business_id"]
        ip_address = data_obj["ip_address"]

        product_data = {
            "name": data_obj.get("name", None),
            "description": data_obj.get("description", None),
            "measure_code": data_obj.get("measure_code", None),
            "pack_params": data_obj.get("pack_params", None),
            "price": data_obj.get("price", None),
            "min_order": data_obj.get("min_order_quantity", None),
            "max_order": data_obj.get("max_order_quantity", None),
            "sku": data_obj.get("sku", None),
            "category_code": data_obj.get("category_code", None),
            "daily_limit": data_obj.get("daily_limit", None),
            "individual_customer": data_obj.get("individual_customer", False),
            "shipment_same_day": data_obj.get("shipment_same_day", False),
            "shipment_hours": data_obj.get("shipment_hours", None),
            "shipment_price": data_obj.get("shipment_price", None)
        }

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)

            logger.warning(f"http_add_new_product_to_catalog - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_add_new_product_to_catalog - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            product_created = await add_new_product_to_catalog(user_id=user_id, business_id=business_id, product_data=product_data, avatar=avatar)
            
            if product_created["status"]:

                log_data = product_created.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/http_add_new_product_to_catalog"
                await add_user_action_log(log_data)

                # new_product = product_created.get("new_product")
                new_product_id = product_created.get("new_product_id")
                new_product_request = await get_product(user_id=user_id, product_id=new_product_id)
                if new_product_request["status"]:
                    new_product = new_product_request.get("product_dict", None)
                else:
                    new_product = None

                if new_product:
                    response = {
                        "status": True,
                        "new_product": new_product
                    }
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_product_created_but_not_updated"
                    }
                
                new_product_id = new_product.get("id", None)
                if new_product_id:
                    preparing = await preparing_push_new_product_to_catalog_supplier(business_id=business_id, product_id=new_product_id)
                    if preparing["status"]:
                        rabbit_messages_add_product = preparing.get("rabbit_messages_add_product", None)
                        rabbit_messages_update_tab_notify = preparing.get("rabbit_messages_update_tab_notify", None)
                        if rabbit_messages_add_product:
                            for message in rabbit_messages_add_product:
                                await broadcast_message_async(message)
                        if rabbit_messages_update_tab_notify:
                            for message in rabbit_messages_update_tab_notify:
                                await broadcast_message_async(message)
                    else:
                        logger.error(f"http_add_new_product_to_catalog - cannot prepare sending message(s) for RABBIT", user_id=user_id)                        
                
            else:
                response = product_created

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_add_new_product_to_catalog - EXCEPTION ERROR"
        }
    

@router.post("/api/change_business_favorite_status")
async def http_change_business_favorite_status(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_change_business_favorite_status - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]

        business_id = data_obj["business_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_change_business_favorite_status - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_change_business_favorite_status - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            favorite_upadted = await change_business_favorite_status(user_id=user_id, business_id=business_id)
            
            if favorite_upadted["status"]:                
                response = favorite_upadted
            else:
                response = favorite_upadted
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_change_business_favorite_status EXCEPTION ERROR"
        }
    
    
@router.post("/api/change_product_favorite_status")
async def http_change_product_favorite_status(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_change_product_favorite_status - Business data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]

        product_id = data_obj["product_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_change_product_favorite_status - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_change_product_favorite_status - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            favorite_upadted = await change_product_favorite_status(user_id=user_id, product_id=product_id)
            
            if favorite_upadted["status"]:                
                response = favorite_upadted
            else:
                response = favorite_upadted
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_change_product_favorite_status EXCEPTION ERROR"
        }
    

@router.post("/api/get_product_review_list")
async def http_get_product_review_list(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_get_product_review_list - data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]

        product_id = data_obj["product_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_get_product_review_list - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_get_product_review_list - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            reviews_list = await get_product_review_list(product_id=product_id)
            
            if reviews_list["status"]:
                response = reviews_list
            else:
                response = reviews_list
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_get_product_review_list EXCEPTION ERROR"
        }
    

@router.post("/api/send_reply_for_product_review")
async def http_send_reply_for_business_review(data: str = Form(...)):
    try:        
        data_obj = json.loads(data)
        logger.info(f"http_send_reply_for_product_review - incoming data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        ip_address = data_obj["ip_address"]
        user_id = data_obj["user_id"]
        comment_id = data_obj["comment_id"]
        reply_text = data_obj["reply_text"]
        product_id = data_obj["product_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_send_reply_for_product_review - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {"status": False, "message": "http_send_reply_for_product_review - JWT verify is False"}
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            reply_added = await add_reply_for_product_review(user_id, product_id, comment_id, reply_text)
            if reply_added["status"]:

                log_data = reply_added.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/send_reply_for_product_review"
                await add_user_action_log(log_data)

                response = reply_added
            else:
                response = reply_added            
            
            response["jwt_token"] = new_token
            return response

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "http_send_reply_for_product_review EXCEPTION ERROR"}
    

@router.post("/api/update_product")
async def http_update_product(
    data: str = Form(...),
    avatar: UploadFile | None = File(None)
):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_update_product - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]
        product_id = data_obj["product_id"]

        product_data = {
            "add_languages": data_obj.get("add_languages", None),
            "name": data_obj.get("name", None),
            "description": data_obj.get("description", None),
            "measure_code": data_obj.get("measure_code", None),
            "pack_params": data_obj.get("pack_params", None),
            "price": data_obj.get("price", None),
            "min_order": data_obj.get("min_order_quantity", None),
            "max_order": data_obj.get("max_order_quantity", None),
            "sku": data_obj.get("sku", None),
            "active": data_obj.get("active", True),
            "category_code": data_obj.get("category_code", None),
            "daily_limit": data_obj.get("daily_limit", None),
            "local_names": data_obj.get("local_names", None),
            "individual_customer": data_obj.get("individual_customer", False),
            "shipment_same_day": data_obj.get("shipment_same_day", False),
            "shipment_hours": data_obj.get("shipment_hours", None),
            "shipment_price": data_obj.get("shipment_price", None)
        }

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_update_product - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_update_product - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            product_updated = await update_product(user_id=user_id, product_id=product_id, product_data=product_data, avatar=avatar)
            
            if product_updated["status"]:

                log_data = product_updated.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/http_update_product"
                await add_user_action_log(log_data)
                                
                updated_product_request = await get_product(user_id=user_id, product_id=product_id)
                if updated_product_request["status"]:
                    updated_product = updated_product_request.get("product_dict", None)
                else:
                    updated_product = None

                if updated_product:
                    response = {
                        "status": True,
                        "updated_product": updated_product
                    }
                else:
                    response = {
                        "status": True,
                        "notify_type": "warning",
                        "notify_code": "notify_warning_product_updated_but_not_updated"
                    }                                
                
            else:
                print("################### TENP LOG ################################# http_update_product")
                print(f"{product_updated}")
                response = product_updated

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "update_product - EXCEPTION ERROR"
        }
    

@router.post("/api/delete_product")
async def http_delete_product(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_delete_product - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]
        product_id = data_obj["product_id"]    

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_delete_product - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_delete_product - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            product_deleted = await delete_product(user_id=user_id, product_id=product_id)
            
            if product_deleted["status"]:

                log_data = product_deleted.get("log_data", {})
                log_data["ip_address"] = ip_address
                if log_data.get("action_type", None) is None:
                    log_data["action_type"] = "ENDPOINT /api/http_deleet_product"
                await add_user_action_log(log_data)
                
                response = product_deleted
            else:
                response = product_deleted

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "delete_product - EXCEPTION ERROR"
        }
    

@router.post("/api/set_filters_supplier_catalog")
async def http_set_filters_supplier_catalog(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_set_filters_supplier_catalog - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        filter_settings = data_obj["filter_settings"]    

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_set_filters_supplier_catalog - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_set_filters_supplier_catalog - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            filter_settings_applied = await set_filters_supplier_catalog(user_id=user_id, filter_settings=filter_settings)
            
            if filter_settings_applied["status"]:                
                response = filter_settings_applied
                response["filters_supplier_catalog"] = filter_settings
            else:
                response = filter_settings_applied

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_set_filters_supplier_catalog - EXCEPTION ERROR"
        }
    

@router.post("/api/set_filters_customer_catalog")
async def http_set_filters_customer_catalog(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_set_filters_customer_catalog - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        filter_settings = data_obj["filter_settings"]        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_set_filters_customer_catalog - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_set_filters_customer_catalog - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            filter_settings_applied = await set_filters_customer_catalog(user_id=user_id, filter_settings=filter_settings)
            
            if filter_settings_applied["status"]:                
                response = filter_settings_applied
                response["filters_customer_catalog"] = filter_settings                
            else:
                response = filter_settings_applied

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_set_filters_customer_catalog - EXCEPTION ERROR"
        }
    

@router.post("/api/set_filters_individual_catalog")
async def http_set_filters_individual_catalog(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_set_filters_individual_catalog - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        filter_settings = data_obj["filter_settings"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_set_filters_individual_catalog - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_set_filters_individual_catalog - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            filter_settings_applied = await set_filters_individual_catalog(user_id=user_id, filter_settings=filter_settings)
            
            if filter_settings_applied["status"]:                
                response = filter_settings_applied
                response["filters_individual_catalog"] = filter_settings                
            else:
                response = filter_settings_applied

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_set_filters_individual_catalog - EXCEPTION ERROR"
        }
    

@router.post("/api/upload_customer_product_catalog_bundle")
async def http_upload_customer_product_catalog_bundle(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_upload_customer_product_catalog_bundle - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        bundle_id = data_obj["bundle_id"]        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_upload_customer_product_catalog_bundle - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_upload_customer_product_catalog_bundle - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_product_catalog = await get_customer_products_request_bundle(user_id=user_id, bundle=bundle_id)
            response = updated_product_catalog
            if updated_product_catalog["status"]:
                response["updated_customer_product_catalog"] = updated_product_catalog.get("products_dict")
                response["updated_customer_product_catalog_count"] = updated_product_catalog.get("total_count")
                response["one_supplier_info"] = updated_product_catalog.get("one_supplier_info")
                
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_upload_customer_product_catalog_bundle - EXCEPTION ERROR"
        }
    

@router.post("/api/upload_individual_product_catalog_bundle")
async def http_upload_individual_product_catalog_bundle(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_upload_individual_product_catalog_bundle - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        bundle_id = data_obj["bundle_id"]
        
        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_upload_individual_product_catalog_bundle - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_upload_individual_product_catalog_bundle - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_product_catalog = await get_individual_products_request_bundle(user_id=user_id, bundle=bundle_id)
            response = updated_product_catalog
            if updated_product_catalog["status"]:
                response["updated_individual_product_catalog"] = updated_product_catalog.get("products_dict")
                response["updated_individual_product_catalog_count"] = updated_product_catalog.get("total_count")
                response["one_supplier_info"] = updated_product_catalog.get("one_supplier_info")
                
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_upload_individual_product_catalog_bundle - EXCEPTION ERROR"
        }
    

@router.post("/api/make_order")
async def http_make_order(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_make_order - Incoming data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]
        business_id = data_obj["business_id"]

        cart = data_obj["cart"]
        order_date = data_obj["order_date"]
        order_comment = data_obj["order_comment"]
        request_free_delivery = data_obj["request_free_delivery"]

        order = {
            "business_id": business_id,
            "cart": cart,
            "order_date": order_date,
            "order_comment": order_comment,
            "request_free_delivery": request_free_delivery
        }

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_make_order - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_make_order - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            created_order = await make_order(user_id, order)
            
            if created_order["status"]:
                print(f"------------------- TEMPORARY LOG !!! -------------------------------------")
                print(f"Make order - Status True: {created_order}")
                redis_product_add_list = created_order.get("redis_product_add_list", [])
                for product in redis_product_add_list:
                    try:
                        await queue_add_product_ordered_quantity(
                            product_id=product.get("product_id"),
                            supplier_date=product.get("supplier_date"),
                            order_quantity=product.get("order_quantity"),
                            ttl_timestamp=product.get("ttl_timestamp"),
                        )
                    except Exception as redis_add_error:
                        logger.error(f"http_make_order - REDIS add data error: {redis_add_error}", user_id=user_id)
                
                supplier_team = created_order.get("supplier_team", [])
                customer_team = created_order.get("customer_team", [])
                userlist = supplier_team + customer_team
                order_id = created_order.get("order_id", None)
                message_id = created_order.get("order_comment_message_id", None)
                if userlist and order_id:
                    preparing = await preparing_push_new_order_to_business_orders(order_id=order_id, customer_user=user_id, supplier_team=supplier_team, customer_team=customer_team)
                    if preparing["status"]:
                        rabbit_messages = preparing.get("rabbit_messages", None)
                        if rabbit_messages:
                            for message in rabbit_messages:
                                await broadcast_message_async(message)
                    else:
                        logger.error(f"http_make_order - cannot prepare sending message(s) for RABBIT", user_id=user_id)

                    if message_id:
                        logger.info(f"http_make_order - message: {message_id}", user_id=user_id)
                        preparing_broadcast = await preparing_chat_message_broadcast(message_id=message_id, userlist=userlist, need_tab_notify=True)
                        if preparing_broadcast["status"]:
                            rabbit_messages = preparing_broadcast.get("rabbit_messages", None)
                            print(f"-------------- TEMPORARY LOG!!! rabbit messages: {rabbit_messages}")
                            if rabbit_messages:                                
                                for message in rabbit_messages:
                                    await broadcast_message_async(message)
                        else:
                            logger.error(f"http_make_order - cannot prepare sending message(s) for RABBIT", user_id=user_id)

                response = {"status": True}
            else:
                response = created_order

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_make_order EXCEPTION ERROR"
        }
    

@router.post("/api/order_action")
async def http_order_action(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_order_action - Incoming data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]
        business_id = data_obj["business_id"]

        order_id = data_obj["order_id"]
        action = data_obj["action"]
        
        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_make_orderhttp_order_action - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_order_action - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_order = await do_order_action(user_id, business_id, order_id, action)
            
            if updated_order["status"]:                                
                
                supplier_team = updated_order.get("supplier_team", [])
                customer_team = updated_order.get("customer_team", [])                
                
                if supplier_team or customer_team:
                    preparing = await preparing_push_updated_order_to_users(order_id=order_id, need_tab_update=True, supplier_team=supplier_team, customer_team=customer_team)                    
                    if preparing["status"]:
                        rabbit_messages = preparing.get("rabbit_messages", None)
                        if rabbit_messages:
                            for message in rabbit_messages:
                                await broadcast_message_async(message)
                    else:
                        logger.error(f"http_order_action - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
                updated_order_dict_request = await get_order(order_id)
                updated_order_dict = None
                if updated_order_dict_request["status"]:
                    updated_order_dict = updated_order_dict_request.get("order_dict", None)
                response = {"status": True, "updated_order": updated_order_dict}

            else:
                response = updated_order

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_order_action EXCEPTION ERROR"
        }
    

@router.post("/api/rate_order")
async def http_rate_order(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_rate_order - Incoming data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]
        business_id = data_obj["business_id"]

        rating_data = data_obj["rating_data"]
        order_id = rating_data.get("order_id")

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_rate_order - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_order_action - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            rated_order = await rate_order(user_id, business_id, rating_data)
            
            if rated_order["status"]:
                supplier_team = rated_order.get("supplier_team", [])
                customer_team = rated_order.get("customer_team", [])                
                
                if supplier_team or customer_team:
                    preparing = await preparing_push_updated_order_to_users(order_id=order_id, need_tab_update=True, supplier_team=supplier_team, customer_team=customer_team)
                    if preparing["status"]:
                        rabbit_messages = preparing.get("rabbit_messages", None)
                        if rabbit_messages:
                            for message in rabbit_messages:
                                await broadcast_message_async(message)
                    else:
                        logger.error(f"http_rate_order - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
                updated_order_dict_request = await get_order(order_id)
                updated_order_dict = None
                if updated_order_dict_request["status"]:
                    updated_order_dict = updated_order_dict_request.get("order_dict", None)
                response = {"status": True, "updated_order": updated_order_dict}
                
            else:
                response = rated_order

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_rate_order EXCEPTION ERROR"
        }
    

@router.post("/api/set_filters_business_messages")
async def http_set_filters_business_messages(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_set_filters_business_messages - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]
        business_id = data_obj["business_id"]

        filter_settings = data_obj["filter_settings"]    

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_set_filters_business_message - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_set_filters_business_message - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            filter_settings_applied = await set_filters_business_messages(user_id=user_id, business_id=business_id, filter_settings=filter_settings)
            
            if filter_settings_applied["status"]:                
                response = filter_settings_applied
                response["filters_business_messages"] = filter_settings
            else:
                response = filter_settings_applied

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_set_filters_business_message - EXCEPTION ERROR"
        }
    

@router.post("/api/set_filters_business_orders")
async def http_set_filters_business_orders(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_set_filters_business_orders - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]
        business_id = data_obj["business_id"]

        filter_settings = data_obj["filter_settings"]    

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_set_filters_business_orders - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_set_filters_business_orders - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            filter_settings_applied = await set_filters_business_orders(user_id=user_id, business_id=business_id, filter_settings=filter_settings)
            
            if filter_settings_applied["status"]:                
                response = filter_settings_applied
                response["filters_business_orders"] = filter_settings
            else:
                response = filter_settings_applied

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_set_filters_business_orders - EXCEPTION ERROR"
        }
    

@router.post("/api/get_orders_excel_file")
async def http_get_orders_excel_file(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_get_orders_excel_file - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]
        ip_address = data_obj["ip_address"]
        business_id = data_obj["business_id"]

        order_ids = data_obj["order_ids"]
        sid = data_obj["sid"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_get_orders_excel_file - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_get_orders_excel_file - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            user_tg_id = None
            permission = await check_permission_for_generate_excel_file(user_id=user_id, business_id=business_id, order_ids=order_ids)

            if not permission["status"]:
                response = {"status": False, "notify_code": "notify_error_cannot_get_permission_to_generate_order_list"}
                if new_token:
                    response["jwt_token"] = new_token
                return response
            else:                
                user_tg_id = permission.get("user_tg_id")

            try:
                inner_message = {
                    "type": "execute",
                    "description": "get_orders_excel_file",
                    "data": {
                        "user_id": user_id,
                        "business_id": business_id,
                        "order_ids": order_ids,
                        "user_tg_id": user_tg_id
                    }
                }
                message = {
                    "receiver": BOT_SERVICE_NAME,
                    "receiver_id": "any",
                    "message": inner_message
                }
                await direct_task_async(BOT_SERVICE_NAME, message)
                response = {"status": True, "notify_type": "success", "notify_code": "notify_success_order_list_request_received"}                

            except Exception as send_error:
                logger.exception(f"http_get_orders_excel_file - Rabbit direct send exception: {send_error}")
                response = {"status": True, "notify_type": "warning", "notify_code": "notify_error_order_list_request_failed"}
                
            if new_token:
                response["jwt_token"] = new_token
            return response
                
    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_get_orders_excel_file - EXCEPTION ERROR"
        }
    

@router.post("/api/upload_counter_agent_businesses_bundle")
async def http_upload_counter_agent_businesses_bundle(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_upload_counter_agent_businesses_bundle - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        bundle_id = data_obj["bundle_id"]        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_upload_counter_agent_businesses_bundle - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_upload_counter_agent_businesses_bundle - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            updated_counter_agents_list = await get_counter_agent_businesses_bundle(user_id=user_id, bundle=bundle_id)
            response = updated_counter_agents_list
            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_upload_counter_agent_businesses_bundle - EXCEPTION ERROR"
        }

    
@router.post("/api/set_filters_counter_agents_serach")
async def http_set_filters_counter_agents_serach(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_set_filters_counter_agents_serach - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        filter_settings = data_obj["filter_settings"]    

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_set_filters_counter_agents_serach - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_set_filters_counter_agents_serach - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")

            filter_settings_applied = await set_filters_counter_agents_serach(user_id=user_id, filter_settings=filter_settings)
            
            if filter_settings_applied["status"]:                
                response = filter_settings_applied
                response["filters_counteragent_search"] = filter_settings
            else:
                response = filter_settings_applied

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_set_filters_counter_agents_serach - EXCEPTION ERROR"
        }
    

@router.post("/api/add_user_phone_number")
async def http_add_user_phone_number(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_add_user_phone_number - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        payload = data_obj["payload"]
        json_contact = data_obj["json_contact"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_add_user_phone_number - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_add_user_phone_number - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            verified_payload = verify_phone_payload(payload=payload)
            if not verified_payload["status"]:
                verify_error = jwt_verify.get("verify_error")
                await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_access_error"}
            verified_contact = verified_payload.get("contact", None)
            if not verified_contact:
                return {"status": False, "notify_type": "error", "notify_code": "notify_error_unknown_error"}
            phone_added = await add_user_phone_number(user_id=user_id, verified_contact=verified_contact, json_contact=json_contact)
            
            if phone_added["status"]:
                response = phone_added                
            else:
                response = phone_added

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_add_user_phone_number - EXCEPTION ERROR"
        }
    

@router.post("/api/get_user_public_profile")
async def http_get_user_public_profile(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_get_user_public_profile - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        getting_user_id = data_obj["getting_user_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_get_user_public_profile - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_get_user_public_profile - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            user_profile = await get_user_public_profile(user_id=user_id, getting_user_id=getting_user_id)
            
            if user_profile["status"]:
                response = user_profile
            else:
                response = user_profile

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_get_user_public_profile - EXCEPTION ERROR"
        }
    

@router.post("/api/change_user_username")
async def http_change_user_username(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_change_user_username - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        username_data = data_obj["username_data"]
        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_change_user_username - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_change_user_username - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            new_username = await change_user_username(user_id=user_id, username_data=username_data)
            
            if new_username["status"]:
                response = new_username
            else:
                response = new_username

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_change_user_username - EXCEPTION ERROR"
        }
    

@router.post("/api/update_referral_list")
async def http_change_user_username(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_update_referral_list - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]        

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"update_referral_list - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "update_referral_list - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            ref_list = await update_referral_list(user_id=user_id)
            
            if ref_list["status"]:
                response = ref_list
            else:
                response = ref_list

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_update_referral_list - EXCEPTION ERROR"
        }


@router.post("/api/get_payment_redirect_link")
async def http_get_payment_redirect_link(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_get_payment_redirect_link - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        payment_data = data_obj["payment_data"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_get_payment_redirect_link - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_get_payment_redirect_link - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            redirect_data = await get_payment_redirect_link(user_id=user_id, payment_data=payment_data)
            
            if redirect_data["status"]:
                response = redirect_data
            else:
                response = redirect_data

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_get_payment_redirect_link - EXCEPTION ERROR"
        }
    


@router.post("/api/get_free_credits")
async def http_get_free_credits(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_get_free_credits - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        payment_data = data_obj["payment_data"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_get_free_credits - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_get_free_credits - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            redirect_data = await get_free_credits(user_id=user_id, payment_data=payment_data)
            
            if redirect_data["status"]:
                response = redirect_data
            else:
                response = redirect_data

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_get_free_credits - EXCEPTION ERROR"
        }
    

@router.post("/api/paypal_webhook")
async def http_paypal_webhook(request: Request):
    try:
        payload = await request.json()
        print(f"incoming webhook: {payload}")

        event_type = payload.get("event_type")

        if event_type not in PAYPAL_WEBHOOK_ALLOWED_EVENTS:
            logger.warning(f"paypal webhook: event_type {event_type} is not in aloowed webhook events")
            return Response(status_code=200)

        if event_type == PAYPAL_WEBHOOK_EVENT_ORDER_APPROVED:
            order_id = payload.get("resource", {}).get("id")

            if not order_id:
                logger.warning("paypal webhook: missing order_id")
                return Response(status_code=200)
            
            lock_key = f"{PAYPAL_ORDERS_CAPTURE_ON_AIR}:{order_id}"

            acquired = await redis_client.set(
                lock_key,
                "1",
                ex=60,
                nx=True,
            )

            if not acquired:
                logger.warning("paypal webhook: dublicate order capture operation")
                return Response(status_code=200)

            capture_order = await capture_paypal_order(order_id=order_id)
            print(f"http_paypal_webhook - capture order: {capture_order}")
            if capture_order["status"] and capture_order["paypal_status"] == "COMPLETED":
                check_order = await check_paypal_order_completed(order_id)
                print(f"WWWWWWWWWWWWWWWWWWWWWWWWWW   incoming webhook - check order: {check_order}")
                if check_order["status"]:
                    payment_id = check_order.get("payment_id")
                    process_order = await process_confirmed_payment(payment_id)
                    print(f"WWWWWWWWWWWWWWWWWWWWWWWWWW   incoming webhook - process order: {process_order}")
                    if process_order["status"]:                
                        user_id = process_order.get("user_id")                        
                        payback_info = process_order.get("payback_info", None)
                        preparing = await preparing_user_update_info_after_successfull_payment(user_id, payment_id)
                        if preparing["status"]:
                            print(f"http_paypal_webhook - PREPARING {preparing}")
                            rabbit_message = preparing.get("rabbit_message", None)                    
                            try:
                                await broadcast_message_async(rabbit_message)
                            except Exception as rabbit_error:
                                logger.exception(f"http_paypal_webhook - rabbit notify failed: {rabbit_error}")

                        if payback_info:
                            print(f"http_paypal_webhook - PAYBACK INFO {payback_info}")
                            referrer_user_id = payback_info.get("user_id")
                            referrer_preparing = await preparing_user_update_info_after_bonus_accural(referrer_user_id, payback_info)
                            if referrer_preparing["status"]:
                                print(f"http_paypal_webhook - REFERRER PREPARING {referrer_preparing}")
                                rabbit_message = referrer_preparing.get("rabbit_message", None)                    
                                try:
                                    await broadcast_message_async(rabbit_message)
                                except Exception as rabbit_error:
                                    logger.exception(f"http_paypal_webhook - rabbit notify failed: {rabbit_error}")

                        user_tg_id = process_order.get("user_tg_id")
                        bot_notify_on = process_order.get("bot_notify_on")
                        bot_message = process_order.get("bot_message")
                        if bot_notify_on:
                            bot_inner_message = {
                                "type": "execute",
                                "description": "send_telegram_user_bot_message",
                                "user_tg_id": user_tg_id,
                                "bot_message": bot_message                                
                            }

                            bot_rabbit_message = {
                                "receiver": BOT_SERVICE_NAME,
                                "receiver_id": "any",
                                "message": bot_inner_message
                            }
                            await direct_task_async(BOT_SERVICE_NAME, bot_rabbit_message)
                        


            """
            check_order = await check_paypal_order(order_id)
            print(f"WWWWWWWWWWWWWWWWWWWWWWWWWW   incoming webhook - check order: {check_order}")
            if check_order["status"]:
                payment_id = check_order.get("payment_id")
                process_order = await process_confirmed_payment(payment_id)
                print(f"WWWWWWWWWWWWWWWWWWWWWWWWWW   incoming webhook - process order: {process_order}")
                if process_order["status"]:                
                    user_id = process_order.get("user_id")
                    payback_info = process_order.get("payback_info", None)
                    preparing = await preparing_user_update_info_after_successfull_payment(user_id, payment_id)
                    if preparing["status"]:
                        print(f"http_paypal_webhook - PREPARING {preparing}")
                        rabbit_message = preparing.get("rabbit_message", None)                    
                        try:
                            await broadcast_message_async(rabbit_message)
                        except Exception as rabbit_error:
                            logger.exception(f"http_paypal_webhook - rabbit notify failed: {rabbit_error}")

                    if payback_info:
                        print(f"http_paypal_webhook - PAYBACK INFO {payback_info}")
                        referrer_user_id = payback_info.get("user_id")
                        referrer_preparing = await preparing_user_update_info_after_bonus_accural(referrer_user_id, payback_info)
                        if referrer_preparing["status"]:
                            print(f"http_paypal_webhook - REFERRER PREPARING {referrer_preparing}")
                            rabbit_message = referrer_preparing.get("rabbit_message", None)                    
                            try:
                                await broadcast_message_async(rabbit_message)
                            except Exception as rabbit_error:
                                logger.exception(f"http_paypal_webhook - rabbit notify failed: {rabbit_error}")
            """

        return Response(status_code=200)

    except Exception as e:
        logger.exception(f"http_paypal_webhook - EXCEPTION - paypal webhook error: {e}")
        return Response(status_code=500)
    

@router.post("/api/start_ad_campaign")
async def http_start_ad_campaign(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_start_ad_campaign - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        campaign_data = data_obj["campaign_data"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_start_ad_campaign - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_start_ad_campaign - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            start_campaign = await start_ad_campaign(user_id=user_id, campaign_data=campaign_data)
            
            if start_campaign["status"]:
                response = start_campaign
            else:
                response = start_campaign

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_start_ad_campaign - EXCEPTION ERROR"
        }
    

@router.post("/api/delete_ad_campaign")
async def http_delete_ad_campaign(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_delete_ad_campaign - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        campaign_id = data_obj["campaign_id"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_delete_ad_campaign - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_delete_ad_campaign - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            delete_campaign = await delete_ad_campaign(user_id=user_id, campaign_id=campaign_id)
            
            if delete_campaign["status"]:
                response = delete_campaign
            else:
                response = delete_campaign

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_delete_ad_campaign - EXCEPTION ERROR"
        }
    

@router.post("/api/prolong_ad_campaign")
async def http_prolong_ad_campaign(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_prolong_ad_campaign - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        campaign_data = data_obj["campaign_data"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_prolong_ad_campaign - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_prolong_ad_campaign - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            prolong_campaign = await prolong_ad_campaign(user_id=user_id, campaign_data=campaign_data)
            
            if prolong_campaign["status"]:
                response = prolong_campaign
            else:
                response = prolong_campaign

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_prolong_ad_campaign - EXCEPTION ERROR"
        }



@router.post("/api/change_tariff_plan")
async def http_change_tariff_plan(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_change_tariff_plan - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        business_id = data_obj["business_id"]
        tariff_data = data_obj["tariff_data"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_change_tariff_plan - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_change_tariff_plan - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            change_tariff = await change_tariff_plan(user_id=user_id, business_id=business_id, tariff_data=tariff_data)
            
            if change_tariff["status"]:
                log_data = change_tariff.get("log_data", {})
                log_data["ip_address"] = ip_address
                await add_user_action_log(log_data)                
                response = {
                    "status": True,
                    "update_info": change_tariff.get("update_info")
                }
            else:
                response = change_tariff

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_change_tariff_plan - EXCEPTION ERROR"
        }
    

@router.post("/api/renew_tariff_plan")
async def http_renew_tariff_plan(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_renew_tariff_plan - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        business_id = data_obj["business_id"]
        tariff_data = data_obj["tariff_data"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_renew_tariff_plan - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_renew_tariff_plan - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            renew_tariff = await renew_tariff_plan(user_id=user_id, business_id=business_id, tariff_data=tariff_data)
            
            if renew_tariff["status"]:                
                log_data = renew_tariff.get("log_data", {})
                log_data["ip_address"] = ip_address
                await add_user_action_log(log_data)
                response = {
                    "status": True,
                    "update_info": renew_tariff.get("update_info")
                }
            else:
                response = renew_tariff

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_renew_tariff_plan - EXCEPTION ERROR"
        }
    
@router.post("/api/get_payment_stars_invoice_link")
async def http_get_payment_stars_invoice_link(data: str = Form(...)):
    try:
        # JSON из строки
        data_obj = json.loads(data)
        logger.info(f"http_get_payment_stars_invoice_link - Received data: {data_obj}")        
        
        jwt_token = data_obj["jwt_token"]
        user_id = data_obj["user_id"]        
        ip_address = data_obj["ip_address"]

        amount_stars = data_obj["amount_stars"]

        jwt_verify = await verify_and_refresh_jwt_token_http(jwt_token, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"http_get_payment_stars_invoice_link - JWT verify is False: {jwt_verify} ", user_id=user_id)
            return {
                "status": False,
                "message": "http_get_payment_stars_invoice_link - JWT verify is False"
            }
        else:            
            new_token = jwt_verify.get("new_token", "")
            
            invoice_data = await get_payment_stars_invoice_link(user_id=user_id, amount_stars=amount_stars)
            
            if invoice_data["status"]:
                response = invoice_data
            else:
                response = invoice_data

            response["jwt_token"] = new_token
            return response            

    except Exception as e:
        logger.exception(e)
        return {
            "status": False,
            "message": "http_get_payment_stars_invoice_link - EXCEPTION ERROR"
        }