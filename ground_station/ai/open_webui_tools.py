"""title: NEXUS Telemetry & Monitoring Tools
author: NEXUS Ground Station
description: Read-only operational tools for querying NEXUS ESP32 telemetry, freshness, sensor quality, statistics, trends, and monitoring incidents.
version: 1.0.0
license: MIT
requirements: pydantic, influxdb-client>=1.36.0
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure NEXUS repository root is present in sys.path when executed in Open WebUI's process
_repo_candidates = [
    os.environ.get("NEXUS_ROOT", ""),
    str(Path(__file__).resolve().parent.parent.parent),
    "/home/aryan/Projects/SPIT/NEXUS",
]
for _candidate in _repo_candidates:
    if _candidate and os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

logger = logging.getLogger("nexus.ai.open_webui")


class Tools:
    """Read-only operational tools for NEXUS Ground Station telemetry and monitoring.

    Connects Open WebUI operators to validated InfluxDB telemetry and SQLite incident records.
    Strictly read-only: cannot actuate hardware, mutate thresholds, delete records, or send commands.
    """

    def __init__(self) -> None:
        """Initialize tools with underlying NEXUS AI tool implementation."""
        # Lazily import to avoid circular dependencies or heavy initialization if module is only inspected
        from ground_station.ai.tools import NexusAITools
        self._tools = NexusAITools()

    def get_latest_telemetry(self, device_id: str = "esp32_01") -> str:
        """Get latest telemetry readings (temperature, humidity, LDR raw ADC, X0 raw ADC, DHT validity).

        Note: x0_raw_adc is the raw numeric ADC count (0-4095) from MUX channel 0; report its numeric count as uncalibrated raw ADC, not gas ppm.
        Temperature and humidity are null if dht_valid is False to prevent invalid data interpretation.

        :param device_id: Device identifier (e.g. 'esp32_01', 'nexus_esp32').
        :return: JSON formatted string containing latest sensor observations and reception metadata.
        """
        try:
            res = self._tools.get_latest_telemetry(device_id=device_id)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_latest_telemetry: %s", e)
            return json.dumps({"success": False, "error": f"Failed to retrieve telemetry: {e}"})

    def get_telemetry_freshness(self, device_id: str = "esp32_01", msg_type: str = "telem") -> str:
        """Inspect telemetry arrival age, expected cadence, and stale status.

        :param device_id: Device identifier (default: 'esp32_01').
        :param msg_type: Message type to evaluate ('telem', 'hb', or 'status'). Default: 'telem'.
        :return: JSON formatted string detailing freshness status, arrival lag, and last sequence number.
        """
        try:
            res = self._tools.get_telemetry_freshness(device_id=device_id, msg_type=msg_type)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_telemetry_freshness: %s", e)
            return json.dumps({"success": False, "error": f"Failed to check freshness: {e}"})

    def get_signal_statistics(
        self,
        device_id: str = "esp32_01",
        signal: str = "temp",
        window: str = "-15m",
    ) -> str:
        """Compute summary statistics (min, max, mean, count) for a signal over a bounded window without truncation.

        :param device_id: Device identifier (default: 'esp32_01').
        :param signal: Permitted signal name ('temp', 'hum', 'ldr_raw', 'x0_raw', 'x1_raw', 'slot_state', 'dist_cm', 'free_heap', 'exec_ticks').
        :param window: Relative duration window (e.g. '-15m', '-1h', '-24h'). Default: '-15m'.
        :return: JSON formatted string containing statistical aggregates.
        """
        try:
            res = self._tools.get_signal_statistics(device_id=device_id, signal=signal, window=window)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_signal_statistics: %s", e)
            return json.dumps({"success": False, "error": f"Failed to compute statistics: {e}"})

    def get_signal_trend(
        self,
        device_id: str = "esp32_01",
        signal: str = "temp",
        window: str = "-15m",
    ) -> str:
        """Compute rate-of-change slope and directional trend (RISING, FALLING, STABLE) over a time window.

        :param device_id: Device identifier (default: 'esp32_01').
        :param signal: Numeric signal name ('temp', 'hum', 'ldr_raw', 'x0_raw', 'x1_raw', 'slot_state', 'dist_cm', 'free_heap').
        :param window: Relative duration window (e.g. '-15m', '-1h'). Default: '-15m'.
        :return: JSON formatted string containing trend direction, slope per minute, and delta.
        """
        try:
            res = self._tools.get_signal_trend(device_id=device_id, signal=signal, window=window)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_signal_trend: %s", e)
            return json.dumps({"success": False, "error": f"Failed to compute trend: {e}"})

    def audit_sensor_quality(
        self,
        device_id: str = "esp32_01",
        window: str = "-15m",
    ) -> str:
        """Audit sensor reading quality flags and invalid sample ratios over an evaluation window.

        :param device_id: Device identifier (default: 'esp32_01').
        :param window: Relative duration window (e.g. '-15m', '-1h'). Default: '-15m'.
        :return: JSON formatted string detailing total envelopes, valid DHT count, and invalid ratio.
        """
        try:
            res = self._tools.audit_sensor_quality(device_id=device_id, window=window)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in audit_sensor_quality: %s", e)
            return json.dumps({"success": False, "error": f"Failed to audit sensor quality: {e}"})

    def get_active_incidents(self, device_id: Optional[str] = None) -> str:
        """Query currently active (OPEN) operational incidents, including severity, summary, and opening evidence.

        :param device_id: Optional device identifier to filter incidents. If omitted, checks all devices.
        :return: JSON formatted string containing active incidents list and metadata.
        """
        try:
            res = self._tools.get_active_incidents(device_id=device_id)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_active_incidents: %s", e)
            return json.dumps({"success": False, "error": f"Failed to query active incidents: {e}"})

    def get_incident_history(
        self,
        device_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """Query bounded historical incidents (both resolved and active) with timestamps and severities.

        :param device_id: Optional device identifier filter.
        :param rule_id: Optional rule identifier filter (e.g. 'stale_telemetry', 'dht_sensor_invalid').
        :param limit: Maximum incidents to return (clamped between 1 and 50, default: 10).
        :return: JSON formatted string containing chronological incident history.
        """
        try:
            res = self._tools.get_incident_history(device_id=device_id, rule_id=rule_id, limit=limit)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_incident_history: %s", e)
            return json.dumps({"success": False, "error": f"Failed to query incident history: {e}"})

    def get_incident_details(self, incident_id: str) -> str:
        """Retrieve full details, opening/resolving evidence, and chronological transitions for a specific incident.

        :param incident_id: Unique incident identifier (e.g. 'inc_stale_telemetry_...').
        :return: JSON formatted string detailing incident lifecycle, triggers, and state transitions.
        """
        try:
            res = self._tools.get_incident_details(incident_id=incident_id)
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_incident_details: %s", e)
            return json.dumps({"success": False, "error": f"Failed to retrieve incident details: {e}"})

    def get_system_status(self) -> str:
        """Inspect telemetry database connection health and overall monitoring state.

        :return: JSON formatted string containing InfluxDB health and active incident counts.
        """
        try:
            res = self._tools.get_system_status()
            return json.dumps(res.to_dict(), default=str)
        except Exception as e:
            logger.error("Error in get_system_status: %s", e)
            return json.dumps({"success": False, "error": f"Failed to get system status: {e}"})
