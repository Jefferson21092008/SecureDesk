from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.attachment import Attachment
from app.models.category import Category
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.ticket_history import TicketHistory
from app.models.user import User, UserRole
from app.schemas.ticket import (
    SortOrder,
    TicketCreate,
    TicketPage,
    TicketRead,
    TicketSortBy,
    TicketUpdate,
)
from app.services.attachment_storage import delete_stored_file
from app.services.sla import SLAStatus, calculate_sla_due_at

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
    if data.category_id is not None and db.get(Category, data.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")

    created_at = datetime.now(timezone.utc)
    ticket = Ticket(
        **data.model_dump(),
        owner_id=current_user.id,
        created_at=created_at,
        sla_due_at=calculate_sla_due_at(created_at, data.priority),
    )
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


@router.get("", response_model=TicketPage)
def list_tickets(
    ticket_status: TicketStatus | None = Query(default=None, alias="status"),
    priority: TicketPriority | None = Query(default=None),
    category_id: int | None = Query(default=None, ge=1),
    sla_status: SLAStatus | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: TicketSortBy = Query(default=TicketSortBy.CREATED_AT),
    sort_order: SortOrder = Query(default=SortOrder.DESC),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketPage:
    query = select(Ticket)

    if current_user.role == UserRole.USER:
        query = query.where(Ticket.owner_id == current_user.id)

    if ticket_status is not None:
        query = query.where(Ticket.status == ticket_status)

    if priority is not None:
        query = query.where(Ticket.priority == priority)

    if category_id is not None:
        query = query.where(Ticket.category_id == category_id)

    if sla_status is not None:
        now = datetime.now(timezone.utc)
        breached = or_(
            and_(Ticket.closed_at.is_not(None), Ticket.closed_at > Ticket.sla_due_at),
            and_(Ticket.closed_at.is_(None), Ticket.sla_due_at < now),
        )
        met = and_(Ticket.closed_at.is_not(None), Ticket.closed_at <= Ticket.sla_due_at)
        on_track = and_(Ticket.closed_at.is_(None), Ticket.sla_due_at >= now)
        sla_filter = {
            SLAStatus.BREACHED: breached,
            SLAStatus.MET: met,
            SLAStatus.ON_TRACK: on_track,
        }[sla_status]
        query = query.where(sla_filter)

    if search is not None:
        term = search.strip()
        if term:
            pattern = f"%{term}%"
            query = query.where(
                or_(
                    Ticket.title.ilike(pattern),
                    Ticket.description.ilike(pattern),
                )
            )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    sort_column = {
        TicketSortBy.CREATED_AT: Ticket.created_at,
        TicketSortBy.ID: Ticket.id,
        TicketSortBy.TITLE: Ticket.title,
        TicketSortBy.SLA_DUE_AT: Ticket.sla_due_at,
    }[sort_by]

    order_expression = sort_column.asc() if sort_order == SortOrder.ASC else sort_column.desc()
    id_tiebreaker = Ticket.id.asc() if sort_order == SortOrder.ASC else Ticket.id.desc()

    query = query.order_by(order_expression)
    if sort_by != TicketSortBy.ID:
        query = query.order_by(id_tiebreaker)

    offset = (page - 1) * page_size
    items = list(db.scalars(query.offset(offset).limit(page_size)))
    pages = (total + page_size - 1) // page_size if total else 0

    return TicketPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


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

    if data.category_id is not None and db.get(Category, data.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")

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

        if field == "priority":
            old_due_at = ticket.sla_due_at
            new_due_at = calculate_sla_due_at(ticket.created_at, value)
            if old_due_at != new_due_at:
                ticket.sla_due_at = new_due_at
                db.add(
                    TicketHistory(
                        ticket_id=ticket.id,
                        actor_id=current_user.id,
                        action="SLA_RECALCULATED",
                        field="sla_due_at",
                        old_value=history_value(old_due_at),
                        new_value=history_value(new_due_at),
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

    storage_keys = list(
        db.scalars(select(Attachment.storage_key).where(Attachment.ticket_id == ticket.id))
    )
    db.delete(ticket)
    db.commit()
    for storage_key in storage_keys:
        delete_stored_file(storage_key)
