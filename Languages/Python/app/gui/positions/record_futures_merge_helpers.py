from __future__ import annotations

from app.integrations.exchanges.binance import normalize_margin_ratio

from .record_build_helpers import (
    _apply_interval_metadata_to_row,
    _copy_allocations_for_key,
    _resolve_trigger_indicators_safe,
)


def _merge_futures_rows_into_positions_map(self, base_rows: list, positions_map: dict, alloc_map_global: dict) -> None:
    try:
        raw_entries = []
        for row in base_rows:
            try:
                raw_entry = dict(row.get("raw_position") or {})
            except Exception:
                raw_entry = {}
            sym_val = str(raw_entry.get("symbol") or row.get("symbol") or "").strip().upper()
            if not sym_val:
                continue
            if not raw_entry:
                try:
                    qty_val = float(row.get("qty") or 0.0)
                except Exception:
                    qty_val = 0.0
                side_key = str(row.get("side_key") or "").upper()
                qty_signed = -abs(qty_val) if side_key == "S" else abs(qty_val)
                try:
                    margin_balance_fallback = float(row.get("margin_balance") or 0.0)
                except Exception:
                    margin_balance_fallback = 0.0
                if margin_balance_fallback <= 0.0:
                    try:
                        margin_balance_fallback = float(row.get("margin_usdt") or 0.0) + float(row.get("pnl_value") or 0.0)
                    except Exception:
                        margin_balance_fallback = float(row.get("margin_usdt") or 0.0)
                raw_entry = {
                    "symbol": sym_val,
                    "positionAmt": qty_signed,
                    "markPrice": row.get("mark"),
                    "isolatedWallet": margin_balance_fallback if margin_balance_fallback > 0.0 else row.get("margin_usdt"),
                    "initialMargin": row.get("margin_usdt"),
                    "marginBalance": margin_balance_fallback,
                    "maintMargin": row.get("maint_margin"),
                    "marginRatio": row.get("margin_ratio"),
                    "unRealizedProfit": row.get("pnl_value"),
                    "updateTime": row.get("update_time"),
                    "leverage": row.get("leverage"),
                    "notional": row.get("size_usdt"),
                }
            else:
                raw_entry["symbol"] = sym_val
            raw_entries.append(raw_entry)

        for p in raw_entries:
            try:
                sym = str(p.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                amt = float(p.get("positionAmt") or 0.0)
                if abs(amt) <= 0.0:
                    continue
                mark = float(p.get("markPrice") or 0.0)
                value = abs(amt) * mark if mark else 0.0
                side_key = "L" if amt > 0 else "S"
                entry_price = float(p.get("entryPrice") or 0.0)
                iso_wallet = float(p.get("isolatedWallet") or 0.0)
                margin_usdt = float(p.get("initialMargin") or 0.0)
                try:
                    position_initial = float(p.get("positionInitialMargin") or 0.0)
                except Exception:
                    position_initial = 0.0
                try:
                    open_order_margin = float(p.get("openOrderMargin") or p.get("openOrderInitialMargin") or 0.0)
                except Exception:
                    open_order_margin = 0.0
                pnl = float(p.get("unRealizedProfit") or 0.0)
                lev_val_raw = float(p.get("leverage") or 0.0)
                leverage = int(lev_val_raw) if lev_val_raw else None
                if margin_usdt <= 0.0 and iso_wallet > 0.0:
                    try:
                        margin_usdt = iso_wallet - pnl
                    except Exception:
                        margin_usdt = iso_wallet
                    if margin_usdt <= 0.0:
                        margin_usdt = iso_wallet
                if margin_usdt <= 0.0 and entry_price > 0.0 and leverage:
                    margin_usdt = abs(amt) * entry_price / max(leverage, 1)
                if margin_usdt <= 0.0 and leverage and leverage > 0 and value > 0.0:
                    margin_usdt = value / max(leverage, 1)
                margin_usdt = max(margin_usdt, 0.0)
                if position_initial > 0.0 or open_order_margin > 0.0:
                    margin_usdt = max(0.0, position_initial) + max(0.0, open_order_margin)
                try:
                    maint = float(p.get("maintMargin") or p.get("maintenanceMargin") or 0.0)
                except Exception:
                    maint = 0.0
                try:
                    initial_margin_val = float(p.get("initialMargin") or 0.0)
                except Exception:
                    initial_margin_val = 0.0
                try:
                    maint_rate_val = float(p.get("maintMarginRate") or p.get("maintenanceMarginRate") or 0.0)
                except Exception:
                    maint_rate_val = 0.0
                if maint <= 0.0 and maint_rate_val > 0.0 and value > 0.0:
                    maint = abs(value) * maint_rate_val
                baseline_margin = maint if maint > 0.0 else initial_margin_val
                if baseline_margin <= 0.0 and margin_usdt > 0.0 and leverage:
                    baseline_margin = margin_usdt / max(leverage, 1)
                if baseline_margin <= 0.0:
                    baseline_margin = margin_usdt
                if position_initial > 0.0:
                    baseline_margin = position_initial
                try:
                    margin_balance_val = float(p.get("marginBalance") or 0.0)
                except Exception:
                    margin_balance_val = 0.0
                if margin_balance_val <= 0.0 and iso_wallet > 0.0:
                    margin_balance_val = iso_wallet
                if margin_balance_val <= 0.0:
                    margin_balance_val = margin_usdt + pnl
                if margin_balance_val <= 0.0:
                    margin_balance_val = margin_usdt
                margin_balance_val = max(margin_balance_val, 0.0)
                try:
                    wallet_balance_val = float(p.get("walletBalance") or 0.0)
                except Exception:
                    wallet_balance_val = 0.0
                if wallet_balance_val <= 0.0:
                    wallet_balance_val = margin_balance_val if margin_balance_val > 0.0 else margin_usdt + pnl
                if wallet_balance_val <= 0.0 and iso_wallet > 0.0:
                    wallet_balance_val = iso_wallet
                wallet_balance_val = max(wallet_balance_val, 0.0)
                raw_margin_ratio_val = None
                for ratio_key in ("marginRatioRaw", "marginRatio", "margin_ratio"):
                    val = p.get(ratio_key)
                    if val in (None, "", 0, 0.0):
                        continue
                    try:
                        raw_margin_ratio_val = float(val)
                        break
                    except Exception:
                        continue
                calc_ratio = normalize_margin_ratio(p.get("marginRatioCalc")) if p.get("marginRatioCalc") is not None else 0.0
                margin_ratio = normalize_margin_ratio(raw_margin_ratio_val)
                if margin_ratio <= 0.0:
                    margin_ratio = calc_ratio
                if (margin_ratio <= 0.0 or not margin_ratio) and wallet_balance_val > 0:
                    unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                    margin_ratio = ((baseline_margin + open_order_margin + unrealized_loss) / wallet_balance_val) * 100.0
                roi_pct = 0.0
                if margin_usdt > 0:
                    try:
                        roi_pct = (pnl / margin_usdt) * 100.0
                    except Exception:
                        roi_pct = 0.0
                    pnl_roi = f"{pnl:+.2f} USDT ({roi_pct:+.2f}%)"
                else:
                    pnl_roi = f"{pnl:+.2f} USDT"
                try:
                    update_time = int(float(p.get("updateTime") or p.get("update_time") or 0))
                except Exception:
                    update_time = 0
                prev_data_entry = {}
                rec_existing = positions_map.get((sym, side_key))
                if isinstance(rec_existing, dict):
                    try:
                        prev_data_entry = dict(rec_existing.get("data") or {})
                    except Exception:
                        prev_data_entry = {}
                try:
                    liquidation_price = float(
                        p.get("liquidationPrice")
                        or p.get("liqPrice")
                        or prev_data_entry.get("liquidation_price")
                        or 0.0
                    )
                except Exception:
                    liquidation_price = 0.0
                stop_loss_enabled = False
                if side_key in ("L", "S"):
                    try:
                        stop_loss_enabled = self._position_stop_loss_enabled(sym, side_key)
                    except Exception:
                        stop_loss_enabled = False
                data = {
                    "symbol": sym,
                    "qty": abs(amt),
                    "mark": mark,
                    "size_usdt": value,
                    "margin_usdt": margin_usdt,
                    "margin_balance": margin_balance_val,
                    "wallet_balance": wallet_balance_val,
                    "maint_margin": maint,
                    "open_order_margin": open_order_margin,
                    "margin_ratio": margin_ratio,
                    "margin_ratio_raw": normalize_margin_ratio(raw_margin_ratio_val),
                    "margin_ratio_calc": calc_ratio,
                    "pnl_roi": pnl_roi,
                    "pnl_value": pnl,
                    "roi_percent": roi_pct,
                    "side_key": side_key,
                    "update_time": update_time,
                    "entry_price": entry_price if entry_price > 0 else None,
                    "leverage": leverage,
                    "liquidation_price": liquidation_price if liquidation_price > 0 else None,
                    "interval": None,
                    "interval_display": None,
                    "open_time": None,
                }
                rec = positions_map.get((sym, side_key))
                prev_data_entry = {}
                prev_indicators: list[str] = []
                if rec and isinstance(rec, dict):
                    try:
                        prev_data_entry = dict(rec.get("data") or {})
                    except Exception:
                        prev_data_entry = {}
                    try:
                        prev_indicators = list(rec.get("indicators") or [])
                    except Exception:
                        prev_indicators = []
                row_triggers = _resolve_trigger_indicators_safe(
                    prev_data_entry.get("trigger_indicators"),
                    prev_data_entry.get("trigger_desc"),
                )
                if not row_triggers and prev_indicators:
                    cleaned = [str(t).strip() for t in prev_indicators if str(t).strip()]
                    if cleaned:
                        row_triggers = sorted(dict.fromkeys(cleaned))
                if rec is None:
                    rec = {
                        "symbol": sym,
                        "side_key": side_key,
                        "entry_tf": "-",
                        "open_time": "-",
                        "close_time": "-",
                        "status": "Active",
                    }
                else:
                    rec = dict(rec)
                rec["data"] = data
                rec["leverage"] = data.get("leverage")
                rec["liquidation_price"] = data.get("liquidation_price")
                rec["status"] = "Active"
                rec["close_time"] = "-"
                if (not rec.get("entry_tf") or rec["entry_tf"] == "-") and data.get("interval_display"):
                    rec["entry_tf"] = data["interval_display"]
                allocations_existing = _copy_allocations_for_key(alloc_map_global, sym, side_key)
                interval_display: dict[str, str] = {}
                interval_lookup: dict[str, str] = {}
                intervals_from_alloc: set[str] = set()
                interval_trigger_map: dict[str, set[str]] = {}
                trigger_union: set[str] = set()
                if allocations_existing:
                    rec["allocations"] = allocations_existing
                    for alloc in allocations_existing:
                        if not isinstance(alloc, dict):
                            continue
                        iv_disp = alloc.get("interval_display") or alloc.get("interval")
                        iv_raw = alloc.get("interval")
                        status_flag = str(alloc.get("status") or "Active").strip().lower()
                        try:
                            qty_val = abs(float(alloc.get("qty") or 0.0))
                        except Exception:
                            qty_val = None
                        is_active = status_flag not in {"closed", "error"}
                        if qty_val is not None and qty_val <= 0.0:
                            qty_val = 0.0
                        if qty_val:
                            is_active = True
                        normalized_iv = ""
                        key_iv = "-"
                        if iv_disp:
                            iv_text = str(iv_disp).strip()
                            if iv_text:
                                try:
                                    canon_iv = self._canonicalize_interval(iv_text)
                                except Exception:
                                    canon_iv = None
                                normalized_iv = (canon_iv or iv_text).strip()
                                if normalized_iv:
                                    key_iv = normalized_iv.lower()
                                    if is_active:
                                        intervals_from_alloc.add(normalized_iv)
                                    if key_iv and (canon_iv or iv_text):
                                        interval_display.setdefault(key_iv, canon_iv or iv_text)
                                        lookup_val = str(iv_raw or iv_text).strip()
                                        if lookup_val:
                                            interval_lookup.setdefault(key_iv, lookup_val)
                        normalized_triggers = _resolve_trigger_indicators_safe(
                            alloc.get("trigger_indicators"),
                            alloc.get("trigger_desc"),
                        )
                        if normalized_triggers:
                            alloc["trigger_indicators"] = normalized_triggers
                        elif alloc.get("trigger_indicators"):
                            alloc.pop("trigger_indicators", None)
                        if is_active and normalized_triggers:
                            trigger_union.update(normalized_triggers)
                            interval_trigger_map.setdefault(key_iv, set()).update(normalized_triggers)
                    if not data.get("trigger_desc"):
                        for alloc in allocations_existing:
                            if not isinstance(alloc, dict):
                                continue
                            desc = alloc.get("trigger_desc")
                            if desc:
                                data["trigger_desc"] = desc
                                break
                    if trigger_union:
                        indicators_union = sorted(dict.fromkeys(trigger_union))
                        rec["indicators"] = indicators_union
                        data["trigger_indicators"] = indicators_union
                    elif row_triggers:
                        rec["indicators"] = row_triggers
                        data["trigger_indicators"] = row_triggers
                elif row_triggers:
                    rec["indicators"] = row_triggers
                    data["trigger_indicators"] = row_triggers
                if not data.get("trigger_desc") and prev_data_entry.get("trigger_desc"):
                    data["trigger_desc"] = prev_data_entry.get("trigger_desc")
                try:
                    getattr(self, "_pending_close_times", {}).pop((sym, side_key), None)
                except Exception:
                    pass
                _apply_interval_metadata_to_row(
                    self,
                    sym=sym,
                    side_key=side_key,
                    rec=rec,
                    data=data,
                    allocations_existing=allocations_existing,
                    intervals_from_alloc=intervals_from_alloc,
                    interval_display=interval_display,
                    interval_lookup=interval_lookup,
                    interval_trigger_map=interval_trigger_map,
                    trigger_union=trigger_union,
                )
                rec["stop_loss_enabled"] = stop_loss_enabled
                positions_map[(sym, side_key)] = rec
            except Exception:
                continue
    except Exception:
        pass
