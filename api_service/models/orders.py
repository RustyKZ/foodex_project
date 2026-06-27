from sqlalchemy import Column, Integer, BigInteger, String, Boolean, JSON, Numeric, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect
from decimal import Decimal

Base = declarative_base()


class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)

    date = Column(Integer, nullable=False, default=0)
    name = Column(String(255), nullable=False, default="")
    avatar = Column(String(255), nullable=False, default="")
    supplier_id = Column(Integer, nullable=False, default=0)
    customer_id = Column(Integer, nullable=False, default=0)
    individual_id = Column(Integer, nullable=False, default=0)
    delivery_date = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="")
    cart = Column(JSON, default=lambda: [], nullable=False)
    cart_order_date = Column(String(50), nullable=False, default="")
    customer_comment = Column(Text, nullable=False, default="")
    subtotal = Column(Numeric(16, 2), nullable=False, default=0)
    delivery_cost = Column(Numeric(16, 2), nullable=False, default=0)
    total = Column(Numeric(16, 2), nullable=False, default=0)
    missed_price = Column(Boolean, default=False, nullable=False)
    last_update = Column(Integer, nullable=False, default=0)
    update_timeline = Column(JSON, default=lambda: {}, nullable=False)
    request_free_delivery = Column(Boolean, default=False, nullable=False)
    currency = Column(String(100), nullable=False, default="USD")
    deleted = Column(Boolean, default=False, nullable=False)
    dispute = Column(JSON, default=lambda: {}, nullable=False)
    dispute_resolved_by_supplier_side = Column(Boolean, default=False, nullable=False)
    dispute_resolved_by_customer_side = Column(Boolean, default=False, nullable=False)
    rated_customer = Column(Boolean, default=False, nullable=False)
    rated_supplier = Column(Boolean, default=False, nullable=False)
    supplier_date = Column(String(50), nullable=False, default="")
    supplier_ttl = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<Order id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        if isinstance(data.get("subtotal"), Decimal):
            data["subtotal"] = str(data["subtotal"])
        if isinstance(data.get("delivery_cost"), Decimal):
            data["delivery_cost"] = str(data["delivery_cost"])
        if isinstance(data.get("total"), Decimal):
            data["total"] = str(data["total"])
        return data
    

class OrderItem(Base):
    __tablename__ = 'order_item'

    id = Column(Integer, primary_key=True)

    order_id = Column(Integer, nullable=False, default=0)
    product_id = Column(Integer, nullable=False, default=0)
    measure_code = Column(String(50), nullable=False, default="")
    amount = Column(Numeric(16, 2), nullable=False, default=0)
    price = Column(Numeric(16, 2), nullable=False, default=0)
    cost = Column(Numeric(16, 2), nullable=False, default=0)
    confirmed = Column(Boolean, default=False, nullable=False)
    product_snapshot = Column(JSON, default=lambda: {}, nullable=False)
    rated = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<OrderItem id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        if isinstance(data.get("amount"), Decimal):
            data["amount"] = str(data["amount"])
        if isinstance(data.get("price"), Decimal):
            data["price"] = str(data["price"])
        if isinstance(data.get("cost"), Decimal):
            data["cost"] = str(data["cost"])
        return data
    