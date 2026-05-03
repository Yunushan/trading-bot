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

function makeStorage() {
  const items = new Map();
  return {
    getItem(key) {
      return items.has(key) ? items.get(key) : null;
    },
    setItem(key, value) {
      items.set(key, String(value));
    },
    removeItem(key) {
      items.delete(key);
    },
    clear() {
      items.clear();
    },
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
globalThis.localStorage = makeStorage();
globalThis.sessionStorage = makeStorage();

const {
  PERSISTED_STORAGE_KEY,
  TOKEN_SESSION_STORAGE_KEY,
  elements,
  readStoredConfig,
  state,
  writeStoredConfig,
} = await import("../modules/state.js");
const {
  buildDashboardStreamUrl,
  createDashboardStream,
  parseServerSentEvent,
} = await import("../modules/stream.js");

async function test(name, callback) {
  await callback();
  console.log(`ok - ${name}`);
}

await test("dashboard token migrates out of localStorage into sessionStorage", async () => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(
    PERSISTED_STORAGE_KEY,
    JSON.stringify({
      baseUrl: "http://127.0.0.1:8000",
      token: "legacy-token",
    }),
  );

  readStoredConfig();

  assert.equal(state.baseUrl, "http://127.0.0.1:8000");
  assert.equal(state.token, "legacy-token");
  assert.deepEqual(JSON.parse(localStorage.getItem(PERSISTED_STORAGE_KEY)), {
    baseUrl: "http://127.0.0.1:8000",
  });
  assert.deepEqual(JSON.parse(sessionStorage.getItem(TOKEN_SESSION_STORAGE_KEY)), {
    token: "legacy-token",
  });
});

await test("dashboard token writes stay session-scoped", async () => {
  localStorage.clear();
  sessionStorage.clear();
  state.baseUrl = "http://localhost:8000";
  state.token = "session-token";

  writeStoredConfig();

  assert.deepEqual(JSON.parse(localStorage.getItem(PERSISTED_STORAGE_KEY)), {
    baseUrl: "http://localhost:8000",
  });
  assert.deepEqual(JSON.parse(sessionStorage.getItem(TOKEN_SESSION_STORAGE_KEY)), {
    token: "session-token",
  });
});

await test("dashboard stream helper sends auth header without query token", async () => {
  const streamUrl = buildDashboardStreamUrl("http://localhost:8000", "/api/v1/stream/dashboard", {
    log_limit: "30",
    interval_ms: "1000",
  });
  assert.equal(streamUrl, "http://localhost:8000/api/v1/stream/dashboard?log_limit=30&interval_ms=1000");
  assert.doesNotMatch(streamUrl, /token=/);

  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('event: dashboard\ndata: {"ok":true}\n\n'));
      controller.close();
    },
  });
  let capturedUrl = "";
  let capturedHeaders = {};
  let opened = false;
  let dashboardPayload = null;

  const handle = createDashboardStream({
    streamUrl,
    headers: { Authorization: "Bearer session-token" },
    fetchImpl: async (url, options) => {
      capturedUrl = url;
      capturedHeaders = options.headers;
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        body,
      };
    },
    onOpen: () => {
      opened = true;
    },
    onDashboard: (payload) => {
      dashboardPayload = payload;
    },
  });

  await handle.closed;

  assert.equal(opened, true);
  assert.equal(capturedUrl, streamUrl);
  assert.equal(capturedHeaders.Authorization, "Bearer session-token");
  assert.deepEqual(dashboardPayload, { ok: true });
});

await test("server-sent dashboard event parser keeps event name and JSON data", async () => {
  const event = parseServerSentEvent('event: dashboard\ndata: {"state":"ok"}');

  assert.equal(event.name, "dashboard");
  assert.equal(event.data, '{"state":"ok"}');
});
