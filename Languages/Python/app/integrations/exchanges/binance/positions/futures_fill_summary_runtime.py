from __future__ import annotations

import time


def _convert_asset_to_usdt(self, amount: float | str | None, asset: str | None) -> float:
    """Convert a commission amount into USDT using last price when needed."""
    try:
        value = float(amount or 0.0)
    except Exception:
        return 0.0
    if value == 0.0:
        return 0.0
    code = str(asset or "").upper()
    if not code:
        return value
    if code in {"USDT", "BUSD", "USD"}:
        return value
    try:
        px = float(self.get_last_price(f"{code}USDT") or 0.0)
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
        try:
            qty = abs(float(trade.get("qty") or 0.0))
        except Exception:
            qty = 0.0
        try:
            price = float(trade.get("price") or 0.0)
        except Exception:
            price = 0.0
        total_qty += qty
        total_quote += qty * price
        try:
            realized_pnl += float(trade.get("realizedPnl") or 0.0)
        except Exception:
            pass
        try:
            commission_val = float(trade.get("commission") or 0.0)
        except Exception:
            commission_val = 0.0
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
