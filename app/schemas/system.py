from pydantic import BaseModel, ConfigDict


class APIInfo(BaseModel):
    name: str
    version: str
    docs: str
    redoc: str
    openapi: str
    health: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "SecureDesk API",
                "version": "1.0.0",
                "docs": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
                "health": "/health",
            }
        }
    )


class HealthResponse(BaseModel):
    status: str

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})
