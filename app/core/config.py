from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SecureDesk"
    debug: bool = False
    database_url: str = "postgresql+psycopg://securedesk:securedesk@localhost:5432/securedesk"
    jwt_secret: str = "development-only-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    attachments_dir: str = "uploads/attachments"
    attachment_max_bytes: int = 5 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
