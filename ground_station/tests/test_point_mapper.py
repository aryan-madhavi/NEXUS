"""Unit tests for InfluxDB PointMapper.

Validates schema translation, tag/field cardinality separation, precision,
timestamp semantics, and missing-data suppression for invalid DHT readings.
"""

import unittest
from ground_station.connection_manager.envelope_parser import EnvelopeParser
from ground_station.persistence.point_mapper import PointMapper


class TestPointMapper(unittest.TestCase):
    """Test suite for PointMapper."""

    def test_heartbeat_mapping(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":10,"type":"hb","uptime":12000,"heap":250000,"ticks":50}\n'
        env = EnvelopeParser.parse(raw)
        # Attach simulated transport and receive timestamp
        env = env.__class__(
            raw_bytes=env.raw_bytes,
            raw_text=env.raw_text,
            ver=env.ver,
            dev=env.dev,
            seq=env.seq,
            msg_type=env.msg_type,
            uptime_ms=env.uptime_ms,
            payload=env.payload,
            extra_fields=env.extra_fields,
            raw_dict=env.raw_dict,
            transport="serial",
            received_at=1710000000.123456,
        )

        data = PointMapper.to_dict(env)
        self.assertEqual(data["measurement"], "nexus_hb")
        self.assertEqual(data["tags"]["dev"], "nexus_esp32")
        self.assertEqual(data["tags"]["type"], "hb")
        self.assertEqual(data["tags"]["transport"], "serial")

        # Stable tags vs numeric fields check
        self.assertEqual(data["fields"]["seq"], 10)
        self.assertEqual(data["fields"]["uptime_ms"], 12000)
        self.assertEqual(data["fields"]["free_heap"], 250000)
        self.assertEqual(data["fields"]["exec_ticks"], 50)
        self.assertEqual(data["time_ns"], 1710000000123456000)

    def test_telemetry_mapping_valid_dht(self):
        raw = (
            '{"ver":1,"dev":"nexus_esp32","seq":20,"type":"telem","uptime":15000,'
            '"ldr":1250,"x0":2150,"temp":24.5,"hum":62.0,"dht_valid":true}\n'
        )
        env = EnvelopeParser.parse(raw)
        data = PointMapper.to_dict(env)

        self.assertEqual(data["measurement"], "nexus_telem")
        self.assertEqual(data["tags"]["dev"], "nexus_esp32")
        self.assertEqual(data["tags"]["type"], "telem")
        self.assertEqual(data["fields"]["seq"], 20)
        self.assertEqual(data["fields"]["ldr_raw"], 1250)
        self.assertEqual(data["fields"]["x0_raw"], 2150)
        self.assertTrue(data["fields"]["dht_valid"])
        self.assertAlmostEqual(data["fields"]["temp"], 24.5)
        self.assertAlmostEqual(data["fields"]["hum"], 62.0)

    def test_telemetry_mapping_invalid_dht_suppression(self):
        """Invalid DHT readings must remain missing/null and never become zero."""
        raw = (
            '{"ver":1,"dev":"nexus_esp32","seq":21,"type":"telem","uptime":16000,'
            '"ldr":1280,"x0":2190,"dht_valid":false}\n'
        )
        env = EnvelopeParser.parse(raw)
        data = PointMapper.to_dict(env)

        self.assertEqual(data["fields"]["seq"], 21)
        self.assertEqual(data["fields"]["ldr_raw"], 1280)
        self.assertEqual(data["fields"]["x0_raw"], 2190)
        self.assertFalse(data["fields"]["dht_valid"])

        # Temperature and humidity must NOT be present in fields
        self.assertNotIn("temp", data["fields"])
        self.assertNotIn("hum", data["fields"])

    def test_status_mapping(self):
        raw = (
            '{"ver":1,"dev":"nexus_esp32","seq":30,"type":"status","uptime":20000,'
            '"disp":100,"comp":98,"fail":2,"lat_us":150,"dur_us":450}\n'
        )
        env = EnvelopeParser.parse(raw)
        data = PointMapper.to_dict(env)

        self.assertEqual(data["measurement"], "nexus_status")
        self.assertEqual(data["fields"]["seq"], 30)
        self.assertEqual(data["fields"]["uptime_ms"], 20000)
        self.assertEqual(data["fields"]["dispatched"], 100)
        self.assertEqual(data["fields"]["completed"], 98)
        self.assertEqual(data["fields"]["failed"], 2)
        self.assertEqual(data["fields"]["max_lat_us"], 150)
        self.assertEqual(data["fields"]["max_dur_us"], 450)

    def test_event_mapping_attributes_as_numeric_fields(self):
        """Event attributes must be numeric fields, not tags, to prevent tag cardinality explosion."""
        raw = (
            '{"ver":1,"dev":"nexus_esp32","seq":40,"type":"event","uptime":25000,'
            '"ev":2,"sev":1,"src":5,"val":1024}\n'
        )
        env = EnvelopeParser.parse(raw)
        data = PointMapper.to_dict(env)

        self.assertEqual(data["measurement"], "nexus_event")
        self.assertEqual(data["fields"]["seq"], 40)
        self.assertEqual(data["fields"]["event_type"], 2)
        self.assertEqual(data["fields"]["severity"], 1)
        self.assertEqual(data["fields"]["source_id"], 5)
        self.assertEqual(data["fields"]["payload_val"], 1024)

        # Confirm not present in tags
        self.assertNotIn("event_type", data["tags"])
        self.assertNotIn("severity", data["tags"])
        self.assertNotIn("payload_val", data["tags"])

    def test_single_measurement_option(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":50,"type":"hb","uptime":1000,"heap":200000,"ticks":10}\n'
        env = EnvelopeParser.parse(raw)
        data = PointMapper.to_dict(env, measurement_prefix="nexus_stream", use_single_measurement=True)

        self.assertEqual(data["measurement"], "nexus_stream")
        self.assertEqual(data["tags"]["type"], "hb")

    def test_command_and_response_mapping(self):
        cmd_raw = '{"ver":1,"dev":"nexus_esp32","seq":60,"type":"cmd","uptime":3000,"cmd_id":12,"action":"reboot"}\n'
        cmd_env = EnvelopeParser.parse(cmd_raw)
        cmd_data = PointMapper.to_dict(cmd_env)

        self.assertEqual(cmd_data["measurement"], "nexus_cmd")
        self.assertEqual(cmd_data["fields"]["seq"], 60)
        self.assertEqual(cmd_data["fields"]["uptime_ms"], 3000)
        self.assertEqual(cmd_data["fields"]["field_cmd_id"], 12)
        self.assertEqual(cmd_data["fields"]["field_action"], "reboot")

        resp_raw = '{"ver":1,"dev":"nexus_esp32","seq":61,"type":"resp","uptime":3100,"req_seq":60,"status":0}\n'
        resp_env = EnvelopeParser.parse(resp_raw)
        resp_data = PointMapper.to_dict(resp_env)

        self.assertEqual(resp_data["measurement"], "nexus_resp")
        self.assertEqual(resp_data["fields"]["seq"], 61)
        self.assertEqual(resp_data["fields"]["field_req_seq"], 60)
        self.assertEqual(resp_data["fields"]["field_status"], 0)

    def test_missing_received_at_fallback_to_wallclock(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":70,"type":"hb","uptime":5000,"heap":200000,"ticks":10}\n'
        env = EnvelopeParser.parse(raw)
        self.assertIsNone(env.received_at)

        data = PointMapper.to_dict(env)
        self.assertIsInstance(data["time_ns"], int)
        self.assertGreater(data["time_ns"], 0)


if __name__ == "__main__":
    unittest.main()
