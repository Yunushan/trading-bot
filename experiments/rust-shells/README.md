# Trading Bot Rust Shell Experiments

This directory is a Rust workspace for shared contracts/core logic plus multiple desktop-shell experiments.

It is not a single finished application. The Rust side is currently a Service API client and UI parity scaffold, not a native trading runtime. Python remains the primary end-user implementation and the only active strategy, risk, and exchange execution owner.

## Workspace layout

- `crates/contracts`: shared DTOs and contracts
- `crates/core`: shared Rust core scaffold
- `apps/tauri-desktop`: Tauri desktop shell
- `apps/slint-desktop`: Slint desktop shell
- `apps/egui-desktop`: egui desktop shell
- `apps/iced-desktop`: Iced desktop shell
- `apps/dioxus-desktop`: Dioxus Desktop shell

The shared Rust core exposes the same LLM provider catalog used by the Python
service API. The Rust shells may mirror Python/C++ tabs, controls, route names,
and model options, but mirrored UI does not mean native trading execution. All
live strategy, risk, account, order, and exchange behavior must continue through
the Python Service API until the native Rust runtime gaps below are closed.

## Status overview

| Component | Status | Notes |
| --- | --- | --- |
| Shared contracts crate | Active foundation | Common types and workspace contracts |
| Shared core crate | Active foundation | Intended home for reusable Rust-side business logic |
| Tauri desktop shell | Operational Service API client | Most complete Rust UI; can manage/connect to the Python Service API, but does not own trading execution |
| Slint desktop shell | Non-operational native UI evaluation | Native declarative desktop direction; surfaces the same option map but does not manage the Service API |
| egui desktop shell | Non-operational comparison renderer | Fast dashboard-oriented UI path; renders catalog/status data from `trading-bot-core` |
| Iced desktop shell | Non-operational comparison renderer | Pure Rust reactive desktop path; renders catalog/status data from `trading-bot-core` |
| Dioxus Desktop shell | Non-operational comparison renderer | Component-style desktop shell; renders catalog/status data from `trading-bot-core` |

Recommended order for this project:

1. Use `Tauri` for serious Rust desktop work because it is the only Rust shell with an interactive Service API client and managed local Python Service API flow.
2. Keep `Slint` only as a non-operational native-widget evaluation path until it gains the same live client behavior.
3. Keep `egui`, `Iced`, and `Dioxus Desktop` as non-operational comparison renderers, not as product-grade candidates yet.

The `Tauri` recommendation is an engineering recommendation based on the current repo shape, not a statement that the other shells are removed or unsupported.

## Native trading runtime boundary

Rust native trading execution is currently disabled. The Rust workspace is a
Service API client, tab/catalog parity layer, and desktop-framework evaluation
path. It must not be treated as a standalone trading engine until the native
runtime capability gaps are implemented and tested.

The C++ experiment already contains native runtime pieces that Rust does not:

- `BinanceRestClient.*`: balance, symbols, klines, ticker price, open futures
  positions, symbol filters, and market/limit futures orders.
- `BinanceWsClient.*`: book ticker and kline WebSocket stream scaffolding.
- `TradingBotWindow.dashboard_runtime*.cpp`: dashboard runtime lifecycle,
  polling, signal candle caches, retry windows, open-position tracking, order
  fallback helpers, and shutdown handling.
- `TradingBotWindow.positions.cpp`: live futures position/balance refresh and
  local table reconciliation.

`trading-bot-core` now has a native `BinanceRestMarketDataClient` foundation for
exchangeInfo USDT symbols, optional 24h quote-volume ordering, klines, ticker
prices, and Binance error payload handling. Before native Rust trading can be
enabled, Rust still needs custom interval aggregation, WebSocket streams, signed
account/position snapshots, order submission, runtime lifecycle, connector
diagnostics, and risk/shutdown guards with regression tests. The source-level
guard for this is `rust_native_trading_runtime_ready() == false` and the
capability matrix exposed by `rust_native_runtime_capabilities()`.

## Full Python app parity audit

The Rust workspace now exposes a broader full-app parity contract through
`native_python_app_parity_domains()`. That matrix is intentionally separate from
option-list and route-catalog parity: mirrored controls are useful, but they do
not mean Rust owns the Python app's execution behavior.

Current source-level guards:

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
cargo run -p trading-bot-egui-desktop
```

If `cargo` is not installed yet, install Rust with `rustup` first.

## Recommendation

Use this workspace when you want to:

- build shared Rust contracts/core incrementally
- evaluate desktop framework tradeoffs
- prototype a future Rust-native runtime

If you want the most complete working app today, use `Languages/Python`.
