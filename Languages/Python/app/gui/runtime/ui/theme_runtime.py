from __future__ import annotations

from PyQt6 import QtGui

from app.gui.runtime.ui import design_layout_runtime

from app.gui.runtime.ui.theme_styles import (
    CHECKBOX_CHECK_IMAGE,
    DESIGN_CLASSIC,
    DESIGN_OPTIONS,
    DESIGN_WORKSTATION,
    WORKSTATION_DESIGN_STYLES,
)


def bind_main_window_theme_runtime(main_window_cls) -> None:
    main_window_cls.apply_theme = _gui_apply_theme
    main_window_cls.apply_design = _gui_apply_design


def _blend_color(base: QtGui.QColor, accent: QtGui.QColor, amount: float) -> str:
    ratio = max(0.0, min(1.0, float(amount)))
    inv = 1.0 - ratio
    red = round((base.red() * inv) + (accent.red() * ratio))
    green = round((base.green() * inv) + (accent.green() * ratio))
    blue = round((base.blue() * inv) + (accent.blue() * ratio))
    return QtGui.QColor(red, green, blue).name()


def _accent_theme_styles(accent: str) -> str:
    color = QtGui.QColor(accent)
    if not color.isValid():
        return ""

    red = color.red()
    green = color.green()
    blue = color.blue()
    hover = color.lighter(115).name()
    pressed = color.darker(135).name()
    accent_text = "#0c0f16" if color.lightness() >= 160 else "#ffffff"
    outline = color.darker(230).name()
    base_text = "#e0e0e0"
    muted_text = "#9ca3af"
    canvas_bg = _blend_color(QtGui.QColor("#080808"), color, 0.08)
    surface_bg = _blend_color(QtGui.QColor("#121212"), color, 0.12)
    panel_bg = _blend_color(QtGui.QColor("#151515"), color, 0.16)
    control_bg = _blend_color(QtGui.QColor("#1e1e1e"), color, 0.18)
    control_hover_bg = _blend_color(QtGui.QColor("#242424"), color, 0.23)
    input_bg = _blend_color(QtGui.QColor("#101010"), color, 0.13)
    disabled_bg = _blend_color(QtGui.QColor("#252525"), color, 0.10)
    disabled_border = _blend_color(QtGui.QColor("#444444"), color, 0.18)
    header_bg = _blend_color(QtGui.QColor("#171717"), color, 0.25)
    tab_bg = _blend_color(QtGui.QColor("#101010"), color, 0.18)
    tab_hover_bg = _blend_color(QtGui.QColor("#181818"), color, 0.28)
    separator = _blend_color(QtGui.QColor("#1f2937"), color, 0.35)
    hover_fill = f"rgba({red}, {green}, {blue}, 52)"

    return f"""
    /* Accent theme surfaces */
    QWidget {{
        background-color: {surface_bg};
        color: {base_text};
    }}
    QMainWindow, QDialog {{
        background-color: {canvas_bg};
        color: {base_text};
    }}
    QTabWidget::pane, QScrollArea, QFrame, QSplitter, QStackedWidget {{
        background-color: {canvas_bg};
        border-color: {outline};
    }}
    QGroupBox {{
        background-color: {panel_bg};
        border: 1px solid {outline};
        margin-top: 6px;
    }}
    QGroupBox::title {{
        color: {accent};
        background-color: {panel_bg};
    }}
    QLabel {{
        color: {base_text};
        background-color: transparent;
    }}
    QLabel:disabled {{
        color: {muted_text};
    }}
    /* Buttons */
    QPushButton, QToolButton {{
        background-color: {accent};
        border: 1px solid {accent};
        color: {accent_text};
    }}
    QPushButton:hover, QToolButton:hover {{
        background-color: {hover};
        border-color: {hover};
    }}
    QPushButton:pressed, QPushButton:checked, QToolButton:pressed, QToolButton:checked {{
        background-color: {pressed};
        border-color: {pressed};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        background-color: {disabled_bg};
        border: 1px solid {disabled_border};
        color: #808080;
    }}
    /* Inputs */
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {control_bg};
        color: {base_text};
        border: 1px solid {outline};
        selection-background-color: {accent};
        selection-color: {accent_text};
    }}
    QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
        background-color: {control_hover_bg};
        border: 1px solid {accent};
    }}
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        background-color: {control_hover_bg};
        border: 1px solid {accent};
        outline: none;
    }}
    QLineEdit:disabled, QComboBox:disabled, QListWidget:disabled, QSpinBox:disabled,
    QDoubleSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
        background-color: {disabled_bg};
        color: #808080;
        border: 1px solid {disabled_border};
    }}
    QComboBox QAbstractItemView {{
        background-color: {input_bg};
        border: 1px solid {outline};
        selection-background-color: {accent};
        selection-color: {accent_text};
    }}
    QComboBox::drop-down {{
        border: none;
        border-left: 1px solid {outline};
        background-color: {control_bg};
        width: 18px;
    }}
    QComboBox:hover::drop-down, QComboBox:on::drop-down {{
        border-left: 1px solid {accent};
        background-color: {control_hover_bg};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        background-color: {control_bg};
        border: none;
        border-left: 1px solid {outline};
        border-bottom: 1px solid {outline};
        width: 18px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        background-color: {control_bg};
        border: none;
        border-left: 1px solid {outline};
        width: 18px;
    }}
    QSpinBox:hover::up-button, QSpinBox:hover::down-button,
    QDoubleSpinBox:hover::up-button, QDoubleSpinBox:hover::down-button,
    QSpinBox:focus::up-button, QSpinBox:focus::down-button,
    QDoubleSpinBox:focus::up-button, QDoubleSpinBox:focus::down-button {{
        background-color: {control_hover_bg};
        border-left: 1px solid {accent};
    }}
    QSpinBox:hover::up-button, QDoubleSpinBox:hover::up-button,
    QSpinBox:focus::up-button, QDoubleSpinBox:focus::up-button {{
        border-bottom: 1px solid {accent};
    }}
    /* Checkboxes / radios */
    QCheckBox, QRadioButton {{
        background-color: transparent;
        color: {base_text};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        background-color: {input_bg};
        border: 1px solid {outline};
    }}
    QCheckBox::indicator:unchecked {{
        image: none;
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border-color: {accent};
        image: {CHECKBOX_CHECK_IMAGE};
    }}
    QCheckBox::indicator:hover {{
        border-color: {accent};
    }}
    QRadioButton::indicator:checked {{
        background-color: {accent};
        border: 1px solid {accent};
    }}
    QRadioButton::indicator:hover {{
        border: 1px solid {accent};
    }}
    /* Tabs / group boxes */
    QTabBar::tab {{
        background-color: {tab_bg};
        border: 1px solid {outline};
        color: {base_text};
    }}
    QTabBar::tab:selected {{
        background-color: {accent};
        border: 1px solid {accent};
        color: {accent_text};
    }}
    QTabBar::tab:hover {{
        background-color: {tab_hover_bg};
        border: 1px solid {accent};
    }}
    QTabWidget::pane {{
        border: 1px solid {outline};
    }}
    /* Selection / tables / lists */
    QListWidget, QTreeWidget, QTableWidget, QTableView, QTreeView, QListView, QAbstractItemView {{
        background-color: {input_bg};
        alternate-background-color: {panel_bg};
        color: {base_text};
        border: 1px solid {outline};
        selection-background-color: {accent};
        selection-color: {accent_text};
    }}
    QAbstractItemView::item:selected {{
        background-color: {accent};
        color: {accent_text};
    }}
    QAbstractItemView::item:hover {{
        background-color: {hover_fill};
        color: {base_text};
    }}
    QHeaderView::section {{
        background-color: {header_bg};
        border: 1px solid {outline};
        color: {base_text};
    }}
    QProgressBar {{
        border: 1px solid {outline};
        background-color: {control_bg};
        color: {base_text};
    }}
    QProgressBar::chunk {{
        background-color: {accent};
    }}
    /* Sliders / scrollbars */
    QSlider::groove:horizontal, QSlider::groove:vertical {{
        background: {control_bg};
        border: 1px solid {outline};
    }}
    QSlider::handle:horizontal, QSlider::handle:vertical {{
        background: {accent};
        border: 1px solid {outline};
    }}
    QSlider::sub-page:horizontal, QSlider::sub-page:vertical {{
        background: {accent};
    }}
    QScrollBar:vertical, QScrollBar:horizontal {{
        background: {canvas_bg};
        border: 1px solid {outline};
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {hover};
        border: 1px solid {outline};
        border-radius: 4px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        background: {control_bg};
        border: 1px solid {outline};
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: {canvas_bg};
    }}
    QMenu {{
        background-color: {input_bg};
        border: 1px solid {outline};
        color: {base_text};
    }}
    QMenu::item:selected {{
        background-color: {accent};
        color: {accent_text};
    }}
    QStatusBar {{
        background-color: {panel_bg};
        border-top: 1px solid {separator};
        color: {base_text};
    }}
    """


def _normalize_design(value: object) -> str:
    text = str(value or "").strip()
    for option in DESIGN_OPTIONS:
        if option.lower() == text.lower():
            return option
    return DESIGN_CLASSIC


def _current_design(self) -> str:
    combo = getattr(self, "design_combo", None)
    if combo is not None:
        try:
            return _normalize_design(combo.currentText())
        except Exception:
            pass
    config = getattr(self, "config", {}) or {}
    return _normalize_design(config.get("design", DESIGN_CLASSIC))


def _design_styles(design: str) -> str:
    if design == DESIGN_WORKSTATION:
        return WORKSTATION_DESIGN_STYLES
    return ""


def _store_theme_config(self, name: str, theme_raw: str) -> None:
    try:
        stored_name = name if name else "Dark"
        if theme_raw == "gren":
            stored_name = "Green"
        self.config["theme"] = stored_name.title() if stored_name else "Dark"
    except Exception:
        pass


def _gui_apply_theme(self, name: str):
    theme_raw = (name or "").strip().lower()
    theme = {"gren": "green"}.get(theme_raw, theme_raw)
    base_stylesheet = (
        self.DARK_THEME
        if theme.startswith("dark") or theme in {"blue", "yellow", "green", "red"}
        else self.LIGHT_THEME
    )

    accents = {
        "blue": "#2563eb",
        "yellow": "#fbbf24",
        "green": "#22c55e",
        "red": "#ef4444",
    }
    accent = accents.get(theme)
    accent_styles = _accent_theme_styles(accent) if accent else ""
    design = _current_design(self)
    design_styles = _design_styles(design)

    self.setStyleSheet(base_stylesheet + accent_styles + design_styles)
    design_layout_runtime.apply_design_layout(self, design)
    _store_theme_config(self, name, theme_raw)
    try:
        self.config["design"] = design
    except Exception:
        pass
    persist = getattr(self, "_persist_ui_preferences", None)
    if callable(persist):
        persist()


def _gui_apply_design(self, name: str):
    design = _normalize_design(name)
    try:
        self.config["design"] = design
    except Exception:
        pass

    theme_combo = getattr(self, "theme_combo", None)
    try:
        theme_name = theme_combo.currentText() if theme_combo is not None else self.config.get("theme", "Dark")
    except Exception:
        theme_name = "Dark"
    _gui_apply_theme(self, theme_name)
