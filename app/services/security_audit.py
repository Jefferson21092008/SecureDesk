from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.rate_limit import client_ip
from app.models.security_audit import SecurityAuditLog


class SecurityEventType(str, Enum):
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    FORBIDDEN_ACCESS = "FORBIDDEN_ACCESS"


def _clean_user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    if not value:
        return None
    return value[:512]


def add_security_event(
    db: Session,
    request: Request,
    event_type: SecurityEventType | str,
    *,
    actor_id: int | None = None,
    status_code: int | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityAuditLog:
    event = SecurityAuditLog(
        event_type=event_type.value if isinstance(event_type, SecurityEventType) else str(event_type),
        actor_id=actor_id,
        method=request.method[:10],
        path=request.url.path[:255],
        status_code=status_code,
        ip_address=client_ip(request)[:64],
        user_agent=_clean_user_agent(request),
        details=details,
    )
    db.add(event)
    return event


def record_security_event_detached(
    request: Request,
    event_type: SecurityEventType | str,
    *,
    actor_id: int | None = None,
    status_code: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist middleware-level audit events without changing the request result.

    The app exposes the session factory on ``app.state`` so tests can replace it
    with the same isolated SQLite session factory used by dependency overrides.
    """
    session_factory: sessionmaker[Session] = request.app.state.audit_session_factory
    try:
        with session_factory() as db:
            add_security_event(
                db,
                request,
                event_type,
                actor_id=actor_id,
                status_code=status_code,
                details=details,
            )
            db.commit()
    except SQLAlchemyError:
        # Audit persistence must not replace the original API response with a 500.
        # Database observability/alerting can surface this separately in production.
        return
