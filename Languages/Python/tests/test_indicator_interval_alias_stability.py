from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.shared.indicator_value_core import (  # noqa: E402
    filter_indicator_entries_for_interval,
    format_interval_display_token,
    indicator_entry_signature,
    normalize_interval_token,
)
from app.gui.shared.indicator_value_collect_runtime import collect_indicator_value_strings  # noqa: E402
from app.gui.shared.indicator_value_desc_runtime import _fallback_trigger_entries_from_desc  # noqa: E402


def _canonicalize_indicator_key(value):
    return str(value or "").strip().lower() or None


def _normalize_indicator_values(values):
    if isinstance(values, str):
        values = [values]
    return [
        str(value).strip().lower()
        for value in (values or [])
        if str(value).strip()
    ]


def _resolve_trigger_indicators(raw, desc=None):
    normalized = _normalize_indicator_values(raw)
    if normalized:
        return normalized
    text = str(desc or "").lower()
    if "rsi" in text:
        return ["rsi"]
    return []


class IndicatorIntervalAliasStabilityTests(unittest.TestCase):
    def test_normalize_interval_token_collapses_equivalent_aliases(self):
        self.assertEqual("1m", normalize_interval_token("1m"))
        self.assertEqual("1h", normalize_interval_token("60"))
        self.assertEqual("1h", normalize_interval_token("60m"))
        self.assertEqual("1h", normalize_interval_token("1H"))
        self.assertEqual("1mo", normalize_interval_token("1M"))

    def test_format_interval_display_token_uses_canonical_ui_label(self):
        self.assertEqual("1H", format_interval_display_token("60"))
        self.assertEqual("1H", format_interval_display_token("60m"))
        self.assertEqual("1H", format_interval_display_token("1H"))
        self.assertEqual("1M", format_interval_display_token("1mo"))

    def test_indicator_entry_signature_uses_canonical_interval_identity(self):
        self.assertEqual(
            ("rsi", "1h"),
            indicator_entry_signature("RSI@60M 30.00 -Buy"),
        )
        self.assertEqual(
            ("rsi", "1h"),
            indicator_entry_signature("RSI@1H 31.00 -Sell"),
        )

    def test_filter_indicator_entries_for_interval_matches_equivalent_aliases(self):
        entries = [
            "RSI@60M 30.00 -Buy",
            "MACD@5M 1.00 -Sell",
        ]

        filtered = filter_indicator_entries_for_interval(
            entries,
            "1h",
            include_non_matching=False,
        )

        self.assertEqual(["RSI@60M 30.00 -Buy"], filtered)

    def test_collect_indicator_value_strings_uses_canonical_interval_display(self):
        record = {
            "status": "Active",
            "indicators": ["rsi"],
            "data": {
                "interval_display": "60m",
                "trigger_desc": "RSI = 30 -> BUY",
                "trigger_indicators": ["rsi"],
                "trigger_actions": {"rsi": "buy"},
            },
        }

        entries, interval_map = collect_indicator_value_strings(
            record,
            "1h",
            resolve_trigger_indicators=_resolve_trigger_indicators,
            normalize_indicator_values=_normalize_indicator_values,
            canonicalize_indicator_key=_canonicalize_indicator_key,
        )

        self.assertEqual(["RSI@1H 30.00 -Buy"], entries)
        self.assertEqual({"rsi": ["1H"]}, interval_map)

    def test_fallback_trigger_entries_use_canonical_interval_display(self):
        self.assertEqual(
            ["RSI@1H 30.00 -Buy"],
            _fallback_trigger_entries_from_desc(
                "RSI = 30 -> BUY",
                "60m",
                canonicalize_indicator_key=_canonicalize_indicator_key,
                allowed_indicators={"rsi"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
