from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.category import Category
from app.models.department import Department
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.services.sla import calculate_sla_due_at


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed_user(db: Session, email: str, role: UserRole = UserRole.USER) -> tuple[User, str]:
    user = User(email=email, password_hash="unused-test-hash", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, create_access_token(str(user.id))


def seed_ticket(
    db: Session,
    owner: User,
    *,
    title: str,
    created_at: datetime,
    status: TicketStatus = TicketStatus.OPEN,
    priority: TicketPriority = TicketPriority.MEDIUM,
    department: Department | None = None,
    category: Category | None = None,
    agent: User | None = None,
    closed_at: datetime | None = None,
) -> Ticket:
    ticket = Ticket(
        title=title,
        description="Metrics period test ticket",
        status=status,
        priority=priority,
        owner_id=owner.id,
        created_at=created_at,
        closed_at=closed_at,
        sla_due_at=calculate_sla_due_at(created_at, priority),
        department_id=department.id if department else None,
        category_id=category.id if category else None,
        assigned_agent_id=agent.id if agent else None,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_metrics_reject_inverted_period(client: TestClient, db: Session) -> None:
    _, token = seed_user(db, "period-inverted@example.com")

    response = client.get(
        "/metrics/overview?date_from=2026-02-10&date_to=2026-02-01",
        headers=auth(token),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "date_from must be before or equal to date_to"


def test_metrics_reject_invalid_date_format(client: TestClient, db: Session) -> None:
    _, token = seed_user(db, "period-invalid@example.com")

    response = client.get("/metrics/overview?date_from=10-02-2026", headers=auth(token))

    assert response.status_code == 422


def test_overview_period_is_inclusive_for_both_calendar_days(
    client: TestClient,
    db: Session,
) -> None:
    owner, token = seed_user(db, "period-overview@example.com")

    seed_ticket(
        db,
        owner,
        title="Before",
        created_at=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
    )
    seed_ticket(
        db,
        owner,
        title="Start boundary",
        created_at=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
        priority=TicketPriority.LOW,
    )
    seed_ticket(
        db,
        owner,
        title="End boundary",
        created_at=datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=timezone.utc),
        status=TicketStatus.CLOSED,
        priority=TicketPriority.HIGH,
        closed_at=datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc),
    )
    seed_ticket(
        db,
        owner,
        title="After",
        created_at=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    )

    response = client.get(
        "/metrics/overview?date_from=2026-02-01&date_to=2026-02-28",
        headers=auth(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["by_status"] == {"open": 1, "in_progress": 0, "closed": 1}
    assert payload["by_priority"] == {"low": 1, "medium": 0, "high": 1}


def test_overview_supports_date_from_without_date_to(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "period-from@example.com")
    seed_ticket(
        db,
        owner,
        title="Old",
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    seed_ticket(
        db,
        owner,
        title="New",
        created_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )

    payload = client.get(
        "/metrics/overview?date_from=2026-04-01",
        headers=auth(token),
    ).json()

    assert payload["total"] == 1


def test_overview_supports_date_to_without_date_from(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "period-to@example.com")
    seed_ticket(
        db,
        owner,
        title="Old",
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    seed_ticket(
        db,
        owner,
        title="New",
        created_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )

    payload = client.get(
        "/metrics/overview?date_to=2026-04-01",
        headers=auth(token),
    ).json()

    assert payload["total"] == 1


def test_period_filter_and_user_scope_are_combined(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "period-owner@example.com")
    other, _ = seed_user(db, "period-other@example.com")
    in_period = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)

    seed_ticket(db, owner, title="Own in period", created_at=in_period)
    seed_ticket(db, other, title="Foreign in period", created_at=in_period)
    seed_ticket(
        db,
        owner,
        title="Own outside period",
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )

    payload = client.get(
        "/metrics/overview?date_from=2026-06-01&date_to=2026-06-30",
        headers=auth(token),
    ).json()

    assert payload["scope"] == "OWN"
    assert payload["total"] == 1


def test_sla_metrics_period_is_based_on_ticket_creation_date(
    client: TestClient,
    db: Session,
) -> None:
    owner, token = seed_user(db, "period-sla@example.com")

    included_created = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
    seed_ticket(
        db,
        owner,
        title="Created in March and closed in April",
        created_at=included_created,
        status=TicketStatus.CLOSED,
        closed_at=included_created + timedelta(hours=2),
    )
    excluded_created = datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)
    seed_ticket(
        db,
        owner,
        title="Created in April",
        created_at=excluded_created,
        status=TicketStatus.CLOSED,
        closed_at=excluded_created + timedelta(hours=2),
    )

    payload = client.get(
        "/metrics/sla?date_from=2026-03-01&date_to=2026-03-31",
        headers=auth(token),
    ).json()

    assert payload["total"] == 1
    assert payload["closed"]["total"] == 1
    assert payload["average_resolution_hours"] == 2.0


def test_breakdown_metrics_respect_period(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "period-breakdown@example.com")
    department = Department(name="Period Support")
    category = Category(name="Period Access")
    agent = User(
        email="period-agent@example.com",
        password_hash="unused-test-hash",
        role=UserRole.AGENT,
    )
    db.add_all([department, category, agent])
    db.commit()
    db.refresh(department)
    db.refresh(category)
    db.refresh(agent)

    seed_ticket(
        db,
        owner,
        title="Included grouped",
        created_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        department=department,
        category=category,
        agent=agent,
    )
    seed_ticket(
        db,
        owner,
        title="Excluded ungrouped",
        created_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )

    payload = client.get(
        "/metrics/breakdown?date_from=2026-08-01&date_to=2026-08-31",
        headers=auth(token),
    ).json()

    assert payload["by_department"] == [
        {
            "department_id": department.id,
            "department_name": "Period Support",
            "total": 1,
        }
    ]
    assert payload["by_category"] == [
        {"category_id": category.id, "category_name": "Period Access", "total": 1}
    ]
    assert payload["by_agent"] == [
        {"agent_id": agent.id, "agent_email": agent.email, "total": 1}
    ]


def test_staff_period_metrics_remain_global(client: TestClient, db: Session) -> None:
    first, _ = seed_user(db, "period-global-first@example.com")
    second, _ = seed_user(db, "period-global-second@example.com")
    _, admin_token = seed_user(db, "period-global-admin@example.com", UserRole.ADMIN)
    created_at = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)

    seed_ticket(db, first, title="First", created_at=created_at)
    seed_ticket(db, second, title="Second", created_at=created_at)

    payload = client.get(
        "/metrics/overview?date_from=2026-11-01&date_to=2026-11-30",
        headers=auth(admin_token),
    ).json()

    assert payload["scope"] == "GLOBAL"
    assert payload["total"] == 2
