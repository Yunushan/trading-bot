from __future__ import annotations

import unittest

from app.integrations.brokers import FxcmBrokerConnector, IgBrokerConnector, OandaBrokerConnector
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

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None,
        params: dict[str, object],
    ) -> dict[str, object]:
        return {
            "id": "fake-order-1",
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "open",
            "clientOrderId": params.get("clientOrderId"),
        }


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeOandaSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, object]] = []
        self.gets: list[dict[str, object]] = []

    def get(self, url: str, **kwargs) -> _FakeResponse:
        self.gets.append({"url": url, **kwargs})
        if url.endswith("/summary"):
            return _FakeResponse({"account": {"id": "001", "balance": "1000.00"}})
        return _FakeResponse({"prices": [{"instrument": "EUR_USD", "closeoutBid": "1.1"}]})

    def post(self, url: str, **kwargs) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return _FakeResponse(
            {
                "orderCreateTransaction": {"id": "10", "instrument": "EUR_USD"},
                "orderFillTransaction": {"id": "11", "units": "100"},
                "lastTransactionID": "11",
            },
            status_code=201,
        )


class _FakeFxcmClient:
    def __init__(self) -> None:
        self.orders: list[tuple[str, object]] = []

    def get_accounts(self) -> dict[str, object]:
        return {"accountId": "fxcm-1", "balance": 1000}

    def get_offers(self) -> dict[str, object]:
        return {"EUR/USD": {"bid": 1.1, "ask": 1.2}}

    def create_market_buy_order(self, symbol: str, amount: object) -> dict[str, object]:
        self.orders.append((symbol, amount))
        return {"tradeId": "fxcm-order-1", "currency": symbol, "amountK": amount, "isBuy": True}


class _FakeIgSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, object]] = []
        self.gets: list[dict[str, object]] = []

    def get(self, url: str, **kwargs) -> _FakeResponse:
        self.gets.append({"url": url, **kwargs})
        if url.endswith("/accounts"):
            return _FakeResponse({"accounts": [{"accountId": "ig-1", "balance": {"balance": 1000}}]})
        return _FakeResponse({"instrument": {"epic": "CS.D.EURUSD.CFD.IP"}})

    def post(self, url: str, **kwargs) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return _FakeResponse({"dealReference": "ig-ref-1"}, status_code=200)


class ExchangeSupportCapabilitiesTests(unittest.TestCase):
    def test_ccxt_venues_support_market_account_and_order_routing_with_evidence_required(self):
        for exchange in CCXT_DIAGNOSTIC_EXCHANGES:
            with self.subTest(exchange=exchange):
                payload = build_exchange_support_payload(
                    config={"selected_exchange": exchange, "connector_backend": "ccxt"}
                )

                self.assertTrue(payload["exchange_supported"])
                self.assertTrue(payload["connector_backend_supported"])
                self.assertTrue(payload["market_data_supported"])
                self.assertTrue(payload["account_snapshot_supported"])
                self.assertTrue(payload["order_routing_supported"])
                self.assertTrue(payload["order_execution_supported"])
                self.assertTrue(payload["trading_supported"])
                self.assertTrue(payload["live_evidence_required"])
                self.assertEqual("order-routing-evidence-required", payload["support_tier"])
                self.assertTrue(payload["ccxt_exchange_id"])
                self.assertEqual([], payload["unsupported_reasons"])
                self.assertIn("requires a passed connector evidence artifact", payload["capability_gaps"][0])

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

    def test_service_snapshot_marks_ccxt_order_routing_as_evidence_required_warning(self):
        snapshot = build_exchange_connector_snapshot(
            config={"selected_exchange": "Kraken", "connector_backend": "ccxt"},
            snapshot={"health": "ok", "state": "ready"},
            source="unit-test",
        )

        self.assertEqual("warning", snapshot["health"])
        self.assertEqual("connector_evidence_required", snapshot["state"])
        self.assertTrue(snapshot["support"]["market_data_supported"])
        self.assertTrue(snapshot["support"]["account_snapshot_supported"])
        self.assertTrue(snapshot["support"]["order_execution_supported"])
        self.assertIn("requires a passed connector evidence artifact", snapshot["support"]["capability_gaps"][0])

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

    def test_ccxt_order_routing_supports_dry_run_and_guarded_live_submit(self):
        created: list[tuple[str, dict[str, object], _FakeCcxtExchange]] = []

        def factory(exchange_id: str, options: dict[str, object]) -> _FakeCcxtExchange:
            exchange = _FakeCcxtExchange()
            created.append((exchange_id, options, exchange))
            return exchange

        connector = CcxtDiagnosticsConnector(
            selected_exchange="OKX",
            api_key="real-key",
            api_secret="real-secret",
            mode="Demo/Testnet",
            exchange_factory=factory,
        )
        dry_run = connector.submit_order(
            symbol="BTC/USDT",
            side="buy",
            amount=0.01,
            client_order_id="client-1",
        )
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual("BTC/USDT", dry_run["request"]["symbol"])
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_order(symbol="BTC/USDT", side="buy", amount=0.01, dry_run=False)
        submitted = connector.submit_order(
            symbol="BTC/USDT",
            side="sell",
            amount=0.02,
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("fake-order-1", submitted["order"]["id"])
        self.assertEqual("okx", created[-1][0])
        self.assertTrue(created[-1][2].sandbox_enabled)

    def test_supported_brokers_require_provider_backend_for_order_routing(self):
        cases = (
            ("OANDA", "oanda-rest"),
            ("FXCM", "fxcmpy"),
            ("IG", "ig-rest"),
        )
        for broker, backend in cases:
            with self.subTest(broker=broker):
                payload = build_exchange_support_payload(
                    config={
                        "selected_exchange": "",
                        "connector_backend": backend,
                        "selected_forex_broker": broker,
                    }
                )
                self.assertTrue(payload["broker_supported"])
                self.assertTrue(payload["order_routing_supported"])
                self.assertTrue(payload["order_execution_supported"])
                self.assertTrue(payload["live_evidence_required"])
                self.assertEqual("order-routing-evidence-required", payload["support_tier"])

                wrong_backend = build_exchange_support_payload(
                    config={
                        "selected_exchange": "",
                        "connector_backend": "ccxt",
                        "selected_forex_broker": broker,
                    }
                )
                self.assertTrue(wrong_backend["broker_supported"])
                self.assertFalse(wrong_backend["order_routing_supported"])
                self.assertIn("requires connector backend", wrong_backend["capability_gaps"][0])

    def test_oanda_order_routing_is_guarded(self):
        session = _FakeOandaSession()
        connector = OandaBrokerConnector(
            account_id="001",
            token="real-token",
            session=session,
        )
        account = connector.fetch_account_snapshot()
        self.assertEqual("001", account["account"]["id"])
        prices = connector.fetch_pricing_snapshot(["EUR/USD"])
        self.assertEqual("EUR_USD", prices["prices"][0]["instrument"])
        dry_run = connector.submit_market_order(instrument="EUR/USD", side="buy", units=100)
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual("EUR_USD", dry_run["request"]["order"]["instrument"])
        self.assertEqual("100", dry_run["request"]["order"]["units"])
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_market_order(instrument="EUR/USD", side="buy", units=100, dry_run=False)
        submitted = connector.submit_market_order(
            instrument="EUR/USD",
            side="sell",
            units=100,
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("-100", submitted["request"]["order"]["units"])
        self.assertEqual("11", submitted["order"]["lastTransactionID"])
        self.assertEqual("/v3/accounts/001/orders", session.posts[0]["url"][-23:])
        self.assertNotIn("real-token", repr(submitted))

    def test_fxcm_order_routing_is_guarded(self):
        client = _FakeFxcmClient()
        connector = FxcmBrokerConnector(access_token="real-token", client=client)

        account = connector.fetch_account_snapshot()
        self.assertEqual("fxcm-1", account["accounts"]["accountId"])
        market = connector.fetch_market_snapshot("EUR/USD")
        self.assertEqual(1.1, market["market"]["EUR/USD"]["bid"])
        dry_run = connector.submit_market_order(symbol="EUR/USD", side="buy", amount=100)
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual("create_market_buy_order", dry_run["request"]["method"])
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_market_order(symbol="EUR/USD", side="buy", amount=100, dry_run=False)
        submitted = connector.submit_market_order(
            symbol="EUR/USD",
            side="buy",
            amount=100,
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("fxcm-order-1", submitted["order"]["tradeId"])
        self.assertEqual([("EUR/USD", 100)], client.orders)
        self.assertNotIn("real-token", repr(submitted))

    def test_ig_order_routing_is_guarded(self):
        session = _FakeIgSession()
        connector = IgBrokerConnector(
            api_key="real-api-key",
            cst="real-cst",
            security_token="real-security-token",
            account_id="ig-1",
            session=session,
        )

        account = connector.fetch_account_snapshot()
        self.assertEqual("ig-1", account["accounts"][0]["accountId"])
        market = connector.fetch_market_snapshot("CS.D.EURUSD.CFD.IP")
        self.assertEqual("CS.D.EURUSD.CFD.IP", market["market"]["instrument"]["epic"])
        dry_run = connector.submit_market_order(
            epic="CS.D.EURUSD.CFD.IP",
            direction="buy",
            size=1.5,
            deal_reference="client-ig-1",
        )
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual("MARKET", dry_run["request"]["orderType"])
        self.assertEqual("BUY", dry_run["request"]["direction"])
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_market_order(
                epic="CS.D.EURUSD.CFD.IP",
                direction="sell",
                size=1,
                dry_run=False,
            )
        submitted = connector.submit_market_order(
            epic="CS.D.EURUSD.CFD.IP",
            direction="sell",
            size=1,
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("ig-ref-1", submitted["order"]["dealReference"])
        self.assertEqual("/positions/otc", session.posts[0]["url"][-14:])
        self.assertNotIn("real-security-token", repr(submitted))


if __name__ == "__main__":
    unittest.main()
