"""NEXUS Deterministic Background Monitoring Service.

Provides a thread-safe, bounded background monitoring engine independent of LLMs and Grafana:
- Scheduled, adaptive cadence (normal 5s, active incidents 2s, bounded backoff on source failure up to 30s).
- InfluxDB telemetry source health tracked separately from device health.
- Durable incident persistence and transition history in SQLite.
- Clean Python API for status inspection, active incidents, and historical queries.
- Bounded and transactional 90-day retention pruning.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from ground_station.analysis.models import (
    DataSourceUnavailableError,
    QueryTimeoutError,
)
from ground_station.analysis.telemetry_query import TelemetryQueryService

from .models import (
    DataSourceHealth,
    DataSourceStatus,
    EvaluationReport,
    Incident,
    IncidentTransition,
    MonitorStatus,
    utc_now,
)
from .rules.base import MonitoringRule
from .rules.executive import DeviceRebootRule, ExecutiveFailureRule
from .rules.freshness import TelemetryFreshnessRule
from .rules.sensor import DHTInvalidReadingRule
from .store import IncidentStore

logger = logging.getLogger("nexus.monitoring.service")


@dataclass
class MonitoringConfig:
    """Configuration for NEXUS background monitoring service."""

    devices: List[str] = field(default_factory=lambda: ["esp32_01"])
    db_path: str = "nexus_incidents.db"
    normal_interval_sec: float = 5.0
    active_interval_sec: float = 2.0
    backoff_base_sec: float = 5.0
    backoff_max_sec: float = 30.0
    retention_days: int = 90
    retention_interval_sec: float = 86400.0  # Run retention cleanup daily

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> MonitoringConfig:
        """Construct MonitoringConfig from environment dictionary."""
        e = env or os.environ
        devs_str = e.get("NEXUS_MONITORING_DEVICES", "esp32_01,nexus_esp32")
        devs = [d.strip() for d in devs_str.split(",") if d.strip()]
        return cls(
            devices=devs or ["esp32_01"],
            db_path=e.get("NEXUS_INCIDENT_DB", "nexus_incidents.db"),
            normal_interval_sec=float(e.get("NEXUS_MONITOR_NORMAL_INTERVAL", "5.0")),
            active_interval_sec=float(e.get("NEXUS_MONITOR_ACTIVE_INTERVAL", "2.0")),
            backoff_base_sec=float(e.get("NEXUS_MONITOR_BACKOFF_BASE", "5.0")),
            backoff_max_sec=float(e.get("NEXUS_MONITOR_BACKOFF_MAX", "30.0")),
            retention_days=int(e.get("NEXUS_INCIDENT_RETENTION_DAYS", "90")),
        )


class MonitoringService:
    """Autonomous, deterministic monitoring service and incident manager."""

    def __init__(
        self,
        config: Optional[MonitoringConfig] = None,
        query_service: Optional[TelemetryQueryService] = None,
        store: Optional[IncidentStore] = None,
        auto_register_default_rules: bool = True,
    ) -> None:
        """Initialize MonitoringService.

        Args:
            config: Service configuration options.
            query_service: Telemetry query foundation instance (dependency injection).
            store: IncidentStore SQLite instance (dependency injection).
            auto_register_default_rules: Register standard deterministic rules on init.
        """
        self.config = config or MonitoringConfig()
        self._external_query = query_service is not None
        self.query_service = query_service or TelemetryQueryService()

        self._external_store = store is not None
        self.store = store or IncidentStore(self.config.db_path)

        self._rules: Dict[str, MonitoringRule] = {}
        self._devices: set[str] = set(self.config.devices)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._consecutive_source_failures = 0
        self._last_evaluated_at: Optional[datetime] = None
        self._evaluation_count = 0
        self._current_interval_sec = self.config.normal_interval_sec
        self._last_retention_cleanup = 0.0

        self._last_data_source_health = DataSourceHealth(
            status=DataSourceStatus.UNAVAILABLE,
            last_check_at=utc_now(),
            response_time_ms=0.0,
            error_message="Not yet evaluated",
        )

        if auto_register_default_rules:
            self.register_rule(TelemetryFreshnessRule(cadence_sec=2.0, grace_factor=3.0))
            self.register_rule(DHTInvalidReadingRule(window="-15m"))
            self.register_rule(ExecutiveFailureRule())
            self.register_rule(DeviceRebootRule(window="-15m"))

    # --- Rule and Device Management API ---

    def register_rule(self, rule: MonitoringRule) -> None:
        """Register a monitoring rule."""
        with self._lock:
            self._rules[rule.rule_id] = rule
            logger.debug("Registered monitoring rule: %s", rule.rule_id)

    def unregister_rule(self, rule_id: str) -> None:
        """Unregister a monitoring rule."""
        with self._lock:
            self._rules.pop(rule_id, None)

    def add_device(self, device_id: str) -> None:
        """Add a device to the monitoring roster."""
        with self._lock:
            self._devices.add(device_id)

    def remove_device(self, device_id: str) -> None:
        """Remove a device from the monitoring roster."""
        with self._lock:
            self._devices.discard(device_id)

    # --- Core Evaluation Pipeline ---

    def check_data_source_health(self) -> DataSourceHealth:
        """Perform dedicated data-source health audit.

        Reports InfluxDB connectivity/timeout status without triggering device incidents.
        """
        start = time.perf_counter()
        now = utc_now()
        try:
            health = self.query_service.check_health()
            elapsed_ms = (time.perf_counter() - start) * 1000
            is_healthy = health.get("status") in ("pass", "healthy")
            status = DataSourceStatus.HEALTHY if is_healthy else DataSourceStatus.DEGRADED
            err = health.get("error") or health.get("message") if not is_healthy else None

            ds_health = DataSourceHealth(
                status=status,
                last_check_at=now,
                response_time_ms=elapsed_ms,
                error_message=err,
            )
        except (DataSourceUnavailableError, QueryTimeoutError) as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            ds_health = DataSourceHealth(
                status=DataSourceStatus.UNAVAILABLE,
                last_check_at=now,
                response_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            ds_health = DataSourceHealth(
                status=DataSourceStatus.UNAVAILABLE,
                last_check_at=now,
                response_time_ms=elapsed_ms,
                error_message=f"Unexpected health check error: {e}",
            )

        with self._lock:
            self._last_data_source_health = ds_health
        return ds_health

    def evaluate_once(self) -> EvaluationReport:
        """Execute a single bounded, deterministic evaluation pass across all monitored devices and rules.

        Thread-safe and synchronous. Can be called on-demand or by the background scheduler.
        """
        eval_start = time.perf_counter()
        now = utc_now()

        with self._lock:
            active_devices = sorted(list(self._devices))
            active_rules = list(self._rules.values())

        report = EvaluationReport(
            timestamp=now,
            devices_evaluated=active_devices,
            newly_opened=[],
            resolved=[],
            ongoing=[],
        )

        # 1. Check data source health
        ds_health = self.check_data_source_health()
        report.data_source = ds_health

        if ds_health.status == DataSourceStatus.UNAVAILABLE:
            with self._lock:
                self._consecutive_source_failures += 1
            logger.warning(
                "Telemetry data source is UNAVAILABLE (%s). Skipping device incident evaluations.",
                ds_health.error_message,
            )
            report.duration_ms = (time.perf_counter() - eval_start) * 1000
            return report

        # Source is reachable
        with self._lock:
            if self._consecutive_source_failures > 0:
                logger.info(
                    "Telemetry data source recovered after %d failed attempts.",
                    self._consecutive_source_failures,
                )
            self._consecutive_source_failures = 0

        # 2. Evaluate rules across all devices
        for dev in active_devices:
            for rule in active_rules:
                active_inc = self.store.get_active_incident(dev, rule.rule_id)
                is_active = active_inc is not None

                res = rule.evaluate(
                    query_service=self.query_service,
                    device_id=dev,
                    is_active=is_active,
                )

                if res.triggered:
                    if active_inc is not None:
                        # Ongoing incident: refresh timestamp, prevent duplicate
                        self.store.touch_incident(active_inc.incident_id, evaluated_at=now)
                        report.ongoing.append(active_inc)
                    else:
                        # New confirmed incident: open and record transition
                        new_inc = self.store.open_incident(
                            device_id=dev,
                            rule_id=rule.rule_id,
                            severity=res.severity,
                            summary=res.summary,
                            open_evidence=res.evidence,
                            reason=res.reason,
                            opened_at=now,
                        )
                        report.newly_opened.append(new_inc)
                        logger.warning("Opened incident [%s] for %s (%s)", new_inc.incident_id, dev, rule.rule_id)
                elif res.cleared:
                    if active_inc is not None:
                        # Condition cleared: resolve incident and record transition
                        resolved_inc = self.store.resolve_incident(
                            incident_id=active_inc.incident_id,
                            resolve_evidence=res.evidence,
                            reason=res.reason,
                            resolved_at=now,
                        )
                        report.resolved.append(resolved_inc)
                        logger.info("Resolved incident [%s] for %s (%s)", resolved_inc.incident_id, dev, rule.rule_id)
                else:
                    # Neither triggered nor cleared (neutral/insufficient data)
                    if active_inc is not None:
                        self.store.touch_incident(active_inc.incident_id, evaluated_at=now)
                        report.ongoing.append(active_inc)

        # 3. Periodic retention cleanup (bounded 90 days)
        current_time = time.time()
        if (current_time - self._last_retention_cleanup) > self.config.retention_interval_sec:
            try:
                self.store.cleanup_retention(older_than_days=self.config.retention_days)
                self._last_retention_cleanup = current_time
            except Exception as e:
                logger.error("Periodic retention cleanup encountered an error: %s", e)

        # 4. Finalize metrics
        report.duration_ms = (time.perf_counter() - eval_start) * 1000
        with self._lock:
            self._last_evaluated_at = now
            self._evaluation_count += 1

        return report

    # --- Background Scheduler Lifecycle ---

    def start(self) -> None:
        """Start the background monitoring thread."""
        with self._lock:
            if self.is_running:
                logger.warning("Monitoring service is already running.")
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._scheduler_loop,
                name="nexus_monitor_scheduler",
                daemon=True,
            )
            self._thread.start()
            logger.info("Background monitoring service started.")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal background scheduler to stop and wait for thread termination."""
        with self._lock:
            if not self.is_running or self._thread is None:
                return

            self._stop_event.set()
            thread = self._thread
            self._thread = None

        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("Monitoring thread did not terminate within %0.1fs timeout.", timeout)
        else:
            logger.info("Background monitoring service stopped cleanly.")

    @property
    def is_running(self) -> bool:
        """Check if background scheduler thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _scheduler_loop(self) -> None:
        """Autonomous scheduler loop with adaptive cadence and bounded backoff."""
        logger.info("Monitoring scheduler loop active.")
        while not self._stop_event.is_set():
            try:
                report = self.evaluate_once()

                # Calculate next interval based on state and health
                if report.data_source and report.data_source.status == DataSourceStatus.UNAVAILABLE:
                    # Exponential backoff on data source failure capped at backoff_max_sec
                    exponent = max(0, self._consecutive_source_failures - 1)
                    backoff = min(
                        self.config.backoff_max_sec,
                        self.config.backoff_base_sec * (2**exponent),
                    )
                    next_interval = backoff
                else:
                    active_count = len(self.store.get_active_incidents())
                    if active_count > 0:
                        # Faster interval for active incidents / prompt recovery verification
                        next_interval = self.config.active_interval_sec
                    else:
                        next_interval = self.config.normal_interval_sec

                with self._lock:
                    self._current_interval_sec = next_interval

            except Exception as e:
                logger.exception("Unexpected exception in monitoring scheduler loop: %s", e)
                next_interval = self.config.normal_interval_sec

            # Bounded sleep with interruptible stop event
            if self._stop_event.wait(next_interval):
                break

        logger.info("Monitoring scheduler loop exited.")

    # --- Clean Python Inspection and Query API ---

    def get_status(self) -> MonitorStatus:
        """Retrieve current operational status snapshot."""
        with self._lock:
            active_count = len(self.store.get_active_incidents())
            return MonitorStatus(
                is_running=self.is_running,
                data_source=self._last_data_source_health,
                last_evaluated_at=self._last_evaluated_at,
                evaluation_count=self._evaluation_count,
                active_incident_count=active_count,
                monitored_devices=sorted(list(self._devices)),
                current_interval_sec=self._current_interval_sec,
                rules_registered=list(self._rules.keys()),
            )

    def get_active_incidents(self, device_id: Optional[str] = None) -> List[Incident]:
        """Fetch all currently OPEN incidents, optionally filtered by device."""
        return self.store.get_active_incidents(device_id=device_id)

    def get_incident_history(
        self,
        device_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
    ) -> List[Incident]:
        """Query bounded historical incidents with optional filters."""
        return self.store.get_incident_history(
            device_id=device_id,
            rule_id=rule_id,
            state=state,
            limit=limit,
        )

    def get_incident_transitions(self, incident_id: str) -> List[IncidentTransition]:
        """Retrieve chronological state transitions for an incident."""
        return self.store.get_incident_transitions(incident_id=incident_id)

    def cleanup_retention(self, older_than_days: int = 90, batch_size: int = 500) -> int:
        """Trigger explicit retention cleanup of resolved incidents."""
        return self.store.cleanup_retention(older_than_days=older_than_days, batch_size=batch_size)

    def close(self) -> None:
        """Stop background worker and cleanly release all database and client resources."""
        self.stop()
        if not self._external_store:
            self.store.close()
        if not self._external_query:
            self.query_service.close()
