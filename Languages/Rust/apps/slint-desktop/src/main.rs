#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

slint::include_modules!();

use trading_bot_core::app_banner;

fn main() -> Result<(), slint::PlatformError> {
    let app = AppWindow::new()?;
    app.set_app_title(app_banner("Slint").into());
    app.run()
}
