#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use dioxus::prelude::*;
use trading_bot_core::app_banner;

fn main() {
    launch(app);
}

fn app() -> Element {
    let banner = app_banner("Dioxus Desktop");
    rsx! {
        main {
            h1 { "{banner}" }
            p { "Shared Rust core scaffold wired to the Dioxus desktop shell." }
        }
    }
}
