from dataclasses import dataclass

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import (
    client_ip,
    identifier_digest,
    rate_limit_exception,
    rate_limiter,
)
from app.core.security import AccessTokenClaims, create_access_token, decode_access_token, hash_password, verify_password
from app.db import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.schemas.auth import Token, UserCreate, UserRead
from app.services.security_audit import SecurityEventType, add_security_event

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
email_adapter = TypeAdapter(EmailStr)


@dataclass(frozen=True)
class AuthContext:
    user: User
    claims: AccessTokenClaims


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _persist_auth_event(
    db: Session,
    request: Request,
    event_type: SecurityEventType,
    *,
    actor_id: int | None = None,
    status_code: int | None = None,
    details: dict[str, object] | None = None,
) -> None:
    add_security_event(
        db,
        request,
        event_type,
        actor_id=actor_id,
        status_code=status_code,
        details=details,
    )
    db.commit()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)) -> User:
    decision = rate_limiter.consume(
        key=f"auth:register:{client_ip(request)}",
        limit=settings.register_rate_limit_requests,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if not decision.allowed:
        _persist_auth_event(
            db,
            request,
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"scope": "register", "retry_after": decision.retry_after},
        )
        raise rate_limit_exception("Too many registration attempts", decision)

    existing = db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.USER,
    )
    db.add(user)
    db.flush()
    add_security_event(
        db,
        request,
        SecurityEventType.ACCOUNT_CREATED,
        actor_id=user.id,
        status_code=status.HTTP_201_CREATED,
        details={"role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    ip = client_ip(request)
    endpoint_decision = rate_limiter.consume(
        key=f"auth:login:{ip}",
        limit=settings.login_rate_limit_requests,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if not endpoint_decision.allowed:
        _persist_auth_event(
            db,
            request,
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"scope": "login_endpoint", "retry_after": endpoint_decision.retry_after},
        )
        raise rate_limit_exception("Too many login attempts", endpoint_decision)

    identifier_hash = identifier_digest(form_data.username)
    failure_key = f"auth:login-failure:{ip}:{identifier_hash}"
    failure_decision = rate_limiter.inspect(
        key=failure_key,
        limit=settings.login_failure_limit,
        window_seconds=settings.login_failure_window_seconds,
    )
    if not failure_decision.allowed:
        _persist_auth_event(
            db,
            request,
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={
                "scope": "login_failures",
                "identifier_hash": identifier_hash,
                "retry_after": failure_decision.retry_after,
            },
        )
        raise rate_limit_exception("Too many failed login attempts", failure_decision)

    try:
        email = str(email_adapter.validate_python(form_data.username)).strip().lower()
    except ValidationError:
        rate_limiter.record(failure_key, settings.login_failure_window_seconds)
        _persist_auth_event(
            db,
            request,
            SecurityEventType.LOGIN_FAILED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details={"identifier_hash": identifier_hash, "reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(form_data.password, user.password_hash):
        rate_limiter.record(failure_key, settings.login_failure_window_seconds)
        _persist_auth_event(
            db,
            request,
            SecurityEventType.LOGIN_FAILED,
            actor_id=user.id if user else None,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details={"identifier_hash": identifier_hash, "reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    rate_limiter.clear(failure_key)
    token = create_access_token(str(user.id))
    _persist_auth_event(
        db,
        request,
        SecurityEventType.LOGIN_SUCCESS,
        actor_id=user.id,
        status_code=status.HTTP_200_OK,
    )
    return Token(
        access_token=token,
        expires_in=settings.access_token_minutes * 60,
    )


def get_auth_context(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    try:
        claims = decode_access_token(token)
        if db.scalar(select(RevokedToken.id).where(RevokedToken.jti == claims.jti)) is not None:
            raise unauthorized()
        user = db.get(User, int(claims.subject))
    except HTTPException:
        raise
    except (ValueError, TypeError, jwt.InvalidTokenError):
        raise unauthorized() from None

    if not user:
        raise unauthorized()

    request.state.audit_actor_id = user.id
    return AuthContext(user=user, claims=claims)


def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    db.add(
        RevokedToken(
            jti=context.claims.jti,
            user_id=context.user.id,
            expires_at=context.claims.expires_at,
        )
    )
    add_security_event(
        db,
        request,
        SecurityEventType.LOGOUT,
        actor_id=context.user.id,
        status_code=status.HTTP_204_NO_CONTENT,
        details={"revoked_jti": context.claims.jti},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
