from pydantic import BaseModel, Field
from typing import Literal, List, Annotated


from constants.messages import MESSAGE, NOTIFICATION, MESSAGE_LENGTH_LIMIT


PositiveInt = Annotated[int, Field(ge=1)]

class MarkChatReadedData(BaseModel):
    chat_type: Literal[MESSAGE, NOTIFICATION]
    order_id: int = Field(..., ge=0)
    unread_ids: List[PositiveInt]
    read_ids: List[PositiveInt]

class CreateNewMessageData(BaseModel):
    order_id: int = Field(..., ge=1)
    sender_user: int = Field(..., ge=1)
    sender_business: int = Field(..., ge=1)
    receiver_business: int = Field(..., ge=1)
    text: str = Field(..., min_length=1, max_length=MESSAGE_LENGTH_LIMIT)
    