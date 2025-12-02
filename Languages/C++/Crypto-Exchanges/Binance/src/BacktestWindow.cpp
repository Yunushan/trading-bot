#include "BacktestWindow.h"

#include <QCheckBox>
#include <QAbstractItemView>
#include <QComboBox>
#include <QDate>
#include <QDateEdit>
#include <QDesktopServices>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QCoreApplication>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QMessageBox>
#include <QProcess>
#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>
#include <QScrollArea>
#include <QSpinBox>
#include <QSizePolicy>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTabWidget>
#include <QTimer>
#include <QUrl>
#ifndef HAS_QT_WEBENGINE
#define HAS_QT_WEBENGINE 0
#endif
#include <QVBoxLayout>
#include <QtMath>
#if HAS_QT_WEBENGINE
#include <QWebEngineView>
#endif

#include <functional>
#include <set>

namespace {
QString formatDuration(qint64 seconds) {
    const qint64 mins = seconds / 60;
    const qint64 hrs = mins / 60;
    const qint64 days = hrs / 24;
    const qint64 months = days / 30;
    if (months > 0) {
        return QString::number(months) + "mo";
    }
    if (days > 0) {
        return QString::number(days) + "d";
    }
    if (hrs > 0) {
        return QString::number(hrs) + "h";
    }
    if (mins > 0) {
        return QString::number(mins) + "m";
    }
    return QString::number(seconds) + "s";
}
} // namespace

BacktestWindow::BacktestWindow(QWidget *parent)
    : QMainWindow(parent),
      symbolList_(nullptr),
      intervalList_(nullptr),
      customIntervalEdit_(nullptr),
      statusLabel_(nullptr),
      botStatusLabel_(nullptr),
      botTimeLabel_(nullptr),
      runButton_(nullptr),
      stopButton_(nullptr),
      addSelectedBtn_(nullptr),
      addAllBtn_(nullptr),
      symbolSourceCombo_(nullptr),
      resultsTable_(nullptr),
      botTimer_(nullptr),
      tabs_(nullptr),
      backtestTab_(nullptr),
      dashboardThemeCombo_(nullptr),
      dashboardPage_(nullptr),
      codePage_(nullptr) {
    setWindowTitle("Binance Trading Bot");
    resize(1350, 900);

    auto *central = new QWidget(this);
    setCentralWidget(central);
    auto *rootLayout = new QVBoxLayout(central);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    tabs_ = new QTabWidget(central);
    tabs_->setMovable(false);
    tabs_->setDocumentMode(true);
    tabs_->addTab(createDashboardTab(), "Dashboard");
    tabs_->addTab(createChartTab(), "Chart");
    tabs_->addTab(createPositionsTab(), "Positions");
    backtestTab_ = createBacktestTab();
    tabs_->addTab(backtestTab_, "Backtest");
    tabs_->addTab(createCodeTab(), "Code Languages And Exchanges");
    tabs_->setCurrentWidget(backtestTab_);

    rootLayout->addWidget(tabs_);

    populateDefaults();
    wireSignals();

    // Ensure the initial theme applies after all tabs/widgets exist.
    if (dashboardThemeCombo_) {
        applyDashboardTheme(dashboardThemeCombo_->currentText());
    }
}

QWidget *BacktestWindow::createPlaceholderTab(const QString &title, const QString &body) {
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(12);

    auto *heading = new QLabel(title, page);
    heading->setStyleSheet("font-size: 18px; font-weight: 600;");
    layout->addWidget(heading);

    auto *desc = new QLabel(body, page);
    desc->setWordWrap(true);
    layout->addWidget(desc);

    layout->addStretch();
    return page;
}

QWidget *BacktestWindow::createDashboardTab() {
    auto *page = new QWidget(this);
    page->setObjectName("dashboardPage");
    dashboardPage_ = page;

    auto *pageLayout = new QVBoxLayout(page);
    pageLayout->setContentsMargins(0, 0, 0, 0);
    pageLayout->setSpacing(0);

    auto *scrollArea = new QScrollArea(page);
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    pageLayout->addWidget(scrollArea);

    auto *content = new QWidget(scrollArea);
    scrollArea->setWidget(content);

    auto *root = new QVBoxLayout(content);
    root->setContentsMargins(10, 10, 10, 10);
    root->setSpacing(12);

    auto *accountBox = new QGroupBox("Account & Status", page);
    auto *accountGrid = new QGridLayout(accountBox);
    accountGrid->setHorizontalSpacing(10);
    accountGrid->setVerticalSpacing(8);
    accountGrid->setContentsMargins(12, 12, 12, 12);
    root->addWidget(accountBox);

    auto addPair = [accountGrid, accountBox](int row, int &col, const QString &label, QWidget *widget, int span = 1) {
        accountGrid->addWidget(new QLabel(label, accountBox), row, col++);
        accountGrid->addWidget(widget, row, col, 1, span);
        col += span;
    };

    int col = 0;
    auto *apiKeyEdit = new QLineEdit(accountBox);
    apiKeyEdit->setPlaceholderText("API Key");
    apiKeyEdit->setMinimumWidth(240);
    addPair(0, col, "API Key:", apiKeyEdit, 2);

    auto *modeCombo = new QComboBox(accountBox);
    modeCombo->addItems({"Live", "Paper (Testnet)"});
    addPair(0, col, "Mode:", modeCombo);

    dashboardThemeCombo_ = new QComboBox(accountBox);
    dashboardThemeCombo_->addItems({"Dark", "Light"});
    addPair(0, col, "Theme:", dashboardThemeCombo_);
    connect(dashboardThemeCombo_, &QComboBox::currentTextChanged, this, &BacktestWindow::applyDashboardTheme);

    auto *pnlActive = new QLabel("--", accountBox);
    pnlActive->setStyleSheet("color: #a5b4fc;");
    addPair(0, col, "Total PNL Active Positions:", pnlActive);

    auto *pnlClosed = new QLabel("--", accountBox);
    pnlClosed->setStyleSheet("color: #a5b4fc;");
    addPair(0, col, "Total PNL Closed Positions:", pnlClosed);

    auto *botStatus = new QLabel("OFF", accountBox);
    botStatus->setStyleSheet("color: #ef4444; font-weight: 700;");
    addPair(0, col, "Bot Status:", botStatus);

    accountGrid->addWidget(new QLabel("Bot Active Time:", accountBox), 0, col++);
    auto *botTime = new QLabel("--", accountBox);
    botTime->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    accountGrid->addWidget(botTime, 0, col, 1, 2);
    accountGrid->setColumnStretch(col, 1);

    col = 0;
    auto *apiSecretEdit = new QLineEdit(accountBox);
    apiSecretEdit->setEchoMode(QLineEdit::Password);
    apiSecretEdit->setPlaceholderText("API Secret Key");
    apiSecretEdit->setMinimumWidth(240);
    addPair(1, col, "API Secret Key:", apiSecretEdit, 2);

    auto *accountTypeCombo = new QComboBox(accountBox);
    accountTypeCombo->addItems({"Futures", "Spot"});
    addPair(1, col, "Account Type:", accountTypeCombo);

    auto *accountModeCombo = new QComboBox(accountBox);
    accountModeCombo->addItems({"Classic Trading", "Multi-Asset Mode"});
    addPair(1, col, "Account Mode:", accountModeCombo);

    auto *connectorCombo = new QComboBox(accountBox);
    connectorCombo->addItems({
        "Binance SDK Derivatives Trading USDⓈ Futures (Official Recommended)",
        "Binance Gateway",
        "Custom Connector"
    });
    connectorCombo->setMinimumWidth(260);
    addPair(1, col, "Connector:", connectorCombo, 3);

    col = 0;
    auto *balanceLabel = new QLabel("N/A", accountBox);
    balanceLabel->setStyleSheet("color: #fbbf24; font-weight: 700;");
    addPair(2, col, "Total USDT balance:", balanceLabel);

    auto *refreshBalanceBtn = new QPushButton("Refresh Balance", accountBox);
    accountGrid->addWidget(refreshBalanceBtn, 2, col++);

    auto *leverageSpin = new QSpinBox(accountBox);
    leverageSpin->setRange(1, 125);
    leverageSpin->setValue(20);
    addPair(2, col, "Leverage (Futures):", leverageSpin);

    auto *marginModeCombo = new QComboBox(accountBox);
    marginModeCombo->addItems({"Isolated", "Cross"});
    addPair(2, col, "Margin Mode (Futures):", marginModeCombo);

    auto *positionModeCombo = new QComboBox(accountBox);
    positionModeCombo->addItems({"Hedge", "One-way"});
    addPair(2, col, "Position Mode:", positionModeCombo);

    auto *assetsModeCombo = new QComboBox(accountBox);
    assetsModeCombo->addItems({"Single-Asset Mode", "Multi-Asset Mode"});
    addPair(2, col, "Assets Mode:", assetsModeCombo);

    col = 0;
    auto *indicatorSourceCombo = new QComboBox(accountBox);
    indicatorSourceCombo->addItems({"Binance futures", "Binance spot", "Testnet futures"});
    indicatorSourceCombo->setMinimumWidth(180);
    addPair(3, col, "Indicator Source:", indicatorSourceCombo, 2);

    auto *orderTypeCombo = new QComboBox(accountBox);
    orderTypeCombo->addItems({"GTC", "IOC", "FOK"});
    addPair(3, col, "Order Type:", orderTypeCombo);

    auto *expiryCombo = new QComboBox(accountBox);
    expiryCombo->addItems({"30 min (GTD)", "1h (GTD)", "4h (GTD)", "GTC"});
    addPair(3, col, "Expiry / TIF:", expiryCombo);

    for (int stretchCol : {1, 2, 4, 6, 8, 10, 12}) {
        accountGrid->setColumnStretch(stretchCol, 1);
    }
    accountGrid->setColumnStretch(13, 2);

    auto *marketsBox = new QGroupBox("Markets / Intervals", page);
    auto *marketsLayout = new QVBoxLayout(marketsBox);
    marketsLayout->setSpacing(8);
    marketsLayout->setContentsMargins(12, 12, 12, 12);

    auto *indicatorRow = new QHBoxLayout();
    indicatorRow->setSpacing(10);
    indicatorRow->addWidget(new QLabel("Indicator Source:", marketsBox));
    auto *indicatorSource = new QComboBox(marketsBox);
    indicatorSource->addItems({"Binance futures", "Binance spot", "Combined watchlist"});
    indicatorRow->addWidget(indicatorSource);
    indicatorRow->addSpacing(8);
    indicatorRow->addWidget(new QLabel("TIF:", marketsBox));
    auto *tifCombo = new QComboBox(marketsBox);
    tifCombo->addItems({"GTC", "IOC", "FOK"});
    indicatorRow->addWidget(tifCombo);
    indicatorRow->addSpacing(8);
    indicatorRow->addWidget(new QLabel("Expiry:", marketsBox));
    auto *expiryTif = new QComboBox(marketsBox);
    expiryTif->addItems({"30 min (GTD)", "1h (GTD)", "4h (GTD)", "GTC"});
    indicatorRow->addWidget(expiryTif);
    indicatorRow->addStretch();
    marketsLayout->addLayout(indicatorRow);

    auto *listsGrid = new QGridLayout();
    listsGrid->setHorizontalSpacing(12);
    listsGrid->setVerticalSpacing(8);
    listsGrid->addWidget(new QLabel("Symbols (select 1 or more):", marketsBox), 0, 0);
    listsGrid->addWidget(new QLabel("Intervals (select 1 or more):", marketsBox), 0, 1);

    auto *dashboardSymbolList = new QListWidget(marketsBox);
    dashboardSymbolList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardSymbolList->addItems({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"});
    listsGrid->addWidget(dashboardSymbolList, 1, 0, 2, 1);

    auto *dashboardIntervalList = new QListWidget(marketsBox);
    dashboardIntervalList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardIntervalList->addItems({
        "1m", "3m", "5m", "10m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h"
    });
    listsGrid->addWidget(dashboardIntervalList, 1, 1, 2, 1);

    auto *refreshSymbolsBtn = new QPushButton("Refresh Symbols", marketsBox);
    listsGrid->addWidget(refreshSymbolsBtn, 3, 0, 1, 1);

    auto *customIntervalEdit = new QLineEdit(marketsBox);
    customIntervalEdit->setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated");
    listsGrid->addWidget(customIntervalEdit, 3, 1, 1, 1);
    auto *customButton = new QPushButton("Add Custom Interval(s)", marketsBox);
    listsGrid->addWidget(customButton, 3, 2, 1, 1);
    marketsLayout->addLayout(listsGrid);

    auto *marketsHint = new QLabel("Pre-load your Binance futures symbols and multi-timeframe intervals.", marketsBox);
    marketsHint->setStyleSheet("color: #94a3b8; font-size: 12px;");
    marketsLayout->addWidget(marketsHint);
    root->addWidget(marketsBox);

    connect(customButton, &QPushButton::clicked, this, [customIntervalEdit, dashboardIntervalList]() {
        const auto parts = customIntervalEdit->text().split(',', Qt::SkipEmptyParts);
        for (QString interval : parts) {
            interval = interval.trimmed();
            if (interval.isEmpty()) {
                continue;
            }
            bool exists = false;
            for (int i = 0; i < dashboardIntervalList->count(); ++i) {
                if (dashboardIntervalList->item(i)->text().compare(interval, Qt::CaseInsensitive) == 0) {
                    exists = true;
                    break;
                }
            }
            if (!exists) {
                dashboardIntervalList->addItem(interval);
            }
        }
        customIntervalEdit->clear();
    });

    auto *strategyBox = new QGroupBox("Strategy Controls", page);
    auto *strategyGrid = new QGridLayout(strategyBox);
    strategyGrid->setHorizontalSpacing(12);
    strategyGrid->setVerticalSpacing(8);
    strategyGrid->setContentsMargins(12, 12, 12, 12);
    root->addWidget(strategyBox);

    int row = 0;
    strategyGrid->addWidget(new QLabel("Side:", strategyBox), row, 0);
    auto *sideCombo = new QComboBox(strategyBox);
    sideCombo->addItems({"Both (Long/Short)", "Long Only", "Short Only"});
    strategyGrid->addWidget(sideCombo, row, 1);

    strategyGrid->addWidget(new QLabel("Position % of Balance:", strategyBox), row, 2);
    auto *positionPct = new QDoubleSpinBox(strategyBox);
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setValue(2.0);
    positionPct->setSuffix(" %");
    strategyGrid->addWidget(positionPct, row, 3);

    strategyGrid->addWidget(new QLabel("Loop Interval Override:", strategyBox), row, 4);
    auto *loopOverride = new QComboBox(strategyBox);
    loopOverride->addItems({"Off", "30 seconds", "1 minute", "5 minutes"});
    loopOverride->setCurrentText("1 minute");
    strategyGrid->addWidget(loopOverride, row, 5);

    ++row;
    auto *enableLeadTrader = new QCheckBox("Enable Lead Trader", strategyBox);
    strategyGrid->addWidget(enableLeadTrader, row, 0, 1, 2);
    auto *leadTraderCombo = new QComboBox(strategyBox);
    leadTraderCombo->addItems({"Futures Public Lead Trader", "Signals Feed", "Manual Lead"});
    leadTraderCombo->setEnabled(false);
    connect(enableLeadTrader, &QCheckBox::toggled, leadTraderCombo, &QWidget::setEnabled);
    strategyGrid->addWidget(leadTraderCombo, row, 2, 1, 2);

    ++row;
    auto *oneWayCheck = new QCheckBox("Add-only in current net direction (one-way)", strategyBox);
    strategyGrid->addWidget(oneWayCheck, row, 0, 1, 3);
    auto *hedgeStackCheck = new QCheckBox("Allow simultaneous long / short positions (hedge stacking)", strategyBox);
    strategyGrid->addWidget(hedgeStackCheck, row, 3, 1, 3);

    ++row;
    auto *stopWithoutCloseCheck = new QCheckBox("Stop Bot Without Closing Active Positions", strategyBox);
    stopWithoutCloseCheck->setToolTip(
        "When checked, the Stop button will halt strategy threads but keep existing positions open."
    );
    strategyGrid->addWidget(stopWithoutCloseCheck, row, 0, 1, 3);
    auto *windowCloseCheck = new QCheckBox("Market Close All Active Positions On Window Close (WIP)", strategyBox);
    windowCloseCheck->setEnabled(false);
    strategyGrid->addWidget(windowCloseCheck, row, 3, 1, 3);

    ++row;
    strategyGrid->addWidget(new QLabel("Stop Loss:", strategyBox), row, 0);
    auto *stopLossEnable = new QCheckBox("Enable", strategyBox);
    strategyGrid->addWidget(stopLossEnable, row, 1);

    auto *stopScopeCombo = new QComboBox(strategyBox);
    stopScopeCombo->addItems({"Per Trade Stop Loss", "Global Portfolio Stop", "Trailing Stop"});
    strategyGrid->addWidget(stopScopeCombo, row, 2, 1, 2);

    auto *stopUsdtSpin = new QDoubleSpinBox(strategyBox);
    stopUsdtSpin->setRange(0.0, 1'000'000.0);
    stopUsdtSpin->setDecimals(2);
    stopUsdtSpin->setSuffix(" USDT");
    stopUsdtSpin->setEnabled(false);
    strategyGrid->addWidget(stopUsdtSpin, row, 4);

    auto *stopPctSpin = new QDoubleSpinBox(strategyBox);
    stopPctSpin->setRange(0.0, 100.0);
    stopPctSpin->setDecimals(2);
    stopPctSpin->setSuffix(" %");
    stopPctSpin->setEnabled(false);
    strategyGrid->addWidget(stopPctSpin, row, 5);

    connect(stopLossEnable, &QCheckBox::toggled, stopScopeCombo, &QWidget::setEnabled);
    connect(stopLossEnable, &QCheckBox::toggled, stopUsdtSpin, &QWidget::setEnabled);
    connect(stopLossEnable, &QCheckBox::toggled, stopPctSpin, &QWidget::setEnabled);

    ++row;
    strategyGrid->addWidget(new QLabel("Template:", strategyBox), row, 0);
    auto *templateCombo = new QComboBox(strategyBox);
    templateCombo->addItems({"No Template", "Futures Public Lead Trader", "Volume Top 50", "RSI Reversal"});
    strategyGrid->addWidget(templateCombo, row, 1, 1, 2);

    strategyGrid->setColumnStretch(1, 1);
    strategyGrid->setColumnStretch(3, 1);
    strategyGrid->setColumnStretch(5, 1);

    auto *indicatorsBox = new QGroupBox("Indicators", page);
    auto *indGrid = new QGridLayout(indicatorsBox);
    indGrid->setHorizontalSpacing(14);
    indGrid->setVerticalSpacing(8);
    indGrid->setContentsMargins(12, 12, 12, 12);

    auto addIndicatorRow = [indicatorsBox, indGrid](int rowIndex, const QString &name) {
        auto *cb = new QCheckBox(name, indicatorsBox);
        auto *btn = new QPushButton("Buy-Sell Values", indicatorsBox);
        btn->setMinimumWidth(150);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        QObject::connect(cb, &QCheckBox::toggled, btn, &QWidget::setEnabled);
        indGrid->addWidget(cb, rowIndex, 0);
        indGrid->addWidget(btn, rowIndex, 1);
    };

    QStringList indicators = {
        "Moving Average (MA)", "Donchian Channels (DC)", "Parabolic SAR (PSAR)", "Bollinger Bands (BB)",
        "Relative Strength Index (RSI)", "Volume", "Stochastic RSI", "Williams %R", "MACD",
        "Ultimate Oscillator", "ADX", "DMI", "SuperTrend", "EMA Cross"
    };
    for (int i = 0; i < indicators.size(); ++i) {
        addIndicatorRow(i, indicators[i]);
    }
    indGrid->setColumnStretch(0, 1);
    indGrid->setColumnStretch(1, 1);
    root->addWidget(indicatorsBox);

    root->addStretch();

    applyDashboardTheme(dashboardThemeCombo_ ? dashboardThemeCombo_->currentText() : QString());
    return page;
}

void BacktestWindow::applyDashboardTheme(const QString &themeName) {
    if (!dashboardPage_) {
        return;
    }

    const bool isLight = themeName.compare("Light", Qt::CaseInsensitive) == 0;
    const QString darkCss = R"(
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
    )";

    const QString lightCss = R"(
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
    )";

    const QString darkGlobal = R"(
        QMainWindow { background: #0b0f16; }
        QTabWidget::pane { border: 1px solid #1f2937; background: #0b0f16; }
        QTabBar::tab { background: #111827; color: #e5e7eb; padding: 6px 10px; }
        QTabBar::tab:selected { background: #1f2937; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage { background: #0b0f16; color: #e5e7eb; }
        QScrollArea#backtestScrollArea { background: #0b0f16; border: none; }
        QWidget#backtestScrollWidget { background: #0b0f16; }
        QGroupBox { color: #e5e7eb; border-color: #1f2937; }
        QLabel { color: #e5e7eb; }
        QLabel:disabled, QCheckBox:disabled, QComboBox:disabled, QLineEdit:disabled { color: #9ca3af; }
        QGroupBox::title { color: #e5e7eb; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 3px 6px; }
        QListWidget { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; }
        QPushButton { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 6px 10px; }
        QPushButton:hover { background: #1f2937; }
        QTableWidget { background: #0d1117; color: #e5e7eb; gridline-color: #1f2937; selection-background-color: #1f2937; selection-color: #e5e7eb; }
        QHeaderView::section { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; }
    )";

    const QString lightGlobal = R"(
        QMainWindow { background: #f5f7fb; }
        QTabWidget::pane { border: 1px solid #d1d5db; background: #f5f7fb; }
        QTabBar::tab { background: #e5e7eb; color: #0f172a; padding: 6px 10px; }
        QTabBar::tab:selected { background: #ffffff; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage { background: #f5f7fb; color: #0f172a; }
        QScrollArea#backtestScrollArea { background: #f5f7fb; border: none; }
        QWidget#backtestScrollWidget { background: #f5f7fb; }
        QGroupBox { color: #0f172a; border-color: #d1d5db; }
        QLabel { color: #0f172a; }
        QLabel:disabled, QCheckBox:disabled, QComboBox:disabled, QLineEdit:disabled { color: #6b7280; }
        QGroupBox::title { color: #0f172a; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; }
        QListWidget { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; }
        QPushButton { background: #e5e7eb; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 10px; }
        QPushButton:hover { background: #dbeafe; }
        QTableWidget { background: #ffffff; color: #0f172a; gridline-color: #d1d5db; selection-background-color: #dbeafe; selection-color: #0f172a; }
        QHeaderView::section { background: #e5e7eb; color: #0f172a; border: 1px solid #d1d5db; }
    )";

    // Apply to the whole window (covers Chart/Positions/Backtest/Code tabs)
    this->setStyleSheet(isLight ? lightGlobal : darkGlobal);

    // Apply dashboard-specific overrides
    dashboardPage_->setStyleSheet(isLight ? lightCss : darkCss);

    // Apply code tab readability (headings + content on matching background)
    if (codePage_) {
        const QString codeCss = isLight
                                    ? QStringLiteral(
                                          "QWidget#codePage { background: #f5f7fb; color: #0f172a; }"
                                          "QLabel { color: #0f172a; }"
                                          "QTableWidget { background: #ffffff; color: #0f172a; gridline-color: #d1d5db; }"
                                          "QHeaderView::section { background: #e5e7eb; color: #0f172a; }")
                                    : QStringLiteral(
                                          "QWidget#codePage { background: #0b0f16; color: #e5e7eb; }"
                                          "QLabel { color: #e5e7eb; }"
                                          "QTableWidget { background: #0d1117; color: #e5e7eb; gridline-color: #1f2937; }"
                                          "QHeaderView::section { background: #111827; color: #e5e7eb; }");
        codePage_->setStyleSheet(codeCss);
    }
}

QWidget *BacktestWindow::createChartTab() {
    auto *page = new QWidget(this);
    page->setObjectName("chartPage");
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(10);

    auto *heading = new QLabel("Chart", page);
    heading->setStyleSheet("font-size: 18px; font-weight: 600;");
    layout->addWidget(heading);

    auto *desc = new QLabel(
        "TradingView/price chart workspace to match the Python Chart tab. Embedded chart uses TradingView widget.",
        page);
    desc->setWordWrap(true);
    layout->addWidget(desc);

#if HAS_QT_WEBENGINE
    auto *view = new QWebEngineView(page);
    view->setMinimumHeight(520);
    view->setContextMenuPolicy(Qt::NoContextMenu);
  const auto html = QStringLiteral(R"(
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    html, body, #container {
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      background: #0b1020;
      overflow: hidden; /* prevent scrollbars */
    }
    ::-webkit-scrollbar { width: 0px; height: 0px; display: none; }
  </style>
</head>
<body>
  <div id="container">
    <div class="tradingview-widget-container" style="height:100%; width:100%;">
      <div id="tradingview_embed"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({
          "width": "100%",
          "height": "100%",
          "symbol": "BINANCE:BTCUSDT",
          "interval": "60",
          "timezone": "Etc/UTC",
          "theme": "dark",
          "style": "1",
          "locale": "en",
          "toolbar_bg": "#0b1020",
          "enable_publishing": false,
          "hide_top_toolbar": false,
          "hide_legend": false,
          "allow_symbol_change": true,
          "container_id": "tradingview_embed"
        });
      </script>
    </div>
  </div>
</body>
</html>
    )");
    view->setHtml(html, QUrl("https://www.tradingview.com/"));
    layout->addWidget(view, 1);
#else
    auto *placeholder = new QWidget(page);
    placeholder->setMinimumHeight(420);
    placeholder->setStyleSheet("background-color: #0f1624; border: 1px dashed #2d3748;");
    layout->addWidget(placeholder, 1);

    auto *hint = new QLabel(
        "Qt WebEngine is not installed in this toolchain, so the embedded chart is disabled. "
        "Click below to open TradingView in your browser.", page);
    hint->setWordWrap(true);
    layout->addWidget(hint);

    auto *openBtn = new QPushButton("Open TradingView Chart in Browser", page);
    connect(openBtn, &QPushButton::clicked, this, []() {
        QDesktopServices::openUrl(QUrl("https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT"));
    });
    layout->addWidget(openBtn, 0, Qt::AlignLeft);
#endif

    return page;
}

QWidget *BacktestWindow::createPositionsTab() {
    auto *page = new QWidget(this);
    page->setObjectName("positionsPage");
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(12);

    auto *heading = new QLabel("Positions", page);
    heading->setStyleSheet("font-size: 18px; font-weight: 600;");
    layout->addWidget(heading);

    auto *desc = new QLabel(
        "Live/active positions view to mirror the Python Positions tab. Populate rows from your trading engine.",
        page);
    desc->setWordWrap(true);
    layout->addWidget(desc);

    auto *table = new QTableWidget(0, 10, page);
    table->setHorizontalHeaderLabels({
        "Symbol", "Interval", "Side", "Entry", "Mark", "Position %", "ROI (USDT)", "ROI (%)", "Leverage", "Status"
    });
    table->horizontalHeader()->setStretchLastSection(true);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    layout->addWidget(table, 1);

    return page;
}

QWidget *BacktestWindow::createBacktestTab() {
    auto *page = new QWidget(this);
    page->setObjectName("backtestPage");
    auto *rootLayout = new QVBoxLayout(page);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    auto *scrollArea = new QScrollArea(page);
    scrollArea->setObjectName("backtestScrollArea");
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    rootLayout->addWidget(scrollArea);

    auto *scrollWidget = new QWidget(scrollArea);
    scrollWidget->setObjectName("backtestScrollWidget");
    scrollArea->setWidget(scrollWidget);
    auto *contentLayout = new QVBoxLayout(scrollWidget);
    contentLayout->setContentsMargins(12, 12, 12, 12);
    contentLayout->setSpacing(16);

    auto *topLayout = new QHBoxLayout();
    topLayout->setSpacing(16);
    contentLayout->addLayout(topLayout);

    topLayout->addWidget(createMarketsGroup(), 4);
    topLayout->addWidget(createParametersGroup(), 3);
    topLayout->addWidget(createIndicatorsGroup(), 2);

    auto *controlsLayout = new QHBoxLayout();
    runButton_ = new QPushButton("Run Backtest", page);
    controlsLayout->addWidget(runButton_);
    stopButton_ = new QPushButton("Stop", page);
    stopButton_->setEnabled(false);
    controlsLayout->addWidget(stopButton_);

    statusLabel_ = new QLabel(page);
    statusLabel_->setMinimumWidth(220);
    controlsLayout->addWidget(statusLabel_);

    addSelectedBtn_ = new QPushButton("Add Selected to Dashboard", page);
    controlsLayout->addWidget(addSelectedBtn_);
    addAllBtn_ = new QPushButton("Add All to Dashboard", page);
    controlsLayout->addWidget(addAllBtn_);
    controlsLayout->addStretch();

    auto *botStatusWidget = new QWidget(page);
    auto *botStatusLayout = new QHBoxLayout(botStatusWidget);
    botStatusLayout->setContentsMargins(0, 0, 0, 0);
    botStatusLayout->setSpacing(8);
    botStatusLabel_ = new QLabel("Bot Status: Idle", botStatusWidget);
    botTimeLabel_ = new QLabel("Bot Active Time: --", botStatusWidget);
    botStatusLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    botTimeLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    botStatusLayout->addWidget(botStatusLabel_);
    botStatusLayout->addWidget(botTimeLabel_);
    controlsLayout->addWidget(botStatusWidget);

    contentLayout->addLayout(controlsLayout);
    contentLayout->addWidget(createResultsGroup(), 1);

    return page;
}

void BacktestWindow::launchPythonBot() {
    QDir dir(QCoreApplication::applicationDirPath());
    dir.cd("../../../Languages/Python/Crypto-Exchanges/Binance");
    const QString script = dir.filePath("main.py");
    if (!QFileInfo::exists(script)) {
        QMessageBox::warning(this, "Python bot missing", QString("Could not find %1").arg(script));
        return;
    }
    QString python = "pythonw.exe";
    if (QStandardPaths::findExecutable(python).isEmpty()) {
        python = "python.exe";
        if (QStandardPaths::findExecutable(python).isEmpty()) {
            python = "python";
        }
    }
    const bool ok = QProcess::startDetached(python, {script}, dir.absolutePath());
    if (!ok) {
        QMessageBox::critical(this, "Launch failed", "Unable to start the Python Binance bot.");
    }
}

QWidget *BacktestWindow::createCodeTab() {
    auto *page = new QWidget(this);
    page->setObjectName("codePage");
    codePage_ = page;
    auto *outer = new QVBoxLayout(page);
    outer->setContentsMargins(16, 16, 16, 16);
    outer->setSpacing(10);

    auto *scroll = new QScrollArea(page);
    scroll->setWidgetResizable(true);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    outer->addWidget(scroll);

    auto *container = new QWidget(scroll);
    scroll->setWidget(container);
    auto *layout = new QVBoxLayout(container);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->setSpacing(14);

    auto *heading = new QLabel("Code Languages And Exchanges", container);
    heading->setStyleSheet("font-size: 20px; font-weight: 700;");
    layout->addWidget(heading);

    auto *sub = new QLabel(
        "Select your preferred code language, crypto exchange, and forex broker. Folders for each selection are created "
        "automatically to keep related assets organized.",
        container);
    sub->setWordWrap(true);
    sub->setStyleSheet("color: #cbd5e1;");
    layout->addWidget(sub);

    auto makeBadge = [](const QString &text, const QString &bg) {
        auto *lbl = new QLabel(text);
        lbl->setStyleSheet(QString("padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 700; "
                                   "color: #cbd5e1; background: %1;")
                               .arg(bg));
        return lbl;
    };
    auto makeCard = [&](const QString &title,
                        const QString &subtitle,
                        const QString &border,
                        const QString &badgeText = QString(),
                        const QString &badgeBg = QString("#1f2937"),
                        bool disabled = false,
                        std::function<void()> onClick = nullptr) {
        auto *button = new QPushButton(container);
        button->setFlat(true);
        button->setCursor(disabled ? Qt::ArrowCursor : Qt::PointingHandCursor);
        button->setStyleSheet("QPushButton { border: none; padding: 0; text-align: left; }");
        button->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);

        auto *card = new QFrame(button);
        card->setMinimumHeight(130);
        card->setMaximumHeight(150);
        card->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::MinimumExpanding);
        if (!disabled) {
            card->setStyleSheet(QString(
                "QFrame { border: 2px solid #1f2937; border-radius: 10px; background: #0d1117; padding: 8px; }"
                "QLabel { color: #e6edf3; }"
                "QPushButton:hover QFrame { border-color: %1; }"
                "QPushButton:pressed QFrame { border-color: %1; background: #0f172a; }").arg(border));
        } else {
            card->setStyleSheet(
                "QFrame { border: 2px solid #1f2937; border-radius: 10px; background: #0d1117; padding: 8px; }"
                "QLabel { color: #6b7280; }");
        }
        auto *v = new QVBoxLayout(card);
        v->setContentsMargins(12, 10, 12, 10);
        v->setSpacing(6);
        if (!badgeText.isEmpty()) {
            v->addWidget(makeBadge(badgeText, badgeBg), 0, Qt::AlignLeft);
        }
        auto *titleLbl = new QLabel(title, card);
        titleLbl->setStyleSheet(QString("font-size: 18px; font-weight: 700; color:%1;")
                                    .arg(disabled ? "#6b7280" : "#e6edf3"));
        v->addWidget(titleLbl);
        auto *subLbl = new QLabel(subtitle, card);
        subLbl->setWordWrap(true);
        subLbl->setStyleSheet(QString("color:%1; font-size: 12px;").arg(disabled ? "#4b5563" : "#94a3b8"));
        v->addWidget(subLbl);
        v->addStretch();

        auto *btnLayout = new QVBoxLayout(button);
        btnLayout->setContentsMargins(0, 0, 0, 0);
        btnLayout->addWidget(card);

        button->setEnabled(!disabled);
        if (onClick && !disabled) {
            connect(button, &QPushButton::clicked, button, [onClick]() { onClick(); });
        }
        return button;
    };

    auto addSection = [&](const QString &title, const QList<QWidget *> &cards) {
        auto *titleLbl = new QLabel(title, container);
        titleLbl->setStyleSheet("font-size: 16px; font-weight: 700;");
        layout->addWidget(titleLbl);

        auto *row = new QGridLayout();
        row->setHorizontalSpacing(12);
        row->setVerticalSpacing(12);

        for (int i = 0; i < cards.size(); ++i) {
            row->addWidget(cards[i], 0, i);
        }
        layout->addLayout(row);
    };

    addSection("Choose your language",
               {makeCard("Python", "Fast to build - Huge ecosystem", "#22d3ee", "Recommended", "#1d4ed8", false,
                         [this]() { launchPythonBot(); }),
                makeCard("C++", "Qt native desktop (preview)", "#2563eb", "Preview", "#1f2937"),
                makeCard("Rust", "Memory safe - coming soon", "#1f2937", "Coming Soon", "#1f2937", true),
                makeCard("C", "Low-level power - coming soon", "#1f2937", "Coming Soon", "#1f2937", true)});

    addSection("Choose your market",
               {makeCard("Crypto Exchange", "Binance, Bybit, KuCoin", "#10b981"),
                makeCard("Forex Exchange", "OANDA, FXCM, MetaTrader - coming soon", "#1f2937", "Coming Soon",
                         "#1f2937", true)});

    addSection("Crypto exchanges",
               {makeCard("Binance", "Advanced desktop bot ready to launch", "#f59e0b"),
                makeCard("Bybit", "Derivatives-focused - coming soon", "#1f2937", "Coming Soon", "#1f2937", true),
                makeCard("OKX", "Options + spot - coming soon", "#1f2937", "Coming Soon", "#1f2937", true)});

    auto *envTitle = new QLabel("Environment Versions", container);
    envTitle->setStyleSheet("font-size: 14px; font-weight: 700;");
    layout->addWidget(envTitle);

    auto *table = new QTableWidget(container);
    table->setColumnCount(3);
    table->setHorizontalHeaderLabels({"Dependency", "Installed", "Latest"});
    table->horizontalHeader()->setStretchLastSection(true);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table->setSelectionMode(QAbstractItemView::NoSelection);
    table->verticalHeader()->setVisible(false);
    table->horizontalHeader()->setStyleSheet("font-weight: 700;");

    struct Row {
        const char *name;
        const char *installed;
        const char *latest;
    };
    const Row rows[] = {
        {"python-binance", "1.0.19", "1.0.32"}, {"binance-connector", "3.12.0", "3.12.0"},
        {"PyQt6", "6.9.1", "6.10.0"},          {"PyQt6-Qt6", "6.9.2", "6.10.0"},
        {"PyQt6-WebEngine", "6.9.0", "6.10.0"}, {"numba", "0.61.2", "0.62.1"},
        {"llvmlite", "0.44.0", "0.45.1"},       {"numpy", "2.2.6", "2.3.5"},
        {"pandas", "2.3.2", "2.3.3"},           {"pandas-ta", "0.4.7b0", "0.4.7b0"},
        {"requests", "2.32.3", "2.32.3"}};
    table->setRowCount(static_cast<int>(std::size(rows)));
    for (int i = 0; i < static_cast<int>(std::size(rows)); ++i) {
        table->setItem(i, 0, new QTableWidgetItem(rows[i].name));
        table->setItem(i, 1, new QTableWidgetItem(rows[i].installed));
        table->setItem(i, 2, new QTableWidgetItem(rows[i].latest));
    }
    layout->addWidget(table);

    auto *statusRow = new QHBoxLayout();
    auto *statusLbl = new QLabel("Bot Status: OFF", container);
    statusLbl->setStyleSheet("color: #ef4444; font-weight: 700;");
    auto *activeLbl = new QLabel("Bot Active Time: --", container);
    activeLbl->setStyleSheet("color: #cbd5e1;");
    statusRow->addStretch();
    statusRow->addWidget(statusLbl);
    statusRow->addSpacing(18);
    statusRow->addWidget(activeLbl);
    layout->addLayout(statusRow);

    layout->addStretch();
    return page;
}

QWidget *BacktestWindow::createMarketsGroup() {
    auto *group = new QGroupBox("Markets", this);
    auto *layout = new QGridLayout(group);

    auto *symbolLabel = new QLabel("Symbol Source:", group);
    symbolSourceCombo_ = new QComboBox(group);
    symbolSourceCombo_->addItems({"Futures", "Spot"});
    auto *refreshBtn = new QPushButton("Refresh", group);
    layout->addWidget(symbolLabel, 0, 0);
    layout->addWidget(symbolSourceCombo_, 0, 1);
    layout->addWidget(refreshBtn, 0, 2);

    auto *symbolsInfo = new QLabel("Symbols (select 1 or more):", group);
    layout->addWidget(symbolsInfo, 1, 0, 1, 3);
    symbolList_ = new QListWidget(group);
    symbolList_->setSelectionMode(QAbstractItemView::MultiSelection);
    symbolList_->setMinimumWidth(220);
    symbolList_->setMaximumWidth(280);
    layout->addWidget(symbolList_, 2, 0, 4, 3);

    auto *intervalInfo = new QLabel("Intervals (select 1 or more):", group);
    layout->addWidget(intervalInfo, 1, 3);
    intervalList_ = new QListWidget(group);
    intervalList_->setSelectionMode(QAbstractItemView::MultiSelection);
    intervalList_->setMinimumWidth(180);
    intervalList_->setMaximumWidth(240);
    layout->addWidget(intervalList_, 2, 3, 4, 2);

    customIntervalEdit_ = new QLineEdit(group);
    customIntervalEdit_->setPlaceholderText("e.g., 45s, 7m, 90m");
    layout->addWidget(customIntervalEdit_, 6, 3, 1, 1);
    auto *addBtn = new QPushButton("Add Custom Interval(s)", group);
    layout->addWidget(addBtn, 6, 4, 1, 1);
    connect(addBtn, &QPushButton::clicked, this, &BacktestWindow::handleAddCustomIntervals);
    connect(refreshBtn, &QPushButton::clicked, this, [this]() {
        updateStatusMessage("Symbol catalog refreshed from " + symbolSourceCombo_->currentText());
    });

    return group;
}

QWidget *BacktestWindow::createParametersGroup() {
    auto *group = new QGroupBox("Parameters", this);
    auto *form = new QFormLayout(group);

    auto addCombo = [form](const QString &label, const QStringList &items) {
        auto *combo = new QComboBox(form->parentWidget());
        combo->addItems(items);
        form->addRow(label, combo);
        return combo;
    };

    addCombo("Logic:", {"AND", "OR"});
    auto *startDate = new QDateEdit(QDate::currentDate().addMonths(-1), group);
    startDate->setCalendarPopup(true);
    form->addRow("Start Date:", startDate);
    auto *endDate = new QDateEdit(QDate::currentDate(), group);
    endDate->setCalendarPopup(true);
    form->addRow("End Date:", endDate);

    auto *capitalSpin = new QDoubleSpinBox(group);
    capitalSpin->setSuffix(" USDT");
    capitalSpin->setRange(0.0, 1'000'000.0);
    capitalSpin->setValue(1000.0);
    form->addRow("Capital:", capitalSpin);

    auto *positionPct = new QDoubleSpinBox(group);
    positionPct->setSuffix(" %");
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setValue(2.0);
    form->addRow("Position %:", positionPct);

    auto *sideCombo = addCombo("Side:", {"BOTH", "BUY", "SELL"});
    sideCombo->setCurrentText("BOTH");

    addCombo("Margin Mode:", {"Isolated", "Cross"});
    addCombo("Position Mode:", {"Hedge", "One-way"});
    addCombo("Assets Mode:", {"Single-Asset", "Multi-Asset"});
    addCombo("Account Mode:", {"Classic Trading", "Multi-Asset Mode"});

    auto *leverageSpin = new QSpinBox(group);
    leverageSpin->setRange(1, 125);
    leverageSpin->setValue(5);
    form->addRow("Leverage:", leverageSpin);

    auto *loopSpin = new QSpinBox(group);
    loopSpin->setRange(1, 10'000);
    loopSpin->setSuffix(" ms");
    loopSpin->setValue(500);
    form->addRow("Loop Interval:", loopSpin);

    addCombo("MDD Logic:", {"Per Trade", "Cumulative", "Entire Account"});

    auto *templateEnable = new QCheckBox("Enable Backtest Template", group);
    templateEnable->setChecked(false);
    auto *templateCombo = new QComboBox(group);
    templateCombo->addItems({"Volume Top 50", "RSI Reversal", "StochRSI Sweep"});
    templateCombo->setEnabled(false);

    connect(templateEnable, &QCheckBox::toggled, templateCombo, &QWidget::setEnabled);
    form->addRow(templateEnable);
    form->addRow("Template:", templateCombo);

    return group;
}

QWidget *BacktestWindow::createIndicatorsGroup() {
    auto *group = new QGroupBox("Indicators", this);
    auto *grid = new QGridLayout(group);
    grid->setHorizontalSpacing(14);
    grid->setVerticalSpacing(8);
    grid->setColumnStretch(0, 2);
    grid->setColumnStretch(1, 1);

    const QStringList indicators = {
        "Moving Average (MA)", "Donchian Channels", "Parabolic SAR", "Bollinger Bands",
        "Relative Strength Index", "Volume", "Stochastic RSI", "Williams %R",
        "MACD", "Ultimate Oscillator", "ADX", "DMI", "SuperTrend", "EMA", "Stochastic Oscillator"
    };

    int row = 0;
    for (const auto &ind : indicators) {
        auto *cb = new QCheckBox(ind, group);
        auto *btn = new QPushButton("Params...", group);
        btn->setMinimumWidth(140);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        connect(cb, &QCheckBox::toggled, btn, &QWidget::setEnabled);
        grid->addWidget(cb, row, 0);
        grid->addWidget(btn, row, 1);
        ++row;
    }

    return group;
}

QWidget *BacktestWindow::createResultsGroup() {
    auto *group = new QGroupBox("Backtest Results", this);
    auto *layout = new QVBoxLayout(group);
    resultsTable_ = new QTableWidget(0, 10, group);
    resultsTable_->setHorizontalHeaderLabels({
        "Symbol", "Interval", "Logic", "Trades", "Loop Interval",
        "Start Date", "End Date", "Position %", "ROI (USDT)", "ROI (%)"
    });
    resultsTable_->horizontalHeader()->setStretchLastSection(true);
    resultsTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    layout->addWidget(resultsTable_);
    return group;
}

void BacktestWindow::populateDefaults() {
    if (symbolList_) {
        symbolList_->addItems({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"});
        for (int i = 0; i < symbolList_->count(); ++i) {
            if (i < 2) {
                symbolList_->item(i)->setSelected(true);
            }
        }
    }
    if (intervalList_) {
        intervalList_->addItems({"1m", "3m", "5m", "15m", "1h", "4h", "1d"});
        for (int i = 0; i < intervalList_->count() && i < 2; ++i) {
            intervalList_->item(i)->setSelected(true);
        }
    }
}

void BacktestWindow::wireSignals() {
    connect(runButton_, &QPushButton::clicked, this, &BacktestWindow::handleRunBacktest);
    connect(stopButton_, &QPushButton::clicked, this, &BacktestWindow::handleStopBacktest);
    connect(addSelectedBtn_, &QPushButton::clicked, this, [this]() {
        const int selectedSymbols = symbolList_ ? symbolList_->selectedItems().size() : 0;
        const int selectedIntervals = intervalList_ ? intervalList_->selectedItems().size() : 0;
        updateStatusMessage(
            QString("Added %1 symbol(s) x %2 interval(s) to dashboard.")
                .arg(selectedSymbols)
                .arg(selectedIntervals));
    });
    connect(addAllBtn_, &QPushButton::clicked, this, [this]() {
        const int symbolCount = symbolList_ ? symbolList_->count() : 0;
        const int intervalCount = intervalList_ ? intervalList_->count() : 0;
        updateStatusMessage(
            QString("Added all %1 symbol(s) x %2 interval(s) to dashboard.")
                .arg(symbolCount)
                .arg(intervalCount));
    });
}

void BacktestWindow::handleAddCustomIntervals() {
    if (!intervalList_) {
        return;
    }
    const QString raw = customIntervalEdit_ ? customIntervalEdit_->text().trimmed() : QString();
    if (raw.isEmpty()) {
        updateStatusMessage("No intervals entered.");
        return;
    }
    const auto parts = raw.split(',', Qt::SkipEmptyParts);
    for (QString part : parts) {
        part = part.trimmed();
        appendUniqueInterval(part);
    }
    if (customIntervalEdit_) {
        customIntervalEdit_->clear();
    }
    updateStatusMessage("Custom intervals appended.");
}

void BacktestWindow::handleRunBacktest() {
    botStart_ = std::chrono::steady_clock::now();
    ensureBotTimer(true);
    botStatusLabel_->setText("Bot Status: Running");
    runButton_->setEnabled(false);
    stopButton_->setEnabled(true);
    updateStatusMessage("Running backtest...");

    const int currentRow = resultsTable_->rowCount();
    resultsTable_->insertRow(currentRow);
    resultsTable_->setItem(currentRow, 0, new QTableWidgetItem("BTCUSDT"));
    resultsTable_->setItem(currentRow, 1, new QTableWidgetItem("1h"));
    resultsTable_->setItem(currentRow, 2, new QTableWidgetItem("AND"));
    resultsTable_->setItem(currentRow, 3, new QTableWidgetItem("42"));
    resultsTable_->setItem(currentRow, 4, new QTableWidgetItem("500 ms"));
    resultsTable_->setItem(currentRow, 5, new QTableWidgetItem("2024-01-01"));
    resultsTable_->setItem(currentRow, 6, new QTableWidgetItem("2024-02-01"));
    resultsTable_->setItem(currentRow, 7, new QTableWidgetItem("2%"));
    resultsTable_->setItem(currentRow, 8, new QTableWidgetItem("+152.4"));
    resultsTable_->setItem(currentRow, 9, new QTableWidgetItem("+15.2%"));
}

void BacktestWindow::handleStopBacktest() {
    ensureBotTimer(false);
    botTimeLabel_->setText("Bot Active Time: --");
    botStatusLabel_->setText("Bot Status: Stopped");
    runButton_->setEnabled(true);
    stopButton_->setEnabled(false);
    updateStatusMessage("Backtest stopped.");
}

void BacktestWindow::updateBotActiveTime() {
    if (!botTimer_) {
        return;
    }
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - botStart_);
    botTimeLabel_->setText("Bot Active Time: " + formatDuration(elapsed.count()));
}

void BacktestWindow::ensureBotTimer(bool running) {
    if (!botTimer_) {
        botTimer_ = new QTimer(this);
        botTimer_->setInterval(1000);
        connect(botTimer_, &QTimer::timeout, this, &BacktestWindow::updateBotActiveTime);
    }
    if (running) {
        botTimer_->start();
    } else {
        botTimer_->stop();
    }
}

void BacktestWindow::updateStatusMessage(const QString &message) {
    if (statusLabel_) {
        statusLabel_->setText(message);
    }
}

void BacktestWindow::appendUniqueInterval(const QString &interval) {
    if (!intervalList_ || interval.isEmpty()) {
        return;
    }
    for (int i = 0; i < intervalList_->count(); ++i) {
        if (intervalList_->item(i)->text().compare(interval, Qt::CaseInsensitive) == 0) {
            return;
        }
    }
    intervalList_->addItem(interval);
}
