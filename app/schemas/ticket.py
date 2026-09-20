from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import reject_unsafe_text
from app.models.ticket import TicketPriority, TicketStatus
from app.services.sla import SLAStatus


class TicketSortBy(str, Enum):
    CREATED_AT = "created_at"
    ID = "id"
    TITLE = "title"
    SLA_DUE_AT = "sla_due_at"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class TicketCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "title": "VPN connection unavailable",
                "description": "The corporate VPN fails during connection after authentication.",
                "priority": "HIGH",
                "category_id": 2,
                "department_id": 1,
            }
        },
    )

    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=5000)
    priority: TicketPriority = TicketPriority.MEDIUM
    category_id: int | None = Field(default=None, ge=1)
    department_id: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = reject_unsafe_text(value, field_name="Title")
        if len(value) < 3:
            raise ValueError("Title must contain at least 3 characters")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        value = reject_unsafe_text(value, field_name="Description", allow_newlines=True)
        if len(value) < 3:
            raise ValueError("Description must contain at least 3 characters")
        return value


class TicketRead(BaseModel):
    id: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    owner_id: int
    category_id: int | None
    department_id: int | None
    assigned_agent_id: int | None
    closed_at: datetime | None
    created_at: datetime
    sla_due_at: datetime
    sla_target_hours: int
    sla_status: SLAStatus

    model_config = {"from_attributes": True}


class TicketPage(BaseModel):
    items: list[TicketRead]
    page: int
    page_size: int
    total: int
    pages: int


class TicketUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "priority": "HIGH",
                "department_id": 1,
            }
        },
    )

    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, min_length=3, max_length=5000)
    priority: TicketPriority | None = None
    status: TicketStatus | None = None
    category_id: int | None = Field(default=None, ge=1)
    department_id: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = reject_unsafe_text(value, field_name="Title")
        if len(value) < 3:
            raise ValueError("Title must contain at least 3 characters")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = reject_unsafe_text(value, field_name="Description", allow_newlines=True)
        if len(value) < 3:
            raise ValueError("Description must contain at least 3 characters")
        return value

    @model_validator(mode="after")
    def validate_update(self) -> "TicketUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        null_fields = [
            field
            for field in self.model_fields_set
            if field not in {"category_id", "department_id"} and getattr(self, field) is None
        ]
        if null_fields:
            raise ValueError(f"Fields cannot be null: {', '.join(sorted(null_fields))}")
        return self
