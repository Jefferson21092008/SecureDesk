from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.ticket import Ticket, TicketStatus
from app.models.ticket_history import TicketHistory
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketRead, TicketUpdate

router = APIRouter()


def history_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Ticket:
    ticket = Ticket(**data.model_dump(), owner_id=current_user.id)
    db.add(ticket)
    db.flush()

    db.add(
        TicketHistory(
            ticket_id=ticket.id,
            actor_id=current_user.id,
            action="CREATED",
        )
    )

    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("", response_model=list[TicketRead])
def list_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Ticket]:
    if current_user.role in {UserRole.AGENT, UserRole.ADMIN}:
        return list(db.scalars(select(Ticket).order_by(Ticket.id.desc())))
    return list(db.scalars(
        select(Ticket)
        .where(Ticket.owner_id == current_user.id)
        .order_by(Ticket.id.desc())
    ))


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.role == UserRole.USER and ticket.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.role == UserRole.USER and ticket.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if current_user.role == UserRole.USER and data.status is not None:
        raise HTTPException(status_code=403, detail="Users cannot change ticket status")

    if data.status == TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use the close endpoint to close a ticket",
        )

    if ticket.status == TicketStatus.CLOSED and data.status is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use the reopen endpoint before changing a closed ticket status",
        )

    for field, value in data.model_dump(exclude_unset=True).items():
        old_value = getattr(ticket, field)
        if old_value == value:
            continue

        setattr(ticket, field, value)
        db.add(
            TicketHistory(
                ticket_id=ticket.id,
                actor_id=current_user.id,
                action="UPDATED",
                field=field,
                old_value=history_value(old_value),
                new_value=history_value(value),
            )
        )

    db.commit()
    db.refresh(ticket)
    return ticket


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if current_user.role not in {UserRole.AGENT, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Only agents and admins can delete tickets")

    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    db.delete(ticket)
    db.commit()
