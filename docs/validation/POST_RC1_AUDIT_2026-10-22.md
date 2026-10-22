# NEXUS Post-`v0.9.0-rc1` Audit & Fixes (2026-10-22)

Baseline: `main` @ `fee4fee` (`v0.9.0-rc1`). Scope: full-repository audit against the
project vision, regression repair, and live-stack verification. No hardware was
flashed or reset; no persistent data was modified.

## 1. Verified pin map (source of truth: `firmware/main/sensors/*.h`)

| Signal | GPIO | Notes |
|:---|:---:|:---|
| LDR | GPIO35 (ADC1_CH7) | Input-only |
| CD4051 COM | GPIO36 (ADC1_CH0) | Input-only; X0 = HW-870, X1 = Hall (IC2 unpopulated on V14) |
| CD4051 SEL A/B/C | GPIO4 / GPIO2 / GPIO5 | GPIO2 and GPIO5 are strapping pins (outputs after boot) |
| DHT11 | GPIO19 | Bidirectional one-wire |
| MOC7811 | GPIO34 | Input-only; external 10k pull-up (R7) |
| HC-SR04 TRIG / ECHO | GPIO25 / GPIO26 | Echo ≤ 3.3 V verified in M10 |
| UART0 TX / RX | GPIO1 / GPIO3 | Reserved for USB serial; TSOP1838 barred (GPIO1 conflict) |

All analog acquisition stays on ADC1 (ADC2 conflicts with Wi-Fi).

**Unallocated candidates for a future physical button keypad (M11, not wired):**
GPIO32, GPIO33, GPIO16, GPIO17, GPIO21, GPIO22, GPIO23 (internal pull-up capable,
non-strapping); GPIO39 (input-only, needs external pull-up). Must be re-checked
against the physical PCB before wiring.

## 2. Defects found and fixed

| # | Area | Defect | Fix |
|:---|:---|:---|:---|
| 1 | `firmware/main/sensors/nexus_hcsr04.c` | `fee4fee` enabled live acquisition unconditionally, breaking the host safety-gate test | `s_live_hw_enabled` = `true` only under `ESP_PLATFORM` |
| 2 | `tests/test_milestone3_host.c` | Asserted 3 sensor jobs; M9 registers 5 | Configure MOC7811/HC-SR04 mocks, assert 5 |
| 3 | `firmware/main/command/nexus_command_dispatcher.c` | `DISPLAY ENVIRONMENT/LIGHT/ANALOG` used `error_count == 0`, so one startup timeout reported `valid:false` forever | Validity from latest sample flags; regression test in `test_milestone8_host.c` |
| 4 | `ground_station/analysis/telemetry_query.py` | Flux `limit()` ran before `sort()`, so `get_raw_envelopes`/`get_history` returned the **oldest** N rows (AI "latest" telemetry was 4 days stale) | `sort(desc: true)` before `limit()`, return newest chronological tail; unit test added |
| 5 | `ground_station/ai/agent.py` | LLM answers without tool calls were returned ungrounded (placeholder values observed with `mistral:7b`) | Fall back to deterministic tool-grounded router when no tool is called |
| 6 | `ground_station/ai/agent.py` | Fallback default device `esp32_01` has no data; live device is `nexus_esp32` | Retry on `nexus_esp32` only when no device was named and default returned empty |
| 7 | AI tools / registry / Open WebUI | M9 signals (`x1_raw`, `slot_state`, `dist_cm`) missing from routing and descriptions | Added |
| 8 | `docs/milestones/MILESTONE_9.md` | Pin table had stale GPIOs (LDR GPIO39, DHT11 GPIO17) | Corrected to match firmware headers |

## 3. Verification

| Check | Result |
|:---|:---|
| C host suites M2/M3/M4/M8/M9 (`gcc -std=gnu11 -Wall -Wextra -Werror`) | All pass |
| ESP-IDF v6.0.1 `idf.py build` | Pass, `nexus.bin` 0xe2890, 12 % partition free |
| `pytest ground_station/tests/ tests/soak/` | 237 / 237 pass |
| Live InfluxDB latest envelope (`nexus_esp32`) | 2026-10-22 08:26:19Z, seq 3957, all M9 fields present |
| Live AI deterministic Q&A (distance, slot, hall, temp/hum) | Grounded in the above envelope |
| Live `mistral:7b` tool loop | ~50 s latency; did not call tools unprompted → now forced to grounded fallback |

## 4. Open items

- Hall IC2 unpopulated → `x1_raw` is floating mux noise; label as unavailable in UI.
- Physical command buttons not present on V14; keypad design deferred to M11.
- Protocol v1 has no `boot_id`; sub-0.5 s reboot dedup ambiguity remains (documented).
- Local LLM latency/tool-calling reliability is weak on this host; evaluate smaller tool-capable models.
