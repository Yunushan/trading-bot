from __future__ import annotations

import json
import threading
import time
import unittest
from urllib.parse import parse_qs

import requests

from app.integrations.brokers import (
    AvaTradeBrokerConnector,
    CiticFuturesCtpConnector,
    EcMarketsBrokerConnector,
    FinaltoBrokerConnector,
    FxcmBrokerConnector,
    GtcFxBrokerConnector,
    IgBrokerConnector,
    MT4_BRIDGE_PROVIDERS,
    MT4_BRIDGE_TOKEN_HEADER,
    MT5_BROKER_PROVIDERS,
    MetaTrader4BridgeConnector,
    MetaTrader4BridgeServer,
    MetaTrader4BridgeState,
    MetaTrader5BrokerConnector,
    MoomooOpenDConnector,
    OandaBrokerConnector,
    Trading212BrokerConnector,
)
from app.integrations.exchanges.ccxt_diagnostics import CcxtDiagnosticsConnector
from app.service.schemas.status import build_exchange_connector_snapshot
from app.settings.exchange_support import (
    CCXT_DIAGNOSTIC_EXCHANGES,
    SUPPORTED_BROKERS,
    SUPPORTED_FOREX_BROKERS,
    build_exchange_support_payload,
)


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
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


class _FakeHttpSession:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.calls: list[dict[str, object]] = []

    def _call(self, method: str, url: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(self.payload, status_code=self.status_code)

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        return self._call("GET", url, **kwargs)

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        return self._call("POST", url, **kwargs)

    def delete(self, url: str, **kwargs: object) -> _FakeResponse:
        return self._call("DELETE", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: object) -> _FakeResponse:
        return self._call(method.upper(), url, **kwargs)


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


class _FakeTrading212Session:
    def __init__(self) -> None:
        self.posts: list[dict[str, object]] = []
        self.gets: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.gets.append({"url": url, **kwargs})
        if url.endswith("/equity/account/summary"):
            return _FakeResponse({"id": 212, "currency": "GBP", "cash": {"availableToTrade": 1000}})
        if url.endswith("/equity/metadata/instruments"):
            return _FakeResponse([{"ticker": "AAPL_US_EQ", "name": "Apple"}])
        if url.endswith("/equity/metadata/exchanges"):
            return _FakeResponse([{"id": 1, "name": "NASDAQ"}])
        if url.endswith("/equity/positions"):
            return _FakeResponse([{"ticker": "AAPL_US_EQ", "quantity": 1.5}])
        if url.endswith("/equity/orders"):
            return _FakeResponse([{"id": 41, "ticker": "AAPL_US_EQ", "status": "NEW"}])
        if url.endswith("/equity/orders/41"):
            return _FakeResponse({"id": 41, "ticker": "AAPL_US_EQ", "status": "NEW"})
        raise AssertionError(f"Unexpected Trading 212 GET: {url}")

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        request = dict(kwargs.get("json") or {})
        return _FakeResponse(
            {
                "id": 42,
                "ticker": request.get("ticker"),
                "quantity": request.get("quantity"),
                "status": "NEW",
            }
        )

    def delete(self, url: str, **kwargs: object) -> _FakeResponse:
        self.deletes.append({"url": url, **kwargs})
        return _FakeResponse({})


class _FakeMoomooEnum:
    US = "US"
    SIMULATE = "SIMULATE"
    REAL = "REAL"
    BUY = "BUY"
    SELL = "SELL"
    NORMAL = "NORMAL"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    TRAILING_STOP_LIMIT = "TRAILING_STOP_LIMIT"
    DAY = "DAY"
    GTC = "GTC"
    NONE = "NONE"
    ALL = "ALL"
    PRICE = "PRICE"
    PERCENTAGE = "PERCENTAGE"
    CANCEL = "CANCEL"
    FUTUINC = "FUTUINC"


class _FakeMoomooSdk:
    RET_OK = 0
    TrdMarket = _FakeMoomooEnum
    TrdEnv = _FakeMoomooEnum
    TrdSide = _FakeMoomooEnum
    OrderType = _FakeMoomooEnum
    TimeInForce = _FakeMoomooEnum
    Session = _FakeMoomooEnum
    TrailType = _FakeMoomooEnum
    ModifyOrderOp = _FakeMoomooEnum
    SecurityFirm = _FakeMoomooEnum


class _FakeMoomooTradeContext:
    def __init__(self) -> None:
        self.unlocks: list[str] = []
        self.placed: list[dict[str, object]] = []
        self.modified: list[dict[str, object]] = []
        self.closed = False

    def get_acc_list(self) -> tuple[int, object]:
        return (0, [{"acc_id": 7001, "trd_env": "SIMULATE"}])

    def accinfo_query(self, **kwargs: object) -> tuple[int, object]:
        return (0, [{"acc_id": kwargs["acc_id"], "total_assets": 1000.0}])

    def position_list_query(self, **kwargs: object) -> tuple[int, object]:
        return (0, [{"code": "US.AAPL", "qty": 2.0, "acc_id": kwargs["acc_id"]}])

    def order_list_query(self, **kwargs: object) -> tuple[int, object]:
        return (0, [{"order_id": "m-41", "refresh_cache": kwargs["refresh_cache"]}])

    def unlock_trade(self, password: str) -> tuple[int, object]:
        self.unlocks.append(password)
        return (0, {"unlocked": True})

    def place_order(self, **kwargs: object) -> tuple[int, object]:
        self.placed.append(dict(kwargs))
        return (0, [{"order_id": "m-42", "code": kwargs["code"], "qty": kwargs["qty"]}])

    def modify_order(self, **kwargs: object) -> tuple[int, object]:
        self.modified.append(dict(kwargs))
        return (0, [{"order_id": kwargs["order_id"]}])

    def close(self) -> None:
        self.closed = True


class _FakeMoomooQuoteContext:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.closed = False

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        self.calls.append(list(codes))
        return (0, [{"code": code, "last_price": 200.0} for code in codes])

    def close(self) -> None:
        self.closed = True


class _FakeMt5Value:
    def __init__(self, **values: object) -> None:
        self._values = values
        for key, value in values.items():
            setattr(self, key, value)

    def _asdict(self) -> dict[str, object]:
        return dict(self._values)


class _FakeMt5Client:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self, *, initialize_result: bool = True, check_retcode: int = 0) -> None:
        self.initialize_result = initialize_result
        self.check_retcode = check_retcode
        self.initialize_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.selected_symbols: list[str] = []
        self.checked_requests: list[dict[str, object]] = []
        self.sent_requests: list[dict[str, object]] = []
        self.shutdown_calls = 0

    def initialize(self, *args: object, **kwargs: object) -> bool:
        self.initialize_calls.append((args, kwargs))
        return self.initialize_result

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        return True

    def last_error(self) -> tuple[int, str]:
        return (1, "password=terminal-secret")

    def terminal_info(self) -> _FakeMt5Value:
        return _FakeMt5Value(connected=True, trade_allowed=True)

    def version(self) -> tuple[int, int, str]:
        return (500, 5735, "04 Apr 2026")

    def account_info(self) -> _FakeMt5Value:
        return _FakeMt5Value(login=123456, balance=1000.0, trade_allowed=True)

    def symbol_info(self, symbol: str) -> _FakeMt5Value:
        return _FakeMt5Value(
            name=symbol,
            visible=symbol in self.selected_symbols,
            filling_mode=self.SYMBOL_FILLING_FOK | self.SYMBOL_FILLING_IOC,
        )

    def symbol_select(self, symbol: str, enabled: bool) -> bool:
        if enabled:
            self.selected_symbols.append(symbol)
        return enabled

    def symbol_info_tick(self, symbol: str) -> _FakeMt5Value:
        return _FakeMt5Value(symbol=symbol, bid=1.1001, ask=1.1003)

    def positions_get(self, **kwargs: object) -> tuple[_FakeMt5Value, ...]:
        return (_FakeMt5Value(ticket=101, symbol=kwargs.get("symbol", "EURUSD"), volume=0.1),)

    def orders_get(self, **kwargs: object) -> tuple[_FakeMt5Value, ...]:
        return (_FakeMt5Value(ticket=201, symbol=kwargs.get("symbol", "EURUSD"), volume_current=0.1),)

    def order_check(self, request: dict[str, object]) -> _FakeMt5Value:
        self.checked_requests.append(dict(request))
        return _FakeMt5Value(retcode=self.check_retcode, comment="Done", request=_FakeMt5Value(**request))

    def order_send(self, request: dict[str, object]) -> _FakeMt5Value:
        self.sent_requests.append(dict(request))
        return _FakeMt5Value(retcode=self.TRADE_RETCODE_DONE, order=301, deal=302, request=_FakeMt5Value(**request))


class _FakeCtpField:
    def __init__(self, **values: object) -> None:
        for key, value in values.items():
            setattr(self, key, value)


class _FakeCtpSpi:
    pass


class _FakeCtpApi:
    instances: list[_FakeCtpApi] = []

    def __init__(self) -> None:
        self.spi: object | None = None
        self.front = ""
        self.auth_requests: list[object] = []
        self.login_requests: list[object] = []
        self.order_requests: list[object] = []
        self.cancel_requests: list[object] = []
        self.released = False
        self.__class__.instances.append(self)

    @classmethod
    def CreateFtdcTraderApi(cls, flow_path: str = "") -> _FakeCtpApi:
        return cls()

    def RegisterSpi(self, spi: object | None) -> None:
        self.spi = spi

    def SubscribePrivateTopic(self, topic: object) -> None:
        return None

    def SubscribePublicTopic(self, topic: object) -> None:
        return None

    def RegisterFront(self, front: str) -> None:
        self.front = front

    def Init(self) -> None:
        self.spi.OnFrontConnected()

    def ReqAuthenticate(self, request: object, request_id: int) -> int:
        self.auth_requests.append(request)
        self.spi.OnRspAuthenticate(_FakeCtpField(), _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqUserLogin(self, request: object, request_id: int) -> int:
        self.login_requests.append(request)
        response = _FakeCtpField(FrontID=7, SessionID=9, MaxOrderRef="40")
        self.spi.OnRspUserLogin(response, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqSettlementInfoConfirm(self, request: object, request_id: int) -> int:
        self.spi.OnRspSettlementInfoConfirm(
            _FakeCtpField(BrokerID=request.BrokerID, InvestorID=request.InvestorID),
            _FakeCtpField(ErrorID=0, ErrorMsg=""),
            request_id,
            True,
        )
        return 0

    def ReqQryTradingAccount(self, request: object, request_id: int) -> int:
        value = _FakeCtpField(AccountID="ctp-account", Balance=1200.5, Available=900.0, CurrencyID="CNY")
        self.spi.OnRspQryTradingAccount(value, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqQryInvestorPosition(self, request: object, request_id: int) -> int:
        value = _FakeCtpField(ExchangeID="SHFE", InstrumentID=request.InstrumentID or "au2612", Position=2)
        self.spi.OnRspQryInvestorPosition(value, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqQryOrder(self, request: object, request_id: int) -> int:
        value = _FakeCtpField(ExchangeID="SHFE", InstrumentID=request.InstrumentID or "au2612", OrderRef="39")
        self.spi.OnRspQryOrder(value, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqQryDepthMarketData(self, request: object, request_id: int) -> int:
        value = _FakeCtpField(
            ExchangeID=request.ExchangeID,
            InstrumentID=request.InstrumentID,
            LastPrice=501.2,
            BidPrice1=501.0,
            AskPrice1=501.4,
        )
        self.spi.OnRspQryDepthMarketData(value, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqQryInstrument(self, request: object, request_id: int) -> int:
        value = _FakeCtpField(
            ExchangeID=request.ExchangeID or "SHFE",
            InstrumentID=request.InstrumentID or "au2612",
            ProductID=request.ProductID or "au",
            PriceTick=0.02,
        )
        self.spi.OnRspQryInstrument(value, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def ReqOrderInsert(self, request: object, request_id: int) -> int:
        self.order_requests.append(request)
        values = dict(vars(request))
        values.update(OrderStatus="3", OrderSubmitStatus="0", OrderSysID="sys-41")
        self.spi.OnRtnOrder(_FakeCtpField(**values))
        return 0

    def ReqOrderAction(self, request: object, request_id: int) -> int:
        self.cancel_requests.append(request)
        self.spi.OnRspOrderAction(request, _FakeCtpField(ErrorID=0, ErrorMsg=""), request_id, True)
        return 0

    def Release(self) -> None:
        self.released = True


class _FakeCtpSdk:
    CThostFtdcTraderSpi = _FakeCtpSpi
    CThostFtdcTraderApi = _FakeCtpApi
    THOST_TERT_QUICK = 2
    THOST_FTDC_D_Buy = "0"
    THOST_FTDC_D_Sell = "1"
    THOST_FTDC_OF_Open = "0"
    THOST_FTDC_OF_Close = "1"
    THOST_FTDC_OF_CloseToday = "3"
    THOST_FTDC_OF_CloseYesterday = "4"
    THOST_FTDC_HF_Speculation = "1"
    THOST_FTDC_OPT_AnyPrice = "1"
    THOST_FTDC_OPT_LimitPrice = "2"
    THOST_FTDC_TC_IOC = "1"
    THOST_FTDC_TC_GFD = "3"
    THOST_FTDC_VC_AV = "1"
    THOST_FTDC_FCC_NotForceClose = "0"
    THOST_FTDC_CC_Immediately = "1"
    THOST_FTDC_AF_Delete = "0"


for _ctp_field_name in (
    "CThostFtdcReqAuthenticateField",
    "CThostFtdcReqUserLoginField",
    "CThostFtdcSettlementInfoConfirmField",
    "CThostFtdcQryTradingAccountField",
    "CThostFtdcQryInvestorPositionField",
    "CThostFtdcQryOrderField",
    "CThostFtdcQryDepthMarketDataField",
    "CThostFtdcQryInstrumentField",
    "CThostFtdcInputOrderField",
    "CThostFtdcInputOrderActionField",
):
    setattr(_FakeCtpSdk, _ctp_field_name, _FakeCtpField)


def _run_fake_mt4_agent(
    *,
    base_url: str,
    token: str,
    terminal_id: str,
    expected_commands: int,
    seen: list[dict[str, str]],
    errors: list[BaseException],
) -> None:
    session = requests.Session()
    headers = {MT4_BRIDGE_TOKEN_HEADER: token}
    deadline = time.monotonic() + 10.0
    try:
        while len(seen) < expected_commands and time.monotonic() < deadline:
            response = session.get(
                f"{base_url}/v1/agents/{terminal_id}/next",
                headers=headers,
                timeout=2.0,
            )
            if response.status_code == 204:
                time.sleep(0.01)
                continue
            response.raise_for_status()
            command = {key: values[0] for key, values in parse_qs(response.text).items()}
            seen.append(command)
            operation = command["operation"]
            if operation == "account_snapshot":
                result: object = {"account_number": 123456, "balance": 1_000.0}
            elif operation == "market_snapshot":
                result = {"symbol": command["symbol"], "bid": 1.1, "ask": 1.1002}
            elif operation == "open_positions_snapshot":
                result = {"positions": [], "count": 0}
            elif operation == "open_orders_snapshot":
                result = {"orders": [], "count": 0}
            elif operation == "market_order":
                result = {"ticket": 7001, "symbol": command["symbol"]}
            elif operation == "cancel_order":
                result = {"ticket": int(command["ticket"]), "cancelled": True}
            elif operation == "close_position":
                result = {"ticket": int(command["ticket"]), "closed": True}
            else:
                raise AssertionError(f"unexpected MT4 operation: {operation}")
            completed = session.post(
                f"{base_url}/v1/agents/{terminal_id}/results",
                headers=headers,
                data={
                    "command_id": command["command_id"],
                    "status": "completed",
                    "error_code": "0",
                    "error_message": "",
                    "payload_json": json.dumps(result),
                },
                timeout=2.0,
            )
            completed.raise_for_status()
        if len(seen) != expected_commands:
            raise AssertionError(f"fake MT4 agent handled {len(seen)} of {expected_commands} expected commands")
    except BaseException as exc:
        errors.append(exc)


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

    def test_service_snapshot_blocks_unresolved_exchange_order_intents(self):
        snapshot = build_exchange_connector_snapshot(
            config={"selected_exchange": "Binance", "connector_backend": "sdk"},
            snapshot={
                "health": "ok",
                "state": "ready",
                "order_intents": {"unresolved_count": 1, "unresolved_client_order_ids": ["tb-safe-id"]},
            },
            source="unit-test",
        )

        self.assertEqual("error", snapshot["health"])
        self.assertEqual("order_intent_reconciliation_required", snapshot["state"])
        self.assertIn("1 unresolved exchange order intent(s) require reconciliation.", snapshot["attention"])
        self.assertEqual(1, snapshot["order_intents"]["unresolved_count"])

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

    def test_order_connectors_reject_boolean_and_non_finite_numeric_inputs(self):
        cases = (
            (
                "ccxt",
                CcxtDiagnosticsConnector(selected_exchange="OKX").submit_order,
                {"symbol": "BTC/USDT", "side": "buy"},
                "amount",
            ),
            (
                "oanda",
                OandaBrokerConnector(account_id="test-account").submit_market_order,
                {"instrument": "EUR_USD", "side": "buy"},
                "units",
            ),
            (
                "fxcm",
                FxcmBrokerConnector().submit_market_order,
                {"symbol": "EUR/USD", "side": "buy"},
                "amount",
            ),
            (
                "ig",
                IgBrokerConnector().submit_market_order,
                {"epic": "CS.D.EURUSD.CFD.IP", "direction": "BUY"},
                "size",
            ),
            (
                "trading212",
                Trading212BrokerConnector().submit_market_order,
                {"ticker": "AAPL_US_EQ", "side": "buy"},
                "quantity",
            ),
            (
                "moomoo",
                MoomooOpenDConnector().submit_order,
                {"code": "US.AAPL", "side": "buy", "order_type": "MARKET"},
                "quantity",
            ),
        )
        invalid_values = (True, float("nan"), float("inf"), float("-inf"))

        for connector_name, submit, request, numeric_field in cases:
            for invalid_value in invalid_values:
                with self.subTest(connector=connector_name, field=numeric_field, value=invalid_value):
                    with self.assertRaisesRegex(ValueError, "positive number"):
                        submit(**request, **{numeric_field: invalid_value})

        moomoo = MoomooOpenDConnector()
        for invalid_price in invalid_values:
            with self.subTest(connector="moomoo", field="price", value=invalid_price):
                with self.assertRaisesRegex(ValueError, "non-negative number"):
                    moomoo.submit_order(
                        code="US.AAPL",
                        side="buy",
                        quantity=1,
                        order_type="NORMAL",
                        price=invalid_price,
                    )

    def test_extra_order_fields_cannot_override_validated_order_inputs(self):
        cases = (
            (
                "oanda",
                OandaBrokerConnector(account_id="test-account").submit_market_order,
                {"instrument": "EUR_USD", "side": "buy", "units": 1},
                {"units": "NaN"},
            ),
            (
                "ig",
                IgBrokerConnector().submit_market_order,
                {"epic": "CS.D.EURUSD.CFD.IP", "direction": "BUY", "size": 1},
                {"direction": "SELL"},
            ),
            (
                "trading212",
                Trading212BrokerConnector().submit_market_order,
                {"ticker": "AAPL_US_EQ", "side": "buy", "quantity": 1},
                {"quantity": float("inf")},
            ),
            (
                "moomoo",
                MoomooOpenDConnector().submit_order,
                {"code": "US.AAPL", "side": "buy", "quantity": 1, "order_type": "MARKET"},
                {"trd_env": "REAL"},
            ),
        )

        for connector_name, submit, request, extra_fields in cases:
            with self.subTest(connector=connector_name):
                with self.assertRaisesRegex(ValueError, "must not override validated fields"):
                    submit(**request, extra_order_fields=extra_fields)

        additive = Trading212BrokerConnector().submit_market_order(
            ticker="AAPL_US_EQ",
            side="buy",
            quantity=1,
            extra_order_fields={"clientRequestId": "client-safe-1"},
        )
        self.assertEqual("client-safe-1", additive["request"]["clientRequestId"])

    def test_rest_broker_urls_require_secure_remote_transport(self):
        constructors = (
            (
                "oanda",
                lambda url, allow: OandaBrokerConnector(
                    account_id="test-account",
                    base_url=url,
                    allow_insecure_remote=allow,
                ),
            ),
            (
                "ig",
                lambda url, allow: IgBrokerConnector(
                    base_url=url,
                    allow_insecure_remote=allow,
                ),
            ),
            (
                "trading212",
                lambda url, allow: Trading212BrokerConnector(
                    base_url=url,
                    allow_insecure_remote=allow,
                ),
            ),
        )

        for connector_name, constructor in constructors:
            with self.subTest(connector=connector_name, case="remote-http"):
                with self.assertRaisesRegex(ValueError, "must use HTTPS"):
                    constructor("http://broker.example/api", False)
            with self.subTest(connector=connector_name, case="embedded-credentials"):
                with self.assertRaisesRegex(ValueError, "must not contain credentials"):
                    constructor("https://user:secret@broker.example/api", False)
            with self.subTest(connector=connector_name, case="query"):
                with self.assertRaisesRegex(ValueError, "query string or fragment"):
                    constructor("https://broker.example/api?token=secret", False)
            with self.subTest(connector=connector_name, case="invalid-scheme"):
                with self.assertRaisesRegex(ValueError, r"absolute HTTP\(S\) URL"):
                    constructor("ftp://broker.example/api", False)

            loopback = constructor("http://127.0.0.1:8080/api", False)
            self.assertEqual("http://127.0.0.1:8080/api", loopback.base_url)
            explicit_insecure = constructor("http://broker.example/api", True)
            self.assertTrue(explicit_insecure.build_capability_snapshot()["insecure_remote_transport_allowed"])

    def test_rest_broker_path_identifiers_are_encoded_as_single_segments(self):
        oanda_session = _FakeOandaSession()
        oanda = OandaBrokerConnector(
            account_id="account/../../orders",
            token="token",
            session=oanda_session,
        )
        oanda.fetch_account_snapshot()
        self.assertIn("/account%2F..%2F..%2Forders/summary", oanda_session.gets[0]["url"])

        ig_session = _FakeIgSession()
        ig = IgBrokerConnector(
            api_key="api-key",
            cst="cst",
            security_token="security-token",
            session=ig_session,
        )
        ig.fetch_market_snapshot("CS.D.EUR/USD?source=test")
        self.assertIn("/CS.D.EUR%2FUSD%3Fsource%3Dtest", ig_session.gets[0]["url"])

    def test_sensitive_broker_requests_fail_closed_on_redirects(self):
        cases = (
            (
                "oanda",
                lambda session: OandaBrokerConnector(
                    account_id="test-account",
                    token="token",
                    session=session,
                ).fetch_account_snapshot(),
            ),
            (
                "ig",
                lambda session: IgBrokerConnector(
                    api_key="api-key",
                    cst="cst",
                    security_token="security-token",
                    session=session,
                ).fetch_account_snapshot(),
            ),
            (
                "trading212",
                lambda session: Trading212BrokerConnector(
                    api_key="api-key",
                    api_secret="api-secret",
                    session=session,
                ).fetch_account_snapshot(),
            ),
        )

        for connector_name, request in cases:
            session = _FakeHttpSession({"redirect": "rejected"}, status_code=302)
            with self.subTest(connector=connector_name):
                with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                    request(session)
                self.assertIs(False, session.calls[0]["allow_redirects"])

        mt4_session = _FakeHttpSession({"status": "ok"})
        mt4 = MetaTrader4BridgeConnector(
            provider="Trade Nation",
            terminal_id="redirect-contract",
            token="redirect-test-token-123",
            bridge_url="https://bridge.example",
            session=mt4_session,
        )
        mt4.fetch_bridge_snapshot()
        self.assertIs(False, mt4_session.calls[0]["allow_redirects"])

    def test_supported_brokers_require_provider_backend_for_order_routing(self):
        cases = (
            ("OANDA", "oanda-rest"),
            ("FXCM", "fxcmpy"),
            ("IG", "ig-rest"),
            *((broker, "metatrader5") for broker in MT5_BROKER_PROVIDERS),
            ("Trading 212", "trading212-public-api"),
            ("moomoo", "moomoo-opend"),
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

    def test_trading212_public_api_is_real_broker_support_without_false_forex_claim(self):
        session = _FakeTrading212Session()
        connector = Trading212BrokerConnector(
            api_key="real-api-key",
            api_secret="real-api-secret",
            environment="paper",
            session=session,
        )

        support = connector.support_payload()
        self.assertTrue(support["broker_supported"])
        self.assertTrue(support["order_routing_supported"])
        self.assertTrue(support["order_execution_supported"])
        self.assertFalse(support["forex_order_routing_supported"])
        self.assertEqual("invest-and-stocks-isa-equities-only", support["broker_market_scope"])
        self.assertIn("Trading 212", SUPPORTED_BROKERS)
        self.assertNotIn("Trading 212", SUPPORTED_FOREX_BROKERS)
        self.assertIn("forex/CFD order routing is not exposed", support["capability_gaps"][-1])

        account = connector.fetch_account_snapshot()
        instruments = connector.fetch_instruments_snapshot()
        exchanges = connector.fetch_exchanges_snapshot()
        positions = connector.fetch_positions_snapshot()
        orders = connector.fetch_pending_orders_snapshot()
        order = connector.fetch_order_snapshot(41)
        self.assertEqual(212, account["account"]["id"])
        self.assertEqual(1, instruments["instrument_count"])
        self.assertEqual(1, exchanges["exchange_count"])
        self.assertEqual(1, positions["position_count"])
        self.assertEqual(1, orders["order_count"])
        self.assertEqual(41, order["order"]["id"])
        self.assertTrue(all(call["auth"] == ("real-api-key", "real-api-secret") for call in session.gets))

        market = connector.submit_market_order(ticker="AAPL_US_EQ", side="buy", quantity=0.5)
        limit = connector.submit_limit_order(
            ticker="AAPL_US_EQ",
            side="sell",
            quantity=1,
            limit_price=200,
            time_validity="good-till-cancel",
        )
        stop = connector.submit_stop_order(
            ticker="AAPL_US_EQ",
            side="sell",
            quantity=1,
            stop_price=150,
        )
        stop_limit = connector.submit_stop_limit_order(
            ticker="AAPL_US_EQ",
            side="buy",
            quantity=1,
            stop_price=180,
            limit_price=181,
        )
        self.assertEqual(False, market["request"]["extendedHours"])
        self.assertEqual(-1.0, limit["request"]["quantity"])
        self.assertEqual("GOOD_TILL_CANCEL", limit["request"]["timeValidity"])
        self.assertEqual(150.0, stop["request"]["stopPrice"])
        self.assertEqual(181.0, stop_limit["request"]["limitPrice"])
        self.assertEqual([], session.posts)

        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_market_order(
                ticker="AAPL_US_EQ",
                side="buy",
                quantity=1,
                dry_run=False,
            )
        submitted = connector.submit_market_order(
            ticker="AAPL_US_EQ",
            side="sell",
            quantity=1,
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual(-1.0, submitted["order"]["quantity"])
        self.assertTrue(session.posts[0]["url"].endswith("/api/v0/equity/orders/market"))
        self.assertEqual(("real-api-key", "real-api-secret"), session.posts[0]["auth"])

        cancelled = connector.cancel_order(42, dry_run=False, allow_live=True)
        self.assertTrue(cancelled["cancelled"])
        self.assertTrue(session.deletes[0]["url"].endswith("/api/v0/equity/orders/42"))
        self.assertTrue(
            all(call.get("allow_redirects") is False for call in [*session.gets, *session.posts, *session.deletes])
        )
        self.assertNotIn("real-api-secret", repr(account))
        self.assertNotIn("real-api-secret", repr(submitted))

    def test_citic_futures_ctp_runs_handshake_reads_guarded_orders_and_cancel(self):
        _FakeCtpApi.instances.clear()
        connector = CiticFuturesCtpConnector(
            front="tcp://10.20.30.40:53205",
            broker_id="66666",
            investor_id="real-investor",
            password="real-ctp-password",
            app_id="real-app-id",
            auth_code="real-auth-code",
            timeout_seconds=1,
            query_interval_seconds=0,
            sdk_module=_FakeCtpSdk,
        )

        support = connector.support_payload()
        self.assertTrue(support["broker_supported"])
        self.assertTrue(support["order_routing_supported"])
        self.assertFalse(support["forex_order_routing_supported"])
        self.assertEqual("china-futures-and-options", support["broker_market_scope"])
        self.assertIn("CITIC Futures", SUPPORTED_BROKERS)
        self.assertNotIn("CITIC Futures", SUPPORTED_FOREX_BROKERS)

        account = connector.fetch_account_snapshot()
        positions = connector.fetch_positions_snapshot("au2612")
        orders = connector.fetch_orders_snapshot("au2612")
        market = connector.fetch_market_snapshot(exchange_id="SHFE", instrument_id="au2612")
        instruments = connector.fetch_instruments_snapshot(exchange_id="SHFE", product_id="au")
        self.assertEqual(1200.5, account["account"][0]["Balance"])
        self.assertEqual(2, positions["positions"][0]["Position"])
        self.assertEqual("39", orders["orders"][0]["OrderRef"])
        self.assertEqual(501.2, market["market"][0]["LastPrice"])
        self.assertEqual("au", instruments["instruments"][0]["ProductID"])

        dry_run = connector.submit_order(
            exchange_id="SHFE",
            instrument_id="au2612",
            side="buy",
            volume=2,
            price=501.2,
        )
        self.assertEqual("dry_run", dry_run["status"])
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_order(
                exchange_id="SHFE",
                instrument_id="au2612",
                side="buy",
                volume=2,
                price=501.2,
                dry_run=False,
            )
        submitted = connector.submit_order(
            exchange_id="SHFE",
            instrument_id="au2612",
            side="sell",
            volume=1,
            offset="close_today",
            price=502.0,
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("sys-41", submitted["submission"]["order"]["OrderSysID"])
        order_ref = submitted["submission"]["order_ref"]
        cancelled = connector.cancel_order(
            exchange_id="SHFE",
            instrument_id="au2612",
            order_ref=order_ref,
            order_sys_id="sys-41",
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("cancelled", cancelled["status"])
        api = _FakeCtpApi.instances[0]
        self.assertEqual("tcp://10.20.30.40:53205", api.front)
        self.assertEqual("real-app-id", api.auth_requests[0].AppID)
        self.assertEqual("3", api.order_requests[0].CombOffsetFlag)
        self.assertEqual(7, api.cancel_requests[0].FrontID)
        self.assertNotIn("real-ctp-password", repr(account))
        self.assertNotIn("real-auth-code", repr(submitted))
        connector.close()
        self.assertTrue(api.released)

    def test_citic_futures_ctp_validates_endpoint_order_shapes_and_credentials(self):
        with self.assertRaisesRegex(ValueError, "tcp://host:port"):
            CiticFuturesCtpConnector(front="https://example.com/ctp")
        connector = CiticFuturesCtpConnector()
        with self.assertRaisesRegex(ValueError, "price is required"):
            connector.submit_order(
                exchange_id="SHFE",
                instrument_id="au2612",
                side="buy",
                volume=1,
            )
        with self.assertRaisesRegex(ValueError, "must be omitted"):
            connector.submit_order(
                exchange_id="SHFE",
                instrument_id="au2612",
                side="buy",
                volume=1,
                order_type="market",
                price=500,
            )
        with self.assertRaisesRegex(RuntimeError, "investor_id, password, app_id, and auth_code"):
            connector.fetch_account_snapshot()

    def test_moomoo_opend_supports_remote_gateway_reads_and_guarded_orders(self):
        trade = _FakeMoomooTradeContext()
        quote = _FakeMoomooQuoteContext()
        connector = MoomooOpenDConnector(
            host="10.20.30.40",
            port=21111,
            market="US",
            environment="simulate",
            account_id=7001,
            security_firm="FUTUINC",
            sdk_module=_FakeMoomooSdk,
            trade_context=trade,
            quote_context=quote,
        )

        support = connector.support_payload()
        self.assertTrue(support["broker_supported"])
        self.assertTrue(support["order_routing_supported"])
        self.assertFalse(support["forex_order_routing_supported"])
        self.assertEqual(
            "stocks-etfs-options-futures-funds-and-supported-crypto",
            support["broker_market_scope"],
        )
        self.assertIn("moomoo", SUPPORTED_BROKERS)
        self.assertNotIn("moomoo", SUPPORTED_FOREX_BROKERS)

        accounts = connector.fetch_accounts_snapshot()
        account = connector.fetch_account_snapshot()
        positions = connector.fetch_positions_snapshot()
        orders = connector.fetch_orders_snapshot(refresh_cache=True)
        market = connector.fetch_market_snapshot(["us.aapl", "US.MSFT"])
        self.assertEqual(7001, accounts["accounts"][0]["acc_id"])
        self.assertEqual(1000.0, account["account"][0]["total_assets"])
        self.assertEqual("US.AAPL", positions["positions"][0]["code"])
        self.assertTrue(orders["orders"][0]["refresh_cache"])
        self.assertEqual(["US.AAPL", "US.MSFT"], market["codes"])
        self.assertEqual("10.20.30.40", market["host"])

        dry_run = connector.submit_order(
            code="US.AAPL",
            side="buy",
            quantity=2,
            order_type="stop-limit",
            price=201,
            aux_price=200,
            time_in_force="GTC",
            session="ALL",
            remark="client-moomoo-1",
        )
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual("STOP_LIMIT", dry_run["request"]["order_type"])
        self.assertEqual(200.0, dry_run["request"]["aux_price"])
        self.assertEqual([], trade.placed)
        with self.assertRaisesRegex(ValueError, "trail_type and trail_value"):
            connector.submit_order(
                code="US.AAPL",
                side="sell",
                quantity=1,
                order_type="trailing-stop",
                price=200,
            )
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_order(
                code="US.AAPL",
                side="buy",
                quantity=1,
                order_type="market",
                dry_run=False,
            )
        submitted = connector.submit_order(
            code="US.AAPL",
            side="sell",
            quantity=1,
            order_type="market",
            dry_run=False,
            allow_live=True,
        )
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("m-42", submitted["order"][0]["order_id"])
        self.assertEqual("SELL", trade.placed[0]["trd_side"])
        self.assertEqual("MARKET", trade.placed[0]["order_type"])
        self.assertEqual([], trade.unlocks)

        cancelled = connector.cancel_order("m-42", dry_run=False, allow_live=True)
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual("CANCEL", trade.modified[0]["modify_order_op"])
        connector.close()
        self.assertTrue(trade.closed)
        self.assertTrue(quote.closed)

    def test_moomoo_real_orders_unlock_once_without_exposing_password(self):
        trade = _FakeMoomooTradeContext()
        connector = MoomooOpenDConnector(
            environment="real",
            unlock_password="real-trade-password",
            sdk_module=_FakeMoomooSdk,
            trade_context=trade,
            quote_context=_FakeMoomooQuoteContext(),
        )
        first = connector.submit_order(
            code="US.AAPL",
            side="buy",
            quantity=1,
            order_type="market",
            dry_run=False,
            allow_live=True,
        )
        connector.cancel_order("m-42", dry_run=False, allow_live=True)
        self.assertEqual(["real-trade-password"], trade.unlocks)
        self.assertNotIn("real-trade-password", repr(first))

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
        self.assertTrue(all(call.get("allow_redirects") is False for call in [*session.gets, *session.posts]))
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
        self.assertTrue(all(call.get("allow_redirects") is False for call in [*session.gets, *session.posts]))
        self.assertNotIn("real-security-token", repr(submitted))

    def test_metatrader4_bridge_runs_local_remote_protocol_reads_and_guarded_mutations(self):
        token = "mt4-bridge-test-token-123"
        terminal_id = "trade-nation-demo"
        seen: list[dict[str, str]] = []
        errors: list[BaseException] = []
        with MetaTrader4BridgeServer(token=token, port=0) as server:
            agent = threading.Thread(
                target=_run_fake_mt4_agent,
                kwargs={
                    "base_url": server.base_url,
                    "token": token,
                    "terminal_id": terminal_id,
                    "expected_commands": 7,
                    "seen": seen,
                    "errors": errors,
                },
                daemon=True,
            )
            agent.start()
            connector = MetaTrader4BridgeConnector(
                provider="Trade Nation",
                terminal_id=terminal_id,
                token=token,
                bridge_url=server.base_url,
                operation_timeout=5.0,
                poll_interval=0.01,
            )

            bridge = connector.fetch_bridge_snapshot()
            account = connector.fetch_account_snapshot()
            market = connector.fetch_market_snapshot("EURUSD")
            positions = connector.fetch_open_positions_snapshot("EURUSD")
            orders = connector.fetch_open_orders_snapshot("EURUSD")
            dry_run = connector.submit_market_order(
                symbol="EURUSD",
                side="buy",
                volume=0.1,
            )
            with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
                connector.submit_market_order(
                    symbol="EURUSD",
                    side="buy",
                    volume=0.1,
                    dry_run=False,
                )
            submitted = connector.submit_market_order(
                symbol="EURUSD",
                side="buy",
                volume=0.1,
                dry_run=False,
                allow_live=True,
            )
            cancelled = connector.cancel_order(
                ticket=7002,
                dry_run=False,
                allow_live=True,
            )
            closed = connector.close_position(
                ticket=7001,
                dry_run=False,
                allow_live=True,
            )
            agent.join(timeout=10.0)

        self.assertFalse(agent.is_alive())
        self.assertEqual([], errors)
        self.assertEqual("ok", bridge["bridge"]["status"])
        self.assertEqual(123456, account["account"]["account_number"])
        self.assertEqual("EURUSD", market["market"]["symbol"])
        self.assertEqual(0, positions["positions"]["count"])
        self.assertEqual(0, orders["orders"]["count"])
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual(7001, submitted["order"]["ticket"])
        self.assertTrue(cancelled["order"]["cancelled"])
        self.assertTrue(closed["order"]["closed"])
        self.assertEqual(
            [
                "account_snapshot",
                "market_snapshot",
                "open_positions_snapshot",
                "open_orders_snapshot",
                "market_order",
                "cancel_order",
                "close_position",
            ],
            [command["operation"] for command in seen],
        )
        self.assertNotIn(token, repr(connector.build_capability_snapshot()))
        self.assertTrue(connector.support_payload()["forex_order_routing_supported"])

    def test_metatrader4_bridge_validates_providers_transport_auth_and_queue_ownership(self):
        self.assertEqual(
            ("Trade Nation", "FXTF", "FOREX EXCHANGE"),
            MT4_BRIDGE_PROVIDERS,
        )
        for provider in MT4_BRIDGE_PROVIDERS:
            with self.subTest(provider=provider):
                connector = MetaTrader4BridgeConnector(
                    provider=provider,
                    terminal_id="terminal-1",
                )
                support = connector.support_payload()
                self.assertTrue(support["broker_supported"])
                self.assertTrue(support["forex_order_routing_supported"])
                self.assertEqual("metatrader4-bridge", support["connector_backend"])

        with self.assertRaisesRegex(ValueError, "provider must be one of"):
            MetaTrader4BridgeConnector(provider="unknown", terminal_id="terminal-1")
        with self.assertRaisesRegex(ValueError, "terminal_id"):
            MetaTrader4BridgeConnector(provider="FXTF", terminal_id="bad terminal")
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            MetaTrader4BridgeConnector(
                provider="FXTF",
                terminal_id="terminal-1",
                bridge_url="http://192.0.2.10:8765",
            )
        with self.assertRaisesRegex(ValueError, "at least 16"):
            MetaTrader4BridgeServer(token="short")

        state = MetaTrader4BridgeState(command_lease_seconds=0.01)
        command = state.enqueue(
            terminal_id="terminal-1",
            provider="FXTF",
            operation="account_snapshot",
            payload={},
        )
        claimed = state.claim_next("terminal-1")
        self.assertEqual(command["command_id"], claimed["command_id"])
        with self.assertRaisesRegex(PermissionError, "different terminal"):
            state.complete(
                terminal_id="terminal-2",
                command_id=command["command_id"],
                status="completed",
                result={},
            )
        completed = state.complete(
            terminal_id="terminal-1",
            command_id=command["command_id"],
            status="completed",
            result={"balance": 1.0},
        )
        duplicate = state.complete(
            terminal_id="terminal-1",
            command_id=command["command_id"],
            status="completed",
            result={"balance": 2.0},
        )
        self.assertEqual({"balance": 1.0}, completed["result"])
        self.assertEqual(completed, duplicate)

    def test_metatrader5_provider_wrappers_expose_verified_backend(self):
        cases = (
            (AvaTradeBrokerConnector, "AvaTrade"),
            (EcMarketsBrokerConnector, "EC Markets"),
            (GtcFxBrokerConnector, "GTCFX"),
            (FinaltoBrokerConnector, "Finalto"),
        )
        for connector_type, provider in cases:
            with self.subTest(provider=provider):
                connector = connector_type(client=_FakeMt5Client())
                support = connector.support_payload()
                self.assertEqual(provider, support["selected_forex_broker"])
                self.assertEqual("metatrader5", support["connector_backend"])
                self.assertTrue(support["broker_supported"])
                self.assertTrue(support["order_routing_supported"])
                self.assertTrue(support["live_evidence_required"])

    def test_every_verified_metatrader5_provider_has_routable_support_and_an_official_source(self):
        self.assertGreaterEqual(len(MT5_BROKER_PROVIDERS), 36)
        for provider in MT5_BROKER_PROVIDERS:
            with self.subTest(provider=provider):
                connector = MetaTrader5BrokerConnector(provider=provider, client=_FakeMt5Client())
                snapshot = connector.build_capability_snapshot()
                self.assertTrue(snapshot["support"]["broker_supported"])
                self.assertTrue(snapshot["support"]["order_routing_supported"])
                self.assertEqual("metatrader5", snapshot["support"]["connector_backend"])
                self.assertTrue(str(snapshot["official_transport_source"]).startswith("https://"))

    def test_stonex_mt5_is_routable_without_a_false_forex_claim(self):
        connector = MetaTrader5BrokerConnector(provider="StoneX", client=_FakeMt5Client())
        support = connector.support_payload()

        self.assertTrue(support["broker_supported"])
        self.assertTrue(support["order_routing_supported"])
        self.assertFalse(support["forex_order_routing_supported"])
        self.assertEqual("futures-and-options-on-futures", support["broker_market_scope"])
        self.assertIn("StoneX", SUPPORTED_BROKERS)
        self.assertNotIn("StoneX", SUPPORTED_FOREX_BROKERS)
        self.assertIn("forex/CFD order routing is not exposed", support["capability_gaps"][-1])

    def test_new_mt5_providers_preserve_aliases_and_market_scopes(self):
        sbcfx = MetaTrader5BrokerConnector(provider="SBCFX", client=_FakeMt5Client())
        phillip = MetaTrader5BrokerConnector(
            provider="Phillip Securities",
            client=_FakeMt5Client(),
        )
        ai_gold = MetaTrader5BrokerConnector(provider="AI Gold", client=_FakeMt5Client())

        self.assertTrue(sbcfx.support_payload()["forex_order_routing_supported"])
        self.assertEqual("PhillipCapital (Phillip Nova)", phillip.provider)
        self.assertTrue(phillip.support_payload()["forex_order_routing_supported"])
        self.assertEqual("AI Gold Securities", ai_gold.provider)
        ai_gold_support = ai_gold.support_payload()
        self.assertTrue(ai_gold_support["order_routing_supported"])
        self.assertFalse(ai_gold_support["forex_order_routing_supported"])
        self.assertEqual("otc-commodity-derivatives", ai_gold_support["broker_market_scope"])

    def test_metatrader5_runtime_supports_reads_and_guarded_preflighted_orders(self):
        client = _FakeMt5Client()
        connector = MetaTrader5BrokerConnector(
            provider="AvaTrade",
            login="123456",
            password="terminal-secret",
            server="Ava-Demo",
            terminal_path=r"C:\Ava MT5\terminal64.exe",
            portable=True,
            client=client,
        )

        dry_run = connector.submit_market_order(symbol="EURUSD.a", side="buy", volume=0.1)
        self.assertEqual("dry_run", dry_run["status"])
        self.assertEqual("EURUSD.a", dry_run["request"]["symbol"])
        self.assertEqual([], client.initialize_calls)
        self.assertNotIn("terminal-secret", repr(dry_run))
        with self.assertRaisesRegex(RuntimeError, "allow_live=True"):
            connector.submit_market_order(
                symbol="EURUSD.a",
                side="buy",
                volume=0.1,
                dry_run=False,
            )

        terminal = connector.fetch_terminal_snapshot()
        account = connector.fetch_account_snapshot()
        market = connector.fetch_market_snapshot("EURUSD.a")
        positions = connector.fetch_open_positions_snapshot("EURUSD.a")
        orders = connector.fetch_open_orders_snapshot("EURUSD.a")
        submitted = connector.submit_market_order(
            symbol="EURUSD.a",
            side="buy",
            volume=0.1,
            stop_loss=1.09,
            take_profit=1.12,
            deviation=10,
            magic=42,
            position_ticket=101,
            dry_run=False,
            allow_live=True,
        )

        self.assertTrue(terminal["terminal"]["connected"])
        self.assertEqual(123456, account["account"]["login"])
        self.assertEqual(1.1003, market["tick"]["ask"])
        self.assertEqual(101, positions["positions"][0]["ticket"])
        self.assertEqual(201, orders["orders"][0]["ticket"])
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual(301, submitted["order"]["order"])
        self.assertEqual(1.1003, client.sent_requests[0]["price"])
        self.assertEqual(101, client.sent_requests[0]["position"])
        self.assertEqual(client.ORDER_FILLING_IOC, client.sent_requests[0]["type_filling"])
        self.assertEqual(1, len(client.initialize_calls))
        self.assertEqual((r"C:\Ava MT5\terminal64.exe",), client.initialize_calls[0][0])
        self.assertEqual("Ava-Demo", client.initialize_calls[0][1]["server"])
        self.assertNotIn("terminal-secret", repr(submitted))
        connector.close()
        self.assertEqual(1, client.shutdown_calls)

    def test_metatrader5_rejects_initialization_and_preflight_failures_safely(self):
        failed_initialize = MetaTrader5BrokerConnector(
            provider="EC Markets",
            password="terminal-secret",
            client=_FakeMt5Client(initialize_result=False),
        )
        with self.assertRaisesRegex(RuntimeError, "initialize failed") as initialize_error:
            failed_initialize.fetch_account_snapshot()
        self.assertNotIn("terminal-secret", str(initialize_error.exception))

        rejected_client = _FakeMt5Client(check_retcode=10030)
        rejected = MetaTrader5BrokerConnector(provider="GTCFX", client=rejected_client)
        with self.assertRaisesRegex(RuntimeError, "preflight failed"):
            rejected.submit_market_order(
                symbol="EURUSD",
                side="sell",
                volume=0.2,
                dry_run=False,
                allow_live=True,
            )
        self.assertEqual([], rejected_client.sent_requests)

    def test_metatrader5_bounds_native_inputs_before_terminal_calls(self):
        with self.assertRaisesRegex(ValueError, "timeout_ms must be at most 300000"):
            MetaTrader5BrokerConnector(provider="AvaTrade", timeout_ms=300001, client=_FakeMt5Client())
        with self.assertRaisesRegex(ValueError, "server must not contain control characters"):
            MetaTrader5BrokerConnector(provider="AvaTrade", server="Ava\nDemo", client=_FakeMt5Client())

        connector = MetaTrader5BrokerConnector(provider="AvaTrade", client=_FakeMt5Client())
        with self.assertRaisesRegex(ValueError, "symbol must contain at most 64 UTF-8 bytes"):
            connector.fetch_market_snapshot("x" * 65)
        with self.assertRaisesRegex(ValueError, "comment must not contain control characters"):
            connector.submit_market_order(symbol="EURUSD", side="buy", volume=0.1, comment="safe\ncomment")


if __name__ == "__main__":
    unittest.main()
