#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductEntrypointContract {
    pub product: &'static str,
    pub canonical_repo_path: &'static str,
    pub canonical_module: &'static str,
    pub installed_command: &'static str,
    pub compatibility_entrypoint: &'static str,
    pub compatibility_status: &'static str,
}

impl ProductEntrypointContract {
    pub fn compatibility_notice(&self) -> String {
        format!(
            "Deprecated compatibility {} entrypoint remains available via '{}'. Prefer '{}' or the installed command '{}'.",
            self.product,
            self.compatibility_entrypoint,
            self.canonical_repo_path,
            self.installed_command
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeStartupPackagingContract {
    pub native_surface: &'static str,
    pub product_name: &'static str,
    pub identifier: &'static str,
    pub app_user_model_id: &'static str,
    pub icon_resource: &'static str,
    pub startup_suppression_env: &'static [&'static str],
    pub release_smoke_commands: &'static [&'static str],
    pub delegates_trading_execution_to_python: bool,
}

pub const DESKTOP_ENTRYPOINT_CONTRACT: ProductEntrypointContract = ProductEntrypointContract {
    product: "desktop",
    canonical_repo_path: "apps/desktop-pyqt/main.py",
    canonical_module: "app.desktop.product_main",
    installed_command: "trading-bot-desktop",
    compatibility_entrypoint: "Languages/Python/main.py",
    compatibility_status: "deprecated",
};

pub const SERVICE_ENTRYPOINT_CONTRACT: ProductEntrypointContract = ProductEntrypointContract {
    product: "service",
    canonical_repo_path: "apps/service-api/main.py",
    canonical_module: "app.service.product_main",
    installed_command: "trading-bot-service",
    compatibility_entrypoint: "python -m app.service.main",
    compatibility_status: "deprecated",
};

pub const CPP_STARTUP_PACKAGING_CONTRACT: NativeStartupPackagingContract =
    NativeStartupPackagingContract {
        native_surface: "cpp-qt",
        product_name: "Trading-Bot-C++",
        identifier: "TradingBot.Desktop.Cpp",
        app_user_model_id: "TradingBot.Desktop.Cpp",
        icon_resource: ":/app_icon.ico",
        startup_suppression_env: &[
            "BOT_DISABLE_PYTHONW_RELAUNCH",
            "BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH",
        ],
        release_smoke_commands: &[
            "cmake --build build/binance_cpp --config Release",
            "build/binance_cpp/Release/Trading-Bot-C++.exe",
        ],
        delegates_trading_execution_to_python: true,
    };

pub const RUST_TAURI_STARTUP_PACKAGING_CONTRACT: NativeStartupPackagingContract =
    NativeStartupPackagingContract {
        native_surface: "rust-tauri",
        product_name: "Trading Bot Tauri",
        identifier: "com.tradingbot.tauri",
        app_user_model_id: "com.tradingbot.tauri",
        icon_resource: "tauri.conf.json",
        startup_suppression_env: &[
            "BOT_DISABLE_PYTHONW_RELAUNCH",
            "BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH",
        ],
        release_smoke_commands: &[
            "cargo build --workspace",
            "node apps/tauri-desktop/ui/tauri-ui-behavior.test.cjs",
        ],
        delegates_trading_execution_to_python: true,
    };

pub fn python_product_entrypoint_contracts() -> &'static [ProductEntrypointContract] {
    &[DESKTOP_ENTRYPOINT_CONTRACT, SERVICE_ENTRYPOINT_CONTRACT]
}

pub fn native_startup_packaging_contracts() -> &'static [NativeStartupPackagingContract] {
    &[
        CPP_STARTUP_PACKAGING_CONTRACT,
        RUST_TAURI_STARTUP_PACKAGING_CONTRACT,
    ]
}

pub fn startup_suppression_env_is_required(name: impl AsRef<str>) -> bool {
    let name = name.as_ref().trim();
    CPP_STARTUP_PACKAGING_CONTRACT
        .startup_suppression_env
        .contains(&name)
        && RUST_TAURI_STARTUP_PACKAGING_CONTRACT
            .startup_suppression_env
            .contains(&name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_product_entrypoints_match_canonical_contracts() {
        assert_eq!(
            DESKTOP_ENTRYPOINT_CONTRACT.canonical_repo_path,
            "apps/desktop-pyqt/main.py"
        );
        assert_eq!(
            DESKTOP_ENTRYPOINT_CONTRACT.canonical_module,
            "app.desktop.product_main"
        );
        assert_eq!(
            SERVICE_ENTRYPOINT_CONTRACT.canonical_repo_path,
            "apps/service-api/main.py"
        );
        assert_eq!(
            SERVICE_ENTRYPOINT_CONTRACT.canonical_module,
            "app.service.product_main"
        );
        assert!(
            DESKTOP_ENTRYPOINT_CONTRACT
                .compatibility_notice()
                .contains("Deprecated compatibility desktop entrypoint")
        );
        assert!(
            SERVICE_ENTRYPOINT_CONTRACT
                .compatibility_notice()
                .contains("trading-bot-service")
        );
    }

    #[test]
    fn native_startup_packaging_contracts_capture_platform_metadata() {
        let contracts = native_startup_packaging_contracts();
        assert_eq!(contracts.len(), 2);
        assert_eq!(contracts[0].identifier, "TradingBot.Desktop.Cpp");
        assert_eq!(contracts[0].app_user_model_id, "TradingBot.Desktop.Cpp");
        assert_eq!(contracts[1].product_name, "Trading Bot Tauri");
        assert_eq!(contracts[1].identifier, "com.tradingbot.tauri");
        for contract in contracts {
            assert!(contract.delegates_trading_execution_to_python);
            assert!(
                contract
                    .startup_suppression_env
                    .contains(&"BOT_DISABLE_PYTHONW_RELAUNCH")
            );
            assert!(
                contract
                    .startup_suppression_env
                    .contains(&"BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH")
            );
            assert!(!contract.release_smoke_commands.is_empty());
        }
        assert!(startup_suppression_env_is_required(
            "BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH"
        ));
    }
}
