# Trading Bot Service API Guide

This document is the main operator/developer reference for the headless service layer in `Languages/Python/app/service/`.

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

## Dependency sets

From `Languages/Python/`:

```bash
cd Languages/Python
```

Install the service-focused dependency set:

```bash
pip install -r requirements.service.txt
```

If you want the fuller backend environment used by Docker and service-owned backtest workloads:

```bash
pip install -r requirements.backend.txt
```

## Run the standalone API

Basic local run:

```bash
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

Expose it to the local network:

```bash
python -m app.service.main --serve --host 0.0.0.0 --port 8000
```

## Optional bearer token

CLI form:

```bash
python -m app.service.main --serve --host 127.0.0.1 --port 8000 --api-token your-secret-token
```

Environment-variable form:

```bash
BOT_SERVICE_API_TOKEN=your-secret-token python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

PowerShell:

```powershell
$env:BOT_SERVICE_API_TOKEN='your-secret-token'
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

When bearer auth is enabled:

- REST requests use `Authorization: Bearer ...`
- the browser dashboard uses the same token for SSE via query-string because `EventSource` does not support custom headers

## Built-in web dashboard

The service serves a thin same-origin dashboard at:

```text
http://127.0.0.1:8000/ui/
```

Current dashboard capabilities:

- runtime and status inspection
- account and portfolio snapshots
- log viewing
- editable top-level config patching
- lifecycle start/stop requests
- execution-session visibility
- service-owned backtest visibility and control
- live dashboard refresh over Server-Sent Events

## Desktop-hosted API mode

If you want browser clients to follow the real desktop-owned runtime instead of a separate standalone service process, use the embedded desktop host.

You can enable this either:

- from the desktop GUI via the `Desktop Service API` controls
- or through environment variables before launching `main.py`

PowerShell example:

```powershell
$env:BOT_ENABLE_DESKTOP_SERVICE_API='1'
$env:BOT_DESKTOP_SERVICE_API_HOST='127.0.0.1'
$env:BOT_DESKTOP_SERVICE_API_PORT='8000'
$env:BOT_SERVICE_API_TOKEN='your-secret-token'
python main.py
```

Then open:

```text
http://127.0.0.1:8000/ui/
```

This mode serves the API against the same embedded service object the desktop GUI mirrors, so browser clients can observe live desktop-owned runtime, account, portfolio, and log state.

## Current endpoint coverage

Core routes:

- `GET /health`
- `GET /api/dashboard`
- `GET /api/runtime`
- `GET /api/status`
- `GET /api/config`
- `GET /api/config-summary`
- `GET /api/account`
- `GET /api/portfolio`
- `GET /api/logs`
- `GET /api/execution`
- `GET /api/backtest`

Streaming:

- `GET /api/stream/dashboard`

Write/control routes:

- `POST /api/control/start`
- `POST /api/control/stop`
- `PATCH /api/config`
- `PUT /api/runtime/state`
- `POST /api/backtest/run`
- `POST /api/backtest/stop`

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

- thin browser dashboard in `Languages/Python/clients/web/`
- Expo-based Android/iOS thin client scaffold in `Languages/Python/clients/mobile/`

These clients are intended to talk to the backend API only. Exchange or broker secrets should stay on the backend.
