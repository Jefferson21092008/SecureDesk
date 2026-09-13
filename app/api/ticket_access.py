from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.user import User, UserRole


def can_access_ticket(ticket: Ticket, current_user: User) -> bool:
    """Return whether the current user is allowed to see the ticket object."""
    if current_user.role in {UserRole.AGENT, UserRole.ADMIN}:
        return True
    return ticket.owner_id == current_user.id


def get_accessible_ticket(ticket_id: int, current_user: User, db: Session) -> Ticket:
    """Load a ticket without revealing whether an inaccessible object exists.

    Returning the same 404 response for missing and unauthorized ticket IDs makes
    direct-object-reference probing less useful to regular users.
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or not can_access_ticket(ticket, current_user):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
