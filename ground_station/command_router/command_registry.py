"""Canonical NEXUS Command Registry.

Defines the authoritative vocabulary, numeric codes, stable IDs, parameter constraints,
and milestone dispositions for all NEXUS commands.
Maintains exact 1-to-1 parity with firmware/main/command/nexus_command_registry.h/.c.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


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
    """Command response status codes matching firmware and ground station."""

    OK = 0
    REJECTED = 1
    UNKNOWN_CMD = 2
    UNSUPPORTED = 3
    FAILED = 4
    DUPLICATE = 5
    TIMEOUT = 6
    CONFIRMATION_REQUIRED = 7
    TARGET_UNREACHABLE = 8
    INTERNAL_ERROR = 9


# Canonical Verb Codes (20 verbs)
VERB_CODES: Dict[str, int] = {
    "NOP": 0x00,
    "INITIALIZE": 0x01,
    "START": 0x02,
    "STOP": 0x03,
    "RESET": 0x04,
    "SET": 0x05,
    "GET": 0x06,
    "ENABLE": 0x07,
    "DISABLE": 0x08,
    "CALIBRATE": 0x09,
    "ACKNOWLEDGE": 0x0A,
    "CLEAR": 0x0B,
    "TEST": 0x0C,
    "ACTUATE": 0x0D,
    "CAPTURE": 0x0E,
    "PUBLISH": 0x0F,
    "DISPLAY": 0x10,
    "HISTORY": 0x11,
    "DIAGNOSTICS": 0x18,
    "OPEN": 0x1E,
    "ASK": 0x1F,
    "EXPORT": 0x20,
    "RUN": 0x21,
}

# Noun Codes by (verb, noun) context
NOUN_CODES: Dict[Tuple[str, str], int] = {
    # 00 NOP
    ("NOP", "NONE"): 0x00,
    # 01 INITIALIZE
    ("INITIALIZE", "SYSTEM"): 0x01,
    ("INITIALIZE", "SENSORS"): 0x02,
    ("INITIALIZE", "TRANSPORTS"): 0x03,
    ("INITIALIZE", "EXECUTIVE"): 0x04,
    # 02 START
    ("START", "SYSTEM"): 0x01,
    ("START", "SENSORS"): 0x02,
    ("START", "TELEMETRY"): 0x03,
    ("START", "SELF_TEST"): 0x04,
    ("START", "EXECUTIVE"): 0x05,
    # 03 STOP
    ("STOP", "SYSTEM"): 0x01,
    ("STOP", "SENSORS"): 0x02,
    ("STOP", "TELEMETRY"): 0x03,
    ("STOP", "EXECUTIVE"): 0x04,
    # 04 RESET
    ("RESET", "FAULTS"): 0x01,
    ("RESET", "STATISTICS"): 0x02,
    ("RESET", "SENSOR_STATE"): 0x03,
    ("RESET", "QUEUES"): 0x04,
    # 05 SET
    ("SET", "PRIORITY"): 0x01,
    ("SET", "SAMPLE_INTERVAL"): 0x02,
    ("SET", "THRESHOLD"): 0x03,
    ("SET", "SENSOR_ENABLE"): 0x04,
    ("SET", "TRANSPORT_PREFERENCE"): 0x05,
    ("SET", "CONFIGURATION"): 0x06,
    # 06 GET
    ("GET", "STATUS"): 0x01,
    ("GET", "CONFIGURATION"): 0x02,
    ("GET", "SENSOR_LIST"): 0x03,
    ("GET", "TIME"): 0x04,
    ("GET", "VERSION"): 0x05,
    ("GET", "HEALTH"): 0x06,
    ("GET", "CAPABILITIES"): 0x07,
    # 07 ENABLE
    ("ENABLE", "SENSOR"): 0x01,
    ("ENABLE", "TRANSPORT"): 0x02,
    ("ENABLE", "TELEMETRY"): 0x03,
    # 08 DISABLE
    ("DISABLE", "SENSOR"): 0x01,
    ("DISABLE", "TRANSPORT"): 0x02,
    ("DISABLE", "TELEMETRY"): 0x03,
    # 09 CALIBRATE
    ("CALIBRATE", "SENSOR"): 0x01,
    ("CALIBRATE", "ANALOG"): 0x02,
    ("CALIBRATE", "ENVIRONMENT"): 0x03,
    # 10 ACKNOWLEDGE
    ("ACKNOWLEDGE", "FAULT"): 0x01,
    ("ACKNOWLEDGE", "WARNING"): 0x02,
    ("ACKNOWLEDGE", "EVENT"): 0x03,
    # 11 CLEAR
    ("CLEAR", "FAULTS"): 0x01,
    ("CLEAR", "HISTORY"): 0x02,
    ("CLEAR", "STATISTICS"): 0x03,
    # 12 TEST
    ("TEST", "SENSOR"): 0x01,
    ("TEST", "TRANSPORT"): 0x02,
    ("TEST", "EXECUTIVE"): 0x03,
    ("TEST", "PERIPHERAL"): 0x04,
    # 13 ACTUATE
    ("ACTUATE", "RELAY"): 0x01,
    ("ACTUATE", "LED"): 0x02,
    ("ACTUATE", "MOTOR"): 0x03,
    ("ACTUATE", "SERVO"): 0x04,
    ("ACTUATE", "BUZZER"): 0x05,
    ("ACTUATE", "SHIFT_REGISTER"): 0x06,
    # 14 CAPTURE
    ("CAPTURE", "TELEMETRY"): 0x01,
    ("CAPTURE", "SENSOR_SNAPSHOT"): 0x02,
    ("CAPTURE", "EVENT_SNAPSHOT"): 0x03,
    # 15 PUBLISH
    ("PUBLISH", "TELEMETRY"): 0x01,
    ("PUBLISH", "EVENT"): 0x02,
    ("PUBLISH", "STATUS"): 0x03,
    # 16 DISPLAY
    ("DISPLAY", "STATUS"): 0x01,
    ("DISPLAY", "EXECUTIVE"): 0x02,
    ("DISPLAY", "QUEUES"): 0x03,
    ("DISPLAY", "FAULTS"): 0x04,
    ("DISPLAY", "SENSORS"): 0x05,
    ("DISPLAY", "TRANSPORTS"): 0x06,
    ("DISPLAY", "CONFIGURATION"): 0x07,
    ("DISPLAY", "ENVIRONMENT"): 0x41,
    ("DISPLAY", "LIGHT"): 0x42,
    ("DISPLAY", "DISTANCE"): 0x43,
    ("DISPLAY", "ANALOG"): 0x44,
    ("DISPLAY", "MOTION"): 0x45,
    ("DISPLAY", "EVENTS"): 0x46,
    ("DISPLAY", "ACTUATORS"): 0x47,
    ("DISPLAY", "CONNECTIVITY"): 0x48,
    # 17 HISTORY
    ("HISTORY", "EVENTS"): 0x01,
    ("HISTORY", "FAULTS"): 0x02,
    ("HISTORY", "EXECUTIVE"): 0x03,
    ("HISTORY", "SENSORS"): 0x04,
    ("HISTORY", "TRANSPORTS"): 0x05,
    ("HISTORY", "ENVIRONMENT"): 0x41,
    ("HISTORY", "SENSOR_READINGS"): 0x42,
    # 24 DIAGNOSTICS
    ("DIAGNOSTICS", "SYSTEM"): 0x01,
    ("DIAGNOSTICS", "SENSORS"): 0x02,
    ("DIAGNOSTICS", "QUEUES"): 0x03,
    ("DIAGNOSTICS", "TIMING"): 0x04,
    ("DIAGNOSTICS", "MEMORY"): 0x05,
    ("DIAGNOSTICS", "TRANSPORTS"): 0x06,
    ("DIAGNOSTICS", "EXECUTIVE"): 0x07,
    ("DIAGNOSTICS", "PERIPHERALS"): 0x08,
    ("DIAGNOSTICS", "DATABASE"): 0x09,
    ("DIAGNOSTICS", "AI_SERVICE"): 0x0A,
    # 30 OPEN
    ("OPEN", "DASHBOARD"): 0x01,
    ("OPEN", "LOGS"): 0x02,
    ("OPEN", "AI"): 0x03,
    ("OPEN", "GROUND"): 0x04,
    ("OPEN", "DATABASE"): 0x05,
    ("OPEN", "DIAGNOSTICS"): 0x06,
    # 31 ASK
    ("ASK", "SYSTEM"): 0x01,
    ("ASK", "SENSOR"): 0x02,
    ("ASK", "EXECUTIVE"): 0x03,
    ("ASK", "DIAGNOSTICS"): 0x04,
    ("ASK", "ENVIRONMENT"): 0x41,
    # 32 EXPORT
    ("EXPORT", "TELEMETRY"): 0x01,
    ("EXPORT", "DIAGNOSTICS"): 0x02,
    ("EXPORT", "EVENTS"): 0x03,
    ("EXPORT", "FAULTS"): 0x04,
    ("EXPORT", "CONFIGURATION"): 0x05,
    # 33 RUN
    ("RUN", "SELF_TEST"): 0x01,
    ("RUN", "SENSOR_TEST"): 0x02,
    ("RUN", "STRESS_TEST"): 0x03,
    ("RUN", "TRANSPORT_TEST"): 0x04,
    ("RUN", "QUALIFICATION_TEST"): 0x05,
}


def make_cmd_id(verb: str, noun: str) -> int:
    """Generate unique 16-bit command ID: (verb_code << 8) | noun_code."""
    v_code = VERB_CODES[verb.strip().upper()]
    n_code = NOUN_CODES[(verb.strip().upper(), noun.strip().upper())]
    return (v_code << 8) | n_code


# Authoritative individual value mappings for all 27 command parameters
PARAM_VALUE_MAPPINGS: Dict[str, Dict[str, str]] = {
    "event_id": {
        "1": "BOOT_START — System initialization sequence started by FreeRTOS bootloader",
        "2": "BOOT_COMPLETE — All core peripherals, tasks, and queues initialized successfully",
        "3": "HEARTBEAT — Periodic cyclic executive heartbeat pulse (1 Hz)",
        "4": "WIFI_CONNECTED — Station Wi-Fi interface connected and IP address leased",
        "5": "MQTT_CONNECTED — Mosquitto broker connection established and topics subscribed",
        "6": "TELEMETRY_SAMPLE — Periodic sensor acquisition frame sampled by executive",
        "7": "THRESHOLD_EXCEEDED — Monitored sensor signal breached configured high/low setpoint",
        "8": "COMMAND_RECEIVED — Inbound command packet accepted from Serial or MQTT wire",
        "9": "COMMAND_EXECUTED — Command dispatcher executed handler and formatted reply",
        "10": "ERROR_RAISED — Transient error or recoverable exception logged in event queue",
        "11": "WATCHDOG_RESET — Task watchdog timer expired triggering defensive reset",
    },
    "fault_id": {
        "1": "SENSOR_READ_FAIL — I2C/SPI or ADC sensor read timed out or returned invalid checksum",
        "2": "TELEMETRY_OVERFLOW — Telemetry ring buffer capacity exhausted; frames dropped",
        "3": "QUEUE_FULL — Inter-task FreeRTOS message queue full; command dropped",
        "4": "MQTT_DISCONNECT — Broker connection severed or TCP socket keepalive timed out",
        "5": "HEAP_LOW — Available FreeRTOS dynamic heap dropped below safety threshold (16 KB)",
        "6": "WATCHDOG_TIMEOUT — Monitored task failed to feed watchdog timer within deadline",
        "7": "EXECUTIVE_PANIC — Task execution aborted due to unhandled fatal state",
        "8": "HARDWARE_FAULT — Peripheral communication failure (I2C bus arbitration loss or SPI error)",
        "9": "FLASH_WRITE_FAIL — Non-volatile configuration write or NVS commit error",
        "10": "BROWNOUT_DETECTED — Core supply voltage dropped below operational threshold",
        "11": "CALIBRATION_INVALID — Sensor calibration parameters out of valid matrix bounds",
        "12": "CLOCK_SKEW — System RTC or SNTP synchronization loss",
        "13": "COMM_FRAMING_ERR — Frame delimiter or checksum corrupted on incoming transport packet",
        "14": "SECURITY_REJECT — Unauthorized command source or invalid cryptographic token",
        "15": "GENERAL_FAULT — Unspecified system or runtime exception logged in incident manager",
    },
    "warning_id": {
        "1": "TEMP_HIGH — Ambient temperature exceeded warning threshold (default: >45°C)",
        "2": "HUMIDITY_HIGH — Relative humidity exceeded condensation risk threshold (default: >80%)",
        "3": "DISTANCE_LOW — Ultrasonic distance closer than minimum safety margin (default: <10 cm)",
        "4": "LIGHT_LOW — Ambient illumination dropped below minimum operating lux (default: <50 counts)",
        "5": "DEADLINE_MISS — Non-critical cyclic task exceeded scheduled compute window",
        "6": "PACKET_RETRY — Serial or MQTT transport frame retransmission triggered",
        "7": "BUFFER_ALMOST_FULL — Ring buffer reached 80% capacity",
        "8": "BATTERY_LOW — DC power input dropped near dropout threshold",
        "9": "SIGNAL_NOISY — Sensor reading variance exceeded filtering threshold",
        "10": "STALE_SAMPLE — Sensor acquisition did not update within expected cadence",
        "11": "NTP_DRIFT — Local clock drift detected against host reference",
        "12": "THROTTLE_ACTIVE — Command execution throttled due to rate limiting",
        "13": "CONFIG_DEVIATION — Parameter value differs from factory default profile",
        "14": "PEER_UNREACHABLE — Ground station heartbeat packet timed out",
        "15": "GENERAL_WARNING — Informational alert logged in telemetry stream",
    },
    "led_id": {
        "1": "Heartbeat LED (Green, GPIO 27) — Blinks at 1 Hz during normal cyclic execution",
        "2": "Network LED (Blue, GPIO 14) — Illuminates when Wi-Fi and MQTT connections are active",
        "3": "Sensor LED (Yellow, GPIO 12) — Flashes during active sensor bus transactions",
        "4": "Fault LED (Red, GPIO 13) — Latches on when unacknowledged faults or errors occur",
    },
    "sensor_id": {
        "ldr": "Light Dependent Resistor (LDR) — Analog ambient light intensity on CD4051 channel X3",
        "dht11": "DHT11 Digital Sensor — Relative humidity (%) and temperature (°C) on GPIO 25/19",
        "cd4051": "CD4051 Analog Multiplexer — 8:1 analog input bus routed to ESP32 ADC1_CH0",
        "cd4051_x0": "HW-870 Infrared Photodetector (IR-1) — Analog obstacle reflection on CD4051 X0",
        "moc7811": "MOC7811 Slotted Optical Switch — Digital beam status (0=intact, 1=broken) on GPIO 34",
        "hcsr04": "HC-SR04 Ultrasonic Sensor — Distance (cm) via Trigger & Echo transit timing",
        "mux_x0": "HW-870 Infrared Obstacle Reflection (Channel X0 calibration alias)",
        "mux_x1": "Hall Magnetic Sensor IC2 (Channel X1 calibration alias; unmounted PCB footprint)",
    },
    "channel": {
        "0": "Channel X0: HW-870 IR-1 Infrared Obstacle Reflection (GPIO 36 / ADC1_CH0)",
        "1": "Channel X1: Hall Magnetic Sensor IC2 (Unmounted PCB footprint; floating ADC noise ~17 counts)",
        "2": "Channel X2: Sound / Microphone Sensor (Unmounted auxiliary input)",
        "3": "Channel X3: Light Dependent Resistor LDR (Analog Light Intensity)",
        "4": "Channel X4: Auxiliary Analog Expansion 0",
        "5": "Channel X5: Auxiliary Analog Expansion 1",
        "6": "Channel X6: Auxiliary Analog Expansion 2",
        "7": "Channel X7: Auxiliary Analog Expansion 3",
    },
    "state": {
        "on": "Assert logic high (3.3V) — Turn ON / illuminate actuator",
        "off": "Deassert logic low (0.0V) — Turn OFF / extinguish actuator",
    },
    "transport": {
        "auto": "Automatic Failover — Prefers USB Serial if connected, automatically falls back to MQTT",
        "serial": "USB Serial Transport — Dedicated point-to-point /dev/ttyUSB0 link at 115200 baud",
        "mqtt": "MQTT Network Transport — Mosquitto broker at localhost:1883 over topic nexus/cmd",
    },
    "transport_id": {
        "serial": "USB Serial Transport — Dedicated point-to-point /dev/ttyUSB0 link at 115200 baud",
        "mqtt": "MQTT Network Transport — Mosquitto broker at localhost:1883 over topic nexus/cmd",
    },
    "priority": {
        "1": "Priority Class 1 (High) — Critical safety tasks, watchdog monitoring, immediate actuator control",
        "2": "Priority Class 2 (Medium) — Default operational priority for sensor sampling and telemetry",
        "3": "Priority Class 3 (Low) — Background tasks, non-critical telemetry logging, deep maintenance",
    },
    "job_id": {
        "0": "Job 0: Executive Core Supervisor (FreeRTOS scheduler tick & state management)",
        "1": "Job 1: Telemetry Acquisition Engine (cyclic sensor sampling)",
        "2": "Job 2: Serial Transport Processor (UART frame parsing and packet framing)",
        "3": "Job 3: MQTT Network Client (publish telemetry and receive commands)",
        "4": "Job 4: Health & Watchdog Monitor (periodic task checks)",
        "5": "Job 5: Event Queue Dispatcher (event distribution and incident alerts)",
        "6": "Job 6: Actuator Driver Service (LED, Buzzer, and Shift Register control)",
        "7": "Job 7: Diagnostic & Self-Test Routine (periodic loopback checks)",
        "8": "Job 8: Expansion Executive Worker Task 8 (Telemetry post-processing)",
        "9": "Job 9: Expansion Executive Worker Task 9 (Network failover supervision)",
        "10": "Job 10: Expansion Executive Worker Task 10 (Secondary sensor bus management)",
        "11": "Job 11: Expansion Executive Worker Task 11 (Non-volatile storage logging)",
        "12": "Job 12: Expansion Executive Worker Task 12 (Auxiliary peripheral supervisor)",
        "13": "Job 13: Expansion Executive Worker Task 13 (Calibration and offset calculation)",
        "14": "Job 14: Expansion Executive Worker Task 14 (Security audit and frame authentication)",
        "15": "Job 15: Expansion Executive Worker Task 15 (Factory diagnostic loopback)",
    },
    "condition": {
        "gt": "Greater Than (>) — Triggers incident alert when sensor reading strictly exceeds threshold limit",
        "lt": "Less Than (<) — Triggers incident alert when sensor reading strictly drops below threshold limit",
    },
    "signal": {
        "temp": "Ambient Temperature (°C) — Sampled from DHT11 digital sensor (range: 0..50 °C)",
        "hum": "Relative Humidity (%) — Sampled from DHT11 digital sensor (range: 20..90 %)",
        "ldr_raw": "Ambient Light (ADC counts) — Sampled from LDR on CD4051 channel X3 (0..4095)",
        "x0_raw": "Infrared Reflection (ADC counts) — Sampled from HW-870 on CD4051 X0 (0..4095)",
        "x1_raw": "Hall Sensor IC2 (ADC counts) — CD4051 X1 (Unmounted; floating baseline ~17 counts)",
        "dist_cm": "Ultrasonic Distance (cm) — Echo transit from HC-SR04 (range: 2..400 cm)",
    },
    "key": {
        "sample_rate": "Sensor sampling cadence in milliseconds (50..60000 ms)",
        "wifi_ssid": "Configured station Wi-Fi network SSID string",
        "mqtt_broker": "Hostname or IP address of the target Mosquitto MQTT broker",
        "log_level": "Logging verbosity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        "telemetry_interval": "Cyclic telemetry publishing interval in milliseconds (100..60000 ms)",
    },
    "enabled": {
        "true": "Enable sensor acquisition in executive cyclic schedule",
        "false": "Disable sensor acquisition (halts sampling and power consumption)",
    },
    "format": {
        "json": "JavaScript Object Notation — Structured array of telemetry/event objects",
        "csv": "Comma-Separated Values — Tabular format with column headers for spreadsheet import",
    },
    "value": {
        "0": "0x00 — All 8 shift register output pins deasserted (LOW)",
        "1": "0x01 — Output pin Q0 asserted (HIGH)",
        "15": "0x0F — Lower nibble (Q0..Q3) asserted (HIGH)",
        "240": "0xF0 — Upper nibble (Q4..Q7) asserted (HIGH)",
        "255": "0xFF — All 8 shift register output pins asserted (HIGH)",
    },
    "interval_ms": {
        "100": "100 ms (10 Hz) — High-speed diagnostic telemetry streaming",
        "500": "500 ms (2 Hz) — Fast dynamic monitoring",
        "1000": "1000 ms (1 Hz) — Standard nominal operational cadence (default)",
        "5000": "5000 ms (0.2 Hz) — Bandwidth-conserving slow monitoring mode",
        "60000": "60000 ms (0.016 Hz) — Maximum interval (1 sample per minute)",
    },
    "duration_ms": {
        "50": "50 ms — Short audible acknowledgment chirp",
        "100": "100 ms — Standard operational beep (default)",
        "200": "200 ms — Distinct alert notification tone",
        "500": "500 ms — Medium warning buzz",
        "1000..5000": "1000-5000 ms — Extended alarm tone (hard safety cutoff enforced at 5000 ms)",
    },
    "threshold": {
        "-40.0..0.0": "Sub-zero temperature alarm setpoint (°C)",
        "45.0": "Default high temperature warning setpoint (45.0 °C)",
        "80.0": "Default high humidity condensation threshold (80.0 %)",
        "10.0": "Default proximity collision warning margin (10.0 cm)",
        "100..4095": "Raw ADC count threshold for optical/infrared reflections",
    },
    "offset": {
        "-100..-1": "Negative calibration offset count (subtracted from raw reading)",
        "0": "Zero calibration bias (factory default pass-through)",
        "1..100": "Positive calibration offset count (added to raw reading)",
    },
    "temp_offset": {
        "-10..-1": "Negative temperature bias in °C (subtracted from DHT11 reading)",
        "0": "Zero temperature calibration bias (default)",
        "1..10": "Positive temperature bias in °C (added to DHT11 reading)",
    },
    "hum_offset": {
        "-20..-1": "Negative relative humidity bias in % (subtracted from DHT11 reading)",
        "0": "Zero humidity calibration bias (default)",
        "1..20": "Positive relative humidity bias in % (added to DHT11 reading)",
    },
    "event_name": {
        "OPERATOR_CHECKPOINT": "Interactive operator audit milestone marker",
        "TEST_EVENT": "Synthetic test event for validating event queue dispatch",
        "TELEMETRY_ALERT": "High-priority operational event generated by threshold monitor",
    },
    "limit": {
        "10": "10 records — Minimal preview export batch",
        "50": "50 records — Standard export default for events/faults",
        "100": "100 records — Standard export default for telemetry",
        "500..1000": "500-1000 records — Maximum export volume batch",
    },
    "duration_sec": {
        "1..5": "1-5 seconds — Brief CPU/queue stress test (default: 5s)",
        "6..30": "6-30 seconds — Extended stress test (hard safety ceiling enforced at 30s)",
    },
    "question": {
        "Provide complete health status of the ESP32": "Synthesizes packet freshness, uptime, seq #, and transport state",
        "max recorded distance to date": "Queries historical InfluxDB telemetry for all-time peak ultrasonic distance",
        "What is the current executive dispatch load and deadline miss rate?": "Inspects task scheduler performance and execution timing",
        "Analyze current diagnostic logs and identify root cause of any warnings": "Synthesizes active incident logs and hardware diagnostics",
        "Is the ambient temperature and humidity within nominal operating envelope?": "Evaluates live DHT11 readings against environmental safety limits",
    },
}


@dataclass(frozen=True)
class ParameterDefinition:
    """Definition and constraints for a command parameter."""

    name: str
    type_name: str  # "string", "int", "float", "bool", "select"
    required: bool = False
    description: str = ""
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None
    units: Optional[str] = None
    value_semantics: Optional[str] = None
    discovery_workflow: Optional[str] = None
    value_mappings: Optional[Dict[str, str]] = None


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
    is_supported: bool = True
    requires_confirmation: bool = False
    parameters: List[ParameterDefinition] = field(default_factory=list)


def _p(name: str, type_name: str, required: bool = False, description: str = "",
       default: Optional[Any] = None, min_value: Optional[float] = None,
       max_value: Optional[float] = None, options: Optional[List[str]] = None,
       units: Optional[str] = None, value_semantics: Optional[str] = None,
       discovery_workflow: Optional[str] = None,
       value_mappings: Optional[Dict[str, str]] = None) -> ParameterDefinition:
    """Helper to create a ParameterDefinition with automatic default value mappings."""
    if value_mappings is None:
        value_mappings = PARAM_VALUE_MAPPINGS.get(name)
    return ParameterDefinition(
        name=name,
        type_name=type_name,
        required=required,
        description=description,
        default=default,
        min_value=min_value,
        max_value=max_value,
        options=options,
        units=units,
        value_semantics=value_semantics,
        discovery_workflow=discovery_workflow,
        value_mappings=value_mappings,
    )


class CommandRegistry:
    """Authoritative Command Registry holding all 104 candidate and supported commands."""

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
            is_supported=True,
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
            is_supported=False,
            description="Re-initialization of running system requires restart",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("INITIALIZE", "SENSORS"),
            verb="INITIALIZE",
            noun="SENSORS",
            verb_code=VERB_CODES["INITIALIZE"],
            noun_code=NOUN_CODES[("INITIALIZE", "SENSORS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Re-initialize sensor registry and sampling states",
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
            is_supported=False,
            description="Transport re-initialization at runtime requires controlled teardown",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("INITIALIZE", "EXECUTIVE"),
            verb="INITIALIZE",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["INITIALIZE"],
            noun_code=NOUN_CODES[("INITIALIZE", "EXECUTIVE")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=False,
            description="Executive runs deterministically from boot; live re-init is restricted",
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
            is_supported=False,
            description="System executive is already started and running",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "SENSORS"),
            verb="START",
            noun="SENSORS",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "SENSORS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Resume sensor sampling jobs",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "TELEMETRY"),
            verb="START",
            noun="TELEMETRY",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "TELEMETRY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Resume periodic telemetry streaming",
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
            is_supported=True,
            description="Run executive and data structure self-tests",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("START", "EXECUTIVE"),
            verb="START",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["START"],
            noun_code=NOUN_CODES[("START", "EXECUTIVE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Resume executive scheduler if paused",
        ),

        # 03 STOP
        CommandRegistryEntry(
            cmd_id=make_cmd_id("STOP", "SYSTEM"),
            verb="STOP",
            noun="SYSTEM",
            verb_code=VERB_CODES["STOP"],
            noun_code=NOUN_CODES[("STOP", "SYSTEM")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=False,
            description="Stopping core system is prohibited to preserve safety watchdog",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("STOP", "SENSORS"),
            verb="STOP",
            noun="SENSORS",
            verb_code=VERB_CODES["STOP"],
            noun_code=NOUN_CODES[("STOP", "SENSORS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Pause sensor sampling jobs",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("STOP", "TELEMETRY"),
            verb="STOP",
            noun="TELEMETRY",
            verb_code=VERB_CODES["STOP"],
            noun_code=NOUN_CODES[("STOP", "TELEMETRY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Mute periodic telemetry streaming",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("STOP", "EXECUTIVE"),
            verb="STOP",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["STOP"],
            noun_code=NOUN_CODES[("STOP", "EXECUTIVE")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=False,
            description="Stopping executive scheduler is unsupported",
        ),

        # 04 RESET
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RESET", "FAULTS"),
            verb="RESET",
            noun="FAULTS",
            verb_code=VERB_CODES["RESET"],
            noun_code=NOUN_CODES[("RESET", "FAULTS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Clear registered fault counters without rebooting",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RESET", "STATISTICS"),
            verb="RESET",
            noun="STATISTICS",
            verb_code=VERB_CODES["RESET"],
            noun_code=NOUN_CODES[("RESET", "STATISTICS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Reset executive and transport statistical counters",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RESET", "SENSOR_STATE"),
            verb="RESET",
            noun="SENSOR_STATE",
            verb_code=VERB_CODES["RESET"],
            noun_code=NOUN_CODES[("RESET", "SENSOR_STATE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Reset sensor error states and re-arm readings",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RESET", "QUEUES"),
            verb="RESET",
            noun="QUEUES",
            verb_code=VERB_CODES["RESET"],
            noun_code=NOUN_CODES[("RESET", "QUEUES")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Flush non-critical ready and event queue backlogs",
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
            is_supported=False,
            description="Dynamic priority adjustment is unsupported for executive scheduling safety",
            parameters=[
                _p("job_id", "int", required=True, min_value=0, max_value=15, default=1, units="index", value_semantics="JOB_INDEX", description="Executive job index (0-15)", discovery_workflow="Query active jobs via DISPLAY EXECUTIVE"),
                _p("priority", "int", required=True, min_value=1, max_value=3, default=2, options=["1", "2", "3"], units="class", value_semantics="PRIORITY_CLASS", description="Priority class (1=High, 2=Medium, 3=Low)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "SAMPLE_INTERVAL"),
            verb="SET",
            noun="SAMPLE_INTERVAL",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "SAMPLE_INTERVAL")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Configure sampling interval for target sensor",
            parameters=[
                _p("sensor_id", "select", required=True, default="dht11", options=["ldr", "cd4051", "dht11", "moc7811", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Sensor identifier", discovery_workflow="Query mounted sensors via GET /api/sensors"),
                _p("interval_ms", "int", required=True, min_value=50, max_value=60000, default=1000, units="ms", value_semantics="NUMERIC_INTERVAL", description="Sampling interval in ms (50-60000)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "THRESHOLD"),
            verb="SET",
            noun="THRESHOLD",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "THRESHOLD")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Set telemetry alert thresholds",
            parameters=[
                _p("signal", "select", required=True, default="temp", options=["temp", "hum", "ldr_raw", "x0_raw", "x1_raw", "dist_cm"], value_semantics="SIGNAL_ENUM", description="Signal name (temp, hum, ldr_raw, x0_raw, x1_raw, dist_cm)"),
                _p("threshold", "float", required=True, min_value=-40.0, max_value=4095.0, default=45.0, units="°C/%/counts/cm", value_semantics="NUMERIC_LIMIT", description="Numeric threshold trigger limit"),
                _p("condition", "select", default="gt", options=["gt", "lt"], value_semantics="COMPARISON_OPERATOR", description="Alert trigger condition (gt: greater than, lt: less than)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "SENSOR_ENABLE"),
            verb="SET",
            noun="SENSOR_ENABLE",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "SENSOR_ENABLE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Enable or disable sensor sampling",
            parameters=[
                _p("sensor_id", "select", required=True, default="dht11", options=["ldr", "cd4051", "dht11", "moc7811", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Target sensor identifier", discovery_workflow="Query mounted sensors via GET /api/sensors"),
                _p("enabled", "bool", required=True, default=True, options=["true", "false"], value_semantics="BOOLEAN_FLAG", description="Enable acquisition flag (true=poll sensor, false=suspend)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "TRANSPORT_PREFERENCE"),
            verb="SET",
            noun="TRANSPORT_PREFERENCE",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "TRANSPORT_PREFERENCE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Set active transport preference (serial, mqtt, or auto)",
            parameters=[
                _p("transport", "select", required=True, default="auto", options=["auto", "serial", "mqtt"], value_semantics="TRANSPORT_PREFERENCE_ENUM", description="Preferred transport (auto=failover, serial=force UART, mqtt=force Wi-Fi)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("SET", "CONFIGURATION"),
            verb="SET",
            noun="CONFIGURATION",
            verb_code=VERB_CODES["SET"],
            noun_code=NOUN_CODES[("SET", "CONFIGURATION")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Set runtime operational parameter",
            parameters=[
                _p("key", "string", required=True, default="sample_rate", options=["sample_rate", "wifi_ssid", "mqtt_broker", "log_level", "telemetry_interval"], value_semantics="NVS_CONFIG_KEY", description="Configuration setting key", discovery_workflow="Inspect active keys via DISPLAY CONFIGURATION"),
                _p("value", "string", required=True, default="1000", value_semantics="CONFIG_VALUE_STRING", description="Configuration parameter value string"),
            ],
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
            is_supported=True,
            description="Retrieve current executive, heap, and connection status",
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
            is_supported=True,
            description="Retrieve protocol version and configuration parameters",
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
            is_supported=True,
            description="Enumerate registered sensors on device",
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
            is_supported=True,
            description="Retrieve high-resolution device uptime timestamps",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "VERSION"),
            verb="GET",
            noun="VERSION",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "VERSION")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Retrieve firmware version and build timestamp",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "HEALTH"),
            verb="GET",
            noun="HEALTH",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "HEALTH")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Retrieve system health score and subsystem flags",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("GET", "CAPABILITIES"),
            verb="GET",
            noun="CAPABILITIES",
            verb_code=VERB_CODES["GET"],
            noun_code=NOUN_CODES[("GET", "CAPABILITIES")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Enumerate actual installed hardware sensors, actuators, and transports",
        ),

        # 07 ENABLE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ENABLE", "SENSOR"),
            verb="ENABLE",
            noun="SENSOR",
            verb_code=VERB_CODES["ENABLE"],
            noun_code=NOUN_CODES[("ENABLE", "SENSOR")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Enable acquisition job for specified sensor",
            parameters=[
                _p("sensor_id", "select", required=True, default="dht11", options=["ldr", "cd4051", "dht11", "moc7811", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Target sensor identifier to enable", discovery_workflow="Query registered sensors via GET /api/sensors or DISPLAY SENSORS"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ENABLE", "TRANSPORT"),
            verb="ENABLE",
            noun="TRANSPORT",
            verb_code=VERB_CODES["ENABLE"],
            noun_code=NOUN_CODES[("ENABLE", "TRANSPORT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Enable target transport (serial or mqtt)",
            parameters=[
                _p("transport_id", "select", required=True, default="serial", options=["serial", "mqtt"], value_semantics="TRANSPORT_IDENTIFIER", description="Transport layer identifier to enable"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ENABLE", "TELEMETRY"),
            verb="ENABLE",
            noun="TELEMETRY",
            verb_code=VERB_CODES["ENABLE"],
            noun_code=NOUN_CODES[("ENABLE", "TELEMETRY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Enable periodic telemetry transmission",
            parameters=[
                _p("interval_ms", "int", min_value=100, max_value=60000, default=1000, units="ms", value_semantics="NUMERIC_INTERVAL", description="Telemetry streaming cadence in ms (100-60000)"),
            ],
        ),

        # 08 DISABLE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISABLE", "SENSOR"),
            verb="DISABLE",
            noun="SENSOR",
            verb_code=VERB_CODES["DISABLE"],
            noun_code=NOUN_CODES[("DISABLE", "SENSOR")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Disable acquisition job for specified sensor",
            parameters=[
                _p("sensor_id", "select", required=True, default="dht11", options=["ldr", "cd4051", "dht11", "moc7811", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Target sensor identifier to disable", discovery_workflow="Query registered sensors via GET /api/sensors or DISPLAY SENSORS"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISABLE", "TRANSPORT"),
            verb="DISABLE",
            noun="TRANSPORT",
            verb_code=VERB_CODES["DISABLE"],
            noun_code=NOUN_CODES[("DISABLE", "TRANSPORT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Disable target transport",
            parameters=[
                _p("transport_id", "select", required=True, default="mqtt", options=["serial", "mqtt"], value_semantics="TRANSPORT_IDENTIFIER", description="Transport layer identifier to disable"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISABLE", "TELEMETRY"),
            verb="DISABLE",
            noun="TELEMETRY",
            verb_code=VERB_CODES["DISABLE"],
            noun_code=NOUN_CODES[("DISABLE", "TELEMETRY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Disable periodic telemetry transmission",
        ),

        # 09 CALIBRATE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CALIBRATE", "SENSOR"),
            verb="CALIBRATE",
            noun="SENSOR",
            verb_code=VERB_CODES["CALIBRATE"],
            noun_code=NOUN_CODES[("CALIBRATE", "SENSOR")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Set zero/span calibration offset for target sensor",
            parameters=[
                _p("sensor_id", "select", required=True, default="dht11", options=["ldr", "dht11", "mux_x0", "mux_x1", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Sensor identifier for calibration", discovery_workflow="Query registered sensors via GET /api/sensors"),
                _p("offset", "float", default=0.0, min_value=-100.0, max_value=100.0, units="units", value_semantics="CALIBRATION_OFFSET", description="Calibration zero/span offset bias value"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CALIBRATE", "ANALOG"),
            verb="CALIBRATE",
            noun="ANALOG",
            verb_code=VERB_CODES["CALIBRATE"],
            noun_code=NOUN_CODES[("CALIBRATE", "ANALOG")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Sample analog baseline calibration for MUX channel",
            parameters=[
                _p("channel", "int", required=True, min_value=0, max_value=7, default=0, options=["0", "1", "2", "3", "4", "5", "6", "7"], units="channel_idx", value_semantics="MUX_CHANNEL_INDEX", description="CD4051 MUX channel (0=HW-870 LDR, 1=Hall 49E, 2-7=Spare)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CALIBRATE", "ENVIRONMENT"),
            verb="CALIBRATE",
            noun="ENVIRONMENT",
            verb_code=VERB_CODES["CALIBRATE"],
            noun_code=NOUN_CODES[("CALIBRATE", "ENVIRONMENT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Calibrate temperature and humidity reference baseline",
            parameters=[
                _p("temp_offset", "float", default=0.0, min_value=-10.0, max_value=10.0, units="°C", value_semantics="TEMPERATURE_OFFSET", description="Reference temperature offset in °C (-10 to 10)"),
                _p("hum_offset", "float", default=0.0, min_value=-20.0, max_value=20.0, units="%", value_semantics="HUMIDITY_OFFSET", description="Reference humidity offset in % (-20 to 20)"),
            ],
        ),

        # 10 ACKNOWLEDGE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACKNOWLEDGE", "FAULT"),
            verb="ACKNOWLEDGE",
            noun="FAULT",
            verb_code=VERB_CODES["ACKNOWLEDGE"],
            noun_code=NOUN_CODES[("ACKNOWLEDGE", "FAULT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Acknowledge active fault alert",
            parameters=[
                _p("fault_id", "int", required=False, min_value=1, max_value=15, default=1, options=["1", "2", "3", "4", "5", "6", "7", "8"], units="code_or_id", value_semantics="FAULT_IDENTIFIER", description="Active fault code (1=DHT Checksum, 2=Stale Telem, 3=Out of Bounds) or incident ID", discovery_workflow="Query active faults via DISPLAY FAULTS or GET /api/incidents"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACKNOWLEDGE", "WARNING"),
            verb="ACKNOWLEDGE",
            noun="WARNING",
            verb_code=VERB_CODES["ACKNOWLEDGE"],
            noun_code=NOUN_CODES[("ACKNOWLEDGE", "WARNING")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Acknowledge warning alert",
            parameters=[
                _p("warning_id", "int", required=False, min_value=1, max_value=15, default=2, options=["1", "2", "3", "4", "5", "6"], units="code_or_id", value_semantics="WARNING_IDENTIFIER", description="Warning code (2=Stale Telem, 3=Range Exceeded, 5=Deadline Miss) or incident ID", discovery_workflow="Query active warnings via GET /api/incidents or telemetry health alerts"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACKNOWLEDGE", "EVENT"),
            verb="ACKNOWLEDGE",
            noun="EVENT",
            verb_code=VERB_CODES["ACKNOWLEDGE"],
            noun_code=NOUN_CODES[("ACKNOWLEDGE", "EVENT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Acknowledge notification event",
            parameters=[
                _p("event_id", "int", required=False, min_value=1, max_value=11, default=1, options=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"], units="event_type_or_seq", value_semantics="EVENT_IDENTIFIER", description="Firmware event type (1=SYSTEM_BOOT..11=COMMAND_COMPLETED) or event sequence ID", discovery_workflow="Query event types and recent events via DISPLAY QUEUES or GET /api/incidents"),
            ],
        ),

        # 11 CLEAR
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CLEAR", "FAULTS"),
            verb="CLEAR",
            noun="FAULTS",
            verb_code=VERB_CODES["CLEAR"],
            noun_code=NOUN_CODES[("CLEAR", "FAULTS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Clear all active and latched faults without rebooting",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CLEAR", "HISTORY"),
            verb="CLEAR",
            noun="HISTORY",
            verb_code=VERB_CODES["CLEAR"],
            noun_code=NOUN_CODES[("CLEAR", "HISTORY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Clear stored history ring buffer",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CLEAR", "STATISTICS"),
            verb="CLEAR",
            noun="STATISTICS",
            verb_code=VERB_CODES["CLEAR"],
            noun_code=NOUN_CODES[("CLEAR", "STATISTICS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Clear executive dispatch statistics",
        ),

        # 12 TEST
        CommandRegistryEntry(
            cmd_id=make_cmd_id("TEST", "SENSOR"),
            verb="TEST",
            noun="SENSOR",
            verb_code=VERB_CODES["TEST"],
            noun_code=NOUN_CODES[("TEST", "SENSOR")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Execute single synchronous sensor diagnostic read",
            parameters=[
                _p("sensor_id", "select", required=True, default="dht11", options=["ldr", "cd4051", "dht11", "moc7811", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Target sensor for diagnostic single read", discovery_workflow="Query registered sensors via GET /api/sensors"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("TEST", "TRANSPORT"),
            verb="TEST",
            noun="TRANSPORT",
            verb_code=VERB_CODES["TEST"],
            noun_code=NOUN_CODES[("TEST", "TRANSPORT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Ping and verify transport round-trip",
            parameters=[
                _p("transport_id", "select", required=False, default="serial", options=["serial", "mqtt"], value_semantics="TRANSPORT_IDENTIFIER", description="Transport layer for ping loopback test"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("TEST", "EXECUTIVE"),
            verb="TEST",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["TEST"],
            noun_code=NOUN_CODES[("TEST", "EXECUTIVE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Run executive dispatch timing validation",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("TEST", "PERIPHERAL"),
            verb="TEST",
            noun="PERIPHERAL",
            verb_code=VERB_CODES["TEST"],
            noun_code=NOUN_CODES[("TEST", "PERIPHERAL")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Test board peripheral lines and shift register",
        ),

        # 13 ACTUATE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACTUATE", "RELAY"),
            verb="ACTUATE",
            noun="RELAY",
            verb_code=VERB_CODES["ACTUATE"],
            noun_code=NOUN_CODES[("ACTUATE", "RELAY")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=False,
            description="Relay K1 hardware unmounted on this build",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACTUATE", "LED"),
            verb="ACTUATE",
            noun="LED",
            verb_code=VERB_CODES["ACTUATE"],
            noun_code=NOUN_CODES[("ACTUATE", "LED")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Set onboard LED state (LED1..4)",
            parameters=[
                _p("led_id", "int", required=True, min_value=1, max_value=4, default=1, options=["1", "2", "3", "4"], units="channel", value_semantics="HARDWARE_CHANNEL", description="Diagnostic LED index (1=GPIO27, 2=GPIO14, 3=GPIO12, 4=GPIO13)"),
                _p("state", "select", required=True, options=["on", "off"], default="on", value_semantics="BINARY_STATE", description="Desired LED output state (on=illuminate, off=extinguish)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACTUATE", "MOTOR"),
            verb="ACTUATE",
            noun="MOTOR",
            verb_code=VERB_CODES["ACTUATE"],
            noun_code=NOUN_CODES[("ACTUATE", "MOTOR")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=False,
            description="DC Motors unmounted on this build",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACTUATE", "SERVO"),
            verb="ACTUATE",
            noun="SERVO",
            verb_code=VERB_CODES["ACTUATE"],
            noun_code=NOUN_CODES[("ACTUATE", "SERVO")],
            disposition=CommandDisposition.UNSUPPORTED,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=False,
            description="Servo motor unmounted on GPIO33 on this build",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACTUATE", "BUZZER"),
            verb="ACTUATE",
            noun="BUZZER",
            verb_code=VERB_CODES["ACTUATE"],
            noun_code=NOUN_CODES[("ACTUATE", "BUZZER")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Beep onboard 5V buzzer for bounded duration",
            parameters=[
                _p("duration_ms", "int", required=True, min_value=10, max_value=5000, default=200, units="ms", value_semantics="NUMERIC_DURATION", description="Beep duration in milliseconds (10-5000)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ACTUATE", "SHIFT_REGISTER"),
            verb="ACTUATE",
            noun="SHIFT_REGISTER",
            verb_code=VERB_CODES["ACTUATE"],
            noun_code=NOUN_CODES[("ACTUATE", "SHIFT_REGISTER")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Shift 8-bit output pattern to 74HC595",
            parameters=[
                _p("value", "int", required=True, min_value=0, max_value=255, default=0, units="byte", value_semantics="BITMASK_BYTE", description="8-bit pattern to shift into 74HC595 (0-255)"),
            ],
        ),

        # 14 CAPTURE
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CAPTURE", "TELEMETRY"),
            verb="CAPTURE",
            noun="TELEMETRY",
            verb_code=VERB_CODES["CAPTURE"],
            noun_code=NOUN_CODES[("CAPTURE", "TELEMETRY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Capture instantaneous telemetry snapshot",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CAPTURE", "SENSOR_SNAPSHOT"),
            verb="CAPTURE",
            noun="SENSOR_SNAPSHOT",
            verb_code=VERB_CODES["CAPTURE"],
            noun_code=NOUN_CODES[("CAPTURE", "SENSOR_SNAPSHOT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Capture snapshot of all active sensor channels",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("CAPTURE", "EVENT_SNAPSHOT"),
            verb="CAPTURE",
            noun="EVENT_SNAPSHOT",
            verb_code=VERB_CODES["CAPTURE"],
            noun_code=NOUN_CODES[("CAPTURE", "EVENT_SNAPSHOT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Capture snapshot of recent event queue entries",
        ),

        # 15 PUBLISH
        CommandRegistryEntry(
            cmd_id=make_cmd_id("PUBLISH", "TELEMETRY"),
            verb="PUBLISH",
            noun="TELEMETRY",
            verb_code=VERB_CODES["PUBLISH"],
            noun_code=NOUN_CODES[("PUBLISH", "TELEMETRY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Immediately transmit current telemetry frame",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("PUBLISH", "EVENT"),
            verb="PUBLISH",
            noun="EVENT",
            verb_code=VERB_CODES["PUBLISH"],
            noun_code=NOUN_CODES[("PUBLISH", "EVENT")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Publish high-priority event notification",
            parameters=[
                _p("event_name", "string", required=True, default="OPERATOR_CHECKPOINT", value_semantics="EVENT_NAME_STRING", description="Event name identifier or operator message"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("PUBLISH", "STATUS"),
            verb="PUBLISH",
            noun="STATUS",
            verb_code=VERB_CODES["PUBLISH"],
            noun_code=NOUN_CODES[("PUBLISH", "STATUS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Publish heartbeat status envelope",
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
            is_supported=True,
            description="Format active device and executive status",
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
            is_supported=True,
            description="Format executive metrics (dispatch, complete, fail, misses)",
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
            is_supported=True,
            description="Format ready and event queue depths and watermarks",
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
            is_supported=True,
            description="Format fault summary",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "SENSORS"),
            verb="DISPLAY",
            noun="SENSORS",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "SENSORS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format comprehensive summary of all registered sensors",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "TRANSPORTS"),
            verb="DISPLAY",
            noun="TRANSPORTS",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "TRANSPORTS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format active connection status and transport stats",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "CONFIGURATION"),
            verb="DISPLAY",
            noun="CONFIGURATION",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "CONFIGURATION")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format current device configuration",
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
            is_supported=True,
            description="Format environmental sensor readings (DHT11 temp and humidity)",
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
            is_supported=True,
            description="Format light sensor readings (LDR ADC raw)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "DISTANCE"),
            verb="DISPLAY",
            noun="DISTANCE",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "DISTANCE")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format HC-SR04 ultrasonic distance reading",
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
            is_supported=True,
            description="Format analog multiplexer readings (CD4051 X0 Gas, X1 Hall)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "MOTION"),
            verb="DISPLAY",
            noun="MOTION",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "MOTION")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format optical motion readings (MOC7811 slot opto)",
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
            is_supported=True,
            description="Format event queue counters",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "ACTUATORS"),
            verb="DISPLAY",
            noun="ACTUATORS",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "ACTUATORS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format current status of board actuators (LEDs, Buzzer, Shift Register)",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DISPLAY", "CONNECTIVITY"),
            verb="DISPLAY",
            noun="CONNECTIVITY",
            verb_code=VERB_CODES["DISPLAY"],
            noun_code=NOUN_CODES[("DISPLAY", "CONNECTIVITY")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format Wi-Fi, IP, and broker connectivity details",
        ),

        # 17 HISTORY
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "EVENTS"),
            verb="HISTORY",
            noun="EVENTS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "EVENTS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format recent event logs from memory ring buffer",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "FAULTS"),
            verb="HISTORY",
            noun="FAULTS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "FAULTS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format historical fault logs",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "EXECUTIVE"),
            verb="HISTORY",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "EXECUTIVE")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format historical executive latency milestones",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "SENSORS"),
            verb="HISTORY",
            noun="SENSORS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "SENSORS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format sensor transition history",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "TRANSPORTS"),
            verb="HISTORY",
            noun="TRANSPORTS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "TRANSPORTS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format transport state transition history",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "ENVIRONMENT"),
            verb="HISTORY",
            noun="ENVIRONMENT",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "ENVIRONMENT")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format environmental history snapshots",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("HISTORY", "SENSOR_READINGS"),
            verb="HISTORY",
            noun="SENSOR_READINGS",
            verb_code=VERB_CODES["HISTORY"],
            noun_code=NOUN_CODES[("HISTORY", "SENSOR_READINGS")],
            disposition=CommandDisposition.REQUIRED_M8,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=True,
            is_supported=True,
            description="Format recent sensor reading trends",
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
            is_supported=True,
            description="Format full system diagnostics (heap, reset reason, uptime)",
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
            is_supported=True,
            description="Format sensor diagnostics (read counts, error rates, valid flags)",
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
            is_supported=True,
            description="Format queue high water marks and overflow tallies",
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
            is_supported=True,
            description="Format execution timing (max dispatch latency, job durations)",
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
            is_supported=True,
            description="Format memory heap usage and minimum watermark",
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
            is_supported=True,
            description="Format transport throughput and error counters",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "EXECUTIVE"),
            verb="DIAGNOSTICS",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "EXECUTIVE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format executive priority class stats and scheduling health",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "PERIPHERALS"),
            verb="DIAGNOSTICS",
            noun="PERIPHERALS",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "PERIPHERALS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Format peripheral bus and GPIO diagnostics",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "DATABASE"),
            verb="DIAGNOSTICS",
            noun="DATABASE",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "DATABASE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Check InfluxDB time-series database health from ground station",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("DIAGNOSTICS", "AI_SERVICE"),
            verb="DIAGNOSTICS",
            noun="AI_SERVICE",
            verb_code=VERB_CODES["DIAGNOSTICS"],
            noun_code=NOUN_CODES[("DIAGNOSTICS", "AI_SERVICE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Check Open WebUI and local LLM service reachability",
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
            is_supported=True,
            description="Open Grafana telemetry dashboard on operator workstation",
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
            is_supported=True,
            description="Open operational log explorer in browser",
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
            is_supported=True,
            description="Open Open WebUI AI assistant interface",
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
            is_supported=True,
            description="Open NEXUS Ground Station web control panel",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("OPEN", "DATABASE"),
            verb="OPEN",
            noun="DATABASE",
            verb_code=VERB_CODES["OPEN"],
            noun_code=NOUN_CODES[("OPEN", "DATABASE")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Open InfluxDB web UI",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("OPEN", "DIAGNOSTICS"),
            verb="OPEN",
            noun="DIAGNOSTICS",
            verb_code=VERB_CODES["OPEN"],
            noun_code=NOUN_CODES[("OPEN", "DIAGNOSTICS")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Open ground station diagnostics view",
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
            is_supported=True,
            description="Query AI assistant about system operational status",
            parameters=[
                _p("question", "string", required=True, default="Provide complete health status of the ESP32", value_semantics="NATURAL_LANGUAGE_QUERY", description="Natural language prompt regarding system operational health, uptime, or memory"),
            ],
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
            is_supported=True,
            description="Query AI assistant about specific sensor trends and anomalies",
            parameters=[
                _p("sensor_id", "select", required=False, default="hcsr04", options=["ldr", "cd4051", "dht11", "moc7811", "hcsr04"], value_semantics="SENSOR_IDENTIFIER", description="Sensor identifier to scope AI telemetry query", discovery_workflow="Query mounted sensors via GET /api/sensors"),
                _p("question", "string", required=True, default="max recorded distance to date", value_semantics="NATURAL_LANGUAGE_QUERY", description="Natural language query for signal trend, statistical aggregation, or anomalies"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ASK", "EXECUTIVE"),
            verb="ASK",
            noun="EXECUTIVE",
            verb_code=VERB_CODES["ASK"],
            noun_code=NOUN_CODES[("ASK", "EXECUTIVE")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Query AI assistant about executive scheduling and timing",
            parameters=[
                _p("question", "string", required=True, default="What is the current executive dispatch load and deadline miss rate?", value_semantics="NATURAL_LANGUAGE_QUERY", description="Natural language prompt regarding cyclic executive scheduler performance"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("ASK", "DIAGNOSTICS"),
            verb="ASK",
            noun="DIAGNOSTICS",
            verb_code=VERB_CODES["ASK"],
            noun_code=NOUN_CODES[("ASK", "DIAGNOSTICS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Query AI assistant for diagnostic health analysis",
            parameters=[
                _p("question", "string", required=True, default="Analyze current diagnostic logs and identify root cause of any warnings", value_semantics="NATURAL_LANGUAGE_QUERY", description="Natural language query for diagnostic log synthesis"),
            ],
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
            is_supported=True,
            description="Query AI assistant regarding environmental conditions",
            parameters=[
                _p("question", "string", required=True, default="Is the ambient temperature and humidity within nominal operating envelope?", value_semantics="NATURAL_LANGUAGE_QUERY", description="Natural language prompt analyzing environmental readings against safety thresholds"),
            ],
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
            is_supported=True,
            description="Export telemetry data to JSON or CSV via ground station",
            parameters=[
                _p("format", "select", required=False, default="json", options=["json", "csv"], value_semantics="EXPORT_FORMAT_ENUM", description="Data export serialization format"),
                _p("limit", "int", required=False, min_value=1, max_value=1000, default=100, units="records", value_semantics="RECORD_COUNT_LIMIT", description="Maximum number of historical records to export (1-1000)"),
            ],
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
            is_supported=True,
            description="Export diagnostic snapshot from ground station",
            parameters=[
                _p("format", "select", required=False, default="json", options=["json", "csv"], value_semantics="EXPORT_FORMAT_ENUM", description="Diagnostic snapshot export format"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("EXPORT", "EVENTS"),
            verb="EXPORT",
            noun="EVENTS",
            verb_code=VERB_CODES["EXPORT"],
            noun_code=NOUN_CODES[("EXPORT", "EVENTS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Export recorded incident events",
            parameters=[
                _p("format", "select", required=False, default="json", options=["json", "csv"], value_semantics="EXPORT_FORMAT_ENUM", description="Incident event log export format"),
                _p("limit", "int", required=False, min_value=1, max_value=500, default=50, units="events", value_semantics="RECORD_COUNT_LIMIT", description="Maximum number of events to export (1-500)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("EXPORT", "FAULTS"),
            verb="EXPORT",
            noun="FAULTS",
            verb_code=VERB_CODES["EXPORT"],
            noun_code=NOUN_CODES[("EXPORT", "FAULTS")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Export recorded fault history",
            parameters=[
                _p("format", "select", required=False, default="json", options=["json", "csv"], value_semantics="EXPORT_FORMAT_ENUM", description="Fault history serialization format"),
                _p("limit", "int", required=False, min_value=1, max_value=500, default=50, units="faults", value_semantics="RECORD_COUNT_LIMIT", description="Maximum number of fault records to export (1-500)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("EXPORT", "CONFIGURATION"),
            verb="EXPORT",
            noun="CONFIGURATION",
            verb_code=VERB_CODES["EXPORT"],
            noun_code=NOUN_CODES[("EXPORT", "CONFIGURATION")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.GROUND_STATION,
            is_supported_m8=False,
            is_supported=True,
            description="Export current configuration manifest",
            parameters=[
                _p("format", "select", required=False, default="json", options=["json"], value_semantics="EXPORT_FORMAT_ENUM", description="Configuration export format"),
            ],
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
            is_supported=True,
            description="Run bounded executive and data structure self-test",
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
            is_supported=True,
            description="Run physical sensor driver validity and presence self-test",
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RUN", "STRESS_TEST"),
            verb="RUN",
            noun="STRESS_TEST",
            verb_code=VERB_CODES["RUN"],
            noun_code=NOUN_CODES[("RUN", "STRESS_TEST")],
            disposition=CommandDisposition.DEFERRED_M9_M10,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Run bounded executive queue stress test",
            parameters=[
                _p("duration_sec", "int", required=False, min_value=1, max_value=30, default=5, units="s", value_semantics="NUMERIC_DURATION", description="Executive queue stress test execution duration (1-30 seconds)"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RUN", "TRANSPORT_TEST"),
            verb="RUN",
            noun="TRANSPORT_TEST",
            verb_code=VERB_CODES["RUN"],
            noun_code=NOUN_CODES[("RUN", "TRANSPORT_TEST")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            description="Run end-to-end transport roundtrip latency test",
            parameters=[
                _p("transport_id", "select", required=False, default="serial", options=["serial", "mqtt"], value_semantics="TRANSPORT_IDENTIFIER", description="Transport layer for latency test"),
            ],
        ),
        CommandRegistryEntry(
            cmd_id=make_cmd_id("RUN", "QUALIFICATION_TEST"),
            verb="RUN",
            noun="QUALIFICATION_TEST",
            verb_code=VERB_CODES["RUN"],
            noun_code=NOUN_CODES[("RUN", "QUALIFICATION_TEST")],
            disposition=CommandDisposition.EXISTING_CAPABILITY,
            destination=CommandDestination.FIRMWARE,
            is_supported_m8=False,
            is_supported=True,
            requires_confirmation=True,
            description="Run qualification test verification suite",
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
    def is_supported(cls, cmd_id: int) -> bool:
        """Check if command ID is implemented in active system."""
        entry = cls.lookup_by_id(cmd_id)
        return entry.is_supported if entry else False

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

    @classmethod
    def validate_command_parameters(
        cls, entry: CommandRegistryEntry, params: Optional[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """Validate supplied params dictionary against entry's parameter specifications."""
        params = params or {}
        for p in entry.parameters:
            if p.required and p.name not in params:
                return False, f"Missing required parameter: {p.name}"
            if p.name in params:
                val = params[p.name]
                if p.type_name == "int":
                    try:
                        int_val = int(val)
                    except (ValueError, TypeError):
                        return False, f"Parameter '{p.name}' must be an integer, got: {val}"
                    if p.min_value is not None and int_val < p.min_value:
                        return False, f"Parameter '{p.name}' value {int_val} below minimum {p.min_value}"
                    if p.max_value is not None and int_val > p.max_value:
                        return False, f"Parameter '{p.name}' value {int_val} above maximum {p.max_value}"
                elif p.type_name == "float":
                    try:
                        float_val = float(val)
                    except (ValueError, TypeError):
                        return False, f"Parameter '{p.name}' must be a float, got: {val}"
                    if p.min_value is not None and float_val < p.min_value:
                        return False, f"Parameter '{p.name}' value {float_val} below minimum {p.min_value}"
                    if p.max_value is not None and float_val > p.max_value:
                        return False, f"Parameter '{p.name}' value {float_val} above maximum {p.max_value}"
                elif p.type_name == "bool":
                    if str(val).lower() not in ("0", "1", "true", "false"):
                        return False, f"Parameter '{p.name}' must be boolean, got: {val}"
                elif p.type_name == "select" and p.options:
                    if str(val) not in p.options:
                        return False, f"Parameter '{p.name}' must be one of {p.options}, got: {val}"
        return True, ""

    @classmethod
    def get_catalog_schema(cls) -> Dict[str, Any]:
        """Return JSON-serializable command catalog for browser control panel."""
        verbs = sorted(list(set(e.verb for e in cls._ENTRIES)))
        catalog: Dict[str, Dict[str, Any]] = {}
        entries_list: List[Dict[str, Any]] = []

        for e in cls._ENTRIES:
            param_list = []
            for p in e.parameters:
                param_list.append({
                    "name": p.name,
                    "type": p.type_name,
                    "required": p.required,
                    "description": p.description,
                    "default": p.default,
                    "min_value": p.min_value,
                    "max_value": p.max_value,
                    "enum_values": p.options or [],
                    "units": p.units,
                    "value_semantics": p.value_semantics,
                    "discovery_workflow": p.discovery_workflow,
                    "value_mappings": p.value_mappings or {},
                })

            item = {
                "cmd_id": e.cmd_id,
                "verb": e.verb,
                "noun": e.noun,
                "verb_code": e.verb_code,
                "noun_code": e.noun_code,
                "disposition": e.disposition.value,
                "destination": e.destination.value,
                "is_supported": e.is_supported,
                "is_supported_m8": e.is_supported_m8,
                "requires_confirmation": e.requires_confirmation,
                "description": e.description,
                "parameters": param_list,
            }
            entries_list.append(item)

            if e.verb not in catalog:
                catalog[e.verb] = {}
            catalog[e.verb][e.noun] = item

        return {
            "total_commands": len(cls._ENTRIES),
            "verbs": verbs,
            "catalog": catalog,
            "entries": entries_list,
        }

