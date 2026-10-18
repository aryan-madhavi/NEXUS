"""Unit tests for the NEXUS MQTT Transport Adapter."""

import unittest
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from ground_station.connection_manager.mqtt_adapter import (
    MqttConfig,
    MqttTransportAdapter,
)


@dataclass
class MockMqttMessage:
    topic: str
    payload: bytes
    qos: int = 1


class MockMqttClient:
    """In-memory mock for Paho MQTT Client simulating callbacks and network actions."""

    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.connected_host: Optional[str] = None
        self.connected_port: Optional[int] = None
        self.subscribed_topics: List[str] = []
        self.loop_started = False
        self.disconnected = False

        # Callback slots matching Paho client
        self.on_connect: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None
        self.on_subscribe: Optional[Callable] = None
        self.on_message: Optional[Callable] = None

    def username_pw_set(self, username: Optional[str], password: Optional[str] = None) -> None:
        self.username = username
        self.password = password

    def connect_async(self, host: str, port: int, keepalive: int = 60) -> None:
        self.connected_host = host
        self.connected_port = port

    def loop_start(self) -> None:
        self.loop_started = True

    def loop_stop(self) -> None:
        self.loop_started = False

    def subscribe(self, topic: str, qos: int = 1) -> None:
        self.subscribed_topics.append(topic)

    def disconnect(self) -> None:
        self.disconnected = True


class TestMqttTransportAdapter(unittest.TestCase):
    """Test suite for MqttTransportAdapter using controlled in-memory mock Paho client."""

    def test_no_connection_on_import_or_construction(self):
        adapter = MqttTransportAdapter()
        self.assertFalse(adapter.is_running)
        self.assertFalse(adapter.is_connected)
        self.assertIsNone(adapter._client)

    def test_start_connects_and_subscribes(self):
        mock_client = MockMqttClient("test_client")
        config = MqttConfig(
            host="127.0.0.1",
            port=1883,
            client_factory=lambda cid: mock_client,
        )
        adapter = MqttTransportAdapter(config=config)
        adapter.start(lambda name, data: None)

        self.assertTrue(adapter.is_running)
        self.assertTrue(mock_client.loop_started)
        self.assertEqual(mock_client.connected_host, "127.0.0.1")

        # Simulate Paho on_connect event (reason_code=0 / Success)
        mock_client.on_connect(mock_client, None, {}, 0)

        self.assertTrue(adapter.is_connected)
        self.assertIn("nexus/+/telemetry", mock_client.subscribed_topics)

        stats = adapter.get_stats()
        self.assertEqual(stats.connect_count, 1)

        adapter.stop()
        self.assertFalse(adapter.is_running)
        self.assertTrue(mock_client.disconnected)

    def test_valid_telemetry_message_forwarding(self):
        mock_client = MockMqttClient("test_client")
        config = MqttConfig(client_factory=lambda cid: mock_client)
        adapter = MqttTransportAdapter(config=config)

        received_payloads = []
        adapter.start(lambda name, data: received_payloads.append(data))
        mock_client.on_connect(mock_client, None, {}, 0)

        valid_payload = b'{"ver":1,"dev":"nexus_esp32","seq":10,"type":"hb","uptime":1000,"heap":200000,"ticks":10}'
        msg = MockMqttMessage(topic="nexus/nexus_esp32/telemetry", payload=valid_payload)
        mock_client.on_message(mock_client, None, msg)

        self.assertEqual(len(received_payloads), 1)
        self.assertEqual(received_payloads[0], valid_payload)

        stats = adapter.get_stats()
        self.assertEqual(stats.messages_received, 1)
        self.assertEqual(stats.messages_forwarded, 1)
        self.assertEqual(stats.topic_mismatch_errors, 0)
        self.assertEqual(stats.identity_mismatch_errors, 0)

        adapter.stop()

    def test_unexpected_topic_rejected(self):
        mock_client = MockMqttClient("test_client")
        config = MqttConfig(client_factory=lambda cid: mock_client)
        adapter = MqttTransportAdapter(config=config)

        received_payloads = []
        adapter.start(lambda name, data: received_payloads.append(data))
        mock_client.on_connect(mock_client, None, {}, 0)

        # Message on unexpected topic (e.g. alerts or wrong prefix)
        msg1 = MockMqttMessage(
            topic="nexus/nexus_esp32/alerts",
            payload=b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}',
        )
        msg2 = MockMqttMessage(
            topic="other_prefix/nexus_esp32/telemetry",
            payload=b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}',
        )

        mock_client.on_message(mock_client, None, msg1)
        mock_client.on_message(mock_client, None, msg2)

        self.assertEqual(len(received_payloads), 0)
        stats = adapter.get_stats()
        self.assertEqual(stats.messages_received, 2)
        self.assertEqual(stats.messages_forwarded, 0)
        self.assertEqual(stats.topic_mismatch_errors, 2)

        adapter.stop()

    def test_device_identity_mismatch_quarantined(self):
        mock_client = MockMqttClient("test_client")
        config = MqttConfig(client_factory=lambda cid: mock_client)
        adapter = MqttTransportAdapter(config=config)

        received_payloads = []
        adapter.start(lambda name, data: received_payloads.append(data))
        mock_client.on_connect(mock_client, None, {}, 0)

        # Topic claims "nexus_esp32_primary", but payload claims "dev": "nexus_esp32_imposter"
        mismatch_payload = b'{"ver":1,"dev":"nexus_esp32_imposter","seq":1,"type":"hb","uptime":100,"heap":200000,"ticks":10}'
        msg = MockMqttMessage(
            topic="nexus/nexus_esp32_primary/telemetry",
            payload=mismatch_payload,
        )
        mock_client.on_message(mock_client, None, msg)

        # Must be quarantined/dropped: never forwarded to manager
        self.assertEqual(len(received_payloads), 0)
        stats = adapter.get_stats()
        self.assertEqual(stats.identity_mismatch_errors, 1)
        self.assertEqual(stats.messages_forwarded, 0)

        adapter.stop()

    def test_disconnect_callback_handling(self):
        mock_client = MockMqttClient("test_client")
        config = MqttConfig(client_factory=lambda cid: mock_client)
        adapter = MqttTransportAdapter(config=config)
        adapter.start(lambda name, data: None)
        mock_client.on_connect(mock_client, None, {}, 0)
        self.assertTrue(adapter.is_connected)

        # Trigger disconnect callback
        mock_client.on_disconnect(mock_client, None, 0)
        self.assertFalse(adapter.is_connected)

        stats = adapter.get_stats()
        self.assertEqual(stats.disconnect_count, 1)

        adapter.stop()

    def test_config_defaults_and_repr_masking(self):
        config = MqttConfig(password="super_secret_broker_password")
        self.assertEqual(config.host, "localhost")
        self.assertEqual(config.port, 1883)
        self.assertEqual(config.client_id, "nexus_ground_station")
        self.assertEqual(config.keepalive_sec, 60)
        self.assertIsNone(config.username)
        self.assertEqual(config.password, "super_secret_broker_password")

        # Repr must mask the password with ***
        rep = repr(config)
        self.assertIn("password='***'", rep)
        self.assertNotIn("super_secret_broker_password", rep)

    def test_config_from_env(self):
        custom_env = {
            "MQTT_HOST": "192.168.1.100",
            "MQTT_PORT": "8883",
            "MQTT_CLIENT_ID": "custom_station",
            "MQTT_KEEPALIVE_SEC": "120",
            "MQTT_USERNAME": "nexus_user",
            "MQTT_PASSWORD": "secret_password",
            "MQTT_TOPIC_SUBSCRIPTION": "custom/+/telemetry",
            "MQTT_TOPIC_REGEX": r"^custom/(?P<device_id>[^/]+)/telemetry$",
        }
        config = MqttConfig.from_env(custom_env)
        self.assertEqual(config.host, "192.168.1.100")
        self.assertEqual(config.port, 8883)
        self.assertEqual(config.client_id, "custom_station")
        self.assertEqual(config.keepalive_sec, 120)
        self.assertEqual(config.username, "nexus_user")
        self.assertEqual(config.password, "secret_password")
        self.assertEqual(config.topic_subscription, "custom/+/telemetry")

        # Invalid port/keepalive integer falls back gracefully
        fallback_env = {
            "MQTT_PORT": "not_an_int",
            "MQTT_KEEPALIVE_SEC": "invalid",
        }
        config_fallback = MqttConfig.from_env(fallback_env)
        self.assertEqual(config_fallback.port, 1883)
        self.assertEqual(config_fallback.keepalive_sec, 60)


if __name__ == "__main__":
    unittest.main()

