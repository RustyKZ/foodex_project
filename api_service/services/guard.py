from models.app_users import AppUser, UserBlacklist, UserGreylist
from models.monitoring import SystemAction
from models.bot_models import BotMessage

from sqlalchemy import or_
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

from datetime import datetime, timezone, timedelta

from constants.verify_error import *

import base64

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)

from config import get_settings
settings = get_settings()
ADMIN_TG_IDS = settings.ADMIN_TG_IDS

from services.error import put_critical_error_into_db


async def is_user_in_blacklist_by_ip_address(ip_address):
    async with async_session() as session:
        try:
            if not ip_address or not isinstance(ip_address, str):
                logger.error(f"is_user_in_blacklist_by_ip_address - Error: Incorrect IP address")
                return {"status": False, "message": f"Error: Incorrect IP address"}
            
            query = select(UserBlacklist).filter(UserBlacklist.ip_address == ip_address)
            result = await session.execute(query)
            user = result.scalars().first()
            if user is None:
                return {"status": False, "message": f"IP address {ip_address} is not in Blacklist"}
            else:                
                current_time = datetime.now(timezone.utc)
                current_time_unix = int(current_time.timestamp())
                log = {
                    "date": current_time.isoformat(),
                    "date_ts": current_time_unix,
                    "note": AUTHORIZATION_ATTEMPT
                }
                user.log.append(log)
                flag_modified(user, "log")
                await session.commit()
                return {"status": True, "message": f"IP address {ip_address} is in Blacklist!"}

        except Exception as session_error:
            await session.rollback()            
            await put_critical_error_into_db("is_user_in_blacklist_by_ip_address", "main exception error", f"Error text: {str(session_error)}", {"ip_address": ip_address})
            return {"status": False, "message": f"is_user_in_blacklist_by_ip_address - Session exception - {session_error}"}

async def is_user_in_blacklist_by_tg_id(tg_id):
    async with async_session() as session:
        try:
            if not isinstance(tg_id, int):
                logger.error(f"is_user_in_blacklist_by_tg_id - Error: Incorrect TG ID")
                return {"status": False, "message": f"Error: Incorrect TG ID"}
            query = select(UserBlacklist).filter(UserBlacklist.tg_id == tg_id)
            result = await session.execute(query)
            user = result.scalars().first()
            if user is None:
                return {"status": False, "message": f"TG ID {tg_id} is not in Blacklist"}
            else:
                current_time = datetime.now(timezone.utc)
                current_time_unix = int(current_time.timestamp())
                log = {
                    "date": current_time.isoformat(),
                    "date_ts": current_time_unix,
                    "note": AUTHORIZATION_ATTEMPT
                }
                user.log.append(log)
                flag_modified(user, "log")
                await session.commit()
                return {"status": True, "message": f"TG ID {tg_id} is in Blacklist!"}

        except Exception as session_error:
            await session.rollback()
            await put_critical_error_into_db("is_user_in_blacklist_by_tg_id", "main exception error", f"Error text: {str(session_error)}", {"user_tg_id": tg_id})
            return {"status": False, "message": f"is_user_in_blacklist_by_tg_id - Session exception - {session_error}"}
        

async def bad_verification_fallout(user_id: int, verify_error: str, ip_address: str) -> dict:
    try:
        fallout = None

        if verify_error in [VERIFY_ERROR_DB_QUERY_ERROR, VERIFY_ERROR_TOKEN_EXPIRED]:
            return {"status": True, "fallout": fallout}
        
        elif verify_error in [VERIFY_ERROR_SID_INVALID, VERIFY_ERROR_ID_MISMATCH]:
            greylisted = await put_user_into_greylist(user_id, ip_address, verify_error)
            if greylisted["status"]:
                fallout = FALLOUT_GREYLISTED
                return {"status": True, "fallout": fallout}
            else:
                fallout = FALLOUT_LIST_ADDING_ERROR
                return {"status": True, "fallout": fallout}
                
        elif verify_error in [VERIFY_ERROR_TOKEN_INVALID]:
            blacklisted = await put_user_into_blacklist(user_id, ip_address, verify_error)
            if blacklisted["status"]:
                fallout = FALLOUT_BLACKLISTED
                return {"status": True, "fallout": fallout}
            else:
                fallout = FALLOUT_LIST_ADDING_ERROR
                return {"status": True, "fallout": fallout}
        
        else:
            await put_critical_error_into_db("bad_verification_fallout", "Unknown verify error status", f"Unknown verify error status: {verify_error}", {"user_id": user_id, "verify_error": verify_error})
            return {"status": False}
            
    except Exception as e:
        logger.exception("bad_verification_fallout - MAIN EXCEPTION ERROR") 
        await put_critical_error_into_db("bad_verification_fallout", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "verify_error": verify_error})
        return {"status": False}
    

async def put_user_into_greylist(user_id: int, ip_address: str, verify_error: str) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).where(AppUser.id == user_id)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("put_user_into_greylist", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False}
                
                conditions = []
                conditions.append(UserGreylist.user_id == user_id)

                user_tg_id = None
                if user.tg_id:
                    user_tg_id = user.tg_id
                    conditions.append(UserGreylist.tg_id == user_tg_id)

                user_phone = None
                if user.phone:
                    user_phone = user.phone
                    conditions.append(UserGreylist.phone == user_phone)
                
                user_email = None
                if user.email:
                    user_email = user.email
                    conditions.append(UserGreylist.email == user_email)
                
                greylist_notes_query = select(UserGreylist).where(
                    or_(*conditions)
                ).with_for_update()

                greylist_notes_result = await session.execute(greylist_notes_query)
                greylists = greylist_notes_result.scalars().all()

                current_time = datetime.now(timezone.utc)
                current_time_unix = int(current_time.timestamp())

                if greylists:
                    log = {
                        "date_ts": current_time_unix,
                        "date": current_time.isoformat(),
                        "note": verify_error
                    }
                    put_status = False
                    for greylist_note in greylists:
                        if not isinstance(greylist_note.log, list):
                            greylist_note.log = []
                        greylist_note.log.append(log)
                        flag_modified(greylist_note, "log")
                        if len(greylist_note.log) == GREYLIST_ERROR_QUANTITY_FOR_ADMIN_INFORMATION:
                            text_message = f"{GREYLIST_LIMIT_ADMIN_NOTIFICATION} UserGreyList.id: {greylist_note.id}"
                            message_data = {
                                "message_text": text_message,
                                "html": True
                            }
                            new_bot_message = BotMessage(
                                sending_date = current_time_unix,
                                theme = "Notification for admin: GREYLIST record limit has been exceeded",
                                userlist = ADMIN_TG_IDS,
                                message_data = message_data,
                                confirmed = True
                            )
                            session.add(new_bot_message)                            
                        put_status = True                    
                    return {"status": put_status}
                else:
                    log = [{
                        "date_ts": current_time_unix,
                        "date": current_time.isoformat(),
                        "note": verify_error
                    }]
                    new_greylist_note = UserGreylist(
                        user_id = user_id,
                        add_date = current_time_unix,
                        ip_address = ip_address,
                        log = log
                    )
                    session.add(new_greylist_note)
                    await session.flush()
                    if user_tg_id:                        
                        new_greylist_note.tg_id = user_tg_id
                    if user_phone:
                        new_greylist_note.phone = user_phone
                    if user_email:
                        new_greylist_note.email = user_email
                    return {"status": True}
            
            except Exception as e:
                logger.exception("put_user_into_greylist - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db("put_user_into_greylist", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "ip_address": ip_address})
                return {"status": False}


async def put_user_into_blacklist(user_id: int, ip_address: str, verify_error: str) -> dict:
    async with async_session() as session:
        async with session.begin():
            try:
                # Checking user
                user_query = select(AppUser).where(AppUser.id == user_id)
                user_result = await session.execute(user_query)
                user = user_result.scalars().first()
                if not user:
                    await put_critical_error_into_db("put_user_into_blacklist", "user not found", f"User {user_id} not found", {"user_id": user_id})
                    return {"status": False}
                
                conditions = []
                conditions.append(UserBlacklist.user_id == user_id)

                user_tg_id = None
                if user.tg_id:
                    user_tg_id = user.tg_id
                    conditions.append(UserBlacklist.tg_id == user_tg_id)

                user_phone = None
                if user.phone:
                    user_phone = user.phone
                    conditions.append(UserBlacklist.phone == user_phone)
                
                user_email = None
                if user.email:
                    user_email = user.email
                    conditions.append(UserBlacklist.email == user_email)
                
                blacklist_notes_query = select(UserBlacklist).where(
                    or_(*conditions)
                ).with_for_update()

                blacklist_notes_result = await session.execute(blacklist_notes_query)
                blacklists = blacklist_notes_result.scalars().all()

                current_time = datetime.now(timezone.utc)
                current_time_unix = int(current_time.timestamp())

                if blacklists:
                    log = {
                        "date_ts": current_time_unix,
                        "date": current_time.isoformat(),
                        "note": verify_error
                    }
                    put_status = False
                    for blacklist_note in blacklists:
                        if not isinstance(blacklist_note.log, list):
                            blacklist_note.log = []
                        blacklist_note.log.append(log)
                        flag_modified(blacklist_note, "log")                                                
                        put_status = True                    
                    return {"status": put_status}
                else:
                    log = [{
                        "date_ts": current_time_unix,
                        "date": current_time.isoformat(),
                        "note": verify_error
                    }]
                    new_black_note = UserBlacklist(
                        user_id = user_id,
                        add_date = current_time_unix,
                        ip_address = ip_address,
                        log = log
                    )
                    session.add(new_black_note)
                    await session.flush()
                    if user_tg_id:                        
                        new_black_note.tg_id = user_tg_id
                    if user_phone:
                        new_black_note.phone = user_phone
                    if user_email:
                        new_black_note.email = user_email

                    text_message = f"{BLACKLIST_ADMIN_NOTIFICATION_EXISTED} UserBlackList.id: {blacklist_note.id}"
                    message_data = {
                        "message_text": text_message,
                        "html": True
                    }
                    new_bot_message = BotMessage(
                        sending_date = current_time_unix,
                        theme = "Notification for admin: BLACKLIST add note detected",
                        userlist = ADMIN_TG_IDS,
                        message_data = message_data,
                        confirmed = True
                    )
                    session.add(new_bot_message)                            
                    return {"status": True}
            
            except Exception as e:
                logger.exception("put_user_into_blacklist - MAIN EXCEPTION ERROR") 
                await put_critical_error_into_db("put_user_into_blacklist", "main exception error", f"Error text: {str(e)}", {"user_id": user_id, "ip_address": ip_address})
                return {"status": False}