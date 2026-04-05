# Trading Bot Rust Workspace

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

## Build examples

From `Languages/Rust`:

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
