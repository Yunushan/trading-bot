const SERVICE_API_BASE_PATH = "/api/v1";
const SERVICE_API_LEGACY_BASE_PATH = "/api";
const SERVICE_API_VERSION = "1.0.0";

const SERVICE_API_ROUTE_SUFFIXES = Object.freeze({
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
  llm_local_model_status: "/llm/local-model/status",
  llm_local_model_start: "/llm/local-model/start",
  llm_local_model_pull: "/llm/local-model/pull",
  llm_local_model_delete: "/llm/local-model/delete",
  stream_dashboard: "/stream/dashboard",
});

const MOBILE_REQUIRED_ROUTE_NAMES = Object.freeze([
  "dashboard",
  "llm_providers",
  "llm_config",
  "config_persistence",
  "config_save",
  "config_load",
  "operational_preflight",
  "control_start",
  "control_stop",
  "backtest_run",
  "terminal_run",
  "llm_prompt",
]);

function serviceApiRoute(name) {
  const suffix = SERVICE_API_ROUTE_SUFFIXES[name];
  if (!suffix) {
    throw new Error(`Unknown service API route: ${name}`);
  }
  return `${SERVICE_API_BASE_PATH}${suffix}`;
}

module.exports = {
  MOBILE_REQUIRED_ROUTE_NAMES,
  SERVICE_API_BASE_PATH,
  SERVICE_API_LEGACY_BASE_PATH,
  SERVICE_API_ROUTE_SUFFIXES,
  SERVICE_API_VERSION,
  serviceApiRoute,
};
