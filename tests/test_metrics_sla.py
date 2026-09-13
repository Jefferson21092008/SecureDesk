from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole


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
    sla_due_at: datetime,
    closed_at: datetime | None = None,
) -> Ticket:
    ticket = Ticket(
        title=title,
        description="SLA metrics test ticket",
        status=TicketStatus.CLOSED if closed_at is not None else TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        owner_id=owner.id,
        created_at=created_at,
        closed_at=closed_at,
        sla_due_at=sla_due_at,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_sla_metrics_requires_authentication(client: TestClient) -> None:
    response = client.get("/metrics/sla")
    assert response.status_code == 401


def test_sla_metrics_returns_stable_empty_contract(client: TestClient, db: Session) -> None:
    _, token = seed_user(db, "sla-metrics-empty@example.com")

    response = client.get("/metrics/sla", headers=auth(token))

    assert response.status_code == 200
    assert response.json() == {
        "scope": "OWN",
        "total": 0,
        "by_sla_status": {"on_track": 0, "met": 0, "breached": 0},
        "closed": {
            "total": 0,
            "met": 0,
            "breached": 0,
            "compliance_rate_percent": None,
        },
        "average_resolution_hours": None,
    }


def test_sla_metrics_classifies_status_and_calculates_closed_kpis(
    client: TestClient,
    db: Session,
) -> None:
    owner, token = seed_user(db, "sla-metrics-kpi@example.com")
    now = datetime.now(timezone.utc)

    seed_ticket(
        db,
        owner,
        title="Open on track",
        created_at=now - timedelta(hours=1),
        sla_due_at=now + timedelta(hours=3),
    )
    seed_ticket(
        db,
        owner,
        title="Open breached",
        created_at=now - timedelta(hours=10),
        sla_due_at=now - timedelta(hours=2),
    )
    seed_ticket(
        db,
        owner,
        title="Closed met",
        created_at=now - timedelta(hours=8),
        sla_due_at=now - timedelta(hours=2),
        closed_at=now - timedelta(hours=4),
    )
    seed_ticket(
        db,
        owner,
        title="Closed breached",
        created_at=now - timedelta(hours=10),
        sla_due_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=2),
    )

    response = client.get("/metrics/sla", headers=auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "OWN"
    assert payload["total"] == 4
    assert payload["by_sla_status"] == {"on_track": 1, "met": 1, "breached": 2}
    assert payload["closed"] == {
        "total": 2,
        "met": 1,
        "breached": 1,
        "compliance_rate_percent": 50.0,
    }
    assert payload["average_resolution_hours"] == 6.0


def test_open_breach_does_not_reduce_closed_sla_compliance(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "sla-metrics-open-breach@example.com")
    now = datetime.now(timezone.utc)

    seed_ticket(
        db,
        owner,
        title="Met closed ticket",
        created_at=now - timedelta(hours=4),
        sla_due_at=now - timedelta(hours=1),
        closed_at=now - timedelta(hours=2),
    )
    seed_ticket(
        db,
        owner,
        title="Still open and overdue",
        created_at=now - timedelta(hours=10),
        sla_due_at=now - timedelta(hours=1),
    )

    payload = client.get("/metrics/sla", headers=auth(token)).json()

    assert payload["by_sla_status"]["breached"] == 1
    assert payload["closed"]["compliance_rate_percent"] == 100.0


def test_user_sla_metrics_only_include_own_tickets(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "sla-metrics-owner@example.com")
    other, _ = seed_user(db, "sla-metrics-other@example.com")
    now = datetime.now(timezone.utc)

    seed_ticket(
        db,
        owner,
        title="Own met",
        created_at=now - timedelta(hours=3),
        sla_due_at=now - timedelta(hours=1),
        closed_at=now - timedelta(hours=2),
    )
    seed_ticket(
        db,
        other,
        title="Foreign breach",
        created_at=now - timedelta(hours=8),
        sla_due_at=now - timedelta(hours=3),
    )

    payload = client.get("/metrics/sla", headers=auth(token)).json()

    assert payload["scope"] == "OWN"
    assert payload["total"] == 1
    assert payload["by_sla_status"] == {"on_track": 0, "met": 1, "breached": 0}


@pytest.mark.parametrize("role", [UserRole.AGENT, UserRole.ADMIN])
def test_staff_sla_metrics_are_global(client: TestClient, db: Session, role: UserRole) -> None:
    owner, _ = seed_user(db, f"sla-global-owner-{role.value.lower()}@example.com")
    _, token = seed_user(db, f"sla-global-staff-{role.value.lower()}@example.com", role)
    now = datetime.now(timezone.utc)

    seed_ticket(
        db,
        owner,
        title="Global on track",
        created_at=now - timedelta(hours=1),
        sla_due_at=now + timedelta(hours=2),
    )

    payload = client.get("/metrics/sla", headers=auth(token)).json()

    assert payload["scope"] == "GLOBAL"
    assert payload["total"] == 1
    assert payload["by_sla_status"] == {"on_track": 1, "met": 0, "breached": 0}
