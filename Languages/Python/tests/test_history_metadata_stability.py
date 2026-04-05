from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.history_records_emit_runtime import build_raw_history_records  # noqa: E402
from app.gui.positions.history_records_group_runtime import group_history_records  # noqa: E402
from app.gui.positions.history_records_meta_runtime import build_meta_map  # noqa: E402


class _HistoryMetadataWindowStub:
    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None

    def _canonicalize_interval(self, value):
        if value is None:
            return None
        return str(value).strip().lower() or None


def _normalize_indicator_values(values):
    return [
        str(value).strip()
        for value in (values or [])
        if str(value).strip()
    ]


def _derive_margin_snapshot(*_args, **_kwargs):
    return (0.0, 0.0, 0.0, 0.0)


class HistoryMetadataStabilityTests(unittest.TestCase):
    def test_build_meta_map_collapses_equivalent_interval_aliases(self):
        metadata = {
            "meta-60m-a": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "60m",
                "indicators": ["rsi"],
                "stop_loss_enabled": False,
            },
            "meta-1h-b": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1h",
                "indicators": ["rsi"],
                "stop_loss_enabled": True,
            },
        }

        self.assertEqual(
            [
                {
                    "interval": "1h",
                    "indicators": ["rsi"],
                    "stop_loss_enabled": True,
                }
            ],
            build_meta_map(metadata)[("BTCUSDT", "L")],
        )

    def test_build_meta_map_is_order_insensitive_and_merges_duplicate_flags(self):
        forward_metadata = {
            "meta-5m": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "5m",
                "indicators": ["macd"],
                "stop_loss_enabled": False,
            },
            "meta-1m-a": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1m",
                "indicators": ["rsi"],
                "stop_loss_enabled": False,
            },
            "meta-1m-b": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1m",
                "indicators": ["rsi"],
                "stop_loss_enabled": True,
            },
        }
        reverse_metadata = dict(reversed(list(forward_metadata.items())))

        forward_map = build_meta_map(forward_metadata)
        reverse_map = build_meta_map(reverse_metadata)

        self.assertEqual(forward_map, reverse_map)
        self.assertEqual(
            [
                {
                    "interval": "1m",
                    "indicators": ["rsi"],
                    "stop_loss_enabled": True,
                },
                {
                    "interval": "5m",
                    "indicators": ["macd"],
                    "stop_loss_enabled": False,
                },
            ],
            forward_map[("BTCUSDT", "L")],
        )

    def test_duplicate_metadata_stop_loss_fallback_is_stable_after_grouping(self):
        window = _HistoryMetadataWindowStub()
        open_records = {
            ("BTCUSDT", "L"): {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "1m",
                "open_time": "2026-04-05T12:20:00+00:00",
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 0.25,
                    "margin_usdt": 25.0,
                    "size_usdt": 250.0,
                    "entry_price": 100.0,
                    "leverage": 10,
                },
                "stop_loss_enabled": False,
            }
        }
        metadata = {
            "meta-a": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1m",
                "indicators": ["rsi"],
                "stop_loss_enabled": False,
            },
            "meta-b": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "interval": "1m",
                "indicators": ["rsi"],
                "stop_loss_enabled": True,
            },
        }

        def _grouped_records(raw_metadata):
            raw_records = build_raw_history_records(
                window,
                copy.deepcopy(open_records),
                [],
                build_meta_map(raw_metadata),
                normalize_indicator_values=_normalize_indicator_values,
                derive_margin_snapshot=_derive_margin_snapshot,
            )
            return group_history_records(window, raw_records, {"closed", "liquidated"})

        forward = _grouped_records(metadata)
        reverse = _grouped_records(dict(reversed(list(metadata.items()))))

        self.assertEqual(forward, reverse)
        self.assertEqual(1, len(forward))
        self.assertTrue(forward[0]["stop_loss_enabled"])
        self.assertEqual(["rsi"], forward[0]["indicators"])
        self.assertEqual("1m", forward[0]["entry_tf"])

    def test_entry_tf_fallback_expands_in_canonical_interval_order(self):
        window = _HistoryMetadataWindowStub()
        open_records = {
            ("BTCUSDT", "L"): {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "5m, 1m, 5m",
                "open_time": "2026-04-05T12:20:00+00:00",
                "close_time": "-",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 0.25,
                    "margin_usdt": 25.0,
                    "size_usdt": 250.0,
                    "entry_price": 100.0,
                },
                "stop_loss_enabled": False,
            }
        }

        raw_records = build_raw_history_records(
            window,
            open_records,
            [],
            {},
            normalize_indicator_values=_normalize_indicator_values,
            derive_margin_snapshot=_derive_margin_snapshot,
        )

        self.assertEqual(["1m", "5m"], [record["entry_tf"] for record in raw_records])


if __name__ == "__main__":
    unittest.main()
