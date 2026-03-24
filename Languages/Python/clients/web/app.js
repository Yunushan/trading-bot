const state = {
  baseUrl: "",
  token: "",
  authRequired: false,
  serviceApiContext: "",
  refreshTimer: null,
  eventSource: null,
};

const elements = {
  baseUrl: document.getElementById("base-url"),
  apiToken: document.getElementById("api-token"),
  connectButton: document.getElementById("connect-button"),
  refreshButton: document.getElementById("refresh-button"),
  connectionState: document.getElementById("connection-state"),
  connectionMessage: document.getElementById("connection-message"),
  serviceApiContext: document.getElementById("service-api-context"),
  serviceApiOwner: document.getElementById("service-api-owner"),
  serviceApiAuth: document.getElementById("service-api-auth"),
  serviceApiStream: document.getElementById("service-api-stream"),
  runtimePhase: document.getElementById("runtime-phase"),
  runtimeService: document.getElementById("runtime-service"),
  runtimePlatform: document.getElementById("runtime-platform"),
  runtimePython: document.getElementById("runtime-python"),
  runtimeDesktop: document.getElementById("runtime-desktop"),
  statusMode: document.getElementById("status-mode"),
  statusActive: document.getElementById("status-active"),
  statusEngines: document.getElementById("status-engines"),
  statusAccount: document.getElementById("status-account"),
  statusExchange: document.getElementById("status-exchange"),
  statusMessage: document.getElementById("status-message"),
  controlPhase: document.getElementById("control-phase"),
  controlJobs: document.getElementById("control-jobs"),
  runtimeEngineCount: document.getElementById("runtime-engine-count"),
  controlClosePositions: document.getElementById("control-close-positions"),
  requestStartButton: document.getElementById("request-start-button"),
  markRunningButton: document.getElementById("mark-running-button"),
  requestStopButton: document.getElementById("request-stop-button"),
  markIdleButton: document.getElementById("mark-idle-button"),
  runtimeSyncActions: document.getElementById("runtime-sync-actions"),
  controlModeHint: document.getElementById("control-mode-hint"),
  controlMessage: document.getElementById("control-message"),
  configCredentials: document.getElementById("config-credentials"),
  configMode: document.getElementById("config-mode"),
  configAccountType: document.getElementById("config-account-type"),
  configMarginMode: document.getElementById("config-margin-mode"),
  configPositionMode: document.getElementById("config-position-mode"),
  configSide: document.getElementById("config-side"),
  configSelectedExchange: document.getElementById("config-selected-exchange"),
  configConnectorBackend: document.getElementById("config-connector-backend"),
  configCodeLanguage: document.getElementById("config-code-language"),
  configTheme: document.getElementById("config-theme"),
  configLeverage: document.getElementById("config-leverage"),
  configPositionPct: document.getElementById("config-position-pct"),
  configSymbols: document.getElementById("config-symbols"),
  configIntervals: document.getElementById("config-intervals"),
  reloadConfigButton: document.getElementById("reload-config-button"),
  saveConfigButton: document.getElementById("save-config-button"),
  configMessage: document.getElementById("config-message"),
  accountSource: document.getElementById("account-source"),
  accountTotal: document.getElementById("account-total"),
  accountAvailable: document.getElementById("account-available"),
  accountUpdated: document.getElementById("account-updated"),
  portfolioSource: document.getElementById("portfolio-source"),
  portfolioOpen: document.getElementById("portfolio-open"),
  portfolioClosed: document.getElementById("portfolio-closed"),
  portfolioActivePnl: document.getElementById("portfolio-active-pnl"),
  portfolioClosedPnl: document.getElementById("portfolio-closed-pnl"),
  runtimeNotes: document.getElementById("runtime-notes"),
  logsCount: document.getElementById("logs-count"),
  logsEmpty: document.getElementById("logs-empty"),
  logsList: document.getElementById("logs-list"),
};

function readStoredConfig() {
  try {
    const payload = JSON.parse(localStorage.getItem("trading-bot-service-dashboard") || "{}");
    state.baseUrl = String(payload.baseUrl || "").trim();
    state.token = String(payload.token || "").trim();
  } catch {
    state.baseUrl = "";
    state.token = "";
  }
}

function writeStoredConfig() {
  try {
    localStorage.setItem(
      "trading-bot-service-dashboard",
      JSON.stringify({
        baseUrl: state.baseUrl,
        token: state.token,
      }),
    );
  } catch {
    // Local persistence is only a convenience.
  }
}

function normalizedBaseUrl() {
  const raw = String(elements.baseUrl.value || state.baseUrl || window.location.origin).trim();
  if (!raw) {
    return window.location.origin;
  }
  return raw.replace(/\/+$/, "");
}

function authHeaders() {
  const token = String(elements.apiToken.value || state.token || "").trim();
  state.token = token;
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

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

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatTimestamp(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function titleizeLabel(value) {
  return String(value || "-")
    .split("-")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

async function requestJson(path, { method = "GET", payload = null, allowUnauthorized = false } = {}) {
  const headers = {
    Accept: "application/json",
    ...authHeaders(),
  };
  const options = {
    method,
    headers,
  };
  if (payload !== null) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(`${state.baseUrl}${path}`, options);
  if (response.status === 401 && allowUnauthorized) {
    return { unauthorized: true };
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ""}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function fetchJson(path, options = {}) {
  return requestJson(path, { ...options, method: "GET" });
}

function sendJson(method, path, payload) {
  return requestJson(path, { method, payload });
}

function closeDashboardStream() {
  if (state.eventSource) {
    try {
      state.eventSource.close();
    } catch {
      // Ignore stream close errors.
    }
    state.eventSource = null;
  }
}

function stopRefreshTimer() {
  if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
    state.refreshTimer = null;
  }
}

function readInteger(input, fallback = 0) {
  const numeric = Number.parseInt(String(input.value || "").trim(), 10);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallback;
  }
  return numeric;
}

function readNumber(input, fallback = 0) {
  const numeric = Number.parseFloat(String(input.value || "").trim());
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallback;
  }
  return numeric;
}

function splitList(value) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderRuntime(runtime) {
  elements.runtimePhase.textContent = runtime.phase || "-";
  elements.runtimeService.textContent = runtime.service_name || "-";
  elements.runtimePlatform.textContent = runtime.platform || "-";
  elements.runtimePython.textContent = runtime.python_version || "-";
  elements.runtimeDesktop.textContent = runtime.desktop_entrypoint || "-";
  const notes = Array.isArray(runtime.notes) ? runtime.notes : [];
  elements.runtimeNotes.innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
}

function renderStatus(status) {
  const stateLabel = String(status.state || "").toLowerCase();
  const lifecycle = status.lifecycle_phase || status.state || "-";
  const isActive = stateLabel === "running";
  elements.statusMode.textContent = lifecycle;
  elements.statusMode.className = `pill ${isActive ? "ok" : lifecycle === "starting" || lifecycle === "stopping" ? "warn" : "muted"}`;
  elements.statusActive.textContent = isActive ? "Yes" : "No";
  elements.statusEngines.textContent = formatNumber(status.active_engine_count);
  elements.statusAccount.textContent = `${status.mode || "-"} / ${status.account_type || "-"}`;
  elements.statusExchange.textContent = status.selected_exchange || "-";
  elements.statusMessage.textContent = `${status.status_message || "No status message."} Source: ${status.runtime_source || "-"}. Last transition: ${formatTimestamp(status.last_transition_at)}.`;
  elements.controlPhase.textContent = lifecycle;
  elements.controlPhase.className = elements.statusMode.className;
}

function renderConfig(config) {
  elements.configMode.value = config.mode || "Live";
  elements.configAccountType.value = config.account_type || "Futures";
  elements.configMarginMode.value = config.margin_mode || "Isolated";
  elements.configPositionMode.value = config.position_mode || "Hedge";
  elements.configSide.value = config.side || "BOTH";
  elements.configSelectedExchange.value = config.selected_exchange || "";
  elements.configConnectorBackend.value = config.connector_backend || "";
  elements.configCodeLanguage.value = config.code_language || "";
  elements.configTheme.value = config.theme || "";
  elements.configLeverage.value = config.leverage ?? 0;
  elements.configPositionPct.value = config.position_pct ?? 0;
  elements.configSymbols.value = Array.isArray(config.symbols) ? config.symbols.join(", ") : "";
  elements.configIntervals.value = Array.isArray(config.intervals) ? config.intervals.join(", ") : "";
  elements.configCredentials.textContent = config.api_credentials_present ? "Keys Present" : "No Keys";
  elements.configCredentials.className = `pill ${config.api_credentials_present ? "ok" : "muted"}`;
}

function renderAccount(account) {
  elements.accountSource.textContent = account.source || "-";
  elements.accountTotal.textContent = formatNumber(account.total_balance);
  elements.accountAvailable.textContent = formatNumber(account.available_balance);
  elements.accountUpdated.textContent = formatTimestamp(account.updated_at);
}

function renderPortfolio(portfolio) {
  elements.portfolioSource.textContent = portfolio.source || "-";
  elements.portfolioOpen.textContent = formatNumber(portfolio.open_position_count);
  elements.portfolioClosed.textContent = formatNumber(portfolio.closed_position_count);
  elements.portfolioActivePnl.textContent = formatNumber(portfolio.active_pnl_total);
  elements.portfolioClosedPnl.textContent = formatNumber(portfolio.closed_pnl_total);
}

function renderLogs(logs) {
  const items = Array.isArray(logs) ? logs : [];
  elements.logsCount.textContent = String(items.length);
  elements.logsEmpty.style.display = items.length ? "none" : "block";
  elements.logsList.innerHTML = items
    .map(
      (entry) => `
        <article class="log-row">
          <div class="log-meta">
            <span>${escapeHtml(String(entry.level || "info").toUpperCase())}</span>
            <span>${escapeHtml(entry.source || "service")}</span>
            <span>${escapeHtml(formatTimestamp(entry.created_at))}</span>
          </div>
          <div class="log-message">${escapeHtml(entry.message || "")}</div>
        </article>
      `,
    )
    .join("");
}

function updateControlSurfaceMode() {
  const desktopEmbedded = state.serviceApiContext === "desktop-embedded";
  const runtimeControlsVisible = !desktopEmbedded;
  if (elements.markRunningButton) {
    elements.markRunningButton.style.display = runtimeControlsVisible ? "" : "none";
  }
  if (elements.markIdleButton) {
    elements.markIdleButton.style.display = runtimeControlsVisible ? "" : "none";
  }
  if (elements.runtimeSyncActions) {
    elements.runtimeSyncActions.style.display = runtimeControlsVisible ? "flex" : "none";
  }
  if (elements.runtimeEngineCount) {
    elements.runtimeEngineCount.disabled = desktopEmbedded;
  }
  if (elements.controlModeHint) {
    elements.controlModeHint.textContent = desktopEmbedded
      ? "Connected to the desktop-embedded API. Start and stop are forwarded into the live desktop GUI, and running/idle state follows the real desktop bot automatically."
      : "Start and stop record lifecycle intent. Running and idle mirror the runtime state explicitly in the current standalone service phase.";
  }
}

function renderServiceApi(meta) {
  const payload = meta && typeof meta === "object" ? meta : {};
  state.serviceApiContext = String(payload.host_context || "").trim();
  elements.serviceApiContext.textContent = titleizeLabel(payload.host_context || "-");
  elements.serviceApiOwner.textContent = titleizeLabel(payload.host_owner || "-");
  elements.serviceApiAuth.textContent = payload.auth_required ? "Bearer Token" : "Open";
  elements.serviceApiStream.textContent = payload.sse_available ? "SSE Live" : "Polling Only";
  updateControlSurfaceMode();
}

function renderDashboardSnapshot(payload) {
  if (!payload || typeof payload !== "object") {
    return;
  }
  if (payload.service_api) {
    renderServiceApi(payload.service_api);
  }
  if (payload.runtime) {
    renderRuntime(payload.runtime);
  }
  if (payload.status) {
    renderStatus(payload.status);
  }
  if (payload.config) {
    renderConfig(payload.config);
  }
  if (payload.account) {
    renderAccount(payload.account);
  }
  if (payload.portfolio) {
    renderPortfolio(payload.portfolio);
  }
  if (Array.isArray(payload.logs)) {
    renderLogs(payload.logs);
  }
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
      setConnectionMessage(error.message);
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

function bootstrap() {
  readStoredConfig();
  const defaultBaseUrl = state.baseUrl || window.location.origin;
  elements.baseUrl.value = defaultBaseUrl;
  elements.apiToken.value = state.token;
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
  connectAndRefresh();
}

bootstrap();
