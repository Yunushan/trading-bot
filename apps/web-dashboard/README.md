# Trading Bot Web Dashboard

Thin browser dashboard for the Trading Bot service API.

This app is served by the backend at `/ui/` and talks to the same service API
contract used by the desktop-remote and mobile thin-client paths.

## Scope

- inspect runtime, status, backtest state, config, account, portfolio, and logs
- request service lifecycle heartbeat start/stop through the service API
- edit service-owned runtime config state
- save or load the durable service config file
- trigger and stop service-owned backtests

It does not hold exchange credentials or run trading logic locally.

## Config Persistence

Patch Runtime updates the in-memory service config. Save File writes the full
validated runtime config to the backend's configured service config file, and
Load File validates that file before replacing the current runtime config.

## Auth Handling

When bearer auth is enabled, the dashboard keeps the API token in browser
session storage for the current tab/session. It does not write the token to
long-lived local storage.

Live dashboard updates use a `fetch`-based event-stream request with the
`Authorization` header. The token is not added to the stream URL.

## Preflight And Live Safety

The Preflight card mirrors backend operational live safety checks before start
and order requests.

- Start shows whether live start is allowed, blocked, or warning, plus the
  reason. A blocked Start disables Request Lifecycle Start. Warnings, demo mode, and
  disabled gates keep Request Lifecycle Start clickable because the backend can still
  accept the request.
- Orders shows whether live order submission is allowed, blocked, or warning,
  plus the reason.
- Ages lists exchange connector, execution heartbeat, account snapshot, and
  portfolio snapshot freshness as current age, max age, and fresh or stale
  state. A missing idle execution heartbeat is not a live-start blocker, but a
  stale running execution heartbeat is.
- Attention lists stale inputs and remediation hints, such as reconnecting the
  exchange, checking the execution runner heartbeat, refreshing the account
  snapshot, or refreshing the portfolio snapshot.

Use Recheck Preflight to refresh `/runtime/operational-preflight` without
waiting for the regular dashboard poll.

## Lifecycle Control Modes

The Control Plane card also interprets backend control-plane metadata.

- Desktop Forwarded means lifecycle requests are queued into the desktop GUI,
  where the live/demo runtime owns strategy and order execution.
- Heartbeat Only means standalone service start/stop only maintains a lifecycle
  heartbeat. It does not run strategies, market-data loops, or exchange orders.
- Intent Only means lifecycle requests are recorded until an execution adapter
  attaches.
- Trading Execution shows whether the attached owner reports strategy and order
  execution support.

For blocked-state triage and recovery steps, use the operator runbook:
[docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md](../../docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md).

## Run

This dashboard is normally served by the backend:

```bash
python ../service-api/main.py --serve --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/ui/
```
