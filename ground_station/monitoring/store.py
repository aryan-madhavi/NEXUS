"""NEXUS SQLite Incident and History Store.

Implements durable, transactional persistence for incidents and their state transitions.
Guarantees:
- Schema initialization is idempotent and migration-safe.
- Active incidents are deduplicated at the schema level via a partial unique index on (device_id, rule_id).
- State transitions are recorded atomically with incident state updates.
- 90-day retention cleanup prunes eligible resolved records in bounded transactions
  and NEVER removes active incidents.
- Explicit error handling ensures failures are surfaced without pretending persistence succeeded.
- Reentrant lock ensures thread safety across background scheduler and API readers.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .models import (
    Incident,
    IncidentSeverity,
    IncidentState,
    IncidentTransition,
    utc_now,
)

logger = logging.getLogger("nexus.monitoring.store")


class IncidentStorageError(Exception):
    """Raised when an error occurs during incident persistence operations."""


def _parse_utc_iso(val: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string into a timezone-aware UTC datetime."""
    if not val:
        return None
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO-8601 UTC string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class IncidentStore:
    """Thread-safe SQLite storage engine for durable incidents and transitions."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Initialize IncidentStore.

        Args:
            db_path: Path to SQLite file, or ':memory:' for transient/test instances.
        """
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self.init_schema()

    def _connect(self) -> None:
        """Establish SQLite connection with WAL mode and foreign key constraints."""
        try:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0,
            )
            self._conn.row_factory = sqlite3.Row
            with self._conn:
                self._conn.execute("PRAGMA foreign_keys = ON;")
                # Use WAL journal mode for file-based DBs for better concurrency
                if self.db_path != ":memory:":
                    self._conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.Error as e:
            logger.error("Failed to connect to SQLite at %s: %s", self.db_path, e)
            raise IncidentStorageError(f"Failed to connect to SQLite at {self.db_path}: {e}") from e

    def close(self) -> None:
        """Close SQLite database connection safely."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception as e:
                    logger.warning("Error closing SQLite connection: %s", e)
                finally:
                    self._conn = None

    def init_schema(self) -> None:
        """Initialize database schema, tables, and indexes idempotently."""
        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                with self._conn:
                    # 1. Incidents table
                    self._conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS incidents (
                            incident_id TEXT PRIMARY KEY,
                            device_id TEXT NOT NULL,
                            rule_id TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            state TEXT NOT NULL,
                            summary TEXT NOT NULL,
                            opened_at TEXT NOT NULL,
                            resolved_at TEXT,
                            last_evaluated_at TEXT NOT NULL,
                            open_evidence TEXT NOT NULL,
                            resolve_evidence TEXT
                        );
                        """
                    )

                    # 2. Durable transition history
                    self._conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS incident_transitions (
                            transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            incident_id TEXT NOT NULL,
                            from_state TEXT,
                            to_state TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            evidence TEXT NOT NULL,
                            FOREIGN KEY (incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
                        );
                        """
                    )

                    # 3. Partial unique index to strictly prevent duplicate active incidents
                    self._conn.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_incidents
                        ON incidents(device_id, rule_id)
                        WHERE state = 'OPEN';
                        """
                    )

                    # 4. Query optimization indexes
                    self._conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_incidents_lookup
                        ON incidents(device_id, rule_id, state);
                        """
                    )
                    self._conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_incidents_retention
                        ON incidents(state, resolved_at);
                        """
                    )
                    self._conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_transitions_incident
                        ON incident_transitions(incident_id, timestamp);
                        """
                    )
            except sqlite3.Error as e:
                logger.error("Failed to initialize incident store schema: %s", e)
                raise IncidentStorageError(f"Failed to initialize schema: {e}") from e

    def _row_to_incident(self, row: sqlite3.Row) -> Incident:
        """Convert a database row into an Incident dataclass."""
        open_ev = {}
        if row["open_evidence"]:
            try:
                open_ev = json.loads(row["open_evidence"])
            except Exception:
                open_ev = {"raw": row["open_evidence"]}

        resolve_ev = None
        if row["resolve_evidence"]:
            try:
                resolve_ev = json.loads(row["resolve_evidence"])
            except Exception:
                resolve_ev = {"raw": row["resolve_evidence"]}

        return Incident(
            incident_id=row["incident_id"],
            device_id=row["device_id"],
            rule_id=row["rule_id"],
            severity=IncidentSeverity(row["severity"]),
            state=IncidentState(row["state"]),
            summary=row["summary"],
            opened_at=_parse_utc_iso(row["opened_at"]) or utc_now(),
            resolved_at=_parse_utc_iso(row["resolved_at"]),
            last_evaluated_at=_parse_utc_iso(row["last_evaluated_at"]),
            open_evidence=open_ev,
            resolve_evidence=resolve_ev,
        )

    def _row_to_transition(self, row: sqlite3.Row) -> IncidentTransition:
        """Convert a database row into an IncidentTransition dataclass."""
        ev = {}
        if row["evidence"]:
            try:
                ev = json.loads(row["evidence"])
            except Exception:
                ev = {"raw": row["evidence"]}

        return IncidentTransition(
            transition_id=row["transition_id"],
            incident_id=row["incident_id"],
            from_state=row["from_state"],
            to_state=row["to_state"],
            timestamp=_parse_utc_iso(row["timestamp"]) or utc_now(),
            reason=row["reason"],
            evidence=ev,
        )

    def get_active_incident(self, device_id: str, rule_id: str) -> Optional[Incident]:
        """Fetch active (OPEN) incident for a specific device and rule if one exists."""
        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                cursor = self._conn.execute(
                    """
                    SELECT * FROM incidents
                    WHERE device_id = ? AND rule_id = ? AND state = 'OPEN'
                    LIMIT 1;
                    """,
                    (device_id, rule_id),
                )
                row = cursor.fetchone()
                return self._row_to_incident(row) if row else None
            except sqlite3.Error as e:
                logger.error("Error fetching active incident (%s, %s): %s", device_id, rule_id, e)
                raise IncidentStorageError(f"Error fetching active incident: {e}") from e

    def get_active_incidents(self, device_id: Optional[str] = None) -> List[Incident]:
        """Fetch all currently OPEN incidents, optionally filtered by device."""
        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                if device_id:
                    cursor = self._conn.execute(
                        """
                        SELECT * FROM incidents
                        WHERE state = 'OPEN' AND device_id = ?
                        ORDER BY opened_at DESC;
                        """,
                        (device_id,),
                    )
                else:
                    cursor = self._conn.execute(
                        """
                        SELECT * FROM incidents
                        WHERE state = 'OPEN'
                        ORDER BY opened_at DESC;
                        """
                    )
                return [self._row_to_incident(r) for r in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error("Error fetching active incidents: %s", e)
                raise IncidentStorageError(f"Error fetching active incidents: {e}") from e

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Fetch incident by unique incident_id."""
        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                cursor = self._conn.execute(
                    "SELECT * FROM incidents WHERE incident_id = ? LIMIT 1;",
                    (incident_id,),
                )
                row = cursor.fetchone()
                return self._row_to_incident(row) if row else None
            except sqlite3.Error as e:
                logger.error("Error fetching incident %s: %s", incident_id, e)
                raise IncidentStorageError(f"Error fetching incident: {e}") from e

    def get_incident_history(
        self,
        device_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
    ) -> List[Incident]:
        """Query bounded incident history with optional filters."""
        limit = max(1, min(limit, 1000))
        query = "SELECT * FROM incidents WHERE 1=1"
        params: List[Any] = []

        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        if rule_id:
            query += " AND rule_id = ?"
            params.append(rule_id)
        if state:
            query += " AND state = ?"
            params.append(state.upper())

        query += " ORDER BY opened_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                cursor = self._conn.execute(query, params)
                return [self._row_to_incident(r) for r in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error("Error querying incident history: %s", e)
                raise IncidentStorageError(f"Error querying incident history: {e}") from e

    def get_incident_transitions(self, incident_id: str) -> List[IncidentTransition]:
        """Retrieve ordered durable transitions for a specific incident."""
        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                cursor = self._conn.execute(
                    """
                    SELECT * FROM incident_transitions
                    WHERE incident_id = ?
                    ORDER BY transition_id ASC;
                    """,
                    (incident_id,),
                )
                return [self._row_to_transition(r) for r in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error("Error fetching transitions for %s: %s", incident_id, e)
                raise IncidentStorageError(f"Error fetching transitions: {e}") from e

    def open_incident(
        self,
        device_id: str,
        rule_id: str,
        severity: IncidentSeverity,
        summary: str,
        open_evidence: Dict[str, Any],
        reason: str = "Condition confirmed",
        opened_at: Optional[datetime] = None,
    ) -> Incident:
        """Open a new incident or return the existing active incident.

        Deduplication behavior:
        - If an OPEN incident already exists for (device_id, rule_id), its last_evaluated_at
          timestamp is refreshed, and the existing incident is returned without creating
          a duplicate incident record or transition.
        - If no OPEN incident exists, a new unique incident_id is allocated, persisted in
          incidents, and an OPEN transition is atomically recorded in incident_transitions.
        """
        now = opened_at or utc_now()
        now_iso = _to_utc_iso(now)

        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")

            # Check for existing active incident first
            existing = self.get_active_incident(device_id, rule_id)
            if existing is not None:
                # Update last_evaluated_at
                try:
                    with self._conn:
                        self._conn.execute(
                            "UPDATE incidents SET last_evaluated_at = ? WHERE incident_id = ?;",
                            (now_iso, existing.incident_id),
                        )
                    return self.get_incident(existing.incident_id) or existing
                except sqlite3.Error as e:
                    logger.error("Failed to update active incident evaluation time: %s", e)
                    raise IncidentStorageError(f"Failed to touch active incident: {e}") from e

            # Create new incident
            unique_suffix = uuid.uuid4().hex[:8]
            time_tag = now.strftime("%Y%m%dT%H%M%SZ")
            incident_id = f"inc_{rule_id}_{device_id}_{time_tag}_{unique_suffix}"
            evidence_json = json.dumps(open_evidence, default=str)

            try:
                with self._conn:
                    self._conn.execute(
                        """
                        INSERT INTO incidents (
                            incident_id, device_id, rule_id, severity, state, summary,
                            opened_at, resolved_at, last_evaluated_at, open_evidence, resolve_evidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL);
                        """,
                        (
                            incident_id,
                            device_id,
                            rule_id,
                            severity.value,
                            IncidentState.OPEN.value,
                            summary,
                            now_iso,
                            now_iso,
                            evidence_json,
                        ),
                    )

                    self._conn.execute(
                        """
                        INSERT INTO incident_transitions (
                            incident_id, from_state, to_state, timestamp, reason, evidence
                        ) VALUES (?, NULL, ?, ?, ?, ?);
                        """,
                        (
                            incident_id,
                            IncidentState.OPEN.value,
                            now_iso,
                            reason,
                            evidence_json,
                        ),
                    )
            except sqlite3.IntegrityError:
                # Handled race condition: unique index on (device_id, rule_id) WHERE state='OPEN' caught a concurrent open
                logger.info("Active incident for (%s, %s) was opened concurrently; retrieving existing.", device_id, rule_id)
                active = self.get_active_incident(device_id, rule_id)
                if active:
                    return active
                raise IncidentStorageError("Integrity conflict creating incident and active record could not be fetched.")
            except sqlite3.Error as e:
                logger.error("Failed to persist new incident: %s", e)
                raise IncidentStorageError(f"Failed to persist new incident: {e}") from e

            new_inc = self.get_incident(incident_id)
            if new_inc is None:
                raise IncidentStorageError(f"Failed to retrieve created incident {incident_id}")
            return new_inc

    def resolve_incident(
        self,
        incident_id: str,
        resolve_evidence: Dict[str, Any],
        reason: str = "Condition cleared",
        resolved_at: Optional[datetime] = None,
    ) -> Incident:
        """Transition an OPEN incident to RESOLVED and record the resolution transition."""
        now = resolved_at or utc_now()
        now_iso = _to_utc_iso(now)
        evidence_json = json.dumps(resolve_evidence, default=str)

        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")

            incident = self.get_incident(incident_id)
            if incident is None:
                raise IncidentStorageError(f"Cannot resolve non-existent incident: {incident_id}")

            if incident.state == IncidentState.RESOLVED:
                # Already resolved, idempotent return
                return incident

            try:
                with self._conn:
                    self._conn.execute(
                        """
                        UPDATE incidents
                        SET state = ?, resolved_at = ?, last_evaluated_at = ?, resolve_evidence = ?
                        WHERE incident_id = ?;
                        """,
                        (
                            IncidentState.RESOLVED.value,
                            now_iso,
                            now_iso,
                            evidence_json,
                            incident_id,
                        ),
                    )

                    self._conn.execute(
                        """
                        INSERT INTO incident_transitions (
                            incident_id, from_state, to_state, timestamp, reason, evidence
                        ) VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            incident_id,
                            IncidentState.OPEN.value,
                            IncidentState.RESOLVED.value,
                            now_iso,
                            reason,
                            evidence_json,
                        ),
                    )
            except sqlite3.Error as e:
                logger.error("Failed to resolve incident %s: %s", incident_id, e)
                raise IncidentStorageError(f"Failed to resolve incident {incident_id}: {e}") from e

            resolved = self.get_incident(incident_id)
            if resolved is None:
                raise IncidentStorageError(f"Failed to reload resolved incident {incident_id}")
            return resolved

    def touch_incident(self, incident_id: str, evaluated_at: Optional[datetime] = None) -> None:
        """Update last_evaluated_at timestamp for an active incident."""
        now_iso = _to_utc_iso(evaluated_at or utc_now())
        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")
            try:
                with self._conn:
                    self._conn.execute(
                        "UPDATE incidents SET last_evaluated_at = ? WHERE incident_id = ?;",
                        (now_iso, incident_id),
                    )
            except sqlite3.Error as e:
                logger.error("Failed to touch incident %s: %s", incident_id, e)
                raise IncidentStorageError(f"Failed to touch incident {incident_id}: {e}") from e

    def cleanup_retention(self, older_than_days: int = 90, batch_size: int = 500) -> int:
        """Prune resolved incident history older than the retention threshold.

        Guarantees:
        - Active (OPEN) incidents are NEVER pruned, regardless of age.
        - Deletions are bounded by batch_size and executed transactionally.
        - Foreign key constraints ensure related transitions are also cleaned up.

        Returns:
            Number of resolved incidents pruned.
        """
        if older_than_days <= 0:
            return 0

        cutoff = utc_now() - timedelta(days=older_than_days)
        cutoff_iso = _to_utc_iso(cutoff)
        batch_size = max(1, min(batch_size, 5000))

        with self._lock:
            if self._conn is None:
                raise IncidentStorageError("Database connection is closed.")

            total_deleted = 0
            try:
                # Find eligible resolved IDs bounded by batch_size
                cursor = self._conn.execute(
                    """
                    SELECT incident_id FROM incidents
                    WHERE state = 'RESOLVED' AND resolved_at < ?
                    LIMIT ?;
                    """,
                    (cutoff_iso, batch_size),
                )
                ids_to_delete = [row["incident_id"] for row in cursor.fetchall()]

                if not ids_to_delete:
                    return 0

                with self._conn:
                    # Explicit deletion of transitions and incidents
                    placeholders = ",".join("?" for _ in ids_to_delete)
                    self._conn.execute(
                        f"DELETE FROM incident_transitions WHERE incident_id IN ({placeholders});",
                        ids_to_delete,
                    )
                    del_cursor = self._conn.execute(
                        f"DELETE FROM incidents WHERE incident_id IN ({placeholders});",
                        ids_to_delete,
                    )
                    total_deleted = del_cursor.rowcount

                logger.info("Retention cleanup pruned %d resolved incidents older than %s", total_deleted, cutoff_iso)
                return total_deleted
            except sqlite3.Error as e:
                logger.error("Retention cleanup failed: %s", e)
                raise IncidentStorageError(f"Retention cleanup failed: {e}") from e
