from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import SessionLocal
from app.models.user import User, UserRole
from app.schemas.auth import UserCreate


def ensure_initial_admin(db: Session, *, email: str, password: str) -> User:
    data = UserCreate(email=email, password=password)
    user = db.scalar(select(User).where(User.email == data.email))

    if user is None:
        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            role=UserRole.ADMIN,
        )
        db.add(user)
    elif user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN

    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")

    if not email and not password:
        print("Initial admin bootstrap skipped: credentials are not configured.")
        return
    if not email or not password:
        raise SystemExit("INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD must be configured together")

    with SessionLocal() as db:
        admin = ensure_initial_admin(db, email=email, password=password)

    print(f"Initial admin ready: {admin.email}")


if __name__ == "__main__":
    main()
