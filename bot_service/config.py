# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from functools import lru_cache
import os
import socket

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENVS_DIR = BASE_DIR.parent / "envs"


class Settings(BaseSettings):    
    # Service
    PROJECT_NAME: str
    BOT_SERVICE_NAME: str = "BOT_SERVICE"
    API_SERVICE_NAME: str = "API_SERVICE"
    INSTANCE_ID: str = ""

    #Admin TG Ids
    ADMIN_TG_IDS: list[int] = Field(default_factory=list)

    #Sending params
    BROADCAST_BATCH_SIZE: int = 1000

    # Database
    BOT_SERVICE_DB_NAME: str
    BOT_SERVICE_DB_USER: str
    BOT_SERVICE_DB_PASSWORD: str
    BOT_SERVICE_DB_HOST: str
    BOT_SERVICE_DB_PORT: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_UNNAMED_USER_NICKNAME: str = "Unnamed User"
    TELEGRAM_UNKNOWN_USER_NICKNAME: str = "Unknown User"
    TELEGRAM_BOT_ADMIN_IDS_STR: str = "899014896"
    TELEGRAM_BOT_USERNAME: str

    # Paths
    LANDING_URL: str
    TELEGRAM_MINI_APP_URL: str

    # Rabbit
    BOT_SERVICE_RABBIT_USERNAME: str
    BOT_SERVICE_RABBIT_PASSWORD: str
    BOT_SERVICE_RABBIT_HOST: str

    RABBIT_DIRECT_EXCHANGE_NAME: str
    RABBIT_BROADCAST_EXCHANGE_NAME: str
    BOT_SERVICE_RABBIT_DIRECT_QUEUE_NAME: str
    
    # Custom    
    BOT_SERVICE_DEV_MODE: bool = False
    DEFAULT_LANGUAGE: str = "en"

    LOGOUT_TIMEOUT: int = 900
    REQUEST_BATCH_SIZE: int = 1000
    RABBIT_BROADCAST_MAX_DELAY: int = 500
    RABBIT_MESSAGE_LIST_LIMIT: int = 1000

    PUT_ERROR_INTO_DATABASE: bool = False

    model_config = SettingsConfigDict(
        env_file=[
            ENVS_DIR / "shared.env",
            ENVS_DIR / "bot_service_dev.env",
            # ENVS_DIR / "bot_service_prod.env",
        ],
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache
def get_settings():
    settings = Settings()    
    settings.INSTANCE_ID = os.getenv("POD_NAME", socket.gethostname())
    
    return settings

settings = get_settings()
