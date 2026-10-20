# NEXUS — Milestone 8: Canonical Command Engine, Bidirectional Protocol, and Laptop Application Launcher

## 1. Milestone Overview

Milestone 8 establishes the complete, secure, bidirectional command capability for **NEXUS** (*Networked Environmental eXecutive with Unified Sensing*). Building upon the dual-transport telemetry pipeline (Milestone 6) and deterministic monitoring engine (Milestone 7), Milestone 8 enables both host-to-device remote control and board-to-laptop application launching through a unified, version-controlled command protocol.

The end-to-end command architecture operates across two primary paths:

### Path A: Laptop Operator to ESP32 Firmware Command Path
$$\text{Ground Station / Operator} \longrightarrow \text{Command Router} \longrightarrow \text{Serial / MQTT Transport} \longrightarrow \text{Connection Manager RX Callback}$$
$$\big\downarrow$$
$$\text{ESP32 Command Dispatcher} \longrightarrow \text{Handler Execution} \longrightarrow \text{Bounded Structured Response Envelope} \longrightarrow \text{TX Queue}$$

### Path B: ESP32 Firmware to Laptop Application Launcher Path
$$\text{ESP32 Event / Command Source} \longrightarrow \text{Protocol v1 Envelope} \longrightarrow \text{Serial / MQTT Transport} \longrightarrow \text{Ground Station Host Manager}$$
$$\big\downarrow$$
$$\text{Command Router} \longrightarrow \text{Safe Application Launcher} \longrightarrow \text{URL Security Validation \& Cooldown} \longrightarrow \text{Host Browser / Application}$$

---

## 2. Command Origin and Physical Boundary Analysis

A critical requirement of Milestone 8 is explicitly separating command origin, transport directionality, and physical board input capabilities:

1. **ESP32-Originated Command**: The ESP32 firmware formats an outbound command envelope (e.g. `{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd","verb":"OPEN","noun":"DASHBOARD"}`) and enqueues it to the Connection Manager for delivery across serial or MQTT. The Ground Station ingests this envelope and invokes the safe application launcher.
2. **Laptop-Originated Command**: The operator or Ground Station constructs an outbound command envelope (e.g. `GET STATUS` or `DISPLAY SENSORS`) and transmits it across serial or MQTT. The firmware Connection Manager receives it, validates framing, dispatches it to the registered handler, and returns a structured response envelope.
3. **Physically Entered Board Command (Hardware Gap)**:
   - **Hardware Inspection**: Detailed schematic inspection of `docs/PROJECT_BLUEPRINT.md` and `docs/SPEC_SHEET.md` confirms that no board-mounted keypad, pushbuttons, or rotary encoder currently exist on the hardware.
   - **GPIO1 Conflict**: A TSOP1838 IR receiver is soldered to GPIO1. However, on the ESP32-WROOM-32 module, GPIO1 is the primary hardware UART0 TX pin used for critical USB serial console output and transport communication. Repurposing or pulsing GPIO1 as an active IR input pin would corrupt UART0 transmission and destabilize serial communication.
   - **Physical Boundary Conclusion**: In Milestone 8, software command architectures for both ESP32-originated and host-originated commands are fully implemented and verified. The physical board-side input mechanism remains an identified hardware gap deferred to a future hardware iteration, avoiding unsafe pin rewiring or hardware modifications.

---

## 3. Canonical Command Registry Matrix

The candidate inventory of 52 verb-noun pairs from `docs/PROJECT_BLUEPRINT.md` was reconciled against source requirements, architectural safety boundaries, and current hardware capabilities. Every command is uniquely identified by a deterministic 16-bit identifier:

$$\text{cmd\_id} = (\text{verb\_code} \ll 8) \mid \text{noun\_code}$$

### Canonical Command Registry Table (All 52 Candidates)

| Command Name | Verb | Noun | Verb Code | Noun Code | Command ID | Milestone Disposition | Target Destination | Handler / Implementation | Test Reference |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|:---|
| `NOP NONE` | `NOP` | `NONE` | `0x00` | `0x00` | `0x0000` (0) | **REQUIRED_M8** | Firmware | `handle_nop_none` | C Test 2, PyTest |
| `INITIALIZE SYSTEM` | `INITIALIZE` | `SYSTEM` | `0x01` | `0x01` | `0x0101` (257) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `INITIALIZE SENSORS` | `INITIALIZE` | `SENSORS` | `0x01` | `0x02` | `0x0102` (258) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `INITIALIZE TRANSPORTS` | `INITIALIZE` | `TRANSPORTS` | `0x01` | `0x03` | `0x0103` (259) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `START SYSTEM` | `START` | `SYSTEM` | `0x02` | `0x01` | `0x0201` (513) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `START SENSORS` | `START` | `SENSORS` | `0x02` | `0x02` | `0x0202` (514) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `START TELEMETRY` | `START` | `TELEMETRY` | `0x02` | `0x03` | `0x0203` (515) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `START SELF_TEST` | `START` | `SELF_TEST` | `0x02` | `0x04` | `0x0204` (516) | **REQUIRED_M8** | Firmware | `handle_run_self_test` | C Test 2 |
| `STOP SENSORS` | `STOP` | `SENSORS` | `0x03` | `0x02` | `0x0302` (770) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `STOP TELEMETRY` | `STOP` | `TELEMETRY` | `0x03` | `0x03` | `0x0303` (771) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `RESET FAULTS` | `RESET` | `FAULTS` | `0x04` | `0x01` | `0x0401` (1025) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `RESET STATISTICS` | `RESET` | `STATISTICS` | `0x04` | `0x02` | `0x0402` (1026) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `SET PRIORITY` | `SET` | `PRIORITY` | `0x05` | `0x01` | `0x0501` (1281) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `SET SAMPLE_INTERVAL` | `SET` | `SAMPLE_INTERVAL` | `0x05` | `0x02` | `0x0502` (1282) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `SET THRESHOLD` | `SET` | `THRESHOLD` | `0x05` | `0x03` | `0x0503` (1283) | **UNSUPPORTED** | Firmware | Safe rejection (Code 3) | C Test 4 |
| `GET STATUS` | `GET` | `STATUS` | `0x06` | `0x01` | `0x0601` (1537) | **REQUIRED_M8** | Firmware | `handle_get_status` | C Test 2, PyTest |
| `GET CONFIGURATION` | `GET` | `CONFIGURATION` | `0x06` | `0x02` | `0x0602` (1538) | **REQUIRED_M8** | Firmware | `handle_get_configuration` | C Test 2, PyTest |
| `GET SENSOR_LIST` | `GET` | `SENSOR_LIST` | `0x06` | `0x03` | `0x0603` (1539) | **REQUIRED_M8** | Firmware | `handle_get_sensor_list` | C Test 2, PyTest |
| `GET TIME` | `GET` | `TIME` | `0x06` | `0x04` | `0x0604` (1540) | **REQUIRED_M8** | Firmware | `handle_get_time` | C Test 2, PyTest |
| `DISPLAY STATUS` | `DISPLAY` | `STATUS` | `0x10` | `0x01` | `0x1001` (4097) | **REQUIRED_M8** | Firmware | `handle_display_status` | C Test 3, PyTest |
| `DISPLAY EXECUTIVE` | `DISPLAY` | `EXECUTIVE` | `0x10` | `0x02` | `0x1002` (4098) | **REQUIRED_M8** | Firmware | `handle_display_executive` | C Test 3 |
| `DISPLAY QUEUES` | `DISPLAY` | `QUEUES` | `0x10` | `0x03` | `0x1003` (4099) | **REQUIRED_M8** | Firmware | `handle_display_queues` | C Test 3 |
| `DISPLAY FAULTS` | `DISPLAY` | `FAULTS` | `0x10` | `0x04` | `0x1004` (4100) | **REQUIRED_M8** | Firmware | `handle_display_faults` | C Test 3 |
| `DISPLAY ENVIRONMENT` | `DISPLAY` | `ENVIRONMENT` | `0x10` | `0x41` | `0x1041` (4161) | **REQUIRED_M8** | Firmware | `handle_display_environment` | C Test 3 |
| `DISPLAY LIGHT` | `DISPLAY` | `LIGHT` | `0x10` | `0x42` | `0x1042` (4162) | **REQUIRED_M8** | Firmware | `handle_display_light` | C Test 3 |
| `DISPLAY DISTANCE` | `DISPLAY` | `DISTANCE` | `0x10` | `0x43` | `0x1043` (4163) | **DEFERRED_M9_M10** | Firmware | Safe rejection (HC-SR04 not present) | C Test 4 |
| `DISPLAY ANALOG` | `DISPLAY` | `ANALOG` | `0x10` | `0x44` | `0x1044` (4164) | **REQUIRED_M8** | Firmware | `handle_display_analog` | C Test 3 |
| `DISPLAY MOTION` | `DISPLAY` | `MOTION` | `0x10` | `0x45` | `0x1045` (4165) | **DEFERRED_M9_M10** | Firmware | Safe rejection (PIR not present) | C Test 4 |
| `DISPLAY EVENTS` | `DISPLAY` | `EVENTS` | `0x10` | `0x46` | `0x1046` (4166) | **REQUIRED_M8** | Firmware | `handle_display_events` | C Test 3 |
| `HISTORY EVENTS` | `HISTORY` | `EVENTS` | `0x11` | `0x01` | `0x1101` (4353) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Host incidents.db) | C Test 4 |
| `HISTORY FAULTS` | `HISTORY` | `FAULTS` | `0x11` | `0x02` | `0x1102` (4354) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Host incidents.db) | C Test 4 |
| `HISTORY EXECUTIVE` | `HISTORY` | `EXECUTIVE` | `0x11` | `0x03` | `0x1103` (4355) | **DEFERRED_M9_M10** | Firmware | Safe rejection (M9/M10 scheduler history) | C Test 4 |
| `HISTORY ENVIRONMENT`| `HISTORY` | `ENVIRONMENT` | `0x11` | `0x41` | `0x1141` (4417) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Host InfluxDB) | C Test 4 |
| `HISTORY SENSORS` | `HISTORY` | `SENSORS` | `0x11` | `0x42` | `0x1142` (4418) | **DEFERRED_M9_M10** | Firmware | Safe rejection (Host InfluxDB) | C Test 4 |
| `DIAGNOSTICS SYSTEM` | `DIAGNOSTICS` | `SYSTEM` | `0x18` | `0x01` | `0x1801` (6145) | **REQUIRED_M8** | Firmware | `handle_diagnostics_system` | C Test 3, PyTest |
| `DIAGNOSTICS SENSORS`| `DIAGNOSTICS` | `SENSORS` | `0x18` | `0x02` | `0x1802` (6146) | **REQUIRED_M8** | Firmware | `handle_diagnostics_sensors`| C Test 3 |
| `DIAGNOSTICS QUEUES` | `DIAGNOSTICS` | `QUEUES` | `0x18` | `0x03` | `0x1803` (6147) | **REQUIRED_M8** | Firmware | `handle_diagnostics_queues` | C Test 3 |
| `DIAGNOSTICS TIMING` | `DIAGNOSTICS` | `TIMING` | `0x18` | `0x04` | `0x1804` (6148) | **REQUIRED_M8** | Firmware | `handle_diagnostics_timing` | C Test 3 |
| `DIAGNOSTICS MEMORY` | `DIAGNOSTICS` | `MEMORY` | `0x18` | `0x05` | `0x1805` (6149) | **REQUIRED_M8** | Firmware | `handle_diagnostics_memory` | C Test 3 |
| `DIAGNOSTICS TRANSPORTS`|`DIAGNOSTICS`| `TRANSPORTS`| `0x18` | `0x06` | `0x1806` (6150) | **REQUIRED_M8** | Firmware | `handle_diagnostics_transports`| C Test 3 |
| `OPEN DASHBOARD` | `OPEN` | `DASHBOARD` | `0x1E` | `0x01` | `0x1E01` (7681) | **REQUIRED_M8** | Ground Station | `ApplicationLauncher.launch("DASHBOARD")` | C Test 6, PyTest |
| `OPEN LOGS` | `OPEN` | `LOGS` | `0x1E` | `0x02` | `0x1E02` (7682) | **REQUIRED_M8** | Ground Station | `ApplicationLauncher.launch("LOGS")` | C Test 6, PyTest |
| `OPEN AI` | `OPEN` | `AI` | `0x1E` | `0x03` | `0x1E03` (7683) | **REQUIRED_M8** | Ground Station | `ApplicationLauncher.launch("AI")` | C Test 6, PyTest |
| `OPEN GROUND` | `OPEN` | `GROUND` | `0x1E` | `0x04` | `0x1E04` (7684) | **REQUIRED_M8** | Ground Station | `ApplicationLauncher.launch("GROUND")` | C Test 6, PyTest |
| `ASK SYSTEM` | `ASK` | `SYSTEM` | `0x1F` | `0x01` | `0x1F01` (7937) | **DEFERRED_M9_M10** | Ground Station | Safe rejection (M9/M10 AI tool routing) | PyTest Router |
| `ASK ENVIRONMENT` | `ASK` | `ENVIRONMENT` | `0x1F` | `0x41` | `0x1F41` (8001) | **DEFERRED_M9_M10** | Ground Station | Safe rejection (M9/M10 AI tool routing) | PyTest Router |
| `ASK SENSOR` | `ASK` | `SENSOR` | `0x1F` | `0x42` | `0x1F42` (8002) | **DEFERRED_M9_M10** | Ground Station | Safe rejection (M9/M10 AI tool routing) | PyTest Router |
| `EXPORT TELEMETRY` | `EXPORT` | `TELEMETRY` | `0x20` | `0x01` | `0x2001` (8193) | **DEFERRED_M9_M10** | Ground Station | Safe rejection (Host InfluxDB exporter) | PyTest Router |
| `EXPORT DIAGNOSTICS`| `EXPORT` | `DIAGNOSTICS` | `0x20` | `0x02` | `0x2002` (8194) | **DEFERRED_M9_M10** | Ground Station | Safe rejection (Host InfluxDB exporter) | PyTest Router |
| `RUN SELF_TEST` | `RUN` | `SELF_TEST` | `0x21` | `0x01` | `0x2101` (8449) | **REQUIRED_M8** | Firmware | `handle_run_self_test` | C Test 2 |
| `RUN SENSOR_TEST` | `RUN` | `SENSOR_TEST` | `0x21` | `0x02` | `0x2102` (8450) | **REQUIRED_M8** | Firmware | `handle_run_sensor_test` | C Test 2 |
| `RUN STRESS_TEST` | `RUN` | `STRESS_TEST` | `0x21` | `0x03` | `0x2103` (8451) | **UNSUPPORTED** | Test Harness | Safe rejection (Controlled harness only) | C Test 4 |

---

## 4. Firmware Implementation

### Architectural Modules
The firmware command subsystem resides in `firmware/main/command/`:
- [`nexus_command_registry.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_registry.h) / [`nexus_command_registry.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_registry.c): Authoritative definitions of verbs, nouns, 16-bit IDs, milestone dispositions, and lookup APIs (`nexus_cmd_registry_lookup_by_id`, `nexus_cmd_registry_lookup_by_name`).
- [`nexus_command_dispatcher.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_dispatcher.h) / [`nexus_command_dispatcher.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_dispatcher.c): Envelope validation, parameter range checking, handler execution, structured response generation, and integration callback `nexus_command_dispatcher_rx_callback`.

### Safety Constraints & Invariants
1. **Zero Dynamic Allocation**: All command parsing and response envelope formatting uses fixed-size stack buffers bounded strictly to `NEXUS_ENVELOPE_MAX_LEN` (256 bytes).
2. **Scheduling Isolation**: Command dispatch executes synchronously within the Connection Manager RX callback context and never blocks the 50 ms Executive cyclic scheduling tasks.
3. **No Arbitrary Shell/Register Operations**: Only registered verb-noun handlers are callable; raw addresses, memory offsets, and GPIO assignments cannot be altered via commands.
4. **Transport Response Routing**: Responses to incoming commands are automatically enqueued to the Connection Manager TX queue with routing policies matching the source transport (`SERIAL_ONLY` for serial commands, `MQTT_ONLY` for MQTT commands).

---

## 5. Ground Station Application Launcher and Router

### Module Architecture
The Ground Station command infrastructure resides in `ground_station/command_router/`:
- [`command_registry.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/command_router/command_registry.py): Exact 1-to-1 Python parity with C registry, providing verified ID mapping, envelope construction, and validation helpers.
- [`application_launcher.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/command_router/application_launcher.py): Safe launcher for allowlisted actions (`DASHBOARD`, `LOGS`, `AI`, `GROUND`).
- [`router.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/command_router/router.py): Bidirectional command routing, telemetry accounting, pending response tracking, and error isolation.

### Security and Sandboxing Rules
- **Explicit URL Allowlist**: Permitted schemes (`http`, `https`), permitted hosts (`localhost`, `127.0.0.1`, `10.12.252.18`), and permitted ports (`80`, `443`, `3000`, `8000`, `8080`, `9090`).
- **No Arbitrary Shell Execution**: Absolutely no `subprocess.Popen(..., shell=True)` or `os.system()` calls. All browser launches use `webbrowser.open_new_tab()`.
- **Idempotency Cooldown**: Repeated identical launch requests within the configurable cooldown window (default 2.0s) are safely suppressed (`duplicate_suppressed=True`), avoiding browser window/tab exhaustion while returning an honest success confirmation.
- **Service Reachability**: Includes fast TCP connection probing (`connect_ex`) to verify destination endpoint health without blocking launcher execution.

---

## 6. Verification and Acceptance Evidence

### A. C Host Unit Tests (C99 / GCC)
The Milestone 8 host test harness (`tests/test_milestone8_host.c`) compiles and executes all 7 test categories natively:
```bash
gcc -Wall -Wextra -Werror -I firmware/main -I firmware/main/command -I firmware/main/transports -I firmware/main/data_structures -I firmware/main/executive -I firmware/main/sensors firmware/main/command/*.c firmware/main/transports/*.c firmware/main/data_structures/*.c firmware/main/executive/*.c firmware/main/sensors/*.c tests/test_milestone8_host.c -o tests/test_milestone8_host -lpthread && ./tests/test_milestone8_host
```
**Results**:
- `test_registry_integrity`: 52/52 commands verified, 0 duplicate IDs, 0 duplicate verb-noun pairs. **PASS**
- `test_supported_commands_execution`: Valid execution of NOP, GET STATUS, GET CONFIGURATION, GET SENSOR_LIST, GET TIME, RUN SELF_TEST, RUN SENSOR_TEST. **PASS**
- `test_display_and_diagnostics_handlers`: All 8 DISPLAY and DIAGNOSTICS handlers executed with validated responses. **PASS**
- `test_unsupported_and_deferred_commands_rejection`: Safe rejection of all unsupported and deferred commands with code 3. **PASS**
- `test_input_validation_and_malformed_rejection`: Corrupt JSON, missing fields, out-of-range bounds, oversized payloads rejected. **PASS**
- `test_bounded_response_and_open_formatting`: Strict 256-byte bounds and ESP32-originated OPEN formatting verified. **PASS**
- `test_connection_manager_rx_callback_integration`: Serial/MQTT RX callback parsing, response TX enqueueing, and queue draining verified. **PASS**

### B. Previous Milestone Host Tests Regression Suite
- Milestone 2 (`tests/test_milestone2_host`): **5/5 passed**
- Milestone 3 (`tests/test_milestone3_host`): **11/11 passed**
- Milestone 4 (`tests/test_milestone4_host`): **15/15 passed**
- Milestone 8 (`tests/test_milestone8_host`): **7/7 passed**
**Total C Host Tests**: **38/38 passed (100%)**

### C. Ground Station Pytest Suite
```bash
.venv/bin/pytest ground_station/tests/
```
**Results**:
- Baseline tests: 191 passed
- New M8 test suites:
  - `ground_station/tests/test_command_registry.py`: 7 passed
  - `ground_station/tests/test_application_launcher.py`: 10 passed
  - `ground_station/tests/test_command_router.py`: 7 passed
**Total Python Tests**: **215/215 passed in 5.35s (100%)**

### D. ESP-IDF Firmware Compilation
```bash
idf.py build
```
**Result**: Clean compilation of `nexus.bin` (0xe1ca0 bytes, 12% free in partition). Zero compiler warnings with `-Wall -Wextra -Werror`.
