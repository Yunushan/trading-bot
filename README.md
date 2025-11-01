# Binance Trading Bot Workspace

This repository packages a cross‑platform trading workstation that ships with a production‑ready **Binance desktop bot (PyQt6)**, a guided launcher (`starter.py`), and scaffolding for future language/ exchange ports. The goal of this README is to serve as a complete beginner‑friendly manual: how to install the project on every OS, what each button does, how the tabs behave, and how to operate the bot safely.

---

## Table of contents

1. [System requirements](#system-requirements)
2. [Project layout](#project-layout)
3. [Quick start](#quick-start)
4. [Installing dependencies](#installing-dependencies)
   - [Windows](#windows)
   - [macOS](#macos)
   - [Linux (Ubuntu / Debian / Fedora / Arch)](#linux-ubuntu--debian--fedora--arch)
   - [FreeBSD](#freebsd)
5. [Launching the applications](#launching-the-applications)
6. [First-run checklist](#first-run-checklist)
7. [Dashboard tab – full walkthrough](#dashboard-tab--full-walkthrough)
   - [Account & API section](#account--api-section)
   - [Market / interval pickers](#market--interval-pickers)
   - [Strategy controls](#strategy-controls)
   - [Risk management (stop loss)](#risk-management-stop-loss)
   - [Indicator configuration](#indicator-configuration)
   - [Session controls & presets](#session-controls--presets)
   - [Realtime log viewer](#realtime-log-viewer)
8. [Chart tab](#chart-tab)
9. [Positions tab](#positions-tab)
10. [Backtest tab](#backtest-tab)
11. [Code Languages & Exchanges tab](#code-languages--exchanges-tab)
12. [Utilities and helper scripts](#utilities-and-helper-scripts)
13. [Troubleshooting & FAQ](#troubleshooting--faq)
14. [Safety notes](#safety-notes)
15. [License](#license)

---

## System requirements

- **Python**: 3.10 – 3.13 (3.11+ recommended). Python 3.14 has not been fully verified.
- **pip**: bundled with Python, used to install dependencies.
- **Internet access**: required for Binance REST/WebSocket APIs.
- **Operating system**: Windows 10/11, macOS (Intel & Apple Silicon), most Linux distributions, or FreeBSD.
- **Binance account** with API key/secret. Create a Testnet account to experiment safely.

Optional but recommended:

- GPU driver updates for hardware acceleration (charts).
- Virtual environment tool (`venv`) to isolate Python dependencies.

---

## Project layout

```
Languages/
├─ Python/
│  ├─ Crypto-Exchanges/
│  │  └─ Binance/            # full PyQt6 trading application
│  └─ Forex-Brokers/
├─ C++/
│  └─ Crypto-Exchanges/
│     └─ Binance/backtest_tab    # Qt C++ prototype for the Backtest UI
├─ C/
└─ Rust/
starter.py                    # language & exchange launcher (wizard)
requirements.txt              # shared dependency list for Python projects
```

Everything users interact with today lives under `Languages/Python/Crypto-Exchanges/Binance` (referred to as “the Binance app”). Other language folders are stubs reserved for future ports.

---

## Quick start

1. **Clone or download** this repository.
2. **Install Python** (3.11 or 3.12 preferred). Remember to check “Add Python to PATH” on Windows.
3. **Install dependencies** using the instructions for your OS below.
4. **Launch the GUI:**
   - Windows one-click: double-click `Languages/Python/Crypto-Exchanges/Binance/Binance-Bot-Trading.bat`, **or**
   - Any OS: activate the virtual environment and run `python main.py` from the Binance folder.
5. The dashboard opens. Fill in your Binance API key/secret, choose Demo/Testnet or Live, configure symbols and indicators, then click **Start**.
6. Use the **Positions** tab to monitor open trades and the **Chart/Backtest** tabs for analysis.

---

## Installing dependencies

All commands assume you are inside the Binance Python workspace:

```bash
cd Languages/Python/Crypto-Exchanges/Binance
```

### Windows

**One-click (recommended if Python ≥ 3.10 is already installed):**

1. Double-click `Binance-Bot-Trading.bat`.
2. The script creates a virtual environment (`.venv`), installs `requirements.txt`, and starts the GUI.

**Manual method:**

```powershell
python -m pip install --upgrade pip
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ..\..\..\..\requirements.txt
python main.py
```

> **PowerShell policy tip:** If you encounter a script execution warning, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry activation.

### macOS

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../../../../requirements.txt
python3 main.py
```

> **PyQt note:** If the GUI fails to launch after dependency installation, run `pip install PyQt6 PyQt6-Qt6` to pull the Qt runtime explicitly.

### Linux (Ubuntu / Debian / Fedora / Arch)

```bash
python3 -m pip install --upgrade pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../../../../requirements.txt
python3 main.py
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
pip install -r ../../../../requirements.txt
python3.11 main.py
```

---

## Launching the applications

| Component | Location | Purpose | How to run |
|-----------|----------|---------|------------|
| **Binance GUI bot** | `Languages/Python/Crypto-Exchanges/Binance/main.py` | Full desktop trading workstation | `python main.py` (inside virtual env) |
| **Windows launcher** | `Languages/Python/Crypto-Exchanges/Binance/Binance-Bot-Trading.bat` | Automates environment creation + launch | Double-click on Windows |
| **Project wizard** | `starter.py` | Card-based selector that opens the right app for your chosen language/exchange | `python starter.py` from repo root |

All tools are cross-platform except the `.bat` helper which is Windows-only.

---

## First-run checklist

1. **Create Binance API keys**: log into Binance, create API keys, enable **Futures** permissions if required, and add your IP to the whitelist if you use IP restrictions.
2. **Select Demo/Testnet vs Live**: Beginners should select *Demo/Testnet* to avoid real trades.
3. **Choose Account Type**: *Spot* for spot trades, *Futures* for USDⓈ-M futures. When using futures, confirm your account is set to hedge mode if you plan to run both longs and shorts simultaneously.
4. **Verify leverage**: The dashboard leverage spinner only sets target leverage for the strategy. You still must configure leverage per symbol on Binance (the bot attempts to sync but validating manually is safer).
5. **Configure position percentage**: This percentage represents the **margin** allocation per indicator trigger (e.g., 2% of a 3,500 USDT wallet ≈ 70 USDT margin per signal at 20× leverage → 1,400 USDT notional).
6. **Enable stop loss**: For beginners, keep stop-loss enabled with a 1 % percent scope **per trade**.
7. **Save a template**: Use the **Save Config** button so you can reload the same setup later.
8. **Run in small scope**: Start with 1–2 symbols/interval combinations before scaling up.

---

## Dashboard tab – full walkthrough

The dashboard is the control center. Elements are laid out from top to bottom, left to right.

### Account & API section

| Control | Description |
|---------|-------------|
| **API Key / Secret** | Paste your Binance keys. Secrets are stored in-memory for the current session only. |
| **Mode** | `Live` sends orders to production. `Demo/Testnet` targets Binance Testnet. |
| **Account Type** | `Spot` or `Futures`. Determines available connectors and controls. |
| **Account Mode** | Binance “Classic Trading” or other modes (for documentation). Does not switch your Binance account automatically—make sure the selected mode matches your Binance settings. |
| **Connector** | Currently defaults to **Binance SDK Derivatives Trading USDⓈ Futures** (official). Switching connectors lets you plug in alternative libraries when available. |
| **Theme** | Light/Dark UI theme switcher. |
| **Refresh Buttons** | `Refresh Symbols` pulls the latest symbol list from Binance. |

### Market & interval pickers

| Control | Description |
|---------|-------------|
| **Symbols** | Multi-select list of trading pairs. Hold `Ctrl`/`Cmd` to pick several. |
| **Intervals** | Standard Binance intervals (1m, 3m, 5m, …). |
| **Custom Interval(s)** | Type comma-separated custom intervals (e.g., `45s,90m`). Click **Add Custom Interval(s)** to append them. |
| **Loop Interval Override** | How frequently the engine refreshes data per symbol (e.g., 1 minute). |

### Strategy controls

| Control | Description |
|---------|-------------|
| **Side** | `Buy (Long)`, `Sell (Short)`, or `Both`. In hedge mode the bot opens separate long and short legs. |
| **Position % of Balance** | Margin allocation per indicator trigger (e.g., 2 % of wallet). Combined with leverage and the number of triggered indicators, this gives total notional exposure. |
| **Leverage (Futures)** | Target leverage passed to futures orders. The bot attempts to align exchange leverage; verify on Binance. |
| **Margin Mode** | `Cross` or `Isolated`. Applies when supported by the connector. |
| **Position Mode** | `Hedge` (long + short simultaneously) or `One-way`. Hedge mode is required for the logic described in the user request (multiple concurrent legs). |
| **Assets Mode** | Single-Asset vs Multi-Asset margin (Binance futures feature). |
| **Time in Force (TIF)** | Order life (GTC, IOC, FOK, GTD). `GTD Minutes` is active when TIF=GTD. |
| **Add-only** | When enabled, prevents the bot from increasing exposure in the opposite direction (useful in one-way mode). |
| **Market Close All On Window Close** | Emergency guard to close positions when quitting the app. |

### Risk management (stop loss)

- **Enable**: toggles stop-loss logic.
- **Mode**: `USDT`, `Percent`, or `Both`. Percent is relative to entry margin by default.
- **Scope**:
  - `Per Trade`: each indicator leg is monitored independently.
  - `Cumulative`: combines all legs within a symbol/side.
  - `Entire Account`: aborts all when the account reaches the threshold.
- **USDT / Percent fields**: thresholds. Example: Percent=1 with 20× leverage closes the leg when price moves 1 % against you (~20 % on margin).

### Indicator configuration

Click the **Indicators** section to expand each study (RSI, Stochastic RSI, Williams %R, MA, MACD, SuperTrend, etc.). For every indicator you can:

- **Enable** the signal
- Adjust key parameters (length, smoothing, thresholds)
- Set **buy_value / sell_value** to customize triggers

When an indicator fires, the bot records the **indicator key**, **interval**, and **side**. The new sizing logic ensures only one position per `(symbol, indicator, side)` bucket is active at any time; duplicate triggers for the same slot are ignored until the existing leg closes.

### Session controls & presets

- **Start**: launches workers for every selected symbol/interval/side combination.
- **Save Config / Load Config**: persists your dashboard settings to JSON for later reuse.
- **Template** dropdown: quickly load pre-bundled setups (e.g., “Top 10 %2 per trade 5x Isolated”). Templates notch stop-loss, leverage, and indicator defaults.
- **Lead Trader** (coming soon): hook to copy trade from a published lead profile.

### Realtime log viewer

Bottom pane toggles between:

- **All Logs**: everything (orders, warnings, system messages).
- **Position Trigger Logs**: concise feed of indicator triggers and decision outcomes (opened, suppressed by guard, closed by stop-loss, etc.).

Double-clicking logs copies them to the clipboard for support purposes.

---

## Chart tab

Enabled when chart dependencies are present (PyQtGraph / QtCharts). Features:

- Market selection synced with the dashboard (if “Auto Follow” is enabled).
- View modes: raw candles, indicator overlays, or TradingView embed (when configured).
- Manual refresh/zoom tools for quick technical inspection before enabling a strategy.

If charts are disabled, the tab is hidden automatically to save resources.

---

## Positions tab

Core monitoring panel. Key elements:

| Control | Description |
|---------|-------------|
| **Refresh Positions** | Manually request an update (auto-refresh runs on a timer). |
| **Market Close ALL Positions** | Attempts to close every open leg immediately (best effort). |
| **Positions View** | `Cumulative View` groups positions per symbol/side, `Per Trade View` lists each indicator leg separately. |
| **Open table columns** | Symbol, Balance/Position, Last Price, Size (USDT notional), Margin Ratio, Margin (USDT), PNL (ROI%), Interval(s), Indicator(s), Side, Open Time, Close Time, Stop-Loss status, Live status, and a **Close** button for each row. |
| **Closed table** | Displays historical positions when you switch to the “Closed Positions” mini-tab (within the same page). |

The internal guards ensure margin allocation matches your `Position %` value. If you see the same indicator listed twice for a symbol in this table, the second entry will show `Status: Pending Close` while the system cancels duplicates.

---

## Backtest tab

Use historical data to validate indicator settings before going live.

1. **Symbol/Interval overrides**: choose assets and timeframes just for the backtest (independent of live runtime pairs).
2. **Capital & leverage**: set the simulated account size, leverage, and margin/position modes identical to the dashboard options.
3. **Indicator configuration**: mirrors live controls so you can keep parameters aligned.
4. **Start Backtest**: fetches candles (from Binance by default) and runs the strategy.
5. **Results table**: sortable grid with metrics such as PNL, ROI, win rate, max drawdown, trade count, and per-interval stats. Column widths auto-size; click headers to sort.
6. **Export/clear**: copy rows to CSV via context menu or clear them to rerun from scratch.

Backtests run locally; however, ensure you respect exchange rate limits by spacing out repeated runs.

---

## Code Languages & Exchanges tab

This tab mirrors the card UI from `starter.py`. Use it to scaffold folders when you plan to port the bot or build auxiliary tools:

1. **Choose your language** (Python, C++, Rust, etc.).
2. **Pick a market** (Crypto Exchanges vs Forex Brokers).
3. **Select an exchange/broker** (Binance, Bybit, OKX, FXCM, etc.).
4. The workspace automatically creates the corresponding directory tree and drops placeholder READMEs or `.gitkeep` files so you can start coding in an organized structure.

It’s a documentation hub as well—each card includes a subtitle describing the stack and badge labels (Recommended, Coming Soon, etc.).

---

## Utilities and helper scripts

| File | Location | Description |
|------|----------|-------------|
| `starter.py` | repo root | Launches the card-based wizard that links to each language/exchange app and ensures Windows AppID metadata is set for proper taskbar integration. |
| `Binance-Bot-Trading.bat` | `Languages/Python/Crypto-Exchanges/Binance/` | Automates environment bootstrap on Windows. |
| `close_all.py` | `Languages/Python/Crypto-Exchanges/Binance/app/` | Auxiliary script to close every futures position—useful for emergency scripts or cron jobs. |
| `position_guard.py` | same folder | Contains the guard logic used to deduplicate indicator entries and enforce stop-loss/stop-gap rules (referenced in this README for understanding behaviour). |
| `requirements.txt` | repo root | Shared dependency pinning for all Python components. |

---

## Troubleshooting & FAQ

**The GUI won’t start / missing Qt platform plugin**
> Ensure the virtual environment is activated and reinstall Qt packages: `pip install PyQt6 PyQt6-Qt6 PyQt6-Charts`.

**Orders are sized smaller than expected**
> Verify `Position % of Balance` describes the **margin share**. With 2 % and 3,500 USDT wallet, each indicator produces ~70 USDT margin. If you see ~6 USDT, confirm you restarted the app after updating to the latest code, and that leverage is set correctly on Binance.

**Multiple identical legs opened**
> Duplicate protection is interval-aware. After updating, restart the bot; the guard checks all existing `(symbol, indicator, side)` legs across intervals before placing new ones.

**Stop-loss did not trigger**
> Make sure `Stop Loss` is enabled and the scope/percent values make sense. For futures hedge mode, the bot closes the specific leg that breaches the threshold; other legs remain open.

**Where are logs stored?**
> In-memory only. Copy/paste from the log viewer or run the bot from a terminal to capture stdout/ stderr.

**How do I update dependencies?**
> Reactivate the virtual environment and run `pip install -r ../../../../requirements.txt --upgrade`. Re-run the `.bat` file on Windows for a fresh environment.

---

## Safety notes

- **Beta software**: The Binance bot is still in BETA. Expect occasional bugs—always test on Testnet first.
- **No warranty**: You bear full responsibility for trading losses. Review the source code before entrusting significant capital.
- **API key scope**: Never enable withdrawal permissions on trading keys. Store keys in a secure password manager and rotate them periodically.
- **Exchange settings**: Leverage mode (cross/isolated) and position mode (hedge/one-way) must be configured on Binance itself even if you change them in the GUI.
- **Backtest limitations**: Historical simulations do not guarantee future performance. Slippage, funding fees, and latency are approximations.

---

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for the full terms. Use the software at your own risk and comply with all exchange terms of service.

Happy trading and safe experimenting! If you discover issues or have feature ideas, open a GitHub issue or start a discussion so we can continue improving the workspace together.
*** End Patch
