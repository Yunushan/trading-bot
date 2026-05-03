import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

const { serviceApiRoute } = require("./service-contract");
const {
  DEFAULT_BASE_URL,
  configPersistenceTone,
  controlPlaneLifecycleSummary,
  currentPreflight,
  formatConfigPersistenceState,
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
} = require("./app-logic");

const LLM_USE_FOR_OPTIONS = [
  { label: "Advisory", value: "advisory" },
  { label: "Signals", value: "signal_confirmation" },
  { label: "Risk", value: "risk_review" },
  { label: "Backtest", value: "backtest_explanation" },
];

function StatusChip({ label, tone = "muted" }) {
  return (
    <View style={[styles.pill, styles[`pill_${tone}`] || styles.pill_muted]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  );
}

function Card({ title, tone, children }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHead}>
        <Text style={styles.cardTitle}>{title}</Text>
        {tone ? <StatusChip label={tone.label} tone={tone.tone} /> : null}
      </View>
      {children}
    </View>
  );
}

function StatRow({ label, value }) {
  return (
    <View style={styles.statRow}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

function ToggleRow({ label, active, onPress }) {
  return (
    <Pressable style={styles.toggleRow} onPress={onPress}>
      <Text style={styles.statLabel}>{label}</Text>
      <View style={[styles.switchTrack, active ? styles.switchTrackOn : null]}>
        <View style={[styles.switchKnob, active ? styles.switchKnobOn : null]} />
      </View>
    </Pressable>
  );
}

export default function App() {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("Connect to a running service API.");
  const [health, setHealth] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [terminalCommand, setTerminalCommand] = useState("status");
  const [terminalHistory, setTerminalHistory] = useState([]);
  const [llmProviders, setLlmProviders] = useState([]);
  const [llmConfig, setLlmConfig] = useState(null);
  const [llmPatch, setLlmPatch] = useState(hydrateLlmPatch(null));
  const [llmPrompt, setLlmPrompt] = useState("Summarize the current trading bot risk.");
  const [llmResult, setLlmResult] = useState(null);
  const [configPersistence, setConfigPersistence] = useState(null);

  const requestJson = async (path, { method = "GET", body = null } = {}) => {
    const headers = { Accept: "application/json" };
    const authToken = String(token || "").trim();
    if (authToken) {
      headers.Authorization = `Bearer ${authToken}`;
    }
    const options = { method, headers };
    if (body !== null) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, options);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ""}`);
    }
    return response.json();
  };

  const refresh = async () => {
    setLoading(true);
    try {
      const nextHealth = await requestJson("/health");
      setHealth(nextHealth);
      const nextDashboard = await requestJson(`${serviceApiRoute("dashboard")}?log_limit=10`);
      setDashboard(nextDashboard);
      setConfigPersistence(nextDashboard?.config_persistence || null);
      const nextProviders = await requestJson(serviceApiRoute("llm_providers"));
      setLlmProviders(Array.isArray(nextProviders) ? nextProviders : []);
      const nextLlmConfig = await requestJson(serviceApiRoute("llm_config"));
      setLlmConfig(nextLlmConfig);
      setLlmPatch(hydrateLlmPatch(nextLlmConfig));
      setMessage(`Connected to ${normalizeBaseUrl(baseUrl)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  };

  const recheckPreflight = async () => {
    setLoading(true);
    try {
      const nextPreflight = await requestJson(serviceApiRoute("operational_preflight"));
      setDashboard((current) => {
        const payload = current && typeof current === "object" ? current : {};
        const operational = payload.operational && typeof payload.operational === "object" ? payload.operational : {};
        return {
          ...payload,
          operational: {
            ...operational,
            preflight: nextPreflight,
          },
        };
      });
      setMessage(nextPreflight.message || "Preflight refreshed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  };

  const sendLifecycle = async (action) => {
    const preflight = currentPreflight(dashboard);
    if (action === "start" && isPreflightStartBlocked(preflight)) {
      const detail = preflightGateReason(preflight.start) || preflight.message || "live start is blocked";
      setMessage(`Live start blocked by preflight: ${detail}`);
      return;
    }
    setLoading(true);
    try {
      const path = action === "start" ? serviceApiRoute("control_start") : serviceApiRoute("control_stop");
      const body =
        action === "start"
          ? { requested_job_count: 1, source: "mobile-client" }
          : { close_positions: false, source: "mobile-client" };
      const result = await requestJson(path, { method: "POST", body });
      setMessage(result.status_message || `Lifecycle ${action} request sent.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  const runBacktest = async () => {
    setLoading(true);
    try {
      const result = await requestJson(serviceApiRoute("backtest_run"), {
        method: "POST",
        body: { request: {}, source: "mobile-client" },
      });
      setMessage(result.status_message || "Backtest request sent.");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  const runTerminalCommand = async (commandText = terminalCommand) => {
    const command = String(commandText || "").trim();
    if (!command) {
      setMessage("Enter a terminal command first.");
      return;
    }
    setLoading(true);
    try {
      const result = await requestJson(serviceApiRoute("terminal_run"), {
        method: "POST",
        body: { command, source: "mobile-terminal" },
      });
      setTerminalHistory((items) => [result, ...items].slice(0, 8));
      setMessage(result.accepted ? "Terminal command completed." : "Terminal command failed.");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  const updateLlmPatch = (patch) => {
    setLlmPatch((current) => ({ ...current, ...patch }));
  };

  const applyConfigPersistence = (persistence) => {
    setConfigPersistence(persistence || null);
    setDashboard((current) => {
      if (!current || typeof current !== "object") {
        return current;
      }
      return {
        ...current,
        config_persistence: persistence || null,
      };
    });
  };

  const llmProviderDefaultsPatch = (provider) => {
    const suggestions = Array.isArray(provider?.model_suggestions) ? provider.model_suggestions : [];
    return {
      llm_provider: provider?.key || "local",
      llm_model: suggestions[0] || provider?.default_model || "",
      llm_reasoning_effort: provider?.default_reasoning_effort || provider?.reasoning_efforts?.[0] || "default",
      llm_base_url: provider?.default_base_url || "",
      llm_api_key_env: provider?.api_key_env || "",
      llm_allow_public_network: provider?.mode === "cloud",
    };
  };

  const localLlmProvider = () =>
    llmProviders.find((provider) => provider.key === "local" || provider.mode === "local") || {
      key: "local",
      default_model: "llama3.3",
      default_base_url: "http://127.0.0.1:11434/v1",
      api_key_env: "LOCAL_LLM_API_KEY",
      model_suggestions: ["llama3.3"],
      reasoning_efforts: ["default", "none", "low", "medium", "high", "xhigh"],
      mode: "local",
    };

  const setLlmAllowPublicNetwork = () => {
    const nextAllow = !llmPatch.llm_allow_public_network;
    const selectedProvider = providerByKey(llmProviders, llmPatch.llm_provider);
    if (!nextAllow && selectedProvider?.mode === "cloud") {
      updateLlmPatch({
        ...llmProviderDefaultsPatch(localLlmProvider()),
        llm_allow_public_network: false,
      });
      return;
    }
    updateLlmPatch({ llm_allow_public_network: nextAllow });
  };

  const selectLlmProvider = (providerKey) => {
    const provider = providerByKey(llmProviders, providerKey);
    if (!provider) {
      return;
    }
    if (provider.mode === "cloud" && !llmPatch.llm_allow_public_network) {
      return;
    }
    updateLlmPatch(llmProviderDefaultsPatch(provider));
  };

  const saveLlmSettings = async () => {
    setLoading(true);
    try {
      const payload = { ...llmPatch };
      if (!String(payload.llm_api_key || "").trim()) {
        delete payload.llm_api_key;
      }
      const result = await requestJson(serviceApiRoute("llm_config"), {
        method: "PATCH",
        body: { config: payload },
      });
      setLlmConfig(result);
      setLlmPatch(hydrateLlmPatch(result));
      await refresh();
      setMessage("LLM settings saved to runtime. Save Config File to persist.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  const refreshConfigPersistence = async () => {
    setLoading(true);
    try {
      const persistence = await requestJson(serviceApiRoute("config_persistence"));
      applyConfigPersistence(persistence);
      setMessage("Config persistence refreshed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  };

  const saveConfigFile = async () => {
    setLoading(true);
    try {
      const persistence = await requestJson(serviceApiRoute("config_save"), {
        method: "POST",
        body: { source: "mobile-client" },
      });
      applyConfigPersistence(persistence);
      setMessage("Current runtime config saved to the service config file.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  };

  const loadConfigFile = async () => {
    setLoading(true);
    try {
      const result = await requestJson(serviceApiRoute("config_load"), {
        method: "POST",
        body: { source: "mobile-client" },
      });
      applyConfigPersistence(result?.persistence || null);
      await refresh();
      setMessage("Service config file loaded into the runtime.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  const runLlmDryRun = async () => {
    const prompt = String(llmPrompt || "").trim();
    if (!prompt) {
      setMessage("Enter an LLM test prompt first.");
      return;
    }
    setLoading(true);
    try {
      const result = await requestJson(serviceApiRoute("llm_prompt"), {
        method: "POST",
        body: {
          prompt,
          dry_run: true,
          source: "mobile-llm-settings",
        },
      });
      setLlmResult(result);
      setMessage(result.ok ? "LLM request prepared." : "LLM request check failed.");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh().catch(() => {});
    // Base URL and token are user-controlled and do not auto-refresh.
    // The initial connect probe keeps the scaffold useful on first launch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runtime = dashboard?.runtime || {};
  const status = dashboard?.status || {};
  const backtest = dashboard?.backtest || {};
  const topRun = backtest.top_run || null;
  const logs = Array.isArray(dashboard?.logs) ? dashboard.logs.slice(0, 5) : [];
  const authRequired = Boolean(health?.service_api?.auth_required ?? health?.auth_required);
  const hostContext = health?.service_api?.host_context || health?.host_context || "-";
  const runtimeTone =
    String(status.state || "").toLowerCase() === "running"
      ? { label: "Running", tone: "ok" }
      : { label: "Idle", tone: "muted" };
  const backtestTone =
    String(backtest.state || "").toLowerCase() === "running"
      ? { label: "Running", tone: "ok" }
      : String(backtest.state || "").toLowerCase() === "failed"
        ? { label: "Failed", tone: "error" }
        : { label: backtest.state || "Idle", tone: "muted" };
  const selectedLlmProvider = providerByKey(llmProviders, llmPatch.llm_provider);
  const selectedModelSuggestions = Array.isArray(selectedLlmProvider?.model_suggestions)
    ? selectedLlmProvider.model_suggestions.map((model) => String(model))
    : [];
  const selectedReasoningEfforts = Array.isArray(selectedLlmProvider?.reasoning_efforts)
    ? selectedLlmProvider.reasoning_efforts.map((effort) => String(effort))
    : ["default"];
  const llmTone = llmPatch.llm_enabled
    ? { label: "Enabled", tone: "ok" }
    : { label: "Disabled", tone: "muted" };
  const llmSettingsEnabled = Boolean(llmPatch.llm_enabled);
  const preflight = currentPreflight(dashboard);
  const preflightState = preflight?.state || "unknown";
  const preflightStartBlocked = isPreflightStartBlocked(preflight);
  const preflightReasons = Array.isArray(preflight?.reasons)
    ? preflight.reasons.map((reason) => String(reason || "").trim()).filter(Boolean)
    : [];
  const preflightCritical = preflightCriticalLabels(preflight);
  const preflightAttention = preflightFreshnessRemediations(preflight);
  const preflightToneInfo = {
    label: titleizeLabel(preflightState),
    tone: preflightTone(preflightState),
  };
  const startGateToneInfo = {
    label: preflightStartGateLabel(preflight),
    tone: preflightTone(preflightStartBlocked ? "blocked" : preflightState),
  };
  const controlPlane = runtime.control_plane && typeof runtime.control_plane === "object"
    ? runtime.control_plane
    : {};
  const lifecycleModeInfo = controlPlaneLifecycleSummary(controlPlane);
  const configPersistenceInfo = configPersistence || dashboard?.config_persistence || null;
  const configPersistenceToneInfo = {
    label: configPersistenceInfo?.dirty
      ? "Unsaved"
      : configPersistenceInfo?.exists
        ? "Synced"
        : "Runtime Only",
    tone: configPersistenceTone(configPersistenceInfo),
  };

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.eyebrow}>Thin Mobile Client</Text>
        <Text style={styles.title}>Trading Bot Mobile</Text>
        <Text style={styles.lede}>
          Android and iOS starter over the existing service API. This client is intentionally thin:
          inspect runtime, request lifecycle heartbeat changes, and trigger the extracted backtest runner.
        </Text>

        <Card title="Connection">
          <Text style={styles.fieldLabel}>Base URL</Text>
          <TextInput
            value={baseUrl}
            onChangeText={setBaseUrl}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
            placeholder="http://192.168.x.x:8000"
            placeholderTextColor="#7d93aa"
          />
          <Text style={styles.fieldLabel}>Bearer Token</Text>
          <TextInput
            value={token}
            onChangeText={setToken}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            style={styles.input}
            placeholder="Optional"
            placeholderTextColor="#7d93aa"
          />
          <View style={styles.buttonRow}>
            <Pressable style={styles.button} onPress={() => refresh()}>
              <Text style={styles.buttonText}>Connect / Refresh</Text>
            </Pressable>
          </View>
          <StatRow label="Host Context" value={hostContext} />
          <StatRow label="Auth" value={authRequired ? "Bearer Token" : "Open"} />
          <Text style={styles.message}>{message}</Text>
          {loading ? <ActivityIndicator color="#57c6ff" style={styles.loader} /> : null}
        </Card>

        <Card title="Runtime" tone={runtimeTone}>
          <StatRow label="Service" value={runtime.service_name || "-"} />
          <StatRow label="Control Mode" value={runtime.control_plane?.mode || "-"} />
          <StatRow label="Status" value={status.status_message || "-"} />
          <StatRow label="Mode / Account" value={`${status.mode || "-"} / ${status.account_type || "-"}`} />
          <StatRow label="Exchange" value={status.selected_exchange || "-"} />
        </Card>

        <Card title="Preflight" tone={preflightToneInfo}>
          <StatRow label="Start" value={formatPreflightGate(preflight?.start)} />
          <StatRow label="Orders" value={formatPreflightGate(preflight?.orders)} />
          <StatRow label="Mode" value={formatPreflightMode(preflight)} />
          <StatRow
            label="Critical"
            value={preflightCritical.length ? preflightCritical.join(", ") : "Fresh"}
          />
          <StatRow label="Ages" value={preflightFreshnessAges(preflight)} />
          <Text style={styles.message}>
            {preflight?.message || "No preflight snapshot returned yet."}
            {preflightReasons.length ? ` ${preflightReasons.join("; ")}` : ""}
          </Text>
          {preflightAttention.length ? (
            preflightAttention.map((item) => (
              <Text key={item} style={styles.attentionItem}>
                {item}
              </Text>
            ))
          ) : (
            <Text style={styles.message}>No stale preflight inputs reported.</Text>
          )}
          <View style={styles.buttonRow}>
            <Pressable style={[styles.button, styles.secondaryButton]} onPress={() => recheckPreflight()}>
              <Text style={styles.buttonText}>Recheck Preflight</Text>
            </Pressable>
          </View>
        </Card>

        <Card title="Lifecycle Controls" tone={lifecycleModeInfo}>
          <StatRow label="Lifecycle Mode" value={lifecycleModeInfo.label} />
          <StatRow label="Control Mode" value={controlPlane.mode || "-"} />
          <StatRow label="Owner" value={controlPlane.owner || "-"} />
          <StatRow label="Scope" value={controlPlane.execution_scope || "-"} />
          <StatRow
            label="Trading Execution"
            value={controlPlane.trading_execution_supported ? "Supported" : "Not supported"}
          />
          <StatRow label="Preflight Start Gate" value={preflightStartGateLabel(preflight)} />
          <Text style={styles.message}>{lifecycleModeInfo.summary}</Text>
          <View style={styles.buttonRow}>
            <Pressable
              style={[styles.button, preflightStartBlocked ? styles.disabledButton : null]}
              disabled={preflightStartBlocked}
              accessibilityState={{ disabled: preflightStartBlocked }}
              onPress={() => sendLifecycle("start")}
            >
              <Text style={styles.buttonText}>Request Lifecycle Start</Text>
            </Pressable>
            <Pressable style={[styles.button, styles.secondaryButton]} onPress={() => sendLifecycle("stop")}>
              <Text style={styles.buttonText}>Request Lifecycle Stop</Text>
            </Pressable>
          </View>
        </Card>

        <Card title="AI / LLM Settings" tone={llmTone}>
          <ToggleRow
            label="Enable LLM assistance"
            active={Boolean(llmPatch.llm_enabled)}
            onPress={() => updateLlmPatch({ llm_enabled: !llmPatch.llm_enabled })}
          />
          <View
            style={[styles.fadeSection, llmSettingsEnabled ? null : styles.fadeSectionDisabled]}
            pointerEvents={llmSettingsEnabled ? "auto" : "none"}
          >
            <ToggleRow
              label="Allow public network endpoint"
              active={Boolean(llmPatch.llm_allow_public_network)}
              onPress={setLlmAllowPublicNetwork}
            />

            <Text style={styles.fieldLabel}>Provider</Text>
            <View style={styles.optionGrid}>
              {(llmProviders.length ? llmProviders : [{ key: "openai", label: "OpenAI / ChatGPT", mode: "cloud" }]).map((provider) => {
                const providerDisabled =
                  !llmSettingsEnabled ||
                  (provider.mode === "cloud" && !llmPatch.llm_allow_public_network);
                return (
                  <Pressable
                    key={provider.key}
                    style={[
                      styles.optionButton,
                      llmPatch.llm_provider === provider.key ? styles.optionButtonSelected : null,
                      providerDisabled ? styles.disabledButton : null,
                    ]}
                    disabled={providerDisabled}
                    onPress={() => selectLlmProvider(provider.key)}
                  >
                    <Text style={styles.optionButtonText}>{provider.label || provider.key}</Text>
                  </Pressable>
                );
              })}
            </View>

            <Text style={styles.fieldLabel}>Model</Text>
            <StatRow label="Selected Model" value={llmPatch.llm_model || "-"} />
            {selectedModelSuggestions.length ? (
              <View style={styles.optionGrid}>
                {selectedModelSuggestions.map((model) => (
                  <Pressable
                    key={model}
                    style={[
                      styles.optionButton,
                      llmPatch.llm_model === model ? styles.optionButtonSelected : null,
                    ]}
                    disabled={!llmSettingsEnabled}
                    onPress={() => updateLlmPatch({ llm_model: model })}
                  >
                    <Text style={styles.optionButtonText}>{model}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}

            <Text style={styles.fieldLabel}>Reasoning / Thinking</Text>
            <StatRow label="Selected Effort" value={llmPatch.llm_reasoning_effort || "default"} />
            <View style={styles.optionGrid}>
              {selectedReasoningEfforts.map((effort) => (
                <Pressable
                  key={effort}
                  style={[
                    styles.optionButton,
                    (llmPatch.llm_reasoning_effort || "default") === effort ? styles.optionButtonSelected : null,
                  ]}
                  disabled={!llmSettingsEnabled}
                  onPress={() => updateLlmPatch({ llm_reasoning_effort: effort })}
                >
                  <Text style={styles.optionButtonText}>{effort}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Base URL / Local or Private IP</Text>
            <TextInput
              value={llmPatch.llm_base_url}
              onChangeText={(value) => updateLlmPatch({ llm_base_url: value })}
              autoCapitalize="none"
              autoCorrect={false}
              editable={llmSettingsEnabled}
              style={styles.input}
              placeholder="http://192.168.1.20:11434/v1"
              placeholderTextColor="#7d93aa"
            />

            <Text style={styles.fieldLabel}>API Key Environment Variable</Text>
            <TextInput
              value={llmPatch.llm_api_key_env}
              onChangeText={(value) => updateLlmPatch({ llm_api_key_env: value })}
              autoCapitalize="none"
              autoCorrect={false}
              editable={llmSettingsEnabled}
              style={styles.input}
              placeholder="OPENAI_API_KEY"
              placeholderTextColor="#7d93aa"
            />

            <Text style={styles.fieldLabel}>API Token</Text>
            <TextInput
              value={llmPatch.llm_api_key}
              onChangeText={(value) => updateLlmPatch({ llm_api_key: value })}
              autoCapitalize="none"
              autoCorrect={false}
              editable={llmSettingsEnabled}
              secureTextEntry
              style={styles.input}
              placeholder={llmConfig?.api_key_present ? "Token is already configured" : "Optional"}
              placeholderTextColor="#7d93aa"
            />

            <Text style={styles.fieldLabel}>Use For</Text>
            <View style={styles.optionGrid}>
              {LLM_USE_FOR_OPTIONS.map((option) => (
                <Pressable
                  key={option.value}
                  style={[
                    styles.optionButton,
                    llmPatch.llm_use_for === option.value ? styles.optionButtonSelected : null,
                  ]}
                  disabled={!llmSettingsEnabled}
                  onPress={() => updateLlmPatch({ llm_use_for: option.value })}
                >
                  <Text style={styles.optionButtonText}>{option.label}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Dry-Run Test Prompt</Text>
            <TextInput
              value={llmPrompt}
              onChangeText={setLlmPrompt}
              autoCapitalize="sentences"
              autoCorrect={false}
              editable={llmSettingsEnabled}
              style={[styles.input, styles.multiInput]}
              multiline
              placeholder="Ask the selected provider to explain current risk."
              placeholderTextColor="#7d93aa"
            />
          </View>
          <View style={styles.buttonRow}>
            <Pressable style={styles.button} onPress={() => saveLlmSettings()}>
              <Text style={styles.buttonText}>Save LLM Settings</Text>
            </Pressable>
            <Pressable
              style={[
                styles.button,
                styles.secondaryButton,
                llmSettingsEnabled ? null : styles.disabledButton,
              ]}
              disabled={!llmSettingsEnabled}
              onPress={() => runLlmDryRun()}
            >
              <Text style={styles.buttonText}>Prepare Test</Text>
            </Pressable>
          </View>
          <StatRow label="Current Provider" value={llmConfig?.provider_label || "-"} />
          <StatRow label="Token" value={llmConfig?.api_key_present ? "Configured" : "Missing"} />
          {llmResult ? (
            <Text style={styles.terminalOutput}>{JSON.stringify(llmResult, null, 2)}</Text>
          ) : null}
        </Card>

        <Card title="Config File" tone={configPersistenceToneInfo}>
          <StatRow label="State" value={formatConfigPersistenceState(configPersistenceInfo)} />
          <StatRow label="Path" value={configPersistenceInfo?.path || "-"} />
          <StatRow label="File" value={configPersistenceInfo?.exists ? "Exists" : "Missing"} />
          <StatRow label="Last Saved" value={formatTimestamp(configPersistenceInfo?.last_saved_at || configPersistenceInfo?.saved_at)} />
          <StatRow label="Last Loaded" value={formatTimestamp(configPersistenceInfo?.last_loaded_at || configPersistenceInfo?.loaded_at)} />
          <StatRow label="Modified" value={formatTimestamp(configPersistenceInfo?.modified_at)} />
          <Text style={styles.message}>
            Runtime changes are not durable until Save File completes.
          </Text>
          <View style={styles.buttonRow}>
            <Pressable style={[styles.button, styles.secondaryButton]} onPress={() => refreshConfigPersistence()}>
              <Text style={styles.buttonText}>Refresh Status</Text>
            </Pressable>
            <Pressable style={styles.button} onPress={() => saveConfigFile()}>
              <Text style={styles.buttonText}>Save File</Text>
            </Pressable>
            <Pressable style={[styles.button, styles.secondaryButton]} onPress={() => loadConfigFile()}>
              <Text style={styles.buttonText}>Load File</Text>
            </Pressable>
          </View>
        </Card>

        <Card title="Terminal">
          <Text style={styles.message}>
            Controlled service commands only. This does not run operating-system shell commands on the backend.
          </Text>
          <Text style={styles.fieldLabel}>Command</Text>
          <TextInput
            value={terminalCommand}
            onChangeText={setTerminalCommand}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
            placeholder="status, start 1, stop, config get, llm providers"
            placeholderTextColor="#7d93aa"
          />
          <View style={styles.buttonRow}>
            <Pressable style={styles.button} onPress={() => runTerminalCommand()}>
              <Text style={styles.buttonText}>Run Command</Text>
            </Pressable>
            <Pressable style={[styles.button, styles.secondaryButton]} onPress={() => runTerminalCommand("help")}>
              <Text style={styles.buttonText}>Help</Text>
            </Pressable>
          </View>
          {terminalHistory.length ? (
            terminalHistory.map((entry, index) => (
              <View key={`${entry.created_at || index}-${entry.command || "command"}`} style={styles.terminalRow}>
                <Text style={styles.logMeta}>
                  {entry.accepted ? "OK" : "FAILED"} · {entry.command || ""}
                </Text>
                <Text style={styles.terminalOutput}>{entry.output || ""}</Text>
              </View>
            ))
          ) : (
            <Text style={styles.message}>No terminal commands run yet.</Text>
          )}
        </Card>

        <Card title="Backtest" tone={backtestTone}>
          <StatRow label="Session" value={backtest.session_id || "-"} />
          <StatRow label="Runs / Errors" value={`${formatNumber(backtest.run_count)} / ${formatNumber(backtest.error_count)}`} />
          <StatRow label="Updated" value={formatTimestamp(backtest.updated_at || backtest.completed_at)} />
          <StatRow
            label="Top Run"
            value={
              topRun
                ? `${topRun.symbol || "-"} @ ${topRun.interval || "-"} (${formatNumber(topRun.roi_percent)}%)`
                : "-"
            }
          />
          <Text style={styles.message}>{backtest.status_message || "No backtest submitted yet."}</Text>
          <View style={styles.buttonRow}>
            <Pressable style={styles.button} onPress={() => runBacktest()}>
              <Text style={styles.buttonText}>Run Backtest</Text>
            </Pressable>
          </View>
        </Card>

        <Card title="Recent Logs">
          {logs.length ? (
            logs.map((entry, index) => (
              <View key={`${entry.sequence_id || index}`} style={styles.logRow}>
                <Text style={styles.logMeta}>
                  {(entry.level || "info").toUpperCase()} · {entry.source || "service"} · {formatTimestamp(entry.created_at)}
                </Text>
                <Text style={styles.logMessage}>{entry.message || ""}</Text>
              </View>
            ))
          ) : (
            <Text style={styles.message}>No logs returned yet.</Text>
          )}
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#07111f",
  },
  scroll: {
    paddingHorizontal: 18,
    paddingVertical: 20,
    gap: 16,
  },
  eyebrow: {
    color: "#57c6ff",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  title: {
    color: "#f2f5f9",
    fontSize: 30,
    fontWeight: "800",
    marginTop: 6,
  },
  lede: {
    color: "#9db2c7",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
    marginBottom: 2,
  },
  card: {
    backgroundColor: "#0b1727",
    borderRadius: 20,
    padding: 18,
    borderWidth: 1,
    borderColor: "rgba(111, 171, 255, 0.18)",
    gap: 10,
  },
  cardHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  cardTitle: {
    color: "#f2f5f9",
    fontSize: 18,
    fontWeight: "700",
  },
  pill: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  pillText: {
    color: "#dff5ff",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  pill_ok: {
    backgroundColor: "rgba(45, 212, 191, 0.18)",
  },
  pill_error: {
    backgroundColor: "rgba(251, 113, 133, 0.18)",
  },
  pill_warning: {
    backgroundColor: "rgba(245, 158, 11, 0.2)",
  },
  pill_muted: {
    backgroundColor: "rgba(255, 255, 255, 0.08)",
  },
  fieldLabel: {
    color: "#9db2c7",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 4,
  },
  input: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.08)",
    backgroundColor: "rgba(2, 10, 19, 0.74)",
    color: "#f2f5f9",
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
  },
  multiInput: {
    minHeight: 86,
    textAlignVertical: "top",
  },
  optionGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  optionButton: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.1)",
    backgroundColor: "rgba(2, 10, 19, 0.54)",
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  optionButtonSelected: {
    borderColor: "#57c6ff",
    backgroundColor: "rgba(15, 125, 222, 0.32)",
  },
  optionButtonText: {
    color: "#f2f5f9",
    fontSize: 12,
    fontWeight: "700",
  },
  fadeSection: {
    gap: 10,
  },
  fadeSectionDisabled: {
    opacity: 0.38,
  },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    paddingVertical: 8,
  },
  switchTrack: {
    width: 48,
    height: 26,
    borderRadius: 999,
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    padding: 3,
  },
  switchTrackOn: {
    backgroundColor: "rgba(45, 212, 191, 0.38)",
  },
  switchKnob: {
    width: 20,
    height: 20,
    borderRadius: 999,
    backgroundColor: "#9db2c7",
  },
  switchKnobOn: {
    transform: [{ translateX: 22 }],
    backgroundColor: "#dff5ff",
  },
  buttonRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 6,
  },
  button: {
    backgroundColor: "#0f7dde",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 14,
  },
  secondaryButton: {
    backgroundColor: "rgba(255, 255, 255, 0.1)",
  },
  disabledButton: {
    opacity: 0.45,
  },
  buttonText: {
    color: "#ffffff",
    fontWeight: "700",
  },
  statRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 16,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.05)",
  },
  statLabel: {
    color: "#9db2c7",
    fontSize: 13,
    flex: 1,
  },
  statValue: {
    color: "#f2f5f9",
    fontSize: 13,
    fontWeight: "700",
    flex: 1,
    textAlign: "right",
  },
  message: {
    color: "#9db2c7",
    fontSize: 13,
    lineHeight: 19,
    marginTop: 4,
  },
  attentionItem: {
    color: "#ffdca8",
    fontSize: 12,
    lineHeight: 18,
    backgroundColor: "rgba(245, 158, 11, 0.08)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.18)",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  loader: {
    marginTop: 6,
  },
  logRow: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255, 255, 255, 0.05)",
  },
  logMeta: {
    color: "#9db2c7",
    fontSize: 12,
    marginBottom: 4,
  },
  logMessage: {
    color: "#f2f5f9",
    fontSize: 13,
    lineHeight: 19,
  },
  terminalRow: {
    backgroundColor: "rgba(2, 10, 19, 0.58)",
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.06)",
  },
  terminalOutput: {
    color: "#d7f7ff",
    fontFamily: "monospace",
    fontSize: 12,
    lineHeight: 17,
  },
});
