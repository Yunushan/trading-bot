import { toLocalDateTimeValue } from "./utils.js";

const STORAGE_KEY = "trading-bot-service-dashboard";

export const state = {
  baseUrl: "",
  token: "",
  authRequired: false,
  serviceApiContext: "",
  controlPlaneMode: "",
  controlPlaneStartSupported: false,
  controlPlaneStopSupported: false,
  backtestFormInitialized: false,
  refreshTimer: null,
  eventSource: null,
};

export const elements = {
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
  runtimeControlMode: document.getElementById("runtime-control-mode"),
  runtimeExecOwner: document.getElementById("runtime-exec-owner"),
  statusMode: document.getElementById("status-mode"),
  statusActive: document.getElementById("status-active"),
  statusEngines: document.getElementById("status-engines"),
  statusAccount: document.getElementById("status-account"),
  statusExchange: document.getElementById("status-exchange"),
  statusMessage: document.getElementById("status-message"),
  executionState: document.getElementById("execution-state"),
  executionKind: document.getElementById("execution-kind"),
  executionWorkload: document.getElementById("execution-workload"),
  executionSession: document.getElementById("execution-session"),
  executionJobs: document.getElementById("execution-jobs"),
  executionProgress: document.getElementById("execution-progress"),
  executionHeartbeat: document.getElementById("execution-heartbeat"),
  executionStarted: document.getElementById("execution-started"),
  executionMessage: document.getElementById("execution-message"),
  backtestState: document.getElementById("backtest-state"),
  backtestSession: document.getElementById("backtest-session"),
  backtestCounts: document.getElementById("backtest-counts"),
  backtestScope: document.getElementById("backtest-scope"),
  backtestTopRun: document.getElementById("backtest-top-run"),
  backtestStarted: document.getElementById("backtest-started"),
  backtestUpdated: document.getElementById("backtest-updated"),
  backtestMessage: document.getElementById("backtest-message"),
  backtestTopRunsCount: document.getElementById("backtest-top-runs-count"),
  backtestTopRunsEmpty: document.getElementById("backtest-top-runs-empty"),
  backtestTopRunsList: document.getElementById("backtest-top-runs-list"),
  backtestErrorsCount: document.getElementById("backtest-errors-count"),
  backtestErrorsEmpty: document.getElementById("backtest-errors-empty"),
  backtestErrorsList: document.getElementById("backtest-errors-list"),
  backtestSymbols: document.getElementById("backtest-symbols"),
  backtestIntervals: document.getElementById("backtest-intervals"),
  backtestCapital: document.getElementById("backtest-capital"),
  backtestLogic: document.getElementById("backtest-logic"),
  backtestSource: document.getElementById("backtest-source"),
  backtestStart: document.getElementById("backtest-start"),
  backtestEnd: document.getElementById("backtest-end"),
  runBacktestButton: document.getElementById("run-backtest-button"),
  stopBacktestButton: document.getElementById("stop-backtest-button"),
  backtestControlMessage: document.getElementById("backtest-control-message"),
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

export function readStoredConfig() {
  try {
    const payload = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    state.baseUrl = String(payload.baseUrl || "").trim();
    state.token = String(payload.token || "").trim();
  } catch {
    state.baseUrl = "";
    state.token = "";
  }
}

export function writeStoredConfig() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        baseUrl: state.baseUrl,
        token: state.token,
      }),
    );
  } catch {
    // Local persistence is only a convenience.
  }
}

export function normalizedBaseUrl() {
  const raw = String(elements.baseUrl.value || state.baseUrl || window.location.origin).trim();
  if (!raw) {
    return window.location.origin;
  }
  return raw.replace(/\/+$/, "");
}

export function authHeaders() {
  const token = String(elements.apiToken.value || state.token || "").trim();
  state.token = token;
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

export function closeDashboardStream() {
  if (state.eventSource) {
    try {
      state.eventSource.close();
    } catch {
      // Ignore stream close errors.
    }
    state.eventSource = null;
  }
}

export function stopRefreshTimer() {
  if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
    state.refreshTimer = null;
  }
}

export function initializeBacktestFormDefaults() {
  if (state.backtestFormInitialized) {
    return;
  }
  const now = new Date();
  const start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  if (elements.backtestStart && !elements.backtestStart.value) {
    elements.backtestStart.value = toLocalDateTimeValue(start);
  }
  if (elements.backtestEnd && !elements.backtestEnd.value) {
    elements.backtestEnd.value = toLocalDateTimeValue(now);
  }
  state.backtestFormInitialized = true;
}
