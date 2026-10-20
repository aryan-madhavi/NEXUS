"""Unit tests for the Ground Station bidirectional command router.

Tests inbound command handling, application launcher invocation, response formatting,
firmware command dispatch, and response correlation.
"""

import json
from unittest.mock import MagicMock
import pytest

from ground_station.command_router.application_launcher import ApplicationLauncher, LaunchResult
from ground_station.command_router.command_registry import CommandRegistry, StatusCode
from ground_station.command_router.router import CommandRouter, InboundRoutingResult


class TestCommandRouter:
    """Test suite for Ground Station CommandRouter."""

    @pytest.fixture
    def mock_launcher(self) -> MagicMock:
        """Create mock application launcher."""
        launcher = MagicMock(spec=ApplicationLauncher)
        launcher.launch.return_value = LaunchResult(
            action="DASHBOARD",
            target_url="http://127.0.0.1:3000",
            launch_accepted=True,
            service_reachable=True,
            duplicate_suppressed=False,
            message="Grafana opened successfully",
            code=StatusCode.OK,
        )
        return launcher

    @pytest.fixture
    def router(self, mock_launcher: MagicMock) -> CommandRouter:
        """Create command router with mock launcher."""
        return CommandRouter(
            dev_id="nexus_esp32",
            launcher=mock_launcher,
        )

    def test_inbound_open_command_routes_to_launcher(
        self, router: CommandRouter, mock_launcher: MagicMock
    ) -> None:
        """Verify an inbound OPEN command triggers the launcher and generates a response envelope."""
        cmd_payload = json.dumps({
            "ver": 1,
            "dev": "nexus_esp32",
            "seq": 101,
            "type": "cmd",
            "cmd_id": 0x1E01,
            "verb": "OPEN",
            "noun": "DASHBOARD",
        })

        res: InboundRoutingResult = router.handle_inbound_payload(
            payload=cmd_payload,
            source="serial",
        )

        assert res.handled is True
        assert res.action_taken == "launched"
        assert res.response_envelope is not None
        mock_launcher.launch.assert_called_once_with(
            verb="OPEN",
            noun="DASHBOARD",
            source="serial",
            extra_params={},
        )

        resp = res.response_envelope
        assert resp["ver"] == 1
        assert resp["type"] == "resp"
        assert resp["verb"] == "OPEN"
        assert resp["noun"] == "DASHBOARD"
        assert resp["cmd_id"] == 0x1E01
        assert resp["status"] == "completed"
        assert resp["code"] == 0

    def test_inbound_unsupported_command_safe_rejection(
        self, router: CommandRouter, mock_launcher: MagicMock
    ) -> None:
        """Verify an unsupported or deferred command is rejected with code 3."""
        cmd_payload = json.dumps({
            "ver": 1,
            "dev": "nexus_esp32",
            "seq": 102,
            "type": "cmd",
            "verb": "ASK",
            "noun": "SYSTEM",
        })

        res = router.handle_inbound_payload(cmd_payload, source="mqtt")
        assert res.handled is True
        assert res.action_taken == "rejected_unsupported"
        assert res.response_envelope is not None
        mock_launcher.launch.assert_not_called()

        resp = res.response_envelope
        assert resp["status"] == "unsupported"
        assert resp["code"] == StatusCode.UNSUPPORTED
        assert "Milestone 8" in resp["msg"]

    def test_inbound_malformed_json_rejection(self, router: CommandRouter) -> None:
        """Verify malformed JSON input is rejected safely."""
        bad_json = "{\"ver\": 1, \"dev\": \"nexus_esp32\", \"seq\": "
        res = router.handle_inbound_payload(bad_json, source="serial")

        assert res.handled is False
        assert res.action_taken == "rejected_malformed"
        assert res.response_envelope is not None
        assert res.response_envelope["status"] == "rejected"
        assert res.response_envelope["code"] == StatusCode.REJECTED

    def test_inbound_missing_required_fields(self, router: CommandRouter) -> None:
        """Verify envelopes missing required fields are rejected safely."""
        missing_type = json.dumps({"ver": 1, "dev": "nexus_esp32", "seq": 1})
        res = router.handle_inbound_payload(missing_type, source="serial")
        assert res.handled is False
        assert res.action_taken == "ignored"

        missing_verb = json.dumps({"ver": 1, "dev": "nexus_esp32", "seq": 1, "type": "cmd"})
        res2 = router.handle_inbound_payload(missing_verb, source="serial")
        assert res2.handled is False
        assert res2.action_taken == "rejected_invalid"
        assert res2.response_envelope["code"] == StatusCode.REJECTED

    def test_inbound_firmware_response_correlation(self, router: CommandRouter) -> None:
        """Verify inbound firmware response envelopes correlate with tracked requests."""
        resp_payload = json.dumps({
            "ver": 1,
            "dev": "nexus_esp32",
            "seq": 205,
            "type": "resp",
            "cmd_id": 0x0601,
            "verb": "GET",
            "noun": "STATUS",
            "status": "completed",
            "code": 0,
            "uptime": 65000,
            "msg": "Operational",
        })

        res = router.handle_inbound_payload(resp_payload, source="serial")
        assert res.handled is True
        assert res.action_taken == "response_correlated"
        assert res.response_envelope is None  # Does not produce a response to a response

        # Verify response recorded in history
        history = router.get_response_history()
        assert len(history) == 1
        assert history[0]["cmd_id"] == 0x0601
        assert history[0]["status"] == "completed"

    def test_outbound_command_dispatch_and_routing(self, router: CommandRouter) -> None:
        """Verify router creates validated outbound command dictionaries."""
        mock_sender = MagicMock(return_value=True)

        env = router.send_command(
            verb="GET",
            noun="STATUS",
            sender_func=mock_sender,
            extra_params={"filter": "all"},
        )

        assert env["type"] == "cmd"
        assert env["verb"] == "GET"
        assert env["noun"] == "STATUS"
        assert env["cmd_id"] == 0x0601
        assert env["filter"] == "all"
        assert env["seq"] == 1

        mock_sender.assert_called_once_with(env)

    def test_outbound_unsupported_command_fails(self, router: CommandRouter) -> None:
        """Verify router rejects sending commands that are unsupported in M8."""
        with pytest.raises(ValueError, match="not supported in Milestone 8"):
            router.send_command(
                verb="RESET",
                noun="STATISTICS",
            )
