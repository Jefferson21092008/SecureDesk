"""Contract tests for request IDs and privacy-conscious HTTP diagnostics."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.observability import REQUEST_ID_HEADER, http_logger
from app.main import app


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _is_uuid4(value: str) -> bool:
    parsed = UUID(value)
    return parsed.version == 4 and str(parsed) == value


def test_health_returns_server_generated_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "attacker-supplied"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert _is_uuid4(response.headers[REQUEST_ID_HEADER])
    assert response.headers[REQUEST_ID_HEADER] != "attacker-supplied"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_request_ids_differ_across_requests(client: TestClient) -> None:
    first = client.get("/health")
    second = client.get("/health")
    assert _is_uuid4(first.headers[REQUEST_ID_HEADER])
    assert _is_uuid4(second.headers[REQUEST_ID_HEADER])
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


def test_security_and_not_found_responses_have_request_id(client: TestClient) -> None:
    unauthorized = client.get("/admin/users")
    not_found = client.get("/no-such-endpoint")
    assert unauthorized.status_code == 401
    assert not_found.status_code == 404
    assert _is_uuid4(unauthorized.headers[REQUEST_ID_HEADER])
    assert _is_uuid4(not_found.headers[REQUEST_ID_HEADER])


def test_global_rate_limit_429_retains_headers_and_request_id(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1)
    allowed = client.get("/")
    denied = client.get("/")
    assert allowed.status_code == 200
    assert denied.status_code == 429
    assert denied.headers["Retry-After"]
    assert denied.headers["X-RateLimit-Remaining"] == "0"
    assert _is_uuid4(denied.headers[REQUEST_ID_HEADER])
    assert denied.headers["X-Frame-Options"] == "DENY"


def test_structured_logs_correlate_and_redact_client_data(client: TestClient) -> None:
    capture = _LogCapture()
    http_logger.addHandler(capture)
    try:
        secret = "never-log-this-token-value"
        response = client.get(
            f"/health?token={secret}",
            headers={"Authorization": f"Bearer {secret}", "X-Request-ID": secret},
        )
        unmatched = client.get(f"/no-route/{secret}?password={secret}")
        assert response.status_code == 200
        assert unmatched.status_code == 404
        assert len(capture.messages) == 2
        entry = json.loads(capture.messages[0])
        assert entry == {
            "event": "http_request",
            "request_id": response.headers[REQUEST_ID_HEADER],
            "method": "GET",
            "route": "/health",
            "status_code": 200,
            "duration_ms": entry["duration_ms"],
        }
        assert entry["duration_ms"] >= 0
        missing_entry = json.loads(capture.messages[1])
        assert missing_entry["route"] == "<unmatched>"
        assert missing_entry["request_id"] == unmatched.headers[REQUEST_ID_HEADER]
        assert secret not in "".join(capture.messages)
    finally:
        http_logger.removeHandler(capture)


def test_unhandled_error_returns_safe_500_with_correlated_log(monkeypatch) -> None:
    from app.core.rate_limit import rate_limiter

    def fail_consume(*_args, **_kwargs):
        raise RuntimeError("sensitive-database-url=postgresql://secret-user:secret-password@example")

    monkeypatch.setattr(rate_limiter, "consume", fail_consume)
    capture = _LogCapture()
    http_logger.addHandler(capture)
    try:
        # ServerErrorMiddleware still re-raises after sending the response;
        # disable the TestClient re-raise to inspect the real HTTP 500 payload.
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/?password=this-is-secret")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert _is_uuid4(response.headers[REQUEST_ID_HEADER])
        assert len(capture.messages) == 1
        record = json.loads(capture.messages[0])
        assert record["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert record["status_code"] == 500
        assert record["error_type"] in {"RuntimeError", "ExceptionGroup"}
        assert "secret-password" not in str(response.content)
        assert "secret-password" not in "".join(capture.messages)
    finally:
        http_logger.removeHandler(capture)


def test_concurrent_requests_do_not_reuse_request_ids() -> None:
    def fetch_id(_index: int) -> str:
        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        return response.headers[REQUEST_ID_HEADER]

    with ThreadPoolExecutor(max_workers=6) as pool:
        identifiers = list(pool.map(fetch_id, range(12)))
    assert len(set(identifiers)) == len(identifiers)
    assert all(_is_uuid4(value) for value in identifiers)
