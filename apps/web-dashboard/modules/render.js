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
  const operationalHealth = String(status.operational_health || status.operational?.health || "unknown").toLowerCase();
  elements.statusOperational.textContent = titleizeLabel(operationalHealth);
  elements.statusOperational.className = `pill ${healthTone(operationalHealth)}`;
  const operationalAttention = Array.isArray(status.operational?.attention)
    ? status.operational.attention
    : [];
  const attentionItems = operationalAttention.slice(0, 3).filter(Boolean);
  const attention = attentionItems.length ? ` Attention: ${attentionItems.join(" ")}` : "";
  elements.statusMessage.textContent = `${status.status_message || "No status message."} Source: ${status.runtime_source || "-"}. Last transition: ${formatTimestamp(status.last_transition_at)}.${attention}`;
  elements.controlPhase.textContent = lifecycle;
  elements.controlPhase.className = elements.statusMode.className;
}

function healthTone(health) {
  const value = String(health || "").toLowerCase();
  if (value === "ok") {
    return "ok";
  }
  if (value === "warning") {
    return "warn";
  }
  if (value === "error") {
    return "error";
  }
  return "muted";
}

function preflightTone(preflightState) {
  const value = String(preflightState || "").toLowerCase();
  if (value === "ok") {
    return "ok";
  }
  if (value === "warning" || value === "disabled") {
    return "warn";
  }
  if (value === "blocked" || value === "error") {
    return "error";
  }
  return "muted";
}

function renderPreflightGate(gate) {
  const payload = gate && typeof gate === "object" ? gate : {};
  const stateLabel = titleizeLabel(payload.state || (payload.allowed === false ? "blocked" : "unknown"));
  const enabledLabel = payload.gate_enabled === false ? "Gate disabled" : "Gate enabled";
  const allowedLabel = payload.allowed === false ? "blocked" : payload.allowed === true ? "allowed" : "unknown";
  const reasons = Array.isArray(payload.reasons) ? payload.reasons.filter(Boolean) : [];
  const reason = reasons.length ? ` - ${reasons[0]}` : "";
  return `${stateLabel} (${enabledLabel}, ${allowedLabel})${reason}`;
}

function preflightCriticalLabels(preflight) {
  const payload = preflight && typeof preflight === "object" ? preflight : {};
  const critical = payload.critical_stale;
  const labels = [];
  const addLabel = (label) => {
    const value = String(label || "").trim();
    if (value && !labels.includes(value)) {
      labels.push(value);
    }
  };
  if (Array.isArray(critical)) {
    critical.forEach(addLabel);
  } else if (critical && typeof critical === "object") {
    Object.values(critical).forEach((items) => {
      if (Array.isArray(items)) {
        items.forEach(addLabel);
      }
    });
  }
  return labels;
}

export function renderPreflight(preflight) {
  const payload = preflight && typeof preflight === "object" ? preflight : {};
  const stateLabel = String(payload.state || "unknown").toLowerCase();
  const critical = preflightCriticalLabels(payload);
  const reasons = Array.isArray(payload.reasons) ? payload.reasons.filter(Boolean) : [];
  const message = String(payload.message || "").trim();
  const reasonText = reasons.length ? ` Reasons: ${reasons.join(" ")}` : "";
  elements.preflightState.textContent = titleizeLabel(stateLabel);
  elements.preflightState.className = `pill ${preflightTone(stateLabel)}`;
  elements.preflightStart.textContent = renderPreflightGate(payload.start);
  elements.preflightOrders.textContent = renderPreflightGate(payload.orders);
  elements.preflightMode.textContent = `${payload.live_mode ? "Live" : "Demo/Test"} / ${payload.mode || "-"}`;
  elements.preflightCritical.textContent = critical.length ? critical.join(", ") : "Fresh";
  elements.preflightMessage.textContent = `${message || "No preflight snapshot received yet."}${reasonText}`;
}

function renderRateLimit(rateLimit) {
  const payload = rateLimit && typeof rateLimit === "object" ? rateLimit : {};
  if (payload.active) {
    const seconds = Number(payload.seconds_until_unban);
    if (Number.isFinite(seconds) && seconds > 0) {
      return `Limited for ${formatNumber(seconds)}s`;
    }
    return "Limited";
  }
  if (Object.hasOwn(payload, "active")) {
    return "Clear";
  }
  return "-";
}

function renderNetwork(network) {
  const payload = network && typeof network === "object" ? network : {};
  if (payload.offline) {
    const hits = Number(payload.offline_hits);
    return Number.isFinite(hits) && hits > 0 ? `Offline (${formatNumber(hits)} hits)` : "Offline";
  }
  if (Object.hasOwn(payload, "offline")) {
    return "Online";
  }
  return "-";
}

function renderConnectorError(lastError) {
  const payload = lastError && typeof lastError === "object" ? lastError : null;
  if (!payload) {
    return "No recent error";
  }
  const category = titleizeLabel(payload.category || "exchange");
  const message = String(payload.message || "").trim();
  return message ? `${category}: ${message}` : category;
}

function renderOrderCircuit(orderCircuit) {
  const payload = orderCircuit && typeof orderCircuit === "object" ? orderCircuit : {};
  if (payload.active) {
    const blockCount = formatNumber(payload.block_count);
    const threshold = formatNumber(payload.block_threshold);
    return `Open (${blockCount}/${threshold} blocks)`;
  }
  if (payload.cleared_at) {
    return `Closed ${formatTimestamp(payload.cleared_at)}`;
  }
  return titleizeLabel(payload.state || "closed");
}

function renderCircuitIncidentLog(incidentLog) {
  const payload = incidentLog && typeof incidentLog === "object" ? incidentLog : {};
  const path = String(payload.path || "").trim();
  if (!path) {
    return "-";
  }
  const writeError = String(payload.last_write_error?.message || "").trim();
  if (payload.write_ok === false || writeError) {
    return `${path} (write failed${writeError ? `: ${writeError}` : ""})`;
  }
  const source = titleizeLabel(payload.path_source || "");
  const maxBytes = Number(payload.max_bytes || 0);
  const backupCount = Number(payload.backup_count ?? -1);
  const retention = [];
  if (source && source !== "-") {
    retention.push(source);
  }
  if (Number.isFinite(maxBytes) && maxBytes > 0) {
    retention.push(`${formatNumber(maxBytes)} B`);
  }
  if (Number.isFinite(backupCount) && backupCount >= 0) {
    retention.push(`${formatNumber(backupCount)} backup${backupCount === 1 ? "" : "s"}`);
  }
  return retention.length ? `${path} (${retention.join(", ")})` : path;
}

function renderLastCircuitIncident(incidentLog) {
  const payload = incidentLog && typeof incidentLog === "object" ? incidentLog : {};
  const event = payload.last_event && typeof payload.last_event === "object" ? payload.last_event : null;
  if (!event) {
    return "No persisted incident";
  }
  const rawAction = String(event.action || event.event || "incident").replace(
    /^connector_order_circuit_/,
    "",
  );
  const action = titleizeLabel(rawAction.replaceAll("_", "-"));
  const timestamp = formatTimestamp(event.ts || event.created_at || event.generated_at);
  return timestamp === "-" ? action : `${action} @ ${timestamp}`;
}

function renderConnectorIncidents(incidents) {
  const payload = incidents && typeof incidents === "object" ? incidents : {};
  const events = Array.isArray(payload.events) ? payload.events : [];
  elements.connectorIncidentsCount.textContent = String(events.length);
  elements.connectorIncidentsEmpty.style.display = events.length ? "none" : "block";
  elements.connectorIncidentsList.innerHTML = events
    .map((item) => {
      const rawAction = String(item.action || item.event || "incident").replace(
        /^connector_order_circuit_/,
        "",
      );
      const action = titleizeLabel(rawAction.replaceAll("_", "-"));
      const timestamp = formatTimestamp(item.ts || item.created_at || item.generated_at);
      const reason = titleizeLabel(item.reason || item.state || "");
      const blockCount =
        item.block_count === null || item.block_count === undefined
          ? ""
          : `Blocks ${escapeHtml(formatNumber(item.block_count))}`;
      const message = String(item.message || item.circuit?.message || "").trim();
      const meta = [timestamp, reason, blockCount].filter((value) => value && value !== "-");
      return `
        <article class="mini-row">
          <div class="mini-head">
            <strong>${escapeHtml(action)}</strong>
            <span>${escapeHtml(timestamp)}</span>
          </div>
          ${meta.length ? `<div class="mini-meta">${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>` : ""}
          ${message ? `<div class="mini-error">${escapeHtml(message)}</div>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderConnectorMessage(connector, orderCircuit) {
  const circuit = orderCircuit && typeof orderCircuit === "object" ? orderCircuit : {};
  if (circuit.active && circuit.reset_blocked_reason) {
    return circuit.reset_blocked_reason;
  }
  if (circuit.active && circuit.message) {
    return circuit.message;
  }
  const attention = Array.isArray(connector.attention) ? connector.attention : [];
  if (attention.length) {
    return attention[0];
  }
  const source = connector.source || "-";
  const generatedAt = formatTimestamp(connector.generated_at);
  return `Source: ${source}. Updated: ${generatedAt}.`;
}

function renderExchangeConnector(connector, status = {}, orderCircuit = {}, incidentLog = {}) {
  const payload = connector && typeof connector === "object" ? connector : {};
  const circuit = orderCircuit && typeof orderCircuit === "object" ? orderCircuit : {};
  const incidents = incidentLog && typeof incidentLog === "object" ? incidentLog : {};
  const health = String(payload.health || status.connector_health || "unknown").toLowerCase();
  const exchange = payload.selected_exchange || status.selected_exchange || "-";
  const backend = payload.connector_backend || "-";
  elements.connectorHealth.textContent = titleizeLabel(health);
  elements.connectorHealth.className = `pill ${healthTone(health)}`;
  elements.connectorState.textContent = titleizeLabel(payload.state || "-");
  elements.connectorBackend.textContent = `${exchange} / ${backend}`;
  elements.connectorRateLimit.textContent = renderRateLimit(payload.rate_limit);
  elements.connectorNetwork.textContent = renderNetwork(payload.network);
  elements.connectorOrderCircuit.textContent = renderOrderCircuit(circuit);
  elements.connectorIncidentLog.textContent = renderCircuitIncidentLog(incidents);
  elements.connectorIncidentLog.title = String(incidents.last_write_error?.message || incidents.path || "");
  elements.connectorLastIncident.textContent = renderLastCircuitIncident(incidents);
  elements.connectorLastIncident.title = String(incidents.last_event?.message || "");
  elements.connectorUpdated.textContent = formatTimestamp(payload.generated_at);
  elements.connectorLastError.textContent = renderConnectorError(payload.last_error);
  elements.connectorMessage.textContent = renderConnectorMessage(payload, circuit);
  if (elements.resetConnectorCircuitButton) {
    elements.resetConnectorCircuitButton.disabled = !circuit.active;
  }
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
  elements.configOrderAuditMaxBytes.value = config.order_audit_max_bytes ?? 10485760;
  elements.configOrderAuditBackupCount.value = config.order_audit_backup_count ?? 1;
  elements.configIncidentLogMaxBytes.value =
    config.connector_order_circuit_incident_log_max_bytes ?? 2097152;
  elements.configIncidentLogBackupCount.value =
    config.connector_order_circuit_incident_log_backup_count ?? 1;
  elements.configConnectorStaleSeconds.value =
    config.operational_connector_snapshot_stale_seconds ?? 120;
  elements.configExecutionHeartbeatStaleSeconds.value =
    config.operational_execution_heartbeat_stale_seconds ?? 10;
  elements.configAccountStaleSeconds.value = config.operational_account_snapshot_stale_seconds ?? 300;
  elements.configPortfolioStaleSeconds.value =
    config.operational_portfolio_snapshot_stale_seconds ?? 300;
  elements.configLiveStartGateEnabled.checked = config.operational_live_start_gate_enabled ?? true;
  elements.configLiveOrderGateEnabled.checked = config.operational_live_order_gate_enabled ?? true;
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
  renderPreflight(payload.operational?.preflight || payload.status?.operational?.preflight);
  renderExchangeConnector(
    payload.operational?.exchange_connector || payload.status?.exchange_connector,
    payload.status || {},
    payload.operational?.connector_order_circuit_breaker || payload.status?.operational?.connector_order_circuit_breaker,
    payload.operational?.connector_order_circuit_incident_log
      || payload.status?.operational?.connector_order_circuit_incident_log,
  );
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
  renderConnectorIncidents(
    payload.connector_order_circuit_incidents
      || payload.operational?.connector_order_circuit_incidents
      || {},
  );
}
