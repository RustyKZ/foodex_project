from models.app_users import AppUser
from models.messages import Message, Notification
from models.busineses import Business, BusinessTranslation
from models.orders import Order

from datetime import datetime, timezone, timedelta

from sqlalchemy import update
from sqlalchemy import or_, and_
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from fastapi import UploadFile

from session_config import async_session


from services.order_actions import get_business_opened_and_just_closed_orders_ids

from logger_config import get_logger
logger = get_logger(__name__)

from .error import put_critical_error_into_db

from constants.frontend import TAB_MESSAGE_CENTER
from constants.messages import *
from constants.business_types import SUPPLIER, CUSTOMER, INDIVIDUAL
from constants.limit_settings import DEFAULT_MESSAGES_UPLOAD_LIMIT

from shemas.messages import MarkChatReadedData, CreateNewMessageData

from pydantic import ValidationError


async def set_tab_notify_off(user_id : int, tab_notify_list : list) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                user = (
                    await session.execute(
                        select(AppUser)
                        .where(AppUser.id == user_id)
                        .with_for_update()
                    )
                ).scalars().first()

                if not user or not user.active:
                    await put_critical_error_into_db(
                        "set_tab_notify_off",
                        "incorrect data",
                        "User not found or inactive",
                        {"user_id": user_id}
                    )
                    return {"status": False}
                
                if isinstance(user.tab_notify, dict):
                    old_user_tab_notify = user.tab_notify
                else:
                    old_user_tab_notify = {}

                user_active_business = user.active_business_id
                if user_active_business is None:
                    business_key = "0"    
                else:
                    business_key = f"{user_active_business}"

                if isinstance(old_user_tab_notify.get(business_key), dict):
                    old_business_tab_notify = old_user_tab_notify.get(business_key)
                else:
                    old_business_tab_notify = {}
                
                new_business_tab_notify = {}
                for key, value in old_business_tab_notify.items():
                    if value and key not in tab_notify_list:
                        new_business_tab_notify[key] = True

                old_user_tab_notify[business_key] = new_business_tab_notify
                user.tab_notify = old_user_tab_notify
                flag_modified(user, "tab_notify")                

                return {"status": True, "tab_notify": user.tab_notify}

            except Exception as e:
                logger.exception(f"set_tab_notify_off - MAIN EXCEPTION: {e}")
                await put_critical_error_into_db(
                    "set_tab_notify_off",
                    "main exception error",
                    str(e),
                    {"user_id": user_id}
                )
                return {"status": False}
            

async def get_start_app_messages(user_id : int, local_messages : list, local_notifications : list) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id))).scalars().first()
                if not user:
                    await put_critical_error_into_db("get_start_app_messages", "incorrect data", "User not found", {"user_id": user_id})
                    return {"status": False}

                nots_filters = [
                    Notification.receiver_user == user_id,
                    Notification.deleted.is_(False)
                ]

                if local_notifications:
                    nots_filters.append(Notification.id.notin_(local_notifications))

                nots = (await session.execute(select(Notification).where(*nots_filters))).scalars().all()

                notifications = []
                for n in nots:
                    notifications.append(n.to_dict())
                
                chat_messages = {}
                odrer_names_for_messages_dict = {}
                business_avatars_for_messages_dict = {}

                user_active_business = user.active_business_id
                if user_active_business:
                    messages_request = await get_user_active_business_messages(user_id, user_active_business, local_messages)
                    if messages_request["status"]:
                        chat_messages = messages_request.get("chat_messages", {})
                        odrer_names_for_messages_dict = messages_request.get("odrer_names_for_messages_dict", {})
                        business_avatars_for_messages_dict = messages_request.get("business_avatars_for_messages_dict", {})

                return {
                    "status": True, 
                    "chat_messages": chat_messages, 
                    "notifications": notifications, 
                    "odrer_names_for_messages_dict": odrer_names_for_messages_dict,
                    "business_avatars_for_messages_dict": business_avatars_for_messages_dict
                }

            except Exception as e:
                logger.exception(f"get_start_app_messages - MAIN EXCEPTION: {e}")
                await put_critical_error_into_db("get_start_app_messages", "main exception error", str(e), {"user_id": user_id})
                return {"status": False}


async def get_user_notifications(user_id : int, local_notifications : list) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id))).scalars().first()
                if not user:
                    await put_critical_error_into_db("get_user_notifications", "incorrect data", "User not found", {"user_id": user_id})
                    return {"status": False}

                nots_filters = [
                    Notification.receiver_user == user_id,
                    Notification.deleted.is_(False)
                ]

                if local_notifications:
                    nots_filters.append(Notification.id.notin_(local_notifications))

                nots = (await session.execute(select(Notification).where(*nots_filters))).scalars().all()

                notifications = []
                for n in nots:
                    notifications.append(n.to_dict())

                return {
                    "status": True,                 
                    "notifications": notifications                    
                }

            except Exception as e:
                logger.exception(f"get_user_notifications - MAIN EXCEPTION: {e}")
                await put_critical_error_into_db("get_user_notifications", "main exception error", str(e), {"user_id": user_id})
                return {"status": False}            


async def get_user_active_business_messages(user_id: int, business_id: int, local_messages: list) -> dict:
    async with async_session() as session:        
        try:
            logger.info(f"get_user_active_business_messages - incoming data: User ID {user_id}, Business ID {business_id}, local messages {local_messages}")
            # Проверяем бизнес
            result = await session.execute(select(Business).where(Business.id == business_id))
            business = result.scalars().first()
            if not business:
                logger.error(f"get_user_active_business_messages - Business {business_id} not found", user_id=user_id)
                return {"status": False}

            if business.owner_id != user_id and user_id not in business.staff:
                logger.error(f"get_user_active_business_messages - User {user_id} has no access to messages of business {business_id}", user_id=user_id)
                return {"status": False}

            chat_messages = {}
            order_names_for_messages_dict = {}
            business_avatars_for_messages_dict = {}

            # Получаем открытые заказы
            opened_orders_request = await get_business_opened_and_just_closed_orders_ids(business_id)
            opened_orders_ids = opened_orders_request.get("order_ids", []) if opened_orders_request.get("status") else []

            if not opened_orders_ids:
                logger.info(f"get_user_active_business_messages - Business {business_id} has no opened orders", user_id=user_id)
                return {"status": False}

            # Фильтруем сообщения по бизнесу и открытым заказам
            message_filters = [
                or_(Message.sender_business == business_id, Message.receiver_business == business_id),
                Message.deleted.is_(False),
                Message.order_id.in_(opened_orders_ids)
            ]
            if local_messages:
                message_filters.append(Message.id.notin_(local_messages))

            messages_result = await session.execute(
                select(Message)
                .where(*message_filters)
                .order_by(Message.id.desc())
                .limit(DEFAULT_MESSAGES_UPLOAD_LIMIT)
            )
            messages = messages_result.scalars().all()
            

            # Собираем chat_messages, order_ids и business_ids
            order_ids = []
            businesses_ids = []            

            for msg in messages:
                order_ids.append(msg.order_id)            
                if msg.sender_business not in businesses_ids:
                    businesses_ids.append(msg.sender_business)
                if msg.receiver_business not in businesses_ids:
                    businesses_ids.append(msg.receiver_business)

            inner_data_order_avatars = {}
            # Получаем имена заказов
            if order_ids:
                order_names_result = await session.execute(select(Order.id, Order.name, Order.avatar).where(Order.id.in_(order_ids)))
                for row in order_names_result.mappings().all():
                    order_names_for_messages_dict[row['id']] = row['name']
                    inner_data_order_avatars[row['id']] = row['avatar']

            business_team = {}
            # Получаем аватары и типы бизнеса
            if businesses_ids:
                business_avatars_result = await session.execute(
                    select(Business.id, Business.avatar_name, Business.business_type, Business.owner_id, Business.staff)
                    .where(Business.id.in_(businesses_ids))
                )
                for row in business_avatars_result.mappings().all():
                    business_avatars_for_messages_dict[row['id']] = {
                        'avatar_name': row['avatar_name'],
                        'business_type': row['business_type']
                    }
                    business_team[row['id']] = [row['owner_id']] + row['staff']
            
            for msg in messages:
                chat_messages[str(msg.id)] = msg.to_dict()
                user_side = SENDER if msg.sender_business == business_id else RECEIVER
                chat_messages[str(msg.id)]["user_side"] = user_side
                chat_messages[str(msg.id)]["avatar"] = inner_data_order_avatars[msg.order_id] or ""
                if user_side == SENDER:
                    chat_messages[str(msg.id)]["receiver_team"] = business_team[msg.receiver_business]
                else:
                    chat_messages[str(msg.id)]["receiver_team"] = []

            return {
                "status": True,
                "chat_messages": chat_messages,
                "order_names_for_messages_dict": order_names_for_messages_dict,
                "business_avatars_for_messages_dict": business_avatars_for_messages_dict
            }

        except Exception as e:
            logger.exception(f"get_user_active_business_messages - MAIN EXCEPTION: {e}")
            await put_critical_error_into_db(
                "get_user_active_business_messages",
                "main exception error",
                str(e),
                {"user_id": user_id}
            )
            return {"status": False}
        

async def get_bulk_messages(user_id: int, messages_ids: list) -> dict:
    async with async_session() as session:        
        try:
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_bulk_messages", "incorrect data", "User not found", {"user_id": user_id})
                return {"status": False}
            
            result = await session.execute(select(Business).where(Business.id == user.active_business_id))

            business = result.scalars().first()
            if not business:
                logger.error(f"get_bulk_messages - Business {user.active_business_id} not found", user_id=user_id)
                return {"status": False}

            business_id = business.id

            if business.owner_id != user_id and user_id not in business.staff:
                logger.error(f"get_bulk_messages - User {user_id} has no access to messages of business {business_id}", user_id=user_id)
                return {"status": False}
            
            if not isinstance(messages_ids, list):
                await put_critical_error_into_db("get_bulk_messages", "incorrect data", f"Message list is not list: {type(messages_ids)}", {"user_id": user_id})
                return {"status": False}
                    
            chat_messages = {}
            order_names_for_messages_dict = {}
            business_avatars_for_messages_dict = {}

            if not messages_ids:
                return {
                    "status": True,
                    "chat_messages": chat_messages,
                    "order_names_for_messages_dict": order_names_for_messages_dict,
                    "business_avatars_for_messages_dict": business_avatars_for_messages_dict
                }
            
            message_filters = [
                Message.id.in_(messages_ids),
                or_(Message.sender_business == business_id, Message.receiver_business == business_id),
                Message.deleted.is_(False)                
            ]            

            messages_result = await session.execute(
                select(Message)
                .where(*message_filters)
                .order_by(Message.id.desc())
                .limit(DEFAULT_MESSAGES_UPLOAD_LIMIT)
            )
            messages = messages_result.scalars().all()
                        
            order_ids = []
            businesses_ids = []            

            for msg in messages:
                order_ids.append(msg.order_id)            
                if msg.sender_business not in businesses_ids:
                    businesses_ids.append(msg.sender_business)
                if msg.receiver_business not in businesses_ids:
                    businesses_ids.append(msg.receiver_business)

            inner_data_order_avatars = {}            
            if order_ids:
                order_names_result = await session.execute(select(Order.id, Order.name, Order.avatar).where(Order.id.in_(order_ids)))
                for row in order_names_result.mappings().all():
                    order_names_for_messages_dict[row['id']] = row['name']
                    inner_data_order_avatars[row['id']] = row['avatar']

            business_team = {}            
            if businesses_ids:
                business_avatars_result = await session.execute(
                    select(Business.id, Business.avatar_name, Business.business_type, Business.owner_id, Business.staff)
                    .where(Business.id.in_(businesses_ids))
                )
                for row in business_avatars_result.mappings().all():
                    business_avatars_for_messages_dict[row['id']] = {
                        'avatar_name': row['avatar_name'],
                        'business_type': row['business_type']
                    }
                    business_team[row['id']] = [row['owner_id']] + row['staff']
            
            for msg in messages:
                chat_messages[str(msg.id)] = msg.to_dict()
                user_side = SENDER if msg.sender_business == business_id else RECEIVER
                chat_messages[str(msg.id)]["user_side"] = user_side
                chat_messages[str(msg.id)]["avatar"] = inner_data_order_avatars[msg.order_id] or ""
                if user_side == SENDER:
                    chat_messages[str(msg.id)]["receiver_team"] = business_team[msg.receiver_business]
                else:
                    chat_messages[str(msg.id)]["receiver_team"] = []

            return {
                "status": True,
                "chat_messages": chat_messages,
                "order_names_for_messages_dict": order_names_for_messages_dict,
                "business_avatars_for_messages_dict": business_avatars_for_messages_dict
            }

        except Exception as e:
            logger.exception(f"get_bulk_messages - MAIN EXCEPTION: {e}")
            await put_critical_error_into_db(
                "get_bulk_messages",
                "main exception error",
                str(e),
                {"user_id": user_id}
            )
            return {"status": False}
            

async def get_message(user_id: int, message_id: int) -> dict:
    async with async_session() as session:        
        try:            
            user = (await session.execute(select(AppUser).where(AppUser.id == user_id))).scalars().first()
            if not user:
                await put_critical_error_into_db("get_message", "incorrect data", "User not found", {"user_id": user_id})
                return {"status": False}                            
                
            message = (await session.execute(select(Message).where(Message.id == message_id, Message.deleted.is_(False)))).scalars().first()
            if not message:
                logger.error(f"get_message - message {message_id} not found", user_id=user_id)
                return {"status": False}

            businesses_ids = [message.sender_business, message.receiver_business]

            if user.active_business_id not in businesses_ids:
                logger.info(f"get_message - message {message_id} has not relation for user {user_id} active business", user_id=user_id)
                return {"status": False}                            

            businesses = (await session.execute(select(Business).where(Business.id.in_(businesses_ids)))).scalars().all()
                
            if len(businesses) != 2:
                await put_critical_error_into_db("get_message", "incorrect data", "Both businesses not found", {"businesses ids": businesses_ids})
                return {"status": False}
            
            permitted_users = [businesses[0].owner_id] + businesses[0].staff + [businesses[1].owner_id] + businesses[1].staff
            if user_id not in permitted_users:
                logger.info(f"get_message - User {user_id} has not access for message {message_id}", user_id=user_id)
                return {"status": False}

            order = (await session.execute(select(Order).where(Order.id == message.order_id))).scalars().first()            
            if not order:
                await put_critical_error_into_db("get_message", "incorrect data", "Order not found", {"businesses ids": businesses_ids})
                return {"status": False}
            
            message_dict = message.to_dict()
            message_dict["avatar"] = order.avatar
            if user.active_business_id == message.sender_business:
                message_dict["user_side"] = SENDER
                if message.receiver_business == businesses[0].id:
                    message_dict["receiver_team"] = [businesses[0].owner_id] + businesses[0].staff
                elif message.receiver_business == businesses[1].id:
                    message_dict["receiver_team"] = [businesses[1].owner_id] + businesses[1].staff
                else:
                    message_dict["receiver_team"] = []
            else:
                message_dict["user_side"] = RECEIVER
                message_dict["receiver_team"] = []

            business_avatars_for_messages_dict = {
                f"{businesses[0].id}": {
                    "avatar_name": businesses[0].avatar_name,
                    "business_type": businesses[0].business_type
                },
                f"{businesses[1].id}": {
                    "avatar_name": businesses[1].avatar_name,
                    "business_type": businesses[1].business_type
                }
            }
                
            order_name_for_messages_dict = {f"{order.id}": order.name}
            
            return {
                "status": True, 
                "chat_message": message_dict,
                "order_name_for_messages_dict": order_name_for_messages_dict,
                "business_avatars_for_messages_dict": business_avatars_for_messages_dict,
                "active_business_id": user.active_business_id
            }

        except Exception as e:
            logger.exception(f"get_message - MAIN EXCEPTION: {e}")
            await put_critical_error_into_db("get_message", "main exception error", str(e), {"user_id": user_id, "message_id": message_id})
            return {"status": False}


async def mark_chat_readed(user_id: int, chat_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:                
                try:
                    validated_data = MarkChatReadedData(**chat_data)
                except ValidationError as e:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active == True))).scalars().first()
                if not user:
                    await put_critical_error_into_db("mark_chat_readed", "user not found or not active", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False}

                chat_type = validated_data.chat_type
                order_id = validated_data.order_id
                unread_ids = validated_data.unread_ids
                read_ids = validated_data.read_ids

                if not unread_ids:                    
                    return {"status": True, "read_ids": read_ids, "business_id": user.active_business_id, "chat_type": None}

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                interrested_users_clean = None

                if chat_type == NOTIFICATION:
                    stmt = (update(Notification).where(
                        Notification.id.in_(unread_ids),
                        Notification.receiver_user == user_id
                    ).values(read_date=current_time_unix))
                    await session.execute(stmt)
                
                elif chat_type == MESSAGE:
                    key_user = f"{user_id}"

                    messages = (await session.execute(
                        select(Message.id, Message.read_users, Message.names_dict_users, Message.sender_business, Message.receiver_business)
                        .where(
                            Message.id.in_(unread_ids),
                            Message.order_id == order_id,
                            or_(Message.sender_business == user.active_business_id, Message.receiver_business == user.active_business_id)
                        ).with_for_update()
                    )).mappings().all()                

                    business_ids = []

                    for row in messages:
                        read_users = list(row['read_users'])
                        if user_id not in read_users:
                            read_users.append(user_id)

                        names_dict_users = dict(row['names_dict_users'])
                        if names_dict_users.get(key_user) != user.username:
                            names_dict_users[key_user] = user.username

                        sender_business_id = row['sender_business']
                        receiver_business_id = row['receiver_business']
                        if sender_business_id not in business_ids:
                            business_ids.append(sender_business_id)
                        if receiver_business_id not in business_ids:
                            business_ids.append(receiver_business_id)

                        stmt = (
                            update(Message)
                            .where(Message.id == row['id'])
                            .values(
                                read_users=read_users,
                                names_dict_users=names_dict_users
                            )
                        )
                        await session.execute(stmt)

                    interrested_users = []
                    if business_ids:
                        businesses_data = (await session.execute(
                            select(Business.id, Business.owner_id, Business.staff)
                            .where(Business.id.in_(business_ids))
                        )).mappings().all()
                        for row in businesses_data:                            
                            interrested_users = interrested_users + [row['owner_id']] + row['staff']
                    
                    interrested_users_clean = []
                    for u_id in interrested_users:
                        if u_id not in interrested_users_clean and u_id != user_id:
                            interrested_users_clean.append(u_id)                    

                else:                    
                    return {"status": False}
                                
                return {"status": True, "read_ids": read_ids, "business_id": user.active_business_id, "chat_type": chat_type, "userlist": interrested_users_clean}

            except Exception as e:
                logger.exception(f"mark_chat_readed - MAIN EXCEPTION: {e}")
                await put_critical_error_into_db("mark_chat_readed", "main exception error", str(e), {"user_id": user_id, "chat_data": chat_data})
                return {"status": False}


async def create_new_message(user_id: int, message_data: dict) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                try:
                    validated_data = CreateNewMessageData(**message_data)
                except ValidationError as e:
                    return {"status": False, "notify_type": "error", "notify_code": "notify_error_input_error"}
                
                user = (await session.execute(select(AppUser).where(AppUser.id == user_id, AppUser.active == True))).scalars().first()
                if not user:
                    await put_critical_error_into_db("create_new_message", "user not found or not active", f"User {user_id} not found or not active", {"user_id": user_id})
                    return {"status": False}
                
                order_id = validated_data.order_id
                sender_user_id = validated_data.sender_user
                sender_business_id = validated_data.sender_business
                receiver_business_id = validated_data.receiver_business
                text = validated_data.text

                if sender_user_id != user_id:
                    logger.info(f"create_new_message - user {user_id} cannot to create this message: {message_data}", user_id=user_id)
                    return {"status": False}

                businesses_ids = [sender_business_id, receiver_business_id]

                if user.active_business_id not in businesses_ids:
                    logger.info(f"create_new_message - created new message has not relation for user {user_id} active business", user_id=user_id)
                    return {"status": False}                            

                businesses = (await session.execute(select(Business).where(Business.id.in_(businesses_ids)))).scalars().all()
                
                if len(businesses) != 2:
                    await put_critical_error_into_db("create_new_message", "incorrect data", "Both businesses not found", {"businesses ids": businesses_ids})
                    return {"status": False}

                names_dict_users = {}
                names_dict_users[f"{user_id}"] = user.username
                names_dict_businesses = {
                    businesses[0].id: {
                        "native": businesses[0].name
                    },
                    businesses[1].id: {
                        "native": businesses[1].name
                    }
                }
                    
                business_names_local = (await session.execute(
                    select(BusinessTranslation.business_id, BusinessTranslation.name, BusinessTranslation.language)
                    .where(BusinessTranslation.business_id.in_(businesses_ids))
                )).mappings().all()
                                
                for row in business_names_local:
                    names_dict_businesses.setdefault(row['business_id'], {"native": None})[row['language']] = row['name']

                names_dict_businesses = {
                    str(k): v for k, v in names_dict_businesses.items()
                }

                current_time_unix = int(datetime.now(timezone.utc).timestamp())

                new_message = Message(
                    order_id = order_id,
                    date = current_time_unix,
                    sender_business = sender_business_id,
                    sender_user = sender_user_id,
                    receiver_business = receiver_business_id,
                    text = text,
                    names_dict_users = names_dict_users,
                    names_dict_businesses = names_dict_businesses
                )
                session.add(new_message)
                await session.flush()

                message_id = new_message.id

                userlist = [businesses[0].owner_id] + businesses[0].staff + [businesses[1].owner_id] + businesses[1].staff
                if user_id in userlist:
                    userlist.remove(user_id)
                
                return {"status": True, "message_id": message_id, "userlist": userlist}

            except Exception as e:
                logger.exception(f"create_new_message - MAIN EXCEPTION: {e}")
                await put_critical_error_into_db("create_new_message", "main exception error", str(e), {"user_id": user_id, "message_data": message_data})
                return {"status": False}






