# Trading Bot Rust Shell Experiments

This directory is a Rust workspace for shared contracts/core logic plus multiple desktop-shell experiments.

It is not a single finished application. The Rust side is currently a scaffold and expansion path intended to share logic across several UI frameworks while the Python app remains the primary end-user implementation.

## Workspace layout

- `crates/contracts`: shared DTOs and contracts
- `crates/core`: shared Rust core scaffold
- `apps/tauri-desktop`: Tauri desktop shell
- `apps/slint-desktop`: Slint desktop shell
- `apps/egui-desktop`: egui desktop shell
- `apps/iced-desktop`: Iced desktop shell
- `apps/dioxus-desktop`: Dioxus Desktop shell

The shared Rust core exposes the same LLM provider catalog used by the Python
service API. The egui and Tauri shells include starter controls for OpenAI,
Claude, Gemini, DeepSeek, Grok, Qwen, and local/private OpenAI-compatible
endpoints with model, base URL/IP, API env var, token, and use-mode fields.

## Status overview

| Component | Status | Notes |
| --- | --- | --- |
| Shared contracts crate | Active foundation | Common types and workspace contracts |
| Shared core crate | Active foundation | Intended home for reusable Rust-side business logic |
| Tauri desktop shell | Recommended first shell | Most packaging-oriented scaffold in the current tree |
| Slint desktop shell | Experimental scaffold | Native declarative desktop direction |
| egui desktop shell | Experimental scaffold | Fast dashboard-oriented UI path |
| Iced desktop shell | Experimental scaffold | Pure Rust reactive desktop path |
| Dioxus Desktop shell | Experimental scaffold | Component-style desktop shell |

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

Before native Rust trading can be enabled, `trading-bot-core` needs equivalent
REST market data, WebSocket streams, signed account/position snapshots, order
submission, runtime lifecycle, and risk/shutdown guards with regression tests.
The source-level guard for this is `rust_native_trading_runtime_ready() == false`
and the capability matrix exposed by `rust_native_runtime_capabilities()`.

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
