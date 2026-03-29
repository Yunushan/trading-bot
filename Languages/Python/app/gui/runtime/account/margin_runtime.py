from __future__ import annotations


def _derive_margin_snapshot(
    position: dict | None,
    qty_hint: float = 0.0,
    entry_price_hint: float = 0.0,
) -> tuple[float, float, float, float]:
    """Return margin, balance, maintenance requirement, and unrealized loss for a futures position."""
    if not isinstance(position, dict):
        return 0.0, 0.0, 0.0, 0.0
    try:
        margin = float(
            position.get("isolatedMargin")
            or position.get("isolatedWallet")
            or position.get("initialMargin")
            or 0.0
        )
    except Exception:
        margin = 0.0
    try:
        leverage = float(position.get("leverage") or 0.0)
    except Exception:
        leverage = 0.0
    try:
        entry_price = float(position.get("entryPrice") or 0.0)
    except Exception:
        entry_price = 0.0
    if entry_price <= 0.0:
        entry_price = max(0.0, float(entry_price_hint or 0.0))
    try:
        notional_val = abs(float(position.get("notional") or 0.0))
    except Exception:
        notional_val = 0.0
    if notional_val <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
        notional_val = entry_price * qty_hint
    if margin <= 0.0:
        if leverage > 0.0 and notional_val > 0.0:
            margin = notional_val / leverage
        elif notional_val > 0.0:
            margin = notional_val
    if margin <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
        if leverage > 0.0:
            margin = (entry_price * qty_hint) / leverage
        else:
            margin = entry_price * qty_hint
    margin = max(margin, 0.0)
    try:
        margin_balance = float(position.get("marginBalance") or 0.0)
    except Exception:
        margin_balance = 0.0
    try:
        iso_wallet = float(position.get("isolatedWallet") or 0.0)
    except Exception:
        iso_wallet = 0.0
    try:
        unrealized_profit = float(position.get("unRealizedProfit") or 0.0)
    except Exception:
        unrealized_profit = 0.0
    if margin_balance <= 0.0 and iso_wallet > 0.0:
        margin_balance = iso_wallet + unrealized_profit
    if margin_balance <= 0.0 and iso_wallet > 0.0:
        margin_balance = iso_wallet
    if margin_balance <= 0.0 and margin > 0.0:
        margin_balance = margin + unrealized_profit
    if margin_balance <= 0.0 and margin > 0.0:
        margin_balance = margin
    margin_balance = max(margin_balance, 0.0)
    try:
        maint_margin = float(position.get("maintMargin") or position.get("maintenanceMargin") or 0.0)
    except Exception:
        maint_margin = 0.0
    try:
        maint_rate = float(
            position.get("maintMarginRate")
            or position.get("maintenanceMarginRate")
            or position.get("maintMarginRatio")
            or position.get("maintenanceMarginRatio")
            or 0.0
        )
    except Exception:
        maint_rate = 0.0
    if maint_rate > 1.0:
        maint_rate = maint_rate / 100.0
    if maint_margin <= 0.0 and maint_rate > 0.0 and notional_val > 0.0:
        maint_margin = notional_val * maint_rate
    if margin_balance > 0.0 and maint_margin > margin_balance:
        maint_margin = margin_balance
    unrealized_loss = max(0.0, -unrealized_profit)
    return margin, margin_balance, maint_margin, unrealized_loss
