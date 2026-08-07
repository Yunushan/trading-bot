from __future__ import annotations

from datetime import datetime, timezone
import math
import threading
import time

import requests

from ..runtime_diagnostics import report_runtime_fallback
from app.security.redaction import redact_text


def close_all_spot_positions(self):
    results = []
    balances = self.list_spot_non_usdt_balances()
    for bal in balances:
        asset = str((bal or {}).get("asset") or "").strip().upper()
        symbol = f"{asset}USDT" if asset else ""
        try:
            qty = float((bal or {}).get("free") or 0.0)
        except (TypeError, ValueError) as exc:
            results.append(
                {
                    "symbol": symbol,
                    "qty": 0.0,
                    "ok": False,
                    "error": f"Invalid spot balance quantity: {redact_text(exc)}",
                }
            )
            continue
        if not asset or not math.isfinite(qty):
            results.append(
                {
                    "symbol": symbol,
                    "qty": qty if math.isfinite(qty) else 0.0,
                    "ok": False,
                    "error": "Invalid spot balance asset or non-finite quantity",
                }
            )
            continue
        if qty <= 0.0:
            continue

        try:
            symbol_info = self.get_symbol_info_spot(symbol)
        except Exception as exc:
            results.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "ok": False,
                    "error": f"Unable to verify spot symbol metadata: {redact_text(exc)}",
                }
            )
            continue
        status = str((symbol_info or {}).get("status") or "TRADING").upper()
        quote_asset = str((symbol_info or {}).get("quoteAsset") or "USDT").upper()
        if status != "TRADING" or quote_asset != "USDT":
            results.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "ok": True,
                    "skipped": True,
                    "reason": "Symbol is not tradable against USDT on this venue",
                }
            )
            continue

        try:
            filters = self.get_spot_symbol_filters(symbol)
            price = float(self.get_last_price(symbol) or 0.0)
            min_notional = float(filters.get("minNotional", 0.0) or 0.0)
            step = float(filters.get("stepSize", 0.0) or 0.0)

            if not math.isfinite(price) or price <= 0.0:
                results.append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "ok": True,
                        "skipped": True,
                        "reason": "Last price unavailable, cannot compute notional",
                    }
                )
                continue
            if not math.isfinite(min_notional) or min_notional < 0.0:
                raise ValueError("Invalid minimum-notional filter")
            if not math.isfinite(step) or step < 0.0:
                raise ValueError("Invalid step-size filter")

            est_notional = qty * price
            if min_notional > 0.0 and est_notional < min_notional:
                results.append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "ok": True,
                        "skipped": True,
                        "reason": f"Dust position below min notional ({est_notional:.8f} < {min_notional:.8f})",
                    }
                )
                continue

            qty_adj = self._floor_to_step(qty, step) if step else qty
            if not math.isfinite(qty_adj) or qty_adj <= 0.0:
                results.append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "ok": True,
                        "skipped": True,
                        "reason": "Quantity too small after applying step size",
                    }
                )
                continue

            trade = self.place_spot_market_order(symbol, "SELL", qty_adj)
            if not trade.get("ok"):
                results.append(
                    {
                        "symbol": symbol,
                        "qty": qty_adj,
                        "ok": False,
                        "error": trade.get("error") or "Spot market order failed",
                        "details": trade,
                    }
                )
                continue

            computed_qty = trade.get("computed", {}).get("qty", qty_adj)
            results.append({"symbol": symbol, "qty": computed_qty, "ok": True, "res": trade})
        except Exception as exc:
            results.append({"symbol": symbol, "qty": qty, "ok": False, "error": redact_text(exc)})
    return results


def trigger_emergency_close_all(
    self,
    *,
    reason: str | None = None,
    source: str | None = None,
    max_attempts: int = 12,
    initial_delay: float = 5.0,
) -> bool:
    safe_reason = redact_text(reason or "")
    safe_source = redact_text(source or "")
    meta = {
        "reason": safe_reason,
        "source": safe_source,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    with self._emergency_closer_lock:
        existing = getattr(self, "_emergency_closer_thread", None)
        if existing and existing.is_alive():
            self._emergency_close_requested = True
            try:
                self._emergency_close_info.update(meta)
            except Exception:
                self._emergency_close_info = dict(meta)
            if safe_reason:
                self._log(f"Emergency close-all already running; latest reason: {safe_reason}", lvl="warn")
            return False

        self._emergency_close_requested = True
        self._emergency_close_info = dict(meta)
        base_delay = max(1.0, float(initial_delay or 1.0))
        account = str(getattr(self, "account_type", "FUTURES") or "FUTURES").upper()

        def _worker():
            success = False
            attempt = 0
            last_error = None
            while max_attempts <= 0 or attempt < max_attempts:
                attempt += 1
                try:
                    if account.startswith("FUT"):
                        from ..positions.close_all_runtime import close_all_futures_positions as _close_all_futures

                        result = _close_all_futures(self) or []
                        ok = all((r.get("ok") or r.get("skipped")) for r in result) if result else True
                    else:
                        result = self.close_all_spot_positions() or []
                        ok = all(bool(r.get("ok")) for r in result) if result else True
                    if ok:
                        success = True
                        if attempt == 1:
                            self._log("Emergency close-all completed successfully on first attempt.", lvl="warn")
                        else:
                            self._log(f"Emergency close-all completed successfully on attempt {attempt}.", lvl="warn")
                        break
                    last_error = RuntimeError("partial failures")
                    self._log(f"Emergency close-all attempt {attempt} had partial failures; retrying...", lvl="error")
                except requests.exceptions.RequestException as exc:
                    last_error = exc
                    self._log(
                        f"Emergency close-all attempt {attempt} failed (network): {redact_text(exc)}",
                        lvl="error",
                    )
                except Exception as exc:
                    last_error = exc
                    self._log(
                        f"Emergency close-all attempt {attempt} failed: {redact_text(exc)}",
                        lvl="error",
                    )
                time.sleep(min(90.0, base_delay * (attempt + 1)))

            if not success:
                if last_error:
                    self._log(
                        f"Emergency close-all aborted after {attempt} attempts: {redact_text(last_error)}",
                        lvl="error",
                    )
                else:
                    self._log(f"Emergency close-all aborted after {attempt} attempts without success.", lvl="error")

            with self._emergency_closer_lock:
                self._emergency_closer_thread = None
                self._emergency_close_requested = False
                info = dict(self._emergency_close_info or {})
                info["completed_at"] = datetime.now(timezone.utc).isoformat()
                info["success"] = bool(success)
                if last_error:
                    info["error"] = redact_text(last_error)
                self._emergency_close_info = info
            try:
                self._network_emergency_dispatched = False
                self._network_offline_hits = 0
                self._network_offline_since = time.time()
            except Exception as exc:
                report_runtime_fallback(self, "Emergency close network-state reset failed", exc)

        thread = threading.Thread(target=_worker, name="EmergencyCloseAll", daemon=True)
        self._emergency_closer_thread = thread
        self._log(
            f"Emergency close-all triggered ({safe_source or 'unspecified'}): "
            f"{safe_reason or 'no reason provided'}.",
            lvl="warn",
        )
        try:
            thread.start()
        except Exception:
            self._emergency_closer_thread = None
            self._emergency_close_requested = False
            raise
        return True


def get_last_price(self, symbol: str, *, max_age: float = 5.0) -> float:
    sym = (symbol or "").upper()
    if not sym:
        return 0.0
    cache = getattr(self, "_last_price_cache", None)
    try:
        cache_max_age = float(max_age)
    except (TypeError, ValueError):
        cache_max_age = 0.0
    if not math.isfinite(cache_max_age) or cache_max_age < 0.0:
        cache_max_age = 0.0
    if cache is not None:
        cached = cache.get(sym)
        if cached:
            try:
                cached_price, cached_at = float(cached[0]), float(cached[1])
                age = time.time() - cached_at
                if math.isfinite(cached_price) and cached_price > 0.0 and 0.0 <= age <= cache_max_age:
                    return cached_price
            except (IndexError, TypeError, ValueError):
                pass
    price = 0.0
    try:
        if self.account_type == "FUTURES":
            ticker = self._futures_call("futures_symbol_ticker", allow_recv=True, symbol=sym)
            price = float((ticker or {}).get("price", 0.0))
        else:
            ticker = self.client.get_symbol_ticker(symbol=sym)
            price = float(ticker.get("price", 0.0))
    except Exception as exc:
        report_runtime_fallback(self, f"Price lookup failed for {sym}", exc)
        price = 0.0
    if not math.isfinite(price) or price <= 0.0:
        price = 0.0
    if price <= 0.0 and self.account_type != "FUTURES":
        try:
            resp = requests.get(f"{self._spot_base()}/v3/ticker/price", params={"symbol": sym}, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    price = float(data.get("price") or 0.0)
        except Exception as exc:
            report_runtime_fallback(self, f"Spot price HTTP fallback failed for {sym}", exc)
    if not math.isfinite(price) or price <= 0.0:
        price = 0.0
    if cache is not None and price > 0.0:
        cache[sym] = (price, time.time())
    return price


def _handle_network_offline(self, context: str, exc: Exception) -> None:
    now = time.time()
    message = f"Network connectivity lost while {context}. Monitoring for recovery."
    already_offline = getattr(self, "_network_offline", False)
    if not already_offline:
        self._network_offline = True
        self._network_offline_since = now
        self._network_offline_hits = 1
        self._network_emergency_dispatched = False
        self._last_network_error_log = now
        self._log(message, lvl="error")
    else:
        self._network_offline_hits = getattr(self, "_network_offline_hits", 0) + 1
        if (now - getattr(self, "_last_network_error_log", 0.0)) > 60.0:
            self._last_network_error_log = now
            self._log(message, lvl="warn")
    try:
        offline_since = getattr(self, "_network_offline_since", now)
        hits = getattr(self, "_network_offline_hits", 0)
        should_trigger = False
        if not getattr(self, "_network_emergency_dispatched", False):
            elapsed = now - offline_since
            if hits >= 4 or elapsed >= 45.0:
                should_trigger = True
        if should_trigger:
            elapsed = now - offline_since
            try:
                self._log(
                    f"Emergency close-all triggered after {hits} offline hits (elapsed {elapsed:.1f}s).",
                    lvl="warn",
                )
            except Exception as exc:
                report_runtime_fallback(self, "Emergency offline-close notification failed", exc)
            delay = min(180.0, max(30.0, elapsed))
            reason = context or "network_offline"
            accepted = self.trigger_emergency_close_all(reason=reason, source="network", initial_delay=delay)
            self._network_emergency_dispatched = bool(
                accepted or getattr(self, "_emergency_close_requested", False)
            )
    except Exception as exc:
        report_runtime_fallback(self, "Network-offline state handling failed", exc, level="error")


def _handle_network_recovered(self) -> None:
    if getattr(self, "_network_offline", False):
        self._network_offline = False
        self._network_offline_since = 0.0
        self._network_offline_hits = 0
        self._network_emergency_dispatched = False
        try:
            self._log("Network connectivity restored.", lvl="info")
        except Exception as exc:
            report_runtime_fallback(self, "Network recovery notification failed", exc)


def bind_binance_operational_runtime(wrapper_cls) -> None:
    wrapper_cls.close_all_spot_positions = close_all_spot_positions
    wrapper_cls.trigger_emergency_close_all = trigger_emergency_close_all
    wrapper_cls.get_last_price = get_last_price
    wrapper_cls._handle_network_offline = _handle_network_offline
    wrapper_cls._handle_network_recovered = _handle_network_recovered
