"""NEXUS Ground Station REST API & Web Mission Control Server.

Serves the browser-based mission control panel, provides registry-driven command dispatch,
real-time telemetry inspection, sensor capabilities, service reachability checks, and
bounded audit logs. Uses standard library HTTP server for zero-dependency portability.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

from ground_station.command_router.command_registry import (
    CommandDestination,
    CommandRegistry,
    StatusCode,
)
from ground_station.command_router.router import CommandRouter
from ground_station.connection_manager.envelope_parser import (
    MessageType,
    ParsedEnvelope,
    TelemetryPayload,
)
from ground_station.connection_manager.nexus_host_manager import NexusHostManager

logger = logging.getLogger("nexus.server")

STATIC_DIR = Path(__file__).parent / "static"


class TelemetryCache:
    """Thread-safe cache of latest telemetry, sensors, and recent history."""

    def __init__(self, max_history: int = 100) -> None:
        self._lock = threading.Lock()
        self._max_history = max_history
        self._latest_telemetry: Dict[str, Any] = {
            "received_at": None,
            "transport": None,
            "dev": "nexus_esp32",
            "seq": 0,
            "temp": 0.0,
            "hum": 0.0,
            "dht_valid": False,
            "ldr": 0,
            "x0": 0,
            "x1": 0,
            "slot": 0,
            "dist": 0,
            "uptime_ms": 0,
            "heap": 0,
            "ticks": 0,
            "has_data": False,
        }
        self._history: List[Dict[str, Any]] = []

    def update(self, envelope: Union[ParsedEnvelope, Dict[str, Any]]) -> None:
        """Update cache from a parsed envelope or direct telemetry dictionary."""
        now = time.time()
        with self._lock:
            if isinstance(envelope, dict):
                entry = dict(envelope)
                if "received_at" not in entry:
                    entry["received_at"] = now
                entry["has_data"] = True
                self._latest_telemetry.update(entry)
                self._history.append(entry)
                if len(self._history) > self._max_history:
                    self._history.pop(0)
                return

            if envelope.msg_type == MessageType.TELEMETRY:
                fields: Dict[str, Any] = {}
                if hasattr(envelope, "raw_dict") and envelope.raw_dict:
                    fields = dict(envelope.raw_dict)
                elif isinstance(envelope.payload, TelemetryPayload):
                    fields = {
                        "temp": envelope.payload.temp,
                        "hum": envelope.payload.hum,
                        "dht_valid": envelope.payload.dht_valid,
                        "ldr": envelope.payload.ldr_raw,
                        "x0": envelope.payload.x0_raw,
                        "x1": envelope.payload.x1_raw,
                        "slot": envelope.payload.slot_state,
                        "dist": envelope.payload.dist_cm,
                        "uptime": envelope.payload.uptime_ms,
                    }

                entry = {
                    "received_at": now,
                    "transport": envelope.transport or "unknown",
                    "dev": envelope.dev,
                    "seq": envelope.seq,
                    "temp": fields.get("temp", fields.get("dht_temp", 0.0)),
                    "hum": fields.get("hum", fields.get("dht_hum", 0.0)),
                    "dht_valid": bool(fields.get("dht_valid", True)),
                    "ldr": fields.get("ldr", fields.get("ldr_raw", 0)),
                    "x0": fields.get("x0", fields.get("mux_x0", 0)),
                    "x1": fields.get("x1", fields.get("mux_x1", 0)),
                    "slot": fields.get("slot", fields.get("slot_state", fields.get("moc7811", 0))),
                    "dist": fields.get("dist", fields.get("dist_cm", fields.get("distance_cm", 0))),
                    "uptime_ms": fields.get("uptime", fields.get("uptime_ms", 0)),
                    "heap": fields.get("heap", 0),
                    "ticks": fields.get("ticks", 0),
                    "has_data": True,
                }
                self._latest_telemetry = entry
                self._history.append(entry)
                if len(self._history) > self._max_history:
                    self._history.pop(0)

    def get_latest(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._latest_telemetry)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])


def check_port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """Check if a TCP port is open and listening."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        res = sock.connect_ex((host, port))
        return res == 0
    except Exception:
        return False
    finally:
        sock.close()


class NexusRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for NEXUS Ground Station API and static UI."""

    server_version = "NexusGroundStation/1.0"

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for static UI assets and REST APIs."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)

        # Static assets
        if path == "/" or path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/styles.css":
            self._serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        # Navigation routes (SPA overview and diagnostics)
        elif path == "/overview":
            self._redirect_to("/#tab-dashboard")
        elif path == "/diagnostics":
            if "application/json" in self.headers.get("Accept", ""):
                self._handle_api_diagnostics()
            else:
                self._redirect_to("/#tab-services")
        # REST APIs
        elif path == "/api/status":
            self._handle_api_status()
        elif path == "/api/registry":
            self._handle_api_registry()
        elif path == "/api/telemetry/latest":
            self._handle_api_telemetry_latest()
        elif path == "/api/sensors":
            self._handle_api_sensors()
        elif path == "/api/commands":
            self._handle_api_commands()
        elif path == "/api/services":
            self._handle_api_services()
        elif path == "/api/export":
            self._handle_api_export(query)
        elif path == "/api/diagnostics":
            self._handle_api_diagnostics()
        elif path == "/api/incidents":
            self._handle_api_incidents()
        else:
            self._send_json({"error": "Not Found", "path": path}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """Handle POST requests for command execution."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/command":
            self._handle_api_command()
        else:
            self._send_json({"error": "Not Found", "path": path}, status=HTTPStatus.NOT_FOUND)

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        """Serve a static file from disk safely."""
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"error": "File Not Found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._send_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as err:
            logger.error("Error serving static file %s: %s", file_path, err)
            self._send_json({"error": "Internal Server Error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _redirect_to(self, location: str) -> None:
        """Send a 302 Found redirect."""
        self.send_response(HTTPStatus.FOUND)
        self._send_cors_headers()
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Serialize and send JSON response."""
        try:
            payload = json.dumps(
                data,
                indent=2 if status != HTTPStatus.OK else None,
                default=lambda o: dict(o) if hasattr(o, "items") else (list(o) if hasattr(o, "__iter__") and not isinstance(o, (str, bytes)) else str(o))
            ).encode("utf-8")
            self.send_response(status)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as err:
            logger.error("Error writing JSON response: %s", err)

    def _handle_api_status(self) -> None:
        """Return comprehensive system, transport, connection, and service status."""
        server = self.server  # type: ignore[attr-defined]
        host_mgr: Optional[NexusHostManager] = getattr(server, "host_manager", None)
        router: Optional[CommandRouter] = getattr(server, "router", None)
        cache: TelemetryCache = getattr(server, "telemetry_cache")

        # Transport & connection metrics
        mgr_stats = host_mgr.get_stats() if host_mgr else None
        serial_connected = False
        mqtt_connected = False
        active_transport = "NONE"

        if mgr_stats and mgr_stats.adapters:
            ser_dict = mgr_stats.adapters.get("serial", {})
            mq_dict = mgr_stats.adapters.get("mqtt", {})
            serial_connected = bool(ser_dict.get("is_connected", False))
            mqtt_connected = bool(mq_dict.get("is_connected", False))

            if serial_connected and mqtt_connected:
                active_transport = "DUAL"
            elif serial_connected:
                active_transport = "SERIAL"
            elif mqtt_connected:
                active_transport = "MQTT"

        # Check external local services
        grafana_ok = check_port_open("127.0.0.1", 3000)
        influx_ok = check_port_open("127.0.0.1", 8086)
        webui_ok = check_port_open("127.0.0.1", 8080)

        router_stats = router.stats if router else None
        latest = cache.get_latest()

        status_payload = {
            "device_id": getattr(router, "_dev_id", "nexus_esp32"),
            "connected": serial_connected or mqtt_connected,
            "active_transport": active_transport,
            "transports": {
                "serial": {
                    "connected": serial_connected,
                    "stats": mgr_stats.adapters.get("serial", {}) if mgr_stats else {},
                },
                "mqtt": {
                    "connected": mqtt_connected,
                    "stats": mgr_stats.adapters.get("mqtt", {}) if mgr_stats else {},
                },
            },
            "services": {
                "ground_station": {"status": "online", "url": "http://127.0.0.1:8000"},
                "grafana": {"status": "online" if grafana_ok else "offline", "port": 3000, "url": "http://127.0.0.1:3000"},
                "influxdb": {"status": "online" if influx_ok else "offline", "port": 8086, "url": "http://127.0.0.1:8086"},
                "open_webui": {"status": "online" if webui_ok else "offline", "port": 8080, "url": "http://127.0.0.1:8080"},
            },
            "capabilities": {
                "mounted": [
                    {"id": "ldr", "name": "LDR Light Sensor", "gpio": 35, "bus": "ADC1_CH7"},
                    {"id": "dht11", "name": "DHT11 Temp & Humidity", "gpio": 19, "bus": "Single-Wire"},
                    {"id": "cd4051_x0", "name": "Infrared Sensor IR-1 (CD4051 X0)", "gpio": 36, "bus": "Analog Mux"},
                    {"id": "moc7811", "name": "MOC7811 Slot Optocoupler", "gpio": 34, "bus": "Digital Input"},
                    {"id": "hcsr04", "name": "HC-SR04 Ultrasonic Distance", "gpio": "25/26", "bus": "Trig/Echo"},
                    {"id": "leds", "name": "Status LEDs 1-4", "gpio": "27,14,12,13", "bus": "GPIO Output"},
                    {"id": "buzzer", "name": "Active Buzzer", "gpio": 15, "bus": "GPIO Output"},
                    {"id": "74hc595", "name": "74HC595 Shift Register", "gpio": "16,17,21", "bus": "SPI Shift"},
                ],
                "unmounted": [
                    {"id": "cd4051_x1", "name": "Hall Magnetic Sensor (IC2)", "gpio": 36, "reason": "Not physically installed on EDU_ROBO board"},
                    {"id": "touch", "name": "Touch Sensor", "gpio": 18, "reason": "Module not physically mounted"},
                    {"id": "vibration", "name": "Vibration Sensor", "gpio": 23, "reason": "Module not physically mounted"},
                    {"id": "sound", "name": "Sound Sensor", "gpio": 32, "reason": "Module not physically mounted"},
                    {"id": "servo", "name": "Servo Motor", "gpio": 33, "reason": "Actuator not physically mounted"},
                    {"id": "lm35", "name": "LM35 Temperature Sensor", "gpio": 39, "reason": "Sensor not physically mounted"},
                    {"id": "lcd", "name": "16x2 Character LCD", "gpio": "21+", "reason": "Display not installed"},
                    {"id": "relay_k1", "name": "Relay K1", "gpio": 3, "reason": "Relay unmounted"},
                    {"id": "dc_motors", "name": "L293D DC Motors", "gpio": "27,14,12,13,22", "reason": "Motors unmounted"},
                ],
            },
            "ingestion": {
                "messages_received": mgr_stats.messages_received if mgr_stats else 0,
                "messages_parsed": mgr_stats.messages_parsed if mgr_stats else 0,
                "parse_errors": mgr_stats.parse_errors if mgr_stats else 0,
                "queue_size": mgr_stats.queue_size if mgr_stats else 0,
                "queue_capacity": mgr_stats.queue_capacity if mgr_stats else 100,
                "dropped_count": mgr_stats.dropped_count if mgr_stats else 0,
            },
            "commands": {
                "inbound_received": router_stats.inbound_commands_received if router_stats else 0,
                "outbound_dispatched": router_stats.outbound_commands_dispatched if router_stats else 0,
                "responses_received": router_stats.inbound_responses_received if router_stats else 0,
                "routing_errors": router_stats.routing_errors if router_stats else 0,
            },
            "latest_telemetry_age_sec": round(time.time() - latest["received_at"], 1) if latest.get("received_at") else None,
            "timestamp": time.time(),
        }
        self._send_json(status_payload)

    def _handle_api_registry(self) -> None:
        """Return the machine-readable command schema catalog."""
        schema = CommandRegistry.get_catalog_schema()
        self._send_json({
            "status": "ok",
            "total_commands": schema["total_commands"],
            "verbs": schema["verbs"],
            "catalog": schema["catalog"],
        })

    def _handle_api_telemetry_latest(self) -> None:
        """Return the latest cached sensor readings."""
        server = self.server  # type: ignore[attr-defined]
        cache: TelemetryCache = getattr(server, "telemetry_cache")
        self._send_json(cache.get_latest())

    def _handle_api_sensors(self) -> None:
        """Return active sensors status with truthful values."""
        server = self.server  # type: ignore[attr-defined]
        cache: TelemetryCache = getattr(server, "telemetry_cache")
        latest = cache.get_latest()

        sensors = [
            {
                "id": "dht11_temp",
                "name": "Ambient Temperature",
                "category": "environment",
                "value": latest.get("temp"),
                "unit": "°C",
                "valid": latest.get("dht_valid", False),
                "mounted": True,
                "pin": 19,
            },
            {
                "id": "dht11_hum",
                "name": "Relative Humidity",
                "category": "environment",
                "value": latest.get("hum"),
                "unit": "%",
                "valid": latest.get("dht_valid", False),
                "mounted": True,
                "pin": 19,
            },
            {
                "id": "ldr",
                "name": "Light Intensity",
                "category": "optical",
                "value": latest.get("ldr"),
                "unit": "ADC (0-4095)",
                "valid": latest.get("has_data", False),
                "mounted": True,
                "pin": 35,
            },
            {
                "id": "mux_x0",
                "name": "Infrared Sensor IR-1 (CD4051 X0)",
                "category": "optical",
                "value": latest.get("x0"),
                "unit": "Raw ADC (0-4095)",
                "valid": latest.get("has_data", False),
                "mounted": True,
                "status": "Installed",
                "pin": "36 (X0)",
            },
            {
                "id": "hall_x1",
                "name": "Hall Magnetic Sensor (IC2)",
                "category": "magnetic",
                "value": None,
                "unit": "N/A",
                "valid": False,
                "mounted": False,
                "status": "Not Installed",
                "reason": "Not physically installed on EDU_ROBO board",
                "pin": "36 (X1)",
            },
            {
                "id": "moc7811",
                "name": "Optical Slot Interrupter",
                "category": "motion",
                "value": latest.get("slot"),
                "unit": "state (0=open, 1=blocked)",
                "valid": latest.get("has_data", False),
                "mounted": True,
                "pin": 34,
            },
            {
                "id": "hcsr04",
                "name": "Ultrasonic Distance",
                "category": "ranging",
                "value": latest.get("dist"),
                "unit": "cm",
                "valid": latest.get("has_data", False) and latest.get("dist", 0) > 0,
                "mounted": True,
                "pin": "25/26",
            },
            {
                "id": "touch",
                "name": "Touch Sensor",
                "category": "input",
                "value": None,
                "unit": "binary",
                "valid": False,
                "mounted": False,
                "pin": 18,
                "status": "UNMOUNTED",
            },
            {
                "id": "vibration",
                "name": "Vibration Sensor",
                "category": "mechanical",
                "value": None,
                "unit": "binary",
                "valid": False,
                "mounted": False,
                "pin": 23,
                "status": "UNMOUNTED",
            },
            {
                "id": "sound",
                "name": "Sound Sensor",
                "category": "acoustic",
                "value": None,
                "unit": "binary",
                "valid": False,
                "mounted": False,
                "pin": 32,
                "status": "UNMOUNTED",
            },
            {
                "id": "lm35",
                "name": "LM35 Precision Temperature",
                "category": "environment",
                "value": None,
                "unit": "°C",
                "valid": False,
                "mounted": False,
                "pin": 39,
                "status": "UNMOUNTED",
            },
        ]
        self._send_json({"sensors": sensors, "timestamp": time.time()})

    def _handle_api_commands(self) -> None:
        """Return history of dispatched commands and responses."""
        server = self.server  # type: ignore[attr-defined]
        router: Optional[CommandRouter] = getattr(server, "router", None)
        if not router:
            self._send_json({"history": [], "responses": []})
            return

        self._send_json({
            "history": router.get_history(),
            "responses": router.get_response_history(),
        })

    def _handle_api_services(self) -> None:
        """Return URLs and status of auxiliary monitoring services."""
        grafana_ok = check_port_open("127.0.0.1", 3000)
        influx_ok = check_port_open("127.0.0.1", 8086)
        webui_ok = check_port_open("127.0.0.1", 8080)

        services = [
            {
                "name": "Grafana Dashboard",
                "category": "visualization",
                "url": "http://127.0.0.1:3000",
                "online": grafana_ok,
                "description": "Apollo Mission Control charts and time-series panels",
            },
            {
                "name": "InfluxDB Time-Series UI",
                "category": "database",
                "url": "http://127.0.0.1:8086",
                "online": influx_ok,
                "description": "Raw measurement buckets and Flux query explorer",
            },
            {
                "name": "Open WebUI AI Copilot",
                "category": "ai",
                "url": "http://127.0.0.1:8080",
                "online": webui_ok,
                "description": "Grounded natural language interface with verified tools",
            },
            {
                "name": "Ground Station Logs",
                "category": "diagnostics",
                "url": "http://127.0.0.1:3000/explore",
                "online": grafana_ok,
                "description": "Historical audit trails and incident logs",
            },
        ]
        self._send_json({"services": services})

    def _handle_api_export(self, query: Dict[str, List[str]]) -> None:
        """Export recent telemetry records as JSON or CSV."""
        server = self.server  # type: ignore[attr-defined]
        cache: TelemetryCache = getattr(server, "telemetry_cache")
        fmt = query.get("format", ["json"])[0].lower()
        limit_str = query.get("limit", ["50"])[0]
        try:
            limit = min(500, max(1, int(limit_str)))
        except ValueError:
            limit = 50

        records = cache.get_history(limit=limit)

        if fmt == "csv":
            output = io.StringIO()
            if records:
                canonical = [
                    "received_at", "dev", "seq", "transport", "has_data",
                    "uptime_ms", "free_heap_kb", "temp", "hum", "dht_valid",
                    "ldr", "x0", "x1", "slot", "dist", "heap", "ticks"
                ]
                all_keys = set()
                for r in records:
                    all_keys.update(r.keys())
                fieldnames = [k for k in canonical if k in all_keys] + [k for k in sorted(all_keys) if k not in canonical]
                writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
            csv_data = output.getvalue().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="nexus_telemetry.csv"')
            self.send_header("Content-Length", str(len(csv_data)))
            self.end_headers()
            self.wfile.write(csv_data)
        else:
            self._send_json({"count": len(records), "records": records})

    def _handle_api_diagnostics(self) -> None:
        """Return diagnostic metrics across system subsystems."""
        server = self.server  # type: ignore[attr-defined]
        host_mgr: Optional[NexusHostManager] = getattr(server, "host_manager", None)
        router: Optional[CommandRouter] = getattr(server, "router", None)
        cache: TelemetryCache = getattr(server, "telemetry_cache")

        diag = {
            "uptime_system": time.time(),
            "host_manager": host_mgr.get_stats().to_dict() if host_mgr and hasattr(host_mgr.get_stats(), "to_dict") else {},
            "router_stats": vars(router.stats) if router and hasattr(router, "stats") else {},
            "latest_telemetry": cache.get_latest(),
            "services": {
                "influxdb_port_8086": check_port_open("127.0.0.1", 8086),
                "grafana_port_3000": check_port_open("127.0.0.1", 3000),
                "webui_port_8080": check_port_open("127.0.0.1", 8080),
                "mosquitto_port_1883": check_port_open("127.0.0.1", 1883),
            },
        }
        self._send_json(diag)

    def _handle_api_incidents(self) -> None:
        """Return active incidents, event dictionaries, and runtime discovery metadata."""
        server = self.server  # type: ignore[attr-defined]
        cache: TelemetryCache = getattr(server, "telemetry_cache")
        router: Optional[CommandRouter] = getattr(server, "router", None)
        latest = cache.get_latest()

        active_incidents = []
        now = time.time()

        # Check telemetry health flags
        if latest.get("has_data"):
            if not latest.get("dht_valid", True):
                active_incidents.append({
                    "id": 1,
                    "type": "FAULT",
                    "code": 1,
                    "name": "DHT11 Checksum Error",
                    "severity": "WARNING",
                    "source": "dht11",
                    "details": "DHT11 sensor reading reported dht_valid=false (checksum or timing failure)",
                    "timestamp": latest.get("received_at", now),
                    "acknowledged": False,
                })
            latest_age = now - latest.get("received_at", now) if latest.get("received_at") else 0
            if latest_age > 6.0:
                active_incidents.append({
                    "id": 2,
                    "type": "WARNING",
                    "code": 2,
                    "name": "Telemetry Ingestion Stale",
                    "severity": "WARNING",
                    "source": "transport",
                    "details": f"Latest telemetry packet is {latest_age:.1f}s old (expected 2.0s cadence)",
                    "timestamp": latest.get("received_at", now),
                    "acknowledged": False,
                })
            dist = latest.get("dist")
            if dist is not None and (dist < 2.0 or dist > 400.0):
                active_incidents.append({
                    "id": 3,
                    "type": "WARNING",
                    "code": 3,
                    "name": "Ultrasonic Reading Out of Range",
                    "severity": "INFO",
                    "source": "hcsr04",
                    "details": f"HC-SR04 reading ({dist} cm) outside valid range 2.0 - 400.0 cm",
                    "timestamp": latest.get("received_at", now),
                    "acknowledged": False,
                })

        firmware_event_types = [
            {"id": 1, "code": "0x01", "name": "SYSTEM_BOOT", "severity": "INFO", "source": "firmware", "description": "System executive booted and initialized"},
            {"id": 2, "code": "0x02", "name": "JOB_STARTED", "severity": "DEBUG", "source": "executive", "description": "Executive job dispatched to ready state"},
            {"id": 3, "code": "0x03", "name": "JOB_COMPLETED", "severity": "DEBUG", "source": "executive", "description": "Executive job execution completed successfully"},
            {"id": 4, "code": "0x04", "name": "JOB_FAILED", "severity": "ERROR", "source": "executive", "description": "Executive job callback returned false/failure"},
            {"id": 5, "code": "0x05", "name": "DEADLINE_MISS", "severity": "WARN", "source": "executive", "description": "Job execution exceeded allocated deadline_ms budget"},
            {"id": 6, "code": "0x06", "name": "QUEUE_OVERFLOW", "severity": "WARN", "source": "executive", "description": "Ready queue capacity (16) or event queue (32) overflowed"},
            {"id": 7, "code": "0x07", "name": "FAULT_LATCHED", "severity": "ERROR", "source": "executive", "description": "Subsystem fault latched in executive state"},
            {"id": 8, "code": "0x08", "name": "FAULT_CLEARED", "severity": "INFO", "source": "executive", "description": "Fault cleared via CLEAR FAULTS command"},
            {"id": 9, "code": "0x09", "name": "SENSOR_SAMPLE", "severity": "DEBUG", "source": "sensors", "description": "Periodic sensor sampling frame recorded"},
            {"id": 10, "code": "0x0A", "name": "COMMAND_RECEIVED", "severity": "INFO", "source": "dispatcher", "description": "Command envelope received across active transport"},
            {"id": 11, "code": "0x0B", "name": "COMMAND_COMPLETED", "severity": "INFO", "source": "dispatcher", "description": "Command dispatch and execution finished"},
        ]

        monitoring_rules = [
            {"rule_id": "dht_sensor_invalid", "name": "DHT Sensor Invalid Readings", "severity": "WARNING", "condition": "dht_valid=false in >=3 samples over 15m window"},
            {"rule_id": "stale_telemetry", "name": "Telemetry Freshness Loss", "severity": "WARNING", "condition": "Host arrival age > cadence * grace_factor (6.0s for telem)"},
            {"rule_id": "executive_task_failure", "name": "Cyclic Executive Task Failure", "severity": "CRITICAL", "condition": "Monotonic jobs_failed counter increases (failed_delta > 0)"},
            {"rule_id": "device_reboot", "name": "Unplanned Device Reboot", "severity": "INFO", "condition": "ESP32 monotonic uptime drops or seq resets"},
        ]

        self._send_json({
            "status": "ok",
            "active_incidents": active_incidents,
            "total_active": len(active_incidents),
            "firmware_event_types": firmware_event_types,
            "monitoring_rules": monitoring_rules,
            "discovery_workflow": {
                "step_1": "Query GET /api/incidents or inspect telemetry badges to discover active entity ID (fault_id, warning_id, or event_id).",
                "step_2": "Submit command: POST /api/command with verb='ACKNOWLEDGE', noun='FAULT'|'WARNING'|'EVENT', params={'fault_id': <id>}.",
                "step_3": "Verify response status: ok, code: 0, ack: true.",
                "step_4": "Note: Acknowledgement records that the operator acknowledged the alert. To reset cumulative error counters on firmware, submit 'CLEAR FAULTS'.",
            },
            "timestamp": now,
        })

    def _handle_api_command(self) -> None:
        """Handle command execution request with safety checks and correlation."""
        server = self.server  # type: ignore[attr-defined]
        router: Optional[CommandRouter] = getattr(server, "router", None)

        if not router:
            self._send_json(
                {"status": "failed", "code": int(StatusCode.INTERNAL_ERROR), "msg": "Command router not initialized"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0 or content_length > 8192:
                self._send_json(
                    {"status": "rejected", "code": int(StatusCode.REJECTED), "msg": "Payload empty or exceeds size limit"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body)
        except Exception as err:
            self._send_json(
                {"status": "rejected", "code": int(StatusCode.REJECTED), "msg": f"Invalid JSON payload: {err}"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        verb = body.get("verb")
        noun = body.get("noun")
        params = body.get("params", {})
        confirmed = bool(body.get("confirmed", False))
        transport = str(body.get("transport", "auto"))
        timeout_sec = float(body.get("timeout", 3.0))

        if not verb or not noun:
            self._send_json(
                {"status": "rejected", "code": int(StatusCode.REJECTED), "msg": "Fields 'verb' and 'noun' are required"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        # Execute command via router
        res = router.dispatch_command(
            verb=str(verb),
            noun=str(noun),
            params=params,
            confirmed=confirmed,
            timeout_sec=timeout_sec,
            transport=transport,
            source="web_console",
        )

        self._send_json(res)


class NexusGroundStationServer:
    """Ground Station HTTP Server runner."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        host_manager: Optional[NexusHostManager] = None,
        router: Optional[CommandRouter] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.host_manager = host_manager
        self.router = router
        self.telemetry_cache = TelemetryCache()

        if self.host_manager:
            self.host_manager.register_consumer(self.telemetry_cache.update)

        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def start(self) -> None:
        """Start the background HTTP server."""
        if self._is_running:
            return

        server_address = (self.host, self.port)
        self._httpd = ThreadingHTTPServer(server_address, NexusRequestHandler)
        self.port = self._httpd.server_port
        # Attach references to server instance for handler access
        self._httpd.host_manager = self.host_manager  # type: ignore[attr-defined]
        self._httpd.router = self.router  # type: ignore[attr-defined]
        self._httpd.telemetry_cache = self.telemetry_cache  # type: ignore[attr-defined]

        self._is_running = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="NexusGroundStationHTTPServer",
            daemon=True,
        )
        self._thread.start()
        logger.info("NEXUS Ground Station web server started on http://%s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the HTTP server cleanly."""
        if not self._is_running:
            return
        self._is_running = False
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("NEXUS Ground Station web server stopped")
