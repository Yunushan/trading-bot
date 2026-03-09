# Trading Bot (Rust -> Languages/Rust)

This directory is now a Rust workspace, not a single placeholder crate.

It is organized around one shared Rust core plus multiple framework-specific
desktop shells so features can be implemented once in shared logic and surfaced
through different GUI runtimes.

## Workspace layout

- `crates/contracts`: shared DTOs and contracts.
- `crates/core`: shared business/core scaffold.
- `apps/tauri-desktop`: Tauri desktop shell.
- `apps/slint-desktop`: Slint desktop shell.
- `apps/egui-desktop`: egui desktop shell.
- `apps/iced-desktop`: Iced desktop shell.
- `apps/dioxus-desktop`: Dioxus Desktop shell.

## Build examples

```bash
cd Languages/Rust
cargo run -p trading-bot-rust
cargo run -p trading-bot-egui-desktop
cargo run -p trading-bot-tauri-desktop
```

If `cargo` is not installed yet, install Rust with `rustup` first.
