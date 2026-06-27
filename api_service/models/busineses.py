from sqlalchemy import Column, Integer, BigInteger, String, Boolean, JSON, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect
from decimal import Decimal

from constants.tariff import TARIFF_FREE

Base = declarative_base()


class Business(Base):
    __tablename__ = 'businesses'

    id = Column(Integer, primary_key=True, index=True)

    business_type = Column(Integer, default=1, nullable=False)
    
    owner_id = Column(Integer, default=0, nullable=False)
    name = Column(String(255), nullable=False, default="")
    description = Column(String(255), nullable=False, default="")
    avatar_name = Column(String(255), nullable=False, default="")
    reg_date = Column(Integer, default=0, nullable=False)    

    staff = Column(JSON, default=lambda: [], nullable=False)
    active_orders = Column(JSON, default=lambda: [], nullable=False)
    closed_orders = Column(JSON, default=lambda: [], nullable=False)

    contacts_allowed = Column(JSON, default=lambda: [], nullable=False)
    contacts_incoming = Column(JSON, default=lambda: [], nullable=False)
    contacts_outcoming = Column(JSON, default=lambda: [], nullable=False)

    tariff = Column(String(50), nullable=False, default=TARIFF_FREE)
    end_tariff_date = Column(Integer, default=0, nullable=False)

    language = Column(String(5), nullable=False, default="en")
    extra_languages = Column(JSON, default=lambda: [], nullable=False)

    address = Column(String(255), nullable=False, default="")
    geopoint = Column(Boolean, default=False, nullable=False)
    latitude = Column(Numeric(9, 6), nullable=False, default=0)
    longitude = Column(Numeric(9, 6), nullable=False, default=0)

    timezone = Column(String(255), nullable=False, default="UTC")
    currency = Column(String(50), nullable=False, default="USD")

    schedule = Column(JSON, default=lambda: {}, nullable=False)

    staff_incoming = Column(JSON, default=lambda: [], nullable=False)

    active = Column(Boolean, default=True, nullable=False)

    deleted = Column(Boolean, default=False, nullable=False)    

    def __repr__(self):
        return f"<Business id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        if isinstance(data.get("latitude"), Decimal):
            data["latitude"] = str(data["latitude"])
        if isinstance(data.get("longitude"), Decimal):
            data["longitude"] = str(data["longitude"])
        return data

# business_type: 1=Supplier, 2=Customer, 3=Individual

# schedule expamples:
# {} - 24/7
# { "without_rest": True (PRIMARY KEY, if it True other keys will be ignored)
#   "0": {"restday": False, "start": 28800, "end": 64800, "breaks" (optional): [{"start": 43200, "end": 46800}]}, - inactive field
#   ...
# } - 24/7
# {
#   "0": {"restday": False, "start": 28800, "end": 64800, "breaks" (optional): [{"start": 43200, "end": 46800}]},
#   "1": {"restday": False, "start": 28800, "end": 64800, "breaks" (optional): [{"start": 43200, "end": 46800}]},
#   ... ,
#   "5": {"restday": True (it is priority key, other keys will be ignored), "start": 28800, "end": 64800, "breaks" (opcional): [{"start": 43200, "end": 46800}]},
#   "6": {"restday": True}
# }



class BusinessTranslation(Base):
    __tablename__ = 'business_translation'

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, default=0, nullable=False)
    language = Column(String(5), nullable=False, default="en")
    
    name = Column(String(255), nullable=False, default="")
    description = Column(String(255), nullable=False, default="")
    address = Column(String(255), nullable=False, default="")
    
    def __repr__(self):
        return f"<BusinessTranslation id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        return data


