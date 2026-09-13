from datetime import datetime, timedelta, timezone
from enum import Enum


class SLAStatus(str, Enum):
    ON_TRACK = "ON_TRACK"
    MET = "MET"
    BREACHED = "BREACHED"


SLA_HOURS_BY_PRIORITY = {
    "LOW": 24,
    "MEDIUM": 8,
    "HIGH": 4,
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_sla_target_hours(priority: object) -> int:
    key = getattr(priority, "value", priority)
    return SLA_HOURS_BY_PRIORITY[str(key)]


def calculate_sla_due_at(created_at: datetime, priority: object) -> datetime:
    return _as_utc(created_at) + timedelta(hours=get_sla_target_hours(priority))


def calculate_sla_status(
    sla_due_at: datetime,
    *,
    closed_at: datetime | None = None,
    now: datetime | None = None,
) -> SLAStatus:
    due_at = _as_utc(sla_due_at)

    if closed_at is not None:
        return SLAStatus.MET if _as_utc(closed_at) <= due_at else SLAStatus.BREACHED

    current_time = _as_utc(now or datetime.now(timezone.utc))
    return SLAStatus.BREACHED if current_time > due_at else SLAStatus.ON_TRACK
