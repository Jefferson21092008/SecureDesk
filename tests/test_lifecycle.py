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
            "title": "Email unavailable",
            "description": "The corporate mailbox cannot send messages.",
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


def assign_to_agent(client: TestClient, ticket_id: int, admin_token: str, agent_id: int) -> None:
    response = client.patch(
        f"/tickets/{ticket_id}/assignment",
        headers=auth(admin_token),
        json={"agent_id": agent_id},
    )
    assert response.status_code == 200


def test_lifecycle_requires_authentication(client: TestClient) -> None:
    assert client.post("/tickets/1/close").status_code == 401
    assert client.post("/tickets/1/reopen").status_code == 401


def test_user_cannot_close_ticket(client: TestClient) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)

    response = client.post(
        f"/tickets/{ticket.json()['id']}/close",
        headers=auth(owner_token),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Users cannot close or reopen tickets"


def test_agent_can_close_assigned_ticket(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "agent@example.com")
    agent = promote(db, "agent@example.com", UserRole.AGENT)
    agent_token = login(client, "agent@example.com")

    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")
    assign_to_agent(client, ticket_id, admin_token, agent.id)

    response = client.post(f"/tickets/{ticket_id}/close", headers=auth(agent_token))

    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"
    assert response.json()["closed_at"] is not None


def test_agent_cannot_close_ticket_assigned_to_another_agent(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "agent1@example.com")
    promote(db, "agent1@example.com", UserRole.AGENT)
    agent1_token = login(client, "agent1@example.com")

    create_user_and_token(client, "agent2@example.com")
    agent2 = promote(db, "agent2@example.com", UserRole.AGENT)

    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")
    assign_to_agent(client, ticket_id, admin_token, agent2.id)

    response = client.post(f"/tickets/{ticket_id}/close", headers=auth(agent1_token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Agents can only close or reopen tickets assigned to themselves"


def test_admin_can_close_and_reopen_any_ticket(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    closed = client.post(f"/tickets/{ticket_id}/close", headers=auth(admin_token))
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["closed_at"] is not None

    reopened = client.post(f"/tickets/{ticket_id}/reopen", headers=auth(admin_token))
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "OPEN"
    assert reopened.json()["closed_at"] is None


def test_invalid_lifecycle_transitions_return_conflict(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    reopen_open = client.post(f"/tickets/{ticket_id}/reopen", headers=auth(admin_token))
    assert reopen_open.status_code == 409

    closed = client.post(f"/tickets/{ticket_id}/close", headers=auth(admin_token))
    assert closed.status_code == 200

    close_again = client.post(f"/tickets/{ticket_id}/close", headers=auth(admin_token))
    assert close_again.status_code == 409


def test_close_and_reopen_are_recorded_in_history(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "admin@example.com")
    admin = promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    assert client.post(f"/tickets/{ticket_id}/close", headers=auth(admin_token)).status_code == 200
    assert client.post(f"/tickets/{ticket_id}/reopen", headers=auth(admin_token)).status_code == 200

    history = client.get(f"/tickets/{ticket_id}/history", headers=auth(admin_token))
    assert history.status_code == 200

    lifecycle = [item for item in history.json() if item["action"] in {"CLOSED", "REOPENED"}]
    assert len(lifecycle) == 2
    assert lifecycle[0]["action"] == "CLOSED"
    assert lifecycle[0]["old_value"] == "OPEN"
    assert lifecycle[0]["new_value"] == "CLOSED"
    assert lifecycle[0]["actor_id"] == admin.id
    assert lifecycle[1]["action"] == "REOPENED"
    assert lifecycle[1]["old_value"] == "CLOSED"
    assert lifecycle[1]["new_value"] == "OPEN"
    assert lifecycle[1]["actor_id"] == admin.id


def test_generic_patch_cannot_bypass_lifecycle_endpoints(client: TestClient, db: Session) -> None:
    owner_token = create_user_and_token(client, "owner@example.com")
    ticket = create_ticket(client, owner_token)
    ticket_id = ticket.json()["id"]

    create_user_and_token(client, "admin@example.com")
    promote(db, "admin@example.com", UserRole.ADMIN)
    admin_token = login(client, "admin@example.com")

    direct_close = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(admin_token),
        json={"status": "CLOSED"},
    )
    assert direct_close.status_code == 409
    assert direct_close.json()["detail"] == "Use the close endpoint to close a ticket"

    assert client.post(f"/tickets/{ticket_id}/close", headers=auth(admin_token)).status_code == 200

    direct_reopen = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(admin_token),
        json={"status": "OPEN"},
    )
    assert direct_reopen.status_code == 409
    assert direct_reopen.json()["detail"] == "Use the reopen endpoint before changing a closed ticket status"
