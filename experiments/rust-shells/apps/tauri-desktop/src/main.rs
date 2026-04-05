#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use tauri::Manager;
use trading_bot_core::app_banner;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_title(&app_banner("Tauri"));
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Tauri desktop shell");
}
