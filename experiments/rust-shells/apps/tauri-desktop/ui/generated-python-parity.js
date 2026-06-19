// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.
(function () {
  window.PythonParityContract = Object.freeze({
  "accountModeOptions": [
    "Classic Trading",
    "Portfolio Margin"
  ],
  "accountTypeOptions": [
    {
      "key": "Spot",
      "label": "Spot",
      "value": "Spot"
    },
    {
      "key": "Futures",
      "label": "Futures",
      "value": "Futures"
    }
  ],
  "assetsModeOptions": [
    {
      "key": "Single-Asset",
      "label": "Single-Asset Mode",
      "value": "Single-Asset"
    },
    {
      "key": "Multi-Assets",
      "label": "Multi-Assets Mode",
      "value": "Multi-Assets"
    }
  ],
  "backtestExecutionBackendOptions": [
    {
      "key": "local",
      "label": "local",
      "value": "local"
    },
    {
      "key": "service",
      "label": "service",
      "value": "service"
    }
  ],
  "backtestIntervals": [
    "1m",
    "3m",
    "5m",
    "10m",
    "15m",
    "20m",
    "30m",
    "1h",
    "2h",
    "3h",
    "4h",
    "5h",
    "6h",
    "7h",
    "8h",
    "9h",
    "10h",
    "11h",
    "12h",
    "1d",
    "2d",
    "3d",
    "4d",
    "5d",
    "6d",
    "1w",
    "2w",
    "3w",
    "1month",
    "2months",
    "3months",
    "6months",
    "1mo",
    "2mo",
    "3mo",
    "6mo",
    "1y",
    "2y"
  ],
  "backtestRunRequestFields": [
    "account_mode",
    "account_type",
    "api_key",
    "api_secret",
    "assets_mode",
    "backtest",
    "capital",
    "connector_backend",
    "end",
    "indicators",
    "intervals",
    "leverage",
    "logic",
    "margin_mode",
    "mdd_logic",
    "mode",
    "optimizer_combo_size",
    "optimizer_metric",
    "optimizer_min_trades",
    "optimizer_mode",
    "pair_overrides",
    "position_mode",
    "position_pct",
    "position_pct_units",
    "scan_mdd_limit",
    "scan_scope",
    "scan_top_n",
    "side",
    "start",
    "stop_loss",
    "symbol_source",
    "symbols"
  ],
  "backtestTemplates": [
    {
      "key": "volume_top50",
      "label": "First 50 Highest Volume"
    },
    {
      "key": "volume_last_week",
      "label": "Last 1 week \u00b7 2% per trade \u00b7 50 highest volume"
    },
    {
      "key": "top100_isolated_1pct_sl",
      "label": "Top 100, %2 per trade, isolated, %20 per trade SL"
    }
  ],
  "chartMarketOptions": [
    "Futures",
    "Spot"
  ],
  "chartViewKeys": [
    "tradingview",
    "original",
    "lightweight"
  ],
  "chartViewOptions": [
    {
      "key": "tradingview",
      "label": "TradingView",
      "value": "tradingview"
    },
    {
      "key": "original",
      "label": "Original",
      "value": "original"
    },
    {
      "key": "lightweight",
      "label": "TradingView Lightweight",
      "value": "lightweight"
    }
  ],
  "configModeOptions": [
    {
      "key": "Live",
      "label": "Live",
      "value": "Live"
    },
    {
      "key": "Demo",
      "label": "Demo",
      "value": "Demo"
    },
    {
      "key": "Testnet",
      "label": "Testnet",
      "value": "Testnet"
    }
  ],
  "connectorKeys": [
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance"
  ],
  "connectorOptions": [
    {
      "key": "binance-sdk-derivatives-trading-usds-futures",
      "label": "Binance SDK Derivatives Trading USD\u24c8 Futures (Official Recommended)"
    },
    {
      "key": "binance-sdk-derivatives-trading-coin-futures",
      "label": "Binance SDK Derivatives Trading COIN-M Futures"
    },
    {
      "key": "binance-sdk-spot",
      "label": "Binance SDK Spot (Official Recommended)"
    },
    {
      "key": "binance-connector",
      "label": "Binance Connector Python"
    },
    {
      "key": "ccxt",
      "label": "CCXT (Unified)"
    },
    {
      "key": "python-binance",
      "label": "python-binance (Community)"
    }
  ],
  "contractHash": "6e9fa38bf7e734ebf67f42ac1cde448ef09c8077a0d8b459c39fe6986d47fe18",
  "dashboardLoopChoices": [
    {
      "key": "30s",
      "label": "30 seconds",
      "value": "30s"
    },
    {
      "key": "45s",
      "label": "45 seconds",
      "value": "45s"
    },
    {
      "key": "1m",
      "label": "1 minute",
      "value": "1m"
    },
    {
      "key": "2m",
      "label": "2 minutes",
      "value": "2m"
    },
    {
      "key": "3m",
      "label": "3 minutes",
      "value": "3m"
    },
    {
      "key": "5m",
      "label": "5 minutes",
      "value": "5m"
    },
    {
      "key": "10m",
      "label": "10 minutes",
      "value": "10m"
    },
    {
      "key": "30m",
      "label": "30 minutes",
      "value": "30m"
    },
    {
      "key": "1h",
      "label": "1 hour",
      "value": "1h"
    },
    {
      "key": "2h",
      "label": "2 hours",
      "value": "2h"
    }
  ],
  "dashboardStrategyTemplates": [
    {
      "key": "",
      "label": "No Template"
    },
    {
      "key": "top10",
      "label": "Top 10 %2 per trade 1x Isolated"
    },
    {
      "key": "top50",
      "label": "Top 50 %2 per trade 1x"
    },
    {
      "key": "top100",
      "label": "Top 100 %1 per trade 1x"
    }
  ],
  "defaultBacktest": {
    "account_mode": "Classic Trading",
    "assets_mode": "Single-Asset",
    "capital": 1000.0,
    "connector_backend": "binance-sdk-derivatives-trading-usds-futures",
    "end_date": null,
    "execution_backend": "local",
    "indicators": {
      "adx": {
        "buy_value": 20,
        "enabled": false,
        "filter_operator": "gte",
        "length": 14,
        "sell_value": null,
        "signal_role": "filter"
      },
      "ao": {
        "buy_value": 0,
        "enabled": false,
        "fast": 5,
        "sell_value": 0,
        "slow": 34
      },
      "aroon": {
        "buy_value": 50,
        "enabled": false,
        "length": 25,
        "sell_value": -50
      },
      "atr": {
        "buy_value": 1.0,
        "enabled": false,
        "filter_operator": "gte",
        "length": 14,
        "sell_value": null,
        "signal_mode": "percent_of_close",
        "signal_role": "filter"
      },
      "bb": {
        "buy_value": 0,
        "enabled": false,
        "length": 20,
        "sell_value": 100,
        "signal_mode": "band_position",
        "std": 2
      },
      "bbw": {
        "buy_value": 5.0,
        "enabled": false,
        "length": 20,
        "sell_value": 2.0,
        "std": 2
      },
      "cci": {
        "buy_value": -100,
        "constant": 0.015,
        "enabled": false,
        "length": 20,
        "sell_value": 100
      },
      "chop": {
        "buy_value": 38.2,
        "enabled": false,
        "length": 14,
        "sell_value": 61.8
      },
      "cmf": {
        "buy_value": 0.05,
        "enabled": false,
        "length": 20,
        "sell_value": -0.05
      },
      "dmi": {
        "buy_value": 0,
        "enabled": false,
        "length": 14,
        "sell_value": 0
      },
      "donchian": {
        "buy_value": 0,
        "enabled": false,
        "length": 20,
        "sell_value": 100,
        "signal_mode": "band_position"
      },
      "ema": {
        "buy_value": 0,
        "enabled": false,
        "length": 20,
        "sell_value": 0,
        "signal_mode": "price_cross"
      },
      "ichimoku": {
        "base_length": 26,
        "buy_value": 0,
        "conversion_length": 9,
        "displacement": 26,
        "enabled": false,
        "sell_value": 0,
        "span_b_length": 52
      },
      "keltner": {
        "atr_length": 10,
        "buy_value": 0,
        "enabled": false,
        "length": 20,
        "multiplier": 2.0,
        "sell_value": 100,
        "signal_mode": "band_position"
      },
      "kst": {
        "buy_value": 0,
        "enabled": false,
        "roc1": 10,
        "roc2": 15,
        "roc3": 20,
        "roc4": 30,
        "sell_value": 0,
        "signal": 9,
        "sma1": 10,
        "sma2": 10,
        "sma3": 10,
        "sma4": 15
      },
      "ma": {
        "buy_value": 0,
        "enabled": false,
        "length": 20,
        "sell_value": 0,
        "signal_mode": "price_cross",
        "type": "SMA"
      },
      "macd": {
        "buy_value": 0,
        "enabled": false,
        "fast": 12,
        "sell_value": 0,
        "signal": 9,
        "slow": 26
      },
      "mfi": {
        "buy_value": 20,
        "enabled": false,
        "length": 14,
        "sell_value": 80
      },
      "natr": {
        "buy_value": 2.0,
        "enabled": false,
        "length": 14,
        "sell_value": 1.0
      },
      "obv": {
        "buy_value": 0,
        "enabled": false,
        "length": 3,
        "sell_value": 0,
        "signal_mode": "slope"
      },
      "ppo": {
        "buy_value": 0,
        "enabled": false,
        "fast": 12,
        "sell_value": 0,
        "signal": 9,
        "slow": 26
      },
      "psar": {
        "af": 0.02,
        "buy_value": 0,
        "enabled": false,
        "max_af": 0.2,
        "sell_value": 0,
        "signal_mode": "price_cross"
      },
      "roc": {
        "buy_value": 0,
        "enabled": false,
        "length": 12,
        "sell_value": 0
      },
      "rsi": {
        "buy_value": 30,
        "enabled": true,
        "length": 14,
        "sell_value": 70
      },
      "rvol": {
        "buy_value": 1.5,
        "enabled": false,
        "length": 20,
        "sell_value": 0.75
      },
      "stoch_rsi": {
        "buy_value": 20,
        "enabled": false,
        "length": 14,
        "sell_value": 80,
        "smooth_d": 3,
        "smooth_k": 3
      },
      "stochastic": {
        "buy_value": 20,
        "enabled": false,
        "length": 14,
        "sell_value": 80,
        "smooth_d": 3,
        "smooth_k": 3
      },
      "supertrend": {
        "atr_period": 10,
        "buy_value": 0,
        "enabled": false,
        "multiplier": 3.0,
        "sell_value": 0,
        "signal_mode": "price_cross"
      },
      "trix": {
        "buy_value": 0,
        "enabled": false,
        "length": 15,
        "sell_value": 0
      },
      "uo": {
        "buy_value": 30,
        "enabled": false,
        "long": 28,
        "medium": 14,
        "sell_value": 70,
        "short": 7
      },
      "volume": {
        "buy_value": 1.0,
        "enabled": false,
        "filter_operator": "gte",
        "length": 20,
        "sell_value": null,
        "signal_mode": "relative_to_sma",
        "signal_role": "filter"
      },
      "vwap": {
        "buy_value": 0,
        "enabled": false,
        "length": 20,
        "sell_value": 0,
        "signal_mode": "price_cross"
      },
      "willr": {
        "buy_value": -80,
        "enabled": false,
        "length": 14,
        "sell_value": -20
      }
    },
    "intervals": [
      "1h"
    ],
    "leverage": 20,
    "logic": "AND",
    "margin_mode": "Isolated",
    "mdd_logic": "per_trade",
    "optimizer_combo_size": 2,
    "optimizer_metric": "roi_percent",
    "optimizer_min_trades": 1,
    "optimizer_mode": "current",
    "position_mode": "Hedge",
    "position_pct": 2.0,
    "scan_auto_apply": false,
    "scan_mdd_limit": 10.0,
    "scan_scope": "selected",
    "scan_top_n": 200,
    "side": "BOTH",
    "start_date": null,
    "stop_loss": {
      "enabled": false,
      "mode": "usdt",
      "percent": 0.0,
      "scope": "per_trade",
      "usdt": 0.0
    },
    "symbol_source": "Futures",
    "symbols": [
      "BTCUSDT"
    ],
    "template": {
      "enabled": false,
      "name": null
    }
  },
  "defaultBacktestIntervals": [
    "1h"
  ],
  "defaultBacktestSymbols": [
    "BTCUSDT"
  ],
  "defaultChartSymbols": [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "TRXUSDT"
  ],
  "defaultExecution": {
    "account_mode": "Classic Trading",
    "account_type": "Futures",
    "assets_mode": "Single-Asset",
    "backtest_symbol_interval_pairs": [],
    "connector_order_block_circuit_breaker_enabled": true,
    "connector_order_block_pause_threshold": 2,
    "connector_order_block_window_seconds": 60.0,
    "connector_order_circuit_incident_log_backup_count": 1,
    "connector_order_circuit_incident_log_max_bytes": 2097152,
    "connector_order_circuit_incident_log_path": "",
    "gtd_minutes": 30,
    "intervals": [
      "1m"
    ],
    "lead_trader_enabled": false,
    "lead_trader_profile": null,
    "leverage": 1,
    "live_allow_auto_bump_to_min_order": false,
    "live_trading_acknowledgement": "",
    "live_trading_enabled": false,
    "live_trading_max_leverage": 20,
    "live_trading_max_position_pct": 10.0,
    "live_trading_max_session_orders": 100,
    "lookback": 200,
    "loop_interval_override": "1m",
    "margin_mode": "Isolated",
    "mode": "Demo/Testnet",
    "operational_account_snapshot_stale_seconds": 300.0,
    "operational_connector_snapshot_stale_seconds": 120.0,
    "operational_execution_heartbeat_stale_seconds": 10.0,
    "operational_live_order_gate_enabled": true,
    "operational_live_start_gate_enabled": true,
    "operational_portfolio_snapshot_stale_seconds": 300.0,
    "order_audit_backup_count": 1,
    "order_audit_enabled": true,
    "order_audit_log_path": "",
    "order_audit_max_bytes": 10485760,
    "order_type": "MARKET",
    "position_mode": "Hedge",
    "position_pct": 2.0,
    "runtime_symbol_interval_pairs": [],
    "side": "BOTH",
    "symbols": [
      "BTCUSDT"
    ],
    "tif": "GTC"
  },
  "defaultExecutionIntervals": [
    "1m"
  ],
  "defaultExecutionSymbols": [
    "BTCUSDT"
  ],
  "designOptions": [
    {
      "key": "Classic",
      "label": "Classic",
      "value": "Classic"
    },
    {
      "key": "Workstation",
      "label": "Workstation",
      "value": "Workstation"
    }
  ],
  "exchangeOptions": [
    {
      "badge": "",
      "disabled": false,
      "key": "Binance",
      "label": "Binance",
      "title": "Binance"
    },
    {
      "badge": "coming soon",
      "disabled": true,
      "key": "Bybit",
      "label": "Bybit (coming soon)",
      "title": "Bybit"
    },
    {
      "badge": "coming soon",
      "disabled": true,
      "key": "OKX",
      "label": "OKX (coming soon)",
      "title": "OKX"
    },
    {
      "badge": "coming soon",
      "disabled": true,
      "key": "Gate",
      "label": "Gate (coming soon)",
      "title": "Gate"
    },
    {
      "badge": "coming soon",
      "disabled": true,
      "key": "Bitget",
      "label": "Bitget (coming soon)",
      "title": "Bitget"
    },
    {
      "badge": "coming soon",
      "disabled": true,
      "key": "MEXC",
      "label": "MEXC (coming soon)",
      "title": "MEXC"
    },
    {
      "badge": "coming soon",
      "disabled": true,
      "key": "KuCoin",
      "label": "KuCoin (coming soon)",
      "title": "KuCoin"
    }
  ],
  "indicatorCatalog": [
    {
      "defaultEnabled": false,
      "displayName": "Moving Average (MA)",
      "key": "ma",
      "name": "Moving Average (MA)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Donchian Channels (DC)",
      "key": "donchian",
      "name": "Donchian Channels (DC)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Parabolic SAR (PSAR)",
      "key": "psar",
      "name": "Parabolic SAR (PSAR)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Bollinger Bands (BB)",
      "key": "bb",
      "name": "Bollinger Bands (BB)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Bollinger Band Width (BBW)",
      "key": "bbw",
      "name": "Bollinger Band Width (BBW)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Keltner Channels (KC)",
      "key": "keltner",
      "name": "Keltner Channels (KC)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Ichimoku Cloud (IC)",
      "key": "ichimoku",
      "name": "Ichimoku Cloud (IC)"
    },
    {
      "defaultEnabled": true,
      "displayName": "Relative Strength Index (RSI)",
      "key": "rsi",
      "name": "Relative Strength Index (RSI)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Volume",
      "key": "volume",
      "name": "Volume"
    },
    {
      "defaultEnabled": false,
      "displayName": "On-Balance Volume (OBV)",
      "key": "obv",
      "name": "On-Balance Volume (OBV)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Relative Volume (RVOL)",
      "key": "rvol",
      "name": "Relative Volume (RVOL)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Chaikin Money Flow (CMF)",
      "key": "cmf",
      "name": "Chaikin Money Flow (CMF)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Commodity Channel Index (CCI)",
      "key": "cci",
      "name": "Commodity Channel Index (CCI)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Rate of Change (ROC)",
      "key": "roc",
      "name": "Rate of Change (ROC)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Triple Exponential Average (TRIX)",
      "key": "trix",
      "name": "Triple Exponential Average (TRIX)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Percentage Price Oscillator (PPO)",
      "key": "ppo",
      "name": "Percentage Price Oscillator (PPO)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Awesome Oscillator (AO)",
      "key": "ao",
      "name": "Awesome Oscillator (AO)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Know Sure Thing (KST)",
      "key": "kst",
      "name": "Know Sure Thing (KST)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Aroon Oscillator (AROON)",
      "key": "aroon",
      "name": "Aroon Oscillator (AROON)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Choppiness Index (CHOP)",
      "key": "chop",
      "name": "Choppiness Index (CHOP)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Average True Range (ATR)",
      "key": "atr",
      "name": "Average True Range (ATR)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Normalized Average True Range (NATR)",
      "key": "natr",
      "name": "Normalized Average True Range (NATR)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Volume Weighted Average Price (VWAP)",
      "key": "vwap",
      "name": "Volume Weighted Average Price (VWAP)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Money Flow Index (MFI)",
      "key": "mfi",
      "name": "Money Flow Index (MFI)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Stochastic RSI (SRSI)",
      "key": "stoch_rsi",
      "name": "Stochastic RSI (SRSI)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Williams %R",
      "key": "willr",
      "name": "Williams %R"
    },
    {
      "defaultEnabled": false,
      "displayName": "Moving Average Convergence/Divergence (MACD)",
      "key": "macd",
      "name": "Moving Average Convergence/Divergence (MACD)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Ultimate Oscillator (UO)",
      "key": "uo",
      "name": "Ultimate Oscillator (UO)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Average Directional Index (ADX)",
      "key": "adx",
      "name": "Average Directional Index (ADX)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Directional Movement Index (DMI)",
      "key": "dmi",
      "name": "Directional Movement Index (DMI)"
    },
    {
      "defaultEnabled": false,
      "displayName": "SuperTrend (ST)",
      "key": "supertrend",
      "name": "SuperTrend (ST)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Exponential Moving Average (EMA)",
      "key": "ema",
      "name": "Exponential Moving Average (EMA)"
    },
    {
      "defaultEnabled": false,
      "displayName": "Stochastic Oscillator",
      "key": "stochastic",
      "name": "Stochastic Oscillator"
    }
  ],
  "indicatorKeys": [
    "ma",
    "donchian",
    "psar",
    "bb",
    "bbw",
    "keltner",
    "ichimoku",
    "rsi",
    "volume",
    "obv",
    "rvol",
    "cmf",
    "cci",
    "roc",
    "trix",
    "ppo",
    "ao",
    "kst",
    "aroon",
    "chop",
    "atr",
    "natr",
    "vwap",
    "mfi",
    "stoch_rsi",
    "willr",
    "macd",
    "uo",
    "adx",
    "dmi",
    "supertrend",
    "ema",
    "stochastic"
  ],
  "indicatorSourceOptions": [
    {
      "key": "Binance spot",
      "label": "Binance spot",
      "value": "Binance spot"
    },
    {
      "key": "Binance futures",
      "label": "Binance futures",
      "value": "Binance futures"
    },
    {
      "key": "TradingView",
      "label": "TradingView",
      "value": "TradingView"
    },
    {
      "key": "Bybit",
      "label": "Bybit",
      "value": "Bybit"
    },
    {
      "key": "Coinbase",
      "label": "Coinbase",
      "value": "Coinbase"
    },
    {
      "key": "OKX",
      "label": "OKX",
      "value": "OKX"
    },
    {
      "key": "Gate",
      "label": "Gate",
      "value": "Gate"
    },
    {
      "key": "Bitget",
      "label": "Bitget",
      "value": "Bitget"
    },
    {
      "key": "Mexc",
      "label": "Mexc",
      "value": "Mexc"
    },
    {
      "key": "Kucoin",
      "label": "Kucoin",
      "value": "Kucoin"
    },
    {
      "key": "HTX",
      "label": "HTX",
      "value": "HTX"
    },
    {
      "key": "Kraken",
      "label": "Kraken",
      "value": "Kraken"
    }
  ],
  "leadTraderOptions": [
    {
      "key": "futures_public",
      "label": "Futures Public Lead Trader",
      "value": "futures_public"
    },
    {
      "key": "futures_private",
      "label": "Futures Private Lead Trader",
      "value": "futures_private"
    },
    {
      "key": "spot_public",
      "label": "Spot Public Lead Trader",
      "value": "spot_public"
    },
    {
      "key": "spot_private",
      "label": "Spot Private Lead Trader",
      "value": "spot_private"
    }
  ],
  "llmProviderKeys": [
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "mistral",
    "grok",
    "qwen",
    "local",
    "ollama",
    "vllm",
    "llamacpp",
    "lmstudio",
    "tgi",
    "open-source"
  ],
  "llmProviders": [
    {
      "api_key_env": "OPENAI_API_KEY",
      "default_base_url": "https://api.openai.com/v1",
      "default_model": "gpt-5.5",
      "default_reasoning_effort": "default",
      "key": "openai",
      "label": "OpenAI / ChatGPT",
      "mode": "cloud",
      "model_suggestions": [
        "gpt-5.5",
        "gpt-5.5-2026-04-23",
        "gpt-5.5-pro",
        "gpt-5.5-pro-2026-04-23",
        "gpt-5.4",
        "gpt-5.4-2026-03-05",
        "gpt-5.4-pro",
        "gpt-5.4-pro-2026-03-05",
        "gpt-5.4-mini",
        "gpt-5.4-mini-2026-03-17",
        "gpt-5.4-nano",
        "gpt-5.4-nano-2026-03-17",
        "gpt-5.3-chat-latest",
        "gpt-5.3-codex",
        "gpt-5.2",
        "gpt-5.2-codex",
        "gpt-5.2-chat-latest",
        "gpt-5.2-pro",
        "gpt-5.1",
        "gpt-5-codex",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "ANTHROPIC_API_KEY",
      "default_base_url": "https://api.anthropic.com",
      "default_model": "claude-sonnet-4-5-20250929",
      "default_reasoning_effort": "default",
      "key": "anthropic",
      "label": "Anthropic Claude",
      "mode": "cloud",
      "model_suggestions": [
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-5-20251101",
        "claude-opus-4-1-20250805",
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-5",
        "claude-opus-4-1",
        "claude-opus-4-0",
        "claude-sonnet-4-0"
      ],
      "protocol": "anthropic-messages",
      "reasoning_efforts": [
        "default",
        "disabled",
        "enabled",
        "low",
        "medium",
        "high"
      ]
    },
    {
      "api_key_env": "GEMINI_API_KEY",
      "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
      "default_model": "gemini-3-flash-preview",
      "default_reasoning_effort": "default",
      "key": "gemini",
      "label": "Google Gemini",
      "mode": "cloud",
      "model_suggestions": [
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-customtools",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-preview-09-2025",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-lite-preview-09-2025"
      ],
      "protocol": "gemini-generate-content",
      "reasoning_efforts": [
        "default",
        "minimal",
        "low",
        "medium",
        "high"
      ]
    },
    {
      "api_key_env": "DEEPSEEK_API_KEY",
      "default_base_url": "https://api.deepseek.com",
      "default_model": "deepseek-v4-flash",
      "default_reasoning_effort": "default",
      "key": "deepseek",
      "label": "DeepSeek",
      "mode": "cloud",
      "model_suggestions": [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-chat",
        "deepseek-reasoner"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "disabled",
        "enabled",
        "high",
        "max"
      ]
    },
    {
      "api_key_env": "MISTRAL_API_KEY",
      "default_base_url": "https://api.mistral.ai/v1",
      "default_model": "mistral-small-latest",
      "default_reasoning_effort": "default",
      "key": "mistral",
      "label": "Mistral AI",
      "mode": "cloud",
      "model_suggestions": [
        "mistral-large-latest",
        "mistral-medium-latest",
        "mistral-small-latest",
        "codestral-latest",
        "open-mistral-nemo"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "low",
        "medium",
        "high"
      ]
    },
    {
      "api_key_env": "XAI_API_KEY",
      "default_base_url": "https://api.x.ai/v1",
      "default_model": "grok-4.3",
      "default_reasoning_effort": "default",
      "key": "grok",
      "label": "xAI Grok",
      "mode": "cloud",
      "model_suggestions": [
        "grok-4.3",
        "grok-4.3-latest",
        "grok-4.20",
        "grok-4.20-reasoning",
        "grok-4.20-non-reasoning",
        "grok-4-fast-reasoning",
        "grok-4-fast-non-reasoning"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "low",
        "medium",
        "high"
      ]
    },
    {
      "api_key_env": "DASHSCOPE_API_KEY",
      "default_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
      "default_model": "qwen3.6-plus",
      "default_reasoning_effort": "default",
      "key": "qwen",
      "label": "Alibaba Qwen / DashScope",
      "mode": "cloud",
      "model_suggestions": [
        "qwen3.6-max-preview",
        "qwen3.6-plus",
        "qwen3.6-plus-2026-04-02",
        "qwen3.6-flash",
        "qwen3.6-flash-2026-04-16",
        "qwen3-max",
        "qwen3-max-2026-01-23",
        "qwen3-max-2025-09-23",
        "qwen3-max-preview",
        "qwen3.5-plus",
        "qwen3.5-plus-2026-02-15",
        "qwen3.5-flash",
        "qwen3.5-flash-2026-02-23",
        "qwen3-coder-plus",
        "qwen3-coder-flash",
        "qwen-plus-us",
        "qwen-flash-us"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "low",
        "medium",
        "high"
      ]
    },
    {
      "api_key_env": "LOCAL_LLM_API_KEY",
      "default_base_url": "http://127.0.0.1:11434/v1",
      "default_model": "qwen3:8b",
      "default_reasoning_effort": "default",
      "key": "local",
      "label": "Local / Custom OpenAI-Compatible",
      "mode": "local",
      "model_suggestions": [
        "qwen3:0.6b",
        "qwen3:1.7b",
        "qwen3:4b",
        "qwen3:8b",
        "qwen3:14b",
        "qwen3:30b-a3b",
        "qwen3:32b",
        "qwen3",
        "qwen3-vl:8b",
        "qwen3-vl:32b",
        "qwen3.5",
        "qwen2.5:0.5b",
        "qwen2.5:1.5b",
        "qwen2.5:3b",
        "qwen2.5:7b",
        "qwen2.5:14b",
        "qwen2.5:32b",
        "qwen2.5:72b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:7b",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:32b",
        "qwq:32b",
        "gpt-oss:20b",
        "gpt-oss:120b",
        "gpt-oss:latest",
        "llama4:maverick",
        "llama4:scout",
        "deepseek-v3",
        "deepseek-v3.1",
        "deepseek-v3.2",
        "deepseek-r1:1.5b",
        "deepseek-r1:7b",
        "deepseek-r1:8b",
        "deepseek-r1:14b",
        "deepseek-r1:32b",
        "deepseek-r1:70b",
        "deepseek-coder-v2",
        "llama3.3",
        "llama3.1:8b",
        "llama3.1:70b",
        "llama3.2:1b",
        "llama3.2:3b",
        "llama3.2-vision:11b",
        "llama3.2-vision:90b",
        "mistral",
        "mistral-nemo",
        "mistral-small3.2",
        "mixtral:8x7b",
        "mixtral:8x22b",
        "codestral",
        "devstral",
        "gemma3:1b",
        "gemma3:4b",
        "gemma3:12b",
        "gemma3:27b",
        "gemma4:27b",
        "gemma2:2b",
        "gemma2:9b",
        "gemma2:27b",
        "phi4",
        "phi4-mini",
        "phi3.5",
        "phi3:mini",
        "falcon3:1b",
        "falcon3:3b",
        "falcon3:7b",
        "falcon3:10b",
        "yi:6b",
        "yi:9b",
        "yi:34b",
        "glm4",
        "glm4.5",
        "glm5",
        "kimi-k2",
        "minimax-m2",
        "step3",
        "mimo-v2",
        "internlm2.5",
        "baichuan2:7b",
        "baichuan2:13b",
        "minicpm-v",
        "smollm2:135m",
        "smollm2:360m",
        "smollm2:1.7b",
        "granite3.3:2b",
        "granite3.3:8b",
        "command-r",
        "command-r-plus",
        "starcoder2:3b",
        "starcoder2:7b",
        "starcoder2:15b",
        "codellama:7b",
        "codellama:13b",
        "codellama:34b",
        "dolphin-mixtral",
        "openchat",
        "neural-chat",
        "orca-mini",
        "zephyr",
        "solar",
        "nous-hermes2",
        "wizardlm2",
        "vicuna",
        "rwkv",
        "pythia",
        "dolly-v2",
        "stablelm",
        "redpajama",
        "openllama",
        "mpt",
        "dbrx",
        "arctic",
        "bloom",
        "bloomz",
        "mamba",
        "custom-model",
        "Qwen/Qwen3-0.6B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-Coder-14B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/QwQ-32B",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "google-t5/t5-small",
        "google-t5/t5-base",
        "google-t5/t5-large",
        "google/flan-t5-small",
        "google/flan-t5-base",
        "google/flan-t5-large",
        "google/flan-t5-xl",
        "google/flan-t5-xxl",
        "RWKV/rwkv-4-world",
        "RWKV/rwkv-5-world",
        "RWKV/rwkv-6-world",
        "BlinkDL/rwkv-7-world",
        "EleutherAI/gpt-neox-20b",
        "EleutherAI/gpt-j-6b",
        "EleutherAI/gpt-neo-2.7B",
        "yandex/yalm-100b",
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.2-1B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mistral-Nemo-Instruct-2407",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mistralai/Codestral-22B-v0.1",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        "deepseek-ai/DeepSeek-Coder-V2-Instruct",
        "google/gemma-3-1b-it",
        "google/gemma-3-4b-it",
        "google/gemma-3-12b-it",
        "google/gemma-3-27b-it",
        "google/gemma-2-2b-it",
        "google/gemma-2-9b-it",
        "google/gemma-2-27b-it",
        "microsoft/phi-4",
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
        "tiiuae/Falcon3-1B-Instruct",
        "tiiuae/Falcon3-3B-Instruct",
        "tiiuae/Falcon3-7B-Instruct",
        "tiiuae/Falcon3-10B-Instruct",
        "tiiuae/falcon-180B-chat",
        "01-ai/Yi-6B-Chat",
        "01-ai/Yi-9B-Chat",
        "01-ai/Yi-34B-Chat",
        "THUDM/glm-4-9b-chat",
        "internlm/internlm2_5-7b-chat",
        "internlm/internlm2_5-20b-chat",
        "baichuan-inc/Baichuan2-7B-Chat",
        "baichuan-inc/Baichuan2-13B-Chat",
        "openbmb/MiniCPM3-4B",
        "HuggingFaceTB/SmolLM2-135M-Instruct",
        "HuggingFaceTB/SmolLM2-360M-Instruct",
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "ibm-granite/granite-3.3-2b-instruct",
        "ibm-granite/granite-3.3-8b-instruct",
        "CohereForAI/c4ai-command-r-v01",
        "CohereForAI/c4ai-command-r-plus",
        "CohereForAI/aya-23-8B",
        "CohereForAI/aya-23-35B",
        "bigscience/bloomz-7b1",
        "bigscience/bloom",
        "mosaicml/mpt-7b-instruct",
        "mosaicml/mpt-30b-instruct",
        "databricks/dbrx-instruct",
        "ai21labs/Jamba-v0.1",
        "Nexusflow/Starling-LM-7B-beta",
        "HuggingFaceH4/zephyr-7b-beta",
        "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
        "openchat/openchat-3.5-0106",
        "WizardLMTeam/WizardLM-2-8x22B",
        "lmsys/vicuna-13b-v1.5",
        "codellama/CodeLlama-7b-Instruct-hf",
        "codellama/CodeLlama-13b-Instruct-hf",
        "codellama/CodeLlama-34b-Instruct-hf",
        "bigcode/starcoder2-3b",
        "bigcode/starcoder2-7b",
        "bigcode/starcoder2-15b",
        "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "google/flan-ul2",
        "allenai/OLMo-7B-Instruct",
        "allenai/OLMo-2-1124-7B-Instruct",
        "allenai/OLMo-2-1124-13B-Instruct",
        "cerebras/Cerebras-GPT-111M",
        "cerebras/Cerebras-GPT-256M",
        "cerebras/Cerebras-GPT-590M",
        "cerebras/Cerebras-GPT-1.3B",
        "cerebras/Cerebras-GPT-2.7B",
        "cerebras/Cerebras-GPT-6.7B",
        "cerebras/Cerebras-GPT-13B",
        "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
        "EleutherAI/pythia-70m",
        "EleutherAI/pythia-160m",
        "EleutherAI/pythia-410m",
        "EleutherAI/pythia-1b",
        "EleutherAI/pythia-1.4b",
        "EleutherAI/pythia-2.8b",
        "EleutherAI/pythia-6.9b",
        "EleutherAI/pythia-12b",
        "databricks/dolly-v2-3b",
        "databricks/dolly-v2-7b",
        "databricks/dolly-v2-12b",
        "stabilityai/stablelm-base-alpha-3b",
        "stabilityai/stablelm-base-alpha-7b",
        "stabilityai/stablelm-tuned-alpha-3b",
        "stabilityai/stablelm-tuned-alpha-7b",
        "lmsys/fastchat-t5-3b-v1.0",
        "aisquared/dlite-v2-1_5b",
        "h2oai/h2ogpt-oasst1-512-12b",
        "togethercomputer/RedPajama-INCITE-7B-Instruct",
        "openlm-research/open_llama_3b",
        "openlm-research/open_llama_7b",
        "openlm-research/open_llama_13b",
        "mosaicml/mpt-7b-chat",
        "mosaicml/mpt-7b-storywriter",
        "mosaicml/mpt-30b-chat",
        "nomic-ai/gpt4all-j",
        "Salesforce/xgen-7b-8k-inst",
        "inceptionai/jais-13b-chat",
        "codellama/CodeLlama-70b-Instruct-hf",
        "teknium/OpenHermes-2.5-Mistral-7B",
        "apple/OpenELM-270M-Instruct",
        "apple/OpenELM-450M-Instruct",
        "apple/OpenELM-1_1B-Instruct",
        "apple/OpenELM-3B-Instruct",
        "Deci/DeciLM-7B-instruct",
        "THUDM/chatglm-6b",
        "THUDM/chatglm2-6b",
        "THUDM/chatglm3-6b",
        "Skywork/Skywork-13B-base",
        "LLM360/Amber",
        "Cerebras/FLOR-6.3B",
        "Qwen/Qwen1.5-0.5B-Chat",
        "Qwen/Qwen1.5-1.8B-Chat",
        "Qwen/Qwen1.5-4B-Chat",
        "Qwen/Qwen1.5-7B-Chat",
        "Qwen/Qwen1.5-14B-Chat",
        "Qwen/Qwen1.5-32B-Chat",
        "Qwen/Qwen1.5-72B-Chat",
        "Qwen/Qwen1.5-110B-Chat",
        "Qwen/Qwen1.5-MoE-A2.7B-Chat",
        "LargeWorldModel/LWM-Text-1M",
        "YerevaNN/YerevaNN-Grok-1",
        "state-spaces/mamba-130m",
        "state-spaces/mamba-370m",
        "state-spaces/mamba-790m",
        "state-spaces/mamba-1.4b",
        "state-spaces/mamba-2.8b",
        "Snowflake/snowflake-arctic-instruct",
        "Fugaku-LLM/Fugaku-LLM-13B-instruct",
        "tiiuae/Falcon2-11B",
        "01-ai/Yi-1.5-6B-Chat",
        "01-ai/Yi-1.5-9B-Chat",
        "01-ai/Yi-1.5-34B-Chat",
        "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "deepseek-ai/DeepSeek-V2-Chat",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1-0528",
        "microsoft/Phi-3-medium-128k-instruct",
        "microsoft/Phi-3-mini-128k-instruct",
        "microsoft/phi-4-reasoning",
        "yulan-team/YuLan-Mini",
        "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
        "bigcode/santacoder",
        "Salesforce/codegen2-1B",
        "Salesforce/codegen2-3_7B",
        "Salesforce/codegen2-7B",
        "HuggingFaceH4/starchat-alpha",
        "replit/replit-code-v1-3b",
        "Salesforce/codet5p-770m",
        "Salesforce/codet5p-2b",
        "Salesforce/codet5p-6b",
        "Salesforce/codegen25-7b-multi",
        "Deci/DeciCoder-1b",
        "meta-llama/Llama-2-7b-chat-hf",
        "meta-llama/Llama-2-13b-chat-hf",
        "meta-llama/Llama-2-70b-chat-hf",
        "meta-llama/Llama-3-8B-Instruct",
        "meta-llama/Llama-3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Large-Instruct-2411",
        "Qwen/Qwen2-72B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3.5",
        "Qwen/Qwen3.5-30B-A3B",
        "Qwen/Qwen3.5-Coder",
        "zai-org/GLM-4.5",
        "zai-org/GLM-4.5-Air",
        "zai-org/GLM-4.6",
        "zai-org/GLM-5",
        "moonshotai/Kimi-K2",
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.5",
        "MiniMaxAI/MiniMax-M2.5",
        "stepfun-ai/Step3",
        "stepfun-ai/Step-3.5-Flash",
        "XiaomiMiMo/MiMo-V2-Flash",
        "google/gemma-4-4b-it",
        "google/gemma-4-12b-it",
        "google/gemma-4-27b-it",
        "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
        "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
        "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "OLLAMA_API_KEY",
      "default_base_url": "http://127.0.0.1:11434/v1",
      "default_model": "qwen3:8b",
      "default_reasoning_effort": "default",
      "key": "ollama",
      "label": "Ollama",
      "mode": "local",
      "model_suggestions": [
        "qwen3:0.6b",
        "qwen3:1.7b",
        "qwen3:4b",
        "qwen3:8b",
        "qwen3:14b",
        "qwen3:30b-a3b",
        "qwen3:32b",
        "qwen3",
        "qwen3-vl:8b",
        "qwen3-vl:32b",
        "qwen3.5",
        "qwen2.5:0.5b",
        "qwen2.5:1.5b",
        "qwen2.5:3b",
        "qwen2.5:7b",
        "qwen2.5:14b",
        "qwen2.5:32b",
        "qwen2.5:72b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:7b",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:32b",
        "qwq:32b",
        "gpt-oss:20b",
        "gpt-oss:120b",
        "gpt-oss:latest",
        "llama4:maverick",
        "llama4:scout",
        "deepseek-v3",
        "deepseek-v3.1",
        "deepseek-v3.2",
        "deepseek-r1:1.5b",
        "deepseek-r1:7b",
        "deepseek-r1:8b",
        "deepseek-r1:14b",
        "deepseek-r1:32b",
        "deepseek-r1:70b",
        "deepseek-coder-v2",
        "llama3.3",
        "llama3.1:8b",
        "llama3.1:70b",
        "llama3.2:1b",
        "llama3.2:3b",
        "llama3.2-vision:11b",
        "llama3.2-vision:90b",
        "mistral",
        "mistral-nemo",
        "mistral-small3.2",
        "mixtral:8x7b",
        "mixtral:8x22b",
        "codestral",
        "devstral",
        "gemma3:1b",
        "gemma3:4b",
        "gemma3:12b",
        "gemma3:27b",
        "gemma4:27b",
        "gemma2:2b",
        "gemma2:9b",
        "gemma2:27b",
        "phi4",
        "phi4-mini",
        "phi3.5",
        "phi3:mini",
        "falcon3:1b",
        "falcon3:3b",
        "falcon3:7b",
        "falcon3:10b",
        "yi:6b",
        "yi:9b",
        "yi:34b",
        "glm4",
        "glm4.5",
        "glm5",
        "kimi-k2",
        "minimax-m2",
        "step3",
        "mimo-v2",
        "internlm2.5",
        "baichuan2:7b",
        "baichuan2:13b",
        "minicpm-v",
        "smollm2:135m",
        "smollm2:360m",
        "smollm2:1.7b",
        "granite3.3:2b",
        "granite3.3:8b",
        "command-r",
        "command-r-plus",
        "starcoder2:3b",
        "starcoder2:7b",
        "starcoder2:15b",
        "codellama:7b",
        "codellama:13b",
        "codellama:34b",
        "dolphin-mixtral",
        "openchat",
        "neural-chat",
        "orca-mini",
        "zephyr",
        "solar",
        "nous-hermes2",
        "wizardlm2",
        "vicuna",
        "rwkv",
        "pythia",
        "dolly-v2",
        "stablelm",
        "redpajama",
        "openllama",
        "mpt",
        "dbrx",
        "arctic",
        "bloom",
        "bloomz",
        "mamba",
        "custom-model"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "VLLM_API_KEY",
      "default_base_url": "http://127.0.0.1:8000/v1",
      "default_model": "Qwen/Qwen3-8B",
      "default_reasoning_effort": "default",
      "key": "vllm",
      "label": "vLLM / SGLang",
      "mode": "local",
      "model_suggestions": [
        "Qwen/Qwen3-0.6B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-Coder-14B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/QwQ-32B",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "google-t5/t5-small",
        "google-t5/t5-base",
        "google-t5/t5-large",
        "google/flan-t5-small",
        "google/flan-t5-base",
        "google/flan-t5-large",
        "google/flan-t5-xl",
        "google/flan-t5-xxl",
        "RWKV/rwkv-4-world",
        "RWKV/rwkv-5-world",
        "RWKV/rwkv-6-world",
        "BlinkDL/rwkv-7-world",
        "EleutherAI/gpt-neox-20b",
        "EleutherAI/gpt-j-6b",
        "EleutherAI/gpt-neo-2.7B",
        "yandex/yalm-100b",
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.2-1B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mistral-Nemo-Instruct-2407",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mistralai/Codestral-22B-v0.1",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        "deepseek-ai/DeepSeek-Coder-V2-Instruct",
        "google/gemma-3-1b-it",
        "google/gemma-3-4b-it",
        "google/gemma-3-12b-it",
        "google/gemma-3-27b-it",
        "google/gemma-2-2b-it",
        "google/gemma-2-9b-it",
        "google/gemma-2-27b-it",
        "microsoft/phi-4",
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
        "tiiuae/Falcon3-1B-Instruct",
        "tiiuae/Falcon3-3B-Instruct",
        "tiiuae/Falcon3-7B-Instruct",
        "tiiuae/Falcon3-10B-Instruct",
        "tiiuae/falcon-180B-chat",
        "01-ai/Yi-6B-Chat",
        "01-ai/Yi-9B-Chat",
        "01-ai/Yi-34B-Chat",
        "THUDM/glm-4-9b-chat",
        "internlm/internlm2_5-7b-chat",
        "internlm/internlm2_5-20b-chat",
        "baichuan-inc/Baichuan2-7B-Chat",
        "baichuan-inc/Baichuan2-13B-Chat",
        "openbmb/MiniCPM3-4B",
        "HuggingFaceTB/SmolLM2-135M-Instruct",
        "HuggingFaceTB/SmolLM2-360M-Instruct",
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "ibm-granite/granite-3.3-2b-instruct",
        "ibm-granite/granite-3.3-8b-instruct",
        "CohereForAI/c4ai-command-r-v01",
        "CohereForAI/c4ai-command-r-plus",
        "CohereForAI/aya-23-8B",
        "CohereForAI/aya-23-35B",
        "bigscience/bloomz-7b1",
        "bigscience/bloom",
        "mosaicml/mpt-7b-instruct",
        "mosaicml/mpt-30b-instruct",
        "databricks/dbrx-instruct",
        "ai21labs/Jamba-v0.1",
        "Nexusflow/Starling-LM-7B-beta",
        "HuggingFaceH4/zephyr-7b-beta",
        "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
        "openchat/openchat-3.5-0106",
        "WizardLMTeam/WizardLM-2-8x22B",
        "lmsys/vicuna-13b-v1.5",
        "codellama/CodeLlama-7b-Instruct-hf",
        "codellama/CodeLlama-13b-Instruct-hf",
        "codellama/CodeLlama-34b-Instruct-hf",
        "bigcode/starcoder2-3b",
        "bigcode/starcoder2-7b",
        "bigcode/starcoder2-15b",
        "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "google/flan-ul2",
        "allenai/OLMo-7B-Instruct",
        "allenai/OLMo-2-1124-7B-Instruct",
        "allenai/OLMo-2-1124-13B-Instruct",
        "cerebras/Cerebras-GPT-111M",
        "cerebras/Cerebras-GPT-256M",
        "cerebras/Cerebras-GPT-590M",
        "cerebras/Cerebras-GPT-1.3B",
        "cerebras/Cerebras-GPT-2.7B",
        "cerebras/Cerebras-GPT-6.7B",
        "cerebras/Cerebras-GPT-13B",
        "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
        "EleutherAI/pythia-70m",
        "EleutherAI/pythia-160m",
        "EleutherAI/pythia-410m",
        "EleutherAI/pythia-1b",
        "EleutherAI/pythia-1.4b",
        "EleutherAI/pythia-2.8b",
        "EleutherAI/pythia-6.9b",
        "EleutherAI/pythia-12b",
        "databricks/dolly-v2-3b",
        "databricks/dolly-v2-7b",
        "databricks/dolly-v2-12b",
        "stabilityai/stablelm-base-alpha-3b",
        "stabilityai/stablelm-base-alpha-7b",
        "stabilityai/stablelm-tuned-alpha-3b",
        "stabilityai/stablelm-tuned-alpha-7b",
        "lmsys/fastchat-t5-3b-v1.0",
        "aisquared/dlite-v2-1_5b",
        "h2oai/h2ogpt-oasst1-512-12b",
        "togethercomputer/RedPajama-INCITE-7B-Instruct",
        "openlm-research/open_llama_3b",
        "openlm-research/open_llama_7b",
        "openlm-research/open_llama_13b",
        "mosaicml/mpt-7b-chat",
        "mosaicml/mpt-7b-storywriter",
        "mosaicml/mpt-30b-chat",
        "nomic-ai/gpt4all-j",
        "Salesforce/xgen-7b-8k-inst",
        "inceptionai/jais-13b-chat",
        "codellama/CodeLlama-70b-Instruct-hf",
        "teknium/OpenHermes-2.5-Mistral-7B",
        "apple/OpenELM-270M-Instruct",
        "apple/OpenELM-450M-Instruct",
        "apple/OpenELM-1_1B-Instruct",
        "apple/OpenELM-3B-Instruct",
        "Deci/DeciLM-7B-instruct",
        "THUDM/chatglm-6b",
        "THUDM/chatglm2-6b",
        "THUDM/chatglm3-6b",
        "Skywork/Skywork-13B-base",
        "LLM360/Amber",
        "Cerebras/FLOR-6.3B",
        "Qwen/Qwen1.5-0.5B-Chat",
        "Qwen/Qwen1.5-1.8B-Chat",
        "Qwen/Qwen1.5-4B-Chat",
        "Qwen/Qwen1.5-7B-Chat",
        "Qwen/Qwen1.5-14B-Chat",
        "Qwen/Qwen1.5-32B-Chat",
        "Qwen/Qwen1.5-72B-Chat",
        "Qwen/Qwen1.5-110B-Chat",
        "Qwen/Qwen1.5-MoE-A2.7B-Chat",
        "LargeWorldModel/LWM-Text-1M",
        "YerevaNN/YerevaNN-Grok-1",
        "state-spaces/mamba-130m",
        "state-spaces/mamba-370m",
        "state-spaces/mamba-790m",
        "state-spaces/mamba-1.4b",
        "state-spaces/mamba-2.8b",
        "Snowflake/snowflake-arctic-instruct",
        "Fugaku-LLM/Fugaku-LLM-13B-instruct",
        "tiiuae/Falcon2-11B",
        "01-ai/Yi-1.5-6B-Chat",
        "01-ai/Yi-1.5-9B-Chat",
        "01-ai/Yi-1.5-34B-Chat",
        "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "deepseek-ai/DeepSeek-V2-Chat",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1-0528",
        "microsoft/Phi-3-medium-128k-instruct",
        "microsoft/Phi-3-mini-128k-instruct",
        "microsoft/phi-4-reasoning",
        "yulan-team/YuLan-Mini",
        "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
        "bigcode/santacoder",
        "Salesforce/codegen2-1B",
        "Salesforce/codegen2-3_7B",
        "Salesforce/codegen2-7B",
        "HuggingFaceH4/starchat-alpha",
        "replit/replit-code-v1-3b",
        "Salesforce/codet5p-770m",
        "Salesforce/codet5p-2b",
        "Salesforce/codet5p-6b",
        "Salesforce/codegen25-7b-multi",
        "Deci/DeciCoder-1b",
        "meta-llama/Llama-2-7b-chat-hf",
        "meta-llama/Llama-2-13b-chat-hf",
        "meta-llama/Llama-2-70b-chat-hf",
        "meta-llama/Llama-3-8B-Instruct",
        "meta-llama/Llama-3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Large-Instruct-2411",
        "Qwen/Qwen2-72B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3.5",
        "Qwen/Qwen3.5-30B-A3B",
        "Qwen/Qwen3.5-Coder",
        "zai-org/GLM-4.5",
        "zai-org/GLM-4.5-Air",
        "zai-org/GLM-4.6",
        "zai-org/GLM-5",
        "moonshotai/Kimi-K2",
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.5",
        "MiniMaxAI/MiniMax-M2.5",
        "stepfun-ai/Step3",
        "stepfun-ai/Step-3.5-Flash",
        "XiaomiMiMo/MiMo-V2-Flash",
        "google/gemma-4-4b-it",
        "google/gemma-4-12b-it",
        "google/gemma-4-27b-it",
        "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
        "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
        "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "LLAMACPP_API_KEY",
      "default_base_url": "http://127.0.0.1:8080/v1",
      "default_model": "local-model",
      "default_reasoning_effort": "default",
      "key": "llamacpp",
      "label": "llama.cpp server",
      "mode": "local",
      "model_suggestions": [
        "local-model",
        "qwen3-8b-q4_k_m.gguf",
        "llama-3.1-8b-instruct-q4_k_m.gguf",
        "mistral-7b-instruct-q4_k_m.gguf",
        "gemma-3-4b-it-q4_k_m.gguf",
        "qwen3:0.6b",
        "qwen3:1.7b",
        "qwen3:4b",
        "qwen3:8b",
        "qwen3:14b",
        "qwen3:30b-a3b",
        "qwen3:32b",
        "qwen3",
        "qwen3-vl:8b",
        "qwen3-vl:32b",
        "qwen3.5",
        "qwen2.5:0.5b",
        "qwen2.5:1.5b",
        "qwen2.5:3b",
        "qwen2.5:7b",
        "qwen2.5:14b",
        "qwen2.5:32b",
        "qwen2.5:72b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:7b",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:32b",
        "qwq:32b",
        "gpt-oss:20b",
        "gpt-oss:120b",
        "gpt-oss:latest",
        "llama4:maverick",
        "llama4:scout",
        "deepseek-v3",
        "deepseek-v3.1",
        "deepseek-v3.2",
        "deepseek-r1:1.5b",
        "deepseek-r1:7b",
        "deepseek-r1:8b",
        "deepseek-r1:14b",
        "deepseek-r1:32b",
        "deepseek-r1:70b",
        "deepseek-coder-v2",
        "llama3.3",
        "llama3.1:8b",
        "llama3.1:70b",
        "llama3.2:1b",
        "llama3.2:3b",
        "llama3.2-vision:11b",
        "llama3.2-vision:90b",
        "mistral",
        "mistral-nemo",
        "mistral-small3.2",
        "mixtral:8x7b",
        "mixtral:8x22b",
        "codestral",
        "devstral",
        "gemma3:1b",
        "gemma3:4b",
        "gemma3:12b",
        "gemma3:27b",
        "gemma4:27b",
        "gemma2:2b",
        "gemma2:9b",
        "gemma2:27b",
        "phi4",
        "phi4-mini",
        "phi3.5",
        "phi3:mini",
        "falcon3:1b",
        "falcon3:3b",
        "falcon3:7b",
        "falcon3:10b",
        "yi:6b",
        "yi:9b",
        "yi:34b",
        "glm4",
        "glm4.5",
        "glm5",
        "kimi-k2",
        "minimax-m2",
        "step3",
        "mimo-v2",
        "internlm2.5",
        "baichuan2:7b",
        "baichuan2:13b",
        "minicpm-v",
        "smollm2:135m",
        "smollm2:360m",
        "smollm2:1.7b",
        "granite3.3:2b",
        "granite3.3:8b",
        "command-r",
        "command-r-plus",
        "starcoder2:3b",
        "starcoder2:7b",
        "starcoder2:15b",
        "codellama:7b",
        "codellama:13b",
        "codellama:34b",
        "dolphin-mixtral",
        "openchat",
        "neural-chat",
        "orca-mini",
        "zephyr",
        "solar",
        "nous-hermes2",
        "wizardlm2",
        "vicuna",
        "rwkv",
        "pythia",
        "dolly-v2",
        "stablelm",
        "redpajama",
        "openllama",
        "mpt",
        "dbrx",
        "arctic",
        "bloom",
        "bloomz",
        "mamba",
        "custom-model",
        "google/flan-ul2",
        "allenai/OLMo-7B-Instruct",
        "allenai/OLMo-2-1124-7B-Instruct",
        "allenai/OLMo-2-1124-13B-Instruct",
        "cerebras/Cerebras-GPT-111M",
        "cerebras/Cerebras-GPT-256M",
        "cerebras/Cerebras-GPT-590M",
        "cerebras/Cerebras-GPT-1.3B",
        "cerebras/Cerebras-GPT-2.7B",
        "cerebras/Cerebras-GPT-6.7B",
        "cerebras/Cerebras-GPT-13B",
        "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
        "EleutherAI/pythia-70m",
        "EleutherAI/pythia-160m",
        "EleutherAI/pythia-410m",
        "EleutherAI/pythia-1b",
        "EleutherAI/pythia-1.4b",
        "EleutherAI/pythia-2.8b",
        "EleutherAI/pythia-6.9b",
        "EleutherAI/pythia-12b",
        "databricks/dolly-v2-3b",
        "databricks/dolly-v2-7b",
        "databricks/dolly-v2-12b",
        "stabilityai/stablelm-base-alpha-3b",
        "stabilityai/stablelm-base-alpha-7b",
        "stabilityai/stablelm-tuned-alpha-3b",
        "stabilityai/stablelm-tuned-alpha-7b",
        "lmsys/fastchat-t5-3b-v1.0",
        "aisquared/dlite-v2-1_5b",
        "h2oai/h2ogpt-oasst1-512-12b",
        "togethercomputer/RedPajama-INCITE-7B-Instruct",
        "openlm-research/open_llama_3b",
        "openlm-research/open_llama_7b",
        "openlm-research/open_llama_13b",
        "mosaicml/mpt-7b-chat",
        "mosaicml/mpt-7b-storywriter",
        "mosaicml/mpt-30b-chat",
        "nomic-ai/gpt4all-j",
        "Salesforce/xgen-7b-8k-inst",
        "inceptionai/jais-13b-chat",
        "codellama/CodeLlama-70b-Instruct-hf",
        "teknium/OpenHermes-2.5-Mistral-7B",
        "apple/OpenELM-270M-Instruct",
        "apple/OpenELM-450M-Instruct",
        "apple/OpenELM-1_1B-Instruct",
        "apple/OpenELM-3B-Instruct",
        "Deci/DeciLM-7B-instruct",
        "THUDM/chatglm-6b",
        "THUDM/chatglm2-6b",
        "THUDM/chatglm3-6b",
        "THUDM/glm-4-9b-chat",
        "Skywork/Skywork-13B-base",
        "LLM360/Amber",
        "Cerebras/FLOR-6.3B",
        "Qwen/Qwen1.5-0.5B-Chat",
        "Qwen/Qwen1.5-1.8B-Chat",
        "Qwen/Qwen1.5-4B-Chat",
        "Qwen/Qwen1.5-7B-Chat",
        "Qwen/Qwen1.5-14B-Chat",
        "Qwen/Qwen1.5-32B-Chat",
        "Qwen/Qwen1.5-72B-Chat",
        "Qwen/Qwen1.5-110B-Chat",
        "Qwen/Qwen1.5-MoE-A2.7B-Chat",
        "LargeWorldModel/LWM-Text-1M",
        "YerevaNN/YerevaNN-Grok-1",
        "state-spaces/mamba-130m",
        "state-spaces/mamba-370m",
        "state-spaces/mamba-790m",
        "state-spaces/mamba-1.4b",
        "state-spaces/mamba-2.8b",
        "Snowflake/snowflake-arctic-instruct",
        "Fugaku-LLM/Fugaku-LLM-13B-instruct",
        "tiiuae/Falcon2-11B",
        "01-ai/Yi-1.5-6B-Chat",
        "01-ai/Yi-1.5-9B-Chat",
        "01-ai/Yi-1.5-34B-Chat",
        "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "deepseek-ai/DeepSeek-V2-Chat",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1-0528",
        "microsoft/Phi-3-medium-128k-instruct",
        "microsoft/Phi-3-mini-128k-instruct",
        "microsoft/phi-4-reasoning",
        "yulan-team/YuLan-Mini",
        "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
        "bigcode/santacoder",
        "Salesforce/codegen2-1B",
        "Salesforce/codegen2-3_7B",
        "Salesforce/codegen2-7B",
        "HuggingFaceH4/starchat-alpha",
        "replit/replit-code-v1-3b",
        "Salesforce/codet5p-770m",
        "Salesforce/codet5p-2b",
        "Salesforce/codet5p-6b",
        "Salesforce/codegen25-7b-multi",
        "Deci/DeciCoder-1b",
        "meta-llama/Llama-2-7b-chat-hf",
        "meta-llama/Llama-2-13b-chat-hf",
        "meta-llama/Llama-2-70b-chat-hf",
        "meta-llama/Llama-3-8B-Instruct",
        "meta-llama/Llama-3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Large-Instruct-2411",
        "Qwen/Qwen2-72B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3.5",
        "Qwen/Qwen3.5-30B-A3B",
        "Qwen/Qwen3.5-Coder",
        "zai-org/GLM-4.5",
        "zai-org/GLM-4.5-Air",
        "zai-org/GLM-4.6",
        "zai-org/GLM-5",
        "moonshotai/Kimi-K2",
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.5",
        "MiniMaxAI/MiniMax-M2.5",
        "stepfun-ai/Step3",
        "stepfun-ai/Step-3.5-Flash",
        "XiaomiMiMo/MiMo-V2-Flash",
        "google/gemma-4-4b-it",
        "google/gemma-4-12b-it",
        "google/gemma-4-27b-it",
        "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
        "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
        "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "LMSTUDIO_API_KEY",
      "default_base_url": "http://127.0.0.1:1234/v1",
      "default_model": "local-model",
      "default_reasoning_effort": "default",
      "key": "lmstudio",
      "label": "LM Studio",
      "mode": "local",
      "model_suggestions": [
        "local-model",
        "Qwen/Qwen3-0.6B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-Coder-14B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/QwQ-32B",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "google-t5/t5-small",
        "google-t5/t5-base",
        "google-t5/t5-large",
        "google/flan-t5-small",
        "google/flan-t5-base",
        "google/flan-t5-large",
        "google/flan-t5-xl",
        "google/flan-t5-xxl",
        "RWKV/rwkv-4-world",
        "RWKV/rwkv-5-world",
        "RWKV/rwkv-6-world",
        "BlinkDL/rwkv-7-world",
        "EleutherAI/gpt-neox-20b",
        "EleutherAI/gpt-j-6b",
        "EleutherAI/gpt-neo-2.7B",
        "yandex/yalm-100b",
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.2-1B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mistral-Nemo-Instruct-2407",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mistralai/Codestral-22B-v0.1",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        "deepseek-ai/DeepSeek-Coder-V2-Instruct",
        "google/gemma-3-1b-it",
        "google/gemma-3-4b-it",
        "google/gemma-3-12b-it",
        "google/gemma-3-27b-it",
        "google/gemma-2-2b-it",
        "google/gemma-2-9b-it",
        "google/gemma-2-27b-it",
        "microsoft/phi-4",
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
        "tiiuae/Falcon3-1B-Instruct",
        "tiiuae/Falcon3-3B-Instruct",
        "tiiuae/Falcon3-7B-Instruct",
        "tiiuae/Falcon3-10B-Instruct",
        "tiiuae/falcon-180B-chat",
        "01-ai/Yi-6B-Chat",
        "01-ai/Yi-9B-Chat",
        "01-ai/Yi-34B-Chat",
        "THUDM/glm-4-9b-chat",
        "internlm/internlm2_5-7b-chat",
        "internlm/internlm2_5-20b-chat",
        "baichuan-inc/Baichuan2-7B-Chat",
        "baichuan-inc/Baichuan2-13B-Chat",
        "openbmb/MiniCPM3-4B",
        "HuggingFaceTB/SmolLM2-135M-Instruct",
        "HuggingFaceTB/SmolLM2-360M-Instruct",
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "ibm-granite/granite-3.3-2b-instruct",
        "ibm-granite/granite-3.3-8b-instruct",
        "CohereForAI/c4ai-command-r-v01",
        "CohereForAI/c4ai-command-r-plus",
        "CohereForAI/aya-23-8B",
        "CohereForAI/aya-23-35B",
        "bigscience/bloomz-7b1",
        "bigscience/bloom",
        "mosaicml/mpt-7b-instruct",
        "mosaicml/mpt-30b-instruct",
        "databricks/dbrx-instruct",
        "ai21labs/Jamba-v0.1",
        "Nexusflow/Starling-LM-7B-beta",
        "HuggingFaceH4/zephyr-7b-beta",
        "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
        "openchat/openchat-3.5-0106",
        "WizardLMTeam/WizardLM-2-8x22B",
        "lmsys/vicuna-13b-v1.5",
        "codellama/CodeLlama-7b-Instruct-hf",
        "codellama/CodeLlama-13b-Instruct-hf",
        "codellama/CodeLlama-34b-Instruct-hf",
        "bigcode/starcoder2-3b",
        "bigcode/starcoder2-7b",
        "bigcode/starcoder2-15b",
        "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "google/flan-ul2",
        "allenai/OLMo-7B-Instruct",
        "allenai/OLMo-2-1124-7B-Instruct",
        "allenai/OLMo-2-1124-13B-Instruct",
        "cerebras/Cerebras-GPT-111M",
        "cerebras/Cerebras-GPT-256M",
        "cerebras/Cerebras-GPT-590M",
        "cerebras/Cerebras-GPT-1.3B",
        "cerebras/Cerebras-GPT-2.7B",
        "cerebras/Cerebras-GPT-6.7B",
        "cerebras/Cerebras-GPT-13B",
        "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
        "EleutherAI/pythia-70m",
        "EleutherAI/pythia-160m",
        "EleutherAI/pythia-410m",
        "EleutherAI/pythia-1b",
        "EleutherAI/pythia-1.4b",
        "EleutherAI/pythia-2.8b",
        "EleutherAI/pythia-6.9b",
        "EleutherAI/pythia-12b",
        "databricks/dolly-v2-3b",
        "databricks/dolly-v2-7b",
        "databricks/dolly-v2-12b",
        "stabilityai/stablelm-base-alpha-3b",
        "stabilityai/stablelm-base-alpha-7b",
        "stabilityai/stablelm-tuned-alpha-3b",
        "stabilityai/stablelm-tuned-alpha-7b",
        "lmsys/fastchat-t5-3b-v1.0",
        "aisquared/dlite-v2-1_5b",
        "h2oai/h2ogpt-oasst1-512-12b",
        "togethercomputer/RedPajama-INCITE-7B-Instruct",
        "openlm-research/open_llama_3b",
        "openlm-research/open_llama_7b",
        "openlm-research/open_llama_13b",
        "mosaicml/mpt-7b-chat",
        "mosaicml/mpt-7b-storywriter",
        "mosaicml/mpt-30b-chat",
        "nomic-ai/gpt4all-j",
        "Salesforce/xgen-7b-8k-inst",
        "inceptionai/jais-13b-chat",
        "codellama/CodeLlama-70b-Instruct-hf",
        "teknium/OpenHermes-2.5-Mistral-7B",
        "apple/OpenELM-270M-Instruct",
        "apple/OpenELM-450M-Instruct",
        "apple/OpenELM-1_1B-Instruct",
        "apple/OpenELM-3B-Instruct",
        "Deci/DeciLM-7B-instruct",
        "THUDM/chatglm-6b",
        "THUDM/chatglm2-6b",
        "THUDM/chatglm3-6b",
        "Skywork/Skywork-13B-base",
        "LLM360/Amber",
        "Cerebras/FLOR-6.3B",
        "Qwen/Qwen1.5-0.5B-Chat",
        "Qwen/Qwen1.5-1.8B-Chat",
        "Qwen/Qwen1.5-4B-Chat",
        "Qwen/Qwen1.5-7B-Chat",
        "Qwen/Qwen1.5-14B-Chat",
        "Qwen/Qwen1.5-32B-Chat",
        "Qwen/Qwen1.5-72B-Chat",
        "Qwen/Qwen1.5-110B-Chat",
        "Qwen/Qwen1.5-MoE-A2.7B-Chat",
        "LargeWorldModel/LWM-Text-1M",
        "YerevaNN/YerevaNN-Grok-1",
        "state-spaces/mamba-130m",
        "state-spaces/mamba-370m",
        "state-spaces/mamba-790m",
        "state-spaces/mamba-1.4b",
        "state-spaces/mamba-2.8b",
        "Snowflake/snowflake-arctic-instruct",
        "Fugaku-LLM/Fugaku-LLM-13B-instruct",
        "tiiuae/Falcon2-11B",
        "01-ai/Yi-1.5-6B-Chat",
        "01-ai/Yi-1.5-9B-Chat",
        "01-ai/Yi-1.5-34B-Chat",
        "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "deepseek-ai/DeepSeek-V2-Chat",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1-0528",
        "microsoft/Phi-3-medium-128k-instruct",
        "microsoft/Phi-3-mini-128k-instruct",
        "microsoft/phi-4-reasoning",
        "yulan-team/YuLan-Mini",
        "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
        "bigcode/santacoder",
        "Salesforce/codegen2-1B",
        "Salesforce/codegen2-3_7B",
        "Salesforce/codegen2-7B",
        "HuggingFaceH4/starchat-alpha",
        "replit/replit-code-v1-3b",
        "Salesforce/codet5p-770m",
        "Salesforce/codet5p-2b",
        "Salesforce/codet5p-6b",
        "Salesforce/codegen25-7b-multi",
        "Deci/DeciCoder-1b",
        "meta-llama/Llama-2-7b-chat-hf",
        "meta-llama/Llama-2-13b-chat-hf",
        "meta-llama/Llama-2-70b-chat-hf",
        "meta-llama/Llama-3-8B-Instruct",
        "meta-llama/Llama-3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Large-Instruct-2411",
        "Qwen/Qwen2-72B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3.5",
        "Qwen/Qwen3.5-30B-A3B",
        "Qwen/Qwen3.5-Coder",
        "zai-org/GLM-4.5",
        "zai-org/GLM-4.5-Air",
        "zai-org/GLM-4.6",
        "zai-org/GLM-5",
        "moonshotai/Kimi-K2",
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.5",
        "MiniMaxAI/MiniMax-M2.5",
        "stepfun-ai/Step3",
        "stepfun-ai/Step-3.5-Flash",
        "XiaomiMiMo/MiMo-V2-Flash",
        "google/gemma-4-4b-it",
        "google/gemma-4-12b-it",
        "google/gemma-4-27b-it",
        "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
        "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
        "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "HUGGINGFACE_API_KEY",
      "default_base_url": "http://127.0.0.1:3000/v1",
      "default_model": "tgi",
      "default_reasoning_effort": "default",
      "key": "tgi",
      "label": "Hugging Face TGI",
      "mode": "local",
      "model_suggestions": [
        "tgi",
        "Qwen/Qwen3-0.6B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-Coder-14B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/QwQ-32B",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "google-t5/t5-small",
        "google-t5/t5-base",
        "google-t5/t5-large",
        "google/flan-t5-small",
        "google/flan-t5-base",
        "google/flan-t5-large",
        "google/flan-t5-xl",
        "google/flan-t5-xxl",
        "RWKV/rwkv-4-world",
        "RWKV/rwkv-5-world",
        "RWKV/rwkv-6-world",
        "BlinkDL/rwkv-7-world",
        "EleutherAI/gpt-neox-20b",
        "EleutherAI/gpt-j-6b",
        "EleutherAI/gpt-neo-2.7B",
        "yandex/yalm-100b",
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.2-1B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mistral-Nemo-Instruct-2407",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mistralai/Codestral-22B-v0.1",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        "deepseek-ai/DeepSeek-Coder-V2-Instruct",
        "google/gemma-3-1b-it",
        "google/gemma-3-4b-it",
        "google/gemma-3-12b-it",
        "google/gemma-3-27b-it",
        "google/gemma-2-2b-it",
        "google/gemma-2-9b-it",
        "google/gemma-2-27b-it",
        "microsoft/phi-4",
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
        "tiiuae/Falcon3-1B-Instruct",
        "tiiuae/Falcon3-3B-Instruct",
        "tiiuae/Falcon3-7B-Instruct",
        "tiiuae/Falcon3-10B-Instruct",
        "tiiuae/falcon-180B-chat",
        "01-ai/Yi-6B-Chat",
        "01-ai/Yi-9B-Chat",
        "01-ai/Yi-34B-Chat",
        "THUDM/glm-4-9b-chat",
        "internlm/internlm2_5-7b-chat",
        "internlm/internlm2_5-20b-chat",
        "baichuan-inc/Baichuan2-7B-Chat",
        "baichuan-inc/Baichuan2-13B-Chat",
        "openbmb/MiniCPM3-4B",
        "HuggingFaceTB/SmolLM2-135M-Instruct",
        "HuggingFaceTB/SmolLM2-360M-Instruct",
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "ibm-granite/granite-3.3-2b-instruct",
        "ibm-granite/granite-3.3-8b-instruct",
        "CohereForAI/c4ai-command-r-v01",
        "CohereForAI/c4ai-command-r-plus",
        "CohereForAI/aya-23-8B",
        "CohereForAI/aya-23-35B",
        "bigscience/bloomz-7b1",
        "bigscience/bloom",
        "mosaicml/mpt-7b-instruct",
        "mosaicml/mpt-30b-instruct",
        "databricks/dbrx-instruct",
        "ai21labs/Jamba-v0.1",
        "Nexusflow/Starling-LM-7B-beta",
        "HuggingFaceH4/zephyr-7b-beta",
        "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
        "openchat/openchat-3.5-0106",
        "WizardLMTeam/WizardLM-2-8x22B",
        "lmsys/vicuna-13b-v1.5",
        "codellama/CodeLlama-7b-Instruct-hf",
        "codellama/CodeLlama-13b-Instruct-hf",
        "codellama/CodeLlama-34b-Instruct-hf",
        "bigcode/starcoder2-3b",
        "bigcode/starcoder2-7b",
        "bigcode/starcoder2-15b",
        "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "google/flan-ul2",
        "allenai/OLMo-7B-Instruct",
        "allenai/OLMo-2-1124-7B-Instruct",
        "allenai/OLMo-2-1124-13B-Instruct",
        "cerebras/Cerebras-GPT-111M",
        "cerebras/Cerebras-GPT-256M",
        "cerebras/Cerebras-GPT-590M",
        "cerebras/Cerebras-GPT-1.3B",
        "cerebras/Cerebras-GPT-2.7B",
        "cerebras/Cerebras-GPT-6.7B",
        "cerebras/Cerebras-GPT-13B",
        "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
        "EleutherAI/pythia-70m",
        "EleutherAI/pythia-160m",
        "EleutherAI/pythia-410m",
        "EleutherAI/pythia-1b",
        "EleutherAI/pythia-1.4b",
        "EleutherAI/pythia-2.8b",
        "EleutherAI/pythia-6.9b",
        "EleutherAI/pythia-12b",
        "databricks/dolly-v2-3b",
        "databricks/dolly-v2-7b",
        "databricks/dolly-v2-12b",
        "stabilityai/stablelm-base-alpha-3b",
        "stabilityai/stablelm-base-alpha-7b",
        "stabilityai/stablelm-tuned-alpha-3b",
        "stabilityai/stablelm-tuned-alpha-7b",
        "lmsys/fastchat-t5-3b-v1.0",
        "aisquared/dlite-v2-1_5b",
        "h2oai/h2ogpt-oasst1-512-12b",
        "togethercomputer/RedPajama-INCITE-7B-Instruct",
        "openlm-research/open_llama_3b",
        "openlm-research/open_llama_7b",
        "openlm-research/open_llama_13b",
        "mosaicml/mpt-7b-chat",
        "mosaicml/mpt-7b-storywriter",
        "mosaicml/mpt-30b-chat",
        "nomic-ai/gpt4all-j",
        "Salesforce/xgen-7b-8k-inst",
        "inceptionai/jais-13b-chat",
        "codellama/CodeLlama-70b-Instruct-hf",
        "teknium/OpenHermes-2.5-Mistral-7B",
        "apple/OpenELM-270M-Instruct",
        "apple/OpenELM-450M-Instruct",
        "apple/OpenELM-1_1B-Instruct",
        "apple/OpenELM-3B-Instruct",
        "Deci/DeciLM-7B-instruct",
        "THUDM/chatglm-6b",
        "THUDM/chatglm2-6b",
        "THUDM/chatglm3-6b",
        "Skywork/Skywork-13B-base",
        "LLM360/Amber",
        "Cerebras/FLOR-6.3B",
        "Qwen/Qwen1.5-0.5B-Chat",
        "Qwen/Qwen1.5-1.8B-Chat",
        "Qwen/Qwen1.5-4B-Chat",
        "Qwen/Qwen1.5-7B-Chat",
        "Qwen/Qwen1.5-14B-Chat",
        "Qwen/Qwen1.5-32B-Chat",
        "Qwen/Qwen1.5-72B-Chat",
        "Qwen/Qwen1.5-110B-Chat",
        "Qwen/Qwen1.5-MoE-A2.7B-Chat",
        "LargeWorldModel/LWM-Text-1M",
        "YerevaNN/YerevaNN-Grok-1",
        "state-spaces/mamba-130m",
        "state-spaces/mamba-370m",
        "state-spaces/mamba-790m",
        "state-spaces/mamba-1.4b",
        "state-spaces/mamba-2.8b",
        "Snowflake/snowflake-arctic-instruct",
        "Fugaku-LLM/Fugaku-LLM-13B-instruct",
        "tiiuae/Falcon2-11B",
        "01-ai/Yi-1.5-6B-Chat",
        "01-ai/Yi-1.5-9B-Chat",
        "01-ai/Yi-1.5-34B-Chat",
        "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "deepseek-ai/DeepSeek-V2-Chat",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1-0528",
        "microsoft/Phi-3-medium-128k-instruct",
        "microsoft/Phi-3-mini-128k-instruct",
        "microsoft/phi-4-reasoning",
        "yulan-team/YuLan-Mini",
        "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
        "bigcode/santacoder",
        "Salesforce/codegen2-1B",
        "Salesforce/codegen2-3_7B",
        "Salesforce/codegen2-7B",
        "HuggingFaceH4/starchat-alpha",
        "replit/replit-code-v1-3b",
        "Salesforce/codet5p-770m",
        "Salesforce/codet5p-2b",
        "Salesforce/codet5p-6b",
        "Salesforce/codegen25-7b-multi",
        "Deci/DeciCoder-1b",
        "meta-llama/Llama-2-7b-chat-hf",
        "meta-llama/Llama-2-13b-chat-hf",
        "meta-llama/Llama-2-70b-chat-hf",
        "meta-llama/Llama-3-8B-Instruct",
        "meta-llama/Llama-3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Large-Instruct-2411",
        "Qwen/Qwen2-72B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3.5",
        "Qwen/Qwen3.5-30B-A3B",
        "Qwen/Qwen3.5-Coder",
        "zai-org/GLM-4.5",
        "zai-org/GLM-4.5-Air",
        "zai-org/GLM-4.6",
        "zai-org/GLM-5",
        "moonshotai/Kimi-K2",
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.5",
        "MiniMaxAI/MiniMax-M2.5",
        "stepfun-ai/Step3",
        "stepfun-ai/Step-3.5-Flash",
        "XiaomiMiMo/MiMo-V2-Flash",
        "google/gemma-4-4b-it",
        "google/gemma-4-12b-it",
        "google/gemma-4-27b-it",
        "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
        "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
        "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    },
    {
      "api_key_env": "OPEN_SOURCE_LLM_API_KEY",
      "default_base_url": "http://127.0.0.1:8000/v1",
      "default_model": "Qwen/Qwen3-8B",
      "default_reasoning_effort": "default",
      "key": "open-source",
      "label": "Generic Open-Source / Remote",
      "mode": "local",
      "model_suggestions": [
        "Qwen/Qwen3-0.6B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-Coder-14B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/QwQ-32B",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "google-t5/t5-small",
        "google-t5/t5-base",
        "google-t5/t5-large",
        "google/flan-t5-small",
        "google/flan-t5-base",
        "google/flan-t5-large",
        "google/flan-t5-xl",
        "google/flan-t5-xxl",
        "RWKV/rwkv-4-world",
        "RWKV/rwkv-5-world",
        "RWKV/rwkv-6-world",
        "BlinkDL/rwkv-7-world",
        "EleutherAI/gpt-neox-20b",
        "EleutherAI/gpt-j-6b",
        "EleutherAI/gpt-neo-2.7B",
        "yandex/yalm-100b",
        "meta-llama/Llama-3.3-70B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.2-1B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mistral-Nemo-Instruct-2407",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mistralai/Codestral-22B-v0.1",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        "deepseek-ai/DeepSeek-Coder-V2-Instruct",
        "google/gemma-3-1b-it",
        "google/gemma-3-4b-it",
        "google/gemma-3-12b-it",
        "google/gemma-3-27b-it",
        "google/gemma-2-2b-it",
        "google/gemma-2-9b-it",
        "google/gemma-2-27b-it",
        "microsoft/phi-4",
        "microsoft/Phi-4-mini-instruct",
        "microsoft/Phi-3.5-mini-instruct",
        "tiiuae/Falcon3-1B-Instruct",
        "tiiuae/Falcon3-3B-Instruct",
        "tiiuae/Falcon3-7B-Instruct",
        "tiiuae/Falcon3-10B-Instruct",
        "tiiuae/falcon-180B-chat",
        "01-ai/Yi-6B-Chat",
        "01-ai/Yi-9B-Chat",
        "01-ai/Yi-34B-Chat",
        "THUDM/glm-4-9b-chat",
        "internlm/internlm2_5-7b-chat",
        "internlm/internlm2_5-20b-chat",
        "baichuan-inc/Baichuan2-7B-Chat",
        "baichuan-inc/Baichuan2-13B-Chat",
        "openbmb/MiniCPM3-4B",
        "HuggingFaceTB/SmolLM2-135M-Instruct",
        "HuggingFaceTB/SmolLM2-360M-Instruct",
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "ibm-granite/granite-3.3-2b-instruct",
        "ibm-granite/granite-3.3-8b-instruct",
        "CohereForAI/c4ai-command-r-v01",
        "CohereForAI/c4ai-command-r-plus",
        "CohereForAI/aya-23-8B",
        "CohereForAI/aya-23-35B",
        "bigscience/bloomz-7b1",
        "bigscience/bloom",
        "mosaicml/mpt-7b-instruct",
        "mosaicml/mpt-30b-instruct",
        "databricks/dbrx-instruct",
        "ai21labs/Jamba-v0.1",
        "Nexusflow/Starling-LM-7B-beta",
        "HuggingFaceH4/zephyr-7b-beta",
        "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
        "openchat/openchat-3.5-0106",
        "WizardLMTeam/WizardLM-2-8x22B",
        "lmsys/vicuna-13b-v1.5",
        "codellama/CodeLlama-7b-Instruct-hf",
        "codellama/CodeLlama-13b-Instruct-hf",
        "codellama/CodeLlama-34b-Instruct-hf",
        "bigcode/starcoder2-3b",
        "bigcode/starcoder2-7b",
        "bigcode/starcoder2-15b",
        "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "google/flan-ul2",
        "allenai/OLMo-7B-Instruct",
        "allenai/OLMo-2-1124-7B-Instruct",
        "allenai/OLMo-2-1124-13B-Instruct",
        "cerebras/Cerebras-GPT-111M",
        "cerebras/Cerebras-GPT-256M",
        "cerebras/Cerebras-GPT-590M",
        "cerebras/Cerebras-GPT-1.3B",
        "cerebras/Cerebras-GPT-2.7B",
        "cerebras/Cerebras-GPT-6.7B",
        "cerebras/Cerebras-GPT-13B",
        "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
        "EleutherAI/pythia-70m",
        "EleutherAI/pythia-160m",
        "EleutherAI/pythia-410m",
        "EleutherAI/pythia-1b",
        "EleutherAI/pythia-1.4b",
        "EleutherAI/pythia-2.8b",
        "EleutherAI/pythia-6.9b",
        "EleutherAI/pythia-12b",
        "databricks/dolly-v2-3b",
        "databricks/dolly-v2-7b",
        "databricks/dolly-v2-12b",
        "stabilityai/stablelm-base-alpha-3b",
        "stabilityai/stablelm-base-alpha-7b",
        "stabilityai/stablelm-tuned-alpha-3b",
        "stabilityai/stablelm-tuned-alpha-7b",
        "lmsys/fastchat-t5-3b-v1.0",
        "aisquared/dlite-v2-1_5b",
        "h2oai/h2ogpt-oasst1-512-12b",
        "togethercomputer/RedPajama-INCITE-7B-Instruct",
        "openlm-research/open_llama_3b",
        "openlm-research/open_llama_7b",
        "openlm-research/open_llama_13b",
        "mosaicml/mpt-7b-chat",
        "mosaicml/mpt-7b-storywriter",
        "mosaicml/mpt-30b-chat",
        "nomic-ai/gpt4all-j",
        "Salesforce/xgen-7b-8k-inst",
        "inceptionai/jais-13b-chat",
        "codellama/CodeLlama-70b-Instruct-hf",
        "teknium/OpenHermes-2.5-Mistral-7B",
        "apple/OpenELM-270M-Instruct",
        "apple/OpenELM-450M-Instruct",
        "apple/OpenELM-1_1B-Instruct",
        "apple/OpenELM-3B-Instruct",
        "Deci/DeciLM-7B-instruct",
        "THUDM/chatglm-6b",
        "THUDM/chatglm2-6b",
        "THUDM/chatglm3-6b",
        "Skywork/Skywork-13B-base",
        "LLM360/Amber",
        "Cerebras/FLOR-6.3B",
        "Qwen/Qwen1.5-0.5B-Chat",
        "Qwen/Qwen1.5-1.8B-Chat",
        "Qwen/Qwen1.5-4B-Chat",
        "Qwen/Qwen1.5-7B-Chat",
        "Qwen/Qwen1.5-14B-Chat",
        "Qwen/Qwen1.5-32B-Chat",
        "Qwen/Qwen1.5-72B-Chat",
        "Qwen/Qwen1.5-110B-Chat",
        "Qwen/Qwen1.5-MoE-A2.7B-Chat",
        "LargeWorldModel/LWM-Text-1M",
        "YerevaNN/YerevaNN-Grok-1",
        "state-spaces/mamba-130m",
        "state-spaces/mamba-370m",
        "state-spaces/mamba-790m",
        "state-spaces/mamba-1.4b",
        "state-spaces/mamba-2.8b",
        "Snowflake/snowflake-arctic-instruct",
        "Fugaku-LLM/Fugaku-LLM-13B-instruct",
        "tiiuae/Falcon2-11B",
        "01-ai/Yi-1.5-6B-Chat",
        "01-ai/Yi-1.5-9B-Chat",
        "01-ai/Yi-1.5-34B-Chat",
        "deepseek-ai/DeepSeek-V2-Lite-Chat",
        "deepseek-ai/DeepSeek-V2-Chat",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3-0324",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-R1-0528",
        "microsoft/Phi-3-medium-128k-instruct",
        "microsoft/Phi-3-mini-128k-instruct",
        "microsoft/phi-4-reasoning",
        "yulan-team/YuLan-Mini",
        "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
        "bigcode/santacoder",
        "Salesforce/codegen2-1B",
        "Salesforce/codegen2-3_7B",
        "Salesforce/codegen2-7B",
        "HuggingFaceH4/starchat-alpha",
        "replit/replit-code-v1-3b",
        "Salesforce/codet5p-770m",
        "Salesforce/codet5p-2b",
        "Salesforce/codet5p-6b",
        "Salesforce/codegen25-7b-multi",
        "Deci/DeciCoder-1b",
        "meta-llama/Llama-2-7b-chat-hf",
        "meta-llama/Llama-2-13b-chat-hf",
        "meta-llama/Llama-2-70b-chat-hf",
        "meta-llama/Llama-3-8B-Instruct",
        "meta-llama/Llama-3-70B-Instruct",
        "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Large-Instruct-2411",
        "Qwen/Qwen2-72B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3.5",
        "Qwen/Qwen3.5-30B-A3B",
        "Qwen/Qwen3.5-Coder",
        "zai-org/GLM-4.5",
        "zai-org/GLM-4.5-Air",
        "zai-org/GLM-4.6",
        "zai-org/GLM-5",
        "moonshotai/Kimi-K2",
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2.5",
        "MiniMaxAI/MiniMax-M2.5",
        "stepfun-ai/Step3",
        "stepfun-ai/Step-3.5-Flash",
        "XiaomiMiMo/MiMo-V2-Flash",
        "google/gemma-4-4b-it",
        "google/gemma-4-12b-it",
        "google/gemma-4-27b-it",
        "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
        "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
        "nvidia/Llama-3.1-Nemotron-Nano-8B-v1",
        "qwen3:0.6b",
        "qwen3:1.7b",
        "qwen3:4b",
        "qwen3:8b",
        "qwen3:14b",
        "qwen3:30b-a3b",
        "qwen3:32b",
        "qwen3",
        "qwen3-vl:8b",
        "qwen3-vl:32b",
        "qwen3.5",
        "qwen2.5:0.5b",
        "qwen2.5:1.5b",
        "qwen2.5:3b",
        "qwen2.5:7b",
        "qwen2.5:14b",
        "qwen2.5:32b",
        "qwen2.5:72b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:7b",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:32b",
        "qwq:32b",
        "gpt-oss:20b",
        "gpt-oss:120b",
        "gpt-oss:latest",
        "llama4:maverick",
        "llama4:scout",
        "deepseek-v3",
        "deepseek-v3.1",
        "deepseek-v3.2",
        "deepseek-r1:1.5b",
        "deepseek-r1:7b",
        "deepseek-r1:8b",
        "deepseek-r1:14b",
        "deepseek-r1:32b",
        "deepseek-r1:70b",
        "deepseek-coder-v2",
        "llama3.3",
        "llama3.1:8b",
        "llama3.1:70b",
        "llama3.2:1b",
        "llama3.2:3b",
        "llama3.2-vision:11b",
        "llama3.2-vision:90b",
        "mistral",
        "mistral-nemo",
        "mistral-small3.2",
        "mixtral:8x7b",
        "mixtral:8x22b",
        "codestral",
        "devstral",
        "gemma3:1b",
        "gemma3:4b",
        "gemma3:12b",
        "gemma3:27b",
        "gemma4:27b",
        "gemma2:2b",
        "gemma2:9b",
        "gemma2:27b",
        "phi4",
        "phi4-mini",
        "phi3.5",
        "phi3:mini",
        "falcon3:1b",
        "falcon3:3b",
        "falcon3:7b",
        "falcon3:10b",
        "yi:6b",
        "yi:9b",
        "yi:34b",
        "glm4",
        "glm4.5",
        "glm5",
        "kimi-k2",
        "minimax-m2",
        "step3",
        "mimo-v2",
        "internlm2.5",
        "baichuan2:7b",
        "baichuan2:13b",
        "minicpm-v",
        "smollm2:135m",
        "smollm2:360m",
        "smollm2:1.7b",
        "granite3.3:2b",
        "granite3.3:8b",
        "command-r",
        "command-r-plus",
        "starcoder2:3b",
        "starcoder2:7b",
        "starcoder2:15b",
        "codellama:7b",
        "codellama:13b",
        "codellama:34b",
        "dolphin-mixtral",
        "openchat",
        "neural-chat",
        "orca-mini",
        "zephyr",
        "solar",
        "nous-hermes2",
        "wizardlm2",
        "vicuna",
        "rwkv",
        "pythia",
        "dolly-v2",
        "stablelm",
        "redpajama",
        "openllama",
        "mpt",
        "dbrx",
        "arctic",
        "bloom",
        "bloomz",
        "mamba",
        "custom-model"
      ],
      "protocol": "openai-chat-completions",
      "reasoning_efforts": [
        "default",
        "none",
        "disabled",
        "auto",
        "low",
        "medium",
        "high",
        "xhigh"
      ]
    }
  ],
  "llmUseForOptions": [
    {
      "key": "advisory",
      "label": "Advisory",
      "value": "advisory"
    },
    {
      "key": "signal_confirmation",
      "label": "Signal confirmation",
      "value": "signal_confirmation"
    },
    {
      "key": "risk_review",
      "label": "Risk review",
      "value": "risk_review"
    },
    {
      "key": "backtest_explanation",
      "label": "Backtest explanation",
      "value": "backtest_explanation"
    }
  ],
  "marginModeOptions": [
    {
      "key": "Isolated",
      "label": "Isolated",
      "value": "Isolated"
    },
    {
      "key": "Cross",
      "label": "Cross",
      "value": "Cross"
    }
  ],
  "mddLogicOptions": [
    {
      "key": "per_trade",
      "label": "Per Trade MDD"
    },
    {
      "key": "cumulative",
      "label": "Cumulative MDD"
    },
    {
      "key": "entire_account",
      "label": "Entire Account MDD"
    }
  ],
  "optimizerMetricOptions": [
    {
      "key": "roi_percent",
      "label": "roi_percent",
      "value": "roi_percent"
    },
    {
      "key": "roi_percent_mdd",
      "label": "roi_percent_mdd",
      "value": "roi_percent_mdd"
    },
    {
      "key": "roi_drawdown",
      "label": "roi_drawdown",
      "value": "roi_drawdown"
    },
    {
      "key": "roi_value",
      "label": "roi_value",
      "value": "roi_value"
    }
  ],
  "optimizerModeOptions": [
    {
      "key": "current",
      "label": "current",
      "value": "current"
    },
    {
      "key": "single",
      "label": "single",
      "value": "single"
    },
    {
      "key": "pairs",
      "label": "pairs",
      "value": "pairs"
    },
    {
      "key": "combinations",
      "label": "combinations",
      "value": "combinations"
    }
  ],
  "orderTypeOptions": [
    {
      "key": "MARKET",
      "label": "MARKET",
      "value": "MARKET"
    },
    {
      "key": "LIMIT",
      "label": "LIMIT",
      "value": "LIMIT"
    }
  ],
  "positionModeOptions": [
    {
      "key": "Hedge",
      "label": "Hedge",
      "value": "Hedge"
    },
    {
      "key": "One-way",
      "label": "One-way",
      "value": "One-way"
    }
  ],
  "positionsViewOptions": [
    {
      "key": "cumulative",
      "label": "Cumulative View",
      "value": "cumulative"
    },
    {
      "key": "per_trade",
      "label": "Per Trade View",
      "value": "per_trade"
    }
  ],
  "scanScopeOptions": [
    {
      "key": "selected",
      "label": "selected",
      "value": "selected"
    },
    {
      "key": "top_n",
      "label": "top_n",
      "value": "top_n"
    },
    {
      "key": "all_loaded",
      "label": "all_loaded",
      "value": "all_loaded"
    }
  ],
  "schemaVersion": 1,
  "serviceRouteMethods": {
    "account": [
      "GET",
      "PUT"
    ],
    "backtest": [
      "GET"
    ],
    "backtest_run": [
      "POST"
    ],
    "backtest_stop": [
      "POST"
    ],
    "config": [
      "GET",
      "PUT",
      "PATCH"
    ],
    "config_load": [
      "POST"
    ],
    "config_persistence": [
      "GET"
    ],
    "config_save": [
      "POST"
    ],
    "config_summary": [
      "GET"
    ],
    "connector_order_circuit_breaker": [
      "GET",
      "PUT"
    ],
    "connector_order_circuit_breaker_reset": [
      "POST"
    ],
    "connector_order_circuit_incidents": [
      "GET"
    ],
    "control_start": [
      "POST"
    ],
    "control_start_failed": [
      "POST"
    ],
    "control_stop": [
      "POST"
    ],
    "dashboard": [
      "GET"
    ],
    "exchange_connector": [
      "GET",
      "PUT"
    ],
    "execution": [
      "GET"
    ],
    "llm_config": [
      "GET",
      "PATCH"
    ],
    "llm_local_model_delete": [
      "POST"
    ],
    "llm_local_model_pull": [
      "POST"
    ],
    "llm_local_model_start": [
      "POST"
    ],
    "llm_local_model_status": [
      "GET"
    ],
    "llm_prompt": [
      "POST"
    ],
    "llm_providers": [
      "GET"
    ],
    "logs": [
      "GET",
      "POST"
    ],
    "operational_preflight": [
      "GET"
    ],
    "portfolio": [
      "GET",
      "PUT"
    ],
    "runtime": [
      "GET"
    ],
    "runtime_state": [
      "PUT"
    ],
    "status": [
      "GET"
    ],
    "stream_dashboard": [
      "GET"
    ],
    "terminal_run": [
      "POST"
    ]
  },
  "serviceRouteNames": [
    "runtime",
    "dashboard",
    "status",
    "execution",
    "backtest",
    "config_summary",
    "config",
    "config_persistence",
    "config_save",
    "config_load",
    "runtime_state",
    "operational_preflight",
    "control_start",
    "control_stop",
    "control_start_failed",
    "connector_order_circuit_breaker",
    "connector_order_circuit_breaker_reset",
    "connector_order_circuit_incidents",
    "backtest_run",
    "backtest_stop",
    "account",
    "portfolio",
    "exchange_connector",
    "logs",
    "terminal_run",
    "llm_providers",
    "llm_config",
    "llm_prompt",
    "llm_local_model_status",
    "llm_local_model_start",
    "llm_local_model_pull",
    "llm_local_model_delete",
    "stream_dashboard"
  ],
  "serviceRoutePaths": {
    "account": "/api/v1/account",
    "backtest": "/api/v1/backtest",
    "backtest_run": "/api/v1/backtest/run",
    "backtest_stop": "/api/v1/backtest/stop",
    "config": "/api/v1/config",
    "config_load": "/api/v1/config/load",
    "config_persistence": "/api/v1/config/persistence",
    "config_save": "/api/v1/config/save",
    "config_summary": "/api/v1/config-summary",
    "connector_order_circuit_breaker": "/api/v1/runtime/connector-order-circuit-breaker",
    "connector_order_circuit_breaker_reset": "/api/v1/runtime/connector-order-circuit-breaker/reset",
    "connector_order_circuit_incidents": "/api/v1/runtime/connector-order-circuit-breaker/incidents",
    "control_start": "/api/v1/control/start",
    "control_start_failed": "/api/v1/control/start-failed",
    "control_stop": "/api/v1/control/stop",
    "dashboard": "/api/v1/dashboard",
    "exchange_connector": "/api/v1/exchange/connector",
    "execution": "/api/v1/execution",
    "llm_config": "/api/v1/llm/config",
    "llm_local_model_delete": "/api/v1/llm/local-model/delete",
    "llm_local_model_pull": "/api/v1/llm/local-model/pull",
    "llm_local_model_start": "/api/v1/llm/local-model/start",
    "llm_local_model_status": "/api/v1/llm/local-model/status",
    "llm_prompt": "/api/v1/llm/prompt",
    "llm_providers": "/api/v1/llm/providers",
    "logs": "/api/v1/logs",
    "operational_preflight": "/api/v1/runtime/operational-preflight",
    "portfolio": "/api/v1/portfolio",
    "runtime": "/api/v1/runtime",
    "runtime_state": "/api/v1/runtime/state",
    "status": "/api/v1/status",
    "stream_dashboard": "/api/v1/stream/dashboard",
    "terminal_run": "/api/v1/terminal/run"
  },
  "serviceRouteQueryFields": {
    "account": [],
    "backtest": [],
    "backtest_run": [],
    "backtest_stop": [],
    "config": [],
    "config_load": [],
    "config_persistence": [],
    "config_save": [],
    "config_summary": [],
    "connector_order_circuit_breaker": [],
    "connector_order_circuit_breaker_reset": [],
    "connector_order_circuit_incidents": [
      "limit"
    ],
    "control_start": [],
    "control_start_failed": [],
    "control_stop": [],
    "dashboard": [
      "log_limit",
      "incident_limit"
    ],
    "exchange_connector": [],
    "execution": [],
    "llm_config": [],
    "llm_local_model_delete": [],
    "llm_local_model_pull": [],
    "llm_local_model_start": [],
    "llm_local_model_status": [
      "base_url",
      "model"
    ],
    "llm_prompt": [],
    "llm_providers": [],
    "logs": [
      "limit"
    ],
    "operational_preflight": [],
    "portfolio": [],
    "runtime": [],
    "runtime_state": [],
    "status": [],
    "stream_dashboard": [
      "log_limit",
      "incident_limit",
      "interval_ms",
      "max_events"
    ],
    "terminal_run": []
  },
  "serviceRouteRequestFields": {
    "account": [
      "total_balance",
      "available_balance",
      "source"
    ],
    "backtest": [],
    "backtest_run": [
      "request",
      "source"
    ],
    "backtest_stop": [
      "source"
    ],
    "config": [
      "config"
    ],
    "config_load": [
      "path",
      "source",
      "allow_unsafe_path"
    ],
    "config_persistence": [],
    "config_save": [
      "path",
      "source",
      "allow_unsafe_path"
    ],
    "config_summary": [],
    "connector_order_circuit_breaker": [
      "snapshot",
      "source",
      "force"
    ],
    "connector_order_circuit_breaker_reset": [
      "snapshot",
      "source",
      "force"
    ],
    "connector_order_circuit_incidents": [],
    "control_start": [
      "requested_job_count",
      "source"
    ],
    "control_start_failed": [
      "reason",
      "source"
    ],
    "control_stop": [
      "close_positions",
      "source"
    ],
    "dashboard": [],
    "exchange_connector": [
      "snapshot",
      "source"
    ],
    "execution": [],
    "llm_config": [
      "config"
    ],
    "llm_local_model_delete": [
      "base_url",
      "model",
      "source"
    ],
    "llm_local_model_pull": [
      "base_url",
      "model",
      "source"
    ],
    "llm_local_model_start": [
      "base_url",
      "model",
      "source"
    ],
    "llm_local_model_status": [],
    "llm_prompt": [
      "prompt",
      "system_prompt",
      "dry_run",
      "source"
    ],
    "llm_providers": [],
    "logs": [
      "message",
      "source",
      "level"
    ],
    "operational_preflight": [],
    "portfolio": [
      "open_position_records",
      "closed_position_records",
      "closed_trade_registry",
      "active_pnl",
      "active_margin",
      "closed_pnl",
      "closed_margin",
      "total_balance",
      "available_balance",
      "source"
    ],
    "runtime": [],
    "runtime_state": [
      "active",
      "active_engine_count",
      "source"
    ],
    "status": [],
    "stream_dashboard": [],
    "terminal_run": [
      "command",
      "source"
    ]
  },
  "serviceRouteResponseFields": {
    "account": [
      "account_type",
      "mode",
      "selected_exchange",
      "connector_backend",
      "balance_currency",
      "total_balance",
      "available_balance",
      "source",
      "generated_at"
    ],
    "backtest": [
      "session_id",
      "state",
      "workload_kind",
      "status_message",
      "symbols",
      "intervals",
      "indicator_keys",
      "logic",
      "symbol_source",
      "capital",
      "run_count",
      "error_count",
      "cancelled",
      "started_at",
      "completed_at",
      "updated_at",
      "source",
      "top_run",
      "runs",
      "top_runs",
      "errors"
    ],
    "backtest_run": [
      "accepted",
      "action",
      "session_id",
      "state",
      "status_message",
      "source"
    ],
    "backtest_stop": [
      "accepted",
      "action",
      "session_id",
      "state",
      "status_message",
      "source"
    ],
    "config": [
      "mode",
      "account_type",
      "margin_mode",
      "position_mode",
      "side",
      "leverage",
      "position_pct",
      "connector_backend",
      "selected_exchange",
      "code_language",
      "theme",
      "design",
      "order_audit_max_bytes",
      "order_audit_backup_count",
      "connector_order_circuit_incident_log_max_bytes",
      "connector_order_circuit_incident_log_backup_count",
      "operational_connector_snapshot_stale_seconds",
      "operational_execution_heartbeat_stale_seconds",
      "operational_account_snapshot_stale_seconds",
      "operational_portfolio_snapshot_stale_seconds",
      "operational_live_start_gate_enabled",
      "operational_live_order_gate_enabled",
      "live_allow_auto_bump_to_min_order",
      "symbols",
      "intervals",
      "api_credentials_present",
      "llm",
      "exchange_support"
    ],
    "config_load": [
      "config",
      "persistence"
    ],
    "config_persistence": [
      "path",
      "exists",
      "modified_at",
      "kind",
      "format_version",
      "loaded",
      "dirty",
      "last_loaded_at",
      "last_saved_at",
      "migrated_from_format_version"
    ],
    "config_save": [
      "path",
      "exists",
      "modified_at",
      "kind",
      "format_version",
      "loaded",
      "dirty",
      "last_loaded_at",
      "last_saved_at",
      "migrated_from_format_version"
    ],
    "config_summary": [
      "mode",
      "account_type",
      "connector_backend",
      "selected_exchange",
      "code_language",
      "theme",
      "design",
      "api_credentials_present",
      "symbol_count",
      "interval_count",
      "enabled_indicator_count",
      "runtime_pair_count",
      "backtest_pair_count",
      "llm_enabled",
      "llm_provider",
      "llm_mode",
      "llm_api_key_present"
    ],
    "connector_order_circuit_breaker": [
      "active",
      "state",
      "reason",
      "message",
      "block_count",
      "block_threshold",
      "block_window_seconds",
      "source",
      "generated_at"
    ],
    "connector_order_circuit_breaker_reset": [
      "active",
      "state",
      "source",
      "generated_at"
    ],
    "connector_order_circuit_incidents": [
      "path",
      "path_source",
      "configured_path",
      "limit",
      "events",
      "parse_errors"
    ],
    "control_start": [
      "accepted",
      "action",
      "lifecycle_phase",
      "runtime_active",
      "active_engine_count",
      "requested_job_count",
      "close_positions_requested",
      "source",
      "status_message",
      "generated_at"
    ],
    "control_start_failed": [
      "accepted",
      "action",
      "lifecycle_phase",
      "runtime_active",
      "active_engine_count",
      "requested_job_count",
      "close_positions_requested",
      "source",
      "status_message",
      "generated_at"
    ],
    "control_stop": [
      "accepted",
      "action",
      "lifecycle_phase",
      "runtime_active",
      "active_engine_count",
      "requested_job_count",
      "close_positions_requested",
      "source",
      "status_message",
      "generated_at"
    ],
    "dashboard": [
      "runtime",
      "status",
      "operational",
      "config",
      "config_summary",
      "execution",
      "backtest",
      "account",
      "portfolio",
      "logs",
      "service_api",
      "connector_order_circuit_incidents"
    ],
    "exchange_connector": [
      "health",
      "state",
      "generated_at",
      "source",
      "selected_exchange",
      "connector_backend",
      "support",
      "rate_limit",
      "network",
      "last_error",
      "attention"
    ],
    "execution": [
      "executor_kind",
      "owner",
      "state",
      "workload_kind",
      "session_id",
      "requested_job_count",
      "active_engine_count",
      "progress_label",
      "progress_percent",
      "heartbeat_at",
      "tick_count",
      "last_action",
      "last_message",
      "started_at",
      "updated_at",
      "source",
      "notes"
    ],
    "llm_config": [
      "enabled",
      "provider",
      "provider_label",
      "mode",
      "protocol",
      "model",
      "base_url",
      "api_key_env",
      "api_key_present",
      "allow_public_network",
      "use_for",
      "reasoning_effort"
    ],
    "llm_local_model_delete": [
      "ok",
      "action",
      "model",
      "status"
    ],
    "llm_local_model_pull": [
      "ok",
      "action",
      "model",
      "status"
    ],
    "llm_local_model_start": [
      "started",
      "server_kind",
      "executable",
      "error"
    ],
    "llm_local_model_status": [
      "model",
      "base_url",
      "server_kind",
      "installed",
      "can_download",
      "can_start",
      "storage_hint",
      "storage_paths",
      "estimated_size_label"
    ],
    "llm_prompt": [
      "provider",
      "model",
      "dry_run",
      "prompt",
      "system_prompt",
      "response",
      "source"
    ],
    "llm_providers": [
      "key",
      "label",
      "mode",
      "protocol",
      "default_base_url",
      "default_model",
      "api_key_env",
      "model_suggestions",
      "reasoning_efforts",
      "default_reasoning_effort"
    ],
    "logs": [
      "sequence_id",
      "level",
      "message",
      "source",
      "generated_at"
    ],
    "operational_preflight": [
      "state",
      "message",
      "mode",
      "live_mode",
      "generated_at",
      "start",
      "orders",
      "freshness",
      "critical_stale",
      "reasons"
    ],
    "portfolio": [
      "account_type",
      "open_position_count",
      "closed_position_count",
      "active_pnl",
      "active_margin",
      "closed_pnl",
      "closed_margin",
      "total_balance",
      "available_balance",
      "positions",
      "source",
      "generated_at"
    ],
    "runtime": [
      "service_name",
      "phase",
      "python_entrypoint",
      "desktop_entrypoint",
      "repo_root",
      "platform",
      "python_version",
      "capabilities",
      "control_plane",
      "notes"
    ],
    "runtime_state": [
      "state",
      "lifecycle_phase",
      "requested_action",
      "close_positions_requested",
      "status_message",
      "last_transition_at",
      "service_mode",
      "generated_at",
      "api_enabled",
      "docker_required",
      "runtime_source",
      "active_engine_count",
      "account_type",
      "mode",
      "selected_exchange",
      "connector_backend",
      "connector_health",
      "exchange_connector",
      "operational_health",
      "operational",
      "notes"
    ],
    "status": [
      "state",
      "lifecycle_phase",
      "requested_action",
      "close_positions_requested",
      "status_message",
      "last_transition_at",
      "service_mode",
      "generated_at",
      "api_enabled",
      "docker_required",
      "runtime_source",
      "active_engine_count",
      "account_type",
      "mode",
      "selected_exchange",
      "connector_backend",
      "connector_health",
      "exchange_connector",
      "operational_health",
      "operational",
      "notes"
    ],
    "stream_dashboard": [
      "event",
      "data"
    ],
    "terminal_run": [
      "command",
      "exit_code",
      "output",
      "source",
      "generated_at"
    ]
  },
  "serviceRouteSchemas": [
    {
      "name": "runtime",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "service_name",
        "phase",
        "python_entrypoint",
        "desktop_entrypoint",
        "repo_root",
        "platform",
        "python_version",
        "capabilities",
        "control_plane",
        "notes"
      ]
    },
    {
      "name": "dashboard",
      "query_fields": [
        "log_limit",
        "incident_limit"
      ],
      "request_fields": [],
      "response_fields": [
        "runtime",
        "status",
        "operational",
        "config",
        "config_summary",
        "execution",
        "backtest",
        "account",
        "portfolio",
        "logs",
        "service_api",
        "connector_order_circuit_incidents"
      ]
    },
    {
      "name": "status",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "state",
        "lifecycle_phase",
        "requested_action",
        "close_positions_requested",
        "status_message",
        "last_transition_at",
        "service_mode",
        "generated_at",
        "api_enabled",
        "docker_required",
        "runtime_source",
        "active_engine_count",
        "account_type",
        "mode",
        "selected_exchange",
        "connector_backend",
        "connector_health",
        "exchange_connector",
        "operational_health",
        "operational",
        "notes"
      ]
    },
    {
      "name": "execution",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "executor_kind",
        "owner",
        "state",
        "workload_kind",
        "session_id",
        "requested_job_count",
        "active_engine_count",
        "progress_label",
        "progress_percent",
        "heartbeat_at",
        "tick_count",
        "last_action",
        "last_message",
        "started_at",
        "updated_at",
        "source",
        "notes"
      ]
    },
    {
      "name": "backtest",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "session_id",
        "state",
        "workload_kind",
        "status_message",
        "symbols",
        "intervals",
        "indicator_keys",
        "logic",
        "symbol_source",
        "capital",
        "run_count",
        "error_count",
        "cancelled",
        "started_at",
        "completed_at",
        "updated_at",
        "source",
        "top_run",
        "runs",
        "top_runs",
        "errors"
      ]
    },
    {
      "name": "config_summary",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "mode",
        "account_type",
        "connector_backend",
        "selected_exchange",
        "code_language",
        "theme",
        "design",
        "api_credentials_present",
        "symbol_count",
        "interval_count",
        "enabled_indicator_count",
        "runtime_pair_count",
        "backtest_pair_count",
        "llm_enabled",
        "llm_provider",
        "llm_mode",
        "llm_api_key_present"
      ]
    },
    {
      "name": "config",
      "query_fields": [],
      "request_fields": [
        "config"
      ],
      "response_fields": [
        "mode",
        "account_type",
        "margin_mode",
        "position_mode",
        "side",
        "leverage",
        "position_pct",
        "connector_backend",
        "selected_exchange",
        "code_language",
        "theme",
        "design",
        "order_audit_max_bytes",
        "order_audit_backup_count",
        "connector_order_circuit_incident_log_max_bytes",
        "connector_order_circuit_incident_log_backup_count",
        "operational_connector_snapshot_stale_seconds",
        "operational_execution_heartbeat_stale_seconds",
        "operational_account_snapshot_stale_seconds",
        "operational_portfolio_snapshot_stale_seconds",
        "operational_live_start_gate_enabled",
        "operational_live_order_gate_enabled",
        "live_allow_auto_bump_to_min_order",
        "symbols",
        "intervals",
        "api_credentials_present",
        "llm",
        "exchange_support"
      ]
    },
    {
      "name": "config_persistence",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "path",
        "exists",
        "modified_at",
        "kind",
        "format_version",
        "loaded",
        "dirty",
        "last_loaded_at",
        "last_saved_at",
        "migrated_from_format_version"
      ]
    },
    {
      "name": "config_save",
      "query_fields": [],
      "request_fields": [
        "path",
        "source",
        "allow_unsafe_path"
      ],
      "response_fields": [
        "path",
        "exists",
        "modified_at",
        "kind",
        "format_version",
        "loaded",
        "dirty",
        "last_loaded_at",
        "last_saved_at",
        "migrated_from_format_version"
      ]
    },
    {
      "name": "config_load",
      "query_fields": [],
      "request_fields": [
        "path",
        "source",
        "allow_unsafe_path"
      ],
      "response_fields": [
        "config",
        "persistence"
      ]
    },
    {
      "name": "runtime_state",
      "query_fields": [],
      "request_fields": [
        "active",
        "active_engine_count",
        "source"
      ],
      "response_fields": [
        "state",
        "lifecycle_phase",
        "requested_action",
        "close_positions_requested",
        "status_message",
        "last_transition_at",
        "service_mode",
        "generated_at",
        "api_enabled",
        "docker_required",
        "runtime_source",
        "active_engine_count",
        "account_type",
        "mode",
        "selected_exchange",
        "connector_backend",
        "connector_health",
        "exchange_connector",
        "operational_health",
        "operational",
        "notes"
      ]
    },
    {
      "name": "operational_preflight",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "state",
        "message",
        "mode",
        "live_mode",
        "generated_at",
        "start",
        "orders",
        "freshness",
        "critical_stale",
        "reasons"
      ]
    },
    {
      "name": "control_start",
      "query_fields": [],
      "request_fields": [
        "requested_job_count",
        "source"
      ],
      "response_fields": [
        "accepted",
        "action",
        "lifecycle_phase",
        "runtime_active",
        "active_engine_count",
        "requested_job_count",
        "close_positions_requested",
        "source",
        "status_message",
        "generated_at"
      ]
    },
    {
      "name": "control_stop",
      "query_fields": [],
      "request_fields": [
        "close_positions",
        "source"
      ],
      "response_fields": [
        "accepted",
        "action",
        "lifecycle_phase",
        "runtime_active",
        "active_engine_count",
        "requested_job_count",
        "close_positions_requested",
        "source",
        "status_message",
        "generated_at"
      ]
    },
    {
      "name": "control_start_failed",
      "query_fields": [],
      "request_fields": [
        "reason",
        "source"
      ],
      "response_fields": [
        "accepted",
        "action",
        "lifecycle_phase",
        "runtime_active",
        "active_engine_count",
        "requested_job_count",
        "close_positions_requested",
        "source",
        "status_message",
        "generated_at"
      ]
    },
    {
      "name": "connector_order_circuit_breaker",
      "query_fields": [],
      "request_fields": [
        "snapshot",
        "source",
        "force"
      ],
      "response_fields": [
        "active",
        "state",
        "reason",
        "message",
        "block_count",
        "block_threshold",
        "block_window_seconds",
        "source",
        "generated_at"
      ]
    },
    {
      "name": "connector_order_circuit_breaker_reset",
      "query_fields": [],
      "request_fields": [
        "snapshot",
        "source",
        "force"
      ],
      "response_fields": [
        "active",
        "state",
        "source",
        "generated_at"
      ]
    },
    {
      "name": "connector_order_circuit_incidents",
      "query_fields": [
        "limit"
      ],
      "request_fields": [],
      "response_fields": [
        "path",
        "path_source",
        "configured_path",
        "limit",
        "events",
        "parse_errors"
      ]
    },
    {
      "name": "backtest_run",
      "query_fields": [],
      "request_fields": [
        "request",
        "source"
      ],
      "response_fields": [
        "accepted",
        "action",
        "session_id",
        "state",
        "status_message",
        "source"
      ]
    },
    {
      "name": "backtest_stop",
      "query_fields": [],
      "request_fields": [
        "source"
      ],
      "response_fields": [
        "accepted",
        "action",
        "session_id",
        "state",
        "status_message",
        "source"
      ]
    },
    {
      "name": "account",
      "query_fields": [],
      "request_fields": [
        "total_balance",
        "available_balance",
        "source"
      ],
      "response_fields": [
        "account_type",
        "mode",
        "selected_exchange",
        "connector_backend",
        "balance_currency",
        "total_balance",
        "available_balance",
        "source",
        "generated_at"
      ]
    },
    {
      "name": "portfolio",
      "query_fields": [],
      "request_fields": [
        "open_position_records",
        "closed_position_records",
        "closed_trade_registry",
        "active_pnl",
        "active_margin",
        "closed_pnl",
        "closed_margin",
        "total_balance",
        "available_balance",
        "source"
      ],
      "response_fields": [
        "account_type",
        "open_position_count",
        "closed_position_count",
        "active_pnl",
        "active_margin",
        "closed_pnl",
        "closed_margin",
        "total_balance",
        "available_balance",
        "positions",
        "source",
        "generated_at"
      ]
    },
    {
      "name": "exchange_connector",
      "query_fields": [],
      "request_fields": [
        "snapshot",
        "source"
      ],
      "response_fields": [
        "health",
        "state",
        "generated_at",
        "source",
        "selected_exchange",
        "connector_backend",
        "support",
        "rate_limit",
        "network",
        "last_error",
        "attention"
      ]
    },
    {
      "name": "logs",
      "query_fields": [
        "limit"
      ],
      "request_fields": [
        "message",
        "source",
        "level"
      ],
      "response_fields": [
        "sequence_id",
        "level",
        "message",
        "source",
        "generated_at"
      ]
    },
    {
      "name": "terminal_run",
      "query_fields": [],
      "request_fields": [
        "command",
        "source"
      ],
      "response_fields": [
        "command",
        "exit_code",
        "output",
        "source",
        "generated_at"
      ]
    },
    {
      "name": "llm_providers",
      "query_fields": [],
      "request_fields": [],
      "response_fields": [
        "key",
        "label",
        "mode",
        "protocol",
        "default_base_url",
        "default_model",
        "api_key_env",
        "model_suggestions",
        "reasoning_efforts",
        "default_reasoning_effort"
      ]
    },
    {
      "name": "llm_config",
      "query_fields": [],
      "request_fields": [
        "config"
      ],
      "response_fields": [
        "enabled",
        "provider",
        "provider_label",
        "mode",
        "protocol",
        "model",
        "base_url",
        "api_key_env",
        "api_key_present",
        "allow_public_network",
        "use_for",
        "reasoning_effort"
      ]
    },
    {
      "name": "llm_prompt",
      "query_fields": [],
      "request_fields": [
        "prompt",
        "system_prompt",
        "dry_run",
        "source"
      ],
      "response_fields": [
        "provider",
        "model",
        "dry_run",
        "prompt",
        "system_prompt",
        "response",
        "source"
      ]
    },
    {
      "name": "llm_local_model_status",
      "query_fields": [
        "base_url",
        "model"
      ],
      "request_fields": [],
      "response_fields": [
        "model",
        "base_url",
        "server_kind",
        "installed",
        "can_download",
        "can_start",
        "storage_hint",
        "storage_paths",
        "estimated_size_label"
      ]
    },
    {
      "name": "llm_local_model_start",
      "query_fields": [],
      "request_fields": [
        "base_url",
        "model",
        "source"
      ],
      "response_fields": [
        "started",
        "server_kind",
        "executable",
        "error"
      ]
    },
    {
      "name": "llm_local_model_pull",
      "query_fields": [],
      "request_fields": [
        "base_url",
        "model",
        "source"
      ],
      "response_fields": [
        "ok",
        "action",
        "model",
        "status"
      ]
    },
    {
      "name": "llm_local_model_delete",
      "query_fields": [],
      "request_fields": [
        "base_url",
        "model",
        "source"
      ],
      "response_fields": [
        "ok",
        "action",
        "model",
        "status"
      ]
    },
    {
      "name": "stream_dashboard",
      "query_fields": [
        "log_limit",
        "incident_limit",
        "interval_ms",
        "max_events"
      ],
      "request_fields": [],
      "response_fields": [
        "event",
        "data"
      ]
    }
  ],
  "serviceRoutes": [
    {
      "methods": [
        "GET"
      ],
      "name": "runtime",
      "path": "/api/v1/runtime"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "dashboard",
      "path": "/api/v1/dashboard"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "status",
      "path": "/api/v1/status"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "execution",
      "path": "/api/v1/execution"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "backtest",
      "path": "/api/v1/backtest"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "config_summary",
      "path": "/api/v1/config-summary"
    },
    {
      "methods": [
        "GET",
        "PUT",
        "PATCH"
      ],
      "name": "config",
      "path": "/api/v1/config"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "config_persistence",
      "path": "/api/v1/config/persistence"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "config_save",
      "path": "/api/v1/config/save"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "config_load",
      "path": "/api/v1/config/load"
    },
    {
      "methods": [
        "PUT"
      ],
      "name": "runtime_state",
      "path": "/api/v1/runtime/state"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "operational_preflight",
      "path": "/api/v1/runtime/operational-preflight"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "control_start",
      "path": "/api/v1/control/start"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "control_stop",
      "path": "/api/v1/control/stop"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "control_start_failed",
      "path": "/api/v1/control/start-failed"
    },
    {
      "methods": [
        "GET",
        "PUT"
      ],
      "name": "connector_order_circuit_breaker",
      "path": "/api/v1/runtime/connector-order-circuit-breaker"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "connector_order_circuit_breaker_reset",
      "path": "/api/v1/runtime/connector-order-circuit-breaker/reset"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "connector_order_circuit_incidents",
      "path": "/api/v1/runtime/connector-order-circuit-breaker/incidents"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "backtest_run",
      "path": "/api/v1/backtest/run"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "backtest_stop",
      "path": "/api/v1/backtest/stop"
    },
    {
      "methods": [
        "GET",
        "PUT"
      ],
      "name": "account",
      "path": "/api/v1/account"
    },
    {
      "methods": [
        "GET",
        "PUT"
      ],
      "name": "portfolio",
      "path": "/api/v1/portfolio"
    },
    {
      "methods": [
        "GET",
        "PUT"
      ],
      "name": "exchange_connector",
      "path": "/api/v1/exchange/connector"
    },
    {
      "methods": [
        "GET",
        "POST"
      ],
      "name": "logs",
      "path": "/api/v1/logs"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "terminal_run",
      "path": "/api/v1/terminal/run"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "llm_providers",
      "path": "/api/v1/llm/providers"
    },
    {
      "methods": [
        "GET",
        "PATCH"
      ],
      "name": "llm_config",
      "path": "/api/v1/llm/config"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "llm_prompt",
      "path": "/api/v1/llm/prompt"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "llm_local_model_status",
      "path": "/api/v1/llm/local-model/status"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "llm_local_model_start",
      "path": "/api/v1/llm/local-model/start"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "llm_local_model_pull",
      "path": "/api/v1/llm/local-model/pull"
    },
    {
      "methods": [
        "POST"
      ],
      "name": "llm_local_model_delete",
      "path": "/api/v1/llm/local-model/delete"
    },
    {
      "methods": [
        "GET"
      ],
      "name": "stream_dashboard",
      "path": "/api/v1/stream/dashboard"
    }
  ],
  "sideOptions": [
    {
      "key": "BUY",
      "label": "Buy (Long)"
    },
    {
      "key": "SELL",
      "label": "Sell (Short)"
    },
    {
      "key": "BOTH",
      "label": "Both (Long/Short)"
    }
  ],
  "signalLogicOptions": [
    {
      "key": "AND",
      "label": "AND",
      "value": "AND"
    },
    {
      "key": "OR",
      "label": "OR",
      "value": "OR"
    },
    {
      "key": "SEPARATE",
      "label": "SEPARATE",
      "value": "SEPARATE"
    }
  ],
  "source": "Languages/Python",
  "stopLossModes": [
    {
      "key": "usdt",
      "label": "USDT Based Stop Loss"
    },
    {
      "key": "percent",
      "label": "Percentage Based Stop Loss"
    },
    {
      "key": "both",
      "label": "Both Stop Loss (USDT & Percentage)"
    }
  ],
  "stopLossScopes": [
    {
      "key": "per_trade",
      "label": "Per Trade Stop Loss"
    },
    {
      "key": "cumulative",
      "label": "Cumulative Stop Loss"
    },
    {
      "key": "entire_account",
      "label": "Entire Account Stop Loss"
    }
  ],
  "themeOptions": [
    {
      "key": "Light",
      "label": "Light",
      "value": "Light"
    },
    {
      "key": "Dark",
      "label": "Dark",
      "value": "Dark"
    },
    {
      "key": "Blue",
      "label": "Blue",
      "value": "Blue"
    },
    {
      "key": "Yellow",
      "label": "Yellow",
      "value": "Yellow"
    },
    {
      "key": "Green",
      "label": "Green",
      "value": "Green"
    },
    {
      "key": "Red",
      "label": "Red",
      "value": "Red"
    }
  ],
  "timeInForceOptions": [
    {
      "key": "GTC",
      "label": "GTC",
      "value": "GTC"
    },
    {
      "key": "IOC",
      "label": "IOC",
      "value": "IOC"
    },
    {
      "key": "FOK",
      "label": "FOK",
      "value": "FOK"
    },
    {
      "key": "GTD",
      "label": "GTD",
      "value": "GTD"
    }
  ],
  "tradingviewIntervalMap": {
    "10h": "600",
    "10m": "10",
    "11h": "660",
    "12h": "720",
    "15m": "15",
    "1d": "1D",
    "1h": "60",
    "1m": "1",
    "1mo": "1M",
    "1month": "1M",
    "1w": "1W",
    "1y": "12M",
    "20m": "20",
    "2d": "2D",
    "2h": "120",
    "2mo": "2M",
    "2months": "2M",
    "2w": "2W",
    "2y": "24M",
    "30m": "30",
    "3d": "3D",
    "3h": "180",
    "3m": "3",
    "3mo": "3M",
    "3months": "3M",
    "3w": "3W",
    "45m": "45",
    "4d": "4D",
    "4h": "240",
    "5d": "5D",
    "5h": "300",
    "5m": "5",
    "6d": "6D",
    "6h": "360",
    "6mo": "6M",
    "6months": "6M",
    "7h": "420",
    "8h": "480",
    "9h": "540"
  }
});
}());
