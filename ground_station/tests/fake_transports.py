"""Fake Transport Adapters for NEXUS Host Ground Station testing.

Provides fully deterministic, isolated in-memory transport adapters without
touching physical hardware, serial ports, or network brokers.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Union

from ground_station.connection_manager.nexus_host_manager import TransportAdapter


class FakeTransport(TransportAdapter):
    """Synchronous in-memory fake transport for deterministic unit tests."""

    def __init__(self, name: str = "fake_serial") -> None:
        self._name = name
        self._is_running = False
        self._on_receive: Optional[Callable[[str, Union[bytes, str]], None]] = None
        self._messages_sent: List[Union[bytes, str]] = []
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def start(self, on_receive: Callable[[str, Union[bytes, str]], None]) -> None:
        with self._lock:
            self._is_running = True
            self._on_receive = on_receive

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
            self._on_receive = None

    def feed(self, data: Union[bytes, str]) -> None:
        """Feed a synthetic raw envelope into the transport receive callback."""
        callback = None
        with self._lock:
            if not self._is_running:
                raise RuntimeError(f"Cannot feed data to stopped transport '{self._name}'")
            callback = self._on_receive
            self._messages_sent.append(data)

        if callback:
            callback(self._name, data)

    def feed_batch(self, items: List[Union[bytes, str]]) -> None:
        """Feed a sequence of raw envelopes."""
        for item in items:
            self.feed(item)

    @property
    def messages_sent(self) -> List[Union[bytes, str]]:
        with self._lock:
            return list(self._messages_sent)


class AsyncThreadedFakeTransport(TransportAdapter):
    """Threaded in-memory fake transport for concurrency and shutdown testing."""

    def __init__(self, name: str = "fake_async_producer") -> None:
        self._name = name
        self._is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_receive: Optional[Callable[[str, Union[bytes, str]], None]] = None
        self._items_to_emit: List[Union[bytes, str]] = []
        self._lock = threading.Lock()
        self._emitted_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def emitted_count(self) -> int:
        with self._lock:
            return self._emitted_count

    def schedule_payloads(self, payloads: List[Union[bytes, str]]) -> None:
        """Schedule a list of payloads to be asynchronously emitted upon start."""
        with self._lock:
            self._items_to_emit.extend(payloads)

    def start(self, on_receive: Callable[[str, Union[bytes, str]], None]) -> None:
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._on_receive = on_receive
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker,
                name=f"Worker-{self._name}",
                daemon=True,
            )
            self._thread.start()

    def _worker(self) -> None:
        idx = 0
        while not self._stop_event.is_set():
            payload = None
            callback = None
            with self._lock:
                if idx < len(self._items_to_emit):
                    payload = self._items_to_emit[idx]
                    idx += 1
                    callback = self._on_receive
                else:
                    break

            if callback and payload is not None:
                callback(self._name, payload)
                with self._lock:
                    self._emitted_count += 1

            time.sleep(0.001)  # Micro-yield for scheduler interleaving

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._is_running = False
            t = self._thread
            self._thread = None

        if t and t.is_alive():
            t.join(timeout=1.0)
