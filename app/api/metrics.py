from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.metrics import (
    MetricsScope,
    TicketMetricsOverview,
    TicketPriorityCounts,
    TicketStatusCounts,
)

router = APIRouter()


@router.get("/overview", response_model=TicketMetricsOverview)
def ticket_metrics_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketMetricsOverview:
    query = select(
        func.count(Ticket.id).label("total"),
        func.sum(case((Ticket.status == TicketStatus.OPEN, 1), else_=0)).label("status_open"),
        func.sum(case((Ticket.status == TicketStatus.IN_PROGRESS, 1), else_=0)).label(
            "status_in_progress"
        ),
        func.sum(case((Ticket.status == TicketStatus.CLOSED, 1), else_=0)).label("status_closed"),
        func.sum(case((Ticket.priority == TicketPriority.LOW, 1), else_=0)).label("priority_low"),
        func.sum(case((Ticket.priority == TicketPriority.MEDIUM, 1), else_=0)).label(
            "priority_medium"
        ),
        func.sum(case((Ticket.priority == TicketPriority.HIGH, 1), else_=0)).label("priority_high"),
    )

    scope = MetricsScope.GLOBAL
    if current_user.role == UserRole.USER:
        query = query.where(Ticket.owner_id == current_user.id)
        scope = MetricsScope.OWN

    counts = db.execute(query).mappings().one()

    return TicketMetricsOverview(
        scope=scope,
        total=int(counts["total"] or 0),
        by_status=TicketStatusCounts(
            open=int(counts["status_open"] or 0),
            in_progress=int(counts["status_in_progress"] or 0),
            closed=int(counts["status_closed"] or 0),
        ),
        by_priority=TicketPriorityCounts(
            low=int(counts["priority_low"] or 0),
            medium=int(counts["priority_medium"] or 0),
            high=int(counts["priority_high"] or 0),
        ),
    )
