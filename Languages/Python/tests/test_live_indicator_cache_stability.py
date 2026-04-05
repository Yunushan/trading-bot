from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.shared.live_indicator_runtime import (  # noqa: E402
    collect_current_indicator_live_strings,
    sanitize_interval_hint,
)


class _ComboStub:
    def currentText(self) -> str:
        return ""


class _LiveIndicatorWindowStub:
    def __init__(self) -> None:
        self.config = {
            "indicator_use_live_values": True,
            "indicators": {
                "rsi": {
                    "buy_value": 30.0,
                    "sell_value": 70.0,
                }
            },
        }
        self.ind_source_combo = _ComboStub()


def _canonicalize_indicator_key(value) -> str:
    return str(value or "").strip().lower()


def _normalize_indicator_token(value) -> str:
    return str(value or "").strip().lower()


def _indicator_short_label(value) -> str:
    return str(value or "").strip().upper()


def _dedupe_indicator_entries(entries: list[str] | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        text = str(entry or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


class LiveIndicatorCacheStabilityTests(unittest.TestCase):
    def test_sanitize_interval_hint_canonicalizes_aliases_and_order(self):
        self.assertEqual("1h", sanitize_interval_hint("60m, 1h"))
        self.assertEqual("1h", sanitize_interval_hint("1h, 60"))
        self.assertEqual("1M", sanitize_interval_hint("1mo, 1M"))

    def test_collect_current_indicator_live_strings_dedupes_equivalent_interval_aliases(self):
        window = _LiveIndicatorWindowStub()
        cache: dict = {}
        refresh_requests: list[tuple[tuple[str, str], str, str, tuple[str, ...]]] = []

        def _queue_refresh(
            _window,
            _cache,
            cache_key,
            symbol,
            interval,
            indicator_keys,
            *_args,
        ) -> None:
            refresh_requests.append(
                (
                    cache_key,
                    str(symbol),
                    str(interval),
                    tuple(sorted(str(key) for key in indicator_keys)),
                )
            )

        entries = collect_current_indicator_live_strings(
            window,
            "BTCUSDT",
            ["rsi"],
            cache,
            interval_map={"rsi": ["60m", "1h", "60"]},
            default_interval_hint="1h",
            sanitize_interval_hint=sanitize_interval_hint,
            canonicalize_indicator_key=_canonicalize_indicator_key,
            normalize_indicator_token=_normalize_indicator_token,
            indicator_short_label=_indicator_short_label,
            dedupe_indicator_entries_normalized=_dedupe_indicator_entries,
            queue_live_indicator_refresh=_queue_refresh,
        )

        self.assertEqual(["RSI@1H --"], entries)
        self.assertEqual(1, len(refresh_requests))
        self.assertEqual((("BTCUSDT", "1h"), "BTCUSDT", "1h", ("rsi",)), refresh_requests[0])
        self.assertEqual({("BTCUSDT", "1h")}, set(cache))

    def test_collect_current_indicator_live_strings_reuses_cached_equivalent_default_interval(self):
        window = _LiveIndicatorWindowStub()
        cache = {
            ("BTCUSDT", "1h"): {
                "df": object(),
                "values": {"rsi": 32.0},
                "error": False,
                "df_ts": time.monotonic(),
                "error_ts": 0.0,
                "use_live_values": True,
            }
        }
        refresh_requests: list[tuple[tuple[str, str], str]] = []

        def _queue_refresh(
            _window,
            _cache,
            cache_key,
            _symbol,
            interval,
            *_args,
        ) -> None:
            refresh_requests.append((cache_key, str(interval)))

        entries = collect_current_indicator_live_strings(
            window,
            "BTCUSDT",
            ["rsi"],
            cache,
            interval_map=None,
            default_interval_hint="60",
            sanitize_interval_hint=sanitize_interval_hint,
            canonicalize_indicator_key=_canonicalize_indicator_key,
            normalize_indicator_token=_normalize_indicator_token,
            indicator_short_label=_indicator_short_label,
            dedupe_indicator_entries_normalized=_dedupe_indicator_entries,
            queue_live_indicator_refresh=_queue_refresh,
        )

        self.assertEqual(["RSI@1H 32.00"], entries)
        self.assertEqual([], refresh_requests)
        self.assertEqual({("BTCUSDT", "1h")}, set(cache))


if __name__ == "__main__":
    unittest.main()
