import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_DEVELOPMENT_JWT_SECRET, Settings
from app.models.user import User, UserRole

STRONG_PASSWORD = "StrongPass123!"


def register(client: TestClient, email: str, password: str = STRONG_PASSWORD, **extra):
    payload = {"email": email, "password": password, **extra}
    return client.post("/auth/register", json=payload)


def token(client: TestClient, email: str, password: str = STRONG_PASSWORD) -> str:
    response = client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.parametrize(
    "password",
    [
        "Short1!",
        "alllowercase123!",
        "ALLUPPERCASE123!",
        "NoDigitsHere!!",
        "NoSymbols12345",
    ],
)
def test_registration_rejects_weak_passwords(client: TestClient, password: str) -> None:
    response = register(client, "weak@example.com", password)
    assert response.status_code == 422


def test_registration_rejects_password_containing_email_identifier(client: TestClient) -> None:
    response = register(client, "jefferson@example.com", "Jefferson123!")
    assert response.status_code == 422


def test_registration_normalizes_email_and_duplicate_check_is_case_insensitive(client: TestClient) -> None:
    first = register(client, "Mixed.Case@Example.COM")
    assert first.status_code == 201
    assert first.json()["email"] == "mixed.case@example.com"

    second = register(client, "mixed.case@example.com")
    assert second.status_code == 409

    login = client.post(
        "/auth/login",
        data={"username": "MIXED.CASE@EXAMPLE.COM", "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200


def test_registration_rejects_unknown_fields(client: TestClient) -> None:
    response = register(client, "extra-register@example.com", role="ADMIN")
    assert response.status_code == 422


def test_ticket_create_rejects_mass_assignment_fields(client: TestClient) -> None:
    created_user = register(client, "strict-ticket@example.com")
    assert created_user.status_code == 201
    access_token = token(client, "strict-ticket@example.com")

    response = client.post(
        "/tickets",
        headers=auth(access_token),
        json={
            "title": "Strict input",
            "description": "Unknown server-controlled fields must be rejected.",
            "owner_id": 999,
        },
    )
    assert response.status_code == 422


def test_ticket_update_rejects_empty_and_unknown_payloads(client: TestClient) -> None:
    register(client, "strict-patch@example.com")
    access_token = token(client, "strict-patch@example.com")
    created = client.post(
        "/tickets",
        headers=auth(access_token),
        json={"title": "Patch target", "description": "A valid ticket for patch validation."},
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    empty = client.patch(f"/tickets/{ticket_id}", headers=auth(access_token), json={})
    unknown = client.patch(
        f"/tickets/{ticket_id}",
        headers=auth(access_token),
        json={"role": "ADMIN"},
    )
    assert empty.status_code == 422
    assert unknown.status_code == 422


def test_text_inputs_are_trimmed_and_blank_comments_rejected(client: TestClient) -> None:
    register(client, "trim@example.com")
    access_token = token(client, "trim@example.com")
    created = client.post(
        "/tickets",
        headers=auth(access_token),
        json={
            "title": "   Trimmed title   ",
            "description": "   Trimmed description   ",
        },
    )
    assert created.status_code == 201
    assert created.json()["title"] == "Trimmed title"
    assert created.json()["description"] == "Trimmed description"

    blank_comment = client.post(
        f"/tickets/{created.json()['id']}/comments",
        headers=auth(access_token),
        json={"content": "   \t\n  "},
    )
    assert blank_comment.status_code == 422


def test_control_characters_are_rejected(client: TestClient) -> None:
    register(client, "control@example.com")
    access_token = token(client, "control@example.com")
    response = client.post(
        "/tickets",
        headers=auth(access_token),
        json={"title": "Bad\u0000Title", "description": "Valid description"},
    )
    assert response.status_code == 422


def test_assignment_rejects_invalid_agent_id(client: TestClient, db: Session) -> None:
    registered = register(client, "admin-hardening@example.com")
    assert registered.status_code == 201
    admin = db.get(User, registered.json()["id"])
    assert admin is not None
    admin.role = UserRole.ADMIN
    db.commit()
    access_token = token(client, "admin-hardening@example.com")

    # Route validation runs before the ticket is accessed, so any positive id works here.
    response = client.patch(
        "/tickets/1/assignment",
        headers=auth(access_token),
        json={"agent_id": 0},
    )
    assert response.status_code == 422


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            jwt_secret=DEFAULT_DEVELOPMENT_JWT_SECRET,
            database_url="postgresql+psycopg://app:strong-db-password@db:5432/securedesk",
        )


def test_production_rejects_debug_and_default_database_credentials() -> None:
    strong_secret = "x" * 48
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=True,
            jwt_secret=strong_secret,
            database_url="postgresql+psycopg://app:strong-db-password@db:5432/securedesk",
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            jwt_secret=strong_secret,
            database_url="postgresql+psycopg://securedesk:securedesk@db:5432/securedesk",
        )
