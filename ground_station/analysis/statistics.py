"""NEXUS Telemetry Statistics & Trend Calculation.

Provides deterministic calculations for:
- Window comparisons (current vs prior time window delta & percent change).
- Linear trend analysis (slope per minute, direction, and magnitude).
- In-memory series aggregation without silent zeros for missing values.
"""

from __future__ import annotations

from typing import List, Optional

from .models import (
    SignalSummary,
    TelemetryRecord,
    TrendDirection,
    TrendSummary,
    WindowComparison,
)
from .telemetry_query import TelemetryQueryService


class TelemetryStatistics:
    """Deterministic statistical and trend analyzer for NEXUS telemetry."""

    @staticmethod
    def calculate_series_summary(
        dev: str,
        signal: str,
        records: List[TelemetryRecord],
        start_time: str,
        stop_time: str,
        invalid_count: int = 0,
    ) -> SignalSummary:
        """Calculate statistical summary from a provided list of TelemetryRecords.

        Missing or None values are never converted to 0.0.
        """
        if not records:
            return SignalSummary(
                dev=dev,
                signal=signal,
                measurement="unknown",
                field_name=signal,
                start_time=start_time,
                stop_time=stop_time,
                sample_count=0,
                invalid_count=invalid_count,
                min_value=None,
                max_value=None,
                mean_value=None,
                first_value=None,
                last_value=None,
                first_time=None,
                last_time=None,
            )

        numeric_vals = [float(r.value) for r in records if isinstance(r.value, (int, float)) and not isinstance(r.value, bool)]
        measurement = records[0].measurement
        field_name = records[0].field

        if not numeric_vals:
            return SignalSummary(
                dev=dev,
                signal=signal,
                measurement=measurement,
                field_name=field_name,
                start_time=start_time,
                stop_time=stop_time,
                sample_count=len(records),
                invalid_count=invalid_count,
                min_value=None,
                max_value=None,
                mean_value=None,
                first_value=records[0].value,
                last_value=records[-1].value,
                first_time=records[0].host_time,
                last_time=records[-1].host_time,
            )

        min_val = min(numeric_vals)
        max_val = max(numeric_vals)
        mean_val = sum(numeric_vals) / len(numeric_vals)

        return SignalSummary(
            dev=dev,
            signal=signal,
            measurement=measurement,
            field_name=field_name,
            start_time=start_time,
            stop_time=stop_time,
            sample_count=len(numeric_vals),
            invalid_count=invalid_count,
            min_value=min_val,
            max_value=max_val,
            mean_value=mean_val,
            first_value=records[0].value,
            last_value=records[-1].value,
            first_time=records[0].host_time,
            last_time=records[-1].host_time,
        )

    @classmethod
    def compare_windows(
        cls,
        query_service: TelemetryQueryService,
        dev: str,
        signal: str,
        current_window: str = "-15m",
        prior_start: str = "-30m",
        prior_stop: str = "-15m",
        transport: Optional[str] = None,
    ) -> WindowComparison:
        """Compare statistics between current window (e.g. -15m to now) and prior window (-30m to -15m).

        Full-window queries are executed directly in InfluxDB to avoid silent data truncation.
        """
        curr_stats = query_service.get_window_statistics(
            dev=dev,
            signal=signal,
            start=current_window,
            stop="now()",
            transport=transport,
        )

        prior_stats = query_service.get_window_statistics(
            dev=dev,
            signal=signal,
            start=prior_start,
            stop=prior_stop,
            transport=transport,
        )

        delta_mean: Optional[float] = None
        pct_change_mean: Optional[float] = None

        if curr_stats.mean_value is not None and prior_stats.mean_value is not None:
            delta_mean = curr_stats.mean_value - prior_stats.mean_value
            if abs(prior_stats.mean_value) > 1e-9:
                pct_change_mean = (delta_mean / abs(prior_stats.mean_value)) * 100.0

        return WindowComparison(
            dev=dev,
            signal=signal,
            current_window=curr_stats,
            prior_window=prior_stats,
            delta_mean=delta_mean,
            pct_change_mean=pct_change_mean,
        )

    @classmethod
    def calculate_trend(
        cls,
        query_service: TelemetryQueryService,
        dev: str,
        signal: str,
        window: str = "-15m",
        transport: Optional[str] = None,
        stability_threshold_per_min: float = 0.05,
    ) -> TrendSummary:
        """Compute deterministic linear trend slope and direction over a time window.

        Args:
            query_service: InfluxDB query client service.
            dev: Allowed device ID.
            signal: Allowed numeric signal.
            window: Time window lookback.
            transport: Optional transport filter.
            stability_threshold_per_min: Minimum rate of change to classify as rising/falling.

        Returns:
            TrendSummary with direction, slope per minute, delta, and boundary values.
        """
        records = query_service.get_history(
            dev=dev,
            signal=signal,
            start=window,
            stop="now()",
            transport=transport,
            limit=1000,
        )

        numeric_records = [
            r for r in records
            if isinstance(r.value, (int, float)) and not isinstance(r.value, bool)
        ]

        if len(numeric_records) < 2:
            return TrendSummary(
                dev=dev,
                signal=signal,
                window=window,
                direction=TrendDirection.INSUFFICIENT_DATA,
                slope_per_minute=None,
                delta=None,
                sample_count=len(numeric_records),
                start_value=numeric_records[0].value if numeric_records else None,
                end_value=numeric_records[-1].value if numeric_records else None,
            )

        # Compute least-squares linear regression: y = slope * t + intercept
        # t_i in seconds relative to first record
        t0 = numeric_records[0].host_time.timestamp()
        t_vals = [r.host_time.timestamp() - t0 for r in numeric_records]
        y_vals = [float(r.value) for r in numeric_records]
        n = len(numeric_records)

        sum_t = sum(t_vals)
        sum_y = sum(y_vals)
        sum_tt = sum(t * t for t in t_vals)
        sum_ty = sum(t * y for t, y in zip(t_vals, y_vals))

        denom = (n * sum_tt) - (sum_t * sum_t)
        if abs(denom) < 1e-9:
            # All samples at exact same timestamp
            slope_sec = 0.0
        else:
            slope_sec = ((n * sum_ty) - (sum_t * sum_y)) / denom

        slope_min = slope_sec * 60.0
        delta = y_vals[-1] - y_vals[0]

        if abs(slope_min) <= stability_threshold_per_min:
            direction = TrendDirection.STABLE
        elif slope_min > 0:
            direction = TrendDirection.RISING
        else:
            direction = TrendDirection.FALLING

        return TrendSummary(
            dev=dev,
            signal=signal,
            window=window,
            direction=direction,
            slope_per_minute=slope_min,
            delta=delta,
            sample_count=n,
            start_value=y_vals[0],
            end_value=y_vals[-1],
        )
