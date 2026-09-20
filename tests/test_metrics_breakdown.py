from datetime import datetime, timezone

import pytest
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


def seed_department(db: Session, name: str) -> Department:
    department = Department(name=name)
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


def seed_category(db: Session, name: str) -> Category:
    category = Category(name=name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def seed_ticket(
    db: Session,
    owner: User,
    *,
    title: str,
    department: Department | None = None,
    category: Category | None = None,
    agent: User | None = None,
) -> Ticket:
    created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    ticket = Ticket(
        title=title,
        description="Metrics breakdown test ticket",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        owner_id=owner.id,
        department_id=department.id if department else None,
        category_id=category.id if category else None,
        assigned_agent_id=agent.id if agent else None,
        created_at=created_at,
        sla_due_at=calculate_sla_due_at(created_at, TicketPriority.MEDIUM),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_breakdown_metrics_requires_authentication(client: TestClient) -> None:
    response = client.get("/metrics/breakdown")
    assert response.status_code == 401


def test_breakdown_metrics_returns_empty_lists_when_no_tickets(
    client: TestClient,
    db: Session,
) -> None:
    _, token = seed_user(db, "breakdown-empty@example.com")

    response = client.get("/metrics/breakdown", headers=auth(token))

    assert response.status_code == 200
    assert response.json() == {
        "scope": "OWN",
        "by_department": [],
        "by_category": [],
        "by_agent": [],
    }


def test_user_breakdown_counts_only_own_tickets_and_keeps_null_buckets(
    client: TestClient,
    db: Session,
) -> None:
    owner, token = seed_user(db, "breakdown-owner@example.com")
    other, _ = seed_user(db, "breakdown-other@example.com")
    agent, _ = seed_user(db, "breakdown-agent@example.com", UserRole.AGENT)
    department = seed_department(db, "Infrastructure")
    category = seed_category(db, "Network")

    seed_ticket(
        db,
        owner,
        title="Own grouped",
        department=department,
        category=category,
        agent=agent,
    )
    seed_ticket(db, owner, title="Own unclassified")
    seed_ticket(
        db,
        other,
        title="Foreign grouped",
        department=department,
        category=category,
        agent=agent,
    )

    payload = client.get("/metrics/breakdown", headers=auth(token)).json()

    assert payload["scope"] == "OWN"
    assert payload["by_department"] == [
        {
            "department_id": department.id,
            "department_name": "Infrastructure",
            "total": 1,
        },
        {"department_id": None, "department_name": None, "total": 1},
    ]
    assert payload["by_category"] == [
        {"category_id": category.id, "category_name": "Network", "total": 1},
        {"category_id": None, "category_name": None, "total": 1},
    ]
    assert payload["by_agent"] == [
        {"agent_id": agent.id, "agent_email": agent.email, "total": 1},
        {"agent_id": None, "agent_email": None, "total": 1},
    ]


def test_breakdown_groups_repeated_dimensions(client: TestClient, db: Session) -> None:
    owner, token = seed_user(db, "breakdown-repeat@example.com")
    agent, _ = seed_user(db, "repeat-agent@example.com", UserRole.AGENT)
    department = seed_department(db, "Support")
    category = seed_category(db, "Access")

    for index in range(3):
        seed_ticket(
            db,
            owner,
            title=f"Repeated {index}",
            department=department,
            category=category,
            agent=agent,
        )

    payload = client.get("/metrics/breakdown", headers=auth(token)).json()

    assert payload["by_department"] == [
        {"department_id": department.id, "department_name": "Support", "total": 3}
    ]
    assert payload["by_category"] == [
        {"category_id": category.id, "category_name": "Access", "total": 3}
    ]
    assert payload["by_agent"] == [
        {"agent_id": agent.id, "agent_email": agent.email, "total": 3}
    ]


@pytest.mark.parametrize("role", [UserRole.AGENT, UserRole.ADMIN])
def test_staff_breakdown_is_global(client: TestClient, db: Session, role: UserRole) -> None:
    first_owner, _ = seed_user(db, f"breakdown-first-{role.value.lower()}@example.com")
    second_owner, _ = seed_user(db, f"breakdown-second-{role.value.lower()}@example.com")
    _, staff_token = seed_user(db, f"breakdown-staff-{role.value.lower()}@example.com", role)
    assigned_agent, _ = seed_user(
        db,
        f"breakdown-assignee-{role.value.lower()}@example.com",
        UserRole.AGENT,
    )
    department = seed_department(db, f"Operations {role.value}")
    category = seed_category(db, f"Hardware {role.value}")

    seed_ticket(
        db,
        first_owner,
        title="First global",
        department=department,
        category=category,
        agent=assigned_agent,
    )
    seed_ticket(
        db,
        second_owner,
        title="Second global",
        department=department,
        category=category,
        agent=assigned_agent,
    )

    payload = client.get("/metrics/breakdown", headers=auth(staff_token)).json()

    assert payload["scope"] == "GLOBAL"
    assert payload["by_department"][0]["total"] == 2
    assert payload["by_category"][0]["total"] == 2
    assert payload["by_agent"][0]["total"] == 2


def test_breakdown_orders_named_groups_and_places_null_bucket_last(
    client: TestClient,
    db: Session,
) -> None:
    owner, token = seed_user(db, "breakdown-order@example.com")
    agent_z, _ = seed_user(db, "z-agent@example.com", UserRole.AGENT)
    agent_a, _ = seed_user(db, "a-agent@example.com", UserRole.AGENT)
    department_z = seed_department(db, "Zeta")
    department_a = seed_department(db, "Alpha")
    category_z = seed_category(db, "Z-category")
    category_a = seed_category(db, "A-category")

    seed_ticket(
        db,
        owner,
        title="Z group",
        department=department_z,
        category=category_z,
        agent=agent_z,
    )
    seed_ticket(
        db,
        owner,
        title="A group",
        department=department_a,
        category=category_a,
        agent=agent_a,
    )
    seed_ticket(db, owner, title="No group")

    payload = client.get("/metrics/breakdown", headers=auth(token)).json()

    assert [row["department_name"] for row in payload["by_department"]] == [
        "Alpha",
        "Zeta",
        None,
    ]
    assert [row["category_name"] for row in payload["by_category"]] == [
        "A-category",
        "Z-category",
        None,
    ]
    assert [row["agent_email"] for row in payload["by_agent"]] == [
        "a-agent@example.com",
        "z-agent@example.com",
        None,
    ]
