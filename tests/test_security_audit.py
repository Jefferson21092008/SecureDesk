from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.security_audit import SecurityAuditLog
from app.models.user import User, UserRole
from app.services.security_audit import SecurityEventType

PASSWORD = "StrongPass123!"


def register(client: TestClient, email: str, *, user_agent: str | None = None):
    headers = {"User-Agent": user_agent} if user_agent else None
    return client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD},
        headers=headers,
    )


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def token_for(client: TestClient, email: str) -> str:
    response = login(client, email)
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def promote(db: Session, email: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def events(db: Session, event_type: SecurityEventType) -> list[SecurityAuditLog]:
    return list(
        db.scalars(
            select(SecurityAuditLog)
            .where(SecurityAuditLog.event_type == event_type.value)
            .order_by(SecurityAuditLog.id.asc())
        )
    )


def test_registration_creates_security_audit_event(client: TestClient, db: Session) -> None:
    response = register(client, "audit-register@example.com", user_agent="SecureDesk-Test-Agent/1.0")

    assert response.status_code == 201
    event = events(db, SecurityEventType.ACCOUNT_CREATED)[0]
    assert event.actor_id == response.json()["id"]
    assert event.method == "POST"
    assert event.path == "/auth/register"
    assert event.status_code == 201
    assert event.ip_address
    assert event.user_agent == "SecureDesk-Test-Agent/1.0"
    assert event.details == {"role": "USER"}


def test_successful_login_is_audited(client: TestClient, db: Session) -> None:
    email = "audit-login-success@example.com"
    assert register(client, email).status_code == 201

    response = login(client, email)

    assert response.status_code == 200
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    event = events(db, SecurityEventType.LOGIN_SUCCESS)[0]
    assert event.actor_id == user.id
    assert event.path == "/auth/login"
    assert event.status_code == 200


def test_failed_login_is_audited_without_revealing_account_to_client(client: TestClient, db: Session) -> None:
    email = "audit-login-failed@example.com"
    assert register(client, email).status_code == 201

    response = login(client, email, "WrongPass123!")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    event = events(db, SecurityEventType.LOGIN_FAILED)[0]
    assert event.status_code == 401
    assert event.details is not None
    assert event.details["reason"] == "invalid_credentials"
    assert event.details["identifier_hash"] != email


def test_logout_records_revoked_session_identifier(client: TestClient, db: Session) -> None:
    email = "audit-logout@example.com"
    assert register(client, email).status_code == 201
    token = token_for(client, email)

    response = client.post("/auth/logout", headers=auth_headers(token))

    assert response.status_code == 204
    event = events(db, SecurityEventType.LOGOUT)[0]
    assert event.actor_id is not None
    assert event.status_code == 204
    assert event.details is not None
    assert event.details["revoked_jti"]
    assert event.details["revoked_jti"] != token


def test_audit_log_does_not_store_password_or_raw_bearer_token(client: TestClient, db: Session) -> None:
    email = "audit-secrets@example.com"
    secret_password = "DoNotLogThisPassword123!"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": secret_password},
    )
    assert response.status_code == 201

    failed = client.post(
        "/auth/login",
        data={"username": email, "password": "AlsoDoNotLogThis!"},
    )
    assert failed.status_code == 401

    success = client.post(
        "/auth/login",
        data={"username": email, "password": secret_password},
    )
    assert success.status_code == 200
    token = success.json()["access_token"]
    assert client.post("/auth/logout", headers=auth_headers(token)).status_code == 204

    rows = list(db.scalars(select(SecurityAuditLog)))
    serialized = "\n".join(
        f"{row.event_type}|{row.path}|{row.user_agent}|{row.details}" for row in rows
    )
    assert secret_password not in serialized
    assert "AlsoDoNotLogThis!" not in serialized
    assert token not in serialized


def test_unauthenticated_access_is_audited(client: TestClient, db: Session) -> None:
    response = client.get("/tickets")

    assert response.status_code == 401
    event = events(db, SecurityEventType.UNAUTHORIZED_ACCESS)[0]
    assert event.actor_id is None
    assert event.path == "/tickets"
    assert event.status_code == 401


def test_forbidden_access_is_audited_with_actor(client: TestClient, db: Session) -> None:
    email = "audit-forbidden@example.com"
    register_response = register(client, email)
    user_id = register_response.json()["id"]
    token = token_for(client, email)

    response = client.post("/tickets/999/close", headers=auth_headers(token))

    assert response.status_code == 403
    event = events(db, SecurityEventType.FORBIDDEN_ACCESS)[0]
    assert event.actor_id == user_id
    assert event.path == "/tickets/999/close"
    assert event.status_code == 403


def test_global_rate_limit_rejection_is_audited(client: TestClient, db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 60)

    assert client.get("/tickets").status_code == 401
    blocked = client.get("/tickets")

    assert blocked.status_code == 429
    rate_events = events(db, SecurityEventType.RATE_LIMIT_EXCEEDED)
    assert rate_events[-1].details == {"scope": "api_global", "retry_after": 60}
    assert rate_events[-1].status_code == 429


def test_auth_endpoint_rate_limit_rejection_is_audited(client: TestClient, db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "register_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60)

    assert register(client, "audit-rate-one@example.com").status_code == 201
    blocked = register(client, "audit-rate-two@example.com")

    assert blocked.status_code == 429
    rate_events = events(db, SecurityEventType.RATE_LIMIT_EXCEEDED)
    assert rate_events[-1].details == {"scope": "register", "retry_after": 60}


def test_security_audit_endpoint_requires_admin(client: TestClient) -> None:
    email = "audit-user@example.com"
    assert register(client, email).status_code == 201
    token = token_for(client, email)

    response = client.get("/security/audit", headers=auth_headers(token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Only admins can view security audit logs"


def test_admin_can_filter_and_paginate_security_audit(client: TestClient, db: Session) -> None:
    admin_email = "audit-admin@example.com"
    assert register(client, admin_email).status_code == 201
    promote(db, admin_email, UserRole.ADMIN)
    admin_token = token_for(client, admin_email)

    target_email = "audit-target@example.com"
    assert register(client, target_email).status_code == 201
    assert login(client, target_email, "WrongPass123!").status_code == 401
    assert login(client, target_email, "WrongPass456!").status_code == 401

    response = client.get(
        "/security/audit?event_type=LOGIN_FAILED&page=1&page_size=1",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["total"] == 2
    assert body["pages"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["event_type"] == "LOGIN_FAILED"


def test_security_audit_log_is_read_only_through_api(client: TestClient, db: Session) -> None:
    admin_email = "audit-readonly-admin@example.com"
    assert register(client, admin_email).status_code == 201
    promote(db, admin_email, UserRole.ADMIN)
    token = token_for(client, admin_email)
    headers = auth_headers(token)

    assert client.post("/security/audit", headers=headers, json={}).status_code == 405
    assert client.patch("/security/audit/1", headers=headers, json={}).status_code == 404
    assert client.delete("/security/audit/1", headers=headers).status_code == 404
