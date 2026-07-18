from __future__ import annotations

import math
import time
from collections.abc import Mapping

from .....settings.exchange_limits import BINANCE_MAX_FUTURES_LEVERAGE


def _mutation_accepted(result: object, *, leverage: int | None = None) -> bool:
    """Return whether a settings mutation has an explicit valid acknowledgement."""
    if not isinstance(result, Mapping) or not result:
        return False
    success = result.get("success", result.get("ok"))
    if isinstance(success, str):
        success = success.strip().lower() in {"true", "1", "yes"}
    if success is False or result.get("error"):
        return False
    code = result.get("code")
    if code is not None:
        try:
            if int(code) not in {0, 200}:
                return False
        except (TypeError, ValueError):
            return False
    if leverage is not None:
        try:
            return int(result.get("leverage")) == int(leverage)
        except (TypeError, ValueError):
            return False
    return success is True or code is not None or str(result.get("status") or "").upper() in {"OK", "SUCCESS", "ACCEPTED"}


def _coerce_max_futures_leverage(value: object = None) -> int:
    try:
        return max(1, int(value or BINANCE_MAX_FUTURES_LEVERAGE))
    except Exception:
        return BINANCE_MAX_FUTURES_LEVERAGE


def _max_futures_leverage_limit(self) -> int:
    configured = getattr(self, "_max_futures_leverage_constant", BINANCE_MAX_FUTURES_LEVERAGE)
    return _coerce_max_futures_leverage(configured)


def get_symbol_margin_type(
    self,
    symbol: str,
    *,
    allow_default_fallback: bool = True,
    raise_on_lookup_error: bool = False,
) -> str | None:
    """Return current margin type for symbol ('ISOLATED' | 'CROSSED') or None on error."""
    sym = (symbol or "").upper()
    if not sym:
        return None

    def _is_error_payload(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        success = value.get("success")
        if isinstance(success, str):
            success = success.strip().lower() in {"true", "1", "yes"}
        if success is False or value.get("error"):
            return True
        code = value.get("code")
        if code is None:
            return False
        try:
            return int(code) not in {0, 200}
        except (TypeError, ValueError):
            return True

    try:
        info = None
        try:
            info = self.client.futures_position_information(symbol=sym)
        except Exception:
            try:
                info = self.client.futures_position_risk(symbol=sym)
            except Exception as fallback_exc:
                if raise_on_lookup_error:
                    raise RuntimeError(f"Unable to read margin type for {sym}") from fallback_exc
                info = None
        if raise_on_lookup_error and (info is None or _is_error_payload(info)):
            raise RuntimeError(f"Unable to read margin type for {sym}")
        rows = []
        if isinstance(info, list):
            if raise_on_lookup_error and any(_is_error_payload(row) for row in info):
                raise RuntimeError(f"Unable to read margin type for {sym}")
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
    except Exception as exc:
        if raise_on_lookup_error:
            raise RuntimeError(f"Unable to read margin type for {sym}") from exc
        return None
    if not allow_default_fallback:
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
                amount = float(row.get("positionAmt") or 0)
            except Exception:
                pass
            else:
                # Do not treat an invalid exchange position as flat. The caller
                # must block a margin-mode change until exposure is trustworthy.
                if not math.isfinite(amount):
                    return math.inf
                total += amount
        return float(total)
    except Exception:
        # A failed position lookup leaves exposure unknown. Treat it as open so
        # a margin-mode transition cannot be attempted against live exposure.
        return math.inf


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

    cur = (
        self.get_symbol_margin_type(
            sym,
            allow_default_fallback=False,
            raise_on_lookup_error=True,
        )
        or ""
    ).upper()
    if cur and cur != want_mm:
        if abs(self._futures_net_position_amt(sym)) > 0:
            raise RuntimeError(
                f"{sym} is {cur} with an open position; refusing to place order until margin type can be changed to {want_mm}."
            )

    try:
        if self._futures_open_orders_count(sym) > 0:
            try:
                cancellation = self.client.futures_cancel_all_open_orders(symbol=sym)
                if not _mutation_accepted(cancellation):
                    raise RuntimeError("exchange did not acknowledge open-order cancellation")
            except Exception as exc:
                raise RuntimeError(f"Unable to cancel open futures orders for {sym}; order blocked") from exc
    except Exception:
        raise

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
        v = (
            self.get_symbol_margin_type(
                sym,
                allow_default_fallback=False,
                raise_on_lookup_error=True,
            )
            or ""
        ).upper()
        if v == want_mm:
            break
        if not v:
            if last_err:
                raise RuntimeError(f"Failed to set margin type for {sym} to {want_mm}: {last_err}") from last_err
            raise RuntimeError(f"Unable to verify margin type for {sym}; order blocked")
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
        vv = (
            self.get_symbol_margin_type(
                sym,
                allow_default_fallback=False,
                raise_on_lookup_error=True,
            )
            or ""
        ).upper()
        try:
            net_amt = abs(float(self._futures_net_position_amt(sym)))
        except Exception:
            net_amt = None
        if not vv:
            raise RuntimeError(f"Unable to verify margin type for {sym}; order blocked")
        if vv != want_mm:
            label = vv if vv else "UNKNOWN"
            raise RuntimeError(f"Margin type for {sym} is {label}; wanted {want_mm}. Blocking order.")

    if desired_lev is not None:
        lev = self.clamp_futures_leverage(sym, desired_lev)
        try:
            result = self.client.futures_change_leverage(symbol=sym, leverage=lev)
            if not _mutation_accepted(result, leverage=lev):
                raise RuntimeError("exchange did not acknowledge leverage update")
            self.futures_leverage = lev
        except Exception as exc:
            raise RuntimeError(f"Unable to set leverage for {sym}; order blocked") from exc
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
    if hedge_mode is not None:
        try:
            result = self.client.futures_change_position_mode(dualSidePosition=bool(hedge_mode))
            if not _mutation_accepted(result):
                raise RuntimeError("exchange did not acknowledge position mode update")
        except Exception as exc:
            raise RuntimeError("Unable to set futures position mode") from exc
    sym = (symbol or "").upper()
    if not sym:
        return
    mm = (margin_mode or getattr(self, "_default_margin_mode", "ISOLATED") or "ISOLATED").upper()
    if mm == "CROSS":
        mm = "CROSSED"
    try:
        result = self.client.futures_change_margin_type(symbol=sym, marginType=mm)
        if not _mutation_accepted(result):
            raise RuntimeError("exchange did not acknowledge margin mode update")
    except Exception as exc:
        message = str(exc).lower()
        if "no need to change" not in message and "-4046" not in message:
            raise RuntimeError(f"Unable to set margin mode for {sym}; order blocked") from exc
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
        result = self.client.futures_change_leverage(symbol=sym, leverage=lev)
        if not _mutation_accepted(result, leverage=lev):
            raise RuntimeError("exchange did not acknowledge leverage update")
    except Exception as exc:
        message = str(exc).lower()
        if "same leverage" not in message and "not modified" not in message:
            raise RuntimeError(f"Unable to set leverage for {sym}; order blocked") from exc
    self._default_margin_mode = mm
    self.futures_leverage = lev


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
    max_futures_leverage = _max_futures_leverage_limit(self)
    lev = max(1, min(max_futures_leverage, lev))
    self._requested_default_leverage = lev
    self._default_leverage = lev
    self.futures_leverage = lev


def bind_binance_futures_settings(wrapper_cls, *, max_futures_leverage: int = BINANCE_MAX_FUTURES_LEVERAGE):
    wrapper_cls.get_symbol_margin_type = get_symbol_margin_type
    wrapper_cls._futures_open_orders_count = _futures_open_orders_count
    wrapper_cls._futures_net_position_amt = _futures_net_position_amt
    wrapper_cls._ensure_margin_and_leverage_or_block = _ensure_margin_and_leverage_or_block
    wrapper_cls.ensure_futures_settings = ensure_futures_settings
    wrapper_cls.configure_futures_symbol = configure_futures_symbol
    wrapper_cls.set_futures_leverage = set_futures_leverage
    wrapper_cls._max_futures_leverage_constant = _coerce_max_futures_leverage(max_futures_leverage)
