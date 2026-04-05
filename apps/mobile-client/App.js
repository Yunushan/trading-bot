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

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_PATH = "/api/v1";

function apiPath(path) {
  return `${API_BASE_PATH}/${String(path || "").replace(/^\/+/, "")}`;
}

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

export default function App() {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("Connect to a running service API.");
  const [health, setHealth] = useState(null);
  const [dashboard, setDashboard] = useState(null);

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
      const nextDashboard = await requestJson(`${apiPath("dashboard")}?log_limit=10`);
      setDashboard(nextDashboard);
      setMessage(`Connected to ${normalizeBaseUrl(baseUrl)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  };

  const sendLifecycle = async (action) => {
    setLoading(true);
    try {
      const path = action === "start" ? apiPath("control/start") : apiPath("control/stop");
      const body =
        action === "start"
          ? { requested_job_count: 1, source: "mobile-client" }
          : { close_positions: false, source: "mobile-client" };
      const result = await requestJson(path, { method: "POST", body });
      setMessage(result.status_message || `${action} request sent.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      setLoading(false);
    }
  };

  const runBacktest = async () => {
    setLoading(true);
    try {
      const result = await requestJson(apiPath("backtest/run"), {
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

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.eyebrow}>Thin Mobile Client</Text>
        <Text style={styles.title}>Trading Bot Mobile</Text>
        <Text style={styles.lede}>
          Android and iOS starter over the existing service API. This client is intentionally thin:
          inspect runtime, request lifecycle changes, and trigger the extracted backtest runner.
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

        <Card title="Controls">
          <View style={styles.buttonRow}>
            <Pressable style={styles.button} onPress={() => sendLifecycle("start")}>
              <Text style={styles.buttonText}>Request Start</Text>
            </Pressable>
            <Pressable style={[styles.button, styles.secondaryButton]} onPress={() => sendLifecycle("stop")}>
              <Text style={styles.buttonText}>Request Stop</Text>
            </Pressable>
          </View>
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
});
