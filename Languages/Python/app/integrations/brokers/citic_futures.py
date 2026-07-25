from __future__ import annotations

import math
from dataclasses import dataclass, field
from importlib import import_module
from threading import Event, Lock
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit

from ...security.redaction import redact_text, redact_value
from ...settings.exchange_support import build_exchange_support_payload


CITIC_CTP_ORDER_TYPES = ("MARKET", "LIMIT")
CITIC_CTP_OFFSETS = ("OPEN", "CLOSE", "CLOSE_TODAY", "CLOSE_YESTERDAY")
CITIC_CTP_TIME_IN_FORCE = ("GFD", "IOC")

_ACCOUNT_FIELDS = (
    "AccountID",
    "BrokerID",
    "CurrencyID",
    "TradingDay",
    "PreBalance",
    "Balance",
    "Available",
    "CurrMargin",
    "FrozenMargin",
    "Commission",
    "FrozenCommission",
    "CloseProfit",
    "PositionProfit",
)
_POSITION_FIELDS = (
    "BrokerID",
    "InvestorID",
    "ExchangeID",
    "InstrumentID",
    "PosiDirection",
    "HedgeFlag",
    "PositionDate",
    "Position",
    "YdPosition",
    "TodayPosition",
    "LongFrozen",
    "ShortFrozen",
    "OpenCost",
    "PositionCost",
    "UseMargin",
    "PositionProfit",
    "CloseProfit",
)
_ORDER_FIELDS = (
    "BrokerID",
    "InvestorID",
    "ExchangeID",
    "InstrumentID",
    "Direction",
    "CombOffsetFlag",
    "OrderPriceType",
    "LimitPrice",
    "VolumeTotalOriginal",
    "VolumeTraded",
    "VolumeTotal",
    "OrderRef",
    "OrderSysID",
    "FrontID",
    "SessionID",
    "OrderStatus",
    "OrderSubmitStatus",
    "StatusMsg",
    "InsertDate",
    "InsertTime",
    "UpdateTime",
    "CancelTime",
)
_MARKET_FIELDS = (
    "TradingDay",
    "ActionDay",
    "ExchangeID",
    "InstrumentID",
    "LastPrice",
    "Volume",
    "OpenInterest",
    "OpenPrice",
    "HighestPrice",
    "LowestPrice",
    "ClosePrice",
    "UpperLimitPrice",
    "LowerLimitPrice",
    "BidPrice1",
    "BidVolume1",
    "AskPrice1",
    "AskVolume1",
    "UpdateTime",
    "UpdateMillisec",
)
_INSTRUMENT_FIELDS = (
    "ExchangeID",
    "InstrumentID",
    "InstrumentName",
    "ProductID",
    "ProductClass",
    "VolumeMultiple",
    "PriceTick",
    "OpenDate",
    "ExpireDate",
    "MinLimitOrderVolume",
    "MaxLimitOrderVolume",
    "UnderlyingInstrID",
    "StrikePrice",
    "OptionsType",
)
_CTP_OPERATION_ERRORS = (
    AttributeError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _clean_text(value: object, *, field_name: str, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field_name} is required")
    if any(character in text for character in ("\r", "\n", "\x00")):
        raise ValueError(f"{field_name} contains invalid control characters")
    return text


def _clean_front(value: object) -> str:
    front = _clean_text(value, field_name="CITIC Futures CTP front")
    parsed = urlsplit(front)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("CITIC Futures CTP front must contain a valid TCP port") from exc
    if (
        parsed.scheme.lower() != "tcp"
        or not parsed.hostname
        or port is None
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("CITIC Futures CTP front must be a tcp://host:port endpoint without credentials or a path")
    return front[:-1] if front.endswith("/") else front


def _positive_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive number")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a positive number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return parsed


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0 or str(value).strip() not in {str(parsed), f"+{parsed}"}:
        raise ValueError(f"{field_name} must be a positive integer")
    return parsed


def _normalized_choice(value: object, *, field_name: str, choices: tuple[str, ...]) -> str:
    choice = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if choice not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}")
    return choice


def _decoded(value: object) -> object:
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gb18030"):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return redact_text(str(value))


def _field_payload(value: object, fields: tuple[str, ...]) -> dict[str, object]:
    if value is None:
        return {}
    payload: dict[str, object] = {}
    for name in fields:
        if hasattr(value, name):
            payload[name] = _decoded(getattr(value, name))
    return redact_value(payload)


def _response_error(info: object) -> str:
    if info is None:
        return ""
    try:
        error_id = int(getattr(info, "ErrorID", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        error_id = -1
    if error_id == 0:
        return ""
    message = _decoded(getattr(info, "ErrorMsg", "unknown CTP error"))
    return redact_text(f"CTP error {error_id}: {message}")


@dataclass
class _PendingResponse:
    event: Event = field(default_factory=Event)
    rows: list[dict[str, object]] = field(default_factory=list)
    error: str = ""


class _OpenCtpTraderClient:
    """Synchronous safety wrapper around the callback-driven OpenCTP trader API."""

    def __init__(
        self,
        *,
        front: str,
        broker_id: str,
        investor_id: str,
        password: str,
        app_id: str,
        auth_code: str,
        timeout_seconds: float,
        query_interval_seconds: float,
        flow_path: str = "",
        sdk_module: Any | None = None,
    ) -> None:
        self.front = front
        self.broker_id = broker_id
        self.investor_id = investor_id
        self.password = password
        self.app_id = app_id
        self.auth_code = auth_code
        self.timeout_seconds = timeout_seconds
        self.query_interval_seconds = query_interval_seconds
        self.flow_path = str(flow_path or "")
        self._sdk_module = sdk_module
        self._api: Any | None = None
        self._spi: Any | None = None
        self._ready = Event()
        self._connection_error = ""
        self._request_lock = Lock()
        self._request_id = 0
        self._order_ref = 0
        self._front_id = 0
        self._session_id = 0
        self._pending_queries: dict[int, _PendingResponse] = {}
        self._pending_orders: dict[str, _PendingResponse] = {}
        self._pending_cancels: dict[int, _PendingResponse] = {}
        self._pending_cancel_refs: dict[str, int] = {}
        self._pending_lock = Lock()
        self._query_lock = Lock()
        self._last_query_at = 0.0
        self._connected = False

    def _sdk(self) -> Any:
        if self._sdk_module is None:
            try:
                self._sdk_module = import_module("openctp_ctp.thosttraderapi")
            except ImportError as exc:
                raise RuntimeError("CITIC Futures CTP support requires the optional 'openctp-ctp' package") from exc
        return self._sdk_module

    def _next_request_id(self) -> int:
        with self._request_lock:
            self._request_id += 1
            return self._request_id

    def _next_order_ref(self) -> str:
        with self._request_lock:
            self._order_ref += 1
            return str(self._order_ref)

    def _fail_connection(self, message: object) -> None:
        self._connection_error = redact_text(str(message or "CTP connection failed"))
        self._ready.set()

    def _request_ok(self, result: object, *, operation: str) -> None:
        try:
            code = int(result or 0)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(f"CITIC Futures CTP {operation} returned an invalid status") from exc
        if code != 0:
            raise RuntimeError(f"CITIC Futures CTP {operation} was rejected with status {code}")

    def _make_spi(self) -> Any:
        owner = self
        sdk = self._sdk()
        base = getattr(sdk, "CThostFtdcTraderSpi", None)
        if base is None:
            raise RuntimeError("OpenCTP does not expose CThostFtdcTraderSpi")

        class TraderSpi(base):
            def __init__(self) -> None:
                super().__init__()

            def OnFrontConnected(self) -> None:
                owner._on_front_connected()

            def OnFrontDisconnected(self, reason: int) -> None:
                owner._connected = False
                owner._fail_connection(f"CTP front disconnected with reason {reason}")

            def OnRspAuthenticate(self, response: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_authenticate(info)

            def OnRspUserLogin(self, response: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_login(response, info)

            def OnRspSettlementInfoConfirm(
                self, response: object, info: object, request_id: int, is_last: bool
            ) -> None:
                owner._on_settlement_confirm(info)

            def OnRspQryTradingAccount(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_query(value, info, request_id, is_last, _ACCOUNT_FIELDS)

            def OnRspQryInvestorPosition(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_query(value, info, request_id, is_last, _POSITION_FIELDS)

            def OnRspQryOrder(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_query(value, info, request_id, is_last, _ORDER_FIELDS)

            def OnRspQryDepthMarketData(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_query(value, info, request_id, is_last, _MARKET_FIELDS)

            def OnRspQryInstrument(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_query(value, info, request_id, is_last, _INSTRUMENT_FIELDS)

            def OnRspOrderInsert(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_order_insert_response(value, info)

            def OnErrRtnOrderInsert(self, value: object, info: object) -> None:
                owner._on_order_insert_response(value, info)

            def OnRtnOrder(self, value: object) -> None:
                owner._on_order_return(value)

            def OnRspOrderAction(self, value: object, info: object, request_id: int, is_last: bool) -> None:
                owner._on_cancel_response(value, info, request_id)

            def OnErrRtnOrderAction(self, value: object, info: object) -> None:
                owner._on_cancel_error(value, info)

            def OnRspError(self, info: object, request_id: int, is_last: bool) -> None:
                owner._on_generic_error(info, request_id)

        return TraderSpi()

    def connect(self) -> None:
        if self._connected:
            return
        sdk = self._sdk()
        api_type = getattr(sdk, "CThostFtdcTraderApi", None)
        factory = getattr(api_type, "CreateFtdcTraderApi", None)
        if not callable(factory):
            raise RuntimeError("OpenCTP does not expose CThostFtdcTraderApi.CreateFtdcTraderApi")
        self._ready.clear()
        self._connection_error = ""
        self._spi = self._make_spi()
        self._api = factory(self.flow_path) if self.flow_path else factory()
        self._api.RegisterSpi(self._spi)
        topic = getattr(sdk, "THOST_TERT_QUICK", 2)
        self._api.SubscribePrivateTopic(topic)
        self._api.SubscribePublicTopic(topic)
        self._api.RegisterFront(self.front)
        self._api.Init()
        if not self._ready.wait(self.timeout_seconds):
            self.close()
            raise TimeoutError("CITIC Futures CTP connection timed out")
        if self._connection_error:
            message = self._connection_error
            self.close()
            raise RuntimeError(message)
        self._connected = True

    def _on_front_connected(self) -> None:
        try:
            sdk = self._sdk()
            request = sdk.CThostFtdcReqAuthenticateField()
            request.BrokerID = self.broker_id
            request.UserID = self.investor_id
            request.AppID = self.app_id
            request.AuthCode = self.auth_code
            self._request_ok(
                self._api.ReqAuthenticate(request, self._next_request_id()), operation="authentication request"
            )
        except _CTP_OPERATION_ERRORS as exc:
            self._fail_connection(exc)

    def _on_authenticate(self, info: object) -> None:
        error = _response_error(info)
        if error:
            self._fail_connection(f"CITIC Futures authentication failed: {error}")
            return
        try:
            sdk = self._sdk()
            request = sdk.CThostFtdcReqUserLoginField()
            request.BrokerID = self.broker_id
            request.UserID = self.investor_id
            request.Password = self.password
            request.UserProductInfo = "trading-bot"
            self._request_ok(self._api.ReqUserLogin(request, self._next_request_id()), operation="login request")
        except _CTP_OPERATION_ERRORS as exc:
            self._fail_connection(exc)

    def _on_login(self, response: object, info: object) -> None:
        error = _response_error(info)
        if error:
            self._fail_connection(f"CITIC Futures login failed: {error}")
            return
        try:
            self._front_id = int(getattr(response, "FrontID", 0) or 0)
            self._session_id = int(getattr(response, "SessionID", 0) or 0)
            self._order_ref = int(str(getattr(response, "MaxOrderRef", "0") or "0").strip() or 0)
            sdk = self._sdk()
            request = sdk.CThostFtdcSettlementInfoConfirmField()
            request.BrokerID = self.broker_id
            request.InvestorID = self.investor_id
            self._request_ok(
                self._api.ReqSettlementInfoConfirm(request, self._next_request_id()),
                operation="settlement confirmation request",
            )
        except _CTP_OPERATION_ERRORS as exc:
            self._fail_connection(exc)

    def _on_settlement_confirm(self, info: object) -> None:
        error = _response_error(info)
        if error:
            self._fail_connection(f"CITIC Futures settlement confirmation failed: {error}")
            return
        self._connected = True
        self._ready.set()

    def _on_query(
        self,
        value: object,
        info: object,
        request_id: int,
        is_last: bool,
        fields: tuple[str, ...],
    ) -> None:
        with self._pending_lock:
            pending = self._pending_queries.get(int(request_id))
            if pending is None:
                return
            error = _response_error(info)
            if error:
                pending.error = error
            if value is not None:
                payload = _field_payload(value, fields)
                if payload:
                    pending.rows.append(payload)
            if is_last or error:
                pending.event.set()

    def _on_generic_error(self, info: object, request_id: int) -> None:
        error = _response_error(info) or "unknown CTP request error"
        with self._pending_lock:
            for collection in (self._pending_queries, self._pending_cancels):
                pending = collection.get(int(request_id))
                if pending is not None:
                    pending.error = error
                    pending.event.set()

    def _on_order_insert_response(self, value: object, info: object) -> None:
        order_ref = str(getattr(value, "OrderRef", "") or "").strip()
        error = _response_error(info)
        if not order_ref or not error:
            return
        with self._pending_lock:
            pending = self._pending_orders.get(order_ref)
            if pending is not None:
                pending.error = error
                pending.event.set()

    def _on_order_return(self, value: object) -> None:
        order_ref = str(getattr(value, "OrderRef", "") or "").strip()
        if not order_ref:
            return
        payload = _field_payload(value, _ORDER_FIELDS)
        with self._pending_lock:
            pending = self._pending_orders.get(order_ref)
            if pending is not None:
                pending.rows = [payload]
                pending.event.set()
            cancel_request_id = self._pending_cancel_refs.get(order_ref)
            cancel_pending = self._pending_cancels.get(cancel_request_id or -1)
            if cancel_pending is not None and str(payload.get("OrderStatus", "")):
                cancel_pending.rows = [payload]
                cancel_pending.event.set()

    def _on_cancel_response(self, value: object, info: object, request_id: int) -> None:
        with self._pending_lock:
            pending = self._pending_cancels.get(int(request_id))
            if pending is None:
                return
            pending.error = _response_error(info)
            payload = _field_payload(value, _ORDER_FIELDS)
            if payload:
                pending.rows = [payload]
            pending.event.set()

    def _on_cancel_error(self, value: object, info: object) -> None:
        order_ref = str(getattr(value, "OrderRef", "") or "").strip()
        with self._pending_lock:
            request_id = self._pending_cancel_refs.get(order_ref)
            pending = self._pending_cancels.get(request_id or -1)
            if pending is not None:
                pending.error = _response_error(info) or "CTP cancellation failed"
                pending.event.set()

    def _ensure_connected(self) -> None:
        if not self._connected:
            self.connect()

    def _throttle_query(self) -> None:
        with self._query_lock:
            elapsed = monotonic() - self._last_query_at
            remaining = self.query_interval_seconds - elapsed
            if remaining > 0:
                sleep(remaining)
            self._last_query_at = monotonic()

    def _query(self, request: object, method_name: str) -> list[dict[str, object]]:
        self._ensure_connected()
        self._throttle_query()
        request_id = self._next_request_id()
        pending = _PendingResponse()
        with self._pending_lock:
            self._pending_queries[request_id] = pending
        try:
            method = getattr(self._api, method_name, None)
            if not callable(method):
                raise RuntimeError(f"OpenCTP does not expose {method_name}")
            self._request_ok(method(request, request_id), operation=method_name)
            if not pending.event.wait(self.timeout_seconds):
                raise TimeoutError(f"CITIC Futures CTP {method_name} timed out")
            if pending.error:
                raise RuntimeError(f"CITIC Futures CTP {method_name} failed: {pending.error}")
            return redact_value(list(pending.rows))
        finally:
            with self._pending_lock:
                self._pending_queries.pop(request_id, None)

    def fetch_account(self) -> list[dict[str, object]]:
        sdk = self._sdk()
        request = sdk.CThostFtdcQryTradingAccountField()
        request.BrokerID = self.broker_id
        request.InvestorID = self.investor_id
        return self._query(request, "ReqQryTradingAccount")

    def fetch_positions(self, instrument_id: str = "") -> list[dict[str, object]]:
        sdk = self._sdk()
        request = sdk.CThostFtdcQryInvestorPositionField()
        request.BrokerID = self.broker_id
        request.InvestorID = self.investor_id
        request.InstrumentID = str(instrument_id or "")
        return self._query(request, "ReqQryInvestorPosition")

    def fetch_orders(self, instrument_id: str = "") -> list[dict[str, object]]:
        sdk = self._sdk()
        request = sdk.CThostFtdcQryOrderField()
        request.BrokerID = self.broker_id
        request.InvestorID = self.investor_id
        request.InstrumentID = str(instrument_id or "")
        return self._query(request, "ReqQryOrder")

    def fetch_market(self, *, exchange_id: str, instrument_id: str) -> list[dict[str, object]]:
        sdk = self._sdk()
        request = sdk.CThostFtdcQryDepthMarketDataField()
        request.ExchangeID = exchange_id
        request.InstrumentID = instrument_id
        return self._query(request, "ReqQryDepthMarketData")

    def fetch_instruments(
        self, *, exchange_id: str = "", product_id: str = "", instrument_id: str = ""
    ) -> list[dict[str, object]]:
        sdk = self._sdk()
        request = sdk.CThostFtdcQryInstrumentField()
        request.ExchangeID = exchange_id
        request.ProductID = product_id
        request.InstrumentID = instrument_id
        return self._query(request, "ReqQryInstrument")

    def submit_order(self, order: dict[str, object]) -> dict[str, object]:
        self._ensure_connected()
        sdk = self._sdk()
        request = sdk.CThostFtdcInputOrderField()
        request_id = self._next_request_id()
        order_ref = self._next_order_ref()
        request.BrokerID = self.broker_id
        request.UserID = self.investor_id
        request.InvestorID = self.investor_id
        request.ExchangeID = order["exchange_id"]
        request.InstrumentID = order["instrument_id"]
        request.Direction = getattr(sdk, "THOST_FTDC_D_Buy" if order["side"] == "BUY" else "THOST_FTDC_D_Sell")
        offset_names = {
            "OPEN": "THOST_FTDC_OF_Open",
            "CLOSE": "THOST_FTDC_OF_Close",
            "CLOSE_TODAY": "THOST_FTDC_OF_CloseToday",
            "CLOSE_YESTERDAY": "THOST_FTDC_OF_CloseYesterday",
        }
        request.CombOffsetFlag = getattr(sdk, offset_names[str(order["offset"])])
        request.CombHedgeFlag = getattr(sdk, "THOST_FTDC_HF_Speculation")
        request.OrderPriceType = getattr(
            sdk, "THOST_FTDC_OPT_AnyPrice" if order["order_type"] == "MARKET" else "THOST_FTDC_OPT_LimitPrice"
        )
        if order["price"] is not None:
            request.LimitPrice = order["price"]
        request.VolumeTotalOriginal = order["volume"]
        request.TimeCondition = getattr(
            sdk, "THOST_FTDC_TC_IOC" if order["time_in_force"] == "IOC" else "THOST_FTDC_TC_GFD"
        )
        request.VolumeCondition = getattr(sdk, "THOST_FTDC_VC_AV")
        request.MinVolume = 1
        request.OrderRef = order_ref
        request.ForceCloseReason = getattr(sdk, "THOST_FTDC_FCC_NotForceClose")
        request.ContingentCondition = getattr(sdk, "THOST_FTDC_CC_Immediately")
        pending = _PendingResponse()
        with self._pending_lock:
            self._pending_orders[order_ref] = pending
        try:
            self._request_ok(self._api.ReqOrderInsert(request, request_id), operation="order insert")
            if not pending.event.wait(self.timeout_seconds):
                raise TimeoutError("CITIC Futures CTP order acknowledgement timed out")
            if pending.error:
                raise RuntimeError(f"CITIC Futures CTP order insert failed: {pending.error}")
            return redact_value(
                {
                    "request_id": request_id,
                    "order_ref": order_ref,
                    "order": pending.rows[0] if pending.rows else {},
                }
            )
        finally:
            with self._pending_lock:
                self._pending_orders.pop(order_ref, None)

    def cancel_order(
        self,
        *,
        exchange_id: str,
        instrument_id: str,
        order_ref: str,
        order_sys_id: str = "",
        front_id: int = 0,
        session_id: int = 0,
    ) -> dict[str, object]:
        self._ensure_connected()
        sdk = self._sdk()
        request = sdk.CThostFtdcInputOrderActionField()
        request_id = self._next_request_id()
        request.BrokerID = self.broker_id
        request.UserID = self.investor_id
        request.InvestorID = self.investor_id
        request.ExchangeID = exchange_id
        request.InstrumentID = instrument_id
        request.OrderRef = order_ref
        request.OrderSysID = order_sys_id
        request.FrontID = int(front_id or self._front_id)
        request.SessionID = int(session_id or self._session_id)
        request.ActionFlag = getattr(sdk, "THOST_FTDC_AF_Delete")
        pending = _PendingResponse()
        with self._pending_lock:
            self._pending_cancels[request_id] = pending
            self._pending_cancel_refs[order_ref] = request_id
        try:
            self._request_ok(self._api.ReqOrderAction(request, request_id), operation="order cancellation")
            if not pending.event.wait(self.timeout_seconds):
                raise TimeoutError("CITIC Futures CTP cancellation acknowledgement timed out")
            if pending.error:
                raise RuntimeError(f"CITIC Futures CTP cancellation failed: {pending.error}")
            return redact_value(
                {
                    "request_id": request_id,
                    "order_ref": order_ref,
                    "order_sys_id": order_sys_id,
                    "order": pending.rows[0] if pending.rows else {},
                }
            )
        finally:
            with self._pending_lock:
                self._pending_cancels.pop(request_id, None)
                self._pending_cancel_refs.pop(order_ref, None)

    def close(self) -> None:
        api, self._api = self._api, None
        self._connected = False
        self._spi = None
        if api is None:
            return
        try:
            api.RegisterSpi(None)
        except _CTP_OPERATION_ERRORS as exc:
            self._connection_error = redact_text(f"CITIC Futures CTP SPI detach failed during close: {exc}")
        release = getattr(api, "Release", None)
        if callable(release):
            release()


class CiticFuturesCtpConnector:
    """Guarded CITIC Futures connector over its officially published CTP interface."""

    def __init__(
        self,
        *,
        front: str = "tcp://101.226.254.149:53205",
        broker_id: str = "66666",
        investor_id: str = "",
        password: str = "",
        app_id: str = "",
        auth_code: str = "",
        timeout_seconds: float = 15.0,
        query_interval_seconds: float = 1.0,
        flow_path: str = "",
        sdk_module: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.front = _clean_front(front)
        self.broker_id = _clean_text(broker_id, field_name="CITIC Futures broker_id")
        self.investor_id = _clean_text(investor_id, field_name="CITIC Futures investor_id", required=False)
        self.password = str(password or "")
        self.app_id = _clean_text(app_id, field_name="CITIC Futures app_id", required=False)
        self.auth_code = str(auth_code or "")
        self.timeout_seconds = _positive_float(timeout_seconds, field_name="timeout_seconds")
        try:
            self.query_interval_seconds = float(query_interval_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("query_interval_seconds must be a non-negative number") from exc
        if not math.isfinite(self.query_interval_seconds) or self.query_interval_seconds < 0:
            raise ValueError("query_interval_seconds must be a non-negative number")
        self.flow_path = str(flow_path or "")
        self._sdk_module = sdk_module
        self._client_value = client

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "citic-ctp",
                "selected_forex_broker": "CITIC Futures",
            }
        )

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_broker": "CITIC Futures",
                "selected_forex_broker": "CITIC Futures",
                "connector_backend": "citic-ctp",
                "transport": "CTP TCP",
                "front": self.front,
                "broker_id": self.broker_id,
                "investor_id_present": bool(self.investor_id),
                "password_present": bool(self.password),
                "app_id_present": bool(self.app_id),
                "auth_code_present": bool(self.auth_code),
                "provider_api_scope": "china-futures-and-options",
                "forex_order_routing_supported": False,
                "supported_order_types": list(CITIC_CTP_ORDER_TYPES),
                "supported_offsets": list(CITIC_CTP_OFFSETS),
                "supported_time_in_force": list(CITIC_CTP_TIME_IN_FORCE),
                "official_transport_source": "https://www.citicsf.com/e-futures/csc/app/external_access",
                "support": self.support_payload(),
            }
        )

    def _client(self) -> Any:
        if self._client_value is None:
            if not self.investor_id or not self.password or not self.app_id or not self.auth_code:
                raise RuntimeError(
                    "CITIC Futures CTP network access requires investor_id, password, app_id, and auth_code"
                )
            self._client_value = _OpenCtpTraderClient(
                front=self.front,
                broker_id=self.broker_id,
                investor_id=self.investor_id,
                password=self.password,
                app_id=self.app_id,
                auth_code=self.auth_code,
                timeout_seconds=self.timeout_seconds,
                query_interval_seconds=self.query_interval_seconds,
                flow_path=self.flow_path,
                sdk_module=self._sdk_module,
            )
        return self._client_value

    def fetch_account_snapshot(self) -> dict[str, object]:
        return redact_value({**self.build_capability_snapshot(), "account": self._client().fetch_account()})

    def fetch_positions_snapshot(self, instrument_id: str = "") -> dict[str, object]:
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "positions": self._client().fetch_positions(str(instrument_id or "").strip()),
            }
        )

    def fetch_orders_snapshot(self, instrument_id: str = "") -> dict[str, object]:
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "orders": self._client().fetch_orders(str(instrument_id or "").strip()),
            }
        )

    def fetch_market_snapshot(self, *, exchange_id: str, instrument_id: str) -> dict[str, object]:
        exchange = _clean_text(exchange_id, field_name="exchange_id")
        instrument = _clean_text(instrument_id, field_name="instrument_id")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "market": self._client().fetch_market(exchange_id=exchange, instrument_id=instrument),
            }
        )

    def fetch_instruments_snapshot(
        self, *, exchange_id: str = "", product_id: str = "", instrument_id: str = ""
    ) -> dict[str, object]:
        instruments = self._client().fetch_instruments(
            exchange_id=str(exchange_id or "").strip(),
            product_id=str(product_id or "").strip(),
            instrument_id=str(instrument_id or "").strip(),
        )
        return redact_value({**self.build_capability_snapshot(), "instruments": instruments})

    def _order_request(
        self,
        *,
        exchange_id: str,
        instrument_id: str,
        side: str,
        volume: int,
        offset: str,
        order_type: str,
        price: float | None,
        time_in_force: str,
    ) -> dict[str, object]:
        normalized_type = _normalized_choice(
            order_type or "LIMIT", field_name="order_type", choices=CITIC_CTP_ORDER_TYPES
        )
        normalized_price = (
            None if price is None or str(price).strip() == "" else _positive_float(price, field_name="price")
        )
        if normalized_type == "LIMIT" and normalized_price is None:
            raise ValueError("price is required for a CITIC Futures limit order")
        if normalized_type == "MARKET" and normalized_price is not None:
            raise ValueError("price must be omitted for a CITIC Futures market order")
        return {
            "exchange_id": _clean_text(exchange_id, field_name="exchange_id"),
            "instrument_id": _clean_text(instrument_id, field_name="instrument_id"),
            "side": _normalized_choice(side, field_name="side", choices=("BUY", "SELL")),
            "volume": _positive_int(volume, field_name="volume"),
            "offset": _normalized_choice(offset or "OPEN", field_name="offset", choices=CITIC_CTP_OFFSETS),
            "order_type": normalized_type,
            "price": normalized_price,
            "time_in_force": _normalized_choice(
                time_in_force or "GFD", field_name="time_in_force", choices=CITIC_CTP_TIME_IN_FORCE
            ),
        }

    def submit_order(
        self,
        *,
        exchange_id: str,
        instrument_id: str,
        side: str,
        volume: int,
        offset: str = "open",
        order_type: str = "limit",
        price: float | None = None,
        time_in_force: str = "GFD",
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        request = self._order_request(
            exchange_id=exchange_id,
            instrument_id=instrument_id,
            side=side,
            volume=volume,
            offset=offset,
            order_type=order_type,
            price=price,
            time_in_force=time_in_force,
        )
        if dry_run:
            return redact_value({"status": "dry_run", "request": request, **self.build_capability_snapshot()})
        if not allow_live:
            raise RuntimeError("CITIC Futures CTP order submission requires allow_live=True when dry_run=False")
        submitted = self._client().submit_order(request)
        return redact_value(
            {"status": "submitted", "request": request, "submission": submitted, **self.build_capability_snapshot()}
        )

    def cancel_order(
        self,
        *,
        exchange_id: str,
        instrument_id: str,
        order_ref: str,
        order_sys_id: str = "",
        front_id: int = 0,
        session_id: int = 0,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        request = {
            "exchange_id": _clean_text(exchange_id, field_name="exchange_id"),
            "instrument_id": _clean_text(instrument_id, field_name="instrument_id"),
            "order_ref": _clean_text(order_ref, field_name="order_ref"),
            "order_sys_id": str(order_sys_id or "").strip(),
            "front_id": int(front_id),
            "session_id": int(session_id),
        }
        if request["front_id"] < 0 or request["session_id"] < 0:
            raise ValueError("front_id and session_id must be non-negative")
        if dry_run:
            return redact_value({"status": "dry_run", "request": request, **self.build_capability_snapshot()})
        if not allow_live:
            raise RuntimeError("CITIC Futures CTP cancellation requires allow_live=True when dry_run=False")
        cancelled = self._client().cancel_order(**request)
        return redact_value(
            {"status": "cancelled", "request": request, "cancellation": cancelled, **self.build_capability_snapshot()}
        )

    def close(self) -> None:
        client, self._client_value = self._client_value, None
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> CiticFuturesCtpConnector:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


__all__ = [
    "CITIC_CTP_OFFSETS",
    "CITIC_CTP_ORDER_TYPES",
    "CITIC_CTP_TIME_IN_FORCE",
    "CiticFuturesCtpConnector",
]
