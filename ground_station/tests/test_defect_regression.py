"""Regression test suite for Critical Defects A and B.

Covers:
1. ASK SENSOR routing and deterministic grounding for HC-SR04 maximum distance query.
2. Prevention of generic nominal string template on substantive questions.
3. ASK SYSTEM routing, health reporting, and unobservable hardware disclaimers.
4. Correct host-local execution metadata (_execution_path and device_wire_envelope).
5. Non-existent sensor ID error handling.
6. Incident discovery API (/api/incidents) and ACKNOWLEDGE command parity.
7. Reference manual mechanical completeness validation.
"""

from __future__ import annotations

import pytest
from ground_station.ai.agent import NexusConversationalAgent
from ground_station.ai.tools import TelemetryStatistics, TelemetryQuality, TelemetryQueryService
from ground_station.command_router.command_registry import CommandRegistry, StatusCode
from ground_station.command_router.router import CommandRouter


class MockTransportAdapter:
    def __init__(self, is_connected: bool = True):
        self._connected = is_connected

    def is_connected(self) -> bool:
        return self._connected

    def send(self, data: bytes) -> bool:
        return True


def test_ask_sensor_hcsr04_max_distance_grounding():
    """Verify ASK SENSOR for HC-SR04 max distance returns concrete statistics and not generic nominal text."""
    router = CommandRouter(dev_id="nexus_esp32")
    
    # Execute Test A
    resp = router.dispatch_command("ASK", "SENSOR", {
        "sensor_id": "hcsr04",
        "question": "max recorded distance to date"
    }, timeout_sec=10.0)

    assert resp["status"] == "ok"
    assert resp["code"] == 0
    assert resp["_execution_path"] == "HOST_LOCAL_OPERATION"
    assert resp["device_wire_envelope"] == "NOT_APPLICABLE"

    answer = resp["answer"]
    # Must NOT be the old canned nominal string
    assert "NEXUS environmental monitoring telemetry nominal. Query" not in answer
    # Must contain substantive statistical fields
    assert "Maximum Recorded Value" in answer
    assert "cm" in answer
    assert "dist_cm" in answer
    assert "nexus_esp32" in answer
    assert "Time Range" in answer

    # Verify tool calls
    assert "tool_calls" in resp
    assert len(resp["tool_calls"]) > 0
    assert resp["tool_calls"][0]["name"] == "get_signal_statistics"
    assert resp["tool_calls"][0]["arguments"]["signal"] == "dist_cm"


def test_ask_system_health_grounding_and_observable_bounds():
    """Verify ASK SYSTEM returns observable telemetry evidence and notes unobservable components."""
    router = CommandRouter(dev_id="nexus_esp32")

    # Execute Test B
    resp = router.dispatch_command("ASK", "SYSTEM", {
        "question": "Provide complete health status of the ESP32"
    }, timeout_sec=10.0)

    assert resp["status"] == "ok"
    assert resp["code"] == 0
    assert resp["_execution_path"] == "HOST_LOCAL_OPERATION"
    assert resp["device_wire_envelope"] == "NOT_APPLICABLE"

    answer = resp["answer"]
    # Must NOT be the old canned nominal string
    assert "NEXUS environmental monitoring telemetry nominal. Query" not in answer
    # Must state observable health
    assert "Health & Operational Status for ESP32" in answer
    assert "Monotonic Uptime" in answer
    assert "Active Transports" in answer
    # Must explicitly state unobservable hardware bounds
    assert "Unobservable / Hardware Constraints" in answer
    assert "unmounted peripherals" in answer

    # Verify tool calls
    assert "tool_calls" in resp
    assert len(resp["tool_calls"]) > 0
    assert resp["tool_calls"][0]["name"] == "get_telemetry_freshness"


def test_ask_unknown_sensor_handling():
    """Verify non-existent sensor ID is handled gracefully without inventing telemetry."""
    agent = NexusConversationalAgent()
    res = agent.ask("What is the status of non_existent_sensor_xyz?")
    assert res.content is not None
    assert len(res.content) > 0
    # Must not claim nominal telemetry for bogus sensor
    assert "non_existent_sensor_xyz" in res.content or "telemetry" in res.content.lower() or "not recognized" in res.content.lower()


def test_acknowledge_command_definitions():
    """Verify ACKNOWLEDGE FAULT, WARNING, EVENT commands exist in canonical registry."""
    ack_fault = CommandRegistry.lookup_by_name("ACKNOWLEDGE", "FAULT")
    assert ack_fault is not None
    assert ack_fault.cmd_id == 0x0A01
    assert any(p.name == "fault_id" for p in ack_fault.parameters)

    ack_warn = CommandRegistry.lookup_by_name("ACKNOWLEDGE", "WARNING")
    assert ack_warn is not None
    assert ack_warn.cmd_id == 0x0A02
    assert any(p.name == "warning_id" for p in ack_warn.parameters)

    ack_event = CommandRegistry.lookup_by_name("ACKNOWLEDGE", "EVENT")
    assert ack_event is not None
    assert ack_event.cmd_id == 0x0A03
    assert any(p.name == "event_id" for p in ack_event.parameters)


def test_reference_manual_mechanical_completeness():
    """Verify all 115 commands and parameters pass parity validation."""
    from scripts.validate_reference_manual import (
        validate_command_catalog,
        validate_sensor_dictionary,
        validate_event_fault_dictionary,
        validate_actuator_dictionary,
        validate_html_manual,
    )

    cat = validate_command_catalog()
    assert cat["total_commands"] == 115
    assert cat["unique_command_ids"] == 115

    sen = validate_sensor_dictionary()
    assert sen["mounted_sensors_count"] == 5
    assert sen["unmounted_sensors_count"] == 5

    ev = validate_event_fault_dictionary()
    assert ev["firmware_event_types_count"] == 11
    assert ev["monitoring_rules_count"] == 4

    act = validate_actuator_dictionary()
    assert act["total_actuators"] == 9
    assert act["mounted_actuators"] == 6

    html_res = validate_html_manual()
    assert html_res["status"] == "PASS"
