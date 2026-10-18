"""Unit tests for the NEXUS Host Connection Manager."""

import threading
import time
import unittest

from ground_station.connection_manager.envelope_parser import MessageType
from ground_station.connection_manager.nexus_host_manager import (
    NexusHostManager,
    QueueFullPolicy,
)
from ground_station.tests.fake_transports import AsyncThreadedFakeTransport, FakeTransport


class TestNexusHostManager(unittest.TestCase):
    """Test suite for host connection manager and queue lifecycle."""

    def test_basic_ingestion_and_consumption(self):
        manager = NexusHostManager(queue_capacity=10)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)
        manager.start()

        msg = '{"ver":1,"dev":"nexus_esp32","seq":100,"type":"hb","uptime":12000,"heap":250000,"ticks":50}\n'
        transport.feed(msg)

        stats = manager.get_stats()
        self.assertEqual(stats.messages_received, 1)
        self.assertEqual(stats.messages_parsed, 1)
        self.assertEqual(stats.parse_errors, 0)
        self.assertEqual(stats.enqueued_count, 1)
        self.assertEqual(stats.dropped_count, 0)
        self.assertEqual(stats.queue_size, 1)
        self.assertEqual(stats.queue_hwm, 1)

        # Consume from downstream queue
        env = manager.get_envelope(timeout=0.1)
        self.assertIsNotNone(env)
        self.assertEqual(env.seq, 100)
        self.assertEqual(env.msg_type, MessageType.HEARTBEAT)

        stats2 = manager.get_stats()
        self.assertEqual(stats2.dequeued_count, 1)
        self.assertEqual(stats2.queue_size, 0)

        manager.stop()
        self.assertFalse(manager.is_running)

    def test_queue_overflow_drop_newest(self):
        # Small bounded queue with capacity = 3
        manager = NexusHostManager(queue_capacity=3, queue_policy=QueueFullPolicy.DROP_NEWEST)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)
        manager.start()

        # Feed 3 items to fill capacity
        for seq in (1, 2, 3):
            transport.feed(f'{{"ver":1,"dev":"nexus_esp32","seq":{seq},"type":"cmd"}}\n')

        stats = manager.get_stats()
        self.assertEqual(stats.enqueued_count, 3)
        self.assertEqual(stats.dropped_count, 0)
        self.assertEqual(stats.queue_size, 3)
        self.assertEqual(stats.queue_hwm, 3)

        # Feed 4th item -> must be dropped according to DROP_NEWEST
        transport.feed('{"ver":1,"dev":"nexus_esp32","seq":4,"type":"cmd"}\n')

        stats = manager.get_stats()
        self.assertEqual(stats.enqueued_count, 3)
        self.assertEqual(stats.dropped_count, 1)
        self.assertEqual(stats.queue_size, 3)

        # Verify the 3 queued items are seq 1, 2, 3 (seq 4 was dropped)
        e1 = manager.get_envelope_nowait()
        e2 = manager.get_envelope_nowait()
        e3 = manager.get_envelope_nowait()
        e4 = manager.get_envelope_nowait()

        self.assertIsNotNone(e1)
        self.assertIsNotNone(e2)
        self.assertIsNotNone(e3)
        self.assertIsNone(e4)
        self.assertEqual([e1.seq, e2.seq, e3.seq], [1, 2, 3])

        manager.stop()

    def test_queue_overflow_drop_oldest(self):
        # Bounded queue with capacity = 3 and DROP_OLDEST
        manager = NexusHostManager(queue_capacity=3, queue_policy=QueueFullPolicy.DROP_OLDEST)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)
        manager.start()

        # Feed seq 1, 2, 3
        for seq in (1, 2, 3):
            transport.feed(f'{{"ver":1,"dev":"nexus_esp32","seq":{seq},"type":"cmd"}}\n')

        # Feed seq 4 -> seq 1 should be evicted, seq 4 enqueued
        transport.feed('{"ver":1,"dev":"nexus_esp32","seq":4,"type":"cmd"}\n')

        stats = manager.get_stats()
        self.assertEqual(stats.dropped_count, 1)
        self.assertEqual(stats.enqueued_count, 4)
        self.assertEqual(stats.queue_size, 3)

        # Verify queued items are seq 2, 3, 4
        e_first = manager.get_envelope_nowait()
        e_second = manager.get_envelope_nowait()
        e_third = manager.get_envelope_nowait()

        self.assertIsNotNone(e_first)
        self.assertIsNotNone(e_second)
        self.assertIsNotNone(e_third)
        self.assertEqual([e_first.seq, e_second.seq, e_third.seq], [2, 3, 4])

        manager.stop()

    def test_error_isolation_malformed_messages_do_not_disrupt_valid(self):
        manager = NexusHostManager(queue_capacity=10)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)
        manager.start()

        # 1. Feed malformed JSON
        transport.feed('{"broken":json\n')
        # 2. Feed oversized frame (> 256 bytes)
        transport.feed("X" * 300 + "\n")
        # 3. Feed unsupported version
        transport.feed('{"ver":99,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n')
        # 4. Feed unknown message type
        transport.feed('{"ver":1,"dev":"nexus_esp32","seq":2,"type":"bogus"}\n')

        stats = manager.get_stats()
        self.assertEqual(stats.messages_received, 4)
        self.assertEqual(stats.messages_parsed, 0)
        self.assertEqual(stats.parse_errors, 4)
        self.assertEqual(stats.enqueued_count, 0)

        # 5. Now feed a valid message -> must succeed seamlessly
        transport.feed('{"ver":1,"dev":"nexus_esp32","seq":500,"type":"hb","uptime":5000,"heap":200000,"ticks":50}\n')

        stats2 = manager.get_stats()
        self.assertEqual(stats2.messages_received, 5)
        self.assertEqual(stats2.messages_parsed, 1)
        self.assertEqual(stats2.enqueued_count, 1)

        env = manager.get_envelope_nowait()
        self.assertIsNotNone(env)
        self.assertEqual(env.seq, 500)

        manager.stop()

    def test_start_stop_lifecycle_and_idempotence(self):
        manager = NexusHostManager()
        t1 = FakeTransport(name="t1")
        t2 = FakeTransport(name="t2")

        manager.register_transport(t1)
        manager.register_transport(t2)

        self.assertFalse(manager.is_running)
        self.assertFalse(t1.is_running)
        self.assertFalse(t2.is_running)

        # Start manager
        manager.start()
        self.assertTrue(manager.is_running)
        self.assertTrue(t1.is_running)
        self.assertTrue(t2.is_running)

        # Redundant start is a no-op
        manager.start()
        self.assertTrue(manager.is_running)

        # Registering an adapter while already running starts it immediately
        t3 = FakeTransport(name="t3")
        manager.register_transport(t3)
        self.assertTrue(t3.is_running)

        # Stop manager
        manager.stop()
        self.assertFalse(manager.is_running)
        self.assertFalse(t1.is_running)
        self.assertFalse(t2.is_running)
        self.assertFalse(t3.is_running)

        # Redundant stop is safe
        manager.stop()
        self.assertFalse(manager.is_running)

    def test_multi_transport_and_multi_device_tracking(self):
        manager = NexusHostManager(queue_capacity=20)
        t_serial = FakeTransport(name="serial")
        t_mqtt = FakeTransport(name="mqtt")

        manager.register_transport(t_serial)
        manager.register_transport(t_mqtt)
        manager.start()

        # Serial message from dev A
        t_serial.feed('{"ver":1,"dev":"dev_alpha","seq":1,"type":"hb","uptime":100,"heap":200000,"ticks":10}\n')
        # MQTT message from dev B
        t_mqtt.feed('{"ver":1,"dev":"dev_beta","seq":10,"type":"hb","uptime":200,"heap":190000,"ticks":20}\n')
        # MQTT message from dev A
        t_mqtt.feed('{"ver":1,"dev":"dev_alpha","seq":2,"type":"hb","uptime":150,"heap":195000,"ticks":15}\n')

        stats = manager.get_stats()
        self.assertEqual(stats.messages_received, 3)
        self.assertEqual(stats.messages_parsed, 3)
        self.assertEqual(stats.enqueued_count, 3)

        summary = stats.device_summary
        self.assertEqual(summary["total_accepted"], 3)
        self.assertEqual(summary["device_count"], 2)
        self.assertIn("dev_alpha", summary["devices"])
        self.assertIn("dev_beta", summary["devices"])

        # Check dev_alpha has both transports recorded
        dev_alpha = manager.tracker.get_device("dev_alpha")
        self.assertIsNotNone(dev_alpha)
        self.assertEqual(dev_alpha.total_accepted, 2)
        self.assertIn("serial", dev_alpha.transports)
        self.assertIn("mqtt", dev_alpha.transports)

        manager.stop()

    def test_concurrent_producers_and_consumer(self):
        """Verify thread safety with concurrent background producers and consumer."""
        manager = NexusHostManager(queue_capacity=50)

        # Create two async transports
        producer1 = AsyncThreadedFakeTransport(name="producer_1")
        producer2 = AsyncThreadedFakeTransport(name="producer_2")

        # Schedule 30 messages on each producer
        p1_msgs = [
            f'{{"ver":1,"dev":"dev_1","seq":{i},"type":"cmd"}}\n'
            for i in range(1, 31)
        ]
        p2_msgs = [
            f'{{"ver":1,"dev":"dev_2","seq":{i},"type":"cmd"}}\n'
            for i in range(1, 31)
        ]

        producer1.schedule_payloads(p1_msgs)
        producer2.schedule_payloads(p2_msgs)

        manager.register_transport(producer1)
        manager.register_transport(producer2)

        consumed_items = []
        stop_consumer = threading.Event()

        def consumer_worker():
            while not stop_consumer.is_set():
                item = manager.get_envelope(timeout=0.01)
                if item is not None:
                    consumed_items.append(item)

        consumer_thread = threading.Thread(target=consumer_worker, daemon=True)
        consumer_thread.start()

        # Start manager (starts producers)
        manager.start()

        # Wait for producers to finish emitting
        max_wait = 2.0
        start_time = time.monotonic()
        while time.monotonic() - start_time < max_wait:
            if producer1.emitted_count == 30 and producer2.emitted_count == 30:
                break
            time.sleep(0.01)

        # Allow consumer a moment to drain
        drain_start = time.monotonic()
        while time.monotonic() - drain_start < 1.0:
            if len(consumed_items) == 60:
                break
            time.sleep(0.01)

        stop_consumer.set()
        consumer_thread.join(timeout=1.0)
        manager.stop()

        stats = manager.get_stats()
        self.assertEqual(stats.messages_received, 60)
        self.assertEqual(stats.messages_parsed, 60)
        self.assertEqual(stats.parse_errors, 0)
        self.assertEqual(len(consumed_items), 60)

    def test_consumer_exception_does_not_disrupt_other_consumers(self):
        manager = NexusHostManager(queue_capacity=10)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)

        # Consumer 1 raises an unhandled exception
        def failing_consumer(env):
            raise RuntimeError("Simulated consumer crash")

        # Consumer 2 records received envelopes
        received_by_c2 = []

        def healthy_consumer(env):
            received_by_c2.append(env)

        manager.register_consumer(failing_consumer)
        manager.register_consumer(healthy_consumer)

        manager.start()

        msg = '{"ver":1,"dev":"nexus_esp32","seq":100,"type":"hb","uptime":1000,"heap":200000,"ticks":10}\n'
        transport.feed(msg)

        self.assertEqual(len(received_by_c2), 1)
        self.assertEqual(received_by_c2[0].seq, 100)

        manager.stop()

    def test_duplicate_consumer_registration_ignored(self):
        manager = NexusHostManager(queue_capacity=10)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)

        call_count = 0

        def single_consumer(env):
            nonlocal call_count
            call_count += 1

        # Register same callback multiple times
        manager.register_consumer(single_consumer)
        manager.register_consumer(single_consumer)
        manager.register_consumer(single_consumer)

        manager.start()
        transport.feed('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n')

        # Must only be called once
        self.assertEqual(call_count, 1)
        manager.stop()

    def test_concurrent_consumer_registration_unregistration(self):
        manager = NexusHostManager(queue_capacity=50)
        transport = FakeTransport(name="fake_serial")
        manager.register_transport(transport)
        manager.start()

        stop_threads = threading.Event()

        def dummy_consumer(env):
            pass

        def churn_workers():
            while not stop_threads.is_set():
                manager.register_consumer(dummy_consumer)
                time.sleep(0.001)
                manager.unregister_consumer(dummy_consumer)

        def feed_workers():
            seq = 0
            while not stop_threads.is_set():
                seq += 1
                transport.feed(f'{{"ver":1,"dev":"nexus_esp32","seq":{seq},"type":"cmd"}}\n')
                time.sleep(0.002)

        t1 = threading.Thread(target=churn_workers, daemon=True)
        t2 = threading.Thread(target=feed_workers, daemon=True)
        t1.start()
        t2.start()

        time.sleep(0.1)
        stop_threads.set()
        t1.join(timeout=1.0)
        t2.join(timeout=1.0)
        manager.stop()


if __name__ == "__main__":
    unittest.main()
