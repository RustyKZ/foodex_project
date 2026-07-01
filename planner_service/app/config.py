# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

from functools import lru_cache
import os
import socket

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENVS_DIR = BASE_DIR.parent.parent / "envs"

RUNNING_IN_DOCKER = bool(os.getenv("RUNNING_IN_DOCKER"))

class Settings(BaseSettings):
    # Service
    PROJECT_NAME: str
    API_SERVICE_NAME: str = "API_SERVICE"
    BOT_SERVICE_NAME: str = "BOT_SERVICE"
    PLANNER_SERVICE_NAME: str = "PLANNER_SERVICE"
    INSTANCE_ID: str = ""

    # Database
    PLANNER_SERVICE_DB_NAME: str
    PLANNER_SERVICE_DB_USER: str
    PLANNER_SERVICE_DB_PASSWORD: str
    PLANNER_SERVICE_DB_HOST: str
    PLANNER_SERVICE_DB_PORT: str    

    # Rabbit
    PLANNER_SERVICE_RABBIT_USERNAME: str
    PLANNER_SERVICE_RABBIT_PASSWORD: str
    PLANNER_SERVICE_RABBIT_HOST: str

    RABBIT_BROADCAST_EXCHANGE_NAME: str
    RABBIT_DIRECT_EXCHANGE_NAME: str

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str
    
    REQUEST_BATCH_SIZE: int = 1000
    RABBIT_BROADCAST_MAX_DELAY: int = 500
    RABBIT_MESSAGE_LIST_LIMIT: int = 1000

    PUT_ERROR_INTO_DATABASE: bool = False

    DAILY_ACCOUNTING_HOUR: int = 0
    DAILY_ACCOUNTING_MINUTE: int = 30

    if RUNNING_IN_DOCKER:
        model_config = SettingsConfigDict(extra="ignore") 
    else:
        model_config = SettingsConfigDict(
            env_file=[
                ENVS_DIR / "local_shared.env",
                ENVS_DIR / "local_planner_service.env",
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
