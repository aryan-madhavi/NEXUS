# NEXUS Hardware Soak-Test Evidence & Reliability Report

**Overall Verdict: INCONCLUSIVE**

## 1. Acceptance Criteria Evaluation Matrix

| # | Criterion Scope | Classification | Verdict | Evaluation Evidence |
|---|---|---|---|---|
| 10 | **Error Isolation** | Proposed Criterion | **INCONCLUSIVE** | Telemetry envelope count (20) < 100 |
| 11 | **Queue Hwm** | Proposed Criterion | **PASS** | Peak queue depth 2/16 within proposed limit of 4 |
| 12 | **Physical Driver** | Proposed Criterion | **PASS** | Physical driver attempts: 890/900 OK (98.89% >= 80.0%) across [10000..300000] ms |
| 1 | **System Stability** | Firm Requirement | **INCONCLUSIVE** | Observation duration (300.0s) < 1800s |
| 2 | **Executive Deadlines** | Firm Requirement | **PASS** | dline_misses == 0 across all 61 periodic reports |
| 3 | **Executive Queues** | Firm Requirement | **PASS** | q_overflows == 0 across all 61 periodic reports |
| 4 | **Callback Budget** | Firm Requirement | **PASS** | Peak callback duration 15000 us strictly within 50000 us budget |
| 5 | **Dispatch Latency** | Proposed Criterion | **PASS** | Peak dispatch latency 45000 us bounded by startup quantization allowance |
| 6 | **Transport Queuing** | Firm Requirement | **PASS** | tx_drop == 0 and tx_fail == 0 across all 61 periodic reports |
| 7 | **Schema Integrity** | Firm Requirement | **PASS** | 100% schema compliance across 20 envelopes; zero fabricated readings |
| 8 | **Heap Stability** | Firm Requirement | **INCONCLUSIVE** | Insufficient steady-state duration (58 samples, span < 600s) |
| 9 | **Telemetry Validity** | Proposed Criterion | **INCONCLUSIVE** | Telemetry envelope count (20) < 100 |

## 2. Stream-Ordered Sequence & Envelope Metrics

- **Total Captured Envelopes**: 20
- **Message Breakdown**: {'telem': 20}
- **Sequence Range**: `1` to `20`
- **Duplicates Received**: 0
- **Out-of-Order Deliveries**: 0
- **Unobserved MQTT Sequences**: 0 *(Note: Under AUTO routing, envelopes may stream over Serial during MQTT drops)*
- **Implausible Sequence Jumps**: 0

## 3. Sensor Telemetry vs. Physical Driver Acquisition

- **Telemetry Envelopes (0.5 Hz Executive Latch)**: 20
  - Valid Samples: 20
  - Degraded (Omitted Temp/Hum): 0
  - Schema Violations (Fabricated/Malformed): 0
- **Max Consecutive Invalids**: 0 envelopes
- **Temperature Dynamic Range**: 24.5°C to 24.5°C
- **Humidity Dynamic Range**: 55.0% to 55.0% RH

## 4. Physical Driver Snapshots

- Initial Snapshot: `uptime=10000 ms, ok=10, err=0`
- Final Snapshot:   `uptime=300000 ms, ok=900, err=10`

---
*Report generated deterministically by `analyze_nexus_soak.py`.*