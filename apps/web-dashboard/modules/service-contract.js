export const SERVICE_API_BASE_PATH = "/api/v1";
export const SERVICE_API_LEGACY_BASE_PATH = "/api";
export const SERVICE_API_VERSION = "1.0.0";

export const SERVICE_API_ROUTE_SUFFIXES = Object.freeze({
  runtime: "/runtime",
  dashboard: "/dashboard",
  status: "/status",
  execution: "/execution",
  backtest: "/backtest",
  config_summary: "/config-summary",
  config: "/config",
  config_persistence: "/config/persistence",
  config_save: "/config/save",
  config_load: "/config/load",
  runtime_state: "/runtime/state",
  operational_preflight: "/runtime/operational-preflight",
  control_start: "/control/start",
  control_stop: "/control/stop",
  control_start_failed: "/control/start-failed",
  connector_order_circuit_breaker: "/runtime/connector-order-circuit-breaker",
  connector_order_circuit_breaker_reset: "/runtime/connector-order-circuit-breaker/reset",
  connector_order_circuit_incidents: "/runtime/connector-order-circuit-breaker/incidents",
  backtest_run: "/backtest/run",
  backtest_stop: "/backtest/stop",
  account: "/account",
  portfolio: "/portfolio",
  exchange_connector: "/exchange/connector",
  logs: "/logs",
  terminal_run: "/terminal/run",
  llm_providers: "/llm/providers",
  llm_config: "/llm/config",
  llm_prompt: "/llm/prompt",
  stream_dashboard: "/stream/dashboard",
});

export const DASHBOARD_REQUIRED_ROUTE_NAMES = Object.freeze([
  "dashboard",
  "status",
  "stream_dashboard",
  "control_start",
  "control_stop",
  "runtime_state",
  "operational_preflight",
  "connector_order_circuit_breaker_reset",
  "config",
  "config_persistence",
  "config_save",
  "config_load",
  "backtest_run",
  "backtest_stop",
]);

export function serviceApiRoute(name) {
  const suffix = SERVICE_API_ROUTE_SUFFIXES[name];
  if (!suffix) {
    throw new Error(`Unknown service API route: ${name}`);
  }
  return `${SERVICE_API_BASE_PATH}${suffix}`;
}
