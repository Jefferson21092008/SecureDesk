from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.invitation import UserInvitation
from app.models.user import User


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def find_invitation_by_hash(db: Session, digest: str) -> UserInvitation | None:
    return db.scalar(select(UserInvitation).where(UserInvitation.token_hash == digest))


def list_invitations(db: Session, *, limit: int = 100) -> list[UserInvitation]:
    return list(db.scalars(select(UserInvitation).order_by(UserInvitation.id.desc()).limit(limit)))


def list_users(db: Session, *, limit: int = 100) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id.asc()).limit(limit)))


def revoke_pending_invitations(db: Session, email: str, now: datetime) -> None:
    db.execute(
        update(UserInvitation)
        .where(
            UserInvitation.email == email,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


def redeem_invitation_once(db: Session, invitation_id: int, now: datetime) -> bool:
    result = db.execute(
        update(UserInvitation)
        .where(
            UserInvitation.id == invitation_id,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
            UserInvitation.expires_at > now,
        )
        .values(accepted_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1
