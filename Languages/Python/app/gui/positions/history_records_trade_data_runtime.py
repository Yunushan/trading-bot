from __future__ import annotations

from app.integrations.exchanges.binance import normalize_margin_ratio


def _compute_trade_data(
    base_data: dict,
    allocation: dict | None,
    side_key: str,
    status: str,
    *,
    derive_margin_snapshot,
) -> dict:
    data = dict(base_data)
    base_qty = float(base_data.get("qty") or 0.0)
    base_margin = float(base_data.get("margin_usdt") or 0.0)
    base_pnl = float(base_data.get("pnl_value") or 0.0)
    base_roi = float(base_data.get("roi_percent") or 0.0)
    base_size = float(base_data.get("size_usdt") or 0.0)
    mark = float(base_data.get("mark") or 0.0)
    entry_price = float(base_data.get("entry_price") or 0.0)
    leverage = int(base_data.get("leverage") or 0) if base_data.get("leverage") else 0
    base_margin_ratio = normalize_margin_ratio(base_data.get("margin_ratio"))
    base_margin_balance = float(base_data.get("margin_balance") or 0.0)
    base_maint_margin = float(base_data.get("maint_margin") or 0.0)

    qty = base_qty
    margin = base_margin
    notional = base_size
    status_lower = str(status or "").strip().lower()
    pnl = base_pnl
    margin_ratio = 0.0
    margin_balance_val = 0.0
    maint_margin_val = 0.0
    base_liq_price = None

    def _extract_liq_value(candidate):
        try:
            if candidate is None or candidate == "":
                return None
            value = float(candidate)
            return value if value > 0.0 else None
        except Exception:
            return None

    for cand in (
        base_data.get("liquidation_price"),
        base_data.get("liquidationPrice"),
        base_data.get("liq_price"),
        base_data.get("liqPrice"),
    ):
        found = _extract_liq_value(cand)
        if found:
            base_liq_price = found
            break
    if not base_liq_price:
        raw_base = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
        if raw_base:
            for cand in (raw_base.get("liquidationPrice"), raw_base.get("liqPrice")):
                found = _extract_liq_value(cand)
                if found:
                    base_liq_price = found
                    break

    if allocation:
        try:
            qty = abs(float(allocation.get("qty") or 0.0))
        except Exception:
            qty = max(base_qty, 0.0)
        try:
            entry_price_alloc = float(allocation.get("entry_price") or 0.0)
            if entry_price_alloc > 0:
                entry_price = entry_price_alloc
        except Exception:
            pass
        try:
            leverage_alloc = int(allocation.get("leverage") or 0)
            if leverage_alloc:
                leverage = leverage_alloc
        except Exception:
            pass
        try:
            margin = float(allocation.get("margin_usdt") or 0.0)
        except Exception:
            margin = 0.0
        try:
            notional = float(allocation.get("notional") or 0.0)
        except Exception:
            notional = 0.0
        if base_liq_price is None:
            for cand in (
                allocation.get("liquidation_price"),
                allocation.get("liquidationPrice"),
                allocation.get("liq_price"),
                allocation.get("liqPrice"),
            ):
                found = _extract_liq_value(cand)
                if found:
                    base_liq_price = found
                    break
        alloc_pnl = allocation.get("pnl_value")
        if alloc_pnl is not None:
            try:
                pnl = float(alloc_pnl)
            except Exception:
                pnl = base_pnl
        if allocation.get("status"):
            status_lower = str(allocation.get("status")).strip().lower()
    allocation_data = allocation if isinstance(allocation, dict) else {}
    margin_ratio = normalize_margin_ratio(allocation_data.get("margin_ratio"))
    try:
        margin_balance_val = float(allocation_data.get("margin_balance") or 0.0)
    except Exception:
        margin_balance_val = 0.0
    try:
        maint_margin_val = float(allocation_data.get("maint_margin") or 0.0)
    except Exception:
        maint_margin_val = 0.0

    qty = max(qty, 0.0)
    if notional <= 0:
        if entry_price > 0 and qty > 0:
            notional = entry_price * qty
        elif mark > 0 and qty > 0:
            notional = mark * qty
        elif base_size > 0 and base_qty > 0:
            notional = base_size * (qty / base_qty)
        else:
            notional = 0.0

    if margin <= 0:
        if leverage and leverage > 0 and entry_price > 0 and qty > 0:
            margin = (entry_price * qty) / leverage
        elif base_margin > 0 and base_qty > 0:
            margin = base_margin * (qty / base_qty)
        else:
            margin = 0.0
    margin = max(margin, 0.0)

    if status_lower == "active":
        if allocation is None or allocation.get("pnl_value") is None:
            direction = 1.0 if side_key == "L" else -1.0 if side_key == "S" else 0.0
            if direction != 0.0 and entry_price > 0 and mark > 0 and qty > 0:
                pnl = direction * (mark - entry_price) * qty
            elif base_pnl and base_qty > 0:
                pnl = base_pnl * (qty / base_qty)
    else:
        if allocation is None or allocation.get("pnl_value") is None:
            if base_pnl and base_qty > 0:
                pnl = base_pnl * (qty / base_qty)
            else:
                pnl = base_pnl

    roi_percent = (pnl / margin * 100.0) if margin > 0 else base_roi
    pnl_roi = f"{pnl:+.2f} USDT ({roi_percent:+.2f}%)" if margin > 0 else f"{pnl:+.2f} USDT"

    raw_position = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
    if margin_ratio <= 0.0:
        margin_ratio = base_margin_ratio
    if margin_balance_val <= 0.0:
        margin_balance_val = base_margin_balance
    if maint_margin_val <= 0.0:
        maint_margin_val = base_maint_margin
    if margin_ratio <= 0.0 and raw_position is not None:
        snap_margin, snap_balance, snap_maint, snap_unreal_loss = derive_margin_snapshot(
            raw_position,
            qty_hint=qty if qty > 0 else base_qty,
            entry_price_hint=entry_price if entry_price > 0 else base_data.get("entry_price") or 0.0,
        )
        if margin <= 0.0 and snap_margin > 0.0:
            margin = snap_margin
        if margin_balance_val <= 0.0 and snap_balance > 0.0:
            margin_balance_val = snap_balance
        if maint_margin_val <= 0.0 and snap_maint > 0.0:
            maint_margin_val = snap_maint
        if margin_ratio <= 0.0 and snap_balance > 0.0 and snap_maint > 0.0:
            margin_ratio = ((snap_maint + snap_unreal_loss) / snap_balance) * 100.0
    if margin_balance_val <= 0.0:
        margin_balance_val = margin + max(pnl, 0.0)
    margin_balance_val = max(margin_balance_val, 0.0)
    if margin_ratio <= 0.0 and margin_balance_val > 0 and maint_margin_val > 0.0:
        unrealized_loss = max(0.0, -pnl) if status_lower == "active" else 0.0
        margin_ratio = ((maint_margin_val + unrealized_loss) / margin_balance_val) * 100.0

    data.update(
        {
            "qty": qty,
            "margin_usdt": margin,
            "pnl_value": pnl,
            "roi_percent": roi_percent,
            "pnl_roi": pnl_roi,
            "size_usdt": max(notional, 0.0),
            "margin_balance": max(margin_balance_val, 0.0),
            "maint_margin": max(0.0, maint_margin_val),
            "margin_ratio": max(margin_ratio, 0.0),
        }
    )
    trigger_inds = []
    allocation_trigger_indicators = allocation.get("trigger_indicators") if allocation else None
    base_trigger_indicators = base_data.get("trigger_indicators")
    if isinstance(allocation_trigger_indicators, (list, tuple, set)):
        trigger_inds = [
            str(ind).strip()
            for ind in allocation_trigger_indicators
            if str(ind).strip()
        ]
    elif isinstance(base_trigger_indicators, (list, tuple, set)):
        trigger_inds = [
            str(ind).strip()
            for ind in base_trigger_indicators
            if str(ind).strip()
        ]
    if trigger_inds:
        trigger_inds = list(dict.fromkeys(trigger_inds))
        data["trigger_indicators"] = trigger_inds
    if entry_price > 0:
        data["entry_price"] = entry_price
    if leverage:
        data["leverage"] = leverage
    if base_liq_price:
        data["liquidation_price"] = base_liq_price
    if allocation and isinstance(allocation, dict) and allocation.get("trigger_desc"):
        data["trigger_desc"] = allocation.get("trigger_desc")
    elif base_data.get("trigger_desc") and not data.get("trigger_desc"):
        data["trigger_desc"] = base_data.get("trigger_desc")
    if allocation and isinstance(allocation, dict):
        for field_name in (
            "entry_fee_usdt",
            "close_fee_usdt",
            "realized_pnl_usdt",
            "net_realized_usdt",
        ):
            value = allocation.get(field_name)
            if value is None or value == "":
                continue
            try:
                data[field_name] = float(value)
            except Exception:
                data[field_name] = value
        fills_meta = allocation.get("fills_meta")
        if isinstance(fills_meta, dict) and fills_meta:
            data["fills_meta"] = dict(fills_meta)
    return data
