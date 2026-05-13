(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.TauriUiBehavior = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  "use strict";

  const linesFromText = (value) => String(value || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);

  const uniqueValues = (...groups) => {
    const seen = new Set();
    const result = [];
    for (const group of groups) {
      for (const item of Array.isArray(group) ? group : linesFromText(group)) {
        const text = String(item || "").trim();
        if (!text || seen.has(text)) continue;
        seen.add(text);
        result.push(text);
      }
    }
    return result;
  };

  const mergeUniqueLines = (currentText, additions) => uniqueValues(linesFromText(currentText), additions);

  const normalizeIndicatorList = (value) => {
    if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
    return linesFromText(value);
  };

  const normalizeOverrideRow = (row) => {
    const controls = row?.strategy_controls && typeof row.strategy_controls === "object"
      ? { ...row.strategy_controls }
      : {};
    if (row?.leverage !== undefined && controls.leverage === undefined) controls.leverage = row.leverage;
    if (row?.loop_interval_override !== undefined && controls.loop_interval_override === undefined) {
      controls.loop_interval_override = row.loop_interval_override;
    }
    if (row?.stop_loss && typeof row.stop_loss === "object" && controls.stop_loss === undefined) {
      controls.stop_loss = row.stop_loss;
    }
    return {
      symbol: String(row?.symbol || "").trim().toUpperCase(),
      interval: String(row?.interval || "").trim(),
      indicators: normalizeIndicatorList(row?.indicators ?? row?.indicator_keys ?? row?.indicator),
      strategy_controls: controls
    };
  };

  const overrideImportKey = (row, normalize = normalizeOverrideRow) => {
    const normalized = normalize(row);
    const controls = normalized.strategy_controls || {};
    return [
      normalized.symbol,
      normalized.interval,
      normalizeIndicatorList(normalized.indicators).join(","),
      controls.leverage ?? ""
    ].join("|");
  };

  const backtestRunsFromPayload = (payload) => {
    if (Array.isArray(payload?.top_runs)) return payload.top_runs;
    if (Array.isArray(payload?.results)) return payload.results;
    if (Array.isArray(payload?.runs)) return payload.runs;
    if (Array.isArray(payload)) return payload;
    return [];
  };

  const numericRunValue = (row, key, fallback = 0) => {
    const value = Number(row?.[key] ?? row?.data?.[key]);
    return Number.isFinite(value) ? value : fallback;
  };

  const defaultIndicatorKeysForRequest = (value) => normalizeIndicatorList(value);

  const selectBacktestScanBest = (runs, mddLimit, indicatorKeysForRequest = defaultIndicatorKeysForRequest) => {
    let best = null;
    let bestScore = null;
    const limit = Number.isFinite(Number(mddLimit)) ? Number(mddLimit) : 0;
    for (const row of runs || []) {
      const trades = Math.trunc(numericRunValue(row, "trades", 0));
      if (trades <= 0) continue;
      const mdd = numericRunValue(row, "max_drawdown_percent", 0);
      if (mdd > limit) continue;
      const symbol = String(row?.symbol || "").trim().toUpperCase();
      const interval = String(row?.interval || "").trim();
      if (!symbol || !interval) continue;
      const roiPercent = numericRunValue(row, "roi_percent", 0);
      const roiValue = numericRunValue(row, "roi_value", 0);
      const score = [roiPercent, roiValue, -mdd];
      if (
        !bestScore
        || score[0] > bestScore[0]
        || (score[0] === bestScore[0] && score[1] > bestScore[1])
        || (score[0] === bestScore[0] && score[1] === bestScore[1] && score[2] > bestScore[2])
      ) {
        bestScore = score;
        best = {
          symbol,
          interval,
          indicator_keys: indicatorKeysForRequest(row?.indicator_keys ?? row?.indicators ?? row?.indicator),
          roi_percent: roiPercent,
          roi_value: roiValue,
          max_drawdown_percent: mdd,
          trades
        };
      }
    }
    return best;
  };

  const importBacktestRowsToDashboard = ({
    runtimeRows = [],
    resultRows = [],
    indexes = [],
    rowToOverride = normalizeOverrideRow,
    overrideKey = overrideImportKey
  }) => {
    const rows = [...runtimeRows];
    const existing = new Set(rows.map((row) => overrideKey(row)));
    const importedSymbols = [];
    const importedIntervals = [];
    let added = 0;
    let skipped = 0;

    for (const index of indexes) {
      const source = resultRows[index];
      const next = rowToOverride(source);
      if (!next.symbol || !next.interval) {
        skipped += 1;
        continue;
      }
      const key = overrideKey(next);
      if (existing.has(key)) {
        skipped += 1;
        continue;
      }
      rows.push(next);
      existing.add(key);
      importedSymbols.push(next.symbol);
      importedIntervals.push(next.interval);
      added += 1;
    }

    return { rows, importedSymbols, importedIntervals, added, skipped };
  };

  const localModelStorageText = (status) => Array.isArray(status?.storage_paths) && status.storage_paths.length
    ? status.storage_paths.join("; ")
    : (status?.storage_hint || "Ollama model cache outside this project.");

  const describeLocalModelStatus = (status, fallbackModel = "") => {
    if (!status || typeof status !== "object") return "Local model status: unavailable.";
    const installed = status.installed ? "installed" : "not installed";
    const size = status.estimated_size_label ? `, estimated ${status.estimated_size_label}` : "";
    const warning = status.disk_space_warning ? ` ${status.disk_space_warning}` : "";
    const error = status.error ? ` Server check: ${status.error}` : "";
    return `Local model '${status.model || fallbackModel}' is ${installed} on ${status.server_kind || "local server"}${size}. Storage: ${localModelStorageText(status)}.${warning}${error}`;
  };

  return {
    backtestRunsFromPayload,
    describeLocalModelStatus,
    importBacktestRowsToDashboard,
    linesFromText,
    localModelStorageText,
    mergeUniqueLines,
    normalizeIndicatorList,
    normalizeOverrideRow,
    numericRunValue,
    overrideImportKey,
    selectBacktestScanBest,
    uniqueValues
  };
});
