# Trading Bot User Guide

This document keeps the day-to-day operator walkthrough out of the root README.

Use the root [README.md](../README.md) for installation, platform support, and repository layout. Use this guide once the app is installed and you are ready to operate it.

## First-run checklist

1. **Create API credentials for your selected venue**: if you use the current primary Binance path, create Binance API keys, enable **Futures** permissions if required, and add your IP to the whitelist if you use IP restrictions.
2. **Select Demo/Testnet vs Live**: Beginners should select *Demo/Testnet* to avoid real trades.
3. **Choose Account Type**: *Spot* for spot trades, *Futures* for USDⓈ-M futures. When using futures, confirm your account is set to hedge mode if you plan to run both longs and shorts simultaneously.
4. **Verify leverage**: The dashboard leverage spinner only sets target leverage for the strategy. You still must configure leverage per symbol on Binance (the bot attempts to sync but validating manually is safer).
5. **Configure position percentage**: This percentage represents the **margin** allocation per indicator trigger (for example, 2% of a 3,500 USDT wallet is about 70 USDT margin per signal at 20x leverage, or about 1,400 USDT notional).
6. **Enable stop loss**: For beginners, keep stop-loss enabled with a 1% percent scope **per trade**.
7. **Save a template**: Use the **Save Config** button so you can reload the same setup later.
8. **Run in small scope**: Start with 1-2 symbols/interval combinations before scaling up.

## Dashboard Tab

The dashboard is the control center. Elements are laid out from top to bottom, left to right.

### Account & API section

| Control | Description |
|---------|-------------|
| **API Key / Secret** | Paste your exchange or broker credentials. Secrets are stored in-memory for the current session only. Binance is the primary current live integration. |
| **Mode** | `Live` sends orders to production. `Demo/Testnet` targets the test environment for the active connector; Binance Testnet is the primary current path. |
| **Account Type** | `Spot` or `Futures`. Determines available connectors and controls. |
| **Account Mode** | Binance “Classic Trading” or other modes (for documentation). Does not switch your Binance account automatically, so make sure the selected mode matches your venue settings. |
| **Connector** | Currently defaults to **Binance SDK Derivatives Trading USDⓈ Futures** (official). Switching connectors lets you plug in alternative libraries when available. |
| **Theme** | Light/Dark UI theme switcher. |
| **Refresh Buttons** | `Refresh Symbols` pulls the latest symbol list from the active exchange connector. Binance is the current default implementation. |

### Market & interval pickers

| Control | Description |
|---------|-------------|
| **Symbols** | Multi-select list of trading pairs. Hold `Ctrl`/`Cmd` to pick several. |
| **Intervals** | Standard exchange intervals (1m, 3m, 5m, and so on). The current default connector uses Binance-style interval sets. |
| **Custom Interval(s)** | Type comma-separated custom intervals such as `45s,90m`. Click **Add Custom Interval(s)** to append them. |
| **Loop Interval Override** | How frequently the engine refreshes data per symbol, for example 1 minute. |

### Strategy controls

| Control | Description |
|---------|-------------|
| **Side** | `Buy (Long)`, `Sell (Short)`, or `Both`. In hedge mode the bot opens separate long and short legs. |
| **Position % of Balance** | Margin allocation per indicator trigger. Combined with leverage and the number of triggered indicators, this gives total notional exposure. |
| **Leverage (Futures)** | Target leverage passed to futures orders. The bot attempts to align exchange leverage; verify on Binance. |
| **Margin Mode** | `Cross` or `Isolated`. Applies when supported by the connector. |
| **Position Mode** | `Hedge` or `One-way`. Hedge mode is required for simultaneous long/short operation. |
| **Assets Mode** | Single-Asset vs Multi-Asset margin. This is currently a Binance futures-oriented control. |
| **Time in Force (TIF)** | Order life such as GTC, IOC, FOK, or GTD. `GTD Minutes` is active when TIF is GTD. |
| **Add-only** | Prevents the bot from increasing exposure in the opposite direction. |
| **Market Close All On Window Close** | Emergency guard to close positions when quitting the app. |

### Risk management (stop loss)

- **Enable** toggles stop-loss logic.
- **Mode** can be `USDT`, `Percent`, or `Both`.
- **Scope** can be `Per Trade`, `Cumulative`, or `Entire Account`.
- **USDT / Percent fields** define the thresholds. Example: Percent=`1` with `20x` leverage closes the leg when price moves about `1%` against you, or about `20%` on margin.

### Indicator configuration

Click the **Indicators** section to expand each study such as RSI, Stochastic RSI, Williams %R, MA, MACD, or SuperTrend. For every indicator you can enable the signal, adjust key parameters, and set `buy_value` / `sell_value` trigger values.

When an indicator fires, the bot records the **indicator key**, **interval**, and **side**. The sizing logic ensures only one position per `(symbol, indicator, side)` bucket is active at a time.

### Session controls & presets

- **Start** launches workers for every selected symbol/interval/side combination.
- **Save Config / Load Config** persists your dashboard settings to JSON for later reuse.
- **Template** quickly loads a pre-bundled setup.
- **Lead Trader** is reserved for future copy-trading style work.

### Realtime log viewer

- **All Logs** shows orders, warnings, and system messages.
- **Position Trigger Logs** shows a concise feed of indicator triggers and decision outcomes.

Double-clicking logs copies them to the clipboard.

## Chart Tab

Enabled when chart dependencies are present. Features:

- Market selection synced with the dashboard when **Auto Follow** is enabled.
- View modes for raw candles, indicator overlays, or TradingView embed when configured.
- Manual refresh and zoom tools for quick inspection before enabling a strategy.

If charts are disabled, the tab is hidden automatically to save resources.

## Positions Tab

| Control | Description |
|---------|-------------|
| **Refresh Positions** | Manually request an update. Auto-refresh also runs on a timer. |
| **Market Close ALL Positions** | Attempts to close every open leg immediately. |
| **Positions View** | `Cumulative View` groups positions per symbol/side. `Per Trade View` lists each indicator leg separately. |
| **Open table columns** | Symbol, Balance/Position, Last Price, Size, Margin Ratio, Margin, PNL (ROI%), Interval(s), Indicator(s), Side, Open Time, Close Time, Stop-Loss status, Live status, and a **Close** button per row. |
| **Closed table** | Displays historical positions when you switch to the closed-positions mini-tab. |

The internal guards ensure margin allocation matches your configured position percentage. If the same indicator appears twice for a symbol, the duplicate should move into a close/pending-close path instead of staying as a second live leg.

## Backtest Tab

1. Choose symbol and interval overrides for the backtest.
2. Set capital, leverage, and margin/position modes.
3. Mirror your live indicator configuration.
4. Click **Start Backtest** to fetch candles from the active data source and run the strategy.
5. Review the results table for PNL, ROI, win rate, max drawdown, trade count, and interval-level stats.
6. Export or clear results as needed.

Backtests run locally. Respect exchange rate limits if you are repeating runs against live venue data.

## Code Languages Tab

This tab lists the supported code languages and keeps the scaffolding paths organized.

1. Choose your language such as Python, C++, or Rust.
2. The workspace ensures the language folder exists so related assets stay organized.
3. When Rust is selected, you can also choose a Rust desktop framework scaffold such as Tauri, Slint, egui, Iced, or Dioxus Desktop.

## Utilities and helper scripts

| File | Location | Description |
|------|----------|-------------|
| `Trading-Bot-Python.bat` | `Languages/Python/` | Automates environment bootstrap on Windows. |
| `close_all.py` | `Languages/Python/app/` | Auxiliary script to close every futures position. |
| `trading_core/positions.py` | `Languages/Python/` | Public reusable positions surface exposing the guard logic used to deduplicate indicator entries and enforce stop-loss/stop-gap rules. |
| `requirements.txt` | `Languages/Python/` | Python dependency pinning for the desktop GUI. |

## Troubleshooting & FAQ

**The GUI won’t start / missing Qt platform plugin**  
Ensure the virtual environment is activated and reinstall Qt packages: `pip install PyQt6 PyQt6-Qt6 PyQt6-Charts`.

**Orders are sized smaller than expected**  
Verify `Position % of Balance` describes the margin share. If you see unusually small sizes, confirm you restarted the app after updating and that leverage is correct on your venue.

**Multiple identical legs opened**  
Duplicate protection is interval-aware. After updating, restart the bot so the latest guard logic is active.

**Stop-loss did not trigger**  
Make sure `Stop Loss` is enabled and the scope/percent values make sense. In hedge mode the bot closes only the leg that breaches the threshold.

**Where are logs stored?**  
They are in-memory only unless you capture stdout/stderr from a terminal launch.

**How do I update dependencies?**  
Reactivate the virtual environment and run `pip install -r requirements.txt --upgrade`. On Windows you can also rerun the `.bat` launcher.

## Safety notes

- **Beta software**: always test on demo/testnet first.
- **No warranty**: review the code before entrusting significant capital.
- **API key scope**: never enable withdrawal permissions on trading keys.
- **Exchange settings**: leverage mode and position mode must still be configured on the venue itself.
- **Backtest limitations**: historical simulations do not guarantee future performance.
