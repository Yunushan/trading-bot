import os
import copy

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
    "backtest": {
        "symbols": ["BTCUSDT"],
        "intervals": ["1h"],
        "capital": 1000.0,
        "logic": "AND",
        "symbol_source": "Futures",
        "start_date": None,
        "end_date": None,
        "position_pct": 2.0,
        "side": "BOTH",
        "margin_mode": "Isolated",
        "position_mode": "Hedge",
        "assets_mode": "Single-Asset",
        "leverage": 5,
        "indicators": {},
    },
    "runtime_symbol_interval_pairs": [],
    "backtest_symbol_interval_pairs": [],
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

INDICATOR_DISPLAY_NAMES = {
    'ma': 'Moving Average (MA)',
    'donchian': 'Donchian Channels (DC)',
    'psar': 'Parabolic SAR (PSAR)',
    'bb': 'Bollinger Bands (BB)',
    'rsi': 'Relative Strength Index (RSI)',
    'volume': 'Volume',
    'stoch_rsi': 'Stochastic RSI (SRSI)',
    'willr': 'Williams %R',
    'macd': 'Moving Average Convergence/Divergence (MACD)',
}

DEFAULT_CONFIG["backtest"]["indicators"] = copy.deepcopy(DEFAULT_CONFIG["indicators"])
if "rsi" in DEFAULT_CONFIG["backtest"]["indicators"]:
    DEFAULT_CONFIG["backtest"]["indicators"]["rsi"].update({"enabled": True, "buy_value": 30, "sell_value": 70})

