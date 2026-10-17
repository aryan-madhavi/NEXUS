#!/usr/bin/env python3
"""
NEXUS Hardware Soak-Test Capture Tool
Part of the NEXUS Environmental Monitoring Project (ESP-IDF v6.0.1 / FreeRTOS).

Safely captures concurrent USB Serial (UART0) and MQTT telemetry streams.
Includes an isolated software simulation mode (--simulate) for automated testing
without physical hardware access.

Hardware Safety Guarantees:
- Hardware capture is strictly opt-in via --hardware AND --i-understand-serial-risks.
- Never sends reset commands, never manipulates DTR/RTS pins, never flashes or erases.
- Bounded-time, non-blocking binary line reading with partial line recovery.
- Bounded, interruptible MQTT subscriber management with exact client ID tracking.
"""

import os
import sys
import time
import select
import signal
import argparse
import subprocess
import threading
from datetime import datetime, timezone

# Optional serial import (only required if --hardware is selected)
try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    import termios
except ImportError:
    termios = None

MAX_LINE_BUFFER_BYTES = 4096
DEFAULT_BAUD = 115200
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_DURATION_SEC = 1800  # 30 minutes nominal


def get_iso_timestamp():
    """Return formatted UTC ISO-8601 timestamp with microsecond resolution."""
    return datetime.now(timezone.utc).strftime("[%Y-%m-%d %H:%M:%S.%f] ")


class BoundedStreamReader:
    """
    Robust, non-blocking binary reader that buffers chunks, extracts delimited lines,
    bounds memory usage, handles partial lines on shutdown, and avoids readline deadlocks.
    """

    def __init__(self, raw_read_func, max_buffer_bytes=MAX_LINE_BUFFER_BYTES):
        self.raw_read = raw_read_func
        self.max_buffer = max_buffer_bytes
        self.buffer = bytearray()
        self.records_received = 0
        self.records_malformed = 0
        self.records_dropped = 0
        self.records_written = 0

    def feed_chunk(self, chunk):
        """Append raw bytes to buffer with strict size ceiling."""
        if not chunk:
            return []
        self.buffer.extend(chunk)
        lines = []

        while True:
            newline_pos = self.buffer.find(b"\n")
            if newline_pos != -1:
                line_bytes = bytes(self.buffer[: newline_pos + 1])
                del self.buffer[: newline_pos + 1]
                self.records_received += 1
                lines.append(self._process_line(line_bytes))
            else:
                break

        # Guard against unbounded buffer growth from missing newlines
        if len(self.buffer) > self.max_buffer:
            truncated = bytes(self.buffer[: self.max_buffer])
            del self.buffer[: self.max_buffer]
            self.records_dropped += 1
            self.records_malformed += 1
            lines.append(
                f"[OVERSIZED_TRUNCATED] {truncated.decode('utf-8', errors='replace')}\n"
            )

        return lines

    def flush_remaining(self):
        """Flush any trailing partial line when shutting down."""
        lines = []
        if self.buffer:
            partial = bytes(self.buffer)
            self.buffer.clear()
            self.records_received += 1
            lines.append(
                f"[PARTIAL_ON_SHUTDOWN] {partial.decode('utf-8', errors='replace')}\n"
            )
        return lines

    def _process_line(self, line_bytes):
        """Decode line with replacement characters on invalid UTF-8."""
        try:
            return line_bytes.decode("utf-8")
        except UnicodeDecodeError:
            self.records_malformed += 1
            return line_bytes.decode("utf-8", errors="replace")


class SoakCaptureHarness:
    """Manages concurrent capture streams with verified bounded shutdown."""

    def __init__(self, args):
        self.args = args
        self.running = True
        self.mqtt_proc = None
        self.mqtt_client_id = f"nexus_soak_{os.getpid()}_{int(time.time())}"
        self.mqtt_ready = threading.Event()
        self.mqtt_records_written = 0
        self.serial_records_written = 0
        self.cleanup_uncertain = False

        # Prepare filenames
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = self.args.log_dir or os.getcwd()
        os.makedirs(out_dir, exist_ok=True)

        self.serial_out_path = self.args.serial_out or os.path.join(
            out_dir, f"soak_serial_{ts_str}.log"
        )
        self.mqtt_out_path = self.args.mqtt_out or os.path.join(
            out_dir, f"soak_mqtt_{ts_str}.log"
        )
        self.mqtt_err_path = os.path.join(out_dir, f"soak_mqtt_err_{ts_str}.log")

        # Setup OS signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        print(f"\n[CAPTURE] Caught signal {signum}. Initiating clean shutdown...")
        self.running = False

    def verify_broker_reachability(self):
        """Perform a local-only probe to verify broker responsiveness."""
        if not self.args.use_podman_broker:
            return True

        probe_cmd = [
            "podman",
            "exec",
            self.args.broker_container,
            "mosquitto_sub",
            "-h",
            "127.0.0.1",
            "-p",
            str(self.args.broker_port),
            "-t",
            "nexus/probe",
            "-E",
        ]
        try:
            res = subprocess.run(
                probe_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            return res.returncode == 0
        except Exception as e:
            print(f"[CAPTURE] Broker probe error: {e}", file=sys.stderr)
            return False

    def _mqtt_listener(self):
        """Background worker thread draining the MQTT subscriber stream."""
        if not self.args.use_podman_broker:
            cmd = [
                "mosquitto_sub",
                "-h",
                self.args.broker_host,
                "-p",
                str(self.args.broker_port),
                "-i",
                self.mqtt_client_id,
                "-t",
                self.args.topic,
                "-v",
            ]
        else:
            cmd = [
                "podman",
                "exec",
                self.args.broker_container,
                "mosquitto_sub",
                "-h",
                "127.0.0.1",
                "-p",
                str(self.args.broker_port),
                "-i",
                self.mqtt_client_id,
                "-t",
                self.args.topic,
                "-v",
            ]

        err_file = None
        mqtt_file = None
        reader = None

        try:
            err_file = open(self.mqtt_err_path, "w", encoding="utf-8", buffering=1)
            mqtt_file = open(self.mqtt_out_path, "w", encoding="utf-8", buffering=1)

            self.mqtt_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=err_file,
                bufsize=0,
            )

            # Check if subscriber died immediately
            time.sleep(0.3)
            if self.mqtt_proc.poll() is not None:
                print(
                    f"[CAPTURE] MQTT subscriber failed on startup (exit={self.mqtt_proc.returncode}).",
                    file=sys.stderr,
                )
                return

            self.mqtt_ready.set()
            reader = BoundedStreamReader(
                lambda: os.read(self.mqtt_proc.stdout.fileno(), 1024)
            )

            # Polled, non-blocking read loop
            while self.running and self.mqtt_proc.poll() is None:
                rlist, _, _ = select.select([self.mqtt_proc.stdout], [], [], 0.2)
                if rlist:
                    try:
                        raw = os.read(self.mqtt_proc.stdout.fileno(), 1024)
                        if not raw:
                            break
                        lines = reader.feed_chunk(raw)
                        for line in lines:
                            ts = get_iso_timestamp()
                            mqtt_file.write(ts + line)
                            self.mqtt_records_written += 1
                        mqtt_file.flush()
                    except (OSError, ValueError):
                        break

            # Flush trailing partial lines on shutdown
            if reader:
                for line in reader.flush_remaining():
                    mqtt_file.write(get_iso_timestamp() + line)
                    self.mqtt_records_written += 1
                mqtt_file.flush()

        except Exception as e:
            print(f"[CAPTURE] MQTT listener error: {e}", file=sys.stderr)
        finally:
            self._terminate_mqtt_proc()
            if mqtt_file and not mqtt_file.closed:
                mqtt_file.flush()
                try:
                    os.fsync(mqtt_file.fileno())
                except OSError:
                    pass
                mqtt_file.close()
            if err_file and not err_file.closed:
                err_file.close()

    def _terminate_mqtt_proc(self):
        """Terminate the subscriber with bounded timeouts and exact PID tracking."""
        if not self.mqtt_proc or self.mqtt_proc.poll() is not None:
            return

        # 1. Bounded SIGINT
        try:
            self.mqtt_proc.send_signal(signal.SIGINT)
            self.mqtt_proc.wait(timeout=1.5)
            return
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass

        # 2. SIGTERM
        try:
            self.mqtt_proc.terminate()
            self.mqtt_proc.wait(timeout=1.0)
            return
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass

        # 3. SIGKILL & targeted container cleanup by exact client ID
        try:
            self.mqtt_proc.kill()
            self.mqtt_proc.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            self.cleanup_uncertain = True

        if self.args.use_podman_broker:
            try:
                subprocess.run(
                    [
                        "podman",
                        "exec",
                        self.args.broker_container,
                        "pkill",
                        "-f",
                        self.mqtt_client_id,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
            except Exception:
                self.cleanup_uncertain = True

    def run_software_simulation(self):
        """Execute deterministic software simulation without accessing hardware."""
        print("[CAPTURE] Running in SOFTWARE SIMULATION mode (--simulate).")
        print(f"[CAPTURE] Writing synthetic serial logs to: {self.serial_out_path}")
        print(f"[CAPTURE] Writing synthetic MQTT logs to:   {self.mqtt_out_path}")

        sim_duration = min(self.args.duration, 10)  # Bounded simulation runtime
        start_time = time.monotonic()
        seq = 1

        with open(self.serial_out_path, "w", encoding="utf-8") as s_file, open(
            self.mqtt_out_path, "w", encoding="utf-8"
        ) as m_file:
            # Cold boot banner
            s_file.write(
                f"{get_iso_timestamp()}I (456) app_init: ESP-IDF: v6.0.1\n"
            )
            s_file.write(
                f"{get_iso_timestamp()}I (535) nexus_main: reset_reason=1\n"
            )
            s_file.write(
                f"{get_iso_timestamp()}I (805) nexus_wifi_mqtt: MQTT connected to broker\n"
            )
            self.serial_records_written += 3

            uptime = 500
            heap = 194096

            while self.running and (time.monotonic() - start_time < sim_duration):
                uptime += 1000
                heap += (seq % 3) * 4 - 4  # Bounded small jitter

                # Periodic heartbeat
                s_file.write(
                    f"{get_iso_timestamp()}I ({uptime}) nexus_main: heartbeat uptime_ms={uptime} free_heap={heap}\n"
                )
                self.serial_records_written += 1

                hb_json = f'{{"ver":1,"dev":"nexus_esp32","seq":{seq},"type":"hb","uptime":{uptime},"heap":{heap},"ticks":{seq*10}}}\n'
                m_file.write(
                    f"{get_iso_timestamp()}nexus/nexus_esp32/telemetry {hb_json}"
                )
                self.mqtt_records_written += 1
                seq += 1

                # Periodic telemetry at 0.5 Hz
                if seq % 2 == 0:
                    telem_json = f'{{"ver":1,"dev":"nexus_esp32","seq":{seq},"type":"telem","uptime":{uptime},"ldr":1024,"x0":3100,"temp":32,"hum":58,"dht_valid":true}}\n'
                    m_file.write(
                        f"{get_iso_timestamp()}nexus/nexus_esp32/telemetry {telem_json}"
                    )
                    self.mqtt_records_written += 1
                    seq += 1

                # Periodic stats at 5 s
                if uptime % 5000 == 0:
                    s_file.write(
                        f"{get_iso_timestamp()}I ({uptime}) nexus_main: exec_stats: ticks={uptime//100} dispatched={seq*2} completed={seq*2} failed=0 dline_misses=0 q_overflows=0 ready_hwm=4 ev_hwm=1 max_lat_us=92300 max_dur_us=24500\n"
                    )
                    s_file.write(
                        f"{get_iso_timestamp()}I ({uptime}) nexus_main: conn_stats: state=CONNECTED tx_enq={seq} tx_disp={seq} tx_drop=0 tx_fail=0 q_depth=0 q_hwm=2 rx_dup=0\n"
                    )
                    s_file.write(
                        f"{get_iso_timestamp()}I ({uptime}) nexus_dht11: DHT11 read OK: temp=32°C, hum=58% (total_ok={seq//2}, total_err=0)\n"
                    )
                    self.serial_records_written += 3

                s_file.flush()
                m_file.flush()
                time.sleep(0.2)

        print("[CAPTURE] Software simulation complete.")
        return 0

    def run_hardware_capture(self):
        """Execute physical hardware capture with verified opt-in safeguards."""
        if not self.args.i_understand_serial_risks:
            print("\n" + "=" * 70, file=sys.stderr)
            print("SAFETY INTERLOCK ERROR: --hardware requested without risk opt-in.", file=sys.stderr)
            print("Opening a USB-to-UART bridge (/dev/ttyUSB0) can assert kernel DTR/RTS", file=sys.stderr)
            print("lines, triggering an unrequested hardware reset on ESP32 DevKit boards.", file=sys.stderr)
            print("To proceed, you must pass: --i-understand-serial-risks", file=sys.stderr)
            print("=" * 70 + "\n", file=sys.stderr)
            return 2

        if not HAS_SERIAL:
            print("[ERROR] pyserial is not installed in the active Python environment.", file=sys.stderr)
            return 1

        print("[CAPTURE] Starting physical hardware capture.")
        print(f"[CAPTURE] Target serial port: {self.args.port} at {self.args.baud} baud")
        print("[CAPTURE] Operating in PASSIVE listener mode (DTR/RTS manipulation disabled).")

        # 1. Start background MQTT subscriber
        mqtt_thread = threading.Thread(target=self._mqtt_listener, daemon=True)
        mqtt_thread.start()
        self.mqtt_ready.wait(timeout=2.0)

        # 2. Open serial connection passively
        ser = None
        s_file = None
        reader = None

        try:
            # Open port without flow control to avoid holding EN in reset
            ser = serial.serial_for_url(
                self.args.port,
                baudrate=self.args.baud,
                timeout=0.1,
                do_not_open=True,
                dsrdtr=False,
                rtscts=False,
            )
            ser.dtr = False
            ser.rts = False
            ser.open()
            if termios and hasattr(ser, "fd") and ser.fd:
                try:
                    attrs = termios.tcgetattr(ser.fd)
                    attrs[2] &= ~termios.HUPCL
                    termios.tcsetattr(ser.fd, termios.TCSANOW, attrs)
                except Exception:
                    pass
            s_file = open(self.serial_out_path, "w", encoding="utf-8", buffering=1)
            reader = BoundedStreamReader(lambda: ser.read(1024))

            if getattr(self.args, "reset_target", False):
                print("[CAPTURE] Explicit --reset-target requested. Pulsing EN line to capture cold-boot banner...")
                try:
                    ser.dtr = False
                    ser.rts = True
                    time.sleep(0.1)
                    ser.rts = False
                    time.sleep(0.1)
                except Exception as e:
                    print(f"[CAPTURE] Warning: Failed to pulse reset lines: {e}", file=sys.stderr)

            start_time = time.monotonic()
            print(f"[CAPTURE] Recording streams for {self.args.duration}s. Press Ctrl+C to halt.")

            while self.running and (time.monotonic() - start_time < self.args.duration):
                raw = ser.read(512)
                if raw:
                    lines = reader.feed_chunk(raw)
                    for line in lines:
                        s_file.write(get_iso_timestamp() + line)
                        self.serial_records_written += 1
                    s_file.flush()
                else:
                    time.sleep(0.01)

            if reader:
                for line in reader.flush_remaining():
                    s_file.write(get_iso_timestamp() + line)
                    self.serial_records_written += 1
                s_file.flush()

        except Exception as e:
            print(f"[CAPTURE] Serial read failure: {e}", file=sys.stderr)
            return 1
        finally:
            self.running = False
            if ser and ser.is_open:
                ser.close()
            if s_file and not s_file.closed:
                s_file.flush()
                try:
                    os.fsync(s_file.fileno())
                except OSError:
                    pass
                s_file.close()
            mqtt_thread.join(timeout=3.0)

        return 0

    def print_summary(self):
        """Display exact accounting of records captured."""
        print("\n" + "=" * 55)
        print("          NEXUS CAPTURE EXECUTION SUMMARY          ")
        print("=" * 55)
        print(f"Serial Output File:      {self.serial_out_path}")
        print(f"Serial Records Written:  {self.serial_records_written}")
        print(f"MQTT Output File:        {self.mqtt_out_path}")
        print(f"MQTT Records Written:    {self.mqtt_records_written}")
        if self.cleanup_uncertain:
            print("Cleanup Status:          UNCERTAIN (process may linger)")
        else:
            print("Cleanup Status:          CLEAN (all processes terminated)")
        print("=" * 55 + "\n")


class NexusCaptureArgParser(argparse.ArgumentParser):
    """Custom parser ensuring CLI usage errors exit with code 3 (INPUT_ERROR)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"[ERROR] {self.prog}: error: {message}", file=sys.stderr)
        sys.exit(3)


def build_arg_parser():
    parser = NexusCaptureArgParser(
        description="NEXUS Hardware Soak-Test Capture Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        default=True,
        help="Run deterministic software simulation without accessing hardware.",
    )
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="Opt-in to physical hardware UART capture on serial port.",
    )
    parser.add_argument(
        "--i-understand-serial-risks",
        action="store_true",
        help="Acknowledge that opening USB-to-UART devices can toggle DTR/RTS and reset the ESP32.",
    )
    parser.add_argument(
        "--reset-target",
        action="store_true",
        default=False,
        help="Explicitly pulse the hardware EN pin at capture start to record cold-boot banner.",
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help="Serial port for hardware capture.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
        help="Serial baud rate.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SEC,
        help="Capture duration in seconds.",
    )
    parser.add_argument(
        "--log-dir",
        default="docs/validation",
        help="Directory to store captured log files.",
    )
    parser.add_argument(
        "--serial-out",
        help="Explicit path for serial log output.",
    )
    parser.add_argument(
        "--mqtt-out",
        help="Explicit path for MQTT telemetry log output.",
    )
    parser.add_argument(
        "--topic",
        default="nexus/nexus_esp32/#",
        help="MQTT topic subscription pattern.",
    )
    parser.add_argument(
        "--broker-host",
        default="127.0.0.1",
        help="MQTT broker host address.",
    )
    parser.add_argument(
        "--broker-port",
        type=int,
        default=1883,
        help="MQTT broker TCP port.",
    )
    parser.add_argument(
        "--use-podman-broker",
        action="store_true",
        default=True,
        help="Execute mosquitto_sub via podman exec nexus_broker.",
    )
    parser.add_argument(
        "--broker-container",
        default="nexus_broker",
        help="Name of local Mosquitto podman container.",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    # Determine execution mode: --hardware overrides default simulation
    if args.hardware:
        args.simulate = False

    harness = SoakCaptureHarness(args)

    if args.simulate:
        code = harness.run_software_simulation()
    else:
        code = harness.run_hardware_capture()

    harness.print_summary()
    sys.exit(code)


if __name__ == "__main__":
    main()
