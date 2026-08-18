use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};
use std::time::{Duration, Instant};

use chrono::{DateTime, NaiveDate, NaiveDateTime, Utc};
use serde_json::{Map, Value, json};

use crate::backtest_runtime::{
    NativeBacktestRequest, NativeBacktestResult, default_config_choice, normalize_config_choice,
    run_native_backtest_with_cancel_and_window,
};
use crate::generated_python_parity::{
    PYTHON_LOGIC_CONFIG_CHOICES, PYTHON_MDD_LOGIC_CONFIG_CHOICES,
    PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES, PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES,
    PYTHON_SCAN_SCOPE_CONFIG_CHOICES, PYTHON_SIDE_CONFIG_CHOICES,
    PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES, PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES,
};
use crate::market_data::BinanceKlineCandle;
use crate::python_source_default_backtest_config;
use crate::python_source_default_execution_config;
use crate::python_source_ui_defaults;
use crate::strategy_runtime::normalize_backtest_interval;

pub const MAX_OPTIMIZER_RUNS: u64 = 100_000_000_000;
pub const DEFAULT_RESULT_LIMIT: usize = 5_000;
pub const DEFAULT_OPTIMIZER_DURATION_SECONDS: u64 = 4 * 60 * 60;
pub const MIN_OPTIMIZER_DURATION_SECONDS: u64 = 60;
pub const MAX_OPTIMIZER_DURATION_SECONDS: u64 = 7 * 24 * 60 * 60;

#[derive(Debug, Clone)]
pub struct CandleLoadResult {
    pub ok: bool,
    pub candles: Vec<BinanceKlineCandle>,
    pub error: String,
}

impl CandleLoadResult {
    pub fn success(candles: Vec<BinanceKlineCandle>) -> Self {
        Self {
            ok: true,
            candles,
            error: String::new(),
        }
    }

    pub fn failure(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            candles: Vec::new(),
            error: error.into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct NativeBacktestBatchRequest {
    pub symbols: Vec<String>,
    pub intervals: Vec<String>,
    pub indicator_configs: BTreeMap<String, Value>,
    pub run_template: NativeBacktestRequest,
    pub optimizer_enabled: bool,
    pub optimizer_mode: String,
    pub optimizer_metric: String,
    pub optimizer_scope: String,
    pub optimizer_combo_size: usize,
    pub optimizer_min_trades: usize,
    pub optimizer_mdd_limit: f64,
    pub optimizer_max_duration_seconds: u64,
    pub result_limit: usize,
    pub max_run_count: u64,
    pub start_display: String,
    pub end_display: String,
    pub start_ms: Option<i64>,
    pub end_ms: Option<i64>,
    pub warmup_bars: usize,
    pub loop_interval_override: String,
    pub connector_backend: String,
    pub selected_exchange: String,
    pub scan_top_n: usize,
    pub resume_combo_offset: u64,
    pub resume_prior_runs: Vec<Value>,
    pub resume_prior_errors: Vec<Value>,
    pub pair_overrides: Vec<Value>,
}

impl Default for NativeBacktestBatchRequest {
    fn default() -> Self {
        let backtest_defaults = python_source_default_backtest_config();
        let execution_defaults = python_source_default_execution_config();
        let ui_defaults = python_source_ui_defaults();
        let default_symbols = backtest_defaults
            .get("symbols")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|value| !value.trim().is_empty())
                    .map(str::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        let default_intervals = backtest_defaults
            .get("intervals")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|value| !value.trim().is_empty())
                    .map(str::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        let default_indicator_configs = backtest_defaults
            .get("indicators")
            .and_then(Value::as_object)
            .map(|values| {
                values
                    .iter()
                    .map(|(key, value)| (key.clone(), value.clone()))
                    .collect::<BTreeMap<_, _>>()
            })
            .unwrap_or_default();
        let text_default = |defaults: &Value, key: &str, fallback: &str| {
            defaults
                .get(key)
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .unwrap_or(fallback)
                .to_owned()
        };
        let number_default = |key: &str, fallback: f64| {
            backtest_defaults
                .get(key)
                .and_then(Value::as_f64)
                .filter(|value| value.is_finite())
                .unwrap_or(fallback)
        };
        Self {
            symbols: default_symbols,
            intervals: default_intervals,
            indicator_configs: default_indicator_configs,
            run_template: NativeBacktestRequest::default(),
            optimizer_enabled: false,
            optimizer_mode: text_default(backtest_defaults, "optimizer_mode", "current"),
            optimizer_metric: text_default(backtest_defaults, "optimizer_metric", "roi_percent"),
            optimizer_scope: text_default(backtest_defaults, "scan_scope", "selected"),
            optimizer_combo_size: number_default("optimizer_combo_size", 2.0)
                .trunc()
                .clamp(1.0, 5.0) as usize,
            optimizer_min_trades: number_default("optimizer_min_trades", 1.0).trunc().max(0.0)
                as usize,
            optimizer_mdd_limit: number_default("scan_mdd_limit", 10.0).max(0.0),
            optimizer_max_duration_seconds: number_default(
                "optimizer_max_duration_seconds",
                14_400.0,
            )
            .trunc()
            .clamp(
                MIN_OPTIMIZER_DURATION_SECONDS as f64,
                MAX_OPTIMIZER_DURATION_SECONDS as f64,
            ) as u64,
            result_limit: DEFAULT_RESULT_LIMIT,
            max_run_count: MAX_OPTIMIZER_RUNS,
            start_display: String::new(),
            end_display: String::new(),
            start_ms: None,
            end_ms: None,
            warmup_bars: 50,
            loop_interval_override: text_default(
                execution_defaults,
                "loop_interval_override",
                "1m",
            ),
            connector_backend: text_default(
                backtest_defaults,
                "connector_backend",
                "binance-connector",
            ),
            selected_exchange: ui_defaults
                .get("selected_exchange")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .unwrap_or("Binance")
                .to_owned(),
            scan_top_n: number_default("scan_top_n", 200.0).trunc().max(1.0) as usize,
            resume_combo_offset: 0,
            resume_prior_runs: Vec::new(),
            resume_prior_errors: Vec::new(),
            pair_overrides: Vec::new(),
        }
    }
}

fn request_object(payload: &Value) -> Result<&Map<String, Value>, String> {
    payload
        .as_object()
        .ok_or_else(|| "Native backtest request must be a JSON object.".to_owned())
}

fn request_text(object: &Map<String, Value>, key: &str, fallback: &str) -> String {
    object
        .get(key)
        .and_then(|value| {
            value
                .as_str()
                .map(str::to_owned)
                .or_else(|| value.as_f64().map(|number| number.to_string()))
        })
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| fallback.to_owned())
}

fn request_number(object: &Map<String, Value>, key: &str, fallback: f64) -> f64 {
    object
        .get(key)
        .and_then(|value| {
            value
                .as_f64()
                .or_else(|| value.as_str().and_then(|text| text.trim().parse().ok()))
        })
        .filter(|value: &f64| value.is_finite())
        .unwrap_or(fallback)
}

fn request_bool(object: &Map<String, Value>, key: &str, fallback: bool) -> bool {
    let Some(value) = object.get(key) else {
        return fallback;
    };
    if let Some(boolean) = value.as_bool() {
        return boolean;
    }
    if let Some(number) = value.as_f64() {
        return number != 0.0;
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

fn request_text_list(object: &Map<String, Value>, key: &str) -> Vec<String> {
    object
        .get(key)
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|value| value.as_str().map(str::trim))
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect()
}

const WARMUP_PARAMETER_KEYS: &[&str] = &[
    "length",
    "fast",
    "slow",
    "signal",
    "smooth_k",
    "smooth_d",
    "short",
    "medium",
    "long",
    "atr_period",
    "atr_length",
    "conversion_length",
    "base_length",
    "span_b_length",
    "displacement",
    "roc1",
    "roc2",
    "roc3",
    "roc4",
    "sma1",
    "sma2",
    "sma3",
    "sma4",
];

fn estimate_warmup_bars(indicator_configs: &BTreeMap<String, Value>) -> usize {
    let maximum = indicator_configs
        .values()
        .map(|config| {
            if !config_enabled(config) {
                return 0;
            }
            let mut maximum = 0_usize;
            let mut has_candidate = false;
            for source in [Some(config), config.get("params")] {
                let Some(object) = source.and_then(Value::as_object) else {
                    continue;
                };
                for key in WARMUP_PARAMETER_KEYS {
                    let value = object
                        .get(*key)
                        .and_then(|value| {
                            value
                                .as_f64()
                                .or_else(|| value.as_str().and_then(|text| text.parse().ok()))
                        })
                        .filter(|value: &f64| value.is_finite() && *value >= 0.0)
                        .map(|value| {
                            has_candidate = true;
                            value
                        })
                        .unwrap_or(0.0);
                    maximum = maximum.max(value.floor() as usize);
                }
            }
            if has_candidate { maximum } else { 50 }
        })
        .max()
        .unwrap_or(100);
    if maximum == 0 { 100 } else { maximum }
}

fn parse_request_datetime(value: &str) -> Result<Option<i64>, String> {
    let value = value.trim();
    if value.is_empty() {
        return Ok(None);
    }
    if let Ok(parsed) = DateTime::parse_from_rfc3339(value) {
        return Ok(Some(parsed.timestamp_millis()));
    }
    for format in ["%Y-%m-%d %H:%M:%S%.f", "%Y-%m-%dT%H:%M:%S%.f"] {
        if let Ok(parsed) = NaiveDateTime::parse_from_str(value, format) {
            return Ok(Some(parsed.and_utc().timestamp_millis()));
        }
    }
    if let Ok(parsed) = NaiveDate::parse_from_str(value, "%Y-%m-%d")
        && let Some(parsed) = parsed.and_hms_opt(0, 0, 0)
    {
        return Ok(Some(parsed.and_utc().timestamp_millis()));
    }
    Err(format!("Invalid backtest date: {value}"))
}

fn resolve_request_date_range(start: &str, end: &str) -> Result<(i64, i64), String> {
    let end_ms = parse_request_datetime(end)?.unwrap_or_else(|| Utc::now().timestamp_millis());
    let start_ms =
        parse_request_datetime(start)?.unwrap_or_else(|| end_ms.saturating_sub(30 * 86_400_000));
    if start_ms >= end_ms {
        return Err("Backtest start must be earlier than backtest end.".to_owned());
    }
    Ok((start_ms, end_ms))
}

impl NativeBacktestBatchRequest {
    /// Convert the Python Service API backtest request shape without dropping
    /// controls that are only relevant to optimizer or pair-override runs.
    pub fn from_python_request(payload: &Value) -> Result<Self, String> {
        let object = request_object(payload)?;
        let defaults = python_source_default_backtest_config();
        let mut symbols = request_text_list(object, "symbols");
        let intervals = unique_intervals(&request_text_list(object, "intervals"));
        let indicator_configs = object
            .get("indicators")
            .and_then(Value::as_object)
            .map(|value| {
                value
                    .iter()
                    .map(|(key, config)| (key.clone(), config.clone()))
                    .collect::<BTreeMap<_, _>>()
            })
            .unwrap_or_default();
        if symbols.is_empty() {
            return Err("At least one symbol is required for native backtesting.".to_owned());
        }
        if intervals.is_empty() {
            return Err("At least one interval is required for native backtesting.".to_owned());
        }
        if indicator_configs.is_empty() {
            return Err(
                "At least one enabled indicator is required for native backtesting.".to_owned(),
            );
        }

        let mut run_template = NativeBacktestRequest::default();
        run_template.logic = normalize_config_choice(
            &request_text(
                object,
                "logic",
                defaults
                    .get("logic")
                    .and_then(Value::as_str)
                    .unwrap_or("AND"),
            ),
            PYTHON_LOGIC_CONFIG_CHOICES,
            &default_config_choice(PYTHON_LOGIC_CONFIG_CHOICES, "AND"),
        );
        run_template.side = normalize_config_choice(
            &request_text(
                object,
                "side",
                defaults
                    .get("side")
                    .and_then(Value::as_str)
                    .unwrap_or("BOTH"),
            ),
            PYTHON_SIDE_CONFIG_CHOICES,
            &default_config_choice(PYTHON_SIDE_CONFIG_CHOICES, "BOTH"),
        );
        run_template.capital = request_number(object, "capital", run_template.capital);
        if run_template.capital <= 0.0 {
            return Err("Backtest capital must be positive.".to_owned());
        }
        run_template.position_pct =
            request_number(object, "position_pct", run_template.position_pct);
        run_template.position_pct_units = request_text(object, "position_pct_units", "percent");
        run_template.leverage = request_number(object, "leverage", run_template.leverage).max(1.0);
        run_template.margin_mode = request_text(object, "margin_mode", &run_template.margin_mode);
        run_template.position_mode =
            request_text(object, "position_mode", &run_template.position_mode);
        run_template.assets_mode = request_text(object, "assets_mode", &run_template.assets_mode);
        run_template.account_mode =
            request_text(object, "account_mode", &run_template.account_mode);
        run_template.mdd_logic = normalize_config_choice(
            &request_text(object, "mdd_logic", &run_template.mdd_logic),
            PYTHON_MDD_LOGIC_CONFIG_CHOICES,
            &default_config_choice(PYTHON_MDD_LOGIC_CONFIG_CHOICES, "per_trade"),
        );
        run_template.fee_bps = request_number(object, "fee_bps", run_template.fee_bps).max(0.0);
        run_template.slippage_bps =
            request_number(object, "slippage_bps", run_template.slippage_bps).max(0.0);

        let stop_loss = object
            .get("stop_loss")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        run_template.stop_loss_enabled = request_bool(
            &stop_loss,
            "enabled",
            request_bool(object, "stop_loss_enabled", run_template.stop_loss_enabled),
        );
        run_template.stop_loss_mode = normalize_config_choice(
            &request_text(
                &stop_loss,
                "mode",
                &request_text(object, "stop_loss_mode", &run_template.stop_loss_mode),
            ),
            PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES,
            &default_config_choice(PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES, "usdt"),
        );
        run_template.stop_loss_usdt = request_number(
            &stop_loss,
            "usdt",
            request_number(object, "stop_loss_usdt", run_template.stop_loss_usdt),
        )
        .max(0.0);
        run_template.stop_loss_percent = request_number(
            &stop_loss,
            "percent",
            request_number(object, "stop_loss_percent", run_template.stop_loss_percent),
        )
        .max(0.0);
        run_template.stop_loss_scope = normalize_config_choice(
            &request_text(
                &stop_loss,
                "scope",
                &request_text(object, "stop_loss_scope", &run_template.stop_loss_scope),
            ),
            PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES,
            &default_config_choice(PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES, "per_trade"),
        );

        let optimizer_mode = normalize_config_choice(
            &request_text(
                object,
                "optimizer_mode",
                defaults
                    .get("optimizer_mode")
                    .and_then(Value::as_str)
                    .unwrap_or("current"),
            ),
            PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES,
            &default_config_choice(PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES, "current"),
        );
        let optimizer_scope = normalize_config_choice(
            &request_text(
                object,
                "scan_scope",
                defaults
                    .get("scan_scope")
                    .and_then(Value::as_str)
                    .unwrap_or("selected"),
            ),
            PYTHON_SCAN_SCOPE_CONFIG_CHOICES,
            &default_config_choice(PYTHON_SCAN_SCOPE_CONFIG_CHOICES, "selected"),
        );
        let scan_top_n = request_number(
            object,
            "scan_top_n",
            defaults
                .get("scan_top_n")
                .and_then(Value::as_f64)
                .unwrap_or(200.0),
        )
        .trunc()
        .max(1.0) as usize;
        if !optimizer_mode.eq_ignore_ascii_case("current")
            && optimizer_scope.eq_ignore_ascii_case("top_n")
        {
            symbols.truncate(scan_top_n);
        }
        let has_pair_overrides = object.contains_key("pair_overrides");
        let pair_overrides = object
            .get("pair_overrides")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let optimizer_enabled = request_bool(
            object,
            "optimizer_enabled",
            !optimizer_mode.eq_ignore_ascii_case("current") && !has_pair_overrides,
        );
        let start_display = request_text(object, "start", &request_text(object, "start_date", ""));
        let end_display = request_text(object, "end", &request_text(object, "end_date", ""));
        let (start_ms, end_ms) = resolve_request_date_range(&start_display, &end_display)?;
        let normalized_optimizer_max_duration_seconds = request_number(
            object,
            "optimizer_max_duration_seconds",
            defaults
                .get("optimizer_max_duration_seconds")
                .and_then(Value::as_f64)
                .unwrap_or(DEFAULT_OPTIMIZER_DURATION_SECONDS as f64),
        )
        .trunc()
        .max(MIN_OPTIMIZER_DURATION_SECONDS as f64)
        .min(MAX_OPTIMIZER_DURATION_SECONDS as f64)
            as u64;
        let optimizer_max_duration_seconds = if optimizer_enabled {
            normalized_optimizer_max_duration_seconds
        } else {
            0
        };
        let warmup_bars = estimate_warmup_bars(&indicator_configs);
        Ok(Self {
            symbols,
            intervals,
            indicator_configs,
            run_template,
            optimizer_enabled,
            optimizer_mode,
            optimizer_metric: normalize_config_choice(
                &request_text(
                    object,
                    "optimizer_metric",
                    defaults
                        .get("optimizer_metric")
                        .and_then(Value::as_str)
                        .unwrap_or("roi_percent"),
                ),
                PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES,
                &default_config_choice(PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES, "roi_percent"),
            ),
            optimizer_scope,
            optimizer_combo_size: request_number(
                object,
                "optimizer_combo_size",
                defaults
                    .get("optimizer_combo_size")
                    .and_then(Value::as_f64)
                    .unwrap_or(2.0),
            )
            .trunc()
            .clamp(1.0, 5.0) as usize,
            optimizer_min_trades: request_number(
                object,
                "optimizer_min_trades",
                defaults
                    .get("optimizer_min_trades")
                    .and_then(Value::as_f64)
                    .unwrap_or(1.0),
            )
            .trunc()
            .max(0.0) as usize,
            optimizer_mdd_limit: request_number(
                object,
                "scan_mdd_limit",
                defaults
                    .get("scan_mdd_limit")
                    .and_then(Value::as_f64)
                    .unwrap_or(10.0),
            )
            .max(0.0),
            optimizer_max_duration_seconds,
            result_limit: request_number(
                object,
                "optimizer_result_limit",
                DEFAULT_RESULT_LIMIT as f64,
            )
            .trunc()
            .max(1.0) as usize,
            max_run_count: MAX_OPTIMIZER_RUNS,
            start_display,
            end_display,
            start_ms: Some(start_ms),
            end_ms: Some(end_ms),
            warmup_bars,
            loop_interval_override: request_text(
                object,
                "loop_interval_override",
                defaults
                    .get("loop_interval_override")
                    .and_then(Value::as_str)
                    .unwrap_or("1m"),
            ),
            connector_backend: request_text(
                object,
                "connector_backend",
                defaults
                    .get("connector_backend")
                    .and_then(Value::as_str)
                    .unwrap_or("binance-connector"),
            ),
            selected_exchange: request_text(
                object,
                "selected_exchange",
                crate::python_source_ui_defaults()
                    .get("selected_exchange")
                    .and_then(Value::as_str)
                    .unwrap_or("Binance"),
            ),
            scan_top_n,
            resume_combo_offset: request_number(object, "resume_combo_offset", 0.0)
                .trunc()
                .max(0.0) as u64,
            resume_prior_runs: object
                .get("resume_prior_runs")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default(),
            resume_prior_errors: object
                .get("resume_prior_errors")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default(),
            pair_overrides,
        })
    }
}

#[derive(Debug, Clone)]
pub struct OptimizerScore {
    pub eligible: bool,
    pub values: Vec<f64>,
    pub rejection_reason: String,
}

#[derive(Debug, Clone)]
struct OverridePlan {
    symbol: String,
    interval: String,
    indicator_keys: Vec<String>,
    run_template: NativeBacktestRequest,
    reported_logic: String,
    loop_interval_override: String,
    connector_backend: String,
}

#[derive(Debug, Default)]
struct OverridePlanSet {
    has_valid_overrides: bool,
    plans: Vec<OverridePlan>,
}

#[derive(Debug)]
struct RankedRow {
    score: Vec<f64>,
    original_index: u64,
    row: Value,
}

fn normalized_token(value: &str, fallback: &str) -> String {
    let token = value.trim().to_ascii_lowercase().replace(['-', ' '], "_");
    if token.is_empty() {
        fallback.to_owned()
    } else {
        token
    }
}

fn config_enabled(config: &Value) -> bool {
    let Some(value) = config.get("enabled") else {
        return false;
    };
    if let Some(value) = value.as_bool() {
        return value;
    }
    if let Some(value) = value.as_f64() {
        return value != 0.0;
    }
    matches!(
        value
            .as_str()
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase()
            .as_str(),
        "true" | "1" | "yes" | "on"
    )
}

fn config_is_filter(config: &Value) -> bool {
    let role = config
        .get("signal_role")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .or_else(|| config.get("role").and_then(Value::as_str))
        .unwrap_or("signal");
    matches!(
        normalized_token(role, "signal").as_str(),
        "filter" | "entry_filter" | "gate" | "confirmation"
    )
}

fn append_combinations(
    keys: &[String],
    target_size: usize,
    start: usize,
    current: &mut Vec<String>,
    groups: &mut Vec<Vec<String>>,
) {
    if current.len() == target_size {
        groups.push(current.clone());
        return;
    }
    let remaining = target_size.saturating_sub(current.len());
    for index in start..=keys.len().saturating_sub(remaining) {
        current.push(keys[index].clone());
        append_combinations(keys, target_size, index + 1, current, groups);
        current.pop();
    }
}

fn with_filters(signal_keys: &[String], filter_keys: &[String]) -> Vec<String> {
    let mut combined = signal_keys.to_vec();
    for key in filter_keys {
        if !combined.contains(key) {
            combined.push(key.clone());
        }
    }
    combined
}

pub fn build_indicator_groups(
    configs: &BTreeMap<String, Value>,
    mode: &str,
    combo_size: usize,
    logic: &str,
) -> Vec<Vec<String>> {
    let mut signal_keys = Vec::new();
    let mut filter_keys = Vec::new();
    for (key, config) in configs {
        if !config_enabled(config) {
            continue;
        }
        if config_is_filter(config) {
            filter_keys.push(key.clone());
        } else {
            signal_keys.push(key.clone());
        }
    }
    if signal_keys.is_empty() {
        return Vec::new();
    }

    let mode_default = default_config_choice(PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES, "current");
    let logic_default = default_config_choice(PYTHON_LOGIC_CONFIG_CHOICES, "AND");
    let mode = normalize_config_choice(mode, PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES, &mode_default);
    let logic = normalize_config_choice(logic, PYTHON_LOGIC_CONFIG_CHOICES, &logic_default);
    let mut signal_groups = Vec::new();
    match mode.as_str() {
        "current" => {
            if logic.eq_ignore_ascii_case("SEPARATE") {
                signal_groups.extend(signal_keys.iter().map(|key| vec![key.clone()]));
            } else {
                signal_groups.push(signal_keys);
            }
        }
        "single" => {
            signal_groups.extend(signal_keys.iter().map(|key| vec![key.clone()]));
        }
        "pairs" => {
            let mut current = Vec::new();
            append_combinations(&signal_keys, 2, 0, &mut current, &mut signal_groups);
        }
        _ => {
            let maximum = combo_size.clamp(1, signal_keys.len());
            for size in 1..=maximum {
                let mut current = Vec::new();
                append_combinations(&signal_keys, size, 0, &mut current, &mut signal_groups);
            }
        }
    }
    signal_groups
        .iter()
        .map(|group| with_filters(group, &filter_keys))
        .collect()
}

fn saturating_multiply(left: u64, right: u64) -> u64 {
    left.checked_mul(right).unwrap_or(u64::MAX)
}

pub fn estimate_run_count(
    symbol_count: usize,
    interval_count: usize,
    indicator_group_count: usize,
) -> u64 {
    saturating_multiply(
        saturating_multiply(symbol_count as u64, interval_count as u64),
        indicator_group_count as u64,
    )
}

fn json_text(object: &Value, key: &str, fallback: &str) -> String {
    object
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(fallback)
        .to_owned()
}

fn json_number(object: &Value, key: &str, fallback: f64) -> f64 {
    object
        .get(key)
        .and_then(|value| {
            value
                .as_f64()
                .or_else(|| value.as_str()?.trim().parse::<f64>().ok())
        })
        .unwrap_or(fallback)
}

fn json_bool(object: &Value, key: &str, fallback: bool) -> bool {
    let Some(value) = object.get(key) else {
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

fn merged_pair_controls(entry: &Value) -> Value {
    let mut controls = entry
        .get("strategy_controls")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    for key in [
        "logic",
        "capital",
        "side",
        "position_pct",
        "position_pct_units",
        "margin_mode",
        "position_mode",
        "assets_mode",
        "account_mode",
        "mdd_logic",
        "leverage",
        "stop_loss_enabled",
        "stop_loss_mode",
        "stop_loss_usdt",
        "stop_loss_percent",
        "stop_loss_scope",
    ] {
        if let Some(value) = entry.get(key).filter(|value| !value.is_null()) {
            controls.insert(key.to_owned(), value.clone());
        }
    }
    if let Some(stop_loss) = entry.get("stop_loss").filter(|value| value.is_object()) {
        controls.insert("stop_loss".to_owned(), stop_loss.clone());
    }
    Value::Object(controls)
}

fn normalized_indicator_keys(entry: &Value) -> Vec<String> {
    let mut keys = entry
        .get("indicators")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    keys.sort();
    keys.dedup();
    keys
}

fn resolve_indicator_bundle(
    active_configs: &BTreeMap<String, Value>,
    override_keys: &[String],
) -> BTreeMap<String, Value> {
    if override_keys.is_empty() {
        return active_configs.clone();
    }
    let override_key_set = override_keys.iter().cloned().collect::<BTreeSet<_>>();
    let mut resolved = BTreeMap::new();
    for key in override_keys {
        if let Some(config) = active_configs.get(key) {
            let mut config = config.clone();
            if let Some(object) = config.as_object_mut() {
                object.insert("enabled".to_owned(), Value::Bool(true));
            }
            resolved.insert(key.clone(), config);
        }
    }
    for (key, config) in active_configs {
        if !override_key_set.contains(key) && config_enabled(config) && config_is_filter(config) {
            resolved.insert(key.clone(), config.clone());
        }
    }
    if resolved.is_empty() {
        active_configs.clone()
    } else {
        resolved
    }
}

fn apply_pair_controls(
    mut request: NativeBacktestRequest,
    controls: &Value,
) -> NativeBacktestRequest {
    let logic = normalize_config_choice(
        &json_text(controls, "logic", ""),
        PYTHON_LOGIC_CONFIG_CHOICES,
        "",
    );
    if !logic.is_empty() {
        request.logic = logic;
    }
    let capital = json_number(controls, "capital", -1.0);
    if capital > 0.0 && capital.is_finite() {
        request.capital = capital;
    }
    let side = normalize_config_choice(
        &json_text(controls, "side", ""),
        PYTHON_SIDE_CONFIG_CHOICES,
        "",
    );
    if !side.is_empty() {
        request.side = side;
    }
    let position_pct = json_number(controls, "position_pct", -1.0);
    if position_pct > 0.0 && position_pct.is_finite() {
        request.position_pct = position_pct;
    }
    let position_pct_units = json_text(controls, "position_pct_units", "");
    if !position_pct_units.is_empty() {
        request.position_pct_units = position_pct_units;
    }
    let leverage = json_number(controls, "leverage", -1.0);
    if leverage > 0.0 && leverage.is_finite() {
        request.leverage = leverage.max(1.0);
    }
    for (target, key) in [
        (&mut request.margin_mode, "margin_mode"),
        (&mut request.position_mode, "position_mode"),
        (&mut request.assets_mode, "assets_mode"),
        (&mut request.account_mode, "account_mode"),
    ] {
        let value = json_text(controls, key, "");
        if !value.is_empty() {
            *target = value;
        }
    }
    let mdd_logic = normalize_config_choice(
        &json_text(controls, "mdd_logic", ""),
        crate::generated_python_parity::PYTHON_MDD_LOGIC_CONFIG_CHOICES,
        "",
    );
    if !mdd_logic.is_empty() {
        request.mdd_logic = mdd_logic;
    }

    let mut stop_loss = controls
        .get("stop_loss")
        .filter(|value| value.is_object())
        .cloned()
        .unwrap_or_else(|| json!({}));
    if let Some(object) = stop_loss.as_object_mut() {
        for (control_key, stop_key) in [
            ("stop_loss_enabled", "enabled"),
            ("stop_loss_mode", "mode"),
            ("stop_loss_usdt", "usdt"),
            ("stop_loss_percent", "percent"),
            ("stop_loss_scope", "scope"),
        ] {
            if let Some(value) = controls.get(control_key) {
                object.insert(stop_key.to_owned(), value.clone());
            }
        }
    }
    if stop_loss
        .as_object()
        .is_some_and(|object| !object.is_empty())
    {
        request.stop_loss_enabled = json_bool(&stop_loss, "enabled", request.stop_loss_enabled);
        let stop_loss_mode = normalize_config_choice(
            &json_text(&stop_loss, "mode", ""),
            PYTHON_STOP_LOSS_MODE_CONFIG_CHOICES,
            "",
        );
        if !stop_loss_mode.is_empty() {
            request.stop_loss_mode = stop_loss_mode;
        }
        request.stop_loss_usdt = json_number(&stop_loss, "usdt", request.stop_loss_usdt).max(0.0);
        request.stop_loss_percent =
            json_number(&stop_loss, "percent", request.stop_loss_percent).max(0.0);
        let stop_loss_scope = normalize_config_choice(
            &json_text(&stop_loss, "scope", ""),
            PYTHON_STOP_LOSS_SCOPE_CONFIG_CHOICES,
            "",
        );
        if !stop_loss_scope.is_empty() {
            request.stop_loss_scope = stop_loss_scope;
        }
    }
    request
}

fn strategy_controls(request: &NativeBacktestRequest) -> Value {
    json!({
        "logic": request.logic,
        "capital": request.capital,
        "side": request.side,
        "position_pct": request.position_pct,
        "position_pct_units": request.position_pct_units,
        "leverage": request.leverage,
        "margin_mode": request.margin_mode,
        "position_mode": request.position_mode,
        "assets_mode": request.assets_mode,
        "account_mode": request.account_mode,
        "mdd_logic": request.mdd_logic,
        "stop_loss": {
            "enabled": request.stop_loss_enabled,
            "mode": request.stop_loss_mode,
            "usdt": request.stop_loss_usdt,
            "percent": request.stop_loss_percent,
            "scope": request.stop_loss_scope,
        },
    })
}

fn build_override_plans(request: &NativeBacktestBatchRequest) -> OverridePlanSet {
    let mut result = OverridePlanSet::default();
    let mut seen = BTreeSet::new();
    for entry in &request.pair_overrides {
        if !entry.is_object() {
            continue;
        }
        let symbol = json_text(entry, "symbol", "").to_ascii_uppercase();
        let interval =
            normalize_backtest_interval(Some(&Value::String(json_text(entry, "interval", ""))));
        if symbol.is_empty() || interval.is_empty() {
            continue;
        }
        let override_keys = normalized_indicator_keys(entry);
        let dedupe_key = format!(
            "{symbol}\u{1f}{interval}\u{1f}{}",
            override_keys.join("\u{1e}")
        );
        if !seen.insert(dedupe_key) {
            continue;
        }
        result.has_valid_overrides = true;
        let controls = merged_pair_controls(entry);
        let run_template = apply_pair_controls(request.run_template.clone(), &controls);
        let bundle = resolve_indicator_bundle(&request.indicator_configs, &override_keys);
        let groups = build_indicator_groups(
            &bundle,
            "current",
            request.optimizer_combo_size,
            &run_template.logic,
        );
        let reported_logic = normalize_config_choice(
            &run_template.logic,
            PYTHON_LOGIC_CONFIG_CHOICES,
            &default_config_choice(PYTHON_LOGIC_CONFIG_CHOICES, "AND"),
        );
        let separate_logic =
            normalize_config_choice("SEPARATE", PYTHON_LOGIC_CONFIG_CHOICES, "SEPARATE");
        let and_logic = normalize_config_choice("AND", PYTHON_LOGIC_CONFIG_CHOICES, "AND");
        let effective_logic = if reported_logic.eq_ignore_ascii_case(&separate_logic) {
            and_logic
        } else {
            reported_logic.clone()
        };
        for group in groups {
            let mut effective_template = run_template.clone();
            effective_template.logic = effective_logic.clone();
            let loop_interval_override = json_text(
                entry,
                "loop_interval_override",
                &json_text(
                    &controls,
                    "loop_interval_override",
                    &request.loop_interval_override,
                ),
            );
            let connector_backend = json_text(
                entry,
                "connector_backend",
                &json_text(&controls, "connector_backend", &request.connector_backend),
            );
            result.plans.push(OverridePlan {
                symbol: symbol.clone(),
                interval: interval.clone(),
                indicator_keys: group,
                run_template: effective_template,
                reported_logic: reported_logic.clone(),
                loop_interval_override,
                connector_backend,
            });
        }
    }
    result
}

fn normalized_optimizer_metric(metric: &str) -> String {
    let default_metric =
        default_config_choice(PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES, "roi_percent");
    normalize_config_choice(
        metric,
        PYTHON_OPTIMIZER_METRIC_CONFIG_CHOICES,
        &default_metric,
    )
}

pub fn optimizer_score(
    result: &NativeBacktestResult,
    metric: &str,
    mdd_limit: f64,
    min_trades: usize,
) -> OptimizerScore {
    let mut reasons = Vec::new();
    if result.trades < min_trades {
        reasons.push(format!("trades {} < {min_trades}", result.trades));
    }
    let limit = mdd_limit.max(0.0);
    if limit > 0.0 && result.max_drawdown_percent > limit {
        reasons.push(format!(
            "MDD {:.2}% > {:.2}%",
            result.max_drawdown_percent, limit
        ));
    }
    if !reasons.is_empty() {
        return OptimizerScore {
            eligible: false,
            values: Vec::new(),
            rejection_reason: reasons.join("; "),
        };
    }
    let values = optimizer_score_values(
        result.roi_value,
        result.roi_percent,
        result.trades,
        result.max_drawdown_percent,
        metric,
    );
    OptimizerScore {
        eligible: true,
        values,
        rejection_reason: String::new(),
    }
}

fn optimizer_score_values(
    roi_value: f64,
    roi_percent: f64,
    trades: usize,
    max_drawdown_percent: f64,
    metric: &str,
) -> Vec<f64> {
    match normalized_optimizer_metric(metric).as_str() {
        "roi_value" => vec![roi_value, roi_percent, trades as f64, -max_drawdown_percent],
        "roi_drawdown" => vec![
            roi_percent / max_drawdown_percent.abs().max(1.0),
            roi_percent,
            roi_value,
            trades as f64,
            -max_drawdown_percent,
        ],
        _ => vec![roi_percent, roi_value, trades as f64, -max_drawdown_percent],
    }
}

fn optimizer_score_from_row(
    row: &Value,
    metric: &str,
    mdd_limit: f64,
    min_trades: usize,
) -> OptimizerScore {
    let trades = json_number(row, "trades", 0.0).max(0.0).floor() as usize;
    let max_drawdown_percent = json_number(row, "max_drawdown_percent", 0.0);
    let explicitly_eligible = json_bool(row, "optimizer_eligible", true);
    let mut reasons = Vec::new();
    if trades < min_trades {
        reasons.push(format!("trades {} < {min_trades}", trades));
    }
    let limit = mdd_limit.max(0.0);
    if limit > 0.0 && max_drawdown_percent > limit {
        reasons.push(format!("MDD {:.2}% > {:.2}%", max_drawdown_percent, limit));
    }
    if !explicitly_eligible {
        let stored_reason = json_text(
            row,
            "optimizer_rejection_reason",
            "prior optimizer rejection",
        );
        reasons.push(stored_reason);
    }
    if !reasons.is_empty() {
        return OptimizerScore {
            eligible: false,
            values: Vec::new(),
            rejection_reason: reasons.join("; "),
        };
    }
    OptimizerScore {
        eligible: true,
        values: optimizer_score_values(
            json_number(row, "roi_value", 0.0),
            json_number(row, "roi_percent", 0.0),
            trades,
            max_drawdown_percent,
            metric,
        ),
        rejection_reason: String::new(),
    }
}

fn compare_scores(left: &[f64], right: &[f64]) -> Ordering {
    for (left, right) in left.iter().zip(right) {
        let ordering = left.partial_cmp(right).unwrap_or(Ordering::Equal);
        if ordering != Ordering::Equal {
            return ordering;
        }
    }
    left.len().cmp(&right.len())
}

fn unique_symbols(values: &[String]) -> Vec<String> {
    let mut output = Vec::new();
    for value in values {
        let normalized = value.trim().to_ascii_uppercase();
        if !normalized.is_empty() && !output.contains(&normalized) {
            output.push(normalized);
        }
    }
    output
}

fn unique_intervals(values: &[String]) -> Vec<String> {
    let mut output = Vec::new();
    for value in values {
        let normalized = normalize_backtest_interval(Some(&Value::String(value.clone())));
        if !normalized.is_empty() && !output.contains(&normalized) {
            output.push(normalized);
        }
    }
    output
}

fn insert_snapshot_fields(snapshot: &mut Map<String, Value>, request: &NativeBacktestBatchRequest) {
    snapshot.insert(
        "source".to_owned(),
        Value::String("native-rust-backtest".to_owned()),
    );
    snapshot.insert("state".to_owned(), Value::String("starting".to_owned()));
    snapshot.insert("cancelled".to_owned(), Value::Bool(false));
    snapshot.insert(
        "optimizer_scope".to_owned(),
        Value::String(request.optimizer_scope.clone()),
    );
    snapshot.insert(
        "optimizer_enabled".to_owned(),
        Value::Bool(request.optimizer_enabled),
    );
    snapshot.insert(
        "optimizer_max_duration_seconds".to_owned(),
        json!(request.optimizer_max_duration_seconds),
    );
    snapshot.insert("scan_top_n".to_owned(), json!(request.scan_top_n));
    snapshot.insert(
        "resume_checkpoint".to_owned(),
        json!(request.resume_combo_offset > 0 || !request.resume_prior_runs.is_empty()),
    );
    snapshot.insert(
        "selected_exchange".to_owned(),
        json!(request.selected_exchange),
    );
}

pub fn run_native_backtest_batch<F, S>(
    request: &NativeBacktestBatchRequest,
    mut load_candles: F,
    mut should_stop: S,
) -> Value
where
    F: FnMut(&str, &str) -> CandleLoadResult,
    S: FnMut() -> bool,
{
    let mut snapshot = Map::new();
    insert_snapshot_fields(&mut snapshot, request);
    let symbols = unique_symbols(&request.symbols);
    let intervals = unique_intervals(&request.intervals);
    let groups = build_indicator_groups(
        &request.indicator_configs,
        &request.optimizer_mode,
        request.optimizer_combo_size,
        &request.run_template.logic,
    );
    let override_plans = build_override_plans(request);
    let (planned_symbols, planned_intervals) = if override_plans.has_valid_overrides {
        (
            unique_symbols(
                &override_plans
                    .plans
                    .iter()
                    .map(|plan| plan.symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            unique_intervals(
                &override_plans
                    .plans
                    .iter()
                    .map(|plan| plan.interval.clone())
                    .collect::<Vec<_>>(),
            ),
        )
    } else {
        (symbols.clone(), intervals.clone())
    };
    let run_count = if override_plans.has_valid_overrides {
        override_plans.plans.len() as u64
    } else {
        estimate_run_count(symbols.len(), intervals.len(), groups.len())
    };
    let resume_combo_offset = request.resume_combo_offset.min(run_count);
    let optimizer_deadline =
        if request.optimizer_enabled && request.optimizer_max_duration_seconds > 0 {
            Some(Instant::now() + Duration::from_secs(request.optimizer_max_duration_seconds))
        } else {
            None
        };
    snapshot.insert("optimizer_run_count".to_owned(), json!(run_count));
    snapshot.insert(
        "indicator_group_count".to_owned(),
        json!(if override_plans.has_valid_overrides {
            override_plans.plans.len()
        } else {
            groups.len()
        }),
    );
    snapshot.insert("symbol_count".to_owned(), json!(planned_symbols.len()));
    snapshot.insert("interval_count".to_owned(), json!(planned_intervals.len()));
    snapshot.insert(
        "pair_override_count".to_owned(),
        json!(if override_plans.has_valid_overrides {
            override_plans.plans.len()
        } else {
            0
        }),
    );

    if !override_plans.has_valid_overrides && (symbols.is_empty() || intervals.is_empty()) {
        snapshot.insert("state".to_owned(), json!("failed"));
        snapshot.insert(
            "status_message".to_owned(),
            json!("Select at least one symbol and interval."),
        );
        return Value::Object(snapshot);
    }
    if (override_plans.has_valid_overrides && override_plans.plans.is_empty())
        || (!override_plans.has_valid_overrides && groups.is_empty())
    {
        snapshot.insert("state".to_owned(), json!("failed"));
        snapshot.insert(
            "status_message".to_owned(),
            json!(
                "Optimizer mode needs enabled signal indicators for the selected combination type."
            ),
        );
        return Value::Object(snapshot);
    }
    if run_count > request.max_run_count.max(1) {
        snapshot.insert("state".to_owned(), json!("failed"));
        snapshot.insert(
            "status_message".to_owned(),
            json!(format!(
                "Estimated optimizer runs {run_count} exceed the native hard cap {}.",
                request.max_run_count.max(1)
            )),
        );
        return Value::Object(snapshot);
    }

    let result_limit = request.result_limit.max(1);
    let metric = normalized_optimizer_metric(&request.optimizer_metric);
    let mode_default = default_config_choice(PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES, "current");
    let scope_default = default_config_choice(PYTHON_SCAN_SCOPE_CONFIG_CHOICES, "selected");
    let mode = normalize_config_choice(
        &request.optimizer_mode,
        PYTHON_OPTIMIZER_MODE_CONFIG_CHOICES,
        &mode_default,
    );
    let scope = normalize_config_choice(
        &request.optimizer_scope,
        PYTHON_SCAN_SCOPE_CONFIG_CHOICES,
        &scope_default,
    );
    let separate_logic =
        normalize_config_choice("SEPARATE", PYTHON_LOGIC_CONFIG_CHOICES, "SEPARATE");
    let and_logic = normalize_config_choice("AND", PYTHON_LOGIC_CONFIG_CHOICES, "AND");
    let reported_logic = normalize_config_choice(
        &request.run_template.logic,
        PYTHON_LOGIC_CONFIG_CHOICES,
        &default_config_choice(PYTHON_LOGIC_CONFIG_CHOICES, "AND"),
    );
    let effective_logic = if reported_logic.eq_ignore_ascii_case(&separate_logic) {
        and_logic
    } else {
        reported_logic.clone()
    };
    let mut eligible_rows = Vec::new();
    let mut rejected_samples = Vec::new();
    let mut plain_rows = Vec::new();
    let mut errors = request.resume_prior_errors.clone();
    let mut candle_cache: BTreeMap<(String, String), CandleLoadResult> = BTreeMap::new();
    let mut processed_count = 0_u64;
    let mut cancelled = false;
    let mut budget_exhausted = false;
    let mut completed_combo_count = resume_combo_offset;

    let mut prior_candidate_count = 0_u64;
    let mut prior_eligible_count = 0_u64;
    let mut prior_filtered_count = 0_u64;
    for (index, row) in request.resume_prior_runs.iter().enumerate() {
        prior_candidate_count = prior_candidate_count.max(
            json_number(row, "optimizer_candidate_count", 0.0)
                .max(0.0)
                .floor() as u64,
        );
        prior_eligible_count = prior_eligible_count.max(
            json_number(row, "optimizer_eligible_count", 0.0)
                .max(0.0)
                .floor() as u64,
        );
        prior_filtered_count = prior_filtered_count.max(
            json_number(row, "optimizer_filtered_count", 0.0)
                .max(0.0)
                .floor() as u64,
        );
        if request.optimizer_enabled {
            let score = optimizer_score_from_row(
                row,
                &metric,
                request.optimizer_mdd_limit,
                request.optimizer_min_trades,
            );
            if score.eligible {
                eligible_rows.push(RankedRow {
                    score: score.values,
                    original_index: index as u64,
                    row: row.clone(),
                });
            } else if rejected_samples.len() < result_limit {
                rejected_samples.push(row.clone());
            }
        } else {
            plain_rows.push(row.clone());
        }
    }
    let mut candidate_count = prior_candidate_count.max(request.resume_prior_runs.len() as u64);
    let mut eligible_count = prior_eligible_count.max(eligible_rows.len() as u64);
    let mut filtered_count = prior_filtered_count.max(
        request
            .resume_prior_runs
            .iter()
            .filter(|row| !json_bool(row, "optimizer_eligible", true))
            .count() as u64,
    );

    let mut process_run = |symbol: &str,
                           interval: &str,
                           group: &[String],
                           mut run_template: NativeBacktestRequest,
                           reported_logic: &str,
                           loop_interval_override: &str,
                           connector_backend: &str|
     -> bool {
        if should_stop() {
            cancelled = true;
            return false;
        }
        if optimizer_deadline.is_some_and(|deadline| Instant::now() >= deadline) {
            budget_exhausted = true;
            return false;
        }
        let cache_key = (symbol.to_owned(), interval.to_owned());
        let loaded = if let Some(loaded) = candle_cache.get(&cache_key) {
            loaded.clone()
        } else {
            let loaded = load_candles(symbol, interval);
            candle_cache.insert(cache_key.clone(), loaded.clone());
            loaded
        };
        if !loaded.ok {
            if should_stop() || loaded.error == "backtest_cancelled" {
                cancelled = true;
                return false;
            }
            errors.push(json!({
                "symbol": symbol,
                "interval": interval,
                "indicator_keys": group,
                "error": loaded.error,
            }));
            processed_count += 1;
            return true;
        }

        run_template.symbol = symbol.to_owned();
        run_template.interval = interval.to_owned();
        run_template.indicators = group
            .iter()
            .filter_map(|key| {
                request.indicator_configs.get(key).map(|config| {
                    let mut config = config.clone();
                    if let Some(object) = config.as_object_mut() {
                        object.insert("enabled".to_owned(), Value::Bool(true));
                    }
                    (key.clone(), config)
                })
            })
            .collect();
        let result = run_native_backtest_with_cancel_and_window(
            &loaded.candles,
            &run_template,
            request.start_ms,
            request.end_ms,
            &mut should_stop,
        );
        processed_count += 1;
        if !result.ok {
            if result.error == "backtest_cancelled" || should_stop() {
                cancelled = true;
                return false;
            }
            errors.push(json!({
                "symbol": symbol,
                "interval": interval,
                "indicator_keys": group,
                "error": result.error,
            }));
            return true;
        }

        let mut row = result.to_json();
        let row_object = row
            .as_object_mut()
            .expect("native backtest result must serialize to an object");
        row_object.insert("logic".to_owned(), json!(reported_logic));
        row_object.insert("start".to_owned(), json!(request.start_display));
        row_object.insert("end".to_owned(), json!(request.end_display));
        row_object.insert(
            "loop_interval_override".to_owned(),
            json!(loop_interval_override),
        );
        row_object.insert("connector_backend".to_owned(), json!(connector_backend));
        let mut controls = strategy_controls(&run_template);
        if let Some(controls_object) = controls.as_object_mut() {
            controls_object.insert("logic".to_owned(), json!(reported_logic));
        }
        row_object.insert("strategy_controls".to_owned(), controls);
        if !request.optimizer_enabled {
            candidate_count += 1;
            eligible_count += 1;
            plain_rows.push(row);
            return true;
        }

        let score = optimizer_score(
            &result,
            &metric,
            request.optimizer_mdd_limit,
            request.optimizer_min_trades,
        );
        row_object.insert("optimizer_metric".to_owned(), json!(metric));
        row_object.insert("optimizer_mode".to_owned(), json!(mode));
        row_object.insert("optimizer_scope".to_owned(), json!(scope));
        row_object.insert(
            "optimizer_mdd_limit".to_owned(),
            json!(request.optimizer_mdd_limit),
        );
        row_object.insert(
            "optimizer_min_trades".to_owned(),
            json!(request.optimizer_min_trades),
        );
        row_object.insert("optimizer_eligible".to_owned(), json!(score.eligible));
        row_object.insert(
            "optimizer_primary_score".to_owned(),
            score
                .values
                .first()
                .map_or(Value::Null, |value| json!(value)),
        );
        row_object.insert(
            "optimizer_rejection_reason".to_owned(),
            json!(score.rejection_reason),
        );
        let original_index = candidate_count;
        candidate_count += 1;
        if score.eligible {
            eligible_count += 1;
            eligible_rows.push(RankedRow {
                score: score.values,
                original_index,
                row,
            });
        } else {
            filtered_count += 1;
            if rejected_samples.len() < result_limit {
                rejected_samples.push(row);
            }
        }
        true
    };

    snapshot.insert("state".to_owned(), json!("running"));
    if override_plans.has_valid_overrides {
        for (combo_index, plan) in override_plans.plans.iter().enumerate() {
            let combo_index = combo_index as u64;
            if combo_index < resume_combo_offset {
                continue;
            }
            if !process_run(
                &plan.symbol,
                &plan.interval,
                &plan.indicator_keys,
                plan.run_template.clone(),
                &plan.reported_logic,
                &plan.loop_interval_override,
                &plan.connector_backend,
            ) {
                break;
            }
            completed_combo_count = combo_index + 1;
        }
    } else {
        let mut combo_index = 0_u64;
        'outer: for symbol in &symbols {
            for interval in &intervals {
                for group in &groups {
                    if combo_index < resume_combo_offset {
                        combo_index += 1;
                        continue;
                    }
                    let mut run_template = request.run_template.clone();
                    run_template.logic = effective_logic.clone();
                    if !process_run(
                        symbol,
                        interval,
                        group,
                        run_template,
                        &reported_logic,
                        &request.loop_interval_override,
                        &request.connector_backend,
                    ) {
                        break 'outer;
                    }
                    completed_combo_count = combo_index + 1;
                    combo_index += 1;
                }
            }
        }
    }

    eligible_rows.sort_by(|left, right| {
        compare_scores(&right.score, &left.score)
            .then_with(|| left.original_index.cmp(&right.original_index))
    });
    if eligible_rows.len() > result_limit {
        eligible_rows.truncate(result_limit);
    }
    let mut final_rows = if !request.optimizer_enabled {
        if plain_rows.len() > result_limit {
            plain_rows.truncate(result_limit);
        }
        plain_rows
    } else if eligible_rows.is_empty() {
        rejected_samples
    } else {
        eligible_rows.into_iter().map(|ranked| ranked.row).collect()
    };
    for (index, row) in final_rows.iter_mut().enumerate() {
        if request.optimizer_enabled && !eligible_count.eq(&0) {
            row.as_object_mut()
                .expect("row must be object")
                .insert("optimizer_rank".to_owned(), json!(index + 1));
        } else if request.optimizer_enabled {
            row.as_object_mut()
                .expect("row must be object")
                .insert("optimizer_rank".to_owned(), Value::Null);
        }
        if request.optimizer_enabled {
            let object = row.as_object_mut().expect("row must be object");
            object.insert(
                "optimizer_candidate_count".to_owned(),
                json!(candidate_count),
            );
            object.insert("optimizer_eligible_count".to_owned(), json!(eligible_count));
            object.insert("optimizer_filtered_count".to_owned(), json!(filtered_count));
            object.insert("optimizer_run_count".to_owned(), json!(run_count));
        }
    }
    if budget_exhausted {
        errors.push(json!({
            "error": "backtest_optimizer_time_budget_exhausted",
            "processed_runs": processed_count,
            "max_duration_seconds": request.optimizer_max_duration_seconds,
        }));
    }
    let progress_percent = if run_count > 0 {
        (completed_combo_count as f64 / run_count as f64 * 100.0).min(100.0)
    } else {
        100.0
    };
    snapshot.insert("runs".to_owned(), Value::Array(final_rows.clone()));
    snapshot.insert("top_runs".to_owned(), Value::Array(final_rows.clone()));
    if let Some(top_run) = final_rows.first() {
        snapshot.insert("top_run".to_owned(), top_run.clone());
    }
    snapshot.insert("errors".to_owned(), Value::Array(errors));
    snapshot.insert("processed_count".to_owned(), json!(completed_combo_count));
    snapshot.insert(
        "completed_combo_count".to_owned(),
        json!(completed_combo_count),
    );
    snapshot.insert(
        "optimizer_candidate_count".to_owned(),
        json!(candidate_count),
    );
    snapshot.insert("optimizer_eligible_count".to_owned(), json!(eligible_count));
    snapshot.insert("optimizer_filtered_count".to_owned(), json!(filtered_count));
    snapshot.insert("progress_percent".to_owned(), json!(progress_percent));
    if cancelled {
        snapshot.insert("state".to_owned(), json!("cancelled"));
        snapshot.insert("cancelled".to_owned(), json!(true));
        snapshot.insert(
            "status_message".to_owned(),
            json!(format!(
                "Native Rust backtest cancelled after {completed_combo_count} of {run_count} run(s)."
            )),
        );
    } else if budget_exhausted {
        snapshot.insert("state".to_owned(), json!("budget_exhausted"));
        snapshot.insert("cancelled".to_owned(), json!(false));
        snapshot.insert(
            "status_message".to_owned(),
            json!(format!(
                "Native Rust optimizer time budget reached after {completed_combo_count} of {run_count} run(s). A checkpoint is available for resume."
            )),
        );
    } else if candidate_count == 0
        && snapshot["errors"]
            .as_array()
            .is_some_and(|errors| !errors.is_empty())
    {
        snapshot.insert("state".to_owned(), json!("failed"));
        snapshot.insert(
            "status_message".to_owned(),
            json!(format!(
                "Native Rust backtest produced no valid runs; {} error(s).",
                snapshot["errors"].as_array().map_or(0, Vec::len)
            )),
        );
    } else {
        snapshot.insert("state".to_owned(), json!("completed"));
        snapshot.insert("progress_percent".to_owned(), json!(100.0));
        snapshot.insert(
            "status_message".to_owned(),
            json!(format!(
                "Native Rust backtest completed {completed_combo_count} run(s); {eligible_count} eligible, {filtered_count} filtered, {} error(s).",
                snapshot["errors"].as_array().map_or(0, Vec::len)
            )),
        );
    }
    Value::Object(snapshot)
}

pub fn run_native_backtest_batch_without_cancel<F>(
    request: &NativeBacktestBatchRequest,
    load_candles: F,
) -> Value
where
    F: FnMut(&str, &str) -> CandleLoadResult,
{
    run_native_backtest_batch(request, load_candles, || false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::generated_python_indicator_reference::PYTHON_INDICATOR_REFERENCE_JSON;
    use crate::generated_python_parity::{
        PYTHON_DEFAULT_BACKTEST_JSON, PYTHON_DEFAULT_EXECUTION_JSON,
    };

    fn candles_from_value(value: &Value) -> Vec<BinanceKlineCandle> {
        value
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .map(|(index, candle)| BinanceKlineCandle {
                open_time_ms: index as i64 * 60_000,
                open: candle["open"].as_f64().unwrap(),
                high: candle["high"].as_f64().unwrap(),
                low: candle["low"].as_f64().unwrap(),
                close: candle["close"].as_f64().unwrap(),
                volume: candle["volume"].as_f64().unwrap(),
            })
            .collect()
    }

    fn fixture_candles() -> Vec<BinanceKlineCandle> {
        let reference: Value = serde_json::from_str(PYTHON_INDICATOR_REFERENCE_JSON).unwrap();
        candles_from_value(&reference["candles"])
    }

    fn fixture_case(fixture_name: &str) -> Value {
        let reference: Value = serde_json::from_str(PYTHON_INDICATOR_REFERENCE_JSON).unwrap();
        reference["backtest_cases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|case| {
                case["fixture_name"].as_str() == Some(fixture_name)
                    && case["name"] == "rsi-per-trade-both"
            })
            .cloned()
            .unwrap_or_else(|| panic!("missing generated backtest fixture {fixture_name}"))
    }

    #[test]
    fn native_batch_defaults_match_python_backtest_and_execution_contracts() {
        let python_backtest: Value = serde_json::from_str(PYTHON_DEFAULT_BACKTEST_JSON)
            .expect("generated Python backtest defaults must be valid JSON");
        let python_execution: Value = serde_json::from_str(PYTHON_DEFAULT_EXECUTION_JSON)
            .expect("generated Python execution defaults must be valid JSON");
        let request = NativeBacktestBatchRequest::default();
        assert_eq!(
            request.optimizer_mode,
            python_backtest["optimizer_mode"].as_str().unwrap()
        );
        assert_eq!(
            request.optimizer_metric,
            python_backtest["optimizer_metric"].as_str().unwrap()
        );
        assert_eq!(
            request.optimizer_scope,
            python_backtest["scan_scope"].as_str().unwrap()
        );
        assert_eq!(
            request.optimizer_combo_size,
            python_backtest["optimizer_combo_size"].as_u64().unwrap() as usize
        );
        assert_eq!(
            request.optimizer_min_trades,
            python_backtest["optimizer_min_trades"].as_u64().unwrap() as usize
        );
        assert_eq!(
            request.optimizer_mdd_limit,
            python_backtest["scan_mdd_limit"].as_f64().unwrap()
        );
        assert_eq!(
            request.optimizer_max_duration_seconds,
            python_backtest["optimizer_max_duration_seconds"]
                .as_u64()
                .unwrap()
        );
        assert_eq!(
            request.loop_interval_override,
            python_execution["loop_interval_override"].as_str().unwrap()
        );
        assert_eq!(
            request.connector_backend,
            python_backtest["connector_backend"].as_str().unwrap()
        );
        assert_eq!(request.selected_exchange, "Binance");
        assert_eq!(request.symbols, ["BTCUSDT"]);
        assert_eq!(request.intervals, ["1h"]);
        assert_eq!(request.indicator_configs["rsi"]["enabled"], true);
    }

    #[test]
    fn native_batch_request_normalizes_python_interval_aliases() {
        let payload = json!({
            "symbols": ["btcusdt"],
            "intervals": ["60 minutes", "1H", "1M", "20 minutes", "3 hours"],
            "indicators": {"rsi": {"enabled": true}},
            "start": "2026-01-01",
            "end": "2026-02-01"
        });
        let request = NativeBacktestBatchRequest::from_python_request(&payload)
            .expect("Python-shaped request should parse");
        assert_eq!(request.intervals, ["1h", "1mo", "20m", "3h"]);

        let mut override_request = NativeBacktestBatchRequest::default();
        override_request.pair_overrides = vec![json!({
            "symbol": "btcusdt",
            "interval": "60 minutes",
            "indicators": ["rsi"]
        })];
        let plans = build_override_plans(&override_request);
        assert!(plans.has_valid_overrides);
        assert_eq!(plans.plans[0].interval, "1h");
    }

    #[test]
    fn indicator_groups_preserve_python_filter_and_optimizer_modes() {
        let configs = BTreeMap::from([
            ("rsi".to_owned(), json!({"enabled": true})),
            ("ema".to_owned(), json!({"enabled": true})),
            (
                "rvol".to_owned(),
                json!({"enabled": true, "signal_role": "filter"}),
            ),
        ]);
        assert_eq!(
            build_indicator_groups(&configs, "current", 2, "AND"),
            vec![vec!["ema".to_owned(), "rsi".to_owned(), "rvol".to_owned()]]
        );
        assert_eq!(
            build_indicator_groups(&configs, "single", 2, "OR"),
            vec![
                vec!["ema".to_owned(), "rvol".to_owned()],
                vec!["rsi".to_owned(), "rvol".to_owned()]
            ]
        );
        assert_eq!(estimate_run_count(2, 3, 4), 24);
    }

    #[test]
    fn native_batch_matches_python_reference_result_and_reuses_candles() {
        for fixture_name in [
            "baseline",
            "reversal-and-flat",
            "parameterized-longer-series",
        ] {
            let test_case = fixture_case(fixture_name);
            let configs = test_case["configs"]
                .as_object()
                .unwrap()
                .iter()
                .map(|(key, value)| (key.clone(), value.clone()))
                .collect();
            let request = NativeBacktestBatchRequest {
                symbols: vec!["BTCUSDT".to_owned(), "BTCUSDT".to_owned()],
                intervals: vec!["1m".to_owned()],
                indicator_configs: configs,
                run_template: NativeBacktestRequest {
                    logic: "OR".to_owned(),
                    side: "BOTH".to_owned(),
                    capital: 1_000.0,
                    position_pct: 25.0,
                    position_pct_units: "percent".to_owned(),
                    leverage: 1.0,
                    fee_bps: 5.0,
                    slippage_bps: 2.0,
                    ..NativeBacktestRequest::default()
                },
                ..NativeBacktestBatchRequest::default()
            };
            let candles = candles_from_value(&test_case["candles"]);
            let mut load_count = 0;
            let snapshot =
                run_native_backtest_batch_without_cancel(&request, |symbol, interval| {
                    assert_eq!(symbol, "BTCUSDT");
                    assert_eq!(interval, "1m");
                    load_count += 1;
                    CandleLoadResult::success(candles.clone())
                });
            assert_eq!(load_count, 1, "batch runs must reuse candles for a pair");
            assert_eq!(
                snapshot["state"], "completed",
                "batch failed for {fixture_name}"
            );
            assert_eq!(snapshot["optimizer_run_count"], 1);
            assert_eq!(snapshot["optimizer_candidate_count"], 1);
            assert_eq!(
                snapshot["top_run"]["trades"], test_case["expected"]["trades"],
                "trade count mismatch for {fixture_name}"
            );
            let expected_roi = test_case["expected"]["roi_percent"].as_f64().unwrap();
            let actual_roi = snapshot["top_run"]["roi_percent"].as_f64().unwrap();
            assert!(
                (actual_roi - expected_roi).abs() <= 1e-9,
                "ROI mismatch for {fixture_name}: expected {expected_roi}, got {actual_roi}"
            );
        }
    }

    #[test]
    fn native_batch_separate_splits_signals_and_preserves_logic_metadata() {
        let request = NativeBacktestBatchRequest {
            symbols: vec!["BTCUSDT".to_owned()],
            intervals: vec!["1m".to_owned()],
            indicator_configs: BTreeMap::from([
                (
                    "ema".to_owned(),
                    json!({
                        "enabled": true,
                        "length": 3,
                        "buy_value": 100.0,
                        "sell_value": 110.0
                    }),
                ),
                (
                    "rsi".to_owned(),
                    json!({
                        "enabled": true,
                        "length": 3,
                        "buy_value": 45.0,
                        "sell_value": 55.0
                    }),
                ),
            ]),
            run_template: NativeBacktestRequest {
                logic: "SEPARATE".to_owned(),
                capital: 1_000.0,
                position_pct: 25.0,
                position_pct_units: "percent".to_owned(),
                ..NativeBacktestRequest::default()
            },
            ..NativeBacktestBatchRequest::default()
        };
        let candles = fixture_candles();
        let snapshot = run_native_backtest_batch_without_cancel(&request, |_, _| {
            CandleLoadResult::success(candles.clone())
        });
        assert_eq!(snapshot["state"], "completed");
        assert_eq!(snapshot["optimizer_run_count"], 2);
        assert_eq!(snapshot["processed_count"], 2);
        let rows = snapshot["top_runs"].as_array().unwrap();
        assert_eq!(rows.len(), 2);
        for row in rows {
            assert_eq!(row["logic"], "SEPARATE");
            assert_eq!(row["strategy_controls"]["logic"], "SEPARATE");
        }
    }

    #[test]
    fn native_batch_pair_overrides_dedupe_and_keep_filters() {
        let request = NativeBacktestBatchRequest {
            indicator_configs: BTreeMap::from([
                (
                    "rsi".to_owned(),
                    json!({"enabled": true, "buy_value": 45.0}),
                ),
                (
                    "rvol".to_owned(),
                    json!({
                        "enabled": true,
                        "signal_role": "filter",
                        "filter_value": 0.5,
                    }),
                ),
            ]),
            pair_overrides: vec![
                json!({
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "indicators": ["rsi"],
                    "capital": 700.0,
                }),
                json!({
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "indicators": ["rsi"],
                    "capital": 700.0,
                }),
            ],
            ..NativeBacktestBatchRequest::default()
        };
        let plans = build_override_plans(&request);
        assert!(plans.has_valid_overrides);
        assert_eq!(plans.plans.len(), 1);
        assert_eq!(plans.plans[0].run_template.capital, 700.0);
        assert!(plans.plans[0].indicator_keys.contains(&"rvol".to_owned()));
    }

    #[test]
    fn native_batch_cancellation_and_optimizer_rejection_are_reported() {
        let request = NativeBacktestBatchRequest {
            symbols: vec!["BTCUSDT".to_owned()],
            intervals: vec!["1m".to_owned()],
            optimizer_enabled: true,
            indicator_configs: BTreeMap::from([(
                "rsi".to_owned(),
                json!({"enabled": true, "buy_value": 45.0}),
            )]),
            optimizer_min_trades: 99,
            ..NativeBacktestBatchRequest::default()
        };
        let candles = fixture_candles();
        let snapshot = run_native_backtest_batch(
            &request,
            |_, _| CandleLoadResult::success(candles.clone()),
            || false,
        );
        assert_eq!(snapshot["state"], "completed");
        assert_eq!(snapshot["optimizer_eligible_count"], 0);
        assert_eq!(snapshot["top_run"]["optimizer_rank"], Value::Null);

        let cancelled = run_native_backtest_batch(
            &request,
            |_, _| CandleLoadResult::success(candles.clone()),
            || true,
        );
        assert_eq!(cancelled["state"], "cancelled");
        assert_eq!(cancelled["cancelled"], true);
    }

    #[test]
    fn python_request_conversion_preserves_dates_warmup_and_controls() {
        let request = NativeBacktestBatchRequest::from_python_request(&json!({
            "symbols": ["btcusdt"],
            "intervals": ["5m"],
            "indicators": {
                "macd": {"enabled": true, "fast": 12, "slow": 26, "signal": 9},
                "rsi": {"enabled": true, "length": 14},
                "ichimoku": {"enabled": false, "span_b_length": 52}
            },
            "logic": "OR",
            "side": "SELL",
            "capital": 2500,
            "position_pct": 25,
            "position_pct_units": "percent",
            "leverage": 7,
            "margin_mode": "Cross",
            "position_mode": "One-way",
            "assets_mode": "Multi-Asset",
            "account_mode": "Portfolio",
            "mdd_logic": "cumulative",
            "fee_bps": 3,
            "slippage_bps": 1,
            "stop_loss": {"enabled": true, "mode": "both", "usdt": 20, "percent": 4, "scope": "cumulative"},
            "optimizer_mode": "pairs",
            "optimizer_metric": "roi_drawdown",
            "scan_scope": "top_n",
            "optimizer_combo_size": 3,
            "optimizer_min_trades": 4,
            "optimizer_max_duration_seconds": 120,
            "scan_mdd_limit": 8,
            "optimizer_result_limit": 17,
            "start": "2024-01-02T03:04:05Z",
            "end": "2024-01-03 03:04:05",
            "loop_interval_override": "15m",
            "connector_backend": "binance-connector",
            "selected_exchange": "Binance",
            "pair_overrides": [{"symbol": "btcusdt", "interval": "5m", "indicators": ["rsi"]}]
        }))
        .expect("Python request should convert");

        assert_eq!(request.symbols, ["btcusdt"]);
        assert_eq!(request.intervals, ["5m"]);
        assert_eq!(request.run_template.logic, "OR");
        assert_eq!(request.run_template.side, "SELL");
        assert_eq!(request.run_template.position_pct, 25.0);
        assert_eq!(request.run_template.position_pct_units, "percent");
        assert_eq!(request.run_template.stop_loss_scope, "cumulative");
        assert!(request.run_template.stop_loss_enabled);
        assert!(!request.optimizer_enabled);
        assert_eq!(request.optimizer_mode, "pairs");
        assert_eq!(request.optimizer_metric, "roi_drawdown");
        assert_eq!(request.optimizer_scope, "top_n");
        assert_eq!(request.optimizer_combo_size, 3);
        assert_eq!(request.optimizer_min_trades, 4);
        assert_eq!(request.optimizer_max_duration_seconds, 0);
        assert_eq!(request.result_limit, 17);
        assert_eq!(request.loop_interval_override, "15m");
        assert_eq!(request.connector_backend, "binance-connector");
        assert_eq!(request.selected_exchange, "Binance");
        assert_eq!(request.start_ms, Some(1_704_164_645_000));
        assert_eq!(request.end_ms, Some(1_704_251_045_000));
        assert_eq!(request.warmup_bars, 26);
    }

    #[test]
    fn python_request_conversion_normalizes_aliases_and_truncates_numeric_controls() {
        let request = NativeBacktestBatchRequest::from_python_request(&json!({
            "symbols": ["btcusdt", "ethusdt"],
            "intervals": ["60 minutes", "1h", "60m"],
            "indicators": {"rsi": {"enabled": true}},
            "logic": "not-a-python-logic",
            "side": "sell",
            "optimizer_mode": "pairs",
            "optimizer_metric": "roi percent mdd",
            "scan_scope": "top n",
            "scan_top_n": 1.9,
            "optimizer_combo_size": 3.9,
            "optimizer_min_trades": 4.9,
            "optimizer_max_duration_seconds": 120.9,
            "optimizer_result_limit": 17.9,
            "resume_combo_offset": 2.9,
            "start": "2026-01-01",
            "end": "2026-01-02"
        }))
        .expect("Python request aliases should convert");

        assert_eq!(request.symbols, ["btcusdt"]);
        assert_eq!(request.intervals, ["1h"]);
        assert_eq!(request.run_template.logic, "AND");
        assert_eq!(request.run_template.side, "SELL");
        assert_eq!(request.optimizer_mode, "pairs");
        assert_eq!(request.optimizer_metric, "roi_percent_mdd");
        assert_eq!(request.optimizer_scope, "top_n");
        assert_eq!(request.scan_top_n, 1);
        assert_eq!(request.optimizer_combo_size, 3);
        assert_eq!(request.optimizer_min_trades, 4);
        assert_eq!(request.optimizer_max_duration_seconds, 120);
        assert_eq!(request.result_limit, 17);
        assert_eq!(request.resume_combo_offset, 2);
    }

    #[test]
    fn python_request_pair_overrides_disable_generated_optimizer_ownership() {
        let request = NativeBacktestBatchRequest::from_python_request(&json!({
            "symbols": ["btcusdt"],
            "intervals": ["1h"],
            "indicators": {"rsi": {"enabled": true}},
            "optimizer_mode": "pairs",
            "optimizer_max_duration_seconds": 120,
            "pair_overrides": [{
                "symbol": "btcusdt",
                "interval": "1h",
                "indicators": ["rsi"]
            }],
            "start": "2026-01-01",
            "end": "2026-01-02"
        }))
        .expect("Python pair-override request should convert");

        assert!(!request.optimizer_enabled);
        assert_eq!(request.optimizer_max_duration_seconds, 0);
        assert_eq!(request.pair_overrides.len(), 1);
    }

    #[test]
    fn native_batch_budget_and_resume_preserve_python_checkpoint_semantics() {
        let request = NativeBacktestBatchRequest {
            symbols: (0..20).map(|index| format!("BTCUSDT{index}")).collect(),
            intervals: (0..20).map(|index| format!("{}m", index + 1)).collect(),
            indicator_configs: BTreeMap::from([(
                "rsi".to_owned(),
                json!({"enabled": true, "buy_value": 45.0, "sell_value": 55.0}),
            )]),
            optimizer_enabled: true,
            optimizer_mode: "single".to_owned(),
            optimizer_max_duration_seconds: 1,
            result_limit: 10,
            ..NativeBacktestBatchRequest::default()
        };
        let candles = fixture_candles();
        let budget_snapshot = run_native_backtest_batch(
            &request,
            |_, _| {
                std::thread::sleep(Duration::from_millis(6));
                CandleLoadResult::success(candles.clone())
            },
            || false,
        );
        assert_eq!(budget_snapshot["state"], "budget_exhausted");
        assert!(budget_snapshot["completed_combo_count"].as_u64().unwrap() > 0);
        assert!(
            budget_snapshot["completed_combo_count"].as_u64().unwrap()
                < budget_snapshot["optimizer_run_count"].as_u64().unwrap()
        );
        assert!(
            budget_snapshot["errors"]
                .as_array()
                .unwrap()
                .iter()
                .any(|error| error["error"] == "backtest_optimizer_time_budget_exhausted")
        );

        let mut resumed = request.clone();
        resumed.optimizer_max_duration_seconds = 0;
        resumed.resume_combo_offset = budget_snapshot["completed_combo_count"].as_u64().unwrap();
        resumed.resume_prior_runs = budget_snapshot["runs"].as_array().unwrap().clone();
        resumed.resume_prior_errors = budget_snapshot["errors"].as_array().unwrap().clone();
        let completed_snapshot = run_native_backtest_batch(
            &resumed,
            |_, _| CandleLoadResult::success(candles.clone()),
            || false,
        );
        assert_eq!(completed_snapshot["state"], "completed");
        assert_eq!(
            completed_snapshot["completed_combo_count"],
            completed_snapshot["optimizer_run_count"]
        );
        assert_eq!(completed_snapshot["progress_percent"], 100.0);
        assert_eq!(completed_snapshot["resume_checkpoint"], true);
    }

    #[test]
    fn python_request_date_defaults_match_thirty_day_window() {
        let request = NativeBacktestBatchRequest::from_python_request(&json!({
            "symbols": ["BTCUSDT"],
            "intervals": ["1m"],
            "indicators": {"rsi": {"enabled": true, "length": 14}}
        }))
        .expect("default dates should be accepted");
        let start = request.start_ms.expect("start timestamp");
        let end = request.end_ms.expect("end timestamp");
        assert!(end > start);
        assert!((end - start - 30 * 86_400_000).abs() < 2_000);
    }
}
