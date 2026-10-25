#!/usr/bin/env bash
# ==============================================================================
# NEXUS Demo Launcher — Common Environment, Logging, and Runtime Library
# ==============================================================================
set -euo pipefail

# Determine repository root reliably regardless of current working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEXUS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export NEXUS_ROOT

# Log and state paths
LOG_DIR="${NEXUS_ROOT}/ground_station/logs"
RUN_DIR="${NEXUS_ROOT}/ground_station/data/run"
STATE_FILE="${RUN_DIR}/demo_launcher_state.env"
GS_LOG_FILE="${LOG_DIR}/nexus_ground_station.log"
MQTT_INGEST_LOG_FILE="${LOG_DIR}/nexus_mqtt_ingestion.log"

# URLs
MISSION_CONTROL_URL="http://127.0.0.1:8000"
OPEN_WEBUI_URL="http://127.0.0.1:8080"
GRAFANA_URL="http://127.0.0.1:3000"
INFLUXDB_URL="http://127.0.0.1:8086"
MQTT_HOST="127.0.0.1"
MQTT_PORT=1883

# Color codes (disabled if not terminal or NO_COLOR set)
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    RED="\033[31m"
    GREEN="\033[32m"
    YELLOW="\033[33m"
    BLUE="\033[34m"
    CYAN="\033[36m"
    RESET="\033[0m"
else
    BOLD=""
    DIM=""
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    CYAN=""
    RESET=""
fi

log_info() {
    printf "${GREEN}[INFO]${RESET} %s\n" "$*"
}

log_warn() {
    printf "${YELLOW}[WARN]${RESET} %s\n" "$*" >&2
}

log_error() {
    printf "${RED}[ERROR]${RESET} %s\n" "$*" >&2
}

log_step() {
    printf "${BOLD}${CYAN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"
}

# Ensure directories exist
ensure_dirs() {
    mkdir -p "${LOG_DIR}" "${RUN_DIR}"
}

# Detect container runtime: podman or docker
detect_compose_cmd() {
    if command -v podman-compose >/dev/null 2>&1 && command -v podman >/dev/null 2>&1; then
        echo "podman-compose"
    elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

# Check if PID is alive and command line contains expected pattern
is_process_alive() {
    local pid="$1"
    local pattern="${2:-}"
    if [[ -z "${pid}" ]] || ! [[ "${pid}" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    if ! kill -0 "${pid}" 2>/dev/null; then
        return 1
    fi
    if [[ -n "${pattern}" ]]; then
        local cmdline
        cmdline="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
        if [[ "${cmdline}" != *"${pattern}"* ]]; then
            return 1
        fi
    fi
    return 0
}

# Check TCP port connectivity with bounded timeout (using bash /dev/tcp or nc/curl)
check_tcp_port() {
    local host="$1"
    local port="$2"
    local timeout_sec="${3:-2}"
    if command -v timeout >/dev/null 2>&1; then
        timeout "${timeout_sec}" bash -c "</dev/tcp/${host}/${port}" 2>/dev/null && return 0
    else
        bash -c "</dev/tcp/${host}/${port}" 2>/dev/null && return 0
    fi
    return 1
}

# Check HTTP endpoint with timeout
check_http_endpoint() {
    local url="$1"
    local expected_code="${2:-200}"
    local timeout_sec="${3:-2}"
    local code
    code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "${timeout_sec}" --max-time "${timeout_sec}" "${url}" 2>/dev/null || echo "000")"
    if [[ "${code}" == "${expected_code}" ]]; then
        return 0
    elif [[ "${expected_code}" == "2xx" ]] && [[ "${code}" =~ ^2[0-9][0-9]$ ]]; then
        return 0
    fi
    return 1
}

# Load state file if exists
load_launcher_state() {
    LAUNCHER_STARTED_CONTAINERS=""
    LAUNCHER_GS_PID=""
    LAUNCHER_MQTT_INGEST_PID=""
    if [[ -f "${STATE_FILE}" ]]; then
        # shellcheck disable=SC1090
        source "${STATE_FILE}" 2>/dev/null || true
    fi
}

# Save state file atomically
save_launcher_state() {
    ensure_dirs
    local tmp_file="${STATE_FILE}.tmp.$$"
    cat <<EOF > "${tmp_file}"
# NEXUS Demo Launcher State — Auto-generated
LAUNCHER_STARTED_CONTAINERS="${LAUNCHER_STARTED_CONTAINERS:-}"
LAUNCHER_GS_PID="${LAUNCHER_GS_PID:-}"
LAUNCHER_MQTT_INGEST_PID="${LAUNCHER_MQTT_INGEST_PID:-}"
LAUNCHER_LAST_UPDATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
EOF
    mv -f "${tmp_file}" "${STATE_FILE}"
}

# Clean state file safely
clear_launcher_state() {
    rm -f "${STATE_FILE}" "${STATE_FILE}.tmp."* 2>/dev/null || true
}

# Telemetry freshness threshold (seconds) for a HEALTHY (LIVE) verdict
TELEMETRY_FRESH_SEC="${TELEMETRY_FRESH_SEC:-10}"

# Query the latest persisted telemetry record via the project's read-only
# TelemetryQueryService. The verdict is based on the InfluxDB record host
# timestamp, never on transport connectivity alone.
# Prints exactly one line:
#   "<age_sec>|<value>|<transport>"  when a record exists
#   "none"                            when no record exists
#   "err"                             on any query/import failure
query_latest_telemetry() {
    local py="${NEXUS_ROOT}/.venv/bin/python"
    if [[ ! -x "${py}" ]]; then
        echo "err"
        return 0
    fi
    (
        cd "${NEXUS_ROOT}" && PYTHONPATH="${NEXUS_ROOT}" timeout 10 "${py}" - <<'PYEOF' 2>/dev/null
import time
try:
    from ground_station.analysis.telemetry_query import TelemetryQueryService
    svc = TelemetryQueryService()
    rec = svc.get_latest_reading("nexus_esp32", "dist_cm")
    if rec is None or rec.host_time is None:
        print("none")
    else:
        age = time.time() - rec.host_time.timestamp()
        print(f"{age:.2f}|{rec.value}|{rec.transport}")
except Exception:
    print("err")
PYEOF
    ) || echo "err"
}

# Returns 0 if the given age (seconds) is below TELEMETRY_FRESH_SEC
is_age_fresh() {
    local age="$1"
    [[ "$(awk -v a="${age}" -v t="${TELEMETRY_FRESH_SEC}" 'BEGIN {print (a >= 0 && a < t) ? "1" : "0"}')" == "1" ]]
}
