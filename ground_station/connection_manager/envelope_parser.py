"""NEXUS Protocol v1 Envelope Parser.

Performs strict parsing, decoding, schema validation, and type-safe representation
of NEXUS firmware telemetry envelopes adhering to NEXUS Protocol v1 specifications.
"""

from __future__ import annotations

import enum
import json
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Union

# NEXUS Protocol v1 Constants matching firmware (nexus_envelope.h)
NEXUS_ENVELOPE_MAX_LEN = 256
NEXUS_PROTOCOL_VERSION = 1
NEXUS_DEV_ID_MAX_LEN = 16

UINT8_MAX = 0xFF
UINT16_MAX = 0xFFFF
UINT32_MAX = 0xFFFFFFFF
INT32_MIN = -0x80000000
INT32_MAX = 0x7FFFFFFF
INT64_MAX = 0x7FFFFFFFFFFFFFFF


class MessageType(enum.Enum):
    """Enumeration of recognized NEXUS message types."""

    HEARTBEAT = "hb"
    TELEMETRY = "telem"
    STATUS = "status"
    EVENT = "event"
    COMMAND = "cmd"
    RESPONSE = "resp"


# Canonical string mapping (firmware supports short and long forms)
_TYPE_LOOKUP = {
    "hb": MessageType.HEARTBEAT,
    "heartbeat": MessageType.HEARTBEAT,
    "telem": MessageType.TELEMETRY,
    "telemetry": MessageType.TELEMETRY,
    "status": MessageType.STATUS,
    "event": MessageType.EVENT,
    "cmd": MessageType.COMMAND,
    "command": MessageType.COMMAND,
    "resp": MessageType.RESPONSE,
    "response": MessageType.RESPONSE,
}


# --- Exception Hierarchy ---


class EnvelopeParseError(Exception):
    """Base exception for all NEXUS envelope parsing and validation failures."""

    def __init__(self, message: str, category: str = "parse_error") -> None:
        super().__init__(message)
        self.category = category


class OversizedEnvelopeError(EnvelopeParseError):
    """Raised when an incoming raw payload exceeds NEXUS_ENVELOPE_MAX_LEN."""

    def __init__(self, length: int) -> None:
        super().__init__(
            f"Envelope length {length} bytes exceeds maximum limit of {NEXUS_ENVELOPE_MAX_LEN} bytes",
            category="oversized_envelope",
        )
        self.length = length


class MalformedJsonError(EnvelopeParseError):
    """Raised when envelope contains malformed JSON, invalid UTF-8, or non-finite constants."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Malformed JSON: {reason}", category="malformed_json")


class UnsupportedVersionError(EnvelopeParseError):
    """Raised when the envelope version is not NEXUS_PROTOCOL_VERSION (1)."""

    def __init__(self, version: Any) -> None:
        super().__init__(
            f"Unsupported protocol version: {version!r} (expected {NEXUS_PROTOCOL_VERSION})",
            category="unsupported_version",
        )
        self.version = version


class UnknownMessageTypeError(EnvelopeParseError):
    """Raised when the envelope type is not a recognized NEXUS message type."""

    def __init__(self, msg_type: Any) -> None:
        super().__init__(
            f"Unknown message type: {msg_type!r}",
            category="unknown_message_type",
        )
        self.msg_type = msg_type


class MissingFieldError(EnvelopeParseError):
    """Raised when a mandatory field is missing from the envelope."""

    def __init__(self, field_name: str, msg_type: Optional[str] = None) -> None:
        type_ctx = f" for message type '{msg_type}'" if msg_type else ""
        super().__init__(
            f"Missing required field '{field_name}'{type_ctx}",
            category="missing_field",
        )
        self.field_name = field_name


class FieldTypeError(EnvelopeParseError):
    """Raised when a field has an invalid data type."""

    def __init__(self, field_name: str, expected_type: str, actual_value: Any) -> None:
        super().__init__(
            f"Field '{field_name}' expected {expected_type}, got {type(actual_value).__name__}",
            category="field_type_error",
        )
        self.field_name = field_name
        self.expected_type = expected_type


class FieldRangeError(EnvelopeParseError):
    """Raised when a field's value is outside the allowed protocol range."""

    def __init__(self, field_name: str, min_val: Any, max_val: Any, actual_value: Any) -> None:
        super().__init__(
            f"Field '{field_name}' value {actual_value!r} out of range [{min_val}, {max_val}]",
            category="field_range_error",
        )
        self.field_name = field_name


# --- Typed Payloads ---


@dataclass(frozen=True)
class HeartbeatPayload:
    """Parsed payload for Heartbeat ('hb') envelopes."""

    uptime_ms: int
    free_heap: int
    exec_ticks: int


@dataclass(frozen=True)
class TelemetryPayload:
    """Parsed payload for Telemetry ('telem') envelopes.

    When dht_valid is False, temp and hum are strictly None to ensure
    downstream consumers never treat degraded/uninitialized readings as valid.
    """

    uptime_ms: int
    ldr_raw: int
    x0_raw: int
    dht_valid: bool
    temp: Optional[float]
    hum: Optional[float]
    suppressed_temp: Optional[float] = None
    suppressed_hum: Optional[float] = None


@dataclass(frozen=True)
class StatusPayload:
    """Parsed payload for Executive Status ('status') envelopes."""

    uptime_ms: int
    dispatched: int
    completed: int
    failed: int
    max_lat_us: int
    max_dur_us: int


@dataclass(frozen=True)
class EventPayload:
    """Parsed payload for Executive Event ('event') envelopes."""

    uptime_ms: int
    event_type: int
    severity: int
    source_id: int
    payload_val: int


@dataclass(frozen=True)
class CommandPayload:
    """Parsed payload for Inbound/Outbound Command ('cmd') envelopes."""

    uptime_ms: Optional[int]
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class ResponsePayload:
    """Parsed payload for Command Response ('resp') envelopes."""

    uptime_ms: Optional[int]
    fields: Mapping[str, Any]


EnvelopePayload = Union[
    HeartbeatPayload,
    TelemetryPayload,
    StatusPayload,
    EventPayload,
    CommandPayload,
    ResponsePayload,
]


@dataclass(frozen=True)
class ParsedEnvelope:
    """Immutable, validated representation of a NEXUS Protocol envelope."""

    raw_bytes: bytes
    raw_text: str
    ver: int
    dev: str
    seq: int
    msg_type: MessageType
    uptime_ms: Optional[int]
    payload: EnvelopePayload
    extra_fields: Mapping[str, Any]
    raw_dict: Mapping[str, Any]
    transport: Optional[str] = None
    received_at: Optional[float] = None


def _reject_json_constant(constant: str) -> None:
    """Reject non-standard/non-finite JSON constants like NaN, Infinity, -Infinity."""
    raise ValueError(f"Non-finite numeric constant '{constant}' is disallowed by NEXUS protocol")


def _is_int(val: Any) -> bool:
    """Check if value is an integer and NOT a boolean."""
    return isinstance(val, int) and not isinstance(val, bool)


def _is_finite_number(val: Any) -> bool:
    """Check if value is a finite int or float and NOT a boolean."""
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return math.isfinite(val)
    return False


class EnvelopeParser:
    """Strict parser and validator for NEXUS Protocol v1 wire-format envelopes."""

    @staticmethod
    def parse(data: Union[bytes, str]) -> ParsedEnvelope:
        """Parse, validate, and return an immutable ParsedEnvelope.

        Args:
            data: Raw envelope as bytes or string (typically newline-delimited JSON).

        Returns:
            ParsedEnvelope containing strictly typed header and payload.

        Raises:
            OversizedEnvelopeError: If the raw data length exceeds NEXUS_ENVELOPE_MAX_LEN (256 bytes).
            MalformedJsonError: If JSON syntax is invalid, encoding is broken, or contains NaN/Infinity.
            UnsupportedVersionError: If 'ver' is not 1.
            UnknownMessageTypeError: If 'type' is not recognized.
            MissingFieldError: If a mandatory field is missing.
            FieldTypeError: If a field has the wrong data type.
            FieldRangeError: If a numeric field is out of its allowable protocol range.
        """
        # 1. Bounded size enforcement (< 256 bytes wire limit as defined by firmware)
        if isinstance(data, str):
            raw_bytes = data.encode("utf-8", errors="replace")
            raw_text = data
        elif isinstance(data, (bytes, bytearray)):
            raw_bytes = bytes(data)
            try:
                raw_text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as err:
                raise MalformedJsonError(f"Invalid UTF-8 byte sequence: {err}") from err
        else:
            raise FieldTypeError("data", "bytes or str", data)

        if len(raw_bytes) >= NEXUS_ENVELOPE_MAX_LEN:
            raise OversizedEnvelopeError(len(raw_bytes))

        # Strip newline/carriage returns for parsing
        trimmed = raw_text.strip()
        if not trimmed:
            raise MalformedJsonError("Empty envelope payload")

        # 2. Strict JSON decoding (rejecting NaN, Infinity, -Infinity)
        try:
            parsed_json = json.loads(trimmed, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as err:
            raise MalformedJsonError(f"Syntax error at char {err.pos}: {err.msg}") from err
        except ValueError as err:
            raise MalformedJsonError(str(err)) from err

        if not isinstance(parsed_json, dict):
            raise MalformedJsonError("Envelope root must be a JSON object")

        # 3. Common Header Validation
        # 3a. 'ver': required, int, must be 1
        if "ver" not in parsed_json:
            raise MissingFieldError("ver")
        ver_val = parsed_json["ver"]
        if not _is_int(ver_val):
            raise FieldTypeError("ver", "integer", ver_val)
        if ver_val != NEXUS_PROTOCOL_VERSION:
            raise UnsupportedVersionError(ver_val)

        # 3b. 'dev': required, str, non-empty, bounded length
        if "dev" not in parsed_json:
            raise MissingFieldError("dev")
        dev_val = parsed_json["dev"]
        if not isinstance(dev_val, str):
            raise FieldTypeError("dev", "string", dev_val)
        if len(dev_val) == 0:
            raise FieldRangeError("dev", 1, 64, 0)

        # 3c. 'seq': required, uint32 int (0..0xFFFFFFFF)
        if "seq" not in parsed_json:
            raise MissingFieldError("seq")
        seq_val = parsed_json["seq"]
        if not _is_int(seq_val):
            raise FieldTypeError("seq", "uint32 integer", seq_val)
        if seq_val < 0 or seq_val > UINT32_MAX:
            raise FieldRangeError("seq", 0, UINT32_MAX, seq_val)

        # 3d. 'type': required, str, recognized
        if "type" not in parsed_json:
            raise MissingFieldError("type")
        type_val = parsed_json["type"]
        if not isinstance(type_val, str):
            raise FieldTypeError("type", "string", type_val)
        if type_val not in _TYPE_LOOKUP:
            raise UnknownMessageTypeError(type_val)
        msg_type = _TYPE_LOOKUP[type_val]

        # 3e. 'uptime': required for firmware-originated packets (hb, telem, status, event), optional for cmd
        uptime_ms: Optional[int] = None
        if "uptime" in parsed_json:
            up_val = parsed_json["uptime"]
            if not _is_int(up_val):
                raise FieldTypeError("uptime", "int64 integer", up_val)
            if up_val < 0 or up_val > INT64_MAX:
                raise FieldRangeError("uptime", 0, INT64_MAX, up_val)
            uptime_ms = up_val
        elif msg_type in (
            MessageType.HEARTBEAT,
            MessageType.TELEMETRY,
            MessageType.STATUS,
            MessageType.EVENT,
        ):
            raise MissingFieldError("uptime", type_val)

        # 4. Message-Type Specific Payload Validation
        payload: EnvelopePayload
        consumed_keys = {"ver", "dev", "seq", "type", "uptime"}

        if msg_type == MessageType.HEARTBEAT:
            assert uptime_ms is not None
            # 'heap': uint32
            if "heap" not in parsed_json:
                raise MissingFieldError("heap", type_val)
            heap_val = parsed_json["heap"]
            if not _is_int(heap_val):
                raise FieldTypeError("heap", "uint32 integer", heap_val)
            if heap_val < 0 or heap_val > UINT32_MAX:
                raise FieldRangeError("heap", 0, UINT32_MAX, heap_val)

            # 'ticks': uint32
            if "ticks" not in parsed_json:
                raise MissingFieldError("ticks", type_val)
            ticks_val = parsed_json["ticks"]
            if not _is_int(ticks_val):
                raise FieldTypeError("ticks", "uint32 integer", ticks_val)
            if ticks_val < 0 or ticks_val > UINT32_MAX:
                raise FieldRangeError("ticks", 0, UINT32_MAX, ticks_val)

            consumed_keys.update({"heap", "ticks"})
            payload = HeartbeatPayload(
                uptime_ms=uptime_ms,
                free_heap=heap_val,
                exec_ticks=ticks_val,
            )

        elif msg_type == MessageType.TELEMETRY:
            assert uptime_ms is not None
            # 'ldr': integer (ADC count)
            if "ldr" not in parsed_json:
                raise MissingFieldError("ldr", type_val)
            ldr_val = parsed_json["ldr"]
            if not _is_int(ldr_val):
                raise FieldTypeError("ldr", "integer", ldr_val)
            if ldr_val < INT32_MIN or ldr_val > INT32_MAX:
                raise FieldRangeError("ldr", INT32_MIN, INT32_MAX, ldr_val)

            # 'x0': integer (ADC count)
            if "x0" not in parsed_json:
                raise MissingFieldError("x0", type_val)
            x0_val = parsed_json["x0"]
            if not _is_int(x0_val):
                raise FieldTypeError("x0", "integer", x0_val)
            if x0_val < INT32_MIN or x0_val > INT32_MAX:
                raise FieldRangeError("x0", INT32_MIN, INT32_MAX, x0_val)

            # 'dht_valid': boolean
            if "dht_valid" not in parsed_json:
                raise MissingFieldError("dht_valid", type_val)
            dht_valid_val = parsed_json["dht_valid"]
            if not isinstance(dht_valid_val, bool):
                raise FieldTypeError("dht_valid", "boolean", dht_valid_val)

            consumed_keys.update({"ldr", "x0", "dht_valid"})

            temp_out: Optional[float] = None
            hum_out: Optional[float] = None
            suppressed_temp: Optional[float] = None
            suppressed_hum: Optional[float] = None

            if dht_valid_val is True:
                # When dht_valid is True, temp and hum MUST be valid finite numbers
                if "temp" not in parsed_json:
                    raise MissingFieldError("temp", type_val)
                t_val = parsed_json["temp"]
                if not _is_finite_number(t_val):
                    raise FieldTypeError("temp", "finite number", t_val)

                if "hum" not in parsed_json:
                    raise MissingFieldError("hum", type_val)
                h_val = parsed_json["hum"]
                if not _is_finite_number(h_val):
                    raise FieldTypeError("hum", "finite number", h_val)

                temp_out = float(t_val)
                hum_out = float(h_val)
                consumed_keys.update({"temp", "hum"})
            else:
                # When dht_valid is False:
                # In firmware, temp and hum are omitted. If present, they MUST NOT
                # be exposed as valid readings.
                if "temp" in parsed_json:
                    consumed_keys.add("temp")
                    if _is_finite_number(parsed_json["temp"]):
                        suppressed_temp = float(parsed_json["temp"])
                if "hum" in parsed_json:
                    consumed_keys.add("hum")
                    if _is_finite_number(parsed_json["hum"]):
                        suppressed_hum = float(parsed_json["hum"])

            payload = TelemetryPayload(
                uptime_ms=uptime_ms,
                ldr_raw=ldr_val,
                x0_raw=x0_val,
                dht_valid=dht_valid_val,
                temp=temp_out,
                hum=hum_out,
                suppressed_temp=suppressed_temp,
                suppressed_hum=suppressed_hum,
            )

        elif msg_type == MessageType.STATUS:
            assert uptime_ms is not None
            expected_status_fields = ("disp", "comp", "fail", "lat_us", "dur_us")
            for field in expected_status_fields:
                if field not in parsed_json:
                    raise MissingFieldError(field, type_val)
                val = parsed_json[field]
                if not _is_int(val):
                    raise FieldTypeError(field, "uint32 integer", val)
                if val < 0 or val > UINT32_MAX:
                    raise FieldRangeError(field, 0, UINT32_MAX, val)

            consumed_keys.update(expected_status_fields)
            payload = StatusPayload(
                uptime_ms=uptime_ms,
                dispatched=parsed_json["disp"],
                completed=parsed_json["comp"],
                failed=parsed_json["fail"],
                max_lat_us=parsed_json["lat_us"],
                max_dur_us=parsed_json["dur_us"],
            )

        elif msg_type == MessageType.EVENT:
            assert uptime_ms is not None
            # 'ev': uint8 (0..255)
            if "ev" not in parsed_json:
                raise MissingFieldError("ev", type_val)
            ev_val = parsed_json["ev"]
            if not _is_int(ev_val):
                raise FieldTypeError("ev", "uint8 integer", ev_val)
            if ev_val < 0 or ev_val > UINT8_MAX:
                raise FieldRangeError("ev", 0, UINT8_MAX, ev_val)

            # 'sev': uint8 (0..255)
            if "sev" not in parsed_json:
                raise MissingFieldError("sev", type_val)
            sev_val = parsed_json["sev"]
            if not _is_int(sev_val):
                raise FieldTypeError("sev", "uint8 integer", sev_val)
            if sev_val < 0 or sev_val > UINT8_MAX:
                raise FieldRangeError("sev", 0, UINT8_MAX, sev_val)

            # 'src': uint16 (0..65535)
            if "src" not in parsed_json:
                raise MissingFieldError("src", type_val)
            src_val = parsed_json["src"]
            if not _is_int(src_val):
                raise FieldTypeError("src", "uint16 integer", src_val)
            if src_val < 0 or src_val > UINT16_MAX:
                raise FieldRangeError("src", 0, UINT16_MAX, src_val)

            # 'val': int32 (-2147483648..2147483647)
            if "val" not in parsed_json:
                raise MissingFieldError("val", type_val)
            val_val = parsed_json["val"]
            if not _is_int(val_val):
                raise FieldTypeError("val", "int32 integer", val_val)
            if val_val < INT32_MIN or val_val > INT32_MAX:
                raise FieldRangeError("val", INT32_MIN, INT32_MAX, val_val)

            consumed_keys.update({"ev", "sev", "src", "val"})
            payload = EventPayload(
                uptime_ms=uptime_ms,
                event_type=ev_val,
                severity=sev_val,
                source_id=src_val,
                payload_val=val_val,
            )

        elif msg_type == MessageType.COMMAND:
            cmd_fields = {k: v for k, v in parsed_json.items() if k not in ("ver", "dev", "seq", "type", "uptime")}
            consumed_keys.update(cmd_fields.keys())
            payload = CommandPayload(
                uptime_ms=uptime_ms,
                fields=MappingProxyType(cmd_fields),
            )

        elif msg_type == MessageType.RESPONSE:
            resp_fields = {k: v for k, v in parsed_json.items() if k not in ("ver", "dev", "seq", "type", "uptime")}
            consumed_keys.update(resp_fields.keys())
            payload = ResponsePayload(
                uptime_ms=uptime_ms,
                fields=MappingProxyType(resp_fields),
            )

        else:
            raise UnknownMessageTypeError(type_val)

        # 5. Extra fields capture (preserves unconsumed fields safely in immutable mapping)
        extra_fields: Dict[str, Any] = {k: v for k, v in parsed_json.items() if k not in consumed_keys}

        return ParsedEnvelope(
            raw_bytes=raw_bytes,
            raw_text=raw_text,
            ver=ver_val,
            dev=dev_val,
            seq=seq_val,
            msg_type=msg_type,
            uptime_ms=uptime_ms,
            payload=payload,
            extra_fields=MappingProxyType(extra_fields),
            raw_dict=MappingProxyType(parsed_json),
        )
