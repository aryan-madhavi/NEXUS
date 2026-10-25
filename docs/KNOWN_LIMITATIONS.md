# NEXUS Known Limitations, Hardware Constraints, and Architectural Gaps

## 1. Overview and Engineering Candor

This document provides a prioritized, evidence-backed register of known hardware conflicts, unpopulated PCB components, firmware timing constraints, and software architectural asymmetries in NEXUS. 

Every entry is categorized by operational severity, citing exact source paths, hardware schematics, and test evidence.

---

## 2. Prioritized Limitations Register

### 1. HC-SR04 Ultrasonic Range Hard-Capped at ~137 cm
- **Status:** Implemented / Capped by Design
- **Severity:** Medium (Functional Limitation)
- **Technical Root Cause:** The HC-SR04 ultrasonic sensor datasheet specifies a 2 cm to 400 cm range (echo pulse up to 25 ms). However, `components/nexus_sensors/src/nexus_hcsr04.c` enforces a hard timeout cap of $8,000\text{ }\mu\text{s}$ during echo pulse measurement. This cap is required to prevent blocking the cyclic executive cooperative tick callback ($\le 50\text{ ms}$ budget).
  $$\text{Max Distance} = \frac{8000\text{ }\mu\text{s} \times 0.0343\text{ cm}/\mu\text{s}}{2} \approx 137.2\text{ cm}$$
- **Operational Impact:** Any physical object farther than $\sim 137\text{ cm}$ produces a timeout. The driver treats this as out-of-range, and `dist_cm` is omitted from the telemetry envelope.
- **Evidence Reference:** `components/nexus_sensors/src/nexus_hcsr04.c` (lines 88–105).
- **Workaround:** Position reflectors within $10\text{--}120\text{ cm}$ during testing and demonstrations.
- **Required Next Step:** Offload ultrasonic pulse timing to ESP32 hardware RMT peripheral or MCPWM capture timer to achieve 400 cm range without blocking CPU ticks.

---

### 2. `IC2` Linear Hall Effect Sensor Footprint Unpopulated on PCB
- **Status:** Blocked / Hardware Unpopulated
- **Severity:** Low (Hardware Discrepancy)
- **Technical Root Cause:** On the physical EDU_ROBO V14 PCB, component footprint `IC2` (intended for an A1302/A1308 linear Hall effect magnetic sensor) is unpopulated. The firmware samples CD4051 analog multiplexer channel X1 (`GPIO36` / `ADC1_CH0`), but the input pin is floating.
- **Operational Impact:** Telemetry publishes `x1_raw` values fluctuating randomly between $15$ and $80$ raw ADC counts. It does NOT represent magnetic field flux.
- **Evidence Reference:** Physical PCB BOM inspection; `docs/validation/m10_b3_hw870_excitation.log`.
- **Workaround:** Mission Control UI and AI prompts explicitly label `x1_raw` as unpopulated floating noise.
- **Required Next Step:** Solder an analog Hall sensor onto footprint `IC2` or disable channel X1 acquisition in firmware.

---

### 3. TSOP1838 Infrared Demodulator Blocked by UART0 TX Pin Conflict
- **Status:** Blocked / Hardware Pin Conflict
- **Severity:** High (Feature Blocked)
- **Technical Root Cause:** On the EDU_ROBO V14 PCB schematic, the TSOP1838 38 kHz infrared receiver output is wired to `GPIO1`. In the ESP32 architecture, `GPIO1` is dedicated to hardware `U0TXD` (Serial Console Transmit).
- **Operational Impact:** Enabling the TSOP1838 receiver driver corrupts UART0 serial console output and breaks serial telemetry ingestion. The TSOP1838 driver is disabled in firmware.
- **Evidence Reference:** `docs/SPEC_SHEET.md`; `main/nexus_cmd_dispatcher.c`.
- **Workaround:** Infrared demodulation is bypassed; remote control features are unavailable over physical IR.
- **Required Next Step:** Cut PCB trace to `GPIO1` and fly-wire TSOP1838 output to an unused input pin (e.g., `GPIO39` / Sensor_VN).

---

### 4. Asymmetric Safety Confirmation Gating
- **Status:** Implemented (Host Only) / Firmware Asymmetry
- **Severity:** High (Security & Safety)
- **Technical Root Cause:** Hazardous command confirmation (`requires_confirmation: true`, returning `StatusCode.CONFIRMATION_REQUIRED` = 7 when `confirmed=false`) is enforced **exclusively in the Python Ground Station** (`ground_station/command_router/router.py`). The ESP32 firmware Command Dispatcher (`main/nexus_cmd_dispatcher.c`) contains no confirmation verification or signature checks.
- **Operational Impact:** Any command received directly over serial UART or via unauthenticated MQTT `nexus/<dev>/cmd` executes immediately on the hardware without confirmation gating.
- **Evidence Reference:** `ground_station/command_router/router.py` (lines 595–605); `main/nexus_cmd_dispatcher.c` (lines 200–450).
- **Workaround:** Restrict MQTT network access to trusted hosts using Mosquitto ACLs.
- **Required Next Step:** Add confirmation token validation inside `nexus_cmd_dispatcher.c` for hazardous opcodes.

---

### 5. InfluxDB Telemetry Probe Anomaly in Demo Launcher Scripts
- **Status:** Implemented (Software Anomaly)
- **Severity:** Medium (Operational False Alarm)
- **Technical Root Cause:** In `scripts/nexus_demo_common.sh`, the health inspection function `query_latest_telemetry()` evaluates telemetry freshness strictly by querying `dist_cm`:
  ```python
  rec = svc.get_latest_reading("nexus_esp32", "dist_cm")
  ```
- **Operational Impact:** If the ultrasonic sensor is disconnected, aimed at open space (> 137 cm), or omitted, `rec` is `None`. Consequently, `./scripts/nexus-demo-status.sh` reports `TELEMETRY INGESTION: NO DATA` or `UNVERIFIED`, even when LDR light levels, temperature, and system metrics are streaming and persisted normally.
- **Evidence Reference:** `scripts/nexus_demo_common.sh` (lines 160–185).
- **Workaround:** Check overall device freshness via REST API: `curl http://127.0.0.1:8000/api/telemetry/latest`.
- **Required Next Step:** Update `query_latest_telemetry()` to query any active field in `nexus_telemetry` bucket rather than hardcoding `dist_cm`.

---

### 6. Dual Incident & Monitoring Subsystem Divergence
- **Status:** Implemented (Architectural Divergence)
- **Severity:** Medium (Architectural Inconsistency)
- **Technical Root Cause:** NEXUS contains two parallel incident monitoring implementations:
  1. `MonitoringService` (`ground_station/monitoring/service.py`): Evaluates 4 deterministic rules against InfluxDB and persists alerts to SQLite WAL (`ground_station/data/nexus_incidents.db`). Runs under `run_*_ingestion.py --enable-monitoring`.
  2. `NexusGroundStationServer` (`ground_station/server.py`): The main web server endpoint `GET /api/incidents` evaluates ephemeral alerts in-memory against `TelemetryCache` without reading from `nexus_incidents.db`.
- **Operational Impact:** Incidents recorded in SQLite by the background ingestion service do not populate the Mission Control web panel incident history tab unless bridged.
- **Evidence Reference:** `ground_station/server.py` (lines 350–385); `ground_station/monitoring/service.py`.
- **Workaround:** Historical incidents can be audited directly via SQLite: `sqlite3 ground_station/data/nexus_incidents.db "SELECT * FROM incidents;"`.
- **Required Next Step:** Refactor `ground_station/server.py` to query `IncidentStore` in SQLite for all incident REST endpoints.

---

### 7. Conversational AI Fall-Through on Out-of-Domain Queries
- **Status:** Partially Verified (Prompt Handling Limitation)
- **Severity:** Low (UX Quirk)
- **Technical Root Cause:** The system prompt in `ground_station/ai/prompts.py` enforces a strict tool-calling mandate: whenever the user asks about system state, the model must invoke a telemetry tool before responding. For ungrounded queries (e.g. "Calculate rocket trajectory to Mars") or non-existent devices (`non_existent_device_xyz_99`), the model or deterministic fallback defaults to dumping the active telemetry block of `nexus_esp32`.
- **Operational Impact:** The assistant fails to explain why orbital mechanics or unknown devices are invalid, responding instead with the standard environmental sensor telemetry.
- **Evidence Reference:** `docs/validation/open_webui_validation_evidence.json` (Items 7 & 9).
- **Workaround:** Operator queries should stick to supported diagnostic topics (sensor trends, freshness, incident history).
- **Required Next Step:** Add out-of-domain intent classification in `ground_station/ai/agent.py` prior to invoking telemetry lookup tools.

---

### 8. Hardcoded Host LAN IP in Docker Compose
- **Status:** Implemented (Configuration Friction)
- **Severity:** Low (Setup Friction)
- **Technical Root Cause:** In `docker-compose.yml`, the Mosquitto broker port mapping is configured as:
  ```yaml
  ports:
    - "127.0.0.1:1883:1883"
    - "${MQTT_BIND_IP:-10.12.252.18}:1883:1883"
  ```
- **Operational Impact:** If cloned to another developer's machine where the physical network interface does not have IP `10.12.252.18` and `MQTT_BIND_IP` is unset, `podman-compose` fails with `cannot bind allocated socket: Cannot assign requested address`.
- **Evidence Reference:** `docker-compose.yml` (line 15).
- **Workaround:** Create `.env` from `.env.example` and set `MQTT_BIND_IP=0.0.0.0` or the local host LAN IP.
- **Required Next Step:** Change default fallback in `docker-compose.yml` from `10.12.252.18` to `0.0.0.0`.

---

### 9. Stubbed Actuator Command Handlers
- **Status:** Implemented (Stubs / Partially Verified)
- **Severity:** Low (Expected Educational Scaffold)
- **Technical Root Cause:** While the command registry defines 115 commands, 51 firmware command handlers return success status codes (`code=0`) without asserting physical GPIO outputs. For instance, `74HC595` shift register commands, relay K1 toggles, and motor PWM handlers are software stubs or simulations.
- **Operational Impact:** Mission Control reports successful execution, but no physical relay clicks or shift-register LED patterns occur.
- **Evidence Reference:** `main/nexus_cmd_dispatcher.c` (lines 350–520).
- **Workaround:** Physical actuator demonstrations should focus on the 4 on-board LEDs (`GPIO27, 14, 12, 13`), Buzzer (`GPIO18`), and core telemetry sensors.
- **Required Next Step:** Implement physical SPI/GPIO drivers for the 74HC595 shift register and L293D motor driver.

---

### 10. Non-Existence of Cactus-Compute Engine
- **Status:** Planned / Non-Existent
- **Severity:** Informational (Documentation Correction)
- **Technical Root Cause:** Early architectural roadmap notes referenced a "Cactus-Compute edge neural network inference runtime" for running on-device edge ML. 
- **Operational Impact:** Zero implementation code or C libraries exist in the repository for Cactus-Compute. All machine intelligence in NEXUS is provided via the host-side Ollama / Open WebUI runtime.
- **Evidence Reference:** Full repository grep for `cactus_compute` yields zero executable symbols.
- **Workaround:** N/A (Feature was deferred).
- **Required Next Step:** Formally deprecate roadmap references to Cactus-Compute in project blueprints.

---

### 11. Host Scheduling Contention in `test_milestone4_host` Test 15
- **Status:** Partially Verified (Host Test Jitter)
- **Severity:** Low (Test Harness Flake)
- **Technical Root Cause:** In `tests/test_milestone4_host.c`, Test 15 launches a concurrent producer thread pushing 200 envelopes with 50 µs delay into a 32-element queue while a consumer thread drains. On multi-core Linux systems without real-time thread priority pinning, host OS thread scheduling occasionally delays the consumer, causing the bounded queue to fill and triggering `assert(enqueued)`.
- **Operational Impact:** Test 15 intermittently aborts in host CI environments despite the underlying ring buffer and queue overflow rejection logic functioning correctly.
- **Evidence Reference:** `tests/test_milestone4_host.c` (lines 1210–1235).
- **Workaround:** Re-run test or run with real-time thread scheduling (`chrt -f 50 ./tests/test_milestone4_host`).
- **Required Next Step:** Adjust test assertion to verify graceful overflow drop accounting rather than asserting that the queue never saturates under unpinned host scheduling.

