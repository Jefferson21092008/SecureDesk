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


def create_ticket(client: TestClient, token: str, title: str = "Printer offline"):
    return client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": title,
            "description": "The finance printer is not responding.",
            "priority": "MEDIUM",
        },
    )


def test_history_requires_authentication(client: TestClient) -> None:
    response = client.get("/tickets/1/history")
    assert response.status_code == 401


def test_ticket_creation_registers_history(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)
    assert ticket.status_code == 201

    response = client.get(f"/tickets/{ticket.json()['id']}/history", headers=auth(token))

    assert response.status_code == 200
    history = response.json()
    assert len(history) == 1
    assert history[0]["action"] == "CREATED"
    assert history[0]["field"] is None
    assert history[0]["old_value"] is None
    assert history[0]["new_value"] is None
    assert history[0]["actor_id"] == ticket.json()["owner_id"]
    assert history[0]["created_at"]


def test_patch_registers_changed_fields_with_old_and_new_values(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)
    ticket_id = ticket.json()["id"]

    update = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(token),
        json={"title": "Printer error E42", "priority": "HIGH"},
    )
    assert update.status_code == 200

    response = client.get(f"/tickets/{ticket_id}/history", headers=auth(token))
    assert response.status_code == 200

    history = response.json()
    assert len(history) == 4
    updates = {item["field"]: item for item in history if item["action"] == "UPDATED"}

    assert updates["title"]["old_value"] == "Printer offline"
    assert updates["title"]["new_value"] == "Printer error E42"
    assert updates["priority"]["old_value"] == "MEDIUM"
    assert updates["priority"]["new_value"] == "HIGH"


def test_patch_with_same_value_does_not_create_extra_history(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)
    ticket_id = ticket.json()["id"]

    update = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(token),
        json={"priority": "MEDIUM"},
    )
    assert update.status_code == 200

    response = client.get(f"/tickets/{ticket_id}/history", headers=auth(token))
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_user_cannot_access_another_users_history(client: TestClient) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    other_token = create_user_and_token(client, "other@example.com")
    ticket = create_ticket(client, owner_token)

    response = client.get(
        f"/tickets/{ticket.json()['id']}/history",
        headers=auth(other_token),
    )

    assert response.status_code == 403


def test_agent_update_is_recorded_with_agent_as_actor(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "agent@example.com")
    agent = db.scalar(select(User).where(User.email == "agent@example.com"))
    assert agent is not None
    agent.role = UserRole.AGENT
    db.commit()

    login = client.post(
        "/auth/login",
        data={"username": "agent@example.com", "password": PASSWORD},
    )
    agent_token = login.json()["access_token"]

    update = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(agent_token),
        json={"status": "IN_PROGRESS"},
    )
    assert update.status_code == 200

    response = client.get(f"/tickets/{ticket_id}/history", headers=auth(agent_token))
    assert response.status_code == 200

    status_change = next(item for item in response.json() if item["field"] == "status")
    assert status_change["old_value"] == "OPEN"
    assert status_change["new_value"] == "IN_PROGRESS"
    assert status_change["actor_id"] == agent.id
