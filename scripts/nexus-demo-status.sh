#!/usr/bin/env bash
# ==============================================================================
# NEXUS — Demo Status Reporter (scripts/nexus-demo-status.sh)
#
# Inspects and reports:
#   1. Podman / Docker Compose service states
#   2. MQTT broker connectivity (Mosquitto port 1883)
#   3. Ground Station availability (Port 8000)
#   4. InfluxDB readiness & latest telemetry freshness in InfluxDB
#   5. Grafana health & provisioned dashboards (Port 3000)
#   6. Open WebUI status (Port 8080)
#   7. Physical ESP32 connection state (Serial/MQTT telemetry status)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/nexus_demo_common.sh
source "${SCRIPT_DIR}/nexus_demo_common.sh"

load_launcher_state

PYTHON_BIN="${NEXUS_ROOT}/.venv/bin/python"
COMPOSE_CMD="$(detect_compose_cmd)"

log_step "NEXUS Mission Control Architecture — Runtime Health Inspection"
echo ""

# 1. Container compose inspection
printf "  ${BOLD}%-30s %-15s %-35s${RESET}\n" "CONTAINER / SERVICE" "STATE" "CONTAINER STATUS"
printf "  ------------------------------------------------------------------------------------\n"

CONTAINERS_COUNT=0
if command -v podman >/dev/null 2>&1; then
    while IFS= read -r line; do
        if [[ -n "${line}" ]]; then
            NAME="$(echo "${line}" | awk '{print $1}')"
            STATUS="$(echo "${line}" | cut -d' ' -f2-)"
            STATE_LABEL="HEALTHY"
            COLOR="${GREEN}"
            if [[ "${STATUS}" != *"healthy"* ]] && [[ "${STATUS}" != *"Up"* ]]; then
                STATE_LABEL="DEGRADED"
                COLOR="${YELLOW}"
            fi
            printf "  %-30s ${COLOR}%-15s${RESET} %-35s\n" "${NAME}" "${STATE_LABEL}" "${STATUS}"
            CONTAINERS_COUNT=$((CONTAINERS_COUNT + 1))
        fi
    done < <(podman ps --format "{{.Names}} {{.Status}}" --filter "name=nexus" 2>/dev/null || true)
fi

if [[ ${CONTAINERS_COUNT} -eq 0 ]]; then
    printf "  %-30s ${RED}%-15s${RESET} %-35s\n" "nexus_* containers" "STOPPED" "No running nexus containers found"
fi

printf "  ------------------------------------------------------------------------------------\n"
echo ""

# 2. Host and Web Services status table
printf "  ${BOLD}%-30s %-15s %-20s %-20s${RESET}\n" "SERVICE ENDPOINT" "STATUS" "PORT / TRANSPORT" "BROWSER / URL"
printf "  ------------------------------------------------------------------------------------\n"

# Ground Station
GS_STATE="STOPPED"
GS_COLOR="${RED}"
if check_http_endpoint "${MISSION_CONTROL_URL}/api/status" 200 1; then
    GS_STATE="HEALTHY"
    GS_COLOR="${GREEN}"
elif check_tcp_port "127.0.0.1" 8000 1; then
    GS_STATE="DEGRADED"
    GS_COLOR="${YELLOW}"
fi
printf "  %-30s ${GS_COLOR}%-15s${RESET} %-20s %-20s\n" "Mission Control UI & API" "${GS_STATE}" "TCP 8000 (HTTP)" "${MISSION_CONTROL_URL}"

# Grafana
GRAFANA_STATE="STOPPED"
GRAFANA_COLOR="${RED}"
if check_http_endpoint "${GRAFANA_URL}/api/health" 200 1; then
    GRAFANA_STATE="HEALTHY"
    GRAFANA_COLOR="${GREEN}"
elif check_tcp_port "127.0.0.1" 3000 1; then
    GRAFANA_STATE="DEGRADED"
    GRAFANA_COLOR="${YELLOW}"
fi
printf "  %-30s ${GRAFANA_COLOR}%-15s${RESET} %-20s %-20s\n" "Grafana Monitoring Dashboard" "${GRAFANA_STATE}" "TCP 3000 (HTTP)" "${GRAFANA_URL}"

# InfluxDB
INFLUX_STATE="STOPPED"
INFLUX_COLOR="${RED}"
if check_http_endpoint "${INFLUXDB_URL}/health" 200 1; then
    INFLUX_STATE="HEALTHY"
    INFLUX_COLOR="${GREEN}"
elif check_tcp_port "127.0.0.1" 8086 1; then
    INFLUX_STATE="DEGRADED"
    INFLUX_COLOR="${YELLOW}"
fi
printf "  %-30s ${INFLUX_COLOR}%-15s${RESET} %-20s %-20s\n" "InfluxDB Time-Series Engine" "${INFLUX_STATE}" "TCP 8086 (HTTP)" "${INFLUXDB_URL}"

# Mosquitto MQTT
MQTT_STATE="STOPPED"
MQTT_COLOR="${RED}"
if check_tcp_port "${MQTT_HOST}" "${MQTT_PORT}" 1; then
    MQTT_STATE="HEALTHY"
    MQTT_COLOR="${GREEN}"
fi
printf "  %-30s ${MQTT_COLOR}%-15s${RESET} %-20s %-20s\n" "Eclipse Mosquitto Broker" "${MQTT_STATE}" "TCP 1883 (MQTT)" "mqtt://127.0.0.1:1883"

# Open WebUI
WEBUI_STATE="STOPPED"
WEBUI_COLOR="${RED}"
if check_http_endpoint "${OPEN_WEBUI_URL}/api/version" 200 1; then
    WEBUI_STATE="HEALTHY"
    WEBUI_COLOR="${GREEN}"
elif check_tcp_port "127.0.0.1" 8080 1; then
    WEBUI_STATE="DEGRADED"
    WEBUI_COLOR="${YELLOW}"
fi
printf "  %-30s ${WEBUI_COLOR}%-15s${RESET} %-20s %-20s\n" "Open WebUI AI Copilot" "${WEBUI_STATE}" "TCP 8080 (HTTP)" "${OPEN_WEBUI_URL}"

printf "  ------------------------------------------------------------------------------------\n"
echo ""

# 3. Telemetry and Hardware Ingestion Inspection
log_step "Telemetry & Hardware Telemetry Verification"

HARDWARE_MODE="SOFTWARE-ONLY (NO PHYSICAL SERIAL DEVICE DETECTED)"
if [[ -e "/dev/ttyUSB0" ]] || [[ -e "/dev/ttyACM0" ]]; then
    HARDWARE_MODE="PHYSICAL HARDWARE READY (/dev/ttyUSB0 present)"
fi
printf "  ${BOLD}Hardware Interface Mode:${RESET} %s\n" "${HARDWARE_MODE}"

# InfluxDB telemetry freshness query
if [[ -x "${PYTHON_BIN}" ]] && check_http_endpoint "${INFLUXDB_URL}/health" 200 1; then
    TELEMETRY_READING="$(query_latest_telemetry)"

    if [[ "${TELEMETRY_READING}" == "none" ]]; then
        printf "  ${BOLD}InfluxDB Telemetry Stream:${RESET} ${YELLOW}NO TELEMETRY RECORDED YET${RESET}\n"
    elif [[ "${TELEMETRY_READING}" == "err"* ]]; then
        printf "  ${BOLD}InfluxDB Telemetry Stream:${RESET} ${YELLOW}QUERY UNAVAILABLE (${TELEMETRY_READING})${RESET}\n"
    else
        AGE="$(echo "${TELEMETRY_READING}" | cut -d'|' -f1)"
        VAL="$(echo "${TELEMETRY_READING}" | cut -d'|' -f2)"
        TRN="$(echo "${TELEMETRY_READING}" | cut -d'|' -f3)"

        if is_age_fresh "${AGE}"; then
            printf "  ${BOLD}InfluxDB Telemetry Stream:${RESET} ${GREEN}VERIFIED LIVE${RESET} (Latest: ${VAL} cm via ${TRN}, age: ${AGE}s ago)\n"
        else
            printf "  ${BOLD}InfluxDB Telemetry Stream:${RESET} ${YELLOW}IDLE / HISTORICAL${RESET} (Latest: ${VAL} cm via ${TRN}, age: ${AGE}s ago)\n"
        fi
    fi
else
    printf "  ${BOLD}InfluxDB Telemetry Stream:${RESET} ${DIM}SKIPPED (InfluxDB or Python venv offline)${RESET}\n"
fi

# Mission Control Connection state
if check_http_endpoint "${MISSION_CONTROL_URL}/api/status" 200 1; then
    DEV_CONNECTED="$(curl -s "${MISSION_CONTROL_URL}/api/status" 2>/dev/null | grep -o '"connected": *[a-z]*' | head -n1 || echo "")"
    ACTIVE_TRANS="$(curl -s "${MISSION_CONTROL_URL}/api/status" 2>/dev/null | grep -o '"active_transport": *"[^"]*"' | head -n1 || echo "")"
    printf "  ${BOLD}Mission Control Link State:${RESET} %s, %s\n" "${DEV_CONNECTED:-connected: unknown}" "${ACTIVE_TRANS:-transport: none}"
fi

echo ""
exit 0
