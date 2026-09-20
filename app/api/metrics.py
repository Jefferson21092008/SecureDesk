from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.category import Category
from app.models.department import Department
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.metrics import (
    AgentMetricItem,
    CategoryMetricItem,
    DepartmentMetricItem,
    MetricsScope,
    SLAClosedMetrics,
    SLAStatusCounts,
    TicketBreakdownMetrics,
    TicketMetricsOverview,
    TicketPriorityCounts,
    TicketSLAMetrics,
    TicketStatusCounts,
)

router = APIRouter()


def _apply_ticket_scope(query, current_user: User):
    if current_user.role == UserRole.USER:
        return query.where(Ticket.owner_id == current_user.id), MetricsScope.OWN
    return query, MetricsScope.GLOBAL


def _resolution_seconds_expression(db: Session):
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        return (func.julianday(Ticket.closed_at) - func.julianday(Ticket.created_at)) * 86400.0
    return func.extract("epoch", Ticket.closed_at - Ticket.created_at)


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

    query, scope = _apply_ticket_scope(query, current_user)
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


@router.get("/sla", response_model=TicketSLAMetrics)
def ticket_sla_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketSLAMetrics:
    now = datetime.now(timezone.utc)

    met = (Ticket.closed_at.is_not(None)) & (Ticket.closed_at <= Ticket.sla_due_at)
    closed_breached = (Ticket.closed_at.is_not(None)) & (Ticket.closed_at > Ticket.sla_due_at)
    open_breached = (Ticket.closed_at.is_(None)) & (Ticket.sla_due_at < now)
    breached = or_(closed_breached, open_breached)
    on_track = (Ticket.closed_at.is_(None)) & (Ticket.sla_due_at >= now)
    closed = Ticket.closed_at.is_not(None)

    resolution_seconds = _resolution_seconds_expression(db)

    query = select(
        func.count(Ticket.id).label("total"),
        func.sum(case((on_track, 1), else_=0)).label("on_track"),
        func.sum(case((met, 1), else_=0)).label("met"),
        func.sum(case((breached, 1), else_=0)).label("breached"),
        func.sum(case((closed, 1), else_=0)).label("closed_total"),
        func.sum(case((closed_breached, 1), else_=0)).label("closed_breached"),
        func.avg(case((closed, resolution_seconds))).label("avg_resolution_seconds"),
    )

    query, scope = _apply_ticket_scope(query, current_user)
    counts = db.execute(query).mappings().one()

    total = int(counts["total"] or 0)
    met_count = int(counts["met"] or 0)
    closed_total = int(counts["closed_total"] or 0)
    closed_breached_count = int(counts["closed_breached"] or 0)

    compliance_rate = None
    if closed_total:
        compliance_rate = round((met_count / closed_total) * 100, 2)

    average_resolution_hours = None
    if counts["avg_resolution_seconds"] is not None:
        average_resolution_hours = round(float(counts["avg_resolution_seconds"]) / 3600, 2)

    return TicketSLAMetrics(
        scope=scope,
        total=total,
        by_sla_status=SLAStatusCounts(
            on_track=int(counts["on_track"] or 0),
            met=met_count,
            breached=int(counts["breached"] or 0),
        ),
        closed=SLAClosedMetrics(
            total=closed_total,
            met=met_count,
            breached=closed_breached_count,
            compliance_rate_percent=compliance_rate,
        ),
        average_resolution_hours=average_resolution_hours,
    )


@router.get("/breakdown", response_model=TicketBreakdownMetrics)
def ticket_breakdown_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketBreakdownMetrics:
    department_query = (
        select(
            Ticket.department_id.label("department_id"),
            Department.name.label("department_name"),
            func.count(Ticket.id).label("total"),
        )
        .outerjoin(Department, Ticket.department_id == Department.id)
        .group_by(Ticket.department_id, Department.name)
        .order_by(
            Department.name.is_(None),
            Department.name.asc(),
            Ticket.department_id.asc(),
        )
    )
    department_query, scope = _apply_ticket_scope(department_query, current_user)

    category_query = (
        select(
            Ticket.category_id.label("category_id"),
            Category.name.label("category_name"),
            func.count(Ticket.id).label("total"),
        )
        .outerjoin(Category, Ticket.category_id == Category.id)
        .group_by(Ticket.category_id, Category.name)
        .order_by(
            Category.name.is_(None),
            Category.name.asc(),
            Ticket.category_id.asc(),
        )
    )
    category_query, _ = _apply_ticket_scope(category_query, current_user)

    agent_query = (
        select(
            Ticket.assigned_agent_id.label("agent_id"),
            User.email.label("agent_email"),
            func.count(Ticket.id).label("total"),
        )
        .outerjoin(User, Ticket.assigned_agent_id == User.id)
        .group_by(Ticket.assigned_agent_id, User.email)
        .order_by(
            User.email.is_(None),
            User.email.asc(),
            Ticket.assigned_agent_id.asc(),
        )
    )
    agent_query, _ = _apply_ticket_scope(agent_query, current_user)

    department_rows = db.execute(department_query).mappings().all()
    category_rows = db.execute(category_query).mappings().all()
    agent_rows = db.execute(agent_query).mappings().all()

    return TicketBreakdownMetrics(
        scope=scope,
        by_department=[
            DepartmentMetricItem(
                department_id=row["department_id"],
                department_name=row["department_name"],
                total=int(row["total"] or 0),
            )
            for row in department_rows
        ],
        by_category=[
            CategoryMetricItem(
                category_id=row["category_id"],
                category_name=row["category_name"],
                total=int(row["total"] or 0),
            )
            for row in category_rows
        ],
        by_agent=[
            AgentMetricItem(
                agent_id=row["agent_id"],
                agent_email=row["agent_email"],
                total=int(row["total"] or 0),
            )
            for row in agent_rows
        ],
    )
