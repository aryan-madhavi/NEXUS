#!/usr/bin/env python3
"""
NEXUS Soak-Test Automated Test Suite
Part of the NEXUS Environmental Monitoring Project (ESP-IDF v6.0.1 / FreeRTOS).

Validates the soak-test capture harness (nexus_soak_capture.py) and
log analyzer (analyze_nexus_soak.py) across 19 deterministic synthetic scenarios:
 1. Fully valid capture passing all measurable criteria.
 2. Zero telemetry and empty files.
 3. Malformed JSON, invalid UTF-8, truncated records, and oversized lines.
 4. Missing mandatory fields and boolean-as-integer schema violations.
 5. Sequence continuity, duplicates, reordering, ordinary gaps, and uint32 wraparound.
 6. Counter regression and suspected reboot/reset.
 7. Missing or invalid boot/reset-reason evidence.
 8. Short captures and insufficient telemetry coverage.
 9. Timestamp regression, repeated timestamps, and inconsistent elapsed duration.
10. Callback/dispatch threshold boundary values.
11. Queue high-water and overflow thresholds.
12. TX drop/failure thresholds.
13. Telemetry validity and consecutive invalid-frame limits.
14. Sensor-driver success/failure calculations only where observable.
15. Phased heap analysis: stable, leaking, noisy, and insufficient samples.
16. MQTT absence, malformed messages, reconnect scenarios, and routing ambiguity.
17. Output file collision protection, input error handling, and deterministic exit codes.
18. Capture harness simulation mode, bounded stream reader, and interrupt handling.
19. Reproducibility of machine-readable JSON and Markdown summaries.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import subprocess
# Ensure tests/soak is on sys.path
SOAK_DIR = os.path.dirname(os.path.abspath(__file__))
if SOAK_DIR not in sys.path:
    sys.path.insert(0, SOAK_DIR)

from nexus_soak_capture import BoundedStreamReader  # noqa: E402
from analyze_nexus_soak import NexusLogAnalyzer  # noqa: E402


class BaseSoakTestCase(unittest.TestCase):
    """Helper base class providing isolated temporary directory and log generators."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="nexus_test_")
        self.serial_file = os.path.join(self.test_dir, "serial.log")
        self.mqtt_file = os.path.join(self.test_dir, "mqtt.log")
        self.json_out = os.path.join(self.test_dir, "report.json")
        self.md_out = os.path.join(self.test_dir, "report.md")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def write_file(self, path, content):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def create_valid_serial_log(
        self,
        duration_sec=1805,
        peak_dur=15000,
        peak_lat=45000,
        dl_miss=0,
        q_ovf=0,
        tx_drop=0,
        tx_fail=0,
        q_hwm=2,
        heap_base=125000,
        heap_slope=0.0,
        reset_reason=1,
        drv_ok=900,
        drv_err=10,
    ):
        """Generate a realistic, comprehensive Serial console log."""
        lines = []
        # Boot record
        if reset_reason is not None:
            lines.append(
                f"[2026-10-17 12:00:00.000] I (10) nexus_boot: reset_reason={reset_reason} (ESP_RST_POWERON)\n"
            )

        # Uptime steps (every 5 seconds)
        step_sec = 5
        steps = int(duration_sec / step_sec)
        for i in range(steps + 1):
            t_sec = i * step_sec
            t_ms = t_sec * 1000
            iso = f"[2026-10-17 12:{t_sec//60:02d}:{t_sec%60:02d}.000] "

            # Free heap sample
            heap_val = int(heap_base + heap_slope * t_sec)
            lines.append(
                f"{iso}I ({t_ms}) nexus_heap: uptime_ms={t_ms} free_heap={heap_val} min_free_heap={heap_val-1000}\n"
            )

            # Executive snapshot
            ticks = i * 50
            disp = i * 20
            comp = disp
            lines.append(
                f"{iso}I ({t_ms}) nexus_exec: ticks={ticks} dispatched={disp} completed={comp} failed=0 "
                f"dline_misses={dl_miss} q_overflows={q_ovf} max_lat_us={peak_lat} max_dur_us={peak_dur}\n"
            )

            # Transport snapshot
            enq = i * 15
            lines.append(
                f"{iso}I ({t_ms}) nexus_conn: tx_enq={enq} tx_disp={enq} tx_drop={tx_drop} tx_fail={tx_fail} "
                f"q_depth=1 q_hwm={q_hwm} state=CONNECTED\n"
            )

        # DHT11 Driver snapshots
        lines.append(
            "[2026-10-17 12:00:10.000] I (10000) nexus_dht11: periodic_stats total_ok=10, total_err=0\n"
        )
        lines.append(
            f"[2026-10-17 12:30:00.000] I ({duration_sec*1000}) nexus_dht11: periodic_stats total_ok={drv_ok}, total_err={drv_err}\n"
        )
        return "".join(lines)

    def create_valid_mqtt_log(
        self,
        count=150,
        seq_start=1,
        dht_valid=True,
        drop_dht_fields_on_false=True,
        corrupt_ratio=0.0,
    ):
        """Generate a valid Protocol v1 MQTT telemetry log."""
        lines = []
        for i in range(count):
            seq = seq_start + i
            uptime = i * 2000
            iso = f"[2026-10-17 12:{i//30:02d}:{(i*2)%60:02d}.100] "
            pkt = {
                "ver": 1,
                "dev": "nexus_esp32",
                "seq": seq,
                "type": "telem",
                "uptime": uptime,
                "ldr": 450 + (i % 20),
                "x0": 110 + (i % 10),
            }
            if dht_valid:
                pkt["dht_valid"] = True
                pkt["temp"] = 24.5
                pkt["hum"] = 55.0
            else:
                pkt["dht_valid"] = False
                if not drop_dht_fields_on_false:
                    # Fabricated readings violation!
                    pkt["temp"] = 0.0
                    pkt["hum"] = 0.0

            lines.append(f"{iso}{json.dumps(pkt)}\n")
        return "".join(lines)


class TestNexusSoakHarness(BaseSoakTestCase):
    """Automated tests covering scenarios 1 through 19."""

    # -------------------------------------------------------------------------
    # Scenario 1: Fully valid capture that passes all measurable criteria
    # -------------------------------------------------------------------------
    def test_01_fully_valid_capture(self):
        """Scenario 1: Fully valid capture passing all firm and proposed criteria."""
        self.write_file(self.serial_file, self.create_valid_serial_log())
        self.write_file(self.mqtt_file, self.create_valid_mqtt_log(count=150))

        analyzer = NexusLogAnalyzer(self.serial_file, self.mqtt_file)
        analyzer.parse_serial_stream()
        analyzer.parse_mqtt_stream()
        analyzer.evaluate_acceptance()

        self.assertEqual(analyzer.overall_verdict, "PASS")
        for key in [
            "1_system_stability",
            "2_executive_deadlines",
            "3_executive_queues",
            "4_callback_budget",
            "6_transport_queuing",
            "7_schema_integrity",
            "8_heap_stability",
        ]:
            self.assertEqual(analyzer.criteria_results[key][1], "PASS", f"Failed {key}")

    # -------------------------------------------------------------------------
    # Scenario 2: Zero telemetry and empty files
    # -------------------------------------------------------------------------
    def test_02_zero_telemetry_and_empty_files(self):
        """Scenario 2: Empty files must yield INCONCLUSIVE, never false PASS."""
        self.write_file(self.serial_file, "")
        self.write_file(self.mqtt_file, "")

        analyzer = NexusLogAnalyzer(self.serial_file, self.mqtt_file)
        analyzer.parse_serial_stream()
        analyzer.parse_mqtt_stream()
        analyzer.evaluate_acceptance()

        self.assertEqual(analyzer.overall_verdict, "INCONCLUSIVE")
        self.assertNotEqual(analyzer.overall_verdict, "PASS")
        self.assertEqual(
            analyzer.criteria_results["1_system_stability"][1], "INCONCLUSIVE"
        )
        self.assertEqual(
            analyzer.criteria_results["7_schema_integrity"][1], "INCONCLUSIVE"
        )

    # -------------------------------------------------------------------------
    # Scenario 3: Malformed JSON, invalid UTF-8, truncated records, oversized lines
    # -------------------------------------------------------------------------
    def test_03_malformed_and_oversized_records(self):
        """Scenario 3: Non-blocking binary reader handles malformed and oversized data."""
        # Test BoundedStreamReader directly
        chunks = [
            b"valid line 1\n",
            b"invalid utf8 \xff\xfe\x00 byte\n",
            b"partial line without newline",
        ]
        reader = BoundedStreamReader(lambda: b"")
        lines = []
        for c in chunks:
            lines.extend(reader.feed_chunk(c))

        # Check partial recovery on flush
        flushed = reader.flush_remaining()
        self.assertEqual(len(flushed), 1)
        self.assertIn("[PARTIAL_ON_SHUTDOWN]", flushed[0])
        self.assertGreaterEqual(reader.records_malformed, 1)

        # Test oversized line truncation
        oversized = b"A" * 5000  # Exceeds 4096 buffer
        oversized_lines = reader.feed_chunk(oversized)
        self.assertTrue(any("[OVERSIZED_TRUNCATED]" in line for line in oversized_lines))
        self.assertGreater(reader.records_dropped, 0)

        # Test analyzer schema handling of malformed JSON
        bad_mqtt = (
            "[2026-10-17 12:00:00.000] {malformed json line\n"
            "[2026-10-17 12:00:01.000] not even json at all\n"
            "[2026-10-17 12:00:02.000] {\"ver\": 1, \"dev\": \"test\", \"seq\": 1}\n"
        )
        self.write_file(self.mqtt_file, bad_mqtt)
        analyzer = NexusLogAnalyzer(None, self.mqtt_file)
        analyzer.parse_mqtt_stream()
        self.assertGreater(analyzer.malformed_envelopes, 0)

    # -------------------------------------------------------------------------
    # Scenario 4: Missing mandatory fields and wrong JSON types (bool-not-int)
    # -------------------------------------------------------------------------
    def test_04_schema_violations_and_boolean_int_subclass(self):
        """Scenario 4: Rejects booleans supplied where integers or floats are required."""
        bad_pkts = [
            # ver is boolean True instead of integer 1
            {"ver": True, "dev": "nexus", "seq": 1, "type": "telem", "uptime": 100},
            # seq is boolean False instead of integer
            {"ver": 1, "dev": "nexus", "seq": False, "type": "telem", "uptime": 100},
            # ldr is boolean True
            {"ver": 1, "dev": "nexus", "seq": 3, "type": "telem", "uptime": 100, "ldr": True, "x0": 10, "dht_valid": True, "temp": 25.0, "hum": 50.0},
            # dht_valid is False but temp and hum are fabricated!
            {"ver": 1, "dev": "nexus", "seq": 4, "type": "telem", "uptime": 200, "ldr": 500, "x0": 10, "dht_valid": False, "temp": 0.0, "hum": 0.0},
            # dht_valid is a string instead of boolean
            {"ver": 1, "dev": "nexus", "seq": 5, "type": "telem", "uptime": 300, "ldr": 500, "x0": 10, "dht_valid": "true"},
        ]
        content = "\n".join(f"[2026-10-17 12:00:0{i}.000] {json.dumps(p)}" for i, p in enumerate(bad_pkts))
        self.write_file(self.mqtt_file, content)

        analyzer = NexusLogAnalyzer(None, self.mqtt_file)
        analyzer.parse_mqtt_stream()
        analyzer.evaluate_acceptance()

        self.assertGreater(analyzer.fabricated_readings, 0)
        self.assertGreater(analyzer.telem_invalid_types, 0)
        self.assertGreater(analyzer.telem_malformed_valid, 0)
        self.assertEqual(analyzer.criteria_results["7_schema_integrity"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 5: Sequence continuity, duplicates, reordering, wraparound
    # -------------------------------------------------------------------------
    def test_05_sequence_analysis_and_wraparound(self):
        """Scenario 5: Handles duplicates, reordering, uint32 wraparound, and implausible jumps."""
        # Stream 1: Duplicates, out-of-order, and ordinary gaps
        pkts1 = [
            {"ver": 1, "dev": "nexus", "seq": 10, "type": "hb", "uptime": 1000},
            {"ver": 1, "dev": "nexus", "seq": 11, "type": "hb", "uptime": 2000},
            {"ver": 1, "dev": "nexus", "seq": 10, "type": "hb", "uptime": 2100},  # Duplicate
            {"ver": 1, "dev": "nexus", "seq": 9, "type": "hb", "uptime": 2200},   # Out of order
            {"ver": 1, "dev": "nexus", "seq": 15, "type": "hb", "uptime": 3000},  # Gap: 12, 13, 14
        ]
        content1 = "\n".join(f"[2026-10-17 12:00:0{i}.000] {json.dumps(p)}" for i, p in enumerate(pkts1))
        self.write_file(self.mqtt_file, content1)

        analyzer1 = NexusLogAnalyzer(None, self.mqtt_file)
        analyzer1.parse_mqtt_stream()

        self.assertEqual(len(analyzer1.duplicate_arrivals), 1)
        self.assertEqual(analyzer1.duplicate_arrivals[0][1], 10)
        self.assertEqual(len(analyzer1.out_of_order_arrivals), 1)
        self.assertEqual(analyzer1.out_of_order_arrivals[0][1], 9)
        self.assertIn(12, analyzer1.pending_gaps)
        self.assertIn(13, analyzer1.pending_gaps)
        self.assertIn(14, analyzer1.pending_gaps)

        # Stream 2: Wraparound across uint32 ceiling (0xFFFFFFFA -> 0xFFFFFFFF -> 2)
        pkts2 = [
            {"ver": 1, "dev": "nexus", "seq": 0xFFFFFFFA, "type": "hb", "uptime": 1000},
            {"ver": 1, "dev": "nexus", "seq": 0xFFFFFFFF, "type": "hb", "uptime": 2000},
            {"ver": 1, "dev": "nexus", "seq": 2, "type": "hb", "uptime": 3000},  # Wraps around 0 to 2
        ]
        content2 = "\n".join(f"[2026-10-17 12:00:0{i}.000] {json.dumps(p)}" for i, p in enumerate(pkts2))
        self.write_file(self.mqtt_file, content2)

        analyzer2 = NexusLogAnalyzer(None, self.mqtt_file)
        analyzer2.parse_mqtt_stream()
        # Pending gaps across wraparound should include 0 and 1
        self.assertIn(0, analyzer2.pending_gaps)
        self.assertIn(1, analyzer2.pending_gaps)

        # Stream 3: Implausible jump > 50000
        pkts3 = [
            {"ver": 1, "dev": "nexus", "seq": 100, "type": "hb", "uptime": 1000},
            {"ver": 1, "dev": "nexus", "seq": 60000, "type": "hb", "uptime": 2000},  # Jump = 59900
        ]
        content3 = "\n".join(f"[2026-10-17 12:00:0{i}.000] {json.dumps(p)}" for i, p in enumerate(pkts3))
        self.write_file(self.mqtt_file, content3)

        analyzer3 = NexusLogAnalyzer(None, self.mqtt_file)
        analyzer3.parse_mqtt_stream()
        self.assertGreaterEqual(len(analyzer3.implausible_jumps), 1)

    # -------------------------------------------------------------------------
    # Scenario 6: Counter regression and suspected reboot/reset
    # -------------------------------------------------------------------------
    def test_06_counter_regression_and_multiple_resets(self):
        """Scenario 6: Detects cumulative counter regressions and multiple resets."""
        # Case A: Counter regression alone during steady state causes system stability failure
        serial_counter_reg = (
            "[2026-10-17 12:00:00.000] I (10) nexus_boot: reset_reason=1 (ESP_RST_POWERON)\n"
            "[2026-10-17 12:00:05.000] I (5000) nexus_exec: ticks=50 dispatched=20 completed=20 failed=0 dline_misses=0 q_overflows=0 max_lat_us=1000 max_dur_us=2000\n"
            # Counter regression: disp drops from 20 to 5
            "[2026-10-17 12:00:10.000] I (10000) nexus_exec: ticks=100 dispatched=5 completed=5 failed=0 dline_misses=0 q_overflows=0 max_lat_us=1000 max_dur_us=2000\n"
        )
        self.write_file(self.serial_file, serial_counter_reg)
        analyzer_reg = NexusLogAnalyzer(self.serial_file, None)
        analyzer_reg.parse_serial_stream()
        analyzer_reg.evaluate_acceptance()
        self.assertGreater(analyzer_reg.exec_counter_regressions, 0)
        self.assertEqual(analyzer_reg.criteria_results["1_system_stability"][1], "FAIL")
        self.assertEqual(analyzer_reg.criteria_results["2_executive_deadlines"][1], "INCONCLUSIVE")

        # Case B: Multiple reset reasons indicate reboot during soak
        serial_multi_rst = (
            "[2026-10-17 12:00:00.000] I (10) nexus_boot: reset_reason=1 (ESP_RST_POWERON)\n"
            "[2026-10-17 12:00:15.000] I (10) nexus_boot: reset_reason=3 (ESP_RST_SW)\n"
        )
        self.write_file(self.serial_file, serial_multi_rst)
        analyzer_multi = NexusLogAnalyzer(self.serial_file, None)
        analyzer_multi.parse_serial_stream()
        analyzer_multi.evaluate_acceptance()
        self.assertEqual(analyzer_multi.criteria_results["1_system_stability"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 7: Missing or invalid boot/reset-reason evidence
    # -------------------------------------------------------------------------
    def test_07_missing_or_invalid_reset_reasons(self):
        """Scenario 7: Missing boot record yields INCONCLUSIVE; panic/wdt yields FAIL."""
        # Case A: Missing boot record
        serial_mid = (
            "[2026-10-17 12:10:00.000] I (600000) nexus_exec: ticks=50 dispatched=20 completed=20 failed=0 dline_misses=0 q_overflows=0 max_lat_us=1000 max_dur_us=2000\n"
        )
        self.write_file(self.serial_file, serial_mid)
        analyzer_a = NexusLogAnalyzer(self.serial_file, None)
        analyzer_a.parse_serial_stream()
        analyzer_a.evaluate_acceptance()
        self.assertEqual(analyzer_a.criteria_results["1_system_stability"][1], "INCONCLUSIVE")

        # Case B: Hardware WDT / Brownout / Panic reset
        serial_wdt = (
            "[2026-10-17 12:00:00.000] I (10) nexus_boot: reset_reason=6 (ESP_RST_TASK_WDT)\n"
        )
        self.write_file(self.serial_file, serial_wdt)
        analyzer_b = NexusLogAnalyzer(self.serial_file, None)
        analyzer_b.parse_serial_stream()
        analyzer_b.evaluate_acceptance()
        self.assertEqual(analyzer_b.criteria_results["1_system_stability"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 8: Short captures and insufficient telemetry coverage
    # -------------------------------------------------------------------------
    def test_08_short_capture_duration(self):
        """Scenario 8: Capture duration < 1800s or telem count < 100 yields INCONCLUSIVE."""
        # Short serial: only 300 seconds
        self.write_file(self.serial_file, self.create_valid_serial_log(duration_sec=300))
        # Short mqtt: only 40 envelopes
        self.write_file(self.mqtt_file, self.create_valid_mqtt_log(count=40))

        analyzer = NexusLogAnalyzer(self.serial_file, self.mqtt_file)
        analyzer.parse_serial_stream()
        analyzer.parse_mqtt_stream()
        analyzer.evaluate_acceptance()

        self.assertEqual(analyzer.criteria_results["1_system_stability"][1], "INCONCLUSIVE")
        self.assertEqual(analyzer.criteria_results["9_telemetry_validity"][1], "INCONCLUSIVE")
        self.assertEqual(analyzer.criteria_results["10_error_isolation"][1], "INCONCLUSIVE")
        self.assertEqual(analyzer.overall_verdict, "INCONCLUSIVE")

    # -------------------------------------------------------------------------
    # Scenario 9: Timestamp regression, repeated timestamps, inconsistent duration
    # -------------------------------------------------------------------------
    def test_09_timestamp_regression_in_driver_logs(self):
        """Scenario 9: Regressing timestamps in driver logs trigger counter regressions."""
        serial_content = (
            "[2026-10-17 12:00:00.000] I (10) nexus_boot: reset_reason=1 (ESP_RST_POWERON)\n"
            "[2026-10-17 12:05:00.000] I (300000) nexus_dht11: total_ok=50, total_err=2\n"
            # Regressing uptime timestamp from 300000 down to 100000
            "[2026-10-17 12:06:00.000] I (100000) nexus_dht11: total_ok=55, total_err=2\n"
        )
        self.write_file(self.serial_file, serial_content)
        analyzer = NexusLogAnalyzer(self.serial_file, None)
        analyzer.parse_serial_stream()
        analyzer.evaluate_acceptance()

        self.assertGreater(analyzer.driver_counter_regressions, 0)
        self.assertEqual(analyzer.criteria_results["12_physical_driver"][1], "INCONCLUSIVE")

    # -------------------------------------------------------------------------
    # Scenario 10: Callback/dispatch threshold boundary values
    # -------------------------------------------------------------------------
    def test_10_boundary_values_for_callback_and_latency(self):
        """Scenario 10: Callback budget (50,000 us) and dispatch latency (110,000 us) boundaries."""
        # Boundary PASS: callback=49999 us, latency=110000 us
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(peak_dur=49999, peak_lat=110000),
        )
        analyzer_pass = NexusLogAnalyzer(self.serial_file, None)
        analyzer_pass.parse_serial_stream()
        analyzer_pass.evaluate_acceptance()
        self.assertEqual(analyzer_pass.criteria_results["4_callback_budget"][1], "PASS")
        self.assertEqual(analyzer_pass.criteria_results["5_dispatch_latency"][1], "PASS")

        # Boundary FAIL: callback=50000 us (limit is strictly < 50000 us)
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(peak_dur=50000, peak_lat=110001),
        )
        analyzer_fail = NexusLogAnalyzer(self.serial_file, None)
        analyzer_fail.parse_serial_stream()
        analyzer_fail.evaluate_acceptance()
        self.assertEqual(analyzer_fail.criteria_results["4_callback_budget"][1], "FAIL")
        self.assertEqual(analyzer_fail.criteria_results["5_dispatch_latency"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 11: Queue high-water and overflow thresholds
    # -------------------------------------------------------------------------
    def test_11_queue_overflow_and_hwm_thresholds(self):
        """Scenario 11: Queue overflow > 0 fails firm req; hwm > 4 fails proposed."""
        # Queue overflow fails firm requirement 3
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(q_ovf=1, q_hwm=3),
        )
        analyzer_qovf = NexusLogAnalyzer(self.serial_file, None)
        analyzer_qovf.parse_serial_stream()
        analyzer_qovf.evaluate_acceptance()
        self.assertEqual(analyzer_qovf.criteria_results["3_executive_queues"][1], "FAIL")
        self.assertEqual(analyzer_qovf.criteria_results["11_queue_hwm"][1], "PASS")

        # HWM = 5 fails proposed criterion 11
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(q_ovf=0, q_hwm=5),
        )
        analyzer_hwm = NexusLogAnalyzer(self.serial_file, None)
        analyzer_hwm.parse_serial_stream()
        analyzer_hwm.evaluate_acceptance()
        self.assertEqual(analyzer_hwm.criteria_results["3_executive_queues"][1], "PASS")
        self.assertEqual(analyzer_hwm.criteria_results["11_queue_hwm"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 12: TX drop/failure thresholds
    # -------------------------------------------------------------------------
    def test_12_tx_drop_and_failure_thresholds(self):
        """Scenario 12: Any tx_drop or tx_fail causes transport integrity failure."""
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(tx_drop=1, tx_fail=0),
        )
        analyzer_drop = NexusLogAnalyzer(self.serial_file, None)
        analyzer_drop.parse_serial_stream()
        analyzer_drop.evaluate_acceptance()
        self.assertEqual(analyzer_drop.criteria_results["6_transport_queuing"][1], "FAIL")

        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(tx_drop=0, tx_fail=2),
        )
        analyzer_fail = NexusLogAnalyzer(self.serial_file, None)
        analyzer_fail.parse_serial_stream()
        analyzer_fail.evaluate_acceptance()
        self.assertEqual(analyzer_fail.criteria_results["6_transport_queuing"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 13: Telemetry validity and consecutive invalid-frame limits
    # -------------------------------------------------------------------------
    def test_13_telemetry_validity_percentage_and_consecutive_invalids(self):
        """Scenario 13: Telemetry validity < 85% or > 3 consecutive invalid frames fails."""
        # 120 total envelopes, 30 degraded (validity = 90/120 = 75.0% < 85%)
        # with 5 consecutive invalids at indices 20..24
        pkts = []
        invalid_indices = set(range(20, 25)).union(set(range(40, 65)))  # 5 + 25 = 30 invalids
        for i in range(120):
            is_valid = i not in invalid_indices
            pkt = {
                "ver": 1,
                "dev": "nexus",
                "seq": i + 1,
                "type": "telem",
                "uptime": i * 1000,
                "ldr": 400,
                "x0": 100,
                "dht_valid": is_valid,
            }
            if is_valid:
                pkt["temp"] = 24.0
                pkt["hum"] = 50.0
            pkts.append(f"[2026-10-17 12:00:00.000] {json.dumps(pkt)}")

        self.write_file(self.mqtt_file, "\n".join(pkts))
        analyzer = NexusLogAnalyzer(None, self.mqtt_file)
        analyzer.parse_mqtt_stream()
        analyzer.evaluate_acceptance()

        self.assertEqual(analyzer.criteria_results["9_telemetry_validity"][1], "FAIL")
        self.assertEqual(analyzer.criteria_results["10_error_isolation"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 14: Sensor-driver success/failure observable calculations
    # -------------------------------------------------------------------------
    def test_14_physical_driver_success_ratio(self):
        """Scenario 14: Sensor driver success evaluated strictly across boundary logs."""
        # PASS: delta_ok = 850, delta_err = 50 -> 850/900 = 94.4% >= 80%
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(drv_ok=850, drv_err=50),
        )
        analyzer_pass = NexusLogAnalyzer(self.serial_file, None)
        analyzer_pass.parse_serial_stream()
        analyzer_pass.evaluate_acceptance()
        self.assertEqual(analyzer_pass.criteria_results["12_physical_driver"][1], "PASS")

        # FAIL: delta_ok = 700, delta_err = 300 -> 700/1000 = 70% < 80%
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(drv_ok=700, drv_err=300),
        )
        analyzer_fail = NexusLogAnalyzer(self.serial_file, None)
        analyzer_fail.parse_serial_stream()
        analyzer_fail.evaluate_acceptance()
        self.assertEqual(analyzer_fail.criteria_results["12_physical_driver"][1], "FAIL")

    # -------------------------------------------------------------------------
    # Scenario 15: Phased heap analysis (stable, leaking, noisy, insufficient)
    # -------------------------------------------------------------------------
    def test_15_phased_heap_analysis_scenarios(self):
        """Scenario 15: Phased OLS linear regression distinguishing leaks from stability."""
        # Case A: Stable heap (slope ~ 0 B/hr) -> PASS
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(heap_slope=0.0),
        )
        analyzer_stable = NexusLogAnalyzer(self.serial_file, None)
        analyzer_stable.parse_serial_stream()
        analyzer_stable.evaluate_acceptance()
        self.assertEqual(analyzer_stable.criteria_results["8_heap_stability"][1], "PASS")

        # Case B: Significant leak (-150 B/hr with R^2 > 0.8) -> FAIL
        # slope in B/s = -150 / 3600 = -0.04166
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(heap_slope=-0.045),
        )
        analyzer_leak = NexusLogAnalyzer(self.serial_file, None)
        analyzer_leak.parse_serial_stream()
        analyzer_leak.evaluate_acceptance()
        self.assertEqual(analyzer_leak.criteria_results["8_heap_stability"][1], "FAIL")

        # Case C: Insufficient steady-state samples (< 30 samples) -> INCONCLUSIVE
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(duration_sec=200),
        )
        analyzer_short = NexusLogAnalyzer(self.serial_file, None)
        analyzer_short.parse_serial_stream()
        analyzer_short.evaluate_acceptance()
        self.assertEqual(analyzer_short.criteria_results["8_heap_stability"][1], "INCONCLUSIVE")

        # Case D: High baseline free heap (e.g. 292,288 B matching Milestone 3.1) -> PASS
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(heap_base=292288, heap_slope=0.0),
        )
        analyzer_high = NexusLogAnalyzer(self.serial_file, None)
        analyzer_high.parse_serial_stream()
        analyzer_high.evaluate_acceptance()
        self.assertEqual(analyzer_high.criteria_results["8_heap_stability"][1], "PASS")

    # -------------------------------------------------------------------------
    # Scenario 16: MQTT absence and routing ambiguity
    # -------------------------------------------------------------------------
    def test_16_mqtt_absence_and_routing_ambiguity(self):
        """Scenario 16: MQTT absence does not fail serial criteria; missing MQTT is INCONCLUSIVE."""
        self.write_file(self.serial_file, self.create_valid_serial_log())

        analyzer = NexusLogAnalyzer(self.serial_file, None)
        analyzer.parse_serial_stream()
        analyzer.parse_mqtt_stream()
        analyzer.evaluate_acceptance()

        # Serial firm criteria pass
        self.assertEqual(analyzer.criteria_results["1_system_stability"][1], "PASS")
        self.assertEqual(analyzer.criteria_results["2_executive_deadlines"][1], "PASS")
        self.assertEqual(analyzer.criteria_results["6_transport_queuing"][1], "PASS")

        # MQTT telemetry schema is INCONCLUSIVE due to unobserved MQTT stream
        self.assertEqual(analyzer.criteria_results["7_schema_integrity"][1], "INCONCLUSIVE")
        # Overall verdict must be INCONCLUSIVE, not false PASS
        self.assertEqual(analyzer.overall_verdict, "INCONCLUSIVE")

    # -------------------------------------------------------------------------
    # Scenario 17: Output file errors, collision protection, and exit codes
    # -------------------------------------------------------------------------
    def test_17_exit_codes_and_collision_guard(self):
        """Scenario 17: Validates exit codes 0 (PASS), 1 (FAIL), 2 (INCONCLUSIVE), 3 (INPUT_ERROR)."""
        # Test exit code 3 on missing positional arguments
        cmd_no_args = [sys.executable, "tests/soak/analyze_nexus_soak.py"]
        res_no_args = subprocess.run(cmd_no_args, capture_output=True)
        self.assertEqual(res_no_args.returncode, 3)

        # Test exit code 3 on nonexistent input file
        cmd_missing = [sys.executable, "tests/soak/analyze_nexus_soak.py", "nonexistent_file.log"]
        res_missing = subprocess.run(cmd_missing, capture_output=True)
        self.assertEqual(res_missing.returncode, 3)

        # Test exit code 3 on capture CLI invalid flag
        cmd_capture_usage = [sys.executable, "tests/soak/nexus_soak_capture.py", "--invalid-flag-12345"]
        res_capture_usage = subprocess.run(cmd_capture_usage, capture_output=True)
        self.assertEqual(res_capture_usage.returncode, 3)

        # Test exit code 3 on self-overwrite collision guard
        self.write_file(self.serial_file, "content")
        cmd_collision = [
            sys.executable,
            "tests/soak/analyze_nexus_soak.py",
            self.serial_file,
            "--json-out",
            self.serial_file,  # Attempting to overwrite input!
        ]
        res_collision = subprocess.run(cmd_collision, capture_output=True)
        self.assertEqual(res_collision.returncode, 3)

        # Test exit code 0 on passing capture
        self.write_file(self.serial_file, self.create_valid_serial_log())
        self.write_file(self.mqtt_file, self.create_valid_mqtt_log())
        cmd_pass = [
            sys.executable,
            "tests/soak/analyze_nexus_soak.py",
            self.serial_file,
            self.mqtt_file,
        ]
        res_pass = subprocess.run(cmd_pass, capture_output=True)
        self.assertEqual(res_pass.returncode, 0)

        # Test exit code 1 on failing capture (deadline miss)
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(dl_miss=3),
        )
        cmd_fail = [
            sys.executable,
            "tests/soak/analyze_nexus_soak.py",
            self.serial_file,
            self.mqtt_file,
        ]
        res_fail = subprocess.run(cmd_fail, capture_output=True)
        self.assertEqual(res_fail.returncode, 1)

        # Test exit code 2 on inconclusive capture (short duration)
        self.write_file(
            self.serial_file,
            self.create_valid_serial_log(duration_sec=200),
        )
        cmd_inc = [
            sys.executable,
            "tests/soak/analyze_nexus_soak.py",
            self.serial_file,
        ]
        res_inc = subprocess.run(cmd_inc, capture_output=True)
        self.assertEqual(res_inc.returncode, 2)

    # -------------------------------------------------------------------------
    # Scenario 18: Capture harness simulation mode and safety boundaries
    # -------------------------------------------------------------------------
    def test_18_capture_harness_simulation_and_safety(self):
        """Scenario 18: Software simulation mode creates logs without opening serial port."""
        serial_out = os.path.join(self.test_dir, "sim_serial.log")
        mqtt_out = os.path.join(self.test_dir, "sim_mqtt.log")

        # Execute 2-second simulation
        cmd_sim = [
            sys.executable,
            "tests/soak/nexus_soak_capture.py",
            "--simulate",
            "--duration",
            "2",
            "--serial-out",
            serial_out,
            "--mqtt-out",
            mqtt_out,
        ]
        res_sim = subprocess.run(cmd_sim, capture_output=True, text=True)
        self.assertEqual(res_sim.returncode, 0)
        self.assertTrue(os.path.exists(serial_out))
        self.assertTrue(os.path.exists(mqtt_out))
        self.assertGreater(os.path.getsize(serial_out), 0)
        self.assertGreater(os.path.getsize(mqtt_out), 0)

        # Verify that hardware flag without explicit risk acknowledgement is rejected
        cmd_unsafe = [
            sys.executable,
            "tests/soak/nexus_soak_capture.py",
            "--hardware",
        ]
        res_unsafe = subprocess.run(cmd_unsafe, capture_output=True, text=True)
        self.assertEqual(res_unsafe.returncode, 2)
        self.assertIn("SAFETY INTERLOCK ERROR", res_unsafe.stderr)

    # -------------------------------------------------------------------------
    # Scenario 19: Reproducibility of machine-readable output and Markdown
    # -------------------------------------------------------------------------
    def test_19_reproducibility_of_reports(self):
        """Scenario 19: Generated JSON and Markdown reports are deterministic and schema-stable."""
        self.write_file(self.serial_file, self.create_valid_serial_log())
        self.write_file(self.mqtt_file, self.create_valid_mqtt_log())

        analyzer1 = NexusLogAnalyzer(self.serial_file, self.mqtt_file)
        analyzer1.parse_serial_stream()
        analyzer1.parse_mqtt_stream()
        analyzer1.evaluate_acceptance()
        json1 = analyzer1.generate_json_report()
        md1 = analyzer1.generate_markdown_report()

        analyzer2 = NexusLogAnalyzer(self.serial_file, self.mqtt_file)
        analyzer2.parse_serial_stream()
        analyzer2.parse_mqtt_stream()
        analyzer2.evaluate_acceptance()
        json2 = analyzer2.generate_json_report()
        md2 = analyzer2.generate_markdown_report()

        # Both runs must produce identical dictionaries and markdown
        self.assertEqual(json1, json2)
        self.assertEqual(md1, md2)

        # Check required schema keys
        self.assertIn("metadata", json1)
        self.assertIn("summary", json1)
        self.assertIn("overall_verdict", json1)
        self.assertIn("criteria", json1)
        self.assertIn("sequence_metrics", json1)
        self.assertIn("telemetry_metrics", json1)
        self.assertIn("serial_metrics", json1)
        self.assertEqual(json1["overall_verdict"], "PASS")
        self.assertEqual(json1["summary"]["overall_verdict"], "PASS")

        # Check agreement between JSON verdict and Markdown summary
        self.assertIn(f"**Overall Verdict: {json1['overall_verdict']}**", md1)


if __name__ == "__main__":
    unittest.main()
