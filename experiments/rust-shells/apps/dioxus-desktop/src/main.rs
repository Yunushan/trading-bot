#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use dioxus::prelude::*;
use trading_bot_core::{
    TradingAppTab, app_banner, rust_execution_modes, rust_trading_execution_supported,
    service_api_capabilities, service_api_routes, trading_app_tabs,
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

    rsx! {
        style { "{APP_STYLE}" }
        main { class: "app-shell",
            header { class: "topbar",
                div {
                    h1 { "{banner}" }
                    p { class: "label", "Rust desktop shell mirroring Python and C++ tabs." }
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
