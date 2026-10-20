"""NEXUS Phase 6.3: Simultaneous Multi-Transport Ingestion Runner.

Connects both SerialTransportAdapter (/dev/ttyUSB0) and MqttTransportAdapter (10.12.252.18:1883)
to a unified NexusHostManager, feeding validated envelopes into InfluxDBWriter.
Verifies simultaneous reception, per-transport metrics, absence of queue overflows, and
accurate tag attribution (transport=serial vs transport=mqtt).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ground_station import load_env_file
from ground_station.connection_manager.envelope_parser import (
    ParsedEnvelope,
)
from ground_station.connection_manager.mqtt_adapter import (
    MqttConfig,
    MqttTransportAdapter,
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


class DualTransportIngestionSession:
    """Orchestrates simultaneous Serial + MQTT physical ingestion session."""

    def __init__(
        self,
        serial_port: str = "/dev/ttyUSB0",
        serial_baud: int = 115200,
        mqtt_host: Optional[str] = None,
        mqtt_port: Optional[int] = None,
        mqtt_topic: Optional[str] = None,
        duration_sec: int = 30,
        log_path: Optional[str] = None,
        enable_monitoring: bool = False,
    ) -> None:
        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.duration_sec = duration_sec
        self.log_path = log_path
        self.enable_monitoring = enable_monitoring or (
            os.environ.get("NEXUS_ENABLE_MONITORING", "").lower() in ("1", "true", "yes")
        )
        self.monitoring_service: Optional[MonitoringService] = None
        self._running = False
        self._log_file = None

        # Per-transport counters
        self.counts_by_transport: Dict[str, int] = {"serial": 0, "mqtt": 0}
        self.types_by_transport: Dict[str, Dict[str, int]] = {"serial": {}, "mqtt": {}}
        self.seq_by_transport: Dict[str, List[int]] = {"serial": [], "mqtt": []}

        # Pipeline components
        self.manager: Optional[NexusHostManager] = None
        self.serial_adapter: Optional[SerialTransportAdapter] = None
        self.mqtt_adapter: Optional[MqttTransportAdapter] = None
        self.influx_writer: Optional[InfluxDBWriter] = None
        self.influx_config: Optional[InfluxDBConfig] = None

    def setup(self) -> bool:
        """Initialize configurations and components."""
        print(f"[{get_utc_timestamp()}] Initializing Simultaneous Multi-Transport Session...")

        env = load_env_file()
        merged_env = {**env, **os.environ}

        # InfluxDB Config
        self.influx_config = InfluxDBConfig.from_env(merged_env)
        self.influx_config.batch_size = 2
        self.influx_config.flush_interval_sec = 0.5

        # MQTT Config
        mqtt_cfg = MqttConfig.from_env(merged_env)
        if self.mqtt_host:
            mqtt_cfg.host = self.mqtt_host
        if self.mqtt_port:
            mqtt_cfg.port = self.mqtt_port
        if self.mqtt_topic:
            mqtt_cfg.topic_subscription = self.mqtt_topic

        # Serial Config
        serial_cfg = SerialConfig(
            port=self.serial_port,
            baud_rate=self.serial_baud,
            read_timeout_sec=0.2,
            max_frame_bytes=256,
            reconnect_enabled=True,
            reconnect_base_delay_sec=0.5,
            reconnect_max_delay_sec=5.0,
        )

        print(f"  Serial Transport: {serial_cfg.port} @ {serial_cfg.baud_rate} baud")
        print(f"  MQTT Transport:   {mqtt_cfg.host}:{mqtt_cfg.port} (sub: {mqtt_cfg.topic_subscription})")
        print(f"  Duration:         {self.duration_sec}s")

        if self.log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            self._log_file = open(self.log_path, "w", encoding="utf-8")
            self._log_file.write("# NEXUS Simultaneous Multi-Transport Capture\n")
            self._log_file.write(f"# Started: {get_utc_timestamp()}\n\n")
            self._log_file.flush()

        # Manager & Adapters
        self.manager = NexusHostManager(queue_capacity=500, queue_policy=QueueFullPolicy.DROP_NEWEST)
        self.serial_adapter = SerialTransportAdapter(config=serial_cfg, name="serial")
        self.mqtt_adapter = MqttTransportAdapter(config=mqtt_cfg, name="mqtt")
        self.influx_writer = InfluxDBWriter(config=self.influx_config, name="influxdb")

        # Register transports and consumers
        self.manager.register_transport(self.serial_adapter)
        self.manager.register_transport(self.mqtt_adapter)
        self.manager.register_consumer(self._on_envelope_ingested)
        self.manager.register_consumer(self.influx_writer.write_envelope)

        if self.enable_monitoring:
            # Dual-transport has two adapters, but exactly ONE unified monitoring worker
            monitoring_cfg = MonitoringConfig.from_env(merged_env)
            self.monitoring_service = MonitoringService(config=monitoring_cfg)
            print(
                f"  Monitoring Service: ENABLED (db={monitoring_cfg.db_path}, "
                f"interval={monitoring_cfg.normal_interval_sec}s)"
            )

        return True

    def _on_envelope_ingested(self, envelope: ParsedEnvelope) -> None:
        """Observe envelopes arriving across both transports."""
        tr = envelope.transport or "unknown"
        self.counts_by_transport[tr] = self.counts_by_transport.get(tr, 0) + 1
        
        t_dict = self.types_by_transport.setdefault(tr, {})
        m_type = envelope.msg_type.value
        t_dict[m_type] = t_dict.get(m_type, 0) + 1

        seq_list = self.seq_by_transport.setdefault(tr, [])
        if len(seq_list) < 200:
            seq_list.append(envelope.seq)

        print(
            f"[{get_utc_timestamp()}] [STREAM:{tr:<6}] "
            f"type={m_type:<6} dev={envelope.dev:<12} seq={envelope.seq:<4} uptime={envelope.uptime_ms or 0}ms"
        )

        if self._log_file:
            self._log_file.write(
                f"[{get_utc_timestamp()}] [{tr}] {envelope.raw_text.strip()}\n"
            )
            self._log_file.flush()

    def run(self) -> int:
        """Run the dual-transport session."""
        self._running = True

        def _sig_handler(signum, frame):
            print(f"\n[{get_utc_timestamp()}] Caught signal {signum}; stopping session...")
            self._running = False

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        print(f"[{get_utc_timestamp()}] Starting unified pipeline (Serial + MQTT -> InfluxDB)...")
        if self.influx_writer:
            self.influx_writer.start()
        self.manager.start()
        if self.monitoring_service:
            print(f"[{get_utc_timestamp()}] Starting unified background deterministic monitoring service...")
            self.monitoring_service.start()

        start_time = time.monotonic()
        last_progress_time = start_time

        try:
            while self._running:
                time.sleep(0.1)
                now = time.monotonic()
                elapsed = now - start_time

                if now - last_progress_time >= 5.0:
                    last_progress_time = now
                    s_conn = "CONNECTED" if self.serial_adapter.is_connected else "DISCONNECTED"
                    m_conn = "CONNECTED" if self.mqtt_adapter.is_connected else "DISCONNECTED"
                    print(
                        f"[{get_utc_timestamp()}] Progress ({int(elapsed)}s): "
                        f"Serial({s_conn}, pkts={self.counts_by_transport.get('serial', 0)}) | "
                        f"MQTT({m_conn}, pkts={self.counts_by_transport.get('mqtt', 0)}) | "
                        f"Queue={self.manager.get_stats().queue_size}"
                    )

                if self.duration_sec > 0 and elapsed >= self.duration_sec:
                    print(f"[{get_utc_timestamp()}] Target duration ({self.duration_sec}s) reached.")
                    break

        except KeyboardInterrupt:
            print(f"\n[{get_utc_timestamp()}] User interrupted.")
        finally:
            self.shutdown()

        self.print_summary()
        self.verify_database()
        return 0

    def shutdown(self) -> None:
        """Clean shutdown of adapters and persistent queues."""
        print(f"[{get_utc_timestamp()}] Stopping pipeline components...")
        self._running = False
        if self.monitoring_service:
            print(f"[{get_utc_timestamp()}] Stopping background monitoring service...")
            self.monitoring_service.stop()
        if self.manager:
            self.manager.stop()
        if self.influx_writer:
            self.influx_writer.stop()
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        print(f"[{get_utc_timestamp()}] Pipeline stopped cleanly.")

    def print_summary(self) -> None:
        """Print detailed summary statistics."""
        print("\n" + "=" * 70)
        print("NEXUS PHASE 6.3 SIMULTANEOUS MULTI-TRANSPORT EXECUTION SUMMARY")
        print("=" * 70)
        print(f"Serial Envelopes Ingested: {self.counts_by_transport.get('serial', 0)}")
        print(f"  Types:                   {self.types_by_transport.get('serial', {})}")
        s_seqs = self.seq_by_transport.get('serial', [])
        if s_seqs:
            print(f"  Sequence Range:          min={min(s_seqs)}, max={max(s_seqs)}, count={len(s_seqs)}")

        print(f"MQTT Envelopes Ingested:   {self.counts_by_transport.get('mqtt', 0)}")
        print(f"  Types:                   {self.types_by_transport.get('mqtt', {})}")
        m_seqs = self.seq_by_transport.get('mqtt', [])
        if m_seqs:
            print(f"  Sequence Range:          min={min(m_seqs)}, max={max(m_seqs)}, count={len(m_seqs)}")

        s_stats = self.serial_adapter.get_stats()
        print("\nSerial Adapter Stats:")
        print(f"  Connected:               {s_stats.is_connected} (connects={s_stats.connect_count}, disconnects={s_stats.disconnect_count})")
        print(f"  Bytes Read:              {s_stats.bytes_read}")
        print(f"  Frames Received:         {s_stats.frames_received}")
        print(f"  Frames Forwarded:        {s_stats.frames_forwarded}")

        m_stats = self.mqtt_adapter.get_stats()
        print("\nMQTT Adapter Stats:")
        print(f"  Connected:               {m_stats.is_connected} (connects={m_stats.connect_count}, disconnects={m_stats.disconnect_count})")
        print(f"  Messages Received:       {m_stats.messages_received}")
        print(f"  Messages Forwarded:      {m_stats.messages_forwarded}")

        mgr_stats = self.manager.get_stats()
        print("\nHost Manager Unified Stats:")
        print(f"  Messages Received:       {mgr_stats.messages_received}")
        print(f"  Messages Parsed:         {mgr_stats.messages_parsed}")
        print(f"  Parse Errors:            {mgr_stats.parse_errors}")
        print(f"  Enqueued:                {mgr_stats.enqueued_count}")
        print(f"  Queue Overflow Drops:    {mgr_stats.dropped_count}")
        print(f"  Queue High-Water Mark:   {mgr_stats.queue_hwm}")

        w_stats = self.influx_writer.get_stats()
        print("\nInfluxDB Writer Stats:")
        print(f"  Accepted Records:        {w_stats.accepted_records}")
        print(f"  Successful Writes:       {w_stats.successful_writes}")
        print(f"  Write Failures:          {w_stats.write_failures}")
        print(f"  Queue Drops:             {w_stats.queue_drops}")

        if self.monitoring_service:
            mon_status = self.monitoring_service.get_status()
            ds_str = mon_status.data_source.status.value if mon_status.data_source else "UNKNOWN"
            print("\nDeterministic Monitoring Status:")
            print(f"  Running:                 {mon_status.is_running}")
            print(f"  Cycle Count:             {mon_status.evaluation_count}")
            print(f"  Active Incidents:        {mon_status.active_incident_count}")
            print(f"  Source State:            {ds_str}")
        print("=" * 70)

    def verify_database(self) -> None:
        """Query InfluxDB for both transport tags."""
        if InfluxDBClient is None:
            return

        print("\n" + "-" * 70)
        print("INFLUXDB DIRECT DUAL-TRANSPORT STORAGE VERIFICATION")
        print("-" * 70)
        try:
            client = InfluxDBClient(
                url=self.influx_config.url,
                token=self.influx_config.token,
                org=self.influx_config.org,
                timeout=5000,
            )
            query_api = client.query_api()

            query = f'''
            from(bucket: "{self.influx_config.bucket}")
              |> range(start: -15m)
              |> filter(fn: (r) => r.dev == "nexus_esp32" and (r.transport == "serial" or r.transport == "mqtt"))
              |> group(columns: ["transport", "_measurement"])
              |> count()
            '''
            tables = query_api.query(query, org=self.influx_config.org)
            for table in tables:
                for record in table.records:
                    tr = record.values.get("transport")
                    m = record.values.get("_measurement")
                    c = record.get_value()
                    print(f"  Transport: {tr:<8} Measurement: {m:<15} Points: {c}")

            client.close()
        except Exception as e:
            print(f"Database query failed: {e}")
        print("-" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Simultaneous Multi-Transport Ingestion Runner")
    parser.add_argument("--serial-port", type=str, default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--mqtt-host", type=str, default=None, help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=None, help="MQTT broker port")
    parser.add_argument("--duration", type=int, default=30, help="Run duration in seconds")
    parser.add_argument("--log-file", type=str, default=None, help="Capture log path")
    parser.add_argument(
        "--enable-monitoring",
        action="store_true",
        default=False,
        help="Enable background deterministic incident monitoring service",
    )
    args = parser.parse_args()

    session = DualTransportIngestionSession(
        serial_port=args.serial_port,
        serial_baud=args.baud,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        duration_sec=args.duration,
        log_path=args.log_file,
        enable_monitoring=args.enable_monitoring,
    )

    if not session.setup():
        return 1

    return session.run()


if __name__ == "__main__":
    sys.exit(main())
