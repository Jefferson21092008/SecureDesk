from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.ticket import Ticket, TicketStatus
from app.models.ticket_history import TicketHistory
from app.models.user import User, UserRole
from app.schemas.ticket import TicketRead

router = APIRouter()


def _get_ticket(ticket_id: int, db: Session) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def _require_staff_role(current_user: User) -> None:
    if current_user.role == UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users cannot close or reopen tickets",
        )


def _require_lifecycle_permission(ticket: Ticket, current_user: User) -> None:
    if current_user.role == UserRole.AGENT and ticket.assigned_agent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents can only close or reopen tickets assigned to themselves",
        )


@router.post("/{ticket_id}/close", response_model=TicketRead)
def close_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Ticket:
    _require_staff_role(current_user)
    ticket = _get_ticket(ticket_id, db)
    _require_lifecycle_permission(ticket, current_user)

    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is already closed",
        )

    old_status = ticket.status
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.now(timezone.utc)

    db.add(
        TicketHistory(
            ticket_id=ticket.id,
            actor_id=current_user.id,
            action="CLOSED",
            field="status",
            old_value=old_status.value,
            new_value=TicketStatus.CLOSED.value,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/reopen", response_model=TicketRead)
def reopen_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Ticket:
    _require_staff_role(current_user)
    ticket = _get_ticket(ticket_id, db)
    _require_lifecycle_permission(ticket, current_user)

    if ticket.status != TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only closed tickets can be reopened",
        )

    ticket.status = TicketStatus.OPEN
    ticket.closed_at = None

    db.add(
        TicketHistory(
            ticket_id=ticket.id,
            actor_id=current_user.id,
            action="REOPENED",
            field="status",
            old_value=TicketStatus.CLOSED.value,
            new_value=TicketStatus.OPEN.value,
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket
