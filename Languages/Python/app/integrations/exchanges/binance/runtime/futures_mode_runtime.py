from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse

import requests


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
            for row in pins:
                try:
                    types.append((row.get("marginType") or "").upper())
                    open_amt += abs(float(row.get("positionAmt") or 0.0))
                except Exception:
                    pass
            current = next((item for item in types if item), None)
            if target in types:
                current = target
    except Exception as exc:
        self._log(f"margin probe failed for {sym}: {type(exc).__name__}: {exc}", lvl="warn")
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
                self.client.futures_change_leverage(symbol=sym, leverage=int(want_lev))
            except Exception:
                pass
        return True

    raise RuntimeError(f"wrong_margin_mode_after_change: now={now}, want={target}, symbol={sym}")


def set_position_mode(self, hedge: bool) -> bool:
    try:
        self.client.futures_change_position_mode(dualSidePosition=bool(hedge))
        return True
    except Exception:
        for method_name in ("futures_change_position_side_dual", "futures_change_positionMode"):
            try:
                fn = getattr(self.client, method_name, None)
                if fn:
                    fn(dualSidePosition=bool(hedge))
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
                fn(**payload)
                return True
        except Exception:
            continue
    try:
        self.client._request_futures_api("post", "multiAssetsMargin", signed=True, data=payload)
        return True
    except Exception:
        try:
            headers = {"X-MBX-APIKEY": getattr(self.client, "API_KEY", self.api_key)}
            ts = int(time.time() * 1000)
            params = dict(payload)
            params["timestamp"] = ts
            query = urllib.parse.urlencode(params)
            signature = hmac.new((self.api_secret or "").encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"{self._futures_base()}/v1/multiAssetsMargin"
            requests.post(url, params={**params, "signature": signature}, headers=headers, timeout=5)
            return True
        except Exception:
            return False


def bind_binance_futures_mode_runtime(wrapper_cls) -> None:
    wrapper_cls._ensure_symbol_margin = _ensure_symbol_margin
    wrapper_cls.set_position_mode = set_position_mode
    wrapper_cls.set_multi_assets_mode = set_multi_assets_mode
