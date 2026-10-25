# NEXUS Live Demonstration Guide & Recovery Playbook

This document provides the standard operational procedure for conducting a live demonstration of the NEXUS Aerospace Ground Station and Embedded Telemetry platform.

---

## 1. Quick Operator Workflow

The entire NEXUS stack can be started, monitored, and stopped using three shell scripts located in [`scripts/`](file:///home/aryan/Projects/SPIT/NEXUS/scripts/):

```bash
# 1. Start the entire demonstration stack (Infrastructure Compose containers + Ground Station):
./scripts/nexus-demo-start.sh

# 2. Check complete runtime health, container states, and telemetry freshness:
./scripts/nexus-demo-status.sh

# 3. Stop the demonstration gracefully when done (Stops Ground Station and NEXUS Compose containers):
./scripts/nexus-demo-stop.sh
```

---

## 2. Infrastructure Lifecycle & Architecture

The demo scripts manage both the containerized infrastructure and the host Ground Station runtime:

| Service / Subsystem | Host Port / Transport | Default URL | Management Mechanism |
| :--- | :--- | :--- | :--- |
| **Mission Control UI** | TCP `8000` (HTTP) | [http://127.0.0.1:8000](http://127.0.0.1:8000) | Managed host Python process (`ground_station/run_ground_station.py`). |
| **Mosquitto Broker** | TCP `1883` (MQTT) | `mqtt://127.0.0.1:1883` | Container `nexus_broker` (`podman-compose -f docker-compose.yml`). |
| **InfluxDB 2.x Engine** | TCP `8086` (HTTP) | [http://127.0.0.1:8086](http://127.0.0.1:8086) | Container `nexus_influxdb` (`podman-compose -f docker-compose.yml`). |
| **Grafana Monitoring** | TCP `3000` (HTTP) | [http://127.0.0.1:3000](http://127.0.0.1:3000) | Container `nexus_grafana` (`podman-compose -f docker-compose.yml`). |
| **Open WebUI AI Copilot** | TCP `8080` (HTTP) | [http://127.0.0.1:8080](http://127.0.0.1:8080) | User service (`systemctl --user status open-webui.service`). |

### Lifecycle Policy:
- **`nexus-demo-start.sh`**:
  - Validates environment (`.env`), Python venv, and container engine. If `.env` is missing, halts immediately with instructions (never silently auto-creates credentials).
  - Launches container infrastructure using `podman-compose -f docker-compose.yml up -d` (without rebuilding unless images are absent).
  - Awaits Mosquitto (1883), InfluxDB (`/health`), and Grafana (`/api/health`) readiness with bounded timeouts.
  - Starts or resumes the Ground Station server with `setsid` and `PYTHONPATH` detachment.
  - **Failure Cleanup**: If the Ground Station fails to become ready within the timeout or if startup is cancelled via `SIGINT`/`SIGTERM`, the newly spawned process is cleanly terminated without leaving orphaned processes.
  - **Evidence-Based Telemetry Verdict**: Queries InfluxDB directly for the latest persisted sensor reading. Reports `HEALTHY (LIVE: <age>s)` only when a record exists and its arrival age is under 10 seconds. If no records exist, InfluxDB is unreachable, or data is stale, reports `UNVERIFIED`.
- **`nexus-demo-stop.sh`**:
  - Stops the tracked Ground Station host process via graceful `SIGINT` (escalating to `SIGTERM` if needed).
  - Stops all NEXUS Compose containers using `podman-compose -f docker-compose.yml stop`.
  - **Data Preservation Guarantee**: Persistent named volumes (`nexus_influxdb_data`, `nexus_influxdb_config`, `nexus_mosquitto_data`, `nexus_mosquitto_log`, `nexus_grafana_data`) are completely preserved. Never uses `-v` or volume deletion.
  - Does not disrupt unrelated Podman containers (e.g. `mongodb`, `freellmapi`, `m2s-lab`).

---

## 3. Demonstration Modes

### A. Live Hardware Mode (Default when ESP32 is plugged in)
- **Transport**: DUAL (Serial on `/dev/ttyUSB0` at 115200 baud + Wi-Fi MQTT on port 1883).
- **Telemetry Verification**: Real-time sensor readings (Ultrasonic distance, LDR, IR mux, optocoupler) are streamed into Ground Station memory and committed to InfluxDB.
- **Verification Indicator**: `./scripts/nexus-demo-status.sh` and `./scripts/nexus-demo-start.sh` display `HEALTHY (LIVE: <age>s)` backed by actual InfluxDB timestamps with arrival age `< 10s`. If transport is open but no data flows, status reports `UNVERIFIED`.

### B. Software-Only Demo Mode (When physical ESP32 is absent)
- If the ESP32 is not connected or Wi-Fi is unreachable, launch with simulated telemetry:
  ```bash
  ./scripts/nexus-demo-start.sh --mock-stream
  ```
- **Behavior**: Generates realistic telemetry envelopes for UI visualization and command dispatch testing without requiring physical sensors. Status displays `SIMULATED (MOCK)` rather than physical live telemetry.

---

## 4. Common Troubleshooting & Recovery Steps

### Scenario 1: Mission Control UI shows "DISCONNECTED"
1. Run `./scripts/nexus-demo-status.sh` to check if `nexus_broker` or serial ports are active.
2. If serial connection was interrupted, check device path:
   ```bash
   ls -la /dev/ttyUSB* /dev/ttyACM*
   ```
3. Restart the Ground Station process:
   ```bash
   ./scripts/nexus-demo-stop.sh
   ./scripts/nexus-demo-start.sh --no-browser
   ```

### Scenario 2: Containers are stopped or not responding
1. Verify container runtime:
   ```bash
   podman ps -a --filter "name=nexus"
   ```
2. Restart infrastructure containers via compose:
   ```bash
   podman-compose -f docker-compose.yml up -d
   ```
3. Note: **NEVER run `podman-compose down -v`**, as `-v` destroys all historical InfluxDB and Grafana database volumes.

### Scenario 3: Open WebUI shows offline
1. Open WebUI runs as a systemd user unit or local process. Verify its status:
   ```bash
   systemctl --user status open-webui.service
   ```
2. Restart the unit:
   ```bash
   systemctl --user restart open-webui.service
   ```

---

## 5. Security and Operational Safety Rules
- **No Automatic Firmware Flashing**: The demo scripts will never attempt to flash ESP32 flash memory or overwrite board calibration.
- **No Destructive Command Execution**: The scripts do not issue physical actuator triggers (motor power or buzzer) during startup.
- **No Secret Exposure**: All tokens and passwords in `.env` remain masked and local.
