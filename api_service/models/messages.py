from sqlalchemy import Column, Integer, String, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect


Base = declarative_base()

class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, index=True)
    
    order_id = Column(Integer, default=0, nullable=False)
    date = Column(Integer, default=0, nullable=False)
    sender_business = Column(Integer, default=0, nullable=False)
    sender_user = Column(Integer, default=0, nullable=False)
    receiver_business = Column(Integer, default=0, nullable=False)
    read_users = Column(JSON, default=lambda: [], nullable=False)
    text = Column(Text, nullable=False, default="")
    names_dict_users = Column(JSON, default=lambda: {}, nullable=False)
    names_dict_businesses = Column(JSON, default=lambda: {}, nullable=False)

    deleted = Column(Boolean, default=False, nullable=False)    

    def __repr__(self):
        return f"<Message id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data
    


class Notification(Base):
    
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, index=True)

    date = Column(Integer, default=0, nullable=False)
    receiver_user = Column(Integer, default=0, nullable=False)
    receiver_business = Column(Integer, nullable=True, default=None)
    type = Column(String(255), nullable=False, default="")
    is_sample = Column(Boolean, default=False, nullable=False)
    sample_code = Column(String(255), nullable=True, default=None)
    sample_text = Column(Text, nullable=True, default=None)
    sample_data = Column(JSON, default=lambda: {}, nullable=False)
    text = Column(Text, nullable=True, default=None)
    translations = Column(JSON, default=lambda: {}, nullable=False)
    read_date = Column(Integer, default=0, nullable=False)

    deleted = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Notification id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data