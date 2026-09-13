from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.user import User, UserRole


def get_accessible_ticket(ticket_id: int, current_user: User, db: Session) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.role == UserRole.USER and ticket.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ticket
