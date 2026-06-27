from config import settings

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = (
   f"postgresql+asyncpg://{settings.API_SERVICE_DB_USER}:"
   f"{settings.API_SERVICE_DB_PASSWORD}@"
   f"{settings.API_SERVICE_DB_HOST}:"
   f"{settings.API_SERVICE_DB_PORT}/"
   f"{settings.API_SERVICE_DB_NAME}"
)

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаем фабрику сессий
async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

