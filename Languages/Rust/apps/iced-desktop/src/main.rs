#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use iced::{
    widget::{column, text},
    Element, Fill,
};
use trading_bot_core::app_banner;

#[derive(Default)]
struct TradingBotIced;

#[derive(Debug, Clone)]
enum Message {}

fn update(_state: &mut TradingBotIced, _message: Message) {}

fn view(_state: &TradingBotIced) -> Element<'_, Message> {
    column![
        text(app_banner("Iced")).size(32),
        text("Shared Rust core scaffold wired to the Iced desktop shell."),
    ]
    .spacing(12)
    .padding(24)
    .width(Fill)
    .into()
}

fn main() -> iced::Result {
    iced::application("Trading Bot Iced", update, view).run()
}
