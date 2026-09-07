from __future__ import annotations

import math
import time
from datetime import datetime, timezone

from PyQt6 import QtCore

from app.integrations.exchanges.binance import BinanceWrapper, normalize_margin_ratio
from app.security.redaction import redact_text

from ..runtime.account import margin_runtime
from ..shared import helper_runtime


def _observation_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _validate_observation_rows(rows: object, account_type: str) -> None:
    if not isinstance(rows, (list, tuple)):
        raise ValueError("Positions observation must be a complete list")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Position row must be an object")
        key = "symbol" if account_type == "FUTURES" else "asset"
        symbol = row.get(key)
        if (
            not isinstance(symbol, str) or not symbol.strip()
            or symbol.strip().upper() in {"UNKNOWN", "NONE", "NULL", "-"}
            or any(char.isspace() for char in symbol.strip())
        ):
            raise ValueError(f"Position {key} is missing or invalid")
        fields = ("positionAmt",) if account_type == "FUTURES" else ("free", "locked")
        for field in fields:
            number = _observation_number(row.get(field), field)
            if account_type == "SPOT" and number < 0.0:
                raise ValueError(f"{field} must not be negative")
        if account_type == "FUTURES":
            side = row.get("positionSide")
            if side not in (None, "BOTH", "LONG", "SHORT"):
                raise ValueError("Position side is invalid")
            amount = _observation_number(row["positionAmt"], "positionAmt")
            if (side == "LONG" and amount < 0.0) or (side == "SHORT" and amount > 0.0):
                raise ValueError("Position amount contradicts its hedge side")
            for field in ("markPrice", "entryPrice", "notional", "leverage", "unRealizedProfit"):
                if row.get(field) not in (None, ""):
                    _observation_number(row[field], field)


class _PositionsWorker(QtCore.QObject):
    positions_ready = QtCore.pyqtSignal(list, str, str, int)  # rows, account_type, observed_at, generation
    observation_failed = QtCore.pyqtSignal(int)
    error = QtCore.pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        mode: str,
        account_type: str,
        connector_backend: str | None = None,
        live_safety_config: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._api_key = api_key
        self._api_secret = api_secret
        self._mode = mode
        self._acct = account_type
        self._symbols = None
        self._busy = False
        self._timer = None
        self._wrapper = None
        self._last_err_ts = 0
        self._enabled = True
        self._interval_ms = 5000
        self._spot_filter_cache: dict[str, dict] = {}
        self._connector_backend = helper_runtime._normalize_connector_backend(
            connector_backend
        )
        self._live_safety_config = dict(live_safety_config or {})
        self._observation_generation = 0

    @QtCore.pyqtSlot(int)
    def start_with_interval(self, interval_ms: int):
        try:
            self._enabled = True
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._tick)
            self._timer.start()
            try:
                self._tick()
            except Exception:
                pass
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def stop_timer(self):
        try:
            self._enabled = False
            self._observation_generation += 1
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = None
        except Exception:
            pass

    @QtCore.pyqtSlot(int)
    def set_interval(self, interval_ms: int):
        try:
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                self._timer.setInterval(self._interval_ms)
        except Exception:
            pass

    def configure(
        self,
        api_key=None,
        api_secret=None,
        mode=None,
        account_type=None,
        symbols=None,
        connector_backend=None,
        live_safety_config=None,
    ):
        self._observation_generation += 1
        if api_key is not None:
            self._api_key = api_key
        if api_secret is not None:
            self._api_secret = api_secret
        if mode is not None:
            self._mode = mode
        if account_type is not None:
            self._acct = account_type
        if connector_backend is not None:
            self._connector_backend = helper_runtime._normalize_connector_backend(
                connector_backend
            )
        if live_safety_config is not None:
            self._live_safety_config = dict(live_safety_config or {})
        self._symbols = set(symbols) if symbols else None
        self._wrapper = None
        self._spot_filter_cache = {}

    def _ensure_wrapper(self):
        if self._wrapper is None:
            try:
                self._wrapper = BinanceWrapper(
                    self._api_key or "",
                    self._api_secret or "",
                    mode=self._mode or "Demo/Testnet",
                    account_type=self._acct or "Futures",
                    connector_backend=self._connector_backend,
                    live_safety_config=self._live_safety_config,
                )
            except Exception:
                self._wrapper = None

    def _compute_futures_metrics(self, p: dict) -> dict:
        try:
            sym = str(p.get("symbol") or "").strip().upper()
            amt = float(p.get("positionAmt") or 0.0)
            try:
                mark = float(p.get("markPrice") or 0.0)
            except Exception:
                mark = 0.0
            raw_mark = mark
            lev = int(float(p.get("leverage") or 0.0)) or 0
            pnl = float(p.get("unRealizedProfit") or 0.0)
            notional = float(p.get("notional") or 0.0)
            entry_price = float(p.get("entryPrice") or 0.0)
            qty_abs = abs(amt)
            if notional <= 0.0 and mark > 0.0 and qty_abs > 0.0:
                notional = qty_abs * mark
            if entry_price <= 0.0 and qty_abs > 0.0 and notional > 0.0:
                entry_price = notional / qty_abs

            if mark <= 0.0 or not math.isfinite(mark):
                for key in (
                    "indexPrice",
                    "lastPrice",
                    "estimatedSettlePrice",
                    "oraclePrice",
                    "avgPrice",
                ):
                    try:
                        alt = float(p.get(key) or 0.0)
                    except Exception:
                        alt = 0.0
                    if alt > 0.0:
                        mark = alt
                        break
            if (mark <= 0.0 or not math.isfinite(mark)) and notional > 0.0 and qty_abs > 0.0:
                implied = notional / qty_abs
                if implied > 0.0:
                    mark = implied
            if (mark <= 0.0 or not math.isfinite(mark)) and entry_price > 0.0:
                mark = entry_price
            if (mark <= 0.0 or not math.isfinite(mark)) and sym and self._wrapper is not None:
                try:
                    alt = float(self._wrapper.get_last_price(sym, max_age=2.5) or 0.0)
                    if alt > 0.0:
                        mark = alt
                except Exception:
                    pass

            size_usdt = abs(notional)
            if (size_usdt <= 0.0 or not math.isfinite(size_usdt)) and mark > 0.0 and qty_abs > 0.0:
                size_usdt = qty_abs * mark
                notional = size_usdt

            if (
                (not math.isfinite(pnl)) or abs(pnl) <= 1e-9 or raw_mark <= 0.0
            ) and mark > 0.0 and entry_price > 0.0 and qty_abs > 0.0:
                pnl = (mark - entry_price) * amt
            elif not math.isfinite(pnl):
                pnl = 0.0

            margin, margin_balance, maint_margin, unrealized_loss = (
                margin_runtime._derive_margin_snapshot(
                    p,
                    qty_hint=qty_abs,
                    entry_price_hint=entry_price,
                )
            )
            if margin <= 0.0 and size_usdt > 0.0 and lev > 0:
                margin = size_usdt / max(lev, 1)
            margin = max(margin, 0.0)
            margin_balance = max(margin_balance, 0.0)
            roi = (pnl / margin * 100.0) if margin > 0 else 0.0
            pnl_roi_str = f"{pnl:+.2f} USDT ({roi:+.2f}%)"

            ratio = normalize_margin_ratio(p.get("marginRatio"))
            if ratio <= 0.0 and margin_balance > 0.0 and maint_margin > 0.0:
                ratio = ((maint_margin + unrealized_loss) / margin_balance) * 100.0
            try:
                update_time = int(float(p.get("updateTime") or p.get("update_time") or 0))
            except Exception:
                update_time = None
            try:
                liq_price = float(p.get("liquidationPrice") or p.get("liqPrice") or 0.0)
            except Exception:
                liq_price = 0.0
            contract_type = str(
                p.get("contractType") or p.get("contract_type") or ""
            ).strip()
            return {
                "size_usdt": size_usdt,
                "margin_usdt": margin,
                "margin_balance": margin_balance,
                "maint_margin": max(maint_margin, 0.0),
                "pnl_roi": pnl_roi_str,
                "margin_ratio": ratio,
                "pnl_value": pnl,
                "roi_percent": roi,
                "update_time": update_time,
                "leverage": lev or None,
                "entry_price": entry_price or None,
                "mark": mark if mark > 0.0 else 0.0,
                "liquidation_price": liq_price if liq_price > 0.0 else 0.0,
                "contract_type": contract_type or None,
            }
        except Exception as exc:
            raise ValueError("Futures position metrics are unavailable or invalid") from exc

    def _tick(self):
        if not self._enabled:
            return
        if self._busy:
            return
        self._busy = True
        generation = self._observation_generation
        try:
            acct = str(self._acct or "FUTURES").upper()
            if acct not in {"FUTURES", "SPOT"}:
                raise ValueError("Positions account type is invalid")
            self._ensure_wrapper()
            wrapper = self._wrapper
            if wrapper is None:
                raise ValueError("Positions connector is unavailable")
            rows = []
            # Start the observation clock before I/O, not after queueing/rendering.
            observed_at = datetime.now(timezone.utc).isoformat()
            if acct == "FUTURES":
                positions = wrapper.list_open_futures_positions(max_age=0.0, force_refresh=True)
                if generation != self._observation_generation:
                    return
                _validate_observation_rows(positions, acct)
                for p in positions:
                    try:
                        sym = p["symbol"].strip().upper()
                        amt = float(p.get("positionAmt") or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        metrics = self._compute_futures_metrics(p)
                        mark = metrics.get("mark")
                        if mark is None:
                            mark = float(p.get("markPrice") or 0.0)
                        value = metrics.get("size_usdt")
                        if not value:
                            value = abs(amt) * mark if mark else 0.0
                        side_key = "L" if amt > 0 else "S"
                        data_row = {
                            "symbol": sym,
                            "qty": abs(amt),
                            "mark": mark or 0.0,
                            "value": value,
                            "side_key": side_key,
                            "raw_position": dict(p),
                        }
                        data_row.update(metrics)
                        data_row["stop_loss_enabled"] = False
                        rows.append(data_row)
                    except Exception as exc:
                        raise ValueError("Futures position row could not be converted") from exc
            else:
                balances = wrapper.get_balances()
                if generation != self._observation_generation:
                    return
                _validate_observation_rows(balances, acct)
                base = "USDT"
                for b in balances:
                    try:
                        asset = b["asset"].strip().upper()
                        free = _observation_number(b["free"], "free")
                        locked = _observation_number(b["locked"], "locked")
                        total = _observation_number(free + locked, "balance total")
                        if asset in (base, None) or total <= 0:
                            continue
                        sym = f"{asset}{base}"
                        last = _observation_number(wrapper.get_last_price(sym, max_age=8.0), "spot price")
                        value = total * last
                        cost_snap = None
                        try:
                            cost_snap = self._wrapper.get_spot_position_cost(sym)
                        except Exception:
                            cost_snap = None
                        if cost_snap and cost_snap.get("qty", 0.0) > 0.0:
                            snap_qty = float(cost_snap.get("qty") or 0.0)
                            snap_cost = float(cost_snap.get("cost") or 0.0)
                            if snap_qty > 0.0 and snap_cost > 0.0:
                                cost_per_unit = snap_cost / snap_qty
                                margin_usdt = cost_per_unit * total
                            else:
                                margin_usdt = value
                        else:
                            margin_usdt = value
                        if margin_usdt <= 0.0:
                            margin_usdt = value
                        pnl_value = value - margin_usdt
                        roi = (pnl_value / margin_usdt * 100.0) if margin_usdt > 0 else 0.0
                        pnl_roi = f"{pnl_value:+.2f} USDT ({roi:+.2f}%)"
                        filters = self._spot_filter_cache.get(sym)
                        if filters is None:
                            try:
                                filters = self._wrapper.get_spot_symbol_filters(sym) or {}
                            except Exception:
                                filters = {}
                            self._spot_filter_cache[sym] = filters
                        rows.append(
                            {
                                "symbol": sym,
                                "qty": total,
                                "mark": last,
                                "value": value,
                                "size_usdt": value,
                                "margin_usdt": margin_usdt,
                                "pnl_roi": pnl_roi,
                                "pnl_value": pnl_value,
                                "roi_percent": roi,
                                "side_key": "L",
                                "raw_position": {
                                    "cost_usdt": margin_usdt,
                                    "qty_total": total,
                                },
                                "stop_loss_enabled": False,
                            }
                        )
                    except Exception as exc:
                        raise ValueError("Spot position row could not be converted") from exc
            for row in rows:
                for field in ("qty", "mark", "value", "margin_usdt", "pnl_value", "roi_percent"):
                    number = _observation_number(row.get(field), field)
                    if field in {"qty", "mark"} and number <= 0.0:
                        raise ValueError(f"Position {field} must be positive")
                    if field in {"value", "margin_usdt"} and number < 0.0:
                        raise ValueError(f"Position {field} must not be negative")
            if generation == self._observation_generation and self._enabled:
                self.positions_ready.emit(rows, acct, observed_at, generation)
        except Exception as exc:
            if generation == self._observation_generation and self._enabled:
                self.observation_failed.emit(generation)
                if time.time() - self._last_err_ts > 5:
                    self._last_err_ts = time.time()
                    self.error.emit(f"Positions observation unavailable: {redact_text(exc)}")
        finally:
            self._busy = False
