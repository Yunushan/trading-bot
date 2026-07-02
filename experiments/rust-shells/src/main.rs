use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use trading_bot_core::{
    account::{
        BinanceAccountSnapshot, BinanceApiCredentials, BinanceFuturesMultiAssetsMode,
        BinanceFuturesPosition, BinanceFuturesPositionMode, BinanceSignedRestClient,
    },
    app_banner, cpp_entire_python_app_contract_parity_ready, cpp_entire_python_app_parity_ready,
    market_data::{
        BinanceKlineCandle, BinanceMarket, BinanceRestMarketDataClient, BinanceTickerPrice,
    },
    native_full_python_app_parity_ready, native_python_app_contract_parity_ready,
    native_python_app_parity_domains, python_source_contract_hash,
    rust_entire_python_app_contract_parity_ready, rust_entire_python_app_parity_ready,
    rust_native_runtime_capabilities, rust_native_trading_runtime_ready, supported_frameworks,
};

const MARKET_SMOKE_MAX_ATTEMPTS: usize = 3;
const MARKET_SMOKE_RETRY_DELAY: Duration = Duration::from_millis(750);
const ACCOUNT_SMOKE_MAX_ATTEMPTS: usize = 3;
const ACCOUNT_SMOKE_RETRY_DELAY: Duration = Duration::from_millis(750);
const PROMOTION_SOURCE_TREE_IGNORED_PATHS: &[&str] = &[
    "artifacts/rust-native-runtime-evidence",
    "artifacts/native-source-sync",
    "release-platform-evidence",
];

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

fn native_source_sync_binding() -> Value {
    json!({
        "required": true,
        "audit_artifact": "native-source-sync-audit",
        "audit_path": "artifacts/native-source-sync/native-source-sync-audit.json",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": python_source_contract_hash(),
        "surface_contract_required": true
    })
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
    let expected_artifacts = [
        "rust-native-live-market-data-smoke.json",
        "rust-native-live-account-read-smoke.json",
    ];
    let source_control_write_guard = generated_evidence_write_guard(&evidence_artifact_paths(
        &evidence_dir,
        &expected_artifacts,
    ))?;
    let commit = current_git_commit();
    let source_tree_clean = current_source_tree_clean();
    let missing: Vec<&str> = [
        (!api_key_present).then_some("BINANCE_API_KEY"),
        (!api_secret_present).then_some("BINANCE_API_SECRET"),
        (!confirmed).then_some("TRADING_BOT_RUST_LIVE_SMOKE=1"),
        (!source_tree_clean).then_some("clean source tree"),
    ]
    .into_iter()
    .flatten()
    .collect();
    let ok = missing.is_empty() && source_control_write_guard.ok;
    let report = json!({
        "ok": ok,
        "mode": "native_live_smoke_preflight",
        "network_access_attempted": false,
        "order_submission_attempted": false,
        "read_only": true,
        "runtime_ready_claimed": false,
        "commit": commit,
        "python_source_contract_hash": python_source_contract_hash(),
        "native_source_sync": native_source_sync_binding(),
        "source_tree_clean": source_tree_clean,
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
        "expected_artifacts": expected_artifacts,
        "source_control_write_guard": source_control_write_guard.as_json(),
        "operator_command": "TRADING_BOT_RUST_LIVE_SMOKE=1 BINANCE_API_KEY=... BINANCE_API_SECRET=... BINANCE_TESTNET=true cargo run -p trading-bot-rust -- --native-live-smoke"
    });
    println!("{}", serde_json::to_string_pretty(&report)?);
    if ok {
        Ok(())
    } else {
        Err("live smoke prerequisites or evidence write guard are incomplete; no network request was attempted".into())
    }
}

fn run_native_live_market_smoke_preflight() -> Result<(), Box<dyn std::error::Error>> {
    let confirmed = env_truthy("TRADING_BOT_RUST_MARKET_SMOKE").unwrap_or(false);
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    let expected_artifacts = ["rust-native-live-market-data-smoke.json"];
    let source_control_write_guard = generated_evidence_write_guard(&evidence_artifact_paths(
        &evidence_dir,
        &expected_artifacts,
    ))?;
    let commit = current_git_commit();
    let source_tree_clean = current_source_tree_clean();
    let missing: Vec<&str> = [
        (!confirmed).then_some("TRADING_BOT_RUST_MARKET_SMOKE=1"),
        (!source_tree_clean).then_some("clean source tree"),
    ]
    .into_iter()
    .flatten()
    .collect();
    let ok = missing.is_empty() && source_control_write_guard.ok;
    let report = json!({
        "ok": ok,
        "mode": "native_live_market_smoke_preflight",
        "network_access_attempted": false,
        "order_submission_attempted": false,
        "read_only": true,
        "runtime_ready_claimed": false,
        "commit": commit,
        "python_source_contract_hash": python_source_contract_hash(),
        "native_source_sync": native_source_sync_binding(),
        "source_tree_clean": source_tree_clean,
        "secrets_redacted": true,
        "prerequisites": {
            "market_smoke_confirmation_present": confirmed,
            "binance_testnet": testnet,
            "symbol": symbol,
            "interval": interval,
        },
        "missing": missing,
        "evidence_dir": evidence_dir.display().to_string(),
        "expected_artifacts": expected_artifacts,
        "source_control_write_guard": source_control_write_guard.as_json(),
        "operator_command": "TRADING_BOT_RUST_MARKET_SMOKE=1 BINANCE_TESTNET=true cargo run -p trading-bot-rust -- --native-live-market-smoke"
    });
    println!("{}", serde_json::to_string_pretty(&report)?);
    if ok {
        Ok(())
    } else {
        Err("market-data smoke prerequisite or evidence write guard is incomplete; no network request was attempted".into())
    }
}

fn run_native_live_market_smoke() -> Result<(), Box<dyn std::error::Error>> {
    require_market_smoke_confirmation()?;
    require_clean_source_tree_for_promotion()?;
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    require_generated_evidence_write_allowed(&evidence_artifact_paths(
        &evidence_dir,
        &["rust-native-live-market-data-smoke.json"],
    ))?;
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

    let evidence = collect_market_smoke_evidence_with_retry(
        &market_client,
        testnet,
        &symbol,
        &interval,
        MARKET_SMOKE_MAX_ATTEMPTS,
        MARKET_SMOKE_RETRY_DELAY,
    )?;
    write_market_smoke_evidence(evidence)?;
    println!(
        "Rust native live market-data smoke completed; signed account and standalone trading evidence remain gated."
    );
    Ok(())
}

fn run_native_live_smoke() -> Result<(), Box<dyn std::error::Error>> {
    require_live_smoke_confirmation()?;
    require_clean_source_tree_for_promotion()?;
    let api_key = env_required("BINANCE_API_KEY")?;
    let api_secret = env_required("BINANCE_API_SECRET")?;
    let credentials = BinanceApiCredentials::new(api_key, api_secret);
    let testnet = env_truthy("BINANCE_TESTNET").unwrap_or(true);
    let symbol =
        std::env::var("BINANCE_LIVE_SMOKE_SYMBOL").unwrap_or_else(|_| "BTCUSDT".to_owned());
    let interval = std::env::var("BINANCE_LIVE_SMOKE_INTERVAL").unwrap_or_else(|_| "1m".to_owned());
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    require_generated_evidence_write_allowed(&evidence_artifact_paths(
        &evidence_dir,
        &[
            "rust-native-live-market-data-smoke.json",
            "rust-native-live-account-read-smoke.json",
        ],
    ))?;

    let market_client = BinanceRestMarketDataClient::new(BinanceMarket::Futures, testnet)?;
    let account_client = BinanceSignedRestClient::new(BinanceMarket::Futures, testnet)?;

    println!(
        "Rust native live smoke: futures {} endpoint, symbol={}, interval={}",
        if testnet { "testnet" } else { "production" },
        symbol,
        interval
    );
    println!("This smoke is read-only; it does not submit, modify, or cancel orders.");

    let market_evidence = collect_market_smoke_evidence_with_retry(
        &market_client,
        testnet,
        &symbol,
        &interval,
        MARKET_SMOKE_MAX_ATTEMPTS,
        MARKET_SMOKE_RETRY_DELAY,
    )?;

    let account_evidence = collect_account_smoke_evidence_with_retry(
        &account_client,
        &credentials,
        ACCOUNT_SMOKE_MAX_ATTEMPTS,
        ACCOUNT_SMOKE_RETRY_DELAY,
    )?;
    write_live_smoke_evidence(LiveSmokeEvidence {
        market: market_evidence,
        account_base_url: account_evidence.account_base_url,
        account_endpoints: account_evidence.account_endpoints,
        position_mode: account_evidence.position_mode,
        dual_side_position: account_evidence.dual_side_position,
        multi_assets_margin: account_evidence.multi_assets_margin,
        balance_asset: account_evidence.balance_asset,
        positions_count: account_evidence.positions_count,
    })?;
    println!(
        "Rust native live smoke completed; standalone native trading execution remains disabled."
    );
    Ok(())
}

#[derive(Debug)]
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

#[derive(Debug)]
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

#[derive(Debug)]
struct AccountSmokeEvidence {
    account_base_url: String,
    account_endpoints: Vec<(&'static str, String)>,
    position_mode: String,
    dual_side_position: bool,
    multi_assets_margin: bool,
    balance_asset: String,
    positions_count: usize,
}

trait MarketSmokeClient {
    fn base_url(&self) -> &str;
    fn exchange_info_url(&self) -> String;
    fn klines_url(&self) -> String;
    fn ticker_price_url(&self) -> String;
    fn fetch_usdt_symbols(
        &self,
        sort_by_volume: bool,
        top_n: Option<usize>,
    ) -> Result<Vec<String>, Box<dyn std::error::Error>>;
    fn fetch_klines(
        &self,
        symbol: &str,
        interval: &str,
        limit: usize,
    ) -> Result<Vec<BinanceKlineCandle>, Box<dyn std::error::Error>>;
    fn fetch_ticker_price(
        &self,
        symbol: &str,
    ) -> Result<BinanceTickerPrice, Box<dyn std::error::Error>>;
}

impl MarketSmokeClient for BinanceRestMarketDataClient {
    fn base_url(&self) -> &str {
        self.base_url()
    }

    fn exchange_info_url(&self) -> String {
        self.exchange_info_url()
    }

    fn klines_url(&self) -> String {
        self.klines_url()
    }

    fn ticker_price_url(&self) -> String {
        self.ticker_price_url()
    }

    fn fetch_usdt_symbols(
        &self,
        sort_by_volume: bool,
        top_n: Option<usize>,
    ) -> Result<Vec<String>, Box<dyn std::error::Error>> {
        Ok(self.fetch_usdt_symbols(sort_by_volume, top_n)?)
    }

    fn fetch_klines(
        &self,
        symbol: &str,
        interval: &str,
        limit: usize,
    ) -> Result<Vec<BinanceKlineCandle>, Box<dyn std::error::Error>> {
        Ok(self.fetch_klines(symbol, interval, limit)?)
    }

    fn fetch_ticker_price(
        &self,
        symbol: &str,
    ) -> Result<BinanceTickerPrice, Box<dyn std::error::Error>> {
        Ok(self.fetch_ticker_price(symbol)?)
    }
}

fn collect_market_smoke_evidence_with_retry<C: MarketSmokeClient + ?Sized>(
    market_client: &C,
    testnet: bool,
    symbol: &str,
    interval: &str,
    max_attempts: usize,
    retry_delay: Duration,
) -> Result<MarketSmokeEvidence, Box<dyn std::error::Error>> {
    let max_attempts = max_attempts.max(1);
    let mut last_error = String::new();
    for attempt in 1..=max_attempts {
        match collect_market_smoke_evidence(market_client, testnet, symbol, interval) {
            Ok(evidence) => {
                if attempt > 1 {
                    println!("market-data smoke recovered on attempt {attempt}/{max_attempts}");
                }
                return Ok(evidence);
            }
            Err(error) => {
                last_error = format_error_chain(error.as_ref());
                if attempt == max_attempts {
                    break;
                }
                eprintln!(
                    "market-data smoke attempt {attempt}/{max_attempts} failed: {last_error}; retrying"
                );
                if !retry_delay.is_zero() {
                    std::thread::sleep(retry_delay);
                }
            }
        }
    }
    Err(format!("market-data smoke failed after {max_attempts} attempt(s): {last_error}").into())
}

fn collect_market_smoke_evidence<C: MarketSmokeClient + ?Sized>(
    market_client: &C,
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

trait AccountSmokeClient {
    fn base_url(&self) -> &str;
    fn futures_position_mode_url(&self) -> String;
    fn futures_multi_assets_margin_url(&self) -> String;
    fn futures_balance_url(&self) -> String;
    fn futures_position_risk_url(&self) -> String;
    fn fetch_futures_position_mode(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceFuturesPositionMode, Box<dyn std::error::Error>>;
    fn fetch_futures_multi_assets_mode(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceFuturesMultiAssetsMode, Box<dyn std::error::Error>>;
    fn fetch_usdt_balance(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceAccountSnapshot, Box<dyn std::error::Error>>;
    fn fetch_open_futures_positions(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<Vec<BinanceFuturesPosition>, Box<dyn std::error::Error>>;
}

impl AccountSmokeClient for BinanceSignedRestClient {
    fn base_url(&self) -> &str {
        self.base_url()
    }

    fn futures_position_mode_url(&self) -> String {
        self.futures_position_mode_url()
    }

    fn futures_multi_assets_margin_url(&self) -> String {
        self.futures_multi_assets_margin_url()
    }

    fn futures_balance_url(&self) -> String {
        self.futures_balance_url()
    }

    fn futures_position_risk_url(&self) -> String {
        self.futures_position_risk_url()
    }

    fn fetch_futures_position_mode(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceFuturesPositionMode, Box<dyn std::error::Error>> {
        Ok(self.fetch_futures_position_mode(credentials)?)
    }

    fn fetch_futures_multi_assets_mode(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceFuturesMultiAssetsMode, Box<dyn std::error::Error>> {
        Ok(self.fetch_futures_multi_assets_mode(credentials)?)
    }

    fn fetch_usdt_balance(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceAccountSnapshot, Box<dyn std::error::Error>> {
        Ok(self.fetch_usdt_balance(credentials)?)
    }

    fn fetch_open_futures_positions(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<Vec<BinanceFuturesPosition>, Box<dyn std::error::Error>> {
        Ok(self.fetch_open_futures_positions(credentials)?)
    }
}

fn collect_account_smoke_evidence_with_retry<C: AccountSmokeClient + ?Sized>(
    account_client: &C,
    credentials: &BinanceApiCredentials,
    max_attempts: usize,
    retry_delay: Duration,
) -> Result<AccountSmokeEvidence, Box<dyn std::error::Error>> {
    let max_attempts = max_attempts.max(1);
    let mut last_error = String::new();
    for attempt in 1..=max_attempts {
        match collect_account_smoke_evidence(account_client, credentials) {
            Ok(evidence) => {
                if attempt > 1 {
                    println!("signed account smoke recovered on attempt {attempt}/{max_attempts}");
                }
                return Ok(evidence);
            }
            Err(error) => {
                last_error = format_error_chain(error.as_ref());
                if attempt == max_attempts {
                    break;
                }
                eprintln!(
                    "signed account smoke attempt {attempt}/{max_attempts} failed: {last_error}; retrying"
                );
                if !retry_delay.is_zero() {
                    std::thread::sleep(retry_delay);
                }
            }
        }
    }
    Err(format!("signed account smoke failed after {max_attempts} attempt(s): {last_error}").into())
}

fn collect_account_smoke_evidence<C: AccountSmokeClient + ?Sized>(
    account_client: &C,
    credentials: &BinanceApiCredentials,
) -> Result<AccountSmokeEvidence, Box<dyn std::error::Error>> {
    let position_mode = account_client.fetch_futures_position_mode(credentials)?;
    println!(
        "position mode fetched: {} dual_side={}",
        position_mode.position_mode, position_mode.dual_side_position
    );
    let multi_assets_mode = account_client.fetch_futures_multi_assets_mode(credentials)?;
    println!(
        "multi-assets mode fetched: {}",
        multi_assets_mode.multi_assets_margin
    );
    let balance = account_client.fetch_usdt_balance(credentials)?;
    println!(
        "USDT balance fetched: asset={} totals redacted from smoke output",
        balance.asset
    );
    let positions = account_client.fetch_open_futures_positions(credentials)?;
    println!("open futures positions fetched: {}", positions.len());
    Ok(AccountSmokeEvidence {
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
    })
}

fn write_market_smoke_evidence(
    evidence: MarketSmokeEvidence,
) -> Result<(), Box<dyn std::error::Error>> {
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    let destinations =
        evidence_artifact_paths(&evidence_dir, &["rust-native-live-market-data-smoke.json"]);
    require_generated_evidence_write_allowed(&destinations)?;
    fs::create_dir_all(&evidence_dir)?;
    let payload = build_market_smoke_payload(
        &evidence,
        current_unix_timestamp_label(),
        current_git_commit(),
        current_source_tree_clean(),
        std::env::args().collect::<Vec<_>>().join(" "),
    );
    write_json_file(&destinations[0], &payload)?;
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
        "python_source_contract_hash": python_source_contract_hash(),
        "native_source_sync": native_source_sync_binding(),
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
    let destinations = evidence_artifact_paths(
        &evidence_dir,
        &[
            "rust-native-live-market-data-smoke.json",
            "rust-native-live-account-read-smoke.json",
        ],
    );
    require_generated_evidence_write_allowed(&destinations)?;
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
        "python_source_contract_hash": python_source_contract_hash(),
        "native_source_sync": native_source_sync_binding(),
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

    write_json_file(&destinations[0], &market_payload)?;
    write_json_file(&destinations[1], &account_payload)?;
    println!(
        "Rust native live smoke evidence written to {}",
        evidence_dir.display()
    );
    Ok(())
}

fn run_local_recovery_evidence() -> Result<(), Box<dyn std::error::Error>> {
    let evidence_dir = rust_native_runtime_evidence_dir()?;
    let destinations = evidence_artifact_paths(
        &evidence_dir,
        &[
            "rust-native-live-stream-recovery.json",
            "rust-native-order-guard-recovery.json",
        ],
    );
    require_generated_evidence_write_allowed(&destinations)?;

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
        "python_source_contract_hash": python_source_contract_hash(),
        "native_source_sync": native_source_sync_binding(),
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
        "python_source_contract_hash": python_source_contract_hash(),
        "native_source_sync": native_source_sync_binding(),
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

    write_json_file(&destinations[0], &stream_payload)?;
    write_json_file(&destinations[1], &order_payload)?;
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

struct GeneratedEvidenceWriteGuard {
    ok: bool,
    generated_evidence_write_targets: Vec<String>,
    non_generated_in_repo_write_targets: Vec<String>,
    tracked_generated_evidence_write_targets: Vec<String>,
    issues: Vec<String>,
}

impl GeneratedEvidenceWriteGuard {
    fn as_json(&self) -> Value {
        json!({
            "ok": self.ok,
            "generated_evidence_write_targets": self.generated_evidence_write_targets,
            "non_generated_in_repo_write_targets": self.non_generated_in_repo_write_targets,
            "tracked_generated_evidence_write_targets": self.tracked_generated_evidence_write_targets,
            "issues": self.issues
        })
    }
}

fn evidence_artifact_paths(evidence_dir: &Path, filenames: &[&str]) -> Vec<PathBuf> {
    filenames
        .iter()
        .map(|filename| evidence_dir.join(filename))
        .collect()
}

fn require_generated_evidence_write_allowed(
    paths: &[PathBuf],
) -> Result<GeneratedEvidenceWriteGuard, Box<dyn std::error::Error>> {
    let guard = generated_evidence_write_guard(paths)?;
    if guard.ok {
        Ok(guard)
    } else {
        Err(guard.issues.join("; ").into())
    }
}

fn generated_evidence_write_guard(
    paths: &[PathBuf],
) -> Result<GeneratedEvidenceWriteGuard, Box<dyn std::error::Error>> {
    let root = repo_root();
    let mut generated_targets = Vec::new();
    let mut non_generated_in_repo_targets = Vec::new();
    for path in paths {
        if let Some(relative) = repo_relative_path(path, &root) {
            if is_generated_evidence_path(&relative) {
                generated_targets.push(relative);
            } else {
                non_generated_in_repo_targets.push(relative);
            }
        }
    }
    let tracked_targets = tracked_git_files(&generated_targets, &root)?;
    let mut issues = Vec::new();
    if !non_generated_in_repo_targets.is_empty() {
        issues.push(format!(
            "refusing to write generated evidence artifact outside generated evidence directories inside the repository: {}. Use artifacts/rust-native-runtime-evidence, artifacts/native-source-sync, release-platform-evidence, or an absolute path outside the repository.",
            non_generated_in_repo_targets.join(", ")
        ));
    }
    if !tracked_targets.is_empty() {
        issues.push(format!(
            "refusing to write generated evidence artifact over tracked source path(s): {}. Commit the removal of generated evidence artifacts first, then regenerate/import evidence from a clean candidate source commit.",
            tracked_targets.join(", ")
        ));
    }
    Ok(GeneratedEvidenceWriteGuard {
        ok: issues.is_empty(),
        generated_evidence_write_targets: generated_targets,
        non_generated_in_repo_write_targets: non_generated_in_repo_targets,
        tracked_generated_evidence_write_targets: tracked_targets,
        issues,
    })
}

fn repo_relative_path(path: &Path, root: &Path) -> Option<String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().ok()?.join(path)
    };
    let relative = absolute.strip_prefix(root).ok()?;
    Some(relative.to_string_lossy().replace('\\', "/"))
}

fn is_generated_evidence_path(path: &str) -> bool {
    (path.starts_with("artifacts/rust-native-runtime-evidence/")
        && (path.ends_with(".json")
            || path.ends_with(".zip")
            || path
                == "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md"
            || path.starts_with("artifacts/rust-native-runtime-evidence/downloads/")))
        || path == "artifacts/rust-native-runtime-evidence-plan.md"
        || (path.starts_with("artifacts/native-source-sync/") && path.ends_with(".json"))
        || (path.starts_with("release-platform-evidence/") && path.ends_with(".json"))
}

fn tracked_git_files(
    relative_paths: &[String],
    root: &Path,
) -> Result<Vec<String>, Box<dyn std::error::Error>> {
    if relative_paths.is_empty() {
        return Ok(Vec::new());
    }
    let output = Command::new("git")
        .arg("ls-files")
        .arg("--")
        .args(relative_paths)
        .current_dir(root)
        .output()?;
    if !output.status.success() {
        return Err("could not check generated evidence source-control state".into());
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(|line| line.trim().replace('\\', "/"))
        .filter(|line| !line.is_empty())
        .collect())
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

fn source_tree_status_command(untracked_files: &str) -> Vec<String> {
    let mut args = vec![
        "status".to_owned(),
        "--porcelain".to_owned(),
        format!("--untracked-files={untracked_files}"),
        "--".to_owned(),
        ".".to_owned(),
    ];
    args.extend(
        PROMOTION_SOURCE_TREE_IGNORED_PATHS
            .iter()
            .map(|path| format!(":(exclude){path}")),
    );
    args
}

fn source_tree_status_clean(untracked_files: &str) -> bool {
    let args = source_tree_status_command(untracked_files);
    let output = Command::new("git")
        .args(&args)
        .current_dir(repo_root())
        .output();
    if let Ok(output) = output {
        return output.status.success()
            && String::from_utf8_lossy(&output.stdout).trim().is_empty();
    }
    false
}

fn current_source_tree_clean() -> bool {
    source_tree_status_clean("no") && source_tree_status_clean("all")
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

fn require_clean_source_tree_for_promotion() -> Result<(), Box<dyn std::error::Error>> {
    if current_source_tree_clean() {
        return Ok(());
    }
    Err(
        "source tree must be clean before collecting Rust native promotion evidence; commit or remove source changes first"
            .into(),
    )
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    struct FakeMarketSmokeClient {
        symbol_failures_remaining: Cell<usize>,
        symbol_attempts: Cell<usize>,
    }

    struct FakeAccountSmokeClient {
        mode_failures_remaining: Cell<usize>,
        mode_attempts: Cell<usize>,
    }

    impl FakeMarketSmokeClient {
        fn new(symbol_failures: usize) -> Self {
            Self {
                symbol_failures_remaining: Cell::new(symbol_failures),
                symbol_attempts: Cell::new(0),
            }
        }
    }

    impl FakeAccountSmokeClient {
        fn new(mode_failures: usize) -> Self {
            Self {
                mode_failures_remaining: Cell::new(mode_failures),
                mode_attempts: Cell::new(0),
            }
        }
    }

    impl MarketSmokeClient for FakeMarketSmokeClient {
        fn base_url(&self) -> &str {
            "https://example.test"
        }

        fn exchange_info_url(&self) -> String {
            "https://example.test/fapi/v1/exchangeInfo".to_owned()
        }

        fn klines_url(&self) -> String {
            "https://example.test/fapi/v1/klines".to_owned()
        }

        fn ticker_price_url(&self) -> String {
            "https://example.test/fapi/v1/ticker/price".to_owned()
        }

        fn fetch_usdt_symbols(
            &self,
            _sort_by_volume: bool,
            _top_n: Option<usize>,
        ) -> Result<Vec<String>, Box<dyn std::error::Error>> {
            self.symbol_attempts.set(self.symbol_attempts.get() + 1);
            let failures_remaining = self.symbol_failures_remaining.get();
            if failures_remaining > 0 {
                self.symbol_failures_remaining
                    .set(failures_remaining.saturating_sub(1));
                return Err("transient exchangeInfo reset".into());
            }
            Ok(vec!["BTCUSDT".to_owned(), "ETHUSDT".to_owned()])
        }

        fn fetch_klines(
            &self,
            _symbol: &str,
            _interval: &str,
            _limit: usize,
        ) -> Result<Vec<BinanceKlineCandle>, Box<dyn std::error::Error>> {
            Ok(vec![BinanceKlineCandle {
                open_time_ms: 1,
                open: 1.0,
                high: 2.0,
                low: 0.5,
                close: 1.5,
                volume: 10.0,
            }])
        }

        fn fetch_ticker_price(
            &self,
            symbol: &str,
        ) -> Result<BinanceTickerPrice, Box<dyn std::error::Error>> {
            Ok(BinanceTickerPrice {
                symbol: symbol.to_owned(),
                price: 1.5,
            })
        }
    }

    impl AccountSmokeClient for FakeAccountSmokeClient {
        fn base_url(&self) -> &str {
            "https://signed.example.test"
        }

        fn futures_position_mode_url(&self) -> String {
            "https://signed.example.test/fapi/v1/positionSide/dual".to_owned()
        }

        fn futures_multi_assets_margin_url(&self) -> String {
            "https://signed.example.test/fapi/v1/multiAssetsMargin".to_owned()
        }

        fn futures_balance_url(&self) -> String {
            "https://signed.example.test/fapi/v2/balance".to_owned()
        }

        fn futures_position_risk_url(&self) -> String {
            "https://signed.example.test/fapi/v2/positionRisk".to_owned()
        }

        fn fetch_futures_position_mode(
            &self,
            _credentials: &BinanceApiCredentials,
        ) -> Result<BinanceFuturesPositionMode, Box<dyn std::error::Error>> {
            self.mode_attempts.set(self.mode_attempts.get() + 1);
            let failures_remaining = self.mode_failures_remaining.get();
            if failures_remaining > 0 {
                self.mode_failures_remaining
                    .set(failures_remaining.saturating_sub(1));
                return Err("transient signed account reset".into());
            }
            Ok(BinanceFuturesPositionMode {
                dual_side_position: true,
                position_mode: "Hedge".to_owned(),
            })
        }

        fn fetch_futures_multi_assets_mode(
            &self,
            _credentials: &BinanceApiCredentials,
        ) -> Result<BinanceFuturesMultiAssetsMode, Box<dyn std::error::Error>> {
            Ok(BinanceFuturesMultiAssetsMode {
                multi_assets_margin: false,
            })
        }

        fn fetch_usdt_balance(
            &self,
            _credentials: &BinanceApiCredentials,
        ) -> Result<BinanceAccountSnapshot, Box<dyn std::error::Error>> {
            Ok(BinanceAccountSnapshot {
                asset: "USDT".to_owned(),
                usdt_balance: 100.0,
                total_usdt_balance: 100.0,
                available_usdt_balance: 80.0,
            })
        }

        fn fetch_open_futures_positions(
            &self,
            _credentials: &BinanceApiCredentials,
        ) -> Result<Vec<BinanceFuturesPosition>, Box<dyn std::error::Error>> {
            Ok(vec![BinanceFuturesPosition {
                symbol: "BTCUSDT".to_owned(),
                position_side: "LONG".to_owned(),
                position_amt: 0.01,
                ..Default::default()
            }])
        }
    }

    #[test]
    fn market_smoke_retry_recovers_after_transient_exchange_info_failure() {
        let client = FakeMarketSmokeClient::new(1);

        let evidence = collect_market_smoke_evidence_with_retry(
            &client,
            true,
            "BTCUSDT",
            "1m",
            2,
            Duration::ZERO,
        )
        .expect("market smoke should recover on second attempt");

        assert_eq!(2, client.symbol_attempts.get());
        assert_eq!(2, evidence.symbols_count);
        assert_eq!(1, evidence.candles_count);
        assert_eq!("BTCUSDT", evidence.ticker_symbol);
    }

    #[test]
    fn market_smoke_retry_reports_final_failure_after_attempts() {
        let client = FakeMarketSmokeClient::new(3);

        let error = collect_market_smoke_evidence_with_retry(
            &client,
            true,
            "BTCUSDT",
            "1m",
            2,
            Duration::ZERO,
        )
        .expect_err("market smoke should fail after bounded attempts");
        let message = format_error_chain(error.as_ref());

        assert_eq!(2, client.symbol_attempts.get());
        assert!(message.contains("market-data smoke failed after 2 attempt(s)"));
        assert!(message.contains("transient exchangeInfo reset"));
    }

    #[test]
    fn signed_account_smoke_retry_recovers_after_transient_read_failure() {
        let client = FakeAccountSmokeClient::new(1);
        let credentials = BinanceApiCredentials::new("key", "secret");

        let evidence =
            collect_account_smoke_evidence_with_retry(&client, &credentials, 2, Duration::ZERO)
                .expect("signed account smoke should recover on second attempt");

        assert_eq!(2, client.mode_attempts.get());
        assert_eq!("Hedge", evidence.position_mode);
        assert!(evidence.dual_side_position);
        assert_eq!("USDT", evidence.balance_asset);
        assert_eq!(1, evidence.positions_count);
    }

    #[test]
    fn signed_account_smoke_retry_reports_final_failure_after_attempts() {
        let client = FakeAccountSmokeClient::new(3);
        let credentials = BinanceApiCredentials::new("key", "secret");

        let error =
            collect_account_smoke_evidence_with_retry(&client, &credentials, 2, Duration::ZERO)
                .expect_err("signed account smoke should fail after bounded attempts");
        let message = format_error_chain(error.as_ref());

        assert_eq!(2, client.mode_attempts.get());
        assert!(message.contains("signed account smoke failed after 2 attempt(s)"));
        assert!(message.contains("transient signed account reset"));
    }

    #[test]
    fn source_tree_clean_status_commands_match_promotion_exclusions() {
        let tracked_args = source_tree_status_command("no");
        let untracked_args = source_tree_status_command("all");

        assert_eq!(
            &tracked_args[..5],
            &[
                "status".to_owned(),
                "--porcelain".to_owned(),
                "--untracked-files=no".to_owned(),
                "--".to_owned(),
                ".".to_owned(),
            ]
        );
        assert_eq!(
            &untracked_args[..5],
            &[
                "status".to_owned(),
                "--porcelain".to_owned(),
                "--untracked-files=all".to_owned(),
                "--".to_owned(),
                ".".to_owned(),
            ]
        );
        for args in [&tracked_args, &untracked_args] {
            assert!(args.contains(&":(exclude)artifacts/rust-native-runtime-evidence".to_owned()));
            assert!(args.contains(&":(exclude)artifacts/native-source-sync".to_owned()));
            assert!(args.contains(&":(exclude)release-platform-evidence".to_owned()));
        }
    }

    #[test]
    fn generated_evidence_path_classifier_covers_runtime_plan_artifacts() {
        for path in [
            "artifacts/rust-native-runtime-evidence/rust-native-live-account-read-smoke.json",
            "artifacts/rust-native-runtime-evidence/live-smoke.zip",
            "artifacts/rust-native-runtime-evidence/downloads/artifact.json",
            "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md",
            "artifacts/rust-native-runtime-evidence-plan.md",
            "artifacts/native-source-sync/native-source-sync-audit.json",
            "release-platform-evidence/browser-chrome-windows_11_x64.json",
        ] {
            assert!(
                is_generated_evidence_path(path),
                "{path} should be generated evidence"
            );
        }

        for path in [
            "docs/rust-native-runtime-evidence.json",
            "artifacts/rust-native-runtime-evidence/readme.md",
            "artifacts/native-source-sync/readme.md",
            "release-platform-evidence/readme.md",
        ] {
            assert!(
                !is_generated_evidence_path(path),
                "{path} should remain source-controlled or non-evidence"
            );
        }
    }

    #[test]
    fn generated_evidence_write_guard_rejects_in_repo_nongenerated_destinations() {
        let destination = repo_root()
            .join("docs")
            .join("rust-native-live-account-read-smoke.json");
        let guard = generated_evidence_write_guard(&[destination]).expect("guard should run");

        assert!(!guard.ok);
        assert_eq!(
            guard.non_generated_in_repo_write_targets,
            vec!["docs/rust-native-live-account-read-smoke.json".to_owned()]
        );
        assert!(
            guard.issues.iter().any(|issue| issue
                .contains("outside generated evidence directories inside the repository")),
            "guard should explain noncanonical in-repo destinations"
        );
    }
}
