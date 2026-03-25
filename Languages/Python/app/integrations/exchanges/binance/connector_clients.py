from __future__ import annotations

import re

DEFAULT_CONNECTOR_BACKEND = "binance-sdk-derivatives-trading-usds-futures"

_ccxt = None

try:
    from binance.spot import Spot as _OfficialSpotClient
    from binance.api import API as _OfficialAPIBase
    from binance.error import (
        ClientError as _OfficialClientError,
        ServerError as _OfficialServerError,
    )
except Exception:
    _OfficialSpotClient = None
    _OfficialAPIBase = None
    _OfficialClientError = None
    _OfficialServerError = None


def _load_ccxt():
    global _ccxt
    if _ccxt is None:
        import ccxt as _ccxt_mod

        _ccxt = _ccxt_mod
    return _ccxt


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _normalize_connector_choice(value) -> str:
    text_raw = str(value or "").strip()
    if not text_raw:
        return DEFAULT_CONNECTOR_BACKEND
    text = text_raw.lower()
    if text in {
        "binance-sdk-derivatives-trading-usds-futures",
        "binance_sdk_derivatives_trading_usds_futures",
    } or ("sdk" in text and "future" in text and ("usd" in text or "usds" in text)):
        return "binance-sdk-derivatives-trading-usds-futures"
    if text in {
        "binance-sdk-derivatives-trading-coin-futures",
        "binance_sdk_derivatives_trading_coin_futures",
    } or ("sdk" in text and "coin" in text and "future" in text):
        return "binance-sdk-derivatives-trading-coin-futures"
    if text in {"binance-sdk-spot", "binance_sdk_spot"} or ("sdk" in text and "spot" in text):
        return "binance-sdk-spot"
    if text == "ccxt" or "ccxt" in text:
        return "ccxt"
    if "connector" in text or "official" in text or text == "binance-connector":
        return "binance-connector"
    if "python" in text and "binance" in text:
        return "python-binance"
    return DEFAULT_CONNECTOR_BACKEND


class OfficialConnectorError(Exception):
    def __init__(self, code=None, status_code=None, message=""):
        self.code = code if code is not None else 0
        self.status_code = status_code if status_code is not None else 0
        self.message = message or ""
        super().__init__(self.message)


if _OfficialAPIBase is not None and _OfficialSpotClient is not None:

    class _OfficialFuturesHTTP(_OfficialAPIBase):  # type: ignore[misc]
        def __init__(self, api_key, api_secret, base_url):
            super().__init__(api_key, api_secret, base_url=base_url)


    class OfficialConnectorAdapter:
        def __init__(self, api_key, api_secret, *, mode="Live"):
            mode_text = (mode or "Live").strip().lower()
            is_testnet = any(tag in mode_text for tag in ("test", "demo"))
            spot_base = (
                "https://testnet.binance.vision"
                if is_testnet
                else "https://api.binance.com"
            )
            futures_base = (
                "https://testnet.binancefuture.com"
                if is_testnet
                else "https://fapi.binance.com"
            )
            self._spot = _OfficialSpotClient(api_key, api_secret, base_url=spot_base)
            self._futures = _OfficialFuturesHTTP(
                api_key,
                api_secret,
                base_url=futures_base,
            )
            self._bw_throttled = True
            self._bw_throttle = None

        def _throttle(self, path: str | None) -> None:
            cb = getattr(self, "_bw_throttle", None)
            if callable(cb):
                try:
                    cb(path)
                except Exception:
                    pass

        def _call(self, func, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                if _OfficialClientError is not None and isinstance(exc, _OfficialClientError):
                    raise OfficialConnectorError(
                        exc.error_code,
                        exc.status_code,
                        exc.error_message,
                    ) from exc
                if _OfficialServerError is not None and isinstance(exc, _OfficialServerError):
                    raise OfficialConnectorError(None, exc.status_code, exc.message) from exc
                raise

        def _call_futures(self, method: str, path: str, params=None, *, signed=False):
            payload = dict(params or {})
            http_method = (method or "GET").upper()
            self._throttle(path)
            if signed:
                return self._call(self._futures.sign_request, http_method, path, payload)
            return self._call(self._futures.send_request, http_method, path, payload)

        def get_account(self, **params):
            self._throttle("/api/v3/account")
            return self._call(self._spot.account, **params)

        def get_symbol_info(self, symbol: str):
            self._throttle("/api/v3/exchangeInfo")
            data = self._call(self._spot.exchange_info, symbol=symbol)
            symbols = (data or {}).get("symbols") if isinstance(data, dict) else None
            if symbols:
                return symbols[0]
            return None

        def get_exchange_info(self, **params):
            self._throttle("/api/v3/exchangeInfo")
            return self._call(self._spot.exchange_info, **params)

        def get_symbol_ticker(self, **params):
            self._throttle("/api/v3/ticker/price")
            return self._call(self._spot.ticker_price, **params)

        def get_klines(self, **params):
            self._throttle("/api/v3/klines")
            return self._call(self._spot.klines, **params)

        def create_order(self, **params):
            payload = dict(params or {})
            self._throttle("/api/v3/order")
            return self._call(self._spot.new_order, **payload)

        def futures_klines(self, **params):
            return self._call_futures("GET", "/fapi/v1/klines", params, signed=False)

        def futures_exchange_info(self, **params):
            return self._call_futures("GET", "/fapi/v1/exchangeInfo", params, signed=False)

        def futures_leverage_bracket(self, **params):
            return self._call_futures("GET", "/fapi/v1/leverageBracket", params, signed=False)

        def futures_account(self, **params):
            return self._call_futures("GET", "/fapi/v2/account", params, signed=True)

        def futures_account_balance(self, **params):
            return self._call_futures("GET", "/fapi/v2/balance", params, signed=True)

        def futures_position_information(self, **params):
            return self._call_futures("GET", "/fapi/v2/positionRisk", params, signed=True)

        def futures_position_risk(self, **params):
            return self._call_futures("GET", "/fapi/v2/positionRisk", params, signed=True)

        def futures_create_order(self, **params):
            return self._call_futures("POST", "/fapi/v1/order", params, signed=True)

        def futures_symbol_ticker(self, **params):
            return self._call_futures("GET", "/fapi/v1/ticker/price", params, signed=False)

        def futures_get_position_mode(self, **params):
            return self._call_futures("GET", "/fapi/v1/positionSide/dual", params, signed=True)

        def futures_change_position_mode(self, **params):
            return self._call_futures("POST", "/fapi/v1/positionSide/dual", params, signed=True)

        def futures_cancel_all_open_orders(self, **params):
            return self._call_futures("DELETE", "/fapi/v1/allOpenOrders", params, signed=True)

        def futures_get_open_orders(self, **params):
            return self._call_futures("GET", "/fapi/v1/openOrders", params, signed=True)

        def futures_change_margin_type(self, **params):
            return self._call_futures("POST", "/fapi/v1/marginType", params, signed=True)

        def futures_change_leverage(self, **params):
            return self._call_futures("POST", "/fapi/v1/leverage", params, signed=True)

        def futures_book_ticker(self, **params):
            return self._call_futures("GET", "/fapi/v1/ticker/bookTicker", params, signed=False)

        def _request_futures_api(self, method, path, signed=False, version=1, **kwargs):
            payload = dict(kwargs.get("data") or kwargs.get("params") or {})
            url_path = f"/fapi/v{int(version)}/{path}"
            return self._call_futures(method, url_path, payload, signed=signed)

else:

    class OfficialConnectorAdapter:
        def __init__(self, *_, **__):
            raise RuntimeError("binance-connector library is not available")


class CcxtConnectorError(Exception):
    def __init__(self, code=None, status_code=None, message="", response=None):
        self.code = code if code is not None else 0
        self.status_code = status_code if status_code is not None else 0
        self.message = message or ""
        self.response = response
        super().__init__(self.message)


def _wrap_ccxt_exception(exc: Exception) -> CcxtConnectorError:
    message = str(exc)
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    if code is None and message:
        match = re.search(r'"code"\s*:\s*(-?\d+)', message)
        if match is None:
            match = re.search(r"code\s*=\s*(-?\d+)", message)
        if match is not None:
            try:
                code = int(match.group(1))
            except Exception:
                code = None
    if status is None and message:
        match = re.search(r"\b(4\d\d|5\d\d)\b", message)
        if match is not None:
            try:
                status = int(match.group(1))
            except Exception:
                status = None
    response = getattr(exc, "response", None)
    return CcxtConnectorError(
        code=code,
        status_code=status,
        message=message,
        response=response,
    )


def _ccxt_method_name(prefix: str, http_method: str, path: str) -> str:
    method = (http_method or "").strip().lower()
    parts = [part for part in re.split(r"[\\/_-]", str(path or "")) if part]
    cap = "".join(part[:1].upper() + part[1:] for part in parts)
    return f"{prefix}{method.title()}{cap}"


class CcxtBinanceAdapter:
    def __init__(self, api_key, api_secret, *, mode="Live", account_type="Spot"):
        try:
            ccxt = _load_ccxt()
        except Exception as exc:
            raise RuntimeError("ccxt library is not available") from exc
        self.API_KEY = api_key or ""
        self.API_SECRET = api_secret or ""
        self.mode = mode
        self.account_type = str(account_type or "Spot").strip().upper()
        self._bw_throttled = True
        self._bw_throttle = None
        self._exchange = ccxt.binance(
            {
                "apiKey": self.API_KEY,
                "secret": self.API_SECRET,
                "enableRateLimit": True,
            }
        )
        try:
            default_type = "future" if self.account_type.startswith("FUT") else "spot"
            self._exchange.options["defaultType"] = default_type
        except Exception:
            pass
        if _is_testnet_mode(self.mode):
            try:
                self._exchange.set_sandbox_mode(True)
            except Exception:
                pass
            self._apply_testnet_urls()

    def _apply_testnet_urls(self) -> None:
        try:
            urls = getattr(self._exchange, "urls", None)
            if not isinstance(urls, dict):
                return
            api = urls.get("api")
            if not isinstance(api, dict):
                return
            spot_base = "https://testnet.binance.vision"
            futures_base = "https://testnet.binancefuture.com"

            def _swap(key: str, value: str) -> None:
                if key in api and isinstance(api.get(key), str):
                    api[key] = value

            _swap("public", f"{spot_base}/api/v3")
            _swap("private", f"{spot_base}/api/v3")
            _swap("fapiPublic", f"{futures_base}/fapi/v1")
            _swap("fapiPrivate", f"{futures_base}/fapi/v1")
            _swap("dapiPublic", f"{futures_base}/dapi/v1")
            _swap("dapiPrivate", f"{futures_base}/dapi/v1")
        except Exception:
            pass

    def _throttle(self, path: str | None) -> None:
        cb = getattr(self, "_bw_throttle", None)
        if callable(cb):
            try:
                cb(path)
            except Exception:
                pass

    def _call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            raise _wrap_ccxt_exception(exc) from exc

    def _call_ccxt_method(
        self,
        method_name: str,
        params: dict | None = None,
        *,
        path: str | None = None,
    ):
        self._throttle(path or method_name)
        func = getattr(self._exchange, method_name, None)
        if func is None:
            raise RuntimeError(f"ccxt method missing: {method_name}")
        clean_params = {key: val for key, val in (params or {}).items() if val is not None}
        if clean_params:
            return self._call(func, clean_params)
        return self._call(func)

    def _call_ccxt_request(
        self,
        api_prefix: str,
        http_method: str,
        path: str,
        params: dict | None = None,
    ):
        method_name = _ccxt_method_name(api_prefix, http_method, path)
        func = getattr(self._exchange, method_name, None)
        if func is not None:
            return self._call_ccxt_method(method_name, params, path=path)
        return self._call(
            self._exchange.request,
            path,
            api=api_prefix,
            method=http_method.upper(),
            params=params or {},
        )

    def get_account(self, **params):
        return self._call_ccxt_method("privateGetAccount", params, path="/api/v3/account")

    def get_symbol_info(self, symbol: str):
        payload = {"symbol": symbol}
        data = self._call_ccxt_method(
            "publicGetExchangeInfo",
            payload,
            path="/api/v3/exchangeInfo",
        )
        symbols = (data or {}).get("symbols") if isinstance(data, dict) else None
        if symbols:
            return symbols[0]
        return None

    def get_exchange_info(self, **params):
        return self._call_ccxt_method("publicGetExchangeInfo", params, path="/api/v3/exchangeInfo")

    def get_symbol_ticker(self, **params):
        return self._call_ccxt_method("publicGetTickerPrice", params, path="/api/v3/ticker/price")

    def get_klines(self, **params):
        return self._call_ccxt_method("publicGetKlines", params, path="/api/v3/klines")

    def create_order(self, **params):
        return self._call_ccxt_method("privatePostOrder", params, path="/api/v3/order")

    def get_my_trades(self, **params):
        return self._call_ccxt_method("privateGetMyTrades", params, path="/api/v3/myTrades")

    def futures_klines(self, **params):
        return self._call_ccxt_method("fapiPublicGetKlines", params, path="/fapi/v1/klines")

    def futures_exchange_info(self, **params):
        return self._call_ccxt_method("fapiPublicGetExchangeInfo", params, path="/fapi/v1/exchangeInfo")

    def futures_leverage_bracket(self, **params):
        return self._call_ccxt_method("fapiPrivateGetLeverageBracket", params, path="/fapi/v1/leverageBracket")

    def futures_account(self, **params):
        return self._call_ccxt_method("fapiPrivateGetAccount", params, path="/fapi/v2/account")

    def futures_account_balance(self, **params):
        return self._call_ccxt_method("fapiPrivateGetBalance", params, path="/fapi/v2/balance")

    def futures_position_information(self, **params):
        return self._call_ccxt_method("fapiPrivateGetPositionRisk", params, path="/fapi/v2/positionRisk")

    def futures_position_risk(self, **params):
        return self.futures_position_information(**params)

    def futures_create_order(self, **params):
        return self._call_ccxt_method("fapiPrivatePostOrder", params, path="/fapi/v1/order")

    def futures_symbol_ticker(self, **params):
        return self._call_ccxt_method("fapiPublicGetTickerPrice", params, path="/fapi/v1/ticker/price")

    def futures_get_position_mode(self, **params):
        return self._call_ccxt_method("fapiPrivateGetPositionSideDual", params, path="/fapi/v1/positionSide/dual")

    def futures_change_position_mode(self, **params):
        return self._call_ccxt_method("fapiPrivatePostPositionSideDual", params, path="/fapi/v1/positionSide/dual")

    def futures_cancel_all_open_orders(self, **params):
        return self._call_ccxt_method("fapiPrivateDeleteAllOpenOrders", params, path="/fapi/v1/allOpenOrders")

    def futures_get_open_orders(self, **params):
        return self._call_ccxt_method("fapiPrivateGetOpenOrders", params, path="/fapi/v1/openOrders")

    def futures_change_margin_type(self, **params):
        return self._call_ccxt_method("fapiPrivatePostMarginType", params, path="/fapi/v1/marginType")

    def futures_change_leverage(self, **params):
        return self._call_ccxt_method("fapiPrivatePostLeverage", params, path="/fapi/v1/leverage")

    def futures_book_ticker(self, **params):
        return self._call_ccxt_method("fapiPublicGetTickerBookTicker", params, path="/fapi/v1/ticker/bookTicker")

    def futures_account_trades(self, **params):
        return self._call_ccxt_method("fapiPrivateGetUserTrades", params, path="/fapi/v1/userTrades")

    def _request_futures_api(self, method, path, signed=False, version=1, **kwargs):
        payload = dict(kwargs.get("data") or kwargs.get("params") or {})
        api_prefix = "fapiPrivate" if signed else "fapiPublic"
        return self._call_ccxt_request(api_prefix, method, path, payload)
