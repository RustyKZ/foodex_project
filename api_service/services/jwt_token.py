from models.app_users import AppUser

from sqlalchemy.future import select

import jwt
from config import settings
JWT_SECRET = settings.API_SERVICE_JWT_SECRET
JWT_ALGORITHM = settings.API_SERVICE_JWT_ALGORITHM
JWT_EXP_DELTA_SECONDS = settings.API_SERVICE_JWT_EXP_DELTA_SECONDS
JWT_REFRESH_PERIOD_SECONDS = settings.API_SERVICE_JWT_REFRESH_PERIOD_SECONDS

from rediska.redis_cli import redis_client
from constants.redis_vars import TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY
from constants.verify_error import *

from datetime import datetime, timezone

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)



async def get_jwt_token(user_id):
    jwt_token = ""
    try:        
        current_time_unix = int(datetime.now(timezone.utc).timestamp())
        try:
            await redis_client.zadd(TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY, {user_id: current_time_unix})
        except Exception as redis_error:
            logger.error(f"get_jwt_token - Exception Redis error: \n{redis_error}")        
        payload = {
            "user_id": user_id,
            "exp": current_time_unix + JWT_EXP_DELTA_SECONDS,
            "iat": current_time_unix
        }
        jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        if isinstance(jwt_token, bytes):
            jwt_token = jwt_token.decode('utf-8')
    except Exception as e:
        logger.error(f"get_jwt_token: Exception JWT - \n{e}")
        jwt_token = ""
    return jwt_token


async def verify_and_refresh_jwt_token_ws(token: str, sid: str, user_id: int):
    try:
        current_time_unix = int(datetime.now(timezone.utc).timestamp())
        try:
            await redis_client.zadd(TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY, {user_id: current_time_unix})
        except Exception as redis_error:
            logger.error(f"verify_and_refresh_jwt_token_ws - Exception Redis error: \n{redis_error}")
        try:
            async with async_session() as session:
                query = select(AppUser).filter(AppUser.id == user_id)            
                result = await session.execute(query)
                user = result.scalars().first()
        except Exception as e:
            logger.error(f"verify_and_refresh_jwt_token_ws - Exception - User query error: \n{e}")
            return {"status": False, "verify_error": VERIFY_ERROR_DB_QUERY_ERROR}

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        exp_timestamp = payload.get("exp")
        
        if exp_timestamp is None:
            return {"status": False, "verify_error": VERIFY_ERROR_TOKEN_INVALID}

        if user.sid != sid:
            return {"status": False, "verify_error": VERIFY_ERROR_SID_INVALID}
        
        if user.id != user_id or payload["user_id"] != user_id:
            return {"status": False, "verify_error": VERIFY_ERROR_ID_MISMATCH}
        
        current_time_unix = int(datetime.now(timezone.utc).timestamp())
        
        if exp_timestamp - current_time_unix < JWT_REFRESH_PERIOD_SECONDS:
            try:
                new_payload = {
                    "user_id": user_id,
                    "exp": current_time_unix + JWT_EXP_DELTA_SECONDS,
                    "iat": current_time_unix
                }
                new_token = jwt.encode(new_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
                return {"status": True, "new_token": new_token}
            except Exception as e:
                return {"status": True, "new_token": ""} 
        return {"status": True, "new_token": ""}

    except jwt.ExpiredSignatureError:
        logger.error(f"verify_and_refresh_jwt_token_ws - except: jwt.ExpiredSignatureError")
        return {"status": False, "verify_error": VERIFY_ERROR_TOKEN_EXPIRED}  # Токен истек
    except jwt.InvalidTokenError:
        logger.error(f"verify_and_refresh_jwt_token_ws - except: jwt.InvalidTokenError")
        return {"status": False, "verify_error": VERIFY_ERROR_TOKEN_INVALID}  # Токен некорректен


async def verify_and_refresh_jwt_token_http(token: str, user_id: int):
    try:        
        logger.info(f"verify_and_refresh_jwt_token_http - checking token for user {user_id}")
        current_time_unix = int(datetime.now(timezone.utc).timestamp())
        try:            
            await redis_client.zadd(TABLE_FOR_USERS_ONLINE_LAST_ACTIVITY, {user_id: current_time_unix})
        except Exception as redis_error:
            logger.error(f"verify_and_refresh_jwt_token_http - Exception Redis error: \n{redis_error}")

        try:
            async with async_session() as session:
                query = select(AppUser).filter(AppUser.id == user_id)            
                result = await session.execute(query)
                user = result.scalars().first()
        except Exception as e:
            logger.error(f"verify_and_refresh_jwt_token_http - Exception - User query error: \n{e}")
            return {"status": False, "verify_error": VERIFY_ERROR_DB_QUERY_ERROR}

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        exp_timestamp = payload.get("exp")
        
        if exp_timestamp is None:
            return {"status": False, "verify_error": VERIFY_ERROR_TOKEN_INVALID}
        
        if user.id != user_id or payload["user_id"] != user_id:
            return {"status": False, "verify_error": VERIFY_ERROR_ID_MISMATCH}
        
        if exp_timestamp - current_time_unix < JWT_REFRESH_PERIOD_SECONDS:
            try:
                new_payload = {
                    "user_id": user_id,
                    "exp": current_time_unix + JWT_EXP_DELTA_SECONDS,
                    "iat": current_time_unix
                }
                new_token = jwt.encode(new_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
                return {"status": True, "new_token": new_token}
            except Exception as e:
                return {"status": True, "new_token": ""} 
        return {"status": True, "new_token": ""}

    except jwt.ExpiredSignatureError:
        logger.error(f"verify_and_refresh_jwt_token_http - except: jwt.ExpiredSignatureError")
        return {"status": False, "verify_error": VERIFY_ERROR_TOKEN_EXPIRED}  # Токен истек
    except jwt.InvalidTokenError:
        logger.error(f"verify_and_refresh_jwt_token_http - except: jwt.InvalidTokenError")
        return {"status": False, "verify_error": VERIFY_ERROR_TOKEN_INVALID}  # Токен некорректен
