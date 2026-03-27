from __future__ import annotations

import os
from pathlib import Path


BINANCE_SUPPORTED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}

BINANCE_INTERVAL_LOWER = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
}

BACKTEST_INTERVAL_ORDER = [
    "1m", "3m", "5m", "10m", "15m", "20m", "30m",
    "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h", "10h", "11h", "12h",
    "1d", "2d", "3d", "4d", "5d", "6d",
    "1w", "2w", "3w",
    "1month", "2months", "3months", "6months",
    "1mo", "2mo", "3mo", "6mo",
    "1y", "2y",
]

TRADINGVIEW_INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "10m": "10",
    "15m": "15",
    "20m": "20",
    "30m": "30",
    "45m": "45",
    "1h": "60",
    "2h": "120",
    "3h": "180",
    "4h": "240",
    "5h": "300",
    "6h": "360",
    "7h": "420",
    "8h": "480",
    "9h": "540",
    "10h": "600",
    "11h": "660",
    "12h": "720",
    "1d": "1D",
    "2d": "2D",
    "3d": "3D",
    "4d": "4D",
    "5d": "5D",
    "6d": "6D",
    "1w": "1W",
    "2w": "2W",
    "3w": "3W",
    "1mo": "1M",
    "2mo": "2M",
    "3mo": "3M",
    "6mo": "6M",
    "1month": "1M",
    "2months": "2M",
    "3months": "3M",
    "6months": "6M",
    "1y": "12M",
    "2y": "24M",
}

STOP_LOSS_MODE_LABELS = {
    "usdt": "USDT Based Stop Loss",
    "percent": "Percentage Based Stop Loss",
    "both": "Both Stop Loss (USDT & Percentage)",
}

STOP_LOSS_SCOPE_LABELS = {
    "per_trade": "Per Trade Stop Loss",
    "cumulative": "Cumulative Stop Loss",
    "entire_account": "Entire Account Stop Loss",
}

DASHBOARD_LOOP_CHOICES = [
    ("30 seconds", "30s"),
    ("45 seconds", "45s"),
    ("1 minute", "1m"),
    ("2 minutes", "2m"),
    ("3 minutes", "3m"),
    ("5 minutes", "5m"),
    ("10 minutes", "10m"),
    ("30 minutes", "30m"),
    ("1 hour", "1h"),
    ("2 hours", "2h"),
]

LEAD_TRADER_OPTIONS = [
    ("Futures Public Lead Trader", "futures_public"),
    ("Futures Private Lead Trader", "futures_private"),
    ("Spot Public Lead Trader", "spot_public"),
    ("Spot Private Lead Trader", "spot_private"),
]

MDD_LOGIC_LABELS = {
    "per_trade": "Per Trade MDD",
    "cumulative": "Cumulative MDD",
    "entire_account": "Entire Account MDD",
}

FUTURES_CONNECTOR_KEYS = {
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-connector",
    "ccxt",
    "python-binance",
}

SPOT_CONNECTOR_KEYS = {
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
}

CHART_INTERVAL_OPTIONS = list(BACKTEST_INTERVAL_ORDER)
CHART_MARKET_OPTIONS = ["Futures", "Spot"]
ACCOUNT_MODE_OPTIONS = ["Classic Trading", "Portfolio Margin"]
DEFAULT_CHART_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "TRXUSDT",
]
SIDE_LABELS = {
    "BUY": "Buy (Long)",
    "SELL": "Sell (Short)",
    "BOTH": "Both (Long/Short)",
}

MAX_CLOSED_HISTORY = 200
APP_STATE_PATH = Path.home() / ".trading_bot_state.json"
LEGACY_APP_STATE_PATH = Path.home() / ".binance_trading_bot_state.json"
TRADINGVIEW_SYMBOL_PREFIX = "BINANCE:"
POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17
WAITING_POSITION_LATE_THRESHOLD = 45.0
DBG_BACKTEST_DASHBOARD = True
DBG_BACKTEST_RUN = True


def _connector_options() -> list[tuple[str, str]]:
    return [
        ("Binance SDK Derivatives Trading USDⓈ Futures (Official Recommended)", "binance-sdk-derivatives-trading-usds-futures"),
        ("Binance SDK Derivatives Trading COIN-M Futures", "binance-sdk-derivatives-trading-coin-futures"),
        ("Binance SDK Spot (Official Recommended)", "binance-sdk-spot"),
        ("Binance Connector Python", "binance-connector"),
        ("CCXT (Unified)", "ccxt"),
        ("python-binance (Community)", "python-binance"),
    ]


def _env_flag_enabled(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_symbol_fetch_top_n() -> int:
    try:
        value = int(os.environ.get("BOT_SYMBOL_FETCH_TOP_N") or 200)
    except Exception:
        value = 200
    return max(50, min(value, 5000))


def _build_main_window_module_state_payload(
    context: dict[str, object],
    *,
    connector_options: list[tuple[str, str]],
    default_connector_backend: str,
    symbol_fetch_top_n: int,
    save_position_allocations,
    load_position_allocations,
    collect_dependency_versions,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    payload.update(_build_core_globals(context))
    payload.update(_build_runtime_helper_globals(context))
    payload.update(_build_language_and_indicator_globals(context))
    payload.update(
        _build_connector_dependency_and_option_globals(
            context,
            connector_options=connector_options,
            default_connector_backend=default_connector_backend,
            symbol_fetch_top_n=symbol_fetch_top_n,
            save_position_allocations=save_position_allocations,
            load_position_allocations=load_position_allocations,
            collect_dependency_versions=collect_dependency_versions,
        )
    )
    return payload


def _build_core_globals(context: dict[str, object]) -> dict[str, object]:
    return {
        "DEFAULT_CONFIG": context["DEFAULT_CONFIG"],
        "INDICATOR_DISPLAY_NAMES": context["INDICATOR_DISPLAY_NAMES"],
        "MDD_LOGIC_DEFAULT": context["MDD_LOGIC_DEFAULT"],
        "MDD_LOGIC_OPTIONS": context["MDD_LOGIC_OPTIONS"],
        "STOP_LOSS_MODE_ORDER": context["STOP_LOSS_MODE_ORDER"],
        "STOP_LOSS_SCOPE_OPTIONS": context["STOP_LOSS_SCOPE_OPTIONS"],
        "BACKTEST_TEMPLATE_DEFAULT": context["BACKTEST_TEMPLATE_DEFAULT"],
        "normalize_stop_loss_dict": context["normalize_stop_loss_dict"],
        "coerce_bool": context["coerce_bool"],
        "BinanceWrapper": context["BinanceWrapper"],
        "normalize_margin_ratio": context["normalize_margin_ratio"],
        "BacktestEngine": context["BacktestEngine"],
        "BacktestRequest": context["BacktestRequest"],
        "IndicatorDefinition": context["IndicatorDefinition"],
        "StrategyEngine": context["StrategyEngine"],
        "StopWorker": context["StopWorker"],
        "StartWorker": context["StartWorker"],
        "CallWorker": context["CallWorker"],
        "IntervalPositionGuard": context["IntervalPositionGuard"],
        "ParamDialog": context["ParamDialog"],
        "BACKTEST_TEMPLATE_DEFINITIONS": context["BACKTEST_TEMPLATE_DEFINITIONS"],
    }


def _build_runtime_helper_globals(context: dict[str, object]) -> dict[str, object]:
    main_window_runtime = context["main_window_runtime"]
    main_window_positions = context["main_window_positions"]
    main_window_ui_support = context["main_window_ui_support"]
    main_window_backtest_runtime = context["main_window_backtest_runtime"]
    main_window_web_embed = context["main_window_web_embed"]
    main_window_positions_worker = context["main_window_positions_worker"]

    return {
        "_allow_guard_bypass": main_window_runtime._allow_guard_bypass,
        "_restore_window_after_guard": main_window_runtime._restore_window_after_guard,
        "_mw_interval_sort_key": main_window_runtime._mw_interval_sort_key,
        "_is_trigger_log_line": main_window_runtime._is_trigger_log_line,
        "_mw_positions_records_cumulative": main_window_positions._mw_positions_records_cumulative,
        "_apply_window_icon": main_window_ui_support._apply_window_icon,
        "_NumericItem": main_window_ui_support._NumericItem,
        "_StarterCard": main_window_ui_support._StarterCard,
        "_BacktestWorker": main_window_backtest_runtime._BacktestWorker,
        "_LazyWebEmbed": main_window_web_embed._LazyWebEmbed,
        "_PositionsWorker": main_window_positions_worker._PositionsWorker,
        "_load_app_state_file": context["_load_app_state_file"],
        "_save_app_state_file": context["_save_app_state_file"],
        "_DEFAULT_WEB_UA": context["_DEFAULT_WEB_UA"],
        "_binance_unavailable_reason": context["_binance_unavailable_reason"],
        "_chart_safe_mode_enabled": context["_chart_safe_mode_enabled"],
        "_configure_tradingview_webengine_env": context["_configure_tradingview_webengine_env"],
        "_lightweight_unavailable_reason": context["_lightweight_unavailable_reason"],
        "_load_tradingview_widget": context["_load_tradingview_widget"],
        "_native_chart_host_prewarm_enabled": context["_native_chart_host_prewarm_enabled"],
        "_tradingview_external_preferred": context["_tradingview_external_preferred"],
        "_tradingview_supported": context["_tradingview_supported"],
        "_tradingview_unavailable_reason": context["_tradingview_unavailable_reason"],
        "_webengine_charts_allowed": context["_webengine_charts_allowed"],
        "_webengine_embed_unavailable_reason": context["_webengine_embed_unavailable_reason"],
    }


def _build_language_and_indicator_globals(context: dict[str, object]) -> dict[str, object]:
    return {
        "_BASE_PROJECT_PATH": context["_BASE_PROJECT_PATH"],
        "CPP_BUILD_ROOT": context["CPP_BUILD_ROOT"],
        "CPP_CACHE_META_FILE": context["CPP_CACHE_META_FILE"],
        "CPP_CODE_LANGUAGE_KEY": context["CPP_CODE_LANGUAGE_KEY"],
        "_CPP_DEPENDENCY_VERSION_TARGETS": context["_CPP_DEPENDENCY_VERSION_TARGETS"],
        "CPP_EXECUTABLE_BASENAME": context["CPP_EXECUTABLE_BASENAME"],
        "CPP_EXECUTABLE_LEGACY_BASENAME": context["CPP_EXECUTABLE_LEGACY_BASENAME"],
        "CPP_PACKAGED_EXECUTABLE_BASENAME": context["CPP_PACKAGED_EXECUTABLE_BASENAME"],
        "CPP_PROJECT_PATH": context["CPP_PROJECT_PATH"],
        "CPP_RELEASE_CPP_ASSET": context["CPP_RELEASE_CPP_ASSET"],
        "CPP_RELEASE_OWNER": context["CPP_RELEASE_OWNER"],
        "CPP_RELEASE_REPO": context["CPP_RELEASE_REPO"],
        "CPP_SUPPORTED_EXCHANGE_KEY": context["CPP_SUPPORTED_EXCHANGE_KEY"],
        "_DEFAULT_DEPENDENCY_VERSION_TARGETS": context["_DEFAULT_DEPENDENCY_VERSION_TARGETS"],
        "EXCHANGE_PATHS": context["EXCHANGE_PATHS"],
        "FOREX_BROKER_PATHS": context["FOREX_BROKER_PATHS"],
        "LANGUAGE_PATHS": context["LANGUAGE_PATHS"],
        "PYTHON_CODE_LANGUAGE_KEY": context["PYTHON_CODE_LANGUAGE_KEY"],
        "RELEASE_INFO_JSON_NAME": context["RELEASE_INFO_JSON_NAME"],
        "RELEASE_TAG_TEXT_NAME": context["RELEASE_TAG_TEXT_NAME"],
        "_REQUIREMENTS_PATHS": context["_REQUIREMENTS_PATHS"],
        "RUST_CODE_LANGUAGE_KEY": context["RUST_CODE_LANGUAGE_KEY"],
        "RUST_FRAMEWORK_PACKAGES": context["RUST_FRAMEWORK_PACKAGES"],
        "RUST_PROJECT_PATH": context["RUST_PROJECT_PATH"],
        "STARTER_CRYPTO_EXCHANGES": context["STARTER_CRYPTO_EXCHANGES"],
        "STARTER_FOREX_BROKERS": context["STARTER_FOREX_BROKERS"],
        "STARTER_MARKET_OPTIONS": context["STARTER_MARKET_OPTIONS"],
        "_rust_dependency_targets_for_config": context["_rust_dependency_targets_for_config"],
        "_rust_framework_key": context["_rust_framework_key"],
        "_rust_framework_option": context["_rust_framework_option"],
        "_rust_framework_path": context["_rust_framework_path"],
        "_rust_framework_title": context["_rust_framework_title"],
        "rsi_indicator": context["rsi_indicator"],
        "stoch_rsi_indicator": context["stoch_rsi_indicator"],
        "williams_r_indicator": context["williams_r_indicator"],
        "sma_indicator": context["sma_indicator"],
        "ema_indicator": context["ema_indicator"],
        "donchian_high_indicator": context["donchian_high_indicator"],
        "donchian_low_indicator": context["donchian_low_indicator"],
        "bollinger_bands_indicator": context["bollinger_bands_indicator"],
        "psar_indicator": context["psar_indicator"],
        "macd_indicator": context["macd_indicator"],
        "uo_indicator": context["uo_indicator"],
        "adx_indicator": context["adx_indicator"],
        "dmi_indicator": context["dmi_indicator"],
        "supertrend_indicator": context["supertrend_indicator"],
        "stochastic_indicator": context["stochastic_indicator"],
    }


def _build_connector_dependency_and_option_globals(
    context: dict[str, object],
    *,
    connector_options: list[tuple[str, str]],
    default_connector_backend: str,
    symbol_fetch_top_n: int,
    save_position_allocations,
    load_position_allocations,
    collect_dependency_versions,
) -> dict[str, object]:
    main_window_helper_runtime = context["main_window_helper_runtime"]
    dependency_versions_runtime = context["dependency_versions_runtime"]

    return {
        "BINANCE_SUPPORTED_INTERVALS": BINANCE_SUPPORTED_INTERVALS,
        "BINANCE_INTERVAL_LOWER": BINANCE_INTERVAL_LOWER,
        "BACKTEST_INTERVAL_ORDER": BACKTEST_INTERVAL_ORDER,
        "MAX_CLOSED_HISTORY": MAX_CLOSED_HISTORY,
        "APP_STATE_PATH": APP_STATE_PATH,
        "LEGACY_APP_STATE_PATH": LEGACY_APP_STATE_PATH,
        "TRADINGVIEW_SYMBOL_PREFIX": TRADINGVIEW_SYMBOL_PREFIX,
        "TRADINGVIEW_INTERVAL_MAP": TRADINGVIEW_INTERVAL_MAP,
        "STOP_LOSS_MODE_LABELS": STOP_LOSS_MODE_LABELS,
        "STOP_LOSS_SCOPE_LABELS": STOP_LOSS_SCOPE_LABELS,
        "DASHBOARD_LOOP_CHOICES": DASHBOARD_LOOP_CHOICES,
        "LEAD_TRADER_OPTIONS": LEAD_TRADER_OPTIONS,
        "MDD_LOGIC_LABELS": MDD_LOGIC_LABELS,
        "CONNECTOR_OPTIONS": connector_options,
        "DEFAULT_CONNECTOR_BACKEND": default_connector_backend,
        "FUTURES_CONNECTOR_KEYS": FUTURES_CONNECTOR_KEYS,
        "SPOT_CONNECTOR_KEYS": SPOT_CONNECTOR_KEYS,
        "_normalize_connector_backend": main_window_helper_runtime._normalize_connector_backend,
        "_recommended_connector_for_key": main_window_helper_runtime._recommended_connector_for_key,
        "_format_indicator_list": main_window_helper_runtime._format_indicator_list,
        "_safe_float": main_window_helper_runtime._safe_float,
        "_safe_int": main_window_helper_runtime._safe_int,
        "_normalize_indicator_token": main_window_helper_runtime._normalize_indicator_token,
        "_canonicalize_indicator_key": main_window_helper_runtime._canonicalize_indicator_key,
        "_normalize_indicator_values": main_window_helper_runtime._normalize_indicator_values,
        "_infer_indicators_from_desc": main_window_helper_runtime._infer_indicators_from_desc,
        "_resolve_trigger_indicators": main_window_helper_runtime._resolve_trigger_indicators,
        "_normalize_datetime_pair": main_window_helper_runtime._normalize_datetime_pair,
        "_make_engine_key": main_window_helper_runtime._make_engine_key,
        "_DISABLE_CHARTS": _env_flag_enabled("BOT_DISABLE_CHARTS"),
        "_DISABLE_TRADINGVIEW": _env_flag_enabled("BOT_DISABLE_TRADINGVIEW"),
        "_SYMBOL_FETCH_TOP_N": symbol_fetch_top_n,
        "_DEPENDENCY_USAGE_POLL_INTERVAL_MS": dependency_versions_runtime._DEPENDENCY_USAGE_POLL_INTERVAL_MS,
        "_normalize_dependency_key": dependency_versions_runtime._normalize_dependency_key,
        "_normalize_dependency_usage_text": dependency_versions_runtime._normalize_dependency_usage_text,
        "_set_dependency_usage_widget": dependency_versions_runtime._set_dependency_usage_widget,
        "_set_dependency_usage_counter_widget": dependency_versions_runtime._set_dependency_usage_counter_widget,
        "_make_dependency_cell_copyable": dependency_versions_runtime._make_dependency_cell_copyable,
        "_apply_dependency_usage_entry": dependency_versions_runtime._apply_dependency_usage_entry,
        "_rust_manifest_path": dependency_versions_runtime._rust_manifest_path,
        "_rust_package_metadata": dependency_versions_runtime._rust_package_metadata,
        "_rust_project_version": dependency_versions_runtime._rust_project_version,
        "_rust_tool_path": dependency_versions_runtime._rust_tool_path,
        "_rust_toolchain_env": dependency_versions_runtime._rust_toolchain_env,
        "_reset_rust_dependency_caches": dependency_versions_runtime._reset_rust_dependency_caches,
        "_rust_tool_version": dependency_versions_runtime._rust_tool_version,
        "_rust_auto_install_enabled": dependency_versions_runtime._rust_auto_install_enabled,
        "_rust_auto_install_cooldown_seconds": dependency_versions_runtime._rust_auto_install_cooldown_seconds,
        "_rust_missing_tool_labels": dependency_versions_runtime._rust_missing_tool_labels,
        "_install_rust_toolchain": dependency_versions_runtime._install_rust_toolchain,
        "_cpp_qt_webengine_available": dependency_versions_runtime._cpp_qt_webengine_available,
        "_cpp_qt_websockets_available": dependency_versions_runtime._cpp_qt_websockets_available,
        "_cpp_auto_setup_enabled": dependency_versions_runtime._cpp_auto_setup_enabled,
        "_cpp_auto_setup_cooldown_seconds": dependency_versions_runtime._cpp_auto_setup_cooldown_seconds,
        "_tail_text": dependency_versions_runtime._tail_text,
        "_cpp_auto_prepare_environment_result": dependency_versions_runtime._cpp_auto_prepare_environment_result,
        "_apply_cpp_auto_prepare_result": dependency_versions_runtime._apply_cpp_auto_prepare_result,
        "_maybe_auto_prepare_cpp_environment": dependency_versions_runtime._maybe_auto_prepare_cpp_environment,
        "_dependency_usage_state": dependency_versions_runtime._dependency_usage_state,
        "_refresh_dependency_usage_labels": dependency_versions_runtime._refresh_dependency_usage_labels,
        "_resolve_dependency_targets_for_config": dependency_versions_runtime._resolve_dependency_targets_for_config,
        "_collect_dependency_versions": collect_dependency_versions,
        "DEPENDENCY_VERSION_TARGETS": dependency_versions_runtime.DEPENDENCY_VERSION_TARGETS,
        "CHART_INTERVAL_OPTIONS": CHART_INTERVAL_OPTIONS,
        "CHART_MARKET_OPTIONS": CHART_MARKET_OPTIONS,
        "ACCOUNT_MODE_OPTIONS": ACCOUNT_MODE_OPTIONS,
        "POS_TRIGGERED_VALUE_COLUMN": POS_TRIGGERED_VALUE_COLUMN,
        "POS_CURRENT_VALUE_COLUMN": POS_CURRENT_VALUE_COLUMN,
        "POS_STOP_LOSS_COLUMN": POS_STOP_LOSS_COLUMN,
        "POS_STATUS_COLUMN": POS_STATUS_COLUMN,
        "POS_CLOSE_COLUMN": POS_CLOSE_COLUMN,
        "WAITING_POSITION_LATE_THRESHOLD": WAITING_POSITION_LATE_THRESHOLD,
        "DEFAULT_CHART_SYMBOLS": DEFAULT_CHART_SYMBOLS,
        "SIDE_LABELS": SIDE_LABELS,
        "_save_position_allocations": save_position_allocations,
        "_load_position_allocations": load_position_allocations,
        "_DBG_BACKTEST_DASHBOARD": DBG_BACKTEST_DASHBOARD,
        "_DBG_BACKTEST_RUN": DBG_BACKTEST_RUN,
    }


def _build_side_label_lookup(side_labels: dict[str, str]) -> dict[str, str]:
    return {label.lower(): code for code, label in side_labels.items()}


def install_main_window_module_state(
    module_globals: dict[str, object],
    *,
    this_file,
) -> None:
    from app.config import (
        BACKTEST_TEMPLATE_DEFAULT,
        DEFAULT_CONFIG,
        INDICATOR_DISPLAY_NAMES,
        MDD_LOGIC_DEFAULT,
        MDD_LOGIC_OPTIONS,
        STOP_LOSS_MODE_ORDER,
        STOP_LOSS_SCOPE_OPTIONS,
        coerce_bool,
        normalize_stop_loss_dict,
    )
    from app.core.backtest import BacktestEngine, BacktestRequest, IndicatorDefinition
    from app.core.indicators import (
        adx as adx_indicator,
        bollinger_bands as bollinger_bands_indicator,
        dmi as dmi_indicator,
        donchian_high as donchian_high_indicator,
        donchian_low as donchian_low_indicator,
        ema as ema_indicator,
        macd as macd_indicator,
        parabolic_sar as psar_indicator,
        rsi as rsi_indicator,
        sma as sma_indicator,
        stochastic as stochastic_indicator,
        stoch_rsi as stoch_rsi_indicator,
        supertrend as supertrend_indicator,
        ultimate_oscillator as uo_indicator,
        williams_r as williams_r_indicator,
    )
    from app.core.positions import IntervalPositionGuard
    from app.core.strategy import StrategyEngine
    from app.gui.backtest import main_window_backtest_runtime
    from app.gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
    from app.gui.chart.chart_embed import (
        _DEFAULT_WEB_UA,
        _binance_unavailable_reason,
        _chart_safe_mode_enabled,
        _configure_tradingview_webengine_env,
        _lightweight_unavailable_reason,
        _load_tradingview_widget,
        _native_chart_host_prewarm_enabled,
        _tradingview_external_preferred,
        _tradingview_supported,
        _tradingview_unavailable_reason,
        _webengine_charts_allowed,
        _webengine_embed_unavailable_reason,
    )
    from app.gui.code import dependency_versions_runtime
    from app.gui.code.code_language_catalog import (
        BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
        CPP_BUILD_ROOT,
        CPP_CACHE_META_FILE,
        CPP_CODE_LANGUAGE_KEY,
        CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
        CPP_EXECUTABLE_BASENAME,
        CPP_EXECUTABLE_LEGACY_BASENAME,
        CPP_PACKAGED_EXECUTABLE_BASENAME,
        CPP_PROJECT_PATH,
        CPP_RELEASE_CPP_ASSET,
        CPP_RELEASE_OWNER,
        CPP_RELEASE_REPO,
        CPP_SUPPORTED_EXCHANGE_KEY,
        DEFAULT_DEPENDENCY_VERSION_TARGETS as _DEFAULT_DEPENDENCY_VERSION_TARGETS,
        EXCHANGE_PATHS,
        FOREX_BROKER_PATHS,
        LANGUAGE_PATHS,
        PYTHON_CODE_LANGUAGE_KEY,
        RELEASE_INFO_JSON_NAME,
        RELEASE_TAG_TEXT_NAME,
        REQUIREMENTS_PATHS as _REQUIREMENTS_PATHS,
        RUST_CODE_LANGUAGE_KEY,
        RUST_FRAMEWORK_PACKAGES,
        RUST_PROJECT_PATH,
        STARTER_CRYPTO_EXCHANGES,
        STARTER_FOREX_BROKERS,
        STARTER_MARKET_OPTIONS,
        _rust_dependency_targets_for_config,
        _rust_framework_key,
        _rust_framework_option,
        _rust_framework_path,
        _rust_framework_title,
    )
    from app.gui.positions import main_window_positions, main_window_positions_worker
    from app.gui.runtime.window import main_window_runtime
    from app.gui.shared import (
        allocation_persistence,
        main_window_helper_runtime,
        main_window_ui_support,
        main_window_web_embed,
    )
    from app.gui.shared.main_window_config import _load_app_state_file, _save_app_state_file
    from app.gui.shared.param_dialog import ParamDialog
    from app.integrations.exchanges.binance import BinanceWrapper, normalize_margin_ratio
    from app.workers import CallWorker, StartWorker, StopWorker

    connector_options = _connector_options()
    default_connector_backend = connector_options[0][1]

    main_window_helper_runtime.bind_main_window_helper_runtime(
        default_connector_backend=default_connector_backend,
    )

    def _save_position_allocations(
        entry_allocations: dict,
        open_position_records: dict,
        mode: str | None = None,
    ) -> bool:
        return allocation_persistence.save_position_allocations(
            entry_allocations,
            open_position_records,
            this_file=this_file,
            mode=mode,
        )

    def _load_position_allocations(mode: str | None = None) -> tuple[dict, dict]:
        return allocation_persistence.load_position_allocations(
            this_file=this_file,
            mode=mode,
        )

    def _collect_dependency_versions(
        targets: list[dict[str, str]] | None = None,
        *,
        include_latest: bool = True,
        config: dict | None = None,
    ) -> list[tuple[str, str, str, str]]:
        return dependency_versions_runtime._collect_dependency_versions(
            targets,
            include_latest=include_latest,
            config=config,
        )

    symbol_fetch_top_n = _resolve_symbol_fetch_top_n()
    context = dict(locals())
    module_globals.update(
        _build_main_window_module_state_payload(
            context,
            connector_options=connector_options,
            default_connector_backend=default_connector_backend,
            symbol_fetch_top_n=symbol_fetch_top_n,
            save_position_allocations=_save_position_allocations,
            load_position_allocations=_load_position_allocations,
            collect_dependency_versions=_collect_dependency_versions,
        )
    )
    module_globals["SIDE_LABEL_LOOKUP"] = _build_side_label_lookup(
        module_globals["SIDE_LABELS"]
    )
