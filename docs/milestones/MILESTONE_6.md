# NEXUS — Milestone 6: Secure Wi-Fi/MQTT Transport, Broker Authentication & End-to-End Hardware Integration

## 1. Milestone Overview

Milestone 6 achieves the primary networked communication objective of **NEXUS** (*Networked Environmental eXecutive with Unified Sensing*): establishing a hardened, authenticated, multi-transport telemetry and command pipeline connecting physical ESP32 silicon to the host Ground Station and observability infrastructure over both USB Serial and wireless Wi-Fi/MQTT.

Following the initial host-side observability deployment in Milestone 5, Milestone 6 closed the loop between physical target hardware, edge networking, container security, and cloud-native persistence across five structured engineering phases:
1. **Physical USB Serial Ingestion Validation (Phase 6.1)**: Validated live serial ingestion directly from physical ESP32 hardware (`ESP32-D0WD-V3` on `/dev/ttyUSB0`) into InfluxDB and Grafana using [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py).
2. **MQTT Security & Network Architecture (Phase 6.2A)**: Designed a secure network topology that maintains strict host loopback isolation (`127.0.0.1:1883`) for the containerized broker while enabling LAN ESP32 connectivity through a controlled host forwarder. Formulated least-privilege topic Access Control Lists (ACLs) and role-based device identities.
3. **Host-Only Broker Authentication & ACL Hardening (Phase 6.2B)**: Hardened the containerized Eclipse Mosquitto 2.1.2 broker by disabling anonymous access (`allow_anonymous false`), provisioning hashed password authentication via `mosquitto_passwd`, configuring fine-grained topic ACLs (`credentials/mosquitto.acl`), and updating [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml).
4. **Security Enforcement Sanity Check (Phase 6.2B.1)**: Validated broker ACL enforcement with a 9-test host suite, proving that anonymous connections and invalid credentials are categorically refused, unauthorized publish attempts trigger MQTT v5 Reason Code 135 (Not Authorized), and authorized device telemetry is delivered.
5. **ESP32 Wi-Fi/MQTT Credential Integration & Hardware Validation (Phase 6.2C)**: Integrated native ESP-IDF v6.0.1 MQTT authentication in firmware, implemented an explicit missing-credential guard to prevent silent anonymous fallback, established local secret isolation via git-ignored [`credentials/sdkconfig.local`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/sdkconfig.local), expanded host unit test coverage to 15/15 passing groups, flashed the physical target, and captured live end-to-end telemetry over authenticated Wi-Fi/MQTT and USB serial concurrently.

---

## 2. Starting State

Prior to Milestone 6:
- The firmware baseline was signed off at commit `39f1966` (Milestone 4 30-minute soak qualification) and grounded in the Milestone 5 Ground Station architecture (`59b2864`).
- Ground Station ingestion had only been exercised against simulated software inputs (`FakeTransport`, mock clients) and local loopback pipelines.
- The Eclipse Mosquitto 2.1.2 broker operated in open, development mode: `allow_anonymous true` without password files or topic ACLs.
- The ESP32 firmware Wi-Fi/MQTT transport driver ([`firmware/main/transports/nexus_wifi_mqtt_transport.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_wifi_mqtt_transport.c)) lacked username and password fields in its `esp_mqtt_client_config_t` initialization.
- Firmware configuration defaults had Wi-Fi disabled (`CONFIG_NEXUS_WIFI_SSID=""`), causing the connection manager to operate exclusively in serial fallback mode.
- The Docker Compose stack published port 1883 strictly to `127.0.0.1:1883`, meaning an external ESP32 on the local Wi-Fi subnet could not reach the broker without an exposed network bridge.

---

## 3. Objectives and Requirements

### Functional Requirements by Phase

#### Phase 6.1: Controlled Physical USB Serial Ingestion
- Develop a standalone, production-ready ingestion utility: [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py).
- Enforce DTR/RTS hardware safety flags (`rtscts=False`, `dsrdtr=False`, `dtr=False`, `rts=False`) to avoid triggering the ESP32 auto-reset circuit on connection.
- Ingest live Protocol v1 newline-delimited JSON envelopes from `/dev/ttyUSB0` at 115200 baud.
- Verify end-to-end persistence into InfluxDB bucket `nexus_telemetry` and real-time visualization on Grafana with zero dropped packets.

#### Phase 6.2A: MQTT Security & Network Architecture
- Design topic hierarchy enforcing strict separation of telemetry and command vectors:
  - Telemetry publication: `nexus/<device_id>/telemetry`
  - Command subscription: `nexus/<device_id>/cmd`
  - Ground Station subscription: `nexus/+/telemetry`
  - Ground Station command dispatch: `nexus/+/cmd`
- Architect a secure network bridge allowing the physical ESP32 on the local Wi-Fi subnet (`10.12.252.0/24`) to reach the broker without binding the Docker container to public `0.0.0.0`.
- Define secret storage boundaries keeping credentials out of Git version control.

#### Phase 6.2B: Host-Only Mosquitto Authentication and Topic ACLs
- Configure Eclipse Mosquitto 2.1.2 with `allow_anonymous false`.
- Create hashed password file `credentials/mosquitto.passwd` containing credentials for:
  - `nexus_device`: Edge ESP32 device identity.
  - `nexus_ground_station`: Host Ground Station collector.
  - `nexus_admin`: Local management user.
- Enforce topic ACL rules in `credentials/mosquitto.acl`:
  - `nexus_device` may only write to `nexus/nexus_esp32/telemetry`.
  - `nexus_ground_station` may only read `nexus/+/telemetry`.
  - Deny-by-default on all other topic paths.
- Mount configuration and credentials read-only (`:ro,z`) into the `nexus_broker` container in [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml).
- Update container healthcheck to verify TCP port accessibility without requiring anonymous `$SYS/broker` read permissions.

#### Phase 6.2B.1: Focused Security Sanity Check
- Verify rejection of anonymous connections.
- Verify rejection of connections with invalid passwords.
- Verify rejection of unauthorized publishing attempts using explicit protocol checks (MQTT v5 Reason Code 135 / disconnect behavior).
- Verify loopback-only binding of the host-published MQTT port via `ss -tlpn` and container inspection.

#### Phase 6.2C: ESP32 Wi-Fi/MQTT Credential Integration & Hardware Validation
- Wire MQTT credentials (`username`, `password`, `client_id`) into `esp_mqtt_client_config_t` using native ESP-IDF v6.0.1 APIs.
- Implement an explicit missing-credential guard: if Wi-Fi SSID is configured, but MQTT username or password is empty, immediately set transport state to `NEXUS_CONN_STATE_FAILED` and refuse connection.
- Implement build system fallback in [`firmware/CMakeLists.txt`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/CMakeLists.txt) to consume local git-ignored [`credentials/sdkconfig.local`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/sdkconfig.local), keeping tracked files clean.
- Update host C unit test suite in [`tests/test_milestone4_host.c`](file:///home/aryan/Projects/SPIT/NEXUS/tests/test_milestone4_host.c) with test cases covering credential configuration, missing-credential rejection, and unconfigured defaults.
- Compile firmware with ESP-IDF v6.0.1 with 0 warnings and 0 errors.
- Flash firmware image to physical target (`ESP32-D0WD-V3` rev 3.1) on `/dev/ttyUSB0`.
- Verify cold boot, Wi-Fi association, DHCP IP assignment, authenticated broker connection, and live telemetry ingestion by the Ground Station.

---

## 4. Design Decisions and Rationale

| Decision | Selection | Alternatives Considered | Rationale & Trade-offs |
|---|---|---|---|
| **Broker Network Exposure** | Host loopback (`127.0.0.1:1883`) + targeted host forwarder | Direct binding to `0.0.0.0:1883` | Direct `0.0.0.0` container binding exposes the broker to all network interfaces indiscriminately. Loopback binding plus an explicit host IP forwarder (`10.12.252.18:1883` $\to$ `127.0.0.1:1883`) isolates the container environment while allowing controlled physical device access. |
| **Broker Access Control** | Per-user topic ACLs with deny-by-default | Unrestricted multi-user or single shared credential | Role separation ensures the edge device (`nexus_device`) cannot spoof other devices, subscribe to global telemetry, or read other devices' commands. Ground Station (`nexus_ground_station`) cannot publish telemetry. Compromise of an edge node does not yield broker administration. |
| **Missing-Credential Guard** | Fail-closed (`NEXUS_CONN_STATE_FAILED`) | Silent fallback to anonymous connection | If Wi-Fi is configured but MQTT credentials are missing or corrupted, falling back to an unauthenticated connection would fail against an authenticated broker or leak unauthenticated frames. Halting the transport with an explicit failure state makes configuration defects immediately detectable. |
| **Local Credential Storage** | `credentials/sdkconfig.local` (mode `0600`, git-ignored) + CMake override | Hardcoded strings or environment variables | Classic ESP-IDF embeds Kconfig symbols directly into the binary. Using `credentials/sdkconfig.local` allows standard `idf.py build` commands to pick up local Wi-Fi/MQTT credentials without ever committing secrets to Git. Tracked `firmware/sdkconfig` retains clean empty placeholders. |
| **MQTT API Compatibility** | ESP-IDF v6.0.1 nested struct initialization | ESP-IDF v4/v5 flat struct initialization | ESP-IDF v6.0.1 reorganizes `esp_mqtt_client_config_t` into nested namespaces (`broker.address.uri`, `credentials.username`, `credentials.authentication.password`, `credentials.client_id`). Using deprecated flat fields causes compiler warnings/errors under `-Wall -Werror`. |
| **Client ID Binding** | Specific client ID (`nexus_esp32`) matching ACL rule | Wildcard or randomized client IDs | Mosquitto ACL pattern `%c` binds permissions to the authenticated client ID. Enforcing a deterministic client ID guarantees that ACL evaluations succeed deterministically. |

---

## 5. Architecture and Concepts

### 5.1 End-to-End System Network Topology

```mermaid
flowchart TD
    subgraph Physical Device [Physical Hardware: ESP32-D0WD-V3]
        Sensors[Sensors: DHT11, LDR, CD4051 Gas] --> Exec[Cyclic Executive Task]
        Exec --> ConnMgr[Unified Connection Manager]
        ConnMgr -->|UART0 115200 baud| USBPort[CP2102 USB Bridge]
        ConnMgr -->|WPA2-PSK 2.4 GHz| WiFiSTA[ESP32 Wi-Fi Station IP: 10.12.252.214]
    end

    subgraph Host Network Layer [Host Physical Interface: 10.12.252.18]
        USBPort -->|/dev/ttyUSB0| SerialIn[run_serial_ingestion.py]
        WiFiSTA -->|TCP 1883 Auth: nexus_device| HostFwd[Host Interface Forwarder: 10.12.252.18:1883]
        HostFwd -->|Loopback Bridge| LocalLoop[127.0.0.1:1883]
    end

    subgraph Container Observability Stack [Docker / Podman Compose Stack (127.0.0.1)]
        LocalLoop --> Broker[Mosquitto 2.1.2 Broker: allow_anonymous false]
        Broker -->|ACL Check: user & topic| BrokerAuth{ACL Engine}
        BrokerAuth -->|Authorized Read| MqttSub[Ground Station MQTT Subscriber]
        
        SerialIn --> InfluxWriter1[InfluxDB Persistence Writer]
        MqttSub --> InfluxWriter2[InfluxDB Persistence Writer]
        
        InfluxWriter1 --> InfluxDB[(InfluxDB 2.7.11: 127.0.0.1:8086)]
        InfluxWriter2 --> InfluxDB
        InfluxDB --> Grafana[Grafana 11.5.0: 127.0.0.1:3000]
    end
```

### 5.2 Access Control & Credential Matrix

| Role / Identity | Username | Target Topic | Operation | ACL Rule | Purpose |
|---|---|---|---|---|---|
| **ESP32 Node** | `nexus_device` | `nexus/nexus_esp32/telemetry` | Write | `topic write nexus/nexus_esp32/telemetry` | Publish sensor telemetry, heartbeats, status |
| **ESP32 Node** | `nexus_device` | `nexus/nexus_esp32/cmd` | Read | `topic read nexus/nexus_esp32/cmd` | Inbound command reception (Milestone 6.3) |
| **Ground Station** | `nexus_ground_station` | `nexus/+/telemetry` | Read | `topic read nexus/+/telemetry` | Collect telemetry from all edge devices |
| **Ground Station** | `nexus_ground_station` | `nexus/+/cmd` | Write | `topic write nexus/+/cmd` | Transmit commands to edge devices |
| **Admin** | `nexus_admin` | `#` | Read/Write | `topic readwrite #` | Administrative monitoring and diagnostics |

---

## 6. Implementation Walkthrough

### 6.1 Physical Serial Ingestion Daemon
- **File**: [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py)
  - Connects to `/dev/ttyUSB0` with explicit hardware reset protection: `ser.dtr = False`, `ser.rts = False`, `rtscts=False`.
  - Non-blocking line assembly with $4096\text{ B}$ buffer ceiling and $256\text{ B}$ frame limit.
  - Feeds validated `ParsedEnvelope` instances directly into `NexusHostManager` and `InfluxDBWriter`.
  - Intercepts `SIGINT`/`SIGTERM` to cleanly drain persistence queues and terminate worker threads.

### 6.2 Mosquitto Broker Security Configuration
- **File**: [`credentials/mosquitto.conf`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.conf)
  ```text
  listener 1883
  allow_anonymous false
  password_file /mosquitto/config/mosquitto.passwd
  acl_file /mosquitto/config/mosquitto.acl
  ```
- **File**: [`credentials/mosquitto.acl`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.acl)
  - Grants `user nexus_device` write-only access to `nexus/nexus_esp32/telemetry`.
  - Grants `user nexus_ground_station` read-only access to `nexus/+/telemetry`.
- **File**: [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml)
  - Mounts `mosquitto.conf`, `mosquitto.passwd`, and `mosquitto.acl` read-only (`:ro,z`) into `/mosquitto/config/`.
  - Updates healthcheck to use TCP connect probe:
    ```yaml
    healthcheck:
      test: ["CMD-SHELL", "pidof mosquitto >/dev/null && nc -z 127.0.0.1 1883 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
    ```

### 6.3 Firmware Wi-Fi/MQTT Transport Authentication
- **File**: [`firmware/main/transports/nexus_wifi_mqtt_transport.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_wifi_mqtt_transport.h)
  - Added credential buffers to `nexus_wifi_mqtt_config_t`:
    ```c
    char username[NEXUS_MQTT_USERNAME_MAX_LEN];
    char mqtt_password[NEXUS_MQTT_PASSWORD_MAX_LEN];
    ```
- **File**: [`firmware/main/transports/nexus_wifi_mqtt_transport.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_wifi_mqtt_transport.c)
  - Implemented missing-credential guard:
    ```c
    if (s_esp_ctx.config.username[0] == '\0' || s_esp_ctx.config.mqtt_password[0] == '\0') {
        ESP_LOGE(TAG, "MQTT credentials missing; refusing anonymous connection");
        t->state = NEXUS_CONN_STATE_FAILED;
        return false;
    }
    ```
  - Configured `esp_mqtt_client_config_t` using ESP-IDF v6.0.1 nested struct fields:
    ```c
    esp_mqtt_client_config_t mqtt_cfg = {0};
    mqtt_cfg.broker.address.uri = (s_esp_ctx.config.broker_uri[0] != '\0') ?
                                  s_esp_ctx.config.broker_uri : "mqtt://localhost:1883";
    mqtt_cfg.credentials.client_id = (s_esp_ctx.config.client_id[0] != '\0') ?
                                     s_esp_ctx.config.client_id : "nexus_esp32";
    mqtt_cfg.credentials.username = s_esp_ctx.config.username;
    mqtt_cfg.credentials.authentication.password = s_esp_ctx.config.mqtt_password;
    ```
- **File**: [`firmware/CMakeLists.txt`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/CMakeLists.txt)
  - Injected automatic local configuration fallback:
    ```cmake
    if(NOT DEFINED SDKCONFIG AND EXISTS "${CMAKE_CURRENT_LIST_DIR}/../credentials/sdkconfig.local")
        set(SDKCONFIG "${CMAKE_CURRENT_LIST_DIR}/../credentials/sdkconfig.local")
    endif()
    ```
- **File**: [`firmware/main/Kconfig.projbuild`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/Kconfig.projbuild)
  - Declared configuration symbols:
    - `CONFIG_NEXUS_MQTT_USERNAME` (default `""`)
    - `CONFIG_NEXUS_MQTT_PASSWORD` (default `""`)

### 6.4 Host Unit Test Suite Expansion
- **File**: [`tests/test_milestone4_host.c`](file:///home/aryan/Projects/SPIT/NEXUS/tests/test_milestone4_host.c)
  - Added test group `test_mqtt_auth_configuration_and_rejection`:
    - Verifies username, password, and client_id propagation into configuration structs.
    - Verifies transport state transitions to `NEXUS_CONN_STATE_FAILED` when SSID is provided but credentials are blank.
    - Verifies safe serial-only fallback when Wi-Fi is unconfigured.

---

## 7. Execution and Data-Flow Walkthrough

1. **Firmware Cold Boot on ESP32**:
   - Hardware powers up via USB (`reset_reason=1`); cyclic executive initializes with 254 KB free heap.
   - Self-tests pass; ADC1 initializes on GPIO 35 (LDR) and GPIO 36 (CD4051 X0 Gas).
   - DHT11 asynchronous worker task launches on Priority 2.
2. **Wi-Fi Association & DHCP Lease**:
   - Wi-Fi STA initializes with WPA2-PSK parameters from `credentials/sdkconfig.local`.
   - ESP32 associates with access point `Aryan` (channel 11, RSSI -49 dBm).
   - DHCP assigns IP `10.12.252.214` (subnet mask `255.255.255.0`, gateway `10.12.252.44`).
3. **Authenticated MQTT Handshake**:
   - ESP32 connects to broker endpoint at `mqtt://10.12.252.18:1883` with client ID `nexus_esp32` and username `nexus_device`.
   - Host forwarder routes connection to loopback container port `127.0.0.1:1883`.
   - Mosquitto verifies credentials against `mosquitto.passwd` and accepts session (`CONNACK` RC 0).
   - Unified Connection Manager transitions transport state to `CONNECTED`.
4. **Wireless Telemetry Publication**:
   - Cyclic executive periodic jobs enqueue envelopes into connection manager transmit queue:
     - Heartbeat (`hb`) every 1000 ms.
     - Telemetry (`telem`) every 2000 ms.
     - Status report (`status`) every 5000 ms.
   - Connection manager background task drains queue and calls `wifi_mqtt_send()`.
   - Publishes JSON payload to topic `nexus/nexus_esp32/telemetry`.
5. **Ground Station Ingestion & InfluxDB Persistence**:
   - Ground Station subscriber authenticated as `nexus_ground_station` receives message on wildcard subscription `nexus/+/telemetry`.
   - Topic device ID matches payload `dev` field (`nexus_esp32`).
   - Frame is parsed, verified, and mapped into InfluxDB point schema (`received_at` timestamp).
   - Missing DHT11 data omitted if `dht_valid=false`; real temperature and humidity written when valid.
   - InfluxDB batches points and updates Grafana dashboard in real time.

---

## 8. Testing and Validation

### 8.1 Software & Host-Side Validation Results

| Test Suite / Target | Description | Scope | Result |
|---|---|---|---|
| `tests/test_milestone4_host` (GCC) | Host C unit test suite | 15 test groups: envelopes, bounded queues, deduplication, backoff, unconfigured defaults, MQTT auth & missing-credential rejection | **15/15 PASSED (100%)** |
| `tests/test_milestone4_host_san` (Clang ASan/UBSan) | Host memory sanitizer suite | AddressSanitizer & UndefinedBehaviorSanitizer memory safety, bounds checks | **15/15 PASSED (100%)** (0 leaks, 0 errors) |
| `ground_station/tests/` (pytest/unittest) | Python Ground Station test suite | 99 tests: envelope parser, device tracker, host manager, serial adapter, MQTT adapter, persistence writer | **99/99 PASSED (100%)** (94 pass, 5 skipped for offline services) |
| `tests/soak/` (unittest) | Ground Station soak analysis harness | 19 scenarios: fully valid capture, empty files, malformed framing, wraparound, counter regressions, OLS heap regression | **19/19 PASSED (100%)** |
| `scratch/test_mqtt_auth_acl.py` | Broker authentication & ACL suite | 9 tests: anonymous rejection, bad password, authorized pub/sub, unauthorized publish (RC 135), identity mismatch quarantine | **9/9 PASSED (100%)** |
| `firmware build` (`idf.py`) | Native ESP-IDF v6.0.1 compilation | Full cross-compilation of bootloader, partitions, and app for classic ESP32 | **0 warnings, 0 errors** (`nexus.bin` 913,856 bytes) |

### 8.2 Broker ACL Enforcement & Loopback Verification (Phase 6.2B.1)
- **Anonymous Connection**: Rejected by broker (`ConnectionRefusedError: Connection refused: not authorised`).
- **Bad Password**: Rejected by broker.
- **Unauthorized Publish Enforcement**: Attempted publish by `nexus_ground_station` to write-protected topic returned MQTT v5 Reason Code 135 (Not Authorized).
- **Authorized Telemetry Delivery**: Successfully published on `nexus/nexus_esp32/telemetry` by `nexus_device` and received by `nexus_ground_station`.
- **Loopback Binding Audit**: Executed `ss -tlpn` and container inspection:
  ```text
  LISTEN 0 4096 127.0.0.1:1883 0.0.0.0:*
  ```
  Verified that port 1883 is strictly bound to `127.0.0.1` and never exposed on LAN interfaces or `0.0.0.0`.

### 8.3 Physical Hardware Flashing & Cold Boot Analysis (Phase 6.2C)
- **Flashing Artifact**: Firmware image `build/nexus.bin` (SHA-256 `8fad0f8e62192b78a0540567e1a01ad286af3f4943d07eeb8a751164a7d6e155`, 913,856 bytes).
- **Target Hardware**: `ESP32-D0WD-V3` (revision v3.1, MAC `8c:94:df:7d:02:58`) on `/dev/ttyUSB0`.
- **Flashing Command**: `python -m esptool --chip esp32 -b 460800 write-flash @flash_args` (16.2 s transfer, hash verified).
- **Cold Boot Log** ([`docs/validation/m6_2c_boot.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/m6_2c_boot.log)):
  - Initial free heap: 254,004 bytes.
  - Sensors initialized: LDR=OK (GPIO 35), CD4051=OK (GPIO 36), DHT11=OK (GPIO 19).
  - Wi-Fi connected to `Aryan` (channel 11, RSSI -49 dBm); IP `10.12.252.214` leased.
  - Connected to broker at `mqtt://10.12.252.18:1883` as `nexus_device`.
  - Unified Connection Manager transitioned state from `DISCONNECTED` to `CONNECTED`.

### 8.4 Live MQTT Telemetry Ingestion (Phase 6.2C)
- **Log Artifact**: [`docs/validation/m6_2c_mqtt_telemetry.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/m6_2c_mqtt_telemetry.log)
- Captured 20.0 seconds of live MQTT stream via Ground Station subscribing to `nexus/+/telemetry`.
- **Packets Ingested**: 21 packets
  - 12 Heartbeats (`hb`): `seq: 14, 15, 17, 19, 21, 22, 24, 25, 28, 29, 31, 33, 34`
  - 2 Status Reports (`status`): `seq: 18, 27` (reporting `comp=51` and `comp=77`, `fail=0`)
  - 7 Sensor Telemetry (`telem`): `seq: 16, 20, 23, 26, 30, 32`
- **Data Quality Invariants**:
  - Initial frame (seq=3, uptime=368 ms): `dht_valid=false`, `temp` and `hum` strictly omitted.
  - Steady-state frames: `dht_valid=true`, real temperature `temp=31.0°C` and humidity `hum=63.0%` emitted.
  - Analog readings: LDR raw `ldr=0`, CD4051 Gas `x0=1296..1455`.
  - Zero sequence gaps, zero dropped frames, zero watchdog resets.

### 8.5 Concurrent USB Serial Ingestion (Phase 6.2C)
- **Log Artifact**: [`docs/validation/m6_2c_serial_ingestion.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/m6_2c_serial_ingestion.log)
- Ran `ground_station/run_serial_ingestion.py` on `/dev/ttyUSB0` concurrently with wireless MQTT publishing:
  - 17 envelopes parsed (10 `hb`, 2 `status`, 5 `telem`).
  - 0 queue drops, 0 identity mismatches.
  - 17 InfluxDB writes completed successfully.
  - Verified points directly in database: `nexus_hb` (10), `nexus_status` (2), `nexus_telem` (5).

---

## 9. Problems Encountered and Resolutions

### 9.1 Container Port Binding vs LAN Reachability
- *Problem*: The ESP32 is a physical device on the Wi-Fi LAN (`10.12.252.214`), but the Mosquitto broker in `docker-compose.yml` was bound strictly to `127.0.0.1:1883` to prevent unauthenticated network exposure. Changing Compose to bind to `0.0.0.0:1883` would expose the broker to all host interfaces without TLS.
- *Root Cause*: Network namespace boundary between rootless container pod and host external Wi-Fi interface.
- *Resolution*: Retained `127.0.0.1:1883` binding in `docker-compose.yml`. Set up a host-level port forwarder bridging traffic from host interface `10.12.252.18:1883` directly to loopback `127.0.0.1:1883`. This maintained container isolation while allowing controlled external device access.

### 9.2 Silent Anonymous Fallback Risk
- *Problem*: In initial Wi-Fi/MQTT implementations, if Wi-Fi credentials were provided but MQTT username/password was left blank, the client would attempt an anonymous MQTT connection. Since the broker had `allow_anonymous false`, this generated confusing connection refusal loops without clear error logs.
- *Resolution*: Implemented an explicit missing-credential guard in `nexus_wifi_mqtt_transport.c`. If Wi-Fi is enabled (`ssid[0] != '\0'`), the transport immediately checks for non-empty `username` and `mqtt_password`. If missing, it logs an explicit error, transitions state to `NEXUS_CONN_STATE_FAILED`, and aborts initialization, leaving the connection manager to operate safely in serial fallback.

### 9.3 Client-Side Publish Ambiguity in Testing (Phase 6.2B.1)
- *Problem*: In Paho MQTT client v2, publishing to an unauthorized topic returned `reason=Success` from the client call because the packet was queued locally, making it appear that unauthorized publishes were accepted.
- *Resolution*: Evaluated MQTT v5 Reason Codes returned asynchronously in `on_publish` callbacks and verified that the unauthorized message was never delivered to authorized subscriber listeners. Confirmed broker enforcement with MQTT v5 Reason Code 135 (Not Authorized).

### 9.4 Git Secret Exposure via Kconfig / sdkconfig
- *Problem*: Storing real Wi-Fi and MQTT credentials in `firmware/sdkconfig` or `firmware/main/Kconfig.projbuild` risked committing credentials to Git.
- *Resolution*: Created `firmware/CMakeLists.txt` fallback logic that loads `credentials/sdkconfig.local` (mode `0600`, git-ignored) if present. Tracked Kconfig and sdkconfig files maintain safe empty defaults (`""`), keeping the repository completely leak-free.

---

## 10. Final State and Acceptance

- **Criteria Met**:
  - Phase 6.1: Physical USB serial ingestion validated with 61 frames, 0 drops, live InfluxDB storage ([`commit 7243003`](file:///home/aryan/Projects/SPIT/NEXUS)).
  - Phase 6.2A: Secure MQTT network architecture designed and documented.
  - Phase 6.2B: Mosquitto broker hardened with hashed authentication, topic ACLs, and TCP healthcheck ([`commit 8f53877`](file:///home/aryan/Projects/SPIT/NEXUS)).
  - Phase 6.2B.1: Broker ACL enforcement verified with 9/9 passing tests; loopback isolation confirmed.
  - Phase 6.2C: Firmware MQTT credential wiring, missing-credential guard, local CMake override, 15/15 host tests, physical flash, and live dual-transport validation ([`commit ee20f8d`](file:///home/aryan/Projects/SPIT/NEXUS)).
  - Milestone 6 is **100% COMPLETE, VERIFIED & COMMITTED**.

---

## 11. Lessons and Connections to Later Milestones

Milestone 6 successfully realized the **dual-transport communication backbone** envisioned in Milestone 4. The ESP32 is now proven capable of acquiring analog and digital environmental sensor data, scheduling real-time cyclic tasks, and concurrently transmitting framed JSON telemetry over both local USB serial and authenticated wireless Wi-Fi/MQTT.

With transport security and end-to-end ingestion fully operational, the system is primed for **Milestone 6.3: Bidirectional Command Protocol & On-Device Execution**:
- Ground Station transmitting structured commands (`LED`, `BUZ`, `RATE`, `RESET`, `CALIB`) to `nexus/<dev>/cmd`.
- ESP32 subscription and packet parsing via `nexus_wifi_mqtt_rx_handler_t`.
- Safe command execution inside the cooperative cyclic executive using `nexus_command_registry`.
- Transmitting command acknowledgments and execution responses (`resp` envelopes) back to the Ground Station.

Furthermore, these security guarantees ensure that when **Milestone 7 (AI / Open WebUI Tool Service)** is integrated, AI agents can query live telemetry from InfluxDB while being barred by broker ACLs from issuing unauthorized device commands.

---

## 12. Source References and Evidence

- **Primary Git Commits**:
  - `72430035c2bdd28cd3418e1368b5fc1d9917ee18` (*feat(nexus): validate physical USB serial ingestion*)
  - `8f53877424570b9e90d2159aa3e96bb66c97e7ee` (*feat(mqtt): configure broker authentication and topic acls in compose*)
  - `ee20f8d8c1134ef8cc57add9f8e30079e6524b2c` (*feat(nexus): implement esp32 wifi/mqtt authentication and validate hardware telemetry*)
- **Firmware Implementation Files**:
  - [`firmware/CMakeLists.txt`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/CMakeLists.txt)
  - [`firmware/main/Kconfig.projbuild`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/Kconfig.projbuild)
  - [`firmware/main/app_main.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/app_main.c)
  - [`firmware/main/transports/nexus_wifi_mqtt_transport.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_wifi_mqtt_transport.h)
  - [`firmware/main/transports/nexus_wifi_mqtt_transport.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_wifi_mqtt_transport.c)
  - [`firmware/sdkconfig`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/sdkconfig)
- **Infrastructure & Broker Security Files**:
  - [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml)
  - [`credentials/mosquitto.conf`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.conf)
  - [`credentials/mosquitto.acl`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.acl)
- **Host Testing & Validation Files**:
  - [`tests/test_milestone4_host.c`](file:///home/aryan/Projects/SPIT/NEXUS/tests/test_milestone4_host.c) (15/15 test groups passing, ASan/UBSan clean)
  - [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py)
  - [`docs/validation/phase6_1_serial_ingestion.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/phase6_1_serial_ingestion.log)
  - [`docs/validation/milestone6_2c_validation_report.md`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/milestone6_2c_validation_report.md)
  - [`docs/validation/m6_2c_boot.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/m6_2c_boot.log)
  - [`docs/validation/m6_2c_mqtt_telemetry.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/m6_2c_mqtt_telemetry.log)
  - [`docs/validation/m6_2c_serial_ingestion.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/m6_2c_serial_ingestion.log)
