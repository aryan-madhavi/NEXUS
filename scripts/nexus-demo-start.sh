#!/usr/bin/env bash
# ==============================================================================
# NEXUS — Professor-Ready Demo Launcher (scripts/nexus-demo-start.sh)
#
# Idempotently starts and verifies all required NEXUS services:
#   1. Podman / Docker Compose infrastructure (Mosquitto, InfluxDB, Grafana)
#   2. Ground Station Server (REST API & Mission Control Web Panel on port 8000)
#   3. Open WebUI (Verified service or automated systemd/local startup on port 8080)
#   4. Telemetry Ingestion (MQTT InfluxDB writer & Serial adapter)
#
# Flags:
#   --no-browser      Suppress automatic opening of browser tabs
#   --mock-stream     Enable simulated telemetry stream (useful if ESP32 is absent)
#   --help, -h        Show usage summary
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/nexus_demo_common.sh
source "${SCRIPT_DIR}/nexus_demo_common.sh"

OPEN_BROWSER=true
MOCK_STREAM=false

for arg in "$@"; do
    case "${arg}" in
        --no-browser)
            OPEN_BROWSER=false
            ;;
        --mock-stream)
            MOCK_STREAM=true
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-browser    Do not open Mission Control in default browser"
            echo "  --mock-stream   Launch Ground Station with simulated telemetry generator"
            echo "  -h, --help      Display this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: ${arg}"
            echo "Run '$0 --help' for usage."
            exit 1
            ;;
    esac
done

ensure_dirs
load_launcher_state

# Track the Ground Station process started during this specific invocation
INVOCATION_SPAWNED_GS_PID=""

# Graceful cleanup on failure or interrupt
cleanup_on_failure() {
    local exit_code="${1:-1}"
    if [[ -n "${INVOCATION_SPAWNED_GS_PID:-}" ]]; then
        if is_process_alive "${INVOCATION_SPAWNED_GS_PID}" "run_ground_station.py"; then
            log_warn "Cleaning up partially started Ground Station process (PID: ${INVOCATION_SPAWNED_GS_PID})..."
            kill -INT "${INVOCATION_SPAWNED_GS_PID}" 2>/dev/null || true
            sleep 1
            if kill -0 "${INVOCATION_SPAWNED_GS_PID}" 2>/dev/null; then
                kill -TERM "${INVOCATION_SPAWNED_GS_PID}" 2>/dev/null || true
                sleep 1
            fi
            if kill -0 "${INVOCATION_SPAWNED_GS_PID}" 2>/dev/null; then
                kill -KILL "${INVOCATION_SPAWNED_GS_PID}" 2>/dev/null || true
            fi
        fi
        LAUNCHER_GS_PID=""
        rm -f "${RUN_DIR}/ground_station.pid" 2>/dev/null || true
        save_launcher_state
    fi
}

cleanup_on_interrupt() {
    printf "\n"
    log_warn "Startup interrupted by operator (SIGINT/SIGTERM)."
    cleanup_on_failure 130
    exit 130
}
trap cleanup_on_interrupt INT TERM

log_step "Step 1: System Preflight Checks"

# 1.1 Python Virtual Environment
PYTHON_BIN="${NEXUS_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
    log_error "Python virtual environment not found at: ${PYTHON_BIN}"
    log_error "Please run: python3 -m venv .venv && .venv/bin/pip install -r ground_station/requirements.txt"
    exit 1
fi
log_info "Python environment verified: ${PYTHON_BIN}"

# 1.2 Environment file
if [[ ! -f "${NEXUS_ROOT}/.env" ]]; then
    log_error "Environment configuration file '${NEXUS_ROOT}/.env' is missing!"
    log_error "Please create it from the template before starting:"
    log_error "    cp ${NEXUS_ROOT}/.env.example ${NEXUS_ROOT}/.env"
    log_error "and configure your local secrets and service ports."
    exit 1
else
    log_info "Environment configuration verified: ${NEXUS_ROOT}/.env"
fi

# 1.3 Container Compose Runtime
COMPOSE_CMD="$(detect_compose_cmd)"
if [[ -z "${COMPOSE_CMD}" ]]; then
    log_error "No container compose tool found! Please install podman-compose or docker compose."
    exit 1
fi
log_info "Container compose engine: ${COMPOSE_CMD}"

# 1.4 Check physical ESP32 device existence
HAS_ESP32_SERIAL=false
if [[ -e "/dev/ttyUSB0" ]] || [[ -e "/dev/ttyACM0" ]]; then
    HAS_ESP32_SERIAL=true
    log_info "Physical ESP32 serial interface detected (/dev/ttyUSB0 or /dev/ttyACM0)"
else
    log_info "Physical ESP32 serial device not connected. (Software/MQTT ingestion path will be used)"
fi

log_step "Step 2: Infrastructure Containers (Mosquitto, InfluxDB, Grafana)"

# Check if all required container endpoints are healthy
ARE_CONTAINERS_HEALTHY=true
if ! check_tcp_port "${MQTT_HOST}" "${MQTT_PORT}" 1 || \
   ! check_http_endpoint "${INFLUXDB_URL}/health" 200 1 || \
   ! check_http_endpoint "${GRAFANA_URL}/api/health" 200 1; then
    ARE_CONTAINERS_HEALTHY=false
fi

if [[ "${ARE_CONTAINERS_HEALTHY}" == "true" ]]; then
    log_info "Infrastructure containers are already up and healthy (Mosquitto, InfluxDB, Grafana)."
else
    log_info "Starting infrastructure containers via: ${COMPOSE_CMD} -f ${NEXUS_ROOT}/docker-compose.yml up -d"
    (cd "${NEXUS_ROOT}" && ${COMPOSE_CMD} -f "${NEXUS_ROOT}/docker-compose.yml" up -d)
    LAUNCHER_STARTED_CONTAINERS="true"
    save_launcher_state
fi

# Wait for container health with bounded timeout (30 seconds)
log_info "Verifying container readiness..."
TIMEOUT=30
ELAPSED=0

while [[ ${ELAPSED} -lt ${TIMEOUT} ]]; do
    MQTT_OK=false
    INFLUX_OK=false
    GRAFANA_OK=false

    if check_tcp_port "${MQTT_HOST}" "${MQTT_PORT}" 1; then
        MQTT_OK=true
    fi
    if check_http_endpoint "${INFLUXDB_URL}/health" 200 1; then
        INFLUX_OK=true
    fi
    if check_http_endpoint "${GRAFANA_URL}/api/health" 200 1; then
        GRAFANA_OK=true
    fi

    if [[ "${MQTT_OK}" == "true" ]] && [[ "${INFLUX_OK}" == "true" ]] && [[ "${GRAFANA_OK}" == "true" ]]; then
        break
    fi

    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if [[ "${MQTT_OK}" != "true" ]] || [[ "${INFLUX_OK}" != "true" ]] || [[ "${GRAFANA_OK}" != "true" ]]; then
    log_error "Container services failed to reach healthy state within ${TIMEOUT}s!"
    log_error "MQTT: ${MQTT_OK}, InfluxDB: ${INFLUX_OK}, Grafana: ${GRAFANA_OK}"
    exit 1
fi
log_info "All container services healthy (Mosquitto, InfluxDB, Grafana)."

log_step "Step 3: Open WebUI Service Verification"

# Open WebUI is typically managed as a user systemd service or local runner
if check_http_endpoint "${OPEN_WEBUI_URL}/api/version" 200 2; then
    log_info "Open WebUI is running and responsive at ${OPEN_WEBUI_URL}"
else
    # Try starting user systemd service if available
    if command -v systemctl >/dev/null 2>&1 && systemctl --user is-enabled open-webui.service >/dev/null 2>&1; then
        log_info "Starting Open WebUI via systemctl --user start open-webui.service..."
        systemctl --user start open-webui.service 2>/dev/null || true
        # Brief wait
        sleep 2
    fi
    if check_http_endpoint "${OPEN_WEBUI_URL}/api/version" 200 2; then
        log_info "Open WebUI successfully started and responsive."
    else
        log_warn "Open WebUI is not responding at ${OPEN_WEBUI_URL}. AI Copilot interface will show as offline until started."
    fi
fi

log_step "Step 4: Ground Station & Ingestion Server Startup"

# 4.1 Ground Station Process
GS_RUNNING=false
if check_http_endpoint "${MISSION_CONTROL_URL}/api/status" 200 1; then
    log_info "Ground Station HTTP server is already running and responding at ${MISSION_CONTROL_URL}."
    GS_RUNNING=true
elif [[ -n "${LAUNCHER_GS_PID:-}" ]] && is_process_alive "${LAUNCHER_GS_PID}" "run_ground_station.py"; then
    log_info "Ground Station already running with tracked PID ${LAUNCHER_GS_PID}."
    GS_RUNNING=true
fi

if [[ "${GS_RUNNING}" == "false" ]]; then
    log_info "Launching Ground Station server (logging to ${GS_LOG_FILE})..."
    EXTRA_GS_ARGS=()
    if [[ "${MOCK_STREAM}" == "true" ]]; then
        EXTRA_GS_ARGS+=( "--mock-stream" )
        log_info "Enabled --mock-stream generator flag."
    fi

    # Launch Ground Station in background with PYTHONPATH and detached session
    (
        cd "${NEXUS_ROOT}"
        export PYTHONPATH="${NEXUS_ROOT}"
        if command -v setsid >/dev/null 2>&1; then
            setsid "${PYTHON_BIN}" ground_station/run_ground_station.py "${EXTRA_GS_ARGS[@]}" >> "${GS_LOG_FILE}" 2>&1 </dev/null &
        else
            nohup "${PYTHON_BIN}" ground_station/run_ground_station.py "${EXTRA_GS_ARGS[@]}" >> "${GS_LOG_FILE}" 2>&1 </dev/null &
        fi
        echo $! > "${RUN_DIR}/ground_station.pid"
    )
    LAUNCHER_GS_PID="$(cat "${RUN_DIR}/ground_station.pid")"
    INVOCATION_SPAWNED_GS_PID="${LAUNCHER_GS_PID}"
    save_launcher_state

    # Wait for Ground Station readiness
    GS_TIMEOUT=15
    GS_ELAPSED=0
    GS_READY=false
    while [[ ${GS_ELAPSED} -lt ${GS_TIMEOUT} ]]; do
        if check_http_endpoint "${MISSION_CONTROL_URL}/api/status" 200 1; then
            GS_READY=true
            break
        fi
        sleep 1
        GS_ELAPSED=$((GS_ELAPSED + 1))
    done

    if [[ "${GS_READY}" != "true" ]]; then
        log_error "Ground Station server failed to respond on ${MISSION_CONTROL_URL}/api/status within ${GS_TIMEOUT}s!"
        log_error "Check log file: ${GS_LOG_FILE}"
        tail -n 20 "${GS_LOG_FILE}" 2>/dev/null || true
        cleanup_on_failure 1
        exit 1
    fi
    log_info "Ground Station server online (PID: ${LAUNCHER_GS_PID})."
fi

# 4.2 Verify Ingestion Pipeline & Telemetry Stream
log_step "Step 5: Verifying Ingestion Pipeline & Telemetry Freshness"

# Check latest telemetry via InfluxDB record timestamp (never transport connection alone)
TELEMETRY_STATUS="UNVERIFIED"

if [[ "${MOCK_STREAM}" == "true" ]]; then
    TELEMETRY_STATUS="SIMULATED (MOCK)"
    log_info "Telemetry stream is operating in simulated mode (--mock-stream)."
else
    # Query InfluxDB directly for latest recorded telemetry
    TLM_RESULT="$(query_latest_telemetry)"
    if [[ "${TLM_RESULT}" == "err" ]]; then
        TELEMETRY_STATUS="UNVERIFIED (QUERY ERROR)"
        log_warn "Telemetry query service returned an error. InfluxDB may still be starting or unreachable."
    elif [[ "${TLM_RESULT}" == "none" ]]; then
        TELEMETRY_STATUS="UNVERIFIED (NO READINGS)"
        log_warn "No telemetry records found in InfluxDB. ESP32 may be powered off or Wi-Fi disconnected."
    else
        TLM_AGE="$(echo "${TLM_RESULT}" | cut -d'|' -f1)"
        TLM_VAL="$(echo "${TLM_RESULT}" | cut -d'|' -f2)"
        TLM_TRN="$(echo "${TLM_RESULT}" | cut -d'|' -f3)"

        if is_age_fresh "${TLM_AGE}"; then
            TELEMETRY_STATUS="HEALTHY (LIVE: ${TLM_AGE}s)"
            log_info "Verified live telemetry in InfluxDB: ${TLM_VAL} cm via ${TLM_TRN} (${TLM_AGE}s ago)."
        else
            TELEMETRY_STATUS="UNVERIFIED (STALE: ${TLM_AGE}s)"
            log_warn "Latest telemetry record in InfluxDB is ${TLM_AGE}s old (> ${TELEMETRY_FRESH_SEC}s threshold)."
        fi
    fi
fi

# 4.3 Summary Table
log_step "NEXUS Demonstration Status Summary"
echo ""
printf "  ${BOLD}%-25s %-25s %-30s${RESET}\n" "SERVICE / COMPONENT" "STATUS" "ACCESS URL"
printf "  ------------------------------------------------------------------------------------\n"
printf "  %-25s ${GREEN}%-25s${RESET} %-30s\n" "Mission Control UI" "ONLINE" "${MISSION_CONTROL_URL}"
printf "  %-25s ${GREEN}%-25s${RESET} %-30s\n" "Grafana Dashboards" "ONLINE" "${GRAFANA_URL}"
printf "  %-25s ${GREEN}%-25s${RESET} %-30s\n" "InfluxDB Engine" "ONLINE" "${INFLUXDB_URL}"
if check_http_endpoint "${OPEN_WEBUI_URL}/api/version" 200 1; then
    printf "  %-25s ${GREEN}%-25s${RESET} %-30s\n" "Open WebUI AI Copilot" "ONLINE" "${OPEN_WEBUI_URL}"
else
    printf "  %-25s ${YELLOW}%-25s${RESET} %-30s\n" "Open WebUI AI Copilot" "OFFLINE" "${OPEN_WEBUI_URL}"
fi
printf "  %-25s ${CYAN}%-25s${RESET} %-30s\n" "Telemetry Pipeline" "${TELEMETRY_STATUS}" "Port ${MQTT_PORT} (MQTT)"
printf "  ------------------------------------------------------------------------------------\n"
echo ""

# Browser launch
if [[ "${OPEN_BROWSER}" == "true" ]]; then
    if command -v xdg-open >/dev/null 2>&1; then
        log_info "Opening Mission Control in browser: ${MISSION_CONTROL_URL}"
        xdg-open "${MISSION_CONTROL_URL}" >/dev/null 2>&1 || true
    fi
fi

save_launcher_state
log_info "NEXUS demo environment is ready for presentation."
exit 0
