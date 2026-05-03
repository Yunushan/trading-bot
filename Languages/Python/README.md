> [!WARNING]
> Trading Bot is still in beta. It may contain mistakes, bugs, or operational gaps.
> Use demo accounts first and treat live trading as your own responsibility.

# Trading Bot Python Workspace

This folder contains the main Python implementation of the project: the PyQt6 desktop app and the service/backend API.

The canonical top-level product launchers now live at the repository root in `../../apps/desktop-pyqt/` and `../../apps/service-api/`. The thin browser and Android/iOS clients live in `../../apps/web-dashboard/` and `../../apps/mobile-client/`.

Reusable trading-domain code is now exposed through the `trading_core` Python package in this workspace. Keep `app.core` for the existing desktop/service runtime internals; use `trading_core` for new shared-domain imports.

The workspace is broader than a Binance-only bot. It is intended for exchange, crypto, and future FX/broker integrations, with Binance currently serving as the primary live/demo connector path.

## Live trading safety

Live exchange mode is fail-closed. A runtime that would talk to live endpoints is blocked unless all of these are configured:

- `live_trading_enabled: true`
- `live_trading_acknowledgement: "I_UNDERSTAND_LIVE_TRADING_RISK"`
- non-placeholder Binance API credentials
- valid caps: `live_trading_max_leverage` and `live_trading_max_position_pct`

Environment alternative:

```bash
export BOT_ENABLE_LIVE_TRADING=true
export BOT_LIVE_TRADING_ACKNOWLEDGEMENT=I_UNDERSTAND_LIVE_TRADING_RISK
export BOT_LIVE_MAX_LEVERAGE=5
export BOT_LIVE_MAX_POSITION_PCT=2
```

## Order audit log

Order intent, local rejection, exchange request, exchange response, exchange error, and fill-summary events are written as append-only JSON Lines. The default path is `~/.trading-bot/order_audit.jsonl`.

Override the path when needed:

```bash
export BOT_ORDER_AUDIT_LOG=/secure/path/order_audit.jsonl
```

## Config validation

Runtime config updates are validated before the service stores them. Invalid symbols, intervals, leverage, position size, stop-loss objects, and symbol/interval override rows are rejected instead of being applied silently. The HTTP API returns `422` with per-field validation details for invalid config requests.

## Support tiers

- Desktop GUI: Windows, macOS, Linux, and FreeBSD
- Backend/service API: Windows, macOS, Linux, BSD family, and Solaris/illumos on a best-effort basis
- Native mobile thin client: Android and iOS via `../../apps/mobile-client/`

## Related docs

- Operator guide: [../../docs/USER_GUIDE.md](../../docs/USER_GUIDE.md)
- Service API guide: [../../docs/SERVICE_API.md](../../docs/SERVICE_API.md)
- Release guide: [../../docs/RELEASES.md](../../docs/RELEASES.md)
- Support matrix: [../../docs/SUPPORT_MATRIX.md](../../docs/SUPPORT_MATRIX.md)
- Expansion plan: [../../docs/PLATFORM_EXPANSION_PLAN.md](../../docs/PLATFORM_EXPANSION_PLAN.md)
- Python tools guide: [tools/README.md](tools/README.md)

## Requirements

- Python 3.10 to 3.14
- `pip`
- Internet access for supported exchange or broker APIs
- API credentials for a supported venue if you want live/demo connectivity

Python 3.11 or newer is recommended.

## Install

All commands below assume you already switched into the Python workspace:

```bash
cd Languages/Python
```

For local development, CI parity, and the complete Python test surface, install
the editable workspace with all reviewed optional groups:

```bash
python -m pip install -e ".[desktop,service,dev]"
python -m unittest discover tests
```

The `dev` extra includes test-only tools such as the FastAPI `TestClient`
transport dependency used by service API contract tests. Use the
`requirements*.txt` shims below when you only need a runtime install for one app
surface.

### Windows

One-click launch:

- If Python 3.10 to 3.14 is already installed, double-click `Trading-Bot-Python.bat`.

Manual setup:

```powershell
python -m pip install --upgrade pip
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ../../apps/desktop-pyqt/main.py
```

If PowerShell blocks activation, run this once and retry:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 ../../apps/desktop-pyqt/main.py
```

### macOS

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 ../../apps/desktop-pyqt/main.py
```

If PyQt fails to launch cleanly on macOS, install the Qt runtime explicitly:

```bash
pip install PyQt6 PyQt6-Qt6
```

### FreeBSD

```sh
pkg install python3 py39-pip  # or the matching current Python package on your system
python3 -m pip install --upgrade pip
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 ../../apps/desktop-pyqt/main.py
```

### BSD family / Solaris / illumos

For non-FreeBSD BSD systems and Solaris/illumos, the current best-effort path is the headless backend/service layer rather than the full PyQt desktop GUI:

```bash
pip install -r requirements.backend.txt
python ../../apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

Exact OS package names for Python, `pip`, `venv`, and Qt vary by platform, so those system-level install commands are intentionally left platform-specific.

## Desktop usage

1. Enter the API key and secret for the selected connector.
2. Choose account type and mode.
3. Select symbols, intervals, and indicator settings.
4. Press `Start`.
5. Use the `Positions`, `Chart`, and `Backtest` tabs to monitor and analyze activity.

The current primary live/demo connector path is Binance, but the workspace is structured for broader venue support.

## Optional service API

The full backend/API reference lives in [../../docs/SERVICE_API.md](../../docs/SERVICE_API.md).

Quick start:

```bash
pip install -r requirements.service.txt
python ../../apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

Use that guide for:

- standalone API startup
- bearer-token protection, which is required for non-loopback hosts
- built-in `/ui/` dashboard usage
- desktop-hosted API mode
- current endpoint coverage
- Docker-backed backend runs

## Optional Docker backend

The repo includes optional backend-only Docker packaging in [../../docker/README.md](../../docker/README.md).

Quick start from the repository root:

```bash
export BOT_SERVICE_API_TOKEN=your-secret-token
docker compose -f docker/compose.yaml up --build
```

This packages the headless service API and thin web dashboard only. It does not containerize the PyQt desktop GUI.

## Android/iOS thin client

There is an Expo-based native thin client in `../../apps/mobile-client/` for Android and iOS.

From that folder:

```bash
npm install
npm run start
```

For native build profiles, see `../../apps/mobile-client/eas.json`.

When connecting from a physical phone to a backend running on your machine, use the machine's LAN IP instead of `127.0.0.1`.

## Safe exit

Closing the desktop window or pressing `Alt+F4` triggers a best-effort market close of active positions.

## License

See the repository [LICENSE](../../LICENSE).
