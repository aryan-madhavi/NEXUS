"""Live integration tests for NEXUS Telemetry Analysis and Query Engine.

Validates the typed query engine, full-window aggregations, deduplication,
and data quality audits against the running local InfluxDB service.

Cleanly skips if InfluxDB service at http://127.0.0.1:8086 is unreachable.
"""

import os
import time
import unittest
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Optional

from ground_station import load_env_file
from ground_station.analysis.quality import TelemetryQuality
from ground_station.analysis.telemetry_query import TelemetryQueryService
from ground_station.connection_manager.envelope_parser import (
    MessageType,
    ParsedEnvelope,
    TelemetryPayload,
)
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
class TestLiveTelemetryAnalysis(unittest.TestCase):
    """End-to-end integration tests for TelemetryQueryService against local InfluxDB."""

    @classmethod
    def setUpClass(cls) -> None:
        merged_env = {**load_env_file(), **os.environ}
        cls.config = InfluxDBConfig.from_env(merged_env)
        cls.config.flush_interval_sec = 0.05
        cls.config.batch_size = 1

        cls.query_service = TelemetryQueryService(config=cls.config)
        cls.test_run_id = uuid.uuid4().hex[:8]
        cls.dev_id = f"nexus_val_{cls.test_run_id}"

        # Seed synthetic telemetry batch with controlled valid/invalid DHT and dual transport
        cls._seed_test_telemetry()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.query_service.close()

    @classmethod
    def _seed_test_telemetry(cls) -> None:
        """Seed controlled test telemetry records into InfluxDB."""
        writer = InfluxDBWriter(config=cls.config, name="test_analysis_seeder")
        writer.start()

        now = time.time()

        def make_env(seq: int, uptime_ms: int, ldr: int, x0: int, dht_valid: bool, temp: Optional[float], hum: Optional[float], transport: str, offset: float) -> ParsedEnvelope:
            payload = TelemetryPayload(
                uptime_ms=uptime_ms,
                ldr_raw=ldr,
                x0_raw=x0,
                dht_valid=dht_valid,
                temp=temp,
                hum=hum,
            )
            return ParsedEnvelope(
                raw_bytes=b"",
                raw_text="",
                ver=1,
                dev=cls.dev_id,
                seq=seq,
                msg_type=MessageType.TELEMETRY,
                uptime_ms=uptime_ms,
                payload=payload,
                extra_fields={},
                raw_dict={},
                transport=transport,
                received_at=now - offset,
            )

        # 1. Valid telemetry via MQTT (seq=1, temp=22.0, dht_valid=True)
        env1 = make_env(seq=1, uptime_ms=1000, ldr=1100, x0=2100, dht_valid=True, temp=22.0, hum=45.0, transport="mqtt", offset=10.0)
        writer.write_envelope(env1)

        # 2. Dual-transport arrival (seq=2, temp=24.0, dht_valid=True): both MQTT and Serial
        env2_mqtt = make_env(seq=2, uptime_ms=2000, ldr=1150, x0=2150, dht_valid=True, temp=24.0, hum=46.0, transport="mqtt", offset=6.0)
        env2_serial = make_env(seq=2, uptime_ms=2000, ldr=1150, x0=2150, dht_valid=True, temp=24.0, hum=46.0, transport="serial", offset=5.98)
        writer.write_envelope(env2_mqtt)
        writer.write_envelope(env2_serial)

        # 3. Invalid DHT reading (seq=3, dht_valid=False, temp/hum suppressed)
        env3 = make_env(seq=3, uptime_ms=3000, ldr=1200, x0=2200, dht_valid=False, temp=None, hum=None, transport="mqtt", offset=2.0)
        writer.write_envelope(env3)

        # Wait for writes to flush to InfluxDB
        deadline = time.time() + 4.0
        while time.time() < deadline:
            stats = writer.get_stats()
            if stats.successful_writes >= 4:
                break
            time.sleep(0.05)

        writer.stop(timeout=3.0)

    def test_01_health_check_and_latency_baseline(self) -> None:
        """Verify InfluxDB health reporting and capture measured query latency."""
        health = self.query_service.check_health()
        self.assertEqual(health["status"], "pass")
        self.assertIsNotNone(health["latency_ms"])
        # Report actual measured latency; verify it completes well within bounds
        print(f"\n[Live InfluxDB Health] Status: {health['status']}, Latency: {health['latency_ms']:.2f} ms")
        self.assertLess(health["latency_ms"], 500.0)

    def test_02_get_latest_reading_and_timestamp_distinction(self) -> None:
        """Verify latest reading accurately captures values and distinguishes host time from uptime_ms."""
        record = self.query_service.get_latest_reading(self.dev_id, "ldr_raw")
        self.assertIsNotNone(record)
        self.assertEqual(record.dev, self.dev_id)
        self.assertEqual(record.field, "ldr_raw")
        self.assertEqual(record.value, 1200)

        # Verify host_time is datetime and distinctly separate from device uptime_ms
        self.assertIsInstance(record.host_time, datetime)
        self.assertEqual(record.host_time.tzinfo, timezone.utc)

    def test_03_canonical_observation_deduplication(self) -> None:
        """Verify that simultaneous dual-transport envelopes collapse into a single ObservationEvent."""
        events = self.query_service.get_raw_envelopes(
            dev=self.dev_id,
            msg_type="telem",
            start="-5m",
            deduplicate=True,
        )

        # 3 unique physical ticks were generated (seq 1, seq 2, seq 3), even though 4 envelopes were written
        seq_map = {e.seq: e for e in events}
        self.assertIn(2, seq_map)
        ev2 = seq_map[2]
        self.assertEqual(ev2.uptime_ms, 2000)
        # Provenance: both MQTT and Serial captured
        self.assertEqual(sorted(ev2.transports), ["mqtt", "serial"])
        self.assertEqual(ev2.fields.get("temp"), 24.0)

    def test_04_full_window_statistics_and_invalid_data_accounting(self) -> None:
        """Verify full-window statistics accurately compute min/max/mean and count invalid readings."""
        start_time = time.perf_counter()
        summary = self.query_service.get_window_statistics(
            dev=self.dev_id,
            signal="temp",
            start="-15m",
            stop="now()",
            transport="mqtt",
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        print(f"[Live InfluxDB Stats Latency] temp summary: {elapsed_ms:.2f} ms (Target: <50ms)")

        # In MQTT: seq 1 had temp=22.0, seq 2 had temp=24.0 -> 2 valid samples
        self.assertEqual(summary.sample_count, 2)
        # seq 3 had dht_valid=False -> 1 confirmed invalid reading
        self.assertEqual(summary.invalid_count, 1)
        self.assertAlmostEqual(summary.min_value, 22.0, places=1)
        self.assertAlmostEqual(summary.max_value, 24.0, places=1)
        self.assertAlmostEqual(summary.mean_value, 23.0, places=1)
        self.assertFalse(summary.is_truncated, "Full window statistics must never be marked truncated")

    def test_05_freshness_reporting(self) -> None:
        """Verify freshness report calculates elapsed age against expected cadence."""
        report = TelemetryQuality.get_freshness(
            self.query_service,
            dev=self.dev_id,
            msg_type="telem",
            cadence_sec=2.0,
            grace_factor=3.0,
        )

        self.assertEqual(report.dev, self.dev_id)
        self.assertIsNotNone(report.last_seen_host)
        self.assertIsNotNone(report.age_seconds)
        self.assertEqual(report.expected_cadence_sec, 2.0)


if __name__ == "__main__":
    unittest.main()
