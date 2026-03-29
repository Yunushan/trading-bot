from __future__ import annotations

import re

_QUOTE_ASSETS = [
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "DAI",
    "USD",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "TRY",
    "GBP",
    "AUD",
    "BRL",
    "RUB",
    "IDR",
    "UAH",
    "ZAR",
    "BIDR",
    "PAX",
]


def _normalize_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper().replace("/", "")
    if raw.endswith(".P"):
        raw = raw[:-2]
    return raw


def _spot_symbol_with_underscore(symbol: str) -> str:
    if "_" in symbol:
        return symbol
    for quote in _QUOTE_ASSETS:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            return f"{base}_{quote}"
    return symbol


def _build_binance_url(symbol: str, interval: str | None, market: str | None) -> str:
    sym = _normalize_symbol(symbol)
    interval_param = str(interval or "").strip()
    if interval_param:
        interval_param = re.sub(r"\s+", "", interval_param)
    market_key = (market or "").strip().lower()
    if market_key == "spot":
        sym = _spot_symbol_with_underscore(sym)
        url = f"https://www.binance.com/en/trade/{sym}?type=spot"
    else:
        url = f"https://www.binance.com/en/futures/{sym}"
    if interval_param:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}interval={interval_param}"
    return url
