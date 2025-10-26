#include "BacktestWindow.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDate>
#include <QDateEdit>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QScrollArea>
#include <QSpinBox>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTimer>
#include <QVBoxLayout>
#include <QtMath>

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
      botTimer_(nullptr) {
    setWindowTitle("Binance Trading Bot - Backtest (Qt/C++23)");
    resize(1200, 900);

    auto *central = new QWidget(this);
    setCentralWidget(central);
    auto *rootLayout = new QVBoxLayout(central);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    auto *scrollArea = new QScrollArea(central);
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
    runButton_ = new QPushButton("Run Backtest", this);
    controlsLayout->addWidget(runButton_);
    stopButton_ = new QPushButton("Stop", this);
    stopButton_->setEnabled(false);
    controlsLayout->addWidget(stopButton_);

    statusLabel_ = new QLabel(this);
    statusLabel_->setMinimumWidth(220);
    controlsLayout->addWidget(statusLabel_);

    addSelectedBtn_ = new QPushButton("Add Selected to Dashboard", this);
    controlsLayout->addWidget(addSelectedBtn_);
    addAllBtn_ = new QPushButton("Add All to Dashboard", this);
    controlsLayout->addWidget(addAllBtn_);
    controlsLayout->addStretch();

    auto *botStatusWidget = new QWidget(this);
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

    populateDefaults();
    wireSignals();
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
