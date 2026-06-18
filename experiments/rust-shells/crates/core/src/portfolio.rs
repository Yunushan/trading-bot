use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PortfolioAllocation {
    pub ledger_id: String,
    pub interval: String,
    pub interval_display: String,
    pub trigger_indicators: Vec<String>,
    pub trade_id: String,
    pub client_order_id: String,
    pub order_id: String,
    pub event_uid: String,
    pub slot_id: String,
    pub context_key: String,
    pub open_time: String,
    pub close_time: String,
    pub qty: f64,
    pub margin_usdt: f64,
    pub notional: f64,
    pub pnl_value: Option<f64>,
    pub status: String,
    pub close_price: Option<f64>,
    pub entry_price: Option<f64>,
    pub leverage: Option<i64>,
}

impl Default for PortfolioAllocation {
    fn default() -> Self {
        Self {
            ledger_id: String::new(),
            interval: String::new(),
            interval_display: String::new(),
            trigger_indicators: Vec::new(),
            trade_id: String::new(),
            client_order_id: String::new(),
            order_id: String::new(),
            event_uid: String::new(),
            slot_id: String::new(),
            context_key: String::new(),
            open_time: String::new(),
            close_time: String::new(),
            qty: 0.0,
            margin_usdt: 0.0,
            notional: 0.0,
            pnl_value: None,
            status: String::new(),
            close_price: None,
            entry_price: None,
            leverage: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PortfolioPositionRecord {
    pub symbol: String,
    pub side_key: String,
    pub interval: String,
    pub quantity: Option<f64>,
    pub mark_price: Option<f64>,
    pub size_usdt: Option<f64>,
    pub margin_usdt: Option<f64>,
    pub pnl_value: Option<f64>,
    pub roi_percent: Option<f64>,
    pub leverage: Option<i64>,
    pub liquidation_price: Option<f64>,
    pub status: String,
    pub stop_loss_enabled: bool,
    pub open_time: String,
    pub close_time: String,
    pub allocations: Vec<PortfolioAllocation>,
}

impl Default for PortfolioPositionRecord {
    fn default() -> Self {
        Self {
            symbol: String::new(),
            side_key: String::new(),
            interval: String::new(),
            quantity: None,
            mark_price: None,
            size_usdt: None,
            margin_usdt: None,
            pnl_value: None,
            roi_percent: None,
            leverage: None,
            liquidation_price: None,
            status: "Active".to_owned(),
            stop_loss_enabled: false,
            open_time: String::new(),
            close_time: String::new(),
            allocations: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ServicePositionSnapshot {
    pub symbol: String,
    pub side_key: String,
    pub side_label: String,
    pub interval: String,
    pub quantity: Option<f64>,
    pub mark_price: Option<f64>,
    pub size_usdt: Option<f64>,
    pub margin_usdt: Option<f64>,
    pub pnl_value: Option<f64>,
    pub roi_percent: Option<f64>,
    pub leverage: Option<i64>,
    pub liquidation_price: Option<f64>,
    pub status: String,
    pub stop_loss_enabled: bool,
    pub open_time: String,
    pub close_time: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ServicePortfolioSnapshot {
    pub account_type: String,
    pub open_position_count: usize,
    pub closed_position_count: usize,
    pub active_pnl: Option<f64>,
    pub active_margin: Option<f64>,
    pub closed_pnl: Option<f64>,
    pub closed_margin: Option<f64>,
    pub total_balance: Option<f64>,
    pub available_balance: Option<f64>,
    pub positions: Vec<ServicePositionSnapshot>,
    pub source: String,
    pub generated_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AllocationPersistencePayload {
    pub version: u32,
    pub mode: String,
    pub timestamp: f64,
    pub entry_allocations: BTreeMap<String, Vec<PortfolioAllocation>>,
    pub open_position_records: BTreeMap<String, PortfolioPositionRecord>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ClosedAllocationUpdate {
    pub close_status: String,
    pub close_time: String,
    pub qty_reported: Option<f64>,
    pub margin_reported: Option<f64>,
    pub pnl_reported: Option<f64>,
    pub close_price_reported: Option<f64>,
    pub entry_price_reported: Option<f64>,
    pub leverage_reported: Option<i64>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct PortfolioReconciliationState {
    pub entry_allocations: BTreeMap<(String, String), Vec<PortfolioAllocation>>,
    pub open_position_records: BTreeMap<(String, String), PortfolioPositionRecord>,
    pub closed_position_records: Vec<PortfolioPositionRecord>,
    pub pending_close_times: BTreeMap<(String, String), String>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct PositionAllocationReduction {
    pub changed: bool,
    pub closed_allocations: Vec<PortfolioAllocation>,
    pub survivor_allocations: Vec<PortfolioAllocation>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct CloseAllPositionResult {
    pub symbol: String,
    pub ok: bool,
    pub skipped: bool,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct CloseAllReconciliationSummary {
    pub closed_count: usize,
    pub remaining_open_count: usize,
    pub closed_symbols: Vec<String>,
}

const POSITION_QTY_TOL: f64 = 1e-9;

pub fn side_label(side_key: impl AsRef<str>) -> String {
    match side_key.as_ref().trim().to_uppercase().as_str() {
        "L" => "Long".to_owned(),
        "S" => "Short".to_owned(),
        "SPOT" => "Spot".to_owned(),
        "" => "Unknown".to_owned(),
        other => other.to_owned(),
    }
}

pub fn build_position_snapshot(record: &PortfolioPositionRecord) -> ServicePositionSnapshot {
    ServicePositionSnapshot {
        symbol: normalized_symbol(&record.symbol),
        side_key: normalized_side_key(&record.side_key),
        side_label: side_label(&record.side_key),
        interval: non_empty_or(&record.interval, "-"),
        quantity: finite_option(record.quantity),
        mark_price: finite_option(record.mark_price),
        size_usdt: finite_option(record.size_usdt),
        margin_usdt: finite_option(record.margin_usdt),
        pnl_value: finite_option(record.pnl_value),
        roi_percent: finite_option(record.roi_percent),
        leverage: record.leverage.filter(|value| *value > 0),
        liquidation_price: finite_option(record.liquidation_price),
        status: non_empty_or(&record.status, "Active"),
        stop_loss_enabled: record.stop_loss_enabled,
        open_time: non_empty_or(&record.open_time, "-"),
        close_time: non_empty_or(&record.close_time, "-"),
    }
}

pub fn build_portfolio_snapshot(
    account_type: impl AsRef<str>,
    open_records: &[PortfolioPositionRecord],
    closed_records: &[PortfolioPositionRecord],
    total_balance: Option<f64>,
    available_balance: Option<f64>,
    source: impl AsRef<str>,
    generated_at: impl AsRef<str>,
) -> ServicePortfolioSnapshot {
    let mut positions = open_records
        .iter()
        .map(build_position_snapshot)
        .collect::<Vec<_>>();
    positions.sort_by(|left, right| {
        (
            left.symbol.as_str(),
            left.side_key.as_str(),
            left.interval.as_str(),
            left.open_time.as_str(),
        )
            .cmp(&(
                right.symbol.as_str(),
                right.side_key.as_str(),
                right.interval.as_str(),
                right.open_time.as_str(),
            ))
    });
    let (active_pnl, active_margin) = compute_open_totals(open_records);
    let (closed_pnl, closed_margin) = compute_closed_totals(closed_records);
    ServicePortfolioSnapshot {
        account_type: non_empty_or(account_type.as_ref(), "Unknown"),
        open_position_count: positions.len(),
        closed_position_count: closed_records.len(),
        active_pnl,
        active_margin,
        closed_pnl,
        closed_margin,
        total_balance: finite_option(total_balance),
        available_balance: finite_option(available_balance),
        positions,
        source: non_empty_or(source.as_ref(), "service"),
        generated_at: generated_at.as_ref().trim().to_owned(),
    }
}

pub fn compute_open_totals(records: &[PortfolioPositionRecord]) -> (Option<f64>, Option<f64>) {
    let mut pnl_total = 0.0;
    let mut pnl_found = false;
    let mut margin_total = 0.0;
    let mut margin_found = false;
    for record in records {
        if let Some(pnl) = finite_option(record.pnl_value) {
            pnl_total += pnl;
            pnl_found = true;
        }
        let margin = finite_option(record.margin_usdt)
            .filter(|value| *value > 0.0)
            .or_else(|| allocation_margin_total(&record.allocations));
        if let Some(margin) = margin.filter(|value| *value > 0.0) {
            margin_total += margin;
            margin_found = true;
        }
    }
    (
        pnl_found.then_some(pnl_total),
        (margin_found && margin_total > 0.0).then_some(margin_total),
    )
}

pub fn compute_closed_totals(records: &[PortfolioPositionRecord]) -> (Option<f64>, Option<f64>) {
    let mut pnl_total = 0.0;
    let mut pnl_found = false;
    let mut margin_total = 0.0;
    let mut margin_found = false;
    for record in records {
        if let Some(pnl) = finite_option(record.pnl_value) {
            pnl_total += pnl;
            pnl_found = true;
        }
        if let Some(margin) = finite_option(record.margin_usdt).filter(|value| *value > 0.0) {
            margin_total += margin;
            margin_found = true;
        }
    }
    (
        pnl_found.then_some(pnl_total),
        (margin_found && margin_total > 0.0).then_some(margin_total),
    )
}

pub fn collect_allocations(allocations: &[PortfolioAllocation]) -> Vec<PortfolioAllocation> {
    let mut unique = Vec::<PortfolioAllocation>::new();
    let mut seen = BTreeMap::<String, usize>::new();
    for allocation in allocations {
        let mut entry = allocation.clone();
        if entry.interval.trim().is_empty() && !entry.interval_display.trim().is_empty() {
            entry.interval = entry.interval_display.trim().to_owned();
        }
        entry.trigger_indicators = normalized_trigger_indicators(&entry.trigger_indicators);
        let key = allocation_dedupe_key(&entry);
        if let Some(index) = seen.get(&key).copied() {
            let existing = &mut unique[index];
            existing.margin_usdt = existing.margin_usdt.max(entry.margin_usdt);
            existing.qty = existing.qty.max(entry.qty);
            existing.notional = existing.notional.max(entry.notional);
            if existing.pnl_value.is_none() {
                existing.pnl_value = entry.pnl_value;
            }
            continue;
        }
        seen.insert(key, unique.len());
        unique.push(entry);
    }
    unique.sort_by_key(allocation_sort_key);
    unique
}

pub fn update_closed_allocations(
    record: &PortfolioPositionRecord,
    allocations: &[PortfolioAllocation],
    update: &ClosedAllocationUpdate,
) -> Vec<PortfolioAllocation> {
    if allocations.is_empty() {
        return Vec::new();
    }

    let mut entries = allocations.to_vec();
    let base_qty = finite_option(record.quantity).unwrap_or(0.0).abs();
    let base_margin = finite_option(record.margin_usdt).unwrap_or(0.0);
    let base_pnl = finite_option(record.pnl_value).unwrap_or(0.0);
    let base_size = finite_option(record.size_usdt).unwrap_or(0.0);

    let mut total_qty = entries.iter().map(|entry| entry.qty.abs()).sum::<f64>();
    if total_qty <= 0.0 && base_qty > 0.0 {
        total_qty = base_qty;
    }
    let entries_count = entries.len();

    for entry in &mut entries {
        entry.status = non_empty_or(&update.close_status, "Closed");
        entry.close_time = update.close_time.trim().to_owned();
        let qty = entry.qty.abs();
        let mut ratio = if total_qty > 0.0 {
            qty / total_qty
        } else if entries_count > 0 {
            1.0 / entries_count as f64
        } else {
            0.0
        };
        if ratio <= 0.0 && entries_count > 0 {
            ratio = 1.0 / entries_count as f64;
        }
        if entry.margin_usdt <= 0.0 && base_margin > 0.0 {
            entry.margin_usdt = base_margin * ratio;
        }
        if entry.notional <= 0.0 && base_size > 0.0 {
            entry.notional = base_size * ratio;
        }
        if entry.pnl_value.is_none() {
            entry.pnl_value = Some(if base_pnl != 0.0 {
                if base_qty > 0.0 && qty > 0.0 {
                    base_pnl * (qty / base_qty)
                } else {
                    base_pnl * ratio
                }
            } else {
                base_pnl
            });
        }
    }

    let mut qty_distribution_sum = entries.iter().map(|entry| entry.qty.abs()).sum::<f64>();
    if qty_distribution_sum <= 0.0 {
        qty_distribution_sum = update.qty_reported.unwrap_or(0.0).max(0.0);
    }

    for entry in &mut entries {
        let mut share = if qty_distribution_sum > 0.0 {
            entry.qty.abs() / qty_distribution_sum
        } else if entries_count > 0 {
            1.0 / entries_count as f64
        } else {
            0.0
        };
        if share <= 0.0 && entries_count > 0 {
            share = 1.0 / entries_count as f64;
        }
        if let Some(quantity) = update.qty_reported.filter(|value| *value > 0.0) {
            entry.qty = quantity * share;
        }
        if let Some(margin) = update.margin_reported.filter(|value| *value > 0.0) {
            entry.margin_usdt = margin * share;
        }
        if let Some(pnl) = update.pnl_reported {
            entry.pnl_value = Some(pnl * share);
        }
        if let Some(close_price) = update.close_price_reported.filter(|value| *value > 0.0) {
            entry.close_price = Some(close_price);
        }
        if let Some(entry_price) = update.entry_price_reported.filter(|value| *value > 0.0) {
            if entry.entry_price.is_none() {
                entry.entry_price = Some(entry_price);
            }
        }
        if let Some(leverage) = update.leverage_reported.filter(|value| *value > 0) {
            entry.leverage = Some(leverage);
        }
    }
    entries
}

pub fn build_allocation_persistence_payload(
    mode: impl AsRef<str>,
    timestamp: f64,
    entry_allocations: &BTreeMap<(String, String), Vec<PortfolioAllocation>>,
    open_position_records: &BTreeMap<(String, String), PortfolioPositionRecord>,
) -> AllocationPersistencePayload {
    let serialized_allocations = entry_allocations
        .iter()
        .map(|(key, entries)| (serialize_allocation_key(key), collect_allocations(entries)))
        .collect::<BTreeMap<_, _>>();

    let serialized_records = open_position_records
        .iter()
        .filter_map(|(key, record)| {
            if !record.status.trim().eq_ignore_ascii_case("active") {
                return None;
            }
            Some((serialize_allocation_key(key), record.clone()))
        })
        .collect::<BTreeMap<_, _>>();

    AllocationPersistencePayload {
        version: 1,
        mode: non_empty_or(mode.as_ref(), "unknown"),
        timestamp,
        entry_allocations: serialized_allocations,
        open_position_records: serialized_records,
    }
}

pub fn reduce_position_allocation_state(
    state: &mut PortfolioReconciliationState,
    symbol: impl AsRef<str>,
    side_key: impl AsRef<str>,
    interval: Option<&str>,
    qty: Option<f64>,
    target_identity: Option<&BTreeMap<String, String>>,
) -> PositionAllocationReduction {
    let key = (
        normalized_symbol(symbol.as_ref()),
        normalized_side_key(side_key.as_ref()),
    );
    if !matches!(key.1.as_str(), "L" | "S") {
        return PositionAllocationReduction::default();
    }
    let entries = match state.entry_allocations.get(&key) {
        Some(entries) if !entries.is_empty() => entries.clone(),
        _ => return PositionAllocationReduction::default(),
    };

    let qty_value = coerce_close_quantity(qty);
    let target_payload = normalized_target_identity(target_identity);
    let mut closed_snapshots = Vec::new();
    let mut survivor_entries = entries.clone();
    let mut matched = false;

    if !target_payload.is_empty() {
        let consumed = consume_closed_entries(&entries, qty_value, None, |entry| {
            allocation_matches_target_identity(entry, &target_payload)
        });
        closed_snapshots = consumed.0;
        survivor_entries = consumed.1;
        matched = consumed.3;
    }

    if !matched {
        let consumed = consume_closed_entries(&entries, qty_value, None, |entry| {
            allocation_matches_interval(entry, interval)
        });
        closed_snapshots = consumed.0;
        survivor_entries = consumed.1;
        matched = consumed.3;
    }

    if !matched {
        return PositionAllocationReduction {
            survivor_allocations: entries,
            ..Default::default()
        };
    }

    if survivor_entries.is_empty() {
        state.entry_allocations.remove(&key);
        state.open_position_records.remove(&key);
    } else {
        state
            .entry_allocations
            .insert(key.clone(), survivor_entries.clone());
        if let Some(record) = state.open_position_records.get_mut(&key) {
            record.allocations = survivor_entries.clone();
        }
    }

    PositionAllocationReduction {
        changed: !closed_snapshots.is_empty() || survivor_entries != entries,
        closed_allocations: closed_snapshots,
        survivor_allocations: survivor_entries,
    }
}

pub fn apply_close_all_to_position_state(
    state: &mut PortfolioReconciliationState,
    results: &[CloseAllPositionResult],
    close_time: impl AsRef<str>,
    max_history: usize,
) -> CloseAllReconciliationSummary {
    let mut symbols_to_mark = BTreeSet::<String>::new();
    let mut had_error = false;
    for item in results {
        let symbol = normalized_symbol(&item.symbol);
        if symbol == "Unknown" {
            continue;
        }
        if item.ok || item.skipped {
            symbols_to_mark.insert(symbol);
        } else {
            had_error = true;
        }
    }

    if symbols_to_mark.is_empty() && !had_error && !state.open_position_records.is_empty() {
        symbols_to_mark.extend(
            state
                .open_position_records
                .keys()
                .map(|(symbol, _side)| normalized_symbol(symbol)),
        );
    }

    if symbols_to_mark.is_empty() {
        return CloseAllReconciliationSummary {
            remaining_open_count: state.open_position_records.len(),
            ..Default::default()
        };
    }

    let close_time = non_empty_or(close_time.as_ref(), "");
    let history_limit = max_history.max(1);
    let keys = state
        .open_position_records
        .keys()
        .cloned()
        .collect::<Vec<_>>();
    let mut closed_symbols = BTreeSet::<String>::new();

    for key in keys {
        if !symbols_to_mark.contains(&normalized_symbol(&key.0)) {
            continue;
        }
        let Some(mut snapshot) = state.open_position_records.remove(&key) else {
            continue;
        };
        state
            .pending_close_times
            .entry(key.clone())
            .or_insert_with(|| close_time.clone());
        snapshot.status = "Closed".to_owned();
        snapshot.close_time = close_time.clone();
        if let Some(allocations) = state.entry_allocations.remove(&key) {
            let mut closed_allocations = allocations;
            for allocation in &mut closed_allocations {
                allocation.trigger_indicators =
                    normalized_trigger_indicators(&allocation.trigger_indicators);
            }
            snapshot.allocations = closed_allocations;
        }
        closed_symbols.insert(normalized_symbol(&snapshot.symbol));
        state.closed_position_records.insert(0, snapshot);
        if state.closed_position_records.len() > history_limit {
            state.closed_position_records.truncate(history_limit);
        }
    }

    CloseAllReconciliationSummary {
        closed_count: closed_symbols.len(),
        remaining_open_count: state.open_position_records.len(),
        closed_symbols: closed_symbols.into_iter().collect(),
    }
}

pub fn serialize_allocation_key(key: &(String, String)) -> String {
    format!("{}:{}", key.0, key.1)
}

pub fn deserialize_allocation_key(key: impl AsRef<str>) -> (String, String) {
    let text = key.as_ref();
    match text.split_once(':') {
        Some((left, right)) => (left.to_owned(), right.to_owned()),
        None => (text.to_owned(), String::new()),
    }
}

fn allocation_margin_total(allocations: &[PortfolioAllocation]) -> Option<f64> {
    let total = allocations
        .iter()
        .map(|allocation| allocation.margin_usdt.max(0.0))
        .sum::<f64>();
    (total > 0.0).then_some(total)
}

fn allocation_dedupe_key(entry: &PortfolioAllocation) -> String {
    let indicators = normalized_trigger_indicators(&entry.trigger_indicators).join("|");
    let identity = allocation_identity(entry).unwrap_or_default().join("|");
    format!(
        "{}|{}|{}|{}",
        entry.ledger_id.trim(),
        allocation_interval(entry).to_lowercase(),
        indicators,
        identity
    )
}

fn allocation_identity(entry: &PortfolioAllocation) -> Option<Vec<String>> {
    let tokens = [
        &entry.trade_id,
        &entry.client_order_id,
        &entry.order_id,
        &entry.event_uid,
        &entry.slot_id,
        &entry.context_key,
        &entry.open_time,
        &entry.close_time,
    ]
    .iter()
    .map(|value| value.trim().to_owned())
    .collect::<Vec<_>>();
    tokens
        .iter()
        .any(|value| !value.is_empty())
        .then_some(tokens)
}

fn allocation_sort_key(entry: &PortfolioAllocation) -> (String, String, String, String, String) {
    (
        allocation_interval(entry).to_lowercase(),
        entry.open_time.trim().to_owned(),
        entry.trade_id.trim().to_owned(),
        entry.order_id.trim().to_owned(),
        entry.ledger_id.trim().to_owned(),
    )
}

fn allocation_interval(entry: &PortfolioAllocation) -> String {
    let display = entry.interval_display.trim();
    if !display.is_empty() {
        display.to_owned()
    } else {
        entry.interval.trim().to_owned()
    }
}

fn coerce_close_quantity(value: Option<f64>) -> Option<f64> {
    value.filter(|value| value.is_finite() && *value > 0.0)
}

fn normalized_target_identity(
    target_identity: Option<&BTreeMap<String, String>>,
) -> BTreeMap<String, String> {
    let Some(target_identity) = target_identity else {
        return BTreeMap::new();
    };
    [
        "_aggregate_key",
        "aggregate_key",
        "trade_id",
        "client_order_id",
        "order_id",
        "event_uid",
        "context_key",
        "slot_id",
        "open_time",
    ]
    .iter()
    .filter_map(|field| {
        target_identity.get(*field).and_then(|value| {
            let text = value.trim();
            (!text.is_empty()).then_some(((*field).to_owned(), text.to_owned()))
        })
    })
    .collect()
}

fn allocation_matches_target_identity(
    entry: &PortfolioAllocation,
    target_identity: &BTreeMap<String, String>,
) -> bool {
    if target_identity.is_empty() {
        return false;
    }
    for field in ["trade_id", "client_order_id", "order_id", "event_uid"] {
        if let Some(expected) = target_identity.get(field) {
            if !expected.is_empty() && allocation_identity_value(entry, field) == expected {
                return true;
            }
        }
    }

    if let Some(target_slot) = target_identity.get("slot_id") {
        if !target_slot.is_empty() && entry.slot_id.trim() == target_slot {
            if let Some(target_context) = target_identity.get("context_key") {
                let entry_context = entry.context_key.trim();
                if !target_context.is_empty()
                    && !entry_context.is_empty()
                    && entry_context != target_context
                {
                    return false;
                }
            }
            return true;
        }
    }

    if let Some(target_context) = target_identity.get("context_key") {
        if !target_context.is_empty() && entry.context_key.trim() == target_context {
            if let Some(target_open_time) = target_identity.get("open_time") {
                let entry_open_time = entry.open_time.trim();
                if !target_open_time.is_empty()
                    && !entry_open_time.is_empty()
                    && entry_open_time != target_open_time
                {
                    return false;
                }
            }
            return true;
        }
    }

    target_identity
        .get("open_time")
        .is_some_and(|target_open_time| {
            !target_open_time.is_empty() && entry.open_time.trim() == target_open_time
        })
}

fn allocation_identity_value<'a>(entry: &'a PortfolioAllocation, field: &str) -> &'a str {
    match field {
        "trade_id" => entry.trade_id.trim(),
        "client_order_id" => entry.client_order_id.trim(),
        "order_id" => entry.order_id.trim(),
        "event_uid" => entry.event_uid.trim(),
        _ => "",
    }
}

fn allocation_matches_interval(entry: &PortfolioAllocation, interval: Option<&str>) -> bool {
    let normalized_interval = interval.map(str::trim).unwrap_or_default();
    normalized_interval.is_empty()
        || allocation_interval(entry).eq_ignore_ascii_case(normalized_interval)
}

fn consume_closed_entries<F>(
    entries: &[PortfolioAllocation],
    mut qty_remaining: Option<f64>,
    close_time: Option<&str>,
    matcher: F,
) -> (
    Vec<PortfolioAllocation>,
    Vec<PortfolioAllocation>,
    Option<f64>,
    bool,
)
where
    F: Fn(&PortfolioAllocation) -> bool,
{
    let mut closed_snapshots = Vec::new();
    let mut survivors = Vec::new();
    let mut matched = false;

    for entry in entries {
        let target_match = matcher(entry);
        if target_match {
            matched = true;
        } else {
            survivors.push(entry.clone());
            continue;
        }

        let entry_qty = entry.qty.abs();
        let Some(remaining) = qty_remaining else {
            closed_snapshots.push(build_closed_allocation_snapshot(entry, close_time, None));
            continue;
        };

        if remaining <= POSITION_QTY_TOL {
            survivors.push(entry.clone());
            continue;
        }

        let qty_used = if entry_qty > POSITION_QTY_TOL {
            entry_qty.min(remaining)
        } else {
            remaining
        };

        if entry_qty > POSITION_QTY_TOL && (entry_qty - qty_used) > POSITION_QTY_TOL {
            closed_snapshots.push(build_closed_allocation_snapshot(
                entry,
                close_time,
                Some(qty_used),
            ));
            let mut survivor = entry.clone();
            let survivor_qty = (entry_qty - qty_used).max(0.0);
            survivor.qty = survivor_qty;
            scale_allocation_fields(
                &mut survivor,
                if entry_qty > 0.0 {
                    survivor_qty / entry_qty
                } else {
                    1.0
                },
            );
            survivors.push(survivor);
        } else {
            closed_snapshots.push(build_closed_allocation_snapshot(
                entry,
                close_time,
                (entry_qty > POSITION_QTY_TOL).then_some(qty_used),
            ));
        }

        qty_remaining = Some((remaining - qty_used.max(0.0)).max(0.0));
    }

    (closed_snapshots, survivors, qty_remaining, matched)
}

fn build_closed_allocation_snapshot(
    entry: &PortfolioAllocation,
    close_time: Option<&str>,
    qty_closed: Option<f64>,
) -> PortfolioAllocation {
    let mut snapshot = entry.clone();
    let entry_qty = entry.qty.abs();
    if let Some(qty_closed) = qty_closed.filter(|value| value.is_finite()) {
        if entry_qty > POSITION_QTY_TOL {
            let qty_used = qty_closed.max(0.0).min(entry_qty);
            snapshot.qty = qty_used;
            scale_allocation_fields(
                &mut snapshot,
                if entry_qty > 0.0 {
                    qty_used / entry_qty
                } else {
                    1.0
                },
            );
        }
    }
    if let Some(close_time) = close_time.map(str::trim).filter(|value| !value.is_empty()) {
        snapshot.close_time = close_time.to_owned();
    }
    snapshot.status = "Closed".to_owned();
    snapshot
}

fn scale_allocation_fields(entry: &mut PortfolioAllocation, ratio: f64) {
    if !ratio.is_finite() || ratio < 0.0 {
        return;
    }
    if entry.margin_usdt > 0.0 {
        entry.margin_usdt = (entry.margin_usdt * ratio).max(0.0);
    }
    if entry.notional > 0.0 {
        entry.notional = (entry.notional * ratio).max(0.0);
    }
}

fn normalized_trigger_indicators(values: &[String]) -> Vec<String> {
    let mut values = values
        .iter()
        .filter_map(|value| {
            let cleaned = value.trim().to_lowercase();
            (!cleaned.is_empty()).then_some(cleaned)
        })
        .collect::<Vec<_>>();
    values.sort();
    values.dedup();
    values
}

fn normalized_symbol(value: &str) -> String {
    let symbol = value.trim().to_uppercase();
    if symbol.is_empty() {
        "Unknown".to_owned()
    } else {
        symbol
    }
}

fn normalized_side_key(value: &str) -> String {
    let side = value.trim().to_uppercase();
    if side.is_empty() {
        "Unknown".to_owned()
    } else {
        side
    }
}

fn non_empty_or(value: &str, fallback: &str) -> String {
    let text = value.trim();
    if text.is_empty() {
        fallback.to_owned()
    } else {
        text.to_owned()
    }
}

fn finite_option(value: Option<f64>) -> Option<f64> {
    value.filter(|value| value.is_finite())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn allocation(id: &str, interval: &str, qty: f64, margin: f64) -> PortfolioAllocation {
        PortfolioAllocation {
            ledger_id: id.to_owned(),
            interval: interval.to_owned(),
            trigger_indicators: vec!["RSI".to_owned(), " rsi ".to_owned()],
            trade_id: "trade-1".to_owned(),
            open_time: "2026-01-01T00:00:00Z".to_owned(),
            qty,
            margin_usdt: margin,
            notional: margin * 10.0,
            ..Default::default()
        }
    }

    fn record(symbol: &str, side_key: &str, interval: &str) -> PortfolioPositionRecord {
        PortfolioPositionRecord {
            symbol: symbol.to_owned(),
            side_key: side_key.to_owned(),
            interval: interval.to_owned(),
            quantity: Some(0.5),
            mark_price: Some(20_000.0),
            size_usdt: Some(10_000.0),
            margin_usdt: Some(500.0),
            pnl_value: Some(42.0),
            roi_percent: Some(8.4),
            leverage: Some(20),
            liquidation_price: Some(15_000.0),
            status: "Active".to_owned(),
            stop_loss_enabled: true,
            open_time: "2026-01-01T00:00:00Z".to_owned(),
            close_time: "-".to_owned(),
            allocations: Vec::new(),
        }
    }

    #[test]
    fn position_snapshot_matches_python_service_shape_defaults() {
        let snapshot = build_position_snapshot(&PortfolioPositionRecord {
            symbol: "btcusdt".to_owned(),
            side_key: "l".to_owned(),
            status: String::new(),
            ..Default::default()
        });
        assert_eq!(snapshot.symbol, "BTCUSDT");
        assert_eq!(snapshot.side_key, "L");
        assert_eq!(snapshot.side_label, "Long");
        assert_eq!(snapshot.interval, "-");
        assert_eq!(snapshot.status, "Active");
        assert_eq!(snapshot.open_time, "-");
        assert_eq!(snapshot.close_time, "-");
    }

    #[test]
    fn portfolio_snapshot_sorts_positions_and_computes_totals() {
        let mut eth = record("ETHUSDT", "S", "5m");
        eth.margin_usdt = None;
        eth.pnl_value = Some(-10.0);
        eth.allocations = vec![
            PortfolioAllocation {
                margin_usdt: 100.0,
                ..Default::default()
            },
            PortfolioAllocation {
                margin_usdt: 75.0,
                ..Default::default()
            },
        ];
        let btc = record("BTCUSDT", "L", "1m");
        let mut closed = record("SOLUSDT", "L", "15m");
        closed.status = "Closed".to_owned();
        closed.pnl_value = Some(5.5);
        closed.margin_usdt = Some(50.0);

        let snapshot = build_portfolio_snapshot(
            "FUTURES",
            &[eth, btc],
            &[closed],
            Some(1_000.0),
            Some(800.0),
            "service",
            "2026-01-01T00:00:01Z",
        );

        assert_eq!(snapshot.open_position_count, 2);
        assert_eq!(snapshot.closed_position_count, 1);
        assert_eq!(snapshot.positions[0].symbol, "BTCUSDT");
        assert_eq!(snapshot.positions[1].symbol, "ETHUSDT");
        assert_eq!(snapshot.active_pnl, Some(32.0));
        assert_eq!(snapshot.active_margin, Some(675.0));
        assert_eq!(snapshot.closed_pnl, Some(5.5));
        assert_eq!(snapshot.closed_margin, Some(50.0));
        assert_eq!(snapshot.total_balance, Some(1_000.0));
        assert_eq!(snapshot.available_balance, Some(800.0));
    }

    #[test]
    fn allocation_collection_dedupes_and_merges_like_python_history_helpers() {
        let first = allocation("ledger-1", "1m", 0.1, 10.0);
        let mut duplicate = allocation("ledger-1", "1m", 0.2, 20.0);
        duplicate.notional = 300.0;
        let mut other = allocation("ledger-2", "5m", 0.3, 30.0);
        other.trade_id = "trade-2".to_owned();

        let collected = collect_allocations(&[other.clone(), first, duplicate]);
        assert_eq!(collected.len(), 2);
        assert_eq!(collected[0].ledger_id, "ledger-1");
        assert_eq!(collected[0].trigger_indicators, vec!["rsi".to_owned()]);
        assert_eq!(collected[0].qty, 0.2);
        assert_eq!(collected[0].margin_usdt, 20.0);
        assert_eq!(collected[0].notional, 300.0);
        assert_eq!(collected[1].ledger_id, "ledger-2");
    }

    #[test]
    fn closed_allocation_update_distributes_reported_values_by_quantity_share() {
        let base = PortfolioPositionRecord {
            quantity: Some(3.0),
            margin_usdt: Some(300.0),
            size_usdt: Some(3_000.0),
            pnl_value: Some(90.0),
            ..Default::default()
        };
        let entries = vec![
            PortfolioAllocation {
                qty: 1.0,
                ..Default::default()
            },
            PortfolioAllocation {
                qty: 2.0,
                ..Default::default()
            },
        ];
        let updated = update_closed_allocations(
            &base,
            &entries,
            &ClosedAllocationUpdate {
                close_status: "Closed".to_owned(),
                close_time: "2026-01-02T00:00:00Z".to_owned(),
                qty_reported: Some(6.0),
                margin_reported: Some(600.0),
                pnl_reported: Some(120.0),
                close_price_reported: Some(110.0),
                entry_price_reported: Some(100.0),
                leverage_reported: Some(10),
            },
        );
        assert_eq!(updated[0].status, "Closed");
        assert_eq!(updated[0].close_time, "2026-01-02T00:00:00Z");
        assert_eq!(updated[0].qty, 2.0);
        assert_eq!(updated[0].margin_usdt, 200.0);
        assert_eq!(updated[0].pnl_value, Some(40.0));
        assert_eq!(updated[1].qty, 4.0);
        assert_eq!(updated[1].margin_usdt, 400.0);
        assert_eq!(updated[1].pnl_value, Some(80.0));
        assert_eq!(updated[1].close_price, Some(110.0));
        assert_eq!(updated[1].entry_price, Some(100.0));
        assert_eq!(updated[1].leverage, Some(10));
    }

    #[test]
    fn allocation_persistence_payload_serializes_active_records_only() {
        let mut allocations = BTreeMap::new();
        allocations.insert(
            ("BTCUSDT".to_owned(), "L".to_owned()),
            vec![allocation("ledger-1", "1m", 0.1, 10.0)],
        );

        let mut open_records = BTreeMap::new();
        open_records.insert(
            ("BTCUSDT".to_owned(), "L".to_owned()),
            record("BTCUSDT", "L", "1m"),
        );
        open_records.insert(
            ("ETHUSDT".to_owned(), "S".to_owned()),
            PortfolioPositionRecord {
                status: "Closed".to_owned(),
                ..record("ETHUSDT", "S", "5m")
            },
        );

        let payload = build_allocation_persistence_payload(
            "live",
            1_770_000_000.0,
            &allocations,
            &open_records,
        );
        assert_eq!(payload.version, 1);
        assert_eq!(payload.mode, "live");
        assert_eq!(payload.entry_allocations.len(), 1);
        assert!(payload.entry_allocations.contains_key("BTCUSDT:L"));
        assert_eq!(payload.open_position_records.len(), 1);
        assert!(payload.open_position_records.contains_key("BTCUSDT:L"));
        assert_eq!(
            deserialize_allocation_key("BTCUSDT:L"),
            ("BTCUSDT".to_owned(), "L".to_owned())
        );
    }

    #[test]
    fn reduction_splits_allocation_and_updates_open_record() {
        let mut first = allocation("ledger-1", "1m", 0.10, 100.0);
        first.trade_id = "trade-1".to_owned();
        first.notional = 1_000.0;
        let mut second = allocation("ledger-2", "5m", 0.20, 200.0);
        second.trade_id = "trade-2".to_owned();
        second.notional = 2_000.0;

        let mut state = PortfolioReconciliationState::default();
        state.entry_allocations.insert(
            ("BTCUSDT".to_owned(), "L".to_owned()),
            vec![first.clone(), second.clone()],
        );
        state.open_position_records.insert(
            ("BTCUSDT".to_owned(), "L".to_owned()),
            PortfolioPositionRecord {
                quantity: Some(0.30),
                allocations: vec![first, second],
                ..record("BTCUSDT", "L", "1m")
            },
        );

        let mut target_identity = BTreeMap::new();
        target_identity.insert("trade_id".to_owned(), "trade-1".to_owned());
        let result = reduce_position_allocation_state(
            &mut state,
            "btcusdt",
            "l",
            Some("15m"),
            Some(0.05),
            Some(&target_identity),
        );

        assert!(result.changed);
        assert_eq!(result.closed_allocations.len(), 1);
        assert_eq!(result.closed_allocations[0].status, "Closed");
        assert!((result.closed_allocations[0].qty - 0.05).abs() < POSITION_QTY_TOL);
        assert!((result.closed_allocations[0].margin_usdt - 50.0).abs() < POSITION_QTY_TOL);
        assert!((result.closed_allocations[0].notional - 500.0).abs() < POSITION_QTY_TOL);
        assert_eq!(result.survivor_allocations.len(), 2);
        assert!((result.survivor_allocations[0].qty - 0.05).abs() < POSITION_QTY_TOL);
        assert!((result.survivor_allocations[0].margin_usdt - 50.0).abs() < POSITION_QTY_TOL);
        let survivors = state
            .entry_allocations
            .get(&("BTCUSDT".to_owned(), "L".to_owned()))
            .expect("surviving allocation bucket should remain");
        assert_eq!(survivors.len(), 2);
        let open_record = state
            .open_position_records
            .get(&("BTCUSDT".to_owned(), "L".to_owned()))
            .expect("open record should remain after partial reduction");
        assert_eq!(open_record.allocations.len(), 2);
    }

    #[test]
    fn close_all_reconciliation_moves_open_records_to_closed_history() {
        let mut btc_allocation = allocation("ledger-1", "1m", 0.10, 100.0);
        btc_allocation.trigger_indicators = vec!["RSI".to_owned(), " rsi ".to_owned()];
        let eth_allocation = allocation("ledger-2", "5m", 0.20, 200.0);
        let mut state = PortfolioReconciliationState::default();
        state
            .entry_allocations
            .insert(("BTCUSDT".to_owned(), "L".to_owned()), vec![btc_allocation]);
        state
            .entry_allocations
            .insert(("ETHUSDT".to_owned(), "S".to_owned()), vec![eth_allocation]);
        state.open_position_records.insert(
            ("BTCUSDT".to_owned(), "L".to_owned()),
            record("BTCUSDT", "L", "1m"),
        );
        state.open_position_records.insert(
            ("ETHUSDT".to_owned(), "S".to_owned()),
            record("ETHUSDT", "S", "5m"),
        );

        let summary = apply_close_all_to_position_state(
            &mut state,
            &[CloseAllPositionResult {
                symbol: "btcusdt".to_owned(),
                ok: true,
                skipped: false,
            }],
            "2026-06-18T12:15:00Z",
            10,
        );

        assert_eq!(summary.closed_count, 1);
        assert_eq!(summary.remaining_open_count, 1);
        assert_eq!(summary.closed_symbols, vec!["BTCUSDT".to_owned()]);
        assert!(
            !state
                .open_position_records
                .contains_key(&("BTCUSDT".to_owned(), "L".to_owned()))
        );
        assert!(
            state
                .open_position_records
                .contains_key(&("ETHUSDT".to_owned(), "S".to_owned()))
        );
        assert!(
            !state
                .entry_allocations
                .contains_key(&("BTCUSDT".to_owned(), "L".to_owned()))
        );
        assert!(
            state
                .pending_close_times
                .contains_key(&("BTCUSDT".to_owned(), "L".to_owned()))
        );
        assert_eq!(state.closed_position_records.len(), 1);
        assert_eq!(state.closed_position_records[0].status, "Closed");
        assert_eq!(
            state.closed_position_records[0].close_time,
            "2026-06-18T12:15:00Z"
        );
        assert_eq!(
            state.closed_position_records[0].allocations[0].trigger_indicators,
            vec!["rsi".to_owned()]
        );
    }
}
