const assert = require("node:assert/strict");
const behavior = require("./tauri-ui-behavior.js");

const {
  backtestRunsFromPayload,
  describeLocalModelStatus,
  importBacktestRowsToDashboard,
  mergeUniqueLines,
  normalizeOverrideRow,
  overrideImportKey,
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
  { symbol: "ETHUSDT", interval: "5m", indicator_keys: ["macd"], strategy_controls: { leverage: 2 } },
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

console.log("tauri-ui-behavior tests passed");
