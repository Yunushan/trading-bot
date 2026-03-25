import { fetchJson, sendJson } from "./modules/api.js";
import { renderConfig, renderDashboardSnapshot, renderServiceApi } from "./modules/render.js";
import {
  closeDashboardStream,
  elements,
  initializeBacktestFormDefaults,
  normalizedBaseUrl,
  readStoredConfig,
  state,
  stopRefreshTimer,
  writeStoredConfig,
} from "./modules/state.js";
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
  const snapshot = await fetchJson("/api/dashboard?log_limit=30");
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
  if (typeof EventSource === "undefined") {
    startPollingFallback();
    return;
  }
  const params = new URLSearchParams({ log_limit: "30", interval_ms: "1000" });
  if (state.token) {
    params.set("token", state.token);
  }
  const streamUrl = `${state.baseUrl}/api/stream/dashboard?${params.toString()}`;
  const source = new EventSource(streamUrl);
  state.eventSource = source;
  let opened = false;

  source.addEventListener("open", () => {
    opened = true;
    stopRefreshTimer();
    setConnectionState("Live Stream", "ok");
    setConnectionMessage(
      `Connected to ${state.baseUrl}${state.authRequired ? " with bearer auth." : "."} Live updates use SSE.`,
    );
  });

  source.addEventListener("dashboard", (event) => {
    try {
      renderDashboardSnapshot(JSON.parse(event.data));
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : String(error));
    }
  });

  source.onerror = () => {
    closeDashboardStream();
    if (!opened) {
      setConnectionState("Stream Failed", "warn");
      setConnectionMessage("Live stream failed; falling back to periodic refresh.");
    } else {
      setConnectionState("Reconnect", "warn");
      setConnectionMessage("Live stream interrupted; falling back to periodic refresh.");
    }
    startPollingFallback();
  };
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
      const probe = await fetchJson("/api/status", { allowUnauthorized: true });
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
    const result = await sendJson("POST", "/api/control/start", payload);
    setControlMessage(result.status_message || "Start request recorded.");
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
    const result = await sendJson("POST", "/api/control/stop", payload);
    setControlMessage(result.status_message || "Stop request recorded.");
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
    const result = await sendJson("PUT", "/api/runtime/state", payload);
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
    const result = await sendJson("PUT", "/api/runtime/state", payload);
    setControlMessage(result.status_message || "Runtime marked idle.");
    await refreshDashboard();
  } catch (error) {
    setControlMessage(error instanceof Error ? error.message : String(error));
  }
}

async function reloadConfig() {
  try {
    const config = await fetchJson("/api/config");
    renderConfig(config);
    setConfigMessage("Config reloaded from the service.");
  } catch (error) {
    setConfigMessage(error instanceof Error ? error.message : String(error));
  }
}

async function saveConfigPatch() {
  try {
    const config = await sendJson("PATCH", "/api/config", {
      config: collectConfigPatch(),
    });
    renderConfig(config);
    setConfigMessage("Config patch saved to the service.");
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
    const result = await sendJson("POST", "/api/backtest/run", payload);
    elements.backtestControlMessage.textContent = result.status_message || "Backtest request submitted.";
    await refreshDashboard();
  } catch (error) {
    elements.backtestControlMessage.textContent = error instanceof Error ? error.message : String(error);
  }
}

async function stopBacktest() {
  try {
    const result = await sendJson("POST", "/api/backtest/stop", {
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
  elements.reloadConfigButton.addEventListener("click", () => {
    reloadConfig();
  });
  elements.saveConfigButton.addEventListener("click", () => {
    saveConfigPatch();
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
