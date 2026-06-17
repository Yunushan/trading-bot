#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use dioxus::prelude::*;
use trading_bot_core::{
    TradingAppTab, app_banner, cpp_entire_python_app_parity_ready,
    native_full_python_app_parity_ready, native_python_app_parity_domains,
    rust_entire_python_app_parity_ready, rust_execution_modes, rust_native_runtime_capabilities,
    rust_native_trading_runtime_ready, rust_shell_framework_parity,
    rust_trading_execution_supported, service_api_capabilities, service_api_routes,
    trading_app_tabs,
};

const APP_STYLE: &str = r#"
body {
  margin: 0;
  background: #080d16;
  color: #f4f7fb;
  font-family: Segoe UI, system-ui, sans-serif;
}
button {
  font: inherit;
}
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
}
.topbar, .footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 24px;
  background: #0b1220;
  border-bottom: 1px solid #273449;
}
.footer {
  border-top: 1px solid #273449;
  border-bottom: 0;
  font-size: 13px;
}
.status-strip, .tabs, .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tabs {
  overflow-x: auto;
  padding: 10px 24px;
  border-bottom: 1px solid #273449;
  background: #0d1524;
}
.pill, .tab, .action {
  border: 1px solid #273449;
  border-radius: 6px;
  background: #0f1828;
  color: #d7e3f3;
  padding: 7px 11px;
}
.tab.active {
  border-color: #0284c7;
  background: #0c4a6e;
  color: #f0f9ff;
}
.workspace {
  padding: 20px 24px;
  display: grid;
  gap: 16px;
}
.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
.metrics, .cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 12px;
}
.panel {
  border: 1px solid #273449;
  border-radius: 8px;
  background: #101827;
  padding: 14px;
}
.label {
  color: #9ca9bd;
  font-size: 13px;
}
h1, h2, h3, p {
  margin: 0;
}
h1 {
  font-size: 22px;
}
h2 {
  font-size: 24px;
}
ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
li {
  margin: 4px 0;
}
@media (max-width: 900px) {
  .section-head, .metrics, .cards {
    display: grid;
    grid-template-columns: 1fr;
  }
}
"#;

fn main() {
    launch(app);
}

fn active_tab(tab_key: &str) -> &'static TradingAppTab {
    trading_app_tabs()
        .iter()
        .find(|tab| tab.key == tab_key)
        .or_else(|| trading_app_tabs().first())
        .expect("trading app tabs must not be empty")
}

fn app() -> Element {
    let banner = app_banner("Dioxus Desktop");
    let mut selected_tab_key = use_signal(|| "dashboard");
    let selected_key = selected_tab_key();
    let tab = active_tab(selected_key);
    let rust_exec_supported = rust_trading_execution_supported();
    let rust_native_ready = rust_native_trading_runtime_ready();
    let full_python_app_parity_ready = native_full_python_app_parity_ready();
    let cpp_python_app_parity_ready = cpp_entire_python_app_parity_ready();
    let rust_python_app_parity_ready = rust_entire_python_app_parity_ready();

    rsx! {
        style { "{APP_STYLE}" }
        main { class: "app-shell",
            header { class: "topbar",
                div {
                    h1 { "{banner}" }
                    p { class: "label", "Non-operational Rust comparison renderer; Tauri is the interactive Service API client." }
                }
                div { class: "status-strip",
                    span { class: "pill", "Total PNL Active Positions: --" }
                    span { class: "pill", "Total PNL Closed Positions: --" }
                    span { class: "pill", "Bot Status: OFF" }
                    span { class: "pill", "Bot Active Time: --" }
                }
            }
            nav { class: "tabs",
                for item in trading_app_tabs() {
                    button {
                        class: if item.key == selected_key { "tab active" } else { "tab" },
                        onclick: move |_| selected_tab_key.set(item.key),
                        "{item.title}"
                    }
                }
            }
            section { class: "workspace",
                div { class: "section-head",
                    div {
                        h2 { "{tab.title}" }
                        p { class: "label", "{tab.summary}" }
                    }
                    div { class: "actions",
                        for action in tab.actions {
                            button { class: "action", "{action}" }
                        }
                    }
                }
                div { class: "metrics",
                    div { class: "panel",
                        div { class: "label", "Status" }
                        strong { "{tab.status}" }
                    }
                    div { class: "panel",
                        div { class: "label", "Primary" }
                        strong { "{tab.primary_metric}" }
                    }
                    div { class: "panel",
                        div { class: "label", "Secondary" }
                        strong { "{tab.secondary_metric}" }
                    }
                }
                div { class: "cards",
                    for section in tab.sections {
                        div { class: "panel",
                            h3 { "{section.title}" }
                            ul {
                                for item in section.items {
                                    li { "{item}" }
                                }
                            }
                        }
                    }
                    for table in tab.tables {
                        div { class: "panel",
                            h3 { "{table.title}" }
                            ul {
                                for column in table.columns {
                                    li { "{column}" }
                                }
                            }
                        }
                    }
                    div { class: "panel",
                        h3 { "Service API Integration" }
                        ul {
                            for capability in service_api_capabilities() {
                                li { "{capability.title}: {capability.detail}" }
                            }
                        }
                        p { "Standalone Rust trading execution supported: {rust_exec_supported}" }
                        ul {
                            for mode in rust_execution_modes() {
                                li { "{mode.title}: {mode.detail} | trading_execution_supported={mode.trading_execution_supported}" }
                            }
                        }
                        h3 { "Framework Parity" }
                        ul {
                            for parity in rust_shell_framework_parity() {
                                li { "{parity.framework} - {parity.status}: {parity.detail}" }
                            }
                        }
                        h3 { "Native Runtime Gap" }
                        p { "Native Rust trading runtime ready: {rust_native_ready}" }
                        ul {
                            for capability in rust_native_runtime_capabilities() {
                                li { "{capability.key} - {capability.title} | C++: {capability.cpp_status} | Rust: {capability.rust_status} | Required before enable: {capability.required_before_enable} | trading_execution_supported={capability.trading_execution_supported}" }
                            }
                        }
                        h3 { "Full Python App Parity Audit" }
                        p { "Entire Python app parity ready: {full_python_app_parity_ready}" }
                        p { "C++ entire Python app parity ready: {cpp_python_app_parity_ready}" }
                        p { "Rust entire Python app parity ready: {rust_python_app_parity_ready}" }
                        ul {
                            for domain in native_python_app_parity_domains() {
                                li { "{domain.key} - {domain.title} | Python: {domain.python_surface} | C++: {domain.cpp_status} | Rust: {domain.rust_status} | Required before full parity: {domain.required_before_full_parity} | cpp_full_parity={domain.cpp_full_parity} | rust_full_parity={domain.rust_full_parity}" }
                            }
                        }
                        h3 { "Canonical Routes" }
                        ul {
                            for route in service_api_routes() {
                                li { "{route.methods.join(\"/\")} {route.path} ({route.name})" }
                            }
                        }
                    }
                }
            }
            footer { class: "footer",
                span { "Total PNL Active Positions: --" }
                span { "Total PNL Closed Positions: --" }
                span { "Bot Status: OFF" }
                span { "Bot Active Time: --" }
            }
        }
    }
}
