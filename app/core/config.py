from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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
    attachment_storage_backend: Literal["local", "r2", "s3"] = "local"
    r2_endpoint_url: str = ""
    r2_bucket_name: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: SecretStr = SecretStr("")
    s3_endpoint_url: str = ""
    s3_bucket_name: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_region: str = "sa-east-1"
    attachment_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    trust_proxy_headers: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Managed Postgres providers commonly expose postgresql:// URLs.
        # SQLAlchemy must be told explicitly to use the installed psycopg v3 driver.
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.attachment_storage_backend == "r2":
            endpoint = urlsplit(self.r2_endpoint_url)
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.path not in {"", "/"}
                or endpoint.query
                or endpoint.fragment
            ):
                raise ValueError("R2_ENDPOINT_URL must be an HTTPS S3 API endpoint")
            if not all((self.r2_bucket_name, self.r2_access_key_id, self.r2_secret_access_key.get_secret_value())):
                raise ValueError("R2 bucket and API credentials are required when ATTACHMENT_STORAGE_BACKEND=r2")
        if self.attachment_storage_backend == "s3":
            endpoint = urlsplit(self.s3_endpoint_url)
            host = endpoint.hostname or ""
            # Only the private Supabase S3 API, not a public storage URL.
            if (
                endpoint.scheme != "https"
                or not (host.endswith(".supabase.co") and host != ".supabase.co")
                or endpoint.path != "/storage/v1/s3"
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
                or endpoint.port not in (None, 443)
            ):
                raise ValueError("S3_ENDPOINT_URL must be the Supabase HTTPS S3 API endpoint")
            if not all(
                (self.s3_bucket_name, self.s3_access_key_id, self.s3_secret_access_key.get_secret_value(), self.s3_region)
            ):
                raise ValueError("S3 bucket, region and credentials required when ATTACHMENT_STORAGE_BACKEND=s3")
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
