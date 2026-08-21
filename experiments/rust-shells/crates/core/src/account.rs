use std::collections::HashMap;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow, bail};
use reqwest::blocking::Client;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::market_data::BinanceMarket;
use crate::tls::build_http_client;

const DEFAULT_RECV_WINDOW_MS: u64 = 10_000;
const POSITION_EPSILON: f64 = 1e-10;
const PREFERRED_FUTURES_COLLATERAL_ASSETS: [&str; 3] = ["USDT", "BUSD", "USD"];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinanceApiCredentials {
    pub api_key: String,
    pub api_secret: String,
}

impl BinanceApiCredentials {
    pub fn new(api_key: impl Into<String>, api_secret: impl Into<String>) -> Self {
        Self {
            api_key: api_key.into(),
            api_secret: api_secret.into(),
        }
    }

    fn validate(&self) -> Result<()> {
        if self.api_key.trim().is_empty() || self.api_secret.trim().is_empty() {
            bail!("Missing API credentials");
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceAccountSnapshot {
    pub asset: String,
    /// Canonical total balance in `asset`; this is the source for all markets.
    pub total_balance: f64,
    /// Canonical available balance in `asset`; this is the source for all markets.
    pub available_balance: f64,
    /// Legacy USD-M/Spot field retained for callers that still use the old name.
    pub usdt_balance: f64,
    /// Legacy USD-M/Spot field retained for callers that still use the old name.
    pub total_usdt_balance: f64,
    /// Legacy USD-M/Spot field retained for callers that still use the old name.
    pub available_usdt_balance: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceBalanceRow {
    pub asset: String,
    pub free: f64,
    pub locked: f64,
    pub total: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesPosition {
    pub symbol: String,
    pub position_side: String,
    pub position_amt: f64,
    pub notional: f64,
    pub initial_margin: f64,
    pub position_initial_margin: f64,
    pub open_order_margin: f64,
    pub isolated_wallet: f64,
    pub isolated_margin: f64,
    pub maint_margin: f64,
    pub maint_margin_rate: f64,
    pub margin_balance: f64,
    pub wallet_balance: f64,
    pub margin_ratio: f64,
    pub margin_ratio_calc: f64,
    pub leverage: f64,
    pub unrealized_profit: f64,
    pub entry_price: f64,
    pub mark_price: f64,
    pub liquidation_price: f64,
    pub margin_type: String,
    pub update_time_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinanceFuturesPositionMode {
    pub dual_side_position: bool,
    pub position_mode: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinanceFuturesMarginMode {
    pub symbol: String,
    pub margin_type: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinanceFuturesSymbolSettings {
    pub symbol: String,
    pub margin_type: Option<String>,
    pub leverage: Option<i64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesAccountReadSnapshot {
    pub positions: Vec<BinanceFuturesPosition>,
    pub symbol_settings: Option<BinanceFuturesSymbolSettings>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesLeverageChange {
    pub symbol: String,
    pub leverage: i64,
    pub max_notional_value: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinanceFuturesMultiAssetsMode {
    pub multi_assets_margin: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesPositionMarginChange {
    pub symbol: String,
    pub position_side: String,
    pub amount: f64,
    pub margin_type: i64,
}

impl Default for BinanceFuturesPosition {
    fn default() -> Self {
        Self {
            symbol: String::new(),
            position_side: "BOTH".to_owned(),
            position_amt: 0.0,
            notional: 0.0,
            initial_margin: 0.0,
            position_initial_margin: 0.0,
            open_order_margin: 0.0,
            isolated_wallet: 0.0,
            isolated_margin: 0.0,
            maint_margin: 0.0,
            maint_margin_rate: 0.0,
            margin_balance: 0.0,
            wallet_balance: 0.0,
            margin_ratio: 0.0,
            margin_ratio_calc: 0.0,
            leverage: 0.0,
            unrealized_profit: 0.0,
            entry_price: 0.0,
            mark_price: 0.0,
            liquidation_price: 0.0,
            margin_type: String::new(),
            update_time_ms: 0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct BinanceSignedRestClient {
    http: Client,
    market: BinanceMarket,
    base_url: String,
    recv_window_ms: u64,
    testnet: bool,
}

impl BinanceSignedRestClient {
    pub fn new(market: BinanceMarket, testnet: bool) -> Result<Self> {
        let mut client = Self::with_base_url(market, market.default_base_url(testnet))?;
        client.testnet = testnet;
        Ok(client)
    }

    pub fn with_base_url(market: BinanceMarket, base_url: impl Into<String>) -> Result<Self> {
        let http = build_http_client(Duration::from_secs(10), "trading-bot-rust/0.1")
            .context("build Binance signed REST HTTP client")?;
        Self::with_http_client(market, base_url, http)
    }

    pub fn with_http_client(
        market: BinanceMarket,
        base_url: impl Into<String>,
        http: Client,
    ) -> Result<Self> {
        let base_url = normalize_base_url(base_url.into())?;
        Ok(Self {
            http,
            market,
            base_url,
            recv_window_ms: DEFAULT_RECV_WINDOW_MS,
            testnet: false,
        })
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub fn recv_window_ms(&self) -> u64 {
        self.recv_window_ms
    }

    pub fn with_recv_window_ms(mut self, recv_window_ms: u64) -> Self {
        self.recv_window_ms = recv_window_ms;
        self
    }

    pub(crate) fn alternate_futures_prefix_client(&self) -> Result<Self> {
        let alternate_market = match self.market {
            BinanceMarket::Futures => BinanceMarket::CoinFutures,
            BinanceMarket::CoinFutures => BinanceMarket::Futures,
            BinanceMarket::Spot => bail!("spot market has no futures prefix fallback"),
        };
        let mut client =
            Self::with_http_client(alternate_market, self.base_url.clone(), self.http.clone())?;
        client.recv_window_ms = self.recv_window_ms;
        client.testnet = self.testnet;
        Ok(client)
    }

    pub(crate) fn futures_fallback_allowed(&self) -> bool {
        if !self.market.is_futures() {
            return false;
        }
        let base_url = self.base_url.to_ascii_lowercase();
        self.testnet
            || base_url.contains("127.0.0.1")
            || base_url.contains("localhost")
            || base_url.contains("[::1]")
            || base_url.contains("testnet")
    }

    pub fn futures_balance_url(&self) -> String {
        self.futures_account_path("balance")
    }

    pub fn futures_account_url(&self) -> String {
        self.futures_account_path("account")
    }

    pub fn futures_position_risk_url(&self) -> String {
        self.futures_account_path("positionRisk")
    }

    pub fn futures_position_mode_url(&self) -> String {
        self.futures_v1_path("/positionSide/dual")
    }

    pub fn futures_margin_type_url(&self) -> String {
        self.futures_v1_path("/marginType")
    }

    pub fn futures_leverage_url(&self) -> String {
        self.futures_v1_path("/leverage")
    }

    pub fn futures_multi_assets_margin_url(&self) -> String {
        self.futures_v1_path("/multiAssetsMargin")
    }

    pub fn spot_account_url(&self) -> String {
        self.url_for_path("/api/v3/account")
    }

    pub fn fetch_usdt_balance(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceAccountSnapshot> {
        match self.market {
            BinanceMarket::Futures => self.fetch_futures_usdt_balance(credentials),
            BinanceMarket::CoinFutures => self.fetch_futures_collateral_balance(credentials),
            BinanceMarket::Spot => self.fetch_spot_usdt_balance(credentials),
        }
    }

    pub fn fetch_futures_usdt_balance(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceAccountSnapshot> {
        self.require_futures_market()?;
        let balance_payload = self.signed_get_json(
            &self.futures_balance_path(),
            credentials,
            &[],
            current_timestamp_ms()?,
        )?;
        let account_payload = self.signed_get_json(
            &self.futures_account_path("account"),
            credentials,
            &[],
            current_timestamp_ms()?,
        );
        match self.market {
            BinanceMarket::Futures => {
                parse_futures_usdt_balance(&balance_payload, account_payload.as_ref().ok())
            }
            BinanceMarket::CoinFutures => {
                parse_futures_collateral_balance(&balance_payload, account_payload.as_ref().ok())
            }
            BinanceMarket::Spot => bail!("spot market is not a futures market"),
        }
    }

    pub fn fetch_futures_collateral_balance(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceAccountSnapshot> {
        self.require_futures_market()?;
        let balance_payload = self.signed_get_json(
            &self.futures_balance_path(),
            credentials,
            &[],
            current_timestamp_ms()?,
        )?;
        let account_payload = self.signed_get_json(
            &self.futures_account_path("account"),
            credentials,
            &[],
            current_timestamp_ms()?,
        );
        parse_futures_collateral_balance(&balance_payload, account_payload.as_ref().ok())
    }

    pub fn fetch_spot_usdt_balance(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceAccountSnapshot> {
        self.require_market(BinanceMarket::Spot)?;
        let account_payload =
            self.signed_get_json("/api/v3/account", credentials, &[], current_timestamp_ms()?)?;
        parse_spot_usdt_balance(&account_payload)
    }

    pub fn fetch_spot_balance_rows(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<Vec<BinanceBalanceRow>> {
        self.require_spot_market()?;
        let account_payload =
            self.signed_get_json("/api/v3/account", credentials, &[], current_timestamp_ms()?)?;
        parse_spot_balance_rows(&account_payload)
    }

    pub fn fetch_balance_rows(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<Vec<BinanceBalanceRow>> {
        match self.market {
            BinanceMarket::Spot => self.fetch_spot_balance_rows(credentials),
            BinanceMarket::Futures | BinanceMarket::CoinFutures => {
                self.require_futures_market()?;
                let payload = self.signed_get_json(
                    &self.futures_balance_path(),
                    credentials,
                    &[],
                    current_timestamp_ms()?,
                )?;
                parse_futures_balance_rows(&payload)
            }
        }
    }

    pub fn fetch_spot_balance(
        &self,
        credentials: &BinanceApiCredentials,
        asset: impl AsRef<str>,
    ) -> Result<f64> {
        self.require_spot_market()?;
        let rows = self.fetch_spot_balance_rows(credentials)?;
        Ok(select_balance_free(&rows, asset))
    }

    pub fn list_spot_non_usdt_balances(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<Vec<BinanceBalanceRow>> {
        self.require_spot_market()?;
        let rows = self.fetch_spot_balance_rows(credentials)?;
        Ok(non_usdt_balance_rows(&rows))
    }

    pub fn fetch_open_futures_positions(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<Vec<BinanceFuturesPosition>> {
        self.require_futures_market()?;
        let (risk_payload, account_payload) = self.fetch_futures_position_payloads(credentials)?;
        parse_open_futures_positions(&risk_payload, account_payload.as_ref())
    }

    pub fn fetch_futures_account_read_snapshot(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: &str,
    ) -> Result<BinanceFuturesAccountReadSnapshot> {
        self.require_futures_market()?;
        let (risk_payload, account_payload) = self.fetch_futures_position_payloads(credentials)?;
        let account_payload_ref = account_payload.as_ref();
        let positions = parse_open_futures_positions(&risk_payload, account_payload_ref)?;
        let symbol_settings =
            parse_futures_symbol_settings(&risk_payload, account_payload_ref, symbol)?;
        Ok(BinanceFuturesAccountReadSnapshot {
            positions,
            symbol_settings,
        })
    }

    fn fetch_futures_position_payloads(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<(Value, Option<Value>)> {
        let risk_payload = self.signed_get_json(
            &self.futures_position_risk_path(),
            credentials,
            &[],
            current_timestamp_ms()?,
        )?;
        let account_payload = self
            .signed_get_json(
                &self.futures_account_path("account"),
                credentials,
                &[],
                current_timestamp_ms()?,
            )
            .ok();
        Ok((risk_payload, account_payload))
    }

    pub fn fetch_futures_position_mode(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceFuturesPositionMode> {
        self.require_futures_market()?;
        let payload = self.signed_get_json(
            &self.futures_v1_path("/positionSide/dual"),
            credentials,
            &[],
            current_timestamp_ms()?,
        )?;
        parse_futures_position_mode(&payload)
    }

    pub fn change_futures_position_mode(
        &self,
        credentials: &BinanceApiCredentials,
        hedge_mode: bool,
    ) -> Result<BinanceFuturesPositionMode> {
        self.require_futures_market()?;
        let params = build_futures_position_mode_params(hedge_mode);
        let payload = self.signed_post_json(
            &self.futures_v1_path("/positionSide/dual"),
            credentials,
            &params,
            current_timestamp_ms()?,
            self.recv_window_ms,
        )?;
        let _ = payload;
        Ok(BinanceFuturesPositionMode {
            dual_side_position: hedge_mode,
            position_mode: if hedge_mode {
                "Hedge".to_owned()
            } else {
                "One-way".to_owned()
            },
        })
    }

    pub fn change_futures_margin_type(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: &str,
        margin_type: &str,
    ) -> Result<BinanceFuturesMarginMode> {
        self.require_futures_market()?;
        let params = build_futures_margin_type_params(symbol, margin_type)?;
        let payload = self.signed_post_json(
            &self.futures_v1_path("/marginType"),
            credentials,
            &params,
            current_timestamp_ms()?,
            self.recv_window_ms,
        )?;
        if let Ok(parsed) = parse_futures_margin_mode(&payload, symbol) {
            return Ok(parsed);
        }
        Ok(BinanceFuturesMarginMode {
            symbol: normalize_required_symbol(symbol)?,
            margin_type: normalize_futures_margin_type(margin_type)?,
        })
    }

    pub fn change_futures_leverage(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: &str,
        leverage: i64,
    ) -> Result<BinanceFuturesLeverageChange> {
        self.require_futures_market()?;
        let params = build_futures_leverage_params(symbol, leverage)?;
        let payload = self.signed_post_json(
            &self.futures_v1_path("/leverage"),
            credentials,
            &params,
            current_timestamp_ms()?,
            self.recv_window_ms,
        )?;
        if let Ok(parsed) = parse_futures_leverage_change(&payload, symbol) {
            return Ok(parsed);
        }
        Ok(BinanceFuturesLeverageChange {
            symbol: normalize_required_symbol(symbol)?,
            leverage,
            max_notional_value: None,
        })
    }

    pub fn fetch_futures_multi_assets_mode(
        &self,
        credentials: &BinanceApiCredentials,
    ) -> Result<BinanceFuturesMultiAssetsMode> {
        self.require_futures_market()?;
        let payload = self.signed_get_json(
            &self.futures_v1_path("/multiAssetsMargin"),
            credentials,
            &[],
            current_timestamp_ms()?,
        )?;
        parse_futures_multi_assets_mode(&payload)
    }

    pub fn change_futures_multi_assets_mode(
        &self,
        credentials: &BinanceApiCredentials,
        enabled: bool,
    ) -> Result<BinanceFuturesMultiAssetsMode> {
        self.require_futures_market()?;
        let params = build_futures_multi_assets_mode_params(enabled);
        let payload = self.signed_post_json(
            &self.futures_v1_path("/multiAssetsMargin"),
            credentials,
            &params,
            current_timestamp_ms()?,
            self.recv_window_ms,
        )?;
        if let Ok(parsed) = parse_futures_multi_assets_mode(&payload) {
            return Ok(parsed);
        }
        Ok(BinanceFuturesMultiAssetsMode {
            multi_assets_margin: enabled,
        })
    }

    pub fn change_futures_position_margin(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: &str,
        amount: f64,
        position_side: Option<&str>,
    ) -> Result<BinanceFuturesPositionMarginChange> {
        self.require_futures_market()?;
        let params = build_futures_position_margin_params(symbol, amount, position_side)?;
        let payload = self.signed_post_json(
            &self.futures_v1_path("/positionMargin"),
            credentials,
            &params,
            current_timestamp_ms()?,
            self.recv_window_ms,
        )?;
        parse_futures_position_margin_change(&payload, symbol, amount, position_side)
    }

    fn require_market(&self, expected: BinanceMarket) -> Result<()> {
        if self.market != expected {
            bail!(
                "client was built for {:?}, expected {:?}",
                self.market,
                expected
            );
        }
        Ok(())
    }

    pub(crate) fn require_futures_market(&self) -> Result<()> {
        if !self.market.is_futures() {
            bail!(
                "client was built for {:?}, expected a futures market",
                self.market
            );
        }
        Ok(())
    }

    pub(crate) fn require_spot_market(&self) -> Result<()> {
        self.require_market(BinanceMarket::Spot)
    }

    fn futures_account_path(&self, suffix: &str) -> String {
        let version = if self.market == BinanceMarket::Futures {
            "v2"
        } else {
            "v1"
        };
        self.url_for_path(&format!(
            "{}/{}/{}",
            self.market.futures_api_prefix(),
            version,
            suffix.trim_start_matches('/')
        ))
    }

    fn futures_balance_path(&self) -> String {
        self.futures_account_path("balance")
    }

    fn futures_position_risk_path(&self) -> String {
        self.futures_account_path("positionRisk")
    }

    pub(crate) fn futures_v1_path(&self, suffix: &str) -> String {
        self.url_for_path(&format!(
            "{}/v1/{}",
            self.market.futures_api_prefix(),
            suffix.trim_start_matches('/')
        ))
    }

    pub(crate) fn url_for_path(&self, path: &str) -> String {
        format!("{}{}", self.base_url, path)
    }

    pub(crate) fn public_get_json(&self, path: &str, query: &[(&str, &str)]) -> Result<Value> {
        let url = self.url_for_path(path);
        let response = self
            .http
            .get(&url)
            .query(query)
            .send()
            .with_context(|| format!("GET Binance REST {path}"))?;
        let status = response.status();
        let payload = response
            .text()
            .with_context(|| format!("read Binance response body from {path}"))?;
        if !status.is_success() {
            bail!("Binance REST {path} returned HTTP {status}: {payload}");
        }
        let value: Value = serde_json::from_str(&payload)
            .with_context(|| format!("parse Binance JSON response from {path}"))?;
        ensure_not_binance_error(&value)?;
        Ok(value)
    }

    pub(crate) fn signed_get_json(
        &self,
        path: &str,
        credentials: &BinanceApiCredentials,
        params: &[(&str, String)],
        timestamp_ms: i64,
    ) -> Result<Value> {
        self.signed_request_json(
            "GET",
            path,
            credentials,
            params,
            timestamp_ms,
            self.recv_window_ms,
        )
    }

    pub(crate) fn signed_post_json(
        &self,
        path: &str,
        credentials: &BinanceApiCredentials,
        params: &[(&str, String)],
        timestamp_ms: i64,
        recv_window_ms: u64,
    ) -> Result<Value> {
        self.signed_request_json(
            "POST",
            path,
            credentials,
            params,
            timestamp_ms,
            recv_window_ms,
        )
    }

    pub(crate) fn signed_delete_json(
        &self,
        path: &str,
        credentials: &BinanceApiCredentials,
        params: &[(&str, String)],
        timestamp_ms: i64,
        recv_window_ms: u64,
    ) -> Result<Value> {
        self.signed_request_json(
            "DELETE",
            path,
            credentials,
            params,
            timestamp_ms,
            recv_window_ms,
        )
    }

    fn signed_request_json(
        &self,
        method: &str,
        path: &str,
        credentials: &BinanceApiCredentials,
        params: &[(&str, String)],
        timestamp_ms: i64,
        recv_window_ms: u64,
    ) -> Result<Value> {
        credentials.validate()?;
        let query = signed_query_string(
            &credentials.api_secret,
            timestamp_ms,
            recv_window_ms,
            params,
        );
        let endpoint = if path.starts_with("http://") || path.starts_with("https://") {
            path.to_owned()
        } else {
            format!("{}{}", self.base_url, path)
        };
        let url = format!("{endpoint}?{query}");
        let method = method.trim().to_uppercase();
        let request = match method.as_str() {
            "GET" => self.http.get(&url),
            "POST" => self.http.post(&url),
            "DELETE" => self.http.delete(&url),
            _ => bail!("unsupported signed Binance REST method {method}"),
        };
        let response = request
            .header("X-MBX-APIKEY", credentials.api_key.trim())
            .send()
            .with_context(|| {
                format!("{method} signed Binance REST {path} via {}", self.base_url)
            })?;
        let status = response.status();
        let payload = response
            .text()
            .with_context(|| format!("read Binance response body from {path}"))?;
        if !status.is_success() {
            bail!("Binance REST {path} returned HTTP {status}: {payload}");
        }
        let value: Value = serde_json::from_str(&payload)
            .with_context(|| format!("parse Binance JSON response from {path}"))?;
        ensure_not_binance_error(&value)?;
        Ok(value)
    }
}

pub fn hmac_sha256_hex(secret: &str, message: &str) -> String {
    const BLOCK_SIZE: usize = 64;
    let mut key = secret.as_bytes().to_vec();
    if key.len() > BLOCK_SIZE {
        key = Sha256::digest(&key).to_vec();
    }
    key.resize(BLOCK_SIZE, 0);

    let mut inner_pad = [0x36_u8; BLOCK_SIZE];
    let mut outer_pad = [0x5c_u8; BLOCK_SIZE];
    for (index, byte) in key.iter().enumerate() {
        inner_pad[index] ^= byte;
        outer_pad[index] ^= byte;
    }

    let mut inner = Sha256::new();
    inner.update(inner_pad);
    inner.update(message.as_bytes());
    let inner_hash = inner.finalize();

    let mut outer = Sha256::new();
    outer.update(outer_pad);
    outer.update(inner_hash);
    lower_hex(&outer.finalize())
}

pub fn signed_query_string(
    api_secret: &str,
    timestamp_ms: i64,
    recv_window_ms: u64,
    params: &[(&str, String)],
) -> String {
    let mut parts = Vec::new();
    for (key, value) in params {
        if !key.trim().is_empty() {
            parts.push(format!("{}={}", key.trim(), value.trim()));
        }
    }
    parts.push(format!("timestamp={timestamp_ms}"));
    if recv_window_ms > 0 {
        parts.push(format!("recvWindow={recv_window_ms}"));
    }
    let query = parts.join("&");
    let signature = hmac_sha256_hex(api_secret, &query);
    format!("{query}&signature={signature}")
}

pub fn build_futures_position_mode_params(hedge_mode: bool) -> Vec<(&'static str, String)> {
    vec![(
        "dualSidePosition",
        if hedge_mode { "true" } else { "false" }.to_owned(),
    )]
}

pub fn normalize_futures_margin_type(margin_type: &str) -> Result<String> {
    let normalized = margin_type.trim().to_uppercase().replace('-', "_");
    match normalized.as_str() {
        "ISOLATED" => Ok("ISOLATED".to_owned()),
        "CROSS" | "CROSSED" => Ok("CROSSED".to_owned()),
        _ => bail!("futures margin type must be ISOLATED or CROSSED"),
    }
}

pub fn build_futures_margin_type_params(
    symbol: &str,
    margin_type: &str,
) -> Result<Vec<(&'static str, String)>> {
    Ok(vec![
        ("symbol", normalize_required_symbol(symbol)?),
        ("marginType", normalize_futures_margin_type(margin_type)?),
    ])
}

pub fn build_futures_leverage_params(
    symbol: &str,
    leverage: i64,
) -> Result<Vec<(&'static str, String)>> {
    if !(1..=125).contains(&leverage) {
        bail!("futures leverage must be between 1 and 125");
    }
    Ok(vec![
        ("symbol", normalize_required_symbol(symbol)?),
        ("leverage", leverage.to_string()),
    ])
}

pub fn build_futures_multi_assets_mode_params(enabled: bool) -> Vec<(&'static str, String)> {
    vec![(
        "multiAssetsMargin",
        if enabled { "true" } else { "false" }.to_owned(),
    )]
}

pub fn build_futures_position_margin_params(
    symbol: &str,
    amount: f64,
    position_side: Option<&str>,
) -> Result<Vec<(&'static str, String)>> {
    if !amount.is_finite() || amount <= 0.0 {
        bail!("position-margin amount must be positive");
    }
    let mut params = vec![
        ("symbol", normalize_required_symbol(symbol)?),
        ("amount", format_position_margin_amount(amount)),
        ("type", "1".to_owned()),
    ];
    if let Some(position_side) = position_side
        .map(str::trim)
        .filter(|value| !value.is_empty() && !value.eq_ignore_ascii_case("BOTH"))
    {
        params.push(("positionSide", position_side.to_uppercase()));
    }
    Ok(params)
}

pub fn parse_futures_position_mode(payload: &Value) -> Result<BinanceFuturesPositionMode> {
    ensure_not_binance_error(payload)?;
    let value = dual_side_position_value(payload)
        .ok_or_else(|| anyhow!("futures position mode response missing dualSidePosition"))?;
    let dual_side_position = coerce_bool_flag(value);
    Ok(BinanceFuturesPositionMode {
        dual_side_position,
        position_mode: if dual_side_position {
            "Hedge".to_owned()
        } else {
            "One-way".to_owned()
        },
    })
}

pub fn parse_futures_margin_mode(
    payload: &Value,
    fallback_symbol: &str,
) -> Result<BinanceFuturesMarginMode> {
    ensure_not_binance_error(payload)?;
    let row = first_payload_object(payload)
        .ok_or_else(|| anyhow!("futures margin type response missing object payload"))?;
    let symbol = if let Some(symbol) = upper_string(row, "symbol").filter(|value| !value.is_empty())
    {
        symbol
    } else {
        normalize_required_symbol(fallback_symbol)?
    };
    let margin_type = row
        .get("marginType")
        .or_else(|| row.get("margin_type"))
        .and_then(Value::as_str)
        .map(normalize_futures_margin_type)
        .transpose()?
        .ok_or_else(|| anyhow!("futures margin type response missing marginType"))?;
    Ok(BinanceFuturesMarginMode {
        symbol,
        margin_type,
    })
}

pub fn parse_futures_leverage_change(
    payload: &Value,
    fallback_symbol: &str,
) -> Result<BinanceFuturesLeverageChange> {
    ensure_not_binance_error(payload)?;
    let row = first_payload_object(payload)
        .ok_or_else(|| anyhow!("futures leverage response missing object payload"))?;
    let symbol = if let Some(symbol) = upper_string(row, "symbol").filter(|value| !value.is_empty())
    {
        symbol
    } else {
        normalize_required_symbol(fallback_symbol)?
    };
    let leverage = first_i64(row, &["leverage"])
        .filter(|value| (1..=125).contains(value))
        .ok_or_else(|| anyhow!("futures leverage response missing valid leverage"))?;
    Ok(BinanceFuturesLeverageChange {
        symbol,
        leverage,
        max_notional_value: first_f64(row, &["maxNotionalValue", "maxNotional"]),
    })
}

pub fn parse_futures_multi_assets_mode(payload: &Value) -> Result<BinanceFuturesMultiAssetsMode> {
    ensure_not_binance_error(payload)?;
    let value = multi_assets_margin_value(payload)
        .ok_or_else(|| anyhow!("futures multi-assets response missing multiAssetsMargin"))?;
    Ok(BinanceFuturesMultiAssetsMode {
        multi_assets_margin: coerce_bool_flag(value),
    })
}

pub fn parse_futures_position_margin_change(
    payload: &Value,
    fallback_symbol: &str,
    amount: f64,
    fallback_position_side: Option<&str>,
) -> Result<BinanceFuturesPositionMarginChange> {
    ensure_not_binance_error(payload)?;
    if !amount.is_finite() || amount <= 0.0 {
        bail!("position-margin amount must be positive");
    }
    let row = first_payload_object(payload)
        .ok_or_else(|| anyhow!("futures position-margin response must be an object"))?;
    let symbol = row
        .get("symbol")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(fallback_symbol);
    let position_side = row
        .get("positionSide")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .or_else(|| {
            fallback_position_side
                .map(str::trim)
                .filter(|value| !value.is_empty())
        })
        .unwrap_or("BOTH")
        .to_uppercase();
    Ok(BinanceFuturesPositionMarginChange {
        symbol: normalize_required_symbol(symbol)?,
        position_side,
        amount: first_f64(row, &["amount"]).unwrap_or(amount),
        margin_type: parse_json_i64(row.get("type")).unwrap_or(1),
    })
}

fn build_balance_snapshot(
    asset: impl Into<String>,
    total_balance: f64,
    available_balance: f64,
) -> BinanceAccountSnapshot {
    let asset = asset.into();
    BinanceAccountSnapshot {
        asset,
        total_balance,
        available_balance,
        // Keep the old fields populated as aliases so existing USD-M and Spot
        // consumers remain source-compatible while Coin-M reports its real asset.
        usdt_balance: total_balance,
        total_usdt_balance: total_balance,
        available_usdt_balance: available_balance,
    }
}

pub fn parse_futures_usdt_balance(
    balance_payload: &Value,
    account_payload: Option<&Value>,
) -> Result<BinanceAccountSnapshot> {
    ensure_not_binance_error(balance_payload)?;
    if let Some(account) = account_payload {
        ensure_not_binance_error(account)?;
    }

    let mut snapshot = None;
    if let Some(rows) = balance_payload.as_array() {
        'preferred_asset: for preferred_asset in PREFERRED_FUTURES_COLLATERAL_ASSETS {
            for row_value in rows {
                let Some(row) = row_value.as_object() else {
                    continue;
                };
                let asset = row
                    .get("asset")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .trim()
                    .to_uppercase();
                if asset != preferred_asset {
                    continue;
                }
                let total = first_f64(row, &["balance", "walletBalance", "crossWalletBalance"]);
                let available = first_f64(row, &["availableBalance", "maxWithdrawAmount"]);
                let Some(total) = total.or(available) else {
                    continue;
                };
                snapshot = Some(build_balance_snapshot(
                    asset,
                    total,
                    available.unwrap_or(total),
                ));
                break 'preferred_asset;
            }
        }
    }

    if let Some(snapshot) = snapshot {
        return Ok(snapshot);
    }

    let mut snapshot = BinanceAccountSnapshot {
        asset: "USDT".to_owned(),
        total_balance: 0.0,
        available_balance: 0.0,
        usdt_balance: 0.0,
        total_usdt_balance: 0.0,
        available_usdt_balance: 0.0,
    };

    if let Some(account) = account_payload.and_then(Value::as_object) {
        let mut has_total = false;
        let mut has_available = false;
        if let Some(total) = first_f64(
            account,
            &[
                "totalWalletBalance",
                "totalMarginBalance",
                "totalCrossWalletBalance",
                "totalCrossBalance",
                "walletBalance",
            ],
        )
        .filter(|value| value.is_finite() && *value > 0.0)
        {
            snapshot.total_usdt_balance = total;
            snapshot.usdt_balance = total;
            snapshot.total_balance = total;
            has_total = true;
        }
        if let Some(available) =
            first_f64(account, &["availableBalance", "maxWithdrawAmount", "free"])
                .filter(|value| value.is_finite() && *value >= 0.0)
        {
            snapshot.available_usdt_balance = available;
            snapshot.available_balance = available;
            has_available = true;
        }
        if !has_total || !has_available {
            for preferred_asset in PREFERRED_FUTURES_COLLATERAL_ASSETS {
                let Some(asset_row) = find_asset_row(account.get("assets"), preferred_asset) else {
                    continue;
                };
                let total = first_f64(
                    asset_row,
                    &[
                        "walletBalance",
                        "marginBalance",
                        "crossWalletBalance",
                        "availableBalance",
                    ],
                )
                .filter(|value| *value > 0.0);
                let available = first_f64(
                    asset_row,
                    &[
                        "availableBalance",
                        "maxWithdrawAmount",
                        "crossWalletBalance",
                    ],
                )
                .filter(|value| *value >= 0.0);
                if total.is_none() && available.is_none() {
                    continue;
                }
                snapshot.asset = preferred_asset.to_owned();
                if !has_total && let Some(total) = total {
                    snapshot.usdt_balance = total;
                    snapshot.total_usdt_balance = total;
                    snapshot.total_balance = total;
                    has_total = true;
                }
                if !has_available && let Some(available) = available {
                    snapshot.available_usdt_balance = available;
                    snapshot.available_balance = available;
                    has_available = true;
                }
                if has_total && has_available {
                    break;
                }
            }
        }
    }

    if snapshot.total_usdt_balance <= 0.0
        && snapshot.usdt_balance <= 0.0
        && snapshot.available_usdt_balance <= 0.0
    {
        bail!("USDT balance missing from futures account response");
    }
    Ok(snapshot)
}

pub fn parse_futures_collateral_balance(
    balance_payload: &Value,
    account_payload: Option<&Value>,
) -> Result<BinanceAccountSnapshot> {
    ensure_not_binance_error(balance_payload)?;
    if let Some(account) = account_payload {
        ensure_not_binance_error(account)?;
    }

    let mut rows = parse_futures_balance_rows(balance_payload).unwrap_or_default();
    if rows.is_empty()
        && let Some(account_rows) = account_payload
            .and_then(Value::as_object)
            .and_then(|account| account.get("assets"))
    {
        rows = parse_futures_balance_rows(account_rows).unwrap_or_default();
    }

    let selected = rows
        .iter()
        .find(|row| PREFERRED_FUTURES_COLLATERAL_ASSETS.contains(&row.asset.as_str()))
        .or_else(|| rows.first());
    if let Some(row) = selected {
        return Ok(build_balance_snapshot(
            row.asset.clone(),
            row.total,
            row.free,
        ));
    }

    if let Some(account) = account_payload.and_then(Value::as_object) {
        let total = first_f64(
            account,
            &[
                "totalWalletBalance",
                "totalMarginBalance",
                "totalCrossWalletBalance",
                "totalCrossBalance",
                "walletBalance",
            ],
        );
        let available = first_f64(
            account,
            &[
                "availableBalance",
                "maxWithdrawAmount",
                "withdrawAvailable",
                "free",
            ],
        );
        if let Some(total) = total.or(available) {
            let asset = account
                .get("asset")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .unwrap_or("COLLATERAL");
            return Ok(build_balance_snapshot(
                asset.trim().to_uppercase(),
                total,
                available.unwrap_or(total),
            ));
        }
    }

    bail!("futures collateral balance missing from account response")
}

pub fn parse_spot_usdt_balance(account_payload: &Value) -> Result<BinanceAccountSnapshot> {
    ensure_not_binance_error(account_payload)?;
    let account = account_payload
        .as_object()
        .ok_or_else(|| anyhow!("spot account response must be an object"))?;
    let row = find_asset_row(account.get("balances"), "USDT")
        .ok_or_else(|| anyhow!("USDT balance missing from spot account response"))?;
    let free = first_f64(row, &["free"]).unwrap_or(0.0);
    let locked = first_f64(row, &["locked"]).unwrap_or(0.0);
    let total = free + locked;
    Ok(build_balance_snapshot("USDT", total, free))
}

pub fn parse_futures_balance_rows(balance_payload: &Value) -> Result<Vec<BinanceBalanceRow>> {
    ensure_not_binance_error(balance_payload)?;
    let rows = balance_payload
        .as_array()
        .ok_or_else(|| anyhow!("futures balance response must be an array"))?;
    let mut balances = Vec::new();
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let asset = row
            .get("asset")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if asset.is_empty() {
            continue;
        }
        let total =
            first_f64(row, &["balance", "walletBalance", "crossWalletBalance"]).unwrap_or(0.0);
        let free = first_f64(row, &["availableBalance", "maxWithdrawAmount"]).unwrap_or(total);
        let locked = (total - free).max(0.0);
        if total > 0.0 || free > 0.0 || locked > 0.0 {
            balances.push(BinanceBalanceRow {
                asset,
                free,
                locked,
                total,
            });
        }
    }
    Ok(balances)
}

pub fn parse_spot_balance_rows(account_payload: &Value) -> Result<Vec<BinanceBalanceRow>> {
    ensure_not_binance_error(account_payload)?;
    let account = account_payload
        .as_object()
        .ok_or_else(|| anyhow!("spot account response must be an object"))?;
    let rows = account
        .get("balances")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("spot account response missing balances array"))?;
    let mut balances = Vec::new();
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let asset = row
            .get("asset")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if asset.is_empty() {
            continue;
        }
        let free = first_f64(row, &["free"]).unwrap_or(0.0);
        let locked = first_f64(row, &["locked"]).unwrap_or(0.0);
        let total = free + locked;
        if total > 0.0 || free > 0.0 || locked > 0.0 {
            balances.push(BinanceBalanceRow {
                asset,
                free,
                locked,
                total,
            });
        }
    }
    Ok(balances)
}

pub fn select_balance_free(rows: &[BinanceBalanceRow], asset: impl AsRef<str>) -> f64 {
    let asset = asset.as_ref().trim().to_uppercase();
    rows.iter()
        .find(|row| row.asset.eq_ignore_ascii_case(&asset))
        .map(|row| row.free)
        .unwrap_or(0.0)
}

pub fn non_usdt_balance_rows(rows: &[BinanceBalanceRow]) -> Vec<BinanceBalanceRow> {
    rows.iter()
        .filter(|row| {
            !row.asset.eq_ignore_ascii_case("USDT") && row.free.is_finite() && row.free > 0.0
        })
        .cloned()
        .collect()
}

pub fn parse_open_futures_positions(
    position_risk_payload: &Value,
    account_payload: Option<&Value>,
) -> Result<Vec<BinanceFuturesPosition>> {
    ensure_not_binance_error(position_risk_payload)?;
    if let Some(account) = account_payload {
        ensure_not_binance_error(account)?;
    }
    let rows = position_risk_payload
        .as_array()
        .ok_or_else(|| anyhow!("positionRisk response must be an array"))?;
    let account_positions = account_position_map(account_payload);
    let mut positions = Vec::new();
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let symbol = row
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if symbol.is_empty() {
            continue;
        }
        let Some(position_amt) = first_f64(row, &["positionAmt"]) else {
            continue;
        };
        if !position_amt.is_finite() || position_amt.abs() <= POSITION_EPSILON {
            continue;
        }

        let mut position = BinanceFuturesPosition {
            symbol,
            position_side: upper_string(row, "positionSide")
                .filter(|side| !side.is_empty())
                .unwrap_or_else(|| "BOTH".to_owned()),
            position_amt,
            notional: first_f64(row, &["notional"]).unwrap_or(0.0),
            initial_margin: first_f64(row, &["initialMargin"]).unwrap_or(0.0),
            position_initial_margin: first_f64(row, &["positionInitialMargin"]).unwrap_or(0.0),
            open_order_margin: first_f64(row, &["openOrderInitialMargin", "openOrderMargin"])
                .unwrap_or(0.0),
            isolated_wallet: first_f64(row, &["isolatedWallet"]).unwrap_or(0.0),
            isolated_margin: first_f64(row, &["isolatedMargin"]).unwrap_or(0.0),
            maint_margin: first_f64(row, &["maintMargin", "maintenanceMargin"]).unwrap_or(0.0),
            maint_margin_rate: first_f64(
                row,
                &[
                    "maintMarginRate",
                    "maintenanceMarginRate",
                    "maintMarginRatio",
                ],
            )
            .unwrap_or(0.0)
            .max(0.0),
            margin_balance: first_f64(row, &["marginBalance"]).unwrap_or(0.0),
            wallet_balance: first_f64(row, &["walletBalance"]).unwrap_or(0.0),
            margin_ratio: normalize_margin_ratio_percent(
                first_f64(row, &["marginRatio"]).unwrap_or(0.0),
            ),
            leverage: first_f64(row, &["leverage"]).unwrap_or(0.0),
            unrealized_profit: first_f64(row, &["unRealizedProfit", "unrealizedProfit"])
                .unwrap_or(0.0),
            entry_price: first_f64(row, &["entryPrice"]).unwrap_or(0.0),
            mark_price: first_f64(row, &["markPrice"]).unwrap_or(0.0),
            liquidation_price: first_f64(row, &["liquidationPrice"]).unwrap_or(0.0),
            margin_type: row
                .get("marginType")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_owned(),
            update_time_ms: first_i64(row, &["updateTime"]).unwrap_or(0),
            ..Default::default()
        };

        if let Some(account_position) = lookup_account_position(
            &account_positions,
            &position.symbol,
            &position.position_side,
        ) {
            merge_positive(
                account_position,
                &["initialMargin"],
                &mut position.initial_margin,
            );
            merge_positive(
                account_position,
                &["positionInitialMargin"],
                &mut position.position_initial_margin,
            );
            merge_positive(
                account_position,
                &["openOrderInitialMargin", "openOrderMargin"],
                &mut position.open_order_margin,
            );
            merge_positive(
                account_position,
                &["isolatedWallet"],
                &mut position.isolated_wallet,
            );
            merge_positive(
                account_position,
                &["isolatedMargin"],
                &mut position.isolated_margin,
            );
            if position.maint_margin <= 0.0 {
                merge_positive(
                    account_position,
                    &["maintMargin", "maintenanceMargin"],
                    &mut position.maint_margin,
                );
            }
            if position.margin_balance <= 0.0 {
                merge_positive(
                    account_position,
                    &["marginBalance"],
                    &mut position.margin_balance,
                );
            }
            if position.wallet_balance <= 0.0 {
                merge_positive(
                    account_position,
                    &["walletBalance"],
                    &mut position.wallet_balance,
                );
            }
            if position.notional <= 0.0 {
                merge_positive(account_position, &["notional"], &mut position.notional);
            }
            if position.entry_price <= 0.0 {
                merge_positive(account_position, &["entryPrice"], &mut position.entry_price);
            }
            if position.mark_price <= 0.0 {
                merge_positive(account_position, &["markPrice"], &mut position.mark_price);
            }
            if position.liquidation_price <= 0.0 {
                merge_positive(
                    account_position,
                    &["liquidationPrice"],
                    &mut position.liquidation_price,
                );
            }
            if position.leverage <= 0.0 {
                merge_positive(account_position, &["leverage"], &mut position.leverage);
            }
            if !position.unrealized_profit.is_finite() {
                merge_number(
                    account_position,
                    &["unRealizedProfit", "unrealizedProfit"],
                    &mut position.unrealized_profit,
                );
            }
            if position.margin_ratio <= 0.0 {
                merge_positive(
                    account_position,
                    &["marginRatio"],
                    &mut position.margin_ratio,
                );
                position.margin_ratio = normalize_margin_ratio_percent(position.margin_ratio);
            }
        }

        complete_position_derived_fields(&mut position);
        positions.push(position);
    }
    Ok(positions)
}

/// Parse the exchange settings for one configured symbol without treating a zero-size
/// position row as an open position. Binance returns margin type and leverage on those rows,
/// which is required to reconcile a flat account before read-only signal evaluation.
pub fn parse_futures_symbol_settings(
    position_risk_payload: &Value,
    account_payload: Option<&Value>,
    symbol: &str,
) -> Result<Option<BinanceFuturesSymbolSettings>> {
    ensure_not_binance_error(position_risk_payload)?;
    if let Some(account) = account_payload {
        ensure_not_binance_error(account)?;
    }
    let configured_symbol = normalize_required_symbol(symbol)?;
    let risk_rows = position_risk_payload
        .as_array()
        .ok_or_else(|| anyhow!("positionRisk response must be an array"))?;
    let account_rows = account_payload
        .and_then(Value::as_object)
        .and_then(|account| account.get("positions"))
        .and_then(Value::as_array)
        .into_iter()
        .flatten();

    let mut observed = false;
    let mut margin_types = Vec::new();
    let mut leverages = Vec::new();
    for row in risk_rows.iter().chain(account_rows) {
        let Some(row) = row.as_object() else {
            continue;
        };
        let row_symbol = row
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if row_symbol != configured_symbol {
            continue;
        }
        observed = true;
        if let Some(margin_type) = row
            .get("marginType")
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
        {
            let margin_type = normalize_futures_margin_type(margin_type)?;
            if !margin_types.contains(&margin_type) {
                margin_types.push(margin_type);
            }
        }
        if let Some(leverage) = first_f64(row, &["leverage"])
            .filter(|value| value.is_finite() && *value >= 1.0 && *value <= 125.0)
        {
            let leverage = leverage.round() as i64;
            if !leverages.contains(&leverage) {
                leverages.push(leverage);
            }
        }
    }

    if !observed {
        return Ok(None);
    }
    if margin_types.len() > 1 {
        bail!(
            "conflicting futures margin settings observed for {configured_symbol}: {}",
            margin_types.join(", ")
        );
    }
    if leverages.len() > 1 {
        bail!(
            "conflicting futures leverage settings observed for {configured_symbol}: {:?}",
            leverages
        );
    }
    Ok(Some(BinanceFuturesSymbolSettings {
        symbol: configured_symbol,
        margin_type: margin_types.into_iter().next(),
        leverage: leverages.into_iter().next(),
    }))
}

fn complete_position_derived_fields(position: &mut BinanceFuturesPosition) {
    if position.notional <= 0.0
        && position.mark_price.is_finite()
        && position.position_amt.is_finite()
    {
        position.notional = position.position_amt.abs() * position.mark_price.max(0.0);
    }

    let abs_notional = position.notional.abs();
    if position.maint_margin <= 0.0 && position.maint_margin_rate > 0.0 && abs_notional > 0.0 {
        position.maint_margin = abs_notional * position.maint_margin_rate;
    }

    let mut derived_margin = 0.0_f64;
    if position.position_initial_margin > 0.0 || position.open_order_margin > 0.0 {
        derived_margin =
            position.position_initial_margin.max(0.0) + position.open_order_margin.max(0.0);
    }
    if derived_margin <= 0.0 && position.initial_margin > 0.0 {
        derived_margin = position.initial_margin;
    }
    if derived_margin <= 0.0 && position.isolated_margin > 0.0 {
        derived_margin = position.isolated_margin;
    }
    if derived_margin <= 0.0 && position.isolated_wallet > 0.0 {
        let margin_from_isolated = position.isolated_wallet - position.unrealized_profit;
        derived_margin = if margin_from_isolated > 0.0 {
            margin_from_isolated
        } else {
            position.isolated_wallet
        };
    }
    if derived_margin <= 0.0
        && position.entry_price > 0.0
        && position.position_amt.abs() > 0.0
        && position.leverage > 0.0
    {
        derived_margin =
            (position.position_amt.abs() * position.entry_price) / position.leverage.max(1.0);
    }
    if derived_margin <= 0.0 && abs_notional > 0.0 && position.leverage > 0.0 {
        derived_margin = abs_notional / position.leverage.max(1.0);
    }
    derived_margin = derived_margin.max(0.0);

    if position.initial_margin <= 0.0 && derived_margin > 0.0 {
        position.initial_margin = derived_margin;
    }
    if position.margin_balance <= 0.0 {
        if position.isolated_wallet > 0.0 {
            position.margin_balance = position.isolated_wallet.max(0.0);
        } else if derived_margin > 0.0 {
            position.margin_balance = (derived_margin + position.unrealized_profit).max(0.0);
        }
    }
    if position.wallet_balance <= 0.0 {
        if position.margin_balance > 0.0 {
            position.wallet_balance = position.margin_balance;
        } else if derived_margin > 0.0 {
            position.wallet_balance = (derived_margin + position.unrealized_profit).max(0.0);
        }
    }

    let balance = if position.wallet_balance > 0.0 {
        position.wallet_balance
    } else {
        position.margin_balance
    }
    .max(0.0);
    let unrealized_loss = if position.unrealized_profit < 0.0 {
        position.unrealized_profit.abs()
    } else {
        0.0
    };
    let numerator =
        position.maint_margin.max(0.0) + position.open_order_margin.max(0.0) + unrealized_loss;
    if balance > 0.0 && numerator > 0.0 {
        position.margin_ratio_calc = (numerator / balance) * 100.0;
        if position.margin_ratio <= 0.0 {
            position.margin_ratio = position.margin_ratio_calc;
        }
    }
    position.margin_ratio = normalize_margin_ratio_percent(position.margin_ratio);
    if !position.margin_ratio.is_finite() || position.margin_ratio < 0.0 {
        position.margin_ratio = 0.0;
    }
}

pub(crate) fn current_timestamp_ms() -> Result<i64> {
    let duration = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .context("system clock is before Unix epoch")?;
    Ok(duration.as_millis().try_into().unwrap_or(i64::MAX))
}

fn account_position_map(account_payload: Option<&Value>) -> HashMap<String, Map<String, Value>> {
    let mut map = HashMap::new();
    let Some(rows) = account_payload
        .and_then(Value::as_object)
        .and_then(|account| account.get("positions"))
        .and_then(Value::as_array)
    else {
        return map;
    };
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let symbol = row
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if symbol.is_empty() {
            continue;
        }
        let side = upper_string(row, "positionSide")
            .filter(|side| !side.is_empty())
            .unwrap_or_else(|| "BOTH".to_owned());
        let key = position_key(&symbol, &side);
        map.insert(key, row.clone());
        if side != "BOTH" {
            map.entry(position_key(&symbol, "BOTH"))
                .or_insert_with(|| row.clone());
        }
    }
    map
}

fn lookup_account_position<'a>(
    positions: &'a HashMap<String, Map<String, Value>>,
    symbol: &str,
    side: &str,
) -> Option<&'a Map<String, Value>> {
    positions
        .get(&position_key(symbol, side))
        .or_else(|| positions.get(&position_key(symbol, "BOTH")))
}

fn position_key(symbol: &str, side: &str) -> String {
    format!(
        "{}|{}",
        symbol.trim().to_uppercase(),
        side.trim().to_uppercase()
    )
}

fn merge_positive(row: &Map<String, Value>, keys: &[&str], target: &mut f64) {
    if let Some(value) = first_f64(row, keys).filter(|value| value.is_finite() && *value > 0.0) {
        *target = value;
    }
}

fn merge_number(row: &Map<String, Value>, keys: &[&str], target: &mut f64) {
    if let Some(value) = first_f64(row, keys).filter(|value| value.is_finite()) {
        *target = value;
    }
}

fn find_asset_row<'a>(
    rows_value: Option<&'a Value>,
    asset: &str,
) -> Option<&'a Map<String, Value>> {
    let rows = rows_value.and_then(Value::as_array)?;
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        if row
            .get("asset")
            .and_then(Value::as_str)
            .map(|text| text.trim().eq_ignore_ascii_case(asset))
            .unwrap_or(false)
        {
            return Some(row);
        }
    }
    None
}

fn first_f64(row: &Map<String, Value>, keys: &[&str]) -> Option<f64> {
    for key in keys {
        if let Some(value) = parse_json_f64(row.get(*key)).filter(|value| value.is_finite()) {
            return Some(value);
        }
    }
    None
}

fn first_i64(row: &Map<String, Value>, keys: &[&str]) -> Option<i64> {
    for key in keys {
        if let Some(value) = parse_json_i64(row.get(*key)) {
            return Some(value);
        }
    }
    None
}

fn upper_string(row: &Map<String, Value>, key: &str) -> Option<String> {
    row.get(key)
        .and_then(Value::as_str)
        .map(|value| value.trim().to_uppercase())
}

fn normalize_required_symbol(symbol: &str) -> Result<String> {
    let normalized = symbol.trim().to_uppercase();
    if normalized.is_empty() {
        bail!("futures symbol is required");
    }
    Ok(normalized)
}

fn first_payload_object(payload: &Value) -> Option<&Map<String, Value>> {
    payload.as_object().or_else(|| {
        payload
            .as_array()
            .and_then(|rows| rows.first()?.as_object())
    })
}

fn dual_side_position_value(payload: &Value) -> Option<&Value> {
    if let Some(value) = payload.get("dualSidePosition") {
        return Some(value);
    }
    payload.as_array().and_then(|rows| {
        rows.first()
            .and_then(|first| first.get("dualSidePosition").or(Some(first)))
    })
}

fn multi_assets_margin_value(payload: &Value) -> Option<&Value> {
    if let Some(value) = payload.get("multiAssetsMargin") {
        return Some(value);
    }
    payload.as_array().and_then(|rows| {
        rows.first()
            .and_then(|first| first.get("multiAssetsMargin").or(Some(first)))
    })
}

fn coerce_bool_flag(value: &Value) -> bool {
    match value {
        Value::Bool(flag) => *flag,
        Value::Number(number) => number.as_i64().unwrap_or(0) != 0,
        Value::String(text) => matches!(
            text.trim().to_ascii_lowercase().as_str(),
            "true" | "1" | "yes" | "y"
        ),
        _ => false,
    }
}

fn parse_json_f64(value: Option<&Value>) -> Option<f64> {
    let parsed = match value? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.trim().parse::<f64>().ok(),
        _ => None,
    }?;
    parsed.is_finite().then_some(parsed)
}

fn parse_json_i64(value: Option<&Value>) -> Option<i64> {
    match value? {
        Value::Number(number) => number.as_i64(),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn normalize_base_url(value: String) -> Result<String> {
    let trimmed = value.trim().trim_end_matches('/').to_owned();
    if trimmed.is_empty() {
        bail!("base URL is required");
    }
    if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
        bail!("base URL must start with http:// or https://");
    }
    Ok(trimmed)
}

fn normalize_margin_ratio_percent(value: f64) -> f64 {
    if !value.is_finite() || value <= 0.0 {
        return 0.0;
    }
    if value <= 1.0 { value * 100.0 } else { value }
}

fn format_position_margin_amount(value: f64) -> String {
    let mut text = format!("{value:.8}");
    while text.contains('.') && text.ends_with('0') {
        text.pop();
    }
    if text.ends_with('.') {
        text.pop();
    }
    text
}

fn ensure_not_binance_error(value: &Value) -> Result<()> {
    let Some(obj) = value.as_object() else {
        return Ok(());
    };
    if obj.contains_key("code") && obj.contains_key("msg") {
        if matches!(
            parse_json_i64(obj.get("code")),
            Some(0) | Some(200) | Some(20_000)
        ) {
            return Ok(());
        }
        let message = obj
            .get("msg")
            .and_then(Value::as_str)
            .unwrap_or("Binance API error");
        bail!("{message}");
    }
    Ok(())
}

fn lower_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::thread;

    use reqwest::blocking::Client;
    use serde_json::json;

    use super::*;

    #[test]
    fn hmac_and_signed_query_match_binance_signature_shape() {
        let key =
            "\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b\x0b";
        assert_eq!(
            hmac_sha256_hex(key, "Hi There"),
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
        );

        let query = signed_query_string(
            "test-secret",
            1_700_000_000_000,
            10_000,
            &[("symbol", "BTCUSDT".to_owned())],
        );
        assert!(
            query.starts_with("symbol=BTCUSDT&timestamp=1700000000000&recvWindow=10000&signature=")
        );
        assert_eq!(query.rsplit_once('=').expect("signature").1.len(), 64);
    }

    #[test]
    fn client_builds_cpp_equivalent_account_endpoint_paths() {
        let futures =
            BinanceSignedRestClient::with_base_url(BinanceMarket::Futures, "https://example.test/")
                .expect("futures client");
        let coin = BinanceSignedRestClient::with_base_url(
            BinanceMarket::CoinFutures,
            "https://coin.test/",
        )
        .expect("coin futures client");
        let spot = BinanceSignedRestClient::with_base_url(BinanceMarket::Spot, "https://spot.test")
            .expect("spot client");

        assert_eq!(
            futures.futures_balance_url(),
            "https://example.test/fapi/v2/balance"
        );
        assert_eq!(
            futures.futures_account_url(),
            "https://example.test/fapi/v2/account"
        );
        assert_eq!(
            futures.futures_position_risk_url(),
            "https://example.test/fapi/v2/positionRisk"
        );
        assert_eq!(
            futures.futures_position_mode_url(),
            "https://example.test/fapi/v1/positionSide/dual"
        );
        assert_eq!(
            futures.futures_margin_type_url(),
            "https://example.test/fapi/v1/marginType"
        );
        assert_eq!(
            futures.futures_leverage_url(),
            "https://example.test/fapi/v1/leverage"
        );
        assert_eq!(
            futures.futures_multi_assets_margin_url(),
            "https://example.test/fapi/v1/multiAssetsMargin"
        );
        assert_eq!(
            futures.futures_v1_path("/order"),
            "https://example.test/fapi/v1/order"
        );
        assert_eq!(
            futures.futures_v1_path("/openOrders"),
            "https://example.test/fapi/v1/openOrders"
        );
        assert_eq!(
            futures.futures_v1_path("/allOpenOrders"),
            "https://example.test/fapi/v1/allOpenOrders"
        );
        assert_eq!(
            coin.futures_balance_url(),
            "https://coin.test/dapi/v1/balance"
        );
        assert_eq!(
            coin.futures_account_url(),
            "https://coin.test/dapi/v1/account"
        );
        assert_eq!(
            coin.futures_position_risk_url(),
            "https://coin.test/dapi/v1/positionRisk"
        );
        assert_eq!(
            coin.futures_position_mode_url(),
            "https://coin.test/dapi/v1/positionSide/dual"
        );
        assert_eq!(
            coin.futures_v1_path("/order"),
            "https://coin.test/dapi/v1/order"
        );
        assert_eq!(
            coin.futures_v1_path("/openOrders"),
            "https://coin.test/dapi/v1/openOrders"
        );
        assert_eq!(
            coin.futures_v1_path("/allOpenOrders"),
            "https://coin.test/dapi/v1/allOpenOrders"
        );
        assert_eq!(spot.spot_account_url(), "https://spot.test/api/v3/account");
    }

    #[test]
    fn futures_account_settings_read_and_mutations_use_python_compatible_wire_contract() {
        fn serve_request(mut stream: TcpStream, expected_prefix: &str, body: &str) {
            let mut request = Vec::new();
            let mut buffer = [0_u8; 1024];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream
                    .read(&mut buffer)
                    .expect("read account fixture request");
                if count == 0 {
                    break;
                }
                request.extend_from_slice(&buffer[..count]);
            }
            let request_line = String::from_utf8_lossy(&request)
                .lines()
                .next()
                .unwrap_or_default()
                .to_owned();
            assert!(
                request_line.starts_with(expected_prefix),
                "unexpected request line: {request_line}"
            );
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
                body.len(),
                body
            );
            stream
                .write_all(response.as_bytes())
                .expect("write account fixture response");
        }

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind account fixture");
        let address = listener.local_addr().expect("account fixture address");
        let server = thread::spawn(move || {
            let (stream, _) = listener.accept().expect("position-risk request");
            serve_request(
                stream,
                "GET /fapi/v2/positionRisk?",
                r#"[{"symbol":"BTCUSDT","positionSide":"BOTH","positionAmt":"0","marginType":"isolated","leverage":"5"}]"#,
            );
            let (stream, _) = listener.accept().expect("account request");
            serve_request(
                stream,
                "GET /fapi/v2/account?",
                r#"{"positions":[{"symbol":"BTCUSDT","positionSide":"BOTH","positionAmt":"0","marginType":"isolated","leverage":"5"}]}"#,
            );
            let (stream, _) = listener.accept().expect("margin mutation request");
            serve_request(
                stream,
                "POST /fapi/v1/marginType?symbol=BTCUSDT&marginType=CROSSED&",
                r#"{"code":200,"msg":"success"}"#,
            );
            let (stream, _) = listener.accept().expect("leverage mutation request");
            serve_request(
                stream,
                "POST /fapi/v1/leverage?symbol=BTCUSDT&leverage=25&",
                r#"{"symbol":"BTCUSDT","leverage":25,"maxNotionalValue":"100000"}"#,
            );
        });

        let http = Client::builder()
            .no_proxy()
            .build()
            .expect("proxy-free account fixture client");
        let client = BinanceSignedRestClient::with_http_client(
            BinanceMarket::Futures,
            format!("http://{address}"),
            http,
        )
        .expect("futures account fixture client");
        let credentials = BinanceApiCredentials::new("key", "secret");
        let snapshot = client
            .fetch_futures_account_read_snapshot(&credentials, "btcusdt")
            .expect("account read snapshot");
        assert!(snapshot.positions.is_empty());
        assert_eq!(
            snapshot
                .symbol_settings
                .as_ref()
                .and_then(|settings| settings.margin_type.as_deref()),
            Some("ISOLATED")
        );
        assert_eq!(
            snapshot
                .symbol_settings
                .as_ref()
                .and_then(|settings| settings.leverage),
            Some(5)
        );
        assert_eq!(
            client
                .change_futures_margin_type(&credentials, "btcusdt", "cross")
                .expect("margin mutation")
                .margin_type,
            "CROSSED"
        );
        assert_eq!(
            client
                .change_futures_leverage(&credentials, "btcusdt", 25)
                .expect("leverage mutation")
                .leverage,
            25
        );
        server.join().expect("account fixture server");
    }

    #[test]
    fn coin_futures_balance_parser_preserves_collateral_asset() {
        let snapshot = parse_futures_collateral_balance(
            &json!([
                {"asset": "BTC", "balance": "0.75", "availableBalance": "0.50"},
                {"asset": "ETH", "balance": "0.25", "availableBalance": "0.20"}
            ]),
            Some(&json!({
                "assets": [
                    {"asset": "BTC", "walletBalance": "0.75", "availableBalance": "0.50"}
                ]
            })),
        )
        .expect("COIN-M collateral balance");

        assert_eq!(snapshot.asset, "BTC");
        assert_eq!(snapshot.total_balance, 0.75);
        assert_eq!(snapshot.available_balance, 0.5);
        assert_eq!(snapshot.total_usdt_balance, snapshot.total_balance);
        assert_eq!(snapshot.available_usdt_balance, snapshot.available_balance);
    }

    #[test]
    fn futures_market_guard_accepts_usd_m_and_coin_m_but_rejects_spot() {
        let futures =
            BinanceSignedRestClient::with_base_url(BinanceMarket::Futures, "https://example.test")
                .expect("USD-M client");
        let coin = BinanceSignedRestClient::with_base_url(
            BinanceMarket::CoinFutures,
            "https://example.test",
        )
        .expect("COIN-M client");
        let spot =
            BinanceSignedRestClient::with_base_url(BinanceMarket::Spot, "https://example.test")
                .expect("Spot client");

        assert!(futures.require_futures_market().is_ok());
        assert!(coin.require_futures_market().is_ok());
        assert!(spot.require_futures_market().is_err());
    }

    #[test]
    fn parses_and_builds_futures_position_mode_like_python_clients() {
        let hedge =
            parse_futures_position_mode(&json!({"dualSidePosition": "true"})).expect("hedge mode");
        assert!(hedge.dual_side_position);
        assert_eq!(hedge.position_mode, "Hedge");

        let one_way = parse_futures_position_mode(&json!([{"dualSidePosition": false}]))
            .expect("one-way mode");
        assert!(!one_way.dual_side_position);
        assert_eq!(one_way.position_mode, "One-way");

        let fallback_truthy =
            parse_futures_position_mode(&json!(["yes"])).expect("truthy list fallback");
        assert!(fallback_truthy.dual_side_position);

        assert_eq!(
            build_futures_position_mode_params(true),
            vec![("dualSidePosition", "true".to_owned())]
        );
        assert_eq!(
            build_futures_position_mode_params(false),
            vec![("dualSidePosition", "false".to_owned())]
        );
        assert!(parse_futures_position_mode(&json!({})).is_err());
    }

    #[test]
    fn builds_futures_margin_leverage_and_multi_assets_requests_like_python() {
        assert_eq!(normalize_futures_margin_type("cross").unwrap(), "CROSSED");
        assert_eq!(
            build_futures_margin_type_params("btcusdt", "cross").unwrap(),
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("marginType", "CROSSED".to_owned())
            ]
        );
        assert_eq!(
            build_futures_margin_type_params(" ETHUSDT ", "isolated").unwrap(),
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("marginType", "ISOLATED".to_owned())
            ]
        );
        assert_eq!(
            build_futures_leverage_params("btcusdt", 20).unwrap(),
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("leverage", "20".to_owned())
            ]
        );
        assert_eq!(
            build_futures_multi_assets_mode_params(true),
            vec![("multiAssetsMargin", "true".to_owned())]
        );
        assert_eq!(
            build_futures_position_margin_params("btcusdt", 1.25, Some("long")).unwrap(),
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("amount", "1.25".to_owned()),
                ("type", "1".to_owned()),
                ("positionSide", "LONG".to_owned())
            ]
        );
        assert!(build_futures_margin_type_params("", "isolated").is_err());
        assert!(build_futures_margin_type_params("BTCUSDT", "portfolio").is_err());
        assert!(build_futures_leverage_params("BTCUSDT", 0).is_err());
        assert!(build_futures_leverage_params("BTCUSDT", 126).is_err());
        assert!(build_futures_position_margin_params("BTCUSDT", 0.0, None).is_err());
    }

    #[test]
    fn parses_futures_setting_responses_and_accepts_success_codes() {
        let margin =
            parse_futures_margin_mode(&json!({"symbol": "btcusdt", "marginType": "cross"}), "")
                .expect("margin mode");
        assert_eq!(
            margin,
            BinanceFuturesMarginMode {
                symbol: "BTCUSDT".to_owned(),
                margin_type: "CROSSED".to_owned(),
            }
        );

        let leverage = parse_futures_leverage_change(
            &json!({"symbol": "ethusdt", "leverage": "21", "maxNotionalValue": "1000000"}),
            "",
        )
        .expect("leverage change");
        assert_eq!(leverage.symbol, "ETHUSDT");
        assert_eq!(leverage.leverage, 21);
        assert_eq!(leverage.max_notional_value, Some(1_000_000.0));

        let margin_change = parse_futures_position_margin_change(
            &json!({"code": 200, "msg": "success"}),
            "btcusdt",
            1.25,
            Some("long"),
        )
        .expect("position margin change");
        assert_eq!(
            margin_change,
            BinanceFuturesPositionMarginChange {
                symbol: "BTCUSDT".to_owned(),
                position_side: "LONG".to_owned(),
                amount: 1.25,
                margin_type: 1,
            }
        );

        let multi = parse_futures_multi_assets_mode(&json!({"multiAssetsMargin": "true"}))
            .expect("multi assets mode");
        assert!(multi.multi_assets_margin);

        assert!(ensure_not_binance_error(&json!({"code": 200, "msg": "success"})).is_ok());
        assert!(
            ensure_not_binance_error(
                &json!({"code": -4046, "msg": "No need to change margin type."})
            )
            .is_err()
        );
    }

    #[test]
    fn parses_futures_usdt_balance_and_normalized_rows() {
        let balance_payload = json!([
            {"asset": "BTC", "balance": "0", "availableBalance": "0"},
            {"asset": "USDT", "balance": "125.50", "availableBalance": "100.25"}
        ]);
        let account_payload = json!({
            "totalWalletBalance": "130.00",
            "availableBalance": "99.00",
            "assets": [
                {"asset": "USDT", "walletBalance": "128.00", "availableBalance": "98.00"}
            ]
        });

        let snapshot =
            parse_futures_usdt_balance(&balance_payload, Some(&account_payload)).expect("balance");
        assert_eq!(snapshot.asset, "USDT");
        assert_eq!(snapshot.usdt_balance, 125.5);
        assert_eq!(snapshot.total_usdt_balance, 125.5);
        assert_eq!(snapshot.available_usdt_balance, 100.25);

        let rows = parse_futures_balance_rows(&balance_payload).expect("rows");
        assert_eq!(
            rows,
            [BinanceBalanceRow {
                asset: "USDT".to_owned(),
                free: 100.25,
                locked: 25.25,
                total: 125.5,
            }]
        );
    }

    #[test]
    fn rejects_non_finite_exchange_numeric_strings() {
        let balances = json!([
            {"asset": "USDT", "balance": "NaN", "availableBalance": "inf"},
            {"asset": "BUSD", "balance": "12.5", "availableBalance": "10.0"}
        ]);
        let fallback = parse_futures_usdt_balance(&balances, None).expect("BUSD fallback");
        assert_eq!(fallback.asset, "BUSD");
        assert_eq!(fallback.usdt_balance, 12.5);
        assert_eq!(fallback.available_usdt_balance, 10.0);
        assert!(
            parse_futures_balance_rows(&balances)
                .expect("balance rows")
                .iter()
                .all(|row| row.total.is_finite() && row.free.is_finite() && row.locked.is_finite())
        );

        let positions = json!([
            {"symbol": "BTCUSDT", "positionAmt": "NaN", "markPrice": "65000"},
            {"symbol": "ETHUSDT", "positionAmt": "0.5", "markPrice": "inf", "leverage": "10"}
        ]);
        let parsed = parse_open_futures_positions(&positions, None).expect("positions");
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].symbol, "ETHUSDT");
        assert!(parsed[0].position_amt.is_finite());
        assert!(parsed[0].mark_price.is_finite());
        assert!(parsed[0].notional.is_finite());
    }

    #[test]
    fn futures_balance_fallback_skips_malformed_asset_rows() {
        let balance_payload = json!([]);
        let account_payload = json!({
            "assets": [
                null,
                {"asset": "USDT", "walletBalance": "NaN"},
                {"asset": "BUSD", "walletBalance": "8.5", "availableBalance": "7.0"}
            ]
        });

        let snapshot = parse_futures_usdt_balance(&balance_payload, Some(&account_payload))
            .expect("BUSD account-asset fallback");
        assert_eq!(snapshot.asset, "BUSD");
        assert_eq!(snapshot.usdt_balance, 8.5);
        assert_eq!(snapshot.available_usdt_balance, 7.0);
    }

    #[test]
    fn futures_account_fallback_supports_cross_margin_totals() {
        let balance_payload = json!([]);
        let account_payload = json!({
            "totalCrossWalletBalance": "21.5",
            "totalCrossBalance": "22.0",
            "assets": [
                {"asset": "USDT", "crossWalletBalance": "21.5"}
            ]
        });

        let snapshot = parse_futures_usdt_balance(&balance_payload, Some(&account_payload))
            .expect("cross-margin account fallback");
        assert_eq!(snapshot.asset, "USDT");
        assert_eq!(snapshot.usdt_balance, 21.5);
        assert_eq!(snapshot.total_usdt_balance, 21.5);
        assert_eq!(snapshot.available_usdt_balance, 21.5);
    }

    #[test]
    fn parses_spot_usdt_balance_and_rows_like_python_account_surface() {
        let payload = json!({
            "balances": [
                {"asset": "ETH", "free": "0", "locked": "0"},
                {"asset": "USDT", "free": "10.5", "locked": "2.25"}
            ]
        });
        let snapshot = parse_spot_usdt_balance(&payload).expect("spot balance");
        assert_eq!(snapshot.asset, "USDT");
        assert_eq!(snapshot.usdt_balance, 12.75);
        assert_eq!(snapshot.available_usdt_balance, 10.5);

        let rows = parse_spot_balance_rows(&payload).expect("spot rows");
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].asset, "USDT");
        assert_eq!(rows[0].locked, 2.25);
        assert_eq!(select_balance_free(&rows, "usdt"), 10.5);
        assert_eq!(select_balance_free(&rows, "BTC"), 0.0);
        assert!(non_usdt_balance_rows(&rows).is_empty());

        let mixed_rows = vec![
            BinanceBalanceRow {
                asset: "USDT".to_owned(),
                free: 100.0,
                locked: 0.0,
                total: 100.0,
            },
            BinanceBalanceRow {
                asset: "ETH".to_owned(),
                free: 0.25,
                locked: 0.05,
                total: 0.30,
            },
            BinanceBalanceRow {
                asset: "BTC".to_owned(),
                free: 0.0,
                locked: 0.1,
                total: 0.1,
            },
        ];
        let non_usdt = non_usdt_balance_rows(&mixed_rows);
        assert_eq!(non_usdt.len(), 1);
        assert_eq!(non_usdt[0].asset, "ETH");
        assert_eq!(non_usdt[0].free, 0.25);
    }

    #[test]
    fn parses_open_futures_positions_with_account_overlay_and_margin_calc() {
        let risk_payload = json!([
            {"symbol": "ETHUSDT", "positionSide": "BOTH", "positionAmt": "0", "markPrice": "2000"},
            {
                "symbol": "BTCUSDT",
                "positionSide": "LONG",
                "positionAmt": "0.5",
                "notional": "0",
                "openOrderInitialMargin": "3",
                "maintMarginRate": "0.005",
                "unRealizedProfit": "-5",
                "entryPrice": "20000",
                "markPrice": "21000",
                "leverage": "10",
                "marginType": "isolated",
                "updateTime": 1700000000000_i64
            }
        ]);
        let account_payload = json!({
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "positionSide": "LONG",
                    "positionInitialMargin": "1000",
                    "walletBalance": "1200",
                    "liquidationPrice": "15000"
                }
            ]
        });

        let positions =
            parse_open_futures_positions(&risk_payload, Some(&account_payload)).expect("positions");
        assert_eq!(positions.len(), 1);
        let position = &positions[0];
        assert_eq!(position.symbol, "BTCUSDT");
        assert_eq!(position.position_side, "LONG");
        assert_eq!(position.position_amt, 0.5);
        assert_eq!(position.notional, 10_500.0);
        assert_eq!(position.position_initial_margin, 1000.0);
        assert_eq!(position.wallet_balance, 1200.0);
        assert_eq!(position.liquidation_price, 15000.0);
        assert!((position.maint_margin - 52.5).abs() < 1e-9);
        assert!((position.margin_ratio_calc - 5.041666666666667).abs() < 1e-9);
        assert_eq!(position.margin_ratio, position.margin_ratio_calc);
        assert_eq!(position.margin_type, "isolated");
        assert_eq!(position.update_time_ms, 1_700_000_000_000);
    }

    #[test]
    fn parses_flat_symbol_settings_without_promoting_zero_position_to_open() {
        let risk_payload = json!([
            {
                "symbol": "BTCUSDT",
                "positionSide": "BOTH",
                "positionAmt": "0",
                "marginType": "isolated",
                "leverage": "5"
            },
            {
                "symbol": "ETHUSDT",
                "positionSide": "BOTH",
                "positionAmt": "0",
                "marginType": "cross",
                "leverage": "20"
            }
        ]);
        let positions = parse_open_futures_positions(&risk_payload, None).expect("open positions");
        assert!(positions.is_empty());

        let settings = parse_futures_symbol_settings(&risk_payload, None, "btcusdt")
            .expect("flat symbol settings")
            .expect("BTCUSDT settings");
        assert_eq!(settings.symbol, "BTCUSDT");
        assert_eq!(settings.margin_type.as_deref(), Some("ISOLATED"));
        assert_eq!(settings.leverage, Some(5));
    }

    #[test]
    fn flat_symbol_settings_reject_conflicting_exchange_rows() {
        let risk_payload = json!([
            {
                "symbol": "BTCUSDT",
                "positionSide": "LONG",
                "positionAmt": "0",
                "marginType": "isolated",
                "leverage": "5"
            },
            {
                "symbol": "BTCUSDT",
                "positionSide": "SHORT",
                "positionAmt": "0",
                "marginType": "cross",
                "leverage": "5"
            }
        ]);

        let error = parse_futures_symbol_settings(&risk_payload, None, "BTCUSDT")
            .expect_err("conflicting settings must be rejected");
        assert!(
            error
                .to_string()
                .contains("conflicting futures margin settings")
        );
    }

    #[test]
    fn binance_error_payloads_are_rejected() {
        let payload = json!({"code": -1022, "msg": "Signature for this request is not valid."});
        assert!(parse_spot_usdt_balance(&payload).is_err());
        assert!(parse_open_futures_positions(&payload, None).is_err());
    }
}
