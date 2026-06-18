use crate::orders::{BinanceFuturesSymbolFilters, format_decimal_for_order};

pub const LIVE_TRADING_ACKNOWLEDGEMENT: &str = "I_UNDERSTAND_LIVE_TRADING_RISK";
pub const DEFAULT_LIVE_MAX_LEVERAGE: i64 = 20;
pub const DEFAULT_LIVE_MAX_POSITION_PCT: f64 = 10.0;
pub const DEFAULT_LIVE_MAX_SESSION_ORDERS: i64 = 100;
pub const MAX_LIVE_MAX_SESSION_ORDERS: i64 = 100_000;
pub const BINANCE_MAX_FUTURES_LEVERAGE: i64 = 125;

#[derive(Debug, Clone, PartialEq)]
pub struct OrderSubmitIntent {
    pub market: String,
    pub symbol: String,
    pub side: String,
    pub order_type: String,
    pub quantity: Option<f64>,
    pub price: Option<f64>,
    pub position_side: String,
    pub close_position: bool,
    pub reduce_only: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OrderSymbolFilters {
    pub step_size: f64,
    pub tick_size: f64,
    pub min_qty: f64,
    pub min_notional: f64,
}

impl Default for OrderSymbolFilters {
    fn default() -> Self {
        Self {
            step_size: 0.0,
            tick_size: 0.0,
            min_qty: 0.0,
            min_notional: 0.0,
        }
    }
}

impl From<&BinanceFuturesSymbolFilters> for OrderSymbolFilters {
    fn from(filters: &BinanceFuturesSymbolFilters) -> Self {
        Self {
            step_size: filters.step_size,
            tick_size: filters.tick_size,
            min_qty: filters.min_qty,
            min_notional: filters.min_notional,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct LiveTradingSafetyConfig {
    pub live_trading_enabled: bool,
    pub live_trading_acknowledgement: String,
    pub live_trading_max_leverage: i64,
    pub live_trading_max_position_pct: f64,
    pub live_trading_max_session_orders: i64,
}

impl Default for LiveTradingSafetyConfig {
    fn default() -> Self {
        Self {
            live_trading_enabled: false,
            live_trading_acknowledgement: String::new(),
            live_trading_max_leverage: DEFAULT_LIVE_MAX_LEVERAGE,
            live_trading_max_position_pct: DEFAULT_LIVE_MAX_POSITION_PCT,
            live_trading_max_session_orders: DEFAULT_LIVE_MAX_SESSION_ORDERS,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct LiveTradingSafetyInput {
    pub mode: String,
    pub api_key: String,
    pub api_secret: String,
    pub account_type: String,
    pub leverage: i64,
    pub margin_mode: String,
    pub position_pct: f64,
    pub config: LiveTradingSafetyConfig,
}

impl Default for LiveTradingSafetyInput {
    fn default() -> Self {
        Self {
            mode: String::new(),
            api_key: String::new(),
            api_secret: String::new(),
            account_type: "FUTURES".to_owned(),
            leverage: 1,
            margin_mode: String::new(),
            position_pct: 2.0,
            config: LiveTradingSafetyConfig::default(),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceOrderSubmitGuardInput {
    pub mode: String,
    pub market: String,
    pub params: Vec<(String, String)>,
    pub api_key: String,
    pub api_secret: String,
    pub account_type: String,
    pub leverage: i64,
    pub margin_mode: String,
    pub position_pct: f64,
    pub config: LiveTradingSafetyConfig,
    pub filters: Option<OrderSymbolFilters>,
    pub last_price: Option<f64>,
    pub order_audit_enabled: bool,
    pub order_audit_writable: bool,
    pub connector_state: String,
    pub connector_health: String,
    pub live_submit_attempt_count: i64,
}

impl Default for BinanceOrderSubmitGuardInput {
    fn default() -> Self {
        Self {
            mode: String::new(),
            market: "futures".to_owned(),
            params: Vec::new(),
            api_key: String::new(),
            api_secret: String::new(),
            account_type: "FUTURES".to_owned(),
            leverage: 1,
            margin_mode: String::new(),
            position_pct: 2.0,
            config: LiveTradingSafetyConfig::default(),
            filters: None,
            last_price: None,
            order_audit_enabled: true,
            order_audit_writable: true,
            connector_state: String::new(),
            connector_health: String::new(),
            live_submit_attempt_count: 0,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceOrderSubmitGuardResult {
    pub allowed: bool,
    pub errors: Vec<String>,
    pub next_submit_attempt_count: i64,
}

pub fn order_submit_intent_from_params(
    market: impl AsRef<str>,
    params: &[(&str, String)],
) -> OrderSubmitIntent {
    let owned = params
        .iter()
        .map(|(key, value)| ((*key).to_owned(), value.clone()))
        .collect::<Vec<_>>();
    order_submit_intent_from_param_pairs(market, &owned)
}

pub fn order_submit_intent_from_param_pairs(
    market: impl AsRef<str>,
    params: &[(String, String)],
) -> OrderSubmitIntent {
    OrderSubmitIntent {
        market: market.as_ref().trim().to_lowercase(),
        symbol: param_value(params, &["symbol"])
            .unwrap_or_default()
            .trim()
            .to_uppercase(),
        side: param_value(params, &["side"])
            .unwrap_or_default()
            .trim()
            .to_uppercase(),
        order_type: param_value(params, &["type"])
            .unwrap_or_default()
            .trim()
            .to_uppercase(),
        quantity: float_param(param_value(params, &["quantity"]).as_deref()),
        price: float_param(param_value(params, &["price"]).as_deref()),
        position_side: param_value(params, &["positionSide", "position_side"])
            .unwrap_or_default()
            .trim()
            .to_uppercase(),
        close_position: bool_param(
            param_value(params, &["closePosition", "close_position"]).as_deref(),
        ),
        reduce_only: bool_param(param_value(params, &["reduceOnly", "reduce_only"]).as_deref()),
    }
}

pub fn validate_order_submit_intent(intent: &OrderSubmitIntent) -> Vec<String> {
    let mut errors = Vec::new();
    if !matches!(intent.market.as_str(), "futures" | "spot") {
        errors.push("order market must be futures or spot".to_owned());
    }
    if intent.symbol.is_empty() {
        errors.push("order symbol is required".to_owned());
    }
    if !matches!(intent.side.as_str(), "BUY" | "SELL") {
        errors.push("order side must be BUY or SELL".to_owned());
    }
    if intent.order_type.is_empty() {
        errors.push("order type is required".to_owned());
    } else if !matches!(intent.order_type.as_str(), "LIMIT" | "MARKET") {
        errors.push("order type must be LIMIT or MARKET".to_owned());
    }
    if !intent.position_side.is_empty()
        && !matches!(intent.position_side.as_str(), "BOTH" | "LONG" | "SHORT")
    {
        errors.push("positionSide must be BOTH, LONG, or SHORT".to_owned());
    }
    if !intent.position_side.is_empty() && intent.market != "futures" {
        errors.push("positionSide is only supported for futures".to_owned());
    }
    if intent.close_position && intent.market != "futures" {
        errors.push("closePosition orders are only supported for futures".to_owned());
    }
    if intent.reduce_only && intent.market != "futures" {
        errors.push("reduceOnly orders are only supported for futures".to_owned());
    }
    if intent.close_position && intent.reduce_only {
        errors.push("closePosition and reduceOnly cannot be used together".to_owned());
    }
    let quantity_required = intent.market != "futures" || !intent.close_position;
    if quantity_required && intent.quantity.map(|value| value <= 0.0).unwrap_or(true) {
        errors.push("order quantity must be > 0".to_owned());
    }
    if intent.order_type == "LIMIT" && intent.price.map(|value| value <= 0.0).unwrap_or(true) {
        errors.push("limit order price must be > 0".to_owned());
    }
    errors
}

pub fn validate_order_filter_constraints(
    intent: &OrderSubmitIntent,
    filters: &OrderSymbolFilters,
    last_price: Option<f64>,
) -> Vec<String> {
    let Some(quantity) = intent.quantity.filter(|value| value.is_finite()) else {
        return Vec::new();
    };
    let mut errors = Vec::new();
    let risk_reducing_exit =
        intent.market == "futures" && (intent.reduce_only || intent.close_position);

    if filters.min_qty > 0.0 && quantity < filters.min_qty && !risk_reducing_exit {
        errors.push(format!(
            "order quantity {} is below {} minQty {}",
            decimal_text(quantity),
            intent.symbol,
            decimal_text(filters.min_qty)
        ));
    }
    if filters.step_size > 0.0 && !aligned_to_step(quantity, filters.step_size) {
        errors.push(format!(
            "order quantity {} is not aligned to {} stepSize {}",
            decimal_text(quantity),
            intent.symbol,
            decimal_text(filters.step_size)
        ));
    }

    let price = intent.price.or(last_price).filter(|value| *value > 0.0);
    if filters.tick_size > 0.0
        && price
            .map(|value| !aligned_to_step(value, filters.tick_size))
            .unwrap_or(false)
    {
        errors.push(format!(
            "order price {} is not aligned to {} tickSize {}",
            decimal_text(price.unwrap_or_default()),
            intent.symbol,
            decimal_text(filters.tick_size)
        ));
    }
    if filters.min_notional > 0.0 && !risk_reducing_exit {
        match price {
            Some(price) => {
                let notional = quantity * price;
                if notional < filters.min_notional {
                    errors.push(format!(
                        "order notional {} is below {} minNotional {}",
                        decimal_text(notional),
                        intent.symbol,
                        decimal_text(filters.min_notional)
                    ));
                }
            }
            None => errors.push(format!(
                "last price unavailable for {} minNotional validation",
                intent.symbol
            )),
        }
    }
    errors
}

pub fn is_live_trading_mode(mode: impl AsRef<str>) -> bool {
    let text = mode.as_ref().trim().to_lowercase();
    if text.is_empty() {
        return false;
    }
    !["demo", "test", "sandbox", "paper"]
        .iter()
        .any(|token| text.contains(token))
}

pub fn validate_live_trading_safety(input: &LiveTradingSafetyInput) -> Vec<String> {
    if !is_live_trading_mode(&input.mode) {
        return Vec::new();
    }

    let mut errors = Vec::new();
    let cfg = &input.config;
    if !cfg.live_trading_enabled
        || cfg.live_trading_acknowledgement.trim() != LIVE_TRADING_ACKNOWLEDGEMENT
    {
        errors.push(format!(
            "set live_trading_enabled=true and live_trading_acknowledgement={LIVE_TRADING_ACKNOWLEDGEMENT:?}"
        ));
    }
    if !credential_is_real(&input.api_key) || !credential_is_real(&input.api_secret) {
        errors.push("provide non-placeholder Binance API credentials".to_owned());
    }
    if cfg.live_trading_max_leverage < 1
        || cfg.live_trading_max_leverage > BINANCE_MAX_FUTURES_LEVERAGE
    {
        errors.push(format!(
            "live_trading_max_leverage must be between 1 and {BINANCE_MAX_FUTURES_LEVERAGE}"
        ));
    }
    if cfg.live_trading_max_position_pct <= 0.0 || cfg.live_trading_max_position_pct > 100.0 {
        errors.push("live_trading_max_position_pct must be > 0 and <= 100".to_owned());
    }
    if cfg.live_trading_max_session_orders < 1
        || cfg.live_trading_max_session_orders > MAX_LIVE_MAX_SESSION_ORDERS
    {
        errors.push(format!(
            "live_trading_max_session_orders must be between 1 and {MAX_LIVE_MAX_SESSION_ORDERS}"
        ));
    }
    if input.position_pct <= 0.0 || input.position_pct > 100.0 {
        errors.push("position_pct must be > 0 and <= 100 for live trading".to_owned());
    } else if input.position_pct > cfg.live_trading_max_position_pct {
        errors.push(format!(
            "position_pct {}% exceeds live cap {}%",
            decimal_text(input.position_pct),
            decimal_text(cfg.live_trading_max_position_pct)
        ));
    }

    if input.account_type.trim().to_uppercase().starts_with("FUT") {
        if input.leverage < 1 {
            errors.push("leverage must be >= 1 for live futures trading".to_owned());
        } else if input.leverage > cfg.live_trading_max_leverage {
            errors.push(format!(
                "leverage {} exceeds live cap {}",
                input.leverage, cfg.live_trading_max_leverage
            ));
        }

        let margin = input.margin_mode.trim().to_uppercase();
        if !margin.is_empty() && !matches!(margin.as_str(), "ISOLATED" | "CROSS") {
            errors
                .push("margin_mode must be Isolated or Cross for live futures trading".to_owned());
        }
    }

    errors
}

pub fn guard_live_order_submit(
    input: &BinanceOrderSubmitGuardInput,
) -> BinanceOrderSubmitGuardResult {
    let current_count = input.live_submit_attempt_count.max(0);
    if !is_live_trading_mode(&input.mode) {
        return BinanceOrderSubmitGuardResult {
            allowed: true,
            errors: Vec::new(),
            next_submit_attempt_count: current_count,
        };
    }

    let mut errors = validate_live_trading_safety(&LiveTradingSafetyInput {
        mode: input.mode.clone(),
        api_key: input.api_key.clone(),
        api_secret: input.api_secret.clone(),
        account_type: input.account_type.clone(),
        leverage: input.leverage,
        margin_mode: input.margin_mode.clone(),
        position_pct: input.position_pct,
        config: input.config.clone(),
    });

    if !input.order_audit_enabled {
        errors.push("order audit is disabled".to_owned());
    }
    if !input.order_audit_writable {
        errors.push("order audit is not writable".to_owned());
    }
    errors.extend(connector_health_errors(
        &input.connector_state,
        &input.connector_health,
    ));

    let intent = order_submit_intent_from_param_pairs(&input.market, &input.params);
    errors.extend(validate_order_submit_intent(&intent));
    if !intent.symbol.is_empty()
        && intent.quantity.is_some()
        && matches!(intent.market.as_str(), "futures" | "spot")
    {
        match &input.filters {
            Some(filters) => errors.extend(validate_order_filter_constraints(
                &intent,
                filters,
                input.last_price,
            )),
            None => errors.push(format!(
                "{} symbol filters unavailable for {}",
                intent.market, intent.symbol
            )),
        }
    }

    let max_session_orders = input.config.live_trading_max_session_orders;
    if current_count >= max_session_orders {
        errors.push(format!(
            "live session order cap {max_session_orders} reached"
        ));
    }

    let allowed = errors.is_empty();
    BinanceOrderSubmitGuardResult {
        allowed,
        errors,
        next_submit_attempt_count: if allowed {
            current_count + 1
        } else {
            current_count
        },
    }
}

fn connector_health_errors(state: &str, health: &str) -> Vec<String> {
    let state = state.trim().to_lowercase();
    let health = health.trim().to_lowercase();
    if !state.is_empty() && state != "ready" {
        return vec![format!(
            "connector health is {} / {}",
            if health.is_empty() {
                "unknown"
            } else {
                &health
            },
            state
        )];
    }
    if !health.is_empty() && !matches!(health.as_str(), "ok" | "unknown") {
        return vec![format!("connector health is {health}")];
    }
    Vec::new()
}

fn param_value(params: &[(String, String)], keys: &[&str]) -> Option<String> {
    for key in keys {
        if let Some((_, value)) = params
            .iter()
            .find(|(current, _)| current.trim().eq_ignore_ascii_case(key))
        {
            return Some(value.clone());
        }
    }
    None
}

fn bool_param(value: Option<&str>) -> bool {
    matches!(
        value.unwrap_or_default().trim().to_lowercase().as_str(),
        "1" | "true" | "yes" | "y" | "on"
    )
}

fn float_param(value: Option<&str>) -> Option<f64> {
    let text = value?.trim();
    if text.is_empty() {
        return None;
    }
    text.parse::<f64>().ok().filter(|value| value.is_finite())
}

fn aligned_to_step(value: f64, step: f64) -> bool {
    if !value.is_finite() || !step.is_finite() || step <= 0.0 {
        return true;
    }
    let ratio = value / step;
    (ratio - ratio.round()).abs() <= 1e-9
}

fn credential_is_real(value: &str) -> bool {
    let text = value.trim();
    if text.is_empty() {
        return false;
    }
    !matches!(
        text.to_lowercase().as_str(),
        "api_key"
            | "api-secret"
            | "api_secret"
            | "binance_api_key"
            | "binance_api_secret"
            | "changeme"
            | "demo"
            | "example"
            | "sandbox"
            | "secret"
            | "test"
            | "testnet"
            | "your-api-key"
            | "your-api-secret"
            | "your_api_key"
            | "your_api_secret"
    )
}

fn decimal_text(value: f64) -> String {
    format_decimal_for_order(value, 12)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::orders::{
        BinanceFuturesSymbolFilters, build_futures_limit_order_params,
        build_futures_market_order_params,
    };

    fn futures_filters() -> OrderSymbolFilters {
        OrderSymbolFilters {
            step_size: 0.001,
            tick_size: 0.10,
            min_qty: 0.01,
            min_notional: 5.0,
        }
    }

    fn live_config() -> LiveTradingSafetyConfig {
        LiveTradingSafetyConfig {
            live_trading_enabled: true,
            live_trading_acknowledgement: LIVE_TRADING_ACKNOWLEDGEMENT.to_owned(),
            live_trading_max_leverage: 20,
            live_trading_max_position_pct: 10.0,
            live_trading_max_session_orders: 3,
        }
    }

    #[test]
    fn validates_order_intent_like_python_trading_core() {
        let close_position = order_submit_intent_from_param_pairs(
            "futures",
            &[
                ("symbol".to_owned(), "btcusdt".to_owned()),
                ("side".to_owned(), "SELL".to_owned()),
                ("type".to_owned(), "MARKET".to_owned()),
                ("closePosition".to_owned(), "true".to_owned()),
            ],
        );
        assert!(validate_order_submit_intent(&close_position).is_empty());

        let invalid = order_submit_intent_from_param_pairs(
            "spot",
            &[
                ("symbol".to_owned(), "ETHUSDT".to_owned()),
                ("side".to_owned(), "HOLD".to_owned()),
                ("type".to_owned(), "STOP".to_owned()),
                ("reduceOnly".to_owned(), "true".to_owned()),
                ("positionSide".to_owned(), "LONG".to_owned()),
            ],
        );
        assert_eq!(
            validate_order_submit_intent(&invalid),
            vec![
                "order side must be BUY or SELL".to_owned(),
                "order type must be LIMIT or MARKET".to_owned(),
                "positionSide is only supported for futures".to_owned(),
                "reduceOnly orders are only supported for futures".to_owned(),
                "order quantity must be > 0".to_owned(),
            ]
        );
    }

    #[test]
    fn parses_existing_order_params_into_guard_intent() {
        let params =
            build_futures_limit_order_params("ethusdt", "buy", 1.25, 2000.0, false, "LONG", "IOC")
                .expect("limit params");
        let intent = order_submit_intent_from_params("futures", &params.params);
        assert_eq!(intent.symbol, "ETHUSDT");
        assert_eq!(intent.side, "BUY");
        assert_eq!(intent.order_type, "LIMIT");
        assert_eq!(intent.quantity, Some(1.25));
        assert_eq!(intent.price, Some(2000.0));
        assert_eq!(intent.position_side, "LONG");
        assert!(validate_order_submit_intent(&intent).is_empty());
    }

    #[test]
    fn validates_filter_alignment_and_min_notional_like_python_guard() {
        let params = build_futures_market_order_params("BTCUSDT", "BUY", 0.0125, false, "")
            .expect("market params");
        let intent = order_submit_intent_from_params("futures", &params.params);
        let errors = validate_order_filter_constraints(&intent, &futures_filters(), Some(300.03));
        assert_eq!(
            errors,
            vec![
                "order quantity 0.0125 is not aligned to BTCUSDT stepSize 0.001".to_owned(),
                "order price 300.03 is not aligned to BTCUSDT tickSize 0.1".to_owned(),
                "order notional 3.750375 is below BTCUSDT minNotional 5".to_owned(),
            ]
        );
    }

    #[test]
    fn risk_reducing_exit_skips_min_qty_and_notional_but_not_step() {
        let params = build_futures_market_order_params("BTCUSDT", "SELL", 0.0015, true, "")
            .expect("reduce-only params");
        let intent = order_submit_intent_from_params("futures", &params.params);
        let errors = validate_order_filter_constraints(&intent, &futures_filters(), Some(100.0));
        assert_eq!(
            errors,
            vec!["order quantity 0.0015 is not aligned to BTCUSDT stepSize 0.001".to_owned()]
        );
    }

    #[test]
    fn live_safety_blocks_missing_ack_placeholders_and_caps() {
        let errors = validate_live_trading_safety(&LiveTradingSafetyInput {
            mode: "live".to_owned(),
            api_key: "test".to_owned(),
            api_secret: "secret".to_owned(),
            leverage: 25,
            position_pct: 20.0,
            margin_mode: "invalid".to_owned(),
            config: live_config(),
            ..Default::default()
        });
        assert_eq!(
            errors,
            vec![
                "provide non-placeholder Binance API credentials".to_owned(),
                "position_pct 20% exceeds live cap 10%".to_owned(),
                "leverage 25 exceeds live cap 20".to_owned(),
                "margin_mode must be Isolated or Cross for live futures trading".to_owned(),
            ]
        );

        let missing_ack = validate_live_trading_safety(&LiveTradingSafetyInput {
            mode: "real".to_owned(),
            api_key: "real-key".to_owned(),
            api_secret: "real-secret".to_owned(),
            config: LiveTradingSafetyConfig::default(),
            ..Default::default()
        });
        assert!(
            missing_ack
                .iter()
                .any(|error| error.contains("live_trading_enabled=true"))
        );
    }

    #[test]
    fn live_order_guard_fails_closed_and_does_not_increment_on_errors() {
        let input = BinanceOrderSubmitGuardInput {
            mode: "live".to_owned(),
            market: "futures".to_owned(),
            params: vec![
                ("symbol".to_owned(), "ETHUSDT".to_owned()),
                ("side".to_owned(), "BUY".to_owned()),
                ("type".to_owned(), "MARKET".to_owned()),
                ("quantity".to_owned(), "1".to_owned()),
            ],
            api_key: "real-key".to_owned(),
            api_secret: "real-secret".to_owned(),
            config: live_config(),
            filters: None,
            order_audit_enabled: false,
            connector_state: "paused".to_owned(),
            connector_health: "degraded".to_owned(),
            live_submit_attempt_count: 1,
            ..Default::default()
        };
        let result = guard_live_order_submit(&input);
        assert!(!result.allowed);
        assert_eq!(result.next_submit_attempt_count, 1);
        assert!(
            result
                .errors
                .contains(&"order audit is disabled".to_owned())
        );
        assert!(
            result
                .errors
                .contains(&"connector health is degraded / paused".to_owned())
        );
        assert!(
            result
                .errors
                .contains(&"futures symbol filters unavailable for ETHUSDT".to_owned())
        );
    }

    #[test]
    fn live_order_guard_allows_safe_order_and_increments_session_count() {
        let params = build_futures_market_order_params("ETHUSDT", "BUY", 0.25, false, "")
            .expect("order params")
            .params
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect();
        let result = guard_live_order_submit(&BinanceOrderSubmitGuardInput {
            mode: "live".to_owned(),
            market: "futures".to_owned(),
            params,
            api_key: "real-key".to_owned(),
            api_secret: "real-secret".to_owned(),
            leverage: 5,
            margin_mode: "isolated".to_owned(),
            position_pct: 2.0,
            config: live_config(),
            filters: Some(futures_filters()),
            last_price: Some(2000.0),
            connector_state: "ready".to_owned(),
            connector_health: "ok".to_owned(),
            live_submit_attempt_count: 2,
            ..Default::default()
        });
        assert!(result.allowed, "{:?}", result.errors);
        assert_eq!(result.next_submit_attempt_count, 3);
    }

    #[test]
    fn live_order_guard_blocks_session_cap_and_demo_mode_short_circuits() {
        let params = vec![
            ("symbol".to_owned(), "ETHUSDT".to_owned()),
            ("side".to_owned(), "BUY".to_owned()),
            ("type".to_owned(), "MARKET".to_owned()),
            ("quantity".to_owned(), "1".to_owned()),
        ];
        let capped = guard_live_order_submit(&BinanceOrderSubmitGuardInput {
            mode: "live".to_owned(),
            market: "futures".to_owned(),
            params: params.clone(),
            api_key: "real-key".to_owned(),
            api_secret: "real-secret".to_owned(),
            config: live_config(),
            filters: Some(futures_filters()),
            last_price: Some(1000.0),
            live_submit_attempt_count: 3,
            ..Default::default()
        });
        assert!(!capped.allowed);
        assert!(
            capped
                .errors
                .contains(&"live session order cap 3 reached".to_owned())
        );

        let demo = guard_live_order_submit(&BinanceOrderSubmitGuardInput {
            mode: "demo".to_owned(),
            params,
            live_submit_attempt_count: 3,
            ..Default::default()
        });
        assert!(demo.allowed);
        assert!(demo.errors.is_empty());
        assert_eq!(demo.next_submit_attempt_count, 3);
    }

    #[test]
    fn futures_filters_convert_into_guard_filters() {
        let filters = BinanceFuturesSymbolFilters {
            symbol: "BTCUSDT".to_owned(),
            step_size: 0.001,
            tick_size: 0.1,
            min_qty: 0.01,
            max_qty: 100.0,
            min_notional: 5.0,
            quantity_precision: 3,
            price_precision: 1,
        };
        assert_eq!(
            OrderSymbolFilters::from(&filters),
            OrderSymbolFilters {
                step_size: 0.001,
                tick_size: 0.1,
                min_qty: 0.01,
                min_notional: 5.0,
            }
        );
    }
}
