"""Integration tests for Serial and MQTT Adapters interacting with NexusHostManager."""

import time
import unittest

from ground_station.connection_manager.envelope_parser import MessageType
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
from ground_station.tests.test_mqtt_adapter import MockMqttClient, MockMqttMessage
from ground_station.tests.test_serial_adapter import MockSerialPort


class TestTransportIntegration(unittest.TestCase):
    """Integration suite verifying concurrent serial and MQTT transports with host manager."""

    def test_dual_transports_feeding_same_manager(self):
        manager = NexusHostManager(queue_capacity=50)

        # Serial setup
        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(port="/dev/test_serial", serial_factory=lambda *a, **kw: serial_port),
            name="serial",
        )

        # MQTT setup
        mqtt_client = MockMqttClient("test_gw")
        mqtt_adapter = MqttTransportAdapter(
            config=MqttConfig(client_factory=lambda cid: mqtt_client),
            name="mqtt",
        )

        manager.register_transport(serial_adapter)
        manager.register_transport(mqtt_adapter)
        manager.start()

        # Connect MQTT
        mqtt_client.on_connect(mqtt_client, None, {}, 0)

        # 1. Feed heartbeat over Serial
        serial_msg = b'{"ver":1,"dev":"nexus_esp32","seq":100,"type":"hb","uptime":1000,"heap":250000,"ticks":10}\n'
        serial_port.feed_bytes(serial_msg)

        # 2. Feed telemetry over MQTT
        mqtt_msg = MockMqttMessage(
            topic="nexus/nexus_esp32/telemetry",
            payload=b'{"ver":1,"dev":"nexus_esp32","seq":101,"type":"telem","uptime":1010,"ldr":500,"x0":100,"temp":24,"hum":60,"dht_valid":true}\n',
        )
        mqtt_client.on_message(mqtt_client, None, mqtt_msg)

        start = time.monotonic()
        while time.monotonic() - start < 1.0:
            if manager.get_stats().messages_parsed == 2:
                break
            time.sleep(0.01)

        # Verify manager received both envelopes
        stats = manager.get_stats()
        self.assertEqual(stats.messages_received, 2)
        self.assertEqual(stats.messages_parsed, 2)
        self.assertEqual(stats.enqueued_count, 2)
        self.assertEqual(stats.queue_size, 2)

        # Consume from queue
        e1 = manager.get_envelope_nowait()
        e2 = manager.get_envelope_nowait()

        self.assertIsNotNone(e1)
        self.assertIsNotNone(e2)
        self.assertEqual({e1.msg_type, e2.msg_type}, {MessageType.HEARTBEAT, MessageType.TELEMETRY})

        # Verify device tracker has both transports recorded for nexus_esp32
        dev = manager.tracker.get_device("nexus_esp32")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.total_accepted, 2)
        self.assertIn("serial", dev.transports)
        self.assertIn("mqtt", dev.transports)

        manager.stop()

    def test_failing_transport_does_not_disrupt_healthy_transport(self):
        manager = NexusHostManager(queue_capacity=50)

        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(
                port="/dev/test_serial",
                reconnect_enabled=False,
                serial_factory=lambda *a, **kw: serial_port,
            ),
            name="serial",
        )

        mqtt_client = MockMqttClient("test_gw")
        mqtt_adapter = MqttTransportAdapter(
            config=MqttConfig(client_factory=lambda cid: mqtt_client),
            name="mqtt",
        )

        manager.register_transport(serial_adapter)
        manager.register_transport(mqtt_adapter)
        manager.start()

        mqtt_client.on_connect(mqtt_client, None, {}, 0)

        # Inject fatal I/O error into Serial port
        try:
            import serial
            serial_port.raise_on_read = serial.SerialException("Hardware USB disconnect")
        except ImportError:
            serial_port.raise_on_read = OSError("Hardware USB disconnect")
        time.sleep(0.05)

        # Serial should now be disconnected
        self.assertFalse(serial_adapter.is_connected)

        # MQTT must continue receiving and processing messages normally
        mqtt_msg = MockMqttMessage(
            topic="nexus/nexus_esp32/telemetry",
            payload=b'{"ver":1,"dev":"nexus_esp32","seq":201,"type":"cmd"}\n',
        )
        mqtt_client.on_message(mqtt_client, None, mqtt_msg)

        stats = manager.get_stats()
        self.assertEqual(stats.messages_parsed, 1)
        self.assertEqual(stats.enqueued_count, 1)

        env = manager.get_envelope_nowait()
        self.assertIsNotNone(env)
        self.assertEqual(env.seq, 201)

        manager.stop()

    def test_queue_overflow_drop_accounting_with_mixed_adapters(self):
        # Small queue capacity = 3
        manager = NexusHostManager(queue_capacity=3, queue_policy=QueueFullPolicy.DROP_NEWEST)

        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(port="/dev/test_serial", serial_factory=lambda *a, **kw: serial_port),
            name="serial",
        )

        mqtt_client = MockMqttClient("test_gw")
        mqtt_adapter = MqttTransportAdapter(
            config=MqttConfig(client_factory=lambda cid: mqtt_client),
            name="mqtt",
        )

        manager.register_transport(serial_adapter)
        manager.register_transport(mqtt_adapter)
        manager.start()
        mqtt_client.on_connect(mqtt_client, None, {}, 0)

        # Fill queue with 3 messages (2 from serial, 1 from MQTT)
        serial_port.feed_bytes(b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n')
        serial_port.feed_bytes(b'{"ver":1,"dev":"nexus_esp32","seq":2,"type":"cmd"}\n')
        time.sleep(0.05)

        mqtt_client.on_message(
            mqtt_client,
            None,
            MockMqttMessage(
                topic="nexus/nexus_esp32/telemetry",
                payload=b'{"ver":1,"dev":"nexus_esp32","seq":3,"type":"cmd"}\n',
            ),
        )

        # 4th message from MQTT exceeds capacity
        mqtt_client.on_message(
            mqtt_client,
            None,
            MockMqttMessage(
                topic="nexus/nexus_esp32/telemetry",
                payload=b'{"ver":1,"dev":"nexus_esp32","seq":4,"type":"cmd"}\n',
            ),
        )

        stats = manager.get_stats()
        self.assertEqual(stats.enqueued_count, 3)
        self.assertEqual(stats.dropped_count, 1)
        self.assertEqual(stats.queue_size, 3)

        manager.stop()

    def test_repeated_start_stop_lifecycle(self):
        manager = NexusHostManager()
        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(port="/dev/test_serial", serial_factory=lambda *a, **kw: serial_port),
            name="serial",
        )
        mqtt_client = MockMqttClient("test_gw")
        mqtt_adapter = MqttTransportAdapter(
            config=MqttConfig(client_factory=lambda cid: mqtt_client),
            name="mqtt",
        )

        manager.register_transport(serial_adapter)
        manager.register_transport(mqtt_adapter)

        # Start and stop multiple times
        for _ in range(3):
            manager.start()
            self.assertTrue(manager.is_running)
            self.assertTrue(serial_adapter.is_running)
            self.assertTrue(mqtt_adapter.is_running)

            manager.stop()
            self.assertFalse(manager.is_running)
            self.assertFalse(serial_adapter.is_running)
            self.assertFalse(mqtt_adapter.is_running)

    def test_shutdown_blocks_subsequent_callback_ingestion(self):
        manager = NexusHostManager()
        mqtt_client = MockMqttClient("test_gw")
        mqtt_adapter = MqttTransportAdapter(
            config=MqttConfig(client_factory=lambda cid: mqtt_client),
            name="mqtt",
        )
        manager.register_transport(mqtt_adapter)
        manager.start()
        manager.stop()

        # Direct manager callback invocation while stopped must be rejected
        res = manager.handle_raw_message("serial", b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n')
        self.assertFalse(res)
        self.assertEqual(manager.get_stats().messages_received, 0)
        self.assertEqual(manager.get_stats().queue_size, 0)

        # MQTT callback while adapter is stopped must be ignored
        msg = MockMqttMessage(
            topic="nexus/nexus_esp32/telemetry",
            payload=b'{"ver":1,"dev":"nexus_esp32","seq":2,"type":"cmd"}\n',
        )
        mqtt_client.on_message(mqtt_client, None, msg)
        self.assertEqual(mqtt_adapter.get_stats().messages_received, 0)
        self.assertEqual(manager.get_stats().messages_received, 0)


if __name__ == "__main__":
    unittest.main()
