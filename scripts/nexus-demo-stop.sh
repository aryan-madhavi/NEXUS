#!/usr/bin/env bash
# ==============================================================================
# NEXUS — Graceful Demo Terminator (scripts/nexus-demo-stop.sh)
#
# Gracefully shuts down demo components started by the launcher:
#   1. Ground Station host process (PID-verified, graceful SIGINT/SIGTERM, timeout)
#   2. Infrastructure containers (podman-compose / docker compose stop or down)
#
# CRITICAL SAFETY PRECAUTIONS:
#   - Never executes 'docker compose down -v' (does NOT delete data volumes)
#   - Never terminates unrelated processes
#   - Verifies PID identity before signaling
#   - Safe to run repeatedly
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/nexus_demo_common.sh
source "${SCRIPT_DIR}/nexus_demo_common.sh"

load_launcher_state

log_step "Step 1: Stopping Tracked Host Processes"

STOPPED_ANY=false

# 1. Stop Ground Station if tracked
if [[ -n "${LAUNCHER_GS_PID:-}" ]]; then
    if is_process_alive "${LAUNCHER_GS_PID}" "run_ground_station.py"; then
        log_info "Stopping Ground Station process (PID: ${LAUNCHER_GS_PID})..."
        kill -INT "${LAUNCHER_GS_PID}" 2>/dev/null || true

        # Wait up to 5 seconds for clean exit
        WAIT_COUNT=0
        while kill -0 "${LAUNCHER_GS_PID}" 2>/dev/null && [[ ${WAIT_COUNT} -lt 5 ]]; do
            sleep 1
            WAIT_COUNT=$((WAIT_COUNT + 1))
        done

        if kill -0 "${LAUNCHER_GS_PID}" 2>/dev/null; then
            log_warn "Process ${LAUNCHER_GS_PID} did not stop after SIGINT. Escalating to SIGTERM..."
            kill -TERM "${LAUNCHER_GS_PID}" 2>/dev/null || true
            sleep 2
        fi

        if kill -0 "${LAUNCHER_GS_PID}" 2>/dev/null; then
            log_warn "Process ${LAUNCHER_GS_PID} did not exit after SIGTERM. Sending SIGKILL..."
            kill -KILL "${LAUNCHER_GS_PID}" 2>/dev/null || true
        fi
        log_info "Ground Station process ${LAUNCHER_GS_PID} stopped."
        STOPPED_ANY=true
    else
        log_info "Tracked Ground Station process (PID: ${LAUNCHER_GS_PID}) was not running."
    fi
    LAUNCHER_GS_PID=""
fi

# Clean up PID file if exists
rm -f "${RUN_DIR}/ground_station.pid" 2>/dev/null || true

# 2. Check for any remaining ground station processes launched manually
MANUAL_GS_PIDS="$(pgrep -f "ground_station/run_ground_station.py" 2>/dev/null || true)"
if [[ -n "${MANUAL_GS_PIDS}" ]]; then
    log_info "Notice: Ground station process(es) (${MANUAL_GS_PIDS}) detected that were not started by this launcher session."
    log_info "To preserve operator work, unowned processes were left running."
fi

log_step "Step 2: Stopping Infrastructure Containers"

COMPOSE_CMD="$(detect_compose_cmd)"
if [[ -n "${COMPOSE_CMD}" ]]; then
    # Verify if any nexus containers are currently running before issuing stop
    RUNNING_NEXUS_CONTAINERS="$(podman ps --format "{{.Names}}" --filter "name=nexus_" 2>/dev/null || docker ps --format "{{.Names}}" --filter "name=nexus_" 2>/dev/null || true)"
    if [[ -n "${RUNNING_NEXUS_CONTAINERS}" ]]; then
        log_info "Stopping NEXUS Compose services (${COMPOSE_CMD} -f ${NEXUS_ROOT}/docker-compose.yml stop)..."
        # Execute safe, non-destructive stop (preserves persistent volumes and retains container configurations)
        (cd "${NEXUS_ROOT}" && ${COMPOSE_CMD} -f "${NEXUS_ROOT}/docker-compose.yml" stop)
        STOPPED_ANY=true
        log_info "NEXUS Compose services stopped successfully. (Persistent volumes preserved)"
    else
        log_info "No running NEXUS Compose services found."
    fi
else
    log_warn "No container compose command detected. Skipping container shutdown."
fi

LAUNCHER_STARTED_CONTAINERS=""
save_launcher_state

log_step "Shutdown Complete"
if [[ "${STOPPED_ANY}" == "true" ]]; then
    log_info "Demo components stopped cleanly."
else
    log_info "No active demo launcher components needed stopping."
fi

exit 0
