<p style="color:#b71c1c; font-weight:bold; text-align:center;">
  WARNING: Trading Bot is still in BETA. It may contain mistakes, bugs, or errors.
</p>
<p style="color:#b71c1c; text-align:center;">
  Neither the author nor this bot accepts any legal responsibility for trading outcomes. Use it at your own risk.
</p>

# Trading Bot (Python → Languages/Python)

A PyQt6 desktop GUI for spot, futures, exchange, and broker-driven trading workflows, with Binance as the current primary live connector path.

Support tiers:

- Desktop GUI: Windows, macOS, Linux, and FreeBSD
- Backend/service API: Windows, macOS, Linux, BSD family, and Solaris/illumos on a best-effort basis
- Native mobile thin client: Android and iOS via `clients/mobile/`

## Introduction

This repository provides a desktop assistant for building and exercising trading strategies across exchanges, crypto venues, and future FX/broker integrations. The application focuses on transparency and configurability, yet it is an experimental project that should be evaluated carefully on demo accounts before live deployment. The current primary live/demo implementation is Binance, but the workspace architecture is broader than a Binance-only bot.

Repo-level docs:

- operator guide: [../../docs/USER_GUIDE.md](../../docs/USER_GUIDE.md)
- service API guide: [../../docs/SERVICE_API.md](../../docs/SERVICE_API.md)
- release guide: [../../docs/RELEASES.md](../../docs/RELEASES.md)
- support matrix: [../../docs/SUPPORT_MATRIX.md](../../docs/SUPPORT_MATRIX.md)
- expansion plan: [../../docs/PLATFORM_EXPANSION_PLAN.md](../../docs/PLATFORM_EXPANSION_PLAN.md)
- Python tools guide: [tools/README.md](tools/README.md)

## Requirements
- Python 3.10+ to 3.14 (3.11,3.12,3.13)
- pip
- Internet access for supported exchange or broker APIs. Binance is the current primary live path.

---

## Install Python + dependencies

> All commands below assume you already switched to the Python workspace:
> ```bash
> cd Languages/Python
> ```

### For Easy Windows Install (If Python 3.10,3.11,3.12,3.13 Installed)
### Windows
   ```execute
    run (Double Click) "Trading-Bot-Python.bat" file.
   ```
### For Regular Windows Install (If Python 3.10,3.11,3.12,3.13 Installed)
1. Install Python from https://python.org (check **Add Python to PATH** during setup).
2. Open **PowerShell**:
   ```powershell
   python -m pip install --upgrade pip
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Run:
   ```powershell
   python main.py
   ```

### Linux (Debian/Ubuntu/Fedora/Arch)
```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### macOS (Intel & Apple Silicon)
```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

If you see issues with PyQt on macOS, install the Qt runtime:
```bash
pip install PyQt6 PyQt6-Qt6
```

### FreeBSD
```sh
pkg install python3 py39-pip  # or pkg install python311 py311-pip
python3 -m pip install --upgrade pip
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### BSD family / Solaris / illumos

The current best-effort expansion path for non-FreeBSD BSD systems and Solaris/illumos is the headless service/backend, not the full PyQt desktop GUI.

Use the service entrypoint and backend dependency set:

```bash
pip install -r requirements.backend.txt
python -m app.service.main --serve --host 0.0.0.0 --port 8000
```

Package names for Python, pip, venv, and Qt differ across these operating systems, so the exact system-level install commands are intentionally left to the target platform.

---

## Usage
- Paste your **API Key/Secret** for the selected connector.
- Select **Account Type** (Spot/Futures) and **Mode** (Live/Testnet).
- Choose symbols and intervals, set indicators and position %.
- Press **Start**.
- The **Positions** tab shows each interval separately with **Size**, **Margin Ratio**, **Margin**, **PNL (ROI%)**, **Entry TF**, **Side**, **Time**, **Status**, and **Close**.

## Optional service API

The full service/backend reference now lives in [../../docs/SERVICE_API.md](../../docs/SERVICE_API.md).

Use that guide for:

- standalone API startup
- bearer-token protection
- built-in `/ui/` dashboard usage
- desktop-hosted API mode
- current endpoint coverage
- Docker-backed backend runs

Quick start:

```bash
pip install -r requirements.service.txt
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

## Optional Docker backend

The repo now includes optional backend-only Docker packaging in [docker/README.md](../../docker/README.md).

Quick start from the repository root:

```bash
docker compose -f docker/compose.yaml up --build
```

This packages the headless service API and thin web dashboard only. It does not containerize the PyQt desktop GUI.

## Native Android/iOS thin client

There is now an Expo-based native client in `Languages/Python/clients/mobile/` for Android and iOS thin-client work.

From that folder:

```bash
npm install
npm run start
```

For native build profiles, the Expo/EAS configuration is in `Languages/Python/clients/mobile/eas.json`.

Use the machine's LAN IP instead of `127.0.0.1` when connecting from a physical phone to a backend running on your desktop or server.

### Safe Exit
Closing the window or pressing Alt+F4 will market-close all active positions (best effort).

---

## License

See the repository [LICENSE](../../LICENSE) for the official terms.
