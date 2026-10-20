# NEXUS — Milestone 7 Final Acceptance & Operational Closure Report

## Executive Summary

This report establishes the formal, authoritative closure of **Milestone 7 (M7)** for **NEXUS** (*Networked Environmental eXecutive with Unified Sensing*).

Milestone 7 delivers a comprehensive telemetry analysis foundation, a deterministic background incident-monitoring engine with durable SQLite storage, a read-only conversational AI assistant powered by local Ollama models (`mistral:7b`), integration with Open WebUI tool-calling, and live end-to-end operational validation over the physical telemetry pipeline:

$$\text{Physical ESP32} \longrightarrow \text{Wi-Fi / Mosquitto MQTT (10.12.252.18:1883)} \longrightarrow \text{Ground Station Ingestion} \longrightarrow \text{InfluxDB} \longrightarrow \text{Grafana}$$

All automated regression tests (**210/210 passed**) and linting checks (**0 errors**) were verified, and all M7 milestones (M7.1 through M7.5) have achieved full acceptance criteria.

---

## 1. Verified Milestone Breakdown (M7.1 – M7.5)

### M7.1 — Telemetry Analysis Foundation
- **Package:** `ground_station/analysis/`
- **Capabilities:**
  - Typed telemetry domain models (`TelemetryPoint`, `DeviceSeries`, `DataQualityReport`, `SignalStatistics`).
  - Robust data-quality assessment (null rates, cadence irregularities, monotonically increasing sequence gaps, sensor validity flag analysis).
  - Statistical aggregation and trend computation (mean, median, standard deviation, min/max, linear regression slope/intercept, variance).
  - Bounded InfluxDB Flux query execution with parameterized limits, window bounding, and fallback to historical fixtures during offline operations.
- **Verification:** Unit and live integration test coverage in `test_analysis_unit.py` (22 tests) and `test_analysis_live.py` (5 tests).

### M7.2 — Deterministic Incident Monitoring & Durable Store
- **Package:** `ground_station/monitoring/`
- **Capabilities:**
  - Typed incident definitions (`Incident`, `IncidentSeverity`, `IncidentStatus`, `IncidentTransition`).
  - Thread-safe SQLite persistence (`ground_station/data/incidents.db` by default) supporting atomic transitions, status changes, resolution notes, and bounded audit queries.
  - Pluggable deterministic rule engine:
    - `FreshnessRule`: Detects communication blackouts and cadence degradation.
    - `SensorAnomalyRule`: Evaluates DHT validity, temperature/humidity range violations, and LDR light shifts.
    - `ExecutiveHealthRule`: Detects heap depletion (<10 KB warning, <5 KB critical) and loop stall conditions.
  - Adaptive evaluation scheduler adjusting cycle frequency based on incident state and telemetry freshness.
  - Outage-aware state handling: distinguishes sensor data quality issues from source-level data transport outages.
- **Verification:** Coverage across `test_monitoring_unit.py` (25 tests), `test_monitoring_lifecycle.py` (6 tests), and `test_monitoring_live.py` (1 test).

### M7.3 — Read-Only Conversational AI Core
- **Package:** `ground_station/ai/`
- **Capabilities:**
  - Security-enforced read-only tool boundary (`tool_registry.py`, `tools.py`).
  - Nine bounded operational query tools:
    1. `get_latest_telemetry`
    2. `query_telemetry_history`
    3. `get_sensor_statistics`
    4. `detect_telemetry_anomalies`
    5. `get_telemetry_trends`
    6. `list_active_incidents`
    7. `get_incident_details`
    8. `get_system_overview`
    9. `evaluate_monitoring_rules`
  - Strict input validation rejecting arbitrary code execution, SQL/Flux injection, filesystem access, and transport manipulation.
  - Deterministic Rule Router fallback providing immediate grounded answers if the local LLM runtime is unreachable or offline.
  - Local model baseline: `mistral:7b` via local Ollama endpoint (`http://127.0.0.1:11434`).
  - Interactive terminal CLI: `ground_station/ai/cli.py`.
- **Verification:** Full unit test suite in `test_ai_unit.py` (24 tests).

### M7.4 — Operational Integration & Tool Ecosystem
- **Package:** `ground_station/ai/open_webui_tools.py`, `ground_station/ai/register_open_webui.py`, `ground_station/monitoring/runner.py`
- **Capabilities:**
  - Native Open WebUI Tool format adapter (`Tools` class with valve configuration and type annotations).
  - Automated registration script for Open WebUI instance at `http://127.0.0.1:8080`.
  - Standalone monitoring runner CLI (`runner.py`) for daemonized or headless incident evaluation.
  - Ingestion entry point integration (`run_mqtt_ingestion.py`, `run_serial_ingestion.py`, `run_dual_transport_ingestion.py`) with optional `--enable-monitoring` flag.
  - Clean lifecycle management: graceful thread shutdown, database connection closing, and zero duplicate workers.
- **Verification:** Integration testing in `test_open_webui_integration.py` (6 tests).

### M7.5 — End-to-End Live Validation & Physical Acceptance
- **Scope:** Complete round-trip verification across all physical and containerized layers.
- **Open WebUI:** Real tool call round-trip tested in browser UI with Mistral 7B invoking `get_latest_telemetry` and returning structured responses.
- **Physical Pipeline:** Live hardware telemetry streaming through Mosquitto MQTT to InfluxDB and Grafana.

---

## 2. Live Telemetry Pipeline Validation Evidence

The following operational validation was executed directly against the live environment:

### A. Broker Reachability & Authentication
- **Broker Container:** `nexus_broker` (Eclipse Mosquitto 2.1.2) running in Podman pod `pod_nexus`.
- **Bound Addresses:** `127.0.0.1:1883` and `10.12.252.18:1883` (verified via `rootlessport`).
- **Authentication:** ACL-enforced access requiring valid credentials.
- **Result:** Connection accepted for user `nexus_ground_station` (code `0`). Anonymous connections rejected.

### B. Physical ESP32 Hardware
- **Hardware Target:** ESP32-D0WD-V3 (rev 3.1) connected via Wi-Fi.
- **Connection Confirmation:** Mosquitto logged:
  ```
  New client connected from 10.89.0.4:59824 as nexus_esp32 (p4, c1, k120, u'nexus_device')
  ```
- **Firmware Status:** Resident firmware was already configured for `mqtt://10.12.252.18:1883`. Flashing was **not needed** and was deliberately avoided to preserve flash endurance.
- **Telemetry Stream Received:**
  - Sequence Range: `2032` to `2063` (consecutive, 0 dropped packets during sampling).
  - Device Uptime: `1,214,730 ms` to `1,233,631 ms` (~20.5 minutes continuous uptime).
  - Sensor Payload: Ambient temperature `31.0°C`, relative humidity `72.0%`, LDR reading `11`, gas ADC reading `1006`.

### C. Ground Station Ingestion
- **Execution:** `run_mqtt_ingestion.py --host 10.12.252.18 --duration 20 --enable-monitoring`
- **Ingestion Stats:**
  - Total Envelopes Ingested: **32** (`hb: 19`, `telem: 9`, `status: 4`).
  - InfluxDB Writes: **32 submitted, 32 accepted and persisted** into bucket `nexus_telemetry`. Zero write failures.
  - Background Monitor: Evaluated 2 cycles, 0 active incidents, source state `HEALTHY`.

### D. InfluxDB Persistence
- **Bucket / Org:** `nexus_telemetry` / `nexus`
- **Measurement:** `nexus_telem`
- **Verification Query (Flux):**
  ```flux
  from(bucket: "nexus_telemetry")
    |> range(start: -30m)
    |> filter(fn: (r) => r["_measurement"] == "nexus_telem")
    |> filter(fn: (r) => r["dev"] == "nexus_esp32")
    |> filter(fn: (r) => r["_field"] == "temp")
    |> last()
  ```
  Returned point: `_time = 2026-10-20T02:44:23Z`, `temp = 31.0`, `dev = nexus_esp32`, `transport = mqtt`.

### E. Grafana Dashboard Retrieval
- **Service:** `nexus_grafana` (Grafana 11.5.0) at `http://127.0.0.1:3000`.
- **Dashboard:** `NEXUS Telemetry & Device Health` (uid: `nexus_telemetry_health`).
- **Datasource:** `InfluxDB_Flux` (uid: `nexus_influxdb_flux`).
- **Panel Query Result:** Executed query via Grafana `/api/ds/query` endpoint for Panel 1 (`Ambient Temperature`). Retrieved 5 frames for `nexus_esp32`:
  - `temp`: `31.0°C`
  - `hum`: `72.0%`
  - `ldr_raw`: `11`
  - `x0_raw`: `1006`
  - `uptime_ms`: `1232230`

---

## 3. Disambiguation of Data Sources

To maintain strict data integrity, the system distinguishes between:
1. **Physical ESP32 Live Telemetry:**
   - Tagged `dev=nexus_esp32`, `transport=mqtt`.
   - Sequence numbers increment monotonically (`2032`...`2063`).
   - Timestamps reflect real-time ingestion.
2. **Historical Fixtures & Soak Telemetry:**
   - Used for unit and soak test validation (e.g., in `tests/soak/`).
   - Identified by device IDs such as `nexus_soak_sim` or synthetic timestamps.
3. **Serial Ingestion:**
   - Tagged `transport=serial` when ingested via `/dev/ttyUSB0`.

---

## 4. Key Engineering Corrections

### Raw ADC Semantics (`x0_raw_adc`)
- **Correction:** The `x0_raw` field originates from the ESP32's raw analog-to-digital converter input (ADC1 Channel 0, 12-bit, 0–4095 range).
- **Enforcement:** Updated AI tool schemas (`tools.py`, `open_webui_tools.py`) and system prompts (`prompts.py`) to explicitly describe `x0_raw_adc` as an uncalibrated raw integer count, preventing the conversational assistant from hallucinating calibrated gas concentrations (e.g., ppm) or confusing it with the DHT11 sensor validity boolean.
- **Unit Verification:** Added deterministic test `test_deterministic_fallback_telemetry_grounding_preserves_x0_raw_adc_and_invalid_dht` to verify correct presentation.

---

## 5. Verification Results (Rerun During Closure)

| Check | Tool / Scope | Result | Notes |
|---|---|---|---|
| **Full Regression Suite** | `pytest ground_station/tests tests/soak` | **210 passed in 8.11s** | 0 failures, 0 errors, 0 skipped |
| **Code Style & Linting** | `ruff check` on all M7 modules | **All checks passed!** | Clean across `ai/`, `analysis/`, `monitoring/`, and tests |
| **Patch Cleanliness** | `git diff --check` | **Clean (Exit 0)** | No trailing whitespace or merge markers |
| **Security Hygiene** | Tracked and untracked file scan | **Clean** | No credentials, tokens, or private keys staged |

*(Note: The live ESP32 pipeline validation was completed and recorded in Phase M7.5. The automated test and lint checks above were rerun directly during this closure task.)*

---

## 6. Model Baseline & Deferred Scope

- **Primary Local Model:** `mistral:7b` (running under Ollama) is established and validated as the standard operational conversational model.
- **Deferred Evaluation:** The specialized model `cactus-compute/needle` remains deferred as an optional future enhancement. It is not required for M7 completion, and `mistral:7b` provides full conversational competence across all nine telemetry tools.

---

## 7. Operating Caveats

1. **Host Network Binding:** The Mosquitto broker is bound to `10.12.252.18:1883`. If the host Wi-Fi interface obtains a different IP address following a network transition, port binding must be updated in `.env` (`MQTT_BIND_IP`) or the broker restarted once the IP is reacquired.
2. **Monitoring Service Lifecycle:** The monitoring engine can run independently via `ground_station.monitoring.runner` or inside ingestion scripts with `--enable-monitoring`. When both transports run concurrently in `run_dual_transport_ingestion.py`, exactly one unified monitoring worker is instantiated.
3. **Database Concurrency:** The incident store uses SQLite with WAL mode, suitable for multi-reader single-writer operational logging.

---

## 8. Final Verdict

**Milestone 7 (M7) is formally accepted, verified, and closed.**
