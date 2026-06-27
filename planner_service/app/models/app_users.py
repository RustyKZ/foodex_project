from sqlalchemy import Column, Integer, BigInteger, String, Boolean, JSON, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect
from decimal import Decimal

Base = declarative_base()

class AppUser(Base):
    __tablename__ = 'app_users'

    id = Column(Integer, primary_key=True, index=True)
    
    tg_id = Column(BigInteger, unique=True, nullable=True)
    tg_firstname = Column(String(255), nullable=False, default="")
    tg_lastname = Column(String(255), nullable=False, default="")
    tg_username = Column(String(255), unique=True, nullable=True)
    username = Column(String(255), nullable=False, default="")
    
    reg_date = Column(Integer, default=0, nullable=False)
    referrer_id = Column(Integer, nullable=False, default=0)
    referrer_username = Column(String(255), nullable=False, default="")
    language = Column(String(5), nullable=False, default="en")

    last_activity = Column(Integer, default=0, nullable=False)
    instance_id = Column(String(255), nullable=False, default="")
    sid = Column(String(255), nullable=False, default="")
    
    tab_notify = Column(JSON, default=lambda: {}, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    
    active_business_id = Column(Integer, default=0, nullable=False)    
    business_list = Column(JSON, default=lambda: [], nullable=False)
    individual_id = Column(Integer, default=0, nullable=False)

    contacts_allowed = Column(JSON, default=lambda: [], nullable=False)
    contacts_incoming = Column(JSON, default=lambda: [], nullable=False)
    contacts_outcoming = Column(JSON, default=lambda: [], nullable=False)

    credits = Column(Numeric(16, 2), nullable=False, default=0)
    phone = Column(String(255), unique=True, nullable=True)
    is_phone_verified = Column(Boolean, default=False, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    is_email_verified = Column(Boolean, default=False, nullable=False)

    settings = Column(JSON, default=lambda: {}, nullable=False)

    referrals = Column(JSON, default=lambda: [], nullable=False)
    referral_bonus = Column(Numeric(16, 2), nullable=False, default=0)

    limit_of_business = Column(Integer, nullable=False, default=3)

    dict_of_username = Column(JSON, default=lambda: {}, nullable=False)

    outcoming_employer_business_id = Column(Integer, default=0, nullable=False)
    outcoming_employer_business_name = Column(String(255), nullable=False, default="")
    outcoming_request_delete_date = Column(Integer, default=0, nullable=False)

    favorite_businesses = Column(JSON, default=lambda: [], nullable=False)
    favorite_products = Column(JSON, default=lambda: [], nullable=False)

    def __repr__(self):
        return f"<AppUser id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        if isinstance(data.get("credits"), Decimal):
            data["credits"] = str(data["credits"])
        if isinstance(data.get("referral_bonus"), Decimal):
            data["referral_bonus"] = str(data["referral_bonus"])
        return data
    


class UserGreylist(Base):
    __tablename__ = 'users_greylist'

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, unique=True, nullable=True)
    tg_id = Column(BigInteger, unique=True, nullable=True)
    phone = Column(String(255), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    ip_address = Column(String(255), nullable=False, default="")
    add_date = Column(Integer, default=0, nullable=False)
    log = Column(JSON, default=lambda: [], nullable=False)

    def __repr__(self):
        return f"<UserGreylist id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data
    
    
class UserBlacklist(Base):
    __tablename__ = 'users_blacklist'

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, unique=True, nullable=True)
    tg_id = Column(BigInteger, unique=True, nullable=True)
    phone = Column(String(255), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    ip_address = Column(String(255), nullable=False, default="")
    add_date = Column(Integer, default=0, nullable=False)
    log = Column(JSON, default=lambda: [], nullable=False)

    def __repr__(self):
        return f"<UserBlacklist id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data