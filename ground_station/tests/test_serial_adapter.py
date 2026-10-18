"""Unit tests for the NEXUS Serial Transport Adapter."""

import threading
import time
import unittest
from typing import List

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    serial = None
    HAS_SERIAL = False

from ground_station.connection_manager.serial_adapter import (
    SerialConfig,
    SerialTransportAdapter,
)


class MockSerialPort:
    """In-memory mock for serial.Serial simulating chunks, timeouts, and disconnects."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.2,
        rtscts: bool = False,
        dsrdtr: bool = False,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.rtscts = rtscts
        self.dsrdtr = dsrdtr
        self.is_open = True
        self.dtr = False
        self.rts = False
        self._chunks: List[bytes] = []
        self._lock = threading.Lock()
        self.raise_on_read: Exception | None = None
        self.closed_count = 0

    def feed_bytes(self, data: bytes) -> None:
        with self._lock:
            self._chunks.append(data)

    def read(self, size: int = 128) -> bytes:
        if not self.is_open:
            if serial is not None:
                raise serial.SerialException("Port is closed")
            raise OSError("Port is closed")

        if self.raise_on_read:
            raise self.raise_on_read

        with self._lock:
            if self._chunks:
                chunk = self._chunks.pop(0)
                if len(chunk) <= size:
                    return chunk
                # Return size, retain remainder
                ret = chunk[:size]
                self._chunks.insert(0, chunk[size:])
                return ret
        time.sleep(0.01)
        return b""

    def close(self) -> None:
        self.is_open = False
        self.closed_count += 1


@unittest.skipUnless(HAS_SERIAL, "pyserial is not installed in this environment")
class TestSerialTransportAdapter(unittest.TestCase):
    """Test suite for SerialTransportAdapter using controlled in-memory serial mocks."""

    def test_no_device_opened_on_import_or_construction(self):
        # Construction must not open any ports or access hardware
        config = SerialConfig(port="/dev/nonexistent_test_port")
        adapter = SerialTransportAdapter(config=config)
        self.assertFalse(adapter.is_running)
        self.assertFalse(adapter.is_connected)
        self.assertIsNone(adapter._serial_port)

    def test_hardware_safety_no_rts_dtr_reset(self):
        created_ports: List[MockSerialPort] = []

        def factory(*args, **kwargs):
            p = MockSerialPort(*args, **kwargs)
            created_ports.append(p)
            return p

        config = SerialConfig(
            port="/dev/test_port",
            serial_factory=factory,
            reconnect_enabled=False,
        )
        adapter = SerialTransportAdapter(config=config)
        adapter.start(lambda name, data: None)
        time.sleep(0.05)
        adapter.stop()

        self.assertEqual(len(created_ports), 1)
        p = created_ports[0]
        # Assert DTR and RTS are not asserted and hardware flow control is disabled
        self.assertFalse(p.dtr)
        self.assertFalse(p.rts)
        self.assertFalse(p.rtscts)
        self.assertFalse(p.dsrdtr)
        self.assertFalse(p.is_open)

    def test_single_and_multiple_frames_in_one_read(self):
        received_frames = []
        frame1 = b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n'
        frame2 = b'{"ver":1,"dev":"nexus_esp32","seq":2,"type":"cmd"}\n'

        mock_port = MockSerialPort(port="/dev/test")
        mock_port.feed_bytes(frame1 + frame2)

        config = SerialConfig(
            port="/dev/test",
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        adapter.start(lambda name, data: received_frames.append(data))

        time.sleep(0.08)
        adapter.stop()

        self.assertEqual(len(received_frames), 2)
        self.assertEqual(received_frames[0], frame1)
        self.assertEqual(received_frames[1], frame2)

    def test_partial_reads_and_fragmented_frames(self):
        received_frames = []
        full_msg = b'{"ver":1,"dev":"nexus_esp32","seq":10,"type":"telem","uptime":100,"ldr":10,"x0":20,"dht_valid":false}\n'

        mock_port = MockSerialPort(port="/dev/test")
        # Split message into 3 small fragments
        mock_port.feed_bytes(full_msg[:20])
        mock_port.feed_bytes(full_msg[20:50])
        mock_port.feed_bytes(full_msg[50:])

        config = SerialConfig(
            port="/dev/test",
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        adapter.start(lambda name, data: received_frames.append(data))

        time.sleep(0.1)
        adapter.stop()

        self.assertEqual(len(received_frames), 1)
        self.assertEqual(received_frames[0], full_msg)

    def test_crlf_and_lf_framing_and_empty_lines(self):
        received_frames = []
        lf_msg = b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n'
        crlf_msg = b'{"ver":1,"dev":"nexus_esp32","seq":2,"type":"cmd"}\r\n'
        empty_lines = b'\n\r\n\n'

        mock_port = MockSerialPort(port="/dev/test")
        mock_port.feed_bytes(empty_lines + lf_msg + empty_lines + crlf_msg + empty_lines)

        config = SerialConfig(
            port="/dev/test",
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        adapter.start(lambda name, data: received_frames.append(data))

        time.sleep(0.08)
        adapter.stop()

        self.assertEqual(len(received_frames), 2)
        self.assertEqual(received_frames[0], lf_msg)
        self.assertEqual(received_frames[1], crlf_msg)

    def test_oversized_frame_discarded(self):
        received_frames = []
        # Oversized line > 256 bytes
        oversized = b'{"ver":1,"dev":"nexus_esp32","pad":"' + (b"X" * 260) + b'"}\n'
        valid_after = b'{"ver":1,"dev":"nexus_esp32","seq":99,"type":"cmd"}\n'

        mock_port = MockSerialPort(port="/dev/test")
        mock_port.feed_bytes(oversized + valid_after)

        config = SerialConfig(
            port="/dev/test",
            max_frame_bytes=256,
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        adapter.start(lambda name, data: received_frames.append(data))

        time.sleep(0.08)
        adapter.stop()

        # Oversized frame must be discarded; valid frame must be received
        self.assertEqual(len(received_frames), 1)
        self.assertEqual(received_frames[0], valid_after)

        stats = adapter.get_stats()
        self.assertEqual(stats.frames_dropped_oversized, 1)

    def test_buffer_ceiling_protection_on_missing_newlines(self):
        # Continuous stream without newlines should not grow memory unboundedly
        mock_port = MockSerialPort(port="/dev/test")
        # Feed 1500 bytes with newline to trigger buffer ceiling and oversized discard
        mock_port.feed_bytes(b"A" * 1500 + b"\n")
        # Then feed a valid line
        valid_line = b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd"}\n'
        mock_port.feed_bytes(valid_line)

        config = SerialConfig(
            port="/dev/test",
            max_buffer_bytes=1000,
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        received_frames = []
        adapter.start(lambda name, data: received_frames.append(data))

        start = time.monotonic()
        while time.monotonic() - start < 1.0:
            if received_frames:
                break
            time.sleep(0.01)
        adapter.stop()

        stats = adapter.get_stats()
        self.assertGreaterEqual(stats.framing_errors, 1)
        self.assertIn(valid_line, received_frames)

    def test_disconnect_and_reconnect_lifecycle(self):
        mock_port1 = MockSerialPort(port="/dev/test")
        mock_port2 = MockSerialPort(port="/dev/test")
        ports = [mock_port1, mock_port2]

        def factory(*args, **kwargs):
            if ports:
                return ports.pop(0)
            p = MockSerialPort(*args, **kwargs)
            return p

        config = SerialConfig(
            port="/dev/test",
            reconnect_enabled=True,
            reconnect_base_delay_sec=0.02,
            reconnect_max_delay_sec=0.05,
            serial_factory=factory,
        )
        adapter = SerialTransportAdapter(config=config)
        received = []
        adapter.start(lambda name, data: received.append(data))

        time.sleep(0.05)
        self.assertTrue(adapter.is_connected)

        # Trigger disconnect on port 1
        mock_port1.raise_on_read = serial.SerialException("Device disconnected")
        time.sleep(0.08)

        # Port 2 should be connected upon reconnect
        valid = b'{"ver":1,"dev":"nexus_esp32","seq":200,"type":"cmd"}\n'
        mock_port2.feed_bytes(valid)
        time.sleep(0.08)

        adapter.stop()

        stats = adapter.get_stats()
        self.assertGreaterEqual(stats.disconnect_count, 1)
        self.assertGreaterEqual(stats.connect_count, 2)
        self.assertIn(valid, received)

    def test_deterministic_shutdown_while_waiting_or_reading(self):
        mock_port = MockSerialPort(port="/dev/test")
        config = SerialConfig(
            port="/dev/test",
            read_timeout_sec=0.5,
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        adapter.start(lambda name, data: None)
        time.sleep(0.05)
        self.assertTrue(adapter.is_running)

        start_stop = time.monotonic()
        adapter.stop()
        stop_duration = time.monotonic() - start_stop

        # Stop must be fast and deterministic (< 1.0s), not hung on read
        self.assertLess(stop_duration, 1.0)
        self.assertFalse(adapter.is_running)
        self.assertFalse(mock_port.is_open)

    def test_exact_255_256_boundary_limits(self):
        # Firmware buffer is 256 bytes; with NUL, max wire length is 255.
        # Exactly 255 bytes: must be accepted and forwarded.
        # Exactly 256 bytes: must be rejected as oversized.
        prefix = b'{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd","pad":"'
        pad_255 = 255 - len(prefix) - 3  # for '\"}\n'
        frame_255 = prefix + (b"A" * pad_255) + b'"}\n'
        self.assertEqual(len(frame_255), 255)

        pad_256 = 256 - len(prefix) - 3
        frame_256 = prefix + (b"B" * pad_256) + b'"}\n'
        self.assertEqual(len(frame_256), 256)

        mock_port = MockSerialPort(port="/dev/test")
        mock_port.feed_bytes(frame_256 + frame_255)

        config = SerialConfig(
            port="/dev/test",
            max_frame_bytes=256,
            serial_factory=lambda *a, **kw: mock_port,
        )
        adapter = SerialTransportAdapter(config=config)
        received_frames = []
        adapter.start(lambda name, data: received_frames.append(data))

        time.sleep(0.08)
        adapter.stop()

        # frame_256 must be dropped as oversized, frame_255 must be received
        self.assertEqual(len(received_frames), 1)
        self.assertEqual(received_frames[0], frame_255)

        stats = adapter.get_stats()
        self.assertEqual(stats.frames_dropped_oversized, 1)
        self.assertEqual(stats.frames_forwarded, 1)

    def test_open_serial_with_real_pty(self):
        """Verify _open_serial against a real POSIX pseudo-terminal with DTR/RTS protection."""
        import os
        import pty

        master, slave = pty.openpty()
        slave_name = os.ttyname(slave)
        try:
            config = SerialConfig(port=slave_name, serial_factory=None)
            adapter = SerialTransportAdapter(config=config)
            ser = adapter._open_serial()
            self.assertTrue(ser.is_open)
            self.assertFalse(ser.dtr)
            self.assertFalse(ser.rts)
            ser.close()
        finally:
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
