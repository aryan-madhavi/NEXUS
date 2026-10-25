"""NEXUS USB Serial Transport Adapter.

Reads newline-delimited JSON envelopes from the ESP32 serial interface using pyserial.
Enforces bounded memory buffering, max frame length, graceful reconnects, and
RTS/DTR reset prevention.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Union

try:
    import serial
except ImportError:
    serial = None

from .envelope_parser import NEXUS_ENVELOPE_MAX_LEN
from .nexus_host_manager import TransportAdapter

logger = logging.getLogger("nexus.serial_adapter")


@dataclass
class SerialConfig:
    """Configuration for NEXUS Serial Transport Adapter."""

    port: Optional[str] = None
    baud_rate: int = 115200
    read_timeout_sec: float = 0.2
    max_buffer_bytes: int = 4096
    max_frame_bytes: int = NEXUS_ENVELOPE_MAX_LEN
    reconnect_enabled: bool = True
    reconnect_base_delay_sec: float = 0.5
    reconnect_max_delay_sec: float = 5.0
    # Optional dependency injection for unit tests
    serial_factory: Optional[Callable[..., Any]] = None


@dataclass(frozen=True)
class SerialStats:
    """Telemetry snapshot for serial transport."""

    is_connected: bool
    connect_count: int
    disconnect_count: int
    reconnect_attempts: int
    bytes_read: int
    frames_received: int
    frames_forwarded: int
    frames_dropped_oversized: int
    framing_errors: int
    io_errors: int
    last_read_monotonic: Optional[float]
    last_read_wallclock: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_connected": self.is_connected,
            "connect_count": self.connect_count,
            "disconnect_count": self.disconnect_count,
            "reconnect_attempts": self.reconnect_attempts,
            "bytes_read": self.bytes_read,
            "frames_received": self.frames_received,
            "frames_forwarded": self.frames_forwarded,
            "frames_dropped_oversized": self.frames_dropped_oversized,
            "framing_errors": self.framing_errors,
            "io_errors": self.io_errors,
            "last_read_monotonic": self.last_read_monotonic,
            "last_read_wallclock": self.last_read_wallclock,
        }


class SerialTransportAdapter(TransportAdapter):
    """Threaded USB Serial transport adapter for NEXUS host ground station."""

    def __init__(
        self,
        config: Optional[SerialConfig] = None,
        name: str = "serial",
    ) -> None:
        self._name = name
        self._config = config or SerialConfig()
        self._is_running = False
        self._is_connected = False
        self._on_receive: Optional[Callable[[str, Union[bytes, str]], None]] = None

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._serial_port: Optional[Any] = None

        # Statistics
        self._connect_count = 0
        self._disconnect_count = 0
        self._reconnect_attempts = 0
        self._bytes_read = 0
        self._frames_received = 0
        self._frames_forwarded = 0
        self._frames_dropped_oversized = 0
        self._framing_errors = 0
        self._io_errors = 0
        self._last_read_monotonic: Optional[float] = None
        self._last_read_wallclock: Optional[float] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def start(self, on_receive: Callable[[str, Union[bytes, str]], None]) -> None:
        """Start the background serial reader worker thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._on_receive = on_receive
            self._stop_event.clear()

            self._thread = threading.Thread(
                target=self._reader_loop,
                name=f"NexusSerialReader-{self._name}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Cleanly and deterministically stop the serial reader and close port."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            self._stop_event.set()
            thread = self._thread
            self._thread = None
            port = self._serial_port
            self._serial_port = None
            self._is_connected = False

        # Close port to interrupt any active blocking reads
        if port is not None:
            try:
                port.close()
            except Exception as err:
                logger.debug("Error closing serial port: %s", err)

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _open_serial(self) -> Any:
        """Open serial port with explicit DTR/RTS reset prevention.

        Note: On classic ESP32 boards with CP2102/CH340 USB bridges, the kernel driver
        open() syscall may assert control lines transiently in hardware before userspace
        can apply ioctl/termios settings; userspace pre-configuration minimizes but
        cannot eliminate hardware/driver-level resets on port open.
        """
        if not self._config.port:
            raise ValueError("Serial port is not configured; cannot open connection")

        factory = self._config.serial_factory
        if factory is not None:
            # Explicit hardware safety for caller-provided factory / mock
            ser = factory(
                port=self._config.port,
                baudrate=self._config.baud_rate,
                timeout=self._config.read_timeout_sec,
                rtscts=False,
                dsrdtr=False,
            )
            if hasattr(ser, "dtr"):
                try:
                    ser.dtr = False
                except Exception:
                    pass
            if hasattr(ser, "rts"):
                try:
                    ser.rts = False
                except Exception:
                    pass
            return ser

        if serial is None:
            raise ImportError("pyserial is required for SerialTransportAdapter; install via ground_station/requirements.txt")

        # Explicit hardware safety: rtscts=False, dsrdtr=False, do_not_open=True to configure DTR/RTS before open
        try:
            ser = serial.serial_for_url(
                self._config.port,
                baudrate=self._config.baud_rate,
                timeout=self._config.read_timeout_sec,
                rtscts=False,
                dsrdtr=False,
                do_not_open=True,
            )
            if hasattr(ser, "dtr"):
                try:
                    ser.dtr = False
                except Exception:
                    pass
            if hasattr(ser, "rts"):
                try:
                    ser.rts = False
                except Exception:
                    pass
            ser.open()
            if hasattr(ser, "dtr"):
                try:
                    ser.dtr = False
                except Exception:
                    pass
            if hasattr(ser, "rts"):
                try:
                    ser.rts = False
                except Exception:
                    pass
            # Clear HUPCL if termios is available to prevent hangup pulse on close
            try:
                import termios
                if hasattr(ser, "fd") and ser.fd:
                    attrs = termios.tcgetattr(ser.fd)
                    attrs[2] &= ~termios.HUPCL
                    termios.tcsetattr(ser.fd, termios.TCSANOW, attrs)
            except Exception:
                pass
            return ser
        except Exception as err:
            logger.debug("serial_for_url failed (%s), falling back to serial.Serial: %s", self._config.port, err)
            ser = serial.Serial(
                port=self._config.port,
                baudrate=self._config.baud_rate,
                timeout=self._config.read_timeout_sec,
                rtscts=False,
                dsrdtr=False,
            )
            if hasattr(ser, "dtr"):
                try:
                    ser.dtr = False
                except Exception:
                    pass
            if hasattr(ser, "rts"):
                try:
                    ser.rts = False
                except Exception:
                    pass
            return ser

    def _reader_loop(self) -> None:
        """Worker thread loop handling bounded buffered serial reading and reconnects."""
        reconnect_delay = self._config.reconnect_base_delay_sec
        buffer = bytearray()

        while not self._stop_event.is_set():
            # 1. Ensure Port Connection
            ser = None
            with self._lock:
                ser = self._serial_port

            if ser is None:
                if not self._config.port:
                    logger.warning("Serial port is unconfigured; reader loop pausing")
                    if self._stop_event.wait(timeout=1.0):
                        break
                    continue

                try:
                    with self._lock:
                        self._reconnect_attempts += 1
                    ser = self._open_serial()
                    with self._lock:
                        self._serial_port = ser
                        self._is_connected = True
                        self._connect_count += 1
                    reconnect_delay = self._config.reconnect_base_delay_sec
                    logger.info("Serial transport connected to %s", self._config.port)
                except Exception as err:
                    with self._lock:
                        self._io_errors += 1
                        self._is_connected = False
                    logger.debug("Serial connection attempt failed (%s): %s", self._config.port, err)
                    if not self._config.reconnect_enabled:
                        break
                    if self._stop_event.wait(timeout=reconnect_delay):
                        break
                    reconnect_delay = min(
                        reconnect_delay * 2.0,
                        self._config.reconnect_max_delay_sec,
                    )
                    continue

            # 2. Read and buffer data
            try:
                chunk = ser.read(128)
            except Exception as err:
                logger.warning("Serial read error on %s: %s", self._config.port, err)
                with self._lock:
                    self._io_errors += 1
                    self._disconnect_count += 1
                    self._is_connected = False
                    if self._serial_port is ser:
                        self._serial_port = None
                try:
                    ser.close()
                except Exception:
                    pass
                if not self._config.reconnect_enabled:
                    break
                continue

            if not chunk:
                # Read timeout (normal during idle)
                continue

            m_now = time.monotonic()
            w_now = time.time()
            with self._lock:
                self._bytes_read += len(chunk)
                self._last_read_monotonic = m_now
                self._last_read_wallclock = w_now

            buffer.extend(chunk)

            # 3. Process complete delimited lines
            while True:
                newline_pos = buffer.find(b"\n")
                if newline_pos == -1:
                    break

                # Extract line including newline
                raw_line = bytes(buffer[: newline_pos + 1])
                del buffer[: newline_pos + 1]

                with self._lock:
                    self._frames_received += 1

                # Enforce firmware wire-length limit (buffer capacity 256 -> max 255 wire bytes)
                if len(raw_line) >= self._config.max_frame_bytes:
                    with self._lock:
                        self._frames_dropped_oversized += 1
                    logger.debug(
                        "Dropped oversized serial frame of %d bytes (>= %d limit)",
                        len(raw_line),
                        self._config.max_frame_bytes,
                    )
                    continue

                trimmed = raw_line.rstrip(b"\r\n")
                if not trimmed:
                    # Empty lines ignored
                    continue

                # Cease processing immediately if shutdown has been requested
                if self._stop_event.is_set():
                    break

                # Forward complete frame non-blockingly
                callback = self._on_receive
                if callback:
                    try:
                        callback(self._name, raw_line)
                        with self._lock:
                            self._frames_forwarded += 1
                    except Exception as cb_err:
                        logger.error("Error in serial on_receive callback: %s", cb_err)

            # 4. Bounded buffer protection against missing newlines
            if len(buffer) > self._config.max_buffer_bytes:
                with self._lock:
                    self._framing_errors += 1
                    self._frames_dropped_oversized += 1
                logger.warning(
                    "Serial stream buffer exceeded ceiling of %d bytes without newline; discarding buffer",
                    self._config.max_buffer_bytes,
                )
                buffer.clear()

        # Clean up port on thread exit
        with self._lock:
            port = self._serial_port
            self._serial_port = None
            self._is_connected = False
        if port is not None:
            try:
                port.close()
            except Exception:
                pass

    def send_frame(self, data: Union[str, bytes]) -> bool:
        """Thread-safely send a newline-terminated frame over serial to ESP32."""
        with self._lock:
            port = self._serial_port
            connected = self._is_connected
        if not connected or port is None:
            logger.warning("Cannot send frame: serial transport is not connected")
            return False

        if isinstance(data, str):
            if not data.endswith("\n"):
                data = data + "\n"
            raw = data.encode("utf-8")
        else:
            raw = data if data.endswith(b"\n") else data + b"\n"

        if len(raw) > self._config.max_frame_bytes:
            logger.error("Cannot send frame: payload length %d exceeds max %d", len(raw), self._config.max_frame_bytes)
            return False

        try:
            port.write(raw)
            if hasattr(port, "flush"):
                port.flush()
            return True
        except Exception as err:
            logger.error("Failed to write frame to serial port: %s", err)
            with self._lock:
                self._io_errors += 1
            return False

    def get_stats(self) -> SerialStats:
        """Return a snapshot of serial adapter telemetry."""
        with self._lock:
            return SerialStats(
                is_connected=self._is_connected,
                connect_count=self._connect_count,
                disconnect_count=self._disconnect_count,
                reconnect_attempts=self._reconnect_attempts,
                bytes_read=self._bytes_read,
                frames_received=self._frames_received,
                frames_forwarded=self._frames_forwarded,
                frames_dropped_oversized=self._frames_dropped_oversized,
                framing_errors=self._framing_errors,
                io_errors=self._io_errors,
                last_read_monotonic=self._last_read_monotonic,
                last_read_wallclock=self._last_read_wallclock,
            )
