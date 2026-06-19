#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use eframe::egui;
use trading_bot_core::{
    TradingAppTab, app_banner, cpp_entire_python_app_contract_parity_ready,
    cpp_entire_python_app_parity_ready, native_full_python_app_parity_ready,
    native_python_app_contract_parity_ready, native_python_app_parity_domains,
    rust_entire_python_app_contract_parity_ready, rust_entire_python_app_parity_ready,
    rust_execution_modes, rust_native_runtime_capabilities,
    rust_native_trading_runtime_ready, rust_shell_framework_parity,
    rust_trading_execution_supported, service_api_capabilities, service_api_routes,
    trading_app_tabs,
};

struct EguiShell {
    selected_tab_key: &'static str,
}

impl Default for EguiShell {
    fn default() -> Self {
        Self {
            selected_tab_key: trading_app_tabs()
                .first()
                .map(|tab| tab.key)
                .unwrap_or("dashboard"),
        }
    }
}

impl EguiShell {
    fn selected_tab(&self) -> &'static TradingAppTab {
        trading_app_tabs()
            .iter()
            .find(|tab| tab.key == self.selected_tab_key)
            .or_else(|| trading_app_tabs().first())
            .expect("trading app tabs must not be empty")
    }

    fn render_metric_grid(ui: &mut egui::Ui, tab: &TradingAppTab) {
        egui::Grid::new(format!("{}_metric_grid", tab.key))
            .num_columns(2)
            .spacing([18.0, 10.0])
            .striped(true)
            .show(ui, |ui| {
                ui.label("Status");
                ui.strong(tab.status);
                ui.end_row();
                ui.label("Primary");
                ui.strong(tab.primary_metric);
                ui.end_row();
                ui.label("Secondary");
                ui.strong(tab.secondary_metric);
                ui.end_row();
            });
    }

    fn render_actions(ui: &mut egui::Ui, tab: &TradingAppTab) {
        ui.horizontal_wrapped(|ui| {
            for action in tab.actions {
                ui.add(egui::Button::new(*action).min_size(egui::vec2(96.0, 30.0)));
            }
        });
    }

    fn render_sections(ui: &mut egui::Ui, tab: &TradingAppTab) {
        for section in tab.sections {
            ui.group(|ui| {
                ui.heading(section.title);
                ui.separator();
                for item in section.items {
                    ui.label(*item);
                }
            });
            ui.add_space(8.0);
        }
    }

    fn render_tables(ui: &mut egui::Ui, tab: &TradingAppTab) {
        for table in tab.tables {
            ui.group(|ui| {
                ui.heading(table.title);
                egui::ScrollArea::horizontal().show(ui, |ui| {
                    egui::Grid::new(format!("{}_{}_table", tab.key, table.title))
                        .num_columns(table.columns.len())
                        .spacing([14.0, 8.0])
                        .striped(true)
                        .show(ui, |ui| {
                            for column in table.columns {
                                ui.strong(*column);
                            }
                            ui.end_row();
                            for _ in table.columns {
                                ui.label("--");
                            }
                            ui.end_row();
                        });
                });
            });
            ui.add_space(8.0);
        }
    }

    fn render_service_api(ui: &mut egui::Ui) {
        ui.group(|ui| {
            ui.heading("Service API Integration");
            ui.separator();
            for capability in service_api_capabilities() {
                ui.strong(capability.title);
                ui.label(capability.detail);
                ui.add_space(4.0);
            }
            ui.label(format!(
                "Standalone Rust trading execution supported: {}",
                rust_trading_execution_supported()
            ));
            for mode in rust_execution_modes() {
                ui.strong(mode.title);
                ui.label(format!(
                    "{} | trading_execution_supported={}",
                    mode.detail, mode.trading_execution_supported
                ));
                ui.add_space(4.0);
            }
            ui.label("Framework Parity:");
            for parity in rust_shell_framework_parity() {
                ui.strong(format!("{} - {}", parity.framework, parity.status));
                ui.label(parity.detail);
                ui.add_space(4.0);
            }
            ui.label(format!(
                "Native Rust trading runtime ready: {}",
                rust_native_trading_runtime_ready()
            ));
            ui.label("Native Runtime Gap:");
            for capability in rust_native_runtime_capabilities() {
                ui.strong(format!("{} - {}", capability.key, capability.title));
                ui.label(format!("C++: {}", capability.cpp_status));
                ui.label(format!("Rust: {}", capability.rust_status));
                ui.label(format!(
                    "Required before enable: {} | trading_execution_supported={}",
                    capability.required_before_enable, capability.trading_execution_supported
                ));
                ui.add_space(4.0);
            }
            ui.label(format!(
                "Python app contract/catalog parity ready: {}",
                native_python_app_contract_parity_ready()
            ));
            ui.label(format!(
                "C++ Python app contract/catalog parity ready: {}",
                cpp_entire_python_app_contract_parity_ready()
            ));
            ui.label(format!(
                "Rust Python app contract/catalog parity ready: {}",
                rust_entire_python_app_contract_parity_ready()
            ));
            ui.label(format!(
                "Full standalone Python app parity ready: {}",
                native_full_python_app_parity_ready()
            ));
            ui.label(format!(
                "C++ full standalone Python app parity ready: {}",
                cpp_entire_python_app_parity_ready()
            ));
            ui.label(format!(
                "Rust full standalone Python app parity ready: {}",
                rust_entire_python_app_parity_ready()
            ));
            ui.label("Python App Contract Parity Audit:");
            for domain in native_python_app_parity_domains() {
                ui.strong(format!("{} - {}", domain.key, domain.title));
                ui.label(format!("Python: {}", domain.python_surface));
                ui.label(format!("C++: {}", domain.cpp_status));
                ui.label(format!("Rust: {}", domain.rust_status));
                ui.label(format!(
                    "Contract completion: {} | cpp_contract_parity={} | rust_contract_parity={}",
                    domain.required_before_full_parity,
                    domain.cpp_full_parity,
                    domain.rust_full_parity
                ));
                ui.add_space(4.0);
            }
            ui.label("Canonical routes:");
            for route in service_api_routes() {
                ui.label(format!(
                    "{} {} ({})",
                    route.methods.join("/"),
                    route.path,
                    route.name
                ));
            }
        });
    }

    fn render_tab(&mut self, ui: &mut egui::Ui, tab: &TradingAppTab) {
        ui.heading(tab.title);
        ui.label(tab.summary);
        ui.add_space(8.0);
        Self::render_actions(ui, tab);
        ui.separator();
        Self::render_metric_grid(ui, tab);
        ui.separator();
        egui::ScrollArea::vertical().show(ui, |ui| {
            Self::render_sections(ui, tab);
            Self::render_tables(ui, tab);
            Self::render_service_api(ui);
        });
    }
}

impl eframe::App for EguiShell {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::TopBottomPanel::top("topbar").show(ctx, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.heading(app_banner("egui"));
                ui.separator();
                ui.label("Total PNL Active Positions: --");
                ui.label("Total PNL Closed Positions: --");
                ui.colored_label(egui::Color32::LIGHT_RED, "Bot Status: OFF");
                ui.label("Bot Active Time: --");
            });
        });

        egui::SidePanel::left("trading_tabs")
            .resizable(false)
            .default_width(210.0)
            .show(ctx, |ui| {
                ui.heading("Tabs");
                ui.separator();
                for tab in trading_app_tabs() {
                    let selected = self.selected_tab_key == tab.key;
                    if ui.selectable_label(selected, tab.title).clicked() {
                        self.selected_tab_key = tab.key;
                    }
                }
            });

        egui::TopBottomPanel::bottom("bottombar").show(ctx, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.label("Total PNL Active Positions: --");
                ui.label("Total PNL Closed Positions: --");
                ui.colored_label(egui::Color32::LIGHT_RED, "Bot Status: OFF");
                ui.label("Bot Active Time: --");
            });
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            let tab = self.selected_tab();
            self.render_tab(ui, tab);
        });
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions::default();
    eframe::run_native(
        "Trading Bot egui",
        options,
        Box::new(|_cc| Ok(Box::new(EguiShell::default()))),
    )
}
