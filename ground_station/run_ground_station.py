#!/usr/bin/env python3
"""NEXUS Ground Station — Unified System Runner & Mission Control Server.

Coordinates:
  1. SerialTransportAdapter (/dev/ttyUSB0 by default)
  2. MqttTransportAdapter (Mosquitto broker integration)
  3. NexusHostManager (Thread-safe envelope ingestion & queue management)
  4. CommandRouter (Correlated command dispatch & destination routing)
  5. NexusGroundStationServer (REST API & static web mission control console)

Usage:
  python -m ground_station.run_ground_station
  python ground_station/run_ground_station.py --port 8000 --mock-stream
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ground_station import load_env_file
from ground_station.command_router.command_registry import CommandRegistry
from ground_station.command_router.router import CommandRouter
from ground_station.connection_manager.envelope_parser import (
    EnvelopeParser,
    MessageType,
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
from ground_station.server import NexusGroundStationServer, TelemetryCache

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s UTC] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("NexusGroundStation")


def get_utc_timestamp() -> str:
    """Return formatted UTC timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


class GroundStationOrchestrator:
    """Orchestrates hardware transports, routing, and HTTP mission server."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        serial_port: str = "/dev/ttyUSB0",
        baud_rate: int = 115200,
        enable_serial: bool = True,
        enable_mqtt: bool = True,
        mock_stream: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.enable_serial = enable_serial
        self.enable_mqtt = enable_mqtt
        self.mock_stream = mock_stream

        self.host_manager: Optional[NexusHostManager] = None
        self.serial_adapter: Optional[SerialTransportAdapter] = None
        self.mqtt_adapter: Optional[MqttTransportAdapter] = None
        self.router: Optional[CommandRouter] = None
        self.server: Optional[NexusGroundStationServer] = None
        self.telemetry_cache: TelemetryCache = TelemetryCache()

        self._running = False
        self._mock_thread: Optional[threading.Thread] = None

    def initialize(self) -> bool:
        """Initialize all subsystems and adapters."""
        logger.info("Initializing NEXUS Ground Station Subsystems...")

        # Load environment configuration
        env = load_env_file()
        merged_env = {**env, **os.environ}

        # 1. Initialize Host Manager
        self.host_manager = NexusHostManager(
            queue_capacity=100,
            queue_policy=QueueFullPolicy.DROP_OLDEST,
        )

        # 2. Setup Serial Adapter if enabled
        if self.enable_serial:
            serial_cfg = SerialConfig(
                port=self.serial_port,
                baud_rate=self.baud_rate,
                read_timeout_sec=0.1,
                reconnect_base_delay_sec=1.0,
                reconnect_max_delay_sec=5.0,
            )
            self.serial_adapter = SerialTransportAdapter(config=serial_cfg)
            try:
                self.host_manager.register_adapter("serial", self.serial_adapter)
                logger.info("Registered SerialTransportAdapter on %s @ %d bps", self.serial_port, self.baud_rate)
            except Exception as err:
                logger.warning("Could not register SerialTransportAdapter: %s", err)

        # 3. Setup MQTT Adapter if enabled
        if self.enable_mqtt:
            try:
                mqtt_cfg = MqttConfig.from_env(merged_env)
                self.mqtt_adapter = MqttTransportAdapter(config=mqtt_cfg)
                self.host_manager.register_adapter("mqtt", self.mqtt_adapter)
                logger.info("Registered MqttTransportAdapter on %s:%d (topic: %s)", mqtt_cfg.host, mqtt_cfg.port, mqtt_cfg.topic_subscription)
            except Exception as err:
                logger.warning("Could not register MqttTransportAdapter: %s", err)

        # 3.5 Setup InfluxDB Writer if available
        self.influx_writer = None
        try:
            from ground_station.persistence.influxdb_writer import InfluxDBConfig, InfluxDBWriter
            influx_cfg = InfluxDBConfig.from_env(merged_env)
            self.influx_writer = InfluxDBWriter(config=influx_cfg, name="influxdb")
            self.influx_writer.start()
            self.host_manager.register_consumer(self.influx_writer.write_envelope)
            logger.info("Registered and started InfluxDBWriter to InfluxDB at %s (bucket: %s)", influx_cfg.url, influx_cfg.bucket)
        except Exception as err:
            logger.warning("Could not register InfluxDBWriter: %s", err)

        # 4. Ingestion hook: update telemetry cache and router responses
        def on_envelope_ingested(envelope: ParsedEnvelope) -> None:
            raw_dict = envelope.raw_dict
            env_type = str(raw_dict.get("type", "")).lower()

            # Route responses to CommandRouter if pending
            if (env_type in ("res", "rsp", "resp", "response") or envelope.msg_type == MessageType.RESPONSE) and self.router:
                self.router.route_incoming_envelope(envelope)

            # Ingest sensor readings into TelemetryCache
            if env_type in ("tlm", "dat", "sensor", "ext", "telem", "telemetry") or envelope.msg_type == MessageType.TELEMETRY:
                uptime_val = raw_dict.get("uptime", raw_dict.get("uptime_ms", int(time.time() * 1000) % 86400000))
                heap_val = raw_dict.get("heap")
                heap_kb = int(heap_val / 1024) if heap_val is not None else raw_dict.get("free_heap_kb", 184)
                reading = {
                    "received_at": time.time(),
                    "seq": envelope.seq,
                    "has_data": True,
                    "uptime_ms": uptime_val,
                    "free_heap_kb": heap_kb,
                    "temp": raw_dict.get("temp"),
                    "hum": raw_dict.get("hum"),
                    "dht_valid": raw_dict.get("dht_valid", raw_dict.get("temp") is not None),
                    "ldr": raw_dict.get("ldr"),
                    "x0": raw_dict.get("x0"),
                    "x1": raw_dict.get("x1"),
                    "slot": raw_dict.get("slot"),
                    "dist": raw_dict.get("dist"),
                    "transport": getattr(envelope, "transport", "unknown") or "unknown",
                }
                self.telemetry_cache.update(reading)
            elif env_type in ("hb", "heartbeat", "status") or envelope.msg_type in (MessageType.HEARTBEAT, MessageType.STATUS):
                uptime_val = raw_dict.get("uptime", raw_dict.get("uptime_ms"))
                heap_val = raw_dict.get("heap")
                heap_kb = int(heap_val / 1024) if heap_val is not None else raw_dict.get("free_heap_kb")
                partial: Dict[str, Any] = {"received_at": time.time(), "transport": getattr(envelope, "transport", "unknown") or "unknown"}
                if uptime_val is not None:
                    partial["uptime_ms"] = uptime_val
                if heap_kb is not None:
                    partial["free_heap_kb"] = heap_kb
                self.telemetry_cache.update(partial)

        self.host_manager.register_consumer(on_envelope_ingested)

        # 5. Initialize Command Router
        self.router = CommandRouter(
            host_manager=self.host_manager,
            dev_id="nexus_esp32",
        )

        # 6. Initialize HTTP Mission Server
        self.server = NexusGroundStationServer(
            host=self.host,
            port=self.port,
            host_manager=self.host_manager,
            router=self.router,
        )
        self.server.telemetry_cache = self.telemetry_cache

        return True

    def start(self) -> None:
        """Start all background loops and server."""
        self._running = True
        logger.info("Starting NEXUS Host Manager...")
        if self.host_manager:
            self.host_manager.start()



        # Start mock telemetry generator if requested
        if self.mock_stream:
            self._start_mock_stream()

        # Start HTTP Server (blocking on main thread)
        logger.info("NEXUS Mission Control Panel ready at http://%s:%d", self.host, self.port)
        if self.server:
            self.server.start()
            try:
                while self._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.stop()

    def _start_mock_stream(self) -> None:
        """Generate truthful simulated sensor telemetry for offline UI testing."""
        logger.info("Starting mock telemetry stream (truthful sensor simulation)...")

        def mock_loop() -> None:
            seq = 100
            import math
            while self._running:
                t = time.time()
                # Synthesize realistic environmental readings
                temp = round(24.5 + 2.0 * math.sin(t / 60.0), 1)
                hum = round(52.0 + 5.0 * math.cos(t / 45.0), 1)
                ldr = int(1850 + 400 * math.sin(t / 30.0))
                x0 = int(320 + 80 * math.sin(t / 20.0))
                x1 = int(2048 + 30 * math.cos(t / 15.0))
                slot = 1 if (int(t) % 10 < 3) else 0
                dist = round(18.5 + 4.0 * math.sin(t / 25.0), 1)

                reading = {
                    "received_at": t,
                    "seq": seq,
                    "has_data": True,
                    "uptime_ms": int((t % 86400) * 1000),
                    "free_heap_kb": 182,
                    "temp": temp,
                    "hum": hum,
                    "dht_valid": True,
                    "ldr": ldr,
                    "x0": x0,
                    "x1": x1,
                    "slot": slot,
                    "dist": dist,
                    "transport": "simulation",
                }
                self.telemetry_cache.update(reading)
                seq += 1
                time.sleep(1.0)

        self._mock_thread = threading.Thread(target=mock_loop, name="MockTelemetryStream", daemon=True)
        self._mock_thread.start()

    def stop(self) -> None:
        """Gracefully stop all subsystems."""
        logger.info("Shutting down NEXUS Ground Station...")
        self._running = False

        if self.server:
            self.server.stop()

        if self.host_manager:
            self.host_manager.stop()

        if self.influx_writer:
            self.influx_writer.stop()

        logger.info("NEXUS Ground Station shutdown complete.")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="NEXUS Mission Control Ground Station Runner")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP server listen host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP server listen port (default: 8000)")
    parser.add_argument("--serial-port", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--no-serial", action="store_true", help="Disable serial transport")
    parser.add_argument("--no-mqtt", action="store_true", help="Disable MQTT transport")
    parser.add_argument("--mock-stream", action="store_true", help="Generate simulated telemetry stream for UI testing")

    args = parser.parse_args()

    orchestrator = GroundStationOrchestrator(
        host=args.host,
        port=args.port,
        serial_port=args.serial_port,
        baud_rate=args.baud,
        enable_serial=not args.no_serial,
        enable_mqtt=not args.no_mqtt,
        mock_stream=args.mock_stream,
    )

    def handle_signal(sig: int, frame: object) -> None:
        logger.info("Caught signal %d; initiating graceful termination...", sig)
        orchestrator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if not orchestrator.initialize():
        logger.error("Failed to initialize ground station orchestrator.")
        return 1

    try:
        orchestrator.start()
    except KeyboardInterrupt:
        orchestrator.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
