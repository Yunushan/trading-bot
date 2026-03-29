from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from ...config import MDD_LOGIC_DEFAULT, MDD_LOGIC_OPTIONS, STOP_LOSS_MODE_ORDER, STOP_LOSS_SCOPE_OPTIONS
from .engine_signal_runtime import IndicatorCache, SignalCache, collect_indicator_signals
from .models import BacktestRequest, BacktestRunResult, IndicatorDefinition


def simulate_backtest(
    engine,
    symbol: str,
    interval: str,
    df: pd.DataFrame,
    indicators: List[IndicatorDefinition],
    request: BacktestRequest,
    *,
    leverage_override: float | None = None,
    indicator_cache: Optional[IndicatorCache] = None,
    signal_cache: Optional[SignalCache] = None,
    work_df: Optional[pd.DataFrame] = None,
    work_start_idx: int | None = None,
) -> Optional[BacktestRunResult]:
    logic = (request.logic or "AND").upper()
    if work_df is None:
        work_df = df.loc[df.index >= request.start]
        work_start_idx = None
    if work_df.empty:
        return None

    capital = float(request.capital or 0.0)
    if capital <= 0.0:
        return None

    pct_raw = float(request.position_pct or 0.0)
    pct_units_raw = str(getattr(request, "position_pct_units", "") or "").strip().lower()
    if pct_units_raw in {"percent", "%", "perc"}:
        pct_fraction = pct_raw / 100.0
    elif pct_units_raw in {"fraction", "decimal", "ratio"}:
        pct_fraction = pct_raw
    else:
        pct_fraction = pct_raw / 100.0 if pct_raw > 1.0 else pct_raw
    pct_fraction = max(0.0001, min(1.0, pct_fraction))
    leverage = max(1.0, float(leverage_override if leverage_override is not None else (request.leverage or 1.0)))
    margin_mode = (request.margin_mode or "Isolated").strip().upper()
    side_pref = (request.side or "BOTH").strip().upper()

    indicator_signals, indicator_keys = collect_indicator_signals(
        symbol=symbol,
        interval=interval,
        df=df,
        indicators=indicators,
        work_df=work_df,
        work_start_idx=work_start_idx,
        compute_indicator_series_fn=engine._compute_indicator_series,
        generate_signals_fn=engine._generate_signals,
        indicator_cache=indicator_cache,
        signal_cache=signal_cache,
    )
    if not indicator_signals:
        return None

    should_stop_cb = getattr(engine, "_should_stop_cb", None)
    position_open = False
    entry_price = 0.0
    units = 0.0
    position_margin = 0.0
    direction = ""
    equity = float(capital)
    trades = 0

    mdd_logic_raw = getattr(request, "mdd_logic", MDD_LOGIC_DEFAULT)
    mdd_logic = str(mdd_logic_raw or MDD_LOGIC_DEFAULT).lower()
    if mdd_logic not in MDD_LOGIC_OPTIONS:
        mdd_logic = MDD_LOGIC_OPTIONS[0]

    drawdown_state_cumulative = {"peak": equity, "max_value": 0.0, "max_pct": 0.0}
    drawdown_state_account = {"peak": equity, "max_value": 0.0, "max_pct": 0.0}
    per_trade_state = {"max_value": 0.0, "max_pct": 0.0}
    trade_drawdown_totals = {"max_value": 0.0, "max_pct": 0.0}
    trade_result_totals = {"max_value": 0.0, "max_pct": 0.0}
    trade_state = {
        "active": False,
        "direction": "",
        "entry_price": 0.0,
        "peak_price": 0.0,
        "trough_price": 0.0,
        "max_value": 0.0,
        "max_pct": 0.0,
        "notional": 0.0,
        "units": 0.0,
    }

    def _update_drawdown(state: dict, current_equity: float) -> None:
        try:
            current = float(current_equity)
        except Exception:
            current = 0.0
        peak = state.get("peak", 0.0)
        if current > peak:
            state["peak"] = current
            return
        if peak <= 0.0:
            return
        drawdown_value = peak - current
        if drawdown_value <= 0.0:
            return
        if drawdown_value > state.get("max_value", 0.0):
            state["max_value"] = drawdown_value
        drawdown_pct = (drawdown_value / peak * 100.0) if peak else 0.0
        if drawdown_pct > state.get("max_pct", 0.0):
            state["max_pct"] = drawdown_pct

    def _record_realized_equity(value: float) -> None:
        _update_drawdown(drawdown_state_cumulative, value)
        if mdd_logic == "entire_account":
            _update_drawdown(drawdown_state_account, value)

    def _reset_trade_state() -> None:
        trade_state["active"] = False
        trade_state["direction"] = ""
        trade_state["entry_price"] = 0.0
        trade_state["peak_price"] = 0.0
        trade_state["trough_price"] = 0.0
        trade_state["max_value"] = 0.0
        trade_state["max_pct"] = 0.0
        trade_state["notional"] = 0.0
        trade_state["units"] = 0.0

    def _start_trade(dir_text: str, units_val: float) -> None:
        units_abs = abs(units_val)
        if units_abs <= 0.0 or entry_price <= 0.0:
            return
        trade_state["active"] = True
        trade_state["direction"] = dir_text
        trade_state["entry_price"] = entry_price
        trade_state["peak_price"] = entry_price
        trade_state["trough_price"] = entry_price
        trade_state["max_value"] = 0.0
        trade_state["max_pct"] = 0.0
        trade_state["notional"] = abs(entry_price * units_abs)
        trade_state["units"] = units_abs

    def _update_trade_drawdown(price_val: float, high_val: float, low_val: float) -> None:
        if not trade_state["active"]:
            return
        units_in_position = float(trade_state.get("units") or 0.0)
        if units_in_position <= 0.0:
            return
        if trade_state["direction"] == "LONG":
            trade_state["peak_price"] = max(trade_state["peak_price"], high_val)
            worst_price = min(low_val, price_val)
            drawdown_price = max(0.0, trade_state["peak_price"] - worst_price)
        else:
            trade_state["trough_price"] = min(trade_state["trough_price"], low_val)
            worst_price = max(high_val, price_val)
            drawdown_price = max(0.0, worst_price - trade_state["trough_price"])
        drawdown_value = drawdown_price * units_in_position
        notional = trade_state["notional"]
        if notional <= 0.0:
            notional = abs(trade_state["entry_price"] * units_in_position)
            trade_state["notional"] = notional
        drawdown_pct = (drawdown_value / notional * 100.0) if notional else 0.0
        if drawdown_value > trade_state["max_value"]:
            trade_state["max_value"] = drawdown_value
        if drawdown_pct > trade_state["max_pct"]:
            trade_state["max_pct"] = drawdown_pct
        if drawdown_value > trade_drawdown_totals["max_value"]:
            trade_drawdown_totals["max_value"] = drawdown_value
        if drawdown_pct > trade_drawdown_totals["max_pct"]:
            trade_drawdown_totals["max_pct"] = drawdown_pct

    def _finalize_trade(exit_price: float | None = None) -> None:
        if not trade_state["active"]:
            return
        value = trade_state["max_value"]
        pct = trade_state["max_pct"]
        if value > trade_drawdown_totals["max_value"]:
            trade_drawdown_totals["max_value"] = value
        if pct > trade_drawdown_totals["max_pct"]:
            trade_drawdown_totals["max_pct"] = pct
        if mdd_logic == "per_trade":
            if value > per_trade_state["max_value"]:
                per_trade_state["max_value"] = value
                per_trade_state["max_pct"] = pct
        units_in_position = float(trade_state.get("units") or 0.0)
        entry_price_local = float(trade_state.get("entry_price") or 0.0)
        notional = float(trade_state.get("notional") or 0.0)
        if notional <= 0.0 and entry_price_local > 0.0 and units_in_position > 0.0:
            notional = abs(entry_price_local * units_in_position)
        loss_value = 0.0
        loss_pct = 0.0
        if units_in_position > 0.0 and entry_price_local > 0.0:
            exit_px = entry_price_local if exit_price is None else float(exit_price)
            if trade_state.get("direction") == "LONG":
                pnl_val = (exit_px - entry_price_local) * units_in_position
            else:
                pnl_val = (entry_price_local - exit_px) * units_in_position
            if pnl_val < 0.0:
                loss_value = abs(pnl_val)
                if notional > 0.0:
                    loss_pct = (loss_value / notional) * 100.0
        if loss_value > trade_result_totals["max_value"]:
            trade_result_totals["max_value"] = loss_value
        if loss_pct > trade_result_totals["max_pct"]:
            trade_result_totals["max_pct"] = loss_pct
        _reset_trade_state()

    _reset_trade_state()
    _record_realized_equity(equity)

    can_long = side_pref in ("BUY", "BOTH")
    can_short = side_pref in ("SELL", "BOTH")
    stop_enabled = bool(getattr(request, "stop_loss_enabled", False))
    stop_mode = str(getattr(request, "stop_loss_mode", "usdt")).lower()
    if stop_mode not in STOP_LOSS_MODE_ORDER:
        stop_mode = STOP_LOSS_MODE_ORDER[0]
    stop_usdt = max(0.0, float(getattr(request, "stop_loss_usdt", 0.0) or 0.0))
    stop_percent = max(0.0, float(getattr(request, "stop_loss_percent", 0.0) or 0.0))
    scope = str(getattr(request, "stop_loss_scope", "per_trade") or "per_trade").lower()
    if scope not in STOP_LOSS_SCOPE_OPTIONS:
        scope = STOP_LOSS_SCOPE_OPTIONS[0]

    n_rows = len(work_df)
    if n_rows == 0:
        return None

    close_values = work_df["close"].to_numpy(dtype=float, copy=False)
    high_values = work_df["high"].to_numpy(dtype=float, copy=False) if "high" in work_df else close_values
    low_values = work_df["low"].to_numpy(dtype=float, copy=False) if "low" in work_df else close_values

    buy_arrays = [signals["buy"] for signals in indicator_signals if signals["buy"] is not None]
    sell_arrays = [signals["sell"] for signals in indicator_signals if signals["sell"] is not None]

    if buy_arrays:
        if len(buy_arrays) == 1:
            aggregated_buy_array = buy_arrays[0]
        else:
            buy_stack = np.vstack(buy_arrays)
            if logic == "AND":
                aggregated_buy_array = np.all(buy_stack, axis=0)
            else:
                aggregated_buy_array = np.any(buy_stack, axis=0)
    else:
        aggregated_buy_array = np.zeros(n_rows, dtype=bool)

    if sell_arrays:
        if len(sell_arrays) == 1:
            aggregated_sell_array = sell_arrays[0]
        else:
            sell_stack = np.vstack(sell_arrays)
            aggregated_sell_array = np.any(sell_stack, axis=0)
    else:
        aggregated_sell_array = np.zeros(n_rows, dtype=bool)

    for idx in range(n_rows):
        if should_stop_cb and callable(should_stop_cb) and should_stop_cb():
            raise RuntimeError("backtest_cancelled")
        price = float(close_values[idx] if np.isfinite(close_values[idx]) else 0.0)
        if price <= 0.0:
            continue
        high_price_val = float(high_values[idx] if np.isfinite(high_values[idx]) else price)
        if high_price_val <= 0.0:
            high_price_val = price
        low_price_val = float(low_values[idx] if np.isfinite(low_values[idx]) else price)
        if low_price_val <= 0.0:
            low_price_val = price

        aggregated_buy = bool(aggregated_buy_array[idx])
        aggregated_sell = bool(aggregated_sell_array[idx])
        if not position_open and mdd_logic == "entire_account":
            _update_drawdown(drawdown_state_account, equity)

        if position_open:
            _update_trade_drawdown(price, high_price_val, low_price_val)
            if mdd_logic == "entire_account":
                if units > 0.0:
                    if direction == "LONG":
                        best_price = max(high_price_val, price)
                        worst_price = min(low_price_val, price)
                        best_equity = equity + (best_price - entry_price) * units
                        worst_equity = equity + (worst_price - entry_price) * units
                    else:
                        best_price = min(low_price_val, price)
                        worst_price = max(high_price_val, price)
                        best_equity = equity + (entry_price - best_price) * units
                        worst_equity = equity + (entry_price - worst_price) * units
                    _update_drawdown(drawdown_state_account, best_equity)
                    _update_drawdown(drawdown_state_account, worst_equity)
                else:
                    _update_drawdown(drawdown_state_account, equity)
            effective_leverage = leverage
            if margin_mode == "CROSS":
                effective_leverage = max(1.0, leverage * pct_fraction)
            if direction == "LONG" and effective_leverage > 1.0:
                liq_price = entry_price * (1.0 - (1.0 / effective_leverage))
                if liq_price < 0.0:
                    liq_price = 0.0
                if low_price_val <= liq_price:
                    loss = min(equity, position_margin)
                    equity = max(0.0, equity - loss)
                    _record_realized_equity(equity)
                    _finalize_trade(float(liq_price))
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    continue
            if direction == "SHORT" and effective_leverage > 1.0:
                liq_price = entry_price * (1.0 + (1.0 / effective_leverage))
                if high_price_val >= liq_price:
                    loss = min(equity, position_margin)
                    equity = max(0.0, equity - loss)
                    _record_realized_equity(equity)
                    _finalize_trade(float(liq_price))
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    continue

            if stop_enabled and units > 0.0 and entry_price > 0.0:
                if direction == "LONG":
                    worst_price = min(price, low_price_val)
                    loss_usdt = max(0.0, (entry_price - worst_price) * units)
                else:
                    worst_price = max(price, high_price_val)
                    loss_usdt = max(0.0, (worst_price - entry_price) * units)
                if scope == "per_trade" and position_margin > 0.0:
                    denom = position_margin
                else:
                    denom = entry_price * units
                loss_pct = (loss_usdt / denom * 100.0) if denom > 0 else 0.0
                triggered = False
                if stop_mode in ("usdt", "both") and stop_usdt > 0.0 and loss_usdt >= stop_usdt:
                    triggered = True
                if not triggered and stop_mode in ("percent", "both") and stop_percent > 0.0 and loss_pct >= stop_percent:
                    triggered = True
                if triggered:
                    exit_price = worst_price
                    pnl = (exit_price - entry_price) * units if direction == "LONG" else (entry_price - exit_price) * units
                    equity = max(0.0, equity + pnl)
                    _record_realized_equity(equity)
                    _finalize_trade(exit_price)
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    trades += 1
                    continue

            if direction == "LONG" and aggregated_sell:
                pnl = (price - entry_price) * units
                equity = max(0.0, equity + pnl)
                _record_realized_equity(equity)
                _finalize_trade(price)
                position_open = False
                units = 0.0
                position_margin = 0.0
                direction = ""
                if can_short and aggregated_sell and equity > 0.0:
                    aggregated_sell = True
                else:
                    aggregated_sell = False
            elif direction == "SHORT" and aggregated_buy:
                pnl = (entry_price - price) * units
                equity = max(0.0, equity + pnl)
                _record_realized_equity(equity)
                _finalize_trade(price)
                position_open = False
                units = 0.0
                position_margin = 0.0
                direction = ""
                if can_long and aggregated_buy and equity > 0.0:
                    aggregated_buy = True
                else:
                    aggregated_buy = False

        if not position_open and equity > 0.0:
            if aggregated_buy and can_long:
                entry_price = price
                position_margin = equity * pct_fraction
                units = (position_margin * leverage) / entry_price if entry_price > 0.0 else 0.0
                if units <= 0.0:
                    position_margin = 0.0
                    continue
                position_open = True
                direction = "LONG"
                _start_trade(direction, units)
                trades += 1
            elif aggregated_sell and can_short:
                entry_price = price
                position_margin = equity * pct_fraction
                units = (position_margin * leverage) / entry_price if entry_price > 0.0 else 0.0
                if units <= 0.0:
                    position_margin = 0.0
                    continue
                position_open = True
                direction = "SHORT"
                _start_trade(direction, units)
                trades += 1

    if position_open and units > 0.0:
        last_price = float(work_df["close"].iloc[-1] or 0.0)
        if direction == "LONG":
            pnl = (last_price - entry_price) * units
        else:
            pnl = (entry_price - last_price) * units
        equity = max(0.0, equity + pnl)
        _record_realized_equity(equity)
        _finalize_trade(last_price)
        position_open = False
        units = 0.0
        position_margin = 0.0
        direction = ""

    roi_value = equity - capital
    roi_percent = (roi_value / capital * 100.0) if capital else 0.0

    position_mode_val = (request.position_mode or "").strip() if hasattr(request, "position_mode") else ""
    assets_mode_val = (request.assets_mode or "").strip() if hasattr(request, "assets_mode") else ""
    account_mode_val = (request.account_mode or "").strip() if hasattr(request, "account_mode") else ""

    cumulative_dd_value = float(drawdown_state_cumulative.get("max_value", 0.0))
    cumulative_dd_pct = float(drawdown_state_cumulative.get("max_pct", 0.0))
    account_dd_value = float(drawdown_state_account.get("max_value", 0.0))
    account_dd_pct = float(drawdown_state_account.get("max_pct", 0.0))
    per_trade_dd_value = float(per_trade_state.get("max_value", 0.0))
    per_trade_dd_pct = float(per_trade_state.get("max_pct", 0.0))

    if mdd_logic == "per_trade":
        selected_dd_value = per_trade_dd_value
        selected_dd_pct = per_trade_dd_pct
    elif mdd_logic == "entire_account":
        selected_dd_value = account_dd_value
        selected_dd_pct = account_dd_pct
    else:
        selected_dd_value = cumulative_dd_value
        selected_dd_pct = cumulative_dd_pct

    return BacktestRunResult(
        symbol="",
        interval="",
        indicator_keys=indicator_keys,
        trades=trades,
        roi_value=float(roi_value),
        roi_percent=float(roi_percent),
        final_equity=float(equity),
        max_drawdown_value=float(selected_dd_value),
        max_drawdown_percent=float(selected_dd_pct),
        max_drawdown_during_value=float(trade_drawdown_totals.get("max_value", 0.0)),
        max_drawdown_during_percent=float(trade_drawdown_totals.get("max_pct", 0.0)),
        max_drawdown_result_value=float(trade_result_totals.get("max_value", 0.0)),
        max_drawdown_result_percent=float(trade_result_totals.get("max_pct", 0.0)),
        logic=logic,
        leverage=float(leverage),
        mdd_logic=mdd_logic,
        start=request.start,
        end=request.end,
        position_pct=pct_fraction,
        stop_loss_enabled=stop_enabled,
        stop_loss_mode=stop_mode,
        stop_loss_usdt=stop_usdt,
        stop_loss_percent=stop_percent,
        stop_loss_scope=scope,
        margin_mode=margin_mode,
        position_mode=position_mode_val,
        assets_mode=assets_mode_val,
        account_mode=account_mode_val,
    )
