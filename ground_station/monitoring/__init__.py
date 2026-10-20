"""NEXUS Ground Station Deterministic Monitoring Package.

Provides autonomous background monitoring, durable incident persistence,
conservative operational rules, and status reporting.
"""

from .models import (
    DataSourceHealth,
    DataSourceStatus,
    EvaluationReport,
    Incident,
    IncidentSeverity,
    IncidentState,
    IncidentTransition,
    MonitorStatus,
)
from .rules import (
    DHTInvalidReadingRule,
    DeviceRebootRule,
    ExecutiveFailureRule,
    MonitoringRule,
    RuleEvaluationResult,
    TelemetryFreshnessRule,
)
from .service import MonitoringConfig, MonitoringService
from .store import IncidentStorageError, IncidentStore

__all__ = [
    "DataSourceHealth",
    "DataSourceStatus",
    "EvaluationReport",
    "Incident",
    "IncidentSeverity",
    "IncidentState",
    "IncidentTransition",
    "IncidentStorageError",
    "IncidentStore",
    "MonitorStatus",
    "MonitoringConfig",
    "MonitoringRule",
    "MonitoringService",
    "RuleEvaluationResult",
    "TelemetryFreshnessRule",
    "DHTInvalidReadingRule",
    "ExecutiveFailureRule",
    "DeviceRebootRule",
]
