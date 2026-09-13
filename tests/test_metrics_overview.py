from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
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
    status: TicketStatus = TicketStatus.OPEN,
    priority: TicketPriority = TicketPriority.MEDIUM,
) -> Ticket:
    created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    ticket = Ticket(
        title=title,
        description="Metrics overview test ticket",
        status=status,
        priority=priority,
        owner_id=owner.id,
        created_at=created_at,
        closed_at=created_at if status == TicketStatus.CLOSED else None,
        sla_due_at=calculate_sla_due_at(created_at, priority),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_metrics_overview_requires_authentication(client: TestClient) -> None:
    response = client.get("/metrics/overview")
    assert response.status_code == 401


def test_metrics_overview_returns_zero_buckets_when_empty(client: TestClient, db: Session) -> None:
    _, token = seed_user(db, "empty-metrics@example.com")

    response = client.get("/metrics/overview", headers=auth(token))

    assert response.status_code == 200
    assert response.json() == {
        "scope": "OWN",
        "total": 0,
        "by_status": {"open": 0, "in_progress": 0, "closed": 0},
        "by_priority": {"low": 0, "medium": 0, "high": 0},
    }


def test_user_metrics_count_only_own_tickets(client: TestClient, db: Session) -> None:
    owner, owner_token = seed_user(db, "metrics-owner@example.com")
    other, _ = seed_user(db, "metrics-other@example.com")

    seed_ticket(db, owner, title="Own low", status=TicketStatus.OPEN, priority=TicketPriority.LOW)
    seed_ticket(
        db,
        owner,
        title="Own medium",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.MEDIUM,
    )
    seed_ticket(db, owner, title="Own high", status=TicketStatus.CLOSED, priority=TicketPriority.HIGH)
    seed_ticket(db, other, title="Foreign high", status=TicketStatus.OPEN, priority=TicketPriority.HIGH)

    response = client.get("/metrics/overview", headers=auth(owner_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "OWN"
    assert payload["total"] == 3
    assert payload["by_status"] == {"open": 1, "in_progress": 1, "closed": 1}
    assert payload["by_priority"] == {"low": 1, "medium": 1, "high": 1}


@pytest.mark.parametrize("role", [UserRole.AGENT, UserRole.ADMIN])
def test_staff_metrics_are_global(client: TestClient, db: Session, role: UserRole) -> None:
    first, _ = seed_user(db, f"first-{role.value.lower()}@example.com")
    second, _ = seed_user(db, f"second-{role.value.lower()}@example.com")
    _, staff_token = seed_user(db, f"staff-{role.value.lower()}@example.com", role)

    seed_ticket(db, first, title="Open high", status=TicketStatus.OPEN, priority=TicketPriority.HIGH)
    seed_ticket(
        db,
        first,
        title="Progress high",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.HIGH,
    )
    seed_ticket(db, second, title="Closed low", status=TicketStatus.CLOSED, priority=TicketPriority.LOW)
    seed_ticket(db, second, title="Open medium", status=TicketStatus.OPEN, priority=TicketPriority.MEDIUM)

    response = client.get("/metrics/overview", headers=auth(staff_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "GLOBAL"
    assert payload["total"] == 4
    assert payload["by_status"] == {"open": 2, "in_progress": 1, "closed": 1}
    assert payload["by_priority"] == {"low": 1, "medium": 1, "high": 2}
