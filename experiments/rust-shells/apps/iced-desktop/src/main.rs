#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use iced::{
    Element, Fill,
    widget::{button, column, container, row, scrollable, text},
};
use trading_bot_core::{
    TradingAppTab, app_banner, cpp_entire_python_app_parity_ready,
    native_full_python_app_parity_ready, native_python_app_parity_domains,
    rust_entire_python_app_parity_ready, rust_execution_modes, rust_native_runtime_capabilities,
    rust_native_trading_runtime_ready, rust_shell_framework_parity,
    rust_trading_execution_supported, service_api_capabilities, service_api_routes,
    trading_app_tabs,
};

struct TradingBotIced {
    selected_tab_key: &'static str,
}

impl Default for TradingBotIced {
    fn default() -> Self {
        Self {
            selected_tab_key: trading_app_tabs()
                .first()
                .map(|tab| tab.key)
                .unwrap_or("dashboard"),
        }
    }
}

#[derive(Debug, Clone)]
enum Message {
    SelectTab(&'static str),
}

fn update(state: &mut TradingBotIced, message: Message) {
    match message {
        Message::SelectTab(tab_key) => {
            state.selected_tab_key = tab_key;
        }
    }
}

fn selected_tab(state: &TradingBotIced) -> &'static TradingAppTab {
    trading_app_tabs()
        .iter()
        .find(|tab| tab.key == state.selected_tab_key)
        .or_else(|| trading_app_tabs().first())
        .expect("trading app tabs must not be empty")
}

fn action_row(tab: &'static TradingAppTab) -> Element<'static, Message> {
    let mut actions = row![].spacing(8);
    for action in tab.actions {
        actions = actions.push(button(text(*action)));
    }
    actions.into()
}

fn sections(tab: &'static TradingAppTab) -> Element<'static, Message> {
    let mut body = column![].spacing(12);
    for section in tab.sections {
        let mut group = column![text(section.title).size(20)].spacing(6);
        for item in section.items {
            group = group.push(text(*item));
        }
        body = body.push(container(group).padding(12).width(Fill));
    }
    for table in tab.tables {
        let mut group = column![text(table.title).size(20)].spacing(6);
        group = group.push(text(table.columns.join(" | ")));
        group = group.push(text("--"));
        body = body.push(container(group).padding(12).width(Fill));
    }
    body.into()
}

fn service_api_panel() -> Element<'static, Message> {
    let mut body = column![text("Service API Integration").size(20)].spacing(6);
    for capability in service_api_capabilities() {
        body = body.push(text(capability.title));
        body = body.push(text(capability.detail));
    }
    body = body.push(text(format!(
        "Standalone Rust trading execution supported: {}",
        rust_trading_execution_supported()
    )));
    for mode in rust_execution_modes() {
        body = body.push(text(mode.title));
        body = body.push(text(format!(
            "{} | trading_execution_supported={}",
            mode.detail, mode.trading_execution_supported
        )));
    }
    body = body.push(text("Framework Parity"));
    for parity in rust_shell_framework_parity() {
        body = body.push(text(format!(
            "{} - {}: {}",
            parity.framework, parity.status, parity.detail
        )));
    }
    body = body.push(text(format!(
        "Native Rust trading runtime ready: {}",
        rust_native_trading_runtime_ready()
    )));
    body = body.push(text("Native Runtime Gap"));
    for capability in rust_native_runtime_capabilities() {
        body = body.push(text(format!(
            "{} - {} | C++: {} | Rust: {} | Required before enable: {} | trading_execution_supported={}",
            capability.key,
            capability.title,
            capability.cpp_status,
            capability.rust_status,
            capability.required_before_enable,
            capability.trading_execution_supported
        )));
    }
    body = body.push(text(format!(
        "Entire Python app parity ready: {}",
        native_full_python_app_parity_ready()
    )));
    body = body.push(text(format!(
        "C++ entire Python app parity ready: {}",
        cpp_entire_python_app_parity_ready()
    )));
    body = body.push(text(format!(
        "Rust entire Python app parity ready: {}",
        rust_entire_python_app_parity_ready()
    )));
    body = body.push(text("Full Python App Parity Audit"));
    for domain in native_python_app_parity_domains() {
        body = body.push(text(format!(
            "{} - {} | Python: {} | C++: {} | Rust: {} | Required before full parity: {} | cpp_full_parity={} | rust_full_parity={}",
            domain.key,
            domain.title,
            domain.python_surface,
            domain.cpp_status,
            domain.rust_status,
            domain.required_before_full_parity,
            domain.cpp_full_parity,
            domain.rust_full_parity
        )));
    }
    body = body.push(text("Canonical routes"));
    for route in service_api_routes() {
        body = body.push(text(format!(
            "{} {} ({})",
            route.methods.join("/"),
            route.path,
            route.name
        )));
    }
    container(body).padding(12).width(Fill).into()
}

fn tab_body(tab: &'static TradingAppTab) -> Element<'static, Message> {
    column![
        text(tab.title).size(28),
        text(tab.summary),
        action_row(tab),
        row![text("Status").width(160), text(tab.status)],
        row![text("Primary").width(160), text(tab.primary_metric)],
        row![text("Secondary").width(160), text(tab.secondary_metric)],
        sections(tab),
        service_api_panel(),
    ]
    .spacing(12)
    .into()
}

fn view(state: &TradingBotIced) -> Element<'_, Message> {
    let mut tab_bar = row![].spacing(6);
    for tab in trading_app_tabs() {
        let label = if tab.key == state.selected_tab_key {
            format!("[{}]", tab.title)
        } else {
            tab.title.to_owned()
        };
        tab_bar = tab_bar.push(button(text(label)).on_press(Message::SelectTab(tab.key)));
    }

    let tab = selected_tab(state);
    let header = row![
        text(app_banner("Iced")).size(26),
        text("Total PNL Active Positions: --"),
        text("Total PNL Closed Positions: --"),
        text("Bot Status: OFF"),
        text("Bot Active Time: --"),
    ]
    .spacing(18);
    let footer = row![
        text("Total PNL Active Positions: --"),
        text("Total PNL Closed Positions: --"),
        text("Bot Status: OFF"),
        text("Bot Active Time: --"),
    ]
    .spacing(18);

    container(
        column![header, tab_bar, scrollable(tab_body(tab)), footer]
            .spacing(16)
            .padding(24)
            .width(Fill)
            .height(Fill),
    )
    .width(Fill)
    .height(Fill)
    .into()
}

fn main() -> iced::Result {
    iced::application("Trading Bot Iced", update, view).run()
}
