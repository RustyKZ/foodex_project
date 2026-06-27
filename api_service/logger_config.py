import logging
import sys
import time
from pythonjsonlogger import jsonlogger

class UserContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        user_id = kwargs.pop("user_id", 0)
        try:
            extra["user_id"] = int(user_id)
        except (ValueError, TypeError):
            extra["user_id"] = 0
        return msg, kwargs

def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(user_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)

    logger.addHandler(handler)

def get_logger(name=None):
    base_logger = logging.getLogger(name)
    return UserContextAdapter(base_logger, {})

