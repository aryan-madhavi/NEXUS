# NEXUS Milestone 10 — Qualification Matrix & Release Gate Decision
# Board: DOIT ESP32DEVKIT-V1 (30-pin WROOM-32) | Kit: EDU_ROBO BOM V14
# Generated: 2026-10-22

---

## Hardware Configuration Notes

| Item | Status | Notes |
|------|--------|-------|
| Hall Effect IC2 (CD4051 X1) | **NOT INSTALLED** | Unpopulated on target PCB (BOM V14). x1_raw = mux channel float noise only. |
| TSOP1838 IR Receiver (GPIO1) | **BLOCKED** | GPIO1 = UART0 TX — hard conflict with console serial. Excluded until schematic revision. |

---

## Phase-by-Phase Qualification Summary

| Phase | Scope | Verdict | Evidence |
|-------|-------|---------|----------|
| A — Baseline Preflight | 44C + 236Py host tests | ✅ PASS | CI build logs |
| B1 — LDR | GPIO35/ADC1_CH7 | ✅ PASS | m10_b1_ldr_recovery.log |
| B2 — DHT11 | GPIO19 | ✅ PASS | m10_b2_dht11_excitation.log |
| B3 — HW-870 TCRT5000 | CD4051 X0/GPIO36 | ✅ QUALIFIED | m10_b3_hw870_excitation.log |
| B4 — MOC7811 Optical Slot | GPIO34 | ✅ PASS | m10_b4_moc7811_excitation.log |
| C — HC-SR04 Ultrasonic | GPIO25/GPIO26 | ✅ PASS | m10_c_hcsr04_excitation.log |
| D — Hall Effect IC2 | CD4051 X1/GPIO36 | ⛔ BLOCKED | IC2 not installed on PCB |
| E — Executive Timing | 100 Hz loop, heap | ✅ PASS | Phase E session logs |
| F — Command Dispatcher | 6/6 verbs via MQTT | ✅ PASS | m10_f_command_dispatcher.log |
| G — InfluxDB & Grafana | End-to-end pipeline | ✅ PASS | m10_g_influx_pipeline.log |
| I — 30-min Soak (run 2) | Sustained reliability | ✅ PASS | soak_qualification_run2_report.md |

---

## Phase F Details — Command Dispatcher (6/6 PASS)

| Command | seq | Status | code | RTT |
|---------|-----|--------|------|-----|
| NOP NONE | 107197 | completed | 0 | 0.2s |
| GET STATUS | 107198 | completed | 0 | 0.1s |
| DIAGNOSTICS SYSTEM | 107199 | completed | 0 | 1.1s |
| DISPLAY EXECUTIVE | 107200 | completed | 0 | 1.1s |
| RUN SELF_TEST | 107201 | completed | 0 | 0.3s |
| UNKNOWN COMMAND | 107202 | rejected | 2 | 0.2s |

---

## Phase G Details — InfluxDB Pipeline (PASS)

- Ingestion session: 90s, 149/149 writes, 0 failures, 0 drops
- Measurements verified: nexus_hb (88pts), nexus_telem (44pts), nexus_status (17pts)
- Invalid DHT gating: hum/temp count=40 vs telem=44 (4 invalid correctly omitted)
- Grafana: "NEXUS Telemetry & Device Health" (11 panels, uid=nexus_telemetry_health)
- DS health: "datasource is working. 3 buckets found" — OK

---

## Phase I Details — Soak Test (Qualifying Run 2: PASS)

| # | Criterion | Verdict |
|---|-----------|---------|
| 1 | System Stability (cold boot, reset_reason=1) | ✅ PASS |
| 2 | Executive Deadlines (dline_misses=0/357) | ✅ PASS |
| 3 | Executive Queues (q_overflows=0/357) | ✅ PASS |
| 4 | Callback Budget (peak 29856µs < 50000µs) | ✅ PASS |
| 5 | Dispatch Latency (peak 101600µs, startup allowance) | ✅ PASS |
| 6 | Transport Queuing (tx_drop=0, tx_fail=0) | ✅ PASS |
| 7 | Schema Integrity (880/880 compliant, 0 fabricated) | ✅ PASS |
| 8 | Heap Stability (trend=+199B/hr, R²=0.00) | ✅ PASS |
| 9 | Telemetry Validity (784/880=89.09% >= 85% target) | ✅ PASS |
| 10 | Error Isolation (max consec invalids=2 <= 3) | ✅ PASS |
| 11 | Queue HWM (peak 2/16) | ✅ PASS |
| 12 | Physical Driver (782/877=89.17% >= 80% target) | ✅ PASS |

---

## Release Gate Decision

### Open Blockers — v1.0.0 REFUSED

| # | Blocker | Severity |
|---|---------|----------|
| B1 | Hall Effect IC2 (Phase D) — sensor NOT installed on EDU_ROBO BOM V14 | MANDATORY |
| B2 | TSOP1838 IR Receiver — GPIO1 conflict with UART0 TX | MANDATORY |

**v1.0.0 may NOT be tagged until both hardware blockers are resolved.**

### Permitted Tag: v0.9.0-rc1

All firmware, transport, command dispatch, and observability layers are fully
qualified. Two hardware-only blockers are deferred to the next PCB revision.

    git tag -a v0.9.0-rc1 \
      -m "M10 RC1: All firmware layers qualified. Phase D (IC2) and IR (GPIO1) blocked on HW rev."

---
Generated: 2026-10-22 | Evidence root: docs/validation/
