from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.security_audit import SecurityAuditLog
from app.models.user import User, UserRole
from app.schemas.security_audit import SecurityAuditPage

router = APIRouter()


def require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view security audit logs",
        )


@router.get("/audit", response_model=SecurityAuditPage)
def list_security_audit_logs(
    event_type: str | None = None,
    actor_id: int | None = None,
    status_code: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SecurityAuditPage:
    require_admin(current_user)

    filters = []
    if event_type is not None:
        filters.append(SecurityAuditLog.event_type == event_type)
    if actor_id is not None:
        filters.append(SecurityAuditLog.actor_id == actor_id)
    if status_code is not None:
        filters.append(SecurityAuditLog.status_code == status_code)

    total = db.scalar(select(func.count(SecurityAuditLog.id)).where(*filters)) or 0
    offset = (page - 1) * page_size
    items = list(
        db.scalars(
            select(SecurityAuditLog)
            .where(*filters)
            .order_by(SecurityAuditLog.created_at.desc(), SecurityAuditLog.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    )

    return SecurityAuditPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )
