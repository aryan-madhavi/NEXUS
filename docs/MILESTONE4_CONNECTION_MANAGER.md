# NEXUS — Milestone 4: Unified Connection Manager Specification & Verification

## 1. Executive Summary

Milestone 4 implements the **Unified Connection Manager** for NEXUS on ESP32 (ESP-IDF v6.0.1) and FreeRTOS, establishing a common communication layer that abstracts physical transports (USB Serial and Wi-Fi / MQTT) from the custom NEXUS deterministic executive and sensor drivers.

Key architectural properties:
- **Zero Executive Interference:** All transmission enqueue operations are non-blocking (measured at 89 ns/op on Linux x86_64 host without sanitizers; $< 3\ \mu\text{s}$ on 240 MHz ESP32 is an analytical instruction-budget estimate pending physical target trace verification). Transport network I/O, UART output, DNS resolution, and reconnection backoffs are handled entirely on an asynchronous FreeRTOS background task (`nexus_conn`).
- **Bounded Resources:** Static queue allocation with capacity for 16 messages (`NEXUS_CONN_TX_QUEUE_CAPACITY = 16`), 256-byte envelopes (`NEXUS_ENVELOPE_MAX_LEN = 256`), and a 32-entry sliding sequence deduplication window (`NEXUS_CONN_DEDUP_WINDOW = 32`). Zero heap allocations during runtime message dispatch.
- **Bounded Scratch Parser:** All wire-format envelope parsing copies inputs into a local stack buffer (`scratch[256]`) with strict length enforcement ($\text{len} < 256$) and guaranteed NUL termination, preventing memory overreads on malformed or unterminated data.
- **Composite Deduplication Identity:** Deduplication matches on composite identity `(source, dev, seq)` to prevent commands from distinct sources (e.g. Serial vs MQTT) from being falsely discarded merely because they share a sequence number.
- **Thread-Safe Diagnostics & Spinlocks:** Multi-field statistics snapshots and transport state transitions are synchronized using ESP-IDF classic dual-core spinlocks (`portMUX_TYPE`), preventing torn reads and lost counter increments without blocking event loops.
- **Exponential Reconnect Backoff:** Wi-Fi disconnect transitions trigger an asynchronous one-shot timer (`nexus_wifi_reconn`) with geometric backoff ($1\text{ s} \to 2\text{ s} \dots 60\text{ s}$ ceiling), avoiding network storms when the AP is offline.
- **Clean Lifecycle Teardown & Safe Rendezvous:** Event-handler instance handles are retained and cleanly unregistered on `wifi_mqtt_stop()`, timers are cancelled, and transport pointers are nulled. The background worker task (`nexus_conn`) uses a FreeRTOS notification (`ulTaskNotifyTake`) and binary semaphore (`task_exit_sem`) rendezvous with a 500 ms bounded timeout, returning false on timeout without destructive task deletion (preserving retryability). Worker self-stop is rejected, queue drain yields early on shutdown, and startup failures cleanly roll back started transports.
- **Graceful Unconfigured Fallback & Kconfig Isolation:** Configured via `firmware/main/Kconfig.projbuild`. When Wi-Fi SSID is blank (`CONFIG_NEXUS_WIFI_SSID=""`), the Wi-Fi/MQTT transport remains cleanly in `DISCONNECTED`, while the connection manager automatically routes all messages via USB Serial without hanging or throwing errors. Credentials remain out of Git.

---

## 2. Firmware Architecture & Component Structure

```text
firmware/main/
├── transports/
│   ├── nexus_transport.h / .c             # Base transport interface, state enum, routing enum, statistics
│   ├── nexus_envelope.h / .c              # Bounded 256-byte envelope, formatters & bounded header parser
│   ├── nexus_serial_transport.h / .c      # USB Serial transport adapter (stdout / UART)
│   ├── nexus_wifi_mqtt_transport.h / .c   # Wi-Fi STA + ESP-MQTT client adapter with backoff & spinlocks
│   └── nexus_connection_manager.h / .c    # Unified manager, bounded TX queue, composite dedup, worker task
├── executive/
│   └── nexus_executive.h / .c             # 100 ms tick scheduler (Milestone 3.1 timing contract)
├── sensors/
│   └── ...                                # LDR ADC, CD4051 Mux, DHT11 drivers
├── Kconfig.projbuild                      # Project Kconfig definitions (Wi-Fi, MQTT, backoff)
├── idf_component.yml                      # Espressif ESP-MQTT component dependency
├── CMakeLists.txt                         # Component registration & include paths
└── app_main.c                             # Lifecycle orchestration and telemetry registration
```

---

## 3. State Model & Transitions

### Connection Manager States (`nexus_conn_state_t`):
- `NEXUS_CONN_STATE_DISCONNECTED`: No active physical transports.
- `NEXUS_CONN_STATE_CONNECTING`: At least one transport is negotiating a connection.
- `NEXUS_CONN_STATE_CONNECTED`: At least one primary transport (or both dual-link transports) is active and ready.
- `NEXUS_CONN_STATE_DEGRADED`: A secondary transport (e.g. MQTT) has lost connection while Serial remains connected.
- `NEXUS_CONN_STATE_FAILED`: Transports experienced fatal initialization failure.

### Routing Policies (`nexus_route_policy_t`):
- `NEXUS_ROUTE_AUTO`: Prioritizes MQTT for remote telemetry uplink; automatically falls back to USB Serial if MQTT is offline.
- `NEXUS_ROUTE_SERIAL_ONLY`: Exclusively transmits over USB Serial.
- `NEXUS_ROUTE_MQTT_ONLY`: Exclusively transmits over MQTT. Fails gracefully if MQTT is offline.
- `NEXUS_ROUTE_BROADCAST`: Transmits over all connected transports concurrently.

---

## 4. Message Framing & Envelope Specification

Messages are formatted in newline-delimited JSON (`\n`) adhering to the NEXUS Protocol v1:

- **Heartbeat (`hb`):**
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":101,"type":"hb","uptime":12345,"heap":245000,"ticks":120}
  ```
- **Telemetry (`telem` — Valid DHT11 sample):**
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":102,"type":"telem","uptime":12350,"ldr":2048,"x0":1024,"temp":25,"hum":60,"dht_valid":true}
  ```
- **Telemetry (`telem` — Uninitialized or Degraded DHT11 sample, temp/hum omitted):**
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":102,"type":"telem","uptime":12350,"ldr":2048,"x0":1024,"dht_valid":false}
  ```
- **Status (`status`):**
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":103,"type":"status","uptime":12360,"disp":50,"comp":48,"fail":2,"lat_us":1200,"dur_us":450}
  ```
- **Event (`event`):**
  ```json
  {"ver":1,"dev":"nexus_esp32","seq":104,"type":"event","uptime":12370,"ev":1,"sev":2,"src":42,"val":999}
  ```

---

## 5. FreeRTOS Task & Concurrency Model

```
+--------------------------------------------------------------------------------+
|  FreeRTOS Task: nexus_exec (Priority 3, 4096 words stack)                      |
|  - Period: 100 ms tick                                                         |
|  - Class 0: Heartbeat (1000 ms period, 20 ms budget)                           |
|  - Class 1: LDR (500 ms), CD4051 X0 (1000 ms), DHT11 (2000 ms)                 |
|  - Class 2: Metrics (5000 ms), Connection Telemetry (2000 ms, 20 ms budget)    |
|                                                                                |
|  Job Callback:                                                                 |
|    nexus_conn_mgr_send_telemetry(...)                                          |
|      -> try_lock_tx() (Timeout = 0 ticks)                                      |
|      -> memcpy into static ring slot                                           |
|      -> Duration: < 3 microseconds (Non-blocking!)                             |
+--------------------------------------------------------------------------------+
                                       |
                   [ Bounded TX Queue: Capacity 16 ]
                                       |
                                       v
+--------------------------------------------------------------------------------+
|  FreeRTOS Task: nexus_conn (Priority 2, 4096 words stack)                      |
|  - Loop delay / notify: ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(10))            |
|  - Dequeues items from TX Queue                                                |
|  - Calls transport->ops->send(...) according to routing policy                 |
|  - Serial: stdout line-buffered output                                         |
|  - Wi-Fi/MQTT: esp_mqtt_client_enqueue(...)                                    |
|  - Shutdown rendezvous: signals task_exit_sem binary semaphore on termination   |
+--------------------------------------------------------------------------------+
```

---

## 6. Test & Build Verification Summary

| Test Suite / Target | Description | Result | Details |
|---|---|---|---|
| `test_milestone2_host` | Job table, queues, ring buffer, executive lifecycle | **5/5 PASSED (100%)** | Zero regression |
| `test_milestone3_host` | Sensor registry, LDR, Mux, DHT11 (safe API & error classification), timing contract | **11/11 PASSED (100%)** | Zero regression |
| `test_milestone4_host` | Envelope serialization, bounded parsing (F-01), queue saturation, routing, composite dedup (F-02), backoff (F-04), defaults/lifecycle (F-05/F-06), worker stop start-rejection, timing isolation, executive integration, MQTT inbound receive-path, telemetry schema validity | **13/13 PASSED (100%)** | Enqueue duration: **64 ns/op** (host without sanitizers), **597 ns/op** (ASan); sub-3-µs ESP32 duration is an analytical estimate |
| `test_milestone4_host (ASan/UBSan)` | Clang AddressSanitizer and UndefinedBehaviorSanitizer memory safety run | **13/13 PASSED (100%)** | 0 memory leaks, 0 buffer overruns, 0 UB |
| `firmware (ESP-IDF v6.0.1)` | Native cross-compilation for ESP32 with MQTT & Wi-Fi components (`credentials/sdkconfig.local` in `build/`) | **BUILD SUCCEEDED** | Binary: `nexus.bin` (0xdf0f0 bytes / 913,648 bytes, SHA-256: `fa9b9c92976b27490e7bece4fc1a0b23b12027a28b8df2d8eee7e4dd4502cbac`, 13% partition free, 0 warnings, 0 errors) |
