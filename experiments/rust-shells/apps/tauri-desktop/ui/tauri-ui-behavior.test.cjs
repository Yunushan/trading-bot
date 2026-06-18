const assert = require("node:assert/strict");
const behavior = require("./tauri-ui-behavior.js");

const {
  backtestRunsFromPayload,
  cleanBacktestResultMetadata,
  describeCircuitIncidentCount,
  describeConfigPersistence,
  describeLastCircuitIncident,
  describeLocalModelStatus,
  describeOperationalPreflight,
  describeOrderCircuit,
  formatLlmPromptResult,
  formatServiceLogLine,
  formatServiceLogs,
  formatPreflightLabel,
  importBacktestRowsToDashboard,
  mergeUniqueLines,
  normalizeOverrideRow,
  overrideImportKey,
  preflightFreshnessAges,
  serviceLogItemsFromPayload,
  preflightStartBlocked,
  preflightStartDetail,
  selectBacktestScanBest
} = behavior;

assert.deepEqual(backtestRunsFromPayload({ top_runs: [{ symbol: "BTCUSDT" }] }), [{ symbol: "BTCUSDT" }]);
assert.deepEqual(backtestRunsFromPayload({ results: [{ symbol: "ETHUSDT" }] }), [{ symbol: "ETHUSDT" }]);
assert.deepEqual(backtestRunsFromPayload({ runs: [{ symbol: "SOLUSDT" }] }), [{ symbol: "SOLUSDT" }]);
assert.deepEqual(backtestRunsFromPayload([{ symbol: "BNBUSDT" }]), [{ symbol: "BNBUSDT" }]);
assert.deepEqual(backtestRunsFromPayload({ state: "idle" }), []);

const best = selectBacktestScanBest(
  [
    { symbol: "BTCUSDT", interval: "1m", trades: 0, roi_percent: 100, roi_value: 100, max_drawdown_percent: 1 },
    { symbol: "ETHUSDT", interval: "5m", trades: 9, roi_percent: 8, roi_value: 12, max_drawdown_percent: 15 },
    { symbol: "XRPUSDT", interval: "15m", trades: 4, roi_percent: 9, roi_value: 3, max_drawdown_percent: 7, indicators: ["RSI"] },
    { symbol: "SOLUSDT", interval: "1h", trades: 6, roi_percent: 9, roi_value: 7, max_drawdown_percent: 9, indicator_keys: ["macd"] },
    { symbol: "adausdt", interval: "4h", trades: 7, roi_percent: 9, roi_value: 7, max_drawdown_percent: 5, indicator: "volume" }
  ],
  10,
  (value) => behavior.normalizeIndicatorList(value).map((item) => item.toLowerCase())
);

assert.deepEqual(best, {
  symbol: "ADAUSDT",
  interval: "4h",
  indicator_keys: ["volume"],
  roi_percent: 9,
  roi_value: 7,
  max_drawdown_percent: 5,
  trades: 7
});

const runtimeRows = [
  normalizeOverrideRow({
    symbol: "BTCUSDT",
    interval: "1m",
    indicators: ["rsi"],
    strategy_controls: { leverage: 1 }
  })
];
const resultRows = [
  { symbol: "BTCUSDT", interval: "1m", indicator_keys: ["rsi"], strategy_controls: { leverage: 1 } },
  {
    symbol: "ETHUSDT",
    interval: "5m",
    indicator_keys: ["macd"],
    strategy_controls: { leverage: 2 },
    roi_percent: 12.5,
    optimizer_rank: 1,
    optimizer_metric: "roi_percent",
    optimizer_eligible: true
  },
  { symbol: "", interval: "15m", indicator_keys: ["volume"], strategy_controls: { leverage: 3 } }
];

const imported = importBacktestRowsToDashboard({
  runtimeRows,
  resultRows,
  indexes: [0, 1, 2],
  rowToOverride: normalizeOverrideRow,
  overrideKey: overrideImportKey
});

assert.equal(imported.added, 1);
assert.equal(imported.skipped, 2);
assert.equal(imported.rows.length, 2);
assert.deepEqual(imported.importedSymbols, ["ETHUSDT"]);
assert.deepEqual(imported.importedIntervals, ["5m"]);
assert.equal(overrideImportKey(imported.rows[1]), "ETHUSDT|5m|macd|2");
assert.deepEqual(imported.rows[1].backtest_result, {
  source: "python-backtest",
  symbol: "ETHUSDT",
  interval: "5m",
  indicator_keys: ["macd"],
  roi_percent: 12.5,
  strategy_controls: { leverage: 2 },
  optimizer_rank: 1,
  optimizer_metric: "roi_percent",
  optimizer_eligible: true
});
assert.deepEqual(cleanBacktestResultMetadata({ symbol: "BTCUSDT", interval: "1m" }), null);

assert.deepEqual(mergeUniqueLines("BTCUSDT\nETHUSDT", ["ETHUSDT", "SOLUSDT"]), [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT"
]);

const statusText = describeLocalModelStatus(
  {
    model: "qwen3:8b",
    installed: false,
    server_kind: "ollama",
    estimated_size_label: "5.2 GB",
    storage_paths: ["C:\\Users\\demo\\.ollama\\models"],
    disk_space_warning: "Low disk space.",
    error: "connection refused"
  },
  "fallback"
);

assert.match(statusText, /qwen3:8b/);
assert.match(statusText, /not installed on ollama/);
assert.match(statusText, /5\.2 GB/);
assert.match(statusText, /Low disk space/);
assert.match(statusText, /connection refused/);

assert.deepEqual(describeConfigPersistence(null), {
  stateText: "Runtime only",
  pathText: "-",
  tone: "neutral"
});
assert.deepEqual(describeConfigPersistence({
  exists: true,
  dirty: false,
  path: "C:\\Users\\demo\\config.json",
  last_saved_at: "2026-05-14T10:00:00+00:00"
}), {
  stateText: "Config file in sync - saved 2026-05-14T10:00:00+00:00",
  pathText: "C:\\Users\\demo\\config.json",
  tone: "good"
});
assert.deepEqual(describeConfigPersistence({
  exists: true,
  dirty: true,
  path: "C:\\Users\\demo\\config.json",
  last_loaded_at: "2026-05-14T09:55:00+00:00"
}), {
  stateText: "Unsaved runtime changes - loaded 2026-05-14T09:55:00+00:00",
  pathText: "C:\\Users\\demo\\config.json",
  tone: "warn"
});

const blockedPreflight = {
  state: "blocked",
  mode: "Live",
  live_mode: true,
  message: "Live preflight blocked.",
  start: { allowed: false, state: "blocked", reasons: ["account snapshot stale", "portfolio snapshot stale"] },
  orders: { allowed: true, state: "ok", reasons: [] },
  critical_stale: { start: ["account snapshot"], orders: [] },
  freshness: {
    account: { age_seconds: 900, max_age_seconds: 300, stale: true },
    portfolio: { age_seconds: 30, max_age_seconds: 300, stale: false }
  }
};
assert.equal(preflightStartBlocked(blockedPreflight), true);
assert.equal(preflightStartDetail(blockedPreflight), "account snapshot stale; portfolio snapshot stale");
assert.deepEqual(formatPreflightLabel(blockedPreflight), {
  text: "Preflight: start blocked (account snapshot stale; portfolio snapshot stale)",
  tone: "bad"
});
assert.match(preflightFreshnessAges(blockedPreflight), /Account 900s\/300s stale/);
assert.deepEqual(describeOperationalPreflight(blockedPreflight), {
  stateText: "Blocked",
  startText: "Blocked (Gate enabled, blocked) - account snapshot stale",
  ordersText: "Ok (Gate enabled, allowed)",
  modeText: "Live / Live",
  criticalText: "account snapshot",
  agesText: "Account 900s/300s stale | Portfolio 30s/300s fresh",
  messageText: "Live preflight blocked.",
  tone: "bad"
});

const orderBlockedPreflight = {
  state: "blocked",
  start: { allowed: true, state: "ok", reasons: [] },
  orders: { allowed: false, state: "blocked", reasons: ["connector stale"] }
};
assert.equal(preflightStartBlocked(orderBlockedPreflight), false);
assert.deepEqual(formatPreflightLabel(orderBlockedPreflight), {
  text: "Preflight: orders blocked (connector stale)",
  tone: "warn"
});

assert.deepEqual(formatPreflightLabel({
  state: "warning",
  start: { allowed: true, state: "warning", reasons: ["demo mode"] },
  orders: { allowed: true, state: "ok", reasons: [] }
}), {
  text: "Preflight: warning, start allowed (demo mode)",
  tone: "warn"
});

assert.equal(describeOrderCircuit({ active: true, block_count: 2, block_threshold: 3 }), "Open (2/3 blocks)");
assert.equal(
  describeOrderCircuit({ active: true, reset_blocked_reason: "connector still error" }),
  "Open - reset blocked: connector still error"
);
assert.equal(describeOrderCircuit({ active: false, state: "closed" }), "Closed");
assert.equal(describeCircuitIncidentCount({ events: [{}, {}] }), "2");
assert.equal(
  describeLastCircuitIncident(
    { last_event: { action: "connector_order_circuit_trip", ts: "2026-05-14T11:00:00+00:00" } },
    null
  ),
  "Trip @ 2026-05-14T11:00:00+00:00"
);
assert.deepEqual(serviceLogItemsFromPayload({ logs: [{ message: "dashboard log" }] }), [{ message: "dashboard log" }]);
assert.deepEqual(serviceLogItemsFromPayload({ items: [{ message: "direct log" }] }), [{ message: "direct log" }]);
assert.equal(formatServiceLogLine({
  sequence_id: 7,
  level: "warning",
  source: "runtime",
  generated_at: "2026-05-14T11:30:00+00:00",
  message: "preflight blocked"
}), "[WARNING] #7 runtime 2026-05-14T11:30:00+00:00: preflight blocked");
assert.equal(
  formatServiceLogs(["raw line", { level: "info", source: "service", message: "ready" }]),
  "raw line\n[INFO] service: ready"
);
assert.equal(formatServiceLogs({ items: [] }), "No service logs returned.");
const llmDryRunResult = formatLlmPromptResult({
  ok: true,
  dry_run: true,
  request: {
    provider: "local",
    url: "http://127.0.0.1:11434/v1/chat/completions",
    headers: { Authorization: "********" }
  },
  output_policy: { advisory_only: true, violations: [], blocked: false },
  text: ""
});
assert.match(llmDryRunResult, /LLM advisory dry run ok/);
assert.match(llmDryRunResult, /Prepared request/);
assert.match(llmDryRunResult, /advisory only/);
const llmBlockedResult = formatLlmPromptResult({
  ok: false,
  dry_run: false,
  provider: "openai",
  output_policy: { advisory_only: true, violations: ["order_execution_claim"], blocked: true },
  text: "order was executed"
});
assert.match(llmBlockedResult, /LLM advisory request failed/);
assert.match(llmBlockedResult, /Output policy: blocked/);
assert.match(llmBlockedResult, /order_execution_claim/);

console.log("tauri-ui-behavior tests passed");
