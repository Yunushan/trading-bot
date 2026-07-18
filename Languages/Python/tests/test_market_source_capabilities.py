from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.market.market_data import (  # noqa: E402
    _require_supported_live_kline_source,
    get_klines,
)
from app.native_parity import INDICATOR_SOURCE_OPTIONS  # noqa: E402


class _UnsupportedSourceWrapper:
    indicator_source = "Coinbase"


class MarketSourceCapabilitiesTests(unittest.TestCase):
    def test_indicator_source_catalog_only_lists_implemented_live_sources(self):
        self.assertEqual(
            INDICATOR_SOURCE_OPTIONS,
            ("Binance spot", "Binance futures", "Bybit"),
        )

    def test_unsupported_live_source_is_rejected_before_any_client_fallback(self):
        with self.assertRaisesRegex(NotImplementedError, "coinbase"):
            get_klines(_UnsupportedSourceWrapper(), "BTCUSDT", "1h")

    def test_supported_sources_are_accepted_by_transport_guard(self):
        for source in ("", "binance futures", "binance spot", "bybit"):
            _require_supported_live_kline_source(source)


if __name__ == "__main__":
    unittest.main()
