"""NEXUS InfluxDB Point Mapper.

Transforms validated ParsedEnvelope objects into InfluxDB Points with strict tag/field
cardinality separation, precision preservation, and suppression of invalid sensor readings.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

try:
    from influxdb_client import Point, WritePrecision
except ImportError:
    Point = None
    WritePrecision = None

from ..connection_manager.envelope_parser import (
    CommandPayload,
    EventPayload,
    HeartbeatPayload,
    MessageType,
    ParsedEnvelope,
    ResponsePayload,
    StatusPayload,
    TelemetryPayload,
)

logger = logging.getLogger("nexus.point_mapper")


class PointMapper:
    """Maps NEXUS ParsedEnvelope instances to InfluxDB Point objects or structured dictionaries."""

    @staticmethod
    def to_dict(
        envelope: ParsedEnvelope,
        measurement_prefix: str = "nexus",
        use_single_measurement: bool = False,
    ) -> Dict[str, Any]:
        """Convert a ParsedEnvelope to an intermediate dictionary structure.

        Returns:
            Dict containing:
            - 'measurement': str
            - 'tags': Dict[str, str] (low-cardinality metadata)
            - 'fields': Dict[str, Union[int, float, bool, str]] (high-precision measurements)
            - 'time_ns': int (nanoseconds since Unix epoch)
        """
        # 1. Determine Measurement Name
        msg_type_str = envelope.msg_type.value
        if use_single_measurement:
            measurement = measurement_prefix
        else:
            measurement = f"{measurement_prefix}_{msg_type_str}"

        # 2. Stable Low-Cardinality Tags
        # Device identifier, message type, and transport provenance
        tags: Dict[str, str] = {
            "dev": envelope.dev,
            "type": msg_type_str,
            "transport": envelope.transport or "unknown",
        }

        # 3. Numeric & Telemetry Fields
        # Sequence number and device uptime are stored as FIELDS to avoid unbounded tag cardinality churn
        fields: Dict[str, Any] = {
            "seq": int(envelope.seq),
        }
        if envelope.uptime_ms is not None:
            fields["uptime_ms"] = int(envelope.uptime_ms)

        payload = envelope.payload

        if isinstance(payload, HeartbeatPayload):
            fields["free_heap"] = int(payload.free_heap)
            fields["exec_ticks"] = int(payload.exec_ticks)

        elif isinstance(payload, TelemetryPayload):
            fields["ldr_raw"] = int(payload.ldr_raw)
            fields["x0_raw"] = int(payload.x0_raw)
            fields["dht_valid"] = bool(payload.dht_valid)

            # Strict Missing-Data Semantics:
            # If dht_valid is False or temp/hum is None, DO NOT emit temperature or humidity fields.
            # Never fabricate 0.0 or 0 for missing/degraded sensor measurements.
            if payload.dht_valid:
                if payload.temp is not None:
                    fields["temp"] = float(payload.temp)
                if payload.hum is not None:
                    fields["hum"] = float(payload.hum)

            if payload.x1_raw is not None:
                fields["x1_raw"] = int(payload.x1_raw)
            if payload.slot_state is not None:
                fields["slot_state"] = int(payload.slot_state)
            if payload.dist_cm is not None:
                fields["dist_cm"] = float(payload.dist_cm)

        elif isinstance(payload, StatusPayload):
            fields["dispatched"] = int(payload.dispatched)
            fields["completed"] = int(payload.completed)
            fields["failed"] = int(payload.failed)
            fields["max_lat_us"] = int(payload.max_lat_us)
            fields["max_dur_us"] = int(payload.max_dur_us)

        elif isinstance(payload, EventPayload):
            # Event attributes are numeric fields, NOT tags, to prevent high tag cardinality
            fields["event_type"] = int(payload.event_type)
            fields["severity"] = int(payload.severity)
            fields["source_id"] = int(payload.source_id)
            fields["payload_val"] = int(payload.payload_val)

        elif isinstance(payload, (CommandPayload, ResponsePayload)):
            for k, v in payload.fields.items():
                if isinstance(v, (int, float, bool, str)):
                    fields[f"field_{k}"] = v

        else:
            logger.warning("Unrecognized envelope payload type: %s", type(payload).__name__)

        # 4. Host Receive Timestamp Semantics
        # The firmware produces uptime_ms, not UTC wall-clock time.
        # Point timestamp represents the host receive time (nanoseconds since Unix epoch).
        if envelope.received_at is not None:
            time_ns = int(envelope.received_at * 1e9)
        else:
            time_ns = time.time_ns()

        return {
            "measurement": measurement,
            "tags": tags,
            "fields": fields,
            "time_ns": time_ns,
        }

    @classmethod
    def to_point(
        cls,
        envelope: ParsedEnvelope,
        measurement_prefix: str = "nexus",
        use_single_measurement: bool = False,
    ) -> Any:
        """Convert a ParsedEnvelope to an influxdb_client.Point object.

        If influxdb_client is not installed, returns the intermediate dictionary.
        """
        data = cls.to_dict(
            envelope=envelope,
            measurement_prefix=measurement_prefix,
            use_single_measurement=use_single_measurement,
        )

        if Point is None:
            return data

        point = Point(data["measurement"])
        for tag_k, tag_v in data["tags"].items():
            point.tag(tag_k, tag_v)
        for field_k, field_v in data["fields"].items():
            point.field(field_k, field_v)

        if WritePrecision is not None:
            point.time(data["time_ns"], WritePrecision.NS)
        else:
            point.time(data["time_ns"])

        return point
