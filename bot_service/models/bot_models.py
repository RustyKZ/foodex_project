from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect


Base = declarative_base()

class BotMessages(Base):
    __tablename__ = "botmessages"

    id = Column(Integer, primary_key=True, index=True)

    date = Column(DateTime, nullable=True)
    sending_date =Column(Integer, nullable=False)
    theme = Column(String(255), nullable=False)
    userlist = Column(JSON, default=lambda: [], nullable=False)
    message_data = Column(JSON, nullable=False, default=lambda: {})
    confirmed = Column(Boolean, default=False, nullable=False)
    sended = Column(Boolean, default=False, nullable=False)
    not_actual = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<BotMessages(id={self.id})>"

    def to_dict(self):
        return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
    
# message_data dict type:
# "image_path": string
# "message_text": string
# "button_name": string
# "button_link": string
# "html": boolean

    
class BotCommands(Base):
    __tablename__ = "botcommands"

    id = Column(Integer, primary_key=True, index=True)

    command = Column(String(255), nullable=False)
    description = Column(String(255), nullable=False)
    response_data = Column(JSON, nullable=False, default=lambda: {})

    def __repr__(self):
        return f"<BotCommands(id={self.id})>"

    def to_dict(self):
        return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}

# response_data dict type:
# "image_path": string
# "message_text": string
# "button_name": string
# "button_link": string
# "script_name": string
# "html": boolean