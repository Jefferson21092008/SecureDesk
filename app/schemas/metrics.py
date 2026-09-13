from enum import Enum

from pydantic import BaseModel


class MetricsScope(str, Enum):
    OWN = "OWN"
    GLOBAL = "GLOBAL"


class TicketStatusCounts(BaseModel):
    open: int
    in_progress: int
    closed: int


class TicketPriorityCounts(BaseModel):
    low: int
    medium: int
    high: int


class TicketMetricsOverview(BaseModel):
    scope: MetricsScope
    total: int
    by_status: TicketStatusCounts
    by_priority: TicketPriorityCounts
