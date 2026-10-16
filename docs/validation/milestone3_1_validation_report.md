# NEXUS — Milestone 3.1 Hardware Validation Report

## 1. Executive Summary & Verification Context

Milestone 3.1 addressed the executive timing contract ambiguity identified following Milestone 3. The timing semantics were corrected so that:
1. `deadline_ms` strictly measures the maximum permitted callback execution duration budget.
2. Dispatch latency is measured and tracked independently as a scheduling performance metric (`max_dispatch_latency_us`).
3. Delayed dispatch due to polling quantization or queueing latency no longer increments deadline miss counters.

Physical hardware validation of this correction was conducted on an ESP32 DevKit V1 board running ESP-IDF v6.0.1. A 70-second continuous serial capture was recorded from cold boot.

Based on the combination of unit tests, build validation, and hardware telemetry, the Milestone 3.1 timing contract correction is **ACCEPTED**.

---

## 2. Firmware Binary Identity & Hardware Details

- **Target Chip:** ESP32-D0WD-V3 (revision v3.1, 240 MHz, MAC: `8c:94:df:7d:02:58`)
- **Board Configuration:** ESP32-WROOM-32 DevKit V1
- **Serial Interface:** Silicon Labs CP2102 USB-to-UART Bridge on `/dev/ttyUSB0`
- **ESP-IDF Version:** ESP-IDF v6.0.1 (`CONFIG_FREERTOS_HZ = 100`, tick period = 10 ms)
- **Executive Polling Interval:** 100 ms (`EXECUTIVE_TICK_PERIOD_MS = 100U`)
- **Firmware Binary Path:** `firmware/build/nexus.bin`
- **Firmware Binary Size:** 160,784 bytes (`0x27410` bytes; 85% free in 1 MB app partition)
- **Firmware SHA-256 Checksum:** `621d6199f23938c7a28bee7db8642b02e972789dcb919e537399a783a0d81f01`
- **Flashing Method:** `idf.py -p /dev/ttyUSB0 flash` (without full erase; partition hashes verified)

---

## 3. Host-Test and Build Verification Results

| Suite / Build Target | Scope | Result | Exit Code |
|---|---|---|---|
| `tests/test_milestone2_host` | Job table, ready queue, event queue, ring buffer, executive lifecycle | **5/5 PASSED (100%)** | `0` |
| `tests/test_milestone3_host` | Sensor registry, ADC LDR, CD4051 mux, DHT11 packet parsing, priority integration, budget-only deadline misses, failure accounting invariant, startup quantization timeline | **9/9 PASSED (100%)** | `0` |
| `firmware (ESP-IDF v6.0.1)` | Native compilation of all components, drivers, executive, and FreeRTOS tasks | **0 warnings, 0 errors** | `0` |

---

## 4. Hardware Runtime Telemetry Summary

The following metrics were logged over the 69-second captured run:

| Uptime (`ms`) | Ticks | Dispatched | Completed | Failed | Dline Misses | Queue Overflows | Ready HWM | Ev HWM | `max_lat_us` | `max_dur_us` | Free Heap (`B`) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **87** | 1 | 5 | 3 | 1 | **0** | **0** | 5 | 3 | 0 | 5,218 | 288,172 |
| **5,180** | 52 | 28 | 24 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **10,180** | 102 | 52 | 48 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **20,180** | 202 | 99 | 95 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **30,180** | 302 | 146 | 142 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **40,180** | 402 | 193 | 189 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **50,180** | 502 | 240 | 236 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **60,180** | 602 | 287 | 283 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |
| **65,180** | 652 | 310 | 306 | 3 | **0** | **0** | 5 | 7 | 92,394 | 40,908 | 292,288 |

### Telemetry Findings:
1. **Deadline Miss Invariant (`dline_misses = 0`):** Decoupling dispatch latency from callback budget evaluation ensured that zero false deadline misses occurred across 310 dispatches.
2. **Dispatch Latency (`max_lat_us = 92394`):** Accurately reflects the initial cold-boot startup quantization delay (~92.4 ms) before the first FreeRTOS tick alignment at 680 ms. Remained stable for the remainder of the session.
3. **Callback Duration (`max_dur_us = 40908`):** Worst-case callback wall-clock execution time was 40.9 ms (recorded during serial metrics logging), safely within the 50 ms metrics budget.
4. **Snapshot Accounting Invariant:**
   $$\text{dispatched} = \text{completed} + \text{failed} + \text{in\_flight}$$
   Across all steady-state telemetry snapshots, `dispatched = completed + 3 + 1` holds identically, where 3 represents the early DHT11 power-up stabilization errors, and 1 represents the active `job_executive_metrics` execution.
5. **Heap Stability:** After initial startup allocations (`free_heap = 288172`), free heap settled at `292288` bytes and remained completely constant from uptime 1,180 ms through 69,180 ms, demonstrating zero memory leaks.

---

## 5. Sensor Observations

| Sensor | Pin / Interface | Readings | Validity / Flags | Total Samples | Errors | Notes |
|---|---|---|---|---|---|---|
| **LDR** | GPIO35 (ADC1_CH7) | `raw=0 proc=0` | `0x01` (`VALID`) | 131 | 0 | Sampled every 500 ms without driver errors. The capture had no physical illumination change (unperturbed lighting condition), so dynamic response was not tested in this session. This is an environmental test condition, not a firmware defect. |
| **CD4051 X0** | GPIO36 (ADC1_CH0) | `raw=3120..3131` (`proc=2514..2523 mV`) | `0x01` (`VALID`) | 66 | 0 | Multiplexer channel X0 sampled every 1,000 ms with 0 errors. Voltages consistent at ~2.52 V. |
| **DHT11 Temp** | GPIO4 (Background Task) | `32°C` (`raw=32 proc=32`) | `0x03` (`INIT \| VALID`) | 30 | 3 (startup) | 3 startup timeouts during initial 5 s power-on stabilization; stabilized completely at $t \ge 10\text{ s}$ with 0 subsequent errors. |
| **DHT11 Hum** | GPIO4 (Background Task) | `56%` (`raw=56 proc=56`) | `0x03` (`INIT \| VALID`) | 30 | 3 (startup) | Stable humidity measurements matching ambient environment. |

---

## 6. Acceptance Assessment

| Item | Status | Evaluation Evidence |
|---|---|---|
| Startup identification & self-test | **PASS** | Firmware identifies as NEXUS; executive and bounded structures self-test reported PASSED. |
| Sensor job registration | **PASS** | 4 sensors initialized and Priority Class 1 jobs registered. |
| System stability (no panics/reboots) | **PASS** | Continuous 69+ second session; clean power-on reset (`reset_reason=1`); zero brownouts or watchdogs. |
| Bounded queue integrity | **PASS** | Zero queue overflows (`q_overflows = 0`); ready queue HWM = 5/16; event queue HWM = 7/32. |
| LDR dynamic illumination response | **NOT DEMONSTRATED BY THIS CAPTURE** | The capture had no physical illumination change, so dynamic response was not tested in this session. (Earlier physical verification confirmed ADC scaling and hardware connectivity; this capture reflects an unperturbed lighting condition and is not a firmware defect.) |
| CD4051 X0 and DHT11 health | **PASS** | CD4051 sampled 66 times with 0 errors. DHT11 produced 30 valid readings after its initial 3 power-on warm-up timeouts. |
| Execution-budget deadline accounting | **PASS** | `dline_misses = 0` throughout; callback durations remained within budget. |
| Dispatch latency telemetry | **PASS** | `max_lat_us` recorded startup quantization (~92.4 ms) without triggering deadline misses. |
| Callback duration telemetry | **PASS** | `max_dur_us` recorded worst-case wall-clock duration (40.9 ms) within budget. |
| In-flight accounting consistency | **PASS** | Snapshot invariant $\text{dispatched} = \text{completed} + \text{failed} + \text{in\_flight}$ held across all reports. |

---

## 7. Explicit Timing Model Semantics & Limitations

1. **Relative Sliding-Window Scheduling (Not Phase-Locked):**
   - The scheduler updates `job->last_run_us = current_time_us` upon dispatch.
   - Rescheduling is relative to actual dispatch time, meaning that any dispatch delayed by $\Delta t$ causes subsequent nominal releases to permanently slip forward by $\Delta t$.
   - On hardware, the initial startup quantization delay (~92.4 ms) slipped all harmonic periods (500, 1000, 2000, 5000 ms) onto the 100 ms FreeRTOS tick grid at 680 ms.
2. **Wall-Clock Callback Duration (Not Pure CPU Runtime):**
   - `max_job_duration_us` is measured via `esp_timer_get_time()` (monotonic hardware timer).
   - It captures total elapsed wall-clock time between callback invocation and return, which includes ISR execution and preemption by higher-priority FreeRTOS tasks (such as `nexus_dht11_task`).
3. **No Hard-Real-Time Guarantee:**
   - The NEXUS executive is a cooperative cyclic executive governed by a 100 ms polling loop.
   - It guarantees deterministic bounded memory, priority ordering among ready jobs, and non-blocking sensor integration, but does not provide hard-real-time dispatch determinism below the 100 ms polling resolution.

---

## 8. Log Artifact References

- Raw serial stream: [`docs/validation/milestone3_1_hardware_validation_raw.log`](milestone3_1_hardware_validation_raw.log)
- Formatted log: [`docs/validation/milestone3_1_hardware_validation.log`](milestone3_1_hardware_validation.log)
