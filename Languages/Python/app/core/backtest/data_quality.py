from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ...integrations.exchanges.binance import _coerce_interval_seconds


REQUIRED_BACKTEST_COLUMNS = ("open", "high", "low", "close", "volume")
PRICE_COLUMNS = ("open", "high", "low", "close")


class BacktestDataQualityError(ValueError):
    def __init__(self, report: "BacktestDataQualityReport") -> None:
        self.report = report
        super().__init__(report.message())


@dataclass(frozen=True, slots=True)
class BacktestDataQualityReport:
    row_count: int
    missing_columns: tuple[str, ...] = ()
    null_counts: dict[str, int] | None = None
    non_positive_price_counts: dict[str, int] | None = None
    negative_volume_count: int = 0
    invalid_ohlc_count: int = 0
    duplicate_index_count: int = 0
    non_datetime_index: bool = False
    non_monotonic_index: bool = False
    gap_count: int = 0
    max_gap_seconds: float = 0.0
    expected_interval_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.issues()

    def issues(self) -> list[str]:
        issues: list[str] = []
        if self.row_count <= 0:
            issues.append("no rows")
        if self.missing_columns:
            issues.append("missing columns: " + ", ".join(self.missing_columns))
        if self.non_datetime_index:
            issues.append("index must be a DatetimeIndex")
        if self.duplicate_index_count:
            issues.append(f"{self.duplicate_index_count} duplicate timestamp(s)")
        if self.non_monotonic_index:
            issues.append("timestamps are not monotonic increasing")
        if self.gap_count:
            issues.append(
                f"{self.gap_count} candle gap(s); largest gap {self.max_gap_seconds:.0f}s"
            )
        for column, count in sorted((self.null_counts or {}).items()):
            if count:
                issues.append(f"{column} has {count} null/non-finite value(s)")
        for column, count in sorted((self.non_positive_price_counts or {}).items()):
            if count:
                issues.append(f"{column} has {count} non-positive value(s)")
        if self.negative_volume_count:
            issues.append(f"volume has {self.negative_volume_count} negative value(s)")
        if self.invalid_ohlc_count:
            issues.append(f"{self.invalid_ohlc_count} row(s) violate OHLC high/low bounds")
        return issues

    def message(self) -> str:
        issues = self.issues()
        if not issues:
            return "Backtest data quality check passed."
        return "Backtest data quality failed: " + "; ".join(issues)


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def _count_non_finite(series: pd.Series) -> int:
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.to_numpy(dtype=float, copy=False)
    return int((~np.isfinite(values)).sum())


def _gap_summary(index: pd.DatetimeIndex, interval: str) -> tuple[int, float, float]:
    if len(index) < 2:
        expected = _coerce_interval_seconds(interval)
        return 0, 0.0, float(expected)
    expected = float(_coerce_interval_seconds(interval))
    diffs = index.to_series().diff().dropna().dt.total_seconds()
    if diffs.empty:
        return 0, 0.0, expected
    max_gap = float(diffs.max() or 0.0)
    gap_threshold = max(expected * 1.5, expected + 1.0)
    return int((diffs > gap_threshold).sum()), max_gap, expected


def inspect_backtest_frame(df: pd.DataFrame, *, interval: str) -> BacktestDataQualityReport:
    row_count = int(len(df.index)) if isinstance(df, pd.DataFrame) else 0
    if not isinstance(df, pd.DataFrame):
        return BacktestDataQualityReport(row_count=0, missing_columns=REQUIRED_BACKTEST_COLUMNS)

    missing_columns = tuple(column for column in REQUIRED_BACKTEST_COLUMNS if column not in df.columns)
    null_counts: dict[str, int] = {}
    non_positive_price_counts: dict[str, int] = {}
    negative_volume_count = 0
    invalid_ohlc_count = 0
    if not missing_columns:
        for column in REQUIRED_BACKTEST_COLUMNS:
            null_counts[column] = _count_non_finite(df[column])
        for column in PRICE_COLUMNS:
            numeric = _numeric_series(df, column)
            non_positive_price_counts[column] = int((numeric <= 0.0).sum())
        volume = _numeric_series(df, "volume")
        negative_volume_count = int((volume < 0.0).sum())
        open_values = _numeric_series(df, "open")
        high_values = _numeric_series(df, "high")
        low_values = _numeric_series(df, "low")
        close_values = _numeric_series(df, "close")
        invalid_ohlc_count = int(
            (
                (high_values < low_values)
                | (high_values < open_values)
                | (high_values < close_values)
                | (low_values > open_values)
                | (low_values > close_values)
            ).sum()
        )

    index = df.index
    non_datetime_index = not isinstance(index, pd.DatetimeIndex)
    duplicate_index_count = int(index.duplicated().sum()) if row_count else 0
    non_monotonic_index = bool(row_count and not getattr(index, "is_monotonic_increasing", False))
    gap_count = 0
    max_gap_seconds = 0.0
    expected_interval_seconds = float(_coerce_interval_seconds(interval))
    if isinstance(index, pd.DatetimeIndex) and not non_monotonic_index and duplicate_index_count == 0:
        gap_count, max_gap_seconds, expected_interval_seconds = _gap_summary(index, interval)

    return BacktestDataQualityReport(
        row_count=row_count,
        missing_columns=missing_columns,
        null_counts=null_counts,
        non_positive_price_counts=non_positive_price_counts,
        negative_volume_count=negative_volume_count,
        invalid_ohlc_count=invalid_ohlc_count,
        duplicate_index_count=duplicate_index_count,
        non_datetime_index=non_datetime_index,
        non_monotonic_index=non_monotonic_index,
        gap_count=gap_count,
        max_gap_seconds=max_gap_seconds,
        expected_interval_seconds=expected_interval_seconds,
    )


def validate_backtest_frame(df: pd.DataFrame, *, interval: str) -> BacktestDataQualityReport:
    report = inspect_backtest_frame(df, interval=interval)
    if not report.ok:
        raise BacktestDataQualityError(report)
    return report
