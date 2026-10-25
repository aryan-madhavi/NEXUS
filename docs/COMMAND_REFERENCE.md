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
      └─► MQTT Broker (nexus/<dev>/cmd)├─► AI Conversational Agent (Ollama mistral:7b)
                                       ├─► Application Launchers (Dashboard, Grafana)
                                       └─► Data Exporters (JSON / CSV)
```

1. **Firmware Device Dispatch (`FIRMWARE_DEVICE_DISPATCH`):**
   - **Target:** 97 commands targeting the ESP32.
   - **Transports:** Transmitted across physical transports to the ESP32 (USB Serial `/dev/ttyUSB0` at 115200 baud 8N1 or Mosquitto MQTT topic `nexus/nexus_esp32/cmd` at QoS 1).
   - **Processing:** Processed by the zero-allocation C Command Dispatcher (`firmware/main/command/nexus_command_dispatcher.c`).
   - **Response Routing:** Response envelopes (`"type": "resp"`) are emitted symmetrically on the originating transport (Serial `stdout` for Serial RX; MQTT `nexus/nexus_esp32/telemetry` for MQTT RX). *Note: There is no separate `nexus/resp` topic; all outbound frames from the device publish to `<prefix>/telemetry`.*
2. **Host-Local Operations (`HOST_LOCAL_OPERATION`):**
   - **Target:** 18 commands executed entirely within the Ground Station host process (Python runtime).
   - **Subsystems:** Encompasses `OPEN` application launchers (`0x1E01..0x1E06`), `EXPORT` data generation (`0x2001..0x2005`), `DIAGNOSTICS DATABASE/AI_SERVICE` (`0x1809..0x180A`), and `ASK` conversational AI queries (`0x1F01..0x1F04, 0x1F41`).
   - **Device Wire Envelope:** Explicitly tagged **`NOT_APPLICABLE`**. No packets are transmitted over Serial or MQTT to the ESP32.

### 1.2 Protocol Wire Envelopes (Protocol v1)

The wire protocol is strictly newline-delimited single-line UTF-8 JSON (`"ver": 1`) with a strict `< 256`-byte ceiling (`NEXUS_ENVELOPE_MAX_LEN = 256`, max 255 payload bytes). Binary framing and CBOR are **not** implemented.

#### A. Inbound Command Frame (`cmd`)
```json
{"ver":1,"dev":"nexus_esp32","seq":42,"type":"cmd","cmd_id":1537,"verb":"GET","noun":"STATUS"}
```

#### B. Outbound Response Frame (`resp`)
```json
{"ver":1,"dev":"nexus_esp32","seq":42,"type":"resp","cmd_id":1537,"verb":"GET","noun":"STATUS","status":"completed","code":0,"msg":"Status retrieved","uptime":53455,"free_heap":193640,"exec_ok":true}
```

---

## 2. Command Execution Model & Safety Classifications

All 115 registered commands in [`ground_station/command_router/command_registry.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/command_router/command_registry.py) are classified into five operational safety categories:

| Classification | Count | Execution Policy | Rejection / Safety Enforcement |
| :--- | :---: | :--- | :--- |
| **SAFE_CONTROL** | 53 | Parameter validation, immediate execution on device/host. | Valid arguments accepted; returns `StatusCode.OK (0)`. |
| **READ_ONLY** | 41 | Sensor sampling, telemetry query, diagnostics inspection. | Non-destructive; returns telemetry payload; `StatusCode.OK (0)`. |
| **UNMOUNTED_HARDWARE** | 10 | Commands targeting peripherals unpopulated on EDU_ROBO V14. | Truthfully rejected with `StatusCode.UNSUPPORTED (3)`. |
| **HAZARDOUS_DESTRUCTIVE** | 9 | System reset, fault clear, queue clear, stress tests. | Rejects unconfirmed requests with `StatusCode.CONFIRMATION_REQUIRED (7)`. Requires `"confirmed": true`. |
| **PHYSICAL_ACTUATOR** | 2 | Diagnostic control of Status LEDs (1–4) and Active Buzzer. | Safe pulse limits enforced (`ACTUATE BUZZER` max 5000 ms, `GPIO 22 = 0` motor lock). |


### 2.1 Reality of Command Execution Tiers (Advertised vs Physically Executed)

To avoid ambiguity between what is declared in the protocol catalog versus what the physical firmware hardware performs, NEXUS defines six distinct tiers of command reality:

1. **Advertised in Registry (115 Commands):** All 115 commands defined in Python `CommandRegistry` across 23 verbs.
2. **Ground Station Local Operations (18 Commands):** Commands processed entirely by Python `CommandRouter` (e.g. `OPEN DASHBOARD`, `EXPORT CSV`, `ASK TELEMETRY`). No wire frame is transmitted to firmware.
3. **Firmware Dispatched & Handled (97 Commands):** Received by firmware `nexus_cmd_dispatcher.c` across 97 C `case` statements.
   - **Physically Executed / Live Hardware (42 Commands):** Read real ADC/GPIO, toggle real LEDs/Buzzer, or mutate live FreeRTOS cyclic executive state (e.g., `GET TELEMETRY`, `ACTUATE LED_1`, `ACTUATE BUZZER`, `START SENSORS`, `SET PRIORITY`).
   - **Simulated / Protocol-Success Acks (45 Commands):** Validated and acknowledged with `code 0 (OK)` by firmware, but target actuators or peripherals that are software-simulated or lack physical drivers (e.g. `74HC595` shift register commands, mock relay toggles).
   - **Truthfully Unsupported (10 Commands):** Target hardware peripherals unpopulated or blocked on EDU_ROBO V14 (e.g. `INITIALIZE SYSTEM`, `INITIALIZE TRANSPORTS`, `INITIALIZE EXECUTIVE`). Explicitly return `code 3 (UNSUPPORTED)`.

### Hazardous Command Confirmation Flow
The 9 hazardous commands (`RESET FAULTS`, `RESET STATISTICS`, `RESET SENSOR_STATE`, `RESET QUEUES`, `CLEAR FAULTS`, `CLEAR HISTORY`, `CLEAR STATISTICS`, `RUN STRESS_TEST`, `RUN QUALIFICATION_TEST`) require explicit two-stage confirmation. If submitted with `confirmed=false`, `CommandRouter.dispatch_command()` halts execution before sending any wire frame, returning `code=7 (CONFIRMATION_REQUIRED)`:
```json
{"status": "confirmation_required", "code": 7, "msg": "Hazardous command requires explicit confirmation: RESET FAULTS"}
```
Mission Control displays a confirmation modal requiring the operator to check a safety acknowledgement box before re-submitting with `confirmed: true`.

---

## 3. Master Parameter Dictionary (27 Parameters)

The following dictionary defines every parameter key, its value semantics, allowed values, units, defaults, and individual value meanings across the 115 commands:

### 3.1 Identifiers & Hardware Channels

#### `sensor_id` (`select`, `SENSOR_IDENTIFIER`)
- **Allowed Values:** `ldr`, `cd4051`, `dht11`, `moc7811`, `hcsr04`
- **Default:** `dht11`
- **Individual Mappings:**
  - `ldr`: Light Dependent Resistor — Ambient light intensity on dedicated ADC pin `GPIO 35` (`ADC1_CH7`, raw counts 0–4095).
  - `cd4051`: CD4051 Analog Multiplexer — 8:1 analog input bus (`GPIO 4, 2, 5` select -> `GPIO 36` `ADC1_CH0`).
  - `dht11`: DHT11 Digital Sensor — Relative humidity (%) and temperature (°C) on 1-wire pin `GPIO 19`.
  - `moc7811`: MOC7811 Slotted Optical Switch — Digital beam status (0=clear, 1=blocked) on `GPIO 34`.
  - `hcsr04`: HC-SR04 Ultrasonic Sensor — Distance (cm) via Trigger (`GPIO 25`) and Echo (`GPIO 26`).
- **Discovery Workflow:** Query mounted sensors via `GET /api/sensors` or `GET SENSOR_LIST`.

#### `event_id` (`int`, `EVENT_IDENTIFIER`)
- **Allowed Range:** `1 .. 11` (units: `event_type_or_seq`)
- **Default:** `1`
- **Omission / Null:** Optional. If omitted, defaults to 1. Handled by firmware dispatcher.
- **Individual Value Meanings (`firmware/main/data_structures/nexus_event_queue.h`):**
  - `1`: `SYSTEM_BOOT` — FreeRTOS system bootloader execution commenced and self-tests ran.
  - `2`: `JOB_REGISTERED` — New periodic job registered in executive job table.
  - `3`: `JOB_FAILED` — Periodic job callback returned failure status.
  - `4`: `DEADLINE_MISS` — Job callback execution duration exceeded allocated budget.
  - `5`: `QUEUE_OVERFLOW` — Ready queue capacity saturated; newest item rejected.
  - `6`: `SENSOR_DEGRADED` — Sensor reported checksum failure, timeout, or invalid sample.
  - `7`: `SENSOR_RECOVERED` — Sensor restored valid acquisition after transient fault.
  - `8`: `TRANSPORT_ONLINE` — Transport interface entered connected state.
  - `9`: `TRANSPORT_OFFLINE` — Transport interface degraded or disconnected.
  - `10`: `CONFIG_CHANGED` — Runtime configuration parameter modified.
  - `11`: `COMMAND_COMPLETED` — Dispatched command executed to completion.
- **Discovery Workflow:** Query event types via `DISPLAY QUEUES` or active alerts via `GET /api/incidents`.

#### `fault_id` (`int`, `FAULT_IDENTIFIER`)
- **Allowed Range:** `1 .. 15` (units: `code_or_id`)
- **Default:** `1`
- **Individual Value Meanings:**
  - `1`: `SENSOR_READ_FAIL` — ADC or 1-wire sensor read timed out or failed checksum.
  - `2`: `TELEMETRY_OVERFLOW` — Telemetry queue capacity exhausted; frame dropped.
  - `3`: `QUEUE_FULL` — Inter-task ready queue saturated; dispatch delayed.
  - `4`: `MQTT_DISCONNECT` — Broker connection severed or TCP socket keepalive timed out.
  - `5`: `HEAP_LOW` — FreeRTOS heap dropped below safety margin (< 50 KB).
  - `6`: `DEADLINE_OVERRUN` — Cyclic task callback exceeded allocated deadline budget.
- **Discovery Workflow:** Query active faults via `DISPLAY FAULTS` or `GET /api/incidents`.

#### `warning_id` (`int`, `WARNING_IDENTIFIER`)
- **Allowed Range:** `1 .. 15` (units: `code_or_id`)
- **Default:** `2`
- **Individual Value Meanings:**
  - `1`: `TEMP_HIGH` — Ambient temperature exceeded warning threshold (> 45°C).
  - `2`: `STALE_TELEMETRY` — Telemetry arrival age exceeded expected cadence * grace factor (> 6.0s).
  - `3`: `RANGE_EXCEEDED` — HC-SR04 ultrasonic distance reading out of nominal range (< 2 cm or > 400 cm).
  - `4`: `HUMIDITY_HIGH` — Relative humidity exceeded condensation risk threshold (> 85%).
  - `5`: `DEADLINE_MISS` — Executive callback duration exceeded budget.
  - `6`: `LIGHT_LOW` — Ambient illumination dropped below minimum operating counts (< 50).
- **Discovery Workflow:** Query active warnings via `GET /api/incidents` or `DISPLAY FAULTS`.

#### `led_id` (`int`, `HARDWARE_CHANNEL`)
- **Allowed Range:** `1 .. 4` (units: `channel`)
- **Default:** `1`
- **Individual Value Meanings (`firmware/main/command/nexus_command_dispatcher.c:73`):**
  - `1`: Diagnostic LED 1 — Green LED on `GPIO 27` (shared with L293D 1A).
  - `2`: Diagnostic LED 2 — Blue LED on `GPIO 14` (shared with L293D 2A).
  - `3`: Diagnostic LED 3 — Yellow LED on `GPIO 12` (shared with L293D 3A; strapping MTDI).
  - `4`: Diagnostic LED 4 — Red LED on `GPIO 13` (shared with L293D 4A).

#### `channel` (`int`, `MUX_CHANNEL_INDEX`)
- **Allowed Range:** `0 .. 7` (units: `channel_idx`)
- **Default:** `0`
- **Individual Value Meanings (`firmware/main/sensors/nexus_cd4051.c`):**
  - `0`: Channel X0 — HW-870 IR-1 Infrared Obstacle Reflection (GPIO 36 / ADC1_CH0).
  - `1`: Channel X1 — Hall Magnetic Sensor IC2 footprint (Unpopulated on PCB; floating mux noise).
  - `2`: Channel X2 — Soil Moisture Header (Unmounted).
  - `3`: Channel X3 — Rain Drop Sensor Header (Unmounted).
  - `4..6`: Channels X4..X6 — Line Follower IR Left/Center/Right Headers (Unmounted).
  - `7`: Channel X7 — Potentiometer RV1 footprint (Unpopulated on board).

#### `job_id` (`int`, `JOB_INDEX`)
- **Allowed Range:** `0 .. 15` (units: `index`)
- **Default:** `1`
- **Individual Value Meanings (`firmware/main/app_main.c:223-248`, `firmware/main/sensors/nexus_sensors.c:108-146`):**
  - `1`: `heartbeat` — Critical cyclic executive heartbeat (Class 0, 1000 ms, deadline 20 ms).
  - `2`: `metrics` — Executive dispatch statistics and degraded sensor logging (Class 2, 5000 ms, deadline 50 ms).
  - `3`: `conn_telem` — Comprehensive sensor telemetry streaming (Class 2, 2000 ms, deadline 20 ms).
  - `4`: `ldr_acq` — LDR ambient light ADC sampling on GPIO 35 (Class 1, 500 ms, deadline 10 ms).
  - `5`: `mux_acq` — CD4051 analog multiplexer sampling for X0/X1 (Class 1, 1000 ms, deadline 10 ms).
  - `6`: `dht11_acq` — DHT11 temperature/humidity worker snapshot (Class 1, 2000 ms, deadline 10 ms).
  - `7`: `moc7811_acq` — MOC7811 optical slot beam state sampling (Class 1, 1000 ms, deadline 10 ms).
  - `8`: `hcsr04_acq` — HC-SR04 ultrasonic distance ranging (Class 1, 1000 ms, deadline 20 ms).
  - `0, 9..15`: Spare/unassigned job slots in the 16-slot table.
- **Discovery Workflow:** Query active jobs via `DISPLAY EXECUTIVE`.

---

### 3.2 Discrete Enums & Options

#### `state` (`select`, `BINARY_STATE`)
- **Allowed Values:** `on`, `off`
- **Default:** `on`
- **Meaning:** `on` asserts logic high (3.3V); `off` deasserts logic low (0.0V).

#### `priority` (`int`, `PRIORITY_CLASS`)
- **Allowed Values:** `1`, `2`, `3`
- **Default:** `2`
- **Meaning:**
  - `1`: High Priority Class (`CLASS_0`) — Critical safety tasks, heartbeat.
  - `2`: Medium Priority Class (`CLASS_1`) — Sensor acquisition jobs.
  - `3`: Low Priority Class (`CLASS_2`) — Telemetry publishing and background metrics.

#### `condition` (`select`, `COMPARISON_OPERATOR`)
- **Allowed Values:** `gt`, `lt`
- **Default:** `gt`
- **Meaning:** `gt` triggers when signal > threshold; `lt` triggers when signal < threshold.

#### `signal` (`select`, `SIGNAL_ENUM`)
- **Allowed Values:** `temp`, `hum`, `ldr_raw`, `x0_raw`, `x1_raw`, `dist_cm`
- **Default:** `temp`
- **Meaning:**
  - `temp`: Ambient Temperature (°C) from DHT11 (0..50 °C).
  - `hum`: Relative Humidity (%) from DHT11 (20..90 %).
  - `ldr_raw`: Ambient Light from LDR on GPIO 35 (0..4095 counts).
  - `x0_raw`: Infrared Reflection from HW-870 on CD4051 X0 (0..4095 counts).
  - `x1_raw`: Hall Sensor IC2 footprint on CD4051 X1 (Unpopulated on PCB; floating counts).
  - `dist_cm`: Ultrasonic Distance from HC-SR04 (2..137 cm physical, up to 400 cm theoretical).

#### `transport` & `transport_id` (`select`, `TRANSPORT_PREFERENCE_ENUM` / `TRANSPORT_IDENTIFIER`)
- **Allowed Values:** `auto`, `serial`, `mqtt`
- **Default:** `auto` (or `serial` for transport-specific commands)
- **Meaning:**
  - `auto`: Automatic Failover — Prefers connected USB Serial, falls back to MQTT.
  - `serial`: USB Serial Transport — Dedicated point-to-point `/dev/ttyUSB0` link at 115200 baud.
  - `mqtt`: MQTT Network Transport — Mosquitto broker at localhost:1883 over topic `nexus/nexus_esp32/cmd`.

#### `key` (`string`, `NVS_CONFIG_KEY`)
- **Allowed Values:** `sample_rate`, `wifi_ssid`, `mqtt_broker`, `log_level`, `telemetry_interval`
- **Default:** `sample_rate`
- **Meaning:** Target configuration parameter key.
- **Discovery Workflow:** Inspect active keys via `DISPLAY CONFIGURATION`.

#### `enabled` (`bool`, `BOOLEAN_FLAG`)
- **Allowed Values:** `true`, `false`
- **Default:** `true`
- **Meaning:** `true` enables sensor acquisition; `false` halts acquisition.

#### `format` (`select`, `EXPORT_FORMAT_ENUM`)
- **Allowed Values:** `json`, `csv`
- **Default:** `json`
- **Meaning:** `json` produces structured JSON array; `csv` produces comma-delimited tabular rows.

#### `question` (`string`, `NATURAL_LANGUAGE_QUERY`)
- **Default:** `'Provide complete health status of the ESP32'`
- **Meaning:** Natural language prompt regarding system operational health, uptime, or telemetry dispatched to the local AI assistant.

#### `event_name` (`string`, `EVENT_NAME_STRING`)
- **Default:** `'OPERATOR_CHECKPOINT'`
- **Meaning:** Operator-defined event identifier string published via `PUBLISH EVENT`.

#### `value` (`string`, `CONFIG_VALUE_STRING`)
- **Default:** `'1000'`
- **Meaning:** String representation of configuration value to set.

---

### 3.3 Numeric Values, Units & Ranges

#### `duration_ms` (`int`, `NUMERIC_DURATION`)
- **Allowed Range:** `10 .. 5000` (units: `ms`)
- **Default:** `200`
- **Significance:** Buzzer beep duration. Firmware enforces an automatic `esp_timer` safety cutoff at 5000 ms.

#### `interval_ms` (`int`, `NUMERIC_INTERVAL`)
- **Allowed Range:** `50 .. 60000` (units: `ms`)
- **Default:** `1000`
- **Significance:** Sensor sampling or telemetry streaming interval.

#### `threshold` (`float`, `NUMERIC_LIMIT`)
- **Allowed Range:** `-40.0 .. 4095.0` (units depend on signal: `°C`, `%`, `counts`, `cm`)
- **Default:** `45.0`

#### `offset`, `temp_offset`, `hum_offset` (`float`, `CALIBRATION_OFFSET`)
- **Allowed Ranges:** `offset`: `-100.0 .. 100.0`; `temp_offset`: `-10.0 .. 10.0 °C`; `hum_offset`: `-20.0 .. 20.0 %`
- **Default:** `0.0`
- **Significance:** Additive calibration bias applied to sensor measurements.

#### `duration_sec` (`int`, `NUMERIC_DURATION`)
- **Allowed Range:** `1 .. 30` (units: `s`)
- **Default:** `5`
- **Significance:** Executive queue stress test duration.

#### `limit` (`int`, `RECORD_COUNT_LIMIT`)
- **Allowed Range:** `1 .. 1000` (units: `records`)
- **Default:** `100`

---

## 4. Authoritative Command Catalog (115 Commands)

Below is the complete inventory of all 115 registered commands across all 23 verbs. Each command lists its stable ID, destination, support status, confirmation requirement, parameters, and handler implementation truth:

### Verb 00: `NOP` (No Operation)
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0000` (0) | `NOP NONE` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live State:** Loopback echo test returning `code=0`. |
- **Example Request:** `{"verb": "NOP", "noun": "NONE", "params": {}}`
- **Expected Response:** `{"status": "completed", "code": 0, "msg": "NOP executed successfully", "uptime": 12000}`

### Verb 01: `INITIALIZE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0101` (257) | `INITIALIZE SYSTEM` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (live re-init requires reboot). |
| `0x0102` (258) | `INITIALIZE SENSORS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without re-running `nexus_sensors_init()`. |
| `0x0103` (259) | `INITIALIZE TRANSPORTS` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (runtime teardown restricted). |
| `0x0104` (260) | `INITIALIZE EXECUTIVE` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (deterministic boot lock). |

### Verb 02: `START`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0201` (513) | `START SYSTEM` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (system already running). |
| `0x0202` (514) | `START SENSORS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without mutating sampling timers. |
| `0x0203` (515) | `START TELEMETRY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without mutating telemetry state. |
| `0x0204` (516) | `START SELF_TEST` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live State:** Runs real `nexus_executive_run_selftest()`. |
| `0x0205` (517) | `START EXECUTIVE` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` (executive is already running). |

### Verb 03: `STOP`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0301` (769) | `STOP SYSTEM` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (safety watchdog preservation). |
| `0x0302` (770) | `STOP SENSORS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without halting sensor jobs. |
| `0x0303` (771) | `STOP TELEMETRY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without muting outbound queue. |
| `0x0304` (772) | `STOP EXECUTIVE` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (executive cannot be stopped). |

### Verb 04: `RESET`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0401` (1025) | `RESET FAULTS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Live State:** Zeroes `jobs_failed`, `deadline_misses`, sensor errors. |
| `0x0402` (1026) | `RESET STATISTICS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Live State:** Zeroes `disp->stats` and `conn_mgr` statistics. |
| `0x0403` (1027) | `RESET SENSOR_STATE` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Live State:** Clears sensor error flags across all 8 registry slots. |
| `0x0404` (1028) | `RESET QUEUES` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Live State:** Re-initializes `ready_queue` and `event_queue`. |

### Verb 05: `SET`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0501` (1281) | `SET PRIORITY` | FIRMWARE | UNSUPPORTED | `false` | `false` | `job_id`, `priority` | **Unsupported:** Returns `code=3` (dynamic priority unsafe). |
| `0x0502` (1282) | `SET SAMPLE_INTERVAL` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `sensor_id`, `interval_ms` | **Ack Stub:** Returns `code=0` without mutating job periods. |
| `0x0503` (1283) | `SET THRESHOLD` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `signal`, `threshold`, `condition` | **Ack Stub:** Returns `code=0` without mutating alert thresholds. |
| `0x0504` (1284) | `SET SENSOR_ENABLE` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `sensor_id`, `enabled` | **Ack Stub:** Returns `code=0` without disabling sensor slots. |
| `0x0505` (1285) | `SET TRANSPORT_PREFERENCE` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `transport` | **Ack Stub:** Returns `code=0` without mutating `s_conn_mgr.default_route`. |
| `0x0506` (1286) | `SET CONFIGURATION` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `key`, `value` | **Ack Stub:** Returns `code=0` without writing NVS. |

### Verb 06: `GET`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0601` (1537) | `GET STATUS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns uptime, heap, queue depths, job metrics. |
| `0x0602` (1538) | `GET CONFIGURATION` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns protocol version and connection settings. |
| `0x0603` (1539) | `GET SENSOR_LIST` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns array of supported sensor identifiers. |
| `0x0604` (1540) | `GET TIME` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns `uptime_ms` and monotonic microseconds. |
| `0x0605` (1541) | `GET VERSION` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Live Readback:** Returns firmware version (`1.0.0`) and IDF version. |
| `0x0606` (1542) | `GET HEALTH` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Live Readback:** Evaluates `exec_ok` and returns health scores. |
| `0x0607` (1543) | `GET CAPABILITIES` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Live Readback:** Enumerates mounted vs unmounted hardware peripherals. |

### Verb 07: `ENABLE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0701` (1793) | `ENABLE SENSOR` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `sensor_id` | **Ack Stub:** Returns `code=0` without mutating sensor state. |
| `0x0702` (1794) | `ENABLE TRANSPORT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `transport_id` | **Ack Stub:** Returns `code=0` without enabling transport link. |
| `0x0703` (1795) | `ENABLE TELEMETRY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `interval_ms` | **Ack Stub:** Returns `code=0` without starting telemetry stream. |

### Verb 08: `DISABLE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0801` (2049) | `DISABLE SENSOR` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `sensor_id` | **Ack Stub:** Returns `code=0` without halting sensor polling. |
| `0x0802` (2050) | `DISABLE TRANSPORT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `transport_id` | **Ack Stub:** Returns `code=0` without shutting down transport. |
| `0x0803` (2051) | `DISABLE TELEMETRY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without stopping telemetry stream. |

### Verb 09: `CALIBRATE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0901` (2305) | `CALIBRATE SENSOR` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `sensor_id`, `offset` | **Ack Stub:** Returns `code=0` without applying offset. |
| `0x0902` (2306) | `CALIBRATE ANALOG` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `channel` | **Ack Stub:** Returns `code=0` without baseline calibration. |
| `0x0903` (2307) | `CALIBRATE ENVIRONMENT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `temp_offset`, `hum_offset` | **Ack Stub:** Returns `code=0` without setting offsets. |

### Verb 0A: `ACKNOWLEDGE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0A01` (2561) | `ACKNOWLEDGE FAULT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `fault_id` | **Ack Stub:** Returns `code=0` (`ack: true`) without state change. |
| `0x0A02` (2562) | `ACKNOWLEDGE WARNING` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `warning_id` | **Ack Stub:** Returns `code=0` (`ack: true`) without state change. |
| `0x0A03` (2563) | `ACKNOWLEDGE EVENT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `event_id` | **Ack Stub:** Returns `code=0` (`ack: true`) without state change. |
- **Example Request:** `{"verb": "ACKNOWLEDGE", "noun": "EVENT", "params": {"event_id": 1}}`
- **Expected Response:** `{"status": "completed", "code": 0, "msg": "Event acknowledged", "uptime": 12050, "ack": true, "event_id": 1}`

### Verb 0B: `CLEAR`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0B01` (2817) | `CLEAR FAULTS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Live State:** Clears `jobs_failed = 0` (does not clear sensor errors). |
| `0x0B02` (2818) | `CLEAR HISTORY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Ack Stub:** Returns `code=0` (does not reset `sensor_history`). |
| `0x0B03` (2819) | `CLEAR STATISTICS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Live State:** Zeroes executive jobs dispatched/completed/failed. |

### Verb 0C: `TEST`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0C01` (3073) | `TEST SENSOR` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `sensor_id` | **Live State:** Checks registry slot presence (`count > 0`). |
| `0x0C02` (3074) | `TEST TRANSPORT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `transport_id` | **Hardcoded Stub:** Returns `"latency_us": 120` without link probe. |
| `0x0C03` (3075) | `TEST EXECUTIVE` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns `"exec_ok": true` without timing test. |
| `0x0C04` (3076) | `TEST PERIPHERAL` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns `"peripherals_ok": true`. |

### Verb 0D: `ACTUATE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0D01` (3329) | `ACTUATE RELAY` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (Relay K1 unmounted, GPIO 3 conflict). |
| `0x0D02` (3330) | `ACTUATE LED` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `led_id`, `state` | **Live Hardware:** Toggles GPIOs 27/14/12/13 and enforces `GPIO 22 = 0`. |
| `0x0D03` (3331) | `ACTUATE MOTOR` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (DC motors unmounted). |
| `0x0D04` (3332) | `ACTUATE SERVO` | FIRMWARE | UNSUPPORTED | `false` | `false` | None | **Unsupported:** Returns `code=3` (Servo unmounted on GPIO 33). |
| `0x0D05` (3333) | `ACTUATE BUZZER` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `duration_ms` | **Live Hardware:** Drives GPIO 15 HIGH with `esp_timer` cutoff `<= 5000 ms`. |
| `0x0D06` (3334) | `ACTUATE SHIFT_REGISTER` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `value` | **Ack Stub:** Returns `"shifted": true` without toggling GPIOs 21/16/17. |

### Verb 0E: `CAPTURE`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0E01` (3585) | `CAPTURE TELEMETRY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without taking snapshot. |
| `0x0E02` (3586) | `CAPTURE SENSOR_SNAPSHOT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without reading ADCs. |
| `0x0E03` (3587) | `CAPTURE EVENT_SNAPSHOT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without reading event queue. |

### Verb 0F: `PUBLISH`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x0F01` (3841) | `PUBLISH TELEMETRY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without enqueuing telemetry frame. |
| `0x0F02` (3842) | `PUBLISH EVENT` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `event_name` | **Ack Stub:** Returns `code=0` without enqueuing event frame. |
| `0x0F03` (3843) | `PUBLISH STATUS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Ack Stub:** Returns `code=0` without enqueuing status frame. |

### Verb 10: `DISPLAY`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x1001` (4097) | `DISPLAY STATUS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns executive status and tick count. |
| `0x1002` (4098) | `DISPLAY EXECUTIVE` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns jobs dispatched/completed/failed/missed. |
| `0x1003` (4099) | `DISPLAY QUEUES` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns ready queue and event queue occupancy. |
| `0x1004` (4100) | `DISPLAY FAULTS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns cumulative fault counts and latched status. |
| `0x1005` (4101) | `DISPLAY SENSORS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Live Readback:** Summarizes all 8 sensor registry slots. |
| `0x1006` (4102) | `DISPLAY TRANSPORTS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns static transport connection summaries. |
| `0x1007` (4103) | `DISPLAY CONFIGURATION` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Live Readback:** Returns configured intervals and parameters. |
| `0x1041` (4161) | `DISPLAY ENVIRONMENT` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns DHT11 temp/humidity and valid flag. |
| `0x1042` (4162) | `DISPLAY LIGHT` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns LDR raw ADC counts on GPIO 35. |
| `0x1043` (4163) | `DISPLAY DISTANCE` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns HC-SR04 ultrasonic distance in cm. |
| `0x1044` (4164) | `DISPLAY ANALOG` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns CD4051 X0 (HW-870) and X1 counts. |
| `0x1045` (4165) | `DISPLAY MOTION` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns MOC7811 optical slot state (clear/blocked). |
| `0x1046` (4166) | `DISPLAY EVENTS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns event queue count and drop count. |
| `0x1047` (4167) | `DISPLAY ACTUATORS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns static actuator status dict. |
| `0x1048` (4168) | `DISPLAY CONNECTIVITY` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns `serial: true, wifi: true, mqtt: true` even if offline. |

### Verb 11: `HISTORY`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x1101` (4353) | `HISTORY EVENTS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Reads historical event entries from memory. |
| `0x1102` (4354) | `HISTORY FAULTS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Reads historical fault records from memory. |
| `0x1103` (4355) | `HISTORY EXECUTIVE` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Reads executive timing and latency history. |
| `0x1104` (4356) | `HISTORY SENSORS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns `"readings_logged": true` without reading ring buffer. |
| `0x1105` (4357) | `HISTORY TRANSPORTS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns static transport transition summary. |
| `0x1141` (4417) | `HISTORY ENVIRONMENT` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Hardcoded Stub:** Returns `"env_logged": true` without reading ring buffer. |
| `0x1142` (4418) | `HISTORY SENSOR_READINGS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Hardcoded Stub:** Returns `"sensor_history": true` without reading ring buffer. |

### Verb 18: `DIAGNOSTICS`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x1801` (6145) | `DIAGNOSTICS SYSTEM` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Full diagnostics (heap, reset reason, uptime). |
| `0x1802` (6146) | `DIAGNOSTICS SENSORS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Reads per-sensor sample counts, errors, and valid flags. |
| `0x1803` (6147) | `DIAGNOSTICS QUEUES` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns ready queue depth and event drops. |
| `0x1804` (6148) | `DIAGNOSTICS TIMING` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns max dispatch latency and max callback duration. |
| `0x1805` (6149) | `DIAGNOSTICS MEMORY` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Free heap and minimum ever free heap watermark. |
| `0x1806` (6150) | `DIAGNOSTICS TRANSPORTS` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live Readback:** Returns `tx_packets`, `tx_drops`, and `reconnects`. *(Bug: rx_packets is 0)* |
| `0x1807` (6151) | `DIAGNOSTICS EXECUTIVE` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Hardcodes `"sched": "preemptive_priority"` (executive is cooperative). |
| `0x1808` (6152) | `DIAGNOSTICS PERIPHERALS` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | None | **Hardcoded Stub:** Returns static peripheral bus diagnostic dict. |
| `0x1809` (6153) | `DIAGNOSTICS DATABASE` | GROUND_STATION | EXISTING_CAPABILITY | `true` | `false` | None | **Host-Local:** Verifies InfluxDB HTTP connectivity and query latency. |
| `0x180A` (6154) | `DIAGNOSTICS AI_SERVICE` | GROUND_STATION | EXISTING_CAPABILITY | `true` | `false` | None | **Host-Local:** Verifies Open WebUI and local Ollama reachability. |

### Verb 1E: `OPEN`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x1E01` (7681) | `OPEN DASHBOARD` | GROUND_STATION | REQUIRED_M8 | `true` | `false` | None | **Host-Local:** Opens Grafana (`http://127.0.0.1:3000`) via `webbrowser.open_new_tab`. |
| `0x1E02` (7682) | `OPEN LOGS` | GROUND_STATION | REQUIRED_M8 | `true` | `false` | None | **Host-Local:** Opens Grafana explore / logs view (`:3000/explore`). |
| `0x1E03` (7683) | `OPEN AI` | GROUND_STATION | REQUIRED_M8 | `true` | `false` | None | **Host-Local:** Opens Open WebUI assistant (`http://127.0.0.1:8080`). |
| `0x1E04` (7684) | `OPEN GROUND` | GROUND_STATION | REQUIRED_M8 | `true` | `false` | None | **Host-Local:** Opens Mission Control UI (`http://127.0.0.1:8000/overview`). |
| `0x1E05` (7685) | `OPEN DATABASE` | GROUND_STATION | EXISTING_CAPABILITY | `true` | `false` | None | **Host-Local:** Opens InfluxDB UI (`http://127.0.0.1:8086`). |
| `0x1E06` (7686) | `OPEN DIAGNOSTICS` | GROUND_STATION | EXISTING_CAPABILITY | `true` | `false` | None | **Host-Local:** Opens diagnostics view (`:8000/diagnostics`). |

### Verb 1F: `ASK`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x1F01` (7937) | `ASK SYSTEM` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `question` | **Host-Local:** Dispatches question to `NexusConversationalAgent` for system telemetry. |
| `0x1F02` (7938) | `ASK SENSOR` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `sensor_id`, `question` | **Host-Local:** Dispatches question to AI agent for sensor trend/peak analysis. |
| `0x1F03` (7939) | `ASK EXECUTIVE` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `question` | **Host-Local:** Dispatches question to AI agent for scheduler/deadline analysis. |
| `0x1F04` (7940) | `ASK DIAGNOSTICS` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `question` | **Host-Local:** Dispatches question to AI agent for incident/fault root cause analysis. |
| `0x1F41` (8001) | `ASK ENVIRONMENT` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `question` | **Host-Local:** Dispatches question to AI agent for environmental threshold evaluation. |
- **Example Request:** `{"verb": "ASK", "noun": "SENSOR", "params": {"sensor_id": "hcsr04", "question": "max recorded distance to date"}}`
- **Expected Response:** `{"status": "completed", "code": 0, "msg": "AI service response for SENSOR", "data": {"reply": "..."}, "_execution_path": "HOST_LOCAL_OPERATION", "device_wire_envelope": "NOT_APPLICABLE"}`

### Verb 20: `EXPORT`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x2001` (8193) | `EXPORT TELEMETRY` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `format`, `limit` | **Host-Local:** Returns export summary string; live export via `GET /api/export`. |
| `0x2002` (8194) | `EXPORT DIAGNOSTICS` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `format` | **Host-Local:** Returns export summary string; live export via `GET /api/export`. |
| `0x2003` (8195) | `EXPORT EVENTS` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `format`, `limit` | **Host-Local:** Returns export summary string; live export via `GET /api/export`. |
| `0x2004` (8196) | `EXPORT FAULTS` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `format`, `limit` | **Host-Local:** Returns export summary string; live export via `GET /api/export`. |
| `0x2005` (8197) | `EXPORT CONFIGURATION` | GROUND_STATION | DEFERRED_M9_M10 | `true` | `false` | `format` | **Host-Local:** Returns export summary string; live export via `GET /api/export`. |

### Verb 21: `RUN`
| ID | Verb Noun | Target | Disposition | Supported | Confirmed | Parameters | Handler Truth |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `0x2101` (8449) | `RUN SELF_TEST` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live State:** Executes `nexus_executive_run_selftest()`. |
| `0x2102` (8450) | `RUN SENSOR_TEST` | FIRMWARE | REQUIRED_M8 | `true` | `false` | None | **Live State:** Verifies sensor presence in registry (`count > 0`). |
| `0x2103` (8451) | `RUN STRESS_TEST` | FIRMWARE | DEFERRED_M9_M10 | `true` | `true` | `duration_sec` | **Hardcoded Stub:** Returns `"cycles": 1000` without running stress iterations. |
| `0x2104` (8452) | `RUN TRANSPORT_TEST` | FIRMWARE | EXISTING_CAPABILITY | `true` | `false` | `transport_id` | **Hardcoded Stub:** Returns `"latency_us": 120`. |
| `0x2105` (8453) | `RUN QUALIFICATION_TEST` | FIRMWARE | EXISTING_CAPABILITY | `true` | `true` | None | **Hardcoded Stub:** Returns qualification pass without executing suite. |

---

## 5. Runtime Entity Discovery & Incident Lifecycle

### 5.1 Dual Incident Architecture Distinction
The Ground Station incorporates two separate incident handling paths:
1. **Stateless Web API (`GET /api/incidents` on `server.py:613-698`):** Computes ad-hoc alert dictionaries from the latest in-memory `TelemetryCache` sample (e.g. `dht_valid=false`, `age > 6.0s`, `dist` out of `2..400 cm`), returning hardcoded `"acknowledged": false`.
2. **Durable Monitoring Engine (`MonitoringService` in `monitoring/service.py`):** Evaluates 4 deterministic Flux-backed rules with hysteresis against InfluxDB and persists state transitions atomically into SQLite WAL (`nexus_incidents.db`).

### 5.2 Incident Lifecycle & Discovery
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
      "incident_id": 1,
      "title": "DHT11 Sensor Degraded",
      "severity": "WARNING",
      "signal": "dht_valid",
      "current_value": false,
      "acknowledged": false,
      "rule_id": "dht_sensor_invalid"
    }
  ],
  "event_types": {
    "1": "SYSTEM_BOOT", "2": "JOB_REGISTERED", "3": "JOB_FAILED", "4": "DEADLINE_MISS",
    "5": "QUEUE_OVERFLOW", "6": "SENSOR_DEGRADED", "7": "SENSOR_RECOVERED",
    "8": "TRANSPORT_ONLINE", "9": "TRANSPORT_OFFLINE", "10": "CONFIG_CHANGED", "11": "COMMAND_COMPLETED"
  }
}
```

### 5.3 Acknowledging vs Clearing Incidents
- **`ACKNOWLEDGE EVENT / FAULT / WARNING` (`0x0A01..0x0A03`):** Transmits an acknowledgement command to the ESP32 firmware, which responds with `{"ack": true}`. It acknowledges the notification without clearing cumulative error metrics.
- **`CLEAR FAULTS` (`0x0B01`):** Resets cumulative fault statistics (`jobs_failed = 0`) in the FreeRTOS executive without rebooting. Requires confirmation gating (`"confirmed": true`).

---

## 6. Protocol Status Codes

The NEXUS command protocol enforces explicit integer status codes across firmware and Ground Station (`StatusCode` enum in `ground_station/command_router/command_registry.py:33-46`):

| Code | Status String | Definition & Handling |
| :---: | :--- | :--- |
| **0** | `OK` / `completed` | Command executed successfully; results returned. |
| **1** | `REJECTED` | Parameter validation failed; missing required argument, type mismatch, or out-of-range value. |
| **2** | `UNKNOWN_CMD` | Verb or Noun code not recognized in canonical registry. |
| **3** | `UNSUPPORTED` | Command recognized but peripheral is unmounted or operation is restricted on EDU_ROBO V14. |
| **4** | `FAILED` | Internal execution failure during handler execution. |
| **5** | `DUPLICATE` | Repeated command sequence number dropped by idempotent filter. |
| **6** | `TIMEOUT` | Target failed to acknowledge or reply within timeout deadline (default 3.0s). |
| **7** | `CONFIRMATION_REQUIRED` | Hazardous operation submitted without `"confirmed": true` safety flag. |
| **8** | `TARGET_UNREACHABLE` | Selected transport path is offline or disconnected. |
| **9** | `INTERNAL_ERROR` | Transport parsing error or unhandled runtime exception. |

---

## 7. Cross-References & Source of Truth

- **Command Registry Authority:** [`ground_station/command_router/command_registry.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/command_router/command_registry.py)
- **Firmware Dispatcher Authority:** [`firmware/main/command/nexus_command_dispatcher.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_dispatcher.c)
- **Firmware Registry Header:** [`firmware/main/command/nexus_command_registry.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/command/nexus_command_registry.h)
- **Hardware Pin Map & Schematics:** [`docs/HARDWARE.md`](file:///home/aryan/Projects/SPIT/NEXUS/docs/HARDWARE.md)
- **Wire Framing & Telemetry Protocol:** [`docs/PROTOCOL_AND_TELEMETRY.md`](file:///home/aryan/Projects/SPIT/NEXUS/docs/PROTOCOL_AND_TELEMETRY.md)
- **Validation Script:** [`scripts/validate_reference_manual.py`](file:///home/aryan/Projects/SPIT/NEXUS/scripts/validate_reference_manual.py)
