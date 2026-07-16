#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, State};
use trading_bot_core::{
    account::{
        BinanceAccountSnapshot, BinanceApiCredentials, BinanceFuturesMultiAssetsMode,
        BinanceFuturesPosition, BinanceFuturesPositionMode, BinanceSignedRestClient,
    },
    app_banner,
    config_persistence::{
        load_service_config_file, service_config_file_status, write_service_config_file,
    },
    exchange_connectors::DEFAULT_CONNECTOR_BACKEND,
    market_data::{BinanceKlineCandle, BinanceMarket, BinanceRestMarketDataClient},
    native_python_app_contract_parity_ready,
    native_runtime::{
        NativeRuntimeAccountPreflightSnapshot, NativeRuntimeClosePlanningInput,
        NativeRuntimeCycleInput, NativeRuntimeExposureGuardInput, NativeRuntimeFreshnessInput,
        NativeRuntimeGuardedExecutionCycleInput, NativeRuntimeGuardedExecutionCycleSnapshot,
        NativeRuntimeLoop, NativeRuntimeLoopConfig, NativeRuntimeOperationalPreflightInput,
        NativeRuntimeReadOnlyMarketCycleInput,
    },
    order_audit::{ConnectorOrderCircuitBreakerConfig, OrderAuditConfig},
    order_guard::{LiveTradingSafetyConfig, OrderSymbolFilters},
    orders::BinanceFuturesSymbolFilters,
    python_source_contract_hash,
    runtime_order_engine::RuntimeOrderEngine,
    rust_trading_execution_supported, service_api_route_path, service_api_route_supports_method,
    service_api_route_supports_query_field, service_api_route_supports_request_field,
    supported_frameworks,
};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Debug, Serialize)]
struct ServiceApiProxyResponse {
    ok: bool,
    status: u16,
    route_name: String,
    path: String,
    payload: Value,
    error: String,
}

#[derive(Debug, Serialize)]
struct NativeConfigPersistenceResponse {
    ok: bool,
    config: Value,
    persistence: Value,
    error: String,
}

impl NativeConfigPersistenceResponse {
    fn error(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            config: Value::Null,
            persistence: service_config_file_status(None),
            error: error.into(),
        }
    }
}

#[derive(Default)]
struct ServiceProcessState {
    child: Mutex<Option<Child>>,
}

#[derive(Default)]
struct NativeRuntimeManagedState {
    runtime: Option<NativeRuntimeLoop>,
    order_engine: Option<RuntimeOrderEngine>,
    market_poll_spec: Option<NativeRuntimeMarketPollSpec>,
    account_bootstrap: Option<NativeRuntimeAccountBootstrapState>,
    started_at_ms: Option<i64>,
    running: bool,
    paused: bool,
}

#[derive(Default)]
struct NativeRuntimeState {
    inner: Mutex<NativeRuntimeManagedState>,
}

#[derive(Debug, Serialize)]
struct NativeRuntimeControlResponse {
    ok: bool,
    execution_backend: String,
    status: Value,
    lifecycle: Value,
    stream: Value,
    trading_execution_supported: bool,
    promotion_required: bool,
    message: String,
    error: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NativeRuntimeMarketPollSpec {
    market: BinanceMarket,
    symbol: String,
    interval: String,
    testnet: bool,
}

#[derive(Debug, Serialize)]
struct NativeRuntimeMarketPollResponse {
    ok: bool,
    market: String,
    symbol: String,
    interval: String,
    testnet: bool,
    candle_count: usize,
    poll_status: String,
    signal_evaluation_allowed: bool,
    strategy_evaluated: bool,
    signal: Option<String>,
    trading_execution_supported: bool,
    status_message: String,
    error: String,
}

#[derive(Debug, Clone)]
struct NativeRuntimeAccountBootstrapState {
    refreshed_at_ms: i64,
    signal_evaluation_allowed: bool,
    status_message: String,
    balance: BinanceAccountSnapshot,
    positions: Vec<BinanceFuturesPosition>,
    position_mode: BinanceFuturesPositionMode,
    multi_assets_mode: BinanceFuturesMultiAssetsMode,
}

#[derive(Debug, Serialize)]
struct NativeRuntimeAccountPollResponse {
    ok: bool,
    market: String,
    symbol: String,
    testnet: bool,
    balance_asset: String,
    total_balance: f64,
    available_balance: f64,
    open_positions_count: usize,
    configured_symbol_position_found: bool,
    configured_symbol_open_position_amt: f64,
    position_mode: String,
    multi_assets_mode: bool,
    signal_evaluation_allowed: bool,
    status_message: String,
    error: String,
}

#[derive(Debug, Serialize)]
struct NativeRuntimeExecutionResponse {
    ok: bool,
    state: String,
    signal: Option<String>,
    order_id: String,
    order_status: String,
    executed_qty: f64,
    dry_run: bool,
    trading_execution_supported: bool,
    promotion_required: bool,
    message: String,
    error: String,
}

impl NativeRuntimeMarketPollResponse {
    fn error(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            market: String::new(),
            symbol: String::new(),
            interval: String::new(),
            testnet: false,
            candle_count: 0,
            poll_status: String::new(),
            signal_evaluation_allowed: false,
            strategy_evaluated: false,
            signal: None,
            trading_execution_supported: rust_trading_execution_supported(),
            status_message: String::new(),
            error: error.into(),
        }
    }
}

impl NativeRuntimeAccountPollResponse {
    fn error(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            market: String::new(),
            symbol: String::new(),
            testnet: false,
            balance_asset: String::new(),
            total_balance: 0.0,
            available_balance: 0.0,
            open_positions_count: 0,
            configured_symbol_position_found: false,
            configured_symbol_open_position_amt: 0.0,
            position_mode: String::new(),
            multi_assets_mode: false,
            signal_evaluation_allowed: false,
            status_message: String::new(),
            error: error.into(),
        }
    }
}

impl NativeRuntimeExecutionResponse {
    fn error(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            state: "blocked".to_owned(),
            signal: None,
            order_id: String::new(),
            order_status: String::new(),
            executed_qty: 0.0,
            dry_run: !rust_trading_execution_supported(),
            trading_execution_supported: rust_trading_execution_supported(),
            promotion_required: !rust_trading_execution_supported(),
            message: String::new(),
            error: error.into(),
        }
    }

    fn from_snapshot(snapshot: NativeRuntimeGuardedExecutionCycleSnapshot) -> Self {
        let signal = snapshot
            .market_cycle
            .strategy_decision
            .as_ref()
            .and_then(|decision| decision.signal.clone());
        let order = snapshot
            .order
            .as_ref()
            .and_then(|result| result.order_result.as_ref());
        let order_id = order
            .map(|result| result.order_id.clone())
            .unwrap_or_default();
        let order_status = order
            .map(|result| result.status.clone())
            .unwrap_or_default();
        let executed_qty = order.map(|result| result.executed_qty).unwrap_or_default();
        let dry_run = order_status.eq_ignore_ascii_case("DRY_RUN");
        Self {
            ok: snapshot.state != "blocked",
            state: snapshot.state,
            signal,
            order_id,
            order_status,
            executed_qty,
            dry_run,
            trading_execution_supported: snapshot.trading_execution_supported,
            promotion_required: !snapshot.trading_execution_supported,
            message: snapshot.status_message,
            error: String::new(),
        }
    }
}

impl NativeRuntimeControlResponse {
    fn error(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            execution_backend: "native-rust".to_owned(),
            status: json!({
                "runtime_active": false,
                "active_duration": "--",
                "lifecycle_phase": "error"
            }),
            lifecycle: json!({}),
            stream: json!({}),
            trading_execution_supported: rust_trading_execution_supported(),
            promotion_required: !rust_trading_execution_supported(),
            message: String::new(),
            error: error.into(),
        }
    }
}

impl NativeRuntimeState {
    fn start(&self, config: &Value, now_ms: i64) -> NativeRuntimeControlResponse {
        let market_poll_spec = match native_runtime_market_poll_spec(config) {
            Ok(spec) => spec,
            Err(error) => return NativeRuntimeControlResponse::error(error),
        };
        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeControlResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        if managed.running {
            return native_runtime_snapshot(
                &mut managed,
                now_ms,
                "Native Rust runtime is already running.",
            );
        }

        let mut runtime = NativeRuntimeLoop::new(native_runtime_config(config));
        runtime.start();
        managed.runtime = Some(runtime);
        managed.order_engine = Some(native_runtime_order_engine(config, now_ms));
        managed.market_poll_spec = Some(market_poll_spec);
        managed.account_bootstrap = None;
        managed.started_at_ms = Some(now_ms);
        managed.running = true;
        managed.paused = false;
        native_runtime_snapshot(
            &mut managed,
            now_ms,
            if rust_trading_execution_supported() {
                "Native Rust runtime started."
            } else {
                "Native Rust runtime started in fail-closed coordination mode; live order submission remains promotion-gated."
            },
        )
    }

    fn status(&self, now_ms: i64) -> NativeRuntimeControlResponse {
        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeControlResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        native_runtime_snapshot(
            &mut managed,
            now_ms,
            "Native Rust runtime status refreshed.",
        )
    }

    fn set_paused(&self, paused: bool, now_ms: i64) -> NativeRuntimeControlResponse {
        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeControlResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        if !managed.running {
            return NativeRuntimeControlResponse::error("Native Rust runtime is not running.");
        }
        let Some(runtime) = managed.runtime.as_mut() else {
            return NativeRuntimeControlResponse::error(
                "Native Rust runtime state is unavailable.",
            );
        };
        runtime.set_global_pause(paused);
        managed.paused = paused;
        native_runtime_snapshot(
            &mut managed,
            now_ms,
            if paused {
                "Native Rust runtime paused."
            } else {
                "Native Rust runtime resumed."
            },
        )
    }

    fn stop_with_close_request(
        &self,
        close_positions: bool,
        config: Value,
        api_key: String,
        api_secret: String,
        now_ms: i64,
    ) -> NativeRuntimeControlResponse {
        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeControlResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        if !managed.running {
            return native_runtime_snapshot(
                &mut managed,
                now_ms,
                "Native Rust runtime is already idle.",
            );
        }
        if managed.runtime.is_none() {
            return NativeRuntimeControlResponse::error(
                "Native Rust runtime state is unavailable.",
            );
        }

        // The promoted runtime closes against a freshly reconciled account snapshot.
        // Before promotion this must remain side-effect free: the coordinator has not
        // submitted native live orders and must not issue an unverified close request.
        let mut close_status_message = String::new();
        let close_dispatched = if !close_positions {
            false
        } else if !rust_trading_execution_supported() {
            close_status_message =
                "Close positions was not dispatched because native live execution is not promoted."
                    .to_owned();
            false
        } else {
            match dispatch_native_runtime_position_closes(
                &mut managed,
                &config,
                api_key,
                api_secret,
                now_ms,
            ) {
                Ok(message) => {
                    close_status_message = message;
                    true
                }
                Err(error) => {
                    close_status_message =
                        format!("Native close-all was not completed before shutdown: {error}");
                    false
                }
            }
        };
        let Some(runtime) = managed.runtime.as_mut() else {
            return NativeRuntimeControlResponse::error(
                "Native Rust runtime state is unavailable.",
            );
        };
        let stop = runtime.request_stop(
            close_dispatched,
            "tauri-native-runtime",
            true,
            if !close_status_message.is_empty() {
                &close_status_message
            } else {
                "Native runtime stop accepted."
            },
        );
        runtime.mark_idle_after_stop("tauri-native-runtime", &stop.status_message);
        managed.market_poll_spec = None;
        managed.account_bootstrap = None;
        managed.order_engine = None;
        managed.running = false;
        managed.paused = false;
        managed.started_at_ms = None;
        native_runtime_snapshot(
            &mut managed,
            now_ms,
            if !close_status_message.is_empty() {
                format!("Native Rust runtime stopped. {close_status_message}")
            } else {
                "Native Rust runtime stopped.".to_owned()
            },
        )
    }

    fn poll_market(&self, config: &Value, now_ms: i64) -> NativeRuntimeMarketPollResponse {
        let spec = match native_runtime_market_poll_spec(config) {
            Ok(spec) => spec,
            Err(error) => return NativeRuntimeMarketPollResponse::error(error),
        };
        {
            let managed = match self.inner.lock() {
                Ok(value) => value,
                Err(_) => {
                    return NativeRuntimeMarketPollResponse::error(
                        "Native runtime state lock is poisoned.",
                    );
                }
            };
            if !managed.running {
                return NativeRuntimeMarketPollResponse::error(
                    "Native Rust runtime is not running.",
                );
            }
            if managed.market_poll_spec.as_ref() != Some(&spec) {
                return NativeRuntimeMarketPollResponse::error(
                    "Native runtime market configuration changed; stop and restart the runtime before polling.",
                );
            }
        }
        let mut input = match NativeRuntimeReadOnlyMarketCycleInput::from_python_service_config(
            now_ms,
            Vec::new(),
            config,
            false,
        ) {
            Ok(input) => input,
            Err(error) => return NativeRuntimeMarketPollResponse::error(error.to_string()),
        };
        let client = match BinanceRestMarketDataClient::new(spec.market, spec.testnet) {
            Ok(client) => client,
            Err(error) => return NativeRuntimeMarketPollResponse::error(error.to_string()),
        };
        let candles = match client.fetch_klines(&spec.symbol, &spec.interval, 500) {
            Ok(candles) => candles,
            Err(error) => return NativeRuntimeMarketPollResponse::error(error.to_string()),
        };
        input.candles = candles.clone();

        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeMarketPollResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        if !managed.running {
            return NativeRuntimeMarketPollResponse::error("Native Rust runtime is not running.");
        }
        if managed.market_poll_spec.as_ref() != Some(&spec) {
            return NativeRuntimeMarketPollResponse::error(
                "Native runtime market configuration changed; stop and restart the runtime before polling.",
            );
        }
        let account_bootstrap = managed.account_bootstrap.clone();
        let account_ready = account_bootstrap
            .as_ref()
            .filter(|snapshot| native_runtime_account_bootstrap_is_fresh(snapshot, now_ms))
            .filter(|snapshot| snapshot.signal_evaluation_allowed);
        let Some(runtime) = managed.runtime.as_mut() else {
            return NativeRuntimeMarketPollResponse::error(
                "Native Rust runtime state is unavailable.",
            );
        };

        let ingestion = runtime.run_rest_kline_ingestion_cycle(now_ms, || Ok(candles.clone()));
        if ingestion.poll_status != "rest_closed_kline" {
            return NativeRuntimeMarketPollResponse {
                ok: false,
                market: native_runtime_market_label(spec.market).to_owned(),
                symbol: spec.symbol,
                interval: spec.interval,
                testnet: spec.testnet,
                candle_count: candles.len(),
                poll_status: ingestion.poll_status,
                signal_evaluation_allowed: ingestion.cycle.signal_evaluation_allowed,
                strategy_evaluated: false,
                signal: None,
                trading_execution_supported: ingestion.cycle.trading_execution_supported,
                status_message: ingestion.cycle.status_message,
                error: ingestion
                    .poll_error
                    .unwrap_or_else(|| "REST market poll failed.".to_owned()),
            };
        }
        let Some(account_bootstrap) = account_ready else {
            let account_status = account_bootstrap
                .as_ref()
                .map(|snapshot| snapshot.status_message.as_str())
                .unwrap_or(
                    "Read-only native account bootstrap is required before signal evaluation.",
                );
            return NativeRuntimeMarketPollResponse {
                ok: true,
                market: native_runtime_market_label(spec.market).to_owned(),
                symbol: spec.symbol,
                interval: spec.interval,
                testnet: spec.testnet,
                candle_count: candles.len(),
                poll_status: ingestion.poll_status,
                signal_evaluation_allowed: false,
                strategy_evaluated: false,
                signal: None,
                trading_execution_supported: rust_trading_execution_supported(),
                status_message: format!(
                    "Read-only native market data refreshed; signal evaluation is withheld until a fresh account bootstrap passes: {account_status}"
                ),
                error: String::new(),
            };
        };
        match runtime.run_read_only_market_cycle(input) {
            Ok(snapshot) => NativeRuntimeMarketPollResponse {
                ok: true,
                market: native_runtime_market_label(spec.market).to_owned(),
                symbol: spec.symbol,
                interval: spec.interval,
                testnet: spec.testnet,
                candle_count: candles.len(),
                poll_status: ingestion.poll_status,
                signal_evaluation_allowed: snapshot.cycle.signal_evaluation_allowed
                    && account_bootstrap.signal_evaluation_allowed,
                strategy_evaluated: snapshot.strategy_evaluated,
                signal: snapshot
                    .strategy_decision
                    .and_then(|decision| decision.signal),
                trading_execution_supported: snapshot.trading_execution_supported,
                status_message: snapshot.status_message,
                error: String::new(),
            },
            Err(error) => NativeRuntimeMarketPollResponse::error(error.to_string()),
        }
    }

    fn poll_account(
        &self,
        config: &Value,
        api_key: String,
        api_secret: String,
        now_ms: i64,
    ) -> NativeRuntimeAccountPollResponse {
        let spec = match native_runtime_market_poll_spec(config) {
            Ok(spec) => spec,
            Err(error) => return NativeRuntimeAccountPollResponse::error(error),
        };
        {
            let managed = match self.inner.lock() {
                Ok(value) => value,
                Err(_) => {
                    return NativeRuntimeAccountPollResponse::error(
                        "Native runtime state lock is poisoned.",
                    );
                }
            };
            if !managed.running {
                return NativeRuntimeAccountPollResponse::error(
                    "Native Rust runtime is not running.",
                );
            }
            if managed.market_poll_spec.as_ref() != Some(&spec) {
                return NativeRuntimeAccountPollResponse::error(
                    "Native runtime market configuration changed; stop and restart the runtime before polling.",
                );
            }
        }
        if api_key.trim().is_empty() || api_secret.trim().is_empty() {
            self.clear_account_bootstrap(&spec);
            return NativeRuntimeAccountPollResponse::error(
                "API key and API secret are required for the read-only native account bootstrap.",
            );
        }
        let credentials = BinanceApiCredentials::new(api_key, api_secret);
        let client = match BinanceSignedRestClient::new(spec.market, spec.testnet) {
            Ok(client) => client,
            Err(error) => {
                self.clear_account_bootstrap(&spec);
                return NativeRuntimeAccountPollResponse::error(error.to_string());
            }
        };
        let position_mode = match client.fetch_futures_position_mode(&credentials) {
            Ok(value) => value,
            Err(error) => {
                self.clear_account_bootstrap(&spec);
                return NativeRuntimeAccountPollResponse::error(error.to_string());
            }
        };
        let multi_assets_mode = match client.fetch_futures_multi_assets_mode(&credentials) {
            Ok(value) => value,
            Err(error) => {
                self.clear_account_bootstrap(&spec);
                return NativeRuntimeAccountPollResponse::error(error.to_string());
            }
        };
        let balance = match client.fetch_usdt_balance(&credentials) {
            Ok(value) => value,
            Err(error) => {
                self.clear_account_bootstrap(&spec);
                return NativeRuntimeAccountPollResponse::error(error.to_string());
            }
        };
        let positions = match client.fetch_open_futures_positions(&credentials) {
            Ok(value) => value,
            Err(error) => {
                self.clear_account_bootstrap(&spec);
                return NativeRuntimeAccountPollResponse::error(error.to_string());
            }
        };

        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeAccountPollResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        if !managed.running {
            return NativeRuntimeAccountPollResponse::error("Native Rust runtime is not running.");
        }
        if managed.market_poll_spec.as_ref() != Some(&spec) {
            return NativeRuntimeAccountPollResponse::error(
                "Native runtime market configuration changed; stop and restart the runtime before polling.",
            );
        }
        let Some(runtime) = managed.runtime.as_ref() else {
            return NativeRuntimeAccountPollResponse::error(
                "Native Rust runtime state is unavailable.",
            );
        };
        let snapshot = runtime.bootstrap_read_only_account(
            &balance,
            &positions,
            Some(&position_mode),
            Some(&multi_assets_mode),
        );
        let total_balance = balance.total_usdt_balance;
        let available_balance = balance.available_usdt_balance;
        let position_mode_label = position_mode.position_mode.clone();
        let multi_assets_enabled = multi_assets_mode.multi_assets_margin;
        managed.account_bootstrap = Some(NativeRuntimeAccountBootstrapState {
            refreshed_at_ms: now_ms.max(0),
            signal_evaluation_allowed: snapshot.signal_evaluation_allowed,
            status_message: snapshot.status_message.clone(),
            balance,
            positions,
            position_mode,
            multi_assets_mode,
        });
        NativeRuntimeAccountPollResponse {
            ok: true,
            market: native_runtime_market_label(spec.market).to_owned(),
            symbol: spec.symbol,
            testnet: spec.testnet,
            balance_asset: snapshot.balance_asset,
            total_balance,
            available_balance,
            open_positions_count: snapshot.open_positions_count,
            configured_symbol_position_found: snapshot.configured_symbol_position_found,
            configured_symbol_open_position_amt: snapshot.configured_symbol_open_position_amt,
            position_mode: position_mode_label,
            multi_assets_mode: multi_assets_enabled,
            signal_evaluation_allowed: snapshot.signal_evaluation_allowed,
            status_message: snapshot.status_message,
            error: String::new(),
        }
    }

    fn execute_guarded_cycle(
        &self,
        config: &Value,
        api_key: String,
        api_secret: String,
        now_ms: i64,
    ) -> NativeRuntimeExecutionResponse {
        let spec = match native_runtime_market_poll_spec(config) {
            Ok(spec) => spec,
            Err(error) => return NativeRuntimeExecutionResponse::error(error),
        };
        if spec.market != BinanceMarket::Futures {
            return NativeRuntimeExecutionResponse::error(
                "Native guarded execution currently supports Binance USD-M Futures only.",
            );
        }
        {
            let managed = match self.inner.lock() {
                Ok(value) => value,
                Err(_) => {
                    return NativeRuntimeExecutionResponse::error(
                        "Native runtime state lock is poisoned.",
                    );
                }
            };
            if !managed.running {
                return NativeRuntimeExecutionResponse::error(
                    "Native Rust runtime is not running.",
                );
            }
            if managed.market_poll_spec.as_ref() != Some(&spec) {
                return NativeRuntimeExecutionResponse::error(
                    "Native runtime market configuration changed; stop and restart the runtime before executing.",
                );
            }
        }
        if api_key.trim().is_empty() || api_secret.trim().is_empty() {
            return NativeRuntimeExecutionResponse::error(
                "API key and API secret are required for native guarded execution.",
            );
        }

        let credentials = BinanceApiCredentials::new(api_key.clone(), api_secret.clone());
        let account_client = match BinanceSignedRestClient::new(spec.market, spec.testnet) {
            Ok(client) => client,
            Err(error) => return NativeRuntimeExecutionResponse::error(error.to_string()),
        };
        let market_client = match BinanceRestMarketDataClient::new(spec.market, spec.testnet) {
            Ok(client) => client,
            Err(error) => return NativeRuntimeExecutionResponse::error(error.to_string()),
        };
        let candles = match market_client.fetch_klines(&spec.symbol, &spec.interval, 500) {
            Ok(candles) => candles,
            Err(error) => return NativeRuntimeExecutionResponse::error(error.to_string()),
        };
        let ticker = match market_client.fetch_ticker_price(&spec.symbol) {
            Ok(ticker) if ticker.price.is_finite() && ticker.price > 0.0 => ticker,
            Ok(_) => {
                return NativeRuntimeExecutionResponse::error(
                    "Native guarded execution received an invalid Binance ticker price.",
                );
            }
            Err(error) => return NativeRuntimeExecutionResponse::error(error.to_string()),
        };
        let filters = match account_client.fetch_futures_symbol_filters(&spec.symbol) {
            Ok(filters) => filters,
            Err(error) => return NativeRuntimeExecutionResponse::error(error.to_string()),
        };
        let market_input = match NativeRuntimeReadOnlyMarketCycleInput::from_python_service_config(
            now_ms,
            candles.clone(),
            config,
            false,
        ) {
            Ok(input) => input,
            Err(error) => return NativeRuntimeExecutionResponse::error(error.to_string()),
        };

        let mut managed = match self.inner.lock() {
            Ok(value) => value,
            Err(_) => {
                return NativeRuntimeExecutionResponse::error(
                    "Native runtime state lock is poisoned.",
                );
            }
        };
        if !managed.running {
            return NativeRuntimeExecutionResponse::error("Native Rust runtime is not running.");
        }
        if managed.market_poll_spec.as_ref() != Some(&spec) {
            return NativeRuntimeExecutionResponse::error(
                "Native runtime market configuration changed; stop and restart the runtime before executing.",
            );
        }
        let Some(account_bootstrap) = managed.account_bootstrap.clone() else {
            return NativeRuntimeExecutionResponse::error(
                "A fresh native account bootstrap is required before guarded execution.",
            );
        };
        if !native_runtime_account_bootstrap_is_fresh(&account_bootstrap, now_ms)
            || !account_bootstrap.signal_evaluation_allowed
        {
            return NativeRuntimeExecutionResponse::error(format!(
                "Native account bootstrap is not execution-ready: {}",
                account_bootstrap.status_message
            ));
        }

        let NativeRuntimeManagedState {
            runtime,
            order_engine,
            ..
        } = &mut *managed;
        let (Some(runtime), Some(engine)) = (runtime.as_mut(), order_engine.as_mut()) else {
            return NativeRuntimeExecutionResponse::error(
                "Native runtime execution state is unavailable.",
            );
        };
        let ingestion = runtime.run_rest_kline_ingestion_cycle(now_ms, || Ok(candles.clone()));
        if ingestion.poll_status != "rest_closed_kline" {
            return NativeRuntimeExecutionResponse::error(ingestion.poll_error.unwrap_or_else(
                || "Native guarded execution market ingestion failed.".to_owned(),
            ));
        }

        configure_native_runtime_order_engine(engine, config, now_ms);
        engine.api_key = api_key;
        engine.api_secret = api_secret;
        let account_snapshot = runtime.bootstrap_read_only_account(
            &account_bootstrap.balance,
            &account_bootstrap.positions,
            Some(&account_bootstrap.position_mode),
            Some(&account_bootstrap.multi_assets_mode),
        );
        let execution_input = NativeRuntimeGuardedExecutionCycleInput {
            market_cycle: market_input,
            exposure: native_runtime_exposure_input(
                config,
                &spec,
                &account_bootstrap,
                ticker.price,
                &filters,
            ),
            filters: Some(OrderSymbolFilters::from(&filters)),
            market: "futures".to_owned(),
            connector_state: "active".to_owned(),
            connector_health: "ok".to_owned(),
            operational_preflight: runtime.build_operational_preflight(
                native_runtime_operational_preflight_input(
                    config,
                    now_ms,
                    account_bootstrap.refreshed_at_ms,
                    account_snapshot.account_preflight,
                    engine.circuit.is_open(),
                ),
            ),
            now_iso: native_runtime_now_iso(now_ms),
            now_epoch_seconds: now_ms.max(0) as f64 / 1_000.0,
            source: "tauri-native-runtime".to_owned(),
        };
        let result = runtime.run_guarded_execution_cycle(engine, execution_input, |params| {
            let quantity = params
                .params
                .iter()
                .find(|(key, _)| *key == "quantity")
                .and_then(|(_, value)| value.parse::<f64>().ok())
                .filter(|value| value.is_finite() && *value > 0.0)
                .unwrap_or(0.0);
            let reduce_only = params
                .params
                .iter()
                .any(|(key, value)| *key == "reduceOnly" && value.eq_ignore_ascii_case("true"));
            account_client.place_futures_market_order(
                &credentials,
                &params.symbol,
                &params.side,
                quantity,
                reduce_only,
                &params.position_side,
            )
        });
        engine.api_key.clear();
        engine.api_secret.clear();
        match result {
            Ok(snapshot) => NativeRuntimeExecutionResponse::from_snapshot(snapshot),
            Err(error) => NativeRuntimeExecutionResponse::error(error.to_string()),
        }
    }

    fn clear_account_bootstrap(&self, spec: &NativeRuntimeMarketPollSpec) {
        if let Ok(mut managed) = self.inner.lock()
            && managed.running
            && managed.market_poll_spec.as_ref() == Some(spec)
        {
            managed.account_bootstrap = None;
        }
    }
}

fn dispatch_native_runtime_position_closes(
    managed: &mut NativeRuntimeManagedState,
    config: &Value,
    api_key: String,
    api_secret: String,
    now_ms: i64,
) -> Result<String, String> {
    let spec = native_runtime_market_poll_spec(config)?;
    if spec.market != BinanceMarket::Futures {
        return Err(
            "Native guarded close-all currently supports Binance USD-M Futures only.".to_owned(),
        );
    }
    if managed.market_poll_spec.as_ref() != Some(&spec) {
        return Err(
            "Native runtime market configuration changed; stop and restart the runtime before closing positions."
                .to_owned(),
        );
    }
    if api_key.trim().is_empty() || api_secret.trim().is_empty() {
        return Err(
            "API key and API secret are required for native guarded position close.".to_owned(),
        );
    }

    let credentials = BinanceApiCredentials::new(api_key.clone(), api_secret.clone());
    let account_client = BinanceSignedRestClient::new(spec.market, spec.testnet)
        .map_err(|error| error.to_string())?;
    let exchange_position_mode = account_client
        .fetch_futures_position_mode(&credentials)
        .map_err(|error| error.to_string())?;
    let positions = account_client
        .fetch_open_futures_positions(&credentials)
        .map_err(|error| error.to_string())?;
    let mut step_size_by_symbol = BTreeMap::new();
    for position in &positions {
        let filters = account_client
            .fetch_futures_symbol_filters(&position.symbol)
            .map_err(|error| error.to_string())?;
        step_size_by_symbol.insert(position.symbol.clone(), filters.step_size);
    }

    let Some(runtime) = managed.runtime.as_mut() else {
        return Err("Native Rust runtime state is unavailable.".to_owned());
    };
    let mode = runtime.reconcile_position_mode(Some(&exchange_position_mode));
    if !mode.matches_config {
        return Err(format!(
            "Native close-all refused because configured position mode {} does not match exchange mode {}.",
            mode.configured_position_mode,
            mode.exchange_position_mode
                .unwrap_or_else(|| "unknown".to_owned()),
        ));
    }
    let plan = runtime
        .plan_close_positions(NativeRuntimeClosePlanningInput {
            positions,
            step_size_by_symbol: step_size_by_symbol.into_iter().collect(),
            // Binance MARKET close-all uses quantity-specific reduce-only orders.
            prefer_close_position: false,
        })
        .map_err(|error| error.to_string())?;
    let Some(engine) = managed.order_engine.as_mut() else {
        return Err("Native runtime order engine is unavailable.".to_owned());
    };
    configure_native_runtime_order_engine(engine, config, now_ms);
    engine.api_key = api_key;
    engine.api_secret = api_secret;
    // This is an explicit de-risking action after promotion, not an entry order.
    // It remains restricted to freshly reconciled, reduce-only directives.
    engine.dry_run = false;
    let batch = engine.execute_planned_position_closes(
        &plan.directives,
        native_runtime_now_iso(now_ms),
        "tauri-native-runtime-stop",
        |directive| {
            account_client.place_futures_market_order(
                &credentials,
                &directive.symbol,
                &directive.side,
                directive.quantity,
                directive.reduce_only,
                &directive.position_side,
            )
        },
    );
    engine.api_key.clear();
    engine.api_secret.clear();
    if !batch.ok {
        return Err(format!(
            "{} of {} requested contracts remain after {} close attempt(s).",
            batch.remaining_qty,
            batch.requested_qty,
            batch.attempts.len(),
        ));
    }
    Ok(format!(
        "Native close-all reconciled {} requested contracts across {} close attempt(s).",
        batch.closed_qty,
        batch.attempts.len(),
    ))
}

fn config_root(config: &Value) -> &Value {
    config
        .get("config")
        .filter(|value| value.is_object())
        .unwrap_or(config)
}

fn first_config_string(config: &Value, key: &str, default: &str) -> String {
    let value = config_root(config).get(key);
    let text = value
        .and_then(|value| {
            value
                .as_array()
                .and_then(|items| items.first())
                .unwrap_or(value)
                .as_str()
        })
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(default);
    text.to_owned()
}

fn native_runtime_ownership_error(config: &Value) -> Option<String> {
    let selected_exchange = first_config_string(config, "selected_exchange", "Binance");
    if !selected_exchange.eq_ignore_ascii_case("Binance") {
        return Some(format!(
            "Native Rust runtime coordinates Binance futures only. {selected_exchange} remains Python Service API/provider connector-owned."
        ));
    }

    let connector_backend =
        first_config_string(config, "connector_backend", DEFAULT_CONNECTOR_BACKEND)
            .to_ascii_lowercase();
    if matches!(
        connector_backend.as_str(),
        "binance-sdk-derivatives-trading-usds-futures"
            | "binance-sdk-derivatives-trading-coin-futures"
    ) {
        return None;
    }

    Some(format!(
        "Native Rust runtime coordinates only Python's explicit Binance futures connector keys; '{connector_backend}' remains Python Service API/provider connector-owned."
    ))
}

fn native_runtime_market_poll_spec(config: &Value) -> Result<NativeRuntimeMarketPollSpec, String> {
    if let Some(error) = native_runtime_ownership_error(config) {
        return Err(error);
    }
    let connector_backend =
        first_config_string(config, "connector_backend", DEFAULT_CONNECTOR_BACKEND)
            .to_ascii_lowercase();
    let market = match connector_backend.as_str() {
        "binance-sdk-derivatives-trading-usds-futures" => BinanceMarket::Futures,
        "binance-sdk-derivatives-trading-coin-futures" => BinanceMarket::CoinFutures,
        _ => return Err("Native Rust runtime requires a Binance futures connector.".to_owned()),
    };
    let default_symbol = match market {
        BinanceMarket::CoinFutures => "BTCUSD_PERP",
        BinanceMarket::Futures | BinanceMarket::Spot => "BTCUSDT",
    };
    let mode = first_config_string(config, "mode", "Demo/Testnet");
    Ok(NativeRuntimeMarketPollSpec {
        market,
        symbol: first_config_string(config, "symbols", default_symbol).to_ascii_uppercase(),
        interval: first_config_string(config, "intervals", "1m"),
        testnet: python_mode_uses_testnet(&mode),
    })
}

fn python_mode_uses_testnet(mode: &str) -> bool {
    let normalized = mode.to_ascii_lowercase();
    ["demo", "test", "sandbox"]
        .iter()
        .any(|marker| normalized.contains(marker))
}

fn native_runtime_market_label(market: BinanceMarket) -> &'static str {
    match market {
        BinanceMarket::Futures => "USD-M futures",
        BinanceMarket::CoinFutures => "Coin-M futures",
        BinanceMarket::Spot => "spot",
    }
}

fn native_runtime_account_bootstrap_is_fresh(
    bootstrap: &NativeRuntimeAccountBootstrapState,
    now_ms: i64,
) -> bool {
    now_ms.saturating_sub(bootstrap.refreshed_at_ms).max(0) <= 5 * 60 * 1_000
}

fn config_i64(config: &Value, key: &str, default: i64) -> i64 {
    let Some(value) = config_root(config).get(key) else {
        return default;
    };
    value
        .as_i64()
        .or_else(|| value.as_f64().map(|value| value.round() as i64))
        .or_else(|| value.as_str().and_then(|value| value.trim().parse().ok()))
        .unwrap_or(default)
}

fn config_f64(config: &Value, key: &str, default: f64) -> f64 {
    let Some(value) = config_root(config).get(key) else {
        return default;
    };
    value
        .as_f64()
        .or_else(|| value.as_str().and_then(|value| value.trim().parse().ok()))
        .filter(|value| value.is_finite())
        .unwrap_or(default)
}

fn config_bool(config: &Value, key: &str, default: bool) -> bool {
    let Some(value) = config_root(config).get(key) else {
        return default;
    };
    match value {
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().is_some_and(|value| value != 0.0),
        Value::String(value) => match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => default,
        },
        _ => default,
    }
}

fn native_runtime_now_iso(now_ms: i64) -> String {
    format!("native-runtime-{}", now_ms.max(0))
}

fn native_runtime_order_engine(config: &Value, now_ms: i64) -> RuntimeOrderEngine {
    let mut engine = RuntimeOrderEngine::new(
        first_config_string(config, "mode", "Demo/Testnet"),
        native_runtime_order_audit_config(config),
        native_runtime_circuit_breaker_config(config),
        native_runtime_now_iso(now_ms),
    );
    configure_native_runtime_order_engine(&mut engine, config, now_ms);
    engine
}

fn configure_native_runtime_order_engine(
    engine: &mut RuntimeOrderEngine,
    config: &Value,
    now_ms: i64,
) {
    engine.mode = first_config_string(config, "mode", "Demo/Testnet");
    engine.account_type = first_config_string(config, "account_type", "FUTURES");
    engine.leverage = config_i64(config, "leverage", 5).clamp(1, 125);
    engine.margin_mode = native_runtime_config(config).margin_mode;
    engine.position_pct = config_f64(config, "position_pct", 2.0).clamp(0.01, 100.0);
    engine.configure_audit_and_circuit(
        native_runtime_order_audit_config(config),
        native_runtime_circuit_breaker_config(config),
        native_runtime_incident_log_path(config),
        config_i64(
            config,
            "connector_order_circuit_incident_log_max_bytes",
            2 * 1024 * 1024,
        )
        .clamp(1, 1_000_000_000) as u64,
        config_i64(
            config,
            "connector_order_circuit_incident_log_backup_count",
            1,
        )
        .clamp(0, 100) as usize,
        native_runtime_now_iso(now_ms),
    );
    let mut safety = LiveTradingSafetyConfig::default();
    safety.live_trading_enabled = config_bool(config, "live_trading_enabled", false);
    safety.live_trading_acknowledgement =
        first_config_string(config, "live_trading_acknowledgement", "");
    safety.live_trading_max_leverage = config_i64(
        config,
        "live_trading_max_leverage",
        safety.live_trading_max_leverage,
    )
    .clamp(1, 125);
    safety.live_trading_max_position_pct = config_f64(
        config,
        "live_trading_max_position_pct",
        safety.live_trading_max_position_pct,
    )
    .clamp(0.01, 100.0);
    safety.live_trading_max_session_orders = config_i64(
        config,
        "live_trading_max_session_orders",
        safety.live_trading_max_session_orders,
    )
    .clamp(1, 100_000);
    engine.dry_run = !rust_trading_execution_supported() || !safety.live_trading_enabled;
    engine.safety = safety;
}

fn native_runtime_order_audit_config(config: &Value) -> OrderAuditConfig {
    let mut audit = OrderAuditConfig::default();
    audit.enabled = config_bool(config, "order_audit_enabled", true);
    let configured_path = first_config_string(config, "order_audit_log_path", "");
    if !configured_path.trim().is_empty() {
        audit.path = configured_path;
    }
    audit.max_bytes = config_i64(config, "order_audit_max_bytes", 10 * 1024 * 1024)
        .clamp(1, 1_000_000_000) as u64;
    audit.backup_count = config_i64(config, "order_audit_backup_count", 1).clamp(0, 100) as usize;
    audit
}

fn native_runtime_circuit_breaker_config(config: &Value) -> ConnectorOrderCircuitBreakerConfig {
    ConnectorOrderCircuitBreakerConfig {
        enabled: config_bool(
            config,
            "connector_order_block_circuit_breaker_enabled",
            true,
        ),
        block_threshold: config_i64(config, "connector_order_block_pause_threshold", 2)
            .clamp(1, 100_000) as usize,
        block_window_seconds: config_f64(config, "connector_order_block_window_seconds", 60.0)
            .clamp(1.0, 86_400.0),
    }
}

fn native_runtime_incident_log_path(config: &Value) -> PathBuf {
    let configured_path =
        first_config_string(config, "connector_order_circuit_incident_log_path", "");
    if configured_path.trim().is_empty() {
        PathBuf::from("~/.trading-bot/connector_order_circuit_incidents.jsonl")
    } else {
        PathBuf::from(configured_path)
    }
}

fn native_runtime_operational_preflight_input(
    config: &Value,
    now_ms: i64,
    account_refreshed_at_ms: i64,
    account_preflight: NativeRuntimeAccountPreflightSnapshot,
    connector_order_circuit_active: bool,
) -> NativeRuntimeOperationalPreflightInput {
    let fresh =
        |timestamp_ms: i64, timestamp_field: &str, source: &str| NativeRuntimeFreshnessInput {
            timestamp_ms: Some(timestamp_ms.max(0)),
            timestamp_field: timestamp_field.to_owned(),
            max_age_ms: 5 * 60 * 1_000,
            should_warn: true,
            state: "ok".to_owned(),
            source: source.to_owned(),
        };
    NativeRuntimeOperationalPreflightInput {
        mode: first_config_string(config, "mode", "Demo/Testnet"),
        health: "ok".to_owned(),
        generated_at_ms: now_ms.max(0),
        start_gate_enabled: true,
        order_gate_enabled: true,
        connector_order_circuit_active,
        exchange_connector: fresh(now_ms, "native_market_refreshed_at_ms", "binance-rest"),
        execution: fresh(
            now_ms,
            "native_execution_refreshed_at_ms",
            "tauri-native-runtime",
        ),
        account: fresh(
            account_refreshed_at_ms,
            "native_account_refreshed_at_ms",
            "binance-signed-rest",
        ),
        portfolio: fresh(
            account_refreshed_at_ms,
            "native_portfolio_refreshed_at_ms",
            "native-account-bootstrap",
        ),
        account_preflight: Some(account_preflight),
    }
}

fn native_runtime_exposure_input(
    config: &Value,
    spec: &NativeRuntimeMarketPollSpec,
    account: &NativeRuntimeAccountBootstrapState,
    price: f64,
    filters: &BinanceFuturesSymbolFilters,
) -> NativeRuntimeExposureGuardInput {
    let matching_positions: Vec<&BinanceFuturesPosition> = account
        .positions
        .iter()
        .filter(|position| position.symbol.eq_ignore_ascii_case(&spec.symbol))
        .collect();
    let total_margin = account
        .positions
        .iter()
        .map(|position| position.initial_margin + position.open_order_margin)
        .filter(|value| value.is_finite() && *value > 0.0)
        .sum();
    let existing_side_margin = matching_positions
        .iter()
        .map(|position| position.initial_margin + position.open_order_margin)
        .filter(|value| value.is_finite() && *value > 0.0)
        .sum();
    let net_position_amt = matching_positions
        .iter()
        .map(|position| position.position_amt)
        .filter(|value| value.is_finite())
        .sum();
    NativeRuntimeExposureGuardInput {
        symbol: spec.symbol.clone(),
        interval: spec.interval.clone(),
        side: "BOTH".to_owned(),
        position_pct_fraction: (config_f64(config, "position_pct", 2.0) / 100.0).clamp(0.0001, 1.0),
        available_usdt: account.balance.available_usdt_balance.max(0.0),
        wallet_usdt: account.balance.total_usdt_balance.max(0.0),
        ledger_margin_total: total_margin,
        existing_indicator_margin: 0.0,
        existing_side_margin,
        active_slot_count: account
            .positions
            .iter()
            .filter(|position| {
                position.position_amt.is_finite() && position.position_amt.abs() > 1e-10
            })
            .count(),
        slot_already_active: matching_positions.iter().any(|position| {
            position.position_amt.is_finite() && position.position_amt.abs() > 1e-10
        }),
        price,
        leverage: config_i64(config, "leverage", 5).clamp(1, 125),
        filter_min_qty: filters.min_qty,
        filter_min_notional: filters.min_notional,
        filter_step_size: filters.step_size,
        flip_close_qty: None,
        live_mode: first_config_string(config, "mode", "").eq_ignore_ascii_case("live"),
        live_allow_auto_bump_to_min_order: config_bool(
            config,
            "live_allow_auto_bump_to_min_order",
            false,
        ),
        max_auto_bump_percent: config_f64(config, "max_auto_bump_percent", 5.0).clamp(0.0, 100.0),
        auto_bump_percent_multiplier: config_f64(config, "auto_bump_percent_multiplier", 10.0)
            .clamp(0.0, 1_000.0),
        margin_over_target_tolerance: 0.0,
        margin_filter_slippage: 0.0,
        add_only: config_bool(config, "add_only", false),
        dual_side: account.position_mode.dual_side_position,
        net_position_amt,
    }
}

fn native_runtime_config(config: &Value) -> NativeRuntimeLoopConfig {
    let position_mode = first_config_string(config, "position_mode", "Hedge");
    let margin_mode = first_config_string(config, "margin_mode", "Isolated");
    let assets_mode = first_config_string(config, "assets_mode", "Single-Asset Mode");
    let loop_interval_override = first_config_string(config, "loop_interval_override", "");
    let loop_interval_override = if matches!(
        loop_interval_override.trim().to_ascii_lowercase().as_str(),
        "" | "none" | "default" | "automatic"
    ) {
        None
    } else {
        Some(loop_interval_override)
    };

    NativeRuntimeLoopConfig {
        symbol: first_config_string(config, "symbols", "BTCUSDT").to_ascii_uppercase(),
        interval: first_config_string(config, "intervals", "1m"),
        position_mode: if position_mode.to_ascii_lowercase().contains("one") {
            "One-way".to_owned()
        } else {
            "Hedge".to_owned()
        },
        margin_mode: if margin_mode.to_ascii_lowercase().contains("cross") {
            "CROSSED".to_owned()
        } else {
            "ISOLATED".to_owned()
        },
        leverage: config_i64(config, "leverage", 5).clamp(1, 125),
        multi_assets_mode: assets_mode.to_ascii_lowercase().contains("multi"),
        loop_interval_override,
        ..NativeRuntimeLoopConfig::default()
    }
}

fn format_active_duration(started_at_ms: Option<i64>, now_ms: i64, running: bool) -> String {
    if !running {
        return "--".to_owned();
    }
    let elapsed_seconds = started_at_ms
        .map(|started_at_ms| now_ms.saturating_sub(started_at_ms).max(0) / 1_000)
        .unwrap_or(0);
    let hours = elapsed_seconds / 3_600;
    let minutes = (elapsed_seconds % 3_600) / 60;
    let seconds = elapsed_seconds % 60;
    format!("{hours:02}:{minutes:02}:{seconds:02}")
}

fn native_runtime_snapshot(
    managed: &mut NativeRuntimeManagedState,
    now_ms: i64,
    message: impl Into<String>,
) -> NativeRuntimeControlResponse {
    let trading_execution_supported = rust_trading_execution_supported();
    let account_bootstrap = managed.account_bootstrap.as_ref();
    let active_duration = format_active_duration(managed.started_at_ms, now_ms, managed.running);
    let Some(runtime) = managed.runtime.as_mut() else {
        return NativeRuntimeControlResponse {
            ok: true,
            execution_backend: "native-rust".to_owned(),
            status: json!({
                "runtime_active": false,
                "active_duration": active_duration,
                "active_time": active_duration,
                "lifecycle_phase": "idle",
                "paused": false,
                "account_bootstrap_fresh": false,
                "execution_owner": "native-rust-coordinator"
            }),
            lifecycle: json!({
                "lifecycle_phase": "idle",
                "is_alive": false,
                "execution_owner": "native-rust-coordinator",
                "native_trading_execution_enabled": trading_execution_supported
            }),
            stream: json!({}),
            trading_execution_supported,
            promotion_required: !trading_execution_supported,
            message: message.into(),
            error: String::new(),
        };
    };

    let cycle = runtime.run_cycle(NativeRuntimeCycleInput {
        now_ms,
        stream_event: None,
        stream_disconnected: false,
    });
    let mut lifecycle = cycle.lifecycle;
    if let Some(object) = lifecycle.as_object_mut() {
        object.insert(
            "execution_owner".to_owned(),
            Value::String("native-rust-coordinator".to_owned()),
        );
        object.insert(
            "native_trading_execution_enabled".to_owned(),
            Value::Bool(trading_execution_supported),
        );
    }
    let lifecycle_phase = lifecycle
        .get("lifecycle_phase")
        .and_then(Value::as_str)
        .unwrap_or(if managed.running { "running" } else { "idle" });
    let stream = &cycle.stream;
    let stream_payload = json!({
        "connected": stream.connected,
        "reconnect_attempts": stream.reconnect_attempts,
        "last_event_time_ms": stream.last_event_time_ms,
        "last_disconnect_time_ms": stream.last_disconnect_time_ms,
        "kline_cache_health": {
            "stale": stream.kline_cache_health.stale,
            "reason": stream.kline_cache_health.reason,
            "candle_count": stream.kline_cache_health.candle_count,
            "latest_event_time_ms": stream.kline_cache_health.latest_event_time_ms,
            "latest_closed_open_time_ms": stream.kline_cache_health.latest_closed_open_time_ms
        },
        "reconnect_decision": {
            "should_reconnect": stream.reconnect_decision.should_reconnect,
            "next_attempt": stream.reconnect_decision.next_attempt,
            "delay_ms": stream.reconnect_decision.delay_ms,
            "reason": stream.reconnect_decision.reason
        }
    });
    NativeRuntimeControlResponse {
        ok: true,
        execution_backend: "native-rust".to_owned(),
        status: json!({
            "runtime_active": managed.running,
            "active_duration": active_duration,
            "active_time": active_duration,
            "lifecycle_phase": lifecycle_phase,
            "paused": managed.paused,
            "account_bootstrap_fresh": account_bootstrap
                .map(|snapshot| native_runtime_account_bootstrap_is_fresh(snapshot, now_ms))
                .unwrap_or(false),
            "account_signal_evaluation_allowed": account_bootstrap
                .map(|snapshot| snapshot.signal_evaluation_allowed)
                .unwrap_or(false),
            "signal_evaluation_allowed": cycle.signal_evaluation_allowed,
            "execution_owner": "native-rust-coordinator",
            "status_message": cycle.status_message
        }),
        lifecycle,
        stream: stream_payload,
        trading_execution_supported,
        promotion_required: !trading_execution_supported,
        message: message.into(),
        error: String::new(),
    }
}

impl Drop for ServiceProcessState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[derive(Debug, Serialize)]
struct ServiceProcessResponse {
    ok: bool,
    running: bool,
    healthy: bool,
    managed: bool,
    pid: Option<u32>,
    base_url: String,
    message: String,
    error: String,
}

impl ServiceProcessResponse {
    fn ok(
        running: bool,
        healthy: bool,
        managed: bool,
        pid: Option<u32>,
        base_url: String,
        message: impl Into<String>,
    ) -> Self {
        Self {
            ok: true,
            running,
            healthy,
            managed,
            pid,
            base_url,
            message: message.into(),
            error: String::new(),
        }
    }

    fn err(
        running: bool,
        managed: bool,
        pid: Option<u32>,
        base_url: String,
        error: impl Into<String>,
    ) -> Self {
        Self {
            ok: false,
            running,
            healthy: false,
            managed,
            pid,
            base_url,
            message: String::new(),
            error: error.into(),
        }
    }
}

#[derive(Debug, Serialize)]
struct DesktopLanguageLaunchResponse {
    ok: bool,
    language: String,
    path: String,
    pid: Option<u32>,
    message: String,
    error: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct NativeRuntimeCandleInput {
    open_time_ms: i64,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
}

#[derive(Debug, Serialize)]
struct NativeRuntimePreviewResponse {
    ok: bool,
    computed_indicator_keys: Vec<String>,
    unsupported_indicator_keys: Vec<String>,
    strategy_evaluated: bool,
    signal: Option<String>,
    trading_execution_supported: bool,
    status_message: String,
    error: String,
}

impl NativeRuntimePreviewResponse {
    fn error(error: impl Into<String>) -> Self {
        Self {
            ok: false,
            computed_indicator_keys: Vec::new(),
            unsupported_indicator_keys: Vec::new(),
            strategy_evaluated: false,
            signal: None,
            trading_execution_supported: false,
            status_message: String::new(),
            error: error.into(),
        }
    }
}

impl DesktopLanguageLaunchResponse {
    fn ok(language: &str, path: &Path, pid: u32, message: impl Into<String>) -> Self {
        Self {
            ok: true,
            language: language.to_string(),
            path: path.to_string_lossy().to_string(),
            pid: Some(pid),
            message: message.into(),
            error: String::new(),
        }
    }

    fn err(language: &str, error: impl Into<String>) -> Self {
        Self {
            ok: false,
            language: language.to_string(),
            path: String::new(),
            pid: None,
            message: String::new(),
            error: error.into(),
        }
    }
}

fn response_ok(
    route_name: &str,
    path: &str,
    status: u16,
    payload: Value,
) -> ServiceApiProxyResponse {
    ServiceApiProxyResponse {
        ok: (200..300).contains(&status),
        status,
        route_name: route_name.to_string(),
        path: path.to_string(),
        payload,
        error: String::new(),
    }
}

fn response_error(
    route_name: &str,
    path: &str,
    status: u16,
    error: impl Into<String>,
) -> ServiceApiProxyResponse {
    ServiceApiProxyResponse {
        ok: false,
        status,
        route_name: route_name.to_string(),
        path: path.to_string(),
        payload: json!({}),
        error: error.into(),
    }
}

fn is_loopback_host(host: &str) -> bool {
    matches!(host, "localhost" | "127.0.0.1" | "::1" | "[::1]")
}

fn normalize_bind_host(host: &str) -> String {
    let trimmed = host.trim();
    if trimmed.is_empty() {
        return "127.0.0.1".to_string();
    }
    if let Ok(url) = reqwest::Url::parse(trimmed) {
        return url.host_str().unwrap_or("127.0.0.1").to_string();
    }
    trimmed.trim_matches('/').to_string()
}

fn service_base_url(host: &str, port: u16) -> String {
    let host = normalize_bind_host(host);
    let display_host = if host == "::1" {
        "[::1]".to_string()
    } else {
        host
    };
    format!("http://{display_host}:{port}")
}

fn normalize_service_base_url(
    base_url: &str,
    allow_public_network_endpoint: bool,
) -> Result<reqwest::Url, String> {
    let normalized = if base_url.trim().is_empty() {
        "http://127.0.0.1:8000"
    } else {
        base_url.trim()
    };
    let parsed = reqwest::Url::parse(normalized)
        .map_err(|exc| format!("Invalid service API base URL: {exc}"))?;
    match parsed.scheme() {
        "http" | "https" => {}
        scheme => return Err(format!("Unsupported service API URL scheme: {scheme}")),
    }
    let host = parsed.host_str().unwrap_or_default();
    if !allow_public_network_endpoint && !is_loopback_host(host) {
        return Err(
            "Public service API endpoints are disabled. Use localhost/127.0.0.1 or enable the public endpoint control."
                .to_string(),
        );
    }
    Ok(parsed)
}

fn validate_service_api_endpoint_access(
    base_url: &str,
    api_token: &str,
    allow_public_network_endpoint: bool,
) -> Result<(), String> {
    let parsed = normalize_service_base_url(base_url, allow_public_network_endpoint)?;
    if !is_loopback_host(parsed.host_str().unwrap_or_default()) && api_token.trim().is_empty() {
        return Err(
            "BOT_SERVICE_API_TOKEN is required for a non-loopback service API endpoint."
                .to_string(),
        );
    }
    Ok(())
}

fn build_service_url(
    base_url: &str,
    route_name: &str,
    query: Option<&BTreeMap<String, String>>,
    allow_public_network_endpoint: bool,
) -> Result<(String, String), String> {
    let route_path = service_api_route_path(route_name)
        .ok_or_else(|| format!("Unknown service API route: {route_name}"))?;
    let parsed_base = normalize_service_base_url(base_url, allow_public_network_endpoint)?;
    let mut url = parsed_base;
    url.set_path(route_path);
    if let Some(params) = query {
        {
            let mut pairs = url.query_pairs_mut();
            for (key, value) in params {
                pairs.append_pair(&key, &value);
            }
        }
    }
    Ok((url.to_string(), route_path.to_string()))
}

fn validate_service_api_method(route_name: &str, method: &str) -> Result<String, String> {
    let normalized = method.trim().to_uppercase();
    if normalized.is_empty() {
        return Err(format!(
            "Missing service API method for route: {route_name}"
        ));
    }
    if !service_api_route_supports_method(route_name, &normalized) {
        return Err(format!(
            "Service API method {normalized} is not declared by the Python contract for route: {route_name}"
        ));
    }
    Ok(normalized)
}

fn validate_service_api_fields(
    route_name: &str,
    method: &str,
    payload: Option<&Value>,
    query: Option<&BTreeMap<String, String>>,
) -> Result<(), String> {
    let is_get = method == "GET";
    if let Some(query) = query {
        for field in query.keys() {
            if !is_get || !service_api_route_supports_query_field(route_name, field) {
                return Err(format!(
                    "Service API query field {field} is not declared by the Python contract for route: {route_name}"
                ));
            }
        }
    }
    let Some(payload) = payload else {
        return Ok(());
    };
    if payload.is_null() {
        return Ok(());
    }
    let object = payload
        .as_object()
        .ok_or_else(|| format!("Service API payload must be an object for route: {route_name}"))?;
    for field in object.keys() {
        let supported = if is_get {
            service_api_route_supports_query_field(route_name, field)
        } else {
            service_api_route_supports_request_field(route_name, field)
        };
        if !supported {
            let field_kind = if is_get { "query" } else { "request" };
            return Err(format!(
                "Service API {field_kind} field {field} is not declared by the Python contract for route: {route_name}"
            ));
        }
    }
    Ok(())
}

fn service_health_url(base_url: &str) -> Result<String, String> {
    let mut url = normalize_service_base_url(base_url, false)?;
    url.set_path("/health");
    url.set_query(None);
    Ok(url.to_string())
}

fn check_service_health(base_url: &str, api_token: &str) -> Result<(), String> {
    let url = service_health_url(base_url)?;
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|exc| format!("Could not create health-check client: {exc}"))?;
    let mut request = client.get(url).header("Accept", "application/json");
    if !api_token.trim().is_empty() {
        request = request.bearer_auth(api_token.trim());
    }
    let response = request
        .send()
        .map_err(|exc| format!("Service health check failed: {exc}"))?;
    if response.status().is_success() {
        Ok(())
    } else {
        Err(format!(
            "Service health check returned HTTP {}",
            response.status().as_u16()
        ))
    }
}

fn managed_child_snapshot(state: &ServiceProcessState) -> (bool, Option<u32>) {
    let Ok(mut guard) = state.child.lock() else {
        return (false, None);
    };
    let Some(child) = guard.as_mut() else {
        return (false, None);
    };
    match child.try_wait() {
        Ok(None) => (true, Some(child.id())),
        Ok(Some(_)) | Err(_) => {
            *guard = None;
            (false, None)
        }
    }
}

fn push_candidate_ancestors(candidates: &mut Vec<PathBuf>, start: impl AsRef<Path>) {
    let start = start.as_ref();
    for ancestor in start.ancestors() {
        let root = ancestor.to_path_buf();
        if !candidates.iter().any(|item| item == &root) {
            candidates.push(root);
        }
    }
}

fn find_repo_root(app: &AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(current_dir) = env::current_dir() {
        push_candidate_ancestors(&mut candidates, current_dir);
    }
    if let Ok(current_exe) = env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            push_candidate_ancestors(&mut candidates, parent);
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        push_candidate_ancestors(&mut candidates, resource_dir);
    }
    candidates.into_iter().find(|root| {
        root.join("apps")
            .join("service-api")
            .join("main.py")
            .is_file()
    })
}

fn python_executable() -> String {
    env::var("TRADING_BOT_PYTHON")
        .or_else(|_| env::var("PYTHON"))
        .unwrap_or_else(|_| "python".to_string())
}

fn executable_names(base_name: &str) -> Vec<String> {
    let mut names = Vec::new();
    #[cfg(target_os = "windows")]
    names.push(format!("{base_name}.exe"));
    names.push(base_name.to_string());
    names
}

fn find_python_desktop_entrypoint(repo_root: &Path) -> Option<PathBuf> {
    [
        repo_root.join("apps").join("desktop-pyqt").join("main.py"),
        repo_root.join("Languages").join("Python").join("main.py"),
    ]
    .into_iter()
    .find(|candidate| candidate.is_file())
}

fn find_cpp_desktop_executable(repo_root: &Path) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(raw_path) = env::var("TRADING_BOT_CPP") {
        let candidate = PathBuf::from(raw_path.trim());
        if !candidate.as_os_str().is_empty() {
            candidates.push(candidate);
        }
    }

    let roots = [
        repo_root.to_path_buf(),
        repo_root.join("release"),
        repo_root.join("build").join("binance_cpp"),
        repo_root.join("build").join("binance_cpp").join("Release"),
        repo_root.join("build").join("binance_cpp").join("Debug"),
        repo_root
            .join("build")
            .join("binance_cpp")
            .join("RelWithDebInfo"),
        repo_root
            .join("build")
            .join("binance_cpp")
            .join("MinSizeRel"),
    ];
    for root in roots {
        for name in executable_names("Trading-Bot-C++")
            .into_iter()
            .chain(executable_names("binance_backtest_tab"))
        {
            candidates.push(root.join(name));
        }
    }

    candidates.into_iter().find(|candidate| candidate.is_file())
}

fn apply_no_console_flag(command: &mut Command) {
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);
}

fn prepend_process_path(command: &mut Command, directory: &Path) {
    let separator = if cfg!(windows) { ";" } else { ":" };
    let existing = env::var("PATH").unwrap_or_default();
    let path = if existing.trim().is_empty() {
        directory.to_string_lossy().to_string()
    } else {
        format!("{}{}{}", directory.to_string_lossy(), separator, existing)
    };
    command.env("PATH", path);
}

fn spawn_desktop_process(
    language: &str,
    path: &Path,
    command: &mut Command,
) -> DesktopLanguageLaunchResponse {
    let mut child = match command.spawn() {
        Ok(value) => value,
        Err(exc) => {
            return DesktopLanguageLaunchResponse::err(
                language,
                format!("Could not launch {language} desktop: {exc}"),
            );
        }
    };
    let pid = child.id();
    thread::sleep(Duration::from_millis(600));
    match child.try_wait() {
        Ok(None) => DesktopLanguageLaunchResponse::ok(
            language,
            path,
            pid,
            format!("{language} desktop launch started."),
        ),
        Ok(Some(status)) => {
            let code = status
                .code()
                .map(|value| value.to_string())
                .unwrap_or_else(|| "unknown".to_string());
            DesktopLanguageLaunchResponse::err(
                language,
                format!("{language} desktop exited immediately with code {code}."),
            )
        }
        Err(exc) => DesktopLanguageLaunchResponse::err(
            language,
            format!("{language} desktop launch state check failed: {exc}"),
        ),
    }
}

fn service_pythonpath(repo_root: &Path) -> String {
    let separator = if cfg!(windows) { ";" } else { ":" };
    let mut paths = vec![
        repo_root.to_string_lossy().to_string(),
        repo_root
            .join("Languages")
            .join("Python")
            .to_string_lossy()
            .to_string(),
    ];
    if let Ok(existing) = env::var("PYTHONPATH") {
        if !existing.trim().is_empty() {
            paths.push(existing);
        }
    }
    paths.join(separator)
}

fn launch_python_desktop(repo_root: &Path) -> DesktopLanguageLaunchResponse {
    let Some(script_path) = find_python_desktop_entrypoint(repo_root) else {
        return DesktopLanguageLaunchResponse::err(
            "Python",
            "Could not locate apps/desktop-pyqt/main.py or Languages/Python/main.py.",
        );
    };
    let mut command = Command::new(python_executable());
    command
        .arg(&script_path)
        .current_dir(repo_root)
        .env("PYTHONPATH", service_pythonpath(repo_root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    apply_no_console_flag(&mut command);

    spawn_desktop_process("Python", &script_path, &mut command)
}

fn launch_cpp_desktop(repo_root: &Path) -> DesktopLanguageLaunchResponse {
    let Some(executable_path) = find_cpp_desktop_executable(repo_root) else {
        return DesktopLanguageLaunchResponse::err(
            "C++",
            "Could not find a built Trading-Bot-C++ executable. Build C++ first or set TRADING_BOT_CPP to the executable path.",
        );
    };
    let mut command = Command::new(&executable_path);
    if let Some(parent) = executable_path.parent() {
        command.current_dir(parent);
        prepend_process_path(&mut command, parent);
    } else {
        command.current_dir(repo_root);
    }
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    apply_no_console_flag(&mut command);

    spawn_desktop_process("C++", &executable_path, &mut command)
}

fn wait_for_service_health(
    state: &ServiceProcessState,
    base_url: &str,
    api_token: &str,
) -> Result<(), String> {
    let mut last_error = String::new();
    for _ in 0..32 {
        match check_service_health(base_url, api_token) {
            Ok(()) => return Ok(()),
            Err(exc) => last_error = exc,
        }
        let (running, _) = managed_child_snapshot(state);
        if !running {
            return Err("Service process exited before /health became available.".to_string());
        }
        thread::sleep(Duration::from_millis(250));
    }
    Err(last_error)
}

fn native_config_saved_at() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs().to_string())
        .unwrap_or_default()
}

#[tauri::command]
fn save_native_runtime_config(config: Value) -> NativeConfigPersistenceResponse {
    match write_service_config_file(&config, None, false, false, native_config_saved_at()) {
        Ok(persistence) => NativeConfigPersistenceResponse {
            ok: true,
            config: Value::Null,
            persistence,
            error: String::new(),
        },
        Err(error) => NativeConfigPersistenceResponse::error(error),
    }
}

#[tauri::command]
fn load_native_runtime_config() -> NativeConfigPersistenceResponse {
    match load_service_config_file(None) {
        Ok(result) => NativeConfigPersistenceResponse {
            ok: true,
            config: result.config,
            persistence: service_config_file_status(None),
            error: String::new(),
        },
        Err(error) => NativeConfigPersistenceResponse::error(error),
    }
}

#[tauri::command]
async fn service_api_request(
    base_url: String,
    api_token: String,
    route_name: String,
    method: String,
    payload: Option<Value>,
    query: Option<BTreeMap<String, String>>,
    allow_public_network_endpoint: bool,
) -> ServiceApiProxyResponse {
    if let Err(exc) =
        validate_service_api_endpoint_access(&base_url, &api_token, allow_public_network_endpoint)
    {
        return response_error(&route_name, "", 0, exc);
    }
    let (url, route_path) = match build_service_url(
        &base_url,
        &route_name,
        query.as_ref(),
        allow_public_network_endpoint,
    ) {
        Ok(value) => value,
        Err(exc) => return response_error(&route_name, "", 0, exc),
    };
    let method = match validate_service_api_method(&route_name, &method) {
        Ok(value) => value,
        Err(exc) => return response_error(&route_name, &route_path, 0, exc),
    };
    if let Err(exc) =
        validate_service_api_fields(&route_name, &method, payload.as_ref(), query.as_ref())
    {
        return response_error(&route_name, &route_path, 0, exc);
    }
    let timeout_secs = match route_name.as_str() {
        "llm_local_model_pull" => 3_600,
        "llm_local_model_delete" | "llm_local_model_start" => 120,
        _ => 8,
    };
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(timeout_secs))
        .build()
    {
        Ok(value) => value,
        Err(exc) => {
            return response_error(
                &route_name,
                &route_path,
                0,
                format!("Could not create HTTP client: {exc}"),
            );
        }
    };
    let mut request = match method.as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PATCH" => client.patch(&url),
        "PUT" => client.put(&url),
        _ => {
            return response_error(
                &route_name,
                &route_path,
                0,
                format!("Unsupported service API method: {method}"),
            );
        }
    }
    .header("Accept", "application/json");
    if !api_token.trim().is_empty() {
        request = request.bearer_auth(api_token.trim());
    }
    if matches!(method.as_str(), "POST" | "PATCH" | "PUT") {
        request = request.json(&payload.unwrap_or_else(|| json!({})));
    }
    let response = match request.send().await {
        Ok(value) => value,
        Err(exc) => {
            return response_error(
                &route_name,
                &route_path,
                0,
                format!("Service API request failed: {exc}"),
            );
        }
    };
    let status = response.status().as_u16();
    let text = match response.text().await {
        Ok(value) => value,
        Err(exc) => {
            return response_error(
                &route_name,
                &route_path,
                status,
                format!("Could not read service response: {exc}"),
            );
        }
    };
    let payload = if text.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({ "raw": text }))
    };
    let mut result = response_ok(&route_name, &route_path, status, payload);
    if !result.ok {
        let detail = result
            .payload
            .get("detail")
            .and_then(Value::as_str)
            .unwrap_or("Service API returned an error status.");
        result.error = detail.to_string();
    }
    result
}

#[tauri::command]
fn evaluate_native_runtime_preview(
    config: Value,
    candles: Vec<NativeRuntimeCandleInput>,
    symbol: String,
    interval: String,
    now_ms: i64,
    last_candle_is_closed: bool,
) -> NativeRuntimePreviewResponse {
    let candles = candles
        .into_iter()
        .map(|candle| BinanceKlineCandle {
            open_time_ms: candle.open_time_ms,
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
            volume: candle.volume,
        })
        .collect::<Vec<_>>();
    let input = match NativeRuntimeReadOnlyMarketCycleInput::from_python_service_config(
        now_ms,
        candles,
        &config,
        last_candle_is_closed,
    ) {
        Ok(input) => input,
        Err(error) => return NativeRuntimePreviewResponse::error(error.to_string()),
    };
    let mut runtime = NativeRuntimeLoop::new(NativeRuntimeLoopConfig {
        symbol: symbol.trim().to_ascii_uppercase(),
        interval: interval.trim().to_owned(),
        ..NativeRuntimeLoopConfig::default()
    });
    runtime.start();
    match runtime.run_read_only_market_cycle(input) {
        Ok(snapshot) => NativeRuntimePreviewResponse {
            ok: true,
            computed_indicator_keys: snapshot.computed_indicator_keys,
            unsupported_indicator_keys: snapshot.unsupported_indicator_keys,
            strategy_evaluated: snapshot.strategy_evaluated,
            signal: snapshot
                .strategy_decision
                .and_then(|decision| decision.signal),
            trading_execution_supported: snapshot.trading_execution_supported,
            status_message: snapshot.status_message,
            error: String::new(),
        },
        Err(error) => NativeRuntimePreviewResponse::error(error.to_string()),
    }
}

#[tauri::command]
fn start_native_runtime(
    state: State<'_, NativeRuntimeState>,
    config: Value,
    now_ms: i64,
) -> NativeRuntimeControlResponse {
    state.start(&config, now_ms)
}

#[tauri::command]
fn poll_native_runtime_market(
    state: State<'_, NativeRuntimeState>,
    config: Value,
    now_ms: i64,
) -> NativeRuntimeMarketPollResponse {
    state.poll_market(&config, now_ms)
}

#[tauri::command]
fn poll_native_runtime_account(
    state: State<'_, NativeRuntimeState>,
    config: Value,
    api_key: String,
    api_secret: String,
    now_ms: i64,
) -> NativeRuntimeAccountPollResponse {
    state.poll_account(&config, api_key, api_secret, now_ms)
}

#[tauri::command]
fn execute_native_runtime_cycle(
    state: State<'_, NativeRuntimeState>,
    config: Value,
    api_key: String,
    api_secret: String,
    now_ms: i64,
) -> NativeRuntimeExecutionResponse {
    state.execute_guarded_cycle(&config, api_key, api_secret, now_ms)
}

#[tauri::command]
fn native_runtime_status(
    state: State<'_, NativeRuntimeState>,
    now_ms: i64,
) -> NativeRuntimeControlResponse {
    state.status(now_ms)
}

#[tauri::command]
fn set_native_runtime_paused(
    state: State<'_, NativeRuntimeState>,
    paused: bool,
    now_ms: i64,
) -> NativeRuntimeControlResponse {
    state.set_paused(paused, now_ms)
}

#[tauri::command]
fn stop_native_runtime(
    state: State<'_, NativeRuntimeState>,
    close_positions: bool,
    config: Value,
    api_key: String,
    api_secret: String,
    now_ms: i64,
) -> NativeRuntimeControlResponse {
    state.stop_with_close_request(close_positions, config, api_key, api_secret, now_ms)
}

#[tauri::command]
fn launch_desktop_language(app: AppHandle, language: String) -> DesktopLanguageLaunchResponse {
    let language = language.trim();
    let Some(repo_root) = find_repo_root(&app) else {
        return DesktopLanguageLaunchResponse::err(
            language,
            "Could not locate the trading-bot repository from the Tauri shell.",
        );
    };

    match language.to_lowercase().as_str() {
        "python" | "python (pyqt)" => launch_python_desktop(&repo_root),
        "c++" | "cpp" | "c++ (qt/c++23)" => launch_cpp_desktop(&repo_root),
        "rust" => DesktopLanguageLaunchResponse::ok(
            "Rust",
            &repo_root,
            0,
            "Rust Tauri shell is already open.",
        ),
        _ => DesktopLanguageLaunchResponse::err(
            language,
            format!("Unsupported desktop language: {language}"),
        ),
    }
}

#[tauri::command]
fn service_process_status(
    state: State<'_, ServiceProcessState>,
    host: String,
    port: u16,
    api_token: String,
) -> ServiceProcessResponse {
    let base_url = service_base_url(&host, port);
    let (running, pid) = managed_child_snapshot(&state);
    let healthy = check_service_health(&base_url, &api_token).is_ok();
    ServiceProcessResponse::ok(
        running || healthy,
        healthy,
        running,
        pid,
        base_url,
        if healthy {
            "Service API is reachable."
        } else if running {
            "Managed service process is running, but health is not ready."
        } else {
            "Service API is not running."
        },
    )
}

#[tauri::command]
fn start_service_api(
    app: AppHandle,
    state: State<'_, ServiceProcessState>,
    host: String,
    port: u16,
    api_token: String,
    load_config: bool,
) -> ServiceProcessResponse {
    let bind_host = normalize_bind_host(&host);
    let base_url = service_base_url(&bind_host, port);
    if !is_loopback_host(&bind_host) {
        return ServiceProcessResponse::err(
            false,
            false,
            None,
            base_url,
            "Tauri only auto-starts the local service on loopback hosts.",
        );
    }
    if check_service_health(&base_url, &api_token).is_ok() {
        let (running, pid) = managed_child_snapshot(&state);
        return ServiceProcessResponse::ok(
            true,
            true,
            running,
            pid,
            base_url,
            "Service API is already reachable.",
        );
    }
    let (already_running, pid) = managed_child_snapshot(&state);
    if already_running {
        match wait_for_service_health(&state, &base_url, &api_token) {
            Ok(()) => {
                return ServiceProcessResponse::ok(
                    true,
                    true,
                    true,
                    pid,
                    base_url,
                    "Managed service API is running.",
                );
            }
            Err(exc) => {
                return ServiceProcessResponse::err(true, true, pid, base_url, exc);
            }
        }
    }
    let Some(repo_root) = find_repo_root(&app) else {
        return ServiceProcessResponse::err(
            false,
            false,
            None,
            base_url,
            "Could not locate apps/service-api/main.py from the Tauri shell.",
        );
    };
    let service_script = repo_root.join("apps").join("service-api").join("main.py");
    let mut command = Command::new(python_executable());
    command
        .arg(service_script)
        .arg("--serve")
        .arg("--host")
        .arg(&bind_host)
        .arg("--port")
        .arg(port.to_string())
        .current_dir(&repo_root)
        .env("PYTHONPATH", service_pythonpath(&repo_root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    if !api_token.trim().is_empty() {
        command.arg("--api-token").arg(api_token.trim());
    }
    if load_config {
        command.arg("--load-config");
    }
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    let child = match command.spawn() {
        Ok(value) => value,
        Err(exc) => {
            return ServiceProcessResponse::err(
                false,
                false,
                None,
                base_url,
                format!("Could not launch Python service API: {exc}"),
            );
        }
    };
    let pid = Some(child.id());
    {
        let Ok(mut guard) = state.child.lock() else {
            return ServiceProcessResponse::err(
                true,
                true,
                pid,
                base_url,
                "Service process started, but Tauri state lock failed.",
            );
        };
        *guard = Some(child);
    }
    match wait_for_service_health(&state, &base_url, &api_token) {
        Ok(()) => ServiceProcessResponse::ok(
            true,
            true,
            true,
            pid,
            base_url,
            "Managed service API started.",
        ),
        Err(exc) => ServiceProcessResponse::err(true, true, pid, base_url, exc),
    }
}

#[tauri::command]
fn stop_service_api(
    state: State<'_, ServiceProcessState>,
    host: String,
    port: u16,
) -> ServiceProcessResponse {
    let base_url = service_base_url(&host, port);
    let Ok(mut guard) = state.child.lock() else {
        return ServiceProcessResponse::err(
            false,
            false,
            None,
            base_url,
            "Service process state lock failed.",
        );
    };
    let Some(mut child) = guard.take() else {
        return ServiceProcessResponse::ok(
            false,
            false,
            false,
            None,
            base_url,
            "No Tauri-managed service API process is running.",
        );
    };
    let pid = child.id();
    let kill_result = child.kill();
    let _ = child.wait();
    match kill_result {
        Ok(()) => ServiceProcessResponse::ok(
            false,
            false,
            true,
            Some(pid),
            base_url,
            "Managed service API stopped.",
        ),
        Err(exc) => ServiceProcessResponse::err(
            false,
            true,
            Some(pid),
            base_url,
            format!("Could not stop managed service API: {exc}"),
        ),
    }
}

fn run_packaged_smoke() -> Result<String, String> {
    if supported_frameworks() != ["Tauri"] {
        return Err("the packaged Rust desktop shell catalog must contain only Tauri".to_owned());
    }
    let contract_hash = python_source_contract_hash();
    if contract_hash.len() != 64 || !contract_hash.chars().all(|value| value.is_ascii_hexdigit()) {
        return Err("the generated Python source contract hash is invalid".to_owned());
    }
    if !native_python_app_contract_parity_ready() {
        return Err("the generated native source contract is incomplete".to_owned());
    }
    if rust_trading_execution_supported() {
        return Err(
            "native Rust trading must remain disabled until promotion evidence passes".to_owned(),
        );
    }

    Ok(format!(
        "Trading Bot Tauri packaged smoke passed (contract {contract_hash}, native trading disabled)."
    ))
}

fn main() {
    if env::args().any(|arg| arg == "--smoke") {
        match run_packaged_smoke() {
            Ok(message) => println!("{message}"),
            Err(error) => {
                eprintln!("Tauri packaged smoke failed: {error}");
                std::process::exit(1);
            }
        }
        return;
    }

    tauri::Builder::default()
        .manage(ServiceProcessState::default())
        .manage(NativeRuntimeState::default())
        .invoke_handler(tauri::generate_handler![
            launch_desktop_language,
            evaluate_native_runtime_preview,
            start_native_runtime,
            poll_native_runtime_market,
            poll_native_runtime_account,
            execute_native_runtime_cycle,
            native_runtime_status,
            set_native_runtime_paused,
            stop_native_runtime,
            save_native_runtime_config,
            load_native_runtime_config,
            service_api_request,
            service_process_status,
            start_service_api,
            stop_service_api
        ])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_title(&app_banner("Tauri"));
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Tauri desktop shell");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn account_bootstrap(
        refreshed_at_ms: i64,
        signal_evaluation_allowed: bool,
        status_message: &str,
    ) -> NativeRuntimeAccountBootstrapState {
        NativeRuntimeAccountBootstrapState {
            refreshed_at_ms,
            signal_evaluation_allowed,
            status_message: status_message.to_owned(),
            balance: BinanceAccountSnapshot {
                asset: "USDT".to_owned(),
                usdt_balance: 100.0,
                total_usdt_balance: 100.0,
                available_usdt_balance: 100.0,
            },
            positions: Vec::new(),
            position_mode: BinanceFuturesPositionMode {
                dual_side_position: true,
                position_mode: "Hedge".to_owned(),
            },
            multi_assets_mode: BinanceFuturesMultiAssetsMode {
                multi_assets_margin: false,
            },
        }
    }

    fn candles(count: i64) -> Vec<NativeRuntimeCandleInput> {
        (0..count)
            .map(|index| {
                let close = 100.0 + index as f64;
                NativeRuntimeCandleInput {
                    open_time_ms: index * 60_000,
                    open: close - 0.5,
                    high: close + 1.0,
                    low: close - 1.0,
                    close,
                    volume: 1_000.0 + index as f64,
                }
            })
            .collect()
    }

    #[test]
    fn native_runtime_preview_calculates_python_configured_indicators_read_only() {
        let response = evaluate_native_runtime_preview(
            json!({
                "indicators": {
                    "rsi": {
                        "enabled": true,
                        "length": 14,
                        "buy_value": 30.0,
                        "sell_value": 70.0
                    }
                }
            }),
            candles(64),
            "btcusdt".to_owned(),
            "1m".to_owned(),
            64 * 60_000,
            true,
        );

        assert!(response.ok, "{}", response.error);
        assert!(response.strategy_evaluated);
        assert!(
            response
                .computed_indicator_keys
                .iter()
                .any(|key| key == "rsi")
        );
        assert!(response.unsupported_indicator_keys.is_empty());
        assert!(!response.trading_execution_supported);
    }

    #[test]
    fn native_runtime_preview_rejects_malformed_python_indicator_config() {
        let response = evaluate_native_runtime_preview(
            json!({"indicators": {"rsi": "not-an-object"}}),
            candles(64),
            "BTCUSDT".to_owned(),
            "1m".to_owned(),
            64 * 60_000,
            true,
        );

        assert!(!response.ok);
        assert!(!response.error.is_empty());
        assert!(!response.trading_execution_supported);
    }

    #[test]
    fn native_runtime_controller_delegates_non_binance_or_non_futures_connectors() {
        let state = NativeRuntimeState::default();
        let non_binance = state.start(
            &json!({
                "selected_exchange": "Bybit",
                "connector_backend": "ccxt"
            }),
            1_700_000_000_000,
        );
        assert!(!non_binance.ok);
        assert!(
            non_binance
                .error
                .contains("Python Service API/provider connector-owned")
        );

        let spot = state.start(
            &json!({
                "selected_exchange": "Binance",
                "connector_backend": "binance-sdk-spot"
            }),
            1_700_000_000_000,
        );
        assert!(!spot.ok);
        assert!(
            spot.error
                .contains("only Python's explicit Binance futures connector keys")
        );
    }

    #[test]
    fn native_runtime_market_poll_spec_matches_python_connector_and_mode_rules() {
        let usds = native_runtime_market_poll_spec(&json!({
            "mode": "Live",
            "symbols": ["ethusdt"],
            "intervals": ["5m"]
        }))
        .expect("USD-M poll spec");
        assert_eq!(usds.market, BinanceMarket::Futures);
        assert_eq!(usds.symbol, "ETHUSDT");
        assert_eq!(usds.interval, "5m");
        assert!(!usds.testnet);

        let coin = native_runtime_market_poll_spec(&json!({
            "connector_backend": "binance-sdk-derivatives-trading-coin-futures",
            "mode": "Sandbox"
        }))
        .expect("Coin-M poll spec");
        assert_eq!(coin.market, BinanceMarket::CoinFutures);
        assert_eq!(coin.symbol, "BTCUSD_PERP");
        assert_eq!(coin.interval, "1m");
        assert!(coin.testnet);
    }

    #[test]
    fn native_runtime_market_poll_rejects_idle_runtime_before_network_access() {
        let state = NativeRuntimeState::default();
        let response = state.poll_market(&json!({}), 1_700_000_000_000);
        assert!(!response.ok);
        assert_eq!(response.error, "Native Rust runtime is not running.");
    }

    #[test]
    fn native_runtime_guarded_execution_rejects_idle_runtime_before_network_access() {
        let state = NativeRuntimeState::default();
        let response = state.execute_guarded_cycle(
            &json!({}),
            "test-key".to_owned(),
            "test-secret".to_owned(),
            1_700_000_000_000,
        );
        assert!(!response.ok);
        assert_eq!(response.state, "blocked");
        assert_eq!(response.error, "Native Rust runtime is not running.");
    }

    #[test]
    fn native_runtime_order_engine_stays_dry_run_until_promotion() {
        let engine = native_runtime_order_engine(
            &json!({
                "mode": "Live",
                "live_trading_enabled": true,
                "live_trading_acknowledgement": "I_UNDERSTAND_LIVE_TRADING_RISK",
            }),
            1_700_000_000_000,
        );
        assert!(engine.safety.live_trading_enabled);
        assert_eq!(
            engine.safety.live_trading_acknowledgement,
            "I_UNDERSTAND_LIVE_TRADING_RISK"
        );
        assert!(engine.dry_run);
    }

    #[test]
    fn native_runtime_order_engine_uses_python_audit_and_circuit_config() {
        let engine = native_runtime_order_engine(
            &json!({
                "order_audit_enabled": false,
                "order_audit_log_path": "C:/audit/runtime-orders.jsonl",
                "order_audit_max_bytes": 4096,
                "order_audit_backup_count": 3,
                "connector_order_block_circuit_breaker_enabled": false,
                "connector_order_block_pause_threshold": 7,
                "connector_order_block_window_seconds": 45.0,
                "connector_order_circuit_incident_log_path": "C:/audit/circuit.jsonl",
                "connector_order_circuit_incident_log_max_bytes": 2048,
                "connector_order_circuit_incident_log_backup_count": 2,
            }),
            1_700_000_000_000,
        );
        assert!(!engine.audit_config.enabled);
        assert_eq!(engine.audit_config.path, "C:/audit/runtime-orders.jsonl");
        assert_eq!(engine.audit_config.max_bytes, 4096);
        assert_eq!(engine.audit_config.backup_count, 3);
        assert_eq!(
            engine.connector_incident_path,
            PathBuf::from("C:/audit/circuit.jsonl")
        );
        assert_eq!(engine.connector_incident_max_bytes, 2048);
        assert_eq!(engine.connector_incident_backup_count, 2);
        let circuit_config = engine.circuit.config();
        assert!(!circuit_config.enabled);
        assert_eq!(circuit_config.block_threshold, 7);
        assert_eq!(circuit_config.block_window_seconds, 45.0);
    }

    #[test]
    fn native_runtime_account_bootstrap_requires_a_recent_read() {
        let bootstrap = account_bootstrap(1_700_000_000_000, true, "account ready");
        assert!(native_runtime_account_bootstrap_is_fresh(
            &bootstrap,
            1_700_000_300_000
        ));
        assert!(!native_runtime_account_bootstrap_is_fresh(
            &bootstrap,
            1_700_000_300_001
        ));
    }

    #[test]
    fn native_runtime_failed_account_poll_clears_signal_gate() {
        let state = NativeRuntimeState::default();
        let config = json!({
            "symbols": ["BTCUSDT"],
            "intervals": ["1m"],
            "indicators": {"rsi": {"enabled": true}}
        });
        let started = state.start(&config, 1_700_000_000_000);
        assert!(started.ok, "{}", started.error);
        {
            let mut managed = state.inner.lock().expect("runtime state lock");
            managed.account_bootstrap =
                Some(account_bootstrap(1_700_000_000_000, true, "account ready"));
        }

        let response = state.poll_account(&config, String::new(), String::new(), 1_700_000_001_000);
        assert!(!response.ok);
        assert!(response.error.contains("API key and API secret"));
        let managed = state.inner.lock().expect("runtime state lock");
        assert!(managed.account_bootstrap.is_none());
    }

    #[test]
    fn native_runtime_controller_tracks_lifecycle_without_retaining_credentials() {
        let state = NativeRuntimeState::default();
        let started = state.start(
            &json!({
                "symbols": ["ethusdt"],
                "intervals": ["5m"],
                "position_mode": "One-way",
                "margin_mode": "Cross",
                "assets_mode": "Multi-Assets Mode",
                "leverage": 200,
                "loop_interval_override": "15m",
                "api_key": "must-not-appear",
                "api_secret": "also-must-not-appear"
            }),
            1_700_000_000_000,
        );

        assert!(started.ok, "{}", started.error);
        assert_eq!(started.status["runtime_active"], true);
        assert_eq!(started.status["lifecycle_phase"], "running");
        assert_eq!(started.lifecycle["symbol"], "ETHUSDT");
        assert_eq!(started.lifecycle["interval"], "5m");
        assert_eq!(
            started.lifecycle["execution_owner"],
            "native-rust-coordinator"
        );
        assert!(!started.trading_execution_supported);
        assert!(started.promotion_required);

        let paused = state.set_paused(true, 1_700_000_005_000);
        assert!(paused.ok, "{}", paused.error);
        assert_eq!(paused.status["runtime_active"], true);
        assert_eq!(paused.status["paused"], true);
        assert_eq!(paused.status["lifecycle_phase"], "paused");

        let resumed = state.set_paused(false, 1_700_000_010_000);
        assert!(resumed.ok, "{}", resumed.error);
        assert_eq!(resumed.status["lifecycle_phase"], "running");

        let stopped = state.stop_with_close_request(
            true,
            json!({
                "symbols": ["ETHUSDT"],
                "intervals": ["5m"],
                "position_mode": "One-way",
            }),
            "must-not-appear".to_owned(),
            "also-must-not-appear".to_owned(),
            1_700_000_015_000,
        );
        assert!(stopped.ok, "{}", stopped.error);
        assert_eq!(stopped.status["runtime_active"], false);
        assert_eq!(stopped.status["lifecycle_phase"], "idle");
        assert!(stopped.message.contains("not dispatched"));

        let serialized = serde_json::to_string(&started).expect("response should serialize");
        assert!(!serialized.contains("must-not-appear"));
        assert!(!serialized.contains("also-must-not-appear"));
        let stopped_serialized =
            serde_json::to_string(&stopped).expect("response should serialize");
        assert!(!stopped_serialized.contains("must-not-appear"));
        assert!(!stopped_serialized.contains("also-must-not-appear"));
    }

    #[test]
    fn packaged_smoke_validates_contract_without_opening_a_window() {
        let message =
            run_packaged_smoke().expect("packaged smoke should pass while promotion is gated");
        assert!(message.contains("Trading Bot Tauri packaged smoke passed"));
        assert!(message.contains(python_source_contract_hash()));
        assert!(message.contains("native trading disabled"));
    }

    #[test]
    fn remote_service_api_endpoint_requires_an_explicit_token() {
        assert!(validate_service_api_endpoint_access("http://127.0.0.1:8000", "", false).is_ok());
        assert!(
            validate_service_api_endpoint_access("http://192.168.1.10:8000", "", false)
                .unwrap_err()
                .contains("Public service API endpoints are disabled")
        );
        assert!(
            validate_service_api_endpoint_access("http://192.168.1.10:8000", "", true)
                .unwrap_err()
                .contains("BOT_SERVICE_API_TOKEN")
        );
        assert!(
            validate_service_api_endpoint_access(
                "https://service.example.test",
                "session-token",
                true,
            )
            .is_ok()
        );
    }

    #[test]
    fn service_api_proxy_validation_matches_the_generated_python_schema() {
        assert_eq!(
            validate_service_api_method("config", "patch"),
            Ok("PATCH".to_owned())
        );
        assert!(
            validate_service_api_method("config", "post")
                .unwrap_err()
                .contains("not declared by the Python contract")
        );
        assert!(
            validate_service_api_fields(
                "dashboard",
                "GET",
                None,
                Some(&BTreeMap::from([("log_limit".to_owned(), "25".to_owned())])),
            )
            .is_ok()
        );
        assert!(
            validate_service_api_fields(
                "dashboard",
                "GET",
                None,
                Some(&BTreeMap::from([("unexpected".to_owned(), "1".to_owned())])),
            )
            .unwrap_err()
            .contains("query field unexpected")
        );
        assert!(
            validate_service_api_fields(
                "terminal_run",
                "POST",
                Some(&json!({"unexpected": true})),
                None,
            )
            .unwrap_err()
            .contains("request field unexpected")
        );
    }
}
