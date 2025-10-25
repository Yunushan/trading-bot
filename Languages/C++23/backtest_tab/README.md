## Binance Backtest Tab (Qt/C++23)

This directory contains a standalone Qt Widgets application that recreates the Binance Trading Bot's **Backtest** tab UI using modern C++23. It is intended as the starting point for the multi-language re-platform effort requested for the project.

### Features

- Mirrors the layout of the Python backtest tab: markets selector, parameter form, indicator toggles, action buttons, status widgets, and a results table placeholder.
- Implements light interactions (custom interval parsing, pseudo status updates, mock bot active timer) so the UI feels alive even without a live backend.
- Written with clean, modern C++ (RAII, `std::chrono`) and Qt 6 Widgets to align with the requested C++23/Qt toolchain.

### Building

1. Ensure Qt 6.5+ with Widgets is installed and available in your environment.
2. Configure and build with CMake:

```bash
cmake -S Languages/C++23/backtest_tab -B build/backtest_tab -DCMAKE_PREFIX_PATH="path/to/Qt/6.x/gcc_64"
cmake --build build/backtest_tab
```

3. Run the demo executable:

```bash
build/backtest_tab/binance_backtest_tab
```

The resulting window mirrors the Python UI and is ready for wiring into the actual trading engine logic.

### Next steps

- Hook the Qt controls to real backtesting logic (shared libraries, REST clients, etc.).
- Share configuration structures between Python and C++ via JSON schemas.
- Extend the C++ app with networking, threading, and exchange connectors as needed.
