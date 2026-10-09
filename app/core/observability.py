"""Minimal, privacy-conscious HTTP observability for SecureDesk.

Log only server-generated metadata, never raw URLs, query strings, request
bodies, headers, IPs, credentials, exception messages, or tracebacks.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from time import perf_counter
from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("securedesk_request_id", default=None)

# A dedicated stderr handler keeps INFO logs visible under both Uvicorn and
# local development, regardless of the root logger's level/configuration.
http_logger = logging.getLogger("securedesk.http")
http_logger.setLevel(logging.INFO)
if not http_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    http_logger.addHandler(handler)
http_logger.propagate = False


def new_request_id(request: Request) -> Token[str | None]:
    """Create a trusted identifier; do not accept user-provided ID headers."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    return _request_id.set(request_id)


def current_request_id() -> str | None:
    """Get the ID in async request context, for later instrumentation."""
    return _request_id.get()


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def request_route_pattern(request: Request) -> str:
    """The registered route template, never the path or query from the client."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return route_path if isinstance(route_path, str) else "<unmatched>"


def log_http_request(request: Request, *, status_code: int, started_at: float, error: Exception | None = None) -> None:
    """Write a single JSON log record with only allowlisted fields."""
    method = request.method if request.method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} else "OTHER"
    data: dict[str, str | int | float] = {
        "event": "http_request",
        "request_id": request.state.request_id,
        "method": method,
        "route": request_route_pattern(request),
        "status_code": status_code,
        "duration_ms": round(max(0.0, perf_counter() - started_at) * 1000, 2),
    }
    if error is not None:
        # Exception *messages* can include SQL, credentials or customer data.
        # Class name is defined by code and is safe to record.
        data["error_type"] = type(error).__name__
    http_logger.info(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
