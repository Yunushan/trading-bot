use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DesktopShellTabContract {
    pub key: &'static str,
    pub title: &'static str,
    pub load_policy: &'static str,
    pub placeholder_message: &'static str,
    pub activation_hooks: &'static [&'static str],
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DesktopShellThemeContract {
    pub requested: String,
    pub stored_name: String,
    pub palette: String,
    pub chart_theme: String,
    pub accent_color: Option<String>,
}

pub const PYTHON_LAZY_SECONDARY_TAB_PROPERTY: &str = "_bot_lazy_secondary_tab_key";
pub const DESKTOP_SHELL_PARITY_BOUNDARIES: &[&str] = &[
    "Dashboard-first startup composition",
    "Chart, Positions, Backtest, Liquidation Heatmap, and Code Languages primary tab order",
    "Backtest, Liquidation Heatmap, and Code Languages lazy placeholder lifecycle",
    "Code tab window-suppression and dependency auto-refresh hooks",
    "Chart safe-mode and code-to-chart deferred reload hooks",
    "Theme persistence and chart-theme forwarding",
    "Rust Tauri operational Service API ownership as the only user-selectable Rust desktop shell",
];

pub fn desktop_shell_tabs() -> &'static [DesktopShellTabContract] {
    &[
        DesktopShellTabContract {
            key: "dashboard",
            title: "Dashboard",
            load_policy: "startup",
            placeholder_message: "",
            activation_hooks: &["dashboard_runtime_state", "dashboard_chart_section"],
        },
        DesktopShellTabContract {
            key: "chart",
            title: "Chart",
            load_policy: "startup",
            placeholder_message: "",
            activation_hooks: &[
                "chart_safe_mode_guard",
                "tradingview_external_fallback",
                "lightweight_chart_refresh",
                "dashboard_selection_auto_follow",
            ],
        },
        DesktopShellTabContract {
            key: "positions",
            title: "Positions",
            load_policy: "startup",
            placeholder_message: "",
            activation_hooks: &["positions_table_refresh", "closed_history_reconciliation"],
        },
        DesktopShellTabContract {
            key: "backtest",
            title: "Backtest",
            load_policy: "lazy-placeholder",
            placeholder_message: "Backtest tools load the first time you open this tab.",
            activation_hooks: &[
                "create_backtest_tab",
                "refresh_symbol_interval_pairs",
                "initialize_backtest_ui_defaults",
                "update_connector_labels",
            ],
        },
        DesktopShellTabContract {
            key: "liquidation",
            title: "Liquidation Heatmap",
            load_policy: "lazy-placeholder",
            placeholder_message: "Liquidation heatmaps load the first time you open this tab.",
            activation_hooks: &["init_liquidation_heatmap_tab"],
        },
        DesktopShellTabContract {
            key: "code",
            title: "Code Languages",
            load_policy: "lazy-placeholder",
            placeholder_message: "Code language tools load the first time you open this tab.",
            activation_hooks: &[
                "start_code_tab_window_suppression",
                "init_code_language_tab",
                "dependency_usage_auto_poll",
                "dependency_versions_auto_refresh",
            ],
        },
    ]
}

pub fn primary_tab_titles() -> Vec<&'static str> {
    desktop_shell_tabs().iter().map(|tab| tab.title).collect()
}

pub fn lazy_secondary_tab_keys() -> Vec<&'static str> {
    desktop_shell_tabs()
        .iter()
        .filter(|tab| tab.load_policy == "lazy-placeholder")
        .map(|tab| tab.key)
        .collect()
}

pub fn lazy_secondary_tab_load_delay_ms(
    key: &str,
    platform: &str,
    env_override: Option<&str>,
) -> u64 {
    if key.trim().to_lowercase() != "code" {
        return 0;
    }
    let default_delay =
        if platform.eq_ignore_ascii_case("win32") || platform.eq_ignore_ascii_case("windows") {
            90
        } else {
            0
        };
    env_override
        .and_then(|value| value.trim().parse::<i64>().ok())
        .unwrap_or(default_delay)
        .clamp(0, 1000) as u64
}

pub fn lazy_secondary_tab_prewarm_enabled(platform: &str, env_flag: Option<&str>) -> bool {
    if !platform.eq_ignore_ascii_case("win32") && !platform.eq_ignore_ascii_case("windows") {
        return false;
    }
    let flag = env_flag.unwrap_or("0").trim().to_lowercase();
    !matches!(flag.as_str(), "0" | "false" | "no" | "off")
}

pub fn build_desktop_startup_contract(platform: &str, preload_flag: Option<&str>) -> Value {
    json!({
        "root_widget": "QTabWidget",
        "startup_tab": "Dashboard",
        "tab_bar_event_filter": true,
        "current_changed_handler": "_on_tab_changed",
        "tab_bar_clicked_handler": "_on_tab_bar_clicked",
        "lazy_property": PYTHON_LAZY_SECONDARY_TAB_PROPERTY,
        "lazy_tabs": lazy_secondary_tab_keys(),
        "prewarm_keys": ["code", "backtest"],
        "prewarm_enabled": lazy_secondary_tab_prewarm_enabled(platform, preload_flag),
        "first_visible_sections": [
            "Dashboard header",
            "Markets & Intervals",
            "Strategy Controls",
            "Indicators",
            "Symbol / Interval Overrides",
            "Desktop Service API",
            "Logs"
        ],
    })
}

pub fn build_tab_activation_effect(
    tab_key: &str,
    chart_mode: &str,
    safe_chart_mode: bool,
    recent_code_switch: bool,
    code_language_is_cpp: bool,
) -> Value {
    let key = tab_key.trim().to_lowercase();
    if key == "code" {
        return json!({
            "tab": "code",
            "start_dependency_usage_auto_poll": true,
            "schedule_dependency_versions_auto_refresh": true,
            "start_code_tab_window_suppression": true,
            "maybe_auto_prepare_cpp_environment": code_language_is_cpp,
            "cancel_code_auto_refresh": false,
        });
    }
    if key == "chart" {
        let mode = chart_mode.trim().to_lowercase();
        return json!({
            "tab": "chart",
            "stop_dependency_usage_auto_poll": true,
            "cancel_code_auto_refresh": true,
            "safe_mode_redirect": safe_chart_mode && matches!(mode.as_str(), "tradingview" | "original" | "lightweight"),
            "defer_after_code_switch": recent_code_switch,
            "load_chart": true,
            "dashboard_selection_auto_follow": true,
        });
    }
    if ["backtest", "liquidation"].contains(&key.as_str()) {
        return json!({
            "tab": key,
            "lazy_load_on_first_open": true,
            "only_if_current": false,
            "cancel_code_auto_refresh": true,
        });
    }
    json!({
        "tab": key,
        "stop_dependency_usage_auto_poll": true,
        "cancel_code_auto_refresh": true,
    })
}

pub fn normalize_desktop_theme(name: &str) -> DesktopShellThemeContract {
    let raw = name.trim().to_lowercase();
    let normalized = if raw == "gren" { "green" } else { raw.as_str() };
    let palette = if normalized.starts_with("dark")
        || matches!(normalized, "blue" | "yellow" | "green" | "red")
    {
        "dark"
    } else {
        "light"
    };
    let accent_color = match normalized {
        "blue" => Some("#3b82f6".to_owned()),
        "yellow" => Some("#f59e0b".to_owned()),
        "green" => Some("#22c55e".to_owned()),
        "red" => Some("#ef4444".to_owned()),
        _ => None,
    };
    let stored = if normalized.is_empty() {
        "Dark".to_owned()
    } else {
        title_case(normalized)
    };
    DesktopShellThemeContract {
        requested: name.to_owned(),
        stored_name: stored,
        palette: palette.to_owned(),
        chart_theme: if palette == "light" { "light" } else { "dark" }.to_owned(),
        accent_color,
    }
}

pub fn rust_desktop_shell_ownership_contract() -> Value {
    json!({
        "tauri": {
            "status": "operational-service-api-client",
            "owns_local_python_service_lifecycle": true,
            "owns_trading_execution": false,
            "primary_tabs": primary_tab_titles(),
        },
        "execution_boundary": "Python service/desktop runtime remains the trading execution owner.",
    })
}

fn title_case(value: &str) -> String {
    let mut chars = value.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn desktop_shell_tab_contract_matches_python_main_window_order() {
        assert_eq!(
            primary_tab_titles(),
            vec![
                "Dashboard",
                "Chart",
                "Positions",
                "Backtest",
                "Liquidation Heatmap",
                "Code Languages"
            ]
        );
        let tabs = desktop_shell_tabs();
        assert_eq!(tabs[0].load_policy, "startup");
        assert_eq!(
            tabs[3].placeholder_message,
            "Backtest tools load the first time you open this tab."
        );
        assert_eq!(
            tabs[5].placeholder_message,
            "Code language tools load the first time you open this tab."
        );
        assert!(
            tabs[5]
                .activation_hooks
                .contains(&"start_code_tab_window_suppression")
        );
    }

    #[test]
    fn lazy_secondary_tab_lifecycle_matches_python_placeholders_and_prewarm() {
        assert_eq!(
            lazy_secondary_tab_keys(),
            vec!["backtest", "liquidation", "code"]
        );
        assert_eq!(lazy_secondary_tab_load_delay_ms("code", "win32", None), 90);
        assert_eq!(
            lazy_secondary_tab_load_delay_ms("code", "win32", Some("1500")),
            1000
        );
        assert_eq!(
            lazy_secondary_tab_load_delay_ms("backtest", "win32", Some("99")),
            0
        );
        assert!(!lazy_secondary_tab_prewarm_enabled("linux", Some("1")));
        assert!(lazy_secondary_tab_prewarm_enabled("win32", Some("true")));

        let startup = build_desktop_startup_contract("win32", Some("1"));
        assert_eq!(startup["startup_tab"], "Dashboard");
        assert_eq!(startup["lazy_property"], PYTHON_LAZY_SECONDARY_TAB_PROPERTY);
        assert_eq!(
            startup["lazy_tabs"],
            json!(["backtest", "liquidation", "code"])
        );
        assert_eq!(startup["prewarm_keys"], json!(["code", "backtest"]));
        assert_eq!(startup["prewarm_enabled"], true);
    }

    #[test]
    fn tab_change_effects_match_python_code_chart_guards() {
        let code = build_tab_activation_effect("code", "", false, false, true);
        assert_eq!(code["start_dependency_usage_auto_poll"], true);
        assert_eq!(code["schedule_dependency_versions_auto_refresh"], true);
        assert_eq!(code["maybe_auto_prepare_cpp_environment"], true);

        let chart = build_tab_activation_effect("chart", "tradingview", true, true, false);
        assert_eq!(chart["safe_mode_redirect"], true);
        assert_eq!(chart["defer_after_code_switch"], true);
        assert_eq!(chart["cancel_code_auto_refresh"], true);
        assert_eq!(chart["dashboard_selection_auto_follow"], true);

        let backtest = build_tab_activation_effect("backtest", "", false, false, false);
        assert_eq!(backtest["lazy_load_on_first_open"], true);
    }

    #[test]
    fn theme_and_rust_shell_ownership_contract_match_python_boundaries() {
        let green = normalize_desktop_theme("gren");
        assert_eq!(green.stored_name, "Green");
        assert_eq!(green.palette, "dark");
        assert_eq!(green.chart_theme, "dark");
        assert_eq!(green.accent_color.as_deref(), Some("#22c55e"));

        let light = normalize_desktop_theme("Light");
        assert_eq!(light.palette, "light");
        assert_eq!(light.chart_theme, "light");

        let ownership = rust_desktop_shell_ownership_contract();
        assert_eq!(
            ownership["tauri"]["owns_local_python_service_lifecycle"],
            true
        );
        assert_eq!(ownership["tauri"]["owns_trading_execution"], false);
        let ownership_object = ownership.as_object().expect("ownership contract object");
        assert!(ownership_object.contains_key("tauri"));
        assert!(ownership_object.contains_key("execution_boundary"));
        assert_eq!(ownership_object.len(), 2);
        assert_eq!(
            ownership["execution_boundary"],
            "Python service/desktop runtime remains the trading execution owner."
        );
    }
}
