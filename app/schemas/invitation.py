from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: Literal[UserRole.USER, UserRole.AGENT] = UserRole.USER

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class InvitationRead(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class InvitationCreated(InvitationRead):
    # Returned exactly once; only the SHA-256 digest is persisted.
    token: str


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=30, max_length=256)
    password: str = Field(min_length=12, max_length=128)
