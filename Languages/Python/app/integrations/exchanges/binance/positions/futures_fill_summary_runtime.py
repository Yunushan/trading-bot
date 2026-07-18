from __future__ import annotations

import math
import time


def _finite_float(value: float | str | None) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _convert_asset_to_usdt(self, amount: float | str | None, asset: str | None) -> float:
    """Convert a commission amount into USDT using last price when needed."""
    value = _finite_float(amount)
    if value == 0.0:
        return 0.0
    code = str(asset or "").upper()
    if not code:
        return value
    if code in {"USDT", "BUSD", "USD"}:
        return value
    try:
        px = _finite_float(self.get_last_price(f"{code}USDT"))
        if px > 0.0:
            return value * px
    except Exception:
        pass
    return value


def _summarize_futures_order_fills(
    self,
    symbol: str,
    order_id: int | str | None,
    *,
    attempts: int = 2,
    delay: float = 0.2,
) -> dict:
    """Fetch fills for an order to expose realized PnL and commission totals."""
    sym = str(symbol or "").upper()
    if not sym or order_id is None:
        return {}
    try:
        oid = int(float(order_id))
    except Exception:
        return {}

    trades: list[dict] = []
    for attempt in range(max(1, attempts) + 1):
        try:
            self._throttle_request("/fapi/v1/userTrades")
            trades = self.client.futures_account_trades(symbol=sym, orderId=oid, limit=100) or []
        except Exception:
            trades = []
        if trades:
            break
        if attempt < attempts:
            try:
                time.sleep(max(0.0, float(delay)))
            except Exception:
                pass
    if not trades:
        return {}

    total_qty = 0.0
    total_quote = 0.0
    realized_pnl = 0.0
    commission_by_asset: dict[str, float] = {}
    for trade in trades:
        qty = abs(_finite_float(trade.get("qty")))
        price = _finite_float(trade.get("price"))
        total_qty += qty
        total_quote += qty * price
        realized_pnl += _finite_float(trade.get("realizedPnl"))
        commission_val = _finite_float(trade.get("commission"))
        asset = str(trade.get("commissionAsset") or "").upper() or "USDT"
        commission_by_asset[asset] = commission_by_asset.get(asset, 0.0) + commission_val

    avg_price = (total_quote / total_qty) if total_qty > 0 else 0.0
    commission_usdt = 0.0
    for asset, amount in commission_by_asset.items():
        commission_usdt += self._convert_asset_to_usdt(amount, asset)
    net_realized = realized_pnl - commission_usdt
    return {
        "order_id": oid,
        "filled_qty": total_qty,
        "avg_price": avg_price,
        "realized_pnl": realized_pnl,
        "commission_breakdown": commission_by_asset,
        "commission_usdt": commission_usdt,
        "net_realized": net_realized,
        "trade_count": len(trades),
    }
