use serde::{Deserialize, Serialize};

pub const STOP_LOSS_MODE_ORDER: &[&str] = &["usdt", "percent", "both"];
pub const STOP_LOSS_SCOPE_OPTIONS: &[&str] = &["per_trade", "cumulative", "entire_account"];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StopLossSettings {
    pub enabled: bool,
    pub mode: String,
    pub usdt: f64,
    pub percent: f64,
    pub scope: String,
}

impl Default for StopLossSettings {
    fn default() -> Self {
        Self {
            enabled: false,
            mode: "usdt".to_owned(),
            usdt: 0.0,
            percent: 0.0,
            scope: "per_trade".to_owned(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StopLossRuntimeContext {
    pub stop_cfg: StopLossSettings,
    pub stop_mode: String,
    pub stop_usdt_limit: f64,
    pub stop_percent_limit: f64,
    pub scope: String,
    pub stop_enabled: bool,
    pub apply_usdt_limit: bool,
    pub apply_percent_limit: bool,
    pub account_type: String,
    pub is_cumulative: bool,
    pub is_entire_account: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FuturesLegEntry {
    pub qty: f64,
    pub entry_price: f64,
    pub leverage: f64,
    pub margin_usdt: f64,
    pub ledger_id: String,
    pub indicator_keys: Vec<String>,
    pub trigger_signature: Vec<String>,
}

impl Default for FuturesLegEntry {
    fn default() -> Self {
        Self {
            qty: 0.0,
            entry_price: 0.0,
            leverage: 0.0,
            margin_usdt: 0.0,
            ledger_id: String::new(),
            indicator_keys: Vec::new(),
            trigger_signature: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FuturesRiskPosition {
    pub symbol: String,
    pub position_side: String,
    pub position_amt: f64,
    pub entry_price: f64,
    pub isolated_wallet: f64,
    pub initial_margin: f64,
    pub notional: f64,
    pub leverage: f64,
    pub margin_ratio: f64,
    pub maint_margin: f64,
    pub margin_balance: f64,
}

impl Default for FuturesRiskPosition {
    fn default() -> Self {
        Self {
            symbol: String::new(),
            position_side: "BOTH".to_owned(),
            position_amt: 0.0,
            entry_price: 0.0,
            isolated_wallet: 0.0,
            initial_margin: 0.0,
            notional: 0.0,
            leverage: 1.0,
            margin_ratio: 0.0,
            maint_margin: 0.0,
            margin_balance: 0.0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FuturesStopCloseDirective {
    pub symbol: String,
    pub interval: String,
    pub side_label: String,
    pub close_side: String,
    pub position_side: Option<String>,
    pub qty: f64,
    pub reason: String,
    pub loss_usdt: f64,
    pub price_loss_percent: f64,
    pub margin_loss_percent: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EntireAccountStopDecision {
    pub triggered: bool,
    pub reason: String,
    pub total_unrealized: f64,
    pub total_wallet: f64,
    pub loss_percent: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CloseOppositeRequest {
    pub symbol: String,
    pub interval: String,
    pub next_side: String,
    pub dual_side: bool,
    pub allow_opposite_positions: bool,
    pub hedge_preserve_opposites: bool,
    pub strict_indicator_flip_enforcement: bool,
    pub indicator_tokens: Vec<String>,
    pub signature_tokens: Vec<String>,
    pub target_qty: Option<String>,
}

impl Default for CloseOppositeRequest {
    fn default() -> Self {
        Self {
            symbol: String::new(),
            interval: String::new(),
            next_side: String::new(),
            dual_side: false,
            allow_opposite_positions: true,
            hedge_preserve_opposites: false,
            strict_indicator_flip_enforcement: true,
            indicator_tokens: Vec::new(),
            signature_tokens: Vec::new(),
            target_qty: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum CloseOppositeAction {
    InvalidSideAllowsNoop,
    AlreadyFlat,
    SkipHedgeScopeMissing,
    SkipHedgeIsolationScopeMissing,
    SkipMissingOppositeSignature,
    CloseIndicatorScopeBeforeOpen,
    CloseSymbolLevelBeforeOpen,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CloseOppositePlan {
    pub allowed_to_open_now: bool,
    pub action: CloseOppositeAction,
    pub symbol: String,
    pub interval: String,
    pub desired_side: String,
    pub opposite_side: String,
    pub close_side: String,
    pub position_side: Option<String>,
    pub reason: String,
}

pub fn normalize_stop_loss_settings(settings: StopLossSettings) -> StopLossSettings {
    let mode = normalize_choice(&settings.mode, STOP_LOSS_MODE_ORDER, "usdt");
    let scope = normalize_choice(&settings.scope, STOP_LOSS_SCOPE_OPTIONS, "per_trade");
    StopLossSettings {
        enabled: settings.enabled,
        mode,
        usdt: finite_non_negative(settings.usdt),
        percent: finite_non_negative(settings.percent),
        scope,
    }
}

pub fn build_stop_loss_runtime_context(
    settings: StopLossSettings,
    account_type: impl AsRef<str>,
) -> StopLossRuntimeContext {
    let stop_cfg = normalize_stop_loss_settings(settings);
    let stop_mode = stop_cfg.mode.clone();
    let stop_usdt_limit = finite_non_negative(stop_cfg.usdt);
    let stop_percent_limit = finite_non_negative(stop_cfg.percent);
    let scope = stop_cfg.scope.clone();
    let apply_usdt_limit =
        stop_cfg.enabled && matches!(stop_mode.as_str(), "usdt" | "both") && stop_usdt_limit > 0.0;
    let apply_percent_limit = stop_cfg.enabled
        && matches!(stop_mode.as_str(), "percent" | "both")
        && stop_percent_limit > 0.0;
    let stop_enabled = apply_usdt_limit || apply_percent_limit;
    let account_type = account_type.as_ref().trim().to_uppercase();
    StopLossRuntimeContext {
        stop_cfg,
        stop_mode,
        stop_usdt_limit,
        stop_percent_limit,
        scope: scope.clone(),
        stop_enabled,
        apply_usdt_limit,
        apply_percent_limit,
        account_type,
        is_cumulative: stop_enabled && scope == "cumulative",
        is_entire_account: stop_enabled && scope == "entire_account",
    }
}

pub fn evaluate_per_trade_stop_loss(
    symbol: impl AsRef<str>,
    interval: impl AsRef<str>,
    side_label: impl AsRef<str>,
    entries: &[FuturesLegEntry],
    last_price: Option<f64>,
    dual_side: bool,
    ctx: &StopLossRuntimeContext,
) -> Vec<FuturesStopCloseDirective> {
    let Some(last_price) = last_price.filter(|value| value.is_finite()) else {
        return Vec::new();
    };
    if !ctx.stop_enabled || ctx.scope != "per_trade" || ctx.account_type != "FUTURES" {
        return Vec::new();
    }
    let side_label = normalize_trade_side(side_label.as_ref());
    if !matches!(side_label.as_str(), "BUY" | "SELL") {
        return Vec::new();
    }
    let close_side = if side_label == "BUY" { "SELL" } else { "BUY" };
    let position_side = if dual_side {
        Some(if side_label == "BUY" { "LONG" } else { "SHORT" }.to_owned())
    } else {
        None
    };
    entries
        .iter()
        .filter_map(|entry| {
            let qty = finite_non_negative(entry.qty);
            let entry_price = finite_non_negative(entry.entry_price);
            if qty <= 0.0 || entry_price <= 0.0 {
                return None;
            }
            let loss_usdt = if side_label == "BUY" {
                (entry_price - last_price).max(0.0) * qty
            } else {
                (last_price - entry_price).max(0.0) * qty
            };
            let denom = entry_price * qty;
            let price_pct = if denom > 0.0 {
                loss_usdt / denom * 100.0
            } else {
                0.0
            };
            let margin_entry = if entry.margin_usdt > 0.0 {
                entry.margin_usdt
            } else if entry.leverage > 0.0 {
                denom / entry.leverage
            } else {
                denom
            };
            let margin_pct = if margin_entry > 0.0 {
                loss_usdt / margin_entry * 100.0
            } else {
                0.0
            };
            let effective_pct = price_pct.max(margin_pct);
            if !stop_threshold_triggered(ctx, loss_usdt, effective_pct) {
                return None;
            }
            Some(FuturesStopCloseDirective {
                symbol: normalize_symbol(symbol.as_ref()),
                interval: interval.as_ref().trim().to_owned(),
                side_label: side_label.clone(),
                close_side: close_side.to_owned(),
                position_side: position_side.clone(),
                qty,
                reason: "per_trade_stop_loss".to_owned(),
                loss_usdt,
                price_loss_percent: price_pct,
                margin_loss_percent: margin_pct,
            })
        })
        .collect()
}

pub fn evaluate_directional_futures_stop_loss(
    symbol: impl AsRef<str>,
    interval: impl AsRef<str>,
    long_qty: f64,
    long_entry_price: f64,
    short_qty: f64,
    short_entry_price: f64,
    long_position: Option<&FuturesRiskPosition>,
    short_position: Option<&FuturesRiskPosition>,
    last_price: Option<f64>,
    dual_side: bool,
    ctx: &StopLossRuntimeContext,
) -> Vec<FuturesStopCloseDirective> {
    let Some(last_price) = last_price.filter(|value| value.is_finite()) else {
        return Vec::new();
    };
    if !ctx.stop_enabled || ctx.scope == "per_trade" || ctx.is_cumulative {
        return Vec::new();
    }
    let mut directives = Vec::new();
    if let Some(directive) = evaluate_directional_leg(
        symbol.as_ref(),
        interval.as_ref(),
        "BUY",
        long_qty,
        long_entry_price,
        long_position,
        last_price,
        dual_side,
        ctx,
    ) {
        directives.push(directive);
    }
    if let Some(directive) = evaluate_directional_leg(
        symbol.as_ref(),
        interval.as_ref(),
        "SELL",
        short_qty,
        short_entry_price,
        short_position,
        last_price,
        dual_side,
        ctx,
    ) {
        directives.push(directive);
    }
    directives
}

pub fn evaluate_cumulative_futures_stop_loss(
    symbol: impl AsRef<str>,
    interval: impl AsRef<str>,
    positions: &[FuturesRiskPosition],
    last_price: Option<f64>,
    dual_side: bool,
    ctx: &StopLossRuntimeContext,
) -> Vec<FuturesStopCloseDirective> {
    let Some(last_price) = last_price.filter(|value| value.is_finite()) else {
        return Vec::new();
    };
    if !ctx.stop_enabled || !ctx.is_cumulative || ctx.account_type != "FUTURES" {
        return Vec::new();
    }
    let symbol = normalize_symbol(symbol.as_ref());
    let mut long = CumulativeSideTotals::default();
    let mut short = CumulativeSideTotals::default();
    for position in positions {
        if normalize_symbol(&position.symbol) != symbol || position.entry_price <= 0.0 {
            continue;
        }
        let Some((side_key, qty)) = position_side_and_qty(position, dual_side) else {
            continue;
        };
        if qty <= 0.0 {
            continue;
        }
        let margin = position_margin(position);
        let loss = if side_key == "LONG" {
            (position.entry_price - last_price).max(0.0) * qty
        } else {
            (last_price - position.entry_price).max(0.0) * qty
        };
        let totals = if side_key == "LONG" {
            &mut long
        } else {
            &mut short
        };
        totals.qty += qty;
        totals.loss += loss;
        totals.margin += margin.max(0.0);
    }

    let mut directives = Vec::new();
    if let Some(directive) =
        cumulative_directive(&symbol, interval.as_ref(), "LONG", &long, dual_side, ctx)
    {
        directives.push(directive);
    }
    if let Some(directive) =
        cumulative_directive(&symbol, interval.as_ref(), "SHORT", &short, dual_side, ctx)
    {
        directives.push(directive);
    }
    directives
}

pub fn evaluate_entire_account_stop_loss(
    ctx: &StopLossRuntimeContext,
    total_unrealized: f64,
    total_wallet: f64,
) -> EntireAccountStopDecision {
    if ctx.account_type != "FUTURES" || !ctx.is_entire_account {
        return EntireAccountStopDecision {
            triggered: false,
            reason: String::new(),
            total_unrealized,
            total_wallet,
            loss_percent: 0.0,
        };
    }
    if ctx.apply_usdt_limit && total_unrealized <= -ctx.stop_usdt_limit {
        return EntireAccountStopDecision {
            triggered: true,
            reason: format!("entire-account-usdt-limit ({total_unrealized:.2})"),
            total_unrealized,
            total_wallet,
            loss_percent: 0.0,
        };
    }
    if ctx.apply_percent_limit && total_wallet > 0.0 && total_unrealized < 0.0 {
        let loss_percent = total_unrealized.abs() / total_wallet * 100.0;
        if loss_percent >= ctx.stop_percent_limit {
            return EntireAccountStopDecision {
                triggered: true,
                reason: format!("entire-account-percent-limit ({loss_percent:.2}%)"),
                total_unrealized,
                total_wallet,
                loss_percent,
            };
        }
    }
    EntireAccountStopDecision {
        triggered: false,
        reason: String::new(),
        total_unrealized,
        total_wallet,
        loss_percent: 0.0,
    }
}

pub fn has_opposite_live(
    positions: &[FuturesRiskPosition],
    symbol: impl AsRef<str>,
    opposite_side: impl AsRef<str>,
) -> bool {
    let symbol = normalize_symbol(symbol.as_ref());
    let opposite_side = normalize_trade_side(opposite_side.as_ref());
    let tol = 1e-9;
    for position in positions {
        if normalize_symbol(&position.symbol) != symbol {
            continue;
        }
        let position_side = position.position_side.trim().to_uppercase();
        let amt = position.position_amt;
        if opposite_side == "BUY" {
            if (position_side == "LONG" && amt > tol)
                || ((position_side == "BOTH" || position_side.is_empty()) && amt > tol)
            {
                return true;
            }
        } else if opposite_side == "SELL"
            && ((position_side == "SHORT" && amt < -tol)
                || ((position_side == "BOTH" || position_side.is_empty()) && amt < -tol))
        {
            return true;
        }
    }
    false
}

pub fn plan_close_opposite_position(
    request: &CloseOppositeRequest,
    positions: &[FuturesRiskPosition],
) -> CloseOppositePlan {
    let symbol = normalize_symbol(&request.symbol);
    let interval = request.interval.trim().to_owned();
    let desired = normalize_trade_side(&request.next_side);
    if !matches!(desired.as_str(), "BUY" | "SELL") {
        return close_opposite_plan(
            true,
            CloseOppositeAction::InvalidSideAllowsNoop,
            symbol,
            interval,
            desired,
            String::new(),
            None,
            "invalid desired side; no close-opposite action required",
        );
    }
    let opposite = if desired == "BUY" { "SELL" } else { "BUY" }.to_owned();
    let indicator_tokens = normalize_tokens(&request.indicator_tokens);
    let signature_tokens = normalize_tokens(&request.signature_tokens);
    let allow_opposite_requested =
        request.allow_opposite_positions && !request.hedge_preserve_opposites;

    if request.dual_side && indicator_tokens.is_empty() && signature_tokens.is_empty() {
        return close_opposite_plan(
            true,
            CloseOppositeAction::SkipHedgeScopeMissing,
            symbol,
            interval,
            desired,
            opposite,
            None,
            "hedge scope missing",
        );
    }
    if allow_opposite_requested && (indicator_tokens.is_empty() || signature_tokens.is_empty()) {
        return close_opposite_plan(
            true,
            CloseOppositeAction::SkipHedgeIsolationScopeMissing,
            symbol,
            interval,
            desired,
            opposite,
            None,
            "hedge isolation missing indicator/signature scope",
        );
    }
    if request.strict_indicator_flip_enforcement
        && !indicator_tokens.is_empty()
        && signature_tokens.is_empty()
    {
        return close_opposite_plan(
            true,
            CloseOppositeAction::SkipMissingOppositeSignature,
            symbol,
            interval,
            desired,
            opposite,
            None,
            "missing opposite signature for indicator scope",
        );
    }
    let live_opposite = has_opposite_live(positions, &symbol, &opposite);
    if !live_opposite {
        return close_opposite_plan(
            true,
            CloseOppositeAction::AlreadyFlat,
            symbol,
            interval,
            desired,
            opposite,
            None,
            "opposite exposure already flat",
        );
    }
    let position_side = if request.dual_side {
        Some(if opposite == "BUY" { "LONG" } else { "SHORT" }.to_owned())
    } else {
        None
    };
    if allow_opposite_requested && !indicator_tokens.is_empty() {
        close_opposite_plan(
            false,
            CloseOppositeAction::CloseIndicatorScopeBeforeOpen,
            symbol,
            interval,
            desired,
            opposite,
            position_side,
            "close indicator-scoped opposite exposure before opening",
        )
    } else {
        close_opposite_plan(
            false,
            CloseOppositeAction::CloseSymbolLevelBeforeOpen,
            symbol,
            interval,
            desired,
            opposite,
            position_side,
            "close symbol-level opposite exposure before opening",
        )
    }
}

fn evaluate_directional_leg(
    symbol: &str,
    interval: &str,
    side_label: &str,
    qty: f64,
    entry_price: f64,
    position: Option<&FuturesRiskPosition>,
    last_price: f64,
    dual_side: bool,
    ctx: &StopLossRuntimeContext,
) -> Option<FuturesStopCloseDirective> {
    let qty = finite_non_negative(qty);
    let entry_price = finite_non_negative(entry_price);
    if qty <= 0.0 || entry_price <= 0.0 {
        return None;
    }
    let loss_usdt = if side_label == "BUY" {
        (entry_price - last_price).max(0.0) * qty
    } else {
        (last_price - entry_price).max(0.0) * qty
    };
    let denom = entry_price * qty;
    let price_pct = if denom > 0.0 {
        loss_usdt / denom * 100.0
    } else {
        0.0
    };
    let (margin_pct, ratio_pct) = match position {
        Some(position) => {
            let margin = position_margin(position);
            let margin_share = if margin > 0.0 { margin } else { denom };
            let margin_pct = if margin_share > 0.0 {
                loss_usdt / margin_share * 100.0
            } else {
                0.0
            };
            let ratio = normalized_margin_ratio(position.margin_ratio);
            let fallback_ratio =
                if ratio <= 0.0 && position.maint_margin > 0.0 && position.margin_balance > 0.0 {
                    ((position.maint_margin + loss_usdt) / position.margin_balance) * 100.0
                } else {
                    ratio
                };
            (margin_pct, fallback_ratio)
        }
        None => (0.0, 0.0),
    };
    let effective_pct = price_pct.max(margin_pct).max(ratio_pct);
    if !stop_threshold_triggered(ctx, loss_usdt, effective_pct) {
        return None;
    }
    let close_side = if side_label == "BUY" { "SELL" } else { "BUY" };
    Some(FuturesStopCloseDirective {
        symbol: normalize_symbol(symbol),
        interval: interval.trim().to_owned(),
        side_label: side_label.to_owned(),
        close_side: close_side.to_owned(),
        position_side: if dual_side {
            Some(if side_label == "BUY" { "LONG" } else { "SHORT" }.to_owned())
        } else {
            None
        },
        qty,
        reason: if side_label == "BUY" {
            "stop_loss_long"
        } else {
            "stop_loss_short"
        }
        .to_owned(),
        loss_usdt,
        price_loss_percent: price_pct,
        margin_loss_percent: margin_pct.max(ratio_pct),
    })
}

fn cumulative_directive(
    symbol: &str,
    interval: &str,
    side_key: &str,
    totals: &CumulativeSideTotals,
    dual_side: bool,
    ctx: &StopLossRuntimeContext,
) -> Option<FuturesStopCloseDirective> {
    if totals.qty <= 0.0 {
        return None;
    }
    let margin_pct = if totals.margin > 0.0 {
        totals.loss / totals.margin * 100.0
    } else {
        0.0
    };
    if !stop_threshold_triggered(ctx, totals.loss, margin_pct) {
        return None;
    }
    let close_side = if side_key == "LONG" { "SELL" } else { "BUY" };
    Some(FuturesStopCloseDirective {
        symbol: symbol.to_owned(),
        interval: interval.trim().to_owned(),
        side_label: if side_key == "LONG" { "BUY" } else { "SELL" }.to_owned(),
        close_side: close_side.to_owned(),
        position_side: if dual_side {
            Some(side_key.to_owned())
        } else {
            None
        },
        qty: totals.qty,
        reason: "cumulative_stop_loss".to_owned(),
        loss_usdt: totals.loss,
        price_loss_percent: 0.0,
        margin_loss_percent: margin_pct,
    })
}

fn stop_threshold_triggered(ctx: &StopLossRuntimeContext, loss_usdt: f64, loss_pct: f64) -> bool {
    (ctx.apply_usdt_limit && loss_usdt >= ctx.stop_usdt_limit)
        || (ctx.apply_percent_limit && loss_pct >= ctx.stop_percent_limit)
}

fn position_side_and_qty(
    position: &FuturesRiskPosition,
    dual_side: bool,
) -> Option<(&'static str, f64)> {
    let amt = position.position_amt;
    if dual_side {
        match position.position_side.trim().to_uppercase().as_str() {
            "LONG" => Some(("LONG", amt.max(0.0))),
            "SHORT" => Some(("SHORT", amt.abs().max(0.0))),
            _ => None,
        }
    } else if amt > 0.0 {
        Some(("LONG", amt))
    } else if amt < 0.0 {
        Some(("SHORT", amt.abs()))
    } else {
        None
    }
}

fn position_margin(position: &FuturesRiskPosition) -> f64 {
    if position.isolated_wallet > 0.0 {
        return position.isolated_wallet;
    }
    if position.initial_margin > 0.0 {
        return position.initial_margin;
    }
    let leverage = if position.leverage > 0.0 {
        position.leverage
    } else {
        1.0
    };
    let notional = position.notional.abs();
    if notional > 0.0 && leverage > 0.0 {
        notional / leverage
    } else {
        0.0
    }
}

fn normalized_margin_ratio(value: f64) -> f64 {
    if !value.is_finite() || value <= 0.0 {
        return 0.0;
    }
    if value <= 1.0 { value * 100.0 } else { value }
}

fn close_opposite_plan(
    allowed_to_open_now: bool,
    action: CloseOppositeAction,
    symbol: String,
    interval: String,
    desired_side: String,
    opposite_side: String,
    position_side: Option<String>,
    reason: &str,
) -> CloseOppositePlan {
    let close_side = if opposite_side == "BUY" {
        "SELL"
    } else if opposite_side == "SELL" {
        "BUY"
    } else {
        ""
    };
    CloseOppositePlan {
        allowed_to_open_now,
        action,
        symbol,
        interval,
        desired_side,
        opposite_side,
        close_side: close_side.to_owned(),
        position_side,
        reason: reason.to_owned(),
    }
}

fn normalize_choice(value: &str, choices: &[&str], default_value: &str) -> String {
    let text = value.trim().to_lowercase();
    if choices.iter().any(|choice| *choice == text) {
        text
    } else {
        default_value.to_owned()
    }
}

fn normalize_trade_side(value: &str) -> String {
    match value.trim().to_uppercase().as_str() {
        "LONG" | "L" => "BUY".to_owned(),
        "SHORT" | "S" => "SELL".to_owned(),
        other => other.to_owned(),
    }
}

fn normalize_symbol(value: &str) -> String {
    value.trim().to_uppercase()
}

fn normalize_tokens(values: &[String]) -> Vec<String> {
    values
        .iter()
        .map(|value| value.trim().to_lowercase())
        .filter(|value| !value.is_empty())
        .collect()
}

fn finite_non_negative(value: f64) -> f64 {
    if value.is_finite() {
        value.max(0.0)
    } else {
        0.0
    }
}

#[derive(Debug, Default)]
struct CumulativeSideTotals {
    qty: f64,
    loss: f64,
    margin: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stop_ctx(mode: &str, scope: &str, usdt: f64, percent: f64) -> StopLossRuntimeContext {
        build_stop_loss_runtime_context(
            StopLossSettings {
                enabled: true,
                mode: mode.to_owned(),
                usdt,
                percent,
                scope: scope.to_owned(),
            },
            "FUTURES",
        )
    }

    #[test]
    fn stop_loss_settings_normalize_like_python_settings() {
        let invalid = normalize_stop_loss_settings(StopLossSettings {
            enabled: true,
            mode: "invalid".to_owned(),
            usdt: -10.0,
            percent: f64::NAN,
            scope: "bad".to_owned(),
        });
        assert_eq!(
            invalid,
            StopLossSettings {
                enabled: true,
                mode: "usdt".to_owned(),
                usdt: 0.0,
                percent: 0.0,
                scope: "per_trade".to_owned(),
            }
        );

        let ctx = stop_ctx("both", "cumulative", 25.0, 3.5);
        assert!(ctx.stop_enabled);
        assert!(ctx.apply_usdt_limit);
        assert!(ctx.apply_percent_limit);
        assert!(ctx.is_cumulative);
        assert!(!ctx.is_entire_account);
    }

    #[test]
    fn per_trade_stop_loss_uses_margin_percent_and_python_close_side() {
        let ctx = stop_ctx("percent", "per_trade", 0.0, 20.0);
        let directives = evaluate_per_trade_stop_loss(
            "btcusdt",
            "1m",
            "BUY",
            &[FuturesLegEntry {
                qty: 1.0,
                entry_price: 100.0,
                leverage: 5.0,
                margin_usdt: 0.0,
                ..Default::default()
            }],
            Some(95.0),
            true,
            &ctx,
        );
        assert_eq!(directives.len(), 1);
        let directive = &directives[0];
        assert_eq!(directive.symbol, "BTCUSDT");
        assert_eq!(directive.close_side, "SELL");
        assert_eq!(directive.position_side, Some("LONG".to_owned()));
        assert_eq!(directive.reason, "per_trade_stop_loss");
        assert_eq!(directive.loss_usdt, 5.0);
        assert_eq!(directive.price_loss_percent, 5.0);
        assert_eq!(directive.margin_loss_percent, 25.0);
    }

    #[test]
    fn cumulative_stop_loss_aggregates_by_side_like_python() {
        let ctx = stop_ctx("both", "cumulative", 8.0, 50.0);
        let positions = vec![
            FuturesRiskPosition {
                symbol: "BTCUSDT".to_owned(),
                position_side: "LONG".to_owned(),
                position_amt: 0.5,
                entry_price: 100.0,
                isolated_wallet: 10.0,
                ..Default::default()
            },
            FuturesRiskPosition {
                symbol: "BTCUSDT".to_owned(),
                position_side: "SHORT".to_owned(),
                position_amt: -0.25,
                entry_price: 80.0,
                isolated_wallet: 10.0,
                ..Default::default()
            },
        ];
        let directives = evaluate_cumulative_futures_stop_loss(
            "btcusdt",
            "5m",
            &positions,
            Some(110.0),
            true,
            &ctx,
        );
        assert_eq!(directives.len(), 1);
        assert_eq!(directives[0].side_label, "SELL");
        assert_eq!(directives[0].close_side, "BUY");
        assert_eq!(directives[0].position_side, Some("SHORT".to_owned()));
        assert_eq!(directives[0].qty, 0.25);
        assert_eq!(directives[0].loss_usdt, 7.5);
        assert_eq!(directives[0].reason, "cumulative_stop_loss");
    }

    #[test]
    fn entire_account_stop_loss_matches_python_usdt_and_percent_reasons() {
        let ctx = stop_ctx("usdt", "entire_account", 50.0, 0.0);
        let usdt = evaluate_entire_account_stop_loss(&ctx, -55.125, 1_000.0);
        assert!(usdt.triggered);
        assert_eq!(usdt.reason, "entire-account-usdt-limit (-55.12)");

        let ctx = stop_ctx("percent", "entire_account", 0.0, 5.0);
        let pct = evaluate_entire_account_stop_loss(&ctx, -75.0, 1_000.0);
        assert!(pct.triggered);
        assert_eq!(pct.reason, "entire-account-percent-limit (7.50%)");
        assert_eq!(pct.loss_percent, 7.5);
    }

    #[test]
    fn directional_stop_loss_uses_margin_ratio_fallback() {
        let mut ctx = stop_ctx("percent", "directional", 0.0, 20.0);
        ctx.scope = "directional".to_owned();
        let directive = evaluate_directional_futures_stop_loss(
            "ETHUSDT",
            "15m",
            1.0,
            100.0,
            0.0,
            0.0,
            Some(&FuturesRiskPosition {
                margin_ratio: 0.25,
                ..Default::default()
            }),
            None,
            Some(99.0),
            false,
            &ctx,
        );
        assert_eq!(directive.len(), 1);
        assert_eq!(directive[0].reason, "stop_loss_long");
        assert_eq!(directive[0].close_side, "SELL");
        assert!(directive[0].margin_loss_percent >= 25.0);
    }

    #[test]
    fn close_opposite_plan_respects_python_hedge_scope_skips() {
        let request = CloseOppositeRequest {
            symbol: "btcusdt".to_owned(),
            interval: "1m".to_owned(),
            next_side: "BUY".to_owned(),
            dual_side: true,
            ..Default::default()
        };
        let plan = plan_close_opposite_position(&request, &[]);
        assert!(plan.allowed_to_open_now);
        assert_eq!(plan.action, CloseOppositeAction::SkipHedgeScopeMissing);
        assert_eq!(plan.opposite_side, "SELL");
    }

    #[test]
    fn close_opposite_plan_requires_symbol_close_when_opposite_live() {
        let request = CloseOppositeRequest {
            symbol: "btcusdt".to_owned(),
            interval: "1m".to_owned(),
            next_side: "BUY".to_owned(),
            dual_side: false,
            allow_opposite_positions: false,
            ..Default::default()
        };
        let positions = vec![FuturesRiskPosition {
            symbol: "BTCUSDT".to_owned(),
            position_side: "BOTH".to_owned(),
            position_amt: -0.5,
            ..Default::default()
        }];
        let plan = plan_close_opposite_position(&request, &positions);
        assert!(!plan.allowed_to_open_now);
        assert_eq!(plan.action, CloseOppositeAction::CloseSymbolLevelBeforeOpen);
        assert_eq!(plan.close_side, "BUY");
        assert_eq!(plan.position_side, None);
    }

    #[test]
    fn close_opposite_plan_requires_indicator_scope_close_in_hedge_mode() {
        let request = CloseOppositeRequest {
            symbol: "btcusdt".to_owned(),
            interval: "1m".to_owned(),
            next_side: "SELL".to_owned(),
            dual_side: true,
            allow_opposite_positions: true,
            indicator_tokens: vec!["RSI".to_owned()],
            signature_tokens: vec!["rsi".to_owned()],
            ..Default::default()
        };
        let positions = vec![FuturesRiskPosition {
            symbol: "BTCUSDT".to_owned(),
            position_side: "LONG".to_owned(),
            position_amt: 0.5,
            ..Default::default()
        }];
        let plan = plan_close_opposite_position(&request, &positions);
        assert!(!plan.allowed_to_open_now);
        assert_eq!(
            plan.action,
            CloseOppositeAction::CloseIndicatorScopeBeforeOpen
        );
        assert_eq!(plan.opposite_side, "BUY");
        assert_eq!(plan.close_side, "SELL");
        assert_eq!(plan.position_side, Some("LONG".to_owned()));
    }
}
