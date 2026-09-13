from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.services.sla import SLAStatus, calculate_sla_status, get_sla_target_hours

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.category import Category
    from app.models.comment import Comment
    from app.models.department import Department
    from app.models.ticket_history import TicketHistory
    from app.models.user import User


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(default=TicketStatus.OPEN, index=True)
    priority: Mapped[TicketPriority] = mapped_column(default=TicketPriority.MEDIUM, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    owner: Mapped["User"] = relationship(
        back_populates="tickets",
        foreign_keys=[owner_id],
    )
    department: Mapped["Department | None"] = relationship(back_populates="tickets")
    category: Mapped["Category | None"] = relationship(back_populates="tickets")
    assigned_agent: Mapped["User | None"] = relationship(
        back_populates="assigned_tickets",
        foreign_keys=[assigned_agent_id],
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    history: Mapped[list["TicketHistory"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    @property
    def sla_target_hours(self) -> int:
        return get_sla_target_hours(self.priority)

    @property
    def sla_status(self) -> SLAStatus:
        return calculate_sla_status(self.sla_due_at, closed_at=self.closed_at)

