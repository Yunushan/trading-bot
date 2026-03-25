from __future__ import annotations

import time


def get_symbol_margin_type(self, symbol: str) -> str | None:
    """Return current margin type for symbol ('ISOLATED' | 'CROSSED') or None on error."""
    sym = (symbol or "").upper()
    if not sym:
        return None
    try:
        info = None
        try:
            info = self.client.futures_position_information(symbol=sym)
        except Exception:
            try:
                info = self.client.futures_position_risk(symbol=sym)
            except Exception:
                info = None
        rows = []
        if isinstance(info, list):
            rows.extend(info)
        elif info:
            rows.append(info)

        def _extract(row):
            if not isinstance(row, dict):
                return None
            row_sym = (row.get("symbol") or row.get("pair") or "").upper()
            if row_sym and row_sym != sym:
                return None
            raw = row.get("marginType")
            if raw in (None, ""):
                raw = row.get("margintype")
            if raw in (None, ""):
                raw = row.get("margin_type")
            text = str(raw or "").strip().upper()
            if text in ("ISOLATED", "CROSSED", "CROSS"):
                return "CROSSED" if text.startswith("CROSS") else "ISOLATED"
            return None

        for row in rows:
            mt = _extract(row)
            if mt:
                return mt
        try:
            acct = self._get_futures_account_cached(force_refresh=True) or {}
            for row in acct.get("positions", []):
                mt = _extract(row)
                if mt:
                    return mt
        except Exception:
            pass
    except Exception:
        return None
    fallback = getattr(self, "_default_margin_mode", None)
    if fallback:
        fb = str(fallback).strip().upper()
        if fb:
            return "CROSSED" if fb.startswith("CROSS") else "ISOLATED"
    return None


def _futures_open_orders_count(self, symbol: str) -> int:
    try:
        arr = self.client.futures_get_open_orders(symbol=(symbol or "").upper())
        return len(arr or [])
    except Exception:
        return 0


def _futures_net_position_amt(self, symbol: str) -> float:
    try:
        sym = (symbol or "").upper()
        info = self.client.futures_position_information(symbol=sym) or []
        total = 0.0
        for row in info:
            if (row or {}).get("symbol", "").upper() != sym:
                continue
            try:
                total += float(row.get("positionAmt") or 0)
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
    sym = (symbol or "").upper()
    want_mm = (desired_mm or getattr(self, "_default_margin_mode", "ISOLATED") or "ISOLATED").upper()
    want_mm = "CROSSED" if want_mm in ("CROSS", "CROSSED") else "ISOLATED"
    fast_mode = bool(getattr(self, "_fast_order_mode", False))
    try:
        desired_lev_norm = int(desired_lev) if desired_lev is not None else None
    except Exception:
        desired_lev_norm = None
    if fast_mode and sym:
        try:
            cache = getattr(self, "_futures_settings_cache", None)
            if cache is None:
                cache = {}
                self._futures_settings_cache = cache
            ttl = float(getattr(self, "_fast_order_cache_ttl", 60.0) or 60.0)
            entry = None
            try:
                lock = getattr(self, "_futures_settings_cache_lock", None)
            except Exception:
                lock = None
            if lock:
                with lock:
                    entry = cache.get(sym)
            else:
                entry = cache.get(sym)
            if isinstance(entry, dict):
                cached_mm = str(entry.get("margin_mode") or "").upper()
                cached_lev = entry.get("leverage")
                age = time.time() - float(entry.get("ts") or 0.0)
                if cached_mm == want_mm and (desired_lev_norm is None or cached_lev == desired_lev_norm) and age < ttl:
                    return
        except Exception:
            pass

    cur = (self.get_symbol_margin_type(sym) or "").upper()
    if cur and cur != want_mm:
        if abs(self._futures_net_position_amt(sym)) > 0:
            raise RuntimeError(
                f"{sym} is {cur} with an open position; refusing to place order until margin type can be changed to {want_mm}."
            )

    try:
        if self._futures_open_orders_count(sym) > 0:
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
            except Exception:
                pass
    except Exception:
        pass

    last_err = None
    for _attempt in range(5):
        try:
            self.client.futures_change_margin_type(symbol=sym, marginType=want_mm)
        except Exception as exc:
            msg = str(getattr(exc, "message", "") or exc).lower()
            if "no need to change" in msg or "no need to change margin type" in msg or "code=-4099" in msg:
                pass
            elif "-4048" in msg or ("cannot change" in msg and ("open" in msg or "position" in msg)):
                raise RuntimeError(
                    f"Binance refused to change margin type for {sym} while open orders/positions exist (-4048). Close them first."
                )
            else:
                last_err = exc
        v = (self.get_symbol_margin_type(sym) or "").upper()
        if v == want_mm:
            break
        if not v:
            self._log(f"margin_type probe returned blank for {sym}; assuming {want_mm}", lvl="info")
            break
        try:
            net_amt = abs(float(self._futures_net_position_amt(sym)))
        except Exception:
            net_amt = None
        if (not v) and (net_amt is None or net_amt <= 0):
            v = want_mm
            break
        time.sleep(0.2)
    else:
        if last_err:
            raise RuntimeError(f"Failed to set margin type for {sym} to {want_mm}: {last_err}")
        vv = (self.get_symbol_margin_type(sym) or "").upper()
        try:
            net_amt = abs(float(self._futures_net_position_amt(sym)))
        except Exception:
            net_amt = None
        if not vv:
            self._log(f"margin_type still blank for {sym}; proceeding as {want_mm}", lvl="warn")
            vv = want_mm
        if vv != want_mm:
            label = vv if vv else "UNKNOWN"
            raise RuntimeError(f"Margin type for {sym} is {label}; wanted {want_mm}. Blocking order.")

    if desired_lev is not None:
        lev = self.clamp_futures_leverage(sym, desired_lev)
        try:
            self.client.futures_change_leverage(symbol=sym, leverage=lev)
            self.futures_leverage = lev
        except Exception:
            pass
    try:
        cache = getattr(self, "_futures_settings_cache", None)
        if cache is None:
            cache = {}
            self._futures_settings_cache = cache
        lock = getattr(self, "_futures_settings_cache_lock", None)
        payload = {"margin_mode": want_mm, "leverage": desired_lev_norm, "ts": time.time()}
        if lock:
            with lock:
                cache[sym] = payload
        else:
            cache[sym] = payload
    except Exception:
        pass


def ensure_futures_settings(
    self,
    symbol: str,
    leverage: int | None = None,
    margin_mode: str | None = None,
    hedge_mode: bool | None = None,
):
    try:
        if hedge_mode is not None:
            try:
                self.client.futures_change_position_mode(dualSidePosition=bool(hedge_mode))
            except Exception:
                pass
        sym = (symbol or "").upper()
        if not sym:
            return
        mm = (margin_mode or getattr(self, "_default_margin_mode", "ISOLATED") or "ISOLATED").upper()
        if mm == "CROSS":
            mm = "CROSSED"
        try:
            self.client.futures_change_margin_type(symbol=sym, marginType=mm)
        except Exception as exc:
            if "no need to change" not in str(exc).lower() and "-4046" not in str(exc):
                pass
        try:
            lev_requested = int(
                leverage
                if leverage is not None
                else getattr(self, "_requested_default_leverage", getattr(self, "_default_leverage", 5)) or 5
            )
        except Exception:
            lev_requested = 5
        lev = self.clamp_futures_leverage(sym, lev_requested)
        try:
            self.client.futures_change_leverage(symbol=sym, leverage=lev)
        except Exception as exc:
            if "same leverage" not in str(exc).lower() and "not modified" not in str(exc).lower():
                pass
        self._default_margin_mode = mm
        self.futures_leverage = lev
    except Exception:
        pass


def configure_futures_symbol(self, symbol: str):
    """Back-compat shim: some strategy code calls this; forward to ensure_futures_settings."""
    try:
        self.ensure_futures_settings(symbol)
    except Exception:
        pass


def set_futures_leverage(self, lev: int):
    try:
        lev = int(lev)
    except Exception:
        return
    max_futures_leverage = max(1, int(getattr(self, "_max_futures_leverage_constant", 150) or 150))
    lev = max(1, min(max_futures_leverage, lev))
    self._requested_default_leverage = lev
    self._default_leverage = lev
    self.futures_leverage = lev


def bind_binance_futures_settings(wrapper_cls, *, max_futures_leverage: int = 150):
    wrapper_cls.get_symbol_margin_type = get_symbol_margin_type
    wrapper_cls._futures_open_orders_count = _futures_open_orders_count
    wrapper_cls._futures_net_position_amt = _futures_net_position_amt
    wrapper_cls._ensure_margin_and_leverage_or_block = _ensure_margin_and_leverage_or_block
    wrapper_cls.ensure_futures_settings = ensure_futures_settings
    wrapper_cls.configure_futures_symbol = configure_futures_symbol
    wrapper_cls.set_futures_leverage = set_futures_leverage
    wrapper_cls._max_futures_leverage_constant = max(1, int(max_futures_leverage or 150))
