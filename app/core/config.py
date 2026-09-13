from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEVELOPMENT_JWT_SECRET = "development-only-secret-change-me-32-bytes"


class Settings(BaseSettings):
    app_name: str = "SecureDesk"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://securedesk:securedesk@localhost:5432/securedesk"
    jwt_secret: str = Field(default=DEFAULT_DEVELOPMENT_JWT_SECRET, min_length=32, max_length=512)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = Field(default="securedesk", min_length=1, max_length=100)
    jwt_audience: str = Field(default="securedesk-api", min_length=1, max_length=100)
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    api_rate_limit_requests: int = Field(default=120, ge=1, le=10000)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    login_rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    register_rate_limit_requests: int = Field(default=10, ge=1, le=1000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    login_failure_limit: int = Field(default=5, ge=1, le=100)
    login_failure_window_seconds: int = Field(default=300, ge=1, le=86400)
    attachments_dir: str = "uploads/attachments"
    attachment_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.app_env != "production":
            return self

        if self.debug:
            raise ValueError("DEBUG must be disabled in production")
        if self.jwt_secret == DEFAULT_DEVELOPMENT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be replaced in production")
        if "securedesk:securedesk@" in self.database_url:
            raise ValueError("Default database credentials cannot be used in production")
        return self


settings = Settings()
