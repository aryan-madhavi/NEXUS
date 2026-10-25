#!/usr/bin/env bash
# ==============================================================================
# NEXUS ESP32 Board Flash & Monitor Utility (scripts/nexus-board.sh)
#
# Supports:
#   - Direct flash via idf.py or esptool with explicit hardware reset flags:
#     --chip esp32 --before default-reset --after hard-reset
#   - Full flash erase (--erase-all / erase command) for recovering corrupted flash
#   - Bounded automated serial test monitoring (capturing raw telemetry output)
#   - Interactive serial monitor via idf.py monitor or Python fallback
#
# Usage:
#   ./scripts/nexus-board.sh flash           # Standard flash via idf.py
#   ./scripts/nexus-board.sh esptool-flash   # Low-level esptool flash with --after hard-reset
#   ./scripts/nexus-board.sh erase           # Full flash erase via esptool
#   ./scripts/nexus-board.sh monitor         # Interactive serial monitor
#   ./scripts/nexus-board.sh test-monitor [sec] # Automated capture & verification of N seconds
#   ./scripts/nexus-board.sh run             # Flash and launch interactive monitor
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEXUS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FIRMWARE_DIR="${NEXUS_ROOT}/firmware"
BUILD_DIR="${FIRMWARE_DIR}/build"

# Default serial port and baud rates
PORT="${ESPPORT:-/dev/ttyUSB0}"
BAUD="${ESPBAUD:-115200}"
FLASH_BAUD="${ESPFLASHBAUD:-460800}"

# Locate ESP-IDF environment
IDF_EXPORT=""
if [[ -f "/home/aryan/.espressif/v6.0.1/esp-idf/export.sh" ]]; then
    IDF_EXPORT="/home/aryan/.espressif/v6.0.1/esp-idf/export.sh"
elif [[ -n "${IDF_PATH:-}" ]] && [[ -f "${IDF_PATH}/export.sh" ]]; then
    IDF_EXPORT="${IDF_PATH}/export.sh"
elif [[ -f "${HOME}/esp/esp-idf/export.sh" ]]; then
    IDF_EXPORT="${HOME}/esp/esp-idf/export.sh"
fi

ensure_idf_env() {
    if ! command -v idf.py >/dev/null 2>&1 && [[ -n "${IDF_EXPORT}" ]]; then
        # shellcheck disable=SC1090
        source "${IDF_EXPORT}" >/dev/null 2>&1
    fi
}

check_device() {
    if [[ ! -e "${PORT}" ]]; then
        echo "[ERROR] Device port ${PORT} not found!" >&2
        echo "Check USB cable connection or specify port with: ESPPORT=/dev/ttyACM0 $0 $1" >&2
        exit 1
    fi

    # Check if another process is currently holding the port open
    local occupying_pids
    occupying_pids="$(lsof -t "${PORT}" 2>/dev/null || true)"
    if [[ -n "${occupying_pids}" ]]; then
        echo "[WARNING] Device port ${PORT} is currently in use by process(es): ${occupying_pids}" >&2
        echo "[INFO] Process details:" >&2
        ps -f -p ${occupying_pids} >&2 || true
        # If user runs flash, esptool-flash, or erase, multiple open handles cause serial errors
        if [[ "${CMD:-}" =~ ^(flash|esptool-flash|erase)$ ]]; then
            echo "[INFO] Releasing port ${PORT} for flash operation..." >&2
            kill -TERM ${occupying_pids} 2>/dev/null || true
            sleep 1
        fi
    fi
}

get_esptool() {
    if command -v esptool >/dev/null 2>&1; then
        echo "esptool"
    elif command -v esptool.py >/dev/null 2>&1; then
        echo "esptool.py"
    else
        echo "python3 -m esptool"
    fi
}

CMD="${1:-help}"

case "${CMD}" in
    flash)
        check_device
        ensure_idf_env
        echo "[INFO] Flashing firmware to ESP32 on ${PORT} (baud: ${FLASH_BAUD})..."
        echo "[TIP] If connection hangs at 'Connecting...', press and hold BOOT button on the ESP32."
        (
            cd "${FIRMWARE_DIR}"
            idf.py -p "${PORT}" -b "${FLASH_BAUD}" flash
        )
        echo "[INFO] Flash complete."
        ;;

    esptool-flash)
        check_device
        ensure_idf_env
        ESPTOOL_BIN="$(get_esptool)"
        echo "[INFO] Direct esptool flashing using ${ESPTOOL_BIN} (--before default-reset --after hard-reset)..."
        if [[ ! -f "${BUILD_DIR}/nexus.bin" ]]; then
            echo "[INFO] Building binaries first..."
            (cd "${FIRMWARE_DIR}" && idf.py build)
        fi
        (
            cd "${BUILD_DIR}"
            ${ESPTOOL_BIN} --chip esp32 -p "${PORT}" -b "${FLASH_BAUD}" \
                --before default-reset --after hard-reset write-flash \
                --flash-mode dio --flash-freq 40m --flash-size 2MB \
                0x1000 bootloader/bootloader.bin \
                0x8000 partition_table/partition-table.bin \
                0x10000 nexus.bin
        )
        echo "[INFO] Direct esptool flash complete."
        ;;

    erase)
        check_device
        ensure_idf_env
        ESPTOOL_BIN="$(get_esptool)"
        echo "[INFO] Erasing entire ESP32 flash chip on ${PORT} using ${ESPTOOL_BIN}..."
        (
            ${ESPTOOL_BIN} --chip esp32 -p "${PORT}" -b "${FLASH_BAUD}" \
                --before default-reset --after hard-reset erase-flash
        )
        echo "[INFO] Chip erased successfully. You can now reflash via '$0 flash' or '$0 esptool-flash'."
        ;;

    monitor)
        check_device
        ensure_idf_env
        echo "[INFO] Starting ESP-IDF serial monitor on ${PORT} @ ${BAUD} bps..."
        echo "[INFO] Press Ctrl+] to exit monitor."
        (
            cd "${FIRMWARE_DIR}"
            idf.py -p "${PORT}" -b "${BAUD}" monitor
        )
        ;;

    test-monitor)
        # Automated non-interactive monitor capture for qualification testing
        check_device
        DURATION="${2:-10}"
        echo "[INFO] Running automated serial monitor test on ${PORT} for ${DURATION} seconds..."
        python3 -c "
import serial, time, sys
port = '${PORT}'
baud = int('${BAUD}')
duration = float('${DURATION}')
try:
    s = serial.Serial(port, baud, timeout=0.2)
    s.dtr = False
    s.rts = False
    start = time.time()
    total_bytes = 0
    lines = []
    while time.time() - start < duration:
        line = s.readline()
        if line:
            total_bytes += len(line)
            sys.stdout.write(line.decode('utf-8', errors='replace'))
            sys.stdout.flush()
    s.close()
    print(f'\n[SUMMARY] Captured {total_bytes} bytes in {duration}s.')
except Exception as err:
    print(f'[ERROR] Serial test failed: {err}', file=sys.stderr)
    sys.exit(1)
"
        ;;

    run)
        check_device
        ensure_idf_env
        echo "[INFO] Flashing firmware and launching monitor on ${PORT}..."
        (
            cd "${FIRMWARE_DIR}"
            idf.py -p "${PORT}" flash monitor
        )
        ;;

    -h|--help|help)
        echo "Usage: $0 [flash|esptool-flash|erase|monitor|test-monitor|run]"
        echo ""
        echo "Commands:"
        echo "  flash         - Build and flash firmware via idf.py"
        echo "  esptool-flash - Direct esptool write_flash with --before default-reset --after hard-reset"
        echo "  erase         - Complete chip erase via esptool erase_flash"
        echo "  monitor       - Interactive serial monitor (Ctrl+] to exit)"
        echo "  test-monitor  - Automated capture of serial output for N seconds (default: 10s)"
        echo "  run           - Flash firmware and start interactive monitor"
        echo ""
        echo "Environment Overrides:"
        echo "  ESPPORT       - Serial device port (default: /dev/ttyUSB0)"
        echo "  ESPBAUD       - Monitor baud rate (default: 115200)"
        echo "  ESPFLASHBAUD  - Flash baud rate (default: 460800)"
        exit 0
        ;;

    *)
        echo "[ERROR] Unknown command: ${CMD}" >&2
        echo "Run '$0 help' for usage." >&2
        exit 1
        ;;
esac
