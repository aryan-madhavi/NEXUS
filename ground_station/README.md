# NEXUS Ground Station — Host Foundation, Adapters & Persistence Provisioning (Milestone 5, Phase 5.3B.2)

Part of the **NEXUS Environmental Monitoring and Local-AI Ground Station Project**.

Phase 5.3B establishes full local service provisioning and Compose integration for the NEXUS Ground Station:
- **Unified Connection Manager & Queue** (`NexusHostManager`, `TransportAdapter`, `QueueFullPolicy`)
- **Strict Protocol v1 Envelope Parser** (`EnvelopeParser`)
- **Device & Transport Identity Tracker** (`DeviceTracker`)
- **USB Serial Transport Adapter** (`SerialTransportAdapter`, `SerialConfig`, `SerialStats`)
- **MQTT Transport Adapter** (`MqttTransportAdapter`, `MqttConfig`, `MqttStats`)
- **InfluxDB Persistence Foundation** (`PersistenceWriter`, `InfluxDBWriter`, `PointMapper`, `InfluxDBConfig`, `InfluxDBStats`, `PersistenceQueuePolicy`)
- **Service Provisioning Stack** (`docker-compose.yml`, InfluxDB 2.7.11 & Eclipse Mosquitto 2.1.2)
- **Deterministic In-Memory Test Suite** (92 automated unit and integration tests)

---

## 1. Scope & Implementation Boundaries

### Implemented in Phase 5.1, Phase 5.2 & Phase 5.3A
- **Protocol v1 Envelope Parser**: Strict validation of newline-delimited JSON envelopes (`hb`, `telem`, `status`, `event`, `cmd`, `resp`) up to 256 bytes wire-length limit (`NEXUS_ENVELOPE_MAX_LEN`). Rejects oversized payloads, malformed JSON, unsupported versions (`ver != 1`), and non-finite numeric constants (`NaN`, `Infinity`, `-Infinity`).
- **Bounded Downstream Handoff Queue**: Configurable capacity (`queue_capacity`) and overflow policies (`DROP_NEWEST`, `DROP_OLDEST`) with explicit drop and high-water mark counters.
- **USB Serial Adapter**: Reads line-delimited envelopes via `pyserial`. Features bounded buffering (4096-byte ceiling), max frame length enforcement (>= 256 bytes dropped as oversized), partial line recovery, and exponential reconnect backoff.
- **Hardware Safety & DTR/RTS Protection**: Prevents unintended ESP32 hardware resets on USB serial open by explicitly disabling RTS/DTR handshakes and avoiding toggling. Requires explicit port configuration before connecting (never opens `/dev/ttyUSB0` by default).
- **MQTT Adapter**: Subscribes to device telemetry using Paho MQTT (`CallbackAPIVersion.VERSION2`). Enforces topic regex matching (`nexus/<device_id>/telemetry`), payload device identity cross-validation, and error quarantine.
- **InfluxDB Persistence Layer**: Bounded, non-blocking asynchronous writer protocol (`PersistenceWriter`) and InfluxDB v2 implementation (`InfluxDBWriter`) with worker thread batching, exponential retry backoff, and strict tag/field cardinality control.
- **Strict Sensor Missing-Data Semantics**: Invalid DHT measurements (`dht_valid=false`) or missing temperature/humidity values are omitted from InfluxDB points and never fabricated as numeric zeros.
- **Timestamp Provenance**: Point timestamps represent host receive wall-clock time (`received_at` in nanoseconds), preserving device `uptime_ms` as an integer metric field.
- **Isolated Error & Lifecycle Management**: Transport errors, parsing errors, queue drops, and database write/retry failures are tracked in separate, non-overlapping counters. Start/stop lifecycles are deterministic, thread-safe, and idempotent.
- **Controlled Testability**: 100% of unit and integration tests run in-memory using mock serial ports, mock MQTT clients, and mock InfluxDB clients with zero hardware, live broker, or network dependencies.

### Planned for Later Phases (Explicitly Out-of-Scope)
- **No live InfluxDB server or network connectivity** (Tested exclusively via mock client; live server integration deferred).
- **No Grafana dashboards or Docker provisioning** (Deferred to Phase 5.3B / later).
- **No Open WebUI or AI inference** (Deferred to Milestone 6).
- **No cross-transport message deduplication** (Deduplication policy will be established once multi-link physical stream characteristics are empirically evaluated; transport provenance is preserved via the `transport` tag).

---

## 2. Hardware Safety & Serial Configuration

> [!WARNING]
> **Serial Port Hardware Caution & Validation Boundary:**
> On classic ESP32 development boards (e.g. NodeMCU, DevKit V1), the onboard USB-UART bridge (CP2102 or CH340) wires DTR and RTS through a dual-transistor circuit to the board's `CHIP_PU` (EN) and `GPIO0` pins. Inadvertently opening or pulsing a serial port with default terminal settings can pulse DTR/RTS low, causing an unexpected hardware reset or bootloader latch.
>
> In NEXUS host code:
> 1. Requires explicit port configuration: `port` defaults to `None`, and no port is ever opened at import time, during instantiation, or automatically (never connects to `/dev/ttyUSB0` without explicit caller configuration).
> 2. Disables flow control flags: `rtscts=False` and `dsrdtr=False`.
> 3. Avoids intentional modem toggles: `ser.dtr = False` and `ser.rts = False` are set post-open.
> 4. All unit and integration tests run entirely in-memory using `MockSerialPort` with zero access to physical device nodes.
>
> **Important Distinction (Static Review vs Hardware Validation):**
> Static code inspection confirms that application code does not pulse DTR/RTS. However, on Linux POSIX systems, the kernel USB-serial driver (`cp210x.ko` or `ch341.ko`) or bridge hardware may generate a transient pulse during the kernel `open()` syscall before userspace executes ioctl calls. Static inspection cannot eliminate this driver-level risk; verifying that opening `/dev/ttyUSB0` does not reset the board requires future, explicitly authorized hardware qualification.

### Serial Configuration Options (`SerialConfig`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `port` | `Optional[str]` | `None` | Serial port path (e.g. `/dev/ttyUSB0`). Must be configured explicitly. |
| `baud_rate` | `int` | `115200` | Baud rate matching ESP32 firmware UART speed. |
| `read_timeout_sec` | `float` | `0.2` | Non-blocking read timeout (allows responsive shutdown without hung threads). |
| `max_buffer_bytes` | `int` | `4096` | Upper memory ceiling for stream buffer against missing newlines. |
| `max_frame_bytes` | `int` | `256` | Maximum frame length matching `NEXUS_ENVELOPE_MAX_LEN`. |
| `reconnect_enabled` | `bool` | `True` | Automatically attempt reconnect if port disconnects. |
| `reconnect_base_delay_sec`| `float` | `0.5` | Initial backoff interval before reconnect. |
| `reconnect_max_delay_sec` | `float` | `5.0` | Maximum backoff interval ceiling. |

---

## 3. MQTT Configuration & Topic Conventions

The MQTT topic hierarchy directly reflects the firmware implementation in `firmware/main/transports/nexus_wifi_mqtt_transport.c`:

- **Device Telemetry Publish**: `nexus/<device_id>/telemetry`
  - All firmware envelopes (`hb`, `telem`, `status`, `event`) are published to this topic.
- **Device Command Ingress**: `nexus/<device_id>/cmd`
  - Inbound commands subscribed by the ESP32 connection manager.
- **Ground Station Telemetry Subscription**: `nexus/+/telemetry`
  - Ground station subscribes to all NEXUS devices using the single-level wildcard `+`.

### Topic & Device Identity Consistency
To protect against spoofing, misconfiguration, or cross-device corruption, `MqttTransportAdapter`:
1. Validates that incoming message topics match the pattern `nexus/<device_id>/telemetry`.
2. Inspects the envelope payload to extract the declared `"dev"` identity.
3. Cross-validates `<device_id>` from the topic against `"dev"` in the payload. If they disagree, the message is quarantined, `identity_mismatch_errors` is incremented, and the message is discarded before reaching the host manager queue.

### MQTT Configuration Options (`MqttConfig`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `"localhost"` | MQTT broker hostname or IP address. |
| `port` | `int` | `1883` | MQTT broker port. |
| `client_id` | `str` | `"nexus_ground_station"` | MQTT client identifier. |
| `keepalive_sec` | `int` | `60` | Keepalive ping interval. |
| `username` | `Optional[str]` | `None` | Broker username (credentials never logged). |
| `password` | `Optional[str]` | `None` | Broker password (credentials never logged). |
| `topic_subscription` | `str` | `"nexus/+/telemetry"` | Inbound telemetry subscription pattern. |
| `topic_regex_pattern` | `str` | `r"^nexus/(?P<device_id>[^/]+)/telemetry$"` | Validation regex for topic structure. |

---

## 4. Reconnect & Shutdown Policies

Both transport adapters implement robust, deterministic lifecycle management:

1. **Serial Reconnect**:
   - Disconnection (e.g. `SerialException` or physical unplug) increments `disconnect_count` and closes the port handle.
   - If `reconnect_enabled` is active, the reader thread enters an exponential backoff loop ($0.5\text{ s} \to 1.0\text{ s} \dots 5.0\text{ s}$).
   - The thread waits on an internal `threading.Event`, allowing immediate shutdown without waiting for backoff timers to expire.
2. **MQTT Reconnect**:
   - Paho MQTT's native background loop (`loop_start()`) handles automatic broker reconnection.
   - Adapter connection state transitions are reflected through `on_connect` and `on_disconnect` callbacks with atomic counter updates.
3. **Deterministic Shutdown**:
   - `NexusHostManager.stop()` invokes `stop()` on all registered transport adapters.
   - Serial ports are closed and background threads joined within a 2.0-second timeout.
   - MQTT network loops are stopped (`loop_stop()`) and connections disconnected (`disconnect()`).
   - Downstream persistence writers (e.g. `InfluxDBWriter`) are managed and stopped via their own explicit `stop()` lifecycle method.
   - All `stop()` implementations are idempotent and safe to call repeatedly.

---

## 5. InfluxDB Persistence Layer (Phase 5.3A)

The persistence layer lives in `ground_station/persistence/` and provides thread-safe, bounded, asynchronous writes to InfluxDB v2 without blocking transport read loops.

### Architecture & Data Flow

```text
  [Serial Port]  -->  SerialTransportAdapter (thread)
                                |
                                v
  [MQTT Broker]  -->  MqttTransportAdapter (thread)
                                |
                                v
                     NexusHostManager.handle_raw_message()
                                |
                                v (ParsedEnvelope + transport + received_at)
                    Registered Persistence Consumer Callback
                                |
                                v (write_envelope: non-blocking queue.put_nowait)
                    InfluxDBWriter Bounded Queue (max_queue_size)
                                |
                                v (Worker Thread: batch flush / timer flush)
                        PointMapper.to_point()
                                |
                                v (Bounded Retries & Exponential Backoff)
                     InfluxDBClient.write_api.write()
```

### InfluxDB Data Model & Tag Cardinality

To avoid InfluxDB TSI (Time Series Index) RAM explosion, tags are strictly limited to low-cardinality metadata:

| Measurement | Tags (Low Cardinality) | Fields (High Precision / High Churn) |
|---|---|---|
| `nexus_hb` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `free_heap` (int), `exec_ticks` (int) |
| `nexus_telem` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `ldr_raw` (int), `x0_raw` (int), `dht_valid` (bool), `temp` (float, omitted if invalid), `hum` (float, omitted if invalid) |
| `nexus_status` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `dispatched` (int), `completed` (int), `failed` (int), `max_lat_us` (int), `max_dur_us` (int) |
| `nexus_event` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `event_type` (int), `severity` (int), `source_id` (int), `payload_val` (int) |

**Cardinality Justification:**
- `dev`: Stable device identity (e.g. `nexus_esp32`), bounded by physical fleet size.
- `type`: Bounded message type enum (`hb`, `telem`, `status`, `event`).
- `transport`: Bounded link provenance (`serial`, `mqtt`).
- **Never indexed as tags**: `seq`, `uptime_ms`, `event_type`, `severity`, `source_id`, `payload_val`, and sensor values. Storing monotonic sequence numbers or uptime values as tags would create unbounded time series churn, rapidly exhausting host memory.

### Timestamp Semantics & Limitations

1. **Firmware Clock Limitation**: The ESP32 firmware produces `uptime_ms` (a monotonic millisecond count since the ESP32 last booted). The ESP32 does not possess a battery-backed Real-Time Clock (RTC) and does not assume internet NTP connectivity when operating over isolated serial links.
2. **Host Receive Timestamp**: InfluxDB points use host receive wall-clock time (`received_at`, nanoseconds since Unix epoch) as the primary point timestamp.
3. **Telemetry Fidelity**: The firmware's `uptime_ms` is preserved as an integer field on every point, allowing analysts to detect firmware reboots (`uptime_ms` resets to 0) and verify sampling periodicity independently of network/serial latency jitter.

### Sensor Missing-Data Policy

When the ESP32 DHT sensor fails or is degraded (`dht_valid=false`), or when `temp` / `hum` values are `None`:
- `PointMapper` **omits** `temp` and `hum` fields from the InfluxDB point entirely.
- InfluxDB stores sparse points natively without fabricating values.
- Invalid readings are **never** coerced to `0.0` or `0`, preventing spurious anomalies in downstream Grafana dashboards or statistical aggregation.

### Queue Overflow & Retry Policies

- **Bounded Memory**: Persistence queue capacity defaults to `1000` records (`max_queue_size`).
- **Overflow Policy**:
  - `DROP_NEWEST`: Drops incoming records when queue is full; increments `queue_drops`.
  - `DROP_OLDEST`: Evicts the oldest queued record to accept the newest; increments `queue_drops`.
- **Batching**: Envelopes are written when the queue reaches `batch_size` (default `50`) or when `flush_interval_sec` (default `1.0s`) elapses.
- **Bounded Exponential Backoff**: Write errors trigger retries up to `max_retries` (default `3`) with delays doubling from `retry_base_delay_sec` (`0.2s`) to `retry_max_delay_sec` (`2.0s`).
- **Retry Exhaustion**: If all retries fail, the batch is discarded, `retries_exhausted_drops` is incremented, and `write_failures` is recorded. The queue never grows unboundedly during an outage.
- **Clean Shutdown**: `stop(timeout=2.0) -> bool` signals the worker thread to exit and drains any in-flight queued records before closing the client. Returns `True` if the worker terminated within the timeout, or `False` if shutdown timed out.
- **Timed-Out Shutdown Safety**: If `stop(timeout=...)` times out because the worker is blocked on a socket call, `is_shutdown_timed_out` becomes `True` and `is_worker_alive` remains `True`. To prevent race conditions, queue stealing, and overlapping threads, `start()` rejects restart on the same instance with `RuntimeError` while the previous worker thread is alive. Once the previous worker terminates, `is_worker_alive` clears and `start()` can safely proceed. Repeated `stop()` calls remain safe.

### Configuration Options (`InfluxDBConfig`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | `"http://localhost:8086"` | InfluxDB v2 server endpoint URL. |
| `org` | `str` | `"nexus"` | InfluxDB organization name. |
| `bucket` | `str` | `"nexus_telemetry"` | InfluxDB target bucket. |
| `token` | `Optional[str]` | `None` | InfluxDB v2 API authentication token (masked in `repr`). |
| `timeout_ms` | `int` | `3000` | HTTP write request timeout in milliseconds. |
| `max_queue_size` | `int` | `1000` | Maximum queued envelopes before applying drop policy. |
| `batch_size` | `int` | `50` | Maximum records per InfluxDB write batch. |
| `flush_interval_sec` | `float` | `1.0` | Maximum time to buffer records before flushing a partial batch. |
| `max_retries` | `int` | `3` | Maximum retry attempts on network/server write failure. |
| `retry_base_delay_sec`| `float` | `0.2` | Initial retry backoff interval. |
| `retry_max_delay_sec` | `float` | `2.0` | Maximum retry backoff interval ceiling. |
| `queue_policy` | `PersistenceQueuePolicy` | `DROP_NEWEST` | Queue overflow behavior (`DROP_NEWEST` or `DROP_OLDEST`). |
| `measurement_prefix` | `str` | `"nexus"` | Measurement name prefix (e.g. `nexus_telem`). |
| `use_single_measurement` | `bool` | `False` | When True, uses single `nexus` measurement with `type` tag. |

---

## 6. Service Provisioning & Compose Architecture (Milestone 5, Phase 5.3B)

Phase 5.3B establishes local service provisioning and Compose integration for both InfluxDB 2.x and the Eclipse Mosquitto MQTT broker in the root `docker-compose.yml`.

### Architecture Overview

```text
                               +--------------------------------------------+
                               |              Host Workstation              |
                               |                                            |
  +------------------+         |   +------------------------------------+   |
  |  ESP32 Firmware  |         |   |    NEXUS Host Ground Station       |   |
  |  (Physical MCU)  |         |   |   (NexusHostManager / InfluxWriter) |   |
  +--------+---------+         |   +---------+----------------+---------+   |
           |                   |             |                |             |
   Serial  | (UART)            |     MQTT    | (127.0.0.1:    | Influx HTTP | (127.0.0.1:
   /dev/   |                   |             |  1883)         |             |  8086)
   ttyUSB0 |                   |             v                v             |
           v                   |   +------------------------------------+   |
  +--------+---------+         |   |       Docker / Podman Compose      |   |
  | USB Serial Port  |         |   |          (nexus_network)           |   |
  +------------------+         |   |                                    |   |
                               |   |  +--------------+  +-------------+ |   |
                               |   |  |     mqtt     |  |  influxdb   | |   |
                               |   |  |   (broker)   |  |  (engine)   | |   |
                               |   |  +-------+------+  +------+------+ |   |
                               |   +----------|----------------|--------+   |
                               +--------------|----------------|------------+
                                              v                v
                                     [nexus_mosquitto]  [nexus_influxdb]
                                       data & logs       data & config
```

### Compose Services Specification

| Service | Container Name | Image Version | Internal Port | Host Port Binding | Persistent Volumes / Mounts |
|---|---|---|---|---|---|
| `influxdb` | `nexus_influxdb` | `influxdb:2.7.11` | `8086/tcp` | `127.0.0.1:8086` | `nexus_influxdb_data` (`/var/lib/influxdb2`), `nexus_influxdb_config` (`/etc/influxdb2`) |
| `mqtt` | `nexus_broker` | `eclipse-mosquitto:2.1.2` | `1883/tcp` | `127.0.0.1:1883` | `./credentials/mosquitto.conf` (`/mosquitto/config/mosquitto.conf:ro,z`), `nexus_mosquitto_data` (`/mosquitto/data`), `nexus_mosquitto_log` (`/mosquitto/log`) |
| `grafana` | `nexus_grafana` | `grafana/grafana:11.5.0` | `3000/tcp` | `127.0.0.1:3000` | `nexus_grafana_data` (`/var/lib/grafana`), `./grafana/provisioning` (`/etc/grafana/provisioning:ro,z`), `./grafana/dashboards` (`/etc/grafana/dashboards:ro,z`) |


### Key Design & Safety Principles

1. **Pinned Image Versions**:
   - InfluxDB is pinned to `influxdb:2.7.11` (via `${INFLUXDB_VERSION:-2.7.11}`).
   - Mosquitto is pinned to `eclipse-mosquitto:2.1.2` (via `${MOSQUITTO_VERSION:-2.1.2}`), matching the exact image ID (`sha256:8c4aa039...`) identified in the local container environment.
   - Generic or unpinned `latest` tags are avoided to guarantee reproducibility.

2. **Loopback-Only Host Bindings (`127.0.0.1`)**:
   - Both ports `8086` (InfluxDB HTTP) and `1883` (MQTT TCP) are bound exclusively to the loopback interface (`127.0.0.1`).
   - Neither port is exposed to `0.0.0.0` or public interfaces by default, protecting unencrypted telemetry and write APIs from unauthorized external network access.

3. **Network Decision: LAN Wi-Fi Access vs Loopback**:
   > [!IMPORTANT]
   > **Firmware Connection Warning:**
   > A loopback binding (`127.0.0.1:1883`) allows host processes (such as the Ground Station) to communicate with the broker, but it is **strictly unreachable from external LAN devices** (such as the ESP32 connecting over Wi-Fi).
   >
   > If the ESP32 firmware connects to the broker via Wi-Fi:
   > - The host port binding must be explicitly configured to bind to the host's LAN IP (e.g. `192.168.0.110:1883:1883`) or `0.0.0.0:1883:1883`.
   > - If exposed to the LAN, strong credentials (`allow_anonymous false` with a password file) and TLS encryption should be configured.
   > - Do not broaden port bindings to public interfaces without explicit security review.

4. **Preservation of Broker Configuration & Data**:
   - The broker configuration is mounted directly from the tracked/credentials location: `./credentials/mosquitto.conf` (read-only).
   - Retained messages, sessions, and engine persistence use the named volume `nexus_mosquitto_data` (`/mosquitto/data`).
   - Broker logging is isolated to the named volume `nexus_mosquitto_log` (`/mosquitto/log`).
   - No passwords, tokens, or ACL files are overwritten or modified by Compose.

5. **Container Identity & Migration Boundary**:
   > [!NOTE]
   > Compose manages containers according to its own project/service naming scheme (`<project>_<service>_<index>`). Adding a service to `docker-compose.yml` does **not** automatically adopt a pre-existing standalone container.
   >
   > In Phase 5.3B.2:
   > - The pre-existing standalone `nexus_broker` container was verified and gracefully stopped.
   > - The Compose service configuration is prepared and validated offline.
   > - No new containers are launched in this phase. Starting services under Compose requires explicit user approval.

6. **Standalone Broker Recovery Path**:
   If you need to restart the original standalone broker container (without Compose):
   ```bash
   podman run --name nexus_broker --network host \
     -v /home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro \
     -d docker.io/library/eclipse-mosquitto:latest
   ```

### Setup & Startup Workflow

#### 1. Configure Secrets & Environment
```bash
# Copy template (never commit the real .env file!):
cp .env.example .env
chmod 600 .env

# Edit .env to set strong passwords and initial admin tokens:
nano .env
```

#### 2. Validate Compose Configuration (Offline)
Validate syntax, image tags, and variable substitutions without starting containers or contacting image registries:
```bash
# Using podman-compose:
podman-compose config

# Or using Docker Compose (if docker CLI is installed):
docker compose config
```

#### 3. Start Stack Services (When Approved)
```bash
# Start both InfluxDB and Mosquitto in the background:
podman-compose up -d

# Inspect running containers and health status:
podman-compose ps
```

#### 4. Safe Health & Status Inspection
Inspect service health without printing secrets:
```bash
# Verify InfluxDB health endpoint:
curl -s http://127.0.0.1:8086/health
# Expected output: {"name":"influxdb","message":"ready for queries and writes","status":"pass","checks":[]}

# Verify Mosquitto broker reachability via probe:
podman exec nexus_broker mosquitto_sub -h 127.0.0.1 -p 1883 -t '$SYS/broker/uptime' -C 1
```

#### 5. View Logs
```bash
podman-compose logs -f influxdb
podman-compose logs -f mqtt
```

#### 6. Stop Services Safely
```bash
# Graceful shutdown (preserves all persisted database telemetry & broker state in named volumes):
podman-compose down
```

> [!CAUTION]
> **Data Loss Warning:**
> NEVER use `docker compose down -v` or `podman-compose down -v` for routine shutdown!
> The `-v` flag permanently destroys all named persistent volumes (`nexus_influxdb_data`, `nexus_influxdb_config`, `nexus_mosquitto_data`, `nexus_mosquitto_log`), resulting in complete data loss.

### Troubleshooting Guide

- **Port Conflict (`bind: address already in use`)**:
  Another service is listening on port `8086` or `1883`. Check with:
  ```bash
  ss -tulpn | grep -E '8086|1883'
  ```
  Adjust `INFLUXDB_PORT` or `MQTT_PORT` in `.env`.
- **Mosquitto Listener Bind Error (`Error: Address not available`)**:
  If `credentials/mosquitto.conf` contains an explicit IP bind (e.g. `listener 1883 10.12.252.18`) that is not present on the container's network interface, Mosquitto will fail to bind. When running inside a Compose bridge network, use `listener 1883` (without specific IP) in the config, and let Compose port mapping control host binding (`127.0.0.1:1883:1883`).
- **InfluxDB Authentication 401 Unauthorized**:
  Ensure `INFLUXDB_TOKEN` matches `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`. Note that `DOCKER_INFLUXDB_INIT_*` variables are processed only on the **first run** when the volume is newly created.
- **Health Check Failing**:
  Inspect logs with `podman-compose logs [service]` and verify container process state.

---

## 7. Environment, Dependencies & Testing

### Python Version
- Supported: **Python 3.10+** (Tested and verified on **Python 3.14.8** on Linux x86_64).

### Virtual Environment Setup
```bash
# From repository root (/home/aryan/Projects/SPIT/NEXUS):
python3 -m venv .venv
source .venv/bin/activate
```

### Dependency Installation Strategy
`ground_station/requirements.txt` specifies minimum constrained versions for runtime and testing:
```text
pyserial>=3.5
paho-mqtt>=2.0.0
influxdb-client>=1.40.0
pytest>=8.0.0
```

Install dependencies:
```bash
pip install -r ground_station/requirements.txt
```

### Running Automated Unit Tests
All unit and integration tests run entirely in-memory using controlled mock serial ports, mock MQTT clients, and mock InfluxDB clients. No live serial port is opened, no network sockets are created, and no database server is required.

---

## 7. Ground Station to InfluxDB End-to-End Integration (Milestone 5, Phase 5.4)

Phase 5.4 integrates and validates the complete Ground Station ingestion and persistence pipeline:

```text
Synthetic Protocol v1 Raw Frames
              │
              ▼
       [FakeTransport]
              │
              ▼ (on_receive callback)
      [NexusHostManager]
        - Generates host received_at timestamp
        - Parses raw JSON via EnvelopeParser
        - Enforces Protocol v1 validation
        - Tracks device rate and state in DeviceTracker
        - Enqueues into bounded internal queue
        - Dispatches non-blockingly to registered consumers outside transport locks
              │
              ▼ (consumer callback: write_envelope)
      [InfluxDBWriter]
        - Non-blocking bounded queue ingestion (DROP_NEWEST / DROP_OLDEST)
        - Dedicated background worker thread with batching and flush intervals
        - Maps ParsedEnvelope -> InfluxDB Point via PointMapper (suppresses invalid DHT)
        - Exponential retry backoff on write failure
              │
              ▼ (HTTP Write API at 127.0.0.1:8086)
          [InfluxDB]
```

### Verified Pipeline Semantics

1. **Deterministic Transport Isolation**: Synthetic telemetry envelopes are ingested via `FakeTransport` without requiring physical serial hardware, serial probing, or MQTT network exposure.
2. **Consumer Dispatch Isolation**: `NexusHostManager` snapshots consumer callbacks under lock but executes all consumer invocations (`write_envelope`) outside transport and manager locks. Consumer exceptions are isolated and logged without impacting transport ingestion.
3. **Sensor Missing-Data Semantics**: Telemetry envelopes with `dht_valid=false` have their `temp` and `hum` fields suppressed at the `PointMapper` layer. InfluxDB stores sparse points without fabricating zero values.
4. **Non-Telemetry Ingestion**: Non-telemetry envelopes such as heartbeats (`type="hb"`) are routed to `nexus_hb` with system metrics (`free_heap`, `exec_ticks`, `uptime_ms`) preserved as numeric fields.
5. **Malformed Message Filtering**: Envelopes violating Protocol v1 schema (e.g. non-integer sequence numbers) are rejected during parsing, incrementing `parse_errors` on the manager and never reaching persistence.
6. **Duplicate Delivery Semantics**: Repeated envelopes are ingested with distinct host receive timestamps (`received_at`), resulting in separate InfluxDB points without corrupting sequence counters.
7. **Clean Lifecycle & Teardown**: Consumer registration/unregistration is explicit. The writer's background worker terminates deterministically within a bounded join deadline on `stop()`, verifying `is_worker_alive == False` and `is_shutdown_timed_out == False`.

---

## 8. Grafana Dashboard Provisioning & Visualization (Milestone 5, Phase 5.5)

Phase 5.5 adds an automated, reproducible visualization layer via Grafana v11.5.0, provisioned as code directly from the repository.

### Data Source Configuration
- **Engine**: InfluxDB 2.x (Flux query language)
- **Container Network URL**: `http://influxdb:8086` (internal container-to-container communication on `nexus_net`)
- **Organization & Bucket**: `nexus` / `nexus_telemetry`
- **Credential Safety**: Authentication token is injected securely into the container via the environment variable `INFLUXDB_TOKEN` and expanded dynamically in `grafana/provisioning/datasources/influxdb.yml` using `$__env{INFLUXDB_TOKEN}`. Real tokens are **never** hardcoded into versioned provisioning files.
- **Deduplication**: `prune: true` and a deterministic `uid: nexus_influxdb_flux` prevent duplicate data sources on container restart.

### Dashboard: `NEXUS Telemetry & Device Health`
Provisioned automatically into the `NEXUS` folder via `grafana/dashboards/nexus_telemetry.json` (`uid: nexus_telemetry_health`).

| Row / Category | Panel Name | Visualization | Measurement / Field | Units & Semantics |
|---|---|---|---|---|
| **Environmental Telemetry** | Ambient Temperature | Time Series | `nexus_telem.temp` | `°C` (Celsius). Sparse points; suppressed when DHT is degraded. |
| | Relative Humidity | Time Series | `nexus_telem.hum` | `%` (Percentage, 0–100). Suppressed when DHT is degraded. |
| | DHT Sensor Health | Stat Panel | `nexus_telem.dht_valid` | Mapped: `true` $\to$ `VALID` (Green), `false` $\to$ `DEGRADED` (Red). |
| | Device Uptime | Stat Panel | `*.uptime_ms` | `ms` (Milliseconds since MCU boot). Tracks reboot resets. |
| **Analog Raw Sensors** | LDR Raw Reading | Time Series | `nexus_telem.ldr_raw` | Raw 12-bit ADC counts (0–4095) from light sensor. |
| | X0 Raw Reading | Time Series | `nexus_telem.x0_raw` | Raw 12-bit ADC counts (0–4095) from diagnostic channel. |
| **Device Health & Executive** | Device Free Heap | Time Series | `nexus_hb.free_heap` | `Bytes` (IEC format). Tracks memory stability / leaks. |
| | Executive Loop Ticks | Time Series | `nexus_hb.exec_ticks` | Execution ticks per heartbeat interval. |

- **Filtering & Resiliency**: Includes a dynamic `$dev` templated variable populated from `schema.tagValues(bucket: "nexus_telemetry", tag: "dev")` with an `All` regex match (`.*`). Queries use `createEmpty: false` and `spanNulls: false` to ensure missing or suppressed readings are never drawn as zero.
- **Local Access URL**: [`http://127.0.0.1:3000/d/nexus_telemetry_health/nexus-telemetry-and-device-health`](http://127.0.0.1:3000/d/nexus_telemetry_health/nexus-telemetry-and-device-health)
- **Authentication Policy**: Anonymous access is **disabled by default** (`GF_AUTH_ANONYMOUS_ENABLED=false`) in accordance with Phase 5.6 security hardening. All dashboard, data source, and query APIs require user authentication via HTTP Basic Auth or session login (`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`). The `/api/health` probe remains accessible for container health checks.

### Operational Boundaries & Future AI Integration

1. **Local Loopback Security Boundary**:
   - InfluxDB (`127.0.0.1:8086`), Mosquitto (`127.0.0.1:1883`), and Grafana (`127.0.0.1:3000`) are strictly bound to loopback.
   - **LAN Exposure Notice**: Physical ESP32 connection over Wi-Fi requires a future dedicated, secured broker endpoint with TLS and authentication (`allow_anonymous false`). Do not bind `0.0.0.0` without access control.

2. **Future AI Integration Architecture (Open WebUI)**:
   - Planned AI assistant integration (Open WebUI) must query telemetry strictly through a **dedicated read-only custom Python data/tool service** interfacing with InfluxDB.
   - **Privilege Separation Principle**: The AI agent / tool service must **never** be granted direct database admin credentials, unrestricted write permissions, serial port access, or authorization to publish to device command topics.

3. **Synthetic Validation vs Live Hardware Disclaimer**:
   - Telemetry mapping, persistence, and dashboard rendering have been qualified exclusively using **synthetic Protocol v1 frames**.
   - Physical `/dev/ttyUSB0` serial ingestion, ESP32 reset handling, and live Wi-Fi MQTT publishing have **not** been validated in this milestone.

---


## 9. Running Test Suites

All tests run fully offline or against host-local containerized services without touching hardware.

#### Using `pytest` (Recommended):
```bash
.venv/bin/pytest ground_station/tests -v
```

#### Using standard library `unittest`:
```bash
.venv/bin/python -m unittest discover -s ground_station/tests -v
```

#### Running Soak Regression Suite:
```bash
.venv/bin/pytest tests/soak/test_soak_harness.py -v
```

---

## 10. Repository Layout

```text
├── docker-compose.yml                          # Multi-container Compose stack (InfluxDB, Mosquitto, Grafana)
├── .env.example                                # Template for environment credentials and ports
├── credentials/
│   └── mosquitto.conf                          # Mosquitto broker configuration
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── influxdb.yml                    # InfluxDB v2 Flux data source provisioning
│   │   └── dashboards/
│   │       └── dashboards.yml                  # Dashboard provider definition
│   └── dashboards/
│       └── nexus_telemetry.json                # Pre-configured NEXUS Telemetry & Health dashboard
├── ground_station/
│   ├── __init__.py                             # Package export symbols
│   ├── requirements.txt                        # Pinned host dependencies
│   ├── README.md                               # Architecture, safety, and test documentation
│   ├── connection_manager/
│   │   ├── __init__.py                         # Module exports
│   │   ├── envelope_parser.py                  # Strict Protocol v1 schema parser and validator
│   │   ├── device_tracker.py                   # Device/transport identity and rate tracking
│   │   ├── nexus_host_manager.py               # Transport manager, stats, and bounded handoff queue
│   │   ├── serial_adapter.py                   # USB Serial transport adapter (pyserial)
│   │   └── mqtt_adapter.py                     # MQTT transport adapter (paho-mqtt v2)
│   ├── persistence/
│   │   ├── __init__.py                         # Module exports (PersistenceWriter, InfluxDBWriter, etc.)
│   │   ├── base.py                             # Abstract PersistenceWriter protocol & QueuePolicy enum
│   │   ├── point_mapper.py                     # Strict envelope-to-point mapper & cardinality separation
│   │   └── influxdb_writer.py                  # Bounded, batched InfluxDB v2 writer with retries & worker thread
│   └── tests/
│       ├── __init__.py                         # Test package
│       ├── fake_transports.py                  # In-memory fake transport helpers
│       ├── test_envelope_parser.py             # Protocol v1 parser unit tests (18 tests)
│       ├── test_device_tracker.py              # Identity & monotonic tracker unit tests (5 tests)
│       ├── test_nexus_host_manager.py          # Queue overflow, consumer isolation & lifecycle unit tests (10 tests)
│       ├── test_serial_adapter.py              # Serial adapter unit tests (10 tests)
│       ├── test_mqtt_adapter.py                # MQTT adapter unit tests (8 tests)
│       ├── test_transport_integration.py       # Dual-transport integration tests (5 tests)
│       ├── test_point_mapper.py                # PointMapper schema & cardinality tests (8 tests)
│       ├── test_influxdb_writer.py             # InfluxDBWriter queue, retry & lifecycle tests (26 tests)
│       ├── test_persistence_integration.py     # End-to-end transport + host + InfluxDB mock tests (2 tests)
│       └── test_live_persistence_integration.py# Live service end-to-end integration tests (5 tests)
```



