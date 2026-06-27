
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from .config import settings


ASYNC_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.PLANNER_SERVICE_DB_USER}:"
    f"{settings.PLANNER_SERVICE_DB_PASSWORD}@"
    f"{settings.PLANNER_SERVICE_DB_HOST}:"
    f"{settings.PLANNER_SERVICE_DB_PORT}/"
    f"{settings.PLANNER_SERVICE_DB_NAME}"
)

# Создаем асинхронный движок
async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)

# Создаем фабрику сессий
async_session = sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession
)

SYNC_DATABASE_URL = (
    f"postgresql+psycopg2://{settings.PLANNER_SERVICE_DB_USER}:"
    f"{settings.PLANNER_SERVICE_DB_PASSWORD}@"
    f"{settings.PLANNER_SERVICE_DB_HOST}:"
    f"{settings.PLANNER_SERVICE_DB_PORT}/"
    f"{settings.PLANNER_SERVICE_DB_NAME}"
)

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

sync_session = sessionmaker(bind=sync_engine)
