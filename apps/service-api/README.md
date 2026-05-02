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

Deprecated compatibility launchers still work:

```bash
cd Languages/Python
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

Run controlled CLI/terminal commands locally:

```bash
python apps/service-api/main.py --terminal "status"
python apps/service-api/main.py --terminal "config set mode=Demo/Testnet theme=Blue"
python apps/service-api/main.py --terminal "llm providers"
```

Control an already running service or desktop API host:

```bash
python apps/service-api/main.py --base-url http://127.0.0.1:8000 --terminal "status"
```

The terminal command surface is intentionally allowlisted and does not execute
raw operating-system shell commands.

## Contract Samples

The service keeps sample response payloads in `contracts/` for clients that
consume the HTTP API directly.

- `contracts/operational-preflight.sample.json` documents
  `GET /api/v1/runtime/operational-preflight`. Desktop, mobile, and dashboard
  clients should treat the top-level fields, `start` and `orders` gate objects,
  `freshness` inputs, `critical_stale` lists, and `reasons` as the stable shape.

Operator recovery steps for blocked or warning preflight states are documented
in [docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md](../../docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md).
