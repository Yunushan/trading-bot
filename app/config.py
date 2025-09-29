import os

DEFAULT_CONFIG = {
    "api_key": os.getenv("BINANCE_API_KEY", ""),
    "api_secret": os.getenv("BINANCE_API_SECRET", ""),
    "mode": "Live",              # "Live" or "Demo/Testnet"
    "account_type": "Futures",   # "Spot" or "Futures"
    "margin_mode": "Isolated",   # For Futures: "Cross" or "Isolated"
    "symbols": ["BTCUSDT"],
    "intervals": ["1m"],
    "lookback": 200,
    "leverage": 5,
    "tif": "GTC",
    "gtd_minutes": 30,           # Only used when tif == 'GTD'
    "position_mode": "Hedge",    # "One-way" or "Hedge"
    "assets_mode": "Single-Asset",
    "indicator_source": "Binance futures",  # Binance spot | Binance futures | TradingView | Bybit
    "indicators": {
        "ma":        {"enabled": False, "length": 20, "type": "SMA", "buy_value": None, "sell_value": None},
        "donchian":  {"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        "psar":      {"enabled": False, "af": 0.02, "max_af": 0.2, "buy_value": None, "sell_value": None},
        "bb":        {"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
        "rsi":       {"enabled": True,  "length": 14, "buy_value": None, "sell_value": None},
        "volume":    {"enabled": False, "buy_value": None, "sell_value": None},
        "stoch_rsi": {"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
        "willr":     {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        "macd":      {"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
    },
    "side": "BOTH",              # "BUY", "SELL", or "BOTH"
    "position_pct": 2.0,         # % of USDT to allocate (Futures: notional before leverage)
    "order_type": "MARKET",
    "max_auto_bump_percent": 5.0,
}

# Central registry of available indicators and their default params (all disabled by default)
AVAILABLE_INDICATORS = {
    "ma":        {"enabled": False, "length": 20, "type": "SMA", "buy_value": None, "sell_value": None},
    "donchian":  {"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
    "psar":      {"enabled": False, "af": 0.02, "max_af": 0.2, "buy_value": None, "sell_value": None},
    "bb":        {"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
    "rsi":       {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    "volume":    {"enabled": False, "buy_value": None, "sell_value": None},
    "stoch_rsi": {"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
    "willr":     {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    "macd":      {"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
}
