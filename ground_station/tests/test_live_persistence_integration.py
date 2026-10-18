"""Live end-to-end integration tests: NexusHostManager -> InfluxDBWriter -> InfluxDB.

Validates the full pipeline:
  Synthetic raw data -> FakeTransport -> NexusHostManager (parse, track, dispatch)
                     -> registered consumer -> InfluxDBWriter (batch, retry, queue)
                     -> InfluxDB (local service)

Exercises Protocol v1 telemetry envelopes, sensor suppression on invalid DHT,
non-telemetry envelopes, malformed envelopes, and duplicate delivery.
Cleanly skips if local InfluxDB service is not reachable.
"""

import os
import time
import unittest
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

from ground_station.connection_manager.nexus_host_manager import (
    NexusHostManager,
    QueueFullPolicy,
)
from ground_station.persistence.influxdb_writer import (
    InfluxDBConfig,
    InfluxDBWriter,
)
from ground_station.tests.fake_transports import FakeTransport

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None


def load_env_file(path: str = ".env") -> Dict[str, str]:
    """Parse local .env file safely without third-party dependencies."""
    env = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env


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
class TestLivePersistenceIntegration(unittest.TestCase):
    """End-to-end integration test against running InfluxDB instance."""

    def setUp(self) -> None:
        merged_env = {**load_env_file(), **os.environ}
        self.config = InfluxDBConfig.from_env(merged_env)
        # Use short flush interval and batch size 1 for responsive test execution
        self.config.flush_interval_sec = 0.05
        self.config.batch_size = 1

        self.test_run_id = uuid.uuid4().hex[:8]
        self.dev_id = f"nexus_val_{self.test_run_id}"

        self.transport = FakeTransport(name="fake_serial")
        self.manager = NexusHostManager(queue_capacity=50)
        self.writer = InfluxDBWriter(config=self.config, name="test_influxdb_writer")

        # Independent client for reading back data
        self.query_client: Optional[InfluxDBClient] = InfluxDBClient(
            url=self.config.url,
            token=self.config.token,
            org=self.config.org,
            timeout=self.config.timeout_ms,
        )

        # Wire pipeline: Transport -> Manager -> Writer
        self.manager.register_transport(self.transport)
        self.manager.register_consumer(self.writer.write_envelope)

        self.writer.start()
        self.manager.start()

    def tearDown(self) -> None:
        try:
            self.manager.unregister_consumer(self.writer.write_envelope)
        finally:
            try:
                self.manager.stop()
            finally:
                try:
                    stopped = self.writer.stop(timeout=5.0)
                    self.assertTrue(stopped, "Writer worker thread did not stop within timeout")
                    stats = self.writer.get_stats()
                    self.assertFalse(stats.is_worker_alive, "Writer worker thread still alive after stop")
                    self.assertFalse(stats.is_shutdown_timed_out, "Writer flagged shutdown timed out")
                finally:
                    if self.query_client is not None:
                        self.query_client.close()
                        self.query_client = None

    def _wait_for_successful_writes(self, target_count: int, timeout: float = 3.0) -> None:
        """Poll writer statistics until target_count successful writes are confirmed."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.writer.get_stats().successful_writes >= target_count:
                return
            time.sleep(0.02)
        self.fail(
            f"Timed out waiting for {target_count} writes; current stats: {self.writer.get_stats()}"
        )

    def _query_records(self, measurement: str, dev_id: str, seq: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query InfluxDB for pivoted records matching measurement and dev_id."""
        query_api = self.query_client.query_api()
        flux_filter_seq = f'|> filter(fn: (r) => r["seq"] == {seq})' if seq is not None else ""
        query = f'''
        from(bucket: "{self.config.bucket}")
          |> range(start: -5m)
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["dev"] == "{dev_id}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          {flux_filter_seq}
        '''
        tables = query_api.query(query, org=self.config.org)
        results = []
        for table in tables:
            for record in table.records:
                results.append(record.values)
        return results

    def test_case_1_valid_telemetry_with_temp_and_hum(self) -> None:
        """Case 1: Valid telemetry envelope with active DHT sensor maps all fields accurately."""
        initial_mgr_stats = self.manager.get_stats()
        initial_writer_stats = self.writer.get_stats()

        raw_json = (
            f'{{"ver":1,"dev":"{self.dev_id}","seq":10,"type":"telem",'
            f'"uptime":10500,"ldr":1520,"x0":2510,"dht_valid":true,"temp":23.5,"hum":45.2}}\n'
        )

        self.transport.feed(raw_json)
        self._wait_for_successful_writes(initial_writer_stats.successful_writes + 1)

        # Verify manager metrics
        mgr_stats = self.manager.get_stats()
        self.assertEqual(mgr_stats.messages_received, initial_mgr_stats.messages_received + 1)
        self.assertEqual(mgr_stats.messages_parsed, initial_mgr_stats.messages_parsed + 1)
        self.assertEqual(mgr_stats.parse_errors, initial_mgr_stats.parse_errors)

        # Verify InfluxDB storage
        records = self._query_records("nexus_telem", self.dev_id, seq=10)
        self.assertEqual(len(records), 1)
        rec = records[0]

        # Tags
        self.assertEqual(rec["dev"], self.dev_id)
        self.assertEqual(rec["transport"], "fake_serial")
        self.assertEqual(rec["type"], "telem")

        # Fields & Types
        self.assertEqual(rec["seq"], 10)
        self.assertEqual(rec["uptime_ms"], 10500)
        self.assertEqual(rec["ldr_raw"], 1520)
        self.assertEqual(rec["x0_raw"], 2510)
        self.assertIs(rec["dht_valid"], True)
        self.assertAlmostEqual(rec["temp"], 23.5, places=1)
        self.assertAlmostEqual(rec["hum"], 45.2, places=1)

    def test_case_2_invalid_dht_suppresses_temp_and_hum(self) -> None:
        """Case 2: Telemetry with dht_valid=false suppresses temp and hum fields."""
        initial_writer_stats = self.writer.get_stats()

        raw_json = (
            f'{{"ver":1,"dev":"{self.dev_id}","seq":20,"type":"telem",'
            f'"uptime":12000,"ldr":1800,"x0":2900,"dht_valid":false,"temp":0.0,"hum":0.0}}\n'
        )

        self.transport.feed(raw_json)
        self._wait_for_successful_writes(initial_writer_stats.successful_writes + 1)

        records = self._query_records("nexus_telem", self.dev_id, seq=20)
        self.assertEqual(len(records), 1)
        rec = records[0]

        self.assertEqual(rec["seq"], 20)
        self.assertEqual(rec["uptime_ms"], 12000)
        self.assertEqual(rec["ldr_raw"], 1800)
        self.assertEqual(rec["x0_raw"], 2900)
        self.assertIs(rec["dht_valid"], False)

        # Temperature and Humidity MUST be omitted from persisted fields
        self.assertNotIn("temp", rec)
        self.assertNotIn("hum", rec)

    def test_case_3_non_telemetry_heartbeat(self) -> None:
        """Case 3: Non-telemetry envelope (heartbeat) maps to nexus_hb with proper fields."""
        initial_writer_stats = self.writer.get_stats()

        raw_json = (
            f'{{"ver":1,"dev":"{self.dev_id}","seq":30,"type":"hb",'
            f'"uptime":15000,"heap":215000,"ticks":25}}\n'
        )

        self.transport.feed(raw_json)
        self._wait_for_successful_writes(initial_writer_stats.successful_writes + 1)

        records = self._query_records("nexus_hb", self.dev_id, seq=30)
        self.assertEqual(len(records), 1)
        rec = records[0]

        self.assertEqual(rec["dev"], self.dev_id)
        self.assertEqual(rec["transport"], "fake_serial")
        self.assertEqual(rec["type"], "hb")
        self.assertEqual(rec["seq"], 30)
        self.assertEqual(rec["uptime_ms"], 15000)
        self.assertEqual(rec["free_heap"], 215000)
        self.assertEqual(rec["exec_ticks"], 25)

    def test_case_4_malformed_envelope_rejected_before_persistence(self) -> None:
        """Case 4: Malformed envelope is dropped by parser and never reaches persistence."""
        initial_mgr_stats = self.manager.get_stats()
        initial_writer_stats = self.writer.get_stats()

        # Malformed: seq is a string rather than an integer
        raw_json = f'{{"ver":1,"dev":"{self.dev_id}","seq":"not_an_int","type":"telem"}}\n'

        self.transport.feed(raw_json)
        time.sleep(0.1)

        # Manager recorded parse error
        mgr_stats = self.manager.get_stats()
        self.assertEqual(mgr_stats.parse_errors, initial_mgr_stats.parse_errors + 1)

        # Writer received nothing
        writer_stats = self.writer.get_stats()
        self.assertEqual(writer_stats.accepted_records, initial_writer_stats.accepted_records)
        self.assertEqual(writer_stats.successful_writes, initial_writer_stats.successful_writes)

        # Database contains no records for this device
        records = self._query_records("nexus_telem", self.dev_id)
        self.assertEqual(len(records), 0)

    def test_case_5_duplicate_envelope_behavior(self) -> None:
        """Case 5: Repeated envelopes receive distinct host timestamps and are stored as distinct points."""
        initial_writer_stats = self.writer.get_stats()

        raw_json = (
            f'{{"ver":1,"dev":"{self.dev_id}","seq":50,"type":"telem",'
            f'"uptime":20000,"ldr":1400,"x0":2300,"dht_valid":true,"temp":21.8,"hum":52.1}}\n'
        )

        # Send first copy
        self.transport.feed(raw_json)
        time.sleep(0.05)  # Ensure distinct host receive timestamps
        # Send duplicate copy
        self.transport.feed(raw_json)

        self._wait_for_successful_writes(initial_writer_stats.successful_writes + 2)

        records = self._query_records("nexus_telem", self.dev_id, seq=50)
        self.assertEqual(len(records), 2, "Expected 2 distinct points stored for duplicate delivery")

        time_0 = records[0]["_time"]
        time_1 = records[1]["_time"]
        self.assertNotEqual(time_0, time_1, "Each point must carry distinct host receive timestamps")


if __name__ == "__main__":
    unittest.main()
