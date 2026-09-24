from __future__ import annotations

import math
from collections.abc import Mapping
from trading_core.orders import confirmed_close_quantity

from ..positions.close_execution import _pause_for_close_uncertainty


def _finite_positive(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) and number > 0.0 else 0.0


def _reconciled_close_qty(result: object, requested_qty: float) -> float:
    if not math.isfinite(requested_qty) or requested_qty <= 0.0:
        return 0.0
    try:
        return confirmed_close_quantity(result, requested_qty)
    except (TypeError, ValueError):
        return 0.0


def _stop_snapshot_number(value: object, *, field: str, symbol: str, required: bool) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{symbol} futures stop snapshot is missing {field}")
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{symbol} futures stop snapshot has invalid {field}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{symbol} futures stop snapshot has invalid {field}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{symbol} futures stop snapshot has non-finite {field}")
    return number


def validate_futures_stop_positions(
    positions: object,
    *,
    symbol: str,
    dual_side: bool | None = None,
    require_margin: bool = False,
) -> list[tuple[Mapping, str, float, float, str | None, float, float]]:
    """Validate an entire exchange snapshot before cumulative stop accounting."""
    if not isinstance(positions, (list, tuple)):
        raise ValueError("futures stop position snapshot is unavailable")
    target_symbol = str(symbol or "").strip().upper()
    if not target_symbol:
        raise ValueError("futures stop symbol is unavailable")

    parsed: list[tuple[Mapping, str, float, float, str | None, float, float]] = []
    for index, position in enumerate(positions):
        if not isinstance(position, Mapping):
            raise ValueError(f"futures stop snapshot row {index} is not an object")
        raw_symbol = position.get("symbol")
        if not isinstance(raw_symbol, str) or not raw_symbol.strip():
            raise ValueError(f"futures stop snapshot row {index} has no symbol")
        position_symbol = raw_symbol.strip().upper()
        amt = _stop_snapshot_number(
            position.get("positionAmt"),
            field="positionAmt",
            symbol=position_symbol,
            required=True,
        )
        assert amt is not None
        entry_px = 0.0
        margin = 0.0
        side_raw = position.get("positionSide")
        if side_raw is None:
            side_raw = position.get("positionside")
        position_side: str | None = None
        if side_raw is not None:
            if not isinstance(side_raw, str) or not side_raw.strip():
                raise ValueError(f"{position_symbol} futures stop snapshot has invalid positionSide")
            position_side = side_raw.strip().upper()
            if position_side not in {"BOTH", "LONG", "SHORT"}:
                raise ValueError(f"{position_symbol} futures stop snapshot has unknown positionSide")
            if (position_side == "LONG" and amt < 0.0) or (
                position_side == "SHORT" and amt > 0.0 and dual_side is not True
            ):
                raise ValueError(f"{position_symbol} futures stop snapshot amount conflicts with positionSide")

        qty = 0.0
        if abs(amt) > 1e-10:
            entry_value = _stop_snapshot_number(
                position.get("entryPrice"),
                field="entryPrice",
                symbol=position_symbol,
                required=True,
            )
            assert entry_value is not None
            if entry_value <= 0.0:
                raise ValueError(f"{position_symbol} futures stop snapshot entryPrice must be positive")
            entry_px = entry_value
            qty = abs(amt)
            if position_symbol == target_symbol and dual_side is True:
                if position_side not in {"LONG", "SHORT"}:
                    raise ValueError(f"{position_symbol} hedge-mode stop snapshot has no LONG/SHORT side")
            if position_symbol == target_symbol and require_margin:
                margin_candidates: list[float] = []
                for field in ("isolatedWallet", "initialMargin"):
                    candidate = _stop_snapshot_number(
                        position.get(field), field=field, symbol=position_symbol, required=False
                    )
                    if candidate is not None:
                        if candidate < 0.0:
                            raise ValueError(f"{position_symbol} futures stop snapshot {field} is negative")
                        margin_candidates.append(candidate)
                margin = next((value for value in margin_candidates if value > 0.0), 0.0)
                if margin <= 0.0:
                    notional = _stop_snapshot_number(
                        position.get("notional"), field="notional", symbol=position_symbol, required=False
                    )
                    leverage = _stop_snapshot_number(
                        position.get("leverage"), field="leverage", symbol=position_symbol, required=False
                    )
                    if notional is not None and leverage is not None and leverage > 0.0:
                        margin = abs(notional) / leverage
                if not math.isfinite(margin) or margin <= 0.0:
                    raise ValueError(f"{position_symbol} futures stop snapshot has no usable margin denominator")
        parsed.append((position, position_symbol, amt, entry_px, position_side, qty, margin))
    return parsed


def build_futures_stop_state(
    self,
    *,
    cw,
    df,
    dual_side: bool | None = None,
    require_margin: bool = False,
):
    last_price = None
    live_price_error: Exception | None = None
    try:
        live_price = _finite_positive(self.binance.get_last_price(cw["symbol"]))
        if live_price > 0.0:
            last_price = live_price
    except Exception as exc:
        live_price_error = exc
        last_price = None
    if last_price is None and not df.empty:
        try:
            close_price = _finite_positive(df["close"].iloc[-1])
            last_price = close_price if close_price > 0.0 else None
        except Exception as exc:
            if live_price_error is None:
                live_price_error = exc
            last_price = None
    if last_price is None and live_price_error is not None:
        _pause_for_close_uncertainty(
            self,
            f"{cw['symbol']} futures stop-loss price is unavailable: {live_price_error}",
            reconciliation_required=False,
        )

    state = {
        "last_price": last_price,
        "positions_cache": None,
        "positions_cache_ok": False,
    }

    def load_positions_cache():
        if state["positions_cache"] is None:
            try:
                positions = self.binance.list_open_futures_positions()
                validate_futures_stop_positions(
                    positions,
                    symbol=cw["symbol"],
                    dual_side=dual_side,
                    require_margin=require_margin,
                )
                state["positions_cache"] = list(positions)
                state["positions_cache_ok"] = True
            except Exception as exc:
                state["positions_cache"] = []
                state["positions_cache_ok"] = False
                _pause_for_close_uncertainty(
                    self,
                    f"{cw['symbol']} futures stop-loss position snapshot failed: {exc}",
                    reconciliation_required=False,
                )
        return state["positions_cache"] or []

    state["load_positions_cache"] = load_positions_cache
    return state


def purge_flat_futures_cycle_legs(self, *, cw, dual_side: bool, state) -> None:
    try:
        load_positions_cache = state.get("load_positions_cache")
        if callable(load_positions_cache):
            load_positions_cache()
        if state.get("positions_cache_ok"):
            self._purge_flat_futures_legs(
                cw["symbol"],
                state.get("positions_cache") or [],
                dual_side=dual_side,
            )
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{cw['symbol']} flat futures leg purge failed during stop-loss cycle: {exc}",
            reconciliation_required=True,
        )


def ensure_futures_leg_entry_price(
    self,
    *,
    cw,
    leg_key,
    expect_long: bool,
    dual_side: bool,
    state,
):
    leg = self._leg_ledger.get(leg_key, {}) or {}
    qty_val = _finite_positive(leg.get("qty"))
    entry_px = _finite_positive(leg.get("entry_price"))
    matched_pos = None
    load_positions_cache = state.get("load_positions_cache")
    cache = load_positions_cache() if callable(load_positions_cache) else []
    for pos in cache:
        try:
            if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                continue
            amt = float(pos.get("positionAmt") or 0.0)
            if not math.isfinite(amt):
                continue
            if dual_side:
                pos_side = str(pos.get("positionSide") or "").upper()
                if expect_long and pos_side != "LONG":
                    continue
                if (not expect_long) and pos_side != "SHORT":
                    continue
                qty_candidate = abs(amt)
            else:
                if expect_long and amt <= 0.0:
                    continue
                if (not expect_long) and amt >= 0.0:
                    continue
                qty_candidate = abs(amt)
            if qty_candidate <= 0.0:
                continue
            matched_pos = pos
            if entry_px <= 0.0:
                entry_px = _finite_positive(pos.get("entryPrice"))
            break
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{cw['symbol']} futures stop-loss position row is invalid: {exc}",
                reconciliation_required=True,
            )
            return leg, qty_val, entry_px, None
    if matched_pos and entry_px > 0.0:
        leg["entry_price"] = entry_px
        self._leg_ledger[leg_key] = leg
    return leg, qty_val, entry_px, matched_pos


__all__ = [
    "build_futures_stop_state",
    "ensure_futures_leg_entry_price",
    "purge_flat_futures_cycle_legs",
    "validate_futures_stop_positions",
]
