from __future__ import annotations

import copy
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()

for _parent in _THIS_FILE.parents:
    if (_parent / "Languages").exists():
        BASE_PROJECT_PATH = _parent
        break
else:
    BASE_PROJECT_PATH = _THIS_FILE.parents[2]

PYTHON_CODE_LANGUAGE_KEY = "Python (PyQt)"
CPP_CODE_LANGUAGE_KEY = "C++ (Qt/C++23)"
RUST_CODE_LANGUAGE_KEY = "Rust"
CPP_SUPPORTED_EXCHANGE_KEY = "Binance"
CPP_EXECUTABLE_BASENAME = "Trading-Bot-C++"
CPP_EXECUTABLE_LEGACY_BASENAME = "binance_backtest_tab"
CPP_PACKAGED_EXECUTABLE_BASENAME = "Trading-Bot-C++"
CPP_RELEASE_OWNER = "Yunushan"
CPP_RELEASE_REPO = "trading-bot"
CPP_RELEASE_CPP_ASSET = "Trading-Bot-C++.zip"
CPP_CACHE_META_FILE = "cpp-runtime-meta.json"
RELEASE_INFO_JSON_NAME = "release-info.json"
RELEASE_TAG_TEXT_NAME = "release-tag.txt"
CPP_PROJECT_PATH = (BASE_PROJECT_PATH / "Languages" / "C++").resolve()
RUST_PROJECT_PATH = (BASE_PROJECT_PATH / "Languages" / "Rust").resolve()
CPP_BUILD_ROOT = (BASE_PROJECT_PATH / "build" / "binance_cpp").resolve()

LANGUAGE_PATHS = {
    PYTHON_CODE_LANGUAGE_KEY: "Languages/Python",
    CPP_CODE_LANGUAGE_KEY: "Languages/C++",
    RUST_CODE_LANGUAGE_KEY: "Languages/Rust",
}

RUST_FRAMEWORK_PATHS = {
    "Tauri": "Languages/Rust/apps/tauri-desktop",
    "Slint": "Languages/Rust/apps/slint-desktop",
    "egui": "Languages/Rust/apps/egui-desktop",
    "Iced": "Languages/Rust/apps/iced-desktop",
    "Dioxus Desktop": "Languages/Rust/apps/dioxus-desktop",
}

RUST_FRAMEWORK_PACKAGES = {
    "Tauri": "trading-bot-tauri-desktop",
    "Slint": "trading-bot-slint-desktop",
    "egui": "trading-bot-egui-desktop",
    "Iced": "trading-bot-iced-desktop",
    "Dioxus Desktop": "trading-bot-dioxus-desktop",
}

RUST_SHARED_PATHS = [
    "Languages/Rust/crates/contracts",
    "Languages/Rust/crates/core",
]

EXCHANGE_PATHS = {
    "Binance": None,
    "Bybit": None,
    "OKX": None,
    "Bitget": None,
    "Gate": None,
    "MEXC": None,
    "KuCoin": None,
    "HTX": None,
    "Crypto.com Exchange": None,
    "Kraken": None,
    "Bitfinex": None,
}

FOREX_BROKER_PATHS: dict[str, str | None] = {}
MUTED_TEXT = "#94a3b8"

STARTER_LANGUAGE_OPTIONS = [
    {
        "config_key": PYTHON_CODE_LANGUAGE_KEY,
        "title": "Python",
        "subtitle": "Fast to build - Huge ecosystem",
        "accent": "#3b82f6",
        "badge": "Recommended",
    },
    {
        "config_key": CPP_CODE_LANGUAGE_KEY,
        "title": "C++",
        "subtitle": "Qt native desktop (preview)",
        "accent": "#38bdf8",
        "badge": "Preview",
    },
    {
        "config_key": RUST_CODE_LANGUAGE_KEY,
        "title": "Rust",
        "subtitle": "Shared core with desktop framework shells",
        "accent": "#fb923c",
        "badge": "Scaffold",
    },
]

RUST_FRAMEWORK_OPTIONS = [
    {
        "key": "Tauri",
        "title": "Tauri",
        "subtitle": "Desktop shell with web UI",
        "accent": "#f59e0b",
        "badge": "Desktop",
    },
    {
        "key": "Slint",
        "title": "Slint",
        "subtitle": "Native declarative desktop UI",
        "accent": "#22c55e",
        "badge": "Desktop",
    },
    {
        "key": "egui",
        "title": "egui",
        "subtitle": "Fast trader dashboard UI",
        "accent": "#38bdf8",
        "badge": "Desktop",
    },
    {
        "key": "Iced",
        "title": "Iced",
        "subtitle": "Pure Rust reactive desktop UI",
        "accent": "#a78bfa",
        "badge": "Desktop",
    },
    {
        "key": "Dioxus Desktop",
        "title": "Dioxus Desktop",
        "subtitle": "Rust component UI with desktop renderer",
        "accent": "#ec4899",
        "badge": "Desktop",
    },
]

STARTER_MARKET_OPTIONS = [
    {"key": "crypto", "title": "Crypto Exchange", "subtitle": "Binance, Bybit, KuCoin", "accent": "#34d399"},
    {
        "key": "forex",
        "title": "Forex Exchange",
        "subtitle": "OANDA, FXCM, MetaTrader - coming soon",
        "accent": "#93c5fd",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

STARTER_CRYPTO_EXCHANGES = [
    {"key": "Binance", "title": "Binance", "subtitle": "Advanced desktop bot ready to launch", "accent": "#fbbf24"},
    {
        "key": "Bybit",
        "title": "Bybit",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#fb7185",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "OKX",
        "title": "OKX",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#a78bfa",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "Gate",
        "title": "Gate",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#22c55e",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "Bitget",
        "title": "Bitget",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#0ea5e9",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "MEXC",
        "title": "MEXC",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#10b981",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "KuCoin",
        "title": "KuCoin",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#eab308",
        "badge": "coming soon",
        "disabled": True,
    },
]

STARTER_FOREX_BROKERS = [
    {
        "key": "OANDA",
        "title": "OANDA",
        "subtitle": "Popular REST API - coming soon",
        "accent": "#60a5fa",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "FXCM",
        "title": "FXCM",
        "subtitle": "Streaming quotes - coming soon",
        "accent": "#c084fc",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "IG",
        "title": "IG",
        "subtitle": "Global CFD trading - coming soon",
        "accent": "#f472b6",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

REQUIREMENTS_PATHS = [
    _THIS_FILE.parents[2] / "requirements.txt",
    _THIS_FILE.parents[3] / "requirements.txt",
]

DEFAULT_DEPENDENCY_VERSION_TARGETS = [
    {"label": "python-binance", "package": "python-binance"},
    {"label": "binance-connector", "package": "binance-connector"},
    {"label": "ccxt", "package": "ccxt"},
    {"label": "PyQt6", "package": "PyQt6"},
    {"label": "PyQt6-Qt6", "package": "PyQt6-Qt6"},
    {"label": "PyQt6-WebEngine", "package": "PyQt6-WebEngine"},
    {"label": "numba", "package": "numba"},
    {"label": "llvmlite", "package": "llvmlite"},
    {"label": "numpy", "package": "numpy"},
    {"label": "pandas", "package": "pandas"},
    {"label": "requests", "package": "requests"},
    {"label": "binance-sdk-derivatives-trading-usds-futures", "package": "binance-sdk-derivatives-trading-usds-futures"},
    {"label": "binance-sdk-derivatives-trading-coin-futures", "package": "binance-sdk-derivatives-trading-coin-futures"},
    {"label": "binance-sdk-spot", "package": "binance-sdk-spot"},
]

CPP_DEPENDENCY_VERSION_TARGETS = [
    {"label": "Qt6 (C++)", "custom": "cpp_qt", "latest": "6.11.0"},
    {"label": "Qt6 Network (REST)", "custom": "cpp_qt_network", "latest": "6.11.0"},
    {"label": "Qt6 WebEngine", "custom": "cpp_qt_webengine", "latest": "6.11.0"},
    {"label": "Qt6 WebSockets", "custom": "cpp_qt_websockets", "latest": "6.11.0"},
    {
        "label": "Binance REST client (native)",
        "custom": "cpp_file_version",
        "path": "Languages/C++/src/BinanceRestClient.cpp",
        "usage": "Active",
    },
    {
        "label": "Binance WebSocket client (native)",
        "custom": "cpp_file_version",
        "path": "Languages/C++/src/BinanceWsClient.cpp",
        "usage": "Active",
    },
    {"label": "Eigen", "custom": "cpp_eigen", "latest_key": "eigen"},
    {"label": "xtensor", "custom": "cpp_xtensor", "latest_key": "xtensor"},
    {"label": "TA-Lib", "custom": "cpp_talib", "latest_key": "ta-lib"},
    {"label": "libcurl", "custom": "cpp_libcurl", "latest": "8.19.0"},
    {"label": "cpr", "custom": "cpp_cpr", "latest_key": "cpr"},
]

RUST_BASE_DEPENDENCY_VERSION_TARGETS = [
    {"label": "rustc", "custom": "rust_rustc", "latest": "Install rustup"},
    {"label": "cargo", "custom": "rust_cargo", "latest": "Install rustup"},
    {
        "label": "Trading Bot Rust workspace",
        "custom": "rust_file_version",
        "path": "Languages/Rust/Cargo.toml",
        "usage": "Active",
    },
    {
        "label": "trading-bot-core",
        "custom": "rust_file_version",
        "path": "Languages/Rust/crates/core/Cargo.toml",
        "usage": "Active",
    },
    {
        "label": "trading-bot-contracts",
        "custom": "rust_file_version",
        "path": "Languages/Rust/crates/contracts/Cargo.toml",
        "usage": "Active",
    },
]


def _rust_framework_option(config_or_key: dict | str | None = None) -> dict[str, str]:
    selected_key = ""
    if isinstance(config_or_key, dict):
        try:
            selected_key = str(config_or_key.get("selected_rust_framework") or "").strip()
        except Exception:
            selected_key = ""
    elif config_or_key is not None:
        selected_key = str(config_or_key).strip()
    for option in RUST_FRAMEWORK_OPTIONS:
        if str(option.get("key") or "").strip() == selected_key:
            return option
    return {}


def _rust_framework_key(config: dict | None = None) -> str:
    return str(_rust_framework_option(config).get("key") or "").strip()


def _rust_framework_title(config: dict | None = None) -> str:
    return str(_rust_framework_option(config).get("title") or _rust_framework_key(config) or "Rust").strip()


def _rust_framework_path(config: dict | None = None) -> Path | None:
    relative_path = RUST_FRAMEWORK_PATHS.get(_rust_framework_key(config))
    if not relative_path:
        return None
    return (BASE_PROJECT_PATH / relative_path).resolve()


def _rust_framework_dependency_target(config: dict | None = None) -> dict[str, str] | None:
    option = _rust_framework_option(config)
    framework_key = str(option.get("key") or "").strip()
    framework_path = RUST_FRAMEWORK_PATHS.get(framework_key)
    if not framework_key or not framework_path:
        return None
    manifest_path = f"{framework_path}/Cargo.toml"
    badge = str(option.get("badge") or "").strip() or "Framework"
    return {
        "label": f"{framework_key} ({badge})",
        "custom": "rust_file_version",
        "path": manifest_path,
        "usage": "Active",
    }


def _rust_dependency_targets_for_config(config: dict | None = None) -> list[dict[str, str]]:
    targets = copy.deepcopy(RUST_BASE_DEPENDENCY_VERSION_TARGETS)
    framework_target = _rust_framework_dependency_target(config)
    if framework_target:
        targets.append(framework_target)
    return targets
