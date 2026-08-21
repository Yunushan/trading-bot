use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Result, anyhow, bail};
use serde_json::{Map, Value};

use crate::account::{BinanceApiCredentials, BinanceSignedRestClient, current_timestamp_ms};

const FUTURES_ORDER_RECV_WINDOW_MS: u64 = 5_000;
const SPOT_ORDER_RECV_WINDOW_MS: u64 = 5_000;
static CLIENT_ORDER_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn new_binance_client_order_id() -> String {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64;
    let sequence = CLIENT_ORDER_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("tb-{timestamp:016x}{sequence:016x}")
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesSymbolFilters {
    pub symbol: String,
    pub step_size: f64,
    pub tick_size: f64,
    pub min_qty: f64,
    pub max_qty: f64,
    pub min_notional: f64,
    pub quantity_precision: i64,
    pub price_precision: i64,
    pub quote_asset_precision: i64,
    pub max_leverage: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesOrderResult {
    pub symbol: String,
    pub side: String,
    pub position_side: String,
    pub order_id: String,
    pub status: String,
    pub executed_qty: f64,
    pub avg_price: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesOpenOrder {
    pub symbol: String,
    pub order_id: String,
    pub client_order_id: String,
    pub status: String,
    pub side: String,
    pub order_type: String,
    pub position_side: String,
    pub orig_qty: f64,
    pub executed_qty: f64,
    pub price: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesCancelResult {
    pub symbol: String,
    pub order_id: String,
    pub status: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesTrade {
    pub symbol: String,
    pub trade_id: String,
    pub order_id: String,
    pub price: f64,
    pub quantity: f64,
    pub quote_quantity: f64,
    pub realized_pnl: f64,
    pub commission: f64,
    pub commission_asset: String,
    pub time_ms: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesLeverageBracket {
    pub symbol: String,
    pub initial_leverage: i64,
    pub notional_cap: f64,
    pub notional_floor: f64,
    pub maint_margin_ratio: f64,
    pub cum: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesForceOrder {
    pub symbol: String,
    pub order_id: String,
    pub side: String,
    pub position_side: String,
    pub status: String,
    pub order_type: String,
    pub avg_price: f64,
    pub executed_qty: f64,
    pub orig_qty: f64,
    pub price: f64,
    pub time_ms: i64,
    pub update_time_ms: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceSpotTrade {
    pub symbol: String,
    pub trade_id: String,
    pub order_id: String,
    pub price: f64,
    pub quantity: f64,
    pub quote_quantity: f64,
    pub commission: f64,
    pub commission_asset: String,
    pub is_buyer: bool,
    pub is_maker: bool,
    pub is_best_match: bool,
    pub time_ms: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceSpotPositionCost {
    pub symbol: String,
    pub quantity: f64,
    pub cost: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesOrderParams {
    pub params: Vec<(&'static str, String)>,
    pub symbol: String,
    pub side: String,
    pub position_side: String,
}

// Spot and futures share the normalized filter/order response shape. The aliases
// keep the market-specific API explicit without duplicating the wire contract.
pub type BinanceSpotSymbolFilters = BinanceFuturesSymbolFilters;
pub type BinanceSpotOrderResult = BinanceFuturesOrderResult;
pub type BinanceSpotOrderParams = BinanceFuturesOrderParams;

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceSpotSymbolMetadata {
    pub symbol: String,
    pub status: String,
    pub base_asset: String,
    pub quote_asset: String,
    pub filters: BinanceSpotSymbolFilters,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceQuantityAdjustment {
    pub ok: bool,
    pub quantity: f64,
    pub error: Option<String>,
}

impl BinanceSignedRestClient {
    pub fn fetch_futures_symbol_filters(
        &self,
        symbol: impl AsRef<str>,
    ) -> Result<BinanceFuturesSymbolFilters> {
        self.require_futures_market()?;
        let exchange_info_path = self.futures_v1_path("/exchangeInfo");
        let payload = self.public_get_json(&exchange_info_path, &[])?;
        parse_futures_symbol_filters(&payload, symbol.as_ref())
    }

    pub fn fetch_spot_symbol_filters(
        &self,
        symbol: impl AsRef<str>,
    ) -> Result<BinanceSpotSymbolFilters> {
        self.require_spot_market()?;
        let payload = self.public_get_json("/api/v3/exchangeInfo", &[])?;
        parse_spot_symbol_filters(&payload, symbol.as_ref())
    }

    pub fn fetch_spot_symbol_metadata(
        &self,
        symbol: impl AsRef<str>,
    ) -> Result<BinanceSpotSymbolMetadata> {
        self.require_spot_market()?;
        let payload = self.public_get_json("/api/v3/exchangeInfo", &[])?;
        parse_spot_symbol_metadata(&payload, symbol.as_ref())
    }

    pub fn adjust_spot_quantity_to_filters(
        &self,
        symbol: impl AsRef<str>,
        quantity: f64,
        estimated_price: f64,
    ) -> Result<BinanceQuantityAdjustment> {
        let filters = self.fetch_spot_symbol_filters(symbol)?;
        Ok(adjust_spot_quantity_to_filters(
            &filters,
            quantity,
            estimated_price,
        ))
    }

    pub fn adjust_futures_quantity_to_filters(
        &self,
        symbol: impl AsRef<str>,
        quantity: f64,
        price: Option<f64>,
    ) -> Result<BinanceQuantityAdjustment> {
        let filters = self.fetch_futures_symbol_filters(symbol)?;
        Ok(adjust_futures_quantity_to_filters(
            &filters, quantity, price,
        ))
    }

    pub fn place_futures_market_order(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        side: impl AsRef<str>,
        quantity: f64,
        reduce_only: bool,
        position_side: impl AsRef<str>,
    ) -> Result<BinanceFuturesOrderResult> {
        self.require_futures_market()?;
        let order_params =
            build_futures_market_order_params(symbol, side, quantity, reduce_only, position_side)?;
        let mut request_params = order_params.params.clone();
        request_params.push(("newClientOrderId", new_binance_client_order_id()));
        execute_futures_order_with_fallback(self, credentials, &request_params, |payload| {
            parse_futures_order_result(
                payload,
                &order_params.symbol,
                &order_params.side,
                &order_params.position_side,
            )
        })
    }

    pub fn place_spot_market_order(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        side: impl AsRef<str>,
        quantity: f64,
    ) -> Result<BinanceSpotOrderResult> {
        self.require_spot_market()?;
        let order_params = build_spot_market_order_params(symbol, side, quantity)?;
        let mut request_params = order_params.params.clone();
        request_params.push(("newClientOrderId", new_binance_client_order_id()));
        let payload = self.signed_post_json(
            "/api/v3/order",
            credentials,
            &request_params,
            current_timestamp_ms()?,
            SPOT_ORDER_RECV_WINDOW_MS,
        )?;
        parse_spot_order_result(&payload, &order_params.symbol, &order_params.side)
    }

    // The public request mirrors Binance's independent order fields and the Python contract.
    #[allow(clippy::too_many_arguments)]
    pub fn place_futures_limit_order(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        side: impl AsRef<str>,
        quantity: f64,
        price: f64,
        reduce_only: bool,
        position_side: impl AsRef<str>,
        time_in_force: impl AsRef<str>,
    ) -> Result<BinanceFuturesOrderResult> {
        self.require_futures_market()?;
        let order_params = build_futures_limit_order_params(
            symbol,
            side,
            quantity,
            price,
            reduce_only,
            position_side,
            time_in_force,
        )?;
        let mut request_params = order_params.params.clone();
        request_params.push(("newClientOrderId", new_binance_client_order_id()));
        execute_futures_order_with_fallback(self, credentials, &request_params, |payload| {
            parse_futures_order_result(
                payload,
                &order_params.symbol,
                &order_params.side,
                &order_params.position_side,
            )
        })
    }

    pub fn fetch_open_futures_orders(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: Option<impl AsRef<str>>,
    ) -> Result<Vec<BinanceFuturesOpenOrder>> {
        self.require_futures_market()?;
        let requested_symbol = symbol
            .as_ref()
            .map(|value| normalize_symbol(value.as_ref()))
            .transpose()?;
        let mut params = Vec::new();
        if let Some(symbol) = requested_symbol.as_ref() {
            params.push(("symbol", symbol.clone()));
        }
        let payload = self.signed_get_json(
            &self.futures_v1_path("/openOrders"),
            credentials,
            &params,
            current_timestamp_ms()?,
        )?;
        parse_futures_open_orders(&payload, requested_symbol.as_deref())
    }

    pub fn cancel_all_open_futures_orders(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
    ) -> Result<BinanceFuturesCancelResult> {
        self.require_futures_market()?;
        let symbol = normalize_symbol(symbol.as_ref())?;
        let params = vec![("symbol", symbol.clone())];
        let payload = self.signed_delete_json(
            &self.futures_v1_path("/allOpenOrders"),
            credentials,
            &params,
            current_timestamp_ms()?,
            FUTURES_ORDER_RECV_WINDOW_MS,
        )?;
        parse_futures_cancel_result(&payload, &symbol, "")
    }

    pub fn cancel_futures_order(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        order_id: impl AsRef<str>,
    ) -> Result<BinanceFuturesCancelResult> {
        self.require_futures_market()?;
        let symbol = normalize_symbol(symbol.as_ref())?;
        let order_id = order_id.as_ref().trim().to_owned();
        if order_id.is_empty() {
            bail!("Order ID is required");
        }
        let params = vec![("symbol", symbol.clone()), ("orderId", order_id.clone())];
        let payload = self.signed_delete_json(
            &self.futures_v1_path("/order"),
            credentials,
            &params,
            current_timestamp_ms()?,
            FUTURES_ORDER_RECV_WINDOW_MS,
        )?;
        parse_futures_cancel_result(&payload, &symbol, &order_id)
    }

    pub fn fetch_futures_trades(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        order_id: Option<&str>,
        limit: usize,
    ) -> Result<Vec<BinanceFuturesTrade>> {
        self.require_futures_market()?;
        let symbol = normalize_symbol(symbol.as_ref())?;
        let limit = limit.clamp(1, 1_000).to_string();
        let mut params = vec![("symbol", symbol.clone()), ("limit", limit)];
        if let Some(order_id) = order_id.map(str::trim).filter(|value| !value.is_empty()) {
            params.push(("orderId", order_id.to_owned()));
        }
        let payload = self.signed_get_json(
            &self.futures_v1_path("/userTrades"),
            credentials,
            &params,
            current_timestamp_ms()?,
        )?;
        parse_futures_trades(&payload, &symbol)
    }

    pub fn fetch_futures_leverage_brackets(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: Option<&str>,
    ) -> Result<Vec<BinanceFuturesLeverageBracket>> {
        self.require_futures_market()?;
        let requested_symbol = symbol.map(normalize_symbol).transpose()?;
        let params = requested_symbol
            .as_ref()
            .map(|symbol| vec![("symbol", symbol.clone())])
            .unwrap_or_default();
        let payload = self.signed_get_json(
            &self.futures_v1_path("/leverageBracket"),
            credentials,
            &params,
            current_timestamp_ms()?,
        )?;
        parse_futures_leverage_brackets(&payload, requested_symbol.as_deref())
    }

    pub fn fetch_futures_max_leverage(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        fallback_max_leverage: i64,
    ) -> Result<i64> {
        self.require_futures_market()?;
        let configured_cap = fallback_max_leverage.max(1);
        let raw_symbol = symbol.as_ref().trim();
        if raw_symbol.is_empty() {
            return Ok(configured_cap);
        }
        let symbol = normalize_symbol(raw_symbol)?;
        if let Ok(brackets) = self.fetch_futures_leverage_brackets(credentials, Some(&symbol))
            && let Ok(maximum) = max_futures_leverage_from_brackets(&brackets, configured_cap)
        {
            return Ok(maximum);
        }
        let exchange_info_max = self
            .fetch_futures_symbol_filters(&symbol)
            .ok()
            .map(|filters| filters.max_leverage)
            .filter(|value| *value > 0)
            .unwrap_or(configured_cap);
        Ok(exchange_info_max.clamp(1, configured_cap))
    }

    pub fn fetch_futures_force_orders(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: Option<&str>,
        start_time_ms: Option<i64>,
        end_time_ms: Option<i64>,
        limit: usize,
    ) -> Result<Vec<BinanceFuturesForceOrder>> {
        self.require_futures_market()?;
        let requested_symbol = symbol.map(normalize_symbol).transpose()?;
        let mut params = Vec::new();
        if let Some(symbol) = requested_symbol.as_ref() {
            params.push(("symbol", symbol.clone()));
        }
        if let Some(start_time_ms) = start_time_ms.filter(|value| *value > 0) {
            params.push(("startTime", start_time_ms.to_string()));
        }
        if let Some(end_time_ms) = end_time_ms.filter(|value| *value > 0) {
            params.push(("endTime", end_time_ms.to_string()));
        }
        params.push(("limit", limit.clamp(1, 1_000).to_string()));
        let payload = self.signed_get_json(
            &self.futures_v1_path("/forceOrders"),
            credentials,
            &params,
            current_timestamp_ms()?,
        )?;
        parse_futures_force_orders(&payload, requested_symbol.as_deref())
    }

    pub fn fetch_spot_trades(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        limit: usize,
    ) -> Result<Vec<BinanceSpotTrade>> {
        self.require_spot_market()?;
        let symbol = normalize_symbol(symbol.as_ref())?;
        let params = vec![
            ("symbol", symbol.clone()),
            ("limit", limit.clamp(1, 1_000).to_string()),
        ];
        let payload = self.signed_get_json(
            "/api/v3/myTrades",
            credentials,
            &params,
            current_timestamp_ms()?,
        )?;
        parse_spot_trades(&payload, &symbol)
    }

    pub fn fetch_spot_position_cost(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        limit: usize,
    ) -> Result<Option<BinanceSpotPositionCost>> {
        self.require_spot_market()?;
        let symbol = normalize_symbol(symbol.as_ref())?;
        if !symbol.ends_with("USDT") {
            return Ok(None);
        }
        let trades = self.fetch_spot_trades(credentials, &symbol, limit)?;
        calculate_spot_position_cost(&symbol, &trades)
    }
}

fn execute_futures_order_with_fallback<T, F>(
    client: &BinanceSignedRestClient,
    credentials: &BinanceApiCredentials,
    params: &[(&str, String)],
    parse: F,
) -> Result<T>
where
    F: Fn(&Value) -> Result<T>,
{
    let submit = |candidate: &BinanceSignedRestClient| {
        candidate.signed_post_json(
            &candidate.futures_v1_path("/order"),
            credentials,
            params,
            current_timestamp_ms()?,
            FUTURES_ORDER_RECV_WINDOW_MS,
        )
    };

    let primary_payload = match submit(client) {
        Ok(payload) => payload,
        Err(primary_error) if client.futures_fallback_allowed() => {
            let fallback = client
                .alternate_futures_prefix_client()
                .map_err(|fallback_error| {
                    anyhow!("{primary_error}; fallback setup failed: {fallback_error}")
                })?;
            let fallback_payload = submit(&fallback).map_err(|fallback_error| {
                anyhow!("{primary_error}; fallback request failed: {fallback_error}")
            })?;
            return parse(&fallback_payload).map_err(|fallback_error| {
                anyhow!("{primary_error}; fallback response rejected: {fallback_error}")
            });
        }
        Err(error) => return Err(error),
    };

    match parse(&primary_payload) {
        Ok(result) => Ok(result),
        Err(primary_error) if client.futures_fallback_allowed() => {
            let fallback = client
                .alternate_futures_prefix_client()
                .map_err(|fallback_error| {
                    anyhow!("{primary_error}; fallback setup failed: {fallback_error}")
                })?;
            let fallback_payload = submit(&fallback).map_err(|fallback_error| {
                anyhow!("{primary_error}; fallback request failed: {fallback_error}")
            })?;
            parse(&fallback_payload).map_err(|fallback_error| {
                anyhow!("{primary_error}; fallback response rejected: {fallback_error}")
            })
        }
        Err(error) => Err(error),
    }
}

pub fn build_futures_market_order_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    quantity: f64,
    reduce_only: bool,
    position_side: impl AsRef<str>,
) -> Result<BinanceFuturesOrderParams> {
    let symbol = normalize_symbol(symbol.as_ref())?;
    let side = normalize_order_side(side.as_ref())?;
    validate_positive("Quantity", quantity)?;
    let position_side = normalize_position_side(position_side.as_ref());
    let has_directional_side = is_directional_position_side(&position_side);

    let mut params = vec![
        ("symbol", symbol.clone()),
        ("side", side.clone()),
        ("type", "MARKET".to_owned()),
        ("quantity", format_decimal_for_order(quantity, 8)),
    ];
    if reduce_only && !has_directional_side {
        params.push(("reduceOnly", "true".to_owned()));
    }
    if has_directional_side {
        params.push(("positionSide", position_side.clone()));
    }
    Ok(BinanceFuturesOrderParams {
        params,
        symbol,
        side,
        position_side,
    })
}

pub fn build_spot_market_order_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    quantity: f64,
) -> Result<BinanceSpotOrderParams> {
    let symbol = normalize_symbol(symbol.as_ref())?;
    let side = normalize_order_side(side.as_ref())?;
    validate_positive("Quantity", quantity)?;
    Ok(BinanceSpotOrderParams {
        params: vec![
            ("symbol", symbol.clone()),
            ("side", side.clone()),
            ("type", "MARKET".to_owned()),
            ("quantity", format_decimal_for_order(quantity, 8)),
        ],
        symbol,
        side,
        position_side: String::new(),
    })
}

pub fn build_futures_limit_order_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    quantity: f64,
    price: f64,
    reduce_only: bool,
    position_side: impl AsRef<str>,
    time_in_force: impl AsRef<str>,
) -> Result<BinanceFuturesOrderParams> {
    let symbol = normalize_symbol(symbol.as_ref())?;
    let side = normalize_order_side(side.as_ref())?;
    validate_positive("Quantity", quantity)?;
    validate_positive("Price", price)?;
    let position_side = normalize_position_side(position_side.as_ref());
    let has_directional_side = is_directional_position_side(&position_side);
    let time_in_force = normalize_time_in_force(time_in_force.as_ref());

    let mut params = vec![
        ("symbol", symbol.clone()),
        ("side", side.clone()),
        ("type", "LIMIT".to_owned()),
        ("timeInForce", time_in_force),
        ("quantity", format_decimal_for_order(quantity, 8)),
        ("price", format_decimal_for_order(price, 8)),
    ];
    if reduce_only && !has_directional_side {
        params.push(("reduceOnly", "true".to_owned()));
    }
    if has_directional_side {
        params.push(("positionSide", position_side.clone()));
    }
    Ok(BinanceFuturesOrderParams {
        params,
        symbol,
        side,
        position_side,
    })
}

pub fn parse_futures_symbol_filters(
    exchange_info: &Value,
    symbol: &str,
) -> Result<BinanceFuturesSymbolFilters> {
    ensure_not_binance_error(exchange_info)?;
    let clean_symbol = normalize_symbol(symbol)?;
    let rows = exchange_info
        .get("symbols")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("exchangeInfo response missing symbols array"))?;
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let current = row
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if current != clean_symbol {
            continue;
        }

        let mut result = BinanceFuturesSymbolFilters {
            symbol: clean_symbol,
            step_size: 0.0,
            tick_size: 0.0,
            min_qty: 0.0,
            max_qty: 0.0,
            min_notional: 0.0,
            quantity_precision: parse_json_i64(row.get("quantityPrecision"))
                .unwrap_or(0)
                .max(0),
            price_precision: parse_json_i64(row.get("pricePrecision"))
                .unwrap_or(0)
                .max(0),
            quote_asset_precision: parse_json_i64(row.get("quoteAssetPrecision"))
                .or_else(|| parse_json_i64(row.get("quotePrecision")))
                .unwrap_or(0)
                .max(0),
            max_leverage: parse_json_i64(row.get("maxLeverage"))
                .or_else(|| parse_json_i64(row.get("max_leverage")))
                .unwrap_or(0)
                .max(0),
        };
        let mut lot_step_size = 0.0;
        let mut lot_min_qty = 0.0;
        let mut lot_max_qty = 0.0;
        let mut market_step_size = 0.0;
        let mut market_min_qty = 0.0;
        let mut market_max_qty = 0.0;
        let mut price_tick_size = 0.0;

        for filter in row
            .get("filters")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let Some(filter) = filter.as_object() else {
                continue;
            };
            match filter
                .get("filterType")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase()
                .as_str()
            {
                "LOT_SIZE" => {
                    lot_step_size = first_f64(filter, &["stepSize"]).unwrap_or(0.0);
                    lot_min_qty = first_f64(filter, &["minQty"]).unwrap_or(0.0);
                    lot_max_qty = first_f64(filter, &["maxQty"]).unwrap_or(0.0);
                }
                "MARKET_LOT_SIZE" => {
                    market_step_size = first_f64(filter, &["stepSize"]).unwrap_or(0.0);
                    market_min_qty = first_f64(filter, &["minQty"]).unwrap_or(0.0);
                    market_max_qty = first_f64(filter, &["maxQty"]).unwrap_or(0.0);
                }
                "MIN_NOTIONAL" | "NOTIONAL" => {
                    result.min_notional =
                        first_f64(filter, &["notional", "minNotional"]).unwrap_or(0.0);
                }
                "PRICE_FILTER" => {
                    price_tick_size = first_f64(filter, &["tickSize"]).unwrap_or(0.0);
                }
                "LEVERAGE" => {
                    result.max_leverage = first_f64(filter, &["maxLeverage", "max_leverage"])
                        .map(|value| value.trunc() as i64)
                        .filter(|value| *value > 0)
                        .unwrap_or(result.max_leverage);
                }
                _ => {}
            }
        }

        result.step_size = positive_or_zero(if market_step_size > 0.0 {
            market_step_size
        } else {
            lot_step_size
        });
        result.tick_size = positive_or_zero(price_tick_size);
        result.min_qty = positive_or_zero(if market_min_qty > 0.0 {
            market_min_qty
        } else {
            lot_min_qty
        });
        result.max_qty = positive_or_zero(if market_max_qty > 0.0 {
            market_max_qty
        } else {
            lot_max_qty
        });
        result.min_notional = positive_or_zero(result.min_notional);
        return Ok(result);
    }

    bail!("Symbol {clean_symbol} not found in futures exchangeInfo")
}

pub fn parse_spot_symbol_filters(
    exchange_info: &Value,
    symbol: &str,
) -> Result<BinanceSpotSymbolFilters> {
    parse_futures_symbol_filters(exchange_info, symbol)
        .map_err(|error| anyhow!("spot exchangeInfo parse failed: {error}"))
}

pub fn parse_spot_symbol_metadata(
    exchange_info: &Value,
    symbol: &str,
) -> Result<BinanceSpotSymbolMetadata> {
    ensure_not_binance_error(exchange_info)?;
    let clean_symbol = normalize_symbol(symbol)?;
    let rows = exchange_info
        .get("symbols")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("spot exchangeInfo response missing symbols array"))?;
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let current = row
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if current != clean_symbol {
            continue;
        }
        return Ok(BinanceSpotSymbolMetadata {
            symbol: clean_symbol.clone(),
            status: row
                .get("status")
                .and_then(Value::as_str)
                .unwrap_or("TRADING")
                .trim()
                .to_uppercase(),
            base_asset: row
                .get("baseAsset")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            quote_asset: row
                .get("quoteAsset")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            filters: parse_spot_symbol_filters(exchange_info, &clean_symbol)?,
        });
    }
    bail!("Symbol {clean_symbol} not found in spot exchangeInfo")
}

pub fn parse_futures_order_result(
    payload: &Value,
    fallback_symbol: &str,
    fallback_side: &str,
    fallback_position_side: &str,
) -> Result<BinanceFuturesOrderResult> {
    let obj = normalized_binance_order_object(payload)?;
    let order_id = [
        "orderId",
        "order_id",
        "id",
        "clientOrderId",
        "client_order_id",
        "clientOrderID",
    ]
    .iter()
    .find_map(|key| json_value_to_string(obj.get(*key)))
    .unwrap_or_default();
    if order_id.trim().is_empty() {
        bail!("futures order response missing orderId/order identifier");
    }
    let status = json_value_to_string(obj.get("status"))
        .unwrap_or_default()
        .trim()
        .to_uppercase();
    if status.is_empty() {
        bail!("futures order response missing explicit status");
    }
    if matches!(
        status.as_str(),
        "REJECTED" | "EXPIRED" | "EXPIRED_IN_MATCH" | "CANCELED"
    ) {
        bail!("futures order response has terminal failure status {status}");
    }
    let avg_price = first_f64(obj, &["avgPrice"])
        .filter(|value| *value > 0.0)
        .or_else(|| first_f64(obj, &["price"]))
        .unwrap_or(0.0);
    let executed_qty = first_f64(obj, &["executedQty"])
        .filter(|value| *value > 0.0)
        .or_else(|| first_f64(obj, &["origQty"]))
        .unwrap_or(0.0);
    Ok(BinanceFuturesOrderResult {
        symbol: obj
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or(fallback_symbol)
            .trim()
            .to_uppercase(),
        side: obj
            .get("side")
            .and_then(Value::as_str)
            .unwrap_or(fallback_side)
            .trim()
            .to_uppercase(),
        position_side: obj
            .get("positionSide")
            .and_then(Value::as_str)
            .unwrap_or(fallback_position_side)
            .trim()
            .to_uppercase(),
        order_id,
        status,
        executed_qty,
        avg_price,
    })
}

pub fn parse_futures_open_orders(
    payload: &Value,
    requested_symbol: Option<&str>,
) -> Result<Vec<BinanceFuturesOpenOrder>> {
    ensure_not_binance_error(payload)?;
    let requested_symbol = requested_symbol.map(normalize_symbol).transpose()?;
    let rows = if let Some(rows) = payload.as_array() {
        rows
    } else if let Some(object) = payload.as_object() {
        object
            .get("orders")
            .or_else(|| object.get("data"))
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow!("futures open-orders response missing orders array"))?
    } else {
        bail!("futures open-orders response must be an array or object")
    };

    let mut orders = Vec::with_capacity(rows.len());
    for value in rows {
        let object = value
            .as_object()
            .ok_or_else(|| anyhow!("futures open-orders response contained a malformed row"))?;
        let symbol = object
            .get("symbol")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_uppercase)
            .ok_or_else(|| anyhow!("futures open-order row is missing symbol"))?;
        let order_id = json_value_to_string(object.get("orderId"))
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| anyhow!("futures open-order row is missing orderId"))?;
        let order = BinanceFuturesOpenOrder {
            symbol: symbol.clone(),
            order_id,
            client_order_id: object
                .get("clientOrderId")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_owned(),
            status: object
                .get("status")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            side: object
                .get("side")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            order_type: object
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            position_side: object
                .get("positionSide")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            orig_qty: first_f64(object, &["origQty"]).unwrap_or(0.0),
            executed_qty: first_f64(object, &["executedQty"]).unwrap_or(0.0),
            price: first_f64(object, &["price"]).unwrap_or(0.0),
        };
        if requested_symbol
            .as_deref()
            .is_none_or(|requested| requested == symbol)
        {
            orders.push(order);
        }
    }
    Ok(orders)
}

pub fn parse_futures_cancel_result(
    payload: &Value,
    fallback_symbol: &str,
    fallback_order_id: &str,
) -> Result<BinanceFuturesCancelResult> {
    let object = payload
        .as_object()
        .ok_or_else(|| anyhow!("futures cancel response must be an object"))?;
    if let Some(code_value) = object.get("code") {
        let code = parse_json_i64(Some(code_value))
            .ok_or_else(|| anyhow!("futures cancel response has an invalid code"))?;
        if !matches!(code, 0 | 200 | 20_000) {
            let message = object
                .get("msg")
                .and_then(Value::as_str)
                .unwrap_or("Binance cancel request failed");
            bail!("{message}");
        }
    }
    let symbol = object
        .get("symbol")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(fallback_symbol);
    let symbol = normalize_symbol(symbol)?;
    let order_id = json_value_to_string(object.get("orderId"))
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| fallback_order_id.trim().to_owned());
    let status = object
        .get("status")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_uppercase)
        .unwrap_or_else(|| "CANCELED".to_owned());
    Ok(BinanceFuturesCancelResult {
        symbol,
        order_id,
        status,
    })
}

pub fn parse_futures_trades(
    payload: &Value,
    requested_symbol: &str,
) -> Result<Vec<BinanceFuturesTrade>> {
    ensure_not_binance_error(payload)?;
    let requested_symbol = normalize_symbol(requested_symbol)?;
    let rows = if let Some(rows) = payload.as_array() {
        rows
    } else if let Some(object) = payload.as_object() {
        object
            .get("trades")
            .or_else(|| object.get("data"))
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow!("futures trade response missing trades array"))?
    } else {
        bail!("futures trade response must be an array or object")
    };

    let mut trades = Vec::with_capacity(rows.len());
    for value in rows {
        let object = value
            .as_object()
            .ok_or_else(|| anyhow!("futures trade response contained a malformed row"))?;
        let row_symbol = object
            .get("symbol")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_uppercase)
            .unwrap_or_else(|| requested_symbol.clone());
        if row_symbol != requested_symbol {
            continue;
        }
        let order_id = json_value_to_string(object.get("orderId"))
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| anyhow!("futures trade row is missing orderId"))?;
        let price = first_f64(object, &["price"]).unwrap_or(0.0);
        let quantity = first_f64(object, &["qty", "quantity"]).unwrap_or(0.0);
        let quote_quantity = first_f64(object, &["quoteQty"])
            .filter(|value| value.is_finite() && *value > 0.0)
            .unwrap_or_else(|| price * quantity);
        trades.push(BinanceFuturesTrade {
            symbol: row_symbol,
            trade_id: json_value_to_string(object.get("id"))
                .or_else(|| json_value_to_string(object.get("tradeId")))
                .unwrap_or_default(),
            order_id,
            price,
            quantity,
            quote_quantity,
            realized_pnl: first_f64(object, &["realizedPnl"]).unwrap_or(0.0),
            commission: first_f64(object, &["commission"]).unwrap_or(0.0),
            commission_asset: object
                .get("commissionAsset")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase(),
            time_ms: parse_json_i64(object.get("time"))
                .or_else(|| parse_json_i64(object.get("T")))
                .unwrap_or(0),
        });
    }
    Ok(trades)
}

pub fn parse_futures_leverage_brackets(
    payload: &Value,
    requested_symbol: Option<&str>,
) -> Result<Vec<BinanceFuturesLeverageBracket>> {
    ensure_not_binance_error(payload)?;
    let requested_symbol = requested_symbol.map(normalize_symbol).transpose()?;
    let records = if let Some(records) = payload.as_array() {
        records
    } else if let Some(object) = payload.as_object() {
        if let Some(records) = object.get("data").and_then(Value::as_array) {
            records
        } else {
            std::slice::from_ref(payload)
        }
    } else {
        bail!("futures leverage-bracket response must be an array or object")
    };

    let mut brackets = Vec::new();
    for record_value in records {
        let record = record_value.as_object().ok_or_else(|| {
            anyhow!("futures leverage-bracket response contained a malformed record")
        })?;
        let record_symbol = record
            .get("symbol")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_uppercase)
            .or_else(|| requested_symbol.clone())
            .unwrap_or_default();
        if requested_symbol
            .as_deref()
            .is_some_and(|requested| !record_symbol.is_empty() && requested != record_symbol)
        {
            continue;
        }
        let bracket_rows = record
            .get("brackets")
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow!("futures leverage-bracket record missing brackets array"))?;
        for bracket_value in bracket_rows {
            let bracket = bracket_value
                .as_object()
                .ok_or_else(|| anyhow!("futures leverage-bracket row is malformed"))?;
            let initial_leverage = parse_json_i64(bracket.get("initialLeverage"))
                .filter(|value| *value > 0)
                .ok_or_else(|| anyhow!("futures leverage-bracket row missing initialLeverage"))?;
            brackets.push(BinanceFuturesLeverageBracket {
                symbol: record_symbol.clone(),
                initial_leverage,
                notional_cap: first_f64(bracket, &["notionalCap"]).unwrap_or(0.0),
                notional_floor: first_f64(bracket, &["notionalFloor"]).unwrap_or(0.0),
                maint_margin_ratio: first_f64(bracket, &["maintMarginRatio"]).unwrap_or(0.0),
                cum: first_f64(bracket, &["cum"]).unwrap_or(0.0),
            });
        }
    }
    if brackets.is_empty() {
        bail!("futures leverage-bracket response contained no valid brackets");
    }
    Ok(brackets)
}

pub fn max_futures_leverage_from_brackets(
    brackets: &[BinanceFuturesLeverageBracket],
    fallback_max_leverage: i64,
) -> Result<i64> {
    let configured_cap = fallback_max_leverage.max(1);
    let maximum = brackets
        .iter()
        .map(|bracket| bracket.initial_leverage)
        .filter(|value| *value > 0)
        .max()
        .ok_or_else(|| anyhow!("futures leverage-bracket response contained no usable leverage"))?;
    Ok(maximum.min(configured_cap))
}

pub fn clamp_futures_leverage(
    requested_leverage: Option<f64>,
    configured_max_leverage: i64,
    symbol_max_leverage: Option<i64>,
    futures_account: bool,
) -> i64 {
    let configured_cap = configured_max_leverage.max(1);
    let desired = match requested_leverage {
        None => 5,
        Some(value) if value.is_finite() => value.trunc() as i64,
        Some(_) => 1,
    }
    .max(1)
    .min(configured_cap);
    if !futures_account {
        return desired;
    }
    let symbol_cap = symbol_max_leverage
        .filter(|value| *value > 0)
        .unwrap_or(configured_cap)
        .clamp(1, configured_cap);
    desired.min(symbol_cap)
}

pub fn parse_futures_force_orders(
    payload: &Value,
    requested_symbol: Option<&str>,
) -> Result<Vec<BinanceFuturesForceOrder>> {
    ensure_not_binance_error(payload)?;
    let requested_symbol = requested_symbol.map(normalize_symbol).transpose()?;
    let rows = if let Some(rows) = payload.as_array() {
        rows
    } else if let Some(object) = payload.as_object() {
        ["rows", "data", "forceOrders", "orders", "list"]
            .iter()
            .find_map(|key| object.get(*key).and_then(Value::as_array))
            .ok_or_else(|| anyhow!("futures force-order response missing rows array"))?
    } else {
        bail!("futures force-order response must be an array or object")
    };

    let mut orders = Vec::with_capacity(rows.len());
    for value in rows {
        let Some(object) = value.as_object() else {
            continue;
        };
        let row_symbol = object
            .get("symbol")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_uppercase)
            .or_else(|| requested_symbol.clone())
            .unwrap_or_default();
        if requested_symbol
            .as_deref()
            .is_some_and(|requested| requested != row_symbol)
        {
            continue;
        }
        orders.push(BinanceFuturesForceOrder {
            symbol: row_symbol,
            order_id: json_value_to_string(object.get("orderId")).unwrap_or_default(),
            side: upper_string(object, "side"),
            position_side: upper_string(object, "positionSide"),
            status: upper_string(object, "status"),
            order_type: upper_string(object, "type"),
            avg_price: first_f64(object, &["avgPrice"]).unwrap_or(0.0),
            executed_qty: first_f64(object, &["executedQty"]).unwrap_or(0.0),
            orig_qty: first_f64(object, &["origQty"]).unwrap_or(0.0),
            price: first_f64(object, &["price"]).unwrap_or(0.0),
            time_ms: parse_json_i64(object.get("time")).unwrap_or(0),
            update_time_ms: parse_json_i64(object.get("updateTime")).unwrap_or(0),
        });
    }
    Ok(orders)
}

pub fn parse_spot_trades(payload: &Value, requested_symbol: &str) -> Result<Vec<BinanceSpotTrade>> {
    ensure_not_binance_error(payload)?;
    let requested_symbol = normalize_symbol(requested_symbol)?;
    let rows = if let Some(rows) = payload.as_array() {
        rows
    } else if let Some(object) = payload.as_object() {
        ["data", "rows", "trades"]
            .iter()
            .find_map(|key| object.get(*key).and_then(Value::as_array))
            .ok_or_else(|| anyhow!("spot trade response missing trades array"))?
    } else {
        bail!("spot trade response must be an array or object")
    };

    let mut trades = Vec::with_capacity(rows.len());
    for value in rows {
        let Some(object) = value.as_object() else {
            continue;
        };
        let row_symbol = object
            .get("symbol")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_uppercase)
            .unwrap_or_else(|| requested_symbol.clone());
        if row_symbol != requested_symbol {
            continue;
        }
        let price = first_f64(object, &["price"]).unwrap_or(0.0);
        let quantity = first_f64(object, &["qty", "executedQty"]).unwrap_or(0.0);
        trades.push(BinanceSpotTrade {
            symbol: row_symbol,
            trade_id: json_value_to_string(object.get("id"))
                .or_else(|| json_value_to_string(object.get("tradeId")))
                .unwrap_or_default(),
            order_id: json_value_to_string(object.get("orderId")).unwrap_or_default(),
            price,
            quantity,
            quote_quantity: first_f64(object, &["quoteQty"])
                .filter(|value| value.is_finite() && *value >= 0.0)
                .unwrap_or_else(|| price * quantity),
            commission: first_f64(object, &["commission"]).unwrap_or(0.0),
            commission_asset: upper_string(object, "commissionAsset"),
            is_buyer: coerce_bool_value(object.get("isBuyer")),
            is_maker: coerce_bool_value(object.get("isMaker")),
            is_best_match: coerce_bool_value(object.get("isBestMatch")),
            time_ms: parse_json_i64(object.get("time")).unwrap_or(0),
        });
    }
    Ok(trades)
}

pub fn calculate_spot_position_cost(
    symbol: &str,
    trades: &[BinanceSpotTrade],
) -> Result<Option<BinanceSpotPositionCost>> {
    let symbol = normalize_symbol(symbol)?;
    let mut quantity = 0.0;
    let mut cost = 0.0;
    for trade in trades {
        if trade.symbol != symbol
            || !trade.price.is_finite()
            || trade.price < 0.0
            || !trade.quantity.is_finite()
            || trade.quantity < 0.0
            || !trade.quote_quantity.is_finite()
            || trade.quote_quantity < 0.0
        {
            bail!("spot trade history contained invalid cost-basis data")
        }
        if trade.is_buyer {
            quantity += trade.quantity;
            cost += trade.quote_quantity;
        } else {
            quantity -= trade.quantity;
            cost -= trade.quote_quantity;
        }
    }
    if quantity <= 0.0 || cost <= 0.0 {
        return Ok(None);
    }
    Ok(Some(BinanceSpotPositionCost {
        symbol,
        quantity,
        cost,
    }))
}

pub fn parse_spot_order_result(
    payload: &Value,
    fallback_symbol: &str,
    fallback_side: &str,
) -> Result<BinanceSpotOrderResult> {
    let result = parse_futures_order_result(payload, fallback_symbol, fallback_side, "")?;
    if result.order_id.trim().is_empty() {
        bail!("spot order response missing orderId");
    }
    if result.status.trim().is_empty() {
        bail!("spot order response missing explicit status");
    }
    if matches!(result.status.as_str(), "REJECTED" | "EXPIRED" | "CANCELED") {
        bail!(
            "spot order response has terminal failure status {}",
            result.status
        );
    }
    Ok(result)
}

pub fn futures_order_recv_window_ms() -> u64 {
    FUTURES_ORDER_RECV_WINDOW_MS
}

pub fn format_decimal_for_order(value: f64, precision_hint: usize) -> String {
    let precision = precision_hint.min(16);
    let mut text = format!("{value:.precision$}");
    while text.contains('.') && (text.ends_with('0') || text.ends_with('.')) {
        text.pop();
    }
    if text.is_empty() {
        "0".to_owned()
    } else {
        text
    }
}

pub fn floor_to_step(value: f64, step: f64) -> f64 {
    if step <= 0.0 || !value.is_finite() || !step.is_finite() {
        return value;
    }
    (value / step).trunc() * step
}

pub fn ceil_to_step(value: f64, step: f64) -> f64 {
    if step <= 0.0 || !value.is_finite() || !step.is_finite() {
        return value;
    }
    (value / step).ceil() * step
}

pub fn floor_to_decimals(value: f64, decimals: i32) -> f64 {
    if decimals < 0 || !value.is_finite() {
        return value;
    }
    let scale = 10_f64.powi(decimals);
    if !scale.is_finite() || scale <= 0.0 {
        return value;
    }
    (value * scale).trunc() / scale
}

pub fn ceil_to_decimals(value: f64, decimals: i32) -> f64 {
    if decimals < 0 || !value.is_finite() {
        return value;
    }
    let scale = 10_f64.powi(decimals);
    if !scale.is_finite() || scale <= 0.0 {
        return value;
    }
    let scaled = value * scale;
    // Python's Decimal(ROUND_UP) rounds away from zero for negative values.
    if value < 0.0 {
        scaled.floor() / scale
    } else {
        scaled.ceil() / scale
    }
}

pub fn adjust_spot_quantity_to_filters(
    filters: &BinanceSpotSymbolFilters,
    quantity: f64,
    estimated_price: f64,
) -> BinanceQuantityAdjustment {
    if !quantity.is_finite() {
        return failed_quantity_adjustment("qty must be a finite number");
    }
    if quantity <= 0.0 {
        return failed_quantity_adjustment("qty<=0");
    }
    if !estimated_price.is_finite() {
        return failed_quantity_adjustment("price must be a finite number");
    }
    if let Some(error) = validate_quantity_filters(filters) {
        return failed_quantity_adjustment(&error);
    }

    let mut adjusted = quantity;
    if filters.step_size > 0.0 {
        adjusted = floor_to_step(adjusted, filters.step_size);
    }
    if filters.min_qty > 0.0 && adjusted < filters.min_qty {
        adjusted = filters.min_qty;
    }
    if filters.min_notional > 0.0 && estimated_price > 0.0 {
        let mut needed = filters.min_notional / estimated_price;
        if filters.step_size > 0.0 {
            needed = ceil_to_step(needed, filters.step_size);
        }
        if filters.min_qty > 0.0 {
            needed = needed.max(filters.min_qty);
        }
        if adjusted < needed {
            adjusted = needed;
        }
    }
    if estimated_price > 0.0
        && filters.min_notional > 0.0
        && adjusted * estimated_price < filters.min_notional
    {
        let mut needed = filters.min_notional / estimated_price;
        if filters.step_size > 0.0 {
            needed = floor_to_step(needed + filters.step_size, filters.step_size);
        }
        if needed < filters.min_qty {
            needed = filters.min_qty;
            if filters.step_size > 0.0 {
                needed = floor_to_step(needed, filters.step_size);
            }
        }
        adjusted = needed;
        if adjusted * estimated_price < filters.min_notional {
            return failed_quantity_adjustment(&format!(
                "below_minNotional({adjusted:.8}<{:.8})",
                filters.min_notional
            ));
        }
    }
    if !adjusted.is_finite() || adjusted <= 0.0 {
        return failed_quantity_adjustment("adj<=0");
    }
    BinanceQuantityAdjustment {
        ok: true,
        quantity: adjusted,
        error: None,
    }
}

pub fn adjust_futures_quantity_to_filters(
    filters: &BinanceFuturesSymbolFilters,
    quantity: f64,
    price: Option<f64>,
) -> BinanceQuantityAdjustment {
    if !quantity.is_finite() {
        return failed_quantity_adjustment("qty must be a finite number");
    }
    let normalized_price = price.unwrap_or(0.0);
    if !normalized_price.is_finite() {
        return failed_quantity_adjustment("price must be a finite number");
    }
    if let Some(error) = validate_quantity_filters(filters) {
        return failed_quantity_adjustment(&error);
    }

    let mut adjusted = quantity;
    if filters.step_size > 0.0 {
        adjusted = floor_to_step(adjusted, filters.step_size);
    }
    if filters.min_qty > 0.0 && adjusted < filters.min_qty {
        adjusted = filters.min_qty;
    }
    if filters.min_notional > 0.0 && normalized_price > 0.0 {
        let mut needed = filters.min_notional / normalized_price;
        if filters.step_size > 0.0 {
            needed = ceil_to_step(needed, filters.step_size);
        }
        if adjusted < needed {
            adjusted = needed;
        }
    }
    if !adjusted.is_finite() || adjusted <= 0.0 {
        return failed_quantity_adjustment("adj<=0");
    }
    BinanceQuantityAdjustment {
        ok: true,
        quantity: adjusted,
        error: None,
    }
}

pub fn required_percent_for_symbol(
    price: f64,
    filters: &BinanceFuturesSymbolFilters,
    futures_balance: f64,
    leverage: f64,
) -> f64 {
    if !price.is_finite()
        || price <= 0.0
        || !futures_balance.is_finite()
        || futures_balance <= 0.0
        || !leverage.is_finite()
        || leverage <= 0.0
    {
        return 0.0;
    }
    let step = if filters.step_size.is_finite() && filters.step_size > 0.0 {
        filters.step_size
    } else {
        0.001
    };
    let min_qty = if filters.min_qty.is_finite() && filters.min_qty > 0.0 {
        filters.min_qty
    } else {
        step
    };
    let min_notional = if filters.min_notional.is_finite() && filters.min_notional > 0.0 {
        filters.min_notional
    } else {
        5.0
    };
    let mut needed_qty = min_qty.max(min_notional / price);
    let units = (needed_qty / step).trunc();
    if (needed_qty - units * step).abs() > 1e-12 {
        needed_qty = (units + 1.0) * step;
    }
    if !needed_qty.is_finite() || needed_qty <= 0.0 {
        return 0.0;
    }
    let required = ((needed_qty * price) / leverage / futures_balance) * 100.0;
    if required.is_finite() { required } else { 0.0 }
}

fn failed_quantity_adjustment(error: &str) -> BinanceQuantityAdjustment {
    BinanceQuantityAdjustment {
        ok: false,
        quantity: 0.0,
        error: Some(error.to_owned()),
    }
}

fn validate_quantity_filters(filters: &BinanceFuturesSymbolFilters) -> Option<String> {
    for (name, value) in [
        ("stepSize", filters.step_size),
        ("minQty", filters.min_qty),
        ("minNotional", filters.min_notional),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Some(format!(
                "filters_error: {name} must be a finite non-negative number"
            ));
        }
    }
    None
}

fn normalize_symbol(value: &str) -> Result<String> {
    let symbol = value.trim().to_uppercase();
    if symbol.is_empty() {
        bail!("Symbol is required");
    }
    Ok(symbol)
}

fn normalize_order_side(value: &str) -> Result<String> {
    match value.trim().to_uppercase().as_str() {
        "BUY" | "LONG" | "L" => Ok("BUY".to_owned()),
        "SELL" | "SHORT" | "S" => Ok("SELL".to_owned()),
        _ => bail!("Side must be BUY or SELL"),
    }
}

fn normalize_position_side(value: &str) -> String {
    value.trim().to_uppercase()
}

fn normalize_time_in_force(value: &str) -> String {
    let normalized = value.trim().to_uppercase();
    if normalized.is_empty() {
        "IOC".to_owned()
    } else {
        normalized
    }
}

fn is_directional_position_side(value: &str) -> bool {
    matches!(value.trim().to_uppercase().as_str(), "LONG" | "SHORT")
}

fn validate_positive(label: &str, value: f64) -> Result<()> {
    if !value.is_finite() || value <= 0.0 {
        bail!("{label} must be > 0");
    }
    Ok(())
}

fn first_f64(row: &Map<String, Value>, keys: &[&str]) -> Option<f64> {
    for key in keys {
        if let Some(value) = parse_json_f64(row.get(*key)).filter(|value| value.is_finite()) {
            return Some(value);
        }
    }
    None
}

fn parse_json_f64(value: Option<&Value>) -> Option<f64> {
    match value? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.trim().parse::<f64>().ok(),
        _ => None,
    }
}

fn parse_json_i64(value: Option<&Value>) -> Option<i64> {
    match value? {
        Value::Number(number) => number.as_i64(),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn json_value_to_string(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::Number(number) => Some(number.to_string()),
        Value::String(text) => Some(text.trim().to_owned()),
        _ => None,
    }
}

fn upper_string(row: &Map<String, Value>, key: &str) -> String {
    row.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_uppercase()
}

fn coerce_bool_value(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number.as_f64().is_some_and(|value| value != 0.0),
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(values)) => !values.is_empty(),
        Some(Value::Object(values)) => !values.is_empty(),
    }
}

fn positive_or_zero(value: f64) -> f64 {
    if value.is_finite() && value > 0.0 {
        value
    } else {
        0.0
    }
}

fn ensure_not_binance_error(value: &Value) -> Result<()> {
    let Some(obj) = value.as_object() else {
        return Ok(());
    };
    if obj.contains_key("code") && obj.contains_key("msg") {
        let message = obj
            .get("msg")
            .and_then(Value::as_str)
            .unwrap_or("Binance API error");
        bail!("{message}");
    }
    Ok(())
}

fn is_binance_order_error_object(obj: &Map<String, Value>) -> bool {
    let Some(code) = parse_json_i64(obj.get("code")) else {
        return false;
    };
    code != 0 && (obj.contains_key("msg") || obj.contains_key("message"))
}

fn binance_order_error_message(obj: &Map<String, Value>) -> String {
    obj.get("msg")
        .or_else(|| obj.get("message"))
        .and_then(Value::as_str)
        .unwrap_or("unknown")
        .to_owned()
}

fn normalized_binance_order_object(payload: &Value) -> Result<&Map<String, Value>> {
    let obj = payload
        .as_object()
        .ok_or_else(|| anyhow!("futures order response must be an object"))?;

    if is_binance_order_error_object(obj) {
        bail!("Binance order error: {}", binance_order_error_message(obj));
    }
    if let Some(error) = obj.get("error").and_then(Value::as_object) {
        if is_binance_order_error_object(error) {
            bail!(
                "Binance order error: {}",
                binance_order_error_message(error)
            );
        }
    }

    let success_rejected = match obj.get("success") {
        Some(Value::Bool(value)) => !*value,
        Some(Value::String(text)) => !matches!(
            text.trim().to_ascii_lowercase().as_str(),
            "true" | "1" | "yes"
        ),
        _ => false,
    };
    if success_rejected {
        let message = obj
            .get("msg")
            .or_else(|| obj.get("message"))
            .and_then(Value::as_str)
            .unwrap_or("order rejected");
        bail!("Binance order rejected: {message}");
    }

    let normalized = obj
        .get("data")
        .and_then(Value::as_object)
        .filter(|data| !data.is_empty())
        .unwrap_or(obj);
    if is_binance_order_error_object(normalized) {
        bail!(
            "Binance order error: {}",
            binance_order_error_message(normalized)
        );
    }
    Ok(normalized)
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::thread;

    use serde_json::json;

    use crate::account::{BinanceApiCredentials, signed_query_string};
    use crate::market_data::BinanceMarket;

    use super::*;

    #[test]
    fn parses_futures_symbol_filters_like_cpp_preferring_market_lot_size() {
        let payload = json!({
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "quantityPrecision": 3,
                    "pricePrecision": 2,
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "100"},
                        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.01", "minQty": "0.02", "maxQty": "50"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        {"filterType": "LEVERAGE", "maxLeverage": "50"}
                    ]
                }
            ]
        });
        let filters = parse_futures_symbol_filters(&payload, "btcusdt").expect("filters");
        assert_eq!(filters.symbol, "BTCUSDT");
        assert_eq!(filters.step_size, 0.01);
        assert_eq!(filters.min_qty, 0.02);
        assert_eq!(filters.max_qty, 50.0);
        assert_eq!(filters.tick_size, 0.10);
        assert_eq!(filters.min_notional, 5.0);
        assert_eq!(filters.max_leverage, 50);
        assert_eq!(filters.quantity_precision, 3);
        assert_eq!(filters.price_precision, 2);
    }

    #[test]
    fn quantity_adjustment_helpers_match_python_filter_sizing() {
        let fixture: Value = serde_json::from_str(
            crate::generated_python_parity::PYTHON_ORDER_SIZING_REFERENCE_JSON,
        )
        .expect("generated Python order-sizing fixture");
        assert_eq!(fixture["schema_version"].as_i64(), Some(1));
        let cases = fixture["cases"].as_array().expect("fixture cases");
        assert!(cases.len() >= 5);
        for case in cases {
            let filters_value = case["filters"].as_object().expect("fixture filters");
            let filters = BinanceFuturesSymbolFilters {
                symbol: "BTCUSDT".to_owned(),
                step_size: filters_value["stepSize"].as_f64().expect("step size"),
                tick_size: 0.1,
                min_qty: filters_value["minQty"].as_f64().expect("min qty"),
                max_qty: 50.0,
                min_notional: filters_value["minNotional"].as_f64().expect("min notional"),
                quantity_precision: 3,
                price_precision: 2,
                quote_asset_precision: 8,
                max_leverage: 125,
            };
            let case_name = case["name"].as_str().expect("case name");
            if let Some(expected_percent) = case.get("expected_percent").and_then(Value::as_f64) {
                let actual = required_percent_for_symbol(
                    case["price"].as_f64().expect("price"),
                    &filters,
                    case["balance"].as_f64().expect("balance"),
                    case["leverage"].as_f64().expect("leverage"),
                );
                assert!((actual - expected_percent).abs() < 1e-12, "{case_name}");
                continue;
            }
            let adjustment = if case["market"].as_str() == Some("spot") {
                adjust_spot_quantity_to_filters(
                    &filters,
                    case["quantity"].as_f64().expect("quantity"),
                    case["price"].as_f64().expect("price"),
                )
            } else {
                adjust_futures_quantity_to_filters(
                    &filters,
                    case["quantity"].as_f64().expect("quantity"),
                    Some(case["price"].as_f64().expect("price")),
                )
            };
            let expected_error = case["expected_error"].as_str();
            assert_eq!(adjustment.ok, expected_error.is_none(), "{case_name}");
            assert_eq!(adjustment.error.as_deref(), expected_error, "{case_name}");
            assert!(
                (adjustment.quantity
                    - case["expected_quantity"]
                        .as_f64()
                        .expect("expected quantity"))
                .abs()
                    < 1e-12,
                "{case_name}"
            );
        }

        assert!((floor_to_step(1.239, 0.01) - 1.23).abs() < 1e-12);
        assert!((ceil_to_step(1.231, 0.01) - 1.24).abs() < 1e-12);
        assert!((floor_to_decimals(1.239, 2) - 1.23).abs() < 1e-12);
        assert!((ceil_to_decimals(1.231, 2) - 1.24).abs() < 1e-12);
        let rounding_cases = fixture["rounding_cases"]
            .as_array()
            .expect("rounding fixture cases");
        assert!(rounding_cases.len() >= 3);
        for case in rounding_cases {
            let value = case["value"].as_f64().expect("rounding value");
            let decimals = case["decimals"].as_i64().expect("rounding decimals") as i32;
            let name = case["name"].as_str().expect("rounding case name");
            assert!(
                (floor_to_decimals(value, decimals)
                    - case["expected_floor"].as_f64().expect("expected floor"))
                .abs()
                    < 1e-12,
                "{name} floor"
            );
            assert!(
                (ceil_to_decimals(value, decimals)
                    - case["expected_ceil"].as_f64().expect("expected ceil"))
                .abs()
                    < 1e-12,
                "{name} ceil"
            );
        }
    }

    #[test]
    fn quantity_adjustment_helpers_fail_closed_for_invalid_inputs() {
        let filters = BinanceFuturesSymbolFilters {
            symbol: "BTCUSDT".to_owned(),
            step_size: 0.01,
            tick_size: 0.1,
            min_qty: 0.02,
            max_qty: 50.0,
            min_notional: 5.0,
            quantity_precision: 3,
            price_precision: 2,
            quote_asset_precision: 8,
            max_leverage: 125,
        };
        let invalid_qty = adjust_spot_quantity_to_filters(&filters, f64::NAN, 100.0);
        assert!(!invalid_qty.ok);
        assert_eq!(
            invalid_qty.error.as_deref(),
            Some("qty must be a finite number")
        );
        let invalid_filter = BinanceFuturesSymbolFilters {
            step_size: f64::NAN,
            ..filters
        };
        let result = adjust_futures_quantity_to_filters(&invalid_filter, 1.0, Some(100.0));
        assert!(!result.ok);
        assert!(
            result
                .error
                .as_deref()
                .is_some_and(|error| error.contains("stepSize"))
        );
    }

    #[test]
    fn market_order_params_match_python_and_cpp_reduce_only_hedge_rules() {
        let one_way = build_futures_market_order_params("ethusdt", "long", 0.123400, true, "BOTH")
            .expect("one-way params");
        assert_eq!(
            one_way.params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "BUY".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "0.1234".to_owned()),
                ("reduceOnly", "true".to_owned()),
            ]
        );

        let hedge = build_futures_market_order_params("ethusdt", "SELL", 2.0, true, "SHORT")
            .expect("hedge params");
        assert_eq!(
            hedge.params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "2".to_owned()),
                ("positionSide", "SHORT".to_owned()),
            ]
        );
    }

    #[test]
    fn spot_market_order_params_match_python_without_futures_only_fields() {
        let order =
            build_spot_market_order_params("ethusdt", "buy", 0.123400).expect("spot params");
        assert_eq!(
            order.params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "BUY".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "0.1234".to_owned()),
            ]
        );
        assert!(order.position_side.is_empty());
    }

    #[test]
    fn limit_order_params_default_ioc_and_format_decimal_values() {
        let order = build_futures_limit_order_params(
            "btcusdt",
            "sell",
            1.250000,
            20123.450000,
            false,
            "",
            "",
        )
        .expect("limit params");
        assert_eq!(
            order.params,
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "LIMIT".to_owned()),
                ("timeInForce", "IOC".to_owned()),
                ("quantity", "1.25".to_owned()),
                ("price", "20123.45".to_owned()),
            ]
        );
    }

    #[test]
    fn signed_order_query_uses_cpp_order_recv_window() {
        let order = build_futures_market_order_params("BTCUSDT", "BUY", 1.0, false, "")
            .expect("market params");
        let query = signed_query_string(
            "test-secret",
            1_700_000_000_000,
            futures_order_recv_window_ms(),
            &order.params,
        );
        assert!(
            query
                .starts_with("symbol=BTCUSDT&side=BUY&type=MARKET&quantity=1&timestamp=1700000000000&recvWindow=5000&signature=")
        );
        assert_eq!(query.rsplit_once('=').expect("signature").1.len(), 64);
    }

    #[test]
    fn parses_order_result_with_cpp_fallback_fields() {
        let payload = json!({
            "symbol": "BTCUSDT",
            "side": "BUY",
            "positionSide": "LONG",
            "orderId": 12345,
            "status": "FILLED",
            "executedQty": "0",
            "origQty": "0.2",
            "avgPrice": "0",
            "price": "21000.5"
        });
        let result =
            parse_futures_order_result(&payload, "ETHUSDT", "SELL", "BOTH").expect("order result");
        assert_eq!(result.symbol, "BTCUSDT");
        assert_eq!(result.side, "BUY");
        assert_eq!(result.position_side, "LONG");
        assert_eq!(result.order_id, "12345");
        assert_eq!(result.status, "FILLED");
        assert_eq!(result.executed_qty, 0.2);
        assert_eq!(result.avg_price, 21000.5);
    }

    #[test]
    fn parses_open_futures_orders_and_applies_symbol_filter() {
        let payload = json!([
            {
                "symbol": "BTCUSDT",
                "orderId": 12345,
                "clientOrderId": "client-1",
                "status": "NEW",
                "side": "SELL",
                "type": "LIMIT",
                "positionSide": "LONG",
                "origQty": "0.2",
                "executedQty": "0",
                "price": "21000.5"
            },
            {
                "symbol": "ETHUSDT",
                "orderId": "67890",
                "status": "PARTIALLY_FILLED",
                "side": "BUY",
                "type": "STOP",
                "origQty": "1",
                "executedQty": "0.25",
                "price": "2000"
            }
        ]);
        let orders = parse_futures_open_orders(&payload, Some("btcusdt")).expect("open orders");
        assert_eq!(orders.len(), 1);
        assert_eq!(orders[0].symbol, "BTCUSDT");
        assert_eq!(orders[0].order_id, "12345");
        assert_eq!(orders[0].client_order_id, "client-1");
        assert_eq!(orders[0].order_type, "LIMIT");
        assert_eq!(orders[0].position_side, "LONG");
        assert_eq!(orders[0].orig_qty, 0.2);
        assert_eq!(orders[0].price, 21000.5);
    }

    #[test]
    fn open_futures_order_parser_rejects_malformed_rows() {
        assert!(parse_futures_open_orders(&json!([{"symbol": "BTCUSDT"}]), None).is_err());
        assert!(parse_futures_open_orders(&json!(["not-an-order"]), None).is_err());
        assert!(parse_futures_open_orders(&json!({"orders": "not-an-array"}), None).is_err());
    }

    #[test]
    fn parses_futures_cancel_success_and_rejects_error_codes() {
        let bulk = parse_futures_cancel_result(
            &json!({"code": 200, "msg": "The liquidation is successful."}),
            "btcusdt",
            "",
        )
        .expect("bulk cancel");
        assert_eq!(bulk.symbol, "BTCUSDT");
        assert!(bulk.order_id.is_empty());
        assert_eq!(bulk.status, "CANCELED");

        let single = parse_futures_cancel_result(
            &json!({"symbol": "BTCUSDT", "orderId": 12345, "status": "CANCELED"}),
            "ETHUSDT",
            "999",
        )
        .expect("single cancel");
        assert_eq!(single.symbol, "BTCUSDT");
        assert_eq!(single.order_id, "12345");
        assert_eq!(single.status, "CANCELED");

        assert!(
            parse_futures_cancel_result(
                &json!({"code": -2011, "msg": "Unknown order sent."}),
                "BTCUSDT",
                "12345",
            )
            .is_err()
        );
    }

    #[test]
    fn parses_futures_trades_like_python_fill_summary_input() {
        let trades = parse_futures_trades(
            &json!([
                {
                    "symbol": "btcusdt",
                    "id": 1,
                    "orderId": 123,
                    "price": "40000",
                    "qty": "2",
                    "quoteQty": "80000",
                    "realizedPnl": "4",
                    "commission": "0.1",
                    "commissionAsset": "usdt",
                    "time": 1700000000000_i64
                },
                {
                    "symbol": "ETHUSDT",
                    "orderId": 456,
                    "price": "2000",
                    "qty": "1"
                }
            ]),
            "BTCUSDT",
        )
        .expect("trade rows");
        assert_eq!(trades.len(), 1);
        assert_eq!(trades[0].trade_id, "1");
        assert_eq!(trades[0].order_id, "123");
        assert_eq!(trades[0].quantity, 2.0);
        assert_eq!(trades[0].quote_quantity, 80000.0);
        assert_eq!(trades[0].realized_pnl, 4.0);
        assert_eq!(trades[0].commission_asset, "USDT");
        assert_eq!(trades[0].time_ms, 1700000000000);
        assert!(parse_futures_trades(&json!([{"symbol": "BTCUSDT"}]), "BTCUSDT").is_err());
    }

    #[test]
    fn parses_futures_leverage_brackets_like_python_max_leverage_lookup() {
        let brackets = parse_futures_leverage_brackets(
            &json!([
                {
                    "symbol": "BTCUSDT",
                    "brackets": [
                        {
                            "initialLeverage": 50,
                            "notionalCap": "100000",
                            "notionalFloor": "0",
                            "maintMarginRatio": "0.01",
                            "cum": "0"
                        }
                    ]
                },
                {
                    "symbol": "ETHUSDT",
                    "brackets": [{"initialLeverage": 25}]
                }
            ]),
            Some("btcusdt"),
        )
        .expect("leverage brackets");
        assert_eq!(brackets.len(), 1);
        assert_eq!(brackets[0].symbol, "BTCUSDT");
        assert_eq!(brackets[0].initial_leverage, 50);
        assert_eq!(brackets[0].notional_cap, 100000.0);
        assert_eq!(brackets[0].maint_margin_ratio, 0.01);
        assert_eq!(
            max_futures_leverage_from_brackets(&brackets, 125).unwrap(),
            50
        );
        assert_eq!(
            max_futures_leverage_from_brackets(&brackets, 20).unwrap(),
            20
        );
        assert!(max_futures_leverage_from_brackets(&[], 125).is_err());
        assert_eq!(clamp_futures_leverage(None, 125, Some(50), true), 5);
        assert_eq!(clamp_futures_leverage(Some(80.0), 125, Some(50), true), 50);
        assert_eq!(clamp_futures_leverage(Some(80.0), 20, None, false), 20);
        assert_eq!(clamp_futures_leverage(Some(f64::NAN), 20, None, true), 1);
        assert!(parse_futures_leverage_brackets(&json!([]), Some("BTCUSDT")).is_err());
    }

    #[test]
    fn parses_futures_force_orders_like_python_history_metadata() {
        let orders = parse_futures_force_orders(
            &json!({
                "forceOrders": [{
                    "symbol": "BTCUSDT",
                    "orderId": 123,
                    "side": "SELL",
                    "positionSide": "LONG",
                    "status": "FILLED",
                    "type": "LIMIT",
                    "avgPrice": "40000",
                    "executedQty": "0.2",
                    "origQty": "0.2",
                    "price": "39900",
                    "time": 1700000000000_i64,
                    "updateTime": 1700000001000_i64
                }]
            }),
            Some("btcusdt"),
        )
        .expect("force orders");
        assert_eq!(orders.len(), 1);
        assert_eq!(orders[0].symbol, "BTCUSDT");
        assert_eq!(orders[0].order_id, "123");
        assert_eq!(orders[0].position_side, "LONG");
        assert_eq!(orders[0].executed_qty, 0.2);
        assert_eq!(orders[0].time_ms, 1_700_000_000_000);
    }

    #[test]
    fn parses_spot_trades_like_python_cost_basis_input() {
        let trades = parse_spot_trades(
            &json!([
                {
                    "symbol": "ETHUSDT",
                    "id": 1,
                    "orderId": 11,
                    "price": "2000",
                    "qty": "0.25",
                    "quoteQty": "500",
                    "commission": "0.001",
                    "commissionAsset": "ETH",
                    "isBuyer": true,
                    "isMaker": false,
                    "isBestMatch": true,
                    "time": 1700000000000_i64
                }
            ]),
            "ethusdt",
        )
        .expect("spot trades");
        assert_eq!(trades.len(), 1);
        assert_eq!(trades[0].symbol, "ETHUSDT");
        assert_eq!(trades[0].order_id, "11");
        assert_eq!(trades[0].quantity, 0.25);
        assert_eq!(trades[0].quote_quantity, 500.0);
        assert!(trades[0].is_buyer);
        assert_eq!(trades[0].commission_asset, "ETH");
        let cost = calculate_spot_position_cost("ethusdt", &trades)
            .expect("spot cost basis")
            .expect("open spot position");
        assert_eq!(cost.symbol, "ETHUSDT");
        assert_eq!(cost.quantity, 0.25);
        assert_eq!(cost.cost, 500.0);
        let sold = BinanceSpotTrade {
            is_buyer: false,
            ..trades[0].clone()
        };
        assert!(
            calculate_spot_position_cost("ETHUSDT", &[sold])
                .expect("closed spot position")
                .is_none()
        );
    }

    #[test]
    fn spot_trade_flags_follow_python_truthiness_for_json_values() {
        let trades = parse_spot_trades(
            &json!([
                {"symbol": "ETHUSDT", "id": 1, "price": "1", "qty": "1", "isBuyer": "false"},
                {"symbol": "ETHUSDT", "id": 2, "price": "1", "qty": "1", "isBuyer": 0.5},
                {"symbol": "ETHUSDT", "id": 3, "price": "1", "qty": "1", "isBuyer": []},
                {"symbol": "ETHUSDT", "id": 4, "price": "1", "qty": "1", "isBuyer": [0]}
            ]),
            "ETHUSDT",
        )
        .expect("spot trades");
        assert_eq!(trades.len(), 4);
        assert!(trades[0].is_buyer);
        assert!(trades[1].is_buyer);
        assert!(!trades[2].is_buyer);
        assert!(trades[3].is_buyer);
    }

    #[test]
    fn signed_futures_order_lifecycle_uses_python_cpp_equivalent_http_paths() {
        fn serve_request(mut stream: TcpStream, expected_prefix: &str, body: &str) {
            let mut request = Vec::new();
            let mut buffer = [0_u8; 1024];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream.read(&mut buffer).expect("read request");
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
                .expect("write response");
        }

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind local Binance fixture");
        let address = listener.local_addr().expect("fixture address");
        let server = thread::spawn(move || {
            let responses = [
                (
                    "GET /fapi/v1/openOrders?symbol=BTCUSDT&",
                    r#"[{"symbol":"BTCUSDT","orderId":123,"status":"NEW"}]"#,
                ),
                (
                    "DELETE /fapi/v1/allOpenOrders?symbol=BTCUSDT&",
                    r#"{"code":200,"msg":"The liquidation is successful."}"#,
                ),
                (
                    "DELETE /fapi/v1/order?symbol=BTCUSDT&orderId=123&",
                    r#"{"symbol":"BTCUSDT","orderId":123,"status":"CANCELED"}"#,
                ),
                (
                    "GET /fapi/v1/userTrades?symbol=BTCUSDT&limit=100&orderId=123&",
                    r#"[{"symbol":"BTCUSDT","id":1,"orderId":123,"price":"40000","qty":"2","quoteQty":"80000","realizedPnl":"4","commission":"0.1","commissionAsset":"USDT","time":1700000000000}]"#,
                ),
                (
                    "GET /fapi/v1/leverageBracket?symbol=BTCUSDT&",
                    r#"[{"symbol":"BTCUSDT","brackets":[{"initialLeverage":50,"notionalCap":"100000","notionalFloor":"0","maintMarginRatio":"0.01","cum":"0"}]}]"#,
                ),
                (
                    "GET /fapi/v1/leverageBracket?symbol=BTCUSDT&",
                    r#"[{"symbol":"BTCUSDT","brackets":[{"initialLeverage":50,"notionalCap":"100000","notionalFloor":"0","maintMarginRatio":"0.01","cum":"0"}]}]"#,
                ),
                (
                    "GET /fapi/v1/forceOrders?symbol=BTCUSDT&startTime=1700000000000&endTime=1700000001000&limit=20&",
                    r#"{"forceOrders":[{"symbol":"BTCUSDT","orderId":456,"side":"SELL","positionSide":"LONG","status":"FILLED","type":"LIMIT","avgPrice":"40000","executedQty":"2","origQty":"2","price":"39900","time":1700000000000,"updateTime":1700000001000}]}"#,
                ),
                (
                    "POST /fapi/v1/positionMargin?symbol=BTCUSDT&amount=1.25&type=1&positionSide=LONG&",
                    r#"{"code":200,"msg":"success"}"#,
                ),
            ];
            for (expected_prefix, body) in responses {
                let (stream, _) = listener.accept().expect("accept Binance fixture request");
                serve_request(stream, expected_prefix, body);
            }
        });

        let http = reqwest::blocking::Client::builder()
            .no_proxy()
            .build()
            .expect("proxy-free fixture client");
        let client = BinanceSignedRestClient::with_http_client(
            BinanceMarket::Futures,
            format!("http://{}", address),
            http,
        )
        .expect("futures fixture client");
        let credentials = BinanceApiCredentials::new("key", "secret");
        let open_orders = client
            .fetch_open_futures_orders(&credentials, Some("btcusdt"))
            .expect("open orders request");
        assert_eq!(open_orders.len(), 1);
        assert_eq!(open_orders[0].order_id, "123");
        assert_eq!(
            client
                .cancel_all_open_futures_orders(&credentials, "btcusdt")
                .expect("bulk cancellation")
                .status,
            "CANCELED"
        );
        assert_eq!(
            client
                .cancel_futures_order(&credentials, "btcusdt", "123")
                .expect("individual cancellation")
                .order_id,
            "123"
        );
        let trades = client
            .fetch_futures_trades(&credentials, "btcusdt", Some("123"), 100)
            .expect("trade history");
        assert_eq!(trades.len(), 1);
        assert_eq!(trades[0].order_id, "123");
        assert_eq!(trades[0].quantity, 2.0);
        let brackets = client
            .fetch_futures_leverage_brackets(&credentials, Some("btcusdt"))
            .expect("leverage brackets");
        assert_eq!(brackets.len(), 1);
        assert_eq!(brackets[0].initial_leverage, 50);
        assert_eq!(
            client
                .fetch_futures_max_leverage(&credentials, "btcusdt", 125)
                .expect("maximum leverage"),
            50
        );
        let force_orders = client
            .fetch_futures_force_orders(
                &credentials,
                Some("btcusdt"),
                Some(1_700_000_000_000),
                Some(1_700_000_001_000),
                20,
            )
            .expect("force orders");
        assert_eq!(force_orders.len(), 1);
        assert_eq!(force_orders[0].order_id, "456");
        assert_eq!(force_orders[0].position_side, "LONG");
        assert_eq!(force_orders[0].executed_qty, 2.0);
        let position_margin = client
            .change_futures_position_margin(&credentials, "btcusdt", 1.25, Some("long"))
            .expect("position margin");
        assert_eq!(position_margin.symbol, "BTCUSDT");
        assert_eq!(position_margin.position_side, "LONG");
        assert_eq!(position_margin.amount, 1.25);
        server.join().expect("Binance fixture server");
    }

    #[test]
    fn futures_order_testnet_fallback_reuses_client_order_id_across_prefixes() {
        fn serve_order_request(mut stream: TcpStream, expected_prefix: &str, body: &str) -> String {
            let mut request = Vec::new();
            let mut buffer = [0_u8; 1024];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream.read(&mut buffer).expect("read order request");
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
                "unexpected order request line: {request_line}"
            );
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
                body.len(),
                body
            );
            stream
                .write_all(response.as_bytes())
                .expect("write order response");
            request_line
        }

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind order fallback fixture");
        let address = listener
            .local_addr()
            .expect("order fallback fixture address");
        let server = thread::spawn(move || {
            let first = listener.accept().expect("accept primary order request").0;
            let first_line = serve_order_request(
                first,
                "POST /fapi/v1/order?symbol=BTCUSDT&side=BUY&type=MARKET&quantity=0.1&newClientOrderId=tb-",
                "[]",
            );
            let second = listener.accept().expect("accept fallback order request").0;
            let second_line = serve_order_request(
                second,
                "POST /dapi/v1/order?symbol=BTCUSDT&side=BUY&type=MARKET&quantity=0.1&newClientOrderId=tb-",
                r#"{"symbol":"BTCUSDT","side":"BUY","clientOrderId":"tb-fallback","status":"NEW","executedQty":"0.1","price":"20000"}"#,
            );
            (first_line, second_line)
        });

        let http = reqwest::blocking::Client::builder()
            .no_proxy()
            .build()
            .expect("proxy-free order fallback client");
        let client = BinanceSignedRestClient::with_http_client(
            BinanceMarket::Futures,
            format!("http://{}", address),
            http,
        )
        .expect("order fallback client");
        let result = client
            .place_futures_market_order(
                &BinanceApiCredentials::new("key", "secret"),
                "btcusdt",
                "buy",
                0.1,
                false,
                "",
            )
            .expect("fallback order should be accepted");
        assert_eq!(result.order_id, "tb-fallback");
        assert_eq!(result.status, "NEW");
        assert_eq!(result.executed_qty, 0.1);

        let (first_line, second_line) = server.join().expect("order fallback fixture server");
        fn client_order_id(request_line: &str) -> &str {
            request_line
                .split_once("newClientOrderId=")
                .and_then(|(_, remainder)| remainder.split_once('&'))
                .map(|(value, _)| value)
                .expect("client order ID in request")
        }
        assert_eq!(client_order_id(&first_line), client_order_id(&second_line));
        assert!(client_order_id(&first_line).starts_with("tb-"));
    }

    #[test]
    fn spot_market_order_submission_injects_stable_client_order_id() {
        fn serve_order_request(mut stream: TcpStream) -> String {
            let mut request = Vec::new();
            let mut buffer = [0_u8; 1024];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream.read(&mut buffer).expect("read spot order request");
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
            assert!(request_line.starts_with(
                "POST /api/v3/order?symbol=ETHUSDT&side=BUY&type=MARKET&quantity=0.25&newClientOrderId=tb-"
            ));
            let body = r#"{"symbol":"ETHUSDT","side":"BUY","orderId":808,"status":"NEW","executedQty":"0.25","price":"2000"}"#;
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
                body.len(),
                body
            );
            stream
                .write_all(response.as_bytes())
                .expect("write spot order response");
            request_line
        }

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind spot order fixture");
        let address = listener.local_addr().expect("spot order fixture address");
        let server = thread::spawn(move || {
            let (stream, _) = listener.accept().expect("accept spot order request");
            serve_order_request(stream)
        });
        let http = reqwest::blocking::Client::builder()
            .no_proxy()
            .build()
            .expect("proxy-free spot order client");
        let client = BinanceSignedRestClient::with_http_client(
            BinanceMarket::Spot,
            format!("http://{}", address),
            http,
        )
        .expect("spot order client");
        let result = client
            .place_spot_market_order(
                &BinanceApiCredentials::new("key", "secret"),
                "ethusdt",
                "buy",
                0.25,
            )
            .expect("spot order should be accepted");
        assert_eq!(result.order_id, "808");
        assert_eq!(result.status, "NEW");
        let request_line = server.join().expect("spot order fixture server");
        let client_order_id = request_line
            .split_once("newClientOrderId=")
            .and_then(|(_, remainder)| remainder.split_once('&'))
            .map(|(value, _)| value)
            .expect("spot client order ID");
        assert_eq!(client_order_id.len(), 35);
        assert!(client_order_id.starts_with("tb-"));
    }

    #[test]
    fn signed_spot_trade_history_uses_python_equivalent_my_trades_path() {
        fn serve_request(mut stream: TcpStream) {
            let mut request = Vec::new();
            let mut buffer = [0_u8; 1024];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream.read(&mut buffer).expect("read request");
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
            assert!(request_line.starts_with("GET /api/v3/myTrades?symbol=ETHUSDT&limit=1000&"));
            let body = r#"[{"symbol":"ETHUSDT","id":7,"orderId":42,"price":"2000","qty":"0.25","quoteQty":"500","commission":"0.001","commissionAsset":"ETH","isBuyer":true,"isMaker":false,"isBestMatch":true,"time":1700000000000}]"#;
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
                body.len(),
                body
            );
            stream
                .write_all(response.as_bytes())
                .expect("write response");
        }

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind spot fixture");
        let address = listener.local_addr().expect("spot fixture address");
        let server = thread::spawn(move || {
            for _ in 0..2 {
                let (stream, _) = listener.accept().expect("accept spot fixture request");
                serve_request(stream);
            }
        });
        let http = reqwest::blocking::Client::builder()
            .no_proxy()
            .build()
            .expect("proxy-free spot fixture client");
        let client = BinanceSignedRestClient::with_http_client(
            BinanceMarket::Spot,
            format!("http://{}", address),
            http,
        )
        .expect("spot fixture client");
        let trades = client
            .fetch_spot_trades(
                &BinanceApiCredentials::new("key", "secret"),
                "ethusdt",
                1000,
            )
            .expect("spot trade history");
        assert_eq!(trades.len(), 1);
        assert_eq!(trades[0].order_id, "42");
        assert_eq!(trades[0].quote_quantity, 500.0);
        assert!(trades[0].is_buyer);
        let cost = client
            .fetch_spot_position_cost(
                &BinanceApiCredentials::new("key", "secret"),
                "ethusdt",
                1000,
            )
            .expect("spot cost basis")
            .expect("open spot position");
        assert_eq!(cost.symbol, "ETHUSDT");
        assert_eq!(cost.quantity, 0.25);
        assert_eq!(cost.cost, 500.0);
        server.join().expect("spot fixture server");
    }

    #[test]
    fn spot_order_result_requires_success_status_and_order_id() {
        let payload = json!({
            "symbol": "BTCUSDT",
            "side": "BUY",
            "orderId": 12345,
            "status": "FILLED",
            "executedQty": "0.2",
            "cummulativeQuoteQty": "4200"
        });
        let result = parse_spot_order_result(&payload, "BTCUSDT", "BUY").expect("spot result");
        assert_eq!(result.order_id, "12345");
        assert_eq!(result.status, "FILLED");
        let wrapped = json!({
            "success": "true",
            "data": {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "id": "client-spot-1",
                "status": "NEW",
                "executedQty": "0.2",
                "price": "21000"
            }
        });
        let wrapped_result =
            parse_spot_order_result(&wrapped, "BTCUSDT", "BUY").expect("wrapped spot result");
        assert_eq!(wrapped_result.order_id, "client-spot-1");
        assert_eq!(wrapped_result.status, "NEW");
        assert_eq!(wrapped_result.executed_qty, 0.2);
        assert_eq!(wrapped_result.avg_price, 21000.0);
        assert!(
            parse_spot_order_result(
                &json!({"success": false, "message": "order rejected"}),
                "BTCUSDT",
                "BUY"
            )
            .is_err()
        );
        assert!(
            parse_spot_order_result(
                &json!({"data": {"code": -2010, "msg": "insufficient balance"}}),
                "BTCUSDT",
                "BUY"
            )
            .is_err()
        );
        assert!(
            parse_spot_order_result(
                &json!({"symbol": "BTCUSDT", "side": "BUY", "orderId": 1}),
                "BTCUSDT",
                "BUY"
            )
            .is_err()
        );
        assert!(
            parse_spot_order_result(
                &json!({"symbol": "BTCUSDT", "side": "BUY", "orderId": 1, "status": "REJECTED"}),
                "BTCUSDT",
                "BUY"
            )
            .is_err()
        );
    }

    #[test]
    fn parses_spot_symbol_metadata_for_close_all_guards() {
        let payload = json!({
            "symbols": [{
                "symbol": "ETHUSDT",
                "status": "TRADING",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5"}
                ]
            }]
        });
        let metadata = parse_spot_symbol_metadata(&payload, "ethusdt").expect("spot metadata");
        assert_eq!(metadata.status, "TRADING");
        assert_eq!(metadata.base_asset, "ETH");
        assert_eq!(metadata.quote_asset, "USDT");
        assert_eq!(metadata.filters.step_size, 0.001);
        assert_eq!(metadata.filters.min_notional, 5.0);
    }

    #[test]
    fn validation_and_error_payloads_fail_closed() {
        assert!(build_futures_market_order_params("", "BUY", 1.0, false, "").is_err());
        assert!(build_futures_market_order_params("BTCUSDT", "HOLD", 1.0, false, "").is_err());
        assert!(
            build_futures_limit_order_params("BTCUSDT", "BUY", 1.0, 0.0, false, "", "").is_err()
        );

        let payload = json!({"code": -2010, "msg": "Account has insufficient balance."});
        assert!(parse_futures_order_result(&payload, "BTCUSDT", "BUY", "BOTH").is_err());
        assert!(
            parse_futures_order_result(&json!({"status": "NEW"}), "BTCUSDT", "BUY", "BOTH")
                .is_err()
        );
        assert!(
            parse_futures_order_result(&json!({"orderId": 1}), "BTCUSDT", "BUY", "BOTH").is_err()
        );
        assert!(
            parse_futures_order_result(
                &json!({"orderId": 1, "status": "EXPIRED_IN_MATCH"}),
                "BTCUSDT",
                "BUY",
                "BOTH"
            )
            .is_err()
        );
    }
}
