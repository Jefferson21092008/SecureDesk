from pydantic import BaseModel, ConfigDict, Field


class TicketAssignmentUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"agent_id": 5}},
    )

    agent_id: int | None = Field(default=None, ge=1)
