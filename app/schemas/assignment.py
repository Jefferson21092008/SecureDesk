from pydantic import BaseModel, ConfigDict, Field


class TicketAssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: int | None = Field(default=None, ge=1)
