#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Manager, State};
use trading_bot_core::{
    app_banner,
    market_data::BinanceKlineCandle,
    native_python_app_contract_parity_ready,
    native_runtime::{
        NativeRuntimeCycleInput, NativeRuntimeLoop, NativeRuntimeLoopConfig,
        NativeRuntimeReadOnlyMarketCycleInput,
    },
    python_source_contract_hash, rust_trading_execution_supported, service_api_route_path,
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

#[derive(Default)]
struct ServiceProcessState {
    child: Mutex<Option<Child>>,
}

#[derive(Default)]
struct NativeRuntimeManagedState {
    runtime: Option<NativeRuntimeLoop>,
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

    fn stop(&self, close_positions: bool, now_ms: i64) -> NativeRuntimeControlResponse {
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
        let Some(runtime) = managed.runtime.as_mut() else {
            return NativeRuntimeControlResponse::error(
                "Native Rust runtime state is unavailable.",
            );
        };

        // Tauri does not claim a close-all dispatch until the promoted worker owns
        // credentialed position reconciliation. Stopping the fail-closed coordinator
        // is still safe because it cannot have submitted native live orders.
        let close_dispatched = close_positions && rust_trading_execution_supported();
        let stop = runtime.request_stop(
            close_dispatched,
            "tauri-native-runtime",
            true,
            if close_positions && !close_dispatched {
                "Close positions was not dispatched because native live execution is not promoted."
            } else {
                "Native runtime stop accepted."
            },
        );
        runtime.mark_idle_after_stop("tauri-native-runtime", &stop.status_message);
        managed.running = false;
        managed.paused = false;
        managed.started_at_ms = None;
        native_runtime_snapshot(
            &mut managed,
            now_ms,
            if close_positions && !close_dispatched {
                "Native Rust runtime stopped; no live close was required or dispatched while execution is promotion-gated."
            } else {
                "Native Rust runtime stopped."
            },
        )
    }
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

fn build_service_url(
    base_url: &str,
    route_name: &str,
    query: Option<BTreeMap<String, String>>,
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
    let (url, route_path) =
        match build_service_url(&base_url, &route_name, query, allow_public_network_endpoint) {
            Ok(value) => value,
            Err(exc) => return response_error(&route_name, "", 0, exc),
        };
    let method = method.trim().to_uppercase();
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
    now_ms: i64,
) -> NativeRuntimeControlResponse {
    state.stop(close_positions, now_ms)
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
            native_runtime_status,
            set_native_runtime_paused,
            stop_native_runtime,
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

        let stopped = state.stop(true, 1_700_000_015_000);
        assert!(stopped.ok, "{}", stopped.error);
        assert_eq!(stopped.status["runtime_active"], false);
        assert_eq!(stopped.status["lifecycle_phase"], "idle");
        assert!(stopped.message.contains("no live close"));

        let serialized = serde_json::to_string(&started).expect("response should serialize");
        assert!(!serialized.contains("must-not-appear"));
        assert!(!serialized.contains("also-must-not-appear"));
    }

    #[test]
    fn packaged_smoke_validates_contract_without_opening_a_window() {
        let message =
            run_packaged_smoke().expect("packaged smoke should pass while promotion is gated");
        assert!(message.contains("Trading Bot Tauri packaged smoke passed"));
        assert!(message.contains(python_source_contract_hash()));
        assert!(message.contains("native trading disabled"));
    }
}
