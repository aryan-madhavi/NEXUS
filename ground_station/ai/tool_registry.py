"""NEXUS AI Tool Registry and Dispatcher.

Defines the JSON function calling schemas for Ollama/OpenAI tool interfaces
and routes model tool calls safely to explicit Python implementations in `NexusAITools`.

Strictly enforces:
- Explicit allowlisted tool names.
- Type checking on arguments.
- Immediate rejection of unauthorized tools or command execution requests.
- Wrapping tool responses in safe, structured dictionaries.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from .tools import NexusAITools, ToolResult

logger = logging.getLogger("nexus.ai.registry")


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_telemetry",
            "description": "Get latest sensor and executive readings for a monitored device (e.g. temperature, humidity, LDR raw, X0 raw ADC counts, DHT validity flag).",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device identifier (default: 'esp32_01').",
                    }
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_telemetry_freshness",
            "description": "Check telemetry arrival age and determine if a device has become stale based on expected cyclic executive cadences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device identifier (default: 'esp32_01').",
                    },
                    "msg_type": {
                        "type": "string",
                        "enum": ["telem", "hb", "status"],
                        "description": "Message type to check ('telem', 'hb', or 'status'). Default is 'telem'.",
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_signal_statistics",
            "description": "Compute statistical summary (min, max, mean, count) for a specific signal over a time window without silent truncation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device identifier (default: 'esp32_01').",
                    },
                    "signal": {
                        "type": "string",
                        "description": "Signal name: 'temp', 'hum', 'ldr_raw', 'x0_raw', 'dht_valid', 'free_heap', 'exec_ticks', etc.",
                    },
                    "window": {
                        "type": "string",
                        "description": "Relative time window (e.g. '-15m', '-1h', '-24h'). Default: '-15m'.",
                    },
                },
                "required": ["device_id", "signal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_signal_trend",
            "description": "Compute slope per minute and trend direction (RISING, FALLING, STABLE, INSUFFICIENT_DATA) for a numeric signal over a time window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device identifier (default: 'esp32_01').",
                    },
                    "signal": {
                        "type": "string",
                        "description": "Signal name: 'temp', 'hum', 'ldr_raw', 'x0_raw', 'free_heap', etc.",
                    },
                    "window": {
                        "type": "string",
                        "description": "Relative time window (e.g. '-15m', '-1h', '-6h'). Default: '-15m'.",
                    },
                },
                "required": ["device_id", "signal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_sensor_quality",
            "description": "Audit sensor validity flags in a window, distinguishing confirmed invalid samples from absent telemetry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device identifier (default: 'esp32_01').",
                    },
                    "window": {
                        "type": "string",
                        "description": "Relative evaluation window (e.g. '-15m', '-1h'). Default: '-15m'.",
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_incidents",
            "description": "Query currently active (OPEN) operational incidents, including rule identifier, severity, summary, and opening evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Optional device filter. If omitted, returns active incidents for all devices.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_incident_history",
            "description": "Query recent incident history (both resolved and open) with timestamps, severities, and summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Optional device identifier filter.",
                    },
                    "rule_id": {
                        "type": "string",
                        "description": "Optional rule identifier filter (e.g. 'stale_telemetry', 'dht_sensor_invalid').",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of incidents to return (1-50, default: 10).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_incident_details",
            "description": "Retrieve complete details, opening/resolving evidence, and chronological state transitions for a specific incident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Unique incident identifier (e.g. 'inc_stale_telemetry_...').",
                    }
                },
                "required": ["incident_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Inspect overall Ground Station telemetry database connection health and monitoring service state.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

ALLOWED_TOOL_NAMES = {t["function"]["name"] for t in TOOL_DEFINITIONS}


class ToolDispatcher:
    """Dispatches tool calls safely with validation and allowlist enforcement."""

    def __init__(self, tools: NexusAITools) -> None:
        self.tools = tools
        self._handlers: Dict[str, Callable[..., ToolResult]] = {
            "get_latest_telemetry": self.tools.get_latest_telemetry,
            "get_telemetry_freshness": self.tools.get_telemetry_freshness,
            "get_signal_statistics": self.tools.get_signal_statistics,
            "get_signal_trend": self.tools.get_signal_trend,
            "audit_sensor_quality": self.tools.audit_sensor_quality,
            "get_active_incidents": self.tools.get_active_incidents,
            "get_incident_history": self.tools.get_incident_history,
            "get_incident_details": self.tools.get_incident_details,
            "get_system_status": self.tools.get_system_status,
        }

    def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool call with strict allowlist and argument validation."""
        if tool_name not in ALLOWED_TOOL_NAMES:
            logger.warning("Attempted invocation of unapproved tool: '%s'", tool_name)
            return ToolResult(
                success=False,
                data={},
                error=(
                    f"Unauthorized or unknown tool: '{tool_name}'. "
                    f"Allowed tools: {sorted(list(ALLOWED_TOOL_NAMES))}"
                ),
            )

        if not isinstance(arguments, dict):
            logger.warning("Invalid non-dict arguments passed to '%s': %r", tool_name, arguments)
            return ToolResult(
                success=False,
                data={"arguments_received": arguments},
                error=f"Tool arguments must be a dictionary, got {type(arguments).__name__}.",
            )

        handler = self._handlers.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                data={},
                error=f"No handler registered for approved tool '{tool_name}'.",
            )

        try:
            logger.info("Executing tool '%s' with args: %s", tool_name, arguments)
            return handler(**arguments)
        except TypeError as e:
            logger.warning("Argument mismatch executing '%s': %s", tool_name, e)
            return ToolResult(
                success=False,
                data={"arguments_received": arguments},
                error=f"Invalid arguments for tool '{tool_name}': {e}",
            )
        except Exception as e:
            logger.exception("Unexpected error executing tool '%s': %s", tool_name, e)
            return ToolResult(
                success=False,
                data={"arguments_received": arguments},
                error=f"Execution error in '{tool_name}': {e}",
            )
