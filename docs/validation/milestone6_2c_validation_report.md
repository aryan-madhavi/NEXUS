# NEXUS — Milestone 6.2C Validation Report: ESP32 Wi-Fi/MQTT Credential Integration & End-to-End Hardware Validation

## 1. Executive Summary & Context

Milestone 6.2C implements the smallest safe change required to connect the ESP32 Wi-Fi/MQTT transport to the authenticated, loopback-bound Mosquitto broker established in M6.2B/M6.2B.1, while preserving USB serial operation and the Unified Connection Manager.

Following the initial static integration and unconfigured guard validation, Wi-Fi credentials were provisioned in `credentials/sdkconfig.local` (mode `0600`), the firmware rebuilt, flashed to the physical ESP32 on `/dev/ttyUSB0`, and validated end-to-end against the local Mosquitto broker and Ground Station.

### Key Technical Achievements
1. **MQTT Authentication Wiring**: Configured `esp_mqtt_client_config_t` credentials (`username`, `password`, `client_id`) in `nexus_wifi_mqtt_transport.c` utilizing native ESP-IDF v6.0.1 APIs.
2. **Missing-Credential Guard**: Enforced explicit and safe missing-credential rejection (`NEXUS_CONN_STATE_FAILED`) when Wi-Fi is configured without credentials, preventing silent anonymous fallback.
3. **Repeatable Credential Integration**: Established automatic `SDKCONFIG` fallback in `firmware/CMakeLists.txt` to consume local git-ignored `credentials/sdkconfig.local` (mode `0600`), keeping tracked files (`firmware/sdkconfig` and `firmware/main/Kconfig.projbuild`) completely clean of secrets.
4. **Target Hardware Identification & Flashing**: Successfully identified `ESP32-D0WD-V3` on `/dev/ttyUSB0` (MAC: `8c:94:df:7d:02:58`), flashed the verified M6.2C firmware binary (`build/nexus.bin`), and captured cold-boot execution logs.
5. **Wi-Fi Association & DHCP**: ESP32 successfully associated with access point `Aryan` (channel 11, WPA2-PSK), obtained IP address `10.12.252.214` via DHCP.
6. **Authenticated MQTT Session**: Authenticated as `nexus_device` with client ID `nexus_esp32`, connecting to the broker via host interface `10.12.252.18:1883` forwarded to loopback `127.0.0.1:1883`, preserving broker network isolation.
7. **End-to-End Telemetry Ingestion**: Received 21 verified telemetry packets on topic `nexus/nexus_esp32/telemetry` by the Ground Station subscribing to `nexus/+/telemetry`.
8. **Dual-Transport & Sensor Telemetry Verification**: USB serial output and wireless MQTT telemetry operated concurrently with 0 dropped frames, 0 buffer overflows, and zero queue drops. Valid DHT11 sensor readings (`temp=31°C`, `hum=63%`, `dht_valid=true`) streamed consistently.

---

## 2. Firmware Binary Identity & Target Hardware

- **Target Chip**: ESP32-D0WD-V3 (revision v3.1, 240 MHz, MAC: `8c:94:df:7d:02:58`)
- **Crystal Frequency**: 40 MHz
- **Flash Size**: 4 MB physical (configured for 2 MB partition table in `flash_args`)
- **Serial Interface**: Silicon Labs CP2102 USB-to-UART Bridge on `/dev/ttyUSB0` (115200 baud, 8N1)
- **ESP-IDF Version**: v6.0.1 (native toolchain on Linux x86_64)
- **Binary Image Path**: `build/nexus.bin`
- **Binary Image Size**: 913,856 bytes (`0xdf1c0` bytes; ~13% headroom in 1 MB app partition)
- **Binary SHA-256 Checksum**: `8fad0f8e62192b78a0540567e1a01ad286af3f4943d07eeb8a751164a7d6e155`
- **Active SDKCONFIG**: `credentials/sdkconfig.local` (mode `0600`, ignored by Git)

---

## 3. Credential Provisioning & Security Hygiene

- **Device Identity**: `nexus_device`
- **Client Identifier**: `nexus_esp32`
- **Telemetry Topic**: `nexus/nexus_esp32/telemetry`
- **Command Topic**: `nexus/nexus_esp32/cmd`
- **Ground Station Subscription**: `nexus/+/telemetry`
- **Credential Storage**: Real secrets reside exclusively in ignored local configuration (`credentials/nexus_device.env` and `credentials/sdkconfig.local`).
- **Tracked Defaults**: `firmware/sdkconfig` and `firmware/main/Kconfig.projbuild` maintain empty placeholders (`""`).
- **Exposure Verification**: Zero credentials, password hashes, or bearer tokens leaked in firmware binary strings, diagnostic logs, serial streams, or test traces.
- **Network Boundary**: Mosquitto remains bound to loopback `127.0.0.1:1883` in `docker-compose.yml`. A host forwarder bridges incoming ESP32 packets from host Wi-Fi interface `10.12.252.18:1883` to loopback, avoiding unconstrained `0.0.0.0` container exposure.

---

## 4. Software & Host-Side Validation Results

| Test Suite / Target | Description | Result | Details |
|---|---|---|---|
| `tests/test_milestone4_host` (GCC) | Connection manager, envelope framing, dedup, bounded queues, MQTT auth & missing-credential rejection | **15/15 PASSED (100%)** | Clean compile with `-Wall -Wextra -Werror` |
| `tests/test_milestone4_host_san` (Clang ASan/UBSan) | Memory safety, buffer boundaries, address sanitization | **15/15 PASSED (100%)** | 0 memory leaks, 0 buffer overflows, 0 undefined behaviors |
| `ground_station/tests/` (pytest) | Ground Station adapter, envelope parser, InfluxDB writer, persistence, device tracker | **99/99 PASSED (100%)** | Run duration: 4.06s |
| `tests/soak/` (pytest) | Ground Station soak harness and stress resilience | **19/19 PASSED (100%)** | Run duration: 2.72s |
| `scratch/test_mqtt_auth_acl.py` | Broker authentication, ACL enforcement, subscriber forwarding, spoof rejection | **9/9 PASSED (100%)** | Unauthorized publish rejected; authorized device telemetry delivered |
| `firmware build` (`idf.py`) | Native ESP-IDF v6.0.1 cross-compilation of bootloader, partitions, and app | **0 warnings, 0 errors** | `nexus.bin` generated (913,856 bytes) |
| `git diff --check` | Whitespace, formatting, and conflict marker audit | **0 errors** | Clean working tree diffs |

---

## 5. Hardware Flashing & Cold Boot Analysis

- **Flashing Tool**: `esptool v5.3.0` via `python -m esptool`
- **Flashing Parameters**: `--chip esp32 -b 460800 --before default-reset --after hard-reset write-flash @flash_args`
  - Bootloader: `0x1000` (26,128 bytes) $\rightarrow$ Hash verified
  - Partition Table: `0x8000` (3,072 bytes) $\rightarrow$ Hash verified
  - Application (`nexus.bin`): `0x10000` (913,856 bytes) $\rightarrow$ Hash verified
- **Flashing Outcome**: **SUCCESS** (16.2s transfer at 454.9 kbit/s). Hard reset via RTS pin executed.

### Cold-Boot Execution Timeline (`docs/validation/m6_2c_boot.log`)
1. **System & Peripherals**:
   - `Project name: nexus`, `App version: c6441de-dirty`, `Compile time: Oct 19 2026 11:18:38`
   - `ESP-IDF: v6.0.1`, `Chip rev: v3.1`
   - Free heap: 254,004 bytes.
2. **Self-Tests & Subsystems**:
   - `Executive and bounded data structures self-test PASSED`.
   - `ADC1 initialized for GPIO35 (ch7) and GPIO36 (ch0)`
   - `Sensors initialized: LDR=OK, CD4051=OK, DHT11=OK (total registered=4)`
   - `All sensor drivers and registry initialized successfully`.
3. **Wi-Fi Association**:
   - Wi-Fi STA initialized with WPA2-PSK threshold.
   - Connected with access point `Aryan` (BSSID: `d2:1b:8f:5a:fa:35`, channel 11, RSSI -49 dBm).
   - Acquired DHCP IP: `10.12.252.214` (mask: `255.255.255.0`, gateway: `10.12.252.44`).
4. **MQTT Connection**:
   - Connected to broker at `mqtt://10.12.252.18:1883` with username `nexus_device`.
   - `I (7675) nexus_wifi_mqtt: MQTT connected to broker`.
   - Unified Connection Manager transitioned state from `DISCONNECTED` to `CONNECTED`.
5. **Sensor Quality Invariant**:
   - Initial sample (seq=3, uptime=368ms): `dht_valid=false`, `temp` and `hum` strictly omitted.
   - Subsequent samples (seq=5, 8, 12, ...): `dht_valid=true`, real temperature `temp=31` and humidity `hum=63` emitted.

---

## 6. End-to-End Wi-Fi / MQTT Telemetry Ingestion

Captured 20.0s of live MQTT stream via Ground Station subscriber on topic `nexus/+/telemetry` (`docs/validation/m6_2c_mqtt_telemetry.log`):

- **Broker**: `nexus_broker` (Mosquitto 2.1.2)
- **Target Topic**: `nexus/nexus_esp32/telemetry`
- **Total Received Packets**: 21 packets
  - **Heartbeats (`hb`)**: 12 packets (`seq: 14, 15, 17, 19, 21, 22, 24, 25, 28, 29, 31, 33, 34`)
  - **Status Reports (`status`)**: 2 packets (`seq: 18, 27` showing `comp=51` and `comp=77`, `fail=0`)
  - **Sensor Telemetry (`telem`)**: 7 packets (`seq: 16, 20, 23, 26, 30, 32`)
- **Packet Integrity**:
  - Valid JSON framing across 100% of packets.
  - Zero dropped sequence numbers in the MQTT stream.
  - Sensor readings verified: `temp=31`, `hum=63`, `ldr=0`, `x0=1296..1455`, `dht_valid=true`.
  - Executive status shows `failed=0`, `dline_misses=0`, `q_overflows=0`.
  - Connection manager stats: `tx_drop=0`, `tx_fail=0`, `rx_dup=0`.

---

## 7. Physical USB Serial Ingestion Verification (`docs/validation/m6_2c_serial_ingestion.log`)

Execution of `ground_station/run_serial_ingestion.py` against `/dev/ttyUSB0` for 10.0 seconds:
- **Bytes Read**: 24,892 bytes
- **Serial Frames Forwarded**: 632
- **Envelopes Parsed**: 17 total (10 `hb`, 2 `status`, 5 `telem`)
- **Queue Drops**: 0
- **InfluxDB Writes**: 17 successful, 0 failures, 0 drops
- **Direct Database Query Verification**:
  - `nexus_hb`: 10 points
  - `nexus_status`: 2 points
  - `nexus_telem`: 5 points (`temp=31.0°C`, `hum=62.0-63.0%`, `ldr_raw=0`, `x0_raw=1328-1477`)

---

## 8. Artifacts Created & Preserved

- `docs/validation/m6_2c_boot.log`: Raw serial boot log from the newly flashed ESP32 showing boot, Wi-Fi association, DHCP lease, and MQTT broker connection.
- `docs/validation/m6_2c_mqtt_telemetry.log`: Ground Station MQTT subscriber log capturing 21 live telemetry packets from the physical ESP32.
- `docs/validation/m6_2c_serial_ingestion.log`: Ground Station serial ingestion and InfluxDB persistence log.
- `docs/validation/milestone6_2c_validation_report.md`: This comprehensive validation report.
- `credentials/sdkconfig.local`: Mode `0600`, ignored by Git, contains local device build configuration.
- `docker-compose.yml`: Uncommitted changes from M6.2B/M6.2B.1 preserved.
