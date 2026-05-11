const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

const PREFLIGHT_FRESHNESS_LABELS = [
  ["exchange_connector", "Exchange"],
  ["execution", "Execution"],
  ["account", "Account"],
  ["portfolio", "Portfolio"],
];

const PREFLIGHT_REMEDIATION_LABELS = {
  exchange_connector: {
    label: "Exchange connector",
    action: "Check connector health, credentials, network, and rate-limit state.",
  },
  execution: {
    label: "Execution heartbeat",
    action: "Check the execution runner heartbeat before starting live trading.",
  },
  account: {
    label: "Account snapshot",
    action: "Refresh account balances from the service or exchange connector.",
  },
  portfolio: {
    label: "Portfolio snapshot",
    action: "Refresh open and closed position state before live actions.",
  },
};

function normalizeBaseUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return DEFAULT_BASE_URL;
  }
  return raw.replace(/\/+$/, "");
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

function titleizeLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "Unknown";
  }
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function preflightTone(value) {
  const state = String(value || "").toLowerCase();
  if (state === "blocked" || state === "error") {
    return "error";
  }
  if (state === "ok" || state === "ready") {
    return "ok";
  }
  if (state === "warning") {
    return "warning";
  }
  return "muted";
}

function currentPreflight(dashboard) {
  return dashboard?.operational?.preflight || dashboard?.status?.operational?.preflight || null;
}

function isPreflightStartBlocked(preflight) {
  return Boolean(preflight?.start && typeof preflight.start === "object" && preflight.start.allowed === false);
}

function preflightStartGateLabel(preflight) {
  if (!preflight) {
    return "Preflight Unknown";
  }
  return isPreflightStartBlocked(preflight)
    ? "Preflight Blocked"
    : `Preflight ${titleizeLabel(preflight.state || "ready")}`;
}

function formatPreflightGate(gate) {
  if (!gate || typeof gate !== "object") {
    return "-";
  }
  const allowed = gate.allowed === false ? "Blocked" : "Allowed";
  const state = titleizeLabel(gate.state || (gate.allowed === false ? "blocked" : "ok"));
  const gateState = gate.gate_enabled === false ? "Gate Off" : "Gate On";
  return `${allowed} / ${state} / ${gateState}`;
}

function formatPreflightMode(preflight) {
  if (!preflight || typeof preflight !== "object") {
    return "-";
  }
  return `${preflight.live_mode ? "Live" : "Demo/Test"} / ${preflight.mode || "-"}`;
}

function formatConnectorSupport(support) {
  const payload = support && typeof support === "object" ? support : {};
  if (payload.trading_supported === true) {
    return "Trading Supported";
  }
  if (payload.trading_supported === false) {
    const reasons = Array.isArray(payload.unsupported_reasons) ? payload.unsupported_reasons : [];
    const reason = reasons.map((item) => String(item || "").trim()).find(Boolean);
    return reason ? `Unsupported: ${reason}` : "Unsupported";
  }
  return "-";
}

function preflightGateReason(gate) {
  const reasons = Array.isArray(gate?.reasons) ? gate.reasons : [];
  return reasons.map((reason) => String(reason || "").trim()).filter(Boolean).join("; ");
}

function preflightCriticalLabels(preflight) {
  const critical = preflight?.critical_stale && typeof preflight.critical_stale === "object"
    ? preflight.critical_stale
    : {};
  const labels = [];
  for (const key of ["start", "orders"]) {
    const items = Array.isArray(critical[key]) ? critical[key] : [];
    for (const item of items) {
      const label = String(item || "").trim();
      if (label && !labels.includes(label)) {
        labels.push(label);
      }
    }
  }
  return labels;
}

function formatFreshnessAge(item) {
  const maxAge = Number(item?.max_age_seconds);
  const maxText = Number.isFinite(maxAge) ? `${Math.round(maxAge)}s` : "-";
  const age = Number(item?.age_seconds);
  const ageText = Number.isFinite(age) ? `${Math.round(age)}s` : "missing";
  return `${ageText}/${maxText} ${item?.stale ? "stale" : "fresh"}`;
}

function preflightFreshnessAges(preflight) {
  const freshness = preflight?.freshness && typeof preflight.freshness === "object" ? preflight.freshness : {};
  const ages = PREFLIGHT_FRESHNESS_LABELS.map(([key, label]) => {
    const item = freshness[key];
    return item && typeof item === "object" ? `${label} ${formatFreshnessAge(item)}` : "";
  }).filter(Boolean);
  return ages.length ? ages.join("; ") : "-";
}

function preflightFreshnessRemediations(preflight) {
  const freshness = preflight?.freshness && typeof preflight.freshness === "object" ? preflight.freshness : {};
  return Object.entries(PREFLIGHT_REMEDIATION_LABELS)
    .filter(([key]) => Boolean(freshness[key]?.stale))
    .map(([key, detail]) => {
      const item = freshness[key];
      const maxAge = Number(item?.max_age_seconds);
      const age = Number(item?.age_seconds);
      const maxText = Number.isFinite(maxAge) ? `${Math.round(maxAge)}s max` : "unknown max age";
      const ageText = Number.isFinite(age) ? `${Math.round(age)}s old` : "missing";
      return `${detail.label}: ${ageText}, ${maxText}. ${detail.action}`;
    });
}

function formatConfigPersistenceState(persistence) {
  const payload = persistence && typeof persistence === "object" ? persistence : {};
  const dirty = Boolean(payload.dirty);
  const exists = Boolean(payload.exists);
  const lastSaved = formatTimestamp(payload.last_saved_at || payload.saved_at);
  const lastLoaded = formatTimestamp(payload.last_loaded_at || payload.loaded_at);
  let stateText = "Runtime only";
  if (dirty) {
    stateText = "Unsaved runtime changes";
  } else if (exists) {
    stateText = "Config file in sync";
  }
  const detail = [];
  if (lastSaved !== "-") {
    detail.push(`saved ${lastSaved}`);
  }
  if (lastLoaded !== "-") {
    detail.push(`loaded ${lastLoaded}`);
  }
  return detail.length ? `${stateText} / ${detail.join(" / ")}` : stateText;
}

function configPersistenceTone(persistence) {
  const payload = persistence && typeof persistence === "object" ? persistence : {};
  if (payload.dirty) {
    return "warning";
  }
  if (payload.exists) {
    return "ok";
  }
  return "muted";
}

function controlPlaneLifecycleSummary(controlPlane) {
  const payload = controlPlane && typeof controlPlane === "object" ? controlPlane : {};
  const mode = String(payload.mode || "").trim();
  const owner = String(payload.owner || "").trim();
  const scope = String(payload.execution_scope || "").trim();
  const startSupported = Boolean(payload.start_supported);
  const stopSupported = Boolean(payload.stop_supported);
  const tradingExecutionSupported = Boolean(payload.trading_execution_supported);
  const normalized = `${mode} ${owner} ${scope}`.toLowerCase();

  if (normalized.includes("desktop")) {
    return {
      label: "Desktop Forwarded",
      tone: "ok",
      summary: "Lifecycle requests are forwarded to the desktop GUI, where the real live/demo runtime owns trading execution.",
    };
  }

  if (mode === "local-service-executor" || scope === "service-lifecycle-heartbeat") {
    return {
      label: "Heartbeat Only",
      tone: "warning",
      summary: "Standalone service start/stop manages a lifecycle heartbeat only; it does not run strategies, market-data loops, or exchange orders.",
    };
  }

  if (mode === "intent-only" || (!startSupported && !stopSupported)) {
    return {
      label: "Intent Only",
      tone: "warning",
      summary: "Lifecycle requests are recorded until a real execution adapter is attached.",
    };
  }

  if (tradingExecutionSupported) {
    return {
      label: "Executor Attached",
      tone: "ok",
      summary: "Lifecycle requests are handled by an attached backend executor that reports trading execution support.",
    };
  }

  return {
    label: startSupported || stopSupported ? "Delegated Adapter" : "Unknown",
    tone: startSupported || stopSupported ? "warning" : "muted",
    summary: "Lifecycle request handling depends on the attached service control adapter.",
  };
}

function hydrateLlmPatch(config) {
  const payload = config || {};
  return {
    llm_enabled: Boolean(payload.enabled),
    llm_provider: payload.provider || "openai",
    llm_model: payload.model || "",
    llm_base_url: payload.base_url || "",
    llm_api_key_env: payload.api_key_env || "",
    llm_api_key: "",
    llm_use_for: payload.use_for || "advisory",
    llm_allow_public_network: Boolean(payload.allow_public_network),
    llm_reasoning_effort: payload.reasoning_effort || "default",
  };
}

function providerByKey(providers, key) {
  const providerKey = String(key || "openai");
  return providers.find((item) => item.key === providerKey) || providers[0] || null;
}

module.exports = {
  DEFAULT_BASE_URL,
  configPersistenceTone,
  controlPlaneLifecycleSummary,
  currentPreflight,
  formatConnectorSupport,
  formatConfigPersistenceState,
  formatFreshnessAge,
  formatNumber,
  formatPreflightGate,
  formatPreflightMode,
  formatTimestamp,
  hydrateLlmPatch,
  isPreflightStartBlocked,
  normalizeBaseUrl,
  preflightCriticalLabels,
  preflightFreshnessAges,
  preflightFreshnessRemediations,
  preflightGateReason,
  preflightStartGateLabel,
  preflightTone,
  providerByKey,
  titleizeLabel,
};
