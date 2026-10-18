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
from ground_station.persistence.point_mapper import PointMapper


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

    def test_serial_firmware_compatibility_and_persistence_mapping(self):
        """Simulate realistic physical firmware UART stream through serial adapter, host manager, and point mapper.

        Validates:
        - ESP-IDF bootloader and system log lines are safely rejected as malformed JSON without disrupting stream.
        - Multiple frames in a single chunk with CRLF and LF delimiters.
        - Fragmented envelope arrival across chunk boundaries.
        - Oversized frame (>= 256 bytes) dropped by serial adapter.
        - Corrupted JSON frame parsed and rejected as parse error.
        - Firmware envelopes (hb, status, telem without DHT, telem with DHT) cleanly parsed.
        - PointMapper strictly suppresses temp and hum when dht_valid is False and includes them when True.
        - InfluxDB tags dev='nexus_esp32' and transport='serial' are accurately populated.
        """
        manager = NexusHostManager(queue_capacity=50)
        serial_port = MockSerialPort(port="/dev/test_serial")
        serial_adapter = SerialTransportAdapter(
            config=SerialConfig(
                port="/dev/test_serial",
                max_frame_bytes=256,
                serial_factory=lambda *a, **kw: serial_port,
            ),
            name="serial",
        )
        manager.register_transport(serial_adapter)
        manager.start()

        # 1. ESP-IDF boot banner (non-JSON log lines)
        boot_log1 = b"I (13) boot: ESP-IDF v6.0.1 2nd stage bootloader\n"
        boot_log2 = b"I (260) nexus_main: reset_reason=1\n"
        serial_port.feed_bytes(boot_log1 + boot_log2)

        # 2. Heartbeat frame (complete with LF)
        hb_frame = b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"hb","uptime":327,"heap":198872,"ticks":1}\n'
        serial_port.feed_bytes(hb_frame)

        # 3. Status frame with CRLF
        status_frame = b'{"ver":1,"dev":"nexus_esp32","seq":2,"type":"status","uptime":366,"disp":5,"comp":4,"fail":0,"lat_us":0,"dur_us":8945}\r\n'
        serial_port.feed_bytes(status_frame)

        # 4. Oversized frame (> 256 bytes)
        oversized = b'{"ver":1,"dev":"nexus_esp32","seq":99,"type":"cmd","payload":"' + (b"X" * 260) + b'"}\n'
        serial_port.feed_bytes(oversized)

        # 5. Malformed JSON frame
        malformed = b'{"ver":1,"dev":"nexus_esp32","seq":99,"type":BROKEN_SYNTAX\n'
        serial_port.feed_bytes(malformed)

        # 6. Fragmented Degraded Telemetry (dht_valid=false, temp/hum omitted) across 2 chunks
        degraded_telem = b'{"ver":1,"dev":"nexus_esp32","seq":3,"type":"telem","uptime":366,"ldr":0,"x0":3146,"dht_valid":false}\n'
        serial_port.feed_bytes(degraded_telem[:30])
        serial_port.feed_bytes(degraded_telem[30:])

        # 7. Valid Telemetry (dht_valid=true, temp=31, hum=74)
        valid_telem = b'{"ver":1,"dev":"nexus_esp32","seq":4,"type":"telem","uptime":2421,"ldr":0,"x0":3146,"temp":31,"hum":74,"dht_valid":true}\n'
        serial_port.feed_bytes(valid_telem)

        # Wait for all chunks to be processed
        start = time.monotonic()
        while time.monotonic() - start < 1.0:
            if manager.get_stats().enqueued_count >= 4:
                break
            time.sleep(0.01)

        manager.stop()

        # Check serial adapter metrics
        adapter_stats = serial_adapter.get_stats()
        self.assertEqual(adapter_stats.frames_dropped_oversized, 1)

        # Check host manager metrics:
        # Received: 2 boot lines + 1 hb + 1 status + 1 malformed + 1 degraded telem + 1 valid telem = 7 lines passed to manager
        # (oversized was dropped at the serial adapter layer)
        # Parsed: hb (1), status (2), degraded telem (3), valid telem (4) = 4
        # Parse errors: boot_log1, boot_log2, malformed = 3
        mgr_stats = manager.get_stats()
        self.assertEqual(mgr_stats.messages_parsed, 4)
        self.assertEqual(mgr_stats.parse_errors, 3)
        self.assertEqual(mgr_stats.enqueued_count, 4)
        self.assertEqual(mgr_stats.queue_size, 4)

        # Dequeue and map all 4 valid envelopes
        e_hb = manager.get_envelope_nowait()
        e_status = manager.get_envelope_nowait()
        e_telem_degraded = manager.get_envelope_nowait()
        e_telem_valid = manager.get_envelope_nowait()

        self.assertIsNotNone(e_hb)
        self.assertIsNotNone(e_status)
        self.assertIsNotNone(e_telem_degraded)
        self.assertIsNotNone(e_telem_valid)

        # Validate Heartbeat mapping
        d_hb = PointMapper.to_dict(e_hb)
        self.assertEqual(d_hb["measurement"], "nexus_hb")
        self.assertEqual(d_hb["tags"]["dev"], "nexus_esp32")
        self.assertEqual(d_hb["tags"]["transport"], "serial")
        self.assertEqual(d_hb["fields"]["free_heap"], 198872)
        self.assertEqual(d_hb["fields"]["exec_ticks"], 1)

        # Validate Status mapping
        d_status = PointMapper.to_dict(e_status)
        self.assertEqual(d_status["measurement"], "nexus_status")
        self.assertEqual(d_status["fields"]["dispatched"], 5)
        self.assertEqual(d_status["fields"]["completed"], 4)
        self.assertEqual(d_status["fields"]["failed"], 0)

        # Validate Degraded Telemetry mapping (Missing-Data Semantics)
        d_degraded = PointMapper.to_dict(e_telem_degraded)
        self.assertEqual(d_degraded["measurement"], "nexus_telem")
        self.assertEqual(d_degraded["tags"]["dev"], "nexus_esp32")
        self.assertEqual(d_degraded["tags"]["transport"], "serial")
        self.assertEqual(d_degraded["fields"]["dht_valid"], False)
        self.assertEqual(d_degraded["fields"]["ldr_raw"], 0)
        self.assertEqual(d_degraded["fields"]["x0_raw"], 3146)
        # temp and hum MUST NOT be present in fields
        self.assertNotIn("temp", d_degraded["fields"])
        self.assertNotIn("hum", d_degraded["fields"])

        # Validate Valid Telemetry mapping
        d_valid = PointMapper.to_dict(e_telem_valid)
        self.assertEqual(d_valid["measurement"], "nexus_telem")
        self.assertEqual(d_valid["tags"]["dev"], "nexus_esp32")
        self.assertEqual(d_valid["tags"]["transport"], "serial")
        self.assertEqual(d_valid["fields"]["dht_valid"], True)
        self.assertEqual(d_valid["fields"]["ldr_raw"], 0)
        self.assertEqual(d_valid["fields"]["x0_raw"], 3146)
        self.assertEqual(d_valid["fields"]["temp"], 31.0)
        self.assertEqual(d_valid["fields"]["hum"], 74.0)


if __name__ == "__main__":
    unittest.main()
