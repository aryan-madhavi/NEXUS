"""Unit tests for ground_station.run_mqtt_ingestion."""

import unittest
from unittest.mock import MagicMock, patch

from ground_station.connection_manager.envelope_parser import (
    EnvelopeParser,
    MessageType,
    ParsedEnvelope,
    TelemetryPayload,
)
from ground_station.run_mqtt_ingestion import MqttIngestionSession


class TestMqttIngestionSession(unittest.TestCase):
    """Test suite for MqttIngestionSession logic."""

    def test_session_init_defaults(self):
        session = MqttIngestionSession(duration_sec=10)
        self.assertEqual(session.duration_sec, 10)
        self.assertIsNone(session.host)
        self.assertIsNone(session.port)
        self.assertEqual(session.messages_total, 0)

    @patch("ground_station.run_mqtt_ingestion.InfluxDBWriter")
    @patch("ground_station.run_mqtt_ingestion.MqttTransportAdapter")
    @patch("ground_station.run_mqtt_ingestion.NexusHostManager")
    def test_session_setup(self, mock_manager, mock_adapter, mock_writer):
        session = MqttIngestionSession(host="127.0.0.1", port=1883, duration_sec=5)
        self.assertTrue(session.setup())
        self.assertIsNotNone(session.manager)
        self.assertIsNotNone(session.mqtt_adapter)
        self.assertIsNotNone(session.influx_writer)

    def test_on_envelope_ingested_telemetry(self):
        session = MqttIngestionSession()
        raw = '{"ver":1,"dev":"nexus_esp32","seq":10,"type":"telem","uptime":5000,"ldr":512,"x0":1024,"temp":25.0,"hum":50.0,"dht_valid":true}\n'
        envelope = EnvelopeParser.parse(raw)

        session._on_envelope_ingested(envelope)
        self.assertEqual(session.messages_total, 1)
        self.assertEqual(session.envelopes_by_type.get("telem"), 1)
        self.assertEqual(session.dht_valid_count, 1)
        self.assertEqual(session.latest_temp, 25.0)
        self.assertEqual(session.latest_hum, 50.0)
        self.assertEqual(session.latest_ldr, 512)
        self.assertEqual(session.latest_x0, 1024)
        self.assertIn("nexus_esp32", session.devices_seen)
        self.assertEqual(session.first_seq, 10)
        self.assertEqual(session.last_seq, 10)


if __name__ == "__main__":
    unittest.main()
