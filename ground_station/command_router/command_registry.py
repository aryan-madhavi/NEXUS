"""Canonical NEXUS Command Registry.

Defines the authoritative vocabulary, numeric codes, stable IDs, parameter constraints,
and milestone dispositions for all NEXUS commands.
Maintains exact 1-to-1 parity with firmware/main/command/nexus_command_registry.h/.c.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


class CommandDisposition(enum.Enum):
    """Milestone disposition for candidate commands."""

    REQUIRED_M8 = "REQUIRED_M8"
    EXISTING_CAPABILITY = "EXISTING_CAPABILITY"
    DEFERRED_M9_M10 = "DEFERRED_M9_M10"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_REQUIRED = "NOT_REQUIRED"


class CommandDestination(enum.Enum):
    """Target subsystem executing the command."""

    FIRMWARE = "firmware"
    GROUND_STATION = "ground_station"
    TEST_HARNESS = "test_harness"


class StatusCode(enum.IntEnum):
    """Command response status codes matching firmware."""

    OK = 0
    REJECTED = 1
    UNKNOWN_CMD = 2
    UNSUPPORTED = 3
    FAILED = 4
    DUPLICATE = 5


# Verb Codes
VERB_CODES: Dict[str, int] = {
    "NOP": 0x00,
    "INITIALIZE": 0x01,
    "START": 0x02,
    "STOP": 0x03,
    "RESET": 0x04,
    "SET": 0x05,
    "GET": 0x06,
    "DISPLAY": 0x10,
    "HISTORY": 0x11,
    "DIAGNOSTICS": 0x18,
    "OPEN": 0x1E,
    "ASK": 0x1F,
    "EXPORT": 0x20,
    "RUN": 0x21,
}

# Noun Codes by context
NOUN_CODES: Dict[Tuple[str, str], int] = {
    ("NOP", "NONE"): 0x00,
    ("INITIALIZE", "SYSTEM"): 0x01,
    ("INITIALIZE", "SENSORS"): 0x02,
    ("INITIALIZE", "TRANSPORTS"): 0x03,
    ("START", "SYSTEM"): 0x01,
    ("START", "SENSORS"): 0x02,
    ("START", "TELEMETRY"): 0x03,
    ("START", "SELF_TEST"): 0x04,
    ("STOP", "SENSORS"): 0x02,
    ("STOP", "TELEMETRY"): 0x03,
    ("RESET", "FAULTS"): 0x01,
    ("RESET", "STATISTICS"): 0x02,
    ("SET", "PRIORITY"): 0x01,
    ("SET", "SAMPLE_INTERVAL"): 0x02,
    ("SET", "THRESHOLD"): 0x03,
    ("GET", "STATUS"): 0x01,
    ("GET", "CONFIGURATION"): 0x02,
    ("GET", "SENSOR_LIST"): 0x03,
    ("GET", "TIME"): 0x04,
    ("DISPLAY", "STATUS"): 0x01,
    ("DISPLAY", "EXECUTIVE"): 0x02,
    ("DISPLAY", "QUEUES"): 0x03,
    ("DISPLAY", "FAULTS"): 0x04,
    ("DISPLAY", "ENVIRONMENT"): 0x41,
    ("DISPLAY", "LIGHT"): 0x42,
    ("DISPLAY", "DISTANCE"): 0x43,
    ("DISPLAY", "ANALOG"): 0x44,
    ("DISPLAY", "MOTION"): 0x45,
    ("DISPLAY", "EVENTS"): 0x46,
    ("HISTORY", "EVENTS"): 0x01,
    ("HISTORY", "FAULTS"): 0x02,
    ("HISTORY", "EXECUTIVE"): 0x03,
    ("HISTORY", "ENVIRONMENT"): 0x41,
    ("HISTORY", "SENSORS"): 0x42,
    ("DIAGNOSTICS", "SYSTEM"): 0x01,
    ("DIAGNOSTICS", "SENSORS"): 0x02,
    ("DIAGNOSTICS", "QUEUES"): 0x03,
    ("DIAGNOSTICS", "TIMING"): 0x04,
    ("DIAGNOSTICS", "MEMORY"): 0x05,
    ("DIAGNOSTICS", "TRANSPORTS"): 0x06,
    ("OPEN", "DASHBOARD"): 0x01,
    ("OPEN", "LOGS"): 0x02,
    ("OPEN", "AI"): 0x03,
    ("OPEN", "GROUND"): 0x04,
    ("ASK", "SYSTEM"): 0x01,
    ("ASK", "ENVIRONMENT"): 0x41,
    ("ASK", "SENSOR"): 0x42,
    ("EXPORT", "TELEMETRY"): 0x01,
    ("EXPORT", "DIAGNOSTICS"): 0x02,
    ("RUN", "SELF_TEST"): 0x01,
    ("RUN", "SENSOR_TEST"): 0x02,
    ("RUN", "STRESS_TEST"): 0x03,
}


def make_cmd_id(verb: str, noun: str) -> int:
    """Generate unique 16-bit command ID: (verb_code << 8) | noun_code."""
    v_code = VERB_CODES[verb]
    n_code = NOUN_CODES[(verb, noun)]
    return (v_code << 8) | n_code


@dataclass(frozen=True)
class CommandRegistryEntry:
    """Immutable entry in the canonical NEXUS command matrix."""

    cmd_id: int
    verb: str
    noun: str
    verb_code: int
    noun_code: int
    disposition: CommandDisposition
    destination: CommandDestination
    is_supported_m8: bool
    description: str


class CommandRegistry:
    """Authoritative Command Registry holding all candidate and supported commands."""

    _ENTRIES: List[CommandRegistryEntry] = [
        # 00 NOP
        CommandRegistryEntry(
            cmd_id=make_cmd_id("NOP", "NONE"),
            verb="NOP",
            noun="NONE",
            verb_code=VERB_CODES["NOP"],
            noun_code=NOUN_CODES[("NOP", "NONE")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Parser and protocol loopback test",
        ),
        # 01 INITIALIZE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("INITIALIZE", "SYSTEM"),
            verb="INITIALIZE",
            noun="SYSTEM",
            verb_code=VERB_CODES["INITIALIZE"],
            noun_code=NOUN_CODES[("INITIALIZE", "SYSTEM")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Re-initialization of running system services is unsupported without reboot",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("INITIALIZE", "SENSORS"),
            verb="INITIALIZE",
            noun="SENSORS",
            verb_code=VERB_CODES["INITIALIZE"],
            noun_code=NOUN_CODES[("INITIALIZE", "SENSORS")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Dynamic re-initialization of sensor peripherals is unsupported at runtime",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("INITIALIZE", "TRANSPORTS"),
            verb="INITIALIZE",
            noun="TRANSPORTS",
            verb_code=VERB_CODES["INITIALIZE"],
            noun_code=NOUN_CODES[("INITIALIZE", "TRANSPORTS")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Transport re-initialization without clean teardown is unsupported",
        ),
        # 02 START
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "SYSTEM"),
            verb="START",
            noun="SYSTEM",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "SYSTEM")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="System executive is started automatically at boot",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "SENSORS"),
            verb="START",
            noun="SENSORS",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "SENSORS")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Sensor acquisition jobs are started deterministically at boot",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "TELEMETRY"),
            verb="START",
            noun="TELEMETRY",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "TELEMETRY")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Telemetry broadcast is enabled automatically at boot",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "SELF_TEST"),
            verb="START",
            noun="SELF_TEST",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "SELF_TEST")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Run bounded executive and data-structure self-test",
        ),
        # 03 STOP
        CommandRegistryEntry(
            cmd_id=make_cmd_id("STOP", "SENSORS"),
            verb="STOP",
            noun="SENSORS",
            verb_code=VERB_CODES["STOP"],
            noun_code=NOUN_CODES[("STOP", "SENSORS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Halting scheduled sensor acquisitions is deferred to M9/M10",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("STOP", "TELEMETRY"),
            verb="STOP",
            noun="TELEMETRY",
            verb_code=VERB_CODES["STOP"],
            noun_code=NOUN_CODES[("STOP", "TELEMETRY")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Halting core telemetry transmission remotely is deferred to M9/M10",
        ),
        # 04 RESET
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RESET", "FAULTS"),
            verb="RESET",
            noun="FAULTS",
            verb_code=VERB_CODES["RESET"],
            noun_code=NOUN_CODES[("RESET", "FAULTS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Clearing latched hardware faults requires dedicated fault manager (M9/M10)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RESET", "STATISTICS"),
            verb="RESET",
            noun="STATISTICS",
            verb_code=VERB_CODES["RESET"],
            noun_code=NOUN_CODES[("RESET", "STATISTICS")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Resetting diagnostic counters destabilizes host metrics monitoring; unsupported",
        ),
        # 05 SET
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "PRIORITY"),
            verb="SET",
            noun="PRIORITY",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "PRIORITY")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Modifying job priorities at runtime alters deterministic scheduling guarantees",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "SAMPLE_INTERVAL"),
            verb="SET",
            noun="SAMPLE_INTERVAL",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "SAMPLE_INTERVAL")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Modifying sample intervals at runtime is not supported by current executive",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "THRESHOLD"),
            verb="SET",
            noun="THRESHOLD",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "THRESHOLD")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Threshold monitoring is handled host-side in Ground Station monitoring engine",
        ),
        # 06 GET
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "STATUS"),
            verb="GET",
            noun="STATUS",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "STATUS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Retrieve system state, uptime, free heap, and connection state",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "CONFIGURATION"),
            verb="GET",
            noun="CONFIGURATION",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "CONFIGURATION")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Retrieve protocol version, device identity, and routing defaults",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "SENSOR_LIST"),
            verb="GET",
            noun="SENSOR_LIST",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "SENSOR_LIST")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Retrieve registered present sensor drivers",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "TIME"),
            verb="GET",
            noun="TIME",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "TIME")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Retrieve monotonic uptime in milliseconds and microseconds",
        ),
        # 16 DISPLAY
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "STATUS"),
            verb="DISPLAY",
            noun="STATUS",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "STATUS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display overall device operational status summary",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "EXECUTIVE"),
            verb="DISPLAY",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "EXECUTIVE")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display executive dispatch metrics and latency",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "QUEUES"),
            verb="DISPLAY",
            noun="QUEUES",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "QUEUES")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display ready queue, event queue, and tx queue depths",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "FAULTS"),
            verb="DISPLAY",
            noun="FAULTS",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "FAULTS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display active sensor error counts and executive failures",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "ENVIRONMENT"),
            verb="DISPLAY",
            noun="ENVIRONMENT",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "ENVIRONMENT")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display latest DHT11 temperature, humidity, and validity",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "LIGHT"),
            verb="DISPLAY",
            noun="LIGHT",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "LIGHT")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display latest calibrated LDR light reading",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "DISTANCE"),
            verb="DISPLAY",
            noun="DISTANCE",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "DISTANCE")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="HC-SR04 distance sensor is not yet connected; deferred to M9",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "ANALOG"),
            verb="DISPLAY",
            noun="ANALOG",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "ANALOG")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display raw analog readings from CD4051 channel X0",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "MOTION"),
            verb="DISPLAY",
            noun="MOTION",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "MOTION")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Motion sensor hardware is not installed; deferred to M9",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "EVENTS"),
            verb="DISPLAY",
            noun="EVENTS",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "EVENTS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Display recent system and executive event details",
        ),
        # 17 HISTORY
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "EVENTS"),
            verb="HISTORY",
            noun="EVENTS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "EVENTS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Bounded firmware event history query deferred to M9/M10 (use host incidents.db)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "FAULTS"),
            verb="HISTORY",
            noun="FAULTS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "FAULTS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Firmware fault history query deferred to M9/M10 (use host incidents.db)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "EXECUTIVE"),
            verb="HISTORY",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "EXECUTIVE")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Scheduler history query deferred to M9/M10",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "ENVIRONMENT"),
            verb="HISTORY",
            noun="ENVIRONMENT",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "ENVIRONMENT")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Environmental history is persisted host-side in InfluxDB (query via Ground Station)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "SENSORS"),
            verb="HISTORY",
            noun="SENSORS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "SENSORS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            description="Per-sensor history is persisted host-side in InfluxDB (query via Ground Station)",
        ),
        # 24 DIAGNOSTICS
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "SYSTEM"),
            verb="DIAGNOSTICS",
            noun="SYSTEM",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "SYSTEM")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Detailed system health diagnostics: uptime, heap, reset reason, ticks",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "SENSORS"),
            verb="DIAGNOSTICS",
            noun="SENSORS",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "SENSORS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Sensor driver error counts, read counts, and freshness metrics",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "QUEUES"),
            verb="DIAGNOSTICS",
            noun="QUEUES",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "QUEUES")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Queue depths, high-water marks, and overflow statistics",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "TIMING"),
            verb="DIAGNOSTICS",
            noun="TIMING",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "TIMING")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Executive dispatch latency, execution duration, and deadline metrics",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "MEMORY"),
            verb="DIAGNOSTICS",
            noun="MEMORY",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "MEMORY")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Free heap, minimum free heap watermark, and allocation health",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "TRANSPORTS"),
            verb="DIAGNOSTICS",
            noun="TRANSPORTS",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "TRANSPORTS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Serial and MQTT transport connection states, packets, and error counts",
        ),
        # 30 OPEN
        CommandRegistryEntry(
            cmd_id=make_cmd_id("OPEN", "DASHBOARD"),
            verb="OPEN",
            noun="DASHBOARD",
            verb_code=VERB_CODES["OPEN"],
            noun_code=NOUN_CODES[("OPEN", "DASHBOARD")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=True,
            description="Laptop Ground Station opens Grafana dashboard",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("OPEN", "LOGS"),
            verb="OPEN",
            noun="LOGS",
            verb_code=VERB_CODES["OPEN"],
            noun_code=NOUN_CODES[("OPEN", "LOGS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=True,
            description="Laptop Ground Station opens structured log viewer",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("OPEN", "AI"),
            verb="OPEN",
            noun="AI",
            verb_code=VERB_CODES["OPEN"],
            noun_code=NOUN_CODES[("OPEN", "AI")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=True,
            description="Laptop Ground Station opens Open WebUI AI interface",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("OPEN", "GROUND"),
            verb="OPEN",
            noun="GROUND",
            verb_code=VERB_CODES["OPEN"],
            noun_code=NOUN_CODES[("OPEN", "GROUND")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=True,
            description="Laptop Ground Station opens ground-station overview",
        ),
        # 31 ASK
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ASK", "SYSTEM"),
            verb="ASK",
            noun="SYSTEM",
            verb_code=VERB_CODES["ASK"],
            noun_code=NOUN_CODES[("ASK", "SYSTEM")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            description="Open AI with system context; deferred to M9/M10",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ASK", "ENVIRONMENT"),
            verb="ASK",
            noun="ENVIRONMENT",
            verb_code=VERB_CODES["ASK"],
            noun_code=NOUN_CODES[("ASK", "ENVIRONMENT")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            description="Open AI with environmental context; deferred to M9/M10",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ASK", "SENSOR"),
            verb="ASK",
            noun="SENSOR",
            verb_code=VERB_CODES["ASK"],
            noun_code=NOUN_CODES[("ASK", "SENSOR")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            description="Open AI with selected sensor context; deferred to M9/M10",
        ),
        # 32 EXPORT
        CommandRegistryEntry(
            cmd_id=make_cmd_id("EXPORT", "TELEMETRY"),
            verb="EXPORT",
            noun="TELEMETRY",
            verb_code=VERB_CODES["EXPORT"],
            noun_code=NOUN_CODES[("EXPORT", "TELEMETRY")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            description="Bounded telemetry export job deferred to M9/M10 (supported via host analysis)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("EXPORT", "DIAGNOSTICS"),
            verb="EXPORT",
            noun="DIAGNOSTICS",
            verb_code=VERB_CODES["EXPORT"],
            noun_code=NOUN_CODES[("EXPORT", "DIAGNOSTICS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            description="Diagnostic report generation deferred to M9/M10 (supported via host analysis)",
        ),
        # 33 RUN
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RUN", "SELF_TEST"),
            verb="RUN",
            noun="SELF_TEST",
            verb_code=VERB_CODES["RUN"],
            noun_code=NOUN_CODES[("RUN", "SELF_TEST")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Execute bounded executive and bounded data structures self-test",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RUN", "SENSOR_TEST"),
            verb="RUN",
            noun="SENSOR_TEST",
            verb_code=VERB_CODES["RUN"],
            noun_code=NOUN_CODES[("RUN", "SENSOR_TEST")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            description="Execute physical sensor driver validity and presence self-test",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RUN", "STRESS_TEST"),
            verb="RUN",
            noun="STRESS_TEST",
            verb_code=VERB_CODES["RUN"],
            noun_code=NOUN_CODES[("RUN", "STRESS_TEST")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.TEST_HARNESS,
            is_supported_m8=False,
            description="Stress test is restricted to controlled host test harness builds only",
        ),
    ]

    _BY_ID: Dict[int, CommandRegistryEntry] = {e.cmd_id: e for e in _ENTRIES}
    _BY_NAME: Dict[Tuple[str, str], CommandRegistryEntry] = {
        (e.verb.upper(), e.noun.upper()): e for e in _ENTRIES
    }

    @classmethod
    def get_all(cls) -> List[CommandRegistryEntry]:
        """Return all candidate commands."""
        return list(cls._ENTRIES)

    @classmethod
    def lookup_by_id(cls, cmd_id: int) -> Optional[CommandRegistryEntry]:
        """Look up command entry by 16-bit command ID."""
        return cls._BY_ID.get(cmd_id)

    @classmethod
    def lookup_by_name(cls, verb: str, noun: str) -> Optional[CommandRegistryEntry]:
        """Look up command entry by verb and noun strings (case-insensitive)."""
        return cls._BY_NAME.get((verb.strip().upper(), noun.strip().upper()))

    @classmethod
    def is_supported_m8(cls, cmd_id: int) -> bool:
        """Check if command ID is implemented and supported in Milestone 8."""
        entry = cls.lookup_by_id(cmd_id)
        return entry.is_supported_m8 if entry else False

    @classmethod
    def build_envelope(
        cls,
        cmd_id: int,
        seq: int,
        dev: str = "nexus_esp32",
        uptime_ms: Optional[int] = None,
        extra_fields: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Construct a validated Protocol v1 command dictionary."""
        entry = cls.lookup_by_id(cmd_id)
        if not entry:
            raise ValueError(f"Unknown command ID: {cmd_id}")

        env: Dict[str, object] = {
            "ver": 1,
            "dev": dev,
            "seq": seq,
            "type": "cmd",
            "cmd_id": entry.cmd_id,
            "verb": entry.verb,
            "noun": entry.noun,
        }
        if uptime_ms is not None:
            env["uptime"] = uptime_ms
        if extra_fields:
            for k, v in extra_fields.items():
                if k not in env:
                    env[k] = v
        return env
