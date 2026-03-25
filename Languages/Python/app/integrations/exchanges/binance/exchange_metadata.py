from __future__ import annotations

import requests


def fetch_symbols(self, sort_by_volume: bool = False, top_n: int | None = None):
    """
    Robust symbol fetcher.
    FUTURES: return only USDT-M perpetual symbols from exchangeInfo.
    SPOT: return USDT quote symbols.
    """

    def _safe_json(url: str, timeout: float = 10.0):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            return None
        return None

    acct = str(getattr(self, "account_type", "SPOT") or "SPOT").strip().upper()
    allowed = set()

    if acct.startswith("FUT"):
        info = None
        try:
            info = self.client.futures_exchange_info()
        except Exception:
            info = None
        if not info or not isinstance(info, dict) or "symbols" not in info:
            info = _safe_json(f"{self._futures_base()}/v1/exchangeInfo") or {}

        for symbol_info in (info or {}).get("symbols", []):
            try:
                if (
                    symbol_info.get("status") == "TRADING"
                    and symbol_info.get("quoteAsset") == "USDT"
                    and symbol_info.get("contractType") == "PERPETUAL"
                ):
                    allowed.add((symbol_info.get("symbol") or "").upper())
            except Exception:
                continue

        ordered = sorted(list(allowed))
        if sort_by_volume and ordered:
            vol_map = {}
            data = _safe_json(f"{self._futures_base()}/v1/ticker/24hr") or []
            for ticker in data:
                sym = (ticker.get("symbol") or "").upper()
                try:
                    vol_map[sym] = float(ticker.get("quoteVolume") or 0.0)
                except Exception:
                    vol_map[sym] = 0.0
            ordered = sorted(ordered, key=lambda s: vol_map.get(s, 0.0), reverse=True)

        if top_n:
            ordered = ordered[: int(top_n)]
        return ordered

    info = None
    try:
        info = self.client.get_exchange_info()
    except Exception:
        info = None
    if not info or not isinstance(info, dict) or "symbols" not in info:
        info = _safe_json(f"{self._spot_base()}/v3/exchangeInfo") or {}

    for symbol_info in (info or {}).get("symbols", []):
        try:
            if symbol_info.get("status") == "TRADING" and symbol_info.get("quoteAsset") == "USDT":
                allowed.add((symbol_info.get("symbol") or "").upper())
        except Exception:
            continue

    ordered = sorted(list(allowed))
    if sort_by_volume and ordered:
        vol_map = {}
        data = _safe_json(f"{self._spot_base()}/v3/ticker/24hr") or []
        for ticker in data:
            sym = (ticker.get("symbol") or "").upper()
            try:
                vol_map[sym] = float(ticker.get("quoteVolume") or 0.0)
            except Exception:
                vol_map[sym] = 0.0
        ordered = sorted(ordered, key=lambda s: vol_map.get(s, 0.0), reverse=True)

    if top_n:
        ordered = ordered[: int(top_n)]
    return ordered


def get_symbol_info_spot(self, symbol: str) -> dict:
    key = symbol.upper()
    if key not in self._symbol_info_cache_spot:
        info = None
        try:
            info = self.client.get_symbol_info(key)
        except Exception:
            info = None
        if not info:
            try:
                resp = requests.get(f"{self._spot_base()}/v3/exchangeInfo", params={"symbol": key}, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        symbols = data.get("symbols") or []
                        if symbols:
                            info = symbols[0]
            except Exception:
                info = None
        if not info:
            raise ValueError(f"No spot symbol info for {symbol}")
        self._symbol_info_cache_spot[key] = info
    return self._symbol_info_cache_spot[key]


def get_symbol_quote_precision_spot(self, symbol: str) -> int:
    info = self.get_symbol_info_spot(symbol)
    qp = info.get("quoteAssetPrecision") or info.get("quotePrecision") or 8
    return int(qp)


def get_spot_symbol_filters(self, symbol: str) -> dict:
    info = self.get_symbol_info_spot(symbol)
    step_size = None
    min_qty = None
    min_notional = None
    for filt in info.get("filters", []):
        if filt.get("filterType") == "LOT_SIZE":
            step_size = float(filt.get("stepSize", "0"))
            min_qty = float(filt.get("minQty", "0"))
        elif filt.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
            min_notional = float(filt.get("minNotional", filt.get("notional", "0")))
    return {"stepSize": step_size or 0.0, "minQty": min_qty or 0.0, "minNotional": min_notional or 0.0}


def get_futures_exchange_info(self) -> dict:
    if self._symbol_info_cache_futures is None:
        self._symbol_info_cache_futures = self._futures_call("futures_exchange_info", allow_recv=True)
    return self._symbol_info_cache_futures


def get_futures_symbol_info(self, symbol: str) -> dict:
    info = self.get_futures_exchange_info()
    for symbol_info in info.get("symbols", []):
        if symbol_info.get("symbol") == symbol.upper():
            return symbol_info
    raise ValueError(f"No futures symbol info for {symbol}")


def get_futures_symbol_filters(self, symbol: str) -> dict:
    symbol_info = self.get_futures_symbol_info(symbol)
    step_size = None
    min_qty = None
    price_tick = None
    min_notional = None
    for filt in symbol_info.get("filters", []):
        if filt.get("filterType") == "LOT_SIZE":
            step_size = float(filt.get("stepSize", "0"))
            min_qty = float(filt.get("minQty", "0"))
        elif filt.get("filterType") == "PRICE_FILTER":
            price_tick = float(filt.get("tickSize", "0"))
        elif filt.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
            mn = filt.get("notional") or filt.get("minNotional") or 0
            try:
                min_notional = float(mn)
            except Exception:
                min_notional = 0.0
    return {
        "stepSize": step_size or 0.0,
        "minQty": min_qty or 0.0,
        "tickSize": price_tick or 0.0,
        "minNotional": min_notional or 0.0,
    }


def get_futures_max_leverage(self, symbol: str) -> int:
    sym = str(symbol or "").upper()
    max_futures_leverage = max(1, int(getattr(self, "_max_futures_leverage_constant", 150) or 150))
    if not sym:
        return max_futures_leverage
    cache = getattr(self, "_futures_max_leverage_cache", {})
    if sym in cache:
        try:
            return int(cache[sym])
        except Exception:
            pass
    max_lev = None
    try:
        data = self.client.futures_leverage_bracket(symbol=sym)
        records = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
        for rec in records:
            if isinstance(rec, dict):
                rec_sym = str(rec.get("symbol") or sym).upper()
                if rec_sym and rec_sym != sym:
                    continue
                brackets = rec.get("brackets") or []
            else:
                brackets = []
            for bracket in brackets:
                if not isinstance(bracket, dict):
                    continue
                lev_val = bracket.get("initialLeverage") or bracket.get("initial_leverage")
                try:
                    lev_int = int(float(lev_val))
                except Exception:
                    continue
                if lev_int > 0:
                    max_lev = max(max_lev or 0, lev_int)
            if max_lev:
                break
    except Exception:
        max_lev = None if max_lev is None else max_lev
    if max_lev is None:
        try:
            info = self.get_futures_symbol_info(sym)
            for filt in info.get("filters", []):
                if str(filt.get("filterType") or "").upper() == "LEVERAGE":
                    lev_val = filt.get("maxLeverage") or filt.get("max_leverage")
                    if lev_val is not None:
                        max_lev = int(float(lev_val))
                        break
        except Exception:
            pass
    if not max_lev or int(max_lev) <= 0:
        max_lev = max_futures_leverage
    max_lev = max(1, min(int(max_lev), max_futures_leverage))
    self._futures_max_leverage_cache[sym] = max_lev
    return max_lev


def get_recent_force_orders(
    self,
    symbol: str | None = None,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 20,
) -> list[dict]:
    """Fetch recent forced liquidation orders for the given futures symbol."""
    func = getattr(self.client, "futures_force_orders", None)
    if func is None:
        func = getattr(self.client, "futures_get_force_orders", None)
    if func is None:
        return []
    params: dict[str, object] = {"limit": max(1, min(int(limit or 1), 1000))}
    if symbol:
        params["symbol"] = str(symbol).upper()
    if start_time:
        try:
            params["startTime"] = int(start_time)
        except Exception:
            pass
    if end_time:
        try:
            params["endTime"] = int(end_time)
        except Exception:
            pass
    try:
        data = func(**params)
    except Exception:
        return []
    if isinstance(data, dict):
        seq = None
        for key in ("rows", "data", "forceOrders", "orders", "list"):
            if key in data:
                seq = data.get(key)
                break
        data_list = seq if isinstance(seq, list) else []
    elif isinstance(data, list):
        data_list = data
    else:
        data_list = []
    normalized: list[dict] = []
    for item in data_list:
        if not isinstance(item, dict):
            continue
        entry: dict[str, object] = {}
        for key in (
            "avgPrice",
            "executedQty",
            "origQty",
            "price",
            "time",
            "updateTime",
            "orderId",
            "side",
            "symbol",
            "positionSide",
            "status",
            "type",
        ):
            if key in item:
                entry[key] = item[key]
        normalized.append(entry)
    return normalized


def clamp_futures_leverage(self, symbol: str, leverage: int | None = None) -> int:
    sym = str(symbol or "").upper()
    max_futures_leverage = max(1, int(getattr(self, "_max_futures_leverage_constant", 150) or 150))
    desired = leverage if leverage is not None else getattr(self, "_requested_default_leverage", getattr(self, "_default_leverage", 5))
    try:
        desired_int = int(float(desired))
    except Exception:
        desired_int = 1
    if desired_int < 1:
        desired_int = 1
    if desired_int > max_futures_leverage:
        desired_int = max_futures_leverage
    account_label = str(getattr(self, "account_type", "") or "").upper()
    if not account_label.startswith("FUT"):
        return desired_int
    max_allowed = self.get_futures_max_leverage(sym) if sym else max_futures_leverage
    effective = max(1, min(desired_int, max_allowed or max_futures_leverage))
    if effective < desired_int and sym:
        notified = getattr(self, "_leverage_cap_notified", set())
        if sym not in notified:
            try:
                self._log(f"{sym} max futures leverage {max_allowed}x; requested {desired_int}x -> using {effective}x.", lvl="warn")
            except Exception:
                try:
                    print(f"[BinanceWrapper] {sym} leverage limited to {effective}x (requested {desired_int}x).")
                except Exception:
                    pass
            notified.add(sym)
            self._leverage_cap_notified = notified
    return effective


def get_base_quote_assets(self, symbol: str):
    if self.account_type == "FUTURES":
        info = self.get_futures_symbol_info(symbol)
        return info.get("baseAsset"), info.get("quoteAsset")
    info = self.get_symbol_info_spot(symbol)
    return info.get("baseAsset"), info.get("quoteAsset")


def bind_binance_exchange_metadata(wrapper_cls, *, max_futures_leverage: int = 150):
    wrapper_cls.fetch_symbols = fetch_symbols
    wrapper_cls.get_symbol_info_spot = get_symbol_info_spot
    wrapper_cls.get_symbol_quote_precision_spot = get_symbol_quote_precision_spot
    wrapper_cls.get_spot_symbol_filters = get_spot_symbol_filters
    wrapper_cls.get_futures_exchange_info = get_futures_exchange_info
    wrapper_cls.get_futures_symbol_info = get_futures_symbol_info
    wrapper_cls.get_futures_symbol_filters = get_futures_symbol_filters
    wrapper_cls.get_futures_max_leverage = get_futures_max_leverage
    wrapper_cls.get_recent_force_orders = get_recent_force_orders
    wrapper_cls.clamp_futures_leverage = clamp_futures_leverage
    wrapper_cls.get_base_quote_assets = get_base_quote_assets
    wrapper_cls._max_futures_leverage_constant = max(1, int(max_futures_leverage or 150))
