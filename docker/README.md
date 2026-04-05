# Docker Backend

Optional container packaging for the Trading Bot service API.

This Docker path packages the headless backend only. It does **not** try to run the PyQt desktop GUI. The container now boots the canonical product wrapper at `apps/service-api/main.py` and includes the thin dashboard assets from `apps/web-dashboard/`.

## Build and run

From the repository root:

```bash
docker compose -f docker/compose.yaml up --build
```

The API will listen on:

```text
http://127.0.0.1:8000
```

## Optional bearer token

Protect the API by exporting `BOT_SERVICE_API_TOKEN` before launch:

```bash
export BOT_SERVICE_API_TOKEN=your-secret-token
docker compose -f docker/compose.yaml up --build
```

PowerShell:

```powershell
$env:BOT_SERVICE_API_TOKEN='your-secret-token'
docker compose -f docker/compose.yaml up --build
```

## What is included

- FastAPI service API
- SSE dashboard endpoint
- thin same-origin web dashboard at `/ui/`
- extracted service-owned backtest runner support

## What is not included

- PyQt desktop GUI
- desktop-hosted API mode
- mobile build tooling
