from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from app.core.strategy.runtime.strategy_runtime import _fetch_cycle_market_state
from app.core.strategy.orders.operational_snapshot import operational_snapshot_issues
from app.integrations.exchanges.binance.market.data_quality import (
    build_live_market_data_quality,
    market_data_quality_issues,
)
from app.integrations.exchanges.binance.transport import ws_runtime


def _frame(*, start_ms: int, periods: int = 3, step_ms: int = 60_000) -> pd.DataFrame:
    index = pd.to_datetime([start_ms + step_ms * offset for offset in range(periods)], unit="ms")
    return pd.DataFrame(
        {
            "open": [100.0 + offset for offset in range(periods)],
            "high": [101.0 + offset for offset in range(periods)],
            "low": [99.0 + offset for offset in range(periods)],
            "close": [100.5 + offset for offset in range(periods)],
            "volume": [10.0] * periods,
        },
        index=index,
    )


def _quality(*, now: float, event_age: float = 30.0, closed: bool = True, frame=None):
    frame = frame if frame is not None else _frame(start_ms=int((now - 180.0) * 1000))
    return build_live_market_data_quality(
        frame,
        "1m",
        now_epoch=now,
        source="binance-futures-rest",
        metadata={
            "event_time_ms": int((now - event_age) * 1000),
            "receipt_time_ms": int(now * 1000),
            "closed": closed,
            "index_monotonic": bool(frame.index.is_monotonic_increasing),
            "index_unique": bool(frame.index.is_unique),
        },
    )


class _LiveCycleStrategy:
    def __init__(self, quality: dict[str, object] | None):
        self.config = {"symbol": "BTCUSDT", "interval": "1m", "lookback": 3, "mode": "Live"}
        frame = _frame(start_ms=1_999_820_000_000)
        frame.attrs["market_data_quality"] = quality
        self.frame = frame
        self.binance = SimpleNamespace(mode="Live", get_klines=lambda *_args, **_kwargs: self.frame)
        self.logs: list[str] = []

    def _reconcile_liquidations(self, _symbol: str) -> None:
        return None

    def stopped(self) -> bool:
        return False

    def compute_indicators(self, _frame):
        return {}

    def generate_signal(self, _frame, _indicators):
        return "BUY", "fresh source event", 100.0, ["rsi"], {}

    def log(self, message: str) -> None:
        self.logs.append(message)


class LiveMarketDataQualityTests(unittest.TestCase):
    def test_fresh_closed_data_is_ready_and_reages_at_order_boundary(self):
        now = 2_000_000.0
        quality = _quality(now=now)

        self.assertTrue(quality["ok"])
        self.assertEqual([], market_data_quality_issues(quality, now_epoch=now + 10.0))
        self.assertIn("event_time_ms", quality)
        self.assertIn("receipt_time_ms", quality)
        self.assertIn("clock_skew_seconds", quality)

    def test_stale_open_and_future_source_data_are_actionable(self):
        now = 2_000_000.0
        stale = _quality(now=now, event_age=300.0)
        self.assertFalse(stale["ok"])
        self.assertTrue(any("stale" in issue for issue in stale["reasons"]))

        open_bar = _quality(now=now, closed=False)
        self.assertIn("market-data latest candle is still open", open_bar["reasons"])
        self.assertIn(
            "market-data latest candle is still open",
            market_data_quality_issues(open_bar, now_epoch=now),
        )

        future = _quality(now=now, event_age=-10.0)
        self.assertIn("source event timestamp is in the future", " ".join(future["reasons"]))

    def test_invalid_ohlcv_duplicate_and_gap_data_fails_closed(self):
        now = 2_000_000.0
        invalid_frame = _frame(start_ms=int((now - 180.0) * 1000))
        invalid_frame.iloc[1, invalid_frame.columns.get_loc("close")] = float("nan")
        invalid_frame.iloc[2, invalid_frame.columns.get_loc("volume")] = -1.0
        invalid = _quality(now=now, frame=invalid_frame)
        self.assertFalse(invalid["finite_ohlcv"])
        self.assertFalse(invalid["volume_valid"])

        duplicate = _frame(start_ms=int((now - 180.0) * 1000))
        duplicate.index = [duplicate.index[0], duplicate.index[0], duplicate.index[2]]
        duplicate_quality = _quality(now=now, frame=duplicate)
        self.assertFalse(duplicate_quality["index_unique"])
        self.assertIn("market-data index contains duplicates", duplicate_quality["reasons"])

        gap = _frame(start_ms=int((now - 300.0) * 1000), step_ms=120_000)
        gap_quality = _quality(now=now, frame=gap)
        self.assertFalse(gap_quality["gap_free"])
        self.assertIn("cadence violation", " ".join(gap_quality["reasons"]))

    def test_operational_snapshot_includes_market_data_quality_reasons(self):
        generated = "2033-05-18T03:33:20+00:00"
        snapshot = {
            "health": "ok",
            "generated_at": generated,
            "freshness": {
                key: {
                    "stale": False,
                    "generated_at": generated,
                    "age_seconds": 0.0,
                    "max_age_seconds": limit,
                }
                for key, limit in (
                    ("exchange_connector", 120.0),
                    ("account", 300.0),
                    ("portfolio", 300.0),
                )
            },
        }
        quality = _quality(now=2_000_000.0, event_age=300.0)
        issues = operational_snapshot_issues(
            snapshot,
            {},
            now_epoch=2_000_000.0,
            market_data_quality=quality,
        )
        self.assertTrue(any("market-data is stale" in issue for issue in issues))

    def test_live_cycle_blocks_bad_quality_and_uses_exchange_event_timestamp(self):
        now = time.time()
        fresh = _quality(now=now, event_age=30.0)
        strategy = _LiveCycleStrategy(fresh)
        with patch("app.core.strategy.runtime.strategy_runtime.time.time", return_value=now):
            state = _fetch_cycle_market_state(strategy, ctx={"cw": strategy.config})
        self.assertIsNotNone(state)
        self.assertEqual(fresh["event_time_ms"] / 1000.0, state["signal_timestamp"])

        stale = _quality(now=now, event_age=300.0)
        blocked = _LiveCycleStrategy(stale)
        with patch("app.core.strategy.runtime.strategy_runtime.time.time", return_value=now):
            self.assertIsNone(_fetch_cycle_market_state(blocked, ctx={"cw": blocked.config}))
        self.assertTrue(any("market-data quality" in message for message in blocked.logs))

        missing = _LiveCycleStrategy(None)
        with patch("app.core.strategy.runtime.strategy_runtime.time.time", return_value=now):
            self.assertIsNone(_fetch_cycle_market_state(missing, ctx={"cw": missing.config}))


class WebsocketOrderingQualityTests(unittest.TestCase):
    def test_replayed_or_out_of_order_messages_do_not_refresh_receipt_time(self):
        harness = SimpleNamespace(
            _ws_enabled=True,
            _ws_kline_cache={},
            _ws_kline_rejections={},
            _ws_lock=__import__("threading").RLock(),
        )
        first = {
            "E": 100_000,
            "k": {"s": "BTCUSDT", "i": "1m", "t": 60_000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "4", "x": True},
        }
        with patch.object(ws_runtime.time, "time", return_value=100.0):
            ws_runtime._ws_kline_handler(harness, first)
        original = dict(harness._ws_kline_cache[("BTCUSDT", "1m")])

        replay = {"E": 99_000, "k": {**first["k"], "c": "1.9"}}
        with patch.object(ws_runtime.time, "time", return_value=200.0):
            ws_runtime._ws_kline_handler(harness, replay)
        current = harness._ws_kline_cache[("BTCUSDT", "1m")]
        self.assertEqual(original["event_time"], current["event_time"])
        self.assertEqual(original["receipt_time_ms"], current["receipt_time_ms"])
        self.assertIn(("BTCUSDT", "1m"), harness._ws_kline_rejections)


if __name__ == "__main__":
    unittest.main()
