from __future__ import annotations

import hashlib
import hmac
import math
import time
import urllib.parse
from collections.abc import Mapping

import requests


def _exchange_mutation_accepted(result: object, *, leverage: int | None = None) -> bool:
    """Return whether a configuration mutation response represents acceptance."""
    if not isinstance(result, Mapping) or not result:
        return False
    success = result.get("success", result.get("ok"))
    if isinstance(success, str):
        success = success.strip().lower() in {"true", "1", "yes"}
    if success is False:
        return False
    if success is True:
        return True
    error = result.get("error")
    if error:
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
    if success is True:
        return True
    status = str(result.get("status") or "").upper()
    return code is not None or status in {"OK", "SUCCESS", "ACCEPTED", "COMPLETED"}


def _set_leverage_or_block(self, symbol: str, leverage: int) -> None:
    result = self.client.futures_change_leverage(symbol=symbol, leverage=int(leverage))
    if not _exchange_mutation_accepted(result, leverage=int(leverage)):
        raise RuntimeError(f"unable to set leverage for {symbol}; order blocked")


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
        if not isinstance(pins, list):
            raise RuntimeError("position probe returned a non-list response")
        types = []
        for row in pins:
            if not isinstance(row, dict):
                raise RuntimeError("position probe returned a malformed row")
            row_symbol = str(row.get("symbol") or "").upper()
            if row_symbol and row_symbol != sym:
                continue
            try:
                amount = float(row.get("positionAmt") or 0.0)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("position probe returned an invalid position amount") from exc
            if not math.isfinite(amount):
                raise RuntimeError("position probe returned a non-finite position amount")
            types.append((row.get("marginType") or "").upper())
            open_amt += abs(amount)
        current = next((item for item in types if item), None)
        if target in types:
            current = target
    except Exception as exc:
        self._log(f"margin probe failed for {sym}: {type(exc).__name__}: {exc}", lvl="warn")
        raise RuntimeError(f"unable to verify futures exposure for {sym}; margin change blocked") from exc

    if (current or "").upper() == target:
        if want_lev:
            try:
                _set_leverage_or_block(self, sym, int(want_lev))
            except Exception as exc:
                raise RuntimeError(f"unable to set leverage for {sym}; order blocked") from exc
        return True

    if open_amt > 0:
        raise RuntimeError(f"wrong_margin_mode: current={current}, want={target}, symbol={sym}, openAmt={open_amt}")

    try:
        cancellation = self.client.futures_cancel_all_open_orders(symbol=sym)
        if not _exchange_mutation_accepted(cancellation):
            raise RuntimeError("exchange did not acknowledge open-order cancellation")
    except Exception as exc:
        raise RuntimeError(f"unable to cancel open futures orders for {sym}; margin change blocked") from exc

    assume_ok = False
    try:
        self.client.futures_change_margin_type(symbol=sym, marginType=target)
    except Exception as exc:
        msg = str(exc)
        if "-4046" in msg or "No need to change margin type" in msg:
            assume_ok = True
            self._log(f"change_margin_type({sym}->{target}) says already correct (-4046).", lvl="warn")
        else:
            self._log(f"change_margin_type({sym}->{target}) raised {type(exc).__name__}: {exc}", lvl="warn")

    try:
        pins2 = self.client.futures_position_information(symbol=sym)
        types2 = [(row.get("marginType") or "").upper() for row in (pins2 or []) if isinstance(row, dict)]
        now = next((item for item in types2 if item), None)
    except Exception:
        types2, now = [], None

    if (now == target) or (target in types2) or (assume_ok and (now in (None, ""))):
        if want_lev:
            try:
                _set_leverage_or_block(self, sym, int(want_lev))
            except Exception as exc:
                raise RuntimeError(f"unable to set leverage for {sym}; order blocked") from exc
        return True

    raise RuntimeError(f"wrong_margin_mode_after_change: now={now}, want={target}, symbol={sym}")


def set_position_mode(self, hedge: bool) -> bool:
    try:
        result = self.client.futures_change_position_mode(dualSidePosition=bool(hedge))
        if _exchange_mutation_accepted(result):
            return True
    except Exception:
        pass
    for method_name in ("futures_change_position_side_dual", "futures_change_positionMode"):
        try:
            fn = getattr(self.client, method_name, None)
            if fn and _exchange_mutation_accepted(fn(dualSidePosition=bool(hedge))):
                return True
        except Exception:
            continue
    return False


def set_multi_assets_mode(self, enabled: bool) -> bool:
    payload = {"multiAssetsMargin": "true" if bool(enabled) else "false"}
    for method_name in (
        "futures_change_multi_assets_margin",
        "futures_multi_assets_margin",
        "futures_set_multi_assets_margin",
    ):
        try:
            fn = getattr(self.client, method_name, None)
            if fn:
                if _exchange_mutation_accepted(fn(**payload)):
                    return True
        except Exception:
            continue
    try:
        result = self.client._request_futures_api("post", "multiAssetsMargin", signed=True, data=payload)
        if _exchange_mutation_accepted(result):
            return True
    except Exception:
        pass
    try:
        headers = {"X-MBX-APIKEY": getattr(self.client, "API_KEY", self.api_key)}
        ts = int(time.time() * 1000)
        params = dict(payload)
        params["timestamp"] = ts
        query = urllib.parse.urlencode(params)
        signature = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{self._futures_base()}/v1/multiAssetsMargin"
        response = requests.post(url, params={**params, "signature": signature}, headers=headers, timeout=5)
        response.raise_for_status()
        try:
            response_payload = response.json()
        except (AttributeError, ValueError):
            response_payload = None
        return _exchange_mutation_accepted(response_payload)
    except Exception:
        return False


def bind_binance_futures_mode_runtime(wrapper_cls) -> None:
    wrapper_cls._ensure_symbol_margin = _ensure_symbol_margin
    wrapper_cls.set_position_mode = set_position_mode
    wrapper_cls.set_multi_assets_mode = set_multi_assets_mode
