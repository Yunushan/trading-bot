#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QComboBox>
#include <QDate>
#include <QDateEdit>
#include <QDoubleSpinBox>
#include <QFontMetrics>
#include <QFormLayout>
#include <QGroupBox>
#include <QGridLayout>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QItemSelectionModel>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QScrollArea>
#include <QSpinBox>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QVBoxLayout>

#include <algorithm>

void TradingBotWindow::refreshBacktestSymbolIntervalTable() {
    if (!backtestSymbolIntervalTable_) {
        return;
    }
    backtestSymbolIntervalTable_->resizeColumnsToContents();
}

void TradingBotWindow::addSelectedBacktestSymbolIntervalPairs() {
    if (!backtestSymbolIntervalTable_ || !symbolList_ || !intervalList_) {
        return;
    }

    QStringList symbols;
    for (auto *item : symbolList_->selectedItems()) {
        if (!item) {
            continue;
        }
        const QString value = item->text().trimmed().toUpper();
        if (!value.isEmpty()) {
            symbols.push_back(value);
        }
    }
    symbols.removeDuplicates();

    QStringList intervals;
    for (auto *item : intervalList_->selectedItems()) {
        if (!item) {
            continue;
        }
        const QString value = item->text().trimmed();
        if (!value.isEmpty()) {
            intervals.push_back(value);
        }
    }
    intervals.removeDuplicates();

    if (symbols.isEmpty() || intervals.isEmpty()) {
        updateStatusMessage("Select at least one symbol and interval before adding overrides.");
        return;
    }

    QSet<QString> existingKeys;
    for (int row = 0; row < backtestSymbolIntervalTable_->rowCount(); ++row) {
        const auto *symItem = backtestSymbolIntervalTable_->item(row, 0);
        const auto *intItem = backtestSymbolIntervalTable_->item(row, 1);
        const QString sym = symItem ? symItem->text().trimmed().toUpper() : QString();
        const QString iv = intItem ? intItem->text().trimmed() : QString();
        if (!sym.isEmpty() && !iv.isEmpty()) {
            existingKeys.insert(sym + "|" + iv);
        }
    }

    const QString connectorText = backtestConnectorCombo_
        ? backtestConnectorCombo_->currentText().trimmed()
        : QStringLiteral("-");
    const QString loopText = backtestLoopCombo_
        ? backtestLoopCombo_->currentText().trimmed()
        : QStringLiteral("-");
    const QString leverageText = backtestLeverageSpin_
        ? QString("%1x").arg(backtestLeverageSpin_->value())
        : QStringLiteral("-");
    const QString sideText = backtestSideCombo_
        ? backtestSideCombo_->currentText().trimmed()
        : QStringLiteral("Default");
    QString stopLossText = QStringLiteral("No");
    if (backtestStopLossEnableCheck_ && backtestStopLossEnableCheck_->isChecked()) {
        const QString mode = backtestStopLossModeCombo_
            ? backtestStopLossModeCombo_->currentData().toString().trimmed().toLower()
            : QStringLiteral("usdt");
        const QString scope = backtestStopLossScopeCombo_
            ? backtestStopLossScopeCombo_->currentData().toString().trimmed().toLower().replace('_', '-')
            : QStringLiteral("per-trade");
        stopLossText = QString("Yes (%1 | %2)")
                           .arg(mode.isEmpty() ? QStringLiteral("usdt") : mode,
                                scope.isEmpty() ? QStringLiteral("per-trade") : scope);
    }
    const QString strategyText = QString("Side: %1").arg(sideText);

    int added = 0;
    const bool wasSorting = backtestSymbolIntervalTable_->isSortingEnabled();
    backtestSymbolIntervalTable_->setSortingEnabled(false);
    for (const QString &sym : symbols) {
        for (const QString &iv : intervals) {
            const QString key = sym + "|" + iv;
            if (existingKeys.contains(key)) {
                continue;
            }
            existingKeys.insert(key);
            const int row = backtestSymbolIntervalTable_->rowCount();
            backtestSymbolIntervalTable_->insertRow(row);
            backtestSymbolIntervalTable_->setItem(row, 0, new QTableWidgetItem(sym));
            backtestSymbolIntervalTable_->setItem(row, 1, new QTableWidgetItem(iv));
            backtestSymbolIntervalTable_->setItem(row, 2, new QTableWidgetItem("Default"));
            backtestSymbolIntervalTable_->setItem(row, 3, new QTableWidgetItem(loopText));
            backtestSymbolIntervalTable_->setItem(row, 4, new QTableWidgetItem(leverageText));
            backtestSymbolIntervalTable_->setItem(row, 5, new QTableWidgetItem(connectorText.isEmpty() ? "-" : connectorText));
            backtestSymbolIntervalTable_->setItem(row, 6, new QTableWidgetItem(strategyText));
            backtestSymbolIntervalTable_->setItem(row, 7, new QTableWidgetItem(stopLossText));
            ++added;
        }
    }
    backtestSymbolIntervalTable_->setSortingEnabled(wasSorting);
    refreshBacktestSymbolIntervalTable();
    updateStatusMessage(QString("Backtest overrides updated: added %1 row(s).").arg(added));
}

void TradingBotWindow::removeSelectedBacktestSymbolIntervalPairs() {
    if (!backtestSymbolIntervalTable_) {
        return;
    }

    QList<int> rows;
    const auto selectedRows = backtestSymbolIntervalTable_->selectionModel()
        ? backtestSymbolIntervalTable_->selectionModel()->selectedRows()
        : QModelIndexList{};
    for (const QModelIndex &idx : selectedRows) {
        if (idx.isValid()) {
            rows.push_back(idx.row());
        }
    }
    std::sort(rows.begin(), rows.end(), std::greater<int>());
    rows.erase(std::unique(rows.begin(), rows.end()), rows.end());

    for (int row : rows) {
        if (row >= 0 && row < backtestSymbolIntervalTable_->rowCount()) {
            backtestSymbolIntervalTable_->removeRow(row);
        }
    }
    refreshBacktestSymbolIntervalTable();
    updateStatusMessage(QString("Backtest overrides updated: removed %1 row(s).").arg(rows.size()));
}

void TradingBotWindow::clearBacktestSymbolIntervalPairs() {
    if (!backtestSymbolIntervalTable_) {
        return;
    }
    const int rowCount = backtestSymbolIntervalTable_->rowCount();
    backtestSymbolIntervalTable_->setRowCount(0);
    updateStatusMessage(QString("Backtest overrides cleared: %1 row(s).").arg(rowCount));
}

void TradingBotWindow::refreshBacktestSymbols() {
    if (!symbolList_) {
        return;
    }

    if (backtestRefreshSymbolsBtn_) {
        backtestRefreshSymbolsBtn_->setEnabled(false);
        backtestRefreshSymbolsBtn_->setText("Refreshing...");
    }
    auto resetButton = [this]() {
        if (backtestRefreshSymbolsBtn_) {
            backtestRefreshSymbolsBtn_->setEnabled(true);
            backtestRefreshSymbolsBtn_->setText("Refresh Symbols");
        }
    };

    QSet<QString> previousSelections;
    for (auto *item : symbolList_->selectedItems()) {
        if (item) {
            previousSelections.insert(item->text().trimmed().toUpper());
        }
    }

    const bool futures = symbolSourceCombo_
        ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    const bool isTestnet = dashboardModeCombo_
        ? TradingBotWindowSupport::isTestnetModeLabel(dashboardModeCombo_->currentText())
        : false;
    const QString connectorText = backtestConnectorCombo_
        ? backtestConnectorCombo_->currentText().trimmed()
        : TradingBotWindowSupport::connectorLabelForKey(TradingBotWindowSupport::recommendedConnectorKey(futures));
    const TradingBotWindowSupport::ConnectorRuntimeConfig connectorCfg =
        TradingBotWindowSupport::resolveConnectorConfig(connectorText, futures);
    if (!connectorCfg.ok()) {
        updateStatusMessage(QString("Backtest symbols: connector error: %1").arg(connectorCfg.error));
        if (symbolList_->count() == 0) {
            symbolList_->addItems(TradingBotWindowSupport::placeholderSymbolsForExchange(QStringLiteral("Binance"), futures));
            if (symbolList_->count() > 0) {
                symbolList_->item(0)->setSelected(true);
            }
        }
        resetButton();
        return;
    }

    constexpr int kBacktestSymbolTopN = 200;
    const auto result = BinanceRestClient::fetchUsdtSymbols(
        futures,
        isTestnet,
        10000,
        true,
        kBacktestSymbolTopN,
        connectorCfg.baseUrl);

    if (!result.ok || result.symbols.isEmpty()) {
        if (symbolList_->count() == 0) {
            symbolList_->clear();
            symbolList_->addItems(TradingBotWindowSupport::placeholderSymbolsForExchange(QStringLiteral("Binance"), futures));
            if (symbolList_->count() > 0) {
                symbolList_->item(0)->setSelected(true);
            }
        }
        const QString err = result.error.trimmed().isEmpty() ? QStringLiteral("no symbols returned") : result.error.trimmed();
        updateStatusMessage(QString("Backtest symbol refresh failed: %1").arg(err));
        resetButton();
        return;
    }

    symbolList_->clear();
    symbolList_->addItems(result.symbols);

    bool anySelected = false;
    for (int i = 0; i < symbolList_->count(); ++i) {
        auto *item = symbolList_->item(i);
        if (!item) {
            continue;
        }
        const QString key = item->text().trimmed().toUpper();
        if (previousSelections.contains(key)) {
            item->setSelected(true);
            anySelected = true;
        }
    }
    if (!anySelected && symbolList_->count() > 0) {
        symbolList_->item(0)->setSelected(true);
    }

    updateStatusMessage(QString("Loaded %1 %2 symbols for backtest.")
                            .arg(result.symbols.size())
                            .arg(futures ? QStringLiteral("FUTURES") : QStringLiteral("SPOT")));
    resetButton();
}

QWidget *TradingBotWindow::createBacktestTab() {
    auto *page = new QWidget(this);
    page->setObjectName("backtestPage");
    backtestPnlActiveLabel_ = nullptr;
    backtestPnlClosedLabel_ = nullptr;
    auto *rootLayout = new QVBoxLayout(page);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    auto *scrollArea = new QScrollArea(page);
    scrollArea->setObjectName("backtestScrollArea");
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
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
    topLayout->addWidget(createParametersGroup(), 5);
    topLayout->addWidget(createIndicatorsGroup(), 3);

    auto *outputGroup = new QGroupBox("Backtest Output", page);
    auto *outputLayout = new QVBoxLayout(outputGroup);
    outputLayout->setContentsMargins(12, 12, 12, 12);
    outputLayout->setSpacing(12);

    auto *controlsLayout = new QHBoxLayout();
    runButton_ = new QPushButton("Run Backtest", outputGroup);
    controlsLayout->addWidget(runButton_);
    stopButton_ = new QPushButton("Stop", outputGroup);
    stopButton_->setEnabled(false);
    controlsLayout->addWidget(stopButton_);

    statusLabel_ = new QLabel(outputGroup);
    statusLabel_->setMinimumWidth(180);
    controlsLayout->addWidget(statusLabel_);

    addSelectedBtn_ = new QPushButton("Add Selected to Dashboard", outputGroup);
    controlsLayout->addWidget(addSelectedBtn_);
    addAllBtn_ = new QPushButton("Add All to Dashboard", outputGroup);
    controlsLayout->addWidget(addAllBtn_);
    controlsLayout->addStretch();

    auto *tabStatusWidget = new QWidget(outputGroup);
    auto *tabStatusLayout = new QHBoxLayout(tabStatusWidget);
    tabStatusLayout->setContentsMargins(0, 0, 0, 0);
    tabStatusLayout->setSpacing(8);

    auto *pnlActiveLabel = new QLabel("Total PNL Active Positions: --", tabStatusWidget);
    auto *pnlClosedLabel = new QLabel("Total PNL Closed Positions: --", tabStatusWidget);
    backtestPnlActiveLabel_ = pnlActiveLabel;
    backtestPnlClosedLabel_ = pnlClosedLabel;
    pnlActiveLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    pnlClosedLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    tabStatusLayout->addWidget(pnlActiveLabel);
    tabStatusLayout->addWidget(pnlClosedLabel);
    tabStatusLayout->addStretch();

    botStatusLabel_ = new QLabel("Bot Status: OFF", tabStatusWidget);
    botTimeLabel_ = new QLabel("Bot Active Time: --", tabStatusWidget);
    botStatusLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    botTimeLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    tabStatusLayout->addWidget(botStatusLabel_);
    tabStatusLayout->addWidget(botTimeLabel_);
    controlsLayout->addWidget(tabStatusWidget);

    outputLayout->addLayout(controlsLayout);
    outputLayout->addWidget(createResultsGroup(), 1);

    contentLayout->addWidget(outputGroup, 1);

    return page;
}

void TradingBotWindow::handleRunBacktest() {
    botStart_ = std::chrono::steady_clock::now();
    ensureBotTimer(true);
    const QString statusText = QStringLiteral("Bot Status: ON");
    const QString statusStyle = QStringLiteral("color: #16a34a; font-weight: 700;");
    const QString activeTimeText = QStringLiteral("Bot Active Time: 0s");
    if (botStatusLabel_) {
        botStatusLabel_->setText(statusText);
        botStatusLabel_->setStyleSheet(statusStyle);
    }
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText(statusText);
        chartBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (positionsBotStatusLabel_) {
        positionsBotStatusLabel_->setText(statusText);
        positionsBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (codeBotStatusLabel_) {
        codeBotStatusLabel_->setText(statusText);
        codeBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (botTimeLabel_) {
        botTimeLabel_->setText(activeTimeText);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(activeTimeText);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(activeTimeText);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(activeTimeText);
    }
    runButton_->setEnabled(false);
    stopButton_->setEnabled(true);
    updateStatusMessage("Running backtest...");
    refreshPositionsSummaryLabels();

    const int currentRow = resultsTable_->rowCount();
    resultsTable_->insertRow(currentRow);
    const QStringList values = {
        "BTCUSDT",
        "1h",
        "AND",
        "RSI, Stochastic RSI, MACD",
        "42",
        "1 minute",
        "2024-01-01",
        "2024-02-01",
        "2.00%",
        "Enabled (USDT 25.00 | Per Trade)",
        "Isolated",
        "Hedge",
        "Single-Asset",
        "Classic Trading",
        "20x",
        "+152.40",
        "+15.24%",
        "-38.12",
        "-3.81%",
        "-74.85",
        "-7.49%",
    };
    for (int col = 0; col < values.size() && col < resultsTable_->columnCount(); ++col) {
        resultsTable_->setItem(currentRow, col, new QTableWidgetItem(values.at(col)));
    }
}

void TradingBotWindow::handleStopBacktest() {
    ensureBotTimer(false);
    const QString statusText = QStringLiteral("Bot Status: OFF");
    const QString statusStyle = QStringLiteral("color: #ef4444; font-weight: 700;");
    const QString activeTimeText = QStringLiteral("Bot Active Time: --");
    if (botTimeLabel_) {
        botTimeLabel_->setText(activeTimeText);
    }
    if (botStatusLabel_) {
        botStatusLabel_->setText(statusText);
        botStatusLabel_->setStyleSheet(statusStyle);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(activeTimeText);
    }
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText(statusText);
        chartBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(activeTimeText);
    }
    if (positionsBotStatusLabel_) {
        positionsBotStatusLabel_->setText(statusText);
        positionsBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(activeTimeText);
    }
    if (codeBotStatusLabel_) {
        codeBotStatusLabel_->setText(statusText);
        codeBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (!dashboardRuntimeActive_ && dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("--");
    }
    if (!dashboardRuntimeActive_ && dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("OFF");
        dashboardBotStatusLabel_->setStyleSheet(statusStyle);
    }
    runButton_->setEnabled(true);
    stopButton_->setEnabled(false);
    updateStatusMessage("Backtest stopped.");
    refreshPositionsSummaryLabels();
}

QWidget *TradingBotWindow::createMarketsGroup() {
    auto *group = new QGroupBox("Markets & Intervals", this);
    auto *layout = new QGridLayout(group);
    layout->setHorizontalSpacing(10);
    layout->setVerticalSpacing(8);

    auto *symbolLabel = new QLabel("Symbol Source:", group);
    symbolSourceCombo_ = new QComboBox(group);
    symbolSourceCombo_->addItems({"Futures", "Spot"});
    auto *refreshBtn = new QPushButton("Refresh Symbols", group);
    backtestRefreshSymbolsBtn_ = refreshBtn;
    layout->addWidget(symbolLabel, 0, 0);
    layout->addWidget(symbolSourceCombo_, 0, 1);
    layout->addWidget(refreshBtn, 0, 2);

    auto *symbolsInfo = new QLabel("Symbols (select 1 or more):", group);
    layout->addWidget(symbolsInfo, 1, 0, 1, 3);
    symbolList_ = new QListWidget(group);
    symbolList_->setSelectionMode(QAbstractItemView::MultiSelection);
    symbolList_->setMinimumHeight(260);
    layout->addWidget(symbolList_, 2, 0, 4, 3);

    auto *intervalInfo = new QLabel("Intervals (select 1 or more):", group);
    layout->addWidget(intervalInfo, 1, 3);
    intervalList_ = new QListWidget(group);
    intervalList_->setSelectionMode(QAbstractItemView::MultiSelection);
    intervalList_->setMinimumHeight(260);
    layout->addWidget(intervalList_, 2, 3, 4, 2);

    customIntervalEdit_ = new QLineEdit(group);
    customIntervalEdit_->setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated");
    layout->addWidget(customIntervalEdit_, 6, 0, 1, 4);
    auto *addBtn = new QPushButton("Add Custom Interval(s)", group);
    layout->addWidget(addBtn, 6, 4, 1, 1);
    connect(addBtn, &QPushButton::clicked, this, &TradingBotWindow::handleAddCustomIntervals);
    connect(refreshBtn, &QPushButton::clicked, this, &TradingBotWindow::refreshBacktestSymbols);
    if (symbolSourceCombo_) {
        connect(symbolSourceCombo_, &QComboBox::currentTextChanged, this, [this](const QString &) {
            if (backtestConnectorCombo_) {
                const bool futures = symbolSourceCombo_
                    ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
                    : true;
                TradingBotWindowSupport::rebuildConnectorComboForAccount(backtestConnectorCombo_, futures, true);
            }
            refreshBacktestSymbols();
        });
    }

    auto *pairGroup = new QGroupBox("Symbol / Interval Overrides", group);
    auto *pairLayout = new QVBoxLayout(pairGroup);
    pairLayout->setContentsMargins(8, 8, 8, 8);
    pairLayout->setSpacing(8);

    backtestSymbolIntervalTable_ = new QTableWidget(0, 8, pairGroup);
    backtestSymbolIntervalTable_->setHorizontalHeaderLabels({
        "Symbol",
        "Interval",
        "Indicators",
        "Loop",
        "Leverage",
        "Connector",
        "Strategy Controls",
        "Stop-Loss",
    });
    QHeaderView *overrideHeader = backtestSymbolIntervalTable_->horizontalHeader();
    overrideHeader->setStretchLastSection(false);
    overrideHeader->setSectionResizeMode(QHeaderView::ResizeToContents);
    overrideHeader->setSectionsMovable(true);
    backtestSymbolIntervalTable_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    backtestSymbolIntervalTable_->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    backtestSymbolIntervalTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    backtestSymbolIntervalTable_->setSelectionMode(QAbstractItemView::MultiSelection);
    backtestSymbolIntervalTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    backtestSymbolIntervalTable_->setSortingEnabled(true);
    backtestSymbolIntervalTable_->setMinimumHeight(180);
    backtestSymbolIntervalTable_->verticalHeader()->setDefaultSectionSize(28);
    pairLayout->addWidget(backtestSymbolIntervalTable_);

    auto *pairButtons = new QHBoxLayout();
    auto *addPairBtn = new QPushButton("Add Selected", pairGroup);
    auto *removePairBtn = new QPushButton("Remove Selected", pairGroup);
    auto *clearPairBtn = new QPushButton("Clear All", pairGroup);
    pairButtons->addWidget(addPairBtn);
    pairButtons->addWidget(removePairBtn);
    pairButtons->addWidget(clearPairBtn);
    pairButtons->addStretch();
    pairLayout->addLayout(pairButtons);
    connect(addPairBtn, &QPushButton::clicked, this, &TradingBotWindow::addSelectedBacktestSymbolIntervalPairs);
    connect(removePairBtn, &QPushButton::clicked, this, &TradingBotWindow::removeSelectedBacktestSymbolIntervalPairs);
    connect(clearPairBtn, &QPushButton::clicked, this, &TradingBotWindow::clearBacktestSymbolIntervalPairs);
    layout->addWidget(pairGroup, 7, 0, 1, 5);

    return group;
}

QWidget *TradingBotWindow::createParametersGroup() {
    auto *group = new QGroupBox("Backtest Parameters", this);
    auto *form = new QFormLayout(group);
    form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    form->setLabelAlignment(Qt::AlignLeft | Qt::AlignVCenter);

    auto addCombo = [form](const QString &label, const QStringList &items) {
        auto *combo = new QComboBox(form->parentWidget());
        combo->addItems(items);
        form->addRow(label, combo);
        return combo;
    };

    addCombo("Signal Logic:", {"AND", "OR", "SEPARATE"});
    addCombo("MDD Logic:", {"Per Trade MDD", "Cumulative MDD", "Entire Account MDD"});

    auto *startDate = new QDateEdit(QDate::currentDate().addMonths(-1), group);
    startDate->setCalendarPopup(true);
    startDate->setDisplayFormat("yyyy-MM-dd");
    form->addRow("Start Date:", startDate);
    auto *endDate = new QDateEdit(QDate::currentDate(), group);
    endDate->setCalendarPopup(true);
    endDate->setDisplayFormat("yyyy-MM-dd");
    form->addRow("End Date:", endDate);

    auto *capitalSpin = new QDoubleSpinBox(group);
    capitalSpin->setSuffix(" USDT");
    capitalSpin->setRange(0.0, 1'000'000.0);
    capitalSpin->setDecimals(2);
    capitalSpin->setValue(1000.0);
    form->addRow("Capital (USDT):", capitalSpin);

    auto *positionPct = new QDoubleSpinBox(group);
    positionPct->setSuffix(" %");
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setDecimals(2);
    positionPct->setValue(2.0);
    form->addRow("Position % of Balance:", positionPct);

    auto *loopCombo = new QComboBox(group);
    loopCombo->addItem("30 seconds", "30s");
    loopCombo->addItem("45 seconds", "45s");
    loopCombo->addItem("1 minute", "1m");
    loopCombo->addItem("2 minutes", "2m");
    loopCombo->addItem("3 minutes", "3m");
    loopCombo->addItem("5 minutes", "5m");
    loopCombo->addItem("10 minutes", "10m");
    loopCombo->addItem("30 minutes", "30m");
    loopCombo->addItem("1 hour", "1h");
    loopCombo->addItem("2 hours", "2h");
    loopCombo->setCurrentIndex(loopCombo->findData("1m"));
    backtestLoopCombo_ = loopCombo;
    form->addRow("Loop Interval Override:", loopCombo);

    auto *stopLossRow = new QWidget(group);
    auto *stopLossLayout = new QHBoxLayout(stopLossRow);
    stopLossLayout->setContentsMargins(0, 0, 0, 0);
    stopLossLayout->setSpacing(6);
    auto *stopEnable = new QCheckBox("Enable", stopLossRow);
    auto *stopMode = new QComboBox(stopLossRow);
    stopMode->addItem("USDT Based Stop Loss", "usdt");
    stopMode->addItem("Percentage Based Stop Loss", "percent");
    stopMode->addItem("Both Stop Loss (USDT & Percentage)", "both");
    auto *stopScope = new QComboBox(stopLossRow);
    stopScope->addItem("Per Trade Stop Loss", "per_trade");
    stopScope->addItem("Cumulative Stop Loss", "cumulative");
    stopScope->addItem("Entire Account Stop Loss", "entire_account");
    auto *stopUsdt = new QDoubleSpinBox(stopLossRow);
    stopUsdt->setPrefix("USDT ");
    stopUsdt->setRange(0.0, 1'000'000.0);
    stopUsdt->setDecimals(2);
    stopUsdt->setSingleStep(1.0);
    stopUsdt->setValue(25.0);
    auto *stopPct = new QDoubleSpinBox(stopLossRow);
    stopPct->setSuffix(" %");
    stopPct->setRange(0.0, 100.0);
    stopPct->setDecimals(2);
    stopPct->setSingleStep(0.1);
    stopPct->setValue(2.0);

    stopLossLayout->addWidget(stopEnable);
    stopLossLayout->addWidget(stopMode, 1);
    stopLossLayout->addWidget(stopScope, 1);
    stopLossLayout->addWidget(stopUsdt);
    stopLossLayout->addWidget(stopPct);
    form->addRow("Stop Loss:", stopLossRow);
    backtestStopLossEnableCheck_ = stopEnable;
    backtestStopLossModeCombo_ = stopMode;
    backtestStopLossScopeCombo_ = stopScope;

    const auto updateStopLossWidgets = [stopEnable, stopMode, stopScope, stopUsdt, stopPct]() {
        const bool enabled = stopEnable->isChecked();
        stopMode->setEnabled(enabled);
        stopScope->setEnabled(enabled);
        stopUsdt->setEnabled(enabled);
        stopPct->setEnabled(enabled);
        const QString mode = stopMode->currentData().toString();
        stopUsdt->setVisible(enabled && (mode == "usdt" || mode == "both"));
        stopPct->setVisible(enabled && (mode == "percent" || mode == "both"));
    };
    connect(stopEnable, &QCheckBox::toggled, this, [updateStopLossWidgets](bool) {
        updateStopLossWidgets();
    });
    connect(stopMode, &QComboBox::currentIndexChanged, this, [updateStopLossWidgets](int) {
        updateStopLossWidgets();
    });
    updateStopLossWidgets();

    auto *sideCombo = addCombo("Side:", {"Buy (Long)", "Sell (Short)", "Both (Long/Short)"});
    sideCombo->setCurrentText("Both (Long/Short)");
    backtestSideCombo_ = sideCombo;

    addCombo("Margin Mode (Futures):", {"Isolated", "Cross"});
    addCombo("Position Mode:", {"Hedge", "One-way"});
    auto *assetsCombo = new QComboBox(group);
    assetsCombo->addItem("Single-Asset Mode", "Single-Asset");
    assetsCombo->addItem("Multi-Assets Mode", "Multi-Assets");
    form->addRow("Assets Mode:", assetsCombo);
    addCombo("Account Mode:", {"Classic Trading", "Multi-Asset Mode"});

    auto *connectorCombo = new QComboBox(group);
    const bool sourceFutures = symbolSourceCombo_
        ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    TradingBotWindowSupport::rebuildConnectorComboForAccount(connectorCombo, sourceFutures, true);
    connectorCombo->setMinimumWidth(220);
    form->addRow("Connector:", connectorCombo);
    backtestConnectorCombo_ = connectorCombo;
    connect(connectorCombo, &QComboBox::currentTextChanged, this, [this](const QString &) {
        refreshBacktestSymbols();
    });

    auto *leverageSpin = new QSpinBox(group);
    leverageSpin->setRange(1, 150);
    leverageSpin->setValue(5);
    backtestLeverageSpin_ = leverageSpin;
    form->addRow("Leverage (Futures):", leverageSpin);

    auto *templateEnable = new QCheckBox("Enable", group);
    templateEnable->setChecked(false);
    auto *templateCombo = new QComboBox(group);
    templateCombo->addItems({
        "First 50 Highest Volume",
        "Last 1 week · 2% per trade · 50 highest volume",
        "Top 100, %2 per trade, isolated, %20 (%1 Actual Move) per trade SL",
    });
    templateCombo->setEnabled(false);

    connect(templateEnable, &QCheckBox::toggled, templateCombo, &QWidget::setEnabled);
    form->addRow("Template:", templateCombo);
    form->addRow("", templateEnable);

    auto *scanRow = new QWidget(group);
    auto *scanLayout = new QHBoxLayout(scanRow);
    scanLayout->setContentsMargins(0, 0, 0, 0);
    scanLayout->setSpacing(6);
    auto *scanMddSpin = new QDoubleSpinBox(scanRow);
    scanMddSpin->setRange(0.0, 100.0);
    scanMddSpin->setDecimals(2);
    scanMddSpin->setSuffix(" %");
    scanMddSpin->setValue(0.0);
    auto *scanBtn = new QPushButton("Scan Symbols", scanRow);
    scanLayout->addWidget(scanMddSpin);
    scanLayout->addWidget(scanBtn);
    scanLayout->addStretch();
    connect(scanBtn, &QPushButton::clicked, this, [this, scanMddSpin]() {
        updateStatusMessage(QString("Backtest symbol scan simulated (Max MDD: %1%).").arg(scanMddSpin->value(), 0, 'f', 2));
    });
    form->addRow("Max MDD Scanner:", scanRow);

    return group;
}

QWidget *TradingBotWindow::createIndicatorsGroup() {
    auto *group = new QGroupBox("Indicators", this);
    group->setMinimumWidth(220);
    group->setMaximumWidth(340);
    group->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
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
        auto *btn = new QPushButton("Buy-Sell Values", group);
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

QWidget *TradingBotWindow::createResultsGroup() {
    auto *group = new QGroupBox("Backtest Results", this);
    auto *layout = new QVBoxLayout(group);
    resultsTable_ = new QTableWidget(0, 21, group);
    resultsTable_->setHorizontalHeaderLabels({
        "Symbol",
        "Interval",
        "Logic",
        "Indicators",
        "Trades",
        "Loop Interval",
        "Start Date",
        "End Date",
        "Position % Of Balance",
        "Stop-Loss Options",
        "Margin Mode (Futures)",
        "Position Mode",
        "Assets Mode",
        "Account Mode",
        "Leverage (Futures)",
        "ROI (USDT)",
        "ROI (%)",
        "Max Drawdown During Position (USDT)",
        "Max Drawdown During Position (%)",
        "Max Drawdown Results (USDT)",
        "Max Drawdown Results (%)",
    });
    QHeaderView *header = resultsTable_->horizontalHeader();
    header->setStretchLastSection(false);
    header->setSectionsMovable(true);
    header->setSectionResizeMode(QHeaderView::Interactive);
    QFontMetrics fm(header->font());
    for (int col = 0; col < resultsTable_->columnCount(); ++col) {
        const auto *item = resultsTable_->horizontalHeaderItem(col);
        const QString text = item ? item->text() : QString();
        header->resizeSection(col, std::max(80, fm.horizontalAdvance(text) + 28));
    }
    resultsTable_->setSortingEnabled(true);
    resultsTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    resultsTable_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    resultsTable_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    resultsTable_->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    resultsTable_->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    resultsTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    resultsTable_->setSelectionMode(QAbstractItemView::MultiSelection);
    resultsTable_->setMinimumHeight(420);
    layout->addWidget(resultsTable_);
    return group;
}

void TradingBotWindow::populateDefaults() {
    if (symbolList_) {
        symbolList_->addItems({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"});
        for (int i = 0; i < symbolList_->count(); ++i) {
            if (i < 2) {
                symbolList_->item(i)->setSelected(true);
            }
        }
    }
    if (intervalList_) {
        intervalList_->addItems({
            "1m", "3m", "5m", "10m", "15m", "20m", "30m",
            "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h",
        });
        for (int i = 0; i < intervalList_->count() && i < 2; ++i) {
            intervalList_->item(i)->setSelected(true);
        }
    }
}

void TradingBotWindow::wireSignals() {
    connect(runButton_, &QPushButton::clicked, this, &TradingBotWindow::handleRunBacktest);
    connect(stopButton_, &QPushButton::clicked, this, &TradingBotWindow::handleStopBacktest);
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
