## Trading Bot C++ Desktop Preview (Qt/C++23)

This directory contains a standalone Qt Widgets application that recreates the Trading Bot's **Backtest** tab UI using modern C++23. It is intended as the starting point for the multi-language re-platform effort requested for the project.

### Features

- Mirrors the layout of the Python backtest tab: markets selector, parameter form, indicator toggles, action buttons, status widgets, and a results table placeholder.
- Implements light interactions (custom interval parsing, pseudo status updates, mock bot active timer) so the UI feels alive even without a live backend.
- Uses native C++ Binance REST calls (Qt Network) for dashboard balance and symbol refresh.
- Includes a native Binance WebSocket client class (`BinanceWsClient`) for direct stream integration.
- Written with clean, modern C++ (RAII, `std::chrono`) and Qt 6 Widgets to align with the requested C++23/Qt toolchain.

### Building

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

Pinned versions installed by the script:

```powershell
QtVersion         = 6.10.2
AqtInstallVersion = 3.3.0
VcpkgRef          = c1f21baeaf7127c13ee141fe1bdaa49eed371c0c
```

1. Ensure Qt `6.10.2` with Widgets/Network is installed and available in your environment.
2. Configure and build with CMake:

```bash
cmake -S Languages/C++ -B build/binance_cpp
cmake --build build/binance_cpp
```

`CMakeLists.txt` requires `Qt6 6.10.2 EXACT`, so builds stay reproducible for future clones.
If auto-detection misses your Qt install, pass `-DQt6_DIR=/absolute/path/to/lib/cmake/Qt6`.

3. Run the demo executable:

```bash
build/binance_cpp/Trading-Bot-C++
```

The resulting window mirrors the Python UI and now uses native C++ exchange connectivity for the dashboard refresh actions.

### Next steps

- Hook the Qt controls to full backtesting/order-routing logic.
- Add indicator engine modules (TA-Lib, Eigen/xtensor, or custom SIMD implementations).
- Expand WebSocket stream handling (depth, kline, user-data) and reconciliation.
