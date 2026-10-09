"""Issue and redeem one-time invitation codes (never persist or log plaintext codes)."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.invitation import UserInvitation
from app.models.user import User
from app.repositories import invitations as repository
from app.schemas.auth import UserCreate
from app.schemas.invitation import InvitationCreate

INVITATION_VALIDITY_HOURS = 48


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_invitation(db: Session, *, data: InvitationCreate, created_by_id: int) -> tuple[UserInvitation, str]:
    if repository.find_user_by_email(db, str(data.email)) is not None:
        raise HTTPException(status_code=409, detail="Account already exists")

    now = now_utc()
    # Reissuing an invitation invalidates earlier, unredeemed codes for that address.
    repository.revoke_pending_invitations(db, str(data.email), now)
    raw_token = token_urlsafe(32)
    invitation = UserInvitation(
        email=str(data.email),
        role=data.role,
        token_hash=token_digest(raw_token),
        created_by_id=created_by_id,
        expires_at=now + timedelta(hours=INVITATION_VALIDITY_HOURS),
    )
    db.add(invitation)
    db.flush()
    return invitation, raw_token


def accept_invitation(db: Session, *, token: str, password: str) -> tuple[User, UserInvitation]:
    invitation = repository.find_invitation_by_hash(db, token_digest(token))
    if invitation is None:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    now = now_utc()
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    try:
        validated = UserCreate(email=invitation.email, password=password)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Password does not meet security requirements") from None

    if repository.find_user_by_email(db, str(validated.email)) is not None:
        raise HTTPException(status_code=409, detail="Account already exists")

    # Atomic UPDATE ensures two simultaneous requests cannot redeem the same token.
    if not repository.redeem_invitation_once(db, invitation.id, now):
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    user = User(email=str(validated.email), password_hash=hash_password(validated.password), role=invitation.role)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already exists") from None
    return user, invitation
