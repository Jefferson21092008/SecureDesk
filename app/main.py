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
from app.core.openapi import (
    API_DESCRIPTION,
    API_VERSION,
    OPENAPI_TAGS,
    SWAGGER_UI_PARAMETERS,
    operation_id_from_route_name,
)
from app.core.rate_limit import client_ip, rate_limiter
from app.db import SessionLocal
from app.schemas.system import APIInfo, HealthResponse
from app.services.security_audit import SecurityEventType, record_security_event_detached

app = FastAPI(
    title=f"{settings.app_name} API",
    summary="Secure IT service desk API",
    description=API_DESCRIPTION,
    version=API_VERSION,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
    generate_unique_id_function=operation_id_from_route_name,
)
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


app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(categories_router, prefix="/categories", tags=["Categories"])
app.include_router(departments_router, prefix="/departments", tags=["Departments"])
app.include_router(assignment_router, prefix="/tickets", tags=["Ticket Assignment"])
app.include_router(tickets_router, prefix="/tickets", tags=["Tickets"])
app.include_router(attachments_router, prefix="/tickets", tags=["Attachments"])
app.include_router(comments_router, prefix="/tickets", tags=["Comments"])
app.include_router(history_router, prefix="/tickets", tags=["History"])
app.include_router(lifecycle_router, prefix="/tickets", tags=["Lifecycle"])
app.include_router(metrics_router, prefix="/metrics", tags=["Metrics"])
app.include_router(security_audit_router, prefix="/security", tags=["Security Audit"])


@app.get(
    "/",
    response_model=APIInfo,
    tags=["System"],
    summary="Discover the API",
    description="Returns stable links to the interactive documentation, OpenAPI schema and health endpoint.",
)
def api_info() -> APIInfo:
    return APIInfo(
        name=f"{settings.app_name} API",
        version=API_VERSION,
        docs="/docs",
        redoc="/redoc",
        openapi="/openapi.json",
        health="/health",
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Check API health",
    description="Lightweight liveness endpoint used by Docker health checks and external monitoring.",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
