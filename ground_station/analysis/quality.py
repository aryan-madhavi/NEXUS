"""NEXUS Telemetry Quality & Freshness Assessment.

Provides audits for:
- Telemetry freshness and stale signal detection based on cyclic executive cadences.
- Sensor data quality audits (distinguishing missing data vs invalid readings).
- Sequence integrity and device reboot detection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .models import FreshnessReport
from .telemetry_query import TelemetryQueryService


class TelemetryQuality:
    """Evaluates telemetry freshness, sensor health, and data stream integrity."""

    # Expected default cadences from firmware app_main.c
    CADENCE_HEARTBEAT_SEC = 1.0
    CADENCE_TELEMETRY_SEC = 2.0
    CADENCE_STATUS_SEC = 5.0

    @classmethod
    def get_freshness(
        cls,
        query_service: TelemetryQueryService,
        dev: str,
        msg_type: str = "telem",
        cadence_sec: Optional[float] = None,
        grace_factor: float = 3.0,
    ) -> FreshnessReport:
        """Evaluate telemetry freshness for a specific message type.

        Args:
            query_service: Bounded query service instance.
            dev: Allowed device ID.
            msg_type: Message type ('telem', 'hb', 'status').
            cadence_sec: Expected publication interval in seconds (default based on type).
            grace_factor: Multiplier before flagging as stale (default: 3.0x).

        Returns:
            FreshnessReport detailing host arrival age, firmware uptime, and stale status.
        """
        if cadence_sec is None:
            if msg_type == "hb":
                cadence_sec = cls.CADENCE_HEARTBEAT_SEC
            elif msg_type == "status":
                cadence_sec = cls.CADENCE_STATUS_SEC
            else:
                cadence_sec = cls.CADENCE_TELEMETRY_SEC

        measurement = f"nexus_{msg_type}"
        query_service.validate_measurement(measurement)

        # Query latest envelopes over the last 30 days
        envelopes = query_service.get_raw_envelopes(
            dev=dev,
            msg_type=msg_type,
            start="-30d",
            stop="now()",
            limit=5,
            deduplicate=False,
        )

        if not envelopes:
            return FreshnessReport(
                dev=dev,
                measurement=measurement,
                last_seen_host=None,
                last_uptime_ms=None,
                last_seq=None,
                age_seconds=None,
                expected_cadence_sec=cadence_sec,
                is_stale=True,
                has_telemetry=False,
                transport=None,
                transports_seen=[],
                dht_healthy=None,
            )

        latest_env = max(envelopes, key=lambda e: e.host_time)
        now_utc = datetime.now(timezone.utc)
        age_seconds = max(0.0, (now_utc - latest_env.host_time).total_seconds())
        stale_threshold = cadence_sec * grace_factor
        is_stale = age_seconds > stale_threshold

        transports_seen = sorted(list({t for e in envelopes for t in e.transports}))
        dht_healthy = bool(latest_env.fields.get("dht_valid")) if "dht_valid" in latest_env.fields else None

        return FreshnessReport(
            dev=dev,
            measurement=measurement,
            last_seen_host=latest_env.host_time,
            last_uptime_ms=latest_env.uptime_ms,
            last_seq=latest_env.seq,
            age_seconds=age_seconds,
            expected_cadence_sec=cadence_sec,
            is_stale=is_stale,
            has_telemetry=True,
            transport=latest_env.transports[0] if latest_env.transports else None,
            transports_seen=transports_seen,
            dht_healthy=dht_healthy,
        )

    @classmethod
    def audit_sensor_quality(
        cls,
        query_service: TelemetryQueryService,
        dev: str,
        window: str = "-15m",
        transport: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive quality audit of environmental sensors.

        Distinguishes:
        - Confirmed invalid readings (where dht_valid == False).
        - Valid readings with populated temp/hum.
        - Raw ADC observations from x0_raw (verifying bounds without fabricating ppm).
        """
        envelopes = query_service.get_raw_envelopes(
            dev=dev,
            msg_type="telem",
            start=window,
            stop="now()",
            transport=transport,
            limit=1000,
            deduplicate=True,
        )

        total_envelopes = len(envelopes)
        if total_envelopes == 0:
            return {
                "dev": dev,
                "window": window,
                "total_samples": 0,
                "dht_valid_count": 0,
                "dht_invalid_count": 0,
                "dht_invalid_ratio": 0.0,
                "x0_raw_stats": None,
                "ldr_raw_stats": None,
            }

        dht_valid_count = 0
        dht_invalid_count = 0
        x0_vals = []
        ldr_vals = []

        for e in envelopes:
            dht_v = e.fields.get("dht_valid")
            if dht_v is True:
                dht_valid_count += 1
            elif dht_v is False:
                dht_invalid_count += 1

            if "x0_raw" in e.fields and e.fields["x0_raw"] is not None:
                x0_vals.append(int(e.fields["x0_raw"]))
            if "ldr_raw" in e.fields and e.fields["ldr_raw"] is not None:
                ldr_vals.append(int(e.fields["ldr_raw"]))

        inv_ratio = (dht_invalid_count / total_envelopes) if total_envelopes > 0 else 0.0

        x0_stats = None
        if x0_vals:
            x0_stats = {
                "count": len(x0_vals),
                "min": min(x0_vals),
                "max": max(x0_vals),
                "mean": sum(x0_vals) / len(x0_vals),
                "all_constant": len(set(x0_vals)) == 1 if len(x0_vals) > 10 else False,
            }

        ldr_stats = None
        if ldr_vals:
            ldr_stats = {
                "count": len(ldr_vals),
                "min": min(ldr_vals),
                "max": max(ldr_vals),
                "mean": sum(ldr_vals) / len(ldr_vals),
            }

        return {
            "dev": dev,
            "window": window,
            "total_samples": total_envelopes,
            "dht_valid_count": dht_valid_count,
            "dht_invalid_count": dht_invalid_count,
            "dht_invalid_ratio": inv_ratio,
            "x0_raw_stats": x0_stats,
            "ldr_raw_stats": ldr_stats,
        }

    @classmethod
    def audit_sequence_integrity(
        cls,
        query_service: TelemetryQueryService,
        dev: str,
        msg_type: str = "telem",
        window: str = "-15m",
        transport: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit sequence continuity, missed packets, and reboot occurrences.

        A device reboot is indicated by an uptime_ms drop or sequence reset.
        """
        envelopes = query_service.get_raw_envelopes(
            dev=dev,
            msg_type=msg_type,
            start=window,
            stop="now()",
            transport=transport,
            limit=1000,
            deduplicate=True,
        )

        if len(envelopes) < 2:
            return {
                "dev": dev,
                "msg_type": msg_type,
                "total_observations": len(envelopes),
                "sequence_gaps": 0,
                "reboots_detected": 0,
                "out_of_order_count": 0,
            }

        seq_gaps = 0
        reboots = 0
        out_of_order = 0

        for i in range(1, len(envelopes)):
            prev = envelopes[i - 1]
            curr = envelopes[i]

            # Reboot check: monotonic uptime dropped significantly
            if curr.uptime_ms < prev.uptime_ms:
                reboots += 1
                continue

            seq_diff = curr.seq - prev.seq
            if seq_diff > 1:
                seq_gaps += (seq_diff - 1)
            elif seq_diff < 0:
                out_of_order += 1

        return {
            "dev": dev,
            "msg_type": msg_type,
            "total_observations": len(envelopes),
            "sequence_gaps": seq_gaps,
            "reboots_detected": reboots,
            "out_of_order_count": out_of_order,
        }
