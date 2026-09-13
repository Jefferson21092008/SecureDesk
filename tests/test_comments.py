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


def test_comment_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/tickets/1/comments")
    assert response.status_code == 401


def test_user_can_create_and_list_comments_on_own_ticket(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)
    ticket_id = ticket.json()["id"]

    first = client.post(
        f"/tickets/{ticket_id}/comments",
        headers=auth(token),
        json={"content": "I restarted the printer, but the problem continues."},
    )
    second = client.post(
        f"/tickets/{ticket_id}/comments",
        headers=auth(token),
        json={"content": "The display now shows error E42."},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["author_id"] > 0
    assert first.json()["ticket_id"] == ticket_id
    assert first.json()["created_at"]

    response = client.get(f"/tickets/{ticket_id}/comments", headers=auth(token))

    assert response.status_code == 200
    comments = response.json()
    assert [comment["content"] for comment in comments] == [
        "I restarted the printer, but the problem continues.",
        "The display now shows error E42.",
    ]


def test_user_cannot_access_comments_from_another_users_ticket(client: TestClient) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    other_token = create_user_and_token(client, "other@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create = client.post(
        f"/tickets/{ticket_id}/comments",
        headers=auth(other_token),
        json={"content": "I should not be able to write here."},
    )
    read = client.get(f"/tickets/{ticket_id}/comments", headers=auth(other_token))

    assert create.status_code == 404
    assert read.status_code == 404


def test_agent_can_comment_on_any_ticket(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

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

    response = client.post(
        f"/tickets/{ticket_id}/comments",
        headers=auth(agent_token),
        json={"content": "Support is investigating the issue."},
    )

    assert response.status_code == 201
    assert response.json()["author_id"] == agent.id


def test_comment_rejects_empty_content(client: TestClient) -> None:
    token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, token)

    response = client.post(
        f"/tickets/{ticket.json()['id']}/comments",
        headers=auth(token),
        json={"content": ""},
    )

    assert response.status_code == 422
