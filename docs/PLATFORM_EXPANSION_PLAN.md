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

- `Languages/Python/main.py`: desktop bootstrap and platform-specific startup behavior
- `Languages/Python/app/gui/main_window.py`: large PyQt desktop application shell
- `Languages/Python/app/strategy.py`: core trading/runtime behavior candidate
- `Languages/Python/app/binance_wrapper.py`: exchange integration candidate
- `Languages/Python/app/backtester.py`: backtesting candidate

This means the project already has the raw pieces needed for expansion, but they are still too close to the desktop process.

## Target architecture

The recommended direction is to split the Python implementation into these layers:

```text
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
  clients/
    web/                 # optional future web frontend
    mobile/              # optional future thin mobile client
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

The first concrete exchange move is already in place: the Binance integration package now lives under `app/integrations/exchanges/binance/`, with the live support modules using package-local imports internally and `app/binance_wrapper.py` kept only as a compatibility shim for older imports.

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

### `clients/web/`

Optional browser-based frontend.

Use this only after the backend exists.

The current thin dashboard should keep trending toward small browser modules, with shared state, render helpers, and API transport split out of the top-level browser bootstrap file.

### `clients/mobile/`

Optional native thin client for Android/iOS.

Do not move exchange or broker secrets here. Mobile must talk to the backend only.

### `docker/`

Optional deployment packaging.

Docker should package the backend service, not the current PyQt GUI.

## Recommended migration mapping from current files

Start by treating these current files as the seeds of the new layers:

- `Languages/Python/app/strategy.py`
  Current state: compatibility shim
  New home: `app/core/strategy/engine.py`

- `Languages/Python/app/strategy_signal_order*.py`
  Current state: compatibility shims
  New home: `app/core/strategy/strategy_signal_order*.py`

- `Languages/Python/app/strategy_signal_orders_runtime.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_signal_orders_runtime.py`

- `Languages/Python/app/strategy_runtime.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_runtime.py`

- `Languages/Python/app/strategy_runtime_support.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_runtime_support.py`

- `Languages/Python/app/strategy_cycle_runtime.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_cycle_runtime.py`

- `Languages/Python/app/strategy_indicator_compute.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_indicator_compute.py`

- `Languages/Python/app/strategy_signal_generation.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_signal_generation.py`

- `Languages/Python/app/strategy_indicator_tracking.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_indicator_tracking.py`

- `Languages/Python/app/strategy_indicator_guard.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_indicator_guard.py`

- `Languages/Python/app/strategy_trade_book.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_trade_book.py`

- `Languages/Python/app/strategy_position_state.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_position_state.py`

- `Languages/Python/app/strategy_position_close_runtime.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_position_close_runtime.py`

- `Languages/Python/app/strategy_position_flip_runtime.py`
  Current state: compatibility shim
  New home: `app/core/strategy/strategy_position_flip_runtime.py`

- `Languages/Python/app/backtester.py`
  Current state: compatibility shim
  New home: `app/core/backtest/engine.py`

- `Languages/Python/app/indicators.py`
  Current state: compatibility shim
  New home: `app/core/indicators/__init__.py`

- `Languages/Python/app/position_guard.py`
  Current state: compatibility shim
  New home: `app/core/positions/guard.py`

- `Languages/Python/app/binance_wrapper.py`
  Current state: compatibility shim
  New home: `app/integrations/exchanges/binance/wrapper.py`

- `Languages/Python/app/gui/main_window.py`
  Future target: `app/desktop/gui/`

- `Languages/Python/app/desktop/bootstrap/main.py`
  Current state: moved desktop-bootstrap implementation behind the public launcher

- `Languages/Python/app/gui/runtime/main_window_init_ui_runtime.py`
  Current state: first extracted `main_window.py` UI-assembly helper

- `Languages/Python/app/gui/runtime/main_window_bindings_runtime.py`
  Current state: extracted `main_window.py` class-binding/configuration helper

- `Languages/Python/app/gui/runtime/main_window_module_state_runtime.py`
  Current state: extracted `main_window.py` constant/helper-alias helper

- `Languages/Python/app/gui/runtime/window_code_tab_suppression_runtime.py`
  Current state: first extracted `window_runtime.py` slice for code-tab suppression on Windows

- `Languages/Python/app/gui/runtime/window_webengine_guard_runtime.py`
  Current state: extracted `window_runtime.py` slice for WebEngine/TradingView prewarm and guard behavior

- `Languages/Python/app/gui/runtime/main_window_window_events_runtime.py`
  Current state: extracted `main_window_runtime.py` slice for native close detection and close/hide window-guard lifecycle behavior

- `Languages/Python/app/gui/runtime/main_window_start_strategy_runtime.py`
  Current state: extracted `main_window_control_runtime.py` slice for start-engine lifecycle and loop-building behavior

- `Languages/Python/app/gui/runtime/main_window_stop_strategy_runtime.py`
  Current state: extracted `main_window_control_runtime.py` slice for stop-engine and close-all lifecycle handling

- `Languages/Python/main.py`
  Current state: stable public launcher shim

Do not try to move everything in one large refactor. Introduce new packages and move responsibility gradually.

## Phase-by-phase plan

## Phase 1: Define boundaries without breaking the desktop app

Goal:

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
   - `backtester.py`
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
- `GET /api/status`
- `POST /api/bot/start`
- `POST /api/bot/stop`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/positions`
- `GET /api/logs`
- `GET /api/backtest`
- `POST /api/backtest/run`
- `POST /api/backtest/stop`

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
- current repo baseline already includes a thin same-origin dashboard in `Languages/Python/clients/web/`

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
- current repo baseline can start from the Expo native-client path in `Languages/Python/clients/mobile/`

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
