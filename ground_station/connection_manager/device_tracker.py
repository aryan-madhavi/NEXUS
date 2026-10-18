"""NEXUS Device and Transport Identity Tracker.

Maintains strictly observed identity, monotonic timestamps, wall-clock records,
and reception/error counters across physical and logical transports.
Does not fabricate online/offline states, signal quality, or cross-transport deduplication.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .envelope_parser import ParsedEnvelope


@dataclass
class TransportState:
    """Observed state for a specific transport attached to a device or input stream."""

    transport_name: str
    first_seen_monotonic: float
    last_seen_monotonic: float
    last_seen_wallclock: float
    last_valid_monotonic: Optional[float] = None
    last_valid_wallclock: Optional[float] = None
    accepted_count: int = 0
    rejected_count: int = 0
    last_seq: Optional[int] = None
    last_uptime_ms: Optional[int] = None
    last_msg_type: Optional[str] = None
    error_counts: Dict[str, int] = field(default_factory=dict)

    def elapsed_since_last_seen(self, now_monotonic: float) -> float:
        """Return elapsed monotonic seconds since transport was last observed."""
        return max(0.0, now_monotonic - self.last_seen_monotonic)

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable dictionary snapshot."""
        return {
            "transport_name": self.transport_name,
            "first_seen_monotonic": self.first_seen_monotonic,
            "last_seen_monotonic": self.last_seen_monotonic,
            "last_seen_wallclock": self.last_seen_wallclock,
            "last_valid_monotonic": self.last_valid_monotonic,
            "last_valid_wallclock": self.last_valid_wallclock,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "last_seq": self.last_seq,
            "last_uptime_ms": self.last_uptime_ms,
            "last_msg_type": self.last_msg_type,
            "error_counts": dict(self.error_counts),
        }


@dataclass
class DeviceState:
    """Observed state for a logical NEXUS device."""

    device_id: str
    first_seen_monotonic: float
    last_seen_monotonic: float
    last_seen_wallclock: float
    last_valid_monotonic: Optional[float] = None
    last_valid_wallclock: Optional[float] = None
    total_accepted: int = 0
    total_rejected: int = 0
    last_seq: Optional[int] = None
    last_uptime_ms: Optional[int] = None
    transports: Dict[str, TransportState] = field(default_factory=dict)
    last_seq_by_type: Dict[str, int] = field(default_factory=dict)

    def elapsed_since_last_seen(self, now_monotonic: float) -> float:
        """Return elapsed monotonic seconds since device was last observed."""
        return max(0.0, now_monotonic - self.last_seen_monotonic)

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable dictionary snapshot."""
        return {
            "device_id": self.device_id,
            "first_seen_monotonic": self.first_seen_monotonic,
            "last_seen_monotonic": self.last_seen_monotonic,
            "last_seen_wallclock": self.last_seen_wallclock,
            "last_valid_monotonic": self.last_valid_monotonic,
            "last_valid_wallclock": self.last_valid_wallclock,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "last_seq": self.last_seq,
            "last_uptime_ms": self.last_uptime_ms,
            "last_seq_by_type": dict(self.last_seq_by_type),
            "transports": {k: v.to_dict() for k, v in self.transports.items()},
        }


class DeviceTracker:
    """Thread-safe tracker for observed device identities, transports, and telemetry rates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: Dict[str, DeviceState] = {}
        # Global transport registry (tracks unknown-device transport activity)
        self._global_transports: Dict[str, TransportState] = {}
        self._total_accepted = 0
        self._total_rejected = 0
        self._global_error_counts: Counter[str] = Counter()

    def record_valid_envelope(
        self,
        transport_name: str,
        envelope: ParsedEnvelope,
        now_monotonic: Optional[float] = None,
        now_wallclock: Optional[float] = None,
    ) -> None:
        """Record an accepted, validated envelope from a specific transport."""
        m_now = time.monotonic() if now_monotonic is None else now_monotonic
        w_now = time.time() if now_wallclock is None else now_wallclock

        dev_id = envelope.dev
        seq = envelope.seq
        type_str = envelope.msg_type.value
        uptime_ms = envelope.uptime_ms

        with self._lock:
            self._total_accepted += 1

            # 1. Update Global Transport Record
            t_global = self._global_transports.get(transport_name)
            if t_global is None:
                t_global = TransportState(
                    transport_name=transport_name,
                    first_seen_monotonic=m_now,
                    last_seen_monotonic=m_now,
                    last_seen_wallclock=w_now,
                )
                self._global_transports[transport_name] = t_global
            t_global.last_seen_monotonic = m_now
            t_global.last_seen_wallclock = w_now
            t_global.last_valid_monotonic = m_now
            t_global.last_valid_wallclock = w_now
            t_global.accepted_count += 1
            t_global.last_seq = seq
            t_global.last_uptime_ms = uptime_ms
            t_global.last_msg_type = type_str

            # 2. Update Device Record
            dev = self._devices.get(dev_id)
            if dev is None:
                dev = DeviceState(
                    device_id=dev_id,
                    first_seen_monotonic=m_now,
                    last_seen_monotonic=m_now,
                    last_seen_wallclock=w_now,
                )
                self._devices[dev_id] = dev

            dev.last_seen_monotonic = m_now
            dev.last_seen_wallclock = w_now
            dev.last_valid_monotonic = m_now
            dev.last_valid_wallclock = w_now
            dev.total_accepted += 1
            dev.last_seq = seq
            if uptime_ms is not None:
                dev.last_uptime_ms = uptime_ms
            dev.last_seq_by_type[type_str] = seq

            # 3. Update Device-Transport Sub-Record
            t_dev = dev.transports.get(transport_name)
            if t_dev is None:
                t_dev = TransportState(
                    transport_name=transport_name,
                    first_seen_monotonic=m_now,
                    last_seen_monotonic=m_now,
                    last_seen_wallclock=w_now,
                )
                dev.transports[transport_name] = t_dev
            t_dev.last_seen_monotonic = m_now
            t_dev.last_seen_wallclock = w_now
            t_dev.last_valid_monotonic = m_now
            t_dev.last_valid_wallclock = w_now
            t_dev.accepted_count += 1
            t_dev.last_seq = seq
            t_dev.last_uptime_ms = uptime_ms
            t_dev.last_msg_type = type_str

    def record_rejected_envelope(
        self,
        transport_name: str,
        error_category: str,
        now_monotonic: Optional[float] = None,
        now_wallclock: Optional[float] = None,
        device_id: Optional[str] = None,
    ) -> None:
        """Record an unparseable or schema-rejected message."""
        m_now = time.monotonic() if now_monotonic is None else now_monotonic
        w_now = time.time() if now_wallclock is None else now_wallclock

        with self._lock:
            self._total_rejected += 1
            self._global_error_counts[error_category] += 1

            # 1. Update Global Transport Record
            t_global = self._global_transports.get(transport_name)
            if t_global is None:
                t_global = TransportState(
                    transport_name=transport_name,
                    first_seen_monotonic=m_now,
                    last_seen_monotonic=m_now,
                    last_seen_wallclock=w_now,
                )
                self._global_transports[transport_name] = t_global
            t_global.last_seen_monotonic = m_now
            t_global.last_seen_wallclock = w_now
            t_global.rejected_count += 1
            t_global.error_counts[error_category] = (
                t_global.error_counts.get(error_category, 0) + 1
            )

            # 2. Update Device Record if device_id is known or recovered
            if device_id:
                dev = self._devices.get(device_id)
                if dev is None:
                    dev = DeviceState(
                        device_id=device_id,
                        first_seen_monotonic=m_now,
                        last_seen_monotonic=m_now,
                        last_seen_wallclock=w_now,
                    )
                    self._devices[device_id] = dev
                dev.last_seen_monotonic = m_now
                dev.last_seen_wallclock = w_now
                dev.total_rejected += 1

                t_dev = dev.transports.get(transport_name)
                if t_dev is None:
                    t_dev = TransportState(
                        transport_name=transport_name,
                        first_seen_monotonic=m_now,
                        last_seen_monotonic=m_now,
                        last_seen_wallclock=w_now,
                    )
                    dev.transports[transport_name] = t_dev
                t_dev.last_seen_monotonic = m_now
                t_dev.last_seen_wallclock = w_now
                t_dev.rejected_count += 1
                t_dev.error_counts[error_category] = (
                    t_dev.error_counts.get(error_category, 0) + 1
                )

    def get_device(self, device_id: str) -> Optional[DeviceState]:
        """Return a snapshot of the requested device state, or None if unknown."""
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None:
                return None
            # Return a shallow-copied clone to prevent caller mutation
            return DeviceState(
                device_id=dev.device_id,
                first_seen_monotonic=dev.first_seen_monotonic,
                last_seen_monotonic=dev.last_seen_monotonic,
                last_seen_wallclock=dev.last_seen_wallclock,
                last_valid_monotonic=dev.last_valid_monotonic,
                last_valid_wallclock=dev.last_valid_wallclock,
                total_accepted=dev.total_accepted,
                total_rejected=dev.total_rejected,
                last_seq=dev.last_seq,
                last_uptime_ms=dev.last_uptime_ms,
                transports={k: TransportState(**v.__dict__) for k, v in dev.transports.items()},
                last_seq_by_type=dict(dev.last_seq_by_type),
            )

    def get_all_devices(self) -> Dict[str, DeviceState]:
        """Return snapshots of all tracked devices."""
        with self._lock:
            return {
                k: DeviceState(
                    device_id=v.device_id,
                    first_seen_monotonic=v.first_seen_monotonic,
                    last_seen_monotonic=v.last_seen_monotonic,
                    last_seen_wallclock=v.last_seen_wallclock,
                    last_valid_monotonic=v.last_valid_monotonic,
                    last_valid_wallclock=v.last_valid_wallclock,
                    total_accepted=v.total_accepted,
                    total_rejected=v.total_rejected,
                    last_seq=v.last_seq,
                    last_uptime_ms=v.last_uptime_ms,
                    transports={tk: TransportState(**tv.__dict__) for tk, tv in v.transports.items()},
                    last_seq_by_type=dict(v.last_seq_by_type),
                )
                for k, v in self._devices.items()
            }

    def get_transport_summary(self) -> Dict[str, Dict[str, Any]]:
        """Return summary of all registered transports and their message counts."""
        with self._lock:
            return {k: v.to_dict() for k, v in self._global_transports.items()}

    def get_summary(self) -> Dict[str, Any]:
        """Return a high-level summary of device tracker metrics."""
        with self._lock:
            return {
                "total_accepted": self._total_accepted,
                "total_rejected": self._total_rejected,
                "device_count": len(self._devices),
                "devices": list(self._devices.keys()),
                "global_error_counts": dict(self._global_error_counts),
                "transports": {k: v.to_dict() for k, v in self._global_transports.items()},
            }
