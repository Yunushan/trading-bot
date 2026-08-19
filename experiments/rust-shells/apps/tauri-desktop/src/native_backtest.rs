use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, AtomicU64, Ordering},
};
use std::thread;

use serde::Serialize;
use serde_json::{Value, json};
use tauri::State;
use trading_bot_core::{
    backtest_batch_runtime::{
        CandleLoadResult, NativeBacktestBatchRequest, run_native_backtest_batch,
    },
    market_data::{
        BinanceMarket, BinanceRestMarketDataClient, interval_seconds,
        python_backtest_interval_seconds,
    },
    python_source_default_backtest_config, python_source_default_execution_config,
};

static NEXT_SESSION_ID: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Default)]
pub struct NativeBacktestState {
    inner: Arc<Mutex<NativeBacktestManagedState>>,
}

#[derive(Default)]
struct NativeBacktestManagedState {
    session_id: String,
    snapshot: Value,
    cancellation: Option<Arc<AtomicBool>>,
    checkpoint: Option<NativeBacktestCheckpoint>,
}

#[derive(Clone)]
struct NativeBacktestCheckpoint {
    request: NativeBacktestBatchRequest,
    completed_combo_count: u64,
    previous_runs: Vec<Value>,
    previous_errors: Vec<Value>,
}

#[derive(Debug, Serialize)]
pub struct NativeBacktestCommandResponse {
    pub ok: bool,
    pub accepted: bool,
    pub session_id: String,
    pub state: String,
    pub snapshot: Value,
    pub status_message: String,
    pub error: String,
}

fn snapshot_state(snapshot: &Value) -> String {
    snapshot
        .get("state")
        .and_then(Value::as_str)
        .unwrap_or("idle")
        .to_owned()
}

fn snapshot_message(snapshot: &Value) -> String {
    snapshot
        .get("status_message")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

fn response(
    accepted: bool,
    session_id: impl Into<String>,
    snapshot: Value,
    error: impl Into<String>,
) -> NativeBacktestCommandResponse {
    let error = error.into();
    let state = snapshot_state(&snapshot);
    NativeBacktestCommandResponse {
        ok: error.is_empty() && !matches!(state.as_str(), "failed" | "rejected"),
        accepted,
        session_id: session_id.into(),
        state,
        status_message: snapshot_message(&snapshot),
        snapshot,
        error,
    }
}

fn request_mode(payload: &Value) -> String {
    let default_mode = python_source_default_execution_config()
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or("Demo/Testnet");
    payload
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or(default_mode)
        .trim()
        .to_ascii_lowercase()
}

fn request_market(payload: &Value) -> BinanceMarket {
    let default_source = python_source_default_backtest_config()
        .get("symbol_source")
        .and_then(Value::as_str)
        .unwrap_or("Futures");
    let source = payload
        .get("symbol_source")
        .and_then(Value::as_str)
        .unwrap_or(default_source)
        .trim()
        .to_ascii_lowercase();
    if source.contains("coin") {
        BinanceMarket::CoinFutures
    } else if source.starts_with("spot") {
        BinanceMarket::Spot
    } else {
        BinanceMarket::Futures
    }
}

fn request_testnet(payload: &Value) -> bool {
    if let Some(value) = payload.get("testnet").and_then(Value::as_bool) {
        return value;
    }
    let mode = request_mode(payload);
    mode.contains("demo") || mode.contains("testnet") || mode.contains("test")
}

fn native_market_data_supported(request: &NativeBacktestBatchRequest) -> bool {
    let backend = request.connector_backend.trim().to_ascii_lowercase();
    let exchange = request.selected_exchange.trim().to_ascii_lowercase();
    (exchange.is_empty() || exchange == "binance")
        && (backend.is_empty()
            || backend.contains("binance")
            || backend == "binance-connector"
            || backend == "python-binance"
            || backend == "ccxt")
}

fn run_worker(
    request: NativeBacktestBatchRequest,
    cancellation: Arc<AtomicBool>,
    session_id: &str,
    market: BinanceMarket,
    testnet: bool,
) -> Value {
    if !native_market_data_supported(&request) {
        let message = if !request
            .selected_exchange
            .trim()
            .eq_ignore_ascii_case("binance")
        {
            format!(
                "Native Rust local backtesting supports Binance market data only; exchange '{}' requires the Python Service API.",
                request.selected_exchange
            )
        } else {
            format!(
                "Native Rust local backtesting supports Binance market-data backends only; connector '{}' requires the Python Service API.",
                request.connector_backend
            )
        };
        return json!({
            "source": "native-rust-backtest",
            "session_id": session_id,
            "execution_backend": "local",
            "state": "failed",
            "cancelled": false,
            "runs": [],
            "top_runs": [],
            "errors": [{"error": message.clone()}],
            "status_message": message,
        });
    }
    let client = match BinanceRestMarketDataClient::new(market, testnet) {
        Ok(client) => client,
        Err(error) => {
            let error_message = error.to_string();
            return json!({
                "source": "native-rust-backtest",
                "session_id": session_id,
                "state": "failed",
                "cancelled": false,
                "runs": [],
                "top_runs": [],
                "errors": [{"error": error_message.clone()}],
                "status_message": error_message,
            });
        }
    };
    let mut snapshot = run_native_backtest_batch(
        &request,
        |symbol, interval| {
            if cancellation.load(Ordering::Acquire) {
                return CandleLoadResult::failure("backtest_cancelled");
            }
            let (start_ms, end_ms) = match (request.start_ms, request.end_ms) {
                (Some(start), Some(end)) => (start, end),
                _ => {
                    return CandleLoadResult::failure(
                        "Native backtest request is missing a validated date range.",
                    );
                }
            };
            match interval_seconds(interval) {
                Ok(value) if value.is_finite() && value > 0.0 => {}
                Ok(_) => return CandleLoadResult::failure("Backtest interval must be positive."),
                Err(error) => return CandleLoadResult::failure(error.to_string()),
            };
            let warmup_ms = (request.warmup_bars as f64
                * python_backtest_interval_seconds(interval)
                * 2.0
                * 1000.0)
                .round()
                .clamp(0.0, i64::MAX as f64) as i64;
            let buffered_start_ms = start_ms.saturating_sub(warmup_ms);
            let limit = if market.is_futures() { 1_500 } else { 1_000 };
            match client.fetch_klines_range(symbol, interval, buffered_start_ms, end_ms, limit) {
                Ok(candles) => CandleLoadResult::success(candles),
                Err(error) => CandleLoadResult::failure(error.to_string()),
            }
        },
        || cancellation.load(Ordering::Acquire),
    );
    if let Some(object) = snapshot.as_object_mut() {
        object.insert("session_id".to_owned(), json!(session_id));
        object.insert("execution_backend".to_owned(), json!("local"));
    }
    snapshot
}

impl NativeBacktestState {
    fn start(&self, payload: Value) -> NativeBacktestCommandResponse {
        let resume_requested = payload
            .get("resume_checkpoint")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let market = request_market(&payload);
        let testnet = request_testnet(&payload);
        let mut managed = match self.inner.lock() {
            Ok(guard) => guard,
            Err(_) => {
                return response(
                    false,
                    "",
                    json!({"state": "failed", "status_message": "Native backtest state lock is poisoned."}),
                    "Native backtest state lock is poisoned.",
                );
            }
        };
        if managed.cancellation.is_some() {
            return response(
                false,
                managed.session_id.clone(),
                managed.snapshot.clone(),
                "A native Rust backtest session is already running.",
            );
        }

        let request = if resume_requested {
            let Some(checkpoint) = managed.checkpoint.clone() else {
                let message = "No native Rust optimizer checkpoint is available to resume.";
                let snapshot = json!({
                    "source": "native-rust-backtest",
                    "state": "failed",
                    "cancelled": false,
                    "runs": [],
                    "top_runs": [],
                    "errors": [{"error": message}],
                    "status_message": message,
                });
                return response(false, "", snapshot, message);
            };
            let mut request = checkpoint.request;
            request.resume_combo_offset = checkpoint.completed_combo_count;
            request.resume_prior_runs = checkpoint.previous_runs;
            request.resume_prior_errors = checkpoint.previous_errors;
            request
        } else {
            match NativeBacktestBatchRequest::from_python_request(&payload) {
                Ok(request) => request,
                Err(error) => {
                    let snapshot = json!({
                        "source": "native-rust-backtest",
                        "state": "failed",
                        "cancelled": false,
                        "runs": [],
                        "top_runs": [],
                        "errors": [{"error": error}],
                        "status_message": error,
                    });
                    return response(false, "", snapshot, error);
                }
            }
        };
        if !resume_requested {
            managed.checkpoint = None;
        }

        let session_id = format!(
            "native-rust-{}",
            NEXT_SESSION_ID.fetch_add(1, Ordering::Relaxed)
        );
        let cancellation = Arc::new(AtomicBool::new(false));
        let snapshot = json!({
            "source": "native-rust-backtest",
            "execution_backend": "local",
            "session_id": session_id,
            "state": "running",
            "cancelled": false,
            "runs": [],
            "top_runs": [],
            "errors": [],
            "processed_count": 0,
            "progress_percent": 0.0,
            "status_message": "Native Rust backtest is preparing market data.",
        });
        managed.session_id = session_id.clone();
        managed.snapshot = snapshot.clone();
        managed.cancellation = Some(cancellation.clone());
        drop(managed);

        let worker_state = self.clone();
        let worker_session_id = session_id.clone();
        thread::spawn(move || {
            let worker_request = request.clone();
            let snapshot = run_worker(request, cancellation, &worker_session_id, market, testnet);
            worker_state.finish(&worker_session_id, snapshot, worker_request);
        });
        response(true, session_id, snapshot, "")
    }

    fn finish(&self, session_id: &str, snapshot: Value, request: NativeBacktestBatchRequest) {
        let Ok(mut managed) = self.inner.lock() else {
            return;
        };
        if managed.session_id == session_id {
            let state = snapshot
                .get("state")
                .and_then(Value::as_str)
                .unwrap_or_default();
            if state == "budget_exhausted" {
                managed.checkpoint = Some(NativeBacktestCheckpoint {
                    completed_combo_count: snapshot
                        .get("completed_combo_count")
                        .and_then(Value::as_u64)
                        .unwrap_or(request.resume_combo_offset),
                    previous_runs: snapshot
                        .get("runs")
                        .and_then(Value::as_array)
                        .cloned()
                        .unwrap_or_default(),
                    previous_errors: snapshot
                        .get("errors")
                        .and_then(Value::as_array)
                        .cloned()
                        .unwrap_or_default(),
                    request,
                });
            } else if state == "completed" {
                managed.checkpoint = None;
            }
            managed.snapshot = snapshot;
            managed.cancellation = None;
        }
    }

    fn status(&self) -> Value {
        self.inner
            .lock()
            .map(|managed| {
                if managed.snapshot.is_null() {
                    json!({
                        "source": "native-rust-backtest",
                        "state": "idle",
                        "runs": [],
                        "top_runs": [],
                        "errors": [],
                    })
                } else {
                    managed.snapshot.clone()
                }
            })
            .unwrap_or_else(|_| {
                json!({
                    "source": "native-rust-backtest",
                    "state": "failed",
                    "status_message": "Native backtest state lock is poisoned.",
                })
            })
    }

    fn stop(&self) -> NativeBacktestCommandResponse {
        let Ok(mut managed) = self.inner.lock() else {
            return response(
                false,
                "",
                json!({"state": "failed", "status_message": "Native backtest state lock is poisoned."}),
                "Native backtest state lock is poisoned.",
            );
        };
        let Some(cancellation) = managed.cancellation.clone() else {
            return response(
                false,
                managed.session_id.clone(),
                managed.snapshot.clone(),
                "No native Rust backtest session is running.",
            );
        };
        cancellation.store(true, Ordering::Release);
        if let Some(object) = managed.snapshot.as_object_mut() {
            object.insert("state".to_owned(), json!("cancelling"));
            object.insert(
                "status_message".to_owned(),
                json!("Native Rust backtest cancellation requested."),
            );
        }
        response(
            true,
            managed.session_id.clone(),
            managed.snapshot.clone(),
            "",
        )
    }
}

#[tauri::command]
pub fn start_native_backtest(
    state: State<'_, NativeBacktestState>,
    request: Value,
) -> NativeBacktestCommandResponse {
    state.start(request)
}

#[tauri::command]
pub fn native_backtest_status(state: State<'_, NativeBacktestState>) -> Value {
    state.status()
}

#[tauri::command]
pub fn stop_native_backtest(
    state: State<'_, NativeBacktestState>,
) -> NativeBacktestCommandResponse {
    state.stop()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn omitted_native_backtest_market_and_mode_follow_python_defaults() {
        let payload = json!({});
        assert_eq!(
            request_mode(&payload),
            python_source_default_execution_config()["mode"]
                .as_str()
                .unwrap()
                .to_ascii_lowercase()
        );
        assert_eq!(
            request_market(&payload),
            match python_source_default_backtest_config()["symbol_source"]
                .as_str()
                .unwrap()
            {
                source if source.to_ascii_lowercase().contains("coin") =>
                    BinanceMarket::CoinFutures,
                source if source.to_ascii_lowercase().starts_with("spot") => BinanceMarket::Spot,
                _ => BinanceMarket::Futures,
            }
        );
    }
}
