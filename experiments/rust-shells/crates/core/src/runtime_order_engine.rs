use anyhow::{Result, anyhow};
use serde_json::{Value, json};
use std::path::PathBuf;

use crate::order_audit::{
    ConnectorOrderBlockIncident, ConnectorOrderCircuitBreaker, ConnectorOrderCircuitBreakerConfig,
    ConnectorOrderCircuitBreakerSnapshot, DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_BACKUP_COUNT,
    DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH,
    DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_MAX_BYTES, OrderAuditConfig, OrderAuditEvent,
    OrderAuditStatus, OrderAuditWriteError, append_connector_order_circuit_incident,
    append_order_audit_event, build_connector_order_circuit_incident, build_order_audit_status,
    redact_order_params,
};
use crate::order_guard::{
    BinanceOrderSubmitGuardInput, BinanceOrderSubmitGuardResult, LiveTradingSafetyConfig,
    OrderSymbolFilters, guard_live_order_submit,
};
use crate::orders::{BinanceFuturesOrderParams, BinanceFuturesOrderResult};
use crate::position_close::{
    BinanceFuturesCloseDirective, BinanceFuturesCloseMethod, build_reduce_only_close_params,
};
use crate::risk::{CloseOppositePlan, FuturesStopCloseDirective};

#[derive(Debug, Clone)]
pub struct RuntimeOrderEngine {
    pub mode: String,
    pub api_key: String,
    pub api_secret: String,
    pub account_type: String,
    pub leverage: i64,
    pub margin_mode: String,
    pub position_pct: f64,
    pub safety: LiveTradingSafetyConfig,
    pub audit_config: OrderAuditConfig,
    pub circuit: ConnectorOrderCircuitBreaker,
    pub connector_incident_path: PathBuf,
    pub connector_incident_max_bytes: u64,
    pub connector_incident_backup_count: usize,
    pub live_submit_attempt_count: i64,
    audit_last_write_error: Option<OrderAuditWriteError>,
    audit_last_write_error_at: String,
    audit_last_write_ok_at: String,
}

impl RuntimeOrderEngine {
    pub fn new(
        mode: impl Into<String>,
        audit_config: OrderAuditConfig,
        circuit_config: ConnectorOrderCircuitBreakerConfig,
        now_iso: impl AsRef<str>,
    ) -> Self {
        Self {
            mode: mode.into(),
            api_key: String::new(),
            api_secret: String::new(),
            account_type: "FUTURES".to_owned(),
            leverage: 1,
            margin_mode: String::new(),
            position_pct: 2.0,
            safety: LiveTradingSafetyConfig::default(),
            audit_config,
            circuit: ConnectorOrderCircuitBreaker::new(circuit_config, now_iso.as_ref()),
            connector_incident_path: PathBuf::from(
                DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH,
            ),
            connector_incident_max_bytes: DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_MAX_BYTES,
            connector_incident_backup_count: DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_BACKUP_COUNT,
            live_submit_attempt_count: 0,
            audit_last_write_error: None,
            audit_last_write_error_at: String::new(),
            audit_last_write_ok_at: String::new(),
        }
    }

    pub fn audit_status(&self) -> OrderAuditStatus {
        build_order_audit_status(
            &self.audit_config,
            self.audit_last_write_error.clone(),
            &self.audit_last_write_error_at,
            &self.audit_last_write_ok_at,
        )
    }

    pub fn submit_futures_order<F>(
        &mut self,
        input: RuntimeOrderSubmitInput<'_>,
        mut execute: F,
    ) -> RuntimeOrderSubmitResult
    where
        F: FnMut(&BinanceFuturesOrderParams) -> Result<BinanceFuturesOrderResult>,
    {
        let params = owned_params(&input.order.params);
        let guard = guard_live_order_submit(&BinanceOrderSubmitGuardInput {
            mode: self.mode.clone(),
            market: input.market.clone(),
            params: params.clone(),
            api_key: self.api_key.clone(),
            api_secret: self.api_secret.clone(),
            account_type: self.account_type.clone(),
            leverage: self.leverage,
            margin_mode: self.margin_mode.clone(),
            position_pct: self.position_pct,
            config: self.safety.clone(),
            filters: input.filters.clone(),
            last_price: input.last_price,
            order_audit_enabled: self.audit_config.enabled,
            order_audit_writable: self.audit_last_write_error.is_none(),
            connector_state: input.connector_state.clone(),
            connector_health: input.connector_health.clone(),
            live_submit_attempt_count: self.live_submit_attempt_count,
        });

        if !guard.allowed {
            let error = guard.errors.join("; ");
            self.write_audit(order_audit_from_params(
                "order_blocked",
                &input.market,
                &params,
                &input.now_iso,
                &input.source,
                None,
                &error,
            ));
            let circuit_snapshot =
                self.record_connector_order_block(&input, &error, input.now_epoch_seconds);
            return RuntimeOrderSubmitResult {
                allowed: false,
                guard,
                order_result: None,
                error,
                circuit_snapshot,
                audit_status: self.audit_status(),
            };
        }

        self.live_submit_attempt_count = guard.next_submit_attempt_count;
        self.write_audit(order_audit_from_params(
            "order_submit_attempt",
            &input.market,
            &params,
            &input.now_iso,
            &input.source,
            None,
            "",
        ));

        match execute(input.order) {
            Ok(order_result) => {
                self.write_audit(order_audit_from_params(
                    "order_accepted",
                    &input.market,
                    &params,
                    &input.now_iso,
                    &input.source,
                    Some(order_result_json(&order_result)),
                    "",
                ));
                RuntimeOrderSubmitResult {
                    allowed: true,
                    guard,
                    order_result: Some(order_result),
                    error: String::new(),
                    circuit_snapshot: None,
                    audit_status: self.audit_status(),
                }
            }
            Err(error) => {
                let message = error.to_string();
                self.write_audit(order_audit_from_params(
                    "order_failed",
                    &input.market,
                    &params,
                    &input.now_iso,
                    &input.source,
                    None,
                    &message,
                ));
                let circuit_snapshot =
                    self.record_connector_order_block(&input, &message, input.now_epoch_seconds);
                RuntimeOrderSubmitResult {
                    allowed: false,
                    guard,
                    order_result: None,
                    error: message,
                    circuit_snapshot,
                    audit_status: self.audit_status(),
                }
            }
        }
    }

    pub fn execute_stop_loss_closes<F>(
        &mut self,
        directives: &[FuturesStopCloseDirective],
        now_iso: impl AsRef<str>,
        source: impl AsRef<str>,
        mut execute: F,
    ) -> RuntimeCloseBatchResult
    where
        F: FnMut(&BinanceFuturesCloseDirective) -> Result<BinanceFuturesOrderResult>,
    {
        let mut batch = RuntimeCloseBatchResult::default();
        for directive in directives {
            let result = self.execute_close_with_fallback(
                &directive.symbol,
                &directive.close_side,
                directive.qty,
                directive.position_side.as_deref(),
                &directive.reason,
                now_iso.as_ref(),
                source.as_ref(),
                &mut execute,
            );
            batch.requested_qty += result.requested_qty;
            batch.closed_qty += result.closed_qty;
            batch.attempts.extend(result.attempts);
        }
        batch.remaining_qty = remaining_qty(batch.requested_qty, batch.closed_qty);
        batch.ok = batch.requested_qty <= 0.0
            || batch.remaining_qty <= close_qty_epsilon(batch.requested_qty);
        batch.audit_status = Some(self.audit_status());
        batch
    }

    pub fn execute_close_opposite_plan<F>(
        &mut self,
        plan: &CloseOppositePlan,
        target_qty: f64,
        now_iso: impl AsRef<str>,
        source: impl AsRef<str>,
        mut execute: F,
    ) -> RuntimeCloseOppositeResult
    where
        F: FnMut(&BinanceFuturesCloseDirective) -> Result<BinanceFuturesOrderResult>,
    {
        if plan.allowed_to_open_now || target_qty <= 0.0 || plan.close_side.trim().is_empty() {
            return RuntimeCloseOppositeResult {
                allowed_to_open_now: true,
                reason: plan.reason.clone(),
                close_result: RuntimeCloseBatchResult {
                    ok: true,
                    audit_status: Some(self.audit_status()),
                    ..Default::default()
                },
            };
        }

        let close_result = self.execute_close_with_fallback(
            &plan.symbol,
            &plan.close_side,
            target_qty,
            plan.position_side.as_deref(),
            "close_opposite_position",
            now_iso.as_ref(),
            source.as_ref(),
            &mut execute,
        );
        let allowed_to_open_now =
            close_result.ok && close_result.remaining_qty <= close_qty_epsilon(target_qty);
        let reason = if allowed_to_open_now {
            "opposite exposure closed".to_owned()
        } else if close_result.remaining_qty > 0.0 {
            format!(
                "opposite close residual {:.10} remains",
                close_result.remaining_qty
            )
        } else {
            "opposite close failed".to_owned()
        };
        RuntimeCloseOppositeResult {
            allowed_to_open_now,
            reason,
            close_result,
        }
    }

    fn execute_close_with_fallback<F>(
        &mut self,
        symbol: &str,
        close_side: &str,
        requested_qty: f64,
        preferred_position_side: Option<&str>,
        reason: &str,
        now_iso: &str,
        source: &str,
        execute: &mut F,
    ) -> RuntimeCloseBatchResult
    where
        F: FnMut(&BinanceFuturesCloseDirective) -> Result<BinanceFuturesOrderResult>,
    {
        let mut result = RuntimeCloseBatchResult {
            requested_qty: requested_qty.max(0.0),
            ..Default::default()
        };
        if requested_qty <= 0.0 {
            result.ok = true;
            result.audit_status = Some(self.audit_status());
            return result;
        }

        for position_side in close_position_side_attempts(close_side, preferred_position_side) {
            let directive = match close_directive(
                symbol,
                close_side,
                requested_qty,
                position_side.as_deref(),
            ) {
                Ok(directive) => directive,
                Err(error) => {
                    result.attempts.push(RuntimeCloseAttempt {
                        directive: None,
                        success: false,
                        result: None,
                        error: error.to_string(),
                    });
                    continue;
                }
            };

            self.write_close_audit(
                "order_close_attempt",
                &directive,
                now_iso,
                source,
                reason,
                None,
                "",
            );
            match execute(&directive) {
                Ok(order_result) => {
                    let closed_qty = reconciled_executed_qty(&order_result, directive.quantity);
                    self.write_close_audit(
                        "order_close_accepted",
                        &directive,
                        now_iso,
                        source,
                        reason,
                        Some(order_result_json(&order_result)),
                        "",
                    );
                    result.closed_qty += closed_qty;
                    result.attempts.push(RuntimeCloseAttempt {
                        directive: Some(directive),
                        success: true,
                        result: Some(order_result),
                        error: String::new(),
                    });
                    break;
                }
                Err(error) => {
                    let message = error.to_string();
                    self.write_close_audit(
                        "order_close_failed",
                        &directive,
                        now_iso,
                        source,
                        reason,
                        None,
                        &message,
                    );
                    result.attempts.push(RuntimeCloseAttempt {
                        directive: Some(directive),
                        success: false,
                        result: None,
                        error: message.clone(),
                    });
                    if !message
                        .to_lowercase()
                        .contains("position side does not match")
                    {
                        break;
                    }
                }
            }
        }

        result.remaining_qty = remaining_qty(result.requested_qty, result.closed_qty);
        result.ok = result.remaining_qty <= close_qty_epsilon(result.requested_qty)
            && result.attempts.iter().any(|attempt| attempt.success);
        result.audit_status = Some(self.audit_status());
        result
    }

    fn record_connector_order_block(
        &mut self,
        input: &RuntimeOrderSubmitInput<'_>,
        message: &str,
        now_epoch_seconds: f64,
    ) -> Option<ConnectorOrderCircuitBreakerSnapshot> {
        let incident = ConnectorOrderBlockIncident {
            interval: input.interval.clone(),
            account_type: self.account_type.clone(),
            connector_health: Some(Value::String(input.connector_health.clone())),
            connector_state: Some(Value::String(input.connector_state.clone())),
            connector_message: message.to_owned(),
            ..ConnectorOrderBlockIncident::new(
                now_epoch_seconds,
                &input.order.symbol,
                &input.order.side,
            )
        };
        let snapshot = self
            .circuit
            .record_connector_order_block(incident, &input.now_iso)?;
        let persisted = build_connector_order_circuit_incident(
            "trip",
            &snapshot,
            &input.source,
            &snapshot.message,
            &input.now_iso,
        );
        let _ = append_connector_order_circuit_incident(
            &self.connector_incident_path,
            &persisted,
            self.connector_incident_max_bytes,
            self.connector_incident_backup_count,
        );
        Some(snapshot)
    }

    fn write_audit(&mut self, event: OrderAuditEvent) {
        if !self.audit_config.enabled {
            self.audit_last_write_error = None;
            return;
        }
        let path = PathBuf::from(&self.audit_config.path);
        match append_order_audit_event(
            &path,
            &event,
            self.audit_config.max_bytes,
            self.audit_config.backup_count,
        ) {
            Ok(()) => {
                self.audit_last_write_error = None;
                self.audit_last_write_ok_at = event.ts;
            }
            Err(error) => {
                self.audit_last_write_error = Some(OrderAuditWriteError {
                    message: error.to_string(),
                    path: path.display().to_string(),
                });
                self.audit_last_write_error_at = event.ts;
            }
        }
    }

    fn write_close_audit(
        &mut self,
        event: &str,
        directive: &BinanceFuturesCloseDirective,
        now_iso: &str,
        source: &str,
        reason: &str,
        order_result: Option<Value>,
        error: &str,
    ) {
        self.write_audit(OrderAuditEvent {
            ts: now_iso.to_owned(),
            event: event.to_owned(),
            symbol: directive.symbol.clone(),
            side: directive.side.clone(),
            market: "futures".to_owned(),
            source: source.to_owned(),
            params: directive
                .to_order_params()
                .ok()
                .map(|params| redact_order_params(&owned_params(&params.params))),
            computed: Some(json!({
                "reason": reason,
                "position_side": directive.position_side,
                "quantity": directive.quantity,
                "closePosition": directive.close_position,
                "reduceOnly": directive.reduce_only,
            })),
            result: order_result,
            error: error.to_owned(),
            ..Default::default()
        });
    }
}

#[derive(Debug, Clone)]
pub struct RuntimeOrderSubmitInput<'a> {
    pub order: &'a BinanceFuturesOrderParams,
    pub market: String,
    pub filters: Option<OrderSymbolFilters>,
    pub last_price: Option<f64>,
    pub connector_state: String,
    pub connector_health: String,
    pub interval: String,
    pub now_iso: String,
    pub now_epoch_seconds: f64,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RuntimeOrderSubmitResult {
    pub allowed: bool,
    pub guard: BinanceOrderSubmitGuardResult,
    pub order_result: Option<BinanceFuturesOrderResult>,
    pub error: String,
    pub circuit_snapshot: Option<ConnectorOrderCircuitBreakerSnapshot>,
    pub audit_status: OrderAuditStatus,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RuntimeCloseAttempt {
    pub directive: Option<BinanceFuturesCloseDirective>,
    pub success: bool,
    pub result: Option<BinanceFuturesOrderResult>,
    pub error: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RuntimeCloseBatchResult {
    pub ok: bool,
    pub requested_qty: f64,
    pub closed_qty: f64,
    pub remaining_qty: f64,
    pub attempts: Vec<RuntimeCloseAttempt>,
    pub audit_status: Option<OrderAuditStatus>,
}

impl Default for RuntimeCloseBatchResult {
    fn default() -> Self {
        Self {
            ok: false,
            requested_qty: 0.0,
            closed_qty: 0.0,
            remaining_qty: 0.0,
            attempts: Vec::new(),
            audit_status: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RuntimeCloseOppositeResult {
    pub allowed_to_open_now: bool,
    pub reason: String,
    pub close_result: RuntimeCloseBatchResult,
}

fn order_audit_from_params(
    event: &str,
    market: &str,
    params: &[(String, String)],
    now_iso: &str,
    source: &str,
    result: Option<Value>,
    error: &str,
) -> OrderAuditEvent {
    let mut audit =
        crate::order_audit::order_audit_event_from_params(event, market, params, now_iso, source);
    audit.result = result;
    audit.error = error.to_owned();
    audit
}

fn owned_params(params: &[(&'static str, String)]) -> Vec<(String, String)> {
    params
        .iter()
        .map(|(key, value)| ((*key).to_owned(), value.clone()))
        .collect()
}

fn order_result_json(result: &BinanceFuturesOrderResult) -> Value {
    json!({
        "symbol": result.symbol,
        "side": result.side,
        "positionSide": result.position_side,
        "orderId": result.order_id,
        "status": result.status,
        "executedQty": result.executed_qty,
        "avgPrice": result.avg_price,
    })
}

fn close_directive(
    symbol: &str,
    side: &str,
    quantity: f64,
    position_side: Option<&str>,
) -> Result<BinanceFuturesCloseDirective> {
    let order =
        build_reduce_only_close_params(symbol, side, quantity, position_side.unwrap_or(""))?;
    let quantity_text = order
        .params
        .iter()
        .find(|(key, _)| *key == "quantity")
        .map(|(_, value)| value.clone())
        .ok_or_else(|| anyhow!("close order quantity missing"))?;
    let reduce_only = order
        .params
        .iter()
        .any(|(key, value)| *key == "reduceOnly" && value.eq_ignore_ascii_case("true"));
    Ok(BinanceFuturesCloseDirective {
        symbol: order.symbol,
        side: order.side,
        position_side: order.position_side,
        quantity,
        quantity_text,
        reduce_only,
        close_position: false,
        method: BinanceFuturesCloseMethod::ReduceOnly,
    })
}

fn close_position_side_attempts(close_side: &str, preferred: Option<&str>) -> Vec<Option<String>> {
    let mut attempts = Vec::new();
    push_position_side_attempt(&mut attempts, preferred);
    let hedge_side = if close_side.trim().eq_ignore_ascii_case("BUY") {
        Some("SHORT")
    } else if close_side.trim().eq_ignore_ascii_case("SELL") {
        Some("LONG")
    } else {
        None
    };
    push_position_side_attempt(&mut attempts, hedge_side);
    if !attempts.iter().any(Option::is_none) {
        attempts.push(None);
    }
    attempts
}

fn push_position_side_attempt(attempts: &mut Vec<Option<String>>, value: Option<&str>) {
    let normalized = value
        .map(|text| text.trim().to_uppercase())
        .filter(|text| !text.is_empty());
    if attempts.iter().any(|current| *current == normalized) {
        return;
    }
    attempts.push(normalized);
}

fn reconciled_executed_qty(result: &BinanceFuturesOrderResult, requested_qty: f64) -> f64 {
    if result.executed_qty.is_finite() && result.executed_qty > 0.0 {
        result.executed_qty.min(requested_qty)
    } else {
        requested_qty
    }
}

fn remaining_qty(requested: f64, closed: f64) -> f64 {
    (requested.max(0.0) - closed.max(0.0)).max(0.0)
}

fn close_qty_epsilon(qty: f64) -> f64 {
    1e-9_f64.max(qty.abs() * 1e-6)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::order_audit::{
        parse_connector_order_circuit_incident_lines, parse_order_audit_event_json_line,
    };
    use crate::order_guard::{LIVE_TRADING_ACKNOWLEDGEMENT, OrderSymbolFilters};
    use crate::orders::build_futures_market_order_params;
    use crate::risk::{
        CloseOppositeAction, CloseOppositeRequest, FuturesRiskPosition,
        plan_close_opposite_position,
    };
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_paths(name: &str) -> (PathBuf, PathBuf) {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let dir =
            std::env::temp_dir().join(format!("trading-bot-rust-runtime-order-{name}-{stamp}"));
        fs::create_dir_all(&dir).expect("temp dir");
        (dir.join("audit.jsonl"), dir.join("incidents.jsonl"))
    }

    fn live_engine(audit_path: PathBuf, incident_path: PathBuf) -> RuntimeOrderEngine {
        let mut engine = RuntimeOrderEngine::new(
            "live",
            OrderAuditConfig {
                enabled: true,
                path: audit_path.display().to_string(),
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
        engine.connector_incident_path = incident_path;
        engine.api_key = "real-key".to_owned();
        engine.api_secret = "real-secret".to_owned();
        engine.leverage = 5;
        engine.margin_mode = "isolated".to_owned();
        engine.position_pct = 2.0;
        engine.safety = LiveTradingSafetyConfig {
            live_trading_enabled: true,
            live_trading_acknowledgement: LIVE_TRADING_ACKNOWLEDGEMENT.to_owned(),
            live_trading_max_leverage: 20,
            live_trading_max_position_pct: 10.0,
            live_trading_max_session_orders: 10,
        };
        engine
    }

    fn submit_input<'a>(order: &'a BinanceFuturesOrderParams) -> RuntimeOrderSubmitInput<'a> {
        RuntimeOrderSubmitInput {
            order,
            market: "futures".to_owned(),
            filters: Some(OrderSymbolFilters {
                step_size: 0.001,
                tick_size: 0.1,
                min_qty: 0.001,
                min_notional: 5.0,
            }),
            last_price: Some(100.0),
            connector_state: "ready".to_owned(),
            connector_health: "ok".to_owned(),
            interval: "1m".to_owned(),
            now_iso: "2026-06-18T00:00:00Z".to_owned(),
            now_epoch_seconds: 1_787_020_800.0,
            source: "rust-runtime-order-engine-test".to_owned(),
        }
    }

    fn order_result(
        symbol: &str,
        side: &str,
        qty: f64,
        position_side: &str,
    ) -> BinanceFuturesOrderResult {
        BinanceFuturesOrderResult {
            symbol: symbol.to_owned(),
            side: side.to_owned(),
            position_side: position_side.to_owned(),
            order_id: "42".to_owned(),
            status: "FILLED".to_owned(),
            executed_qty: qty,
            avg_price: 100.0,
        }
    }

    #[test]
    fn runtime_order_engine_persists_guarded_order_audit_and_circuit_like_python() {
        let (audit_path, incident_path) = temp_paths("blocked");
        let mut engine = live_engine(audit_path.clone(), incident_path.clone());
        let order = build_futures_market_order_params("btcusdt", "BUY", 1.0, false, "")
            .expect("order params");
        let mut input = submit_input(&order);
        input.connector_state = "paused".to_owned();
        input.connector_health = "degraded".to_owned();

        let result =
            engine.submit_futures_order(input, |_| panic!("blocked guard must not execute"));

        assert!(!result.allowed);
        assert!(
            result
                .error
                .contains("connector health is degraded / paused")
        );
        assert!(result.circuit_snapshot.as_ref().expect("circuit").active);
        assert_eq!(engine.live_submit_attempt_count, 0);
        let audit_line = fs::read_to_string(&audit_path).expect("audit file");
        let parsed = parse_order_audit_event_json_line(audit_line.trim()).expect("audit json");
        assert_eq!(parsed.event, "order_blocked");
        assert!(parsed.error.contains("connector health"));

        let incident_text = fs::read_to_string(&incident_path).expect("incident file");
        let incident_log =
            parse_connector_order_circuit_incident_lines([incident_text.as_str()], 10);
        assert_eq!(incident_log.count, 1);
        assert_eq!(
            incident_log.events[0]["event"],
            "connector_order_circuit_trip"
        );
        fs::remove_file(audit_path).ok();
        fs::remove_file(incident_path).ok();
    }

    #[test]
    fn runtime_order_engine_executes_and_audits_successful_submit() {
        let (audit_path, incident_path) = temp_paths("accepted");
        let mut engine = live_engine(audit_path.clone(), incident_path);
        let order = build_futures_market_order_params("ethusdt", "SELL", 0.25, false, "")
            .expect("order params");

        let result = engine.submit_futures_order(submit_input(&order), |_| {
            Ok(order_result("ETHUSDT", "SELL", 0.25, "BOTH"))
        });

        assert!(result.allowed, "{:?}", result.error);
        assert_eq!(engine.live_submit_attempt_count, 1);
        assert_eq!(result.order_result.as_ref().expect("order").order_id, "42");
        let audit = fs::read_to_string(&audit_path).expect("audit");
        assert!(audit.contains("order_submit_attempt"));
        assert!(audit.contains("order_accepted"));
        fs::remove_file(audit_path).ok();
    }

    #[test]
    fn stop_loss_close_execution_uses_python_position_side_fallback_and_reconciles() {
        let (audit_path, incident_path) = temp_paths("stop-loss");
        let mut engine = live_engine(audit_path.clone(), incident_path);
        let directives = vec![FuturesStopCloseDirective {
            symbol: "BTCUSDT".to_owned(),
            interval: "1m".to_owned(),
            side_label: "SELL".to_owned(),
            close_side: "BUY".to_owned(),
            position_side: Some("LONG".to_owned()),
            qty: 2.0,
            reason: "per_trade_stop_loss".to_owned(),
            loss_usdt: 25.0,
            price_loss_percent: 2.5,
            margin_loss_percent: 25.0,
        }];
        let mut calls = 0usize;

        let result = engine.execute_stop_loss_closes(
            &directives,
            "2026-06-18T00:00:01Z",
            "stop-loss",
            |directive| {
                calls += 1;
                if directive.position_side == "LONG" {
                    return Err(anyhow!("Position side does not match user's setting."));
                }
                Ok(order_result(
                    &directive.symbol,
                    &directive.side,
                    directive.quantity,
                    &directive.position_side,
                ))
            },
        );

        assert!(result.ok);
        assert_eq!(calls, 2);
        assert_eq!(result.closed_qty, 2.0);
        assert_eq!(result.remaining_qty, 0.0);
        assert_eq!(
            result.attempts[0].directive.as_ref().unwrap().position_side,
            "LONG"
        );
        assert_eq!(
            result.attempts[1].directive.as_ref().unwrap().position_side,
            "SHORT"
        );
        let audit = fs::read_to_string(&audit_path).expect("audit");
        assert!(audit.contains("order_close_failed"));
        assert!(audit.contains("order_close_accepted"));
        fs::remove_file(audit_path).ok();
    }

    #[test]
    fn close_opposite_execution_blocks_open_until_residual_is_flat() {
        let (audit_path, incident_path) = temp_paths("close-opposite");
        let mut engine = live_engine(audit_path, incident_path);
        let request = CloseOppositeRequest {
            symbol: "btcusdt".to_owned(),
            interval: "1m".to_owned(),
            next_side: "BUY".to_owned(),
            allow_opposite_positions: false,
            ..Default::default()
        };
        let plan = plan_close_opposite_position(
            &request,
            &[FuturesRiskPosition {
                symbol: "BTCUSDT".to_owned(),
                position_side: "BOTH".to_owned(),
                position_amt: -2.0,
                ..Default::default()
            }],
        );
        assert_eq!(plan.action, CloseOppositeAction::CloseSymbolLevelBeforeOpen);

        let blocked = engine.execute_close_opposite_plan(
            &plan,
            2.0,
            "2026-06-18T00:00:02Z",
            "close-opposite",
            |directive| {
                Ok(order_result(
                    &directive.symbol,
                    &directive.side,
                    1.0,
                    "BOTH",
                ))
            },
        );
        assert!(!blocked.allowed_to_open_now);
        assert_eq!(blocked.close_result.closed_qty, 1.0);
        assert_eq!(blocked.close_result.remaining_qty, 1.0);
        assert!(blocked.reason.contains("opposite close residual"));

        let allowed = engine.execute_close_opposite_plan(
            &plan,
            2.0,
            "2026-06-18T00:00:03Z",
            "close-opposite",
            |directive| {
                Ok(order_result(
                    &directive.symbol,
                    &directive.side,
                    2.0,
                    "BOTH",
                ))
            },
        );
        assert!(allowed.allowed_to_open_now);
        assert_eq!(allowed.reason, "opposite exposure closed");
        assert_eq!(allowed.close_result.closed_qty, 2.0);
    }
}
