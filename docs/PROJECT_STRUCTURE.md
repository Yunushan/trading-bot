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
- `Languages/Python/app/gui/window_shell.py` is now the authoritative desktop window shell, with `main_window.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/runtime/window/main_window_init_ui_runtime.py` is now the first extracted `main_window.py` UI-assembly slice
- `Languages/Python/app/gui/runtime/composition/bindings_runtime.py` is now the thin authoritative `main_window.py` class-binding/configuration entrypoint, with `binding_modules.py` and `binding_sections.py` carrying the internal composition loader and binding groups and `main_window_bindings_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/runtime/composition/module_state_runtime.py` is now the thin authoritative `main_window.py` constant/helper-alias module-state entrypoint, with `module_state_constants.py` and `module_state_payload.py` carrying the extracted constant catalog and payload-build helpers and `main_window_module_state_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/bootstrap/runtime_env.py` is now the authoritative bootstrap/runtime metadata module, with `app/preamble.py` left as a compatibility shim
- `Languages/Python/app/bootstrap/startup_window_suppression_cbt_runtime.py` now keeps the CBT startup-suppression orchestration surface, with shared state in `startup_window_suppression_cbt_state_runtime.py`, Win32 API/bootstrap setup in `startup_window_suppression_cbt_api_runtime.py`, the CBT callback in `startup_window_suppression_cbt_proc_runtime.py`, helper-cover management in `startup_window_suppression_cbt_cover_runtime.py`, thread-hook install helpers in `startup_window_suppression_cbt_install_runtime.py` and `startup_window_suppression_cbt_thread_runtime.py`, and teardown in `startup_window_suppression_cbt_cleanup_runtime.py`
- `Languages/Python/app/bootstrap/startup_window_suppression_winevent_runtime.py` now keeps the WinEvent startup-suppression orchestration surface, with shared state in `startup_window_suppression_winevent_state_runtime.py`, tracked-process helpers in `startup_window_suppression_winevent_pid_runtime.py`, window classification/hide helpers in `startup_window_suppression_winevent_window_runtime.py`, and polling helpers in `startup_window_suppression_winevent_poll_runtime.py`
- `Languages/Python/app/platform/windows_taskbar.py` is now a thin facade over `windows_taskbar_metadata_runtime.py`, `windows_taskbar_shortcut_runtime.py`, and `windows_taskbar_shared_runtime.py`
- `Languages/Python/app/gui/runtime/background_workers.py` and `Languages/Python/app/gui/runtime/strategy_workers.py` are now the authoritative GUI worker modules, with `app/workers.py` left as a compatibility shim
- `Languages/Python/app/integrations/exchanges/binance/positions/close_all_runtime.py` is now the authoritative Binance futures close-all helper, with `app/close_all.py` left as a compatibility shim
- `Languages/Python/app/gui/runtime/window/window_code_tab_suppression_runtime.py` is now the first extracted `window_runtime.py` slice for Windows code-tab suppression helpers
- `Languages/Python/app/gui/runtime/window/window_webengine_guard_runtime.py` now carries the extracted WebEngine/TradingView prewarm and window-guard helpers
- `Languages/Python/app/gui/runtime/window/bootstrap_runtime.py`, `init_ui_runtime.py`, `init_finalize_runtime.py`, and `window_events_runtime.py` now carry the extracted window bootstrap/UI/finalize/event helpers, with the corresponding `main_window_*` files kept as compatibility wrappers
- `Languages/Python/app/gui/runtime/window/log_runtime.py`, `portfolio_runtime.py`, `positions_runtime.py`, `startup_runtime.py`, and `state_init_runtime.py` now carry the extracted window-support helpers, with the corresponding `main_window_*` files kept as compatibility wrappers
- `Languages/Python/app/gui/runtime/window/runtime.py` now carries the main window-orchestration surface, with `main_window_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/runtime/window/positions_runtime.py` now carries the extracted window-side positions worker/filter/waiting-table helpers, with `main_window_positions_runtime.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/runtime/window/main_window_window_events_runtime.py` now carries the extracted native close detection and close/hide window-guard lifecycle helpers, with `window/main_window_runtime.py` keeping the window-runtime orchestration surface
- `Languages/Python/app/gui/chart/` now exposes short preferred module names such as `display_runtime.py`, `host_runtime.py`, `selection_runtime.py`, `tab_runtime.py`, and `view_runtime.py`
- The legacy `Languages/Python/app/gui/chart/main_window_chart_*` modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/backtest/` now exposes short preferred module names such as `bridge_runtime.py`, `execution_runtime.py`, `results_runtime.py`, `state_runtime.py`, `tab_runtime.py`, `template_runtime.py`, and `worker_runtime.py`
- The legacy `Languages/Python/app/gui/backtest/main_window_backtest_*` modules remain as compatibility wrappers while callers are migrated
  - `Languages/Python/app/gui/backtest/execution_runtime.py` now keeps the backtest execution facade, with runtime config in `backtest_execution_context_runtime.py`, normal backtest flow in `backtest_execution_run_runtime.py`, and scan flow in `backtest_execution_scan_runtime.py`
  - `Languages/Python/app/gui/backtest/tab_runtime.py` now keeps the backtest-tab orchestration surface, with shared tab config in `backtest_tab_context_runtime.py`, market controls in `backtest_tab_market_runtime.py`, parameter controls in `backtest_tab_params_runtime.py`, indicator controls in `backtest_tab_indicator_runtime.py`, and output/results UI in `backtest_tab_output_runtime.py`
  - `Languages/Python/app/gui/backtest/state_runtime.py` now keeps the backtest state/binding surface, with runtime constants in `backtest_state_context_runtime.py`, date coercion in `backtest_state_dates_runtime.py`, initial UI sync in `backtest_state_init_runtime.py`, symbol/interval list helpers in `backtest_state_lists_runtime.py`, and symbol refresh worker flow in `backtest_state_symbols_runtime.py`
- `Languages/Python/app/gui/runtime/ui/` now exposes short preferred module names such as `secondary_tabs_runtime.py`, `tab_runtime.py`, `theme_runtime.py`, `theme_styles.py`, and `ui_misc_runtime.py`
- The legacy `Languages/Python/app/gui/runtime/ui/main_window_*` modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/runtime/account/` now exposes short preferred module names `account_runtime.py`, `balance_runtime.py`, and `margin_runtime.py`
- `Languages/Python/app/gui/runtime/service/` now exposes short preferred module names `service_api_runtime.py`, `session_runtime.py`, and `status_runtime.py`
- The legacy `Languages/Python/app/gui/runtime/account/main_window_*` and `service/main_window_*` modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/shared/` now exposes short preferred module names such as `config_runtime.py`, `helper_runtime.py`, `ui_support.py`, and `web_embed.py`
- The legacy `Languages/Python/app/gui/shared/main_window_*` helper modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/trade/` now exposes short preferred module names such as `trade_runtime.py`, `signal_runtime.py`, and `signal_open_runtime.py`
- `Languages/Python/app/gui/trade/signal_close_runtime.py` is now a thin facade over `signal_close_allocations_runtime.py`, `signal_close_records_runtime.py`, and `signal_close_interval_runtime.py`
- The legacy `Languages/Python/app/gui/trade/main_window_trade*` modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/code/` now exposes short preferred module names `runtime.py` and `tab_runtime.py` for the main code-tab surfaces
- The legacy `Languages/Python/app/gui/code/main_window_code*.py` modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/code/code_language_ui.py` is now a thin facade over `code_language_ui_build_runtime.py`, `code_language_ui_selection_runtime.py`, and `code_language_ui_state_runtime.py`
- `Languages/Python/app/gui/code/code_language_launcher.py` is now a thin facade over `code_language_cpp_launcher_runtime.py`, `code_language_rust_launcher_runtime.py`, and `code_language_launcher_shared_runtime.py`
- `Languages/Python/app/gui/code/code_language_cpp_bundle_runtime.py` is now a thin facade over `code_language_cpp_bundle_cache_runtime.py`, `code_language_cpp_bundle_packaged_runtime.py`, `code_language_cpp_bundle_release_runtime.py`, and `code_language_cpp_bundle_install_runtime.py`
- `Languages/Python/app/gui/code/dependency_versions_cpp_runtime.py` is now a thin facade over `dependency_versions_cpp_shared_runtime.py`, `dependency_versions_cpp_probe_runtime.py`, `dependency_versions_cpp_latest_runtime.py`, and `dependency_versions_cpp_policy_runtime.py`
- `Languages/Python/app/gui/dashboard/` now exposes short preferred module names such as `actions_runtime.py`, `chart_runtime.py`, `header_runtime.py`, `indicator_runtime.py`, `log_runtime.py`, `markets_runtime.py`, `state_runtime.py`, and `strategy_runtime.py`
- The legacy `Languages/Python/app/gui/dashboard/main_window_dashboard_*` modules remain as compatibility wrappers while callers are migrated
- `Languages/Python/app/gui/chart/lightweight_widget.py` is now a thin facade over `lightweight_widget_assets.py` and `lightweight_widget_runtime.py`
- `Languages/Python/app/gui/chart/tradingview_widget.py` is now a thin facade over `tradingview_widget_assets.py` and `tradingview_widget_runtime.py`
- `Languages/Python/app/gui/chart/binance_web_widget.py` is now a thin facade over `binance_web_widget_helpers.py` and `binance_web_widget_runtime.py`
- `Languages/Python/app/gui/chart/chart_embed.py` is now a thin facade over `chart_embed_state_runtime.py` and `chart_embed_host_runtime.py`
- `Languages/Python/app/gui/chart/display_runtime.py` is now a thin facade over `display_render_runtime.py`, `display_payload_runtime.py`, and `display_load_runtime.py`
- `Languages/Python/app/gui/chart/chart_widgets.py` is now a thin facade over `simple_candlestick_widget.py` and `interactive_chart_view.py`
- `Languages/Python/app/gui/runtime/strategy/` now uses short authoritative modules such as `control_runtime.py`, `start_runtime.py`, `stop_runtime.py`, `override_runtime.py`, `controls_runtime.py`, `ui_runtime.py`, `stop_loss_runtime.py`, `indicator_runtime.py`, and `context_runtime.py`
- The legacy `Languages/Python/app/gui/runtime/strategy/main_window_*` modules remain as compatibility shims only and should not be used by new code
- `Languages/Python/app/gui/positions/` now exposes short preferred module names such as `actions_runtime.py`, `build_runtime.py`, `record_build_runtime.py`, `render_runtime.py`, `table_render_runtime.py`, `history_runtime.py`, `history_records_runtime.py`, `history_update_runtime.py`, `positions_runtime.py`, `tab_runtime.py`, `tracking_runtime.py`, and `worker_runtime.py`
- The legacy `Languages/Python/app/gui/positions/main_window_positions_*` helper modules still remain as compatibility shims and wrapper surfaces during migration
- `Languages/Python/app/gui/positions/positions_runtime.py` now carries the main positions binder/orchestration surface, with `main_window_positions.py` kept as a compatibility wrapper
  - Internal split: shared positions config/helper state now lives in `positions_context_runtime.py`, cumulative record aggregation in `positions_cumulative_runtime.py`, and manual refresh helpers in `positions_refresh_runtime.py`
- `Languages/Python/app/gui/positions/actions_runtime.py` is now a thin facade over `actions_context_runtime.py`, `actions_history_runtime.py`, `actions_state_runtime.py`, and `actions_close_runtime.py`
- `Languages/Python/app/gui/positions/record_build_runtime.py` now carries the extracted positions record seeding/merge helpers, with `main_window_positions_record_build_runtime.py` and `main_window_positions_build_runtime.py` kept as compatibility wrapper surfaces
- `Languages/Python/app/gui/positions/table_render_runtime.py` is now a thin authoritative entrypoint over `table_render_state_runtime.py`, `table_render_prepare_runtime.py`, and `table_render_rows_runtime.py`, with `main_window_positions_table_render_runtime.py` and `main_window_positions_render_runtime.py` kept as compatibility wrapper surfaces
- `Languages/Python/app/gui/positions/history_records_runtime.py` now keeps the per-trade history facade, with configuration state in `history_records_context_runtime.py`, entry-building in `history_records_entries_runtime.py`, grouping/deduping in `history_records_group_runtime.py`, and the entry-building internals split across `history_records_meta_runtime.py`, `history_records_allocations_runtime.py`, `history_records_trade_data_runtime.py`, and `history_records_emit_runtime.py`
- `Languages/Python/app/gui/positions/history_update_runtime.py` now keeps the history-mutation facade, with configuration state in `history_update_context_runtime.py`, exchange/live-position lookups in `history_update_lookup_runtime.py`, close-path orchestration in `history_update_close_runtime.py`, and the close helpers split into `history_update_snapshot_runtime.py`, `history_update_allocation_runtime.py`, and `history_update_registry_runtime.py`; the legacy `main_window_positions_history*.py` files remain compatibility wrappers
- `Languages/Python/app/gui/positions/tab_runtime.py` now carries the extracted positions-tab binder surface, with `main_window_positions_tab.py` kept as a compatibility wrapper
- `Languages/Python/app/gui/positions/worker_runtime.py` now carries the extracted positions polling worker, with `main_window_positions_worker.py` kept as a compatibility wrapper
- C++ source should trend toward `dashboard/`, `positions/`, `runtime/`, `chart/`, `backtest/`, and `net/`
- Long-form maintenance or contributor guidance should live in `docs/`, not the root README

For the Python implementation, the longer-term architecture should also separate:

- `Languages/Python/app/core/` for reusable trading-domain logic
- `Languages/Python/app/core/backtest/` as the first moved backtest package, with shared models in `models.py`, shared indicator helpers in `indicator_runtime.py`, `engine.py` kept as the stable `BacktestEngine` facade, internal engine splits in `engine_run_runtime.py`, `engine_data_runtime.py`, `engine_signal_runtime.py`, and `engine_simulation_runtime.py`, and `app/backtester.py` left as a compatibility shim
- `Languages/Python/app/core/indicators/` as the first moved indicator-math package, with `app/indicators.py` left as a compatibility shim
- `Languages/Python/app/core/positions/` as the first moved core package, with `app/position_guard.py` left as a compatibility shim
- `Languages/Python/app/core/strategy/` as the moved strategy-engine package, with `app/strategy.py` left as a compatibility shim
- `Languages/Python/app/core/strategy/orders/` now carries the moved signal-order runtime family, with the flat `app/strategy_signal_order*.py` modules and `app/strategy_signal_orders_runtime.py` left as the compatibility surface
- `Languages/Python/app/core/strategy/runtime/` now carries the moved cycle/runtime helper family, with the flat `app/strategy_runtime*.py`, `app/strategy_cycle_runtime.py`, `app/strategy_indicator_compute.py`, `app/strategy_signal_generation.py`, and `app/strategy_indicator_tracking.py` files left as compatibility shims
- `Languages/Python/app/core/strategy/runtime/strategy_cycle_risk_runtime.py` now keeps the cycle-risk orchestration surface, with RSI exits in `strategy_cycle_risk_rsi_runtime.py` and futures stop-loss/cache helpers in `strategy_cycle_risk_stop_runtime.py`
- `Languages/Python/app/core/strategy/runtime/strategy_cycle_risk_stop_runtime.py` now keeps the futures stop-loss orchestration surface, with price/cache state in `strategy_cycle_risk_stop_context_runtime.py`, cumulative stop-loss closes in `strategy_cycle_risk_stop_cumulative_runtime.py`, and per-leg stop-loss closes in `strategy_cycle_risk_stop_directional_runtime.py`
- `Languages/Python/app/core/strategy/positions/` now carries the moved guard/trade-book/position helper family, with the flat `app/strategy_indicator_guard.py`, `app/strategy_trade_book.py`, `app/strategy_position_state.py`, `app/strategy_position_close_runtime.py`, and `app/strategy_position_flip_runtime.py` files left as compatibility shims
  - `Languages/Python/app/core/strategy/positions/strategy_position_state.py` now keeps the bind surface, with leg-ledger mutation in `strategy_position_ledger_runtime.py`, indicator conflict handling in `strategy_position_conflict_runtime.py`, and futures margin/purge helpers in `strategy_position_futures_runtime.py`
- `Languages/Python/app/core/strategy/positions/strategy_close_opposite_runtime.py` now keeps the close-opposite orchestration surface, with common refresh/goal helpers in `strategy_close_opposite_common_runtime.py`, ledger-close helpers in `strategy_close_opposite_ledger_runtime.py`, indicator-scope helpers in `strategy_close_opposite_indicator_runtime.py`, and symbol-level exchange closes in `strategy_close_opposite_exchange_runtime.py`
- `Languages/Python/app/core/strategy/orders/strategy_indicator_order_build_runtime.py` now keeps the indicator-order build facade, with shared exchange/cleanup helpers in `strategy_indicator_order_common_runtime.py`, directional builds in `strategy_indicator_order_directional_runtime.py`, fallback builds in `strategy_indicator_order_fallback_runtime.py`, hedge-close builds in `strategy_indicator_order_hedge_runtime.py`, and `orders/strategy_indicator_order_context_runtime.py` keeping the extracted indicator-order context preparation helpers while `strategy_signal_order_collect_runtime.py` keeps the collection/bind surface
- `Languages/Python/app/integrations/` for exchange and persistence adapters
- `Languages/Python/app/integrations/exchanges/binance/` as the first moved exchange package, now carrying the live Binance support modules internally, with `app/binance_wrapper.py` left as a compatibility shim
- `Languages/Python/app/integrations/exchanges/binance/account/account_data.py` now keeps the bind surface only, with cache/auth fallbacks in `account_cache_runtime.py`, spot/balance shaping in `account_balance_runtime.py`, and futures balance/snapshot helpers in `account_futures_runtime.py`
- `Languages/Python/app/integrations/exchanges/binance/clients/sdk_clients.py` now keeps the stable SDK adapter export surface, with shared SDK helpers in `sdk_common_runtime.py` and concrete adapters in `sdk_usds_futures_client.py`, `sdk_coin_futures_client.py`, and `sdk_spot_client.py`
- `Languages/Python/app/service/` for headless backend/runtime/API work
- `Languages/Python/app/service/runners/` for headless lifecycle/runtime coordinators
- `Languages/Python/app/service/runners/backtest_executor.py` as the first service-owned extracted workload reusing the shared backtest engine, with request parsing in `backtest_executor_request_runtime.py`, snapshot publishing in `backtest_executor_snapshot_runtime.py`, and worker-thread execution in `backtest_executor_worker_runtime.py`
- `Languages/Python/app/desktop/` for desktop-only bootstrap and client adapters
- `Languages/Python/app/desktop/service_bridge.py` now keeps the desktop-service bind surface, with client/factory helpers in `service_bridge_client_runtime.py`, control dispatch in `service_bridge_control_runtime.py`, snapshot sync/query helpers in `service_bridge_snapshot_runtime.py`, and API host/config helpers in `service_bridge_host_runtime.py`
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
