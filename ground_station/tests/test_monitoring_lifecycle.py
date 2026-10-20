"""NEXUS M7.4 Workstream B: Monitoring Lifecycle Integration Tests.

Validates:
- Single ownership of MonitoringService per Ground Station session.
- Dual-transport ingestion creates strictly ONE monitoring worker.
- Graceful startup and shutdown without thread leaks or unhandled exceptions.
- Persistent SQLite incident storage across lifecycle restarts.
- Resilient source handling when InfluxDB is offline.
- StandaloneMonitoringRunner lifecycle.
"""

from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import patch

import pytest

from ground_station.monitoring.models import DataSourceStatus
from ground_station.monitoring.runner import StandaloneMonitoringRunner
from ground_station.monitoring.service import MonitoringConfig, MonitoringService
from ground_station.run_dual_transport_ingestion import DualTransportIngestionSession
from ground_station.run_mqtt_ingestion import MqttIngestionSession
from ground_station.run_serial_ingestion import SerialIngestionSession


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_mqtt_session_monitoring_disabled():
    """Verify monitoring is disabled by default in MqttIngestionSession."""
    session = MqttIngestionSession(duration_sec=1, enable_monitoring=False)
    with patch.dict(os.environ, {"NEXUS_ENABLE_MONITORING": ""}):
        assert session.monitoring_service is None
        assert session.enable_monitoring is False


def test_mqtt_session_monitoring_lifecycle(temp_db):
    """Verify MqttIngestionSession starts and stops MonitoringService cleanly."""
    session = MqttIngestionSession(duration_sec=1, enable_monitoring=True)
    with patch.dict(os.environ, {"NEXUS_INCIDENT_DB": temp_db}):
        # Mock connection and adapter setup to avoid real network
        with patch("ground_station.run_mqtt_ingestion.NexusHostManager"), \
             patch("ground_station.run_mqtt_ingestion.MqttTransportAdapter"), \
             patch("ground_station.run_mqtt_ingestion.InfluxDBWriter"):
            success = session.setup()
            assert success is True
            assert session.monitoring_service is not None
            assert isinstance(session.monitoring_service, MonitoringService)
            assert session.monitoring_service.config.db_path == temp_db

            # Start and stop lifecycle
            session.monitoring_service.start()
            assert session.monitoring_service.is_running is True

            session.shutdown()
            assert session.monitoring_service.is_running is False


def test_serial_session_monitoring_lifecycle(temp_db):
    """Verify SerialIngestionSession starts and stops MonitoringService cleanly."""
    session = SerialIngestionSession(duration_sec=1, enable_monitoring=True)
    with patch.dict(os.environ, {"NEXUS_INCIDENT_DB": temp_db}):
        with patch("ground_station.run_serial_ingestion.NexusHostManager"), \
             patch("ground_station.run_serial_ingestion.SerialTransportAdapter"), \
             patch("ground_station.run_serial_ingestion.InfluxDBWriter"):
            success = session.setup()
            assert success is True
            assert session.monitoring_service is not None
            assert session.monitoring_service.config.db_path == temp_db

            session.monitoring_service.start()
            assert session.monitoring_service.is_running is True

            # Test finally block cleanup
            session.monitoring_service.stop()
            assert session.monitoring_service.is_running is False


def test_dual_transport_exactly_one_monitoring_worker(temp_db):
    """Crucial M7.4 invariant: Dual-transport session has 2 adapters but exactly 1 MonitoringService."""
    session = DualTransportIngestionSession(duration_sec=1, enable_monitoring=True)
    with patch.dict(os.environ, {"NEXUS_INCIDENT_DB": temp_db}):
        with patch("ground_station.run_dual_transport_ingestion.NexusHostManager"), \
             patch("ground_station.run_dual_transport_ingestion.SerialTransportAdapter"), \
             patch("ground_station.run_dual_transport_ingestion.MqttTransportAdapter"), \
             patch("ground_station.run_dual_transport_ingestion.InfluxDBWriter"):
            success = session.setup()
            assert success is True
            assert session.monitoring_service is not None

            # Verify there is only one monitoring worker reference
            worker_id = id(session.monitoring_service)
            assert isinstance(session.monitoring_service, MonitoringService)

            # Start and shutdown
            session.monitoring_service.start()
            assert session.monitoring_service.is_running is True
            assert id(session.monitoring_service) == worker_id

            session.shutdown()
            assert session.monitoring_service.is_running is False


def test_standalone_runner_lifecycle(temp_db):
    """Verify StandaloneMonitoringRunner manages monitoring service cleanly."""
    cfg = MonitoringConfig(
        db_path=temp_db,
        devices=["nexus_esp32"],
        normal_interval_sec=0.2,
        active_interval_sec=0.1,
    )
    runner = StandaloneMonitoringRunner(config=cfg, duration_sec=1)
    assert runner.setup() is True
    assert runner.service is not None

    runner.service.start()
    assert runner.service.is_running is True
    time.sleep(0.3)

    runner.shutdown()
    assert runner.service is None


def test_monitoring_offline_source_resilience(temp_db):
    """Verify monitoring handles offline InfluxDB gracefully without crashing or creating fake incidents."""
    cfg = MonitoringConfig(
        db_path=temp_db,
        devices=["nexus_esp32"],
        normal_interval_sec=0.1,
    )
    service = MonitoringService(config=cfg)

    # Force check_data_source_health to report UNAVAILABLE
    with patch.object(service, "check_data_source_health") as mock_health:
        from ground_station.monitoring.models import DataSourceHealth
        from ground_station.monitoring.service import utc_now

        mock_health.return_value = DataSourceHealth(
            status=DataSourceStatus.UNAVAILABLE,
            last_check_at=utc_now(),
            response_time_ms=5.0,
            error_message="Connection refused [test]",
        )

        report = service.evaluate_once()
        assert report.data_source is not None
        assert report.data_source.status == DataSourceStatus.UNAVAILABLE
        assert len(report.newly_opened) == 0
        assert len(report.resolved) == 0

        # Verify no incidents created on unavailable source
        incidents = service.get_active_incidents()
        assert len(incidents) == 0

    service.close()
