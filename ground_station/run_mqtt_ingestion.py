"""NEXUS Phase 6.3: Controlled Wi-Fi/MQTT Ingestion Runner.

Subscribes MqttTransportAdapter to the physical ESP32 telemetry topic (nexus/+/telemetry),
pipes validated envelopes through NexusHostManager into InfluxDBWriter, and records
observable telemetry metrics and direct database verification.

Hardware & Security Safety:
- Operates against authenticated Mosquitto broker (allow_anonymous false, ACLs enforced).
- Credentials loaded safely from .env and masked in all logs and outputs.
- Non-blocking asynchronous message parsing and bounded worker thread batching.
- Validates protocol v1 envelope constraints (max 256B, valid JSON, finite numbers).
- Omits invalid DHT sensor readings from InfluxDB points (never zero-filled).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ground_station import load_env_file
from ground_station.connection_manager.envelope_parser import (
    MessageType,
    ParsedEnvelope,
    TelemetryPayload,
)
from ground_station.connection_manager.mqtt_adapter import (
    MqttConfig,
    MqttTransportAdapter,
)
from ground_station.connection_manager.nexus_host_manager import (
    NexusHostManager,
    QueueFullPolicy,
)
from ground_station.persistence.influxdb_writer import (
    InfluxDBConfig,
    InfluxDBWriter,
)
from ground_station.persistence.point_mapper import PointMapper

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None


def get_utc_timestamp() -> str:
    """Return formatted UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


class MqttIngestionSession:
    """Orchestrates controlled MQTT telemetry ingestion session with full observability."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        topic: Optional[str] = None,
        duration_sec: int = 30,
        log_path: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.topic = topic
        self.duration_sec = duration_sec
        self.log_path = log_path
        self._running = False
        self._log_file = None

        # Telemetry tracking counters
        self.messages_total = 0
        self.envelopes_by_type: Dict[str, int] = {}
        self.devices_seen: set = set()
        self.first_seq: Optional[int] = None
        self.last_seq: Optional[int] = None
        self.first_uptime_ms: Optional[int] = None
        self.last_uptime_ms: Optional[int] = None
        self.dht_valid_count = 0
        self.dht_invalid_count = 0
        self.latest_temp: Optional[float] = None
        self.latest_hum: Optional[float] = None
        self.latest_ldr: Optional[int] = None
        self.latest_x0: Optional[int] = None

        # Ground station components
        self.manager: Optional[NexusHostManager] = None
        self.mqtt_adapter: Optional[MqttTransportAdapter] = None
        self.influx_writer: Optional[InfluxDBWriter] = None
        self.influx_config: Optional[InfluxDBConfig] = None
        self.mqtt_config: Optional[MqttConfig] = None

    def setup(self) -> bool:
        """Initialize configurations and components."""
        print(f"[{get_utc_timestamp()}] Initializing Phase 6.3 MQTT Ingestion Session...")

        # 1. Load configuration safely
        env = load_env_file()
        merged_env = {**env, **os.environ}

        self.mqtt_config = MqttConfig.from_env(merged_env)
        if self.host:
            self.mqtt_config.host = self.host
        if self.port:
            self.mqtt_config.port = self.port
        if self.topic:
            self.mqtt_config.topic_subscription = self.topic

        self.influx_config = InfluxDBConfig.from_env(merged_env)
        self.influx_config.batch_size = 1
        self.influx_config.flush_interval_sec = 0.5

        print(f"  Target Broker: {self.mqtt_config.host}:{self.mqtt_config.port}")
        print(f"  Topic Subscription: {self.mqtt_config.topic_subscription}")
        print(f"  Planned Duration: {self.duration_sec}s")

        # 2. Open optional log file
        if self.log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            self._log_file = open(self.log_path, "w", encoding="utf-8")
            self._log_file.write(f"# NEXUS Phase 6.3 MQTT Ingestion Capture\n")
            self._log_file.write(f"# Started: {get_utc_timestamp()}\n")
            self._log_file.write(f"# Broker: {self.mqtt_config.host}:{self.mqtt_config.port}\n")
            self._log_file.write(f"# Subscription: {self.mqtt_config.topic_subscription}\n\n")
            self._log_file.flush()

        # 3. Instantiate host manager
        self.manager = NexusHostManager(queue_capacity=200, queue_policy=QueueFullPolicy.DROP_NEWEST)

        # 4. Instantiate MQTT adapter
        self.mqtt_adapter = MqttTransportAdapter(config=self.mqtt_config, name="mqtt")

        # 5. Instantiate InfluxDB writer
        self.influx_writer = InfluxDBWriter(config=self.influx_config, name="influxdb")

        # Wire pipeline: MQTT -> Host Manager -> InfluxDB Writer
        self.manager.register_transport(self.mqtt_adapter)
        self.manager.register_consumer(self._on_envelope_ingested)
        self.manager.register_consumer(self.influx_writer.write_envelope)

        return True

    def _on_envelope_ingested(self, envelope: ParsedEnvelope) -> None:
        """Observe validated envelopes passing through the host manager."""
        self.messages_total += 1
        t_name = envelope.msg_type.value
        self.envelopes_by_type[t_name] = self.envelopes_by_type.get(t_name, 0) + 1
        self.devices_seen.add(envelope.dev)

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

        dht_info = f"temp={self.latest_temp}°C hum={self.latest_hum}%" if envelope.msg_type == MessageType.TELEMETRY and self.latest_temp is not None else ""
        print(f"[{get_utc_timestamp()}] [ENVELOPE] type={t_name:<6} dev={envelope.dev:<12} seq={envelope.seq:<4} uptime={envelope.uptime_ms or 0}ms {dht_info}")

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

        print(f"[{get_utc_timestamp()}] Starting Ground Station MQTT pipeline...")
        if self.influx_writer:
            self.influx_writer.start()
        self.manager.start()

        start_time = time.monotonic()
        last_progress_time = start_time

        try:
            while self._running:
                time.sleep(0.1)
                elapsed = time.monotonic() - start_time

                if time.monotonic() - last_progress_time >= 5.0:
                    last_progress_time = time.monotonic()
                    conn_str = "CONNECTED" if self.mqtt_adapter.is_connected else "CONNECTING/DISCONNECTED"
                    print(
                        f"[{get_utc_timestamp()}] Progress: elapsed={int(elapsed)}s, "
                        f"mqtt_state={conn_str}, messages={self.messages_total}, "
                        f"types={self.envelopes_by_type}"
                    )

                if self.duration_sec > 0 and elapsed >= self.duration_sec:
                    print(f"[{get_utc_timestamp()}] Configured duration ({self.duration_sec}s) reached.")
                    break

        except KeyboardInterrupt:
            print(f"\n[{get_utc_timestamp()}] Interrupted by user.")
        finally:
            self.shutdown()

        self.print_summary()
        self.verify_database()
        return 0

    def shutdown(self) -> None:
        """Clean shutdown of adapters and persistent queues."""
        print(f"[{get_utc_timestamp()}] Stopping pipeline components...")
        self._running = False
        if self.manager:
            self.manager.stop()
        if self.influx_writer:
            self.influx_writer.stop()
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        print(f"[{get_utc_timestamp()}] Pipeline stopped cleanly.")

    def print_summary(self) -> None:
        """Print detailed session summary statistics."""
        print("\n" + "=" * 70)
        print("NEXUS PHASE 6.3 MQTT INGESTION SESSION SUMMARY")
        print("=" * 70)
        print(f"Total Envelopes Ingested:  {self.messages_total}")
        print(f"Envelopes by Type:         {self.envelopes_by_type}")
        print(f"Devices Observed:          {sorted(list(self.devices_seen))}")
        print(f"Sequence Range:            first={self.first_seq}, last={self.last_seq}")
        print(f"Uptime Range (ms):         first={self.first_uptime_ms}, last={self.last_uptime_ms}")
        print(f"DHT Samples:               valid={self.dht_valid_count}, invalid={self.dht_invalid_count}")
        if self.latest_temp is not None:
            print(f"Latest Environmental Data: temp={self.latest_temp}°C, hum={self.latest_hum}%, ldr={self.latest_ldr}, x0={self.latest_x0}")

        if self.mqtt_adapter:
            stats = self.mqtt_adapter.get_stats()
            print("\nMQTT Transport Stats:")
            print(f"  Connected:               {stats.is_connected}")
            print(f"  Connect Count:           {stats.connect_count}")
            print(f"  Disconnect Count:        {stats.disconnect_count}")
            print(f"  Messages Received:       {stats.messages_received}")
            print(f"  Messages Forwarded:      {stats.messages_forwarded}")
            print(f"  Topic Mismatches:        {stats.topic_mismatch_errors}")
            print(f"  Identity Mismatches:     {stats.identity_mismatch_errors}")
            print(f"  IO Errors:               {stats.io_errors}")

        if self.manager:
            stats = self.manager.get_stats()
            print("\nHost Manager Stats:")
            print(f"  Messages Received:       {stats.messages_received}")
            print(f"  Messages Parsed:         {stats.messages_parsed}")
            print(f"  Parse Errors:            {stats.parse_errors}")
            print(f"  Enqueued:                {stats.enqueued_count}")
            print(f"  Dequeued:                {stats.dequeued_count}")
            print(f"  Queue Overflow Drops:    {stats.dropped_count}")
            print(f"  Queue High-Water Mark:   {stats.queue_hwm}")

        if self.influx_writer:
            stats = self.influx_writer.get_stats()
            print("\nInfluxDB Writer Stats:")
            print(f"  Accepted Records:        {stats.accepted_records}")
            print(f"  Successful Writes:       {stats.successful_writes}")
            print(f"  Write Failures:          {stats.write_failures}")
            print(f"  Retries Attempted:       {stats.retries_attempted}")
            print(f"  Permanent Drops:         {stats.retries_exhausted_drops}")
            print(f"  Queue Overflow Drops:    {stats.queue_drops}")
            print(f"  Queue High-Water Mark:   {stats.queue_hwm}")
        print("=" * 70)

    def verify_database(self) -> None:
        """Query InfluxDB directly to verify persisted records with transport=mqtt."""
        if InfluxDBClient is None:
            print("[WARN] influxdb_client not installed; skipping direct database verification.")
            return

        print("\n" + "-" * 70)
        print("INFLUXDB DIRECT STORAGE VERIFICATION (transport=mqtt)")
        print("-" * 70)
        try:
            client = InfluxDBClient(
                url=self.influx_config.url,
                token=self.influx_config.token,
                org=self.influx_config.org,
                timeout=5000,
            )
            query_api = client.query_api()

            # Query count of records by measurement and field for transport=mqtt in last 15m
            count_query = f'''
            from(bucket: "{self.influx_config.bucket}")
              |> range(start: -15m)
              |> filter(fn: (r) => r.transport == "mqtt")
              |> group(columns: ["_measurement", "_field"])
              |> count()
            '''
            tables = query_api.query(count_query, org=self.influx_config.org)
            print(f"Aggregated MQTT Measurement Counts in Bucket '{self.influx_config.bucket}' (last 15m):")
            found_any = False
            for table in tables:
                for record in table.records:
                    found_any = True
                    m = record.values.get("_measurement")
                    f = record.values.get("_field")
                    c = record.get_value()
                    print(f"  Measurement: {m:<15} Field: {f:<12} Count: {c}")

            if not found_any:
                print("  [INFO] No MQTT-tagged records found in the last 15m window.")

            # Query sample of recent records for nexus_esp32
            sample_query = f'''
            from(bucket: "{self.influx_config.bucket}")
              |> range(start: -15m)
              |> filter(fn: (r) => r.transport == "mqtt" and r.dev == "nexus_esp32")
              |> filter(fn: (r) => r._measurement == "nexus_telem")
              |> limit(n: 5)
            '''
            tables = query_api.query(sample_query, org=self.influx_config.org)
            print("\nRecent Telemetry Fields Sample (nexus_telem, transport=mqtt):")
            for table in tables:
                for record in table.records:
                    print(f"  Time: {record.get_time()} | Field: {record.get_field()} = {record.get_value()} | Tags: dev={record.values.get('dev')} transport={record.values.get('transport')}")

            client.close()
        except Exception as e:
            print(f"Direct InfluxDB verification query failed: {e}")
        print("-" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS Phase 6.3 Wi-Fi/MQTT Ingestion Runner")
    parser.add_argument("--host", type=str, default=None, help="MQTT broker host address")
    parser.add_argument("--port", type=int, default=None, help="MQTT broker port")
    parser.add_argument("--topic", type=str, default=None, help="MQTT topic subscription filter")
    parser.add_argument("--duration", type=int, default=30, help="Run duration in seconds (default: 30, 0 for infinite)")
    parser.add_argument("--log-file", type=str, default=None, help="Path to capture raw telemetry log")
    args = parser.parse_args()

    session = MqttIngestionSession(
        host=args.host,
        port=args.port,
        topic=args.topic,
        duration_sec=args.duration,
        log_path=args.log_file,
    )

    if not session.setup():
        return 1

    return session.run()


if __name__ == "__main__":
    sys.exit(main())
