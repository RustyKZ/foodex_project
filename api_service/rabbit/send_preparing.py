
from config import settings

from session_config import async_session

from models.app_users import AppUser
from models.busineses import Business
from models.messages import Message, Notification
from models.products import Product
from models.orders import Order, OrderItem

from sqlalchemy.future import select
from sqlalchemy import exists
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm.attributes import flag_modified

from sqlalchemy.orm import aliased

THIS_SERVICE_NAME = settings.API_SERVICE_NAME

from constants.frontend import TAB_MESSAGE_CENTER, TAB_SUPPLIER_PRODUCT_CATALOG, TAB_CURRENT_ORDERS, TAB_USER_PROFILE
from constants.default import DEFAULT_LANGUAGE

from system_i18n.samples_notification import SAMPLES_NOTIFICATION
from system_i18n.entities import ENTITY_BUSINESS, ENTITY_EMPLOYEE, ENTITY_USERNAME

from logger_config import get_logger
logger = get_logger(__name__)

from services.error import put_critical_error_into_db


async def preparing_push_new_product_to_catalog_supplier(business_id : int, product_id : int) -> dict:
    logger.info(f"preparing_push_new_product_to_catalog_supplier - Business ID: {business_id}; Product ID: {product_id}")
    async with async_session() as session:        
        try:
            business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
            business_result = await session.execute(business_query)
            business = business_result.scalars().first()
            if not business:
                logger.error(f"preparing_push_new_product_to_catalog_supplier - Business {business_id} not found")
                return {"status": False}

            push_product_list_ids = business.staff
            if not push_product_list_ids:
                return {"status": False}
                
            users_query = select(AppUser).where(
                AppUser.id.in_(push_product_list_ids),
                AppUser.active.is_(True),
                AppUser.sid != "",
                AppUser.instance_id != ""
            )
            users_result = await session.execute(users_query)
            users = users_result.scalars().all()            
            
            rabbit_messages_add_product = []
            rabbit_messages_update_tab_notify = []
            
            for user in users:                
                inner_message_add_product = {
                    "type": "execute",
                    "description": "push_new_product_to_catalog_supplier",
                    "user_instance_id": user.instance_id,
                    "user_id": user.id,
                    "product_id": product_id
                }
                full_message_add_product = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message_add_product
                }
                rabbit_messages_add_product.append(full_message_add_product)                                

                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                business_id_key = f"{business_id}"
                if not isinstance(user.tab_notify.get(business_id_key), dict):
                    user.tab_notify[business_id_key] = {}
                user.tab_notify[business_id_key][TAB_SUPPLIER_PRODUCT_CATALOG] = True
                flag_modified(user, "tab_notify")                

                if user.active_business_id == business_id:                    
                    try:                        
                        inner_message_update_tab_notify = {
                            "type": "execute",
                            "description": "update_tab_notify",                            
                            "user_id": user.id                            
                        }
                        full_message_update_tab_notify = {
                            "receiver": THIS_SERVICE_NAME,
                            "receiver_id": user.instance_id,
                            "message": inner_message_update_tab_notify
                        }
                        rabbit_messages_update_tab_notify.append(full_message_update_tab_notify)

                    except Exception as err:
                        logger.exception(f"preparing_push_new_product_to_catalog_supplier - SUB EXCEPTION ERROR: {err}")
                        await put_critical_error_into_db(
                            "preparing_push_new_product_to_catalog_supplier", "sub exception error",
                            f"Error text: {str(err)}", {"business_id": business_id, "product_id": product_id}
                        )                
            
            await session.commit()
            
            return { "status": True, "rabbit_messages_add_product": rabbit_messages_add_product, "rabbit_messages_update_tab_notify": rabbit_messages_update_tab_notify }

        except Exception as e:
            logger.exception("preparing_push_new_product_to_catalog_supplier - MAIN EXCEPTION ERROR") 
            await put_critical_error_into_db(
                "preparing_push_new_product_to_catalog_supplier", "main exception error",
                f"Error text: {str(e)}", {"business_id": business_id, "product_id": product_id}
            )
            return {"status": False}
        

async def preparing_user_notify_employee_fired_for_employee(business_id : int, employee_id : int) -> dict:
    logger.info(f"preparing_user_notify_employee_fired_for_employee - Business ID: {business_id}; Employee ID: {employee_id}")
    async with async_session() as session:
        async with session.begin():
            try:
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_user_notify_employee_fired_for_employee - Business {business_id} not found")
                    return {"status": False}

                user_query = select(AppUser).filter(AppUser.id == employee_id, AppUser.active).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    logger.error(f"preparing_user_notify_employee_fired_for_employee - User {employee_id} not found")
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                lang = user.language
                sample_code = 'emloyee_fired_for_employee'
                sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                sample_entity = ENTITY_BUSINESS.get(lang, ENTITY_BUSINESS.get(DEFAULT_LANGUAGE, ""))
                sample_text = f"{sample_pre_text} {sample_entity}: {business.name}"

                notification = Notification(
                    date = current_time_unix,
                    receiver_user = employee_id,
                    type = 'notify',
                    is_sample = True,
                    sample_code = sample_code,
                    sample_text = sample_text,
                    sample_data = {
                        "business_id": business_id,
                        "business_name": business.name
                    }
                )
                session.add(notification)
                await session.flush()
                
                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                
                if not isinstance(user.tab_notify.get("0"), dict):
                    user.tab_notify["0"] = {}
                user.tab_notify["0"][TAB_MESSAGE_CENTER] = True
                flag_modified(user, "tab_notify")

                if not user.sid:
                    logger.error(f"preparing_user_notify_employee_fired_for_employee - User {user.id} is not online. Information updated, but push notification is impossible")
                    return {"status": True, "rabbit_message": None}
                
                inner_message = {
                    "type": "execute",
                    "description": "user_notify_employee_fired_for_employee",
                    "employee_id": employee_id,
                    "notification_id": notification.id

                }
                full_message = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message
                }                
                    
                return {"status": True, "rabbit_message": full_message}

            except Exception as e:
                logger.exception("preparing_user_notify_employee_fired_for_employee - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_notify_employee_fired_for_employee", "main exception error",
                    f"Error text: {str(e)}", {"employee_id": employee_id, "business_id": business_id}
                )
                return {"status": False}
            

async def preparing_user_notify_employee_staff_request_confirmed(employee_id : int, business_id : int):
    logger.info(f"preparing_user_notify_employee_staff_request_confirmed - Employee ID: {employee_id}; Business ID: {business_id};")
    async with async_session() as session:
        async with session.begin():
            try:
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_user_notify_employee_staff_request_confirmed - Business {business_id} not found")
                    return {"status": False}
                

                user_query = select(AppUser).filter(AppUser.id == employee_id, AppUser.active).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    logger.error(f"preparing_user_notify_employee_staff_request_confirmed - User {employee_id} not found")
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                lang = user.language
                sample_code = 'outcoming_staff_request_confirmed'
                sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                sample_entity = ENTITY_BUSINESS.get(lang, ENTITY_BUSINESS.get(DEFAULT_LANGUAGE, ""))
                sample_text = f"{sample_pre_text} {sample_entity}: {business.name}"

                notification = Notification(
                    date = current_time_unix,
                    receiver_user = employee_id,
                    type = 'notify',
                    is_sample = True,
                    sample_code = sample_code,
                    sample_text = sample_text,
                    sample_data = {
                        "business_id": business_id,
                        "business_name": business.name
                    }
                )
                session.add(notification)
                await session.flush()

                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                if not isinstance(user.tab_notify.get("0"), dict):
                    user.tab_notify["0"] = {}
                user.tab_notify["0"][TAB_MESSAGE_CENTER] = True
                flag_modified(user, "tab_notify")

                if not user.sid:
                    logger.error(f"preparing_user_notify_employee_staff_request_confirmed - User {user.id} is not online. Information updated, but push notification is impossible")
                    return {"status": True, "rabbit_message": None}
                
                inner_message = {
                    "type": "execute",
                    "description": "user_notify_employee_staff_request_confirmed",
                    "employee_id": employee_id,
                    "notification_id": notification.id

                }
                full_message = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message
                }                
                    
                return {"status": True, "rabbit_message": full_message}


            except Exception as e:
                logger.exception("preparing_user_notify_employee_staff_request_confirmed - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_notify_employee_staff_request_confirmed", "main exception error",
                    f"Error text: {str(e)}", {"employee_id": employee_id, "business_id": business_id}
                )
                return {"status": False}
            

async def preparing_user_notify_employee_staff_request_rejected(employee_id : int, business_id : int):
    logger.info(f"preparing_user_notify_employee_staff_request_rejected - Employee ID: {employee_id}; Business ID: {business_id};")
    async with async_session() as session:
        async with session.begin():
            try:
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_user_notify_employee_staff_request_rejected - Business {business_id} not found")
                    return {"status": False}  

                user_query = select(AppUser).filter(AppUser.id == employee_id, AppUser.active).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    logger.error(f"preparing_user_notify_employee_staff_request_rejected - User {employee_id} not found")
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                lang = user.language
                sample_code = 'outcoming_staff_request_rejected'
                sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                sample_entity = ENTITY_BUSINESS.get(lang, ENTITY_BUSINESS.get(DEFAULT_LANGUAGE, ""))
                sample_text = f"{sample_pre_text} {sample_entity}: {business.name}"

                notification = Notification(
                    date = current_time_unix,
                    receiver_user = employee_id,
                    type = 'notify',
                    is_sample = True,
                    sample_code = sample_code,
                    sample_text = sample_text,
                    sample_data = {
                        "business_id": business_id,
                        "business_name": business.name
                    }
                )
                session.add(notification)
                await session.flush()

                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                if not isinstance(user.tab_notify.get("0"), dict):
                    user.tab_notify["0"] = {}
                user.tab_notify["0"][TAB_MESSAGE_CENTER] = True
                flag_modified(user, "tab_notify")

                if not user.sid:
                    logger.error(f"preparing_user_notify_employee_staff_request_rejected - User {user.id} is not online. Information updated, but push notification is impossible")
                    return {"status": True, "rabbit_message": None}
                
                inner_message = {
                    "type": "execute",
                    "description": "user_notify_employee_staff_request_rejected",
                    "employee_id": employee_id,
                    "notification_id": notification.id

                }
                full_message = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message
                }                
                    
                return {"status": True, "rabbit_message": full_message}        

            except Exception as e:
                logger.exception("preparing_user_notify_employee_staff_request_rejected - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_notify_employee_staff_request_rejected", "main exception error",
                    f"Error text: {str(e)}", {"employee_id": employee_id, "business_id": business_id}
                )
                return {"status": False}
            

async def preparing_user_notify_incoming_staff_request(business_id : int, employee_id : int):
    logger.info(f"preparing_user_notify_incoming_staff_request - Business ID: {business_id}; Employee ID: {employee_id}")
    async with async_session() as session:
        async with session.begin():
            try:
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_user_notify_incoming_staff_request - Business {business_id} not found")
                    return {"status": False}
                
                employer_id = business.owner_id

                user_query = select(AppUser).filter(AppUser.id == employer_id, AppUser.active).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    logger.error(f"preparing_user_notify_incoming_staff_request - User (employer) {employer_id} not found")
                    return {"status": False}

                employee_query = select(AppUser).filter(AppUser.id == employee_id, AppUser.active)
                employee_result = await session.execute(employee_query)
                employee = employee_result.scalars().first()
                if not employee:
                    logger.error(f"preparing_user_notify_incoming_staff_request - User (employee) {employee_id} not found")
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                lang = user.language
                sample_code = 'incoming_staff_request'
                sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                sample_entity = ENTITY_USERNAME.get(lang, ENTITY_USERNAME.get(DEFAULT_LANGUAGE, ""))
                sample_text = f"{sample_pre_text} {sample_entity}: {employee.username}"

                notification = Notification(
                    date = current_time_unix,
                    receiver_user = employer_id,                    
                    type = 'notify',
                    is_sample = True,
                    sample_code = sample_code,
                    sample_text = sample_text,
                    sample_data = {
                        "employee_id": employee_id,
                        "employee_username": employee.username,
                        "business_id": business_id,
                        "business_name": business.name
                    }
                )
                session.add(notification)
                await session.flush()

                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                business_id_key = f"{business_id}"
                if not isinstance(user.tab_notify.get(business_id_key), dict):
                    user.tab_notify[business_id_key] = {}
                user.tab_notify[business_id_key][TAB_MESSAGE_CENTER] = True
                flag_modified(user, "tab_notify")

                business_update = {
                    "id": business_id,
                    "staff_incoming": business.staff_incoming
                }

                if not user.sid:
                    logger.error(f"preparing_user_notify_incoming_staff_request - User {user.id} is not online. Information updated, but push notification is impossible")
                    return {"status": True, "rabbit_message": None}
                
                inner_message = {
                    "type": "execute",
                    "description": "user_notify_incoming_staff_request",
                    "employer_id": employer_id,
                    "notification_id": notification.id,
                    "business_update": business_update
                }

                full_message = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message
                }                
                    
                return {"status": True, "rabbit_message": full_message}                

            except Exception as e:
                logger.exception("preparing_user_notify_incoming_staff_request - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_notify_incoming_staff_request", "main exception error",
                    f"Error text: {str(e)}", {"business_id": business_id, "employee_id": employee_id}
                )
                return {"status": False}
            

async def preparing_user_notify_employee_staff_request_cancelled(employee_id : int, business_id : int):
    logger.info(f"preparing_user_notify_employee_staff_request_cancelled - Employee ID: {employee_id}; Business ID: {business_id}")
    async with async_session() as session:
        async with session.begin():
            try:
                employee_query = select(AppUser).filter(AppUser.id == employee_id, AppUser.active)
                employee_result = await session.execute(employee_query)
                employee = employee_result.scalars().first()
                if not employee:
                    logger.error(f"preparing_user_notify_employee_staff_request_cancelled - User (employee) {employee_id} not found")
                    return {"status": False}

                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_user_notify_employee_staff_request_cancelled - Business {business_id} not found")
                    return {"status": False}

                user_id = business.owner_id
                user_query = select(AppUser).filter(AppUser.id == user_id, AppUser.active)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    logger.error(f"preparing_user_notify_employee_staff_request_cancelled - User (employer) {user_id} not found")
                    return {"status": False}
                                
                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                lang = user.language
                sample_code = 'outcoming_staff_request_cancelled'
                sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                sample_entity = ENTITY_USERNAME.get(lang, ENTITY_USERNAME.get(DEFAULT_LANGUAGE, ""))
                sample_text = f"{sample_pre_text} {sample_entity}: {employee.username}"


                notification = Notification(
                    date = current_time_unix,
                    receiver_user = user_id,
                    type = 'notify',
                    is_sample = True,
                    sample_code = sample_code,
                    sample_text = sample_text,
                    sample_data = {
                        "employee_id": employee_id,
                        "employee_username": employee.username,
                        "business_id": business_id,
                        "business_name": business.name
                    }
                )
                session.add(notification)
                await session.flush()

                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                business_id_key = f"{business_id}"
                if not isinstance(user.tab_notify.get(business_id_key), dict):
                    user.tab_notify[business_id_key] = {}
                user.tab_notify[business_id_key][TAB_MESSAGE_CENTER] = True
                flag_modified(user, "tab_notify")

                business_update = {
                    "id": business_id,
                    "staff_incoming": business.staff_incoming
                }
                
                if not user.sid:
                    logger.error(f"preparing_user_notify_employee_staff_request_cancelled - User {user.id} is not online. Information updated, but push notification is impossible")
                    return {"status": True, "rabbit_message": None}
                
                inner_message = {
                    "type": "execute",
                    "description": "user_notify_employee_staff_request_cancelled",
                    "employer_id": user.id,
                    "notification_id": notification.id,
                    "business_update": business_update
                }

                full_message = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message
                }
                    
                return {"status": True, "rabbit_message": full_message}

            except Exception as e:
                logger.exception("preparing_user_notify_employee_staff_request_cancelled - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_notify_employee_staff_request_cancelled", "main exception error",
                    f"Error text: {str(e)}", {"employee_id": employee_id, "business_id": business_id}
                )
                return {"status": False}
            

async def preparing_user_notify_employee_quit(business_id : int, employee_id : int):
    logger.info(f"preparing_user_notify_employee_quit - Business ID: {business_id}; Employee ID: {employee_id}")
    async with async_session() as session:
        async with session.begin():
            try:
                business_query = select(Business).filter(Business.id == business_id, Business.active.is_(True))
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_user_notify_employee_quit - Business {business_id} not found")
                    return {"status": False}

                user_query = select(AppUser).filter(AppUser.id == business.owner_id, AppUser.active).with_for_update()
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    logger.error(f"preparing_user_notify_employee_quit - User (employer) {business.owner_id} not found")
                    return {"status": False}
                
                employee_query = select(AppUser).filter(AppUser.id == employee_id, AppUser.active)
                employee_result = await session.execute(employee_query)
                employee = employee_result.scalars().first()
                if not employee:
                    logger.error(f"preparing_user_notify_employee_quit - User (employee) {employee_id} not found")
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                lang = user.language
                sample_code = 'emloyee_quit'
                sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                sample_entity = ENTITY_USERNAME.get(lang, ENTITY_USERNAME.get(DEFAULT_LANGUAGE, ""))
                sample_text = f"{sample_pre_text} {sample_entity}: {employee.username}"

                notification = Notification(
                    date = current_time_unix,
                    receiver_user = user.id,
                    type = 'notify',
                    is_sample = True,
                    sample_code = sample_code,
                    sample_text = sample_text,
                    sample_data = {
                        "business_id": business_id,
                        "business_name": business.name,
                        "employee_id": employee_id,
                        "employee_username": employee.username
                    }
                )
                session.add(notification)
                await session.flush()

                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}
                business_id_key = f"{business_id}"
                if not isinstance(user.tab_notify.get(business_id_key), dict):
                    user.tab_notify[business_id_key] = {}
                user.tab_notify[business_id_key][TAB_MESSAGE_CENTER] = True
                flag_modified(user, "tab_notify")

                if not user.sid:
                    logger.error(f"preparing_user_notify_employee_quit - User {user.id} is not online. Information updated, but push notification is impossible")
                    return {"status": True, "rabbit_message": None}
                
                inner_message = {
                    "type": "execute",
                    "description": "user_notify_employee_quit",
                    "employer_id": user.id,
                    "notification_id": notification.id
                }

                full_message = {
                    "receiver": THIS_SERVICE_NAME,
                    "receiver_id": user.instance_id,
                    "message": inner_message
                }                
                    
                return {"status": True, "rabbit_message": full_message}                                    

            except Exception as e:
                logger.exception("preparing_user_notify_employee_quit - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_notify_employee_quit", "main exception error",
                    f"Error text: {str(e)}", {"employee_id": employee_id, "business_id": business_id}
                )
                return {"status": False}
            

async def preparing_users_notify_business_deleted(business_id : int, employees : list):
    logger.info(f"preparing_user_notify_employee_quit - Business ID: {business_id}; Employee list: {employees}")
    async with async_session() as session:
        async with session.begin():
            try:
                business_query = select(Business).filter(Business.id == business_id)
                business_result = await session.execute(business_query)
                business = business_result.scalars().first()
                if not business:
                    logger.error(f"preparing_users_notify_business_deleted - Business {business_id} not found")
                    return {"status": False}

                users_query = (
                    select(AppUser)
                    .where(AppUser.id.in_(employees))
                ).with_for_update()            
                users_result = await session.execute(users_query)
                users = users_result.scalars().all()

                if len(users) <= 0:
                    logger.error(f"preparing_user_notify_employee_quit - Users (employees) {employees} not found")
                    return {"status": False}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                rabbit_messages = []                

                sample_code = 'business_has_been_deleted'
                
                for user in users:
                    lang = user.language
                    sample_dict = SAMPLES_NOTIFICATION.get(sample_code, {})
                    sample_pre_text = sample_dict.get(lang, sample_dict.get(DEFAULT_LANGUAGE, ""))
                    sample_entity = ENTITY_BUSINESS.get(lang, ENTITY_BUSINESS.get(DEFAULT_LANGUAGE, ""))
                    sample_text = f"{sample_pre_text} {sample_entity}: {business.name}"
                    notification = Notification(
                        date = current_time_unix,
                        receiver_user = user.id,
                        type = 'notify',
                        is_sample = True,
                        sample_code = sample_code,
                        sample_text = sample_text,
                        sample_data = {
                            "business_id": business_id,
                            "business_name": business.name
                        }
                    )
                    session.add(notification)
                    await session.flush()

                    if not isinstance(user.tab_notify, dict):
                        user.tab_notify = {}
                    if not isinstance(user.tab_notify.get("0"), dict):
                        user.tab_notify["0"] = {}
                    user.tab_notify["0"][TAB_MESSAGE_CENTER] = True
                    flag_modified(user, "tab_notify")

                    if user.sid:
                        inner_message = {
                            "type": "execute",
                            "description": "user_notify_business_deleted",
                            "employee_id": user.id,
                            "notification_id": notification.id
                        }

                        full_message = {
                            "receiver": THIS_SERVICE_NAME,
                            "receiver_id": user.instance_id,
                            "message": inner_message
                        }
                        rabbit_messages.append(full_message)

                if rabbit_messages:
                    return {"status": True, "rabbit_messages": rabbit_messages}
                else:
                    logger.error(f"preparing_users_notify_business_deleted - All Users are not online. Information updated, but push notifications is impossible")
                    return {"status": True, "rabbit_messages": None}

            except Exception as e:
                logger.exception("preparing_users_notify_business_deleted - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_users_notify_business_deleted", "main exception error",
                    f"Error text: {str(e)}", {"employees": employees, "business_id": business_id}
                )
                return {"status": False}
            

async def preparing_push_new_order_to_business_orders(order_id: int, customer_user: int, supplier_team: list, customer_team: list) -> dict:
    logger.info(f"preparing_push_new_order_to_business_orders - custoner user ID: {customer_user}; Supplier team list: {supplier_team}; Supplier team list: {customer_team};")
    async with async_session() as session:
        async with session.begin():
            try:                
                order = (await session.execute(select(Order).where(Order.id == order_id, Order.deleted.is_(False)))).scalars().first()
                if not order:
                    return {"status": False}
                
                userlist = supplier_team + customer_team                

                users_query = (
                    select(AppUser)
                    .where(AppUser.id.in_(userlist))
                ).with_for_update()            
                users_result = await session.execute(users_query)
                users = users_result.scalars().all()

                if len(users) <= 0:
                    logger.error(f"preparing_push_new_order_to_business_orders - Users not found")
                    return {"status": False}

                rabbit_messages = []

                business_id_supplier_key = f"{order.supplier_id}"
                business_id_customer_key = f"{order.customer_id}"

                for user in users:                    
                    if not isinstance(user.tab_notify, dict):
                        user.tab_notify = {}
                    if user.id in supplier_team:
                        if not isinstance(user.tab_notify.get(business_id_supplier_key), dict):
                            user.tab_notify[business_id_supplier_key] = {}
                        user.tab_notify[business_id_supplier_key][TAB_CURRENT_ORDERS] = True
                    if user.id in customer_team:
                        if not isinstance(user.tab_notify.get(business_id_customer_key), dict):
                            user.tab_notify[business_id_customer_key] = {}
                        user.tab_notify[business_id_customer_key][TAB_CURRENT_ORDERS] = True
                    flag_modified(user, "tab_notify")

                    if user.sid:
                        inner_message = {
                            "type": "execute",
                            "description": "user_push_new_order",
                            "user_id": user.id,
                            "order_id": order_id
                        }

                        full_message = {
                            "receiver": THIS_SERVICE_NAME,
                            "receiver_id": user.instance_id,
                            "message": inner_message
                        }
                        rabbit_messages.append(full_message)

                if rabbit_messages:
                    return {"status": True, "rabbit_messages": rabbit_messages}
                else:
                    logger.error(f"preparing_push_new_order_to_business_orders - All Users are not online. Information updated, but push is impossible")
                    return {"status": True, "rabbit_messages": None}

            except Exception as e:
                logger.exception("preparing_push_new_order_to_business_orders - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_push_new_order_to_business_orders", "main exception error",
                    f"Error text: {str(e)}", {"order_id": order_id, "customer_user_id": customer_user, "userlist": userlist}
                )
                return {"status": False}
            

async def preparing_chat_message_broadcast(message_id: int, userlist: dict, need_tab_notify: bool) -> dict:
    logger.info(f"preparing_chat_message_broadcast - message ID: {message_id}; User list: {userlist}")
    async with async_session() as session:
        async with session.begin():
            try:
                message = (await session.execute(select(Message).where(Message.id == message_id, Message.deleted.is_(False)))).scalars().first()
                if not message:
                    return {"status": False}
                
                order = (await session.execute(select(Order).where(Order.id == message.order_id))).scalars().first()
                if not order:
                    return {"status": False}
                
                supplier_id = order.supplier_id
                customer_id = order.customer_id
                supplier_id_key = f"{supplier_id}"
                customer_id_key = f"{customer_id}"

                users_query = (
                    select(AppUser)
                    .where(AppUser.id.in_(userlist))
                ).with_for_update()            
                users_result = await session.execute(users_query)
                users = users_result.scalars().all()      

                if len(users) <= 0:
                    logger.error(f"preparing_chat_message_broadcast - Users not found")
                    return {"status": False}

                rabbit_messages = []

                for user in users:                    
                    if not isinstance(user.tab_notify, dict):
                        user.tab_notify = {}
                    if need_tab_notify:
                        user_businesses = [user.active_business_id] + user.business_list
                        if supplier_id in user_businesses:
                            if not isinstance(user.tab_notify.get(supplier_id_key), dict):
                                user.tab_notify[supplier_id_key] = {}
                            user.tab_notify[supplier_id_key][TAB_MESSAGE_CENTER] = True
                        if customer_id in user_businesses:
                            if not isinstance(user.tab_notify.get(customer_id_key), dict):
                                user.tab_notify[customer_id_key] = {}
                            user.tab_notify[customer_id_key][TAB_MESSAGE_CENTER] = True
                        flag_modified(user, "tab_notify")

                    if user.sid:
                        inner_message = {
                            "type": "execute",
                            "description": "order_message_broadcast",
                            "user_id": user.id,
                            "message_id": message_id,
                            "need_tab_notify": need_tab_notify
                        }

                        full_message = {
                            "receiver": THIS_SERVICE_NAME,
                            "receiver_id": user.instance_id,
                            "message": inner_message
                        }
                        rabbit_messages.append(full_message)

                if rabbit_messages:
                    return {"status": True, "rabbit_messages": rabbit_messages}
                else:
                    logger.error(f"preparing_chat_message_broadcast - All Users are not online. Information updated, but push is impossible")
                    return {"status": True, "rabbit_messages": None}

            except Exception as e:
                logger.exception("preparing_chat_message_broadcast - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_chat_message_broadcast", "main exception error",
                    f"Error text: {str(e)}", {"message_id": message_id, "userlist": userlist}
                )
                return {"status": False}


async def preparing_push_updated_order_to_users(order_id : int, need_tab_update : bool, supplier_team : list | None = None, customer_team : list | None = None) -> dict:
    logger.info(f"preparing_push_updated_order_to_users - order ID: {order_id}; need tab update: {need_tab_update}")
    async with async_session() as session:
        async with session.begin():
            try:

                if (supplier_team is not None and not isinstance(supplier_team, list)) or (customer_team is not None and not isinstance(customer_team, list)):
                    logger.error(f"preparing_push_updated_order_to_users - userlist is incorect - supplier team: {supplier_team}; customer_taem: {customer_team}")
                    return {"status": True, "rabbit_messages": None}
                
                need_determinate_supplier_team = False
                need_determinate_customer_team = False
                if supplier_team is None:
                    need_determinate_supplier_team = True
                if customer_team is None:
                    need_determinate_customer_team = True
                
                need_supplier_team_notify = False
                need_customer_team_notify = False
                if (isinstance(supplier_team, list) and len (supplier_team) > 0) or need_determinate_supplier_team:
                    need_supplier_team_notify = True
                if (isinstance(customer_team, list) and len (customer_team) > 0) or need_determinate_customer_team:
                    need_customer_team_notify = True                

                if not need_tab_update and not need_supplier_team_notify and not need_customer_team_notify:
                    logger.info(f"preparing_push_updated_order_to_users - need_tab_update is {need_tab_update} and userlist is - supplier team: {supplier_team}; customer_taem: {customer_team}")
                    return {"status": True, "rabbit_messages": None}
                
                order = (await session.execute(select(Order).where(Order.id == order_id, Order.deleted.is_(False)))).scalars().first()
                if not order:
                    return {"status": False}
                
                if need_determinate_supplier_team or need_determinate_customer_team:
                    business_ids = [order.supplier_id, order.customer_id, order.individual_id]
                    businesses = (await session.execute(
                        select(Business.id, Business.owner_id, Business.staff).where(Business.id.in_(business_ids))
                    )).mappings().all()
                    if len(businesses) != 2:
                        logger.error(f"Expected 2 businesses, got {len(businesses)} for ids={business_ids}")
                        return {"status": False}
                    supplier_business = None
                    customer_business = None
                    if businesses[0]["id"] == order.supplier_id:
                        supplier_business = businesses[0]
                        customer_business = businesses[1]
                    else:
                        supplier_business = businesses[1]
                        customer_business = businesses[0]
                    determinated_supplier_team = [supplier_business["owner_id"]] + supplier_business["staff"]
                    determinated_customer_team = [customer_business["owner_id"]] + customer_business["staff"]
                    if need_determinate_supplier_team:
                        supplier_team = determinated_supplier_team
                    if need_determinate_customer_team:
                        customer_team = determinated_customer_team

                userlist = (supplier_team or []) + (customer_team or [])

                users_query = (
                    select(AppUser)
                    .where(AppUser.id.in_(userlist))
                )
                users_result = await session.execute(users_query)
                users = users_result.scalars().all()

                if len(users) <= 0:
                    logger.error(f"preparing_push_updated_order_to_users - Users not found")
                    return {"status": False}

                rabbit_messages = []

                business_id_supplier_key = f"{order.supplier_id}"
                business_id_customer_key = None
                if order.customer_id:
                    business_id_customer_key = f"{order.customer_id}"
                elif order.individual_id:
                    business_id_customer_key = f"{order.individual_id}"

                if business_id_customer_key is None:
                    logger.error(f"preparing_push_updated_order_to_users - business_id_customer_key is not determinated")
                    return {"status": False}

                for user in users:
                    if need_tab_update:
                        if not isinstance(user.tab_notify, dict):
                            user.tab_notify = {}
                        if user.id in supplier_team:
                            if not isinstance(user.tab_notify.get(business_id_supplier_key), dict):
                                user.tab_notify[business_id_supplier_key] = {}
                            user.tab_notify[business_id_supplier_key][TAB_CURRENT_ORDERS] = True
                        if user.id in customer_team:
                            if not isinstance(user.tab_notify.get(business_id_customer_key), dict):
                                user.tab_notify[business_id_customer_key] = {}
                            user.tab_notify[business_id_customer_key][TAB_CURRENT_ORDERS] = True
                        flag_modified(user, "tab_notify")

                    if user.sid:
                        inner_message = {
                            "type": "execute",
                            "description": "user_update_existed_order",
                            "user_id": user.id,
                            "order_id": order_id,
                            "need_tab_notify": need_tab_update
                        }

                        full_message = {
                            "receiver": THIS_SERVICE_NAME,
                            "receiver_id": user.instance_id,
                            "message": inner_message
                        }
                        rabbit_messages.append(full_message)

                if rabbit_messages:
                    return {"status": True, "rabbit_messages": rabbit_messages}
                else:
                    logger.error(f"preparing_push_updated_order_to_users - All Users are not online. Information updated, but push is impossible")
                    return {"status": True, "rabbit_messages": None}

            except Exception as e:
                logger.exception("preparing_push_updated_order_to_users - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_push_updated_order_to_users", "main exception error",
                    f"Error text: {str(e)}", {"order_id": order_id, "need_tab_update": need_tab_update}
                )
                return {"status": False}
            

async def preparing_user_update_info_after_successfull_payment(user_id: int, payment_id: int) -> dict:
    logger.info(f"preparing_user_update_info_after_successfull_payment - user ID: {user_id}; payment ID: {payment_id};")
    async with async_session() as session:
        async with session.begin():
            try:                
                user_query = (
                    select(AppUser)
                    .where(AppUser.id == user_id)
                )
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                if not user:
                    logger.error(f"preparing_user_update_info_after_successfull_payment - User not found")
                    return {"status": False}
                
                if user.sid:
                    inner_message = {
                        "type": "execute",
                        "description": "user_update_info_after_successfull_payment",
                        "user_id": user_id,
                        "payment_id": payment_id,
                        "need_tab_notify": False
                    }

                    rabbit_message = {
                        "receiver": THIS_SERVICE_NAME,
                        "receiver_id": user.instance_id,
                        "message": inner_message
                    }                    

                
                return {"status": True, "rabbit_message": rabbit_message}
                

            except Exception as e:
                logger.exception("preparing_user_update_info_after_successfull_payment - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_update_info_after_successfull_payment", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id, "payment_id": payment_id}
                )
                return {"status": False}


async def preparing_user_update_info_after_bonus_accural(user_id: int, payback_info: dict) -> dict:
    logger.info(f"preparing_user_update_info_after_bonus_accural - user ID: {user_id}; payback info: {payback_info};")
    async with async_session() as session:
        async with session.begin():
            try:                
                user_query = (
                    select(AppUser)
                    .where(AppUser.id == user_id)
                )
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()

                if not user:
                    logger.error(f"preparing_user_update_info_after_bonus_accural - User not found")
                    return {"status": False}
                
                if not isinstance(payback_info, dict):
                    logger.error(f"preparing_user_update_info_after_bonus_accural - payback info is incorrect")
                    return {"status": False}
                
                if not isinstance(user.tab_notify, dict):
                    user.tab_notify = {}                        
                user.tab_notify[TAB_USER_PROFILE] = True
                flag_modified(user, "tab_notify")
                
                if user.sid:
                    payback_info["updated_referral_bonus"] = str(user.referral_bonus)
                    inner_message = {
                        "type": "execute",
                        "description": "user_update_info_after_bonus_accural",
                        "user_id": user_id,
                        "payback_info": payback_info,
                        "need_tab_notify": True
                    }

                    rabbit_message = {
                        "receiver": THIS_SERVICE_NAME,
                        "receiver_id": user.instance_id,
                        "message": inner_message
                    }                    

                
                return {"status": True, "rabbit_message": rabbit_message}
                

            except Exception as e:
                logger.exception("preparing_user_update_info_after_bonus_accural - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db(
                    "preparing_user_update_info_after_bonus_accural", "main exception error",
                    f"Error text: {str(e)}", {"user_id": user_id, "payback_info": payback_info}
                )
                return {"status": False}