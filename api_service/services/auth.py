from models.app_users import AppUser
from models.busineses import Business

from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from config import settings
DEFAULT_LANGUAGE = settings.DEFAULT_LANGUAGE
INSTANCE_ID = settings.INSTANCE_ID
THIS_SERVICE_NAME = settings.API_SERVICE_NAME
JWT_SECRET = settings.API_SERVICE_JWT_SECRET
JWT_ALGORITHM = settings.API_SERVICE_JWT_ALGORITHM
JWT_EXP_DELTA_SECONDS = settings.API_SERVICE_JWT_EXP_DELTA_SECONDS
JWT_REFRESH_PERIOD_SECONDS = settings.API_SERVICE_JWT_REFRESH_PERIOD_SECONDS

BLOCK_BY_IP_ADDRESS = settings.BLOCK_BY_IP_ADDRESS

from constants.log_entitys import USER_LOGIN, USER_REGISTER, TELEGRAM_ID, USER_LOGOUT

from datetime import datetime, timezone, timedelta

from .verify import verify_user, get_telegram_user_info, get_concat_name, get_params
from .userdata import get_referrer_id, join_staff_request_create
from .interfaces import get_interface, get_interface_list
from .guard import is_user_in_blacklist_by_ip_address, is_user_in_blacklist_by_tg_id
from .jwt_token import get_jwt_token
from .user_action_log import add_user_action_log
from .error import put_critical_error_into_db

from rabbit.rabbit_sender import broadcast_message_async

import base64

from session_config import async_session

from .tariff import get_tariff_list
from .items import get_category_list, get_measures_list

from payments.payments import get_payment_methods_for_frontend

from logger_config import get_logger
logger = get_logger(__name__)


async def tma_boot_application(raw_data : dict) -> dict:
    try:
        verification = verify_user(raw_data)
        
        if verification['status'] and verification['user_data']:
            auth_data = verification['user_data']
            user_language_browser = auth_data.get("language_code", DEFAULT_LANGUAGE)
            
            async with async_session() as session:
                try:
                    query = select(AppUser).filter(AppUser.tg_id == auth_data["id"])
                    result = await session.execute(query)
                    user = result.scalars().first()
                    if user is None:
                        is_tg_user_exist = False
                        user_language = user_language_browser
                    else:
                        is_tg_user_exist = True
                        user_language = getattr(user, "language", user_language_browser)
                    
                    user_interface = await get_interface(user_language)
                    interface_list = await get_interface_list()
                    tariff_list = await get_tariff_list()
                    category_list = await get_category_list()
                    measures_list = await get_measures_list()
                    payment_methods = await get_payment_methods_for_frontend()

                    return {
                        "status": True, 
                        "tg_user_is_exist": is_tg_user_exist, 
                        "user_interface": user_interface, 
                        "interface_list": interface_list,
                        "tariff_list": tariff_list,
                        "category_list": category_list,
                        "measures_list": measures_list,
                        "payment_methods": payment_methods
                    }
                                
                except Exception as session_error:
                    await session.rollback()
                    logger.error(f"tma_boot_application - Exception: \n{session_error}")
                    return {"status": False, "message": f"tma_boot_application - Session exception - {session_error}"}

        else:
            logger.error(f"tma_boot_application: Verification error!")
            return { "status": False, "message": "tma_boot_application: Verification error!"}
        
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"status": False, "message": f"tma_boot_application EXCEPTION ERROR: {e}"}


async def user_register_tma(ip_address : str, tg_hash_data_64 : str) -> dict:
    try:
        is_user_blocked = await is_user_in_blacklist_by_ip_address(ip_address)
        if is_user_blocked["status"] and BLOCK_BY_IP_ADDRESS:
            return {"status": False, "blacklist": True, "notify_type": "error", "notify_code": "notify_error_ip_address_blacklisted", "message": f"user_register_tma - error: IP address {ip_address} is in the blacklist"}
        
        decoded_tg_data = base64.b64decode(tg_hash_data_64).decode()
        verification = verify_user(decoded_tg_data)
        if verification["status"]:            
            user_data = verification["user_data"]
            new_user_created = await create_new_user(user_data)
            if new_user_created["status"]:

                # User action logging
                log_data = {
                    "user_id": new_user_created.get("id", 0),
                    "action_type": USER_REGISTER,
                    "entity_type": TELEGRAM_ID,
                    "entity_id": new_user_created.get("tg_id", 0),
                    "ip_address": ip_address
                }
                await add_user_action_log(log_data)

                return {"status": True, "message": f"user_register_tma - TRUE", "created_user": new_user_created["created_user"]}
            else:
                return {"status": False, "message": f"user_register_tma - error: Account was not created"}
        else:
            return {"status": False, "message": f"user_register_tma - error: Verification error"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"status": False, "message": f"user_register_tma EXCEPTION ERROR: {e}"}


async def user_login_tma(sid : str, ip_address : str, tg_hash_data_64 : str) -> dict:
    try:
        is_user_blocked = await is_user_in_blacklist_by_ip_address(ip_address)
        if is_user_blocked["status"] and BLOCK_BY_IP_ADDRESS:
            return {"status": False, "blacklist": True, "notify_type": "error", "notify_code": "notify_error_ip_address_blacklisted", "message": f"user_login_tma - error: IP address {ip_address} is in the blacklist"}            
        
        decoded_tg_data = base64.b64decode(tg_hash_data_64).decode()
        verification = verify_user(decoded_tg_data)
        if verification["status"]:            
            user_data = verification["user_data"]
            user_tg_id = user_data["id"]
            logger.info(f"user_login_tma - verificated data: {user_data}")

            is_user_blocked = await is_user_in_blacklist_by_tg_id(user_tg_id)
            if is_user_blocked["status"]:
                return {"status": False, "blacklist": True, "notify_type": "error", "notify_code": "notify_error_tg_account_blacklisted", "message": f"user_login_tma - error: TG ID {user_tg_id} is in the blacklist"}

            start_param = user_data.get("start_param", {})
            action = start_param.get("action", None)
            
            request_for_join_staff_business_id = 0
            request_for_join_staff_owner_id = 0
            if action and action == "invite_to_staff":
                request_for_join_staff_business_id = start_param.get("business_id", 0)
                request_for_join_staff_owner_id = start_param.get("employer_id", 0)
            

            current_time_unix = int(datetime.now(timezone.utc).timestamp())
            async with async_session() as session:
                try:
                    user_query = select(AppUser).filter(AppUser.tg_id == user_tg_id).with_for_update()
                    user_result = await session.execute(user_query)
                    user = user_result.scalars().first()
                    if not user:
                        return {"status": False, "message": f"user_login_tma - error: User {user_tg_id} not found"}    
                    if user.sid and user.sid != "":
                        if user.instance_id and user.instance_id != "":
                            instance_address = user.instance_id
                        else:
                            instance_address = "all"
                        inner_logout_message = {
                            "type": "execute",
                            "description": "logout_user_frontend_by_sid",
                            "sid": user.sid
                        }
                        full_logout_message = {
                            "receiver": THIS_SERVICE_NAME,
                            "receiver_id": instance_address,
                            "message": inner_logout_message
                        }
                        await broadcast_message_async(full_logout_message)

                    user.last_activity = current_time_unix
                    user.instance_id = INSTANCE_ID
                    user.sid = sid

                    await session.commit()

                    userdata = user.to_dict()                    
                    print(f"----------------------------------------------------------- USER LOGIN TMA ------------------------")
                    print(f"user_id: {user.id}, request_for_join_staff_business_id: {request_for_join_staff_business_id}, request_for_join_staff_business_id: {request_for_join_staff_business_id}")

                    if request_for_join_staff_business_id != 0 and user.outcoming_employer_business_id == 0:
                        try:                            
                            make_request = await join_staff_request_create(user_id=user.id, business_id=request_for_join_staff_business_id, employer_id=request_for_join_staff_owner_id)
                            if make_request["status"]:
                                userdata = make_request["userdata"]
                                
                                inner_logout_message = {
                                    "type": "execute",
                                    "description": "user_notify_incoming_staff_request",
                                    "employer_id": request_for_join_staff_owner_id,
                                    "business_id": request_for_join_staff_business_id,
                                    "employee_id": user.id
                                }
                                full_logout_message = {
                                    "receiver": THIS_SERVICE_NAME,
                                    "receiver_id": "all",
                                    "message": inner_logout_message
                                }
                                await broadcast_message_async(full_logout_message)
                                
                            print(f"-----------------------------------------------------------")
                            print(f"make_request: {make_request}")
                        except Exception as error_request:
                            logger.error(f"user_login_tma - request_for_join_staff exception: {error_request}")

                    jwt_token = await get_jwt_token(user.id)

                    # User action logging
                    log_data = {
                        "user_id": userdata.get("id", 0),
                        "action_type": USER_LOGIN,
                        "entity_type": TELEGRAM_ID,
                        "entity_id": userdata.get("tg_id", 0),
                        "ip_address": ip_address
                    }                    

                    return {"status": True, "message": f"user_login_tma - User was logged in successfully", "userdata": userdata, "jwt_token": jwt_token, "log_data": log_data}
                
                except Exception as session_error:
                    logger.error(f"user_login_tma - Session error: {session_error}")
                    return {"status": False, "message": f"user_login_tma - session error: {session_error}"}
        else:
            return {"status": False, "message": f"user_login_tma - error: Verification error"}
        
    except Exception as e:
        logger.error(f"user_login_tma - Exception: {e}")
        return {"status": False, "message": f"user_login_tma EXCEPTION ERROR: {e}"}


async def create_new_user(user_data : dict) -> dict:
    try:
        print(f"========================================================================================================")
        print(f"CREATE NEW USER 1 ======================================================================================")
        print(f"{user_data}")
        current_time_unix = int(datetime.now(timezone.utc).timestamp())
        if not isinstance(user_data, dict):
            return {"status": False, "message": f"create_new_user ERROR: user_data is not coorect dictionary"}
        async with async_session() as session:
            try:
                async with session.begin():
                    referrer_id = get_referrer_id(user_data)
                    print(f"CREATE NEW USER 2 ======================================================================================")
                    print(f"Referer ID {referrer_id}")
                    referrer_username = ""
                    if referrer_id != 0:
                        try:
                            referrer_query = select(AppUser).filter(AppUser.id == referrer_id).with_for_update()
                            referrers = await session.execute(referrer_query)
                            referrer = referrers.scalars().first()
                            referrer_username = referrer.username
                            print(f"CREATE NEW USER 2 ======================================================================================")
                            print(f"Referer username {referrer_username}")
                        except Exception as referrer_error:
                            referrer_id = 0
                            print(f"CREATE NEW USER 2 ======================================================================================")
                            print(f"Referer username - Exception: {referrer_error}")
                    new_user = AppUser(
                        tg_id = user_data["id"],
                        tg_firstname = user_data["first_name"],
                        tg_lastname = user_data["last_name"],
                        tg_username = user_data.get("username") or None,
                        username = get_concat_name(user_data),
                        reg_date = current_time_unix,
                        referrer_id = referrer_id,
                        referrer_username = referrer_username,
                        language = user_data.get("language_code", DEFAULT_LANGUAGE),
                        phone = None,
                        email = None
                    )
                    session.add(new_user)
                    await session.flush()

                    if referrer_id != 0:
                        try:
                            referrer.referrals.append(new_user.id)
                            flag_modified(referrer, "referrals")
                            referrer.contacts_allowed.append(new_user.id)
                            flag_modified(referrer, "contacts_allowed")
                            new_user.contacts_allowed.append(referrer.id)
                            flag_modified(new_user, "contacts_allowed")
                        except Exception as contacts_update_error:
                            logger.error(f"create_new_user: Exception - \n{contacts_update_error}")
                    
                    created_user = new_user.to_dict()
                    return {"status": True, "created_user": created_user}
                
            except Exception as session_error:                
                logger.error(f"create_new_user: Exception - \n{session_error}")
                return {"status": False, "message": f"create_new_user: Exception - {session_error}"}
            
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"status": False, "message": f"create_new_user EXCEPTION ERROR: {e}"}
    

async def backend_logout_user_by_sid(sid: str):
    logger.info(f"backend_logout_user_by_sid: {sid}")
    async with async_session() as session:
        try:
            query = select(AppUser).filter(AppUser.sid == sid)
            result = await session.execute(query)
            user = result.scalars().first()
            if user is None:
                return {"status": False, "message": "Player not found"}
            user.sid = ""
            user.instance_id = ""
            user.last_activity = int(datetime.now(timezone.utc).timestamp())
            await session.commit()

            # User action logging
            log_data = {
                "user_id": getattr(user, "id", 0),
                "action_type": USER_LOGOUT,
                "entity_type": TELEGRAM_ID,
                "entity_id": getattr(user, "tg_id", 0),                
            }                    
            await add_user_action_log(log_data)

            return {"status": True, "message": f"User {user.id}({user.username}) was logged out in successfully"}
        except Exception as e:
            await session.rollback()
            logger.error(f"Exception - \n{e}")
            return {"status": False, "message": f"backend_logout_user_by_sid: Exception - {e}"}


                
