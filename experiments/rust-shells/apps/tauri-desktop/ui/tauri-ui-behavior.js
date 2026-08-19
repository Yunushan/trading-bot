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

  const titleizeLabel = (value) => {
    const text = String(value || "").trim().replace(/[_-]+/g, " ");
    if (!text) return "-";
    return text.replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const compactNumber = (value) => {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 1 }) : "-";
  };

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

  const normalizeDesign = (value) => {
    const normalized = String(value || "").trim().toLowerCase();
    return normalized === "workstation" ? "Workstation" : "Classic";
  };

  const designModeClass = (value) => normalizeDesign(value) === "Workstation"
    ? "workstation-design"
    : "classic-design";

  const normalizeTheme = (value) => {
    const normalized = String(value || "").trim().toLowerCase();
    const canonical = normalized === "gren" ? "green" : normalized;
    const themes = new Map([
      ["light", "Light"],
      ["dark", "Dark"],
      ["blue", "Blue"],
      ["yellow", "Yellow"],
      ["green", "Green"],
      ["red", "Red"]
    ]);
    return themes.get(canonical) || "Dark";
  };

  const themeModeClass = (value) => `theme-${normalizeTheme(value).toLowerCase()}`;

  const optionsMatchingKeys = (options, keys) => {
    const optionsByKey = new Map(
      (Array.isArray(options) ? options : [])
        .map((option) => [String(option?.key ?? option?.value ?? "").trim(), option])
        .filter(([key]) => key)
    );
    return uniqueValues(Array.isArray(keys) ? keys : [])
      .map((key) => optionsByKey.get(key))
      .filter(Boolean);
  };

  const mergeUniqueLines = (currentText, additions) => uniqueValues(linesFromText(currentText), additions);

  const normalizeIndicatorList = (value) => {
    if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
    return linesFromText(value);
  };

  const normalizePositionCloseSide = (value) => {
    const side = String(value || "").trim().toUpperCase();
    if (["B", "BUY", "L", "LONG"].includes(side)) return "L";
    if (["S", "SELL", "SHORT"].includes(side)) return "S";
    return "";
  };

  const backtestMetadataKeys = [
    "symbol",
    "interval",
    "indicator_keys",
    "logic",
    "trades",
    "roi_value",
    "roi_percent",
    "max_drawdown_percent",
    "max_drawdown_value",
    "max_drawdown_during_percent",
    "max_drawdown_during_value",
    "max_drawdown_result_percent",
    "max_drawdown_result_value",
    "mdd_logic",
    "mdd_logic_display",
    "start",
    "start_display",
    "end",
    "end_display",
    "side",
    "capital",
    "position_pct",
    "position_pct_display",
    "position_pct_units",
    "leverage",
    "leverage_display",
    "margin_mode",
    "position_mode",
    "assets_mode",
    "account_mode",
    "stop_loss_enabled",
    "stop_loss_mode",
    "stop_loss_scope",
    "stop_loss_usdt",
    "stop_loss_percent",
    "stop_loss_display",
    "loop_interval_override",
    "connector_backend",
    "strategy_controls",
    "optimizer_rank",
    "optimizer_metric",
    "optimizer_primary_score",
    "optimizer_eligible",
    "optimizer_mode",
    "optimizer_scope",
    "optimizer_mdd_limit",
    "optimizer_min_trades",
    "optimizer_candidate_count",
    "optimizer_eligible_count",
    "optimizer_filtered_count",
    "optimizer_run_count"
  ];

  const cleanBacktestResultMetadata = (row) => {
    if (!row || typeof row !== "object") return null;
    if (row.backtest_result && typeof row.backtest_result === "object") return { ...row.backtest_result };
    const metadata = {};
    let hasResultPayload = false;
    for (const key of backtestMetadataKeys) {
      if (row[key] === undefined || row[key] === null) continue;
      metadata[key] = row[key];
      if (!["symbol", "interval"].includes(key)) hasResultPayload = true;
    }
    if (!hasResultPayload) return null;
    metadata.source = metadata.source || "python-backtest";
    return metadata;
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
    const normalized = {
      symbol: String(row?.symbol || "").trim().toUpperCase(),
      interval: String(row?.interval || "").trim(),
      indicators: normalizeIndicatorList(row?.indicators ?? row?.indicator_keys ?? row?.indicator),
      strategy_controls: controls
    };
    const backtestResult = cleanBacktestResultMetadata(row);
    if (backtestResult) normalized.backtest_result = backtestResult;
    return normalized;
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

  const compactTimestamp = (value) => String(value || "").trim();

  const describeConfigPersistence = (persistence) => {
    const payload = persistence && typeof persistence === "object" ? persistence : {};
    const dirty = Boolean(payload.dirty);
    const exists = Boolean(payload.exists);
    const savedAt = compactTimestamp(payload.last_saved_at || payload.saved_at);
    const loadedAt = compactTimestamp(payload.last_loaded_at || payload.loaded_at);
    let stateText = "Runtime only";
    let tone = "neutral";
    if (dirty) {
      stateText = "Unsaved runtime changes";
      tone = "warn";
    } else if (exists) {
      stateText = "Config file in sync";
      tone = "good";
    }
    const detail = [];
    if (savedAt) detail.push(`saved ${savedAt}`);
    if (loadedAt) detail.push(`loaded ${loadedAt}`);
    return {
      stateText: detail.length ? `${stateText} - ${detail.join(" - ")}` : stateText,
      pathText: String(payload.path || "-"),
      tone
    };
  };

  const preflightDetail = (value) => {
    if (Array.isArray(value)) {
      return value.map((item) => String(item || "").trim()).filter(Boolean).join("; ");
    }
    return String(value || "").trim();
  };

  const preflightStartBlocked = (preflight) => {
    if (!preflight || typeof preflight !== "object") return false;
    const start = preflight.start && typeof preflight.start === "object" ? preflight.start : null;
    if (start?.allowed === false || start?.state === "blocked") return true;
    return Boolean((!start && preflight.blocked === true) || preflight.start_blocked === true);
  };

  const preflightStartDetail = (preflight) => {
    if (!preflight || typeof preflight !== "object") return "";
    const start = preflight.start && typeof preflight.start === "object" ? preflight.start : {};
    return preflightDetail(start.reasons)
      || preflightDetail(preflight.reasons)
      || preflightDetail(preflight.message)
      || "operational preflight is blocked";
  };

  const preflightGateText = (gate) => {
    const payload = gate && typeof gate === "object" ? gate : {};
    const stateLabel = titleizeLabel(payload.state || (payload.allowed === false ? "blocked" : "unknown"));
    const enabledLabel = payload.gate_enabled === false ? "Gate disabled" : "Gate enabled";
    const allowedLabel = payload.allowed === false ? "blocked" : payload.allowed === true ? "allowed" : "unknown";
    const reasons = Array.isArray(payload.reasons) ? payload.reasons.filter(Boolean) : [];
    const reason = reasons.length ? ` - ${reasons[0]}` : "";
    return `${stateLabel} (${enabledLabel}, ${allowedLabel})${reason}`;
  };

  const preflightCriticalLabels = (preflight) => {
    const payload = preflight && typeof preflight === "object" ? preflight : {};
    const critical = payload.critical_stale;
    const labels = [];
    const addLabel = (label) => {
      const text = String(label || "").trim();
      if (text && !labels.includes(text)) labels.push(text);
    };
    if (Array.isArray(critical)) {
      critical.forEach(addLabel);
    } else if (critical && typeof critical === "object") {
      Object.values(critical).forEach((items) => {
        if (Array.isArray(items)) items.forEach(addLabel);
      });
    }
    return labels;
  };

  const preflightFreshnessAges = (preflight) => {
    const payload = preflight && typeof preflight === "object" ? preflight : {};
    const freshness = payload.freshness && typeof payload.freshness === "object" ? payload.freshness : {};
    const inputs = [
      ["exchange_connector", "Exchange"],
      ["execution", "Execution"],
      ["account", "Account"],
      ["portfolio", "Portfolio"]
    ];
    const items = inputs.map(([key, label]) => {
      const item = freshness[key] && typeof freshness[key] === "object" ? freshness[key] : null;
      if (!item) return "";
      const age = Number(item.age_seconds);
      const maxAge = Number(item.max_age_seconds);
      const ageText = Number.isFinite(age) ? compactNumber(age) : "-";
      const maxText = Number.isFinite(maxAge) ? compactNumber(maxAge) : "-";
      return `${label} ${ageText}s/${maxText}s ${item.stale ? "stale" : "fresh"}`;
    }).filter(Boolean);
    return items.length ? items.join(" | ") : "-";
  };

  const describeOperationalPreflight = (preflight) => {
    const payload = preflight && typeof preflight === "object" ? preflight : {};
    const state = String(payload.state || "unknown").toLowerCase();
    const critical = preflightCriticalLabels(payload);
    const reasons = Array.isArray(payload.reasons) ? payload.reasons.filter(Boolean) : [];
    const message = String(payload.message || "").trim();
    const reasonText = reasons.length ? ` Reasons: ${reasons.join(" ")}` : "";
    return {
      stateText: titleizeLabel(state),
      startText: preflightGateText(payload.start),
      ordersText: preflightGateText(payload.orders),
      modeText: `${payload.live_mode ? "Live" : "Demo/Test"} / ${payload.mode || "-"}`,
      criticalText: critical.length ? critical.join(", ") : "Fresh",
      agesText: preflightFreshnessAges(payload),
      messageText: `${message || "No preflight snapshot received yet."}${reasonText}`,
      tone: state === "ok" ? "good" : state === "warning" || state === "disabled" ? "warn" : state === "blocked" || state === "error" ? "bad" : "neutral"
    };
  };

  const formatPreflightLabel = (preflight) => {
    if (!preflight || typeof preflight !== "object") {
      return { text: "Preflight: unknown", tone: "neutral" };
    }
    const state = String(preflight.state || "unknown").trim().toLowerCase();
    const start = preflight.start && typeof preflight.start === "object" ? preflight.start : {};
    const orders = preflight.orders && typeof preflight.orders === "object" ? preflight.orders : {};
    const startDetail = preflightDetail(start.reasons) || preflightDetail(preflight.reasons);
    const orderDetail = preflightDetail(orders.reasons);

    if (preflightStartBlocked(preflight)) {
      const detail = preflightStartDetail(preflight);
      return { text: `Preflight: start blocked (${detail})`, tone: "bad" };
    }
    if (orders.allowed === false || orders.state === "blocked") {
      const detail = orderDetail || state;
      return { text: `Preflight: orders blocked (${detail})`, tone: "warn" };
    }
    if (state === "ok") return { text: "Preflight: ok, start allowed", tone: "good" };
    if (state === "warning") {
      const detail = startDetail || orderDetail;
      const suffix = detail ? ` (${detail})` : "";
      return { text: `Preflight: warning, start allowed${suffix}`, tone: "warn" };
    }
    if (state === "blocked") return { text: "Preflight: blocked", tone: "bad" };
    return { text: `Preflight: ${state || "unknown"}`, tone: "neutral" };
  };

  const describeOrderCircuit = (circuit) => {
    const payload = circuit && typeof circuit === "object" ? circuit : {};
    if (payload.active) {
      if (payload.reset_blocked_reason) return `Open - reset blocked: ${payload.reset_blocked_reason}`;
      const blockCount = compactNumber(payload.block_count || 0);
      const threshold = compactNumber(payload.block_threshold || 0);
      return `Open (${blockCount}/${threshold} blocks)`;
    }
    if (payload.cleared_at) return `Closed ${payload.cleared_at}`;
    return titleizeLabel(payload.state || "closed");
  };

  const lastIncidentFrom = (incidentLog, incidents) => {
    const log = incidentLog && typeof incidentLog === "object" ? incidentLog : {};
    const list = incidents && typeof incidents === "object" ? incidents : {};
    return (log.last_event && typeof log.last_event === "object" ? log.last_event : null)
      || (list.last_event && typeof list.last_event === "object" ? list.last_event : null)
      || (Array.isArray(list.events) && list.events.length ? list.events[list.events.length - 1] : null);
  };

  const describeLastCircuitIncident = (incidentLog, incidents) => {
    const event = lastIncidentFrom(incidentLog, incidents);
    if (!event) return "No persisted incident";
    const action = titleizeLabel(String(event.action || event.event || "incident").replace(/^connector_order_circuit_/, ""));
    const timestamp = String(event.ts || event.created_at || event.generated_at || "").trim();
    return timestamp ? `${action} @ ${timestamp}` : action;
  };

  const describeCircuitIncidentCount = (incidents) => {
    const payload = incidents && typeof incidents === "object" ? incidents : {};
    if (Number.isFinite(Number(payload.count))) return compactNumber(payload.count);
    if (Array.isArray(payload.events)) return compactNumber(payload.events.length);
    return "0";
  };

  const serviceLogItemsFromPayload = (payload) => {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    if (Array.isArray(payload.items)) return payload.items;
    if (Array.isArray(payload.logs)) return payload.logs;
    if (Array.isArray(payload.events)) return payload.events;
    return [];
  };

  const formatServiceLogLine = (item) => {
    if (typeof item === "string") return item;
    const payload = item && typeof item === "object" ? item : {};
    const level = String(payload.level || "info").trim().toUpperCase() || "INFO";
    const timestamp = String(payload.generated_at || payload.created_at || payload.ts || "").trim();
    const source = String(payload.source || "service").trim() || "service";
    const sequence = Number.isFinite(Number(payload.sequence_id)) ? `#${Number(payload.sequence_id)} ` : "";
    const message = String(payload.message || payload.detail || "").trim();
    const stamp = timestamp ? ` ${timestamp}` : "";
    const suffix = message ? `: ${message}` : "";
    return `[${level}] ${sequence}${source}${stamp}${suffix}`;
  };

  const formatServiceLogs = (payload, emptyText = "No service logs returned.") => {
    const items = serviceLogItemsFromPayload(payload);
    return items.length ? items.map(formatServiceLogLine).join("\n") : emptyText;
  };

  const normalizeEnvironmentVersionRows = (catalog, observedRows) => {
    const observedByKey = new Map(
      (Array.isArray(observedRows) ? observedRows : [])
        .map((row) => [String(row?.key || "").trim(), row])
        .filter(([key]) => key)
    );
    return (Array.isArray(catalog) ? catalog : []).map((target) => {
      const key = String(target?.key || "").trim();
      const observed = observedByKey.get(key) || {};
      return {
        key,
        label: String(observed.label || target?.label || key).trim(),
        kind: String(observed.kind || target?.kind || "").trim(),
        path: String(observed.path || target?.path || "").trim(),
        installed: String(observed.installed || "Not installed").trim(),
        latest: String(observed.latest || target?.latest || "Unknown").trim(),
        usage: String(observed.usage || target?.usage || "Passive").trim(),
        usageChangeCounter: Number.isFinite(Number(observed.usage_change_counter ?? observed.usageChangeCounter))
          ? Number(observed.usage_change_counter ?? observed.usageChangeCounter)
          : 0,
        selectable: observed.selectable !== false
      };
    }).filter((row) => row.key && row.label);
  };

  const environmentUpdateScope = (rows, selectedKeys) => {
    const selected = new Set((Array.isArray(selectedKeys) ? selectedKeys : []).map(String));
    let updateToolchain = false;
    let updateWorkspace = false;
    let selectedCount = 0;
    for (const row of Array.isArray(rows) ? rows : []) {
      if (!selected.has(String(row?.key || ""))) continue;
      selectedCount += 1;
      const kind = String(row?.kind || "").trim().toLowerCase();
      if (kind === "rust_rustc" || kind === "rust_cargo") updateToolchain = true;
      if (kind === "rust_file_version") updateWorkspace = true;
    }
    return { updateToolchain, updateWorkspace, selectedCount };
  };

  const environmentSelectionCountText = (count, busy = false) => busy
    ? "Updating Rust dependencies..."
    : `${Math.max(0, Number.isFinite(Number(count)) ? Math.trunc(Number(count)) : 0)} selected`;

  const dashboardStreamReconnectDelay = (attempt, baseDelayMs = 1000, maxDelayMs = 30000) => {
    const normalizedAttempt = Math.max(0, Math.trunc(Number(attempt) || 0));
    const base = Math.max(250, Math.trunc(Number(baseDelayMs) || 1000));
    const maximum = Math.max(base, Math.trunc(Number(maxDelayMs) || 30000));
    return Math.min(maximum, base * (2 ** Math.min(normalizedAttempt, 16)));
  };

  const pythonLoopIntervalSeconds = (value, referenceCases = []) => {
    if (typeof value !== "string") return 60;
    const exactCase = (Array.isArray(referenceCases) ? referenceCases : [])
      .find((item) => String(item?.input ?? "") === value);
    const referencedSeconds = Number(exactCase?.loop_seconds);
    if (Number.isFinite(referencedSeconds)) return Math.max(1, Math.trunc(referencedSeconds));

    const suffixMultipliers = { s: 1, m: 60, h: 3_600, d: 86_400, w: 604_800 };
    for (const [suffix, multiplier] of Object.entries(suffixMultipliers)) {
      if (!value.endsWith(suffix)) continue;
      const amountText = value.slice(0, -suffix.length);
      if (!/^[+-]?\d+$/.test(amountText)) return 60;
      const seconds = Number(amountText) * multiplier;
      return Number.isFinite(seconds) ? Math.max(1, Math.trunc(seconds)) : 60;
    }
    if (/^[+-]?\d+$/.test(value.trim())) {
      const seconds = Number(value.trim());
      return Number.isFinite(seconds) ? Math.max(1, Math.trunc(seconds)) : 60;
    }
    return 60;
  };

  const dashboardPayloadFromStreamEvent = (event) => {
    const envelope = event && typeof event === "object" && event.payload && typeof event.payload === "object"
      ? event.payload
      : event;
    const payload = envelope && typeof envelope === "object" ? envelope.payload : null;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
    const generation = Number(envelope.generation);
    return {
      generation: Number.isFinite(generation) ? generation : 0,
      payload
    };
  };

  const formatTerminalResult = (result) => {
    const payload = result && typeof result === "object" ? result : {};
    const accepted = Boolean(payload.accepted);
    const exitCode = Number.isFinite(Number(payload.exit_code)) ? Number(payload.exit_code) : (accepted ? 0 : 1);
    const lines = [`Command ${accepted ? "accepted" : "rejected"} (exit ${exitCode}).`];
    const command = String(payload.command || "").trim();
    const source = String(payload.source || "").trim();
    const createdAt = String(payload.created_at || "").trim();
    if (command) lines.push(`Command: ${command}`);
    if (source) lines.push(`Source: ${source}`);
    if (createdAt) lines.push(`Created: ${createdAt}`);
    lines.push("", String(payload.output || payload.error || "No output returned."));
    return lines.join("\n");
  };

  const formatJsonBlock = (value) => {
    try {
      return JSON.stringify(value, null, 2);
    } catch (error) {
      return String(value || "");
    }
  };

  const formatLlmPromptResult = (result) => {
    const payload = result && typeof result === "object" ? result : {};
    const dryRun = Boolean(payload.dry_run);
    const state = payload.ok ? "ok" : "failed";
    const provider = String(payload.provider || payload.request?.provider || payload.request?.mode || "selected provider");
    const policy = payload.output_policy && typeof payload.output_policy === "object" ? payload.output_policy : {};
    const violations = Array.isArray(policy.violations) ? policy.violations.filter(Boolean) : [];
    const policyLine = policy.blocked
      ? `Output policy: blocked (${violations.join(", ") || "policy violation"})`
      : "Output policy: advisory only";
    const lines = [`LLM advisory ${dryRun ? "dry run" : "request"} ${state}.`, `Provider: ${provider}`, policyLine];
    if (payload.error) {
      lines.push("", "Error:", typeof payload.error === "string" ? payload.error : formatJsonBlock(payload.error));
    }
    if (payload.text) {
      lines.push("", "Advisory response:", String(payload.text));
    }
    if (dryRun && payload.request) {
      lines.push("", "Prepared request:", formatJsonBlock(payload.request));
    }
    if (!payload.error && !payload.text && !payload.request) {
      lines.push("", "No response body returned.");
    }
    return lines.join("\n");
  };

  return {
    backtestRunsFromPayload,
    cleanBacktestResultMetadata,
    describeCircuitIncidentCount,
    describeConfigPersistence,
    describeLastCircuitIncident,
    describeLocalModelStatus,
    describeOperationalPreflight,
    describeOrderCircuit,
    formatPreflightLabel,
    importBacktestRowsToDashboard,
    linesFromText,
    localModelStorageText,
    mergeUniqueLines,
    normalizeIndicatorList,
    normalizePositionCloseSide,
    normalizeOverrideRow,
    numericRunValue,
    optionsMatchingKeys,
    overrideImportKey,
    formatServiceLogLine,
    formatServiceLogs,
    formatTerminalResult,
    formatLlmPromptResult,
    dashboardPayloadFromStreamEvent,
    dashboardStreamReconnectDelay,
    pythonLoopIntervalSeconds,
    environmentSelectionCountText,
    environmentUpdateScope,
    normalizeEnvironmentVersionRows,
    preflightCriticalLabels,
    preflightDetail,
    preflightFreshnessAges,
    preflightGateText,
    serviceLogItemsFromPayload,
    preflightStartBlocked,
    preflightStartDetail,
    selectBacktestScanBest,
    designModeClass,
    normalizeDesign,
    normalizeTheme,
    themeModeClass,
    titleizeLabel,
    uniqueValues
  };
});
