# Trading Bot C++ Workspace

This directory contains the native Qt/C++ desktop path for the trading-bot workspace.

Today it is a C++ desktop preview and re-platforming path, not the primary end-user application. The main production-facing implementation is still the Python/PyQt app in `Languages/Python`.

## Current role

- Native Qt Widgets desktop shell
- C++23 / Qt 6 build target
- Dashboard, chart, positions, backtest, and web/runtime slices under active restructuring
- Native exchange connectivity experiments, with Binance as the current implemented connector path inside the C++ tree

## Current status

| Area | Status | Notes |
| --- | --- | --- |
| Native desktop shell | Active development | Real source tree exists and builds locally |
| Full feature parity with Python app | Not complete | Still a preview/re-platform path |
| Primary exchange implementation | Binance | Current connector code in this workspace is Binance-specific |
| Cross-platform Qt build path | Supported for local builds | Windows, macOS, and Linux toolchains are expected |

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
./Languages/C++/tools/install_cpp_dependencies.ps1
```

```bash
# macOS / Linux
chmod +x ./Languages/C++/tools/install_cpp_dependencies.sh
./Languages/C++/tools/install_cpp_dependencies.sh
```

Pinned versions used by the helper scripts:

```text
QtVersion         = 6.10.2
AqtInstallVersion = 3.3.0
VcpkgRef          = c1f21baeaf7127c13ee141fe1bdaa49eed371c0c
```

Manual build:

```bash
cmake -S Languages/C++ -B build/binance_cpp
cmake --build build/binance_cpp
```

If Qt auto-detection fails, pass `-DQt6_DIR=/absolute/path/to/lib/cmake/Qt6`.

`CMakeLists.txt` currently requires `Qt6 6.10.2 EXACT` so the toolchain stays reproducible.

## Run

```bash
build/binance_cpp/Trading-Bot-C++
```

## Recommendation

Treat this workspace as the native-desktop experimentation and migration path. For day-to-day use, packaging, and the broadest current feature coverage, use the Python app in `Languages/Python`.
