# Trading Bot Rust Shell Experiments

This directory is a Rust workspace for shared contracts/core logic plus the Tauri desktop shell.

It is not a single finished application. The Rust side is currently a Service API client and UI parity scaffold, not a native trading runtime. Python remains the primary end-user implementation and the only active strategy, risk, and exchange execution owner.

## Workspace layout

- `crates/contracts`: shared DTOs and contracts
- `crates/core`: shared Rust core scaffold
- `apps/tauri-desktop`: Tauri desktop shell

The shared Rust core exposes the same LLM provider catalog used by the Python
service API. The Tauri shell may mirror Python/C++ tabs, controls, route names,
and model options, but mirrored UI does not mean native trading execution. All
live strategy, risk, account, order, and exchange behavior must continue through
the Python Service API until the native Rust runtime gaps below are closed.

## Status overview

| Component | Status | Notes |
| --- | --- | --- |
| Shared contracts crate | Active foundation | Common types and workspace contracts |
| Shared core crate | Active foundation | Intended home for reusable Rust-side business logic |
| Tauri desktop shell | Operational Service API client | The only user-selectable Rust desktop shell; can manage/connect to the Python Service API, but does not own trading execution |

For this project, use `Tauri` for Rust desktop work because it is the only Rust shell with an interactive Service API client and managed local Python Service API flow.

## Native trading runtime boundary

Rust native trading execution is currently disabled. The Rust workspace is a
Service API client and tab/catalog parity layer. It must not be treated as a standalone trading engine until the native
runtime capability gaps are implemented and tested.

The C++ experiment already contains native runtime pieces that Rust does not:

- `BinanceRestClient.*`: balance, symbols, klines, ticker price, open futures
  positions, symbol filters, market/limit futures orders, and close-position
  planning rules.
- `BinanceWsClient.*`: book ticker and kline WebSocket stream scaffolding.
- `TradingBotWindow.dashboard_runtime*.cpp`: dashboard runtime lifecycle,
  polling, signal candle caches, retry windows, open-position tracking, order
  fallback helpers, and shutdown handling.
- `TradingBotWindow.positions.cpp`: live futures position/balance refresh and
  local table reconciliation.

`trading-bot-core` now has a native `BinanceRestMarketDataClient` foundation for
exchangeInfo USDT symbols, optional 24h quote-volume ordering, klines, ticker
prices, and Binance error payload handling. It also has `BinanceWebSocketClient`
for Binance book-ticker/kline stream URL construction, tungstenite connection
entry points, and message parsing; `BinanceSignedRestClient` for signed USDT
balance snapshots, normalized balance rows, and open futures position parsing
with account-position overlays; signed market/limit order request/result foundations
and Binance futures symbol filters; order submit guard foundations for Python's
intent, live-safety, audit, connector-health, filter, and session-cap checks;
order audit/circuit-breaker foundations for redacted JSONL events, snapshots,
incidents, threshold/window tripping, reset-block status, and rotation helpers;
risk/stop-loss close-decision foundations for normalized stop-loss settings,
per-trade, directional, cumulative, entire-account, and close-opposite planning;
a runtime-owned order engine for guarded submit, redacted audit JSONL,
connector circuit incident persistence, and submit reconciliation; a
runtime-owned risk/close execution path for stop-loss close fallback and
close-opposite residual reconciliation; plus portfolio/history/allocation
reconciliation helpers and close-position planning foundations that mirror
Python/C++ one-way `reduceOnly`, hedge-mode `positionSide`, and close-all
`closePosition` fallback rules. It also has Desktop shell/tab lifecycle
contracts plus strategy runtime signal/control/provenance helpers and worker
lifecycle snapshots for Python-source parity validation. Before standalone
native Rust trading can be enabled, Rust still needs custom interval
aggregation, supervised stream reconnect/cache guards, dry-run controls, live
credential-gated smoke coverage, hedge/one-way runtime coverage, and shutdown
guard wiring with regression tests. The source-level
guard for this is
`rust_native_trading_runtime_ready() == false` and the capability matrix exposed
by `rust_native_runtime_capabilities()`.

## Python app contract parity audit

The Rust workspace exposes a Python app source-contract parity matrix through
`native_python_app_parity_domains()`. That matrix is intentionally separate from
standalone runtime/product parity: mirrored controls and generated route catalogs
are useful, but they do not mean Rust owns the Python app's trading execution
behavior or has release evidence for every platform.

Current source-level guards:

- `native_python_app_contract_parity_ready() == true`
- `cpp_entire_python_app_contract_parity_ready() == true`
- `rust_entire_python_app_contract_parity_ready() == true`

Current standalone runtime/product guards:

- `native_full_python_app_parity_ready() == false`
- `cpp_entire_python_app_parity_ready() == false`
- `rust_entire_python_app_parity_ready() == false`

The tracked domains are desktop shell/tabs, Service API contract, config
persistence, strategy runtime, exchange connectors, account/portfolio/positions,
order execution/risk, backtest engine, charts/heatmaps, logs/terminal
diagnostics, LLM advisory, and startup/packaging/platform integration.

## Build examples

From `experiments/rust-shells`:

```bash
cargo run -p trading-bot-rust
cargo run -p trading-bot-tauri-desktop
```

If `cargo` is not installed yet, install Rust with `rustup` first.

## Recommendation

Use this workspace when you want to:

- build shared Rust contracts/core incrementally
- work on the Tauri Service API client shell
- prototype a future Rust-native runtime

If you want the most complete working app today, use `Languages/Python`.
