from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from . import code_language_status, code_language_ui

_LAZY_WEB_EMBED_CLS = None
_STARTER_CARD_CLS = None
_RESOLVE_DEPENDENCY_TARGETS_FOR_CONFIG = None
_LAUNCH_CPP_FROM_CODE_TAB = None
_LAUNCH_RUST_FROM_CODE_TAB = None
_REFRESH_CODE_LANGUAGE_CARD_RELEASE_LABELS = None
_REFRESH_DEPENDENCY_USAGE_LABELS = None
_BASE_PROJECT_PATH = None


def _open_external_url(self, url: str) -> bool:
    try:
        target = str(url or "").strip()
    except Exception:
        target = ""
    if not target:
        return False
    try:
        return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(target)))
    except Exception:
        return False


def _build_liquidation_web_panel(self, title: str, url: str, note: str | None = None):
    lazy_web_embed_cls = _LAZY_WEB_EMBED_CLS
    if lazy_web_embed_cls is None:
        raise RuntimeError("_LazyWebEmbed is not configured")

    panel = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    header_layout = QtWidgets.QHBoxLayout()
    title_label = QtWidgets.QLabel(title)
    title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
    header_layout.addWidget(title_label)
    header_layout.addStretch()
    open_btn = QtWidgets.QPushButton("Open in Browser")
    header_layout.addWidget(open_btn)
    reload_btn = QtWidgets.QPushButton("Reload")
    header_layout.addWidget(reload_btn)
    layout.addLayout(header_layout)

    if note:
        note_label = QtWidgets.QLabel(note)
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: #94a3b8;")
        layout.addWidget(note_label)

    url_row = QtWidgets.QHBoxLayout()
    url_row.addWidget(QtWidgets.QLabel("URL:"))
    url_edit = QtWidgets.QLineEdit()
    url_edit.setText(url)
    url_edit.setPlaceholderText("https://")
    url_row.addWidget(url_edit, 1)
    go_btn = QtWidgets.QPushButton("Go")
    url_row.addWidget(go_btn)
    layout.addLayout(url_row)

    web_embed = lazy_web_embed_cls(url)
    layout.addWidget(web_embed, 1)
    try:
        QtCore.QTimer.singleShot(0, web_embed.prime_native_host)
    except Exception:
        pass

    def _current_url() -> str:
        try:
            return str(url_edit.text() or "").strip()
        except Exception:
            return ""

    def _apply_url() -> None:
        target = _current_url()
        if not target:
            return
        web_embed.set_url(target)

    go_btn.clicked.connect(_apply_url)
    url_edit.returnPressed.connect(_apply_url)
    reload_btn.clicked.connect(web_embed.reload)
    open_btn.clicked.connect(lambda: _open_external_url(self, _current_url()))

    return panel


def _init_liquidation_heatmap_tab(self):
    tab = QtWidgets.QWidget()
    outer_layout = QtWidgets.QVBoxLayout(tab)
    outer_layout.setContentsMargins(10, 10, 10, 10)
    outer_layout.setSpacing(12)

    intro = QtWidgets.QLabel(
        "Liquidation heatmaps from multiple providers. "
        "If a heatmap does not load, use 'Open in Browser'."
    )
    intro.setWordWrap(True)
    outer_layout.addWidget(intro)

    tabs = QtWidgets.QTabWidget()
    outer_layout.addWidget(tabs, 1)
    self.liquidation_tabs = tabs

    coinglass_tab = QtWidgets.QWidget()
    coinglass_layout = QtWidgets.QVBoxLayout(coinglass_tab)
    coinglass_layout.setContentsMargins(0, 0, 0, 0)
    coinglass_note = QtWidgets.QLabel(
        "Use the on-page controls for Model 1/2/3, pair, symbol, and time selection."
    )
    coinglass_note.setWordWrap(True)
    coinglass_layout.addWidget(coinglass_note)

    coinglass_models = QtWidgets.QTabWidget()
    coinglass_layout.addWidget(coinglass_models, 1)
    coinglass_models_urls = [
        (1, "https://www.coinglass.com/pro/futures/LiquidationHeatMap"),
        (2, "https://www.coinglass.com/pro/futures/LiquidationHeatMapNew"),
        (3, "https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3"),
    ]
    for model, url in coinglass_models_urls:
        panel = _build_liquidation_web_panel(self, f"Coinglass Heatmap Model {model}", url)
        coinglass_models.addTab(panel, f"Model {model}")

    tabs.addTab(coinglass_tab, "Coinglass Heatmap")

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Coinank Liquidation Heatmap",
            "https://coinank.com/chart/derivatives/liq-heat-map",
        ),
        "Coinank",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Bitcoin Counterflow Liquidation Heatmap",
            "https://www.bitcoincounterflow.com/liquidation-heatmap/",
        ),
        "Bitcoin Counterflow",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Hyblock Capital Liquidation Heatmap",
            "https://hyblockcapital.com/",
        ),
        "Hyblock Capital",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Coinglass Liquidation Map",
            "https://www.coinglass.com/pro/futures/LiquidationMap",
        ),
        "Coinglass Map",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Hyperliquid Liquidation Map",
            "https://www.coinglass.com/hyperliquid-liquidation-map",
        ),
        "Hyperliquid Map",
    )

    return tab


def _init_code_language_tab(self, parent: QtWidgets.QWidget | None = None):
    return code_language_ui.init_code_language_tab(
        self,
        starter_card_cls=_STARTER_CARD_CLS,
        resolve_dependency_targets_for_config=_RESOLVE_DEPENDENCY_TARGETS_FOR_CONFIG,
        parent=parent,
    )


def _code_tab_select_language(self, config_key: str) -> None:
    return code_language_ui.code_tab_select_language(
        self,
        config_key,
        launch_cpp_from_code_tab=_LAUNCH_CPP_FROM_CODE_TAB,
    )


def _code_tab_select_rust_framework(self, framework_key: str) -> None:
    return code_language_ui.code_tab_select_rust_framework(
        self,
        framework_key,
        launch_rust_from_code_tab=_LAUNCH_RUST_FROM_CODE_TAB,
    )


def _code_tab_select_market(self, market_key: str) -> None:
    return code_language_ui.code_tab_select_market(self, market_key)


def _code_tab_select_exchange(self, exchange_key: str) -> None:
    return code_language_ui.code_tab_select_exchange(self, exchange_key)


def _code_tab_select_forex(self, broker_key: str) -> None:
    return code_language_ui.code_tab_select_forex(self, broker_key)


def _finish_code_tab_confirmation(self, accepted: bool) -> None:
    return code_language_ui._finish_code_tab_confirmation(self, accepted)


def _refresh_code_tab_from_config(self) -> None:
    return code_language_ui.refresh_code_tab_from_config(
        self,
        resolve_dependency_targets_for_config=_RESOLVE_DEPENDENCY_TARGETS_FOR_CONFIG,
        refresh_code_language_card_release_labels=_REFRESH_CODE_LANGUAGE_CARD_RELEASE_LABELS,
        refresh_dependency_usage_labels=_REFRESH_DEPENDENCY_USAGE_LABELS,
    )


def _code_tab_visible(self) -> bool:
    return code_language_ui.code_tab_visible(self)


def _ensure_cpp_process_watchdog(self) -> None:
    return code_language_status.ensure_cpp_process_watchdog(self)


def _poll_cpp_process_state(self) -> None:
    return code_language_status.poll_cpp_process_state(self)


def _ensure_rust_process_watchdog(self) -> None:
    return code_language_status.ensure_rust_process_watchdog(self)


def _poll_rust_process_state(self) -> None:
    return code_language_status.poll_rust_process_state(self)


def _update_code_tab_market_sections(self) -> None:
    return code_language_ui.update_code_tab_market_sections(self)


def _update_code_tab_rust_sections(self) -> None:
    return code_language_ui.update_code_tab_rust_sections(self)


def _sync_language_exchange_lists_from_config(self):
    return code_language_ui.sync_language_exchange_lists_from_config(self)


def _ensure_language_exchange_paths(self):
    return code_language_ui.ensure_language_exchange_paths(self, base_project_path=_BASE_PROJECT_PATH)


def _on_code_language_changed(self, text: str):
    return code_language_ui.on_code_language_changed(self, text)


def _on_exchange_selection_changed(self, text: str):
    return code_language_ui.on_exchange_selection_changed(self, text)


def _on_exchange_list_changed(
    self,
    current: QtWidgets.QListWidgetItem | None,
    _previous: QtWidgets.QListWidgetItem | None = None,
) -> None:
    return code_language_ui.on_exchange_list_changed(self, current, _previous)


def _on_forex_selection_changed(self, text: str):
    return code_language_ui.on_forex_selection_changed(self, text)


def bind_main_window_code(
    main_window_cls,
    *,
    lazy_web_embed_cls,
    starter_card_cls,
    resolve_dependency_targets_for_config,
    launch_cpp_from_code_tab,
    launch_rust_from_code_tab,
    refresh_code_language_card_release_labels,
    refresh_dependency_usage_labels,
    base_project_path: Path,
) -> None:
    global _LAZY_WEB_EMBED_CLS
    global _STARTER_CARD_CLS
    global _RESOLVE_DEPENDENCY_TARGETS_FOR_CONFIG
    global _LAUNCH_CPP_FROM_CODE_TAB
    global _LAUNCH_RUST_FROM_CODE_TAB
    global _REFRESH_CODE_LANGUAGE_CARD_RELEASE_LABELS
    global _REFRESH_DEPENDENCY_USAGE_LABELS
    global _BASE_PROJECT_PATH

    _LAZY_WEB_EMBED_CLS = lazy_web_embed_cls
    _STARTER_CARD_CLS = starter_card_cls
    _RESOLVE_DEPENDENCY_TARGETS_FOR_CONFIG = resolve_dependency_targets_for_config
    _LAUNCH_CPP_FROM_CODE_TAB = launch_cpp_from_code_tab
    _LAUNCH_RUST_FROM_CODE_TAB = launch_rust_from_code_tab
    _REFRESH_CODE_LANGUAGE_CARD_RELEASE_LABELS = refresh_code_language_card_release_labels
    _REFRESH_DEPENDENCY_USAGE_LABELS = refresh_dependency_usage_labels
    _BASE_PROJECT_PATH = Path(base_project_path)

    main_window_cls._open_external_url = _open_external_url
    main_window_cls._build_liquidation_web_panel = _build_liquidation_web_panel
    main_window_cls._init_liquidation_heatmap_tab = _init_liquidation_heatmap_tab
    main_window_cls._init_code_language_tab = _init_code_language_tab
    main_window_cls._code_tab_select_language = _code_tab_select_language
    main_window_cls._code_tab_select_rust_framework = _code_tab_select_rust_framework
    main_window_cls._code_tab_select_market = _code_tab_select_market
    main_window_cls._code_tab_select_exchange = _code_tab_select_exchange
    main_window_cls._code_tab_select_forex = _code_tab_select_forex
    main_window_cls._finish_code_tab_confirmation = _finish_code_tab_confirmation
    main_window_cls._refresh_code_tab_from_config = _refresh_code_tab_from_config
    main_window_cls._code_tab_visible = _code_tab_visible
    main_window_cls._ensure_cpp_process_watchdog = _ensure_cpp_process_watchdog
    main_window_cls._poll_cpp_process_state = _poll_cpp_process_state
    main_window_cls._ensure_rust_process_watchdog = _ensure_rust_process_watchdog
    main_window_cls._poll_rust_process_state = _poll_rust_process_state
    main_window_cls._update_code_tab_market_sections = _update_code_tab_market_sections
    main_window_cls._update_code_tab_rust_sections = _update_code_tab_rust_sections
    main_window_cls._sync_language_exchange_lists_from_config = _sync_language_exchange_lists_from_config
    main_window_cls._ensure_language_exchange_paths = _ensure_language_exchange_paths
    main_window_cls._on_code_language_changed = _on_code_language_changed
    main_window_cls._on_exchange_selection_changed = _on_exchange_selection_changed
    main_window_cls._on_exchange_list_changed = _on_exchange_list_changed
    main_window_cls._on_forex_selection_changed = _on_forex_selection_changed
