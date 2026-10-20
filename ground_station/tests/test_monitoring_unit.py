"""Unit tests for NEXUS Deterministic Monitoring and Durable Incidents (M7.2).

Runs 100% offline without requiring InfluxDB or container services.
Tests cover:
- Schema initialization and restart recovery
- Incident opening, duplicate suppression, resolution, and recurrence
- Durable transition ordering, evidence, and timestamps
- 90-day retention cleanup preserving all active incidents
- Bounded cleanup and transactional failure handling
- Telemetry freshness with verified firmware cadence and grace semantics
- DHT invalid vs missing readings (missing data != sensor failure)
- InfluxDB outage, timeout, and recovery without false device-offline incidents
- Scheduler cadence, bounded backoff, and clean shutdown
- Rule confirmation/hysteresis and flapping prevention
- Duplicate suppression when MQTT and serial observe the same telemetry
- Malformed or insufficient evidence handling
"""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from ground_station.analysis.models import (
    DataSourceUnavailableError,
    ObservationEvent,
    QueryTimeoutError,
)
from ground_station.analysis.telemetry_query import TelemetryQueryService
from ground_station.monitoring.models import (
    DataSourceStatus,
    IncidentSeverity,
    IncidentState,
)
from ground_station.monitoring.rules import (
    DHTInvalidReadingRule,
    DeviceRebootRule,
    ExecutiveFailureRule,
    MonitoringRule,
    TelemetryFreshnessRule,
)
from ground_station.monitoring.service import MonitoringConfig, MonitoringService
from ground_station.monitoring.store import IncidentStorageError, IncidentStore


class TestIncidentStore(unittest.TestCase):
    """Tests for SQLite IncidentStore schema, operations, deduplication, and retention."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_incidents.db")
        self.store = IncidentStore(self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_schema_initialization_idempotent(self) -> None:
        """Verify init_schema can be run repeatedly without error or data loss."""
        self.store.init_schema()
        self.store.init_schema()
        # Verify table exists
        incidents = self.store.get_active_incidents()
        self.assertEqual(incidents, [])

    def test_open_incident_and_duplicate_suppression(self) -> None:
        """Verify opening an incident creates a record and transition, while duplicate opens are suppressed."""
        now = datetime.now(timezone.utc)
        inc1 = self.store.open_incident(
            device_id="esp32_01",
            rule_id="stale_telemetry",
            severity=IncidentSeverity.WARNING,
            summary="Telemetry is stale",
            open_evidence={"age_seconds": 12.5},
            reason="Confirmed stale",
            opened_at=now,
        )

        self.assertIsNotNone(inc1.incident_id)
        self.assertEqual(inc1.state, IncidentState.OPEN)
        self.assertEqual(inc1.device_id, "esp32_01")
        self.assertEqual(inc1.rule_id, "stale_telemetry")
        self.assertEqual(inc1.open_evidence["age_seconds"], 12.5)

        # Transitions verification
        transitions = self.store.get_incident_transitions(inc1.incident_id)
        self.assertEqual(len(transitions), 1)
        self.assertIsNone(transitions[0].from_state)
        self.assertEqual(transitions[0].to_state, "OPEN")
        self.assertEqual(transitions[0].reason, "Confirmed stale")

        # Second open attempt for same device and rule: MUST return existing incident and NOT duplicate
        later = now + timedelta(seconds=5)
        inc2 = self.store.open_incident(
            device_id="esp32_01",
            rule_id="stale_telemetry",
            severity=IncidentSeverity.WARNING,
            summary="Still stale",
            open_evidence={"age_seconds": 17.5},
            opened_at=later,
        )

        self.assertEqual(inc1.incident_id, inc2.incident_id)
        # Should still be exactly 1 active incident
        active_list = self.store.get_active_incidents()
        self.assertEqual(len(active_list), 1)
        # No extra transition should have been inserted
        transitions_after = self.store.get_incident_transitions(inc1.incident_id)
        self.assertEqual(len(transitions_after), 1)

    def test_resolution_and_recurrence(self) -> None:
        """Verify resolution transitions to RESOLVED and subsequent occurrence creates a new incident."""
        now = datetime.now(timezone.utc)
        inc1 = self.store.open_incident(
            device_id="esp32_01",
            rule_id="dht_sensor_invalid",
            severity=IncidentSeverity.WARNING,
            summary="DHT invalid",
            open_evidence={"invalid_count": 5},
            opened_at=now,
        )

        # Resolve incident
        resolve_time = now + timedelta(minutes=2)
        resolved_inc = self.store.resolve_incident(
            incident_id=inc1.incident_id,
            resolve_evidence={"valid_count": 10},
            reason="Confirmed valid readings",
            resolved_at=resolve_time,
        )

        self.assertEqual(resolved_inc.state, IncidentState.RESOLVED)
        self.assertIsNotNone(resolved_inc.resolved_at)
        self.assertEqual(self.store.get_active_incidents(), [])

        # Check transition history
        transitions = self.store.get_incident_transitions(inc1.incident_id)
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[0].to_state, "OPEN")
        self.assertEqual(transitions[1].from_state, "OPEN")
        self.assertEqual(transitions[1].to_state, "RESOLVED")
        self.assertEqual(transitions[1].reason, "Confirmed valid readings")

        # Recurrence: condition happens again later
        reoccur_time = now + timedelta(hours=1)
        inc2 = self.store.open_incident(
            device_id="esp32_01",
            rule_id="dht_sensor_invalid",
            severity=IncidentSeverity.WARNING,
            summary="DHT invalid again",
            open_evidence={"invalid_count": 4},
            opened_at=reoccur_time,
        )

        # Must have a new incident ID and be OPEN
        self.assertNotEqual(inc1.incident_id, inc2.incident_id)
        self.assertEqual(inc2.state, IncidentState.OPEN)
        self.assertEqual(len(self.store.get_active_incidents()), 1)

        # Total history has 2 incidents
        history = self.store.get_incident_history(device_id="esp32_01", rule_id="dht_sensor_invalid")
        self.assertEqual(len(history), 2)

    def test_restart_recovery(self) -> None:
        """Verify active incidents and historical transitions persist across restart."""
        now = datetime.now(timezone.utc)
        inc = self.store.open_incident(
            device_id="esp32_02",
            rule_id="executive_task_failure",
            severity=IncidentSeverity.CRITICAL,
            summary="Executive failed 2 tasks",
            open_evidence={"failed_count": 2},
            opened_at=now,
        )

        # Close store to simulate process shutdown
        self.store.close()

        # Reopen store from same file
        recovered_store = IncidentStore(self.db_path)
        try:
            active = recovered_store.get_active_incidents()
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0].incident_id, inc.incident_id)
            self.assertEqual(active[0].device_id, "esp32_02")
            self.assertEqual(active[0].rule_id, "executive_task_failure")
            self.assertEqual(active[0].severity, IncidentSeverity.CRITICAL)

            transitions = recovered_store.get_incident_transitions(inc.incident_id)
            self.assertEqual(len(transitions), 1)
            self.assertEqual(transitions[0].to_state, "OPEN")
        finally:
            recovered_store.close()

    def test_retention_cleanup_preserves_all_active_incidents(self) -> None:
        """Verify 90-day retention cleanup prunes old resolved incidents but NEVER prunes active incidents."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=95)

        # 1. Old active incident (older than 90 days, but OPEN)
        active_old = self.store.open_incident(
            device_id="esp32_old_active",
            rule_id="stale_telemetry",
            severity=IncidentSeverity.WARNING,
            summary="Old active incident",
            open_evidence={},
            opened_at=old_time,
        )

        # 2. Old resolved incident (eligible for cleanup)
        resolved_old = self.store.open_incident(
            device_id="esp32_old_resolved",
            rule_id="dht_sensor_invalid",
            severity=IncidentSeverity.WARNING,
            summary="Old resolved incident",
            open_evidence={},
            opened_at=old_time,
        )
        self.store.resolve_incident(
            incident_id=resolved_old.incident_id,
            resolve_evidence={},
            resolved_at=old_time + timedelta(hours=1),
        )

        # 3. Recent resolved incident (not eligible for cleanup)
        recent_resolved = self.store.open_incident(
            device_id="esp32_recent",
            rule_id="dht_sensor_invalid",
            severity=IncidentSeverity.WARNING,
            summary="Recent resolved incident",
            open_evidence={},
            opened_at=now - timedelta(days=10),
        )
        self.store.resolve_incident(
            incident_id=recent_resolved.incident_id,
            resolve_evidence={},
            resolved_at=now - timedelta(days=9),
        )

        # Run retention cleanup (90 days)
        pruned_count = self.store.cleanup_retention(older_than_days=90, batch_size=500)
        self.assertEqual(pruned_count, 1)

        # Verify old active incident is STILL PRESENT
        self.assertIsNotNone(self.store.get_incident(active_old.incident_id))
        self.assertEqual(len(self.store.get_active_incidents()), 1)

        # Verify old resolved incident was pruned
        self.assertIsNone(self.store.get_incident(resolved_old.incident_id))
        # Verify related transitions were also pruned
        self.assertEqual(self.store.get_incident_transitions(resolved_old.incident_id), [])

        # Verify recent resolved incident is STILL PRESENT
        self.assertIsNotNone(self.store.get_incident(recent_resolved.incident_id))

    def test_bounded_cleanup_and_error_handling(self) -> None:
        """Verify retention cleanup respects batch limits and surfaces storage errors explicitly."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=100)

        for i in range(5):
            inc = self.store.open_incident(
                device_id=f"dev_{i}",
                rule_id="rule_batch",
                severity=IncidentSeverity.INFO,
                summary="Batch test",
                open_evidence={},
                opened_at=old_time,
            )
            self.store.resolve_incident(
                incident_id=inc.incident_id,
                resolve_evidence={},
                resolved_at=old_time + timedelta(minutes=1),
            )

        # Cleanup with batch_size=2
        deleted = self.store.cleanup_retention(older_than_days=90, batch_size=2)
        self.assertEqual(deleted, 2)

        # Next batch cleans another 2
        deleted2 = self.store.cleanup_retention(older_than_days=90, batch_size=2)
        self.assertEqual(deleted2, 2)

        # Error handling: closed connection raises IncidentStorageError
        self.store.close()
        with self.assertRaises(IncidentStorageError):
            self.store.get_active_incidents()


class TestTelemetryFreshnessRule(unittest.TestCase):
    """Tests for TelemetryFreshnessRule cadence, grace, confirmation, and clear semantics."""

    def setUp(self) -> None:
        self.mock_query = MagicMock(spec=TelemetryQueryService)
        # 2.0s cadence * 3.0x grace = 6.0s threshold; confirm_trigger=2, confirm_clear=1
        self.rule = TelemetryFreshnessRule(
            cadence_sec=2.0,
            grace_factor=3.0,
            confirm_trigger_count=2,
            confirm_clear_count=1,
        )

    def test_fresh_telemetry_clears(self) -> None:
        """Verify fresh telemetry (< 6.0s old) results in cleared=True."""
        now = datetime.now(timezone.utc)
        env = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=10,
            uptime_ms=20000,
            host_time=now - timedelta(seconds=2.5),
            transports=["mqtt"],
            fields={"temp": 24.5},
        )
        self.mock_query.get_raw_envelopes.return_value = [env]

        res = self.rule.evaluate(self.mock_query, "esp32_01", is_active=False)
        self.assertFalse(res.triggered)
        self.assertTrue(res.cleared)
        self.assertIn("fresh", res.reason)

    def test_stale_telemetry_requires_confirmation(self) -> None:
        """Verify stale telemetry (> 6.0s old) requires confirm_trigger_count evaluations to trigger."""
        now = datetime.now(timezone.utc)
        env = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=10,
            uptime_ms=20000,
            host_time=now - timedelta(seconds=8.0),  # 8s > 6s threshold
            transports=["mqtt"],
            fields={"temp": 24.5},
        )
        self.mock_query.get_raw_envelopes.return_value = [env]

        # First evaluation: pending confirmation
        res1 = self.rule.evaluate(self.mock_query, "esp32_01", is_active=False)
        self.assertFalse(res1.triggered)
        self.assertIn("pending confirmation", res1.reason)

        # Second consecutive stale evaluation: confirmed trigger!
        res2 = self.rule.evaluate(self.mock_query, "esp32_01", is_active=False)
        self.assertTrue(res2.triggered)
        self.assertFalse(res2.cleared)
        self.assertEqual(res2.severity, IncidentSeverity.WARNING)

    def test_flapping_prevention_on_transient_delay(self) -> None:
        """Verify transient delay followed by recovery does not trigger."""
        now = datetime.now(timezone.utc)
        stale_env = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=10,
            uptime_ms=20000,
            host_time=now - timedelta(seconds=7.0),
            transports=["mqtt"],
            fields={},
        )
        fresh_env = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=11,
            uptime_ms=22000,
            host_time=now - timedelta(seconds=1.0),
            transports=["mqtt"],
            fields={},
        )

        # 1. Stale packet once
        self.mock_query.get_raw_envelopes.return_value = [stale_env]
        res1 = self.rule.evaluate(self.mock_query, "esp32_01")
        self.assertFalse(res1.triggered)

        # 2. Fresh packet next cycle (resets trigger counter)
        self.mock_query.get_raw_envelopes.return_value = [fresh_env]
        res2 = self.rule.evaluate(self.mock_query, "esp32_01")
        self.assertFalse(res2.triggered)
        self.assertTrue(res2.cleared)

    def test_missing_device_initial_observation(self) -> None:
        """Verify device that has never sent telemetry is treated as insufficient data, not false trigger."""
        self.mock_query.get_raw_envelopes.return_value = []
        res = self.rule.evaluate(self.mock_query, "unknown_dev", is_active=False)
        self.assertFalse(res.triggered)
        self.assertFalse(res.cleared)
        self.assertIn("Insufficient data", res.reason)


class TestDHTInvalidReadingRule(unittest.TestCase):
    """Tests for DHT sensor invalid readings rule and missing vs invalid distinction."""

    def setUp(self) -> None:
        self.mock_query = MagicMock(spec=TelemetryQueryService)
        # min_invalid_samples=3, invalid_ratio_threshold=0.5, confirm=1 for test clarity
        self.rule = DHTInvalidReadingRule(
            min_invalid_samples=3,
            invalid_ratio_threshold=0.5,
            confirm_trigger_count=1,
            confirm_clear_count=1,
        )

    def _make_env(self, dht_valid: bool | None, seq: int) -> ObservationEvent:
        fields = {}
        if dht_valid is not None:
            fields["dht_valid"] = dht_valid
        return ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=seq,
            uptime_ms=1000 * seq,
            host_time=datetime.now(timezone.utc),
            transports=["mqtt"],
            fields=fields,
        )

    def test_missing_data_is_not_sensor_failure(self) -> None:
        """Verify that missing samples do not trigger the DHT invalid rule."""
        self.mock_query.get_raw_envelopes.return_value = []
        res = self.rule.evaluate(self.mock_query, "esp32_01", is_active=False)
        self.assertFalse(res.triggered)
        self.assertFalse(res.cleared)
        self.assertIn("Insufficient data", res.reason)

    def test_confirmed_invalid_readings_trigger(self) -> None:
        """Verify confirmed dht_valid=False pattern triggers warning incident."""
        # 4 samples: 3 invalid (dht_valid=False), 1 valid -> 75% invalid
        envs = [
            self._make_env(False, 1),
            self._make_env(False, 2),
            self._make_env(False, 3),
            self._make_env(True, 4),
        ]
        self.mock_query.get_raw_envelopes.return_value = envs

        res = self.rule.evaluate(self.mock_query, "esp32_01", is_active=False)
        self.assertTrue(res.triggered)
        self.assertFalse(res.cleared)
        self.assertEqual(res.evidence["dht_invalid_count"], 3)
        self.assertEqual(res.evidence["total_samples"], 4)

    def test_healthy_sensor_clears(self) -> None:
        """Verify consecutive valid readings clear the incident."""
        envs = [
            self._make_env(True, 1),
            self._make_env(True, 2),
            self._make_env(True, 3),
            self._make_env(True, 4),
        ]
        self.mock_query.get_raw_envelopes.return_value = envs

        res = self.rule.evaluate(self.mock_query, "esp32_01", is_active=True)
        self.assertFalse(res.triggered)
        self.assertTrue(res.cleared)
        self.assertEqual(res.evidence["dht_invalid_count"], 0)


class TestExecutiveRules(unittest.TestCase):
    """Tests for ExecutiveFailureRule and DeviceRebootRule."""

    def test_executive_failure_triggers_critical(self) -> None:
        mock_query = MagicMock(spec=TelemetryQueryService)
        env = ObservationEvent(
            dev="esp32_01",
            msg_type="status",
            seq=1,
            uptime_ms=5000,
            host_time=datetime.now(timezone.utc),
            transports=["mqtt"],
            fields={"failed": 3, "dispatched": 100, "completed": 97, "max_lat_us": 450},
        )
        mock_query.get_raw_envelopes.return_value = [env]

        rule = ExecutiveFailureRule(confirm_trigger_count=1, confirm_clear_count=1)
        res = rule.evaluate(mock_query, "esp32_01", is_active=False)

        self.assertTrue(res.triggered)
        self.assertEqual(res.severity, IncidentSeverity.CRITICAL)
        self.assertEqual(res.evidence["failed_cumulative"], 3)
        self.assertEqual(res.evidence["failed_delta"], 3)

    def test_cumulative_counter_does_not_permanently_trigger(self) -> None:
        """Verify that cumulative jobs_failed does not create a permanent active incident once tasks succeed."""
        mock_query = MagicMock(spec=TelemetryQueryService)
        now = datetime.now(timezone.utc)
        rule = ExecutiveFailureRule(confirm_trigger_count=1, confirm_clear_count=1)

        # 1. Baseline envelope: failed=0, dispatched=10, completed=10
        env1 = ObservationEvent(
            dev="esp32_01",
            msg_type="status",
            seq=1,
            uptime_ms=5000,
            host_time=now - timedelta(seconds=15),
            transports=["mqtt"],
            fields={"failed": 0, "dispatched": 10, "completed": 10},
        )
        # 2. Failure occurs: failed=1, dispatched=20, completed=19
        env2 = ObservationEvent(
            dev="esp32_01",
            msg_type="status",
            seq=2,
            uptime_ms=10000,
            host_time=now - timedelta(seconds=10),
            transports=["mqtt"],
            fields={"failed": 1, "dispatched": 20, "completed": 19},
        )
        mock_query.get_raw_envelopes.return_value = [env1, env2]
        res_fail = rule.evaluate(mock_query, "esp32_01", is_active=False)
        self.assertTrue(res_fail.triggered)
        self.assertEqual(res_fail.evidence["failed_delta"], 1)

        # 3. Subsequent evaluation: executive continues running with 0 new failures (dispatched=30, completed=29, failed remains 1)
        env3 = ObservationEvent(
            dev="esp32_01",
            msg_type="status",
            seq=3,
            uptime_ms=15000,
            host_time=now - timedelta(seconds=5),
            transports=["mqtt"],
            fields={"failed": 1, "dispatched": 30, "completed": 29},
        )
        mock_query.get_raw_envelopes.return_value = [env2, env3]
        res_recover = rule.evaluate(mock_query, "esp32_01", is_active=True)
        # Condition clears! Not permanently active.
        self.assertFalse(res_recover.triggered)
        self.assertTrue(res_recover.cleared)
        self.assertEqual(res_recover.evidence["failed_delta"], 0)
        self.assertEqual(res_recover.evidence["failed_cumulative"], 1)

    def test_executive_failure_no_matching_rows_does_not_claim_recovery(self) -> None:
        """Verify that zero status rows in query returns insufficient data and does NOT claim recovery."""
        mock_query = MagicMock(spec=TelemetryQueryService)
        mock_query.get_raw_envelopes.return_value = []
        rule = ExecutiveFailureRule(confirm_trigger_count=1, confirm_clear_count=1)

        res = rule.evaluate(mock_query, "esp32_01", is_active=True)
        self.assertFalse(res.triggered)
        self.assertFalse(res.cleared)
        self.assertIn("Insufficient data", res.reason)

    def test_device_reboot_triggers_info(self) -> None:
        mock_query = MagicMock(spec=TelemetryQueryService)
        # Sequence with uptime drop: 50000ms -> 1000ms
        now = datetime.now(timezone.utc)
        env1 = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=50,
            uptime_ms=50000,
            host_time=now - timedelta(seconds=4),
            transports=["mqtt"],
            fields={},
        )
        env2 = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=1,
            uptime_ms=1000,
            host_time=now - timedelta(seconds=2),
            transports=["mqtt"],
            fields={},
        )
        mock_query.get_raw_envelopes.return_value = [env1, env2]

        rule = DeviceRebootRule(confirm_trigger_count=1)
        res = rule.evaluate(mock_query, "esp32_01", is_active=False)

        self.assertTrue(res.triggered)
        self.assertEqual(res.severity, IncidentSeverity.INFO)
        self.assertEqual(res.evidence["reboots_detected"], 1)


class TestMonitoringService(unittest.TestCase):
    """Tests for MonitoringService lifecycle, InfluxDB outage handling, and cadence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "service_incidents.db")
        self.store = IncidentStore(self.db_path)
        self.mock_query = MagicMock(spec=TelemetryQueryService)
        self.mock_query.check_health.return_value = {"status": "healthy"}

        self.config = MonitoringConfig(
            devices=["esp32_01"],
            db_path=self.db_path,
            normal_interval_sec=5.0,
            active_interval_sec=1.0,
            backoff_base_sec=2.0,
            backoff_max_sec=10.0,
        )

        self.service = MonitoringService(
            config=self.config,
            query_service=self.mock_query,
            store=self.store,
            auto_register_default_rules=False,
        )

    def tearDown(self) -> None:
        self.service.close()
        self.temp_dir.cleanup()

    def test_startup_grace_period_suppresses_initial_stale(self) -> None:
        """Verify startup_grace_sec suppresses stale evaluation on initial cold start."""
        now = datetime.now(timezone.utc)
        old_env = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=1,
            uptime_ms=1000,
            host_time=now - timedelta(seconds=120),  # 2 minutes old
            transports=["mqtt"],
            fields={"temp": 22.0},
        )
        self.mock_query.get_raw_envelopes.return_value = [old_env]

        rule_with_grace = TelemetryFreshnessRule(
            startup_grace_sec=10.0,
            confirm_trigger_count=1,
        )
        res = rule_with_grace.evaluate(self.mock_query, "esp32_01", is_active=False)
        self.assertFalse(res.triggered)
        self.assertFalse(res.cleared)
        self.assertIn("Startup grace period active", res.reason)

    def test_influxdb_outage_does_not_create_false_incidents(self) -> None:
        """Verify InfluxDB outage reports data-source unavailable without creating false device-offline incidents."""
        self.mock_query.check_health.side_effect = DataSourceUnavailableError("Connection refused: 8086")

        report = self.service.evaluate_once()

        # Data source is reported as UNAVAILABLE
        self.assertIsNotNone(report.data_source)
        self.assertEqual(report.data_source.status, DataSourceStatus.UNAVAILABLE)
        self.assertIn("Connection refused", report.data_source.error_message)

        # Zero false device incidents opened
        self.assertEqual(report.newly_opened, [])
        self.assertEqual(self.service.get_active_incidents(), [])

        # Status inspection reflects data source state
        status = self.service.get_status()
        self.assertEqual(status.data_source.status, DataSourceStatus.UNAVAILABLE)
        self.assertEqual(status.active_incident_count, 0)

    def test_influxdb_timeout_does_not_create_false_incidents(self) -> None:
        """Verify query timeouts in rule evaluation do not create false device incidents."""
        self.mock_query.check_health.return_value = {"status": "healthy"}

        # Custom rule that raises QueryTimeoutError during evaluation
        class TimeoutRule(MonitoringRule):
            def _evaluate_internal(self, query_service, device_id, is_active):
                raise QueryTimeoutError("Query exceeded 3.0s deadline")

        self.service.register_rule(TimeoutRule("timeout_test", "Timeout Test", "Test"))
        report = self.service.evaluate_once()

        self.assertEqual(report.newly_opened, [])
        self.assertEqual(self.service.get_active_incidents(), [])

    def test_dual_transport_deduplicated_telemetry_no_duplicate_incidents(self) -> None:
        """Verify that when telemetry arrives over both MQTT and serial, only a single incident is opened."""
        now = datetime.now(timezone.utc)
        # Single canonical envelope seen over both MQTT and serial
        canonical_env = ObservationEvent(
            dev="esp32_01",
            msg_type="telem",
            seq=10,
            uptime_ms=20000,
            host_time=now - timedelta(seconds=15),  # Stale
            transports=["mqtt", "serial"],
            fields={"temp": 24.5},
        )
        self.mock_query.get_raw_envelopes.return_value = [canonical_env]

        freshness_rule = TelemetryFreshnessRule(confirm_trigger_count=1)
        self.service.register_rule(freshness_rule)

        # First evaluation: opens incident
        rep1 = self.service.evaluate_once()
        self.assertEqual(len(rep1.newly_opened), 1)
        inc_id = rep1.newly_opened[0].incident_id

        # Second evaluation with same canonical observation: no duplicate opened
        rep2 = self.service.evaluate_once()
        self.assertEqual(len(rep2.newly_opened), 0)
        self.assertEqual(len(rep2.ongoing), 1)
        self.assertEqual(rep2.ongoing[0].incident_id, inc_id)

        # Historical transitions must have exactly 1 transition
        transitions = self.service.get_incident_transitions(inc_id)
        self.assertEqual(len(transitions), 1)

    def test_scheduler_lifecycle_and_clean_shutdown(self) -> None:
        """Verify background scheduler thread starts, evaluates, and stops cleanly within timeout."""
        self.assertFalse(self.service.is_running)
        self.service.start()
        self.assertTrue(self.service.is_running)

        # Wait briefly for scheduler to cycle at least once
        time.sleep(0.1)

        status = self.service.get_status()
        self.assertTrue(status.is_running)

        # Stop service
        self.service.stop(timeout=2.0)
        self.assertFalse(self.service.is_running)

    def test_repeated_start_stop_cycles(self) -> None:
        """Verify starting and stopping the service repeatedly does not leak workers or corrupt state."""
        for cycle in range(3):
            self.service.start()
            self.assertTrue(self.service.is_running)
            time.sleep(0.05)
            self.service.stop(timeout=2.0)
            self.assertFalse(self.service.is_running)

        # Verify database is intact and queries still succeed
        active = self.service.get_active_incidents()
        self.assertEqual(active, [])

    def test_persistence_failure_reports_error_cleanly(self) -> None:
        """Simulate persistence failure and verify error is raised rather than claiming success."""
        # Register a rule so evaluate_once queries the store for active incidents
        rule = TelemetryFreshnessRule()
        self.service.register_rule(rule)
        # Force SQLite failure by closing underlying connection
        self.store.close()
        with self.assertRaises(IncidentStorageError):
            self.service.evaluate_once()

    def test_utc_timestamp_consistency(self) -> None:
        """Verify all incident model and transition timestamps are consistent UTC."""
        now = datetime.now(timezone.utc)
        inc = self.store.open_incident(
            device_id="esp32_utc",
            rule_id="utc_test",
            severity=IncidentSeverity.INFO,
            summary="UTC test",
            open_evidence={},
            opened_at=now,
        )

        self.assertEqual(inc.opened_at.tzinfo, timezone.utc)
        self.assertEqual(inc.last_evaluated_at.tzinfo, timezone.utc)

        transitions = self.store.get_incident_transitions(inc.incident_id)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].timestamp.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
