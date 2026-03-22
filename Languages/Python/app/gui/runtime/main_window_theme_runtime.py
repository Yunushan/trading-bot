from __future__ import annotations

from PyQt6 import QtGui


def bind_main_window_theme_runtime(main_window_cls) -> None:
    main_window_cls.apply_theme = _gui_apply_theme


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
    accent_styles = ""
    if accent:
        try:
            color = QtGui.QColor(accent)
            red = color.red()
            green = color.green()
            blue = color.blue()
            hover = color.lighter(115).name()
            pressed = color.darker(135).name()
            accent_text = "#0c0f16" if color.lightness() >= 160 else "#ffffff"
            outline = color.darker(230).name()
            control_bg = "#1e1e1e"
            control_hover_bg = "#242424"
            header_bg = "#171717"
            disabled_bg = "#2a2a2a"
            disabled_border = "#444444"
            base_text = "#e0e0e0"
            hover_fill = f"rgba({red}, {green}, {blue}, 52)"
            accent_styles = f"""
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
                selection-background-color: {accent};
                selection-color: {accent_text};
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
                border: 1px solid {accent};
            }}
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1px solid {accent};
                outline: none;
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
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
                image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
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
            QTabBar::tab:selected {{
                background-color: {accent};
                border: 1px solid {accent};
                color: {accent_text};
            }}
            QTabBar::tab:hover {{
                border: 1px solid {accent};
            }}
            QTabWidget::pane {{
                border: 1px solid {outline};
            }}
            QGroupBox::title {{
                color: {accent};
            }}
            QGroupBox {{
                border: 1px solid {outline};
            }}
            /* Selection / tables */
            QAbstractItemView {{
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
            }}
            QProgressBar {{
                border: 1px solid {outline};
                background-color: {control_bg};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
            }}
            /* Sliders / scrollbars */
            QSlider::handle:horizontal, QSlider::handle:vertical {{
                background: {accent};
                border: 1px solid {outline};
            }}
            QSlider::sub-page:horizontal, QSlider::sub-page:vertical {{
                background: {accent};
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {hover};
                border: 1px solid {outline};
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {accent};
                color: {accent_text};
            }}
            """
        except Exception:
            accent_styles = ""

    self.setStyleSheet(base_stylesheet + accent_styles)
    try:
        stored_name = name if name else "Dark"
        if theme_raw == "gren":
            stored_name = "Green"
        self.config["theme"] = stored_name.title() if stored_name else "Dark"
    except Exception:
        pass
