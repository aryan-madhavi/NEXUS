"""NEXUS Phase 6.1: Controlled USB Serial Ingestion Runner.

Connects SerialTransportAdapter to the physical ESP32 UART interface (/dev/ttyUSB0),
pipes validated envelopes through NexusHostManager into InfluxDBWriter, and records
observable telemetry metrics and database verification.

Hardware Safety:
- No flashing, erasing, or automatic resetting.
- Explicit DTR/RTS reset prevention (ser.dtr=False, ser.rts=False, HUPCL cleared).
- Non-blocking buffered reads with bounded memory and timeout.
- Host services bound exclusively to loopback (127.0.0.1).
- Credentials never logged or printed.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from ground_station import load_env_file
from ground_station.connection_manager.envelope_parser import (
    ParsedEnvelope,
    TelemetryPayload,
)
from ground_station.connection_manager.nexus_host_manager import (
    NexusHostManager,
    QueueFullPolicy,
)
from ground_station.connection_manager.serial_adapter import (
    SerialConfig,
    SerialTransportAdapter,
)
from ground_station.monitoring.service import MonitoringConfig, MonitoringService
from ground_station.persistence.influxdb_writer import (
    InfluxDBConfig,
    InfluxDBWriter,
)

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None


def get_utc_timestamp() -> str:
    """Return formatted UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


class SerialIngestionSession:
    """Orchestrates controlled USB serial ingestion session with full observability."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud_rate: int = 115200,
        duration_sec: int = 30,
        log_path: Optional[str] = None,
        enable_monitoring: bool = False,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.duration_sec = duration_sec
        self.log_path = log_path
        self.enable_monitoring = enable_monitoring or (
            os.environ.get("NEXUS_ENABLE_MONITORING", "").lower() in ("1", "true", "yes")
        )
        self.monitoring_service: Optional[MonitoringService] = None
        self._running = False
        self._log_file = None

        # Telemetry tracking counters
        self.raw_lines_total = 0
        self.boot_log_lines = 0
        self.envelopes_by_type: Dict[str, int] = {}
        self.first_seq: Optional[int] = None
        self.last_seq: Optional[int] = None
        self.first_uptime_ms: Optional[int] = None
        self.last_uptime_ms: Optional[int] = None
        self.detected_reset: bool = False
        self.detected_reset_reason: Optional[str] = None
        self.dht_valid_count = 0
        self.dht_invalid_count = 0
        self.latest_temp: Optional[float] = None
        self.latest_hum: Optional[float] = None
        self.latest_ldr: Optional[int] = None
        self.latest_x0: Optional[int] = None

        # Ground station components
        self.manager: Optional[NexusHostManager] = None
        self.serial_adapter: Optional[SerialTransportAdapter] = None
        self.influx_writer: Optional[InfluxDBWriter] = None
        self.influx_config: Optional[InfluxDBConfig] = None

    def setup(self) -> bool:
        """Initialize configurations and components."""
        print(f"[{get_utc_timestamp()}] Initializing Phase 6.1 Serial Ingestion Session...")
        print(f"  Target Port: {self.port} at {self.baud_rate} baud (8N1, rtscts=False, dsrdtr=False)")
        print(f"  Planned Duration: {self.duration_sec}s")

        # 1. Load configuration safely
        env = load_env_file()
        merged_env = {**env, **os.environ}
        self.influx_config = InfluxDBConfig.from_env(merged_env)
        self.influx_config.batch_size = 1
        self.influx_config.flush_interval_sec = 0.5

        # 2. Open optional log file
        if self.log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            self._log_file = open(self.log_path, "w", encoding="utf-8")
            self._log_file.write("# NEXUS Phase 6.1 Serial Ingestion Capture\n")
            self._log_file.write(f"# Started: {get_utc_timestamp()}\n")
            self._log_file.write(f"# Port: {self.port}, Baud: {self.baud_rate}\n\n")
            self._log_file.flush()

        # 3. Instantiate host manager
        self.manager = NexusHostManager(queue_capacity=200, queue_policy=QueueFullPolicy.DROP_NEWEST)

        # 4. Instantiate serial adapter
        serial_cfg = SerialConfig(
            port=self.port,
            baud_rate=self.baud_rate,
            read_timeout_sec=0.2,
            max_frame_bytes=256,
            reconnect_enabled=True,
            reconnect_base_delay_sec=0.5,
            reconnect_max_delay_sec=5.0,
        )
        self.serial_adapter = SerialTransportAdapter(config=serial_cfg, name="serial")

        # 5. Instantiate InfluxDB writer
        self.influx_writer = InfluxDBWriter(config=self.influx_config, name="influxdb")

        # Wire pipeline: Serial -> Host Manager -> InfluxDB Writer
        self.manager.register_transport(self.serial_adapter)
        self.manager.register_consumer(self._on_envelope_ingested)
        self.manager.register_consumer(self.influx_writer.write_envelope)

        if self.enable_monitoring:
            monitoring_cfg = MonitoringConfig.from_env(merged_env)
            self.monitoring_service = MonitoringService(config=monitoring_cfg)
            print(
                f"  Monitoring Service: ENABLED (db={monitoring_cfg.db_path}, "
                f"interval={monitoring_cfg.normal_interval_sec}s)"
            )

        return True

    def _on_envelope_ingested(self, envelope: ParsedEnvelope) -> None:
        """Observe validated envelopes passing through the host manager."""
        t_name = envelope.msg_type.value
        self.envelopes_by_type[t_name] = self.envelopes_by_type.get(t_name, 0) + 1

        if self.first_seq is None:
            self.first_seq = envelope.seq
        self.last_seq = envelope.seq

        if envelope.uptime_ms is not None:
            if self.first_uptime_ms is None:
                self.first_uptime_ms = envelope.uptime_ms
            self.last_uptime_ms = envelope.uptime_ms

        if isinstance(envelope.payload, TelemetryPayload):
            self.latest_ldr = envelope.payload.ldr_raw
            self.latest_x0 = envelope.payload.x0_raw
            if envelope.payload.dht_valid:
                self.dht_valid_count += 1
                self.latest_temp = envelope.payload.temp
                self.latest_hum = envelope.payload.hum
            else:
                self.dht_invalid_count += 1

        if self._log_file:
            self._log_file.write(f"[{get_utc_timestamp()}] [ENVELOPE] {envelope.raw_text.strip()}\n")
            self._log_file.flush()

    def run(self) -> int:
        """Run the ingestion session for the configured duration."""
        self._running = True

        def _sig_handler(signum, frame):
            print(f"\n[{get_utc_timestamp()}] Caught signal {signum}; initiating clean shutdown...")
            self._running = False

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        print(f"[{get_utc_timestamp()}] Starting InfluxDB persistence writer and host manager...")
        self.influx_writer.start()
        self.manager.start()
        if self.monitoring_service:
            print(f"[{get_utc_timestamp()}] Starting background deterministic monitoring service...")
            self.monitoring_service.start()

        start_time = time.monotonic()
        last_report_time = start_time
        print(f"[{get_utc_timestamp()}] Ingestion loop active. Observing serial stream on {self.port}...\n")

        try:
            while self._running:
                now = time.monotonic()
                elapsed = now - start_time
                if self.duration_sec > 0 and elapsed >= self.duration_sec:
                    print(f"[{get_utc_timestamp()}] Target duration ({self.duration_sec}s) reached.")
                    break

                if now - last_report_time >= 5.0:
                    last_report_time = now
                    self._print_status_report(elapsed)

                time.sleep(0.2)

        finally:
            if self.monitoring_service:
                print(f"[{get_utc_timestamp()}] Stopping background monitoring service...")
                self.monitoring_service.stop()
            print(f"\n[{get_utc_timestamp()}] Stopping serial transport adapter and host manager...")
            self.manager.stop()
            print(f"[{get_utc_timestamp()}] Stopping InfluxDB writer and flushing remaining batches...")
            self.influx_writer.stop()
            if self._log_file:
                self._log_file.close()

        self._print_final_summary()
        self._verify_influxdb_storage()
        return 0

    def _print_status_report(self, elapsed: float) -> None:
        """Print periodic status report to stdout."""
        s_stats = self.serial_adapter.get_stats()
        m_stats = self.manager.get_stats()
        w_stats = self.influx_writer.get_stats()

        dht_status = "N/A"
        if self.latest_temp is not None and self.latest_hum is not None:
            dht_status = f"{self.latest_temp:.1f}°C, {self.latest_hum:.1f}%"
        elif self.dht_invalid_count > 0:
            dht_status = "DEGRADED (temp/hum suppressed)"

        print(
            f"[{get_utc_timestamp()}] [{elapsed:4.1f}s] "
            f"Serial(Conn={s_stats.is_connected}, Read={s_stats.bytes_read}B, Frames={s_stats.frames_received}) | "
            f"HostMgr(Parsed={m_stats.messages_parsed}, Rejects={m_stats.parse_errors}, Q={m_stats.queue_size}) | "
            f"InfluxDB(Writes={w_stats.successful_writes}, Fail={w_stats.write_failures}) | "
            f"DHT: {dht_status}"
        )

    def _print_final_summary(self) -> None:
        """Print complete operational summary."""
        s_stats = self.serial_adapter.get_stats()
        m_stats = self.manager.get_stats()
        w_stats = self.influx_writer.get_stats()

        print("\n" + "=" * 70)
        print("NEXUS PHASE 6.1 — SERIAL INGESTION EXECUTION SUMMARY")
        print("=" * 70)
        print(f"Port / Speed:              {self.port} at {self.baud_rate} baud")
        print(f"Serial Connected:          {s_stats.is_connected} (connects={s_stats.connect_count}, disconnects={s_stats.disconnect_count})")
        print(f"Bytes Read:                {s_stats.bytes_read} bytes")
        print(f"Serial Frames Received:    {s_stats.frames_received}")
        print(f"Serial Frames Forwarded:   {s_stats.frames_forwarded}")
        print(f"Oversized Frames Dropped:  {s_stats.frames_dropped_oversized}")
        print(f"Framing Errors:            {s_stats.framing_errors}")
        print(f"Manager Messages Received: {m_stats.messages_received}")
        print(f"Manager Messages Parsed:   {m_stats.messages_parsed}")
        print(f"Parser Rejects (Non-JSON): {m_stats.parse_errors}")
        print(f"Queue Enqueued:            {m_stats.enqueued_count}")
        print(f"Queue Drops:               {m_stats.dropped_count}")
        print(f"Envelopes by Type:         {self.envelopes_by_type}")
        print(f"Sequence Range:            first={self.first_seq}, last={self.last_seq}")
        print(f"Uptime Range:              first={self.first_uptime_ms}ms, last={self.last_uptime_ms}ms")
        print(f"DHT Telemetry Samples:     valid={self.dht_valid_count}, degraded/invalid={self.dht_invalid_count}")
        if self.latest_temp is not None:
            print(f"Latest Valid Readings:     Temp={self.latest_temp:.1f}°C, Hum={self.latest_hum:.1f}%, LDR={self.latest_ldr}, Gas_X0={self.latest_x0}")
        print(f"InfluxDB Writes:           success={w_stats.successful_writes}, failures={w_stats.write_failures}, queue_drops={w_stats.queue_drops}")
        if self.monitoring_service:
            mon_status = self.monitoring_service.get_status()
            ds_str = mon_status.data_source.status.value if mon_status.data_source else "UNKNOWN"
            print("\nDeterministic Monitoring Status:")
            print(f"  Running:                 {mon_status.is_running}")
            print(f"  Cycle Count:             {mon_status.evaluation_count}")
            print(f"  Active Incidents:        {mon_status.active_incident_count}")
            print(f"  Source State:            {ds_str}")
        print("=" * 70)

    def _verify_influxdb_storage(self) -> None:
        """Query InfluxDB using Flux to verify points landed in storage."""
        if InfluxDBClient is None:
            print("[WARN] influxdb_client not installed; skipping live query verification.")
            return

        print("\n" + "-" * 70)
        print("INFLUXDB DIRECT STORAGE VERIFICATION")
        print("-" * 70)

        try:
            client = InfluxDBClient(
                url=self.influx_config.url,
                token=self.influx_config.token,
                org=self.influx_config.org,
                timeout=self.influx_config.timeout_ms,
            )
            query_api = client.query_api()

            # Query measurements written in the last 15 minutes
            flux_counts = (
                f'from(bucket: "{self.influx_config.bucket}")\n'
                f'  |> range(start: -15m)\n'
                f'  |> filter(fn: (r) => r["_measurement"] =~ /^nexus_/)\n'
                f'  |> group(columns: ["_measurement", "_field"])\n'
                f'  |> count()\n'
            )
            tables = query_api.query(flux_counts)
            print("Aggregated Measurement Counts in Bucket 'nexus_telemetry' (last 15m):")
            record_found = False
            for table in tables:
                for rec in table.records:
                    record_found = True
                    print(f"  Measurement: {rec.values.get('_measurement'):<15} Field: {rec.values.get('_field'):<12} Count: {rec.get_value()}")

            if not record_found:
                print("  [INFO] No records returned for last 15 minutes.")

            # Sample recent telemetry records
            flux_sample = (
                f'from(bucket: "{self.influx_config.bucket}")\n'
                f'  |> range(start: -5m)\n'
                f'  |> filter(fn: (r) => r["_measurement"] == "nexus_telem")\n'
                f'  |> limit(n: 5)\n'
            )
            sample_tables = query_api.query(flux_sample)
            print("\nRecent Telemetry Fields Sample (nexus_telem):")
            for t in sample_tables:
                for r in t.records:
                    print(f"  Time: {r.get_time()} | Field: {r.get_field()} = {r.get_value()} | Tags: dev={r.values.get('dev')} transport={r.values.get('transport')}")

            client.close()
            print("-" * 70)
        except Exception as e:
            print(f"[ERROR] Failed to query InfluxDB for verification: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Phase 6.1 USB Serial Ingestion Runner")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port device path (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud rate (default: 115200)")
    parser.add_argument("--duration", type=int, default=30, help="Run duration in seconds (default: 30, 0 for infinite)")
    parser.add_argument(
        "--log-file",
        default="docs/validation/phase6_1_serial_ingestion.log",
        help="Path to capture serial raw log",
    )
    parser.add_argument(
        "--enable-monitoring",
        action="store_true",
        default=False,
        help="Enable background deterministic incident monitoring service",
    )
    args = parser.parse_args()

    session = SerialIngestionSession(
        port=args.port,
        baud_rate=args.baud,
        duration_sec=args.duration,
        log_path=args.log_file,
        enable_monitoring=args.enable_monitoring,
    )
    if not session.setup():
        return 1
    return session.run()


if __name__ == "__main__":
    sys.exit(main())
