from datetime import datetime

from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class CommentRead(BaseModel):
    id: int
    content: str
    ticket_id: int
    author_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
