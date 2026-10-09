from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models.user import User, UserRole
from app.repositories import invitations as repository
from app.schemas.auth import UserRead
from app.schemas.invitation import InvitationCreate, InvitationCreated, InvitationRead
from app.services.invitations import create_invitation
from app.services.security_audit import SecurityEventType, add_security_event

router = APIRouter()


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can manage users")
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    del admin
    return repository.list_users(db)


@router.get("/invitations", response_model=list[InvitationRead])
def list_invitations(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    return repository.list_invitations(db)


@router.post("/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
def invite_user(
    data: InvitationCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    invitation, raw_token = create_invitation(db, data=data, created_by_id=admin.id)
    add_security_event(
        db,
        request,
        SecurityEventType.INVITATION_CREATED,
        actor_id=admin.id,
        status_code=status.HTTP_201_CREATED,
        details={"invitation_id": invitation.id, "role": invitation.role.value},
    )
    db.commit()
    db.refresh(invitation)
    return InvitationCreated(
        **InvitationRead.model_validate(invitation).model_dump(),
        token=raw_token,
    )
