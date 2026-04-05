from __future__ import annotations

from .module_state_constants import _connector_options, _resolve_symbol_fetch_top_n
from .module_state_payload import (
    _build_main_window_module_state_payload,
    _build_side_label_lookup,
)


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
    from app.gui.backtest import worker_runtime as backtest_worker_runtime
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
    from app.gui.positions import positions_runtime, worker_runtime as positions_worker_runtime
    from app.gui.runtime.background_workers import CallWorker
    from app.gui.runtime.strategy_workers import StartWorker, StopWorker
    from app.gui.runtime.window import runtime as window_runtime
    from app.gui.shared import (
        allocation_persistence,
        helper_runtime as shared_helper_runtime,
        ui_support as shared_ui_support,
        web_embed as shared_web_embed,
    )
    from app.gui.shared.config_runtime import _load_app_state_file, _save_app_state_file
    from app.gui.shared.param_dialog import ParamDialog
    from app.integrations.exchanges.binance import BinanceWrapper, normalize_margin_ratio

    connector_options = _connector_options()
    default_connector_backend = connector_options[0][1]

    shared_helper_runtime.bind_main_window_helper_runtime(
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
    context = {
        "DEFAULT_CONFIG": DEFAULT_CONFIG,
        "INDICATOR_DISPLAY_NAMES": INDICATOR_DISPLAY_NAMES,
        "MDD_LOGIC_DEFAULT": MDD_LOGIC_DEFAULT,
        "MDD_LOGIC_OPTIONS": MDD_LOGIC_OPTIONS,
        "STOP_LOSS_MODE_ORDER": STOP_LOSS_MODE_ORDER,
        "STOP_LOSS_SCOPE_OPTIONS": STOP_LOSS_SCOPE_OPTIONS,
        "BACKTEST_TEMPLATE_DEFAULT": BACKTEST_TEMPLATE_DEFAULT,
        "normalize_stop_loss_dict": normalize_stop_loss_dict,
        "coerce_bool": coerce_bool,
        "BinanceWrapper": BinanceWrapper,
        "normalize_margin_ratio": normalize_margin_ratio,
        "BacktestEngine": BacktestEngine,
        "BacktestRequest": BacktestRequest,
        "IndicatorDefinition": IndicatorDefinition,
        "StrategyEngine": StrategyEngine,
        "StopWorker": StopWorker,
        "StartWorker": StartWorker,
        "CallWorker": CallWorker,
        "IntervalPositionGuard": IntervalPositionGuard,
        "ParamDialog": ParamDialog,
        "BACKTEST_TEMPLATE_DEFINITIONS": BACKTEST_TEMPLATE_DEFINITIONS,
        "window_runtime": window_runtime,
        "positions_runtime": positions_runtime,
        "shared_ui_support": shared_ui_support,
        "backtest_worker_runtime": backtest_worker_runtime,
        "shared_web_embed": shared_web_embed,
        "positions_worker_runtime": positions_worker_runtime,
        "_load_app_state_file": _load_app_state_file,
        "_save_app_state_file": _save_app_state_file,
        "_DEFAULT_WEB_UA": _DEFAULT_WEB_UA,
        "_binance_unavailable_reason": _binance_unavailable_reason,
        "_chart_safe_mode_enabled": _chart_safe_mode_enabled,
        "_configure_tradingview_webengine_env": _configure_tradingview_webengine_env,
        "_lightweight_unavailable_reason": _lightweight_unavailable_reason,
        "_load_tradingview_widget": _load_tradingview_widget,
        "_native_chart_host_prewarm_enabled": _native_chart_host_prewarm_enabled,
        "_tradingview_external_preferred": _tradingview_external_preferred,
        "_tradingview_supported": _tradingview_supported,
        "_tradingview_unavailable_reason": _tradingview_unavailable_reason,
        "_webengine_charts_allowed": _webengine_charts_allowed,
        "_webengine_embed_unavailable_reason": _webengine_embed_unavailable_reason,
        "_BASE_PROJECT_PATH": _BASE_PROJECT_PATH,
        "CPP_BUILD_ROOT": CPP_BUILD_ROOT,
        "CPP_CACHE_META_FILE": CPP_CACHE_META_FILE,
        "CPP_CODE_LANGUAGE_KEY": CPP_CODE_LANGUAGE_KEY,
        "_CPP_DEPENDENCY_VERSION_TARGETS": _CPP_DEPENDENCY_VERSION_TARGETS,
        "CPP_EXECUTABLE_BASENAME": CPP_EXECUTABLE_BASENAME,
        "CPP_EXECUTABLE_LEGACY_BASENAME": CPP_EXECUTABLE_LEGACY_BASENAME,
        "CPP_PACKAGED_EXECUTABLE_BASENAME": CPP_PACKAGED_EXECUTABLE_BASENAME,
        "CPP_PROJECT_PATH": CPP_PROJECT_PATH,
        "CPP_RELEASE_CPP_ASSET": CPP_RELEASE_CPP_ASSET,
        "CPP_RELEASE_OWNER": CPP_RELEASE_OWNER,
        "CPP_RELEASE_REPO": CPP_RELEASE_REPO,
        "CPP_SUPPORTED_EXCHANGE_KEY": CPP_SUPPORTED_EXCHANGE_KEY,
        "_DEFAULT_DEPENDENCY_VERSION_TARGETS": _DEFAULT_DEPENDENCY_VERSION_TARGETS,
        "EXCHANGE_PATHS": EXCHANGE_PATHS,
        "FOREX_BROKER_PATHS": FOREX_BROKER_PATHS,
        "LANGUAGE_PATHS": LANGUAGE_PATHS,
        "PYTHON_CODE_LANGUAGE_KEY": PYTHON_CODE_LANGUAGE_KEY,
        "RELEASE_INFO_JSON_NAME": RELEASE_INFO_JSON_NAME,
        "RELEASE_TAG_TEXT_NAME": RELEASE_TAG_TEXT_NAME,
        "_REQUIREMENTS_PATHS": _REQUIREMENTS_PATHS,
        "RUST_CODE_LANGUAGE_KEY": RUST_CODE_LANGUAGE_KEY,
        "RUST_FRAMEWORK_PACKAGES": RUST_FRAMEWORK_PACKAGES,
        "RUST_PROJECT_PATH": RUST_PROJECT_PATH,
        "STARTER_CRYPTO_EXCHANGES": STARTER_CRYPTO_EXCHANGES,
        "STARTER_FOREX_BROKERS": STARTER_FOREX_BROKERS,
        "STARTER_MARKET_OPTIONS": STARTER_MARKET_OPTIONS,
        "_rust_dependency_targets_for_config": _rust_dependency_targets_for_config,
        "_rust_framework_key": _rust_framework_key,
        "_rust_framework_option": _rust_framework_option,
        "_rust_framework_path": _rust_framework_path,
        "_rust_framework_title": _rust_framework_title,
        "rsi_indicator": rsi_indicator,
        "stoch_rsi_indicator": stoch_rsi_indicator,
        "williams_r_indicator": williams_r_indicator,
        "sma_indicator": sma_indicator,
        "ema_indicator": ema_indicator,
        "donchian_high_indicator": donchian_high_indicator,
        "donchian_low_indicator": donchian_low_indicator,
        "bollinger_bands_indicator": bollinger_bands_indicator,
        "psar_indicator": psar_indicator,
        "macd_indicator": macd_indicator,
        "uo_indicator": uo_indicator,
        "adx_indicator": adx_indicator,
        "dmi_indicator": dmi_indicator,
        "supertrend_indicator": supertrend_indicator,
        "stochastic_indicator": stochastic_indicator,
        "shared_helper_runtime": shared_helper_runtime,
        "dependency_versions_runtime": dependency_versions_runtime,
    }
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
    module_globals["SIDE_LABEL_LOOKUP"] = _build_side_label_lookup(module_globals["SIDE_LABELS"])
