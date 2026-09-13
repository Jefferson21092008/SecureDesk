from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.ticket_access import get_accessible_ticket
from app.db import get_db
from app.models.ticket_history import TicketHistory
from app.models.user import User
from app.schemas.ticket_history import TicketHistoryRead

router = APIRouter()


@router.get(
    "/{ticket_id}/history",
    response_model=list[TicketHistoryRead],
)
def list_ticket_history(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TicketHistory]:
    get_accessible_ticket(ticket_id, current_user, db)

    return list(
        db.scalars(
            select(TicketHistory)
            .where(TicketHistory.ticket_id == ticket_id)
            .order_by(TicketHistory.id.asc())
        )
    )
