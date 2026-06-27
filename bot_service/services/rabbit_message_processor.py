from config import settings
THIS_SERVICE_NAME = settings.BOT_SERVICE_NAME
INSTANCE_ID = settings.INSTANCE_ID

from services.bot_processor import send_orders_excel_file, process_bot_message_for_confirm, process_bot_message_for_send
from services.bot_message_sender import send_telegram_user_message_text_bot_notify_on

from logger_config import get_logger
logger = get_logger(__name__)

        
async def message_processing(full_message):
    print(f"rabbit_message_processor.py - ASYNC DEF message_processing - full message: {full_message}")
    
    if not isinstance(full_message, dict):
        logger.error(f"rabbit_message_processor.py - ASYNC DEF message_processing - Error: Recieved Rabbit MQ message is incorrect")
        return    
    if full_message.get("receiver", None) != THIS_SERVICE_NAME:
        logger.info(f"rabbit_message_processor.py - ASYNC DEF message_processing - This Service is not actual. Recieved Rabbit MQ message was ignored...")
        return
    if full_message.get("receiver_id", None) != INSTANCE_ID and full_message.get("receiver_id", None) != 'all' and full_message.get("receiver_id", None) != 'any':
        logger.info(f"rabbit_message_processor.py - ASYNC DEF message_processing - This POD ID is not actual. Recieved Rabbit MQ message was ignored...")
        return
    
    message = full_message.get("message", None)
    if message is None or not isinstance(message, dict):
        logger.error(f"rabbit_message_processor.py - ASYNC DEF message_processing - Error: Recieved Rabbit MQ sub-message is incorrect")
        return    

    print(f"rabbit_message_processor.py - received message: {message}")

    msg_type = message.get("type")
    description = message.get("description")

    print(f"rabbit_message_processor.py - message type: {msg_type}; Description: {description}")

    
    if msg_type == 'execute' and description == 'test':
        print(f"rabbit_message_processor.py: TEST COMPLETED!!! --------------------------------------------------- OK")
        data = message.get("data", None)
        print(f"INCOMING DATA: {data}")
        return
    
    if msg_type == 'execute' and description == 'get_orders_excel_file':
        print(f"rabbit_message_processor.py: get_orders_excel_file --------------------------------------- data received..........")
        data = message.get("data", None)
        print(f"INCOMING DATA: {data}")
        await send_orders_excel_file(data)
        return
    
    if msg_type == 'execute' and description == 'send_telegram_user_bot_message':
        print(f"rabbit_message_processor.py: send_telegram_user_bot_message - incoming rabbit inner message: {message}")
        user_tg_id = message.get("user_tg_id")
        bot_message = message.get("bot_message")
        await send_telegram_user_message_text_bot_notify_on(user_tg_id=user_tg_id, message=bot_message)        
        return
    
    if msg_type == 'execute' and description == 'process_bot_message_for_confirm':
        print(f"rabbit_message_processor.py: process_bot_message_for_confirm - incoming rabbit inner message: {message}")
        bm_id = message.get("bot_message_id")
        print(f"rabbit_message_processor.py: process_bot_message_for_confirm - BOT MESSAGE ID: {bm_id}")
        await process_bot_message_for_confirm(message_id=bm_id)
        return
    
    if msg_type == 'execute' and description == 'process_bot_message_for_send':
        print(f"rabbit_message_processor.py: process_bot_message_for_send - incoming rabbit inner message: {message}")
        bm_id = message.get("bot_message_id")
        print(f"rabbit_message_processor.py: process_bot_message_for_send - BOT MESSAGE ID: {bm_id}")
        await process_bot_message_for_send(message_id=bm_id)
        return
    



   
    
