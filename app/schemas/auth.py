from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.validation import validate_password_strength
from app.models.user import UserRole


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @model_validator(mode="after")
    def enforce_password_policy(self) -> "UserCreate":
        validate_password_strength(self.password, email=str(self.email))
        return self


class UserRead(BaseModel):
    id: int
    email: EmailStr
    role: UserRole

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
