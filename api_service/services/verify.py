import hmac
import hashlib
import urllib.parse
import base64
import json
from config import get_settings
settings = get_settings()

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
TELEGRAM_UNKNOWN_USER_NICKNAME = settings.TELEGRAM_UNKNOWN_USER_NICKNAME
TELEGRAM_UNNAMED_USER_NICKNAME = settings.TELEGRAM_UNNAMED_USER_NICKNAME

import httpx

from logger_config import get_logger
logger = get_logger(__name__)

def get_params(params_str: str) -> dict:
    """Decode Base64URL payload with JSON"""
    if not params_str:
        logger.warning("Empty params string")
        return {}
    try:
        logger.info(f"Incoming params string: {params_str}")
        # Correct URL-safe padding
        params_str += "=" * (-len(params_str) % 4)
        decoded = base64.urlsafe_b64decode(params_str.encode()).decode()
        parsed_params = json.loads(decoded)
        logger.info(f"Parsed params JSON: {parsed_params}")
        return parsed_params if isinstance(parsed_params, dict) else {}
    except Exception as e:
        logger.error(f"Error decoding startapp data: {e}", exc_info=True)
        return {}


def verify_user(query_string):
    decoded_query_string = urllib.parse.unquote(query_string)
    data = dict(urllib.parse.parse_qsl(decoded_query_string))
    logger.info(f'VERIFY.PY - verify_user - Data: {data}')
    received_hash = data.pop('hash', None)
    # Создаем секретный ключ
    secret_key = hmac.new('WebAppData'.encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
    # Создаем строку данных (data-check-string)
    check_string = '\n'.join([f"{key}={value}" for key, value in sorted(data.items())])
    # Создаем хэш с использованием секретного ключа
    hmac_obj = hmac.new(secret_key, check_string.encode(), hashlib.sha256)
    calculated_hash = hmac_obj.hexdigest()
    # Сравниваем хэши
    if received_hash == calculated_hash:        
        try:            
            user_data = json.loads(data['user'])
            logger.info(f'JSON is parced: {user_data}')
            user_data['auth_date'] = int(data['auth_date'])
                        
            user_data['first_name'] = user_data.get('first_name', "")
            user_data['last_name'] = user_data.get('last_name', "")
            user_data['username'] = user_data.get('username', "")
            user_data['language_code'] = user_data.get('language_code', "en")
            user_data['photo_url'] = user_data.get('photo_url', "")

            start_param_64 = data.get("start_param", None)
            if start_param_64:
                user_data['start_param'] = get_params(start_param_64)

        except Exception as e:
            logger.error(f"JSON parcing error: {e}")
            user_data = None
        return {"status": True, "user_data": user_data}    
    else:
        logger.error("Data is incorrect")
        return {"status": False}


async def get_telegram_user_info(user_telegram_id: int) -> dict:
    logger.info(f'FUNCTION get_telegram_user_info - TG_ID is {user_telegram_id}, type is {type(user_telegram_id)}')
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TELEGRAM_API_URL}/getChat",
                params={"chat_id": user_telegram_id}
            )
            data = response.json()

            if response.status_code == 200 and data.get("ok"):
                user = data.get("result", {})
                return {
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                    "username": user.get("username", "")
                }
            else:
                error_detail = data.get("description", "Unknown error")
                logger.error(f"Telegram API error: {error_detail}")
                return None
            
    except Exception as e:
        logger.error(f"Exception: {e}")
        return None


def get_concat_name(userinfo: dict) -> str:
    try:
        first_name = userinfo.get("first_name", None)
        last_name = userinfo.get("last_name", None)
        username = userinfo.get("username", None)

        if first_name and last_name:
            result = f"{first_name} {last_name}"
        elif not first_name and last_name:
            result = last_name
        elif not last_name and first_name:
            result = first_name
        elif username:
            result = username
        else:
            result = TELEGRAM_UNNAMED_USER_NICKNAME
        
        if result not in (TELEGRAM_UNNAMED_USER_NICKNAME, TELEGRAM_UNKNOWN_USER_NICKNAME) and len(result) > 255:
            result = result[:255]

        return result
    except Exception as e:
        logger.error(f"Exception: {e}")
        return TELEGRAM_UNKNOWN_USER_NICKNAME


def verify_phone_payload(payload: str) -> dict:
    try:
        logger.info(f"verify_phone_payload - Incoming payload: {payload}")

        if not payload:
            return {"status": False}

        data = dict(urllib.parse.parse_qsl(payload))

        received_hash = data.pop("hash", None)
        if not received_hash:
            return {"status": False}

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        check_string = "\n".join(
            f"{k}={v}"
            for k, v in sorted(data.items())
        )

        calculated_hash = hmac.new(
            secret_key,
            check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(received_hash, calculated_hash):
            return {"status": False}

        # parse contact JSON (REMOVE ESCAPES)
        contact = json.loads(data.get("contact", "{}"))

        return {
            "status": True,
            "contact": contact,
            "auth_date": int(data.get("auth_date"))
        }

    except Exception as e:
        logger.error(f"verify_phone_payload - ERROR: {e}", exc_info=True)
        return {"status": False}