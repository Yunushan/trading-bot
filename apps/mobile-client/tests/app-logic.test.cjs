const assert = require("node:assert/strict");

const {
  DEFAULT_BASE_URL,
  configPersistenceTone,
  controlPlaneLifecycleSummary,
  currentPreflight,
  formatConnectorSupport,
  formatConfigPersistenceState,
  formatPreflightGate,
  formatPreflightMode,
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
} = require("../app-logic");

async function test(name, callback) {
  await callback();
  console.log(`ok - ${name}`);
}

async function main() {
  await test("base URL normalization keeps the default and trims trailing slashes", async () => {
    assert.equal(normalizeBaseUrl(""), DEFAULT_BASE_URL);
    assert.equal(normalizeBaseUrl("  http://192.168.1.20:8000/// "), "http://192.168.1.20:8000");
  });

  await test("preflight helpers block only explicit start disallow states", async () => {
    const blocked = {
      state: "blocked",
      live_mode: true,
      mode: "Live",
      start: {
        allowed: false,
        state: "blocked",
        gate_enabled: true,
        reasons: [" stale exchange ", "", "missing account"],
      },
    };
    const warning = {
      state: "warning",
      live_mode: false,
      mode: "Demo/Testnet",
      start: { allowed: true, state: "warning", gate_enabled: true },
    };

    assert.equal(currentPreflight({ operational: { preflight: blocked } }), blocked);
    assert.equal(currentPreflight({ status: { operational: { preflight: warning } } }), warning);
    assert.equal(isPreflightStartBlocked(blocked), true);
    assert.equal(isPreflightStartBlocked(warning), false);
    assert.equal(preflightStartGateLabel(blocked), "Preflight Blocked");
    assert.equal(preflightStartGateLabel(warning), "Preflight Warning");
    assert.equal(preflightGateReason(blocked.start), "stale exchange; missing account");
    assert.equal(formatPreflightGate(blocked.start), "Blocked / Blocked / Gate On");
    assert.equal(formatPreflightMode(blocked), "Live / Live");
    assert.equal(preflightTone("blocked"), "error");
    assert.equal(preflightTone("warning"), "warning");
  });

  await test("preflight freshness helpers surface stale inputs once with remediation text", async () => {
    const preflight = {
      critical_stale: {
        start: ["exchange_connector", "account"],
        orders: ["account", "portfolio"],
      },
      freshness: {
        exchange_connector: { stale: true, age_seconds: 65, max_age_seconds: 30 },
        execution: { stale: false, age_seconds: 3.2, max_age_seconds: 10 },
        account: { stale: true, max_age_seconds: 300 },
      },
    };

    assert.deepEqual(preflightCriticalLabels(preflight), [
      "exchange_connector",
      "account",
      "portfolio",
    ]);
    assert.equal(
      preflightFreshnessAges(preflight),
      "Exchange 65s/30s stale; Execution 3s/10s fresh; Account missing/300s stale",
    );
    assert.deepEqual(preflightFreshnessRemediations(preflight), [
      "Exchange connector: 65s old, 30s max. Check connector health, credentials, network, and rate-limit state.",
      "Account snapshot: missing, 300s max. Refresh account balances from the service or exchange connector.",
    ]);
  });

  await test("connector support helper surfaces unsupported runtime reasons", async () => {
    assert.equal(formatConnectorSupport({ trading_supported: true }), "Trading Supported");
    assert.equal(
      formatConnectorSupport({
        trading_supported: false,
        unsupported_reasons: ["Exchange 'Kraken' is not implemented by this runtime."],
      }),
      "Unsupported: Exchange 'Kraken' is not implemented by this runtime.",
    );
    assert.equal(formatConnectorSupport({ trading_supported: false }), "Unsupported");
    assert.equal(formatConnectorSupport(null), "-");
  });

  await test("config persistence helpers distinguish runtime-only, dirty, and synced states", async () => {
    assert.equal(formatConfigPersistenceState(null), "Runtime only");
    assert.equal(configPersistenceTone(null), "muted");
    assert.equal(
      formatConfigPersistenceState({ dirty: true, exists: true }),
      "Unsaved runtime changes",
    );
    assert.equal(configPersistenceTone({ dirty: true, exists: true }), "warning");
    assert.equal(formatConfigPersistenceState({ dirty: false, exists: true }), "Config file in sync");
    assert.equal(configPersistenceTone({ dirty: false, exists: true }), "ok");
  });

  await test("control-plane summaries distinguish desktop, heartbeat-only, and intent-only modes", async () => {
    assert.deepEqual(
      controlPlaneLifecycleSummary({
        mode: "desktop-gui-dispatch",
        owner: "desktop-gui",
        start_supported: true,
        stop_supported: true,
        execution_scope: "desktop-runtime",
        trading_execution_supported: false,
      }),
      {
        label: "Desktop Forwarded",
        tone: "ok",
        summary: "Lifecycle requests are forwarded to the desktop GUI, where the real live/demo runtime owns trading execution.",
      },
    );
    assert.deepEqual(
      controlPlaneLifecycleSummary({
        mode: "local-service-executor",
        owner: "service-process",
        start_supported: true,
        stop_supported: true,
        execution_scope: "service-lifecycle-heartbeat",
        trading_execution_supported: false,
      }),
      {
        label: "Heartbeat Only",
        tone: "warning",
        summary: "Standalone service start/stop manages a lifecycle heartbeat only; it does not run strategies, market-data loops, or exchange orders.",
      },
    );
    assert.deepEqual(
      controlPlaneLifecycleSummary({
        mode: "intent-only",
        start_supported: false,
        stop_supported: false,
      }),
      {
        label: "Intent Only",
        tone: "warning",
        summary: "Lifecycle requests are recorded until a real execution adapter is attached.",
      },
    );
  });

  await test("LLM hydration maps service config without reusing token values", async () => {
    const patch = hydrateLlmPatch({
      enabled: true,
      provider: "openai",
      model: "gpt-5.2",
      base_url: "https://api.openai.com/v1",
      api_key_env: "OPENAI_API_KEY",
      api_key: "must-not-copy",
      use_for: "risk_review",
      allow_public_network: true,
      reasoning_effort: "medium",
    });

    assert.deepEqual(patch, {
      llm_enabled: true,
      llm_provider: "openai",
      llm_model: "gpt-5.2",
      llm_base_url: "https://api.openai.com/v1",
      llm_api_key_env: "OPENAI_API_KEY",
      llm_api_key: "",
      llm_use_for: "risk_review",
      llm_allow_public_network: true,
      llm_reasoning_effort: "medium",
    });
  });

  await test("provider lookup and label formatting keep mobile controls deterministic", async () => {
    const providers = [
      { key: "local", label: "Local" },
      { key: "openai", label: "OpenAI" },
    ];

    assert.equal(providerByKey(providers, "openai"), providers[1]);
    assert.equal(providerByKey(providers, ""), providers[1]);
    assert.equal(providerByKey(providers, "missing"), providers[0]);
    assert.equal(titleizeLabel("signal_confirmation"), "Signal Confirmation");
    assert.equal(titleizeLabel(""), "Unknown");
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
