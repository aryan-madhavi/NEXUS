"""Unit tests for CommandRouter.dispatch_command method.

Tests:
  1. Parameter validation against catalog ParameterDefinitions.
  2. Hazardous command confirmation gate enforcement.
  3. Ground-station local command execution (OPEN, ASK, EXPORT, DIAGNOSTICS, HISTORY).
  4. Unsupported commands truthful rejection.
  5. Firmware command dispatch, sequence correlation, and timeout handling.
  6. Command and response audit trail logging.
"""

import json
import threading
import time
from unittest.mock import MagicMock
import pytest

from ground_station.command_router.application_launcher import ApplicationLauncher, LaunchResult
from ground_station.command_router.command_registry import CommandRegistry, StatusCode
from ground_station.command_router.router import CommandRouter
from ground_station.connection_manager.envelope_parser import EnvelopeParser, ParsedEnvelope
from ground_station.connection_manager.nexus_host_manager import NexusHostManager


class TestRouterDispatch:
    """Test suite for CommandRouter dispatch_command execution engine."""

    @pytest.fixture
    def mock_launcher(self) -> MagicMock:
        launcher = MagicMock(spec=ApplicationLauncher)
        launcher.launch.return_value = LaunchResult(
            action="DASHBOARD",
            target_url="http://127.0.0.1:3000",
            launch_accepted=True,
            service_reachable=True,
            duplicate_suppressed=False,
            message="Grafana opened",
            code=StatusCode.OK,
        )
        return launcher

    @pytest.fixture
    def mock_host_manager(self) -> MagicMock:
        mgr = MagicMock(spec=NexusHostManager)
        mgr.send_command.return_value = True
        return mgr

    @pytest.fixture
    def router(self, mock_launcher: MagicMock, mock_host_manager: MagicMock) -> CommandRouter:
        return CommandRouter(
            dev_id="nexus_esp32",
            host_manager=mock_host_manager,
            launcher=mock_launcher,
        )

    def test_dispatch_unknown_command(self, router: CommandRouter) -> None:
        """Verify unknown verb/noun returns UNKNOWN_CMD."""
        res = router.dispatch_command("FLY", "MOON")
        assert res["status"] == "rejected"
        assert res["code"] == int(StatusCode.UNKNOWN_CMD)

    def test_dispatch_unsupported_command(self, router: CommandRouter) -> None:
        """Verify SET PRIORITY returns code 3 (UNSUPPORTED) for executive safety."""
        res = router.dispatch_command("SET", "PRIORITY", {"job_id": 1, "priority": 1})
        assert res["status"] == "unsupported"
        assert res["code"] == int(StatusCode.UNSUPPORTED)
        assert "unsupported" in res["msg"].lower()

    def test_dispatch_hazardous_requires_confirmation(self, router: CommandRouter) -> None:
        """Verify RESET FAULTS without confirmed=True returns CONFIRMATION_REQUIRED."""
        res = router.dispatch_command("RESET", "FAULTS", confirmed=False)
        assert res["status"] == "rejected"
        assert res["code"] == int(StatusCode.CONFIRMATION_REQUIRED)

    def test_dispatch_hazardous_with_confirmation(self, router: CommandRouter, mock_host_manager: MagicMock) -> None:
        """Verify RESET FAULTS with confirmed=True dispatches to firmware."""
        res = router.dispatch_command("RESET", "FAULTS", confirmed=True, timeout_sec=0.1)
        mock_host_manager.send_command.assert_called_once()
        # Expect timeout since no mock response fed
        assert res["code"] in (int(StatusCode.TIMEOUT), int(StatusCode.OK))

    def test_dispatch_parameter_type_and_range_validation(self, router: CommandRouter) -> None:
        """Verify parameter validation rules (e.g. integer bounds)."""
        # ACTUATE BUZZER requires duration_ms (10-5000)
        res = router.dispatch_command("ACTUATE", "BUZZER", {"duration_ms": 99999})
        assert res["status"] == "rejected"
        assert res["code"] == int(StatusCode.REJECTED)
        assert "maximum" in res["msg"].lower() or "range" in res["msg"].lower()

    def test_dispatch_local_open_dashboard(self, router: CommandRouter, mock_launcher: MagicMock) -> None:
        """Verify OPEN DASHBOARD executes local application launcher."""
        res = router.dispatch_command("OPEN", "DASHBOARD")
        assert res["status"] == "ok"
        assert res["code"] == int(StatusCode.OK)
        mock_launcher.launch.assert_called_once_with("DASHBOARD")

    def test_dispatch_local_diagnostics(self, router: CommandRouter) -> None:
        """Verify DIAGNOSTICS DATABASE executes locally."""
        res = router.dispatch_command("DIAGNOSTICS", "DATABASE")
        assert res["status"] == "ok"
        assert res["code"] == int(StatusCode.OK)
        assert "target_url" in res.get("extra", {})

    def test_dispatch_local_export(self, router: CommandRouter) -> None:
        """Verify EXPORT TELEMETRY executes locally on ground station."""
        # 1. Add some history
        router.dispatch_command("OPEN", "DASHBOARD")
        history = router.get_history()
        assert len(history) >= 1

        # 2. Export telemetry
        export_res = router.dispatch_command("EXPORT", "TELEMETRY", {"format": "json", "limit": 50})
        assert export_res["status"] == "ok"
        assert export_res["code"] == int(StatusCode.OK)
        assert export_res["format"] == "json"

    def test_dispatch_firmware_correlated_response(self, router: CommandRouter, mock_host_manager: MagicMock) -> None:
        """Verify firmware command correlates inbound response envelope with pending waiter."""
        def delayed_reply() -> None:
            time.sleep(0.05)
            # Find the sequence number sent
            calls = mock_host_manager.send_command.call_args_list
            assert len(calls) > 0
            sent_payload = calls[0][0][0]
            envelope_dict = sent_payload if isinstance(sent_payload, dict) else json.loads(sent_payload)
            seq = envelope_dict["seq"]

            # Feed response envelope into router
            reply_json = json.dumps({
                "ver": 1,
                "dev": "nexus_esp32",
                "seq": seq,
                "type": "resp",
                "cmd_id": 1,
                "code": 0,
                "msg": "Status OK",
                "extra": {"uptime_ms": 12345},
            })
            reply_envelope = EnvelopeParser.parse(reply_json.encode("utf-8"))
            router.handle_incoming_envelope(reply_envelope)

        threading.Thread(target=delayed_reply, daemon=True).start()

        res = router.dispatch_command("GET", "STATUS", timeout_sec=1.0)
        assert res["status"] == "ok"
        assert res["code"] == 0
        assert res["msg"] == "Status OK"
