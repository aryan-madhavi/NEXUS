"""NEXUS Telemetry Freshness Monitoring Rule.

Evaluates host-side telemetry arrival recency against expected cyclic executive
cadence (2.0s for telemetry, 1.0s for heartbeat, 5.0s for status) plus configurable
operational grace.

Distinguishes:
- Confirmed stale data (host arrival age exceeds cadence * grace_factor).
- Fresh data clearing an active incident immediately.
- InfluxDB outages (which never trigger this rule).
- Never-before-seen devices (treated as insufficient data unless configured otherwise).
"""

from __future__ import annotations

from typing import Any, Dict

from ground_station.analysis.quality import TelemetryQuality
from ground_station.analysis.telemetry_query import TelemetryQueryService

from ..models import IncidentSeverity
from .base import MonitoringRule


class TelemetryFreshnessRule(MonitoringRule):
    """Monitors telemetry arrival recency to detect device communication loss."""

    def __init__(
        self,
        rule_id: str = "stale_telemetry",
        msg_type: str = "telem",
        cadence_sec: float = 2.0,
        grace_factor: float = 3.0,
        confirm_trigger_count: int = 2,
        confirm_clear_count: int = 1,
        require_initial_observation: bool = True,
        startup_grace_sec: float = 0.0,
        severity: IncidentSeverity = IncidentSeverity.WARNING,
    ) -> None:
        """Initialize TelemetryFreshnessRule.

        Args:
            rule_id: Stable identifier for incident deduplication.
            msg_type: Target message type ('telem', 'hb', 'status'). Default: 'telem' (2.0s cadence).
            cadence_sec: Expected publication interval in seconds.
            grace_factor: Multiplier before flagging as stale (default: 3.0x, giving 6.0s threshold).
            confirm_trigger_count: Consecutive stale observations required to confirm trigger.
            confirm_clear_count: Consecutive fresh observations required to clear.
            require_initial_observation: If True, do not trigger until at least one envelope has been seen.
            startup_grace_sec: Initial grace period in seconds after rule creation where stale trigger is suppressed.
            severity: Operational severity.
        """
        super().__init__(
            rule_id=rule_id,
            name=f"Telemetry Freshness ({msg_type})",
            description=(
                f"Detects absence of {msg_type} telemetry exceeding "
                f"{cadence_sec}s cadence * {grace_factor}x grace ({cadence_sec * grace_factor:.1f}s threshold)."
            ),
            default_severity=severity,
            confirm_trigger_count=confirm_trigger_count,
            confirm_clear_count=confirm_clear_count,
        )
        self.msg_type = msg_type
        self.cadence_sec = cadence_sec
        self.grace_factor = grace_factor
        self.stale_threshold_sec = cadence_sec * grace_factor
        self.require_initial_observation = require_initial_observation
        self.startup_grace_sec = max(0.0, startup_grace_sec)
        self._created_monotonic = None
        if self.startup_grace_sec > 0:
            import time
            self._created_monotonic = time.monotonic()

    def _evaluate_internal(
        self,
        query_service: TelemetryQueryService,
        device_id: str,
        is_active: bool,
    ) -> tuple[bool, bool, str, Dict[str, Any], str]:
        """Evaluate freshness using TelemetryQuality.get_freshness."""
        report = TelemetryQuality.get_freshness(
            query_service=query_service,
            dev=device_id,
            msg_type=self.msg_type,
            cadence_sec=self.cadence_sec,
            grace_factor=self.grace_factor,
        )

        evidence = {
            "dev": device_id,
            "msg_type": self.msg_type,
            "has_telemetry": report.has_telemetry,
            "last_seen_host": report.last_seen_host.isoformat() if report.last_seen_host else None,
            "last_uptime_ms": report.last_uptime_ms,
            "last_seq": report.last_seq,
            "age_seconds": round(report.age_seconds, 2) if report.age_seconds is not None else None,
            "cadence_sec": self.cadence_sec,
            "grace_factor": self.grace_factor,
            "stale_threshold_sec": self.stale_threshold_sec,
            "transports_seen": list(report.transports_seen),
        }

        # Case 0: Startup grace period active
        if self.startup_grace_sec > 0 and self._created_monotonic is not None and not is_active:
            import time
            elapsed = time.monotonic() - self._created_monotonic
            if elapsed < self.startup_grace_sec:
                return (
                    False,
                    False,
                    f"Startup grace period active for {device_id} ({elapsed:.1f}s / {self.startup_grace_sec:.1f}s).",
                    evidence,
                    "Startup grace period active: postponing stale evaluation until connection grace window expires.",
                )

        # Case 1: Device has never delivered telemetry
        if not report.has_telemetry:
            if self.require_initial_observation and not is_active:
                return (
                    False,
                    False,
                    f"No telemetry received yet for {device_id}.",
                    evidence,
                    "Insufficient data: device has no recorded observations in time window.",
                )
            # If already active or initial observation not required, treat as stale
            return (
                True,
                False,
                f"Device {device_id} has no telemetry in time window.",
                evidence,
                "No telemetry received within the evaluated window.",
            )

        # Case 2: Telemetry is stale (age exceeds threshold)
        if report.is_stale:
            summary = (
                f"Telemetry for {device_id} ({self.msg_type}) is stale: "
                f"last seen {report.age_seconds:.1f}s ago (threshold {self.stale_threshold_sec:.1f}s)."
            )
            reason = (
                f"Host arrival age {report.age_seconds:.1f}s exceeds cadence "
                f"({self.cadence_sec}s) * grace ({self.grace_factor}x) = {self.stale_threshold_sec:.1f}s."
            )
            return True, False, summary, evidence, reason

        # Case 3: Telemetry is fresh
        summary = (
            f"Telemetry for {device_id} ({self.msg_type}) is fresh: "
            f"last seen {report.age_seconds:.1f}s ago."
        )
        reason = f"Host arrival age {report.age_seconds:.1f}s is within freshness threshold {self.stale_threshold_sec:.1f}s."
        return False, True, summary, evidence, reason
