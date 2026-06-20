use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::exchange_connectors::normalize_connector_backend;

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct IndicatorRule {
    pub enabled: bool,
    pub buy_value: Option<f64>,
    pub sell_value: Option<f64>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct StrategySignalInput {
    pub closes: Vec<f64>,
    pub indicators: BTreeMap<String, Vec<f64>>,
    pub rules: BTreeMap<String, IndicatorRule>,
    pub side: String,
    pub use_live_values: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StrategySignalDecision {
    pub signal: Option<String>,
    pub description: String,
    pub trigger_price: Option<f64>,
    pub trigger_sources: Vec<String>,
    pub trigger_actions: BTreeMap<String, String>,
    pub min_bars: usize,
    pub signal_index_from_end: usize,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct StrategyWorkerLifecycleInput {
    pub symbol: String,
    pub interval: String,
    pub loop_interval_override: Option<String>,
    pub thread_alive: bool,
    pub stop_requested: bool,
    pub global_shutdown: bool,
    pub global_pause: bool,
    pub active_engine_count: usize,
    pub offline_backoff: f64,
    pub emergency_close_triggered: bool,
}

pub const PYTHON_STRATEGY_RUNTIME_BOUNDARIES: &[&str] = &[
    "indicator output key expansion",
    "live-vs-closed candle signal indexing",
    "side-gated threshold actions",
    "context-only indicator descriptions",
    "runtime/backtest strategy control normalization",
    "override provenance preservation",
    "worker lifecycle and Python-service execution boundary",
];

pub fn coerce_strategy_bool(value: Option<&Value>, default: bool) -> bool {
    match value {
        None | Some(Value::Null) => default,
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number.as_f64().unwrap_or(0.0) != 0.0,
        Some(Value::String(text)) => {
            let lowered = text.trim().to_lowercase();
            match lowered.as_str() {
                "" => default,
                "0" | "false" | "no" | "off" | "n" => false,
                "1" | "true" | "yes" | "on" | "y" => true,
                _ => default,
            }
        }
        Some(_) => default,
    }
}

pub fn indicator_output_keys_from_config(indicators: &Value) -> Vec<String> {
    let mut keys = Vec::new();
    let Some(object) = indicators.as_object() else {
        return keys;
    };
    let mut add = |items: &[&str]| {
        for item in items {
            if !keys.iter().any(|existing| existing == item) {
                keys.push((*item).to_owned());
            }
        }
    };
    for (key, config) in object {
        if !coerce_strategy_bool(config.get("enabled"), false) {
            continue;
        }
        match key.as_str() {
            "ma" => add(&["ma"]),
            "ema" => add(&["ema"]),
            "bb" => add(&["bb_upper", "bb_mid", "bb_lower"]),
            "bbw" => add(&["bbw"]),
            "keltner" => add(&["keltner_upper", "keltner_mid", "keltner_lower"]),
            "ichimoku" => add(&[
                "ichimoku_tenkan",
                "ichimoku_kijun",
                "ichimoku_span_a",
                "ichimoku_span_b",
                "ichimoku_chikou",
                "ichimoku",
            ]),
            "rsi" => add(&["rsi"]),
            "stoch_rsi" => add(&["stoch_rsi", "stoch_rsi_k", "stoch_rsi_d"]),
            "willr" => add(&["willr"]),
            "atr" => add(&["atr"]),
            "natr" => add(&["natr"]),
            "vwap" => add(&["vwap"]),
            "mfi" => add(&["mfi"]),
            "obv" => add(&["obv"]),
            "rvol" => add(&["rvol"]),
            "cmf" => add(&["cmf"]),
            "cci" => add(&["cci"]),
            "roc" => add(&["roc"]),
            "trix" => add(&["trix"]),
            "ppo" => add(&["ppo", "ppo_signal", "ppo_hist"]),
            "ao" => add(&["ao"]),
            "kst" => add(&["kst", "kst_signal", "kst_hist"]),
            "aroon" => add(&["aroon_up", "aroon_down", "aroon"]),
            "chop" => add(&["chop"]),
            "macd" => add(&["macd_line", "macd_signal"]),
            "uo" => add(&["uo"]),
            "adx" => add(&["adx"]),
            "dmi" => add(&["dmi_plus", "dmi_minus", "dmi"]),
            "supertrend" => add(&["supertrend"]),
            "stochastic" => add(&["stochastic", "stochastic_k", "stochastic_d"]),
            _ => {}
        }
    }
    keys
}

pub fn build_signal_decision(input: StrategySignalInput) -> StrategySignalDecision {
    let min_bars = if input.use_live_values { 2 } else { 3 };
    let signal_index_from_end = if input.use_live_values { 1 } else { 2 };
    if input.closes.len() < min_bars {
        return StrategySignalDecision {
            signal: None,
            description: "no data".to_owned(),
            trigger_price: None,
            trigger_sources: Vec::new(),
            trigger_actions: BTreeMap::new(),
            min_bars,
            signal_index_from_end,
        };
    }

    let signal_index = input.closes.len() - signal_index_from_end;
    let prev_index = signal_index.saturating_sub(1);
    let sig_close = input.closes[signal_index];
    let prev_close = input.closes[prev_index];
    if !sig_close.is_finite() || !prev_close.is_finite() {
        return StrategySignalDecision {
            signal: None,
            description: "no data".to_owned(),
            trigger_price: None,
            trigger_sources: Vec::new(),
            trigger_actions: BTreeMap::new(),
            min_bars,
            signal_index_from_end,
        };
    }

    let side = input.side.trim().to_uppercase();
    let buy_allowed = side == "BUY" || side == "BOTH";
    let sell_allowed = side == "SELL" || side == "BOTH";
    let mut signal: Option<String> = None;
    let mut descriptions = Vec::new();
    let mut sources = Vec::new();
    let mut actions = BTreeMap::new();

    let action = |source: &str,
                  side: &str,
                  desc: String,
                  signal: &mut Option<String>,
                  descriptions: &mut Vec<String>,
                  sources: &mut Vec<String>,
                  actions: &mut BTreeMap<String, String>| {
        actions.insert(source.to_owned(), side.to_lowercase());
        descriptions.push(desc);
        sources.push(source.to_owned());
        if signal.is_none() {
            *signal = Some(side.to_owned());
        }
    };

    if let Some((_, _, value)) = indicator_values(&input, "rsi") {
        if enabled(&input, "rsi") {
            if value.is_finite() {
                descriptions.push(format!("RSI={value:.2}"));
                let rule = rule(&input, "rsi");
                let buy = rule.buy_value.unwrap_or(30.0);
                let sell = rule.sell_value.unwrap_or(70.0);
                if buy_allowed && value <= buy {
                    action(
                        "rsi",
                        "BUY",
                        format!("RSI <= {buy:.2} -> BUY"),
                        &mut signal,
                        &mut descriptions,
                        &mut sources,
                        &mut actions,
                    );
                } else if sell_allowed && value >= sell {
                    action(
                        "rsi",
                        "SELL",
                        format!("RSI >= {sell:.2} -> SELL"),
                        &mut signal,
                        &mut descriptions,
                        &mut sources,
                        &mut actions,
                    );
                }
            } else {
                descriptions.push("RSI=NaN/inf skipped".to_owned());
            }
        }
    }

    if let Some((prev, live, value)) = indicator_values(&input, "stoch_rsi_k") {
        if enabled(&input, "stoch_rsi") {
            descriptions.push(format!(
                "StochRSI %K={value:.2} (prev={prev:.2}, live={live:.2})"
            ));
            let rule = rule(&input, "stoch_rsi");
            let buy = rule.buy_value.unwrap_or(20.0);
            let sell = rule.sell_value.unwrap_or(80.0);
            if buy_allowed && value <= buy {
                action(
                    "stoch_rsi",
                    "BUY",
                    format!("StochRSI %K <= {buy:.2} -> BUY"),
                    &mut signal,
                    &mut descriptions,
                    &mut sources,
                    &mut actions,
                );
            } else if sell_allowed && value >= sell {
                action(
                    "stoch_rsi",
                    "SELL",
                    format!("StochRSI %K >= {sell:.2} -> SELL"),
                    &mut signal,
                    &mut descriptions,
                    &mut sources,
                    &mut actions,
                );
            }
        }
    }

    if let Some((prev, live, value)) = indicator_values(&input, "willr") {
        if enabled(&input, "willr") {
            descriptions.push(format!(
                "Williams %R(prev={prev:.2}, live={live:.2}) -> using {value:.2}"
            ));
            let rule = rule(&input, "willr");
            let buy_upper = rule.buy_value.unwrap_or(-80.0).clamp(-100.0, 0.0);
            let sell_lower = rule.sell_value.unwrap_or(-20.0).clamp(-100.0, 0.0);
            if buy_allowed && (-100.0..=buy_upper).contains(&value) {
                action(
                    "willr",
                    "BUY",
                    format!("Williams %R in [-100.00, {buy_upper:.2}] -> BUY"),
                    &mut signal,
                    &mut descriptions,
                    &mut sources,
                    &mut actions,
                );
            } else if sell_allowed && (sell_lower..=0.0).contains(&value) {
                action(
                    "willr",
                    "SELL",
                    format!("Williams %R in [{sell_lower:.2}, 0.00] -> SELL"),
                    &mut signal,
                    &mut descriptions,
                    &mut sources,
                    &mut actions,
                );
            }
        }
    }

    context_only(&input, "atr", "ATR", "{:.8}", &mut descriptions);
    threshold_action(
        &input,
        "natr",
        "NATR",
        "{:.4}",
        Compare::BuyGeSellLe,
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );

    if let Some((prev, live, value)) = indicator_values(&input, "vwap") {
        if enabled(&input, "vwap") && value.is_finite() {
            let side_label = if sig_close >= value { "above" } else { "below" };
            descriptions.push(format!(
                "VWAP={value:.8} (prev={prev:.8}, live={live:.8}, close {side_label})"
            ));
        } else if enabled(&input, "vwap") {
            descriptions.push("VWAP=NaN/inf skipped".to_owned());
        }
    }

    threshold_action(
        &input,
        "mfi",
        "MFI",
        "{:.2}",
        Compare::BuyLeSellGeDefaults(20.0, 80.0),
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );

    if let Some((prev, live, value)) = indicator_values(&input, "obv") {
        if enabled(&input, "obv") && value.is_finite() {
            let trend = if live > prev {
                "rising"
            } else if live < prev {
                "falling"
            } else {
                "flat"
            };
            descriptions.push(format!(
                "OBV={value:.2} (prev={prev:.2}, live={live:.2}, {trend})"
            ));
            threshold_action_existing_value(
                &input,
                "obv",
                "OBV",
                "{:.2}",
                value,
                Compare::BuyGeSellLe,
                buy_allowed,
                sell_allowed,
                &mut signal,
                &mut descriptions,
                &mut sources,
                &mut actions,
            );
        } else if enabled(&input, "obv") {
            descriptions.push("OBV=NaN/inf skipped".to_owned());
        }
    }

    threshold_action(
        &input,
        "rvol",
        "RVOL",
        "{:.4}",
        Compare::BuyGeSellLe,
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );

    if let Some((prev, live, value)) = indicator_values(&input, "cmf") {
        if enabled(&input, "cmf") && value.is_finite() {
            let flow = if value > 0.0 {
                "accumulation"
            } else if value < 0.0 {
                "distribution"
            } else {
                "neutral"
            };
            descriptions.push(format!(
                "CMF={value:.4} (prev={prev:.4}, live={live:.4}, {flow})"
            ));
            threshold_action_existing_value(
                &input,
                "cmf",
                "CMF",
                "{:.4}",
                value,
                Compare::BuyGeSellLe,
                buy_allowed,
                sell_allowed,
                &mut signal,
                &mut descriptions,
                &mut sources,
                &mut actions,
            );
        } else if enabled(&input, "cmf") {
            descriptions.push("CMF=NaN/inf skipped".to_owned());
        }
    }

    threshold_action(
        &input,
        "cci",
        "CCI",
        "{:.2}",
        Compare::BuyLeSellGeDefaults(-100.0, 100.0),
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );
    threshold_action(
        &input,
        "roc",
        "ROC",
        "{:.2}",
        Compare::BuyGeSellLeDefaults(0.0, 0.0),
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );
    threshold_action(
        &input,
        "trix",
        "TRIX",
        "{:.4}",
        Compare::BuyGeSellLeDefaults(0.0, 0.0),
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );
    threshold_action(
        &input,
        "bbw",
        "BBW",
        "{:.4}",
        Compare::BuyGeSellLe,
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );

    histogram_action(
        &input,
        "ppo",
        "PPO",
        "ppo",
        "ppo_signal",
        "ppo_hist",
        "PPO hist",
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );
    threshold_action(
        &input,
        "ao",
        "AO",
        "{:.4}",
        Compare::BuyGeSellLeDefaults(0.0, 0.0),
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );
    histogram_action(
        &input,
        "kst",
        "KST",
        "kst",
        "kst_signal",
        "kst_hist",
        "KST spread",
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );

    if let Some((_, _, value)) = indicator_values(&input, "aroon") {
        if enabled(&input, "aroon") && value.is_finite() {
            let up = indicator_values(&input, "aroon_up")
                .map(|(_, _, v)| v)
                .unwrap_or(f64::NAN);
            let down = indicator_values(&input, "aroon_down")
                .map(|(_, _, v)| v)
                .unwrap_or(f64::NAN);
            descriptions.push(format!("Aroon={value:.2} (up={up:.2}, down={down:.2})"));
            threshold_action_existing_value(
                &input,
                "aroon",
                "Aroon",
                "{:.2}",
                value,
                Compare::BuyGeSellLeDefaults(50.0, -50.0),
                buy_allowed,
                sell_allowed,
                &mut signal,
                &mut descriptions,
                &mut sources,
                &mut actions,
            );
        } else if enabled(&input, "aroon") {
            descriptions.push("Aroon=NaN/inf skipped".to_owned());
        }
    }

    threshold_action(
        &input,
        "chop",
        "CHOP",
        "{:.4}",
        Compare::BuyLeSellGe,
        buy_allowed,
        sell_allowed,
        &mut signal,
        &mut descriptions,
        &mut sources,
        &mut actions,
    );

    if enabled(&input, "ma") {
        if let Some(ma) = input.indicators.get("ma") {
            let clean: Vec<f64> = ma.iter().copied().filter(|value| !value.is_nan()).collect();
            if clean.len() >= 2 && clean.len() > signal_index {
                let last_ma = clean[signal_index];
                let prev_ma = clean[prev_index];
                descriptions.push(format!("MA_prev={prev_ma:.8},MA_last={last_ma:.8}"));
                if buy_allowed && prev_close < prev_ma && sig_close > last_ma {
                    action(
                        "ma",
                        "BUY",
                        "MA crossover -> BUY".to_owned(),
                        &mut signal,
                        &mut descriptions,
                        &mut sources,
                        &mut actions,
                    );
                } else if sell_allowed && prev_close > prev_ma && sig_close < last_ma {
                    action(
                        "ma",
                        "SELL",
                        "MA crossover -> SELL".to_owned(),
                        &mut signal,
                        &mut descriptions,
                        &mut sources,
                        &mut actions,
                    );
                }
            }
        }
    }

    if enabled(&input, "bb") {
        if let (Some(upper), Some(mid), Some(lower)) = (
            value_at(&input, "bb_upper", signal_index),
            value_at(&input, "bb_mid", signal_index),
            value_at(&input, "bb_lower", signal_index),
        ) {
            descriptions.push(format!(
                "BB_up={upper:.8},BB_mid={mid:.8},BB_low={lower:.8}"
            ));
        }
    }

    if enabled(&input, "keltner") {
        if let (Some(upper), Some(mid), Some(lower)) = (
            value_at(&input, "keltner_upper", signal_index),
            value_at(&input, "keltner_mid", signal_index),
            value_at(&input, "keltner_lower", signal_index),
        ) {
            let channel_state = if sig_close > upper {
                "above upper"
            } else if sig_close < lower {
                "below lower"
            } else {
                "inside channel"
            };
            descriptions.push(format!(
                "KC_up={upper:.8},KC_mid={mid:.8},KC_low={lower:.8},close {channel_state}"
            ));
        }
    }

    if enabled(&input, "ichimoku") {
        if let (Some(tenkan), Some(kijun)) = (
            value_at(&input, "ichimoku_tenkan", signal_index),
            value_at(&input, "ichimoku_kijun", signal_index),
        ) {
            let span_a = value_at(&input, "ichimoku_span_a", signal_index).unwrap_or(f64::NAN);
            let span_b = value_at(&input, "ichimoku_span_b", signal_index).unwrap_or(f64::NAN);
            let spread = tenkan - kijun;
            let cloud_state = if span_a.is_finite() && span_b.is_finite() {
                let top = span_a.max(span_b);
                let bottom = span_a.min(span_b);
                if sig_close > top {
                    "above cloud"
                } else if sig_close < bottom {
                    "below cloud"
                } else {
                    "inside cloud"
                }
            } else {
                "cloud unavailable"
            };
            descriptions.push(format!(
                "IC_tenkan={tenkan:.8},IC_kijun={kijun:.8},IC_span_a={span_a:.8},IC_span_b={span_b:.8},spread={spread:.8},close {cloud_state}"
            ));
            threshold_action_existing_value(
                &input,
                "ichimoku",
                "IC spread",
                "{:.2}",
                spread,
                Compare::BuyGeSellLe,
                buy_allowed,
                sell_allowed,
                &mut signal,
                &mut descriptions,
                &mut sources,
                &mut actions,
            );
        }
    }

    if descriptions.is_empty() {
        descriptions.push("No triggers evaluated".to_owned());
    }

    let mut seen = BTreeSet::new();
    sources.retain(|source| seen.insert(source.clone()));
    StrategySignalDecision {
        trigger_price: signal.as_ref().map(|_| sig_close),
        signal,
        description: descriptions.join(" | "),
        trigger_sources: sources,
        trigger_actions: actions,
        min_bars,
        signal_index_from_end,
    }
}

pub fn normalize_strategy_controls(kind: &str, controls: &Value) -> Value {
    let Some(input) = controls.as_object() else {
        return json!({});
    };
    let kind = kind.trim().to_lowercase();
    let mut out = Map::new();
    if kind == "runtime" {
        if let Some(side) = canonical_side(input.get("side")) {
            out.insert("side".to_owned(), Value::String(side));
        }
        insert_float(input, &mut out, "position_pct");
        if let Some(units) = normalize_position_pct_units(
            input
                .get("position_pct_units")
                .or_else(|| input.get("_position_pct_units")),
        ) {
            out.insert("position_pct_units".to_owned(), Value::String(units));
        }
        if let Some(leverage) = int_value(input.get("leverage")).filter(|value| *value >= 1) {
            out.insert("leverage".to_owned(), json!(leverage));
        }
        if let Some(loop_override) = normalize_loop_override(input.get("loop_interval_override")) {
            out.insert(
                "loop_interval_override".to_owned(),
                Value::String(loop_override),
            );
        }
        if let Some(value) = input.get("add_only") {
            out.insert(
                "add_only".to_owned(),
                Value::Bool(coerce_strategy_bool(Some(value), false)),
            );
        }
        if let Some(account_mode) = normalize_account_mode(input.get("account_mode")) {
            out.insert("account_mode".to_owned(), Value::String(account_mode));
        }
    } else if kind == "backtest" {
        if let Some(logic) = string_value(input.get("logic"))
            .map(|value| value.to_uppercase())
            .filter(|value| matches!(value.as_str(), "AND" | "OR" | "SEPARATE"))
        {
            out.insert("logic".to_owned(), Value::String(logic));
        }
        insert_float(input, &mut out, "capital");
        insert_float(input, &mut out, "position_pct");
        if let Some(units) = normalize_position_pct_units(
            input
                .get("position_pct_units")
                .or_else(|| input.get("_position_pct_units")),
        ) {
            out.insert("position_pct_units".to_owned(), Value::String(units));
        }
        if let Some(side) = canonical_side(input.get("side")) {
            out.insert("side".to_owned(), Value::String(side));
        }
        if let Some(margin_mode) =
            string_value(input.get("margin_mode")).filter(|value| !value.is_empty())
        {
            out.insert("margin_mode".to_owned(), Value::String(margin_mode));
        }
        if let Some(position_mode) =
            string_value(input.get("position_mode")).filter(|value| !value.is_empty())
        {
            out.insert("position_mode".to_owned(), Value::String(position_mode));
        }
        if let Some(assets_mode) = normalize_assets_mode(input.get("assets_mode")) {
            out.insert("assets_mode".to_owned(), Value::String(assets_mode));
        }
        if let Some(account_mode) = normalize_account_mode(input.get("account_mode")) {
            out.insert("account_mode".to_owned(), Value::String(account_mode));
        }
        if let Some(loop_override) = normalize_loop_override(input.get("loop_interval_override")) {
            out.insert(
                "loop_interval_override".to_owned(),
                Value::String(loop_override),
            );
        }
        if let Some(leverage) = int_value(input.get("leverage")) {
            out.insert("leverage".to_owned(), json!(leverage));
        }
    }
    if let Some(stop_loss) = input.get("stop_loss").filter(|value| value.is_object()) {
        out.insert("stop_loss".to_owned(), normalize_stop_loss(stop_loss));
    }
    if let Some(backend) =
        string_value(input.get("connector_backend")).filter(|value| !value.is_empty())
    {
        out.insert(
            "connector_backend".to_owned(),
            Value::String(normalize_connector_backend(backend)),
        );
    }
    Value::Object(out)
}

pub fn clean_backtest_result_payload(payload: &Value) -> Value {
    let Some(object) = payload.as_object() else {
        return json!({});
    };
    let mut out = Map::new();
    for (key, value) in object {
        if key.is_empty() || value.is_null() || value == "" {
            continue;
        }
        out.insert(key.clone(), value.clone());
    }
    Value::Object(out)
}

pub fn format_backtest_result_text(payload: &Value) -> String {
    let cleaned = clean_backtest_result_payload(payload);
    let Some(object) = cleaned.as_object() else {
        return "-".to_owned();
    };
    if object.is_empty() {
        return "-".to_owned();
    }
    let mut pieces = Vec::new();
    if let Some(rank) = object
        .get("optimizer_rank")
        .filter(|value| !value.is_null() && *value != "")
    {
        pieces.push(format!("Rank {}", display_value(rank)));
    }
    if let Some(text) = format_number(object.get("roi_percent"), "%") {
        pieces.push(format!("ROI {text}"));
    }
    let dd_value = object
        .get("max_drawdown_percent")
        .or_else(|| object.get("max_drawdown_during_percent"));
    if let Some(text) = format_number(dd_value, "%") {
        pieces.push(format!("DD {text}"));
    }
    if let Some(trades) = object
        .get("trades")
        .filter(|value| !value.is_null() && *value != "")
    {
        pieces.push(format!("Trades {}", display_value(trades)));
    }
    if pieces.is_empty() {
        string_value(object.get("source"))
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "Imported".to_owned())
    } else {
        pieces.join(" | ")
    }
}

pub fn build_clean_override_entry(kind: &str, entry: &Value) -> Value {
    let Some(object) = entry.as_object() else {
        return json!({"entry": null, "indicator_values": [], "leverage": null, "controls": {}});
    };
    let symbol = string_value(object.get("symbol"))
        .unwrap_or_default()
        .trim()
        .to_uppercase();
    let interval = if kind == "backtest" {
        normalize_backtest_interval(object.get("interval"))
    } else {
        normalize_loop_override(object.get("interval"))
            .or_else(|| string_value(object.get("interval")).map(|value| value.trim().to_owned()))
            .unwrap_or_default()
    };
    if symbol.is_empty() || interval.is_empty() {
        return json!({"entry": null, "indicator_values": [], "leverage": null, "controls": {}});
    }

    let indicator_values = normalize_indicator_values(object.get("indicators"));
    let mut controls = normalize_strategy_controls(
        kind,
        object.get("strategy_controls").unwrap_or(&Value::Null),
    );
    let leverage = controls
        .get("leverage")
        .and_then(Value::as_i64)
        .or_else(|| int_value(object.get("leverage")))
        .map(|value| value.max(1));
    if let Some(leverage) = leverage {
        if let Some(control_object) = controls.as_object_mut() {
            control_object.insert("leverage".to_owned(), json!(leverage));
        }
    }

    let mut clean = Map::new();
    clean.insert("symbol".to_owned(), Value::String(symbol));
    clean.insert("interval".to_owned(), Value::String(interval));
    if !indicator_values.is_empty() {
        clean.insert(
            "indicators".to_owned(),
            Value::Array(
                indicator_values
                    .iter()
                    .map(|item| Value::String(item.clone()))
                    .collect(),
            ),
        );
    }
    let loop_value = object
        .get("loop_interval_override")
        .and_then(|value| normalize_loop_override(Some(value)))
        .or_else(|| {
            controls
                .get("loop_interval_override")
                .and_then(|value| normalize_loop_override(Some(value)))
        });
    if let Some(loop_value) = loop_value {
        clean.insert(
            "loop_interval_override".to_owned(),
            Value::String(loop_value),
        );
    }
    if controls
        .as_object()
        .is_some_and(|object| !object.is_empty())
    {
        if let Some(stop_loss) = controls.get("stop_loss") {
            clean.insert("stop_loss".to_owned(), stop_loss.clone());
        }
        if let Some(backend) = controls.get("connector_backend") {
            clean.insert("connector_backend".to_owned(), backend.clone());
        }
        clean.insert("strategy_controls".to_owned(), controls.clone());
    }
    if let Some(leverage) = leverage {
        clean.insert("leverage".to_owned(), json!(leverage));
    }
    if !clean.contains_key("stop_loss") {
        if let Some(stop_loss) = object.get("stop_loss").filter(|value| value.is_object()) {
            clean.insert("stop_loss".to_owned(), normalize_stop_loss(stop_loss));
        }
    }
    let backtest_result =
        clean_backtest_result_payload(object.get("backtest_result").unwrap_or(&Value::Null));
    if backtest_result
        .as_object()
        .is_some_and(|object| !object.is_empty())
    {
        clean.insert("backtest_result".to_owned(), backtest_result);
    }

    json!({
        "entry": Value::Object(clean),
        "indicator_values": indicator_values,
        "leverage": leverage,
        "controls": controls,
    })
}

pub fn build_worker_lifecycle_snapshot(input: StrategyWorkerLifecycleInput) -> Value {
    let stopped = input.stop_requested || input.global_shutdown || input.global_pause;
    let lifecycle_phase = if input.global_shutdown {
        "shutdown"
    } else if input.global_pause {
        "paused"
    } else if input.stop_requested && input.thread_alive {
        "stopping"
    } else if input.thread_alive {
        "running"
    } else {
        "idle"
    };
    let interval = input
        .loop_interval_override
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(input.interval.as_str());
    let interval_seconds = interval_seconds_value(interval);
    json!({
        "symbol": input.symbol.trim().to_uppercase(),
        "interval": input.interval,
        "thread_name": format!("StrategyLoop-{}@{} ", input.symbol.trim().to_uppercase(), interval),
        "stopped": stopped,
        "is_alive": input.thread_alive,
        "lifecycle_phase": lifecycle_phase,
        "active_engine_count": input.active_engine_count,
        "offline_backoff": input.offline_backoff.max(0.0),
        "next_network_backoff": next_network_backoff(input.offline_backoff),
        "emergency_close_triggered": input.emergency_close_triggered,
        "loop_interval_seconds": interval_seconds,
        "phase_span_seconds": (interval_seconds * 0.35).clamp(2.0, 10.0),
        "execution_owner": "python-service",
        "native_trading_execution_enabled": false,
    })
}

pub fn next_network_backoff(previous: f64) -> f64 {
    if previous <= 0.0 {
        5.0
    } else {
        (previous * 1.5).max(5.0).min(90.0)
    }
}

#[derive(Clone, Copy)]
enum Compare {
    BuyLeSellGe,
    BuyGeSellLe,
    BuyLeSellGeDefaults(f64, f64),
    BuyGeSellLeDefaults(f64, f64),
}

fn enabled(input: &StrategySignalInput, key: &str) -> bool {
    input.rules.get(key).is_some_and(|rule| rule.enabled)
}

fn rule<'a>(input: &'a StrategySignalInput, key: &str) -> IndicatorRule {
    input.rules.get(key).cloned().unwrap_or_default()
}

fn indicator_values(input: &StrategySignalInput, key: &str) -> Option<(f64, f64, f64)> {
    let values = input.indicators.get(key)?;
    let clean: Vec<f64> = values
        .iter()
        .copied()
        .filter(|value| !value.is_nan())
        .collect();
    if clean.is_empty() {
        return None;
    }
    let live = *clean.last()?;
    let prev = if clean.len() >= 2 {
        clean[clean.len() - 2]
    } else {
        live
    };
    let selected = if input.use_live_values { live } else { prev };
    Some((prev, live, selected))
}

fn value_at(input: &StrategySignalInput, key: &str, index: usize) -> Option<f64> {
    let value = *input.indicators.get(key)?.get(index)?;
    value.is_finite().then_some(value)
}

fn context_only(
    input: &StrategySignalInput,
    key: &str,
    label: &str,
    pattern: &str,
    descriptions: &mut Vec<String>,
) {
    if !enabled(input, key) {
        return;
    }
    if let Some((_, _, value)) = indicator_values(input, key) {
        if value.is_finite() {
            descriptions.push(format_label_value(label, pattern, value));
        } else {
            descriptions.push(format!("{label}=NaN/inf skipped"));
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn threshold_action(
    input: &StrategySignalInput,
    key: &str,
    label: &str,
    pattern: &str,
    compare: Compare,
    buy_allowed: bool,
    sell_allowed: bool,
    signal: &mut Option<String>,
    descriptions: &mut Vec<String>,
    sources: &mut Vec<String>,
    actions: &mut BTreeMap<String, String>,
) {
    if !enabled(input, key) {
        return;
    }
    if let Some((_, _, value)) = indicator_values(input, key) {
        if value.is_finite() {
            descriptions.push(format_label_value(label, pattern, value));
            threshold_action_existing_value(
                input,
                key,
                label,
                pattern,
                value,
                compare,
                buy_allowed,
                sell_allowed,
                signal,
                descriptions,
                sources,
                actions,
            );
        } else {
            descriptions.push(format!("{label}=NaN/inf skipped"));
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn threshold_action_existing_value(
    input: &StrategySignalInput,
    key: &str,
    label: &str,
    pattern: &str,
    value: f64,
    compare: Compare,
    buy_allowed: bool,
    sell_allowed: bool,
    signal: &mut Option<String>,
    descriptions: &mut Vec<String>,
    sources: &mut Vec<String>,
    actions: &mut BTreeMap<String, String>,
) {
    let rule = rule(input, key);
    let (buy, sell, buy_ge) = match compare {
        Compare::BuyLeSellGe => match (rule.buy_value, rule.sell_value) {
            (Some(buy), Some(sell)) => (buy, sell, false),
            _ => return,
        },
        Compare::BuyGeSellLe => match (rule.buy_value, rule.sell_value) {
            (Some(buy), Some(sell)) => (buy, sell, true),
            _ => return,
        },
        Compare::BuyLeSellGeDefaults(buy, sell) => (
            rule.buy_value.unwrap_or(buy),
            rule.sell_value.unwrap_or(sell),
            false,
        ),
        Compare::BuyGeSellLeDefaults(buy, sell) => (
            rule.buy_value.unwrap_or(buy),
            rule.sell_value.unwrap_or(sell),
            true,
        ),
    };
    let precision = precision_from_pattern(pattern);
    if buy_ge {
        if buy_allowed && value >= buy {
            actions.insert(key.to_owned(), "buy".to_owned());
            descriptions.push(format!(
                "{label} >= {} -> BUY",
                format_number_precision(buy, precision)
            ));
            sources.push(key.to_owned());
            if signal.is_none() {
                *signal = Some("BUY".to_owned());
            }
        } else if sell_allowed && value <= sell {
            actions.insert(key.to_owned(), "sell".to_owned());
            descriptions.push(format!(
                "{label} <= {} -> SELL",
                format_number_precision(sell, precision)
            ));
            sources.push(key.to_owned());
            if signal.is_none() {
                *signal = Some("SELL".to_owned());
            }
        }
    } else if buy_allowed && value <= buy {
        actions.insert(key.to_owned(), "buy".to_owned());
        descriptions.push(format!(
            "{label} <= {} -> BUY",
            format_number_precision(buy, precision)
        ));
        sources.push(key.to_owned());
        if signal.is_none() {
            *signal = Some("BUY".to_owned());
        }
    } else if sell_allowed && value >= sell {
        actions.insert(key.to_owned(), "sell".to_owned());
        descriptions.push(format!(
            "{label} >= {} -> SELL",
            format_number_precision(sell, precision)
        ));
        sources.push(key.to_owned());
        if signal.is_none() {
            *signal = Some("SELL".to_owned());
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn histogram_action(
    input: &StrategySignalInput,
    key: &str,
    label: &str,
    line_key: &str,
    signal_key: &str,
    hist_key: &str,
    action_label: &str,
    buy_allowed: bool,
    sell_allowed: bool,
    signal: &mut Option<String>,
    descriptions: &mut Vec<String>,
    sources: &mut Vec<String>,
    actions: &mut BTreeMap<String, String>,
) {
    if !enabled(input, key) {
        return;
    }
    let Some((_, _, hist)) = indicator_values(input, hist_key) else {
        return;
    };
    let line = indicator_values(input, line_key)
        .map(|(_, _, value)| value)
        .unwrap_or(f64::NAN);
    let signal_line = indicator_values(input, signal_key)
        .map(|(_, _, value)| value)
        .unwrap_or(f64::NAN);
    if hist.is_finite() {
        let hist_name = if key == "kst" { "spread" } else { "hist" };
        descriptions.push(format!(
            "{label}={line:.4},{label}_signal={signal_line:.4},{hist_name}={hist:.4}"
        ));
        threshold_action_existing_value(
            input,
            key,
            action_label,
            "{:.4}",
            hist,
            Compare::BuyGeSellLeDefaults(0.0, 0.0),
            buy_allowed,
            sell_allowed,
            signal,
            descriptions,
            sources,
            actions,
        );
    } else {
        descriptions.push(format!("{label}=NaN/inf skipped"));
    }
}

fn format_label_value(label: &str, pattern: &str, value: f64) -> String {
    format!(
        "{label}={}",
        format_number_precision(value, precision_from_pattern(pattern))
    )
}

fn precision_from_pattern(pattern: &str) -> usize {
    if pattern.contains(".8") {
        8
    } else if pattern.contains(".4") {
        4
    } else {
        2
    }
}

fn format_number_precision(value: f64, precision: usize) -> String {
    match precision {
        8 => format!("{value:.8}"),
        4 => format!("{value:.4}"),
        _ => format!("{value:.2}"),
    }
}

fn string_value(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::String(text) => Some(text.trim().to_owned()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(flag) => Some(flag.to_string()),
        _ => None,
    }
}

fn float_value(value: Option<&Value>) -> Option<f64> {
    match value? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.trim().parse::<f64>().ok(),
        _ => None,
    }
}

fn int_value(value: Option<&Value>) -> Option<i64> {
    match value? {
        Value::Number(number) => number
            .as_i64()
            .or_else(|| number.as_f64().map(|value| value as i64)),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn insert_float(input: &Map<String, Value>, out: &mut Map<String, Value>, key: &str) {
    if let Some(value) = float_value(input.get(key)) {
        out.insert(key.to_owned(), json!(value));
    }
}

fn canonical_side(value: Option<&Value>) -> Option<String> {
    let text = string_value(value)?;
    let upper = text.to_uppercase();
    if matches!(upper.as_str(), "BUY" | "SELL" | "BOTH") {
        return Some(upper);
    }
    let lower = text.to_lowercase();
    if lower.starts_with("buy") {
        Some("BUY".to_owned())
    } else if lower.starts_with("sell") {
        Some("SELL".to_owned())
    } else if !lower.is_empty() {
        Some("BOTH".to_owned())
    } else {
        None
    }
}

fn normalize_position_pct_units(value: Option<&Value>) -> Option<String> {
    let lower = string_value(value)?.to_lowercase();
    match lower.as_str() {
        "percent" | "%" | "perc" | "percentage" => Some("percent".to_owned()),
        "fraction" | "decimal" | "ratio" => Some("fraction".to_owned()),
        _ => None,
    }
}

fn normalize_loop_override(value: Option<&Value>) -> Option<String> {
    let cleaned: String = string_value(value)?
        .chars()
        .filter(|ch| !ch.is_whitespace())
        .collect::<String>()
        .to_lowercase();
    if cleaned.is_empty() {
        return None;
    }
    let (digits, suffix): (String, String) = cleaned.chars().partition(|ch| ch.is_ascii_digit());
    if digits.is_empty() || digits.len() + suffix.len() != cleaned.len() {
        return None;
    }
    if suffix.is_empty() || matches!(suffix.as_str(), "s" | "m" | "h" | "d" | "w") {
        Some(cleaned)
    } else {
        None
    }
}

fn normalize_account_mode(value: Option<&Value>) -> Option<String> {
    let lower = string_value(value)?.to_lowercase();
    if lower.is_empty() {
        None
    } else if lower.contains("portfolio") {
        Some("Portfolio Margin".to_owned())
    } else {
        Some("Classic Trading".to_owned())
    }
}

fn normalize_assets_mode(value: Option<&Value>) -> Option<String> {
    let lower = string_value(value)?.to_lowercase();
    if lower.is_empty() {
        None
    } else if lower.contains("multi") {
        Some("Multi-Assets".to_owned())
    } else {
        Some("Single-Asset".to_owned())
    }
}

fn normalize_stop_loss(value: &Value) -> Value {
    let Some(object) = value.as_object() else {
        return json!({});
    };
    let enabled = coerce_strategy_bool(object.get("enabled"), false);
    let mut mode = string_value(object.get("mode"))
        .unwrap_or_else(|| "usdt".to_owned())
        .to_lowercase();
    if !matches!(mode.as_str(), "usdt" | "percent" | "both") {
        mode = "usdt".to_owned();
    }
    let mut scope = string_value(object.get("scope"))
        .unwrap_or_else(|| "per_trade".to_owned())
        .to_lowercase();
    if !matches!(
        scope.as_str(),
        "per_trade" | "directional" | "cumulative" | "entire_account"
    ) {
        scope = "per_trade".to_owned();
    }
    json!({
        "enabled": enabled,
        "mode": mode,
        "scope": scope,
        "usdt": float_value(object.get("usdt")).unwrap_or(0.0).max(0.0),
        "percent": float_value(object.get("percent")).unwrap_or(0.0).max(0.0),
    })
}

fn normalize_indicator_values(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| string_value(Some(item)))
            .filter(|item| !item.is_empty())
            .collect(),
        _ => Vec::new(),
    }
}

fn normalize_backtest_interval(value: Option<&Value>) -> String {
    let raw = string_value(value).unwrap_or_default();
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return String::new();
    }
    if let Some(number) = trimmed
        .strip_suffix('M')
        .and_then(|prefix| prefix.parse::<i64>().ok())
    {
        return format!("{number}mo");
    }
    let compact = trimmed.to_lowercase();
    let parts = split_amount_unit(&compact);
    let Some((amount, unit)) = parts else {
        return compact;
    };
    if matches!(unit.as_str(), "mo" | "mon" | "mons" | "month" | "months") {
        return format!("{}mo", format_amount(amount));
    }
    let unit = match unit.as_str() {
        "" | "m" | "min" | "mins" | "minute" | "minutes" => "m",
        "s" | "sec" | "secs" | "second" | "seconds" => "s",
        "h" | "hr" | "hrs" | "hour" | "hours" => "h",
        "d" | "day" | "days" => "d",
        "w" | "wk" | "wks" | "week" | "weeks" => "w",
        "y" | "yr" | "yrs" | "year" | "years" => "y",
        _ => return compact,
    };
    let seconds = match unit {
        "s" => Some(amount),
        "m" => Some(amount * 60.0),
        "h" => Some(amount * 3600.0),
        "d" => Some(amount * 86400.0),
        "w" => Some(amount * 604800.0),
        _ => None,
    };
    if let Some(seconds) = seconds {
        if let Some(canonical) = canonical_interval_by_seconds(seconds) {
            return canonical.to_owned();
        }
    }
    format!("{}{}", format_amount(amount), unit)
}

fn split_amount_unit(value: &str) -> Option<(f64, String)> {
    let compact: String = value.chars().filter(|ch| !ch.is_whitespace()).collect();
    let mut amount = String::new();
    let mut unit = String::new();
    for ch in compact.chars() {
        if ch.is_ascii_digit() || ch == '.' {
            if !unit.is_empty() {
                return None;
            }
            amount.push(ch);
        } else {
            unit.push(ch);
        }
    }
    Some((amount.parse::<f64>().ok()?, unit))
}

fn canonical_interval_by_seconds(seconds: f64) -> Option<&'static str> {
    const ITEMS: &[(f64, &str)] = &[
        (30.0, "30s"),
        (45.0, "45s"),
        (60.0, "1m"),
        (180.0, "3m"),
        (300.0, "5m"),
        (600.0, "10m"),
        (900.0, "15m"),
        (1800.0, "30m"),
        (2700.0, "45m"),
        (3600.0, "1h"),
        (7200.0, "2h"),
        (14400.0, "4h"),
        (86400.0, "1d"),
        (604800.0, "1w"),
    ];
    ITEMS
        .iter()
        .find(|(candidate, _)| (*candidate - seconds).abs() < f64::EPSILON)
        .map(|(_, label)| *label)
}

fn format_amount(value: f64) -> String {
    if value.fract().abs() < f64::EPSILON {
        format!("{}", value as i64)
    } else {
        format!("{value}")
            .trim_end_matches('0')
            .trim_end_matches('.')
            .to_owned()
    }
}

fn interval_seconds_value(interval: &str) -> f64 {
    let Some((amount, unit)) = split_amount_unit(interval) else {
        return 60.0;
    };
    match unit.as_str() {
        "s" => amount,
        "m" | "" => amount * 60.0,
        "h" => amount * 3600.0,
        "d" => amount * 86400.0,
        "w" => amount * 7.0 * 86400.0,
        _ => 60.0,
    }
}

fn display_value(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        _ => value.to_string(),
    }
}

fn format_number(value: Option<&Value>, suffix: &str) -> Option<String> {
    let value = float_value(value)?;
    value.is_finite().then(|| {
        let mut text = format!("{value:.2}");
        while text.contains('.') && text.ends_with('0') {
            text.pop();
        }
        if text.ends_with('.') {
            text.pop();
        }
        format!("{text}{suffix}")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rule(enabled: bool, buy_value: Option<f64>, sell_value: Option<f64>) -> IndicatorRule {
        IndicatorRule {
            enabled,
            buy_value,
            sell_value,
        }
    }

    #[test]
    fn indicator_output_keys_follow_python_compute_contract() {
        let config = json!({
            "rsi": {"enabled": "false"},
            "ema": {"enabled": "true"},
            "atr": {"enabled": true},
            "natr": {"enabled": true},
            "vwap": {"enabled": true},
            "mfi": {"enabled": true},
            "keltner": {"enabled": true},
            "ichimoku": {"enabled": true},
            "obv": {"enabled": true},
            "rvol": {"enabled": true},
            "cmf": {"enabled": true},
            "cci": {"enabled": true},
            "bbw": {"enabled": true},
            "roc": {"enabled": true},
            "trix": {"enabled": true},
            "ppo": {"enabled": true},
            "ao": {"enabled": true},
            "kst": {"enabled": true},
            "aroon": {"enabled": true},
            "chop": {"enabled": true},
            "stoch_rsi": {"enabled": true},
            "willr": {"enabled": true},
            "dmi": {"enabled": true},
            "stochastic": {"enabled": true}
        });
        let keys = indicator_output_keys_from_config(&config);
        assert!(!keys.contains(&"rsi".to_owned()));
        for key in [
            "ema",
            "atr",
            "natr",
            "vwap",
            "mfi",
            "keltner_upper",
            "keltner_mid",
            "keltner_lower",
            "ichimoku_tenkan",
            "ichimoku_kijun",
            "ichimoku",
            "obv",
            "rvol",
            "cmf",
            "cci",
            "bbw",
            "roc",
            "trix",
            "ppo",
            "ppo_signal",
            "ppo_hist",
            "ao",
            "kst",
            "kst_signal",
            "kst_hist",
            "aroon",
            "aroon_up",
            "aroon_down",
            "chop",
            "stoch_rsi_k",
            "willr",
            "dmi_plus",
            "stochastic_d",
        ] {
            assert!(keys.contains(&key.to_owned()), "missing {key}");
        }
    }

    #[test]
    fn signal_generation_uses_python_threshold_and_side_rules() {
        let mut rules = BTreeMap::new();
        rules.insert("rsi".to_owned(), rule(true, Some(30.0), Some(70.0)));
        rules.insert("natr".to_owned(), rule(true, Some(2.0), Some(1.0)));
        rules.insert("rvol".to_owned(), rule(true, Some(1.5), Some(0.75)));
        rules.insert("cci".to_owned(), rule(true, Some(-100.0), Some(100.0)));
        rules.insert("bbw".to_owned(), rule(true, Some(5.0), Some(2.0)));
        rules.insert("roc".to_owned(), rule(true, Some(0.0), Some(0.0)));
        rules.insert("trix".to_owned(), rule(true, Some(0.0), Some(0.0)));
        rules.insert("ppo".to_owned(), rule(true, Some(0.0), Some(0.0)));
        rules.insert("ao".to_owned(), rule(true, Some(0.0), Some(0.0)));
        rules.insert("kst".to_owned(), rule(true, Some(0.0), Some(0.0)));
        rules.insert("aroon".to_owned(), rule(true, Some(50.0), Some(-50.0)));
        rules.insert("chop".to_owned(), rule(true, Some(38.2), Some(61.8)));
        rules.insert("mfi".to_owned(), rule(true, Some(20.0), Some(80.0)));
        rules.insert("atr".to_owned(), rule(true, None, None));
        rules.insert("vwap".to_owned(), rule(true, None, None));
        rules.insert("cmf".to_owned(), rule(true, None, None));
        rules.insert("obv".to_owned(), rule(true, None, None));
        rules.insert("keltner".to_owned(), rule(true, None, None));
        rules.insert("ichimoku".to_owned(), rule(true, None, None));

        let input = StrategySignalInput {
            closes: vec![100.0, 101.0, 106.0],
            indicators: BTreeMap::from([
                ("rsi".to_owned(), vec![50.0, 25.0, 20.0]),
                ("natr".to_owned(), vec![0.5, 1.5, 2.5]),
                ("rvol".to_owned(), vec![0.9, 1.2, 1.6]),
                ("cci".to_owned(), vec![0.0, -120.0, -130.0]),
                ("bbw".to_owned(), vec![1.0, 4.0, 6.0]),
                ("roc".to_owned(), vec![-1.0, 0.5, 2.0]),
                ("trix".to_owned(), vec![-0.1, 0.2, 0.4]),
                ("ppo".to_owned(), vec![0.0, 0.5, 1.0]),
                ("ppo_signal".to_owned(), vec![0.0, 0.25, 0.5]),
                ("ppo_hist".to_owned(), vec![0.0, 0.25, 0.5]),
                ("ao".to_owned(), vec![-0.1, 0.2, 0.4]),
                ("kst".to_owned(), vec![0.0, 1.0, 2.0]),
                ("kst_signal".to_owned(), vec![0.0, 0.5, 1.0]),
                ("kst_hist".to_owned(), vec![0.0, 0.5, 1.0]),
                ("aroon".to_owned(), vec![0.0, 60.0, 80.0]),
                ("aroon_up".to_owned(), vec![50.0, 100.0, 100.0]),
                ("aroon_down".to_owned(), vec![50.0, 40.0, 20.0]),
                ("chop".to_owned(), vec![70.0, 45.0, 30.0]),
                ("mfi".to_owned(), vec![50.0, 18.0, 15.0]),
                ("atr".to_owned(), vec![1.0, 2.0, 3.0]),
                ("vwap".to_owned(), vec![100.0, 100.5, 101.5]),
                ("cmf".to_owned(), vec![0.1, 0.2, 0.25]),
                ("obv".to_owned(), vec![0.0, 1000.0, 2000.0]),
                ("keltner_upper".to_owned(), vec![103.0, 104.0, 105.0]),
                ("keltner_mid".to_owned(), vec![100.0, 101.0, 102.0]),
                ("keltner_lower".to_owned(), vec![97.0, 98.0, 99.0]),
                ("ichimoku_tenkan".to_owned(), vec![100.0, 101.0, 105.0]),
                ("ichimoku_kijun".to_owned(), vec![99.0, 100.0, 103.0]),
                ("ichimoku_span_a".to_owned(), vec![98.0, 100.0, 104.0]),
                ("ichimoku_span_b".to_owned(), vec![97.0, 99.0, 102.0]),
            ]),
            rules,
            side: "BUY".to_owned(),
            use_live_values: true,
        };

        let decision = build_signal_decision(input);
        assert_eq!(decision.signal.as_deref(), Some("BUY"));
        assert_eq!(
            decision.trigger_sources.first().map(String::as_str),
            Some("rsi")
        );
        assert_eq!(
            decision.trigger_actions.get("rsi").map(String::as_str),
            Some("buy")
        );
        for text in [
            "RSI=20.00",
            "NATR=2.5000",
            "RVOL >= 1.5000 -> BUY",
            "CCI <= -100.00 -> BUY",
            "BBW >= 5.0000 -> BUY",
            "ROC >= 0.00 -> BUY",
            "TRIX >= 0.0000 -> BUY",
            "PPO hist >= 0.0000 -> BUY",
            "AO >= 0.0000 -> BUY",
            "KST spread >= 0.0000 -> BUY",
            "Aroon >= 50.00 -> BUY",
            "CHOP <= 38.2000 -> BUY",
            "MFI <= 20.00 -> BUY",
            "ATR=3.00000000",
            "VWAP=101.50000000",
            "CMF=0.2500",
            "OBV=2000.00",
            "KC_up=105.00000000",
            "IC_tenkan=105.00000000",
            "close above cloud",
        ] {
            assert!(decision.description.contains(text), "missing {text}");
        }
    }

    #[test]
    fn signal_generation_switches_to_closed_candle_like_python() {
        let decision = build_signal_decision(StrategySignalInput {
            closes: vec![100.0, 101.0, 102.0],
            indicators: BTreeMap::from([("rsi".to_owned(), vec![80.0, 20.0, 90.0])]),
            rules: BTreeMap::from([("rsi".to_owned(), rule(true, Some(30.0), Some(70.0)))]),
            side: "BUY".to_owned(),
            use_live_values: false,
        });
        assert_eq!(decision.signal.as_deref(), Some("BUY"));
        assert_eq!(decision.trigger_price, Some(101.0));
        assert_eq!(decision.signal_index_from_end, 2);
        assert!(decision.description.contains("RSI=20.00"));
    }

    #[test]
    fn strategy_controls_normalize_runtime_and_backtest_like_python() {
        let runtime = normalize_strategy_controls(
            "runtime",
            &json!({
                "side": "buy only",
                "position_pct": "12.5",
                "position_pct_units": "ratio",
                "leverage": "3",
                "loop_interval_override": " 5 M ",
                "add_only": "false",
                "account_mode": "portfolio margin",
                "connector_backend": "CCXT",
                "stop_loss": {"enabled": "true", "mode": "both", "scope": "bad", "usdt": "50", "percent": "2.5"}
            }),
        );
        assert_eq!(runtime["side"], "BUY");
        assert_eq!(runtime["position_pct"], 12.5);
        assert_eq!(runtime["position_pct_units"], "fraction");
        assert_eq!(runtime["leverage"], 3);
        assert_eq!(runtime["loop_interval_override"], "5m");
        assert_eq!(runtime["add_only"], false);
        assert_eq!(runtime["account_mode"], "Portfolio Margin");
        assert_eq!(runtime["connector_backend"], "ccxt");
        assert_eq!(runtime["stop_loss"]["scope"], "per_trade");

        let backtest = normalize_strategy_controls(
            "backtest",
            &json!({
                "logic": "separate",
                "capital": "1000",
                "side": "sell short",
                "assets_mode": "multi assets",
                "account_mode": "classic",
                "leverage": "10",
                "margin_mode": "Isolated",
                "position_mode": "Hedge"
            }),
        );
        assert_eq!(backtest["logic"], "SEPARATE");
        assert_eq!(backtest["capital"], 1000.0);
        assert_eq!(backtest["side"], "SELL");
        assert_eq!(backtest["assets_mode"], "Multi-Assets");
        assert_eq!(backtest["account_mode"], "Classic Trading");
        assert_eq!(backtest["leverage"], 10);
    }

    #[test]
    fn override_entries_preserve_strategy_controls_and_backtest_provenance() {
        let result = build_clean_override_entry(
            "backtest",
            &json!({
                "symbol": " btcusdt ",
                "interval": "1M",
                "indicators": ["ema", "", "volume"],
                "strategy_controls": {
                    "logic": "or",
                    "position_pct": "20",
                    "position_pct_units": "%",
                    "leverage": 0,
                    "connector_backend": "binance-sdk-spot"
                },
                "leverage": 3,
                "backtest_result": {
                    "source": "python-backtest",
                    "optimizer_rank": 1,
                    "roi_percent": 12.5,
                    "max_drawdown_percent": 3.25,
                    "trades": 4,
                    "empty": ""
                }
            }),
        );
        let entry = &result["entry"];
        assert_eq!(entry["symbol"], "BTCUSDT");
        assert_eq!(entry["interval"], "1mo");
        assert_eq!(entry["indicators"], json!(["ema", "volume"]));
        assert_eq!(entry["leverage"], 1);
        assert_eq!(entry["strategy_controls"]["leverage"], 1);
        assert_eq!(entry["backtest_result"]["source"], "python-backtest");
        assert_eq!(entry["backtest_result"]["optimizer_rank"], 1);
        assert!(entry["backtest_result"].get("empty").is_none());
        assert_eq!(
            format_backtest_result_text(&entry["backtest_result"]),
            "Rank 1 | ROI 12.5% | DD 3.25% | Trades 4"
        );
    }

    #[test]
    fn worker_lifecycle_snapshot_matches_python_runtime_boundaries() {
        let running = build_worker_lifecycle_snapshot(StrategyWorkerLifecycleInput {
            symbol: "btcusdt".to_owned(),
            interval: "1m".to_owned(),
            loop_interval_override: Some("5m".to_owned()),
            thread_alive: true,
            active_engine_count: 2,
            offline_backoff: 5.0,
            ..Default::default()
        });
        assert_eq!(running["lifecycle_phase"], "running");
        assert_eq!(running["thread_name"], "StrategyLoop-BTCUSDT@5m ");
        assert_eq!(running["loop_interval_seconds"], 300.0);
        assert_eq!(running["phase_span_seconds"], 10.0);
        assert_eq!(running["next_network_backoff"], 7.5);
        assert_eq!(running["execution_owner"], "python-service");
        assert_eq!(running["native_trading_execution_enabled"], false);

        let stopping = build_worker_lifecycle_snapshot(StrategyWorkerLifecycleInput {
            symbol: "ethusdt".to_owned(),
            interval: "1m".to_owned(),
            thread_alive: true,
            stop_requested: true,
            ..Default::default()
        });
        assert_eq!(stopping["stopped"], true);
        assert_eq!(stopping["lifecycle_phase"], "stopping");
    }
}
