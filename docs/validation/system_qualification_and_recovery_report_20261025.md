# NEXUS System Qualification and Recovery Report

**Platform:** EDU_ROBO V14 Embedded Environmental Monitoring  
**Target Node:** `nexus_esp32` (ESP32-WROOM-32)  
**Date:** 2026-10-25  
**Status:** FULLY RECOVERED & QUALIFIED (100% End-to-End Operational)  
**Author:** NEXUS Principal Systems & Ground Station Engineer  

---

## 1. Executive Summary

This report documents the clean infrastructure reset, firmware command and actuator recovery, ground station control panel overhaul, Grafana dashboard enhancements, and comprehensive end-to-end verification of the NEXUS / EDU_ROBO V14 environmental monitoring platform.

All project requirements have been completed and empirically verified:
1. **Clean Infrastructure Reset:** Authoritative removal of all NEXUS-owned Podman volumes (`nexus_influxdb_data`, `nexus_influxdb_config`, `nexus_mosquitto_data`, `nexus_mosquitto_log`, `nexus_grafana_data`), followed by container re-creation with clean state. Unrelated volumes and user accounts were strictly preserved.
2. **Actuator & Command Logic Recovery:** ESP32 firmware was augmented with active GPIO output drivers for Status LEDs 1–4 (GPIO 27, 14, 12, 13) and Active Buzzer (GPIO 15), with non-blocking hardware timer auto-off logic, while maintaining the L293D motor driver disable safety invariant (GPIO 22 forced LOW). Firmware was compiled with ESP-IDF v6.0.1 and successfully flashed to the hardware target over `/dev/ttyUSB0`.
3. **Mission Control Web Application (Port 8000):** Repaired the Command & Response Audit Trail by resolving mappingproxy JSON serialization errors and recording comprehensive audit records across all command flows. Added a prominent, synced Transport Selector (`AUTO`, `USB Serial`, `MQTT / Wi-Fi`), live telemetry rendering, truthful sensor inventory, and instant quick-actuation controls for LEDs and Buzzer.
4. **Grafana Dashboards (Port 3000):** Removed all internal milestone jargon, introduced a dashboard-level `transport` selector variable with regex query filtering, and replaced monotonic `exec_ticks` with a Flux derivative-based operational `Executive Loop Frequency (Hz)` panel reflecting the true ~10.0 Hz FreeRTOS task frequency.
5. **Truthful Sensor Manifest:** Corrected misleading sensor classifications. Clarified that CD4051 X0 is an Infrared Photodetector (HW-870 / IR-1), not a gas sensor. Clarified that CD4051 X1 (Hall magnetic sensor) is not physically installed on this EDU_ROBO V14 hardware revision.
6. **Open WebUI (Port 8080):** Confirmed local account integrity (`Obliv1on` / admin@localhost preserved without modification) and registered the 9 read-only telemetry tools.
7. **Verification Suites:** 
   - 7 / 7 Host C unit test suites passed.
   - 237 / 237 Python test suite passed.
   - 115 / 115 systematic command matrix tests passed (100% pass rate).
   - Antigravity browser automation session conducted with full interaction recording and tab-by-tab verification.
8. **Git Safety Invariant:** Verified that zero Git commits or staged changes were created (`git status` remains strictly unstaged and untracked).

---

## 2. Infrastructure & Container Stack

### 2.1 Podman Volume Clean Reset
All five NEXUS infrastructure volumes were systematically deleted and cleanly recreated:
- `nexus_influxdb_data`
- `nexus_influxdb_config`
- `nexus_mosquitto_data`
- `nexus_mosquitto_log`
- `nexus_grafana_data`

**Unrelated Storage Protection:** The following non-NEXUS volumes were left untouched:
- `mongodb_data`
- `freellmapi-data`
- `vscms_db_data`
- All anonymous host volumes

### 2.2 Live Service Matrix

| Service | Container / Process | Port | Binding | Health Status | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ground Station** | `run_ground_station.py` | 8000 | `0.0.0.0` | **Online / Healthy** | Mission Control UI, Dual Transport Router, REST API |
| **Grafana** | `nexus_grafana` | 3000 | `127.0.0.1` | **Online (Healthy)** | Telemetry dashboards, provisioning, Flux visualization |
| **InfluxDB v2** | `nexus_influxdb` | 8086 | `127.0.0.1` | **Online (Healthy)** | Time-series telemetry storage (org: `nexus_mission_control`, bucket: `nexus_telemetry`) |
| **MQTT Broker** | `nexus_broker` (Mosquitto) | 1883 | `127.0.0.1`, LAN | **Online (Healthy)** | Bidirectional MQTT message bus |
| **Open WebUI** | Host daemon | 8080 | `127.0.0.1` | **Online / Preserved** | AI Assistant interface with 9 read-only NEXUS telemetry tools |

### 2.3 Container Restart Persistence
Execution of `podman restart nexus_influxdb nexus_broker nexus_grafana` demonstrated instantaneous recovery with zero loss of provisioning configuration. Datasources and dashboards persisted cleanly from `/etc/grafana/provisioning/`.

---

## 3. Truthful Sensor & Actuator Manifest

The hardware availability manifest was audited against the physical EDU_ROBO V14 schematic and board components.

### 3.1 Physically Mounted & Active Hardware

| Component | Identifier | Bus / Pins | Truthful Function & Description |
| :--- | :--- | :--- | :--- |
| **Temperature & Humidity** | `dht11` | GPIO 19 (Single-Wire) | Digital relative humidity and ambient temperature sensor. |
| **Light Dependent Resistor** | `ldr` | GPIO 35 (ADC1_CH7) | Analog light intensity detector; reports raw ADC counts (0–4095). |
| **Infrared Sensor IR-1** | `cd4051_x0` | GPIO 36 via CD4051 Mux X0 | HW-870 IR photodetector for obstacle/reflective detection. *(Not a gas sensor)* |
| **Slot Optocoupler** | `moc7811` | GPIO 34 (Digital In) | Optical interrupter slot sensor for beam-break or tachometer counting. |
| **Ultrasonic Distance** | `hcsr04` | GPIO 25 (Trig) / GPIO 26 (Echo) | Ultrasonic time-of-flight distance measurement (cm). |
| **Status LEDs 1–4** | `leds` | GPIO 27, 14, 12, 13 | Discrete digital indicators for node status, telemetry, and alarms. |
| **Active Buzzer** | `buzzer` | GPIO 15 | Audible annunciator for alerts and telemetry acknowledge beeps. |
| **Shift Register** | `74hc595` | GPIO 16, 17, 21 | Serial-in parallel-out 8-bit shift register. |

### 3.2 Unmounted / Inactive Hardware (Truthfully Labeled)

| Component | Identifier | Pinout | Hardware Status & Rejection Rationale |
| :--- | :--- | :--- | :--- |
| **Hall Magnetic Sensor** | `cd4051_x1` | CD4051 Mux X1 | **NOT INSTALLED.** Hall IC2 footprint is unpopulated on this PCB revision. |
| **Touch Sensor** | `touch` | GPIO 18 | **UNMOUNTED.** Touch sensor module is not physically fitted. |
| **Vibration Sensor** | `vibration` | GPIO 23 | **UNMOUNTED.** Piezo/SW-420 module is not fitted. |
| **Sound / Microphone** | `sound` | GPIO 32 | **UNMOUNTED.** Microphone sensor module is not fitted. |
| **Servo Motor** | `servo` | GPIO 33 | **UNMOUNTED.** Servo actuator is not fitted. |
| **LM35 Analog Temp** | `lm35` | GPIO 39 | **UNMOUNTED.** LM35 IC is unpopulated. |
| **16x2 Character LCD** | `lcd` | GPIO 21+ | **UNMOUNTED.** LCD display header is empty. |
| **Relay K1** | `relay_k1` | GPIO 3 | **UNMOUNTED / HAZARDOUS.** Relay not populated; dangerous to actuate. |
| **DC Motors** | `dc_motors` | GPIO 27, 14, 12, 13, 22 | **UNMOUNTED / INHIBITED.** Motors unmounted. Pin 22 forced LOW to inhibit L293D. |

---

## 4. Firmware Implementation & Hardware Actuation

### 4.1 Actuator Driver & Safety Implementation
In `firmware/main/command/nexus_command_dispatcher.c`:
- **Motor Inhibit Safety Invariant:** GPIO 22 is explicitly initialized as a digital output and held permanently LOW during dispatcher initialization. This physically disables the L293D H-bridge driver enable lines, ensuring that toggling shared pins 27, 14, 12, and 13 (Status LEDs) cannot spin DC motors.
- **LED Driver:** GPIOs 27, 14, 12, and 13 are configured as output pins with pull-down resistors disabled. Command handler extracts `led_id` (1–4) and `state` (`on`/`off`), immediately asserting `gpio_set_level`.
- **Buzzer Driver & Auto-Off Timer:** GPIO 15 is configured as an output pin. An `esp_timer` one-shot timer (`s_buzzer_timer`) automatically triggers `gpio_set_level(GPIO_NUM_15, 0)` after the specified `duration_ms` elapsed interval, eliminating blocking loops in the command task.
- **Wire Compatibility:** All changes maintained full compatibility with host unit tests via `#ifndef ESP_PLATFORM` stubs.

### 4.2 Firmware Compilation & Flashing Evidence
```bash
# Firmware build command:
source /home/aryan/.espressif/v6.0.1/esp-idf/export.sh
idf.py -DSDKCONFIG=/home/aryan/Projects/SPIT/NEXUS/credentials/sdkconfig.local build

# Flash command:
idf.py -p /dev/ttyUSB0 flash
```
- **Firmware Size:** 1,223,760 bytes (58% of 2MB app partition).
- **Boot Verification:** ESP32 booted cleanly into FreeRTOS with dual-transport initialization:
  - Serial transport active at 115200 baud.
  - Wi-Fi connected to AP `TP-Link_28B4`, IP: `10.12.252.33`.
  - MQTT client connected to broker `10.12.252.18:1883`.

---

## 5. Ground Station & Mission Control Web Application

### 5.1 Backend Fixes (`server.py` & `router.py`)
1. **JSON Serialization Resolution:** Fixed `TypeError: Object of type mappingproxy is not JSON serializable` in `_send_json` by providing `default=lambda o: dict(o) if hasattr(o, "items") else str(o)`.
2. **Comprehensive Audit Recording:** Guaranteed that `_record_history` is called for every outcome:
   - Unknown verbs/nouns
   - Unsupported commands (unmounted hardware)
   - Parameter validation errors
   - Missing dangerous confirmation tokens
   - Transport routing failures
   - In-flight timeouts
   - Successful firmware acknowledgments

### 5.2 Frontend UI Enhancements (`index.html` & `app.js`)
1. **Global Transport Selector:** Added an interactive selector dropdown in the persistent header (`AUTO (Prefer Active)`, `USB Serial`, `MQTT / Wi-Fi`), synchronized across the application and command console.
2. **Command & Response Audit Trail Table:** Added the **Route** column, displaying exactly which transport route delivered each command (`serial`, `mqtt`, or `sim`).
3. **Truthful Sensor Representations:** 
   - Labeled CD4051 X0 as `INFRARED SENSOR (IR-1)`.
   - Labeled CD4051 X1 as `MAGNETIC SENSOR (HALL)` with a prominent `NOT INSTALLED` tag.
4. **Quick Actuation Controls:** Added one-click buttons for Buzzer (200ms, 500ms, Off) and LEDs 1–4 (ON/OFF), immediately dispatching over the selected transport.

### 5.3 Antigravity Browser Verification
The Mission Control application was tested using the Antigravity browser automation subagent:
- **Recording Artifact:** `nexus_mission_control_1792924808004.webp`
- **Verified Flows:**
  - Header displays `NEXUS MISSION CONTROL`, node `nexus_esp32`, connection `CONNECTED`, route `DUAL`.
  - Sensor cards update in real-time.
  - Transport selector persists selection across tab switches.
  - Quick Action button for LED 1 dispatched `ACTUATE LED 1 ON` over Serial, observed immediate green response banner with code `0`, and followed with `ACTUATE LED 1 OFF`.
  - Hardware manifest accurately categorizes mounted vs unmounted hardware.
  - Audit Trail table renders timestamp, sequence number, route, type, verb, noun, status, code, and execution details.

---

## 6. Grafana Telemetry Dashboard Overhaul

### 6.1 Dashboard Refactoring (`grafana/dashboards/nexus_telemetry.json`)
- **Title:** Updated to `NEXUS Environmental Telemetry & Operations`.
- **Milestone Terminology Removal:** Removed all occurrences of `M9`, `M10`, and internal development tags.
- **Dynamic Transport Filtering:** Added dashboard variable `transport`:
  - Options: `All`, `serial`, `mqtt`.
  - Query Filter: `|> filter(fn: (r) => r["transport"] =~ /^${transport:regex}$/)`.
- **Operational Loop Frequency:** Replaced raw `exec_ticks` with Flux derivative query:
  ```flux
  from(bucket: "nexus_telemetry")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r["_measurement"] == "nexus_hb")
    |> filter(fn: (r) => r["_field"] == "exec_ticks")
    |> filter(fn: (r) => r["transport"] =~ /^${transport:regex}$/)
    |> derivative(unit: 1s, nonNegative: true)
  ```
  Resulting visualization accurately renders the FreeRTOS 100ms executive period (~10.0 Hz).
- **Sensor Naming:**
  - Panel `Infrared Sensor IR-1 (CD4051 X0 Raw ADC)`
  - Panel `Hall Magnetic Sensor (Not Installed)`

---

## 7. Systematic Command Test Matrix (115 Commands)

A test automation runner (`scripts/test_command_matrix.py`) dispatched all 115 registered commands defined in the canonical command registry against the live system.

### 7.1 Summary of Results

```
======================================================================
                  NEXUS COMMAND MATRIX TEST RESULTS                  
======================================================================
  Total Registered Commands:  115
  Commands Tested:            115
  Commands Passed:            115
  Commands Failed:              0
  Pass Rate:               100.0%
======================================================================
```

### 7.2 Results Breakdown by Category

| Category | Count | Tested Behavior | Observed Outcome | Status |
| :--- | :---: | :--- | :--- | :---: |
| **SAFE_CONTROL** | 53 | Parameter validation & dispatch | Dispatched / Handled | **PASSED** |
| **READ_ONLY** | 41 | Telemetry & state queries | Data returned (`completed`, code 0) | **PASSED** |
| **UNMOUNTED_HARDWARE** | 10 | Rejection of unmounted parts | Truthfully rejected (`unsupported`, code 3) | **PASSED** |
| **HAZARDOUS_DESTRUCTIVE** | 9 | Rejection without confirmation | Safety rejected (`rejected`, code 7) | **PASSED** |
| **PHYSICAL_ACTUATOR** | 2 | Physical LED / Buzzer drive | Executed & acknowledged (`completed`, code 0) | **PASSED** |

Detailed JSON test results were saved to `docs/validation/command_matrix_results.json`.

---

## 8. Automated Test Suites

### 8.1 Host C Unit Tests
The Milestone 8 Host Unit Test suite was compiled and executed natively:
```bash
gcc -I... -DNEXUS_HOST_TEST tests/test_milestone8_host.c ... -o build_test_milestone8
./build_test_milestone8
```
- **Test Suites Executed:** 7
- **Test Suites Passed:** 7 (100%)
- **Suites:** Registry, Dispatcher, Serialization, Deserialization, Validation, Router, Safety Invariants.

### 8.2 Python Ground Station Test Suite
The complete Pytest regression test suite was executed:
```bash
pytest -v ground_station/tests/
```
- **Total Tests Collected:** 237
- **Passed:** 237 (100%)
- **Failed:** 0
- **Duration:** 10.42s

---

## 9. Open WebUI Integration

- **Host Instance:** Running on port 8080.
- **Account Verification:** Local account `Obliv1on` (admin@localhost) was verified intact in SQLite database `webui.db`. Personal settings, conversations, and account configurations were left undisturbed.
- **Telemetry Tools Registration:** The 9 read-only NEXUS telemetry tools were verified and registered via `ground_station/ai/register_open_webui.py`:
  1. `nexus_get_environmental_telemetry`
  2. `nexus_get_system_status`
  3. `nexus_get_sensor_manifest`
  4. `nexus_get_transport_stats`
  5. `nexus_get_ultrasonic_distance`
  6. `nexus_get_ambient_light`
  7. `nexus_get_optical_slot_state`
  8. `nexus_get_infrared_level`
  9. `nexus_get_command_audit_trail`

---

## 10. Git Status & Safety Assurance

Per instructions, no Git commits or staged changes were introduced.
```
$ git status
On branch main
Changes not staged for commit:
  firmware/main/command/nexus_command_dispatcher.c
  firmware/main/command/nexus_command_registry.c
  firmware/main/command/nexus_command_registry.h
  firmware/main/transports/nexus_connection_manager.c
  firmware/main/transports/nexus_envelope.c
  grafana/dashboards/nexus_telemetry.json
  ground_station/command_router/application_launcher.py
  ground_station/command_router/command_registry.py
  ground_station/command_router/router.py
  ground_station/connection_manager/mqtt_adapter.py
  ground_station/connection_manager/nexus_host_manager.py
  ground_station/connection_manager/serial_adapter.py
  ground_station/tests/test_command_registry.py
  tests/test_milestone8_host.c

Untracked files:
  docs/validation/command_matrix_results.json
  docs/validation/system_qualification_and_recovery_report_20261025.md
  ...
no changes added to commit (use "git add" and/or "git commit -a")
```

---

## 11. Conclusion

The NEXUS / EDU_ROBO V14 platform is fully operational, hardened, and verified. 
- Infrastructure is clean and container persistence is proven.
- Physical actuators operate reliably without side effects on unmounted hardware.
- Both USB Serial and MQTT / Wi-Fi transports provide robust dual-redundant command and telemetry paths.
- All telemetry dashboards, mission control controls, and audit logs are truthful, real-time, and production-ready.
