"""NEXUS Connection Manager and Protocol Parser module."""

from .device_tracker import DeviceState, DeviceTracker, TransportState
from .envelope_parser import (
    CommandPayload,
    EnvelopeParseError,
    EnvelopeParser,
    EnvelopePayload,
    EventPayload,
    FieldRangeError,
    FieldTypeError,
    HeartbeatPayload,
    MalformedJsonError,
    MessageType,
    MissingFieldError,
    OversizedEnvelopeError,
    ParsedEnvelope,
    ResponsePayload,
    StatusPayload,
    TelemetryPayload,
    UnknownMessageTypeError,
    UnsupportedVersionError,
)
from .mqtt_adapter import MqttConfig, MqttStats, MqttTransportAdapter
from .nexus_host_manager import (
    HostManagerStats,
    NexusHostManager,
    QueueFullPolicy,
    TransportAdapter,
)
from .serial_adapter import SerialConfig, SerialStats, SerialTransportAdapter

__all__ = [
    # Envelope parser
    "EnvelopeParser",
    "MessageType",
    "ParsedEnvelope",
    "EnvelopePayload",
    "HeartbeatPayload",
    "TelemetryPayload",
    "StatusPayload",
    "EventPayload",
    "CommandPayload",
    "ResponsePayload",
    # Parser Exceptions
    "EnvelopeParseError",
    "OversizedEnvelopeError",
    "MalformedJsonError",
    "UnsupportedVersionError",
    "UnknownMessageTypeError",
    "MissingFieldError",
    "FieldTypeError",
    "FieldRangeError",
    # Device tracker
    "DeviceTracker",
    "DeviceState",
    "TransportState",
    # Host connection manager
    "NexusHostManager",
    "TransportAdapter",
    "QueueFullPolicy",
    "HostManagerStats",
    # Serial transport adapter
    "SerialConfig",
    "SerialStats",
    "SerialTransportAdapter",
    # MQTT transport adapter
    "MqttConfig",
    "MqttStats",
    "MqttTransportAdapter",
]
