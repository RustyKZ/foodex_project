import socketio
from config import settings
CORS_ALLOWED_ORIGINS = [o.strip() for o in settings.API_SERVICE_WS_CORS_ALLOW_ORIGINS.split(",") if o.strip()] 

if "*" in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = "*"
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=CORS_ALLOWED_ORIGINS)