from sqlalchemy import Column, Integer, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.inspection import inspect

Base = declarative_base()

class ReviewBusiness(Base):
    __tablename__ = 'review_business'

    id = Column(Integer, primary_key=True, index=True)

    banned_by_admin = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(Text, default="", nullable=False)

    date = Column(Integer, default=0, nullable=False)
    order_id = Column(Integer, default=0, nullable=False)
    business_id = Column(Integer, default=0, nullable=False)
    author_user_id = Column(Integer, default=0, nullable=False)
    author_business_id = Column(Integer, default=0, nullable=False)
    comment = Column(Text, nullable=False, default="")
    reply = Column(Text, nullable=False, default="")
    rate = Column(Integer, default=0, nullable=False)
    
    def __repr__(self):
        return f"<ReviewBusiness id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data


class ReviewProduct(Base):
    __tablename__ = 'review_product'

    id = Column(Integer, primary_key=True, index=True)

    banned_by_admin = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(Text, default="", nullable=False)

    date = Column(Integer, default=0, nullable=False)
    product_id = Column(Integer, default=0, nullable=False)
    order_id = Column(Integer, default=0, nullable=False)
    business_id = Column(Integer, default=0, nullable=False)
    author_user_id = Column(Integer, default=0, nullable=False)
    author_business_id = Column(Integer, default=0, nullable=False)
    comment = Column(Text, nullable=False, default="")
    reply = Column(Text, nullable=False, default="")
    rate = Column(Integer, default=0, nullable=False)
    
    def __repr__(self):
        return f"<ReviewProduct id={self.id}>"

    def to_dict(self):
        data = {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
        return data
    