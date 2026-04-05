# Platform Expansion Plan

This document defines the recommended migration path for turning the current desktop-first trading bot into a project that can also support:

- optional Docker deployment
- a web GUI
- Android/iOS thin clients

The key rule is:

> Docker is optional. The architecture change is mandatory.

The current repo can stay desktop-first while growing a headless backend and additional clients around the same core logic.

## Current reality

Today the main Python implementation is centered around these files:

- `apps/desktop-pyqt/main.py`: canonical desktop launcher delegating into the Python workspace
- `apps/service-api/main.py`: canonical service/API launcher delegating into the Python workspace
- `Languages/Python/main.py`: desktop bootstrap and platform-specific startup behavior
- `Languages/Python/app/gui/window_shell.py`: current PyQt desktop application shell
- `Languages/Python/app/gui/main_window.py`: compatibility wrapper for the desktop window shell
- `Languages/Python/trading_core/strategy.py`: canonical reusable strategy surface
- `Languages/Python/app/integrations/exchanges/binance/__init__.py`: canonical exchange integration surface
- `Languages/Python/trading_core/backtest.py`: canonical reusable backtest surface

This means the project already has the raw pieces needed for expansion, but they are still too close to the desktop process.

## Target architecture

The recommended direction is to split the Python implementation into these layers:

```text
apps/
  desktop-pyqt/
  service-api/
  web-dashboard/
  mobile-client/
Languages/Python/
  app/
    core/
      strategy/
      risk/
      indicators/
      positions/
      backtest/
      models/
    integrations/
      exchanges/
        binance/
      storage/
      notifications/
    service/
      api/
      runners/
      jobs/
      schemas/
      auth/
    desktop/
      bootstrap/
      gui/
      presenters/
      adapters/
    shared/
      config/
      logging/
      utils/
docker/
  backend.Dockerfile
  compose.yaml
```

## What each layer should own

### `app/core/`

Pure business logic with no PyQt dependency and no HTTP/API dependency.

Put here:

- strategy execution rules
- signal generation
- risk and stop-loss rules
- position state logic
- backtest orchestration
- shared domain models

This layer should be reusable by:

- desktop app
- headless backend
- tests

### `app/integrations/`

External systems and adapters.

Put here:

- Binance clients and wrappers
- persistence adapters
- file-based config storage
- future Redis/Postgres adapters
- notification hooks

The first concrete exchange move is already in place: the Binance integration package now lives under `app/integrations/exchanges/binance/`, with the live support modules using package-local imports internally and the flat `app/binance_wrapper.py` shim now removed.

### `app/service/`

The headless backend runtime.

Put here:

- FastAPI app
- websocket/SSE event streaming
- service-level orchestration
- bot runners
- scheduled jobs
- request/response schemas
- auth/session logic

This is the layer used by web and mobile clients.

### `app/desktop/`

Desktop-only behavior.

Put here:

- Qt bootstrap
- Windows-specific startup behavior
- PyQt widgets and tabs
- desktop presenters/adapters that call backend/core services

This is where the current desktop bootstrap and GUI should gradually move.

### `apps/web-dashboard/`

Optional browser-based frontend.

Use this only after the backend exists.

The current thin dashboard should keep trending toward small browser modules, with shared state, render helpers, and API transport split out of the top-level browser bootstrap file.

### `apps/mobile-client/`

Optional native thin client for Android/iOS.

Do not move exchange or broker secrets here. Mobile must talk to the backend only.

### `docker/`

Optional deployment packaging.

Docker should package the backend service, not the current PyQt GUI.

## Recommended migration mapping from current files

Start by treating these current or recently removed file families as the seeds of the new layers:

- `Languages/Python/app/strategy.py`
  Current state: removed flat compatibility shim
  Canonical surface: `Languages/Python/trading_core/strategy.py`
  Implementation home: `app/core/strategy/`

- `Languages/Python/app/strategy_signal_order*.py`
  Current state: removed compatibility wrappers
  New home: `app/core/strategy/orders/strategy_signal_order*.py`

- `Languages/Python/app/strategy_signal_orders_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/orders/strategy_signal_orders_runtime.py`

- `Languages/Python/app/strategy_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/runtime/strategy_runtime.py`

- `Languages/Python/app/strategy_runtime_support.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/runtime/strategy_runtime_support.py`

- `Languages/Python/app/strategy_cycle_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/runtime/strategy_cycle_runtime.py`
  Current split: cycle-risk orchestration in `app/core/strategy/runtime/strategy_cycle_risk_runtime.py`, RSI exits in `strategy_cycle_risk_rsi_runtime.py`, and futures stop-loss orchestration in `strategy_cycle_risk_stop_runtime.py`, with price/cache state in `strategy_cycle_risk_stop_context_runtime.py`, cumulative stop-loss closes in `strategy_cycle_risk_stop_cumulative_runtime.py`, and per-leg stop-loss closes in `strategy_cycle_risk_stop_directional_runtime.py`

- `Languages/Python/app/strategy_indicator_compute.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/runtime/strategy_indicator_compute.py`

- `Languages/Python/app/strategy_signal_generation.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/runtime/strategy_signal_generation.py`

- `Languages/Python/app/strategy_indicator_tracking.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/runtime/strategy_indicator_tracking.py`

- `Languages/Python/app/strategy_indicator_guard.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/positions/strategy_indicator_guard.py`

- `Languages/Python/app/strategy_trade_book.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/positions/strategy_trade_book.py`

- `Languages/Python/app/strategy_position_state.py`
    Current state: removed compatibility wrapper
    New home: `app/core/strategy/positions/strategy_position_state.py`
    Current split: bind surface in `strategy_position_state.py`, leg-ledger mutation in `strategy_position_ledger_runtime.py`, indicator conflict handling in `strategy_position_conflict_runtime.py`, and futures margin/purge helpers in `strategy_position_futures_runtime.py`

- `Languages/Python/app/strategy_position_close_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/positions/strategy_position_close_runtime.py`

- `Languages/Python/app/strategy_position_flip_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/positions/strategy_position_flip_runtime.py`
  Current split: close-opposite execution helper in `app/core/strategy/positions/strategy_close_opposite_runtime.py`

- `Languages/Python/app/strategy_signal_order_collect_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/orders/strategy_signal_order_collect_runtime.py`
  Current split: indicator-order build facade in `app/core/strategy/orders/strategy_indicator_order_build_runtime.py`, with shared exchange/cleanup helpers in `strategy_indicator_order_common_runtime.py`, directional/fallback/hedge builders in `strategy_indicator_order_directional_runtime.py`, `strategy_indicator_order_fallback_runtime.py`, and `strategy_indicator_order_hedge_runtime.py`, plus indicator-order context helpers in `app/core/strategy/orders/strategy_indicator_order_context_runtime.py`

- `Languages/Python/app/strategy_position_flip_runtime.py`
  Current state: removed compatibility wrapper
  New home: `app/core/strategy/positions/strategy_position_flip_runtime.py`
  Current split: close-opposite orchestration in `app/core/strategy/positions/strategy_close_opposite_runtime.py`, with internal helpers in `strategy_close_opposite_common_runtime.py`, `strategy_close_opposite_ledger_runtime.py`, `strategy_close_opposite_indicator_runtime.py`, and `strategy_close_opposite_exchange_runtime.py`

- `Languages/Python/trading_core/backtest.py`
  Current state: canonical reusable surface
  Implementation home: `app/core/backtest/engine.py`
  Current split: request/result models in `app/core/backtest/models.py`, indicator helpers in `app/core/backtest/indicator_runtime.py`, and internal engine helpers in `app/core/backtest/engine_run_runtime.py`, `app/core/backtest/engine_data_runtime.py`, `app/core/backtest/engine_signal_runtime.py`, and `app/core/backtest/engine_simulation_runtime.py`

- `Languages/Python/app/gui/positions/main_window_positions_build_runtime.py`
  Current state: GUI-facing wrapper surface
  New home for record shaping helpers: `app/gui/positions/record_build_runtime.py`

- `Languages/Python/app/gui/positions/main_window_positions_render_runtime.py`
  Current state: GUI-facing wrapper surface
  New home for table rendering: `app/gui/positions/table_render_runtime.py`
  Internal split: `app/gui/positions/table_render_state_runtime.py`, `app/gui/positions/table_render_prepare_runtime.py`, and `app/gui/positions/table_render_rows_runtime.py`

- `Languages/Python/app/gui/positions/main_window_positions_history_runtime.py`
  Current state: wrapper surface for positions history
  New home for per-trade history shaping: `app/gui/positions/history_records_runtime.py`
  Current split: configuration state in `app/gui/positions/history_records_context_runtime.py`, entry-building in `app/gui/positions/history_records_entries_runtime.py`, grouping/deduping in `app/gui/positions/history_records_group_runtime.py`, and entry-building internals in `history_records_meta_runtime.py`, `history_records_allocations_runtime.py`, `history_records_trade_data_runtime.py`, and `history_records_emit_runtime.py`
  Related mutation split: `app/gui/positions/history_update_runtime.py` now keeps the update facade, with configuration state in `history_update_context_runtime.py`, exchange/live-position lookups in `history_update_lookup_runtime.py`, close-path orchestration in `history_update_close_runtime.py`, and close helpers in `history_update_snapshot_runtime.py`, `history_update_allocation_runtime.py`, and `history_update_registry_runtime.py`

- `Languages/Python/trading_core/indicators.py`
  Current state: canonical reusable surface
  Implementation home: `app/core/indicators/__init__.py`

- `Languages/Python/trading_core/positions.py`
  Current state: canonical reusable surface
  Implementation home: `app/core/positions/guard.py`

- `Languages/Python/app/binance_wrapper.py`
  Current state: removed flat compatibility shim
  Canonical surface: `app/integrations/exchanges/binance/__init__.py`
  Implementation home: `app/integrations/exchanges/binance/wrapper.py`
  Current split: account binding surface in `app/integrations/exchanges/binance/account/account_data.py`, with internal account helpers in `account_cache_runtime.py`, `account_balance_runtime.py`, and `account_futures_runtime.py`

- `Languages/Python/app/integrations/exchanges/binance/clients/sdk_clients.py`
  Current state: stable SDK adapter export surface
  New home: `app/integrations/exchanges/binance/clients/sdk_clients.py`
  Current split: shared SDK coercion/serialization helpers in `sdk_common_runtime.py`, with concrete adapters in `sdk_usds_futures_client.py`, `sdk_coin_futures_client.py`, and `sdk_spot_client.py`

- `Languages/Python/app/desktop/service_bridge.py`
  Current state: desktop bind surface
  Current split: client/factory helpers in `app/desktop/service_bridge_client_runtime.py`, control dispatch in `app/desktop/service_bridge_control_runtime.py`, snapshot sync/query helpers in `app/desktop/service_bridge_snapshot_runtime.py`, and API host/config helpers in `app/desktop/service_bridge_host_runtime.py`

- `Languages/Python/app/service/runners/backtest_executor.py`
  Current state: service-owned workload adapter
  Current split: request coercion/build helpers in `app/service/runners/backtest_executor_request_runtime.py`, snapshot publishing helpers in `app/service/runners/backtest_executor_snapshot_runtime.py`, and worker-thread execution in `app/service/runners/backtest_executor_worker_runtime.py`

- `Languages/Python/app/gui/window_shell.py`
  Future target: `app/desktop/gui/`

- `Languages/Python/app/gui/main_window.py`
  Current state: compatibility wrapper for `app/gui/window_shell.py`

- `Languages/Python/app/desktop/bootstrap/main.py`
  Current state: moved desktop-bootstrap implementation behind the public launcher

- `Languages/Python/app/bootstrap/startup_window_suppression_cbt_runtime.py`
    Current state: CBT startup-suppression orchestration surface used by desktop bootstrap
    Current split: shared state in `startup_window_suppression_cbt_state_runtime.py`, Win32 API/bootstrap setup in `startup_window_suppression_cbt_api_runtime.py`, the CBT callback in `startup_window_suppression_cbt_proc_runtime.py`, window classification helpers in `startup_window_suppression_cbt_window_runtime.py`, helper-cover management in `startup_window_suppression_cbt_cover_runtime.py`, thread-hook install helpers in `startup_window_suppression_cbt_install_runtime.py` and `startup_window_suppression_cbt_thread_runtime.py`, and teardown in `startup_window_suppression_cbt_cleanup_runtime.py`

- `Languages/Python/app/bootstrap/startup_window_suppression_winevent_runtime.py`
  Current state: WinEvent startup-suppression orchestration surface used by desktop bootstrap
  Current split: shared state in `startup_window_suppression_winevent_state_runtime.py`, tracked-process helpers in `startup_window_suppression_winevent_pid_runtime.py`, window classification/hide helpers in `startup_window_suppression_winevent_window_runtime.py`, and polling helpers in `startup_window_suppression_winevent_poll_runtime.py`

- `Languages/Python/app/gui/runtime/window/main_window_init_ui_runtime.py`
  Current state: first extracted `main_window.py` UI-assembly helper

- `Languages/Python/app/gui/runtime/composition/bindings_runtime.py`
  Current state: authoritative extracted `main_window.py` class-binding/configuration entrypoint, with `binding_modules.py` and `binding_sections.py` carrying the internal composition loader/binder split

- `Languages/Python/app/gui/runtime/composition/module_state_runtime.py`
  Current state: authoritative extracted `main_window.py` constant/helper-alias entrypoint, with `module_state_constants.py` and `module_state_payload.py` carrying the internal constant catalog/payload-builder split

- `Languages/Python/app/gui/runtime/window/window_code_tab_suppression_runtime.py`
  Current state: first extracted `window_runtime.py` slice for code-tab suppression on Windows

- `Languages/Python/app/gui/runtime/window/window_webengine_guard_runtime.py`
  Current state: extracted `window_runtime.py` slice for WebEngine/TradingView prewarm and guard behavior

- `Languages/Python/app/gui/runtime/window/bootstrap_runtime.py`, `init_ui_runtime.py`, `init_finalize_runtime.py`, and `window_events_runtime.py`
  Current state: extracted `main_window.py` and `main_window_runtime.py` slices for bootstrap binding, initial tab assembly, final UI setup, and close/hide window-event behavior, with the matching `main_window_*` files left as compatibility wrappers

- `Languages/Python/app/gui/runtime/window/log_runtime.py`, `portfolio_runtime.py`, `positions_runtime.py`, `startup_runtime.py`, and `state_init_runtime.py`
  Current state: extracted `main_window_runtime.py` and bootstrap-support slices for log buffering, portfolio summaries, positions helper wiring, startup flags, and state initialization, with the matching `main_window_*` files left as compatibility wrappers

- `Languages/Python/app/gui/runtime/window/runtime.py`
  Current state: preferred main window-orchestration module, with `main_window_runtime.py` left as a compatibility wrapper

- `Languages/Python/app/gui/runtime/window/positions_runtime.py`
  Current state: extracted `main_window_runtime.py` slice for positions worker reconfiguration and waiting-position table helpers, with `main_window_positions_runtime.py` left as a compatibility wrapper

- `Languages/Python/app/gui/dashboard/actions_runtime.py`, `chart_runtime.py`, `header_runtime.py`, `indicator_runtime.py`, `log_runtime.py`, `markets_runtime.py`, `state_runtime.py`, and `strategy_runtime.py`
  Current state: preferred dashboard helper modules, with the `main_window_dashboard_*` files in the same package left as compatibility wrappers during migration

- `Languages/Python/app/gui/chart/display_runtime.py`, `host_runtime.py`, `selection_runtime.py`, `tab_runtime.py`, and `view_runtime.py`
  Current state: preferred chart helper modules, with the `main_window_chart_*` files in the same package left as compatibility wrappers during migration

- `Languages/Python/app/gui/backtest/bridge_runtime.py`, `execution_runtime.py`, `results_runtime.py`, `state_runtime.py`, `tab_runtime.py`, `template_runtime.py`, and `worker_runtime.py`
  Current state: preferred backtest helper modules, with the `main_window_backtest_*` files in the same package left as compatibility wrappers during migration

  - `Languages/Python/app/gui/backtest/execution_runtime.py`
    Current state: backtest execution facade
    Internal split: `backtest_execution_context_runtime.py`, `backtest_execution_run_runtime.py`, and `backtest_execution_scan_runtime.py`

  - `Languages/Python/app/gui/backtest/state_runtime.py`
    Current state: backtest state/binding facade
    Internal split: `backtest_state_context_runtime.py`, `backtest_state_dates_runtime.py`, `backtest_state_init_runtime.py`, `backtest_state_lists_runtime.py`, and `backtest_state_symbols_runtime.py`

- `Languages/Python/app/gui/runtime/ui/secondary_tabs_runtime.py`, `tab_runtime.py`, `theme_runtime.py`, `theme_styles.py`, and `ui_misc_runtime.py`
  Current state: preferred UI-composition helper modules, with the `main_window_*` files in the same package left as compatibility wrappers during migration

- `Languages/Python/app/gui/runtime/account/account_runtime.py`, `balance_runtime.py`, and `margin_runtime.py`
  Current state: preferred account-oriented GUI runtime modules, with the `main_window_*` files in the same package left as compatibility wrappers during migration

- `Languages/Python/app/gui/runtime/service/service_api_runtime.py`, `session_runtime.py`, and `status_runtime.py`
  Current state: preferred desktop service/session GUI runtime modules, with the `main_window_*` files in the same package left as compatibility wrappers during migration

- `Languages/Python/app/gui/shared/config_runtime.py`, `helper_runtime.py`, `ui_support.py`, and `web_embed.py`
  Current state: preferred shared GUI helper modules; the first `main_window_*` shared wrapper batch has been removed

- `Languages/Python/app/gui/trade/trade_runtime.py`, `signal_runtime.py`, and `signal_open_runtime.py`
  Current state: preferred trade-signal helper modules, with the `main_window_trade*` files in the same package left as compatibility wrappers during migration

- `Languages/Python/app/gui/trade/signal_close_runtime.py`
  Current state: thin close-signal facade
  Internal split: `signal_close_allocations_runtime.py`, `signal_close_records_runtime.py`, and `signal_close_interval_runtime.py`

- `Languages/Python/app/gui/code/runtime.py` and `tab_runtime.py`
  Current state: preferred code-tab helper modules, with `main_window_code_runtime.py` and `main_window_code.py` left as compatibility wrappers during migration

- `Languages/Python/app/gui/code/code_language_ui.py`
  Current state: thin code-tab language UI facade
  Internal split: `code_language_ui_build_runtime.py`, `code_language_ui_selection_runtime.py`, and `code_language_ui_state_runtime.py`

- `Languages/Python/app/gui/code/code_language_launcher.py`
  Current state: thin code-tab launch facade
  Internal split: `code_language_cpp_launcher_runtime.py`, `code_language_rust_launcher_runtime.py`, and `code_language_launcher_shared_runtime.py`

- `Languages/Python/app/gui/code/code_language_cpp_bundle_runtime.py`
  Current state: thin C++ bundle/runtime facade
  Internal split: `code_language_cpp_bundle_cache_runtime.py`, `code_language_cpp_bundle_packaged_runtime.py`, `code_language_cpp_bundle_release_runtime.py`, and `code_language_cpp_bundle_install_runtime.py`

- `Languages/Python/app/platform/windows_taskbar.py`
  Current state: thin Windows taskbar facade
  Internal split: `windows_taskbar_metadata_runtime.py`, `windows_taskbar_shortcut_runtime.py`, and `windows_taskbar_shared_runtime.py`

- `Languages/Python/app/gui/code/dependency_versions_cpp_runtime.py`
  Current state: thin C++ dependency facade
  Internal split: `dependency_versions_cpp_shared_runtime.py`, `dependency_versions_cpp_probe_runtime.py`, `dependency_versions_cpp_latest_runtime.py`, and `dependency_versions_cpp_policy_runtime.py`

- `Languages/Python/app/gui/chart/lightweight_widget.py`
  Current state: thin lightweight-charts facade
  Internal split: `lightweight_widget_assets.py` and `lightweight_widget_runtime.py`

- `Languages/Python/app/gui/chart/tradingview_widget.py`
  Current state: thin TradingView facade
  Internal split: `tradingview_widget_assets.py` and `tradingview_widget_runtime.py`

- `Languages/Python/app/gui/chart/binance_web_widget.py`
  Current state: thin Binance web-chart facade
  Internal split: `binance_web_widget_helpers.py` and `binance_web_widget_runtime.py`

- `Languages/Python/app/gui/chart/chart_embed.py`
  Current state: thin chart-embed facade
  Internal split: `chart_embed_state_runtime.py` and `chart_embed_host_runtime.py`

- `Languages/Python/app/gui/chart/display_runtime.py`
  Current state: thin chart-display facade
  Internal split: `display_render_runtime.py`, `display_payload_runtime.py`, and `display_load_runtime.py`

- `Languages/Python/app/gui/chart/chart_widgets.py`
  Current state: thin chart-widget facade
  Internal split: `simple_candlestick_widget.py` and `interactive_chart_view.py`

- `Languages/Python/app/gui/runtime/window/main_window_window_events_runtime.py`
  Current state: extracted `main_window_runtime.py` slice for native close detection and close/hide window-guard lifecycle behavior

- `Languages/Python/app/gui/runtime/strategy/start_runtime.py`
  Current state: authoritative start-engine lifecycle and loop-building module, with `main_window_start_strategy_runtime.py` left as a compatibility shim

- `Languages/Python/app/gui/runtime/strategy/stop_runtime.py`
  Current state: authoritative stop-engine and close-all lifecycle module, with `main_window_stop_strategy_runtime.py` left as a compatibility shim

- `Languages/Python/app/gui/runtime/strategy/control_runtime.py`
  Current state: authoritative strategy control binder, with `main_window_control_runtime.py` left as a compatibility shim

- `Languages/Python/app/gui/runtime/strategy/override_runtime.py`, `controls_runtime.py`, `ui_runtime.py`, `stop_loss_runtime.py`, `indicator_runtime.py`, and `context_runtime.py`
  Current state: authoritative strategy GUI runtime modules, with the `main_window_*` files in the same package left as compatibility shims during migration

- `Languages/Python/app/gui/positions/actions_runtime.py`, `build_runtime.py`, `record_build_runtime.py`, `render_runtime.py`, `table_render_runtime.py`, `history_runtime.py`, `history_records_runtime.py`, `history_update_runtime.py`, `positions_runtime.py`, `tab_runtime.py`, `tracking_runtime.py`, and `worker_runtime.py`
    Current state: preferred public positions helper modules, with the `main_window_positions_*` files in the same package left as compatibility shims and wrapper surfaces during migration
    Internal split note: `positions_runtime.py` now keeps the bind/orchestration surface, with shared positions config/helper state in `positions_context_runtime.py`, cumulative record aggregation in `positions_cumulative_runtime.py`, and manual refresh helpers in `positions_refresh_runtime.py`
  - `Languages/Python/app/gui/positions/actions_runtime.py`
    Current state: thin positions-action facade
    Internal split: `actions_context_runtime.py`, `actions_history_runtime.py`, `actions_state_runtime.py`, and `actions_close_runtime.py`

  - `Languages/Python/app/gui/backtest/tab_runtime.py`
    Current state: backtest-tab orchestration surface
    Current split: shared tab config in `backtest_tab_context_runtime.py`, market controls in `backtest_tab_market_runtime.py`, parameter controls in `backtest_tab_params_runtime.py`, indicator controls in `backtest_tab_indicator_runtime.py`, and output/results UI in `backtest_tab_output_runtime.py`

- `Languages/Python/main.py`
  Current state: stable public launcher shim

Do not try to move everything in one large refactor. Introduce new packages and move responsibility gradually.

## Phase-by-phase plan

## Phase 1: Define boundaries without breaking the desktop app

Goal:

- keep `apps/desktop-pyqt/main.py` working
- keep `Languages/Python/main.py` working
- stop adding more business logic to the GUI layer

Steps:

1. Create new packages:
   - `Languages/Python/app/core/`
   - `Languages/Python/app/integrations/`
   - `Languages/Python/app/service/`
   - `Languages/Python/app/desktop/`

2. Move only new code into the new packages first.

3. Add thin compatibility imports so the existing app does not break during migration.

4. Start extracting small reusable pieces from:
   - `strategy.py`
   - `trading_core/backtest.py`
   - `binance_wrapper.py`
   - `gui/main_window.py`

Deliverable:

- old desktop app still launches
- new code starts landing in the correct layer

## Phase 2: Extract a headless application service

Goal:

- create a backend runtime that can run without PyQt

Steps:

1. Add a service entrypoint:
   - `Languages/Python/app/service/main.py`

2. Create a runtime coordinator:
   - `Languages/Python/app/service/runners/bot_runtime.py`

3. Move desktop-owned control flow out of `MainWindow` and into service-level classes.

4. Define service methods such as:
   - start bot
   - stop bot
   - get status
   - get logs
   - get positions
   - run backtest
   - load/save config

Deliverable:

- bot can run in a headless Python process
- desktop can call the same service methods locally
- lifecycle and control intent are owned by the service runner instead of the Qt window
- execution adapters can be attached so the service can report whether control is intent-only or backed by a real runtime owner
- the standalone service process can attach its own local execution adapter before the full trading engine extraction is finished
- execution snapshots should remain part of the service contract so later extracted runners can expose session identity and progress consistently
- workload/progress/heartbeat fields should stay stable across future live-trading and backtest service executors
- the first extracted service-owned workload can be backtest execution, because it already exists outside the GUI aside from its Qt worker wrapper

## Phase 3: Introduce stable schemas

Goal:

- define data contracts before building web/mobile

Steps:

1. Add `Languages/Python/app/service/schemas/`

2. Create models for:
   - bot status
   - account summary
   - account balance snapshots
   - open positions
   - closed positions
   - log events
   - config payloads
   - backtest requests/results

3. Use these schemas internally first between desktop and service adapters.

Deliverable:

- backend and clients can speak a stable API contract
- desktop can start mirroring recent runtime logs into the service layer before HTTP exists
- desktop can mirror account and portfolio snapshots into the service layer before HTTP exists

## Phase 4: Add FastAPI backend

Goal:

- expose the headless runtime over HTTP

Recommended stack:

- FastAPI
- Pydantic
- Uvicorn

Suggested initial endpoints:

- `GET /health`
- `GET /api/v1/status`
- `POST /api/v1/bot/start`
- `POST /api/v1/bot/stop`
- `GET /api/v1/config`
- `PUT /api/v1/config`
- `GET /api/v1/positions`
- `GET /api/v1/logs`
- `GET /api/v1/backtest`
- `POST /api/v1/backtest/run`
- `POST /api/v1/backtest/stop`

Suggested real-time channel:

- websocket or SSE for bot status and log streaming

Deliverable:

- backend usable by desktop, web, and mobile
- optional bearer-token auth can protect API access before full user/session auth exists
- a thin same-origin dashboard can bootstrap the web client path before a larger SPA/frontend build
- the thin dashboard can move from REST polling to SSE once the backend snapshot contract is stable
- extracted service-owned workloads can publish richer snapshots before live trading is moved out of the desktop runtime

## Phase 5: Make desktop a client of the service layer

Goal:

- reduce PyQt ownership of business logic

Steps:

1. Add desktop adapters in:
   - `Languages/Python/app/desktop/adapters/`
   - `Languages/Python/app/desktop/adapters/service_client.py`

2. Let the desktop run in two modes:
   - embedded mode: uses local service classes directly
   - remote mode: talks to HTTP API

3. Keep the current desktop as the main power-user client.

Deliverable:

- desktop remains first-class
- same behavior can later be exposed through web/mobile
- GUI talks to a desktop client contract instead of importing backend service state directly
- desktop can optionally host the service API against the same in-process service state for thin web dashboards or remote inspection
- desktop-hosted API control requests can be forwarded back into the live GUI/runtime thread instead of staying as snapshot-only intent

## Phase 6: Add optional Docker support

Goal:

- package the backend without making Docker required

Steps:

1. Add:
   - `docker/backend.Dockerfile`
   - `docker/compose.yaml`
   - `.dockerignore`

2. Containerize only:
   - backend API
   - optional database
   - optional reverse proxy

3. Do not containerize the current PyQt desktop GUI as the main path.

4. Keep both launch modes documented:
   - local Python service
   - Docker service

Deliverable:

- Docker is available for deployment
- local non-Docker usage still works normally
- current repo baseline can ship this through `docker/backend.Dockerfile` and `docker/compose.yaml`

## Phase 7: Build the web GUI

Goal:

- create browser-based monitoring and control

Suggested stack:

- React + Vite or Next.js
- browser-native charting
- API/WebSocket connection to backend

Suggested feature order:

1. status/dashboard
2. logs
3. positions
4. config editor
5. backtest UI
6. chart integrations

Do not try to port Qt widgets directly. Rebuild the workflows around the backend API.

Deliverable:

- remote control panel for the bot
- current repo baseline already includes a thin same-origin dashboard in `apps/web-dashboard/`

## Phase 8: Add Android/iOS only as thin clients

Goal:

- provide mobile monitoring/control without duplicating core logic

Recommended options:

- React Native
- Flutter

Rules:

- mobile app must call backend API only
- exchange credentials must stay on the backend
- mobile should start as monitoring/control, not full local trading execution

Deliverable:

- optional mobile client built on top of the same backend
- current repo baseline can start from the Expo native-client path in `apps/mobile-client/`

## Suggested first folder creation

This is the safest minimal starting point:

```text
Languages/Python/app/
  core/
    __init__.py
  integrations/
    __init__.py
  service/
    __init__.py
    main.py
    schemas/
      __init__.py
  desktop/
    __init__.py
```

After that, migrate in this order:

1. schemas
2. service runtime
3. exchange integration wrappers
4. strategy/backtest extraction
5. desktop adapters
6. web GUI
7. optional Docker
8. optional mobile

## What not to do

- Do not make Docker mandatory for local desktop users.
- Do not try to port the current PyQt app directly to Android/iOS.
- Do not let web/mobile call exchange or broker APIs directly with user secrets.
- Do not rewrite everything in one step.
- Do not block desktop improvements while building backend layers.

## Practical first milestone

The best first milestone for this repo is:

1. create `app/service/main.py`
2. create shared schemas for status/config/positions/logs
3. move bot start/stop/status orchestration out of `MainWindow`
4. keep the desktop app fully working

Once that milestone is complete, Docker, web GUI, and mobile become straightforward follow-up projects instead of risky rewrites.
