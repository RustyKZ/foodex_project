from models.interface import LanguageInterface

from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from config import get_settings
settings = get_settings()
DEFAULT_LANGUAGE = settings.DEFAULT_LANGUAGE

from session_config import async_session

from logger_config import get_logger
logger = get_logger(__name__)


async def get_interface(label: str) -> dict:
    async with async_session() as session:
        try:
            query = select(LanguageInterface).filter(LanguageInterface.label == label)
            result = await session.execute(query)
            lang_obj = result.scalars().first()
                        
            if lang_obj is None:
                query = select(LanguageInterface).filter(LanguageInterface.label == DEFAULT_LANGUAGE)
                result = await session.execute(query)
                lang_obj = result.scalars().first()
                        
            if lang_obj is None:
                query = select(LanguageInterface).filter(LanguageInterface.id == 1)
                result = await session.execute(query)
                lang_obj = result.scalars().first()
                        
            if lang_obj is None:
                return {}
                        
            if not isinstance(lang_obj.interface, dict):
                return {}
                        
            return lang_obj.interface
        except SQLAlchemyError as e:
            logger.error(f"get_interface - Exception SQLAlchemyError: {e}")
            return {}
        except Exception as e:
            logger.error(f"get_interface - Exception: {e}")
            return {}

async def get_interface_list() -> list:
    async with async_session() as session:
        try:
            query = select(LanguageInterface).filter(LanguageInterface.available == True)
            result = await session.execute(query)
            interfaces = result.scalars().all()
            # Формирование списка словарей с нужными полями
            interface_list = [
                {
                    "id": interface.id,
                    "label": interface.label,
                    "name_english": interface.name_english,
                    "name_native": interface.name_native,
                }
                for interface in interfaces
            ]
            return interface_list
        except SQLAlchemyError as e:
            logger.error(f"get_interface_list - Exception SQLAlchemyError: {e}")
            return []
        except Exception as e:
            logger.error(f"get_interface_list - Exception SQLAlchemyError: {e}")
            return []