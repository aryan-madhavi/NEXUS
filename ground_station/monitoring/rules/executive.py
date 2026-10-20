"""NEXUS Executive Health and Reboot Monitoring Rules.

Implements deterministic rules supported directly by the ESP32 firmware schema:
- ExecutiveTaskFailureRule: Monitors `failed` task executions in `nexus_status`.
- DeviceRebootRule: Monitors device restarts and monotonic uptime drops.
"""

from __future__ import annotations

from typing import Any, Dict

from ground_station.analysis.quality import TelemetryQuality
from ground_station.analysis.telemetry_query import TelemetryQueryService

from ..models import IncidentSeverity
from .base import MonitoringRule


class ExecutiveFailureRule(MonitoringRule):
    """Monitors cyclic executive dispatch status to detect task execution failures.

    Accounts for cumulative counter semantics:
    In ESP32 firmware, `exec->stats.jobs_failed` is a monotonic cumulative counter.
    A failure incident triggers when new task failures occur (`failed_delta > 0`).
    When subsequent status envelopes report `failed_delta == 0` while the executive
    is actively dispatching tasks, the incident resolves with evidence demonstrating
    operational recovery, preventing permanent active incidents from historical counters.
    """

    def __init__(
        self,
        rule_id: str = "executive_task_failure",
        severity: IncidentSeverity = IncidentSeverity.CRITICAL,
        confirm_trigger_count: int = 1,
        confirm_clear_count: int = 2,
    ) -> None:
        super().__init__(
            rule_id=rule_id,
            name="Cyclic Executive Task Failure",
            description="Detects increases in cumulative failed task counts in cyclic executive status telemetry.",
            default_severity=severity,
            confirm_trigger_count=confirm_trigger_count,
            confirm_clear_count=confirm_clear_count,
        )
        self._last_seen_failed: Dict[str, int] = {}
        self._last_seen_dispatched: Dict[str, int] = {}

    def reset_state(self, device_id: str | None = None) -> None:
        """Reset internal hysteresis and baseline tracking."""
        super().reset_state(device_id)
        if device_id:
            self._last_seen_failed.pop(device_id, None)
            self._last_seen_dispatched.pop(device_id, None)
        else:
            self._last_seen_failed.clear()
            self._last_seen_dispatched.clear()

    def _evaluate_internal(
        self,
        query_service: TelemetryQueryService,
        device_id: str,
        is_active: bool,
    ) -> tuple[bool, bool, str, Dict[str, Any], str]:
        """Query nexus_status envelopes and evaluate cumulative counter delta."""
        envelopes = query_service.get_raw_envelopes(
            dev=device_id,
            msg_type="status",
            start="-15m",
            stop="now()",
            limit=5,
            deduplicate=True,
        )

        if not envelopes:
            # Critical: Do NOT claim recovery if there are 0 matching rows!
            return (
                False,
                False,
                f"No status telemetry available for {device_id}.",
                {"dev": device_id, "total_samples": 0},
                "Insufficient data: zero status envelopes found in window (recovery cannot be established without data).",
            )

        latest = envelopes[-1]
        curr_failed = int(latest.fields.get("failed", 0))
        curr_dispatched = int(latest.fields.get("dispatched", 0))
        curr_completed = int(latest.fields.get("completed", 0))
        max_lat_us = latest.fields.get("max_lat_us")
        max_dur_us = latest.fields.get("max_dur_us")

        # Determine delta against previous envelope in window or tracked state
        if len(envelopes) >= 2:
            prev = envelopes[-2]
            prev_failed = int(prev.fields.get("failed", 0))
            prev_dispatched = int(prev.fields.get("dispatched", 0))
            if latest.uptime_ms < prev.uptime_ms:
                # Device reboot reset the monotonic counter
                delta_failed = curr_failed
                delta_dispatched = curr_dispatched
            else:
                delta_failed = max(0, curr_failed - prev_failed)
                delta_dispatched = max(0, curr_dispatched - prev_dispatched)
        elif device_id in self._last_seen_failed:
            prev_failed = self._last_seen_failed[device_id]
            prev_dispatched = self._last_seen_dispatched.get(device_id, 0)
            delta_failed = max(0, curr_failed - prev_failed)
            delta_dispatched = max(0, curr_dispatched - prev_dispatched)
        else:
            # First observation of this device
            delta_failed = curr_failed
            delta_dispatched = curr_dispatched

        self._last_seen_failed[device_id] = curr_failed
        self._last_seen_dispatched[device_id] = curr_dispatched

        evidence = {
            "dev": device_id,
            "uptime_ms": latest.uptime_ms,
            "seq": latest.seq,
            "failed_cumulative": curr_failed,
            "failed_delta": delta_failed,
            "dispatched_cumulative": curr_dispatched,
            "dispatched_delta": delta_dispatched,
            "completed_cumulative": curr_completed,
            "max_lat_us": max_lat_us,
            "max_dur_us": max_dur_us,
            "host_time": latest.host_time.isoformat(),
        }

        # Case 1: New task failure(s) occurred
        if delta_failed > 0:
            summary = (
                f"Cyclic executive on {device_id} experienced {delta_failed} new failed task(s) "
                f"(cumulative failures: {curr_failed}, dispatched: {curr_dispatched})."
            )
            reason = f"Executive status failed counter increased by {delta_failed}."
            return True, False, summary, evidence, reason

        # Case 2: No new failures (delta_failed == 0)
        if is_active:
            # Active failure incident recovering: tasks are running with 0 new failures
            summary = (
                f"Cyclic executive on {device_id} recovered: 0 new failures observed "
                f"(cumulative failures: {curr_failed}, completed: {curr_completed})."
            )
            reason = "Executive status failed counter did not increase (failed_delta == 0) across status evaluations."
            return False, True, summary, evidence, reason

        if curr_failed == 0:
            summary = f"Cyclic executive on {device_id} is healthy: 0 failed tasks (completed: {curr_completed})."
            reason = "Executive status cumulative failed count == 0."
            return False, True, summary, evidence, reason

        # Historical failures exist on ESP32, but delta is 0 and no active incident
        summary = (
            f"Cyclic executive on {device_id} stable: no new failures "
            f"(historical cumulative: {curr_failed}, dispatched: {curr_dispatched})."
        )
        reason = "No new task failures (failed_delta == 0)."
        return False, False, summary, evidence, reason


class DeviceRebootRule(MonitoringRule):
    """Monitors device reboots detected via monotonic uptime drops."""

    def __init__(
        self,
        rule_id: str = "device_reboot_detected",
        window: str = "-15m",
        severity: IncidentSeverity = IncidentSeverity.INFO,
        confirm_trigger_count: int = 1,
        confirm_clear_count: int = 1,
    ) -> None:
        super().__init__(
            rule_id=rule_id,
            name="Device Reboot Detected",
            description="Detects device reboots from monotonic uptime drops in telemetry.",
            default_severity=severity,
            confirm_trigger_count=confirm_trigger_count,
            confirm_clear_count=confirm_clear_count,
        )
        self.window = window

    def _evaluate_internal(
        self,
        query_service: TelemetryQueryService,
        device_id: str,
        is_active: bool,
    ) -> tuple[bool, bool, str, Dict[str, Any], str]:
        """Audit sequence integrity to detect uptime resets."""
        audit = TelemetryQuality.audit_sequence_integrity(
            query_service=query_service,
            dev=device_id,
            msg_type="telem",
            window=self.window,
        )

        reboots = audit.get("reboots_detected", 0)
        seq_gaps = audit.get("sequence_gaps", 0)
        total_obs = audit.get("total_observations", 0)

        evidence = {
            "dev": device_id,
            "window": self.window,
            "total_observations": total_obs,
            "reboots_detected": reboots,
            "sequence_gaps": seq_gaps,
        }

        if total_obs < 2:
            return (
                False,
                False,
                f"Insufficient data for reboot audit on {device_id}.",
                evidence,
                "Need at least 2 observations to detect uptime resets.",
            )

        if reboots > 0:
            summary = f"Device {device_id} reboot detected: {reboots} uptime reset(s) in {self.window}."
            reason = f"Audit detected {reboots} monotonic uptime drop(s)."
            return True, False, summary, evidence, reason

        summary = f"Device {device_id} uptime is monotonic (0 reboots detected in {self.window})."
        reason = "No uptime drops detected in window."
        return False, True, summary, evidence, reason
