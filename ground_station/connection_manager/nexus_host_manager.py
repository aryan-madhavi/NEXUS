"""NEXUS Host Connection Manager.

Manages input transports, strict envelope parsing, device tracking, and bounded
downstream handoff queues with explicit drop/overflow accounting and isolated error handling.
"""

from __future__ import annotations

import abc
import enum
import logging
import queue
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Union

from .device_tracker import DeviceTracker
from .envelope_parser import EnvelopeParseError, EnvelopeParser, ParsedEnvelope

logger = logging.getLogger("nexus.host_manager")


class QueueFullPolicy(enum.Enum):
    """Policy executed when the bounded downstream ingestion queue is at capacity."""

    DROP_NEWEST = "drop_newest"
    DROP_OLDEST = "drop_oldest"


class TransportAdapter(abc.ABC):
    """Abstract interface for NEXUS transport adapters (Serial, MQTT, Fake/Simulated)."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique transport identifier (e.g. 'serial', 'mqtt', 'fake_transport')."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """True if the transport adapter is actively reading/receiving data."""
        raise NotImplementedError

    @abc.abstractmethod
    def start(self, on_receive: Callable[[str, Union[bytes, str]], None]) -> None:
        """Start receiving and forward incoming raw frames to on_receive(transport_name, data)."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self) -> None:
        """Cleanly stop receiving and release transport resources."""
        raise NotImplementedError


@dataclass(frozen=True)
class HostManagerStats:
    """Thread-safe snapshot of Host Connection Manager telemetry and queue metrics."""

    is_running: bool
    messages_received: int
    messages_parsed: int
    parse_errors: int
    enqueued_count: int
    dropped_count: int
    dequeued_count: int
    queue_size: int
    queue_capacity: int
    queue_hwm: int
    queue_policy: str
    transports: Dict[str, Dict[str, Any]]
    device_summary: Dict[str, Any]
    adapters: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class NexusHostManager:
    """Host Connection Manager coordinating transports, envelope parsing, and bounded handoff."""

    def __init__(
        self,
        queue_capacity: int = 100,
        queue_policy: QueueFullPolicy = QueueFullPolicy.DROP_NEWEST,
        parser: Optional[EnvelopeParser] = None,
        tracker: Optional[DeviceTracker] = None,
    ) -> None:
        if queue_capacity <= 0:
            raise ValueError(f"queue_capacity must be a positive integer, got {queue_capacity}")

        self._queue_capacity = queue_capacity
        self._queue_policy = queue_policy
        self._parser = parser or EnvelopeParser()
        self._tracker = tracker or DeviceTracker()

        self._queue: queue.Queue[ParsedEnvelope] = queue.Queue(maxsize=queue_capacity)
        self._adapters: Dict[str, TransportAdapter] = {}
        self._consumers: List[Callable[[ParsedEnvelope], None]] = []
        self._is_running = False
        self._lock = threading.Lock()

        # Ingestion metrics
        self._messages_received = 0
        self._messages_parsed = 0
        self._parse_errors = 0
        self._enqueued_count = 0
        self._dropped_count = 0
        self._dequeued_count = 0
        self._queue_hwm = 0

    @property
    def queue_capacity(self) -> int:
        """Maximum depth of the bounded ingestion queue."""
        return self._queue_capacity

    @property
    def queue_policy(self) -> QueueFullPolicy:
        """Queue overflow handling policy."""
        return self._queue_policy

    @property
    def is_running(self) -> bool:
        """True if the host manager is in active running state."""
        with self._lock:
            return self._is_running

    @property
    def tracker(self) -> DeviceTracker:
        """Reference to the internal device tracker."""
        return self._tracker

    def register_consumer(self, consumer: Callable[[ParsedEnvelope], None]) -> None:
        """Register a non-blocking consumer callback invoked upon valid envelope ingestion."""
        with self._lock:
            if consumer not in self._consumers:
                self._consumers.append(consumer)

    def unregister_consumer(self, consumer: Callable[[ParsedEnvelope], None]) -> None:
        """Unregister a downstream consumer callback."""
        with self._lock:
            if consumer in self._consumers:
                self._consumers.remove(consumer)

    def register_transport(self, adapter: TransportAdapter) -> None:
        """Register a transport adapter with the manager.

        If the manager is already running, starts the adapter immediately.
        """
        with self._lock:
            if adapter.name in self._adapters:
                raise ValueError(f"Transport adapter '{adapter.name}' is already registered")
            self._adapters[adapter.name] = adapter
            should_start = self._is_running

        if should_start:
            adapter.start(self.handle_raw_message)

    def register_adapter(self, name_or_adapter: Any, adapter: Optional[TransportAdapter] = None) -> None:
        """Backwards-compatible adapter registration supporting both (adapter) and (name, adapter)."""
        target = adapter if adapter is not None else name_or_adapter
        self.register_transport(target)

    def unregister_transport(self, name: str) -> None:
        """Stop and remove a registered transport adapter."""
        adapter: Optional[TransportAdapter] = None
        with self._lock:
            adapter = self._adapters.pop(name, None)

        if adapter and adapter.is_running:
            adapter.stop()

    def unregister_adapter(self, name: str) -> None:
        """Backwards-compatible adapter unregistration."""
        self.unregister_transport(name)

    def get_adapter(self, name: str) -> Optional[TransportAdapter]:
        """Retrieve a registered transport adapter by name."""
        with self._lock:
            return self._adapters.get(name)

    def start(self) -> None:
        """Start the host connection manager and all registered transport adapters."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            adapters_to_start = list(self._adapters.values())

        for adapter in adapters_to_start:
            try:
                adapter.start(self.handle_raw_message)
            except Exception as err:
                logger.error(
                    "Failed to start transport adapter '%s': %s",
                    adapter.name,
                    err,
                )

    def stop(self, timeout: float = 2.0) -> None:
        """Stop all registered transport adapters and mark manager as stopped.

        Idempotent: safe to call repeatedly.
        """
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            adapters_to_stop = list(self._adapters.values())

        for adapter in adapters_to_stop:
            try:
                adapter.stop()
            except Exception as err:
                logger.error(
                    "Error stopping transport adapter '%s': %s",
                    adapter.name,
                    err,
                )

    def handle_raw_message(self, transport_name: str, raw_data: Union[bytes, str]) -> bool:
        """Process an incoming raw wire-format envelope from a transport callback.

        Guarantees:
        - Non-blocking execution suitable for transport I/O callbacks.
        - Isolates errors: malformed or malicious payloads never raise exceptions.
        - Strict bounded queue handoff with explicit drop accounting.

        Returns:
            True if envelope was parsed and enqueued; False if rejected or dropped.
        """
        m_now = time.monotonic()
        w_now = time.time()

        with self._lock:
            if not self._is_running:
                return False
            self._messages_received += 1

        # 1. Parse and strictly validate envelope
        try:
            parsed = self._parser.parse(raw_data)
        except EnvelopeParseError as err:
            with self._lock:
                self._parse_errors += 1

            self._tracker.record_rejected_envelope(
                transport_name=transport_name,
                error_category=err.category,
                now_monotonic=m_now,
                now_wallclock=w_now,
            )
            return False
        except Exception as err:
            with self._lock:
                self._parse_errors += 1

            self._tracker.record_rejected_envelope(
                transport_name=transport_name,
                error_category="unexpected_parser_error",
                now_monotonic=m_now,
                now_wallclock=w_now,
            )
            logger.debug("Unexpected parsing error on transport '%s': %s", transport_name, err)
            return False

        # 2. Attach transport provenance and receive timestamp
        parsed = replace(parsed, transport=transport_name, received_at=w_now)

        # 3. Record accepted envelope in device tracker
        with self._lock:
            self._messages_parsed += 1

        self._tracker.record_valid_envelope(
            transport_name=transport_name,
            envelope=parsed,
            now_monotonic=m_now,
            now_wallclock=w_now,
        )

        # 4. Non-blocking enqueue to bounded downstream queue
        enqueued = self._enqueue_envelope(parsed)

        # 5. Non-blocking dispatch to registered downstream consumers
        with self._lock:
            consumers = list(self._consumers)
        for consumer in consumers:
            try:
                consumer(parsed)
            except Exception as c_err:
                logger.error("Error in downstream consumer callback: %s", c_err)

        return enqueued

    def _enqueue_envelope(self, envelope: ParsedEnvelope) -> bool:
        """Enqueue an envelope into the bounded queue according to the configured policy."""
        with self._lock:
            if self._queue_policy == QueueFullPolicy.DROP_NEWEST:
                try:
                    self._queue.put_nowait(envelope)
                    self._enqueued_count += 1
                    current_size = self._queue.qsize()
                    if current_size > self._queue_hwm:
                        self._queue_hwm = current_size
                    return True
                except queue.Full:
                    self._dropped_count += 1
                    return False

            elif self._queue_policy == QueueFullPolicy.DROP_OLDEST:
                try:
                    self._queue.put_nowait(envelope)
                    self._enqueued_count += 1
                    current_size = self._queue.qsize()
                    if current_size > self._queue_hwm:
                        self._queue_hwm = current_size
                    return True
                except queue.Full:
                    # Drop oldest entry to make room
                    try:
                        self._queue.get_nowait()
                        self._dropped_count += 1
                    except queue.Empty:
                        pass

                    try:
                        self._queue.put_nowait(envelope)
                        self._enqueued_count += 1
                        current_size = self._queue.qsize()
                        if current_size > self._queue_hwm:
                            self._queue_hwm = current_size
                        return True
                    except queue.Full:
                        self._dropped_count += 1
                        return False
            else:
                self._dropped_count += 1
                return False

    def get_envelope(self, timeout: Optional[float] = None) -> Optional[ParsedEnvelope]:
        """Retrieve next validated envelope from bounded ingestion queue.

        Args:
            timeout: Maximum seconds to block waiting for an item. None blocks indefinitely.

        Returns:
            ParsedEnvelope or None if timed out.
        """
        try:
            item = self._queue.get(block=True, timeout=timeout)
            with self._lock:
                self._dequeued_count += 1
            return item
        except queue.Empty:
            return None

    def get_envelope_nowait(self) -> Optional[ParsedEnvelope]:
        """Poll next validated envelope non-blockingly.

        Returns:
            ParsedEnvelope or None if queue is currently empty.
        """
        try:
            item = self._queue.get_nowait()
            with self._lock:
                self._dequeued_count += 1
            return item
        except queue.Empty:
            return None

    def send_command(
        self,
        command_payload: Union[str, bytes, Dict[str, Any]],
        target_device: str = "nexus_esp32",
        transport_preference: str = "auto",
    ) -> bool:
        """Route and send an outbound command envelope to an ESP32 device."""
        if isinstance(command_payload, dict):
            import json
            raw_str = json.dumps(command_payload, separators=(",", ":"))
        elif isinstance(command_payload, bytes):
            raw_str = command_payload.decode("utf-8", errors="replace")
        else:
            raw_str = str(command_payload)

        with self._lock:
            adapters = dict(self._adapters)

        # 1. Direct serial preference
        if transport_preference == "serial":
            ser = adapters.get("serial")
            if ser and hasattr(ser, "send_frame"):
                return bool(ser.send_frame(raw_str))
            logger.warning("Serial transport preferred but unavailable")
            return False

        # 2. Direct mqtt preference
        if transport_preference == "mqtt":
            mq = adapters.get("mqtt")
            if mq and hasattr(mq, "publish_command"):
                return bool(mq.publish_command(f"nexus/{target_device}/cmd", raw_str))
            logger.warning("MQTT transport preferred but unavailable")
            return False

        # 3. Auto preference: prefer connected serial, then connected mqtt
        ser = adapters.get("serial")
        if ser and getattr(ser, "is_connected", False) and hasattr(ser, "send_frame"):
            if ser.send_frame(raw_str):
                return True

        mq = adapters.get("mqtt")
        if mq and getattr(mq, "is_connected", False) and hasattr(mq, "publish_command"):
            if mq.publish_command(f"nexus/{target_device}/cmd", raw_str):
                return True

        # Fallback to any adapter with send capability
        for name, adp in adapters.items():
            if hasattr(adp, "send_frame"):
                if adp.send_frame(raw_str):
                    return True
            elif hasattr(adp, "publish_command"):
                if adp.publish_command(f"nexus/{target_device}/cmd", raw_str):
                    return True

        logger.warning("No active transport connected to deliver command payload")
        return False

    def get_stats(self) -> HostManagerStats:
        """Return an immutable telemetry snapshot of the connection manager."""
        with self._lock:
            adapter_stats: Dict[str, Dict[str, Any]] = {}
            for name, adapter in self._adapters.items():
                if hasattr(adapter, "get_stats"):
                    st = adapter.get_stats()
                    adapter_stats[name] = st.to_dict() if hasattr(st, "to_dict") else vars(st)

            return HostManagerStats(
                is_running=self._is_running,
                messages_received=self._messages_received,
                messages_parsed=self._messages_parsed,
                parse_errors=self._parse_errors,
                enqueued_count=self._enqueued_count,
                dropped_count=self._dropped_count,
                dequeued_count=self._dequeued_count,
                queue_size=self._queue.qsize(),
                queue_capacity=self._queue_capacity,
                queue_hwm=self._queue_hwm,
                queue_policy=self._queue_policy.value,
                transports=self._tracker.get_transport_summary(),
                device_summary=self._tracker.get_summary(),
                adapters=adapter_stats,
            )
