#!/usr/bin/env python3
"""
NEXUS Soak-Test Stream-Ordered Evidence Analyzer
Part of the NEXUS Environmental Monitoring Project (ESP-IDF v6.0.1 / FreeRTOS).

Performs rigorous static log analysis on concurrent Serial (UART0) and MQTT telemetry
streams. Enforces modular uint32 sequence tracking, arrival-order preservation,
strict JSON schema validation, snapshot counter monotonicity, phased heap regression,
and structured multi-verdict acceptance criteria.

Exit Codes:
  0: PASS (All firm requirements pass, zero failures)
  1: FAIL (One or more firm requirements fail)
  2: INCONCLUSIVE (Incomplete coverage, missing snapshots, or unobserved streams)
  3: INPUT_ERROR (Invalid CLI arguments, missing input files, self-overwrite risk)
"""

import os
import sys
import re
import json
import argparse
from collections import Counter


MAX_PLAUSIBLE_SEQUENCE_JUMP = 50000
MIN_STEADY_STATE_DURATION_SEC = 600
MIN_STEADY_STATE_SAMPLES = 30
NOMINAL_SOAK_DURATION_SEC = 1800  # 30 minutes


def evaluate_criterion(cond_pass, cond_fail, msg_pass, msg_fail, msg_inconclusive):
    """Helper to return consistent (status, explanation) tuples."""
    if cond_fail:
        return "FAIL", msg_fail
    elif cond_pass:
        return "PASS", msg_pass
    else:
        return "INCONCLUSIVE", msg_inconclusive


class NexusLogAnalyzer:
    """Core analyzer implementing firmware-verified evaluation logic."""

    def __init__(self, serial_log_path, mqtt_log_path):
        self.serial_path = serial_log_path
        self.mqtt_path = mqtt_log_path

        # Raw extraction containers
        self.serial_records = []
        self.mqtt_records = []

        # Sequence state
        self.arrival_stream = []
        self.seen_seqs = set()
        self.duplicate_arrivals = []
        self.out_of_order_arrivals = []
        self.implausible_jumps = []
        self.pending_gaps = set()
        self.max_seen_seq = None
        self.seq_first = None
        self.seq_last = None

        # Telemetry schema state
        self.type_counts = Counter()
        self.telem_valid = 0
        self.telem_degraded = 0
        self.telem_missing_valid = 0
        self.telem_malformed_valid = 0
        self.telem_invalid_types = 0
        self.fabricated_readings = 0
        self.malformed_envelopes = 0
        self.unsupported_versions = 0
        self.consecutive_invalids = 0
        self.max_consecutive_invalids = 0
        self.dht_temps = []
        self.dht_hums = []

        # Serial snapshot state
        self.reset_reasons = []
        self.exec_snapshots = []
        self.conn_snapshots = []
        self.driver_snapshots = []
        self.heap_samples = []  # (uptime_ms, free_heap)
        self.exec_counter_regressions = 0
        self.conn_counter_regressions = 0
        self.driver_counter_regressions = 0

        # Acceptance verdicts
        self.criteria_results = {}
        self.overall_verdict = "INCONCLUSIVE"

    def parse_mqtt_stream(self):
        """Parse MQTT stream strictly preserving arrival order and validating schema."""
        if not self.mqtt_path or not os.path.exists(self.mqtt_path):
            return

        with open(self.mqtt_path, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                self.mqtt_records.append(line)
                match = re.search(r"\{.*\}", line)
                if not match:
                    continue

                raw_json = match.group(0)
                try:
                    pkt = json.loads(raw_json)
                except Exception:
                    self.malformed_envelopes += 1
                    continue

                if not isinstance(pkt, dict):
                    self.malformed_envelopes += 1
                    continue

                ver = pkt.get("ver")
                dev = pkt.get("dev")
                seq = pkt.get("seq")
                msg_type = pkt.get("type")
                uptime = pkt.get("uptime")

                # Strict type enforcement: in Python, isinstance(True, int) is True!
                if type(ver) is not int or ver != 1:
                    self.unsupported_versions += 1
                    self.malformed_envelopes += 1
                    continue

                if type(dev) is not str or len(dev) == 0:
                    self.malformed_envelopes += 1
                    continue

                if type(seq) is not int or seq < 0:
                    self.malformed_envelopes += 1
                    continue

                if type(msg_type) is not str or msg_type not in [
                    "hb",
                    "telem",
                    "status",
                    "event",
                ]:
                    self.malformed_envelopes += 1
                    continue

                if type(uptime) is not int or uptime < 0:
                    self.malformed_envelopes += 1
                    continue

                # --- uint32 Modulo Sequence Processing ---
                if self.seq_first is None:
                    self.seq_first = seq

                if seq in self.seen_seqs:
                    self.duplicate_arrivals.append((idx, seq))
                else:
                    if self.max_seen_seq is None:
                        self.max_seen_seq = seq
                    else:
                        fwd_dist = (seq - self.max_seen_seq) & 0xFFFFFFFF
                        back_dist = (self.max_seen_seq - seq) & 0xFFFFFFFF

                        if fwd_dist < 0x80000000:
                            # Forward progress
                            if fwd_dist > 1:
                                if fwd_dist <= MAX_PLAUSIBLE_SEQUENCE_JUMP:
                                    for step in range(1, fwd_dist):
                                        self.pending_gaps.add(
                                            (self.max_seen_seq + step) & 0xFFFFFFFF
                                        )
                                else:
                                    self.implausible_jumps.append(
                                        (self.max_seen_seq, seq, fwd_dist)
                                    )
                            self.max_seen_seq = seq
                        else:
                            # Out-of-order arrival
                            self.out_of_order_arrivals.append(
                                (idx, seq, self.max_seen_seq, back_dist)
                            )
                            if seq in self.pending_gaps:
                                self.pending_gaps.remove(seq)

                    self.seen_seqs.add(seq)

                self.seq_last = seq
                self.arrival_stream.append((idx, seq, msg_type, pkt))
                self.type_counts[msg_type] += 1

                # --- Telemetry Schema Type & Omission Validation ---
                if msg_type == "telem":
                    ldr = pkt.get("ldr")
                    x0 = pkt.get("x0")

                    if type(ldr) not in (int, float) or type(ldr) is bool:
                        self.telem_invalid_types += 1
                    if type(x0) not in (int, float) or type(x0) is bool:
                        self.telem_invalid_types += 1

                    if "dht_valid" not in pkt:
                        self.telem_missing_valid += 1
                        self.consecutive_invalids += 1
                    else:
                        dht_val = pkt["dht_valid"]
                        if type(dht_val) is not bool:
                            self.telem_malformed_valid += 1
                            self.consecutive_invalids += 1
                        elif dht_val is True:
                            t = pkt.get("temp")
                            h = pkt.get("hum")
                            t_ok = (
                                type(t) in (int, float)
                                and type(t) is not bool
                            )
                            h_ok = (
                                type(h) in (int, float)
                                and type(h) is not bool
                            )

                            if t_ok and h_ok:
                                self.telem_valid += 1
                                self.consecutive_invalids = 0
                                self.dht_temps.append(t)
                                self.dht_hums.append(h)
                            else:
                                self.telem_invalid_types += 1
                                self.consecutive_invalids += 1
                        else:
                            # dht_val is False: temp and hum MUST be omitted
                            if "temp" in pkt or "hum" in pkt:
                                self.fabricated_readings += 1
                                self.consecutive_invalids += 1
                            else:
                                self.telem_degraded += 1
                                self.consecutive_invalids += 1

                    if self.consecutive_invalids > self.max_consecutive_invalids:
                        self.max_consecutive_invalids = self.consecutive_invalids

    def parse_serial_stream(self):
        """Parse raw serial console records for executive, connection, and driver snapshots."""
        if not self.serial_path or not os.path.exists(self.serial_path):
            return

        with open(self.serial_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                self.serial_records.append(line)

                # Reset reason
                m_rst = re.search(r"(?:reset_reason|nexus_main.*son)=(\d+)", line)
                if m_rst:
                    self.reset_reasons.append(int(m_rst.group(1)))

                # Executive stats
                m_exec = re.search(
                    r"ticks=(\d+)\s+dispatched=(\d+)\s+completed=(\d+)\s+failed=(\d+)\s+dline_misses=(\d+)\s+q_overflows=(\d+).*max_lat_us=(\d+)\s+max_dur_us=(\d+)",
                    line,
                )
                if m_exec:
                    snap = {
                        "ticks": int(m_exec.group(1)),
                        "disp": int(m_exec.group(2)),
                        "comp": int(m_exec.group(3)),
                        "fail": int(m_exec.group(4)),
                        "dl_miss": int(m_exec.group(5)),
                        "q_ovf": int(m_exec.group(6)),
                        "lat": int(m_exec.group(7)),
                        "dur": int(m_exec.group(8)),
                    }
                    if self.exec_snapshots:
                        prev = self.exec_snapshots[-1]
                        if (
                            snap["disp"] < prev["disp"]
                            or snap["comp"] < prev["comp"]
                            or snap["ticks"] < prev["ticks"]
                        ):
                            self.exec_counter_regressions += 1
                    self.exec_snapshots.append(snap)

                # Connection stats
                m_conn = re.search(
                    r"tx_enq=(\d+)\s+tx_disp=(\d+)\s+tx_drop=(\d+)\s+tx_fail=(\d+)\s+q_depth=(\d+)\s+q_hwm=(\d+)",
                    line,
                )
                if m_conn:
                    snap = {
                        "enq": int(m_conn.group(1)),
                        "disp": int(m_conn.group(2)),
                        "drop": int(m_conn.group(3)),
                        "fail": int(m_conn.group(4)),
                        "depth": int(m_conn.group(5)),
                        "hwm": int(m_conn.group(6)),
                    }
                    if self.conn_snapshots:
                        prev = self.conn_snapshots[-1]
                        if (
                            snap["enq"] < prev["enq"]
                            or snap["disp"] < prev["disp"]
                        ):
                            self.conn_counter_regressions += 1
                    self.conn_snapshots.append(snap)

                # DHT11 driver snapshots
                m_drv = re.search(
                    r"\((\d+)\)\s+nexus_dht11:.*total_ok=(\d+),\s*total_err=(\d+)",
                    line,
                )
                if m_drv:
                    snap = {
                        "uptime": int(m_drv.group(1)),
                        "ok": int(m_drv.group(2)),
                        "err": int(m_drv.group(3)),
                    }
                    if self.driver_snapshots:
                        prev = self.driver_snapshots[-1]
                        if (
                            snap["ok"] < prev["ok"]
                            or snap["err"] < prev["err"]
                            or snap["uptime"] < prev["uptime"]
                        ):
                            self.driver_counter_regressions += 1
                    self.driver_snapshots.append(snap)

                # Free heap samples
                m_heap = re.search(r"uptime_ms=(\d+)\s+free_heap=(\d+)", line)
                if m_heap:
                    self.heap_samples.append(
                        (int(m_heap.group(1)), int(m_heap.group(2)))
                    )

    def evaluate_acceptance(self):
        """Evaluate all criteria with explicit firm vs proposed distinctions."""
        # 1. System Stability (Firm Req)
        uptimes = []
        if self.heap_samples:
            uptimes.append(self.heap_samples[-1][0])
        if self.exec_snapshots:
            uptimes.append(self.exec_snapshots[-1]["ticks"] * 100)
        if self.driver_snapshots:
            uptimes.append(self.driver_snapshots[-1]["uptime"])
        if self.arrival_stream:
            uptimes.append(self.arrival_stream[-1][3].get("uptime", 0))
        max_uptime_ms = max(uptimes) if uptimes else 0

        if len(self.reset_reasons) == 0:
            v1, m1 = (
                "INCONCLUSIVE",
                "No boot record (reset_reason=1) observed in log",
            )
        elif len(self.reset_reasons) > 1:
            v1, m1 = (
                "FAIL",
                f"Multiple reset events recorded: {self.reset_reasons}",
            )
        elif self.reset_reasons[0] != 1:
            v1, m1 = (
                "FAIL",
                f"Non-poweron reset reason: {self.reset_reasons[0]} (panic/wdt/brownout)",
            )
        elif self.exec_counter_regressions > 0 or self.conn_counter_regressions > 0:
            v1, m1 = (
                "FAIL",
                f"Detected cumulative counter regressions ({self.exec_counter_regressions} exec, {self.conn_counter_regressions} conn) indicating unhandled reset or sequence anomaly",
            )
        elif max_uptime_ms < (NOMINAL_SOAK_DURATION_SEC - 30) * 1000:
            v1, m1 = (
                "INCONCLUSIVE",
                f"Observation duration ({max_uptime_ms/1000:.1f}s) < {NOMINAL_SOAK_DURATION_SEC - 30}s",
            )
        else:
            v1, m1 = (
                "PASS",
                f"Cold boot reset_reason=1 confirmed; monotonic uptime reached {max_uptime_ms/1000:.1f}s",
            )
        self.criteria_results["1_system_stability"] = (
            "Firm Requirement",
            v1,
            m1,
        )

        # 2. Executive Deadlines (Firm Req)
        if not self.exec_snapshots:
            v2, m2 = (
                "INCONCLUSIVE",
                "No exec_stats snapshots captured on Serial",
            )
        else:
            peak_dl = max(s["dl_miss"] for s in self.exec_snapshots)
            if peak_dl > 0:
                v2, m2 = "FAIL", f"Peak deadline misses = {peak_dl}"
            elif self.exec_counter_regressions > 0:
                v2, m2 = (
                    "INCONCLUSIVE",
                    f"Detected {self.exec_counter_regressions} counter regressions in exec_stats",
                )
            else:
                v2, m2 = (
                    "PASS",
                    f"dline_misses == 0 across all {len(self.exec_snapshots)} periodic reports",
                )
        self.criteria_results["2_executive_deadlines"] = (
            "Firm Requirement",
            v2,
            m2,
        )

        # 3. Executive Queues (Firm Req)
        if not self.exec_snapshots:
            v3, m3 = (
                "INCONCLUSIVE",
                "No exec_stats snapshots captured on Serial",
            )
        else:
            peak_qo = max(s["q_ovf"] for s in self.exec_snapshots)
            if peak_qo > 0:
                v3, m3 = "FAIL", f"Peak queue overflows = {peak_qo}"
            else:
                v3, m3 = (
                    "PASS",
                    f"q_overflows == 0 across all {len(self.exec_snapshots)} periodic reports",
                )
        self.criteria_results["3_executive_queues"] = (
            "Firm Requirement",
            v3,
            m3,
        )

        # 4. Callback Execution Budget (Firm Req)
        if not self.exec_snapshots:
            v4, m4 = (
                "INCONCLUSIVE",
                "No exec_stats snapshots captured on Serial",
            )
        else:
            peak_dur = max(s["dur"] for s in self.exec_snapshots)
            if peak_dur >= 50000:
                v4, m4 = (
                    "FAIL",
                    f"Peak callback duration {peak_dur} us >= 50000 us budget",
                )
            else:
                v4, m4 = (
                    "PASS",
                    f"Peak callback duration {peak_dur} us strictly within 50000 us budget",
                )
        self.criteria_results["4_callback_budget"] = (
            "Firm Requirement",
            v4,
            m4,
        )

        # 5. Dispatch Latency (Proposed Criterion)
        if not self.exec_snapshots:
            v5, m5 = (
                "INCONCLUSIVE",
                "No exec_stats snapshots captured on Serial",
            )
        else:
            peak_lat = max(s["lat"] for s in self.exec_snapshots)
            if peak_lat > 110000:
                v5, m5 = (
                    "FAIL",
                    f"Peak latency {peak_lat} us exceeded 110000 us quantization threshold",
                )
            else:
                v5, m5 = (
                    "PASS",
                    f"Peak dispatch latency {peak_lat} us bounded by startup quantization allowance",
                )
        self.criteria_results["5_dispatch_latency"] = (
            "Proposed Criterion",
            v5,
            m5,
        )

        # 6. Transport Transmission Integrity (Firm Req)
        if not self.conn_snapshots:
            v6, m6 = (
                "INCONCLUSIVE",
                "No conn_stats snapshots captured on Serial",
            )
        else:
            peak_drop = max(s["drop"] for s in self.conn_snapshots)
            peak_fail = max(s["fail"] for s in self.conn_snapshots)
            if peak_drop > 0 or peak_fail > 0:
                v6, m6 = (
                    "FAIL",
                    f"Transport failures detected: tx_drop={peak_drop}, tx_fail={peak_fail}",
                )
            elif self.conn_counter_regressions > 0:
                v6, m6 = (
                    "INCONCLUSIVE",
                    f"Detected {self.conn_counter_regressions} counter regressions in conn_stats",
                )
            else:
                v6, m6 = (
                    "PASS",
                    f"tx_drop == 0 and tx_fail == 0 across all {len(self.conn_snapshots)} periodic reports",
                )
        self.criteria_results["6_transport_queuing"] = (
            "Firm Requirement",
            v6,
            m6,
        )

        # 7. Telemetry Schema & Omission Integrity (Firm Req)
        telem_total = (
            self.telem_valid
            + self.telem_degraded
            + self.telem_missing_valid
            + self.telem_malformed_valid
            + self.telem_invalid_types
        )
        if telem_total == 0:
            v7, m7 = (
                "INCONCLUSIVE",
                "MQTT telemetry stream unobserved or zero telem envelopes captured",
            )
        elif (
            self.fabricated_readings > 0
            or self.telem_missing_valid > 0
            or self.telem_malformed_valid > 0
            or self.telem_invalid_types > 0
            or self.malformed_envelopes > 0
        ):
            v7, m7 = (
                "FAIL",
                f"Schema violations: {self.fabricated_readings} fabricated readings, {self.telem_missing_valid} missing flags, {self.telem_malformed_valid} malformed flags, {self.telem_invalid_types} invalid field types, {self.malformed_envelopes} malformed JSON lines",
            )
        else:
            v7, m7 = (
                "PASS",
                f"100% schema compliance across {telem_total} envelopes; zero fabricated readings",
            )
        self.criteria_results["7_schema_integrity"] = (
            "Firm Requirement",
            v7,
            m7,
        )

        # 8. Steady-State Heap Stability (Firm Req)
        steady_samples = [
            h for h in self.heap_samples if h[0] >= 15000
        ]
        if (
            len(steady_samples) < MIN_STEADY_STATE_SAMPLES
            or not self.heap_samples
            or (steady_samples[-1][0] - steady_samples[0][0])
            < (MIN_STEADY_STATE_DURATION_SEC * 1000)
        ):
            v8, m8 = (
                "INCONCLUSIVE",
                f"Insufficient steady-state duration ({len(steady_samples)} samples, span < {MIN_STEADY_STATE_DURATION_SEC}s)",
            )
        else:
            # OLS linear regression slope
            times_sec = [(h[0] - steady_samples[0][0]) / 1000.0 for h in steady_samples]
            heaps = [h[1] for h in steady_samples]
            mean_t = sum(times_sec) / len(times_sec)
            mean_h = sum(heaps) / len(heaps)
            num = sum((t - mean_t) * (h - mean_h) for t, h in zip(times_sec, heaps))
            den = sum((t - mean_t) ** 2 for t in times_sec)
            slope_bps = (num / den) if den != 0 else 0.0
            slope_bph = slope_bps * 3600.0
            spread = max(heaps) - min(heaps)
            net_change = heaps[-1] - heaps[0]

            # R-squared calculation
            ss_tot = sum((h - mean_h) ** 2 for h in heaps)
            ss_res = sum(
                (h - (mean_h + slope_bps * (t - mean_t))) ** 2
                for t, h in zip(times_sec, heaps)
            )
            r2 = (1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

            if (slope_bph < -50.0 and r2 > 0.7) or (net_change < -500 and slope_bph < -20.0):
                v8, m8 = (
                    "FAIL",
                    f"Statistically significant steady-state downward trend: {slope_bph:.1f} B/hr (Net={net_change:+d}B, R2={r2:.2f})",
                )
            else:
                v8, m8 = (
                    "PASS",
                    f"Steady-state heap stable: trend={slope_bph:.1f} B/hr (Net={net_change:+d}B, Spread={spread}B, N={len(steady_samples)}, R2={r2:.2f})",
                )
        self.criteria_results["8_heap_stability"] = (
            "Firm Requirement",
            v8,
            m8,
        )

        # 9. Telemetry Validity Percentage (Proposed Criterion)
        if telem_total < 100:
            v9, m9 = (
                "INCONCLUSIVE",
                f"Telemetry envelope count ({telem_total}) < 100",
            )
        else:
            pct = (self.telem_valid / telem_total) * 100.0
            if pct < 85.0:
                v9, m9 = (
                    "FAIL",
                    f"Valid telemetry envelopes {pct:.2f}% < 85.0% proposed target",
                )
            else:
                v9, m9 = (
                    "PASS",
                    f"{self.telem_valid}/{telem_total} valid envelopes ({pct:.2f}% >= 85.0% target)",
                )
        self.criteria_results["9_telemetry_validity"] = (
            "Proposed Criterion",
            v9,
            m9,
        )

        # 10. Error Run Isolation (Proposed Criterion)
        if telem_total < 100:
            v10, m10 = (
                "INCONCLUSIVE",
                f"Telemetry envelope count ({telem_total}) < 100",
            )
        elif self.max_consecutive_invalids > 3:
            v10, m10 = (
                "FAIL",
                f"Max consecutive invalid envelopes = {self.max_consecutive_invalids} > 3",
            )
        else:
            v10, m10 = (
                "PASS",
                f"Max consecutive invalid envelopes = {self.max_consecutive_invalids} <= 3",
            )
        self.criteria_results["10_error_isolation"] = (
            "Proposed Criterion",
            v10,
            m10,
        )

        # 11. Transmit Queue High-Water Mark (Proposed Criterion)
        if not self.conn_snapshots:
            v11, m11 = (
                "INCONCLUSIVE",
                "No conn_stats snapshots captured on Serial",
            )
        else:
            peak_hwm = max(s["hwm"] for s in self.conn_snapshots)
            if peak_hwm > 4:
                v11, m11 = (
                    "FAIL",
                    f"Peak queue depth {peak_hwm}/16 exceeded proposed limit of 4",
                )
            else:
                v11, m11 = (
                    "PASS",
                    f"Peak queue depth {peak_hwm}/16 within proposed limit of 4",
                )
        self.criteria_results["11_queue_hwm"] = (
            "Proposed Criterion",
            v11,
            m11,
        )

        # 12. Physical Driver Success Ratio (Proposed Criterion)
        if len(self.driver_snapshots) < 2:
            v12, m12 = (
                "INCONCLUSIVE",
                f"Only {len(self.driver_snapshots)} driver snapshots observed (rate-limiting horizon)",
            )
        elif self.driver_counter_regressions > 0:
            v12, m12 = (
                "INCONCLUSIVE",
                f"Detected {self.driver_counter_regressions} counter regressions in driver logs",
            )
        else:
            first = self.driver_snapshots[0]
            last = self.driver_snapshots[-1]
            d_ok = last["ok"] - first["ok"]
            d_err = last["err"] - first["err"]
            tot_att = d_ok + d_err
            if tot_att == 0:
                v12, m12 = (
                    "INCONCLUSIVE",
                    "Zero physical acquisition attempts logged across boundary snapshots",
                )
            else:
                drv_pct = (d_ok / tot_att) * 100.0
                if drv_pct < 80.0:
                    v12, m12 = (
                        "FAIL",
                        f"Physical driver success {drv_pct:.2f}% < 80.0% proposed target",
                    )
                else:
                    v12, m12 = (
                        "PASS",
                        f"Physical driver attempts: {d_ok}/{tot_att} OK ({drv_pct:.2f}% >= 80.0%) across [{first['uptime']}..{last['uptime']}] ms",
                    )
        self.criteria_results["12_physical_driver"] = (
            "Proposed Criterion",
            v12,
            m12,
        )

        # --- Compute Overall Verdict ---
        firm_verdicts = [
            res[1]
            for key, res in self.criteria_results.items()
            if res[0] == "Firm Requirement"
        ]
        if any(v == "FAIL" for v in firm_verdicts):
            self.overall_verdict = "FAIL"
        elif any(v == "INCONCLUSIVE" for v in firm_verdicts):
            self.overall_verdict = "INCONCLUSIVE"
        else:
            self.overall_verdict = "PASS"

    def generate_json_report(self):
        """Produce machine-readable dictionary representation."""
        firm_pass = sum(
            1
            for v in self.criteria_results.values()
            if v[0] == "Firm Requirement" and v[1] == "PASS"
        )
        firm_fail = sum(
            1
            for v in self.criteria_results.values()
            if v[0] == "Firm Requirement" and v[1] == "FAIL"
        )
        firm_inc = sum(
            1
            for v in self.criteria_results.values()
            if v[0] == "Firm Requirement" and v[1] == "INCONCLUSIVE"
        )
        prop_pass = sum(
            1
            for v in self.criteria_results.values()
            if v[0] == "Proposed Criterion" and v[1] == "PASS"
        )
        prop_fail = sum(
            1
            for v in self.criteria_results.values()
            if v[0] == "Proposed Criterion" and v[1] == "FAIL"
        )
        prop_inc = sum(
            1
            for v in self.criteria_results.values()
            if v[0] == "Proposed Criterion" and v[1] == "INCONCLUSIVE"
        )

        return {
            "metadata": {
                "serial_path": self.serial_path,
                "mqtt_path": self.mqtt_path,
                "schema_version": "1.1.0",
            },
            "overall_verdict": self.overall_verdict,
            "summary": {
                "overall_verdict": self.overall_verdict,
                "firm_requirements": {
                    "total": firm_pass + firm_fail + firm_inc,
                    "passed": firm_pass,
                    "failed": firm_fail,
                    "inconclusive": firm_inc,
                },
                "proposed_criteria": {
                    "total": prop_pass + prop_fail + prop_inc,
                    "passed": prop_pass,
                    "failed": prop_fail,
                    "inconclusive": prop_inc,
                },
            },
            "criteria": {
                k: {"classification": v[0], "verdict": v[1], "message": v[2]}
                for k, v in self.criteria_results.items()
            },
            "sequence_metrics": {
                "total_envelopes": len(self.arrival_stream),
                "seq_first": self.seq_first,
                "seq_last": self.seq_last,
                "duplicate_count": len(self.duplicate_arrivals),
                "out_of_order_count": len(self.out_of_order_arrivals),
                "unobserved_mqtt_count": len(self.pending_gaps),
                "implausible_jumps": self.implausible_jumps,
            },
            "telemetry_metrics": {
                "type_breakdown": dict(self.type_counts),
                "valid_count": self.telem_valid,
                "degraded_count": self.telem_degraded,
                "missing_valid_key": self.telem_missing_valid,
                "malformed_valid_key": self.telem_malformed_valid,
                "invalid_field_types": self.telem_invalid_types,
                "fabricated_readings": self.fabricated_readings,
                "max_consecutive_invalids": self.max_consecutive_invalids,
            },
            "serial_metrics": {
                "exec_snapshots_count": len(self.exec_snapshots),
                "conn_snapshots_count": len(self.conn_snapshots),
                "driver_snapshots_count": len(self.driver_snapshots),
                "heap_samples_count": len(self.heap_samples),
                "reset_reasons": self.reset_reasons,
            },
        }

    def generate_markdown_report(self):
        """Format human-readable Markdown summary."""
        lines = [
            "# NEXUS Hardware Soak-Test Evidence & Reliability Report\n",
            f"**Overall Verdict: {self.overall_verdict}**\n",
            "## 1. Acceptance Criteria Evaluation Matrix\n",
            "| # | Criterion Scope | Classification | Verdict | Evaluation Evidence |",
            "|---|---|---|---|---|",
        ]
        for key in sorted(self.criteria_results.keys()):
            classification, verdict, msg = self.criteria_results[key]
            clean_name = key.split("_", 1)[1].replace("_", " ").title()
            lines.append(
                f"| {key.split('_')[0]} | **{clean_name}** | {classification} | **{verdict}** | {msg} |"
            )

        lines.extend(
            [
                "\n## 2. Stream-Ordered Sequence & Envelope Metrics\n",
                f"- **Total Captured Envelopes**: {len(self.arrival_stream)}",
                f"- **Message Breakdown**: {dict(self.type_counts)}",
                f"- **Sequence Range**: `{self.seq_first}` to `{self.seq_last}`",
                f"- **Duplicates Received**: {len(self.duplicate_arrivals)}",
                f"- **Out-of-Order Deliveries**: {len(self.out_of_order_arrivals)}",
                f"- **Unobserved MQTT Sequences**: {len(self.pending_gaps)} *(Note: Under AUTO routing, envelopes may stream over Serial during MQTT drops)*",
                f"- **Implausible Sequence Jumps**: {len(self.implausible_jumps)}",
                "\n## 3. Sensor Telemetry vs. Physical Driver Acquisition\n",
                f"- **Telemetry Envelopes (0.5 Hz Executive Latch)**: {self.telem_valid + self.telem_degraded + self.telem_missing_valid + self.telem_malformed_valid}",
                f"  - Valid Samples: {self.telem_valid}",
                f"  - Degraded (Omitted Temp/Hum): {self.telem_degraded}",
                f"  - Schema Violations (Fabricated/Malformed): {self.fabricated_readings + self.telem_missing_valid + self.telem_malformed_valid + self.telem_invalid_types}",
                f"- **Max Consecutive Invalids**: {self.max_consecutive_invalids} envelopes",
            ]
        )

        if self.dht_temps:
            lines.append(
                f"- **Temperature Dynamic Range**: {min(self.dht_temps)}°C to {max(self.dht_temps)}°C"
            )
        if self.dht_hums:
            lines.append(
                f"- **Humidity Dynamic Range**: {min(self.dht_hums)}% to {max(self.dht_hums)}% RH"
            )

        if len(self.driver_snapshots) >= 2:
            f_drv = self.driver_snapshots[0]
            l_drv = self.driver_snapshots[-1]
            lines.extend(
                [
                    "\n## 4. Physical Driver Snapshots\n",
                    f"- Initial Snapshot: `uptime={f_drv['uptime']} ms, ok={f_drv['ok']}, err={f_drv['err']}`",
                    f"- Final Snapshot:   `uptime={l_drv['uptime']} ms, ok={l_drv['ok']}, err={l_drv['err']}`",
                ]
            )

        lines.append("\n---\n*Report generated deterministically by `analyze_nexus_soak.py`.*")
        return "\n".join(lines)


class NexusAnalyzerArgParser(argparse.ArgumentParser):
    """Custom parser ensuring CLI usage errors exit with code 3 (INPUT_ERROR)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"[ERROR] {self.prog}: error: {message}", file=sys.stderr)
        sys.exit(3)


def build_arg_parser():
    parser = NexusAnalyzerArgParser(
        description="NEXUS Soak-Test Log & Evidence Analyzer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "serial_log",
        nargs="?",
        default=None,
        help="Path to captured serial console log file (positional).",
    )
    parser.add_argument(
        "mqtt_log",
        nargs="?",
        default=None,
        help="Path to captured MQTT telemetry log file (optional positional).",
    )
    parser.add_argument(
        "--serial",
        help="Path to captured serial console log file.",
    )
    parser.add_argument(
        "--mqtt",
        help="Path to captured MQTT telemetry log file.",
    )
    parser.add_argument(
        "--json-out",
        help="Destination path for machine-readable JSON output.",
    )
    parser.add_argument(
        "--md-out",
        help="Destination path for formatted Markdown summary output.",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    serial_path = args.serial or args.serial_log
    mqtt_path = args.mqtt or args.mqtt_log

    if not serial_path:
        parser.error("Serial log path is required (pass serial_log positional or --serial).")

    # Input validation
    for path in [serial_path, mqtt_path]:
        if path:
            if not os.path.exists(path):
                print(f"[ERROR] Input log file not found: {path}", file=sys.stderr)
                sys.exit(3)
            if not os.path.isfile(path):
                print(f"[ERROR] Path is not a regular file: {path}", file=sys.stderr)
                sys.exit(3)

    # Collision guard
    for out in [args.json_out, args.md_out]:
        if out and out in [serial_path, mqtt_path]:
            print(
                f"[ERROR] Output path cannot overwrite input log file: {out}",
                file=sys.stderr,
            )
            sys.exit(3)

    analyzer = NexusLogAnalyzer(serial_path, mqtt_path)
    analyzer.parse_serial_stream()
    analyzer.parse_mqtt_stream()
    analyzer.evaluate_acceptance()

    md_report = analyzer.generate_markdown_report()
    json_report = analyzer.generate_json_report()

    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md_report)
    else:
        print(md_report)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(json_report, f, indent=2)

    # Deterministic exit codes
    if analyzer.overall_verdict == "PASS":
        sys.exit(0)
    elif analyzer.overall_verdict == "FAIL":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
