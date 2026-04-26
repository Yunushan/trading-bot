#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use eframe::egui;
use trading_bot_core::{app_banner, llm_provider_options, LlmProviderOption};

struct EguiShell {
    llm_enabled: bool,
    allow_public_network: bool,
    provider_key: String,
    model: String,
    reasoning_effort: String,
    base_url: String,
    api_key_env: String,
    api_token: String,
    use_for: String,
}

impl Default for EguiShell {
    fn default() -> Self {
        let provider = llm_provider_options()
            .first()
            .expect("LLM provider catalog must not be empty");
        Self {
            llm_enabled: false,
            allow_public_network: provider.mode == "cloud",
            provider_key: provider.key.to_owned(),
            model: provider.model_suggestions.first().unwrap_or(&"").to_string(),
            reasoning_effort: provider
                .reasoning_efforts
                .first()
                .unwrap_or(&"default")
                .to_string(),
            base_url: provider.default_base_url.to_owned(),
            api_key_env: provider.api_key_env.to_owned(),
            api_token: String::new(),
            use_for: "advisory".to_owned(),
        }
    }
}

impl EguiShell {
    fn selected_provider(&self) -> &'static LlmProviderOption {
        llm_provider_options()
            .iter()
            .find(|provider| provider.key == self.provider_key)
            .or_else(|| llm_provider_options().first())
            .expect("LLM provider catalog must not be empty")
    }

    fn local_provider(&self) -> &'static LlmProviderOption {
        llm_provider_options()
            .iter()
            .find(|provider| provider.mode != "cloud")
            .or_else(|| llm_provider_options().first())
            .expect("LLM provider catalog must not be empty")
    }

    fn apply_provider_defaults(&mut self, provider: &'static LlmProviderOption) {
        self.provider_key = provider.key.to_owned();
        self.allow_public_network = provider.mode == "cloud";
        self.model = provider.model_suggestions.first().unwrap_or(&"").to_string();
        self.reasoning_effort = provider
            .reasoning_efforts
            .first()
            .unwrap_or(&"default")
            .to_string();
        self.base_url = provider.default_base_url.to_owned();
        self.api_key_env = provider.api_key_env.to_owned();
    }
}

impl eframe::App for EguiShell {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading(app_banner("egui"));
            ui.label("Wire dashboard widgets to the shared Rust core here.");
            ui.separator();
            ui.heading("AI / LLM Settings");
            ui.checkbox(&mut self.llm_enabled, "Enable LLM assistance");
            if !self.llm_enabled {
                ui.label("LLM assistance disabled - enable it to edit provider and model settings.");
            }
            ui.add_enabled_ui(self.llm_enabled, |ui| {
                if ui
                    .checkbox(
                        &mut self.allow_public_network,
                        "Allow public network endpoint",
                    )
                    .changed()
                    && !self.allow_public_network
                    && self.selected_provider().mode == "cloud"
                {
                    self.apply_provider_defaults(self.local_provider());
                }

                let selected = self.selected_provider();
                let mut selected_key = self.provider_key.clone();
                egui::ComboBox::from_label("Provider")
                    .selected_text(selected.label)
                    .show_ui(ui, |ui| {
                        for provider in llm_provider_options() {
                            let provider_allowed =
                                self.allow_public_network || provider.mode != "cloud";
                            ui.add_enabled_ui(provider_allowed, |ui| {
                                ui.selectable_value(
                                    &mut selected_key,
                                    provider.key.to_owned(),
                                    provider.label,
                                );
                            });
                        }
                    });
                if selected_key != self.provider_key {
                    if let Some(provider) = llm_provider_options()
                        .iter()
                        .find(|provider| provider.key == selected_key)
                    {
                        self.apply_provider_defaults(provider);
                    }
                }

                let provider = self.selected_provider();
                egui::ComboBox::from_label("Model")
                    .selected_text(if self.model.is_empty() {
                        "Custom model"
                    } else {
                        self.model.as_str()
                    })
                    .show_ui(ui, |ui| {
                        for model in provider.model_suggestions {
                            ui.selectable_value(&mut self.model, (*model).to_owned(), *model);
                        }
                    });
                egui::ComboBox::from_label("Reasoning / Thinking")
                    .selected_text(if self.reasoning_effort.is_empty() {
                        "default"
                    } else {
                        self.reasoning_effort.as_str()
                    })
                    .show_ui(ui, |ui| {
                        for effort in provider.reasoning_efforts {
                            ui.selectable_value(
                                &mut self.reasoning_effort,
                                (*effort).to_owned(),
                                *effort,
                            );
                        }
                    });
                ui.horizontal(|ui| {
                    ui.label("Base URL / IP");
                    ui.text_edit_singleline(&mut self.base_url);
                });
                ui.horizontal(|ui| {
                    ui.label("API key env");
                    ui.text_edit_singleline(&mut self.api_key_env);
                });
                ui.horizontal(|ui| {
                    ui.label("API token");
                    ui.add(egui::TextEdit::singleline(&mut self.api_token).password(true));
                });
                egui::ComboBox::from_label("Use for")
                    .selected_text(&self.use_for)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.use_for, "advisory".to_owned(), "Advisory");
                        ui.selectable_value(
                            &mut self.use_for,
                            "signal_confirmation".to_owned(),
                            "Signal confirmation",
                        );
                        ui.selectable_value(&mut self.use_for, "risk_review".to_owned(), "Risk review");
                        ui.selectable_value(
                            &mut self.use_for,
                            "backtest_explanation".to_owned(),
                            "Backtest explanation",
                        );
                    });
            });
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
