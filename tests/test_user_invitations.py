"""Admin-only invitations, token secrecy, replay resistance and account activation."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.invitation import UserInvitation
from app.models.security_audit import SecurityAuditLog
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.services.invitations import now_utc, token_digest
from scripts.bootstrap_admin import InitialAdminConfigurationError, ensure_initial_admin

PASSWORD = "VerySecure!User2026"
ADMIN_PASSWORD = "VerySecure!Admin2026"


def admin_headers(client: TestClient, db: Session) -> dict[str, str]:
    ensure_initial_admin(db, email="root@example.com", password=ADMIN_PASSWORD)
    response = client.post("/auth/login", data={"username": "root@example.com", "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def invite(client: TestClient, headers: dict[str, str], email: str = "new@example.com", role: str = "USER"):
    return client.post("/admin/invitations", headers=headers, json={"email": email, "role": role})


def accept(client: TestClient, token: str, password: str = PASSWORD):
    return client.post("/auth/accept-invitation", json={"token": token, "password": password})


def test_anonymous_and_regular_users_cannot_manage_invitations(client: TestClient, db: Session) -> None:
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/invitations").status_code == 401
    assert invite(client, {}, "guest@example.com").status_code == 401
    response = client.post("/auth/register", json={"email": "employee@example.com", "password": PASSWORD})
    assert response.status_code == 201
    login = client.post("/auth/login", data={"username": "employee@example.com", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert invite(client, headers, "blocked@example.com").status_code == 403
    assert client.get("/admin/users", headers=headers).status_code == 403
    assert client.get("/admin/invitations", headers=headers).status_code == 403


def test_admin_can_invite_user_and_list_without_leaking_token(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    response = invite(client, headers, "NEW@example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "USER"
    assert len(body["token"]) >= 30
    assert "token_hash" not in body

    saved = db.scalar(select(UserInvitation).where(UserInvitation.id == body["id"]))
    assert saved is not None
    assert saved.token_hash == token_digest(body["token"])
    assert body["token"] != saved.token_hash

    invitations = client.get("/admin/invitations", headers=headers)
    assert invitations.status_code == 200
    assert len(invitations.json()) == 1
    assert "token" not in invitations.json()[0]
    assert body["token"] not in invitations.text
    assert client.get("/admin/users", headers=headers).json()[0]["role"] == "ADMIN"


def test_invited_agent_can_activate_and_login(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    invitation = invite(client, headers, "tech@example.com", role="AGENT").json()
    response = accept(client, invitation["token"])
    assert response.status_code == 201
    assert response.json()["email"] == "tech@example.com"
    assert response.json()["role"] == "AGENT"
    assert "password_hash" not in response.text
    logged_in = client.post("/auth/login", data={"username": "tech@example.com", "password": PASSWORD})
    assert logged_in.status_code == 200
    user = db.scalar(select(User).where(User.email == "tech@example.com"))
    assert user is not None and user.role == UserRole.AGENT
    assert accept(client, invitation["token"]).status_code == 400


def test_cannot_invite_admin_or_inject_unknown_fields(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    assert invite(client, headers, "admin2@example.com", role="ADMIN").status_code == 422
    response = client.post(
        "/admin/invitations",
        headers=headers,
        json={"email": "admin2@example.com", "role": "USER", "is_superuser": True},
    )
    assert response.status_code == 422


def test_reissue_revokes_first_code(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    old = invite(client, headers, "same@example.com").json()["token"]
    new = invite(client, headers, "same@example.com").json()["token"]
    assert old != new
    assert accept(client, old).status_code == 400
    assert accept(client, new).status_code == 201


def test_expired_invalid_and_weak_password_rejected(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    invitation = invite(client, headers, "expiry@example.com").json()
    assert accept(client, "x" * 43).status_code == 400
    assert accept(client, invitation["token"], "short").status_code == 422
    assert accept(client, invitation["token"], "ThisPasswordIsPlainAndWeak").status_code == 422
    saved = db.scalar(select(UserInvitation).where(UserInvitation.id == invitation["id"]))
    saved.expires_at = now_utc() - timedelta(minutes=1)
    db.commit()
    assert accept(client, invitation["token"]).status_code == 400
    assert db.scalar(select(User).where(User.email == "expiry@example.com")) is None


def test_duplicate_existing_account_cannot_be_invited(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    assert invite(client, headers, "root@example.com").status_code == 409


def test_invitation_audit_does_not_expose_secret(client: TestClient, db: Session) -> None:
    headers = admin_headers(client, db)
    raw_token = invite(client, headers, "audited@example.com").json()["token"]
    assert accept(client, raw_token).status_code == 201
    rows = list(db.scalars(select(SecurityAuditLog)))
    invitation_events = [row for row in rows if row.event_type.startswith("INVITATION_")]
    assert {row.event_type for row in invitation_events} == {"INVITATION_CREATED", "INVITATION_ACCEPTED"}
    assert raw_token not in repr([(row.path, row.details, row.user_agent) for row in rows])
    assert PASSWORD not in repr([(row.path, row.details) for row in rows])


def test_production_disables_public_registration_without_disabling_invites(
    client: TestClient, db: Session, monkeypatch
) -> None:
    headers = admin_headers(client, db)
    monkeypatch.setattr(settings, "app_env", "production")
    response = client.post("/auth/register", json={"email": "public@example.com", "password": PASSWORD})
    assert response.status_code == 403
    assert db.scalar(select(User).where(User.email == "public@example.com")) is None
    issued = invite(client, headers, "invited@example.com").json()
    assert accept(client, issued["token"]).status_code == 201


def test_bootstrap_never_promotes_a_preexisting_regular_account(db: Session) -> None:
    db.add(User(email="occupied@example.com", role=UserRole.USER, password_hash=hash_password(PASSWORD)))
    db.commit()

    with pytest.raises(InitialAdminConfigurationError, match="non-administrator"):
        ensure_initial_admin(db, email="occupied@example.com", password=ADMIN_PASSWORD)

    persisted = db.scalar(select(User).where(User.email == "occupied@example.com"))
    assert persisted is not None and persisted.role == UserRole.USER
