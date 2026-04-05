from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.record_build_helpers import (  # noqa: E402
    _apply_interval_metadata_to_row,
    _seed_positions_map_from_rows,
)


class _LiveMetadataWindowStub:
    def __init__(self, metadata: dict | None = None) -> None:
        self._engine_indicator_map = metadata or {}
        self._entry_times_by_iv: dict[tuple[str, str, str], str] = {}
        self._entry_intervals: dict[str, dict[str, set[str]]] = {}
        self._entry_times: dict[tuple[str, str], str] = {}
        self._pending_close_times: dict[tuple[str, str], str] = {}

    def _position_stop_loss_enabled(self, *_args, **_kwargs) -> bool:
        return False

    def _canonicalize_interval(self, value):
        if value is None:
            return None
        return str(value).strip().lower() or None

    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None

    def _format_display_time(self, value) -> str:
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        return str(value)


class LiveMetadataIndicatorFallbackTests(unittest.TestCase):
    def test_seed_positions_map_matches_metadata_across_interval_aliases(self):
        window = _LiveMetadataWindowStub(
            {
                "meta-1h": {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "interval": "1h",
                    "indicators": ["rsi"],
                },
            }
        )
        base_rows = [
            {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "60m",
                "open_time": "2026-04-05T12:20:00+00:00",
                "qty": 0.25,
                "margin_usdt": 25.0,
                "size_usdt": 250.0,
                "entry_price": 100.0,
            }
        ]

        positions_map = _seed_positions_map_from_rows(window, base_rows, {}, {})
        record = positions_map[("BTCUSDT", "L")]

        self.assertEqual(["rsi"], record["indicators"])
        self.assertEqual(["rsi"], record["data"]["trigger_indicators"])

    def test_seed_positions_map_uses_primary_metadata_indicators_when_row_has_none(self):
        window = _LiveMetadataWindowStub(
            {
                "meta-5m": {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "interval": "5m",
                    "indicators": ["macd"],
                },
                "meta-1m": {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "interval": "1m",
                    "indicators": ["rsi"],
                },
            }
        )
        base_rows = [
            {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "5m, 1m",
                "open_time": "2026-04-05T12:20:00+00:00",
                "qty": 0.25,
                "margin_usdt": 25.0,
                "size_usdt": 250.0,
                "entry_price": 100.0,
            }
        ]

        positions_map = _seed_positions_map_from_rows(window, base_rows, {}, {})
        record = positions_map[("BTCUSDT", "L")]

        self.assertEqual(["rsi"], record["indicators"])
        self.assertEqual(["rsi"], record["data"]["trigger_indicators"])

    def test_apply_interval_metadata_fallback_is_order_insensitive(self):
        forward_metadata = {
            "meta-5m": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "5m",
                "indicators": ["macd"],
            },
            "meta-1m-a": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1m",
                "indicators": ["rsi"],
            },
            "meta-1m-b": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1m",
                "indicators": ["rsi"],
            },
        }

        def _apply(metadata: dict) -> dict:
            window = _LiveMetadataWindowStub(metadata)
            data: dict[str, object] = {}
            record = {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "-",
                "open_time": "-",
                "close_time": "-",
                "status": "Active",
                "data": data,
                "indicators": [],
            }
            _apply_interval_metadata_to_row(
                window,
                sym="BTCUSDT",
                side_key="L",
                rec=record,
                data=data,
                allocations_existing=[],
                intervals_from_alloc=set(),
                interval_display={},
                interval_lookup={},
                interval_trigger_map={},
                trigger_union=set(),
            )
            return record

        forward = _apply(copy.deepcopy(forward_metadata))
        reverse = _apply(dict(reversed(list(forward_metadata.items()))))

        self.assertEqual(forward, reverse)
        self.assertEqual("1m, 5m", forward["entry_tf"])
        self.assertEqual("1m", forward["data"]["interval_display"])
        self.assertEqual(["rsi"], forward["indicators"])
        self.assertEqual(["rsi"], forward["data"]["trigger_indicators"])

    def test_apply_interval_metadata_does_not_override_existing_row_triggers(self):
        window = _LiveMetadataWindowStub(
            {
                "meta-1m": {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "interval": "1m",
                    "indicators": ["rsi"],
                }
            }
        )
        data: dict[str, object] = {
            "trigger_indicators": ["ema"],
        }
        record = {
            "symbol": "BTCUSDT",
            "side_key": "L",
            "entry_tf": "-",
            "open_time": "-",
            "close_time": "-",
            "status": "Active",
            "data": data,
            "indicators": ["ema"],
        }
        _apply_interval_metadata_to_row(
            window,
            sym="BTCUSDT",
            side_key="L",
            rec=record,
            data=data,
            allocations_existing=[],
            intervals_from_alloc=set(),
            interval_display={},
            interval_lookup={},
            interval_trigger_map={},
            trigger_union=set(),
        )

        self.assertEqual(["ema"], record["indicators"])
        self.assertEqual(["ema"], data["trigger_indicators"])
        self.assertEqual("1m", data["interval_display"])


if __name__ == "__main__":
    unittest.main()
