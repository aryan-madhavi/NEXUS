"""Unit tests for InfluxDBWriter.

Validates bounded queuing, batching, transient retry recovery, permanent retry exhaustion,
clean shutdown flushes, offline execution, and token credential safety.
"""

import threading
import time
import unittest
from typing import Any, List, Optional

from ground_station.connection_manager.envelope_parser import EnvelopeParser, ParsedEnvelope
from ground_station.persistence.base import PersistenceQueuePolicy
from ground_station.persistence.influxdb_writer import (
    InfluxDBConfig,
    InfluxDBWriter,
)


class MockWriteApi:
    """Mock InfluxDB WriteApi tracking batches and simulating network failures."""

    def __init__(self) -> None:
        self.batches: List[dict] = []
        self.fail_countdown = 0
        self.error_to_raise: Exception = RuntimeError("Simulated connection timeout to InfluxDB")
        self.block_event: Optional[threading.Event] = None
        self.entered_write_event: Optional[threading.Event] = None

    def write(self, bucket: str, org: str, record: Any) -> None:
        if self.entered_write_event is not None:
            self.entered_write_event.set()
        if self.block_event is not None:
            self.block_event.wait()

        if self.fail_countdown > 0:
            self.fail_countdown -= 1
            raise self.error_to_raise

        items = list(record) if isinstance(record, (list, tuple)) else [record]
        self.batches.append({
            "bucket": bucket,
            "org": org,
            "record": items,
        })


class MockInfluxDBClient:
    """Mock InfluxDBClient for offline testing without network access."""

    def __init__(self, *args, **kwargs) -> None:
        self.write_api_mock = MockWriteApi()
        self.closed = False

    def write_api(self, write_options: Any = None) -> MockWriteApi:
        return self.write_api_mock

    def close(self) -> None:
        self.closed = True


class TestInfluxDBWriter(unittest.TestCase):
    """Test suite for InfluxDBWriter."""

    def _make_env(self, seq: int, msg_type: str = "hb") -> ParsedEnvelope:
        raw = f'{{"ver":1,"dev":"nexus_esp32","seq":{seq},"type":"{msg_type}","uptime":1000,"heap":200000,"ticks":10}}\n'
        env = EnvelopeParser.parse(raw)
        return env.__class__(
            raw_bytes=env.raw_bytes,
            raw_text=env.raw_text,
            ver=env.ver,
            dev=env.dev,
            seq=env.seq,
            msg_type=env.msg_type,
            uptime_ms=env.uptime_ms,
            payload=env.payload,
            extra_fields=env.extra_fields,
            raw_dict=env.raw_dict,
            transport="serial",
            received_at=time.time(),
        )

    def test_no_client_on_import_or_construction(self):
        client_created = False

        def factory(cfg):
            nonlocal client_created
            client_created = True
            return MockInfluxDBClient()

        config = InfluxDBConfig(client_factory=factory)
        writer = InfluxDBWriter(config=config)

        self.assertFalse(client_created)
        self.assertFalse(writer.is_running)
        self.assertFalse(writer.is_connected)

    def test_batch_flush_on_size_threshold(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            batch_size=3,
            flush_interval_sec=10.0,  # Long interval: flush must be triggered by size
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        # Submit 3 envelopes
        for i in range(1, 4):
            ok = writer.write_envelope(self._make_env(i))
            self.assertTrue(ok)

        # Allow worker thread a brief moment to process the batch
        time.sleep(0.08)
        writer.stop()

        self.assertEqual(len(mock_client.write_api_mock.batches), 1)
        self.assertEqual(len(mock_client.write_api_mock.batches[0]["record"]), 3)

        stats = writer.get_stats()
        self.assertEqual(stats.accepted_records, 3)
        self.assertEqual(stats.successful_writes, 3)
        self.assertEqual(stats.write_failures, 0)
        self.assertEqual(stats.queue_drops, 0)
        self.assertTrue(mock_client.closed)

    def test_periodic_flush_interval(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            batch_size=10,  # Large batch size: flush must be triggered by time
            flush_interval_sec=0.05,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        # Send only 1 envelope (< batch_size 10)
        writer.write_envelope(self._make_env(100))

        # Wait for periodic timer to trigger
        time.sleep(0.12)
        writer.stop()

        self.assertEqual(len(mock_client.write_api_mock.batches), 1)
        self.assertEqual(len(mock_client.write_api_mock.batches[0]["record"]), 1)
        self.assertEqual(writer.get_stats().successful_writes, 1)

    def test_queue_overflow_drop_newest(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            max_queue_size=2,
            queue_policy=PersistenceQueuePolicy.DROP_NEWEST,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        # Note: Do not start writer yet, so queue fills up deterministically
        writer._is_running = True  # Enable write acceptance without starting worker loop

        self.assertTrue(writer.write_envelope(self._make_env(1)))
        self.assertTrue(writer.write_envelope(self._make_env(2)))
        # 3rd item exceeds capacity -> must be dropped
        self.assertFalse(writer.write_envelope(self._make_env(3)))

        stats = writer.get_stats()
        self.assertEqual(stats.accepted_records, 2)
        self.assertEqual(stats.queue_drops, 1)
        self.assertEqual(stats.queue_size, 2)

    def test_queue_overflow_drop_oldest(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            max_queue_size=2,
            queue_policy=PersistenceQueuePolicy.DROP_OLDEST,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer._is_running = True

        self.assertTrue(writer.write_envelope(self._make_env(1)))
        self.assertTrue(writer.write_envelope(self._make_env(2)))
        # 3rd item evicts seq 1, enqueues seq 3
        self.assertTrue(writer.write_envelope(self._make_env(3)))

        stats = writer.get_stats()
        self.assertEqual(stats.accepted_records, 3)
        self.assertEqual(stats.queue_drops, 1)
        self.assertEqual(stats.queue_size, 2)

        # Verify queued items are seq 2 and seq 3
        q_item1 = writer._queue.get_nowait()
        q_item2 = writer._queue.get_nowait()
        self.assertEqual(q_item1.seq, 2)
        self.assertEqual(q_item2.seq, 3)

    def test_transient_write_failure_retry_success(self):
        mock_client = MockInfluxDBClient()
        # Fail 1 attempt, succeed on 2nd attempt
        mock_client.write_api_mock.fail_countdown = 1

        config = InfluxDBConfig(
            batch_size=1,
            max_retries=3,
            retry_base_delay_sec=0.01,
            retry_max_delay_sec=0.05,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(55))
        time.sleep(0.1)

        stats = writer.get_stats()
        self.assertEqual(stats.retries_attempted, 1)
        self.assertEqual(stats.write_failures, 1)
        self.assertEqual(stats.successful_writes, 1)
        self.assertEqual(stats.retries_exhausted_drops, 0)
        self.assertTrue(stats.is_connected)

        writer.stop()

    def test_permanent_failure_retry_exhaustion_drops_batch(self):
        mock_client = MockInfluxDBClient()
        # Fail indefinitely
        mock_client.write_api_mock.fail_countdown = 999

        config = InfluxDBConfig(
            batch_size=2,
            max_retries=2,
            retry_base_delay_sec=0.01,
            retry_max_delay_sec=0.02,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(1))
        writer.write_envelope(self._make_env(2))

        # Wait for initial attempt (1) + 2 retries to exhaust
        time.sleep(0.15)
        writer.stop()

        stats = writer.get_stats()
        self.assertEqual(stats.retries_exhausted_drops, 2)
        self.assertEqual(stats.successful_writes, 0)
        self.assertEqual(stats.retries_attempted, 2)
        self.assertEqual(stats.write_failures, 3)  # 1 initial + 2 retries
        self.assertFalse(stats.is_connected)
        self.assertIsNotNone(stats.last_error)

    def test_worker_shutdown_flushes_pending_records(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            batch_size=10,  # Large batch size
            flush_interval_sec=10.0,  # Long timer
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        # Submit 3 items (below batch threshold)
        for i in range(1, 4):
            writer.write_envelope(self._make_env(i))

        # Immediate shutdown must flush before closing
        writer.stop(timeout=1.0)

        self.assertEqual(len(mock_client.write_api_mock.batches), 1)
        self.assertEqual(len(mock_client.write_api_mock.batches[0]["record"]), 3)
        self.assertEqual(writer.get_stats().successful_writes, 3)
        self.assertTrue(mock_client.closed)

    def test_token_credential_safety_in_repr(self):
        cfg = InfluxDBConfig(token="super_secret_token_12345")
        representation = repr(cfg)

        self.assertNotIn("super_secret_token_12345", representation)
        self.assertIn("***", representation)

    def test_isolation_write_envelope_never_blocks(self):
        mock_client = MockInfluxDBClient()
        mock_client.write_api_mock.fail_countdown = 999
        config = InfluxDBConfig(client_factory=lambda cfg: mock_client)
        writer = InfluxDBWriter(config=config)
        writer.start()

        start = time.monotonic()
        for i in range(10):
            writer.write_envelope(self._make_env(i))
        duration = time.monotonic() - start

        # All 10 submissions must complete instantly in microseconds (< 0.05s)
        self.assertLess(duration, 0.05)
        writer.stop()

    def test_stop_with_empty_queue(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(client_factory=lambda cfg: mock_client)
        writer = InfluxDBWriter(config=config)
        writer.start()
        self.assertTrue(writer.is_running)

        writer.stop(timeout=1.0)
        self.assertFalse(writer.is_running)
        self.assertTrue(mock_client.closed)
        stats = writer.get_stats()
        self.assertEqual(stats.accepted_records, 0)
        self.assertEqual(stats.successful_writes, 0)

    def test_stop_when_queue_contains_more_than_one_batch(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            batch_size=2,
            flush_interval_sec=10.0,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        # Enqueue 5 items (must drain into: batch of 2, batch of 2, batch of 1)
        for i in range(1, 6):
            writer.write_envelope(self._make_env(i))

        writer.stop(timeout=1.0)

        total_points = sum(len(b["record"]) for b in mock_client.write_api_mock.batches)
        self.assertEqual(total_points, 5)
        for b in mock_client.write_api_mock.batches:
            self.assertLessEqual(len(b["record"]), 2)
        self.assertEqual(writer.get_stats().successful_writes, 5)

    def test_stop_while_write_is_blocked_respects_deadline(self):
        mock_client = MockInfluxDBClient()
        unblock_event = threading.Event()
        entered_write = threading.Event()
        mock_client.write_api_mock.block_event = unblock_event
        mock_client.write_api_mock.entered_write_event = entered_write

        config = InfluxDBConfig(
            batch_size=1,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(1))
        self.assertTrue(entered_write.wait(timeout=1.0))

        # stop() with short timeout of 0.1s must return promptly despite blocked write
        start = time.monotonic()
        stopped = writer.stop(timeout=0.1)
        duration = time.monotonic() - start

        self.assertLess(duration, 0.4)
        self.assertFalse(stopped)
        self.assertFalse(writer.is_running)
        self.assertTrue(writer.is_worker_alive)
        self.assertTrue(writer.is_shutdown_timed_out)

        # Unblock worker thread to allow clean exit
        unblock_event.set()
        time.sleep(0.05)
        self.assertFalse(writer.is_worker_alive)
        self.assertFalse(writer.is_shutdown_timed_out)

    def test_stop_during_retry_backoff_interrupts_sleep(self):
        mock_client = MockInfluxDBClient()
        mock_client.write_api_mock.fail_countdown = 999
        config = InfluxDBConfig(
            batch_size=1,
            max_retries=3,
            retry_base_delay_sec=5.0,  # 5-second long backoff delay
            retry_max_delay_sec=10.0,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(1))
        # Give worker a moment to execute attempt 1 and enter backoff wait
        time.sleep(0.05)

        start = time.monotonic()
        writer.stop(timeout=1.0)
        duration = time.monotonic() - start

        # Must interrupt backoff sleep immediately (< 0.5s instead of waiting 5.0s)
        self.assertLess(duration, 0.5)
        self.assertFalse(writer.is_running)

    def test_repeated_start_and_stop_lifecycle(self):
        mock_client1 = MockInfluxDBClient()
        mock_client2 = MockInfluxDBClient()
        clients = [mock_client1, mock_client2]

        config = InfluxDBConfig(
            batch_size=1,
            client_factory=lambda cfg: clients.pop(0),
        )
        writer = InfluxDBWriter(config=config)

        # 1. First cycle
        writer.start()
        writer.start()  # Redundant start
        self.assertTrue(writer.is_running)
        writer.write_envelope(self._make_env(1))
        time.sleep(0.05)
        writer.stop()
        writer.stop()  # Redundant stop
        self.assertFalse(writer.is_running)
        self.assertEqual(writer.get_stats().successful_writes, 1)

        # 2. Second cycle
        writer.start()
        self.assertTrue(writer.is_running)
        writer.write_envelope(self._make_env(2))
        time.sleep(0.05)
        writer.stop()
        self.assertFalse(writer.is_running)
        self.assertEqual(writer.get_stats().successful_writes, 2)

    def test_attempted_enqueue_before_start_and_after_stop(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(client_factory=lambda cfg: mock_client)
        writer = InfluxDBWriter(config=config)

        # Before start
        self.assertFalse(writer.write_envelope(self._make_env(1)))
        stats_before = writer.get_stats()
        self.assertEqual(stats_before.accepted_records, 0)
        self.assertEqual(stats_before.queue_drops, 0)

        # Running
        writer.start()
        self.assertTrue(writer.write_envelope(self._make_env(2)))
        writer.stop()

        # After stop
        self.assertFalse(writer.write_envelope(self._make_env(3)))
        stats_after = writer.get_stats()
        self.assertEqual(stats_after.accepted_records, 1)

    def test_timed_out_worker_and_subsequent_restart(self):
        client1 = MockInfluxDBClient()
        unblock_event = threading.Event()
        entered_write = threading.Event()
        client1.write_api_mock.block_event = unblock_event
        client1.write_api_mock.entered_write_event = entered_write

        client2 = MockInfluxDBClient()
        clients = [client1, client2]

        config = InfluxDBConfig(
            batch_size=1,
            client_factory=lambda cfg: clients.pop(0),
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(1))
        self.assertTrue(entered_write.wait(timeout=1.0))

        # Stop times out because write is blocked
        stopped = writer.stop(timeout=0.05)
        self.assertFalse(stopped)
        self.assertFalse(writer.is_running)
        self.assertTrue(writer.is_worker_alive)
        self.assertTrue(writer.is_shutdown_timed_out)

        # 1. Attempting to restart while previous worker is still alive MUST raise RuntimeError
        with self.assertRaises(RuntimeError) as ctx:
            writer.start()
        self.assertIn("previous worker thread", str(ctx.exception))
        self.assertFalse(writer.is_running)

        # 2. Unblock old worker thread and verify it exits cleanly
        unblock_event.set()
        time.sleep(0.05)
        self.assertFalse(writer.is_worker_alive)
        self.assertFalse(writer.is_shutdown_timed_out)

        # 3. Restart writer with client2 now succeeds
        writer.start()
        self.assertTrue(writer.is_running)

        # 4. Submit new envelope to restarted writer
        writer.write_envelope(self._make_env(2))
        time.sleep(0.05)
        clean_stop = writer.stop(timeout=1.0)
        self.assertTrue(clean_stop)
        self.assertFalse(writer.is_running)

        # Verify client2 successfully processed seq 2
        self.assertEqual(len(client2.write_api_mock.batches), 1)
        pt = client2.write_api_mock.batches[0]["record"][0]
        if hasattr(pt, "_fields"):
            seq_val = pt._fields["seq"]
        elif isinstance(pt, dict):
            seq_val = pt["fields"]["seq"]
        else:
            seq_val = getattr(pt, "fields", {}).get("seq")
        self.assertEqual(seq_val, 2)

    def test_repeated_stop_on_timed_out_worker(self):
        client = MockInfluxDBClient()
        unblock_event = threading.Event()
        entered_write = threading.Event()
        client.write_api_mock.block_event = unblock_event
        client.write_api_mock.entered_write_event = entered_write

        config = InfluxDBConfig(batch_size=1, client_factory=lambda cfg: client)
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(1))
        self.assertTrue(entered_write.wait(timeout=1.0))

        # First stop times out
        self.assertFalse(writer.stop(timeout=0.05))
        self.assertTrue(writer.is_shutdown_timed_out)

        # Repeated stop while still blocked also returns False safely without error
        self.assertFalse(writer.stop(timeout=0.05))
        self.assertTrue(writer.is_shutdown_timed_out)

        # Unblock worker
        unblock_event.set()
        time.sleep(0.05)

        # Repeated stop once worker has terminated returns True
        self.assertTrue(writer.stop(timeout=0.5))
        self.assertFalse(writer.is_shutdown_timed_out)
        self.assertFalse(writer.is_worker_alive)

    def test_timed_out_worker_stats_reporting(self):
        client = MockInfluxDBClient()
        unblock_event = threading.Event()
        entered_write = threading.Event()
        client.write_api_mock.block_event = unblock_event
        client.write_api_mock.entered_write_event = entered_write

        config = InfluxDBConfig(batch_size=1, client_factory=lambda cfg: client)
        writer = InfluxDBWriter(config=config)
        writer.start()

        writer.write_envelope(self._make_env(1))
        self.assertTrue(entered_write.wait(timeout=1.0))

        writer.stop(timeout=0.05)
        stats = writer.get_stats()
        self.assertFalse(stats.is_running)
        self.assertTrue(stats.is_worker_alive)
        self.assertTrue(stats.is_shutdown_timed_out)

        unblock_event.set()
        time.sleep(0.05)

        stats_after = writer.get_stats()
        self.assertFalse(stats_after.is_worker_alive)
        self.assertFalse(stats_after.is_shutdown_timed_out)

    def test_start_failure_leaves_clean_state(self):
        call_count = 0

        def failing_factory(cfg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Simulated DNS resolution failure to InfluxDB")
            return MockInfluxDBClient()

        config = InfluxDBConfig(client_factory=failing_factory)
        writer = InfluxDBWriter(config=config)

        with self.assertRaises(ConnectionError):
            writer.start()

        self.assertFalse(writer.is_running)
        self.assertFalse(writer.is_connected)

        # Subsequent start with healthy factory succeeds
        writer.start()
        self.assertTrue(writer.is_running)
        writer.stop()

    def test_malformed_envelope_isolated_in_batch(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            batch_size=3,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        env1 = self._make_env(10)

        class BrokenEnvelope:
            pass

        bad_env = BrokenEnvelope()
        env3 = self._make_env(12)

        writer.write_envelope(env1)
        writer.write_envelope(bad_env)
        writer.write_envelope(env3)

        time.sleep(0.08)
        writer.stop()

        stats = writer.get_stats()
        self.assertEqual(stats.malformed_records, 1)
        self.assertEqual(stats.successful_writes, 2)
        self.assertEqual(len(mock_client.write_api_mock.batches[0]["record"]), 2)

    def test_batch_size_never_exceeds_configured_limit(self):
        mock_client = MockInfluxDBClient()
        config = InfluxDBConfig(
            batch_size=4,
            flush_interval_sec=0.05,
            client_factory=lambda cfg: mock_client,
        )
        writer = InfluxDBWriter(config=config)
        writer.start()

        # Burst 14 items
        for i in range(14):
            writer.write_envelope(self._make_env(i))

        time.sleep(0.15)
        writer.stop()

        self.assertGreaterEqual(len(mock_client.write_api_mock.batches), 3)
        for b in mock_client.write_api_mock.batches:
            self.assertLessEqual(len(b["record"]), 4)
        self.assertEqual(writer.get_stats().successful_writes, 14)

    def test_config_from_env_defaults(self):
        cfg = InfluxDBConfig.from_env({})
        self.assertEqual(cfg.url, "http://localhost:8086")
        self.assertEqual(cfg.org, "nexus")
        self.assertEqual(cfg.bucket, "nexus_telemetry")
        self.assertIsNone(cfg.token)
        self.assertEqual(cfg.timeout_ms, 3000)
        self.assertEqual(cfg.batch_size, 50)
        self.assertEqual(cfg.flush_interval_sec, 1.0)
        self.assertEqual(cfg.max_queue_size, 1000)
        self.assertEqual(cfg.max_retries, 3)

    def test_config_from_env_custom(self):
        custom_env = {
            "INFLUXDB_URL": "http://127.0.0.1:8086",
            "INFLUXDB_ORG": "custom_org",
            "INFLUXDB_BUCKET": "custom_bucket",
            "INFLUXDB_TOKEN": "custom_secret_token",
            "INFLUXDB_TIMEOUT_MS": "5000",
            "INFLUXDB_BATCH_SIZE": "100",
            "INFLUXDB_FLUSH_INTERVAL_SEC": "2.5",
            "INFLUXDB_MAX_QUEUE_SIZE": "2000",
            "INFLUXDB_MAX_RETRIES": "5",
            "INFLUXDB_USE_SINGLE_MEASUREMENT": "true",
        }
        cfg = InfluxDBConfig.from_env(custom_env)
        self.assertEqual(cfg.url, "http://127.0.0.1:8086")
        self.assertEqual(cfg.org, "custom_org")
        self.assertEqual(cfg.bucket, "custom_bucket")
        self.assertEqual(cfg.token, "custom_secret_token")
        self.assertEqual(cfg.timeout_ms, 5000)
        self.assertEqual(cfg.batch_size, 100)
        self.assertEqual(cfg.flush_interval_sec, 2.5)
        self.assertEqual(cfg.max_queue_size, 2000)
        self.assertEqual(cfg.max_retries, 5)
        self.assertTrue(cfg.use_single_measurement)

    def test_config_from_env_token_fallback(self):
        # INFLUXDB_INIT_ADMIN_TOKEN is used as fallback if INFLUXDB_TOKEN is unset
        cfg = InfluxDBConfig.from_env({"INFLUXDB_INIT_ADMIN_TOKEN": "init_token_fallback"})
        self.assertEqual(cfg.token, "init_token_fallback")

        # INFLUXDB_TOKEN takes precedence if both are present
        cfg_both = InfluxDBConfig.from_env({
            "INFLUXDB_TOKEN": "primary_token",
            "INFLUXDB_INIT_ADMIN_TOKEN": "fallback_token",
        })
        self.assertEqual(cfg_both.token, "primary_token")

    def test_docker_provisioning_config_consistency(self):
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent

        compose_file = repo_root / "docker-compose.yml"
        env_example = repo_root / ".env.example"
        gitignore = repo_root / ".gitignore"

        self.assertTrue(compose_file.is_file(), "docker-compose.yml must exist at repo root")
        self.assertTrue(env_example.is_file(), ".env.example must exist at repo root")
        self.assertTrue(gitignore.is_file(), ".gitignore must exist at repo root")

        compose_text = compose_file.read_text(encoding="utf-8")
        env_text = env_example.read_text(encoding="utf-8")
        gitignore_text = gitignore.read_text(encoding="utf-8")

        # 1. Image version must be pinned, avoiding 'latest'
        self.assertIn("influxdb:${INFLUXDB_VERSION:-2.7.11}", compose_text)
        self.assertNotIn("influxdb:latest", compose_text)
        self.assertIn("INFLUXDB_VERSION=2.7.11", env_text)

        # 2. Local loopback binding only (ports section must not bind to 0.0.0.0)
        self.assertIn("127.0.0.1:", compose_text)
        non_comment_lines = [line for line in compose_text.splitlines() if not line.strip().startswith("#")]
        self.assertNotIn("0.0.0.0", "\n".join(non_comment_lines))

        # 3. Persistent named volume
        self.assertIn("influxdb_data:/var/lib/influxdb2", compose_text)
        self.assertIn("nexus_influxdb_data", compose_text)

        # 4. InfluxDBConfig defaults match environment variables
        default_cfg = InfluxDBConfig()
        self.assertIn(f"INFLUXDB_INIT_ORG={default_cfg.org}", env_text)
        self.assertIn(f"INFLUXDB_INIT_BUCKET={default_cfg.bucket}", env_text)
        self.assertIn(f"DOCKER_INFLUXDB_INIT_ORG=${{INFLUXDB_INIT_ORG:-{default_cfg.org}}}", compose_text)
        self.assertIn(f"DOCKER_INFLUXDB_INIT_BUCKET=${{INFLUXDB_INIT_BUCKET:-{default_cfg.bucket}}}", compose_text)

        # 5. Git secret exclusion verification
        self.assertIn(".env", gitignore_text)
        self.assertIn("!.env.example", gitignore_text)


if __name__ == "__main__":
    unittest.main()
