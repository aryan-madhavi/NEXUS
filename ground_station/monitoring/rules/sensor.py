"""NEXUS Environmental Sensor Health Monitoring Rule.

Monitors DHT11/22 sensor integrity using confirmed `dht_valid` flags.
Distinguishes confirmed sensor-invalid readings from absent telemetry.
Never fabricates gas ppm or safety thresholds from raw ADC signals (x0_raw).
"""

from __future__ import annotations

from typing import Any, Dict

from ground_station.analysis.quality import TelemetryQuality
from ground_station.analysis.telemetry_query import TelemetryQueryService

from ..models import IncidentSeverity
from .base import MonitoringRule


class DHTInvalidReadingRule(MonitoringRule):
    """Monitors DHT sensor status flags to detect confirmed sensor read failures."""

    def __init__(
        self,
        rule_id: str = "dht_sensor_invalid",
        window: str = "-15m",
        min_invalid_samples: int = 3,
        invalid_ratio_threshold: float = 0.5,
        min_valid_samples_to_clear: int = 3,
        confirm_trigger_count: int = 2,
        confirm_clear_count: int = 2,
        severity: IncidentSeverity = IncidentSeverity.WARNING,
    ) -> None:
        """Initialize DHTInvalidReadingRule.

        Args:
            rule_id: Stable identifier for incident deduplication.
            window: Evaluation time window for sensor quality audit.
            min_invalid_samples: Minimum count of dht_valid=False required to trigger.
            invalid_ratio_threshold: Minimum fraction of invalid samples required to trigger.
            min_valid_samples_to_clear: Required consecutive/sufficient valid samples to clear.
            confirm_trigger_count: Consecutive evaluations to confirm trigger.
            confirm_clear_count: Consecutive evaluations to confirm clear.
            severity: Operational severity classification (default: WARNING).
        """
        super().__init__(
            rule_id=rule_id,
            name="DHT Sensor Invalid Readings",
            description=(
                f"Detects confirmed DHT sensor failures where dht_valid=False in at least "
                f"{min_invalid_samples} samples and invalid ratio >= {invalid_ratio_threshold:.0%} in window {window}."
            ),
            default_severity=severity,
            confirm_trigger_count=confirm_trigger_count,
            confirm_clear_count=confirm_clear_count,
        )
        self.window = window
        self.min_invalid_samples = min_invalid_samples
        self.invalid_ratio_threshold = invalid_ratio_threshold
        self.min_valid_samples_to_clear = min_valid_samples_to_clear

    def _evaluate_internal(
        self,
        query_service: TelemetryQueryService,
        device_id: str,
        is_active: bool,
    ) -> tuple[bool, bool, str, Dict[str, Any], str]:
        """Audit sensor quality using TelemetryQuality.audit_sensor_quality."""
        audit = TelemetryQuality.audit_sensor_quality(
            query_service=query_service,
            dev=device_id,
            window=self.window,
        )

        total_samples = audit.get("total_samples", 0)
        dht_valid_count = audit.get("dht_valid_count", 0)
        dht_invalid_count = audit.get("dht_invalid_count", 0)
        dht_invalid_ratio = audit.get("dht_invalid_ratio", 0.0)

        evidence = {
            "dev": device_id,
            "window": self.window,
            "total_samples": total_samples,
            "dht_valid_count": dht_valid_count,
            "dht_invalid_count": dht_invalid_count,
            "dht_invalid_ratio": round(dht_invalid_ratio, 4),
            "threshold_min_invalid": self.min_invalid_samples,
            "threshold_ratio": self.invalid_ratio_threshold,
        }

        # Case 1: Insufficient telemetry samples in window
        if total_samples == 0:
            return (
                False,
                False,
                f"No environmental samples for {device_id} in {self.window}.",
                evidence,
                "Insufficient data: zero telemetry envelopes found in window (absent telemetry is handled by freshness rule).",
            )

        # Case 2: Confirmed invalid reading pattern
        if (
            dht_invalid_count >= self.min_invalid_samples
            and dht_invalid_ratio >= self.invalid_ratio_threshold
        ):
            summary = (
                f"DHT sensor on {device_id} reported {dht_invalid_count}/{total_samples} "
                f"invalid readings ({dht_invalid_ratio:.1%}) in {self.window}."
            )
            reason = (
                f"Confirmed invalid readings ({dht_invalid_count}) >= min threshold ({self.min_invalid_samples}) "
                f"and ratio ({dht_invalid_ratio:.1%}) >= threshold ({self.invalid_ratio_threshold:.1%})."
            )
            return True, False, summary, evidence, reason

        # Case 3: Confirmed healthy sensor readings
        if (
            dht_invalid_count == 0
            and dht_valid_count >= self.min_valid_samples_to_clear
        ):
            summary = (
                f"DHT sensor on {device_id} is healthy: "
                f"{dht_valid_count}/{total_samples} valid readings with 0 invalid in {self.window}."
            )
            reason = f"Confirmed {dht_valid_count} valid readings with 0 invalid samples in evaluation window."
            return False, True, summary, evidence, reason

        # Case 4: Ambiguous/transient (e.g., 1 invalid sample below threshold)
        # If active, does not clear until min_valid_samples_to_clear is met with 0 invalid
        if is_active and dht_invalid_count == 0 and dht_valid_count > 0:
            summary = f"DHT sensor on {device_id} shows {dht_valid_count} valid readings."
            reason = f"Valid readings observed ({dht_valid_count}), condition clearing."
            return False, True, summary, evidence, reason

        return (
            False,
            False,
            f"DHT readings on {device_id} within acceptable tolerance ({dht_invalid_count}/{total_samples} invalid).",
            evidence,
            "Invalid count/ratio below triggering threshold and no active incident.",
        )
