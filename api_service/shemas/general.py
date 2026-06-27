from pydantic import BaseModel, Field
from typing import List, Annotated


PositiveInt = Annotated[int, Field(ge=1)]

class ArrayOfIds(BaseModel):
    list_of_ids: List[PositiveInt]