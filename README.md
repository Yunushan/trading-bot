<div align="center">
  <img src="assets/crypto_forex_logo.png" alt="Trading Bot Workspace logo" width="140" />
  <h1>Trading Bot Workspace</h1>
  <p><strong>Desktop-first multi-market trading workspace with live execution, charting, positions, backtesting, and multi-language scaffolding.</strong></p>
  <p>
    <a href="https://github.com/Yunushan/trading-bot/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Yunushan/trading-bot/ci.yml?branch=main&amp;label=build" alt="Main branch build" /></a>
    <a href="https://github.com/Yunushan/trading-bot/releases"><img src="https://img.shields.io/github/v/release/Yunushan/trading-bot?display_name=tag&amp;label=release" alt="Latest release" /></a>
    <a href="https://github.com/Yunushan/trading-bot/releases"><img src="https://img.shields.io/github/downloads/Yunushan/trading-bot/total?label=downloads" alt="Total downloads" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/python-3.10--3.13-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10 to 3.13" />
    <img src="https://img.shields.io/badge/gui-PyQt6-41CD52?logo=qt&amp;logoColor=white" alt="PyQt6 GUI" />
    <img src="https://img.shields.io/badge/markets-Exchanges%20%7C%20FX%20%7C%20Crypto-111827" alt="Markets" />
    <img src="https://img.shields.io/badge/primary%20live%20integration-Binance-F3BA2F?logo=binance&amp;logoColor=black" alt="Primary live integration Binance" />
    <img src="https://img.shields.io/badge/status-beta-F59E0B" alt="Beta status" />
    <img src="https://img.shields.io/badge/desktop-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20FreeBSD-111827" alt="Desktop platforms" />
    <img src="https://img.shields.io/badge/backend-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20BSD%20Family%20%7C%20Solaris-111827" alt="Backend platforms" />
    <img src="https://img.shields.io/badge/mobile-Android%20%7C%20iOS-111827" alt="Mobile platforms" />
  </p>
  <p>
    <a href="#quick-start">Quick Start</a>
    &bull;
    <a href="#system-requirements">Support</a>
    &bull;
    <a href="#launching-the-applications">Launch</a>
    &bull;
    <a href="#contributing-and-security">Contributing</a>
    &bull;
    <a href="#user-guide">User Guide</a>
    &bull;
    <a href="#release-guide">Release Guide</a>
    &bull;
    <a href="#license">License</a>
  </p>
</div>

A desktop-first trading workspace centered on the **PyQt6 Python app** in `Languages/Python`, with charting, positions, backtesting, top-level thin clients under `apps/`, and native C++/Rust experimentation under `experiments/`. The project is intended as a broader trading-bot workspace for exchanges, crypto venues, and FX/broker integrations, with **Binance as the current primary live connector path**. This README is now the landing page for installation, platform support, project layout, and the main documentation entry points.

---

## Table of contents

1. [System requirements](#system-requirements)
2. [Project layout](#project-layout)
3. [Developer documentation, comments, and LOC tracking](#developer-documentation-comments-and-loc-tracking)
4. [Contributing and security](#contributing-and-security)
5. [Quick start](#quick-start)
6. [Installing dependencies](#installing-dependencies)
   - [Windows](#windows)
   - [macOS](#macos)
   - [Linux (Ubuntu / Debian / Fedora / Arch)](#linux-ubuntu--debian--fedora--arch)
   - [FreeBSD](#freebsd)
7. [Launching the applications](#launching-the-applications)
8. [User guide](#user-guide)
9. [Service API guide](#service-api-guide)
10. [Release guide](#release-guide)
11. [License](#license)

---

## System requirements

- **Python**: 3.10 – 3.13 (3.11+ recommended). Python 3.14 has not been fully verified.
- **pip**: bundled with Python, used to install dependencies.
- **Internet access**: required for supported exchange/broker REST or WebSocket APIs. Binance is the primary current live path.
- **Operating system**:
  Desktop GUI: Windows 10/11, macOS (Intel & Apple Silicon), most Linux distributions, and FreeBSD.
  Backend/service API: Windows, macOS, Linux, BSD family, and Solaris/illumos on a best-effort basis.
  Mobile: Android/iOS native thin-client path via `apps/mobile-client/`.
- **A supported exchange or broker account** with API credentials. Binance API keys and Testnet are the primary current live/demo path.

Optional but recommended:

- GPU driver updates for hardware acceleration (charts).
- Virtual environment tool (`venv`) to isolate Python dependencies.

### Support overview

Status legend:

- `Supported now`: documented user path with a working implementation today.
- `Active development`: planned/scaffolded path exists, but full end-user parity is not finished.
- `Experimental`: best-effort/manual path, not continuously release-validated.
- `Not supported today`: not shipped as a working connector/runtime in the current repo.
- `Not targeted`: no current packaging or support target.

| Area | Target | Status | Notes |
| --- | --- | --- | --- |
| Desktop GUI | Windows 10/11 | Supported now | Primary desktop path |
| Desktop GUI | macOS (Intel and Apple Silicon) | Supported now | Intel and Apple Silicon release coverage |
| Desktop GUI | Linux (major distros) | Supported now | Docs cover Ubuntu, Debian, Fedora, and Arch |
| Desktop GUI | FreeBSD | Supported now | Source/manual path is documented; release automation depends on a self-hosted runner |
| Desktop GUI | BSD family (OpenBSD / NetBSD / DragonFly BSD / others) | Experimental | Better fit today for the headless backend/service path than the full PyQt GUI |
| Desktop GUI | Solaris / illumos | Experimental | Better fit today for the headless backend/service path than the full PyQt GUI |
| Thin web GUI | Modern browser via service API | Supported now | Current shipped web path is the built-in service dashboard |
| Native mobile | Android | Active development | Expo-based native thin client scaffold exists; backend-connected |
| Native mobile | iOS | Active development | Expo-based native thin client scaffold exists; backend-connected |

| Architecture | Status | Notes |
| --- | --- | --- |
| Windows x64 | Supported now | Release workflow builds binaries |
| Windows ARM64 | Supported now | Release workflow builds binaries |
| Linux x64 | Supported now | Release workflow uses Ubuntu 24.04 x64 |
| Linux ARM64 | Supported now | Release workflow uses Ubuntu 24.04 ARM |
| macOS Intel | Supported now | Release workflow includes Intel runners |
| macOS ARM64 | Supported now | Release workflow includes Apple Silicon runners |
| FreeBSD runner architecture (`uname -m`) | Experimental | Release packaging follows the matching self-hosted runner architecture |
| 32-bit x86 desktop | Not targeted | No current workflow or packaging target |

| Market / connector scope | Status | Notes |
| --- | --- | --- |
| Crypto spot trading | Supported now | Current live path is Binance-led |
| Crypto futures trading | Supported now | Current primary live/demo path |
| Multi-exchange crypto expansion | Active development | UI/service/catalog support exists for more venues |
| FX / broker integrations | Active development | Architecture and UI placeholders exist; production live connectors are not shipped yet |
| Unlisted markets outside the current crypto/FX scope | Not supported today | Would require new connector work and testing |

| Venue / integration | Status | Notes |
| --- | --- | --- |
| Binance | Supported now | Current primary live/demo connector |
| Bybit / OKX / Bitget / Gate / MEXC / KuCoin | Active development | Listed in the exchange catalog; live connectors are not fully shipped yet |
| HTX / Crypto.com Exchange / Kraken / Bitfinex | Active development | Present in the exchange catalog, but not wired as completed live paths yet |
| OANDA / FXCM / IG | Active development | Broker placeholders exist; live integrations are not shipped yet |
| Venues not listed in the repo | Not supported today | Requires a new connector and validation work |

For the fuller breakdown, see [docs/SUPPORT_MATRIX.md](docs/SUPPORT_MATRIX.md).

---

## Project layout

```
assets/
docs/
  DEVELOPMENT.md          # contributor notes and maintenance guidance
  PLATFORM_EXPANSION_PLAN.md
  PROJECT_STRUCTURE.md    # repo/source/output layout
  RELEASES.md             # GitHub release workflow and asset guide
  SERVICE_API.md          # standalone/desktop-hosted backend guide
  SUPPORT_MATRIX.md       # support tiers by platform/market/runtime
  USER_GUIDE.md           # operator walkthrough and safety notes
tools/
  update_loc_snapshot.py

apps/
  desktop-pyqt/          # canonical PyQt desktop launcher
  service-api/           # canonical headless service/API launcher
  mobile-client/         # Expo-based Android/iOS thin native client
  web-dashboard/         # thin service dashboard / future web client seed

experiments/
  native-cpp/            # Qt/C++ desktop preview and native re-platform path
  rust-shells/           # Rust shared-core workspace and desktop shell experiments

Languages/
  Python/
    app/                  # full PyQt6 trading application
    trading_core/         # reusable Python trading-domain package boundary
    docs/
    tools/
    main.py               # deprecated desktop compatibility launcher
    requirements.txt
    requirements.service.txt
    requirements.backend.txt
```

The desktop GUI and Python service/backend still live under `Languages/Python`, but their canonical product launch surfaces now live under `apps/desktop-pyqt/` and `apps/service-api/`. The thin browser and mobile clients live under `apps/` as product-facing frontends. The native C++ and Rust workspaces now live under `experiments/` so their preview/scaffold status is explicit in the repo layout. See [docs/SUPPORT_MATRIX.md](docs/SUPPORT_MATRIX.md) for official vs experimental vs scaffolded platform tiers.

Reusable trading-domain imports are now exposed through the Python package `trading_core` inside `Languages/Python/`, while `app.core` remains the in-repo compatibility namespace for the current monolith runtime.

Generated local artifacts such as `build/`, `dist_enduser/`, `.venv/`, and root-level `Trading-Bot-*.exe` files are not canonical source and are ignored by Git.

---

## Developer documentation, comments, and LOC tracking

Contributor-facing structure and maintenance docs now live here:

- `docs/PROJECT_STRUCTURE.md`
- `docs/DEVELOPMENT.md`
- `docs/PLATFORM_EXPANSION_PLAN.md`
- `docs/SERVICE_API.md`

## Contributing and security

- Contribution workflow: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting policy: [SECURITY.md](SECURITY.md)

### Current LOC snapshot

<!-- LOC-SNAPSHOT:START -->
- Snapshot date: `05.04.2026 GMT+3 Time 22:57:48`
- Total tracked code/config/script lines: `102,888`
- Non-empty tracked code/config/script lines (SLOC-style): `92,840`
- Counting scope: tracked files with extensions `.py`, `.cpp`, `.h`, `.js`, `.ps1`, `.sh`, `.bat`, `.yml`, `.cmake`, `.qrc`, `.in` (plus `CMakeLists.txt`)
<!-- LOC-SNAPSHOT:END -->

Auto-refresh command:

```bash
python tools/update_loc_snapshot.py
```

---

## Quick start

1. **Clone or download** this repository.
2. **Install Python** (3.11 or 3.12 preferred). Remember to check “Add Python to PATH” on Windows.
3. **Install dependencies** using the instructions for your OS below.
4. **Launch the GUI:**
   - Canonical product path: run `python apps/desktop-pyqt/main.py` from the repository root, **or**
   - Deprecated compatibility path: double-click `Languages/Python/Trading-Bot-Python.bat` on Windows, or run `python main.py` from `Languages/Python/`.
5. The dashboard opens. Fill in your exchange or broker API credentials, choose Demo/Testnet or Live, configure symbols and indicators, then click **Start**. Today the default live/demo integration path is Binance.
6. Use the **Positions** tab to monitor open trades and the **Chart/Backtest** tabs for analysis.

---

## Installing dependencies

All commands assume you are inside the Python workspace:

```bash
cd Languages/Python
```

### Windows

**One-click (recommended if Python ≥ 3.10 is already installed):**

1. Double-click `Trading-Bot-Python.bat`.
2. The script creates a virtual environment (`.venv`), installs `requirements.txt`, and starts the GUI.

**Manual method:**

```powershell
python -m pip install --upgrade pip
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ../../apps/desktop-pyqt/main.py
```

> **PowerShell policy tip:** If you encounter a script execution warning, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry activation.

### macOS

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 ../../apps/desktop-pyqt/main.py
```

> **PyQt note:** If the GUI fails to launch after dependency installation, run `pip install PyQt6 PyQt6-Qt6` to pull the Qt runtime explicitly.

### Linux (Ubuntu / Debian / Fedora / Arch)

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 ../../apps/desktop-pyqt/main.py
```

- Ubuntu/Debian: `sudo apt install python3 python3-venv python3-pip`
- Fedora: `sudo dnf install python3 python3-virtualenv`
- Arch: `sudo pacman -S python python-pip`

### FreeBSD

```sh
pkg install python311 py311-pip
python3.11 -m pip install --upgrade pip
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3.11 ../../apps/desktop-pyqt/main.py
```

---

## Launching the applications

| Component | Location | Purpose | How to run |
|-----------|----------|---------|------------|
| **Desktop PyQt app** | `apps/desktop-pyqt/main.py` | Full desktop trading workstation | `python apps/desktop-pyqt/main.py` |
| **Service API** | `apps/service-api/main.py` | Headless backend + `/ui/` dashboard host | `python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000` |
| **Windows launcher** | `Languages/Python/Trading-Bot-Python.bat` | Automates environment creation + launch | Double-click on Windows |

All tools are cross-platform except the `.bat` helper which is Windows-only.

---

## User guide

The operator walkthrough now has a dedicated home in [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

Use that guide for:

- first-run checklist
- dashboard, chart, positions, and backtest behavior
- code languages tab
- helper scripts
- troubleshooting and safety notes

The dedicated guide is now the primary home for day-to-day usage details.

## Service API guide

The headless backend, built-in web dashboard, desktop-hosted API mode, and endpoint reference now have a dedicated home in [docs/SERVICE_API.md](docs/SERVICE_API.md).

Use that guide for:

- standalone API startup
- bearer-token setup
- `/ui/` dashboard usage
- desktop-hosted API mode
- Docker-backed backend usage

## Release guide

GitHub release workflow details now also have a dedicated home in [docs/RELEASES.md](docs/RELEASES.md).

Use that guide for:

- release workflows and asset matrix
- tagging steps
- published asset verification

The dedicated release guide is the primary home going forward.

---
---

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for the full terms. Use the software at your own risk and comply with all exchange and broker terms of service.

Happy trading and safe experimenting! If you discover issues or have feature ideas, open a GitHub issue or start a discussion so we can continue improving the workspace together.
