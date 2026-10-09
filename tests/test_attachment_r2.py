"""R2 API tests use an in-memory fake; never send requests to Cloudflare."""

from io import BytesIO

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attachment import Attachment
from app.services import attachment_r2

PASSWORD = "StrongPass123!"


class FakeR2Body:
    def __init__(self, content: bytes) -> None:
        self.source = BytesIO(content)
        self.closed = False

    def iter_chunks(self, chunk_size: int):
        while chunk := self.source.read(chunk_size):
            yield chunk

    def close(self):
        self.closed = True
        self.source.close()


class FakeR2:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.upload_calls: list[dict] = []
        self.bodies: list[FakeR2Body] = []
        self.failing_operation: str | None = None

    def _fail(self, operation: str) -> None:
        if self.failing_operation == operation:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "secret details"}}, operation)

    def put_object(self, **kwargs):
        self._fail("PutObject")
        assert kwargs["Bucket"] == "securedesk-test-private"
        assert "ACL" not in kwargs  # R2 bucket must not be made public
        data = kwargs["Body"].read()
        assert kwargs["ContentLength"] == len(data)
        self.objects[kwargs["Key"]] = data
        self.upload_calls.append(kwargs)

    def get_object(self, **kwargs):
        self._fail("GetObject")
        if kwargs["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        body = FakeR2Body(self.objects[kwargs["Key"]])
        self.bodies.append(body)
        return {"Body": body}

    def delete_object(self, **kwargs):
        self._fail("DeleteObject")
        self.objects.pop(kwargs["Key"], None)


@pytest.fixture
def r2(monkeypatch):
    fake = FakeR2()
    monkeypatch.setattr(settings, "attachment_storage_backend", "r2")
    monkeypatch.setattr(settings, "r2_bucket_name", "securedesk-test-private")
    monkeypatch.setattr(attachment_r2, "_client", lambda: fake)
    return fake


def register(client: TestClient, email: str) -> str:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    response = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def create_ticket(client: TestClient, token: str) -> int:
    response = client.post(
        "/tickets", headers={"Authorization": f"Bearer {token}"}, json={"title": "Cloud upload", "description": "Test"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload(client: TestClient, token: str, ticket_id: int):
    return client.post(
        f"/tickets/{ticket_id}/attachments",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("safe.txt", b"private cloud evidence", "text/plain")},
    )


def test_r2_upload_private_download_delete_and_legacy_compatibility(client, db: Session, r2: FakeR2, monkeypatch):
    token = register(client, "r2-owner@example.com")
    ticket_id = create_ticket(client, token)
    auth = {"Authorization": f"Bearer {token}"}

    created = upload(client, token, ticket_id)
    assert created.status_code == 201
    attachment_id = created.json()["id"]
    saved = db.get(Attachment, attachment_id)
    assert saved is not None
    assert saved.storage_backend == "r2"
    assert r2.objects[saved.storage_key] == b"private cloud evidence"
    assert not r2.upload_calls[0].get("ACL")

    # Verify a restart/configuration switch cannot redirect existing references.
    monkeypatch.setattr(settings, "attachment_storage_backend", "local")
    downloaded = client.get(f"/tickets/{ticket_id}/attachments/{attachment_id}", headers=auth)
    assert downloaded.status_code == 200
    assert downloaded.content == b"private cloud evidence"
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert r2.bodies[-1].closed

    local = upload(client, token, ticket_id)
    assert local.status_code == 201
    assert db.get(Attachment, local.json()["id"]).storage_backend == "local"

    monkeypatch.setattr(settings, "attachment_storage_backend", "r2")
    assert client.get(f"/tickets/{ticket_id}/attachments/{local.json()['id']}", headers=auth).content == b"private cloud evidence"
    removed = client.delete(f"/tickets/{ticket_id}/attachments/{attachment_id}", headers=auth)
    assert removed.status_code == 204
    assert saved.storage_key not in r2.objects


def test_r2_download_enforces_ticket_permissions_before_network(client, r2: FakeR2):
    owner = register(client, "r2-private-owner@example.com")
    stranger = register(client, "r2-private-stranger@example.com")
    ticket_id = create_ticket(client, owner)
    attachment_id = upload(client, owner, ticket_id).json()["id"]
    r2.failing_operation = "GetObject"
    response = client.get(
        f"/tickets/{ticket_id}/attachments/{attachment_id}",
        headers={"Authorization": f"Bearer {stranger}"},
    )
    assert response.status_code == 404


def test_r2_upload_provider_failure_returns_503_without_db_row(client, db: Session, r2: FakeR2, caplog):
    token = register(client, "r2-provider-down@example.com")
    ticket_id = create_ticket(client, token)
    r2.failing_operation = "PutObject"
    with caplog.at_level("WARNING", logger="securedesk.attachments"):
        failed = upload(client, token, ticket_id)
    assert failed.status_code == 503
    assert failed.json()["detail"] == "Attachment storage temporarily unavailable"
    assert db.scalar(select(Attachment).where(Attachment.ticket_id == ticket_id)) is None
    assert "secret details" not in caplog.text


def test_r2_missing_file_is_404_and_provider_unavailable_is_503(client, db: Session, r2: FakeR2):
    token = register(client, "r2-missing@example.com")
    ticket_id = create_ticket(client, token)
    created = upload(client, token, ticket_id)
    saved = db.get(Attachment, created.json()["id"])
    path = f"/tickets/{ticket_id}/attachments/{created.json()['id']}"
    headers = {"Authorization": f"Bearer {token}"}

    r2.objects.pop(saved.storage_key)
    missing = client.get(path, headers=headers)
    assert missing.status_code == 404
    r2.failing_operation = "GetObject"
    down = client.get(path, headers=headers)
    assert down.status_code == 503
    assert down.json()["detail"] == "Attachment storage temporarily unavailable"


def test_deleting_ticket_removes_r2_objects(client, db: Session, r2: FakeR2):
    from app.models.user import User, UserRole

    token = register(client, "r2-ticket-owner@example.com")
    ticket_id = create_ticket(client, token)
    attachment_id = upload(client, token, ticket_id).json()["id"]
    storage_key = db.get(Attachment, attachment_id).storage_key

    admin_token = register(client, "r2-ticket-admin@example.com")
    admin_user = db.scalar(select(User).where(User.email == "r2-ticket-admin@example.com"))
    admin_user.role = UserRole.ADMIN
    db.commit()
    response = client.delete(f"/tickets/{ticket_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 204
    assert storage_key not in r2.objects


def test_r2_rejects_bad_key_without_contacting_network(r2: FakeR2):
    from app.services.attachment_storage import remove_attachment

    assert not remove_attachment("../unsafe.txt", "r2")
    assert not remove_attachment("abc.txt", "unrecognized")
    assert not r2.objects


def test_r2_rejects_oversize_before_put(client, r2: FakeR2, monkeypatch):
    token = register(client, "r2-oversize@example.com")
    ticket_id = create_ticket(client, token)
    monkeypatch.setattr(settings, "attachment_max_bytes", 3)
    response = upload(client, token, ticket_id)
    assert response.status_code == 413
    assert r2.objects == {}
    assert r2.upload_calls == []


def test_r2_db_error_removes_object_after_failed_commit(client, db: Session, r2: FakeR2, monkeypatch):
    from app.main import app

    token = register(client, "r2-rollback@example.com")
    ticket_id = create_ticket(client, token)
    original_flush = Session.flush

    def fail_attachment_flush(self, objects=None):
        if any(isinstance(pending, Attachment) for pending in self.new):
            raise RuntimeError("simulated database failure")
        return original_flush(self, objects)

    monkeypatch.setattr(Session, "flush", fail_attachment_flush)
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = upload(safe_client, token, ticket_id)
    assert response.status_code == 500
    assert db.scalar(select(Attachment).where(Attachment.ticket_id == ticket_id)) is None
    assert r2.objects == {}


def test_failed_r2_delete_is_logged_after_committed_delete(client, db: Session, r2: FakeR2, caplog):
    token = register(client, "r2-delete-error@example.com")
    ticket_id = create_ticket(client, token)
    attachment_id = upload(client, token, ticket_id).json()["id"]
    r2.failing_operation = "DeleteObject"
    with caplog.at_level("WARNING", logger="securedesk.attachments"):
        response = client.delete(
            f"/tickets/{ticket_id}/attachments/{attachment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 204
    assert db.get(Attachment, attachment_id) is None
    assert "attachment_r2_cleanup_failed" in caplog.text
    assert "secret details" not in caplog.text
    assert r2.objects  # orphan until administrative cleanup/reconciliation
