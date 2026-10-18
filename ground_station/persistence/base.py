"""NEXUS Persistence Base Protocols and Enumerations.

Defines the abstract interface for downstream persistence writers and queue overflow policies.
"""

from __future__ import annotations

import abc
import enum
from typing import Any

from ..connection_manager.envelope_parser import ParsedEnvelope


class PersistenceQueuePolicy(enum.Enum):
    """Overflow policy when a bounded persistence queue reaches capacity."""

    DROP_NEWEST = "drop_newest"
    DROP_OLDEST = "drop_oldest"


class PersistenceWriter(abc.ABC):
    """Abstract base protocol for NEXUS host persistence writers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this persistence writer instance."""

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """True if the writer background worker thread is active."""

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool:
        """True if the database client is initialized and connected."""

    @abc.abstractmethod
    def start(self) -> None:
        """Initialize database client and start background worker thread."""

    @abc.abstractmethod
    def stop(self, timeout: float = 2.0) -> bool:
        """Cleanly flush remaining records within timeout and stop worker thread.

        Returns:
            True if worker thread cleanly terminated within timeout; False if shutdown timed out.
        """

    @abc.abstractmethod
    def write_envelope(self, envelope: ParsedEnvelope) -> bool:
        """Non-blocking submission of a validated envelope to the bounded persistence queue.

        Returns:
            True if envelope was queued; False if rejected or dropped due to queue overflow.
        """

    @abc.abstractmethod
    def get_stats(self) -> Any:
        """Return an immutable snapshot of persistence writer statistics."""
