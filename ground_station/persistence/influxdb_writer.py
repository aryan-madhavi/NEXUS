"""NEXUS InfluxDB Persistence Writer.

Implements bounded, batched, retry-safe asynchronous persistence of validated
telemetry envelopes to InfluxDB v2 with zero impact on transport I/O callbacks.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS
except ImportError:
    InfluxDBClient = None
    SYNCHRONOUS = None

from ..connection_manager.envelope_parser import ParsedEnvelope
from .base import PersistenceQueuePolicy, PersistenceWriter
from .point_mapper import PointMapper

logger = logging.getLogger("nexus.influxdb_writer")


@dataclass
class InfluxDBConfig:
    """Configuration for InfluxDB persistence writer."""

    url: str = "http://localhost:8086"
    org: str = "nexus"
    bucket: str = "nexus_telemetry"
    token: Optional[str] = None
    timeout_ms: int = 3000
    max_queue_size: int = 1000
    batch_size: int = 50
    flush_interval_sec: float = 1.0
    max_retries: int = 3
    retry_base_delay_sec: float = 0.2
    retry_max_delay_sec: float = 2.0
    queue_policy: PersistenceQueuePolicy = PersistenceQueuePolicy.DROP_NEWEST
    measurement_prefix: str = "nexus"
    use_single_measurement: bool = False
    # Dependency injection for offline unit tests (returns mock client)
    client_factory: Optional[Callable[..., Any]] = None

    def __repr__(self) -> str:
        # Prevent token leakage in logs and tracebacks
        masked_token = "***" if self.token else None
        return (
            f"InfluxDBConfig(url={self.url!r}, org={self.org!r}, bucket={self.bucket!r}, "
            f"token={masked_token!r}, batch_size={self.batch_size}, "
            f"max_queue_size={self.max_queue_size}, timeout_ms={self.timeout_ms}, "
            f"max_retries={self.max_retries})"
        )

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> InfluxDBConfig:
        """Create an InfluxDBConfig instance from environment variables or a dictionary.

        Supported variables:
        - INFLUXDB_URL: Server endpoint URL (default: http://localhost:8086)
        - INFLUXDB_ORG: InfluxDB organization (default: nexus)
        - INFLUXDB_BUCKET: Target telemetry bucket (default: nexus_telemetry)
        - INFLUXDB_TOKEN / INFLUXDB_INIT_ADMIN_TOKEN: Authentication token
        - INFLUXDB_TIMEOUT_MS: Request timeout in milliseconds (default: 3000)
        - INFLUXDB_BATCH_SIZE: Maximum batch size (default: 50)
        - INFLUXDB_FLUSH_INTERVAL_SEC: Periodic flush interval in seconds (default: 1.0)
        - INFLUXDB_MAX_QUEUE_SIZE: Maximum queue capacity (default: 1000)
        - INFLUXDB_MAX_RETRIES: Maximum retry attempts (default: 3)
        - INFLUXDB_RETRY_BASE_DELAY_SEC: Initial retry backoff (default: 0.2)
        - INFLUXDB_RETRY_MAX_DELAY_SEC: Maximum retry backoff ceiling (default: 2.0)
        - INFLUXDB_MEASUREMENT_PREFIX: Prefix for measurements (default: nexus)
        - INFLUXDB_USE_SINGLE_MEASUREMENT: Use single measurement if 'true'
        """
        import os
        from ground_station import load_env_file

        source = {**load_env_file(), **os.environ} if env is None else env
        token = source.get("INFLUXDB_TOKEN") or source.get("INFLUXDB_INIT_ADMIN_TOKEN")
        return cls(
            url=source.get("INFLUXDB_URL", "http://localhost:8086"),
            org=source.get("INFLUXDB_ORG", "nexus"),
            bucket=source.get("INFLUXDB_BUCKET", "nexus_telemetry"),
            token=token,
            timeout_ms=int(source.get("INFLUXDB_TIMEOUT_MS", 3000)),
            max_queue_size=int(source.get("INFLUXDB_MAX_QUEUE_SIZE", 1000)),
            batch_size=int(source.get("INFLUXDB_BATCH_SIZE", 50)),
            flush_interval_sec=float(source.get("INFLUXDB_FLUSH_INTERVAL_SEC", 1.0)),
            max_retries=int(source.get("INFLUXDB_MAX_RETRIES", 3)),
            retry_base_delay_sec=float(source.get("INFLUXDB_RETRY_BASE_DELAY_SEC", 0.2)),
            retry_max_delay_sec=float(source.get("INFLUXDB_RETRY_MAX_DELAY_SEC", 2.0)),
            measurement_prefix=source.get("INFLUXDB_MEASUREMENT_PREFIX", "nexus"),
            use_single_measurement=source.get("INFLUXDB_USE_SINGLE_MEASUREMENT", "").lower() in ("true", "1", "yes"),
        )


@dataclass(frozen=True)
class InfluxDBStats:
    """Telemetry and operational metrics for InfluxDB persistence writer."""

    is_connected: bool
    is_running: bool
    accepted_records: int
    successful_writes: int
    write_failures: int
    retries_attempted: int
    retries_exhausted_drops: int
    queue_drops: int
    malformed_records: int
    queue_size: int
    queue_hwm: int
    last_write_wallclock: Optional[float]
    last_error: Optional[str]
    is_worker_alive: bool = False
    is_shutdown_timed_out: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "accepted_records": self.accepted_records,
            "successful_writes": self.successful_writes,
            "write_failures": self.write_failures,
            "retries_attempted": self.retries_attempted,
            "retries_exhausted_drops": self.retries_exhausted_drops,
            "queue_drops": self.queue_drops,
            "malformed_records": self.malformed_records,
            "queue_size": self.queue_size,
            "queue_hwm": self.queue_hwm,
            "last_write_wallclock": self.last_write_wallclock,
            "last_error": self.last_error,
            "is_worker_alive": self.is_worker_alive,
            "is_shutdown_timed_out": self.is_shutdown_timed_out,
        }


class InfluxDBWriter(PersistenceWriter):
    """Thread-safe InfluxDB v2 writer with bounded queuing, batching, and exponential retries."""

    def __init__(
        self,
        config: Optional[InfluxDBConfig] = None,
        name: str = "influxdb",
    ) -> None:
        self._name = name
        self._config = config or InfluxDBConfig()

        self._queue: queue.Queue[ParsedEnvelope] = queue.Queue(maxsize=self._config.max_queue_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self._client: Optional[Any] = None
        self._write_api: Optional[Any] = None

        self._is_running = False
        self._is_connected = False

        # Accounting statistics
        self._accepted_records = 0
        self._successful_writes = 0
        self._write_failures = 0
        self._retries_attempted = 0
        self._retries_exhausted_drops = 0
        self._queue_drops = 0
        self._malformed_records = 0
        self._queue_hwm = 0
        self._last_write_wallclock: Optional[float] = None
        self._last_error: Optional[str] = None

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

    @property
    def is_worker_alive(self) -> bool:
        """True if the background worker thread is currently active or blocked in I/O."""
        with self._lock:
            return bool(self._worker_thread is not None and self._worker_thread.is_alive())

    @property
    def is_shutdown_timed_out(self) -> bool:
        """True if writer was stopped but previous worker thread is still alive."""
        with self._lock:
            return bool(not self._is_running and self._worker_thread is not None and self._worker_thread.is_alive())

    def start(self) -> None:
        """Initialize InfluxDB client and start the background persistence worker thread.

        Raises:
            RuntimeError: If a previous worker thread from a timed-out shutdown is still alive.
        """
        with self._lock:
            if self._is_running:
                return

            # Prevent starting overlapping workers or sharing queues with a live timed-out worker
            if self._worker_thread is not None:
                if self._worker_thread.is_alive():
                    raise RuntimeError(
                        f"Cannot start InfluxDB writer '{self._name}': previous worker thread "
                        f"'{self._worker_thread.name}' is still alive after timed-out shutdown"
                    )
                self._worker_thread = None
                self._worker_stop_event = None

            self._is_running = True

            stop_event = threading.Event()
            self._worker_stop_event = stop_event
            self._stop_event = stop_event

            try:
                # Initialize client lazily upon start (never on import/construction)
                self._client = self._create_client()
                if hasattr(self._client, "write_api"):
                    # Synchronous write API gives deterministic control to our background worker
                    if SYNCHRONOUS is not None:
                        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
                    else:
                        self._write_api = self._client.write_api()
                else:
                    self._write_api = self._client

                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    args=(stop_event,),
                    name=f"NexusInfluxDBWriter-{self._name}",
                    daemon=True,
                )
                self._worker_thread.start()
            except Exception as init_err:
                self._is_running = False
                if self._client is not None and hasattr(self._client, "close"):
                    try:
                        self._client.close()
                    except Exception:
                        pass
                self._client = None
                self._write_api = None
                self._worker_thread = None
                self._worker_stop_event = None
                logger.error("Failed to start InfluxDB writer '%s': %s", self._name, init_err)
                raise

            logger.info("InfluxDB writer '%s' started (url=%s, bucket=%s)", self._name, self._config.url, self._config.bucket)

    def stop(self, timeout: float = 2.0) -> bool:
        """Deterministically stop worker thread, flush pending records, and close client.

        The timeout bounds caller wait time on worker join. If the worker cannot finish
        flushing within the timeout (e.g. database network hang), the caller proceeds
        to close the client and unblocks at the deadline.

        Returns:
            True if the worker thread completely terminated within timeout; False if
            shutdown timed out and the worker thread remains alive in the background.
        """
        worker = None
        client = None
        with self._lock:
            if not self._is_running:
                # If already stopped, check whether a previously timed-out worker is still running
                if self._worker_thread is not None and self._worker_thread.is_alive():
                    worker = self._worker_thread
                else:
                    self._worker_thread = None
                    self._worker_stop_event = None
                    return True

            if self._is_running:
                self._is_running = False
                if hasattr(self, "_worker_stop_event") and self._worker_stop_event is not None:
                    self._worker_stop_event.set()
                self._stop_event.set()
                worker = self._worker_thread

        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout)

        with self._lock:
            client = self._client
            self._client = None
            self._write_api = None
            self._is_connected = False
            if worker is not None and not worker.is_alive():
                self._worker_thread = None
                self._worker_stop_event = None

        if client is not None:
            try:
                if hasattr(client, "close"):
                    client.close()
            except Exception as err:
                logger.debug("Error closing InfluxDB client: %s", err)

        worker_alive = bool(worker is not None and worker.is_alive())
        if worker_alive:
            logger.warning(
                "InfluxDB writer '%s' stop timed out after %.2fs; worker thread '%s' still alive",
                self._name,
                timeout,
                worker.name if worker else "unknown",
            )
            return False

        logger.info("InfluxDB writer '%s' stopped", self._name)
        return True

    def write_envelope(self, envelope: ParsedEnvelope) -> bool:
        """Non-blocking submission of a validated envelope into the bounded persistence queue.

        Safe to invoke directly from host-manager ingestion callbacks.
        Never executes network operations or blocks the caller.
        """
        with self._lock:
            if not self._is_running:
                return False

            if self._config.queue_policy == PersistenceQueuePolicy.DROP_NEWEST:
                try:
                    self._queue.put_nowait(envelope)
                    self._accepted_records += 1
                    q_len = self._queue.qsize()
                    if q_len > self._queue_hwm:
                        self._queue_hwm = q_len
                    return True
                except queue.Full:
                    self._queue_drops += 1
                    logger.debug("Persistence queue full; dropped newest envelope seq=%s", envelope.seq)
                    return False

            elif self._config.queue_policy == PersistenceQueuePolicy.DROP_OLDEST:
                try:
                    self._queue.put_nowait(envelope)
                    self._accepted_records += 1
                    q_len = self._queue.qsize()
                    if q_len > self._queue_hwm:
                        self._queue_hwm = q_len
                    return True
                except queue.Full:
                    # Evict oldest item to make space
                    try:
                        self._queue.get_nowait()
                        self._queue_drops += 1
                    except queue.Empty:
                        pass

                    try:
                        self._queue.put_nowait(envelope)
                        self._accepted_records += 1
                        q_len = self._queue.qsize()
                        if q_len > self._queue_hwm:
                            self._queue_hwm = q_len
                        return True
                    except queue.Full:
                        self._queue_drops += 1
                        return False
            else:
                self._queue_drops += 1
                return False

    def _create_client(self) -> Any:
        """Create InfluxDB client instance, supporting dependency injection."""
        if self._config.client_factory is not None:
            return self._config.client_factory(self._config)

        if InfluxDBClient is None:
            raise ImportError(
                "influxdb-client is required for InfluxDBWriter; install via ground_station/requirements.txt"
            )

        return InfluxDBClient(
            url=self._config.url,
            token=self._config.token,
            org=self._config.org,
            timeout=self._config.timeout_ms,
        )

    def _worker_loop(self, stop_event: Optional[threading.Event] = None) -> None:
        """Background worker thread draining persistence queue and writing in batches."""
        active_stop_event = stop_event or self._stop_event
        batch: List[ParsedEnvelope] = []
        last_flush_monotonic = time.monotonic()

        while not active_stop_event.is_set():
            # Calculate remaining time until periodic flush interval
            elapsed = time.monotonic() - last_flush_monotonic
            remaining = max(0.01, self._config.flush_interval_sec - elapsed)

            try:
                # Wait for at least one item up to remaining interval
                item = self._queue.get(timeout=min(0.1, remaining))
                batch.append(item)
            except queue.Empty:
                pass

            # Pull any additional items currently sitting in queue up to batch_size
            while len(batch) < self._config.batch_size and not self._queue.empty():
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            # Flush condition: batch threshold reached or flush interval elapsed
            should_flush = len(batch) >= self._config.batch_size or (
                len(batch) > 0 and (time.monotonic() - last_flush_monotonic) >= self._config.flush_interval_sec
            )

            if should_flush:
                self._process_and_write_batch(batch, active_stop_event)
                batch.clear()
                last_flush_monotonic = time.monotonic()

        # Draining phase on shutdown: flush any remaining items in queue
        drain_batch: List[ParsedEnvelope] = list(batch)
        with self._lock:
            api_closed = (self._write_api is None)

        if api_closed:
            # Client closed / caller deadline expired: drop remaining queued records
            dropped_count = 0
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    dropped_count += 1
                except queue.Empty:
                    break
            with self._lock:
                self._retries_exhausted_drops += (len(drain_batch) + dropped_count)
            drain_batch.clear()
        else:
            while not self._queue.empty():
                with self._lock:
                    api_closed = (self._write_api is None)
                if api_closed:
                    dropped_count = 0
                    while not self._queue.empty():
                        try:
                            self._queue.get_nowait()
                            dropped_count += 1
                        except queue.Empty:
                            break
                    with self._lock:
                        self._retries_exhausted_drops += (len(drain_batch) + dropped_count)
                    drain_batch.clear()
                    break

                try:
                    drain_batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
                if len(drain_batch) >= self._config.batch_size:
                    self._process_and_write_batch(drain_batch, active_stop_event)
                    drain_batch.clear()

            if drain_batch:
                self._process_and_write_batch(drain_batch, active_stop_event)

    def _process_and_write_batch(
        self,
        batch: List[ParsedEnvelope],
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Map envelopes to points and commit batch with bounded retries."""
        if not batch:
            return

        points: List[Any] = []
        for env in batch:
            try:
                p = PointMapper.to_point(
                    envelope=env,
                    measurement_prefix=self._config.measurement_prefix,
                    use_single_measurement=self._config.use_single_measurement,
                )
                points.append(p)
            except Exception as map_err:
                with self._lock:
                    self._malformed_records += 1
                logger.error("Failed to map envelope seq=%s to InfluxDB point: %s", getattr(env, "seq", None), map_err)

        if not points:
            return

        self._flush_points_with_retry(points, stop_event)

    def _flush_points_with_retry(
        self,
        points: List[Any],
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        """Flush points with bounded exponential backoff and error accounting."""
        write_api = None
        with self._lock:
            write_api = self._write_api

        if write_api is None:
            with self._lock:
                self._retries_exhausted_drops += len(points)
                self._write_failures += 1
            return False

        delay = self._config.retry_base_delay_sec
        active_stop_event = stop_event or self._stop_event

        for attempt in range(self._config.max_retries + 1):
            try:
                write_api.write(
                    bucket=self._config.bucket,
                    org=self._config.org,
                    record=points,
                )
                with self._lock:
                    self._successful_writes += len(points)
                    self._last_write_wallclock = time.time()
                    self._is_connected = True
                return True
            except Exception as err:
                with self._lock:
                    self._write_failures += 1
                    self._last_error = str(err)
                    self._is_connected = False

                if attempt < self._config.max_retries:
                    with self._lock:
                        self._retries_attempted += 1
                    logger.warning(
                        "InfluxDB write attempt %d failed: %s; retrying in %.2fs",
                        attempt + 1,
                        err,
                        delay,
                    )
                    # Interruptible sleep
                    if active_stop_event.wait(delay):
                        break
                    delay = min(delay * 2.0, self._config.retry_max_delay_sec)
                else:
                    with self._lock:
                        self._retries_exhausted_drops += len(points)
                    logger.error(
                        "InfluxDB write permanently failed after %d retries; dropped %d records: %s",
                        self._config.max_retries,
                        len(points),
                        err,
                    )
                    return False

        # If interrupted by stop_event during retries
        with self._lock:
            self._retries_exhausted_drops += len(points)
        return False

    def get_stats(self) -> InfluxDBStats:
        """Return an immutable snapshot of InfluxDB persistence telemetry."""
        with self._lock:
            worker_alive = bool(self._worker_thread is not None and self._worker_thread.is_alive())
            shutdown_timed_out = bool(not self._is_running and worker_alive)
            return InfluxDBStats(
                is_connected=self._is_connected,
                is_running=self._is_running,
                accepted_records=self._accepted_records,
                successful_writes=self._successful_writes,
                write_failures=self._write_failures,
                retries_attempted=self._retries_attempted,
                retries_exhausted_drops=self._retries_exhausted_drops,
                queue_drops=self._queue_drops,
                malformed_records=self._malformed_records,
                queue_size=self._queue.qsize(),
                queue_hwm=self._queue_hwm,
                last_write_wallclock=self._last_write_wallclock,
                last_error=self._last_error,
                is_worker_alive=worker_alive,
                is_shutdown_timed_out=shutdown_timed_out,
            )
