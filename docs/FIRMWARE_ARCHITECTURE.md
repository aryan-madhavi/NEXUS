# NEXUS — ESP32 Firmware Architecture

> **Document Status:** Implementation-Accurate Firmware Specification  
> **Target SoC & SDK:** `ESP32-WROOM-32` (`ESP32-D0WD-V3` rev `v3.1`, dual-core Xtensa LX6) • **ESP-IDF v6.0.1**  
> **Primary Source Tree:** `firmware/CMakeLists.txt`, `firmware/sdkconfig`, `firmware/main/**`

---

## 1. Build System & Component Layout

### 1.1 Monolithic `main` Component & Host-Testable Design (`Implemented` / `Verified`)
NEXUS firmware is organized as a single ESP-IDF component (`firmware/main/CMakeLists.txt:1-41`) compiling **21 C source files** across 6 module directories:

```text
firmware/
├── CMakeLists.txt                  # Redirects SDKCONFIG to ../credentials/sdkconfig.local if present
├── sdkconfig                       # Tracked baseline config (ESP-IDF 6.0.1, empty secrets)
├── dependencies.lock               # Locks espressif/mqtt v1.0.0 and IDF 6.0.1
└── main/
    ├── CMakeLists.txt              # Registers 21 .c files and 9 IDF component dependencies
    ├── idf_component.yml           # Declares idf >=4.1.0 and espressif/mqtt: "*"
    ├── Kconfig.projbuild           # 9 CONFIG_NEXUS_* Wi-Fi/MQTT/backoff symbols
    ├── app_main.c                  # Static globals, boot self-test, 8-job wiring, executive_task
    ├── executive/
    │   └── nexus_executive.{h,c}   # Cooperative priority-ordered cyclic executive + self-test
    ├── data_structures/
    │   ├── nexus_job_table.{h,c}   # Fixed 16-slot periodic/aperiodic job descriptor table
    │   ├── nexus_ready_queue.{h,c} # 16-slot priority-ordered (Class 0..2) FIFO ready queue
    │   ├── nexus_event_queue.{h,c} # 32-slot reject-newest circular diagnostic event queue
    │   └── nexus_ring_buffer.{h,c} # 32-slot overwrite-oldest sensor sample ring buffer
    ├── sensors/
    │   ├── nexus_sensor_registry.{h,c} # 8-slot sensor descriptor & latest-sample registry
    │   ├── nexus_sensors.{h,c}     # Subsystem init + registration of 5 acquisition jobs
    │   ├── nexus_adc.{h,c}         # Shared ADC_UNIT_1 oneshot handle (12-bit, 12 dB atten)
    │   ├── nexus_adc_ldr.{h,c}     # LDR driver on GPIO35 (ADC1_CH7)
    │   ├── nexus_cd4051.{h,c}      # CD4051 analog mux on GPIO4/2/5 -> GPIO36 (ADC1_CH0)
    │   ├── nexus_dht11.{h,c}       # Async worker task + critical-section decoder on GPIO19
    │   ├── nexus_moc7811.{h,c}     # Optical slot sensor on GPIO34
    │   └── nexus_hcsr04.{h,c}      # Ultrasonic ranger on GPIO25 (TRIG) / GPIO26 (ECHO)
    ├── transports/
    │   ├── nexus_envelope.{h,c}    # Protocol v1 JSON serializer & bounded header parser (<256B)
    │   ├── nexus_transport.{h,c}   # Polymorphic vtable (init, start, stop, send, recv)
    │   ├── nexus_serial_transport.{h,c}    # UART0 stdio transport (stdout TX / stdin RX)
    │   ├── nexus_wifi_mqtt_transport.{h,c} # Wi-Fi STA + esp_mqtt_client + backoff + RX reassembly
    │   └── nexus_connection_manager.{h,c}  # 16-slot TX queue, route policy, 32-slot RX dedup
    ├── command/
    │   ├── nexus_command_registry.{h,c}    # 115 canonical commands across 23 verbs
    │   └── nexus_command_dispatcher.{h,c}  # Ingress parser, actuator GPIO control, resp formatter
    └── diagnostics/                # Empty directory (0 files; unused)
```

Every core module guards ESP-IDF hardware headers with `#ifdef ESP_PLATFORM`, substituting POSIX `clock_gettime`, `pthread_mutex_t`, and deterministic mock injection hooks when compiled natively with `gcc`/`clang` on Linux (`tests/test_milestone{2,3,4,8,9}_host.c`).

### 1.2 Credential Isolation & `Kconfig.projbuild`
- **Secret Isolation (`firmware/CMakeLists.txt:2-4`):** When `SDKCONFIG` is not explicitly set on the command line, CMake checks `EXISTS "${CMAKE_CURRENT_LIST_DIR}/../credentials/sdkconfig.local"` and uses that gitignored file automatically. Tracked `firmware/sdkconfig` (`L712-728`) contains empty strings for all secrets.
- **Configured Project Symbols (`firmware/main/Kconfig.projbuild:1-63`):**

| Symbol | Type | Default in `sdkconfig` | Purpose |
| :--- | :--- | :--- | :--- |
| `CONFIG_NEXUS_WIFI_SSID` | `string` | `""` | Wi-Fi STA SSID; empty keeps device in USB Serial-only mode |
| `CONFIG_NEXUS_WIFI_PASSWORD` | `string` | `""` | Wi-Fi WPA2 passphrase |
| `CONFIG_NEXUS_MQTT_BROKER_URI` | `string` | `"mqtt://localhost:1883"` | Broker URI (`mqtt://<host-lan-ip>:1883` on hardware) |
| `CONFIG_NEXUS_MQTT_CLIENT_ID` | `string` | `"nexus_esp32"` | MQTT client ID and envelope `"dev"` identifier |
| `CONFIG_NEXUS_MQTT_USERNAME` | `string` | `""` | Mandatory when `WIFI_SSID` is non-empty (`nexus_wifi_mqtt_transport.c:366-377`) |
| `CONFIG_NEXUS_MQTT_PASSWORD` | `string` | `""` | Mandatory when `WIFI_SSID` is non-empty |
| `CONFIG_NEXUS_MQTT_TOPIC_PREFIX` | `string` | `"nexus/nexus_esp32"` | Base prefix for `/telemetry` (pub) and `/cmd` (sub) |
| `CONFIG_NEXUS_RECONNECT_BASE_MS` | `int` | `1000` | Initial Wi-Fi reconnect backoff (`ms`) |
| `CONFIG_NEXUS_RECONNECT_MAX_MS` | `int` | `60000` | Maximum Wi-Fi reconnect backoff ceiling (`ms`) |

### 1.3 Key `sdkconfig` Parameters
- **Target & Optimization:** `CONFIG_IDF_TARGET="esp32"`, `CONFIG_FREERTOS_NUMBER_OF_CORES=2` (`L2127`), `CONFIG_COMPILER_OPTIMIZATION_DEBUG=y` (`-Og`), `CONFIG_COMPILER_OPTIMIZATION_ASSERTION_LEVEL=2` (`L456-465`).
- **Flash & Partition:** `2MB` flash (`L666`), single factory app partition (`CONFIG_PARTITION_TABLE_SINGLE_APP=y`, `L689`).
- **FreeRTOS Tick:** `CONFIG_FREERTOS_HZ=100` (`L2029` -> **1 RTOS tick = `10 ms`**), canary stack overflow checking enabled (`L2035`).
- **Watchdogs (`L1691-1707`):** Interrupt WDT (`300 ms`) and Task WDT (`5 s` monitoring `IDLE0`/`IDLE1`) enabled; **no application task calls `esp_task_wdt_add()`**.

---

## 2. Static Memory Model & Bounded Data Structures

**Zero Dynamic Allocation Policy (`Verified`):** Across all 21 NEXUS `.c` files, there are **zero calls to `malloc`, `calloc`, `realloc`, or `free`** (only underlying ESP-IDF Wi-Fi, lwIP, NVS, FreeRTOS `xTaskCreate`, `xSemaphoreCreateBinary`, `esp_timer_create`, and `esp_mqtt_client_init` allocate from heap during initialization). All NEXUS subsystems live in `.bss` (`app_main.c:21-24`): `s_executive`, `s_sensor_registry`, `s_conn_mgr`, and `s_command_dispatcher`.

### 2.1 Four Core Bounded Structures (`firmware/main/data_structures/`)

| Data Structure | Source Files | Capacity | Ordering / Lookup | Full / Overflow Behavior | Runtime Usage Truth |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Job Table** (`nexus_job_table_t`) | `nexus_job_table.{h,c}` | `16` slots (`NEXUS_JOB_TABLE_CAPACITY`) | First-fit `IDLE` slot scan; 1-based `job_id` (`1..65535` wrap) | Returns `0`, increments `registration_failures` | **Active (`8/16` slots used)** |
| **Ready Queue** (`nexus_ready_queue_t`) | `nexus_ready_queue.{h,c}` | `16` entries (`NEXUS_READY_QUEUE_CAPACITY`) | Sorted array: `CLASS_0` (`0`) > `CLASS_1` (`1`) > `CLASS_2` (`2`); **FIFO within equal priority**; duplicate `job_id` suppressed via `contains()` | **Reject-newest**: increments `overflow_count` & `exec->stats.queue_overflows`, pushes `QUEUE_OVERFLOW` event | **Active** on every `100 ms` executive tick |
| **Event Queue** (`nexus_event_queue_t`) | `nexus_event_queue.{h,c}` | `32` events (`NEXUS_EVENT_QUEUE_CAPACITY`) | FIFO ring buffer (`sequence_id` from `1`, `timestamp_us`, `type`, `severity`, `source_id`, `payload`) | **Reject-newest**: increments `overflow_drop_count`, returns `false` | **Write-only at runtime**: `pop()` is called only in `run_selftest()` and host tests; fills permanently after 32 events unless `RESET QUEUES` is invoked |
| **Sensor History Ring** (`nexus_ring_buffer_t`) | `nexus_ring_buffer.{h,c}` | `32` samples (`NEXUS_SENSOR_HISTORY_CAPACITY`) | Chronological circular ring (`head`, `tail`, `count`) | **Overwrite-oldest**: advances `tail`, increments `total_overwritten` | **Unused at runtime**: initialized & tested in `run_selftest()`, never written by sensor drivers (`count == 0` on live hardware) |

*(Note: `tests/test_milestone2_host.c` verifies all four data structures, though an older doc comment mentioned 64 samples; actual `NEXUS_SENSOR_HISTORY_CAPACITY` in `nexus_ring_buffer.h:26` is `32U`.)*

---

## 3. FreeRTOS Task Architecture & Synchronization

### 3.1 Application Tasks (`3` Explicit `xTaskCreate` Tasks + ESP-IDF System Tasks)

| Task Name | Entry Function & File | Stack (`bytes` in ESP-IDF) | Priority | Core Affinity | Period / Blocking Primitive | Responsibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `"nexus_exec"` | `executive_task` (`app_main.c:213-276, 338`) | `4096` (`EXECUTIVE_TASK_STACK_WORDS`*) | `3` | `tskNO_AFFINITY` | `vTaskDelayUntil(..., pdMS_TO_TICKS(100))` (`100 ms`) | Registers 8 periodic jobs, emits `SYSTEM_BOOT`, executes cooperative `nexus_executive_tick()` |
| `"nexus_conn"` | `conn_mgr_task` (`nexus_connection_manager.c:38-82, 171`) | `4096` | `2` | `tskNO_AFFINITY` | `ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(10))` (`10 ms`) | Drains outbound `tx_queue` (`16` frames) via active route; polls non-blocking `stdin` (`UART0`) RX |
| `"nexus_dht11"` | `dht11_worker_task` (`nexus_dht11.c:84, 368-442`) | `2048` | `2` | `tskNO_AFFINITY` | `ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(2500))` (woken @ `2000 ms`) | Performs `~25 ms` blocking 1-wire start pulse + 40-bit critical-section pulse decode off the executive thread |
| `esp_mqtt_client` *(IDF)* | Internal (`espressif/mqtt`) | IDF default (`6144`) | IDF default (`5`) | Unpinned | Socket select / MQTT keepalive | TCP/MQTT v3.1.1 I/O; invokes `mqtt_event_handler` -> `nexus_conn_mgr_inject_rx()` -> `nexus_command_dispatcher_rx_callback()` |
| `esp_timer` *(IDF)* | Internal (`sdkconfig:1747`) | `3584` | `22` | `CPU0` | Hardware timer ISR/task | Fires `reconnect_timer` (Wi-Fi backoff) and `s_buzzer_timer` (`GPIO15` auto-cutoff) |

*\*Implementation Note:* In ESP-IDF FreeRTOS, `xTaskCreate`'s `usStackDepth` argument is specified in **bytes**, not 32-bit words; thus `EXECUTIVE_TASK_STACK_WORDS = 4096U` allocates a `4096`-byte stack.

### 3.2 Synchronization Primitives & Concurrency Audit

| Primitive | Type & Location | Protected State |
| :--- | :--- | :--- |
| `s_conn_mgr_tx_mux` | `portMUX_TYPE` spinlock (`nexus_connection_manager.c:14`) | `mgr->tx_queue` (`enqueue`, `process_tx_queue`, `get_stats`) |
| `s_wifi_mqtt_spinlock` | `portMUX_TYPE` spinlock (`nexus_wifi_mqtt_transport.c:42`) | `s_esp_ctx`, `transport->state`, `transport->stats`, fragmented MQTT `rx_state` |
| `s_dht11_spinlock` | `portMUX_TYPE` spinlock (`nexus_dht11.c:35`) | Per-bit pulse measurement windows (`<= 175 us` per bit) and `s_async_data` handoff between `"nexus_dht11"` and `"nexus_exec"` |
| `mgr->task_exit_sem` | Binary `SemaphoreHandle_t` (`nexus_connection_manager.c:117`) | Clean `500 ms` bounded join in `nexus_conn_mgr_stop()` |
| `mgr->running` | C11 `atomic_bool` (`nexus_connection_manager.h:98`) | Lock-free worker loop termination flag (`acquire`/`release`) |

> **Documented Concurrency Limitations (`Implemented` — Unsynchronized Paths):**
> 1. **Cross-task command state access:** `nexus_command_dispatcher_process()` runs on `"nexus_conn"` (for Serial RX) or `mqtt_task` (for MQTT RX), reading and mutating `s_executive` (`RESET FAULTS`, `RESET STATISTICS`, `RESET QUEUES` at `nexus_command_dispatcher.c:236-277`) and `s_sensor_registry` (`RESET SENSOR_STATE`) **without a mutex**, racing against `"nexus_exec"` on dual-core SMP.
> 2. **RX deduplication & `next_seq`:** `mgr->dedup` (`nexus_connection_manager.c:521-564`) and `mgr->next_seq++` (`app_main.c:103, 193, 206` vs `nexus_command_dispatcher.c:1193`) do not acquire `s_conn_mgr_tx_mux`.

---

## 4. Custom Application Executive (`nexus_executive.c`)

### 4.1 Priority Classes & Registered Periodic Jobs (`8 / 16` Slots)

Jobs execute **cooperatively to completion** on `"nexus_exec"` in strict priority-class order (`CLASS_0` -> `CLASS_1` -> `CLASS_2`), with FIFO ordering among ready jobs of equal class and at most `NEXUS_READY_QUEUE_CAPACITY` (`16`) dispatches per `100 ms` tick (`nexus_executive.c:134-137`).

| Job ID | Name | Registration Site | Priority Class | `period_ms` | `deadline_ms` | Work Callback & Action |
| :---: | :--- | :--- | :--- | :---: | :---: | :--- |
| `1` | `heartbeat` | `app_main.c:225` | `CLASS_0` (`0`, Critical) | `1000` | `20` | Formats & enqueues `"hb"` (`uptime`, `esp_get_free_heap_size()`, `total_ticks`) |
| `2` | `metrics` | `app_main.c:233` | `CLASS_2` (`2`, Telemetry) | `5000` | `50` | Logs degraded sensors; formats & enqueues `"status"` (`disp`, `comp`, `fail`, `lat_us`, `dur_us`) |
| `3` | `conn_telem` | `app_main.c:241` | `CLASS_2` (`2`, Telemetry) | `2000` | `20` | Reads `s_sensor_registry` (IDs `1..7`), formats & enqueues `"telem"`, logs `conn_mgr` stats |
| `4` | `ldr_acq` | `nexus_sensors.c:109` | `CLASS_1` (`1`, Sensor) | `500` | `10` | Oneshot ADC read on `GPIO35` (`ID 1` `"ldr"`) |
| `5` | `mux_acq` | `nexus_sensors.c:117` | `CLASS_1` (`1`, Sensor) | `1000` | `10` | Selects CD4051 `X0` (`ID 4` `"hw870_x0"`) & `X1` (`ID 5` `"hall_x1"`), waits `20 us`, reads `GPIO36` |
| `6` | `dht11_acq` | `nexus_sensors.c:125` | `CLASS_1` (`1`, Sensor) | `2000` | `10` | Snapshots `s_async_data` (`ID 2` `"dht11_temp"`, `ID 3` `"dht11_hum"`) & notifies `"nexus_dht11"` |
| `7` | `moc7811_acq` | `nexus_sensors.c:133` | `CLASS_1` (`1`, Sensor) | `1000` | `10` | Reads digital level on `GPIO34` (`ID 6` `"moc7811"`) |
| `8` | `hcsr04_acq` | `nexus_sensors.c:142` | `CLASS_1` (`1`, Sensor) | `1000` | `20` | Pulses `GPIO25` `10 us`, measures `GPIO26` Echo up to `8000 us` (`ID 7` `"hcsr04"`) |

### 4.2 Tick Quantization, Drift Rule & Budget-Only Deadline Accounting (`Verified`)
1. **Cold-Boot Quantization (`nexus_executive.c:124-160`):** On Tick 1 (`last_run_us == 0`), all 8 jobs are immediately eligible. `last_run_us` is updated to the **actual dispatch timestamp** (`current_time_us`). Because `app_main` initialization takes ~`80-90 ms` before `vTaskDelayUntil` aligns to the `100 ms` RTOS tick grid, the second execution of a `500 ms` job can experience up to `< 100 ms` one-time grid quantization (`max_dispatch_latency_us` ~ `93 ms` in `test_milestone3_host.c:649`, `100,023 us` in 30-min hardware soak), after which execution locks onto the `100 ms` grid with near-zero jitter.
2. **Decoupled Callback Deadline Check (`nexus_executive.c:196-207`):** Overruns are evaluated strictly against callback execution budget (`duration_us = end_time_us - start_time_us > deadline_ms * 1000U`), preventing grid quantization from falsely triggering `deadline_misses`.
3. **In-Flight Status Invariant (`test_milestone3_host.c:576`):** Because `job_executive_metrics` (`metrics`) reads `s_executive.stats` **while `metrics` itself is executing**, every emitted `"status"` envelope satisfies `disp == comp + fail + 1`.
4. **Rescheduling on Job Failure (`nexus_executive.c:122, 184-193`):** If a job callback returns `false` (e.g., transient DHT11 checksum error or HC-SR04 echo timeout), `jobs_failed++` and `JOB_FAILED` event are recorded, and the job state becomes `NEXUS_JOB_STATE_FAILED` (`!= IDLE`), so periodic rescheduling continues uninterrupted on subsequent periods.

---

## 5. Boot Sequence & Deterministic Pre-Flight Self-Test

`app_main()` (`firmware/main/app_main.c:278-349`) executes a 7-stage deterministic startup:

1. **Boot Banner & Reset Telemetry (`L280-281`):** Logs firmware banner and `esp_reset_reason()`.
2. **Pre-Flight Self-Test (`L284-288`, `nexus_executive.c:225-307`):** Exercises static scratch instances (`s_test_exec`, `s_test_rq`, `s_test_eq`, `s_test_rb`) to verify ready-queue priority ordering, FIFO tie-breaking, event-queue push/pop, ring-buffer overwrite wraparound, and mock job execution. On failure, logs `CRITICAL` and returns cleanly from `app_main()` without entering a reboot loop.
3. **Executive Initialization (`L292`):** Initializes `s_executive` (`100 ms` tick).
4. **Sensor Initialization (`L295-299`):** Initializes `s_sensor_registry`, `ADC_UNIT_1`, LDR, CD4051, DHT11 (spawning `"nexus_dht11"`), MOC7811, and HC-SR04. Partial driver failure logs `ESP_LOGW` without aborting boot.
5. **Connection Manager Initialization (`L301-321`):** Configures `NEXUS_ROUTE_AUTO` and calls `nexus_conn_mgr_init()`. If `CONFIG_NEXUS_WIFI_SSID` is non-empty while `MQTT_USERNAME` or `MQTT_PASSWORD` is empty, `wifi_mqtt_init()` refuses anonymous MQTT (`return false`), skipping transport and command-dispatcher start while still starting the executive.
6. **Command Dispatcher & Transport Start (`L326-334`):** Initializes actuator GPIOs (forcing `GPIO22 = 0` L293D motor inhibit, `GPIO27/14/12/13 = 0` LEDs, `GPIO15 = 0` buzzer + `s_buzzer_timer`), binds `nexus_command_dispatcher_rx_callback`, and starts Serial + Wi-Fi/MQTT + `"nexus_conn"`.
7. **Executive Task Launch (`L338-348`):** Spawns `"nexus_exec"` (`P3`). Only if `xTaskCreate` fails does firmware delay `100 ms` and invoke `esp_restart()`.

---

## 6. Unified Connection Manager & Command Dispatcher

### 6.1 Transport Abstraction (`firmware/main/transports/`)
- **Polymorphic Interface (`nexus_transport.h`):** Both `serial_transport` and `mqtt_transport` implement `nexus_transport_ops_t` (`init`, `start`, `stop`, `send`, `recv`).
- **UART0 Console Sharing (`nexus_serial_transport.c:75`, `nexus_connection_manager.c:44-71`):** Outbound Serial JSON frames write to `stdout` (`115200 8N1`), interleaved with ESP-IDF `ESP_LOG*` lines. Inbound Serial commands read non-blocking `STDIN_FILENO` in 64-byte chunks into `s_rx_line[256]`.
- **Wi-Fi/MQTT State Machine (`nexus_wifi_mqtt_transport.c`):** Transitions `DISCONNECTED -> CONNECTING -> CONNECTED` (subscribing to `<topic_prefix>/cmd` QoS 1) and `DEGRADED` on Wi-Fi/MQTT disconnect, with exponential Wi-Fi reconnect timer (`1 s, 2 s, 4 s, 8 s, 16 s, 32 s, 60 s`). Multi-fragment inbound MQTT payloads `< 256` bytes are reassembled safely under spinlock (`L747-965`).
- **Non-Persistent TX Queue (`nexus_connection_manager.c:481-510`):** Holds `16` `nexus_envelope_t` items (`4 KB`), reject-newest on saturation (`total_dropped++`), pop-before-send (`total_failed++` if underlying send fails).

### 6.2 Firmware Command Handler Tiers (`nexus_command_dispatcher.c`)
Of the **115** entries in `s_command_registry[]` (`nexus_command_registry.c`):
- **`10` Unsupported (`is_supported = false`):** Intercepted at `L1105` returning `code=3` (`NEXUS_CMD_STATUS_UNSUPPORTED`). *(Includes 4 unreachable `case` blocks at `L280` and `L483-502`.)*
- **`42` Live Hardware / State / Readback `case` Labels:**
  - **Physical GPIO Actuation (2):** `ACTUATE LED` (`GPIO27, 14, 12, 13` + re-asserts `GPIO22 = 0`), `ACTUATE BUZZER` (`GPIO15` + `s_buzzer_timer` `0..5000 ms`).
  - **State / Self-Test / Loopback (11 cases):** `NOP NONE`, `START/RUN SELF_TEST`, `RESET FAULTS` (zeroes fault/error counters without rebooting), `RESET STATISTICS/SENSOR_STATE/QUEUES`, `CLEAR FAULTS/STATISTICS`, `TEST/RUN SENSOR(_TEST)`.
  - **Live Readback (29 cases):** `GET {STATUS, CONFIGURATION, TIME, VERSION, HEALTH, CAPABILITIES}`, `DISPLAY {STATUS, EXECUTIVE, QUEUES, FAULTS, SENSORS, CONFIGURATION, ENVIRONMENT, LIGHT, DISTANCE, ANALOG, MOTION, EVENTS}`, `HISTORY {EVENTS, FAULTS, EXECUTIVE}`, `DIAGNOSTICS {SYSTEM, SENSORS, QUEUES, TIMING, MEMORY, TRANSPORTS}`.
- **`51` Reachable Acknowledgement or Hardcoded Stubs:** `INITIALIZE SENSORS`, `START/STOP {SENSORS, TELEMETRY}`, `START EXECUTIVE`, `SET *`, `ENABLE/DISABLE *`, `CALIBRATE *`, `ACKNOWLEDGE *`, `CLEAR HISTORY`, `ACTUATE SHIFT_REGISTER`, `CAPTURE *`, `PUBLISH *`, and 19 hardcoded readbacks/tests (e.g., `DISPLAY CONNECTIVITY` hardcodes `wifi:true, mqtt:true`; `DIAGNOSTICS EXECUTIVE` hardcodes `"preemptive_priority"`).
- **`12` Host-Destined Entries Without C `case` Labels:** `ASK *` (5), `EXPORT *` (5), and `DIAGNOSTICS {DATABASE, AI_SERVICE}` (2) hit `default:` (`code=3 UNSUPPORTED`) if sent directly to the ESP32 instead of intercepted by the Ground Station `CommandRouter`.

---

## 7. Related Documentation

- System context & end-to-end sequences: [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- Pin assignments, schematics, and electrical limits: [HARDWARE.md](HARDWARE.md)
- Wire envelopes and transport routing: [PROTOCOL_AND_TELEMETRY.md](PROTOCOL_AND_TELEMETRY.md)
- Command catalog and handler classifications: [COMMAND_REFERENCE.md](COMMAND_REFERENCE.md)
- Known concurrency and driver limitations: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)

