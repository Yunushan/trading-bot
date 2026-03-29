from __future__ import annotations

from datetime import datetime, timezone
import threading
import time

import requests


def close_all_spot_positions(self):
    results = []
    balances = self.list_spot_non_usdt_balances()
    for bal in balances:
        asset = bal["asset"]
        qty = float(bal.get("free") or 0.0)
        if qty <= 0.0:
            continue
        symbol = f"{asset}USDT"

        try:
            self.get_symbol_info_spot(symbol)
        except Exception:
            results.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "ok": True,
                    "skipped": True,
                    "reason": "Symbol not tradable against USDT on this venue",
                }
            )
            continue

        try:
            filters = self.get_spot_symbol_filters(symbol)
            price = float(self.get_last_price(symbol) or 0.0)
            min_notional = float(filters.get("minNotional", 0.0) or 0.0)
            step = float(filters.get("stepSize", 0.0) or 0.0)

            if price <= 0.0:
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
            if qty_adj <= 0.0:
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
            results.append({"symbol": symbol, "qty": qty, "ok": False, "error": str(exc)})
    return results


def trigger_emergency_close_all(
    self,
    *,
    reason: str | None = None,
    source: str | None = None,
    max_attempts: int = 12,
    initial_delay: float = 5.0,
) -> bool:
    meta = {
        "reason": reason or "",
        "source": source or "",
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
            if reason:
                self._log(f"Emergency close-all already running; latest reason: {reason}", lvl="warn")
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
                    self._log(f"Emergency close-all attempt {attempt} failed (network): {exc}", lvl="error")
                except Exception as exc:
                    last_error = exc
                    self._log(f"Emergency close-all attempt {attempt} failed: {exc}", lvl="error")
                time.sleep(min(90.0, base_delay * (attempt + 1)))

            if not success:
                if last_error:
                    self._log(f"Emergency close-all aborted after {attempt} attempts: {last_error}", lvl="error")
                else:
                    self._log(f"Emergency close-all aborted after {attempt} attempts without success.", lvl="error")

            with self._emergency_closer_lock:
                self._emergency_closer_thread = None
                self._emergency_close_requested = False
                info = dict(self._emergency_close_info or {})
                info["completed_at"] = datetime.now(timezone.utc).isoformat()
                info["success"] = bool(success)
                if last_error:
                    info["error"] = str(last_error)
                self._emergency_close_info = info
            try:
                self._network_emergency_dispatched = False
                self._network_offline_hits = 0
                self._network_offline_since = time.time()
            except Exception:
                pass

        thread = threading.Thread(target=_worker, name="EmergencyCloseAll", daemon=True)
        self._emergency_closer_thread = thread
        self._log(
            f"Emergency close-all triggered ({source or 'unspecified'}): {reason or 'no reason provided'}.",
            lvl="warn",
        )
        thread.start()
        return True


def get_last_price(self, symbol: str, *, max_age: float = 5.0) -> float:
    sym = (symbol or "").upper()
    cache = getattr(self, "_last_price_cache", None)
    if cache is not None and sym:
        cached = cache.get(sym)
        if cached:
            price, ts = cached
            if price and (time.time() - ts) <= max_age:
                return price
    price = 0.0
    try:
        if self.account_type == "FUTURES":
            ticker = self._futures_call("futures_symbol_ticker", allow_recv=True, symbol=sym)
            price = float((ticker or {}).get("price", 0.0))
        else:
            ticker = self.client.get_symbol_ticker(symbol=sym)
            price = float(ticker.get("price", 0.0))
    except Exception:
        price = 0.0
    if price <= 0.0 and self.account_type != "FUTURES" and sym:
        try:
            resp = requests.get(f"{self._spot_base()}/v3/ticker/price", params={"symbol": sym}, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    price = float(data.get("price") or 0.0)
        except Exception:
            pass
    if cache is not None and sym and price:
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
            except Exception:
                pass
            delay = min(180.0, max(30.0, elapsed))
            self._network_emergency_dispatched = True
            reason = context or "network_offline"
            self.trigger_emergency_close_all(reason=reason, source="network", initial_delay=delay)
    except Exception:
        pass


def _handle_network_recovered(self) -> None:
    if getattr(self, "_network_offline", False):
        self._network_offline = False
        self._network_offline_since = 0.0
        self._network_offline_hits = 0
        self._network_emergency_dispatched = False
        try:
            self._log("Network connectivity restored.", lvl="info")
        except Exception:
            pass


def bind_binance_operational_runtime(wrapper_cls) -> None:
    wrapper_cls.close_all_spot_positions = close_all_spot_positions
    wrapper_cls.trigger_emergency_close_all = trigger_emergency_close_all
    wrapper_cls.get_last_price = get_last_price
    wrapper_cls._handle_network_offline = _handle_network_offline
    wrapper_cls._handle_network_recovered = _handle_network_recovered
