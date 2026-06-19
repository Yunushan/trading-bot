import assert from "node:assert/strict";

function makeElement(id) {
  return {
    id,
    textContent: "",
    innerHTML: "",
    className: "",
    value: "",
    checked: false,
    disabled: false,
    title: "",
    style: {},
  };
}

const elementMap = new Map();

globalThis.document = {
  getElementById(id) {
    if (!elementMap.has(id)) {
      elementMap.set(id, makeElement(id));
    }
    return elementMap.get(id);
  },
};

globalThis.window = {
  location: {
    origin: "http://localhost",
  },
};

globalThis.localStorage = {
  getItem() {
    return null;
  },
  setItem() {},
};

const {
  controlPlaneLifecycleSummary,
  renderDashboardSnapshot,
  renderPreflight,
} = await import("../modules/render.js");

function element(id) {
  return elementMap.get(id) || document.getElementById(id);
}

function resetElements() {
  for (const item of elementMap.values()) {
    item.textContent = "";
    item.innerHTML = "";
    item.className = "";
    item.value = "";
    item.checked = false;
    item.disabled = false;
    item.title = "";
    item.style = {};
  }
}

function freshness(overrides = {}) {
  return {
    exchange_connector: {
      stale: false,
      age_seconds: 2,
      max_age_seconds: 60,
      state: "ready",
      source: "unit-test",
    },
    execution: {
      stale: false,
      max_age_seconds: 60,
      state: "idle",
      source: "unit-test",
    },
    account: {
      stale: false,
      age_seconds: 1,
      max_age_seconds: 60,
      source: "unit-test",
    },
    portfolio: {
      stale: false,
      age_seconds: 1,
      max_age_seconds: 60,
      source: "unit-test",
    },
    ...overrides,
  };
}

function basePreflight(overrides = {}) {
  return {
    state: "ok",
    message: "Preflight passed.",
    mode: "Live",
    live_mode: true,
    start: {
      allowed: true,
      state: "ok",
      gate_enabled: true,
      reasons: [],
    },
    orders: {
      allowed: true,
      state: "ok",
      gate_enabled: true,
      reasons: [],
    },
    freshness: freshness(),
    critical_stale: {
      start: [],
      orders: [],
    },
    reasons: [],
    ...overrides,
  };
}

function test(name, callback) {
  resetElements();
  callback();
  console.log(`ok - ${name}`);
}

test("blocked start disables the Request Lifecycle Start button", () => {
  renderPreflight(basePreflight({
    state: "blocked",
    message: "Live preflight blocked.",
    start: {
      allowed: false,
      state: "blocked",
      gate_enabled: true,
      reasons: ["critical snapshots are stale: execution heartbeat"],
    },
    freshness: freshness({
      execution: {
        stale: true,
        age_seconds: 900,
        max_age_seconds: 60,
        state: "running",
        source: "unit-test",
      },
    }),
    critical_stale: {
      start: ["execution heartbeat"],
      orders: [],
    },
    reasons: ["critical snapshots are stale: execution heartbeat"],
  }));

  assert.equal(element("request-start-button").disabled, true);
  assert.equal(element("request-start-button").textContent, "Lifecycle Start Blocked");
  assert.match(element("request-start-button").title, /execution heartbeat/);
  assert.equal(element("start-gate-state").textContent, "Preflight Blocked");
  assert.match(element("start-gate-state").className, /\berror\b/);
  assert.equal(element("preflight-remediation-count").textContent, "1");
  assert.match(element("preflight-remediation-count").className, /\bwarn\b/);
  assert.equal(element("preflight-remediation-empty").style.display, "none");
  assert.match(element("preflight-remediation-list").innerHTML, /Execution heartbeat/);
  assert.match(element("preflight-ages").textContent, /Execution 900s\/60s stale/);
});

test("idle live preflight keeps Request Lifecycle Start ready without an execution heartbeat", () => {
  renderPreflight(basePreflight({
    freshness: freshness({
      execution: {
        stale: false,
        max_age_seconds: 60,
        state: "idle",
        source: "unit-test",
      },
    }),
  }));

  assert.equal(element("request-start-button").disabled, false);
  assert.equal(element("request-start-button").textContent, "Request Lifecycle Start");
  assert.equal(element("request-start-button").title, "Preflight allows start.");
  assert.equal(element("start-gate-state").textContent, "Preflight Ready");
  assert.match(element("start-gate-state").className, /\bok\b/);
  assert.equal(element("preflight-remediation-count").textContent, "0");
  assert.equal(element("preflight-remediation-empty").style.display, "block");
  assert.equal(element("preflight-remediation-list").innerHTML, "");
  assert.doesNotMatch(element("preflight-message").textContent, /execution heartbeat/);
});

test("warning preflight leaves Request Lifecycle Start clickable when the start gate allows it", () => {
  renderPreflight(basePreflight({
    state: "warning",
    message: "Preflight has warnings.",
    live_mode: false,
    mode: "Demo/Testnet",
    start: {
      allowed: true,
      state: "warning",
      gate_enabled: true,
      reasons: ["critical snapshots are stale: account", "Demo/test mode start remains allowed."],
    },
    freshness: freshness({
      account: {
        stale: true,
        age_seconds: 900,
        max_age_seconds: 60,
        source: "unit-test",
      },
    }),
    critical_stale: {
      start: ["account"],
      orders: ["account"],
    },
    reasons: ["critical snapshots are stale: account", "Demo/test mode start remains allowed."],
  }));

  assert.equal(element("request-start-button").disabled, false);
  assert.equal(element("request-start-button").textContent, "Request Lifecycle Start");
  assert.equal(element("start-gate-state").textContent, "Preflight Warning");
  assert.match(element("start-gate-state").className, /\bwarn\b/);
  assert.equal(element("preflight-remediation-count").textContent, "1");
  assert.match(element("preflight-remediation-list").innerHTML, /Account snapshot/);
});

test("control-plane lifecycle summaries distinguish desktop, heartbeat-only, and intent-only modes", () => {
  const desktopControlPlane = {
    mode: "desktop-gui-dispatch",
    owner: "desktop-gui",
    start_supported: true,
    stop_supported: true,
    execution_scope: "desktop-trading-runtime",
    trading_execution_supported: true,
  };
  const heartbeatControlPlane = {
    mode: "local-service-executor",
    owner: "service-process",
    start_supported: true,
    stop_supported: true,
    execution_scope: "service-lifecycle-heartbeat",
    trading_execution_supported: false,
  };
  const intentControlPlane = {
    mode: "intent-only",
    owner: "service-runtime",
    start_supported: false,
    stop_supported: false,
    execution_scope: "intent-only",
    trading_execution_supported: false,
  };

  assert.equal(controlPlaneLifecycleSummary(desktopControlPlane).label, "Desktop Forwarded");
  assert.equal(controlPlaneLifecycleSummary(heartbeatControlPlane).label, "Heartbeat Only");
  assert.equal(controlPlaneLifecycleSummary(intentControlPlane).label, "Intent Only");

  renderDashboardSnapshot({
    service_api: {
      host_context: "desktop-embedded",
      host_owner: "desktop-gui",
    },
    runtime: {
      phase: "phase-2-service-api",
      service_name: "trading-bot-service",
      platform: "test",
      python_version: "3.12",
      desktop_entrypoint: "apps/desktop-pyqt/main.py",
      control_plane: desktopControlPlane,
      notes: [],
    },
  });
  assert.equal(element("control-lifecycle-mode").textContent, "Desktop Forwarded");
  assert.match(element("control-lifecycle-mode").className, /\bok\b/);
  assert.equal(element("control-execution-scope").textContent, "Desktop Trading Runtime");
  assert.equal(element("control-trading-execution").textContent, "Supported");
  assert.match(element("control-mode-hint").textContent, /forwarded to the desktop GUI/);
  assert.equal(element("runtime-engine-count").disabled, true);

  renderDashboardSnapshot({
    service_api: {
      host_context: "standalone-service",
      host_owner: "service-process",
    },
    runtime: {
      phase: "phase-2-service-api",
      service_name: "trading-bot-service",
      platform: "test",
      python_version: "3.12",
      desktop_entrypoint: "apps/desktop-pyqt/main.py",
      control_plane: heartbeatControlPlane,
      notes: [],
    },
  });
  assert.equal(element("control-lifecycle-mode").textContent, "Heartbeat Only");
  assert.match(element("control-lifecycle-mode").className, /\bwarn\b/);
  assert.equal(element("control-execution-scope").textContent, "Service Lifecycle Heartbeat");
  assert.equal(element("control-trading-execution").textContent, "Not Supported");
  assert.match(element("control-mode-hint").textContent, /does not run strategies/);
  assert.equal(element("mark-running-button").style.display, "none");

  renderDashboardSnapshot({
    service_api: {
      host_context: "standalone-service",
      host_owner: "service-process",
    },
    runtime: {
      phase: "phase-2-service-api",
      service_name: "trading-bot-service",
      platform: "test",
      python_version: "3.12",
      desktop_entrypoint: "apps/desktop-pyqt/main.py",
      control_plane: intentControlPlane,
      notes: [],
    },
  });
  assert.equal(element("control-lifecycle-mode").textContent, "Intent Only");
  assert.match(element("control-lifecycle-mode").className, /\bwarn\b/);
  assert.equal(element("control-execution-scope").textContent, "Intent Only");
  assert.equal(element("control-trading-execution").textContent, "Not Supported");
  assert.match(element("control-mode-hint").textContent, /recorded until a real execution adapter/);
  assert.equal(element("mark-running-button").style.display, "");
});

test("exchange connector render surfaces unsupported exchange state", () => {
  renderDashboardSnapshot({
    status: {
      connector_health: "error",
      selected_exchange: "Unlisted",
    },
    operational: {
      exchange_connector: {
        health: "error",
        state: "unsupported_exchange",
        selected_exchange: "Unlisted",
        connector_backend: "custom-rest",
        generated_at: "2026-05-11T00:00:00+00:00",
        support: {
          trading_supported: false,
          unsupported_reasons: ["Exchange 'Unlisted' is not implemented by this runtime."],
        },
        attention: ["Exchange 'Unlisted' is not implemented by this runtime."],
      },
    },
  });

  assert.equal(element("connector-health").textContent, "Error");
  assert.equal(element("connector-state").textContent, "Unsupported Exchange");
  assert.equal(element("connector-backend").textContent, "Unlisted / custom-rest");
  assert.match(element("connector-support").textContent, /Unsupported: Exchange 'Unlisted'/);
  assert.match(element("connector-message").textContent, /Unlisted/);
});

test("config render surfaces advisory-only LLM execution boundary", () => {
  renderDashboardSnapshot({
    config: {
      mode: "Demo/Testnet",
      account_type: "Futures",
      symbols: ["BTCUSDT"],
      intervals: ["1h"],
      theme: "Dark",
      design: "Workstation",
      api_credentials_present: false,
      llm: {
        enabled: true,
        provider_label: "Local / Custom OpenAI-Compatible",
        model: "qwen3:8b",
        mode: "local",
        reasoning_effort: "default",
        catalog_revision: "2026-05-11",
        catalog_path: "~/.trading-bot/llm-models.json",
        execution_policy: {
          advisory_only: true,
          can_execute_orders: false,
        },
      },
    },
  });

  assert.equal(element("llm-enabled").textContent, "Enabled");
  assert.match(element("llm-enabled").className, /\bok\b/);
  assert.equal(element("llm-provider").textContent, "Local / Custom OpenAI-Compatible");
  assert.equal(element("llm-model").textContent, "qwen3:8b");
  assert.equal(element("llm-execution").textContent, "Advisory Only");
  assert.match(element("llm-message").textContent, /cannot submit orders/);
  assert.equal(element("llm-catalog").textContent, "2026-05-11");
  assert.equal(element("config-design").value, "Workstation");
});
