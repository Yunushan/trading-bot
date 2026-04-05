#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use eframe::egui;
use trading_bot_core::app_banner;

struct EguiShell;

impl eframe::App for EguiShell {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading(app_banner("egui"));
            ui.label("Wire dashboard widgets to the shared Rust core here.");
        });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions::default();
    eframe::run_native(
        "Trading Bot egui",
        options,
        Box::new(|_cc| Ok(Box::new(EguiShell))),
    )
}
