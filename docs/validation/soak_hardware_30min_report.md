# NEXUS Hardware Soak-Test Evidence & Reliability Report

**Overall Verdict: FAIL**

## 1. Acceptance Criteria Evaluation Matrix

| # | Criterion Scope | Classification | Verdict | Evaluation Evidence |
|---|---|---|---|---|
| 10 | **Error Isolation** | Proposed Criterion | **PASS** | Max consecutive invalid envelopes = 2 <= 3 |
| 11 | **Queue Hwm** | Proposed Criterion | **PASS** | Peak queue depth 2/16 within proposed limit of 4 |
| 12 | **Physical Driver** | Proposed Criterion | **PASS** | Physical driver attempts: 769/868 OK (88.59% >= 80.0%) across [526365..2285665] ms |
| 1 | **System Stability** | Firm Requirement | **INCONCLUSIVE** | No boot record (reset_reason=1) observed in log |
| 2 | **Executive Deadlines** | Firm Requirement | **PASS** | dline_misses == 0 across all 359 periodic reports |
| 3 | **Executive Queues** | Firm Requirement | **PASS** | q_overflows == 0 across all 359 periodic reports |
| 4 | **Callback Budget** | Firm Requirement | **PASS** | Peak callback duration 29892 us strictly within 50000 us budget |
| 5 | **Dispatch Latency** | Proposed Criterion | **PASS** | Peak dispatch latency 101721 us bounded by startup quantization allowance |
| 6 | **Transport Queuing** | Firm Requirement | **FAIL** | Transport failures detected: tx_drop=2, tx_fail=0 |
| 7 | **Schema Integrity** | Firm Requirement | **PASS** | 100% schema compliance across 888 envelopes; zero fabricated readings |
| 8 | **Heap Stability** | Firm Requirement | **PASS** | Steady-state heap stable: trend=72.9 B/hr (Net=+224B, Spread=3620B, N=1746, R2=0.00) |
| 9 | **Telemetry Validity** | Proposed Criterion | **PASS** | 788/888 valid envelopes (88.74% >= 85.0% target) |

## 2. Stream-Ordered Sequence & Envelope Metrics

- **Total Captured Envelopes**: 2993
- **Message Breakdown**: {'hb': 1746, 'telem': 888, 'status': 359}
- **Sequence Range**: `852` to `3845`
- **Duplicates Received**: 0
- **Out-of-Order Deliveries**: 0
- **Unobserved MQTT Sequences**: 1 *(Note: Under AUTO routing, envelopes may stream over Serial during MQTT drops)*
- **Implausible Sequence Jumps**: 0

## 3. Sensor Telemetry vs. Physical Driver Acquisition

- **Telemetry Envelopes (0.5 Hz Executive Latch)**: 888
  - Valid Samples: 788
  - Degraded (Omitted Temp/Hum): 100
  - Schema Violations (Fabricated/Malformed): 0
- **Max Consecutive Invalids**: 2 envelopes
- **Temperature Dynamic Range**: 32°C to 32°C
- **Humidity Dynamic Range**: 60% to 63% RH

## 4. Physical Driver Snapshots

- Initial Snapshot: `uptime=526365 ms, ok=232, err=27`
- Final Snapshot:   `uptime=2285665 ms, ok=1001, err=126`

---
*Report generated deterministically by `analyze_nexus_soak.py`.*