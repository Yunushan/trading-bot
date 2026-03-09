use trading_bot_contracts::AppIdentity;

pub fn app_banner(shell: &str) -> String {
    format!("Trading Bot Rust scaffold -> {shell}")
}

pub fn default_identity(shell: &str) -> AppIdentity {
    AppIdentity::new(shell)
}

pub fn supported_frameworks() -> &'static [&'static str] {
    &[
        "Tauri",
        "Slint",
        "egui",
        "Iced",
        "Dioxus Desktop",
    ]
}
