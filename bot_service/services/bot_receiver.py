from services.bot_handlers import *
from services.bot_broadcast import broadcast_message

from logger_config import get_logger
logger = get_logger(__name__)

import re
COMMAND_RE = re.compile(r"^/[a-z_]{1,100}(?:$|\$)")

from config import settings
ADMIN_IDS = settings.ADMIN_TG_IDS

DEFAULT_COMMANDS = {
    "start": handler_start,
    "about": handler_about,
    "confirm": handler_confirm,
    "test": handler_test
}

async def receive_bot_command(data):
    logger.info(f"[BOT] receive_bot_command: {data}")
    message = data.get("text", None)
    if not message:
        logger.info(f"[BOT] receive_bot_command - Message is empty")
        return
    if not COMMAND_RE.match(message):
        logger.info(f"[BOT] receive_bot_command - Message is not a COMMAND")
        return
    
    if "$" in message:
        command_part, argument = message.split("$", 1)  # только первое вхождение
    else:
        command_part, argument = message, ""

    command = command_part[1:]  # убираем "/"

    logger.info(f"[BOT] Parsed command: '{command}', argument: '{argument}'")

    # Здесь можно вызвать хэндлер:
    handler = DEFAULT_COMMANDS.get(command)
    if handler:
        await handler(data | {"command": command, "argument": argument})
    else:
        logger.info(f"[BOT] Unknown command: {command}")