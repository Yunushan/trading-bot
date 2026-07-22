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
| `tests.test_service_api_host_contract` | background host validation and startup configuration contracts |
| `tests.test_service_product_main` | canonical service CLI commands, remote requests, validation, and error boundaries |

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
BOT_SERVICE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  python apps/service-api/main.py --serve --host 0.0.0.0 --port 8000
```

Non-loopback host bindings such as `0.0.0.0` require a bearer token with at
least 32 characters. Generate it with `secrets.token_urlsafe(32)` as shown
above; do not reuse an exchange key or a short human-memorable password.

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

Secret-file form for container/orchestrator deployments:

```bash
BOT_SERVICE_API_TOKEN_FILE=/run/secrets/service_api_token \
  python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

The token resolution order is explicit CLI token, `BOT_SERVICE_API_TOKEN`, then
`BOT_SERVICE_API_TOKEN_FILE`. The file is limited to 4 KiB and must not be
checked into source control.

PowerShell:

```powershell
$env:BOT_SERVICE_API_TOKEN='your-secret-token'
python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

When bearer auth is enabled:

- REST requests use `Authorization: Bearer ...`
- the browser dashboard stores the token in tab-scoped session storage, not long-lived local storage
- dashboard live updates use a `fetch`-based event stream with `Authorization: Bearer ...`
- the SSE endpoint does not accept bearer tokens in query strings; use the
  `Authorization` header or polling from clients that cannot set stream headers
- write endpoints require a bearer token in both standalone and desktop-hosted
  API modes. If no token is configured, read routes stay available but
  mutation/control routes return `403`. `BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES=1`
  is a local development escape hatch only; startup rejects it for non-loopback
  bindings.
- `/health`, `/api/v1/dashboard`, and service API metadata include
  `service_api.unsafe_flags_active` plus `service_api.security.warnings` when
  unsafe write/config escape hatches are active.
- `/livez` is a process liveness probe. `/readyz` verifies that the runtime
  descriptor can be built and returns `503` when the service is not ready to
  accept work. Container health checks use `/readyz`.

## Non-loopback TLS policy

The service refuses a non-loopback host unless it has a bearer token of at
least 32 characters and one of the following deployment protections:

- Direct TLS: configure both `BOT_SERVICE_API_TLS_CERTFILE` and
  `BOT_SERVICE_API_TLS_KEYFILE`. The service passes these paths to Uvicorn and
  serves HTTPS itself.
- TLS-terminating reverse proxy: set `BOT_SERVICE_API_TRUST_PROXY_TLS=1` only
  when the proxy enforces HTTPS and the service network is not directly
  reachable by untrusted clients.
- Host-loopback container proxy: set `BOT_SERVICE_API_TRUST_LOOPBACK_PROXY=1`
  only when Docker or another proxy publishes the container port exclusively
  on `127.0.0.1` or `::1`. The checked-in Docker Compose file uses this mode
  with `127.0.0.1:8000:8000`; do not reuse it for a LAN or public port mapping.

For direct TLS, keep the certificate and private key outside the repository.
The private-key path must resolve to a regular file and, on POSIX, may not grant
any group or other permissions. Do not set either trusted-proxy variable merely
to bypass this check.

Request safety limits:

- `BOT_SERVICE_API_MAX_REQUEST_BYTES` caps incoming request bodies. The default
  is 1 MiB. Oversized requests return `413`.
- `BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE` optionally rate-limits write
  methods per client. The quota is shared across `POST`, `PUT`, `PATCH`, and
  `DELETE`. Loopback hosts may leave it unset or set it to `0` for no
  local rate limit. Non-loopback hosts default to 60 writes per minute and
  enforce a minimum of one write per minute even when the value is set to `0`.
  Positive limits return `429` with `Retry-After` once exceeded.
- `BOT_SERVICE_API_WRITE_RATE_LIMIT_MAX_CLIENTS` bounds the in-memory client
  tracking table used by a positive write limit. It defaults to 10,000 clients;
  expired one-minute windows are pruned before a new client is admitted. A full
  table returns `429` instead of allowing unbounded memory growth.
- Both limits are reported in `service_api.limits` metadata so browser/mobile
  clients can display the active policy.
- Health, readiness, liveness, and `/api/...` responses include `Cache-Control:
  no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`, and
  `X-Content-Type-Options: nosniff`. This keeps account, strategy, and runtime
  data out of shared proxy/browser caches without disabling normal caching for
  static dashboard assets.

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
For live-trading and LLM safety checks, use the
[Operator Runbook](OPERATOR_RUNBOOK.md).

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
- `GET /livez`
- `GET /readyz`
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
`path` field on the save/load API request body. Explicit save/load API paths are
blocked outside the safe config directory unless the trusted local caller sends
`allow_unsafe_path: true` or sets `BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH=1`.
Save responses include `contains_secrets`, `secret_fields`, and
`secret_storage_warning` metadata so clients can warn before persisting
plain-JSON credentials. Inline secret values are redacted from saved config
files by default; set `BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS=1` only when you
explicitly want plain-JSON secret persistence.

When an operating-system credential store is available, service secrets use the
native platform API (Windows Credential Manager, macOS Keychain, or Linux Secret
Service). The macOS integration calls the Keychain framework directly, so secret
values are not placed in a `security` command-line argument.

- `GET /api/v1/config/persistence` returns the configured file path, whether it
  exists, last load/save timestamps, and whether runtime changes are dirty.
- `POST /api/v1/config/save` writes the current validated runtime config to the
  configured file.
- `POST /api/v1/config/load` validates the configured file and replaces the
  current runtime config only if validation succeeds.

## LLM provider and local model notes

LLM calls are advisory-only. The API returns `execution_policy.advisory_only`
and request builders prepend an execution-boundary instruction; strategy,
risk, take-profit, stop-loss, and exchange-order execution remain owned by the
deterministic runtime.
LLM responses are also inspected before returning to the app. Output that tries
to submit orders, claims execution, or overrides risk controls is marked
`ok: false` with `output_policy.blocked: true`.

Local Ollama models are downloaded by Ollama into its own model cache, commonly
`~/.ollama/models` on Linux/macOS and `%USERPROFILE%\.ollama\models` on Windows.
They are outside this repository and are not part of Git. The desktop LLM panel
can ask Ollama to download or remove a selected local model after an explicit
operator confirmation. Add provider model overrides with
`BOT_LLM_EXTRA_MODELS_<PROVIDER>` or a JSON catalog pointed to by
`BOT_LLM_MODEL_CATALOG_PATH`.

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
