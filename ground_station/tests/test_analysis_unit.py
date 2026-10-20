"""Unit tests for NEXUS Telemetry Analysis and Query Foundation.

These tests run 100% offline without requiring InfluxDB or container services.
Mocks InfluxDB client and tests parameter validation, canonical deduplication,
missing/invalid data semantics, full-window statistics, and trend calculations.
"""

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

from ground_station.analysis.models import (
    DataSourceUnavailableError,
    InvalidQueryError,
    QueryTimeoutError,
    TelemetryRecord,
    TrendDirection,
)
from ground_station.analysis.quality import TelemetryQuality
from ground_station.analysis.statistics import TelemetryStatistics
from ground_station.analysis.telemetry_query import TelemetryQueryService
from ground_station.persistence.influxdb_writer import InfluxDBConfig


class FakeFluxRecord:
    """Mock representing an InfluxDB FluxRecord."""

    def __init__(
        self,
        values: Dict[str, Any],
        time: datetime,
        value: Any,
        field: str,
        measurement: str,
    ) -> None:
        self.values = values
        self._time = time
        self._value = value
        self._field = field
        self._measurement = measurement

    def get_time(self) -> datetime:
        return self._time

    def get_value(self) -> Any:
        return self._value

    def get_field(self) -> str:
        return self._field

    def get_measurement(self) -> str:
        return self._measurement


class FakeFluxTable:
    """Mock representing an InfluxDB FluxTable."""

    def __init__(self, records: List[FakeFluxRecord]) -> None:
        self.records = records


class TestTelemetryQueryValidation(unittest.TestCase):
    """Test parameter validation, allowlists, and boundary checks."""

    def setUp(self) -> None:
        self.mock_client = MagicMock()
        self.config = InfluxDBConfig(url="http://mock:8086", token="mock-token")
        self.service = TelemetryQueryService(config=self.config, client=self.mock_client)

    def tearDown(self) -> None:
        self.service.close()

    def test_device_validation_allowed(self) -> None:
        self.assertEqual(self.service.validate_device("nexus_esp32"), "nexus_esp32")
        self.assertEqual(self.service.validate_device("dev-123_4"), "dev-123_4")

    def test_device_validation_rejected(self) -> None:
        with self.assertRaises(InvalidQueryError):
            self.service.validate_device("")
        with self.assertRaises(InvalidQueryError):
            self.service.validate_device("dev; drop measurement")
        with self.assertRaises(InvalidQueryError):
            self.service.validate_device("device_name_that_is_way_too_long_exceeding_32_characters")

    def test_signal_validation_allowed(self) -> None:
        m, f = self.service.validate_signal("temp")
        self.assertEqual((m, f), ("nexus_telem", "temp"))

        m, f = self.service.validate_signal("free_heap")
        self.assertEqual((m, f), ("nexus_hb", "free_heap"))

        m, f = self.service.validate_signal("dispatched")
        self.assertEqual((m, f), ("nexus_status", "dispatched"))

    def test_signal_validation_rejected(self) -> None:
        with self.assertRaises(InvalidQueryError):
            self.service.validate_signal("non_existent_sensor")
        with self.assertRaises(InvalidQueryError):
            self.service.validate_signal("arbitrary_field; |> drop()")

    def test_time_range_validation_allowed(self) -> None:
        s, e = self.service.validate_time_range("-15m", "now()")
        self.assertEqual(s, "-15m")
        self.assertEqual(e, "now()")

        s, e = self.service.validate_time_range("-24h")
        self.assertEqual(s, "-24h")

        s, e = self.service.validate_time_range("-30d")
        self.assertEqual(s, "-30d")

    def test_time_range_validation_rejected(self) -> None:
        # Exceeds 30 days
        with self.assertRaises(InvalidQueryError):
            self.service.validate_time_range("-31d")
        with self.assertRaises(InvalidQueryError):
            self.service.validate_time_range("-750h")
        # Malformed
        with self.assertRaises(InvalidQueryError):
            self.service.validate_time_range("invalid_time")
        with self.assertRaises(InvalidQueryError):
            self.service.validate_time_range("+5m")

    def test_limit_validation(self) -> None:
        self.assertEqual(self.service.validate_limit(10), 10)
        self.assertEqual(self.service.validate_limit(1000), 1000)

        with self.assertRaises(InvalidQueryError):
            self.service.validate_limit(0)
        with self.assertRaises(InvalidQueryError):
            self.service.validate_limit(1001)

    def test_transport_validation(self) -> None:
        self.assertIsNone(self.service.validate_transport(None))
        self.assertIsNone(self.service.validate_transport("all"))
        self.assertEqual(self.service.validate_transport("mqtt"), "mqtt")
        self.assertEqual(self.service.validate_transport("serial"), "serial")

        with self.assertRaises(InvalidQueryError):
            self.service.validate_transport("bluetooth")


class TestCanonicalDeduplication(unittest.TestCase):
    """Test observation deduplication across simultaneous MQTT and Serial transports."""

    def setUp(self) -> None:
        self.mock_client = MagicMock()
        self.mock_query_api = MagicMock()
        self.mock_client.query_api.return_value = self.mock_query_api
        self.config = InfluxDBConfig(url="http://mock:8086", token="mock-token")
        self.service = TelemetryQueryService(config=self.config, client=self.mock_client)

    def tearDown(self) -> None:
        self.service.close()

    def test_dual_transport_arrival_deduplication(self) -> None:
        """Simultaneous MQTT and Serial arrival for the same tick merges into single ObservationEvent."""
        base_time = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        mqtt_time = base_time
        serial_time = base_time + timedelta(milliseconds=15)

        # Mock pivoted record dicts
        rec_mqtt = FakeFluxRecord(
            values={
                "_time": mqtt_time,
                "dev": "nexus_esp32",
                "transport": "mqtt",
                "seq": 100,
                "uptime_ms": 50000,
                "ldr_raw": 1500,
                "x0_raw": 2200,
                "dht_valid": True,
                "temp": 24.5,
                "hum": 55.0,
            },
            time=mqtt_time,
            value=24.5,
            field="temp",
            measurement="nexus_telem",
        )

        rec_serial = FakeFluxRecord(
            values={
                "_time": serial_time,
                "dev": "nexus_esp32",
                "transport": "serial",
                "seq": 100,
                "uptime_ms": 50000,
                "ldr_raw": 1500,
                "x0_raw": 2200,
                "dht_valid": True,
                "temp": 24.5,
                "hum": 55.0,
            },
            time=serial_time,
            value=24.5,
            field="temp",
            measurement="nexus_telem",
        )

        self.mock_query_api.query.return_value = [FakeFluxTable([rec_mqtt, rec_serial])]

        events = self.service.get_raw_envelopes(
            dev="nexus_esp32",
            msg_type="telem",
            limit=50,
            deduplicate=True,
        )

        # Verifies that dual delivery collapses to 1 event, preserving both transports
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.dev, "nexus_esp32")
        self.assertEqual(ev.seq, 100)
        self.assertEqual(ev.uptime_ms, 50000)
        self.assertEqual(sorted(ev.transports), ["mqtt", "serial"])
        self.assertEqual(ev.host_time, mqtt_time)
        self.assertEqual(ev.fields["temp"], 24.5)

    def test_reboot_epoch_preserves_distinct_events(self) -> None:
        """Events with same seq but across device reboots must NOT be collapsed."""
        time1 = datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc)
        time2 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)  # 2 hours later after reboot

        rec1 = FakeFluxRecord(
            values={
                "_time": time1,
                "dev": "nexus_esp32",
                "transport": "mqtt",
                "seq": 5,
                "uptime_ms": 10000,
                "temp": 22.0,
            },
            time=time1,
            value=22.0,
            field="temp",
            measurement="nexus_telem",
        )

        # Reboot occurred: uptime_ms reset to 10000, seq restarted at 5, but 2 hours later
        rec2 = FakeFluxRecord(
            values={
                "_time": time2,
                "dev": "nexus_esp32",
                "transport": "mqtt",
                "seq": 5,
                "uptime_ms": 10000,
                "temp": 23.5,
            },
            time=time2,
            value=23.5,
            field="temp",
            measurement="nexus_telem",
        )

        self.mock_query_api.query.return_value = [FakeFluxTable([rec1, rec2])]

        events = self.service.get_raw_envelopes(
            dev="nexus_esp32",
            msg_type="telem",
            deduplicate=True,
        )

        # Because time delta is > 5s, they are NOT merged!
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].host_time, time1)
        self.assertEqual(events[1].host_time, time2)

    def test_reboot_sequence_reuse_within_five_seconds_not_merged(self) -> None:
        """Deterministic regression test: Rapid reboot reuses seq=0, uptime=500 after 2s.

        With the tight correlation window (< 0.5s), the 2.0s time delta correctly
        prevents collapsing these distinct boot cycles into a single event.
        """
        t0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        # Pre-reboot event
        rec1 = FakeFluxRecord(
            values={
                "_time": t0,
                "dev": "nexus_esp32",
                "transport": "mqtt",
                "seq": 0,
                "uptime_ms": 500,
                "temp": 20.0,
            },
            time=t0,
            value=20.0,
            field="temp",
            measurement="nexus_telem",
        )
        # Post-reboot event: reboot occurred, seq=0 and uptime=500 reached 2s later
        t_reboot = t0 + timedelta(seconds=2.0)
        rec2 = FakeFluxRecord(
            values={
                "_time": t_reboot,
                "dev": "nexus_esp32",
                "transport": "serial",
                "seq": 0,
                "uptime_ms": 500,
                "temp": 21.0,
            },
            time=t_reboot,
            value=21.0,
            field="temp",
            measurement="nexus_telem",
        )

        self.mock_query_api.query.return_value = [FakeFluxTable([rec1, rec2])]

        events = self.service.get_raw_envelopes(
            dev="nexus_esp32",
            msg_type="telem",
            deduplicate=True,
            correlation_window_sec=0.5,
        )

        # Must NOT be collapsed into 1 event!
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].host_time, t0)
        self.assertEqual(events[0].transports, ["mqtt"])
        self.assertEqual(events[1].host_time, t_reboot)
        self.assertEqual(events[1].transports, ["serial"])

    def test_same_transport_duplicate_not_merged(self) -> None:
        """Envelopes with identical (dev, seq, uptime) on the SAME transport are not merged as cross-transport."""
        t0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        rec1 = FakeFluxRecord(
            values={
                "_time": t0,
                "dev": "nexus_esp32",
                "transport": "mqtt",
                "seq": 10,
                "uptime_ms": 2000,
                "temp": 22.0,
            },
            time=t0,
            value=22.0,
            field="temp",
            measurement="nexus_telem",
        )
        rec2 = FakeFluxRecord(
            values={
                "_time": t0 + timedelta(milliseconds=100),
                "dev": "nexus_esp32",
                "transport": "mqtt",  # Same transport
                "seq": 10,
                "uptime_ms": 2000,
                "temp": 22.0,
            },
            time=t0 + timedelta(milliseconds=100),
            value=22.0,
            field="temp",
            measurement="nexus_telem",
        )

        self.mock_query_api.query.return_value = [FakeFluxTable([rec1, rec2])]

        events = self.service.get_raw_envelopes(
            dev="nexus_esp32",
            msg_type="telem",
            deduplicate=True,
            correlation_window_sec=0.5,
        )

        # Same-transport duplicates are preserved as separate observations
        self.assertEqual(len(events), 2)


class TestMissingAndInvalidDataSemantics(unittest.TestCase):
    """Verify strict handling: missing readings are not zero, invalid readings counted."""

    def test_missing_data_not_zero_in_summary(self) -> None:
        t0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        records = [
            TelemetryRecord(
                dev="nexus_esp32",
                measurement="nexus_telem",
                field="temp",
                value=25.0,
                host_time=t0,
            ),
            TelemetryRecord(
                dev="nexus_esp32",
                measurement="nexus_telem",
                field="temp",
                value=27.0,
                host_time=t0 + timedelta(seconds=2),
            ),
        ]

        summary = TelemetryStatistics.calculate_series_summary(
            dev="nexus_esp32",
            signal="temp",
            records=records,
            start_time="-15m",
            stop_time="now()",
            invalid_count=3,  # 3 cycles had dht_valid=False
        )

        self.assertEqual(summary.sample_count, 2)
        self.assertEqual(summary.invalid_count, 3)
        self.assertAlmostEqual(summary.mean_value, 26.0)
        self.assertAlmostEqual(summary.min_value, 25.0)
        self.assertAlmostEqual(summary.max_value, 27.0)

    def test_empty_series_has_none_not_zero(self) -> None:
        summary = TelemetryStatistics.calculate_series_summary(
            dev="nexus_esp32",
            signal="temp",
            records=[],
            start_time="-15m",
            stop_time="now()",
            invalid_count=5,
        )

        self.assertEqual(summary.sample_count, 0)
        self.assertEqual(summary.invalid_count, 5)
        self.assertIsNone(summary.mean_value)
        self.assertIsNone(summary.min_value)
        self.assertIsNone(summary.max_value)


class TestTrendAndStatisticsCalculation(unittest.TestCase):
    """Test deterministic linear regression and window comparison."""

    def setUp(self) -> None:
        self.mock_client = MagicMock()
        self.mock_query_api = MagicMock()
        self.mock_client.query_api.return_value = self.mock_query_api
        self.config = InfluxDBConfig(url="http://mock:8086", token="mock-token")
        self.service = TelemetryQueryService(config=self.config, client=self.mock_client)

    def tearDown(self) -> None:
        self.service.close()

    def test_calculate_trend_rising(self) -> None:
        t0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        # Rising by 0.5 deg C per 30 seconds -> 1.0 deg C per minute
        records = [
            FakeFluxRecord({"_time": t0 + timedelta(seconds=0 * 30), "transport": "mqtt"}, t0 + timedelta(seconds=0), 20.0, "temp", "nexus_telem"),
            FakeFluxRecord({"_time": t0 + timedelta(seconds=1 * 30), "transport": "mqtt"}, t0 + timedelta(seconds=30), 20.5, "temp", "nexus_telem"),
            FakeFluxRecord({"_time": t0 + timedelta(seconds=2 * 30), "transport": "mqtt"}, t0 + timedelta(seconds=60), 21.0, "temp", "nexus_telem"),
            FakeFluxRecord({"_time": t0 + timedelta(seconds=3 * 30), "transport": "mqtt"}, t0 + timedelta(seconds=90), 21.5, "temp", "nexus_telem"),
        ]
        self.mock_query_api.query.return_value = [FakeFluxTable(records)]

        trend = TelemetryStatistics.calculate_trend(
            self.service,
            dev="nexus_esp32",
            signal="temp",
            window="-5m",
            stability_threshold_per_min=0.1,
        )

        self.assertEqual(trend.direction, TrendDirection.RISING)
        self.assertAlmostEqual(trend.slope_per_minute, 1.0, places=2)
        self.assertAlmostEqual(trend.delta, 1.5, places=2)

    def test_calculate_trend_stable(self) -> None:
        t0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        records = [
            FakeFluxRecord({"_time": t0, "transport": "mqtt"}, t0, 22.01, "temp", "nexus_telem"),
            FakeFluxRecord({"_time": t0 + timedelta(seconds=30), "transport": "mqtt"}, t0 + timedelta(seconds=30), 22.02, "temp", "nexus_telem"),
            FakeFluxRecord({"_time": t0 + timedelta(seconds=60), "transport": "mqtt"}, t0 + timedelta(seconds=60), 22.01, "temp", "nexus_telem"),
        ]
        self.mock_query_api.query.return_value = [FakeFluxTable(records)]

        trend = TelemetryStatistics.calculate_trend(
            self.service,
            dev="nexus_esp32",
            signal="temp",
            window="-5m",
            stability_threshold_per_min=0.05,
        )

        self.assertEqual(trend.direction, TrendDirection.STABLE)


class TestErrorResilience(unittest.TestCase):
    """Test graceful handling of database failure and timeouts without crashing."""

    def test_database_offline_raises_data_source_unavailable(self) -> None:
        mock_client = MagicMock()
        mock_client.query_api.return_value.query.side_effect = Exception("Connection refused to 127.0.0.1:8086")
        service = TelemetryQueryService(client=mock_client)

        with self.assertRaises(DataSourceUnavailableError):
            service.get_latest_reading("nexus_esp32", "temp")

    def test_query_timeout_raises_query_timeout_error(self) -> None:
        mock_client = MagicMock()
        mock_client.query_api.return_value.query.side_effect = Exception("Query execution timeout")
        service = TelemetryQueryService(client=mock_client)

        with self.assertRaises(QueryTimeoutError):
            service.get_history("nexus_esp32", "temp")


class TestQueryBoundsAndFreshness(unittest.TestCase):
    """Verify raw query limits, full-window statistics un-truncated, and freshness semantics."""

    def setUp(self) -> None:
        self.mock_client = MagicMock()
        self.mock_query_api = MagicMock()
        self.mock_client.query_api.return_value = self.mock_query_api
        self.config = InfluxDBConfig(url="http://mock:8086", token="mock-token")
        self.service = TelemetryQueryService(config=self.config, client=self.mock_client)

    def tearDown(self) -> None:
        self.service.close()

    def test_raw_limit_capping_truncates_multi_series_results(self) -> None:
        """When multi-series query returns excessive records, output is strictly truncated to requested limit."""
        t0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        records_s1 = [
            FakeFluxRecord({"_time": t0 + timedelta(seconds=i), "transport": "mqtt"}, t0 + timedelta(seconds=i), 20.0 + i, "temp", "nexus_telem")
            for i in range(100)
        ]
        records_s2 = [
            FakeFluxRecord({"_time": t0 + timedelta(seconds=i), "transport": "serial"}, t0 + timedelta(seconds=i), 20.0 + i, "temp", "nexus_telem")
            for i in range(100)
        ]
        # InfluxDB returned 200 records across 2 tables
        self.mock_query_api.query.return_value = [FakeFluxTable(records_s1), FakeFluxTable(records_s2)]

        # Request limit=50 -> must return strictly 50 records
        results = self.service.get_history("nexus_esp32", "temp", limit=50)
        self.assertEqual(len(results), 50)

    def test_window_statistics_full_window_without_truncation(self) -> None:
        """Full-window statistics query does not include row limit capping in Flux."""
        self.mock_query_api.query.return_value = []

        self.service.get_window_statistics("nexus_esp32", "temp", start="-1h", stop="now()")

        # Inspect generated Flux query (first call is main stats, second is invalid dht count)
        self.assertGreaterEqual(len(self.mock_query_api.query.call_args_list), 1)
        main_flux = self.mock_query_api.query.call_args_list[0][0][0]
        self.assertNotIn("limit(n:", main_flux, "Full-window statistics must not truncate with limit()")
        self.assertIn("mean()", main_flux)
        self.assertIn("count()", main_flux)

    def test_freshness_influxdb_failure_raises_error_not_device_offline(self) -> None:
        """Data-source failure raises DataSourceUnavailableError; never misreported as device stale/offline."""
        self.mock_query_api.query.side_effect = Exception("Connection refused")

        with self.assertRaises(DataSourceUnavailableError):
            TelemetryQuality.get_freshness(self.service, "nexus_esp32")

    def test_freshness_distinguishes_never_seen_from_stale(self) -> None:
        """Freshness report distinguishes unobserved devices from observed-but-stale devices."""
        # Case A: Device has zero records in InfluxDB
        self.mock_query_api.query.return_value = []
        report_empty = TelemetryQuality.get_freshness(self.service, "nexus_esp32", cadence_sec=2.0)
        self.assertFalse(report_empty.has_telemetry)
        self.assertTrue(report_empty.is_stale)
        self.assertIsNone(report_empty.last_seen_host)

        # Case B: Device was seen recently (0.5s ago, cadence 2s * grace 3 = 6s) -> Fresh!
        t_fresh = datetime.now(timezone.utc) - timedelta(seconds=0.5)
        rec_fresh = FakeFluxRecord(
            values={"_time": t_fresh, "dev": "nexus_esp32", "transport": "mqtt", "seq": 10, "uptime_ms": 20000},
            time=t_fresh,
            value=20.0,
            field="temp",
            measurement="nexus_telem",
        )
        self.mock_query_api.query.return_value = [FakeFluxTable([rec_fresh])]
        report_fresh = TelemetryQuality.get_freshness(self.service, "nexus_esp32", cadence_sec=2.0)
        self.assertTrue(report_fresh.has_telemetry)
        self.assertFalse(report_fresh.is_stale)
        self.assertIsNotNone(report_fresh.last_seen_host)

        # Case C: Device was seen 30s ago (> 6s) -> Stale!
        t_stale = datetime.now(timezone.utc) - timedelta(seconds=30.0)
        rec_stale = FakeFluxRecord(
            values={"_time": t_stale, "dev": "nexus_esp32", "transport": "mqtt", "seq": 10, "uptime_ms": 20000},
            time=t_stale,
            value=20.0,
            field="temp",
            measurement="nexus_telem",
        )
        self.mock_query_api.query.return_value = [FakeFluxTable([rec_stale])]
        report_stale = TelemetryQuality.get_freshness(self.service, "nexus_esp32", cadence_sec=2.0)
        self.assertTrue(report_stale.has_telemetry)
        self.assertTrue(report_stale.is_stale)


if __name__ == "__main__":
    unittest.main()

