# NEXUS — Wire Protocol & Telemetry Specification (Protocol v1)

> **Document Status:** Authoritative Wire Protocol & Transport Specification  
> **Protocol Version:** `NEXUS_PROTOCOL_VERSION = 1` (`"ver": 1`)  
> **Primary Source Files:** `firmware/main/transports/nexus_envelope.{h,c}`, `firmware/main/transports/nexus_connection_manager.{h,c}`, `firmware/main/transports/nexus_wifi_mqtt_transport.c`, `firmware/main/command/nexus_command_dispatcher.c`, `ground_station/connection_manager/envelope_parser.py`, `ground_station/connection_manager/mqtt_adapter.py`, `ground_station/connection_manager/serial_adapter.py`

---

## 1. Framing, Encoding & Hard Size Boundaries

| Property | Specification | Firmware Enforcement | Host Enforcement |
| :--- | :--- | :--- | :--- |
| **Wire Encoding** | Compact single-line UTF-8 JSON (no CBOR or binary framing exists in code) | `snprintf` in `nexus_envelope.c` | `json.loads` (`envelope_parser.py:305`) |
| **Frame Delimiter** | Line Feed `\n` (`0x0A`); optional `\r\n` tolerated on ingress | Appends `\n`; splits on `\n` or `\r` (`nexus_connection_manager.c:54`) | Splits on `b"\n"`, strips `\r` (`serial_adapter.py:348-352`) |
| **Maximum Frame Length** | **`< 256` bytes** (`NEXUS_ENVELOPE_MAX_LEN = 256`, max `255` wire bytes) | `written <= 0 \|\| written >= 256` rejected (`nexus_envelope.c:77`, `nexus_command_dispatcher.c:986`) | `len(raw_bytes) >= 256` raises `OversizedEnvelopeError` (`envelope_parser.py:295`) |
| **Device ID (`"dev"`)** | Non-empty ASCII string; `NEXUS_DEV_ID_MAX_LEN = 16` in C (default `"nexus_esp32"`) | `dev_max_len = 16` (`nexus_envelope.h:18`) | Non-empty string (`envelope_parser.py:326`); `^[a-zA-Z0-9_-]{1,32}$` in Flux queries |
| **Numeric Strictness** | Finite JSON numbers only; booleans are rejected where integers/floats are expected | Typed `strtoul` / `snprintf` | `_reject_json_constant` (`NaN`/`Infinity`) + `not isinstance(val, bool)` (`envelope_parser.py:241-255`) |

---

## 2. Common Envelope Header

Every NEXUS Protocol v1 message carries four mandatory header keys plus `"uptime"` (required on `hb`, `telem`, `status`, `event`; present on ESP32 `resp` and `cmd`, optional on host-originated `cmd`):

| JSON Key | Wire Type | Bounds | Semantics |
| :--- | :--- | :--- | :--- |
| `"ver"` | `int` | Exactly `1` | Protocol schema version (`UnsupportedVersionError` otherwise) |
| `"dev"` | `string` | `1..15` chars on ESP32 (`"nexus_esp32"`) | Originating or target device identifier |
| `"seq"` | `uint32` | `0 .. 4294967295` | Monotonic sequence number for telemetry (`mgr->next_seq++`) or echoed command correlation ID (`1 .. 2147483647` from `CommandRouter`) |
| `"type"` | `string` | `"hb"`, `"telem"`, `"status"`, `"event"`, `"cmd"`, `"resp"` | Message discriminator (`EnvelopeParser` also accepts long-form aliases `"heartbeat"`, `"telemetry"`, `"command"`, `"response"`) |
| `"uptime"` | `int64` | `0 .. INT64_MAX` (`ms`) | Device monotonic milliseconds since boot (`esp_timer_get_time() / 1000LL`); omitted on host-generated `"cmd"` |

---

## 3. Message Type Schemas & Real Sanitized Wire Examples

### 3.1 Heartbeat (`"type": "hb"`) — `1000 ms` Cadence (`CLASS_0`)
Emitted by `job_heartbeat` (`firmware/main/app_main.c:96-108`, `nexus_envelope.c:65-82`):

| Key | C Type | Python Parsed Field (`HeartbeatPayload`) | InfluxDB (`nexus_hb`) | Unit / Notes |
| :--- | :--- | :--- | :--- | :--- |
| `"heap"` | `uint32_t` | `free_heap: int` | `free_heap` | `esp_get_free_heap_size()` in bytes (~`193 KB` with Wi-Fi+MQTT active) |
| `"ticks"` | `uint32_t` | `exec_ticks: int` | `exec_ticks` | Cumulative `100 ms` executive ticks (`~10 Hz` derivative) |

```json
{"ver":1,"dev":"nexus_esp32","seq":204,"type":"hb","uptime":120087,"heap":193640,"ticks":1200}
```

---

### 3.2 Extended Sensor Telemetry (`"type": "telem"`) — `2000 ms` Cadence (`CLASS_2`)
Emitted by `job_connection_telemetry` (`app_main.c:127-197`, `nexus_envelope.c:110-162`; worst-case wire length `165` bytes):

| Key | Presence Rule | C Type | Python (`TelemetryPayload`) | InfluxDB (`nexus_telem`) | Unit & Physical Honesty Rule |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `"ldr"` | Required | `int32_t` | `ldr_raw: int` | `ldr_raw` | Raw 12-bit ADC counts (`0..4095`) on `GPIO 35` |
| `"x0"` | Required | `int32_t` | `x0_raw: int` | `x0_raw` | Raw 12-bit ADC counts (`0..4095`) on `CD4051 X0` (`HW-870`) |
| `"x1"` | Optional (`>= 0`) | `int32_t` | `x1_raw: Optional[int]` | `x1_raw` | `CD4051 X1` counts (**unpopulated `IC2` Hall footprint** on PCB) |
| `"dht_valid"` | Required | `bool` | `dht_valid: bool` | `dht_valid` | `true` iff latest `DHT11` sample has `NEXUS_SENSOR_FLAG_VALID` and no `ERROR` |
| `"temp"` | **Omitted if `!dht_valid`** | `int32_t` | `temp: Optional[float]` | `temp` *(omitted if invalid)* | Ambient temperature in `°C` (never `0` on read failure) |
| `"hum"` | **Omitted if `!dht_valid`** | `int32_t` | `hum: Optional[float]` | `hum` *(omitted if invalid)* | Relative humidity in `%RH` (never `0` on read failure) |
| `"slot"` | Optional (`>= 0`) | `int32_t` | `slot_state: Optional[int]` | `slot_state` | `MOC7811` digital state on `GPIO 34` (`0` = clear, `1` = blocked) |
| `"dist"` | Optional (`>= 0`) | `int32_t` | `dist_cm: Optional[float]` | `dist_cm` | `HC-SR04` distance in `cm` (omitted on echo timeout / out-of-range) |

**Valid DHT + All Sensors Example:**
```json
{"ver":1,"dev":"nexus_esp32","seq":205,"type":"telem","uptime":122087,"ldr":2418,"x0":2730,"x1":412,"temp":29,"hum":58,"dht_valid":true,"slot":0,"dist":24}
```

**Degraded DHT + Ultrasonic Timeout Example (Honest Field Omission):**
```json
{"ver":1,"dev":"nexus_esp32","seq":208,"type":"telem","uptime":124087,"ldr":2420,"x0":2728,"x1":409,"dht_valid":false,"slot":1}
```

---

### 3.3 Executive Status (`"type": "status"`) — `5000 ms` Cadence (`CLASS_2`)
Emitted by `job_executive_metrics` (`app_main.c:199-211`, `nexus_envelope.c:225-248`):

| Key | C Type | Python (`StatusPayload`) | InfluxDB (`nexus_status`) | Semantics |
| :--- | :--- | :--- | :--- | :--- |
| `"disp"` | `uint32_t` | `dispatched: int` | `dispatched` | Cumulative jobs dispatched (`disp == comp + fail + 1` while `metrics` is in-flight) |
| `"comp"` | `uint32_t` | `completed: int` | `completed` | Cumulative jobs returning `true` |
| `"fail"` | `uint32_t` | `failed: int` | `failed` | Cumulative jobs returning `false` |
| `"lat_us"` | `uint32_t` | `max_lat_us: int` | `max_lat_us` | Peak dispatch grid latency (`us`) since boot/reset |
| `"dur_us"` | `uint32_t` | `max_dur_us: int` | `max_dur_us` | Peak single-callback execution duration (`us`) since boot/reset |

```json
{"ver":1,"dev":"nexus_esp32","seq":206,"type":"status","uptime":125087,"disp":781,"comp":780,"fail":0,"lat_us":93120,"dur_us":16420}
```

---

### 3.4 Diagnostic Event (`"type": "event"`) — Schema Implemented, Not Emitted at Runtime
Serializer `nexus_envelope_format_event()` (`nexus_envelope.c:195-213`) and parser `EventPayload` (`envelope_parser.py:187, 528-573` -> InfluxDB `nexus_event`) are **Implemented** and unit-tested (`test_milestone4_host.c`, `test_envelope_parser.py`), **but no runtime firmware job pops `s_executive.event_queue` to transmit `"event"` frames**.

```json
{"ver":1,"dev":"nexus_esp32","seq":12,"type":"event","uptime":100,"ev":1,"sev":1,"src":0,"val":0}
```

---

### 3.5 Command Request (`"type": "cmd"`) & Command Response (`"type": "resp"`)
- **Host -> Firmware `"cmd"` (`ground_station/command_router/router.py:668-678`):**
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":42,"type":"cmd","cmd_id":3330,"verb":"ACTUATE","noun":"LED","led_id":1,"state":"on"}
  ```
  *(Note: Parameters are merged as top-level keys alongside `cmd_id`, `verb`, `noun` so firmware's flat `strstr` parser in `nexus_command_dispatcher.c:1028-1075` can extract them without nested JSON AST allocation.)*
- **Firmware -> Host `"resp"` (`nexus_command_dispatcher.c:128-157`):** Echoes `"seq": 42` for async waiter correlation in `CommandRouter`:
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":42,"type":"resp","cmd_id":3330,"verb":"ACTUATE","noun":"LED","status":"completed","code":0,"msg":"LED output state updated","uptime":126410,"led_id":1,"gpio":27,"level":1}
  ```
- **Device-Originated `"cmd"` (`OPEN *`, `nexus_command_dispatcher.c:1148-1197`):** Helper `nexus_command_send_open_request()` is **Implemented** and host-tested (`test_milestone8_host.c:395`), though no physical button/trigger on the ESP32 invokes it at runtime.

---

## 4. Transports, MQTT Topics & Routing Policies

### 4.1 USB Serial (`UART0`)
- **Physical Link:** `115200` baud, `8N1`, no hardware flow control (`GPIO 1` TX / `GPIO 3` RX -> `/dev/ttyUSB0`).
- **Stream Multiplexing:** Firmware writes JSON envelopes to `stdout` (`nexus_serial_transport.c:75`), interleaved with ANSI/text `ESP_LOGI`/`ESP_LOGW` lines. Host `SerialTransportAdapter` + `NexusHostManager` isolate non-JSON boot/log lines via `MalformedJsonError` accounting without stalling ingestion.
- **No-Reset Serial Open (`serial_adapter.py:198-238`):** Configures `rtscts=False, dsrdtr=False, do_not_open=True`, forces `dtr=False` & `rts=False` before and after `open()`, and clears `termios.HUPCL` so opening/closing `/dev/ttyUSB0` does not reset the ESP32.

### 4.2 Wi-Fi & MQTT v3.1.1 (`espressif/mqtt` <-> Eclipse Mosquitto)
- **Authentication:** Anonymous connections are rejected (`allow_anonymous false` in Mosquitto; `wifi_mqtt_init` in `nexus_wifi_mqtt_transport.c:366-377` aborts initialization if `CONFIG_NEXUS_WIFI_SSID` is non-empty and MQTT username/password are blank).
- **Authoritative Topic Map (QoS 1, `retain = 0`):**

| Topic Pattern | Concrete Default (`nexus_esp32`) | Publisher | Subscriber | Payload Types Carried |
| :--- | :--- | :--- | :--- | :--- |
| `<prefix>/telemetry` (`nexus/+/telemetry`) | `nexus/nexus_esp32/telemetry` | **ESP32 Firmware** (`wifi_mqtt_send`, `L552`) | **Ground Station** (`MqttTransportAdapter`, `L43`) | **`hb`, `telem`, `status`, AND `resp`!** *(There is NO separate `/resp` topic)* |
| `<prefix>/cmd` (`nexus/<dev>/cmd`) | `nexus/nexus_esp32/cmd` | **Ground Station** (`publish_command`, `router.py`/`nexus_host_manager.py:413`) | **ESP32 Firmware** (`MQTT_EVENT_CONNECTED`, `L111`) | Inbound **`cmd`** envelopes |

- **Topic Spoofing Quarantine (`mqtt_adapter.py:319-356`):** Host `MqttTransportAdapter` extracts `<device_id>` from `^nexus/(?P<device_id>[^/]+)/telemetry$` and verifies it equals the `"dev"` field inside the JSON payload before forwarding; mismatches increment `identity_mismatch_errors` and are dropped.

### 4.3 Routing Symmetry & Failover Rules

| Direction & Context | Configured Policy | Actual Runtime Behavior |
| :--- | :--- | :--- |
| **Device -> Host Periodic (`hb`, `telem`, `status`)** | `NEXUS_ROUTE_AUTO` (`app_main.c:303`) | **Active/Standby Failover (`nexus_connection_manager.c:413-426`):** Sends exclusively over **MQTT** when `MQTT_CONNECTED`; fails over immediately to **USB Serial** when MQTT is disconnected or degraded. *(Simultaneous dual-emission `NEXUS_ROUTE_BROADCAST` exists in C at `L446` but is not selected in `app_main.c`.)* |
| **Host -> Device Command (`POST /api/command`)** | `transport="auto"` (`default`) | **Serial-Preferred Failover (`nexus_host_manager.py:404-415`):** Sends over **USB Serial** if `serial.is_connected` is `True`; otherwise publishes to **MQTT** `nexus/<dev>/cmd`. Explicit `"serial"` or `"mqtt"` overrides force the chosen link. |
| **Device -> Host Command Reply (`resp`)** | Source-Pinned (`nexus_command_dispatcher.c:1135-1140`) | Replies on `NEXUS_ROUTE_SERIAL_ONLY` if `cmd` arrived on Serial, or `NEXUS_ROUTE_MQTT_ONLY` (`nexus/nexus_esp32/telemetry`) if `cmd` arrived on MQTT. |

### 4.4 Deduplication Across Layers
1. **Firmware Command RX (`nexus_connection_manager.c:516-575`):** 32-entry circular window keyed on `(source_transport, dev, seq)` drops duplicate QoS 1 MQTT redeliveries (`rx_duplicates++`).
2. **Host Ingestion & InfluxDB (`nexus_host_manager.py`, `influxdb_writer.py`):** Intentionally **does not deduplicate** across Serial and MQTT so both transport paths remain auditable via the `transport` tag.
3. **Host Analytics & AI (`telemetry_query.py:471-518`):** `get_raw_envelopes(..., deduplicate=True, correlation_window_sec=0.5)` collapses cross-transport twins sharing `(dev, seq, uptime_ms)` within `0.5 s`.

