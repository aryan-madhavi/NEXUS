"""Unit tests for the NEXUS Protocol v1 Envelope Parser."""

import unittest

from ground_station.connection_manager.envelope_parser import (
    NEXUS_ENVELOPE_MAX_LEN,
    CommandPayload,
    EnvelopeParser,
    EventPayload,
    FieldRangeError,
    FieldTypeError,
    HeartbeatPayload,
    MalformedJsonError,
    MessageType,
    MissingFieldError,
    OversizedEnvelopeError,
    ResponsePayload,
    StatusPayload,
    TelemetryPayload,
    UnknownMessageTypeError,
    UnsupportedVersionError,
)


class TestEnvelopeParser(unittest.TestCase):
    """Test suite for strict NEXUS Protocol v1 envelope parsing."""

    def test_valid_heartbeat(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":101,"type":"hb","uptime":12345,"heap":245000,"ticks":120}\n'
        env = EnvelopeParser.parse(raw)
        self.assertEqual(env.ver, 1)
        self.assertEqual(env.dev, "nexus_esp32")
        self.assertEqual(env.seq, 101)
        self.assertEqual(env.msg_type, MessageType.HEARTBEAT)
        self.assertEqual(env.uptime_ms, 12345)
        self.assertIsInstance(env.payload, HeartbeatPayload)
        self.assertEqual(env.payload.free_heap, 245000)
        self.assertEqual(env.payload.exec_ticks, 120)
        self.assertEqual(len(env.extra_fields), 0)

    def test_valid_telemetry_with_dht(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":102,"type":"telem","uptime":12350,"ldr":2048,"x0":1024,"temp":25,"hum":60,"dht_valid":true}\n'
        env = EnvelopeParser.parse(raw)
        self.assertEqual(env.msg_type, MessageType.TELEMETRY)
        self.assertIsInstance(env.payload, TelemetryPayload)
        self.assertEqual(env.payload.ldr_raw, 2048)
        self.assertEqual(env.payload.x0_raw, 1024)
        self.assertTrue(env.payload.dht_valid)
        self.assertEqual(env.payload.temp, 25.0)
        self.assertEqual(env.payload.hum, 60.0)

    def test_valid_telemetry_dht_degraded_omitted(self):
        # Firmware omits temp and hum when dht_valid is false
        raw = '{"ver":1,"dev":"nexus_esp32","seq":103,"type":"telem","uptime":12350,"ldr":2048,"x0":1024,"dht_valid":false}\n'
        env = EnvelopeParser.parse(raw)
        self.assertEqual(env.msg_type, MessageType.TELEMETRY)
        self.assertIsInstance(env.payload, TelemetryPayload)
        self.assertFalse(env.payload.dht_valid)
        self.assertIsNone(env.payload.temp)
        self.assertIsNone(env.payload.hum)

    def test_telemetry_dht_degraded_suppresses_fabricated_temp_hum(self):
        # Even if temp/hum are present in the envelope, when dht_valid is false,
        # the parser must NOT expose them as valid readings.
        raw = '{"ver":1,"dev":"nexus_esp32","seq":103,"type":"telem","uptime":12350,"ldr":2048,"x0":1024,"temp":99,"hum":99,"dht_valid":false}\n'
        env = EnvelopeParser.parse(raw)
        self.assertFalse(env.payload.dht_valid)
        self.assertIsNone(env.payload.temp)
        self.assertIsNone(env.payload.hum)
        self.assertEqual(env.payload.suppressed_temp, 99.0)
        self.assertEqual(env.payload.suppressed_hum, 99.0)

    def test_valid_status_metrics(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":104,"type":"status","uptime":12360,"disp":50,"comp":48,"fail":2,"lat_us":1200,"dur_us":450}\n'
        env = EnvelopeParser.parse(raw)
        self.assertEqual(env.msg_type, MessageType.STATUS)
        self.assertIsInstance(env.payload, StatusPayload)
        self.assertEqual(env.payload.dispatched, 50)
        self.assertEqual(env.payload.completed, 48)
        self.assertEqual(env.payload.failed, 2)
        self.assertEqual(env.payload.max_lat_us, 1200)
        self.assertEqual(env.payload.max_dur_us, 450)

    def test_valid_event(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":105,"type":"event","uptime":12370,"ev":1,"sev":2,"src":42,"val":999}\n'
        env = EnvelopeParser.parse(raw)
        self.assertEqual(env.msg_type, MessageType.EVENT)
        self.assertIsInstance(env.payload, EventPayload)
        self.assertEqual(env.payload.event_type, 1)
        self.assertEqual(env.payload.severity, 2)
        self.assertEqual(env.payload.source_id, 42)
        self.assertEqual(env.payload.payload_val, 999)

    def test_valid_command_and_response(self):
        cmd_raw = '{"ver":1,"dev":"ground_station","seq":701,"type":"cmd","target":"led","state":1}\n'
        env_cmd = EnvelopeParser.parse(cmd_raw)
        self.assertEqual(env_cmd.msg_type, MessageType.COMMAND)
        self.assertIsInstance(env_cmd.payload, CommandPayload)
        self.assertEqual(env_cmd.payload.fields["target"], "led")
        self.assertEqual(env_cmd.payload.fields["state"], 1)

        resp_raw = '{"ver":1,"dev":"nexus_esp32","seq":702,"type":"resp","status":"ok"}\n'
        env_resp = EnvelopeParser.parse(resp_raw)
        self.assertEqual(env_resp.msg_type, MessageType.RESPONSE)
        self.assertIsInstance(env_resp.payload, ResponsePayload)
        self.assertEqual(env_resp.payload.fields["status"], "ok")

    def test_long_form_type_names(self):
        raw_hb = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"heartbeat","uptime":100,"heap":200000,"ticks":10}'
        env = EnvelopeParser.parse(raw_hb)
        self.assertEqual(env.msg_type, MessageType.HEARTBEAT)

        raw_telem = '{"ver":1,"dev":"nexus_esp32","seq":2,"type":"telemetry","uptime":200,"ldr":10,"x0":20,"dht_valid":false}'
        env2 = EnvelopeParser.parse(raw_telem)
        self.assertEqual(env2.msg_type, MessageType.TELEMETRY)

    def test_extra_fields_preserved_safely(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"hb","uptime":100,"heap":200000,"ticks":10,"custom_tag":"alpha","note":42}'
        env = EnvelopeParser.parse(raw)
        self.assertEqual(env.extra_fields["custom_tag"], "alpha")
        self.assertEqual(env.extra_fields["note"], 42)

    def test_bytes_and_string_inputs(self):
        s = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"hb","uptime":100,"heap":200000,"ticks":10}'
        env_str = EnvelopeParser.parse(s)
        env_bytes = EnvelopeParser.parse(s.encode("utf-8"))
        self.assertEqual(env_str.seq, env_bytes.seq)
        self.assertEqual(env_str.raw_bytes, env_bytes.raw_bytes)

    # --- Rejection and Error Cases ---

    def test_malformed_json_syntax(self):
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse('{"ver":1,"seq":100,broken')
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse("NOT_JSON")
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse("")
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse("[1, 2, 3]")
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse(b"\xff\xfe\x00")

    def test_unsupported_version(self):
        # Version 0 rejected
        with self.assertRaises(UnsupportedVersionError):
            EnvelopeParser.parse('{"ver":0,"dev":"nexus_esp32","seq":1,"type":"cmd"}')
        # Version 2 rejected
        with self.assertRaises(UnsupportedVersionError):
            EnvelopeParser.parse('{"ver":2,"dev":"nexus_esp32","seq":1,"type":"cmd"}')

    def test_missing_required_fields(self):
        # Missing 'ver'
        with self.assertRaises(MissingFieldError) as ctx:
            EnvelopeParser.parse('{"dev":"nexus_esp32","seq":1,"type":"cmd"}')
        self.assertEqual(ctx.exception.field_name, "ver")

        # Missing 'dev'
        with self.assertRaises(MissingFieldError) as ctx:
            EnvelopeParser.parse('{"ver":1,"seq":1,"type":"cmd"}')
        self.assertEqual(ctx.exception.field_name, "dev")

        # Missing 'seq'
        with self.assertRaises(MissingFieldError) as ctx:
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","type":"cmd"}')
        self.assertEqual(ctx.exception.field_name, "seq")

        # Missing 'type'
        with self.assertRaises(MissingFieldError) as ctx:
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1}')
        self.assertEqual(ctx.exception.field_name, "type")

        # Missing 'uptime' on telem
        with self.assertRaises(MissingFieldError) as ctx:
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","ldr":10,"x0":20,"dht_valid":false}')
        self.assertEqual(ctx.exception.field_name, "uptime")

        # Missing 'temp' when dht_valid is True
        with self.assertRaises(MissingFieldError) as ctx:
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":10,"x0":20,"dht_valid":true,"hum":50}')
        self.assertEqual(ctx.exception.field_name, "temp")

    def test_boolean_schema_violations(self):
        # In Python, isinstance(True, int) is True, so verify strict non-boolean int validation
        with self.assertRaises(FieldTypeError):
            EnvelopeParser.parse('{"ver":true,"dev":"nexus_esp32","seq":1,"type":"cmd"}')

        with self.assertRaises(FieldTypeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":true,"type":"cmd"}')

        with self.assertRaises(FieldTypeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":true,"ldr":10,"x0":20,"dht_valid":false}')

        with self.assertRaises(FieldTypeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":true,"x0":20,"dht_valid":false}')

        # dht_valid must be bool, not int 1 or string "true"
        with self.assertRaises(FieldTypeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":10,"x0":20,"dht_valid":1}')

        with self.assertRaises(FieldTypeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":10,"x0":20,"dht_valid":"true"}')

    def test_field_range_validation(self):
        # Negative sequence
        with self.assertRaises(FieldRangeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":-1,"type":"cmd"}')

        # Sequence overflow (> uint32 max)
        with self.assertRaises(FieldRangeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":4294967296,"type":"cmd"}')

        # Negative uptime
        with self.assertRaises(FieldRangeError):
            EnvelopeParser.parse('{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd","uptime":-1}')

        # Empty dev id
        with self.assertRaises(FieldRangeError):
            EnvelopeParser.parse('{"ver":1,"dev":"","seq":1,"type":"cmd"}')

    def test_non_finite_numeric_rejection(self):
        # Rejects NaN
        raw_nan = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":2000,"x0":1000,"temp":NaN,"hum":50,"dht_valid":true}'
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse(raw_nan)

        # Rejects Infinity
        raw_inf = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":2000,"x0":1000,"temp":Infinity,"hum":50,"dht_valid":true}'
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse(raw_inf)

        # Rejects -Infinity
        raw_ninf = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"telem","uptime":100,"ldr":2000,"x0":1000,"temp":-Infinity,"hum":50,"dht_valid":true}'
        with self.assertRaises(MalformedJsonError):
            EnvelopeParser.parse(raw_ninf)

    def test_unknown_message_type(self):
        raw = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"bogus"}'
        with self.assertRaises(UnknownMessageTypeError) as ctx:
            EnvelopeParser.parse(raw)
        self.assertEqual(ctx.exception.msg_type, "bogus")

    def test_envelope_size_boundary_limits(self):
        # Exactly 255 bytes: accepted
        prefix = '{"ver":1,"dev":"nexus_esp32","seq":1,"type":"cmd","pad":"'
        pad_len = 255 - len(prefix) - 3  # for '\"}\n'
        valid_255 = prefix + ("A" * pad_len) + '"}\n'
        self.assertEqual(len(valid_255.encode("utf-8")), 255)
        env = EnvelopeParser.parse(valid_255)
        self.assertEqual(env.seq, 1)

        # Exactly 256 bytes: rejected as oversized
        invalid_256 = prefix + ("A" * (pad_len + 1)) + '"}\n'
        self.assertEqual(len(invalid_256.encode("utf-8")), 256)
        with self.assertRaises(OversizedEnvelopeError) as ctx:
            EnvelopeParser.parse(invalid_256)
        self.assertEqual(ctx.exception.length, 256)

        # > 256 bytes: rejected
        oversized_300 = "X" * 300
        with self.assertRaises(OversizedEnvelopeError):
            EnvelopeParser.parse(oversized_300)


if __name__ == "__main__":
    unittest.main()
