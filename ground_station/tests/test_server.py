"""Unit and integration tests for NexusGroundStationServer.

Validates:
  1. Static web asset delivery (HTML, CSS, JS).
  2. REST API endpoints (/api/status, /api/registry, /api/telemetry/latest, /api/sensors, etc.).
  3. POST /api/command dispatch handling, input validation, and safety confirmation checks.
  4. Telemetry export formats (JSON & CSV).
"""

import json
import urllib.request
import urllib.error
from typing import Generator
import pytest

from ground_station.command_router.command_registry import CommandRegistry, StatusCode
from ground_station.command_router.router import CommandRouter
from ground_station.connection_manager.nexus_host_manager import NexusHostManager
from ground_station.server import NexusGroundStationServer, TelemetryCache


@pytest.fixture
def test_server() -> Generator[tuple[NexusGroundStationServer, str], None, None]:
    """Start an ephemeral test instance of NexusGroundStationServer."""
    host_mgr = NexusHostManager(queue_capacity=50)
    router = CommandRouter(host_manager=host_mgr, dev_id="nexus_esp32")
    server = NexusGroundStationServer(host="127.0.0.1", port=0, host_manager=host_mgr, router=router)
    
    # Pre-populate some telemetry in cache
    server.telemetry_cache.update({
        "received_at": 1000.0,
        "seq": 42,
        "has_data": True,
        "temp": 24.2,
        "hum": 55.0,
        "dht_valid": True,
        "ldr": 1800,
        "x0": 340,
        "x1": 2048,
        "slot": 0,
        "dist": 15.4,
    })

    server.start()
    actual_port = server.port
    base_url = f"http://127.0.0.1:{actual_port}"

    yield server, base_url

    server.stop()


def test_serve_static_index(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "MISSION CONTROL" in content
        assert "NEXUS" in content
        assert "EDU_ROBO V14" in content


def test_serve_static_assets(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    # CSS
    with urllib.request.urlopen(f"{base_url}/styles.css", timeout=2.0) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/css" in content_type

    # JS
    with urllib.request.urlopen(f"{base_url}/app.js", timeout=2.0) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "javascript" in content_type


def test_api_status(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    with urllib.request.urlopen(f"{base_url}/api/status", timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "connected" in data
        assert "active_transport" in data
        assert "capabilities" in data
        assert "services" in data
        assert len(data["capabilities"]["mounted"]) >= 7
        assert len(data["capabilities"]["unmounted"]) >= 6


def test_api_registry(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    with urllib.request.urlopen(f"{base_url}/api/registry", timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["total_commands"] == 115
        assert len(data["verbs"]) == 23
        assert "GET" in data["catalog"]
        assert "STATUS" in data["catalog"]["GET"]


def test_api_telemetry_latest(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    with urllib.request.urlopen(f"{base_url}/api/telemetry/latest", timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("has_data") is True
        assert data.get("temp") == 24.2
        assert data.get("hum") == 55.0
        assert data.get("ldr") == 1800


def test_api_sensors(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    with urllib.request.urlopen(f"{base_url}/api/sensors", timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "sensors" in data
        sensor_ids = [s["id"] for s in data["sensors"]]
        assert "dht11_temp" in sensor_ids
        assert "ldr" in sensor_ids
        assert "touch" in sensor_ids  # Truthful unmounted


def test_api_services(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    with urllib.request.urlopen(f"{base_url}/api/services", timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "services" in data
        names = [s["name"] for s in data["services"]]
        assert any("Grafana" in n for n in names)
        assert any("InfluxDB" in n for n in names)


def test_api_export_json_and_csv(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    # JSON export
    with urllib.request.urlopen(f"{base_url}/api/export?format=json", timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "records" in data
        assert len(data["records"]) >= 1

    # CSV export
    with urllib.request.urlopen(f"{base_url}/api/export?format=csv", timeout=2.0) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "temp" in content or "received_at" in content


def test_api_command_hazardous_requires_confirmation(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    # RESET FAULTS is a hazardous command requiring confirmation
    payload = json.dumps({
        "verb": "RESET",
        "noun": "FAULTS",
        "confirmed": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/command",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["status"] == "rejected"
        assert res["code"] == int(StatusCode.CONFIRMATION_REQUIRED)
        assert "confirmation" in res["msg"].lower()


def test_api_command_local_dispatch(test_server: tuple[NexusGroundStationServer, str]) -> None:
    _, base_url = test_server
    # OPEN DASHBOARD is handled locally on ground station
    payload = json.dumps({
        "verb": "OPEN",
        "noun": "DASHBOARD",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/command",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["code"] in (int(StatusCode.OK), int(StatusCode.TARGET_UNREACHABLE))
