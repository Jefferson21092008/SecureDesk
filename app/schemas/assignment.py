from pydantic import BaseModel


class TicketAssignmentUpdate(BaseModel):
    agent_id: int | None
