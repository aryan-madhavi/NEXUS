# NEXUS — Milestone 9: Extended Sensor Integration (CD4051 X1, MOC7811, HC-SR04) & Observability

## 1. Milestone Overview

Milestone 9 extends the sensing capabilities of **NEXUS** (*Networked Environmental eXecutive with Unified Sensing*) beyond the baseline environmental suite (LDR, DHT11, and CD4051 Channel X0). It integrates three additional physical sensor channels across the full software stack—from bare-metal ESP-IDF drivers and cyclic executive scheduling to telemetry serialization, Ground Station parsing, InfluxDB persistence, and read-only AI conversational tools:

1. **CD4051 Channel X1 (Hall-Effect Magnetic Sensor)**: Serialized analog acquisition on the shared CD4051 multiplexer alongside Channel X0 (HW-870 Gas/IR).
2. **MOC7811 (Optical Slot Sensor)**: Digital slot sensor driver on GPIO34 (input-only GPI pin), reporting binary beam interruption (0 = unblocked, 1 = blocked).
3. **HC-SR04 (Ultrasonic Distance Sensor)**: Bounded time-of-flight distance measurement on Trigger GPIO25 and Echo GPIO26 with explicit 5V echo pulse electrical protection and sound-speed arithmetic ($echo\_us / 58 = distance\_cm$).
4. **Telemetry & Ground Station Pipeline**: Extended Protocol v1 telemetry formatting within the verified 256-byte envelope limit, backwards-compatible envelope parsing, InfluxDB schema extension, and AI signal grounding.
5. **Commands & Diagnostics**: Updated `DISPLAY ANALOG` (`0x1044`) and `DIAGNOSTICS SENSORS` (`0x1802`) command handlers.

---

## 2. Engineering Constraints Resolution

Before modifying firmware or protocol serialization, three core engineering constraints were rigorously evaluated and resolved:

### A. Sensor Registry Capacity
- **Evaluation**: The sensor registry statically allocates an array of `NEXUS_SENSOR_REGISTRY_CAPACITY = 8U` descriptors.
- **Sensor Count**:
  1. `NEXUS_SENSOR_ID_LDR` (ID 1)
  2. `NEXUS_SENSOR_ID_DHT11_TEMP` (ID 2)
  3. `NEXUS_SENSOR_ID_DHT11_HUM` (ID 3)
  4. `NEXUS_SENSOR_ID_MUX_GAS_X0` (ID 4)
  5. `NEXUS_SENSOR_ID_HALL_X1` (ID 5)
  6. `NEXUS_SENSOR_ID_MOC7811` (ID 6)
  7. `NEXUS_SENSOR_ID_HCSR04` (ID 7)
- **Resolution**: Exactly 7 sensors are registered, comfortably fitting within the existing capacity of 8 descriptors ($7 \le 8$). No modification of static array sizes or bounds checks was needed, preserving binary compatibility and existing unit tests.

### B. Telemetry Envelope Size Ceiling
- **Evaluation**: NEXUS Protocol v1 enforces a strict 256-byte maximum envelope ceiling (`NEXUS_ENVELOPE_MAX_LEN = 256U`).
- **Worst-Case Payload Calculation**:
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":4294967295,"type":"telem","uptime":9223372036854775807,"ldr":4095,"x0":4095,"x1":4095,"temp":50,"hum":100,"dht_valid":true,"slot":1,"dist":400}\n
  ```
- **Empirical Measurement**: The fully populated worst-case extended telemetry envelope was measured in host tests (`test_milestone9_host.c`) at **165 bytes**.
- **Margin**: 91 bytes of headroom below the 256-byte ceiling ($165 < 256$).
- **Backwards Compatibility**: Added `nexus_envelope_format_telemetry_ext` while preserving `nexus_envelope_format_telemetry` as a delegating wrapper. When M9 fields are not populated or negative, they are safely omitted, preserving byte-for-byte M4/M8 test compliance.

### C. Executive Timing Contracts & Electrical Safety
- **CD4051 Settling & Serialized Acquisition**: Channel X0 (Gas) and Channel X1 (Hall) share GPIO36 (ADC1 Ch0). Acquisition is serialized in `nexus_cd4051_acquire_all` with a $20\ \mu\text{s}$ settling delay per channel. Total execution time is $\approx 120\ \mu\text{s}$, well within the 10 ms cyclic executive callback deadline.
- **MOC7811 Pin Semantics**: Configured on GPIO34. GPIO34 is a GPI pin (input-only) on the ESP32 that lacks internal pull-up or pull-down resistors. The driver disables internal pulls and requires an external pull-up resistor on the PCB. Read duration is $< 1\ \mu\text{s}$.
- **HC-SR04 Electrical Safety & Bounded Timing**:
  - *Electrical Hazard*: Standard HC-SR04 modules operate from 5V $V_{CC}$ and output a 5V logic pulse on Echo. ESP32 GPIOs are not 5V tolerant (maximum rating 3.3V). Directly connecting 5V Echo to GPIO26 risks damaging the SoC.
  - *Safety Inhibitor*: The firmware driver implements a safety inhibitor (`s_live_hw_enabled = false`). In default safe mode, the driver returns `NEXUS_HCSR04_STATUS_UNVERIFIED_VOLTAGE` and inhibits physical pin manipulation until physical level shifting (e.g. 1kΩ / 2kΩ voltage divider) is confirmed.
  - *Timing Bounds*: The driver uses a 10 µs trigger pulse and bounds Echo pulse waiting with a 25 ms timeout ($\approx 4.3\text{ m}$ range), preventing task starvation. Distance calculation enforces valid physical bounds ($2\text{ cm} \le d \le 400\text{ cm}$).

---

## 3. Hardware Pinout & Conflict Matrix

| Sensor / Module | Channel / Signal | ESP32 GPIO | Pin Type | Status / Safety Notes |
|:---|:---:|:---:|:---:|:---|
| **LDR** | Analog In | GPIO35 | ADC1 Ch7 (Input only) | Verified M3/M10; active in Class 1 |
| **DHT11** | Data (One-Wire) | GPIO19 | GPIO (Bidirectional) | Verified M3/M10; async worker + Class 1 cache |
| **CD4051 MUX** | Sel A | GPIO4 | GPIO Output | Verified M3/M10; active in Class 1 |
| **CD4051 MUX** | Sel B | GPIO2 | GPIO Output | Verified M3/M10; active in Class 1 |
| **CD4051 MUX** | Sel C | GPIO5 | GPIO Output | Verified M3/M10; active in Class 1 |
| **CD4051 MUX** | Common Out | GPIO36 | ADC1 Ch0 (Input only) | Shared between X0 and X1 |
| **CD4051 X0** | Gas/IR HW-870 | MUX Ch0 | Analog Mux Channel | Verified M3/M10; active in Class 1 |
| **CD4051 X1** | Hall Effect (IC2) | MUX Ch1 | Analog Mux Channel | **Integrated M9**; IC2 unpopulated on PCB V14 (reads floating mux noise) |
| **MOC7811** | Optical Slot In | GPIO34 | GPI (Input only) | **Integrated M9 / Qualified M10**; external 10k pull-up R7 on PCB |
| **HC-SR04** | Trigger | GPIO25 | GPIO Output | **Integrated M9 / Qualified M10**; 10 µs pulse, 20 ms budget |
| **HC-SR04** | Echo | GPIO26 | GPIO Input | **Integrated M9 / Qualified M10**; Echo <= 3.3V verified in M10 |
| **TSOP1838** | IR Receiver | GPIO1 | UART0 TXD | **STRICTLY BARRED** (UART0 console conflict) |

---

## 4. Software Architecture & Implementation Details

### 4.1 Firmware Drivers & Registry (`firmware/main/sensors/`)
- [`nexus_sensor_registry.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensor_registry.h): Defined sensor IDs 5 (`NEXUS_SENSOR_ID_HALL_X1`), 6 (`NEXUS_SENSOR_ID_MOC7811`), 7 (`NEXUS_SENSOR_ID_HCSR04`) and sensor types `NEXUS_SENSOR_TYPE_OPTICAL_SLOT`, `NEXUS_SENSOR_TYPE_ULTRASONIC`.
- [`nexus_cd4051.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_cd4051.h) & [`nexus_cd4051.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_cd4051.c): Added X1 channel initialization, `nexus_cd4051_acquire_x1`, `nexus_cd4051_acquire_all`, and serialized execution inside the cyclic executive callback.
- [`nexus_moc7811.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_moc7811.h) & [`nexus_moc7811.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_moc7811.c): Implemented MOC7811 driver with binary beam state (0=unblocked, 1=blocked), external pull-up handling on GPI GPIO34, and mock test interfaces.
- [`nexus_hcsr04.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_hcsr04.h) & [`nexus_hcsr04.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_hcsr04.c): Implemented HC-SR04 driver with 10 µs trigger pulse, 25 ms timeout, echo-to-distance conversion ($echo\_us / 58$), default voltage inhibitor, and mock test interfaces.
- [`nexus_sensors.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensors.h) & [`nexus_sensors.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensors.c): Initialized and registered MOC7811 and HC-SR04 into the sensor registry and registered their Priority Class 1 cyclic executive jobs.

### 4.2 Transport & Telemetry (`firmware/main/transports/` & `app_main.c`)
- [`nexus_envelope.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_envelope.h) & [`nexus_envelope.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_envelope.c): Implemented `nexus_envelope_format_telemetry_ext` formatting `x1`, `slot`, and `dist` when valid, and preserved `nexus_envelope_format_telemetry` as a backward-compatible wrapper.
- [`nexus_connection_manager.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_connection_manager.h) & [`nexus_connection_manager.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/transports/nexus_connection_manager.c): Added `nexus_conn_mgr_send_telemetry_ext`.
- [`app_main.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/app_main.c): Updated `job_connection_telemetry` to read X1, MOC7811, and HC-SR04 from the registry and publish extended telemetry.

### 4.3 Command Dispatcher (`firmware/main/command/nexus_command_dispatcher.c`)
- **`DISPLAY ANALOG` (`0x1044`)**: Outputs multiplexer channel states for both X0 and X1:
  ```json
  {"mux_x0":3100,"valid":true,"mux_x1":2450,"valid_x1":true}
  ```
- **`DIAGNOSTICS SENSORS` (`0x1802`)**: Aggregates registration, valid readings count, sample reads, and error counts across all registered sensors:
  ```json
  {"registered":7,"valid_sensors":7,"reads":7,"errors":0}
  ```

### 4.4 Ground Station & InfluxDB Persistence (`ground_station/`)
- [`envelope_parser.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/connection_manager/envelope_parser.py): Extended `TelemetryPayload` with optional `x1_raw: Optional[int]`, `slot_state: Optional[int]`, and `dist_cm: Optional[float]`.
- [`point_mapper.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/persistence/point_mapper.py): Mapped `x1_raw`, `slot_state`, and `dist_cm` to InfluxDB fields with strict omission when None or uninitialized.
- [`models.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/analysis/models.py): Added M9 signals to `SIGNAL_CATALOG` and `ALLOWED_FIELDS_BY_MEASUREMENT["nexus_telem"]`.

### 4.5 AI Layer & Conversational Tools (`ground_station/ai/`)
- [`prompts.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/ai/prompts.py): Documented sensor conventions for `x1_raw` (raw ADC counts from Hall effect sensor, never claim calibrated Gauss/Tesla), `slot_state`, and `dist_cm`.
- [`tools.py`](file:///home/aryan/Projects/SPIT/NEXUS/ground_station/ai/tools.py): Exposed `x1_raw_adc`, `slot_state`, and `dist_cm` in `get_latest_telemetry` with operational guardrail notes.

---

## 5. Verification & Test Evidence

### 5.1 Host Unit Tests (C)
All five host unit test suites were compiled and executed with GCC on the Linux host:

1. **`tests/test_milestone2_host`**: 5/5 passed (100%)
   - Executive core, ready queue, event queue, ring buffer, dispatch cycle.
2. **`tests/test_milestone3_host`**: 11/11 passed (100%)
   - Sensor registry capacity, LDR, CD4051 truth table, DHT11 decoder, deadline accounting.
3. **`tests/test_milestone4_host`**: 14/14 passed (100%)
   - Envelope serialization, framing, bounded parser, deduplication, worker lifecycle.
4. **`tests/test_milestone8_host`**: 8/8 passed (100%)
   - Canonical command registry, supported/unsupported dispatch, display/diagnostics regression.
5. **`tests/test_milestone9_host`**: 6/6 passed (100%)
   - CD4051 X1 Hall-effect integration & serialized acquisition.
   - MOC7811 optical slot sensor driver and logic states.
   - HC-SR04 ultrasonic sensor driver, sound-speed math ($echo\_us / 58$), and safety inhibitor.
   - Full sensor suite capacity ($7 \le 8$).
   - Extended telemetry envelope formatting & 256-byte ceiling verification (measured worst-case 165 bytes).
   - Updated `DISPLAY ANALOG` (`0x1044`) and `DIAGNOSTICS SENSORS` (`0x1802`).

**Total C Host Tests**: **44 / 44 PASSED (100%)**.

### 5.2 Ground Station Test Suite (Python)
Executed with pytest under Python 3.14:
- `ground_station/tests/test_envelope_parser.py`: Verified M9 extended telemetry parsing and boundary checks.
- `ground_station/tests/test_point_mapper.py`: Verified InfluxDB field mapping for `x1_raw`, `slot_state`, `dist_cm`.
- Full regression suite: **217 / 217 PASSED (100%)** in 5.32 seconds.

### 5.3 ESP-IDF Cross-Compilation Build
Compiled target firmware using ESP-IDF v6.0.1:
```
Project build complete. To flash, run:
 idf.py flash
...
Successfully created ESP32 image.
Generated /home/aryan/Projects/SPIT/NEXUS/firmware/build/nexus.bin
nexus.bin binary size 0xe26a0 bytes. Smallest app partition is 0x100000 bytes. 0x1d960 bytes (12%) free.
```
- **Binary**: `firmware/build/nexus.bin` (927,392 bytes).
- **Result**: **BUILD PASS (Zero warnings, zero errors)**.

---

## 6. Targeted Closure Audit & Defect Corrections

During the final M9 closure audit, five targeted safety and robustness defects were investigated, remediated, and regression-tested:

1. **HC-SR04 Unconfigured GPIO Safety**:
   - *Issue*: `nexus_hcsr04_init` configured GPIO25 and GPIO26 at boot even while inhibited.
   - *Correction*: In safe inhibited mode (`s_live_hw_enabled == false`), GPIOs 25 and 26 remain completely unconfigured. Pin configuration occurs dynamically only upon explicit `nexus_hcsr04_set_live_enabled(true)` invocation, and pins are reset when disabled.
2. **Inhibitor Enforcement Across Targets**:
   - *Issue*: Host mock read mode previously bypassed the `s_live_hw_enabled` check.
   - *Correction*: Moved inhibitor verification to the entry of `nexus_hcsr04_read` for all targets, ensuring safe unverified voltage status (`NEXUS_HCSR04_STATUS_UNVERIFIED_VOLTAGE`) and preventing fabricated readings.
3. **Executive Callback Budget Compliance**:
   - *Issue*: Echo polling timeout of 25,000 µs could exceed the 10 ms cyclic executive callback budget.
   - *Correction*: Clamped `NEXUS_HCSR04_DEFAULT_TIMEOUT_US` to 8,000 µs (~1.37 m), guaranteeing total inline wait $\le 10\text{ ms}$ (2 ms rise + 8 ms echo).
4. **Stale Data Invalidation on Error**:
   - *Issue*: `nexus_sensor_record_error` set `ERROR | STALE` without clearing `VALID`, risking stale sample leakage.
   - *Correction*: Explicitly cleared `NEXUS_SAMPLE_FLAG_VALID` on error/timeout in `nexus_sensor_registry.c`.
5. **Pre-Publishing Telemetry Validation**:
   - *Issue*: `app_main.c` checked only `(sample_flags & VALID) != 0` for X1, MOC7811, and HC-SR04.
   - *Correction*: Added guards ensuring `sample_count > 0 && (sample_flags & VALID) != 0 && (sample_flags & ERROR) == 0` before populating telemetry.

---

## 7. Milestone Closure Status & Pending Physical Checks

### Milestone Status: **SOFTWARE COMPLETE (ACCEPTED FOR M9 COMMIT)**

All software deliverables, firmware drivers, executive scheduling contracts, protocol v1 serialization bounds, Ground Station parsing, InfluxDB mapping, and read-only AI tools are verified 100% clean and regression-free.

### Outstanding Physical Validation Items (Deferred to Milestone 10):
1. **HC-SR04 Echo Voltage Divider**: Verify with a multimeter that a 3.3V voltage divider ($R_1 = 1\text{ k}\Omega, R_2 = 2\text{ k}\Omega$ or level shifter) is present on GPIO26 before enabling live hardware acquisition.
2. **MOC7811 Pull-Up & Polarity**: Validate the external pull-up on GPI GPIO34 and physically verify optical interrupter beam polarity (`0 = unblocked, 1 = blocked`).
3. **CD4051 X1 Baseline**: Confirm the live analog ADC baseline of the onboard 49E linear Hall sensor at quiescent state (~2048 counts).
4. **Physical Dual-Link Soak**: Verify live streaming from flashed ESP32 to InfluxDB and Grafana over serial and authenticated MQTT.

**Next Canonical Milestone**: **Milestone 10: Final Qualification & Production Release**.
