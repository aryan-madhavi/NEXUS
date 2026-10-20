"""NEXUS Incident and Monitoring Data Models.

Defines typed, immutable representations for:
- Incidents and their lifecycle states (OPEN, RESOLVED)
- Severity levels (INFO, WARNING, CRITICAL)
- Durable incident transition records
- Data-source health status
- Overall monitor status and evaluation reports
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class IncidentState(str, enum.Enum):
    """Lifecycle state of an incident."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class IncidentSeverity(str, enum.Enum):
    """Operational severity classification."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DataSourceStatus(str, enum.Enum):
    """Status of the underlying telemetry data source (InfluxDB)."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class IncidentTransition:
    """A durable record of an incident state change."""

    transition_id: Optional[int]
    incident_id: str
    from_state: Optional[str]
    to_state: str
    timestamp: datetime
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize transition to JSON-compatible dictionary."""
        return {
            "transition_id": self.transition_id,
            "incident_id": self.incident_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class Incident:
    """A durable operational incident record.

    Incident deduplication semantics:
    - At most ONE incident per (device_id, rule_id) can be in the OPEN state at any time.
    - Ongoing evaluations of a confirmed condition update last_evaluated_at but do NOT
      create duplicate active incidents.
    - When a condition clears, the incident transitions to RESOLVED with resolution evidence.
    - If the condition reappears subsequently, a NEW incident is created with a distinct
      incident_id and an OPEN transition.
    """

    incident_id: str
    device_id: str
    rule_id: str
    severity: IncidentSeverity
    state: IncidentState
    summary: str
    opened_at: datetime
    resolved_at: Optional[datetime] = None
    last_evaluated_at: Optional[datetime] = None
    open_evidence: Dict[str, Any] = field(default_factory=dict)
    resolve_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize incident to JSON-compatible dictionary."""
        return {
            "incident_id": self.incident_id,
            "device_id": self.device_id,
            "rule_id": self.rule_id,
            "severity": self.severity.value if isinstance(self.severity, IncidentSeverity) else str(self.severity),
            "state": self.state.value if isinstance(self.state, IncidentState) else str(self.state),
            "summary": self.summary,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "open_evidence": dict(self.open_evidence),
            "resolve_evidence": dict(self.resolve_evidence) if self.resolve_evidence else None,
        }


@dataclass(frozen=True)
class DataSourceHealth:
    """Telemetry data source health assessment."""

    status: DataSourceStatus
    last_check_at: datetime
    response_time_ms: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "status": self.status.value if isinstance(self.status, DataSourceStatus) else str(self.status),
            "last_check_at": self.last_check_at.isoformat(),
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
        }


@dataclass
class MonitorStatus:
    """Status snapshot of the background monitoring service."""

    is_running: bool
    data_source: DataSourceHealth
    last_evaluated_at: Optional[datetime]
    evaluation_count: int
    active_incident_count: int
    monitored_devices: List[str]
    current_interval_sec: float
    rules_registered: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize monitor status to dictionary."""
        return {
            "is_running": self.is_running,
            "data_source": self.data_source.to_dict(),
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "evaluation_count": self.evaluation_count,
            "active_incident_count": self.active_incident_count,
            "monitored_devices": list(self.monitored_devices),
            "current_interval_sec": self.current_interval_sec,
            "rules_registered": list(self.rules_registered),
        }


@dataclass
class EvaluationReport:
    """Report produced by an evaluation pass across all monitored devices and rules."""

    timestamp: datetime
    devices_evaluated: List[str]
    newly_opened: List[Incident] = field(default_factory=list)
    resolved: List[Incident] = field(default_factory=list)
    ongoing: List[Incident] = field(default_factory=list)
    data_source: Optional[DataSourceHealth] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize evaluation report to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "devices_evaluated": list(self.devices_evaluated),
            "newly_opened": [inc.to_dict() for inc in self.newly_opened],
            "resolved": [inc.to_dict() for inc in self.resolved],
            "ongoing": [inc.to_dict() for inc in self.ongoing],
            "data_source": self.data_source.to_dict() if self.data_source else None,
            "duration_ms": self.duration_ms,
        }


def utc_now() -> datetime:
    """Helper to return current time in timezone-aware UTC."""
    return datetime.now(timezone.utc)
