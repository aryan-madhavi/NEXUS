"""NEXUS Command Router.

Routes commands between Ground Station, physical transports (Serial, MQTT),
and the local Application Launcher.
Implements bidirectional dispatch, response tracking, and safe error isolation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from ground_station.connection_manager.envelope_parser import (
    CommandPayload,
    MessageType,
    ParsedEnvelope,
    ResponsePayload,
)
from ground_station.connection_manager.nexus_host_manager import NexusHostManager

from .application_launcher import ApplicationLauncher, LaunchResult
from .command_registry import (
    CommandDestination,
    CommandRegistry,
    CommandRegistryEntry,
    StatusCode,
)

logger = logging.getLogger("nexus.command_router")


@dataclass(frozen=True)
class InboundRoutingResult:
    """Detailed result of routing an inbound payload."""

    handled: bool
    action_taken: str
    response_envelope: Optional[Dict[str, Any]] = None
    launch_result: Optional[LaunchResult] = None


@dataclass(frozen=True)
class CommandRouterStats:
    """Thread-safe snapshot of command routing telemetry."""

    inbound_commands_received: int
    inbound_responses_received: int
    outbound_commands_dispatched: int
    launcher_actions_executed: int
    launcher_actions_suppressed: int
    routing_errors: int
    last_action_timestamp: Optional[float]


class CommandRouter:
    """Coordinates bidirectional command validation, routing, and response correlation."""

    def __init__(
        self,
        dev_id: str = "nexus_esp32",
        host_manager: Optional[NexusHostManager] = None,
        launcher: Optional[ApplicationLauncher] = None,
        registry: Optional[CommandRegistry] = None,
    ) -> None:
        self._dev_id = dev_id
        self._host_manager = host_manager
        self._launcher = launcher or ApplicationLauncher()
        self._registry = registry or CommandRegistry()

        self._lock = threading.Lock()
        self._inbound_cmds = 0
        self._inbound_resps = 0
        self._outbound_cmds = 0
        self._launcher_executed = 0
        self._launcher_suppressed = 0
        self._routing_errors = 0
        self._last_action_ts: Optional[float] = None
        self._next_seq = 1

        self._history: List[Dict[str, Any]] = []
        self._response_history: List[Dict[str, Any]] = []
        self._history_max = 50

        # Pending command callbacks: (dev, seq) -> callback(ResponsePayload)
        self._pending_responses: Dict[str, Callable[[ParsedEnvelope], None]] = {}

        # Auto-register with host manager if supplied
        if self._host_manager:
            self._host_manager.register_consumer(self.handle_incoming_envelope)

    @property
    def launcher(self) -> ApplicationLauncher:
        """Reference to internal application launcher."""
        return self._launcher

    @property
    def stats(self) -> CommandRouterStats:
        """Retrieve telemetry snapshot."""
        with self._lock:
            return CommandRouterStats(
                inbound_commands_received=self._inbound_cmds,
                inbound_responses_received=self._inbound_resps,
                outbound_commands_dispatched=self._outbound_cmds,
                launcher_actions_executed=self._launcher_executed,
                launcher_actions_suppressed=self._launcher_suppressed,
                routing_errors=self._routing_errors,
                last_action_timestamp=self._last_action_ts,
            )

    def handle_inbound_payload(
        self,
        payload: Union[str, bytes, Dict[str, Any]],
        source: str = "serial",
    ) -> InboundRoutingResult:
        """Handle raw string/bytes/dict inbound envelope and route accordingly."""
        now = time.time()
        # Parse JSON
        if isinstance(payload, (str, bytes)):
            try:
                data = json.loads(payload)
            except Exception as err:
                with self._lock:
                    self._routing_errors += 1
                logger.warning("Malformed JSON in inbound command payload: %s", err)
                err_resp = {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": 0,
                    "type": "resp",
                    "cmd_id": 0,
                    "status": "rejected",
                    "code": int(StatusCode.REJECTED),
                    "msg": f"Malformed JSON: {err}",
                }
                return InboundRoutingResult(
                    handled=False,
                    action_taken="rejected_malformed",
                    response_envelope=err_resp,
                )
        elif isinstance(payload, dict):
            data = payload
        else:
            return InboundRoutingResult(
                handled=False,
                action_taken="rejected_invalid",
                response_envelope={
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": 0,
                    "type": "resp",
                    "cmd_id": 0,
                    "status": "rejected",
                    "code": int(StatusCode.REJECTED),
                    "msg": "Payload must be JSON string or dict",
                },
            )

        msg_type = data.get("type")
        if not msg_type:
            return InboundRoutingResult(handled=False, action_taken="ignored")

        seq = data.get("seq", 0)

        # Handle Responses from Firmware
        if msg_type in ("resp", "response"):
            with self._lock:
                self._inbound_resps += 1
                self._last_action_ts = now
                self._response_history.append(dict(data))
                if len(self._response_history) > self._history_max:
                    self._response_history.pop(0)

                key = f"{data.get('dev', self._dev_id)}:{seq}"
                cb = self._pending_responses.pop(key, None)

            if cb:
                try:
                    cb(data)
                except Exception as cb_err:
                    logger.error("Error executing pending response callback: %s", cb_err)

            return InboundRoutingResult(handled=True, action_taken="response_correlated")

        # Handle Inbound Commands
        if msg_type in ("cmd", "command"):
            verb = str(data.get("verb", "")).strip().upper()
            noun = str(data.get("noun", "")).strip().upper()
            cmd_id = data.get("cmd_id")

            if not verb or not noun:
                err_resp = {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": seq,
                    "type": "resp",
                    "cmd_id": cmd_id or 0,
                    "status": "rejected",
                    "code": int(StatusCode.REJECTED),
                    "msg": "Missing verb or noun in command envelope",
                }
                return InboundRoutingResult(
                    handled=False,
                    action_taken="rejected_invalid",
                    response_envelope=err_resp,
                )

            with self._lock:
                self._inbound_cmds += 1
                self._last_action_ts = now

            entry = self._registry.lookup_by_name(verb, noun)
            if not entry:
                err_resp = {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": seq,
                    "type": "resp",
                    "cmd_id": cmd_id or 0,
                    "verb": verb,
                    "noun": noun,
                    "status": "unknown",
                    "code": int(StatusCode.UNKNOWN_CMD),
                    "msg": f"Unknown verb-noun pair: {verb} {noun}",
                }
                return InboundRoutingResult(
                    handled=True,
                    action_taken="rejected_unknown",
                    response_envelope=err_resp,
                )

            # Check Milestone 8 support
            if not entry.is_supported_m8:
                err_resp = {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": seq,
                    "type": "resp",
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "status": "unsupported",
                    "code": int(StatusCode.UNSUPPORTED),
                    "msg": f"Command {entry.verb} {entry.noun} is not supported in Milestone 8 ({entry.disposition.value})",
                }
                return InboundRoutingResult(
                    handled=True,
                    action_taken="rejected_unsupported",
                    response_envelope=err_resp,
                )

            # Route OPEN commands to application launcher
            if entry.verb == "OPEN" and entry.destination == CommandDestination.GROUND_STATION:
                extra_params = {k: v for k, v in data.items() if k not in ("ver", "dev", "seq", "type", "cmd_id", "verb", "noun")}
                res = self._launcher.launch(
                    verb=entry.verb,
                    noun=entry.noun,
                    source=source,
                    extra_params=extra_params,
                )

                with self._lock:
                    if res.duplicate_suppressed:
                        self._launcher_suppressed += 1
                    elif res.launch_accepted:
                        self._launcher_executed += 1
                    else:
                        self._routing_errors += 1

                resp_env = {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": seq,
                    "type": "resp",
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "status": res.status,
                    "code": res.code,
                    "msg": res.message,
                    "target": res.target,
                    "url": res.url,
                }
                return InboundRoutingResult(
                    handled=True,
                    action_taken="launched",
                    response_envelope=resp_env,
                    launch_result=res,
                )

            # Other commands destined for firmware or other subsystems
            return InboundRoutingResult(
                handled=True,
                action_taken="forwarded",
                response_envelope=None,
            )

        return InboundRoutingResult(handled=False, action_taken="ignored")

    def handle_incoming_envelope(self, envelope: ParsedEnvelope) -> Optional[LaunchResult]:
        """Process an incoming envelope from host connection manager."""
        now = time.time()
        if envelope.msg_type == MessageType.COMMAND:
            with self._lock:
                self._inbound_cmds += 1
                self._last_action_ts = now

            if not isinstance(envelope.payload, CommandPayload):
                return None

            fields = envelope.payload.fields
            verb = str(fields.get("verb", "")).strip().upper()
            noun = str(fields.get("noun", "")).strip().upper()
            cmd_id = fields.get("cmd_id")

            entry: Optional[CommandRegistryEntry] = None
            if verb and noun:
                entry = self._registry.lookup_by_name(verb, noun)
            elif isinstance(cmd_id, int):
                entry = self._registry.lookup_by_id(cmd_id)

            if not entry:
                with self._lock:
                    self._routing_errors += 1
                return None

            if entry.verb == "OPEN" and entry.destination == CommandDestination.GROUND_STATION:
                result = self._launcher.launch(entry.noun)
                with self._lock:
                    if result.duplicate_suppressed:
                        self._launcher_suppressed += 1
                    elif result.launch_accepted:
                        self._launcher_executed += 1
                    else:
                        self._routing_errors += 1

                    self._record_history({
                        "type": "inbound_cmd_open",
                        "dev": envelope.dev,
                        "seq": envelope.seq,
                        "verb": entry.verb,
                        "noun": entry.noun,
                        "result": result,
                        "timestamp": now,
                    })
                return result

        elif envelope.msg_type == MessageType.RESPONSE:
            with self._lock:
                self._inbound_resps += 1
                self._last_action_ts = now

            key = f"{envelope.dev}:{envelope.seq}"
            cb: Optional[Callable[[ParsedEnvelope], None]] = None
            with self._lock:
                cb = self._pending_responses.pop(key, None)
                self._record_history({
                    "type": "inbound_response",
                    "dev": envelope.dev,
                    "seq": envelope.seq,
                    "payload": envelope.raw_dict,
                    "timestamp": now,
                })

            if cb:
                try:
                    cb(envelope)
                except Exception as err:
                    logger.error("Error in response callback: %s", err)

        return None

    route_incoming_envelope = handle_incoming_envelope

    def send_command(
        self,
        verb: str,
        noun: str,
        sender_func: Optional[Callable[[Dict[str, Any]], bool]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        dev: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build and send a validated command dictionary."""
        entry = self._registry.lookup_by_name(verb, noun)
        if not entry:
            raise ValueError(f"Unknown command: {verb} {noun}")

        if not entry.is_supported_m8:
            raise ValueError(f"Command {verb} {noun} is not supported in Milestone 8 ({entry.disposition.value})")

        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            self._outbound_cmds += 1

        env = self._registry.build_envelope(
            cmd_id=entry.cmd_id,
            seq=seq,
            dev=dev or self._dev_id,
            extra_fields=extra_params,
        )

        if sender_func:
            sender_func(env)

        with self._lock:
            self._record_history({
                "type": "outbound_cmd",
                "dev": env["dev"],
                "seq": seq,
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "timestamp": time.time(),
            })

        return env

    def build_command_wire_string(
        self,
        verb: str,
        noun: str,
        seq: int,
        dev: str = "nexus_esp32",
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Validate verb-noun pair and serialize into Protocol v1 newline-delimited JSON."""
        entry = self._registry.lookup_by_name(verb, noun)
        if not entry:
            raise ValueError(f"Unknown command: {verb} {noun}")

        env_dict: Dict[str, Any] = {
            "ver": 1,
            "dev": dev,
            "seq": seq,
            "type": "cmd",
            "cmd_id": entry.cmd_id,
            "verb": entry.verb,
            "noun": entry.noun,
        }
        if extra_args:
            for k, v in extra_args.items():
                if k not in env_dict:
                    env_dict[k] = v

        wire_str = json.dumps(env_dict, separators=(",", ":")) + "\n"
        if len(wire_str.encode("utf-8")) >= 256:
            raise ValueError(f"Serialized command length exceeds maximum limit: {len(wire_str)} bytes")

        with self._lock:
            self._outbound_cmds += 1
            self._record_history({
                "type": "outbound_cmd",
                "dev": dev,
                "seq": seq,
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "timestamp": time.time(),
            })

        return wire_str

    def _record_history(self, event: Dict[str, Any]) -> None:
        """Append event to bounded history ring."""
        self._history.append(event)
        if len(self._history) > self._history_max:
            self._history.pop(0)

    def get_history(self) -> List[Dict[str, Any]]:
        """Return a copy of recent command routing history."""
        with self._lock:
            return list(self._history)

    def get_response_history(self) -> List[Dict[str, Any]]:
        """Return a copy of recent firmware responses."""
        with self._lock:
            return list(self._response_history)

    def dispatch_command(
        self,
        verb: str,
        noun: str,
        params: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
        timeout_sec: float = 3.0,
        transport: str = "auto",
        source: str = "web_console",
    ) -> Dict[str, Any]:
        """Dispatch a command with parameter validation, destination routing, and correlation."""
        now = time.time()
        verb_norm = str(verb).strip().upper()
        noun_norm = str(noun).strip().upper()
        params = params or {}

        # 1. Lookup entry
        entry = self._registry.lookup_by_name(verb_norm, noun_norm)
        if not entry:
            res = {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": 0,
                "verb": verb_norm,
                "noun": noun_norm,
                "status": "rejected",
                "code": int(StatusCode.UNKNOWN_CMD),
                "msg": f"Unknown command: {verb_norm} {noun_norm}",
            }
            with self._lock:
                self._record_history({
                    "type": "cmd_rejected",
                    "dev": self._dev_id,
                    "seq": 0,
                    "cmd_id": 0,
                    "verb": verb_norm,
                    "noun": noun_norm,
                    "params": params,
                    "transport": transport,
                    "status": "rejected",
                    "code": int(StatusCode.UNKNOWN_CMD),
                    "msg": res["msg"],
                    "timestamp": now,
                })
            return res

        # 2. Check hardware support / capability
        if not entry.is_supported:
            res = {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "unsupported",
                "code": int(StatusCode.UNSUPPORTED),
                "msg": f"Command {entry.verb} {entry.noun} is unsupported on current hardware configuration",
            }
            with self._lock:
                self._record_history({
                    "type": "cmd_unsupported",
                    "dev": self._dev_id,
                    "seq": 0,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "transport": transport,
                    "status": "unsupported",
                    "code": int(StatusCode.UNSUPPORTED),
                    "msg": res["msg"],
                    "timestamp": now,
                })
            return res

        # 3. Validate parameters
        is_valid, err_msg = self._registry.validate_command_parameters(entry, params)
        if not is_valid:
            res = {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "rejected",
                "code": int(StatusCode.REJECTED),
                "msg": err_msg,
            }
            with self._lock:
                self._record_history({
                    "type": "cmd_rejected",
                    "dev": self._dev_id,
                    "seq": 0,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "transport": transport,
                    "status": "rejected",
                    "code": int(StatusCode.REJECTED),
                    "msg": err_msg,
                    "timestamp": now,
                })
            return res

        # 4. Check hazardous confirmation requirement
        if entry.requires_confirmation and not confirmed:
            res = {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "rejected",
                "code": int(StatusCode.CONFIRMATION_REQUIRED),
                "requires_confirmation": True,
                "msg": f"Command {entry.verb} {entry.noun} requires explicit confirmation before execution",
            }
            with self._lock:
                self._record_history({
                    "type": "cmd_rejected",
                    "dev": self._dev_id,
                    "seq": 0,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "transport": transport,
                    "status": "rejected",
                    "code": int(StatusCode.CONFIRMATION_REQUIRED),
                    "msg": res["msg"],
                    "timestamp": now,
                })
            return res

        # 5. Route by destination
        if entry.destination == CommandDestination.GROUND_STATION:
            res = self._handle_ground_station_command(entry, params, source)
            with self._lock:
                self._record_history({
                    "type": "cmd_ground",
                    "dev": self._dev_id,
                    "seq": 0,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "status": res.get("status", "ok"),
                    "code": res.get("code", 0),
                    "msg": res.get("msg", ""),
                    "timestamp": now,
                })
            return res

        if entry.destination == CommandDestination.TEST_HARNESS:
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "ok",
                "code": int(StatusCode.OK),
                "msg": f"Test harness {entry.verb} {entry.noun} initialized",
            }

        # 6. Destination is FIRMWARE

        if not self._host_manager:
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "failed",
                "code": int(StatusCode.INTERNAL_ERROR),
                "msg": "Ground Station host manager is not available",
            }

        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            self._outbound_cmds += 1

        env = self._registry.build_envelope(
            cmd_id=entry.cmd_id,
            seq=seq,
            dev=self._dev_id,
            extra_fields=params,
        )

        resp_box: Dict[str, Any] = {}
        event = threading.Event()
        corr_key = f"{self._dev_id}:{seq}"

        def _on_firmware_resp(resp_env: Any) -> None:
            if hasattr(resp_env, "raw_dict"):
                resp_box["data"] = dict(resp_env.raw_dict)
            elif isinstance(resp_env, dict):
                resp_box["data"] = resp_env
            else:
                resp_box["data"] = str(resp_env)
            event.set()

        with self._lock:
            self._pending_responses[corr_key] = _on_firmware_resp

        delivered = self._host_manager.send_command(
            env,
            target_device=self._dev_id,
            transport_preference=transport,
        )

        with self._lock:
            self._record_history({
                "type": "outbound_cmd",
                "dev": self._dev_id,
                "seq": seq,
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "params": params,
                "transport": transport,
                "delivered": delivered,
                "timestamp": now,
            })

        if not delivered:
            with self._lock:
                self._pending_responses.pop(corr_key, None)
                self._record_history({
                    "type": "cmd_failed",
                    "dev": self._dev_id,
                    "seq": seq,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "transport": transport,
                    "status": "failed",
                    "code": int(StatusCode.INTERNAL_ERROR),
                    "msg": "No active transport (Serial or MQTT) connected to ESP32",
                    "timestamp": now,
                })
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": seq,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "failed",
                "code": int(StatusCode.INTERNAL_ERROR),
                "msg": "Command failed: no active transport (Serial or MQTT) connected to ESP32",
            }

        # Wait for correlated response
        got_resp = event.wait(timeout=max(0.5, timeout_sec))
        with self._lock:
            self._pending_responses.pop(corr_key, None)

        if not got_resp:
            with self._lock:
                self._record_history({
                    "type": "cmd_timeout",
                    "dev": self._dev_id,
                    "seq": seq,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "transport": transport,
                    "status": "timeout",
                    "code": int(StatusCode.TIMEOUT),
                    "msg": f"Command timed out after {timeout_sec:.1f}s",
                    "timestamp": time.time(),
                })
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": seq,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": entry.verb,
                "noun": entry.noun,
                "status": "timeout",
                "code": int(StatusCode.TIMEOUT),
                "msg": f"Command {entry.verb} {entry.noun} timed out after {timeout_sec:.1f}s waiting for ESP32 acknowledgement",
            }

        data = resp_box.get("data")
        if data:
            result = dict(data)
            if "status" not in result:
                code_val = result.get("code", 0)
                if code_val == int(StatusCode.OK):
                    result["status"] = "ok"
                elif code_val == int(StatusCode.UNSUPPORTED):
                    result["status"] = "unsupported"
                else:
                    result["status"] = "failed"
            with self._lock:
                self._record_history({
                    "type": "cmd_response",
                    "dev": self._dev_id,
                    "seq": seq,
                    "cmd_id": entry.cmd_id,
                    "verb": entry.verb,
                    "noun": entry.noun,
                    "params": params,
                    "transport": transport,
                    "status": result.get("status", "ok"),
                    "code": result.get("code", 0),
                    "msg": result.get("msg", ""),
                    "timestamp": time.time(),
                })
            return result

        return {
            "ver": 1,
            "dev": self._dev_id,
            "seq": seq,
            "type": "resp",
            "cmd_id": entry.cmd_id,
            "verb": entry.verb,
            "noun": entry.noun,
            "status": "ok",
            "code": int(StatusCode.OK),
            "msg": "Command executed",
        }

    def _handle_ground_station_command(
        self,
        entry: CommandRegistryEntry,
        params: Dict[str, Any],
        source: str,
    ) -> Dict[str, Any]:
        """Execute laptop-side ground station operations."""
        verb = entry.verb
        noun = entry.noun

        if verb == "OPEN":
            res = self._launcher.launch(noun)
            is_ok = bool(res.launch_accepted and res.code == int(StatusCode.OK))
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": verb,
                "noun": noun,
                "status": "ok" if is_ok else "failed",
                "code": int(res.code),
                "msg": res.message,
                "url": res.target_url,
                "target": res.action,
            }

        if verb == "DIAGNOSTICS" and noun == "DATABASE":
            # Check InfluxDB connectivity
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                res = sock.connect_ex(("127.0.0.1", 8086))
                is_up = (res == 0)
            except Exception:
                is_up = False
            finally:
                sock.close()
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": verb,
                "noun": noun,
                "status": "ok",
                "code": int(StatusCode.OK),
                "msg": "InfluxDB reachable" if is_up else "InfluxDB unreachable on 127.0.0.1:8086",
                "database_reachable": is_up,
                "port": 8086,
                "extra": {"target_url": "http://127.0.0.1:8086", "reachable": is_up},
            }

        if verb == "DIAGNOSTICS" and noun == "AI_SERVICE":
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                res = sock.connect_ex(("127.0.0.1", 8080))
                is_up = (res == 0)
            except Exception:
                is_up = False
            finally:
                sock.close()
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": verb,
                "noun": noun,
                "status": "ok",
                "code": int(StatusCode.OK),
                "msg": "Open WebUI reachable" if is_up else "Open WebUI unreachable on 127.0.0.1:8080",
                "ai_service_reachable": is_up,
                "port": 8080,
                "extra": {"target_url": "http://127.0.0.1:8080", "reachable": is_up},
            }

        if verb == "ASK":
            question = str(params.get("question", "")).strip()
            sensor_id = str(params.get("sensor_id", "")).strip()

            # Format domain-specific query cleanly without polluting intent
            if noun == "SYSTEM":
                q_text = f"Health status of {self._dev_id}. {question}" if question else f"Provide complete health status of {self._dev_id}."
            elif noun == "SENSOR":
                q_text = f"Sensor {sensor_id} on {self._dev_id}: {question}" if question else f"What is the status and latest reading of sensor '{sensor_id}' on {self._dev_id}?"
            elif noun == "EXECUTIVE":
                q_text = f"Executive status on {self._dev_id}. {question}" if question else f"What is the status of executive scheduling on {self._dev_id}?"
            elif noun == "DIAGNOSTICS":
                q_text = f"System diagnostics on {self._dev_id}. {question}" if question else f"Run diagnostic health analysis on {self._dev_id}."
            elif noun == "ENVIRONMENT":
                q_text = f"Environmental telemetry conditions on {self._dev_id}. {question}" if question else f"What are the current environmental telemetry conditions on {self._dev_id}?"
            else:
                q_text = question or f"Query regarding {noun} on {self._dev_id}"

            try:
                from ground_station.ai.agent import NexusConversationalAgent
                if not hasattr(self, "_ai_agent") or self._ai_agent is None:
                    self._ai_agent = NexusConversationalAgent(model="mistral:7b", request_timeout_sec=10.0)

                agent_res = self._ai_agent.ask(q_text)
                is_refusal = getattr(agent_res, "refusal", False)
                return {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": 0,
                    "type": "resp",
                    "cmd_id": entry.cmd_id,
                    "verb": verb,
                    "noun": noun,
                    "status": "rejected" if is_refusal else "ok",
                    "code": int(StatusCode.REJECTED) if is_refusal else int(StatusCode.OK),
                    "msg": f"AI service response for {noun}",
                    "query": question or q_text,
                    "answer": agent_res.content,
                    "tool_calls": agent_res.tool_calls,
                    "tool_results": agent_res.tool_results,
                    "model": agent_res.model,
                    "latency_ms": agent_res.latency_ms,
                    "fallback_used": agent_res.fallback_used,
                    "_execution_path": "HOST_LOCAL_OPERATION",
                    "device_wire_envelope": "NOT_APPLICABLE",
                }
            except Exception as e:
                logger.error("Error executing ASK command via NexusConversationalAgent: %s", e)
                return {
                    "ver": 1,
                    "dev": self._dev_id,
                    "seq": 0,
                    "type": "resp",
                    "cmd_id": entry.cmd_id,
                    "verb": verb,
                    "noun": noun,
                    "status": "failed",
                    "code": int(StatusCode.INTERNAL_ERROR),
                    "msg": f"AI service execution error: {e}",
                    "query": question,
                    "answer": f"AI telemetry service error: {e}",
                }

        if verb == "EXPORT":
            fmt = params.get("format", "json")
            limit = params.get("limit", 100)
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": verb,
                "noun": noun,
                "status": "ok",
                "code": int(StatusCode.OK),
                "msg": f"Exported {limit} records as {fmt}",
                "format": fmt,
                "limit": limit,
            }

        if verb == "HISTORY":
            with self._lock:
                hist = list(self._history)
            return {
                "ver": 1,
                "dev": self._dev_id,
                "seq": 0,
                "type": "resp",
                "cmd_id": entry.cmd_id,
                "verb": verb,
                "noun": noun,
                "status": "ok",
                "code": int(StatusCode.OK),
                "msg": f"Retrieved {len(hist)} history items",
                "count": len(hist),
                "history": hist[-10:],
            }

        return {
            "ver": 1,
            "dev": self._dev_id,
            "seq": 0,
            "type": "resp",
            "cmd_id": entry.cmd_id,
            "verb": verb,
            "noun": noun,
            "status": "completed",
            "code": int(StatusCode.OK),
            "msg": f"Ground station action {verb} {noun} executed",
        }
