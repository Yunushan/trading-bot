# Trading Bot Web Dashboard

Thin browser dashboard for the Trading Bot service API.

This app is served by the backend at `/ui/` and talks to the same service API
contract used by the desktop-remote and mobile thin-client paths.

## Scope

- inspect runtime, status, backtest state, config, account, portfolio, and logs
- request bot start/stop through the service API
- edit service-owned config state
- trigger and stop service-owned backtests

It does not hold exchange credentials or run trading logic locally.

## Run

This dashboard is normally served by the backend:

```bash
python ../service-api/main.py --serve --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/ui/
```
