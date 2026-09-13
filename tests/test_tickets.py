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


def test_ticket_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/tickets")
    assert response.status_code == 401


def test_user_can_create_and_list_only_own_tickets(client: TestClient) -> None:
    first_token = create_user_and_token(client, "first@example.com")
    second_token = create_user_and_token(client, "second@example.com")

    first_ticket = create_ticket(client, first_token, "First user ticket")
    second_ticket = create_ticket(client, second_token, "Second user ticket")
    assert first_ticket.status_code == 201
    assert second_ticket.status_code == 201

    response = client.get("/tickets", headers=auth(first_token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "First user ticket"


def test_user_cannot_read_another_users_ticket(client: TestClient) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    other_token = create_user_and_token(client, "other@example.com")
    ticket = create_ticket(client, owner_token)

    response = client.get(f"/tickets/{ticket.json()['id']}", headers=auth(other_token))

    assert response.status_code == 403


def test_user_cannot_change_ticket_status(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)

    response = client.patch(
        f"/tickets/{ticket.json()['id']}",
        headers=auth(token),
        json={"status": "CLOSED"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Users cannot change ticket status"


def test_ticket_patch_rejects_explicit_null(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)

    response = client.patch(
        f"/tickets/{ticket.json()['id']}",
        headers=auth(token),
        json={"title": None},
    )

    assert response.status_code == 422


def test_agent_can_see_and_manage_all_tickets(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    create_ticket(client, owner_token)

    create_user_and_token(client, "agent@example.com")
    agent = db.scalar(select(User).where(User.email == "agent@example.com"))
    assert agent is not None
    agent.role = UserRole.AGENT
    db.commit()

    agent_login = client.post(
        "/auth/login",
        data={"username": "agent@example.com", "password": PASSWORD},
    )
    agent_token = agent_login.json()["access_token"]

    tickets = client.get("/tickets", headers=auth(agent_token))
    assert tickets.status_code == 200
    assert tickets.json()["total"] == 1

    ticket_id = tickets.json()["items"][0]["id"]
    update = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(agent_token),
        json={"status": "IN_PROGRESS"},
    )
    assert update.status_code == 200
    assert update.json()["status"] == "IN_PROGRESS"

    delete = client.delete(f"/tickets/{ticket_id}", headers=auth(agent_token))
    assert delete.status_code == 204
