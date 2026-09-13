from fastapi.testclient import TestClient

from app.core.config import settings

PASSWORD = "StrongPass123!"


def register(client: TestClient, email: str) -> None:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_global_rate_limit_blocks_excess_requests(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 60)

    first = client.get("/tickets")
    second = client.get("/tickets")
    blocked = client.get("/tickets")

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many requests"
    assert blocked.headers["retry-after"] == "60"
    assert blocked.headers["x-ratelimit-limit"] == "2"
    assert blocked.headers["x-ratelimit-remaining"] == "0"


def test_global_rate_limit_recovers_after_window(client: TestClient, monkeypatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.core.rate_limit.monotonic", lambda: clock["now"])
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 10)

    assert client.get("/tickets").status_code == 401
    assert client.get("/tickets").status_code == 429

    clock["now"] += 11
    assert client.get("/tickets").status_code == 401


def test_login_endpoint_rate_limit_caps_high_volume(client: TestClient, monkeypatch) -> None:
    # Freeze the limiter clock so Retry-After is deterministic even when
    # password verification intentionally takes measurable time.
    monkeypatch.setattr("app.core.rate_limit.monotonic", lambda: 1000.0)
    monkeypatch.setattr(settings, "login_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60)

    assert login(client, "one@example.com", "wrong").status_code == 401
    assert login(client, "two@example.com", "wrong").status_code == 401

    blocked = login(client, "three@example.com", "wrong")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many login attempts"
    assert blocked.headers["retry-after"] == "60"
    assert blocked.headers["x-ratelimit-limit"] == "2"
    assert blocked.headers["x-ratelimit-remaining"] == "0"


def test_repeated_bad_passwords_block_even_correct_password(client: TestClient) -> None:
    email = "bruteforce@example.com"
    register(client, email)

    for _ in range(settings.login_failure_limit):
        response = login(client, email, "WrongPass123!")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    blocked = login(client, email, PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many failed login attempts"
    assert int(blocked.headers["retry-after"]) > 0


def test_successful_login_clears_failure_counter(client: TestClient) -> None:
    email = "reset@example.com"
    register(client, email)

    for _ in range(settings.login_failure_limit - 1):
        assert login(client, email, "WrongPass123!").status_code == 401

    assert login(client, email, PASSWORD).status_code == 200

    for _ in range(settings.login_failure_limit - 1):
        assert login(client, email, "WrongPass123!").status_code == 401

    assert login(client, email, PASSWORD).status_code == 200


def test_login_failure_window_expires(client: TestClient, monkeypatch) -> None:
    clock = {"now": 5000.0}
    monkeypatch.setattr("app.core.rate_limit.monotonic", lambda: clock["now"])
    email = "window@example.com"
    register(client, email)

    for _ in range(settings.login_failure_limit):
        assert login(client, email, "WrongPass123!").status_code == 401

    assert login(client, email, PASSWORD).status_code == 429

    clock["now"] += settings.login_failure_window_seconds + 1
    assert login(client, email, PASSWORD).status_code == 200


def test_failed_attempts_are_isolated_per_account(client: TestClient) -> None:
    attacked = "attacked@example.com"
    other = "other@example.com"
    register(client, attacked)
    register(client, other)

    for _ in range(settings.login_failure_limit):
        assert login(client, attacked, "WrongPass123!").status_code == 401

    assert login(client, attacked, PASSWORD).status_code == 429
    assert login(client, other, PASSWORD).status_code == 200


def test_registration_endpoint_is_rate_limited(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "register_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60)

    register(client, "reg-one@example.com")
    register(client, "reg-two@example.com")

    blocked = client.post(
        "/auth/register",
        json={"email": "reg-three@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many registration attempts"


def test_forwarded_for_header_cannot_bypass_client_rate_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "register_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60)

    first = client.post(
        "/auth/register",
        json={"email": "proxy-one@example.com", "password": PASSWORD},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    blocked = client.post(
        "/auth/register",
        json={"email": "proxy-two@example.com", "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.20"},
    )

    assert first.status_code == 201
    assert blocked.status_code == 429


def test_health_check_is_exempt_from_rate_limit(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1)

    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_allowed_response_exposes_rate_limit_metadata(client: TestClient) -> None:
    response = client.get("/tickets")

    assert response.status_code == 401
    assert response.headers["x-ratelimit-limit"] == str(settings.api_rate_limit_requests)
    assert response.headers["x-ratelimit-remaining"] == str(settings.api_rate_limit_requests - 1)
