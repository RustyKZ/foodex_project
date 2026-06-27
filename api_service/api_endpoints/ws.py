
from services.auth import user_register_tma, user_login_tma, backend_logout_user_by_sid
from services.userdata import get_advanced_userinfo, get_counter_agent_businesses_bundle, set_user_profile_notify_off
from services.jwt_token import verify_and_refresh_jwt_token_ws

from services.notifications import (set_tab_notify_off, get_start_app_messages, get_user_active_business_messages, create_new_message, mark_chat_readed, 
    get_user_notifications, get_message, get_bulk_messages)
from services.items import get_start_app_supplier_all_products_request, get_start_app_customer_products_request, get_start_app_individual_products_request, get_product_ordered_from_redis
from services.order_actions import get_business_orders, get_archive_business_orders_bundle
from services.guard import bad_verification_fallout

from rabbit.send_preparing import preparing_chat_message_broadcast

from constants.messages import MESSAGE, NOTIFICATION

from rabbit.rabbit_sender import broadcast_message_async


from logger_config import get_logger
logger = get_logger(__name__)

from api_endpoints.sio_init import sio



# Подключение
@sio.event
async def connect(sid, environ):
    logger.info(f"@Socket.IO - User connected: {sid}")
    await sio.emit("message", {"data": f"Socket connection estabilished. Socket ID is {sid}"}, to=sid)


# Отключение
@sio.event
async def disconnect(sid):
    try:
        logger.info(f"@SIO disconnect - User {sid} logged out correctly")        
    except Exception as e:        
        logger.exception(f"❌ @SIO disconnect - Exception: {e}")


@sio.event
async def ws_set_tab_notify_off(sid, data):
    logger.info(f"@Socket.IO - set_tab_notify_off - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]

        tab_notify_off = data["tab_notify_off"]

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - set_tab_notify_off - JWT verify is False: {jwt_verify} ", user_id=user_id)
            
        else:
            if isinstance(tab_notify_off, list) and len(tab_notify_off) > 0:
                change_tab_notify = await set_tab_notify_off(user_id, tab_notify_off)
                if change_tab_notify["status"]:
                    await sio.emit("update_user_tab_notify", {"tab_notify": change_tab_notify["tab_notify"]}, to=sid)

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - set_tab_notify_off - Global Exception: {e}")


@sio.event
async def ws_start_app_messages_request(sid, data):
    logger.info(f"@Socket.IO - ws_start_app_messages_request - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]

        local_messages = data["local_messages"]
        local_notifications = data["local_notifications"]

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_start_app_messages_request - JWT verify is False: {jwt_verify} ", user_id=user_id)
        else:
            start_app_messages = await get_start_app_messages(user_id, local_messages, local_notifications)
            if start_app_messages["status"]:
                chat_messages = start_app_messages.get("chat_messages", {})
                notifications = start_app_messages.get("notifications", [])
                order_names_for_messages_dict = start_app_messages.get("order_names_for_messages_dict", {})
                business_avatars_for_messages_dict = start_app_messages.get("business_avatars_for_messages_dict", {})
                await sio.emit("upload_start_app_messages", {
                        "chat_messages": chat_messages, 
                        "notifications": notifications, 
                        "order_names_for_messages_dict": order_names_for_messages_dict,
                        "business_avatars_for_messages_dict": business_avatars_for_messages_dict
                    }, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_start_app_messages_request - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_start_app_messages_request - Global Exception: {e}")


@sio.event
async def ws_start_app_supplier_all_products_request(sid, data):
    logger.info(f"@Socket.IO - ws_start_app_supplier_all_products_request - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]        

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_start_app_supplier_all_products_request - JWT verify is False: {jwt_verify} ", user_id=user_id)
        else:
            start_app_products = await get_start_app_supplier_all_products_request(user_id)
            if start_app_products["status"]:
                products_dict = start_app_products.get("products_dict", {})                
                await sio.emit("upload_start_app_supplier_products", {"products_dict": products_dict}, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_start_app_supplier_all_products_request - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_start_app_supplier_all_products_request - Global Exception: {e}")


@sio.event
async def ws_start_app_customer_products_request(sid, data):
    logger.info(f"@Socket.IO - ws_start_app_customer_products_request - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]        

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_start_app_customer_products_request - JWT verify is False: {jwt_verify} ", user_id=user_id)
        else:
            start_app_products = await get_start_app_customer_products_request(user_id=user_id)
            if start_app_products["status"]:
                products_dict = start_app_products.get("products_dict", {})
                total_count = start_app_products.get("total_count", 0)
                await sio.emit("upload_start_app_customer_products", {"products_dict": products_dict, "total_count": total_count}, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_start_app_customer_products_request - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_start_app_customer_products_request - Global Exception: {e}")


@sio.event
async def ws_start_app_individual_products_request(sid, data):
    logger.info(f"@Socket.IO - ws_start_app_individual_products_request - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]        

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_start_app_individual_products_request - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            start_app_products = await get_start_app_individual_products_request(user_id=user_id)
            if start_app_products["status"]:
                products_dict = start_app_products.get("products_dict", {})
                total_count = start_app_products.get("total_count", 0)
                one_supplier_info = start_app_products.get("one_supplier_info", None)
                await sio.emit("upload_start_app_individual_products", {"products_dict": products_dict, "total_count": total_count, "one_supplier_info": one_supplier_info}, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_start_app_individual_products_request - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_start_app_individual_products_request - Global Exception: {e}")


@sio.event
async def ws_request_products_ordered(sid, data):
    logger.info(f"@Socket.IO - ws_request_products_ordered - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]
        product_ids = data["product_ids"]
        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_request_products_ordered - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            redis_request_ordered_products = await get_product_ordered_from_redis(user_id=user_id, product_ids=product_ids)
            if redis_request_ordered_products["status"]:
                products_ordered = redis_request_ordered_products.get("products_ordered", {})
                await sio.emit("update_ordered_products", {"products_ordered": products_ordered}, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_request_products_ordered - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_products_ordered - Global Exception: {e}")


@sio.event 
async def ws_request_loading_business_orders(sid, data):
    logger.info(f"@Socket.IO - ws_request_loading_business_orders - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]
        business_id = data["business_id"]        
        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_request_loading_business_orders - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            request_business_orders = await get_business_orders(user_id=user_id, business_id=business_id)
            if request_business_orders["status"]:
                orders_dict = request_business_orders.get("orders_dict", {})
                await sio.emit("update_business_orders", {"orders_dict": orders_dict}, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_request_loading_business_orders - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_loading_business_orders - Global Exception: {e}")


@sio.event 
async def ws_request_loading_archive_business_orders(sid, data):
    logger.info(f"@Socket.IO - ws_request_loading_archive_business_orders - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]
        business_id = data["business_id"]
        bundle = data.get("bundle", 1)

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_request_loading_archive_business_orders - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            request_business_orders = await get_archive_business_orders_bundle(user_id=user_id, business_id=business_id, bundle=bundle)
            if request_business_orders["status"]:
                archive_orders_dict = request_business_orders.get("archive_orders_dict", {})
                total_count = request_business_orders.get("total_count")
                await sio.emit("update_archive_business_orders", {"archive_orders_dict": archive_orders_dict, "total_count": total_count, "bundle": bundle}, to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_request_loading_archive_business_orders - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_loading_archive_business_orders - Global Exception: {e}")


@sio.event
async def ws_request_upload_active_business_messages(sid, data):
    logger.info(f"@Socket.IO - ws_request_upload_active_business_messages - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]
        active_business = data["active_business"]
        local_messages = data["local_messages"]
        
        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_request_upload_active_business_messages - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            messages_request = await get_user_active_business_messages(user_id=user_id, business_id=active_business, local_messages=local_messages)
            if messages_request["status"]:
                chat_messages = messages_request.get("chat_messages", {})                
                order_names_for_messages_dict = messages_request.get("order_names_for_messages_dict", {})
                business_avatars_for_messages_dict = messages_request.get("business_avatars_for_messages_dict", {})
                await sio.emit("upload_active_business_messages", {
                        "chat_messages": chat_messages, 
                        "order_names_for_messages_dict": order_names_for_messages_dict,
                        "business_avatars_for_messages_dict": business_avatars_for_messages_dict,
                        "active_business_id": active_business
                    }, to=sid)

            else:
                logger.warning(f"@Socket.IO - ws_request_upload_active_business_messages - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_upload_active_business_messages - Global Exception: {e}")


@sio.event
async def ws_request_send_message(sid, data):
    logger.info(f"@Socket.IO - ws_request_send_message - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]
        message_data = data["message_data"]
        
        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_request_send_message - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            created_message = await create_new_message(user_id=user_id, message_data=message_data)
            if created_message["status"]:
                message_id = created_message.get("message_id")
                userlist = created_message.get("userlist", [])
                logger.info(f"ws_request_send_message - message: {message_id}", user_id=user_id)

                message_dict_request = await get_message(user_id=user_id, message_id=message_id)
                if message_dict_request["status"]:
                    chat_message = message_dict_request.get("chat_message", None)
                    active_business_id = message_dict_request.get("active_business_id", None)
                    if chat_message:
                        order_name_for_messages_dict = message_dict_request.get("order_name_for_messages_dict", {})
                        business_avatars_for_messages_dict = message_dict_request.get("business_avatars_for_messages_dict", {})
            
                        await sio.emit("push_active_business_message", {
                            "chat_message": chat_message,
                            "order_name_for_messages_dict": order_name_for_messages_dict,
                            "business_avatars_for_messages_dict": business_avatars_for_messages_dict,
                            "active_business_id": active_business_id
                        }, to=sid)
                
                preparing_broadcast = await preparing_chat_message_broadcast(message_id=message_id, userlist=userlist, need_tab_notify=True)
                if preparing_broadcast["status"]:
                    rabbit_messages = preparing_broadcast.get("rabbit_messages", None)
                    print(f"-------------- TEMPORARY LOG!!! rabbit messages: {rabbit_messages}")
                    if rabbit_messages:                                
                        for message in rabbit_messages:
                            await broadcast_message_async(message)
                else:
                    logger.error(f"ws_request_send_message - cannot prepare sending message(s) for RABBIT", user_id=user_id)
                
                

            else:
                logger.warning(f"@Socket.IO - ws_request_send_message - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_send_message - Global Exception: {e}")


@sio.event
async def ws_request_mark_chat_readed(sid, data):
    logger.info(f"@Socket.IO - ws_request_mark_chat_readed - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]
        mark_chat_readed_data = data["mark_chat_readed_data"]
        
        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - request_loading_send_message - JWT verify is False: {jwt_verify}", user_id=user_id)
        else:
            marked = await mark_chat_readed(user_id=user_id, chat_data=mark_chat_readed_data)
            if marked["status"]:                
                business_id = marked.get("business_id", 0)
                chat_type = marked.get("chat_type")
                unread_ids = mark_chat_readed_data.get("unread_ids", [])
                if chat_type == MESSAGE:
                    messages_request = await get_bulk_messages(user_id=user_id, messages_ids=unread_ids)
                    chat_messages = messages_request.get("chat_messages", {})                
                    order_names_for_messages_dict = messages_request.get("order_names_for_messages_dict", {})
                    business_avatars_for_messages_dict = messages_request.get("business_avatars_for_messages_dict", {})
                    await sio.emit("upload_active_business_messages", {
                        "chat_messages": chat_messages, 
                        "order_names_for_messages_dict": order_names_for_messages_dict,
                        "business_avatars_for_messages_dict": business_avatars_for_messages_dict,
                        "active_business_id": business_id
                    }, to=sid)

                    userlist = marked.get("userlist", [])
                    
                    if userlist and unread_ids:                    
                        for m_id in unread_ids:                    
                            preparing_broadcast = await preparing_chat_message_broadcast(message_id=m_id, userlist=userlist, need_tab_notify=False)                            
                            if preparing_broadcast["status"]:
                                rabbit_messages = preparing_broadcast.get("rabbit_messages", None)                                                
                                if rabbit_messages:                                
                                    for message in rabbit_messages:
                                        await broadcast_message_async(message)
                            else:
                                logger.error(f"ws_request_mark_chat_readed - cannot prepare sending message(s) for RABBIT", user_id=user_id)


                elif chat_type == NOTIFICATION:
                    read_ids = marked.get("read_ids", [])
                    notifications_request = await get_user_notifications(user_id=user_id, local_notifications=read_ids)
                    if notifications_request["status"]:
                        notifications = notifications_request.get("notifications", [])
                        await sio.emit("update_notifications_bulk", {"notifications": notifications}, to=sid)                    
            else:
                logger.warning(f"@Socket.IO - ws_request_mark_chat_readed - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_mark_chat_readed - Global Exception: {e}")


@sio.event
async def ws_start_app_counter_agent_businesses_request(sid, data):
    logger.info(f"@Socket.IO - ws_start_app_counter_agent_businesses_request - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]        

        bundle = 1

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_start_app_counter_agent_businesses_request - JWT verify is False: {jwt_verify} ", user_id=user_id)
        else:
            start_app_counter_agent_businesses = await get_counter_agent_businesses_bundle(user_id=user_id, bundle=bundle)
            if start_app_counter_agent_businesses["status"]:
                counter_agents_list = start_app_counter_agent_businesses.get("counter_agents_list", {})
                counter_agents_total_count = start_app_counter_agent_businesses.get("counter_agents_total_count", 0)
                bundle_id = start_app_counter_agent_businesses.get("bundle_id", 0)
                await sio.emit("update_counter_agents_bundle", 
                    {
                        "counter_agents_list": counter_agents_list, 
                        "counter_agents_total_count": counter_agents_total_count, 
                        "bundle_id": bundle_id
                    }, 
                    to=sid)
            else:
                logger.warning(f"@Socket.IO - ws_start_app_counter_agent_businesses_request - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_start_app_counter_agent_businesses_request - Global Exception: {e}")
        

@sio.event
async def ws_request_set_user_profile_notify_off(sid, data):
    logger.info(f"@Socket.IO - ws_request_set_user_profile_notify_off - SID: {sid}; Data: {data}")
    try:
        user_id = data["user_id"]
        jwt_token = data["jwt_token"]
        ip_address = data["ip_address"]        

        jwt_verify = await verify_and_refresh_jwt_token_ws(jwt_token, sid, user_id)
        if jwt_verify['status'] == False:
            verify_error = jwt_verify.get("verify_error")
            await bad_verification_fallout(user_id=user_id, verify_error=verify_error, ip_address=ip_address)
            logger.warning(f"@Socket.IO - ws_request_set_user_profile_notify_off - JWT verify is False: {jwt_verify} ", user_id=user_id)
        else:
            update_user_profile = await set_user_profile_notify_off(user_id=user_id)
            if update_user_profile["status"]:
                updated_tab_notify = update_user_profile.get("updated_tab_notify", None)
                if updated_tab_notify:
                    await sio.emit("update_user_tab_notify", {"tab_notify": updated_tab_notify}, to=sid)                
            else:
                logger.warning(f"@Socket.IO - ws_request_set_user_profile_notify_off - TEMPORARY CODE - else condition", user_id=user_id)
                pass

    except Exception as e:
        logger.exception(f"❌ @Socket.IO - ws_request_set_user_profile_notify_off - Global Exception: {e}")