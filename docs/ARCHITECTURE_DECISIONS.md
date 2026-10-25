# NEXUS — Architecture Decision Records (ADRs)

> **Document Status:** Historical & Reconstructed Architecture Decisions  
> **Provenance Distinction:** Each ADR explicitly labels whether it is **Historically Evidenced** (directly supported by Git commits, code comments, and tests) or **Reconstructed / Recommended** (inferred from current implementation trade-offs).

---

## ADR-01: Cooperative Priority-Ordered Executive over Multi-Task Sensor Threading

- **Status:** Accepted — **Verified** (*Historically Evidenced*: commits `0666a9f`, `9738535`; `firmware/main/executive/nexus_executive.c`)
- **Context:** Running separate FreeRTOS tasks per sensor and telemetry publisher requires per-resource mutexes, larger per-task stack allocations on a RAM-constrained ESP32, and non-deterministic preemption interleavings.
- **Decision:** Run all periodic scheduling, fast sensor acquisitions, and envelope formatting inside a single cooperative FreeRTOS task (`"nexus_exec"`, priority `3`, `100 ms` `vTaskDelayUntil` tick) backed by static bounded structures (`nexus_job_table_t` = 16, `nexus_ready_queue_t` = 16 across `CLASS_0..2`, `nexus_event_queue_t` = 32, `nexus_ring_buffer_t` = 32), offloading **only** the `~25 ms` blocking DHT11 start-pulse/handshake to a dedicated worker task (`"nexus_dht11"`, priority `2`) communicating via `portMUX_TYPE` snapshot.
- **Consequences:**
  - *Positive:* Zero dynamic allocation in the executive; zero deadline misses (`0` across 30-minute soak, peak callback duration `29.86 ms < 50 ms` budget); deterministic priority order (`heartbeat` `CLASS_0` -> sensors `CLASS_1` -> telemetry `CLASS_2`).
  - *Trade-off:* Any inline busy-wait inside a `CLASS_1` job (such as `nexus_hcsr04.c` waiting up to `16 ms` for Echo rise + fall) directly consumes `"nexus_exec"` tick budget; cross-task command handlers on `"nexus_conn"` / `mqtt_task` require explicit locking (currently missing — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).

---

## ADR-02: Decoupling Callback Execution Budget from Grid Quantization Latency

- **Status:** Accepted — **Verified** (*Historically Evidenced*: commit `9738535` `feat(executive): correct timing contract and validate hardware baseline`; `nexus_executive.c:149-207`; `tests/test_milestone3_host.c:489-780`)
- **Context:** Because `app_main()` completes initialization ~`80-90 ms` after boot before `vTaskDelayUntil` aligns to the `100 ms` FreeRTOS tick (`CONFIG_FREERTOS_HZ=100`), a `500 ms` job first run at `T0 = 87 ms` is not yet `>= 500 ms` old at `T = 580 ms` (`493 ms`), so it dispatches at `T = 680 ms` (`93 ms` dispatch latency). Counting `dispatch_latency + callback_duration` against a `10 ms` callback deadline caused false cold-boot deadline misses.
- **Decision:** Track `max_dispatch_latency_us` separately for observability while counting `deadline_misses` strictly when `callback_duration_us > deadline_ms * 1000` (`nexus_executive.c:196-207`), and stamp `last_run_us = current_time_us` to lock periodic jobs onto the `100 ms` grid without burst catch-up.
- **Consequences:** Cold-boot grid alignment never triggers spurious fault latches; steady-state jitter drops near zero once aligned, while callback overruns remain strictly bounded.

---

## ADR-03: Strict `< 256`-Byte Newline-Delimited UTF-8 JSON (Protocol v1) Without CBOR

- **Status:** Accepted — **Verified** (*Historically Evidenced*: commits `4dda0d5`, `2386416`, `39f1966`; `nexus_envelope.h:16`, `envelope_parser.py:17`)
- **Context:** Both human-inspectable UART debugging and machine-validated MQTT ingestion were required across C11 firmware and Python stdlib/Paho adapters without heap-allocating JSON/CBOR ASTs on the ESP32.
- **Decision:** Standardize exclusively on single-line UTF-8 JSON (`"ver": 1`) terminated by `\n` with a hard ceiling of `NEXUS_ENVELOPE_MAX_LEN = 256` bytes (`<= 255` payload bytes). Oversized frames, `NaN`/`Infinity`, and `bool`-as-`int` confusion are rejected outright without truncation.
- **Consequences:**
  - *Positive:* Fixed `256`-byte buffers in `tx_queue` (`16 * 256 = 4 KB`); trivial streaming framing on UART0 and `mosquitto_sub`; worst-case extended M9 `"telem"` frame is `165` bytes.
  - *Trade-off:* Rich command responses (`>= 256` bytes) fall back to `"Response truncated"` (`code=4`, `nexus_command_dispatcher.c:146-153`). Earlier conceptual references to CBOR were superseded and never implemented.

---

## ADR-04: Asymmetric `AUTO` Transport Policy (Device Active/Standby Failover vs Host Dual Ingestion)

- **Status:** Accepted — **Verified** (*Historically Evidenced*: commits `ee20f8d`, `902dab3`; `nexus_connection_manager.c:413-426`, `nexus_host_manager.py:239-291, 369-425`)
- **Context:** UART0 (`115200` baud) is shared with `ESP_LOGI` diagnostic output and tethered by USB cable, whereas Wi-Fi/MQTT enables untethered LAN telemetry but can drop transiently.
- **Decision:**
  1. **Device Outbound (`NEXUS_ROUTE_AUTO`):** Prefer MQTT (`nexus/nexus_esp32/telemetry`, QoS 1) exclusively when `MQTT_CONNECTED`; fail over automatically to USB Serial (`stdout`) when MQTT is disconnected or degraded. (`NEXUS_ROUTE_BROADCAST` is implemented in C for dual emission but not enabled in `app_main.c`.)
  2. **Command Replies:** Pin every `"resp"` frame to the exact transport on which `"cmd"` arrived (`SERIAL_ONLY` or `MQTT_ONLY` on `/telemetry`).
  3. **Host Ingestion & Persistence:** Listen on Serial and MQTT concurrently, persist all valid frames without ingestion-time deduplication (preserving `transport=serial|mqtt` provenance tags), and deduplicate only at query time (`TelemetryQueryService.get_raw_envelopes(deduplicate=True, correlation_window_sec=0.5)`).
  4. **Host Outbound (`transport="auto"`):** Prefer connected local USB Serial first (lowest latency, zero broker dependency), falling back to MQTT (`nexus/<dev>/cmd`).
- **Consequences:** Seamless cable-pull or broker-restart resilience; however, operators capturing raw UART JSON (`milestone10_physical_qualification_20261025.jsonl`) receive `0` JSON envelopes on Serial whenever Wi-Fi/MQTT is actively connected unless MQTT is stopped or `NEXUS_ROUTE_BROADCAST` is selected.

---

## ADR-05: Missing-Data Honesty & Host-UTC Time Authority in Time-Series Storage

- **Status:** Accepted — **Verified** (*Historically Evidenced*: commits `05feaf3`, `59b2864`, `3cc3426`; `nexus_envelope.c:131-143`, `point_mapper.py:70-130`, `grafana/dashboards/nexus_telemetry.json`)
- **Context:** DHT11 1-wire reads occasionally fail checksum/timing (~`10.9%` invalid rate in 30-min soak), `IC2` Hall sensor (`X1`) is unpopulated on the physical PCB, and the ESP32 lacks an RTC/SNTP clock.
- **Decision:**
  1. Omit `temp` and `hum` from `"telem"` JSON and InfluxDB `nexus_telem` points whenever `dht_valid == false` (never substitute `0.0`), while still recording `dht_valid=false` for quality auditing.
  2. Stamp InfluxDB `_time` exclusively with host UTC arrival nanoseconds (`received_at * 1e9`) and persist device `uptime_ms` as a numeric field so reboots (`uptime_ms` drops) never corrupt time-series ordering.
  3. Expose raw ADC counts (`ldr_raw`, `x0_raw`, `x1_raw`) rather than uncalibrated ppm or lux formulas.
- **Consequences:** Eliminates zero-drop spikes in Grafana and prevents hallucinated gas-concentration alarms. *(Remaining gap: firmware still emits floating mux counts for unpopulated `x1` in `"telem"`, though Mission Control UI and AI tools explicitly label `x1_raw` as `NOT INSTALLED` — see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).*

---

## ADR-06: Two-Storage Split — InfluxDB v2 for Telemetry, SQLite WAL for Incident State

- **Status:** Accepted — **Partially verified** (*Historically Evidenced*: commits `59b2864`, `42f4c08`; `ground_station/persistence/influxdb_writer.py`, `ground_station/monitoring/store.py`)
- **Context:** InfluxDB v2 excels at append-only time-series aggregation via Flux, whereas stateful incident lifecycles (`OPEN` -> `RESOLVED`), unique active-incident constraints (`UNIQUE(device_id, rule_id) WHERE state = 'OPEN'`), and atomic transition audit logs require ACID relational semantics.
- **Decision:** Store immutable telemetry/command/status observations in InfluxDB (`nexus_telemetry` bucket) and store mutable incident state + 90-day transition history in local SQLite (`nexus_incidents.db`, `PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;`).
- **Consequences:** Clean separation of append-only telemetry vs transactional incident state; zero false incidents during InfluxDB outages (`MonitoringService` skips rule evaluation when `DataSourceStatus.UNAVAILABLE`). *Integration gap:* `run_ground_station.py` does not yet instantiate `MonitoringService` or wire `/api/incidents` to `IncidentStore`.

---

## ADR-07: Structural Read-Only Isolation & Deterministic Fallback for Local AI

- **Status:** Accepted — **Partially verified** (*Historically Evidenced*: commits `54c1319`, `a445a3f`, `c03e124`; `ground_station/ai/*.py`, `docs/validation/M7_FINAL_CLOSURE.md`)
- **Context:** Local 7B LLMs (`mistral:7b` on Ollama) can hallucinate numbers, omit tool calls, or succumb to prompt injection if given write/command capabilities, and laptops running demos may not always have GPU/Ollama active. Exploratory notes in Milestone 7 also considered `cactus-compute`, which added runtime complexity without benefit over local Ollama.
- **Decision:**
  1. Standardize on local **Ollama (`mistral:7b`)** over stdlib HTTP (`urllib.request`), deferring `cactus-compute` entirely.
  2. Enforce a 4-layer read-only sandbox: (L1) 14-pattern `UNSAFE_MUTATION_PATTERNS` pre-flight refusal, (L2) anti-injection `SYSTEM_PROMPT`, (L3) `ALLOWED_TOOL_NAMES` 9-tool allowlist dispatcher, and (L4) structural dependency isolation (`NexusAITools` imports only `TelemetryQueryService` and `IncidentStore` — zero access to `CommandRouter` or transports).
  3. Discard any Turn-1 LLM response that fails to invoke a tool and fall back to a deterministic 11-branch regex router + template explainer.
- **Consequences:** Hardware actuation or database mutation from AI chat is structurally impossible, and common queries work even when Ollama is offline. *Trade-off:* When an operator asks an off-topic question (e.g., Mars trajectory) where `mistral:7b` rightly makes zero tool calls, the mandatory tool-call gate triggers the deterministic catch-all (`get_latest_telemetry` on `nexus_esp32`) instead of declining out-of-domain prompts.

---

## ADR-08: Hardware Safety Inhibits in Firmware (L293D Motor Lock & Pin Conflict Avoidance)

- **Status:** Accepted — **Verified** (*Historically Evidenced*: commits `c1f2aa1`, `1a9bfcc`, `fee4fee`; `nexus_command_dispatcher.c:68-70, 539`, `docs/SPEC_SHEET.md`)
- **Context:** On the EDU_ROBO V14 PCB, diagnostic LEDs `LED1..LED4` (`GPIO27, 14, 12, 13`) share traces directly with the `L293D` H-bridge inputs (`1A..4A`), while `GPIO1`/`GPIO3` (`UART0 TX/RX`) are wired on-board to `TSOP1838` IR and `PC817` Relay optocoupler.
- **Decision:**
  1. Drive `GPIO22` (`L293D 1,2EN & 3,4EN`) strictly `LOW` (`0`) at dispatcher init and re-assert `GPIO22 = 0` on every `ACTUATE LED` command; mark `ACTUATE MOTOR`, `ACTUATE RELAY`, and `ACTUATE SERVO` as `is_supported = false` (`UNSUPPORTED`).
  2. Leave `GPIO1` and `GPIO3` dedicated exclusively to `UART0` console/serial protocol I/O.
  3. Use `ADC_UNIT_1` (`GPIO35`, `GPIO36`) exclusively so Wi-Fi (`ADC2` hardware conflict on ESP32) never collides with analog sampling.
- **Consequences:** Eliminates accidental H-bridge current draw during LED actuation, preserves UART0 integrity, and enables glitch-free concurrent Wi-Fi + ADC sampling.

---

## ADR-09: Recommended Future Architectural Remediation (*Reconstructed / Recommended*)

Based on static audit findings (see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)), three targeted architectural refinements are recommended for the next engineering iteration:
1. **Executive Command Queue (`Planned`):** Route state-mutating commands (`RESET *`, `CLEAR *`) from `"nexus_conn"` / `mqtt_task` through a thread-safe command mailbox consumed inside `"nexus_exec"` to eliminate SMP data races.
2. **Unified Incident Store in `run_ground_station.py` (`Planned`):** Start `MonitoringService` inside `GroundStationOrchestrator` and back `GET /api/incidents` with `IncidentStore` (`nexus_incidents.db`) so Mission Control UI and AI tools share one authoritative incident ledger.
3. **Explicit Off-Topic Refusal Branch Before AI Catch-All (`Planned`):** Add unknown-device existence verification and an explicit out-of-domain intent check before Branch 10 (`get_latest_telemetry`) in `NexusConversationalAgent._run_deterministic_fallback()`.

