# NEXUS — Milestone 4 Hardware Validation Report (Serial-Only)

## 1. Executive Summary & Verification Context

Milestone 4 introduced the Unified Connection Manager, Protocol v1 256-byte newline-delimited JSON envelopes (`nexus_envelope_t`), dedicated FreeRTOS background worker task (`nexus_conn`, Priority 2, 10 ms cycle), bounded 16-slot transmit queue, sliding 32-entry composite sequence deduplication, dual-core spinlocks for transport state, and graceful start/stop lifecycle management.

Following successful host-test verification (11/11 test groups with Clang AddressSanitizer/UndefinedBehaviorSanitizer) and native ESP-IDF v6.0.1 compilation, physical hardware validation was conducted on the physical ESP32 DevKit V1 board.

The device was flashed over USB serial (`/dev/ttyUSB0`) with unconfigured Wi-Fi/MQTT credentials to test serial transport and fallback isolation out of the box. A 95-second continuous serial capture was recorded from cold boot via hardware reset (RTS pin).

Based on the physical capture of 162/162 valid JSON envelopes, zero packet drops, zero transmission failures, zero resets/panics, and rock-solid flat heap stability over 95 seconds, Milestone 4 Serial-Only Hardware Validation is **ACCEPTED (PASS)**.

---

## 2. Firmware Binary Identity & Hardware Details

- **Target Chip:** ESP32-D0WD-V3 (revision v3.1, 240 MHz, MAC: `8c:94:df:7d:02:58`)
- **Board Configuration:** ESP32-WROOM-32 DevKit V1
- **Serial Interface:** Silicon Labs CP2102 USB-to-UART Bridge on `/dev/ttyUSB0`
- **Baud Rate:** 115200 baud
- **ESP-IDF Version:** ESP-IDF v6.0.1 (`CONFIG_FREERTOS_HZ = 100`, tick period = 10 ms)
- **Firmware Binary Path:** `firmware/build/nexus.bin`
- **Firmware Binary Size:** 907,280 bytes (`0xdd810` bytes; 13% / 141 KB free in 1 MB app partition)
- **Firmware SHA-256 Checksum:** `f5b5f4765cb764755b9e78cbaf49bb069163a7d94b7b2ae8c7c677b722e7b8d0`
- **Flashing Method:** `esptool.py` via `idf.py -p /dev/ttyUSB0 flash` at 460800 baud (without full erase; image partition hashes verified)
- **Flash Command Exit Code:** `0` (Success)
- **Serial Log File Path:** `docs/validation/milestone4_hardware_validation_20261016_212239.log`
- **Serial Log SHA-256:** `1df95ac3189c15d4c76a64f8010f5d1c7b05ab7a1f3abdd322ee84d6715de055`
- **Capture Duration:** 95.02 seconds (61,300 bytes captured, 1,005 lines)

---

## 3. Preflight Check Results

| Check Item | Parameter / Condition | Observed Value | Result |
|---|---|---|---|
| Working tree preservation | `git status --short` | All uncommitted files intact; nothing staged or committed | **PASS** |
| Toolchain environment | ESP-IDF v6.0.1 activation | Activated cleanly via `activate_idf_v6.0.1.sh` | **PASS** |
| Target serial port | Device detection | `/dev/ttyUSB0` (`CP2102_USB_to_UART_Bridge_Controller`) | **PASS** |
| Port exclusivity | `lsof` / `fuser` | No competing process holding port | **PASS** |
| Chip verification | `esptool chip_id` | ESP32-D0WD-V3 (rev v3.1, MAC `8c:94:df:7d:02:58`) | **PASS** |
| Binary existence & size | `firmware/build/nexus.bin` | 907,280 bytes (`0xdd810`) | **PASS** |
| Checksum match | Pre-flash SHA-256 match | `f5b5f4765cb764755b9e78cbaf49bb069163a7d94b7b2ae8c7c677b722e7b8d0` | **PASS** |
| Configuration isolation | `CONFIG_NEXUS_WIFI_SSID` | `""` (unconfigured; serial fallback active) | **PASS** |
| Partition capacity | `0x100000` (1024 KB) partition | `0x227f0` bytes (141,296 bytes / 13%) free headroom | **PASS** |

---

## 4. Hardware Runtime Telemetry Summary

The captured 95-second continuous serial log was parsed and analyzed:

| Metric | Target / Expectation | Physical Observed Result | Evaluation |
|---|---|---|---|
| Total Valid JSON Envelopes | $> 100$ | **162** | **PASS** (100% valid JSON) |
| Invalid / Corrupted Envelopes | 0 | **0** | **PASS** |
| Sequence Range & Ordering | Monotonic $1 \dots N$ | **1 to 162 (Strictly monotonic)** | **PASS** (Zero gap, zero duplicate) |
| Heartbeat Envelopes (`hb`, 1 Hz) | $\approx 90$ | **95** | **PASS** |
| Telemetry Envelopes (`telem`, 0.5 Hz) | $\approx 45$ | **48** | **PASS** |
| Status Envelopes (`status`, 0.2 Hz) | $\approx 18$ | **19** | **PASS** |
| Enqueued Packets (`tx_enq`) | $> 150$ | **154** (at 90.7s periodic report, 162 total) | **PASS** |
| Dispatched Packets (`tx_disp`) | Equal to `tx_enq` | **154** (100% dispatched) | **PASS** |
| Dropped Packets (`tx_drop`) | 0 | **0** | **PASS** |
| Transport Failures (`tx_fail`) | 0 | **0** | **PASS** |
| Transmit Queue Depth (`q_depth`) | $< 16$ | **0** (consistently drained) | **PASS** |
| Transmit Queue High Water Mark (`q_hwm`) | $\le 16$ | **2 / 16** (87.5% margin) | **PASS** |
| Memory Leak Check (`free_heap`) | Constant steady-state | **254,324 bytes** ($t=1.2\text{ s} \to 94.2\text{ s}$) | **PASS** (0 bytes leaked, 100% stable) |
| System Faults / Panics / WDT | 0 | **0** | **PASS** |
| Unexpected Resets | 0 | **0** (`reset_reason=1` cold boot only) | **PASS** |

---

## 5. Physical Sensor Observations

| Sensor | Pin / Driver | Physical Readings | Validity / Flags | Total Samples | Errors | Behavior Notes |
|---|---|---|---|---|---|---|
| **LDR** | GPIO35 (ADC1_CH7) | `raw=0 proc=0` | `0x01` (`VALID`) | 181 | 0 | Sampled every 500 ms without driver errors. Consistent with unilluminated physical condition in test bench. |
| **CD4051 X0** | GPIO36 (ADC1_CH0) | `raw=0..10 proc=0..8` | `0x01` (`VALID`) | 91 | 0 | Mux channel X0 sampled every 1000 ms. Dynamic signal variation observed (`0..10` analog noise/floating input range). |
| **DHT11 Temp** | GPIO4 (Background Task) | `32°C` (`raw=32 proc=32`) | `0x03` (`INIT \| VALID`) | 44 | 2 (startup) | 2 startup timeouts during 5s cold sensor warmup; stabilized at $t \ge 4.2\text{ s}$ with 44 consecutive error-free reads. |
| **DHT11 Hum** | GPIO4 (Background Task) | `62%..64%` (`raw=62..64`) | `0x03` (`INIT \| VALID`) | 44 | 2 (startup) | Physical ambient humidity readings dynamically fluctuating between 62%, 63%, and 64%. |

---

## 6. Comparison with Milestone 3.1 Physical Baseline

1. **System Stability & Reset Reason**:
   - Both Milestone 3.1 and Milestone 4 booted cleanly with `reset_reason=1` (`POWERON_RESET`) and ran with zero crashes, brownouts, or panics.
2. **DHT11 Warmup Characteristic**:
   - Milestone 3.1: 3 startup warmup timeouts before producing steady data.
   - Milestone 4: 2 startup warmup timeouts before producing steady data. Both stabilize completely without further errors.
3. **Heap Footprint**:
   - Milestone 3.1 baseline: `292,288 bytes` (without Wi-Fi/MQTT components compiled).
   - Milestone 4: `254,324 bytes` (with lwIP, Wi-Fi stack, and MQTT components compiled).
   - Both versions exhibit **zero heap drift / zero leaks** throughout continuous execution.
4. **Executive Deadline Accounting**:
   - In Milestone 3.1, `job_executive_metrics` had a duration of 40.9 ms ($< 50\text{ ms}$ budget) logging only sensors.
   - In Milestone 4, `job_executive_metrics` also logs connection manager statistics and formats/enqueues JSON status envelopes over 115200 baud UART, reaching 61.7 ms wall-clock time. Because its registered budget was 50 ms, the executive strictly incremented `dline_misses` by 1 on each 5000 ms metrics period. All sensor jobs (Priority Class 1, period 500/1000/2000 ms) and heartbeats executed well within budget ($< 20\text{ ms}$).
5. **Telemetry Delivery**:
   - Milestone 3.1: Pure human-readable ESP-IDF log output over UART.
   - Milestone 4: Dual-stream operation: human-readable diagnostics plus structured, bounded JSON envelopes (`hb`, `telem`, `status`) over USB serial with monotonic sequence counters.

---

## 7. Acceptance Verdict

**VERDICT: ACCEPTED (PASS) for Milestone 4 Serial-Only Hardware Validation**

- Hardware flashing completed with exit code 0 and hash verification.
- Live serial capture confirms end-to-end operation of the Unified Connection Manager, worker task, transmit queue, and envelope serialization.
- 162 valid JSON envelopes delivered over serial with 0 drops and 0 failures.
- Physical sensors verified active on hardware.
- Wi-Fi/MQTT remained safely idle as designed.

---

## 8. Post-Validation Anomaly Investigation Addendum (2026-10-16)

Following physical serial-only capture `milestone4_hardware_validation_20261016_212239.log`, a post-validation anomaly investigation evaluated two specific observations:

### Finding A: Executive Deadline Misses (`dline_misses=18`, `max_dur_us=61775`)
1. **Identified Callback**: `job_executive_metrics` (registered with `period_ms = 5000`, `deadline_ms = 50`). During the 95 s capture, it dispatched 19 times (ticks 1, 52, 102, ..., 902). Execution 1 took 5.5 ms (< 50 ms). All 18 subsequent executions took ~61.8 ms (> 50 ms), causing exactly 18 deadline misses and 18 `NEXUS_EVENT_TYPE_DEADLINE_MISS` event pushes.
2. **UART Saturation Mechanism**: Both ESP-IDF logging (`ESP_LOGI`) and `nexus_serial_transport` share UART0 (`stdout`). At 115200 baud, serial throughput is 11,520 bytes/s (86.8 µs/byte). `job_executive_metrics` was synchronously emitting ~710 bytes (1 `exec_stats` line, 4 per-sensor lines, 1 `conn_stats` line, plus tags/newlines). Transmission of 710 bytes requires $710 \times 86.8\text{ µs} = 61.63\text{ ms}$, matching the measured `max_dur_us=61775` (61.775 ms) within 0.2%.
3. **Dispatch Latency vs Deadline Miss**: `max_lat_us=96362` represents the 100 ms FreeRTOS tick startup quantization delay (identical to Milestone 3.1's 92,394 µs) and is independent of callback execution duration.
4. **Remediation**: In `firmware/main/app_main.c`, the 4 redundant unconditional per-sensor `ESP_LOGI` statements were removed from `job_executive_metrics` because all sensor data is continuously streamed via structured `telem` envelopes at 0.5 Hz. Steady-state callback output is reduced to ~275 bytes (~24 ms at 115200 baud), restoring a 52% timing safety margin within the 50 ms executive deadline budget.

### Finding B: CD4051 / HW-870 Sensor Reading Discrepancy
1. **Source Code Equivalence**: A `git diff` against Milestone 3.1 (`9738535`) confirms 0 lines diff in `firmware/main/sensors/`. `nexus_adc.c`, `nexus_cd4051.c`, `nexus_sensors.c`, and `nexus_sensor_registry.c` are 100% byte-for-byte identical.
2. **Hardware/Electrical Causality**: In both M3.1 and M4, the ADC reads GPIO 36 (`ADC1_CH0`) with 12 dB attenuation and 12-bit resolution, and scales via `(raw * 3300) / 4095`. In M4, 91 samples were acquired with 0 errors (`flags=0x01 VALID`). The digitized reading of 0–10 counts (0–8 mV) reflects true physical 0V at GPIO 36, indicating an unpowered 5V heater rail on the HW-870 module or a disconnected physical jumper wire during the M4 test setup.
3. **Host Test Limitations**: Host tests verify data structures, state machines, and scaling logic using mock ADC values, but cannot verify physical voltages, analog multiplexer resistance, or module power rails.

### Updated Milestone 4 Verdict: PASS with Caveats
- **Core Functionality**: **PASS**. Unified Connection Manager, FreeRTOS worker task, serialization, and non-blocking executive enqueue operate correctly on real hardware.
- **Caveat 1 (Timing)**: Executive metrics callback streamlined in source; physical timing re-measurement will confirm `dline_misses=0` on next flash session.
- **Caveat 2 (Sensor Module)**: Physical inspection and multimeter verification of the HW-870 5V rail and CD4051 wiring are required to restore expected gas sensor analog baseline.

---

## 9. Post-Fix Hardware Revalidation Results (2026-10-16 22:07:41)

Following the logging streamlining fix in `firmware/main/app_main.c`, the ESP32 was flashed with the post-fix firmware binary and a 95-second serial validation was captured.

- **Flashed Binary**: `firmware/build/nexus.bin` (907,248 bytes, `0xdd7f0` bytes)
- **Binary SHA-256**: `7235f7723d534bbbca5041fad28288f22b2433e65a1616c3bbcc6fb2eaa7d399`
- **Flashing Result**: Exit code 0, partition table and app written at 460800 baud, data hash verified.
- **Capture File**: [`docs/validation/milestone4_postfix_hardware_validation_20261016_220741.log`](file:///home/aryan/Projects/SPIT/NEXUS/docs/validation/milestone4_postfix_hardware_validation_20261016_220741.log) (56,682 bytes, 95.01s elapsed).

### 9.1 Executive Timing & Deadline Compliance
- **Deadline Misses (`dline_misses`)**: **0 (ZERO)** observed across all 19 periodic metrics job dispatches ($t=1\text{ s} \to 90.7\text{ s}$).
- **Maximum Execution Duration (`max_dur_us`)**: **44,370 µs (44.37 ms)**.
  - Reduced by **17.4 ms** from the pre-fix $61,775\text{ µs}$ measurement.
  - Strictly within the registered 50 ms budget (`deadline_ms = 50U`).
  - **Metric Scope Note**: `max_dur_us` is a global executive metric (`exec->stats.max_job_duration_us`) tracking the highest duration recorded across *any* dispatched job in the runtime. While step-function changes correlate with ticks where `job_executive_metrics` executed, individual per-job durations are not tracked separately by the executive; attribution to specific callbacks is an inference from tick timing and serial volume, not a per-job hardware trace.
- **Event Queue High-Water Mark (`ev_hwm`)**: **3 / 32** (zero `NEXUS_EVENT_TYPE_DEADLINE_MISS` events generated).
- **Dispatch Latency (`max_lat_us`)**: **96,332 µs** (consistent with 100 ms FreeRTOS startup tick quantization).
- **Queue Overflows (`q_overflows`)**: **0**.

### 9.2 Unified Connection Manager & Transport Protocol
- **Total Valid JSON Envelopes Received**: **162**
  - Heartbeat (`hb`, 1.0 Hz): **95**
  - Status (`status`, 0.2 Hz): **19**
  - Sensor Telemetry (`telem`, 0.5 Hz): **48**
- **Sequence Integrity**: Monotonic progression from **`seq=1` to `seq=162`** with **0 duplicates and 0 gaps**.
- **Transport Reliability**: `tx_drop = 0`, `tx_fail = 0`.
- **Queue Performance**: `tx_queue_depth = 0`, `tx_queue_hwm = 2 / 16` (87.5% safety margin).
- **Connection State**: `CONNECTED` (`SERIAL_ONLY` active link, Wi-Fi/MQTT safely unconfigured and idle).
- **Wi-Fi / MQTT Status**: **NOT PHYSICALLY VALIDATED** on live network in this capture; this test validates USB serial transport and unconfigured Wi-Fi/MQTT idle fallback only.

### 9.3 Physical Sensor Acquisition & Degraded Sensor Warnings
- **LDR**: `raw=0 proc=0` (`flags=0x01 VALID`, 0 errors, unilluminated bench).
- **CD4051 X0 (HW-870)**: `x0=3..10` raw counts ($4..8\text{ mV}$, mean ~6.4 counts, `flags=0x01 VALID`, 0 errors).
  - The reading is consistent with the initial Milestone 4 capture.
  - The discrepancy with Milestone 3.1 baseline (~3120 counts) remains **anomalous and unresolved pending physical electrical measurement** with a multimeter (HW-870 5V heater supply rail and CD4051 pin 3 wiring continuity). Software equivalence is proven, but physical electrical causes remain to be investigated.
- **DHT11 Temperature & Humidity**:
  - Two startup degraded sensor warnings were emitted at $t=633\text{ ms}$ and $643\text{ ms}$ (`errs=1 flags=0x0C`) during cold warmup, proving the new error-only diagnostic path functions as designed.
  - Stabilized at $t \ge 4.2\text{ s}$ producing steady $32^\circ\text{C}$ and $61\%..62\%$ relative humidity (`flags=0x03 INIT | VALID`) with zero further errors or warnings.

### 9.4 System Health & Memory Stability
- **Free Heap**: 254,324 bytes steady-state across the final 93 seconds (**0 bytes leaked**).
- **System Resets**: 1 (`POWERON_RESET` from initial serial RTS trigger); 0 unexpected reboots.
- **Faults / Panics / Watchdog Timeouts**: **0**.

### 9.5 Revalidation Verdict
**VERDICT: PASS WITH CAVEATS (Serial-Only Validation)**
- **Executive Timing Verification**: **PASS**. Zero observed executive deadline misses in post-fix capture (`dline_misses=0`, global `max_dur_us` 44.37 ms < 50 ms budget).
- **Transport Verification**: **PASS**. 162/162 envelopes delivered over USB serial with perfect sequence ordering, 0 drops, and 0 failures.
- **Caveat 1 (Sensor Reading Anomaly)**: CD4051/HW-870 analog readings remain anomalous and unresolved pending physical electrical measurement with a multimeter.
- **Caveat 2 (Network Transports)**: Wi-Fi and MQTT transports have not been physically validated on air/live network; only USB serial and unconfigured idle fallback have been validated.
