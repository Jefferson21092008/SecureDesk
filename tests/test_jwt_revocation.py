from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.revoked_token import RevokedToken

EMAIL = "jwt@example.com"
PASSWORD = "StrongPass123!"


def register_and_login(client: TestClient) -> str:
    response = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 201

    response = client.post(
        "/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_expiration_metadata(client: TestClient) -> None:
    response = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 201

    response = client.post(
        "/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["expires_in"] == settings.access_token_minutes * 60


def test_access_token_contains_required_identity_and_lifecycle_claims() -> None:
    token = create_access_token("123")
    claims = decode_access_token(token)

    assert claims.subject == "123"
    assert claims.jti
    assert claims.issued_at.tzinfo is not None
    assert claims.expires_at > claims.issued_at


def test_two_logins_receive_different_token_ids(client: TestClient) -> None:
    first = register_and_login(client)
    second_response = client.post(
        "/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
    )
    assert second_response.status_code == 200
    second = second_response.json()["access_token"]

    assert decode_access_token(first).jti != decode_access_token(second).jti


def test_expired_access_token_is_rejected(client: TestClient, monkeypatch) -> None:
    token = register_and_login(client)
    subject = decode_access_token(token).subject

    monkeypatch.setattr(settings, "access_token_minutes", -1)
    expired_token = create_access_token(subject)

    response = client.get("/tickets", headers=auth_headers(expired_token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_token_missing_jti_is_rejected(client: TestClient) -> None:
    token = register_and_login(client)
    subject = decode_access_token(token).subject
    now = datetime.now(timezone.utc)
    malformed = jwt.encode(
        {
            "sub": subject,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/tickets", headers=auth_headers(malformed))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_non_access_token_type_is_rejected(client: TestClient) -> None:
    token = register_and_login(client)
    claims = decode_access_token(token)
    now = datetime.now(timezone.utc)
    wrong_type = jwt.encode(
        {
            "sub": claims.subject,
            "jti": "refresh-token-test-id",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/tickets", headers=auth_headers(wrong_type))

    assert response.status_code == 401


def test_token_for_wrong_audience_is_rejected(client: TestClient) -> None:
    token = register_and_login(client)
    claims = decode_access_token(token)
    now = datetime.now(timezone.utc)
    wrong_audience = jwt.encode(
        {
            "sub": claims.subject,
            "jti": "wrong-audience-test-id",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": "another-api",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/tickets", headers=auth_headers(wrong_audience))

    assert response.status_code == 401


def test_logout_revokes_current_access_token(client: TestClient) -> None:
    token = register_and_login(client)

    before = client.get("/tickets", headers=auth_headers(token))
    logout = client.post("/auth/logout", headers=auth_headers(token))
    after = client.get("/tickets", headers=auth_headers(token))

    assert before.status_code == 200
    assert logout.status_code == 204
    assert after.status_code == 401
    assert after.json()["detail"] == "Invalid or expired token"


def test_logout_persists_only_token_identifier_not_raw_token(client: TestClient, db: Session) -> None:
    token = register_and_login(client)
    claims = decode_access_token(token)

    response = client.post("/auth/logout", headers=auth_headers(token))
    assert response.status_code == 204

    revoked = db.scalar(select(RevokedToken).where(RevokedToken.jti == claims.jti))
    assert revoked is not None
    assert revoked.jti == claims.jti
    assert revoked.jti != token
    assert revoked.user_id == int(claims.subject)


def test_revoking_one_session_does_not_revoke_another(client: TestClient) -> None:
    first = register_and_login(client)
    second_response = client.post(
        "/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
    )
    second = second_response.json()["access_token"]

    assert client.post("/auth/logout", headers=auth_headers(first)).status_code == 204

    assert client.get("/tickets", headers=auth_headers(first)).status_code == 401
    assert client.get("/tickets", headers=auth_headers(second)).status_code == 200


def test_new_login_after_logout_produces_valid_token(client: TestClient) -> None:
    first = register_and_login(client)
    assert client.post("/auth/logout", headers=auth_headers(first)).status_code == 204

    response = client.post(
        "/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
    )
    second = response.json()["access_token"]

    assert response.status_code == 200
    assert second != first
    assert client.get("/tickets", headers=auth_headers(second)).status_code == 200


def test_revoked_token_cannot_be_logged_out_twice(client: TestClient) -> None:
    token = register_and_login(client)

    assert client.post("/auth/logout", headers=auth_headers(token)).status_code == 204
    second = client.post("/auth/logout", headers=auth_headers(token))

    assert second.status_code == 401
    assert second.json()["detail"] == "Invalid or expired token"
