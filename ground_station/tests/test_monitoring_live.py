"""Live integration tests for NEXUS Monitoring Service (M7.2).

Validates end-to-end monitoring evaluation, data-source health checks,
and durable incident lifecycle against live InfluxDB if available.

Cleanly skips if InfluxDB service at http://127.0.0.1:8086 is unreachable.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import urllib.request
import uuid
from pathlib import Path

from ground_station import load_env_file
from ground_station.analysis.telemetry_query import TelemetryQueryService
from ground_station.connection_manager.envelope_parser import (
    MessageType,
    ParsedEnvelope,
    TelemetryPayload,
)
from ground_station.monitoring.models import DataSourceStatus
from ground_station.monitoring.rules import TelemetryFreshnessRule
from ground_station.monitoring.service import MonitoringConfig, MonitoringService
from ground_station.monitoring.store import IncidentStore
from ground_station.persistence.influxdb_writer import (
    InfluxDBConfig,
    InfluxDBWriter,
)

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None


def is_local_influxdb_available(url: str = "http://127.0.0.1:8086", timeout: float = 1.0) -> bool:
    """Return True if local InfluxDB service responds with 200 OK on /health."""
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


@unittest.skipUnless(
    InfluxDBClient is not None and is_local_influxdb_available(),
    "InfluxDBClient or local InfluxDB service at http://127.0.0.1:8086 not available",
)
class TestLiveMonitoringService(unittest.TestCase):
    """End-to-end live integration tests for MonitoringService against InfluxDB."""

    @classmethod
    def setUpClass(cls) -> None:
        merged_env = {**load_env_file(), **os.environ}
        cls.config = InfluxDBConfig.from_env(merged_env)
        cls.config.flush_interval_sec = 0.05
        cls.config.batch_size = 1

        cls.writer = InfluxDBWriter(config=cls.config)
        cls.writer.start()

        cls.query_service = TelemetryQueryService(config=cls.config)
        cls.test_device = f"mon_live_{uuid.uuid4().hex[:6]}"

        # Write fresh telemetry point
        payload = TelemetryPayload(
            uptime_ms=1000,
            ldr_raw=400,
            x0_raw=350,
            dht_valid=True,
            temp=23.5,
            hum=55.0,
        )
        env = ParsedEnvelope(
            raw_bytes=b"",
            raw_text="",
            ver=1,
            dev=cls.test_device,
            seq=1,
            msg_type=MessageType.TELEMETRY,
            uptime_ms=1000,
            payload=payload,
            extra_fields={},
            raw_dict={},
            transport="mqtt",
            received_at=time.time(),
        )
        cls.writer.write_envelope(env)
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "writer"):
            cls.writer.stop()
        if hasattr(cls, "query_service"):
            cls.query_service.close()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "live_incidents.db")
        self.store = IncidentStore(self.db_path)

        mon_config = MonitoringConfig(
            devices=[self.test_device],
            db_path=self.db_path,
            normal_interval_sec=1.0,
            active_interval_sec=0.5,
        )
        self.service = MonitoringService(
            config=mon_config,
            query_service=self.query_service,
            store=self.store,
            auto_register_default_rules=False,
        )

    def tearDown(self) -> None:
        self.service.close()
        self.temp_dir.cleanup()

    def test_live_data_source_health_and_evaluation(self) -> None:
        """Verify data source health against live InfluxDB and evaluation report."""
        ds_health = self.service.check_data_source_health()
        self.assertEqual(ds_health.status, DataSourceStatus.HEALTHY)
        self.assertGreater(ds_health.response_time_ms, 0.0)

        # Freshness rule on freshly written point should be healthy (cleared)
        freshness_rule = TelemetryFreshnessRule(
            cadence_sec=2.0,
            grace_factor=30.0,  # Generous grace so freshly written point is fresh
            confirm_clear_count=1,
        )
        self.service.register_rule(freshness_rule)

        report = self.service.evaluate_once()
        self.assertEqual(report.newly_opened, [])
        self.assertEqual(self.service.get_active_incidents(), [])
