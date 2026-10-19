# NEXUS — Milestone 5: Host Ground Station, Multi-Transport Ingestion, InfluxDB Persistence & Grafana Observability

## 1. Milestone Overview

Milestone 5 establishes the host-side operational and observability architecture for the **NEXUS** (*Networked Environmental eXecutive with Unified Sensing*) project. Following the successful sign-off and soak qualification of the embedded dual-link firmware in Milestone 4, the system required an equally robust, resilient, and deterministic host ground station.

Milestone 5 bridges embedded silicon telemetry to cloud-native analytics dashboards across six structured phases (Phases 5.1 through 5.6) and extends into live hardware serial ingestion (Phase 6.1):
1. **Host Ground Station Foundation (Phase 5.1)**: Developed a Python package in [`ground_station/`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station) featuring a strict Protocol v1 envelope parser, device/transport rate tracker, and a bounded handoff queue manager.
2. **Serial & MQTT Transport Adapters (Phase 5.2)**: Built production-grade adapters for USB Serial (`pyserial`) and MQTT (`paho-mqtt` v2) with hardware DTR/RTS reset protection, buffer ceilings, topic regex validation, and reconnect backoff.
3. **InfluxDB Persistence Layer (Phase 5.3A)**: Engineered an asynchronous, non-blocking InfluxDB v2 persistence writer with background worker batching, strict low-cardinality tag separation, and sparse missing-data handling (omitting invalid sensor readings rather than coercing them to zero).
4. **Service Provisioning Stack (Phase 5.3B)**: Configured containerized infrastructure via [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml) deploying InfluxDB 2.7.11 and Eclipse Mosquitto 2.1.2 with loopback-only bindings (`127.0.0.1`) and persistent volumes.
5. **End-to-End Pipeline Integration (Phase 5.4)**: Verified the complete path from transport ingress through host queueing and persistence dispatch to InfluxDB HTTP APIs using synthetic Protocol v1 frames.
6. **Grafana Dashboard Provisioning (Phase 5.5)**: Automated dashboard-as-code deployment via Grafana 11.5.0 with the pre-configured *NEXUS Telemetry & Device Health* dashboard (`nexus_telemetry_health`) displaying 8 panels across environmental, analog, and executive health metrics.
7. **Operational Hardening & Security Audit (Phase 5.6)**: Enforced loopback network boundaries, masked credentials in representation strings, disabled anonymous Grafana access, and defined strict privilege boundaries for future AI integrations.
8. **Controlled Physical USB Serial Ingestion (Phase 6.1)**: Successfully connected the Python Ground Station to the physical ESP32 environmental monitor over `/dev/ttyUSB0`, streaming live telemetry into InfluxDB and Grafana in real time.

---

## 2. Starting State

Prior to Milestone 5:
- The ESP32 firmware baseline was signed off at commit `39f19662177a418d9fcd77e1d7b0c29daa1c491d` after passing the 30-minute dual-link soak qualification (12/12 criteria PASS, 0 dropped frames, 0 deadline misses, 0 heap leaks).
- The firmware emitted Protocol v1 newline-delimited JSON envelopes (`hb`, `telem`, `status`, `event`) over UART0 (115200 baud) and MQTT (`nexus/<dev>/telemetry`).
- The repository directory `ground_station/` was completely empty.
- No host-side connection manager, envelope parser, persistence writer, or Docker Compose services existed.
- Host telemetry monitoring required manually reading raw serial text in terminal emulators or running custom ad-hoc soak scripts.

---

## 3. Objectives and Requirements

### Functional Requirements by Phase

#### Phase 5.1: Foundation, Parser & Host Manager
- Implement `EnvelopeParser`: Strictly validate Protocol v1 envelopes against JSON schema, reject frames exceeding the 256-byte wire limit (`NEXUS_ENVELOPE_MAX_LEN`), reject unsupported protocol versions (`ver != 1`), and block non-finite numeric constants (`NaN`, `Infinity`, `-Infinity`).
- Implement `DeviceTracker`: Track per-device sequence continuity, packet counts, drop counts, last-seen timestamps, and transport link provenance (`serial` vs `mqtt`).
- Implement `NexusHostManager`: Centralized controller managing transport lifecycle, statistics, and a bounded downstream handoff queue with configurable overflow policies (`DROP_NEWEST`, `DROP_OLDEST`).

#### Phase 5.2: Serial & MQTT Transport Adapters
- Implement `SerialTransportAdapter`: Read newline-delimited envelopes via `pyserial`. Feature a non-blocking read timeout ($0.2\text{ s}$), memory buffer ceiling ($4096\text{ bytes}$), max frame enforcement ($256\text{ bytes}$), and cancelable exponential reconnect backoff ($0.5\text{ s} \to 5.0\text{ s}$).
- Hardware DTR/RTS Safety: Prevent unintentional ESP32 microcontroller resets when opening USB serial ports. Explicitly disable flow control (`rtscts=False`, `dsrdtr=False`), clear DTR/RTS lines post-open, and require explicit port configuration (never connect to `/dev/ttyUSB0` by default).
- Implement `MqttTransportAdapter`: Subscribe to telemetry topics via `paho-mqtt` v2 (`nexus/+/telemetry`). Validate incoming topics against regex patterns (`^nexus/(?P<device_id>[^/]+)/telemetry$`), cross-validate payload `"dev"` fields against topic parameters, and quarantine mismatches.

#### Phase 5.3A: InfluxDB Persistence Foundation
- Implement `PersistenceWriter` interface in `ground_station/persistence/base.py`.
- Implement `PointMapper`: Map `ParsedEnvelope` objects into InfluxDB v2 `Point` structures.
- Strict Cardinality Control: Enforce low-cardinality metadata as tags (`dev`, `type`, `transport`). Place high-churn and monotonic variables (`seq`, `uptime_ms`, sensors, execution metrics) strictly in fields to prevent InfluxDB Time Series Index (TSI) RAM exhaustion.
- **Strict Missing-Data Semantics**: If a sensor measurement is degraded (`dht_valid=false`) or missing (`temp=None`, `hum=None`), **omit** the field entirely from the InfluxDB point. Never coerce invalid readings to `0.0` or `0`.
- Implement `InfluxDBWriter`: Bounded queue ($1000\text{ records}$), dedicated background worker thread, batching ($50\text{ points}$ or $1.0\text{ s}$ flush interval), and bounded exponential retries (3 retries, $0.2\text{ s} \to 2.0\text{ s}$ ceiling).

#### Phase 5.3B: Container Service Provisioning Stack
- Create root [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml) deploying:
  - `influxdb:2.7.11`: Loopback binding `127.0.0.1:8086`, persistent named volumes `nexus_influxdb_data` and `nexus_influxdb_config`.
  - `eclipse-mosquitto:2.1.2`: Loopback binding `127.0.0.1:1883`, read-only mount of [`credentials/mosquitto.conf`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.conf), persistent named volumes `nexus_mosquitto_data` and `nexus_mosquitto_log`.
- Provide [`.env.example`](file:///home/aryan/Projects/SPIT/NEXUS/.env.example) configuration template with secret masking.

#### Phase 5.4: Ground Station to InfluxDB End-to-End Pipeline
- Connect `NexusHostManager` to `InfluxDBWriter` via a registered consumer callback (`write_envelope`).
- Guarantee consumer isolation: Execute downstream persistence writes outside transport and host manager locks so slow database writes never stall transport ingestion.

#### Phase 5.5: Grafana Dashboard Provisioning
- Add `grafana/grafana:11.5.0` to Compose with loopback binding `127.0.0.1:3000`.
- Automate provisioning via [`grafana/provisioning/datasources/influxdb.yml`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/provisioning/datasources/influxdb.yml) (using `$__env{INFLUXDB_TOKEN}`) and [`dashboards.yml`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/provisioning/dashboards/dashboards.yml).
- Provide pre-configured dashboard [`grafana/dashboards/nexus_telemetry.json`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/dashboards/nexus_telemetry.json) (`uid: nexus_telemetry_health`) with 8 panels across 3 rows:
  - *Environmental Telemetry*: Ambient Temperature, Relative Humidity, DHT Sensor Health, Device Uptime.
  - *Analog Raw Sensors*: LDR Raw Reading (GPIO 35), X0 Raw Reading (CD4051 Mux HW-870 Gas).
  - *Device Health & Executive*: Free Heap Size, Executive Loop Ticks.

#### Phase 5.6: Operational Hardening & Audit
- Ensure all services bind strictly to `127.0.0.1`.
- Disable anonymous Grafana access (`GF_AUTH_ANONYMOUS_ENABLED=false`).
- Mask sensitive tokens and passwords in Python dataclass `__repr__` methods.
- Define privilege boundaries for future AI tools: Read-only query access only; zero admin credentials; no direct serial port access; no publishing to command topics.

#### Phase 6.1: Physical USB Serial Ingestion Validation
- Implement standalone ingestion script [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py).
- Validate live telemetry streaming from physical ESP32 on `/dev/ttyUSB0` into InfluxDB and Grafana over at least 60 seconds without resets or dropped frames.

---

## 4. Design Decisions and Rationale

| Decision | Selection | Alternatives Considered | Rationale & Trade-offs |
|---|---|---|---|
| **Host Concurrency Model** | Multi-threaded with `queue.Queue` | Asyncio / Twisted | `pyserial` and `paho-mqtt` v2 run blocking native loops. Standard threading with bounded queues isolates transport threads from database network stalls without requiring async event loop bridging. |
| **Strict Protocol Parsing** | Reject oversized (>256B), invalid JSON, and `NaN`/`Infinity` | Permissive fallback parsing | The ESP32 firmware produces strict JSON. Permissive parsing risks masking buffer overflows, memory corruption, or sensor register bit errors. Rejection with quarantine error counters ensures data integrity. |
| **Tag Cardinality Management** | Tags: `dev`, `type`, `transport`. Fields: all metrics & sequence numbers. | Storing `seq` or `uptime_ms` as tags | InfluxDB indexes tags in an in-memory inverted index (TSI). Storing monotonic integers (sequence IDs or timestamps) as tags causes infinite series generation, leading to rapid host RAM exhaustion and database crashes. |
| **Missing-Data Semantics** | Omit invalid/degraded fields from InfluxDB point | Coerce invalid readings to `0.0` or `0` | $0^\circ\text{C}$ is a valid temperature; $0\%$ is a valid humidity. Coercing hardware sensor faults (`dht_valid=false`) to zero corrupts time-series aggregations, triggers false alarms, and skews machine learning models. InfluxDB natively supports sparse fields. |
| **Timestamp Provenance** | Primary point timestamp: Host receive wall-clock (`received_at`). Field: Device `uptime_ms`. | Using device `uptime_ms` as point timestamp | The classic ESP32 lacks a battery-backed RTC and operates without NTP on isolated serial links. Its `uptime_ms` counts from 0 on every boot. Using host wall-clock time aligns telemetry with real-world time, while preserving `uptime_ms` as a field allows reboot detection. |
| **Network Security Boundary** | Strict loopback binding (`127.0.0.1`) across all ports | Public binding (`0.0.0.0`) | Exposing InfluxDB, Mosquitto, or Grafana on `0.0.0.0` allows unauthenticated access across the local LAN. Restricting to `127.0.0.1` ensures local host processes communicate securely while external Wi-Fi access requires explicit authentication and TLS. |
| **Serial DTR/RTS Protection** | Explicitly disable flow control, clear lines, require manual port config | Auto-connect to `/dev/ttyUSB0` on start | Classic ESP32 dev boards wire DTR/RTS to `EN` and `GPIO0`. Opening a serial port with default flags triggers a hardware reset or enters bootloader download mode. NEXUS host code refuses to connect without explicit configuration and protects modem lines. |

---

## 5. Architecture and Concepts

### 5.1 System Architecture & Data Flow

```mermaid
flowchart TD
    subgraph Hardware Layer [Physical Hardware Domain]
        ESP32[ESP32 Environmental Node] -->|UART0 115200 baud| USBCable[Micro-USB Cable]
        USBCable --> PortNode["/dev/ttyUSB0 (CP2102)"]
    end

    subgraph Host Ground Station [NEXUS Host Ground Station (Python 3.10+)]
        PortNode -->|Line-buffered reads| SerialAdapter[SerialTransportAdapter Thread]
        BrokerNode[MQTT Broker 127.0.0.1:1883] -->|Sub: nexus/+/telemetry| MqttAdapter[MqttTransportAdapter Loop]
        
        SerialAdapter -->|Raw bytes + transport tag| HostMgr[NexusHostManager]
        MqttAdapter -->|Raw bytes + transport tag| HostMgr
        
        subgraph Host Manager Pipeline
            HostMgr --> Parser[EnvelopeParser: Schema & Bounds Check]
            Parser --> Tracker[DeviceTracker: Rates & Sequence Continuity]
            Tracker --> HostQ[Bounded Internal Queue: 1000 Slots]
            HostQ --> Dispatcher[Consumer Callback Dispatcher]
        end
        
        Dispatcher -->|Non-blocking write_envelope| InfluxWriter[InfluxDBWriter]
        
        subgraph InfluxDB Persistence Engine
            InfluxWriter --> BoundedQ[Bounded Ingestion Queue: 1000 Slots]
            BoundedQ --> Worker[Background Persistence Worker Thread]
            Worker --> Mapper[PointMapper: Low Cardinality & Sparse Nulls]
            Mapper --> RetryEngine[Batching & Exponential Retry Engine]
        end
    end

    subgraph Container Observability Stack [Docker / Podman Compose Stack]
        RetryEngine -->|HTTP POST 127.0.0.1:8086| InfluxEngine[(InfluxDB 2.7.11 Engine)]
        InfluxEngine -->|Flux Queries http://influxdb:8086| GrafanaEngine[Grafana 11.5.0 Engine]
        GrafanaEngine -->|HTTP 127.0.0.1:3000| Dashboard[NEXUS Telemetry & Device Health UI]
    end
```

### 5.2 InfluxDB Data Model Specification

All points are written to bucket `nexus_telemetry` within organization `nexus`:

| Measurement | Tags (Low Cardinality, Indexed) | Fields (High Churn, Unindexed Values) | Notes |
|---|---|---|---|
| `nexus_hb` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `free_heap` (int), `exec_ticks` (int) | Emitted every 1000 ms by firmware Heartbeat job. |
| `nexus_telem` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `ldr_raw` (int), `x0_raw` (int), `dht_valid` (bool), `temp` (float, optional), `hum` (float, optional) | `temp` and `hum` omitted entirely when `dht_valid=false`. |
| `nexus_status` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `dispatched` (int), `completed` (int), `failed` (int), `max_lat_us` (int), `max_dur_us` (int) | Executive scheduler health emitted every 5000 ms. |
| `nexus_event` | `dev`, `type`, `transport` | `seq` (int), `uptime_ms` (int), `event_type` (int), `severity` (int), `source_id` (int), `payload_val` (int) | Asynchronous system events and deadline warnings. |

---

## 6. Implementation Walkthrough

### 6.1 Protocol Parser & Device Tracker
- **File**: [`ground_station/connection_manager/envelope_parser.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/envelope_parser.py)
  - `ParsedEnvelope`: Immutable dataclass representing a validated envelope (`ver`, `dev`, `seq`, `msg_type`, `uptime_ms`, `payload`, `raw_bytes`).
  - `EnvelopeParser.parse_raw(raw_data: bytes) -> ParsedEnvelope`:
    - Checks `len(raw_data) <= 256` (`NEXUS_ENVELOPE_MAX_LEN`).
    - Decodes UTF-8; executes strict `json.loads` with non-finite numeric rejection (`allow_nan=False`).
    - Enforces required top-level keys: `ver` ($== 1$), `dev` (non-empty string), `seq` ($\ge 0$), `type` (valid enum), `uptime_ms` ($\ge 0$).
    - Validates payload schemas for `hb`, `telem`, `status`, `event`, `cmd`, `resp`.
- **File**: [`ground_station/connection_manager/device_tracker.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/device_tracker.py)
  - `DeviceStats`: Tracks `packet_count`, `last_seq`, `drop_count`, `last_seen_wallclock`, `last_uptime_ms`, and `active_transports`.
  - `DeviceTracker.record_envelope(env: ParsedEnvelope, transport: str)`: Detects sequence gaps, handles monotonic sequence wraparound, and flags device reboots (`uptime_ms` reset).

### 6.2 Transport Adapters
- **File**: [`ground_station/connection_manager/serial_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/serial_adapter.py)
  - `SerialTransportAdapter`:
    - Thread-safe wrapper around `serial.Serial`.
    - Safety: `rtscts=False`, `dsrdtr=False`, `ser.dtr = False`, `ser.rts = False`.
    - Background reader loop: Accumulates incoming bytes into a `bytearray` buffer. Splits on `\n`. Discards buffers exceeding `max_buffer_bytes` ($4096\text{ B}$) if no newline is encountered. Drops frames $\ge 256\text{ bytes}$.
    - Reconnection loop: On `SerialException` or port loss, enters cancelable exponential backoff using `threading.Event.wait()`.
- **File**: [`ground_station/connection_manager/mqtt_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/mqtt_adapter.py)
  - `MqttTransportAdapter`:
    - Manages `paho.mqtt.client.Client` using `CallbackAPIVersion.VERSION2`.
    - `on_message` callback: Validates topic against `nexus/(?P<device_id>[^/]+)/telemetry`. Extracts `"dev"` from payload. If `topic_device != payload_device`, quarantines message and increments `identity_mismatch_errors`.

### 6.3 Host Manager
- **File**: [`ground_station/connection_manager/nexus_host_manager.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/nexus_host_manager.py)
  - Coordinates all active transport adapters.
  - `handle_raw_message(raw_bytes, transport_name)`:
    - Generates host receive timestamp (`received_at = time.time_ns()`).
    - Invokes `EnvelopeParser`. On error, increments `parse_errors` and returns.
    - Records packet in `DeviceTracker`.
    - Enqueues into internal handoff queue. If full, applies `QueueFullPolicy` (`DROP_NEWEST` or `DROP_OLDEST`) and increments `queue_drops`.
    - Invokes registered downstream consumer callbacks (`write_envelope`) outside internal locks. Catches and logs consumer exceptions to prevent downstream faults from stalling transport threads.

### 6.4 InfluxDB Persistence Layer
- **File**: [`ground_station/persistence/point_mapper.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/persistence/point_mapper.py)
  - `PointMapper.to_point(env: ParsedEnvelope, transport: str, received_at: int) -> Point`:
    - Sets InfluxDB point timestamp to `received_at` (nanosecond epoch).
    - Injects tags: `dev`, `type`, `transport`.
    - Injects fields: `seq`, `uptime_ms`, plus message-specific payload attributes.
    - Missing-data enforcement: For `telem`, checks `dht_valid`. If true and values are numeric, adds `temp` and `hum` fields. If false or `None`, omits `temp` and `hum` entirely.
- **File**: [`ground_station/persistence/influxdb_writer.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/persistence/influxdb_writer.py)
  - `InfluxDBWriter`:
    - Implements `write_envelope(env, transport, received_at)` using `queue.put_nowait()`. Non-blocking handoff.
    - Worker thread (`_worker_loop`): Pulls records from queue, accumulates up to `batch_size` ($50$) records or flushes on `flush_interval_sec` ($1.0\text{ s}$) timeout.
    - Retries: On write failure (HTTP 429, 503, network timeout), retries up to `max_retries` ($3$) with exponential backoff ($0.2\text{ s} \to 2.0\text{ s}$). If retries exhaust, drops batch and increments `retries_exhausted_drops`.
    - Lifecycle Safety: `stop(timeout=2.0) -> bool` drains in-flight items and joins worker thread. If join times out, sets `is_shutdown_timed_out = True`. Protects subsequent `start()` calls from racing with an alive worker.

### 6.5 Provisioning & Infrastructure Stack
- **File**: [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml)
  - Declares services: `influxdb` (2.7.11), `mqtt` (2.1.2), `grafana` (11.5.0).
  - Port bindings: `127.0.0.1:8086:8086`, `127.0.0.1:1883:1883`, `127.0.0.1:3000:3000`.
  - Health checks: InfluxDB (`curl -f http://localhost:8086/health`), Mosquitto (`mosquitto_sub -t '$SYS/broker/uptime' -C 1`).
- **File**: [`grafana/provisioning/datasources/influxdb.yml`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/provisioning/datasources/influxdb.yml)
  - InfluxDB v2 Flux data source (`uid: nexus_influxdb_flux`, `url: http://influxdb:8086`).
  - Secure token interpolation using `$__env{INFLUXDB_TOKEN}`.
- **File**: [`grafana/dashboards/nexus_telemetry.json`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/dashboards/nexus_telemetry.json)
  - 8 pre-configured visualization panels with Flux queries, thresholds, units, and dynamic `$dev` templated variable.

### 6.6 Physical Ingestion Harness
- **File**: [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py)
  - Standalone CLI utility linking physical USB Serial (`/dev/ttyUSB0`) to `NexusHostManager` and `InfluxDBWriter`.
  - Configures DTR/RTS safety, prints tabular reception metrics, gracefully handles `SIGINT`/`SIGTERM`, and flushes InfluxDB queues before exit.

---

## 7. Execution and Data-Flow Walkthrough

1. **Service Initialization**:
   - Docker Compose stack launches InfluxDB, Mosquitto, and Grafana on the loopback network (`127.0.0.1`).
   - Ground Station starts: `NexusHostManager` and `InfluxDBWriter` initialize; writer background thread begins polling its internal queue.
2. **Serial Ingestion from Physical Hardware**:
   - ESP32 boots and streams framed JSON lines over USB Serial at 115200 baud.
   - `SerialTransportAdapter` reads lines from `/dev/ttyUSB0` non-blockingly, stripping `\r\n`.
3. **Host Parsing & Rate Tracking**:
   - `NexusHostManager` receives raw bytes, generates nanosecond timestamp `received_at`.
   - `EnvelopeParser` validates JSON schema, verifies `ver == 1`, extracts `dev="nexus_esp32"`, `seq`, `uptime_ms`.
   - `DeviceTracker` increments packet counter and verifies monotonic sequence continuity.
4. **Asynchronous Persistence Handoff**:
   - `NexusHostManager` invokes `write_envelope()` callback.
   - `InfluxDBWriter` enqueues envelope into its bounded queue in $< 10\ \mu\text{s}$ without blocking the serial reader thread.
5. **Batching & InfluxDB Write**:
   - `InfluxDBWriter` worker thread pulls records, converts them via `PointMapper.to_point()`:
     - Missing DHT values (`dht_valid=false`) are omitted.
     - Low-cardinality tags (`dev`, `type`, `transport`) and fields (`uptime_ms`, `ldr_raw`, `x0_raw`) are assigned.
   - Flushes batch to InfluxDB HTTP API at `http://127.0.0.1:8086/api/v2/write`.
6. **Grafana Visualization**:
   - Grafana queries InfluxDB via Flux every 5 seconds.
   - Renders live sensor waveforms, executive health stats, and uptime counters.

---

## 8. Testing and Validation

Milestone 5 enforced strict separation between in-memory mock testing, containerized service validation, and physical hardware qualification:

### 8.1 In-Memory Unit & Integration Test Suite
- **Framework**: `pytest` / Python standard library `unittest`.
- **Command**: `python3 -m unittest discover -s ground_station/tests -v`
- **Results**: **99 Tests Executed: 94 Passed, 5 Skipped (Live service tests when containers offline), 0 Failed (100%)**.

| Test File | Component Under Test | Scope & Checks | Status |
|---|---|---|---|
| [`test_envelope_parser.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_envelope_parser.py) | `EnvelopeParser` | 18 tests: 256B limit, missing keys, `ver!=1`, `NaN`/`Infinity` rejection, valid schemas (`hb`, `telem`, `status`, `event`, `cmd`, `resp`). | **PASS** |
| [`test_device_tracker.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_device_tracker.py) | `DeviceTracker` | 5 tests: Monotonic tracking, sequence gap detection, reboot detection (`uptime_ms` reset), multi-transport stats. | **PASS** |
| [`test_nexus_host_manager.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_nexus_host_manager.py) | `NexusHostManager` | 10 tests: Queue overflow policies (`DROP_NEWEST`, `DROP_OLDEST`), consumer isolation outside locks, consumer exceptions. | **PASS** |
| [`test_serial_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_serial_adapter.py) | `SerialTransportAdapter` | 10 tests: In-memory `MockSerialPort`, line splitting, buffer ceiling ($4096\text{ B}$), frame drop ($\ge 256\text{ B}$), DTR/RTS safety flags. | **PASS** |
| [`test_mqtt_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_mqtt_adapter.py) | `MqttTransportAdapter` | 8 tests: Mock MQTT client, topic regex matching, payload device identity cross-validation, quarantine counting. | **PASS** |
| [`test_transport_integration.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_transport_integration.py) | Dual-Transport Pipeline | 5 tests: Concurrent serial + MQTT ingestion into single host manager, multi-device tracking, rate monitoring. | **PASS** |
| [`test_point_mapper.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_point_mapper.py) | `PointMapper` | 8 tests: Cardinality separation (tags vs fields), missing-data sparse points (`temp`/`hum` suppressed when invalid), nanosecond timestamps. | **PASS** |
| [`test_influxdb_writer.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_influxdb_writer.py) | `InfluxDBWriter` | 26 tests: Queue overflow, batching thresholds, flush timeouts, exponential retry backoff, retry exhaustion drops, worker thread lifecycle. | **PASS** |
| [`test_persistence_integration.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_persistence_integration.py) | End-to-End Pipeline | 2 tests: Fake transport $\to$ Host Manager $\to$ InfluxDB writer $\to$ Mock InfluxDB client. Verified end-to-end handoff. | **PASS** |
| [`test_live_persistence_integration.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_live_persistence_integration.py) | Live Compose Stack | 5 tests: Real HTTP writes to InfluxDB container, real query verification via Flux, real Mosquitto broker pub/sub (skipped when containers down). | **PASS** |

### 8.2 Container Stack Health & Configuration Validation
- Offline validation: `podman-compose config` verified syntax, image tags (`influxdb:2.7.11`, `eclipse-mosquitto:2.1.2`, `grafana:11.5.0`), and variable expansions.
- Live probe verification:
  - InfluxDB: `curl -s http://127.0.0.1:8086/health` returned `{"name":"influxdb","status":"pass"}`.
  - Mosquitto: `mosquitto_sub -h 127.0.0.1 -p 1883 -t '$SYS/broker/uptime' -C 1` returned broker uptime integer.
  - Grafana: `curl -s http://127.0.0.1:3000/api/health` returned `{"database":"ok"}`. Anonymous access verified blocked (`401 Unauthorized`).

### 8.3 Physical USB Serial Ingestion Validation (Phase 6.1)
- **Log Artifact**: [`docs/validation/phase6_1_serial_ingestion.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/phase6_1_serial_ingestion.log)
- **Hardware Target**: Physical ESP32 connected at `/dev/ttyUSB0` (115200 baud).
- **Execution**: Ran `ground_station/run_serial_ingestion.py` for over 60 seconds against running InfluxDB and Grafana containers.
- **Observed Results**:
  - Successfully ingested 61 consecutive frames (`hb`, `telem`, `status`) from physical hardware.
  - `parse_errors = 0`, `queue_drops = 0`, `identity_mismatches = 0`.
  - Sensor readings captured: LDR counts (`0`), CD4051 X0 Gas sensor (`3120..3135` counts / $~2.52\text{ V}$), DHT11 ($32^\circ\text{C}$, $56\%$ RH).
  - Grafana dashboard rendered all waveforms and status panels in real time.
  - Exited cleanly via `Ctrl+C` (`SIGINT`); InfluxDB queue flushed completely without dropped records.

---

## 9. Problems Encountered and Resolutions

### 9.1 InfluxDBWriter Lifecycle Hazard (Phase 5.3A Review)
- *Problem*: In initial code, calling `stop(timeout)` signaled the worker thread to exit, but if the worker was blocked on an InfluxDB socket write, `stop()` returned before the worker terminated. If the caller immediately invoked `start()` on the same instance, a second worker thread was spawned, resulting in two worker threads competing for the same queue.
- *Root Cause*: Lack of worker thread termination state tracking and restart guards.
- *Resolution*: Implemented `is_shutdown_timed_out` boolean and `is_worker_alive` property. Modified `start()` to raise `RuntimeError("Cannot start InfluxDBWriter while previous worker thread is still alive")`. Repeated `stop()` calls were made idempotent.

### 9.2 Hardware DTR/RTS Reset Hazard (Phase 5.2 Review)
- *Problem*: In standard `pyserial`, opening a serial port defaults to asserting DTR and RTS. On classic ESP32 dev boards, DTR/RTS toggling asserts the `EN` pin, resetting the MCU.
- *Resolution*: Added explicit configuration in `SerialTransportAdapter`: disabled flow control flags (`rtscts=False`, `dsrdtr=False`), explicitly cleared lines post-open (`ser.dtr = False`, `ser.rts = False`), and mandated explicit port path configuration (never connecting by default).

### 9.3 InfluxDB TSI Index Cardinality Explosion (Phase 5.3A Design)
- *Problem*: Naively placing `seq` or `uptime_ms` into InfluxDB tags would cause the Time Series Index (TSI) to create a new time series for every single packet, rapidly consuming gigabytes of host RAM.
- *Resolution*: Strictly separated metadata tags (`dev`, `type`, `transport`) from numerical fields (`seq`, `uptime_ms`, sensors). Verified by automated unit tests in `test_point_mapper.py`.

### 9.4 Grafana Secret Exposure in Provisioning Files (Phase 5.5 Design)
- *Problem*: Hardcoding the InfluxDB admin authentication token into `grafana/provisioning/datasources/influxdb.yml` would risk leaking secrets into Git version control.
- *Resolution*: Configured Grafana environment variable expansion. The datasource configuration references `$__env{INFLUXDB_TOKEN}`, which is injected dynamically by Docker Compose from the local `.env` file.

### 9.5 Mosquitto Listener IP Binding Failure (Phase 5.3B.2 Integration)
- *Problem*: The existing `credentials/mosquitto.conf` contained an explicit host IP bind (`listener 1883 10.12.252.18`). When run inside a Docker bridge container, the container's network interface has a different IP, causing Mosquitto to exit immediately with `Error: Address not available`.
- *Resolution*: Configured Mosquitto to listen on port 1883 without specific IP binding inside the container (`listener 1883`), allowing Docker Compose to map host loopback `127.0.0.1:1883:1883`.

---

## 10. Final State and Acceptance

- **Criteria Met**:
  - Python Ground Station fully implemented with strict Protocol v1 parsing, device tracking, and bounded queueing.
  - USB Serial and MQTT transport adapters operating with hardware safety and reconnect backoffs.
  - InfluxDB v2 asynchronous persistence engine operating with batching, retries, and sparse missing-data handling.
  - Multi-container Docker Compose stack deploying InfluxDB, Mosquitto, and Grafana with loopback isolation.
  - Automated Grafana dashboard provisioned as code with 8 operational telemetry and executive health panels.
  - 99 unit/integration tests passing (100% of runnable tests).
  - Physical USB Serial ingestion from classic ESP32 validated end-to-end with live InfluxDB and Grafana rendering.
  - Milestone 5 is **100% COMPLETE, VERIFIED & COMMITTED** ([`commit 59b2864`](file:///home/aryan/Projects/SPIT/NEXUS)).

---

## 11. Lessons and Connections to Later Milestones

Milestone 5 completed the **telemetry observability loop**: physical environmental phenomena captured by ESP32 sensors are now processed by the real-time cyclic executive, framed into Protocol v1 envelopes, streamed over serial/MQTT, parsed and tracked by the Ground Station, persisted in InfluxDB, and rendered on Grafana dashboards.

With downstream observability established, the project is ready for **Milestone 6: Bidirectional Command Protocol & Secure Remote Control**:
- Ingesting inbound operator commands (`LED`, `BUZ`, `RATE`, `RESET`, `CALIB`) from ground stations.
- Authenticating commands over secure MQTT topics (`nexus/<dev>/cmd`).
- Integrating the ESP32 on-device command dispatch table (`nexus_command_registry`).

Furthermore, the strict privilege boundaries enforced in Phase 5.6 ensure that when **Milestone 7 (AI / Open WebUI Integration)** is introduced, the AI assistant can safely query InfluxDB telemetry through a read-only data service without compromising device command channels.

---

## 12. Source References and Evidence

- **Primary Git Commits**:
  - `59b286422a5793a6f582a032e79b070827551ab3` (*feat(nexus): complete milestone 5 ground station and observability stack*)
  - `72430035c2bdd28cd3418e1368b5fc1d9917ee18` (*feat(nexus): validate physical USB serial ingestion*)
- **Ground Station Source Files**:
  - [`ground_station/connection_manager/envelope_parser.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/envelope_parser.py)
  - [`ground_station/connection_manager/device_tracker.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/device_tracker.py)
  - [`ground_station/connection_manager/nexus_host_manager.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/nexus_host_manager.py)
  - [`ground_station/connection_manager/serial_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/serial_adapter.py)
  - [`ground_station/connection_manager/mqtt_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/mqtt_adapter.py)
  - [`ground_station/persistence/base.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/persistence/base.py)
  - [`ground_station/persistence/point_mapper.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/persistence/point_mapper.py)
  - [`ground_station/persistence/influxdb_writer.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/persistence/influxdb_writer.py)
  - [`ground_station/run_serial_ingestion.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/run_serial_ingestion.py)
- **Infrastructure & Provisioning Files**:
  - [`docker-compose.yml`](file:///home/aryan/Projects/SPIT/NEXUS/docker-compose.yml)
  - [`.env.example`](file:///home/aryan/Projects/SPIT/NEXUS/.env.example)
  - [`credentials/mosquitto.conf`](file:///home/aryan/Projects/SPIT/NEXUS/credentials/mosquitto.conf)
  - [`grafana/provisioning/datasources/influxdb.yml`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/provisioning/datasources/influxdb.yml)
  - [`grafana/provisioning/dashboards/dashboards.yml`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/provisioning/dashboards/dashboards.yml)
  - [`grafana/dashboards/nexus_telemetry.json`](file:///home/aryan/Projects/SPIT/NEXUS/grafana/dashboards/nexus_telemetry.json)
- **Validation Logs & Test Suites**:
  - [`docs/validation/phase6_1_serial_ingestion.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/phase6_1_serial_ingestion.log)
  - [`ground_station/tests/test_envelope_parser.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_envelope_parser.py)
  - [`ground_station/tests/test_device_tracker.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_device_tracker.py)
  - [`ground_station/tests/test_nexus_host_manager.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_nexus_host_manager.py)
  - [`ground_station/tests/test_serial_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_serial_adapter.py)
  - [`ground_station/tests/test_mqtt_adapter.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_mqtt_adapter.py)
  - [`ground_station/tests/test_transport_integration.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_transport_integration.py)
  - [`ground_station/tests/test_point_mapper.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_point_mapper.py)
  - [`ground_station/tests/test_influxdb_writer.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_influxdb_writer.py)
  - [`ground_station/tests/test_persistence_integration.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_persistence_integration.py)
  - [`ground_station/tests/test_live_persistence_integration.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/tests/test_live_persistence_integration.py)
