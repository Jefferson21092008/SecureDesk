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


def test_me_returns_authenticated_user(client: TestClient) -> None:
    assert register(client, "me@example.com").status_code == 201
    login_response = client.post(
        "/auth/login",
        data={"username": "me@example.com", "password": "StrongPass123!"},
    )
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
    assert response.json()["role"] == "USER"


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
