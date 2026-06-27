
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import socketio

from api_endpoints.http import router
from api_endpoints.ws import sio

from config import settings

CORS_ALLOW_ORIGINS = [o.strip() for o in settings.API_SERVICE_CORS_ALLOW_ORIGINS.split(",") if o.strip()] 
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"] 

from rediska.redis_cli import create_redis, close_redis
from rediska.redis_queue import redis_product_ordered_worker

#from services.rabbit_message_processor import message_processing
from logger_config import setup_logger

from rabbit.rabbit_receiver import receive_message, receive_distributed_task
#from services.rabbit_sender import broadcast_message_async

setup_logger()

# Socket.IO приложение
socketio_app = socketio.ASGIApp(sio)

# Lifespan-события запуска
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("!!! MAIN.PY: FastAPI lifespan started...")

    # Redis
    app.state.redis = await create_redis()
    # asyncio.create_task(receive_message())
    # asyncio.gather(
    #        receive_message(),
    #        receive_distributed_task()
    #    )

    app.state.rabbit_broadcast_task = asyncio.create_task(receive_message())
    app.state.rabbit_direct_task = asyncio.create_task(receive_distributed_task())
    app.state.redis_worker_task = asyncio.create_task(redis_product_ordered_worker())

    yield

    app.state.rabbit_broadcast_task.cancel()
    app.state.rabbit_direct_task.cancel()
    app.state.redis_worker_task.cancel()

    await close_redis(app.state.redis)

    print("!!! MAIN.PY: FastAPI lifespan ended")

# Создание FastAPI приложения
fastapi_app = FastAPI(lifespan=lifespan)

# Подключаем маршруты
fastapi_app.include_router(router)

# CORS
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)

# Монтируем Socket.IO приложение
fastapi_app.mount("/", socketio_app)
