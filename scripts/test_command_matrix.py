#!/usr/bin/env python3
"""NEXUS Command Matrix Test Suite.

Systematically exercises all 115 canonical commands from CommandRegistry:
- Read-only queries / diagnostics
- Safe configuration / control
- Physical actuators (LED 1-4, Buzzer)
- Unmounted hardware rejection (Relay, Motors, Servo, Touch, Vibration, etc.)
- Hazardous confirmation requirements (Reboot, Flash erase, etc.)

Tests across both USB Serial and MQTT / Wi-Fi transports against running Ground Station.
Generates structured JSON evidence for the qualification report.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from ground_station.command_router.command_registry import (
    CommandRegistry,
    CommandRegistryEntry,
    CommandDestination,
    StatusCode,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CommandMatrix")

API_URL = "http://127.0.0.1:8000/api/command"

def send_command(verb: str, noun: str, params: Optional[Dict[str, Any]] = None,
                 confirmed: bool = False, transport: str = "serial", timeout: float = 3.0) -> Dict[str, Any]:
    payload = {
        "verb": verb,
        "noun": noun,
        "params": params or {},
        "confirmed": confirmed,
        "transport": transport,
        "timeout": timeout,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout + 2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {"error": str(e), "code": e.code, "body": body}
    except Exception as ex:
        return {"error": str(ex), "status": "failed", "code": 9}

def classify_command(entry: CommandRegistryEntry) -> str:
    verb = entry.verb.upper()
    noun = entry.noun.upper()

    if entry.requires_confirmation:
        return "HAZARDOUS_DESTRUCTIVE"
    if verb == "ACTUATE" and noun in ("LED", "BUZZER"):
        return "PHYSICAL_ACTUATOR"
    if not entry.is_supported or noun in ("RELAY", "MOTOR", "MOTORS", "SERVO", "TOUCH", "VIBRATION", "SOUND", "LM35", "LCD"):
        return "UNMOUNTED_HARDWARE"
    if verb in ("GET", "DISPLAY", "DIAGNOSTICS", "STATUS", "LIST", "SHOW") or noun in ("STATUS", "TELEMETRY", "HEALTH", "CAPABILITIES", "CONFIG", "VERSION", "INFO", "STATISTICS", "SYSTEM"):
        return "READ_ONLY"
    return "SAFE_CONTROL"

def main():
    entries = CommandRegistry.get_all()
    logger.info("Loaded %d canonical commands from registry.", len(entries))

    results: List[Dict[str, Any]] = []
    summary = {
        "total": len(entries),
        "passed": 0,
        "failed": 0,
        "by_class": {},
    }

    for idx, entry in enumerate(entries, 1):
        cat = classify_command(entry)
        summary["by_class"][cat] = summary["by_class"].get(cat, 0) + 1

        verb = entry.verb
        noun = entry.noun
        cmd_id = entry.cmd_id
        cmd_name = f"{verb} {noun}"

        test_params = {}
        # Fill minimal required params if needed
        for p in entry.parameters:
            if p.required:
                if p.type_name == "int":
                    test_params[p.name] = int(p.min_value if p.min_value is not None else 1)
                elif p.type_name == "float":
                    test_params[p.name] = float(p.min_value if p.min_value is not None else 1.0)
                elif p.type_name in ("string", "str"):
                    test_params[p.name] = p.options[0] if p.options else "test"
                elif p.type_name == "select":
                    test_params[p.name] = p.options[0] if p.options else "off"
                elif p.type_name == "bool":
                    test_params[p.name] = False

        # Specific safe test defaults
        if verb == "ACTUATE" and noun == "LED":
            test_params = {"led_id": 1, "state": "off"}
        elif verb == "ACTUATE" and noun == "BUZZER":
            test_params = {"duration_ms": 100}
        elif verb == "ASK":
            if noun == "SENSOR":
                test_params = {"sensor_id": "hcsr04", "question": "max recorded distance to date"}
            elif noun == "SYSTEM":
                test_params = {"question": "Provide complete health status of the ESP32"}
            elif noun == "ENVIRONMENT":
                test_params = {"question": "What is the current temperature and humidity?"}
            else:
                test_params = {"question": f"Status report for {noun.lower()}"}

        # Select transport: alternate between serial and mqtt to test both
        transport = "serial" if idx % 2 == 1 else "mqtt"
        cmd_timeout = 15.0 if verb == "ASK" else 2.5

        # Execute
        res = send_command(verb, noun, params=test_params, confirmed=False, transport=transport, timeout=cmd_timeout)

        status = res.get("status", "unknown")
        code = res.get("code", -1)
        msg = res.get("msg", "")

        # Verify expectations
        verdict = "FAIL"
        reason = ""

        if cat == "HAZARDOUS_DESTRUCTIVE":
            # Must be rejected because confirmed=False
            if status == "rejected" and code == int(StatusCode.CONFIRMATION_REQUIRED):
                verdict = "PASS"
                reason = "Correctly rejected unconfirmed hazardous command"
            else:
                verdict = "FAIL"
                reason = f"Hazardous safety gate breached: status={status}, code={code}"

        elif cat == "UNMOUNTED_HARDWARE":
            # Must be rejected as unsupported
            if status == "unsupported" and code == int(StatusCode.UNSUPPORTED):
                verdict = "PASS"
                reason = "Truthfully rejected unmounted hardware command"
            elif status == "rejected":
                verdict = "PASS"
                reason = f"Rejected unmounted command: {msg}"
            else:
                verdict = "FAIL"
                reason = f"Unmounted device returned unexpected status: {status}"

        elif cat == "PHYSICAL_ACTUATOR":
            if status in ("completed", "ok") and code == int(StatusCode.OK):
                verdict = "PASS"
                reason = f"Actuator executed successfully: {msg}"
            else:
                verdict = "FAIL"
                reason = f"Actuator failed: status={status}, code={code}, msg={msg}"

        elif cat in ("READ_ONLY", "SAFE_CONTROL"):
            if entry.is_supported:
                if status in ("completed", "ok") and code == int(StatusCode.OK):
                    verdict = "PASS"
                    reason = f"Query executed successfully: {msg}"
                elif status == "unsupported" and code == int(StatusCode.UNSUPPORTED):
                    verdict = "PASS"
                    reason = f"Firmware reported unsupported: {msg}"
                else:
                    verdict = "FAIL"
                    reason = f"Command failed: status={status}, code={code}, msg={msg}"
            else:
                if status == "unsupported" and code == int(StatusCode.UNSUPPORTED):
                    verdict = "PASS"
                    reason = "Truthfully rejected unsupported command"
                else:
                    verdict = "FAIL"
                    reason = f"Expected unsupported, got: status={status}"

        if verdict == "PASS":
            summary["passed"] += 1
        else:
            summary["failed"] += 1

        record = {
            "index": idx,
            "cmd_id": cmd_id,
            "verb": verb,
            "noun": noun,
            "classification": cat,
            "transport": transport,
            "destination": entry.destination.value,
            "status": status,
            "code": code,
            "msg": msg,
            "verdict": verdict,
            "reason": reason,
        }
        results.append(record)
        logger.info("[%3d/115] %-25s [%-18s] (%-6s) -> %s (%s)",
                    idx, cmd_name, cat, transport, verdict, reason)

        # Brief pause between commands to avoid saturating serial/MQTT buffers
        time.sleep(0.05)

    # Save output to evidence file
    output_path = "docs/validation/command_matrix_results.json"
    evidence = {
        "timestamp": time.time(),
        "summary": summary,
        "results": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    logger.info("==================================================")
    logger.info("NEXUS Command Matrix Test Run Finished:")
    logger.info("  Total Commands:  %d", summary["total"])
    logger.info("  Passed Verifications: %d", summary["passed"])
    logger.info("  Failed:          %d", summary["failed"])
    logger.info("  Breakdown:       %s", json.dumps(summary["by_class"]))
    logger.info("  Saved detailed evidence to: %s", output_path)
    logger.info("==================================================")

    return 0 if summary["failed"] == 0 else 1

if __name__ == "__main__":
    exit(main())
