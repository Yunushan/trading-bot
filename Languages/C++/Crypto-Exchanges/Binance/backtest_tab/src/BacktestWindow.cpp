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
      backtestTab_(nullptr) {
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
    auto *page = createPlaceholderTab(
        "Dashboard",
        "Overview that mirrors the Python Binance dashboard. Add PnL, bot health, and KPI summaries here."
    );
    if (auto *layout = qobject_cast<QVBoxLayout *>(page->layout())) {
        auto *table = new QTableWidget(0, 6, page);
        table->setHorizontalHeaderLabels({"Symbol", "Interval", "Logic", "PnL (USDT)", "ROI (%)", "Status"});
        table->horizontalHeader()->setStretchLastSection(true);
        table->setEditTriggers(QAbstractItemView::NoEditTriggers);
        layout->addWidget(table, 1);
    }
    return page;
}

QWidget *BacktestWindow::createChartTab() {
    auto *page = new QWidget(this);
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
    auto *rootLayout = new QVBoxLayout(page);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    auto *scrollArea = new QScrollArea(page);
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    rootLayout->addWidget(scrollArea);

    auto *scrollWidget = new QWidget(scrollArea);
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
    grid->setColumnStretch(0, 1);
    grid->setColumnStretch(1, 0);

    const QStringList indicators = {
        "Moving Average (MA)", "Donchian Channels", "Parabolic SAR", "Bollinger Bands",
        "Relative Strength Index", "Volume", "Stochastic RSI", "Williams %R",
        "MACD", "Ultimate Oscillator", "ADX", "DMI", "SuperTrend", "EMA", "Stochastic Oscillator"
    };

    int row = 0;
    for (const auto &ind : indicators) {
        auto *cb = new QCheckBox(ind, group);
        auto *btn = new QPushButton("Params...", group);
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
