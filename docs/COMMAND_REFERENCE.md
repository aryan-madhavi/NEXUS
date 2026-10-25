# NEXUS Command & Data Reference Manual

**Authoritative Technical Reference for Operators, Ground Station Integrators & Firmware Engineers**  
**Version:** 1.0.0 (Milestones 8–10 Qualified)  
**Target Hardware:** EDU_ROBO V14 Carrier Board / ESP32-WROOM-32 (`nexus_esp32`)  
**Mission Control:** `http://127.0.0.1:8000` | **Open WebUI:** `http://127.0.0.1:8080` | **Grafana:** `http://127.0.0.1:3000` | **InfluxDB:** `http://127.0.0.1:8086`

---

## 1. Executive Protocol & Execution Architecture

NEXUS commands represent a unified, dual-target command architecture connecting the browser-based Mission Control application, Python Ground Station router, and ESP32 FreeRTOS cyclic executive.

### 1.1 Firmware Device Dispatch vs Host-Local Operations

The system strictly bifurcates command execution into two distinct runtime paradigms:

```
[Browser Operator / REST Client]
              │
              ▼ POST /api/command
    [Command Router (router.py)]
              │
      ┌───────┴────────────────────────┐
      ▼                                ▼
[FIRMWARE_DEVICE_DISPATCH]       [HOST_LOCAL_OPERATION]
(Target: ESP32 Hardware)         (Target: Ground Station Process)
      │                                │
      ├─► USB Serial (/dev/ttyUSB0)    ├─► Telemetry Analysis & Statistics (InfluxDB)
      └─► MQTT Broker (nexus/cmd)      ├─► AI Conversational Agent (Ollama mistral:7b)
                                       ├─► Application Launchers (Dashboard, Grafana)
                                       └─► Data Exporters (JSON / CSV)
```

1. **Firmware Device Dispatch (`FIRMWARE_DEVICE_DISPATCH`):**
   - Transmitted across physical transports to the ESP32 (USB Serial `/dev/ttyUSB0` at 115200 baud or Mosquitto MQTT topic `nexus/cmd`).
   - Processed by the zero-allocation C Command Dispatcher (`firmware/main/command/nexus_command_dispatcher.c`).
   - Returns a binary CBOR or JSON response envelope on `nexus/resp` or UART TX.
2. **Host-Local Operations (`HOST_LOCAL_OPERATION`):**
   - Executed entirely within the Ground Station host process (Python runtime).
   - Encompasses `OPEN` application launchers, `EXPORT` data generation, `DIAGNOSTICS DATABASE/AI_SERVICE`, and `ASK` conversational AI queries.
   - **Device Wire Envelope:** Explicitly tagged **`NOT_APPLICABLE`**. No packets are transmitted over Serial or MQTT to the ESP32.

### 1.2 Protocol Wire Envelopes

#### A. Inbound Command Frame (JSON / CBOR)
```json
{
  "ver": 1,
  "type": "cmd",
  "cmd_id": 1537,
  "seq": 42,
  "verb": "GET",
  "noun": "STATUS",
  "params": {},
  "ts": 1729864200000
}
```

#### B. Outbound Response Frame
```json
{
  "ver": 1,
  "type": "resp",
  "cmd_id": 1537,
  "seq": 42,
  "status": "ok",
  "code": 0,
  "msg": "Executive status nominal",
  "data": {
    "uptime_ms": 53455,
    "heap_free": 184320,
    "state": 2
  },
  "ts": 1729864200045
}
```

---

## 2. Command Execution Model & Safety Classifications

All 115 registered commands are classified into four operational safety categories:

| Classification | Count | Execution Policy | Rejection / Safety Enforcement |
| :--- | :---: | :--- | :--- |
| **SAFE_CONTROL** | 53 | Parameter validation, immediate execution on device/host. | Valid arguments accepted; returns `StatusCode 0 (OK)`. |
| **READ_ONLY** | 41 | Sensor sampling, telemetry query, diagnostics inspection. | Non-destructive; returns telemetry payload; `StatusCode 0 (OK)`. |
| **UNMOUNTED_HARDWARE** | 10 | Commands targeting peripherals unpopulated on EDU_ROBO V14. | Truthfully rejected with `StatusCode 3 (UNSUPPORTED)`. |
| **HAZARDOUS_DESTRUCTIVE** | 9 | System reset, flash erase, queue clear, stress tests. | Rejects unconfirmed requests with `StatusCode 10 (CONFIRM_REQ)`. Requires `"confirmed": true`. |
| **PHYSICAL_ACTUATOR** | 2 | Diagnostic control of Status LEDs (1–4) and Active Buzzer. | Safe pulse limits enforced (Buzzer max 5000 ms). |

---

## 3. Master Parameter Dictionary (27 Parameters)

The following dictionary defines every parameter key, its value semantics, allowed values, units, defaults, and individual value meanings:

### 3.1 Identifiers & Hardware Channels

#### `sensor_id` (`string`, `SENSOR_IDENTIFIER`)
- **Allowed Values:** `ldr`, `dht11`, `cd4051_x0`, `moc7811`, `hcsr04`, `mux_x0`, `mux_x1`
- **Default:** `dht11`
- **Individual Mappings:**
  - `ldr`: Light Dependent Resistor — Ambient light intensity on CD4051 channel X3 (ADC counts 0–4095).
  - `dht11`: DHT11 Digital Sensor — Relative humidity (%) and temperature (°C) on GPIO 25/19.
  - `cd4051`: CD4051 Analog Multiplexer — 8:1 analog input bus routed to ESP32 ADC1_CH0.
  - `cd4051_x0`: HW-870 Infrared Photodetector (IR-1) — Analog obstacle reflection on CD4051 X0.
  - `moc7811`: MOC7811 Slotted Optical Switch — Digital beam status (0=intact, 1=broken) on GPIO 34.
  - `hcsr04`: HC-SR04 Ultrasonic Sensor — Distance (cm) via Trigger (GPIO 19) & Echo (GPIO 35).
  - `mux_x0`: HW-870 Infrared Obstacle Reflection (Channel X0 calibration alias).
  - `mux_x1`: Hall Magnetic Sensor IC2 (Channel X1 calibration alias; unmounted on PCB).

#### `event_id` (`int`, `EVENT_IDENTIFIER`)
- **Allowed Range:** `1 .. 11` (units: `event_type_or_seq`)
- **Default:** `1`
- **Omission / Null:** Optional. If omitted or null, defaults to 1. Handled by firmware dispatcher.
- **Individual Value Meanings (`firmware/main/events/nexus_event_queue.h`):**
  - `1`: `BOOT_START` — FreeRTOS system bootloader execution commenced.
  - `2`: `BOOT_COMPLETE` — All core peripherals, tasks, and queues initialized successfully.
  - `3`: `HEARTBEAT` — Periodic cyclic executive heartbeat pulse (1 Hz).
  - `4`: `WIFI_CONNECTED` — Station Wi-Fi interface connected and IP address leased.
  - `5`: `MQTT_CONNECTED` — Mosquitto broker connection established and topics subscribed.
  - `6`: `TELEMETRY_SAMPLE` — Periodic sensor acquisition frame sampled by executive.
  - `7`: `THRESHOLD_EXCEEDED` — Monitored sensor signal breached configured high/low setpoint.
  - `8`: `COMMAND_RECEIVED` — Inbound command packet accepted from Serial or MQTT wire.
  - `9`: `COMMAND_EXECUTED` — Command dispatcher executed handler and formatted reply.
  - `10`: `ERROR_RAISED` — Transient error or recoverable exception logged in event queue.
  - `11`: `WATCHDOG_RESET` — Task watchdog timer expired triggering defensive reset.
- **Discovery Workflow:** Query active incidents via `GET /api/incidents` or queue events via `DISPLAY QUEUES`.
- **Operational Semantics:** Acknowledges operator review; does not clear cumulative fault statistics (use `CLEAR FAULTS`).

#### `fault_id` (`int`, `FAULT_IDENTIFIER`)
- **Allowed Range:** `1 .. 15` (units: `code_or_id`)
- **Default:** `1`
- **Individual Value Meanings (`firmware/main/common/nexus_common.h`):**
  - `1`: `SENSOR_READ_FAIL` — I2C/SPI or ADC sensor read timed out or returned invalid checksum.
  - `2`: `TELEMETRY_OVERFLOW` — Telemetry ring buffer capacity exhausted; frames dropped.
  - `3`: `QUEUE_FULL` — Inter-task FreeRTOS message queue full; command dropped.
  - `4`: `MQTT_DISCONNECT` — Broker connection severed or TCP socket keepalive timed out.
  - `5`: `HEAP_LOW` — Available FreeRTOS dynamic heap dropped below safety threshold (16 KB).
  - `6`: `WATCHDOG_TIMEOUT` — Monitored task failed to feed watchdog timer within deadline.

#### `warning_id` (`int`, `WARNING_IDENTIFIER`)
- **Allowed Range:** `1 .. 15` (units: `code_or_id`)
- **Default:** `2`
- **Individual Value Meanings:**
  - `1`: `TEMP_HIGH` — Ambient temperature exceeded warning threshold (default: >45°C).
  - `2`: `HUMIDITY_HIGH` — Relative humidity exceeded condensation risk threshold (default: >80%).
  - `3`: `DISTANCE_LOW` — Ultrasonic distance closer than minimum safety margin (default: <10 cm).
  - `4`: `LIGHT_LOW` — Ambient illumination dropped below minimum operating lux (default: <50 counts).

#### `led_id` (`int`, `PHYSICAL_INDEX`)
- **Allowed Range:** `1 .. 4` (units: `channel`)
- **Default:** `1`
- **Individual Value Meanings (`firmware/main/actuators/nexus_actuators.c`):**
  - `1`: Heartbeat LED (Green, GPIO 27) — Blinks at 1 Hz during normal cyclic execution.
  - `2`: Network LED (Blue, GPIO 14) — Illuminates when Wi-Fi and MQTT connections are active.
  - `3`: Sensor LED (Yellow, GPIO 12) — Flashes during active sensor bus transactions.
  - `4`: Fault LED (Red, GPIO 13) — Latches on when unacknowledged faults or errors occur.

#### `channel` (`int`, `HARDWARE_CHANNEL`)
- **Allowed Range:** `0 .. 7` (units: `channel_idx`)
- **Default:** `0`
- **Individual Value Meanings (`firmware/main/sensors/nexus_analog.c`):**
  - `0`: Channel X0 — HW-870 IR-1 Infrared Obstacle Reflection (GPIO 36 / ADC1_CH0).
  - `1`: Channel X1 — Hall Magnetic Sensor IC2 (Unmounted on EDU_ROBO V14; floating ADC noise ~17 counts).
  - `2`: Channel X2 — Sound / Microphone Sensor (Unmounted auxiliary input).
  - `3`: Channel X3 — Light Dependent Resistor LDR (Analog Light Intensity).
  - `4..7`: Channels X4..X7 — Auxiliary Analog Expansion 0..3 (Unused).

#### `job_id` (`int`, `NUMERIC_RANGE`)
- **Allowed Range:** `0 .. 15` (units: `index`)
- **Default:** `1`
- **Individual Value Meanings (`firmware/main/executive/nexus_executive.h`):**
  - `0`: Job 0 — Executive Core Supervisor (FreeRTOS scheduler tick & state management).
  - `1`: Job 1 — Telemetry Acquisition Engine (cyclic sensor sampling).
  - `2`: Job 2 — Serial Transport Processor (UART frame parsing and packet framing).
  - `3`: Job 3 — MQTT Network Client (publish telemetry and receive commands).
  - `4`: Job 4 — Health & Watchdog Monitor (periodic task checks).
  - `5`: Job 5 — Event Queue Dispatcher (event distribution and incident alerts).
  - `6`: Job 6 — Actuator Driver Service (LED, Buzzer, and Shift Register control).
  - `7`: Job 7 — Diagnostic & Self-Test Routine (periodic loopback checks).
  - `8..15`: Jobs 8–15 — Reserved Executive Slots for Expansion & Testing.

---

### 3.2 Discrete Enums & Options

#### `state` (`string`, `ENUM_OPTION`)
- **Allowed Values:** `on`, `off`
- **Default:** `on`
- **Meaning:** `on` asserts logic high (3.3V); `off` deasserts logic low (0.0V).

#### `priority` (`int`, `NUMERIC_RANGE`)
- **Allowed Values:** `1`, `2`, `3`
- **Default:** `2`
- **Meaning:**
  - `1`: High Priority Class — Critical safety tasks, watchdog monitoring, immediate actuator control.
  - `2`: Medium Priority Class — Default operational priority for sensor sampling and telemetry.
  - `3`: Low Priority Class — Background tasks, non-critical telemetry logging, deep maintenance.

#### `condition` (`string`, `ENUM_OPTION`)
- **Allowed Values:** `gt`, `lt`
- **Default:** `gt`
- **Meaning:** `gt` triggers when signal > threshold; `lt` triggers when signal < threshold.

#### `signal` (`string`, `TELEMETRY_FIELD`)
- **Allowed Values:** `temp`, `hum`, `ldr_raw`, `x0_raw`, `x1_raw`, `dist_cm`
- **Default:** `temp`
- **Meaning:**
  - `temp`: Ambient Temperature (°C) from DHT11 (0..50 °C).
  - `hum`: Relative Humidity (%) from DHT11 (20..90 %).
  - `ldr_raw`: Ambient Light from LDR on CD4051 X3 (0..4095 counts).
  - `x0_raw`: Infrared Reflection from HW-870 on CD4051 X0 (0..4095 counts).
  - `x1_raw`: Hall Sensor IC2 on CD4051 X1 (Unmounted; floating baseline ~17 counts).
  - `dist_cm`: Ultrasonic Distance from HC-SR04 (2..400 cm).

#### `transport` & `transport_id` (`string`, `ENUM_OPTION`)
- **Allowed Values:** `auto`, `serial`, `mqtt`
- **Default:** `auto` (or `serial` for transport commands)
- **Meaning:**
  - `auto`: Automatic Failover — Prefers USB Serial if connected, automatically falls back to MQTT.
  - `serial`: USB Serial Transport — Dedicated point-to-point /dev/ttyUSB0 link at 115200 baud.
  - `mqtt`: MQTT Network Transport — Mosquitto broker at localhost:1883 over topic nexus/cmd.

#### `key` (`string`, `CONFIG_KEY`)
- **Allowed Values:** `sample_rate`, `wifi_ssid`, `mqtt_broker`, `log_level`, `telemetry_interval`
- **Default:** `sample_rate`
- **Meaning:**
  - `sample_rate`: Sensor sampling cadence in milliseconds (50..60000 ms).
  - `wifi_ssid`: Configured station Wi-Fi network SSID string.
  - `mqtt_broker`: Hostname or IP address of the target Mosquitto MQTT broker.
  - `log_level`: Logging verbosity level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
  - `telemetry_interval`: Cyclic telemetry publishing interval in milliseconds (100..60000 ms).

#### `enabled` (`bool`, `BOOLEAN_FLAG`)
- **Allowed Values:** `true`, `false`
- **Default:** `true`
- **Meaning:** `true` enables sensor acquisition; `false` halts acquisition.

#### `format` (`string`, `ENUM_OPTION`)
- **Allowed Values:** `json`, `csv`
- **Default:** `json`
- **Meaning:** `json` produces structured JSON array; `csv` produces comma-delimited tabular rows.

---

### 3.3 Numeric Values, Units & Ranges

#### `duration_ms` (`int`, `TIME_DURATION_MS`)
- **Allowed Range:** `10 .. 5000` (units: `ms`, step: 10 ms)
- **Default:** `200`
- **Significance:** `50 ms` = acknowledgment chirp; `100 ms` = standard beep; `200 ms` = alert; `500 ms` = warning buzz; `1000..5000 ms` = extended alarm. Automatic safety cutoff enforced at 5000 ms.

#### `interval_ms` (`int`, `TIME_INTERVAL_MS`)
- **Allowed Range:** `50 .. 60000` (sensor sampling) or `100 .. 60000` (telemetry streaming)
- **Default:** `1000` (units: `ms`)
- **Significance:** `100 ms` = 10 Hz high-speed diagnostic stream; `1000 ms` = 1 Hz nominal operational cadence; `60000 ms` = 1 sample/min bandwidth-conserving rate.

#### `threshold` (`float`, `NUMERIC_LIMIT`)
- **Allowed Range:** `-40.0 .. 4095.0` (units depend on signal: `°C`, `%`, `counts`, `cm`)
- **Default:** `45.0`
- **Significance:** `45.0` for temperature (°C); `80.0` for humidity (%); `10.0` for ultrasonic distance (cm).

#### `value` (`int`, `BITMASK_BYTE`)
- **Allowed Range:** `0 .. 255` (units: `byte`)
- **Default:** `0`
- **Significance:** 8-bit output pattern shifted into 74HC595 shift register (`0` = all LOW, `1` = Q0 HIGH, `15` = lower nibble HIGH, `255` = all HIGH).

#### `offset`, `temp_offset`, `hum_offset` (`float`, `NUMERIC_OFFSET`)
- **Allowed Ranges:** `offset`: `-100.0 .. 100.0`; `temp_offset`: `-10.0 .. 10.0 °C`; `hum_offset`: `-20.0 .. 20.0 %`
- **Default:** `0.0`
- **Significance:** Additive calibration bias applied to raw sensor measurements.

#### `duration_sec` (`int`, `TIME_DURATION_S`)
- **Allowed Range:** `1 .. 30` (units: `s`)
- **Default:** `5`
- **Significance:** Executive queue stress test duration. Hard safety ceiling enforced at 30 seconds.

#### `limit` (`int`, `COUNT_LIMIT`)
- **Allowed Range:** `1 .. 1000` (units: `records`)
- **Default:** `100`

---

## 4. Authoritative Command Catalog (115 Commands)

Below is the complete inventory of all 115 registered commands across all 20 verbs, including command IDs, execution destinations, parameters, runnable examples, and expected responses:

### Verb 00: `NOP` (No Operation)
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0000` (0) | `NOP NONE` | FIRMWARE | Serial / MQTT | None | SAFE | Parser and protocol loopback test |
- **Example Request:** `{"verb": "NOP", "noun": "NONE", "params": {}}`
- **Expected Response:** `{"status": "ok", "code": 0, "msg": "NOP executed successfully", "ack": true}`

### Verb 01: `INITIALIZE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0101` (257) | `INITIALIZE SYSTEM` | FIRMWARE | Serial / MQTT | None | SAFE | Re-initialization requires restart (unsupported) |
| `0x0102` (258) | `INITIALIZE SENSORS` | FIRMWARE | Serial / MQTT | None | SAFE | Reinitialize physical sensor buses |
| `0x0103` (259) | `INITIALIZE TRANSPORTS` | FIRMWARE | Serial / MQTT | None | SAFE | Reinitialize UART and Wi-Fi/MQTT transports |
| `0x0104` (260) | `INITIALIZE EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Reinitialize executive task table (unsupported) |

### Verb 02: `START`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0201` (513) | `START SYSTEM` | FIRMWARE | Serial / MQTT | None | SAFE | Transition system to ACTIVE running state |
| `0x0202` (514) | `START SENSORS` | FIRMWARE | Serial / MQTT | None | SAFE | Start cyclic sensor sampling job |
| `0x0203` (515) | `START TELEMETRY` | FIRMWARE | Serial / MQTT | None | SAFE | Start publishing periodic telemetry stream |
| `0x0204` (516) | `START SELF_TEST` | FIRMWARE | Serial / MQTT | None | SAFE | Initiate built-in diagnostic self-test sequence |
| `0x0205` (517) | `START EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Start FreeRTOS executive dispatcher scheduler |

### Verb 03: `STOP`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0301` (769) | `STOP SYSTEM` | FIRMWARE | Serial / MQTT | None | SAFE | Transition system to STANDBY quiescent state |
| `0x0302` (770) | `STOP SENSORS` | FIRMWARE | Serial / MQTT | None | SAFE | Suspend cyclic sensor sampling job |
| `0x0303` (771) | `STOP TELEMETRY` | FIRMWARE | Serial / MQTT | None | SAFE | Halt periodic telemetry transmission |
| `0x0304` (772) | `STOP EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Stop executive dispatcher (unsupported) |

### Verb 04: `RESET`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0401` (1025) | `RESET FAULTS` | FIRMWARE | Serial / MQTT | None | HAZARDOUS | Clear latching fault flags and incident counters |
| `0x0402` (1026) | `RESET STATISTICS` | FIRMWARE | Serial / MQTT | None | HAZARDOUS | Reset telemetry packet and dispatch statistics |
| `0x0403` (1027) | `RESET SENSOR_STATE` | FIRMWARE | Serial / MQTT | None | SAFE | Reset sensor calibration baselines and filter state |
| `0x0404` (1028) | `RESET QUEUES` | FIRMWARE | Serial / MQTT | None | HAZARDOUS | Flush event and telemetry ring buffers |
| `0x0405` (1029) | `RESET TRANSPORTS` | FIRMWARE | Serial / MQTT | None | SAFE | Reset serial and network transport state machines |

### Verb 05: `SET`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0501` (1281) | `SET PRIORITY` | FIRMWARE | Serial / MQTT | `job_id` (0..15), `priority` (1..3) | SAFE | Configure executive job priority level |
| `0x0502` (1282) | `SET SAMPLE_INTERVAL` | FIRMWARE | Serial / MQTT | `sensor_id`, `interval_ms` (50..60000) | SAFE | Configure sensor sampling cadence |
| `0x0503` (1283) | `SET THRESHOLD` | GROUND_STATION | Local / HTTP | `signal`, `threshold`, `condition` | SAFE | Configure signal alert threshold setpoint |
| `0x0504` (1284) | `SET SENSOR_ENABLE` | FIRMWARE | Serial / MQTT | `sensor_id`, `enabled` (bool) | SAFE | Enable or disable specific sensor sampling |
| `0x0505` (1285) | `SET TRANSPORT_PREFERENCE` | GROUND_STATION | Local / HTTP | `transport` (`auto`/`serial`/`mqtt`) | SAFE | Set active transport routing preference |
| `0x0506` (1286) | `SET CONFIGURATION` | GROUND_STATION | Local / HTTP | `key`, `value` | SAFE | Set non-volatile configuration key-value pair |

### Verb 06: `GET`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0601` (1537) | `GET STATUS` | FIRMWARE | Serial / MQTT | None | SAFE | Return executive state, uptime, and free heap |
| `0x0602` (1538) | `GET CONFIGURATION` | FIRMWARE | Serial / MQTT | None | SAFE | Query active configuration key-value settings |
| `0x0603` (1539) | `GET SENSOR_LIST` | FIRMWARE | Serial / MQTT | None | SAFE | Return list of supported and enabled sensor IDs |
| `0x0604` (1540) | `GET TIME` | FIRMWARE | Serial / MQTT | None | SAFE | Return system uptime in milliseconds |
| `0x0605` (1541) | `GET TELEMETRY` | FIRMWARE | Serial / MQTT | None | SAFE | Capture instantaneous telemetry snapshot |
| `0x0606` (1542) | `GET FAULT_LIST` | FIRMWARE | Serial / MQTT | None | SAFE | Return active latching fault bitmask |
| `0x0607` (1543) | `GET QUEUE_STATUS` | FIRMWARE | Serial / MQTT | None | SAFE | Return queue occupancy counts |
| `0x0608` (1544) | `GET TRANSPORT_STATUS`| FIRMWARE | Serial / MQTT | None | SAFE | Return connection health for serial and MQTT |
| `0x0609` (1545) | `GET VERSION` | FIRMWARE | Serial / MQTT | None | SAFE | Return firmware semantic version and build date |
| `0x060A` (1546) | `GET CAPABILITIES` | FIRMWARE | Serial / MQTT | None | SAFE | Return hardware peripheral capability bitmask |

### Verb 07: `ENABLE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0701` (1793) | `ENABLE SENSOR` | FIRMWARE | Serial / MQTT | `sensor_id` | SAFE | Enable acquisition for target sensor |
| `0x0702` (1794) | `ENABLE TRANSPORT` | FIRMWARE | Serial / MQTT | `transport_id` (`serial`/`mqtt`) | SAFE | Enable transport communication interface |
| `0x0703` (1795) | `ENABLE TELEMETRY` | FIRMWARE | Serial / MQTT | `interval_ms` (100..60000) | SAFE | Enable cyclic telemetry streaming |
| `0x0704` (1796) | `ENABLE DIAGNOSTICS` | FIRMWARE | Serial / MQTT | None | SAFE | Enable verbose diagnostic logging |

### Verb 08: `DISABLE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0801` (2049) | `DISABLE SENSOR` | FIRMWARE | Serial / MQTT | `sensor_id` | SAFE | Disable acquisition for target sensor |
| `0x0802` (2050) | `DISABLE TRANSPORT` | FIRMWARE | Serial / MQTT | `transport_id` (`serial`/`mqtt`) | SAFE | Disable transport communication interface |
| `0x0803` (2051) | `DISABLE TELEMETRY` | FIRMWARE | Serial / MQTT | None | SAFE | Suspend cyclic telemetry streaming |
| `0x0804` (2052) | `DISABLE DIAGNOSTICS`| FIRMWARE | Serial / MQTT | None | SAFE | Silence verbose diagnostic logging |

### Verb 09: `CALIBRATE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0901` (2305) | `CALIBRATE SENSOR` | FIRMWARE | Serial / MQTT | `sensor_id`, `offset` (-100..100) | SAFE | Apply zero/span offset bias to sensor |
| `0x0902` (2306) | `CALIBRATE ANALOG` | FIRMWARE | Serial / MQTT | `channel` (0..7) | SAFE | Calibrate CD4051 analog multiplexer channel |
| `0x0903` (2307) | `CALIBRATE ENVIRONMENT`| FIRMWARE | Serial / MQTT | `temp_offset`, `hum_offset` | SAFE | Calibrate temperature and humidity bias |
| `0x0904` (2308) | `CALIBRATE TOUCH` | FIRMWARE | Serial / MQTT | None | UNMOUNTED | Calibrate touch sensor (unmounted) |

### Verb 0A: `ACKNOWLEDGE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0A01` (2561) | `ACKNOWLEDGE FAULT` | FIRMWARE | Serial / MQTT | `fault_id` (1..15, default 1) | SAFE | Acknowledge active fault without clearing latch |
| `0x0A02` (2562) | `ACKNOWLEDGE WARNING`| FIRMWARE | Serial / MQTT | `warning_id` (1..15, default 2) | SAFE | Acknowledge telemetry warning alert |
| `0x0A03` (2563) | `ACKNOWLEDGE EVENT` | FIRMWARE | Serial / MQTT | `event_id` (1..11, default 1) | SAFE | Acknowledge firmware event type or sequence ID |
- **Example Request:** `{"verb": "ACKNOWLEDGE", "noun": "EVENT", "params": {"event_id": 1}}`
- **Expected Response:** `{"status": "ok", "code": 0, "msg": "Event acknowledged", "ack": true}`

### Verb 0B: `CLEAR`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0B01` (2817) | `CLEAR FAULTS` | FIRMWARE | Serial / MQTT | None | HAZARDOUS | Clear latching hardware fault flags |
| `0x0B02` (2818) | `CLEAR HISTORY` | FIRMWARE | Serial / MQTT | None | HAZARDOUS | Clear historical telemetry logs |
| `0x0B03` (2819) | `CLEAR STATISTICS` | FIRMWARE | Serial / MQTT | None | HAZARDOUS | Reset dispatch and telemetry counters |

### Verb 0C: `TEST`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0C01` (3073) | `TEST SENSOR` | FIRMWARE | Serial / MQTT | `sensor_id` | SAFE | Execute single diagnostic sensor read |
| `0x0C02` (3074) | `TEST TRANSPORT` | FIRMWARE | Serial / MQTT | `transport_id` (`serial`/`mqtt`) | SAFE | Execute loopback echo ping test |
| `0x0C03` (3075) | `TEST EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Verify executive scheduler responsiveness |
| `0x0C04` (3076) | `TEST PERIPHERAL` | FIRMWARE | Serial / MQTT | None | SAFE | Test onboard peripheral interfaces |

### Verb 0D: `ACTUATE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0D01` (3329) | `ACTUATE RELAY` | FIRMWARE | Serial / MQTT | None | UNMOUNTED | Control Relay K1 (unmounted on board) |
| `0x0D02` (3330) | `ACTUATE LED` | FIRMWARE | Serial / MQTT | `led_id` (1..4), `state` (`on`/`off`)| SAFE | Control Diagnostic Status LEDs 1–4 |
| `0x0D03` (3331) | `ACTUATE MOTOR` | FIRMWARE | Serial / MQTT | None | UNMOUNTED | Control DC motor driver (unmounted) |
| `0x0D04` (3332) | `ACTUATE SERVO` | FIRMWARE | Serial / MQTT | None | UNMOUNTED | Control Servo motor PWM (unmounted) |
| `0x0D05` (3333) | `ACTUATE BUZZER` | FIRMWARE | Serial / MQTT | `duration_ms` (10..5000, default 200)| SAFE | Emit audible alert beep on Active Buzzer |
| `0x0D06` (3334) | `ACTUATE SHIFT_REGISTER`| FIRMWARE | Serial / MQTT | `value` (0..255, default 0) | SAFE | Shift 8-bit pattern into 74HC595 register |

### Verb 0E: `CAPTURE`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0E01` (3585) | `CAPTURE TELEMETRY` | FIRMWARE | Serial / MQTT | None | SAFE | Capture synchronous telemetry snapshot |
| `0x0E02` (3586) | `CAPTURE SENSOR_SNAPSHOT`| FIRMWARE | Serial / MQTT | None | SAFE | Capture raw ADC readings across all channels |
| `0x0E03` (3587) | `CAPTURE EVENT_SNAPSHOT` | FIRMWARE | Serial / MQTT | None | SAFE | Snapshot current event queue contents |

### Verb 0F: `PUBLISH`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x0F01` (3841) | `PUBLISH TELEMETRY` | FIRMWARE | Serial / MQTT | None | SAFE | Force immediate telemetry publish frame |
| `0x0F02` (3842) | `PUBLISH EVENT` | FIRMWARE | Serial / MQTT | `event_name` | SAFE | Broadcast named operational event |
| `0x0F03` (3843) | `PUBLISH STATUS` | FIRMWARE | Serial / MQTT | None | SAFE | Publish executive status broadcast frame |

### Verb 10: `DISPLAY`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x1001` (4097) | `DISPLAY STATUS` | FIRMWARE | Serial / MQTT | None | SAFE | Format human-readable executive status |
| `0x1002` (4098) | `DISPLAY EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Print executive task table and CPU utilization |
| `0x1003` (4099) | `DISPLAY QUEUES` | FIRMWARE | Serial / MQTT | None | SAFE | Print event queue occupancy and drops |
| `0x1004` (4100) | `DISPLAY FAULTS` | FIRMWARE | Serial / MQTT | None | SAFE | Print active fault list and error counters |
| `0x1005` (4101) | `DISPLAY SENSORS` | FIRMWARE | Serial / MQTT | None | SAFE | Print sensor status and recent readings |
| `0x1006` (4102) | `DISPLAY TRANSPORTS` | FIRMWARE | Serial / MQTT | None | SAFE | Print UART and MQTT connection metrics |
| `0x1007` (4103) | `DISPLAY CONFIGURATION`| FIRMWARE | Serial / MQTT | None | SAFE | Print active configuration parameters |
| `0x1041` (4161) | `DISPLAY ENVIRONMENT` | FIRMWARE | Serial / MQTT | None | SAFE | Print temperature, humidity, and light readings |
| `0x1042` (4162) | `DISPLAY LIGHT` | FIRMWARE | Serial / MQTT | None | SAFE | Print ambient light level (LDR ADC counts) |
| `0x1043` (4163) | `DISPLAY DISTANCE` | FIRMWARE | Serial / MQTT | None | SAFE | Print HC-SR04 ultrasonic distance (cm) |
| `0x1044` (4164) | `DISPLAY ANALOG` | FIRMWARE | Serial / MQTT | None | SAFE | Print all 8 CD4051 analog channel counts |
| `0x1045` (4165) | `DISPLAY MOTION` | FIRMWARE | Serial / MQTT | None | SAFE | Print MOC7811 optical slot status |
| `0x1046` (4166) | `DISPLAY EVENTS` | FIRMWARE | Serial / MQTT | None | SAFE | Print recent event log entries |
| `0x1047` (4167) | `DISPLAY ACTUATORS` | FIRMWARE | Serial / MQTT | None | SAFE | Print LED, Buzzer, and Shift Register states |
| `0x1048` (4168) | `DISPLAY CONNECTIVITY` | FIRMWARE | Serial / MQTT | None | SAFE | Print IP address, Wi-Fi RSSI, and MQTT status |

### Verb 11: `HISTORY`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x1101` (4353) | `HISTORY EVENTS` | FIRMWARE | Serial / MQTT | None | SAFE | Retrieve circular event history buffer |
| `0x1102` (4354) | `HISTORY FAULTS` | FIRMWARE | Serial / MQTT | None | SAFE | Retrieve historical fault log records |
| `0x1103` (4355) | `HISTORY EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Retrieve executive dispatch history |
| `0x1104` (4356) | `HISTORY SENSORS` | FIRMWARE | Serial / MQTT | None | SAFE | Retrieve historical sensor averages |
| `0x1105` (4357) | `HISTORY TRANSPORTS` | FIRMWARE | Serial / MQTT | None | SAFE | Retrieve transport reconnect history |
| `0x1141` (4417) | `HISTORY ENVIRONMENT` | FIRMWARE | Serial / MQTT | None | SAFE | Retrieve environmental reading trends |
| `0x1142` (4418) | `HISTORY SENSOR_READINGS`| FIRMWARE | Serial / MQTT | None | SAFE | Retrieve raw sensor reading history |

### Verb 18: `DIAGNOSTICS`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x1801` (6145) | `DIAGNOSTICS SYSTEM` | FIRMWARE | Serial / MQTT | None | SAFE | Comprehensive system diagnostics report |
| `0x1802` (6146) | `DIAGNOSTICS SENSORS` | FIRMWARE | Serial / MQTT | None | SAFE | Sensor health, noise variance, and checksums |
| `0x1803` (6147) | `DIAGNOSTICS QUEUES` | FIRMWARE | Serial / MQTT | None | SAFE | Queue high-water marks and drop telemetry |
| `0x1804` (6148) | `DIAGNOSTICS TIMING` | FIRMWARE | Serial / MQTT | None | SAFE | Executive jitter and task execution timing |
| `0x1805` (6149) | `DIAGNOSTICS MEMORY` | FIRMWARE | Serial / MQTT | None | SAFE | Free heap, minimum ever heap, and stack metrics |
| `0x1806` (6150) | `DIAGNOSTICS TRANSPORTS`| FIRMWARE | Serial / MQTT | None | SAFE | Transport packet counters and error rates |
| `0x1807` (6151) | `DIAGNOSTICS EXECUTIVE` | FIRMWARE | Serial / MQTT | None | SAFE | Executive task scheduling and deadline misses |
| `0x1808` (6152) | `DIAGNOSTICS PERIPHERALS`| FIRMWARE | Serial / MQTT | None | SAFE | Hardware peripheral bus scan results |
| `0x1809` (6153) | `DIAGNOSTICS DATABASE` | GROUND_STATION | Local / HTTP | None | SAFE | Verify InfluxDB connectivity and query latency |
| `0x180A` (6154) | `DIAGNOSTICS AI_SERVICE` | GROUND_STATION | Local / HTTP | None | SAFE | Verify Open WebUI and Ollama reachability |

### Verb 1E: `OPEN`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x1E01` (7681) | `OPEN DASHBOARD` | GROUND_STATION | Local / HTTP | None | SAFE | Open Grafana Telemetry & Device Health dashboard |
| `0x1E02` (7682) | `OPEN LOGS` | GROUND_STATION | Local / HTTP | None | SAFE | Open system service logs viewer |
| `0x1E03` (7683) | `OPEN AI` | GROUND_STATION | Local / HTTP | None | SAFE | Open Open WebUI Conversational Assistant interface |
| `0x1E04` (7684) | `OPEN GROUND` | GROUND_STATION | Local / HTTP | None | SAFE | Open Mission Control primary operations console |
| `0x1E05` (7685) | `OPEN DATABASE` | GROUND_STATION | Local / HTTP | None | SAFE | Open InfluxDB web data explorer |
| `0x1E06` (7686) | `OPEN DIAGNOSTICS` | GROUND_STATION | Local / HTTP | None | SAFE | Open Mission Services & Diagnostics panel |

### Verb 1F: `ASK`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x1F01` (7937) | `ASK SYSTEM` | GROUND_STATION | Local / HTTP | `question` | SAFE | Query AI regarding system health, uptime, or memory |
| `0x1F02` (7938) | `ASK SENSOR` | GROUND_STATION | Local / HTTP | `sensor_id`, `question` | SAFE | Query AI regarding sensor trends, statistics, or peaks |
| `0x1F03` (7939) | `ASK EXECUTIVE` | GROUND_STATION | Local / HTTP | `question` | SAFE | Query AI regarding scheduler load and task deadlines |
| `0x1F04` (7940) | `ASK DIAGNOSTICS` | GROUND_STATION | Local / HTTP | `question` | SAFE | Query AI to analyze incident logs and root causes |
| `0x1F41` (8001) | `ASK ENVIRONMENT` | GROUND_STATION | Local / HTTP | `question` | SAFE | Query AI to evaluate environmental safety thresholds |
- **Example Request:** `{"verb": "ASK", "noun": "SENSOR", "params": {"sensor_id": "hcsr04", "question": "max recorded distance to date"}}`
- **Expected Response:** `{"status": "completed", "code": 0, "msg": "AI service response for SENSOR", "data": {"reply": "...90.0 cm..."}, "_execution_path": "HOST_LOCAL_OPERATION", "device_wire_envelope": "NOT_APPLICABLE"}`

### Verb 20: `EXPORT`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x2001` (8193) | `EXPORT TELEMETRY` | GROUND_STATION | Local / HTTP | `format` (`json`/`csv`), `limit` | SAFE | Export historical telemetry records batch |
| `0x2002` (8194) | `EXPORT DIAGNOSTICS` | GROUND_STATION | Local / HTTP | `format` (`json`/`csv`) | SAFE | Export diagnostic snapshot |
| `0x2003` (8195) | `EXPORT EVENTS` | GROUND_STATION | Local / HTTP | `format` (`json`/`csv`), `limit` | SAFE | Export incident event log entries |
| `0x2004` (8196) | `EXPORT FAULTS` | GROUND_STATION | Local / HTTP | `format` (`json`/`csv`), `limit` | SAFE | Export fault history log records |
| `0x2005` (8197) | `EXPORT CONFIGURATION`| GROUND_STATION | Local / HTTP | `format` (`json`) | SAFE | Export configuration key-value store |

### Verb 21: `RUN`
| ID | Verb Noun | Target | Transports | Parameters | Safety | Description |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `0x2101` (8449) | `RUN SELF_TEST` | FIRMWARE | Serial / MQTT | None | SAFE | Run automated diagnostic self-test sequence |
| `0x2102` (8450) | `RUN SENSOR_TEST` | FIRMWARE | Serial / MQTT | None | SAFE | Run sequential diagnostic scan across all sensors |
| `0x2103` (8451) | `RUN STRESS_TEST` | FIRMWARE | Serial / MQTT | `duration_sec` (1..30) | HAZARDOUS | Run executive message queue stress test |
| `0x2104` (8452) | `RUN TRANSPORT_TEST` | FIRMWARE | Serial / MQTT | `transport_id` (`serial`/`mqtt`) | SAFE | Run transport throughput and latency benchmark |
| `0x2105` (8453) | `RUN QUALIFICATION_TEST`| FIRMWARE | Serial / MQTT | None | HAZARDOUS | Run comprehensive milestone qualification suite |

---

## 5. Runtime Entity Discovery & Incident Lifecycle

### 5.1 Active Incident Discovery (`GET /api/incidents`)
Operators can query live active incidents using the Ground Station incident discovery endpoint:
```bash
curl -s http://127.0.0.1:8000/api/incidents | jq .
```
Response:
```json
{
  "status": "ok",
  "active_incidents": [
    {
      "incident_id": "INC-20261025-001",
      "rule_id": "DIST_COLLISION_ALERT",
      "severity": "WARNING",
      "signal": "dist_cm",
      "current_value": 8.5,
      "threshold": 10.0,
      "state": "ACTIVE",
      "created_at": "2026-10-25T11:20:00Z"
    }
  ],
  "event_types": {
    "1": "BOOT_START", "2": "BOOT_COMPLETE", "3": "HEARTBEAT", "4": "WIFI_CONNECTED",
    "5": "MQTT_CONNECTED", "6": "TELEMETRY_SAMPLE", "7": "THRESHOLD_EXCEEDED",
    "8": "COMMAND_RECEIVED", "9": "COMMAND_EXECUTED", "10": "ERROR_RAISED", "11": "WATCHDOG_RESET"
  }
}
```

### 5.2 Acknowledging vs Clearing Incidents
- **`ACKNOWLEDGE EVENT / FAULT / WARNING`:** Flags the incident as acknowledged by Mission Control. The underlying physical sensor telemetry or fault condition remains monitored.
- **`CLEAR FAULTS`:** Resets the cumulative fault statistics (`jobs_failed = 0`) in the FreeRTOS executive. Requires confirmation gating (`"confirmed": true`).

---

## 6. Protocol Status Codes

The NEXUS command protocol enforces explicit status codes across firmware and ground station:

| Code | Status String | Definition & Handling |
| :---: | :--- | :--- |
| **0** | `OK` / `completed` | Command executed successfully; results returned. |
| **1** | `REJECTED` | Parameter validation failed; missing required argument or out-of-range value. |
| **2** | `UNKNOWN_CMD` | Verb or Noun code not recognized in canonical registry. |
| **3** | `UNSUPPORTED` | Command recognized but peripheral is unmounted on EDU_ROBO V14. |
| **4** | `FAILED` | Internal execution failure during handler execution. |
| **5** | `DUPLICATE` | Repeated command sequence number dropped by idempotent filter. |
| **6** | `TIMEOUT` | Target failed to acknowledge or reply within timeout deadline (default 2.0s). |
| **7** | `CONFIRMATION_REQUIRED` | Hazardous operation submitted without `"confirmed": true` safety flag. |
| **8** | `TARGET_UNREACHABLE` | Selected transport path is offline or disconnected. |
| **9** | `INTERNAL_ERROR` | Transport parsing error or unhandled runtime exception. |

---

## 7. Cross-References & Source of Truth

- **Command Registry Authority:** [`ground_station/command_router/command_registry.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/command_router/command_registry.py)
- **Firmware Dispatcher Authority:** [`firmware/main/command/nexus_command_dispatcher.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_dispatcher.c)
- **Hardware Pin Map & Schematics:** [`docs/SPEC_SHEET.md`](file:///home/aryan/Projects/SPIT/NEXUS/docs/SPEC_SHEET.md)
- **Project Blueprint:** [`docs/PROJECT_BLUEPRINT.md`](file:///home/aryan/Projects/SPIT/NEXUS/docs/PROJECT_BLUEPRINT.md)
- **Qualification & Closure Report:** [`docs/validation/system_qualification_and_closure_report_20261025.md`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/system_qualification_and_closure_report_20261025.md)
