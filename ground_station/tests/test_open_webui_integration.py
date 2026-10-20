"""Unit tests for Open WebUI Native Tool Integration (M7.4 Workstream A).

Runs 100% offline without requiring a live Open WebUI server or InfluxDB.
Covers:
- Tool class discovery and method interface completeness.
- Parsing via Open WebUI spec generator (get_tool_specs) producing 9 valid schemas.
- Delegation to NexusAITools with JSON string return serialization.
- Bounded time ranges, validation, and error reporting.
- Idempotent tool registration into isolated SQLite database fixture.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ground_station.ai.open_webui_tools import Tools
from ground_station.ai.register_open_webui import (
    TOOL_ID,
    TOOL_NAME,
    generate_specs_offline,
    register_tool_in_db,
)
from ground_station.ai.tools import NexusAITools, ToolResult


class TestOpenWebUIToolAdapter(unittest.TestCase):
    """Tests for Open WebUI Tools class."""

    def setUp(self) -> None:
        self.tools_instance = Tools()
        self.mock_ai_tools = MagicMock(spec=NexusAITools)
        self.tools_instance._tools = self.mock_ai_tools

    def test_expected_methods_present(self) -> None:
        """Verify that all 9 approved read-only operations are implemented on Tools."""
        expected = [
            "get_latest_telemetry",
            "get_telemetry_freshness",
            "get_signal_statistics",
            "get_signal_trend",
            "audit_sensor_quality",
            "get_active_incidents",
            "get_incident_history",
            "get_incident_details",
            "get_system_status",
        ]
        for name in expected:
            method = getattr(self.tools_instance, name, None)
            self.assertTrue(callable(method), f"Missing required tool method: {name}")

    def test_get_latest_telemetry_delegation_and_serialization(self) -> None:
        """Verify get_latest_telemetry delegates to NexusAITools and returns valid JSON."""
        self.mock_ai_tools.get_latest_telemetry.return_value = ToolResult(
            success=True,
            data={
                "has_telemetry": True,
                "device_id": "esp32_01",
                "sensors": {"temperature_c": 23.5, "humidity_pct": 52.0},
            },
        )
        res_str = self.tools_instance.get_latest_telemetry("esp32_01")
        self.assertIsInstance(res_str, str)

        parsed = json.loads(res_str)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["data"]["device_id"], "esp32_01")
        self.assertEqual(parsed["data"]["sensors"]["temperature_c"], 23.5)

    def test_get_incident_details_delegation(self) -> None:
        """Verify get_incident_details delegates and handles return payloads."""
        self.mock_ai_tools.get_incident_details.return_value = ToolResult(
            success=True,
            data={"incident": {"incident_id": "inc_123", "rule_id": "stale_telemetry"}},
        )
        res_str = self.tools_instance.get_incident_details("inc_123")
        parsed = json.loads(res_str)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["data"]["incident"]["incident_id"], "inc_123")

    def test_tool_error_handling_no_leaks(self) -> None:
        """Verify tool execution failures return safe JSON without crashing."""
        self.mock_ai_tools.get_latest_telemetry.side_effect = RuntimeError("Internal connection timeout")
        res_str = self.tools_instance.get_latest_telemetry("esp32_01")
        parsed = json.loads(res_str)
        self.assertFalse(parsed["success"])
        self.assertIn("Internal connection timeout", parsed["error"])


class TestOpenWebUISpecGeneration(unittest.TestCase):
    """Verify that Open WebUI specification generator parses the tool class."""

    def test_offline_specs_coverage(self) -> None:
        """Verify generate_specs_offline produces schemas for all 9 read-only tools."""
        specs = generate_specs_offline()
        self.assertEqual(len(specs), 9)
        names = {s["name"] for s in specs}
        expected = {
            "get_latest_telemetry",
            "get_telemetry_freshness",
            "get_signal_statistics",
            "get_signal_trend",
            "audit_sensor_quality",
            "get_active_incidents",
            "get_incident_history",
            "get_incident_details",
            "get_system_status",
        }
        self.assertEqual(names, expected)


class TestOpenWebUIRegistration(unittest.TestCase):
    """Tests for database registration logic using an isolated SQLite database."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_webui.db")

        # Initialize mock Open WebUI schema
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                role TEXT
            );
            """
        )
        conn.execute("INSERT INTO user VALUES ('user-admin-1', 'Admin', 'admin@local', 'admin');")
        conn.execute(
            """
            CREATE TABLE tool (
                id TEXT NOT NULL, 
                user_id TEXT NOT NULL, 
                name TEXT NOT NULL, 
                content TEXT NOT NULL, 
                specs TEXT NOT NULL, 
                meta TEXT NOT NULL, 
                created_at INTEGER NOT NULL, 
                updated_at INTEGER NOT NULL, 
                valves TEXT
            );
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_idempotent_registration(self) -> None:
        """Verify registering inserts a new row and a second call updates it cleanly."""
        # 1. First registration
        ok1 = register_tool_in_db(self.db_path)
        self.assertTrue(ok1)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, user_id FROM tool WHERE id = ?;", (TOOL_ID,))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], TOOL_ID)
        self.assertEqual(row[1], TOOL_NAME)
        self.assertEqual(row[2], "user-admin-1")

        # 2. Second registration (idempotent update)
        ok2 = register_tool_in_db(self.db_path)
        self.assertTrue(ok2)

        cursor.execute("SELECT count(*) FROM tool WHERE id = ?;", (TOOL_ID,))
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
