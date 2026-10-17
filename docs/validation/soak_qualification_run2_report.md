# NEXUS Hardware Soak-Test Evidence & Reliability Report

**Overall Verdict: PASS**

## 1. Acceptance Criteria Evaluation Matrix

| # | Criterion Scope | Classification | Verdict | Evaluation Evidence |
|---|---|---|---|---|
| 10 | **Error Isolation** | Proposed Criterion | **PASS** | Max consecutive invalid envelopes = 2 <= 3 |
| 11 | **Queue Hwm** | Proposed Criterion | **PASS** | Peak queue depth 2/16 within proposed limit of 4 |
| 12 | **Physical Driver** | Proposed Criterion | **PASS** | Physical driver attempts: 782/877 OK (89.17% >= 80.0%) across [865..1788455] ms |
| 1 | **System Stability** | Firm Requirement | **PASS** | Cold boot reset_reason=1 confirmed; monotonic uptime reached 1798.9s |
| 2 | **Executive Deadlines** | Firm Requirement | **PASS** | dline_misses == 0 across all 357 periodic reports |
| 3 | **Executive Queues** | Firm Requirement | **PASS** | q_overflows == 0 across all 357 periodic reports |
| 4 | **Callback Budget** | Firm Requirement | **PASS** | Peak callback duration 29856 us strictly within 50000 us budget |
| 5 | **Dispatch Latency** | Proposed Criterion | **PASS** | Peak dispatch latency 101600 us bounded by startup quantization allowance |
| 6 | **Transport Queuing** | Firm Requirement | **PASS** | tx_drop == 0 and tx_fail == 0 across all 357 periodic reports |
| 7 | **Schema Integrity** | Firm Requirement | **PASS** | 100% schema compliance across 880 envelopes; zero fabricated readings |
| 8 | **Heap Stability** | Firm Requirement | **PASS** | Steady-state heap stable: trend=199.4 B/hr (Net=-52B, Spread=6076B, N=1718, R2=0.00) |
| 9 | **Telemetry Validity** | Proposed Criterion | **PASS** | 784/880 valid envelopes (89.09% >= 85.0% target) |

## 2. Stream-Ordered Sequence & Envelope Metrics

- **Total Captured Envelopes**: 2966
- **Message Breakdown**: {'telem': 880, 'hb': 1731, 'status': 355}
- **Sequence Range**: `15` to `2973`
- **Duplicates Received**: 7
- **Out-of-Order Deliveries**: 0
- **Unobserved MQTT Sequences**: 0 *(Note: Under AUTO routing, envelopes may stream over Serial during MQTT drops)*
- **Implausible Sequence Jumps**: 0

## 3. Sensor Telemetry vs. Physical Driver Acquisition

- **Telemetry Envelopes (0.5 Hz Executive Latch)**: 880
  - Valid Samples: 784
  - Degraded (Omitted Temp/Hum): 96
  - Schema Violations (Fabricated/Malformed): 0
- **Max Consecutive Invalids**: 2 envelopes
- **Temperature Dynamic Range**: 31°C to 31°C
- **Humidity Dynamic Range**: 74% to 74% RH

## 4. Physical Driver Snapshots

- Initial Snapshot: `uptime=865 ms, ok=1, err=0`
- Final Snapshot:   `uptime=1788455 ms, ok=783, err=95`

---
*Report generated deterministically by `analyze_nexus_soak.py`.*