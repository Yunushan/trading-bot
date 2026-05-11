import { fetchJson, sendJson } from "./modules/api.js";
import {
  renderConfig,
  renderConfigPersistence,
  renderDashboardSnapshot,
  renderPreflight,
  renderServiceApi,
} from "./modules/render.js";
import {
  authHeaders,
  closeDashboardStream,
  elements,
  initializeBacktestFormDefaults,
  normalizedBaseUrl,
  readStoredConfig,
  state,
  stopRefreshTimer,
  writeStoredConfig,
} from "./modules/state.js";
import {
  buildDashboardStreamUrl,
  createDashboardStream,
  supportsDashboardStream,
} from "./modules/stream.js";
import { serviceApiRoute } from "./modules/service-contract.js";
import { readInteger, readNumber, splitList } from "./modules/utils.js";

function setConnectionState(label, tone = "muted") {
  elements.connectionState.textContent = label;
  elements.connectionState.className = `pill ${tone}`;
}

function setConnectionMessage(message) {
  elements.connectionMessage.textContent = message;
}

function setControlMessage(message) {
  elements.controlMessage.textContent = message;
}

function setConnectorMessage(message) {
  elements.connectorMessage.textContent = message;
}

function setConfigMessage(message) {
  elements.configMessage.textContent = message;
}

function collectConfigPatch() {
  return {
    mode: elements.configMode.value,
    account_type: elements.configAccountType.value,
    margin_mode: elements.configMarginMode.value,
    position_mode: elements.configPositionMode.value,
    side: elements.configSide.value,
    selected_exchange: elements.configSelectedExchange.value.trim(),
    connector_backend: elements.configConnectorBackend.value.trim(),
    code_language: elements.configCodeLanguage.value.trim(),
    theme: elements.configTheme.value.trim(),
    leverage: readInteger(elements.configLeverage, 0),
    position_pct: readNumber(elements.configPositionPct, 0),
    order_audit_max_bytes: readInteger(elements.configOrderAuditMaxBytes, 1),
    order_audit_backup_count: readInteger(elements.configOrderAuditBackupCount, 0),
    connector_order_circuit_incident_log_max_bytes: readInteger(
      elements.configIncidentLogMaxBytes,
      1,
    ),
    connector_order_circuit_incident_log_backup_count: readInteger(
      elements.configIncidentLogBackupCount,
      0,
    ),
    operational_connector_snapshot_stale_seconds: readNumber(elements.configConnectorStaleSeconds, 120),
    operational_execution_heartbeat_stale_seconds: readNumber(
      elements.configExecutionHeartbeatStaleSeconds,
      10,
    ),
    operational_account_snapshot_stale_seconds: readNumber(elements.configAccountStaleSeconds, 300),
    operational_portfolio_snapshot_stale_seconds: readNumber(elements.configPortfolioStaleSeconds, 300),
    operational_live_start_gate_enabled: Boolean(elements.configLiveStartGateEnabled.checked),
    operational_live_order_gate_enabled: Boolean(elements.configLiveOrderGateEnabled.checked),
    live_allow_auto_bump_to_min_order: Boolean(elements.configLiveAutoBumpEnabled.checked),
    symbols: splitList(elements.configSymbols.value),
    intervals: splitList(elements.configIntervals.value),
  };
}

function collectBacktestRequest() {
  const request = {};
  const symbols = splitList(elements.backtestSymbols.value);
  const intervals = splitList(elements.backtestIntervals.value);
  const capitalText = String(elements.backtestCapital.value || "").trim();
  const logic = String(elements.backtestLogic.value || "").trim();
  const source = String(elements.backtestSource.value || "").trim();
  const start = String(elements.backtestStart.value || "").trim();
  const end = String(elements.backtestEnd.value || "").trim();

  if (symbols.length) {
    request.symbols = symbols;
  }
  if (intervals.length) {
    request.intervals = intervals;
  }
  if (capitalText) {
    request.capital = readNumber(elements.backtestCapital, 0);
  }
  if (logic) {
    request.logic = logic;
  }
  if (source) {
    request.symbol_source = source;
  }
  if (start) {
    request.start = start;
  }
  if (end) {
    request.end = end;
  }
  return request;
}

async function refreshDashboard() {
  state.baseUrl = normalizedBaseUrl();
  state.token = String(elements.apiToken.value || state.token || "").trim();
  writeStoredConfig();
  const health = await fetchJson("/health");
  renderServiceApi(health.service_api || health);
  state.authRequired = Boolean(health.auth_required);
  if (state.authRequired && !state.token) {
    setConnectionState("Token Needed", "warn");
    setConnectionMessage("The API requires a bearer token. Enter it above and connect again.");
    return;
  }
  const snapshot = await fetchJson(`${serviceApiRoute("dashboard")}?log_limit=30&incident_limit=20`);
  renderDashboardSnapshot(snapshot);
  setConnectionState("Connected", "ok");
  setConnectionMessage(
    `Connected to ${state.baseUrl}${state.authRequired ? " with bearer auth." : "."}`,
  );
}

function startPollingFallback() {
  stopRefreshTimer();
  state.refreshTimer = window.setInterval(() => {
    refreshDashboard().catch((error) => {
      setConnectionState("Error", "error");
      setConnectionMessage(error instanceof Error ? error.message : String(error));
    });
  }, 5000);
}

function openDashboardStream() {
  closeDashboardStream();
  if (!supportsDashboardStream()) {
    startPollingFallback();
    return;
  }
  const params = new URLSearchParams({ log_limit: "30", incident_limit: "20", interval_ms: "1000" });
  const streamUrl = buildDashboardStreamUrl(
    state.baseUrl,
    serviceApiRoute("stream_dashboard"),
    Object.fromEntries(params.entries()),
  );
  state.eventSource = createDashboardStream({
    streamUrl,
    headers: authHeaders(),
    onOpen: () => {
      stopRefreshTimer();
      setConnectionState("Live Stream", "ok");
      setConnectionMessage(
        `Connected to ${state.baseUrl}${state.authRequired ? " with bearer auth." : "."} Live updates use a header-authenticated stream.`,
      );
    },
    onDashboard: renderDashboardSnapshot,
    onError: (error, streamState = {}) => {
      closeDashboardStream();
      const status = Number(error?.status || 0);
      if (status === 401) {
        setConnectionState("Unauthorized", "error");
        setConnectionMessage("Live stream unauthorized. Update the bearer token and connect again.");
        return;
      }
      if (!streamState.opened) {
        setConnectionState("Stream Failed", "warn");
        setConnectionMessage("Live stream failed; falling back to periodic refresh.");
      } else {
        setConnectionState("Reconnect", "warn");
        setConnectionMessage("Live stream interrupted; falling back to periodic refresh.");
      }
      startPollingFallback();
    },
  });
}

async function connectAndRefresh() {
  state.baseUrl = normalizedBaseUrl();
  state.token = String(elements.apiToken.value || "").trim();
  writeStoredConfig();
  closeDashboardStream();
  stopRefreshTimer();
  setConnectionState("Checking", "muted");
  setConnectionMessage("Requesting service health and runtime snapshots...");
  try {
    const health = await fetchJson("/health");
    renderServiceApi(health.service_api || health);
    state.authRequired = Boolean(health.auth_required);
    if (state.authRequired) {
      const probe = await fetchJson(serviceApiRoute("status"), { allowUnauthorized: true });
      if (probe && probe.unauthorized) {
        setConnectionState("Unauthorized", "error");
        setConnectionMessage("Bearer token missing or invalid. Update the token and try again.");
        return;
      }
    }
    await refreshDashboard();
    openDashboardStream();
  } catch (error) {
    setConnectionState("Error", "error");
    setConnectionMessage(error instanceof Error ? error.message : String(error));
  }
}

async function requestStart() {
  try {
    const payload = {
      requested_job_count: readInteger(elements.controlJobs, 0),
      source: "web-ui",
    };
    const result = await sendJson("POST", serviceApiRoute("control_start"), payload);
    setControlMessage(result.status_message || "Lifecycle start request recorded.");
    await refreshDashboard();
  } catch (error) {
    setControlMessage(error instanceof Error ? error.message : String(error));
  }
}

async function requestStop() {
  try {
    const payload = {
      close_positions: Boolean(elements.controlClosePositions.checked),
      source: "web-ui",
    };
    const result = await sendJson("POST", serviceApiRoute("control_stop"), payload);
    setControlMessage(result.status_message || "Lifecycle stop request recorded.");
    await refreshDashboard();
  } catch (error) {
    setControlMessage(error instanceof Error ? error.message : String(error));
  }
}

async function syncRunning() {
  try {
    const payload = {
      active: true,
      active_engine_count: readInteger(elements.runtimeEngineCount, 0),
      source: "web-ui",
    };
    const result = await sendJson("PUT", serviceApiRoute("runtime_state"), payload);
    setControlMessage(result.status_message || "Runtime marked active.");
    await refreshDashboard();
  } catch (error) {
    setControlMessage(error instanceof Error ? error.message : String(error));
  }
}

async function syncIdle() {
  try {
    const payload = {
      active: false,
      active_engine_count: 0,
      source: "web-ui",
    };
    const result = await sendJson("PUT", serviceApiRoute("runtime_state"), payload);
    setControlMessage(result.status_message || "Runtime marked idle.");
    await refreshDashboard();
  } catch (error) {
    setControlMessage(error instanceof Error ? error.message : String(error));
  }
}

async function resetConnectorOrderCircuit() {
  try {
    const result = await sendJson("POST", serviceApiRoute("connector_order_circuit_breaker_reset"), {
      source: "web-ui",
    });
    if (result && result.reset_blocked) {
      setConnectorMessage(result.reset_blocked_reason || result.message || "Order circuit reset blocked.");
    } else {
      setConnectorMessage(result?.message || "Order circuit reset.");
    }
    await refreshDashboard();
  } catch (error) {
    setConnectorMessage(error instanceof Error ? error.message : String(error));
  }
}

async function recheckPreflight() {
  if (elements.preflightRecheckButton) {
    elements.preflightRecheckButton.disabled = true;
  }
  elements.preflightMessage.textContent = "Rechecking operational preflight...";
  try {
    const preflight = await fetchJson(serviceApiRoute("operational_preflight"));
    renderPreflight(preflight);
  } catch (error) {
    elements.preflightMessage.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    if (elements.preflightRecheckButton) {
      elements.preflightRecheckButton.disabled = false;
    }
  }
}

async function reloadConfig() {
  try {
    const config = await fetchJson(serviceApiRoute("config"));
    renderConfig(config);
    await reloadConfigPersistence();
    setConfigMessage("Config reloaded from the service.");
  } catch (error) {
    setConfigMessage(error instanceof Error ? error.message : String(error));
  }
}

async function reloadConfigPersistence() {
  const persistence = await fetchJson(serviceApiRoute("config_persistence"));
  renderConfigPersistence(persistence);
  return persistence;
}

async function saveConfigPatch() {
  try {
    const config = await sendJson("PATCH", serviceApiRoute("config"), {
      config: collectConfigPatch(),
    });
    renderConfig(config);
    setConfigMessage("Runtime config patched. Use Save File to persist it.");
    await refreshDashboard();
  } catch (error) {
    setConfigMessage(error instanceof Error ? error.message : String(error));
  }
}

async function saveConfigFile() {
  try {
    const persistence = await sendJson("POST", serviceApiRoute("config_save"), {
      source: "web-dashboard",
    });
    renderConfigPersistence(persistence);
    setConfigMessage("Current runtime config saved to the service config file.");
    await refreshDashboard();
  } catch (error) {
    setConfigMessage(error instanceof Error ? error.message : String(error));
  }
}

async function loadConfigFile() {
  try {
    const result = await sendJson("POST", serviceApiRoute("config_load"), {
      source: "web-dashboard",
    });
    if (result?.config) {
      renderConfig(result.config);
    }
    if (result?.persistence) {
      renderConfigPersistence(result.persistence);
    }
    setConfigMessage("Service config file loaded into the runtime.");
    await refreshDashboard();
  } catch (error) {
    setConfigMessage(error instanceof Error ? error.message : String(error));
  }
}

async function runBacktest() {
  try {
    const payload = {
      request: collectBacktestRequest(),
      source: "web-ui",
    };
    const result = await sendJson("POST", serviceApiRoute("backtest_run"), payload);
    elements.backtestControlMessage.textContent = result.status_message || "Backtest request submitted.";
    await refreshDashboard();
  } catch (error) {
    elements.backtestControlMessage.textContent = error instanceof Error ? error.message : String(error);
  }
}

async function stopBacktest() {
  try {
    const result = await sendJson("POST", serviceApiRoute("backtest_stop"), {
      source: "web-ui",
    });
    elements.backtestControlMessage.textContent = result.status_message || "Backtest stop requested.";
    await refreshDashboard();
  } catch (error) {
    elements.backtestControlMessage.textContent = error instanceof Error ? error.message : String(error);
  }
}

function bootstrap() {
  readStoredConfig();
  elements.baseUrl.value = state.baseUrl || window.location.origin;
  elements.apiToken.value = state.token;
  initializeBacktestFormDefaults();
  elements.connectButton.addEventListener("click", () => {
    connectAndRefresh();
  });
  elements.refreshButton.addEventListener("click", () => {
    refreshDashboard().catch((error) => {
      setConnectionState("Error", "error");
      setConnectionMessage(error instanceof Error ? error.message : String(error));
    });
  });
  elements.requestStartButton.addEventListener("click", () => {
    requestStart();
  });
  elements.requestStopButton.addEventListener("click", () => {
    requestStop();
  });
  elements.markRunningButton.addEventListener("click", () => {
    syncRunning();
  });
  elements.markIdleButton.addEventListener("click", () => {
    syncIdle();
  });
  elements.resetConnectorCircuitButton.addEventListener("click", () => {
    resetConnectorOrderCircuit();
  });
  elements.preflightRecheckButton.addEventListener("click", () => {
    recheckPreflight();
  });
  elements.reloadConfigButton.addEventListener("click", () => {
    reloadConfig();
  });
  elements.saveConfigButton.addEventListener("click", () => {
    saveConfigPatch();
  });
  elements.saveConfigFileButton.addEventListener("click", () => {
    saveConfigFile();
  });
  elements.loadConfigFileButton.addEventListener("click", () => {
    loadConfigFile();
  });
  elements.runBacktestButton.addEventListener("click", () => {
    runBacktest();
  });
  elements.stopBacktestButton.addEventListener("click", () => {
    stopBacktest();
  });
  connectAndRefresh();
}

bootstrap();
