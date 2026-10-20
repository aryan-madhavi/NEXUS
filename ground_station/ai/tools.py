"""NEXUS Read-Only Telemetry and Incident AI Tools.

Provides a small, strictly bounded, typed, read-only interface for conversational AI.
Enforces:
- Input allowlists and regex validation on device IDs, signals, and time windows.
- Strict read-only operations wrapping M7.1 analysis and M7.2 monitoring modules.
- Explicit labeling of missing or invalid sensor readings (never zero-filled or fabricated).
- Raw ADC identification for `x0_raw` (never converted to invented gas ppm or safety thresholds).
- Protection against prompt injection: telemetry and incident data are treated strictly as data.
- Bounded time ranges and query limits.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ground_station.analysis.models import (
    ALLOWED_SIGNALS,
    DEVICE_ID_PATTERN,
    RELATIVE_DURATION_PATTERN,
    DataSourceUnavailableError,
    QueryTimeoutError,
)
from ground_station.analysis.quality import TelemetryQuality
from ground_station.analysis.statistics import TelemetryStatistics
from ground_station.analysis.telemetry_query import TelemetryQueryService
from ground_station.monitoring.store import IncidentStore

logger = logging.getLogger("nexus.ai.tools")


@dataclass(frozen=True)
class ToolResult:
    """Standardized structured output for read-only AI tools."""

    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    time_range_evaluated: Optional[str] = None
    retrieval_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": dict(self.data),
            "error": self.error,
            "time_range_evaluated": self.time_range_evaluated,
            "retrieval_timestamp": self.retrieval_timestamp or datetime.now(timezone.utc).isoformat(),
        }


class NexusAITools:
    """Validated, read-only operational toolset for NEXUS Ground Station telemetry and incidents."""

    def __init__(
        self,
        query_service: Optional[TelemetryQueryService] = None,
        store: Optional[IncidentStore] = None,
    ) -> None:
        """Initialize NexusAITools with analysis and persistence dependencies."""
        self._external_query = query_service is not None
        self.query_service = query_service or TelemetryQueryService()

        self._external_store = store is not None
        self.store = store or IncidentStore("nexus_incidents.db")

    def close(self) -> None:
        """Release underlying connections if internally managed."""
        if not self._external_query and self.query_service is not None:
            self.query_service.close()
        if not self._external_store and self.store is not None:
            self.store.close()

    # --- Validation Helpers ---

    @staticmethod
    def _validate_device(device_id: str) -> str:
        """Validate device identifier against allowlist pattern."""
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("device_id must be a non-empty string.")
        dev = device_id.strip()
        if not DEVICE_ID_PATTERN.match(dev):
            raise ValueError(f"Invalid device_id format: '{dev}'. Must be 1-32 alphanumeric, dash, or underscore.")
        return dev

    @staticmethod
    def _validate_signal(signal: str) -> str:
        """Validate signal name against allowed signals catalog."""
        if not isinstance(signal, str) or not signal:
            raise ValueError("signal must be a non-empty string.")
        sig = signal.strip().lower()
        if sig not in ALLOWED_SIGNALS:
            raise ValueError(f"Unknown or disallowed signal: '{sig}'. Allowed signals: {sorted(list(ALLOWED_SIGNALS))}")
        return sig

    @staticmethod
    def _validate_window(window: str) -> str:
        """Validate relative duration string (e.g., '-15m', '-1h', '-24h')."""
        if not isinstance(window, str) or not window:
            raise ValueError("window must be a non-empty relative duration string (e.g. '-15m', '-1h').")
        win = window.strip().lower()
        if not RELATIVE_DURATION_PATTERN.match(win):
            raise ValueError(f"Invalid window format: '{win}'. Expected relative format like '-15m', '-1h', '-24h'.")
        return win

    @staticmethod
    def _validate_incident_id(incident_id: str) -> str:
        """Validate incident_id format against safe pattern."""
        if not isinstance(incident_id, str) or not incident_id:
            raise ValueError("incident_id must be a non-empty string.")
        inc = incident_id.strip()
        if not re.match(r"^[a-zA-Z0-9_\-.:]{1,128}$", inc):
            raise ValueError(f"Invalid incident_id format: '{inc}'. Must be alphanumeric, dash, underscore, colon, or dot.")
        return inc

    @staticmethod
    def _validate_rule_id(rule_id: str) -> str:
        """Validate rule_id format against safe pattern."""
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("rule_id must be a non-empty string.")
        rule = rule_id.strip()
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", rule):
            raise ValueError(f"Invalid rule_id format: '{rule}'. Must be alphanumeric, dash, or underscore.")
        return rule

    @staticmethod
    def _validate_limit(limit: Any, default: int = 10, max_limit: int = 50) -> int:
        """Validate and clamp numeric result limits."""
        if isinstance(limit, bool) or not isinstance(limit, (int, str)):
            raise ValueError(f"limit must be an integer, got {type(limit).__name__}.")
        try:
            val = int(limit)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid integer limit: {limit!r}.")
        return max(1, min(val, max_limit))

    # --- Read-Only Tools ---

    def get_latest_telemetry(self, device_id: str = "esp32_01") -> ToolResult:
        """Get the latest sensor and executive readings for a monitored device.

        Distinguishes confirmed valid sensor readings from absent or invalid readings.
        `x0_raw` is documented strictly as a raw ADC reading without fabricated ppm.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id)
            envelopes = self.query_service.get_raw_envelopes(
                dev=dev,
                msg_type="telem",
                start="-30d",
                stop="now()",
                limit=1,
                deduplicate=True,
            )

            if not envelopes:
                return ToolResult(
                    success=True,
                    data={
                        "device_id": dev,
                        "has_telemetry": False,
                        "status": "NO_OBSERVATIONS",
                        "message": f"No telemetry observations recorded for device '{dev}'.",
                    },
                    time_range_evaluated="-30d to now()",
                    retrieval_timestamp=now_iso,
                )

            env = envelopes[-1]
            fields = env.fields
            dht_valid = fields.get("dht_valid")

            # Determine sensor validity
            temp_val = fields.get("temp") if dht_valid is True else None
            hum_val = fields.get("hum") if dht_valid is True else None

            data = {
                "device_id": dev,
                "has_telemetry": True,
                "host_time": env.host_time.isoformat(),
                "uptime_ms": env.uptime_ms,
                "seq": env.seq,
                "transports": list(env.transports),
                "sensors": {
                    "temperature_c": temp_val,
                    "humidity_pct": hum_val,
                    "dht_valid": dht_valid,
                    "ldr_raw": fields.get("ldr_raw"),
                    "x0_raw_adc": fields.get("x0_raw"),
                },
                "notes": [
                    "x0_raw_adc is the raw numeric ADC count from MUX input 0; state the numeric count directly as uncalibrated raw ADC, not calibrated gas ppm.",
                    "temperature_c and humidity_pct are null if dht_valid is False to prevent invalid sensor usage.",
                ],
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated="latest envelope",
                retrieval_timestamp=now_iso,
            )

        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id},
                error=f"Telemetry data source unavailable: {e}",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id},
                error=f"Error retrieving latest telemetry: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_telemetry_freshness(self, device_id: str = "esp32_01", msg_type: str = "telem") -> ToolResult:
        """Inspect telemetry arrival age, expected cadence, and stale status."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id)
            if msg_type not in ("telem", "hb", "status"):
                raise ValueError("msg_type must be one of 'telem', 'hb', 'status'.")

            report = TelemetryQuality.get_freshness(
                query_service=self.query_service,
                dev=dev,
                msg_type=msg_type,
            )

            data = {
                "device_id": dev,
                "message_type": msg_type,
                "has_telemetry": report.has_telemetry,
                "is_stale": report.is_stale,
                "age_seconds": round(report.age_seconds, 2) if report.age_seconds is not None else None,
                "expected_cadence_sec": report.expected_cadence_sec,
                "last_seen_host": report.last_seen_host.isoformat() if report.last_seen_host else None,
                "last_uptime_ms": report.last_uptime_ms,
                "last_seq": report.last_seq,
                "transports_seen": list(report.transports_seen),
                "dht_healthy": report.dht_healthy,
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated="-30d to now()",
                retrieval_timestamp=now_iso,
            )
        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id},
                error=f"Data source unavailable during freshness check: {e}",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id},
                error=f"Error checking freshness: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_signal_statistics(
        self,
        device_id: str = "esp32_01",
        signal: str = "temp",
        window: str = "-15m",
    ) -> ToolResult:
        """Compute full-window statistical summary (min, max, mean, sample counts) without truncation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id)
            sig = self._validate_signal(signal)
            win = self._validate_window(window)

            summary = self.query_service.get_window_statistics(
                dev=dev,
                signal=sig,
                start=win,
                stop="now()",
            )

            data = {
                "device_id": dev,
                "signal": sig,
                "window": win,
                "sample_count": summary.sample_count,
                "invalid_count": summary.invalid_count,
                "min": summary.min_value,
                "max": summary.max_value,
                "mean": round(summary.mean_value, 2) if summary.mean_value is not None else None,
                "first_value": summary.first_value,
                "last_value": summary.last_value,
                "first_time": summary.first_time.isoformat() if summary.first_time else None,
                "last_time": summary.last_time.isoformat() if summary.last_time else None,
                "is_truncated": summary.is_truncated,
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated=f"{win} to now()",
                retrieval_timestamp=now_iso,
            )
        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id, "signal": signal},
                error=f"Data source unavailable for statistics query: {e}",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id, "signal": signal},
                error=f"Error computing signal statistics: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_signal_trend(
        self,
        device_id: str = "esp32_01",
        signal: str = "temp",
        window: str = "-15m",
    ) -> ToolResult:
        """Compute rate-of-change and directional trend for a numeric signal over a time window."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id)
            sig = self._validate_signal(signal)
            win = self._validate_window(window)

            trend = TelemetryStatistics.compute_trend(
                query_service=self.query_service,
                dev=dev,
                signal=sig,
                window=win,
            )

            data = {
                "device_id": dev,
                "signal": sig,
                "window": win,
                "direction": trend.direction.value,
                "slope_per_minute": trend.slope_per_minute,
                "delta": trend.delta,
                "sample_count": trend.sample_count,
                "start_value": trend.start_value,
                "end_value": trend.end_value,
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated=f"{win} to now()",
                retrieval_timestamp=now_iso,
            )
        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id, "signal": signal},
                error=f"Data source unavailable for trend query: {e}",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id, "signal": signal},
                error=f"Error computing signal trend: {e}",
                retrieval_timestamp=now_iso,
            )

    def audit_sensor_quality(
        self,
        device_id: str = "esp32_01",
        window: str = "-15m",
    ) -> ToolResult:
        """Audit sensor validity flags, distinguishing confirmed invalid samples from absent telemetry."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id)
            win = self._validate_window(window)

            audit = TelemetryQuality.audit_sensor_quality(
                query_service=self.query_service,
                dev=dev,
                window=win,
            )

            return ToolResult(
                success=True,
                data=audit,
                time_range_evaluated=f"{win} to now()",
                retrieval_timestamp=now_iso,
            )
        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id},
                error=f"Data source unavailable for sensor audit: {e}",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"device_id": device_id},
                error=f"Error auditing sensor quality: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_active_incidents(self, device_id: Optional[str] = None) -> ToolResult:
        """Query currently active (OPEN) operational incidents with opening evidence."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id) if device_id else None
            incidents = self.store.get_active_incidents(device_id=dev)

            data = {
                "active_incident_count": len(incidents),
                "filter_device": dev,
                "incidents": [inc.to_dict() for inc in incidents],
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated="current active incidents",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={},
                error=f"Error querying active incidents: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_incident_history(
        self,
        device_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 10,
    ) -> ToolResult:
        """Query bounded historical incidents (both resolved and active) with timestamps and severities."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            dev = self._validate_device(device_id) if device_id else None
            rule = self._validate_rule_id(rule_id) if rule_id else None
            clamped_limit = self._validate_limit(limit, default=10, max_limit=50)

            history = self.store.get_incident_history(
                device_id=dev,
                rule_id=rule,
                limit=clamped_limit,
            )

            data = {
                "count": len(history),
                "filter_device": dev,
                "filter_rule": rule,
                "limit": clamped_limit,
                "incidents": [inc.to_dict() for inc in history],
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated=f"recent {clamped_limit} incidents",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={},
                error=f"Error querying incident history: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_incident_details(self, incident_id: str) -> ToolResult:
        """Retrieve full details, opening/resolving evidence, and chronological transitions for a specific incident."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            inc_id = self._validate_incident_id(incident_id)

            incident = self.store.get_incident(inc_id)
            if not incident:
                return ToolResult(
                    success=False,
                    data={"incident_id": inc_id},
                    error=f"Incident '{inc_id}' not found.",
                    retrieval_timestamp=now_iso,
                )

            transitions = self.store.get_incident_transitions(inc_id)

            data = {
                "incident": incident.to_dict(),
                "transitions": [t.to_dict() for t in transitions],
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated=f"lifecycle of incident {inc_id}",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"incident_id": incident_id},
                error=f"Error retrieving incident details: {e}",
                retrieval_timestamp=now_iso,
            )

    def get_system_status(self) -> ToolResult:
        """Inspect telemetry database connection health and overall monitoring state."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            health = self.query_service.check_health()
            active_incidents = self.store.get_active_incidents()

            data = {
                "data_source": {
                    "status": health.get("status", "unknown"),
                    "details": health,
                },
                "monitoring": {
                    "active_incident_count": len(active_incidents),
                    "active_incidents_summary": [
                        {"id": inc.incident_id, "dev": inc.device_id, "rule": inc.rule_id, "severity": inc.severity.value}
                        for inc in active_incidents
                    ],
                },
            }

            return ToolResult(
                success=True,
                data=data,
                time_range_evaluated="current system health",
                retrieval_timestamp=now_iso,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={"data_source_status": "UNAVAILABLE"},
                error=f"Error querying system status: {e}",
                retrieval_timestamp=now_iso,
            )
