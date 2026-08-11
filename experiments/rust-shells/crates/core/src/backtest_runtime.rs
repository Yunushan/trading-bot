use std::collections::BTreeMap;

use serde_json::{Value, json};

use crate::market_data::BinanceKlineCandle;
use crate::native_indicators::{
    compute_configured_indicator_series, unsupported_enabled_indicator_keys,
};

#[derive(Debug, Clone, PartialEq)]
pub struct NativeBacktestRequest {
    pub symbol: String,
    pub interval: String,
    pub indicators: BTreeMap<String, Value>,
    pub logic: String,
    pub side: String,
    pub capital: f64,
    pub position_pct: f64,
    pub position_pct_units: String,
    pub leverage: f64,
    pub margin_mode: String,
    pub position_mode: String,
    pub assets_mode: String,
    pub account_mode: String,
    pub mdd_logic: String,
    pub stop_loss_enabled: bool,
    pub stop_loss_mode: String,
    pub stop_loss_usdt: f64,
    pub stop_loss_percent: f64,
    pub stop_loss_scope: String,
    pub fee_bps: f64,
    pub slippage_bps: f64,
}

impl Default for NativeBacktestRequest {
    fn default() -> Self {
        Self {
            symbol: String::new(),
            interval: String::new(),
            indicators: BTreeMap::new(),
            logic: "AND".to_owned(),
            side: "BOTH".to_owned(),
            capital: 1_000.0,
            position_pct: 1.0,
            position_pct_units: String::new(),
            leverage: 1.0,
            margin_mode: "Isolated".to_owned(),
            position_mode: "Hedge".to_owned(),
            assets_mode: "Single-Asset".to_owned(),
            account_mode: "Classic Trading".to_owned(),
            mdd_logic: "per_trade".to_owned(),
            stop_loss_enabled: false,
            stop_loss_mode: "usdt".to_owned(),
            stop_loss_usdt: 0.0,
            stop_loss_percent: 0.0,
            stop_loss_scope: "per_trade".to_owned(),
            fee_bps: 5.0,
            slippage_bps: 2.0,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeBacktestResult {
    pub ok: bool,
    pub error: String,
    pub symbol: String,
    pub interval: String,
    pub indicator_keys: Vec<String>,
    pub trades: usize,
    pub roi_value: f64,
    pub roi_percent: f64,
    pub final_equity: f64,
    pub max_drawdown_value: f64,
    pub max_drawdown_percent: f64,
    pub max_drawdown_during_value: f64,
    pub max_drawdown_during_percent: f64,
    pub max_drawdown_result_value: f64,
    pub max_drawdown_result_percent: f64,
    pub logic: String,
    pub leverage: f64,
    pub mdd_logic: String,
    pub side: String,
    pub capital: f64,
    pub position_pct: f64,
    pub position_pct_units: String,
    pub stop_loss_enabled: bool,
    pub stop_loss_mode: String,
    pub stop_loss_usdt: f64,
    pub stop_loss_percent: f64,
    pub stop_loss_scope: String,
    pub margin_mode: String,
    pub position_mode: String,
    pub assets_mode: String,
    pub account_mode: String,
    pub fee_bps: f64,
    pub slippage_bps: f64,
    pub fees_paid: f64,
}

impl NativeBacktestResult {
    fn from_request(request: &NativeBacktestRequest) -> Self {
        let logic = if request.logic.trim().eq_ignore_ascii_case("AND") {
            "AND"
        } else {
            "OR"
        };
        let requested_side = request.side.trim().to_ascii_uppercase();
        let side = match requested_side.as_str() {
            "BUY" | "SELL" | "BOTH" => requested_side,
            _ => "BOTH".to_owned(),
        };
        let requested_mdd_logic = request.mdd_logic.trim().to_ascii_lowercase();
        let mdd_logic = match requested_mdd_logic.as_str() {
            "per_trade" | "cumulative" | "entire_account" => requested_mdd_logic,
            _ => "per_trade".to_owned(),
        };
        let requested_stop_mode = request.stop_loss_mode.trim().to_ascii_lowercase();
        let stop_loss_mode = match requested_stop_mode.as_str() {
            "usdt" | "percent" | "both" => requested_stop_mode,
            _ => "usdt".to_owned(),
        };
        let requested_stop_scope = request.stop_loss_scope.trim().to_ascii_lowercase();
        let stop_loss_scope = match requested_stop_scope.as_str() {
            "per_trade" | "cumulative" | "entire_account" => requested_stop_scope,
            _ => "per_trade".to_owned(),
        };
        let position_units = request.position_pct_units.trim().to_ascii_lowercase();
        let mut position_pct = request.position_pct;
        if matches!(position_units.as_str(), "percent" | "%" | "perc") {
            position_pct /= 100.0;
        } else if !matches!(position_units.as_str(), "fraction" | "decimal" | "ratio")
            && position_pct > 1.0
        {
            position_pct /= 100.0;
        }

        Self {
            ok: false,
            error: String::new(),
            symbol: request.symbol.trim().to_ascii_uppercase(),
            interval: request.interval.trim().to_owned(),
            indicator_keys: Vec::new(),
            trades: 0,
            roi_value: 0.0,
            roi_percent: 0.0,
            final_equity: 0.0,
            max_drawdown_value: 0.0,
            max_drawdown_percent: 0.0,
            max_drawdown_during_value: 0.0,
            max_drawdown_during_percent: 0.0,
            max_drawdown_result_value: 0.0,
            max_drawdown_result_percent: 0.0,
            logic: logic.to_owned(),
            leverage: request.leverage.max(1.0),
            mdd_logic,
            side,
            capital: request.capital,
            position_pct: position_pct.clamp(0.0001, 1.0),
            position_pct_units: "fraction".to_owned(),
            stop_loss_enabled: request.stop_loss_enabled,
            stop_loss_mode,
            stop_loss_usdt: request.stop_loss_usdt.max(0.0),
            stop_loss_percent: request.stop_loss_percent.max(0.0),
            stop_loss_scope,
            margin_mode: request.margin_mode.trim().to_ascii_uppercase(),
            position_mode: request.position_mode.trim().to_owned(),
            assets_mode: request.assets_mode.trim().to_owned(),
            account_mode: request.account_mode.trim().to_owned(),
            fee_bps: request.fee_bps.max(0.0),
            slippage_bps: request.slippage_bps.max(0.0),
            fees_paid: 0.0,
        }
    }

    pub fn to_json(&self) -> Value {
        json!({
            "ok": self.ok,
            "error": self.error,
            "symbol": self.symbol,
            "interval": self.interval,
            "indicator_keys": self.indicator_keys,
            "trades": self.trades,
            "roi_value": self.roi_value,
            "roi_percent": self.roi_percent,
            "final_equity": self.final_equity,
            "max_drawdown_value": self.max_drawdown_value,
            "max_drawdown_percent": self.max_drawdown_percent,
            "max_drawdown_during_value": self.max_drawdown_during_value,
            "max_drawdown_during_percent": self.max_drawdown_during_percent,
            "max_drawdown_result_value": self.max_drawdown_result_value,
            "max_drawdown_result_percent": self.max_drawdown_result_percent,
            "logic": self.logic,
            "leverage": self.leverage,
            "mdd_logic": self.mdd_logic,
            "side": self.side,
            "capital": self.capital,
            "position_pct": self.position_pct,
            "position_pct_units": self.position_pct_units,
            "stop_loss_enabled": self.stop_loss_enabled,
            "stop_loss_mode": self.stop_loss_mode,
            "stop_loss_usdt": self.stop_loss_usdt,
            "stop_loss_percent": self.stop_loss_percent,
            "stop_loss_scope": self.stop_loss_scope,
            "margin_mode": self.margin_mode,
            "position_mode": self.position_mode,
            "assets_mode": self.assets_mode,
            "account_mode": self.account_mode,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "fees_paid": self.fees_paid,
            "source": "native-rust-backtest",
        })
    }
}

#[derive(Default)]
struct IndicatorSignals {
    key: String,
    buy: Option<Vec<bool>>,
    sell: Option<Vec<bool>>,
    gate: Option<Vec<bool>>,
}

#[derive(Default)]
struct DrawdownState {
    peak: f64,
    max_value: f64,
    max_pct: f64,
}

#[derive(Default)]
struct TradeState {
    active: bool,
    direction: String,
    entry_price: f64,
    peak_price: f64,
    trough_price: f64,
    max_value: f64,
    max_pct: f64,
    notional: f64,
    units: f64,
    entry_fee: f64,
}

fn config_bool(config: &Value, key: &str, fallback: bool) -> bool {
    let Some(value) = config.get(key) else {
        return fallback;
    };
    if let Some(value) = value.as_bool() {
        return value;
    }
    if let Some(value) = value.as_f64() {
        return value != 0.0;
    }
    match value
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "true" | "1" | "yes" | "on" => true,
        "false" | "0" | "no" | "off" => false,
        _ => fallback,
    }
}

fn config_number(config: &Value, key: &str) -> Option<f64> {
    let value = config.get(key)?;
    let parsed = value
        .as_f64()
        .or_else(|| value.as_str()?.trim().parse::<f64>().ok())?;
    parsed.is_finite().then_some(parsed)
}

fn config_length(config: &Value, key: &str, fallback: usize) -> usize {
    config_number(config, key)
        .map(|value| (value as isize).max(1) as usize)
        .unwrap_or(fallback.max(1))
}

fn config_text<'a>(config: &'a Value, key: &str, fallback: &'a str) -> &'a str {
    config
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .unwrap_or(fallback)
}

fn raw_series(series: &BTreeMap<String, Vec<f64>>, key: &str, size: usize) -> Vec<f64> {
    let mut output = series
        .get(key)
        .cloned()
        .unwrap_or_else(|| vec![f64::NAN; size]);
    output.resize(size, f64::NAN);
    output
}

fn relative_volume(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let length = length.max(1);
    let mut output = vec![f64::NAN; candles.len()];
    let mut rolling = 0.0;
    for (index, candle) in candles.iter().enumerate() {
        rolling += candle.volume;
        if index >= length {
            rolling -= candles[index - length].volume;
        }
        let count = length.min(index + 1) as f64;
        let mean = rolling / count;
        output[index] = if mean == 0.0 {
            f64::NAN
        } else {
            candle.volume / mean
        };
    }
    output
}

fn backtest_series(
    key: &str,
    config: &Value,
    candles: &[BinanceKlineCandle],
    computed: &BTreeMap<String, Vec<f64>>,
) -> Vec<f64> {
    let size = candles.len();
    let mode = config_text(config, "signal_mode", "").to_ascii_lowercase();
    let output_key = match key {
        "bb" => "bb_mid",
        "keltner" => "keltner_mid",
        "stoch_rsi" => "stoch_rsi_k",
        "ppo" => "ppo_hist",
        "kst" => "kst_hist",
        "stochastic" => "stochastic_k",
        _ => key,
    };

    if key == "macd" {
        let line = raw_series(computed, "macd_line", size);
        let signal = raw_series(computed, "macd_signal", size);
        return line
            .into_iter()
            .zip(signal)
            .map(|(line, signal)| {
                if line.is_finite() && signal.is_finite() {
                    line - signal
                } else {
                    f64::NAN
                }
            })
            .collect();
    }

    if key == "volume" && mode == "relative_to_sma" {
        return relative_volume(candles, config_length(config, "length", 20));
    }

    let baseline = raw_series(computed, output_key, size);
    if key == "obv" && mode == "slope" {
        let length = config_length(config, "length", 3);
        let mut output = vec![0.0; size];
        for index in length..size {
            if baseline[index].is_finite() && baseline[index - length].is_finite() {
                output[index] = baseline[index] - baseline[index - length];
            }
        }
        return output;
    }

    if mode == "price_cross" {
        return baseline
            .into_iter()
            .zip(candles)
            .map(|(baseline, candle)| {
                if baseline.is_finite() {
                    candle.close - baseline
                } else {
                    0.0
                }
            })
            .collect();
    }

    if mode == "band_position" {
        let keys = match key {
            "donchian" => Some(("donchian_low", "donchian_high")),
            "bb" => Some(("bb_lower", "bb_upper")),
            "keltner" => Some(("keltner_lower", "keltner_upper")),
            _ => None,
        };
        if let Some((lower_key, upper_key)) = keys {
            let lower = raw_series(computed, lower_key, size);
            let upper = raw_series(computed, upper_key, size);
            return (0..size)
                .map(|index| {
                    let range = upper[index] - lower[index];
                    if range.is_finite() && range != 0.0 && lower[index].is_finite() {
                        (candles[index].close - lower[index]) / range * 100.0
                    } else {
                        0.0
                    }
                })
                .collect();
        }
    }

    if mode == "percent_of_close" {
        return baseline
            .into_iter()
            .zip(candles)
            .map(|(baseline, candle)| {
                if candle.close != 0.0 && baseline.is_finite() {
                    baseline / candle.close * 100.0
                } else {
                    0.0
                }
            })
            .collect();
    }
    baseline
}

fn threshold_events(series: &[f64], threshold: f64, less_or_equal: bool) -> Vec<bool> {
    let mut previous = false;
    series
        .iter()
        .map(|value| {
            let current = value.is_finite()
                && if less_or_equal {
                    *value <= threshold
                } else {
                    *value >= threshold
                };
            let event = current && !previous;
            previous = current;
            event
        })
        .collect()
}

fn normalized_filter_operator(config: &Value) -> String {
    let operator = config_text(config, "filter_operator", "gte")
        .to_ascii_lowercase()
        .replace(['-', ' '], "_");
    match operator.as_str() {
        "greater_than_or_equal" | "above_or_equal" | "min" => "gte".to_owned(),
        "greater_than" | "above" => "gt".to_owned(),
        "less_than_or_equal" | "below_or_equal" | "max" => "lte".to_owned(),
        "less_than" | "below" => "lt".to_owned(),
        _ => operator,
    }
}

fn filter_threshold(config: &Value) -> Option<f64> {
    config_number(config, "filter_value")
        .or_else(|| config_number(config, "buy_value"))
        .or_else(|| config_number(config, "sell_value"))
}

fn filter_state(series: &[f64], config: &Value) -> Option<Vec<bool>> {
    let operator = normalized_filter_operator(config);
    if matches!(operator.as_str(), "between" | "outside") {
        let buy = config_number(config, "buy_value")?;
        let sell = config_number(config, "sell_value")?;
        let lower = buy.min(sell);
        let upper = buy.max(sell);
        return Some(
            series
                .iter()
                .map(|value| {
                    let between = value.is_finite() && *value >= lower && *value <= upper;
                    if operator == "outside" {
                        !between
                    } else {
                        between
                    }
                })
                .collect(),
        );
    }
    let threshold = filter_threshold(config)?;
    Some(
        series
            .iter()
            .map(|value| {
                if !value.is_finite() {
                    return false;
                }
                match operator.as_str() {
                    "gt" => *value > threshold,
                    "lte" => *value <= threshold,
                    "lt" => *value < threshold,
                    _ => *value >= threshold,
                }
            })
            .collect(),
    )
}

fn is_filter(config: &Value) -> bool {
    let role = config_text(config, "signal_role", config_text(config, "role", "signal"))
        .to_ascii_lowercase()
        .replace(['-', ' '], "_");
    matches!(
        role.as_str(),
        "filter" | "entry_filter" | "gate" | "confirmation"
    )
}

fn update_drawdown(state: &mut DrawdownState, equity: f64) {
    let current = if equity.is_finite() { equity } else { 0.0 };
    if current > state.peak {
        state.peak = current;
        return;
    }
    if state.peak <= 0.0 {
        return;
    }
    let value = state.peak - current;
    if value <= 0.0 {
        return;
    }
    state.max_value = state.max_value.max(value);
    state.max_pct = state.max_pct.max(value / state.peak * 100.0);
}

fn combine_signals(arrays: &[&Vec<bool>], size: usize, logic: &str) -> Vec<bool> {
    if arrays.is_empty() {
        return vec![false; size];
    }
    (0..size)
        .map(|index| {
            if logic == "AND" {
                arrays.iter().all(|array| array[index])
            } else {
                arrays.iter().any(|array| array[index])
            }
        })
        .collect()
}

fn update_trade(
    trade: &mut TradeState,
    trade_during: &mut DrawdownState,
    price: f64,
    high: f64,
    low: f64,
) {
    if !trade.active || trade.units <= 0.0 {
        return;
    }
    let drawdown_price = if trade.direction == "LONG" {
        trade.peak_price = trade.peak_price.max(high);
        (trade.peak_price - low.min(price)).max(0.0)
    } else {
        trade.trough_price = trade.trough_price.min(low);
        (high.max(price) - trade.trough_price).max(0.0)
    };
    let value = drawdown_price * trade.units;
    let pct = if trade.notional > 0.0 {
        value / trade.notional * 100.0
    } else {
        0.0
    };
    trade.max_value = trade.max_value.max(value);
    trade.max_pct = trade.max_pct.max(pct);
    trade_during.max_value = trade_during.max_value.max(value);
    trade_during.max_pct = trade_during.max_pct.max(pct);
}

fn finalize_trade(
    trade: &mut TradeState,
    trade_during: &mut DrawdownState,
    trade_result: &mut DrawdownState,
    per_trade: &mut DrawdownState,
    mdd_logic: &str,
    exit_price: Option<f64>,
    realized_pnl: Option<f64>,
) {
    if !trade.active {
        return;
    }
    trade_during.max_value = trade_during.max_value.max(trade.max_value);
    trade_during.max_pct = trade_during.max_pct.max(trade.max_pct);
    if mdd_logic == "per_trade" && trade.max_value > per_trade.max_value {
        per_trade.max_value = trade.max_value;
        per_trade.max_pct = trade.max_pct;
    }
    let mut loss_value = 0.0;
    let mut loss_pct = 0.0;
    if trade.units > 0.0 && trade.entry_price > 0.0 {
        let exit = exit_price.unwrap_or(trade.entry_price);
        let pnl = if let Some(realized_pnl) = realized_pnl {
            realized_pnl - trade.entry_fee
        } else if trade.direction == "LONG" {
            (exit - trade.entry_price) * trade.units
        } else {
            (trade.entry_price - exit) * trade.units
        };
        if pnl < 0.0 {
            loss_value = pnl.abs();
            if trade.notional > 0.0 {
                loss_pct = loss_value / trade.notional * 100.0;
            }
        }
    }
    trade_result.max_value = trade_result.max_value.max(loss_value);
    trade_result.max_pct = trade_result.max_pct.max(loss_pct);
    *trade = TradeState::default();
}

fn execution_price(market_price: f64, direction: &str, slippage_rate: f64, entry: bool) -> f64 {
    let adverse = (direction == "LONG") == entry;
    market_price
        * if adverse {
            1.0 + slippage_rate
        } else {
            1.0 - slippage_rate
        }
}

fn realize_close(
    market_price: f64,
    direction: &str,
    entry_price: f64,
    units: f64,
    fee_rate: f64,
    slippage_rate: f64,
    fees_paid: &mut f64,
) -> (f64, f64) {
    let exit_price = execution_price(market_price, direction, slippage_rate, false);
    let gross_pnl = if direction == "LONG" {
        (exit_price - entry_price) * units
    } else {
        (entry_price - exit_price) * units
    };
    let exit_fee = (exit_price * units).abs() * fee_rate;
    *fees_paid += exit_fee;
    (exit_price, gross_pnl - exit_fee)
}

pub fn run_native_backtest(
    candles: &[BinanceKlineCandle],
    request: &NativeBacktestRequest,
) -> NativeBacktestResult {
    run_native_backtest_with_cancel(candles, request, || false)
}

pub fn run_native_backtest_with_cancel<F>(
    candles: &[BinanceKlineCandle],
    request: &NativeBacktestRequest,
    should_stop: F,
) -> NativeBacktestResult
where
    F: FnMut() -> bool,
{
    run_native_backtest_with_cancel_and_window(candles, request, None, None, should_stop)
}

pub fn run_native_backtest_with_cancel_and_window<F>(
    candles: &[BinanceKlineCandle],
    request: &NativeBacktestRequest,
    start_time_ms: Option<i64>,
    end_time_ms: Option<i64>,
    mut should_stop: F,
) -> NativeBacktestResult
where
    F: FnMut() -> bool,
{
    let mut result = NativeBacktestResult::from_request(request);
    if let (Some(start), Some(end)) = (start_time_ms, end_time_ms)
        && start >= end
    {
        result.error = "Backtest start must be earlier than backtest end".to_owned();
        return result;
    }
    if candles.is_empty() {
        result.error = "Backtest requires at least one candle".to_owned();
        return result;
    }
    if result.capital <= 0.0 || !result.capital.is_finite() {
        result.error = "Backtest capital must be positive".to_owned();
        return result;
    }
    let unsupported = unsupported_enabled_indicator_keys(&request.indicators);
    if !unsupported.is_empty() {
        result.error = format!(
            "Unsupported native backtest indicators: {}",
            unsupported.join(", ")
        );
        return result;
    }

    let computed = compute_configured_indicator_series(candles, &request.indicators);
    let mut indicator_signals = Vec::new();
    for (key, config) in &request.indicators {
        if !config_bool(config, "enabled", false) {
            continue;
        }
        let mut signals = IndicatorSignals {
            key: key.clone(),
            ..IndicatorSignals::default()
        };
        let series = backtest_series(key, config, candles, &computed);
        if is_filter(config) {
            signals.gate = filter_state(&series, config);
            if signals.gate.is_none() {
                result.error = format!("Backtest filter '{key}' is missing a valid threshold rule");
                return result;
            }
        } else {
            let buy = config_number(config, "buy_value");
            let sell = config_number(config, "sell_value");
            if buy.is_none() && sell.is_none() {
                result.error = format!("Backtest indicator '{key}' is missing buy/sell values");
                return result;
            }
            if let Some(buy) = buy {
                signals.buy = Some(threshold_events(
                    &series,
                    buy,
                    sell.is_some_and(|sell| buy < sell),
                ));
            }
            if let Some(sell) = sell {
                signals.sell = Some(threshold_events(
                    &series,
                    sell,
                    !buy.is_some_and(|buy| buy < sell),
                ));
            }
        }
        result.indicator_keys.push(signals.key.clone());
        indicator_signals.push(signals);
    }

    let buy_arrays: Vec<&Vec<bool>> = indicator_signals
        .iter()
        .filter_map(|signals| signals.buy.as_ref())
        .collect();
    let sell_arrays: Vec<&Vec<bool>> = indicator_signals
        .iter()
        .filter_map(|signals| signals.sell.as_ref())
        .collect();
    let filter_arrays: Vec<&Vec<bool>> = indicator_signals
        .iter()
        .filter_map(|signals| signals.gate.as_ref())
        .collect();
    if buy_arrays.is_empty() && sell_arrays.is_empty() {
        result.error =
            "At least one signal indicator is required; filter-only indicators cannot open trades."
                .to_owned();
        return result;
    }

    let size = candles.len();
    let raw_buy = combine_signals(&buy_arrays, size, &result.logic);
    let raw_sell = combine_signals(&sell_arrays, size, "OR");
    let entry_filter: Vec<bool> = (0..size)
        .map(|index| filter_arrays.iter().all(|array| array[index]))
        .collect();

    let can_long = matches!(result.side.as_str(), "BUY" | "BOTH");
    let can_short = matches!(result.side.as_str(), "SELL" | "BOTH");
    let fee_rate = result.fee_bps / 10_000.0;
    let slippage_rate = result.slippage_bps / 10_000.0;
    let mut equity = result.capital;
    let mut position_open = false;
    let mut entry_price = 0.0;
    let mut units = 0.0;
    let mut position_margin = 0.0;
    let mut fees_paid = 0.0;
    let mut direction = String::new();
    let mut cumulative = DrawdownState {
        peak: equity,
        ..DrawdownState::default()
    };
    let mut account = DrawdownState {
        peak: equity,
        ..DrawdownState::default()
    };
    let mut per_trade = DrawdownState::default();
    let mut trade_during = DrawdownState::default();
    let mut trade_result = DrawdownState::default();
    let mut trade = TradeState::default();
    let mut last_processed_close = None;

    let record_equity =
        |value: f64, cumulative: &mut DrawdownState, account: &mut DrawdownState| {
            update_drawdown(cumulative, value);
            if result.mdd_logic == "entire_account" {
                update_drawdown(account, value);
            }
        };
    record_equity(equity, &mut cumulative, &mut account);

    for (index, candle) in candles.iter().enumerate() {
        if should_stop() {
            result.error = "backtest_cancelled".to_owned();
            return result;
        }
        if start_time_ms.is_some_and(|start| candle.open_time_ms < start) {
            continue;
        }
        if end_time_ms.is_some_and(|end| candle.open_time_ms > end) {
            break;
        }
        let price = if candle.close.is_finite() {
            candle.close
        } else {
            0.0
        };
        if price <= 0.0 {
            continue;
        }
        last_processed_close = Some(price);
        let high = if candle.high.is_finite() && candle.high > 0.0 {
            candle.high
        } else {
            price
        };
        let low = if candle.low.is_finite() && candle.low > 0.0 {
            candle.low
        } else {
            price
        };
        let mut entry_buy = raw_buy[index] && entry_filter[index];
        let mut entry_sell = raw_sell[index] && entry_filter[index];
        if !position_open && result.mdd_logic == "entire_account" {
            update_drawdown(&mut account, equity);
        }

        if position_open {
            update_trade(&mut trade, &mut trade_during, price, high, low);
            if result.mdd_logic == "entire_account" {
                if units > 0.0 {
                    let best = if direction == "LONG" {
                        equity + (high.max(price) - entry_price) * units
                    } else {
                        equity + (entry_price - low.min(price)) * units
                    };
                    let worst = if direction == "LONG" {
                        equity + (low.min(price) - entry_price) * units
                    } else {
                        equity + (entry_price - high.max(price)) * units
                    };
                    update_drawdown(&mut account, best);
                    update_drawdown(&mut account, worst);
                } else {
                    update_drawdown(&mut account, equity);
                }
            }

            let effective_leverage = if result.margin_mode == "CROSS" {
                result.leverage.max(1.0) * result.position_pct
            } else {
                result.leverage
            };
            if direction == "LONG" && effective_leverage > 1.0 {
                let liquidation = (entry_price * (1.0 - 1.0 / effective_leverage)).max(0.0);
                if low <= liquidation {
                    let loss = equity.min(position_margin);
                    equity = (equity - loss).max(0.0);
                    record_equity(equity, &mut cumulative, &mut account);
                    finalize_trade(
                        &mut trade,
                        &mut trade_during,
                        &mut trade_result,
                        &mut per_trade,
                        &result.mdd_logic,
                        Some(liquidation),
                        Some(-loss),
                    );
                    position_open = false;
                    units = 0.0;
                    position_margin = 0.0;
                    direction.clear();
                    continue;
                }
            }
            if direction == "SHORT" && effective_leverage > 1.0 {
                let liquidation = entry_price * (1.0 + 1.0 / effective_leverage);
                if high >= liquidation {
                    let loss = equity.min(position_margin);
                    equity = (equity - loss).max(0.0);
                    record_equity(equity, &mut cumulative, &mut account);
                    finalize_trade(
                        &mut trade,
                        &mut trade_during,
                        &mut trade_result,
                        &mut per_trade,
                        &result.mdd_logic,
                        Some(liquidation),
                        Some(-loss),
                    );
                    position_open = false;
                    units = 0.0;
                    position_margin = 0.0;
                    direction.clear();
                    continue;
                }
            }

            if result.stop_loss_enabled && units > 0.0 && entry_price > 0.0 {
                let worst = if direction == "LONG" {
                    price.min(low)
                } else {
                    price.max(high)
                };
                let worst_exit = execution_price(worst, &direction, slippage_rate, false);
                let loss = if direction == "LONG" {
                    ((entry_price - worst_exit) * units).max(0.0)
                } else {
                    ((worst_exit - entry_price) * units).max(0.0)
                };
                let denominator = if result.stop_loss_scope == "per_trade" && position_margin > 0.0
                {
                    position_margin
                } else {
                    entry_price * units
                };
                let loss_pct = if denominator > 0.0 {
                    loss / denominator * 100.0
                } else {
                    0.0
                };
                let mut triggered = matches!(result.stop_loss_mode.as_str(), "usdt" | "both")
                    && result.stop_loss_usdt > 0.0
                    && loss >= result.stop_loss_usdt;
                if !triggered
                    && matches!(result.stop_loss_mode.as_str(), "percent" | "both")
                    && result.stop_loss_percent > 0.0
                    && loss_pct >= result.stop_loss_percent
                {
                    triggered = true;
                }
                if triggered {
                    let (exit_price, pnl) = realize_close(
                        worst,
                        &direction,
                        entry_price,
                        units,
                        fee_rate,
                        slippage_rate,
                        &mut fees_paid,
                    );
                    equity = (equity + pnl).max(0.0);
                    record_equity(equity, &mut cumulative, &mut account);
                    finalize_trade(
                        &mut trade,
                        &mut trade_during,
                        &mut trade_result,
                        &mut per_trade,
                        &result.mdd_logic,
                        Some(exit_price),
                        Some(pnl),
                    );
                    position_open = false;
                    units = 0.0;
                    position_margin = 0.0;
                    direction.clear();
                    result.trades += 1;
                    continue;
                }
            }

            if direction == "LONG" && raw_sell[index] {
                let (exit_price, pnl) = realize_close(
                    price,
                    &direction,
                    entry_price,
                    units,
                    fee_rate,
                    slippage_rate,
                    &mut fees_paid,
                );
                equity = (equity + pnl).max(0.0);
                record_equity(equity, &mut cumulative, &mut account);
                finalize_trade(
                    &mut trade,
                    &mut trade_during,
                    &mut trade_result,
                    &mut per_trade,
                    &result.mdd_logic,
                    Some(exit_price),
                    Some(pnl),
                );
                position_open = false;
                units = 0.0;
                position_margin = 0.0;
                direction.clear();
                entry_sell = can_short && entry_sell && equity > 0.0;
            } else if direction == "SHORT" && raw_buy[index] {
                let (exit_price, pnl) = realize_close(
                    price,
                    &direction,
                    entry_price,
                    units,
                    fee_rate,
                    slippage_rate,
                    &mut fees_paid,
                );
                equity = (equity + pnl).max(0.0);
                record_equity(equity, &mut cumulative, &mut account);
                finalize_trade(
                    &mut trade,
                    &mut trade_during,
                    &mut trade_result,
                    &mut per_trade,
                    &result.mdd_logic,
                    Some(exit_price),
                    Some(pnl),
                );
                position_open = false;
                units = 0.0;
                position_margin = 0.0;
                direction.clear();
                entry_buy = can_long && entry_buy && equity > 0.0;
            }
        }

        if !position_open && equity > 0.0 {
            let opening_direction = if entry_buy && can_long {
                Some("LONG")
            } else if entry_sell && can_short {
                Some("SHORT")
            } else {
                None
            };
            if let Some(opening_direction) = opening_direction {
                entry_price = execution_price(price, opening_direction, slippage_rate, true);
                position_margin = equity * result.position_pct;
                units = position_margin * result.leverage / entry_price;
                if units > 0.0 {
                    let entry_fee = (entry_price * units).abs() * fee_rate;
                    fees_paid += entry_fee;
                    equity = (equity - entry_fee).max(0.0);
                    position_open = true;
                    direction = opening_direction.to_owned();
                    trade = TradeState {
                        active: true,
                        direction: direction.clone(),
                        entry_price,
                        peak_price: entry_price,
                        trough_price: entry_price,
                        notional: (entry_price * units.abs()).abs(),
                        units: units.abs(),
                        entry_fee: entry_fee.max(0.0),
                        ..TradeState::default()
                    };
                    result.trades += 1;
                } else {
                    position_margin = 0.0;
                }
            }
        }
    }

    if position_open && units > 0.0 {
        let last = last_processed_close.unwrap_or_else(|| {
            candles
                .last()
                .map(|candle| candle.close)
                .unwrap_or_default()
        });
        let (exit_price, pnl) = realize_close(
            last,
            &direction,
            entry_price,
            units,
            fee_rate,
            slippage_rate,
            &mut fees_paid,
        );
        equity = (equity + pnl).max(0.0);
        record_equity(equity, &mut cumulative, &mut account);
        finalize_trade(
            &mut trade,
            &mut trade_during,
            &mut trade_result,
            &mut per_trade,
            &result.mdd_logic,
            Some(exit_price),
            Some(pnl),
        );
    }

    result.final_equity = equity;
    result.roi_value = equity - result.capital;
    result.roi_percent = if result.capital != 0.0 {
        result.roi_value / result.capital * 100.0
    } else {
        0.0
    };
    result.fees_paid = fees_paid;
    result.max_drawdown_during_value = trade_during.max_value;
    result.max_drawdown_during_percent = trade_during.max_pct;
    result.max_drawdown_result_value = trade_result.max_value;
    result.max_drawdown_result_percent = trade_result.max_pct;
    let selected_drawdown = match result.mdd_logic.as_str() {
        "entire_account" => &account,
        "cumulative" => &cumulative,
        _ => &per_trade,
    };
    result.max_drawdown_value = selected_drawdown.max_value;
    result.max_drawdown_percent = selected_drawdown.max_pct;
    result.ok = true;
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::generated_python_indicator_reference::PYTHON_INDICATOR_REFERENCE_JSON;

    fn text(value: Option<&Value>, fallback: &str) -> String {
        value.and_then(Value::as_str).unwrap_or(fallback).to_owned()
    }

    fn number(value: Option<&Value>, fallback: f64) -> f64 {
        value.and_then(Value::as_f64).unwrap_or(fallback)
    }

    fn candles_from_value(value: &Value) -> Vec<BinanceKlineCandle> {
        value
            .as_array()
            .expect("reference candles must be an array")
            .iter()
            .enumerate()
            .map(|(index, candle)| BinanceKlineCandle {
                open_time_ms: index as i64 * 60_000,
                open: number(candle.get("open"), 0.0),
                high: number(candle.get("high"), 0.0),
                low: number(candle.get("low"), 0.0),
                close: number(candle.get("close"), 0.0),
                volume: number(candle.get("volume"), 0.0),
            })
            .collect()
    }

    #[test]
    fn native_backtest_matches_every_generated_python_reference_case() {
        let reference: Value = serde_json::from_str(PYTHON_INDICATOR_REFERENCE_JSON)
            .expect("generated Python indicator reference must be valid JSON");
        let candles = candles_from_value(&reference["candles"]);
        let cases = reference["backtest_cases"]
            .as_array()
            .expect("generated Python fixture must include backtest cases");
        assert!(cases.len() >= 27);

        for test_case in cases {
            let expected = &test_case["expected"];
            let stop_loss = &test_case["stop_loss"];
            let indicators = test_case["configs"]
                .as_object()
                .expect("backtest configs must be an object")
                .iter()
                .map(|(key, config)| (key.clone(), config.clone()))
                .collect();
            let request = NativeBacktestRequest {
                indicators,
                logic: text(test_case.get("logic"), "AND"),
                side: text(test_case.get("side"), "BOTH"),
                capital: number(test_case.get("capital"), 1_000.0),
                position_pct: number(test_case.get("position_pct"), 1.0),
                position_pct_units: text(test_case.get("position_pct_units"), ""),
                leverage: number(test_case.get("leverage"), 1.0),
                margin_mode: text(test_case.get("margin_mode"), "Isolated"),
                mdd_logic: text(test_case.get("mdd_logic"), "per_trade"),
                stop_loss_enabled: stop_loss["enabled"].as_bool().unwrap_or(false),
                stop_loss_mode: text(stop_loss.get("mode"), "usdt"),
                stop_loss_usdt: number(stop_loss.get("usdt"), 0.0),
                stop_loss_percent: number(stop_loss.get("percent"), 0.0),
                stop_loss_scope: text(stop_loss.get("scope"), "per_trade"),
                fee_bps: number(expected.get("fee_bps"), 5.0),
                slippage_bps: number(expected.get("slippage_bps"), 2.0),
                ..NativeBacktestRequest::default()
            };
            let case_candles = test_case
                .get("candles")
                .filter(|value| value.is_array())
                .map(candles_from_value)
                .unwrap_or_else(|| candles.clone());
            let actual = run_native_backtest(&case_candles, &request);
            let case_name = format!(
                "{}/{}",
                text(test_case.get("fixture_name"), "baseline"),
                text(test_case.get("name"), "unnamed")
            );
            assert!(actual.ok, "{case_name}: {}", actual.error);
            assert_eq!(
                actual.trades,
                expected["trades"].as_u64().unwrap_or_default() as usize,
                "trade count mismatch for {case_name}"
            );
            let actual_json = actual.to_json();
            for key in [
                "roi_value",
                "roi_percent",
                "final_equity",
                "max_drawdown_value",
                "max_drawdown_percent",
                "max_drawdown_during_value",
                "max_drawdown_during_percent",
                "max_drawdown_result_value",
                "max_drawdown_result_percent",
                "capital",
                "position_pct",
                "leverage",
                "stop_loss_usdt",
                "stop_loss_percent",
                "fee_bps",
                "slippage_bps",
                "fees_paid",
            ] {
                let expected_number = expected[key]
                    .as_f64()
                    .unwrap_or_else(|| panic!("missing expected number {key} for {case_name}"));
                let actual_number = actual_json[key]
                    .as_f64()
                    .unwrap_or_else(|| panic!("missing actual number {key} for {case_name}"));
                let tolerance = 1e-9 * expected_number.abs().max(1.0);
                assert!(
                    actual_number.is_finite()
                        && (actual_number - expected_number).abs() <= tolerance,
                    "{key} mismatch for {case_name}: expected {expected_number:.16}, got {actual_number:.16}"
                );
            }
            for key in [
                "logic",
                "mdd_logic",
                "side",
                "position_pct_units",
                "stop_loss_mode",
                "stop_loss_scope",
                "margin_mode",
                "position_mode",
                "assets_mode",
                "account_mode",
            ] {
                assert_eq!(
                    actual_json[key], expected[key],
                    "{key} mismatch for {case_name}"
                );
            }
            assert_eq!(actual.stop_loss_enabled, expected["stop_loss_enabled"]);
            let expected_indicator_keys = expected["indicator_keys"]
                .as_array()
                .expect("expected indicator keys must be an array")
                .iter()
                .map(|value| text(Some(value), ""))
                .collect::<Vec<_>>();
            assert_eq!(actual.indicator_keys, expected_indicator_keys);
        }
    }

    #[test]
    fn native_backtest_rejects_filter_only_and_honors_cancellation() {
        let candles = vec![BinanceKlineCandle {
            open_time_ms: 0,
            open: 100.0,
            high: 101.0,
            low: 99.0,
            close: 100.0,
            volume: 10.0,
        }];
        let filter_only = NativeBacktestRequest {
            indicators: BTreeMap::from([(
                "rvol".to_owned(),
                json!({
                    "enabled": true,
                    "length": 1,
                    "signal_role": "filter",
                    "filter_operator": "gte",
                    "filter_value": 0.5,
                }),
            )]),
            ..NativeBacktestRequest::default()
        };
        let invalid = run_native_backtest(&candles, &filter_only);
        assert!(!invalid.ok);
        assert!(invalid.error.contains("filter-only"));

        let executable = NativeBacktestRequest {
            indicators: BTreeMap::from([(
                "rsi".to_owned(),
                json!({"enabled": true, "length": 1, "buy_value": 45.0}),
            )]),
            ..NativeBacktestRequest::default()
        };
        let cancelled = run_native_backtest_with_cancel(&candles, &executable, || true);
        assert!(!cancelled.ok);
        assert_eq!(cancelled.error, "backtest_cancelled");
    }
}
