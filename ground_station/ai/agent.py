"""NEXUS Conversational AI Agent.

Orchestrates tool-enabled multi-turn chat for the NEXUS Ground Station operator.
Features:
- Native tool calling loop using the local Ollama API (e.g. `mistral:7b`).
- Deterministic fallback routing when the LLM service is offline or unconfigured.
- Prompt injection protection and evidence attribution.
- Enforced read-only boundaries: refuses device actuation, firmware, or mutation requests.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .prompts import SYSTEM_PROMPT
from .tool_registry import TOOL_DEFINITIONS, ToolDispatcher
from .tools import NexusAITools, ToolResult

logger = logging.getLogger("nexus.ai.agent")

UNSAFE_MUTATION_PATTERNS: List[re.Pattern[str]] = [
    # 1. Hardware actuation / reboot / reset / restart commands
    re.compile(
        r"\b(?:reboot|restart|reset|power\s*cycle)\s+(?:the\s+)?(?:esp32|device|board|hardware|mcu|controller|system)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:\s*please\s+)?(?:reboot|restart|reset|power\s*cycle)(?:\s+now|\s+immediately)?\s*[.!?]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:can|could|would|please|i\s+want\s+you\s+to|order\s+you\s+to)\s+(?:you\s+)?(?:reboot|restart|reset|power\s*cycle|turn\s+off|turn\s+on|shut\s*down)\s+(?:the\s+)?(?:esp32|device|board|hardware|system)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:turn\s+(?:on|off)|shut\s*down|power\s*down|halt)\s+(?:the\s+)?(?:esp32|device|board|hardware|sensor|power|system)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:actuate|trigger|toggle)\s+(?:the\s+)?(?:pin|gpio|relay|hardware|sensor|device)\b",
        re.IGNORECASE,
    ),
    # 2. Firmware flashing
    re.compile(
        r"\b(?:flash|burn|upload|install|reflash)\s+(?:the\s+|new\s+|a\s+)?(?:firmware|bin|image|code|rom|sketch)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bflash\s+(?:the\s+)?(?:esp32|device|board)\b",
        re.IGNORECASE,
    ),
    # 3. Telemetry / incident / database mutation or deletion
    re.compile(
        r"\b(?:delete|drop|truncate|purge|wipe|clear|remove)\s+(?:the\s+|all\s+)?(?:incident|incidents|history|database|table|tables|telemetry|records?|logs?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:drop\s+table|drop\s+database|rm\s+-rf)\b",
        re.IGNORECASE,
    ),
    # 4. Threshold / rule / config mutation
    re.compile(
        r"\b(?:change|modify|update|set|tune|override|alter|adjust|write)\s+(?:the\s+)?(?:monitoring\s+|alert\s+|alarm\s+)?(?:threshold|thresholds|rule|rules|config|configuration)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bset\s+(?:temp|temperature|humidity|cadence|threshold)\s*(?:to|=)\s*[0-9]+",
        re.IGNORECASE,
    ),
    # 5. Device command transmission / publishing
    re.compile(
        r"\b(?:publish|send|transmit|inject|dispatch)\s+(?:an?\s+)?(?:mqtt\s+|serial\s+)?(?:command|packet|message|payload|instruction)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:publish\s+.*mqtt|send\s+.*command)\b",
        re.IGNORECASE,
    ),
    # 6. OS / shell execution
    re.compile(
        r"\b(?:exec|execute|run)\s+(?:bash|sh|cmd|powershell|script|binary)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sudo|chmod|chown)\b",
        re.IGNORECASE,
    ),
]


def is_mutation_or_actuation_request(user_query: str) -> bool:
    """Evaluate whether user query is an imperative request for hardware actuation, control, or data mutation."""
    return any(p.search(user_query) for p in UNSAFE_MUTATION_PATTERNS)


@dataclass
class AgentResponse:
    """Outcome of a conversational agent query."""

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    model: str = ""
    fallback_used: bool = False
    refusal: bool = False


class NexusConversationalAgent:
    """Conversational assistant for NEXUS telemetry and monitoring."""

    def __init__(
        self,
        tools: Optional[NexusAITools] = None,
        model: str = "mistral:7b",
        ollama_url: str = "http://localhost:11434",
        system_prompt: str = SYSTEM_PROMPT,
        request_timeout_sec: float = 60.0,
    ) -> None:
        """Initialize NexusConversationalAgent."""
        self.tools = tools or NexusAITools()
        self.dispatcher = ToolDispatcher(self.tools)
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.system_prompt = system_prompt
        self.request_timeout_sec = request_timeout_sec

    def is_ollama_available(self) -> bool:
        """Check if local Ollama service is reachable."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def ask(self, user_query: str, history: Optional[List[Dict[str, str]]] = None) -> AgentResponse:
        """Process an operator query and return an evidence-grounded response.

        Flow:
        1. Check for unauthorized mutation/actuation intents -> refuse immediately.
        2. If Ollama is available, execute model-driven tool loop.
        3. If Ollama is offline or fails, execute deterministic fallback routing.
        """
        start_time = time.perf_counter()

        # Pre-flight check: Refuse command/mutation requests deterministically
        if is_mutation_or_actuation_request(user_query):
            latency = (time.perf_counter() - start_time) * 1000
            return AgentResponse(
                content=(
                    "I cannot perform that action. The NEXUS Conversational Assistant is strictly "
                    "read-only. I cannot actuate hardware, send commands to the ESP32, publish MQTT, "
                    "or modify thresholds and database records."
                ),
                latency_ms=latency,
                model=self.model,
                fallback_used=False,
                refusal=True,
            )

        # Attempt Ollama tool-calling loop if service is reachable
        if self.is_ollama_available():
            try:
                response = self._run_ollama_loop(user_query, history)
                response.latency_ms = (time.perf_counter() - start_time) * 1000
                return response
            except Exception as e:
                logger.warning("Ollama tool-calling loop encountered error (%s); falling back to deterministic routing.", e)

        # Deterministic fallback router
        logger.info("Using deterministic fallback router for query: '%s'", user_query)
        response = self._run_deterministic_fallback(user_query)
        response.latency_ms = (time.perf_counter() - start_time) * 1000
        response.fallback_used = True
        return response

    def _call_ollama_chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Send chat request to Ollama HTTP API."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.ollama_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.request_timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _run_ollama_loop(self, user_query: str, history: Optional[List[Dict[str, str]]] = None) -> AgentResponse:
        """Run tool-calling loop with local model via Ollama."""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_query})

        tool_calls_executed: List[Dict[str, Any]] = []
        tool_results_recorded: List[Dict[str, Any]] = []

        # Turn 1: Model evaluates query against available tools
        step1 = self._call_ollama_chat(messages, tools=TOOL_DEFINITIONS)
        msg1 = step1.get("message", {})
        tool_calls = msg1.get("tool_calls", [])

        if not tool_calls:
            # Model responded directly without calling tools; enforce tool-grounded response via fallback router
            logger.info("Model returned no tool_calls for query '%s'; enforcing tool grounding via fallback.", user_query)
            fallback_resp = self._run_deterministic_fallback(user_query)
            fallback_resp.fallback_used = True
            return fallback_resp

        messages.append(msg1)

        # Execute tool calls
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            tool_calls_executed.append({"name": name, "arguments": args})

            result: ToolResult = self.dispatcher.dispatch(name, args)
            tool_results_recorded.append({"name": name, "result": result.to_dict()})

            # Append tool output to message history
            messages.append({
                "role": "tool",
                "content": json.dumps(result.to_dict(), default=str),
            })

        # Turn 2: Model synthesizes final evidence-based answer
        step2 = self._call_ollama_chat(messages)
        final_msg = step2.get("message", {})
        final_content = final_msg.get("content", "").strip()

        return AgentResponse(
            content=final_content,
            tool_calls=tool_calls_executed,
            tool_results=tool_results_recorded,
            model=self.model,
        )

    def _run_deterministic_fallback(self, user_query: str) -> AgentResponse:
        """Deterministic intent router and response synthesizer for offline or non-LLM mode."""
        q = user_query.lower()

        # Extract device_id if mentioned (e.g. esp32_01, nexus_esp32, nexus_val_fee185f7)
        dev_match = (
            re.search(r"\b((?:esp32|nexus)[0-9a-zA-Z_-]+)\b", q)
            or re.search(r"device\s+([0-9a-zA-Z_-]+)", q)
        )
        dev = dev_match.group(1) if dev_match else "nexus_esp32"

        tool_name: Optional[str] = None
        tool_args: Dict[str, Any] = {}

        # 0. Explanatory queries (definitions, sensor meaning)
        if any(phrase in q for phrase in ("what does", "what is", "meaning of", "explain the term", "define")):
            if "reset" in q or "reboot" in q:
                return AgentResponse(
                    content=(
                        "In NEXUS telemetry, a 'reset' or 'reboot' refers to an ESP32 microcontroller restart "
                        "(e.g. power-on reset, watchdog timeout, or panic). A reset reinitializes "
                        "the cyclic executive, resetting 'uptime_ms' and sequence counters ('seq') to 0. "
                        "Reset events are tracked via the 'uptime_ms' discontinuity or 'stale_telemetry' incidents."
                    ),
                    tool_calls=[],
                    tool_results=[],
                    model="deterministic_fallback_explainer",
                    fallback_used=True,
                )
            elif "x0_raw" in q or "x0" in q:
                return AgentResponse(
                    content=(
                        "In NEXUS telemetry, 'x0_raw' represents raw uncalibrated ADC counts (0-4095) "
                        "from multiplexer input channel 0 (HW-870 Infrared Photodetector). It is an electrical voltage measurement, "
                        "NOT a calibrated gas concentration or ppm value, and must not be used as a safety metric."
                    ),
                    tool_calls=[],
                    tool_results=[],
                    model="deterministic_fallback_explainer",
                    fallback_used=True,
                )
            elif "x1_raw" in q or "x1" in q or "hall" in q:
                return AgentResponse(
                    content=(
                        "In NEXUS telemetry, 'x1_raw' corresponds to multiplexer input channel 1 (Hall-effect magnetic sensor IC2). "
                        "On the EDU_ROBO V14 hardware platform, IC2 is UNPOPULATED / NOT MOUNTED. "
                        "Any reading on x1_raw represents floating ADC noise and cannot be converted to Gauss or Tesla."
                    ),
                    tool_calls=[],
                    tool_results=[],
                    model="deterministic_fallback_explainer",
                    fallback_used=True,
                )
            elif "dht_valid" in q:
                return AgentResponse(
                    content=(
                        "In NEXUS telemetry, 'dht_valid' is a boolean flag indicating whether the DHT11 "
                        "sensor read completed with valid checksum and timing. When dht_valid is False, "
                        "temperature and humidity values are invalid and treated as null (never zero)."
                    ),
                    tool_calls=[],
                    tool_results=[],
                    model="deterministic_fallback_explainer",
                    fallback_used=True,
                )

        # 1. Statistics / min / max / mean / historical queries (checked before trend so max queries are never misrouted)
        if any(w in q for w in ("statistics", "average", "mean", "minimum", "maximum", "min", "max", "highest", "lowest", "peak")):
            sig = "dist_cm" if any(w in q for w in ("dist", "distance", "hcsr04", "ultrasonic")) else "temp"
            if "hum" in q or "humidity" in q:
                sig = "hum"
            elif "ldr" in q or "light" in q:
                sig = "ldr_raw"
            elif "x0" in q or "gas" in q or "hw870" in q or "infrared" in q or "ir" in q:
                sig = "x0_raw"
            elif "x1" in q or "hall" in q or "magnetic" in q:
                sig = "x1_raw"
            elif "slot" in q or "moc7811" in q or "optical" in q:
                sig = "slot_state"
            elif "heap" in q:
                sig = "free_heap"

            win = "-15m"
            if any(p in q for p in ("to date", "all time", "all-time", "ever", "history", "historical", "since beginning", "to-date")):
                win = "-30d"
            elif "24h" in q or "day" in q or "today" in q:
                win = "-24h"
            elif "1h" in q or "hour" in q:
                win = "-1h"
            elif "7d" in q or "week" in q:
                win = "-7d"

            tool_name = "get_signal_statistics"
            tool_args = {"device_id": dev, "signal": sig, "window": win}

        # 2. Incident queries
        elif "inc_" in user_query or any(w in q for w in ("incident", "incidents", "alert", "alerts", "alarm", "fault")):
            inc_match = re.search(r"\b(inc_[0-9a-zA-Z_.:-]+)\b", user_query)
            if inc_match:
                tool_name = "get_incident_details"
                tool_args = {"incident_id": inc_match.group(1)}
            elif "history" in q or "recent" in q or "past" in q or "resolved" in q:
                tool_name = "get_incident_history"
                tool_args = {"device_id": dev, "limit": 10}
            else:
                tool_name = "get_active_incidents"
                tool_args = {"device_id": dev}

        # 3. Overall system status and complete health queries
        elif any(w in q for w in ("health status", "health of", "complete health", "system health", "operational status", "system status", "health")):
            tool_name = "get_telemetry_freshness"
            msg_type = "telem"
            tool_args = {"device_id": dev, "msg_type": msg_type}

        # 4. Freshness / cadence queries
        elif any(w in q for w in ("stale", "fresh", "cadence", "offline", "alive", "last seen")):
            tool_name = "get_telemetry_freshness"
            msg_type = "hb" if "heartbeat" in q or "hb" in q else ("status" if "status" in q else "telem")
            tool_args = {"device_id": dev, "msg_type": msg_type}

        # 5. Reboot / Reset / Uptime diagnostics
        elif any(w in q for w in ("reboot", "reset", "uptime", "restart")):
            tool_name = "get_latest_telemetry"
            tool_args = {"device_id": dev}

        # 6. Trend queries
        elif any(w in q for w in ("trend", "rising", "falling", "slope", "rate")):
            sig = "dist_cm" if any(w in q for w in ("dist", "distance", "hcsr04", "ultrasonic")) else "temp"
            if "hum" in q or "humidity" in q:
                sig = "hum"
            elif "ldr" in q or "light" in q:
                sig = "ldr_raw"
            elif "x0" in q or "gas" in q or "hw870" in q:
                sig = "x0_raw"
            elif "x1" in q or "hall" in q:
                sig = "x1_raw"
            elif "slot" in q or "moc7811" in q or "optical" in q:
                sig = "slot_state"
            elif "heap" in q:
                sig = "free_heap"
            tool_name = "get_signal_trend"
            tool_args = {"device_id": dev, "signal": sig, "window": "-15m"}

        # 7. Sensor quality / invalid readings
        elif any(w in q for w in ("sensor quality", "dht_valid", "invalid reading", "sensor health", "corrupt")):
            tool_name = "audit_sensor_quality"
            tool_args = {"device_id": dev, "window": "-15m"}

        # 8. Executive task failures
        elif any(w in q for w in ("executive", "task failure", "failed task", "dispatched", "latency")):
            tool_name = "get_active_incidents"
            tool_args = {"device_id": dev}

        # 9. Database reachability / InfluxDB overview
        elif any(w in q for w in ("influxdb", "database", "overview")):
            tool_name = "get_system_status"
            tool_args = {}

        # Default fallback: latest telemetry
        else:
            tool_name = "get_latest_telemetry"
            tool_args = {"device_id": dev}

        # Execute selected tool
        res: ToolResult = self.dispatcher.dispatch(tool_name, tool_args)
        if (
            not dev_match
            and tool_args.get("device_id") == "esp32_01"
            and res.success
            and (
                res.data.get("has_telemetry") is False
                or res.data.get("total_samples") == 0
                or res.data.get("sample_count") == 0
            )
        ):
            alt_args = dict(tool_args, device_id="nexus_esp32")
            alt_res = self.dispatcher.dispatch(tool_name, alt_args)
            if alt_res.success and (
                alt_res.data.get("has_telemetry") is True
                or (alt_res.data.get("total_samples") or 0) > 0
                or (alt_res.data.get("sample_count") or 0) > 0
            ):
                tool_args = alt_args
                res = alt_res
        content = self._format_deterministic_explanation(tool_name, tool_args, res)

        return AgentResponse(
            content=content,
            tool_calls=[{"name": tool_name, "arguments": tool_args}],
            tool_results=[{"name": tool_name, "result": res.to_dict()}],
            model="deterministic_fallback_router",
            fallback_used=True,
        )

    def _format_deterministic_explanation(self, tool_name: str, args: Dict[str, Any], res: ToolResult) -> str:
        """Synthesize a human-readable, factual explanation grounded in tool results."""
        if not res.success:
            return f"Unable to retrieve data for {tool_name}: {res.error} (retrieval time: {res.retrieval_timestamp})"

        data = res.data

        if tool_name == "get_latest_telemetry":
            if not data.get("has_telemetry"):
                return f"No telemetry observations recorded for device '{args.get('device_id')}'. (Checked {res.time_range_evaluated})"
            sensors = data.get("sensors", {})
            temp = sensors.get("temperature_c")
            hum = sensors.get("humidity_pct")
            dht_valid = sensors.get("dht_valid")
            ldr = sensors.get("ldr_raw")
            x0 = sensors.get("x0_raw_adc")
            x1 = sensors.get("x1_raw_adc")
            slot_state = sensors.get("slot_state")
            dist_cm = sensors.get("dist_cm")
            t_str = f"{temp}°C" if temp is not None else ("INVALID" if dht_valid is False else "None")
            h_str = f"{hum}%" if hum is not None else ("INVALID" if dht_valid is False else "None")
            uptime_ms = data.get("uptime_ms")
            uptime_desc = f"{uptime_ms} ms (~{uptime_ms / 1000.0:.1f}s since last boot/reset)" if isinstance(uptime_ms, (int, float)) else "Unknown"
            lines = [
                f"Latest telemetry for {data.get('device_id')} at {data.get('host_time')} UTC (uptime {uptime_desc}, seq {data.get('seq')}):",
                f"- Temperature: {t_str}",
                f"- Humidity: {h_str}",
                f"- DHT Valid Flag: {dht_valid}",
                f"- LDR Raw ADC: {ldr}",
                f"- X0 Raw ADC: {x0} (Note: raw ADC count from MUX input 0, not a calibrated gas concentration)",
            ]
            if x1 is not None:
                lines.append(f"- X1 Raw ADC: {x1} (Note: MUX input 1; Hall Effect IC2 is unpopulated on EDU_ROBO V14 PCB)")
            if slot_state is not None:
                lines.append(f"- MOC7811 Optical Slot State: {slot_state} (0 = unblocked, 1 = blocked)")
            if dist_cm is not None:
                lines.append(f"- HC-SR04 Ultrasonic Distance: {dist_cm} cm")
            lines.append(f"- Transports: {', '.join(data.get('transports', []))}")
            return "\n".join(lines)

        elif tool_name == "get_telemetry_freshness":
            stale_str = "STALE (No recent packets)" if data.get("is_stale") else "NOMINAL / FRESH"
            age = data.get("age_seconds")
            cadence = data.get("expected_cadence_sec")
            uptime_ms = data.get("last_uptime_ms")
            uptime_str = f"{uptime_ms} ms (~{uptime_ms / 1000.0:.1f}s since last reboot)" if isinstance(uptime_ms, (int, float)) else "Unknown"
            dht_str = "VALID (Checksum pass)" if data.get("dht_healthy") else "INVALID / UNHEALTHY"
            transports = ", ".join(data.get("transports_seen", [])) or "None active"

            return (
                f"Health & Operational Status for ESP32 ({data.get('device_id')}):\n"
                f"- Telemetry Stream: {stale_str} (packet arrival age: {age}s, expected cadence: {cadence}s)\n"
                f"- Monotonic Uptime: {uptime_str}\n"
                f"- Last Telemetry Sequence: #{data.get('last_seq')} at {data.get('last_seen_host')} UTC\n"
                f"- Active Transports Observed: {transports}\n"
                f"- Primary Sensors Health: DHT11 temperature/humidity {dht_str}\n"
                f"- Observable Scope: Continuous telemetry ingestion active via USB Serial & MQTT to InfluxDB.\n"
                f"- Unobservable / Hardware Constraints: Internal FreeRTOS task stacks and CPU load are not exposed in telemetry stream; unmounted peripherals (Relay K1, DC Motors, Servo, Touch, Vibration, LM35, LCD, and Hall IC2) are absent from EDU_ROBO V14 PCB."
            )

        elif tool_name == "get_active_incidents":
            incs = data.get("incidents", [])
            if not incs:
                return f"No active (OPEN) incidents found for {args.get('device_id', 'all devices')} as of {res.retrieval_timestamp}."
            lines = [f"Found {len(incs)} active incident(s):"]
            for inc in incs:
                lines.append(
                    f"- [{inc.get('severity')}] {inc.get('rule_id')} on {inc.get('device_id')}: {inc.get('summary')} "
                    f"(Opened: {inc.get('opened_at')} UTC, ID: {inc.get('incident_id')})"
                )
            return "\n".join(lines)

        elif tool_name == "get_signal_trend":
            return (
                f"Trend analysis for signal '{data.get('signal')}' on {data.get('device_id')} over window {data.get('window')}:\n"
                f"- Direction: {data.get('direction')}\n"
                f"- Slope: {data.get('slope_per_minute')} units/min\n"
                f"- Total Delta: {data.get('delta')}\n"
                f"- Samples Evaluated: {data.get('sample_count')} (from {data.get('start_value')} to {data.get('end_value')})"
            )

        elif tool_name == "get_signal_statistics":
            sig = data.get("signal", "")
            unit = " cm" if sig == "dist_cm" else ("°C" if sig in ("temp", "temperature") else ("%" if sig in ("hum", "humidity") else " counts"))
            first_t = data.get("first_time") or "N/A"
            last_t = data.get("last_time") or "N/A"
            max_val = data.get("max")
            min_val = data.get("min")
            mean_val = data.get("mean")
            count = data.get("sample_count", 0)
            inval = data.get("invalid_count", 0)
            win = data.get("window", "")

            note_str = ""
            if sig == "dist_cm":
                note_str = " (HC-SR04 ultrasonic distance sensor)"
            elif sig == "x0_raw":
                note_str = " (HW-870 infrared photodetector raw ADC)"

            return (
                f"Historical telemetry statistics for '{sig}'{note_str} on device '{data.get('device_id')}' over window {win}:\n"
                f"- Maximum Recorded Value: {max_val}{unit}\n"
                f"- Minimum Recorded Value: {min_val}{unit}\n"
                f"- Mean Value: {mean_val}{unit}\n"
                f"- Valid Samples: {count} (invalid readings: {inval})\n"
                f"- Time Range: {first_t} to {last_t} UTC"
            )

        elif tool_name == "audit_sensor_quality":
            return (
                f"Sensor Quality Audit for {data.get('dev')} over {data.get('window')}:\n"
                f"- Total Envelopes: {data.get('total_samples')}\n"
                f"- Valid DHT Readings: {data.get('dht_valid_count')}\n"
                f"- Invalid DHT Readings: {data.get('dht_invalid_count')} ({data.get('dht_invalid_ratio'):.1%})\n"
                f"- X0 Raw ADC Stats: {data.get('x0_raw_stats')}"
            )

        elif tool_name == "get_system_status":
            ds = data.get("data_source", {})
            mon = data.get("monitoring", {})
            return (
                f"NEXUS System Status at {res.retrieval_timestamp}:\n"
                f"- Telemetry Database (InfluxDB): {ds.get('status')}\n"
                f"- Active Incidents: {mon.get('active_incident_count')}\n"
                f"- Summary: {mon.get('active_incidents_summary')}"
            )

        elif tool_name == "get_incident_history":
            incs = data.get("incidents", [])
            if not incs:
                return f"No incident history found for {args.get('device_id', 'all devices')} as of {res.retrieval_timestamp}."
            lines = [f"Incident History (recent {len(incs)}):"]
            for inc in incs:
                lines.append(
                    f"- [{inc.get('state')}] [{inc.get('severity')}] {inc.get('rule_id')} on {inc.get('device_id')}: "
                    f"{inc.get('summary')} (Opened: {inc.get('opened_at')} UTC, ID: {inc.get('incident_id')})"
                )
            return "\n".join(lines)

        elif tool_name == "get_incident_details":
            inc = data.get("incident", {})
            trans = data.get("transitions", [])
            lines = [
                f"Incident Details for {inc.get('incident_id')}:",
                f"- Rule: {inc.get('rule_id')} (Severity: {inc.get('severity')})",
                f"- State: {inc.get('state')} (Device: {inc.get('device_id')})",
                f"- Summary: {inc.get('summary')}",
                f"- Opened At: {inc.get('opened_at')} UTC",
                f"- Resolved At: {inc.get('resolved_at')} UTC" if inc.get("resolved_at") else "- Resolved At: Still OPEN",
                f"- Open Evidence: {json.dumps(inc.get('open_evidence', {}))}",
                f"- State Transitions ({len(trans)}):",
            ]
            for t in trans:
                lines.append(f"  * {t.get('from_state')} -> {t.get('to_state')} at {t.get('timestamp')}: {t.get('reason')}")
            return "\n".join(lines)

        return json.dumps(data, indent=2, default=str)
