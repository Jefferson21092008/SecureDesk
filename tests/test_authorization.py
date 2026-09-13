import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.user import User, UserRole

PASSWORD = "StrongPass123!"


def register_and_token(client: TestClient, email: str) -> tuple[int, str]:
    register = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert register.status_code == 201
    user_id = register.json()["id"]

    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_ticket(client: TestClient, token: str, title: str = "Authorization ticket") -> dict:
    response = client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": title,
            "description": "Ticket used by authorization and IDOR tests.",
            "priority": "MEDIUM",
        },
    )
    assert response.status_code == 201
    return response.json()


def make_role(
    client: TestClient,
    db: Session,
    email: str,
    role: UserRole,
) -> tuple[int, str]:
    user_id, _ = register_and_token(client, email)
    user = db.get(User, user_id)
    assert user is not None
    user.role = role
    db.commit()

    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


def upload_attachment(client: TestClient, token: str, ticket_id: int):
    response = client.post(
        f"/tickets/{ticket_id}/attachments",
        headers=auth(token),
        files={"file": ("evidence.txt", b"security evidence", "text/plain")},
    )
    assert response.status_code == 201
    return response


def test_inaccessible_ticket_and_missing_ticket_are_indistinguishable(client: TestClient) -> None:
    _, owner_token = register_and_token(client, "idor-owner@example.com")
    _, attacker_token = register_and_token(client, "idor-attacker@example.com")
    ticket = create_ticket(client, owner_token)

    existing = client.get(f"/tickets/{ticket['id']}", headers=auth(attacker_token))
    missing = client.get("/tickets/999999", headers=auth(attacker_token))

    assert existing.status_code == 404
    assert missing.status_code == 404
    assert existing.json() == {"detail": "Ticket not found"}
    assert missing.json() == {"detail": "Ticket not found"}


def test_user_cannot_modify_another_users_ticket_by_guessing_id(
    client: TestClient,
    db: Session,
) -> None:
    _, owner_token = register_and_token(client, "idor-patch-owner@example.com")
    _, attacker_token = register_and_token(client, "idor-patch-attacker@example.com")
    ticket = create_ticket(client, owner_token, "Original title")

    response = client.patch(
        f"/tickets/{ticket['id']}",
        headers=auth(attacker_token),
        json={"title": "Compromised title"},
    )

    assert response.status_code == 404
    stored = db.get(Ticket, ticket["id"])
    assert stored is not None
    assert stored.title == "Original title"


def test_nested_comment_routes_hide_another_users_ticket(client: TestClient) -> None:
    _, owner_token = register_and_token(client, "idor-comment-owner@example.com")
    _, attacker_token = register_and_token(client, "idor-comment-attacker@example.com")
    ticket = create_ticket(client, owner_token)

    read = client.get(f"/tickets/{ticket['id']}/comments", headers=auth(attacker_token))
    write = client.post(
        f"/tickets/{ticket['id']}/comments",
        headers=auth(attacker_token),
        json={"content": "Unauthorized comment"},
    )

    assert read.status_code == 404
    assert write.status_code == 404


def test_history_route_hides_another_users_ticket(client: TestClient) -> None:
    _, owner_token = register_and_token(client, "idor-history-owner@example.com")
    _, attacker_token = register_and_token(client, "idor-history-attacker@example.com")
    ticket = create_ticket(client, owner_token)

    response = client.get(f"/tickets/{ticket['id']}/history", headers=auth(attacker_token))

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}


def test_attachment_routes_hide_another_users_ticket(client: TestClient) -> None:
    _, owner_token = register_and_token(client, "idor-file-owner@example.com")
    _, attacker_token = register_and_token(client, "idor-file-attacker@example.com")
    ticket = create_ticket(client, owner_token)
    attachment = upload_attachment(client, owner_token, ticket["id"]).json()

    listed = client.get(f"/tickets/{ticket['id']}/attachments", headers=auth(attacker_token))
    downloaded = client.get(
        f"/tickets/{ticket['id']}/attachments/{attachment['id']}",
        headers=auth(attacker_token),
    )
    uploaded = client.post(
        f"/tickets/{ticket['id']}/attachments",
        headers=auth(attacker_token),
        files={"file": ("attack.txt", b"unauthorized", "text/plain")},
    )
    deleted = client.delete(
        f"/tickets/{ticket['id']}/attachments/{attachment['id']}",
        headers=auth(attacker_token),
    )

    assert listed.status_code == 404
    assert downloaded.status_code == 404
    assert uploaded.status_code == 404
    assert deleted.status_code == 404


def test_attachment_id_is_scoped_to_parent_ticket(client: TestClient) -> None:
    _, token = register_and_token(client, "idor-parent@example.com")
    first = create_ticket(client, token, "First parent")
    second = create_ticket(client, token, "Second parent")
    attachment = upload_attachment(client, token, first["id"]).json()

    response = client.get(
        f"/tickets/{second['id']}/attachments/{attachment['id']}",
        headers=auth(token),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Attachment not found"}


def test_query_parameters_cannot_escape_owner_scope(client: TestClient) -> None:
    _, owner_token = register_and_token(client, "query-scope-owner@example.com")
    _, attacker_token = register_and_token(client, "query-scope-attacker@example.com")
    create_ticket(client, owner_token, "Highly confidential incident")
    own = create_ticket(client, attacker_token, "Ordinary request")

    response = client.get(
        "/tickets?search=confidential&page=1&page_size=100&sort_by=id&sort_order=asc",
        headers=auth(attacker_token),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert all(item["id"] != own["id"] for item in response.json()["items"])


def test_ticket_payload_cannot_mass_assign_security_sensitive_fields(client: TestClient, db: Session) -> None:
    user_id, token = register_and_token(client, "mass-assignment@example.com")

    created = client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": "Mass assignment test",
            "description": "Sensitive fields in the request must not override server ownership.",
            "owner_id": 999999,
            "assigned_agent_id": 999999,
            "status": "CLOSED",
        },
    )
    assert created.status_code == 422

    legitimate = create_ticket(client, token, "Mass assignment target")
    patched = client.patch(
        f"/tickets/{legitimate['id']}",
        headers=auth(token),
        json={
            "title": "Legitimate title update",
            "owner_id": 999999,
            "assigned_agent_id": 999999,
            "closed_at": "2099-01-01T00:00:00Z",
        },
    )
    assert patched.status_code == 422

    stored = db.get(Ticket, legitimate["id"])
    assert stored is not None
    assert stored.owner_id == user_id
    assert stored.assigned_agent_id is None
    assert stored.closed_at is None


@pytest.mark.parametrize(
    ("method", "suffix", "json_body"),
    [
        ("post", "/close", None),
        ("post", "/reopen", None),
        ("patch", "/assignment", {"agent_id": None}),
        ("delete", "", None),
    ],
)
def test_role_denial_does_not_reveal_ticket_existence(
    client: TestClient,
    method: str,
    suffix: str,
    json_body: dict | None,
) -> None:
    _, token = register_and_token(client, f"existence-{method}-{suffix.replace('/', '-') or 'delete'}@example.com")
    ticket = create_ticket(client, token)

    request = getattr(client, method)
    kwargs = {"headers": auth(token)}
    if json_body is not None:
        kwargs["json"] = json_body

    existing = request(f"/tickets/{ticket['id']}{suffix}", **kwargs)
    missing = request(f"/tickets/999999{suffix}", **kwargs)

    assert existing.status_code == 403
    assert missing.status_code == 403


def test_agent_cross_ticket_access_remains_allowed(client: TestClient, db: Session) -> None:
    _, owner_token = register_and_token(client, "staff-owner@example.com")
    ticket = create_ticket(client, owner_token)
    _, agent_token = make_role(client, db, "staff-agent@example.com", UserRole.AGENT)

    response = client.get(f"/tickets/{ticket['id']}", headers=auth(agent_token))

    assert response.status_code == 200
    assert response.json()["id"] == ticket["id"]


def test_regular_user_cannot_promote_role_through_api(client: TestClient, db: Session) -> None:
    user_id, token = register_and_token(client, "role-escalation@example.com")
    ticket = create_ticket(client, token)

    response = client.patch(
        f"/tickets/{ticket['id']}",
        headers=auth(token),
        json={"role": "ADMIN", "title": "Still a regular user"},
    )
    assert response.status_code == 422

    user = db.scalar(select(User).where(User.id == user_id))
    assert user is not None
    assert user.role == UserRole.USER
