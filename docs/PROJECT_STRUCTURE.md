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
- `Languages/Python/app/gui/runtime/window/main_window_init_ui_runtime.py` is now the first extracted `main_window.py` UI-assembly slice
- `Languages/Python/app/gui/runtime/composition/bindings_runtime.py` is now the authoritative `main_window.py` class-binding/configuration slice, with `main_window_bindings_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/runtime/composition/module_state_runtime.py` is now the authoritative `main_window.py` constant/helper-alias module-state slice, with `main_window_module_state_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/bootstrap/runtime_env.py` is now the authoritative bootstrap/runtime metadata module, with `app/preamble.py` left as a compatibility shim
- `Languages/Python/app/gui/runtime/background_workers.py` and `Languages/Python/app/gui/runtime/strategy_workers.py` are now the authoritative GUI worker modules, with `app/workers.py` left as a compatibility shim
- `Languages/Python/app/integrations/exchanges/binance/positions/close_all_runtime.py` is now the authoritative Binance futures close-all helper, with `app/close_all.py` left as a compatibility shim
- `Languages/Python/app/gui/runtime/window/window_code_tab_suppression_runtime.py` is now the first extracted `window_runtime.py` slice for Windows code-tab suppression helpers
- `Languages/Python/app/gui/runtime/window/window_webengine_guard_runtime.py` now carries the extracted WebEngine/TradingView prewarm and window-guard helpers
- `Languages/Python/app/gui/runtime/window/bootstrap_runtime.py`, `init_ui_runtime.py`, `init_finalize_runtime.py`, and `window_events_runtime.py` now carry the extracted window bootstrap/UI/finalize/event helpers, with the corresponding `main_window_*` files kept as compatibility wrappers
- `Languages/Python/app/gui/runtime/window/log_runtime.py`, `portfolio_runtime.py`, `positions_runtime.py`, `startup_runtime.py`, and `state_init_runtime.py` now carry the extracted window-support helpers, with the corresponding `main_window_*` files kept as compatibility wrappers
- `Languages/Python/app/gui/runtime/window/positions_runtime.py` now carries the extracted window-side positions worker/filter/waiting-table helpers, with `main_window_positions_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/runtime/window/main_window_window_events_runtime.py` now carries the extracted native close detection and close/hide window-guard lifecycle helpers, with `window/main_window_runtime.py` keeping the window-runtime orchestration surface
- `Languages/Python/app/gui/runtime/strategy/` now uses short authoritative modules such as `control_runtime.py`, `start_runtime.py`, `stop_runtime.py`, `override_runtime.py`, `controls_runtime.py`, `ui_runtime.py`, `stop_loss_runtime.py`, `indicator_runtime.py`, and `context_runtime.py`
- The legacy `Languages/Python/app/gui/runtime/strategy/main_window_*` modules remain as compatibility shims only and should not be used by new code
- `Languages/Python/app/gui/positions/` now exposes short preferred module names such as `actions_runtime.py`, `build_runtime.py`, `record_build_runtime.py`, `render_runtime.py`, `table_render_runtime.py`, `history_runtime.py`, `history_records_runtime.py`, `history_update_runtime.py`, `positions_runtime.py`, `tab_runtime.py`, `tracking_runtime.py`, and `worker_runtime.py`
- The legacy `Languages/Python/app/gui/positions/main_window_positions_*` helper modules still remain as compatibility shims and wrapper surfaces during migration
- `Languages/Python/app/gui/positions/positions_runtime.py` now carries the main positions binder/orchestration surface, with `main_window_positions.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/positions/record_build_runtime.py` now carries the extracted positions record seeding/merge helpers, with `main_window_positions_record_build_runtime.py` and `main_window_positions_build_runtime.py` kept as compatibility wrapper surfaces
- `Languages/Python/app/gui/positions/table_render_runtime.py` now carries the extracted positions table-render implementation, with `main_window_positions_table_render_runtime.py` and `main_window_positions_render_runtime.py` kept as compatibility wrapper surfaces
- `Languages/Python/app/gui/positions/history_records_runtime.py` and `history_update_runtime.py` now carry the extracted per-trade history shaping and mutation helpers, with `main_window_positions_history_records_runtime.py` and `main_window_positions_history_update_runtime.py` kept as compatibility wrappers and `main_window_positions_history_runtime.py` kept as the history wrapper surface
- `Languages/Python/app/gui/positions/tab_runtime.py` now carries the extracted positions-tab binder surface, with `main_window_positions_tab.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/positions/worker_runtime.py` now carries the extracted positions polling worker, with `main_window_positions_worker.py` kept as a compatibility wrapper
- C++ source should trend toward `dashboard/`, `positions/`, `runtime/`, `chart/`, `backtest/`, and `net/`
- Long-form maintenance or contributor guidance should live in `docs/`, not the root README

For the Python implementation, the longer-term architecture should also separate:

- `Languages/Python/app/core/` for reusable trading-domain logic
- `Languages/Python/app/core/backtest/` as the first moved backtest package, with shared models in `models.py`, shared indicator helpers in `indicator_runtime.py`, the main engine in `engine.py`, and `app/backtester.py` left as a compatibility shim
- `Languages/Python/app/core/indicators/` as the first moved indicator-math package, with `app/indicators.py` left as a compatibility shim
- `Languages/Python/app/core/positions/` as the first moved core package, with `app/position_guard.py` left as a compatibility shim
- `Languages/Python/app/core/strategy/` as the moved strategy-engine package, with `app/strategy.py` left as a compatibility shim
- `Languages/Python/app/core/strategy/orders/` now carries the moved signal-order runtime family, with the flat `app/strategy_signal_order*.py` modules and `app/strategy_signal_orders_runtime.py` left as the compatibility surface
- `Languages/Python/app/core/strategy/runtime/` now carries the moved cycle/runtime helper family, with the flat `app/strategy_runtime*.py`, `app/strategy_cycle_runtime.py`, `app/strategy_indicator_compute.py`, `app/strategy_signal_generation.py`, and `app/strategy_indicator_tracking.py` files left as compatibility shims
- `Languages/Python/app/core/strategy/runtime/strategy_cycle_risk_runtime.py` now carries the extracted futures exit/stop-loss/cache-loading risk section, with `strategy_cycle_runtime.py` keeping the cycle orchestration surface
- `Languages/Python/app/core/strategy/positions/` now carries the moved guard/trade-book/position helper family, with the flat `app/strategy_indicator_guard.py`, `app/strategy_trade_book.py`, `app/strategy_position_state.py`, `app/strategy_position_close_runtime.py`, and `app/strategy_position_flip_runtime.py` files left as compatibility shims
- `Languages/Python/app/core/strategy/positions/strategy_close_opposite_runtime.py` now carries the extracted close-opposite/flip execution helper, with `strategy_position_flip_runtime.py` keeping the reconciliation/merge/bind surface
- `Languages/Python/app/core/strategy/orders/strategy_indicator_order_build_runtime.py` now carries the extracted directional/fallback/hedge indicator-order builders, and `orders/strategy_indicator_order_context_runtime.py` now carries the extracted indicator-order context preparation helpers, with `strategy_signal_order_collect_runtime.py` keeping the collection/bind surface
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

## Python import rules

Use the canonical package paths for new code.

- Import bootstrap/runtime metadata from `app.bootstrap.runtime_env`, not `app.preamble`
- Import GUI worker helpers from `app.gui.runtime.background_workers` or `app.gui.runtime.strategy_workers`, not `app.workers`
- Import Binance futures close-all helpers from `app.integrations.exchanges.binance.positions.close_all_runtime`, not `app.close_all`
- Import strategy GUI runtime helpers from the short `app.gui.runtime.strategy.*` module names, not the `main_window_*` compatibility wrappers
- Import positions GUI helpers from the short `app.gui.positions.*_runtime` module names and `app.gui.positions.tab_runtime`, not the `main_window_positions_*` compatibility wrappers

## What should stay small at the repo root

The root should remain focused on:

- project identity
- quick-start documentation
- shared assets
- top-level tooling

If a file is mainly for contributors, maintenance, or release procedure, prefer `docs/` or `tools/`.
