from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.ticket import Ticket
    from app.models.ticket_history import TicketHistory


class UserRole(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[UserRole] = mapped_column(default=UserRole.USER)

    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="owner",
        foreign_keys="Ticket.owner_id",
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="assigned_agent",
        foreign_keys="Ticket.assigned_agent_id",
    )
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")
    history_entries: Mapped[list["TicketHistory"]] = relationship(back_populates="actor")
