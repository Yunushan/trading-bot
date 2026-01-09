
import argparse, json, time
from app.binance_wrapper import BinanceWrapper

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", choices=["BUY","SELL"], required=True)
    ap.add_argument("--pct", type=float, required=True)
    ap.add_argument("--mode", default="Demo/Testnet")
    ap.add_argument("--leverage", type=int, default=20)
    ap.add_argument("--margin", default="ISOLATED")
    ap.add_argument("--reverse_pct", type=float, default=None)
    args = ap.parse_args()

    bw = BinanceWrapper(mode=args.mode, account_type="FUTURES")
    # open
    opened = bw.open_percent_lot(args.symbol, args.side, args.pct, leverage=args.leverage, margin_mode=args.margin)
    print("OPENED", json.dumps(opened, indent=2))
    lot_id = opened["lot_id"]
    print("lot_id:", lot_id)
    # prompt to close
    print("Sleeping 3s before closing...")
    time.sleep(3)
    closed = bw.close_lot_and_optional_reverse(lot_id, reverse_percent=args.reverse_pct, leverage=args.leverage, margin_mode=args.margin)
    print("CLOSED", json.dumps(closed, indent=2))

if __name__ == "__main__":
    main()
