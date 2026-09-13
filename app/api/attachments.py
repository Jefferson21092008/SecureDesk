from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.ticket_access import get_accessible_ticket
from app.db import get_db
from app.models.attachment import Attachment
from app.models.ticket_history import TicketHistory
from app.models.user import User, UserRole
from app.schemas.attachment import AttachmentRead
from app.services.attachment_storage import attachment_path, delete_stored_file, store_upload

router = APIRouter()


def _get_attachment(ticket_id: int, attachment_id: int, db: Session) -> Attachment:
    attachment = db.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.ticket_id == ticket_id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


@router.post(
    "/{ticket_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Attachment:
    ticket = get_accessible_ticket(ticket_id, current_user, db)
    original_filename, storage_key, content_type, size_bytes = store_upload(file)

    attachment = Attachment(
        ticket_id=ticket.id,
        uploader_id=current_user.id,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
    )

    try:
        db.add(attachment)
        db.flush()
        db.add(
            TicketHistory(
                ticket_id=ticket.id,
                actor_id=current_user.id,
                action="ATTACHMENT_ADDED",
                field="attachment_id",
                new_value=str(attachment.id),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(storage_key)
        raise

    db.refresh(attachment)
    return attachment


@router.get("/{ticket_id}/attachments", response_model=list[AttachmentRead])
def list_attachments(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Attachment]:
    ticket = get_accessible_ticket(ticket_id, current_user, db)
    return list(
        db.scalars(
            select(Attachment)
            .where(Attachment.ticket_id == ticket.id)
            .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        )
    )


@router.get("/{ticket_id}/attachments/{attachment_id}")
def download_attachment(
    ticket_id: int,
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    get_accessible_ticket(ticket_id, current_user, db)
    attachment = _get_attachment(ticket_id, attachment_id, db)
    try:
        path = attachment_path(attachment.storage_key)
    except ValueError:
        raise HTTPException(status_code=404, detail="Attachment file not found") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found")

    return FileResponse(
        path=Path(path),
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )


@router.delete(
    "/{ticket_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    ticket_id: int,
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ticket = get_accessible_ticket(ticket_id, current_user, db)
    attachment = _get_attachment(ticket_id, attachment_id, db)

    if current_user.role != UserRole.ADMIN and attachment.uploader_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the uploader or an admin can delete this attachment",
        )

    storage_key = attachment.storage_key
    db.add(
        TicketHistory(
            ticket_id=ticket.id,
            actor_id=current_user.id,
            action="ATTACHMENT_DELETED",
            field="attachment_id",
            old_value=str(attachment.id),
        )
    )
    db.delete(attachment)
    db.commit()
    delete_stored_file(storage_key)
