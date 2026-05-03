# Operational Preflight Runbook

Use this runbook when the desktop app, web dashboard, mobile client, or service
API reports a blocked or warning preflight state.

The preflight exists to stop live starts and live order submission when the
backend is working from stale or incomplete operational data. Do not bypass a
blocked live preflight by repeatedly clicking Start or by disabling gates in
Live mode.

## Where to check

- Desktop: `Desktop Service API` panel, `Preflight` label, `Recheck Preflight`
  button, and the main Start button.
- Web dashboard: `Preflight` card and `Recheck Preflight`.
- Mobile client: `Preflight` card and controls card.
- Direct API: `GET /api/v1/runtime/operational-preflight`.

PowerShell example:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/runtime/operational-preflight
```

With bearer auth:

```powershell
$headers = @{ Authorization = "Bearer $env:BOT_SERVICE_API_TOKEN" }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/runtime/operational-preflight -Headers $headers
```

## Lifecycle Mode Check

Before treating an allowed preflight as permission to start live trading, check
`runtime.control_plane` from `GET /api/v1/runtime` or the dashboard snapshot.
Preflight answers whether operational inputs are fresh enough. The control-plane
descriptor answers which runtime owner receives lifecycle start/stop requests.

- Desktop Forwarded means `mode` is `desktop-gui-dispatch` or the descriptor
  otherwise points at `desktop-gui` / `desktop-trading-runtime`; the desktop GUI
  owns live/demo strategy and order execution.
- Heartbeat Only means `mode` is `local-service-executor` or
  `execution_scope` is `service-lifecycle-heartbeat`; standalone start/stop only
  maintains a lifecycle heartbeat and does not run strategies, market-data
  loops, or exchange orders.
- Intent Only means `mode` or `execution_scope` is `intent-only`; requests are
  recorded until a real execution adapter attaches.
- Check `trading_execution_supported` before assuming the owner can run
  strategy loops or submit exchange orders.

## Decision Rules

- If `state` is `blocked` or `start.allowed` is `false`, do not start live
  trading until the listed reasons are fixed.
- If `orders.allowed` is `false`, live order submission is blocked even when a
  runtime is already active. For urgent position management, use the exchange
  directly instead of assuming the bot can submit recovery orders.
- Warnings in Demo/Testnet or with a disabled gate do not block Start, but the
  reason still needs review before increasing scope or switching to Live.
- A missing idle execution heartbeat is not a live-start blocker. A stale
  running execution heartbeat is a blocker because it means the active runtime
  is not reporting freshness.

## Fields To Read First

Prioritize these fields in order:

1. `critical_stale.start` and `critical_stale.orders`: the data inputs that are
   blocking Start or order submission.
2. `start.reasons`, `orders.reasons`, and top-level `reasons`: the plain-English
   explanation.
3. `freshness.exchange_connector`, `freshness.execution`, `freshness.account`,
   and `freshness.portfolio`: each input's `stale`, `age_seconds`,
   `max_age_seconds`, `generated_at`, `state`, and `source`.
4. `mode`, `live_mode`, and each gate's `gate_enabled`: whether this is a live
   safety block, a demo warning, or an intentionally disabled gate.
5. `generated_at`: confirms the preflight result itself is fresh after a
   manual recheck.

## Triage Flow

1. Stop making new live-start attempts while `start.allowed` is `false`.
2. Use `Recheck Preflight` or call the direct API once to confirm the block is
   current.
3. Read `critical_stale.start` and `critical_stale.orders`.
4. Fix each stale input using the playbook below.
5. Recheck preflight.
6. Start only when `start.allowed` is `true`, `critical_stale.start` is empty,
   and the displayed reason is understood.

## Stale Input Playbook

### Exchange Connector

Symptoms:

- `critical_stale` lists `exchange connector`.
- `freshness.exchange_connector.stale` is `true`.
- Connector health may show rate-limit, network, auth, or venue errors.

Actions:

1. Confirm the selected connector, account type, Live vs Demo/Testnet mode, and
   API credential scope match the intended venue.
2. Check network access, IP whitelist rules, API-key permissions, and exchange
   status.
3. Refresh symbols or account data from the desktop UI, or restart the service
   if the connector snapshot does not update.
4. Review connector health and incident logs in the dashboard before starting.

### Account Snapshot

Symptoms:

- `critical_stale` lists `account`.
- `freshness.account.stale` is `true`.

Actions:

1. Refresh balance/account data from the desktop UI or restart the service
   runtime that owns the account snapshot.
2. Confirm credentials can read account state and that futures permission is
   enabled when using futures.
3. Confirm the configured account type matches the venue account.
4. Recheck preflight and verify `freshness.account.stale` is `false`.

### Portfolio Snapshot

Symptoms:

- `critical_stale` lists `portfolio`.
- `freshness.portfolio.stale` is `true`.

Actions:

1. Refresh positions from the Positions tab or dashboard.
2. Confirm the account type, position mode, and margin mode match the venue.
3. Check for API failures, exchange maintenance, or position-query rate limits.
4. Recheck preflight and verify positions or empty-position state are current.

### Execution Heartbeat

Symptoms:

- `critical_stale.start` lists `execution heartbeat`.
- `freshness.execution.stale` is `true`.
- The execution state is running, but the runner is no longer heartbeating.

Actions:

1. Stop the runtime from the desktop, web, mobile, or service control path.
2. Check runtime logs for worker errors or blocked strategy loops.
3. Restart only after the heartbeat freshness is healthy or the runtime returns
   to an idle state.
4. Recheck preflight before starting again.

## Gate Configuration

These config keys affect preflight behavior:

- `operational_live_start_gate_enabled`
- `operational_live_order_gate_enabled`
- `operational_connector_snapshot_stale_seconds`
- `operational_execution_heartbeat_stale_seconds`
- `operational_account_snapshot_stale_seconds`
- `operational_portfolio_snapshot_stale_seconds`

Treat threshold changes as risk decisions. Widening a stale threshold can hide a
real outage. Disabling live gates should be reserved for controlled test runs,
not for bypassing stale production data.

## Before Restarting Live

Confirm all of the following:

- `start.allowed` is `true`.
- `orders.allowed` is `true` or the order-blocking reason is intentional and
  understood.
- `critical_stale.start` is empty.
- Exchange connector, account, and portfolio freshness are not stale.
- Execution freshness is idle or fresh while running.
- `generated_at` is recent after the last manual recheck.
- The selected mode, account type, connector, leverage, margin mode, and
  position mode match the intended live account.
