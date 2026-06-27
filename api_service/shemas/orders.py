from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal, Dict, Union
from datetime import datetime
from constants.business_types import SUPPLIER_ROLE, CUSTOMER_ROLE


class CartItem(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: float = Field(..., gt=0)


class MakeOrder(BaseModel):
    business_id: int = Field(..., gt=0)
    cart: List[CartItem]
    order_date: str
    order_comment: Optional[str] = Field(default=None, max_length=1000)
    request_free_delivery: bool

    @field_validator('order_date')
    @classmethod
    def validate_order_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("order_date must be in format YYYY-MM-DD")
        return value

    @field_validator('cart')
    @classmethod
    def validate_cart_not_empty(cls, value):
        if not value:
            raise ValueError("cart must not be empty")
        return value
    

class OrderRating(BaseModel):
    order_id: int = Field(..., gt=0)
    business_role: Literal[SUPPLIER_ROLE, CUSTOMER_ROLE]
    order_rate: int = Field(..., ge=1, le=5)
    order_review: Optional[str] = Field(default=None, max_length=1000)
    items_rate: Dict[Union[int, str], int]
    items_review: Dict[Union[int, str], Optional[str]]

    

