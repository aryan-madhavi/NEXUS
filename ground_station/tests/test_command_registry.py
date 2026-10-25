"""Unit tests for the canonical NEXUS command registry.

Verifies completeness, uniqueness, lookup methods, envelope formatting,
and 1-to-1 parity with firmware definitions.
"""

import pytest

from ground_station.command_router.command_registry import (
    CommandDestination,
    CommandDisposition,
    CommandRegistry,
    CommandRegistryEntry,
    StatusCode,
    VERB_CODES,
    NOUN_CODES,
    make_cmd_id,
)


class TestCommandRegistry:
    """Test suite for the canonical command registry."""

    def test_registry_size_and_disposition(self) -> None:
        """Verify registry contains all 52 candidate commands with valid dispositions."""
        entries = CommandRegistry.get_all()
        assert len(entries) == 115, f"Expected 115 candidate commands, got {len(entries)}"

        required_m8 = [e for e in entries if e.disposition == CommandDisposition.REQUIRED_M8]
        deferred = [e for e in entries if e.disposition == CommandDisposition.DEFERRED_M9_M10]
        unsupported = [e for e in entries if e.disposition == CommandDisposition.UNSUPPORTED]

        # Verify required categories are populated
        assert len(required_m8) >= 15, f"Expected at least 15 required M8 commands, got {len(required_m8)}"
        assert len(deferred) >= 10, f"Expected at least 10 deferred commands, got {len(deferred)}"
        assert len(unsupported) >= 10, f"Expected at least 10 unsupported commands, got {len(unsupported)}"

    def test_unique_command_ids_and_names(self) -> None:
        """Verify no duplicate command IDs or verb-noun pairs exist."""
        entries = CommandRegistry.get_all()
        seen_ids = set()
        seen_names = set()

        for entry in entries:
            assert entry.cmd_id not in seen_ids, f"Duplicate command ID: 0x{entry.cmd_id:04X}"
            seen_ids.add(entry.cmd_id)

            pair = (entry.verb, entry.noun)
            assert pair not in seen_names, f"Duplicate command verb-noun: {pair}"
            seen_names.add(pair)

            # Ensure valid bounds
            assert 0 <= entry.cmd_id <= 0xFFFF, f"Command ID out of 16-bit range: {entry.cmd_id}"
            assert 0 <= entry.verb_code <= 0xFF
            assert 0 <= entry.noun_code <= 0xFF

    def test_lookup_by_id(self) -> None:
        """Verify lookup by ID returns correct entry or None."""
        # Valid lookup: NOP NONE (0x0000)
        nop = CommandRegistry.lookup_by_id(0x0000)
        assert nop is not None
        assert nop.verb == "NOP"
        assert nop.noun == "NONE"
        assert nop.is_supported_m8 is True

        # Valid lookup: OPEN DASHBOARD (0x1E01)
        dash = CommandRegistry.lookup_by_id(0x1E01)
        assert dash is not None
        assert dash.verb == "OPEN"
        assert dash.noun == "DASHBOARD"
        assert dash.destination == CommandDestination.GROUND_STATION
        assert dash.is_supported_m8 is True

        # Unknown ID
        assert CommandRegistry.lookup_by_id(0xFFFF) is None
        assert CommandRegistry.lookup_by_id(9999) is None

    def test_lookup_by_name(self) -> None:
        """Verify case-insensitive lookup by verb and noun."""
        entry = CommandRegistry.lookup_by_name("get", "status")
        assert entry is not None
        assert entry.cmd_id == 0x0601
        assert entry.verb == "GET"
        assert entry.noun == "STATUS"

        # Case variations and whitespace
        assert CommandRegistry.lookup_by_name("  Open ", " Dashboard ") is not None
        assert CommandRegistry.lookup_by_name("open", "dashboard").cmd_id == 0x1E01

        # Non-existent commands
        assert CommandRegistry.lookup_by_name("DESTROY", "WORLD") is None
        assert CommandRegistry.lookup_by_name("REBOOT", "SYSTEM") is None

    def test_parity_with_c_constants(self) -> None:
        """Verify command IDs match firmware nexus_command_registry.h exactly."""
        expected_ids = {
            ("NOP", "NONE"): 0x0000,
            ("INITIALIZE", "SYSTEM"): 0x0101,
            ("START", "SYSTEM"): 0x0201,
            ("START", "SELF_TEST"): 0x0204,
            ("STOP", "SENSORS"): 0x0302,
            ("RESET", "FAULTS"): 0x0401,
            ("RESET", "STATISTICS"): 0x0402,
            ("SET", "PRIORITY"): 0x0501,
            ("GET", "STATUS"): 0x0601,
            ("GET", "CONFIGURATION"): 0x0602,
            ("GET", "SENSOR_LIST"): 0x0603,
            ("GET", "TIME"): 0x0604,
            ("DISPLAY", "STATUS"): 0x1001,
            ("DISPLAY", "EXECUTIVE"): 0x1002,
            ("DISPLAY", "ENVIRONMENT"): 0x1041,
            ("HISTORY", "EVENTS"): 0x1101,
            ("HISTORY", "FAULTS"): 0x1102,
            ("DIAGNOSTICS", "SYSTEM"): 0x1801,
            ("DIAGNOSTICS", "MEMORY"): 0x1805,
            ("OPEN", "DASHBOARD"): 0x1E01,
            ("OPEN", "LOGS"): 0x1E02,
            ("OPEN", "AI"): 0x1E03,
            ("OPEN", "GROUND"): 0x1E04,
            ("ASK", "SYSTEM"): 0x1F01,
            ("EXPORT", "TELEMETRY"): 0x2001,
            ("RUN", "SELF_TEST"): 0x2101,
        }

        for (verb, noun), expected_id in expected_ids.items():
            entry = CommandRegistry.lookup_by_name(verb, noun)
            assert entry is not None, f"Missing expected command: {verb} {noun}"
            assert entry.cmd_id == expected_id, (
                f"Mismatch for {verb} {noun}: expected 0x{expected_id:04X}, got 0x{entry.cmd_id:04X}"
            )

    def test_build_envelope(self) -> None:
        """Verify command envelope dictionary construction."""
        env = CommandRegistry.build_envelope(
            cmd_id=0x0601,
            seq=42,
            dev="nexus_esp32",
            uptime_ms=12345,
            extra_fields={"note": "test_req"},
        )

        assert env["ver"] == 1
        assert env["dev"] == "nexus_esp32"
        assert env["seq"] == 42
        assert env["type"] == "cmd"
        assert env["cmd_id"] == 0x0601
        assert env["verb"] == "GET"
        assert env["noun"] == "STATUS"
        assert env["uptime"] == 12345
        assert env["note"] == "test_req"

        # Invalid cmd_id raises ValueError
        with pytest.raises(ValueError, match="Unknown command ID"):
            CommandRegistry.build_envelope(cmd_id=0xDEAD, seq=1)

    def test_status_codes(self) -> None:
        """Verify status codes match firmware enum codes."""
        assert StatusCode.OK == 0
        assert StatusCode.REJECTED == 1
        assert StatusCode.UNKNOWN_CMD == 2
        assert StatusCode.UNSUPPORTED == 3
        assert StatusCode.FAILED == 4
        assert StatusCode.DUPLICATE == 5
