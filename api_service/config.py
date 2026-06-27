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
    #Admin TG Ids
    ADMIN_TG_IDS: list[int] = Field(default_factory=list)

    #Guard
    BLOCK_BY_IP_ADDRESS: bool = False

    # Service
    PROJECT_NAME: str
    API_SERVICE_NAME: str = "API_SERVICE"
    BOT_SERVICE_NAME: str = "BOT_SERVICE"
    INSTANCE_ID: str = ""

    # Database
    API_SERVICE_DB_NAME: str
    API_SERVICE_DB_USER: str
    API_SERVICE_DB_PASSWORD: str
    API_SERVICE_DB_HOST: str
    API_SERVICE_DB_PORT: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_UNNAMED_USER_NICKNAME: str = "Unnamed User"
    TELEGRAM_UNKNOWN_USER_NICKNAME: str = "Unknown User"

    # CORS
    API_SERVICE_CORS_ALLOW_ORIGINS: str = ""
    API_SERVICE_WS_CORS_ALLOW_ORIGINS: str = ""

    # Rabbit
    API_SERVICE_RABBIT_USERNAME: str
    API_SERVICE_RABBIT_PASSWORD: str
    API_SERVICE_RABBIT_HOST: str

    RABBIT_BROADCAST_EXCHANGE_NAME: str
    RABBIT_DIRECT_EXCHANGE_NAME: str
    API_SERVICE_RABBIT_DIRECT_QUEUE_NAME: str


    # MinIO
    MINIO_STORAGE_URL: str 
    MINIO_USERNAME: str
    MINIO_PASSWORD: str
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "foodex"
    MINIO_BUSINESSES_FOLDER_JPEG: str = "businesses/jpeg"
    MINIO_BUSINESSES_FOLDER_WEBP: str = "businesses/webp"
    MINIO_PRODUCTS_FOLDER_JPEG: str = "products/jpeg"
    MINIO_PRODUCTS_FOLDER_WEBP: str = "products/webp"


    
    # JWT
    API_SERVICE_JWT_SECRET: str
    API_SERVICE_JWT_ALGORITHM: str = "HS256"
    API_SERVICE_JWT_EXP_DELTA_SECONDS: int = 3600
    API_SERVICE_JWT_REFRESH_PERIOD_SECONDS: int = 600

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str
    

    # Custom    
    API_SERVICE_DEV_MODE: bool = False
    DEFAULT_LANGUAGE: str = "en"

    LOGOUT_TIMEOUT: int = 900
    REQUEST_BATCH_SIZE: int = 1000
    RABBIT_BROADCAST_MAX_DELAY: int = 500
    RABBIT_MESSAGE_LIST_LIMIT: int = 1000

    PUT_ERROR_INTO_DATABASE: bool = False

    PAYMENT_PAYPAL_CLIENT_ID: str
    PAYMENT_PAYPAL_SECRET: str
    PAYPAL_API_URL: str = "https://api-m.paypal.com"
    PAYPAL_REDIRECT_AFTER_PAYMENT_SUCCESS: str = "https://foodexapp.top/payments/paypal/success"
    PAYPAL_REDIRECT_AFTER_PAYMENT_CANCEL: str = "https://foodexapp.top/payments/paypal/cancel"



    model_config = SettingsConfigDict(
        env_file=[
            ENVS_DIR / "shared.env",
            ENVS_DIR / "api_service_dev.env",
            # ENVS_DIR / "api_service_prod.env",
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
