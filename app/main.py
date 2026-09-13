from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.assignment import router as assignment_router
from app.api.attachments import router as attachments_router
from app.api.auth import router as auth_router
from app.api.categories import router as categories_router
from app.api.comments import router as comments_router
from app.api.departments import router as departments_router
from app.api.history import router as history_router
from app.api.lifecycle import router as lifecycle_router
from app.api.metrics import router as metrics_router
from app.api.security_audit import router as security_audit_router
from app.api.tickets import router as tickets_router
from app.core.config import settings
from app.core.rate_limit import client_ip, rate_limiter
from app.db import SessionLocal
from app.services.security_audit import SecurityEventType, record_security_event_detached

app = FastAPI(title=settings.app_name, version="0.4.0")
app.state.audit_session_factory = SessionLocal


def _apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.middleware("http")
async def enforce_api_rate_limit(request: Request, call_next):
    if request.url.path == "/health":
        response = await call_next(request)
        return _apply_security_headers(response)

    decision = rate_limiter.consume(
        key=f"api:{client_ip(request)}",
        limit=settings.api_rate_limit_requests,
        window_seconds=settings.api_rate_limit_window_seconds,
    )
    if not decision.allowed:
        record_security_event_detached(
            request,
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"scope": "api_global", "retry_after": decision.retry_after},
        )
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests"},
            headers={
                "Retry-After": str(decision.retry_after),
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": "0",
            },
        )
        return _apply_security_headers(response)

    response = await call_next(request)

    # Login failures already record a richer LOGIN_FAILED event in the auth route.
    # Other 401/403 responses are useful authorization signals for defenders.
    if request.url.path != "/auth/login" and response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }:
        event_type = (
            SecurityEventType.UNAUTHORIZED_ACCESS
            if response.status_code == status.HTTP_401_UNAUTHORIZED
            else SecurityEventType.FORBIDDEN_ACCESS
        )
        record_security_event_detached(
            request,
            event_type,
            actor_id=getattr(request.state, "audit_actor_id", None),
            status_code=response.status_code,
        )

    if "X-RateLimit-Limit" not in response.headers:
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
    if "X-RateLimit-Remaining" not in response.headers:
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    if request.url.path.startswith(("/auth", "/security")):
        response.headers.setdefault("Cache-Control", "no-store")
    return _apply_security_headers(response)


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(categories_router, prefix="/categories", tags=["categories"])
app.include_router(departments_router, prefix="/departments", tags=["departments"])
app.include_router(assignment_router, prefix="/tickets", tags=["assignment"])
app.include_router(tickets_router, prefix="/tickets", tags=["tickets"])
app.include_router(attachments_router, prefix="/tickets", tags=["attachments"])
app.include_router(comments_router, prefix="/tickets", tags=["comments"])
app.include_router(history_router, prefix="/tickets", tags=["history"])
app.include_router(lifecycle_router, prefix="/tickets", tags=["lifecycle"])
app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
app.include_router(security_audit_router, prefix="/security", tags=["security"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
