<p style="color:#b71c1c; font-weight:bold; text-align:center;">
  WARNING: Trading Bot is still in BETA. It may contain mistakes, bugs, or errors.
</p>
<p style="color:#b71c1c; text-align:center;">
  Neither the author nor this bot accepts any legal responsibility for trading outcomes. Use it at your own risk.
</p>

# Trading Bot (Python → Languages/Python)

A PyQt6 desktop GUI for spot and futures trading on Binance.

## Introduction

This repository provides a desktop assistant for building and exercising trading strategies on Binance. The application focuses on transparency and configurability, yet it is an experimental project that should be evaluated carefully on demo accounts before live deployment. Attachments such as hero banners or platform-specific previews can help you showcase the bot inside documentation or release notes.




## Requirements
- Python 3.10+ to 3.14 (3.11,3.12,3.13)
- pip
- Internet access for the Binance API

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

---

## Usage
- Paste your **API Key/Secret**.
- Select **Account Type** (Spot/Futures) and **Mode** (Live/Testnet).
- Choose symbols and intervals, set indicators and position %.
- Press **Start**.
- The **Positions** tab shows each interval separately with **Size**, **Margin Ratio**, **Margin**, **PNL (ROI%)**, **Entry TF**, **Side**, **Time**, **Status**, and **Close**.

## Optional service API

The repo now also includes an early headless service API layer for future web/mobile/remote desktop clients.

Install the optional service dependencies:

```bash
pip install -r requirements.service.txt
```

This service-only dependency set is intentionally separate from the desktop GUI stack.

Run the API locally:

```bash
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

Protect the API with an optional bearer token:

```bash
python -m app.service.main --serve --host 127.0.0.1 --port 8000 --api-token your-secret-token
```

Or via environment variable:

```bash
set BOT_SERVICE_API_TOKEN=your-secret-token
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```

The service also serves a thin same-origin dashboard at:

```text
http://127.0.0.1:8000/ui/
```

If bearer auth is enabled, enter the same token into the dashboard before refreshing protected API data.
The dashboard can now:

- read runtime, status, account, portfolio, logs, and editable config
- send start/stop lifecycle requests
- manually mirror running/idle runtime state in standalone service mode
- follow the real desktop bot runtime automatically when attached to the desktop-embedded API
- save a top-level config patch back to the service
- follow live dashboard updates over Server-Sent Events instead of polling after the first connect

Key endpoints currently exposed:

- `GET /health`
- `GET /api/dashboard`
- `GET /api/runtime`
- `GET /api/config`
- `GET /api/status`
- `GET /api/config-summary`
- `GET /api/account`
- `GET /api/portfolio`
- `GET /api/logs`
- `GET /api/stream/dashboard`
- `PATCH /api/config`
- `POST /api/control/start`
- `POST /api/control/stop`
- `PUT /api/runtime/state`

When bearer auth is enabled, the REST API uses the normal `Authorization: Bearer ...` header.
The browser dashboard uses the same token for its SSE stream connection as a query parameter because `EventSource` does not support custom auth headers.

### Host the API from the desktop process

If you want the browser dashboard to follow the real in-process desktop runtime state, you can opt in to a desktop-hosted service API instead of starting a separate headless service process.

You can now also do this directly from the desktop GUI through the `Desktop Service API` controls on the dashboard action area. That UI lets you:

- enable or disable the embedded API host
- choose host and port
- provide a session-only bearer token
- open the browser dashboard directly

The desktop UI persists `enabled`, `host`, and `port` in the app-state file. The token is session-only and is not written into app-state.

Windows PowerShell example:

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

This mode serves the API and dashboard against the same embedded service object the desktop GUI is already mirroring, so web clients can see the desktop-owned runtime/account/portfolio/log updates live.
Start and stop requests from the thin dashboard are now also forwarded into the live desktop GUI thread, so browser clients can trigger the real desktop runtime without using the manual running/idle sync controls.

### Safe Exit
Closing the window or pressing Alt+F4 will market-close all active positions (best effort).

---

## License

Copyright (c) 2025 Trading Bot contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

See [LICENSE](LICENSE) for the official terms.




