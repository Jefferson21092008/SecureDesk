from datetime import datetime

from pydantic import BaseModel


class TicketHistoryRead(BaseModel):
    id: int
    ticket_id: int
    actor_id: int
    action: str
    field: str | None
    old_value: str | None
    new_value: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
