use std::collections::BTreeMap;

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::account::{
    BinanceAccountSnapshot, BinanceFuturesMarginMode, BinanceFuturesMultiAssetsMode,
    BinanceFuturesPosition, BinanceFuturesPositionMode, normalize_futures_margin_type,
};
use crate::native_indicators::{
    compute_configured_indicator_series, default_runtime_indicator_configs,
    unsupported_enabled_indicator_keys,
};
use crate::order_audit::redact_text;
use crate::order_guard::OrderSymbolFilters;
use crate::orders::{
    BinanceFuturesOrderParams, BinanceFuturesOrderResult, build_futures_market_order_params,
};
use crate::position_close::{BinanceFuturesCloseDirective, plan_futures_position_close};
use crate::runtime_order_engine::{
    RuntimeOrderEngine, RuntimeOrderSubmitInput, RuntimeOrderSubmitResult,
};
use crate::strategy_runtime::{StrategyWorkerLifecycleInput, build_worker_lifecycle_snapshot};
use crate::streams::{
    BinanceKlineStreamCandle, BinanceStreamEvent, BinanceWebSocket, BinanceWebSocketClient,
    StreamReconnectPolicy, StreamSupervisor, StreamSupervisorSnapshot,
};
use crate::{
    market_data::{BinanceKlineCandle, interval_seconds},
    runtime_control::{
        RuntimeStopGuardInput, RuntimeStopGuardResult, build_runtime_idle_after_stop_result,
        build_runtime_stop_guard_result,
    },
    rust_trading_execution_supported,
    strategy_runtime::{
        IndicatorRule, StrategySignalDecision, StrategySignalInput, build_signal_decision,
    },
};

const NATIVE_POSITION_EPSILON: f64 = 1e-10;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NativeRuntimeLoopConfig {
    pub symbol: String,
    pub interval: String,
    pub position_mode: String,
    pub margin_mode: String,
    pub leverage: i64,
    pub multi_assets_mode: bool,
    pub loop_interval_override: Option<String>,
    pub stream_reconnect_policy: StreamReconnectPolicy,
    pub stream_stale_after_ms: i64,
}

impl Default for NativeRuntimeLoopConfig {
    fn default() -> Self {
        Self {
            symbol: "BTCUSDT".to_owned(),
            interval: "1m".to_owned(),
            position_mode: "Hedge".to_owned(),
            margin_mode: "ISOLATED".to_owned(),
            leverage: 5,
            multi_assets_mode: false,
            loop_interval_override: None,
            stream_reconnect_policy: StreamReconnectPolicy::default(),
            stream_stale_after_ms: 30_000,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeCycleInput {
    pub now_ms: i64,
    pub stream_event: Option<BinanceStreamEvent>,
    pub stream_disconnected: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeCycleSnapshot {
    pub lifecycle: Value,
    pub stream: StreamSupervisorSnapshot,
    pub signal_evaluation_allowed: bool,
    pub trading_execution_supported: bool,
    pub status_message: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeIngestionSnapshot {
    pub poll_status: String,
    pub poll_error: Option<String>,
    pub cycle: NativeRuntimeCycleSnapshot,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeClosePlanningInput {
    pub positions: Vec<BinanceFuturesPosition>,
    pub step_size_by_symbol: Vec<(String, f64)>,
    pub prefer_close_position: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeClosePlanningSnapshot {
    pub position_mode: String,
    pub hedge_mode: bool,
    pub directives: Vec<BinanceFuturesCloseDirective>,
    pub trading_execution_supported: bool,
    pub status_message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimePositionModeSnapshot {
    pub configured_position_mode: String,
    pub exchange_position_mode: Option<String>,
    pub exchange_dual_side_position: Option<bool>,
    pub matches_config: bool,
    pub signal_evaluation_allowed: bool,
    pub status_message: String,
    pub trading_execution_supported: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeFuturesSettingsInput {
    pub exchange_margin_mode: Option<BinanceFuturesMarginMode>,
    pub exchange_leverage: Option<i64>,
    pub exchange_multi_assets_mode: Option<BinanceFuturesMultiAssetsMode>,
    pub open_position_amt: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimeFuturesSettingsSnapshot {
    pub symbol: String,
    pub configured_margin_mode: String,
    pub exchange_margin_mode: Option<String>,
    pub margin_mode_matches_config: bool,
    pub configured_leverage: i64,
    pub exchange_leverage: Option<i64>,
    pub leverage_matches_config: bool,
    pub configured_multi_assets_mode: bool,
    pub exchange_multi_assets_mode: Option<bool>,
    pub multi_assets_matches_config: bool,
    pub open_position_blocks_margin_change: bool,
    pub signal_evaluation_allowed: bool,
    pub status_message: String,
    pub trading_execution_supported: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeAccountPreflightInput {
    pub exchange_position_mode: Option<BinanceFuturesPositionMode>,
    pub futures_settings: NativeRuntimeFuturesSettingsInput,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeAccountPreflightSnapshot {
    pub position_mode: NativeRuntimePositionModeSnapshot,
    pub futures_settings: NativeRuntimeFuturesSettingsSnapshot,
    pub signal_evaluation_allowed: bool,
    pub status_message: String,
    pub trading_execution_supported: bool,
}

/// Read-only account state consumed by the native runtime before it can evaluate signals.
///
/// This deliberately contains no credentials and performs no exchange mutation. The caller
/// supplies values read from Binance so the runtime and live-smoke path share the same
/// reconciliation logic instead of proving their pieces independently.
#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeReadOnlyAccountBootstrapSnapshot {
    pub balance_asset: String,
    pub open_positions_count: usize,
    pub configured_symbol_position_found: bool,
    pub configured_symbol_open_position_amt: f64,
    pub account_preflight: NativeRuntimeAccountPreflightSnapshot,
    pub signal_evaluation_allowed: bool,
    pub trading_execution_supported: bool,
    pub status_message: String,
}

/// Input for a no-order native runtime cycle hydrated from REST candles.
///
/// REST responses can include an in-progress last candle. Unless explicitly
/// marked closed, the coordinator excludes that candle from signal evaluation.
#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeReadOnlyMarketCycleInput {
    pub now_ms: i64,
    pub candles: Vec<BinanceKlineCandle>,
    /// Python-shaped runtime indicator configuration. Used when callers do not
    /// provide precomputed series, allowing the native loop to calculate the
    /// supported enabled indicators from the Python source contract.
    pub indicator_configs: BTreeMap<String, Value>,
    pub indicators: BTreeMap<String, Vec<f64>>,
    pub rules: BTreeMap<String, IndicatorRule>,
    pub side: String,
    pub last_candle_is_closed: bool,
}

impl NativeRuntimeReadOnlyMarketCycleInput {
    /// Build a native read-only cycle from the validated Python Service API
    /// configuration payload (or its persisted `{ "config": ... }` wrapper).
    ///
    /// The Python service remains the validation owner. This adapter preserves
    /// the indicator objects and derives the same enabled/buy/sell rule shape
    /// that the native strategy evaluator consumes.
    pub fn from_python_service_config(
        now_ms: i64,
        candles: Vec<BinanceKlineCandle>,
        payload: &Value,
        last_candle_is_closed: bool,
    ) -> Result<Self> {
        let config = if payload.get("indicators").is_some() {
            payload
        } else {
            payload
                .get("config")
                .filter(|value| value.is_object())
                .ok_or_else(|| anyhow::anyhow!("Python Service API payload has no config object"))?
        };
        let indicator_object = config
            .get("indicators")
            .and_then(Value::as_object)
            .ok_or_else(|| anyhow::anyhow!("Python Service API config has no indicators object"))?;
        let mut indicator_configs = BTreeMap::new();
        let mut rules = BTreeMap::new();
        for (key, indicator_config) in indicator_object {
            let Some(indicator) = indicator_config.as_object() else {
                bail!("Python Service API indicator {key} must be an object");
            };
            indicator_configs.insert(key.clone(), indicator_config.clone());
            rules.insert(
                key.clone(),
                IndicatorRule {
                    enabled: native_config_bool(indicator.get("enabled")),
                    buy_value: native_config_number(indicator.get("buy_value")),
                    sell_value: native_config_number(indicator.get("sell_value")),
                },
            );
        }
        let side = config
            .get("side")
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .unwrap_or("BOTH")
            .to_owned();
        Ok(Self {
            now_ms,
            candles,
            indicator_configs,
            indicators: BTreeMap::new(),
            rules,
            side,
            last_candle_is_closed,
        })
    }
}

fn native_config_bool(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(value)) => *value,
        Some(Value::Number(value)) => value.as_f64().is_some_and(|value| value != 0.0),
        Some(Value::String(value)) => matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on" | "y"
        ),
        _ => false,
    }
}

fn native_config_number(value: Option<&Value>) -> Option<f64> {
    match value {
        Some(Value::Number(value)) => value.as_f64(),
        Some(Value::String(value)) => value.trim().parse::<f64>().ok(),
        _ => None,
    }
    .filter(|value| value.is_finite())
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeReadOnlyMarketCycleSnapshot {
    pub closed_candle_count: usize,
    pub latest_closed_open_time_ms: i64,
    pub computed_indicator_keys: Vec<String>,
    pub unsupported_indicator_keys: Vec<String>,
    pub cycle: NativeRuntimeCycleSnapshot,
    pub strategy_evaluated: bool,
    pub strategy_decision: Option<StrategySignalDecision>,
    pub trading_execution_supported: bool,
    pub status_message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimeFreshnessInput {
    pub timestamp_ms: Option<i64>,
    pub timestamp_field: String,
    pub max_age_ms: i64,
    pub should_warn: bool,
    pub state: String,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimeFreshnessSnapshot {
    pub stale: bool,
    pub max_age_ms: i64,
    pub age_ms: Option<i64>,
    pub timestamp_ms: Option<i64>,
    pub timestamp_field: String,
    pub state: String,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimePreflightGate {
    pub allowed: bool,
    pub state: String,
    pub gate_enabled: bool,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeOperationalPreflightInput {
    pub mode: String,
    pub health: String,
    pub generated_at_ms: i64,
    pub start_gate_enabled: bool,
    pub order_gate_enabled: bool,
    pub connector_order_circuit_active: bool,
    pub exchange_connector: NativeRuntimeFreshnessInput,
    pub execution: NativeRuntimeFreshnessInput,
    pub account: NativeRuntimeFreshnessInput,
    pub portfolio: NativeRuntimeFreshnessInput,
    pub account_preflight: Option<NativeRuntimeAccountPreflightSnapshot>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimeOperationalFreshnessSnapshot {
    pub exchange_connector: NativeRuntimeFreshnessSnapshot,
    pub execution: NativeRuntimeFreshnessSnapshot,
    pub account: NativeRuntimeFreshnessSnapshot,
    pub portfolio: NativeRuntimeFreshnessSnapshot,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimeCriticalStaleSnapshot {
    pub start: Vec<String>,
    pub orders: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeRuntimeOperationalPreflightSnapshot {
    pub state: String,
    pub message: String,
    pub mode: String,
    pub live_mode: bool,
    pub generated_at_ms: i64,
    pub start: NativeRuntimePreflightGate,
    pub orders: NativeRuntimePreflightGate,
    pub freshness: NativeRuntimeOperationalFreshnessSnapshot,
    pub critical_stale: NativeRuntimeCriticalStaleSnapshot,
    pub reasons: Vec<String>,
    pub trading_execution_supported: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeExposureGuardInput {
    pub symbol: String,
    pub interval: String,
    pub side: String,
    pub position_pct_fraction: f64,
    pub available_usdt: f64,
    pub wallet_usdt: f64,
    pub ledger_margin_total: f64,
    pub existing_indicator_margin: f64,
    pub existing_side_margin: f64,
    pub active_slot_count: usize,
    pub slot_already_active: bool,
    pub price: f64,
    pub leverage: i64,
    pub filter_min_qty: f64,
    pub filter_min_notional: f64,
    pub filter_step_size: f64,
    pub flip_close_qty: Option<f64>,
    pub live_mode: bool,
    pub live_allow_auto_bump_to_min_order: bool,
    pub max_auto_bump_percent: f64,
    pub auto_bump_percent_multiplier: f64,
    pub margin_over_target_tolerance: f64,
    pub margin_filter_slippage: f64,
    pub add_only: bool,
    pub dual_side: bool,
    pub net_position_amt: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeExposureGuardSnapshot {
    pub allowed: bool,
    pub reason: String,
    pub equity_usdt: f64,
    pub target_margin_usdt: f64,
    pub max_indicator_margin_usdt: f64,
    pub margin_estimate_usdt: f64,
    pub projected_side_margin_usdt: f64,
    pub quantity_estimate: f64,
    pub reduce_only: bool,
    pub desired_position_side: Option<String>,
    pub trading_execution_supported: bool,
}

#[derive(Debug, Clone)]
pub struct NativeRuntimeGuardedExecutionCycleInput {
    pub market_cycle: NativeRuntimeReadOnlyMarketCycleInput,
    pub exposure: NativeRuntimeExposureGuardInput,
    pub filters: Option<OrderSymbolFilters>,
    pub market: String,
    pub connector_state: String,
    pub connector_health: String,
    pub operational_preflight: NativeRuntimeOperationalPreflightSnapshot,
    pub now_iso: String,
    pub now_epoch_seconds: f64,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NativeRuntimeGuardedExecutionCycleSnapshot {
    pub market_cycle: NativeRuntimeReadOnlyMarketCycleSnapshot,
    pub exposure: Option<NativeRuntimeExposureGuardSnapshot>,
    pub order: Option<RuntimeOrderSubmitResult>,
    pub state: String,
    pub status_message: String,
    pub trading_execution_supported: bool,
}

#[derive(Debug, Clone)]
pub struct NativeRuntimeLoop {
    pub config: NativeRuntimeLoopConfig,
    pub stream_supervisor: StreamSupervisor,
    runtime_active: bool,
    stop_requested: bool,
    close_positions_requested: bool,
    global_shutdown: bool,
    global_pause: bool,
    active_engine_count: usize,
    emergency_close_triggered: bool,
    status_message: String,
}

impl NativeRuntimeLoop {
    pub fn new(config: NativeRuntimeLoopConfig) -> Self {
        let stream_supervisor = StreamSupervisor::new(
            config.stream_reconnect_policy.clone(),
            config.stream_stale_after_ms,
        );
        Self {
            config,
            stream_supervisor,
            runtime_active: false,
            stop_requested: false,
            close_positions_requested: false,
            global_shutdown: false,
            global_pause: false,
            active_engine_count: 0,
            emergency_close_triggered: false,
            status_message: "Runtime idle.".to_owned(),
        }
    }

    pub fn start(&mut self) {
        self.runtime_active = true;
        self.stop_requested = false;
        self.close_positions_requested = false;
        self.global_shutdown = false;
        self.global_pause = false;
        self.active_engine_count = 1;
        self.status_message = "Runtime started in native dry-run coordination mode.".to_owned();
    }

    pub fn set_global_pause(&mut self, paused: bool) {
        self.global_pause = paused;
        self.status_message = if paused {
            "Runtime paused.".to_owned()
        } else {
            "Runtime resumed.".to_owned()
        };
    }

    pub fn request_shutdown(&mut self) {
        self.global_shutdown = true;
        self.stop_requested = true;
        self.status_message = "Runtime shutdown requested.".to_owned();
    }

    pub fn request_stop(
        &mut self,
        close_positions: bool,
        source: impl Into<String>,
        dispatch_accepted: bool,
        dispatch_message: impl Into<String>,
    ) -> RuntimeStopGuardResult {
        let result = build_runtime_stop_guard_result(RuntimeStopGuardInput {
            runtime_active: self.runtime_active,
            active_engine_count: self.active_engine_count,
            stop_already_in_progress: self.stop_requested,
            close_positions,
            dispatch_accepted,
            dispatch_message: dispatch_message.into(),
            source: source.into(),
        });
        self.status_message = result.status_message.clone();
        if result.accepted {
            self.stop_requested = true;
            self.close_positions_requested = result.close_positions_requested;
        }
        result
    }

    pub fn mark_idle_after_stop(
        &mut self,
        source: impl AsRef<str>,
        status_message: impl AsRef<str>,
    ) -> RuntimeStopGuardResult {
        let result = build_runtime_idle_after_stop_result(
            self.close_positions_requested,
            source,
            status_message,
        );
        self.runtime_active = false;
        self.stop_requested = false;
        self.close_positions_requested = false;
        self.global_shutdown = false;
        self.global_pause = false;
        self.active_engine_count = 0;
        self.status_message = result.status_message.clone();
        result
    }

    pub fn run_cycle(&mut self, input: NativeRuntimeCycleInput) -> NativeRuntimeCycleSnapshot {
        if let Some(event) = input.stream_event {
            self.stream_supervisor.record_event(event, input.now_ms);
        }
        if input.stream_disconnected {
            self.stream_supervisor.record_disconnected(input.now_ms);
        }

        let stream = self.stream_supervisor.snapshot(input.now_ms);
        let offline_backoff = if stream.reconnect_decision.should_reconnect {
            stream.reconnect_decision.delay_ms as f64 / 1_000.0
        } else {
            0.0
        };
        let lifecycle = build_worker_lifecycle_snapshot(StrategyWorkerLifecycleInput {
            symbol: self.config.symbol.clone(),
            interval: self.config.interval.clone(),
            loop_interval_override: self.config.loop_interval_override.clone(),
            thread_alive: self.runtime_active,
            stop_requested: self.stop_requested,
            global_shutdown: self.global_shutdown,
            global_pause: self.global_pause,
            active_engine_count: self.active_engine_count,
            offline_backoff,
            emergency_close_triggered: self.emergency_close_triggered,
        });
        let signal_evaluation_allowed = self.runtime_active
            && !self.stop_requested
            && !self.global_shutdown
            && !self.global_pause
            && !stream.kline_cache_health.stale
            && !stream.reconnect_decision.should_reconnect;

        NativeRuntimeCycleSnapshot {
            lifecycle,
            stream,
            signal_evaluation_allowed,
            trading_execution_supported: rust_trading_execution_supported(),
            status_message: self.status_message.clone(),
        }
    }

    pub fn run_stream_ingestion_cycle<F>(
        &mut self,
        now_ms: i64,
        mut poll_next: F,
    ) -> NativeRuntimeIngestionSnapshot
    where
        F: FnMut() -> Result<Option<BinanceStreamEvent>>,
    {
        match poll_next() {
            Ok(Some(event)) => {
                self.status_message = "Stream event ingested.".to_owned();
                NativeRuntimeIngestionSnapshot {
                    poll_status: "event".to_owned(),
                    poll_error: None,
                    cycle: self.run_cycle(NativeRuntimeCycleInput {
                        now_ms,
                        stream_event: Some(event),
                        stream_disconnected: false,
                    }),
                }
            }
            Ok(None) => {
                self.status_message = "Stream closed; reconnect required.".to_owned();
                NativeRuntimeIngestionSnapshot {
                    poll_status: "closed".to_owned(),
                    poll_error: None,
                    cycle: self.run_cycle(NativeRuntimeCycleInput {
                        now_ms,
                        stream_event: None,
                        stream_disconnected: true,
                    }),
                }
            }
            Err(error) => {
                let redacted_error = redact_text(&error.to_string());
                self.status_message = format!("Stream ingestion error: {redacted_error}");
                NativeRuntimeIngestionSnapshot {
                    poll_status: "error".to_owned(),
                    poll_error: Some(redacted_error),
                    cycle: self.run_cycle(NativeRuntimeCycleInput {
                        now_ms,
                        stream_event: None,
                        stream_disconnected: true,
                    }),
                }
            }
        }
    }

    pub fn ingest_next_websocket_event(
        &mut self,
        now_ms: i64,
        socket: &mut BinanceWebSocket,
    ) -> NativeRuntimeIngestionSnapshot {
        self.run_stream_ingestion_cycle(now_ms, || BinanceWebSocketClient::read_next_event(socket))
    }

    /// Hydrate the stream coordinator from a REST kline poll while a websocket
    /// is reconnecting. The latest REST candle may still be open, so only the
    /// preceding candle is eligible for read-only strategy evaluation.
    pub fn run_rest_kline_ingestion_cycle<F>(
        &mut self,
        now_ms: i64,
        mut poll_klines: F,
    ) -> NativeRuntimeIngestionSnapshot
    where
        F: FnMut() -> Result<Vec<BinanceKlineCandle>>,
    {
        let event = poll_klines()
            .and_then(|candles| latest_closed_rest_kline_event(&self.config, now_ms, &candles));
        let mut snapshot = match event {
            Ok(event) => self.run_stream_ingestion_cycle(now_ms, || Ok(Some(event.clone()))),
            Err(error) => {
                let message = error.to_string();
                self.run_stream_ingestion_cycle(now_ms, || Err(anyhow::anyhow!(message.clone())))
            }
        };
        if snapshot.poll_status == "event" {
            self.status_message = "REST closed kline ingested.".to_owned();
            snapshot.poll_status = "rest_closed_kline".to_owned();
        } else {
            self.status_message = format!(
                "REST kline ingestion error: {}",
                snapshot.poll_error.as_deref().unwrap_or("unknown error")
            );
            snapshot.poll_status = "rest_error".to_owned();
        }
        snapshot.cycle.status_message = self.status_message.clone();
        snapshot
    }

    pub fn position_mode(&self) -> String {
        normalize_native_position_mode(&self.config.position_mode)
    }

    pub fn hedge_mode_enabled(&self) -> bool {
        self.position_mode() == "Hedge"
    }

    pub fn reconcile_position_mode(
        &self,
        exchange_mode: Option<&BinanceFuturesPositionMode>,
    ) -> NativeRuntimePositionModeSnapshot {
        reconcile_native_position_mode(&self.config.position_mode, exchange_mode)
    }

    pub fn reconcile_futures_settings(
        &self,
        input: NativeRuntimeFuturesSettingsInput,
    ) -> NativeRuntimeFuturesSettingsSnapshot {
        reconcile_native_futures_settings(
            &self.config.symbol,
            &self.config.margin_mode,
            self.config.leverage,
            self.config.multi_assets_mode,
            input,
        )
    }

    pub fn reconcile_account_preflight(
        &self,
        input: NativeRuntimeAccountPreflightInput,
    ) -> NativeRuntimeAccountPreflightSnapshot {
        evaluate_native_account_preflight(
            &self.config.position_mode,
            &self.config.symbol,
            &self.config.margin_mode,
            self.config.leverage,
            self.config.multi_assets_mode,
            input,
        )
    }

    /// Bind a freshly read account snapshot to this runtime's configured symbol and safety
    /// preflight. It is intentionally read-only; callers retain ownership of all exchange I/O.
    pub fn bootstrap_read_only_account(
        &self,
        balance: &BinanceAccountSnapshot,
        positions: &[BinanceFuturesPosition],
        exchange_position_mode: Option<&BinanceFuturesPositionMode>,
        exchange_multi_assets_mode: Option<&BinanceFuturesMultiAssetsMode>,
    ) -> NativeRuntimeReadOnlyAccountBootstrapSnapshot {
        let configured_symbol = self.config.symbol.trim().to_ascii_uppercase();
        let matching_positions: Vec<&BinanceFuturesPosition> = positions
            .iter()
            .filter(|position| {
                position
                    .symbol
                    .trim()
                    .eq_ignore_ascii_case(&configured_symbol)
            })
            .collect();
        let configured_symbol_open_position_amt = matching_positions
            .iter()
            .map(|position| position.position_amt)
            .filter(|amount| amount.is_finite())
            .map(f64::abs)
            .sum();
        let mut margin_modes = Vec::new();
        let mut leverages = Vec::new();
        for position in &matching_positions {
            if let Ok(margin_mode) = normalize_futures_margin_type(&position.margin_type) {
                if !margin_modes.contains(&margin_mode) {
                    margin_modes.push(margin_mode);
                }
            }
            if position.leverage.is_finite()
                && position.leverage >= 1.0
                && position.leverage <= 125.0
            {
                let leverage = position.leverage.round() as i64;
                if !leverages.contains(&leverage) {
                    leverages.push(leverage);
                }
            }
        }
        let exchange_margin_mode = (margin_modes.len() == 1).then(|| BinanceFuturesMarginMode {
            symbol: configured_symbol.clone(),
            margin_type: margin_modes[0].clone(),
        });
        let exchange_leverage = (leverages.len() == 1).then(|| leverages[0]);
        let account_preflight =
            self.reconcile_account_preflight(NativeRuntimeAccountPreflightInput {
                exchange_position_mode: exchange_position_mode.cloned(),
                futures_settings: NativeRuntimeFuturesSettingsInput {
                    exchange_margin_mode,
                    exchange_leverage,
                    exchange_multi_assets_mode: exchange_multi_assets_mode.cloned(),
                    open_position_amt: configured_symbol_open_position_amt,
                },
            });
        let signal_evaluation_allowed = account_preflight.signal_evaluation_allowed;
        let status_message = if signal_evaluation_allowed {
            "Read-only native account bootstrap passed reconciliation.".to_owned()
        } else {
            format!(
                "Read-only native account bootstrap is safe but not signal-ready: {}",
                account_preflight.status_message
            )
        };

        NativeRuntimeReadOnlyAccountBootstrapSnapshot {
            balance_asset: balance.asset.trim().to_ascii_uppercase(),
            open_positions_count: positions.len(),
            configured_symbol_position_found: !matching_positions.is_empty(),
            configured_symbol_open_position_amt,
            account_preflight,
            signal_evaluation_allowed,
            trading_execution_supported: rust_trading_execution_supported(),
            status_message,
        }
    }

    /// Feed read-only REST candles through the same stream health and strategy
    /// decision path used by the native runtime. This does not submit orders.
    pub fn run_read_only_market_cycle(
        &mut self,
        input: NativeRuntimeReadOnlyMarketCycleInput,
    ) -> Result<NativeRuntimeReadOnlyMarketCycleSnapshot> {
        let NativeRuntimeReadOnlyMarketCycleInput {
            now_ms,
            candles: input_candles,
            indicator_configs,
            indicators: input_indicators,
            rules,
            side,
            last_candle_is_closed,
        } = input;
        let discard_last_candle = !last_candle_is_closed;
        let mut candles: Vec<BinanceKlineCandle> = input_candles
            .into_iter()
            .filter(|candle| {
                candle.open_time_ms >= 0
                    && [
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                    ]
                    .iter()
                    .all(|value| value.is_finite())
            })
            .collect();
        candles.sort_by_key(|candle| candle.open_time_ms);
        candles.dedup_by_key(|candle| candle.open_time_ms);
        if discard_last_candle {
            let _ = candles.pop();
        }
        let Some(latest_closed) = candles.last() else {
            bail!("no completed finite candles available for native runtime cycle");
        };
        let closed_candle_count = candles.len();
        let latest_closed_open_time_ms = latest_closed.open_time_ms;
        let cycle = self.run_cycle(NativeRuntimeCycleInput {
            now_ms: now_ms.max(0),
            stream_event: Some(BinanceStreamEvent::Kline(BinanceKlineStreamCandle {
                symbol: self.config.symbol.trim().to_ascii_uppercase(),
                interval: self.config.interval.clone(),
                open_time_ms: latest_closed.open_time_ms,
                open: latest_closed.open,
                high: latest_closed.high,
                low: latest_closed.low,
                close: latest_closed.close,
                volume: latest_closed.volume,
                is_closed: true,
                // The REST hydration happened now; stream freshness should reflect ingestion,
                // not the old candle open timestamp.
                event_time_ms: now_ms.max(0),
            })),
            stream_disconnected: false,
        });
        let (source_indicators, unsupported_indicator_keys) = if input_indicators.is_empty() {
            let configs = if indicator_configs.is_empty() {
                default_runtime_indicator_configs()
            } else {
                indicator_configs
            };
            (
                compute_configured_indicator_series(&candles, &configs),
                unsupported_enabled_indicator_keys(&configs),
            )
        } else {
            (input_indicators, Vec::new())
        };
        let indicators: BTreeMap<String, Vec<f64>> = source_indicators
            .into_iter()
            .map(|(key, mut values)| {
                if discard_last_candle {
                    let _ = values.pop();
                }
                (key, values)
            })
            .collect();
        let computed_indicator_keys = indicators.keys().cloned().collect();
        let strategy_decision =
            (cycle.signal_evaluation_allowed && unsupported_indicator_keys.is_empty()).then(|| {
                build_signal_decision(StrategySignalInput {
                    closes: candles.iter().map(|candle| candle.close).collect(),
                    indicators,
                    rules,
                    side,
                    use_live_values: false,
                })
            });
        let strategy_evaluated = strategy_decision.is_some();
        let status_message = if let Some(decision) = &strategy_decision {
            let signal = decision.signal.as_deref().unwrap_or("none");
            format!("Read-only native market cycle evaluated strategy; signal={signal}.")
        } else if !unsupported_indicator_keys.is_empty() {
            format!(
                "Read-only native market cycle withheld strategy evaluation; unsupported indicators: {}.",
                unsupported_indicator_keys.join(", ")
            )
        } else {
            "Read-only native market cycle cached data but signal evaluation is blocked.".to_owned()
        };

        Ok(NativeRuntimeReadOnlyMarketCycleSnapshot {
            closed_candle_count,
            latest_closed_open_time_ms,
            computed_indicator_keys,
            unsupported_indicator_keys,
            cycle,
            strategy_evaluated,
            strategy_decision,
            trading_execution_supported: rust_trading_execution_supported(),
            status_message,
        })
    }

    /// Run a Python-shaped strategy decision through operational preflight,
    /// allocation, exchange-filter, audit, and order-engine guards. A real
    /// submit remains fail-closed until the runtime-ready policy is promoted.
    pub fn run_guarded_execution_cycle<F>(
        &mut self,
        engine: &mut RuntimeOrderEngine,
        input: NativeRuntimeGuardedExecutionCycleInput,
        mut execute: F,
    ) -> Result<NativeRuntimeGuardedExecutionCycleSnapshot>
    where
        F: FnMut(&BinanceFuturesOrderParams) -> Result<BinanceFuturesOrderResult>,
    {
        let market_cycle = self.run_read_only_market_cycle(input.market_cycle)?;
        let Some(decision) = market_cycle.strategy_decision.as_ref() else {
            return Ok(guarded_execution_snapshot(
                market_cycle,
                None,
                None,
                "idle",
                "No actionable native strategy decision; no order was considered.",
            ));
        };
        let Some(signal) = decision.signal.as_deref() else {
            return Ok(guarded_execution_snapshot(
                market_cycle,
                None,
                None,
                "idle",
                "Native strategy returned no BUY or SELL signal; no order was considered.",
            ));
        };
        if !matches!(signal, "BUY" | "SELL") {
            return Ok(guarded_execution_snapshot(
                market_cycle,
                None,
                None,
                "blocked",
                "Native strategy emitted an unsupported signal; no order was considered.",
            ));
        }
        if !operational_preflight_orders_allowed(&input.operational_preflight) {
            let reason = if input.operational_preflight.orders.reasons.is_empty() {
                "Native operational preflight blocked order submission.".to_owned()
            } else {
                format!(
                    "Native operational preflight blocked order submission: {}",
                    input.operational_preflight.orders.reasons.join("; ")
                )
            };
            return Ok(guarded_execution_snapshot(
                market_cycle,
                None,
                None,
                "blocked",
                &reason,
            ));
        }

        let mut exposure_input = input.exposure;
        exposure_input.side = signal.to_owned();
        let last_price = exposure_input.price;
        let exposure = self.evaluate_exposure_guard(exposure_input);
        if !exposure.allowed {
            let message = format!("Native exposure guard blocked order: {}", exposure.reason);
            return Ok(guarded_execution_snapshot(
                market_cycle,
                Some(exposure),
                None,
                "blocked",
                &message,
            ));
        }
        if !engine.dry_run && !rust_trading_execution_supported() {
            return Ok(guarded_execution_snapshot(
                market_cycle,
                Some(exposure),
                None,
                "blocked",
                "Standalone native execution is not runtime-ready; refusing to submit an order.",
            ));
        }

        let order = build_futures_market_order_params(
            &self.config.symbol,
            signal,
            exposure.quantity_estimate,
            exposure.reduce_only,
            exposure.desired_position_side.as_deref().unwrap_or(""),
        )?;
        let submit = engine.submit_futures_order(
            RuntimeOrderSubmitInput {
                order: &order,
                market: non_empty_or(&input.market, "futures"),
                filters: input.filters,
                last_price: Some(last_price),
                connector_state: input.connector_state,
                connector_health: input.connector_health,
                interval: self.config.interval.clone(),
                now_iso: input.now_iso,
                now_epoch_seconds: input.now_epoch_seconds,
                source: non_empty_or(&input.source, "native-runtime-guarded-cycle"),
            },
            |params| execute(params),
        );
        let state = if submit.allowed {
            "accepted"
        } else {
            "blocked"
        };
        let status_message = if submit.allowed && engine.dry_run {
            "Native guarded execution cycle completed as a validated dry run.".to_owned()
        } else if submit.allowed {
            "Native guarded execution cycle submitted an order.".to_owned()
        } else {
            format!("Native order engine blocked order: {}", submit.error)
        };
        Ok(guarded_execution_snapshot(
            market_cycle,
            Some(exposure),
            Some(submit),
            state,
            &status_message,
        ))
    }

    pub fn build_operational_preflight(
        &self,
        input: NativeRuntimeOperationalPreflightInput,
    ) -> NativeRuntimeOperationalPreflightSnapshot {
        build_native_operational_preflight(input)
    }

    pub fn plan_close_positions(
        &mut self,
        input: NativeRuntimeClosePlanningInput,
    ) -> Result<NativeRuntimeClosePlanningSnapshot> {
        let position_mode = self.position_mode();
        let hedge_mode = position_mode == "Hedge";
        let mut directives = Vec::new();
        for position in &input.positions {
            let step_size = input
                .step_size_by_symbol
                .iter()
                .find(|(symbol, _)| symbol.trim().eq_ignore_ascii_case(&position.symbol))
                .map(|(_, step_size)| *step_size)
                .unwrap_or(0.0);
            directives.extend(plan_futures_position_close(
                position,
                hedge_mode,
                step_size,
                input.prefer_close_position,
            )?);
        }

        self.status_message = format!(
            "Planned {} native close directive(s) in {position_mode} dry-run mode.",
            directives.len()
        );
        Ok(NativeRuntimeClosePlanningSnapshot {
            position_mode,
            hedge_mode,
            directives,
            trading_execution_supported: rust_trading_execution_supported(),
            status_message: self.status_message.clone(),
        })
    }

    pub fn evaluate_exposure_guard(
        &self,
        input: NativeRuntimeExposureGuardInput,
    ) -> NativeRuntimeExposureGuardSnapshot {
        evaluate_native_exposure_guard(input)
    }
}

fn latest_closed_rest_kline_event(
    config: &NativeRuntimeLoopConfig,
    observed_at_ms: i64,
    candles: &[BinanceKlineCandle],
) -> Result<BinanceStreamEvent> {
    if candles.len() < 2 {
        bail!("REST kline ingestion requires at least two candles to select a closed candle");
    }
    let candle = &candles[candles.len() - 2];
    let symbol = config.symbol.trim().to_ascii_uppercase();
    let interval = config.interval.trim().to_ascii_lowercase();
    if symbol.is_empty() || interval.is_empty() {
        bail!("REST kline ingestion requires a configured symbol and interval");
    }
    if candle.open_time_ms < 0
        || !candle.open.is_finite()
        || !candle.high.is_finite()
        || !candle.low.is_finite()
        || !candle.close.is_finite()
        || !candle.volume.is_finite()
    {
        bail!("REST kline ingestion received invalid candle data");
    }
    let interval_ms = (interval_seconds(&interval)? * 1_000.0).round() as i64;
    let close_time_ms = candle.open_time_ms.saturating_add(interval_ms.max(1));
    Ok(BinanceStreamEvent::Kline(BinanceKlineStreamCandle {
        symbol,
        interval,
        open_time_ms: candle.open_time_ms,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
        is_closed: true,
        event_time_ms: close_time_ms.min(observed_at_ms.max(candle.open_time_ms)),
    }))
}

pub fn reconcile_native_position_mode(
    configured_position_mode: impl AsRef<str>,
    exchange_mode: Option<&BinanceFuturesPositionMode>,
) -> NativeRuntimePositionModeSnapshot {
    let configured_position_mode = normalize_native_position_mode(configured_position_mode);
    let Some(exchange_mode) = exchange_mode else {
        return NativeRuntimePositionModeSnapshot {
            configured_position_mode,
            exchange_position_mode: None,
            exchange_dual_side_position: None,
            matches_config: false,
            signal_evaluation_allowed: false,
            status_message:
                "Position mode unknown; native runtime must reconcile Binance account mode."
                    .to_owned(),
            trading_execution_supported: rust_trading_execution_supported(),
        };
    };
    let exchange_position_mode = normalize_native_position_mode(&exchange_mode.position_mode);
    let matches_config = configured_position_mode == exchange_position_mode;
    NativeRuntimePositionModeSnapshot {
        configured_position_mode: configured_position_mode.clone(),
        exchange_position_mode: Some(exchange_position_mode.clone()),
        exchange_dual_side_position: Some(exchange_mode.dual_side_position),
        matches_config,
        signal_evaluation_allowed: matches_config,
        status_message: if matches_config {
            format!("Position mode reconciled: {configured_position_mode}.")
        } else {
            format!(
                "Position mode mismatch: config={configured_position_mode}, exchange={exchange_position_mode}."
            )
        },
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

pub fn normalize_native_position_mode(value: impl AsRef<str>) -> String {
    let normalized = value
        .as_ref()
        .trim()
        .to_ascii_lowercase()
        .replace(['_', ' '], "-");
    match normalized.as_str() {
        "one-way" | "oneway" => "One-way".to_owned(),
        _ => "Hedge".to_owned(),
    }
}

pub fn normalize_native_margin_mode(value: impl AsRef<str>) -> String {
    normalize_futures_margin_type(value.as_ref()).unwrap_or_else(|_| "ISOLATED".to_owned())
}

pub fn clamp_native_futures_leverage(value: i64) -> i64 {
    value.clamp(1, 125)
}

pub fn reconcile_native_futures_settings(
    symbol: impl AsRef<str>,
    configured_margin_mode: impl AsRef<str>,
    configured_leverage: i64,
    configured_multi_assets_mode: bool,
    input: NativeRuntimeFuturesSettingsInput,
) -> NativeRuntimeFuturesSettingsSnapshot {
    let symbol = non_empty_or(&symbol.as_ref().trim().to_uppercase(), "UNKNOWN");
    let configured_margin_mode = normalize_native_margin_mode(configured_margin_mode);
    let configured_leverage = clamp_native_futures_leverage(configured_leverage);
    let exchange_margin_mode = input
        .exchange_margin_mode
        .as_ref()
        .map(|mode| normalize_native_margin_mode(&mode.margin_type));
    let exchange_leverage = input
        .exchange_leverage
        .filter(|value| (1..=125).contains(value));
    let exchange_multi_assets_mode = input
        .exchange_multi_assets_mode
        .as_ref()
        .map(|mode| mode.multi_assets_margin);

    let margin_mode_matches_config =
        exchange_margin_mode.as_deref() == Some(configured_margin_mode.as_str());
    let leverage_matches_config = exchange_leverage == Some(configured_leverage);
    let multi_assets_matches_config =
        exchange_multi_assets_mode == Some(configured_multi_assets_mode);
    let open_position_blocks_margin_change = !margin_mode_matches_config
        && input.open_position_amt.is_finite()
        && input.open_position_amt.abs() > NATIVE_POSITION_EPSILON;
    let signal_evaluation_allowed = margin_mode_matches_config
        && leverage_matches_config
        && multi_assets_matches_config
        && !open_position_blocks_margin_change;

    let status_message = if signal_evaluation_allowed {
        format!(
            "Futures settings reconciled: margin={configured_margin_mode}, leverage={configured_leverage}x, multiAssets={}.",
            if configured_multi_assets_mode {
                "enabled"
            } else {
                "disabled"
            }
        )
    } else if open_position_blocks_margin_change {
        format!(
            "{symbol} is {} with an open position; refusing native signal evaluation until margin type can be changed to {configured_margin_mode}.",
            exchange_margin_mode.as_deref().unwrap_or("UNKNOWN")
        )
    } else if exchange_margin_mode.is_none()
        || exchange_leverage.is_none()
        || exchange_multi_assets_mode.is_none()
    {
        "Futures settings unknown; native runtime must reconcile margin mode, leverage, and assets mode before signal evaluation."
            .to_owned()
    } else {
        format!(
            "Futures settings mismatch: margin config={configured_margin_mode}, exchange={}; leverage config={configured_leverage}x, exchange={}x; multiAssets config={}, exchange={}.",
            exchange_margin_mode.as_deref().unwrap_or("UNKNOWN"),
            exchange_leverage
                .map(|value| value.to_string())
                .unwrap_or_else(|| "UNKNOWN".to_owned()),
            configured_multi_assets_mode,
            exchange_multi_assets_mode
                .map(|value| value.to_string())
                .unwrap_or_else(|| "UNKNOWN".to_owned()),
        )
    };

    NativeRuntimeFuturesSettingsSnapshot {
        symbol,
        configured_margin_mode,
        exchange_margin_mode,
        margin_mode_matches_config,
        configured_leverage,
        exchange_leverage,
        leverage_matches_config,
        configured_multi_assets_mode,
        exchange_multi_assets_mode,
        multi_assets_matches_config,
        open_position_blocks_margin_change,
        signal_evaluation_allowed,
        status_message,
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

pub fn evaluate_native_account_preflight(
    configured_position_mode: impl AsRef<str>,
    symbol: impl AsRef<str>,
    configured_margin_mode: impl AsRef<str>,
    configured_leverage: i64,
    configured_multi_assets_mode: bool,
    input: NativeRuntimeAccountPreflightInput,
) -> NativeRuntimeAccountPreflightSnapshot {
    let position_mode = reconcile_native_position_mode(
        configured_position_mode,
        input.exchange_position_mode.as_ref(),
    );
    let futures_settings = reconcile_native_futures_settings(
        symbol,
        configured_margin_mode,
        configured_leverage,
        configured_multi_assets_mode,
        input.futures_settings,
    );
    let signal_evaluation_allowed =
        position_mode.signal_evaluation_allowed && futures_settings.signal_evaluation_allowed;
    let status_message = if signal_evaluation_allowed {
        "Native account preflight passed: position mode and futures settings reconciled.".to_owned()
    } else {
        let mut reasons = Vec::new();
        if !position_mode.signal_evaluation_allowed {
            reasons.push(position_mode.status_message.clone());
        }
        if !futures_settings.signal_evaluation_allowed {
            reasons.push(futures_settings.status_message.clone());
        }
        format!("Native account preflight blocked: {}", reasons.join(" "))
    };

    NativeRuntimeAccountPreflightSnapshot {
        position_mode,
        futures_settings,
        signal_evaluation_allowed,
        status_message,
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

pub fn build_native_operational_preflight(
    input: NativeRuntimeOperationalPreflightInput,
) -> NativeRuntimeOperationalPreflightSnapshot {
    let generated_at_ms = input.generated_at_ms.max(0);
    let mut health = input.health.trim().to_ascii_lowercase();
    if health.is_empty() {
        health = "unknown".to_owned();
    }
    if input.connector_order_circuit_active {
        health = "error".to_owned();
    }

    let freshness = NativeRuntimeOperationalFreshnessSnapshot {
        exchange_connector: build_native_freshness_payload(
            &input.exchange_connector,
            generated_at_ms,
        ),
        execution: build_native_freshness_payload(&input.execution, generated_at_ms),
        account: build_native_freshness_payload(&input.account, generated_at_ms),
        portfolio: build_native_freshness_payload(&input.portfolio, generated_at_ms),
    };

    let mut start_stale_labels = Vec::new();
    let mut order_stale_labels = Vec::new();
    for (label, stale) in [
        ("exchange connector", freshness.exchange_connector.stale),
        ("account", freshness.account.stale),
        ("portfolio", freshness.portfolio.stale),
    ] {
        if stale {
            start_stale_labels.push(label.to_owned());
            order_stale_labels.push(label.to_owned());
        }
    }
    if freshness.execution.stale {
        start_stale_labels.push("execution heartbeat".to_owned());
    }

    let mut start_issues = native_preflight_issues(&health, &start_stale_labels);
    let mut order_issues = native_preflight_issues(&health, &order_stale_labels);
    if let Some(account_preflight) = &input.account_preflight {
        if !account_preflight.signal_evaluation_allowed {
            let reason = format!(
                "native account preflight is blocked: {}",
                account_preflight.status_message
            );
            push_unique_reason(&mut start_issues, reason.clone());
            push_unique_reason(&mut order_issues, reason);
        }
    }

    let live_mode = is_native_live_trading_mode(&input.mode);
    let start = build_native_preflight_gate(
        input.start_gate_enabled,
        live_mode,
        start_issues,
        "Operational live start safety gate is disabled.",
        "Demo/test mode start remains allowed.",
    );
    let orders = build_native_preflight_gate(
        input.order_gate_enabled,
        live_mode,
        order_issues,
        "Operational live order safety gate is disabled.",
        "Demo/test mode order remains allowed.",
    );

    let mut reasons = Vec::new();
    for reason in start.reasons.iter().chain(orders.reasons.iter()) {
        push_unique_reason(&mut reasons, reason.clone());
    }

    let state = if start.state == "blocked" || orders.state == "blocked" {
        "blocked"
    } else if start.state != "ok" || orders.state != "ok" {
        "warning"
    } else {
        "ok"
    }
    .to_owned();
    let message = if state == "blocked" {
        "Live preflight blocked. Review the reasons before starting or submitting orders."
    } else if state == "warning" {
        "Preflight has warnings. Live gate behavior depends on the enabled safety gates."
    } else {
        "Preflight passed. Start and order gates have fresh critical snapshots."
    }
    .to_owned();

    NativeRuntimeOperationalPreflightSnapshot {
        state,
        message,
        mode: input.mode,
        live_mode,
        generated_at_ms,
        start,
        orders,
        freshness,
        critical_stale: NativeRuntimeCriticalStaleSnapshot {
            start: start_stale_labels,
            orders: order_stale_labels,
        },
        reasons,
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

pub fn build_native_freshness_payload(
    input: &NativeRuntimeFreshnessInput,
    now_ms: i64,
) -> NativeRuntimeFreshnessSnapshot {
    let max_age_ms = input.max_age_ms.max(0);
    let age_ms = input.timestamp_ms.map(|timestamp_ms| {
        if now_ms > timestamp_ms {
            now_ms - timestamp_ms
        } else {
            0
        }
    });
    let stale = input.should_warn && age_ms.map_or(true, |age_ms| age_ms > max_age_ms);
    NativeRuntimeFreshnessSnapshot {
        stale,
        max_age_ms,
        age_ms,
        timestamp_ms: input.timestamp_ms,
        timestamp_field: non_empty_or(&input.timestamp_field, "generated_at"),
        state: input.state.trim().to_owned(),
        source: input.source.trim().to_owned(),
    }
}

pub fn is_native_live_trading_mode(mode: impl AsRef<str>) -> bool {
    let text = mode.as_ref().trim().to_ascii_lowercase();
    !text.is_empty()
        && !["demo", "test", "sandbox", "paper"]
            .iter()
            .any(|token| text.contains(token))
}

pub fn operational_preflight_start_allowed(
    preflight: &NativeRuntimeOperationalPreflightSnapshot,
) -> bool {
    preflight.start.allowed
}

pub fn operational_preflight_orders_allowed(
    preflight: &NativeRuntimeOperationalPreflightSnapshot,
) -> bool {
    preflight.orders.allowed
}

pub fn evaluate_native_exposure_guard(
    input: NativeRuntimeExposureGuardInput,
) -> NativeRuntimeExposureGuardSnapshot {
    let side = input.side.trim().to_uppercase();
    if !matches!(side.as_str(), "BUY" | "SELL") {
        return exposure_block("side must be BUY or SELL");
    }
    if !input.price.is_finite() || input.price <= 0.0 {
        return exposure_block("price must be > 0");
    }
    if input.leverage < 1 {
        return exposure_block("leverage must be >= 1");
    }
    if !input.position_pct_fraction.is_finite() || input.position_pct_fraction <= 0.0 {
        return exposure_block("position_pct_fraction must be > 0");
    }

    let leverage = input.leverage as f64;
    let available_usdt = finite_non_negative(input.available_usdt);
    let ledger_margin_total = finite_non_negative(input.ledger_margin_total);
    let wallet_usdt = finite_non_negative(input.wallet_usdt);
    let equity_usdt = wallet_usdt
        .max(available_usdt + ledger_margin_total)
        .max(ledger_margin_total);
    if equity_usdt <= 0.0 {
        return exposure_block("capital guard: no wallet equity to allocate");
    }

    let pct_fraction = if input.position_pct_fraction > 1.0 {
        input.position_pct_fraction / 100.0
    } else {
        input.position_pct_fraction
    };
    let target_margin_usdt = equity_usdt * pct_fraction;
    if target_margin_usdt <= 0.0 {
        return exposure_block("capital guard: computed margin target <= 0");
    }

    let margin_tolerance = normalize_ratio(input.margin_over_target_tolerance);
    let margin_filter_slippage = normalize_ratio(input.margin_filter_slippage);
    let filter_min_margin = filter_min_margin(
        input.filter_min_qty,
        input.filter_min_notional,
        input.price,
        leverage,
    );
    let filter_headroom = if filter_min_margin > 0.0 {
        filter_min_margin * 0.25
    } else {
        0.0
    };
    let max_indicator_margin_usdt = target_margin_usdt * (1.0 + margin_tolerance) + filter_headroom;
    let existing_indicator_margin = finite_non_negative(input.existing_indicator_margin);
    if existing_indicator_margin >= max_indicator_margin_usdt - 1e-9 {
        return exposure_block_with_values(
            format!(
                "{}@{} capital guard: existing {} margin already >= cap",
                non_empty_or(&input.symbol, "-"),
                non_empty_or(&input.interval, "-"),
                side
            ),
            equity_usdt,
            target_margin_usdt,
            max_indicator_margin_usdt,
            0.0,
            finite_non_negative(input.existing_side_margin),
            0.0,
            false,
            None,
        );
    }

    let flip_qty = input
        .flip_close_qty
        .filter(|value| value.is_finite() && *value > 0.0);
    let mut target_margin = if let Some(qty) = flip_qty {
        qty * input.price / leverage
    } else {
        (target_margin_usdt - existing_indicator_margin).max(0.0)
    };
    if target_margin <= 0.0 {
        return exposure_block_with_values(
            "capital guard: exposure already meets allocation target",
            equity_usdt,
            target_margin_usdt,
            max_indicator_margin_usdt,
            0.0,
            finite_non_negative(input.existing_side_margin),
            0.0,
            false,
            None,
        );
    }
    if available_usdt <= 0.0 {
        return exposure_block_with_values(
            "capital guard: no available USDT to allocate",
            equity_usdt,
            target_margin_usdt,
            max_indicator_margin_usdt,
            0.0,
            finite_non_negative(input.existing_side_margin),
            0.0,
            false,
            None,
        );
    }
    if available_usdt < target_margin * 0.95 {
        return exposure_block_with_values(
            "capital guard: requested margin exceeds available USDT",
            equity_usdt,
            target_margin_usdt,
            max_indicator_margin_usdt,
            0.0,
            finite_non_negative(input.existing_side_margin),
            0.0,
            false,
            None,
        );
    }

    let quantity_before_filter_adjustment = if let Some(qty) = flip_qty {
        qty
    } else {
        target_margin * leverage / input.price
    };
    let mut quantity_estimate = adjust_quantity_to_min_filters(
        quantity_before_filter_adjustment,
        input.price,
        input.filter_min_qty,
        input.filter_min_notional,
        input.filter_step_size,
    );
    if quantity_estimate <= 0.0 {
        return exposure_block("capital guard: quantity <= 0 after filter adjustment");
    }

    // Python only permits a live order to be enlarged to satisfy exchange filters
    // after an explicit opt-in.  The same cap also prevents a small requested
    // position percentage from becoming an unexpectedly large minimum order.
    let auto_bump_required =
        flip_qty.is_none() && quantity_estimate > quantity_before_filter_adjustment + 1e-12;
    if auto_bump_required {
        let requested_percent = pct_fraction * 100.0;
        let required_notional = quantity_estimate * input.price;
        let required_margin = required_notional / leverage;
        let required_percent = required_notional / (available_usdt * leverage) * 100.0;
        let multiplier = if input.auto_bump_percent_multiplier.is_finite()
            && input.auto_bump_percent_multiplier > 0.0
        {
            input.auto_bump_percent_multiplier
        } else {
            1.0
        };
        let allowed_percent =
            if input.max_auto_bump_percent.is_finite() && input.max_auto_bump_percent > 0.0 {
                input
                    .max_auto_bump_percent
                    .max(requested_percent * multiplier)
            } else {
                f64::INFINITY
            };
        if input.live_mode && !input.live_allow_auto_bump_to_min_order {
            return exposure_block_with_values(
                "live auto-bump to exchange minimum is disabled; increase position percent or enable live_allow_auto_bump_to_min_order explicitly",
                equity_usdt,
                target_margin_usdt,
                max_indicator_margin_usdt,
                required_margin,
                finite_non_negative(input.existing_side_margin),
                quantity_estimate,
                false,
                None,
            );
        }
        if required_margin > available_usdt * 1.01 || required_percent > allowed_percent + 1e-9 {
            return exposure_block_with_values(
                "capital guard: insufficient funds for exchange minimum order",
                equity_usdt,
                target_margin_usdt,
                max_indicator_margin_usdt,
                required_margin,
                finite_non_negative(input.existing_side_margin),
                quantity_estimate,
                false,
                None,
            );
        }
    }

    let margin_estimate_usdt = quantity_estimate * input.price / leverage;
    target_margin = margin_estimate_usdt;
    let mut indicator_soft_cap = max_indicator_margin_usdt * (1.0 + margin_filter_slippage);
    if filter_min_margin > max_indicator_margin_usdt {
        indicator_soft_cap =
            indicator_soft_cap.max(filter_min_margin * (1.0 + margin_filter_slippage));
    }
    if existing_indicator_margin + margin_estimate_usdt > indicator_soft_cap + 1e-6 {
        return exposure_block_with_values(
            "capital guard: adding margin would exceed indicator cap",
            equity_usdt,
            target_margin_usdt,
            max_indicator_margin_usdt,
            margin_estimate_usdt,
            finite_non_negative(input.existing_side_margin),
            quantity_estimate,
            false,
            None,
        );
    }

    let expected_slots_after = input
        .active_slot_count
        .saturating_add(usize::from(!input.slot_already_active))
        .max(1);
    let max_side_margin =
        target_margin_usdt * expected_slots_after as f64 * (1.0 + margin_tolerance)
            + filter_headroom;
    let mut side_soft_cap = max_side_margin * (1.0 + margin_filter_slippage);
    if filter_min_margin > max_side_margin {
        side_soft_cap = side_soft_cap.max(filter_min_margin * (1.0 + margin_filter_slippage));
    }
    let existing_side_margin = finite_non_negative(input.existing_side_margin);
    let projected_side_margin_usdt = existing_side_margin + margin_estimate_usdt;
    if projected_side_margin_usdt > side_soft_cap + 1e-6 {
        return exposure_block_with_values(
            "capital guard: projected side margin exceeds cap",
            equity_usdt,
            target_margin_usdt,
            max_indicator_margin_usdt,
            margin_estimate_usdt,
            projected_side_margin_usdt,
            quantity_estimate,
            false,
            None,
        );
    }

    let mut reduce_only = false;
    if input.add_only && !input.dual_side {
        let net_position_amt = if input.net_position_amt.is_finite() {
            input.net_position_amt
        } else {
            0.0
        };
        if (net_position_amt > 0.0 && side == "SELL") || (net_position_amt < 0.0 && side == "BUY") {
            quantity_estimate = quantity_estimate.min(net_position_amt.abs());
            reduce_only = true;
        }
        if quantity_estimate <= 0.0 {
            return exposure_block("opposite open blocked in one-way add-only mode");
        }
    }

    let desired_position_side = if input.dual_side {
        Some(if side == "BUY" { "LONG" } else { "SHORT" }.to_owned())
    } else {
        None
    };
    NativeRuntimeExposureGuardSnapshot {
        allowed: true,
        reason: "capital guard: allowed".to_owned(),
        equity_usdt,
        target_margin_usdt,
        max_indicator_margin_usdt,
        margin_estimate_usdt: target_margin,
        projected_side_margin_usdt,
        quantity_estimate,
        reduce_only,
        desired_position_side,
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

fn exposure_block(reason: impl Into<String>) -> NativeRuntimeExposureGuardSnapshot {
    exposure_block_with_values(reason, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, false, None)
}

fn exposure_block_with_values(
    reason: impl Into<String>,
    equity_usdt: f64,
    target_margin_usdt: f64,
    max_indicator_margin_usdt: f64,
    margin_estimate_usdt: f64,
    projected_side_margin_usdt: f64,
    quantity_estimate: f64,
    reduce_only: bool,
    desired_position_side: Option<String>,
) -> NativeRuntimeExposureGuardSnapshot {
    NativeRuntimeExposureGuardSnapshot {
        allowed: false,
        reason: reason.into(),
        equity_usdt,
        target_margin_usdt,
        max_indicator_margin_usdt,
        margin_estimate_usdt,
        projected_side_margin_usdt,
        quantity_estimate,
        reduce_only,
        desired_position_side,
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

fn native_preflight_issues(health: &str, stale_labels: &[String]) -> Vec<String> {
    let mut issues = Vec::new();
    if health == "error" {
        issues.push("operational health is error".to_owned());
    }
    if !stale_labels.is_empty() {
        issues.push(format!(
            "critical snapshots are stale: {}",
            stale_labels.join(", ")
        ));
    }
    issues
}

fn build_native_preflight_gate(
    enabled: bool,
    live_mode: bool,
    issues: Vec<String>,
    disabled_message: &str,
    demo_message: &str,
) -> NativeRuntimePreflightGate {
    if !enabled {
        return NativeRuntimePreflightGate {
            allowed: true,
            state: "warning".to_owned(),
            gate_enabled: false,
            reasons: vec![disabled_message.to_owned()],
        };
    }
    if issues.is_empty() {
        return NativeRuntimePreflightGate {
            allowed: true,
            state: "ok".to_owned(),
            gate_enabled: true,
            reasons: Vec::new(),
        };
    }
    if live_mode {
        return NativeRuntimePreflightGate {
            allowed: false,
            state: "blocked".to_owned(),
            gate_enabled: true,
            reasons: issues,
        };
    }
    let mut reasons = issues;
    reasons.push(demo_message.to_owned());
    NativeRuntimePreflightGate {
        allowed: true,
        state: "warning".to_owned(),
        gate_enabled: true,
        reasons,
    }
}

fn push_unique_reason(reasons: &mut Vec<String>, reason: impl Into<String>) {
    let reason = reason.into();
    let reason = reason.trim();
    if !reason.is_empty() && !reasons.iter().any(|existing| existing == reason) {
        reasons.push(reason.to_owned());
    }
}

fn finite_non_negative(value: f64) -> f64 {
    if value.is_finite() {
        value.max(0.0)
    } else {
        0.0
    }
}

fn normalize_ratio(value: f64) -> f64 {
    if !value.is_finite() || value <= 0.0 {
        0.0
    } else if value > 1.0 {
        value / 100.0
    } else {
        value
    }
}

fn filter_min_margin(min_qty: f64, min_notional: f64, price: f64, leverage: f64) -> f64 {
    if price <= 0.0 || leverage <= 0.0 {
        return 0.0;
    }
    let min_qty_margin = finite_non_negative(min_qty) * price / leverage;
    let min_notional_margin = finite_non_negative(min_notional) / leverage;
    min_qty_margin.max(min_notional_margin)
}

fn adjust_quantity_to_min_filters(
    quantity: f64,
    price: f64,
    min_qty: f64,
    min_notional: f64,
    step_size: f64,
) -> f64 {
    let mut adjusted = finite_non_negative(quantity);
    adjusted = adjusted.max(finite_non_negative(min_qty));
    if price > 0.0 && min_notional > 0.0 {
        adjusted = adjusted.max(min_notional / price);
    }
    if step_size.is_finite() && step_size > 0.0 {
        adjusted = (adjusted / step_size).ceil() * step_size;
    }
    adjusted
}

fn non_empty_or(value: &str, fallback: &str) -> String {
    let value = value.trim();
    if value.is_empty() {
        fallback.to_owned()
    } else {
        value.to_owned()
    }
}

fn guarded_execution_snapshot(
    market_cycle: NativeRuntimeReadOnlyMarketCycleSnapshot,
    exposure: Option<NativeRuntimeExposureGuardSnapshot>,
    order: Option<RuntimeOrderSubmitResult>,
    state: &str,
    status_message: &str,
) -> NativeRuntimeGuardedExecutionCycleSnapshot {
    NativeRuntimeGuardedExecutionCycleSnapshot {
        market_cycle,
        exposure,
        order,
        state: state.to_owned(),
        status_message: status_message.to_owned(),
        trading_execution_supported: rust_trading_execution_supported(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::account::BinanceFuturesPosition;
    use crate::order_audit::{ConnectorOrderCircuitBreakerConfig, OrderAuditConfig};
    use crate::order_guard::OrderSymbolFilters;
    use crate::position_close::BinanceFuturesCloseMethod;
    use crate::runtime_order_engine::RuntimeOrderEngine;
    use crate::streams::{BinanceKlineStreamCandle, BinanceStreamEvent};
    use anyhow::anyhow;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn loop_under_test() -> NativeRuntimeLoop {
        NativeRuntimeLoop::new(NativeRuntimeLoopConfig {
            symbol: "btcusdt".to_owned(),
            interval: "1m".to_owned(),
            position_mode: "Hedge".to_owned(),
            margin_mode: "ISOLATED".to_owned(),
            leverage: 5,
            multi_assets_mode: false,
            loop_interval_override: Some("5m".to_owned()),
            stream_reconnect_policy: StreamReconnectPolicy {
                base_delay_ms: 250,
                max_delay_ms: 5_000,
                reset_after_ms: 60_000,
                max_attempts: 3,
            },
            stream_stale_after_ms: 30_000,
        })
    }

    fn position(symbol: &str, amount: f64, position_side: &str) -> BinanceFuturesPosition {
        BinanceFuturesPosition {
            symbol: symbol.to_owned(),
            position_amt: amount,
            position_side: position_side.to_owned(),
            ..Default::default()
        }
    }

    fn position_mode(dual_side_position: bool) -> BinanceFuturesPositionMode {
        BinanceFuturesPositionMode {
            dual_side_position,
            position_mode: if dual_side_position {
                "Hedge".to_owned()
            } else {
                "One-way".to_owned()
            },
        }
    }

    fn margin_mode(symbol: &str, margin_type: &str) -> BinanceFuturesMarginMode {
        BinanceFuturesMarginMode {
            symbol: symbol.to_owned(),
            margin_type: margin_type.to_owned(),
        }
    }

    fn multi_assets_mode(enabled: bool) -> BinanceFuturesMultiAssetsMode {
        BinanceFuturesMultiAssetsMode {
            multi_assets_margin: enabled,
        }
    }

    fn freshness(
        now_ms: i64,
        age_ms: i64,
        max_age_ms: i64,
        state: &str,
        source: &str,
        timestamp_field: &str,
    ) -> NativeRuntimeFreshnessInput {
        NativeRuntimeFreshnessInput {
            timestamp_ms: Some(now_ms - age_ms),
            timestamp_field: timestamp_field.to_owned(),
            max_age_ms,
            should_warn: true,
            state: state.to_owned(),
            source: source.to_owned(),
        }
    }

    fn fresh_operational_preflight_input(
        runtime: &NativeRuntimeLoop,
        now_ms: i64,
    ) -> NativeRuntimeOperationalPreflightInput {
        NativeRuntimeOperationalPreflightInput {
            mode: "Live".to_owned(),
            health: "ok".to_owned(),
            generated_at_ms: now_ms,
            start_gate_enabled: true,
            order_gate_enabled: true,
            connector_order_circuit_active: false,
            exchange_connector: freshness(
                now_ms,
                30_000,
                120_000,
                "ready",
                "service",
                "generated_at",
            ),
            execution: freshness(now_ms, 3_000, 10_000, "running", "runtime", "heartbeat_at"),
            account: freshness(now_ms, 60_000, 300_000, "ready", "account", "generated_at"),
            portfolio: freshness(
                now_ms,
                60_000,
                300_000,
                "ready",
                "portfolio",
                "generated_at",
            ),
            account_preflight: Some(runtime.reconcile_account_preflight(
                NativeRuntimeAccountPreflightInput {
                    exchange_position_mode: Some(position_mode(true)),
                    futures_settings: NativeRuntimeFuturesSettingsInput {
                        exchange_margin_mode: Some(margin_mode("BTCUSDT", "isolated")),
                        exchange_leverage: Some(5),
                        exchange_multi_assets_mode: Some(multi_assets_mode(false)),
                        open_position_amt: 0.0,
                    },
                },
            )),
        }
    }

    fn exposure_input() -> NativeRuntimeExposureGuardInput {
        NativeRuntimeExposureGuardInput {
            symbol: "BTCUSDT".to_owned(),
            interval: "1m".to_owned(),
            side: "BUY".to_owned(),
            position_pct_fraction: 0.02,
            available_usdt: 100.0,
            wallet_usdt: 1_000.0,
            ledger_margin_total: 0.0,
            existing_indicator_margin: 0.0,
            existing_side_margin: 0.0,
            active_slot_count: 0,
            slot_already_active: false,
            price: 100.0,
            leverage: 5,
            filter_min_qty: 0.001,
            filter_min_notional: 5.0,
            filter_step_size: 0.001,
            flip_close_qty: None,
            live_mode: false,
            live_allow_auto_bump_to_min_order: false,
            max_auto_bump_percent: 5.0,
            auto_bump_percent_multiplier: 10.0,
            margin_over_target_tolerance: 0.05,
            margin_filter_slippage: 0.1,
            add_only: false,
            dual_side: true,
            net_position_amt: 0.0,
        }
    }

    fn guarded_market_cycle_input() -> NativeRuntimeReadOnlyMarketCycleInput {
        NativeRuntimeReadOnlyMarketCycleInput {
            now_ms: 1_700_000_010_000,
            candles: vec![
                market_candle(1_700_000_000_000, 10.0),
                market_candle(1_700_000_060_000, 11.0),
                market_candle(1_700_000_120_000, 12.0),
                market_candle(1_700_000_180_000, 13.0),
            ],
            indicator_configs: BTreeMap::new(),
            indicators: BTreeMap::from([("rsi".to_owned(), vec![50.0, 20.0, 80.0, 90.0])]),
            rules: BTreeMap::from([(
                "rsi".to_owned(),
                IndicatorRule {
                    enabled: true,
                    buy_value: Some(30.0),
                    sell_value: Some(70.0),
                },
            )]),
            side: "BOTH".to_owned(),
            last_candle_is_closed: false,
        }
    }

    fn guarded_execution_input(
        runtime: &NativeRuntimeLoop,
    ) -> NativeRuntimeGuardedExecutionCycleInput {
        NativeRuntimeGuardedExecutionCycleInput {
            market_cycle: guarded_market_cycle_input(),
            exposure: exposure_input(),
            filters: Some(OrderSymbolFilters {
                step_size: 0.001,
                tick_size: 0.1,
                min_qty: 0.001,
                min_notional: 5.0,
            }),
            market: "futures".to_owned(),
            connector_state: "ready".to_owned(),
            connector_health: "ok".to_owned(),
            operational_preflight: runtime.build_operational_preflight(
                fresh_operational_preflight_input(runtime, 1_700_000_010_000),
            ),
            now_iso: "2026-07-11T00:00:00Z".to_owned(),
            now_epoch_seconds: 1_783_728_000.0,
            source: "native-runtime-guarded-cycle-test".to_owned(),
        }
    }

    fn dry_run_engine() -> (RuntimeOrderEngine, std::path::PathBuf) {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock")
            .as_nanos();
        let directory = std::env::temp_dir().join(format!("trading-bot-guarded-cycle-{stamp}"));
        fs::create_dir_all(&directory).expect("audit directory");
        let engine = RuntimeOrderEngine::new(
            "paper",
            OrderAuditConfig {
                enabled: true,
                path: directory.join("audit.jsonl").display().to_string(),
                max_bytes: 64 * 1024,
                backup_count: 1,
            },
            ConnectorOrderCircuitBreakerConfig {
                enabled: true,
                block_threshold: 1,
                block_window_seconds: 60.0,
            },
            "bootstrap",
        );
        (engine, directory)
    }

    fn closed_kline(event_time_ms: i64) -> BinanceStreamEvent {
        BinanceStreamEvent::Kline(BinanceKlineStreamCandle {
            symbol: "BTCUSDT".to_owned(),
            interval: "1m".to_owned(),
            open_time_ms: event_time_ms - 60_000,
            open: 10.0,
            high: 12.0,
            low: 9.5,
            close: 11.0,
            volume: 100.0,
            is_closed: true,
            event_time_ms,
        })
    }

    fn market_candle(open_time_ms: i64, close: f64) -> BinanceKlineCandle {
        BinanceKlineCandle {
            open_time_ms,
            open: close - 0.5,
            high: close + 0.5,
            low: close - 1.0,
            close,
            volume: 100.0,
        }
    }

    #[test]
    fn native_runtime_loop_wires_stream_supervision_to_lifecycle_snapshot() {
        let mut runtime = loop_under_test();
        runtime.start();

        let fresh = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_010_000,
            stream_event: Some(closed_kline(1_700_000_009_000)),
            stream_disconnected: false,
        });
        assert_eq!(fresh.lifecycle["lifecycle_phase"], "running");
        assert_eq!(fresh.lifecycle["execution_owner"], "python-service");
        assert_eq!(fresh.lifecycle["native_trading_execution_enabled"], false);
        assert_eq!(fresh.lifecycle["loop_interval_seconds"], 300.0);
        assert!(!fresh.stream.kline_cache_health.stale);
        assert!(fresh.signal_evaluation_allowed);
        assert!(!fresh.trading_execution_supported);

        let stale = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_040_001,
            stream_event: None,
            stream_disconnected: false,
        });
        assert!(stale.stream.kline_cache_health.stale);
        assert!(!stale.signal_evaluation_allowed);
    }

    #[test]
    fn native_runtime_loop_wires_disconnect_reconnect_backoff_into_worker_state() {
        let mut runtime = loop_under_test();
        runtime.start();
        runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_010_000,
            stream_event: Some(closed_kline(1_700_000_009_000)),
            stream_disconnected: false,
        });

        let disconnected = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_011_000,
            stream_event: None,
            stream_disconnected: true,
        });
        assert!(disconnected.stream.reconnect_decision.should_reconnect);
        assert_eq!(disconnected.stream.reconnect_decision.next_attempt, 1);
        assert_eq!(disconnected.lifecycle["offline_backoff"], 0.25);
        assert!(!disconnected.signal_evaluation_allowed);
    }

    #[test]
    fn native_runtime_loop_wires_stop_guard_and_idle_transition() {
        let mut runtime = loop_under_test();
        runtime.start();

        let stop = runtime.request_stop(true, "tauri", true, "Forwarded to worker.");
        assert!(stop.accepted);
        assert_eq!(stop.lifecycle_phase, "stopping");
        assert!(stop.close_positions_requested);

        let stopping = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_010_000,
            stream_event: Some(closed_kline(1_700_000_009_000)),
            stream_disconnected: false,
        });
        assert_eq!(stopping.lifecycle["lifecycle_phase"], "stopping");
        assert!(!stopping.signal_evaluation_allowed);

        let idle = runtime.mark_idle_after_stop("tauri", "");
        assert_eq!(idle.lifecycle_phase, "idle");
        assert!(!idle.runtime_active);
        assert_eq!(idle.status_message, "Runtime idle after stop request.");

        let snapshot = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_010_100,
            stream_event: None,
            stream_disconnected: false,
        });
        assert_eq!(snapshot.lifecycle["lifecycle_phase"], "idle");
        assert_eq!(snapshot.lifecycle["active_engine_count"], 0);
    }

    #[test]
    fn native_runtime_loop_wires_pause_and_shutdown_without_enabling_trading() {
        let mut runtime = loop_under_test();
        runtime.start();
        runtime.set_global_pause(true);

        let paused = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_010_000,
            stream_event: Some(closed_kline(1_700_000_009_000)),
            stream_disconnected: false,
        });
        assert_eq!(paused.lifecycle["lifecycle_phase"], "paused");
        assert!(!paused.signal_evaluation_allowed);
        assert!(!paused.trading_execution_supported);

        runtime.set_global_pause(false);
        runtime.request_shutdown();
        let shutdown = runtime.run_cycle(NativeRuntimeCycleInput {
            now_ms: 1_700_000_010_100,
            stream_event: None,
            stream_disconnected: false,
        });
        assert_eq!(shutdown.lifecycle["lifecycle_phase"], "shutdown");
        assert!(!shutdown.signal_evaluation_allowed);
        assert!(!shutdown.trading_execution_supported);
    }

    #[test]
    fn native_runtime_read_only_market_cycle_uses_completed_rest_candles_without_orders() {
        let mut runtime = loop_under_test();
        runtime.start();
        let snapshot = runtime
            .run_read_only_market_cycle(NativeRuntimeReadOnlyMarketCycleInput {
                now_ms: 1_700_000_010_000,
                candles: vec![
                    market_candle(1_700_000_000_000, 10.0),
                    market_candle(1_700_000_060_000, 11.0),
                    market_candle(1_700_000_120_000, 12.0),
                    market_candle(1_700_000_180_000, 13.0),
                ],
                indicator_configs: std::collections::BTreeMap::new(),
                indicators: std::collections::BTreeMap::from([(
                    "rsi".to_owned(),
                    // The fourth value belongs to the in-progress REST candle and
                    // must be discarded with that candle. Without lockstep trimming,
                    // the closed-candle strategy would incorrectly emit SELL.
                    vec![50.0, 20.0, 80.0, 90.0],
                )]),
                rules: std::collections::BTreeMap::from([(
                    "rsi".to_owned(),
                    IndicatorRule {
                        enabled: true,
                        buy_value: Some(30.0),
                        sell_value: Some(70.0),
                    },
                )]),
                side: "BOTH".to_owned(),
                last_candle_is_closed: false,
            })
            .expect("read-only market cycle");

        assert_eq!(snapshot.closed_candle_count, 3);
        assert_eq!(snapshot.latest_closed_open_time_ms, 1_700_000_120_000);
        assert!(snapshot.cycle.stream.connected);
        assert!(!snapshot.cycle.stream.kline_cache_health.stale);
        assert!(snapshot.strategy_evaluated);
        assert_eq!(
            snapshot
                .strategy_decision
                .as_ref()
                .and_then(|decision| decision.signal.as_deref()),
            Some("BUY")
        );
        assert!(snapshot.status_message.contains("signal=BUY"));
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn guarded_execution_cycle_audits_a_valid_paper_signal_without_calling_executor() {
        let mut runtime = loop_under_test();
        runtime.start();
        let (mut engine, directory) = dry_run_engine();

        let snapshot = runtime
            .run_guarded_execution_cycle(&mut engine, guarded_execution_input(&runtime), |_| {
                panic!("dry-run cycle must not invoke the exchange executor")
            })
            .expect("guarded cycle");

        assert_eq!(snapshot.state, "accepted");
        assert!(!snapshot.trading_execution_supported);
        assert_eq!(
            snapshot
                .market_cycle
                .strategy_decision
                .as_ref()
                .and_then(|decision| decision.signal.as_deref()),
            Some("BUY")
        );
        assert!(snapshot.exposure.as_ref().expect("exposure").allowed);
        let order = snapshot.order.as_ref().expect("order result");
        assert!(order.allowed, "{}", order.error);
        assert_eq!(
            order.order_result.as_ref().expect("dry run").status,
            "DRY_RUN"
        );
        let audit = fs::read_to_string(directory.join("audit.jsonl")).expect("audit");
        assert!(audit.contains("order_dry_run"));
        fs::remove_dir_all(directory).ok();
    }

    #[test]
    fn guarded_execution_cycle_refuses_non_dry_run_without_runtime_promotion() {
        let mut runtime = loop_under_test();
        runtime.start();
        let (mut engine, directory) = dry_run_engine();
        engine.dry_run = false;

        let snapshot = runtime
            .run_guarded_execution_cycle(&mut engine, guarded_execution_input(&runtime), |_| {
                panic!("runtime policy must block native exchange execution")
            })
            .expect("guarded cycle");

        assert_eq!(snapshot.state, "blocked");
        assert!(snapshot.order.is_none());
        assert!(snapshot.status_message.contains("not runtime-ready"));
        fs::remove_dir_all(directory).ok();
    }

    #[test]
    fn guarded_execution_cycle_cannot_bypass_blocked_operational_preflight() {
        let mut runtime = loop_under_test();
        runtime.start();
        let (mut engine, directory) = dry_run_engine();
        let mut input = guarded_execution_input(&runtime);
        let mut preflight_input = fresh_operational_preflight_input(&runtime, 1_700_000_010_000);
        preflight_input.health = "error".to_owned();
        input.operational_preflight = runtime.build_operational_preflight(preflight_input);

        let snapshot = runtime
            .run_guarded_execution_cycle(&mut engine, input, |_| {
                panic!("blocked preflight must not reach the exchange executor")
            })
            .expect("guarded cycle");

        assert_eq!(snapshot.state, "blocked");
        assert!(snapshot.order.is_none());
        assert!(
            snapshot
                .status_message
                .contains("operational health is error")
        );
        fs::remove_dir_all(directory).ok();
    }

    #[test]
    fn native_runtime_cycle_input_hydrates_python_service_config_payload_and_rules() {
        let input = NativeRuntimeReadOnlyMarketCycleInput::from_python_service_config(
            1_700_000_010_000,
            vec![market_candle(1_700_000_000_000, 10.0)],
            &serde_json::json!({
                "config": {
                    "side": "BUY",
                    "indicators": {
                        "rsi": {"enabled": "true", "length": 3, "buy_value": "30", "sell_value": 70},
                        "volume": {"enabled": false, "buy_value": 1.0}
                    }
                }
            }),
            true,
        )
        .expect("Python service config should hydrate native cycle input");

        assert_eq!(input.side, "BUY");
        assert_eq!(input.indicator_configs.len(), 2);
        assert!(input.rules["rsi"].enabled);
        assert_eq!(input.rules["rsi"].buy_value, Some(30.0));
        assert_eq!(input.rules["rsi"].sell_value, Some(70.0));
        assert!(!input.rules["volume"].enabled);
    }

    #[test]
    fn native_runtime_cycle_input_rejects_malformed_python_service_config() {
        let error = NativeRuntimeReadOnlyMarketCycleInput::from_python_service_config(
            1_700_000_010_000,
            Vec::new(),
            &serde_json::json!({"config": {"indicators": {"rsi": true}}}),
            true,
        )
        .expect_err("non-object indicator config must fail closed");
        assert!(
            error
                .to_string()
                .contains("indicator rsi must be an object")
        );
    }

    #[test]
    fn native_runtime_read_only_market_cycle_rejects_unclosed_or_invalid_candle_sets() {
        let mut runtime = loop_under_test();
        runtime.start();
        let error = runtime
            .run_read_only_market_cycle(NativeRuntimeReadOnlyMarketCycleInput {
                now_ms: 1_700_000_010_000,
                candles: vec![market_candle(1_700_000_000_000, 10.0)],
                indicator_configs: std::collections::BTreeMap::new(),
                indicators: std::collections::BTreeMap::new(),
                rules: std::collections::BTreeMap::new(),
                side: "BOTH".to_owned(),
                last_candle_is_closed: false,
            })
            .expect_err("last open candle must not be evaluated");
        assert!(error.to_string().contains("no completed finite candles"));
    }

    #[test]
    fn native_runtime_read_only_market_cycle_computes_caller_selected_python_configs() {
        let mut runtime = loop_under_test();
        runtime.start();
        let snapshot = runtime
            .run_read_only_market_cycle(NativeRuntimeReadOnlyMarketCycleInput {
                now_ms: 1_700_000_010_000,
                candles: vec![
                    market_candle(1_700_000_000_000, 10.0),
                    market_candle(1_700_000_060_000, 11.0),
                    market_candle(1_700_000_120_000, 12.0),
                ],
                indicator_configs: std::collections::BTreeMap::from([(
                    "ma".to_owned(),
                    serde_json::json!({"enabled": true, "length": 2, "type": "SMA"}),
                )]),
                indicators: std::collections::BTreeMap::new(),
                rules: std::collections::BTreeMap::new(),
                side: "BOTH".to_owned(),
                last_candle_is_closed: true,
            })
            .expect("read-only market cycle should calculate supported Python config");

        assert_eq!(snapshot.computed_indicator_keys, vec!["ma"]);
        assert!(snapshot.strategy_evaluated);
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_read_only_market_cycle_withholds_unknown_enabled_python_indicator() {
        let mut runtime = loop_under_test();
        runtime.start();
        let snapshot = runtime
            .run_read_only_market_cycle(NativeRuntimeReadOnlyMarketCycleInput {
                now_ms: 1_700_000_010_000,
                candles: vec![
                    market_candle(1_700_000_000_000, 10.0),
                    market_candle(1_700_000_060_000, 11.0),
                ],
                indicator_configs: std::collections::BTreeMap::from([(
                    "future_python_indicator".to_owned(),
                    serde_json::json!({"enabled": true}),
                )]),
                indicators: std::collections::BTreeMap::new(),
                rules: std::collections::BTreeMap::new(),
                side: "BOTH".to_owned(),
                last_candle_is_closed: true,
            })
            .expect("unsupported configs should fail closed without failing the read-only cycle");

        assert_eq!(
            snapshot.unsupported_indicator_keys,
            vec!["future_python_indicator"]
        );
        assert!(!snapshot.strategy_evaluated);
        assert!(snapshot.strategy_decision.is_none());
        assert!(
            snapshot
                .status_message
                .contains("unsupported indicators: future_python_indicator")
        );
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_live_ingestion_bridge_feeds_stream_events_into_cycle() {
        let mut runtime = loop_under_test();
        runtime.start();

        let snapshot = runtime.run_stream_ingestion_cycle(1_700_000_010_000, || {
            Ok(Some(closed_kline(1_700_000_009_000)))
        });

        assert_eq!(snapshot.poll_status, "event");
        assert!(snapshot.poll_error.is_none());
        assert!(snapshot.cycle.stream.connected);
        assert!(!snapshot.cycle.stream.kline_cache_health.stale);
        assert!(snapshot.cycle.signal_evaluation_allowed);
        assert!(!snapshot.cycle.trading_execution_supported);
        assert_eq!(snapshot.cycle.status_message, "Stream event ingested.");
    }

    #[test]
    fn native_runtime_live_ingestion_bridge_marks_closed_stream_for_reconnect() {
        let mut runtime = loop_under_test();
        runtime.start();

        let snapshot = runtime.run_stream_ingestion_cycle(1_700_000_010_000, || Ok(None));

        assert_eq!(snapshot.poll_status, "closed");
        assert!(!snapshot.cycle.stream.connected);
        assert!(snapshot.cycle.stream.reconnect_decision.should_reconnect);
        assert!(!snapshot.cycle.signal_evaluation_allowed);
        assert_eq!(
            snapshot.cycle.status_message,
            "Stream closed; reconnect required."
        );
    }

    #[test]
    fn native_runtime_live_ingestion_bridge_redacts_errors_and_recovers() {
        let mut runtime = loop_under_test();
        runtime.start();

        let failed = runtime.run_stream_ingestion_cycle(1_700_000_010_000, || {
            Err(anyhow!("socket failed apiSecret=super-secret-value"))
        });
        assert_eq!(failed.poll_status, "error");
        assert!(
            failed
                .poll_error
                .as_deref()
                .unwrap_or("")
                .contains("<redacted>")
        );
        assert!(
            !failed
                .poll_error
                .as_deref()
                .unwrap_or("")
                .contains("super-secret-value")
        );
        assert!(!failed.cycle.stream.connected);
        assert!(failed.cycle.stream.reconnect_decision.should_reconnect);
        assert!(!failed.cycle.signal_evaluation_allowed);

        let recovered = runtime.run_stream_ingestion_cycle(1_700_000_010_500, || {
            Ok(Some(closed_kline(1_700_000_010_000)))
        });
        assert_eq!(recovered.poll_status, "event");
        assert!(recovered.cycle.stream.connected);
        assert!(!recovered.cycle.stream.reconnect_decision.should_reconnect);
        assert!(recovered.cycle.signal_evaluation_allowed);
        assert!(!recovered.cycle.trading_execution_supported);
    }

    #[test]
    fn native_runtime_rest_ingestion_uses_latest_closed_candle_without_cache_duplicates() {
        let mut runtime = loop_under_test();
        runtime.start();
        let candles = vec![
            market_candle(1_700_000_000_000, 101.0),
            market_candle(1_700_000_060_000, 102.0),
        ];

        let first =
            runtime.run_rest_kline_ingestion_cycle(1_700_000_061_000, || Ok(candles.clone()));
        assert_eq!(first.poll_status, "rest_closed_kline");
        assert!(first.poll_error.is_none());
        assert!(first.cycle.stream.connected);
        assert_eq!(
            first
                .cycle
                .stream
                .kline_cache_health
                .latest_closed_open_time_ms,
            Some(1_700_000_000_000)
        );
        assert!(first.cycle.signal_evaluation_allowed);
        assert_eq!(first.cycle.status_message, "REST closed kline ingested.");

        let second =
            runtime.run_rest_kline_ingestion_cycle(1_700_000_062_000, || Ok(candles.clone()));
        assert_eq!(second.poll_status, "rest_closed_kline");
        assert_eq!(second.cycle.stream.kline_cache_health.candle_count, 1);
        assert!(second.cycle.signal_evaluation_allowed);
        assert!(!second.cycle.trading_execution_supported);
    }

    #[test]
    fn native_runtime_rest_ingestion_redacts_failures_and_blocks_signal_evaluation() {
        let mut runtime = loop_under_test();
        runtime.start();

        let snapshot = runtime.run_rest_kline_ingestion_cycle(1_700_000_010_000, || {
            Err(anyhow!("REST request failed apiSecret=super-secret-value"))
        });
        assert_eq!(snapshot.poll_status, "rest_error");
        assert!(
            snapshot
                .poll_error
                .as_deref()
                .unwrap_or("")
                .contains("<redacted>")
        );
        assert!(
            !snapshot
                .poll_error
                .as_deref()
                .unwrap_or("")
                .contains("super-secret-value")
        );
        assert!(!snapshot.cycle.signal_evaluation_allowed);
        assert!(snapshot.cycle.stream.reconnect_decision.should_reconnect);
    }

    #[test]
    fn native_runtime_rest_ingestion_rejects_insufficient_or_stale_candles() {
        let mut runtime = loop_under_test();
        runtime.start();

        let insufficient = runtime.run_rest_kline_ingestion_cycle(1_700_000_010_000, || {
            Ok(vec![market_candle(1_700_000_000_000, 101.0)])
        });
        assert_eq!(insufficient.poll_status, "rest_error");
        assert!(
            insufficient
                .poll_error
                .as_deref()
                .unwrap_or("")
                .contains("requires at least two candles")
        );
        assert!(!insufficient.cycle.signal_evaluation_allowed);

        let stale = runtime.run_rest_kline_ingestion_cycle(1_700_000_091_000, || {
            Ok(vec![
                market_candle(1_700_000_000_000, 101.0),
                market_candle(1_700_000_060_000, 102.0),
            ])
        });
        assert_eq!(stale.poll_status, "rest_closed_kline");
        assert!(stale.cycle.stream.kline_cache_health.stale);
        assert!(!stale.cycle.signal_evaluation_allowed);
    }

    #[test]
    fn native_runtime_normalizes_position_mode_like_python_config_choices() {
        assert_eq!(normalize_native_position_mode("Hedge"), "Hedge");
        assert_eq!(normalize_native_position_mode("hedge"), "Hedge");
        assert_eq!(normalize_native_position_mode("One-way"), "One-way");
        assert_eq!(normalize_native_position_mode("One Way"), "One-way");
        assert_eq!(normalize_native_position_mode("oneway"), "One-way");
        assert_eq!(normalize_native_position_mode("unexpected"), "Hedge");
    }

    #[test]
    fn native_runtime_reconciles_position_mode_before_signal_evaluation() {
        let runtime = loop_under_test();

        let matched = runtime.reconcile_position_mode(Some(&position_mode(true)));
        assert!(matched.matches_config);
        assert!(matched.signal_evaluation_allowed);
        assert_eq!(matched.configured_position_mode, "Hedge");
        assert_eq!(matched.exchange_position_mode.as_deref(), Some("Hedge"));
        assert_eq!(matched.status_message, "Position mode reconciled: Hedge.");
        assert!(!matched.trading_execution_supported);

        let mismatched = runtime.reconcile_position_mode(Some(&position_mode(false)));
        assert!(!mismatched.matches_config);
        assert!(!mismatched.signal_evaluation_allowed);
        assert_eq!(
            mismatched.exchange_position_mode.as_deref(),
            Some("One-way")
        );
        assert_eq!(
            mismatched.status_message,
            "Position mode mismatch: config=Hedge, exchange=One-way."
        );
        assert!(!mismatched.trading_execution_supported);

        let missing = runtime.reconcile_position_mode(None);
        assert!(!missing.matches_config);
        assert!(!missing.signal_evaluation_allowed);
        assert_eq!(missing.exchange_position_mode, None);
        assert!(missing.status_message.contains("Position mode unknown"));
    }

    #[test]
    fn native_runtime_normalizes_futures_settings_like_python_config_choices() {
        assert_eq!(normalize_native_margin_mode("cross"), "CROSSED");
        assert_eq!(normalize_native_margin_mode("crossed"), "CROSSED");
        assert_eq!(normalize_native_margin_mode("isolated"), "ISOLATED");
        assert_eq!(normalize_native_margin_mode("unexpected"), "ISOLATED");
        assert_eq!(clamp_native_futures_leverage(0), 1);
        assert_eq!(clamp_native_futures_leverage(20), 20);
        assert_eq!(clamp_native_futures_leverage(150), 125);
    }

    #[test]
    fn native_runtime_reconciles_margin_leverage_and_assets_before_signal_evaluation() {
        let runtime = loop_under_test();

        let matched = runtime.reconcile_futures_settings(NativeRuntimeFuturesSettingsInput {
            exchange_margin_mode: Some(margin_mode("BTCUSDT", "isolated")),
            exchange_leverage: Some(5),
            exchange_multi_assets_mode: Some(multi_assets_mode(false)),
            open_position_amt: 0.0,
        });
        assert!(matched.margin_mode_matches_config);
        assert!(matched.leverage_matches_config);
        assert!(matched.multi_assets_matches_config);
        assert!(matched.signal_evaluation_allowed);
        assert_eq!(matched.configured_margin_mode, "ISOLATED");
        assert_eq!(matched.exchange_margin_mode.as_deref(), Some("ISOLATED"));
        assert_eq!(matched.configured_leverage, 5);
        assert_eq!(matched.exchange_leverage, Some(5));
        assert!(!matched.configured_multi_assets_mode);
        assert_eq!(matched.exchange_multi_assets_mode, Some(false));
        assert!(
            matched
                .status_message
                .contains("Futures settings reconciled")
        );
        assert!(!matched.trading_execution_supported);

        let missing = runtime.reconcile_futures_settings(NativeRuntimeFuturesSettingsInput {
            exchange_margin_mode: None,
            exchange_leverage: None,
            exchange_multi_assets_mode: None,
            open_position_amt: 0.0,
        });
        assert!(!missing.signal_evaluation_allowed);
        assert!(!missing.margin_mode_matches_config);
        assert!(!missing.leverage_matches_config);
        assert!(!missing.multi_assets_matches_config);
        assert!(missing.status_message.contains("Futures settings unknown"));
    }

    #[test]
    fn native_runtime_blocks_margin_mismatch_with_open_position_like_python() {
        let runtime = loop_under_test();

        let blocked = runtime.reconcile_futures_settings(NativeRuntimeFuturesSettingsInput {
            exchange_margin_mode: Some(margin_mode("BTCUSDT", "cross")),
            exchange_leverage: Some(5),
            exchange_multi_assets_mode: Some(multi_assets_mode(false)),
            open_position_amt: 0.25,
        });

        assert_eq!(blocked.configured_margin_mode, "ISOLATED");
        assert_eq!(blocked.exchange_margin_mode.as_deref(), Some("CROSSED"));
        assert!(!blocked.margin_mode_matches_config);
        assert!(blocked.leverage_matches_config);
        assert!(blocked.multi_assets_matches_config);
        assert!(blocked.open_position_blocks_margin_change);
        assert!(!blocked.signal_evaluation_allowed);
        assert!(blocked.status_message.contains("open position"));
        assert!(!blocked.trading_execution_supported);

        let mismatched_leverage =
            runtime.reconcile_futures_settings(NativeRuntimeFuturesSettingsInput {
                exchange_margin_mode: Some(margin_mode("BTCUSDT", "isolated")),
                exchange_leverage: Some(20),
                exchange_multi_assets_mode: Some(multi_assets_mode(false)),
                open_position_amt: 0.0,
            });
        assert!(mismatched_leverage.margin_mode_matches_config);
        assert!(!mismatched_leverage.leverage_matches_config);
        assert!(!mismatched_leverage.signal_evaluation_allowed);
        assert!(
            mismatched_leverage
                .status_message
                .contains("Futures settings mismatch")
        );
    }

    #[test]
    fn native_runtime_account_preflight_combines_position_and_futures_settings_gates() {
        let runtime = loop_under_test();

        let passed = runtime.reconcile_account_preflight(NativeRuntimeAccountPreflightInput {
            exchange_position_mode: Some(position_mode(true)),
            futures_settings: NativeRuntimeFuturesSettingsInput {
                exchange_margin_mode: Some(margin_mode("BTCUSDT", "isolated")),
                exchange_leverage: Some(5),
                exchange_multi_assets_mode: Some(multi_assets_mode(false)),
                open_position_amt: 0.0,
            },
        });
        assert!(passed.position_mode.signal_evaluation_allowed);
        assert!(passed.futures_settings.signal_evaluation_allowed);
        assert!(passed.signal_evaluation_allowed);
        assert_eq!(
            passed.status_message,
            "Native account preflight passed: position mode and futures settings reconciled."
        );
        assert!(!passed.trading_execution_supported);

        let blocked_position =
            runtime.reconcile_account_preflight(NativeRuntimeAccountPreflightInput {
                exchange_position_mode: Some(position_mode(false)),
                futures_settings: NativeRuntimeFuturesSettingsInput {
                    exchange_margin_mode: Some(margin_mode("BTCUSDT", "isolated")),
                    exchange_leverage: Some(5),
                    exchange_multi_assets_mode: Some(multi_assets_mode(false)),
                    open_position_amt: 0.0,
                },
            });
        assert!(!blocked_position.position_mode.signal_evaluation_allowed);
        assert!(blocked_position.futures_settings.signal_evaluation_allowed);
        assert!(!blocked_position.signal_evaluation_allowed);
        assert!(
            blocked_position
                .status_message
                .contains("Position mode mismatch")
        );

        let blocked_settings =
            runtime.reconcile_account_preflight(NativeRuntimeAccountPreflightInput {
                exchange_position_mode: Some(position_mode(true)),
                futures_settings: NativeRuntimeFuturesSettingsInput {
                    exchange_margin_mode: Some(margin_mode("BTCUSDT", "crossed")),
                    exchange_leverage: Some(5),
                    exchange_multi_assets_mode: Some(multi_assets_mode(false)),
                    open_position_amt: 0.2,
                },
            });
        assert!(blocked_settings.position_mode.signal_evaluation_allowed);
        assert!(!blocked_settings.futures_settings.signal_evaluation_allowed);
        assert!(
            blocked_settings
                .futures_settings
                .open_position_blocks_margin_change
        );
        assert!(!blocked_settings.signal_evaluation_allowed);
        assert!(blocked_settings.status_message.contains("open position"));
    }

    #[test]
    fn native_runtime_read_only_account_bootstrap_reuses_account_preflight_without_orders() {
        let runtime = loop_under_test();
        let balance = BinanceAccountSnapshot {
            asset: "USDT".to_owned(),
            usdt_balance: 1_000.0,
            total_usdt_balance: 1_000.0,
            available_usdt_balance: 900.0,
        };
        let mut configured_position = position("BTCUSDT", 0.25, "LONG");
        configured_position.margin_type = "isolated".to_owned();
        configured_position.leverage = 5.0;
        let mut other_position = position("ETHUSDT", 1.0, "LONG");
        other_position.margin_type = "cross".to_owned();
        other_position.leverage = 20.0;

        let snapshot = runtime.bootstrap_read_only_account(
            &balance,
            &[configured_position, other_position],
            Some(&position_mode(true)),
            Some(&multi_assets_mode(false)),
        );

        assert_eq!(snapshot.balance_asset, "USDT");
        assert_eq!(snapshot.open_positions_count, 2);
        assert!(snapshot.configured_symbol_position_found);
        assert_eq!(snapshot.configured_symbol_open_position_amt, 0.25);
        assert!(snapshot.account_preflight.signal_evaluation_allowed);
        assert!(snapshot.signal_evaluation_allowed);
        assert!(snapshot.status_message.contains("passed reconciliation"));
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_read_only_account_bootstrap_fails_closed_without_symbol_settings() {
        let runtime = loop_under_test();
        let balance = BinanceAccountSnapshot {
            asset: "USDT".to_owned(),
            usdt_balance: 1_000.0,
            total_usdt_balance: 1_000.0,
            available_usdt_balance: 900.0,
        };

        let snapshot = runtime.bootstrap_read_only_account(
            &balance,
            &[position("ETHUSDT", 1.0, "LONG")],
            Some(&position_mode(true)),
            Some(&multi_assets_mode(false)),
        );

        assert!(!snapshot.configured_symbol_position_found);
        assert!(!snapshot.signal_evaluation_allowed);
        assert!(
            snapshot
                .status_message
                .contains("safe but not signal-ready")
        );
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_read_only_account_bootstrap_keeps_hedged_exposure_and_conflicts_fail_closed()
    {
        let runtime = loop_under_test();
        let balance = BinanceAccountSnapshot {
            asset: "USDT".to_owned(),
            usdt_balance: 1_000.0,
            total_usdt_balance: 1_000.0,
            available_usdt_balance: 900.0,
        };
        let mut long = position("BTCUSDT", 0.25, "LONG");
        long.margin_type = "isolated".to_owned();
        long.leverage = 5.0;
        let mut short = position("BTCUSDT", -0.25, "SHORT");
        short.margin_type = "isolated".to_owned();
        short.leverage = 5.0;

        let reconciled = runtime.bootstrap_read_only_account(
            &balance,
            &[long.clone(), short.clone()],
            Some(&position_mode(true)),
            Some(&multi_assets_mode(false)),
        );
        assert_eq!(reconciled.configured_symbol_open_position_amt, 0.5);
        assert!(reconciled.signal_evaluation_allowed);

        short.leverage = 20.0;
        let conflicting = runtime.bootstrap_read_only_account(
            &balance,
            &[long, short],
            Some(&position_mode(true)),
            Some(&multi_assets_mode(false)),
        );
        assert_eq!(conflicting.configured_symbol_open_position_amt, 0.5);
        assert!(!conflicting.signal_evaluation_allowed);
        assert!(
            conflicting
                .account_preflight
                .futures_settings
                .status_message
                .contains("Futures settings unknown")
        );
    }

    #[test]
    fn native_runtime_operational_preflight_blocks_live_start_and_orders_like_python() {
        let runtime = loop_under_test();
        let now_ms = 1_718_711_400_000;
        let blocked_account =
            runtime.reconcile_account_preflight(NativeRuntimeAccountPreflightInput {
                exchange_position_mode: Some(position_mode(false)),
                futures_settings: NativeRuntimeFuturesSettingsInput {
                    exchange_margin_mode: Some(margin_mode("BTCUSDT", "crossed")),
                    exchange_leverage: Some(20),
                    exchange_multi_assets_mode: Some(multi_assets_mode(true)),
                    open_position_amt: 0.2,
                },
            });

        let mut input = fresh_operational_preflight_input(&runtime, now_ms);
        input.health = "ok".to_owned();
        input.connector_order_circuit_active = true;
        input.exchange_connector =
            freshness(now_ms, 121_000, 120_000, "ready", "service", "generated_at");
        input.execution = freshness(now_ms, 11_000, 10_000, "running", "runtime", "heartbeat_at");
        input.account = freshness(now_ms, 301_000, 300_000, "ready", "account", "generated_at");
        input.portfolio = freshness(
            now_ms,
            301_000,
            300_000,
            "ready",
            "portfolio",
            "generated_at",
        );
        input.account_preflight = Some(blocked_account);

        let preflight = runtime.build_operational_preflight(input);
        assert_eq!(preflight.state, "blocked");
        assert_eq!(
            preflight.message,
            "Live preflight blocked. Review the reasons before starting or submitting orders."
        );
        assert!(preflight.live_mode);
        assert!(!operational_preflight_start_allowed(&preflight));
        assert!(!operational_preflight_orders_allowed(&preflight));
        assert!(preflight.start.gate_enabled);
        assert!(preflight.orders.gate_enabled);
        assert!(
            preflight
                .critical_stale
                .start
                .contains(&"execution heartbeat".to_owned())
        );
        assert!(
            !preflight
                .critical_stale
                .orders
                .contains(&"execution heartbeat".to_owned())
        );
        assert!(
            preflight
                .reasons
                .contains(&"operational health is error".to_owned())
        );
        assert!(preflight.reasons.contains(&(
            "critical snapshots are stale: exchange connector, account, portfolio, execution heartbeat"
                .to_owned()
        )));
        assert!(preflight.reasons.contains(
            &("critical snapshots are stale: exchange connector, account, portfolio".to_owned())
        ));
        assert!(
            preflight
                .reasons
                .iter()
                .any(|reason| reason.contains("native account preflight is blocked"))
        );
        assert!(!preflight.trading_execution_supported);
    }

    #[test]
    fn native_runtime_operational_preflight_warns_in_demo_mode_like_python() {
        let runtime = loop_under_test();
        let now_ms = 1_718_711_400_000;
        let mut input = fresh_operational_preflight_input(&runtime, now_ms);
        input.mode = "Demo/Testnet".to_owned();
        input.health = "error".to_owned();
        input.exchange_connector =
            freshness(now_ms, 121_000, 120_000, "ready", "service", "generated_at");
        input.execution = freshness(now_ms, 11_000, 10_000, "running", "runtime", "heartbeat_at");
        input.account = freshness(now_ms, 301_000, 300_000, "ready", "account", "generated_at");
        input.portfolio = freshness(
            now_ms,
            301_000,
            300_000,
            "ready",
            "portfolio",
            "generated_at",
        );

        let preflight = runtime.build_operational_preflight(input);
        assert_eq!(preflight.state, "warning");
        assert_eq!(
            preflight.message,
            "Preflight has warnings. Live gate behavior depends on the enabled safety gates."
        );
        assert!(!preflight.live_mode);
        assert!(operational_preflight_start_allowed(&preflight));
        assert!(operational_preflight_orders_allowed(&preflight));
        assert!(
            preflight
                .reasons
                .contains(&"Demo/test mode start remains allowed.".to_owned())
        );
        assert!(
            preflight
                .reasons
                .contains(&"Demo/test mode order remains allowed.".to_owned())
        );
    }

    #[test]
    fn native_runtime_operational_preflight_warns_when_live_gates_are_disabled() {
        let runtime = loop_under_test();
        let now_ms = 1_718_711_400_000;
        let mut input = fresh_operational_preflight_input(&runtime, now_ms);
        input.start_gate_enabled = false;
        input.order_gate_enabled = false;

        let preflight = runtime.build_operational_preflight(input);
        assert_eq!(preflight.state, "warning");
        assert!(operational_preflight_start_allowed(&preflight));
        assert!(operational_preflight_orders_allowed(&preflight));
        assert!(!preflight.start.gate_enabled);
        assert!(!preflight.orders.gate_enabled);
        assert!(
            preflight
                .reasons
                .contains(&"Operational live start safety gate is disabled.".to_owned())
        );
        assert!(
            preflight
                .reasons
                .contains(&"Operational live order safety gate is disabled.".to_owned())
        );
    }

    #[test]
    fn native_runtime_operational_preflight_passes_with_fresh_critical_snapshots() {
        let runtime = loop_under_test();
        let now_ms = 1_718_711_400_000;

        let preflight = runtime
            .build_operational_preflight(fresh_operational_preflight_input(&runtime, now_ms));
        assert_eq!(preflight.state, "ok");
        assert_eq!(
            preflight.message,
            "Preflight passed. Start and order gates have fresh critical snapshots."
        );
        assert!(preflight.live_mode);
        assert!(operational_preflight_start_allowed(&preflight));
        assert!(operational_preflight_orders_allowed(&preflight));
        assert!(preflight.critical_stale.start.is_empty());
        assert!(preflight.critical_stale.orders.is_empty());
        assert!(preflight.reasons.is_empty());
        assert_eq!(preflight.freshness.execution.age_ms, Some(3_000));
        assert_eq!(
            preflight.freshness.execution.timestamp_field,
            "heartbeat_at"
        );
        assert!(!preflight.trading_execution_supported);
    }

    #[test]
    fn native_runtime_plans_hedge_mode_close_with_position_side() {
        let mut runtime = loop_under_test();
        let snapshot = runtime
            .plan_close_positions(NativeRuntimeClosePlanningInput {
                positions: vec![position("ethusdt", 1.23456, "LONG")],
                step_size_by_symbol: vec![("ETHUSDT".to_owned(), 0.001)],
                prefer_close_position: true,
            })
            .expect("hedge close planning");

        assert_eq!(snapshot.position_mode, "Hedge");
        assert!(snapshot.hedge_mode);
        assert!(!snapshot.trading_execution_supported);
        assert_eq!(snapshot.directives.len(), 2);

        let close_position = &snapshot.directives[0];
        assert_eq!(
            close_position.method,
            BinanceFuturesCloseMethod::ClosePosition
        );
        assert_eq!(close_position.side, "SELL");
        assert_eq!(close_position.position_side, "LONG");
        assert!(close_position.close_position);
        assert_eq!(
            close_position.to_order_params().expect("params").params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("closePosition", "true".to_owned()),
                ("positionSide", "LONG".to_owned()),
            ]
        );

        let fallback = &snapshot.directives[1];
        assert_eq!(fallback.method, BinanceFuturesCloseMethod::ReduceOnly);
        assert_eq!(fallback.quantity_text, "1.234");
        assert!(!fallback.reduce_only);
        assert_eq!(
            fallback.to_order_params().expect("fallback params").params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "1.234".to_owned()),
                ("positionSide", "LONG".to_owned()),
            ]
        );
    }

    #[test]
    fn native_runtime_plans_one_way_close_with_reduce_only() {
        let mut runtime = loop_under_test();
        runtime.config.position_mode = "One-Way".to_owned();

        let snapshot = runtime
            .plan_close_positions(NativeRuntimeClosePlanningInput {
                positions: vec![position("btcusdt", -0.125, "BOTH")],
                step_size_by_symbol: vec![("BTCUSDT".to_owned(), 0.001)],
                prefer_close_position: false,
            })
            .expect("one-way close planning");

        assert_eq!(snapshot.position_mode, "One-way");
        assert!(!snapshot.hedge_mode);
        assert!(!snapshot.trading_execution_supported);
        assert_eq!(snapshot.directives.len(), 1);

        let directive = &snapshot.directives[0];
        assert_eq!(directive.method, BinanceFuturesCloseMethod::ReduceOnly);
        assert_eq!(directive.side, "BUY");
        assert_eq!(directive.position_side, "");
        assert_eq!(directive.quantity_text, "0.125");
        assert!(directive.reduce_only);
        assert_eq!(
            directive.to_order_params().expect("params").params,
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("side", "BUY".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "0.125".to_owned()),
                ("reduceOnly", "true".to_owned()),
            ]
        );
    }

    #[test]
    fn native_runtime_exposure_guard_allows_position_within_python_capital_guard() {
        let runtime = loop_under_test();
        let snapshot = runtime.evaluate_exposure_guard(exposure_input());

        assert!(snapshot.allowed);
        assert_eq!(snapshot.reason, "capital guard: allowed");
        assert_eq!(snapshot.target_margin_usdt, 20.0);
        assert_eq!(snapshot.quantity_estimate, 1.0);
        assert_eq!(snapshot.margin_estimate_usdt, 20.0);
        assert_eq!(snapshot.projected_side_margin_usdt, 20.0);
        assert_eq!(snapshot.desired_position_side.as_deref(), Some("LONG"));
        assert!(!snapshot.reduce_only);
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_exposure_guard_blocks_existing_indicator_margin_over_cap() {
        let runtime = loop_under_test();
        let mut input = exposure_input();
        input.existing_indicator_margin = 22.0;

        let snapshot = runtime.evaluate_exposure_guard(input);

        assert!(!snapshot.allowed);
        assert!(
            snapshot
                .reason
                .contains("existing BUY margin already >= cap")
        );
        assert_eq!(snapshot.target_margin_usdt, 20.0);
        assert_eq!(snapshot.max_indicator_margin_usdt, 21.25);
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_exposure_guard_blocks_unavailable_margin_like_python() {
        let runtime = loop_under_test();
        let mut input = exposure_input();
        input.available_usdt = 10.0;

        let snapshot = runtime.evaluate_exposure_guard(input);

        assert!(!snapshot.allowed);
        assert_eq!(
            snapshot.reason,
            "capital guard: requested margin exceeds available USDT"
        );
        assert_eq!(snapshot.target_margin_usdt, 20.0);
        assert!(!snapshot.trading_execution_supported);
    }

    #[test]
    fn native_runtime_exposure_guard_requires_live_auto_bump_opt_in() {
        let runtime = loop_under_test();
        let mut input = exposure_input();
        input.position_pct_fraction = 0.0001;
        input.live_mode = true;
        input.filter_min_qty = 0.05;
        input.filter_min_notional = 5.0;

        let snapshot = runtime.evaluate_exposure_guard(input);

        assert!(!snapshot.allowed);
        assert!(snapshot.reason.contains("live auto-bump"));
    }

    #[test]
    fn native_runtime_exposure_guard_allows_live_auto_bump_when_explicitly_enabled() {
        let runtime = loop_under_test();
        let mut input = exposure_input();
        input.position_pct_fraction = 0.0001;
        input.live_mode = true;
        input.live_allow_auto_bump_to_min_order = true;
        input.filter_min_qty = 0.05;
        input.filter_min_notional = 5.0;

        let snapshot = runtime.evaluate_exposure_guard(input);

        assert!(snapshot.allowed);
        assert_eq!(snapshot.quantity_estimate, 0.05);
    }

    #[test]
    fn native_runtime_exposure_guard_converts_one_way_add_only_flip_to_reduce_only() {
        let runtime = loop_under_test();
        let mut input = exposure_input();
        input.side = "SELL".to_owned();
        input.dual_side = false;
        input.add_only = true;
        input.net_position_amt = 0.5;

        let snapshot = runtime.evaluate_exposure_guard(input);

        assert!(snapshot.allowed);
        assert!(snapshot.reduce_only);
        assert_eq!(snapshot.quantity_estimate, 0.5);
        assert_eq!(snapshot.desired_position_side, None);
        assert!(!snapshot.trading_execution_supported);
    }
}
