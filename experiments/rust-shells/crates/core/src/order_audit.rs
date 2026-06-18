use crate::order_guard::{OrderSubmitIntent, order_submit_intent_from_param_pairs};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::VecDeque;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

pub const REDACTED_TEXT: &str = "<redacted>";
pub const DEFAULT_ORDER_AUDIT_MAX_BYTES: u64 = 10 * 1024 * 1024;
pub const DEFAULT_ORDER_AUDIT_BACKUP_COUNT: usize = 1;
pub const DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_MAX_BYTES: u64 = 2 * 1024 * 1024;
pub const DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_BACKUP_COUNT: usize = 1;
pub const DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH: &str =
    "~/.trading-bot/connector_order_circuit_incidents.jsonl";

const SENSITIVE_KEY_PARTS: &[&str] = &[
    "apikey",
    "apisecret",
    "authorization",
    "bearer",
    "passphrase",
    "password",
    "privatekey",
    "secret",
    "signature",
    "token",
    "xmbxapikey",
];
const SAFE_SENSITIVE_KEY_SUFFIXES: &[&str] = &["env", "environment", "present"];
const SECRET_ASSIGNMENT_WORDS: &[&str] = &[
    "x-mbx-apikey",
    "api_key",
    "api-key",
    "api_secret",
    "api-secret",
    "llm_api_key",
    "llm-api-key",
    "access_token",
    "access-token",
    "refresh_token",
    "refresh-token",
    "token",
    "secret",
    "signature",
    "password",
    "passphrase",
    "private_key",
    "private-key",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrderAuditConfig {
    pub enabled: bool,
    pub path: String,
    pub max_bytes: u64,
    pub backup_count: usize,
}

impl Default for OrderAuditConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            path: "~/.trading-bot/order_audit.jsonl".to_owned(),
            max_bytes: DEFAULT_ORDER_AUDIT_MAX_BYTES,
            backup_count: DEFAULT_ORDER_AUDIT_BACKUP_COUNT,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OrderAuditWriteError {
    pub message: String,
    pub path: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OrderAuditStatus {
    pub enabled: bool,
    pub state: String,
    pub path: String,
    pub max_bytes: u64,
    pub backup_count: usize,
    pub write_ok: bool,
    pub last_write_error: Option<OrderAuditWriteError>,
    pub last_write_error_at: String,
    pub last_write_ok_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OrderAuditEvent {
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub ts: String,
    pub event: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub mode: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub account_type: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub connector_backend: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub symbol: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub side: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub market: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub via: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub source: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub params: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub computed: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub order_id: Option<Value>,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub error: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub extra: Option<Value>,
}

impl Default for OrderAuditEvent {
    fn default() -> Self {
        Self {
            ts: String::new(),
            event: "order_event".to_owned(),
            mode: String::new(),
            account_type: String::new(),
            connector_backend: String::new(),
            symbol: String::new(),
            side: String::new(),
            market: String::new(),
            via: String::new(),
            source: String::new(),
            params: None,
            computed: None,
            result: None,
            order_id: None,
            error: String::new(),
            extra: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorOrderCircuitBreakerConfig {
    pub enabled: bool,
    pub block_threshold: usize,
    pub block_window_seconds: f64,
}

impl Default for ConnectorOrderCircuitBreakerConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            block_threshold: 2,
            block_window_seconds: 60.0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorOrderBlockIncident {
    pub timestamp: f64,
    pub symbol: String,
    pub interval: String,
    pub side: String,
    pub account_type: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub connector_health: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub connector_state: Option<Value>,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub connector_message: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub context_key: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub signature: String,
}

impl ConnectorOrderBlockIncident {
    pub fn new(timestamp: f64, symbol: impl Into<String>, side: impl Into<String>) -> Self {
        Self {
            timestamp,
            symbol: symbol.into().trim().to_uppercase(),
            interval: String::new(),
            side: side.into().trim().to_uppercase(),
            account_type: "FUTURES".to_owned(),
            connector_health: None,
            connector_state: None,
            connector_message: String::new(),
            context_key: String::new(),
            signature: String::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorOrderCircuitBreakerSnapshot {
    pub active: bool,
    pub state: String,
    pub reason: String,
    pub message: String,
    pub block_count: usize,
    pub block_threshold: usize,
    pub block_window_seconds: f64,
    pub tripped_at: String,
    pub cleared_at: String,
    pub source: String,
    pub symbol: String,
    pub interval: String,
    pub side: String,
    pub account_type: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub connector_health: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub connector_state: Option<Value>,
    pub reset_blocked: bool,
    pub reset_blocked_reason: String,
    pub reset_blocked_at: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub last_event: Option<Value>,
    pub generated_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorOrderCircuitSnapshotInput {
    pub active: Option<bool>,
    pub state: String,
    pub reason: String,
    pub message: String,
    pub block_count: Option<usize>,
    pub block_threshold: Option<usize>,
    pub block_window_seconds: Option<f64>,
    pub tripped_at: String,
    pub cleared_at: String,
    pub source: String,
    pub symbol: String,
    pub interval: String,
    pub side: String,
    pub account_type: String,
    pub connector_health: Option<Value>,
    pub connector_state: Option<Value>,
    pub reset_blocked: bool,
    pub reset_blocked_reason: String,
    pub reset_blocked_at: String,
    pub last_event: Option<Value>,
}

impl Default for ConnectorOrderCircuitSnapshotInput {
    fn default() -> Self {
        Self {
            active: None,
            state: String::new(),
            reason: String::new(),
            message: String::new(),
            block_count: None,
            block_threshold: None,
            block_window_seconds: None,
            tripped_at: String::new(),
            cleared_at: String::new(),
            source: String::new(),
            symbol: String::new(),
            interval: String::new(),
            side: String::new(),
            account_type: String::new(),
            connector_health: None,
            connector_state: None,
            reset_blocked: false,
            reset_blocked_reason: String::new(),
            reset_blocked_at: String::new(),
            last_event: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorOrderCircuitIncident {
    pub ts: String,
    pub event: String,
    pub action: String,
    pub source: String,
    pub message: String,
    pub active: bool,
    pub state: String,
    pub reason: String,
    pub block_count: usize,
    pub block_threshold: usize,
    pub symbol: String,
    pub interval: String,
    pub side: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub connector_health: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub connector_state: Option<Value>,
    pub circuit: ConnectorOrderCircuitBreakerSnapshot,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorOrderCircuitIncidentLog {
    pub limit: usize,
    pub count: usize,
    pub total_read: usize,
    pub events: Vec<Value>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub last_event: Option<Value>,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub error: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ConnectorOrderCircuitResetInput {
    pub source: String,
    pub force: bool,
    pub reset_block_reason: String,
    pub now_iso: String,
}

impl Default for ConnectorOrderCircuitResetInput {
    fn default() -> Self {
        Self {
            source: "service".to_owned(),
            force: false,
            reset_block_reason: String::new(),
            now_iso: String::new(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ConnectorOrderCircuitBreaker {
    config: ConnectorOrderCircuitBreakerConfig,
    events: Vec<ConnectorOrderBlockIncident>,
    open: bool,
    snapshot: ConnectorOrderCircuitBreakerSnapshot,
}

impl ConnectorOrderCircuitBreaker {
    pub fn new(config: ConnectorOrderCircuitBreakerConfig, now_iso: impl AsRef<str>) -> Self {
        let normalized = normalize_connector_order_circuit_config(config);
        let snapshot = build_connector_order_circuit_breaker_snapshot(
            ConnectorOrderCircuitSnapshotInput {
                block_threshold: Some(normalized.block_threshold),
                block_window_seconds: Some(normalized.block_window_seconds),
                source: "service-bootstrap".to_owned(),
                ..Default::default()
            },
            "service-bootstrap",
            now_iso.as_ref(),
        );
        Self {
            config: normalized,
            events: Vec::new(),
            open: false,
            snapshot,
        }
    }

    pub fn record_connector_order_block(
        &mut self,
        incident: ConnectorOrderBlockIncident,
        now_iso: impl AsRef<str>,
    ) -> Option<ConnectorOrderCircuitBreakerSnapshot> {
        if !self.config.enabled {
            return None;
        }
        let cutoff = incident.timestamp - self.config.block_window_seconds;
        self.events
            .retain(|event| event.timestamp.is_finite() && event.timestamp >= cutoff);
        self.events
            .push(redact_connector_order_block_incident(incident));
        let block_count = self.events.len();
        if self.open || block_count < self.config.block_threshold {
            return None;
        }

        self.open = true;
        let latest =
            self.events.last().cloned().unwrap_or_else(|| {
                ConnectorOrderBlockIncident::new(0.0, String::new(), String::new())
            });
        let message = if latest.connector_message.trim().is_empty() {
            "Connector health circuit breaker paused trading.".to_owned()
        } else {
            redact_text(&latest.connector_message)
        };
        let snapshot = build_connector_order_circuit_breaker_snapshot(
            ConnectorOrderCircuitSnapshotInput {
                active: Some(true),
                state: "open".to_owned(),
                reason: "connector_order_block".to_owned(),
                message,
                block_count: Some(block_count),
                block_threshold: Some(self.config.block_threshold),
                block_window_seconds: Some(self.config.block_window_seconds),
                tripped_at: now_iso.as_ref().to_owned(),
                source: "strategy".to_owned(),
                symbol: latest.symbol,
                interval: latest.interval,
                side: latest.side,
                account_type: latest.account_type,
                connector_health: latest.connector_health,
                connector_state: latest.connector_state,
                ..Default::default()
            },
            "strategy",
            now_iso.as_ref(),
        );
        self.snapshot = snapshot.clone();
        Some(snapshot)
    }

    pub fn is_open(&self) -> bool {
        self.open
    }

    pub fn incidents(&self) -> &[ConnectorOrderBlockIncident] {
        &self.events
    }

    pub fn snapshot(&self) -> ConnectorOrderCircuitBreakerSnapshot {
        self.snapshot.clone()
    }

    pub fn reset_connector_order_circuit_breaker(
        &mut self,
        input: ConnectorOrderCircuitResetInput,
    ) -> ConnectorOrderCircuitBreakerSnapshot {
        let source = blank_as_default(&input.source, "service");
        if self.open && !input.force && !input.reset_block_reason.trim().is_empty() {
            let block_reason = redact_text(&input.reset_block_reason);
            self.snapshot = build_connector_order_circuit_breaker_snapshot(
                ConnectorOrderCircuitSnapshotInput {
                    active: Some(true),
                    state: "open".to_owned(),
                    message: block_reason.clone(),
                    reset_blocked: true,
                    reset_blocked_reason: block_reason,
                    reset_blocked_at: input.now_iso.clone(),
                    source: source.clone(),
                    ..snapshot_to_input(&self.snapshot)
                },
                &source,
                &input.now_iso,
            );
            return self.snapshot.clone();
        }

        self.open = false;
        self.events.clear();
        self.snapshot = build_connector_order_circuit_breaker_snapshot(
            ConnectorOrderCircuitSnapshotInput {
                active: Some(false),
                state: "closed".to_owned(),
                message: "Connector health circuit breaker reset.".to_owned(),
                cleared_at: input.now_iso.clone(),
                reset_blocked: false,
                reset_blocked_reason: String::new(),
                reset_blocked_at: String::new(),
                source,
                ..snapshot_to_input(&self.snapshot)
            },
            "service",
            &input.now_iso,
        );
        self.snapshot.clone()
    }
}

pub fn normalize_connector_order_circuit_config(
    config: ConnectorOrderCircuitBreakerConfig,
) -> ConnectorOrderCircuitBreakerConfig {
    ConnectorOrderCircuitBreakerConfig {
        enabled: config.enabled,
        block_threshold: config.block_threshold.max(1),
        block_window_seconds: if config.block_window_seconds.is_finite() {
            config.block_window_seconds.max(1.0)
        } else {
            60.0
        },
    }
}

pub fn is_sensitive_key(key: impl AsRef<str>) -> bool {
    let normalized = key
        .as_ref()
        .trim()
        .to_lowercase()
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .collect::<String>();
    if SAFE_SENSITIVE_KEY_SUFFIXES
        .iter()
        .any(|suffix| normalized.ends_with(suffix))
    {
        return false;
    }
    SENSITIVE_KEY_PARTS
        .iter()
        .any(|part| normalized.contains(part))
}

pub fn redact_text(value: impl AsRef<str>) -> String {
    let mut text = redact_bearer_text(value.as_ref());
    for word in SECRET_ASSIGNMENT_WORDS {
        text = redact_assignment_word(&text, word);
    }
    text
}

pub fn redact_value(value: Value) -> Value {
    redact_value_at_depth(value, 0)
}

pub fn redact_order_params(params: &[(String, String)]) -> Value {
    let mut object = Map::new();
    for (key, value) in params {
        let value = if is_sensitive_key(key) && !value.is_empty() {
            Value::String(REDACTED_TEXT.to_owned())
        } else {
            redact_value(Value::String(value.clone()))
        };
        object.insert(key.clone(), value);
    }
    Value::Object(object)
}

pub fn order_audit_event_from_params(
    event: impl AsRef<str>,
    market: impl AsRef<str>,
    params: &[(String, String)],
    ts: impl AsRef<str>,
    source: impl AsRef<str>,
) -> OrderAuditEvent {
    let intent = order_submit_intent_from_param_pairs(market.as_ref(), params);
    let mut audit = OrderAuditEvent {
        ts: ts.as_ref().to_owned(),
        event: blank_as_default(event.as_ref(), "order_event"),
        symbol: intent.symbol,
        side: intent.side,
        market: market.as_ref().trim().to_owned(),
        source: source.as_ref().trim().to_owned(),
        params: Some(redact_order_params(params)),
        ..Default::default()
    };
    if audit.market.is_empty() {
        audit.market = intent.market;
    }
    audit
}

pub fn order_submit_intent_from_audit_event(event: &OrderAuditEvent) -> OrderSubmitIntent {
    let mut pairs = Vec::new();
    if let Some(Value::Object(params)) = &event.params {
        for (key, value) in params {
            pairs.push((
                key.clone(),
                value
                    .as_str()
                    .map(ToOwned::to_owned)
                    .unwrap_or_else(|| value.to_string()),
            ));
        }
    }
    order_submit_intent_from_param_pairs(&event.market, &pairs)
}

pub fn finalize_order_audit_event(mut event: OrderAuditEvent) -> OrderAuditEvent {
    event.event = blank_as_default(&event.event, "order_event");
    event.symbol = event.symbol.trim().to_uppercase();
    event.side = event.side.trim().to_uppercase();
    event.market = event.market.trim().to_owned();
    event.via = event.via.trim().to_owned();
    event.source = event.source.trim().to_owned();
    event.mode = event.mode.trim().to_owned();
    event.account_type = event.account_type.trim().to_owned();
    event.connector_backend = event.connector_backend.trim().to_owned();
    event.params = event.params.map(redact_value);
    event.computed = event.computed.map(redact_value);
    event.result = event.result.map(redact_value);
    event.extra = event.extra.map(redact_value);
    event.error = redact_text(&event.error);
    if event.order_id.is_none() {
        if let Some(result) = &event.result {
            event.order_id = extract_order_id(result);
        }
    }
    event
}

pub fn extract_order_id(payload: &Value) -> Option<Value> {
    let object = payload.as_object()?;
    let candidates = object
        .get("info")
        .and_then(Value::as_object)
        .unwrap_or(object);
    for key in [
        "orderId",
        "order_id",
        "id",
        "clientOrderId",
        "client_order_id",
        "clientOrderID",
    ] {
        if let Some(value) = candidates.get(key) {
            if !value.is_null() && value.as_str().map(|text| !text.is_empty()).unwrap_or(true) {
                return Some(value.clone());
            }
        }
    }
    None
}

pub fn build_order_audit_status(
    config: &OrderAuditConfig,
    last_error: Option<OrderAuditWriteError>,
    last_write_error_at: impl AsRef<str>,
    last_write_ok_at: impl AsRef<str>,
) -> OrderAuditStatus {
    let enabled = config.enabled;
    let write_ok = last_error.is_none();
    OrderAuditStatus {
        enabled,
        state: if !enabled {
            "disabled".to_owned()
        } else if write_ok {
            "ready".to_owned()
        } else {
            "write_failed".to_owned()
        },
        path: redact_text(&config.path),
        max_bytes: config.max_bytes.max(1),
        backup_count: config.backup_count.min(100),
        write_ok,
        last_write_error: last_error.map(|error| OrderAuditWriteError {
            message: redact_text(error.message),
            path: redact_text(error.path),
        }),
        last_write_error_at: last_write_error_at.as_ref().to_owned(),
        last_write_ok_at: last_write_ok_at.as_ref().to_owned(),
    }
}

pub fn order_audit_event_json_line(event: &OrderAuditEvent) -> serde_json::Result<String> {
    serde_json::to_string(&finalize_order_audit_event(event.clone()))
}

pub fn parse_order_audit_event_json_line(
    line: impl AsRef<str>,
) -> serde_json::Result<OrderAuditEvent> {
    serde_json::from_str(line.as_ref().trim())
}

pub fn append_order_audit_event(
    path: impl AsRef<Path>,
    event: &OrderAuditEvent,
    max_bytes: u64,
    backup_count: usize,
) -> io::Result<()> {
    let line = order_audit_event_json_line(event)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    append_jsonl_line(path.as_ref(), &line, max_bytes, backup_count)
}

pub fn build_connector_order_circuit_breaker_snapshot(
    input: ConnectorOrderCircuitSnapshotInput,
    source: impl AsRef<str>,
    now_iso: impl AsRef<str>,
) -> ConnectorOrderCircuitBreakerSnapshot {
    let raw_state = input.state.trim().to_lowercase();
    let active = input.active.unwrap_or(false)
        || matches!(raw_state.as_str(), "open" | "paused" | "tripped");
    let message = if active && input.message.trim().is_empty() {
        "Connector health circuit breaker paused trading.".to_owned()
    } else {
        redact_text(&input.message)
    };
    ConnectorOrderCircuitBreakerSnapshot {
        active,
        state: if active { "open" } else { "closed" }.to_owned(),
        reason: input.reason.trim().to_owned(),
        message,
        block_count: input.block_count.unwrap_or(0),
        block_threshold: input.block_threshold.unwrap_or(2).max(1),
        block_window_seconds: input
            .block_window_seconds
            .filter(|value| value.is_finite())
            .unwrap_or(60.0)
            .max(1.0),
        tripped_at: if active && input.tripped_at.trim().is_empty() {
            now_iso.as_ref().to_owned()
        } else {
            input.tripped_at.trim().to_owned()
        },
        cleared_at: input.cleared_at.trim().to_owned(),
        source: blank_as_default(
            if input.source.trim().is_empty() {
                source.as_ref()
            } else {
                input.source.as_str()
            },
            "service",
        ),
        symbol: input.symbol.trim().to_uppercase(),
        interval: input.interval.trim().to_owned(),
        side: input.side.trim().to_uppercase(),
        account_type: input.account_type.trim().to_owned(),
        connector_health: input.connector_health.map(redact_value),
        connector_state: input.connector_state.map(redact_value),
        reset_blocked: input.reset_blocked,
        reset_blocked_reason: redact_text(&input.reset_blocked_reason),
        reset_blocked_at: input.reset_blocked_at.trim().to_owned(),
        last_event: input.last_event.map(redact_value),
        generated_at: now_iso.as_ref().to_owned(),
    }
}

pub fn build_connector_order_circuit_incident(
    action: impl AsRef<str>,
    snapshot: &ConnectorOrderCircuitBreakerSnapshot,
    source: impl AsRef<str>,
    message: impl AsRef<str>,
    ts: impl AsRef<str>,
) -> ConnectorOrderCircuitIncident {
    let action = blank_as_default(action.as_ref(), "trip");
    ConnectorOrderCircuitIncident {
        ts: ts.as_ref().to_owned(),
        event: format!("connector_order_circuit_{action}"),
        action,
        source: blank_as_default(source.as_ref(), "service"),
        message: redact_text(message),
        active: snapshot.active,
        state: snapshot.state.clone(),
        reason: snapshot.reason.clone(),
        block_count: snapshot.block_count,
        block_threshold: snapshot.block_threshold,
        symbol: snapshot.symbol.clone(),
        interval: snapshot.interval.clone(),
        side: snapshot.side.clone(),
        connector_health: snapshot.connector_health.clone().map(redact_value),
        connector_state: snapshot.connector_state.clone().map(redact_value),
        circuit: snapshot.clone(),
    }
}

pub fn connector_order_circuit_incident_json_line(
    incident: &ConnectorOrderCircuitIncident,
) -> serde_json::Result<String> {
    serde_json::to_string(incident)
}

pub fn append_connector_order_circuit_incident(
    path: impl AsRef<Path>,
    incident: &ConnectorOrderCircuitIncident,
    max_bytes: u64,
    backup_count: usize,
) -> io::Result<()> {
    let line = connector_order_circuit_incident_json_line(incident)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    append_jsonl_line(path.as_ref(), &line, max_bytes, backup_count)
}

pub fn parse_connector_order_circuit_incident_lines<'a>(
    lines: impl IntoIterator<Item = &'a str>,
    limit: usize,
) -> ConnectorOrderCircuitIncidentLog {
    let max_items = limit.clamp(1, 200);
    let mut events = VecDeque::with_capacity(max_items);
    let mut total_read = 0usize;
    for (line_index, raw_line) in lines.into_iter().enumerate() {
        let text = raw_line.trim();
        if text.is_empty() {
            continue;
        }
        total_read += 1;
        let decoded = match serde_json::from_str::<Value>(text) {
            Ok(Value::Object(_)) => {
                redact_value(serde_json::from_str::<Value>(text).unwrap_or(Value::Null))
            }
            Ok(value) => {
                let mut object = Map::new();
                object.insert(
                    "event".to_owned(),
                    Value::String("connector_order_circuit_log_parse_error".to_owned()),
                );
                object.insert("action".to_owned(), Value::String("parse_error".to_owned()));
                object.insert(
                    "line_number".to_owned(),
                    Value::Number(serde_json::Number::from(line_index + 1)),
                );
                object.insert(
                    "message".to_owned(),
                    Value::String("Incident log line was not a JSON object.".to_owned()),
                );
                object.insert("value".to_owned(), redact_value(value));
                Value::Object(object)
            }
            Err(error) => {
                let mut object = Map::new();
                object.insert(
                    "event".to_owned(),
                    Value::String("connector_order_circuit_log_parse_error".to_owned()),
                );
                object.insert("action".to_owned(), Value::String("parse_error".to_owned()));
                object.insert(
                    "line_number".to_owned(),
                    Value::Number(serde_json::Number::from(line_index + 1)),
                );
                object.insert(
                    "message".to_owned(),
                    Value::String(format!(
                        "Could not parse incident log line: {}",
                        redact_text(error.to_string())
                    )),
                );
                object.insert(
                    "raw".to_owned(),
                    Value::String(redact_text(text.chars().take(500).collect::<String>())),
                );
                Value::Object(object)
            }
        };
        if events.len() == max_items {
            events.pop_front();
        }
        events.push_back(decoded);
    }
    let events = events.into_iter().collect::<Vec<_>>();
    ConnectorOrderCircuitIncidentLog {
        limit: max_items,
        count: events.len(),
        total_read,
        last_event: events.last().cloned(),
        events,
        error: String::new(),
    }
}

pub fn jsonl_backup_path(path: impl AsRef<Path>, index: usize) -> PathBuf {
    let path = path.as_ref();
    let backup_index = index.max(1);
    let file_name = path
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_default();
    path.with_file_name(format!("{file_name}.{backup_index}"))
}

pub fn rotate_jsonl_if_needed(
    path: impl AsRef<Path>,
    incoming_bytes: u64,
    max_bytes: u64,
    backup_count: usize,
) -> io::Result<bool> {
    if max_bytes == 0 {
        return Ok(false);
    }
    let path = path.as_ref();
    let current_size = match fs::metadata(path) {
        Ok(metadata) => metadata.len(),
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(error),
    };
    if current_size + incoming_bytes <= max_bytes {
        return Ok(false);
    }
    if backup_count == 0 {
        match fs::remove_file(path) {
            Ok(()) => return Ok(true),
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(false),
            Err(error) => return Err(error),
        }
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    for index in (1..=backup_count).rev() {
        let source = if index == 1 {
            path.to_path_buf()
        } else {
            jsonl_backup_path(path, index - 1)
        };
        let target = jsonl_backup_path(path, index);
        if !source.exists() {
            continue;
        }
        if target.exists() {
            fs::remove_file(&target)?;
        }
        fs::rename(source, target)?;
    }
    Ok(true)
}

fn append_jsonl_line(
    path: &Path,
    line: &str,
    max_bytes: u64,
    backup_count: usize,
) -> io::Result<()> {
    let incoming_bytes = (line.len() + 1) as u64;
    rotate_jsonl_if_needed(path, incoming_bytes, max_bytes, backup_count)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new().append(true).create(true).open(path)?;
    file.write_all(line.as_bytes())?;
    file.write_all(b"\n")?;
    Ok(())
}

fn redact_connector_order_block_incident(
    mut incident: ConnectorOrderBlockIncident,
) -> ConnectorOrderBlockIncident {
    incident.symbol = incident.symbol.trim().to_uppercase();
    incident.side = incident.side.trim().to_uppercase();
    incident.account_type = incident.account_type.trim().to_uppercase();
    incident.connector_health = incident.connector_health.map(redact_value);
    incident.connector_state = incident.connector_state.map(redact_value);
    incident.connector_message = redact_text(&incident.connector_message);
    incident.signature = redact_text(&incident.signature);
    incident
}

fn redact_value_at_depth(value: Value, depth: usize) -> Value {
    if depth > 8 {
        return Value::String("...".to_owned());
    }
    match value {
        Value::Object(object) => {
            let mut output = Map::new();
            for (key, item) in object {
                let value = if is_sensitive_key(&key) {
                    match item {
                        Value::Null => Value::Null,
                        Value::String(text) if text.is_empty() => Value::String(String::new()),
                        _ => Value::String(REDACTED_TEXT.to_owned()),
                    }
                } else {
                    redact_value_at_depth(item, depth + 1)
                };
                output.insert(key, value);
            }
            Value::Object(output)
        }
        Value::Array(values) => Value::Array(
            values
                .into_iter()
                .map(|item| redact_value_at_depth(item, depth + 1))
                .collect(),
        ),
        Value::String(text) => Value::String(redact_text(text)),
        other => other,
    }
}

fn redact_bearer_text(value: &str) -> String {
    let words = value.split_whitespace().collect::<Vec<_>>();
    if words
        .windows(2)
        .any(|pair| pair[0].eq_ignore_ascii_case("bearer"))
    {
        let mut out = Vec::with_capacity(words.len());
        let mut redact_next = false;
        for word in words {
            if redact_next {
                out.push(REDACTED_TEXT.to_owned());
                redact_next = false;
                continue;
            }
            out.push(word.to_owned());
            if word.eq_ignore_ascii_case("bearer") {
                redact_next = true;
            }
        }
        return out.join(" ");
    }
    value.to_owned()
}

fn redact_assignment_word(value: &str, word: &str) -> String {
    let mut out = String::with_capacity(value.len());
    let mut index = 0usize;
    let lower = value.to_lowercase();
    let needles = [format!("{word}="), format!("{word}:")];
    while index < value.len() {
        let Some((relative, needle)) = needles
            .iter()
            .filter_map(|needle| lower[index..].find(needle).map(|found| (found, needle)))
            .min_by_key(|(found, _)| *found)
        else {
            out.push_str(&value[index..]);
            break;
        };
        let start = index + relative;
        let value_start = start + needle.len();
        out.push_str(&value[index..value_start]);
        let (value_end, quote) = assignment_value_end(value, value_start);
        if quote != '\0' {
            out.push(quote);
        }
        out.push_str(REDACTED_TEXT);
        if quote != '\0' && value_end < value.len() && value[value_end..].starts_with(quote) {
            out.push(quote);
            index = value_end + quote.len_utf8();
        } else {
            index = value_end;
        }
    }
    out
}

fn assignment_value_end(value: &str, start: usize) -> (usize, char) {
    let bytes = value.as_bytes();
    if start >= bytes.len() {
        return (start, '\0');
    }
    let first = bytes[start] as char;
    let quote = if first == '\'' || first == '"' {
        first
    } else {
        '\0'
    };
    let mut index = if quote == '\0' {
        start
    } else {
        start + quote.len_utf8()
    };
    while index < bytes.len() {
        let ch = bytes[index] as char;
        if quote != '\0' {
            if ch == quote {
                return (index, quote);
            }
        } else if ch.is_ascii_whitespace() || matches!(ch, ',' | ';' | '&' | '}') {
            return (index, quote);
        }
        index += ch.len_utf8();
    }
    (index, quote)
}

fn blank_as_default(value: &str, default_value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        default_value.to_owned()
    } else {
        trimmed.to_owned()
    }
}

fn snapshot_to_input(
    snapshot: &ConnectorOrderCircuitBreakerSnapshot,
) -> ConnectorOrderCircuitSnapshotInput {
    ConnectorOrderCircuitSnapshotInput {
        active: Some(snapshot.active),
        state: snapshot.state.clone(),
        reason: snapshot.reason.clone(),
        message: snapshot.message.clone(),
        block_count: Some(snapshot.block_count),
        block_threshold: Some(snapshot.block_threshold),
        block_window_seconds: Some(snapshot.block_window_seconds),
        tripped_at: snapshot.tripped_at.clone(),
        cleared_at: snapshot.cleared_at.clone(),
        source: snapshot.source.clone(),
        symbol: snapshot.symbol.clone(),
        interval: snapshot.interval.clone(),
        side: snapshot.side.clone(),
        account_type: snapshot.account_type.clone(),
        connector_health: snapshot.connector_health.clone(),
        connector_state: snapshot.connector_state.clone(),
        reset_blocked: snapshot.reset_blocked,
        reset_blocked_reason: snapshot.reset_blocked_reason.clone(),
        reset_blocked_at: snapshot.reset_blocked_at.clone(),
        last_event: snapshot.last_event.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn redacts_sensitive_params_like_python_audit() {
        let params = vec![
            ("symbol".to_owned(), "btcusdt".to_owned()),
            ("api_key".to_owned(), "abc123".to_owned()),
            ("signature".to_owned(), "sig123".to_owned()),
            ("api_key_env".to_owned(), "BINANCE_API_KEY".to_owned()),
        ];
        let redacted = redact_order_params(&params);
        assert_eq!(redacted["symbol"], "btcusdt");
        assert_eq!(redacted["api_key"], REDACTED_TEXT);
        assert_eq!(redacted["signature"], REDACTED_TEXT);
        assert_eq!(redacted["api_key_env"], "BINANCE_API_KEY");
    }

    #[test]
    fn audit_event_json_line_extracts_order_id_and_intent_fields() {
        let event = finalize_order_audit_event(OrderAuditEvent {
            ts: "2026-06-18T00:00:00Z".to_owned(),
            event: "order_accepted".to_owned(),
            symbol: "ethusdt".to_owned(),
            side: "buy".to_owned(),
            market: "futures".to_owned(),
            source: "place_futures_market_order".to_owned(),
            params: Some(redact_order_params(&[
                ("symbol".to_owned(), "ethusdt".to_owned()),
                ("side".to_owned(), "BUY".to_owned()),
                ("type".to_owned(), "MARKET".to_owned()),
                ("quantity".to_owned(), "1.5".to_owned()),
                ("reduceOnly".to_owned(), "true".to_owned()),
            ])),
            result: Some(json!({"info": {"orderId": 42, "api_secret": "do-not-log"}})),
            ..Default::default()
        });
        let line = order_audit_event_json_line(&event).expect("audit json line");
        assert!(line.contains("\"order_id\":42"));
        assert!(line.contains(REDACTED_TEXT));
        assert!(!line.contains("do-not-log"));

        let parsed = parse_order_audit_event_json_line(&line).expect("parse audit");
        let intent = order_submit_intent_from_audit_event(&parsed);
        assert_eq!(intent.symbol, "ETHUSDT");
        assert_eq!(intent.side, "BUY");
        assert_eq!(intent.order_type, "MARKET");
        assert_eq!(intent.quantity, Some(1.5));
        assert!(intent.reduce_only);
    }

    #[test]
    fn order_audit_status_matches_python_states() {
        let status = build_order_audit_status(
            &OrderAuditConfig {
                enabled: true,
                path: "secret=/tmp/order.jsonl".to_owned(),
                max_bytes: 0,
                backup_count: 101,
            },
            Some(OrderAuditWriteError {
                message: "api_key=abc failed".to_owned(),
                path: "/tmp/order.jsonl".to_owned(),
            }),
            "error-at",
            "",
        );
        assert_eq!(status.state, "write_failed");
        assert_eq!(status.max_bytes, 1);
        assert_eq!(status.backup_count, 100);
        assert!(status.path.contains(REDACTED_TEXT));
        assert_eq!(
            status.last_write_error.expect("last error").message,
            format!("api_key={REDACTED_TEXT} failed")
        );

        let disabled = build_order_audit_status(
            &OrderAuditConfig {
                enabled: false,
                ..Default::default()
            },
            None,
            "",
            "",
        );
        assert_eq!(disabled.state, "disabled");
        assert!(!disabled.enabled);
    }

    #[test]
    fn connector_order_circuit_trips_at_threshold_within_window() {
        let mut circuit = ConnectorOrderCircuitBreaker::new(
            ConnectorOrderCircuitBreakerConfig {
                enabled: true,
                block_threshold: 2,
                block_window_seconds: 60.0,
            },
            "bootstrap",
        );
        let first = ConnectorOrderBlockIncident {
            interval: "1m".to_owned(),
            account_type: "futures".to_owned(),
            connector_health: Some(json!("error")),
            connector_state: Some(json!("paused")),
            connector_message: "api_secret=hidden connector down".to_owned(),
            ..ConnectorOrderBlockIncident::new(1000.0, "btcusdt", "buy")
        };
        assert!(
            circuit
                .record_connector_order_block(first, "2026-06-18T00:00:00Z")
                .is_none()
        );
        assert!(!circuit.is_open());

        let snapshot = circuit
            .record_connector_order_block(
                ConnectorOrderBlockIncident {
                    interval: "1m".to_owned(),
                    account_type: "futures".to_owned(),
                    connector_health: Some(json!("error")),
                    connector_state: Some(json!("paused")),
                    connector_message: "api_secret=hidden connector down".to_owned(),
                    ..ConnectorOrderBlockIncident::new(1005.0, "btcusdt", "sell")
                },
                "2026-06-18T00:00:05Z",
            )
            .expect("circuit should trip");
        assert!(circuit.is_open());
        assert!(snapshot.active);
        assert_eq!(snapshot.state, "open");
        assert_eq!(snapshot.reason, "connector_order_block");
        assert_eq!(snapshot.block_count, 2);
        assert_eq!(snapshot.block_threshold, 2);
        assert_eq!(snapshot.symbol, "BTCUSDT");
        assert_eq!(snapshot.side, "SELL");
        assert!(snapshot.message.contains(REDACTED_TEXT));
    }

    #[test]
    fn connector_order_circuit_prunes_outside_window_and_reset_blocks_when_connector_still_error() {
        let mut circuit = ConnectorOrderCircuitBreaker::new(
            ConnectorOrderCircuitBreakerConfig {
                enabled: true,
                block_threshold: 2,
                block_window_seconds: 10.0,
            },
            "bootstrap",
        );
        assert!(
            circuit
                .record_connector_order_block(
                    ConnectorOrderBlockIncident::new(100.0, "BTCUSDT", "BUY"),
                    "first",
                )
                .is_none()
        );
        assert!(
            circuit
                .record_connector_order_block(
                    ConnectorOrderBlockIncident::new(120.0, "BTCUSDT", "SELL"),
                    "second",
                )
                .is_none()
        );
        assert_eq!(circuit.incidents().len(), 1);
        assert!(
            circuit
                .record_connector_order_block(
                    ConnectorOrderBlockIncident::new(121.0, "BTCUSDT", "SELL"),
                    "third",
                )
                .is_some()
        );

        let blocked =
            circuit.reset_connector_order_circuit_breaker(ConnectorOrderCircuitResetInput {
                source: "desktop".to_owned(),
                reset_block_reason: "api_key=abc connector still error".to_owned(),
                now_iso: "2026-06-18T00:01:00Z".to_owned(),
                ..Default::default()
            });
        assert!(blocked.active);
        assert!(blocked.reset_blocked);
        assert!(blocked.reset_blocked_reason.contains(REDACTED_TEXT));

        let reset =
            circuit.reset_connector_order_circuit_breaker(ConnectorOrderCircuitResetInput {
                source: "desktop".to_owned(),
                force: true,
                now_iso: "2026-06-18T00:02:00Z".to_owned(),
                ..Default::default()
            });
        assert!(!reset.active);
        assert_eq!(reset.state, "closed");
        assert_eq!(circuit.incidents().len(), 0);
    }

    #[test]
    fn connector_order_incident_lines_keep_recent_events_and_parse_errors() {
        let snapshot = build_connector_order_circuit_breaker_snapshot(
            ConnectorOrderCircuitSnapshotInput {
                active: Some(true),
                reason: "connector_order_block".to_owned(),
                message: "Bearer token-value".to_owned(),
                block_count: Some(2),
                block_threshold: Some(2),
                symbol: "btcusdt".to_owned(),
                side: "buy".to_owned(),
                connector_health: Some(json!("error")),
                connector_state: Some(json!("paused")),
                ..Default::default()
            },
            "strategy",
            "2026-06-18T00:00:00Z",
        );
        let incident = build_connector_order_circuit_incident(
            "trip",
            &snapshot,
            "service",
            "Bearer token-value",
            "2026-06-18T00:00:01Z",
        );
        let line = connector_order_circuit_incident_json_line(&incident).expect("incident line");
        assert!(line.contains("connector_order_circuit_trip"));
        assert!(line.contains(REDACTED_TEXT));
        assert!(!line.contains("token-value"));

        let log = parse_connector_order_circuit_incident_lines(
            ["not json", line.as_str(), r#"["array"]"#],
            2,
        );
        assert_eq!(log.total_read, 3);
        assert_eq!(log.count, 2);
        assert_eq!(
            log.events[1]["event"],
            "connector_order_circuit_log_parse_error"
        );
        assert!(log.last_event.is_some());
    }

    #[test]
    fn jsonl_rotation_matches_python_backup_names() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("trading-bot-rust-order-audit-{stamp}"));
        fs::create_dir_all(&dir).expect("temp dir");
        let path = dir.join("audit.jsonl");
        fs::write(&path, "first\n").expect("write seed");
        append_jsonl_line(&path, "second", 5, 1).expect("append rotated");
        assert_eq!(
            fs::read_to_string(jsonl_backup_path(&path, 1)).expect("backup"),
            "first\n"
        );
        assert_eq!(fs::read_to_string(&path).expect("current"), "second\n");
        fs::remove_file(&path).ok();
        fs::remove_file(jsonl_backup_path(&path, 1)).ok();
        fs::remove_dir(&dir).ok();
    }
}
