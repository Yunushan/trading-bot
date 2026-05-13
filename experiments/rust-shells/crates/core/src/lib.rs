use trading_bot_contracts::AppIdentity;

pub fn app_banner(shell: &str) -> String {
    format!("Trading Bot Rust scaffold -> {shell}")
}

pub fn default_identity(shell: &str) -> AppIdentity {
    AppIdentity::new(shell)
}

pub fn supported_frameworks() -> &'static [&'static str] {
    &["Tauri", "Slint", "egui", "Iced", "Dioxus Desktop"]
}

pub struct TradingAppTab {
    pub key: &'static str,
    pub title: &'static str,
    pub status: &'static str,
    pub primary_metric: &'static str,
    pub secondary_metric: &'static str,
    pub summary: &'static str,
    pub actions: &'static [&'static str],
    pub sections: &'static [TradingAppSection],
    pub tables: &'static [TradingAppTable],
}

pub struct TradingAppSection {
    pub title: &'static str,
    pub items: &'static [&'static str],
}

pub struct TradingAppTable {
    pub title: &'static str,
    pub columns: &'static [&'static str],
}

pub struct ServiceApiRoute {
    pub name: &'static str,
    pub path: &'static str,
    pub methods: &'static [&'static str],
}

pub struct ServiceApiCapability {
    pub title: &'static str,
    pub detail: &'static str,
}

pub struct RustExecutionMode {
    pub key: &'static str,
    pub title: &'static str,
    pub detail: &'static str,
    pub trading_execution_supported: bool,
}

pub const SERVICE_API_BASE_PATH: &str = "/api/v1";

pub fn rust_trading_execution_supported() -> bool {
    false
}

pub fn rust_execution_modes() -> &'static [RustExecutionMode] {
    &[
        RustExecutionMode {
            key: "service_client",
            title: "Service client",
            detail: "Rust shells read dashboard state and submit lifecycle/config/backtest requests through the canonical Python Service API.",
            trading_execution_supported: false,
        },
        RustExecutionMode {
            key: "tauri_managed_service",
            title: "Tauri managed local service",
            detail: "Tauri may launch apps/service-api/main.py locally, but the Python runtime remains the only active strategy, risk, and exchange execution owner.",
            trading_execution_supported: false,
        },
        RustExecutionMode {
            key: "native_engine_future",
            title: "Native Rust trading engine",
            detail: "Reserved until a Rust engine reaches feature parity with Python strategy controls, order audit, risk gates, and connector safeguards.",
            trading_execution_supported: false,
        },
    ]
}

pub fn service_api_capabilities() -> &'static [ServiceApiCapability] {
    &[
        ServiceApiCapability {
            title: "Managed Local Service API",
            detail: "Tauri can launch apps/service-api/main.py --serve on 127.0.0.1 and stop only the process it started.",
        },
        ServiceApiCapability {
            title: "Canonical /api/v1 Contract",
            detail: "Rust shells use the same dashboard, config, start/stop, backtest, logs, LLM, and preflight routes as Python, web, and mobile clients.",
        },
        ServiceApiCapability {
            title: "Config Hydration",
            detail: "Tauri refreshes dashboard/config snapshots and hydrates visible runtime, account, stop-loss, LLM, symbol, interval, strategy, and backtest controls.",
        },
        ServiceApiCapability {
            title: "Execution Boundary",
            detail: "Python service/desktop runtime remains the trading execution owner; Rust shells are clients and must not bypass strategy, risk, or exchange guards.",
        },
    ]
}

pub fn service_api_routes() -> &'static [ServiceApiRoute] {
    &[
        ServiceApiRoute {
            name: "dashboard",
            path: "/api/v1/dashboard",
            methods: &["GET"],
        },
        ServiceApiRoute {
            name: "status",
            path: "/api/v1/status",
            methods: &["GET"],
        },
        ServiceApiRoute {
            name: "execution",
            path: "/api/v1/execution",
            methods: &["GET"],
        },
        ServiceApiRoute {
            name: "backtest",
            path: "/api/v1/backtest",
            methods: &["GET"],
        },
        ServiceApiRoute {
            name: "config",
            path: "/api/v1/config",
            methods: &["GET", "PUT", "PATCH"],
        },
        ServiceApiRoute {
            name: "config_save",
            path: "/api/v1/config/save",
            methods: &["POST"],
        },
        ServiceApiRoute {
            name: "config_load",
            path: "/api/v1/config/load",
            methods: &["POST"],
        },
        ServiceApiRoute {
            name: "operational_preflight",
            path: "/api/v1/runtime/operational-preflight",
            methods: &["GET"],
        },
        ServiceApiRoute {
            name: "control_start",
            path: "/api/v1/control/start",
            methods: &["POST"],
        },
        ServiceApiRoute {
            name: "control_stop",
            path: "/api/v1/control/stop",
            methods: &["POST"],
        },
        ServiceApiRoute {
            name: "backtest_run",
            path: "/api/v1/backtest/run",
            methods: &["POST"],
        },
        ServiceApiRoute {
            name: "backtest_stop",
            path: "/api/v1/backtest/stop",
            methods: &["POST"],
        },
        ServiceApiRoute {
            name: "logs",
            path: "/api/v1/logs",
            methods: &["GET", "POST"],
        },
        ServiceApiRoute {
            name: "llm_config",
            path: "/api/v1/llm/config",
            methods: &["GET", "PATCH"],
        },
        ServiceApiRoute {
            name: "llm_providers",
            path: "/api/v1/llm/providers",
            methods: &["GET"],
        },
    ]
}

pub fn service_api_route_path(name: &str) -> Option<&'static str> {
    service_api_routes()
        .iter()
        .find(|route| route.name == name)
        .map(|route| route.path)
}

pub fn trading_app_tabs() -> &'static [TradingAppTab] {
    &[
        TradingAppTab {
            key: "dashboard",
            title: "Dashboard",
            status: "Bot Status: OFF",
            primary_metric: "Active PNL: 0.00 USDT",
            secondary_metric: "Closed PNL: 0.00 USDT",
            summary: "Main desktop trading controls mirrored from the Python and C++ dashboards.",
            actions: &["Start", "Stop", "Save Config", "Load Config"],
            sections: &[
                TradingAppSection {
                    title: "Account & Status",
                    items: &[
                        "API Key:",
                        "API Secret Key:",
                        "Mode: Live, Demo, Testnet",
                        "Theme: Light, Dark, Blue, Yellow, Green, Red",
                        "Account Type: Spot, Futures",
                        "Account Mode: Classic Trading, Portfolio Margin",
                        "Connector: Binance SDK Derivatives Trading USD-S Futures, Binance SDK Derivatives Trading COIN-M Futures, Binance SDK Spot, Binance Connector Python, CCXT, python-binance",
                        "Total USDT balance: N/A",
                        "Position Mode: N/A",
                        "Refresh Balance",
                        "Leverage (Futures): 1-150",
                        "Margin Mode (Futures): Cross, Isolated",
                        "Position Mode: One-way, Hedge",
                        "Assets Mode: Single-Asset Mode, Multi-Assets Mode",
                        "Time-in-Force: GTC, IOC, FOK, GTD",
                        "GTD minutes: 1-1440",
                        "Indicator Source: Binance spot, Binance futures, TradingView, Bybit, Coinbase, OKX, Gate, Bitget, Mexc, Kucoin, HTX, Kraken",
                    ],
                },
                TradingAppSection {
                    title: "AI / LLM Settings",
                    items: &[
                        "Enable LLM assistance",
                        "Allow public network endpoint",
                        "Provider:",
                        "Model:",
                        "Base URL / IP:",
                        "API key env:",
                        "API token:",
                        "Use for: Advisory, Signal confirmation, Risk review, Backtest explanation",
                        "Reasoning / Thinking:",
                        "Apply LLM Settings",
                        "Check / Download Local Model",
                        "Remove Local Model",
                    ],
                },
                TradingAppSection {
                    title: "Exchange",
                    items: &["Select exchange", "Binance"],
                },
                TradingAppSection {
                    title: "Markets & Intervals",
                    items: &[
                        "Symbols (select 1 or more):",
                        "Refresh Symbols",
                        "Intervals (select 1 or more):",
                        "Custom interval input: e.g., 45s or 7m or 90m, comma-separated",
                        "Add Custom Interval(s)",
                    ],
                },
                TradingAppSection {
                    title: "Strategy Controls",
                    items: &[
                        "Side: Buy (Long), Sell (Short), Both (Long/Short)",
                        "Position % of Balance:",
                        "Loop Interval Override: 30 seconds, 45 seconds, 1 minute, 2 minutes, 3 minutes, 5 minutes, 10 minutes, 30 minutes, 1 hour, 2 hours",
                        "Enable Lead Trader",
                        "Lead Trader: Futures Public Lead Trader, Futures Private Lead Trader, Spot Public Lead Trader, Spot Private Lead Trader",
                        "Use live candle values for signals (repaints)",
                        "Add-only in current net direction (one-way)",
                        "Allow simultaneous long & short positions (hedge stacking)",
                        "Stop Bot Without Closing Active Positions",
                        "Market Close All Active Positions On Window Close (Working in progress)",
                        "Stop Loss: Enable",
                        "Stop Loss Mode: USDT Based Stop Loss, Percentage Based Stop Loss, Both Stop Loss (USDT & Percentage)",
                        "Stop Loss USDT",
                        "Stop Loss %",
                        "Stop Loss Scope: Per Trade Stop Loss, Cumulative Stop Loss, Entire Account Stop Loss",
                        "Template: No Template, Top 10 %2 per trade 1x Isolated, Top 50 %2 per trade 1x, Top 100 %1 per trade 1x",
                    ],
                },
                TradingAppSection {
                    title: "Indicators",
                    items: &[
                        "Moving Average (MA) + Buy-Sell Values",
                        "Donchian Channels (DC) + Buy-Sell Values",
                        "Parabolic SAR (PSAR) + Buy-Sell Values",
                        "Bollinger Bands (BB) + Buy-Sell Values",
                        "Relative Strength Index (RSI) + Buy-Sell Values",
                        "Volume + Buy-Sell Values",
                        "Stochastic RSI (SRSI) + Buy-Sell Values",
                        "Williams %R + Buy-Sell Values",
                        "Moving Average Convergence/Divergence (MACD) + Buy-Sell Values",
                        "Ultimate Oscillator (UO) + Buy-Sell Values",
                        "Average Directional Index (ADX) + Buy-Sell Values",
                        "Directional Movement Index (DMI) + Buy-Sell Values",
                        "SuperTrend (ST) + Buy-Sell Values",
                        "Exponential Moving Average (EMA) + Buy-Sell Values",
                        "Stochastic Oscillator + Buy-Sell Values",
                    ],
                },
                TradingAppSection {
                    title: "Desktop Service API",
                    items: &[
                        "Enable",
                        "Host: 127.0.0.1",
                        "Port: 8000",
                        "Token: Session only; not saved to app state",
                        "Start API",
                        "Open Dashboard",
                        "Service API: off",
                        "Preflight: unknown",
                        "Recheck Preflight",
                    ],
                },
                TradingAppSection {
                    title: "Logs",
                    items: &[
                        "All Logs",
                        "Position Trigger Logs",
                        "Waiting Positions (Queue)",
                    ],
                },
            ],
            tables: &[
                TradingAppTable {
                    title: "Symbol / Interval Overrides",
                    columns: &[
                        "Symbol",
                        "Interval",
                        "Indicators",
                        "Loop",
                        "Leverage",
                        "Connector",
                        "Strategy Controls",
                        "Stop-Loss",
                    ],
                },
                TradingAppTable {
                    title: "Waiting Positions (Queue)",
                    columns: &["Symbol", "Interval", "Side", "Context", "State", "Age (s)"],
                },
            ],
        },
        TradingAppTab {
            key: "chart",
            title: "Chart",
            status: "Chart ready.",
            primary_metric: "Market: Futures",
            secondary_metric: "View: TradingView",
            summary: "Chart tab controls mirrored from the Python and C++ chart surfaces.",
            actions: &["Refresh", "Open In Browser"],
            sections: &[
                TradingAppSection {
                    title: "Chart Controls",
                    items: &[
                        "Market: Futures, Spot",
                        "Symbol:",
                        "Interval:",
                        "View: TradingView, Original, TradingView Lightweight",
                        "Total PNL Active Positions: --",
                        "Total PNL Closed Positions: --",
                        "Bot Status: OFF",
                        "Bot Active Time: --",
                    ],
                },
                TradingAppSection {
                    title: "Chart View Stack",
                    items: &[
                        "TradingView",
                        "Original",
                        "TradingView Lightweight",
                        "Chart ready.",
                    ],
                },
            ],
            tables: &[],
        },
        TradingAppTab {
            key: "positions",
            title: "Positions",
            status: "Bot Status: OFF",
            primary_metric: "Total Balance: --",
            secondary_metric: "Available Balance: --",
            summary: "Positions tab controls and table columns mirrored from Python and C++.",
            actions: &[
                "Refresh Positions",
                "Market Close ALL Positions",
                "Clear Selected",
                "Clear All",
            ],
            sections: &[TradingAppSection {
                title: "Position Controls",
                items: &[
                    "Positions View: Cumulative View, Per Trade View",
                    "Auto Row Height",
                    "Auto Column Width",
                    "Total PNL Active Positions: --",
                    "Total PNL Closed Positions: --",
                    "Total Balance: --",
                    "Available Balance: --",
                    "Bot Status: OFF",
                    "Bot Active Time: --",
                ],
            }],
            tables: &[TradingAppTable {
                title: "Positions",
                columns: &[
                    "Symbol",
                    "Size (USDT)",
                    "Last Price (USDT)",
                    "Margin Ratio",
                    "Liq Price (USDT)",
                    "Margin (USDT)",
                    "Quantity (Qty)",
                    "PNL (ROI%)",
                    "Interval",
                    "Indicator",
                    "Triggered Indicator Value",
                    "Current Indicator Value",
                    "Side",
                    "Open Time",
                    "Close Time",
                    "Stop-Loss",
                    "Status",
                    "Close",
                ],
            }],
        },
        TradingAppTab {
            key: "backtest",
            title: "Backtest",
            status: "Backtest idle",
            primary_metric: "Backtest Output",
            secondary_metric: "Max MDD Scanner",
            summary: "Backtest controls, indicators, scanner, and results table mirrored from Python and C++.",
            actions: &[
                "Run Backtest",
                "Stop",
                "Add Selected to Dashboard",
                "Add All to Dashboard",
                "Scan Symbols",
            ],
            sections: &[
                TradingAppSection {
                    title: "Markets",
                    items: &[
                        "Symbol Source: Futures, Spot",
                        "Refresh",
                        "Symbols (select 1 or more):",
                        "Intervals (select 1 or more):",
                        "Custom interval input: e.g., 45s or 7m or 90m, comma-separated",
                        "Add Custom Interval(s)",
                    ],
                },
                TradingAppSection {
                    title: "Backtest Parameters",
                    items: &[
                        "Start Date/Time:",
                        "End Date/Time:",
                        "Signal Logic: AND, OR, SEPARATE",
                        "MDD Logic: Per Trade MDD, Cumulative MDD, Entire Account MDD",
                        "Margin Capital:",
                        "Position % of Balance:",
                        "Loop Interval Override:",
                        "Stop Loss: Enable, mode, Scope, USDT, %",
                        "Side: Buy (Long), Sell (Short), Both (Long/Short)",
                        "Margin Mode (Futures): Isolated, Cross",
                        "Position Mode: Hedge, One-way",
                        "Assets Mode: Single-Asset Mode, Multi-Assets Mode",
                        "Account Mode: Classic Trading, Portfolio Margin",
                        "Connector:",
                        "Leverage (Futures):",
                        "Template: Enable",
                        "Max MDD Scanner: Top N, Max MDD %, Scan Symbols",
                    ],
                },
                TradingAppSection {
                    title: "Indicators",
                    items: &[
                        "Moving Average (MA) + Buy-Sell Values",
                        "Donchian Channels (DC) + Buy-Sell Values",
                        "Parabolic SAR (PSAR) + Buy-Sell Values",
                        "Bollinger Bands (BB) + Buy-Sell Values",
                        "Relative Strength Index (RSI) + Buy-Sell Values",
                        "Volume + Buy-Sell Values",
                        "Stochastic RSI (SRSI) + Buy-Sell Values",
                        "Williams %R + Buy-Sell Values",
                        "Moving Average Convergence/Divergence (MACD) + Buy-Sell Values",
                        "Ultimate Oscillator (UO) + Buy-Sell Values",
                        "Average Directional Index (ADX) + Buy-Sell Values",
                        "Directional Movement Index (DMI) + Buy-Sell Values",
                        "SuperTrend (ST) + Buy-Sell Values",
                        "Exponential Moving Average (EMA) + Buy-Sell Values",
                        "Stochastic Oscillator + Buy-Sell Values",
                    ],
                },
                TradingAppSection {
                    title: "Backtest Output",
                    items: &[
                        "Run Backtest",
                        "Stop",
                        "Add Selected to Dashboard",
                        "Add All to Dashboard",
                        "Total PNL Active Positions: --",
                        "Total PNL Closed Positions: --",
                        "Bot Status: OFF",
                        "Bot Active Time: --",
                    ],
                },
            ],
            tables: &[
                TradingAppTable {
                    title: "Symbol / Interval Overrides",
                    columns: &[
                        "Symbol",
                        "Interval",
                        "Indicators",
                        "Loop",
                        "Leverage",
                        "Connector",
                        "Strategy Controls",
                        "Stop-Loss",
                    ],
                },
                TradingAppTable {
                    title: "Backtest Results",
                    columns: &[
                        "Symbol",
                        "Interval",
                        "Logic",
                        "Indicators",
                        "Trades",
                        "Loop Interval",
                        "Start Date",
                        "End Date",
                        "Position % Of Balance",
                        "Stop-Loss Options",
                        "Margin Mode (Futures)",
                        "Position Mode",
                        "Assets Mode",
                        "Account Mode",
                        "Leverage (Futures)",
                        "ROI (USDT)",
                        "ROI (%)",
                        "Max Drawdown During Position (USDT)",
                        "Max Drawdown During Position (%)",
                        "Max Drawdown Results (USDT)",
                        "Max Drawdown Results (%)",
                    ],
                },
            ],
        },
        TradingAppTab {
            key: "liquidation-heatmap",
            title: "Liquidation Heatmap",
            status: "Web panels",
            primary_metric: "Coinglass Heatmap",
            secondary_metric: "Hyperliquid Map",
            summary: "Liquidation heatmap provider tabs mirrored from the Python and C++ web tab.",
            actions: &["Open in Browser", "Reload", "Go"],
            sections: &[
                TradingAppSection {
                    title: "Coinglass Heatmap",
                    items: &[
                        "Use the on-page controls for Model 1/2/3, pair, symbol, and time selection.",
                        "Model 1: https://www.coinglass.com/pro/futures/LiquidationHeatMap",
                        "Model 2: https://www.coinglass.com/pro/futures/LiquidationHeatMapNew",
                        "Model 3: https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3",
                    ],
                },
                TradingAppSection {
                    title: "Providers",
                    items: &[
                        "Coinank: https://coinank.com/chart/derivatives/liq-heat-map",
                        "Bitcoin Counterflow: https://www.bitcoincounterflow.com/liquidation-heatmap/",
                        "Hyblock Capital: https://hyblockcapital.com/",
                        "Coinglass Map: https://www.coinglass.com/pro/futures/LiquidationMap",
                        "Hyperliquid Map: https://www.coinglass.com/hyperliquid-liquidation-map",
                    ],
                },
            ],
            tables: &[],
        },
        TradingAppTab {
            key: "code-languages",
            title: "Code Languages",
            status: "0 selected",
            primary_metric: "Language: Rust",
            secondary_metric: "Framework: Tauri",
            summary: "Code language, Rust framework, and dependency version controls mirrored from Python/C++.",
            actions: &[
                "Update Selected",
                "Update All",
                "Check Versions",
                "Refresh Env Versions",
            ],
            sections: &[
                TradingAppSection {
                    title: "Choose your language",
                    items: &[
                        "Python - Recommended - Fast to build - Huge ecosystem",
                        "C++ - Experiment - Qt native desktop experiment",
                        "Rust - Experiment - Shared core with desktop shell experiments",
                    ],
                },
                TradingAppSection {
                    title: "Choose your Rust framework",
                    items: &[
                        "Tauri - Desktop shell with web UI",
                        "Slint - Native declarative desktop UI",
                        "egui - Fast trader dashboard UI",
                        "Iced - Pure Rust reactive desktop UI",
                        "Dioxus Desktop - Rust component UI with desktop renderer",
                    ],
                },
                TradingAppSection {
                    title: "Environment Versions",
                    items: &[
                        "0 selected",
                        "Update Selected",
                        "Update All",
                        "Check Versions",
                        "Refresh Env Versions",
                    ],
                },
            ],
            tables: &[TradingAppTable {
                title: "Environment Versions",
                columns: &[
                    "Select",
                    "Dependency",
                    "Installed",
                    "Latest",
                    "Usage",
                    "Usage Change Counter",
                ],
            }],
        },
    ]
}

pub struct LlmProviderOption {
    pub key: &'static str,
    pub label: &'static str,
    pub mode: &'static str,
    pub default_base_url: &'static str,
    pub api_key_env: &'static str,
    pub model_suggestions: &'static [&'static str],
    pub reasoning_efforts: &'static [&'static str],
}

pub fn llm_provider_options() -> &'static [LlmProviderOption] {
    &[
        LlmProviderOption {
            key: "openai",
            label: "OpenAI / ChatGPT",
            mode: "cloud",
            default_base_url: "https://api.openai.com/v1",
            api_key_env: "OPENAI_API_KEY",
            model_suggestions: &[
                "gpt-5.5",
                "gpt-5.4",
                "gpt-5.4-mini",
                "gpt-5.4-nano",
                "gpt-5.3-chat-latest",
                "gpt-5.3-codex",
                "gpt-5.2",
                "gpt-5.2-codex",
                "gpt-5.2-chat-latest",
                "gpt-5.2-pro",
                "gpt-5.1",
                "gpt-5-codex",
                "gpt-5-mini",
                "gpt-5-nano",
            ],
            reasoning_efforts: &[
                "default", "none", "minimal", "low", "medium", "high", "xhigh",
            ],
        },
        LlmProviderOption {
            key: "anthropic",
            label: "Anthropic Claude",
            mode: "cloud",
            default_base_url: "https://api.anthropic.com",
            api_key_env: "ANTHROPIC_API_KEY",
            model_suggestions: &[
                "claude-sonnet-4-5-20250929",
                "claude-haiku-4-5-20251001",
                "claude-opus-4-1-20250805",
                "claude-opus-4-20250514",
                "claude-sonnet-4-20250514",
                "claude-sonnet-4-5",
                "claude-haiku-4-5",
                "claude-opus-4-1",
                "claude-opus-4-0",
                "claude-sonnet-4-0",
            ],
            reasoning_efforts: &["default", "disabled", "enabled", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "gemini",
            label: "Google Gemini",
            mode: "cloud",
            default_base_url: "https://generativelanguage.googleapis.com/v1beta",
            api_key_env: "GEMINI_API_KEY",
            model_suggestions: &[
                "gemini-3-flash-preview",
                "gemini-3-pro-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
            ],
            reasoning_efforts: &["default", "minimal", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "deepseek",
            label: "DeepSeek",
            mode: "cloud",
            default_base_url: "https://api.deepseek.com",
            api_key_env: "DEEPSEEK_API_KEY",
            model_suggestions: &[
                "deepseek-v4-flash",
                "deepseek-v4-pro",
                "deepseek-chat",
                "deepseek-reasoner",
            ],
            reasoning_efforts: &["default", "disabled", "enabled", "high", "max"],
        },
        LlmProviderOption {
            key: "grok",
            label: "xAI Grok",
            mode: "cloud",
            default_base_url: "https://api.x.ai/v1",
            api_key_env: "XAI_API_KEY",
            model_suggestions: &[
                "grok-4.20",
                "grok-4.20-reasoning",
                "grok-4.20-non-reasoning",
                "grok-4-fast-reasoning",
                "grok-4-fast-non-reasoning",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "qwen",
            label: "Alibaba Qwen / DashScope",
            mode: "cloud",
            default_base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_env: "DASHSCOPE_API_KEY",
            model_suggestions: &[
                "qwen3-max",
                "qwen3-max-2026-01-23",
                "qwen3-max-preview",
                "qwen3.5-plus",
                "qwen3.5-flash",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "local",
            label: "Local / Custom OpenAI-Compatible",
            mode: "local",
            default_base_url: "http://127.0.0.1:11434/v1",
            api_key_env: "LOCAL_LLM_API_KEY",
            model_suggestions: &[
                "llama3.3",
                "qwen3:8b",
                "qwen3",
                "mistral-small3.2",
                "gpt-oss:20b",
                "custom-model",
            ],
            reasoning_efforts: &["default", "none", "low", "medium", "high", "xhigh"],
        },
    ]
}
