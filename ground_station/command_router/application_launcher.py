"""NEXUS Safe Laptop Application Launcher.

Provides strictly allowlisted, validated URL and application launching for
board-originated and operator-originated OPEN commands.
Enforces URL scheme/host/port allowlists, shell-injection prevention,
idempotency cooldowns, service reachability checks, and mockable browser interaction.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set, Tuple

logger = logging.getLogger("nexus.application_launcher")

# Strict allowable URL schemes
ALLOWED_SCHEMES: Set[str] = {"http", "https"}

# Strict allowable default hosts
DEFAULT_ALLOWED_HOSTS: Set[str] = {"localhost", "127.0.0.1", "10.12.252.18"}

# Strict allowable ports
DEFAULT_ALLOWED_PORTS: Set[int] = {80, 443, 3000, 8000, 8080, 9090}

# Disallowed characters that could indicate command/argument injection
DISALLOWED_URL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f\s;`|&$><\"']")


@dataclass(frozen=True)
class TargetConfig:
    """Configuration specification for an allowlisted launcher target."""

    target_name: str
    url: str
    allowed_schemes: Tuple[str, ...] = ("http", "https")
    allowed_hosts: Tuple[str, ...] = ("127.0.0.1", "localhost", "10.12.252.18")
    allowed_ports: Tuple[int, ...] = (80, 443, 3000, 8000, 8080, 9090)


@dataclass(frozen=True)
class LaunchResult:
    """Outcome of an application launch attempt."""

    action: str
    target_url: str
    launch_accepted: bool
    service_reachable: Optional[bool]
    duplicate_suppressed: bool
    message: str
    timestamp: float = field(default_factory=time.time)
    code: int = 0
    cooldown_remaining: float = 0.0

    @property
    def success(self) -> bool:
        """Alias for launch_accepted for consistency with status callers."""
        return self.launch_accepted

    @property
    def status(self) -> str:
        """Normalized string status: 'completed', 'suppressed', 'rejected', or 'failed'."""
        if self.duplicate_suppressed:
            return "suppressed"
        if not self.launch_accepted:
            if self.code in (1, 3):
                return "rejected" if self.code == 1 else "unsupported"
            return "failed"
        return "completed"

    @property
    def target(self) -> str:
        """Target name in lowercase."""
        return self.action.lower()

    @property
    def url(self) -> str:
        """Destination URL."""
        return self.target_url

    @property
    def reachable(self) -> Optional[bool]:
        """Alias for service_reachable."""
        return self.service_reachable


class LauncherSecurityError(ValueError):
    """Raised when an action or URL fails security validation."""


class ApplicationLauncher:
    """Secure application launcher with explicit allowlisting and idempotency."""

    def __init__(
        self,
        urls: Optional[Dict[str, str]] = None,
        custom_targets: Optional[Dict[str, TargetConfig]] = None,
        allowed_hosts: Optional[Set[str]] = None,
        allowed_ports: Optional[Set[int]] = None,
        cooldown_sec: float = 2.0,
        cooldown_seconds: Optional[float] = None,
        browser_opener: Optional[Callable[[str], bool]] = None,
        reachability_checker: Optional[Callable[[str], bool]] = None,
        check_reachability: bool = True,
        reachability_timeout_sec: float = 0.5,
    ) -> None:
        """Initialize the launcher.

        Args:
            urls: Optional dictionary mapping action ('DASHBOARD', 'LOGS', 'AI', 'GROUND') to URL.
            custom_targets: Optional dictionary of TargetConfig instances.
            allowed_hosts: Set of permissible hostnames/IPs.
            allowed_ports: Set of permissible TCP ports.
            cooldown_sec: Minimum seconds between repeated launches of the same action.
            cooldown_seconds: Alias for cooldown_sec.
            browser_opener: Injectable browser opening function for testing (defaults to webbrowser.open_new_tab).
            reachability_checker: Injectable TCP/HTTP health checker.
            check_reachability: Default setting for network probe reachability check.
            reachability_timeout_sec: Timeout for socket connection probe.
        """
        # Resolve URLs from environment or defaults
        self._urls: Dict[str, str] = {
            "DASHBOARD": os.environ.get("GRAFANA_URL", "http://127.0.0.1:3000"),
            "LOGS": os.environ.get("LOGS_URL", "http://127.0.0.1:3000/explore"),
            "AI": os.environ.get("OPEN_WEBUI_URL", "http://127.0.0.1:8080"),
            "GROUND": os.environ.get("GROUND_STATION_URL", "http://127.0.0.1:8000/overview"),
        }
        if urls:
            for k, v in urls.items():
                self._urls[k.strip().upper()] = v

        self._custom_targets: Dict[str, TargetConfig] = {}
        if custom_targets:
            for name, cfg in custom_targets.items():
                norm_name = name.strip().upper()
                self._custom_targets[norm_name] = cfg
                self._urls[norm_name] = cfg.url

        self._allowed_hosts = set(allowed_hosts or DEFAULT_ALLOWED_HOSTS)
        # Dynamically add hosts from configured URLs
        for u in self._urls.values():
            try:
                parsed = urllib.parse.urlparse(u)
                if parsed.hostname:
                    self._allowed_hosts.add(parsed.hostname.lower())
            except Exception:
                pass

        self._allowed_ports = set(allowed_ports or DEFAULT_ALLOWED_PORTS)
        effective_cooldown = cooldown_seconds if cooldown_seconds is not None else cooldown_sec
        self._cooldown_sec = max(0.1, effective_cooldown)
        self._browser_opener = browser_opener or webbrowser.open_new_tab
        self._reachability_checker = reachability_checker or self._check_socket_reachability
        self._default_check_reachability = check_reachability
        self._reachability_timeout_sec = reachability_timeout_sec

        # Timestamp tracking for cooldown / idempotency
        self._last_launch_mono: Dict[str, float] = {}

    @property
    def allowed_actions(self) -> Set[str]:
        """Set of supported action names."""
        return set(self._urls.keys())

    def get_allowlisted_targets(self) -> Dict[str, TargetConfig]:
        """Return a dictionary of TargetConfig entries for all configured targets."""
        res: Dict[str, TargetConfig] = {}
        for action, url in self._urls.items():
            lower_name = action.lower()
            if action in self._custom_targets:
                res[lower_name] = self._custom_targets[action]
            else:
                res[lower_name] = TargetConfig(
                    target_name=lower_name,
                    url=url,
                    allowed_schemes=("http", "https"),
                    allowed_hosts=tuple(sorted(self._allowed_hosts)),
                    allowed_ports=tuple(sorted(self._allowed_ports)),
                )
        return res

    def reset_cooldown(self, action: Optional[str] = None) -> None:
        """Reset idempotency cooldown timer for specific action or all actions."""
        if action:
            self._last_launch_mono.pop(action.strip().upper(), None)
        else:
            self._last_launch_mono.clear()

    def validate_url(self, url: str, target_cfg: Optional[TargetConfig] = None) -> str:
        """Validate a destination URL against strict security bounds.

        Returns normalized URL if valid, or raises LauncherSecurityError.
        """
        if not isinstance(url, str) or not url.strip():
            raise LauncherSecurityError("Target URL cannot be empty")

        url = url.strip()

        # Reject control characters or shell injection tokens
        if DISALLOWED_URL_CHARS_PATTERN.search(url):
            raise LauncherSecurityError(f"URL contains disallowed characters: {url!r}")

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as err:
            raise LauncherSecurityError(f"Malformed URL: {err}") from err

        valid_schemes = set(target_cfg.allowed_schemes) if target_cfg else ALLOWED_SCHEMES
        scheme = (parsed.scheme or "").lower()
        if scheme not in valid_schemes:
            raise LauncherSecurityError(
                f"Disallowed scheme '{scheme}'. Must be one of {sorted(valid_schemes)}"
            )

        valid_hosts = set(target_cfg.allowed_hosts) if target_cfg else self._allowed_hosts
        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname not in valid_hosts:
            raise LauncherSecurityError(
                f"Disallowed host '{hostname}'. Not in allowlist: {sorted(valid_hosts)}"
            )

        # Port validation
        valid_ports = set(target_cfg.allowed_ports) if target_cfg else self._allowed_ports
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80

        if port not in valid_ports:
            raise LauncherSecurityError(
                f"Disallowed port {port}. Not in allowlist: {sorted(valid_ports)}"
            )

        return url

    def launch(
        self,
        action: str = "",
        custom_url: Optional[str] = None,
        check_reachability: Optional[bool] = None,
        verb: Optional[str] = None,
        noun: Optional[str] = None,
        source: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> LaunchResult:
        """Safely execute an allowlisted application launch action.

        Args:
            action: Action name ('DASHBOARD', 'LOGS', 'AI', 'GROUND').
            custom_url: Optional override URL (must still satisfy allowlist).
            check_reachability: Whether to probe service reachability.
            verb: Optional verb (must be 'OPEN' if provided).
            noun: Optional noun (mapped to action).
            source: Command origin identifier ('serial', 'mqtt', 'esp32', etc.).
            extra_params: Arbitrary additional parameters (validated, unexecuted).

        Returns:
            LaunchResult documenting execution status, reachability, and cooldown suppression.
        """
        # Validate verb if explicitly passed
        if verb:
            norm_verb = verb.strip().upper()
            if norm_verb != "OPEN":
                return LaunchResult(
                    action=norm_verb,
                    target_url="",
                    launch_accepted=False,
                    service_reachable=False,
                    duplicate_suppressed=False,
                    message=f"Unsupported launcher verb '{norm_verb}'. Expected 'OPEN'",
                    code=3,
                )

        effective_action = noun if noun else action
        norm_action = effective_action.strip().upper()

        if norm_action not in self._urls and not custom_url:
            return LaunchResult(
                action=norm_action,
                target_url="",
                launch_accepted=False,
                service_reachable=False,
                duplicate_suppressed=False,
                message=f"Unsupported launcher action '{norm_action}'. Must be one of {sorted(self.allowed_actions)}",
                code=3,
            )

        target_url = custom_url or self._urls[norm_action]
        target_cfg = self._custom_targets.get(norm_action)

        # 1. Validate URL against security constraints
        try:
            validated_url = self.validate_url(target_url, target_cfg=target_cfg)
        except LauncherSecurityError as sec_err:
            logger.warning("Launcher security validation failed for action %s: %s", norm_action, sec_err)
            return LaunchResult(
                action=norm_action,
                target_url=target_url,
                launch_accepted=False,
                service_reachable=False,
                duplicate_suppressed=False,
                message=f"Security rejection: {sec_err}",
                code=1,
            )

        # 2. Cooldown & Idempotency check
        now_mono = time.monotonic()
        last_time = self._last_launch_mono.get(norm_action, 0.0)
        elapsed = now_mono - last_time

        if elapsed < self._cooldown_sec:
            remaining = self._cooldown_sec - elapsed
            logger.info(
                "Suppressed duplicate launch for %s (elapsed %.2fs < cooldown %.2fs)",
                norm_action,
                elapsed,
                self._cooldown_sec,
            )
            return LaunchResult(
                action=norm_action,
                target_url=validated_url,
                launch_accepted=True,
                service_reachable=None,
                duplicate_suppressed=True,
                message=f"Launch suppressed by idempotency cooldown active ({elapsed:.2f}s < {self._cooldown_sec:.2f}s)",
                code=0,
                cooldown_remaining=remaining,
            )

        # 3. Optional Service Reachability probe
        do_reachability = check_reachability if check_reachability is not None else self._default_check_reachability
        reachable: Optional[bool] = None
        if do_reachability:
            try:
                reachable = self._reachability_checker(validated_url)
            except Exception as r_err:
                logger.debug("Reachability check failed: %s", r_err)
                reachable = False

        # 4. Open in browser via safe Python API
        try:
            opened = bool(self._browser_opener(validated_url))
            if opened:
                self._last_launch_mono[norm_action] = now_mono
                reach_str = " (service reachable)" if reachable is True else (" (service unreachable)" if reachable is False else "")
                logger.info("Launched %s -> %s%s from source %s", norm_action, validated_url, reach_str, source)
                return LaunchResult(
                    action=norm_action,
                    target_url=validated_url,
                    launch_accepted=True,
                    service_reachable=reachable,
                    duplicate_suppressed=False,
                    message=f"Application opened successfully{reach_str}",
                    code=0,
                )
            else:
                return LaunchResult(
                    action=norm_action,
                    target_url=validated_url,
                    launch_accepted=False,
                    service_reachable=reachable,
                    duplicate_suppressed=False,
                    message="Browser opening call returned failure",
                    code=4,
                )
        except Exception as open_err:
            logger.error("Error executing browser launch for %s: %s", norm_action, open_err)
            return LaunchResult(
                action=norm_action,
                target_url=validated_url,
                launch_accepted=False,
                service_reachable=reachable,
                duplicate_suppressed=False,
                message=f"Browser opener exception: {open_err}",
                code=4,
            )

    def _check_socket_reachability(self, url: str) -> bool:
        """Fast TCP socket probe to verify destination endpoint is accepting connections."""
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._reachability_timeout_sec)
        try:
            res = sock.connect_ex((host, port))
            return res == 0
        except Exception:
            return False
        finally:
            sock.close()
