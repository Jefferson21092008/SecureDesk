from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.validation import reject_unsafe_text


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return reject_unsafe_text(value, field_name="Comment", allow_newlines=True)


class CommentRead(BaseModel):
    id: int
    content: str
    ticket_id: int
    author_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
