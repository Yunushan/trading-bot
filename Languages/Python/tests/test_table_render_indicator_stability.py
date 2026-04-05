from __future__ import annotations

import copy
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions import table_render_state_runtime  # noqa: E402
from app.gui.positions.table_render_prepare_runtime import _prepare_record_snapshot  # noqa: E402
from app.gui.positions.table_render_rows_runtime import _merge_indicator_sources  # noqa: E402


@contextmanager
def _patched_table_render_state():
    originals = {
        "collect_record_indicator_keys": table_render_state_runtime._collect_record_indicator_keys,
        "collect_indicator_value_strings": table_render_state_runtime._collect_indicator_value_strings,
        "collect_current_indicator_live_strings": table_render_state_runtime._collect_current_indicator_live_strings,
        "dedupe_indicator_entries_normalized": table_render_state_runtime._dedupe_indicator_entries_normalized,
        "filter_indicator_entries": table_render_state_runtime._filter_indicator_entries,
        "indicator_entry_signature": table_render_state_runtime._indicator_entry_signature,
        "indicator_short_label": table_render_state_runtime._indicator_short_label,
    }

    def _collect_record_indicator_keys(rec: dict, **_kwargs) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        sources = rec.get("_aggregated_entries") or [rec]
        for source in sources:
            if not isinstance(source, dict):
                continue
            for indicator in source.get("indicators") or []:
                text = str(indicator or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                ordered.append(text)
        return ordered

    def _collect_indicator_value_strings(
        rec: dict,
        interval_hint: str | None = None,  # noqa: ARG001
    ) -> tuple[list[str], dict[str, list[str]]]:
        values: list[str] = []
        interval_map: dict[str, list[str]] = {}
        sources = rec.get("_aggregated_entries") or [rec]
        for source in sources:
            if not isinstance(source, dict):
                continue
            for entry in source.get("_indicator_value_entries") or []:
                text = str(entry or "").strip()
                if text and text not in values:
                    values.append(text)
            for key, slots in dict(source.get("_indicator_interval_map") or {}).items():
                bucket = interval_map.setdefault(str(key), [])
                for slot in slots or []:
                    slot_text = str(slot or "").strip()
                    if slot_text and slot_text not in bucket:
                        bucket.append(slot_text)
        return values, interval_map

    def _collect_current_indicator_live_strings(*_args, **_kwargs) -> list[str]:
        return []

    def _dedupe_indicator_entries_normalized(entries: list[str] | None) -> list[str]:
        return list(entries or [])

    def _filter_indicator_entries(
        entries: list[str] | None,
        interval_hint: str | None,  # noqa: ARG001
        *,
        include_non_matching: bool = True,  # noqa: ARG001
    ) -> list[str]:
        return list(entries or [])

    def _indicator_entry_signature(entry: str) -> tuple[str, str]:
        parts = str(entry or "").split("@", 1)
        label_part = parts[0].strip().lower()
        interval_part = ""
        if len(parts) == 2:
            interval_part = parts[1].split(None, 1)[0].strip().lower()
        return label_part, interval_part

    def _indicator_short_label(key: Any) -> str:
        return str(key or "").strip().upper()

    setattr(
        table_render_state_runtime,
        "_collect_record_indicator_keys",
        _collect_record_indicator_keys,
    )
    setattr(
        table_render_state_runtime,
        "_collect_indicator_value_strings",
        _collect_indicator_value_strings,
    )
    setattr(
        table_render_state_runtime,
        "_collect_current_indicator_live_strings",
        _collect_current_indicator_live_strings,
    )
    setattr(
        table_render_state_runtime,
        "_dedupe_indicator_entries_normalized",
        _dedupe_indicator_entries_normalized,
    )
    setattr(
        table_render_state_runtime,
        "_filter_indicator_entries",
        _filter_indicator_entries,
    )
    setattr(
        table_render_state_runtime,
        "_indicator_entry_signature",
        _indicator_entry_signature,
    )
    setattr(
        table_render_state_runtime,
        "_indicator_short_label",
        _indicator_short_label,
    )
    try:
        yield
    finally:
        setattr(
            table_render_state_runtime,
            "_collect_record_indicator_keys",
            originals["collect_record_indicator_keys"],
        )
        setattr(
            table_render_state_runtime,
            "_collect_indicator_value_strings",
            originals["collect_indicator_value_strings"],
        )
        setattr(
            table_render_state_runtime,
            "_collect_current_indicator_live_strings",
            originals["collect_current_indicator_live_strings"],
        )
        setattr(
            table_render_state_runtime,
            "_dedupe_indicator_entries_normalized",
            originals["dedupe_indicator_entries_normalized"],
        )
        setattr(
            table_render_state_runtime,
            "_filter_indicator_entries",
            originals["filter_indicator_entries"],
        )
        setattr(
            table_render_state_runtime,
            "_indicator_entry_signature",
            originals["indicator_entry_signature"],
        )
        setattr(
            table_render_state_runtime,
            "_indicator_short_label",
            originals["indicator_short_label"],
        )


def _aggregated_entry(*, indicator: str, interval: str, value: str) -> dict:
    return {
        "symbol": "BTCUSDT",
        "side_key": "L",
        "entry_tf": interval,
        "status": "Active",
        "indicators": [indicator],
        "data": {
            "symbol": "BTCUSDT",
            "side_key": "L",
            "interval_display": interval,
            "trigger_indicators": [indicator],
        },
        "_indicator_value_entries": [f"{indicator.upper()}@{interval.upper()} {value}"],
        "_indicator_interval_map": {indicator: [interval.upper()]},
    }


class _SnapshotWindow:
    pass


class TableRenderIndicatorStabilityTests(unittest.TestCase):
    def test_merge_indicator_sources_is_order_insensitive_for_reversed_aggregates(self):
        rsi_entry = _aggregated_entry(indicator="rsi", interval="1m", value="60.00 -Buy")
        macd_entry = _aggregated_entry(indicator="macd", interval="5m", value="1.00 -Sell")

        with _patched_table_render_state():
            forward = {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "5m, 1m",
                "status": "Active",
                "data": {"symbol": "BTCUSDT", "side_key": "L"},
                "_aggregated_entries": [copy.deepcopy(macd_entry), copy.deepcopy(rsi_entry)],
            }
            reverse = copy.deepcopy(forward)
            reverse["_aggregated_entries"] = [
                copy.deepcopy(rsi_entry),
                copy.deepcopy(macd_entry),
            ]

            first = _merge_indicator_sources(
                forward,
                interval="5m, 1m",
                view_mode="cumulative",
                is_closed_like=False,
            )
            second = _merge_indicator_sources(
                reverse,
                interval="5m, 1m",
                view_mode="cumulative",
                is_closed_like=False,
            )

        self.assertEqual(first, second)
        self.assertEqual(["rsi", "macd"], first[0])
        self.assertEqual(
            ["RSI@1M 60.00 -Buy", "MACD@5M 1.00 -Sell"],
            first[1],
        )
        self.assertEqual(
            {"rsi": ["1M"], "macd": ["5M"]},
            first[2],
        )

    def test_prepare_record_snapshot_is_order_insensitive_for_reversed_aggregates(self):
        rsi_entry = _aggregated_entry(indicator="rsi", interval="1m", value="60.00 -Buy")
        macd_entry = _aggregated_entry(indicator="macd", interval="5m", value="1.00 -Sell")

        with _patched_table_render_state():
            forward = {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "entry_tf": "5m, 1m",
                "status": "Active",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "qty": 0.5,
                    "margin_usdt": 50.0,
                    "pnl_value": 0.0,
                },
                "_aggregated_entries": [copy.deepcopy(macd_entry), copy.deepcopy(rsi_entry)],
            }
            reverse = copy.deepcopy(forward)
            reverse["_aggregated_entries"] = [
                copy.deepcopy(rsi_entry),
                copy.deepcopy(macd_entry),
            ]

            first = _prepare_record_snapshot(
                _SnapshotWindow(),
                forward,
                view_mode="cumulative",
                live_value_cache={},
            )
            second = _prepare_record_snapshot(
                _SnapshotWindow(),
                reverse,
                view_mode="cumulative",
                live_value_cache={},
            )

        self.assertEqual(first, second)
        self.assertEqual(("rsi", "macd"), first[4])
        self.assertEqual(
            ("RSI@1M 60.00 -Buy", "MACD@5M 1.00 -Sell"),
            first[5],
        )
        self.assertEqual(
            (("rsi", ("1M",)), ("macd", ("5M",))),
            first[6],
        )


if __name__ == "__main__":
    unittest.main()
