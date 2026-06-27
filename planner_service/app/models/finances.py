from sqlalchemy import Column, Integer, String, Boolean, JSON, Numeric, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect
from decimal import Decimal

Base = declarative_base()


class TariffPlan(Base):
    
    __tablename__ = 'tariff_plan'

    id = Column(Integer, primary_key=True, index=True)
        
    slug = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False, default="")
    active = Column(Boolean, default=True, nullable=False)

    local_names = Column(JSON, default=lambda: {}, nullable=False)

    day_cost = Column(Numeric(16, 2), nullable=False, default=0)
    month_cost = Column(Numeric(16, 2), nullable=False, default=0)
    year_cost = Column(Numeric(16, 2), nullable=False, default=0)
    
    features = Column(JSON, default=lambda: {}, nullable=False)

    def __repr__(self):
        return f"<TariffPlan id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        if isinstance(data.get("day_cost"), Decimal):
            data["day_cost"] = str(data["day_cost"])
        if isinstance(data.get("month_cost"), Decimal):
            data["month_cost"] = str(data["month_cost"])
        if isinstance(data.get("year_cost"), Decimal):
            data["year_cost"] = str(data["year_cost"])
                
        return data
    

class AdCampaignBusinessPromo(Base):
    __tablename__ = 'ad_campaign_business_promo'

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, default=0, nullable=False)
    initiator_user_id = Column(Integer, default=0, nullable=False)
    deposit_credits = Column(Numeric(16, 2), nullable=False, default=0)
    daily_credits = Column(Numeric(16, 2), nullable=False, default=0)
    remaining_credits = Column(Numeric(16, 2), nullable=False, default=0)
    date_start = Column(Integer, default=0, nullable=False)
    date_end = Column(Integer, default=0, nullable=False)
    log = Column(JSON, default=lambda: [], nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    date_next_charge = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<AdCampaignBusinessPromo id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        if isinstance(data.get("deposit_credits"), Decimal):
            data["deposit_credits"] = str(data["deposit_credits"])
        if isinstance(data.get("daily_credits"), Decimal):
            data["daily_credits"] = str(data["daily_credits"])
        if isinstance(data.get("remaining_credits"), Decimal):
            data["remaining_credits"] = str(data["remaining_credits"])
                
        return data


class PaymentMethod(Base):
    __tablename__ = 'payment_methods'

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False, default="redirect")
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False, default="")
    name_translations = Column(JSON, default=lambda: {}, nullable=False)
    description = Column(Text, nullable=False, default="")
    description_translations = Column(JSON, default=lambda: {}, nullable=False)
    logo = Column(String(255), nullable=False, default="")
    currency = Column(String(50), nullable=False, default="USD")
    merchant_id = Column(String(255), nullable=False, default="")
    credits_per_unit = Column(Numeric(16, 2), nullable=False, default=0)
    custom_options = Column(JSON, default=lambda: {}, nullable=False)
    active = Column(Boolean, default=False, nullable=False)
    show_on_frontend = Column(Boolean, default=False, nullable=False)
    referrer_payback = Column(Boolean, default=False, nullable=False)
    payback_percent = Column(Numeric(5, 2), nullable=False, default=0)
    min_payment_value = Column(Numeric(16, 2), nullable=False, default=Decimal("1"))
    max_payment_value = Column(Numeric(16, 2), nullable=False, default=Decimal("1000000"))
    priority = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<PaymentMethod id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        if isinstance(data.get("credits_per_unit"), Decimal):
            data["credits_per_unit"] = str(data["credits_per_unit"])
        if isinstance(data.get("payback_percent"), Decimal):
            data["payback_percent"] = str(data["payback_percent"])
        if isinstance(data.get("min_payment_value"), Decimal):
            data["min_payment_value"] = str(data["min_payment_value"])
        if isinstance(data.get("max_payment_value"), Decimal):
            data["max_payment_value"] = str(data["max_payment_value"])
                
        return data


class Payment(Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Integer, default=0, nullable=False)
    method_code = Column(String(50), nullable=False, default="")
    user_id = Column(Integer, default=0, nullable=False)
    amount = Column(Numeric(16, 2), nullable=False, default=0)
    currency = Column(String(50), nullable=False, default="USD")
    credits_received = Column(Numeric(16, 2), nullable=False, default=0)
    referrer_id = Column(Integer, default=0, nullable=False)
    credits_payback = Column(Numeric(16, 2), nullable=False, default=0)
    details = Column(JSON, default=lambda: {}, nullable=False)
    confirmed = Column(Boolean, default=False, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    order_id = Column(String(255), nullable=False, default="")
    
    def __repr__(self):
        return f"<Payment id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}        
        if isinstance(data.get("amount"), Decimal):
            data["amount"] = str(data["amount"])
        if isinstance(data.get("credits_received"), Decimal):
            data["credits_received"] = str(data["credits_received"])
        if isinstance(data.get("credits_payback"), Decimal):
            data["credits_payback"] = str(data["credits_payback"])
                
        return data


class StarPaymentData(Base):
    __tablename__ = 'star_payment_data'

    id = Column(Integer, primary_key=True, index=True)    
    date = Column(Integer, default=0, nullable=False)
    tg_id = Column(BigInteger, nullable=True)
    amount = Column(Integer, default=0, nullable=False)
    charge_id = Column(String(255), unique=True, nullable=True)
    payload = Column(String(255), nullable=False, default="")
    processed = Column(Boolean, default=False, nullable=False)
    payment_id = Column(Integer, unique=True, nullable=True)
    
    def __repr__(self):
        return f"<StarPaymentData id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}                
        return data