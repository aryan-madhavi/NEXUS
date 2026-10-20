"""NEXUS Telemetry Analysis Package.

Provides a typed, bounded, read-only analysis and query engine over InfluxDB 2.x
telemetry data for the NEXUS ground station and monitoring layer.
"""

from .models import (
    ALLOWED_MEASUREMENTS,
    ALLOWED_SIGNALS,
    ALLOWED_TRANSPORTS,
    DEFAULT_RAW_QUERY_LIMIT,
    MAX_RAW_QUERY_LIMIT,
    AnalysisError,
    DataSourceUnavailableError,
    DeviceNotFoundError,
    FreshnessReport,
    InvalidQueryError,
    ObservationEvent,
    QueryTimeoutError,
    SignalSummary,
    TelemetryRecord,
    TransportFilter,
    TrendDirection,
    TrendSummary,
    WindowComparison,
)
from .quality import TelemetryQuality
from .statistics import TelemetryStatistics
from .telemetry_query import TelemetryQueryService

__all__ = [
    "ALLOWED_MEASUREMENTS",
    "ALLOWED_SIGNALS",
    "ALLOWED_TRANSPORTS",
    "DEFAULT_RAW_QUERY_LIMIT",
    "MAX_RAW_QUERY_LIMIT",
    "AnalysisError",
    "DataSourceUnavailableError",
    "DeviceNotFoundError",
    "FreshnessReport",
    "InvalidQueryError",
    "ObservationEvent",
    "QueryTimeoutError",
    "SignalSummary",
    "TelemetryQuality",
    "TelemetryRecord",
    "TelemetryStatistics",
    "TelemetryQueryService",
    "TransportFilter",
    "TrendDirection",
    "TrendSummary",
    "WindowComparison",
]
