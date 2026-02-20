## Binance Backtest Tab (Qt/C++23)

This directory contains a standalone Qt Widgets application that recreates the Binance Trading Bot's **Backtest** tab UI using modern C++23. It is intended as the starting point for the multi-language re-platform effort requested for the project.

### Features

- Mirrors the layout of the Python backtest tab: markets selector, parameter form, indicator toggles, action buttons, status widgets, and a results table placeholder.
- Implements light interactions (custom interval parsing, pseudo status updates, mock bot active timer) so the UI feels alive even without a live backend.
- Uses native C++ Binance REST calls (Qt Network) for dashboard balance and symbol refresh.
- Includes a native Binance WebSocket client class (`BinanceWsClient`) for direct stream integration.
- Written with clean, modern C++ (RAII, `std::chrono`) and Qt 6 Widgets to align with the requested C++23/Qt toolchain.

### Building

1. Ensure Qt 6.5+ with Widgets and Network is installed and available in your environment.
2. Configure and build with CMake:

```bash
cmake -S Languages/C++ -B build/binance_cpp -DCMAKE_PREFIX_PATH="path/to/Qt/6.x/gcc_64"
cmake --build build/binance_cpp
```

3. Run the demo executable:

```bash
build/binance_cpp/binance_backtest_tab
```

The resulting window mirrors the Python UI and now uses native C++ exchange connectivity for the dashboard refresh actions.

### Next steps

- Hook the Qt controls to full backtesting/order-routing logic.
- Add indicator engine modules (TA-Lib, Eigen/xtensor, or custom SIMD implementations).
- Expand WebSocket stream handling (depth, kline, user-data) and reconciliation.
