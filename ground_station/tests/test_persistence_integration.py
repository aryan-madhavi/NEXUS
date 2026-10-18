"""Integration tests for Host Manager + Transports + InfluxDB Persistence.

Validates end-to-end flow from fake serial and fake MQTT adapters through NexusHostManager
into InfluxDBWriter, verifying non-blocking isolation, transport provenance tagging,
and lifecycle resilience.
"""

import time
import unittest
from ground_station.connection_manager.mqtt_adapter import (
    MqttConfig,
    MqttTransportAdapter,
)
from ground_station.connection_manager.nexus_host_manager import (
    NexusHostManager,
    QueueFullPolicy,
)
from ground_station.connection_manager.serial_adapter import (
    SerialConfig,
    SerialTransportAdapter,
)
from ground_station.persistence.influxdb_writer import (
    InfluxDBConfig,
    InfluxDBWriter,
)
from ground_station.tests.test_influxdb_writer import MockInfluxDBClient
from ground_station.tests.test_mqtt_adapter import MockMqttClient, MockMqttMessage
from ground_station.tests.test_serial_adapter import MockSerialPort


class TestPersistenceIntegration(unittest.TestCase):
    """End-to-end integration tests for transports and InfluxDB persistence."""

    def test_end_to_end_serial_and_mqtt_to_influxdb(self):
        # 1. Host Manager
        manager = NexusHostManager(queue_capacity=50)

        # 2. Fake Serial Adapter
        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(port="/dev/test_serial", serial_factory=lambda *a, **kw: serial_port),
            name="serial",
        )

        # 3. Fake MQTT Adapter
        mqtt_client = MockMqttClient(client_id="test_gw")
        mqtt_adapter = MqttTransportAdapter(
            config=MqttConfig(client_factory=lambda cid: mqtt_client),
            name="mqtt",
        )

        # 4. InfluxDB Writer with Mock Client
        mock_influx = MockInfluxDBClient()
        influx_writer = InfluxDBWriter(
            config=InfluxDBConfig(
                batch_size=2,
                flush_interval_sec=0.05,
                client_factory=lambda cfg: mock_influx,
            ),
            name="influxdb",
        )

        # Register transports and persistence consumer
        manager.register_transport(serial_adapter)
        manager.register_transport(mqtt_adapter)
        manager.register_consumer(influx_writer.write_envelope)

        manager.start()
        influx_writer.start()
        mqtt_client.on_connect(mqtt_client, None, {}, 0)

        # Send 1 message via Serial
        serial_msg = b'{"ver":1,"dev":"nexus_esp32","seq":100,"type":"hb","uptime":5000,"heap":220000,"ticks":20}\n'
        serial_port.feed_bytes(serial_msg)

        # Send 1 message via MQTT
        mqtt_msg = MockMqttMessage(
            topic="nexus/nexus_esp32/telemetry",
            payload=b'{"ver":1,"dev":"nexus_esp32","seq":101,"type":"telem","uptime":5500,"ldr":1200,"x0":2000,"dht_valid":true,"temp":22.5,"hum":58.0}\n',
        )
        mqtt_client.on_message(mqtt_client, None, mqtt_msg)

        # Wait for batch threshold (2) to trigger write
        time.sleep(0.1)

        manager.stop()
        influx_writer.stop()

        # Verify host manager metrics
        mgr_stats = manager.get_stats()
        self.assertEqual(mgr_stats.messages_received, 2)
        self.assertEqual(mgr_stats.messages_parsed, 2)
        self.assertEqual(mgr_stats.enqueued_count, 2)

        # Verify InfluxDB batches and point attributes
        self.assertGreaterEqual(len(mock_influx.write_api_mock.batches), 1)
        records = [
            pt for batch in mock_influx.write_api_mock.batches for pt in batch["record"]
        ]
        self.assertEqual(len(records), 2)

        # Convert Point objects or dicts to check provenance
        transports = []
        for r in records:
            if hasattr(r, "_tags"):
                transports.append(r._tags.get("transport"))
            elif isinstance(r, dict):
                transports.append(r["tags"].get("transport"))

        self.assertIn("serial", transports)
        self.assertIn("mqtt", transports)

        writer_stats = influx_writer.get_stats()
        self.assertEqual(writer_stats.successful_writes, 2)
        self.assertEqual(writer_stats.write_failures, 0)

    def test_database_outage_does_not_block_transport_ingestion(self):
        """A complete database outage must never block serial/MQTT reads or drop manager queue."""
        manager = NexusHostManager(queue_capacity=50)

        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(port="/dev/test_serial", serial_factory=lambda *a, **kw: serial_port),
            name="serial",
        )

        mock_influx = MockInfluxDBClient()
        # Fail all database writes permanently
        mock_influx.write_api_mock.fail_countdown = 999

        influx_writer = InfluxDBWriter(
            config=InfluxDBConfig(
                batch_size=5,
                max_retries=1,
                retry_base_delay_sec=0.01,
                retry_max_delay_sec=0.02,
                client_factory=lambda cfg: mock_influx,
            ),
            name="influxdb",
        )

        manager.register_transport(serial_adapter)
        manager.register_consumer(influx_writer.write_envelope)

        manager.start()
        influx_writer.start()

        # Ingest 5 messages over serial
        for i in range(1, 6):
            serial_port.feed_bytes(
                f'{{"ver":1,"dev":"nexus_esp32","seq":{i},"type":"cmd"}}\n'.encode("utf-8")
            )

        time.sleep(0.1)

        manager.stop()
        influx_writer.stop()

        # Host manager must have processed all 5 messages without dropping any
        mgr_stats = manager.get_stats()
        self.assertEqual(mgr_stats.messages_received, 5)
        self.assertEqual(mgr_stats.messages_parsed, 5)
        self.assertEqual(mgr_stats.enqueued_count, 5)

        # Persistence writer must account for write failure and retry exhaustion
        writer_stats = influx_writer.get_stats()
        self.assertEqual(writer_stats.accepted_records, 5)
        self.assertGreaterEqual(writer_stats.write_failures, 1)
        self.assertEqual(writer_stats.retries_exhausted_drops, 5)
        self.assertEqual(writer_stats.successful_writes, 0)


if __name__ == "__main__":
    unittest.main()
