"""Unit tests for the safe Ground Station application launcher.

Tests allowlisted URL targets, browser opening, cooldown idempotency suppression,
scheme/host/port validation, and injection resistance.
"""

from unittest.mock import MagicMock, patch
import pytest

from ground_station.command_router.application_launcher import (
    ApplicationLauncher,
    LaunchResult,
    TargetConfig,
)


class TestApplicationLauncher:
    """Test suite for ApplicationLauncher security, routing, and idempotency."""

    @pytest.fixture
    def mock_opener(self) -> MagicMock:
        """Create mock browser opener."""
        return MagicMock(return_value=True)

    @pytest.fixture
    def launcher(self, mock_opener: MagicMock) -> ApplicationLauncher:
        """Create launcher instance with mocked browser opener and 5s cooldown."""
        return ApplicationLauncher(
            cooldown_seconds=5.0,
            browser_opener=mock_opener,
            check_reachability=False,  # Software-only unit testing
        )

    def test_default_allowlisted_targets(self, launcher: ApplicationLauncher) -> None:
        """Verify the 4 standard candidate laptop application targets exist and are configured."""
        targets = launcher.get_allowlisted_targets()
        assert "dashboard" in targets
        assert "logs" in targets
        assert "ai" in targets
        assert "ground" in targets

        # Verify host restrictions
        dash = targets["dashboard"]
        assert dash.url == "http://127.0.0.1:3000"
        assert "127.0.0.1" in dash.allowed_hosts

    def test_successful_launch_mocked(self, launcher: ApplicationLauncher, mock_opener: MagicMock) -> None:
        """Verify launching a supported target invokes browser opener and returns success."""
        res: LaunchResult = launcher.launch(
            verb="OPEN",
            noun="DASHBOARD",
            source="esp32",
        )

        assert res.success is True
        assert res.status == "completed"
        assert res.target == "dashboard"
        assert res.url == "http://127.0.0.1:3000"
        assert res.code == 0
        mock_opener.assert_called_once_with("http://127.0.0.1:3000")

    def test_idempotency_cooldown_suppression(
        self, launcher: ApplicationLauncher, mock_opener: MagicMock
    ) -> None:
        """Verify duplicate rapid requests within cooldown window are suppressed safely."""
        # First call succeeds
        res1 = launcher.launch(verb="OPEN", noun="LOGS", source="esp32")
        assert res1.success is True
        assert res1.status == "completed"
        assert mock_opener.call_count == 1

        # Second rapid call is suppressed
        res2 = launcher.launch(verb="OPEN", noun="LOGS", source="esp32")
        assert res2.success is True
        assert res2.status == "suppressed"
        assert "cooldown active" in res2.message
        assert res2.cooldown_remaining > 0
        # Browser opener must NOT have been called a second time
        assert mock_opener.call_count == 1

        # Different target is NOT suppressed by the first target's cooldown
        res3 = launcher.launch(verb="OPEN", noun="AI", source="esp32")
        assert res3.success is True
        assert res3.status == "completed"
        assert mock_opener.call_count == 2

    def test_cooldown_reset(self, launcher: ApplicationLauncher, mock_opener: MagicMock) -> None:
        """Verify explicit cooldown reset allows immediate relaunch."""
        launcher.launch(verb="OPEN", noun="DASHBOARD")
        assert mock_opener.call_count == 1

        launcher.reset_cooldown("dashboard")
        launcher.launch(verb="OPEN", noun="DASHBOARD")
        assert mock_opener.call_count == 2

    def test_unsupported_action_rejection(self, launcher: ApplicationLauncher, mock_opener: MagicMock) -> None:
        """Verify non-allowlisted actions are rejected safely."""
        res = launcher.launch(verb="OPEN", noun="TERMINAL")
        assert res.success is False
        assert res.status == "unsupported"
        assert res.code == 3
        mock_opener.assert_not_called()

        res2 = launcher.launch(verb="RUN", noun="MALICIOUS_SCRIPT")
        assert res2.success is False
        assert res2.status == "unsupported"
        mock_opener.assert_not_called()

    def test_url_security_validation_disallowed_schemes(self, mock_opener: MagicMock) -> None:
        """Verify disallowed URL schemes (file, ftp, javascript) are rejected."""
        malicious_launcher = ApplicationLauncher(
            custom_targets={
                "bad_scheme": TargetConfig(
                    target_name="bad_scheme",
                    url="file:///etc/passwd",
                    allowed_schemes=("http", "https"),
                    allowed_hosts=("127.0.0.1",),
                )
            },
            browser_opener=mock_opener,
            check_reachability=False,
        )

        res = malicious_launcher.launch(verb="OPEN", noun="BAD_SCHEME")
        assert res.success is False
        assert res.status == "rejected"
        assert res.code == 1
        assert "Disallowed scheme" in res.message
        mock_opener.assert_not_called()

    def test_url_security_validation_disallowed_hosts(self, mock_opener: MagicMock) -> None:
        """Verify disallowed external hosts are rejected."""
        remote_launcher = ApplicationLauncher(
            custom_targets={
                "remote": TargetConfig(
                    target_name="remote",
                    url="http://attacker.example.com:3000",
                    allowed_schemes=("http", "https"),
                    allowed_hosts=("127.0.0.1", "localhost"),
                )
            },
            browser_opener=mock_opener,
            check_reachability=False,
        )

        res = remote_launcher.launch(verb="OPEN", noun="REMOTE")
        assert res.success is False
        assert res.status == "rejected"
        assert res.code == 1
        assert "Disallowed host" in res.message
        mock_opener.assert_not_called()

    def test_url_security_validation_disallowed_ports(self, mock_opener: MagicMock) -> None:
        """Verify disallowed ports are rejected."""
        port_launcher = ApplicationLauncher(
            custom_targets={
                "ssh_port": TargetConfig(
                    target_name="ssh_port",
                    url="http://127.0.0.1:22",
                    allowed_schemes=("http", "https"),
                    allowed_hosts=("127.0.0.1",),
                    allowed_ports=(3000, 8080),
                )
            },
            browser_opener=mock_opener,
            check_reachability=False,
        )

        res = port_launcher.launch(verb="OPEN", noun="SSH_PORT")
        assert res.success is False
        assert res.status == "rejected"
        assert "Disallowed port" in res.message
        mock_opener.assert_not_called()

    def test_browser_opener_failure_handling(self) -> None:
        """Verify honest failure reporting when browser opener returns False or raises exception."""
        failing_opener = MagicMock(return_value=False)
        launcher = ApplicationLauncher(
            browser_opener=failing_opener,
            check_reachability=False,
        )

        res = launcher.launch(verb="OPEN", noun="DASHBOARD")
        assert res.success is False
        assert res.status == "failed"
        assert res.code == 4

        # Exception in opener
        raising_opener = MagicMock(side_effect=RuntimeError("Desktop display server error"))
        launcher2 = ApplicationLauncher(
            browser_opener=raising_opener,
            check_reachability=False,
        )
        res2 = launcher2.launch(verb="OPEN", noun="DASHBOARD")
        assert res2.success is False
        assert res2.status == "failed"
        assert "Desktop display server error" in res2.message

    def test_reachability_check_behavior(self, mock_opener: MagicMock) -> None:
        """Verify socket reachability checking does not crash when service is offline."""
        mock_checker = MagicMock(return_value=False)
        launcher = ApplicationLauncher(
            browser_opener=mock_opener,
            reachability_checker=mock_checker,
            check_reachability=True,
        )

        res = launcher.launch(verb="OPEN", noun="DASHBOARD")
        assert res.reachable is False
        # Request was accepted and opened, but reachability is documented accurately
        assert res.success is True
        assert res.status == "completed"
        assert "unreachable" in res.message
