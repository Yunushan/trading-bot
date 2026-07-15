# Trading Bot Service API

Canonical product launcher for the headless FastAPI service.

The service implementation still lives in `Languages/Python/app/service/` while
the repo finishes its product-first layout migration. This folder is the stable
top-level app boundary for backend packaging and operator-facing launch docs.

## Run

From the repository root with the Python environment already activated:

```bash
python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

For service API development and route-level contract tests, install the full
Python developer surface from `Languages/Python/`:

```bash
python -m pip install -e ".[desktop,service,dev]"
python tools/run_service_tests.py
python tools/run_service_tests.py --check-list
python tools/run_service_tests.py --check-docs
```

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
| `tests.test_service_product_main` | canonical service CLI commands, remote requests, validation, and error boundaries |

Deprecated compatibility launchers still work:

```bash
cd Languages/Python
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

Run controlled CLI/terminal commands locally:

```bash
python apps/service-api/main.py --terminal "status"
python apps/service-api/main.py --terminal "config set mode=Demo/Testnet theme=Blue"
python apps/service-api/main.py --terminal "config save"
python apps/service-api/main.py --terminal "llm providers"
```

Control an already running service or desktop API host:

```bash
python apps/service-api/main.py --base-url http://127.0.0.1:8000 --terminal "status"
```

The terminal command surface is intentionally allowlisted and does not execute
raw operating-system shell commands.

Runtime config changes are transient until explicitly persisted. Use
`--config-path` to choose the durable JSON file, `--load-config` to load it at
startup, `--save-config` or terminal `config save [path]` to write the current
runtime config, and terminal `config load [path]` to validate and load it.
HTTP write/control routes require a bearer token unless the local development
escape hatch `BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES=1` is set. Service
config saves redact inline secret values by default; opt into plain-JSON secret
persistence only with `BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS=1`.

## Contract Samples

The service keeps sample response payloads in `contracts/` for clients that
consume the HTTP API directly.

- `contracts/service-api-contract.json` documents canonical `/api/v1/*` route
  names, compatibility `/api/*` aliases, HTTP methods, and the required route
  lists used by the web dashboard and mobile client contract tests.
- `contracts/runtime.sample.json` documents `GET /api/v1/runtime`, including
  the standalone API's default heartbeat-only `runtime.control_plane`.
- `contracts/operational-preflight.sample.json` documents
  `GET /api/v1/runtime/operational-preflight`. Desktop, mobile, and dashboard
  clients should treat the top-level fields, `start` and `orders` gate objects,
  `freshness` inputs, `critical_stale` lists, and `reasons` as the stable shape.

`GET /api/v1/runtime` and `GET /api/v1/dashboard` also expose
`runtime.control_plane`. Use `mode`, `owner`, `execution_scope`,
`start_supported`, `stop_supported`, `trading_execution_supported`, and `notes`
to distinguish intent-only recording, standalone lifecycle heartbeat sessions,
delegated adapters, and desktop-forwarded trading runtime control.

Operator recovery steps for blocked or warning preflight states are documented
in [docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md](../../docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md).

Validate checked-in contract artifacts with:

```bash
python Languages/Python/tools/check_service_api_contracts.py
```

Refresh the generated route-name artifact with:

```bash
python Languages/Python/tools/check_service_api_contracts.py --write
```
