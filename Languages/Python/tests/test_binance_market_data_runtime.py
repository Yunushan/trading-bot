from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

from app.integrations.exchanges.binance.market.market_data import (
    _fetch_futures_klines_rest,
    _get_klines_range_custom,
    _get_klines_range_native,
    _interval_seconds_to_freq,
    _klines_raw_to_df,
    get_klines,
    get_klines_range,
)


class _NetworkConnectivityError(RuntimeError):
    pass


def _raw_row(open_time: int, *, open_value: str = "1", close_value: str = "2", volume: str = "3") -> list:
    return [
        open_time,
        open_value,
        "4",
        "0.5",
        close_value,
        volume,
        open_time + 59_999,
        "0",
        1,
        "0",
        "0",
        "0",
    ]


class _Client:
    def __init__(self, rows: list[list] | None = None) -> None:
        self.rows = list(rows or [])
        self.futures_calls: list[dict] = []
        self.spot_calls: list[dict] = []
        self.error: Exception | None = None

    def futures_klines(self, **params):
        self.futures_calls.append(dict(params))
        if self.error is not None:
            raise self.error
        return list(self.rows)

    def get_klines(self, **params):
        self.spot_calls.append(dict(params))
        if self.error is not None:
            raise self.error
        return list(self.rows)


class _Wrapper:
    get_klines = get_klines
    get_klines_range = get_klines_range
    _fetch_futures_klines_rest = _fetch_futures_klines_rest
    _get_klines_range_native = _get_klines_range_native
    _get_klines_range_custom = _get_klines_range_custom
    _klines_raw_to_df = staticmethod(_klines_raw_to_df)
    _interval_seconds_to_freq = staticmethod(_interval_seconds_to_freq)
    _network_connectivity_error_cls = _NetworkConnectivityError

    def __init__(self, rows: list[list] | None = None) -> None:
        self.indicator_source = "binance futures"
        self.account_type = "FUTURES"
        self.client = _Client(rows)
        self._kline_cache_lock = threading.RLock()
        self._kline_cache: dict[tuple, dict] = {}
        self._last_ban_log = 0.0
        self._last_network_log = 0.0
        self._last_network_error_log = 0.0
        self.ban_remaining = 0.0
        self.ban_until: float | None = None
        self.live_futures = False
        self.live_symbol_available = True
        self.ws_row = None
        self.logs: list[tuple[str, str]] = []
        self.offline_events: list[tuple[str, Exception]] = []
        self.recovered_count = 0
        self.streams: list[tuple[str, str]] = []

    @staticmethod
    def _futures_base() -> str:
        return "https://testnet.example"

    @staticmethod
    def _futures_base_live() -> str:
        return "https://live.example"

    def _seconds_until_unban(self) -> float:
        return self.ban_remaining

    def _handle_potential_ban(self, _exc: Exception) -> float | None:
        return self.ban_until

    def _use_live_futures_data_for_indicators(self) -> bool:
        return self.live_futures

    def _symbol_available_on_live_futures(self, _symbol: str) -> bool:
        return self.live_symbol_available

    def _ensure_ws_stream(self, symbol: str, interval: str) -> None:
        self.streams.append((symbol, interval))

    def _ws_latest_candle(self, _symbol: str, _interval: str):
        return self.ws_row

    def _handle_network_offline(self, context: str, exc: Exception) -> None:
        self.offline_events.append((context, exc))

    def _handle_network_recovered(self) -> None:
        self.recovered_count += 1

    def _log(self, message: str, *, lvl: str = "info") -> None:
        self.logs.append((message, lvl))


class BinanceMarketDataRuntimeTests(unittest.TestCase):
    def test_rest_fetch_uses_selected_base_and_normalizes_symbol(self):
        wrapper = _Wrapper()
        response = Mock()
        response.json.return_value = [["ok"]]

        with patch("app.integrations.exchanges.binance.market.market_data.requests.get", return_value=response) as get:
            result = wrapper._fetch_futures_klines_rest({"symbol": "btcusdt", "limit": 5}, live=True)

        self.assertEqual([["ok"]], result)
        get.assert_called_once_with(
            "https://live.example/v1/klines",
            params={"symbol": "BTCUSDT", "limit": 5},
            timeout=10,
        )
        response.raise_for_status.assert_called_once_with()

    def test_raw_conversion_is_numeric_and_empty_result_has_stable_schema(self):
        empty = _klines_raw_to_df([])
        self.assertEqual(["open", "high", "low", "close", "volume"], list(empty.columns))
        self.assertTrue(empty.empty)

        frame = _klines_raw_to_df([_raw_row(1_700_000_000_000)])
        self.assertEqual(1.0, frame.iloc[0]["open"])
        self.assertEqual(2.0, frame.iloc[0]["close"])
        self.assertTrue(pd.api.types.is_numeric_dtype(frame["volume"]))

    def test_interval_frequency_rejects_non_positive_values(self):
        self.assertEqual("2D", _interval_seconds_to_freq(172_800))
        self.assertEqual("3h", _interval_seconds_to_freq(10_800))
        self.assertEqual("5min", _interval_seconds_to_freq(300))
        self.assertEqual("45S", _interval_seconds_to_freq(45))
        for value in (0, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _interval_seconds_to_freq(value)

    def test_native_fetch_is_cached_and_returns_defensive_copies(self):
        wrapper = _Wrapper([_raw_row(1_700_000_000_000)])

        first = wrapper.get_klines("btcusdt", "1m", limit=1)
        first.iloc[0, first.columns.get_loc("close")] = 99.0
        second = wrapper.get_klines("btcusdt", "1m", limit=1)

        self.assertEqual(2.0, second.iloc[0]["close"])
        self.assertEqual(1, len(wrapper.client.futures_calls))
        self.assertEqual(1, wrapper.recovered_count)

    def test_active_ban_serves_stale_cache_or_fails_closed(self):
        wrapper = _Wrapper()
        cache_key = ("binance futures", "BTCUSDT", "1m", 1)
        cached = _klines_raw_to_df([_raw_row(1_700_000_000_000)])
        wrapper._kline_cache[cache_key] = {"df": cached, "ts": 0.0}
        wrapper.ban_remaining = 30.0

        with patch("app.integrations.exchanges.binance.market.market_data.time.time", return_value=10_000.0):
            result = wrapper.get_klines("BTCUSDT", "1m", limit=1)
        self.assertEqual(2.0, result.iloc[0]["close"])
        self.assertTrue(any("Serving cached klines" in message for message, _ in wrapper.logs))

        wrapper._kline_cache.clear()
        with self.assertRaisesRegex(RuntimeError, "binance_rest_banned:30s"):
            wrapper.get_klines("BTCUSDT", "1m", limit=1)

    def test_spot_and_custom_intervals_use_the_correct_data_paths(self):
        spot = _Wrapper([_raw_row(1_700_000_000_000)])
        spot.indicator_source = "spot"
        spot.account_type = "SPOT"
        spot.get_klines("BTCUSDT", "1m", limit=1)
        self.assertEqual(1, len(spot.client.spot_calls))
        self.assertEqual([], spot.client.futures_calls)

        custom = _Wrapper()
        custom_frame = _klines_raw_to_df(
            [_raw_row(1_700_000_000_000 + offset * 120_000) for offset in range(3)]
        )
        custom.get_klines_range = Mock(return_value=custom_frame)
        result = custom.get_klines("BTCUSDT", "2m", limit=2)
        self.assertEqual(2, len(result))
        custom.get_klines_range.assert_called_once()

    def test_network_errors_are_classified_and_recorded(self):
        wrapper = _Wrapper()
        wrapper.client.error = requests.ConnectionError("offline token=secret")

        with self.assertRaisesRegex(_NetworkConnectivityError, "network_offline:BTCUSDT@1m"):
            wrapper.get_klines("BTCUSDT", "1m", limit=1)

        self.assertEqual(1, len(wrapper.offline_events))
        self.assertIn("fetching BTCUSDT@1m", wrapper.offline_events[0][0])

    def test_live_futures_falls_back_to_connector_when_symbol_is_unavailable(self):
        wrapper = _Wrapper([_raw_row(1_700_000_000_000)])
        wrapper.live_futures = True
        wrapper.live_symbol_available = False

        result = wrapper.get_klines("BTCUSDT", "1m", limit=1)

        self.assertEqual(1, len(result))
        self.assertEqual([("BTCUSDT", "1m")], wrapper.streams)
        self.assertTrue(any("falling back to testnet" in message for message, _ in wrapper.logs))

    def test_live_futures_rest_result_is_merged_with_latest_websocket_candle(self):
        start_ms = 1_700_000_000_000
        wrapper = _Wrapper()
        wrapper.live_futures = True
        wrapper._fetch_futures_klines_rest = Mock(return_value=[_raw_row(start_ms)])
        wrapper.ws_row = {
            "open_time": start_ms,
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 50.0,
        }

        result = wrapper.get_klines("BTCUSDT", "1m", limit=1)

        self.assertEqual(11.0, result.iloc[0]["close"])
        self.assertEqual(50.0, result.iloc[0]["volume"])
        wrapper._fetch_futures_klines_rest.assert_called_once()

    def test_live_futures_rest_failure_falls_back_without_exposing_secret(self):
        wrapper = _Wrapper([_raw_row(1_700_000_000_000)])
        wrapper.live_futures = True
        wrapper._fetch_futures_klines_rest = Mock(side_effect=RuntimeError("token=secret-value"))

        result = wrapper.get_klines("BTCUSDT", "1m", limit=1)

        self.assertEqual(1, len(result))
        messages = "\n".join(message for message, _ in wrapper.logs)
        self.assertIn("falling back to testnet", messages)
        self.assertNotIn("secret-value", messages)

    def test_empty_custom_range_uses_stale_cache_then_fails_without_it(self):
        wrapper = _Wrapper()
        cache_key = ("binance futures", "BTCUSDT", "2m", 1)
        cached = _klines_raw_to_df([_raw_row(1_700_000_000_000)])
        wrapper._kline_cache[cache_key] = {"df": cached, "ts": 0.0}
        wrapper.get_klines_range = Mock(return_value=_klines_raw_to_df([]))

        with patch("app.integrations.exchanges.binance.market.market_data.time.time", return_value=10_000.0):
            result = wrapper.get_klines("BTCUSDT", "2m", limit=1)
        self.assertEqual(2.0, result.iloc[0]["close"])

        wrapper._kline_cache.clear()
        with self.assertRaisesRegex(RuntimeError, "No kline data returned for interval '2m'"):
            wrapper.get_klines("BTCUSDT", "2m", limit=1)

    def test_native_range_fetches_bounded_window(self):
        start = pd.Timestamp("2026-01-01T00:00:00")
        rows = [
            _raw_row(int(start.timestamp() * 1000)),
            _raw_row(int((start + pd.Timedelta(minutes=1)).timestamp() * 1000)),
        ]
        wrapper = _Wrapper(rows)

        result = wrapper._get_klines_range_native(
            "BTCUSDT",
            "1m",
            start,
            start + pd.Timedelta(minutes=2),
            100,
            "FUTURES",
            "binance futures",
        )

        self.assertEqual(2, len(result))
        self.assertEqual(1, len(wrapper.client.futures_calls))
        call = wrapper.client.futures_calls[0]
        self.assertEqual(int(start.timestamp() * 1000), call["startTime"])
        self.assertEqual(100, call["limit"])

    def test_custom_range_resamples_ohlcv_without_lookahead(self):
        start = pd.Timestamp("2026-01-01T00:00:00")
        index = pd.date_range(start, periods=4, freq="1min")
        base = pd.DataFrame(
            {
                "open": [1.0, 2.0, 3.0, 4.0],
                "high": [2.0, 3.0, 4.0, 5.0],
                "low": [0.0, 1.0, 2.0, 3.0],
                "close": [1.5, 2.5, 3.5, 4.5],
                "volume": [10.0, 20.0, 30.0, 40.0],
            },
            index=index,
        )
        wrapper = _Wrapper()
        wrapper._get_klines_range_native = Mock(return_value=base)

        result = wrapper._get_klines_range_custom(
            "BTCUSDT", "2m", start, start + pd.Timedelta(minutes=3), 4, "FUTURES", "futures"
        )

        self.assertEqual(2, len(result))
        self.assertEqual(1.0, result.iloc[0]["open"])
        self.assertEqual(2.5, result.iloc[0]["close"])
        self.assertEqual(30.0, result.iloc[0]["volume"])

    def test_month_and_year_aliases_follow_python_minute_fallback(self):
        start = pd.Timestamp("2026-01-01T00:00:00")
        index = pd.date_range(start, periods=3, freq="1min")
        base = pd.DataFrame(
            {
                "open": [1.0, 2.0, 3.0],
                "high": [2.0, 3.0, 4.0],
                "low": [0.0, 1.0, 2.0],
                "close": [1.5, 2.5, 3.5],
                "volume": [10.0, 20.0, 30.0],
            },
            index=index,
        )
        wrapper = _Wrapper()
        wrapper._get_klines_range_native = Mock(return_value=base)

        for alias in ("1month", "1mo", "1y"):
            with self.subTest(alias=alias):
                wrapper._get_klines_range_native.reset_mock()
                result = wrapper._get_klines_range_custom(
                    "BTCUSDT", alias, start, start + pd.Timedelta(minutes=2), 2, "FUTURES", "futures"
                )

                self.assertEqual(3, len(result))
                call = wrapper._get_klines_range_native.call_args.args
                self.assertEqual("1m", call[1])
                self.assertEqual(pd.Timedelta(minutes=3), call[3] - call[2])

    def test_custom_range_rejects_unrepresentable_intervals(self):
        wrapper = _Wrapper()
        with self.assertRaisesRegex(NotImplementedError, "below 1 minute"):
            wrapper._get_klines_range_custom("BTCUSDT", "45s", 0, 1, 1, "FUTURES", "futures")
        with self.assertRaisesRegex(NotImplementedError, "not a multiple"):
            wrapper._get_klines_range_custom("BTCUSDT", "90m", 0, 1, 1, "FUTURES", "futures")

    def test_public_range_normalizes_aware_timestamps_to_utc(self):
        wrapper = _Wrapper()
        expected = _klines_raw_to_df([_raw_row(1_767_225_600_000)])
        wrapper._get_klines_range_native = Mock(return_value=expected)
        local_tz = timezone(timedelta(hours=3))

        result = wrapper.get_klines_range(
            "BTCUSDT",
            "1m",
            datetime(2026, 1, 1, 3, 0, tzinfo=local_tz),
            pd.Timestamp("2026-01-01T04:00:00+03:00"),
            limit=10,
        )

        self.assertEqual(1, len(result))
        call = wrapper._get_klines_range_native.call_args.args
        self.assertEqual(pd.Timestamp("2026-01-01T00:00:00"), call[2])
        self.assertEqual(pd.Timestamp("2026-01-01T01:00:00"), call[3])

    def test_public_range_accepts_epoch_milliseconds(self):
        wrapper = _Wrapper()
        wrapper._get_klines_range_native = Mock(
            return_value=_klines_raw_to_df([_raw_row(1_767_225_600_000)])
        )

        wrapper.get_klines_range(
            "BTCUSDT",
            "1m",
            1_767_225_600_000,
            1_767_229_200_000,
            limit=10,
        )

        call = wrapper._get_klines_range_native.call_args.args
        self.assertEqual(pd.Timestamp("2026-01-01T00:00:00"), call[2])
        self.assertEqual(pd.Timestamp("2026-01-01T01:00:00"), call[3])

    def test_public_range_rejects_invalid_boundaries_sources_and_empty_data(self):
        wrapper = _Wrapper()
        for start, end, message in (
            ("NaT", "2026-01-02", "Invalid start_time"),
            ("2026-01-01", "NaT", "Invalid end_time"),
            ("2026-01-02", "2026-01-01", "end_time must be greater"),
        ):
            with self.subTest(start=start, end=end), self.assertRaisesRegex(ValueError, message):
                wrapper.get_klines_range("BTCUSDT", "1m", start, end)

        wrapper.indicator_source = "bybit"
        with self.assertRaisesRegex(NotImplementedError, "not supported for source 'bybit'"):
            wrapper.get_klines_range("BTCUSDT", "1m", "2026-01-01", "2026-01-02")

        wrapper.indicator_source = "futures"
        wrapper._get_klines_range_native = Mock(return_value=_klines_raw_to_df([]))
        with self.assertRaisesRegex(RuntimeError, "No kline data"):
            wrapper.get_klines_range("BTCUSDT", "1m", "2026-01-01", "2026-01-02")


if __name__ == "__main__":
    unittest.main()
