from sqlalchemy import Column, Integer, BigInteger, String, Boolean, JSON, Numeric, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect
from decimal import Decimal

Base = declarative_base()

class Measure(Base):
    __tablename__ = 'measures'

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False, default="")
    name_short = Column(String(50), nullable=False, default="")
    dict_names = Column(JSON, default=lambda: {}, nullable=False)
    dict_names_short = Column(JSON, default=lambda: {}, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    order = Column(Integer, nullable=False, default=0)
    system = Column(Integer, nullable=False, default=0)
    type = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<Measure id={self.id}>"
    
    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data


class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, index=True)

    business_id = Column(Integer, nullable=False, default=0)
    date = Column(Integer, nullable=False, default=0)
    avatar_name = Column(String(255), nullable=False, default="")
    name = Column(String(255), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    measure_code = Column(String(50), nullable=False, default="")
    pack_params = Column(String(255), nullable=False, default="")
    price = Column(Numeric(16, 2), nullable=False, default=0)
    min_order_quantity = Column(Numeric(16, 2), nullable=False, default=1)
    max_order_quantity = Column(Numeric(16, 2), nullable=False, default=0)
    sku = Column(String(50), nullable=False, default="")
    category_code = Column(String(50), nullable=False, default="")
    active = Column(Boolean, default=True, nullable=False)
    daily_limit = Column(Numeric(16, 2), nullable=False, default=0)
    language = Column(String(5), nullable=False, default="")
    individual_customer = Column(Boolean, default=False, nullable=False)
    shipment_same_day = Column(Boolean, default=False, nullable=False)
    shipment_hours = Column(Integer, nullable=False, default=0)
    shipment_price = Column(Numeric(16, 2), nullable=False, default=0)

    deleted = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Product id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        if isinstance(data.get("price"), Decimal):
            data["price"] = str(data["price"])
        if isinstance(data.get("min_order_quantity"), Decimal):
            data["min_order_quantity"] = str(data["min_order_quantity"])
        if isinstance(data.get("max_order_quantity"), Decimal):
            data["max_order_quantity"] = str(data["max_order_quantity"])
        if isinstance(data.get("daily_limit"), Decimal):
            data["daily_limit"] = str(data["daily_limit"])
        if isinstance(data.get("shipment_price"), Decimal):
            data["shipment_price"] = str(data["shipment_price"])
        return data
    

class ProductTranslation(Base):
    __tablename__ = 'product_translation'

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(Integer, nullable=False, default=0)
    language = Column(String(5), nullable=False, default="")
    
    name = Column(String(255), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    pack_params = Column(String(255), nullable=False, default="")
    
    def __repr__(self):
        return f"<ProductTranslation id={self.id}>"
    
    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data

    

class Category(Base):
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False, default="")
    dict_names = Column(JSON, default=lambda: {}, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    order = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<Category id={self.id}>"
    
    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data    
