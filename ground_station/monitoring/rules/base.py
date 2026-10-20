"""NEXUS Monitoring Rule Base and Result Types.

Defines the contract for conservative deterministic monitoring rules:
- Explicit trigger and clear conditions
- Required evidence definitions
- Severity and operational rationale
- Handling of insufficient, stale, or unavailable data
- Confirmation and hysteresis tracking to prevent flapping
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ground_station.analysis.models import (
    DataSourceUnavailableError,
    QueryTimeoutError,
)
from ground_station.analysis.telemetry_query import TelemetryQueryService

from ..models import IncidentSeverity

logger = logging.getLogger("nexus.monitoring.rules")


@dataclass
class RuleEvaluationResult:
    """Outcome of a single rule evaluation for a device.

    Semantics:
    - triggered=True, cleared=False: An incident condition is confirmed and should be opened or remain active.
    - triggered=False, cleared=True: The condition has cleared and any active incident should resolve.
    - triggered=False, cleared=False: Insufficient data, data source unavailable, or hysteresis pending.
      The existing incident state should remain unchanged (no false triggers or premature resolutions).
    """

    rule_id: str
    device_id: str
    triggered: bool
    cleared: bool
    severity: IncidentSeverity
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class MonitoringRule(abc.ABC):
    """Abstract base class for deterministic monitoring rules."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        default_severity: IncidentSeverity = IncidentSeverity.WARNING,
        confirm_trigger_count: int = 1,
        confirm_clear_count: int = 1,
    ) -> None:
        """Initialize monitoring rule.

        Args:
            rule_id: Stable identifier (e.g. 'stale_telemetry', 'dht_sensor_invalid').
            name: Human-readable name.
            description: Operational rationale and evidence definition.
            default_severity: Default IncidentSeverity.
            confirm_trigger_count: Consecutive evaluations required to confirm trigger (hysteresis).
            confirm_clear_count: Consecutive evaluations required to confirm resolution (hysteresis).
        """
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.default_severity = default_severity
        self.confirm_trigger_count = max(1, confirm_trigger_count)
        self.confirm_clear_count = max(1, confirm_clear_count)

        # In-memory hysteresis trackers per device
        self._trigger_counters: Dict[str, int] = {}
        self._clear_counters: Dict[str, int] = {}

    def reset_state(self, device_id: Optional[str] = None) -> None:
        """Reset internal hysteresis counters."""
        if device_id:
            self._trigger_counters.pop(device_id, None)
            self._clear_counters.pop(device_id, None)
        else:
            self._trigger_counters.clear()
            self._clear_counters.clear()

    def evaluate(
        self,
        query_service: TelemetryQueryService,
        device_id: str,
        is_active: bool = False,
    ) -> RuleEvaluationResult:
        """Safe wrapper around _evaluate_internal with exception and hysteresis handling.

        Guarantees:
        - DataSourceUnavailableError and QueryTimeoutError are caught and NEVER produce false incidents.
        - Unhandled exceptions are logged and result in a safe neutral evaluation (triggered=False, cleared=False).
        - Consecutive trigger/clear counts enforce hysteresis to prevent flapping.
        """
        try:
            raw_triggered, raw_cleared, summary, evidence, reason = self._evaluate_internal(
                query_service=query_service,
                device_id=device_id,
                is_active=is_active,
            )
        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            logger.warning(
                "Rule %s skipped evaluation for %s: data source unavailable/timeout (%s)",
                self.rule_id,
                device_id,
                e,
            )
            return RuleEvaluationResult(
                rule_id=self.rule_id,
                device_id=device_id,
                triggered=False,
                cleared=False,
                severity=self.default_severity,
                summary=f"Data source unavailable during evaluation: {e}",
                evidence={"data_source_error": str(e)},
                reason="Data source unavailable or query timed out",
            )
        except Exception as e:
            logger.exception("Unexpected error in rule %s for device %s: %s", self.rule_id, device_id, e)
            return RuleEvaluationResult(
                rule_id=self.rule_id,
                device_id=device_id,
                triggered=False,
                cleared=False,
                severity=self.default_severity,
                summary=f"Evaluation error: {e}",
                evidence={"error": str(e)},
                reason=f"Evaluation failed unexpectedly: {e}",
            )

        # Apply hysteresis / confirmation counters
        final_triggered = False
        final_cleared = False

        if raw_triggered:
            self._clear_counters[device_id] = 0
            count = self._trigger_counters.get(device_id, 0) + 1
            self._trigger_counters[device_id] = count
            if count >= self.confirm_trigger_count:
                final_triggered = True
            else:
                reason = f"Trigger pending confirmation ({count}/{self.confirm_trigger_count}): {reason}"
        elif raw_cleared:
            self._trigger_counters[device_id] = 0
            count = self._clear_counters.get(device_id, 0) + 1
            self._clear_counters[device_id] = count
            if count >= self.confirm_clear_count:
                final_cleared = True
            else:
                reason = f"Clear pending confirmation ({count}/{self.confirm_clear_count}): {reason}"
        else:
            # Neither raw_triggered nor raw_cleared (e.g. insufficient data)
            # Maintain existing counts
            pass

        return RuleEvaluationResult(
            rule_id=self.rule_id,
            device_id=device_id,
            triggered=final_triggered,
            cleared=final_cleared,
            severity=self.default_severity,
            summary=summary,
            evidence=evidence,
            reason=reason,
        )

    @abc.abstractmethod
    def _evaluate_internal(
        self,
        query_service: TelemetryQueryService,
        device_id: str,
        is_active: bool,
    ) -> tuple[bool, bool, str, Dict[str, Any], str]:
        """Subclass implementation of rule logic.

        Returns:
            Tuple of (raw_triggered, raw_cleared, summary, evidence, reason).
        """
