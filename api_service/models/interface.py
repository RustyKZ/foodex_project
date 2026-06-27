from sqlalchemy import Column, Integer, BigInteger, String, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect

Base = declarative_base()

class LanguageInterface(Base):
    __tablename__ = 'language_interfaces'
    id = Column(Integer, primary_key=True, index=True)

    label = Column(String(5), nullable=False, default="en")
    name_english = Column(String(255), nullable=False, default="")
    name_native = Column(String(255), nullable=False, default="")
    interface = Column(JSON, default=lambda: {}, nullable=False)
    available = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<LanguageInterface label={self.label}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        return data