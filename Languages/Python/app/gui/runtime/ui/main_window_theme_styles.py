from __future__ import annotations

LIGHT_THEME = """
QWidget { background-color: #FFFFFF; color: #000000; font-family: Arial; }
QGroupBox { border: 1px solid #C0C0C0; margin-top: 6px; }
QPushButton { background-color: #F0F0F0; border: 1px solid #B0B0B0; padding: 6px; }
QPushButton:disabled { background-color: #D5D5D5; border: 1px solid #B8B8B8; color: #7A7A7A; }
QTextEdit { background-color: #FFFFFF; color: #000000; }
QLineEdit { background-color: #FFFFFF; color: #000000; }
QLineEdit:disabled,
QComboBox:disabled,
QListWidget:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled { background-color: #E6E6E6; color: #7A7A7A; }
QCheckBox:disabled,
QRadioButton:disabled { color: #7A7A7A; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #7A7A7A;
    border-radius: 3px;
    background-color: #FFFFFF;
}
QCheckBox::indicator:unchecked {
    image: none;
}
QCheckBox::indicator:checked {
    background-color: #0A84FF;
    border-color: #0A84FF;
    image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
}
QCheckBox::indicator:hover {
    border-color: #0A84FF;
}
QComboBox { background-color: #FFFFFF; color: #000000; }
QListWidget { background-color: #FFFFFF; color: #000000; }
QLabel { color: #000000; }
QLabel:disabled { color: #7A7A7A; }
"""

DARK_THEME = """
QWidget { background-color: #121212; color: #E0E0E0; font-family: Arial; }
QGroupBox { border: 1px solid #333; margin-top: 6px; }
QPushButton { background-color: #1E1E1E; border: 1px solid #333; padding: 6px; }
QPushButton:disabled { background-color: #2A2A2A; border: 1px solid #444; color: #808080; }
QTextEdit { background-color: #0E0E0E; color: #E0E0E0; }
QLineEdit { background-color: #1E1E1E; color: #E0E0E0; }
QLineEdit:disabled,
QComboBox:disabled,
QListWidget:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled { background-color: #1A1A1A; color: #7E7E7E; }
QCheckBox:disabled,
QRadioButton:disabled { color: #7E7E7E; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #5A5A5A;
    border-radius: 3px;
    background-color: #1A1A1A;
}
QCheckBox::indicator:unchecked {
    image: none;
}
QCheckBox::indicator:checked {
    background-color: #3FB950;
    border-color: #3FB950;
    image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
}
QCheckBox::indicator:hover {
    border-color: #3FB950;
}
QComboBox { background-color: #1E1E1E; color: #E0E0E0; }
QListWidget { background-color: #0E0E0E; color: #E0E0E0; }
QLabel { color: #E0E0E0; }
QLabel:disabled { color: #6F6F6F; }
"""
