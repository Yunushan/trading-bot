import argparse
import time
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from app.strategy import StrategyEngine


class DummyBinance:
    def __init__(self, *, symbol: str, position_amt: float, position_side: str, last_price: float):
        self.orders: list[tuple[str, float, str, str | None]] = []
        self._symbol = symbol.upper()
        self._position_amt = position_amt
        self._position_side = position_side.upper()
        self._last_price = last_price

    def close_futures_leg_exact(self, symbol, qty, side, position_side=None):
        self.orders.append((symbol, float(qty), side.upper(), position_side))
        return {"ok": True, "info": {"executedQty": qty}}

    def list_open_futures_positions(self, *_, **__):
        amt = self._position_amt if self._position_side == "LONG" else -abs(self._position_amt)
        return [
            {
                "symbol": self._symbol,
                "positionAmt": amt,
                "positionSide": self._position_side,
            }
            for _ in (0,)
        ]

    def get_futures_dual_side(self):
        return True

    def get_last_price(self, symbol):
        return self._last_price


parser = argparse.ArgumentParser(description="StrategyEngine indicator close harness")
parser.add_argument("--symbol", default="PUMPUSDT")
parser.add_argument("--interval", default="1m", help="Interval for running job")
parser.add_argument("--leg-interval", default=None, help="Interval label stored on the leg (default equals --interval)")
parser.add_argument("--indicator", default="stoch_rsi", help="Indicator key (e.g., stoch_rsi, rsi, willr)")
parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"], help="Existing leg side to close")
parser.add_argument("--qty", type=float, default=1.0, help="Quantity on the existing leg")
parser.add_argument("--entry-price", type=float, default=1.0)
parser.add_argument("--leverage", type=float, default=20.0)
parser.add_argument("--margin", type=float, default=0.05)
parser.add_argument("--position-side", choices=["LONG", "SHORT"], default=None, help="Exchange positionSide hint (default derived from --side)")
parser.add_argument("--close-side", choices=["BUY", "SELL"], default=None, help="Exchange order side used to close (default opposite of --side)")
parser.add_argument("--last-price", type=float, default=1.0)
parser.add_argument("--buy-threshold", type=float, default=20.0, help="Indicator buy threshold")
parser.add_argument("--sell-threshold", type=float, default=80.0, help="Indicator sell threshold")
parser.add_argument("--ledger-id", default="test-ledger")
parser.add_argument("--age-seconds", type=float, default=5.0, help="Age of the leg in seconds")
args = parser.parse_args()

indicator_key = args.indicator.strip().lower()
leg_interval = args.leg_interval or args.interval
open_side = args.side.upper()
close_side = args.close_side or ("SELL" if open_side == "BUY" else "BUY")
position_side = args.position_side or ("LONG" if open_side == "BUY" else "SHORT")

cfg = {
    "symbol": args.symbol.upper(),
    "interval": args.interval,
    "side": "BOTH",
    "indicators": {
        indicator_key: {
            "enabled": True,
            "buy_value": args.buy_threshold,
            "sell_value": args.sell_threshold,
        }
    },
    "account_type": "FUTURES",
}

binance = DummyBinance(
    symbol=args.symbol,
    position_amt=args.qty,
    position_side=position_side,
    last_price=args.last_price,
)
engine = StrategyEngine(binance, cfg, print)

entry = {
    "qty": float(args.qty),
    "timestamp": time.time() - max(0.0, args.age_seconds),
    "entry_price": float(args.entry_price),
    "leverage": args.leverage,
    "margin_usdt": args.margin,
    "ledger_id": args.ledger_id,
    "trigger_signature": [indicator_key],
    "trigger_indicators": [indicator_key],
    "indicator_keys": [indicator_key],
}
engine._append_leg_entry((args.symbol.upper(), leg_interval, open_side), entry)

print("Attempting close:", entry)
closed_count, closed_qty = engine._close_indicator_positions(
    {"symbol": args.symbol.upper(), "interval": args.interval},
    args.interval,
    indicator_key,
    open_side,
    position_side,
    signature_hint=(indicator_key,),
)
print(f"Closed entries: {closed_count}, quantity: {closed_qty}")
print("Orders sent:", binance.orders)
