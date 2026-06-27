
from logger_config import get_logger
logger = get_logger(__name__)

from redis.asyncio import Redis 
from config import settings 
redis_client = Redis( 
    host=settings.REDIS_HOST, 
    port=settings.REDIS_PORT, 
    password=settings.REDIS_PASSWORD, 
    decode_responses=True, 
    ) 


async def create_redis() -> Redis:
    try:
        await redis_client.ping()
        logger.info("✅ redis_cli.py - Redis connection successful")
        return redis_client
    except Exception as e:
        logger.error(f"❌ redis_cli.py Redis connection failed: {e}")
        raise e  # чтобы FastAPI видел ошибку и не продолжал старт


async def close_redis(redis: Redis) -> None: 
    await redis.close()