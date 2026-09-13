from datetime import datetime

from pydantic import BaseModel


class AttachmentRead(BaseModel):
    id: int
    ticket_id: int
    uploader_id: int | None
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}
