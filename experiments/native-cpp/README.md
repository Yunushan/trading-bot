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
