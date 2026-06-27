
from sqlalchemy import Column, Boolean, Integer, String, DateTime, JSON
from datetime import datetime, timezone
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BotMessage(Base):
    __tablename__ = "botmessages"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    sending_date = Column(Integer, default=0, nullable=False)
    theme = Column(String(255), nullable=False, default="")
    userlist = Column(JSON, default=lambda: [], nullable=False)
    message_data = Column(JSON, default=lambda: {}, nullable=False)
    confirmed = Column(Boolean, default=False, nullable=False)
    sended = Column(Boolean, default=False, nullable=False)
    not_actual = Column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<BotMessage id={self.id} theme={self.theme!r}>"