use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
use trading_bot_core::{
    account::{BinanceApiCredentials, BinanceSignedRestClient},
    app_banner, cpp_entire_python_app_contract_parity_ready, cpp_entire_python_app_parity_ready,
    market_data::{BinanceMarket, BinanceRestMarketDataClient},
    native_full_python_app_parity_ready, native_python_app_contract_parity_ready,
    native_python_app_parity_domains, rust_entire_python_app_contract_parity_ready,
    rust_entire_python_app_parity_ready, rust_native_runtime_capabilities,
    rust_native_trading_runtime_ready, supported_frameworks,
};

fn main() {
    if std::env::args().any(|arg| arg == "--native-live-smoke-preflight") {
        if let Err(error) = run_native_live_smoke_preflight() {
            eprintln!(
                "Rust native live smoke preflight failed: {}",
                format_error_chain(error.as_ref())
            );
            std::process::exit(1);
        }
        return;
    }

    if std::env::args().any(|arg| arg == "--native-live-market-smoke-preflight") {
        if let Err(error) = run_native_live_market_smoke_preflight() {
            eprintln!(
                "Rust native live market-data smoke preflight failed: {}",
                format_error_chain(error.as_ref())
            );
            std::process::exit(1);
        }
        return;
    }

    if std::env::args().any(|arg| arg == "--native-live-market-smoke") {
        if let Err(error) = run_native_live_market_smoke() {
            eprintln!(
                "Rust native live market-data smoke failed: {}",
                format_error_chain(error.as_ref())
            );
            std::process::exit(1);
        }
        return;
    }

    if std::env::args().any(|arg| arg == "--native-live-smoke") {
        if let Err(error) = run_native_live_smoke() {
            eprintln!(
                "Rust native live smoke failed: {}",
                format_error_chain(error.as_ref())
            );
            std::process::exit(1);
        }
        return;
    }

    if std::env::args().any(|arg| arg == "--write-local-recovery-evidence") {
        if let Err(error) = run_local_recovery_evidence() {
            eprintln!(
                "Rust native local recovery evidence failed: {}",
                format_error_chain(error.as_ref())
            );
            std::process::exit(1);
        }
        return;
    }

    println!("{}", app_banner("Rust workspace"));
    println!("Supported desktop shells:");
    for framework in supported_frameworks() {
        println!("- {framework}");
    }
    println!(
        "Native Rust trading runtime ready: {}",
        rust_native_trading_runtime_ready()
    );
    println!(
        "Python app contract/catalog parity ready: {}",
        native_python_app_contract_parity_ready()
    );
    println!(
        "C++ Python app contract/catalog parity ready: {}",
        cpp_entire_python_app_contract_parity_ready()
    );
    println!(
        "Rust Python app contract/catalog parity ready: {}",
        rust_entire_python_app_contract_parity_ready()
    );
    println!(
        "Full standalone Python app parity ready: {}",
        native_full_python_app_parity_ready()
    );
    println!(
        "C++ full standalone Python app parity ready: {}",
        cpp_entire_python_app_parity_ready()
    );
    println!(
        "Rust full standalone Python app parity ready: {}",
        rust_entire_python_app_parity_ready()
    );
    println!("Python app contract parity audit:");
    for domain in native_python_app_parity_domains() {
        println!(
            "- {}: {} | C++ parity: {} | Rust parity: {}",
            domain.key, domain.title, domain.cpp_full_parity, domain.rust_full_parity
        );
    }
    println!("Native runtime capability gaps:");
    for capability in rust_native_runtime_capabilities() {
        println!(
            "- {}: {} | Rust: {}",
            capability.key, capability.title, capability.rust_status
        );
    }
}

fn format_error_chain(error: &dyn std::error::Error) -> String {
    let mut parts = vec![error.to_string()];
    let mut source = error.source();
    while let Some(next) = source {
        parts.push(next.to_string());
        source = next.source();
    }
    parts.join(": ")
}

fn run_native_live_smoke_preflight() -> Result<(), Box<dyn std::error::Error>> {
    let api_key_present = env_non_empty("BINANCE_API_KEY");
    let api_secret_present = env_non_empty("BINANCE_API_SECRET");
    let confirmed = env_truthy("TRADING_BOT_RUST_LIVE_SMOKE").unwrap_or(false);
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    let missing: Vec<&str> = [
        (!api_key_present).then_some("BINANCE_API_KEY"),
        (!api_secret_present).then_some("BINANCE_API_SECRET"),
        (!confirmed).then_some("TRADING_BOT_RUST_LIVE_SMOKE=1"),
    ]
    .into_iter()
    .flatten()
    .collect();
    let ok = missing.is_empty();
    let report = json!({
        "ok": ok,
        "mode": "native_live_smoke_preflight",
        "network_access_attempted": false,
        "order_submission_attempted": false,
        "read_only": true,
        "runtime_ready_claimed": false,
        "secrets_redacted": true,
        "prerequisites": {
            "binance_api_key_present": api_key_present,
            "binance_api_secret_present": api_secret_present,
            "live_smoke_confirmation_present": confirmed,
            "binance_testnet": testnet,
            "symbol": symbol,
            "interval": interval,
        },
        "missing": missing,
        "evidence_dir": evidence_dir.display().to_string(),
        "expected_artifacts": [
            "rust-native-live-market-data-smoke.json",
            "rust-native-live-account-read-smoke.json"
        ],
        "operator_command": "TRADING_BOT_RUST_LIVE_SMOKE=1 BINANCE_API_KEY=... BINANCE_API_SECRET=... BINANCE_TESTNET=true cargo run -p trading-bot-rust -- --native-live-smoke"
    });
    println!("{}", serde_json::to_string_pretty(&report)?);
    if ok {
        Ok(())
    } else {
        Err("live smoke prerequisites are incomplete; no network request was attempted".into())
    }
}

fn run_native_live_market_smoke_preflight() -> Result<(), Box<dyn std::error::Error>> {
    let confirmed = env_truthy("TRADING_BOT_RUST_MARKET_SMOKE").unwrap_or(false);
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    let missing: Vec<&str> = [(!confirmed).then_some("TRADING_BOT_RUST_MARKET_SMOKE=1")]
        .into_iter()
        .flatten()
        .collect();
    let ok = missing.is_empty();
    let report = json!({
        "ok": ok,
        "mode": "native_live_market_smoke_preflight",
        "network_access_attempted": false,
        "order_submission_attempted": false,
        "read_only": true,
        "runtime_ready_claimed": false,
        "secrets_redacted": true,
        "prerequisites": {
            "market_smoke_confirmation_present": confirmed,
            "binance_testnet": testnet,
            "symbol": symbol,
            "interval": interval,
        },
        "missing": missing,
        "evidence_dir": evidence_dir.display().to_string(),
        "expected_artifacts": [
            "rust-native-live-market-data-smoke.json"
        ],
        "operator_command": "TRADING_BOT_RUST_MARKET_SMOKE=1 BINANCE_TESTNET=true cargo run -p trading-bot-rust -- --native-live-market-smoke"
    });
    println!("{}", serde_json::to_string_pretty(&report)?);
    if ok {
        Ok(())
    } else {
        Err("market-data smoke prerequisite is incomplete; no network request was attempted".into())
    }
}

fn run_native_live_market_smoke() -> Result<(), Box<dyn std::error::Error>> {
    require_market_smoke_confirmation()?;
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());
    let market_client = BinanceRestMarketDataClient::new(BinanceMarket::Futures, testnet)?;

    println!(
        "Rust native live market-data smoke: futures {} endpoint, symbol={}, interval={}",
        if testnet { "testnet" } else { "production" },
        symbol,
        interval
    );
    println!(
        "This smoke is public/read-only; it does not use account credentials or submit orders."
    );

    let evidence = collect_market_smoke_evidence(&market_client, testnet, &symbol, &interval)?;
    write_market_smoke_evidence(evidence)?;
    println!(
        "Rust native live market-data smoke completed; signed account and standalone trading evidence remain gated."
    );
    Ok(())
}

fn run_native_live_smoke() -> Result<(), Box<dyn std::error::Error>> {
    require_live_smoke_confirmation()?;
    let api_key = env_required("BINANCE_API_KEY")?;
    let api_secret = env_required("BINANCE_API_SECRET")?;
    let credentials = BinanceApiCredentials::new(api_key, api_secret);
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());

    let market_client = BinanceRestMarketDataClient::new(BinanceMarket::Futures, testnet)?;
    let account_client = BinanceSignedRestClient::new(BinanceMarket::Futures, testnet)?;

    println!(
        "Rust native live smoke: futures {} endpoint, symbol={}, interval={}",
        if testnet { "testnet" } else { "production" },
        symbol,
        interval
    );
    println!("This smoke is read-only; it does not submit, modify, or cancel orders.");

    let market_evidence =
        collect_market_smoke_evidence(&market_client, testnet, &symbol, &interval)?;

    let position_mode = account_client.fetch_futures_position_mode(&credentials)?;
    println!(
        "position mode fetched: {} dual_side={}",
        position_mode.position_mode, position_mode.dual_side_position
    );
    let multi_assets_mode = account_client.fetch_futures_multi_assets_mode(&credentials)?;
    println!(
        "multi-assets mode fetched: {}",
        multi_assets_mode.multi_assets_margin
    );
    let balance = account_client.fetch_usdt_balance(&credentials)?;
    println!(
        "USDT balance fetched: asset={} totals redacted from smoke output",
        balance.asset
    );
    let positions = account_client.fetch_open_futures_positions(&credentials)?;
    println!("open futures positions fetched: {}", positions.len());
    write_live_smoke_evidence(LiveSmokeEvidence {
        market: market_evidence,
        account_base_url: account_client.base_url().to_owned(),
        account_endpoints: vec![
            (
                "positionSideDual",
                account_client.futures_position_mode_url(),
            ),
            (
                "multiAssetsMargin",
                account_client.futures_multi_assets_margin_url(),
            ),
            ("balance", account_client.futures_balance_url()),
            ("positionRisk", account_client.futures_position_risk_url()),
        ],
        position_mode: position_mode.position_mode,
        dual_side_position: position_mode.dual_side_position,
        multi_assets_margin: multi_assets_mode.multi_assets_margin,
        balance_asset: balance.asset,
        positions_count: positions.len(),
    })?;
    println!(
        "Rust native live smoke completed; standalone native trading execution remains disabled."
    );
    Ok(())
}

struct MarketSmokeEvidence {
    testnet: bool,
    symbol: String,
    interval: String,
    market_base_url: String,
    market_endpoints: Vec<(&'static str, String)>,
    symbols_count: usize,
    candles_count: usize,
    ticker_symbol: String,
}

struct LiveSmokeEvidence {
    market: MarketSmokeEvidence,
    account_base_url: String,
    account_endpoints: Vec<(&'static str, String)>,
    position_mode: String,
    dual_side_position: bool,
    multi_assets_margin: bool,
    balance_asset: String,
    positions_count: usize,
}

fn collect_market_smoke_evidence(
    market_client: &BinanceRestMarketDataClient,
    testnet: bool,
    symbol: &str,
    interval: &str,
) -> Result<MarketSmokeEvidence, Box<dyn std::error::Error>> {
    let symbols = market_client.fetch_usdt_symbols(false, Some(5))?;
    println!("market symbols fetched: {}", symbols.len());
    let candles = market_client.fetch_klines(symbol, interval, 10)?;
    println!("klines fetched: {}", candles.len());
    let ticker = market_client.fetch_ticker_price(symbol)?;
    println!("ticker fetched: {} @ {}", ticker.symbol, ticker.price);
    Ok(MarketSmokeEvidence {
        testnet,
        symbol: symbol.to_owned(),
        interval: interval.to_owned(),
        market_base_url: market_client.base_url().to_owned(),
        market_endpoints: vec![
            ("exchangeInfo", market_client.exchange_info_url()),
            ("klines", market_client.klines_url()),
            ("tickerPrice", market_client.ticker_price_url()),
        ],
        symbols_count: symbols.len(),
        candles_count: candles.len(),
        ticker_symbol: ticker.symbol,
    })
}

fn write_market_smoke_evidence(
    evidence: MarketSmokeEvidence,
) -> Result<(), Box<dyn std::error::Error>> {
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    fs::create_dir_all(&evidence_dir)?;
    let payload = build_market_smoke_payload(
        &evidence,
        current_unix_timestamp_label(),
        current_git_commit(),
        current_source_tree_clean(),
        std::env::args().collect::<Vec<_>>().join(" "),
    );
    write_json_file(
        &evidence_dir.join("rust-native-live-market-data-smoke.json"),
        &payload,
    )?;
    println!(
        "Rust native live market-data smoke evidence written to {}",
        evidence_dir.display()
    );
    Ok(())
}

fn build_market_smoke_payload(
    evidence: &MarketSmokeEvidence,
    generated_at: String,
    commit: String,
    source_tree_clean: bool,
    command: String,
) -> Value {
    let environment = json!({
        "binance_testnet": evidence.testnet,
        "symbol": evidence.symbol.as_str(),
        "interval": evidence.interval.as_str(),
        "market_base_url": evidence.market_base_url.as_str(),
        "rust_package": "trading-bot-rust"
    });
    json!({
        "evidence_id": "rust-native-live-market-data-smoke",
        "status": "passed",
        "evidence_scope": if evidence.testnet { "live_testnet" } else { "live_production" },
        "generated_at": generated_at,
        "commit": commit,
        "source_tree_clean": source_tree_clean,
        "command": command,
        "environment": environment,
        "read_only": true,
        "order_submission_attempted": false,
        "secrets_redacted": true,
        "runtime_ready_claimed": false,
        "endpoints": endpoint_rows(&evidence.market_endpoints),
        "suite_results": [
            {
                "name": "fetch_usdt_symbols",
                "status": "passed",
                "observed_count": evidence.symbols_count
            },
            {
                "name": "fetch_klines",
                "status": "passed",
                "observed_count": evidence.candles_count
            },
            {
                "name": "fetch_ticker_price",
                "status": "passed",
                "symbol": evidence.ticker_symbol.as_str()
            }
        ]
    })
}

fn write_live_smoke_evidence(
    evidence: LiveSmokeEvidence,
) -> Result<(), Box<dyn std::error::Error>> {
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    fs::create_dir_all(&evidence_dir)?;
    let generated_at = current_unix_timestamp_label();
    let commit = current_git_commit();
    let source_tree_clean = current_source_tree_clean();
    let command = std::env::args().collect::<Vec<_>>().join(" ");
    let market_payload = build_market_smoke_payload(
        &evidence.market,
        generated_at.clone(),
        commit.clone(),
        source_tree_clean,
        command.clone(),
    );
    let account_environment = json!({
        "binance_testnet": evidence.market.testnet,
        "symbol": evidence.market.symbol.as_str(),
        "interval": evidence.market.interval.as_str(),
        "market_base_url": evidence.market.market_base_url.as_str(),
        "account_base_url": evidence.account_base_url,
        "api_key_present": true,
        "api_secret_present": true,
        "signed_account_read": true,
        "secrets_in_artifact": false,
        "rust_package": "trading-bot-rust"
    });
    let account_payload = json!({
        "evidence_id": "rust-native-live-account-read-smoke",
        "status": "passed",
        "evidence_scope": if evidence.market.testnet { "live_testnet" } else { "live_production" },
        "generated_at": generated_at,
        "commit": commit,
        "source_tree_clean": source_tree_clean,
        "command": command,
        "environment": account_environment,
        "read_only": true,
        "order_submission_attempted": false,
        "secrets_redacted": true,
        "runtime_ready_claimed": false,
        "endpoints": endpoint_rows(&evidence.account_endpoints),
        "suite_results": [
            {
                "name": "fetch_futures_position_mode",
                "status": "passed",
                "position_mode": evidence.position_mode,
                "dual_side_position": evidence.dual_side_position
            },
            {
                "name": "fetch_futures_multi_assets_mode",
                "status": "passed",
                "multi_assets_margin": evidence.multi_assets_margin
            },
            {
                "name": "fetch_usdt_balance",
                "status": "passed",
                "asset": evidence.balance_asset,
                "balances_redacted": true
            },
            {
                "name": "fetch_open_futures_positions",
                "status": "passed",
                "observed_count": evidence.positions_count
            }
        ]
    });

    write_json_file(
        &evidence_dir.join("rust-native-live-market-data-smoke.json"),
        &market_payload,
    )?;
    write_json_file(
        &evidence_dir.join("rust-native-live-account-read-smoke.json"),
        &account_payload,
    )?;
    println!(
        "Rust native live smoke evidence written to {}",
        evidence_dir.display()
    );
    Ok(())
}

fn run_local_recovery_evidence() -> Result<(), Box<dyn std::error::Error>> {
    let stream_recovery = run_cargo_test(
        "native_runtime_live_ingestion_bridge_redacts_errors_and_recovers",
        &[
            "test",
            "-p",
            "trading-bot-core",
            "native_runtime_live_ingestion_bridge_redacts_errors_and_recovers",
            "--",
            "--nocapture",
        ],
    )?;
    let order_engine = run_cargo_test(
        "runtime_order_engine",
        &[
            "test",
            "-p",
            "trading-bot-core",
            "runtime_order_engine",
            "--",
            "--nocapture",
        ],
    )?;
    let order_guard = run_cargo_test(
        "order_guard",
        &[
            "test",
            "-p",
            "trading-bot-core",
            "order_guard",
            "--",
            "--nocapture",
        ],
    )?;
    let order_audit = run_cargo_test(
        "order_audit",
        &[
            "test",
            "-p",
            "trading-bot-core",
            "order_audit",
            "--",
            "--nocapture",
        ],
    )?;
    let risk = run_cargo_test(
        "risk",
        &[
            "test",
            "-p",
            "trading-bot-core",
            "risk",
            "--",
            "--nocapture",
        ],
    )?;

    let all_results = [
        &stream_recovery,
        &order_engine,
        &order_guard,
        &order_audit,
        &risk,
    ];
    if let Some(failed) = all_results.iter().find(|result| !result.passed) {
        return Err(format!(
            "{} failed while generating deterministic recovery evidence",
            failed.name
        )
        .into());
    }

    let evidence_dir = rust_native_runtime_evidence_dir()?;
    fs::create_dir_all(&evidence_dir)?;
    let generated_at = current_unix_timestamp_label();
    let commit = current_git_commit();
    let source_tree_clean = current_source_tree_clean();
    let command = std::env::args().collect::<Vec<_>>().join(" ");
    let environment = json!({
        "scope": "deterministic_local",
        "rust_package": "trading-bot-rust",
        "workspace": rust_workspace_dir().display().to_string()
    });

    let stream_payload = json!({
        "evidence_id": "rust-native-live-stream-recovery",
        "status": "passed",
        "evidence_scope": "deterministic_local",
        "generated_at": generated_at.clone(),
        "commit": commit.clone(),
        "source_tree_clean": source_tree_clean,
        "command": command.clone(),
        "environment": environment.clone(),
        "secrets_redacted": true,
        "runtime_ready_claimed": false,
        "recovery_scenarios": [
            {
                "name": "websocket_error_redaction_and_reconnect_recovery",
                "status": "passed",
                "source": stream_recovery.name.as_str()
            }
        ],
        "suite_results": [stream_recovery.as_json()]
    });
    let order_payload = json!({
        "evidence_id": "rust-native-order-guard-recovery",
        "status": "passed",
        "evidence_scope": "deterministic_local",
        "generated_at": generated_at,
        "commit": commit,
        "source_tree_clean": source_tree_clean,
        "command": command,
        "environment": environment,
        "secrets_redacted": true,
        "runtime_ready_claimed": false,
        "recovery_scenarios": [
            {
                "name": "guarded_submit_audit_circuit_and_dry_run_recovery",
                "status": "passed",
                "source": order_engine.name.as_str()
            },
            {
                "name": "live_order_guard_fail_closed_recovery",
                "status": "passed",
                "source": order_guard.name.as_str()
            },
            {
                "name": "order_audit_redaction_and_status_recovery",
                "status": "passed",
                "source": order_audit.name.as_str()
            },
            {
                "name": "risk_close_decision_recovery",
                "status": "passed",
                "source": risk.name.as_str()
            }
        ],
        "suite_results": [
            order_engine.as_json(),
            order_guard.as_json(),
            order_audit.as_json(),
            risk.as_json()
        ]
    });

    write_json_file(
        &evidence_dir.join("rust-native-live-stream-recovery.json"),
        &stream_payload,
    )?;
    write_json_file(
        &evidence_dir.join("rust-native-order-guard-recovery.json"),
        &order_payload,
    )?;
    println!(
        "Rust native deterministic recovery evidence written to {}",
        evidence_dir.display()
    );
    println!("This local evidence does not enable standalone native Rust trading.");
    Ok(())
}

struct TestCommandResult {
    name: String,
    command: String,
    passed: bool,
    stdout_tail: String,
    stderr_tail: String,
}

impl TestCommandResult {
    fn status_label(&self) -> &'static str {
        if self.passed { "passed" } else { "failed" }
    }

    fn as_json(&self) -> Value {
        json!({
            "name": self.name,
            "status": self.status_label(),
            "command": self.command,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail
        })
    }
}

fn run_cargo_test(
    name: &str,
    args: &[&str],
) -> Result<TestCommandResult, Box<dyn std::error::Error>> {
    let output = Command::new("cargo")
        .args(args)
        .current_dir(rust_workspace_dir())
        .output()?;
    Ok(TestCommandResult {
        name: name.to_owned(),
        command: format!("cargo {}", args.join(" ")),
        passed: output.status.success(),
        stdout_tail: text_tail(&String::from_utf8_lossy(&output.stdout), 1600),
        stderr_tail: text_tail(&String::from_utf8_lossy(&output.stderr), 1600),
    })
}

fn text_tail(text: &str, max_chars: usize) -> String {
    let trimmed = text.trim();
    if trimmed.len() <= max_chars {
        return trimmed.to_owned();
    }
    let start = trimmed
        .char_indices()
        .rev()
        .take_while(|(index, _)| trimmed.len() - *index <= max_chars)
        .last()
        .map(|(index, _)| index)
        .unwrap_or(0);
    trimmed[start..].to_owned()
}

fn endpoint_rows(endpoints: &[(&'static str, String)]) -> Vec<Value> {
    endpoints
        .iter()
        .map(|(name, url)| {
            json!({
                "name": name,
                "url": url,
                "status": "passed"
            })
        })
        .collect()
}

fn write_json_file(path: &Path, payload: &Value) -> Result<(), Box<dyn std::error::Error>> {
    fs::write(path, serde_json::to_string_pretty(payload)? + "\n")?;
    Ok(())
}

fn rust_native_runtime_evidence_dir() -> Result<PathBuf, Box<dyn std::error::Error>> {
    if let Ok(path) = std::env::var("RUST_NATIVE_RUNTIME_EVIDENCE_DIR") {
        let path = path.trim();
        if !path.is_empty() {
            return Ok(PathBuf::from(path));
        }
    }
    Ok(repo_root()
        .join("artifacts")
        .join("rust-native-runtime-evidence"))
}

fn repo_root() -> PathBuf {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output();
    if let Ok(output) = output {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_owned();
            if !path.is_empty() {
                return PathBuf::from(path);
            }
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn rust_workspace_dir() -> PathBuf {
    let candidate = repo_root().join("experiments").join("rust-shells");
    if candidate.join("Cargo.toml").is_file() {
        candidate
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    }
}

fn current_git_commit() -> String {
    if let Ok(value) = std::env::var("GITHUB_SHA").or_else(|_| std::env::var("TRADING_BOT_COMMIT"))
    {
        let value = value.trim();
        if !value.is_empty() {
            return value.to_owned();
        }
    }
    let output = Command::new("git").args(["rev-parse", "HEAD"]).output();
    if let Ok(output) = output {
        if output.status.success() {
            let value = String::from_utf8_lossy(&output.stdout).trim().to_owned();
            if !value.is_empty() {
                return value;
            }
        }
    }
    "unknown-local-commit".to_owned()
}

fn current_source_tree_clean() -> bool {
    let output = Command::new("git")
        .args(["status", "--porcelain", "--untracked-files=no"])
        .current_dir(repo_root())
        .output();
    if let Ok(output) = output {
        return output.status.success()
            && String::from_utf8_lossy(&output.stdout).trim().is_empty();
    }
    false
}

fn current_unix_timestamp_label() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    format!("unix:{seconds}")
}

fn require_live_smoke_confirmation() -> Result<(), Box<dyn std::error::Error>> {
    if env_truthy("TRADING_BOT_RUST_LIVE_SMOKE").unwrap_or(false) {
        return Ok(());
    }
    Err("set TRADING_BOT_RUST_LIVE_SMOKE=1 to confirm live API smoke execution".into())
}

fn require_market_smoke_confirmation() -> Result<(), Box<dyn std::error::Error>> {
    if env_truthy("TRADING_BOT_RUST_MARKET_SMOKE").unwrap_or(false) {
        return Ok(());
    }
    Err("set TRADING_BOT_RUST_MARKET_SMOKE=1 to confirm public market-data smoke execution".into())
}

fn env_required(name: &str) -> Result<String, Box<dyn std::error::Error>> {
    let value = std::env::var(name).unwrap_or_default();
    let value = value.trim();
    if value.is_empty() {
        Err(format!("{name} is required for Rust native live smoke").into())
    } else {
        Ok(value.to_owned())
    }
}

fn env_non_empty(name: &str) -> bool {
    std::env::var(name)
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
}

fn env_truthy(name: &str) -> Option<bool> {
    let value = std::env::var(name).ok()?;
    let value = value.trim().to_ascii_lowercase();
    Some(matches!(value.as_str(), "1" | "true" | "yes" | "on"))
}
