# Operator Runbook

This runbook is the short checklist for running the project safely.

## Before Live Trading

1. Run the app in `Demo/Testnet` first with the same symbols, intervals, indicators, leverage, margin mode, and position percent you plan to use live.
2. Confirm `Preflight` is `ok` in the desktop app or service dashboard.
3. Confirm the exchange connector is `Trading Supported`, not only selected in the UI.
4. Confirm order audit logging is writable.
5. Keep `live_allow_auto_bump_to_min_order` off unless you intentionally accept exchange-minimum auto-bumped orders.
6. Confirm stop-loss and take-profit behavior is deterministic strategy/runtime behavior, not LLM output.
7. Set `live_trading_max_session_orders` or `BOT_LIVE_MAX_SESSION_ORDERS` low for first live sessions.
8. Use small live size first and verify order, close, reduce-only, and emergency-close behavior.

## LLM Usage

LLM assistance is advisory-only. It can explain risk, summarize state, or review signals, but it must not directly submit orders, override risk controls, or claim that a trade was executed.
The app blocks LLM responses that contain direct order-action output or risk-control override claims; treat a blocked response as a model/prompt issue, not as trading advice.

For local models, Ollama stores model files outside this repository, commonly:

- Windows: `%USERPROFILE%\.ollama\models`
- Linux/macOS: `~/.ollama/models`
- Custom Ollama cache: `OLLAMA_MODELS`

The project repository does not store downloaded model weights and Git should never track them.
Use the desktop LLM panel to check/download, cancel an in-progress download, or remove Ollama models after reading the shown size and storage-path warning.

## Service API Safety

Use a bearer token for any exposed or write-capable API session. These flags are development-only escape hatches and are exposed in service API metadata when active:

- `BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES`
- `BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS`
- `BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH`

If any unsafe write/config escape hatch is active, treat the service as unsafe
for normal operation.

`BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH` affects only trusted callers running on
the service host. Remote API save/load requests always use the server-configured
path and reject request-selected paths, even when this flag is active. Remote
config and terminal routes also reject credential and audit/incident-log path
fields; provision those values on the host.

These values are operational exposure limits, not unsafe bypasses:

- `BOT_SERVICE_API_MAX_REQUEST_BYTES`
- `BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE`

Review request-size and write-rate-limit values before exposing the service
beyond loopback.

Scrape authenticated production metrics from
`/api/v1/metrics/prometheus`; keep the bearer token in the monitoring platform's
secret store or credential file. Load
`docker/monitoring/prometheus-alerts.json` as a Prometheus rule file and route
critical alerts to an actively monitored channel. Confirm that unavailable,
read-error-rate, stale-snapshot, open-circuit, and unresolved-order-intent alerts
reach the operator before declaring a deployment ready. Use `X-Request-ID` from
service responses to correlate proxy and application incidents without placing
credentials or query values in logs or labels.

## Operational Readiness

The source of truth for SLOs, RTO/RPO targets, probe thresholds, and required
promotion evidence is `docs/operational-readiness-policy.json`. Run the local
regression checks before every release candidate:

```bash
python tools/check_operational_readiness.py --schema-only
python tools/run_service_sustained_probe.py --profile quick
python tools/run_operational_recovery_drill.py
python tools/run_incident_audit_continuity_drill.py
```

These checks are read-only with respect to trading and cannot submit orders.
The quick probe is not production evidence. A production promotion also
requires a passing 30-minute sustained probe against an external HTTPS service
running the exact candidate commit, a real rolling 30-day telemetry
window, config/restart recovery evidence, and incident/audit continuity
evidence from the same clean candidate commit. Convert the raw telemetry export
with `python tools/import_production_slo_evidence.py --input production-slo-telemetry.json --json`;
the importer writes no artifact unless counts, freshness, source binding, and
all SLO thresholds pass. Validate the complete evidence set with:

```bash
python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json
```

Missing evidence is a failed promotion gate, not an assumed pass. See
`docs/SERVICE_LEVEL_OBJECTIVES.md` and `docs/DISASTER_RECOVERY.md` for the
collection boundaries and operator drills.

## Release Smoke

Before packaging or tagging:

```bash
python tools/check_local_tool_versions.py --json
python tools/check_client_dependency_locks.py --json --strict
python tools/summarize_worktree_changes.py
python tools/audit_workspace_hygiene.py
python tools/audit_risky_patterns.py
python tools/verify_all.py --skip-slow
cd Languages/Python && python tools/run_python_tests.py
cd ../../apps/web-dashboard && npm test
cd ../mobile-client && npm test
```

On Windows machines with multiple Python installs, validate the intended
interpreter explicitly:

```powershell
python tools/check_local_tool_versions.py --json --skip-node --python-command "python"
```

For the service API:

```bash
python apps/service-api/main.py --healthcheck
python Languages/Python/tools/check_service_api_contracts.py
```

For a fresh contributor machine, preview the complete local setup plan first:

```bash
python tools/bootstrap_local_dev.py --dry-run
```

If the default `python` command is not the declared Python, target the install
interpreter explicitly:

```powershell
python tools/bootstrap_local_dev.py --python-command "python" --dry-run
```
