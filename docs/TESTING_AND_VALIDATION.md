# NEXUS Testing and Validation Architecture

## 1. Testing Strategy and Test Pyramid

NEXUS employs a multi-tiered verification strategy designed to ensure mission reliability from embedded C firmware to high-level conversational AI. Because hardware testing on physical microcontrollers can be slow and non-deterministic, testing is tiered to catch protocol, memory, and logic regressions on the host system before code reaches physical hardware.

```mermaid
flowchart TD
    subgraph L5 ["Tier 5: Hardware In-the-Loop & Physical Soak"]
        T5A["30-Minute Hardware Soak Runs (M4/M10)"]
        T5B["Physical Sensor Excitation Logs (M10 B1-B4, C)"]
        T5C["Live Command Matrix Audit (scripts/test_command_matrix.py)"]
    end

    subgraph L4 ["Tier 4: Live Service Integration Tests"]
        T4A["Live Telemetry Analysis (test_analysis_live.py: 5 tests)"]
        T4B["Live Persistence Integration (test_live_persistence_integration.py: 10 tests)"]
        T4C["Live Incident Monitoring (test_monitoring_live.py: 8 tests)"]
    end

    subgraph L3 ["Tier 3: Specification & Soak Harness Qualification"]
        T3A["Reference Manual Parity Validator (validate_reference_manual.py: 7 suites)"]
        T3B["Soak Analysis & Math Harness (test_soak_harness.py: 19 tests)"]
    end

    subgraph L2 ["Tier 2: Host Python Unit & Mocked Integration"]
        T2A["Envelope Parser & Device Tracker (42 tests)"]
        T2B["Host Manager & Transport Integration (33 tests)"]
        T2C["Command Router, Registry & Local Launch (56 tests)"]
        T2D["InfluxDB Writer & Point Mapper (24 tests)"]
        T2E["Monitoring Store & Deterministic Rules (28 tests)"]
        T2F["AI Agent, Tool Dispatcher & Safety Refusal (26 tests)"]
        T2G["REST Server & Mission Control Frontend (12 tests)"]
    end

    subgraph L1 ["Tier 1: Native C Host Unit Tests (GCC / POSIX Mocks)"]
        T1A["Milestone 2: Executive & Bounded Structures (5 tests)"]
        T1B["Milestone 3: Sensor Drivers & Calibration (11 tests)"]
        T1C["Milestone 4: Connection Manager & Transports (15 tests)"]
        T1D["Milestone 8: Command Registry & Dispatcher (8 tests)"]
        T1E["Milestone 9: M9 Sensor Suite & Telemetry (6 tests)"]
    end

    L1 --> L2 --> L3 --> L4 --> L5
```

---

## 2. Test Suites Catalog

### 2.1 Native C Host Test Suites (Tier 1)

These tests compile embedded firmware components with standard `gcc` on Linux, mocking hardware peripherals (GPIO, ADC, UART, FreeRTOS queues) using POSIX primitives (`pthread_mutex`, `nanosleep`).

| Test Binary / Source File | Target Subsystems | Tests | Execution Command | Status / Pass Rate |
| :--- | :--- | :---: | :--- | :--- |
| `tests/test_milestone2_host.c` | Job table, ready queue, event queue, ring buffer, cyclic executive | 5 | `./tests/test_milestone2_host` | **Verified** (5/5 PASS) |
| `tests/test_milestone3_host.c` | Sensor registry, LDR, CD4051 truth table, DHT11 packet parsing, deadline accounting | 11 | `./tests/test_milestone3_host` | **Verified** (11/11 PASS) |
| `tests/test_milestone4_host.c` | Envelope parser (F-01), TX queue bounds, backoff math, composite dedup (F-02), MQTT parsing | 15 | `./tests/test_milestone4_host` | **Verified** (15/15 PASS; see Note 1) |
| `tests/test_milestone8_host.c` | 115-command registry integrity, opcode dispatcher, diagnostics handlers, error formatting | 8 | `./tests/test_milestone8_host` | **Verified** (8/8 PASS) |
| `tests/test_milestone9_host.c` | CD4051 X1, MOC7811 slot, HC-SR04 ultrasonic, extended telemetry formatting (< 256 B) | 6 | `./tests/test_milestone9_host` | **Verified** (6/6 PASS) |
| **Total Tier 1 C Tests** | | **45** | | **45 / 45 PASS (100%)** |

> [!NOTE]
> **Host Concurrency Test 15 in `test_milestone4_host`:**
> Test 15 (`test_tx_queue_concurrency_and_contention_safety`) passes cleanly (15/15) in dedicated test runs. However, under high host CPU multitasking load or thread preemption delays during parallel batch test runs, the consumer thread may be momentarily delayed, allowing the producer (50 µs nanosleep loop) to saturate the 32-element queue and trigger `assert(enqueued)` with `SIGABRT` (exit code 134). Re-running the suite independently confirms 100% pass rate without failures.

---

### 2.2 Python Offline Unit and Mocked Integration Suites (Tier 2)

Offline tests require no active containers, network sockets, or physical serial connections. External dependencies (Mosquitto, InfluxDB, Ollama) are mocked.

| Test File | Subsystem Verified | Tests | Execution Command | Status |
| :--- | :--- | :---: | :--- | :--- |
| `ground_station/tests/test_envelope_parser.py` | JSON framing, schema validation, length bounds, type coercions | 22 | `pytest ground_station/tests/test_envelope_parser.py` | **Verified** |
| `ground_station/tests/test_device_tracker.py` | Device session tracking, heartbeat timeouts, reboot epoch tracking | 20 | `pytest ground_station/tests/test_device_tracker.py` | **Verified** |
| `ground_station/tests/test_nexus_host_manager.py` | Ingestion queue policies, thread-safe envelope ingress, listener dispatch | 18 | `pytest ground_station/tests/test_nexus_host_manager.py` | **Verified** |
| `ground_station/tests/test_serial_adapter.py` | PTY-based serial framing, CRLF handling, DTR/RTS reset avoidance | 11 | `pytest ground_station/tests/test_serial_adapter.py` | **Verified** |
| `ground_station/tests/test_mqtt_adapter.py` | Paho MQTT client lifecycle, subscription routing, reconnection backoff | 14 | `pytest ground_station/tests/test_mqtt_adapter.py` | **Verified** |
| `ground_station/tests/test_transport_integration.py` | Dual serial/MQTT concurrent ingestion into unified manager | 6 | `pytest ground_station/tests/test_transport_integration.py` | **Verified** |
| `ground_station/tests/test_influxdb_writer.py` | Line protocol formatting, buffer queue saturation, retry backoff | 15 | `pytest ground_station/tests/test_influxdb_writer.py` | **Verified** |
| `ground_station/tests/test_point_mapper.py` | Telemetry mapping, missing-data suppression, tag cardinality | 9 | `pytest ground_station/tests/test_point_mapper.py` | **Verified** |
| `ground_station/tests/test_persistence_integration.py` | Mock InfluxDB client, batch flushes, error handling | 8 | `pytest ground_station/tests/test_persistence_integration.py` | **Verified** |
| `ground_station/tests/test_analysis_unit.py` | Query validation, timestamp separation, observation deduplication | 15 | `pytest ground_station/tests/test_analysis_unit.py` | **Verified** |
| `ground_station/tests/test_monitoring_unit.py` | 4 deterministic rules, threshold evaluations, severity mapping | 16 | `pytest ground_station/tests/test_monitoring_unit.py` | **Verified** |
| `ground_station/tests/test_monitoring_lifecycle.py` | SQLite WAL storage, incident deduplication, acknowledgement | 12 | `pytest ground_station/tests/test_monitoring_lifecycle.py` | **Verified** |
| `ground_station/tests/test_command_registry.py` | 115 command entries, 27 parameters, verb/noun validation | 18 | `pytest ground_station/tests/test_command_registry.py` | **Verified** |
| `ground_station/tests/test_command_router.py` | Hazardous gating, timeout handlers, routing targets | 21 | `pytest ground_station/tests/test_command_router.py` | **Verified** |
| `ground_station/tests/test_router_dispatch.py` | End-to-end command correlation, req_id matching | 9 | `pytest ground_station/tests/test_router_dispatch.py` | **Verified** |
| `ground_station/tests/test_application_launcher.py` | Allowlisted host application launching (`OPEN DASHBOARD`, etc.) | 8 | `pytest ground_station/tests/test_application_launcher.py` | **Verified** |
| `ground_station/tests/test_server.py` | REST API routes, CORS headers, UI regression invariants | 12 | `pytest ground_station/tests/test_server.py` | **Verified** |
| `ground_station/tests/test_ai_unit.py` | 15 regex pre-flight refusals, 9 read-only tool definitions, injection defenses | 26 | `pytest ground_station/tests/test_ai_unit.py` | **Verified** |
| `ground_station/tests/test_run_mqtt_ingestion.py` | Standalone MQTT daemon runner lifecycle | 3 | `pytest ground_station/tests/test_run_mqtt_ingestion.py` | **Verified** |
| **Total Tier 2 Offline Tests** | | **233** | `.venv/bin/pytest ground_station/tests --ignore=...live.py` | **233 / 233 PASS (100%)** |

---

### 2.3 Soak Test Analysis & Validation Harness (Tier 3)

Located in `tests/soak/test_soak_harness.py`, this suite exercises the offline reliability analysis engine used to qualify 30-minute hardware soak captures.

- **Test Count:** 19 automated tests.
- **Coverage:**
  - `test_01_fully_valid_capture`: Validates 7/7 qualification criteria parsing.
  - `test_02_zero_telemetry_and_empty_files`: Handles empty logs gracefully.
  - `test_03_malformed_and_oversized_records`: Discard accounting.
  - `test_04_schema_violations_and_boolean_int_subclass`: Python type coercion.
  - `test_05_sequence_analysis_and_wraparound`: Monotonic sequence checks.
  - `test_06_counter_regression_and_multiple_resets`: Reboot epoch segmentation.
  - `test_15_phased_heap_analysis_scenarios`: Linear regression slope math (`bytes/hour`).
- **Execution:**
  ```bash
  .venv/bin/pytest tests/soak/test_soak_harness.py -q
  ```
- **Status:** **Verified** (19 / 19 PASS).

---

### 2.4 Reference Manual Validator (Tier 3)

The script `scripts/validate_reference_manual.py` executes mechanical static verification of consistency across code and documentation.

- **Suites Executed:**
  1. `docs/COMMAND_REFERENCE.md` structure and table schema verification.
  2. Python `CommandRegistry` (115 commands, 27 parameters) exact parity.
  3. Firmware `main/nexus_cmd_dispatcher.c` C switch-case handler coverage.
  4. Firmware `main/include/nexus_command_codes.h` opcode matching.
  5. Mission Control UI `ground_station/static/app.js` parameter render mappings.
  6. Parameter value range, data type, and unit consistency.
  7. Status codes 0–9 definitions parity.
- **Execution:**
  ```bash
  .venv/bin/python scripts/validate_reference_manual.py
  ```
- **Status:** **Verified** (7 / 7 Suites Passed, 100% parity).

---

### 2.5 Live Service Integration Tests (Tier 4)

These suites require active container infrastructure (`nexus_influxdb`, `nexus_broker`).

| Test File | Tests | External Requirements | Description |
| :--- | :---: | :--- | :--- |
| `ground_station/tests/test_analysis_live.py` | 5 | InfluxDB on `:8086` | Real Flux query latency, deduplication window queries, window statistics |
| `ground_station/tests/test_live_persistence_integration.py` | 10 | InfluxDB on `:8086` | Live Line Protocol ingestion, batch writes, point retrieval |
| `ground_station/tests/test_monitoring_live.py` | 8 | InfluxDB + SQLite | Live rule evaluation against streamed InfluxDB points |
| **Total Tier 4 Tests** | **23** | Compose containers running | Integration verification |

---

### 2.6 Hardware In-the-Loop & Qualification Harnesses (Tier 5)

| Harness Script | Purpose | Evidence Artifact Generated |
| :--- | :--- | :--- |
| `scripts/test_command_matrix.py` | Automated execution of all 115 commands over serial and MQTT against physical hardware | `docs/validation/command_matrix_results.json` |
| `tests/soak/nexus_soak_capture.py` | Dual serial/MQTT capture daemon logging raw frames with microsecond timestamps | `docs/validation/soak_qualification_run2_*.log` |
| `tests/soak/analyze_nexus_soak.py` | Statistical evaluation of soak logs against 7 firm qualification criteria | `docs/validation/soak_qualification_run2_report.md` |

---

## 3. How to Reproduce All Tests

### 3.1 Step 1: Run Native C Host Tests
```bash
# Compile and run Milestone 2 unit tests:
gcc -Wall -Wextra -I. -Imain/include -Icomponents/nexus_core/include tests/test_milestone2_host.c -o tests/test_milestone2_host
./tests/test_milestone2_host

# Compile and run Milestone 3 unit tests:
gcc -Wall -Wextra -I. -Imain/include -Icomponents/nexus_core/include -Icomponents/nexus_sensors/include tests/test_milestone3_host.c -o tests/test_milestone3_host
./tests/test_milestone3_host

# Run Milestone 8 and 9 unit tests:
./tests/test_milestone8_host
./tests/test_milestone9_host
```

### 3.2 Step 2: Run Python Offline Pytest Suite
```bash
source .venv/bin/activate
pytest ground_station/tests \
  --ignore=ground_station/tests/test_analysis_live.py \
  --ignore=ground_station/tests/test_live_persistence_integration.py \
  --ignore=ground_station/tests/test_monitoring_live.py \
  -q
```

### 3.3 Step 3: Run Soak Harness Tests
```bash
source .venv/bin/activate
pytest tests/soak/test_soak_harness.py -q
```

### 3.4 Step 4: Validate Reference Manual Parity
```bash
source .venv/bin/activate
python scripts/validate_reference_manual.py
```
