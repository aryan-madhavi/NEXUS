"""NEXUS Open WebUI Tool Registration Script.

Registers or updates the native read-only NEXUS telemetry and incident tools in
the running Open WebUI instance database.
Safe and idempotent:
- Only registers the allowlisted read-only tools defined in `ground_station/ai/open_webui_tools.py`.
- Generates exact OpenAI/Ollama tool schemas matching Open WebUI specification.
- Does not expose credentials or modify users, models, or global system settings.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_repo_root = str(Path(__file__).resolve().parent.parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

logger = logging.getLogger("nexus.ai.register_webui")

DEFAULT_DB_PATH = (
    "/home/aryan/.local/share/open-webui-venv/lib/python3.12/site-packages/open_webui/data/webui.db"
)
TOOL_ID = "nexus_telemetry_tools"
TOOL_NAME = "NEXUS Telemetry & Monitoring Tools"
TOOL_DESCRIPTION = (
    "Read-only operational tools for querying NEXUS ESP32 telemetry, freshness, "
    "sensor quality, statistics, trends, and monitoring incidents."
)


def get_tool_content() -> str:
    """Read tool source code from open_webui_tools.py."""
    tool_file = Path(__file__).parent / "open_webui_tools.py"
    if not tool_file.exists():
        raise FileNotFoundError(f"Open WebUI tool source file not found at: {tool_file}")
    with open(tool_file, "r", encoding="utf-8") as f:
        return f.read()


def generate_specs_offline() -> List[Dict[str, Any]]:
    """Return explicit OpenAI-compatible function schemas for the 9 read-only tools."""
    from ground_station.ai.tool_registry import TOOL_DEFINITIONS

    # Open WebUI specs format is a list of clean function schema dictionaries
    specs: List[Dict[str, Any]] = []
    for item in TOOL_DEFINITIONS:
        fn = item.get("function", {})
        specs.append({
            "name": fn.get("name"),
            "description": fn.get("description"),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return specs


def register_tool_in_db(db_path: str = DEFAULT_DB_PATH) -> bool:
    """Register or update NEXUS tools in Open WebUI SQLite database."""
    p = Path(db_path)
    if not p.exists():
        print(f"[ERROR] Open WebUI database not found at {db_path}")
        return False

    content = get_tool_content()
    specs = generate_specs_offline()
    now_ts = int(time.time())

    meta = {
        "description": TOOL_DESCRIPTION,
        "manifest": {
            "title": TOOL_NAME,
            "author": "NEXUS Ground Station",
            "version": "1.0.0",
        },
    }

    try:
        conn = sqlite3.connect(str(p))
        cursor = conn.cursor()

        # 1. Fetch admin or first user
        cursor.execute("SELECT id FROM user LIMIT 1;")
        row = cursor.fetchone()
        user_id = row[0] if row else "admin"

        # 2. Check if tool exists
        cursor.execute("SELECT id FROM tool WHERE id = ?;", (TOOL_ID,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE tool
                SET name = ?, content = ?, specs = ?, meta = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    TOOL_NAME,
                    content,
                    json.dumps(specs),
                    json.dumps(meta),
                    now_ts,
                    TOOL_ID,
                ),
            )
            print(f"[OK] Successfully updated existing tool '{TOOL_ID}' in Open WebUI.")
        else:
            cursor.execute(
                """
                INSERT INTO tool (id, user_id, name, content, specs, meta, created_at, updated_at, valves)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    TOOL_ID,
                    user_id,
                    TOOL_NAME,
                    content,
                    json.dumps(specs),
                    json.dumps(meta),
                    now_ts,
                    now_ts,
                    None,
                ),
            )
            print(f"[OK] Successfully registered new tool '{TOOL_ID}' ({len(specs)} functions) in Open WebUI.")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Failed to register tool in Open WebUI database: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Register NEXUS read-only tools in Open WebUI")
    parser.add_argument(
        "--db-path",
        type=str,
        default=os.environ.get("WEBUI_DB_PATH", DEFAULT_DB_PATH),
        help=f"Path to webui.db (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()

    success = register_tool_in_db(args.db_path)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
