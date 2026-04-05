import { elements, state } from "./state.js";
import {
  escapeHtml,
  formatNumber,
  formatTimestamp,
  titleizeLabel,
} from "./utils.js";

function renderBacktestTopRuns(topRuns) {
  const items = Array.isArray(topRuns) ? topRuns : [];
  elements.backtestTopRunsCount.textContent = String(items.length);
  elements.backtestTopRunsEmpty.style.display = items.length ? "none" : "block";
  elements.backtestTopRunsList.innerHTML = items
    .map(
      (item) => `
        <article class="mini-row">
          <div class="mini-head">
            <strong>${escapeHtml(item.symbol || "-")} @ ${escapeHtml(item.interval || "-")}</strong>
            <span>${escapeHtml(formatNumber(item.roi_percent))}%</span>
          </div>
          <div class="mini-meta">
            <span>Trades ${escapeHtml(formatNumber(item.trades))}</span>
            <span>MDD ${escapeHtml(formatNumber(item.max_drawdown_percent))}%</span>
            <span>${escapeHtml(item.logic || "-")}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderBacktestErrors(errors) {
  const items = Array.isArray(errors) ? errors : [];
  elements.backtestErrorsCount.textContent = String(items.length);
  elements.backtestErrorsEmpty.style.display = items.length ? "none" : "block";
  elements.backtestErrorsList.innerHTML = items
    .map(
      (item) => `
        <article class="mini-row error-row">
          <div class="mini-head">
            <strong>${escapeHtml(item.symbol || "-")} @ ${escapeHtml(item.interval || "-")}</strong>
          </div>
          <div class="mini-error">${escapeHtml(item.error || "Unknown error.")}</div>
        </article>
      `,
    )
    .join("");
}

function updateControlSurfaceMode() {
  const desktopEmbedded =
    state.serviceApiContext === "desktop-embedded" || state.controlPlaneMode === "desktop-gui-dispatch";
  const runtimeControlsVisible = state.controlPlaneMode === "intent-only";
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
    if (desktopEmbedded) {
      elements.controlModeHint.textContent =
        "Connected to the desktop-embedded API. Start and stop are forwarded into the live desktop GUI, and running/idle state follows the real desktop bot automatically.";
    } else if (state.controlPlaneMode === "local-service-executor") {
      elements.controlModeHint.textContent =
        "This standalone service process owns a local execution adapter. Start and stop run inside the headless service runtime, and manual running/idle sync is not needed.";
    } else if (state.controlPlaneMode === "intent-only") {
      elements.controlModeHint.textContent =
        "This service is running in intent-only mode. Start and stop record lifecycle requests; use manual running/idle sync until a real execution adapter is attached.";
    } else if (state.controlPlaneStartSupported || state.controlPlaneStopSupported) {
      elements.controlModeHint.textContent =
        "This service exposes a delegated control adapter. Start and stop are executable, but runtime state still depends on the attached backend executor.";
    } else {
      elements.controlModeHint.textContent =
        "Control-plane metadata is available, but this service does not currently expose a live execution adapter.";
    }
  }
}

function renderRuntime(runtime) {
  const controlPlane =
    runtime && typeof runtime.control_plane === "object" && runtime.control_plane
      ? runtime.control_plane
      : {};
  state.controlPlaneMode = String(controlPlane.mode || "").trim();
  state.controlPlaneStartSupported = Boolean(controlPlane.start_supported);
  state.controlPlaneStopSupported = Boolean(controlPlane.stop_supported);
  elements.runtimePhase.textContent = runtime.phase || "-";
  elements.runtimeService.textContent = runtime.service_name || "-";
  elements.runtimePlatform.textContent = runtime.platform || "-";
  elements.runtimePython.textContent = runtime.python_version || "-";
  elements.runtimeDesktop.textContent = runtime.desktop_entrypoint || "-";
  elements.runtimeControlMode.textContent = titleizeLabel(controlPlane.mode || "-");
  elements.runtimeExecOwner.textContent = titleizeLabel(controlPlane.owner || "-");
  const runtimeNotes = Array.isArray(runtime.notes) ? runtime.notes : [];
  const controlNotes = Array.isArray(controlPlane.notes) ? controlPlane.notes : [];
  const notes = [...runtimeNotes, ...controlNotes];
  elements.runtimeNotes.innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
  updateControlSurfaceMode();
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

function renderExecution(execution) {
  const payload = execution && typeof execution === "object" ? execution : {};
  const stateLabel = String(payload.state || "idle").toLowerCase();
  const isRunning = stateLabel === "running";
  elements.executionState.textContent = titleizeLabel(payload.state || "-");
  elements.executionState.className = `pill ${isRunning ? "ok" : payload.session_id ? "warn" : "muted"}`;
  elements.executionKind.textContent = titleizeLabel(payload.executor_kind || "-");
  elements.executionWorkload.textContent = titleizeLabel(payload.workload_kind || "-");
  elements.executionSession.textContent = payload.session_id || "-";
  elements.executionJobs.textContent =
    `${formatNumber(payload.active_engine_count)} / ${formatNumber(payload.requested_job_count)}`;
  elements.executionProgress.textContent =
    payload.progress_percent === null || payload.progress_percent === undefined
      ? payload.progress_label || "-"
      : `${formatNumber(payload.progress_percent)}%${payload.progress_label ? ` · ${payload.progress_label}` : ""}`;
  elements.executionHeartbeat.textContent = formatTimestamp(payload.heartbeat_at);
  elements.executionStarted.textContent = formatTimestamp(payload.started_at);
  elements.executionMessage.textContent =
    `${payload.last_message || "No execution session yet."} Source: ${payload.source || "-"}. Updated: ${formatTimestamp(payload.updated_at)}.`;
}

function renderBacktest(backtest) {
  const payload = backtest && typeof backtest === "object" ? backtest : {};
  const stateLabel = String(payload.state || "idle").toLowerCase();
  const isRunning = stateLabel === "running";
  const isWarn = stateLabel === "failed" || stateLabel === "cancelled";
  elements.backtestState.textContent = titleizeLabel(payload.state || "-");
  elements.backtestState.className = `pill ${isRunning ? "ok" : isWarn ? "warn" : payload.session_id ? "warn" : "muted"}`;
  elements.backtestSession.textContent = payload.session_id || "-";
  elements.backtestCounts.textContent = `${formatNumber(payload.run_count)} / ${formatNumber(payload.error_count)}`;
  elements.backtestScope.textContent =
    `${Array.isArray(payload.symbols) && payload.symbols.length ? payload.symbols.join(", ") : "-"} @ ${
      Array.isArray(payload.intervals) && payload.intervals.length ? payload.intervals.join(", ") : "-"
    }`;
  const topRun = payload.top_run && typeof payload.top_run === "object" ? payload.top_run : null;
  elements.backtestTopRun.textContent = topRun
    ? `${topRun.symbol || "-"} ${topRun.interval || "-"} · ${formatNumber(topRun.roi_percent)}%`
    : "-";
  elements.backtestStarted.textContent = formatTimestamp(payload.started_at);
  elements.backtestUpdated.textContent = formatTimestamp(payload.updated_at || payload.completed_at);
  elements.backtestMessage.textContent =
    `${payload.status_message || "No backtest submitted yet."} Source: ${payload.source || "-"}.`;
  renderBacktestTopRuns(payload.top_runs);
  renderBacktestErrors(payload.errors);
  if (elements.runBacktestButton) {
    elements.runBacktestButton.disabled = isRunning;
  }
  if (elements.stopBacktestButton) {
    elements.stopBacktestButton.disabled = !isRunning;
  }
}

export function renderConfig(config) {
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

export function renderServiceApi(meta) {
  const payload = meta && typeof meta === "object" ? meta : {};
  state.serviceApiContext = String(payload.host_context || "").trim();
  elements.serviceApiContext.textContent = titleizeLabel(payload.host_context || "-");
  elements.serviceApiOwner.textContent = titleizeLabel(payload.host_owner || "-");
  elements.serviceApiAuth.textContent = payload.auth_required ? "Bearer Token" : "Open";
  elements.serviceApiStream.textContent = payload.sse_available ? "SSE Live" : "Polling Only";
  updateControlSurfaceMode();
}

export function renderDashboardSnapshot(payload) {
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
  if (payload.execution) {
    renderExecution(payload.execution);
  }
  if (payload.backtest) {
    renderBacktest(payload.backtest);
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
