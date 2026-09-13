from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole

PASSWORD = "StrongPass123!"


def create_user_and_token(client: TestClient, email: str) -> str:
    register = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert register.status_code == 201

    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_ticket(client: TestClient, token: str):
    response = client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": "VPN unavailable",
            "description": "The corporate VPN is not connecting.",
            "priority": "MEDIUM",
        },
    )
    assert response.status_code == 201
    return response


def promote(db: Session, email: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_assignment_requires_authentication(client: TestClient) -> None:
    response = client.patch("/tickets/1/assignment", json={"agent_id": 1})
    assert response.status_code == 401


def test_user_cannot_assign_ticket(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)

    response = client.patch(
        f"/tickets/{ticket.json()['id']}/assignment",
        headers=auth(token),
        json={"agent_id": ticket.json()["owner_id"]},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Users cannot assign tickets"


def test_agent_can_assign_ticket_to_self(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)

    create_user_and_token(client, "agent@example.com")
    agent = promote(db, "agent@example.com", UserRole.AGENT)
    agent_token = login(client, "agent@example.com")

    response = client.patch(
        f"/tickets/{ticket.json()['id']}/assignment",
        headers=auth(agent_token),
        json={"agent_id": agent.id},
    )

    assert response.status_code == 200
    assert response.json()["assigned_agent_id"] == agent.id


def test_agent_cannot_assign_ticket_to_another_agent(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)

    create_user_and_token(client, "agent1@example.com")
    agent1 = promote(db, "agent1@example.com", UserRole.AGENT)
    create_user_and_token(client, "agent2@example.com")
    agent2 = promote(db, "agent2@example.com", UserRole.AGENT)
    agent1_token = login(client, "agent1@example.com")

    response = client.patch(
        f"/tickets/{ticket.json()['id']}/assignment",
        headers=auth(agent1_token),
        json={"agent_id": agent2.id},
    )

    assert response.status_code == 403
    assert agent1.id != agent2.id


def test_admin_can_assign_ticket_to_agent(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)

    create_user_and_token(client, "agent@example.com")
    agent = promote(db, "agent@example.com", UserRole.AGENT)
    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    response = client.patch(
        f"/tickets/{ticket.json()['id']}/assignment",
        headers=auth(admin_token),
        json={"agent_id": agent.id},
    )

    assert response.status_code == 200
    assert response.json()["assigned_agent_id"] == agent.id


def test_admin_cannot_assign_ticket_to_regular_user(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    owner = db.scalar(select(User).where(User.email == "owner@example.com"))
    assert owner is not None

    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    response = client.patch(
        f"/tickets/{ticket.json()['id']}/assignment",
        headers=auth(admin_token),
        json={"agent_id": owner.id},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Assigned user must have AGENT role"


def test_assignment_and_unassignment_are_recorded_in_history(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "agent@example.com")
    agent = promote(db, "agent@example.com", UserRole.AGENT)
    create_user_and_token(client, "admin@example.com")
    admin = promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    assigned = client.patch(
        f"/tickets/{ticket_id}/assignment",
        headers=auth(admin_token),
        json={"agent_id": agent.id},
    )
    assert assigned.status_code == 200

    unassigned = client.patch(
        f"/tickets/{ticket_id}/assignment",
        headers=auth(admin_token),
        json={"agent_id": None},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["assigned_agent_id"] is None

    history = client.get(f"/tickets/{ticket_id}/history", headers=auth(admin_token))
    assert history.status_code == 200

    assignment_events = [
        item for item in history.json() if item["field"] == "assigned_agent_id"
    ]
    assert len(assignment_events) == 2
    assert assignment_events[0]["action"] == "ASSIGNED"
    assert assignment_events[0]["old_value"] is None
    assert assignment_events[0]["new_value"] == str(agent.id)
    assert assignment_events[0]["actor_id"] == admin.id
    assert assignment_events[1]["action"] == "UNASSIGNED"
    assert assignment_events[1]["old_value"] == str(agent.id)
    assert assignment_events[1]["new_value"] is None
