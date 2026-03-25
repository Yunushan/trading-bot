# Project Structure

This repository is a multi-implementation trading-bot workspace. The intent is to keep source code stable and predictable while allowing local build outputs to stay disposable.

## Stable source directories

- `Languages/Python/`: primary end-user desktop app
- `Languages/C++/`: native Qt desktop implementation
- `Languages/Rust/`: Rust workspace with multiple desktop shells and shared crates
- `assets/`: shared icons and branding assets
- `tools/`: repo-level maintenance scripts
- `docs/`: repository and development documentation

## Generated or local-only directories

These are workspace artifacts, not canonical source:

- `build/`
- `dist/`
- `dist_enduser/`
- `.venv/`
- root-level `Trading-Bot-*.exe`

They are ignored by Git and should be treated as disposable.

## Current organization guidance

The repository is intentionally language-first today, but feature code inside each implementation should be grouped by domain where possible.

Preferred direction:

- Python GUI already has feature subpackages at `Languages/Python/app/gui/positions/`, `Languages/Python/app/gui/backtest/`, `Languages/Python/app/gui/chart/`, `Languages/Python/app/gui/code/`, `Languages/Python/app/gui/dashboard/`, `Languages/Python/app/gui/trade/`, `Languages/Python/app/gui/shared/`, and `Languages/Python/app/gui/runtime/`
- Python GUI code should trend toward feature folders such as `dashboard/`, `chart/`, `positions/`, `backtest/`, `code/`, `trade/`, `shared/`, and `runtime/`
- `Languages/Python/app/gui/runtime/main_window_init_ui_runtime.py` is now the first extracted `main_window.py` UI-assembly slice
- `Languages/Python/app/gui/runtime/main_window_bindings_runtime.py` is now the extracted `main_window.py` class-binding/configuration slice
- `Languages/Python/app/gui/runtime/main_window_module_state_runtime.py` is now the extracted `main_window.py` constant/helper-alias module-state slice
- `Languages/Python/app/gui/runtime/window_code_tab_suppression_runtime.py` is now the first extracted `window_runtime.py` slice for Windows code-tab suppression helpers
- `Languages/Python/app/gui/runtime/window_webengine_guard_runtime.py` now carries the extracted WebEngine/TradingView prewarm and window-guard helpers, with `window_runtime.py` left as a compatibility shim
- `Languages/Python/app/gui/runtime/main_window_window_events_runtime.py` now carries the extracted native close detection and close/hide window-guard lifecycle helpers, with `main_window_runtime.py` keeping the compatibility surface
- `Languages/Python/app/gui/runtime/main_window_start_strategy_runtime.py` now carries the extracted start-engine lifecycle and loop-build helpers, with `main_window_control_runtime.py` keeping the control-surface wrappers
- `Languages/Python/app/gui/runtime/main_window_stop_strategy_runtime.py` now carries the extracted stop-engine and close-all lifecycle helpers, with `main_window_control_runtime.py` keeping the control-surface wrappers
- C++ source should trend toward `dashboard/`, `positions/`, `runtime/`, `chart/`, `backtest/`, and `net/`
- Long-form maintenance or contributor guidance should live in `docs/`, not the root README

For the Python implementation, the longer-term architecture should also separate:

- `Languages/Python/app/core/` for reusable trading-domain logic
- `Languages/Python/app/core/backtest/` as the first moved backtest package, with `app/backtester.py` left as a compatibility shim
- `Languages/Python/app/core/indicators/` as the first moved indicator-math package, with `app/indicators.py` left as a compatibility shim
- `Languages/Python/app/core/positions/` as the first moved core package, with `app/position_guard.py` left as a compatibility shim
- `Languages/Python/app/core/strategy/` as the moved strategy-engine package, with `app/strategy.py` left as a compatibility shim
- `Languages/Python/app/core/strategy/` also now carries the moved signal-order runtime family, with the flat `app/strategy_signal_order*.py` modules and `app/strategy_signal_orders_runtime.py` left as compatibility shims
- `Languages/Python/app/core/strategy/` also now carries the moved cycle/runtime helper family, with the flat `app/strategy_runtime*.py`, `app/strategy_cycle_runtime.py`, `app/strategy_indicator_compute.py`, `app/strategy_signal_generation.py`, and `app/strategy_indicator_tracking.py` files left as compatibility shims
- `Languages/Python/app/core/strategy/` also now carries the moved guard/trade-book/position helper family, with the flat `app/strategy_indicator_guard.py`, `app/strategy_trade_book.py`, `app/strategy_position_state.py`, `app/strategy_position_close_runtime.py`, and `app/strategy_position_flip_runtime.py` files left as compatibility shims
- `Languages/Python/app/integrations/` for exchange and persistence adapters
- `Languages/Python/app/integrations/exchanges/binance/` as the first moved exchange package, now carrying the live Binance support modules internally, with `app/binance_wrapper.py` left as a compatibility shim
- `Languages/Python/app/service/` for headless backend/runtime/API work
- `Languages/Python/app/service/runners/` for headless lifecycle/runtime coordinators
- `Languages/Python/app/service/runners/backtest_executor.py` as the first service-owned extracted workload reusing the shared backtest engine
- `Languages/Python/app/desktop/` for desktop-only bootstrap and client adapters
- `Languages/Python/app/desktop/bootstrap/` as the moved desktop-bootstrap implementation, with `Languages/Python/main.py` kept as the stable public launcher
- `Languages/Python/app/desktop/adapters/` for embedded or future remote desktop service clients
- `Languages/Python/clients/web/` for the thin browser dashboard and future web-client assets
- `Languages/Python/clients/web/modules/` now carries the split browser-dashboard state, render, and transport helpers, with `clients/web/app.js` reduced to the top-level coordinator
- `Languages/Python/clients/mobile/` for the thin Expo-based native Android/iOS client
- `docker/` for optional backend-only container packaging

That split is the foundation for optional Docker support and future web/mobile clients. See `docs/PLATFORM_EXPANSION_PLAN.md` for the step-by-step migration path.

## What should stay small at the repo root

The root should remain focused on:

- project identity
- quick-start documentation
- shared assets
- top-level tooling

If a file is mainly for contributors, maintenance, or release procedure, prefer `docs/` or `tools/`.
