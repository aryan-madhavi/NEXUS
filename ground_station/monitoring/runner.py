"""NEXUS Standalone Background Monitoring Runner.

Runs the deterministic background MonitoringService as a dedicated process:
- Scheduled adaptive evaluations (5s normal, 2s active incident, bounded InfluxDB backoff).
- Durable incident lifecycle and state transitions recorded in SQLite.
- Clean SIGINT and SIGTERM termination with interruptible stop events.
- Never starts competing monitoring workers on the same database.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from ground_station import load_env_file
from ground_station.monitoring.service import MonitoringConfig, MonitoringService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("nexus.monitoring.runner")


def get_utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


class StandaloneMonitoringRunner:
    """Manages the standalone lifecycle of MonitoringService."""

    def __init__(
        self,
        config: Optional[MonitoringConfig] = None,
        duration_sec: int = 0,
    ) -> None:
        self.config = config or MonitoringConfig()
        self.duration_sec = duration_sec
        self.service: Optional[MonitoringService] = None
        self._running = False

    def setup(self) -> bool:
        """Initialize monitoring service and rules."""
        logger.info("Initializing NEXUS Standalone Monitoring Service...")
        logger.info("  Monitored Devices: %s", self.config.devices)
        logger.info("  Incident Database: %s", self.config.db_path)
        logger.info("  Normal Cadence:    %0.1fs", self.config.normal_interval_sec)
        logger.info("  Active Cadence:    %0.1fs", self.config.active_interval_sec)

        self.service = MonitoringService(config=self.config)
        return True

    def run(self) -> int:
        """Execute the monitoring loop until signal or configured duration."""
        if not self.service:
            logger.error("Monitoring service not initialized. Call setup() first.")
            return 1

        self._running = True

        def _sig_handler(signum, frame):
            logger.info("Caught signal %d; initiating graceful monitoring shutdown...", signum)
            self._running = False
            if self.service:
                self.service.stop()

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        logger.info("Starting background monitoring thread...")
        self.service.start()

        start_time = time.monotonic()
        last_log_time = start_time

        try:
            while self._running and self.service.is_running:
                time.sleep(0.5)
                now = time.monotonic()
                elapsed = now - start_time

                if now - last_log_time >= 10.0:
                    last_log_time = now
                    status = self.service.get_status()
                    ds_str = status.data_source.status.value if status.data_source else "UNKNOWN"
                    logger.info(
                        "Status: evaluations=%d, active_incidents=%d, source=%s, cadence=%0.1fs",
                        status.evaluation_count,
                        status.active_incident_count,
                        ds_str,
                        status.current_interval_sec,
                    )

                if self.duration_sec > 0 and elapsed >= self.duration_sec:
                    logger.info("Configured duration (%ds) reached.", self.duration_sec)
                    break
        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
        finally:
            self.shutdown()

        return 0

    def shutdown(self) -> None:
        """Gracefully stop and close service resources."""
        self._running = False
        if self.service:
            logger.info("Stopping monitoring service and releasing resources...")
            self.service.close()
            self.service = None
            logger.info("Monitoring service stopped cleanly.")


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Standalone Background Monitoring Runner")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite incident database")
    parser.add_argument("--devices", type=str, default=None, help="Comma-separated device IDs")
    parser.add_argument("--normal-interval", type=float, default=None, help="Normal evaluation interval (seconds)")
    parser.add_argument("--active-interval", type=float, default=None, help="Active incident interval (seconds)")
    parser.add_argument("--duration", type=int, default=0, help="Run duration in seconds (0 = infinite)")
    args = parser.parse_args()

    env = load_env_file()
    cfg = MonitoringConfig.from_env(env)

    if args.db:
        cfg.db_path = args.db
    if args.devices:
        cfg.devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    if args.normal_interval is not None:
        cfg.normal_interval_sec = args.normal_interval
    if args.active_interval is not None:
        cfg.active_interval_sec = args.active_interval

    runner = StandaloneMonitoringRunner(config=cfg, duration_sec=args.duration)
    if not runner.setup():
        return 1

    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
