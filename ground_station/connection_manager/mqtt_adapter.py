"""NEXUS MQTT Transport Adapter.

Subscribes to NEXUS device telemetry topics using Paho MQTT.
Enforces topic validation, device identity consistency, non-blocking callback paths,
and graceful reconnect/shutdown lifecycle management.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Union

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from .nexus_host_manager import TransportAdapter

logger = logging.getLogger("nexus.mqtt_adapter")

# Default topic for NEXUS telemetry publishes: nexus/<device_id>/telemetry
DEFAULT_SUBSCRIPTION_TOPIC = "nexus/+/telemetry"
DEFAULT_TOPIC_REGEX = r"^nexus/(?P<device_id>[^/]+)/telemetry$"


@dataclass
class MqttConfig:
    """Configuration for NEXUS MQTT Transport Adapter."""

    host: str = "localhost"
    port: int = 1883
    client_id: str = "nexus_ground_station"
    keepalive_sec: int = 60
    username: Optional[str] = None
    password: Optional[str] = None
    topic_subscription: str = DEFAULT_SUBSCRIPTION_TOPIC
    topic_regex_pattern: str = DEFAULT_TOPIC_REGEX
    # Optional dependency injection for unit tests
    client_factory: Optional[Callable[..., Any]] = None

    def __repr__(self) -> str:
        # Prevent password leakage in logs and tracebacks
        masked_pw = "***" if self.password else None
        return (
            f"MqttConfig(host={self.host!r}, port={self.port}, "
            f"client_id={self.client_id!r}, keepalive_sec={self.keepalive_sec}, "
            f"username={self.username!r}, password={masked_pw!r}, "
            f"topic_subscription={self.topic_subscription!r})"
        )

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> MqttConfig:
        """Create an MqttConfig instance from environment variables or a dictionary.

        Supported variables:
        - MQTT_HOST: Broker address (default: localhost)
        - MQTT_PORT: Broker TCP port (default: 1883)
        - MQTT_CLIENT_ID: Client identifier (default: nexus_ground_station)
        - MQTT_KEEPALIVE_SEC: Keepalive ping interval in seconds (default: 60)
        - MQTT_USERNAME: Optional username
        - MQTT_PASSWORD: Optional password (masked in repr)
        - MQTT_TOPIC_SUBSCRIPTION: Subscription topic filter (default: nexus/+/telemetry)
        - MQTT_TOPIC_REGEX: Regular expression for parsing topic device IDs
        """
        source = os.environ if env is None else env

        def _get_str(key: str, default: Optional[str] = None) -> Optional[str]:
            val = source.get(key)
            if val is not None and val != "":
                return val
            return default

        def _get_int(key: str, default: int) -> int:
            val = source.get(key)
            if val is not None and val != "":
                try:
                    return int(val)
                except ValueError:
                    return default
            return default

        return cls(
            host=_get_str("MQTT_HOST", "localhost") or "localhost",
            port=_get_int("MQTT_PORT", 1883),
            client_id=_get_str("MQTT_CLIENT_ID", "nexus_ground_station") or "nexus_ground_station",
            keepalive_sec=_get_int("MQTT_KEEPALIVE_SEC", 60),
            username=_get_str("MQTT_USERNAME", None),
            password=_get_str("MQTT_PASSWORD", None),
            topic_subscription=_get_str("MQTT_TOPIC_SUBSCRIPTION", DEFAULT_SUBSCRIPTION_TOPIC) or DEFAULT_SUBSCRIPTION_TOPIC,
            topic_regex_pattern=_get_str("MQTT_TOPIC_REGEX", DEFAULT_TOPIC_REGEX) or DEFAULT_TOPIC_REGEX,
        )


@dataclass(frozen=True)
class MqttStats:
    """Telemetry snapshot for MQTT transport."""

    is_connected: bool
    connect_count: int
    disconnect_count: int
    messages_received: int
    messages_forwarded: int
    topic_mismatch_errors: int
    identity_mismatch_errors: int
    subscription_errors: int
    io_errors: int
    last_message_monotonic: Optional[float]
    last_message_wallclock: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_connected": self.is_connected,
            "connect_count": self.connect_count,
            "disconnect_count": self.disconnect_count,
            "messages_received": self.messages_received,
            "messages_forwarded": self.messages_forwarded,
            "topic_mismatch_errors": self.topic_mismatch_errors,
            "identity_mismatch_errors": self.identity_mismatch_errors,
            "subscription_errors": self.subscription_errors,
            "io_errors": self.io_errors,
            "last_message_monotonic": self.last_message_monotonic,
            "last_message_wallclock": self.last_message_wallclock,
        }


class MqttTransportAdapter(TransportAdapter):
    """Paho MQTT transport adapter for NEXUS host ground station."""

    def __init__(
        self,
        config: Optional[MqttConfig] = None,
        name: str = "mqtt",
    ) -> None:
        self._name = name
        self._config = config or MqttConfig()
        self._topic_regex = re.compile(self._config.topic_regex_pattern)

        self._is_running = False
        self._is_connected = False
        self._on_receive: Optional[Callable[[str, Union[bytes, str]], None]] = None

        self._client: Optional[Any] = None
        self._lock = threading.Lock()

        # Telemetry metrics
        self._connect_count = 0
        self._disconnect_count = 0
        self._messages_received = 0
        self._messages_forwarded = 0
        self._topic_mismatch_errors = 0
        self._identity_mismatch_errors = 0
        self._subscription_errors = 0
        self._io_errors = 0
        self._last_message_monotonic: Optional[float] = None
        self._last_message_wallclock: Optional[float] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def start(self, on_receive: Callable[[str, Union[bytes, str]], None]) -> None:
        """Initialize and connect MQTT client; starts background network loop."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._on_receive = on_receive

            client = self._create_client()
            self._client = client

        try:
            if self._config.username:
                client.username_pw_set(self._config.username, self._config.password)

            client.connect_async(
                host=self._config.host,
                port=self._config.port,
                keepalive=self._config.keepalive_sec,
            )
            client.loop_start()
            logger.info("MQTT transport started (broker=%s:%d)", self._config.host, self._config.port)
        except Exception as err:
            with self._lock:
                self._io_errors += 1
            logger.error("Failed to start MQTT connection: %s", err)

    def stop(self) -> None:
        """Cleanly and deterministically disconnect and stop MQTT network loop."""
        client = None
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            self._is_connected = False
            client = self._client
            self._client = None

        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as err:
                logger.debug("Error during MQTT disconnect: %s", err)

    def _create_client(self) -> Any:
        """Create Paho MQTT Client supporting CallbackAPIVersion.VERSION2."""
        factory = self._config.client_factory
        if factory is not None:
            client = factory(self._config.client_id)
        else:
            if mqtt is None:
                raise ImportError("paho-mqtt is required for MqttTransportAdapter; install via ground_station/requirements.txt")
            if hasattr(mqtt, "CallbackAPIVersion"):
                client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=self._config.client_id,
                )
            else:
                client = mqtt.Client(client_id=self._config.client_id)

        # Wire callbacks
        client.on_connect = self._on_connect_callback
        client.on_disconnect = self._on_disconnect_callback
        client.on_subscribe = self._on_subscribe_callback
        client.on_message = self._on_message_callback
        return client

    def _on_connect_callback(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        """Handle MQTT connection established event."""
        # Handle both Paho v1 (int rc) and v2 (ReasonCode object)
        rc_val = getattr(reason_code, "value", reason_code)
        if rc_val == 0:
            with self._lock:
                self._is_connected = True
                self._connect_count += 1
            logger.info("MQTT connected to broker; subscribing to %s", self._config.topic_subscription)
            try:
                client.subscribe(self._config.topic_subscription, qos=1)
            except Exception as err:
                with self._lock:
                    self._subscription_errors += 1
                logger.error("Failed to subscribe to %s: %s", self._config.topic_subscription, err)
        else:
            with self._lock:
                self._is_connected = False
                self._io_errors += 1
            logger.warning("MQTT connection failed with reason_code=%s", reason_code)

    def _on_disconnect_callback(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags_or_rc: Any = None,
        reason_code: Any = None,
        properties: Any = None,
    ) -> None:
        """Handle MQTT disconnect event."""
        with self._lock:
            self._is_connected = False
            self._disconnect_count += 1
        logger.info("MQTT disconnected from broker")

    def _on_subscribe_callback(
        self,
        client: Any,
        userdata: Any,
        mid: Any,
        reason_codes: Any = None,
        properties: Any = None,
    ) -> None:
        """Handle subscription confirmation."""
        # If reason_codes present, check for failure
        if reason_codes is not None:
            # Paho v2 returns a list of ReasonCodes
            codes = reason_codes if isinstance(reason_codes, list) else [reason_codes]
            for code in codes:
                val = getattr(code, "value", code)
                if val >= 128:  # 0x80 or higher indicates failure in MQTT v5
                    with self._lock:
                        self._subscription_errors += 1
                    logger.error("MQTT subscription rejected with reason_code=%s", code)
                    return
        logger.debug("MQTT subscription confirmed (mid=%s)", mid)

    def _on_message_callback(
        self,
        client: Any,
        userdata: Any,
        message: Any,
    ) -> None:
        """Process incoming MQTT message payload with topic validation and identity checks."""
        m_now = time.monotonic()
        w_now = time.time()
        topic = message.topic
        payload = message.payload

        with self._lock:
            if not self._is_running:
                return
            self._messages_received += 1
            self._last_message_monotonic = m_now
            self._last_message_wallclock = w_now

        # 1. Validate Topic Structure
        match = self._topic_regex.match(topic)
        if not match:
            with self._lock:
                self._topic_mismatch_errors += 1
            logger.debug("Ignored message on unexpected MQTT topic: %s", topic)
            return

        topic_dev_id = match.group("device_id")

        # 2. Validate Payload Device Identity Consistency
        # To avoid unbounded payload logging or duplicate full parsing, perform lightweight extraction
        try:
            raw_text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
            # Lightweight search for "dev": "<dev_id>"
            dev_match = re.search(r'"dev"\s*:\s*"([^"]+)"', raw_text)
            if dev_match:
                payload_dev_id = dev_match.group(1)
                if payload_dev_id != topic_dev_id:
                    with self._lock:
                        self._identity_mismatch_errors += 1
                    logger.warning(
                        "MQTT identity mismatch: topic dev='%s' but payload dev='%s'; discarding message",
                        topic_dev_id,
                        payload_dev_id,
                    )
                    return
        except Exception as err:
            logger.debug("Failed device identity check on topic %s: %s", topic, err)

        # 3. Forward complete payload non-blockingly to host manager
        callback = self._on_receive
        if callback:
            try:
                callback(self._name, payload)
                with self._lock:
                    self._messages_forwarded += 1
            except Exception as err:
                logger.error("Error in MQTT on_receive callback: %s", err)

    def publish_command(self, topic: str, payload: Union[str, bytes], qos: int = 1) -> bool:
        """Publish a command envelope to an ESP32 command topic."""
        with self._lock:
            client = self._client
            connected = self._is_connected
        if not connected or client is None:
            logger.warning("Cannot publish command: MQTT transport is not connected")
            return False

        try:
            res = client.publish(topic, payload, qos=qos)
            res.wait_for_publish(timeout=2.0)
            return True
        except Exception as err:
            logger.error("Failed to publish command to MQTT topic %s: %s", topic, err)
            with self._lock:
                self._io_errors += 1
            return False

    def get_stats(self) -> MqttStats:
        """Return a snapshot of MQTT adapter telemetry."""
        with self._lock:
            return MqttStats(
                is_connected=self._is_connected,
                connect_count=self._connect_count,
                disconnect_count=self._disconnect_count,
                messages_received=self._messages_received,
                messages_forwarded=self._messages_forwarded,
                topic_mismatch_errors=self._topic_mismatch_errors,
                identity_mismatch_errors=self._identity_mismatch_errors,
                subscription_errors=self._subscription_errors,
                io_errors=self._io_errors,
                last_message_monotonic=self._last_message_monotonic,
                last_message_wallclock=self._last_message_wallclock,
            )
