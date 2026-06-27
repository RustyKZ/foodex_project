from sqlalchemy import Column, Integer, String, JSON, Text, BigInteger, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect

Base = declarative_base()

class AppError(Base):
    __tablename__ = 'app_error'

    id = Column(Integer, primary_key=True, index=True)

    date = Column(Integer, default=0, nullable=False)
    service = Column(String(255), nullable=False, default="")
    function = Column(String(255), nullable=False, default="")
    error_short = Column(String(255), nullable=False, default="")
    error_text = Column(Text, nullable=False, default="")
    context = Column(JSON, default=lambda: {}, nullable=False)

    def __repr__(self):
        return f"<AppError id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data


class UserAction(Base):
    __tablename__ = 'user_action'
    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, default=0, nullable=False)
    date = Column(Integer, default=0, nullable=False)
    action_type = Column(String(255), nullable=False, default="")
    entity_type = Column(String(255), nullable=False, default="")
    entity_id = Column(BigInteger, default=0, nullable=False)
    ip_address = Column(String(255), nullable=False, default="")
    extra_data = Column(JSON, default=lambda: {}, nullable=False)

    def __repr__(self):
        return f"<UserAction id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data
    

class SystemAction(Base):
    __tablename__ = 'system_action'
    id = Column(Integer, primary_key=True, index=True)

    date = Column(Integer, default=0, nullable=False)
    service = Column(String(255), nullable=False, default="")
    event = Column(String(255), nullable=False, default="")
    status = Column(String(50), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    meta_json = Column(JSON, default=lambda: {}, nullable=False)
    duration = Column(Float, nullable=False, default=0)

    def __repr__(self):
        return f"<SystemAction id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data