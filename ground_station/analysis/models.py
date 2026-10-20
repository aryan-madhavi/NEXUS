"""NEXUS Telemetry Analysis Data Models and Validation Types.

Defines typed representations for telemetry records, aggregated statistics,
freshness audits, sequence integrity metrics, and allowlists for bounded read-only queries.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# --- Validation Regex and Constants ---

# Allowed device identifiers: 1-32 alphanumeric characters, underscores, and dashes
DEVICE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")

# Relative duration pattern: e.g. -15m, -1h, -24h, -30d
RELATIVE_DURATION_PATTERN = re.compile(r"^-[0-9]+(s|m|h|d)$")

MAX_RAW_QUERY_LIMIT = 1000
DEFAULT_RAW_QUERY_LIMIT = 100
MAX_TIME_RANGE_DAYS = 30
MAX_TIME_RANGE_SECONDS = MAX_TIME_RANGE_DAYS * 86400
DEFAULT_QUERY_TIMEOUT_SECONDS = 3.0
MAX_QUERY_TIMEOUT_SECONDS = 10.0


# --- Allowlist Mappings ---

# Map high-level signal name -> (measurement_name, field_name)
SIGNAL_CATALOG: Dict[str, Tuple[str, str]] = {
    # Environmental telemetry (nexus_telem)
    "temp": ("nexus_telem", "temp"),
    "hum": ("nexus_telem", "hum"),
    "ldr_raw": ("nexus_telem", "ldr_raw"),
    "x0_raw": ("nexus_telem", "x0_raw"),
    "x1_raw": ("nexus_telem", "x1_raw"),
    "slot_state": ("nexus_telem", "slot_state"),
    "dist_cm": ("nexus_telem", "dist_cm"),
    "dht_valid": ("nexus_telem", "dht_valid"),
    # Executive heartbeat & health (nexus_hb)
    "free_heap": ("nexus_hb", "free_heap"),
    "exec_ticks": ("nexus_hb", "exec_ticks"),
    # Executive status metrics (nexus_status)
    "dispatched": ("nexus_status", "dispatched"),
    "completed": ("nexus_status", "completed"),
    "failed": ("nexus_status", "failed"),
    "max_lat_us": ("nexus_status", "max_lat_us"),
    "max_dur_us": ("nexus_status", "max_dur_us"),
    # System events (nexus_event)
    "event_type": ("nexus_event", "event_type"),
    "severity": ("nexus_event", "severity"),
    "source_id": ("nexus_event", "source_id"),
    "payload_val": ("nexus_event", "payload_val"),
}

ALLOWED_SIGNALS: Set[str] = set(SIGNAL_CATALOG.keys())

ALLOWED_MEASUREMENTS: Set[str] = {
    "nexus_telem",
    "nexus_hb",
    "nexus_status",
    "nexus_event",
}

ALLOWED_FIELDS_BY_MEASUREMENT: Dict[str, Set[str]] = {
    "nexus_telem": {"temp", "hum", "ldr_raw", "x0_raw", "x1_raw", "slot_state", "dist_cm", "dht_valid", "seq", "uptime_ms"},
    "nexus_hb": {"free_heap", "exec_ticks", "seq", "uptime_ms"},
    "nexus_status": {"dispatched", "completed", "failed", "max_lat_us", "max_dur_us", "seq", "uptime_ms"},
    "nexus_event": {"event_type", "severity", "source_id", "payload_val", "seq", "uptime_ms"},
}

ALLOWED_TRANSPORTS: Set[str] = {"mqtt", "serial", "all"}


# --- Enums ---

class TrendDirection(enum.Enum):
    """Direction of observed signal trend."""
    STABLE = "stable"
    RISING = "rising"
    FALLING = "falling"
    INSUFFICIENT_DATA = "insufficient_data"


class TransportFilter(str, enum.Enum):
    """Transport filtering selection."""
    MQTT = "mqtt"
    SERIAL = "serial"
    ALL = "all"


# --- Exceptions ---

class AnalysisError(Exception):
    """Base exception for telemetry analysis and query operations."""


class InvalidQueryError(AnalysisError):
    """Raised when query parameters fail allowlist or boundary validation."""


class DeviceNotFoundError(AnalysisError):
    """Raised when the specified device identifier has no records."""


class DataSourceUnavailableError(AnalysisError):
    """Raised when the underlying time-series database is offline or unreachable."""


class QueryTimeoutError(AnalysisError):
    """Raised when a query exceeds its allocated execution deadline."""


# --- Query and Result Models ---

@dataclass(frozen=True)
class TelemetryRecord:
    """A single typed telemetry observation from InfluxDB."""

    dev: str
    measurement: str
    field: str
    value: Union[float, int, bool, str]
    host_time: datetime
    uptime_ms: Optional[int] = None
    seq: Optional[int] = None
    transport: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to standard JSON-compatible dictionary."""
        return {
            "dev": self.dev,
            "measurement": self.measurement,
            "field": self.field,
            "value": self.value,
            "host_time": self.host_time.isoformat(),
            "uptime_ms": self.uptime_ms,
            "seq": self.seq,
            "transport": self.transport,
        }


@dataclass
class ObservationEvent:
    """A canonical, deduplicated device event across transports.

    When both MQTT and serial transports deliver the same event (same dev,
    msg_type, seq, and uptime_ms within a close correlation window), it is
    represented as a single canonical observation while preserving transport
    provenance.
    """

    dev: str
    msg_type: str
    seq: int
    uptime_ms: int
    host_time: datetime
    transports: List[str]
    fields: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dev": self.dev,
            "msg_type": self.msg_type,
            "seq": self.seq,
            "uptime_ms": self.uptime_ms,
            "host_time": self.host_time.isoformat(),
            "transports": list(self.transports),
            "fields": dict(self.fields),
        }


@dataclass
class SignalSummary:
    """Statistical summary for a signal over an un-truncated time window.

    Full-window statistics are computed directly in InfluxDB or over the complete
    dataset, ensuring they are NEVER computed from a silently capped/truncated list of points.
    """

    dev: str
    signal: str
    measurement: str
    field_name: str
    start_time: str
    stop_time: str
    sample_count: int
    invalid_count: int
    min_value: Optional[float]
    max_value: Optional[float]
    mean_value: Optional[float]
    first_value: Optional[Union[float, int, bool]]
    last_value: Optional[Union[float, int, bool]]
    first_time: Optional[datetime]
    last_time: Optional[datetime]
    is_truncated: bool = False
    query_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dev": self.dev,
            "signal": self.signal,
            "measurement": self.measurement,
            "field_name": self.field_name,
            "start_time": self.start_time,
            "stop_time": self.stop_time,
            "sample_count": self.sample_count,
            "invalid_count": self.invalid_count,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "mean_value": self.mean_value,
            "first_value": self.first_value,
            "last_value": self.last_value,
            "first_time": self.first_time.isoformat() if self.first_time else None,
            "last_time": self.last_time.isoformat() if self.last_time else None,
            "is_truncated": self.is_truncated,
            "query_duration_ms": self.query_duration_ms,
        }


@dataclass
class WindowComparison:
    """Comparison of summary statistics between two adjacent time windows."""

    dev: str
    signal: str
    current_window: SignalSummary
    prior_window: SignalSummary
    delta_mean: Optional[float] = None
    pct_change_mean: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dev": self.dev,
            "signal": self.signal,
            "current_window": self.current_window.to_dict(),
            "prior_window": self.prior_window.to_dict(),
            "delta_mean": self.delta_mean,
            "pct_change_mean": self.pct_change_mean,
        }


@dataclass
class TrendSummary:
    """Trend analysis for a numeric signal over a given window."""

    dev: str
    signal: str
    window: str
    direction: TrendDirection
    slope_per_minute: Optional[float]
    delta: Optional[float]
    sample_count: int
    start_value: Optional[float]
    end_value: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dev": self.dev,
            "signal": self.signal,
            "window": self.window,
            "direction": self.direction.value,
            "slope_per_minute": self.slope_per_minute,
            "delta": self.delta,
            "sample_count": self.sample_count,
            "start_value": self.start_value,
            "end_value": self.end_value,
        }


@dataclass
class FreshnessReport:
    """Assessment of telemetry reception freshness and connectivity."""

    dev: str
    measurement: str
    last_seen_host: Optional[datetime]
    last_uptime_ms: Optional[int]
    last_seq: Optional[int]
    age_seconds: Optional[float]
    expected_cadence_sec: float
    is_stale: bool
    has_telemetry: bool = False
    transport: Optional[str] = None
    transports_seen: List[str] = field(default_factory=list)
    dht_healthy: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dev": self.dev,
            "measurement": self.measurement,
            "has_telemetry": self.has_telemetry,
            "last_seen_host": self.last_seen_host.isoformat() if self.last_seen_host else None,
            "last_uptime_ms": self.last_uptime_ms,
            "last_seq": self.last_seq,
            "age_seconds": self.age_seconds,
            "expected_cadence_sec": self.expected_cadence_sec,
            "is_stale": self.is_stale,
            "transport": self.transport,
            "transports_seen": list(self.transports_seen),
            "dht_healthy": self.dht_healthy,
        }

