from binance.client import Client
import sys, time

def ensure_symbol(client: Client, symbol: str, leverage: int, margin_mode: str):
    margin_mode = margin_mode.upper()
    try:
        try:
            client.futures_change_margin_type(symbol=symbol, marginType=margin_mode)
            print(f"[OK] margin {symbol} -> {margin_mode}")
        except Exception as e:
            msg = str(getattr(e, 'message', '') or e)
            if "-4046" in msg or "No need to change margin type" in msg:
                print(f"[OK] margin {symbol} already {margin_mode}")
            else:
                print(f"[WARN] margin {symbol} {e}")
        try:
            client.futures_change_leverage(symbol=symbol, leverage=int(leverage))
            print(f"[OK] leverage {symbol} -> {leverage}")
        except Exception as e:
            print(f"[WARN] leverage {symbol} {e}")
    except Exception as e:
        print(f"[ERR] {symbol} {e}")

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python tools/configure_margin.py <api_key> <api_secret> <mode:live|test> <leverage:int> <ISOLATED|CROSS> SYMBOL1 SYMBOL2 ...")
        sys.exit(1)
    api_key, api_secret, mode, lev, mm, *symbols = sys.argv[1:]
    base_url = "https://testnet.binancefuture.com" if mode.lower().startswith("test") else None
    client = Client(api_key, api_secret, testnet=bool(base_url), futures=True)
    if base_url:
        client.FUTURES_URL = base_url
    for s in symbols:
        ensure_symbol(client, s.upper(), int(lev), mm)
        time.sleep(0.1)
