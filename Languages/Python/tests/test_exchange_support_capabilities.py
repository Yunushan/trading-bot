from __future__ import annotations

import unittest

from app.integrations.exchanges.ccxt_diagnostics import CcxtDiagnosticsConnector
from app.service.schemas.status import build_exchange_connector_snapshot
from app.settings.exchange_support import CCXT_DIAGNOSTIC_EXCHANGES, build_exchange_support_payload


class _FakeCcxtExchange:
    def __init__(self) -> None:
        self.sandbox_enabled = False

    def set_sandbox_mode(self, enabled: bool) -> None:
        self.sandbox_enabled = bool(enabled)

    def load_markets(self) -> dict[str, object]:
        return {"BTC/USDT": {"symbol": "BTC/USDT"}}

    def fetch_ticker(self, symbol: str) -> dict[str, object]:
        return {"symbol": symbol, "last": 42000.5, "bid": 41999.0, "ask": 42001.0}

    def fetch_balance(self) -> dict[str, object]:
        return {
            "total": {"USDT": 12.5},
            "free": {"USDT": 10.0},
            "used": {"USDT": 2.5},
        }


class ExchangeSupportCapabilitiesTests(unittest.TestCase):
    def test_ccxt_diagnostic_venues_support_market_and_account_snapshots_not_orders(self):
        for exchange in CCXT_DIAGNOSTIC_EXCHANGES:
            with self.subTest(exchange=exchange):
                payload = build_exchange_support_payload(
                    config={"selected_exchange": exchange, "connector_backend": "ccxt"}
                )

                self.assertTrue(payload["exchange_supported"])
                self.assertTrue(payload["connector_backend_supported"])
                self.assertTrue(payload["market_data_supported"])
                self.assertTrue(payload["account_snapshot_supported"])
                self.assertFalse(payload["order_execution_supported"])
                self.assertFalse(payload["trading_supported"])
                self.assertEqual("ccxt-diagnostics", payload["support_tier"])
                self.assertTrue(payload["ccxt_exchange_id"])
                self.assertIn("venue-specific order adapter evidence", payload["unsupported_reasons"][0])

    def test_binance_keeps_full_trading_support(self):
        payload = build_exchange_support_payload(
            config={
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-derivatives-trading-usds-futures",
            }
        )

        self.assertTrue(payload["market_data_supported"])
        self.assertTrue(payload["account_snapshot_supported"])
        self.assertTrue(payload["order_execution_supported"])
        self.assertTrue(payload["trading_supported"])
        self.assertEqual("full-trading", payload["support_tier"])

    def test_service_snapshot_marks_ccxt_diagnostics_as_read_only_warning(self):
        snapshot = build_exchange_connector_snapshot(
            config={"selected_exchange": "Kraken", "connector_backend": "ccxt"},
            snapshot={"health": "ok", "state": "ready"},
            source="unit-test",
        )

        self.assertEqual("warning", snapshot["health"])
        self.assertEqual("read_only_connector", snapshot["state"])
        self.assertTrue(snapshot["support"]["market_data_supported"])
        self.assertTrue(snapshot["support"]["account_snapshot_supported"])
        self.assertFalse(snapshot["support"]["order_execution_supported"])
        self.assertIn("venue-specific order adapter evidence", snapshot["attention"][0])

    def test_ccxt_diagnostics_connector_uses_injected_exchange_without_leaking_secrets(self):
        created: list[tuple[str, dict[str, object], _FakeCcxtExchange]] = []

        def factory(exchange_id: str, options: dict[str, object]) -> _FakeCcxtExchange:
            exchange = _FakeCcxtExchange()
            created.append((exchange_id, options, exchange))
            return exchange

        connector = CcxtDiagnosticsConnector(
            selected_exchange="Kraken",
            api_key="real-key",
            api_secret="real-secret",
            password="real-password",
            mode="Demo/Testnet",
            exchange_factory=factory,
        )
        market = connector.fetch_market_snapshot("BTC/USDT")
        account = connector.fetch_account_snapshot()

        self.assertEqual("kraken", market["ccxt_exchange_id"])
        self.assertEqual(1, market["market_count"])
        self.assertEqual(42000.5, market["ticker"]["last"])
        self.assertEqual("USDT", account["balances"][0]["asset"])
        self.assertEqual(12.5, account["balances"][0]["total"])
        self.assertEqual("kraken", created[0][0])
        self.assertTrue(created[0][2].sandbox_enabled)
        self.assertNotIn("real-secret", repr(market))
        self.assertNotIn("real-password", repr(account))


if __name__ == "__main__":
    unittest.main()
