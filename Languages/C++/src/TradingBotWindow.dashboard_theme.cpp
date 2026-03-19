#include "TradingBotWindow.h"

#include <QColor>
#include <QWidget>

namespace {
struct DashboardThemePalette {
    bool isLight = false;
    QString accent;
    QString accentHover;
    QString accentPressed;
    QString accentOutline;
    QString accentText = QStringLiteral("#ffffff");
};

QString normalizedDashboardThemeName(QString themeName) {
    themeName = themeName.trimmed().toLower();
    if (themeName == QStringLiteral("gren")) {
        themeName = QStringLiteral("green");
    }
    return themeName;
}

DashboardThemePalette dashboardThemePaletteForName(const QString &themeName) {
    DashboardThemePalette palette;
    const QString normalized = normalizedDashboardThemeName(themeName);
    palette.isLight = normalized == QStringLiteral("light");

    if (normalized == QStringLiteral("blue")) {
        palette.accent = QStringLiteral("#2563eb");
        palette.accentHover = QStringLiteral("#3b82f6");
        palette.accentPressed = QStringLiteral("#1d4ed8");
        palette.accentOutline = QStringLiteral("#1e40af");
    } else if (normalized == QStringLiteral("yellow")) {
        palette.accent = QStringLiteral("#fbbf24");
        palette.accentHover = QStringLiteral("#fcd34d");
        palette.accentPressed = QStringLiteral("#d97706");
        palette.accentOutline = QStringLiteral("#92400e");
        palette.accentText = QStringLiteral("#0c0f16");
    } else if (normalized == QStringLiteral("green")) {
        palette.accent = QStringLiteral("#22c55e");
        palette.accentHover = QStringLiteral("#4ade80");
        palette.accentPressed = QStringLiteral("#16a34a");
        palette.accentOutline = QStringLiteral("#166534");
    } else if (normalized == QStringLiteral("red")) {
        palette.accent = QStringLiteral("#ef4444");
        palette.accentHover = QStringLiteral("#f87171");
        palette.accentPressed = QStringLiteral("#dc2626");
        palette.accentOutline = QStringLiteral("#991b1b");
    }

    return palette;
}

QString dashboardPageThemeCss(bool isLight) {
    return isLight
        ? QStringLiteral(R"(
        #dashboardPage { background: #f5f7fb; }
        #dashboardPage QLabel { color: #0f172a; }
        #dashboardPage QGroupBox { background: #ffffff; border: 1px solid #d1d5db; border-radius: 8px; margin-top: 12px; }
        #dashboardPage QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #111827; }
        #dashboardPage QLineEdit, #dashboardPage QComboBox, #dashboardPage QDoubleSpinBox, #dashboardPage QSpinBox, #dashboardPage QDateEdit {
            background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 6px;
        }
        #dashboardPage QListWidget { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; }
        #dashboardPage QPushButton { background: #e5e7eb; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 10px; }
        #dashboardPage QPushButton:hover { background: #dbeafe; }
        #dashboardPage QLineEdit:disabled, #dashboardPage QComboBox:disabled, #dashboardPage QDoubleSpinBox:disabled,
        #dashboardPage QSpinBox:disabled, #dashboardPage QDateEdit:disabled, #dashboardPage QListWidget:disabled {
            background: #eef2f7; color: #64748b; border: 1px solid #94a3b8;
        }
        #dashboardPage QPushButton:disabled {
            background: #e5e7eb; color: #64748b; border: 1px solid #94a3b8;
        }
        #dashboardPage QCheckBox:disabled { color: #6b7280; }
        #dashboardPage QCheckBox::indicator:disabled { background: #f8fafc; border: 1px solid #94a3b8; }
        #dashboardPage QCheckBox::indicator:checked:disabled {
            background: #2563eb; border-color: #2563eb;
            image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
        }
        #dashboardPage QComboBox::drop-down:disabled, #dashboardPage QDateEdit::drop-down:disabled,
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QSpinBox::down-button:disabled,
        #dashboardPage QDoubleSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::down-button:disabled {
            background: #e5e7eb; border-left: 1px solid #94a3b8;
        }
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::up-button:disabled {
            border-bottom: 1px solid #94a3b8;
        }
    )")
        : QStringLiteral(R"(
        #dashboardPage { background: #0b0f16; }
        #dashboardPage QLabel { color: #e5e7eb; }
        #dashboardPage QGroupBox { background: #0f1624; border: 1px solid #1f2937; border-radius: 8px; margin-top: 12px; }
        #dashboardPage QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #cbd5e1; }
        #dashboardPage QLineEdit, #dashboardPage QComboBox, #dashboardPage QDoubleSpinBox, #dashboardPage QSpinBox, #dashboardPage QDateEdit {
            background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 4px 6px;
        }
        #dashboardPage QListWidget { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; }
        #dashboardPage QPushButton { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 6px 10px; }
        #dashboardPage QPushButton:hover { background: #1f2937; }
        #dashboardPage QLineEdit:disabled, #dashboardPage QComboBox:disabled, #dashboardPage QDoubleSpinBox:disabled,
        #dashboardPage QSpinBox:disabled, #dashboardPage QDateEdit:disabled, #dashboardPage QListWidget:disabled {
            background: #0b1020; color: #94a3b8; border: 1px solid #334155;
        }
        #dashboardPage QPushButton:disabled {
            background: #101826; color: #94a3b8; border: 1px solid #334155;
        }
        #dashboardPage QCheckBox:disabled { color: #9ca3af; }
        #dashboardPage QCheckBox::indicator:disabled { background: #0b1020; border: 1px solid #475569; }
        #dashboardPage QCheckBox::indicator:checked:disabled {
            background: #2563eb; border-color: #2563eb;
            image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
        }
        #dashboardPage QComboBox::drop-down:disabled, #dashboardPage QDateEdit::drop-down:disabled,
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QSpinBox::down-button:disabled,
        #dashboardPage QDoubleSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::down-button:disabled {
            background: #101826; border-left: 1px solid #334155;
        }
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::up-button:disabled {
            border-bottom: 1px solid #334155;
        }
    )");
}

QString dashboardGlobalThemeCss(bool isLight) {
    return isLight
        ? QStringLiteral(R"(
        QMainWindow { background: #f5f7fb; }
        QTabWidget::pane { border: 1px solid #d1d5db; background: #f5f7fb; }
        QTabBar::tab { background: #e5e7eb; color: #0f172a; padding: 6px 10px; }
        QTabBar::tab:selected { background: #ffffff; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage, QWidget#dashboardPage, QWidget#liquidationPage { background: #f5f7fb; color: #0f172a; }
        QScrollArea#dashboardScrollArea { background: #f5f7fb; border: none; }
        QWidget#dashboardScrollWidget { background: #f5f7fb; }
        QScrollArea#backtestScrollArea { background: #f5f7fb; border: none; }
        QWidget#backtestScrollWidget { background: #f5f7fb; }
        QGroupBox { color: #0f172a; border-color: #d1d5db; }
        QLabel { color: #0f172a; }
        QLabel:disabled, QCheckBox:disabled, QComboBox:disabled, QLineEdit:disabled { color: #6b7280; }
        QGroupBox::title { color: #0f172a; }
        QCheckBox { color: #0f172a; spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #cbd5e1; background: #ffffff; }
        QCheckBox::indicator:hover { border-color: #2563eb; }
        QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
        QCheckBox::indicator:disabled { background: #f1f5f9; border-color: #d1d5db; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; }
        QListWidget { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; }
        QPushButton { background: #e5e7eb; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 10px; }
        QPushButton:hover { background: #dbeafe; }
        QTableWidget { background: #ffffff; color: #0f172a; gridline-color: #d1d5db; selection-background-color: #dbeafe; selection-color: #0f172a; }
        QHeaderView::section { background: #e5e7eb; color: #0f172a; border: 1px solid #d1d5db; }
    )")
        : QStringLiteral(R"(
        QMainWindow { background: #0b0f16; }
        QTabWidget::pane { border: 1px solid #1f2937; background: #0b0f16; }
        QTabBar::tab { background: #111827; color: #e5e7eb; padding: 6px 10px; }
        QTabBar::tab:selected { background: #1f2937; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage, QWidget#dashboardPage, QWidget#liquidationPage { background: #0b0f16; color: #e5e7eb; }
        QScrollArea#dashboardScrollArea { background: #0b0f16; border: none; }
        QWidget#dashboardScrollWidget { background: #0b0f16; }
        QScrollArea#backtestScrollArea { background: #0b0f16; border: none; }
        QWidget#backtestScrollWidget { background: #0b0f16; }
        QGroupBox { color: #e5e7eb; border-color: #1f2937; }
        QLabel { color: #e5e7eb; }
        QLabel:disabled, QCheckBox:disabled, QComboBox:disabled, QLineEdit:disabled { color: #9ca3af; }
        QGroupBox::title { color: #e5e7eb; }
        QCheckBox { color: #e5e7eb; spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #1f2937; background: #0d1117; }
        QCheckBox::indicator:hover { border-color: #2563eb; }
        QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
        QCheckBox::indicator:disabled { background: #111827; border-color: #1f2937; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 3px 6px; }
        QListWidget { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; }
        QPushButton { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 6px 10px; }
        QPushButton:hover { background: #1f2937; }
        QTableWidget { background: #0d1117; color: #e5e7eb; gridline-color: #1f2937; selection-background-color: #1f2937; selection-color: #e5e7eb; }
        QHeaderView::section { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; }
    )");
}

QString dashboardCodeThemeCss(bool isLight) {
    return isLight
        ? QStringLiteral(
              "QWidget#codePage { background: #f5f7fb; color: #0f172a; }"
              "QScrollArea#codeScrollArea { background: #f5f7fb; border: none; }"
              "QWidget#codeContent { background: #f5f7fb; }"
              "QLabel { color: #0f172a; }"
              "QTableWidget { background: #ffffff; color: #0f172a; gridline-color: #d1d5db; }"
              "QHeaderView::section { background: #e5e7eb; color: #0f172a; }")
        : QStringLiteral(
              "QWidget#codePage { background: #0b0f16; color: #e5e7eb; }"
              "QScrollArea#codeScrollArea { background: #0b1220; border: none; }"
              "QWidget#codeContent { background: #0b1220; }"
              "QLabel { color: #e5e7eb; }"
              "QTableWidget { background: #0d1117; color: #e5e7eb; gridline-color: #1f2937; }"
              "QHeaderView::section { background: #111827; color: #e5e7eb; }");
}

QString dashboardAccentCss(const DashboardThemePalette &palette) {
    if (palette.accent.isEmpty()) {
        return QString();
    }

    QString accentOutline = palette.accentOutline;
    const QColor accentColor(palette.accent);
    if (accentColor.isValid()) {
        accentOutline = accentColor.darker(230).name();
    }

    const QString hoverFill = QStringLiteral("rgba(%1, %2, %3, 52)")
                                  .arg(accentColor.red())
                                  .arg(accentColor.green())
                                  .arg(accentColor.blue());
    const QString controlBg = palette.isLight ? QStringLiteral("#ffffff") : QStringLiteral("#0d1117");
    const QString headerBg = palette.isLight ? QStringLiteral("#f1f5f9") : QStringLiteral("#111827");
    const QString disabledBg = palette.isLight ? QStringLiteral("#f1f5f9") : QStringLiteral("#0b1020");
    const QString disabledBorder = palette.isLight ? QStringLiteral("#d1d5db") : QStringLiteral("#1f2937");
    const QString baseText = palette.isLight ? QStringLiteral("#0f172a") : QStringLiteral("#e5e7eb");

    return QStringLiteral(
               "QPushButton { background-color: %1; border: 1px solid %1; color: %4; }"
               "QPushButton:hover { background-color: %2; border-color: %2; }"
               "QPushButton:pressed, QPushButton:checked { background-color: %3; border-color: %3; }"
               "QPushButton:disabled { background-color: %8; border: 1px solid %9; color: #808080; }"
               "QLineEdit QToolButton, QComboBox QToolButton, QAbstractSpinBox QToolButton {"
               "background: transparent; border: none; padding: 0px; margin: 0px; }"
               "QLineEdit QToolButton:hover, QComboBox QToolButton:hover, QAbstractSpinBox QToolButton:hover {"
               "background: transparent; border: none; }"
               "QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QPlainTextEdit {"
               "selection-background-color: %1; selection-color: %4; }"
               "QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover "
               "{ border: 1px solid %1; }"
               "QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus "
               "{ border: 1px solid %1; outline: none; }"
               "QCheckBox::indicator:checked { background-color: %1; border-color: %1; }"
               "QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %1; }"
               "QRadioButton::indicator:checked { background-color: %1; border: 1px solid %1; }"
               "QTabBar::tab:selected { background-color: %1; border: 1px solid %1; color: %4; }"
               "QTabBar::tab:hover { border: 1px solid %1; }"
               "QTabWidget::pane { border: 1px solid %5; }"
               "QGroupBox::title { color: %1; }"
               "QGroupBox { border: 1px solid %5; }"
               "QAbstractItemView { selection-background-color: %1; selection-color: %4; }"
               "QAbstractItemView::item:selected { background-color: %1; color: %4; }"
               "QAbstractItemView::item:hover { background-color: %6; color: %10; }"
               "QHeaderView::section { background-color: %11; border: 1px solid %5; }"
               "QProgressBar { border: 1px solid %5; background-color: %7; }"
               "QProgressBar::chunk { background-color: %1; }"
               "QSlider::handle:horizontal, QSlider::handle:vertical { background: %1; border: 1px solid %5; }"
               "QSlider::sub-page:horizontal, QSlider::sub-page:vertical { background: %1; }"
               "QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: %2; border: 1px solid %5; border-radius: 4px; }"
               "QMenu::item:selected { background-color: %1; color: %4; }")
        .arg(palette.accent)
        .arg(palette.accentHover)
        .arg(palette.accentPressed)
        .arg(palette.accentText)
        .arg(accentOutline)
        .arg(hoverFill)
        .arg(controlBg)
        .arg(disabledBg)
        .arg(disabledBorder)
        .arg(baseText)
        .arg(headerBg);
}
} // namespace

void TradingBotWindow::applyDashboardTheme(const QString &themeName) {
    if (!dashboardPage_) {
        return;
    }

    const DashboardThemePalette palette = dashboardThemePaletteForName(themeName);
    const QString accentCss = dashboardAccentCss(palette);

    this->setStyleSheet(dashboardGlobalThemeCss(palette.isLight) + accentCss);
    dashboardPage_->setStyleSheet(dashboardPageThemeCss(palette.isLight) + accentCss);

    if (codePage_) {
        codePage_->setStyleSheet(dashboardCodeThemeCss(palette.isLight) + accentCss);
    }
}
