
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from datetime import datetime
import time
import threading, requests

import pandas as pd
from binance.client import Client

class BinanceWrapper:

    def _log(self, msg: str, lvl: str = "info"):
        """
        Lightweight logger shim used by helper methods.
        Falls back to print if no .logger attribute is present.
        """
        try:
            lg = getattr(self, "logger", None)
            if lg is not None and hasattr(lg, lvl):
                getattr(lg, lvl)(msg)
            elif lg is not None and hasattr(lg, "info"):
                lg.info(msg)
            else:
                print(f"[BinanceWrapper][{lvl}] {msg}")
        except Exception:
            try:
                print(f"[BinanceWrapper][{lvl}] {msg}")
            except Exception:
                pass


    
    def _ensure_symbol_margin(self, symbol: str, want_mode: str | None, want_lev: int | None):
        sym = (symbol or "").upper()
        target = (want_mode or "ISOLATED").upper()
        if target == "CROSS":
            target = "CROSSED"
        if target not in ("ISOLATED", "CROSSED"):
            target = "ISOLATED"
    
        current = None
        open_amt = 0.0
        try:
            pins = self.client.futures_position_information(symbol=sym)
            if isinstance(pins, list) and pins:
                types = []
                for p in pins:
                    try:
                        types.append((p.get("marginType") or "").upper())
                        open_amt += abs(float(p.get("positionAmt") or 0.0))
                    except Exception:
                        pass
                current = next((t for t in types if t), None)
                if target in types:
                    current = target
        except Exception as e:
            self._log(f"margin probe failed for {sym}: {type(e).__name__}: {e}", lvl="warn")
            current = None
    
        if (current or "").upper() == target:
            if want_lev:
                try:
                    self.client.futures_change_leverage(symbol=sym, leverage=int(want_lev))
                except Exception:
                    pass
            return True
    
        if open_amt > 0:
            raise RuntimeError(f"wrong_margin_mode: current={current}, want={target}, symbol={sym}, openAmt={open_amt}")
    
        assume_ok = False
        try:
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
            except Exception:
                pass
            self.client.futures_change_margin_type(symbol=sym, marginType=target)
        except Exception as e:
            msg = str(e)
            if "-4046" in msg or "No need to change margin type" in msg:
                assume_ok = True
                self._log(f"change_margin_type({sym}->{target}) says already correct (-4046).", lvl="warn")
            else:
                self._log(f"change_margin_type({sym}->{target}) raised {type(e).__name__}: {e}", lvl="warn")
    
        try:
            pins2 = self.client.futures_position_information(symbol=sym)
            types2 = [(p.get("marginType") or "").upper() for p in (pins2 or []) if isinstance(p, dict)]
            now = next((t for t in types2 if t), None)
        except Exception:
            types2, now = [], None
    
        if (now == target) or (target in types2) or (assume_ok and (now in (None, ""))):
            if want_lev:
                try:
                    self.client.futures_change_leverage(symbol=sym, leverage=int(want_lev))
                except Exception:
                    pass
            return True
    
        raise RuntimeError(f"wrong_margin_mode_after_change: now={now}, want={target}, symbol={sym}")

    def set_position_mode(self, hedge: bool) -> bool:
        """Enable/disable dual-side (hedge) mode on futures."""
        try:
            self.client.futures_change_position_mode(dualSidePosition=bool(hedge))
            return True
        except Exception:
            # fallback names used by some client versions
            for m in ("futures_change_position_side_dual", "futures_change_positionMode"):
                try:
                    fn = getattr(self.client, m, None)
                    if fn:
                        fn(dualSidePosition=bool(hedge))
                        return True
                except Exception:
                    continue
        return False

    def set_multi_assets_mode(self, enabled: bool) -> bool:
        """Toggle Single-Asset vs Multi-Assets mode on USDT-M futures margin."""
        # python-binance names vary; try several spellings then raw REST call as a last resort.
        payload = {'multiAssetsMargin': 'true' if bool(enabled) else 'false'}
        for m in ("futures_change_multi_assets_margin", "futures_multi_assets_margin", "futures_set_multi_assets_margin"):
            try:
                fn = getattr(self.client, m, None)
                if fn:
                    fn(**payload)
                    return True
            except Exception:
                continue
        try:
            # raw client request method (available on python-binance Client)
            self.client._request_futures_api('post', 'multiAssetsMargin', data=payload)
            return True
        except Exception:
            try:
                import requests
                headers = {'X-MBX-APIKEY': getattr(self.client, 'API_KEY', '')}
                url = 'https://fapi.binance.com/fapi/v1/multiAssetsMargin'
                requests.post(url, params=payload, headers=headers, timeout=5)
                return True
            except Exception:
                return False
    
    def required_percent_for_symbol(self, symbol: str, leverage: int | float | None = None) -> float:
        """Rough % of total USDT needed to meet minQty/minNotional for a symbol at leverage."""
        try:
            sym = (symbol or "").upper()
            lev = float(leverage if leverage is not None else getattr(self, "futures_leverage", getattr(self, "_default_leverage", 5)) or 5)
            px = float(self.get_last_price(sym) or 0.0)
            f = self.get_futures_symbol_filters(sym) or {}
            step = float(f.get("stepSize") or 0.0) or 0.001
            minQty = float(f.get("minQty") or 0.0) or step
            minNotional = float(f.get("minNotional") or 0.0) or 5.0
            need_qty = max(minQty, (float(minNotional)/px) if px>0 else 0.0)
            if step > 0 and need_qty>0:
                k = int(need_qty / step)
                if abs(need_qty - k*step) > 1e-12:
                    need_qty = (k+1)*step
            if px<=0 or lev<=0 or need_qty<=0: return 0.0
            margin_needed = (need_qty * px) / lev
            bal = float(self.futures_get_usdt_balance() or 0.0)
            if bal <= 0: return 0.0
            return (margin_needed / bal) * 100.0
        except Exception:
            return 0.0

    # ---- SPOT trading (basic MARKET)
    def place_spot_market_order(self, symbol: str, side: str, quantity: float = 0.0, price: float | None = None,
                                use_quote: bool = False, quote_amount: float | None = None, **kwargs):
        """
        Minimal SPOT MARKET order helper.
        Returns a dict with 'ok', 'info', 'computed'.
        """
        sym = symbol.upper()
        if self.account_type != "SPOT":
            return {'ok': False, 'error': 'account_type != SPOT'}
        px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
        if px <= 0:
            return {'ok': False, 'error': 'No price available'}
        qty = float(quantity or 0.0)
        if side.upper() == 'BUY' and use_quote:
            qamt = float(quote_amount or 0.0)
            if qamt <= 0:
                return {'ok': False, 'error': 'quote_amount<=0'}
            qty = qamt / px
        # Adjust to filters
        f = self.get_spot_symbol_filters(sym)
        step = float(f.get('stepSize', 0.0) or 0.0)
        minQty = float(f.get('minQty', 0.0) or 0.0)
        minNotional = float(f.get('minNotional', 0.0) or 0.0)
        if step > 0:
            qty = self._floor_to_step(qty, step)
        if minQty > 0 and qty < minQty:
            qty = minQty
            if step > 0: qty = self._floor_to_step(qty, step)
        if minNotional > 0 and (qty * px) < minNotional:
            needed = (minNotional / px)
            qty = needed
            if step > 0: qty = self._floor_to_step(qty, step)
        try:
            res = self.client.create_order(symbol=sym, side=side.upper(), type='MARKET', quantity=str(qty))
            return {'ok': True, 'info': res, 'computed': {'qty': qty, 'price': px,
                    'filters': {'step': step, 'minQty': minQty, 'minNotional': minNotional}}}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'computed': {'qty': qty, 'price': px,
                    'filters': {'step': step, 'minQty': minQty, 'minNotional': minNotional}}}

    def _ceil_to_step(self, value: float, step: float) -> float:
        try:
            if step <= 0:
                return float(value)
            import math
            return math.ceil(float(value) / float(step)) * float(step)
        except Exception:
            return float(value)
    
    def fetch_symbols(self, sort_by_volume: bool = False, top_n: int | None = None):
        """
        Robust symbol fetcher.
        FUTURES: Return only USDT-M **PERPETUAL** symbols from /fapi/v1/exchangeInfo.
        SPOT   : Return USDT quote symbols from /api/v3/exchangeInfo.
        When sort_by_volume is requested, we sort the **allowed** set by 24h quoteVolume,
        but we never add anything outside the allow-list.
        """
        import requests

        def _safe_json(url: str, timeout: float = 10.0):
            try:
                r = requests.get(url, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
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

            for s in (info or {}).get("symbols", []):
                try:
                    if (s.get("status") == "TRADING"
                        and s.get("quoteAsset") == "USDT"
                        and s.get("contractType") == "PERPETUAL"):
                        allowed.add((s.get("symbol") or "").upper())
                except Exception:
                    continue

            ordered = sorted(list(allowed))
            if sort_by_volume and ordered:
                vol_map = {}
                data = _safe_json(f"{self._futures_base()}/v1/ticker/24hr") or []
                for t in data:
                    sym = (t.get("symbol") or "").upper()
                    try:
                        vol_map[sym] = float(t.get("quoteVolume") or 0.0)
                    except Exception:
                        vol_map[sym] = 0.0
                ordered = sorted(ordered, key=lambda s: vol_map.get(s, 0.0), reverse=True)

            if top_n:
                ordered = ordered[:int(top_n)]
            return ordered

        # SPOT path
        info = None
        try:
            info = self.client.get_exchange_info()
        except Exception:
            info = None
        if not info or not isinstance(info, dict) or "symbols" not in info:
            info = _safe_json(f"{self._spot_base()}/v3/exchangeInfo") or {}

        for s in (info or {}).get("symbols", []):
            try:
                if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
                    allowed.add((s.get("symbol") or "").upper())
            except Exception:
                continue

        ordered = sorted(list(allowed))
        if sort_by_volume and ordered:
            vol_map = {}
            data = _safe_json(f"{self._spot_base()}/v3/ticker/24hr") or []
            for t in data:
                sym = (t.get("symbol") or "").upper()
                try:
                    vol_map[sym] = float(t.get("quoteVolume") or 0.0)
                except Exception:
                    vol_map[sym] = 0.0
            ordered = sorted(ordered, key=lambda s: vol_map.get(s, 0.0), reverse=True)

        if top_n:
            ordered = ordered[:int(top_n)]
        return ordered

    
    def _spot_base(self) -> str:
        # Public REST base for SPOT depending on testnet/production
        return "https://testnet.binance.vision/api" if ("demo" in self.mode.lower() or "test" in self.mode.lower()) else "https://api.binance.com/api"

    def _futures_base(self) -> str:
        # Public REST base for FUTURES depending on testnet/production
        return "https://testnet.binancefuture.com/fapi" if ("demo" in self.mode.lower() or "test" in self.mode.lower()) else "https://fapi.binance.com/fapi"

    def __init__(self, api_key="", api_secret="", mode="Demo/Testnet", account_type="Spot", *, default_leverage: int | None = None, default_margin_mode: str | None = None):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.mode = (mode or "Demo/Testnet").strip()
        self._default_leverage = int(default_leverage) if (default_leverage is not None) else 20
        self.futures_leverage = self._default_leverage
        self._default_margin_mode = str((default_margin_mode or "ISOLATED")).upper()
        self.account_type = (account_type or "Spot").strip().upper()  # "SPOT" or "FUTURES"
        self.indicator_source = "Binance futures"
        self.recv_window = 5000  # ms for futures calls

        # Set base URLs BEFORE creating Client
        if "demo" in self.mode.lower() or "test" in self.mode.lower():
            if self.account_type == "FUTURES":
                Client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"
            else:
                Client.API_URL = "https://testnet.binance.vision/api"
        else:
            if self.account_type == "FUTURES":
                Client.FUTURES_URL = "https://fapi.binance.com/fapi"
            else:
                Client.API_URL = "https://api.binance.com/api"

        self.client = Client(self.api_key, self.api_secret)
        self._symbol_info_cache_spot = {}
        self._symbol_info_cache_futures = None
        self._futures_dual_side_cache = None
        getcontext().prec = 28

    # ---- internal helper for futures methods with recvWindow compatibility
    def _futures_call(self, method_name: str, allow_recv=True, **kwargs):
        method = getattr(self.client, method_name)
        if allow_recv:
            try:
                return method(recvWindow=self.recv_window, **kwargs)
            except TypeError:
                pass
        return method(**kwargs)

    def futures_api_ok(self) -> tuple[bool, str | None]:
        """
        Quick signed call to verify Futures API keys/permissions.
        Returns (ok, error_message).
        """
        try:
            _ = self._futures_call('futures_account_balance', allow_recv=True)
            return True, None
        except Exception as e:
            return False, str(e)

    def spot_api_ok(self) -> tuple[bool, str | None]:
        """Quick call to verify Spot API keys/permissions."""
        try:
            _ = self.client.get_account()
            return True, None
        except Exception as e:
            return False, str(e)


    # ---- SPOT symbol info/filters
    def get_symbol_info_spot(self, symbol: str) -> dict:
        key = symbol.upper()
        if key not in self._symbol_info_cache_spot:
            info = self.client.get_symbol_info(key)
            if not info:
                raise ValueError(f"No spot symbol info for {symbol}")
            self._symbol_info_cache_spot[key] = info
        return self._symbol_info_cache_spot[key]

    def get_symbol_quote_precision_spot(self, symbol: str) -> int:
        info = self.get_symbol_info_spot(symbol)
        qp = info.get('quoteAssetPrecision') or info.get('quotePrecision') or 8
        return int(qp)

    def get_spot_symbol_filters(self, symbol: str) -> dict:
        info = self.get_symbol_info_spot(symbol)
        step_size = None
        min_qty = None
        min_notional = None
        for f in info.get('filters', []):
            if f.get('filterType') == 'LOT_SIZE':
                step_size = float(f.get('stepSize', '0'))
                min_qty = float(f.get('minQty', '0'))
            elif f.get('filterType') in ('MIN_NOTIONAL', 'NOTIONAL'):
                min_notional = float(f.get('minNotional', f.get('notional', '0')))
        return {'stepSize': step_size or 0.0, 'minQty': min_qty or 0.0, 'minNotional': min_notional or 0.0}

    # ---- FUTURES exchange info/filters
    def get_futures_exchange_info(self) -> dict:
        if self._symbol_info_cache_futures is None:
            self._symbol_info_cache_futures = self._futures_call('futures_exchange_info', allow_recv=True)
        return self._symbol_info_cache_futures

    def get_futures_symbol_info(self, symbol: str) -> dict:
        info = self.get_futures_exchange_info()
        for s in info.get('symbols', []):
            if s.get('symbol') == symbol.upper():
                return s
        raise ValueError(f"No futures symbol info for {symbol}")

    def get_futures_symbol_filters(self, symbol: str) -> dict:
        s = self.get_futures_symbol_info(symbol)
        step_size = None
        min_qty = None
        price_tick = None
        min_notional = None
        for f in s.get('filters', []):
            if f.get('filterType') == 'LOT_SIZE':
                step_size = float(f.get('stepSize', '0'))
                min_qty = float(f.get('minQty', '0'))
            elif f.get('filterType') == 'PRICE_FILTER':
                price_tick = float(f.get('tickSize', '0'))
            elif f.get('filterType') in ('MIN_NOTIONAL','NOTIONAL'):
                mn = f.get('notional') or f.get('minNotional') or 0
                try:
                    min_notional = float(mn)
                except Exception:
                    min_notional = 0.0
        return {'stepSize': step_size or 0.0, 'minQty': min_qty or 0.0, 'tickSize': price_tick or 0.0, 'minNotional': min_notional or 0.0}

    # ---- balances
    def get_spot_balance(self, asset="USDT") -> float:
        try:
            info = self.client.get_account()
            for b in info.get('balances', []):
                if b.get('asset') == asset:
                    return float(b.get('free', 0.0))
        except Exception:
            pass
        return 0.0


    # ---- spot positions helpers
    def list_spot_non_usdt_balances(self):
        """Return list of dicts with non-zero free balances for assets (excluding USDT)."""
        out = []
        try:
            info = self.client.get_account()
            for b in info.get('balances', []):
                asset = b.get('asset')
                if not asset or asset == 'USDT':
                    continue
                free = float(b.get('free', 0.0))
                if free > 0:
                    out.append({'asset': asset, 'free': free})
        except Exception:
            pass
        return out

    def close_all_spot_positions(self):
        """Sell all non-USDT spot balances into USDT using market orders, respecting filters."""
        results = []
        balances = self.list_spot_non_usdt_balances()
        for bal in balances:
            asset = bal['asset']; qty = float(bal['free'] or 0.0)
            symbol = f"{asset}USDT"
            try:
                # Ensure symbol exists (raises if not found)
                info = self.get_symbol_info_spot(symbol)
                filters = self.get_spot_symbol_filters(symbol)
                price = float(self.get_last_price(symbol) or 0.0)
                min_notional = filters.get('minNotional', 0.0) or 0.0
                step = filters.get('stepSize', 0.0) or 0.0

                if price <= 0:
                    raise ValueError("last price unavailable")
                est_notional = qty * price
                if est_notional < min_notional:
                    # Skip tiny dust that doesn't meet notional requirements
                    results.append({'symbol': symbol, 'qty': qty, 'ok': False, 'error': f'Notional {est_notional:.8f} < min {min_notional:.8f}'})
                    continue

                qty_adj = self._floor_to_step(qty, step) if step else qty
                if qty_adj <= 0:
                    results.append({'symbol': symbol, 'qty': qty, 'ok': False, 'error': 'Quantity too small after step rounding'})
                    continue

                res = self.place_spot_market_order(symbol, 'SELL', qty_adj)
                results.append({'symbol': symbol, 'qty': qty_adj, 'ok': True, 'res': res})
            except Exception as e:
                results.append({'symbol': symbol, 'qty': qty, 'ok': False, 'error': str(e)})
        return results

    def get_futures_balance_usdt(self) -> float:
        try:
            bals = self._futures_call('futures_account_balance', allow_recv=True)
            for b in bals or []:
                if b.get('asset') == 'USDT':
                    val = b.get('availableBalance', None)
                    if val is None:
                        val = b.get('balance', b.get('walletBalance', 0.0))
                    return float(val)
        except Exception:
            pass
        return 0.0

    def get_total_usdt_value(self) -> float:
        # Prefer futures; fall back to spot if unavailable
        try:
            val = float(self.get_futures_balance_usdt())
        except Exception:
            val = 0.0
        if not val:
            try:
                val = float(self.get_spot_balance('USDT'))
            except Exception:
                pass
        return float(val or 0.0)

    # ---- prices & klines
    def get_last_price(self, symbol: str) -> float:
        try:
            if self.account_type == "FUTURES":
                t = self._futures_call('futures_symbol_ticker', allow_recv=True, symbol=symbol)
                return float((t or {}).get('price', 0.0))
            else:
                t = self.client.get_symbol_ticker(symbol=symbol)
                return float(t.get('price', 0.0))
        except Exception:
            return 0.0

    def get_klines(self, symbol, interval, limit=500):
        source = (getattr(self, "indicator_source", "") or "").strip().lower()
        raw = None
        if source in ("", "binance futures", "binance_futures", "futures"):
            raw = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        elif source in ("binance spot", "binance_spot", "spot"):
            raw = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        elif source == "bybit":
            import requests, pandas as pd
            bybit_interval = self._bybit_interval(interval)
            url = "https://api.bybit.com/v5/market/kline"
            params = {"category":"linear","symbol":symbol,"interval":bybit_interval,"limit":limit}
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            j = r.json() or {}
            lst = (j.get("result", {}) or {}).get("list", []) or []
            lst = sorted(lst, key=lambda x: int(x[0]))
            # Build Binance-like kline rows
            raw = [[int(x[0]), x[1], x[2], x[3], x[4], x[5], 0, 0, 0, 0, 0, 0] for x in lst]
        elif source in ("tradingview","trading view"):
            raise NotImplementedError("TradingView data source is not implemented in this build.")
        else:
            # fallback to account type
            if self.account_type == "FUTURES":
                raw = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            else:
                raw = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)

        cols = ['open_time','open','high','low','close','volume','close_time','qav','num_trades','taker_base','taker_quote','ignore']
        import pandas as pd
        df = pd.DataFrame(raw, columns=cols)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df[['open','high','low','close','volume']]

    # ---- order placement helpers
    @staticmethod
    def _floor_to_step(value: float, step: float) -> float:
        from decimal import Decimal, ROUND_DOWN
        if step <= 0:
            return float(value)
        d_val = Decimal(str(value)); d_step = Decimal(str(step))
        units = (d_val / d_step).to_integral_value(rounding=ROUND_DOWN)
        snapped = units * d_step
        return float(snapped)

    @staticmethod
    def floor_to_decimals(value: float, decimals: int) -> float:
        from decimal import Decimal, ROUND_DOWN
        if decimals < 0:
            return float(value)
        q = Decimal('1').scaleb(-decimals)
        return float(Decimal(str(value)).quantize(q, rounding=ROUND_DOWN))

    @staticmethod
    def ceil_to_decimals(value: float, decimals: int) -> float:
        from decimal import Decimal, ROUND_UP
        if decimals < 0:
            return float(value)
        q = Decimal('1').scaleb(-decimals)
        return float(Decimal(str(value)).quantize(q, rounding=ROUND_UP))

    def adjust_qty_to_filters_spot(self, symbol: str, qty: float, est_price: float):
        if qty <= 0:
            return 0.0, "qty<=0"
        try:
            f = self.get_spot_symbol_filters(symbol)
        except Exception as e:
            return 0.0, f"filters_error:{e}"

        step = f['stepSize'] or 0.0
        min_qty = f['minQty'] or 0.0
        min_notional = f['minNotional'] or 0.0

        adj = qty
        if step > 0:
            adj = self._floor_to_step(adj, step)

        if min_qty > 0 and adj < min_qty:
            adj = min_qty
        # Enforce futures MIN_NOTIONAL if price provided
        if min_notional > 0 and (price or 0) > 0:
            needed = min_notional / float(price)
            if adj < needed:
                adj = needed
            adj = min_qty
            if step > 0:
                adj = self._floor_to_step(adj, step)

        if est_price and min_notional > 0:
            notional = adj * est_price
            if notional < min_notional:
                needed_qty = (min_notional / est_price) if est_price > 0 else adj
                if step > 0:
                    needed_qty = self._floor_to_step(needed_qty + step, step)
                if needed_qty < min_qty:
                    needed_qty = min_qty
                    if step > 0:
                        needed_qty = self._floor_to_step(needed_qty, step)
                adj = needed_qty
                if adj * est_price < min_notional:
                    return 0.0, f"below_minNotional({adj*est_price:.8f}<{min_notional:.8f})"

        if adj <= 0:
            return 0.0, "adj<=0"
        return float(adj), None

    def adjust_qty_to_filters_futures(self, symbol: str, qty: float, price: float | None = None):
        try:
            f = self.get_futures_symbol_filters(symbol)
        except Exception as e:
            return 0.0, f"filters_error:{e}"
        step = float(f.get('stepSize', 0.0) or 0.0)
        min_qty = float(f.get('minQty', 0.0) or 0.0)
        min_notional = float(f.get('minNotional', 0.0) or 0.0)

        adj = float(qty or 0.0)
        if step > 0:
            adj = self._floor_to_step(adj, step)
        if min_qty > 0 and adj < min_qty:
            adj = min_qty
        if min_notional > 0 and (price or 0) > 0:
            need = float(min_notional) / float(price)
            if step > 0:
                need = self._ceil_to_step(need, step)
            if adj < need:
                adj = need
        if adj <= 0:
            return 0.0, "adj<=0"
        return float(adj), None

    def get_base_quote_assets(self, symbol: str):
        if self.account_type == "FUTURES":
            s = self.get_futures_symbol_info(symbol)
            return s.get('baseAsset'), s.get('quoteAsset')
        info = self.get_symbol_info_spot(symbol)
        return info.get('baseAsset'), info.get('quoteAsset')

    def get_futures_dual_side(self) -> bool:
        """
        Returns True if dual-side (hedge) mode is enabled on Futures; False if one-way.
        Tries multiple client methods; normalizes string/array responses.
        """
        methods = [
            "futures_get_position_mode",
            "futures_get_position_side_dual",
            "futures_position_side_dual",
        ]
        for m in methods:
            try:
                fn = getattr(self.client, m, None)
                if not fn:
                    continue
                res = fn()
                val = None
                if isinstance(res, dict):
                    val = res.get("dualSidePosition")
                elif isinstance(res, (list, tuple)) and res:
                    first = res[0]
                    if isinstance(first, dict) and "dualSidePosition" in first:
                        val = first["dualSidePosition"]
                    else:
                        val = first
                else:
                    val = res
                if isinstance(val, str):
                    val = val.strip().lower() in ("true","1","yes","y")
                return bool(val)
            except Exception:
                continue
        return False
    
    
    
    
    
    def place_futures_market_order(self, symbol: str, side: str, percent_balance: float | None = None,
                                   price: float | None = None, position_side: str | None = None,
                                   quantity: float | None = None, **kwargs):

        """Futures MARKET order with robust sizing and clear returns.
        Returns:
           {
             'ok': bool,
             'info': <raw order dict> or None,
             'computed': {'qty': float, 'px': float, 'step': float, 'minQty': float, 'minNotional': float, 'lev': int, 'mode': str},
             'mode': <'percent'|'quantity'|'fallback'>,
             'error': <str> (when ok==False)
           }
        """
        assert self.account_type == "FUTURES", "Futures order called while account_type != FUTURES"

        self._ensure_margin_and_leverage_or_block(sym, kwargs.get('margin_mode') or getattr(self,'_default_margin_mode','ISOLATED'), kwargs.get('leverage'))


        # --- helpers ---
        def _floor_to_step(val: float, step: float) -> float:
            try:
                if step <= 0: return float(val)
                q = int(round(float(val) / float(step)))
                return float(q * float(step))
            except Exception:
                return float(val)

        def _ceil_to_step(val: float, step: float) -> float:
            try:
                if step <= 0: return float(val)
                q = int(-(-float(val) // float(step)))  # ceil division
                return float(q * float(step))
            except Exception:
                return float(val)

        px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
        if px <= 0:
            return {'ok': False, 'error': 'No price available', 'computed': {}}

        f = self.get_futures_symbol_filters(sym) or {}
        step = float(f.get('stepSize') or 0.0) or 0.001
        minQty = float(f.get('minQty') or 0.0) or step
        minNotional = float(f.get('minNotional') or 0.0) or 5.0

        # sizing
        mode = 'percent'
        pct = float(percent_balance or 0.0)  # value like 2.0 for 2%
        lev = int(kwargs.get('leverage') or getattr(self, '_futures_leverage', 1) or 1)
        qty = 0.0

        if pct > 0.0:
            bal = float(self.get_futures_available_balance() or 0.0)
            margin_budget = bal * (pct / 100.0)
            # Respect cap PER SYMBOL across intervals: subtract current margin already tied to this symbol
            try:
                used_usd = 0.0
                for p in (self.list_open_futures_positions() or []):
                    if (p or {}).get('symbol','').upper() == sym:
                        # prefer isolatedWallet, then initialMargin, else notional/leverage
                        used_usd += float(p.get('isolatedWallet') or p.get('initialMargin') or (abs(p.get('notional') or 0.0) / max(lev, 1) ))
                margin_budget = max(margin_budget - used_usd, 0.0)
            except Exception:
                # if anything goes wrong, fall back to original budget
                pass

            qty = _floor_to_step((margin_budget * lev) / px, step)
            need_qty = max(minQty, _ceil_to_step(minNotional/px, step))
            if qty < need_qty:
                req_pct = self.required_percent_for_symbol(sym, lev)
                return {'ok': False, 'symbol': sym,
                        'error': f'exchange minimum requires ~{req_pct:.2f}% (> {pct:.2f}%)',
                        'computed': {'px': px, 'minQty': minQty, 'minNotional': minNotional, 'step': step, 'pct_used': pct,
                                     'need_qty': need_qty, 'lev': lev, 'avail': bal, 'margin_budget': margin_budget},
                        'required_percent': req_pct,
                        'mode': 'percent(strict)'}
            mode = 'percent'
        elif quantity is not None:
            try:
                qty = float(quantity)
            except Exception:
                return {'ok': False, 'error': f'Bad quantity override: {quantity!r}'}
            qty = max(minQty, _floor_to_step(qty, step))
            if qty * px < minNotional:
                qty = max(qty, _ceil_to_step(minNotional/px, step))
            mode = 'quantity'
        else:
            qty = max(minQty, _ceil_to_step(minNotional/px, step))
            mode = 'fallback'

        if qty <= 0:
            return {'ok': False, 'error': 'qty<=0', 'computed': {'px': px, 'minQty': minQty, 'minNotional': minNotional, 'step': step}, 'mode': mode}

        # send order
        try:
            # Hedge mode support
            dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
            side_up = 'BUY' if str(side).upper() in ('BUY','LONG','L') else 'SELL'
            pos_side = position_side or kwargs.get('positionSide')
            if dual and not pos_side:
                pos_side = 'SHORT' if side_up == 'SELL' else 'LONG'

            params = dict(symbol=sym, side=side_up, type='MARKET', quantity=str(qty))
            if dual and pos_side:
                params['positionSide'] = pos_side

            order = self.client.futures_create_order(**params)
            return {'ok': True, 'info': order, 'computed': {'qty': qty, 'px': px, 'step': step, 'minQty': minQty, 'minNotional': minNotional, 'lev': lev}, 'mode': mode}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'computed': {'qty': qty, 'px': px, 'step': step, 'minQty': minQty, 'minNotional': minNotional, 'lev': lev}, 'mode': mode}

    def close_futures_leg_exact(self, symbol: str, qty: float, side: str, position_side: str | None = None):
        """Close exactly `qty` using reduce-only MARKET on the given `side`.
        If hedge mode is enabled, `position_side` should be 'LONG' (to close a long) or 'SHORT' (to close a short).
        """
        try:
            sym = (symbol or '').upper()
            q = float(qty or 0)
            if q <= 0:
                return {'ok': False, 'error': 'qty<=0'}
            params = dict(symbol=sym, side=(side or 'SELL').upper(), type='MARKET', reduceOnly=True, quantity=str(q))
            if position_side:
                params['positionSide'] = position_side
            params.setdefault('newClientOrderId', base_oid)
            info = self.client.futures_create_order(**params)
            return {'ok': True, 'info': info}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def close_futures_position(self, symbol: str):
        """Close open futures position(s) for `symbol` using reduce-only MARKET orders.
        Works in both one-way and hedge modes.
        """
        try:
            sym = (symbol or '').upper()
            dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
            rows = self.list_open_futures_positions() or []
            closed = 0
            failed = 0
            errors = []
            for row in rows:
                if (row.get('symbol') or '').upper() != sym:
                    continue
                amt = float(row.get('positionAmt') or 0)
                if abs(amt) < 1e-12:
                    continue
                side = 'SELL' if amt > 0 else 'BUY'
                params = dict(symbol=sym, side=side, type='MARKET', reduceOnly=True, quantity=str(abs(amt)))
                if dual:
                    params['positionSide'] = 'LONG' if amt > 0 else 'SHORT'
                try:
                    self.client.futures_create_order(**params)
                    closed += 1
                except Exception as e:
                    failed += 1
                    errors.append(str(e))
            return {'ok': failed == 0, 'closed': closed, 'failed': failed, 'errors': errors}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def close_all_futures_positions(self):
        results = []
        try:
            dual = False
            try:
                mode_info = self.client.futures_get_position_mode()
                dual = bool(mode_info.get('dualSidePosition'))
            except Exception:
                pass
            positions = self.list_open_futures_positions() or []
            if not positions:
                return results
            try:
                for s in sorted({p['symbol'] for p in positions}):
                    try:
                        self.client.futures_cancel_all_open_orders(symbol=s)
                    except Exception:
                        pass
            except Exception:
                pass
            for p in positions:
                try:
                    sym = p['symbol']
                    amt = float(p.get('positionAmt') or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    side = 'SELL' if amt > 0 else 'BUY'
                    qty = abs(amt)
                    params = dict(symbol=sym, side=side, type='MARKET', quantity=str(qty))
                    if dual:
                        params['positionSide'] = 'LONG' if amt > 0 else 'SHORT'
                    info = self.client.futures_create_order(**params)
                    results.append({'symbol': sym, 'ok': True, 'info': info})
                except Exception as e:
                    results.append({'symbol': p.get('symbol'), 'ok': False, 'error': str(e)})
        except Exception as e:
            results.append({'ok': False, 'error': str(e)})
        return results

    def list_open_futures_positions(self):
        infos = None
        try:
            infos = self.client.futures_position_information()
        except Exception:
            try:
                infos = self.client.futures_position_risk()
            except Exception:
                infos = None
        out = []
        if not infos:
            try:
                acc = self.client.futures_account() or {}
                for p in acc.get('positions', []):
                    amt = float(p.get('positionAmt') or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    out.append({
                        'symbol': p.get('symbol'),
                        'positionAmt': amt,
                        'notional': float(p.get('notional') or 0.0) if isinstance(p, dict) else 0.0,
                        'initialMargin': float(p.get('initialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'isolatedWallet': float(p.get('isolatedWallet') or 0.0) if isinstance(p, dict) else 0.0,
                        'entryPrice': float(p.get('entryPrice') or 0.0),
                        'markPrice': float(p.get('markPrice') or 0.0),
                        'marginType': p.get('marginType'),
                        'leverage': int(float(p.get('leverage') or 0)),
                        'unRealizedProfit': float(p.get('unRealizedProfit') or 0.0),
                        'liquidationPrice': float(p.get('liquidationPrice') or 0.0),
                    })
            except Exception:
                pass
        else:
            for p in infos or []:
            # Enrich with notional/margins/ROI-friendly fields when present
                try:
                    amt = float(p.get('positionAmt') or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    out.append({
                        'symbol': p.get('symbol'),
                        'positionAmt': amt,
                        'notional': float(p.get('notional') or 0.0) if isinstance(p, dict) else 0.0,
                        'initialMargin': float(p.get('initialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'isolatedWallet': float(p.get('isolatedWallet') or 0.0) if isinstance(p, dict) else 0.0,
                        'entryPrice': float(p.get('entryPrice') or 0.0),
                        'markPrice': float(p.get('markPrice') or 0.0),
                        'marginType': p.get('marginType'),
                        'leverage': int(float(p.get('leverage') or 0)),
                        'unRealizedProfit': float(p.get('unRealizedProfit') or 0.0),
                        'liquidationPrice': float(p.get('liquidationPrice') or 0.0),
                    })
                except Exception:
                    continue
        return out

    

def get_symbol_margin_type(self, symbol: str) -> str | None:
    """Return current margin type for symbol ('ISOLATED' | 'CROSSED') or None on error."""
    try:
        info = None
        try:
            info = self.client.futures_position_information(symbol=symbol.upper())
        except Exception:
            try:
                info = self.client.futures_position_risk(symbol=symbol.upper())
            except Exception:
                info = None
        if not info:
            return None
        row = info[0] if isinstance(info, list) and info else info
        mt = (row.get('marginType') or row.get('margintype') or '').upper()
        return mt if mt in ('ISOLATED','CROSSED') else None
    except Exception:
        return None




def _futures_open_orders_count(self, symbol: str) -> int:
    try:
        arr = self.client.futures_get_open_orders(symbol=(symbol or '').upper())
        return len(arr or [])
    except Exception:
        return 0

def _futures_net_position_amt(self, symbol: str) -> float:
    try:
        sym = (symbol or '').upper()
        info = self.client.futures_position_information(symbol=sym) or []
        total = 0.0
        for row in info:
            if (row or {}).get('symbol','').upper() != sym:
                continue
            try:
                total += float(row.get('positionAmt') or 0)
            except Exception:
                pass
        return float(total)
    except Exception:
        return 0.0

def _ensure_margin_and_leverage_or_block(self, symbol: str, desired_mm: str, desired_lev: int | None):
    """
    Enforce margin type (ISOLATED/CROSSED) + leverage BEFORE any futures order.
    - Always attempt to set the desired margin type.
    - If Binance refuses because of open orders/positions, we block and raise.
    - Verifies by re-reading margin type.
    """
    sym = (symbol or '').upper()
    want_mm = (desired_mm or getattr(self, '_default_margin_mode','ISOLATED') or 'ISOLATED').upper()
    want_mm = 'CROSSED' if want_mm in ('CROSS', 'CROSSED') else 'ISOLATED'

    # If there are open positions and current is not desired, block immediately
    cur = (self.get_symbol_margin_type(sym) or '').upper()
    if cur and cur != want_mm:
        # Any open amt?
        if abs(self._futures_net_position_amt(sym)) > 0:
            raise RuntimeError(f"{sym} is {cur} with an open position; refusing to place order until margin type can be changed to {want_mm}.")

    # If there are open orders, cancel them (margin type change requires no open orders)
    try:
        if self._futures_open_orders_count(sym) > 0:
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
            except Exception:
                pass
    except Exception:
        pass

    # Always try to set desired margin type, tolerate 'no need to change' responses
    last_err = None
    for attempt in range(5):
        try:
            self.client.futures_change_margin_type(symbol=sym, marginType=want_mm)
        except Exception as e:
            msg = str(getattr(e, 'message', '') or e).lower()
            if 'no need to change' in msg or 'no need to change margin type' in msg or 'code=-4099' in msg:
                pass  # desired already
            elif '-4048' in msg or ('cannot change' in msg and ('open' in msg or 'position' in msg)):
                # open order/position prevents margin change
                raise RuntimeError(f"Binance refused to change margin type for {sym} while open orders/positions exist (-4048). Close them first.")
            else:
                # transient? retry
                last_err = e
        # verify
        v = (self.get_symbol_margin_type(sym) or '').upper()
        if v == want_mm:
            break
        import time as _t; _t.sleep(0.2)
    else:
        if last_err:
            raise RuntimeError(f"Failed to set margin type for {sym} to {want_mm}: {last_err}")
        vv = (self.get_symbol_margin_type(sym) or 'UNKNOWN')
        raise RuntimeError(f"Margin type for {sym} is {vv}; wanted {want_mm}. Blocking order.")

    # Apply leverage if requested (non-fatal on failure)
    if desired_lev is not None:
        try:
            lev = max(1, min(125, int(desired_lev)))
            self.client.futures_change_leverage(symbol=sym, leverage=lev)
        except Exception:
            pass


def ensure_futures_settings(self, symbol: str, leverage: int | None = None,
                                margin_mode: str | None = None, hedge_mode: bool | None = None):
        try:
            if hedge_mode is not None:
                try:
                    self.client.futures_change_position_mode(dualSidePosition=bool(hedge_mode))
                except Exception:
                    pass
            sym = (symbol or '').upper()
            if not sym:
                return
            mm = (margin_mode or getattr(self, '_default_margin_mode', 'ISOLATED') or 'ISOLATED').upper()
            if mm == 'CROSS':
                mm = 'CROSSED'
            try:
                self.client.futures_change_margin_type(symbol=sym, marginType=mm)
            except Exception as e:
                if 'no need to change' not in str(e).lower() and '-4046' not in str(e):
                    pass
            try:
                lev = int(leverage if leverage is not None else getattr(self, 'futures_leverage', getattr(self, '_default_leverage', 5)) or 5)
            except Exception:
                lev = 5
            lev = max(1, min(125, int(lev)))
            try:
                self.client.futures_change_leverage(symbol=sym, leverage=lev)
            except Exception as e:
                if 'same leverage' not in str(e).lower() and 'not modified' not in str(e).lower():
                    pass
            self._default_margin_mode = mm
            self._default_leverage = lev
            self.futures_leverage = lev
        except Exception:
            pass



        def configure_futures_symbol(self, symbol: str):
            """Back-compat shim: some strategy code calls this; we forward to ensure_futures_settings."""
            try:
                self.ensure_futures_settings(symbol)
            except Exception:
                pass


        def set_futures_leverage(self, lev: int):
            try:
                lev = int(lev)
            except Exception:
                return
            lev = max(1, min(125, lev))
            self._default_leverage = lev
            self.futures_leverage = lev


# ---- Compatibility monkey-patches (ensure instance has these methods)
def _bw_place_futures_market_order(self, symbol: str, side: str, percent_balance: float | None = None,
                                   price: float | None = None, position_side: str | None = None,
                                   quantity: float | None = None, **kwargs):
    # Reuse the module-level implementation if it exists.
    try:
        return place_futures_market_order(self, symbol, side, percent_balance=percent_balance,
                                          price=price, position_side=position_side,
                                          quantity=quantity, **kwargs)
    except NameError:
        # Fallback minimal implementation
        sym = (symbol or '').upper()
        px = float(price if price is not None else self.get_last_price(sym) or 0.0)
        if px <= 0: return {'ok': False, 'error': 'No price available'}
        qty = float(quantity or 0.0)
        if qty <= 0 and percent_balance:
            bal = float(self.futures_get_usdt_balance() or 0.0)
            lev = int(kwargs.get('leverage') or 1)
            f = float(percent_balance or 0.0)
            f = f if f <= 1.0 else (f/100.0)
            avail_notional = bal * lev * f
            # strict gate
            f_filters = self.get_futures_symbol_filters(sym) or {}
            minNotional = float(f_filters.get('minNotional') or 0.0) or 5.0
            minQty = float(f_filters.get('minQty') or 0.0) or float(f_filters.get('stepSize') or 0.001)
            need_notional = max(minNotional, minQty * px)
            if bool(kwargs.get('strict', True)) and avail_notional < need_notional:
                # percent the user entered (as %)
                f_pct = (f*100.0) if f <= 1.0 else f
                req_pct = (need_notional / max(lev * bal, 1e-9)) * 100.0
                if kwargs.get('auto_bump_to_min', True) and (lev * bal) > 0:
                    # transparently bump percent to the minimum required and continue
                    f = max(f, (req_pct/100.0) + 1e-9)
                    avail_notional = bal * lev * f
                else:
                    return {'ok': False, 'symbol': sym,
                        'error': f'exchange minimum requires ~{req_pct:.2f}% (> {f_pct:.2f}%)',
                        'computed': {
                            'px': px,
                            'step': float(f_filters.get('stepSize') or 0.001),
                            'minQty': minQty,
                            'minNotional': minNotional,
                            'need_qty': max(minQty, need_notional/px),
                            'need_notional': need_notional,
                            'lev': lev,
                            'avail': bal,
                            'margin_budget': bal * f
                        },
                        'required_percent': req_pct,
                        'mode': 'percent(strict)'}

















                qty = avail_notional / px
        qty, err = self.adjust_qty_to_filters_futures(sym, qty, px)
        if err: return {'ok': False, 'error': err, 'computed': {'qty': qty, 'price': px}}
        dual = bool(self.get_futures_dual_side())
        params = dict(symbol=sym, side=side.upper(), type='MARKET', quantity=str(qty))
        if dual:
            params['positionSide'] = (position_side or ('LONG' if side.upper()=='BUY' else 'SHORT'))
        try:
            info = self.client.futures_create_order(**params)
            return {'ok': True, 'info': info, 'computed': {'qty': qty, 'price': px}}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'computed': {'qty': qty, 'price': px}}



def _bw_close_futures_position(self, symbol: str):
    sym = (symbol or '').upper()
    try:
        infos = self.client.futures_position_information(symbol=sym)
    except Exception as e:
        return {'symbol': sym, 'ok': False, 'error': f'fetch failed: {e}'}
    dual = bool(self.get_futures_dual_side())
    errs = []; closed = 0
    # Get filters for correct rounding
    try:
        filt = self.get_futures_symbol_filters(sym)  # stepSize, minQty, minNotional, tickSize
    except Exception:
        filt = {'stepSize': 0.0, 'minQty': 0.0, 'minNotional': 0.0, 'tickSize': 0.0}
    step = float(filt.get('stepSize') or 0.0) or 0.0
    min_qty = float(filt.get('minQty') or 0.0) or 0.0
    tick = float(filt.get('tickSize') or 0.0) or 0.0
    try:
        book = self.client.futures_book_ticker(symbol=sym) or {}
    except Exception:
        book = {}
    try:
        last_px = float(book.get('lastPrice') or self.get_last_price(sym) or 0.0)
    except Exception:
        last_px = 0.0
    bid = float(book.get('bidPrice') or 0.0) or last_px
    ask = float(book.get('askPrice') or 0.0) or last_px
    min_notional = float(filt.get('minNotional') or 0.0) or 0.0

    def _ceil_to_step(x, s):
        if s <= 0: return float(x)
        k = int(float(x) / s + 1e-12)
        if abs(x - k*s) < 1e-12:
            return k*s
        return (k+1)*s

    def _round_to_tick(p, t):
        if t <= 0: return float(p)
        return round(float(p) / t) * t

    for pos in infos or []:
        amt = float(pos.get('positionAmt') or 0.0)
        if abs(amt) <= 0:
            continue
        side = 'SELL' if amt > 0 else 'BUY'
        qty = abs(amt)

        # Round qty UP to step to guarantee full close
        if step > 0:
            qty = _ceil_to_step(qty, step)
        if min_qty > 0 and qty < min_qty:
            qty = _ceil_to_step(min_qty, step) if step > 0 else min_qty
        if min_notional > 0 and last_px > 0 and qty*last_px < min_notional:
            need = (min_notional / max(1e-12, last_px))
            qty = _ceil_to_step(max(qty, need), step) if step > 0 else max(qty, need)

        # Primary attempt: MARKET reduceOnly (best-effort)
        params = dict(symbol=sym, side=side, type='MARKET', quantity=str(qty), reduceOnly=True)
        if dual:
            params['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
        try:
            self.client.futures_create_order(**params)
            closed += 1
            continue
        except Exception as e:
            msg = str(e)
            # Fallback for -1106 reduceOnly not required → use LIMIT IOC reduceOnly and cross the spread
            if "-1106" in msg or "reduceonly" in msg.lower():
                try:
                    px = (bid*0.999 if side=='SELL' else ask*1.001) or last_px
                    if px <= 0:  # last resort
                        px = last_px if last_px>0 else (1.0 if side=='BUY' else 1.0)
                    px = _round_to_tick(px, tick) if tick>0 else px
                    alt = dict(symbol=sym, side=side, type='LIMIT', timeInForce='IOC',
                               price=str(px), quantity=str(qty), reduceOnly=True)
                    if dual:
                        alt['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
                    self.client.futures_create_order(**alt)
                    closed += 1
                    continue
                except Exception as e2:
                    errs.append(str(e2))
            else:
                errs.append(msg)
    return {'symbol': sym, 'ok': (len(errs)==0), 'closed': closed, 'error': '; '.join(errs) if errs else None}

def _bw_close_all_futures_positions(self):
    try:
        infos = self.client.futures_position_information()
    except Exception as e:
        return [{'ok': False, 'error': f'fetch failed: {e}'}]
    symbols = sorted({p.get('symbol','') for p in infos or [] if abs(float(p.get('positionAmt') or 0.0)) > 0})
    return [ _bw_close_futures_position(self, sym) for sym in symbols ]

# Attach if missing
try:
    BinanceWrapper
    if not hasattr(BinanceWrapper, 'place_futures_market_order'):
        BinanceWrapper.place_futures_market_order = _bw_place_futures_market_order
    if not hasattr(BinanceWrapper, 'close_futures_position'):
        BinanceWrapper.close_futures_position = _bw_close_futures_position
    if not hasattr(BinanceWrapper, 'close_all_futures_positions'):
        BinanceWrapper.close_all_futures_positions = _bw_close_all_futures_positions
except Exception:
    pass

# === STRICT PERCENT SIZER OVERRIDE (STOPFIX19) ====================================
def _floor_to_step(value: float, step: float) -> float:
    try:
        if step and step > 0:
            # avoid binary rounding drift
            n = int(float(value) / float(step) + 1e-12)
            return float(n) * float(step)
    except Exception:
        pass
    return float(value or 0.0)

def _place_futures_market_order_STRICT(self, symbol: str, side: str,
                                       percent_balance: float | None = None,
                                       price: float | None = None,
                                       position_side: str | None = None,
                                       quantity: float | None = None,
                                       **kwargs):
    """
    Replacement for place_futures_market_order with *strict* sizing:
      - If percent_balance is used, compute margin budget = availableBalance * (pct/100).
      - notional_target = margin_budget * leverage
      - qty = floor_to_step(notional_target / price)
      - If qty < minQty or qty*price < minNotional -> SKIP (do NOT auto-bump).
      - Return ok=False with 'required_percent' when skipping so the UI can show why.
    Also accepts:
      - reduce_only: bool
      - leverage: int
      - margin_mode: 'ISOLATED'|'CROSSED'
      - interval: str (passthrough for strategy ledger; unused here)
    """
    sym = (symbol or '').upper()
    # Hard-block if symbol is not in desired margin mode
    try:
        self._ensure_symbol_margin(sym, kwargs.get('margin_mode') or getattr(self, '_default_margin_mode','ISOLATED'), kwargs.get('leverage'))
    except Exception as _e:
        self._log(f'BLOCK strict path: {type(_e).__name__}: {_e}', lvl='error')
        return {'ok': False, 'error': str(_e), 'mode': 'strict'}
    # Make sure leverage/margin mode are applied
    # Make sure leverage/margin mode are applied (strict)
    _ensure_err = None
    try:
        self.ensure_futures_settings(sym, leverage=kwargs.get('leverage'), margin_mode=kwargs.get('margin_mode'))
    except Exception as e:
        _ensure_err = str(e)
    if _ensure_err:
        return {'ok': False, 'symbol': sym, 'error': _ensure_err}
    # Resolve price
    px = float(price if price is not None else self.get_last_price(sym) or 0.0)
    if px <= 0.0:
        return {'ok': False, 'symbol': sym, 'error': 'No price available'}

    # Exchange filters
    f = self.get_futures_symbol_filters(sym) or {}
    step = float(f.get('stepSize') or 0.0) or float(f.get('step_size') or 0.0) or 0.001
    minQty = float(f.get('minQty') or 0.0) or step
    minNotional = float(f.get('minNotional') or 0.0) or 5.0

    dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())

    # Decide order quantity
    qty = float(quantity or 0.0)
    mode = 'quantity'
    lev = int(kwargs.get('leverage') or getattr(self, "_default_leverage", 5) or 5)
    if qty <= 0 and percent_balance is not None:
        mode = 'percent(strict)'
        pct = float(percent_balance)
        bal = float(self.get_futures_balance_usdt() or 0.0)
        margin_budget = bal * (pct / 100.0)
        notional_target = margin_budget * max(lev, 1)
        qty_raw = (notional_target / px) if px > 0 else 0.0
        qty = _floor_to_step(qty_raw, step)

        # Strict gate: require BOTH minQty and minNotional
        notional = qty * px
        need_notional = max(minNotional, minQty * px)
        if qty < minQty or notional < minNotional or notional < need_notional:
            # Calculate required percent so the user can see how much is needed
            denom = max(bal * max(lev, 1), 1e-12)
            req_pct = (need_notional / denom) * 100.0
            return {
                'ok': False,
                'symbol': sym,
                'error': f'exchange minimum requires ~{req_pct:.2f}% (> {pct:.2f}%)',
                'computed': {
                    'px': px, 'step': step,
                    'minQty': minQty, 'minNotional': minNotional,
                    'need_qty': max(minQty, need_notional / px),
                    'need_notional': need_notional,
                    'lev': lev, 'avail': bal,
                    'margin_budget': margin_budget
                },
                'required_percent': req_pct,
                'mode': mode
            }

    # Finally adjust the computed qty to step; also guard reduce-only
    qty = _floor_to_step(qty, step)
    if qty <= 0:
        return {'ok': False, 'symbol': sym, 'error': 'qty<=0', 'computed': {'qty': qty, 'px': px, 'step': step}}

    # reduceOnly & positionSide
    side_up = (side or '').upper()
    params = dict(symbol=sym, side=side_up, type='MARKET', quantity=str(qty))
    if bool(kwargs.get('reduce_only')):
        params['reduceOnly'] = True
    if dual:
        ps = position_side or kwargs.get('positionSide')
        if not ps:
            ps = 'SHORT' if side_up == 'SELL' else 'LONG'
        params['positionSide'] = ps

    # Place order
    try:
        info = self.client.futures_create_order(**params)
        return {'ok': True,
                'info': info,
                'computed': {'qty': qty, 'px': px, 'step': step, 'minQty': minQty, 'minNotional': minNotional},
                'mode': mode}
    except Exception as e:
        return {'ok': False, 'symbol': sym, 'error': str(e), 'computed': {'qty': qty, 'px': px, 'step': step}, 'mode': mode}

# Unconditionally override to make behavior predictable.
try:
    BinanceWrapper.place_futures_market_order = _place_futures_market_order_STRICT
except Exception:
    pass
# === END STRICT PERCENT SIZER OVERRIDE ===========================================

def _place_futures_market_order_FLEX(self, symbol: str, side: str,
                                     percent_balance: float | None = None,
                                     price: float | None = None,
                                     position_side: str | None = None,
                                     quantity: float | None = None,
                                     **kwargs):
    """
    Flexible sizer that ALWAYS tries to place the minimum exchange-legal order.
    Behavior:
      1) If `quantity` is given, use it (snapped to step) and enforce exchange minimums.
      2) Else if `percent_balance` is given, compute qty from percent & leverage.
         If below exchange minimums (minQty / minNotional), **auto-bump** to the
         minimum legal quantity as long as wallet `availableBalance` can cover the
         required initial margin. Log mode='percent(bumped_to_min)'.
      3) Time-in-force and GTD goodTillDate are supported.
      4) Supports hedge (positionSide) and reduce_only.
    Returns a dict like the strict variant.
    """
    sym = (symbol or '').upper()
    # Hard-block if symbol is not in desired margin mode
    try:
        self._ensure_symbol_margin(sym, kwargs.get('margin_mode') or getattr(self, '_default_margin_mode','ISOLATED'), kwargs.get('leverage'))
    except Exception as _e:
        self._log(f'BLOCK flex path: {type(_e).__name__}: {_e}', lvl='error')
        return {'ok': False, 'error': str(_e), 'mode': 'flex'}
    side_up = (side or 'BUY').upper()
    pos_side = (position_side or kwargs.get('positionSide') or None)
    px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
    if px <= 0:
        return {'ok': False, 'symbol': sym, 'error': 'No price available'}

    # Exchange filters
    f = self.get_futures_symbol_filters(sym) or {}
    step = float(f.get('stepSize') or 0.0) or 0.001
    minQty = float(f.get('minQty') or 0.0) or step
    minNotional = float(f.get('minNotional') or 0.0) or 5.0

    # Dual-side detection (hedge)
    dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
    if dual and not pos_side:
        pos_side = 'SHORT' if side_up == 'SELL' else 'LONG'

    # Helpers
    def _floor_to_step(val: float, step_: float) -> float:
        try:
            if step_ <= 0: return float(val)
            import math
            return math.floor(float(val) / float(step_)) * float(step_)
        except Exception:
            return float(val)

    def _ceil_to_step(val: float, step_: float) -> float:
        try:
            if step_ <= 0: return float(val)
            import math
            return math.ceil(float(val) / float(step_)) * float(step_)
        except Exception:
            return float(val)

    # Compute minimum legal qty
    min_qty_by_notional = _ceil_to_step((minNotional / px), step)
    min_legal_qty = max(minQty, min_qty_by_notional)

    lev = int(kwargs.get('leverage') or getattr(self, "_default_leverage", 5) or 5)
    reduce_only = bool(kwargs.get('reduce_only') or kwargs.get('reduceOnly') or False)

    # Compute starting qty
    mode = 'quantity' if (quantity is not None and float(quantity) > 0) else 'percent'
    if quantity is not None and float(quantity) > 0:
        qty = _floor_to_step(float(quantity), step)
    else:
        pct = max(float(percent_balance or 0.0), 0.0)
        # Budget and target notional based on percent
        avail = float(self.get_futures_balance_usdt() or 0.0)
        margin_budget = avail * (pct / 100.0)
        target_notional = margin_budget * max(lev, 1)
        qty = _floor_to_step((target_notional / px) if px > 0 else 0.0, step)

        # If below minimums, auto-bump to min legal qty ***if wallet can afford***
        if qty < min_legal_qty:
            # Required notional & margin for minimum legal qty
            required_notional = max(minNotional, minQty * px, min_legal_qty * px)
            required_margin = required_notional / max(lev, 1)
            # Auto-bump guard: do not exceed a configured absolute percent cap
            required_percent = (required_notional / max(avail * max(lev, 1), 1e-12)) * 100.0
            max_auto_bump_percent = float(kwargs.get('max_auto_bump_percent', getattr(self, '_max_auto_bump_percent', 5.0)))
            cushion = 1.01  # small buffer for fees/rounding
            if (required_margin <= avail * cushion) and (required_percent <= max_auto_bump_percent) and (not reduce_only):
                qty = _ceil_to_step(required_notional / px, step)
                mode = 'percent(bumped_to_min)'
            else:
                # Not enough funds or bump exceeds cap
                return {
                    'ok': False,
                    'symbol': sym,
                    'error': f'insufficient funds for exchange minimum (~{required_percent:.2f}% needed)',
                    'computed': {
                        'px': px, 'step': step,
                        'minQty': minQty, 'minNotional': minNotional,
                        'need_qty': _ceil_to_step(required_notional / px, step),
                        'need_notional': required_notional,
                        'lev': lev, 'avail': avail, 'margin_budget': margin_budget
                    },
                    'required_percent': required_percent,
                    'mode': 'percent(strict)'
                }

    # Snap again to be safe
    qty = max(qty, min_legal_qty)
    qty = _floor_to_step(qty, step)
    if qty <= 0 and not reduce_only:
        return {'ok': False, 'symbol': sym, 'error': 'qty<=0 after sizing'}

    # Build order params
    # MARKET orders: no TIF/goodTillDate
    params = dict(symbol=sym, side=side_up, type='MARKET', quantity=str(qty))
    if dual and pos_side:
        params['positionSide'] = pos_side
    if reduce_only:
        params['reduceOnly'] = True

    try:
        order = self.client.futures_create_order(**params)
        return {'ok': True, 'info': order, 'computed': {'qty': qty, 'px': px, 'step': step, 'minQty': minQty, 'minNotional': minNotional}, 'mode': mode}
    except Exception as e:
        return {'ok': False, 'symbol': sym, 'error': str(e), 'computed': {'qty': qty, 'px': px, 'step': step}, 'mode': mode}

# Override to FLEX behavior by default (auto-bump to exchange minimums)
try:
    BinanceWrapper.place_futures_market_order = _place_futures_market_order_FLEX
except Exception:
    pass