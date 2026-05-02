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

const { renderPreflight } = await import("../modules/render.js");

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

test("blocked start disables the Request Start button", () => {
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
  assert.equal(element("request-start-button").textContent, "Start Blocked");
  assert.match(element("request-start-button").title, /execution heartbeat/);
  assert.equal(element("start-gate-state").textContent, "Preflight Blocked");
  assert.match(element("start-gate-state").className, /\berror\b/);
  assert.equal(element("preflight-remediation-count").textContent, "1");
  assert.match(element("preflight-remediation-count").className, /\bwarn\b/);
  assert.equal(element("preflight-remediation-empty").style.display, "none");
  assert.match(element("preflight-remediation-list").innerHTML, /Execution heartbeat/);
  assert.match(element("preflight-ages").textContent, /Execution 900s\/60s stale/);
});

test("idle live preflight keeps Request Start ready without an execution heartbeat", () => {
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
  assert.equal(element("request-start-button").textContent, "Request Start");
  assert.equal(element("request-start-button").title, "Preflight allows start.");
  assert.equal(element("start-gate-state").textContent, "Preflight Ready");
  assert.match(element("start-gate-state").className, /\bok\b/);
  assert.equal(element("preflight-remediation-count").textContent, "0");
  assert.equal(element("preflight-remediation-empty").style.display, "block");
  assert.equal(element("preflight-remediation-list").innerHTML, "");
  assert.doesNotMatch(element("preflight-message").textContent, /execution heartbeat/);
});

test("warning preflight leaves Request Start clickable when the start gate allows it", () => {
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
  assert.equal(element("request-start-button").textContent, "Request Start");
  assert.equal(element("start-gate-state").textContent, "Preflight Warning");
  assert.match(element("start-gate-state").className, /\bwarn\b/);
  assert.equal(element("preflight-remediation-count").textContent, "1");
  assert.match(element("preflight-remediation-list").innerHTML, /Account snapshot/);
});
