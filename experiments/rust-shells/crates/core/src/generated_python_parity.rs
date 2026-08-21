// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.

#[rustfmt::skip]
mod generated {
    pub const PYTHON_SOURCE: &str = "Languages/Python";
    pub const PYTHON_SOURCE_SCHEMA_VERSION: u32 = 1;
    pub const PYTHON_RISK_DEFAULTS_JSON: &str = "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}";
    pub const PYTHON_UI_DEFAULTS_JSON: &str = "{\"design\":\"Classic\",\"indicator_source\":\"Binance futures\",\"selected_exchange\":\"Binance\",\"theme\":\"Dark\"}";
    pub const PYTHON_DEFAULT_EXECUTION_JSON: &str = "{\"account_mode\":\"Classic Trading\",\"account_type\":\"Futures\",\"assets_mode\":\"Single-Asset\",\"backtest_symbol_interval_pairs\":[],\"connector_order_block_circuit_breaker_enabled\":true,\"connector_order_block_pause_threshold\":2,\"connector_order_block_window_seconds\":60.0,\"connector_order_circuit_incident_log_backup_count\":1,\"connector_order_circuit_incident_log_max_bytes\":2097152,\"connector_order_circuit_incident_log_path\":\"\",\"gtd_minutes\":30,\"intervals\":[\"1m\"],\"lead_trader_enabled\":false,\"lead_trader_profile\":null,\"leverage\":1,\"live_allow_auto_bump_to_min_order\":false,\"live_trading_acknowledgement\":\"\",\"live_trading_enabled\":false,\"live_trading_max_leverage\":20,\"live_trading_max_position_pct\":10.0,\"live_trading_max_session_orders\":100,\"lookback\":200,\"loop_interval_override\":\"1m\",\"margin_mode\":\"Isolated\",\"mode\":\"Demo/Testnet\",\"operational_account_snapshot_stale_seconds\":300.0,\"operational_connector_snapshot_stale_seconds\":120.0,\"operational_execution_heartbeat_stale_seconds\":10.0,\"operational_live_order_gate_enabled\":true,\"operational_live_start_gate_enabled\":true,\"operational_portfolio_snapshot_stale_seconds\":300.0,\"order_audit_backup_count\":1,\"order_audit_enabled\":true,\"order_audit_log_path\":\"\",\"order_audit_max_bytes\":10485760,\"order_type\":\"MARKET\",\"position_mode\":\"Hedge\",\"position_pct\":2.0,\"runtime_symbol_interval_pairs\":[],\"side\":\"BOTH\",\"stop_without_close\":false,\"symbols\":[\"BTCUSDT\"],\"tif\":\"GTC\"}";
    pub const PYTHON_DEFAULT_BACKTEST_JSON: &str = "{\"account_mode\":\"Classic Trading\",\"assets_mode\":\"Single-Asset\",\"capital\":1000.0,\"connector_backend\":\"binance-sdk-derivatives-trading-usds-futures\",\"end_date\":null,\"execution_backend\":\"local\",\"fee_bps\":5.0,\"indicators\":{\"adx\":{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"},\"ao\":{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34},\"aroon\":{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50},\"atr\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"},\"bb\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2},\"bbw\":{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2},\"cci\":{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100},\"chop\":{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8},\"cmf\":{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05},\"dmi\":{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0},\"donchian\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"ema\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"ichimoku\":{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52},\"keltner\":{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"kst\":{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15},\"ma\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"},\"macd\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"mfi\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80},\"natr\":{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0},\"obv\":{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"},\"ppo\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"psar\":{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"roc\":{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0},\"rsi\":{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70},\"rvol\":{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75},\"stoch_rsi\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"stochastic\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"supertrend\":{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"trix\":{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0},\"uo\":{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7},\"volume\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"},\"vwap\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"willr\":{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20}},\"intervals\":[\"1h\"],\"leverage\":20,\"logic\":\"AND\",\"margin_mode\":\"Isolated\",\"mdd_logic\":\"per_trade\",\"optimizer_combo_size\":2,\"optimizer_max_duration_seconds\":14400,\"optimizer_metric\":\"roi_percent\",\"optimizer_min_trades\":1,\"optimizer_mode\":\"current\",\"position_mode\":\"Hedge\",\"position_pct\":2.0,\"scan_auto_apply\":false,\"scan_mdd_limit\":10.0,\"scan_scope\":\"selected\",\"scan_top_n\":200,\"side\":\"BOTH\",\"slippage_bps\":2.0,\"start_date\":null,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"symbol_source\":\"Futures\",\"symbols\":[\"BTCUSDT\"],\"template\":{\"enabled\":false,\"name\":null}}";
    pub const PYTHON_OPTION_CATALOGS_JSON: &str = "{\"account_mode_options\":[\"Classic Trading\",\"Portfolio Margin\"],\"account_type_options\":[{\"key\":\"Spot\",\"label\":\"Spot\",\"value\":\"Spot\"},{\"key\":\"Futures\",\"label\":\"Futures\",\"value\":\"Futures\"}],\"assets_mode_options\":[{\"key\":\"Single-Asset\",\"label\":\"Single-Asset Mode\",\"value\":\"Single-Asset\"},{\"key\":\"Multi-Assets\",\"label\":\"Multi-Assets Mode\",\"value\":\"Multi-Assets\"}],\"backtest_execution_backend_options\":[{\"key\":\"local\",\"label\":\"local\",\"value\":\"local\"},{\"key\":\"service\",\"label\":\"service\",\"value\":\"service\"}],\"backtest_templates\":[{\"key\":\"volume_top50\",\"label\":\"First 50 Highest Volume\"},{\"key\":\"volume_last_week\",\"label\":\"Last 1 week \\u00b7 2% per trade \\u00b7 50 highest volume\"},{\"key\":\"top100_isolated_1pct_sl\",\"label\":\"Top 100, %2 per trade, isolated, %20 per trade SL\"}],\"chart_market_options\":[\"Futures\",\"Spot\"],\"chart_view_keys\":[\"tradingview\",\"original\",\"lightweight\"],\"chart_view_options\":[{\"key\":\"tradingview\",\"label\":\"TradingView\",\"value\":\"tradingview\"},{\"key\":\"original\",\"label\":\"Original\",\"value\":\"original\"},{\"key\":\"lightweight\",\"label\":\"TradingView Lightweight\",\"value\":\"lightweight\"}],\"code_language_options\":[{\"accent\":\"#3b82f6\",\"badge\":\"Recommended\",\"disabled\":false,\"key\":\"Python (PyQt)\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Fast to build - Huge ecosystem\",\"title\":\"Python\"},{\"accent\":\"#38bdf8\",\"badge\":\"Experiment\",\"disabled\":false,\"key\":\"C++ (Qt/C++23)\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Qt native desktop experiment\",\"title\":\"C++\"},{\"accent\":\"#fb923c\",\"badge\":\"Experiment\",\"disabled\":false,\"key\":\"Rust\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Service API client + guarded runtime (promotion-gated)\",\"title\":\"Rust\"}],\"config_mode_options\":[{\"key\":\"Live\",\"label\":\"Live\",\"value\":\"Live\"},{\"key\":\"Demo\",\"label\":\"Demo\",\"value\":\"Demo\"},{\"key\":\"Testnet\",\"label\":\"Testnet\",\"value\":\"Testnet\"}],\"connectors\":[{\"key\":\"binance-sdk-derivatives-trading-usds-futures\",\"label\":\"Binance SDK Derivatives Trading USD\\u24c8 Futures (Official Recommended)\"},{\"key\":\"binance-sdk-derivatives-trading-coin-futures\",\"label\":\"Binance SDK Derivatives Trading COIN-M Futures\"},{\"key\":\"binance-sdk-spot\",\"label\":\"Binance SDK Spot (Official Recommended)\"},{\"key\":\"binance-connector\",\"label\":\"Binance Connector Python\"},{\"key\":\"ccxt\",\"label\":\"CCXT (Unified)\"},{\"key\":\"oanda-rest\",\"label\":\"OANDA REST-v20\"},{\"key\":\"fxcmpy\",\"label\":\"FXCM fxcmpy\"},{\"key\":\"ig-rest\",\"label\":\"IG REST Trading API\"},{\"key\":\"citic-ctp\",\"label\":\"CITIC Futures CTP (Local/Remote TCP Front)\"},{\"key\":\"metatrader4-bridge\",\"label\":\"MetaTrader 4 Bridge (Local/Remote Expert Advisor)\"},{\"key\":\"metatrader5\",\"label\":\"MetaTrader 5 (Official Python Integration)\"},{\"key\":\"trading212-public-api\",\"label\":\"Trading 212 Public API (Invest/Stocks ISA equities)\"},{\"key\":\"moomoo-opend\",\"label\":\"moomoo OpenD (Local/Remote Gateway)\"},{\"key\":\"python-binance\",\"label\":\"python-binance (Community)\"}],\"dashboard_loop_choices\":[{\"key\":\"30s\",\"label\":\"30 seconds\",\"value\":\"30s\"},{\"key\":\"45s\",\"label\":\"45 seconds\",\"value\":\"45s\"},{\"key\":\"1m\",\"label\":\"1 minute\",\"value\":\"1m\"},{\"key\":\"2m\",\"label\":\"2 minutes\",\"value\":\"2m\"},{\"key\":\"3m\",\"label\":\"3 minutes\",\"value\":\"3m\"},{\"key\":\"5m\",\"label\":\"5 minutes\",\"value\":\"5m\"},{\"key\":\"10m\",\"label\":\"10 minutes\",\"value\":\"10m\"},{\"key\":\"30m\",\"label\":\"30 minutes\",\"value\":\"30m\"},{\"key\":\"1h\",\"label\":\"1 hour\",\"value\":\"1h\"},{\"key\":\"2h\",\"label\":\"2 hours\",\"value\":\"2h\"}],\"dashboard_strategy_templates\":[{\"key\":\"\",\"label\":\"No Template\"},{\"key\":\"top10\",\"label\":\"Top 10 %2 per trade 1x Isolated\"},{\"key\":\"top50\",\"label\":\"Top 50 %2 per trade 1x\"},{\"key\":\"top100\",\"label\":\"Top 100 %1 per trade 1x\"}],\"default_backtest_intervals\":[\"1h\"],\"default_backtest_symbols\":[\"BTCUSDT\"],\"default_chart_symbols\":[\"BTCUSDT\",\"ETHUSDT\",\"BNBUSDT\",\"SOLUSDT\",\"XRPUSDT\",\"ADAUSDT\",\"DOGEUSDT\",\"AVAXUSDT\",\"LINKUSDT\",\"TRXUSDT\"],\"default_execution_intervals\":[\"1m\"],\"default_execution_symbols\":[\"BTCUSDT\"],\"design_options\":[{\"key\":\"Classic\",\"label\":\"Classic\",\"value\":\"Classic\"},{\"key\":\"Workstation\",\"label\":\"Workstation\",\"value\":\"Workstation\"}],\"exchange_options\":[{\"badge\":\"\",\"disabled\":false,\"key\":\"Binance\",\"label\":\"Binance\",\"title\":\"Binance\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Bybit\",\"label\":\"Bybit (ccxt order routing)\",\"title\":\"Bybit\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"OKX\",\"label\":\"OKX (ccxt order routing)\",\"title\":\"OKX\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Gate\",\"label\":\"Gate (ccxt order routing)\",\"title\":\"Gate\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Bitget\",\"label\":\"Bitget (ccxt order routing)\",\"title\":\"Bitget\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"MEXC\",\"label\":\"MEXC (ccxt order routing)\",\"title\":\"MEXC\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"KuCoin\",\"label\":\"KuCoin (ccxt order routing)\",\"title\":\"KuCoin\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"HTX\",\"label\":\"HTX (ccxt order routing)\",\"title\":\"HTX\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Crypto.com Exchange\",\"label\":\"Crypto.com Exchange (ccxt order routing)\",\"title\":\"Crypto.com Exchange\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Kraken\",\"label\":\"Kraken (ccxt order routing)\",\"title\":\"Kraken\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Bitfinex\",\"label\":\"Bitfinex (ccxt order routing)\",\"title\":\"Bitfinex\"}],\"indicator_ma_type_options\":[{\"key\":\"SMA\",\"label\":\"SMA\",\"value\":\"SMA\"},{\"key\":\"EMA\",\"label\":\"EMA\",\"value\":\"EMA\"}],\"indicator_source_options\":[{\"key\":\"Binance spot\",\"label\":\"Binance spot\",\"value\":\"Binance spot\"},{\"key\":\"Binance futures\",\"label\":\"Binance futures\",\"value\":\"Binance futures\"}],\"indicators\":[{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"},\"default_enabled\":false,\"display_name\":\"Moving Average (MA)\",\"key\":\"ma\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"type\":\"SMA\"},\"runtime_output_keys\":[\"ma\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"default_enabled\":false,\"display_name\":\"Donchian Channels (DC)\",\"key\":\"donchian\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"donchian_high\",\"donchian_low\",\"donchian\"]},{\"backtest_config\":{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"Parabolic SAR (PSAR)\",\"key\":\"psar\",\"runtime_config\":{\"af\":0.02,\"buy_value\":null,\"enabled\":false,\"max_af\":0.2,\"sell_value\":null},\"runtime_output_keys\":[\"psar\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2},\"default_enabled\":false,\"display_name\":\"Bollinger Bands (BB)\",\"key\":\"bb\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2},\"runtime_output_keys\":[\"bb_upper\",\"bb_mid\",\"bb_lower\"]},{\"backtest_config\":{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2},\"default_enabled\":false,\"display_name\":\"Bollinger Band Width (BBW)\",\"key\":\"bbw\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2},\"runtime_output_keys\":[\"bbw\"]},{\"backtest_config\":{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"default_enabled\":false,\"display_name\":\"Keltner Channels (KC)\",\"key\":\"keltner\",\"runtime_config\":{\"atr_length\":10,\"buy_value\":null,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":null},\"runtime_output_keys\":[\"keltner_upper\",\"keltner_mid\",\"keltner_lower\"]},{\"backtest_config\":{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52},\"default_enabled\":false,\"display_name\":\"Ichimoku Cloud (IC)\",\"key\":\"ichimoku\",\"runtime_config\":{\"base_length\":26,\"buy_value\":null,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":null,\"span_b_length\":52},\"runtime_output_keys\":[\"ichimoku_tenkan\",\"ichimoku_kijun\",\"ichimoku_span_a\",\"ichimoku_span_b\",\"ichimoku_chikou\",\"ichimoku\"]},{\"backtest_config\":{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70},\"default_enabled\":true,\"display_name\":\"Relative Strength Index (RSI)\",\"key\":\"rsi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":true,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"rsi\"]},{\"backtest_config\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"},\"default_enabled\":false,\"display_name\":\"Volume\",\"key\":\"volume\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"sell_value\":null},\"runtime_output_keys\":[\"volume\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"},\"default_enabled\":false,\"display_name\":\"On-Balance Volume (OBV)\",\"key\":\"obv\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"sell_value\":null},\"runtime_output_keys\":[\"obv\"]},{\"backtest_config\":{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75},\"default_enabled\":false,\"display_name\":\"Relative Volume (RVOL)\",\"key\":\"rvol\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"rvol\"]},{\"backtest_config\":{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05},\"default_enabled\":false,\"display_name\":\"Chaikin Money Flow (CMF)\",\"key\":\"cmf\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"cmf\"]},{\"backtest_config\":{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100},\"default_enabled\":false,\"display_name\":\"Commodity Channel Index (CCI)\",\"key\":\"cci\",\"runtime_config\":{\"buy_value\":null,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"cci\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0},\"default_enabled\":false,\"display_name\":\"Rate of Change (ROC)\",\"key\":\"roc\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":12,\"sell_value\":null},\"runtime_output_keys\":[\"roc\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0},\"default_enabled\":false,\"display_name\":\"Triple Exponential Average (TRIX)\",\"key\":\"trix\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":15,\"sell_value\":null},\"runtime_output_keys\":[\"trix\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"default_enabled\":false,\"display_name\":\"Percentage Price Oscillator (PPO)\",\"key\":\"ppo\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26},\"runtime_output_keys\":[\"ppo\",\"ppo_signal\",\"ppo_hist\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34},\"default_enabled\":false,\"display_name\":\"Awesome Oscillator (AO)\",\"key\":\"ao\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"fast\":5,\"sell_value\":null,\"slow\":34},\"runtime_output_keys\":[\"ao\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15},\"default_enabled\":false,\"display_name\":\"Know Sure Thing (KST)\",\"key\":\"kst\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":null,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15},\"runtime_output_keys\":[\"kst\",\"kst_signal\",\"kst_hist\"]},{\"backtest_config\":{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50},\"default_enabled\":false,\"display_name\":\"Aroon Oscillator (AROON)\",\"key\":\"aroon\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":25,\"sell_value\":null},\"runtime_output_keys\":[\"aroon_up\",\"aroon_down\",\"aroon\"]},{\"backtest_config\":{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8},\"default_enabled\":false,\"display_name\":\"Choppiness Index (CHOP)\",\"key\":\"chop\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"chop\"]},{\"backtest_config\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"},\"default_enabled\":false,\"display_name\":\"Average True Range (ATR)\",\"key\":\"atr\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"atr\"]},{\"backtest_config\":{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0},\"default_enabled\":false,\"display_name\":\"Normalized Average True Range (NATR)\",\"key\":\"natr\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"natr\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"Volume Weighted Average Price (VWAP)\",\"key\":\"vwap\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"vwap\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80},\"default_enabled\":false,\"display_name\":\"Money Flow Index (MFI)\",\"key\":\"mfi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"mfi\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"default_enabled\":false,\"display_name\":\"Stochastic RSI (SRSI)\",\"key\":\"stoch_rsi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3},\"runtime_output_keys\":[\"stoch_rsi\",\"stoch_rsi_k\",\"stoch_rsi_d\"]},{\"backtest_config\":{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20},\"default_enabled\":false,\"display_name\":\"Williams %R\",\"key\":\"willr\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"willr\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"default_enabled\":false,\"display_name\":\"Moving Average Convergence/Divergence (MACD)\",\"key\":\"macd\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26},\"runtime_output_keys\":[\"macd_line\",\"macd_signal\"]},{\"backtest_config\":{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7},\"default_enabled\":false,\"display_name\":\"Ultimate Oscillator (UO)\",\"key\":\"uo\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":null,\"short\":7},\"runtime_output_keys\":[\"uo\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"},\"default_enabled\":false,\"display_name\":\"Average Directional Index (ADX)\",\"key\":\"adx\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"adx\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0},\"default_enabled\":false,\"display_name\":\"Directional Movement Index (DMI)\",\"key\":\"dmi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"dmi_plus\",\"dmi_minus\",\"dmi\"]},{\"backtest_config\":{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"SuperTrend (ST)\",\"key\":\"supertrend\",\"runtime_config\":{\"atr_period\":10,\"buy_value\":null,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":null},\"runtime_output_keys\":[\"supertrend\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"Exponential Moving Average (EMA)\",\"key\":\"ema\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"ema\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"default_enabled\":false,\"display_name\":\"Stochastic Oscillator\",\"key\":\"stochastic\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3},\"runtime_output_keys\":[\"stochastic\",\"stochastic_k\",\"stochastic_d\"]}],\"intervals\":[\"1m\",\"3m\",\"5m\",\"10m\",\"15m\",\"20m\",\"30m\",\"1h\",\"2h\",\"3h\",\"4h\",\"5h\",\"6h\",\"7h\",\"8h\",\"9h\",\"10h\",\"11h\",\"12h\",\"1d\",\"2d\",\"3d\",\"4d\",\"5d\",\"6d\",\"1w\",\"2w\",\"3w\",\"1month\",\"2months\",\"3months\",\"6months\",\"1mo\",\"2mo\",\"3mo\",\"6mo\",\"1y\",\"2y\"],\"lead_trader_options\":[{\"key\":\"futures_public\",\"label\":\"Futures Public Lead Trader\",\"value\":\"futures_public\"},{\"key\":\"futures_private\",\"label\":\"Futures Private Lead Trader\",\"value\":\"futures_private\"},{\"key\":\"spot_public\",\"label\":\"Spot Public Lead Trader\",\"value\":\"spot_public\"},{\"key\":\"spot_private\",\"label\":\"Spot Private Lead Trader\",\"value\":\"spot_private\"}],\"llm_reasoning_effort_options\":[{\"key\":\"default\",\"label\":\"default\",\"value\":\"default\"},{\"key\":\"disabled\",\"label\":\"disabled\",\"value\":\"disabled\"},{\"key\":\"enabled\",\"label\":\"enabled\",\"value\":\"enabled\"},{\"key\":\"xhigh\",\"label\":\"xhigh\",\"value\":\"xhigh\"},{\"key\":\"high\",\"label\":\"high\",\"value\":\"high\"},{\"key\":\"low\",\"label\":\"low\",\"value\":\"low\"},{\"key\":\"max\",\"label\":\"max\",\"value\":\"max\"},{\"key\":\"medium\",\"label\":\"medium\",\"value\":\"medium\"},{\"key\":\"minimal\",\"label\":\"minimal\",\"value\":\"minimal\"},{\"key\":\"none\",\"label\":\"none\",\"value\":\"none\"}],\"llm_use_for_options\":[{\"key\":\"advisory\",\"label\":\"Advisory\",\"value\":\"advisory\"},{\"key\":\"signal_confirmation\",\"label\":\"Signal confirmation\",\"value\":\"signal_confirmation\"},{\"key\":\"risk_review\",\"label\":\"Risk review\",\"value\":\"risk_review\"},{\"key\":\"backtest_explanation\",\"label\":\"Backtest explanation\",\"value\":\"backtest_explanation\"}],\"margin_mode_options\":[{\"key\":\"Isolated\",\"label\":\"Isolated\",\"value\":\"Isolated\"},{\"key\":\"Cross\",\"label\":\"Cross\",\"value\":\"Cross\"}],\"mdd_logic_options\":[{\"key\":\"per_trade\",\"label\":\"Per Trade MDD\"},{\"key\":\"cumulative\",\"label\":\"Cumulative MDD\"},{\"key\":\"entire_account\",\"label\":\"Entire Account MDD\"}],\"optimizer_metric_options\":[{\"key\":\"roi_percent\",\"label\":\"roi_percent\",\"value\":\"roi_percent\"},{\"key\":\"roi_percent_mdd\",\"label\":\"roi_percent_mdd\",\"value\":\"roi_percent_mdd\"},{\"key\":\"roi_drawdown\",\"label\":\"roi_drawdown\",\"value\":\"roi_drawdown\"},{\"key\":\"roi_value\",\"label\":\"roi_value\",\"value\":\"roi_value\"}],\"optimizer_mode_options\":[{\"key\":\"current\",\"label\":\"current\",\"value\":\"current\"},{\"key\":\"single\",\"label\":\"single\",\"value\":\"single\"},{\"key\":\"pairs\",\"label\":\"pairs\",\"value\":\"pairs\"},{\"key\":\"combinations\",\"label\":\"combinations\",\"value\":\"combinations\"}],\"order_type_options\":[{\"key\":\"MARKET\",\"label\":\"MARKET\",\"value\":\"MARKET\"},{\"key\":\"LIMIT\",\"label\":\"LIMIT\",\"value\":\"LIMIT\"}],\"position_mode_options\":[{\"key\":\"Hedge\",\"label\":\"Hedge\",\"value\":\"Hedge\"},{\"key\":\"One-way\",\"label\":\"One-way\",\"value\":\"One-way\"}],\"position_pct_units_options\":[{\"key\":\"percent\",\"label\":\"percent\",\"value\":\"percent\"},{\"key\":\"fraction\",\"label\":\"fraction\",\"value\":\"fraction\"}],\"positions_view_options\":[{\"key\":\"cumulative\",\"label\":\"Cumulative View\",\"value\":\"cumulative\"},{\"key\":\"per_trade\",\"label\":\"Per Trade View\",\"value\":\"per_trade\"}],\"rust_environment_dependencies\":[{\"key\":\"rustc\",\"kind\":\"rust_rustc\",\"label\":\"rustc\",\"latest\":\"Install rustup\",\"path\":\"\",\"usage\":\"\"},{\"key\":\"cargo\",\"kind\":\"rust_cargo\",\"label\":\"cargo\",\"latest\":\"Install rustup\",\"path\":\"\",\"usage\":\"\"},{\"key\":\"experiments/rust-shells/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"Trading Bot Rust workspace\",\"latest\":\"\",\"path\":\"experiments/rust-shells/Cargo.toml\",\"usage\":\"Active\"},{\"key\":\"experiments/rust-shells/crates/core/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"trading-bot-core\",\"latest\":\"\",\"path\":\"experiments/rust-shells/crates/core/Cargo.toml\",\"usage\":\"Active\"},{\"key\":\"experiments/rust-shells/crates/contracts/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"trading-bot-contracts\",\"latest\":\"\",\"path\":\"experiments/rust-shells/crates/contracts/Cargo.toml\",\"usage\":\"Active\"},{\"key\":\"experiments/rust-shells/apps/tauri-desktop/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"Tauri (Primary)\",\"latest\":\"\",\"path\":\"experiments/rust-shells/apps/tauri-desktop/Cargo.toml\",\"usage\":\"Active\"}],\"rust_framework_options\":[{\"accent\":\"#f59e0b\",\"badge\":\"Primary\",\"disabled\":false,\"key\":\"Tauri\",\"launch_note\":\"Tauri can manage/connect to the local Python Service API, but Python still owns strategy, risk, account, order, and exchange execution.\",\"operational\":true,\"operational_status\":\"Interactive Service API client\",\"subtitle\":\"Operational Service API client\",\"title\":\"Tauri\"}],\"scan_scope_options\":[{\"key\":\"selected\",\"label\":\"selected\",\"value\":\"selected\"},{\"key\":\"top_n\",\"label\":\"top_n\",\"value\":\"top_n\"},{\"key\":\"all_loaded\",\"label\":\"all_loaded\",\"value\":\"all_loaded\"}],\"side_options\":[{\"key\":\"BUY\",\"label\":\"Buy (Long)\"},{\"key\":\"SELL\",\"label\":\"Sell (Short)\"},{\"key\":\"BOTH\",\"label\":\"Both (Long/Short)\"}],\"signal_logic_options\":[{\"key\":\"AND\",\"label\":\"AND\",\"value\":\"AND\"},{\"key\":\"OR\",\"label\":\"OR\",\"value\":\"OR\"},{\"key\":\"SEPARATE\",\"label\":\"SEPARATE\",\"value\":\"SEPARATE\"}],\"starter_market_options\":[{\"accent\":\"#34d399\",\"badge\":\"\",\"disabled\":false,\"key\":\"crypto\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Binance, Bybit, KuCoin\",\"title\":\"Crypto Exchange\"},{\"accent\":\"#93c5fd\",\"badge\":\"Evidence required\",\"disabled\":false,\"key\":\"forex\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"REST, MT4 bridge, MetaTrader 5, and scoped provider APIs\",\"title\":\"Forex Exchange\"}],\"stop_loss_modes\":[{\"key\":\"usdt\",\"label\":\"USDT Based Stop Loss\"},{\"key\":\"percent\",\"label\":\"Percentage Based Stop Loss\"},{\"key\":\"both\",\"label\":\"Both Stop Loss (USDT & Percentage)\"}],\"stop_loss_scopes\":[{\"key\":\"per_trade\",\"label\":\"Per Trade Stop Loss\"},{\"key\":\"cumulative\",\"label\":\"Cumulative Stop Loss\"},{\"key\":\"entire_account\",\"label\":\"Entire Account Stop Loss\"}],\"theme_options\":[{\"key\":\"Light\",\"label\":\"Light\",\"value\":\"Light\"},{\"key\":\"Dark\",\"label\":\"Dark\",\"value\":\"Dark\"},{\"key\":\"Blue\",\"label\":\"Blue\",\"value\":\"Blue\"},{\"key\":\"Yellow\",\"label\":\"Yellow\",\"value\":\"Yellow\"},{\"key\":\"Green\",\"label\":\"Green\",\"value\":\"Green\"},{\"key\":\"Red\",\"label\":\"Red\",\"value\":\"Red\"}],\"time_in_force_options\":[{\"key\":\"GTC\",\"label\":\"GTC\",\"value\":\"GTC\"},{\"key\":\"IOC\",\"label\":\"IOC\",\"value\":\"IOC\"},{\"key\":\"FOK\",\"label\":\"FOK\",\"value\":\"FOK\"},{\"key\":\"GTD\",\"label\":\"GTD\",\"value\":\"GTD\"}],\"tradingview_interval_map\":{\"10h\":\"600\",\"10m\":\"10\",\"11h\":\"660\",\"12h\":\"720\",\"15m\":\"15\",\"1d\":\"1D\",\"1h\":\"60\",\"1m\":\"1\",\"1mo\":\"1M\",\"1month\":\"1M\",\"1w\":\"1W\",\"1y\":\"12M\",\"20m\":\"20\",\"2d\":\"2D\",\"2h\":\"120\",\"2mo\":\"2M\",\"2months\":\"2M\",\"2w\":\"2W\",\"2y\":\"24M\",\"30m\":\"30\",\"3d\":\"3D\",\"3h\":\"180\",\"3m\":\"3\",\"3mo\":\"3M\",\"3months\":\"3M\",\"3w\":\"3W\",\"45m\":\"45\",\"4d\":\"4D\",\"4h\":\"240\",\"5d\":\"5D\",\"5h\":\"300\",\"5m\":\"5\",\"6d\":\"6D\",\"6h\":\"360\",\"6mo\":\"6M\",\"6months\":\"6M\",\"7h\":\"420\",\"8h\":\"480\",\"9h\":\"540\"}}";

    pub struct PythonRuntimeConfigReferenceCase {
    pub name: &'static str,
    pub input_json: &'static str,
    pub expected_json: &'static str,
    pub valid: bool,
    pub expected_error: &'static str,
}

pub const PYTHON_RUNTIME_CONFIG_REFERENCE_CASES: &[PythonRuntimeConfigReferenceCase] = &[
    PythonRuntimeConfigReferenceCase {
        name: "alias-rich-runtime",
        input_json: "{\"account_mode\":\"portfolio margin\",\"account_type\":\"futures\",\"assets_mode\":\"multi-asset\",\"backtest\":{\"account_mode\":\"classic trading\",\"assets_mode\":\"single-asset mode\",\"capital\":\"1000\",\"connector_backend\":\"binance-sdk-spot\",\"end_date\":\"2026-02-01\",\"execution_backend\":\"desktop-local\",\"fee_bps\":5.0,\"indicators\":{},\"intervals\":[\"15 minutes\",\"1M\"],\"leverage\":20,\"logic\":\"or\",\"margin_mode\":\"isolated\",\"mdd_logic\":\"per_trade\",\"optimizer_combo_size\":2,\"optimizer_max_duration_seconds\":7200,\"optimizer_metric\":\"roi-percent-mdd\",\"optimizer_min_trades\":1,\"optimizer_mode\":\"pairs\",\"position_mode\":\"hedge\",\"position_pct\":\"2.0\",\"scan_auto_apply\":\"false\",\"scan_mdd_limit\":20,\"scan_scope\":\"top_n\",\"scan_top_n\":200,\"side\":\"both\",\"slippage_bps\":2.0,\"start_date\":\"2026-01-01\",\"stop_loss\":{\"mode\":\"percent\",\"scope\":\"entire_account\"},\"symbol_source\":\"futures\",\"symbols\":[\"btcusdt\",\"BTCUSDT\"],\"template\":{}},\"backtest_symbol_interval_pairs\":null,\"chart\":{\"auto_follow\":\"yes\",\"interval\":\"1M\",\"market\":\"spot\",\"symbol\":\"ethusdt\",\"view_mode\":\"TradingView Lightweight\"},\"connector_backend\":\"CCXT (Unified)\",\"design\":\"workstation\",\"indicator_source\":\"binance futures\",\"intervals\":[\"1M\",\"2 hours\"],\"live_allow_auto_bump_to_min_order\":\"yes\",\"live_trading_enabled\":\"false\",\"live_trading_max_leverage\":20,\"live_trading_max_position_pct\":\"4.0\",\"live_trading_max_session_orders\":\"25\",\"llm_allow_public_network\":\"false\",\"llm_base_url\":\"http://127.0.0.1:11434/v1\",\"llm_enabled\":\"true\",\"llm_model\":\"local-model\",\"llm_provider\":\"chatgpt\",\"llm_reasoning_effort\":\"extra-high\",\"llm_use_for\":\"risk_review\",\"loop_interval_override\":\"1 hour\",\"margin_mode\":\"cross\",\"mode\":\"live\",\"order_audit_enabled\":\"no\",\"order_type\":\"limit\",\"position_mode\":\"oneway\",\"position_pct\":\"2.5\",\"runtime_symbol_interval_pairs\":[{\"interval\":\"15 minutes\",\"strategy_controls\":{\"leverage\":20,\"loop_interval_override\":\"1 hour\",\"side\":\"buy\",\"stop_loss\":{\"scope\":\"bad-scope\"}},\"symbol\":\"btcusdt\"}],\"selected_exchange\":\"kucoin\",\"side\":\"sell\",\"stop_loss\":{\"mode\":\"percent\",\"scope\":\"entire_account\"},\"symbols\":[\"ethusdt\",\"ETHUSDT\"],\"theme\":\"green\",\"tif\":\"ioc\"}",
        expected_json: "{\"account_mode\":\"Portfolio Margin\",\"account_type\":\"Futures\",\"assets_mode\":\"Multi-Assets\",\"backtest\":{\"account_mode\":\"Classic Trading\",\"assets_mode\":\"Single-Asset\",\"capital\":1000.0,\"connector_backend\":\"binance-sdk-spot\",\"end_date\":\"2026-02-01\",\"execution_backend\":\"local\",\"fee_bps\":5.0,\"indicators\":{},\"intervals\":[\"15m\",\"1mo\"],\"leverage\":20,\"logic\":\"OR\",\"margin_mode\":\"Isolated\",\"mdd_logic\":\"per_trade\",\"optimizer_combo_size\":2,\"optimizer_max_duration_seconds\":7200,\"optimizer_metric\":\"roi_percent_mdd\",\"optimizer_min_trades\":1,\"optimizer_mode\":\"pairs\",\"position_mode\":\"Hedge\",\"position_pct\":2.0,\"scan_auto_apply\":false,\"scan_mdd_limit\":20.0,\"scan_scope\":\"top_n\",\"scan_top_n\":200,\"side\":\"BOTH\",\"slippage_bps\":2.0,\"start_date\":\"2026-01-01\",\"stop_loss\":{\"enabled\":false,\"mode\":\"percent\",\"percent\":0.0,\"scope\":\"entire_account\",\"usdt\":0.0},\"symbol_source\":\"futures\",\"symbols\":[\"BTCUSDT\"],\"template\":{}},\"backtest_symbol_interval_pairs\":[],\"chart\":{\"auto_follow\":true,\"interval\":\"1mo\",\"market\":\"Spot\",\"symbol\":\"ETHUSDT\",\"view_mode\":\"lightweight\"},\"connector_backend\":\"CCXT (Unified)\",\"design\":\"workstation\",\"indicator_source\":\"binance futures\",\"intervals\":[\"1mo\",\"2h\"],\"live_allow_auto_bump_to_min_order\":true,\"live_trading_enabled\":false,\"live_trading_max_leverage\":20,\"live_trading_max_position_pct\":4.0,\"live_trading_max_session_orders\":25,\"llm_allow_public_network\":false,\"llm_base_url\":\"http://127.0.0.1:11434/v1\",\"llm_enabled\":true,\"llm_model\":\"local-model\",\"llm_provider\":\"openai\",\"llm_reasoning_effort\":\"xhigh\",\"llm_use_for\":\"risk_review\",\"loop_interval_override\":\"1h\",\"margin_mode\":\"Cross\",\"mode\":\"live\",\"order_audit_enabled\":false,\"order_type\":\"LIMIT\",\"position_mode\":\"One-way\",\"position_pct\":2.5,\"runtime_symbol_interval_pairs\":[{\"interval\":\"15m\",\"strategy_controls\":{\"leverage\":20,\"loop_interval_override\":\"1h\",\"side\":\"BUY\",\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}},\"symbol\":\"BTCUSDT\"}],\"selected_exchange\":\"kucoin\",\"side\":\"SELL\",\"stop_loss\":{\"enabled\":false,\"mode\":\"percent\",\"percent\":0.0,\"scope\":\"entire_account\",\"usdt\":0.0},\"symbols\":[\"ETHUSDT\"],\"theme\":\"green\",\"tif\":\"IOC\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "canonical-runtime",
        input_json: "{\"chart\":{\"auto_follow\":true,\"interval\":\"15m\",\"market\":\"Spot\",\"symbol\":\"BTCUSDT\",\"view_mode\":\"lightweight\"},\"intervals\":[\"15m\"],\"loop_interval_override\":\"5m\",\"mode\":\"paper\",\"order_type\":\"MARKET\",\"position_pct\":1.5,\"side\":\"BUY\",\"symbols\":[\"BTCUSDT\"],\"tif\":\"GTC\"}",
        expected_json: "{\"chart\":{\"auto_follow\":true,\"interval\":\"15m\",\"market\":\"Spot\",\"symbol\":\"BTCUSDT\",\"view_mode\":\"lightweight\"},\"intervals\":[\"15m\"],\"loop_interval_override\":\"5m\",\"mode\":\"paper\",\"order_type\":\"MARKET\",\"position_pct\":1.5,\"side\":\"BUY\",\"symbols\":[\"BTCUSDT\"],\"tif\":\"GTC\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-unknown-key",
        input_json: "{\"unknown_key\":true}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: unknown_key: is not a supported config key",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-mode-empty",
        input_json: "{\"mode\":\"\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: mode: must be a non-empty text value",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-account-type",
        input_json: "{\"account_type\":\"margin\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: account_type: must be one of: Futures, Spot",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-symbol-type",
        input_json: "{\"symbols\":42}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: symbols: must be a list of symbols",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-symbol-content",
        input_json: "{\"symbols\":[\"BTC USDT\"]}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: symbols: contains an invalid symbol; symbols: must contain at least one symbol",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-interval-type",
        input_json: "{\"intervals\":42}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: intervals: must be a list of intervals",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-interval-content",
        input_json: "{\"intervals\":[\"0m\"]}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: intervals: contains an invalid interval; intervals: must contain at least one interval",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-lookback-type",
        input_json: "{\"lookback\":\"bars\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: lookback: must be an integer",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-lookback-range",
        input_json: "{\"lookback\":0}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: lookback: must be between 1 and 1000000",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-position-pct-exclusive",
        input_json: "{\"position_pct\":0}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: position_pct: must be > 0 and <= 100",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-position-pct-range",
        input_json: "{\"position_pct\":101}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: position_pct: must be > 0 and <= 100",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-bool",
        input_json: "{\"live_trading_enabled\":\"maybe\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: live_trading_enabled: must be a boolean",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-loop-interval",
        input_json: "{\"loop_interval_override\":\"fast\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: loop_interval_override: must be a valid interval",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-pair-type",
        input_json: "{\"runtime_symbol_interval_pairs\":{}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: runtime_symbol_interval_pairs: must be a list of symbol/interval objects",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-pair-entry",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"symbol\":\"BTC USDT\"}]}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: runtime_symbol_interval_pairs[0].symbol: must be a non-empty symbol",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-pair-controls",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"leverage\":0},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: runtime_symbol_interval_pairs[0].strategy_controls.leverage: must be between 1 and 125",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-stop-loss-type",
        input_json: "{\"stop_loss\":\"no\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: stop_loss: must be an object",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-chart-type",
        input_json: "{\"chart\":\"no\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: chart: must be an object",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-chart-key",
        input_json: "{\"chart\":{\"unknown\":true}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: chart.unknown: is not a supported config key",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-chart-market",
        input_json: "{\"chart\":{\"market\":\"margin\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: chart.market: must be one of: Futures, Spot",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-chart-view",
        input_json: "{\"chart\":{\"view_mode\":\"external\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: chart.view_mode: must be one of: lightweight, original, tradingview",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-chart-symbol",
        input_json: "{\"chart\":{\"symbol\":\"BTC USDT\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: chart.symbol: must be a non-empty symbol",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-chart-interval",
        input_json: "{\"chart\":{\"interval\":\"0m\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: chart.interval: must be a valid interval",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-type",
        input_json: "{\"backtest\":\"no\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest: must be an object",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-key",
        input_json: "{\"backtest\":{\"unknown\":true}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest.unknown: is not a supported config key",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-capital",
        input_json: "{\"backtest\":{\"capital\":0}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest.capital: must be > 0 and <= 1e+12",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-date",
        input_json: "{\"backtest\":{\"start_date\":\"not-date\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest.start_date: must be an ISO date or datetime",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-choice",
        input_json: "{\"backtest\":{\"logic\":\"xor\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest.logic: must be one of: AND, OR, SEPARATE",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-mapping",
        input_json: "{\"backtest\":{\"template\":[]}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest.template: must be an object",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-backtest-stop-loss",
        input_json: "{\"backtest\":{\"stop_loss\":\"bad\"}}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: backtest.stop_loss: must be an object",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-risk-int",
        input_json: "{\"indicator_flip_confirmation_bars\":0}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: indicator_flip_confirmation_bars: must be between 1 and 1000000",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-risk-float",
        input_json: "{\"max_auto_bump_percent\":101}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: max_auto_bump_percent: must be >= 0 and <= 100",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-llm-provider",
        input_json: "{\"llm_provider\":\"ghost-ai\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: llm_provider: must be one of: anthropic, deepseek, gemini, grok, llamacpp, lmstudio, local, mistral, moonshot, ollama, open-source, openai, qwen, tgi, vllm",
    },
    PythonRuntimeConfigReferenceCase {
        name: "invalid-text-control",
        input_json: "{\"connector_backend\":\"ok\\u0001\"}",
        expected_json: "{}",
        valid: false,
        expected_error: "Invalid config: connector_backend: must be a non-empty text value",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-account_type-spot",
        input_json: "{\"account_type\":\"spot\"}",
        expected_json: "{\"account_type\":\"Spot\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-account_type-futures",
        input_json: "{\"account_type\":\"futures\"}",
        expected_json: "{\"account_type\":\"Futures\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-margin_mode-isolated",
        input_json: "{\"margin_mode\":\"isolated\"}",
        expected_json: "{\"margin_mode\":\"Isolated\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-margin_mode-cross",
        input_json: "{\"margin_mode\":\"cross\"}",
        expected_json: "{\"margin_mode\":\"Cross\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_mode-hedge",
        input_json: "{\"position_mode\":\"hedge\"}",
        expected_json: "{\"position_mode\":\"Hedge\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_mode-one-way",
        input_json: "{\"position_mode\":\"one-way\"}",
        expected_json: "{\"position_mode\":\"One-way\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_mode-oneway",
        input_json: "{\"position_mode\":\"oneway\"}",
        expected_json: "{\"position_mode\":\"One-way\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-assets_mode-single-asset",
        input_json: "{\"assets_mode\":\"single-asset\"}",
        expected_json: "{\"assets_mode\":\"Single-Asset\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-assets_mode-single-asset mode",
        input_json: "{\"assets_mode\":\"single-asset mode\"}",
        expected_json: "{\"assets_mode\":\"Single-Asset\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-assets_mode-multi-assets",
        input_json: "{\"assets_mode\":\"multi-assets\"}",
        expected_json: "{\"assets_mode\":\"Multi-Assets\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-assets_mode-multi-asset",
        input_json: "{\"assets_mode\":\"multi-asset\"}",
        expected_json: "{\"assets_mode\":\"Multi-Assets\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-assets_mode-multi-assets mode",
        input_json: "{\"assets_mode\":\"multi-assets mode\"}",
        expected_json: "{\"assets_mode\":\"Multi-Assets\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-account_mode-classic trading",
        input_json: "{\"account_mode\":\"classic trading\"}",
        expected_json: "{\"account_mode\":\"Classic Trading\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-account_mode-portfolio margin",
        input_json: "{\"account_mode\":\"portfolio margin\"}",
        expected_json: "{\"account_mode\":\"Portfolio Margin\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-side-both",
        input_json: "{\"side\":\"both\"}",
        expected_json: "{\"side\":\"BOTH\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-side-buy",
        input_json: "{\"side\":\"buy\"}",
        expected_json: "{\"side\":\"BUY\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-side-sell",
        input_json: "{\"side\":\"sell\"}",
        expected_json: "{\"side\":\"SELL\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-order_type-market",
        input_json: "{\"order_type\":\"market\"}",
        expected_json: "{\"order_type\":\"MARKET\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-order_type-limit",
        input_json: "{\"order_type\":\"limit\"}",
        expected_json: "{\"order_type\":\"LIMIT\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-tif-gtc",
        input_json: "{\"tif\":\"gtc\"}",
        expected_json: "{\"tif\":\"GTC\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-tif-ioc",
        input_json: "{\"tif\":\"ioc\"}",
        expected_json: "{\"tif\":\"IOC\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-tif-fok",
        input_json: "{\"tif\":\"fok\"}",
        expected_json: "{\"tif\":\"FOK\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-tif-gtd",
        input_json: "{\"tif\":\"gtd\"}",
        expected_json: "{\"tif\":\"GTD\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-chart_view_mode-tradingview",
        input_json: "{\"chart\":{\"view_mode\":\"tradingview\"}}",
        expected_json: "{\"chart\":{\"view_mode\":\"tradingview\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-chart_view_mode-original",
        input_json: "{\"chart\":{\"view_mode\":\"original\"}}",
        expected_json: "{\"chart\":{\"view_mode\":\"original\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-chart_view_mode-lightweight",
        input_json: "{\"chart\":{\"view_mode\":\"lightweight\"}}",
        expected_json: "{\"chart\":{\"view_mode\":\"lightweight\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-chart_view_mode-tradingview lightweight",
        input_json: "{\"chart\":{\"view_mode\":\"tradingview lightweight\"}}",
        expected_json: "{\"chart\":{\"view_mode\":\"lightweight\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-logic-and",
        input_json: "{\"backtest\":{\"logic\":\"and\"}}",
        expected_json: "{\"backtest\":{\"logic\":\"AND\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-logic-or",
        input_json: "{\"backtest\":{\"logic\":\"or\"}}",
        expected_json: "{\"backtest\":{\"logic\":\"OR\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-logic-separate",
        input_json: "{\"backtest\":{\"logic\":\"separate\"}}",
        expected_json: "{\"backtest\":{\"logic\":\"SEPARATE\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-backtest_execution_backend-desktop",
        input_json: "{\"backtest\":{\"execution_backend\":\"desktop\"}}",
        expected_json: "{\"backtest\":{\"execution_backend\":\"local\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-backtest_execution_backend-desktop-local",
        input_json: "{\"backtest\":{\"execution_backend\":\"desktop-local\"}}",
        expected_json: "{\"backtest\":{\"execution_backend\":\"local\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-backtest_execution_backend-local",
        input_json: "{\"backtest\":{\"execution_backend\":\"local\"}}",
        expected_json: "{\"backtest\":{\"execution_backend\":\"local\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-backtest_execution_backend-remote",
        input_json: "{\"backtest\":{\"execution_backend\":\"remote\"}}",
        expected_json: "{\"backtest\":{\"execution_backend\":\"service\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-backtest_execution_backend-service",
        input_json: "{\"backtest\":{\"execution_backend\":\"service\"}}",
        expected_json: "{\"backtest\":{\"execution_backend\":\"service\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-backtest_execution_backend-service-api",
        input_json: "{\"backtest\":{\"execution_backend\":\"service-api\"}}",
        expected_json: "{\"backtest\":{\"execution_backend\":\"service\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-mdd_logic-per_trade",
        input_json: "{\"backtest\":{\"mdd_logic\":\"per_trade\"}}",
        expected_json: "{\"backtest\":{\"mdd_logic\":\"per_trade\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-mdd_logic-cumulative",
        input_json: "{\"backtest\":{\"mdd_logic\":\"cumulative\"}}",
        expected_json: "{\"backtest\":{\"mdd_logic\":\"cumulative\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-mdd_logic-entire_account",
        input_json: "{\"backtest\":{\"mdd_logic\":\"entire_account\"}}",
        expected_json: "{\"backtest\":{\"mdd_logic\":\"entire_account\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-scan_scope-selected",
        input_json: "{\"backtest\":{\"scan_scope\":\"selected\"}}",
        expected_json: "{\"backtest\":{\"scan_scope\":\"selected\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-scan_scope-top_n",
        input_json: "{\"backtest\":{\"scan_scope\":\"top_n\"}}",
        expected_json: "{\"backtest\":{\"scan_scope\":\"top_n\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-scan_scope-top-n",
        input_json: "{\"backtest\":{\"scan_scope\":\"top-n\"}}",
        expected_json: "{\"backtest\":{\"scan_scope\":\"top_n\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-scan_scope-all_loaded",
        input_json: "{\"backtest\":{\"scan_scope\":\"all_loaded\"}}",
        expected_json: "{\"backtest\":{\"scan_scope\":\"all_loaded\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-scan_scope-all-loaded",
        input_json: "{\"backtest\":{\"scan_scope\":\"all-loaded\"}}",
        expected_json: "{\"backtest\":{\"scan_scope\":\"all_loaded\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_mode-current",
        input_json: "{\"backtest\":{\"optimizer_mode\":\"current\"}}",
        expected_json: "{\"backtest\":{\"optimizer_mode\":\"current\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_mode-single",
        input_json: "{\"backtest\":{\"optimizer_mode\":\"single\"}}",
        expected_json: "{\"backtest\":{\"optimizer_mode\":\"single\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_mode-pairs",
        input_json: "{\"backtest\":{\"optimizer_mode\":\"pairs\"}}",
        expected_json: "{\"backtest\":{\"optimizer_mode\":\"pairs\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_mode-combinations",
        input_json: "{\"backtest\":{\"optimizer_mode\":\"combinations\"}}",
        expected_json: "{\"backtest\":{\"optimizer_mode\":\"combinations\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi_percent",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi_percent\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_percent\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi-percent",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi-percent\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_percent\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi_percent_mdd",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi_percent_mdd\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_percent_mdd\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi-percent-mdd",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi-percent-mdd\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_percent_mdd\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi_drawdown",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi_drawdown\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_drawdown\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi-drawdown",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi-drawdown\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_drawdown\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi_value",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi_value\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_value\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-optimizer_metric-roi-value",
        input_json: "{\"backtest\":{\"optimizer_metric\":\"roi-value\"}}",
        expected_json: "{\"backtest\":{\"optimizer_metric\":\"roi_value\"}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-stop_loss_mode-usdt",
        input_json: "{\"stop_loss\":{\"mode\":\"usdt\"}}",
        expected_json: "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-stop_loss_mode-percent",
        input_json: "{\"stop_loss\":{\"mode\":\"percent\"}}",
        expected_json: "{\"stop_loss\":{\"enabled\":false,\"mode\":\"percent\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-stop_loss_mode-both",
        input_json: "{\"stop_loss\":{\"mode\":\"both\"}}",
        expected_json: "{\"stop_loss\":{\"enabled\":false,\"mode\":\"both\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-stop_loss_scope-per_trade",
        input_json: "{\"stop_loss\":{\"scope\":\"per_trade\"}}",
        expected_json: "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-stop_loss_scope-cumulative",
        input_json: "{\"stop_loss\":{\"scope\":\"cumulative\"}}",
        expected_json: "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"cumulative\",\"usdt\":0.0}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-stop_loss_scope-entire_account",
        input_json: "{\"stop_loss\":{\"scope\":\"entire_account\"}}",
        expected_json: "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"entire_account\",\"usdt\":0.0}}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_use_for-advisory",
        input_json: "{\"llm_use_for\":\"advisory\"}",
        expected_json: "{\"llm_use_for\":\"advisory\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_use_for-backtest_explanation",
        input_json: "{\"llm_use_for\":\"backtest_explanation\"}",
        expected_json: "{\"llm_use_for\":\"backtest_explanation\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_use_for-risk_review",
        input_json: "{\"llm_use_for\":\"risk_review\"}",
        expected_json: "{\"llm_use_for\":\"risk_review\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_use_for-signal_confirmation",
        input_json: "{\"llm_use_for\":\"signal_confirmation\"}",
        expected_json: "{\"llm_use_for\":\"signal_confirmation\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-default",
        input_json: "{\"llm_reasoning_effort\":\"default\"}",
        expected_json: "{\"llm_reasoning_effort\":\"default\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-disabled",
        input_json: "{\"llm_reasoning_effort\":\"disabled\"}",
        expected_json: "{\"llm_reasoning_effort\":\"disabled\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-enabled",
        input_json: "{\"llm_reasoning_effort\":\"enabled\"}",
        expected_json: "{\"llm_reasoning_effort\":\"enabled\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-extra-high",
        input_json: "{\"llm_reasoning_effort\":\"extra-high\"}",
        expected_json: "{\"llm_reasoning_effort\":\"xhigh\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-extra_high",
        input_json: "{\"llm_reasoning_effort\":\"extra_high\"}",
        expected_json: "{\"llm_reasoning_effort\":\"xhigh\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-high",
        input_json: "{\"llm_reasoning_effort\":\"high\"}",
        expected_json: "{\"llm_reasoning_effort\":\"high\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-low",
        input_json: "{\"llm_reasoning_effort\":\"low\"}",
        expected_json: "{\"llm_reasoning_effort\":\"low\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-max",
        input_json: "{\"llm_reasoning_effort\":\"max\"}",
        expected_json: "{\"llm_reasoning_effort\":\"max\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-medium",
        input_json: "{\"llm_reasoning_effort\":\"medium\"}",
        expected_json: "{\"llm_reasoning_effort\":\"medium\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-minimal",
        input_json: "{\"llm_reasoning_effort\":\"minimal\"}",
        expected_json: "{\"llm_reasoning_effort\":\"minimal\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-none",
        input_json: "{\"llm_reasoning_effort\":\"none\"}",
        expected_json: "{\"llm_reasoning_effort\":\"none\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_reasoning_effort-xhigh",
        input_json: "{\"llm_reasoning_effort\":\"xhigh\"}",
        expected_json: "{\"llm_reasoning_effort\":\"xhigh\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-percent",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percent\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percent\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-%",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"%\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"%\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-perc",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"perc\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"perc\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-percentage",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percentage\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percentage\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-fraction",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"fraction\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"fraction\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-decimal",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"decimal\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"decimal\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-position_pct_units-ratio",
        input_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"ratio\"},\"symbol\":\"BTCUSDT\"}]}",
        expected_json: "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"ratio\"},\"symbol\":\"BTCUSDT\"}]}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-alibaba",
        input_json: "{\"llm_provider\":\"alibaba\"}",
        expected_json: "{\"llm_provider\":\"qwen\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-alibaba-qwen",
        input_json: "{\"llm_provider\":\"alibaba-qwen\"}",
        expected_json: "{\"llm_provider\":\"qwen\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-anthropic",
        input_json: "{\"llm_provider\":\"anthropic\"}",
        expected_json: "{\"llm_provider\":\"anthropic\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-anthropic-claude",
        input_json: "{\"llm_provider\":\"anthropic-claude\"}",
        expected_json: "{\"llm_provider\":\"anthropic\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-arctic",
        input_json: "{\"llm_provider\":\"arctic\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-bloom",
        input_json: "{\"llm_provider\":\"bloom\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-bloomz",
        input_json: "{\"llm_provider\":\"bloomz\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-cerebras",
        input_json: "{\"llm_provider\":\"cerebras\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-chatglm",
        input_json: "{\"llm_provider\":\"chatglm\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-chatgpt",
        input_json: "{\"llm_provider\":\"chatgpt\"}",
        expected_json: "{\"llm_provider\":\"openai\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-claude",
        input_json: "{\"llm_provider\":\"claude\"}",
        expected_json: "{\"llm_provider\":\"anthropic\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-codet5",
        input_json: "{\"llm_provider\":\"codet5\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-custom",
        input_json: "{\"llm_provider\":\"custom\"}",
        expected_json: "{\"llm_provider\":\"local\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-dashscope",
        input_json: "{\"llm_provider\":\"dashscope\"}",
        expected_json: "{\"llm_provider\":\"qwen\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-dbrx",
        input_json: "{\"llm_provider\":\"dbrx\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-decicoder",
        input_json: "{\"llm_provider\":\"decicoder\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-deepseek",
        input_json: "{\"llm_provider\":\"deepseek\"}",
        expected_json: "{\"llm_provider\":\"deepseek\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-dolly",
        input_json: "{\"llm_provider\":\"dolly\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-flan-t5",
        input_json: "{\"llm_provider\":\"flan-t5\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-fugaku",
        input_json: "{\"llm_provider\":\"fugaku\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-gemini",
        input_json: "{\"llm_provider\":\"gemini\"}",
        expected_json: "{\"llm_provider\":\"gemini\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-gemma4",
        input_json: "{\"llm_provider\":\"gemma4\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-glm",
        input_json: "{\"llm_provider\":\"glm\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-glm5",
        input_json: "{\"llm_provider\":\"glm5\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-google",
        input_json: "{\"llm_provider\":\"google\"}",
        expected_json: "{\"llm_provider\":\"gemini\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-google-gemini",
        input_json: "{\"llm_provider\":\"google-gemini\"}",
        expected_json: "{\"llm_provider\":\"gemini\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-gpt-neox",
        input_json: "{\"llm_provider\":\"gpt-neox\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-gpt20b",
        input_json: "{\"llm_provider\":\"gpt20b\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-grok",
        input_json: "{\"llm_provider\":\"grok\"}",
        expected_json: "{\"llm_provider\":\"grok\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-hf",
        input_json: "{\"llm_provider\":\"hf\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-hf-tgi",
        input_json: "{\"llm_provider\":\"hf-tgi\"}",
        expected_json: "{\"llm_provider\":\"tgi\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-hugging-face",
        input_json: "{\"llm_provider\":\"hugging-face\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-huggingface",
        input_json: "{\"llm_provider\":\"huggingface\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-huggingface-tgi",
        input_json: "{\"llm_provider\":\"huggingface-tgi\"}",
        expected_json: "{\"llm_provider\":\"tgi\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-jais",
        input_json: "{\"llm_provider\":\"jais\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-kimi",
        input_json: "{\"llm_provider\":\"kimi\"}",
        expected_json: "{\"llm_provider\":\"moonshot\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-llama-4",
        input_json: "{\"llm_provider\":\"llama-4\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-llama-cpp",
        input_json: "{\"llm_provider\":\"llama-cpp\"}",
        expected_json: "{\"llm_provider\":\"llamacpp\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-llama-cpp-server",
        input_json: "{\"llm_provider\":\"llama-cpp-server\"}",
        expected_json: "{\"llm_provider\":\"llamacpp\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-llama.cpp",
        input_json: "{\"llm_provider\":\"llama.cpp\"}",
        expected_json: "{\"llm_provider\":\"llamacpp\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-llama4",
        input_json: "{\"llm_provider\":\"llama4\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-llamacpp",
        input_json: "{\"llm_provider\":\"llamacpp\"}",
        expected_json: "{\"llm_provider\":\"llamacpp\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-lm-studio",
        input_json: "{\"llm_provider\":\"lm-studio\"}",
        expected_json: "{\"llm_provider\":\"lmstudio\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-lmstudio",
        input_json: "{\"llm_provider\":\"lmstudio\"}",
        expected_json: "{\"llm_provider\":\"lmstudio\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-local",
        input_json: "{\"llm_provider\":\"local\"}",
        expected_json: "{\"llm_provider\":\"local\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-local-openai",
        input_json: "{\"llm_provider\":\"local-openai\"}",
        expected_json: "{\"llm_provider\":\"local\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-local-openai-compatible",
        input_json: "{\"llm_provider\":\"local-openai-compatible\"}",
        expected_json: "{\"llm_provider\":\"local\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-mamba",
        input_json: "{\"llm_provider\":\"mamba\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-mimo",
        input_json: "{\"llm_provider\":\"mimo\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-minimax",
        input_json: "{\"llm_provider\":\"minimax\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-mistral",
        input_json: "{\"llm_provider\":\"mistral\"}",
        expected_json: "{\"llm_provider\":\"mistral\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-mistral-ai",
        input_json: "{\"llm_provider\":\"mistral-ai\"}",
        expected_json: "{\"llm_provider\":\"mistral\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-moonshot",
        input_json: "{\"llm_provider\":\"moonshot\"}",
        expected_json: "{\"llm_provider\":\"moonshot\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-moonshot-ai",
        input_json: "{\"llm_provider\":\"moonshot-ai\"}",
        expected_json: "{\"llm_provider\":\"moonshot\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-mpt",
        input_json: "{\"llm_provider\":\"mpt\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-nemotron",
        input_json: "{\"llm_provider\":\"nemotron\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-ollama",
        input_json: "{\"llm_provider\":\"ollama\"}",
        expected_json: "{\"llm_provider\":\"ollama\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-olmo",
        input_json: "{\"llm_provider\":\"olmo\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-open-llama",
        input_json: "{\"llm_provider\":\"open-llama\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-open-source",
        input_json: "{\"llm_provider\":\"open-source\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-open-weight",
        input_json: "{\"llm_provider\":\"open-weight\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-open-weights",
        input_json: "{\"llm_provider\":\"open-weights\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-openai",
        input_json: "{\"llm_provider\":\"openai\"}",
        expected_json: "{\"llm_provider\":\"openai\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-openai-chatgpt",
        input_json: "{\"llm_provider\":\"openai-chatgpt\"}",
        expected_json: "{\"llm_provider\":\"openai\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-openllama",
        input_json: "{\"llm_provider\":\"openllama\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-opensource",
        input_json: "{\"llm_provider\":\"opensource\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-oss",
        input_json: "{\"llm_provider\":\"oss\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-pythia",
        input_json: "{\"llm_provider\":\"pythia\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-qwen",
        input_json: "{\"llm_provider\":\"qwen\"}",
        expected_json: "{\"llm_provider\":\"qwen\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-qwen-local",
        input_json: "{\"llm_provider\":\"qwen-local\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-redpajama",
        input_json: "{\"llm_provider\":\"redpajama\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-replit-code",
        input_json: "{\"llm_provider\":\"replit-code\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-rmkv",
        input_json: "{\"llm_provider\":\"rmkv\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-rwkv",
        input_json: "{\"llm_provider\":\"rwkv\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-s-glang",
        input_json: "{\"llm_provider\":\"s-glang\"}",
        expected_json: "{\"llm_provider\":\"vllm\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-santacoder",
        input_json: "{\"llm_provider\":\"santacoder\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-sglang",
        input_json: "{\"llm_provider\":\"sglang\"}",
        expected_json: "{\"llm_provider\":\"vllm\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-stablelm",
        input_json: "{\"llm_provider\":\"stablelm\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-starchat",
        input_json: "{\"llm_provider\":\"starchat\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-step",
        input_json: "{\"llm_provider\":\"step\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-stepfun",
        input_json: "{\"llm_provider\":\"stepfun\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-t5",
        input_json: "{\"llm_provider\":\"t5\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-text-generation-inference",
        input_json: "{\"llm_provider\":\"text-generation-inference\"}",
        expected_json: "{\"llm_provider\":\"tgi\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-tgi",
        input_json: "{\"llm_provider\":\"tgi\"}",
        expected_json: "{\"llm_provider\":\"tgi\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-vllm",
        input_json: "{\"llm_provider\":\"vllm\"}",
        expected_json: "{\"llm_provider\":\"vllm\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-xai",
        input_json: "{\"llm_provider\":\"xai\"}",
        expected_json: "{\"llm_provider\":\"grok\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-xai-grok",
        input_json: "{\"llm_provider\":\"xai-grok\"}",
        expected_json: "{\"llm_provider\":\"grok\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-xgen",
        input_json: "{\"llm_provider\":\"xgen\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-xiaomi",
        input_json: "{\"llm_provider\":\"xiaomi\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-yalm",
        input_json: "{\"llm_provider\":\"yalm\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "choice-llm_provider-zai",
        input_json: "{\"llm_provider\":\"zai\"}",
        expected_json: "{\"llm_provider\":\"open-source\"}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "bool-stop_without_close-true",
        input_json: "{\"stop_without_close\":\"true\"}",
        expected_json: "{\"stop_without_close\":true}",
        valid: true,
        expected_error: "",
    },
    PythonRuntimeConfigReferenceCase {
        name: "bool-stop_without_close-false",
        input_json: "{\"stop_without_close\":\"false\"}",
        expected_json: "{\"stop_without_close\":false}",
        valid: true,
        expected_error: "",
    },
];

    pub struct PythonStrategyControlsReferenceCase {
    pub name: &'static str,
    pub kind: &'static str,
    pub input_json: &'static str,
    pub expected_json: &'static str,
}

pub const PYTHON_STRATEGY_CONTROLS_REFERENCE_CASES: &[PythonStrategyControlsReferenceCase] = &[
    PythonStrategyControlsReferenceCase {
        name: "runtime-canonical",
        kind: "runtime",
        input_json: "{\"account_mode\":\"portfolio margin\",\"add_only\":\"false\",\"connector_backend\":\"CCXT\",\"leverage\":\"3\",\"loop_interval_override\":\" 5 M \",\"position_pct\":\"12.5\",\"position_pct_units\":\"percentage\",\"side\":\"buy\",\"stop_loss\":{\"enabled\":\"true\",\"mode\":\"both\",\"percent\":\"2.5\",\"scope\":\"bad\",\"usdt\":\"50\"}}",
        expected_json: "{\"account_mode\":\"Portfolio Margin\",\"add_only\":true,\"connector_backend\":\"ccxt\",\"leverage\":3,\"loop_interval_override\":\"5m\",\"position_pct\":12.5,\"position_pct_units\":\"percent\",\"side\":\"BUY\",\"stop_loss\":{\"enabled\":true,\"mode\":\"both\",\"percent\":2.5,\"scope\":\"per_trade\",\"usdt\":50.0}}",
    },
    PythonStrategyControlsReferenceCase {
        name: "runtime-python-truthiness-boundaries",
        kind: "runtime",
        input_json: "{\"_position_pct_units\":\"percentage\",\"account_mode\":false,\"add_only\":null,\"connector_backend\":false,\"leverage\":2.5,\"loop_interval_override\":\" 5 M \",\"position_pct\":true,\"position_pct_units\":\"\",\"side\":\" buy \"}",
        expected_json: "{\"leverage\":2,\"loop_interval_override\":\"5m\",\"position_pct\":1.0,\"position_pct_units\":\"percent\"}",
    },
    PythonStrategyControlsReferenceCase {
        name: "runtime-kind-is-case-sensitive",
        kind: "Runtime",
        input_json: "{\"connector_backend\":\"ccxt\",\"side\":\"buy\",\"stop_loss\":{\"enabled\":true}}",
        expected_json: "{}",
    },
    PythonStrategyControlsReferenceCase {
        name: "backtest-canonical",
        kind: "backtest",
        input_json: "{\"account_mode\":\"classic\",\"assets_mode\":\"multi assets\",\"capital\":\"1000\",\"connector_backend\":\"ccxt\",\"fee_bps\":\"5\",\"leverage\":0,\"logic\":\"separate\",\"loop_interval_override\":\" 1 h \",\"margin_mode\":\" Isolated \",\"position_mode\":\" Hedge \",\"position_pct\":\"0.4\",\"position_pct_units\":\"fraction\",\"side\":\"sell short\",\"slippage_bps\":\"2\",\"stop_loss\":{\"enabled\":\"true\",\"mode\":\"both\",\"percent\":\"2.5\",\"scope\":\"entire_account\"}}",
        expected_json: "{\"account_mode\":\"Classic Trading\",\"assets_mode\":\"Multi-Assets\",\"capital\":1000.0,\"connector_backend\":\"ccxt\",\"leverage\":0,\"logic\":\"SEPARATE\",\"loop_interval_override\":\"1h\",\"margin_mode\":\" Isolated \",\"position_mode\":\" Hedge \",\"position_pct\":0.4,\"position_pct_units\":\"fraction\",\"side\":\"SELL\",\"stop_loss\":{\"enabled\":true,\"mode\":\"both\",\"percent\":2.5,\"scope\":\"entire_account\",\"usdt\":0.0}}",
    },
    PythonStrategyControlsReferenceCase {
        name: "backtest-exact-logic-and-fuzzy-side",
        kind: "backtest",
        input_json: "{\"account_mode\":\"portfolio\",\"assets_mode\":\"single asset\",\"leverage\":\"3.5\",\"logic\":\" OR \",\"margin_mode\":\"\",\"position_mode\":\"Hedge\",\"side\":\" buy \"}",
        expected_json: "{\"account_mode\":\"Portfolio Margin\",\"assets_mode\":\"Single-Asset\",\"position_mode\":\"Hedge\",\"side\":\"BUY\"}",
    },
];

    pub struct PythonStrategyRiskReferenceCase {
    pub name: &'static str,
    pub input_json: &'static str,
    pub expected_json: &'static str,
}

pub const PYTHON_STRATEGY_RISK_REFERENCE_CASES: &[PythonStrategyRiskReferenceCase] = &[
    PythonStrategyRiskReferenceCase {
        name: "risk-defaults",
        input_json: "{}",
        expected_json: "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-canonical-all-controls",
        input_json: "{\"allow_close_ignoring_hold\":\"true\",\"allow_indicator_close_without_signal\":\"false\",\"allow_multi_indicator_close\":\"true\",\"allow_opposite_positions\":\"false\",\"auto_bump_percent_multiplier\":\"20\",\"auto_flip_on_close\":\"false\",\"close_on_exit\":\"true\",\"futures_flat_purge_grace_seconds\":\"18.5\",\"futures_flat_purge_miss_threshold\":\"4\",\"hedge_preserve_opposites\":\"true\",\"indicator_flip_confirmation_bars\":\"2\",\"indicator_flip_cooldown_bars\":\"4\",\"indicator_flip_cooldown_seconds\":\"12.5\",\"indicator_min_position_hold_bars\":\"3\",\"indicator_min_position_hold_seconds\":\"7.25\",\"indicator_reentry_cooldown_bars\":\"2\",\"indicator_reentry_cooldown_seconds\":\"9.5\",\"indicator_reentry_requires_signal_reset\":\"true\",\"indicator_use_live_values\":\"false\",\"max_auto_bump_percent\":\"7.5\",\"positions_missing_autoclose\":\"false\",\"positions_missing_grace_seconds\":\"45\",\"positions_missing_threshold\":\"3\",\"require_indicator_flip_signal\":\"yes\",\"stop_loss\":{\"enabled\":\"true\",\"mode\":\"percent\",\"percent\":\"2.5\",\"scope\":\"entire_account\",\"usdt\":\"25\"},\"strict_indicator_flip_enforcement\":\"no\"}",
        expected_json: "{\"allow_close_ignoring_hold\":true,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":true,\"allow_opposite_positions\":false,\"auto_bump_percent_multiplier\":20.0,\"auto_flip_on_close\":false,\"close_on_exit\":true,\"futures_flat_purge_grace_seconds\":18.5,\"futures_flat_purge_miss_threshold\":4,\"hedge_preserve_opposites\":true,\"indicator_flip_confirmation_bars\":2,\"indicator_flip_cooldown_bars\":4,\"indicator_flip_cooldown_seconds\":12.5,\"indicator_min_position_hold_bars\":3,\"indicator_min_position_hold_seconds\":7.25,\"indicator_reentry_cooldown_bars\":2,\"indicator_reentry_cooldown_seconds\":9.5,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":7.5,\"positions_missing_autoclose\":false,\"positions_missing_grace_seconds\":45.0,\"positions_missing_threshold\":3,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":true,\"mode\":\"percent\",\"percent\":2.5,\"scope\":\"entire_account\",\"usdt\":25.0},\"strict_indicator_flip_enforcement\":false}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-valid-lower-and-upper-bounds",
        input_json: "{\"auto_bump_percent_multiplier\":1000,\"futures_flat_purge_grace_seconds\":604800,\"futures_flat_purge_miss_threshold\":1,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":0,\"indicator_flip_cooldown_seconds\":0,\"indicator_min_position_hold_bars\":0,\"indicator_min_position_hold_seconds\":0,\"indicator_reentry_cooldown_bars\":0,\"indicator_reentry_cooldown_seconds\":0,\"max_auto_bump_percent\":100,\"positions_missing_grace_seconds\":604800,\"positions_missing_threshold\":1,\"stop_loss\":{\"enabled\":false,\"mode\":\"both\",\"percent\":0,\"scope\":\"cumulative\",\"usdt\":0}}",
        expected_json: "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":1000.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":604800.0,\"futures_flat_purge_miss_threshold\":1,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":0,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":0,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":0,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":100.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":604800.0,\"positions_missing_threshold\":1,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"both\",\"percent\":0.0,\"scope\":\"cumulative\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}",
    },
];

    pub const PYTHON_STRATEGY_RISK_LOOSE_REFERENCE_CASES: &[PythonStrategyRiskReferenceCase] = &[
    PythonStrategyRiskReferenceCase {
        name: "risk-loose-string-y",
        input_json: "{\"allow_close_ignoring_hold\":\"y\",\"allow_indicator_close_without_signal\":\"y\",\"allow_multi_indicator_close\":\"y\",\"allow_opposite_positions\":\"y\",\"auto_flip_on_close\":\"y\",\"close_on_exit\":\"y\",\"hedge_preserve_opposites\":\"y\",\"indicator_reentry_requires_signal_reset\":\"y\",\"indicator_use_live_values\":\"y\",\"positions_missing_autoclose\":\"y\",\"require_indicator_flip_signal\":\"y\",\"strict_indicator_flip_enforcement\":\"y\"}",
        expected_json: "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-loose-unknown-string",
        input_json: "{\"allow_close_ignoring_hold\":\"maybe\",\"allow_indicator_close_without_signal\":\"maybe\",\"allow_multi_indicator_close\":\"maybe\",\"allow_opposite_positions\":\"maybe\",\"auto_flip_on_close\":\"maybe\",\"close_on_exit\":\"maybe\",\"hedge_preserve_opposites\":\"maybe\",\"indicator_reentry_requires_signal_reset\":\"maybe\",\"indicator_use_live_values\":\"maybe\",\"positions_missing_autoclose\":\"maybe\",\"require_indicator_flip_signal\":\"maybe\",\"strict_indicator_flip_enforcement\":\"maybe\"}",
        expected_json: "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-loose-fractional-zero",
        input_json: "{\"allow_close_ignoring_hold\":0.5,\"allow_indicator_close_without_signal\":0.5,\"allow_multi_indicator_close\":0.5,\"allow_opposite_positions\":0.5,\"auto_flip_on_close\":0.5,\"close_on_exit\":0.5,\"hedge_preserve_opposites\":0.5,\"indicator_reentry_requires_signal_reset\":0.5,\"indicator_use_live_values\":0.5,\"positions_missing_autoclose\":0.5,\"require_indicator_flip_signal\":0.5,\"strict_indicator_flip_enforcement\":0.5}",
        expected_json: "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":false,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":false,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":false,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":false,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":false,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":false}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-loose-fractional-one",
        input_json: "{\"allow_close_ignoring_hold\":1.5,\"allow_indicator_close_without_signal\":1.5,\"allow_multi_indicator_close\":1.5,\"allow_opposite_positions\":1.5,\"auto_flip_on_close\":1.5,\"close_on_exit\":1.5,\"hedge_preserve_opposites\":1.5,\"indicator_reentry_requires_signal_reset\":1.5,\"indicator_use_live_values\":1.5,\"positions_missing_autoclose\":1.5,\"require_indicator_flip_signal\":1.5,\"strict_indicator_flip_enforcement\":1.5}",
        expected_json: "{\"allow_close_ignoring_hold\":true,\"allow_indicator_close_without_signal\":true,\"allow_multi_indicator_close\":true,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":true,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":true,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":true,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-loose-negative-fractional-zero",
        input_json: "{\"allow_close_ignoring_hold\":-0.5,\"allow_indicator_close_without_signal\":-0.5,\"allow_multi_indicator_close\":-0.5,\"allow_opposite_positions\":-0.5,\"auto_flip_on_close\":-0.5,\"close_on_exit\":-0.5,\"hedge_preserve_opposites\":-0.5,\"indicator_reentry_requires_signal_reset\":-0.5,\"indicator_use_live_values\":-0.5,\"positions_missing_autoclose\":-0.5,\"require_indicator_flip_signal\":-0.5,\"strict_indicator_flip_enforcement\":-0.5}",
        expected_json: "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":false,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":false,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":false,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":false,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":false,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":false}",
    },
    PythonStrategyRiskReferenceCase {
        name: "risk-loose-negative-fractional-one",
        input_json: "{\"allow_close_ignoring_hold\":-1.5,\"allow_indicator_close_without_signal\":-1.5,\"allow_multi_indicator_close\":-1.5,\"allow_opposite_positions\":-1.5,\"auto_flip_on_close\":-1.5,\"close_on_exit\":-1.5,\"hedge_preserve_opposites\":-1.5,\"indicator_reentry_requires_signal_reset\":-1.5,\"indicator_use_live_values\":-1.5,\"positions_missing_autoclose\":-1.5,\"require_indicator_flip_signal\":-1.5,\"strict_indicator_flip_enforcement\":-1.5}",
        expected_json: "{\"allow_close_ignoring_hold\":true,\"allow_indicator_close_without_signal\":true,\"allow_multi_indicator_close\":true,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":true,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":true,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":true,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}",
    },
];
    pub const PYTHON_INDICATOR_ENABLED_REFERENCE_JSON: &str = "[{\"expected\":false,\"input\":{},\"name\":\"indicator-enabled-missing\"},{\"expected\":true,\"input\":{\"enabled\":true},\"name\":\"indicator-enabled-bool-true\"},{\"expected\":false,\"input\":{\"enabled\":false},\"name\":\"indicator-enabled-bool-false\"},{\"expected\":true,\"input\":{\"enabled\":\"true\"},\"name\":\"indicator-enabled-string-true\"},{\"expected\":false,\"input\":{\"enabled\":\"false\"},\"name\":\"indicator-enabled-string-false\"},{\"expected\":true,\"input\":{\"enabled\":\"yes\"},\"name\":\"indicator-enabled-string-yes\"},{\"expected\":false,\"input\":{\"enabled\":\"no\"},\"name\":\"indicator-enabled-string-no\"},{\"expected\":true,\"input\":{\"enabled\":\"on\"},\"name\":\"indicator-enabled-string-on\"},{\"expected\":false,\"input\":{\"enabled\":\"off\"},\"name\":\"indicator-enabled-string-off\"},{\"expected\":false,\"input\":{\"enabled\":\"disabled\"},\"name\":\"indicator-enabled-string-disabled\"},{\"expected\":false,\"input\":{\"enabled\":\"none\"},\"name\":\"indicator-enabled-string-none\"},{\"expected\":false,\"input\":{\"enabled\":\"null\"},\"name\":\"indicator-enabled-string-null\"},{\"expected\":false,\"input\":{\"enabled\":\"0.5\"},\"name\":\"indicator-enabled-string-numeric\"},{\"expected\":false,\"input\":{\"enabled\":\"y\"},\"name\":\"indicator-enabled-string-y\"},{\"expected\":false,\"input\":{\"enabled\":\"maybe\"},\"name\":\"indicator-enabled-unknown-string\"},{\"expected\":false,\"input\":{\"enabled\":\"\"},\"name\":\"indicator-enabled-empty-string\"},{\"expected\":false,\"input\":{\"enabled\":null},\"name\":\"indicator-enabled-null\"},{\"expected\":false,\"input\":{\"enabled\":0},\"name\":\"indicator-enabled-zero\"},{\"expected\":true,\"input\":{\"enabled\":1},\"name\":\"indicator-enabled-one\"},{\"expected\":false,\"input\":{\"enabled\":0.5},\"name\":\"indicator-enabled-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":1.5},\"name\":\"indicator-enabled-fractional-one\"},{\"expected\":false,\"input\":{\"enabled\":-0.5},\"name\":\"indicator-enabled-negative-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":-1.5},\"name\":\"indicator-enabled-negative-fractional-one\"}]";
    pub const PYTHON_BACKTEST_INDICATOR_ENABLED_REFERENCE_JSON: &str = "[{\"expected\":false,\"input\":{},\"name\":\"backtest-indicator-enabled-missing\"},{\"expected\":true,\"input\":{\"enabled\":true},\"name\":\"backtest-indicator-enabled-bool-true\"},{\"expected\":false,\"input\":{\"enabled\":false},\"name\":\"backtest-indicator-enabled-bool-false\"},{\"expected\":true,\"input\":{\"enabled\":\"true\"},\"name\":\"backtest-indicator-enabled-string-true\"},{\"expected\":false,\"input\":{\"enabled\":\"false\"},\"name\":\"backtest-indicator-enabled-string-false\"},{\"expected\":true,\"input\":{\"enabled\":\"yes\"},\"name\":\"backtest-indicator-enabled-string-yes\"},{\"expected\":false,\"input\":{\"enabled\":\"no\"},\"name\":\"backtest-indicator-enabled-string-no\"},{\"expected\":true,\"input\":{\"enabled\":\"on\"},\"name\":\"backtest-indicator-enabled-string-on\"},{\"expected\":false,\"input\":{\"enabled\":\"off\"},\"name\":\"backtest-indicator-enabled-string-off\"},{\"expected\":false,\"input\":{\"enabled\":\"disabled\"},\"name\":\"backtest-indicator-enabled-string-disabled\"},{\"expected\":true,\"input\":{\"enabled\":\"none\"},\"name\":\"backtest-indicator-enabled-string-none\"},{\"expected\":true,\"input\":{\"enabled\":\"null\"},\"name\":\"backtest-indicator-enabled-string-null\"},{\"expected\":true,\"input\":{\"enabled\":\"0.5\"},\"name\":\"backtest-indicator-enabled-string-numeric\"},{\"expected\":true,\"input\":{\"enabled\":\"y\"},\"name\":\"backtest-indicator-enabled-string-y\"},{\"expected\":true,\"input\":{\"enabled\":\"maybe\"},\"name\":\"backtest-indicator-enabled-unknown-string\"},{\"expected\":false,\"input\":{\"enabled\":\"\"},\"name\":\"backtest-indicator-enabled-empty-string\"},{\"expected\":false,\"input\":{\"enabled\":null},\"name\":\"backtest-indicator-enabled-null\"},{\"expected\":false,\"input\":{\"enabled\":0},\"name\":\"backtest-indicator-enabled-zero\"},{\"expected\":true,\"input\":{\"enabled\":1},\"name\":\"backtest-indicator-enabled-one\"},{\"expected\":true,\"input\":{\"enabled\":0.5},\"name\":\"backtest-indicator-enabled-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":1.5},\"name\":\"backtest-indicator-enabled-fractional-one\"},{\"expected\":true,\"input\":{\"enabled\":-0.5},\"name\":\"backtest-indicator-enabled-negative-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":-1.5},\"name\":\"backtest-indicator-enabled-negative-fractional-one\"}]";
    pub const PYTHON_INTERVAL_SECONDS_REFERENCE_JSON: &str = "[{\"indicator_seconds\":1.0,\"input\":\"1s\",\"loop_seconds\":1},{\"indicator_seconds\":300.0,\"input\":\"5m\",\"loop_seconds\":300},{\"indicator_seconds\":60.0,\"input\":\"1.5m\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"0.5h\",\"loop_seconds\":60},{\"indicator_seconds\":3600.0,\"input\":\"1h\",\"loop_seconds\":3600},{\"indicator_seconds\":86400.0,\"input\":\"1d\",\"loop_seconds\":86400},{\"indicator_seconds\":60.0,\"input\":\"1w\",\"loop_seconds\":604800},{\"indicator_seconds\":60.0,\"input\":\"1mo\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"1y\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"5\",\"loop_seconds\":5},{\"indicator_seconds\":0.0,\"input\":\"0m\",\"loop_seconds\":1},{\"indicator_seconds\":-60.0,\"input\":\"-1m\",\"loop_seconds\":1},{\"indicator_seconds\":60.0,\"input\":\"1M\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\" 5m \",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"5m \",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"\",\"loop_seconds\":60}]";
    pub const PYTHON_BACKTEST_INTERVAL_SECONDS_REFERENCE_JSON: &str = "[{\"input\":\"1s\",\"seconds\":1.0},{\"input\":\"5m\",\"seconds\":300.0},{\"input\":\"1.5m\",\"seconds\":90.0},{\"input\":\"0.5h\",\"seconds\":1800.0},{\"input\":\"1h\",\"seconds\":3600.0},{\"input\":\"1d\",\"seconds\":86400.0},{\"input\":\"1w\",\"seconds\":604800.0},{\"input\":\"1mo\",\"seconds\":60.0},{\"input\":\"1y\",\"seconds\":60.0},{\"input\":\"5\",\"seconds\":5.0},{\"input\":\"0m\",\"seconds\":1.0},{\"input\":\"-1m\",\"seconds\":1.0},{\"input\":\"1M\",\"seconds\":60.0},{\"input\":\" 5m \",\"seconds\":300.0},{\"input\":\"5m \",\"seconds\":300.0},{\"input\":\"\",\"seconds\":60.0},{\"input\":\"abc\",\"seconds\":60.0},{\"input\":\"5x\",\"seconds\":60.0}]";
    pub const PYTHON_STOP_INTENT_REFERENCE_JSON: &str = "{\"cases\":[{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{},\"name\":\"default-close-all\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":false},\"name\":\"explicit-close-all\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":true},\"name\":\"explicit-keep-open\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":\"true\"},\"name\":\"string-keep-open\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"false\"},\"name\":\"string-close-all\"}],\"schema_version\":1}";
    pub const PYTHON_STOP_INTENT_LOOSE_REFERENCE_JSON: &str = "{\"cases\":[{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{},\"name\":\"missing\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":null},\"name\":\"null\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"\"},\"name\":\"empty-string\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"y\"},\"name\":\"string-y-is-false\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"maybe\"},\"name\":\"unknown-string-is-false\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":0.5},\"name\":\"fractional-zero-is-false\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":1.5},\"name\":\"fractional-one-is-true\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":-1.5},\"name\":\"negative-fraction-is-true\"}],\"schema_version\":1}";

    pub struct PythonConnectorNormalizationReferenceCase {
    pub name: &'static str,
    pub input: &'static str,
    pub expected: &'static str,
}

pub const PYTHON_CONNECTOR_NORMALIZATION_REFERENCE_CASES: &[PythonConnectorNormalizationReferenceCase] = &[
    PythonConnectorNormalizationReferenceCase {
        name: "empty",
        input: "",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "usds-key",
        input: "binance-sdk-derivatives-trading-usds-futures",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "usds-underscore-key",
        input: "binance_sdk_derivatives_trading_usds_futures",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "usds-label",
        input: "Binance SDK Derivatives Trading USD\u{24c8} Futures (Official Recommended)",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "coin-key",
        input: "binance-sdk-derivatives-trading-coin-futures",
        expected: "binance-sdk-derivatives-trading-coin-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "coin-label",
        input: "Binance SDK Derivatives Trading COIN-M Futures",
        expected: "binance-sdk-derivatives-trading-coin-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "spot-label",
        input: "Binance SDK Spot (Official Recommended)",
        expected: "binance-sdk-spot",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "connector-label",
        input: "Binance Connector Python",
        expected: "binance-connector",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "ccxt-label",
        input: "CCXT (Unified)",
        expected: "ccxt",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "python-binance-label",
        input: "python-binance (Community)",
        expected: "python-binance",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "official-connector-alias",
        input: "Binance Official REST connector",
        expected: "binance-connector",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "unrelated-option-falls-back",
        input: "OANDA REST-v20",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "legacy-gateway-falls-back",
        input: "gateway",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "legacy-custom-falls-back",
        input: "custom",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "url-value-falls-back",
        input: "https://connector.example.test/api",
        expected: "binance-connector",
    },
    PythonConnectorNormalizationReferenceCase {
        name: "unknown-falls-back",
        input: "unknown backend",
        expected: "binance-sdk-derivatives-trading-usds-futures",
    },
];

    pub struct PythonNativeRuntimeConnectorOwnershipReferenceCase {
    pub name: &'static str,
    pub input: &'static str,
    pub expected_owned: bool,
}

pub const PYTHON_NATIVE_RUNTIME_CONNECTOR_OWNERSHIP_REFERENCE_CASES: &[PythonNativeRuntimeConnectorOwnershipReferenceCase] = &[
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "empty-default",
        input: "",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "usds-key",
        input: "binance-sdk-derivatives-trading-usds-futures",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "usds-underscore-alias",
        input: "binance_sdk_derivatives_trading_usds_futures",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "usds-label",
        input: "Binance SDK Derivatives Trading USD\u{24c8} Futures (Official Recommended)",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "usds-readable-alias",
        input: "Binance SDK USD-M Futures",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "coin-key",
        input: "binance-sdk-derivatives-trading-coin-futures",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "spot-key",
        input: "binance-sdk-spot",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "binance-connector-key",
        input: "binance-connector",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "ccxt-label",
        input: "CCXT (Unified)",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "python-binance-label",
        input: "python-binance (Community)",
        expected_owned: true,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "oanda-provider-option",
        input: "OANDA REST-v20",
        expected_owned: false,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "custom-provider",
        input: "custom",
        expected_owned: false,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "unknown-provider",
        input: "unknown backend",
        expected_owned: false,
    },
    PythonNativeRuntimeConnectorOwnershipReferenceCase {
        name: "connector-url-alias",
        input: "https://connector.example.test/api",
        expected_owned: true,
    },
];

    pub struct PythonNativeRuntimeRoutingReferenceCase {
    pub name: &'static str,
    pub selected_exchange: &'static str,
    pub connector_backend: &'static str,
    pub indicator_source: &'static str,
    pub expected_owned: bool,
}

pub const PYTHON_NATIVE_RUNTIME_ROUTING_REFERENCE_CASES: &[PythonNativeRuntimeRoutingReferenceCase] = &[
    PythonNativeRuntimeRoutingReferenceCase {
        name: "binance-default",
        selected_exchange: "Binance",
        connector_backend: "",
        indicator_source: "",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "binance-usds-canonical",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-derivatives-trading-usds-futures",
        indicator_source: "binance_futures",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "binance-usds-label",
        selected_exchange: "Binance",
        connector_backend: "Binance SDK Derivatives Trading USD-M Futures (Official Recommended)",
        indicator_source: "Binance futures",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "binance-coin-futures",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-derivatives-trading-coin-futures",
        indicator_source: "",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "binance-spot",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-spot",
        indicator_source: "Binance spot",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "non-native-exchange",
        selected_exchange: "Bybit",
        connector_backend: "binance-sdk-spot",
        indicator_source: "Binance spot",
        expected_owned: false,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "non-native-connector",
        selected_exchange: "Binance",
        connector_backend: "OANDA REST-v20",
        indicator_source: "Binance spot",
        expected_owned: false,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "unknown-connector",
        selected_exchange: "Binance",
        connector_backend: "unknown backend",
        indicator_source: "Binance spot",
        expected_owned: false,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "non-native-indicator",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-spot",
        indicator_source: "TradingView",
        expected_owned: false,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "indicator-key-alias",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-spot",
        indicator_source: "spot",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "indicator-punctuation-alias",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-spot",
        indicator_source: "Binance/futures",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "empty-indicator",
        selected_exchange: "Binance",
        connector_backend: "binance-sdk-spot",
        indicator_source: "",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "empty-exchange-default",
        selected_exchange: "",
        connector_backend: "binance-sdk-spot",
        indicator_source: "Binance spot",
        expected_owned: true,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "whitespace-exchange-rejected",
        selected_exchange: "   ",
        connector_backend: "binance-sdk-spot",
        indicator_source: "Binance spot",
        expected_owned: false,
    },
    PythonNativeRuntimeRoutingReferenceCase {
        name: "exchange-display-badge-rejected",
        selected_exchange: "Binance (official)",
        connector_backend: "binance-sdk-spot",
        indicator_source: "Binance spot",
        expected_owned: false,
    },
];
    pub const PYTHON_NATIVE_RUNTIME_ROUTING_JSON_COERCION_REFERENCE_JSON: &str = "[{\"config\":{\"connector_backend\":1,\"indicator_source\":\"Binance spot\",\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"numeric-connector\"},{\"config\":{\"connector_backend\":[],\"indicator_source\":\"Binance spot\",\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"empty-connector-list\"},{\"config\":{\"connector_backend\":[\"binance-sdk-spot\"],\"indicator_source\":\"Binance spot\",\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"nonempty-connector-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":1},\"expected_owned\":false,\"name\":\"numeric-exchange\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":[]},\"expected_owned\":true,\"name\":\"empty-exchange-list-default\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":[\"Binance\"]},\"expected_owned\":false,\"name\":\"nonempty-exchange-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":1,\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"numeric-indicator\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":false,\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"false-indicator\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":null,\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"null-indicator\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":[],\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"empty-indicator-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":[0],\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"numeric-first-indicator-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":false},\"expected_owned\":true,\"name\":\"false-exchange-default\"}]";

    pub struct PythonNativeRuntimeModeReferenceCase {
    pub name: &'static str,
    pub input: &'static str,
    pub expected_testnet: bool,
}

pub const PYTHON_NATIVE_RUNTIME_MODE_REFERENCE_CASES: &[PythonNativeRuntimeModeReferenceCase] = &[
    PythonNativeRuntimeModeReferenceCase {
        name: "empty-live",
        input: "",
        expected_testnet: false,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "live",
        input: "Live",
        expected_testnet: false,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "production",
        input: "Production",
        expected_testnet: false,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "demo",
        input: "Demo",
        expected_testnet: true,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "demo-testnet",
        input: "Demo/Testnet",
        expected_testnet: true,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "testnet",
        input: "Testnet",
        expected_testnet: true,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "sandbox",
        input: "Sandbox",
        expected_testnet: true,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "embedded-test-marker",
        input: "contest",
        expected_testnet: true,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "embedded-demo-marker",
        input: "my-demo-mode",
        expected_testnet: true,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "paper-local",
        input: "Paper Local",
        expected_testnet: false,
    },
    PythonNativeRuntimeModeReferenceCase {
        name: "trimmed-testnet",
        input: "  Testnet  ",
        expected_testnet: true,
    },
];
    pub const PYTHON_ORDER_SIZING_REFERENCE_JSON: &str = "{\"cases\":[{\"expected_error\":null,\"expected_quantity\":0.05,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"market\":\"spot\",\"name\":\"spot_min_notional_bump\",\"price\":100.0,\"quantity\":0.023},{\"expected_error\":null,\"expected_quantity\":0.05,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"market\":\"futures\",\"name\":\"futures_min_notional_bump\",\"price\":100.0,\"quantity\":0.023},{\"expected_error\":\"qty<=0\",\"expected_quantity\":0.0,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"market\":\"spot\",\"name\":\"spot_rejects_zero_quantity\",\"price\":100.0,\"quantity\":0.0},{\"expected_error\":\"filters_error: stepSize must be a finite non-negative number\",\"expected_quantity\":0.0,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":-0.01},\"market\":\"futures\",\"name\":\"futures_invalid_step_filter\",\"price\":100.0,\"quantity\":1.0},{\"balance\":100.0,\"expected_percent\":1.0,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"leverage\":5.0,\"market\":\"futures\",\"name\":\"futures_required_percent\",\"price\":100.0}],\"rounding_cases\":[{\"decimals\":2,\"expected_ceil\":1.24,\"expected_floor\":1.23,\"name\":\"positive_decimal\",\"value\":1.231},{\"decimals\":2,\"expected_ceil\":-1.24,\"expected_floor\":-1.23,\"name\":\"negative_decimal\",\"value\":-1.231},{\"decimals\":0,\"expected_ceil\":-2.0,\"expected_floor\":-1.0,\"name\":\"negative_integer_precision\",\"value\":-1.9}],\"schema_version\":1}";
    pub const PYTHON_ORDER_INTENT_REFERENCE_JSON: &str = "{\"cases\":[{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":true,\"market\":\"futures\",\"order_type\":\"MARKET\",\"position_side\":\"\",\"price\":null,\"quantity\":null,\"reduce_only\":false,\"side\":\"SELL\",\"symbol\":\"BTCUSDT\"},\"intent_errors\":[]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":100.0,\"market\":\"futures\",\"name\":\"canonical-close-position\",\"params\":{\"closePosition\":\"true\",\"side\":\"SELL\",\"symbol\":\"BTCUSDT\",\"type\":\"MARKET\"}},{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":false,\"market\":\"futures\",\"order_type\":\"MARKET\",\"position_side\":\"\",\"price\":null,\"quantity\":0.001,\"reduce_only\":false,\"side\":\"SELL\",\"symbol\":\"BTCUSDT\"},\"intent_errors\":[]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":100.0,\"market\":\"futures\",\"name\":\"python-intent-y-is-false-filter-y-is-true\",\"params\":{\"closePosition\":\"y\",\"quantity\":\"0.001\",\"side\":\"SELL\",\"symbol\":\"BTCUSDT\",\"type\":\"MARKET\"}},{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":true,\"market\":\"futures\",\"order_type\":\"LIMIT\",\"position_side\":\"LONG\",\"price\":2000.0,\"quantity\":1.0,\"reduce_only\":true,\"side\":\"BUY\",\"symbol\":\"ETHUSDT\"},\"intent_errors\":[\"closePosition and reduceOnly cannot be used together\"]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":2000.0,\"market\":\"futures\",\"name\":\"canonical-aliases-and-conflicting-flags\",\"params\":{\"close_position\":\"yes\",\"position_side\":\"long\",\"price\":\"2000\",\"quantity\":\"1\",\"reduce_only\":\"on\",\"side\":\"BUY\",\"symbol\":\"ETHUSDT\",\"type\":\"LIMIT\"}},{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":true,\"market\":\"spot\",\"order_type\":\"MARKET\",\"position_side\":\"LONG\",\"price\":null,\"quantity\":null,\"reduce_only\":true,\"side\":\"BUY\",\"symbol\":\"ETHUSDT\"},\"intent_errors\":[\"positionSide is only supported for futures\",\"closePosition orders are only supported for futures\",\"reduceOnly orders are only supported for futures\",\"closePosition and reduceOnly cannot be used together\",\"order quantity must be > 0\"]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":2000.0,\"market\":\"spot\",\"name\":\"spot-rejects-futures-flags\",\"params\":{\"closePosition\":\"true\",\"positionSide\":\"LONG\",\"reduceOnly\":\"true\",\"side\":\"BUY\",\"symbol\":\"ETHUSDT\",\"type\":\"MARKET\"}}],\"schema_version\":1}";
    pub const PYTHON_LIVE_SAFETY_REFERENCE_JSON: &str = "{\"cases\":[{\"expected_errors\":[],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"\",\"api_secret\":\"\",\"config\":{},\"leverage\":0,\"margin_mode\":\"invalid\",\"mode\":\"Demo/Testnet\",\"position_pct\":0.0},\"name\":\"demo-mode-bypasses-live-gates\"},{\"expected_errors\":[\"set live_trading_enabled=true and live_trading_acknowledgement='I_UNDERSTAND_LIVE_TRADING_RISK' or set BOT_ENABLE_LIVE_TRADING=true and BOT_LIVE_TRADING_ACKNOWLEDGEMENT='I_UNDERSTAND_LIVE_TRADING_RISK'\"],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{},\"leverage\":1,\"margin_mode\":\"\",\"mode\":\"Live\",\"position_pct\":2.0},\"name\":\"live-requires-confirmation\"},{\"expected_errors\":[],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":5,\"live_trading_max_position_pct\":3.0,\"live_trading_max_session_orders\":7},\"leverage\":3,\"margin_mode\":\"Isolated\",\"mode\":\"Live\",\"position_pct\":2.0},\"name\":\"live-safe-futures\"},{\"expected_errors\":[\"position_pct 4% exceeds live cap 3%\"],\"input\":{\"account_type\":\"Spot\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":5,\"live_trading_max_position_pct\":3.0,\"live_trading_max_session_orders\":7},\"leverage\":0,\"margin_mode\":\"invalid-is-ignored-for-spot\",\"mode\":\"Live\",\"position_pct\":4.0},\"name\":\"live-spot-position-cap\"},{\"expected_errors\":[\"live_trading_max_leverage must be between 1 and 125\",\"live_trading_max_position_pct must be > 0 and <= 100\",\"live_trading_max_session_orders must be between 1 and 100000\",\"position_pct must be > 0 and <= 100 for live trading\",\"leverage 130 exceeds live cap 126\",\"margin_mode must be Isolated or Cross for live futures trading\"],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":126,\"live_trading_max_position_pct\":0.0,\"live_trading_max_session_orders\":0},\"leverage\":130,\"margin_mode\":\"Portfolio\",\"mode\":\"Production\",\"position_pct\":0.0},\"name\":\"live-invalid-caps-and-futures-controls\"},{\"expected_errors\":[\"provide non-placeholder Binance API credentials\"],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"your_api_key\",\"api_secret\":\"testnet\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":5,\"live_trading_max_position_pct\":3.0,\"live_trading_max_session_orders\":7},\"leverage\":1,\"margin_mode\":\"Cross\",\"mode\":\"Live\",\"position_pct\":2.0},\"name\":\"live-rejects-placeholder-credentials\"}],\"schema_version\":1}";
    pub const PYTHON_CONNECTOR_HEALTH_REFERENCE_JSON: &str = "{\"cases\":[{\"expected_errors\":[\"connector health snapshot missing state\"],\"name\":\"missing-state\",\"snapshot\":{\"health\":\"ok\",\"state\":\"\"}},{\"expected_errors\":[\"connector health snapshot missing health\"],\"name\":\"missing-health\",\"snapshot\":{\"health\":\"\",\"state\":\"ready\"}},{\"expected_errors\":[\"connector health is degraded / paused\"],\"name\":\"not-ready\",\"snapshot\":{\"health\":\"degraded\",\"state\":\"paused\"}},{\"expected_errors\":[\"connector health is degraded\"],\"name\":\"degraded-health\",\"snapshot\":{\"health\":\"degraded\",\"state\":\"ready\"}},{\"expected_errors\":[],\"name\":\"ready-ok\",\"snapshot\":{\"health\":\"ok\",\"state\":\"ready\"}},{\"expected_errors\":[],\"name\":\"ready-unknown\",\"snapshot\":{\"health\":\"unknown\",\"state\":\"ready\"}}],\"schema_version\":1}";
    pub const PYTHON_LLM_OUTPUT_POLICY_REFERENCE_JSON: &str = "{\"cases\":[{\"expected_violations\":[\"order_execution_claim\",\"direct_order_action\"],\"name\":\"structured-order-and-status\",\"text\":\"{\\\"action\\\":\\\"place_order\\\",\\\"status\\\":\\\"executed\\\"}\"},{\"expected_violations\":[\"order_execution_claim\",\"risk_override\"],\"name\":\"natural-order-and-risk\",\"text\":\"I executed the trade and disabled stop loss.\"},{\"expected_violations\":[\"direct_order_action\"],\"name\":\"fenced-direct-order\",\"text\":\"```json\\n{\\\"tool\\\":\\\"submit_order\\\",\\\"symbol\\\":\\\"BTCUSDT\\\"}\\n```\"},{\"expected_violations\":[\"direct_order_action\",\"risk_override\"],\"name\":\"structured-command-and-risk\",\"text\":\"prefix {\\\"command\\\":\\\"create_order\\\",\\\"disable_stop_loss\\\":true} suffix\"},{\"expected_violations\":[\"order_execution_claim\",\"direct_order_action\",\"risk_override\"],\"name\":\"all-policy-categories\",\"text\":\"Order executed; place_order; disable stop loss.\"},{\"expected_violations\":[],\"name\":\"structured-advice\",\"text\":\"{\\\"action\\\":\\\"advise\\\",\\\"recommendation\\\":\\\"wait\\\",\\\"risk\\\":\\\"keep stop loss enabled\\\"}\"}],\"schema_version\":1}";
    pub const PYTHON_LLM_CHAT_REQUEST_REFERENCE_JSON: &str = "{\"cases\":[{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"gpt-5.5\",\"llm_provider\":\"openai\",\"llm_reasoning_effort\":\"high\"},\"context\":{\"config\":{\"account_type\":\"futures\",\"intervals\":[\"1m\"],\"llm\":{\"llm_api_key\":null,\"token\":\"secret-token\"},\"mode\":\"Live\",\"selected_exchange\":\"Binance\",\"symbols\":[\"BTCUSDT\",\"ETHUSDT\"]},\"logs\":[{\"message\":\"api_key=secret\"}],\"portfolio\":{\"active_pnl\":12.5,\"closed_pnl\":null,\"open_position_records\":{\"BTCUSDT:L\":{\"secret\":\"raw\"}}},\"runtime\":{\"control_plane\":\"python\",\"phase\":\"running\"}},\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Authorization\":\"Bearer parity-test-key\",\"Content-Type\":\"application/json\"},\"json\":{\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Be concise\",\"role\":\"system\"},{\"content\":\"Trading context JSON: {\\\"config_summary\\\":{\\\"account_type\\\":\\\"futures\\\",\\\"interval_count\\\":1,\\\"llm\\\":{\\\"llm_api_key\\\":\\\"\\\",\\\"token\\\":\\\"<redacted>\\\"},\\\"mode\\\":\\\"Live\\\",\\\"raw_config_redacted\\\":true,\\\"selected_exchange\\\":\\\"Binance\\\",\\\"symbol_count\\\":2},\\\"execution\\\":{},\\\"logs\\\":{\\\"count\\\":1,\\\"redacted\\\":true},\\\"portfolio_summary\\\":{\\\"active_pnl\\\":12.5,\\\"closed_pnl\\\":null,\\\"closed_position_count\\\":0,\\\"open_position_count\\\":1,\\\"position_records_redacted\\\":true},\\\"privacy_notice\\\":\\\"Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.\\\",\\\"runtime\\\":{\\\"control_plane\\\":\\\"python\\\",\\\"phase\\\":\\\"running\\\"},\\\"status\\\":{}}\",\"role\":\"system\"},{\"content\":\"Summarize risk\",\"role\":\"user\"}],\"model\":\"gpt-5.5\",\"reasoning_effort\":\"high\"},\"mode\":\"cloud\",\"protocol\":\"openai-chat-completions\",\"provider\":\"openai\",\"url\":\"https://api.openai.com/v1/chat/completions\"},\"name\":\"openai-cloud-context-and-reasoning\",\"prompt\":\"Summarize risk\",\"system_prompt\":\"Be concise\"},{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"qwen3.7-max\",\"llm_provider\":\"qwen\",\"llm_reasoning_effort\":\"enabled\"},\"context\":null,\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Authorization\":\"Bearer parity-test-key\",\"Content-Type\":\"application/json\"},\"json\":{\"enable_thinking\":true,\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Explain the signal\",\"role\":\"user\"}],\"model\":\"qwen3.7-max\"},\"mode\":\"cloud\",\"protocol\":\"openai-chat-completions\",\"provider\":\"qwen\",\"url\":\"https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions\"},\"name\":\"qwen-thinking-option\",\"prompt\":\"Explain the signal\",\"system_prompt\":\"\"},{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"claude-sonnet-4-5-20250929\",\"llm_provider\":\"anthropic\",\"llm_reasoning_effort\":\"high\"},\"context\":null,\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\",\"anthropic-version\":\"2023-06-01\",\"x-api-key\":\"parity-test-key\"},\"json\":{\"max_tokens\":9216,\"messages\":[{\"content\":\"Summarize the trade plan\",\"role\":\"user\"}],\"model\":\"claude-sonnet-4-5-20250929\",\"system\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\\n\\nKeep the answer advisory\",\"thinking\":{\"budget_tokens\":8192,\"type\":\"enabled\"}},\"mode\":\"cloud\",\"protocol\":\"anthropic-messages\",\"provider\":\"anthropic\",\"url\":\"https://api.anthropic.com/v1/messages\"},\"name\":\"anthropic-high-thinking\",\"prompt\":\"Summarize the trade plan\",\"system_prompt\":\"Keep the answer advisory\"},{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"gemini-3-pro-preview\",\"llm_provider\":\"gemini\",\"llm_reasoning_effort\":\"medium\"},\"context\":null,\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\"},\"json\":{\"contents\":[{\"parts\":[{\"text\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\"},{\"text\":\"Explain the risk\"}]}],\"generationConfig\":{\"thinkingConfig\":{\"thinkingLevel\":\"high\"}}},\"mode\":\"cloud\",\"protocol\":\"gemini-generate-content\",\"provider\":\"gemini\",\"url\":\"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-preview:generateContent?key=parity-test-key\"},\"name\":\"gemini-pro-thinking-level\",\"prompt\":\"Explain the risk\",\"system_prompt\":\"\"},{\"config\":{\"llm_allow_public_network\":true,\"llm_base_url\":\"https://llm.example.test/v1\",\"llm_model\":\"RWKV/rwkv-6-world\",\"llm_provider\":\"open-source\",\"llm_reasoning_effort\":\"disabled\"},\"context\":{\"config\":{\"api_key\":\"exchange-secret\",\"symbols\":[\"BTCUSDT\"]},\"custom\":{\"local_detail\":\"must-not-leave-private-runtime\"},\"logs\":[{\"message\":\"Bearer private-secret\"}],\"runtime\":{\"phase\":\"running\"}},\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\"},\"json\":{\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Trading context JSON: {\\\"config_summary\\\":{\\\"account_type\\\":null,\\\"interval_count\\\":0,\\\"llm\\\":{},\\\"mode\\\":null,\\\"raw_config_redacted\\\":true,\\\"selected_exchange\\\":null,\\\"symbol_count\\\":1},\\\"execution\\\":{},\\\"logs\\\":{\\\"count\\\":1,\\\"redacted\\\":true},\\\"portfolio_summary\\\":{\\\"active_pnl\\\":null,\\\"closed_pnl\\\":null,\\\"closed_position_count\\\":0,\\\"open_position_count\\\":0,\\\"position_records_redacted\\\":true},\\\"privacy_notice\\\":\\\"Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.\\\",\\\"runtime\\\":{\\\"phase\\\":\\\"running\\\"},\\\"status\\\":{}}\",\"role\":\"system\"},{\"content\":\"Explain the risk\",\"role\":\"user\"}],\"model\":\"RWKV/rwkv-6-world\",\"reasoning_effort\":\"disabled\"},\"mode\":\"local\",\"protocol\":\"openai-chat-completions\",\"provider\":\"open-source\",\"url\":\"https://llm.example.test/v1/chat/completions\"},\"name\":\"open-source-public-endpoint-privacy\",\"prompt\":\"Explain the risk\",\"system_prompt\":\"\"},{\"config\":{\"llm_model\":\"Qwen/Qwen3-8B\",\"llm_provider\":\"local\",\"llm_reasoning_effort\":\"extra-high\"},\"context\":{\"custom\":{\"local_detail\":\"kept-on-loopback\"}},\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\"},\"json\":{\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Trading context JSON: {\\\"custom\\\":{\\\"local_detail\\\":\\\"kept-on-loopback\\\"}}\",\"role\":\"system\"},{\"content\":\"Explain the risk\",\"role\":\"user\"}],\"model\":\"Qwen/Qwen3-8B\",\"reasoning_effort\":\"xhigh\"},\"mode\":\"local\",\"protocol\":\"openai-chat-completions\",\"provider\":\"local\",\"url\":\"http://127.0.0.1:11434/v1/chat/completions\"},\"name\":\"local-open-source-endpoint\",\"prompt\":\"Explain the risk\",\"system_prompt\":\"\"}],\"schema_version\":1}";
    pub const PYTHON_SOURCE_CONTRACT_HASH: &str = "d3b37c88dbdad85a4d3c9ef21b47bd26f42e5cbc4ec9f91c31f5a0f61897a83e";
    pub const CPP_CONTRACT_PARITY_READY: bool = true;
    pub const RUST_CONTRACT_PARITY_READY: bool = true;
    pub const CPP_STANDALONE_RUNTIME_READY: bool = false;
    pub const RUST_STANDALONE_RUNTIME_READY: bool = false;
    pub const CPP_FULL_PARITY_READY: bool = false;
    pub const RUST_FULL_PARITY_READY: bool = false;
    pub const PYTHON_ORDER_GUARD_BEHAVIOR_JSON: &str = "{\"environment_bool_true_values\":[\"1\",\"true\",\"yes\",\"on\"],\"live_only_requirements\":[\"credentials\",\"live_acknowledgement\",\"session_order_cap\",\"session_order_count_increment\"],\"live_safety_environment\":{\"acknowledgement\":\"BOT_LIVE_TRADING_ACKNOWLEDGEMENT\",\"enabled\":\"BOT_ENABLE_LIVE_TRADING\",\"legacy_acknowledgement\":\"BOT_LIVE_TRADING_ACK\",\"max_leverage\":\"BOT_LIVE_MAX_LEVERAGE\",\"max_position_pct\":\"BOT_LIVE_MAX_POSITION_PCT\",\"max_session_orders\":\"BOT_LIVE_MAX_SESSION_ORDERS\"},\"validate_audit_enabled_all_modes\":true,\"validate_audit_writable_all_modes\":true,\"validate_connector_health_all_modes\":true,\"validate_exchange_filters_all_modes\":true,\"validate_intent_all_modes\":true}";
    pub const PYTHON_LIVE_TRADING_ENABLED_ENV: &str = "BOT_ENABLE_LIVE_TRADING";
    pub const PYTHON_LIVE_TRADING_ACK_ENV: &str = "BOT_LIVE_TRADING_ACKNOWLEDGEMENT";
    pub const PYTHON_LIVE_TRADING_ACK_ENV_LEGACY: &str = "BOT_LIVE_TRADING_ACK";
    pub const PYTHON_LIVE_TRADING_MAX_LEVERAGE_ENV: &str = "BOT_LIVE_MAX_LEVERAGE";
    pub const PYTHON_LIVE_TRADING_MAX_POSITION_PCT_ENV: &str = "BOT_LIVE_MAX_POSITION_PCT";
    pub const PYTHON_LIVE_TRADING_MAX_SESSION_ORDERS_ENV: &str = "BOT_LIVE_MAX_SESSION_ORDERS";
    pub const PYTHON_LIVE_SAFETY_ENV_TRUE_VALUES: &[&str] = &[
    "1",
    "true",
    "yes",
    "on",
];
    pub const PYTHON_NATIVE_RUNTIME_EXCHANGES: &[&str] = &[
    "Binance",
];
    pub const PYTHON_NATIVE_RUNTIME_CONNECTOR_BACKENDS: &[&str] = &[
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
];
    pub const PYTHON_NATIVE_RUNTIME_MARKET_FAMILIES: &[&str] = &[
    "usd-m-futures",
    "coin-m-futures",
    "spot",
];
    pub const PYTHON_NATIVE_RUNTIME_EXECUTION_SCOPE: &str = "binance-spot-usds-and-coin-futures";
    pub const PYTHON_NATIVE_RUNTIME_EXECUTION_CAPABILITY: bool = true;
    pub const PYTHON_NATIVE_RUNTIME_CONNECTOR_MARKET_FAMILIES: &[(&str, &str)] = &[
    ("binance-sdk-derivatives-trading-usds-futures", "usd-m-futures"),
    ("binance-sdk-derivatives-trading-coin-futures", "coin-m-futures"),
    ("binance-sdk-spot", "spot"),
    ("binance-connector", "usd-m-futures"),
    ("binance-connector", "spot"),
    ("ccxt", "usd-m-futures"),
    ("ccxt", "spot"),
    ("python-binance", "usd-m-futures"),
    ("python-binance", "spot"),
];
    pub const PYTHON_NATIVE_RUNTIME_INDICATOR_SOURCE_MARKET_FAMILIES: &[(&str, &str)] = &[
    ("binance_spot", "spot"),
    ("binance_futures", "usd-m-futures"),
    ("spot", "spot"),
    ("futures", "usd-m-futures"),
];
    pub const PYTHON_NATIVE_RUNTIME_TESTNET_MODE_MARKERS: &[&str] = &[
    "demo",
    "test",
    "sandbox",
];
    pub const PYTHON_NATIVE_RUNTIME_DELEGATED_OWNER: &str = "Python Service API/provider connector";
    pub const PYTHON_ORDER_GUARD_VALIDATE_INTENT_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_EXCHANGE_FILTERS_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_CONNECTOR_HEALTH_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_AUDIT_ENABLED_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_VALIDATE_AUDIT_WRITABLE_ALL_MODES: bool = true;
    pub const PYTHON_ORDER_GUARD_LIVE_ONLY_REQUIREMENTS: &[&str] = &[
    "credentials",
    "live_acknowledgement",
    "session_order_cap",
    "session_order_count_increment",
];

    pub struct PythonParityDomain {
    pub key: &'static str,
    pub title: &'static str,
    pub python_surface: &'static str,
    pub cpp_status: &'static str,
    pub rust_status: &'static str,
    pub required_before_full_parity: &'static str,
    pub cpp_full_parity: bool,
    pub rust_full_parity: bool,
}

pub const PYTHON_PARITY_DOMAINS: &[PythonParityDomain] = &[
    PythonParityDomain {
        key: "desktop_shell_and_tabs",
        title: "Desktop shell and primary tabs",
        python_surface: "Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "service_api_contract",
        title: "Service API contract",
        python_surface: "Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "config_persistence",
        title: "Config persistence and hydration",
        python_surface: "Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "strategy_runtime",
        title: "Strategy runtime and signal generation",
        python_surface: "Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "exchange_connectors",
        title: "Exchange connectors and market data",
        python_surface: "Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "account_portfolio_positions",
        title: "Account, portfolio, and positions",
        python_surface: "Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "order_execution_and_risk",
        title: "Order execution, audit, and risk",
        python_surface: "Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "backtest_engine",
        title: "Backtest engine, optimizer, and scanner",
        python_surface: "Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "charts_and_heatmaps",
        title: "Charts and liquidation heatmaps",
        python_surface: "TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "logs_terminal_diagnostics",
        title: "Logs, terminal, and diagnostics",
        python_surface: "Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "llm_advisory",
        title: "LLM advisory and local model lifecycle",
        python_surface: "Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
    PythonParityDomain {
        key: "startup_packaging_platform",
        title: "Startup, packaging, and platform integration",
        python_surface: "Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.",
        cpp_status: "Complete",
        rust_status: "Complete",
        required_before_full_parity: "C++: Complete | Rust: Complete",
        cpp_full_parity: true,
        rust_full_parity: true,
    },
];

    pub const PYTHON_PARITY_DOMAIN_KEYS: &[&str] = &[
    "desktop_shell_and_tabs",
    "service_api_contract",
    "config_persistence",
    "strategy_runtime",
    "exchange_connectors",
    "account_portfolio_positions",
    "order_execution_and_risk",
    "backtest_engine",
    "charts_and_heatmaps",
    "logs_terminal_diagnostics",
    "llm_advisory",
    "startup_packaging_platform",
];

    pub const PYTHON_REMOTE_SERVICE_CONFIG_PROTECTED_FIELDS: &[&str] = &[
    "api_key",
    "api_secret",
    "connector_order_circuit_incident_log_path",
    "llm_api_key",
    "order_audit_log_path",
];

    pub const PYTHON_SERVICE_ROUTE_NAMES: &[&str] = &[
    "runtime",
    "dashboard",
    "status",
    "metrics",
    "prometheus_metrics",
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
    "position_close",
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
    "stream_dashboard",
];

    pub struct PythonServiceRoute {
    pub name: &'static str,
    pub path: &'static str,
    pub methods: &'static [&'static str],
}

pub const PYTHON_SERVICE_ROUTES: &[PythonServiceRoute] = &[
    PythonServiceRoute {
        name: "runtime",
        path: "/api/v1/runtime",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "dashboard",
        path: "/api/v1/dashboard",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "status",
        path: "/api/v1/status",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "metrics",
        path: "/api/v1/metrics",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "prometheus_metrics",
        path: "/api/v1/metrics/prometheus",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "execution",
        path: "/api/v1/execution",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "backtest",
        path: "/api/v1/backtest",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "config_summary",
        path: "/api/v1/config-summary",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "config",
        path: "/api/v1/config",
        methods: &["GET", "PUT", "PATCH"],
    },
    PythonServiceRoute {
        name: "config_persistence",
        path: "/api/v1/config/persistence",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "config_save",
        path: "/api/v1/config/save",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "config_load",
        path: "/api/v1/config/load",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "runtime_state",
        path: "/api/v1/runtime/state",
        methods: &["PUT"],
    },
    PythonServiceRoute {
        name: "operational_preflight",
        path: "/api/v1/runtime/operational-preflight",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "control_start",
        path: "/api/v1/control/start",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "control_stop",
        path: "/api/v1/control/stop",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "position_close",
        path: "/api/v1/positions/close",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "control_start_failed",
        path: "/api/v1/control/start-failed",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "connector_order_circuit_breaker",
        path: "/api/v1/runtime/connector-order-circuit-breaker",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "connector_order_circuit_breaker_reset",
        path: "/api/v1/runtime/connector-order-circuit-breaker/reset",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "connector_order_circuit_incidents",
        path: "/api/v1/runtime/connector-order-circuit-breaker/incidents",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "backtest_run",
        path: "/api/v1/backtest/run",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "backtest_stop",
        path: "/api/v1/backtest/stop",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "account",
        path: "/api/v1/account",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "portfolio",
        path: "/api/v1/portfolio",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "exchange_connector",
        path: "/api/v1/exchange/connector",
        methods: &["GET", "PUT"],
    },
    PythonServiceRoute {
        name: "logs",
        path: "/api/v1/logs",
        methods: &["GET", "POST"],
    },
    PythonServiceRoute {
        name: "terminal_run",
        path: "/api/v1/terminal/run",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_providers",
        path: "/api/v1/llm/providers",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "llm_config",
        path: "/api/v1/llm/config",
        methods: &["GET", "PATCH"],
    },
    PythonServiceRoute {
        name: "llm_prompt",
        path: "/api/v1/llm/prompt",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_local_model_status",
        path: "/api/v1/llm/local-model/status",
        methods: &["GET"],
    },
    PythonServiceRoute {
        name: "llm_local_model_start",
        path: "/api/v1/llm/local-model/start",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_local_model_pull",
        path: "/api/v1/llm/local-model/pull",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "llm_local_model_delete",
        path: "/api/v1/llm/local-model/delete",
        methods: &["POST"],
    },
    PythonServiceRoute {
        name: "stream_dashboard",
        path: "/api/v1/stream/dashboard",
        methods: &["GET"],
    },
];

    pub struct PythonServiceRouteSchema {
    pub name: &'static str,
    pub query_fields: &'static [&'static str],
    pub request_fields: &'static [&'static str],
    pub response_fields: &'static [&'static str],
}

pub const PYTHON_SERVICE_ROUTE_SCHEMAS: &[PythonServiceRouteSchema] = &[
    PythonServiceRouteSchema {
        name: "runtime",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["service_name", "phase", "python_entrypoint", "desktop_entrypoint", "repo_root", "platform", "python_version", "capabilities", "control_plane", "notes"],
    },
    PythonServiceRouteSchema {
        name: "dashboard",
        query_fields: &["log_limit", "incident_limit"],
        request_fields: &[],
        response_fields: &["runtime", "status", "operational", "config", "config_summary", "config_persistence", "execution", "backtest", "account", "portfolio", "logs", "service_api", "connector_order_circuit_incidents"],
    },
    PythonServiceRouteSchema {
        name: "status",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["state", "lifecycle_phase", "requested_action", "close_positions_requested", "status_message", "last_transition_at", "service_mode", "generated_at", "api_enabled", "docker_required", "runtime_source", "active_engine_count", "account_type", "mode", "selected_exchange", "connector_backend", "connector_health", "exchange_connector", "operational_health", "operational", "notes"],
    },
    PythonServiceRouteSchema {
        name: "metrics",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["generated_at", "operational_health", "connector_health", "connector_state", "runtime_active", "active_engine_count", "log_warning_count", "log_error_count", "connector_order_circuit_open", "unresolved_order_intent_count"],
    },
    PythonServiceRouteSchema {
        name: "prometheus_metrics",
        query_fields: &[],
        request_fields: &[],
        response_fields: &[],
    },
    PythonServiceRouteSchema {
        name: "execution",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["executor_kind", "owner", "state", "workload_kind", "session_id", "requested_job_count", "active_engine_count", "progress_label", "progress_percent", "heartbeat_at", "tick_count", "last_action", "last_message", "started_at", "updated_at", "source", "notes"],
    },
    PythonServiceRouteSchema {
        name: "backtest",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["session_id", "state", "workload_kind", "status_message", "symbols", "intervals", "indicator_keys", "logic", "symbol_source", "capital", "run_count", "error_count", "cancelled", "started_at", "completed_at", "updated_at", "source", "top_run", "runs", "top_runs", "errors"],
    },
    PythonServiceRouteSchema {
        name: "config_summary",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["mode", "account_type", "connector_backend", "selected_exchange", "code_language", "theme", "design", "api_credentials_present", "symbol_count", "interval_count", "enabled_indicator_count", "runtime_pair_count", "backtest_pair_count", "llm_enabled", "llm_provider", "llm_mode", "llm_api_key_present"],
    },
    PythonServiceRouteSchema {
        name: "config",
        query_fields: &[],
        request_fields: &["config"],
        response_fields: &["mode", "account_type", "margin_mode", "position_mode", "side", "leverage", "position_pct", "connector_backend", "selected_exchange", "code_language", "theme", "design", "order_audit_max_bytes", "order_audit_backup_count", "connector_order_circuit_incident_log_max_bytes", "connector_order_circuit_incident_log_backup_count", "operational_connector_snapshot_stale_seconds", "operational_execution_heartbeat_stale_seconds", "operational_account_snapshot_stale_seconds", "operational_portfolio_snapshot_stale_seconds", "operational_live_start_gate_enabled", "operational_live_order_gate_enabled", "live_allow_auto_bump_to_min_order", "symbols", "intervals", "api_credentials_present", "llm", "exchange_support"],
    },
    PythonServiceRouteSchema {
        name: "config_persistence",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["path", "exists", "modified_at", "kind", "format_version", "loaded", "dirty", "last_loaded_at", "last_saved_at", "migrated_from_format_version"],
    },
    PythonServiceRouteSchema {
        name: "config_save",
        query_fields: &[],
        request_fields: &["path", "source", "allow_unsafe_path"],
        response_fields: &["path", "exists", "modified_at", "kind", "format_version", "loaded", "dirty", "last_loaded_at", "last_saved_at", "migrated_from_format_version"],
    },
    PythonServiceRouteSchema {
        name: "config_load",
        query_fields: &[],
        request_fields: &["path", "source", "allow_unsafe_path"],
        response_fields: &["config", "persistence"],
    },
    PythonServiceRouteSchema {
        name: "runtime_state",
        query_fields: &[],
        request_fields: &["active", "active_engine_count", "source"],
        response_fields: &["state", "lifecycle_phase", "requested_action", "close_positions_requested", "status_message", "last_transition_at", "service_mode", "generated_at", "api_enabled", "docker_required", "runtime_source", "active_engine_count", "account_type", "mode", "selected_exchange", "connector_backend", "connector_health", "exchange_connector", "operational_health", "operational", "notes"],
    },
    PythonServiceRouteSchema {
        name: "operational_preflight",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["state", "message", "mode", "live_mode", "generated_at", "start", "orders", "freshness", "critical_stale", "reasons"],
    },
    PythonServiceRouteSchema {
        name: "control_start",
        query_fields: &[],
        request_fields: &["requested_job_count", "source"],
        response_fields: &["accepted", "action", "lifecycle_phase", "runtime_active", "active_engine_count", "requested_job_count", "close_positions_requested", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "control_stop",
        query_fields: &[],
        request_fields: &["close_positions", "source"],
        response_fields: &["accepted", "action", "lifecycle_phase", "runtime_active", "active_engine_count", "requested_job_count", "close_positions_requested", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "position_close",
        query_fields: &[],
        request_fields: &["symbol", "side_key", "interval", "quantity", "target_identity", "confirm_close", "source"],
        response_fields: &["accepted", "action", "symbol", "side_key", "interval", "quantity", "target_identity", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "control_start_failed",
        query_fields: &[],
        request_fields: &["reason", "source"],
        response_fields: &["accepted", "action", "lifecycle_phase", "runtime_active", "active_engine_count", "requested_job_count", "close_positions_requested", "source", "status_message", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "connector_order_circuit_breaker",
        query_fields: &[],
        request_fields: &["snapshot", "source", "force"],
        response_fields: &["active", "state", "reason", "message", "block_count", "block_threshold", "block_window_seconds", "tripped_at", "cleared_at", "source", "symbol", "interval", "side", "account_type", "connector_health", "connector_state", "reset_blocked", "reset_blocked_reason", "reset_blocked_at", "recovery_pending", "recovery_pending_reason", "last_event", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "connector_order_circuit_breaker_reset",
        query_fields: &[],
        request_fields: &["snapshot", "source", "force"],
        response_fields: &["active", "state", "reason", "message", "block_count", "block_threshold", "block_window_seconds", "tripped_at", "cleared_at", "source", "symbol", "interval", "side", "account_type", "connector_health", "connector_state", "reset_blocked", "reset_blocked_reason", "reset_blocked_at", "recovery_pending", "recovery_pending_reason", "last_event", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "connector_order_circuit_incidents",
        query_fields: &["limit"],
        request_fields: &[],
        response_fields: &["path", "path_source", "configured_path", "max_bytes", "backup_count", "exists", "limit", "count", "total_read", "events", "parse_errors", "last_event", "error"],
    },
    PythonServiceRouteSchema {
        name: "backtest_run",
        query_fields: &[],
        request_fields: &["request", "source"],
        response_fields: &["accepted", "action", "session_id", "state", "status_message", "source"],
    },
    PythonServiceRouteSchema {
        name: "backtest_stop",
        query_fields: &[],
        request_fields: &["source"],
        response_fields: &["accepted", "action", "session_id", "state", "status_message", "source"],
    },
    PythonServiceRouteSchema {
        name: "account",
        query_fields: &[],
        request_fields: &["total_balance", "available_balance", "source"],
        response_fields: &["account_type", "mode", "selected_exchange", "connector_backend", "balance_currency", "total_balance", "available_balance", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "portfolio",
        query_fields: &[],
        request_fields: &["open_position_records", "closed_position_records", "closed_trade_registry", "active_pnl", "active_margin", "closed_pnl", "closed_margin", "total_balance", "available_balance", "source"],
        response_fields: &["account_type", "open_position_count", "closed_position_count", "active_pnl", "active_margin", "closed_pnl", "closed_margin", "total_balance", "available_balance", "positions", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "exchange_connector",
        query_fields: &[],
        request_fields: &["snapshot", "source"],
        response_fields: &["health", "state", "generated_at", "source", "selected_exchange", "connector_backend", "selected_forex_broker", "account_type", "mode", "support", "rate_limit", "network", "last_error", "attention", "order_audit", "order_intents"],
    },
    PythonServiceRouteSchema {
        name: "logs",
        query_fields: &["limit"],
        request_fields: &["message", "source", "level"],
        response_fields: &["sequence_id", "level", "message", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "terminal_run",
        query_fields: &[],
        request_fields: &["command", "source"],
        response_fields: &["command", "exit_code", "output", "source", "generated_at"],
    },
    PythonServiceRouteSchema {
        name: "llm_providers",
        query_fields: &[],
        request_fields: &[],
        response_fields: &["key", "label", "mode", "protocol", "default_base_url", "default_model", "api_key_env", "model_suggestions", "reasoning_efforts", "default_reasoning_effort", "catalog_revision", "catalog_path", "custom_models_env", "custom_models_path_env", "catalog_note", "notes"],
    },
    PythonServiceRouteSchema {
        name: "llm_config",
        query_fields: &[],
        request_fields: &["config"],
        response_fields: &["enabled", "provider", "provider_label", "mode", "protocol", "catalog_revision", "catalog_path", "custom_models_env", "custom_models_path_env", "model", "base_url", "api_key_env", "api_key_present", "allow_public_network", "use_for", "reasoning_effort", "default_reasoning_effort", "reasoning_efforts", "model_suggestions", "notes", "execution_policy"],
    },
    PythonServiceRouteSchema {
        name: "llm_prompt",
        query_fields: &[],
        request_fields: &["prompt", "system_prompt", "dry_run", "source"],
        response_fields: &["provider", "model", "dry_run", "prompt", "system_prompt", "response", "source"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_status",
        query_fields: &["base_url", "model"],
        request_fields: &[],
        response_fields: &["model", "base_url", "server_kind", "installed", "can_download", "can_start", "available_models", "error", "storage_hint", "storage_paths", "estimated_size_label", "free_disk_gb", "recommended_free_disk_gb", "disk_space_warning"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_start",
        query_fields: &[],
        request_fields: &["base_url", "model", "source"],
        response_fields: &["started", "server_kind", "executable", "error"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_pull",
        query_fields: &[],
        request_fields: &["base_url", "model", "source"],
        response_fields: &["ok", "action", "model", "status"],
    },
    PythonServiceRouteSchema {
        name: "llm_local_model_delete",
        query_fields: &[],
        request_fields: &["base_url", "model", "source"],
        response_fields: &["ok", "action", "model", "status"],
    },
    PythonServiceRouteSchema {
        name: "stream_dashboard",
        query_fields: &["log_limit", "incident_limit", "interval_ms", "max_events"],
        request_fields: &[],
        response_fields: &["event", "data"],
    },
];

    pub const PYTHON_BACKTEST_RUN_REQUEST_FIELDS: &[&str] = &[
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
    "optimizer_max_duration_seconds",
    "optimizer_metric",
    "optimizer_min_trades",
    "optimizer_mode",
    "pair_overrides",
    "position_mode",
    "position_pct",
    "position_pct_units",
    "queue_if_busy",
    "resume_checkpoint",
    "scan_mdd_limit",
    "scan_scope",
    "scan_top_n",
    "side",
    "start",
    "stop_loss",
    "symbol_source",
    "symbols",
];

    pub const PYTHON_INDICATOR_KEYS: &[&str] = &[
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
    "stochastic",
];

    pub struct PythonIndicator {
    pub key: &'static str,
    pub display_name: &'static str,
    pub default_enabled: bool,
    pub runtime_config_json: &'static str,
    pub backtest_config_json: &'static str,
    pub runtime_output_keys: &'static [&'static str],
}

pub const PYTHON_INDICATOR_CATALOG: &[PythonIndicator] = &[
    PythonIndicator {
        key: "ma",
        display_name: "Moving Average (MA)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"type\":\"SMA\"}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"}",
        runtime_output_keys: &["ma"],
    },
    PythonIndicator {
        key: "donchian",
        display_name: "Donchian Channels (DC)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"}",
        runtime_output_keys: &["donchian_high", "donchian_low", "donchian"],
    },
    PythonIndicator {
        key: "psar",
        display_name: "Parabolic SAR (PSAR)",
        default_enabled: false,
        runtime_config_json: "{\"af\":0.02,\"buy_value\":null,\"enabled\":false,\"max_af\":0.2,\"sell_value\":null}",
        backtest_config_json: "{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["psar"],
    },
    PythonIndicator {
        key: "bb",
        display_name: "Bollinger Bands (BB)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2}",
        runtime_output_keys: &["bb_upper", "bb_mid", "bb_lower"],
    },
    PythonIndicator {
        key: "bbw",
        display_name: "Bollinger Band Width (BBW)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}",
        backtest_config_json: "{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2}",
        runtime_output_keys: &["bbw"],
    },
    PythonIndicator {
        key: "keltner",
        display_name: "Keltner Channels (KC)",
        default_enabled: false,
        runtime_config_json: "{\"atr_length\":10,\"buy_value\":null,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":null}",
        backtest_config_json: "{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"}",
        runtime_output_keys: &["keltner_upper", "keltner_mid", "keltner_lower"],
    },
    PythonIndicator {
        key: "ichimoku",
        display_name: "Ichimoku Cloud (IC)",
        default_enabled: false,
        runtime_config_json: "{\"base_length\":26,\"buy_value\":null,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":null,\"span_b_length\":52}",
        backtest_config_json: "{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52}",
        runtime_output_keys: &["ichimoku_tenkan", "ichimoku_kijun", "ichimoku_span_a", "ichimoku_span_b", "ichimoku_chikou", "ichimoku"],
    },
    PythonIndicator {
        key: "rsi",
        display_name: "Relative Strength Index (RSI)",
        default_enabled: true,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":true,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70}",
        runtime_output_keys: &["rsi"],
    },
    PythonIndicator {
        key: "volume",
        display_name: "Volume",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"}",
        runtime_output_keys: &["volume"],
    },
    PythonIndicator {
        key: "obv",
        display_name: "On-Balance Volume (OBV)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"}",
        runtime_output_keys: &["obv"],
    },
    PythonIndicator {
        key: "rvol",
        display_name: "Relative Volume (RVOL)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75}",
        runtime_output_keys: &["rvol"],
    },
    PythonIndicator {
        key: "cmf",
        display_name: "Chaikin Money Flow (CMF)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05}",
        runtime_output_keys: &["cmf"],
    },
    PythonIndicator {
        key: "cci",
        display_name: "Commodity Channel Index (CCI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100}",
        runtime_output_keys: &["cci"],
    },
    PythonIndicator {
        key: "roc",
        display_name: "Rate of Change (ROC)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":12,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0}",
        runtime_output_keys: &["roc"],
    },
    PythonIndicator {
        key: "trix",
        display_name: "Triple Exponential Average (TRIX)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":15,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0}",
        runtime_output_keys: &["trix"],
    },
    PythonIndicator {
        key: "ppo",
        display_name: "Percentage Price Oscillator (PPO)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}",
        runtime_output_keys: &["ppo", "ppo_signal", "ppo_hist"],
    },
    PythonIndicator {
        key: "ao",
        display_name: "Awesome Oscillator (AO)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"fast\":5,\"sell_value\":null,\"slow\":34}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34}",
        runtime_output_keys: &["ao"],
    },
    PythonIndicator {
        key: "kst",
        display_name: "Know Sure Thing (KST)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":null,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}",
        runtime_output_keys: &["kst", "kst_signal", "kst_hist"],
    },
    PythonIndicator {
        key: "aroon",
        display_name: "Aroon Oscillator (AROON)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":25,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50}",
        runtime_output_keys: &["aroon_up", "aroon_down", "aroon"],
    },
    PythonIndicator {
        key: "chop",
        display_name: "Choppiness Index (CHOP)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8}",
        runtime_output_keys: &["chop"],
    },
    PythonIndicator {
        key: "atr",
        display_name: "Average True Range (ATR)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"}",
        runtime_output_keys: &["atr"],
    },
    PythonIndicator {
        key: "natr",
        display_name: "Normalized Average True Range (NATR)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0}",
        runtime_output_keys: &["natr"],
    },
    PythonIndicator {
        key: "vwap",
        display_name: "Volume Weighted Average Price (VWAP)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["vwap"],
    },
    PythonIndicator {
        key: "mfi",
        display_name: "Money Flow Index (MFI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80}",
        runtime_output_keys: &["mfi"],
    },
    PythonIndicator {
        key: "stoch_rsi",
        display_name: "Stochastic RSI (SRSI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}",
        runtime_output_keys: &["stoch_rsi", "stoch_rsi_k", "stoch_rsi_d"],
    },
    PythonIndicator {
        key: "willr",
        display_name: "Williams %R",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20}",
        runtime_output_keys: &["willr"],
    },
    PythonIndicator {
        key: "macd",
        display_name: "Moving Average Convergence/Divergence (MACD)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}",
        runtime_output_keys: &["macd_line", "macd_signal"],
    },
    PythonIndicator {
        key: "uo",
        display_name: "Ultimate Oscillator (UO)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":null,\"short\":7}",
        backtest_config_json: "{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7}",
        runtime_output_keys: &["uo"],
    },
    PythonIndicator {
        key: "adx",
        display_name: "Average Directional Index (ADX)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"}",
        runtime_output_keys: &["adx"],
    },
    PythonIndicator {
        key: "dmi",
        display_name: "Directional Movement Index (DMI)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0}",
        runtime_output_keys: &["dmi_plus", "dmi_minus", "dmi"],
    },
    PythonIndicator {
        key: "supertrend",
        display_name: "SuperTrend (ST)",
        default_enabled: false,
        runtime_config_json: "{\"atr_period\":10,\"buy_value\":null,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":null}",
        backtest_config_json: "{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["supertrend"],
    },
    PythonIndicator {
        key: "ema",
        display_name: "Exponential Moving Average (EMA)",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}",
        backtest_config_json: "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}",
        runtime_output_keys: &["ema"],
    },
    PythonIndicator {
        key: "stochastic",
        display_name: "Stochastic Oscillator",
        default_enabled: false,
        runtime_config_json: "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}",
        backtest_config_json: "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}",
        runtime_output_keys: &["stochastic", "stochastic_k", "stochastic_d"],
    },
];

    pub const PYTHON_LLM_PROVIDER_KEYS: &[&str] = &[
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "mistral",
    "grok",
    "qwen",
    "moonshot",
    "local",
    "ollama",
    "vllm",
    "llamacpp",
    "lmstudio",
    "tgi",
    "open-source",
];

    pub const PYTHON_LLM_PROVIDER_CATALOG_REVISION: &str = "2026-07-16";
    pub const PYTHON_LLM_MODEL_CATALOG_PATH_ENV: &str = "BOT_LLM_MODEL_CATALOG_PATH";

    pub struct PythonLlmProvider {
    pub key: &'static str,
    pub label: &'static str,
    pub mode: &'static str,
    pub protocol: &'static str,
    pub default_base_url: &'static str,
    pub default_model: &'static str,
    pub api_key_env: &'static str,
    pub model_suggestions: &'static [&'static str],
    pub reasoning_efforts: &'static [&'static str],
    pub default_reasoning_effort: &'static str,
    pub catalog_revision: &'static str,
    pub custom_models_env: &'static str,
    pub custom_models_path_env: &'static str,
    pub notes: &'static [&'static str],
}

pub const PYTHON_LLM_PROVIDERS: &[PythonLlmProvider] = &[
    PythonLlmProvider {
        key: "openai",
        label: "OpenAI / ChatGPT",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.openai.com/v1",
        default_model: "gpt-5.5",
        api_key_env: "OPENAI_API_KEY",
        model_suggestions: &["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.5-2026-04-23", "gpt-5.5-pro", "gpt-5.5-pro-2026-04-23", "gpt-5.4", "gpt-5.4-2026-03-05", "gpt-5.4-pro", "gpt-5.4-pro-2026-03-05", "gpt-5.4-mini", "gpt-5.4-mini-2026-03-17", "gpt-5.4-nano", "gpt-5.4-nano-2026-03-17", "gpt-5.3-chat-latest", "gpt-5.3-codex", "gpt-5.2", "gpt-5.2-codex", "gpt-5.2-chat-latest", "gpt-5.2-pro", "gpt-5.1", "gpt-5-codex", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"],
        reasoning_efforts: &["default", "none", "minimal", "low", "medium", "high", "xhigh", "max"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_OPENAI",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Uses the OpenAI-compatible chat completions endpoint.", "GPT-5.6 Sol, Terra, and Luna support reasoning levels through max; availability depends on the API account."],
    },
    PythonLlmProvider {
        key: "anthropic",
        label: "Anthropic Claude",
        mode: "cloud",
        protocol: "anthropic-messages",
        default_base_url: "https://api.anthropic.com",
        default_model: "claude-sonnet-4-5-20250929",
        api_key_env: "ANTHROPIC_API_KEY",
        model_suggestions: &["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001", "claude-opus-4-5-20251101", "claude-opus-4-1-20250805", "claude-opus-4-20250514", "claude-sonnet-4-20250514", "claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-5", "claude-opus-4-1", "claude-opus-4-0", "claude-sonnet-4-0"],
        reasoning_efforts: &["default", "disabled", "enabled", "low", "medium", "high"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_ANTHROPIC",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Uses the Anthropic messages endpoint with the 2023-06-01 API version header."],
    },
    PythonLlmProvider {
        key: "gemini",
        label: "Google Gemini",
        mode: "cloud",
        protocol: "gemini-generate-content",
        default_base_url: "https://generativelanguage.googleapis.com/v1beta",
        default_model: "gemini-3-flash-preview",
        api_key_env: "GEMINI_API_KEY",
        model_suggestions: &["gemini-3.1-pro-preview", "gemini-3.1-pro-preview-customtools", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-preview-09-2025", "gemini-2.5-flash-lite", "gemini-2.5-flash-lite-preview-09-2025"],
        reasoning_efforts: &["default", "minimal", "low", "medium", "high"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_GEMINI",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Uses the Gemini generateContent endpoint."],
    },
    PythonLlmProvider {
        key: "deepseek",
        label: "DeepSeek",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.deepseek.com",
        default_model: "deepseek-v4-flash",
        api_key_env: "DEEPSEEK_API_KEY",
        model_suggestions: &["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        reasoning_efforts: &["default", "disabled", "enabled", "high", "max"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_DEEPSEEK",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["DeepSeek documents an OpenAI-compatible chat completions surface."],
    },
    PythonLlmProvider {
        key: "mistral",
        label: "Mistral AI",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.mistral.ai/v1",
        default_model: "mistral-small-latest",
        api_key_env: "MISTRAL_API_KEY",
        model_suggestions: &["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "codestral-latest", "open-mistral-nemo"],
        reasoning_efforts: &["default", "low", "medium", "high"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_MISTRAL",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Mistral exposes an OpenAI-compatible chat completions API."],
    },
    PythonLlmProvider {
        key: "grok",
        label: "xAI Grok",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.x.ai/v1",
        default_model: "grok-4.3",
        api_key_env: "XAI_API_KEY",
        model_suggestions: &["grok-4.3", "grok-4.3-latest", "grok-4.20", "grok-4.20-reasoning", "grok-4.20-non-reasoning", "grok-4-fast-reasoning", "grok-4-fast-non-reasoning"],
        reasoning_efforts: &["default", "low", "medium", "high"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_GROK",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["xAI documents OpenAI-compatible chat completions at /v1/chat/completions."],
    },
    PythonLlmProvider {
        key: "qwen",
        label: "Alibaba Qwen / DashScope",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_model: "qwen3.6-plus",
        api_key_env: "DASHSCOPE_API_KEY",
        model_suggestions: &["qwen3.7-max", "qwen3.7-max-2026-06-08", "qwen3.7-max-2026-05-20", "qwen3.6-max-preview", "qwen3.6-plus", "qwen3.6-plus-2026-04-02", "qwen3.6-flash", "qwen3.6-flash-2026-04-16", "qwen3-max", "qwen3-max-2026-01-23", "qwen3-max-2025-09-23", "qwen3-max-preview", "qwen3.5-plus", "qwen3.5-plus-2026-02-15", "qwen3.5-flash", "qwen3.5-flash-2026-02-23", "qwen3-coder-plus", "qwen3-coder-flash", "qwen-plus-us", "qwen-flash-us"],
        reasoning_efforts: &["default", "disabled", "enabled", "low", "medium", "high", "max"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_QWEN",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["DashScope provides OpenAI-compatible endpoints for Qwen models.", "The request uses enable_thinking for compatible Qwen chat models; Qwen 3.5/3.6 multimodal and Responses-only features require DashScope's corresponding API surface."],
    },
    PythonLlmProvider {
        key: "moonshot",
        label: "Moonshot AI / Kimi",
        mode: "cloud",
        protocol: "openai-chat-completions",
        default_base_url: "https://api.moonshot.ai/v1",
        default_model: "kimi-k3",
        api_key_env: "MOONSHOT_API_KEY",
        model_suggestions: &["kimi-k3", "kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k2.6", "kimi-k2.5"],
        reasoning_efforts: &["default", "disabled", "enabled", "max"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_MOONSHOT",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Uses Moonshot's OpenAI-compatible /v1/chat/completions endpoint.", "Kimi K3 supports reasoning_effort=max. Kimi K2.5 and K2.6 use thinking enabled or disabled; K2.7 Code always reasons.", "Use the provider model discovery endpoint or the editable model field for account-specific releases."],
    },
    PythonLlmProvider {
        key: "local",
        label: "Local / Custom OpenAI-Compatible",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:11434/v1",
        default_model: "qwen3:8b",
        api_key_env: "LOCAL_LLM_API_KEY",
        model_suggestions: &["qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model", "Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_LOCAL",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Use this for any local, LAN, private IP, or custom OpenAI-compatible endpoint.", "The model field is intentionally editable so arbitrary Ollama, GGUF, or Hugging Face IDs can be used."],
    },
    PythonLlmProvider {
        key: "ollama",
        label: "Ollama",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:11434/v1",
        default_model: "qwen3:8b",
        api_key_env: "OLLAMA_API_KEY",
        model_suggestions: &["qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_OLLAMA",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Ollama exposes OpenAI-compatible /v1/chat/completions and /v1/models endpoints.", "Automatic download/start/remove actions are available for localhost Ollama."],
    },
    PythonLlmProvider {
        key: "vllm",
        label: "vLLM / SGLang",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:8000/v1",
        default_model: "Qwen/Qwen3-8B",
        api_key_env: "VLLM_API_KEY",
        model_suggestions: &["Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_VLLM",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Use this for self-hosted vLLM or SGLang OpenAI-compatible servers.", "Set Base URL / IP to a LAN, private, or remote /v1 endpoint."],
    },
    PythonLlmProvider {
        key: "llamacpp",
        label: "llama.cpp server",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:8080/v1",
        default_model: "local-model",
        api_key_env: "LLAMACPP_API_KEY",
        model_suggestions: &["local-model", "qwen3-8b-q4_k_m.gguf", "llama-3.1-8b-instruct-q4_k_m.gguf", "mistral-7b-instruct-q4_k_m.gguf", "gemma-3-4b-it-q4_k_m.gguf", "qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "THUDM/glm-4-9b-chat", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_LLAMACPP",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Use this for llama.cpp server; the loaded model name is often reported by /v1/models.", "GGUF filenames are accepted as editable model IDs when your server exposes them."],
    },
    PythonLlmProvider {
        key: "lmstudio",
        label: "LM Studio",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:1234/v1",
        default_model: "local-model",
        api_key_env: "LMSTUDIO_API_KEY",
        model_suggestions: &["local-model", "Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_LMSTUDIO",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Use this for LM Studio local server or a remote LM Studio-compatible /v1 endpoint.", "The model field is editable because LM Studio exposes locally downloaded model IDs."],
    },
    PythonLlmProvider {
        key: "tgi",
        label: "Hugging Face TGI",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:3000/v1",
        default_model: "tgi",
        api_key_env: "HUGGINGFACE_API_KEY",
        model_suggestions: &["tgi", "Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_TGI",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Use this for Hugging Face Text Generation Inference Messages API endpoints.", "Remote Hugging Face Inference Endpoints should include /v1 in the base URL."],
    },
    PythonLlmProvider {
        key: "open-source",
        label: "Generic Open-Source / Remote",
        mode: "local",
        protocol: "openai-chat-completions",
        default_base_url: "http://127.0.0.1:8000/v1",
        default_model: "Qwen/Qwen3-8B",
        api_key_env: "OPEN_SOURCE_LLM_API_KEY",
        model_suggestions: &["Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "Qwen/Qwen3-8B", "Qwen/Qwen3-14B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct", "Qwen/Qwen2.5-Coder-14B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen/QwQ-32B", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "google-t5/t5-small", "google-t5/t5-base", "google-t5/t5-large", "google/flan-t5-small", "google/flan-t5-base", "google/flan-t5-large", "google/flan-t5-xl", "google/flan-t5-xxl", "RWKV/rwkv-4-world", "RWKV/rwkv-5-world", "RWKV/rwkv-6-world", "BlinkDL/rwkv-7-world", "EleutherAI/gpt-neox-20b", "EleutherAI/gpt-j-6b", "EleutherAI/gpt-neo-2.7B", "yandex/yalm-100b", "meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3", "mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mixtral-8x7B-Instruct-v0.1", "mistralai/Mixtral-8x22B-Instruct-v0.1", "mistralai/Codestral-22B-v0.1", "deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "google/gemma-3-1b-it", "google/gemma-3-4b-it", "google/gemma-3-12b-it", "google/gemma-3-27b-it", "google/gemma-2-2b-it", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "microsoft/phi-4", "microsoft/Phi-4-mini-instruct", "microsoft/Phi-3.5-mini-instruct", "tiiuae/Falcon3-1B-Instruct", "tiiuae/Falcon3-3B-Instruct", "tiiuae/Falcon3-7B-Instruct", "tiiuae/Falcon3-10B-Instruct", "tiiuae/falcon-180B-chat", "01-ai/Yi-6B-Chat", "01-ai/Yi-9B-Chat", "01-ai/Yi-34B-Chat", "THUDM/glm-4-9b-chat", "internlm/internlm2_5-7b-chat", "internlm/internlm2_5-20b-chat", "baichuan-inc/Baichuan2-7B-Chat", "baichuan-inc/Baichuan2-13B-Chat", "openbmb/MiniCPM3-4B", "HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct", "HuggingFaceTB/SmolLM2-1.7B-Instruct", "ibm-granite/granite-3.3-2b-instruct", "ibm-granite/granite-3.3-8b-instruct", "CohereForAI/c4ai-command-r-v01", "CohereForAI/c4ai-command-r-plus", "CohereForAI/aya-23-8B", "CohereForAI/aya-23-35B", "bigscience/bloomz-7b1", "bigscience/bloom", "mosaicml/mpt-7b-instruct", "mosaicml/mpt-30b-instruct", "databricks/dbrx-instruct", "ai21labs/Jamba-v0.1", "Nexusflow/Starling-LM-7B-beta", "HuggingFaceH4/zephyr-7b-beta", "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO", "openchat/openchat-3.5-0106", "WizardLMTeam/WizardLM-2-8x22B", "lmsys/vicuna-13b-v1.5", "codellama/CodeLlama-7b-Instruct-hf", "codellama/CodeLlama-13b-Instruct-hf", "codellama/CodeLlama-34b-Instruct-hf", "bigcode/starcoder2-3b", "bigcode/starcoder2-7b", "bigcode/starcoder2-15b", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF", "google/flan-ul2", "allenai/OLMo-7B-Instruct", "allenai/OLMo-2-1124-7B-Instruct", "allenai/OLMo-2-1124-13B-Instruct", "cerebras/Cerebras-GPT-111M", "cerebras/Cerebras-GPT-256M", "cerebras/Cerebras-GPT-590M", "cerebras/Cerebras-GPT-1.3B", "cerebras/Cerebras-GPT-2.7B", "cerebras/Cerebras-GPT-6.7B", "cerebras/Cerebras-GPT-13B", "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", "EleutherAI/pythia-70m", "EleutherAI/pythia-160m", "EleutherAI/pythia-410m", "EleutherAI/pythia-1b", "EleutherAI/pythia-1.4b", "EleutherAI/pythia-2.8b", "EleutherAI/pythia-6.9b", "EleutherAI/pythia-12b", "databricks/dolly-v2-3b", "databricks/dolly-v2-7b", "databricks/dolly-v2-12b", "stabilityai/stablelm-base-alpha-3b", "stabilityai/stablelm-base-alpha-7b", "stabilityai/stablelm-tuned-alpha-3b", "stabilityai/stablelm-tuned-alpha-7b", "lmsys/fastchat-t5-3b-v1.0", "aisquared/dlite-v2-1_5b", "h2oai/h2ogpt-oasst1-512-12b", "togethercomputer/RedPajama-INCITE-7B-Instruct", "openlm-research/open_llama_3b", "openlm-research/open_llama_7b", "openlm-research/open_llama_13b", "mosaicml/mpt-7b-chat", "mosaicml/mpt-7b-storywriter", "mosaicml/mpt-30b-chat", "nomic-ai/gpt4all-j", "Salesforce/xgen-7b-8k-inst", "inceptionai/jais-13b-chat", "codellama/CodeLlama-70b-Instruct-hf", "teknium/OpenHermes-2.5-Mistral-7B", "apple/OpenELM-270M-Instruct", "apple/OpenELM-450M-Instruct", "apple/OpenELM-1_1B-Instruct", "apple/OpenELM-3B-Instruct", "Deci/DeciLM-7B-instruct", "THUDM/chatglm-6b", "THUDM/chatglm2-6b", "THUDM/chatglm3-6b", "Skywork/Skywork-13B-base", "LLM360/Amber", "Cerebras/FLOR-6.3B", "Qwen/Qwen1.5-0.5B-Chat", "Qwen/Qwen1.5-1.8B-Chat", "Qwen/Qwen1.5-4B-Chat", "Qwen/Qwen1.5-7B-Chat", "Qwen/Qwen1.5-14B-Chat", "Qwen/Qwen1.5-32B-Chat", "Qwen/Qwen1.5-72B-Chat", "Qwen/Qwen1.5-110B-Chat", "Qwen/Qwen1.5-MoE-A2.7B-Chat", "LargeWorldModel/LWM-Text-1M", "YerevaNN/YerevaNN-Grok-1", "state-spaces/mamba-130m", "state-spaces/mamba-370m", "state-spaces/mamba-790m", "state-spaces/mamba-1.4b", "state-spaces/mamba-2.8b", "Snowflake/snowflake-arctic-instruct", "Fugaku-LLM/Fugaku-LLM-13B-instruct", "tiiuae/Falcon2-11B", "01-ai/Yi-1.5-6B-Chat", "01-ai/Yi-1.5-9B-Chat", "01-ai/Yi-1.5-34B-Chat", "deepseek-ai/DeepSeek-V2-Lite-Chat", "deepseek-ai/DeepSeek-V2-Chat", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3-0324", "deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1-0528", "microsoft/Phi-3-medium-128k-instruct", "microsoft/Phi-3-mini-128k-instruct", "microsoft/phi-4-reasoning", "yulan-team/YuLan-Mini", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "bigcode/santacoder", "Salesforce/codegen2-1B", "Salesforce/codegen2-3_7B", "Salesforce/codegen2-7B", "HuggingFaceH4/starchat-alpha", "replit/replit-code-v1-3b", "Salesforce/codet5p-770m", "Salesforce/codet5p-2b", "Salesforce/codet5p-6b", "Salesforce/codegen25-7b-multi", "Deci/DeciCoder-1b", "meta-llama/Llama-2-7b-chat-hf", "meta-llama/Llama-2-13b-chat-hf", "meta-llama/Llama-2-70b-chat-hf", "meta-llama/Llama-3-8B-Instruct", "meta-llama/Llama-3-70B-Instruct", "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "meta-llama/Llama-4-Scout-17B-16E-Instruct", "mistralai/Mistral-7B-Instruct-v0.2", "mistralai/Mistral-Large-Instruct-2407", "mistralai/Mistral-Large-Instruct-2411", "Qwen/Qwen2-72B-Instruct", "Qwen/Qwen3-235B-A22B-Instruct-2507", "Qwen/Qwen3-235B-A22B-Thinking-2507", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3.5", "Qwen/Qwen3.5-30B-A3B", "Qwen/Qwen3.5-Coder", "zai-org/GLM-4.5", "zai-org/GLM-4.5-Air", "zai-org/GLM-4.6", "zai-org/GLM-5", "moonshotai/Kimi-K2", "moonshotai/Kimi-K2-Thinking", "moonshotai/Kimi-K2.5", "MiniMaxAI/MiniMax-M2.5", "stepfun-ai/Step3", "stepfun-ai/Step-3.5-Flash", "XiaomiMiMo/MiMo-V2-Flash", "google/gemma-4-4b-it", "google/gemma-4-12b-it", "google/gemma-4-27b-it", "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1", "nvidia/Llama-3.1-Nemotron-Super-49B-v1", "nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b", "qwen3:30b-a3b", "qwen3:32b", "qwen3", "qwen3-vl:8b", "qwen3-vl:32b", "qwen3.5", "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b", "qwq:32b", "gpt-oss:20b", "gpt-oss:120b", "gpt-oss:latest", "llama4:maverick", "llama4:scout", "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b", "deepseek-coder-v2", "llama3.3", "llama3.1:8b", "llama3.1:70b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b", "llama3.2-vision:90b", "mistral", "mistral-nemo", "mistral-small3.2", "mixtral:8x7b", "mixtral:8x22b", "codestral", "devstral", "gemma3:1b", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma4:27b", "gemma2:2b", "gemma2:9b", "gemma2:27b", "phi4", "phi4-mini", "phi3.5", "phi3:mini", "falcon3:1b", "falcon3:3b", "falcon3:7b", "falcon3:10b", "yi:6b", "yi:9b", "yi:34b", "glm4", "glm4.5", "glm5", "kimi-k2", "minimax-m2", "step3", "mimo-v2", "internlm2.5", "baichuan2:7b", "baichuan2:13b", "minicpm-v", "smollm2:135m", "smollm2:360m", "smollm2:1.7b", "granite3.3:2b", "granite3.3:8b", "command-r", "command-r-plus", "starcoder2:3b", "starcoder2:7b", "starcoder2:15b", "codellama:7b", "codellama:13b", "codellama:34b", "dolphin-mixtral", "openchat", "neural-chat", "orca-mini", "zephyr", "solar", "nous-hermes2", "wizardlm2", "vicuna", "rwkv", "pythia", "dolly-v2", "stablelm", "redpajama", "openllama", "mpt", "dbrx", "arctic", "bloom", "bloomz", "mamba", "custom-model"],
        reasoning_efforts: &["default", "none", "disabled", "auto", "low", "medium", "high", "xhigh"],
        default_reasoning_effort: "default",
        catalog_revision: "2026-07-16",
        custom_models_env: "BOT_LLM_EXTRA_MODELS_OPEN_SOURCE",
        custom_models_path_env: "BOT_LLM_MODEL_CATALOG_PATH",
        notes: &["Use this for any OpenAI-compatible open-source runtime, including remote IP or URL endpoints.", "For public endpoints, enable Allow public network endpoint so context is minimized."],
    },
];

    pub struct PythonOllamaModelSizeHint {
    pub model: &'static str,
    pub label: &'static str,
    pub size_gb: Option<f64>,
}

pub const PYTHON_OLLAMA_MODEL_SIZE_HINTS: &[PythonOllamaModelSizeHint] = &[
    PythonOllamaModelSizeHint {
        model: "qwen3:0.6b",
        label: "about 1 GB",
        size_gb: Some(1.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3:1.7b",
        label: "about 2 GB",
        size_gb: Some(2.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3:4b",
        label: "about 3 GB",
        size_gb: Some(3.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3:8b",
        label: "about 5 GB",
        size_gb: Some(5.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3:14b",
        label: "about 9 GB",
        size_gb: Some(9.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3:30b-a3b",
        label: "about 19 GB",
        size_gb: Some(19.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3:32b",
        label: "about 20 GB",
        size_gb: Some(20.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3-vl:8b",
        label: "about 6 GB",
        size_gb: Some(6.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen3-vl:32b",
        label: "about 21 GB",
        size_gb: Some(21.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5:7b",
        label: "about 5 GB",
        size_gb: Some(5.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5:14b",
        label: "about 9 GB",
        size_gb: Some(9.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5:32b",
        label: "about 20 GB",
        size_gb: Some(20.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5:72b",
        label: "about 45 GB",
        size_gb: Some(45.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5-coder:7b",
        label: "about 5 GB",
        size_gb: Some(5.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5-coder:14b",
        label: "about 9 GB",
        size_gb: Some(9.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwen2.5-coder:32b",
        label: "about 20 GB",
        size_gb: Some(20.0),
    },
    PythonOllamaModelSizeHint {
        model: "qwq:32b",
        label: "about 20 GB",
        size_gb: Some(20.0),
    },
    PythonOllamaModelSizeHint {
        model: "llama3.1:8b",
        label: "about 5 GB",
        size_gb: Some(5.0),
    },
    PythonOllamaModelSizeHint {
        model: "llama3.1:70b",
        label: "about 43 GB",
        size_gb: Some(43.0),
    },
    PythonOllamaModelSizeHint {
        model: "llama3.2:3b",
        label: "about 2 GB",
        size_gb: Some(2.0),
    },
    PythonOllamaModelSizeHint {
        model: "llama3.2:1b",
        label: "about 1 GB",
        size_gb: Some(1.0),
    },
    PythonOllamaModelSizeHint {
        model: "deepseek-r1:1.5b",
        label: "about 2 GB",
        size_gb: Some(2.0),
    },
    PythonOllamaModelSizeHint {
        model: "deepseek-r1:7b",
        label: "about 5 GB",
        size_gb: Some(5.0),
    },
    PythonOllamaModelSizeHint {
        model: "deepseek-r1:8b",
        label: "about 5 GB",
        size_gb: Some(5.0),
    },
    PythonOllamaModelSizeHint {
        model: "deepseek-r1:14b",
        label: "about 9 GB",
        size_gb: Some(9.0),
    },
    PythonOllamaModelSizeHint {
        model: "deepseek-r1:32b",
        label: "about 20 GB",
        size_gb: Some(20.0),
    },
    PythonOllamaModelSizeHint {
        model: "deepseek-r1:70b",
        label: "about 43 GB",
        size_gb: Some(43.0),
    },
    PythonOllamaModelSizeHint {
        model: "gemma3:1b",
        label: "about 1 GB",
        size_gb: Some(1.0),
    },
    PythonOllamaModelSizeHint {
        model: "gemma3:4b",
        label: "about 3 GB",
        size_gb: Some(3.0),
    },
    PythonOllamaModelSizeHint {
        model: "gemma3:12b",
        label: "about 8 GB",
        size_gb: Some(8.0),
    },
    PythonOllamaModelSizeHint {
        model: "gemma3:27b",
        label: "about 17 GB",
        size_gb: Some(17.0),
    },
    PythonOllamaModelSizeHint {
        model: "gpt-oss:20b",
        label: "about 13 GB",
        size_gb: Some(13.0),
    },
    PythonOllamaModelSizeHint {
        model: "gpt-oss:120b",
        label: "about 75 GB",
        size_gb: Some(75.0),
    },
];

    pub const PYTHON_LLM_PROVIDER_CHOICES: &[(&str, &str)] = &[
    ("", "openai"),
    ("alibaba", "qwen"),
    ("alibaba-qwen", "qwen"),
    ("anthropic", "anthropic"),
    ("anthropic-claude", "anthropic"),
    ("arctic", "open-source"),
    ("bloom", "open-source"),
    ("bloomz", "open-source"),
    ("cerebras", "open-source"),
    ("chatglm", "open-source"),
    ("chatgpt", "openai"),
    ("claude", "anthropic"),
    ("codet5", "open-source"),
    ("custom", "local"),
    ("dashscope", "qwen"),
    ("dbrx", "open-source"),
    ("decicoder", "open-source"),
    ("deepseek", "deepseek"),
    ("dolly", "open-source"),
    ("flan-t5", "open-source"),
    ("fugaku", "open-source"),
    ("gemini", "gemini"),
    ("gemma4", "open-source"),
    ("glm", "open-source"),
    ("glm5", "open-source"),
    ("google", "gemini"),
    ("google-gemini", "gemini"),
    ("gpt-neox", "open-source"),
    ("gpt20b", "open-source"),
    ("grok", "grok"),
    ("hf", "open-source"),
    ("hf-tgi", "tgi"),
    ("hugging-face", "open-source"),
    ("huggingface", "open-source"),
    ("huggingface-tgi", "tgi"),
    ("jais", "open-source"),
    ("kimi", "moonshot"),
    ("llama-4", "open-source"),
    ("llama-cpp", "llamacpp"),
    ("llama-cpp-server", "llamacpp"),
    ("llama.cpp", "llamacpp"),
    ("llama4", "open-source"),
    ("llamacpp", "llamacpp"),
    ("lm-studio", "lmstudio"),
    ("lmstudio", "lmstudio"),
    ("local", "local"),
    ("local-openai", "local"),
    ("local-openai-compatible", "local"),
    ("mamba", "open-source"),
    ("mimo", "open-source"),
    ("minimax", "open-source"),
    ("mistral", "mistral"),
    ("mistral-ai", "mistral"),
    ("moonshot", "moonshot"),
    ("moonshot-ai", "moonshot"),
    ("mpt", "open-source"),
    ("nemotron", "open-source"),
    ("ollama", "ollama"),
    ("olmo", "open-source"),
    ("open-llama", "open-source"),
    ("open-source", "open-source"),
    ("open-weight", "open-source"),
    ("open-weights", "open-source"),
    ("openai", "openai"),
    ("openai-chatgpt", "openai"),
    ("openllama", "open-source"),
    ("opensource", "open-source"),
    ("oss", "open-source"),
    ("pythia", "open-source"),
    ("qwen", "qwen"),
    ("qwen-local", "open-source"),
    ("redpajama", "open-source"),
    ("replit-code", "open-source"),
    ("rmkv", "open-source"),
    ("rwkv", "open-source"),
    ("s-glang", "vllm"),
    ("santacoder", "open-source"),
    ("sglang", "vllm"),
    ("stablelm", "open-source"),
    ("starchat", "open-source"),
    ("step", "open-source"),
    ("stepfun", "open-source"),
    ("t5", "open-source"),
    ("text-generation-inference", "tgi"),
    ("tgi", "tgi"),
    ("vllm", "vllm"),
    ("xai", "grok"),
    ("xai-grok", "grok"),
    ("xgen", "open-source"),
    ("xiaomi", "open-source"),
    ("yalm", "open-source"),
    ("zai", "open-source"),
];

    pub const PYTHON_ACCOUNT_TYPE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("spot", "Spot"),
    ("futures", "Futures"),
];

pub const PYTHON_MARGIN_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("isolated", "Isolated"),
    ("cross", "Cross"),
];

pub const PYTHON_POSITION_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("hedge", "Hedge"),
    ("one-way", "One-way"),
    ("oneway", "One-way"),
];

pub const PYTHON_ASSETS_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("single-asset", "Single-Asset"),
    ("single-asset mode", "Single-Asset"),
    ("multi-assets", "Multi-Assets"),
    ("multi-asset", "Multi-Assets"),
    ("multi-assets mode", "Multi-Assets"),
];

pub const PYTHON_ACCOUNT_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("classic trading", "Classic Trading"),
    ("portfolio margin", "Portfolio Margin"),
];

pub const PYTHON_SIDE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("both", "BOTH"),
    ("buy", "BUY"),
    ("sell", "SELL"),
];

pub const PYTHON_ORDER_TYPE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("market", "MARKET"),
    ("limit", "LIMIT"),
];

pub const PYTHON_TIF_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("gtc", "GTC"),
    ("ioc", "IOC"),
    ("fok", "FOK"),
    ("gtd", "GTD"),
];

pub const PYTHON_LOGIC_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("and", "AND"),
    ("or", "OR"),
    ("separate", "SEPARATE"),
];

pub const PYTHON_MDD_LOGIC_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("per_trade", "per_trade"),
    ("cumulative", "cumulative"),
    ("entire_account", "entire_account"),
];

pub const PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("usdt", "usdt"),
    ("percent", "percent"),
    ("both", "both"),
];

pub const PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("per_trade", "per_trade"),
    ("cumulative", "cumulative"),
    ("entire_account", "entire_account"),
];

pub const PYTHON_SCAN_SCOPE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("selected", "selected"),
    ("top_n", "top_n"),
    ("top-n", "top_n"),
    ("all_loaded", "all_loaded"),
    ("all-loaded", "all_loaded"),
];

pub const PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("current", "current"),
    ("single", "single"),
    ("pairs", "pairs"),
    ("combinations", "combinations"),
];

pub const PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("roi_percent", "roi_percent"),
    ("roi-percent", "roi_percent"),
    ("roi_percent_mdd", "roi_percent_mdd"),
    ("roi-percent-mdd", "roi_percent_mdd"),
    ("roi_drawdown", "roi_drawdown"),
    ("roi-drawdown", "roi_drawdown"),
    ("roi_value", "roi_value"),
    ("roi-value", "roi_value"),
];

pub const PYTHON_BACKTEST_EXECUTION_BACKEND_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("desktop", "local"),
    ("desktop-local", "local"),
    ("local", "local"),
    ("remote", "service"),
    ("service", "service"),
    ("service-api", "service"),
];

pub const PYTHON_CHART_VIEW_MODE_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("tradingview", "tradingview"),
    ("original", "original"),
    ("lightweight", "lightweight"),
    ("tradingview lightweight", "lightweight"),
];

pub const PYTHON_LLM_USE_FOR_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("advisory", "advisory"),
    ("backtest_explanation", "backtest_explanation"),
    ("risk_review", "risk_review"),
    ("signal_confirmation", "signal_confirmation"),
];

pub const PYTHON_LLM_REASONING_EFFORT_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("default", "default"),
    ("disabled", "disabled"),
    ("enabled", "enabled"),
    ("extra-high", "xhigh"),
    ("extra_high", "xhigh"),
    ("high", "high"),
    ("low", "low"),
    ("max", "max"),
    ("medium", "medium"),
    ("minimal", "minimal"),
    ("none", "none"),
    ("xhigh", "xhigh"),
];

pub const PYTHON_POSITION_PCT_UNITS_CONFIG_CHOICES: &[(&str, &str)] = &[
    ("percent", "percent"),
    ("%", "percent"),
    ("perc", "percent"),
    ("percentage", "percent"),
    ("fraction", "fraction"),
    ("decimal", "fraction"),
    ("ratio", "fraction"),
];

    pub const PYTHON_CONNECTOR_KEYS: &[&str] = &[
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "oanda-rest",
    "fxcmpy",
    "ig-rest",
    "citic-ctp",
    "metatrader4-bridge",
    "metatrader5",
    "trading212-public-api",
    "moomoo-opend",
    "python-binance",
];

    pub struct PythonConnectorOption {
    pub key: &'static str,
    pub label: &'static str,
}

pub const PYTHON_CONNECTOR_OPTIONS: &[PythonConnectorOption] = &[
    PythonConnectorOption {
        key: "binance-sdk-derivatives-trading-usds-futures",
        label: "Binance SDK Derivatives Trading USD\u{24c8} Futures (Official Recommended)",
    },
    PythonConnectorOption {
        key: "binance-sdk-derivatives-trading-coin-futures",
        label: "Binance SDK Derivatives Trading COIN-M Futures",
    },
    PythonConnectorOption {
        key: "binance-sdk-spot",
        label: "Binance SDK Spot (Official Recommended)",
    },
    PythonConnectorOption {
        key: "binance-connector",
        label: "Binance Connector Python",
    },
    PythonConnectorOption {
        key: "ccxt",
        label: "CCXT (Unified)",
    },
    PythonConnectorOption {
        key: "oanda-rest",
        label: "OANDA REST-v20",
    },
    PythonConnectorOption {
        key: "fxcmpy",
        label: "FXCM fxcmpy",
    },
    PythonConnectorOption {
        key: "ig-rest",
        label: "IG REST Trading API",
    },
    PythonConnectorOption {
        key: "citic-ctp",
        label: "CITIC Futures CTP (Local/Remote TCP Front)",
    },
    PythonConnectorOption {
        key: "metatrader4-bridge",
        label: "MetaTrader 4 Bridge (Local/Remote Expert Advisor)",
    },
    PythonConnectorOption {
        key: "metatrader5",
        label: "MetaTrader 5 (Official Python Integration)",
    },
    PythonConnectorOption {
        key: "trading212-public-api",
        label: "Trading 212 Public API (Invest/Stocks ISA equities)",
    },
    PythonConnectorOption {
        key: "moomoo-opend",
        label: "moomoo OpenD (Local/Remote Gateway)",
    },
    PythonConnectorOption {
        key: "python-binance",
        label: "python-binance (Community)",
    },
];

    pub struct PythonRustEnvironmentDependency {
    pub key: &'static str,
    pub label: &'static str,
    pub kind: &'static str,
    pub path: &'static str,
    pub latest: &'static str,
    pub usage: &'static str,
}

pub const PYTHON_RUST_ENVIRONMENT_DEPENDENCIES: &[PythonRustEnvironmentDependency] = &[
    PythonRustEnvironmentDependency {
        key: "rustc",
        label: "rustc",
        kind: "rust_rustc",
        path: "",
        latest: "Install rustup",
        usage: "",
    },
    PythonRustEnvironmentDependency {
        key: "cargo",
        label: "cargo",
        kind: "rust_cargo",
        path: "",
        latest: "Install rustup",
        usage: "",
    },
    PythonRustEnvironmentDependency {
        key: "experiments/rust-shells/Cargo.toml",
        label: "Trading Bot Rust workspace",
        kind: "rust_file_version",
        path: "experiments/rust-shells/Cargo.toml",
        latest: "",
        usage: "Active",
    },
    PythonRustEnvironmentDependency {
        key: "experiments/rust-shells/crates/core/Cargo.toml",
        label: "trading-bot-core",
        kind: "rust_file_version",
        path: "experiments/rust-shells/crates/core/Cargo.toml",
        latest: "",
        usage: "Active",
    },
    PythonRustEnvironmentDependency {
        key: "experiments/rust-shells/crates/contracts/Cargo.toml",
        label: "trading-bot-contracts",
        kind: "rust_file_version",
        path: "experiments/rust-shells/crates/contracts/Cargo.toml",
        latest: "",
        usage: "Active",
    },
    PythonRustEnvironmentDependency {
        key: "experiments/rust-shells/apps/tauri-desktop/Cargo.toml",
        label: "Tauri (Primary)",
        kind: "rust_file_version",
        path: "experiments/rust-shells/apps/tauri-desktop/Cargo.toml",
        latest: "",
        usage: "Active",
    },
];

    pub const PYTHON_SUPPORTED_BROKERS: &[&str] = &[
    "OANDA",
    "FXCM",
    "IG",
    "Trade Nation",
    "FXTF",
    "FOREX EXCHANGE",
    "AvaTrade",
    "EC Markets",
    "GTCFX",
    "Finalto",
    "ATFX",
    "Vantage",
    "STARTRADER",
    "XM",
    "TMGM",
    "Capital.com",
    "IC Markets Global",
    "Hantec Financial",
    "GO Markets",
    "VT Markets",
    "Neex",
    "ACY Securities",
    "Fortune Prime Global",
    "DecodeFX",
    "CPT Markets",
    "PU Prime",
    "AIMS",
    "ETO Markets",
    "D Prime",
    "Fusion Markets",
    "Exness",
    "Valetax",
    "CXM",
    "DBG Markets",
    "FXT",
    "Plotio",
    "FOREX.com",
    "CMC Markets",
    "StoneX",
    "SBCFX",
    "PhillipCapital (Phillip Nova)",
    "AI Gold Securities",
    "CITIC Futures",
    "Trading 212",
    "moomoo",
];

    pub const PYTHON_SUPPORTED_FOREX_BROKERS: &[&str] = &[
    "OANDA",
    "FXCM",
    "IG",
    "Trade Nation",
    "FXTF",
    "FOREX EXCHANGE",
    "AvaTrade",
    "EC Markets",
    "GTCFX",
    "Finalto",
    "ATFX",
    "Vantage",
    "STARTRADER",
    "XM",
    "TMGM",
    "Capital.com",
    "IC Markets Global",
    "Hantec Financial",
    "GO Markets",
    "VT Markets",
    "Neex",
    "ACY Securities",
    "Fortune Prime Global",
    "DecodeFX",
    "CPT Markets",
    "PU Prime",
    "AIMS",
    "ETO Markets",
    "D Prime",
    "Fusion Markets",
    "Exness",
    "Valetax",
    "CXM",
    "DBG Markets",
    "FXT",
    "Plotio",
    "FOREX.com",
    "CMC Markets",
    "SBCFX",
    "PhillipCapital (Phillip Nova)",
];

    pub const PYTHON_BROKER_ORDER_ROUTING_BACKENDS: &[(&str, &str, &str, bool)] = &[
    ("oanda", "oanda-rest", "forex-and-provider-configured-cfd-markets", true),
    ("fxcm", "fxcmpy", "forex-and-provider-configured-cfd-markets", true),
    ("ig", "ig-rest", "forex-and-provider-configured-cfd-markets", true),
    ("trade nation", "metatrader4-bridge", "forex-and-provider-configured-cfd-markets", true),
    ("fxtf", "metatrader4-bridge", "forex-and-provider-configured-cfd-markets", true),
    ("forex exchange", "metatrader4-bridge", "forex-and-provider-configured-cfd-markets", true),
    ("avatrade", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("ec markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("gtcfx", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("finalto", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("atfx", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("vantage", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("startrader", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("xm", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("tmgm", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("capital.com", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("ic markets global", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("hantec financial", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("go markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("vt markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("neex", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("acy securities", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("fortune prime global", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("decodefx", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("cpt markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("pu prime", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("aims", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("eto markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("d prime", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("fusion markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("exness", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("valetax", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("cxm", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("dbg markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("fxt", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("plotio", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("forex.com", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("cmc markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("stonex", "metatrader5", "futures-and-options-on-futures", false),
    ("sbcfx", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("phillipcapital (phillip nova)", "metatrader5", "forex-and-provider-configured-cfd-markets", true),
    ("ai gold securities", "metatrader5", "otc-commodity-derivatives", false),
    ("citic futures", "citic-ctp", "china-futures-and-options", false),
    ("trading 212", "trading212-public-api", "invest-and-stocks-isa-equities-only", false),
    ("moomoo", "moomoo-opend", "stocks-etfs-options-futures-funds-and-supported-crypto", false),
];

    pub const PYTHON_BROKER_CANONICAL_NAMES: &[(&str, &str)] = &[
    ("oanda", "OANDA"),
    ("fxcm", "FXCM"),
    ("ig", "IG"),
    ("tradenation", "Trade Nation"),
    ("fxtf", "FXTF"),
    ("forexexchange", "FOREX EXCHANGE"),
    ("avatrade", "AvaTrade"),
    ("ecmarkets", "EC Markets"),
    ("gtcfx", "GTCFX"),
    ("finalto", "Finalto"),
    ("atfx", "ATFX"),
    ("vantage", "Vantage"),
    ("startrader", "STARTRADER"),
    ("xm", "XM"),
    ("tmgm", "TMGM"),
    ("capitalcom", "Capital.com"),
    ("icmarketsglobal", "IC Markets Global"),
    ("hantecfinancial", "Hantec Financial"),
    ("gomarkets", "GO Markets"),
    ("vtmarkets", "VT Markets"),
    ("neex", "Neex"),
    ("acysecurities", "ACY Securities"),
    ("fortuneprimeglobal", "Fortune Prime Global"),
    ("decodefx", "DecodeFX"),
    ("cptmarkets", "CPT Markets"),
    ("puprime", "PU Prime"),
    ("aims", "AIMS"),
    ("etomarkets", "ETO Markets"),
    ("dprime", "D Prime"),
    ("fusionmarkets", "Fusion Markets"),
    ("exness", "Exness"),
    ("valetax", "Valetax"),
    ("cxm", "CXM"),
    ("dbgmarkets", "DBG Markets"),
    ("fxt", "FXT"),
    ("plotio", "Plotio"),
    ("forexcom", "FOREX.com"),
    ("cmcmarkets", "CMC Markets"),
    ("stonex", "StoneX"),
    ("sbcfx", "SBCFX"),
    ("phillipcapitalphillipnova", "PhillipCapital (Phillip Nova)"),
    ("aigoldsecurities", "AI Gold Securities"),
    ("citicfutures", "CITIC Futures"),
    ("trading212", "Trading 212"),
    ("moomoo", "moomoo"),
    ("mitrade", "Mitrade"),
    ("axpm", "AXPM"),
    ("spreadex", "Spreadex"),
    ("jefferies", "Jefferies"),
    ("marex", "Marex"),
    ("aigold", "AI Gold Securities"),
    ("phillipsecurities", "PhillipCapital (Phillip Nova)"),
    ("philipsecurities", "PhillipCapital (Phillip Nova)"),
    ("cmcmarkes", "CMC Markets"),
];

    pub const PYTHON_SUPPORTED_EXCHANGES: &[&str] = &[
    "Binance",
    "Bybit",
    "OKX",
    "Bitget",
    "Gate",
    "MEXC",
    "KuCoin",
    "HTX",
    "Crypto.com Exchange",
    "Kraken",
    "Bitfinex",
];

    pub const PYTHON_SUPPORTED_CONNECTOR_BACKENDS: &[&str] = &[
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "python-binance",
    "ccxt",
    "oanda-rest",
    "fxcmpy",
    "ig-rest",
    "citic-ctp",
    "metatrader4-bridge",
    "metatrader5",
    "trading212-public-api",
    "moomoo-opend",
];

    pub const PYTHON_CCXT_DIAGNOSTIC_EXCHANGES: &[&str] = &[
    "Bybit",
    "OKX",
    "Bitget",
    "Gate",
    "MEXC",
    "KuCoin",
    "HTX",
    "Crypto.com Exchange",
    "Kraken",
    "Bitfinex",
];

    pub const PYTHON_CCXT_ORDER_ROUTING_EXCHANGES: &[&str] = &[
    "Bybit",
    "OKX",
    "Bitget",
    "Gate",
    "MEXC",
    "KuCoin",
    "HTX",
    "Crypto.com Exchange",
    "Kraken",
    "Bitfinex",
];

    pub const PYTHON_ORDER_EXECUTION_EXCHANGES: &[&str] = &[
    "Binance",
];

    pub const PYTHON_CCXT_EXCHANGE_IDS: &[(&str, &str)] = &[
    ("bybit", "bybit"),
    ("okx", "okx"),
    ("bitget", "bitget"),
    ("gate", "gateio"),
    ("gate.io", "gateio"),
    ("gateio", "gateio"),
    ("mexc", "mexc"),
    ("kucoin", "kucoin"),
    ("htx", "htx"),
    ("crypto.com", "cryptocom"),
    ("crypto.com exchange", "cryptocom"),
    ("cryptocom", "cryptocom"),
    ("kraken", "kraken"),
    ("bitfinex", "bitfinex"),
];

    pub const PYTHON_BACKTEST_INTERVALS: &[&str] = &[
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
    "2y",
];

    pub struct PythonTradingViewInterval {
    pub interval: &'static str,
    pub code: &'static str,
}

pub const PYTHON_TRADINGVIEW_INTERVAL_MAP: &[PythonTradingViewInterval] = &[
    PythonTradingViewInterval {
        interval: "1m",
        code: "1",
    },
    PythonTradingViewInterval {
        interval: "3m",
        code: "3",
    },
    PythonTradingViewInterval {
        interval: "5m",
        code: "5",
    },
    PythonTradingViewInterval {
        interval: "10m",
        code: "10",
    },
    PythonTradingViewInterval {
        interval: "15m",
        code: "15",
    },
    PythonTradingViewInterval {
        interval: "20m",
        code: "20",
    },
    PythonTradingViewInterval {
        interval: "30m",
        code: "30",
    },
    PythonTradingViewInterval {
        interval: "45m",
        code: "45",
    },
    PythonTradingViewInterval {
        interval: "1h",
        code: "60",
    },
    PythonTradingViewInterval {
        interval: "2h",
        code: "120",
    },
    PythonTradingViewInterval {
        interval: "3h",
        code: "180",
    },
    PythonTradingViewInterval {
        interval: "4h",
        code: "240",
    },
    PythonTradingViewInterval {
        interval: "5h",
        code: "300",
    },
    PythonTradingViewInterval {
        interval: "6h",
        code: "360",
    },
    PythonTradingViewInterval {
        interval: "7h",
        code: "420",
    },
    PythonTradingViewInterval {
        interval: "8h",
        code: "480",
    },
    PythonTradingViewInterval {
        interval: "9h",
        code: "540",
    },
    PythonTradingViewInterval {
        interval: "10h",
        code: "600",
    },
    PythonTradingViewInterval {
        interval: "11h",
        code: "660",
    },
    PythonTradingViewInterval {
        interval: "12h",
        code: "720",
    },
    PythonTradingViewInterval {
        interval: "1d",
        code: "1D",
    },
    PythonTradingViewInterval {
        interval: "2d",
        code: "2D",
    },
    PythonTradingViewInterval {
        interval: "3d",
        code: "3D",
    },
    PythonTradingViewInterval {
        interval: "4d",
        code: "4D",
    },
    PythonTradingViewInterval {
        interval: "5d",
        code: "5D",
    },
    PythonTradingViewInterval {
        interval: "6d",
        code: "6D",
    },
    PythonTradingViewInterval {
        interval: "1w",
        code: "1W",
    },
    PythonTradingViewInterval {
        interval: "2w",
        code: "2W",
    },
    PythonTradingViewInterval {
        interval: "3w",
        code: "3W",
    },
    PythonTradingViewInterval {
        interval: "1mo",
        code: "1M",
    },
    PythonTradingViewInterval {
        interval: "2mo",
        code: "2M",
    },
    PythonTradingViewInterval {
        interval: "3mo",
        code: "3M",
    },
    PythonTradingViewInterval {
        interval: "6mo",
        code: "6M",
    },
    PythonTradingViewInterval {
        interval: "1month",
        code: "1M",
    },
    PythonTradingViewInterval {
        interval: "2months",
        code: "2M",
    },
    PythonTradingViewInterval {
        interval: "3months",
        code: "3M",
    },
    PythonTradingViewInterval {
        interval: "6months",
        code: "6M",
    },
    PythonTradingViewInterval {
        interval: "1y",
        code: "12M",
    },
    PythonTradingViewInterval {
        interval: "2y",
        code: "24M",
    },
];

    pub const PYTHON_DEFAULT_CHART_SYMBOLS: &[&str] = &[
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "TRXUSDT",
];

    pub const PYTHON_DEFAULT_EXECUTION_SYMBOLS: &[&str] = &[
    "BTCUSDT",
];

    pub const PYTHON_DEFAULT_EXECUTION_INTERVALS: &[&str] = &[
    "1m",
];

    pub const PYTHON_DEFAULT_BACKTEST_SYMBOLS: &[&str] = &[
    "BTCUSDT",
];

    pub const PYTHON_DEFAULT_BACKTEST_INTERVALS: &[&str] = &[
    "1h",
];

    pub const PYTHON_CHART_MARKET_OPTIONS: &[&str] = &[
    "Futures",
    "Spot",
];

    pub const PYTHON_ACCOUNT_MODE_OPTIONS: &[&str] = &[
    "Classic Trading",
    "Portfolio Margin",
];

    pub const PYTHON_OPTION_CATALOG_COUNT: usize = 46;
pub const PYTHON_OPTION_CATALOG_ENTRY_COUNT: usize = 267;
pub const PYTHON_UI_OPTION_CATALOG_COUNT: usize = 30;
pub const PYTHON_UI_OPTION_ENTRY_COUNT: usize = 110;

pub struct PythonOptionCatalogManifestEntry {
    pub name: &'static str,
    pub entry_count: usize,
}

pub const PYTHON_OPTION_CATALOG_MANIFEST: &[PythonOptionCatalogManifestEntry] = &[
    PythonOptionCatalogManifestEntry { name: "intervals", entry_count: 38 },
    PythonOptionCatalogManifestEntry { name: "tradingview_interval_map", entry_count: 39 },
    PythonOptionCatalogManifestEntry { name: "default_chart_symbols", entry_count: 10 },
    PythonOptionCatalogManifestEntry { name: "default_execution_symbols", entry_count: 1 },
    PythonOptionCatalogManifestEntry { name: "default_execution_intervals", entry_count: 1 },
    PythonOptionCatalogManifestEntry { name: "default_backtest_symbols", entry_count: 1 },
    PythonOptionCatalogManifestEntry { name: "default_backtest_intervals", entry_count: 1 },
    PythonOptionCatalogManifestEntry { name: "chart_market_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "account_mode_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "config_mode_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "theme_options", entry_count: 6 },
    PythonOptionCatalogManifestEntry { name: "design_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "indicator_source_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "indicator_ma_type_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "exchange_options", entry_count: 11 },
    PythonOptionCatalogManifestEntry { name: "code_language_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "rust_framework_options", entry_count: 1 },
    PythonOptionCatalogManifestEntry { name: "starter_market_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "dashboard_loop_choices", entry_count: 10 },
    PythonOptionCatalogManifestEntry { name: "lead_trader_options", entry_count: 4 },
    PythonOptionCatalogManifestEntry { name: "llm_use_for_options", entry_count: 4 },
    PythonOptionCatalogManifestEntry { name: "llm_reasoning_effort_options", entry_count: 10 },
    PythonOptionCatalogManifestEntry { name: "position_pct_units_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "dashboard_strategy_templates", entry_count: 4 },
    PythonOptionCatalogManifestEntry { name: "side_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "account_type_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "margin_mode_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "position_mode_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "assets_mode_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "order_type_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "time_in_force_options", entry_count: 4 },
    PythonOptionCatalogManifestEntry { name: "signal_logic_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "mdd_logic_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "stop_loss_modes", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "stop_loss_scopes", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "scan_scope_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "optimizer_mode_options", entry_count: 4 },
    PythonOptionCatalogManifestEntry { name: "optimizer_metric_options", entry_count: 4 },
    PythonOptionCatalogManifestEntry { name: "backtest_execution_backend_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "chart_view_options", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "positions_view_options", entry_count: 2 },
    PythonOptionCatalogManifestEntry { name: "chart_view_keys", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "rust_environment_dependencies", entry_count: 6 },
    PythonOptionCatalogManifestEntry { name: "connectors", entry_count: 14 },
    PythonOptionCatalogManifestEntry { name: "backtest_templates", entry_count: 3 },
    PythonOptionCatalogManifestEntry { name: "indicators", entry_count: 33 },
];

pub struct PythonUiOption {
    pub key: &'static str,
    pub label: &'static str,
    pub disabled: bool,
}

pub const PYTHON_DASHBOARD_LOOP_CHOICES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "30s",
        label: "30 seconds",
        disabled: false,
    },
    PythonUiOption {
        key: "45s",
        label: "45 seconds",
        disabled: false,
    },
    PythonUiOption {
        key: "1m",
        label: "1 minute",
        disabled: false,
    },
    PythonUiOption {
        key: "2m",
        label: "2 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "3m",
        label: "3 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "5m",
        label: "5 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "10m",
        label: "10 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "30m",
        label: "30 minutes",
        disabled: false,
    },
    PythonUiOption {
        key: "1h",
        label: "1 hour",
        disabled: false,
    },
    PythonUiOption {
        key: "2h",
        label: "2 hours",
        disabled: false,
    },
];

pub const PYTHON_LEAD_TRADER_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "futures_public",
        label: "Futures Public Lead Trader",
        disabled: false,
    },
    PythonUiOption {
        key: "futures_private",
        label: "Futures Private Lead Trader",
        disabled: false,
    },
    PythonUiOption {
        key: "spot_public",
        label: "Spot Public Lead Trader",
        disabled: false,
    },
    PythonUiOption {
        key: "spot_private",
        label: "Spot Private Lead Trader",
        disabled: false,
    },
];

pub const PYTHON_LLM_USE_FOR_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "advisory",
        label: "Advisory",
        disabled: false,
    },
    PythonUiOption {
        key: "signal_confirmation",
        label: "Signal confirmation",
        disabled: false,
    },
    PythonUiOption {
        key: "risk_review",
        label: "Risk review",
        disabled: false,
    },
    PythonUiOption {
        key: "backtest_explanation",
        label: "Backtest explanation",
        disabled: false,
    },
];

pub const PYTHON_LLM_REASONING_EFFORT_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "default",
        label: "default",
        disabled: false,
    },
    PythonUiOption {
        key: "disabled",
        label: "disabled",
        disabled: false,
    },
    PythonUiOption {
        key: "enabled",
        label: "enabled",
        disabled: false,
    },
    PythonUiOption {
        key: "xhigh",
        label: "xhigh",
        disabled: false,
    },
    PythonUiOption {
        key: "high",
        label: "high",
        disabled: false,
    },
    PythonUiOption {
        key: "low",
        label: "low",
        disabled: false,
    },
    PythonUiOption {
        key: "max",
        label: "max",
        disabled: false,
    },
    PythonUiOption {
        key: "medium",
        label: "medium",
        disabled: false,
    },
    PythonUiOption {
        key: "minimal",
        label: "minimal",
        disabled: false,
    },
    PythonUiOption {
        key: "none",
        label: "none",
        disabled: false,
    },
];

pub const PYTHON_POSITION_PCT_UNITS_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "percent",
        label: "percent",
        disabled: false,
    },
    PythonUiOption {
        key: "fraction",
        label: "fraction",
        disabled: false,
    },
];

pub const PYTHON_DASHBOARD_STRATEGY_TEMPLATES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "",
        label: "No Template",
        disabled: false,
    },
    PythonUiOption {
        key: "top10",
        label: "Top 10 %2 per trade 1x Isolated",
        disabled: false,
    },
    PythonUiOption {
        key: "top50",
        label: "Top 50 %2 per trade 1x",
        disabled: false,
    },
    PythonUiOption {
        key: "top100",
        label: "Top 100 %1 per trade 1x",
        disabled: false,
    },
];

pub const PYTHON_BACKTEST_TEMPLATES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "volume_top50",
        label: "First 50 Highest Volume",
        disabled: false,
    },
    PythonUiOption {
        key: "volume_last_week",
        label: "Last 1 week \u{b7} 2% per trade \u{b7} 50 highest volume",
        disabled: false,
    },
    PythonUiOption {
        key: "top100_isolated_1pct_sl",
        label: "Top 100, %2 per trade, isolated, %20 per trade SL",
        disabled: false,
    },
];

pub const PYTHON_SIDE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "BUY",
        label: "Buy (Long)",
        disabled: false,
    },
    PythonUiOption {
        key: "SELL",
        label: "Sell (Short)",
        disabled: false,
    },
    PythonUiOption {
        key: "BOTH",
        label: "Both (Long/Short)",
        disabled: false,
    },
];

pub const PYTHON_CONFIG_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Live",
        label: "Live",
        disabled: false,
    },
    PythonUiOption {
        key: "Demo",
        label: "Demo",
        disabled: false,
    },
    PythonUiOption {
        key: "Testnet",
        label: "Testnet",
        disabled: false,
    },
];

pub const PYTHON_THEME_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Light",
        label: "Light",
        disabled: false,
    },
    PythonUiOption {
        key: "Dark",
        label: "Dark",
        disabled: false,
    },
    PythonUiOption {
        key: "Blue",
        label: "Blue",
        disabled: false,
    },
    PythonUiOption {
        key: "Yellow",
        label: "Yellow",
        disabled: false,
    },
    PythonUiOption {
        key: "Green",
        label: "Green",
        disabled: false,
    },
    PythonUiOption {
        key: "Red",
        label: "Red",
        disabled: false,
    },
];

pub const PYTHON_DESIGN_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Classic",
        label: "Classic",
        disabled: false,
    },
    PythonUiOption {
        key: "Workstation",
        label: "Workstation",
        disabled: false,
    },
];

pub const PYTHON_INDICATOR_SOURCE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Binance spot",
        label: "Binance spot",
        disabled: false,
    },
    PythonUiOption {
        key: "Binance futures",
        label: "Binance futures",
        disabled: false,
    },
];

pub const PYTHON_INDICATOR_MA_TYPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "SMA",
        label: "SMA",
        disabled: false,
    },
    PythonUiOption {
        key: "EMA",
        label: "EMA",
        disabled: false,
    },
];

pub const PYTHON_EXCHANGE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Binance",
        label: "Binance",
        disabled: false,
    },
    PythonUiOption {
        key: "Bybit",
        label: "Bybit (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "OKX",
        label: "OKX (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Gate",
        label: "Gate (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Bitget",
        label: "Bitget (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "MEXC",
        label: "MEXC (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "KuCoin",
        label: "KuCoin (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "HTX",
        label: "HTX (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Crypto.com Exchange",
        label: "Crypto.com Exchange (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Kraken",
        label: "Kraken (ccxt order routing)",
        disabled: false,
    },
    PythonUiOption {
        key: "Bitfinex",
        label: "Bitfinex (ccxt order routing)",
        disabled: false,
    },
];

pub const PYTHON_ACCOUNT_TYPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Spot",
        label: "Spot",
        disabled: false,
    },
    PythonUiOption {
        key: "Futures",
        label: "Futures",
        disabled: false,
    },
];

pub const PYTHON_MARGIN_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Isolated",
        label: "Isolated",
        disabled: false,
    },
    PythonUiOption {
        key: "Cross",
        label: "Cross",
        disabled: false,
    },
];

pub const PYTHON_POSITION_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Hedge",
        label: "Hedge",
        disabled: false,
    },
    PythonUiOption {
        key: "One-way",
        label: "One-way",
        disabled: false,
    },
];

pub const PYTHON_ASSETS_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "Single-Asset",
        label: "Single-Asset Mode",
        disabled: false,
    },
    PythonUiOption {
        key: "Multi-Assets",
        label: "Multi-Assets Mode",
        disabled: false,
    },
];

pub const PYTHON_ORDER_TYPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "MARKET",
        label: "MARKET",
        disabled: false,
    },
    PythonUiOption {
        key: "LIMIT",
        label: "LIMIT",
        disabled: false,
    },
];

pub const PYTHON_TIME_IN_FORCE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "GTC",
        label: "GTC",
        disabled: false,
    },
    PythonUiOption {
        key: "IOC",
        label: "IOC",
        disabled: false,
    },
    PythonUiOption {
        key: "FOK",
        label: "FOK",
        disabled: false,
    },
    PythonUiOption {
        key: "GTD",
        label: "GTD",
        disabled: false,
    },
];

pub const PYTHON_SIGNAL_LOGIC_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "AND",
        label: "AND",
        disabled: false,
    },
    PythonUiOption {
        key: "OR",
        label: "OR",
        disabled: false,
    },
    PythonUiOption {
        key: "SEPARATE",
        label: "SEPARATE",
        disabled: false,
    },
];

pub const PYTHON_MDD_LOGIC_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "per_trade",
        label: "Per Trade MDD",
        disabled: false,
    },
    PythonUiOption {
        key: "cumulative",
        label: "Cumulative MDD",
        disabled: false,
    },
    PythonUiOption {
        key: "entire_account",
        label: "Entire Account MDD",
        disabled: false,
    },
];

pub const PYTHON_STOP_LOSS_MODES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "usdt",
        label: "USDT Based Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "percent",
        label: "Percentage Based Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "both",
        label: "Both Stop Loss (USDT & Percentage)",
        disabled: false,
    },
];

pub const PYTHON_STOP_LOSS_SCOPES: &[PythonUiOption] = &[
    PythonUiOption {
        key: "per_trade",
        label: "Per Trade Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "cumulative",
        label: "Cumulative Stop Loss",
        disabled: false,
    },
    PythonUiOption {
        key: "entire_account",
        label: "Entire Account Stop Loss",
        disabled: false,
    },
];

pub const PYTHON_SCAN_SCOPE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "selected",
        label: "selected",
        disabled: false,
    },
    PythonUiOption {
        key: "top_n",
        label: "top_n",
        disabled: false,
    },
    PythonUiOption {
        key: "all_loaded",
        label: "all_loaded",
        disabled: false,
    },
];

pub const PYTHON_OPTIMIZER_MODE_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "current",
        label: "current",
        disabled: false,
    },
    PythonUiOption {
        key: "single",
        label: "single",
        disabled: false,
    },
    PythonUiOption {
        key: "pairs",
        label: "pairs",
        disabled: false,
    },
    PythonUiOption {
        key: "combinations",
        label: "combinations",
        disabled: false,
    },
];

pub const PYTHON_OPTIMIZER_METRIC_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "roi_percent",
        label: "roi_percent",
        disabled: false,
    },
    PythonUiOption {
        key: "roi_percent_mdd",
        label: "roi_percent_mdd",
        disabled: false,
    },
    PythonUiOption {
        key: "roi_drawdown",
        label: "roi_drawdown",
        disabled: false,
    },
    PythonUiOption {
        key: "roi_value",
        label: "roi_value",
        disabled: false,
    },
];

pub const PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "local",
        label: "local",
        disabled: false,
    },
    PythonUiOption {
        key: "service",
        label: "service",
        disabled: false,
    },
];

pub const PYTHON_CHART_VIEW_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "tradingview",
        label: "TradingView",
        disabled: false,
    },
    PythonUiOption {
        key: "original",
        label: "Original",
        disabled: false,
    },
    PythonUiOption {
        key: "lightweight",
        label: "TradingView Lightweight",
        disabled: false,
    },
];

pub const PYTHON_POSITIONS_VIEW_OPTIONS: &[PythonUiOption] = &[
    PythonUiOption {
        key: "cumulative",
        label: "Cumulative View",
        disabled: false,
    },
    PythonUiOption {
        key: "per_trade",
        label: "Per Trade View",
        disabled: false,
    },
];

pub struct PythonUiOptionCatalog {
    pub name: &'static str,
    pub options: &'static [PythonUiOption],
}

pub const PYTHON_UI_OPTION_CATALOGS: &[PythonUiOptionCatalog] = &[
    PythonUiOptionCatalog { name: "dashboard loop", options: PYTHON_DASHBOARD_LOOP_CHOICES },
    PythonUiOptionCatalog { name: "lead trader", options: PYTHON_LEAD_TRADER_OPTIONS },
    PythonUiOptionCatalog { name: "LLM use-for", options: PYTHON_LLM_USE_FOR_OPTIONS },
    PythonUiOptionCatalog { name: "LLM reasoning effort", options: PYTHON_LLM_REASONING_EFFORT_OPTIONS },
    PythonUiOptionCatalog { name: "position percentage units", options: PYTHON_POSITION_PCT_UNITS_OPTIONS },
    PythonUiOptionCatalog { name: "dashboard strategy templates", options: PYTHON_DASHBOARD_STRATEGY_TEMPLATES },
    PythonUiOptionCatalog { name: "backtest templates", options: PYTHON_BACKTEST_TEMPLATES },
    PythonUiOptionCatalog { name: "side", options: PYTHON_SIDE_OPTIONS },
    PythonUiOptionCatalog { name: "config mode", options: PYTHON_CONFIG_MODE_OPTIONS },
    PythonUiOptionCatalog { name: "theme", options: PYTHON_THEME_OPTIONS },
    PythonUiOptionCatalog { name: "design", options: PYTHON_DESIGN_OPTIONS },
    PythonUiOptionCatalog { name: "indicator source", options: PYTHON_INDICATOR_SOURCE_OPTIONS },
    PythonUiOptionCatalog { name: "moving average type", options: PYTHON_INDICATOR_MA_TYPE_OPTIONS },
    PythonUiOptionCatalog { name: "exchange", options: PYTHON_EXCHANGE_OPTIONS },
    PythonUiOptionCatalog { name: "account type", options: PYTHON_ACCOUNT_TYPE_OPTIONS },
    PythonUiOptionCatalog { name: "margin mode", options: PYTHON_MARGIN_MODE_OPTIONS },
    PythonUiOptionCatalog { name: "position mode", options: PYTHON_POSITION_MODE_OPTIONS },
    PythonUiOptionCatalog { name: "assets mode", options: PYTHON_ASSETS_MODE_OPTIONS },
    PythonUiOptionCatalog { name: "order type", options: PYTHON_ORDER_TYPE_OPTIONS },
    PythonUiOptionCatalog { name: "time in force", options: PYTHON_TIME_IN_FORCE_OPTIONS },
    PythonUiOptionCatalog { name: "signal logic", options: PYTHON_SIGNAL_LOGIC_OPTIONS },
    PythonUiOptionCatalog { name: "MDD logic", options: PYTHON_MDD_LOGIC_OPTIONS },
    PythonUiOptionCatalog { name: "stop-loss modes", options: PYTHON_STOP_LOSS_MODES },
    PythonUiOptionCatalog { name: "stop-loss scopes", options: PYTHON_STOP_LOSS_SCOPES },
    PythonUiOptionCatalog { name: "scan scope", options: PYTHON_SCAN_SCOPE_OPTIONS },
    PythonUiOptionCatalog { name: "optimizer mode", options: PYTHON_OPTIMIZER_MODE_OPTIONS },
    PythonUiOptionCatalog { name: "optimizer metric", options: PYTHON_OPTIMIZER_METRIC_OPTIONS },
    PythonUiOptionCatalog { name: "backtest execution backend", options: PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS },
    PythonUiOptionCatalog { name: "chart view", options: PYTHON_CHART_VIEW_OPTIONS },
    PythonUiOptionCatalog { name: "positions view", options: PYTHON_POSITIONS_VIEW_OPTIONS },
];

    pub struct PythonStarterOption {
    pub key: &'static str,
    pub title: &'static str,
    pub subtitle: &'static str,
    pub accent: &'static str,
    pub badge: &'static str,
    pub disabled: bool,
    pub operational: bool,
    pub operational_status: &'static str,
    pub launch_note: &'static str,
}

pub const PYTHON_CODE_LANGUAGE_OPTIONS: &[PythonStarterOption] = &[
    PythonStarterOption {
        key: "Python (PyQt)",
        title: "Python",
        subtitle: "Fast to build - Huge ecosystem",
        accent: "#3b82f6",
        badge: "Recommended",
        disabled: false,
        operational: false,
        operational_status: "",
        launch_note: "",
    },
    PythonStarterOption {
        key: "C++ (Qt/C++23)",
        title: "C++",
        subtitle: "Qt native desktop experiment",
        accent: "#38bdf8",
        badge: "Experiment",
        disabled: false,
        operational: false,
        operational_status: "",
        launch_note: "",
    },
    PythonStarterOption {
        key: "Rust",
        title: "Rust",
        subtitle: "Service API client + guarded runtime (promotion-gated)",
        accent: "#fb923c",
        badge: "Experiment",
        disabled: false,
        operational: false,
        operational_status: "",
        launch_note: "",
    },
];

pub const PYTHON_RUST_FRAMEWORK_OPTIONS: &[PythonStarterOption] = &[
    PythonStarterOption {
        key: "Tauri",
        title: "Tauri",
        subtitle: "Operational Service API client",
        accent: "#f59e0b",
        badge: "Primary",
        disabled: false,
        operational: true,
        operational_status: "Interactive Service API client",
        launch_note: "Tauri can manage/connect to the local Python Service API, but Python still owns strategy, risk, account, order, and exchange execution.",
    },
];

pub const PYTHON_STARTER_MARKET_OPTIONS: &[PythonStarterOption] = &[
    PythonStarterOption {
        key: "crypto",
        title: "Crypto Exchange",
        subtitle: "Binance, Bybit, KuCoin",
        accent: "#34d399",
        badge: "",
        disabled: false,
        operational: false,
        operational_status: "",
        launch_note: "",
    },
    PythonStarterOption {
        key: "forex",
        title: "Forex Exchange",
        subtitle: "REST, MT4 bridge, MetaTrader 5, and scoped provider APIs",
        accent: "#93c5fd",
        badge: "Evidence required",
        disabled: false,
        operational: false,
        operational_status: "",
        launch_note: "",
    },
];

}

pub use generated::*;
