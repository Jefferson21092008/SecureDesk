from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.ticket import TicketPriority, TicketStatus


class TicketSortBy(str, Enum):
    CREATED_AT = "created_at"
    ID = "id"
    TITLE = "title"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=5000)
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketRead(BaseModel):
    id: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    owner_id: int
    assigned_agent_id: int | None
    closed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketPage(BaseModel):
    items: list[TicketRead]
    page: int
    page_size: int
    total: int
    pages: int


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, min_length=3, max_length=5000)
    priority: TicketPriority | None = None
    status: TicketStatus | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "TicketUpdate":
        null_fields = [field for field in self.model_fields_set if getattr(self, field) is None]
        if null_fields:
            raise ValueError(f"Fields cannot be null: {', '.join(sorted(null_fields))}")
        return self
