// This file is generated from Languages/Python/app/native_parity.py.
// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.
#pragma once

#include <array>
#include <cstddef>
#include <string_view>

namespace PythonParityContract {

inline constexpr std::string_view kPythonSource = "Languages/Python";
inline constexpr unsigned kPythonSourceSchemaVersion = 1;
inline constexpr std::string_view kPythonSourceContractHash = "e058aeecd592aecd3667108762a794b07fcd9378cda66246de1569bf8999689a";
inline constexpr bool kCppContractParityReady = true;
inline constexpr bool kRustContractParityReady = true;
inline constexpr bool kCppStandaloneRuntimeReady = false;
inline constexpr bool kRustStandaloneRuntimeReady = false;
inline constexpr bool kCppFullParityReady = false;
inline constexpr bool kRustFullParityReady = false;
inline constexpr std::string_view kPythonDefaultExecutionJson = "{\"account_mode\":\"Classic Trading\",\"account_type\":\"Futures\",\"assets_mode\":\"Single-Asset\",\"backtest_symbol_interval_pairs\":[],\"connector_order_block_circuit_breaker_enabled\":true,\"connector_order_block_pause_threshold\":2,\"connector_order_block_window_seconds\":60.0,\"connector_order_circuit_incident_log_backup_count\":1,\"connector_order_circuit_incident_log_max_bytes\":2097152,\"connector_order_circuit_incident_log_path\":\"\",\"gtd_minutes\":30,\"intervals\":[\"1m\"],\"lead_trader_enabled\":false,\"lead_trader_profile\":null,\"leverage\":1,\"live_allow_auto_bump_to_min_order\":false,\"live_trading_acknowledgement\":\"\",\"live_trading_enabled\":false,\"live_trading_max_leverage\":20,\"live_trading_max_position_pct\":10.0,\"live_trading_max_session_orders\":100,\"lookback\":200,\"loop_interval_override\":\"1m\",\"margin_mode\":\"Isolated\",\"mode\":\"Demo/Testnet\",\"operational_account_snapshot_stale_seconds\":300.0,\"operational_connector_snapshot_stale_seconds\":120.0,\"operational_execution_heartbeat_stale_seconds\":10.0,\"operational_live_order_gate_enabled\":true,\"operational_live_start_gate_enabled\":true,\"operational_portfolio_snapshot_stale_seconds\":300.0,\"order_audit_backup_count\":1,\"order_audit_enabled\":true,\"order_audit_log_path\":\"\",\"order_audit_max_bytes\":10485760,\"order_type\":\"MARKET\",\"position_mode\":\"Hedge\",\"position_pct\":2.0,\"runtime_symbol_interval_pairs\":[],\"side\":\"BOTH\",\"stop_without_close\":false,\"symbols\":[\"BTCUSDT\"],\"tif\":\"GTC\"}";
inline constexpr std::string_view kPythonDefaultBacktestJson = "{\"account_mode\":\"Classic Trading\",\"assets_mode\":\"Single-Asset\",\"capital\":1000.0,\"connector_backend\":\"binance-sdk-derivatives-trading-usds-futures\",\"end_date\":null,\"execution_backend\":\"local\",\"fee_bps\":5.0,\"indicators\":{\"adx\":{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"},\"ao\":{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34},\"aroon\":{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50},\"atr\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"},\"bb\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2},\"bbw\":{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2},\"cci\":{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100},\"chop\":{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8},\"cmf\":{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05},\"dmi\":{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0},\"donchian\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"ema\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"ichimoku\":{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52},\"keltner\":{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"kst\":{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15},\"ma\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"},\"macd\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"mfi\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80},\"natr\":{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0},\"obv\":{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"},\"ppo\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"psar\":{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"roc\":{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0},\"rsi\":{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70},\"rvol\":{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75},\"stoch_rsi\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"stochastic\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"supertrend\":{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"trix\":{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0},\"uo\":{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7},\"volume\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"},\"vwap\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"willr\":{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20}},\"intervals\":[\"1h\"],\"leverage\":20,\"logic\":\"AND\",\"margin_mode\":\"Isolated\",\"mdd_logic\":\"per_trade\",\"optimizer_combo_size\":2,\"optimizer_max_duration_seconds\":14400,\"optimizer_metric\":\"roi_percent\",\"optimizer_min_trades\":1,\"optimizer_mode\":\"current\",\"position_mode\":\"Hedge\",\"position_pct\":2.0,\"scan_auto_apply\":false,\"scan_mdd_limit\":10.0,\"scan_scope\":\"selected\",\"scan_top_n\":200,\"side\":\"BOTH\",\"slippage_bps\":2.0,\"start_date\":null,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"symbol_source\":\"Futures\",\"symbols\":[\"BTCUSDT\"],\"template\":{\"enabled\":false,\"name\":null}}";
inline constexpr std::string_view kPythonOptionCatalogsJson = "{\"account_mode_options\":[\"Classic Trading\",\"Portfolio Margin\"],\"account_type_options\":[{\"key\":\"Spot\",\"label\":\"Spot\",\"value\":\"Spot\"},{\"key\":\"Futures\",\"label\":\"Futures\",\"value\":\"Futures\"}],\"assets_mode_options\":[{\"key\":\"Single-Asset\",\"label\":\"Single-Asset Mode\",\"value\":\"Single-Asset\"},{\"key\":\"Multi-Assets\",\"label\":\"Multi-Assets Mode\",\"value\":\"Multi-Assets\"}],\"backtest_execution_backend_options\":[{\"key\":\"local\",\"label\":\"local\",\"value\":\"local\"},{\"key\":\"service\",\"label\":\"service\",\"value\":\"service\"}],\"backtest_templates\":[{\"key\":\"volume_top50\",\"label\":\"First 50 Highest Volume\"},{\"key\":\"volume_last_week\",\"label\":\"Last 1 week \\u00b7 2% per trade \\u00b7 50 highest volume\"},{\"key\":\"top100_isolated_1pct_sl\",\"label\":\"Top 100, %2 per trade, isolated, %20 per trade SL\"}],\"chart_market_options\":[\"Futures\",\"Spot\"],\"chart_view_keys\":[\"tradingview\",\"original\",\"lightweight\"],\"chart_view_options\":[{\"key\":\"tradingview\",\"label\":\"TradingView\",\"value\":\"tradingview\"},{\"key\":\"original\",\"label\":\"Original\",\"value\":\"original\"},{\"key\":\"lightweight\",\"label\":\"TradingView Lightweight\",\"value\":\"lightweight\"}],\"code_language_options\":[{\"accent\":\"#3b82f6\",\"badge\":\"Recommended\",\"disabled\":false,\"key\":\"Python (PyQt)\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Fast to build - Huge ecosystem\",\"title\":\"Python\"},{\"accent\":\"#38bdf8\",\"badge\":\"Experiment\",\"disabled\":false,\"key\":\"C++ (Qt/C++23)\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Qt native desktop experiment\",\"title\":\"C++\"},{\"accent\":\"#fb923c\",\"badge\":\"Experiment\",\"disabled\":false,\"key\":\"Rust\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Service API client + guarded runtime (promotion-gated)\",\"title\":\"Rust\"}],\"config_mode_options\":[{\"key\":\"Live\",\"label\":\"Live\",\"value\":\"Live\"},{\"key\":\"Demo\",\"label\":\"Demo\",\"value\":\"Demo\"},{\"key\":\"Testnet\",\"label\":\"Testnet\",\"value\":\"Testnet\"}],\"connectors\":[{\"key\":\"binance-sdk-derivatives-trading-usds-futures\",\"label\":\"Binance SDK Derivatives Trading USD\\u24c8 Futures (Official Recommended)\"},{\"key\":\"binance-sdk-derivatives-trading-coin-futures\",\"label\":\"Binance SDK Derivatives Trading COIN-M Futures\"},{\"key\":\"binance-sdk-spot\",\"label\":\"Binance SDK Spot (Official Recommended)\"},{\"key\":\"binance-connector\",\"label\":\"Binance Connector Python\"},{\"key\":\"ccxt\",\"label\":\"CCXT (Unified)\"},{\"key\":\"oanda-rest\",\"label\":\"OANDA REST-v20\"},{\"key\":\"fxcmpy\",\"label\":\"FXCM fxcmpy\"},{\"key\":\"ig-rest\",\"label\":\"IG REST Trading API\"},{\"key\":\"citic-ctp\",\"label\":\"CITIC Futures CTP (Local/Remote TCP Front)\"},{\"key\":\"metatrader4-bridge\",\"label\":\"MetaTrader 4 Bridge (Local/Remote Expert Advisor)\"},{\"key\":\"metatrader5\",\"label\":\"MetaTrader 5 (Official Python Integration)\"},{\"key\":\"trading212-public-api\",\"label\":\"Trading 212 Public API (Invest/Stocks ISA equities)\"},{\"key\":\"moomoo-opend\",\"label\":\"moomoo OpenD (Local/Remote Gateway)\"},{\"key\":\"python-binance\",\"label\":\"python-binance (Community)\"}],\"dashboard_loop_choices\":[{\"key\":\"30s\",\"label\":\"30 seconds\",\"value\":\"30s\"},{\"key\":\"45s\",\"label\":\"45 seconds\",\"value\":\"45s\"},{\"key\":\"1m\",\"label\":\"1 minute\",\"value\":\"1m\"},{\"key\":\"2m\",\"label\":\"2 minutes\",\"value\":\"2m\"},{\"key\":\"3m\",\"label\":\"3 minutes\",\"value\":\"3m\"},{\"key\":\"5m\",\"label\":\"5 minutes\",\"value\":\"5m\"},{\"key\":\"10m\",\"label\":\"10 minutes\",\"value\":\"10m\"},{\"key\":\"30m\",\"label\":\"30 minutes\",\"value\":\"30m\"},{\"key\":\"1h\",\"label\":\"1 hour\",\"value\":\"1h\"},{\"key\":\"2h\",\"label\":\"2 hours\",\"value\":\"2h\"}],\"dashboard_strategy_templates\":[{\"key\":\"\",\"label\":\"No Template\"},{\"key\":\"top10\",\"label\":\"Top 10 %2 per trade 1x Isolated\"},{\"key\":\"top50\",\"label\":\"Top 50 %2 per trade 1x\"},{\"key\":\"top100\",\"label\":\"Top 100 %1 per trade 1x\"}],\"default_backtest_intervals\":[\"1h\"],\"default_backtest_symbols\":[\"BTCUSDT\"],\"default_chart_symbols\":[\"BTCUSDT\",\"ETHUSDT\",\"BNBUSDT\",\"SOLUSDT\",\"XRPUSDT\",\"ADAUSDT\",\"DOGEUSDT\",\"AVAXUSDT\",\"LINKUSDT\",\"TRXUSDT\"],\"default_execution_intervals\":[\"1m\"],\"default_execution_symbols\":[\"BTCUSDT\"],\"design_options\":[{\"key\":\"Classic\",\"label\":\"Classic\",\"value\":\"Classic\"},{\"key\":\"Workstation\",\"label\":\"Workstation\",\"value\":\"Workstation\"}],\"exchange_options\":[{\"badge\":\"\",\"disabled\":false,\"key\":\"Binance\",\"label\":\"Binance\",\"title\":\"Binance\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Bybit\",\"label\":\"Bybit (ccxt order routing)\",\"title\":\"Bybit\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"OKX\",\"label\":\"OKX (ccxt order routing)\",\"title\":\"OKX\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Gate\",\"label\":\"Gate (ccxt order routing)\",\"title\":\"Gate\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Bitget\",\"label\":\"Bitget (ccxt order routing)\",\"title\":\"Bitget\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"MEXC\",\"label\":\"MEXC (ccxt order routing)\",\"title\":\"MEXC\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"KuCoin\",\"label\":\"KuCoin (ccxt order routing)\",\"title\":\"KuCoin\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"HTX\",\"label\":\"HTX (ccxt order routing)\",\"title\":\"HTX\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Crypto.com Exchange\",\"label\":\"Crypto.com Exchange (ccxt order routing)\",\"title\":\"Crypto.com Exchange\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Kraken\",\"label\":\"Kraken (ccxt order routing)\",\"title\":\"Kraken\"},{\"badge\":\"ccxt order routing\",\"disabled\":false,\"key\":\"Bitfinex\",\"label\":\"Bitfinex (ccxt order routing)\",\"title\":\"Bitfinex\"}],\"indicator_ma_type_options\":[{\"key\":\"SMA\",\"label\":\"SMA\",\"value\":\"SMA\"},{\"key\":\"EMA\",\"label\":\"EMA\",\"value\":\"EMA\"}],\"indicator_source_options\":[{\"key\":\"Binance spot\",\"label\":\"Binance spot\",\"value\":\"Binance spot\"},{\"key\":\"Binance futures\",\"label\":\"Binance futures\",\"value\":\"Binance futures\"}],\"indicators\":[{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"},\"default_enabled\":false,\"display_name\":\"Moving Average (MA)\",\"key\":\"ma\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"type\":\"SMA\"},\"runtime_output_keys\":[\"ma\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"default_enabled\":false,\"display_name\":\"Donchian Channels (DC)\",\"key\":\"donchian\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"donchian_high\",\"donchian_low\",\"donchian\"]},{\"backtest_config\":{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"Parabolic SAR (PSAR)\",\"key\":\"psar\",\"runtime_config\":{\"af\":0.02,\"buy_value\":null,\"enabled\":false,\"max_af\":0.2,\"sell_value\":null},\"runtime_output_keys\":[\"psar\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2},\"default_enabled\":false,\"display_name\":\"Bollinger Bands (BB)\",\"key\":\"bb\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2},\"runtime_output_keys\":[\"bb_upper\",\"bb_mid\",\"bb_lower\"]},{\"backtest_config\":{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2},\"default_enabled\":false,\"display_name\":\"Bollinger Band Width (BBW)\",\"key\":\"bbw\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2},\"runtime_output_keys\":[\"bbw\"]},{\"backtest_config\":{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"},\"default_enabled\":false,\"display_name\":\"Keltner Channels (KC)\",\"key\":\"keltner\",\"runtime_config\":{\"atr_length\":10,\"buy_value\":null,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":null},\"runtime_output_keys\":[\"keltner_upper\",\"keltner_mid\",\"keltner_lower\"]},{\"backtest_config\":{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52},\"default_enabled\":false,\"display_name\":\"Ichimoku Cloud (IC)\",\"key\":\"ichimoku\",\"runtime_config\":{\"base_length\":26,\"buy_value\":null,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":null,\"span_b_length\":52},\"runtime_output_keys\":[\"ichimoku_tenkan\",\"ichimoku_kijun\",\"ichimoku_span_a\",\"ichimoku_span_b\",\"ichimoku_chikou\",\"ichimoku\"]},{\"backtest_config\":{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70},\"default_enabled\":true,\"display_name\":\"Relative Strength Index (RSI)\",\"key\":\"rsi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":true,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"rsi\"]},{\"backtest_config\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"},\"default_enabled\":false,\"display_name\":\"Volume\",\"key\":\"volume\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"sell_value\":null},\"runtime_output_keys\":[\"volume\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"},\"default_enabled\":false,\"display_name\":\"On-Balance Volume (OBV)\",\"key\":\"obv\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"sell_value\":null},\"runtime_output_keys\":[\"obv\"]},{\"backtest_config\":{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75},\"default_enabled\":false,\"display_name\":\"Relative Volume (RVOL)\",\"key\":\"rvol\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"rvol\"]},{\"backtest_config\":{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05},\"default_enabled\":false,\"display_name\":\"Chaikin Money Flow (CMF)\",\"key\":\"cmf\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"cmf\"]},{\"backtest_config\":{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100},\"default_enabled\":false,\"display_name\":\"Commodity Channel Index (CCI)\",\"key\":\"cci\",\"runtime_config\":{\"buy_value\":null,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"cci\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0},\"default_enabled\":false,\"display_name\":\"Rate of Change (ROC)\",\"key\":\"roc\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":12,\"sell_value\":null},\"runtime_output_keys\":[\"roc\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0},\"default_enabled\":false,\"display_name\":\"Triple Exponential Average (TRIX)\",\"key\":\"trix\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":15,\"sell_value\":null},\"runtime_output_keys\":[\"trix\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"default_enabled\":false,\"display_name\":\"Percentage Price Oscillator (PPO)\",\"key\":\"ppo\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26},\"runtime_output_keys\":[\"ppo\",\"ppo_signal\",\"ppo_hist\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34},\"default_enabled\":false,\"display_name\":\"Awesome Oscillator (AO)\",\"key\":\"ao\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"fast\":5,\"sell_value\":null,\"slow\":34},\"runtime_output_keys\":[\"ao\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15},\"default_enabled\":false,\"display_name\":\"Know Sure Thing (KST)\",\"key\":\"kst\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":null,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15},\"runtime_output_keys\":[\"kst\",\"kst_signal\",\"kst_hist\"]},{\"backtest_config\":{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50},\"default_enabled\":false,\"display_name\":\"Aroon Oscillator (AROON)\",\"key\":\"aroon\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":25,\"sell_value\":null},\"runtime_output_keys\":[\"aroon_up\",\"aroon_down\",\"aroon\"]},{\"backtest_config\":{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8},\"default_enabled\":false,\"display_name\":\"Choppiness Index (CHOP)\",\"key\":\"chop\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"chop\"]},{\"backtest_config\":{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"},\"default_enabled\":false,\"display_name\":\"Average True Range (ATR)\",\"key\":\"atr\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"atr\"]},{\"backtest_config\":{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0},\"default_enabled\":false,\"display_name\":\"Normalized Average True Range (NATR)\",\"key\":\"natr\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"natr\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"Volume Weighted Average Price (VWAP)\",\"key\":\"vwap\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"vwap\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80},\"default_enabled\":false,\"display_name\":\"Money Flow Index (MFI)\",\"key\":\"mfi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"mfi\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"default_enabled\":false,\"display_name\":\"Stochastic RSI (SRSI)\",\"key\":\"stoch_rsi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3},\"runtime_output_keys\":[\"stoch_rsi\",\"stoch_rsi_k\",\"stoch_rsi_d\"]},{\"backtest_config\":{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20},\"default_enabled\":false,\"display_name\":\"Williams %R\",\"key\":\"willr\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"willr\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26},\"default_enabled\":false,\"display_name\":\"Moving Average Convergence/Divergence (MACD)\",\"key\":\"macd\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26},\"runtime_output_keys\":[\"macd_line\",\"macd_signal\"]},{\"backtest_config\":{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7},\"default_enabled\":false,\"display_name\":\"Ultimate Oscillator (UO)\",\"key\":\"uo\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":null,\"short\":7},\"runtime_output_keys\":[\"uo\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"},\"default_enabled\":false,\"display_name\":\"Average Directional Index (ADX)\",\"key\":\"adx\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"adx\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0},\"default_enabled\":false,\"display_name\":\"Directional Movement Index (DMI)\",\"key\":\"dmi\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null},\"runtime_output_keys\":[\"dmi_plus\",\"dmi_minus\",\"dmi\"]},{\"backtest_config\":{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"SuperTrend (ST)\",\"key\":\"supertrend\",\"runtime_config\":{\"atr_period\":10,\"buy_value\":null,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":null},\"runtime_output_keys\":[\"supertrend\"]},{\"backtest_config\":{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"},\"default_enabled\":false,\"display_name\":\"Exponential Moving Average (EMA)\",\"key\":\"ema\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null},\"runtime_output_keys\":[\"ema\"]},{\"backtest_config\":{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3},\"default_enabled\":false,\"display_name\":\"Stochastic Oscillator\",\"key\":\"stochastic\",\"runtime_config\":{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3},\"runtime_output_keys\":[\"stochastic\",\"stochastic_k\",\"stochastic_d\"]}],\"intervals\":[\"1m\",\"3m\",\"5m\",\"10m\",\"15m\",\"20m\",\"30m\",\"1h\",\"2h\",\"3h\",\"4h\",\"5h\",\"6h\",\"7h\",\"8h\",\"9h\",\"10h\",\"11h\",\"12h\",\"1d\",\"2d\",\"3d\",\"4d\",\"5d\",\"6d\",\"1w\",\"2w\",\"3w\",\"1month\",\"2months\",\"3months\",\"6months\",\"1mo\",\"2mo\",\"3mo\",\"6mo\",\"1y\",\"2y\"],\"lead_trader_options\":[{\"key\":\"futures_public\",\"label\":\"Futures Public Lead Trader\",\"value\":\"futures_public\"},{\"key\":\"futures_private\",\"label\":\"Futures Private Lead Trader\",\"value\":\"futures_private\"},{\"key\":\"spot_public\",\"label\":\"Spot Public Lead Trader\",\"value\":\"spot_public\"},{\"key\":\"spot_private\",\"label\":\"Spot Private Lead Trader\",\"value\":\"spot_private\"}],\"llm_reasoning_effort_options\":[{\"key\":\"default\",\"label\":\"default\",\"value\":\"default\"},{\"key\":\"disabled\",\"label\":\"disabled\",\"value\":\"disabled\"},{\"key\":\"enabled\",\"label\":\"enabled\",\"value\":\"enabled\"},{\"key\":\"xhigh\",\"label\":\"xhigh\",\"value\":\"xhigh\"},{\"key\":\"high\",\"label\":\"high\",\"value\":\"high\"},{\"key\":\"low\",\"label\":\"low\",\"value\":\"low\"},{\"key\":\"max\",\"label\":\"max\",\"value\":\"max\"},{\"key\":\"medium\",\"label\":\"medium\",\"value\":\"medium\"},{\"key\":\"minimal\",\"label\":\"minimal\",\"value\":\"minimal\"},{\"key\":\"none\",\"label\":\"none\",\"value\":\"none\"}],\"llm_use_for_options\":[{\"key\":\"advisory\",\"label\":\"Advisory\",\"value\":\"advisory\"},{\"key\":\"signal_confirmation\",\"label\":\"Signal confirmation\",\"value\":\"signal_confirmation\"},{\"key\":\"risk_review\",\"label\":\"Risk review\",\"value\":\"risk_review\"},{\"key\":\"backtest_explanation\",\"label\":\"Backtest explanation\",\"value\":\"backtest_explanation\"}],\"margin_mode_options\":[{\"key\":\"Isolated\",\"label\":\"Isolated\",\"value\":\"Isolated\"},{\"key\":\"Cross\",\"label\":\"Cross\",\"value\":\"Cross\"}],\"mdd_logic_options\":[{\"key\":\"per_trade\",\"label\":\"Per Trade MDD\"},{\"key\":\"cumulative\",\"label\":\"Cumulative MDD\"},{\"key\":\"entire_account\",\"label\":\"Entire Account MDD\"}],\"optimizer_metric_options\":[{\"key\":\"roi_percent\",\"label\":\"roi_percent\",\"value\":\"roi_percent\"},{\"key\":\"roi_percent_mdd\",\"label\":\"roi_percent_mdd\",\"value\":\"roi_percent_mdd\"},{\"key\":\"roi_drawdown\",\"label\":\"roi_drawdown\",\"value\":\"roi_drawdown\"},{\"key\":\"roi_value\",\"label\":\"roi_value\",\"value\":\"roi_value\"}],\"optimizer_mode_options\":[{\"key\":\"current\",\"label\":\"current\",\"value\":\"current\"},{\"key\":\"single\",\"label\":\"single\",\"value\":\"single\"},{\"key\":\"pairs\",\"label\":\"pairs\",\"value\":\"pairs\"},{\"key\":\"combinations\",\"label\":\"combinations\",\"value\":\"combinations\"}],\"order_type_options\":[{\"key\":\"MARKET\",\"label\":\"MARKET\",\"value\":\"MARKET\"},{\"key\":\"LIMIT\",\"label\":\"LIMIT\",\"value\":\"LIMIT\"}],\"position_mode_options\":[{\"key\":\"Hedge\",\"label\":\"Hedge\",\"value\":\"Hedge\"},{\"key\":\"One-way\",\"label\":\"One-way\",\"value\":\"One-way\"}],\"position_pct_units_options\":[{\"key\":\"percent\",\"label\":\"percent\",\"value\":\"percent\"},{\"key\":\"fraction\",\"label\":\"fraction\",\"value\":\"fraction\"}],\"positions_view_options\":[{\"key\":\"cumulative\",\"label\":\"Cumulative View\",\"value\":\"cumulative\"},{\"key\":\"per_trade\",\"label\":\"Per Trade View\",\"value\":\"per_trade\"}],\"rust_environment_dependencies\":[{\"key\":\"rustc\",\"kind\":\"rust_rustc\",\"label\":\"rustc\",\"latest\":\"Install rustup\",\"path\":\"\",\"usage\":\"\"},{\"key\":\"cargo\",\"kind\":\"rust_cargo\",\"label\":\"cargo\",\"latest\":\"Install rustup\",\"path\":\"\",\"usage\":\"\"},{\"key\":\"experiments/rust-shells/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"Trading Bot Rust workspace\",\"latest\":\"\",\"path\":\"experiments/rust-shells/Cargo.toml\",\"usage\":\"Active\"},{\"key\":\"experiments/rust-shells/crates/core/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"trading-bot-core\",\"latest\":\"\",\"path\":\"experiments/rust-shells/crates/core/Cargo.toml\",\"usage\":\"Active\"},{\"key\":\"experiments/rust-shells/crates/contracts/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"trading-bot-contracts\",\"latest\":\"\",\"path\":\"experiments/rust-shells/crates/contracts/Cargo.toml\",\"usage\":\"Active\"},{\"key\":\"experiments/rust-shells/apps/tauri-desktop/Cargo.toml\",\"kind\":\"rust_file_version\",\"label\":\"Tauri (Primary)\",\"latest\":\"\",\"path\":\"experiments/rust-shells/apps/tauri-desktop/Cargo.toml\",\"usage\":\"Active\"}],\"rust_framework_options\":[{\"accent\":\"#f59e0b\",\"badge\":\"Primary\",\"disabled\":false,\"key\":\"Tauri\",\"launch_note\":\"Tauri can manage/connect to the local Python Service API, but Python still owns strategy, risk, account, order, and exchange execution.\",\"operational\":true,\"operational_status\":\"Interactive Service API client\",\"subtitle\":\"Operational Service API client\",\"title\":\"Tauri\"}],\"scan_scope_options\":[{\"key\":\"selected\",\"label\":\"selected\",\"value\":\"selected\"},{\"key\":\"top_n\",\"label\":\"top_n\",\"value\":\"top_n\"},{\"key\":\"all_loaded\",\"label\":\"all_loaded\",\"value\":\"all_loaded\"}],\"side_options\":[{\"key\":\"BUY\",\"label\":\"Buy (Long)\"},{\"key\":\"SELL\",\"label\":\"Sell (Short)\"},{\"key\":\"BOTH\",\"label\":\"Both (Long/Short)\"}],\"signal_logic_options\":[{\"key\":\"AND\",\"label\":\"AND\",\"value\":\"AND\"},{\"key\":\"OR\",\"label\":\"OR\",\"value\":\"OR\"},{\"key\":\"SEPARATE\",\"label\":\"SEPARATE\",\"value\":\"SEPARATE\"}],\"starter_market_options\":[{\"accent\":\"#34d399\",\"badge\":\"\",\"disabled\":false,\"key\":\"crypto\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"Binance, Bybit, KuCoin\",\"title\":\"Crypto Exchange\"},{\"accent\":\"#93c5fd\",\"badge\":\"Evidence required\",\"disabled\":false,\"key\":\"forex\",\"launch_note\":\"\",\"operational\":false,\"operational_status\":\"\",\"subtitle\":\"REST, MT4 bridge, MetaTrader 5, and scoped provider APIs\",\"title\":\"Forex Exchange\"}],\"stop_loss_modes\":[{\"key\":\"usdt\",\"label\":\"USDT Based Stop Loss\"},{\"key\":\"percent\",\"label\":\"Percentage Based Stop Loss\"},{\"key\":\"both\",\"label\":\"Both Stop Loss (USDT & Percentage)\"}],\"stop_loss_scopes\":[{\"key\":\"per_trade\",\"label\":\"Per Trade Stop Loss\"},{\"key\":\"cumulative\",\"label\":\"Cumulative Stop Loss\"},{\"key\":\"entire_account\",\"label\":\"Entire Account Stop Loss\"}],\"theme_options\":[{\"key\":\"Light\",\"label\":\"Light\",\"value\":\"Light\"},{\"key\":\"Dark\",\"label\":\"Dark\",\"value\":\"Dark\"},{\"key\":\"Blue\",\"label\":\"Blue\",\"value\":\"Blue\"},{\"key\":\"Yellow\",\"label\":\"Yellow\",\"value\":\"Yellow\"},{\"key\":\"Green\",\"label\":\"Green\",\"value\":\"Green\"},{\"key\":\"Red\",\"label\":\"Red\",\"value\":\"Red\"}],\"time_in_force_options\":[{\"key\":\"GTC\",\"label\":\"GTC\",\"value\":\"GTC\"},{\"key\":\"IOC\",\"label\":\"IOC\",\"value\":\"IOC\"},{\"key\":\"FOK\",\"label\":\"FOK\",\"value\":\"FOK\"},{\"key\":\"GTD\",\"label\":\"GTD\",\"value\":\"GTD\"}],\"tradingview_interval_map\":{\"10h\":\"600\",\"10m\":\"10\",\"11h\":\"660\",\"12h\":\"720\",\"15m\":\"15\",\"1d\":\"1D\",\"1h\":\"60\",\"1m\":\"1\",\"1mo\":\"1M\",\"1month\":\"1M\",\"1w\":\"1W\",\"1y\":\"12M\",\"20m\":\"20\",\"2d\":\"2D\",\"2h\":\"120\",\"2mo\":\"2M\",\"2months\":\"2M\",\"2w\":\"2W\",\"2y\":\"24M\",\"30m\":\"30\",\"3d\":\"3D\",\"3h\":\"180\",\"3m\":\"3\",\"3mo\":\"3M\",\"3months\":\"3M\",\"3w\":\"3W\",\"45m\":\"45\",\"4d\":\"4D\",\"4h\":\"240\",\"5d\":\"5D\",\"5h\":\"300\",\"5m\":\"5\",\"6d\":\"6D\",\"6h\":\"360\",\"6mo\":\"6M\",\"6months\":\"6M\",\"7h\":\"420\",\"8h\":\"480\",\"9h\":\"540\"}}";

struct PythonRuntimeConfigReferenceCase {
    std::string_view name;
    std::string_view inputJson;
    std::string_view expectedJson;
    bool valid;
    std::string_view expectedError;
};

inline constexpr std::array<PythonRuntimeConfigReferenceCase, 214> kPythonRuntimeConfigReferenceCases = {
    PythonRuntimeConfigReferenceCase{"alias-rich-runtime", "{\"account_mode\":\"portfolio margin\",\"account_type\":\"futures\",\"assets_mode\":\"multi-asset\",\"backtest\":{\"account_mode\":\"classic trading\",\"assets_mode\":\"single-asset mode\",\"capital\":\"1000\",\"connector_backend\":\"binance-sdk-spot\",\"end_date\":\"2026-02-01\",\"execution_backend\":\"desktop-local\",\"fee_bps\":5.0,\"indicators\":{},\"intervals\":[\"15 minutes\",\"1M\"],\"leverage\":20,\"logic\":\"or\",\"margin_mode\":\"isolated\",\"mdd_logic\":\"per_trade\",\"optimizer_combo_size\":2,\"optimizer_max_duration_seconds\":7200,\"optimizer_metric\":\"roi-percent-mdd\",\"optimizer_min_trades\":1,\"optimizer_mode\":\"pairs\",\"position_mode\":\"hedge\",\"position_pct\":\"2.0\",\"scan_auto_apply\":\"false\",\"scan_mdd_limit\":20,\"scan_scope\":\"top_n\",\"scan_top_n\":200,\"side\":\"both\",\"slippage_bps\":2.0,\"start_date\":\"2026-01-01\",\"stop_loss\":{\"mode\":\"percent\",\"scope\":\"entire_account\"},\"symbol_source\":\"futures\",\"symbols\":[\"btcusdt\",\"BTCUSDT\"],\"template\":{}},\"backtest_symbol_interval_pairs\":null,\"chart\":{\"auto_follow\":\"yes\",\"interval\":\"1M\",\"market\":\"spot\",\"symbol\":\"ethusdt\",\"view_mode\":\"TradingView Lightweight\"},\"connector_backend\":\"CCXT (Unified)\",\"design\":\"workstation\",\"indicator_source\":\"binance futures\",\"intervals\":[\"1M\",\"2 hours\"],\"live_allow_auto_bump_to_min_order\":\"yes\",\"live_trading_enabled\":\"false\",\"live_trading_max_leverage\":20,\"live_trading_max_position_pct\":\"4.0\",\"live_trading_max_session_orders\":\"25\",\"llm_allow_public_network\":\"false\",\"llm_base_url\":\"http://127.0.0.1:11434/v1\",\"llm_enabled\":\"true\",\"llm_model\":\"local-model\",\"llm_provider\":\"chatgpt\",\"llm_reasoning_effort\":\"extra-high\",\"llm_use_for\":\"risk_review\",\"loop_interval_override\":\"1 hour\",\"margin_mode\":\"cross\",\"mode\":\"live\",\"order_audit_enabled\":\"no\",\"order_type\":\"limit\",\"position_mode\":\"oneway\",\"position_pct\":\"2.5\",\"runtime_symbol_interval_pairs\":[{\"interval\":\"15 minutes\",\"strategy_controls\":{\"leverage\":20,\"loop_interval_override\":\"1 hour\",\"side\":\"buy\",\"stop_loss\":{\"scope\":\"bad-scope\"}},\"symbol\":\"btcusdt\"}],\"selected_exchange\":\"kucoin\",\"side\":\"sell\",\"stop_loss\":{\"mode\":\"percent\",\"scope\":\"entire_account\"},\"symbols\":[\"ethusdt\",\"ETHUSDT\"],\"theme\":\"green\",\"tif\":\"ioc\"}", "{\"account_mode\":\"Portfolio Margin\",\"account_type\":\"Futures\",\"assets_mode\":\"Multi-Assets\",\"backtest\":{\"account_mode\":\"Classic Trading\",\"assets_mode\":\"Single-Asset\",\"capital\":1000.0,\"connector_backend\":\"binance-sdk-spot\",\"end_date\":\"2026-02-01\",\"execution_backend\":\"local\",\"fee_bps\":5.0,\"indicators\":{},\"intervals\":[\"15m\",\"1mo\"],\"leverage\":20,\"logic\":\"OR\",\"margin_mode\":\"Isolated\",\"mdd_logic\":\"per_trade\",\"optimizer_combo_size\":2,\"optimizer_max_duration_seconds\":7200,\"optimizer_metric\":\"roi_percent_mdd\",\"optimizer_min_trades\":1,\"optimizer_mode\":\"pairs\",\"position_mode\":\"Hedge\",\"position_pct\":2.0,\"scan_auto_apply\":false,\"scan_mdd_limit\":20.0,\"scan_scope\":\"top_n\",\"scan_top_n\":200,\"side\":\"BOTH\",\"slippage_bps\":2.0,\"start_date\":\"2026-01-01\",\"stop_loss\":{\"enabled\":false,\"mode\":\"percent\",\"percent\":0.0,\"scope\":\"entire_account\",\"usdt\":0.0},\"symbol_source\":\"futures\",\"symbols\":[\"BTCUSDT\"],\"template\":{}},\"backtest_symbol_interval_pairs\":[],\"chart\":{\"auto_follow\":true,\"interval\":\"1mo\",\"market\":\"Spot\",\"symbol\":\"ETHUSDT\",\"view_mode\":\"lightweight\"},\"connector_backend\":\"CCXT (Unified)\",\"design\":\"workstation\",\"indicator_source\":\"binance futures\",\"intervals\":[\"1mo\",\"2h\"],\"live_allow_auto_bump_to_min_order\":true,\"live_trading_enabled\":false,\"live_trading_max_leverage\":20,\"live_trading_max_position_pct\":4.0,\"live_trading_max_session_orders\":25,\"llm_allow_public_network\":false,\"llm_base_url\":\"http://127.0.0.1:11434/v1\",\"llm_enabled\":true,\"llm_model\":\"local-model\",\"llm_provider\":\"openai\",\"llm_reasoning_effort\":\"xhigh\",\"llm_use_for\":\"risk_review\",\"loop_interval_override\":\"1h\",\"margin_mode\":\"Cross\",\"mode\":\"live\",\"order_audit_enabled\":false,\"order_type\":\"LIMIT\",\"position_mode\":\"One-way\",\"position_pct\":2.5,\"runtime_symbol_interval_pairs\":[{\"interval\":\"15m\",\"strategy_controls\":{\"leverage\":20,\"loop_interval_override\":\"1h\",\"side\":\"BUY\",\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}},\"symbol\":\"BTCUSDT\"}],\"selected_exchange\":\"kucoin\",\"side\":\"SELL\",\"stop_loss\":{\"enabled\":false,\"mode\":\"percent\",\"percent\":0.0,\"scope\":\"entire_account\",\"usdt\":0.0},\"symbols\":[\"ETHUSDT\"],\"theme\":\"green\",\"tif\":\"IOC\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"canonical-runtime", "{\"chart\":{\"auto_follow\":true,\"interval\":\"15m\",\"market\":\"Spot\",\"symbol\":\"BTCUSDT\",\"view_mode\":\"lightweight\"},\"intervals\":[\"15m\"],\"loop_interval_override\":\"5m\",\"mode\":\"paper\",\"order_type\":\"MARKET\",\"position_pct\":1.5,\"side\":\"BUY\",\"symbols\":[\"BTCUSDT\"],\"tif\":\"GTC\"}", "{\"chart\":{\"auto_follow\":true,\"interval\":\"15m\",\"market\":\"Spot\",\"symbol\":\"BTCUSDT\",\"view_mode\":\"lightweight\"},\"intervals\":[\"15m\"],\"loop_interval_override\":\"5m\",\"mode\":\"paper\",\"order_type\":\"MARKET\",\"position_pct\":1.5,\"side\":\"BUY\",\"symbols\":[\"BTCUSDT\"],\"tif\":\"GTC\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"invalid-unknown-key", "{\"unknown_key\":true}", "{}", false, "Invalid config: unknown_key: is not a supported config key"},
    PythonRuntimeConfigReferenceCase{"invalid-mode-empty", "{\"mode\":\"\"}", "{}", false, "Invalid config: mode: must be a non-empty text value"},
    PythonRuntimeConfigReferenceCase{"invalid-account-type", "{\"account_type\":\"margin\"}", "{}", false, "Invalid config: account_type: must be one of: Futures, Spot"},
    PythonRuntimeConfigReferenceCase{"invalid-symbol-type", "{\"symbols\":42}", "{}", false, "Invalid config: symbols: must be a list of symbols"},
    PythonRuntimeConfigReferenceCase{"invalid-symbol-content", "{\"symbols\":[\"BTC USDT\"]}", "{}", false, "Invalid config: symbols: contains an invalid symbol; symbols: must contain at least one symbol"},
    PythonRuntimeConfigReferenceCase{"invalid-interval-type", "{\"intervals\":42}", "{}", false, "Invalid config: intervals: must be a list of intervals"},
    PythonRuntimeConfigReferenceCase{"invalid-interval-content", "{\"intervals\":[\"0m\"]}", "{}", false, "Invalid config: intervals: contains an invalid interval; intervals: must contain at least one interval"},
    PythonRuntimeConfigReferenceCase{"invalid-lookback-type", "{\"lookback\":\"bars\"}", "{}", false, "Invalid config: lookback: must be an integer"},
    PythonRuntimeConfigReferenceCase{"invalid-lookback-range", "{\"lookback\":0}", "{}", false, "Invalid config: lookback: must be between 1 and 1000000"},
    PythonRuntimeConfigReferenceCase{"invalid-position-pct-exclusive", "{\"position_pct\":0}", "{}", false, "Invalid config: position_pct: must be > 0 and <= 100"},
    PythonRuntimeConfigReferenceCase{"invalid-position-pct-range", "{\"position_pct\":101}", "{}", false, "Invalid config: position_pct: must be > 0 and <= 100"},
    PythonRuntimeConfigReferenceCase{"invalid-bool", "{\"live_trading_enabled\":\"maybe\"}", "{}", false, "Invalid config: live_trading_enabled: must be a boolean"},
    PythonRuntimeConfigReferenceCase{"invalid-loop-interval", "{\"loop_interval_override\":\"fast\"}", "{}", false, "Invalid config: loop_interval_override: must be a valid interval"},
    PythonRuntimeConfigReferenceCase{"invalid-pair-type", "{\"runtime_symbol_interval_pairs\":{}}", "{}", false, "Invalid config: runtime_symbol_interval_pairs: must be a list of symbol/interval objects"},
    PythonRuntimeConfigReferenceCase{"invalid-pair-entry", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"symbol\":\"BTC USDT\"}]}", "{}", false, "Invalid config: runtime_symbol_interval_pairs[0].symbol: must be a non-empty symbol"},
    PythonRuntimeConfigReferenceCase{"invalid-pair-controls", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"leverage\":0},\"symbol\":\"BTCUSDT\"}]}", "{}", false, "Invalid config: runtime_symbol_interval_pairs[0].strategy_controls.leverage: must be between 1 and 125"},
    PythonRuntimeConfigReferenceCase{"invalid-stop-loss-type", "{\"stop_loss\":\"no\"}", "{}", false, "Invalid config: stop_loss: must be an object"},
    PythonRuntimeConfigReferenceCase{"invalid-chart-type", "{\"chart\":\"no\"}", "{}", false, "Invalid config: chart: must be an object"},
    PythonRuntimeConfigReferenceCase{"invalid-chart-key", "{\"chart\":{\"unknown\":true}}", "{}", false, "Invalid config: chart.unknown: is not a supported config key"},
    PythonRuntimeConfigReferenceCase{"invalid-chart-market", "{\"chart\":{\"market\":\"margin\"}}", "{}", false, "Invalid config: chart.market: must be one of: Futures, Spot"},
    PythonRuntimeConfigReferenceCase{"invalid-chart-view", "{\"chart\":{\"view_mode\":\"external\"}}", "{}", false, "Invalid config: chart.view_mode: must be one of: lightweight, original, tradingview"},
    PythonRuntimeConfigReferenceCase{"invalid-chart-symbol", "{\"chart\":{\"symbol\":\"BTC USDT\"}}", "{}", false, "Invalid config: chart.symbol: must be a non-empty symbol"},
    PythonRuntimeConfigReferenceCase{"invalid-chart-interval", "{\"chart\":{\"interval\":\"0m\"}}", "{}", false, "Invalid config: chart.interval: must be a valid interval"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-type", "{\"backtest\":\"no\"}", "{}", false, "Invalid config: backtest: must be an object"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-key", "{\"backtest\":{\"unknown\":true}}", "{}", false, "Invalid config: backtest.unknown: is not a supported config key"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-capital", "{\"backtest\":{\"capital\":0}}", "{}", false, "Invalid config: backtest.capital: must be > 0 and <= 1e+12"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-date", "{\"backtest\":{\"start_date\":\"not-date\"}}", "{}", false, "Invalid config: backtest.start_date: must be an ISO date or datetime"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-choice", "{\"backtest\":{\"logic\":\"xor\"}}", "{}", false, "Invalid config: backtest.logic: must be one of: AND, OR, SEPARATE"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-mapping", "{\"backtest\":{\"template\":[]}}", "{}", false, "Invalid config: backtest.template: must be an object"},
    PythonRuntimeConfigReferenceCase{"invalid-backtest-stop-loss", "{\"backtest\":{\"stop_loss\":\"bad\"}}", "{}", false, "Invalid config: backtest.stop_loss: must be an object"},
    PythonRuntimeConfigReferenceCase{"invalid-risk-int", "{\"indicator_flip_confirmation_bars\":0}", "{}", false, "Invalid config: indicator_flip_confirmation_bars: must be between 1 and 1000000"},
    PythonRuntimeConfigReferenceCase{"invalid-risk-float", "{\"max_auto_bump_percent\":101}", "{}", false, "Invalid config: max_auto_bump_percent: must be >= 0 and <= 100"},
    PythonRuntimeConfigReferenceCase{"invalid-llm-provider", "{\"llm_provider\":\"ghost-ai\"}", "{}", false, "Invalid config: llm_provider: must be one of: anthropic, deepseek, gemini, grok, llamacpp, lmstudio, local, mistral, moonshot, ollama, open-source, openai, qwen, tgi, vllm"},
    PythonRuntimeConfigReferenceCase{"invalid-text-control", "{\"connector_backend\":\"ok\\u0001\"}", "{}", false, "Invalid config: connector_backend: must be a non-empty text value"},
    PythonRuntimeConfigReferenceCase{"choice-account_type-spot", "{\"account_type\":\"spot\"}", "{\"account_type\":\"Spot\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-account_type-futures", "{\"account_type\":\"futures\"}", "{\"account_type\":\"Futures\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-margin_mode-isolated", "{\"margin_mode\":\"isolated\"}", "{\"margin_mode\":\"Isolated\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-margin_mode-cross", "{\"margin_mode\":\"cross\"}", "{\"margin_mode\":\"Cross\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_mode-hedge", "{\"position_mode\":\"hedge\"}", "{\"position_mode\":\"Hedge\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_mode-one-way", "{\"position_mode\":\"one-way\"}", "{\"position_mode\":\"One-way\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_mode-oneway", "{\"position_mode\":\"oneway\"}", "{\"position_mode\":\"One-way\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-assets_mode-single-asset", "{\"assets_mode\":\"single-asset\"}", "{\"assets_mode\":\"Single-Asset\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-assets_mode-single-asset mode", "{\"assets_mode\":\"single-asset mode\"}", "{\"assets_mode\":\"Single-Asset\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-assets_mode-multi-assets", "{\"assets_mode\":\"multi-assets\"}", "{\"assets_mode\":\"Multi-Assets\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-assets_mode-multi-asset", "{\"assets_mode\":\"multi-asset\"}", "{\"assets_mode\":\"Multi-Assets\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-assets_mode-multi-assets mode", "{\"assets_mode\":\"multi-assets mode\"}", "{\"assets_mode\":\"Multi-Assets\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-account_mode-classic trading", "{\"account_mode\":\"classic trading\"}", "{\"account_mode\":\"Classic Trading\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-account_mode-portfolio margin", "{\"account_mode\":\"portfolio margin\"}", "{\"account_mode\":\"Portfolio Margin\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-side-both", "{\"side\":\"both\"}", "{\"side\":\"BOTH\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-side-buy", "{\"side\":\"buy\"}", "{\"side\":\"BUY\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-side-sell", "{\"side\":\"sell\"}", "{\"side\":\"SELL\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-order_type-market", "{\"order_type\":\"market\"}", "{\"order_type\":\"MARKET\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-order_type-limit", "{\"order_type\":\"limit\"}", "{\"order_type\":\"LIMIT\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-tif-gtc", "{\"tif\":\"gtc\"}", "{\"tif\":\"GTC\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-tif-ioc", "{\"tif\":\"ioc\"}", "{\"tif\":\"IOC\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-tif-fok", "{\"tif\":\"fok\"}", "{\"tif\":\"FOK\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-tif-gtd", "{\"tif\":\"gtd\"}", "{\"tif\":\"GTD\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-chart_view_mode-tradingview", "{\"chart\":{\"view_mode\":\"tradingview\"}}", "{\"chart\":{\"view_mode\":\"tradingview\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-chart_view_mode-original", "{\"chart\":{\"view_mode\":\"original\"}}", "{\"chart\":{\"view_mode\":\"original\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-chart_view_mode-lightweight", "{\"chart\":{\"view_mode\":\"lightweight\"}}", "{\"chart\":{\"view_mode\":\"lightweight\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-chart_view_mode-tradingview lightweight", "{\"chart\":{\"view_mode\":\"tradingview lightweight\"}}", "{\"chart\":{\"view_mode\":\"lightweight\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-logic-and", "{\"backtest\":{\"logic\":\"and\"}}", "{\"backtest\":{\"logic\":\"AND\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-logic-or", "{\"backtest\":{\"logic\":\"or\"}}", "{\"backtest\":{\"logic\":\"OR\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-logic-separate", "{\"backtest\":{\"logic\":\"separate\"}}", "{\"backtest\":{\"logic\":\"SEPARATE\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-backtest_execution_backend-desktop", "{\"backtest\":{\"execution_backend\":\"desktop\"}}", "{\"backtest\":{\"execution_backend\":\"local\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-backtest_execution_backend-desktop-local", "{\"backtest\":{\"execution_backend\":\"desktop-local\"}}", "{\"backtest\":{\"execution_backend\":\"local\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-backtest_execution_backend-local", "{\"backtest\":{\"execution_backend\":\"local\"}}", "{\"backtest\":{\"execution_backend\":\"local\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-backtest_execution_backend-remote", "{\"backtest\":{\"execution_backend\":\"remote\"}}", "{\"backtest\":{\"execution_backend\":\"service\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-backtest_execution_backend-service", "{\"backtest\":{\"execution_backend\":\"service\"}}", "{\"backtest\":{\"execution_backend\":\"service\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-backtest_execution_backend-service-api", "{\"backtest\":{\"execution_backend\":\"service-api\"}}", "{\"backtest\":{\"execution_backend\":\"service\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-mdd_logic-per_trade", "{\"backtest\":{\"mdd_logic\":\"per_trade\"}}", "{\"backtest\":{\"mdd_logic\":\"per_trade\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-mdd_logic-cumulative", "{\"backtest\":{\"mdd_logic\":\"cumulative\"}}", "{\"backtest\":{\"mdd_logic\":\"cumulative\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-mdd_logic-entire_account", "{\"backtest\":{\"mdd_logic\":\"entire_account\"}}", "{\"backtest\":{\"mdd_logic\":\"entire_account\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-scan_scope-selected", "{\"backtest\":{\"scan_scope\":\"selected\"}}", "{\"backtest\":{\"scan_scope\":\"selected\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-scan_scope-top_n", "{\"backtest\":{\"scan_scope\":\"top_n\"}}", "{\"backtest\":{\"scan_scope\":\"top_n\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-scan_scope-top-n", "{\"backtest\":{\"scan_scope\":\"top-n\"}}", "{\"backtest\":{\"scan_scope\":\"top_n\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-scan_scope-all_loaded", "{\"backtest\":{\"scan_scope\":\"all_loaded\"}}", "{\"backtest\":{\"scan_scope\":\"all_loaded\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-scan_scope-all-loaded", "{\"backtest\":{\"scan_scope\":\"all-loaded\"}}", "{\"backtest\":{\"scan_scope\":\"all_loaded\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_mode-current", "{\"backtest\":{\"optimizer_mode\":\"current\"}}", "{\"backtest\":{\"optimizer_mode\":\"current\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_mode-single", "{\"backtest\":{\"optimizer_mode\":\"single\"}}", "{\"backtest\":{\"optimizer_mode\":\"single\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_mode-pairs", "{\"backtest\":{\"optimizer_mode\":\"pairs\"}}", "{\"backtest\":{\"optimizer_mode\":\"pairs\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_mode-combinations", "{\"backtest\":{\"optimizer_mode\":\"combinations\"}}", "{\"backtest\":{\"optimizer_mode\":\"combinations\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi_percent", "{\"backtest\":{\"optimizer_metric\":\"roi_percent\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_percent\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi-percent", "{\"backtest\":{\"optimizer_metric\":\"roi-percent\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_percent\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi_percent_mdd", "{\"backtest\":{\"optimizer_metric\":\"roi_percent_mdd\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_percent_mdd\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi-percent-mdd", "{\"backtest\":{\"optimizer_metric\":\"roi-percent-mdd\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_percent_mdd\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi_drawdown", "{\"backtest\":{\"optimizer_metric\":\"roi_drawdown\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_drawdown\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi-drawdown", "{\"backtest\":{\"optimizer_metric\":\"roi-drawdown\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_drawdown\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi_value", "{\"backtest\":{\"optimizer_metric\":\"roi_value\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_value\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-optimizer_metric-roi-value", "{\"backtest\":{\"optimizer_metric\":\"roi-value\"}}", "{\"backtest\":{\"optimizer_metric\":\"roi_value\"}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-stop_loss_mode-usdt", "{\"stop_loss\":{\"mode\":\"usdt\"}}", "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-stop_loss_mode-percent", "{\"stop_loss\":{\"mode\":\"percent\"}}", "{\"stop_loss\":{\"enabled\":false,\"mode\":\"percent\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-stop_loss_mode-both", "{\"stop_loss\":{\"mode\":\"both\"}}", "{\"stop_loss\":{\"enabled\":false,\"mode\":\"both\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-stop_loss_scope-per_trade", "{\"stop_loss\":{\"scope\":\"per_trade\"}}", "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-stop_loss_scope-cumulative", "{\"stop_loss\":{\"scope\":\"cumulative\"}}", "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"cumulative\",\"usdt\":0.0}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-stop_loss_scope-entire_account", "{\"stop_loss\":{\"scope\":\"entire_account\"}}", "{\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"entire_account\",\"usdt\":0.0}}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_use_for-advisory", "{\"llm_use_for\":\"advisory\"}", "{\"llm_use_for\":\"advisory\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_use_for-backtest_explanation", "{\"llm_use_for\":\"backtest_explanation\"}", "{\"llm_use_for\":\"backtest_explanation\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_use_for-risk_review", "{\"llm_use_for\":\"risk_review\"}", "{\"llm_use_for\":\"risk_review\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_use_for-signal_confirmation", "{\"llm_use_for\":\"signal_confirmation\"}", "{\"llm_use_for\":\"signal_confirmation\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-default", "{\"llm_reasoning_effort\":\"default\"}", "{\"llm_reasoning_effort\":\"default\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-disabled", "{\"llm_reasoning_effort\":\"disabled\"}", "{\"llm_reasoning_effort\":\"disabled\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-enabled", "{\"llm_reasoning_effort\":\"enabled\"}", "{\"llm_reasoning_effort\":\"enabled\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-extra-high", "{\"llm_reasoning_effort\":\"extra-high\"}", "{\"llm_reasoning_effort\":\"xhigh\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-extra_high", "{\"llm_reasoning_effort\":\"extra_high\"}", "{\"llm_reasoning_effort\":\"xhigh\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-high", "{\"llm_reasoning_effort\":\"high\"}", "{\"llm_reasoning_effort\":\"high\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-low", "{\"llm_reasoning_effort\":\"low\"}", "{\"llm_reasoning_effort\":\"low\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-max", "{\"llm_reasoning_effort\":\"max\"}", "{\"llm_reasoning_effort\":\"max\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-medium", "{\"llm_reasoning_effort\":\"medium\"}", "{\"llm_reasoning_effort\":\"medium\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-minimal", "{\"llm_reasoning_effort\":\"minimal\"}", "{\"llm_reasoning_effort\":\"minimal\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-none", "{\"llm_reasoning_effort\":\"none\"}", "{\"llm_reasoning_effort\":\"none\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_reasoning_effort-xhigh", "{\"llm_reasoning_effort\":\"xhigh\"}", "{\"llm_reasoning_effort\":\"xhigh\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-percent", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percent\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percent\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-%", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"%\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"%\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-perc", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"perc\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"perc\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-percentage", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percentage\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"percentage\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-fraction", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"fraction\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"fraction\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-decimal", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"decimal\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"decimal\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-position_pct_units-ratio", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"ratio\"},\"symbol\":\"BTCUSDT\"}]}", "{\"runtime_symbol_interval_pairs\":[{\"interval\":\"1m\",\"strategy_controls\":{\"position_pct_units\":\"ratio\"},\"symbol\":\"BTCUSDT\"}]}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-alibaba", "{\"llm_provider\":\"alibaba\"}", "{\"llm_provider\":\"qwen\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-alibaba-qwen", "{\"llm_provider\":\"alibaba-qwen\"}", "{\"llm_provider\":\"qwen\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-anthropic", "{\"llm_provider\":\"anthropic\"}", "{\"llm_provider\":\"anthropic\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-anthropic-claude", "{\"llm_provider\":\"anthropic-claude\"}", "{\"llm_provider\":\"anthropic\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-arctic", "{\"llm_provider\":\"arctic\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-bloom", "{\"llm_provider\":\"bloom\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-bloomz", "{\"llm_provider\":\"bloomz\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-cerebras", "{\"llm_provider\":\"cerebras\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-chatglm", "{\"llm_provider\":\"chatglm\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-chatgpt", "{\"llm_provider\":\"chatgpt\"}", "{\"llm_provider\":\"openai\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-claude", "{\"llm_provider\":\"claude\"}", "{\"llm_provider\":\"anthropic\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-codet5", "{\"llm_provider\":\"codet5\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-custom", "{\"llm_provider\":\"custom\"}", "{\"llm_provider\":\"local\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-dashscope", "{\"llm_provider\":\"dashscope\"}", "{\"llm_provider\":\"qwen\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-dbrx", "{\"llm_provider\":\"dbrx\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-decicoder", "{\"llm_provider\":\"decicoder\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-deepseek", "{\"llm_provider\":\"deepseek\"}", "{\"llm_provider\":\"deepseek\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-dolly", "{\"llm_provider\":\"dolly\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-flan-t5", "{\"llm_provider\":\"flan-t5\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-fugaku", "{\"llm_provider\":\"fugaku\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-gemini", "{\"llm_provider\":\"gemini\"}", "{\"llm_provider\":\"gemini\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-gemma4", "{\"llm_provider\":\"gemma4\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-glm", "{\"llm_provider\":\"glm\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-glm5", "{\"llm_provider\":\"glm5\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-google", "{\"llm_provider\":\"google\"}", "{\"llm_provider\":\"gemini\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-google-gemini", "{\"llm_provider\":\"google-gemini\"}", "{\"llm_provider\":\"gemini\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-gpt-neox", "{\"llm_provider\":\"gpt-neox\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-gpt20b", "{\"llm_provider\":\"gpt20b\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-grok", "{\"llm_provider\":\"grok\"}", "{\"llm_provider\":\"grok\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-hf", "{\"llm_provider\":\"hf\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-hf-tgi", "{\"llm_provider\":\"hf-tgi\"}", "{\"llm_provider\":\"tgi\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-hugging-face", "{\"llm_provider\":\"hugging-face\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-huggingface", "{\"llm_provider\":\"huggingface\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-huggingface-tgi", "{\"llm_provider\":\"huggingface-tgi\"}", "{\"llm_provider\":\"tgi\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-jais", "{\"llm_provider\":\"jais\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-kimi", "{\"llm_provider\":\"kimi\"}", "{\"llm_provider\":\"moonshot\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-llama-4", "{\"llm_provider\":\"llama-4\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-llama-cpp", "{\"llm_provider\":\"llama-cpp\"}", "{\"llm_provider\":\"llamacpp\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-llama-cpp-server", "{\"llm_provider\":\"llama-cpp-server\"}", "{\"llm_provider\":\"llamacpp\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-llama.cpp", "{\"llm_provider\":\"llama.cpp\"}", "{\"llm_provider\":\"llamacpp\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-llama4", "{\"llm_provider\":\"llama4\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-llamacpp", "{\"llm_provider\":\"llamacpp\"}", "{\"llm_provider\":\"llamacpp\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-lm-studio", "{\"llm_provider\":\"lm-studio\"}", "{\"llm_provider\":\"lmstudio\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-lmstudio", "{\"llm_provider\":\"lmstudio\"}", "{\"llm_provider\":\"lmstudio\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-local", "{\"llm_provider\":\"local\"}", "{\"llm_provider\":\"local\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-local-openai", "{\"llm_provider\":\"local-openai\"}", "{\"llm_provider\":\"local\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-local-openai-compatible", "{\"llm_provider\":\"local-openai-compatible\"}", "{\"llm_provider\":\"local\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-mamba", "{\"llm_provider\":\"mamba\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-mimo", "{\"llm_provider\":\"mimo\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-minimax", "{\"llm_provider\":\"minimax\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-mistral", "{\"llm_provider\":\"mistral\"}", "{\"llm_provider\":\"mistral\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-mistral-ai", "{\"llm_provider\":\"mistral-ai\"}", "{\"llm_provider\":\"mistral\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-moonshot", "{\"llm_provider\":\"moonshot\"}", "{\"llm_provider\":\"moonshot\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-moonshot-ai", "{\"llm_provider\":\"moonshot-ai\"}", "{\"llm_provider\":\"moonshot\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-mpt", "{\"llm_provider\":\"mpt\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-nemotron", "{\"llm_provider\":\"nemotron\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-ollama", "{\"llm_provider\":\"ollama\"}", "{\"llm_provider\":\"ollama\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-olmo", "{\"llm_provider\":\"olmo\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-open-llama", "{\"llm_provider\":\"open-llama\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-open-source", "{\"llm_provider\":\"open-source\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-open-weight", "{\"llm_provider\":\"open-weight\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-open-weights", "{\"llm_provider\":\"open-weights\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-openai", "{\"llm_provider\":\"openai\"}", "{\"llm_provider\":\"openai\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-openai-chatgpt", "{\"llm_provider\":\"openai-chatgpt\"}", "{\"llm_provider\":\"openai\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-openllama", "{\"llm_provider\":\"openllama\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-opensource", "{\"llm_provider\":\"opensource\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-oss", "{\"llm_provider\":\"oss\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-pythia", "{\"llm_provider\":\"pythia\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-qwen", "{\"llm_provider\":\"qwen\"}", "{\"llm_provider\":\"qwen\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-qwen-local", "{\"llm_provider\":\"qwen-local\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-redpajama", "{\"llm_provider\":\"redpajama\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-replit-code", "{\"llm_provider\":\"replit-code\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-rmkv", "{\"llm_provider\":\"rmkv\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-rwkv", "{\"llm_provider\":\"rwkv\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-s-glang", "{\"llm_provider\":\"s-glang\"}", "{\"llm_provider\":\"vllm\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-santacoder", "{\"llm_provider\":\"santacoder\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-sglang", "{\"llm_provider\":\"sglang\"}", "{\"llm_provider\":\"vllm\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-stablelm", "{\"llm_provider\":\"stablelm\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-starchat", "{\"llm_provider\":\"starchat\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-step", "{\"llm_provider\":\"step\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-stepfun", "{\"llm_provider\":\"stepfun\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-t5", "{\"llm_provider\":\"t5\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-text-generation-inference", "{\"llm_provider\":\"text-generation-inference\"}", "{\"llm_provider\":\"tgi\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-tgi", "{\"llm_provider\":\"tgi\"}", "{\"llm_provider\":\"tgi\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-vllm", "{\"llm_provider\":\"vllm\"}", "{\"llm_provider\":\"vllm\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-xai", "{\"llm_provider\":\"xai\"}", "{\"llm_provider\":\"grok\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-xai-grok", "{\"llm_provider\":\"xai-grok\"}", "{\"llm_provider\":\"grok\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-xgen", "{\"llm_provider\":\"xgen\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-xiaomi", "{\"llm_provider\":\"xiaomi\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-yalm", "{\"llm_provider\":\"yalm\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"choice-llm_provider-zai", "{\"llm_provider\":\"zai\"}", "{\"llm_provider\":\"open-source\"}", true, ""},
    PythonRuntimeConfigReferenceCase{"bool-stop_without_close-true", "{\"stop_without_close\":\"true\"}", "{\"stop_without_close\":true}", true, ""},
    PythonRuntimeConfigReferenceCase{"bool-stop_without_close-false", "{\"stop_without_close\":\"false\"}", "{\"stop_without_close\":false}", true, ""},
};

struct PythonStrategyControlsReferenceCase {
    std::string_view name;
    std::string_view kind;
    std::string_view inputJson;
    std::string_view expectedJson;
};

inline constexpr std::array<PythonStrategyControlsReferenceCase, 5> kPythonStrategyControlsReferenceCases = {
    PythonStrategyControlsReferenceCase{"runtime-canonical", "runtime", "{\"account_mode\":\"portfolio margin\",\"add_only\":\"false\",\"connector_backend\":\"CCXT\",\"leverage\":\"3\",\"loop_interval_override\":\" 5 M \",\"position_pct\":\"12.5\",\"position_pct_units\":\"percentage\",\"side\":\"buy\",\"stop_loss\":{\"enabled\":\"true\",\"mode\":\"both\",\"percent\":\"2.5\",\"scope\":\"bad\",\"usdt\":\"50\"}}", "{\"account_mode\":\"Portfolio Margin\",\"add_only\":true,\"connector_backend\":\"ccxt\",\"leverage\":3,\"loop_interval_override\":\"5m\",\"position_pct\":12.5,\"position_pct_units\":\"percent\",\"side\":\"BUY\",\"stop_loss\":{\"enabled\":true,\"mode\":\"both\",\"percent\":2.5,\"scope\":\"per_trade\",\"usdt\":50.0}}"},
    PythonStrategyControlsReferenceCase{"runtime-python-truthiness-boundaries", "runtime", "{\"_position_pct_units\":\"percentage\",\"account_mode\":false,\"add_only\":null,\"connector_backend\":false,\"leverage\":2.5,\"loop_interval_override\":\" 5 M \",\"position_pct\":true,\"position_pct_units\":\"\",\"side\":\" buy \"}", "{\"leverage\":2,\"loop_interval_override\":\"5m\",\"position_pct\":1.0,\"position_pct_units\":\"percent\"}"},
    PythonStrategyControlsReferenceCase{"runtime-kind-is-case-sensitive", "Runtime", "{\"connector_backend\":\"ccxt\",\"side\":\"buy\",\"stop_loss\":{\"enabled\":true}}", "{}"},
    PythonStrategyControlsReferenceCase{"backtest-canonical", "backtest", "{\"account_mode\":\"classic\",\"assets_mode\":\"multi assets\",\"capital\":\"1000\",\"connector_backend\":\"ccxt\",\"fee_bps\":\"5\",\"leverage\":0,\"logic\":\"separate\",\"loop_interval_override\":\" 1 h \",\"margin_mode\":\" Isolated \",\"position_mode\":\" Hedge \",\"position_pct\":\"0.4\",\"position_pct_units\":\"fraction\",\"side\":\"sell short\",\"slippage_bps\":\"2\",\"stop_loss\":{\"enabled\":\"true\",\"mode\":\"both\",\"percent\":\"2.5\",\"scope\":\"entire_account\"}}", "{\"account_mode\":\"Classic Trading\",\"assets_mode\":\"Multi-Assets\",\"capital\":1000.0,\"connector_backend\":\"ccxt\",\"leverage\":0,\"logic\":\"SEPARATE\",\"loop_interval_override\":\"1h\",\"margin_mode\":\" Isolated \",\"position_mode\":\" Hedge \",\"position_pct\":0.4,\"position_pct_units\":\"fraction\",\"side\":\"SELL\",\"stop_loss\":{\"enabled\":true,\"mode\":\"both\",\"percent\":2.5,\"scope\":\"entire_account\",\"usdt\":0.0}}"},
    PythonStrategyControlsReferenceCase{"backtest-exact-logic-and-fuzzy-side", "backtest", "{\"account_mode\":\"portfolio\",\"assets_mode\":\"single asset\",\"leverage\":\"3.5\",\"logic\":\" OR \",\"margin_mode\":\"\",\"position_mode\":\"Hedge\",\"side\":\" buy \"}", "{\"account_mode\":\"Portfolio Margin\",\"assets_mode\":\"Single-Asset\",\"position_mode\":\"Hedge\",\"side\":\"BUY\"}"},
};

struct PythonStrategyRiskReferenceCase {
    std::string_view name;
    std::string_view inputJson;
    std::string_view expectedJson;
};

inline constexpr std::array<PythonStrategyRiskReferenceCase, 3> kPythonStrategyRiskReferenceCases = {
    PythonStrategyRiskReferenceCase{"risk-defaults", "{}", "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}"},
    PythonStrategyRiskReferenceCase{"risk-canonical-all-controls", "{\"allow_close_ignoring_hold\":\"true\",\"allow_indicator_close_without_signal\":\"false\",\"allow_multi_indicator_close\":\"true\",\"allow_opposite_positions\":\"false\",\"auto_bump_percent_multiplier\":\"20\",\"auto_flip_on_close\":\"false\",\"close_on_exit\":\"true\",\"futures_flat_purge_grace_seconds\":\"18.5\",\"futures_flat_purge_miss_threshold\":\"4\",\"hedge_preserve_opposites\":\"true\",\"indicator_flip_confirmation_bars\":\"2\",\"indicator_flip_cooldown_bars\":\"4\",\"indicator_flip_cooldown_seconds\":\"12.5\",\"indicator_min_position_hold_bars\":\"3\",\"indicator_min_position_hold_seconds\":\"7.25\",\"indicator_reentry_cooldown_bars\":\"2\",\"indicator_reentry_cooldown_seconds\":\"9.5\",\"indicator_reentry_requires_signal_reset\":\"true\",\"indicator_use_live_values\":\"false\",\"max_auto_bump_percent\":\"7.5\",\"positions_missing_autoclose\":\"false\",\"positions_missing_grace_seconds\":\"45\",\"positions_missing_threshold\":\"3\",\"require_indicator_flip_signal\":\"yes\",\"stop_loss\":{\"enabled\":\"true\",\"mode\":\"percent\",\"percent\":\"2.5\",\"scope\":\"entire_account\",\"usdt\":\"25\"},\"strict_indicator_flip_enforcement\":\"no\"}", "{\"allow_close_ignoring_hold\":true,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":true,\"allow_opposite_positions\":false,\"auto_bump_percent_multiplier\":20.0,\"auto_flip_on_close\":false,\"close_on_exit\":true,\"futures_flat_purge_grace_seconds\":18.5,\"futures_flat_purge_miss_threshold\":4,\"hedge_preserve_opposites\":true,\"indicator_flip_confirmation_bars\":2,\"indicator_flip_cooldown_bars\":4,\"indicator_flip_cooldown_seconds\":12.5,\"indicator_min_position_hold_bars\":3,\"indicator_min_position_hold_seconds\":7.25,\"indicator_reentry_cooldown_bars\":2,\"indicator_reentry_cooldown_seconds\":9.5,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":7.5,\"positions_missing_autoclose\":false,\"positions_missing_grace_seconds\":45.0,\"positions_missing_threshold\":3,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":true,\"mode\":\"percent\",\"percent\":2.5,\"scope\":\"entire_account\",\"usdt\":25.0},\"strict_indicator_flip_enforcement\":false}"},
    PythonStrategyRiskReferenceCase{"risk-valid-lower-and-upper-bounds", "{\"auto_bump_percent_multiplier\":1000,\"futures_flat_purge_grace_seconds\":604800,\"futures_flat_purge_miss_threshold\":1,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":0,\"indicator_flip_cooldown_seconds\":0,\"indicator_min_position_hold_bars\":0,\"indicator_min_position_hold_seconds\":0,\"indicator_reentry_cooldown_bars\":0,\"indicator_reentry_cooldown_seconds\":0,\"max_auto_bump_percent\":100,\"positions_missing_grace_seconds\":604800,\"positions_missing_threshold\":1,\"stop_loss\":{\"enabled\":false,\"mode\":\"both\",\"percent\":0,\"scope\":\"cumulative\",\"usdt\":0}}", "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":1000.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":604800.0,\"futures_flat_purge_miss_threshold\":1,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":0,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":0,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":0,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":100.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":604800.0,\"positions_missing_threshold\":1,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"both\",\"percent\":0.0,\"scope\":\"cumulative\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}"},
};

inline constexpr std::array<PythonStrategyRiskReferenceCase, 6> kPythonStrategyRiskLooseReferenceCases = {
    PythonStrategyRiskReferenceCase{"risk-loose-string-y", "{\"allow_close_ignoring_hold\":\"y\",\"allow_indicator_close_without_signal\":\"y\",\"allow_multi_indicator_close\":\"y\",\"allow_opposite_positions\":\"y\",\"auto_flip_on_close\":\"y\",\"close_on_exit\":\"y\",\"hedge_preserve_opposites\":\"y\",\"indicator_reentry_requires_signal_reset\":\"y\",\"indicator_use_live_values\":\"y\",\"positions_missing_autoclose\":\"y\",\"require_indicator_flip_signal\":\"y\",\"strict_indicator_flip_enforcement\":\"y\"}", "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}"},
    PythonStrategyRiskReferenceCase{"risk-loose-unknown-string", "{\"allow_close_ignoring_hold\":\"maybe\",\"allow_indicator_close_without_signal\":\"maybe\",\"allow_multi_indicator_close\":\"maybe\",\"allow_opposite_positions\":\"maybe\",\"auto_flip_on_close\":\"maybe\",\"close_on_exit\":\"maybe\",\"hedge_preserve_opposites\":\"maybe\",\"indicator_reentry_requires_signal_reset\":\"maybe\",\"indicator_use_live_values\":\"maybe\",\"positions_missing_autoclose\":\"maybe\",\"require_indicator_flip_signal\":\"maybe\",\"strict_indicator_flip_enforcement\":\"maybe\"}", "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}"},
    PythonStrategyRiskReferenceCase{"risk-loose-fractional-zero", "{\"allow_close_ignoring_hold\":0.5,\"allow_indicator_close_without_signal\":0.5,\"allow_multi_indicator_close\":0.5,\"allow_opposite_positions\":0.5,\"auto_flip_on_close\":0.5,\"close_on_exit\":0.5,\"hedge_preserve_opposites\":0.5,\"indicator_reentry_requires_signal_reset\":0.5,\"indicator_use_live_values\":0.5,\"positions_missing_autoclose\":0.5,\"require_indicator_flip_signal\":0.5,\"strict_indicator_flip_enforcement\":0.5}", "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":false,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":false,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":false,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":false,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":false,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":false}"},
    PythonStrategyRiskReferenceCase{"risk-loose-fractional-one", "{\"allow_close_ignoring_hold\":1.5,\"allow_indicator_close_without_signal\":1.5,\"allow_multi_indicator_close\":1.5,\"allow_opposite_positions\":1.5,\"auto_flip_on_close\":1.5,\"close_on_exit\":1.5,\"hedge_preserve_opposites\":1.5,\"indicator_reentry_requires_signal_reset\":1.5,\"indicator_use_live_values\":1.5,\"positions_missing_autoclose\":1.5,\"require_indicator_flip_signal\":1.5,\"strict_indicator_flip_enforcement\":1.5}", "{\"allow_close_ignoring_hold\":true,\"allow_indicator_close_without_signal\":true,\"allow_multi_indicator_close\":true,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":true,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":true,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":true,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}"},
    PythonStrategyRiskReferenceCase{"risk-loose-negative-fractional-zero", "{\"allow_close_ignoring_hold\":-0.5,\"allow_indicator_close_without_signal\":-0.5,\"allow_multi_indicator_close\":-0.5,\"allow_opposite_positions\":-0.5,\"auto_flip_on_close\":-0.5,\"close_on_exit\":-0.5,\"hedge_preserve_opposites\":-0.5,\"indicator_reentry_requires_signal_reset\":-0.5,\"indicator_use_live_values\":-0.5,\"positions_missing_autoclose\":-0.5,\"require_indicator_flip_signal\":-0.5,\"strict_indicator_flip_enforcement\":-0.5}", "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":false,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":false,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":false,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":false,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":false,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":false}"},
    PythonStrategyRiskReferenceCase{"risk-loose-negative-fractional-one", "{\"allow_close_ignoring_hold\":-1.5,\"allow_indicator_close_without_signal\":-1.5,\"allow_multi_indicator_close\":-1.5,\"allow_opposite_positions\":-1.5,\"auto_flip_on_close\":-1.5,\"close_on_exit\":-1.5,\"hedge_preserve_opposites\":-1.5,\"indicator_reentry_requires_signal_reset\":-1.5,\"indicator_use_live_values\":-1.5,\"positions_missing_autoclose\":-1.5,\"require_indicator_flip_signal\":-1.5,\"strict_indicator_flip_enforcement\":-1.5}", "{\"allow_close_ignoring_hold\":true,\"allow_indicator_close_without_signal\":true,\"allow_multi_indicator_close\":true,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":true,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":true,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":true,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}"},
};
inline constexpr std::string_view kPythonIndicatorEnabledReferenceJson = "[{\"expected\":false,\"input\":{},\"name\":\"indicator-enabled-missing\"},{\"expected\":true,\"input\":{\"enabled\":true},\"name\":\"indicator-enabled-bool-true\"},{\"expected\":false,\"input\":{\"enabled\":false},\"name\":\"indicator-enabled-bool-false\"},{\"expected\":true,\"input\":{\"enabled\":\"true\"},\"name\":\"indicator-enabled-string-true\"},{\"expected\":false,\"input\":{\"enabled\":\"false\"},\"name\":\"indicator-enabled-string-false\"},{\"expected\":true,\"input\":{\"enabled\":\"yes\"},\"name\":\"indicator-enabled-string-yes\"},{\"expected\":false,\"input\":{\"enabled\":\"no\"},\"name\":\"indicator-enabled-string-no\"},{\"expected\":true,\"input\":{\"enabled\":\"on\"},\"name\":\"indicator-enabled-string-on\"},{\"expected\":false,\"input\":{\"enabled\":\"off\"},\"name\":\"indicator-enabled-string-off\"},{\"expected\":false,\"input\":{\"enabled\":\"disabled\"},\"name\":\"indicator-enabled-string-disabled\"},{\"expected\":false,\"input\":{\"enabled\":\"none\"},\"name\":\"indicator-enabled-string-none\"},{\"expected\":false,\"input\":{\"enabled\":\"null\"},\"name\":\"indicator-enabled-string-null\"},{\"expected\":false,\"input\":{\"enabled\":\"0.5\"},\"name\":\"indicator-enabled-string-numeric\"},{\"expected\":false,\"input\":{\"enabled\":\"y\"},\"name\":\"indicator-enabled-string-y\"},{\"expected\":false,\"input\":{\"enabled\":\"maybe\"},\"name\":\"indicator-enabled-unknown-string\"},{\"expected\":false,\"input\":{\"enabled\":\"\"},\"name\":\"indicator-enabled-empty-string\"},{\"expected\":false,\"input\":{\"enabled\":null},\"name\":\"indicator-enabled-null\"},{\"expected\":false,\"input\":{\"enabled\":0},\"name\":\"indicator-enabled-zero\"},{\"expected\":true,\"input\":{\"enabled\":1},\"name\":\"indicator-enabled-one\"},{\"expected\":false,\"input\":{\"enabled\":0.5},\"name\":\"indicator-enabled-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":1.5},\"name\":\"indicator-enabled-fractional-one\"},{\"expected\":false,\"input\":{\"enabled\":-0.5},\"name\":\"indicator-enabled-negative-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":-1.5},\"name\":\"indicator-enabled-negative-fractional-one\"},{\"expected\":false,\"input\":{\"enabled\":[]},\"name\":\"indicator-enabled-empty-list\"},{\"expected\":true,\"input\":{\"enabled\":[0]},\"name\":\"indicator-enabled-nonempty-list\"},{\"expected\":false,\"input\":{\"enabled\":{}},\"name\":\"indicator-enabled-empty-object\"},{\"expected\":true,\"input\":{\"enabled\":{\"enabled\":true}},\"name\":\"indicator-enabled-nonempty-object\"}]";
inline constexpr std::string_view kPythonBacktestIndicatorEnabledReferenceJson = "[{\"expected\":false,\"input\":{},\"name\":\"backtest-indicator-enabled-missing\"},{\"expected\":true,\"input\":{\"enabled\":true},\"name\":\"backtest-indicator-enabled-bool-true\"},{\"expected\":false,\"input\":{\"enabled\":false},\"name\":\"backtest-indicator-enabled-bool-false\"},{\"expected\":true,\"input\":{\"enabled\":\"true\"},\"name\":\"backtest-indicator-enabled-string-true\"},{\"expected\":false,\"input\":{\"enabled\":\"false\"},\"name\":\"backtest-indicator-enabled-string-false\"},{\"expected\":true,\"input\":{\"enabled\":\"yes\"},\"name\":\"backtest-indicator-enabled-string-yes\"},{\"expected\":false,\"input\":{\"enabled\":\"no\"},\"name\":\"backtest-indicator-enabled-string-no\"},{\"expected\":true,\"input\":{\"enabled\":\"on\"},\"name\":\"backtest-indicator-enabled-string-on\"},{\"expected\":false,\"input\":{\"enabled\":\"off\"},\"name\":\"backtest-indicator-enabled-string-off\"},{\"expected\":false,\"input\":{\"enabled\":\"disabled\"},\"name\":\"backtest-indicator-enabled-string-disabled\"},{\"expected\":true,\"input\":{\"enabled\":\"none\"},\"name\":\"backtest-indicator-enabled-string-none\"},{\"expected\":true,\"input\":{\"enabled\":\"null\"},\"name\":\"backtest-indicator-enabled-string-null\"},{\"expected\":true,\"input\":{\"enabled\":\"0.5\"},\"name\":\"backtest-indicator-enabled-string-numeric\"},{\"expected\":true,\"input\":{\"enabled\":\"y\"},\"name\":\"backtest-indicator-enabled-string-y\"},{\"expected\":true,\"input\":{\"enabled\":\"maybe\"},\"name\":\"backtest-indicator-enabled-unknown-string\"},{\"expected\":false,\"input\":{\"enabled\":\"\"},\"name\":\"backtest-indicator-enabled-empty-string\"},{\"expected\":false,\"input\":{\"enabled\":null},\"name\":\"backtest-indicator-enabled-null\"},{\"expected\":false,\"input\":{\"enabled\":0},\"name\":\"backtest-indicator-enabled-zero\"},{\"expected\":true,\"input\":{\"enabled\":1},\"name\":\"backtest-indicator-enabled-one\"},{\"expected\":true,\"input\":{\"enabled\":0.5},\"name\":\"backtest-indicator-enabled-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":1.5},\"name\":\"backtest-indicator-enabled-fractional-one\"},{\"expected\":true,\"input\":{\"enabled\":-0.5},\"name\":\"backtest-indicator-enabled-negative-fractional-zero\"},{\"expected\":true,\"input\":{\"enabled\":-1.5},\"name\":\"backtest-indicator-enabled-negative-fractional-one\"},{\"expected\":true,\"input\":{\"enabled\":[]},\"name\":\"backtest-indicator-enabled-empty-list\"},{\"expected\":true,\"input\":{\"enabled\":[0]},\"name\":\"backtest-indicator-enabled-nonempty-list\"},{\"expected\":true,\"input\":{\"enabled\":{}},\"name\":\"backtest-indicator-enabled-empty-object\"},{\"expected\":true,\"input\":{\"enabled\":{\"enabled\":true}},\"name\":\"backtest-indicator-enabled-nonempty-object\"}]";
inline constexpr std::string_view kPythonIntervalSecondsReferenceJson = "[{\"indicator_seconds\":1.0,\"input\":\"1s\",\"loop_seconds\":1},{\"indicator_seconds\":300.0,\"input\":\"5m\",\"loop_seconds\":300},{\"indicator_seconds\":60.0,\"input\":\"1.5m\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"0.5h\",\"loop_seconds\":60},{\"indicator_seconds\":3600.0,\"input\":\"1h\",\"loop_seconds\":3600},{\"indicator_seconds\":86400.0,\"input\":\"1d\",\"loop_seconds\":86400},{\"indicator_seconds\":60.0,\"input\":\"1w\",\"loop_seconds\":604800},{\"indicator_seconds\":60.0,\"input\":\"1mo\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"1y\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"5\",\"loop_seconds\":5},{\"indicator_seconds\":0.0,\"input\":\"0m\",\"loop_seconds\":1},{\"indicator_seconds\":-60.0,\"input\":\"-1m\",\"loop_seconds\":1},{\"indicator_seconds\":60.0,\"input\":\"1M\",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\" 5m \",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"5m \",\"loop_seconds\":60},{\"indicator_seconds\":60.0,\"input\":\"\",\"loop_seconds\":60}]";
inline constexpr std::string_view kPythonBacktestIntervalSecondsReferenceJson = "[{\"input\":\"1s\",\"seconds\":1.0},{\"input\":\"5m\",\"seconds\":300.0},{\"input\":\"1.5m\",\"seconds\":90.0},{\"input\":\"0.5h\",\"seconds\":1800.0},{\"input\":\"1h\",\"seconds\":3600.0},{\"input\":\"1d\",\"seconds\":86400.0},{\"input\":\"1w\",\"seconds\":604800.0},{\"input\":\"1mo\",\"seconds\":60.0},{\"input\":\"1y\",\"seconds\":60.0},{\"input\":\"5\",\"seconds\":5.0},{\"input\":\"0m\",\"seconds\":1.0},{\"input\":\"-1m\",\"seconds\":1.0},{\"input\":\"1M\",\"seconds\":60.0},{\"input\":\" 5m \",\"seconds\":300.0},{\"input\":\"5m \",\"seconds\":300.0},{\"input\":\"\",\"seconds\":60.0},{\"input\":\"abc\",\"seconds\":60.0},{\"input\":\"5x\",\"seconds\":60.0}]";
inline constexpr std::string_view kPythonStopIntentReferenceJson = "{\"cases\":[{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{},\"name\":\"default-close-all\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":false},\"name\":\"explicit-close-all\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":true},\"name\":\"explicit-keep-open\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":\"true\"},\"name\":\"string-keep-open\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"false\"},\"name\":\"string-close-all\"}],\"schema_version\":1}";
inline constexpr std::string_view kPythonStopIntentLooseReferenceJson = "{\"cases\":[{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{},\"name\":\"missing\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":null},\"name\":\"null\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"\"},\"name\":\"empty-string\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"y\"},\"name\":\"string-y-is-false\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":\"maybe\"},\"name\":\"unknown-string-is-false\"},{\"expected\":{\"close_positions\":true,\"stop_without_close\":false},\"input\":{\"stop_without_close\":0.5},\"name\":\"fractional-zero-is-false\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":1.5},\"name\":\"fractional-one-is-true\"},{\"expected\":{\"close_positions\":false,\"stop_without_close\":true},\"input\":{\"stop_without_close\":-1.5},\"name\":\"negative-fraction-is-true\"}],\"schema_version\":1}";

struct PythonConnectorNormalizationReferenceCase {
    std::string_view name;
    std::string_view input;
    std::string_view expected;
};

inline constexpr std::array<PythonConnectorNormalizationReferenceCase, 16> kPythonConnectorNormalizationReferenceCases = {
    PythonConnectorNormalizationReferenceCase{"empty", "", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"usds-key", "binance-sdk-derivatives-trading-usds-futures", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"usds-underscore-key", "binance_sdk_derivatives_trading_usds_futures", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"usds-label", "Binance SDK Derivatives Trading USD\u24c8 Futures (Official Recommended)", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"coin-key", "binance-sdk-derivatives-trading-coin-futures", "binance-sdk-derivatives-trading-coin-futures"},
    PythonConnectorNormalizationReferenceCase{"coin-label", "Binance SDK Derivatives Trading COIN-M Futures", "binance-sdk-derivatives-trading-coin-futures"},
    PythonConnectorNormalizationReferenceCase{"spot-label", "Binance SDK Spot (Official Recommended)", "binance-sdk-spot"},
    PythonConnectorNormalizationReferenceCase{"connector-label", "Binance Connector Python", "binance-connector"},
    PythonConnectorNormalizationReferenceCase{"ccxt-label", "CCXT (Unified)", "ccxt"},
    PythonConnectorNormalizationReferenceCase{"python-binance-label", "python-binance (Community)", "python-binance"},
    PythonConnectorNormalizationReferenceCase{"official-connector-alias", "Binance Official REST connector", "binance-connector"},
    PythonConnectorNormalizationReferenceCase{"unrelated-option-falls-back", "OANDA REST-v20", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"legacy-gateway-falls-back", "gateway", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"legacy-custom-falls-back", "custom", "binance-sdk-derivatives-trading-usds-futures"},
    PythonConnectorNormalizationReferenceCase{"url-value-falls-back", "https://connector.example.test/api", "binance-connector"},
    PythonConnectorNormalizationReferenceCase{"unknown-falls-back", "unknown backend", "binance-sdk-derivatives-trading-usds-futures"},
};

struct PythonNativeRuntimeConnectorOwnershipReferenceCase {
    std::string_view name;
    std::string_view input;
    bool expectedOwned;
};

inline constexpr std::array<PythonNativeRuntimeConnectorOwnershipReferenceCase, 14> kPythonNativeRuntimeConnectorOwnershipReferenceCases = {
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"empty-default", "", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"usds-key", "binance-sdk-derivatives-trading-usds-futures", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"usds-underscore-alias", "binance_sdk_derivatives_trading_usds_futures", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"usds-label", "Binance SDK Derivatives Trading USD\u24c8 Futures (Official Recommended)", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"usds-readable-alias", "Binance SDK USD-M Futures", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"coin-key", "binance-sdk-derivatives-trading-coin-futures", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"spot-key", "binance-sdk-spot", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"binance-connector-key", "binance-connector", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"ccxt-label", "CCXT (Unified)", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"python-binance-label", "python-binance (Community)", true},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"oanda-provider-option", "OANDA REST-v20", false},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"custom-provider", "custom", false},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"unknown-provider", "unknown backend", false},
    PythonNativeRuntimeConnectorOwnershipReferenceCase{"connector-url-alias", "https://connector.example.test/api", true},
};

struct PythonNativeRuntimeRoutingReferenceCase {
    std::string_view name;
    std::string_view selectedExchange;
    std::string_view connectorBackend;
    std::string_view indicatorSource;
    bool expectedOwned;
};

inline constexpr std::array<PythonNativeRuntimeRoutingReferenceCase, 15> kPythonNativeRuntimeRoutingReferenceCases = {
    PythonNativeRuntimeRoutingReferenceCase{"binance-default", "Binance", "", "", true},
    PythonNativeRuntimeRoutingReferenceCase{"binance-usds-canonical", "Binance", "binance-sdk-derivatives-trading-usds-futures", "binance_futures", true},
    PythonNativeRuntimeRoutingReferenceCase{"binance-usds-label", "Binance", "Binance SDK Derivatives Trading USD-M Futures (Official Recommended)", "Binance futures", true},
    PythonNativeRuntimeRoutingReferenceCase{"binance-coin-futures", "Binance", "binance-sdk-derivatives-trading-coin-futures", "", true},
    PythonNativeRuntimeRoutingReferenceCase{"binance-spot", "Binance", "binance-sdk-spot", "Binance spot", true},
    PythonNativeRuntimeRoutingReferenceCase{"non-native-exchange", "Bybit", "binance-sdk-spot", "Binance spot", false},
    PythonNativeRuntimeRoutingReferenceCase{"non-native-connector", "Binance", "OANDA REST-v20", "Binance spot", false},
    PythonNativeRuntimeRoutingReferenceCase{"unknown-connector", "Binance", "unknown backend", "Binance spot", false},
    PythonNativeRuntimeRoutingReferenceCase{"non-native-indicator", "Binance", "binance-sdk-spot", "TradingView", false},
    PythonNativeRuntimeRoutingReferenceCase{"indicator-key-alias", "Binance", "binance-sdk-spot", "spot", true},
    PythonNativeRuntimeRoutingReferenceCase{"indicator-punctuation-alias", "Binance", "binance-sdk-spot", "Binance/futures", true},
    PythonNativeRuntimeRoutingReferenceCase{"empty-indicator", "Binance", "binance-sdk-spot", "", true},
    PythonNativeRuntimeRoutingReferenceCase{"empty-exchange-default", "", "binance-sdk-spot", "Binance spot", true},
    PythonNativeRuntimeRoutingReferenceCase{"whitespace-exchange-rejected", "   ", "binance-sdk-spot", "Binance spot", false},
    PythonNativeRuntimeRoutingReferenceCase{"exchange-display-badge-rejected", "Binance (official)", "binance-sdk-spot", "Binance spot", false},
};
inline constexpr std::string_view kPythonNativeRuntimeRoutingJsonCoercionReferenceJson = "[{\"config\":{\"connector_backend\":1,\"indicator_source\":\"Binance spot\",\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"numeric-connector\"},{\"config\":{\"connector_backend\":[],\"indicator_source\":\"Binance spot\",\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"empty-connector-list\"},{\"config\":{\"connector_backend\":[\"binance-sdk-spot\"],\"indicator_source\":\"Binance spot\",\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"nonempty-connector-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":1},\"expected_owned\":false,\"name\":\"numeric-exchange\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":[]},\"expected_owned\":true,\"name\":\"empty-exchange-list-default\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":[\"Binance\"]},\"expected_owned\":false,\"name\":\"nonempty-exchange-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":1,\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"numeric-indicator\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":false,\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"false-indicator\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":null,\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"null-indicator\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":[],\"selected_exchange\":\"Binance\"},\"expected_owned\":true,\"name\":\"empty-indicator-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"indicator_source\":[0],\"selected_exchange\":\"Binance\"},\"expected_owned\":false,\"name\":\"numeric-first-indicator-list\"},{\"config\":{\"connector_backend\":\"binance-sdk-spot\",\"selected_exchange\":false},\"expected_owned\":true,\"name\":\"false-exchange-default\"}]";

struct PythonNativeRuntimeModeReferenceCase {
    std::string_view name;
    std::string_view input;
    bool expectedTestnet;
};

inline constexpr std::array<PythonNativeRuntimeModeReferenceCase, 11> kPythonNativeRuntimeModeReferenceCases = {
    PythonNativeRuntimeModeReferenceCase{"empty-live", "", false},
    PythonNativeRuntimeModeReferenceCase{"live", "Live", false},
    PythonNativeRuntimeModeReferenceCase{"production", "Production", false},
    PythonNativeRuntimeModeReferenceCase{"demo", "Demo", true},
    PythonNativeRuntimeModeReferenceCase{"demo-testnet", "Demo/Testnet", true},
    PythonNativeRuntimeModeReferenceCase{"testnet", "Testnet", true},
    PythonNativeRuntimeModeReferenceCase{"sandbox", "Sandbox", true},
    PythonNativeRuntimeModeReferenceCase{"embedded-test-marker", "contest", true},
    PythonNativeRuntimeModeReferenceCase{"embedded-demo-marker", "my-demo-mode", true},
    PythonNativeRuntimeModeReferenceCase{"paper-local", "Paper Local", false},
    PythonNativeRuntimeModeReferenceCase{"trimmed-testnet", "  Testnet  ", true},
};
inline constexpr std::string_view kPythonOrderSizingReferenceJson = "{\"cases\":[{\"expected_error\":null,\"expected_quantity\":0.05,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"market\":\"spot\",\"name\":\"spot_min_notional_bump\",\"price\":100.0,\"quantity\":0.023},{\"expected_error\":null,\"expected_quantity\":0.05,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"market\":\"futures\",\"name\":\"futures_min_notional_bump\",\"price\":100.0,\"quantity\":0.023},{\"expected_error\":\"qty<=0\",\"expected_quantity\":0.0,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"market\":\"spot\",\"name\":\"spot_rejects_zero_quantity\",\"price\":100.0,\"quantity\":0.0},{\"expected_error\":\"filters_error: stepSize must be a finite non-negative number\",\"expected_quantity\":0.0,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":-0.01},\"market\":\"futures\",\"name\":\"futures_invalid_step_filter\",\"price\":100.0,\"quantity\":1.0},{\"balance\":100.0,\"expected_percent\":1.0,\"filters\":{\"minNotional\":5.0,\"minQty\":0.02,\"stepSize\":0.01},\"leverage\":5.0,\"market\":\"futures\",\"name\":\"futures_required_percent\",\"price\":100.0}],\"rounding_cases\":[{\"decimals\":2,\"expected_ceil\":1.24,\"expected_floor\":1.23,\"name\":\"positive_decimal\",\"value\":1.231},{\"decimals\":2,\"expected_ceil\":-1.24,\"expected_floor\":-1.23,\"name\":\"negative_decimal\",\"value\":-1.231},{\"decimals\":0,\"expected_ceil\":-2.0,\"expected_floor\":-1.0,\"name\":\"negative_integer_precision\",\"value\":-1.9}],\"schema_version\":1}";
inline constexpr std::string_view kPythonOrderIntentReferenceJson = "{\"cases\":[{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":true,\"market\":\"futures\",\"order_type\":\"MARKET\",\"position_side\":\"\",\"price\":null,\"quantity\":null,\"reduce_only\":false,\"side\":\"SELL\",\"symbol\":\"BTCUSDT\"},\"intent_errors\":[]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":100.0,\"market\":\"futures\",\"name\":\"canonical-close-position\",\"params\":{\"closePosition\":\"true\",\"side\":\"SELL\",\"symbol\":\"BTCUSDT\",\"type\":\"MARKET\"}},{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":false,\"market\":\"futures\",\"order_type\":\"MARKET\",\"position_side\":\"\",\"price\":null,\"quantity\":0.001,\"reduce_only\":false,\"side\":\"SELL\",\"symbol\":\"BTCUSDT\"},\"intent_errors\":[]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":100.0,\"market\":\"futures\",\"name\":\"python-intent-y-is-false-filter-y-is-true\",\"params\":{\"closePosition\":\"y\",\"quantity\":\"0.001\",\"side\":\"SELL\",\"symbol\":\"BTCUSDT\",\"type\":\"MARKET\"}},{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":true,\"market\":\"futures\",\"order_type\":\"LIMIT\",\"position_side\":\"LONG\",\"price\":2000.0,\"quantity\":1.0,\"reduce_only\":true,\"side\":\"BUY\",\"symbol\":\"ETHUSDT\"},\"intent_errors\":[\"closePosition and reduceOnly cannot be used together\"]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":2000.0,\"market\":\"futures\",\"name\":\"canonical-aliases-and-conflicting-flags\",\"params\":{\"close_position\":\"yes\",\"position_side\":\"long\",\"price\":\"2000\",\"quantity\":\"1\",\"reduce_only\":\"on\",\"side\":\"BUY\",\"symbol\":\"ETHUSDT\",\"type\":\"LIMIT\"}},{\"expected\":{\"filter_errors\":[],\"intent\":{\"close_position\":true,\"market\":\"spot\",\"order_type\":\"MARKET\",\"position_side\":\"LONG\",\"price\":null,\"quantity\":null,\"reduce_only\":true,\"side\":\"BUY\",\"symbol\":\"ETHUSDT\"},\"intent_errors\":[\"positionSide is only supported for futures\",\"closePosition orders are only supported for futures\",\"reduceOnly orders are only supported for futures\",\"closePosition and reduceOnly cannot be used together\",\"order quantity must be > 0\"]},\"filters\":{\"minNotional\":5.0,\"minQty\":0.01,\"stepSize\":0.001,\"tickSize\":0.1},\"last_price\":2000.0,\"market\":\"spot\",\"name\":\"spot-rejects-futures-flags\",\"params\":{\"closePosition\":\"true\",\"positionSide\":\"LONG\",\"reduceOnly\":\"true\",\"side\":\"BUY\",\"symbol\":\"ETHUSDT\",\"type\":\"MARKET\"}}],\"schema_version\":1}";
inline constexpr std::string_view kPythonLiveSafetyReferenceJson = "{\"cases\":[{\"expected_errors\":[],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"\",\"api_secret\":\"\",\"config\":{},\"leverage\":0,\"margin_mode\":\"invalid\",\"mode\":\"Demo/Testnet\",\"position_pct\":0.0},\"name\":\"demo-mode-bypasses-live-gates\"},{\"expected_errors\":[\"set live_trading_enabled=true and live_trading_acknowledgement='I_UNDERSTAND_LIVE_TRADING_RISK' or set BOT_ENABLE_LIVE_TRADING=true and BOT_LIVE_TRADING_ACKNOWLEDGEMENT='I_UNDERSTAND_LIVE_TRADING_RISK'\"],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{},\"leverage\":1,\"margin_mode\":\"\",\"mode\":\"Live\",\"position_pct\":2.0},\"name\":\"live-requires-confirmation\"},{\"expected_errors\":[],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":5,\"live_trading_max_position_pct\":3.0,\"live_trading_max_session_orders\":7},\"leverage\":3,\"margin_mode\":\"Isolated\",\"mode\":\"Live\",\"position_pct\":2.0},\"name\":\"live-safe-futures\"},{\"expected_errors\":[\"position_pct 4% exceeds live cap 3%\"],\"input\":{\"account_type\":\"Spot\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":5,\"live_trading_max_position_pct\":3.0,\"live_trading_max_session_orders\":7},\"leverage\":0,\"margin_mode\":\"invalid-is-ignored-for-spot\",\"mode\":\"Live\",\"position_pct\":4.0},\"name\":\"live-spot-position-cap\"},{\"expected_errors\":[\"live_trading_max_leverage must be between 1 and 125\",\"live_trading_max_position_pct must be > 0 and <= 100\",\"live_trading_max_session_orders must be between 1 and 100000\",\"position_pct must be > 0 and <= 100 for live trading\",\"leverage 130 exceeds live cap 126\",\"margin_mode must be Isolated or Cross for live futures trading\"],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"live-api-key\",\"api_secret\":\"live-api-secret\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":126,\"live_trading_max_position_pct\":0.0,\"live_trading_max_session_orders\":0},\"leverage\":130,\"margin_mode\":\"Portfolio\",\"mode\":\"Production\",\"position_pct\":0.0},\"name\":\"live-invalid-caps-and-futures-controls\"},{\"expected_errors\":[\"provide non-placeholder Binance API credentials\"],\"input\":{\"account_type\":\"Futures\",\"api_key\":\"your_api_key\",\"api_secret\":\"testnet\",\"config\":{\"live_trading_acknowledgement\":\"I_UNDERSTAND_LIVE_TRADING_RISK\",\"live_trading_enabled\":true,\"live_trading_max_leverage\":5,\"live_trading_max_position_pct\":3.0,\"live_trading_max_session_orders\":7},\"leverage\":1,\"margin_mode\":\"Cross\",\"mode\":\"Live\",\"position_pct\":2.0},\"name\":\"live-rejects-placeholder-credentials\"}],\"schema_version\":1}";
inline constexpr std::string_view kPythonConnectorHealthReferenceJson = "{\"cases\":[{\"expected_errors\":[\"connector health snapshot missing state\"],\"name\":\"missing-state\",\"snapshot\":{\"health\":\"ok\",\"state\":\"\"}},{\"expected_errors\":[\"connector health snapshot missing health\"],\"name\":\"missing-health\",\"snapshot\":{\"health\":\"\",\"state\":\"ready\"}},{\"expected_errors\":[\"connector health is degraded / paused\"],\"name\":\"not-ready\",\"snapshot\":{\"health\":\"degraded\",\"state\":\"paused\"}},{\"expected_errors\":[\"connector health is degraded\"],\"name\":\"degraded-health\",\"snapshot\":{\"health\":\"degraded\",\"state\":\"ready\"}},{\"expected_errors\":[],\"name\":\"ready-ok\",\"snapshot\":{\"health\":\"ok\",\"state\":\"ready\"}},{\"expected_errors\":[],\"name\":\"ready-unknown\",\"snapshot\":{\"health\":\"unknown\",\"state\":\"ready\"}}],\"schema_version\":1}";
inline constexpr std::string_view kPythonLlmOutputPolicyReferenceJson = "{\"cases\":[{\"expected_violations\":[\"order_execution_claim\",\"direct_order_action\"],\"name\":\"structured-order-and-status\",\"text\":\"{\\\"action\\\":\\\"place_order\\\",\\\"status\\\":\\\"executed\\\"}\"},{\"expected_violations\":[\"order_execution_claim\",\"risk_override\"],\"name\":\"natural-order-and-risk\",\"text\":\"I executed the trade and disabled stop loss.\"},{\"expected_violations\":[\"direct_order_action\"],\"name\":\"fenced-direct-order\",\"text\":\"```json\\n{\\\"tool\\\":\\\"submit_order\\\",\\\"symbol\\\":\\\"BTCUSDT\\\"}\\n```\"},{\"expected_violations\":[\"direct_order_action\",\"risk_override\"],\"name\":\"structured-command-and-risk\",\"text\":\"prefix {\\\"command\\\":\\\"create_order\\\",\\\"disable_stop_loss\\\":true} suffix\"},{\"expected_violations\":[\"order_execution_claim\",\"direct_order_action\",\"risk_override\"],\"name\":\"all-policy-categories\",\"text\":\"Order executed; place_order; disable stop loss.\"},{\"expected_violations\":[],\"name\":\"structured-advice\",\"text\":\"{\\\"action\\\":\\\"advise\\\",\\\"recommendation\\\":\\\"wait\\\",\\\"risk\\\":\\\"keep stop loss enabled\\\"}\"}],\"schema_version\":1}";
inline constexpr std::string_view kPythonLlmChatRequestReferenceJson = "{\"cases\":[{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"gpt-5.5\",\"llm_provider\":\"openai\",\"llm_reasoning_effort\":\"high\"},\"context\":{\"config\":{\"account_type\":\"futures\",\"intervals\":[\"1m\"],\"llm\":{\"llm_api_key\":null,\"token\":\"secret-token\"},\"mode\":\"Live\",\"selected_exchange\":\"Binance\",\"symbols\":[\"BTCUSDT\",\"ETHUSDT\"]},\"logs\":[{\"message\":\"api_key=secret\"}],\"portfolio\":{\"active_pnl\":12.5,\"closed_pnl\":null,\"open_position_records\":{\"BTCUSDT:L\":{\"secret\":\"raw\"}}},\"runtime\":{\"control_plane\":\"python\",\"phase\":\"running\"}},\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Authorization\":\"Bearer parity-test-key\",\"Content-Type\":\"application/json\"},\"json\":{\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Be concise\",\"role\":\"system\"},{\"content\":\"Trading context JSON: {\\\"config_summary\\\":{\\\"account_type\\\":\\\"futures\\\",\\\"interval_count\\\":1,\\\"llm\\\":{\\\"llm_api_key\\\":\\\"\\\",\\\"token\\\":\\\"<redacted>\\\"},\\\"mode\\\":\\\"Live\\\",\\\"raw_config_redacted\\\":true,\\\"selected_exchange\\\":\\\"Binance\\\",\\\"symbol_count\\\":2},\\\"execution\\\":{},\\\"logs\\\":{\\\"count\\\":1,\\\"redacted\\\":true},\\\"portfolio_summary\\\":{\\\"active_pnl\\\":12.5,\\\"closed_pnl\\\":null,\\\"closed_position_count\\\":0,\\\"open_position_count\\\":1,\\\"position_records_redacted\\\":true},\\\"privacy_notice\\\":\\\"Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.\\\",\\\"runtime\\\":{\\\"control_plane\\\":\\\"python\\\",\\\"phase\\\":\\\"running\\\"},\\\"status\\\":{}}\",\"role\":\"system\"},{\"content\":\"Summarize risk\",\"role\":\"user\"}],\"model\":\"gpt-5.5\",\"reasoning_effort\":\"high\"},\"mode\":\"cloud\",\"protocol\":\"openai-chat-completions\",\"provider\":\"openai\",\"url\":\"https://api.openai.com/v1/chat/completions\"},\"name\":\"openai-cloud-context-and-reasoning\",\"prompt\":\"Summarize risk\",\"system_prompt\":\"Be concise\"},{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"qwen3.7-max\",\"llm_provider\":\"qwen\",\"llm_reasoning_effort\":\"enabled\"},\"context\":null,\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Authorization\":\"Bearer parity-test-key\",\"Content-Type\":\"application/json\"},\"json\":{\"enable_thinking\":true,\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Explain the signal\",\"role\":\"user\"}],\"model\":\"qwen3.7-max\"},\"mode\":\"cloud\",\"protocol\":\"openai-chat-completions\",\"provider\":\"qwen\",\"url\":\"https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions\"},\"name\":\"qwen-thinking-option\",\"prompt\":\"Explain the signal\",\"system_prompt\":\"\"},{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"claude-sonnet-4-5-20250929\",\"llm_provider\":\"anthropic\",\"llm_reasoning_effort\":\"high\"},\"context\":null,\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\",\"anthropic-version\":\"2023-06-01\",\"x-api-key\":\"parity-test-key\"},\"json\":{\"max_tokens\":9216,\"messages\":[{\"content\":\"Summarize the trade plan\",\"role\":\"user\"}],\"model\":\"claude-sonnet-4-5-20250929\",\"system\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\\n\\nKeep the answer advisory\",\"thinking\":{\"budget_tokens\":8192,\"type\":\"enabled\"}},\"mode\":\"cloud\",\"protocol\":\"anthropic-messages\",\"provider\":\"anthropic\",\"url\":\"https://api.anthropic.com/v1/messages\"},\"name\":\"anthropic-high-thinking\",\"prompt\":\"Summarize the trade plan\",\"system_prompt\":\"Keep the answer advisory\"},{\"config\":{\"llm_api_key\":\"parity-test-key\",\"llm_model\":\"gemini-3-pro-preview\",\"llm_provider\":\"gemini\",\"llm_reasoning_effort\":\"medium\"},\"context\":null,\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\"},\"json\":{\"contents\":[{\"parts\":[{\"text\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\"},{\"text\":\"Explain the risk\"}]}],\"generationConfig\":{\"thinkingConfig\":{\"thinkingLevel\":\"high\"}}},\"mode\":\"cloud\",\"protocol\":\"gemini-generate-content\",\"provider\":\"gemini\",\"url\":\"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-preview:generateContent?key=parity-test-key\"},\"name\":\"gemini-pro-thinking-level\",\"prompt\":\"Explain the risk\",\"system_prompt\":\"\"},{\"config\":{\"llm_allow_public_network\":true,\"llm_base_url\":\"https://llm.example.test/v1\",\"llm_model\":\"RWKV/rwkv-6-world\",\"llm_provider\":\"open-source\",\"llm_reasoning_effort\":\"disabled\"},\"context\":{\"config\":{\"api_key\":\"exchange-secret\",\"symbols\":[\"BTCUSDT\"]},\"custom\":{\"local_detail\":\"must-not-leave-private-runtime\"},\"logs\":[{\"message\":\"Bearer private-secret\"}],\"runtime\":{\"phase\":\"running\"}},\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\"},\"json\":{\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Trading context JSON: {\\\"config_summary\\\":{\\\"account_type\\\":null,\\\"interval_count\\\":0,\\\"llm\\\":{},\\\"mode\\\":null,\\\"raw_config_redacted\\\":true,\\\"selected_exchange\\\":null,\\\"symbol_count\\\":1},\\\"execution\\\":{},\\\"logs\\\":{\\\"count\\\":1,\\\"redacted\\\":true},\\\"portfolio_summary\\\":{\\\"active_pnl\\\":null,\\\"closed_pnl\\\":null,\\\"closed_position_count\\\":0,\\\"open_position_count\\\":0,\\\"position_records_redacted\\\":true},\\\"privacy_notice\\\":\\\"Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.\\\",\\\"runtime\\\":{\\\"phase\\\":\\\"running\\\"},\\\"status\\\":{}}\",\"role\":\"system\"},{\"content\":\"Explain the risk\",\"role\":\"user\"}],\"model\":\"RWKV/rwkv-6-world\",\"reasoning_effort\":\"disabled\"},\"mode\":\"local\",\"protocol\":\"openai-chat-completions\",\"provider\":\"open-source\",\"url\":\"https://llm.example.test/v1/chat/completions\"},\"name\":\"open-source-public-endpoint-privacy\",\"prompt\":\"Explain the risk\",\"system_prompt\":\"\"},{\"config\":{\"llm_model\":\"Qwen/Qwen3-8B\",\"llm_provider\":\"local\",\"llm_reasoning_effort\":\"extra-high\"},\"context\":{\"custom\":{\"local_detail\":\"kept-on-loopback\"}},\"expected\":{\"execution_policy\":{\"advisory_only\":true,\"can_execute_orders\":false,\"owner\":\"strategy_and_risk_runtime\"},\"headers\":{\"Content-Type\":\"application/json\"},\"json\":{\"messages\":[{\"content\":\"Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.\",\"role\":\"system\"},{\"content\":\"Trading context JSON: {\\\"custom\\\":{\\\"local_detail\\\":\\\"kept-on-loopback\\\"}}\",\"role\":\"system\"},{\"content\":\"Explain the risk\",\"role\":\"user\"}],\"model\":\"Qwen/Qwen3-8B\",\"reasoning_effort\":\"xhigh\"},\"mode\":\"local\",\"protocol\":\"openai-chat-completions\",\"provider\":\"local\",\"url\":\"http://127.0.0.1:11434/v1/chat/completions\"},\"name\":\"local-open-source-endpoint\",\"prompt\":\"Explain the risk\",\"system_prompt\":\"\"}],\"schema_version\":1}";
inline constexpr std::string_view kPythonRiskDefaultsJson = "{\"allow_close_ignoring_hold\":false,\"allow_indicator_close_without_signal\":false,\"allow_multi_indicator_close\":false,\"allow_opposite_positions\":true,\"auto_bump_percent_multiplier\":10.0,\"auto_flip_on_close\":true,\"close_on_exit\":false,\"futures_flat_purge_grace_seconds\":12.0,\"futures_flat_purge_miss_threshold\":2,\"hedge_preserve_opposites\":false,\"indicator_flip_confirmation_bars\":1,\"indicator_flip_cooldown_bars\":1,\"indicator_flip_cooldown_seconds\":0.0,\"indicator_min_position_hold_bars\":1,\"indicator_min_position_hold_seconds\":0.0,\"indicator_reentry_cooldown_bars\":1,\"indicator_reentry_cooldown_seconds\":0.0,\"indicator_reentry_requires_signal_reset\":true,\"indicator_use_live_values\":false,\"max_auto_bump_percent\":5.0,\"positions_missing_autoclose\":true,\"positions_missing_grace_seconds\":30,\"positions_missing_threshold\":2,\"require_indicator_flip_signal\":true,\"stop_loss\":{\"enabled\":false,\"mode\":\"usdt\",\"percent\":0.0,\"scope\":\"per_trade\",\"usdt\":0.0},\"strict_indicator_flip_enforcement\":true}";
inline constexpr std::string_view kPythonUiDefaultsJson = "{\"design\":\"Classic\",\"indicator_source\":\"Binance futures\",\"selected_exchange\":\"Binance\",\"theme\":\"Dark\"}";
inline constexpr std::string_view kPythonOrderGuardBehaviorJson = "{\"environment_bool_true_values\":[\"1\",\"true\",\"yes\",\"on\"],\"live_only_requirements\":[\"credentials\",\"live_acknowledgement\",\"session_order_cap\",\"session_order_count_increment\"],\"live_safety_environment\":{\"acknowledgement\":\"BOT_LIVE_TRADING_ACKNOWLEDGEMENT\",\"enabled\":\"BOT_ENABLE_LIVE_TRADING\",\"legacy_acknowledgement\":\"BOT_LIVE_TRADING_ACK\",\"max_leverage\":\"BOT_LIVE_MAX_LEVERAGE\",\"max_position_pct\":\"BOT_LIVE_MAX_POSITION_PCT\",\"max_session_orders\":\"BOT_LIVE_MAX_SESSION_ORDERS\"},\"validate_audit_enabled_all_modes\":true,\"validate_audit_writable_all_modes\":true,\"validate_connector_health_all_modes\":true,\"validate_exchange_filters_all_modes\":true,\"validate_intent_all_modes\":true}";
inline constexpr std::string_view kPythonLiveTradingEnabledEnv = "BOT_ENABLE_LIVE_TRADING";
inline constexpr std::string_view kPythonLiveTradingAckEnv = "BOT_LIVE_TRADING_ACKNOWLEDGEMENT";
inline constexpr std::string_view kPythonLiveTradingAckEnvLegacy = "BOT_LIVE_TRADING_ACK";
inline constexpr std::string_view kPythonLiveTradingMaxLeverageEnv = "BOT_LIVE_MAX_LEVERAGE";
inline constexpr std::string_view kPythonLiveTradingMaxPositionPctEnv = "BOT_LIVE_MAX_POSITION_PCT";
inline constexpr std::string_view kPythonLiveTradingMaxSessionOrdersEnv = "BOT_LIVE_MAX_SESSION_ORDERS";
inline constexpr std::array<std::string_view, 4> kPythonLiveSafetyEnvironmentTrueValues = {
    "1",
    "true",
    "yes",
    "on",
};
inline constexpr std::array<std::string_view, 1> kPythonNativeRuntimeExchanges = {
    "Binance",
};
inline constexpr std::array<std::string_view, 6> kPythonNativeRuntimeConnectorBackends = {
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
};
inline constexpr std::array<std::string_view, 3> kPythonNativeRuntimeMarketFamilies = {
    "usd-m-futures",
    "coin-m-futures",
    "spot",
};
inline constexpr std::string_view kPythonNativeRuntimeExecutionScope = "binance-spot-usds-and-coin-futures";
inline constexpr bool kPythonNativeRuntimeExecutionCapability = true;
struct PythonStringPair {
    std::string_view key;
    std::string_view value;
};

inline constexpr std::array<PythonStringPair, 9> kPythonNativeRuntimeConnectorMarketFamilies = {
    PythonStringPair{"binance-sdk-derivatives-trading-usds-futures", "usd-m-futures"},
    PythonStringPair{"binance-sdk-derivatives-trading-coin-futures", "coin-m-futures"},
    PythonStringPair{"binance-sdk-spot", "spot"},
    PythonStringPair{"binance-connector", "usd-m-futures"},
    PythonStringPair{"binance-connector", "spot"},
    PythonStringPair{"ccxt", "usd-m-futures"},
    PythonStringPair{"ccxt", "spot"},
    PythonStringPair{"python-binance", "usd-m-futures"},
    PythonStringPair{"python-binance", "spot"},
};
inline constexpr std::array<std::string_view, 3> kPythonNativeRuntimeTestnetModeMarkers = {
    "demo",
    "test",
    "sandbox",
};
inline constexpr std::string_view kPythonNativeRuntimeDelegatedOwner = "Python Service API/provider connector";
inline constexpr bool kPythonOrderGuardValidateIntentAllModes = true;
inline constexpr bool kPythonOrderGuardValidateExchangeFiltersAllModes = true;
inline constexpr bool kPythonOrderGuardValidateConnectorHealthAllModes = true;
inline constexpr bool kPythonOrderGuardValidateAuditEnabledAllModes = true;
inline constexpr bool kPythonOrderGuardValidateAuditWritableAllModes = true;
inline constexpr std::array<std::string_view, 4> kPythonOrderGuardLiveOnlyRequirements = {
    "credentials",
    "live_acknowledgement",
    "session_order_cap",
    "session_order_count_increment",
};

struct PythonParityDomain {
    std::string_view key;
    std::string_view title;
    std::string_view pythonSurface;
    std::string_view cppStatus;
    std::string_view rustStatus;
    std::string_view requiredBeforeFullParity;
    bool cppFullParity;
    bool rustFullParity;
};

inline constexpr std::array<PythonParityDomain, 12> kPythonParityDomains = {
    PythonParityDomain{"desktop_shell_and_tabs", "Desktop shell and primary tabs", "Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"service_api_contract", "Service API contract", "Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"config_persistence", "Config persistence and hydration", "Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"strategy_runtime", "Strategy runtime and signal generation", "Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"exchange_connectors", "Exchange connectors and market data", "Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"account_portfolio_positions", "Account, portfolio, and positions", "Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"order_execution_and_risk", "Order execution, audit, and risk", "Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"backtest_engine", "Backtest engine, optimizer, and scanner", "Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"charts_and_heatmaps", "Charts and liquidation heatmaps", "TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"logs_terminal_diagnostics", "Logs, terminal, and diagnostics", "Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"llm_advisory", "LLM advisory and local model lifecycle", "Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
    PythonParityDomain{"startup_packaging_platform", "Startup, packaging, and platform integration", "Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.", "Complete", "Complete", "C++: Complete | Rust: Complete", true, true},
};

inline constexpr std::array<std::string_view, 12> kPythonParityDomainKeys = {
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
};

inline constexpr std::array<std::string_view, 5> kPythonRemoteServiceConfigProtectedFields = {
    "api_key",
    "api_secret",
    "connector_order_circuit_incident_log_path",
    "llm_api_key",
    "order_audit_log_path",
};

inline constexpr std::array<std::string_view, 36> kPythonServiceRouteNames = {
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
};

struct PythonServiceRoute {
    std::string_view name;
    std::string_view path;
    std::string_view methods;
};

inline constexpr std::array<PythonServiceRoute, 36> kPythonServiceRoutes = {
    PythonServiceRoute{"runtime", "/api/v1/runtime", "GET"},
    PythonServiceRoute{"dashboard", "/api/v1/dashboard", "GET"},
    PythonServiceRoute{"status", "/api/v1/status", "GET"},
    PythonServiceRoute{"metrics", "/api/v1/metrics", "GET"},
    PythonServiceRoute{"prometheus_metrics", "/api/v1/metrics/prometheus", "GET"},
    PythonServiceRoute{"execution", "/api/v1/execution", "GET"},
    PythonServiceRoute{"backtest", "/api/v1/backtest", "GET"},
    PythonServiceRoute{"config_summary", "/api/v1/config-summary", "GET"},
    PythonServiceRoute{"config", "/api/v1/config", "GET,PUT,PATCH"},
    PythonServiceRoute{"config_persistence", "/api/v1/config/persistence", "GET"},
    PythonServiceRoute{"config_save", "/api/v1/config/save", "POST"},
    PythonServiceRoute{"config_load", "/api/v1/config/load", "POST"},
    PythonServiceRoute{"runtime_state", "/api/v1/runtime/state", "PUT"},
    PythonServiceRoute{"operational_preflight", "/api/v1/runtime/operational-preflight", "GET"},
    PythonServiceRoute{"control_start", "/api/v1/control/start", "POST"},
    PythonServiceRoute{"control_stop", "/api/v1/control/stop", "POST"},
    PythonServiceRoute{"position_close", "/api/v1/positions/close", "POST"},
    PythonServiceRoute{"control_start_failed", "/api/v1/control/start-failed", "POST"},
    PythonServiceRoute{"connector_order_circuit_breaker", "/api/v1/runtime/connector-order-circuit-breaker", "GET,PUT"},
    PythonServiceRoute{"connector_order_circuit_breaker_reset", "/api/v1/runtime/connector-order-circuit-breaker/reset", "POST"},
    PythonServiceRoute{"connector_order_circuit_incidents", "/api/v1/runtime/connector-order-circuit-breaker/incidents", "GET"},
    PythonServiceRoute{"backtest_run", "/api/v1/backtest/run", "POST"},
    PythonServiceRoute{"backtest_stop", "/api/v1/backtest/stop", "POST"},
    PythonServiceRoute{"account", "/api/v1/account", "GET,PUT"},
    PythonServiceRoute{"portfolio", "/api/v1/portfolio", "GET,PUT"},
    PythonServiceRoute{"exchange_connector", "/api/v1/exchange/connector", "GET,PUT"},
    PythonServiceRoute{"logs", "/api/v1/logs", "GET,POST"},
    PythonServiceRoute{"terminal_run", "/api/v1/terminal/run", "POST"},
    PythonServiceRoute{"llm_providers", "/api/v1/llm/providers", "GET"},
    PythonServiceRoute{"llm_config", "/api/v1/llm/config", "GET,PATCH"},
    PythonServiceRoute{"llm_prompt", "/api/v1/llm/prompt", "POST"},
    PythonServiceRoute{"llm_local_model_status", "/api/v1/llm/local-model/status", "GET"},
    PythonServiceRoute{"llm_local_model_start", "/api/v1/llm/local-model/start", "POST"},
    PythonServiceRoute{"llm_local_model_pull", "/api/v1/llm/local-model/pull", "POST"},
    PythonServiceRoute{"llm_local_model_delete", "/api/v1/llm/local-model/delete", "POST"},
    PythonServiceRoute{"stream_dashboard", "/api/v1/stream/dashboard", "GET"},
};

struct PythonServiceRouteSchema {
    std::string_view name;
    std::string_view queryFields;
    std::string_view requestFields;
    std::string_view responseFields;
};

inline constexpr std::array<PythonServiceRouteSchema, 36> kPythonServiceRouteSchemas = {
    PythonServiceRouteSchema{"runtime", "", "", "service_name,phase,python_entrypoint,desktop_entrypoint,repo_root,platform,python_version,capabilities,control_plane,notes"},
    PythonServiceRouteSchema{"dashboard", "log_limit,incident_limit", "", "runtime,status,operational,config,config_summary,config_persistence,execution,backtest,account,portfolio,logs,service_api,connector_order_circuit_incidents"},
    PythonServiceRouteSchema{"status", "", "", "state,lifecycle_phase,requested_action,close_positions_requested,status_message,last_transition_at,service_mode,generated_at,api_enabled,docker_required,runtime_source,active_engine_count,account_type,mode,selected_exchange,connector_backend,connector_health,exchange_connector,operational_health,operational,notes"},
    PythonServiceRouteSchema{"metrics", "", "", "generated_at,operational_health,connector_health,connector_state,runtime_active,active_engine_count,log_warning_count,log_error_count,connector_order_circuit_open,unresolved_order_intent_count"},
    PythonServiceRouteSchema{"prometheus_metrics", "", "", ""},
    PythonServiceRouteSchema{"execution", "", "", "executor_kind,owner,state,workload_kind,session_id,requested_job_count,active_engine_count,progress_label,progress_percent,heartbeat_at,tick_count,last_action,last_message,started_at,updated_at,source,notes"},
    PythonServiceRouteSchema{"backtest", "", "", "session_id,state,workload_kind,status_message,symbols,intervals,indicator_keys,logic,symbol_source,capital,run_count,error_count,cancelled,started_at,completed_at,updated_at,source,top_run,runs,top_runs,errors"},
    PythonServiceRouteSchema{"config_summary", "", "", "mode,account_type,connector_backend,selected_exchange,code_language,theme,design,api_credentials_present,symbol_count,interval_count,enabled_indicator_count,runtime_pair_count,backtest_pair_count,llm_enabled,llm_provider,llm_mode,llm_api_key_present"},
    PythonServiceRouteSchema{"config", "", "config", "mode,account_type,margin_mode,position_mode,side,leverage,position_pct,connector_backend,selected_exchange,code_language,theme,design,order_audit_max_bytes,order_audit_backup_count,connector_order_circuit_incident_log_max_bytes,connector_order_circuit_incident_log_backup_count,operational_connector_snapshot_stale_seconds,operational_execution_heartbeat_stale_seconds,operational_account_snapshot_stale_seconds,operational_portfolio_snapshot_stale_seconds,operational_live_start_gate_enabled,operational_live_order_gate_enabled,live_allow_auto_bump_to_min_order,symbols,intervals,api_credentials_present,llm,exchange_support"},
    PythonServiceRouteSchema{"config_persistence", "", "", "path,exists,modified_at,kind,format_version,loaded,dirty,last_loaded_at,last_saved_at,migrated_from_format_version"},
    PythonServiceRouteSchema{"config_save", "", "path,source,allow_unsafe_path", "path,exists,modified_at,kind,format_version,loaded,dirty,last_loaded_at,last_saved_at,migrated_from_format_version"},
    PythonServiceRouteSchema{"config_load", "", "path,source,allow_unsafe_path", "config,persistence"},
    PythonServiceRouteSchema{"runtime_state", "", "active,active_engine_count,source", "state,lifecycle_phase,requested_action,close_positions_requested,status_message,last_transition_at,service_mode,generated_at,api_enabled,docker_required,runtime_source,active_engine_count,account_type,mode,selected_exchange,connector_backend,connector_health,exchange_connector,operational_health,operational,notes"},
    PythonServiceRouteSchema{"operational_preflight", "", "", "state,message,mode,live_mode,generated_at,start,orders,freshness,critical_stale,reasons"},
    PythonServiceRouteSchema{"control_start", "", "requested_job_count,source", "accepted,action,lifecycle_phase,runtime_active,active_engine_count,requested_job_count,close_positions_requested,source,status_message,generated_at"},
    PythonServiceRouteSchema{"control_stop", "", "close_positions,source", "accepted,action,lifecycle_phase,runtime_active,active_engine_count,requested_job_count,close_positions_requested,source,status_message,generated_at"},
    PythonServiceRouteSchema{"position_close", "", "symbol,side_key,interval,quantity,target_identity,confirm_close,source", "accepted,action,symbol,side_key,interval,quantity,target_identity,source,status_message,generated_at"},
    PythonServiceRouteSchema{"control_start_failed", "", "reason,source", "accepted,action,lifecycle_phase,runtime_active,active_engine_count,requested_job_count,close_positions_requested,source,status_message,generated_at"},
    PythonServiceRouteSchema{"connector_order_circuit_breaker", "", "snapshot,source,force", "active,state,reason,message,block_count,block_threshold,block_window_seconds,tripped_at,cleared_at,source,symbol,interval,side,account_type,connector_health,connector_state,reset_blocked,reset_blocked_reason,reset_blocked_at,recovery_pending,recovery_pending_reason,last_event,generated_at"},
    PythonServiceRouteSchema{"connector_order_circuit_breaker_reset", "", "snapshot,source,force", "active,state,reason,message,block_count,block_threshold,block_window_seconds,tripped_at,cleared_at,source,symbol,interval,side,account_type,connector_health,connector_state,reset_blocked,reset_blocked_reason,reset_blocked_at,recovery_pending,recovery_pending_reason,last_event,generated_at"},
    PythonServiceRouteSchema{"connector_order_circuit_incidents", "limit", "", "path,path_source,configured_path,max_bytes,backup_count,exists,limit,count,total_read,events,parse_errors,last_event,error"},
    PythonServiceRouteSchema{"backtest_run", "", "request,source", "accepted,action,session_id,state,status_message,source"},
    PythonServiceRouteSchema{"backtest_stop", "", "source", "accepted,action,session_id,state,status_message,source"},
    PythonServiceRouteSchema{"account", "", "total_balance,available_balance,source", "account_type,mode,selected_exchange,connector_backend,balance_currency,total_balance,available_balance,source,generated_at"},
    PythonServiceRouteSchema{"portfolio", "", "open_position_records,closed_position_records,closed_trade_registry,active_pnl,active_margin,closed_pnl,closed_margin,total_balance,available_balance,source", "account_type,open_position_count,closed_position_count,active_pnl,active_margin,closed_pnl,closed_margin,total_balance,available_balance,positions,source,generated_at"},
    PythonServiceRouteSchema{"exchange_connector", "", "snapshot,source", "health,state,generated_at,source,selected_exchange,connector_backend,selected_forex_broker,account_type,mode,support,rate_limit,network,last_error,attention,order_audit,order_intents"},
    PythonServiceRouteSchema{"logs", "limit", "message,source,level", "sequence_id,level,message,source,generated_at"},
    PythonServiceRouteSchema{"terminal_run", "", "command,source", "command,exit_code,output,source,generated_at"},
    PythonServiceRouteSchema{"llm_providers", "", "", "key,label,mode,protocol,default_base_url,default_model,api_key_env,model_suggestions,reasoning_efforts,default_reasoning_effort,catalog_revision,catalog_path,custom_models_env,custom_models_path_env,catalog_note,notes"},
    PythonServiceRouteSchema{"llm_config", "", "config", "enabled,provider,provider_label,mode,protocol,catalog_revision,catalog_path,custom_models_env,custom_models_path_env,model,base_url,api_key_env,api_key_present,allow_public_network,use_for,reasoning_effort,default_reasoning_effort,reasoning_efforts,model_suggestions,notes,execution_policy"},
    PythonServiceRouteSchema{"llm_prompt", "", "prompt,system_prompt,dry_run,source", "provider,model,dry_run,prompt,system_prompt,response,source"},
    PythonServiceRouteSchema{"llm_local_model_status", "base_url,model", "", "model,base_url,server_kind,installed,can_download,can_start,available_models,error,storage_hint,storage_paths,estimated_size_label,free_disk_gb,recommended_free_disk_gb,disk_space_warning"},
    PythonServiceRouteSchema{"llm_local_model_start", "", "base_url,model,source", "started,server_kind,executable,error"},
    PythonServiceRouteSchema{"llm_local_model_pull", "", "base_url,model,source", "ok,action,model,status"},
    PythonServiceRouteSchema{"llm_local_model_delete", "", "base_url,model,source", "ok,action,model,status"},
    PythonServiceRouteSchema{"stream_dashboard", "log_limit,incident_limit,interval_ms,max_events", "", "event,data"},
};

inline constexpr std::array<std::string_view, 35> kPythonBacktestRunRequestFields = {
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
};

inline constexpr std::array<std::string_view, 33> kPythonIndicatorKeys = {
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
};

struct PythonIndicator {
    std::string_view key;
    std::string_view displayName;
    bool defaultEnabled;
    std::string_view runtimeConfigJson;
    std::string_view backtestConfigJson;
    std::string_view runtimeOutputKeysCsv;
};

inline constexpr std::array<PythonIndicator, 33> kPythonIndicatorCatalog = {
    PythonIndicator{"ma", "Moving Average (MA)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"type\":\"SMA\"}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\",\"type\":\"SMA\"}", "ma"},
    PythonIndicator{"donchian", "Donchian Channels (DC)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\"}", "donchian_high,donchian_low,donchian"},
    PythonIndicator{"psar", "Parabolic SAR (PSAR)", false, "{\"af\":0.02,\"buy_value\":null,\"enabled\":false,\"max_af\":0.2,\"sell_value\":null}", "{\"af\":0.02,\"buy_value\":0,\"enabled\":false,\"max_af\":0.2,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "psar"},
    PythonIndicator{"bb", "Bollinger Bands (BB)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":100,\"signal_mode\":\"band_position\",\"std\":2}", "bb_upper,bb_mid,bb_lower"},
    PythonIndicator{"bbw", "Bollinger Band Width (BBW)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null,\"std\":2}", "{\"buy_value\":5.0,\"enabled\":false,\"length\":20,\"sell_value\":2.0,\"std\":2}", "bbw"},
    PythonIndicator{"keltner", "Keltner Channels (KC)", false, "{\"atr_length\":10,\"buy_value\":null,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":null}", "{\"atr_length\":10,\"buy_value\":0,\"enabled\":false,\"length\":20,\"multiplier\":2.0,\"sell_value\":100,\"signal_mode\":\"band_position\"}", "keltner_upper,keltner_mid,keltner_lower"},
    PythonIndicator{"ichimoku", "Ichimoku Cloud (IC)", false, "{\"base_length\":26,\"buy_value\":null,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":null,\"span_b_length\":52}", "{\"base_length\":26,\"buy_value\":0,\"conversion_length\":9,\"displacement\":26,\"enabled\":false,\"sell_value\":0,\"span_b_length\":52}", "ichimoku_tenkan,ichimoku_kijun,ichimoku_span_a,ichimoku_span_b,ichimoku_chikou,ichimoku"},
    PythonIndicator{"rsi", "Relative Strength Index (RSI)", true, "{\"buy_value\":null,\"enabled\":true,\"length\":14,\"sell_value\":null}", "{\"buy_value\":30,\"enabled\":true,\"length\":14,\"sell_value\":70}", "rsi"},
    PythonIndicator{"volume", "Volume", false, "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}", "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":20,\"sell_value\":null,\"signal_mode\":\"relative_to_sma\",\"signal_role\":\"filter\"}", "volume"},
    PythonIndicator{"obv", "On-Balance Volume (OBV)", false, "{\"buy_value\":null,\"enabled\":false,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":3,\"sell_value\":0,\"signal_mode\":\"slope\"}", "obv"},
    PythonIndicator{"rvol", "Relative Volume (RVOL)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":1.5,\"enabled\":false,\"length\":20,\"sell_value\":0.75}", "rvol"},
    PythonIndicator{"cmf", "Chaikin Money Flow (CMF)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0.05,\"enabled\":false,\"length\":20,\"sell_value\":-0.05}", "cmf"},
    PythonIndicator{"cci", "Commodity Channel Index (CCI)", false, "{\"buy_value\":null,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":-100,\"constant\":0.015,\"enabled\":false,\"length\":20,\"sell_value\":100}", "cci"},
    PythonIndicator{"roc", "Rate of Change (ROC)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":12,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":12,\"sell_value\":0}", "roc"},
    PythonIndicator{"trix", "Triple Exponential Average (TRIX)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":15,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":15,\"sell_value\":0}", "trix"},
    PythonIndicator{"ppo", "Percentage Price Oscillator (PPO)", false, "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}", "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}", "ppo,ppo_signal,ppo_hist"},
    PythonIndicator{"ao", "Awesome Oscillator (AO)", false, "{\"buy_value\":null,\"enabled\":false,\"fast\":5,\"sell_value\":null,\"slow\":34}", "{\"buy_value\":0,\"enabled\":false,\"fast\":5,\"sell_value\":0,\"slow\":34}", "ao"},
    PythonIndicator{"kst", "Know Sure Thing (KST)", false, "{\"buy_value\":null,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":null,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}", "{\"buy_value\":0,\"enabled\":false,\"roc1\":10,\"roc2\":15,\"roc3\":20,\"roc4\":30,\"sell_value\":0,\"signal\":9,\"sma1\":10,\"sma2\":10,\"sma3\":10,\"sma4\":15}", "kst,kst_signal,kst_hist"},
    PythonIndicator{"aroon", "Aroon Oscillator (AROON)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":25,\"sell_value\":null}", "{\"buy_value\":50,\"enabled\":false,\"length\":25,\"sell_value\":-50}", "aroon_up,aroon_down,aroon"},
    PythonIndicator{"chop", "Choppiness Index (CHOP)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":38.2,\"enabled\":false,\"length\":14,\"sell_value\":61.8}", "chop"},
    PythonIndicator{"atr", "Average True Range (ATR)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":1.0,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_mode\":\"percent_of_close\",\"signal_role\":\"filter\"}", "atr"},
    PythonIndicator{"natr", "Normalized Average True Range (NATR)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":2.0,\"enabled\":false,\"length\":14,\"sell_value\":1.0}", "natr"},
    PythonIndicator{"vwap", "Volume Weighted Average Price (VWAP)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "vwap"},
    PythonIndicator{"mfi", "Money Flow Index (MFI)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80}", "mfi"},
    PythonIndicator{"stoch_rsi", "Stochastic RSI (SRSI)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}", "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}", "stoch_rsi,stoch_rsi_k,stoch_rsi_d"},
    PythonIndicator{"willr", "Williams %R", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":-80,\"enabled\":false,\"length\":14,\"sell_value\":-20}", "willr"},
    PythonIndicator{"macd", "Moving Average Convergence/Divergence (MACD)", false, "{\"buy_value\":null,\"enabled\":false,\"fast\":12,\"sell_value\":null,\"signal\":9,\"slow\":26}", "{\"buy_value\":0,\"enabled\":false,\"fast\":12,\"sell_value\":0,\"signal\":9,\"slow\":26}", "macd_line,macd_signal"},
    PythonIndicator{"uo", "Ultimate Oscillator (UO)", false, "{\"buy_value\":null,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":null,\"short\":7}", "{\"buy_value\":30,\"enabled\":false,\"long\":28,\"medium\":14,\"sell_value\":70,\"short\":7}", "uo"},
    PythonIndicator{"adx", "Average Directional Index (ADX)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":20,\"enabled\":false,\"filter_operator\":\"gte\",\"length\":14,\"sell_value\":null,\"signal_role\":\"filter\"}", "adx"},
    PythonIndicator{"dmi", "Directional Movement Index (DMI)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":14,\"sell_value\":0}", "dmi_plus,dmi_minus,dmi"},
    PythonIndicator{"supertrend", "SuperTrend (ST)", false, "{\"atr_period\":10,\"buy_value\":null,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":null}", "{\"atr_period\":10,\"buy_value\":0,\"enabled\":false,\"multiplier\":3.0,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "supertrend"},
    PythonIndicator{"ema", "Exponential Moving Average (EMA)", false, "{\"buy_value\":null,\"enabled\":false,\"length\":20,\"sell_value\":null}", "{\"buy_value\":0,\"enabled\":false,\"length\":20,\"sell_value\":0,\"signal_mode\":\"price_cross\"}", "ema"},
    PythonIndicator{"stochastic", "Stochastic Oscillator", false, "{\"buy_value\":null,\"enabled\":false,\"length\":14,\"sell_value\":null,\"smooth_d\":3,\"smooth_k\":3}", "{\"buy_value\":20,\"enabled\":false,\"length\":14,\"sell_value\":80,\"smooth_d\":3,\"smooth_k\":3}", "stochastic,stochastic_k,stochastic_d"},
};

inline constexpr std::array<std::string_view, 15> kPythonLlmProviderKeys = {
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
};

inline constexpr std::string_view kPythonLlmProviderCatalogRevision = "2026-07-16";
inline constexpr std::string_view kPythonLlmModelCatalogPathEnv = "BOT_LLM_MODEL_CATALOG_PATH";

struct PythonLlmProvider {
    std::string_view key;
    std::string_view label;
    std::string_view mode;
    std::string_view protocol;
    std::string_view defaultBaseUrl;
    std::string_view defaultModel;
    std::string_view apiKeyEnv;
    std::string_view modelSuggestions;
    std::string_view reasoningEfforts;
    std::string_view defaultReasoningEffort;
    std::string_view catalogRevision;
    std::string_view customModelsEnv;
    std::string_view customModelsPathEnv;
    std::string_view notes;
};

inline constexpr std::array<PythonLlmProvider, 15> kPythonLlmProviders = {
    PythonLlmProvider{"openai", "OpenAI / ChatGPT", "cloud", "openai-chat-completions", "https://api.openai.com/v1", "gpt-5.5", "OPENAI_API_KEY", "gpt-5.6,gpt-5.6-sol,gpt-5.6-terra,gpt-5.6-luna,gpt-5.5,gpt-5.5-2026-04-23,gpt-5.5-pro,gpt-5.5-pro-2026-04-23,gpt-5.4,gpt-5.4-2026-03-05,gpt-5.4-pro,gpt-5.4-pro-2026-03-05,gpt-5.4-mini,gpt-5.4-mini-2026-03-17,gpt-5.4-nano,gpt-5.4-nano-2026-03-17,gpt-5.3-chat-latest,gpt-5.3-codex,gpt-5.2,gpt-5.2-codex,gpt-5.2-chat-latest,gpt-5.2-pro,gpt-5.1,gpt-5-codex,gpt-5-mini,gpt-5-nano,gpt-4.1,gpt-4.1-mini,gpt-4.1-nano", "default,none,minimal,low,medium,high,xhigh,max", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_OPENAI", "BOT_LLM_MODEL_CATALOG_PATH", "Uses the OpenAI-compatible chat completions endpoint.\nGPT-5.6 Sol, Terra, and Luna support reasoning levels through max; availability depends on the API account."},
    PythonLlmProvider{"anthropic", "Anthropic Claude", "cloud", "anthropic-messages", "https://api.anthropic.com", "claude-sonnet-4-5-20250929", "ANTHROPIC_API_KEY", "claude-sonnet-4-5-20250929,claude-haiku-4-5-20251001,claude-opus-4-5-20251101,claude-opus-4-1-20250805,claude-opus-4-20250514,claude-sonnet-4-20250514,claude-sonnet-4-5,claude-haiku-4-5,claude-opus-4-5,claude-opus-4-1,claude-opus-4-0,claude-sonnet-4-0", "default,disabled,enabled,low,medium,high", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_ANTHROPIC", "BOT_LLM_MODEL_CATALOG_PATH", "Uses the Anthropic messages endpoint with the 2023-06-01 API version header."},
    PythonLlmProvider{"gemini", "Google Gemini", "cloud", "gemini-generate-content", "https://generativelanguage.googleapis.com/v1beta", "gemini-3-flash-preview", "GEMINI_API_KEY", "gemini-3.1-pro-preview,gemini-3.1-pro-preview-customtools,gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-preview-09-2025,gemini-2.5-flash-lite,gemini-2.5-flash-lite-preview-09-2025", "default,minimal,low,medium,high", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_GEMINI", "BOT_LLM_MODEL_CATALOG_PATH", "Uses the Gemini generateContent endpoint."},
    PythonLlmProvider{"deepseek", "DeepSeek", "cloud", "openai-chat-completions", "https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY", "deepseek-v4-flash,deepseek-v4-pro,deepseek-chat,deepseek-reasoner", "default,disabled,enabled,high,max", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_DEEPSEEK", "BOT_LLM_MODEL_CATALOG_PATH", "DeepSeek documents an OpenAI-compatible chat completions surface."},
    PythonLlmProvider{"mistral", "Mistral AI", "cloud", "openai-chat-completions", "https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY", "mistral-large-latest,mistral-medium-latest,mistral-small-latest,codestral-latest,open-mistral-nemo", "default,low,medium,high", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_MISTRAL", "BOT_LLM_MODEL_CATALOG_PATH", "Mistral exposes an OpenAI-compatible chat completions API."},
    PythonLlmProvider{"grok", "xAI Grok", "cloud", "openai-chat-completions", "https://api.x.ai/v1", "grok-4.3", "XAI_API_KEY", "grok-4.3,grok-4.3-latest,grok-4.20,grok-4.20-reasoning,grok-4.20-non-reasoning,grok-4-fast-reasoning,grok-4-fast-non-reasoning", "default,low,medium,high", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_GROK", "BOT_LLM_MODEL_CATALOG_PATH", "xAI documents OpenAI-compatible chat completions at /v1/chat/completions."},
    PythonLlmProvider{"qwen", "Alibaba Qwen / DashScope", "cloud", "openai-chat-completions", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.6-plus", "DASHSCOPE_API_KEY", "qwen3.7-max,qwen3.7-max-2026-06-08,qwen3.7-max-2026-05-20,qwen3.6-max-preview,qwen3.6-plus,qwen3.6-plus-2026-04-02,qwen3.6-flash,qwen3.6-flash-2026-04-16,qwen3-max,qwen3-max-2026-01-23,qwen3-max-2025-09-23,qwen3-max-preview,qwen3.5-plus,qwen3.5-plus-2026-02-15,qwen3.5-flash,qwen3.5-flash-2026-02-23,qwen3-coder-plus,qwen3-coder-flash,qwen-plus-us,qwen-flash-us", "default,disabled,enabled,low,medium,high,max", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_QWEN", "BOT_LLM_MODEL_CATALOG_PATH", "DashScope provides OpenAI-compatible endpoints for Qwen models.\nThe request uses enable_thinking for compatible Qwen chat models; Qwen 3.5/3.6 multimodal and Responses-only features require DashScope's corresponding API surface."},
    PythonLlmProvider{"moonshot", "Moonshot AI / Kimi", "cloud", "openai-chat-completions", "https://api.moonshot.ai/v1", "kimi-k3", "MOONSHOT_API_KEY", "kimi-k3,kimi-k2.7-code,kimi-k2.7-code-highspeed,kimi-k2.6,kimi-k2.5", "default,disabled,enabled,max", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_MOONSHOT", "BOT_LLM_MODEL_CATALOG_PATH", "Uses Moonshot's OpenAI-compatible /v1/chat/completions endpoint.\nKimi K3 supports reasoning_effort=max. Kimi K2.5 and K2.6 use thinking enabled or disabled; K2.7 Code always reasons.\nUse the provider model discovery endpoint or the editable model field for account-specific releases."},
    PythonLlmProvider{"local", "Local / Custom OpenAI-Compatible", "local", "openai-chat-completions", "http://127.0.0.1:11434/v1", "qwen3:8b", "LOCAL_LLM_API_KEY", "qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model,Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_LOCAL", "BOT_LLM_MODEL_CATALOG_PATH", "Use this for any local, LAN, private IP, or custom OpenAI-compatible endpoint.\nThe model field is intentionally editable so arbitrary Ollama, GGUF, or Hugging Face IDs can be used."},
    PythonLlmProvider{"ollama", "Ollama", "local", "openai-chat-completions", "http://127.0.0.1:11434/v1", "qwen3:8b", "OLLAMA_API_KEY", "qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_OLLAMA", "BOT_LLM_MODEL_CATALOG_PATH", "Ollama exposes OpenAI-compatible /v1/chat/completions and /v1/models endpoints.\nAutomatic download/start/remove actions are available for localhost Ollama."},
    PythonLlmProvider{"vllm", "vLLM / SGLang", "local", "openai-chat-completions", "http://127.0.0.1:8000/v1", "Qwen/Qwen3-8B", "VLLM_API_KEY", "Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_VLLM", "BOT_LLM_MODEL_CATALOG_PATH", "Use this for self-hosted vLLM or SGLang OpenAI-compatible servers.\nSet Base URL / IP to a LAN, private, or remote /v1 endpoint."},
    PythonLlmProvider{"llamacpp", "llama.cpp server", "local", "openai-chat-completions", "http://127.0.0.1:8080/v1", "local-model", "LLAMACPP_API_KEY", "local-model,qwen3-8b-q4_k_m.gguf,llama-3.1-8b-instruct-q4_k_m.gguf,mistral-7b-instruct-q4_k_m.gguf,gemma-3-4b-it-q4_k_m.gguf,qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,THUDM/glm-4-9b-chat,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_LLAMACPP", "BOT_LLM_MODEL_CATALOG_PATH", "Use this for llama.cpp server; the loaded model name is often reported by /v1/models.\nGGUF filenames are accepted as editable model IDs when your server exposes them."},
    PythonLlmProvider{"lmstudio", "LM Studio", "local", "openai-chat-completions", "http://127.0.0.1:1234/v1", "local-model", "LMSTUDIO_API_KEY", "local-model,Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_LMSTUDIO", "BOT_LLM_MODEL_CATALOG_PATH", "Use this for LM Studio local server or a remote LM Studio-compatible /v1 endpoint.\nThe model field is editable because LM Studio exposes locally downloaded model IDs."},
    PythonLlmProvider{"tgi", "Hugging Face TGI", "local", "openai-chat-completions", "http://127.0.0.1:3000/v1", "tgi", "HUGGINGFACE_API_KEY", "tgi,Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_TGI", "BOT_LLM_MODEL_CATALOG_PATH", "Use this for Hugging Face Text Generation Inference Messages API endpoints.\nRemote Hugging Face Inference Endpoints should include /v1 in the base URL."},
    PythonLlmProvider{"open-source", "Generic Open-Source / Remote", "local", "openai-chat-completions", "http://127.0.0.1:8000/v1", "Qwen/Qwen3-8B", "OPEN_SOURCE_LLM_API_KEY", "Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-4B,Qwen/Qwen3-8B,Qwen/Qwen3-14B,Qwen/Qwen3-32B,Qwen/Qwen3-30B-A3B,Qwen/Qwen2.5-0.5B-Instruct,Qwen/Qwen2.5-1.5B-Instruct,Qwen/Qwen2.5-3B-Instruct,Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-14B-Instruct,Qwen/Qwen2.5-32B-Instruct,Qwen/Qwen2.5-72B-Instruct,Qwen/Qwen2.5-Coder-1.5B-Instruct,Qwen/Qwen2.5-Coder-7B-Instruct,Qwen/Qwen2.5-Coder-14B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,Qwen/QwQ-32B,openai/gpt-oss-20b,openai/gpt-oss-120b,google-t5/t5-small,google-t5/t5-base,google-t5/t5-large,google/flan-t5-small,google/flan-t5-base,google/flan-t5-large,google/flan-t5-xl,google/flan-t5-xxl,RWKV/rwkv-4-world,RWKV/rwkv-5-world,RWKV/rwkv-6-world,BlinkDL/rwkv-7-world,EleutherAI/gpt-neox-20b,EleutherAI/gpt-j-6b,EleutherAI/gpt-neo-2.7B,yandex/yalm-100b,meta-llama/Llama-3.3-70B-Instruct,meta-llama/Llama-3.1-8B-Instruct,meta-llama/Llama-3.1-70B-Instruct,meta-llama/Llama-3.2-1B-Instruct,meta-llama/Llama-3.2-3B-Instruct,mistralai/Mistral-7B-Instruct-v0.3,mistralai/Mistral-Nemo-Instruct-2407,mistralai/Mixtral-8x7B-Instruct-v0.1,mistralai/Mixtral-8x22B-Instruct-v0.1,mistralai/Codestral-22B-v0.1,deepseek-ai/DeepSeek-R1,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B,deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,deepseek-ai/DeepSeek-R1-Distill-Qwen-14B,deepseek-ai/DeepSeek-R1-Distill-Qwen-32B,deepseek-ai/deepseek-coder-6.7b-instruct,deepseek-ai/DeepSeek-Coder-V2-Instruct,google/gemma-3-1b-it,google/gemma-3-4b-it,google/gemma-3-12b-it,google/gemma-3-27b-it,google/gemma-2-2b-it,google/gemma-2-9b-it,google/gemma-2-27b-it,microsoft/phi-4,microsoft/Phi-4-mini-instruct,microsoft/Phi-3.5-mini-instruct,tiiuae/Falcon3-1B-Instruct,tiiuae/Falcon3-3B-Instruct,tiiuae/Falcon3-7B-Instruct,tiiuae/Falcon3-10B-Instruct,tiiuae/falcon-180B-chat,01-ai/Yi-6B-Chat,01-ai/Yi-9B-Chat,01-ai/Yi-34B-Chat,THUDM/glm-4-9b-chat,internlm/internlm2_5-7b-chat,internlm/internlm2_5-20b-chat,baichuan-inc/Baichuan2-7B-Chat,baichuan-inc/Baichuan2-13B-Chat,openbmb/MiniCPM3-4B,HuggingFaceTB/SmolLM2-135M-Instruct,HuggingFaceTB/SmolLM2-360M-Instruct,HuggingFaceTB/SmolLM2-1.7B-Instruct,ibm-granite/granite-3.3-2b-instruct,ibm-granite/granite-3.3-8b-instruct,CohereForAI/c4ai-command-r-v01,CohereForAI/c4ai-command-r-plus,CohereForAI/aya-23-8B,CohereForAI/aya-23-35B,bigscience/bloomz-7b1,bigscience/bloom,mosaicml/mpt-7b-instruct,mosaicml/mpt-30b-instruct,databricks/dbrx-instruct,ai21labs/Jamba-v0.1,Nexusflow/Starling-LM-7B-beta,HuggingFaceH4/zephyr-7b-beta,NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO,openchat/openchat-3.5-0106,WizardLMTeam/WizardLM-2-8x22B,lmsys/vicuna-13b-v1.5,codellama/CodeLlama-7b-Instruct-hf,codellama/CodeLlama-13b-Instruct-hf,codellama/CodeLlama-34b-Instruct-hf,bigcode/starcoder2-3b,bigcode/starcoder2-7b,bigcode/starcoder2-15b,nvidia/Llama-3.1-Nemotron-70B-Instruct-HF,google/flan-ul2,allenai/OLMo-7B-Instruct,allenai/OLMo-2-1124-7B-Instruct,allenai/OLMo-2-1124-13B-Instruct,cerebras/Cerebras-GPT-111M,cerebras/Cerebras-GPT-256M,cerebras/Cerebras-GPT-590M,cerebras/Cerebras-GPT-1.3B,cerebras/Cerebras-GPT-2.7B,cerebras/Cerebras-GPT-6.7B,cerebras/Cerebras-GPT-13B,OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5,EleutherAI/pythia-70m,EleutherAI/pythia-160m,EleutherAI/pythia-410m,EleutherAI/pythia-1b,EleutherAI/pythia-1.4b,EleutherAI/pythia-2.8b,EleutherAI/pythia-6.9b,EleutherAI/pythia-12b,databricks/dolly-v2-3b,databricks/dolly-v2-7b,databricks/dolly-v2-12b,stabilityai/stablelm-base-alpha-3b,stabilityai/stablelm-base-alpha-7b,stabilityai/stablelm-tuned-alpha-3b,stabilityai/stablelm-tuned-alpha-7b,lmsys/fastchat-t5-3b-v1.0,aisquared/dlite-v2-1_5b,h2oai/h2ogpt-oasst1-512-12b,togethercomputer/RedPajama-INCITE-7B-Instruct,openlm-research/open_llama_3b,openlm-research/open_llama_7b,openlm-research/open_llama_13b,mosaicml/mpt-7b-chat,mosaicml/mpt-7b-storywriter,mosaicml/mpt-30b-chat,nomic-ai/gpt4all-j,Salesforce/xgen-7b-8k-inst,inceptionai/jais-13b-chat,codellama/CodeLlama-70b-Instruct-hf,teknium/OpenHermes-2.5-Mistral-7B,apple/OpenELM-270M-Instruct,apple/OpenELM-450M-Instruct,apple/OpenELM-1_1B-Instruct,apple/OpenELM-3B-Instruct,Deci/DeciLM-7B-instruct,THUDM/chatglm-6b,THUDM/chatglm2-6b,THUDM/chatglm3-6b,Skywork/Skywork-13B-base,LLM360/Amber,Cerebras/FLOR-6.3B,Qwen/Qwen1.5-0.5B-Chat,Qwen/Qwen1.5-1.8B-Chat,Qwen/Qwen1.5-4B-Chat,Qwen/Qwen1.5-7B-Chat,Qwen/Qwen1.5-14B-Chat,Qwen/Qwen1.5-32B-Chat,Qwen/Qwen1.5-72B-Chat,Qwen/Qwen1.5-110B-Chat,Qwen/Qwen1.5-MoE-A2.7B-Chat,LargeWorldModel/LWM-Text-1M,YerevaNN/YerevaNN-Grok-1,state-spaces/mamba-130m,state-spaces/mamba-370m,state-spaces/mamba-790m,state-spaces/mamba-1.4b,state-spaces/mamba-2.8b,Snowflake/snowflake-arctic-instruct,Fugaku-LLM/Fugaku-LLM-13B-instruct,tiiuae/Falcon2-11B,01-ai/Yi-1.5-6B-Chat,01-ai/Yi-1.5-9B-Chat,01-ai/Yi-1.5-34B-Chat,deepseek-ai/DeepSeek-V2-Lite-Chat,deepseek-ai/DeepSeek-V2-Chat,deepseek-ai/DeepSeek-V3,deepseek-ai/DeepSeek-V3-0324,deepseek-ai/DeepSeek-V3.1,deepseek-ai/DeepSeek-V3.2,deepseek-ai/DeepSeek-R1-0528,microsoft/Phi-3-medium-128k-instruct,microsoft/Phi-3-mini-128k-instruct,microsoft/phi-4-reasoning,yulan-team/YuLan-Mini,AtlaAI/Selene-1-Mini-Llama-3.1-8B,bigcode/santacoder,Salesforce/codegen2-1B,Salesforce/codegen2-3_7B,Salesforce/codegen2-7B,HuggingFaceH4/starchat-alpha,replit/replit-code-v1-3b,Salesforce/codet5p-770m,Salesforce/codet5p-2b,Salesforce/codet5p-6b,Salesforce/codegen25-7b-multi,Deci/DeciCoder-1b,meta-llama/Llama-2-7b-chat-hf,meta-llama/Llama-2-13b-chat-hf,meta-llama/Llama-2-70b-chat-hf,meta-llama/Llama-3-8B-Instruct,meta-llama/Llama-3-70B-Instruct,meta-llama/Llama-4-Maverick-17B-128E-Instruct,meta-llama/Llama-4-Scout-17B-16E-Instruct,mistralai/Mistral-7B-Instruct-v0.2,mistralai/Mistral-Large-Instruct-2407,mistralai/Mistral-Large-Instruct-2411,Qwen/Qwen2-72B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507,Qwen/Qwen3-235B-A22B-Thinking-2507,Qwen/Qwen3-VL-235B-A22B-Instruct,Qwen/Qwen3.5,Qwen/Qwen3.5-30B-A3B,Qwen/Qwen3.5-Coder,zai-org/GLM-4.5,zai-org/GLM-4.5-Air,zai-org/GLM-4.6,zai-org/GLM-5,moonshotai/Kimi-K2,moonshotai/Kimi-K2-Thinking,moonshotai/Kimi-K2.5,MiniMaxAI/MiniMax-M2.5,stepfun-ai/Step3,stepfun-ai/Step-3.5-Flash,XiaomiMiMo/MiMo-V2-Flash,google/gemma-4-4b-it,google/gemma-4-12b-it,google/gemma-4-27b-it,nvidia/Llama-3.1-Nemotron-Ultra-253B-v1,nvidia/Llama-3.1-Nemotron-Super-49B-v1,nvidia/Llama-3.1-Nemotron-Nano-8B-v1,qwen3:0.6b,qwen3:1.7b,qwen3:4b,qwen3:8b,qwen3:14b,qwen3:30b-a3b,qwen3:32b,qwen3,qwen3-vl:8b,qwen3-vl:32b,qwen3.5,qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b,qwen2.5:7b,qwen2.5:14b,qwen2.5:32b,qwen2.5:72b,qwen2.5-coder:1.5b,qwen2.5-coder:7b,qwen2.5-coder:14b,qwen2.5-coder:32b,qwq:32b,gpt-oss:20b,gpt-oss:120b,gpt-oss:latest,llama4:maverick,llama4:scout,deepseek-v3,deepseek-v3.1,deepseek-v3.2,deepseek-r1:1.5b,deepseek-r1:7b,deepseek-r1:8b,deepseek-r1:14b,deepseek-r1:32b,deepseek-r1:70b,deepseek-coder-v2,llama3.3,llama3.1:8b,llama3.1:70b,llama3.2:1b,llama3.2:3b,llama3.2-vision:11b,llama3.2-vision:90b,mistral,mistral-nemo,mistral-small3.2,mixtral:8x7b,mixtral:8x22b,codestral,devstral,gemma3:1b,gemma3:4b,gemma3:12b,gemma3:27b,gemma4:27b,gemma2:2b,gemma2:9b,gemma2:27b,phi4,phi4-mini,phi3.5,phi3:mini,falcon3:1b,falcon3:3b,falcon3:7b,falcon3:10b,yi:6b,yi:9b,yi:34b,glm4,glm4.5,glm5,kimi-k2,minimax-m2,step3,mimo-v2,internlm2.5,baichuan2:7b,baichuan2:13b,minicpm-v,smollm2:135m,smollm2:360m,smollm2:1.7b,granite3.3:2b,granite3.3:8b,command-r,command-r-plus,starcoder2:3b,starcoder2:7b,starcoder2:15b,codellama:7b,codellama:13b,codellama:34b,dolphin-mixtral,openchat,neural-chat,orca-mini,zephyr,solar,nous-hermes2,wizardlm2,vicuna,rwkv,pythia,dolly-v2,stablelm,redpajama,openllama,mpt,dbrx,arctic,bloom,bloomz,mamba,custom-model", "default,none,disabled,auto,low,medium,high,xhigh", "default", "2026-07-16", "BOT_LLM_EXTRA_MODELS_OPEN_SOURCE", "BOT_LLM_MODEL_CATALOG_PATH", "Use this for any OpenAI-compatible open-source runtime, including remote IP or URL endpoints.\nFor public endpoints, enable Allow public network endpoint so context is minimized."},
};

struct PythonOllamaModelSizeHint {
    std::string_view model;
    std::string_view label;
    double sizeGb;
    bool hasSizeGb;
};

inline constexpr std::array<PythonOllamaModelSizeHint, 33> kPythonOllamaModelSizeHints = {
    PythonOllamaModelSizeHint{"qwen3:0.6b", "about 1 GB", 1, true},
    PythonOllamaModelSizeHint{"qwen3:1.7b", "about 2 GB", 2, true},
    PythonOllamaModelSizeHint{"qwen3:4b", "about 3 GB", 3, true},
    PythonOllamaModelSizeHint{"qwen3:8b", "about 5 GB", 5, true},
    PythonOllamaModelSizeHint{"qwen3:14b", "about 9 GB", 9, true},
    PythonOllamaModelSizeHint{"qwen3:30b-a3b", "about 19 GB", 19, true},
    PythonOllamaModelSizeHint{"qwen3:32b", "about 20 GB", 20, true},
    PythonOllamaModelSizeHint{"qwen3-vl:8b", "about 6 GB", 6, true},
    PythonOllamaModelSizeHint{"qwen3-vl:32b", "about 21 GB", 21, true},
    PythonOllamaModelSizeHint{"qwen2.5:7b", "about 5 GB", 5, true},
    PythonOllamaModelSizeHint{"qwen2.5:14b", "about 9 GB", 9, true},
    PythonOllamaModelSizeHint{"qwen2.5:32b", "about 20 GB", 20, true},
    PythonOllamaModelSizeHint{"qwen2.5:72b", "about 45 GB", 45, true},
    PythonOllamaModelSizeHint{"qwen2.5-coder:7b", "about 5 GB", 5, true},
    PythonOllamaModelSizeHint{"qwen2.5-coder:14b", "about 9 GB", 9, true},
    PythonOllamaModelSizeHint{"qwen2.5-coder:32b", "about 20 GB", 20, true},
    PythonOllamaModelSizeHint{"qwq:32b", "about 20 GB", 20, true},
    PythonOllamaModelSizeHint{"llama3.1:8b", "about 5 GB", 5, true},
    PythonOllamaModelSizeHint{"llama3.1:70b", "about 43 GB", 43, true},
    PythonOllamaModelSizeHint{"llama3.2:3b", "about 2 GB", 2, true},
    PythonOllamaModelSizeHint{"llama3.2:1b", "about 1 GB", 1, true},
    PythonOllamaModelSizeHint{"deepseek-r1:1.5b", "about 2 GB", 2, true},
    PythonOllamaModelSizeHint{"deepseek-r1:7b", "about 5 GB", 5, true},
    PythonOllamaModelSizeHint{"deepseek-r1:8b", "about 5 GB", 5, true},
    PythonOllamaModelSizeHint{"deepseek-r1:14b", "about 9 GB", 9, true},
    PythonOllamaModelSizeHint{"deepseek-r1:32b", "about 20 GB", 20, true},
    PythonOllamaModelSizeHint{"deepseek-r1:70b", "about 43 GB", 43, true},
    PythonOllamaModelSizeHint{"gemma3:1b", "about 1 GB", 1, true},
    PythonOllamaModelSizeHint{"gemma3:4b", "about 3 GB", 3, true},
    PythonOllamaModelSizeHint{"gemma3:12b", "about 8 GB", 8, true},
    PythonOllamaModelSizeHint{"gemma3:27b", "about 17 GB", 17, true},
    PythonOllamaModelSizeHint{"gpt-oss:20b", "about 13 GB", 13, true},
    PythonOllamaModelSizeHint{"gpt-oss:120b", "about 75 GB", 75, true},
};

struct PythonLlmProviderChoice {
    std::string_view key;
    std::string_view value;
};

inline constexpr std::array<PythonLlmProviderChoice, 92> kPythonLlmProviderChoices = {
    PythonLlmProviderChoice{"", "openai"},
    PythonLlmProviderChoice{"alibaba", "qwen"},
    PythonLlmProviderChoice{"alibaba-qwen", "qwen"},
    PythonLlmProviderChoice{"anthropic", "anthropic"},
    PythonLlmProviderChoice{"anthropic-claude", "anthropic"},
    PythonLlmProviderChoice{"arctic", "open-source"},
    PythonLlmProviderChoice{"bloom", "open-source"},
    PythonLlmProviderChoice{"bloomz", "open-source"},
    PythonLlmProviderChoice{"cerebras", "open-source"},
    PythonLlmProviderChoice{"chatglm", "open-source"},
    PythonLlmProviderChoice{"chatgpt", "openai"},
    PythonLlmProviderChoice{"claude", "anthropic"},
    PythonLlmProviderChoice{"codet5", "open-source"},
    PythonLlmProviderChoice{"custom", "local"},
    PythonLlmProviderChoice{"dashscope", "qwen"},
    PythonLlmProviderChoice{"dbrx", "open-source"},
    PythonLlmProviderChoice{"decicoder", "open-source"},
    PythonLlmProviderChoice{"deepseek", "deepseek"},
    PythonLlmProviderChoice{"dolly", "open-source"},
    PythonLlmProviderChoice{"flan-t5", "open-source"},
    PythonLlmProviderChoice{"fugaku", "open-source"},
    PythonLlmProviderChoice{"gemini", "gemini"},
    PythonLlmProviderChoice{"gemma4", "open-source"},
    PythonLlmProviderChoice{"glm", "open-source"},
    PythonLlmProviderChoice{"glm5", "open-source"},
    PythonLlmProviderChoice{"google", "gemini"},
    PythonLlmProviderChoice{"google-gemini", "gemini"},
    PythonLlmProviderChoice{"gpt-neox", "open-source"},
    PythonLlmProviderChoice{"gpt20b", "open-source"},
    PythonLlmProviderChoice{"grok", "grok"},
    PythonLlmProviderChoice{"hf", "open-source"},
    PythonLlmProviderChoice{"hf-tgi", "tgi"},
    PythonLlmProviderChoice{"hugging-face", "open-source"},
    PythonLlmProviderChoice{"huggingface", "open-source"},
    PythonLlmProviderChoice{"huggingface-tgi", "tgi"},
    PythonLlmProviderChoice{"jais", "open-source"},
    PythonLlmProviderChoice{"kimi", "moonshot"},
    PythonLlmProviderChoice{"llama-4", "open-source"},
    PythonLlmProviderChoice{"llama-cpp", "llamacpp"},
    PythonLlmProviderChoice{"llama-cpp-server", "llamacpp"},
    PythonLlmProviderChoice{"llama.cpp", "llamacpp"},
    PythonLlmProviderChoice{"llama4", "open-source"},
    PythonLlmProviderChoice{"llamacpp", "llamacpp"},
    PythonLlmProviderChoice{"lm-studio", "lmstudio"},
    PythonLlmProviderChoice{"lmstudio", "lmstudio"},
    PythonLlmProviderChoice{"local", "local"},
    PythonLlmProviderChoice{"local-openai", "local"},
    PythonLlmProviderChoice{"local-openai-compatible", "local"},
    PythonLlmProviderChoice{"mamba", "open-source"},
    PythonLlmProviderChoice{"mimo", "open-source"},
    PythonLlmProviderChoice{"minimax", "open-source"},
    PythonLlmProviderChoice{"mistral", "mistral"},
    PythonLlmProviderChoice{"mistral-ai", "mistral"},
    PythonLlmProviderChoice{"moonshot", "moonshot"},
    PythonLlmProviderChoice{"moonshot-ai", "moonshot"},
    PythonLlmProviderChoice{"mpt", "open-source"},
    PythonLlmProviderChoice{"nemotron", "open-source"},
    PythonLlmProviderChoice{"ollama", "ollama"},
    PythonLlmProviderChoice{"olmo", "open-source"},
    PythonLlmProviderChoice{"open-llama", "open-source"},
    PythonLlmProviderChoice{"open-source", "open-source"},
    PythonLlmProviderChoice{"open-weight", "open-source"},
    PythonLlmProviderChoice{"open-weights", "open-source"},
    PythonLlmProviderChoice{"openai", "openai"},
    PythonLlmProviderChoice{"openai-chatgpt", "openai"},
    PythonLlmProviderChoice{"openllama", "open-source"},
    PythonLlmProviderChoice{"opensource", "open-source"},
    PythonLlmProviderChoice{"oss", "open-source"},
    PythonLlmProviderChoice{"pythia", "open-source"},
    PythonLlmProviderChoice{"qwen", "qwen"},
    PythonLlmProviderChoice{"qwen-local", "open-source"},
    PythonLlmProviderChoice{"redpajama", "open-source"},
    PythonLlmProviderChoice{"replit-code", "open-source"},
    PythonLlmProviderChoice{"rmkv", "open-source"},
    PythonLlmProviderChoice{"rwkv", "open-source"},
    PythonLlmProviderChoice{"s-glang", "vllm"},
    PythonLlmProviderChoice{"santacoder", "open-source"},
    PythonLlmProviderChoice{"sglang", "vllm"},
    PythonLlmProviderChoice{"stablelm", "open-source"},
    PythonLlmProviderChoice{"starchat", "open-source"},
    PythonLlmProviderChoice{"step", "open-source"},
    PythonLlmProviderChoice{"stepfun", "open-source"},
    PythonLlmProviderChoice{"t5", "open-source"},
    PythonLlmProviderChoice{"text-generation-inference", "tgi"},
    PythonLlmProviderChoice{"tgi", "tgi"},
    PythonLlmProviderChoice{"vllm", "vllm"},
    PythonLlmProviderChoice{"xai", "grok"},
    PythonLlmProviderChoice{"xai-grok", "grok"},
    PythonLlmProviderChoice{"xgen", "open-source"},
    PythonLlmProviderChoice{"xiaomi", "open-source"},
    PythonLlmProviderChoice{"yalm", "open-source"},
    PythonLlmProviderChoice{"zai", "open-source"},
};

struct PythonConfigChoice {
    std::string_view key;
    std::string_view value;
};

inline constexpr std::array<PythonConfigChoice, 2> kPythonAccountTypeConfigChoices = {
    PythonConfigChoice{"spot", "Spot"},
    PythonConfigChoice{"futures", "Futures"},
};

inline constexpr std::array<PythonConfigChoice, 2> kPythonMarginModeConfigChoices = {
    PythonConfigChoice{"isolated", "Isolated"},
    PythonConfigChoice{"cross", "Cross"},
};

inline constexpr std::array<PythonConfigChoice, 3> kPythonPositionModeConfigChoices = {
    PythonConfigChoice{"hedge", "Hedge"},
    PythonConfigChoice{"one-way", "One-way"},
    PythonConfigChoice{"oneway", "One-way"},
};

inline constexpr std::array<PythonConfigChoice, 5> kPythonAssetsModeConfigChoices = {
    PythonConfigChoice{"single-asset", "Single-Asset"},
    PythonConfigChoice{"single-asset mode", "Single-Asset"},
    PythonConfigChoice{"multi-assets", "Multi-Assets"},
    PythonConfigChoice{"multi-asset", "Multi-Assets"},
    PythonConfigChoice{"multi-assets mode", "Multi-Assets"},
};

inline constexpr std::array<PythonConfigChoice, 2> kPythonAccountModeConfigChoices = {
    PythonConfigChoice{"classic trading", "Classic Trading"},
    PythonConfigChoice{"portfolio margin", "Portfolio Margin"},
};

inline constexpr std::array<PythonConfigChoice, 3> kPythonSideConfigChoices = {
    PythonConfigChoice{"both", "BOTH"},
    PythonConfigChoice{"buy", "BUY"},
    PythonConfigChoice{"sell", "SELL"},
};

inline constexpr std::array<PythonConfigChoice, 2> kPythonOrderTypeConfigChoices = {
    PythonConfigChoice{"market", "MARKET"},
    PythonConfigChoice{"limit", "LIMIT"},
};

inline constexpr std::array<PythonConfigChoice, 4> kPythonTifConfigChoices = {
    PythonConfigChoice{"gtc", "GTC"},
    PythonConfigChoice{"ioc", "IOC"},
    PythonConfigChoice{"fok", "FOK"},
    PythonConfigChoice{"gtd", "GTD"},
};

inline constexpr std::array<PythonConfigChoice, 3> kPythonLogicConfigChoices = {
    PythonConfigChoice{"and", "AND"},
    PythonConfigChoice{"or", "OR"},
    PythonConfigChoice{"separate", "SEPARATE"},
};

inline constexpr std::array<PythonConfigChoice, 3> kPythonMddLogicConfigChoices = {
    PythonConfigChoice{"per_trade", "per_trade"},
    PythonConfigChoice{"cumulative", "cumulative"},
    PythonConfigChoice{"entire_account", "entire_account"},
};

inline constexpr std::array<PythonConfigChoice, 3> kPythonStopLossModeConfigChoices = {
    PythonConfigChoice{"usdt", "usdt"},
    PythonConfigChoice{"percent", "percent"},
    PythonConfigChoice{"both", "both"},
};

inline constexpr std::array<PythonConfigChoice, 3> kPythonStopLossScopeConfigChoices = {
    PythonConfigChoice{"per_trade", "per_trade"},
    PythonConfigChoice{"cumulative", "cumulative"},
    PythonConfigChoice{"entire_account", "entire_account"},
};

inline constexpr std::array<PythonConfigChoice, 5> kPythonScanScopeConfigChoices = {
    PythonConfigChoice{"selected", "selected"},
    PythonConfigChoice{"top_n", "top_n"},
    PythonConfigChoice{"top-n", "top_n"},
    PythonConfigChoice{"all_loaded", "all_loaded"},
    PythonConfigChoice{"all-loaded", "all_loaded"},
};

inline constexpr std::array<PythonConfigChoice, 4> kPythonOptimizerModeConfigChoices = {
    PythonConfigChoice{"current", "current"},
    PythonConfigChoice{"single", "single"},
    PythonConfigChoice{"pairs", "pairs"},
    PythonConfigChoice{"combinations", "combinations"},
};

inline constexpr std::array<PythonConfigChoice, 8> kPythonOptimizerMetricConfigChoices = {
    PythonConfigChoice{"roi_percent", "roi_percent"},
    PythonConfigChoice{"roi-percent", "roi_percent"},
    PythonConfigChoice{"roi_percent_mdd", "roi_percent_mdd"},
    PythonConfigChoice{"roi-percent-mdd", "roi_percent_mdd"},
    PythonConfigChoice{"roi_drawdown", "roi_drawdown"},
    PythonConfigChoice{"roi-drawdown", "roi_drawdown"},
    PythonConfigChoice{"roi_value", "roi_value"},
    PythonConfigChoice{"roi-value", "roi_value"},
};

inline constexpr std::array<PythonConfigChoice, 6> kPythonBacktestExecutionBackendConfigChoices = {
    PythonConfigChoice{"desktop", "local"},
    PythonConfigChoice{"desktop-local", "local"},
    PythonConfigChoice{"local", "local"},
    PythonConfigChoice{"remote", "service"},
    PythonConfigChoice{"service", "service"},
    PythonConfigChoice{"service-api", "service"},
};

inline constexpr std::array<PythonConfigChoice, 4> kPythonChartViewModeConfigChoices = {
    PythonConfigChoice{"tradingview", "tradingview"},
    PythonConfigChoice{"original", "original"},
    PythonConfigChoice{"lightweight", "lightweight"},
    PythonConfigChoice{"tradingview lightweight", "lightweight"},
};

inline constexpr std::array<PythonConfigChoice, 4> kPythonLlmUseForConfigChoices = {
    PythonConfigChoice{"advisory", "advisory"},
    PythonConfigChoice{"backtest_explanation", "backtest_explanation"},
    PythonConfigChoice{"risk_review", "risk_review"},
    PythonConfigChoice{"signal_confirmation", "signal_confirmation"},
};

inline constexpr std::array<PythonConfigChoice, 12> kPythonLlmReasoningEffortConfigChoices = {
    PythonConfigChoice{"default", "default"},
    PythonConfigChoice{"disabled", "disabled"},
    PythonConfigChoice{"enabled", "enabled"},
    PythonConfigChoice{"extra-high", "xhigh"},
    PythonConfigChoice{"extra_high", "xhigh"},
    PythonConfigChoice{"high", "high"},
    PythonConfigChoice{"low", "low"},
    PythonConfigChoice{"max", "max"},
    PythonConfigChoice{"medium", "medium"},
    PythonConfigChoice{"minimal", "minimal"},
    PythonConfigChoice{"none", "none"},
    PythonConfigChoice{"xhigh", "xhigh"},
};

inline constexpr std::array<PythonConfigChoice, 7> kPythonPositionPctUnitsConfigChoices = {
    PythonConfigChoice{"percent", "percent"},
    PythonConfigChoice{"%", "percent"},
    PythonConfigChoice{"perc", "percent"},
    PythonConfigChoice{"percentage", "percent"},
    PythonConfigChoice{"fraction", "fraction"},
    PythonConfigChoice{"decimal", "fraction"},
    PythonConfigChoice{"ratio", "fraction"},
};

inline constexpr std::array<std::string_view, 14> kPythonConnectorKeys = {
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
};

struct PythonConnectorOption {
    std::string_view key;
    std::string_view label;
};

inline constexpr std::array<PythonConnectorOption, 14> kPythonConnectorOptions = {
    PythonConnectorOption{"binance-sdk-derivatives-trading-usds-futures", "Binance SDK Derivatives Trading USD\u24c8 Futures (Official Recommended)"},
    PythonConnectorOption{"binance-sdk-derivatives-trading-coin-futures", "Binance SDK Derivatives Trading COIN-M Futures"},
    PythonConnectorOption{"binance-sdk-spot", "Binance SDK Spot (Official Recommended)"},
    PythonConnectorOption{"binance-connector", "Binance Connector Python"},
    PythonConnectorOption{"ccxt", "CCXT (Unified)"},
    PythonConnectorOption{"oanda-rest", "OANDA REST-v20"},
    PythonConnectorOption{"fxcmpy", "FXCM fxcmpy"},
    PythonConnectorOption{"ig-rest", "IG REST Trading API"},
    PythonConnectorOption{"citic-ctp", "CITIC Futures CTP (Local/Remote TCP Front)"},
    PythonConnectorOption{"metatrader4-bridge", "MetaTrader 4 Bridge (Local/Remote Expert Advisor)"},
    PythonConnectorOption{"metatrader5", "MetaTrader 5 (Official Python Integration)"},
    PythonConnectorOption{"trading212-public-api", "Trading 212 Public API (Invest/Stocks ISA equities)"},
    PythonConnectorOption{"moomoo-opend", "moomoo OpenD (Local/Remote Gateway)"},
    PythonConnectorOption{"python-binance", "python-binance (Community)"},
};

struct PythonRustEnvironmentDependency {
    std::string_view key;
    std::string_view label;
    std::string_view kind;
    std::string_view path;
    std::string_view latest;
    std::string_view usage;
};

inline constexpr std::array<PythonRustEnvironmentDependency, 6> kPythonRustEnvironmentDependencies = {
    PythonRustEnvironmentDependency{"rustc", "rustc", "rust_rustc", "", "Install rustup", ""},
    PythonRustEnvironmentDependency{"cargo", "cargo", "rust_cargo", "", "Install rustup", ""},
    PythonRustEnvironmentDependency{"experiments/rust-shells/Cargo.toml", "Trading Bot Rust workspace", "rust_file_version", "experiments/rust-shells/Cargo.toml", "", "Active"},
    PythonRustEnvironmentDependency{"experiments/rust-shells/crates/core/Cargo.toml", "trading-bot-core", "rust_file_version", "experiments/rust-shells/crates/core/Cargo.toml", "", "Active"},
    PythonRustEnvironmentDependency{"experiments/rust-shells/crates/contracts/Cargo.toml", "trading-bot-contracts", "rust_file_version", "experiments/rust-shells/crates/contracts/Cargo.toml", "", "Active"},
    PythonRustEnvironmentDependency{"experiments/rust-shells/apps/tauri-desktop/Cargo.toml", "Tauri (Primary)", "rust_file_version", "experiments/rust-shells/apps/tauri-desktop/Cargo.toml", "", "Active"},
};

inline constexpr std::array<std::string_view, 45> kPythonSupportedBrokers = {
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
};

inline constexpr std::array<std::string_view, 40> kPythonSupportedForexBrokers = {
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
};

struct PythonBrokerOrderRoutingBackend {
    std::string_view broker;
    std::string_view key;
    std::string_view backend;
    std::string_view marketScope;
    bool forexOrderRoutingSupported;
};

inline constexpr std::array<PythonBrokerOrderRoutingBackend, 45> kPythonBrokerOrderRoutingBackends = {
    PythonBrokerOrderRoutingBackend{"OANDA", "oanda", "oanda-rest", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"FXCM", "fxcm", "fxcmpy", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"IG", "ig", "ig-rest", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Trade Nation", "trade nation", "metatrader4-bridge", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"FXTF", "fxtf", "metatrader4-bridge", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"FOREX EXCHANGE", "forex exchange", "metatrader4-bridge", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"AvaTrade", "avatrade", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"EC Markets", "ec markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"GTCFX", "gtcfx", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Finalto", "finalto", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"ATFX", "atfx", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Vantage", "vantage", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"STARTRADER", "startrader", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"XM", "xm", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"TMGM", "tmgm", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Capital.com", "capital.com", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"IC Markets Global", "ic markets global", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Hantec Financial", "hantec financial", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"GO Markets", "go markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"VT Markets", "vt markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Neex", "neex", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"ACY Securities", "acy securities", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Fortune Prime Global", "fortune prime global", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"DecodeFX", "decodefx", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"CPT Markets", "cpt markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"PU Prime", "pu prime", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"AIMS", "aims", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"ETO Markets", "eto markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"D Prime", "d prime", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Fusion Markets", "fusion markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Exness", "exness", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Valetax", "valetax", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"CXM", "cxm", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"DBG Markets", "dbg markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"FXT", "fxt", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"Plotio", "plotio", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"FOREX.com", "forex.com", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"CMC Markets", "cmc markets", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"StoneX", "stonex", "metatrader5", "futures-and-options-on-futures", false},
    PythonBrokerOrderRoutingBackend{"SBCFX", "sbcfx", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"PhillipCapital (Phillip Nova)", "phillipcapital (phillip nova)", "metatrader5", "forex-and-provider-configured-cfd-markets", true},
    PythonBrokerOrderRoutingBackend{"AI Gold Securities", "ai gold securities", "metatrader5", "otc-commodity-derivatives", false},
    PythonBrokerOrderRoutingBackend{"CITIC Futures", "citic futures", "citic-ctp", "china-futures-and-options", false},
    PythonBrokerOrderRoutingBackend{"Trading 212", "trading 212", "trading212-public-api", "invest-and-stocks-isa-equities-only", false},
    PythonBrokerOrderRoutingBackend{"moomoo", "moomoo", "moomoo-opend", "stocks-etfs-options-futures-funds-and-supported-crypto", false},
};

struct PythonBrokerCanonicalName {
    std::string_view identity;
    std::string_view canonical;
};

inline constexpr std::array<PythonBrokerCanonicalName, 54> kPythonBrokerCanonicalNames = {
    PythonBrokerCanonicalName{"oanda", "OANDA"},
    PythonBrokerCanonicalName{"fxcm", "FXCM"},
    PythonBrokerCanonicalName{"ig", "IG"},
    PythonBrokerCanonicalName{"tradenation", "Trade Nation"},
    PythonBrokerCanonicalName{"fxtf", "FXTF"},
    PythonBrokerCanonicalName{"forexexchange", "FOREX EXCHANGE"},
    PythonBrokerCanonicalName{"avatrade", "AvaTrade"},
    PythonBrokerCanonicalName{"ecmarkets", "EC Markets"},
    PythonBrokerCanonicalName{"gtcfx", "GTCFX"},
    PythonBrokerCanonicalName{"finalto", "Finalto"},
    PythonBrokerCanonicalName{"atfx", "ATFX"},
    PythonBrokerCanonicalName{"vantage", "Vantage"},
    PythonBrokerCanonicalName{"startrader", "STARTRADER"},
    PythonBrokerCanonicalName{"xm", "XM"},
    PythonBrokerCanonicalName{"tmgm", "TMGM"},
    PythonBrokerCanonicalName{"capitalcom", "Capital.com"},
    PythonBrokerCanonicalName{"icmarketsglobal", "IC Markets Global"},
    PythonBrokerCanonicalName{"hantecfinancial", "Hantec Financial"},
    PythonBrokerCanonicalName{"gomarkets", "GO Markets"},
    PythonBrokerCanonicalName{"vtmarkets", "VT Markets"},
    PythonBrokerCanonicalName{"neex", "Neex"},
    PythonBrokerCanonicalName{"acysecurities", "ACY Securities"},
    PythonBrokerCanonicalName{"fortuneprimeglobal", "Fortune Prime Global"},
    PythonBrokerCanonicalName{"decodefx", "DecodeFX"},
    PythonBrokerCanonicalName{"cptmarkets", "CPT Markets"},
    PythonBrokerCanonicalName{"puprime", "PU Prime"},
    PythonBrokerCanonicalName{"aims", "AIMS"},
    PythonBrokerCanonicalName{"etomarkets", "ETO Markets"},
    PythonBrokerCanonicalName{"dprime", "D Prime"},
    PythonBrokerCanonicalName{"fusionmarkets", "Fusion Markets"},
    PythonBrokerCanonicalName{"exness", "Exness"},
    PythonBrokerCanonicalName{"valetax", "Valetax"},
    PythonBrokerCanonicalName{"cxm", "CXM"},
    PythonBrokerCanonicalName{"dbgmarkets", "DBG Markets"},
    PythonBrokerCanonicalName{"fxt", "FXT"},
    PythonBrokerCanonicalName{"plotio", "Plotio"},
    PythonBrokerCanonicalName{"forexcom", "FOREX.com"},
    PythonBrokerCanonicalName{"cmcmarkets", "CMC Markets"},
    PythonBrokerCanonicalName{"stonex", "StoneX"},
    PythonBrokerCanonicalName{"sbcfx", "SBCFX"},
    PythonBrokerCanonicalName{"phillipcapitalphillipnova", "PhillipCapital (Phillip Nova)"},
    PythonBrokerCanonicalName{"aigoldsecurities", "AI Gold Securities"},
    PythonBrokerCanonicalName{"citicfutures", "CITIC Futures"},
    PythonBrokerCanonicalName{"trading212", "Trading 212"},
    PythonBrokerCanonicalName{"moomoo", "moomoo"},
    PythonBrokerCanonicalName{"mitrade", "Mitrade"},
    PythonBrokerCanonicalName{"axpm", "AXPM"},
    PythonBrokerCanonicalName{"spreadex", "Spreadex"},
    PythonBrokerCanonicalName{"jefferies", "Jefferies"},
    PythonBrokerCanonicalName{"marex", "Marex"},
    PythonBrokerCanonicalName{"aigold", "AI Gold Securities"},
    PythonBrokerCanonicalName{"phillipsecurities", "PhillipCapital (Phillip Nova)"},
    PythonBrokerCanonicalName{"philipsecurities", "PhillipCapital (Phillip Nova)"},
    PythonBrokerCanonicalName{"cmcmarkes", "CMC Markets"},
};

inline constexpr std::array<std::string_view, 11> kPythonSupportedExchanges = {
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
};

inline constexpr std::array<std::string_view, 14> kPythonSupportedConnectorBackends = {
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
};

inline constexpr std::array<std::string_view, 10> kPythonCcxtDiagnosticExchanges = {
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
};

inline constexpr std::array<std::string_view, 10> kPythonCcxtOrderRoutingExchanges = {
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
};

inline constexpr std::array<std::string_view, 1> kPythonOrderExecutionExchanges = {
    "Binance",
};

inline constexpr std::array<PythonStringPair, 14> kPythonCcxtExchangeIds = {
    PythonStringPair{"bybit", "bybit"},
    PythonStringPair{"okx", "okx"},
    PythonStringPair{"bitget", "bitget"},
    PythonStringPair{"gate", "gateio"},
    PythonStringPair{"gate.io", "gateio"},
    PythonStringPair{"gateio", "gateio"},
    PythonStringPair{"mexc", "mexc"},
    PythonStringPair{"kucoin", "kucoin"},
    PythonStringPair{"htx", "htx"},
    PythonStringPair{"crypto.com", "cryptocom"},
    PythonStringPair{"crypto.com exchange", "cryptocom"},
    PythonStringPair{"cryptocom", "cryptocom"},
    PythonStringPair{"kraken", "kraken"},
    PythonStringPair{"bitfinex", "bitfinex"},
};

inline constexpr std::array<PythonStringPair, 4> kPythonNativeRuntimeIndicatorSourceMarketFamilies = {
    PythonStringPair{"binance_spot", "spot"},
    PythonStringPair{"binance_futures", "usd-m-futures"},
    PythonStringPair{"spot", "spot"},
    PythonStringPair{"futures", "usd-m-futures"},
};

inline constexpr std::array<std::string_view, 38> kPythonBacktestIntervals = {
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
};

struct PythonTradingViewInterval {
    std::string_view interval;
    std::string_view code;
};

inline constexpr std::array<PythonTradingViewInterval, 39> kPythonTradingViewIntervalMap = {
    PythonTradingViewInterval{"1m", "1"},
    PythonTradingViewInterval{"3m", "3"},
    PythonTradingViewInterval{"5m", "5"},
    PythonTradingViewInterval{"10m", "10"},
    PythonTradingViewInterval{"15m", "15"},
    PythonTradingViewInterval{"20m", "20"},
    PythonTradingViewInterval{"30m", "30"},
    PythonTradingViewInterval{"45m", "45"},
    PythonTradingViewInterval{"1h", "60"},
    PythonTradingViewInterval{"2h", "120"},
    PythonTradingViewInterval{"3h", "180"},
    PythonTradingViewInterval{"4h", "240"},
    PythonTradingViewInterval{"5h", "300"},
    PythonTradingViewInterval{"6h", "360"},
    PythonTradingViewInterval{"7h", "420"},
    PythonTradingViewInterval{"8h", "480"},
    PythonTradingViewInterval{"9h", "540"},
    PythonTradingViewInterval{"10h", "600"},
    PythonTradingViewInterval{"11h", "660"},
    PythonTradingViewInterval{"12h", "720"},
    PythonTradingViewInterval{"1d", "1D"},
    PythonTradingViewInterval{"2d", "2D"},
    PythonTradingViewInterval{"3d", "3D"},
    PythonTradingViewInterval{"4d", "4D"},
    PythonTradingViewInterval{"5d", "5D"},
    PythonTradingViewInterval{"6d", "6D"},
    PythonTradingViewInterval{"1w", "1W"},
    PythonTradingViewInterval{"2w", "2W"},
    PythonTradingViewInterval{"3w", "3W"},
    PythonTradingViewInterval{"1mo", "1M"},
    PythonTradingViewInterval{"2mo", "2M"},
    PythonTradingViewInterval{"3mo", "3M"},
    PythonTradingViewInterval{"6mo", "6M"},
    PythonTradingViewInterval{"1month", "1M"},
    PythonTradingViewInterval{"2months", "2M"},
    PythonTradingViewInterval{"3months", "3M"},
    PythonTradingViewInterval{"6months", "6M"},
    PythonTradingViewInterval{"1y", "12M"},
    PythonTradingViewInterval{"2y", "24M"},
};

inline constexpr std::array<std::string_view, 10> kPythonDefaultChartSymbols = {
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
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultExecutionSymbols = {
    "BTCUSDT",
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultExecutionIntervals = {
    "1m",
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultBacktestSymbols = {
    "BTCUSDT",
};

inline constexpr std::array<std::string_view, 1> kPythonDefaultBacktestIntervals = {
    "1h",
};

inline constexpr std::array<std::string_view, 2> kPythonChartMarketOptions = {
    "Futures",
    "Spot",
};

inline constexpr std::array<std::string_view, 2> kPythonAccountModeOptions = {
    "Classic Trading",
    "Portfolio Margin",
};

inline constexpr std::size_t kPythonOptionCatalogCount = 46;
inline constexpr std::size_t kPythonOptionCatalogEntryCount = 267;
inline constexpr std::size_t kPythonUiOptionCatalogCount = 30;
inline constexpr std::size_t kPythonUiOptionEntryCount = 110;

struct PythonOptionCatalogManifestEntry {
    std::string_view name;
    std::size_t entryCount;
};

inline constexpr std::array<PythonOptionCatalogManifestEntry, 46> kPythonOptionCatalogManifest = {
    PythonOptionCatalogManifestEntry{"intervals", 38 },
    PythonOptionCatalogManifestEntry{"tradingview_interval_map", 39 },
    PythonOptionCatalogManifestEntry{"default_chart_symbols", 10 },
    PythonOptionCatalogManifestEntry{"default_execution_symbols", 1 },
    PythonOptionCatalogManifestEntry{"default_execution_intervals", 1 },
    PythonOptionCatalogManifestEntry{"default_backtest_symbols", 1 },
    PythonOptionCatalogManifestEntry{"default_backtest_intervals", 1 },
    PythonOptionCatalogManifestEntry{"chart_market_options", 2 },
    PythonOptionCatalogManifestEntry{"account_mode_options", 2 },
    PythonOptionCatalogManifestEntry{"config_mode_options", 3 },
    PythonOptionCatalogManifestEntry{"theme_options", 6 },
    PythonOptionCatalogManifestEntry{"design_options", 2 },
    PythonOptionCatalogManifestEntry{"indicator_source_options", 2 },
    PythonOptionCatalogManifestEntry{"indicator_ma_type_options", 2 },
    PythonOptionCatalogManifestEntry{"exchange_options", 11 },
    PythonOptionCatalogManifestEntry{"code_language_options", 3 },
    PythonOptionCatalogManifestEntry{"rust_framework_options", 1 },
    PythonOptionCatalogManifestEntry{"starter_market_options", 2 },
    PythonOptionCatalogManifestEntry{"dashboard_loop_choices", 10 },
    PythonOptionCatalogManifestEntry{"lead_trader_options", 4 },
    PythonOptionCatalogManifestEntry{"llm_use_for_options", 4 },
    PythonOptionCatalogManifestEntry{"llm_reasoning_effort_options", 10 },
    PythonOptionCatalogManifestEntry{"position_pct_units_options", 2 },
    PythonOptionCatalogManifestEntry{"dashboard_strategy_templates", 4 },
    PythonOptionCatalogManifestEntry{"side_options", 3 },
    PythonOptionCatalogManifestEntry{"account_type_options", 2 },
    PythonOptionCatalogManifestEntry{"margin_mode_options", 2 },
    PythonOptionCatalogManifestEntry{"position_mode_options", 2 },
    PythonOptionCatalogManifestEntry{"assets_mode_options", 2 },
    PythonOptionCatalogManifestEntry{"order_type_options", 2 },
    PythonOptionCatalogManifestEntry{"time_in_force_options", 4 },
    PythonOptionCatalogManifestEntry{"signal_logic_options", 3 },
    PythonOptionCatalogManifestEntry{"mdd_logic_options", 3 },
    PythonOptionCatalogManifestEntry{"stop_loss_modes", 3 },
    PythonOptionCatalogManifestEntry{"stop_loss_scopes", 3 },
    PythonOptionCatalogManifestEntry{"scan_scope_options", 3 },
    PythonOptionCatalogManifestEntry{"optimizer_mode_options", 4 },
    PythonOptionCatalogManifestEntry{"optimizer_metric_options", 4 },
    PythonOptionCatalogManifestEntry{"backtest_execution_backend_options", 2 },
    PythonOptionCatalogManifestEntry{"chart_view_options", 3 },
    PythonOptionCatalogManifestEntry{"positions_view_options", 2 },
    PythonOptionCatalogManifestEntry{"chart_view_keys", 3 },
    PythonOptionCatalogManifestEntry{"rust_environment_dependencies", 6 },
    PythonOptionCatalogManifestEntry{"connectors", 14 },
    PythonOptionCatalogManifestEntry{"backtest_templates", 3 },
    PythonOptionCatalogManifestEntry{"indicators", 33 },
};

struct PythonUiOption {
    std::string_view key;
    std::string_view label;
    bool disabled;
};

inline constexpr std::array<PythonUiOption, 10> kPythonDashboardLoopChoices = {
    PythonUiOption{"30s", "30 seconds", false},
    PythonUiOption{"45s", "45 seconds", false},
    PythonUiOption{"1m", "1 minute", false},
    PythonUiOption{"2m", "2 minutes", false},
    PythonUiOption{"3m", "3 minutes", false},
    PythonUiOption{"5m", "5 minutes", false},
    PythonUiOption{"10m", "10 minutes", false},
    PythonUiOption{"30m", "30 minutes", false},
    PythonUiOption{"1h", "1 hour", false},
    PythonUiOption{"2h", "2 hours", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonLeadTraderOptions = {
    PythonUiOption{"futures_public", "Futures Public Lead Trader", false},
    PythonUiOption{"futures_private", "Futures Private Lead Trader", false},
    PythonUiOption{"spot_public", "Spot Public Lead Trader", false},
    PythonUiOption{"spot_private", "Spot Private Lead Trader", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonLlmUseForOptions = {
    PythonUiOption{"advisory", "Advisory", false},
    PythonUiOption{"signal_confirmation", "Signal confirmation", false},
    PythonUiOption{"risk_review", "Risk review", false},
    PythonUiOption{"backtest_explanation", "Backtest explanation", false},
};

inline constexpr std::array<PythonUiOption, 10> kPythonLlmReasoningEffortOptions = {
    PythonUiOption{"default", "default", false},
    PythonUiOption{"disabled", "disabled", false},
    PythonUiOption{"enabled", "enabled", false},
    PythonUiOption{"xhigh", "xhigh", false},
    PythonUiOption{"high", "high", false},
    PythonUiOption{"low", "low", false},
    PythonUiOption{"max", "max", false},
    PythonUiOption{"medium", "medium", false},
    PythonUiOption{"minimal", "minimal", false},
    PythonUiOption{"none", "none", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonPositionPctUnitsOptions = {
    PythonUiOption{"percent", "percent", false},
    PythonUiOption{"fraction", "fraction", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonDashboardStrategyTemplates = {
    PythonUiOption{"", "No Template", false},
    PythonUiOption{"top10", "Top 10 %2 per trade 1x Isolated", false},
    PythonUiOption{"top50", "Top 50 %2 per trade 1x", false},
    PythonUiOption{"top100", "Top 100 %1 per trade 1x", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonBacktestTemplates = {
    PythonUiOption{"volume_top50", "First 50 Highest Volume", false},
    PythonUiOption{"volume_last_week", "Last 1 week \u00b7 2% per trade \u00b7 50 highest volume", false},
    PythonUiOption{"top100_isolated_1pct_sl", "Top 100, %2 per trade, isolated, %20 per trade SL", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonSideOptions = {
    PythonUiOption{"BUY", "Buy (Long)", false},
    PythonUiOption{"SELL", "Sell (Short)", false},
    PythonUiOption{"BOTH", "Both (Long/Short)", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonConfigModeOptions = {
    PythonUiOption{"Live", "Live", false},
    PythonUiOption{"Demo", "Demo", false},
    PythonUiOption{"Testnet", "Testnet", false},
};

inline constexpr std::array<PythonUiOption, 6> kPythonThemeOptions = {
    PythonUiOption{"Light", "Light", false},
    PythonUiOption{"Dark", "Dark", false},
    PythonUiOption{"Blue", "Blue", false},
    PythonUiOption{"Yellow", "Yellow", false},
    PythonUiOption{"Green", "Green", false},
    PythonUiOption{"Red", "Red", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonDesignOptions = {
    PythonUiOption{"Classic", "Classic", false},
    PythonUiOption{"Workstation", "Workstation", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonIndicatorSourceOptions = {
    PythonUiOption{"Binance spot", "Binance spot", false},
    PythonUiOption{"Binance futures", "Binance futures", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonIndicatorMaTypeOptions = {
    PythonUiOption{"SMA", "SMA", false},
    PythonUiOption{"EMA", "EMA", false},
};

inline constexpr std::array<PythonUiOption, 11> kPythonExchangeOptions = {
    PythonUiOption{"Binance", "Binance", false},
    PythonUiOption{"Bybit", "Bybit (ccxt order routing)", false},
    PythonUiOption{"OKX", "OKX (ccxt order routing)", false},
    PythonUiOption{"Gate", "Gate (ccxt order routing)", false},
    PythonUiOption{"Bitget", "Bitget (ccxt order routing)", false},
    PythonUiOption{"MEXC", "MEXC (ccxt order routing)", false},
    PythonUiOption{"KuCoin", "KuCoin (ccxt order routing)", false},
    PythonUiOption{"HTX", "HTX (ccxt order routing)", false},
    PythonUiOption{"Crypto.com Exchange", "Crypto.com Exchange (ccxt order routing)", false},
    PythonUiOption{"Kraken", "Kraken (ccxt order routing)", false},
    PythonUiOption{"Bitfinex", "Bitfinex (ccxt order routing)", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonAccountTypeOptions = {
    PythonUiOption{"Spot", "Spot", false},
    PythonUiOption{"Futures", "Futures", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonMarginModeOptions = {
    PythonUiOption{"Isolated", "Isolated", false},
    PythonUiOption{"Cross", "Cross", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonPositionModeOptions = {
    PythonUiOption{"Hedge", "Hedge", false},
    PythonUiOption{"One-way", "One-way", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonAssetsModeOptions = {
    PythonUiOption{"Single-Asset", "Single-Asset Mode", false},
    PythonUiOption{"Multi-Assets", "Multi-Assets Mode", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonOrderTypeOptions = {
    PythonUiOption{"MARKET", "MARKET", false},
    PythonUiOption{"LIMIT", "LIMIT", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonTimeInForceOptions = {
    PythonUiOption{"GTC", "GTC", false},
    PythonUiOption{"IOC", "IOC", false},
    PythonUiOption{"FOK", "FOK", false},
    PythonUiOption{"GTD", "GTD", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonSignalLogicOptions = {
    PythonUiOption{"AND", "AND", false},
    PythonUiOption{"OR", "OR", false},
    PythonUiOption{"SEPARATE", "SEPARATE", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonMddLogicOptions = {
    PythonUiOption{"per_trade", "Per Trade MDD", false},
    PythonUiOption{"cumulative", "Cumulative MDD", false},
    PythonUiOption{"entire_account", "Entire Account MDD", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonStopLossModes = {
    PythonUiOption{"usdt", "USDT Based Stop Loss", false},
    PythonUiOption{"percent", "Percentage Based Stop Loss", false},
    PythonUiOption{"both", "Both Stop Loss (USDT & Percentage)", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonStopLossScopes = {
    PythonUiOption{"per_trade", "Per Trade Stop Loss", false},
    PythonUiOption{"cumulative", "Cumulative Stop Loss", false},
    PythonUiOption{"entire_account", "Entire Account Stop Loss", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonScanScopeOptions = {
    PythonUiOption{"selected", "selected", false},
    PythonUiOption{"top_n", "top_n", false},
    PythonUiOption{"all_loaded", "all_loaded", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonOptimizerModeOptions = {
    PythonUiOption{"current", "current", false},
    PythonUiOption{"single", "single", false},
    PythonUiOption{"pairs", "pairs", false},
    PythonUiOption{"combinations", "combinations", false},
};

inline constexpr std::array<PythonUiOption, 4> kPythonOptimizerMetricOptions = {
    PythonUiOption{"roi_percent", "roi_percent", false},
    PythonUiOption{"roi_percent_mdd", "roi_percent_mdd", false},
    PythonUiOption{"roi_drawdown", "roi_drawdown", false},
    PythonUiOption{"roi_value", "roi_value", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonBacktestExecutionBackendOptions = {
    PythonUiOption{"local", "local", false},
    PythonUiOption{"service", "service", false},
};

inline constexpr std::array<PythonUiOption, 3> kPythonChartViewOptions = {
    PythonUiOption{"tradingview", "TradingView", false},
    PythonUiOption{"original", "Original", false},
    PythonUiOption{"lightweight", "TradingView Lightweight", false},
};

inline constexpr std::array<PythonUiOption, 2> kPythonPositionsViewOptions = {
    PythonUiOption{"cumulative", "Cumulative View", false},
    PythonUiOption{"per_trade", "Per Trade View", false},
};

struct PythonUiOptionCatalog {
    std::string_view name;
    const PythonUiOption *options;
    std::size_t size;
};

inline constexpr std::array<PythonUiOptionCatalog, 30> kPythonUiOptionCatalogs = {
    PythonUiOptionCatalog{"dashboard loop", kPythonDashboardLoopChoices.data(), kPythonDashboardLoopChoices.size()},
    PythonUiOptionCatalog{"lead trader", kPythonLeadTraderOptions.data(), kPythonLeadTraderOptions.size()},
    PythonUiOptionCatalog{"LLM use-for", kPythonLlmUseForOptions.data(), kPythonLlmUseForOptions.size()},
    PythonUiOptionCatalog{"LLM reasoning effort", kPythonLlmReasoningEffortOptions.data(), kPythonLlmReasoningEffortOptions.size()},
    PythonUiOptionCatalog{"position percentage units", kPythonPositionPctUnitsOptions.data(), kPythonPositionPctUnitsOptions.size()},
    PythonUiOptionCatalog{"dashboard strategy templates", kPythonDashboardStrategyTemplates.data(), kPythonDashboardStrategyTemplates.size()},
    PythonUiOptionCatalog{"backtest templates", kPythonBacktestTemplates.data(), kPythonBacktestTemplates.size()},
    PythonUiOptionCatalog{"side", kPythonSideOptions.data(), kPythonSideOptions.size()},
    PythonUiOptionCatalog{"config mode", kPythonConfigModeOptions.data(), kPythonConfigModeOptions.size()},
    PythonUiOptionCatalog{"theme", kPythonThemeOptions.data(), kPythonThemeOptions.size()},
    PythonUiOptionCatalog{"design", kPythonDesignOptions.data(), kPythonDesignOptions.size()},
    PythonUiOptionCatalog{"indicator source", kPythonIndicatorSourceOptions.data(), kPythonIndicatorSourceOptions.size()},
    PythonUiOptionCatalog{"moving average type", kPythonIndicatorMaTypeOptions.data(), kPythonIndicatorMaTypeOptions.size()},
    PythonUiOptionCatalog{"exchange", kPythonExchangeOptions.data(), kPythonExchangeOptions.size()},
    PythonUiOptionCatalog{"account type", kPythonAccountTypeOptions.data(), kPythonAccountTypeOptions.size()},
    PythonUiOptionCatalog{"margin mode", kPythonMarginModeOptions.data(), kPythonMarginModeOptions.size()},
    PythonUiOptionCatalog{"position mode", kPythonPositionModeOptions.data(), kPythonPositionModeOptions.size()},
    PythonUiOptionCatalog{"assets mode", kPythonAssetsModeOptions.data(), kPythonAssetsModeOptions.size()},
    PythonUiOptionCatalog{"order type", kPythonOrderTypeOptions.data(), kPythonOrderTypeOptions.size()},
    PythonUiOptionCatalog{"time in force", kPythonTimeInForceOptions.data(), kPythonTimeInForceOptions.size()},
    PythonUiOptionCatalog{"signal logic", kPythonSignalLogicOptions.data(), kPythonSignalLogicOptions.size()},
    PythonUiOptionCatalog{"MDD logic", kPythonMddLogicOptions.data(), kPythonMddLogicOptions.size()},
    PythonUiOptionCatalog{"stop-loss modes", kPythonStopLossModes.data(), kPythonStopLossModes.size()},
    PythonUiOptionCatalog{"stop-loss scopes", kPythonStopLossScopes.data(), kPythonStopLossScopes.size()},
    PythonUiOptionCatalog{"scan scope", kPythonScanScopeOptions.data(), kPythonScanScopeOptions.size()},
    PythonUiOptionCatalog{"optimizer mode", kPythonOptimizerModeOptions.data(), kPythonOptimizerModeOptions.size()},
    PythonUiOptionCatalog{"optimizer metric", kPythonOptimizerMetricOptions.data(), kPythonOptimizerMetricOptions.size()},
    PythonUiOptionCatalog{"backtest execution backend", kPythonBacktestExecutionBackendOptions.data(), kPythonBacktestExecutionBackendOptions.size()},
    PythonUiOptionCatalog{"chart view", kPythonChartViewOptions.data(), kPythonChartViewOptions.size()},
    PythonUiOptionCatalog{"positions view", kPythonPositionsViewOptions.data(), kPythonPositionsViewOptions.size()},
};

struct PythonStarterOption {
    std::string_view key;
    std::string_view title;
    std::string_view subtitle;
    std::string_view accent;
    std::string_view badge;
    bool disabled;
    bool operational;
    std::string_view operationalStatus;
    std::string_view launchNote;
};

inline constexpr std::array<PythonStarterOption, 3> kPythonCodeLanguageOptions = {
    PythonStarterOption{"Python (PyQt)", "Python", "Fast to build - Huge ecosystem", "#3b82f6", "Recommended", false, false, "", ""},
    PythonStarterOption{"C++ (Qt/C++23)", "C++", "Qt native desktop experiment", "#38bdf8", "Experiment", false, false, "", ""},
    PythonStarterOption{"Rust", "Rust", "Service API client + guarded runtime (promotion-gated)", "#fb923c", "Experiment", false, false, "", ""},
};

inline constexpr std::array<PythonStarterOption, 1> kPythonRustFrameworkOptions = {
    PythonStarterOption{"Tauri", "Tauri", "Operational Service API client", "#f59e0b", "Primary", false, true, "Interactive Service API client", "Tauri can manage/connect to the local Python Service API, but Python still owns strategy, risk, account, order, and exchange execution."},
};

inline constexpr std::array<PythonStarterOption, 2> kPythonStarterMarketOptions = {
    PythonStarterOption{"crypto", "Crypto Exchange", "Binance, Bybit, KuCoin", "#34d399", "", false, false, "", ""},
    PythonStarterOption{"forex", "Forex Exchange", "REST, MT4 bridge, MetaTrader 5, and scoped provider APIs", "#93c5fd", "Evidence required", false, false, "", ""},
};

} // namespace PythonParityContract
