# Trading Bot Mobile Client

Thin Expo-based native Android/iOS client over the existing Trading Bot service API.

## Scope

This client is intentionally small:

- connect to the headless service API
- inspect runtime, status, operational preflight, backtest state, and recent logs
- request service lifecycle heartbeat start/stop
- trigger the extracted service-owned backtest runner
- select and save LLM provider settings for OpenAI/ChatGPT, Claude, Gemini, DeepSeek, Grok, Qwen, or a local/private OpenAI-compatible endpoint
- inspect config persistence status and trigger service config file save/load
- run controlled service terminal commands such as `status`, `start 1`, `stop`, `config get`, and `llm providers`

It does **not** run trading logic locally, and it should never store exchange or broker credentials on the phone.
The terminal panel does not execute operating-system shell commands on the backend.

## Install

From this folder:

```bash
npm install
```

Start the Expo dev server:

```bash
npm run start
```

Open directly on Android or iOS:

```bash
npm run android
npm run ios
```

Optional native cloud/local build profiles are defined in:

```text
eas.json
```

## Connect to the backend

If you run this on a physical phone, do not use `127.0.0.1` unless the backend is also on the phone.
Point the app at the LAN IP of the machine running:

```bash
BOT_SERVICE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  python ../service-api/main.py --serve --host 0.0.0.0 --port 8000
```

Example:

```text
http://192.168.1.25:8000
```

Enter the same bearer token used by `BOT_SERVICE_API_TOKEN` in the mobile app connection settings.

## Preflight Safety

The mobile client reads the same operational preflight payload as the web
dashboard. The Preflight card shows Start, Orders, Mode, Critical, Ages, and
stale-input attention rows from the named `operational_preflight` service route
resolved by `service-contract.js` (`/api/v1/runtime/operational-preflight`).

Request Lifecycle Start is disabled only when the backend preflight reports
`start.allowed === false`. Warning, demo/test, and disabled-gate states remain
clickable so the backend remains the source of truth for lifecycle requests.

The Lifecycle Controls card also interprets the backend control-plane metadata:
desktop-forwarded mode means the desktop GUI owns live/demo execution,
heartbeat-only mode means standalone service start/stop only keeps a lifecycle
heartbeat alive, and intent-only mode means requests are recorded until an
execution adapter is attached.

For blocked-state triage and recovery steps, use the operator runbook:
[docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md](../../docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md).

## Config Persistence

LLM and runtime config edits are runtime-only until the service config file is
saved. The Config File card reads `GET /api/v1/config/persistence`, Save File
calls `POST /api/v1/config/save`, and Load File calls
`POST /api/v1/config/load`.

Load File replaces the current runtime config with the validated config from the
service-owned file path shown in the card.

## Notes

- This is a thin-client scaffold, not a full production mobile app.
- It shares the same backend contract as the web dashboard.
- Future work should add richer config editing, positions, and chart views without moving trading execution onto the device.
