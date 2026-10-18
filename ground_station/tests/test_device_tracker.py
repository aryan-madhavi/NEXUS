"""Unit tests for the NEXUS Device and Transport Tracker."""

import unittest

from ground_station.connection_manager.device_tracker import DeviceTracker
from ground_station.connection_manager.envelope_parser import EnvelopeParser


class TestDeviceTracker(unittest.TestCase):
    """Test suite for device and transport identity tracking."""

    def setUp(self):
        self.tracker = DeviceTracker()

    def test_record_valid_envelope_single_device_and_transport(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":100,"type":"hb","uptime":12000,"heap":250000,"ticks":50}'
        env = EnvelopeParser.parse(raw)

        m_time = 1000.5
        w_time = 1700000000.0
        self.tracker.record_valid_envelope(
            transport_name="serial",
            envelope=env,
            now_monotonic=m_time,
            now_wallclock=w_time,
        )

        dev = self.tracker.get_device("nexus_esp32")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.device_id, "nexus_esp32")
        self.assertEqual(dev.first_seen_monotonic, m_time)
        self.assertEqual(dev.last_seen_monotonic, m_time)
        self.assertEqual(dev.last_valid_monotonic, m_time)
        self.assertEqual(dev.total_accepted, 1)
        self.assertEqual(dev.total_rejected, 0)
        self.assertEqual(dev.last_seq, 100)
        self.assertEqual(dev.last_uptime_ms, 12000)
        self.assertEqual(dev.last_seq_by_type.get("hb"), 100)

        # Check transport sub-record
        self.assertIn("serial", dev.transports)
        t_state = dev.transports["serial"]
        self.assertEqual(t_state.accepted_count, 1)
        self.assertEqual(t_state.rejected_count, 0)
        self.assertEqual(t_state.last_seq, 100)
        self.assertEqual(t_state.last_uptime_ms, 12000)

        # Check monotonic elapsed calculation
        elapsed = dev.elapsed_since_last_seen(1005.5)
        self.assertEqual(elapsed, 5.0)

    def test_record_multiple_transports_same_device(self):
        raw1 = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":1000,"ldr":500,"x0":100,"dht_valid":false}'
        raw2 = '{"ver":1,"dev":"nexus_esp32","seq":2,"type":"telem","uptime":2000,"ldr":510,"x0":110,"dht_valid":false}'

        env1 = EnvelopeParser.parse(raw1)
        env2 = EnvelopeParser.parse(raw2)

        self.tracker.record_valid_envelope("serial", env1, now_monotonic=10.0, now_wallclock=100.0)
        self.tracker.record_valid_envelope("mqtt", env2, now_monotonic=12.0, now_wallclock=102.0)

        dev = self.tracker.get_device("nexus_esp32")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.total_accepted, 2)
        self.assertEqual(len(dev.transports), 2)
        self.assertIn("serial", dev.transports)
        self.assertIn("mqtt", dev.transports)
        self.assertEqual(dev.transports["serial"].last_seq, 1)
        self.assertEqual(dev.transports["mqtt"].last_seq, 2)

    def test_record_multiple_distinct_devices(self):
        raw_dev1 = '{"ver":1,"dev":"nexus_node_1","seq":1,"type":"hb","uptime":100,"heap":200000,"ticks":10}'
        raw_dev2 = '{"ver":1,"dev":"nexus_node_2","seq":5,"type":"hb","uptime":500,"heap":190000,"ticks":50}'

        self.tracker.record_valid_envelope("serial", EnvelopeParser.parse(raw_dev1))
        self.tracker.record_valid_envelope("mqtt", EnvelopeParser.parse(raw_dev2))

        all_devs = self.tracker.get_all_devices()
        self.assertEqual(len(all_devs), 2)
        self.assertIn("nexus_node_1", all_devs)
        self.assertIn("nexus_node_2", all_devs)
        self.assertEqual(all_devs["nexus_node_1"].last_seq, 1)
        self.assertEqual(all_devs["nexus_node_2"].last_seq, 5)

    def test_record_rejected_envelopes_and_error_categories(self):
        self.tracker.record_rejected_envelope(
            transport_name="serial",
            error_category="malformed_json",
            now_monotonic=50.0,
            now_wallclock=500.0,
        )
        self.tracker.record_rejected_envelope(
            transport_name="serial",
            error_category="oversized_envelope",
            now_monotonic=51.0,
            now_wallclock=501.0,
        )
        self.tracker.record_rejected_envelope(
            transport_name="mqtt",
            error_category="unsupported_version",
            now_monotonic=52.0,
            now_wallclock=502.0,
            device_id="nexus_esp32",
        )

        summary = self.tracker.get_summary()
        self.assertEqual(summary["total_accepted"], 0)
        self.assertEqual(summary["total_rejected"], 3)
        self.assertEqual(summary["global_error_counts"]["malformed_json"], 1)
        self.assertEqual(summary["global_error_counts"]["oversized_envelope"], 1)
        self.assertEqual(summary["global_error_counts"]["unsupported_version"], 1)

        dev = self.tracker.get_device("nexus_esp32")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.total_rejected, 1)
        self.assertEqual(dev.transports["mqtt"].error_counts["unsupported_version"], 1)

    def test_immutability_of_returned_snapshots(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"hb","uptime":100,"heap":200000,"ticks":10}'
        self.tracker.record_valid_envelope("serial", EnvelopeParser.parse(raw))

        dev_snapshot = self.tracker.get_device("nexus_esp32")
        self.assertIsNotNone(dev_snapshot)
        # Attempt to mutate returned copy
        dev_snapshot.total_accepted = 9999
        dev_snapshot.transports["serial"].accepted_count = 9999

        # Internal state in tracker must remain unaffected
        fresh_dev = self.tracker.get_device("nexus_esp32")
        self.assertIsNotNone(fresh_dev)
        self.assertEqual(fresh_dev.total_accepted, 1)
        self.assertEqual(fresh_dev.transports["serial"].accepted_count, 1)


if __name__ == "__main__":
    unittest.main()
