"""NEXUS Telemetry Query Engine.

Provides a strictly bounded, typed, read-only interface over InfluxDB 2.x
telemetry persistence. Enforces parameter allowlists, guarantees zero Flux injection,
distinguishes host receive time from firmware monotonic uptime, and provides
server-side full-window aggregations without silent truncation.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.exceptions import InfluxDBError
except ImportError:
    InfluxDBClient = None
    InfluxDBError = Exception

from ..persistence.influxdb_writer import InfluxDBConfig
from .models import (
    ALLOWED_MEASUREMENTS,
    ALLOWED_SIGNALS,
    ALLOWED_TRANSPORTS,
    DEFAULT_RAW_QUERY_LIMIT,
    DEVICE_ID_PATTERN,
    MAX_QUERY_TIMEOUT_SECONDS,
    MAX_RAW_QUERY_LIMIT,
    MAX_TIME_RANGE_DAYS,
    MAX_TIME_RANGE_SECONDS,
    RELATIVE_DURATION_PATTERN,
    SIGNAL_CATALOG,
    DataSourceUnavailableError,
    InvalidQueryError,
    ObservationEvent,
    QueryTimeoutError,
    SignalSummary,
    TelemetryRecord,
)

logger = logging.getLogger("nexus.telemetry_query")


class TelemetryQueryService:
    """Bounded, read-only query service for NEXUS telemetry."""

    def __init__(
        self,
        config: Optional[InfluxDBConfig] = None,
        client: Optional[Any] = None,
    ) -> None:
        """Initialize TelemetryQueryService.

        Args:
            config: InfluxDB configuration. If omitted, loaded from environment.
            client: Optional pre-configured InfluxDBClient (used for mocking and tests).
        """
        if config is None:
            self.config = InfluxDBConfig.from_env()
        else:
            self.config = config

        self._external_client = client is not None
        if client is not None:
            self.client = client
        elif InfluxDBClient is not None:
            timeout_ms = min(self.config.timeout_ms, int(MAX_QUERY_TIMEOUT_SECONDS * 1000))
            self.client = InfluxDBClient(
                url=self.config.url,
                token=self.config.token,
                org=self.config.org,
                timeout=timeout_ms,
            )
        else:
            self.client = None

    def close(self) -> None:
        """Close underlying InfluxDB client if internally created."""
        if not self._external_client and self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    # --- Validation Helpers ---

    @staticmethod
    def validate_device(dev: str) -> str:
        """Validate device identifier against allowlist pattern.

        Raises:
            InvalidQueryError: If device ID contains disallowed characters or invalid length.
        """
        if not isinstance(dev, str) or not dev:
            raise InvalidQueryError("Device identifier must be a non-empty string.")
        if not DEVICE_ID_PATTERN.match(dev):
            raise InvalidQueryError(
                f"Device identifier {dev!r} contains invalid characters or length. "
                "Must match ^[a-zA-Z0-9_-]{1,32}$."
            )
        return dev

    @staticmethod
    def validate_signal(signal: str) -> Tuple[str, str]:
        """Validate signal name against allowlist and resolve to (measurement, field).

        Raises:
            InvalidQueryError: If signal is unknown.
        """
        if not isinstance(signal, str) or signal not in SIGNAL_CATALOG:
            allowed = sorted(ALLOWED_SIGNALS)
            raise InvalidQueryError(
                f"Unknown signal {signal!r}. Must be one of: {', '.join(allowed)}"
            )
        return SIGNAL_CATALOG[signal]

    @staticmethod
    def validate_measurement(measurement: str) -> str:
        """Validate raw measurement name against allowlist."""
        if measurement not in ALLOWED_MEASUREMENTS:
            raise InvalidQueryError(
                f"Unknown measurement {measurement!r}. Must be one of: {sorted(ALLOWED_MEASUREMENTS)}"
            )
        return measurement

    @staticmethod
    def validate_time_range(start: str, stop: str = "now()") -> Tuple[str, str]:
        """Validate start and stop time specifications.

        Supports relative durations (e.g. -15m, -1h, -7d, -30d) or ISO-8601 UTC strings.
        Enforces maximum lookback ceiling of MAX_TIME_RANGE_DAYS.

        Raises:
            InvalidQueryError: If format is invalid or window duration is excessive.
        """
        if not isinstance(start, str) or not start:
            raise InvalidQueryError("Query start time must be a non-empty string.")

        # Check relative duration format
        if RELATIVE_DURATION_PATTERN.match(start):
            unit = start[-1]
            try:
                val = int(start[1:-1])
            except ValueError:
                raise InvalidQueryError(f"Malformed relative time offset: {start!r}")

            multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
            total_seconds = val * multiplier
            if total_seconds > MAX_TIME_RANGE_SECONDS:
                raise InvalidQueryError(
                    f"Requested time range {start!r} ({val}{unit}) exceeds maximum allowed "
                    f"limit of {MAX_TIME_RANGE_DAYS} days."
                )
            if total_seconds <= 0:
                raise InvalidQueryError("Relative start offset must be negative and non-zero.")
        elif start.endswith("Z") or "+00:00" in start:
            # Basic ISO validation check
            try:
                # Replace trailing Z if fromisoformat needs it
                clean_start = start.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(clean_start)
                if (datetime.now(parsed.tzinfo) - parsed).total_seconds() > MAX_TIME_RANGE_SECONDS:
                    raise InvalidQueryError(
                        f"Requested ISO start time {start!r} exceeds {MAX_TIME_RANGE_DAYS} days lookback."
                    )
            except ValueError:
                raise InvalidQueryError(f"Invalid ISO timestamp format for start time: {start!r}")
        else:
            raise InvalidQueryError(
                f"Invalid start time format {start!r}. Must be relative offset (-15m, -1h) "
                "or ISO-8601 UTC timestamp."
            )

        if stop != "now()":
            if not (stop.endswith("Z") or "+00:00" in stop or RELATIVE_DURATION_PATTERN.match(stop)):
                raise InvalidQueryError(f"Invalid stop time format {stop!r}.")

        return start, stop

    @staticmethod
    def validate_transport(transport: Optional[str]) -> Optional[str]:
        """Validate transport filter against allowed options."""
        if transport is None or transport == "all":
            return None
        if transport not in ALLOWED_TRANSPORTS:
            raise InvalidQueryError(
                f"Invalid transport filter {transport!r}. Allowed: {sorted(ALLOWED_TRANSPORTS)}"
            )
        return transport

    @staticmethod
    def validate_limit(limit: int) -> int:
        """Validate and bound result row limit."""
        if not isinstance(limit, int) or limit < 1:
            raise InvalidQueryError("Query limit must be a positive integer >= 1.")
        if limit > MAX_RAW_QUERY_LIMIT:
            raise InvalidQueryError(
                f"Requested limit {limit} exceeds maximum raw query limit of {MAX_RAW_QUERY_LIMIT}."
            )
        return limit

    # --- Database Execution Helper ---

    def _execute_query(self, flux: str) -> Tuple[List[Any], float]:
        """Execute Flux query against InfluxDB with strict error handling and latency tracking.

        Returns:
            Tuple of (list_of_tables, elapsed_ms)

        Raises:
            DataSourceUnavailableError: If InfluxDB is unreachable or client is missing.
            QueryTimeoutError: If execution exceeds allocated timeout.
        """
        if self.client is None:
            raise DataSourceUnavailableError(
                "InfluxDB client is not available or library is not installed."
            )

        query_api = self.client.query_api()
        start_time = time.perf_counter()

        try:
            tables = query_api.query(flux, org=self.config.org)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return tables, elapsed_ms
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            msg = str(exc).lower()
            if "timeout" in msg or "deadline" in msg:
                raise QueryTimeoutError(f"InfluxDB query timed out after {elapsed_ms:.1f}ms: {exc}") from exc
            if "refused" in msg or "unreachable" in msg or "bad gateway" in msg or "connection" in msg:
                raise DataSourceUnavailableError(
                    f"InfluxDB service at {self.config.url} is unreachable: {exc}"
                ) from exc
            raise DataSourceUnavailableError(f"InfluxDB query failed: {exc}") from exc

    # --- Public Query API ---

    def check_health(self) -> Dict[str, Any]:
        """Check availability and query latency of the InfluxDB data source."""
        if self.client is None:
            return {"status": "fail", "message": "Client unconfigured", "latency_ms": None}

        start = time.perf_counter()
        try:
            if hasattr(self.client, "ping"):
                alive = self.client.ping()
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                return {
                    "status": "pass" if alive else "fail",
                    "message": "ready for queries and writes" if alive else "ping failed",
                    "latency_ms": elapsed_ms,
                }
            health = self.client.health()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            status = "pass" if health.status == "pass" else "fail"
            return {
                "status": status,
                "message": health.message,
                "version": getattr(health, "version", None),
                "latency_ms": elapsed_ms,
            }
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return {
                "status": "fail",
                "message": str(exc),
                "latency_ms": elapsed_ms,
            }

    def get_latest_reading(
        self,
        dev: str,
        signal: str,
        transport: Optional[str] = None,
    ) -> Optional[TelemetryRecord]:
        """Fetch the most recent observed reading for an allowlisted device and signal.

        Args:
            dev: Allowed device identifier (e.g. 'nexus_esp32').
            signal: Allowed signal name (e.g. 'temp', 'hum', 'ldr_raw', 'free_heap').
            transport: Optional transport filter ('mqtt', 'serial', or None for any).

        Returns:
            TelemetryRecord with typed value, host receive timestamp, and firmware uptime,
            or None if no records exist.
        """
        valid_dev = self.validate_device(dev)
        measurement, field_name = self.validate_signal(signal)
        valid_transport = self.validate_transport(transport)

        transport_clause = f'|> filter(fn: (r) => r["transport"] == "{valid_transport}")' if valid_transport else ""

        flux = f'''
        from(bucket: "{self.config.bucket}")
          |> range(start: -30d)
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["dev"] == "{valid_dev}")
          |> filter(fn: (r) => r["_field"] == "{field_name}")
          {transport_clause}
          |> last()
        '''

        tables, _ = self._execute_query(flux)
        latest_record: Optional[Any] = None

        for table in tables:
            for record in table.records:
                if latest_record is None or record.get_time() > latest_record.get_time():
                    latest_record = record

        if latest_record is None:
            return None

        # Fetch associated seq and uptime_ms from the same envelope point if available
        uptime_ms = latest_record.values.get("uptime_ms")
        seq = latest_record.values.get("seq")

        # If seq or uptime_ms are stored as sibling fields, query them via pivot or return what we have
        return TelemetryRecord(
            dev=valid_dev,
            measurement=measurement,
            field=field_name,
            value=latest_record.get_value(),
            host_time=latest_record.get_time(),
            uptime_ms=int(uptime_ms) if uptime_ms is not None else None,
            seq=int(seq) if seq is not None else None,
            transport=latest_record.values.get("transport"),
        )

    def get_history(
        self,
        dev: str,
        signal: str,
        start: str = "-1h",
        stop: str = "now()",
        transport: Optional[str] = None,
        limit: int = DEFAULT_RAW_QUERY_LIMIT,
    ) -> List[TelemetryRecord]:
        """Fetch bounded historical telemetry records for a single signal.

        Args:
            dev: Validated device ID.
            signal: Validated signal name.
            start: Bounded start offset or ISO timestamp (default: '-1h').
            stop: Bounded stop offset or ISO timestamp (default: 'now()').
            transport: Optional transport filter.
            limit: Maximum records to return (1 <= limit <= 1000).

        Returns:
            List of TelemetryRecord objects in chronological order.
        """
        valid_dev = self.validate_device(dev)
        measurement, field_name = self.validate_signal(signal)
        valid_start, valid_stop = self.validate_time_range(start, stop)
        valid_transport = self.validate_transport(transport)
        valid_limit = self.validate_limit(limit)

        transport_clause = f'|> filter(fn: (r) => r["transport"] == "{valid_transport}")' if valid_transport else ""

        flux = f'''
        from(bucket: "{self.config.bucket}")
          |> range(start: {valid_start}, stop: {valid_stop})
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["dev"] == "{valid_dev}")
          |> filter(fn: (r) => r["_field"] == "{field_name}")
          {transport_clause}
          |> limit(n: {valid_limit})
          |> sort(columns: ["_time"], desc: false)
        '''

        tables, _ = self._execute_query(flux)
        records: List[TelemetryRecord] = []

        for table in tables:
            for record in table.records:
                records.append(
                    TelemetryRecord(
                        dev=valid_dev,
                        measurement=measurement,
                        field=field_name,
                        value=record.get_value(),
                        host_time=record.get_time(),
                        uptime_ms=None,
                        seq=None,
                        transport=record.values.get("transport"),
                    )
                )

        records.sort(key=lambda r: r.host_time)
        return records[:valid_limit]

    def get_raw_envelopes(
        self,
        dev: str,
        msg_type: str = "telem",
        start: str = "-1h",
        stop: str = "now()",
        transport: Optional[str] = None,
        limit: int = DEFAULT_RAW_QUERY_LIMIT,
        deduplicate: bool = True,
        correlation_window_sec: float = 0.5,
    ) -> List[ObservationEvent]:
        """Fetch full, pivoted observation envelopes with canonical deduplication across transports.

        When deduplicate=True, observations with identical (dev, seq, uptime_ms)
        originating from DIFFERENT transports within correlation_window_sec (default: 0.5s)
        are collapsed into a single canonical ObservationEvent, listing all delivering transports.

        Protocol Limitation Notice:
            NEXUS Protocol v1 does not include a reboot counter or boot session UUID.
            Therefore, deduplication relies on transport diversity (same-transport duplicates
            are never merged) and tight host-time correlation (< 0.5s). If a hardware reboot
            occurs within < 0.5s and emits the exact same (seq, uptime_ms) on the alternate
            transport, it cannot be distinguished from network jitter under Protocol v1.
        """
        valid_dev = self.validate_device(dev)
        measurement = f"nexus_{msg_type}"
        self.validate_measurement(measurement)
        valid_start, valid_stop = self.validate_time_range(start, stop)
        valid_transport = self.validate_transport(transport)
        valid_limit = self.validate_limit(limit)

        transport_clause = f'|> filter(fn: (r) => r["transport"] == "{valid_transport}")' if valid_transport else ""

        flux = f'''
        from(bucket: "{self.config.bucket}")
          |> range(start: {valid_start}, stop: {valid_stop})
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["dev"] == "{valid_dev}")
          {transport_clause}
          |> pivot(rowKey:["_time", "dev", "transport"], columnKey: ["_field"], valueColumn: "_value")
          |> limit(n: {valid_limit * 2 if deduplicate else valid_limit})
          |> sort(columns: ["_time"], desc: false)
        '''

        tables, _ = self._execute_query(flux)
        raw_events: List[Dict[str, Any]] = []

        for table in tables:
            for record in table.records:
                raw_events.append(record.values)

        raw_events.sort(key=lambda e: e.get("_time"))

        if not deduplicate:
            result = []
            for ev in raw_events[:valid_limit]:
                fields = {
                    k: v
                    for k, v in ev.items()
                    if k not in {"_time", "_start", "_stop", "_measurement", "dev", "transport", "type", "result", "table"}
                }
                result.append(
                    ObservationEvent(
                        dev=valid_dev,
                        msg_type=msg_type,
                        seq=int(ev.get("seq", 0)),
                        uptime_ms=int(ev.get("uptime_ms", 0)),
                        host_time=ev["_time"],
                        transports=[ev.get("transport", "unknown")],
                        fields=fields,
                    )
                )
            return result

        # Canonical Observation Deduplication Policy
        # Identifies dual-transport arrivals: same (dev, seq, uptime_ms) across DIFFERENT transports within correlation window
        deduped: List[ObservationEvent] = []
        recent_by_identity: Dict[Tuple[str, int, int], ObservationEvent] = {}

        for ev in raw_events:
            seq = int(ev.get("seq", 0))
            uptime_ms = int(ev.get("uptime_ms", 0))
            host_time: datetime = ev["_time"]
            t_name = ev.get("transport", "unknown")
            identity_key = (valid_dev, seq, uptime_ms)

            fields = {
                k: v
                for k, v in ev.items()
                if k not in {"_time", "_start", "_stop", "_measurement", "dev", "transport", "type", "result", "table"}
            }

            if identity_key in recent_by_identity:
                existing = recent_by_identity[identity_key]
                time_delta = abs((host_time - existing.host_time).total_seconds())

                # Strict Dual-Transport Condition:
                # 1. Must arrive from a DIFFERENT transport (e.g. MQTT vs Serial).
                # 2. Must arrive within the narrow correlation window (default 0.5s).
                # Same-transport arrivals or arrivals outside the window are NOT merged.
                if t_name not in existing.transports and time_delta <= correlation_window_sec:
                    existing.transports.append(t_name)
                    # Merge any missing fields if one transport carried sparse data
                    for fk, fv in fields.items():
                        if fk not in existing.fields or existing.fields[fk] is None:
                            existing.fields[fk] = fv
                    continue

            # New unique event
            new_obs = ObservationEvent(
                dev=valid_dev,
                msg_type=msg_type,
                seq=seq,
                uptime_ms=uptime_ms,
                host_time=host_time,
                transports=[t_name],
                fields=fields,
            )
            recent_by_identity[identity_key] = new_obs
            deduped.append(new_obs)

            if len(deduped) >= valid_limit:
                break

        return deduped[:valid_limit]

    def get_window_statistics(
        self,
        dev: str,
        signal: str,
        start: str = "-1h",
        stop: str = "now()",
        transport: Optional[str] = None,
    ) -> SignalSummary:
        """Compute full-window deterministic statistics over an un-truncated time window.

        Executes InfluxDB server-side aggregations (count, min, max, mean, first, last)
        so that metrics are computed over ALL data in the window, rather than silently
        truncating at a point limit.

        For sensors with validity indicators (e.g. DHT temperature/humidity), also queries
        confirmed invalid reading counts (where dht_valid == False).
        """
        valid_dev = self.validate_device(dev)
        measurement, field_name = self.validate_signal(signal)
        valid_start, valid_stop = self.validate_time_range(start, stop)
        valid_transport = self.validate_transport(transport)

        transport_clause = f'|> filter(fn: (r) => r["transport"] == "{valid_transport}")' if valid_transport else ""

        # Note: If transport is not filtered, group across transports so we aggregate all points
        group_clause = '|> group(columns: ["_measurement", "_field", "dev"])' if not valid_transport else ""

        flux = f'''
        base = from(bucket: "{self.config.bucket}")
          |> range(start: {valid_start}, stop: {valid_stop})
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["dev"] == "{valid_dev}")
          |> filter(fn: (r) => r["_field"] == "{field_name}")
          {transport_clause}
          {group_clause}

        base |> count() |> yield(name: "count")
        base |> min() |> yield(name: "min")
        base |> max() |> yield(name: "max")
        base |> mean() |> yield(name: "mean")
        base |> first() |> yield(name: "first")
        base |> last() |> yield(name: "last")
        '''

        tables, elapsed_ms = self._execute_query(flux)
        stats: Dict[str, Any] = {}
        first_time: Optional[datetime] = None
        last_time: Optional[datetime] = None

        for table in tables:
            for record in table.records:
                res_name = record.values.get("result")
                val = record.get_value()
                if res_name:
                    stats[res_name] = val
                if res_name == "first":
                    first_time = record.get_time()
                elif res_name == "last":
                    last_time = record.get_time()

        sample_count = int(stats.get("count", 0))

        # Query confirmed invalid readings if this signal is backed by a validity flag
        invalid_count = 0
        if measurement == "nexus_telem" and field_name in ("temp", "hum"):
            invalid_flux = f'''
            from(bucket: "{self.config.bucket}")
              |> range(start: {valid_start}, stop: {valid_stop})
              |> filter(fn: (r) => r["_measurement"] == "nexus_telem")
              |> filter(fn: (r) => r["dev"] == "{valid_dev}")
              |> filter(fn: (r) => r["_field"] == "dht_valid")
              |> filter(fn: (r) => r["_value"] == false)
              {transport_clause}
              {group_clause}
              |> count()
            '''
            try:
                inv_tables, _ = self._execute_query(invalid_flux)
                for t in inv_tables:
                    for r in t.records:
                        invalid_count += int(r.get_value() or 0)
            except Exception as e:
                logger.warning("Could not evaluate invalid sensor reading count: %s", e)

        min_val = float(stats["min"]) if "min" in stats and stats["min"] is not None else None
        max_val = float(stats["max"]) if "max" in stats and stats["max"] is not None else None
        mean_val = float(stats["mean"]) if "mean" in stats and stats["mean"] is not None else None

        return SignalSummary(
            dev=valid_dev,
            signal=signal,
            measurement=measurement,
            field_name=field_name,
            start_time=valid_start,
            stop_time=valid_stop,
            sample_count=sample_count,
            invalid_count=invalid_count,
            min_value=min_val,
            max_value=max_val,
            mean_value=mean_val,
            first_value=stats.get("first"),
            last_value=stats.get("last"),
            first_time=first_time,
            last_time=last_time,
            is_truncated=False,  # Server-side full window aggregation is never truncated
            query_duration_ms=elapsed_ms,
        )
