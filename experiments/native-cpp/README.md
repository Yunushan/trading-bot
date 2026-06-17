# Trading Bot C++ Workspace

This directory contains the native Qt/C++ desktop path for the trading-bot workspace.

Today it is a C++ desktop preview and re-platforming path, not the primary end-user application. The main production-facing implementation is still the Python/PyQt app in `Languages/Python`.

## Current role

- Native Qt Widgets desktop shell
- C++23 / Qt 6 build target
- Dashboard, chart, positions, backtest, and web/runtime slices under active restructuring
- Native exchange connectivity experiments, with Binance as the current implemented connector path inside the C++ tree
- Dashboard LLM settings for cloud providers and local/private OpenAI-compatible endpoints

## Current status

| Area | Status | Notes |
| --- | --- | --- |
| Native desktop shell | Active development | Real source tree exists and builds locally |
| Full feature parity with Python app | Not complete | Still a preview/re-platform path |
| Primary exchange implementation | Binance | Current connector code in this workspace is Binance-specific |
| Cross-platform Qt build path | Supported for local builds | Windows, macOS, and Linux toolchains are expected |

## Full Python app parity audit

The Python app in `Languages/Python` remains the source of truth for full app
behavior. The C++ workspace mirrors many controls and contains native Binance
runtime experiments, but it is not yet a complete replacement for Python.

| Python feature domain | C++ status | Missing before full parity |
| --- | --- | --- |
| Desktop shell and tabs | Major Qt tabs are present | Production startup/lifecycle parity, release ownership, and tab behavior tests |
| Service API contract | Backtest run/stop can delegate to the local Python Service API; no full `/api/v1` host/client surface yet | Generated route/method/schema parity and operational request/response tests |
| Config persistence | Dashboard save/load experiments | Full Python service config save/load, dirty state, hydration, and redaction behavior |
| Strategy runtime | Dashboard runtime experiments | Complete Python indicator, strategy cycle, worker, signal, and override semantics |
| Exchange connectors | Native Binance REST/WebSocket pieces | Python connector backend parity, diagnostics, rate limits, and non-Binance support |
| Account, portfolio, and positions | Binance balance/open futures position sync | Portfolio snapshots, history/allocation ledgers, reconciliation, and non-Binance account paths |
| Order execution and risk | Futures order helpers and stop-loss controls | Python order audit, preflight, circuit breaker, submit guards, and shutdown risk behavior |
| Backtest engine | Backtest UI mirrors Python controls and delegates run/stop to the Python Service API when available | Result/provenance parity tests and full optimizer/scanner coverage |
| Charts and heatmaps | Qt WebEngine panels and browser fallback | Verified chart state, asset loading, fallback rendering, and guard logging parity |
| Logs, terminal, diagnostics | Local dashboard logs and installer output | Service logs, terminal route, diagnostics, redaction, and test runner parity |
| LLM advisory | Provider/model settings mirrored | Python LLM prompt/config/local-model service route behavior |
| Startup, packaging, platform | Local CMake/Qt build path | Product packaging, startup suppression, platform metadata, and release smoke parity |

## Source layout

The `src/` folder is still being reorganized, but it already contains distinct slices such as:

- `TradingBotWindow.dashboard*.cpp`
- `TradingBotWindow.positions.cpp`
- `TradingBotWindow.chart.cpp`
- `TradingBotWindow.backtest.cpp`
- `TradingBotWindow.web.cpp`
- `TradingBotWindow.runtime.cpp`
- `BinanceRestClient.*`
- `BinanceWsClient.*`

## Build

Optional one-shot dependency setup:

```powershell
# Windows
./experiments/native-cpp/tools/install_cpp_dependencies.ps1
```

```bash
# macOS / Linux
chmod +x ./experiments/native-cpp/tools/install_cpp_dependencies.sh
./experiments/native-cpp/tools/install_cpp_dependencies.sh
```

Pinned versions used by the helper scripts:

```text
QtVersion         = 6.11.0
AqtInstallVersion = 3.3.0
VcpkgRef          = d0ba406f0e5352517386709dba49fbabf99a9e3c
```

Manual build:

```bash
cmake -S experiments/native-cpp -B build/binance_cpp
cmake --build build/binance_cpp
```

If Qt auto-detection fails, pass `-DQt6_DIR=/absolute/path/to/lib/cmake/Qt6`.

The helper scripts target `Qt 6.11.0` where the installer path supports it.
`CMakeLists.txt` keeps the minimum supported version at `Qt 6.10.3`, so existing
`6.10.3` kits still build while newer `6.11.x` kits are also accepted.

## Run

```bash
build/binance_cpp/Trading-Bot-C++
```

## Recommendation

Treat this workspace as the native-desktop experimentation and migration path. For day-to-day use, packaging, and the broadest current feature coverage, use the Python app in `Languages/Python`.
