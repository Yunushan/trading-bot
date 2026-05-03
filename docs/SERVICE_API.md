# Trading Bot Service API Guide

This document is the main operator/developer reference for the headless service layer in `Languages/Python/app/service/` and its canonical product launcher in `apps/service-api/`.

Use this guide for:

- standalone API startup
- bearer-token protection
- built-in web dashboard access
- desktop-hosted API mode
- Docker-backed service runs
- current endpoint coverage

## What the service layer is

The service layer is the backend boundary for:

- the standalone FastAPI process
- the thin browser dashboard at `/ui/`
- the desktop-embedded API host
- future web and mobile clients

It is intentionally separate from the PyQt desktop GUI. Docker packages this backend only, not the desktop app.

Standalone service start/stop currently manages a service lifecycle heartbeat only.
It does not launch trading strategy loops, subscribe to market-data loops for live
execution, or submit/cancel exchange orders. Use desktop-hosted API mode when
browser clients need to observe or control the real desktop-owned live/demo
trading runtime. Service-owned backtests are implemented separately and do run
inside the backend process.

## Dependency sets

From `Languages/Python/`:

```bash
cd Languages/Python
```

Install the service-focused dependency set:

```bash
pip install -r requirements.service.txt
```

For local service API development and HTTP contract tests, use the full editable
developer surface instead:

```bash
python -m pip install -e ".[desktop,service,dev]"
python tools/run_service_tests.py
python tools/run_service_tests.py --check-list
python tools/run_service_tests.py --check-docs
```

That `dev` extra provides the FastAPI `TestClient` transport dependency used by
the route-level contract tests. The focused service test runner covers HTTP
contracts, config/runtime persistence, operational health, lifecycle controls,
desktop integration boundaries, and background-hosted backtest HTTP routes.

Focused service test map:

| Module | Use when checking |
| --- | --- |
| `tests.test_service_api_http_contract` | HTTP route contracts, auth behavior, SSE auth, and runtime/dashboard responses |
| `tests.test_service_schema_contracts` | service response schema builders, payload normalization, and secret redaction contracts |
| `tests.test_service_config_runtime` | service config validation and durable config persistence |
| `tests.test_service_operational_runtime` | operational health snapshots, connector incidents, JSONL rotation, and redaction |
| `tests.test_service_lifecycle_runtime` | lifecycle control, control-plane descriptors, runtime samples, and live preflight gates |
| `tests.test_service_client_integration` | desktop service client selection and service terminal/LLM commands |
| `tests.test_service_background_host_integration` | embedded background host and background-hosted backtest API flows |

If you want the fuller backend environment used by Docker and service-owned backtest workloads:

```bash
pip install -r requirements.backend.txt
```

## Run the standalone API

Basic local run from the repository root:

```bash
python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

Deprecated compatibility launch from `Languages/Python/`:

```bash
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

Expose it to the local network:

```bash
BOT_SERVICE_API_TOKEN=your-secret-token python apps/service-api/main.py --serve --host 0.0.0.0 --port 8000
```

Non-loopback host bindings such as `0.0.0.0` require a bearer token.

### Standalone lifecycle scope

The standalone API exposes `/api/v1/control/start` and `/api/v1/control/stop`
for lifecycle orchestration, but the current local executor is intentionally
limited to a heartbeat session. A successful standalone start response means the
service process is alive and tracking lifecycle state; it does not mean that
trading engines, strategy loops, market-data streams, or exchange order execution
started.

Use the desktop-hosted API mode below for desktop-owned live/demo trading state
until a dedicated headless trading executor is implemented.

### Runtime control-plane descriptor

`GET /api/v1/runtime` and `GET /api/v1/dashboard` include
`runtime.control_plane`. Clients should use this descriptor to decide how to
label lifecycle controls and whether a start/stop request can actually reach a
trading runtime owner.

The checked-in sample response at
`apps/service-api/contracts/runtime.sample.json` documents the standalone API
runtime descriptor shape and the default heartbeat-only control plane.

Stable fields:

- `mode`: control adapter mode, such as `intent-only`,
  `local-service-executor`, `delegated-dispatch`, or `desktop-gui-dispatch`.
- `owner`: process or adapter that owns lifecycle control, such as
  `service-runtime`, `service-process`, `external-control-adapter`, or
  `desktop-gui`.
- `start_supported` and `stop_supported`: whether the current control adapter
  accepts lifecycle requests.
- `execution_scope`: the runtime scope affected by accepted requests.
  Known values include `intent-only`, `service-lifecycle-heartbeat`,
  `delegated-runtime`, and `desktop-trading-runtime`.
- `trading_execution_supported`: whether the owner reports support for
  strategy loops, market-data loops, and exchange order execution.
- `notes`: operator-facing details about the mode.

Mode meanings:

- `intent-only` / `execution_scope: intent-only`: lifecycle requests are
  recorded as service intent until an execution adapter is attached.
- `local-service-executor` / `execution_scope: service-lifecycle-heartbeat`:
  standalone service start/stop maintains a lifecycle heartbeat only. It does
  not run strategies, market-data loops, or exchange orders.
- `delegated-dispatch` / `execution_scope: delegated-runtime`: the service
  forwards control to an attached adapter. Treat trading execution support as
  unavailable unless `trading_execution_supported` is `true`.
- `desktop-gui-dispatch` / `execution_scope: desktop-trading-runtime`:
  lifecycle requests are queued into the desktop GUI, where the desktop-owned
  live/demo runtime owns trading execution.

Preflight and control-plane state answer different questions. Preflight says
whether live start/order safety inputs are fresh enough; `runtime.control_plane`
says which runtime owner, if any, will receive lifecycle start/stop requests.

## Bearer token

CLI form:

```bash
python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000 --api-token your-secret-token
```

Environment-variable form:

```bash
BOT_SERVICE_API_TOKEN=your-secret-token python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

PowerShell:

```powershell
$env:BOT_SERVICE_API_TOKEN='your-secret-token'
python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

When bearer auth is enabled:

- REST requests use `Authorization: Bearer ...`
- the browser dashboard stores the token in tab-scoped session storage, not long-lived local storage
- dashboard live updates use a `fetch`-based event stream with `Authorization: Bearer ...`
- the SSE endpoint still accepts `?token=...` for raw `EventSource` clients, but dashboard code avoids putting bearer tokens in stream URLs

## Built-in web dashboard

The service serves a thin same-origin dashboard at:

```text
http://127.0.0.1:8000/ui/
```

Current dashboard capabilities:

- runtime and status inspection
- account and portfolio snapshots
- log viewing
- editable top-level runtime config patching
- explicit service config file save/load status
- lifecycle heartbeat start/stop requests in standalone mode
- execution-session visibility
- service-owned backtest visibility and control
- live dashboard refresh over Server-Sent Events

Operational preflight blocks and warnings are handled with the
[Operational Preflight Runbook](OPERATIONAL_PREFLIGHT_RUNBOOK.md).

## Desktop-hosted API mode

If you want browser clients to follow the real desktop-owned runtime instead of a separate standalone service process, use the embedded desktop host.

You can enable this either:

- from the desktop GUI via the `Desktop Service API` controls
- or through environment variables before launching the desktop app wrapper

PowerShell example:

```powershell
$env:BOT_ENABLE_DESKTOP_SERVICE_API='1'
$env:BOT_DESKTOP_SERVICE_API_HOST='127.0.0.1'
$env:BOT_DESKTOP_SERVICE_API_PORT='8000'
$env:BOT_SERVICE_API_TOKEN='your-secret-token'
python apps/desktop-pyqt/main.py
```

Then open:

```text
http://127.0.0.1:8000/ui/
```

This mode serves the API against the same embedded service object the desktop GUI mirrors, so browser clients can observe live desktop-owned runtime, account, portfolio, and log state.

## Current endpoint coverage

Canonical routes now live under `/api/v1/*`.
The older `/api/*` paths remain available as compatibility aliases during migration,
but they are hidden from the OpenAPI schema and should not be used for new clients.
`apps/service-api/contracts/service-api-contract.json` is generated from
`app.service.api_contract` and includes the route suffix map plus the
dashboard and mobile required route-name lists used by client contract tests.
Validate the checked-in contract artifacts with
`python Languages/Python/tools/check_service_api_contracts.py`. Add `--write`
to refresh the generated route contract before committing intentional route
metadata changes.

Core routes:

- `GET /health`
- `GET /api/v1/dashboard`
- `GET /api/v1/runtime`
- `GET /api/v1/runtime/operational-preflight`
- `GET /api/v1/status`
- `GET /api/v1/config`
- `GET /api/v1/config-summary`
- `GET /api/v1/config/persistence`
- `GET /api/v1/account`
- `GET /api/v1/portfolio`
- `GET /api/v1/logs`
- `GET /api/v1/execution`
- `GET /api/v1/backtest`

Streaming:

- `GET /api/v1/stream/dashboard`

The dashboard stream accepts `interval_ms`, `log_limit`, and `incident_limit`
query parameters for refresh cadence and payload sizing. It also accepts
`max_events` for bounded diagnostics and contract tests; omit `max_events` for
normal continuous dashboard streams.

Write/control routes:

- `POST /api/v1/control/start`
- `POST /api/v1/control/stop`
- `PATCH /api/v1/config`
- `POST /api/v1/config/save`
- `POST /api/v1/config/load`
- `PUT /api/v1/runtime/state`
- `POST /api/v1/backtest/run`
- `POST /api/v1/backtest/stop`

## Service config persistence

`PUT /api/v1/config`, `PATCH /api/v1/config`, terminal `config set`, and
`--config-patch` update only the in-memory service runtime config. They do not
write a file unless you explicitly save.

The durable service config file defaults to `~/.trading-bot/service-config.json`.
Override it with `BOT_SERVICE_CONFIG_PATH`, `--config-path`, or the optional
`path` field on the save/load API request body. The file contains the full
validated runtime config and can include API credentials, so store it with the
same care as any other secret-bearing config file.

- `GET /api/v1/config/persistence` returns the configured file path, whether it
  exists, last load/save timestamps, and whether runtime changes are dirty.
- `POST /api/v1/config/save` writes the current validated runtime config to the
  configured file.
- `POST /api/v1/config/load` validates the configured file and replaces the
  current runtime config only if validation succeeds.

## Docker path

The optional container path is documented in [docker/README.md](../docker/README.md).

Quick start from the repository root:

```bash
docker compose -f docker/compose.yaml up --build
```

That packages:

- the FastAPI backend
- the thin same-origin dashboard
- service-owned backtest support

It does not package the PyQt desktop GUI.

## Mobile and web clients

Current client directions:

- thin browser dashboard in `apps/web-dashboard/`
- Expo-based Android/iOS thin client scaffold in `apps/mobile-client/`

These clients are intended to talk to the backend API only. Exchange or broker secrets should stay on the backend.
