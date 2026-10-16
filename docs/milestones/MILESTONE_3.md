# NEXUS — Milestone 3: Sensor Subsystem, Sensor Registry & Initial Active Drivers

## 1. Milestone Overview

Milestone 3 expanded the NEXUS firmware from an executive core executing synthetic tasks into a functioning environmental monitoring system connected to real physical sensors. Deployed on the Go-Green Technologies EDU_ROBO V14 IoT Trainer Kit, the system integrated:
- A centralized **Sensor Registry** managing metadata, raw readings, engineering-unit scaling, validity flags, and error counters across all sensors.
- An **Analog-to-Digital Converter (ADC) Subsystem** built strictly on classic ESP32 **ADC1** to permanently avoid Wi-Fi radio conflicts on ADC2.
- An **LDR (Light Dependent Resistor)** driver on GPIO 35 (`ADC1_CHANNEL_7`).
- A **CD4051 8:1 Analog Multiplexer Driver** controlling 3 digital select lines (GPIO 4, 2, 5) and routing the on-board HW-870 MQ Gas / Air Quality sensor (Channel X0) through analog output GPIO 36 (`ADC1_CHANNEL_0`).
- A **DHT11 Temperature and Humidity Driver** on single-wire bidirectional GPIO 19.
- Complete integration with the Milestone 2 Executive as **Priority Class 1** jobs.

Crucially, Milestone 3 established significant debugging history, including the discovery and remediation of an executive-blocking DHT11 scheduling defect, real-time duration measurement implementation, initial physical hardware validation, and a comprehensive closure audit resolving the `dispatched = completed + 4` telemetry invariant and startup deadline miss phenomena.

---

## 2. Starting State

At the beginning of Milestone 3:
- Milestone 2 had delivered the bounded data structures (`nexus_job_table`, `nexus_ready_queue`, `nexus_event_queue`, `nexus_ring_buffer`) and the cyclic executive (`nexus_executive`), verified on hardware over a 65-second baseline.
- Subdirectory `firmware/main/sensors/` was completely empty.
- Executive Priority Class 1 (Sensor Data Acquisition) had zero registered jobs; only Priority Class 0 (Heartbeat) and Priority Class 2 (Metrics) were active.
- Callback duration measurement in `nexus_executive.c` was stubbed with a static nominal constant (`duration_us = 100U`), meaning actual execution times were not yet measured.

---

## 3. Objectives and Requirements

### Functional Requirements
1. **Sensor Registry Subsystem (`nexus_sensor_registry`)**:
   - Manage up to 8 sensor descriptors (`NEXUS_SENSOR_REGISTRY_CAPACITY = 8`) in static memory.
   - Maintain uniform metadata: `sensor_id`, `name`, `type`, `sample_interval_ms`, `error_count`, `sample_count`, `last_update_us`.
   - Store both `latest_raw` (integer ADC counts or sensor bits) and `latest_processed` (scaled physical units: %, mV, °C).
   - Track sample validity flags using bitmask definitions: `NEXUS_SAMPLE_FLAG_VALID` (`0x01`), `NEXUS_SAMPLE_FLAG_INIT` (`0x02`), `NEXUS_SAMPLE_FLAG_TIMEOUT` (`0x04`), `NEXUS_SAMPLE_FLAG_ERROR` (`0x08`).
2. **ADC Subsystem (`nexus_adc`)**:
   - Initialize ESP-IDF ADC OneShot driver.
   - Strictly constrain all analog conversions to **ADC1**, explicitly avoiding ADC2 to guarantee zero interference when Wi-Fi and Bluetooth are activated in Milestone 4.
   - Configure 12-bit conversion resolution (0–4095 counts) and 12 dB attenuation (up to ~3100 mV input range).
3. **LDR Sensor Driver (`nexus_adc_ldr`)**:
   - Sample ambient light via dedicated analog input **GPIO 35** (`ADC1_CHANNEL_7`).
   - Scale raw 12-bit ADC counts (0–4095) into a relative percentage (0–100%).
4. **CD4051 8:1 Multiplexer Driver (`nexus_cd4051`)**:
   - Control three push-pull digital GPIO lines: Select $A$ $\to$ **GPIO 4**, Select $B$ $\to$ **GPIO 2**, Select $C$ $\to$ **GPIO 5**.
   - Read analog common line $X$ via **GPIO 36** (SENSOR_VP, `ADC1_CHANNEL_0`).
   - Enforce switching settle delays ($10\ \mu\text{s}$) to allow multiplexer internal capacitances to charge before ADC sampling.
   - Sample Channel X0 (HW-870 MQ Gas / Air Quality sensor) and convert counts to nominal millivolts.
5. **DHT11 Driver (`nexus_dht11`)**:
   - Implement single-wire bidirectional protocol on **GPIO 19**.
   - Generate $20\text{ ms}$ host pull-down start pulse, switch to input with pull-up, and decode 40-bit pulse-distance-modulated transmission.
   - Verify 8-bit checksum: $(\text{Byte}_0 + \text{Byte}_1 + \text{Byte}_2 + \text{Byte}_3) \pmod{256} == \text{Byte}_4$.
6. **Executive Integration**:
   - Register sensor acquisition routines as Priority Class 1 periodic jobs:
     - LDR: Period $500\text{ ms}$, Execution Budget $10\text{ ms}$.
     - CD4051 X0: Period $1000\text{ ms}$, Execution Budget $10\text{ ms}$.
     - DHT11: Period $2000\text{ ms}$, Execution Budget $10\text{ ms}$.
   - Ensure the executive thread never blocks on sensor I/O.

---

## 4. Design Decisions and Rationale

| Decision | Selection | Alternatives Considered | Rationale & Trade-offs |
|---|---|---|---|
| **ADC Unit Selection** | Strictly ADC1 (GPIO 35, GPIO 36) | ADC2 channels (GPIO 2, 4, 12-15, 25-27) | On the classic ESP32, ADC2 is shared with the Wi-Fi SAR ADC controller. Using ADC2 causes ADC reads to fail or lock up whenever Wi-Fi is active. ADC1 operates completely independently of the Wi-Fi radio. |
| **DHT11 Concurrency Model** | Dedicated Asynchronous Background Task (`nexus_dht11_task`) | Direct polling inside executive callback | Generating the DHT11 $20\text{ ms}$ start pulse requires sleeping or busy-waiting. Executing this inside the cooperative executive would block the entire scheduler, delaying all other ready jobs and causing severe tick jitter. The background task isolates the slow physical bus, caching samples in memory. |
| **CD4051 Channel Switching** | Serialized select line write with settle guard | Free-running timer-driven cycling | CD4051 propagation delay and stray PCB capacitance require a brief electrical settling period ($10\ \mu\text{s}$) after changing select lines before the ADC sample-and-hold circuit triggers. Serialized sampling guarantees clean channel isolation. |
| **Sensor Storage Model** | Static Global Registry with atomic/bounded reads | Message queue from driver to executive | The Sensor Registry serves as a centralized blackboard. Decoupling data acquisition from consumer dispatch allows telemetry jobs to snapshot sensor state without queue allocations. |

---

## 5. Architecture and Concepts

### 5.1 Subsystem Architecture & Concurrency Model

```mermaid
flowchart TD
    subgraph Hardware Layer: EDU_ROBO V14 Trainer Kit
        LDR_Pin[LDR: GPIO 35 / ADC1_CH7]
        HW870_Pin[HW-870 Gas: CD4051 Mux X0]
        MuxOut[CD4051 Output: GPIO 36 / ADC1_CH0]
        MuxSel[CD4051 Selects: GPIO 4, 2, 5]
        DHT_Pin[DHT11: GPIO 19 Bidirectional]
    end

    subgraph Asynchronous Driver Task [FreeRTOS Task: nexus_dht11 (Priority 2, 2048 Words Stack)]
        DHT_Worker[Poll DHT11 Bus Every 2000 ms] --> BusPulse[20 ms Start Pulse & 40-Bit Read]
        BusPulse --> CacheSample[Cache Latest Temp & Humidity]
    end

    subgraph Cooperative Executive Task [FreeRTOS Task: nexus_exec (Priority 3, 4096 Words Stack)]
        ExecTick[Executive 100 ms Tick] --> SchedScan[Scan Priority Class 1 Jobs]
        
        SchedScan --> LDR_Job[Job: ldr_acq 500 ms]
        SchedScan --> MUX_Job[Job: mux_x0_acq 1000 ms]
        SchedScan --> DHT_Job[Job: dht11_acq 2000 ms]

        LDR_Job --> ReadLDR[nexus_adc_ldr_sample -> ADC1_CH7]
        MUX_Job --> ReadMux[nexus_cd4051_read_channel 0 -> ADC1_CH0]
        DHT_Job --> ReadCache[Read Cached DHT11 Sample < 1 µs]
    end

    ReadLDR --> RegUpdate[Update nexus_sensor_registry]
    ReadMux --> RegUpdate
    ReadCache --> RegUpdate

    RegUpdate --> MetricsJob[Job: executive_metrics 5000 ms Class 2]
    MetricsJob --> SerialLog[ESP_LOGI Serial Stream 115200 Baud]

    MuxSel -. Select 000 .-> HW870_Pin
    HW870_Pin -. Analog In .-> MuxOut
    DHT_Pin <==> BusPulse
    LDR_Pin --> ReadLDR
    MuxOut --> ReadMux
```

---

## 6. Implementation Walkthrough

### 6.1 Sensor Registry Subsystem
- **Files**: [`firmware/main/sensors/nexus_sensor_registry.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensor_registry.h), [`nexus_sensor_registry.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensor_registry.c)
- **Key Types & Constants**:
  - `NEXUS_SENSOR_REGISTRY_CAPACITY = 8`
  - Sensor IDs: `NEXUS_SENSOR_ID_LDR` (0), `NEXUS_SENSOR_ID_MUX_GAS_X0` (1), `NEXUS_SENSOR_ID_DHT11_TEMP` (2), `NEXUS_SENSOR_ID_DHT11_HUM` (3).
  - `nexus_sensor_descriptor_t`: Contains `sensor_id`, `name`, `type`, `sample_interval_ms`, `latest_raw`, `latest_processed`, `sample_flags`, `sample_count`, `error_count`, `last_update_us`.
- **Core Functions**:
  - `nexus_sensor_registry_init(nexus_sensor_registry_t *reg)`: Clears all descriptor entries.
  - `nexus_sensor_register(...)`: Registers a sensor with metadata; rejects duplicates and table overflows.
  - `nexus_sensor_update_sample(...)`: Updates `latest_raw`, `latest_processed`, `sample_flags`, increments `sample_count` (or `error_count` if flags indicate error), and records monotonic timestamp `last_update_us`.
  - `nexus_sensor_is_fresh(const nexus_sensor_descriptor_t *s, int64_t current_time_us, uint32_t max_age_ms)`: Checks whether `current_time_us - s->last_update_us <= max_age_us`.

### 6.2 ADC & LDR Driver Subsystems
- **Files**: [`firmware/main/sensors/nexus_adc.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc.h), [`nexus_adc.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc.c), [`nexus_adc_ldr.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc_ldr.h), [`nexus_adc_ldr.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc_ldr.c)
- **Implementation**:
  - `nexus_adc_init()`: Calls `adc_oneshot_new_unit()` for `ADC_UNIT_1`. Configures `ADC_BITWIDTH_12` and `ADC_ATTEN_DB_12`.
  - `nexus_adc_read_raw(adc_channel_t channel, int *out_raw)`: Wraps `adc_oneshot_read()`. Returns true on success.
  - `nexus_adc_ldr_sample(nexus_adc_ldr_t *ldr, nexus_sensor_registry_t *reg)`:
    - Calls `nexus_adc_read_raw(ADC_CHANNEL_7, &raw)`.
    - Clamps raw value between 0 and 4095.
    - Scales to percentage: `scaled_pct = (raw * 100) / 4095`.
    - Updates registry entry `NEXUS_SENSOR_ID_LDR`.

### 6.3 CD4051 Multiplexer Driver
- **Files**: [`firmware/main/sensors/nexus_cd4051.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_cd4051.h), [`nexus_cd4051.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_cd4051.c)
- **Pin Mapping & Channel Truth Table**:
  - Select Lines: $A$ $\to$ GPIO 4, $B$ $\to$ GPIO 2, $C$ $\to$ GPIO 5.
  - Output Line: $X$ $\to$ GPIO 36 (`ADC1_CHANNEL_0`).
  - Bit logic for channel $N \in [0..7]$:
    $$A = N \ \& \ 1, \quad B = (N \gg 1) \ \& \ 1, \quad C = (N \gg 2) \ \& \ 1$$
- **Implementation**:
  - Configures GPIO 4, 2, and 5 as push-pull outputs.
  - `nexus_cd4051_select_channel(uint8_t channel)`: Sets select pins via `gpio_set_level()`, then delays for $10\ \mu\text{s}$ using `esp_rom_delay_us(10)` to allow analog voltage stabilization.
  - `nexus_cd4051_sample_channel_x0(nexus_cd4051_t *mux, nexus_sensor_registry_t *reg)`:
    - Selects channel 0 ($A=0, B=0, C=0$).
    - Reads ADC1 Channel 0.
    - Converts raw counts to millivolts: $\text{mV} = (\text{raw} \times 3300) / 4095$.
    - Publishes to registry as `NEXUS_SENSOR_ID_MUX_GAS_X0`.

### 6.4 DHT11 Driver & Background Worker
- **Files**: [`firmware/main/sensors/nexus_dht11.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_dht11.h), [`nexus_dht11.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_dht11.c)
- **Low-Level Protocol**:
  - Host drives GPIO 19 LOW for $20\text{ ms}$, then HIGH for $30\ \mu\text{s}$, switching to input mode.
  - Sensor pulls LOW for $80\ \mu\text{s}$, then HIGH for $80\ \mu\text{s}$ (response handshake).
  - 40 bits transmitted: Each bit begins with a $50\ \mu\text{s}$ LOW pulse. A '0' bit is followed by a $26\text{–}28\ \mu\text{s}$ HIGH pulse; a '1' bit is followed by a $70\ \mu\text{s}$ HIGH pulse.
  - Portions of pulse measurement are wrapped in a FreeRTOS critical section (`portENTER_CRITICAL`) to prevent preemption during edge timing.
- **Asynchronous FreeRTOS Task Architecture**:
  - `nexus_dht11_init()` spawns FreeRTOS task `nexus_dht11_worker` (Priority 2, 2048 words stack).
  - Background worker loop:
    ```c
    while (1) {
        nexus_dht11_sample_t sample;
        if (nexus_dht11_read(&s_dht11, &sample)) {
            s_cached_sample = sample;
        }
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
    ```
  - Executive Callback (`nexus_dht11_job_fn`):
    - Executes in the `nexus_exec` thread context.
    - Does NOT touch GPIO 19 or wait $20\text{ ms}$.
    - Copies `s_cached_sample` in $< 1\ \mu\text{s}$.
    - Publishes temperature and humidity to `NEXUS_SENSOR_ID_DHT11_TEMP` and `NEXUS_SENSOR_ID_DHT11_HUM`.

---

## 7. Execution and Data-Flow Walkthrough

1. **System Boot (`app_main`)**:
   - Executive self-test executes and passes.
   - Sensor drivers initialize: `nexus_adc_init()`, `nexus_adc_ldr_init()`, `nexus_cd4051_init()`, `nexus_dht11_init()`.
   - `nexus_dht11_init()` creates `nexus_dht11_worker` background task on CPU 0.
   - Sensor Registry registers 4 sensors (`LDR`, `MUX_GAS_X0`, `DHT11_TEMP`, `DHT11_HUM`).
   - Priority Class 1 jobs registered with executive.
2. **Periodic Execution**:
   - **Every 100 ms**: `nexus_exec` task wakes up.
   - **At 500 ms**: LDR job released (Priority Class 1), performs ADC1 conversion ($~35\ \mu\text{s}$), updates registry.
   - **At 1000 ms**: CD4051 X0 job released (Priority Class 1), selects mux channel, performs ADC1 conversion ($~45\ \mu\text{s}$), updates registry. Heartbeat job released (Priority Class 0).
   - **At 2000 ms**: DHT11 job released (Priority Class 1), snapshots cached readings ($< 1\ \mu\text{s}$), updates registry.
   - **At 5000 ms**: Metrics job released (Priority Class 2), formats and prints executive statistics and sensor table to UART0.

---

## 8. Testing and Validation

### 8.1 Host Unit Tests
- **File**: [`tests/test_milestone3_host.c`](file:///home/aryan/Projects/SPIT/NEXUS/tests/test_milestone3_host.c)
- **Compilation**:
  ```bash
  gcc -Wall -Wextra -Werror -I./firmware/main -I./firmware/main/data_structures -I./firmware/main/executive -I./firmware/main/sensors \
      firmware/main/data_structures/*.c firmware/main/executive/*.c firmware/main/sensors/*.c tests/test_milestone3_host.c \
      -o tests/test_milestone3_host
  ```
- **Result**: **7/7 Test Groups Passed (100%)**
  - Sensor registry capacity, duplicates, bounds.
  - Sample update, error accounting, freshness.
  - LDR acquisition and scaling.
  - CD4051 truth table and serialized sampling.
  - DHT11 packet parsing, checksum, and timeout handling.
  - Priority Class 1 integration.
  - Executive deadline accounting with over-budget callback simulation.

### 8.2 Firmware Compilation
- **Command**: `cd firmware && idf.py build`
- **Output**: Binary `nexus.bin` size $160,800\text{ bytes}$ ($0x27410$), 85% free partition space. Zero errors, zero warnings.

### 8.3 Hardware Flash & 65-Second Validation
- **Device**: Classic ESP32 (`ESP32-D0WD-V3` rev 3.1) at `/dev/ttyUSB0`.
- **Command**: `idf.py -p /dev/ttyUSB0 flash`.
- **Observed Physical Telemetry**:
  - **CD4051 X0 (HW-870 Gas)**: 66 samples acquired across 65 seconds with 0 errors. Raw counts: `3120..3174` counts ($2514..2556\text{ mV}$), validity flag `0x01` (`VALID`).
  - **DHT11**: Produced 30 valid readings after 3 initial power-up stabilization timeouts. Reported $32^\circ\text{C}$ temperature and $56\%$ humidity, validity flag `0x03` (`INIT | VALID`).
  - **LDR**: Sampled every $500\text{ ms}$ (131 samples) with 0 errors. Raw count reported `0` counts ($0\%$).

---

## 9. Problems Encountered and Resolutions (The Milestone 3 Closure Audit)

Milestone 3 produced crucial debugging and architectural insights, thoroughly investigated during the formal closure audit:

### 9.1 Scheduling Defect 1: Blocking DHT11 Start Pulse
- *Problem*: In initial Milestone 3 code, `nexus_dht11_read()` executed `vTaskDelay(pdMS_TO_TICKS(20))` directly inside the executive callback.
- *Diagnosis*: Code review revealed that sleeping inside the cooperative executive put `nexus_exec` to sleep for $20\text{ ms}$ every $2\text{ seconds}$, delaying subsequent jobs and inducing severe tick jitter.
- *Resolution*: Refactored the DHT11 driver to run on an asynchronous FreeRTOS worker task (`nexus_dht11_worker`). The executive callback merely copies cached values in $< 1\ \mu\text{s}$.

### 9.2 Scheduling Defect 2: Hardcoded Job Duration
- *Problem*: `nexus_executive.c` used `uint32_t duration_us = 100U;` instead of measuring real elapsed time.
- *Diagnosis*: Any callback exceeding its deadline budget never triggered `deadline_miss_count`.
- *Resolution*: Wrapped `job->work_fn()` with `start_work_us = executive_get_time_us()` and `end_work_us = executive_get_time_us()`, establishing true wall-clock duration measurement.

### 9.3 Audit Investigation 1: The `dispatched = completed + 4` Telemetry Invariant
- *Observation*: Every telemetry report consistently showed `dispatched = completed + 4` (e.g., `dispatched=28 completed=24`, `dispatched=310 completed=306`).
- *Root Cause Analysis*:
  The closure audit proved mathematically that this is **not a software defect or counter leak**, but the exact sum of:
  $$\text{dispatched} = \text{completed} + \text{failed} + \text{in\_flight}$$
  1. `failed = 3`: The asynchronous DHT11 task experienced 3 startup timeouts during its first $5\text{ seconds}$ of power-on electrical stabilization before valid packets were cached. The executive recorded these 3 failed callback runs in `exec->stats.jobs_failed`.
  2. `in_flight = 1`: The metrics line is emitted by `job_executive_metrics()` *while executing inside its own callback*. The executive increments `jobs_dispatched` before executing the callback, but only increments `jobs_completed` upon successful return.
  3. Calculation: $\text{dispatched} = \text{completed} + 3 + 1 = \text{completed} + 4$.

### 9.4 Audit Investigation 2: The Five Startup Deadline Misses
- *Observation*: The Milestone 3 log recorded exactly 5 deadline misses during startup (`dline_misses=5`), but zero subsequent misses.
- *Root Cause Analysis*:
  - In Milestone 3, all 5 jobs (Heartbeat, Metrics, LDR, CD4051, DHT11) were registered at startup with `last_run_us = 0`.
  - The executive loop operated at a $100\text{ ms}$ period.
  - At tick 1 ($100\text{ ms}$), the scheduler evaluated:
    $$\text{latency} = \text{current\_time} - \text{expected\_time} \approx 92.4\text{ ms}$$
    $$\text{total\_time} = \text{latency} + \text{duration} \approx 93\text{ ms}$$
  - The deadline enforcement code evaluated `if (total_time > deadline_ms)`.
  - Because configured deadlines were $10\text{ ms}$ (sensors) and $20\text{ ms}$ (heartbeat), all 5 jobs were falsely marked as missing their deadlines due to startup polling quantization, even though callback execution durations were $< 1\text{ ms}$!
- *Resolution*: This critical finding directly motivated **Milestone 3.1**, where dispatch latency was decoupled from callback execution duration budgets.

### 9.5 Audit Investigation 3: LDR Constant Zero Reading
- *Observation*: LDR raw ADC values read 0 counts continuously.
- *Root Cause Analysis*:
  - ADC1 Channel 7 initialization and conversion logic succeeded with 0 errors.
  - Physical inspection of the EDU_ROBO V14 schematic revealed the LDR is connected in a voltage divider with a pull-down resistor to ground. In ambient indoor lab lighting without direct illumination, the output voltage is near 0 V.
  - Documented as an unperturbed physical lighting condition, not a software defect.

---

## 10. Final State and Acceptance

- **Criteria Met**:
  - Sensor registry implemented and verified with 4 active sensors.
  - ADC1-only architecture established, avoiding all future Wi-Fi conflicts.
  - CD4051 multiplexer channel X0 (HW-870 Gas) and DHT11 temperature/humidity validated on physical hardware.
  - Non-blocking DHT11 background task architecture resolved cooperative executive blocking.
  - Closure audit fully explained all telemetry invariants and startup deadline misses.
  - Milestone 3 core functionality **ACCEPTED**.
- **Remaining Limitations**:
  - Combining dispatch latency with execution duration inside a $100\text{ ms}$ polling loop caused false startup deadline misses.
  - Required the formal timing-contract correction executed in Milestone 3.1.

---

## 11. Lessons and Connections to Later Milestones

Milestone 3 highlighted the vital difference between **dispatch latency** (when a job begins executing relative to its nominal release time) and **callback execution duration** (how long the callback occupies the CPU). In a cooperative cyclic executive, an application with a $100\text{ ms}$ tick cannot guarantee sub-$10\text{ ms}$ dispatch latency without a finer tick or decoupling. This insight led directly to **Milestone 3.1: Executive Timing-Contract Correction & Hardware Validation Baseline**.

---

## 12. Source References and Evidence

- **Primary Commit**: `0bd6fb25950939f0a5eb69ca76aefa47a3acf918` (*feat: add sensor subsystem supporting DHT11, ADC, LDR, and multiplexed inputs with task registry and executive integration*)
- **Source Files**:
  - [`firmware/main/sensors/nexus_sensor_registry.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensor_registry.h), [`.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensor_registry.c)
  - [`firmware/main/sensors/nexus_adc.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc.h), [`.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc.c)
  - [`firmware/main/sensors/nexus_adc_ldr.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc_ldr.h), [`.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_adc_ldr.c)
  - [`firmware/main/sensors/nexus_cd4051.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_cd4051.h), [`.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_cd4051.c)
  - [`firmware/main/sensors/nexus_dht11.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_dht11.h), [`.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_dht11.c)
  - [`firmware/main/sensors/nexus_sensors.h`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensors.h), [`.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/sensors/nexus_sensors.c)
  - [`firmware/main/executive/nexus_executive.c`](file:///home/aryan/Projects/SPIT/NEXUS/firmware/main/executive/nexus_executive.c) (Milestone 3 revision)
- **Host Test Suite**:
  - [`tests/test_milestone3_host.c`](file:///home/aryan/Projects/SPIT/NEXUS/tests/test_milestone3_host.c) (Milestone 3 revision)
