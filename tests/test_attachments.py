from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attachment import Attachment
from app.models.user import User, UserRole

PASSWORD = "StrongPass123!"


def register_and_token(client: TestClient, email: str) -> str:
    register = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert register.status_code == 201
    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_ticket(client: TestClient, token: str, title: str = "Attachment ticket") -> int:
    response = client.post(
        "/tickets",
        headers=auth(token),
        json={
            "title": title,
            "description": "Ticket used to test attachment behavior",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def make_role(client: TestClient, db: Session, email: str, role: UserRole) -> str:
    register_and_token(client, email)
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = role
    db.commit()
    login = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def upload_text(client: TestClient, token: str, ticket_id: int, filename: str = "evidence.txt"):
    return client.post(
        f"/tickets/{ticket_id}/attachments",
        headers=auth(token),
        files={"file": (filename, b"attachment evidence", "text/plain")},
    )


def test_attachment_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/tickets/1/attachments").status_code == 401
    response = client.post(
        "/tickets/1/attachments",
        files={"file": ("evidence.txt", b"content", "text/plain")},
    )
    assert response.status_code == 401


def test_owner_can_upload_list_and_download_attachment(client: TestClient) -> None:
    token = register_and_token(client, "attachment-owner@example.com")
    ticket_id = create_ticket(client, token)

    uploaded = upload_text(client, token, ticket_id)
    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["original_filename"] == "evidence.txt"
    assert payload["content_type"] == "text/plain"
    assert payload["size_bytes"] == len(b"attachment evidence")

    listed = client.get(f"/tickets/{ticket_id}/attachments", headers=auth(token))
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == payload["id"]

    downloaded = client.get(
        f"/tickets/{ticket_id}/attachments/{payload['id']}",
        headers=auth(token),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"attachment evidence"
    assert downloaded.headers["content-type"].startswith("text/plain")


def test_user_cannot_access_another_users_attachments(client: TestClient) -> None:
    owner_token = register_and_token(client, "attachment-owner-2@example.com")
    other_token = register_and_token(client, "attachment-other@example.com")
    ticket_id = create_ticket(client, owner_token)
    uploaded = upload_text(client, owner_token, ticket_id)
    attachment_id = uploaded.json()["id"]

    assert client.get(f"/tickets/{ticket_id}/attachments", headers=auth(other_token)).status_code == 403
    assert (
        client.get(
            f"/tickets/{ticket_id}/attachments/{attachment_id}",
            headers=auth(other_token),
        ).status_code
        == 403
    )


def test_agent_can_upload_to_another_users_ticket(client: TestClient, db: Session) -> None:
    owner_token = register_and_token(client, "attachment-agent-owner@example.com")
    ticket_id = create_ticket(client, owner_token)
    agent_token = make_role(client, db, "attachment-agent@example.com", UserRole.AGENT)

    response = upload_text(client, agent_token, ticket_id, "agent-note.log")

    assert response.status_code == 201
    assert response.json()["original_filename"] == "agent-note.log"


def test_attachment_rejects_unsupported_type(client: TestClient) -> None:
    token = register_and_token(client, "attachment-type@example.com")
    ticket_id = create_ticket(client, token)

    response = client.post(
        f"/tickets/{ticket_id}/attachments",
        headers=auth(token),
        files={"file": ("program.exe", b"MZ", "application/octet-stream")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported attachment type"


def test_attachment_rejects_extension_content_type_mismatch(client: TestClient) -> None:
    token = register_and_token(client, "attachment-extension@example.com")
    ticket_id = create_ticket(client, token)

    response = client.post(
        f"/tickets/{ticket_id}/attachments",
        headers=auth(token),
        files={"file": ("fake.txt", b"not really png", "image/png")},
    )

    assert response.status_code == 415


def test_attachment_rejects_oversized_file(client: TestClient, monkeypatch) -> None:
    token = register_and_token(client, "attachment-size@example.com")
    ticket_id = create_ticket(client, token)
    monkeypatch.setattr(settings, "attachment_max_bytes", 3)

    response = client.post(
        f"/tickets/{ticket_id}/attachments",
        headers=auth(token),
        files={"file": ("large.txt", b"1234", "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Attachment exceeds maximum allowed size"
    assert list(Path(settings.attachments_dir).glob("*")) == []


def test_attachment_rejects_empty_file(client: TestClient) -> None:
    token = register_and_token(client, "attachment-empty@example.com")
    ticket_id = create_ticket(client, token)

    response = client.post(
        f"/tickets/{ticket_id}/attachments",
        headers=auth(token),
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment cannot be empty"


def test_attachment_filename_is_sanitized_and_storage_key_is_random(
    client: TestClient,
    db: Session,
) -> None:
    token = register_and_token(client, "attachment-path@example.com")
    ticket_id = create_ticket(client, token)

    response = upload_text(client, token, ticket_id, "../../secret.txt")
    assert response.status_code == 201
    assert response.json()["original_filename"] == "secret.txt"

    attachment = db.get(Attachment, response.json()["id"])
    assert attachment is not None
    assert "secret" not in attachment.storage_key
    assert "/" not in attachment.storage_key
    assert "\\" not in attachment.storage_key
    assert (Path(settings.attachments_dir) / attachment.storage_key).is_file()


def test_only_uploader_or_admin_can_delete_attachment(client: TestClient, db: Session) -> None:
    owner_token = register_and_token(client, "attachment-delete-owner@example.com")
    ticket_id = create_ticket(client, owner_token)
    uploaded = upload_text(client, owner_token, ticket_id)
    attachment_id = uploaded.json()["id"]

    agent_token = make_role(client, db, "attachment-delete-agent@example.com", UserRole.AGENT)
    forbidden = client.delete(
        f"/tickets/{ticket_id}/attachments/{attachment_id}",
        headers=auth(agent_token),
    )
    assert forbidden.status_code == 403

    admin_token = make_role(client, db, "attachment-delete-admin@example.com", UserRole.ADMIN)
    deleted = client.delete(
        f"/tickets/{ticket_id}/attachments/{attachment_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 204
    assert db.get(Attachment, attachment_id) is None


def test_attachment_actions_are_recorded_in_history(client: TestClient) -> None:
    token = register_and_token(client, "attachment-history@example.com")
    ticket_id = create_ticket(client, token)
    uploaded = upload_text(client, token, ticket_id)
    attachment_id = uploaded.json()["id"]

    deleted = client.delete(
        f"/tickets/{ticket_id}/attachments/{attachment_id}",
        headers=auth(token),
    )
    assert deleted.status_code == 204

    history = client.get(f"/tickets/{ticket_id}/history", headers=auth(token))
    assert history.status_code == 200
    actions = [entry for entry in history.json() if entry["action"].startswith("ATTACHMENT_")]
    assert [entry["action"] for entry in actions] == ["ATTACHMENT_ADDED", "ATTACHMENT_DELETED"]
    assert actions[0]["new_value"] == str(attachment_id)
    assert actions[1]["old_value"] == str(attachment_id)


def test_deleting_ticket_removes_stored_attachment(client: TestClient, db: Session) -> None:
    owner_token = register_and_token(client, "attachment-ticket-delete-owner@example.com")
    ticket_id = create_ticket(client, owner_token)
    uploaded = upload_text(client, owner_token, ticket_id)
    attachment = db.get(Attachment, uploaded.json()["id"])
    assert attachment is not None
    stored_path = Path(settings.attachments_dir) / attachment.storage_key
    assert stored_path.is_file()

    agent_token = make_role(client, db, "attachment-ticket-delete-agent@example.com", UserRole.AGENT)
    deleted = client.delete(f"/tickets/{ticket_id}", headers=auth(agent_token))

    assert deleted.status_code == 204
    assert not stored_path.exists()
