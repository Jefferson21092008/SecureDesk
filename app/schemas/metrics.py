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


class SLAStatusCounts(BaseModel):
    on_track: int
    met: int
    breached: int


class SLAClosedMetrics(BaseModel):
    total: int
    met: int
    breached: int
    compliance_rate_percent: float | None


class TicketSLAMetrics(BaseModel):
    scope: MetricsScope
    total: int
    by_sla_status: SLAStatusCounts
    closed: SLAClosedMetrics
    average_resolution_hours: float | None


class DepartmentMetricItem(BaseModel):
    department_id: int | None
    department_name: str | None
    total: int


class CategoryMetricItem(BaseModel):
    category_id: int | None
    category_name: str | None
    total: int


class AgentMetricItem(BaseModel):
    agent_id: int | None
    agent_email: str | None
    total: int


class TicketBreakdownMetrics(BaseModel):
    scope: MetricsScope
    by_department: list[DepartmentMetricItem]
    by_category: list[CategoryMetricItem]
    by_agent: list[AgentMetricItem]
