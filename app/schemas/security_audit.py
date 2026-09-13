from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SecurityAuditRead(BaseModel):
    id: int
    event_type: str
    actor_id: int | None
    method: str
    path: str
    status_code: int | None
    ip_address: str
    user_agent: str | None
    details: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityAuditPage(BaseModel):
    items: list[SecurityAuditRead]
    page: int
    page_size: int
    total: int
    pages: int
