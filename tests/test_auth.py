from fastapi.testclient import TestClient


def register(client: TestClient, email: str = "user@example.com", password: str = "StrongPass123!"):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_register_creates_regular_user(client: TestClient) -> None:
    response = register(client)

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"
    assert response.json()["role"] == "USER"
    assert "password" not in response.json()
    assert "password_hash" not in response.json()


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    assert register(client).status_code == 201

    response = register(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_login_uses_oauth2_form_and_returns_bearer_token(client: TestClient) -> None:
    assert register(client).status_code == 201

    response = client.post(
        "/auth/login",
        data={"username": "user@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_invalid_credentials(client: TestClient) -> None:
    assert register(client).status_code == 201

    response = client.post(
        "/auth/login",
        data={"username": "user@example.com", "password": "WrongPass123!"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
