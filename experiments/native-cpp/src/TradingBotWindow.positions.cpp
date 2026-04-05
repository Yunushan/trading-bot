#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QMap>
#include <QPushButton>
#include <QSet>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QVariant>
#include <QVBoxLayout>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <limits>

namespace {

constexpr int kTableCellNumericRole = Qt::UserRole + 2;
constexpr int kPositionsRowSequenceRole = Qt::UserRole + 3;
constexpr int kTableCellRawNumericRole = Qt::UserRole + 4;
constexpr int kTableCellRawRoiBasisRole = Qt::UserRole + 5;

double tableCellRawRoiBasis(const QTableWidgetItem *item, double fallback = 0.0) {
    if (!item) {
        return fallback;
    }
    bool ok = false;
    const double rawValue = item->data(kTableCellRawRoiBasisRole).toDouble(&ok);
    if (ok && qIsFinite(rawValue)) {
        return rawValue;
    }
    const double displayValue = item->data(Qt::UserRole + 1).toDouble(&ok);
    if (ok && qIsFinite(displayValue)) {
        return displayValue;
    }
    return fallback;
}

class ScopedTableUpdatesPause final {
public:
    explicit ScopedTableUpdatesPause(QTableWidget *table, bool enabled = true)
        : table_(enabled ? table : nullptr),
          tableUpdatesWereEnabled_(table_ && table_->updatesEnabled()),
          viewport_(table_ ? table_->viewport() : nullptr),
          viewportUpdatesWereEnabled_(viewport_ && viewport_->updatesEnabled()) {
        if (tableUpdatesWereEnabled_) {
            table_->setUpdatesEnabled(false);
        }
        if (viewportUpdatesWereEnabled_) {
            viewport_->setUpdatesEnabled(false);
        }
    }

    ~ScopedTableUpdatesPause() {
        if (viewport_ && viewportUpdatesWereEnabled_) {
            viewport_->setUpdatesEnabled(true);
            viewport_->update();
        }
        if (table_ && tableUpdatesWereEnabled_) {
            table_->setUpdatesEnabled(true);
            table_->update();
        }
    }

private:
    QTableWidget *table_ = nullptr;
    bool tableUpdatesWereEnabled_ = false;
    QWidget *viewport_ = nullptr;
    bool viewportUpdatesWereEnabled_ = false;
};

QString baseAssetFromSymbol(QString symbol) {
    symbol = symbol.trimmed().toUpper();
    if (symbol.isEmpty()) {
        return QString();
    }
    if (symbol.contains('_')) {
        return symbol.section('_', 0, 0).trimmed().toUpper();
    }
    static const QStringList quoteAssets = {
        "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USD", "BTC", "ETH", "BNB",
        "EUR", "TRY", "GBP", "AUD", "BRL", "RUB", "IDR", "UAH", "ZAR", "BIDR", "PAX"
    };
    for (const auto &quote : quoteAssets) {
        if (symbol.endsWith(quote) && symbol.size() > quote.size()) {
            return symbol.left(symbol.size() - quote.size());
        }
    }
    return symbol;
}

QString formatQuantityWithSymbol(double quantity, const QString &symbol) {
    if (!qIsFinite(quantity)) {
        return QStringLiteral("-");
    }
    const QString baseAsset = baseAssetFromSymbol(symbol);
    const double absQty = std::fabs(quantity);
    int decimals = 6;
    if (absQty >= 100000.0) {
        decimals = 0;
    } else if (absQty >= 1000.0) {
        decimals = 3;
    }
    const QString qtyText = QLocale().toString(quantity, 'f', decimals);
    return baseAsset.isEmpty() ? qtyText : QStringLiteral("%1 %2").arg(qtyText, baseAsset);
}

QString formatPositionSizeText(double sizeUsdt, double quantity, const QString &symbol) {
    const QString usdtText = QStringLiteral("%1 USDT").arg(QString::number(std::max(0.0, sizeUsdt), 'f', 2));
    const QString qtyText = formatQuantityWithSymbol(quantity, symbol);
    if (qtyText == QStringLiteral("-")) {
        return usdtText;
    }
    return QStringLiteral("%1\n%2").arg(usdtText, qtyText);
}

double sumSnapshotActivePnl(const BinanceRestClient::FuturesPositionsResult &snapshot) {
    if (!snapshot.ok) {
        return 0.0;
    }
    double activePnl = 0.0;
    for (const auto &pos : snapshot.positions) {
        if (!qIsFinite(pos.positionAmt) || std::fabs(pos.positionAmt) <= 1e-10) {
            continue;
        }
        if (!qIsFinite(pos.unrealizedProfit)) {
            continue;
        }
        activePnl += pos.unrealizedProfit;
    }
    return activePnl;
}

} // namespace

QWidget *TradingBotWindow::createPositionsTab() {
    auto *page = new QWidget(this);
    page->setObjectName("positionsPage");
    positionsPnlActiveLabel_ = nullptr;
    positionsPnlClosedLabel_ = nullptr;
    positionsTotalBalanceLabel_ = nullptr;
    positionsAvailableBalanceLabel_ = nullptr;
    positionsBotStatusLabel_ = nullptr;
    positionsBotTimeLabel_ = nullptr;
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(12);

    auto *ctrlLayout = new QHBoxLayout();
    ctrlLayout->setContentsMargins(0, 0, 0, 0);
    ctrlLayout->setSpacing(8);

    auto *refreshPosBtn = new QPushButton("Refresh Positions", page);
    auto *closeAllBtn = new QPushButton("Market Close ALL Positions", page);
    auto *positionsViewLabel = new QLabel("Positions View:", page);
    auto *positionsViewCombo = new QComboBox(page);
    positionsViewCombo->addItems({"Cumulative View", "Per Trade View"});
    positionsViewCombo->setCurrentIndex(0);
    positionsViewCombo_ = positionsViewCombo;
    positionsCumulativeView_ = true;
    auto *autoRowHeightCheck = new QCheckBox("Auto Row Height", page);
    autoRowHeightCheck->setToolTip("Resize rows to fit multi-line indicator values.");
    autoRowHeightCheck->setChecked(true);
    positionsAutoRowHeightCheck_ = autoRowHeightCheck;
    auto *autoColumnWidthCheck = new QCheckBox("Auto Column Width", page);
    autoColumnWidthCheck->setToolTip("Resize columns to fit full indicator text.");
    autoColumnWidthCheck->setChecked(true);
    positionsAutoColumnWidthCheck_ = autoColumnWidthCheck;

    ctrlLayout->addWidget(refreshPosBtn);
    ctrlLayout->addWidget(closeAllBtn);
    ctrlLayout->addWidget(positionsViewLabel);
    ctrlLayout->addWidget(positionsViewCombo);
    ctrlLayout->addWidget(autoRowHeightCheck);
    ctrlLayout->addWidget(autoColumnWidthCheck);
    ctrlLayout->addStretch();
    layout->addLayout(ctrlLayout);

    auto *statusWidget = new QWidget(page);
    statusWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    auto *statusLayout = new QHBoxLayout(statusWidget);
    statusLayout->setContentsMargins(0, 0, 0, 0);
    statusLayout->setSpacing(12);

    auto *pnlActiveLabel = new QLabel("Total PNL Active Positions: --", statusWidget);
    auto *pnlClosedLabel = new QLabel("Total PNL Closed Positions: --", statusWidget);
    auto *totalBalanceLabel = new QLabel("Total Balance: --", statusWidget);
    auto *availableBalanceLabel = new QLabel("Available Balance: --", statusWidget);
    auto *botStatusLabel = new QLabel("Bot Status: OFF", statusWidget);
    auto *botTimeLabel = new QLabel("Bot Active Time: --", statusWidget);
    positionsPnlActiveLabel_ = pnlActiveLabel;
    positionsPnlClosedLabel_ = pnlClosedLabel;
    positionsTotalBalanceLabel_ = totalBalanceLabel;
    positionsAvailableBalanceLabel_ = availableBalanceLabel;
    positionsBotStatusLabel_ = botStatusLabel;
    positionsBotTimeLabel_ = botTimeLabel;

    for (QLabel *lbl : {pnlActiveLabel, pnlClosedLabel, totalBalanceLabel, availableBalanceLabel}) {
        lbl->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
        lbl->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        statusLayout->addWidget(lbl);
    }
    statusLayout->addStretch();
    for (QLabel *lbl : {botStatusLabel, botTimeLabel}) {
        lbl->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
        lbl->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Preferred);
        statusLayout->addWidget(lbl);
    }
    layout->addWidget(statusWidget);

    auto *table = new QTableWidget(0, 18, page);
    positionsTable_ = table;
    table->setHorizontalHeaderLabels({
        "Symbol",
        "Size",
        "Last Price (USDT)",
        "Margin Ratio",
        "Liq Price (USDT)",
        "Margin (USDT)",
        "Quantity",
        "PNL (ROI%)",
        "Interval",
        "Indicator",
        "Triggered Indicator Value",
        "Current Indicator Value",
        "Side",
        "Open Time",
        "Close Time",
        "Stop-Loss",
        "Status",
        "Close",
    });
    auto *posHeader = table->horizontalHeader();
    posHeader->setStretchLastSection(true);
    posHeader->setSectionsMovable(true);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table->setSortingEnabled(true);
    table->setWordWrap(true);
    table->setTextElideMode(Qt::ElideNone);
    table->setCornerButtonEnabled(false);
    table->verticalHeader()->setVisible(true);
    table->verticalHeader()->setDefaultAlignment(Qt::AlignCenter);
    table->verticalHeader()->setMinimumWidth(32);
    table->verticalHeader()->setDefaultSectionSize(44);
    layout->addWidget(table, 1);

    auto *buttonsLayout = new QHBoxLayout();
    buttonsLayout->setContentsMargins(0, 0, 0, 0);
    buttonsLayout->setSpacing(8);
    auto *clearSelectedBtn = new QPushButton("Clear Selected", page);
    auto *clearAllBtn = new QPushButton("Clear All", page);
    buttonsLayout->addWidget(clearSelectedBtn);
    buttonsLayout->addWidget(clearAllBtn);
    buttonsLayout->addStretch();
    layout->addLayout(buttonsLayout);

    refreshPositionsTableSizing();

    connect(refreshPosBtn, &QPushButton::clicked, this, [=]() {
        const bool futuresMode = dashboardAccountTypeCombo_
            ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
            : true;
        if (!futuresMode) {
            updateStatusMessage("Positions refresh currently supports Futures account only.");
            return;
        }

        const QString mode = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
        if (TradingBotWindowSupport::isPaperTradingModeLabel(mode)) {
            const double paperBalance = currentDashboardPaperBalanceUsdt();
            positionsLastTotalBalanceUsdt_ = paperBalance;
            positionsLastAvailableBalanceUsdt_ = paperBalance;
            updateStatusMessage(QStringLiteral("Positions refresh synced from local paper positions."));
            applyPositionsViewMode();
            return;
        }

        const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
        const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
        if (apiKey.isEmpty() || apiSecret.isEmpty()) {
            updateStatusMessage("Positions refresh skipped: missing API credentials.");
            return;
        }

        const bool isTestnet = dashboardModeCombo_
            ? TradingBotWindowSupport::isTestnetModeLabel(dashboardModeCombo_->currentText())
            : false;
        const QString connectorText = dashboardConnectorCombo_
            ? dashboardConnectorCombo_->currentText().trimmed()
            : TradingBotWindowSupport::connectorLabelForKey(
                  TradingBotWindowSupport::recommendedConnectorKey(true));
        const TradingBotWindowSupport::ConnectorRuntimeConfig connectorCfg =
            TradingBotWindowSupport::resolveConnectorConfig(connectorText, true);
        if (!connectorCfg.ok()) {
            updateStatusMessage(QString("Positions refresh connector error: %1").arg(connectorCfg.error));
            return;
        }

        const auto livePositions = BinanceRestClient::fetchOpenFuturesPositions(
            apiKey,
            apiSecret,
            isTestnet,
            10000,
            connectorCfg.baseUrl);
        if (!livePositions.ok) {
            updateStatusMessage(QString("Positions refresh failed: %1").arg(livePositions.error));
            return;
        }
        positionsLiveActivePnlContextKey_ = QStringLiteral("%1|%2|%3")
                                                .arg(apiKey.trimmed(),
                                                     dashboardAccountTypeCombo_
                                                         ? dashboardAccountTypeCombo_->currentText().trimmed().toLower()
                                                         : QStringLiteral("futures"),
                                                     dashboardModeCombo_
                                                         ? dashboardModeCombo_->currentText().trimmed().toLower()
                                                         : QStringLiteral("live"));
        positionsLiveActivePnlUsdt_ = sumSnapshotActivePnl(livePositions);
        positionsLiveActivePnlUpdatedMs_ = QDateTime::currentMSecsSinceEpoch();
        positionsLiveActivePnlValid_ = true;
        const auto balance = BinanceRestClient::fetchUsdtBalance(
            apiKey,
            apiSecret,
            true,
            isTestnet,
            10000,
            connectorCfg.baseUrl);
        if (balance.ok) {
            const double totalBalance = std::max(
                0.0,
                (balance.totalUsdtBalance > 0.0) ? balance.totalUsdtBalance : balance.usdtBalance);
            const double availableBalance = std::max(
                0.0,
                (balance.availableUsdtBalance > 0.0) ? balance.availableUsdtBalance : totalBalance);
            positionsLastTotalBalanceUsdt_ = totalBalance;
            positionsLastAvailableBalanceUsdt_ = availableBalance;
        }

        QSet<QString> liveSymbols;
        for (const auto &pos : livePositions.positions) {
            const QString sym = pos.symbol.trimmed().toUpper();
            if (!sym.isEmpty()) {
                liveSymbols.insert(sym);
            }
        }

        auto setOrCreateCell = [table](int row, int col, const QString &text) {
            QTableWidgetItem *item = table->item(row, col);
            if (!item) {
                item = new QTableWidgetItem(text);
                table->setItem(row, col, item);
            } else {
                item->setText(text);
            }
            item->setData(Qt::UserRole, text);
        };

        int closedCount = 0;
        QSet<QString> staleSymbols;
        const QString nowText = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
        for (int row = 0; row < table->rowCount(); ++row) {
            const QString status = table->item(row, 16) ? table->item(row, 16)->text().trimmed().toUpper() : QString();
            if (status != QStringLiteral("OPEN")) {
                continue;
            }
            const QString symbol = table->item(row, 0) ? table->item(row, 0)->text().trimmed().toUpper() : QString();
            if (symbol.isEmpty() || liveSymbols.contains(symbol)) {
                continue;
            }
            staleSymbols.insert(symbol);
            setOrCreateCell(row, 16, QStringLiteral("CLOSED"));
            const QString existingClose = table->item(row, 14) ? table->item(row, 14)->text().trimmed() : QString();
            if (existingClose.isEmpty() || existingClose == QStringLiteral("-")) {
                setOrCreateCell(row, 14, nowText);
            }
            ++closedCount;
        }

        if (!staleSymbols.isEmpty()) {
            QList<QString> runtimeKeys = dashboardRuntimeOpenPositions_.keys();
            for (const QString &runtimeKey : runtimeKeys) {
                const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
                if (staleSymbols.contains(symbol)) {
                    dashboardRuntimeOpenPositions_.remove(runtimeKey);
                }
            }
        }

        updateStatusMessage(
            QString("Positions synced from Binance: %1 live symbol(s), %2 stale local row(s) closed.")
                .arg(liveSymbols.size())
                .arg(closedCount));
        applyPositionsViewMode();
    });
    connect(closeAllBtn, &QPushButton::clicked, this, [=]() {
        const int rowCount = table->rowCount();
        table->setRowCount(0);
        dashboardRuntimeOpenPositions_.clear();
        updateStatusMessage(QString("Market close-all simulated for %1 row(s).").arg(rowCount));
        applyPositionsViewMode();
    });
    connect(positionsViewCombo, &QComboBox::currentTextChanged, this, [=](const QString &viewText) {
        updateStatusMessage(QString("Positions view changed to %1.").arg(viewText));
        applyPositionsViewMode();
    });
    connect(autoRowHeightCheck, &QCheckBox::toggled, this, [=](bool enabled) {
        Q_UNUSED(enabled);
        refreshPositionsTableSizing();
    });
    connect(autoColumnWidthCheck, &QCheckBox::toggled, this, [=](bool enabled) {
        Q_UNUSED(enabled);
        refreshPositionsTableSizing();
    });
    connect(clearSelectedBtn, &QPushButton::clicked, this, [=]() {
        QSet<int> selectedRows;
        const auto selected = table->selectedItems();
        for (auto *item : selected) {
            if (item) {
                selectedRows.insert(item->row());
            }
        }
        QSet<QString> clearedPrefixes;
        for (int row : selectedRows) {
            const auto rawText = [table](int r, int c) -> QString {
                QTableWidgetItem *item = table->item(r, c);
                if (!item) {
                    return {};
                }
                const QVariant raw = item->data(Qt::UserRole);
                return raw.isValid() ? raw.toString() : item->text();
            };
            const QString symbol = rawText(row, 0).trimmed().toUpper();
            const QString interval = rawText(row, 8).trimmed().toLower();
            if (!symbol.isEmpty() && !interval.isEmpty()) {
                clearedPrefixes.insert(QStringLiteral("%1|%2|").arg(symbol, interval));
            }
        }
        if (!clearedPrefixes.isEmpty()) {
            const QList<QString> keys = dashboardRuntimeOpenPositions_.keys();
            for (const QString &runtimeKey : keys) {
                for (const QString &prefix : clearedPrefixes) {
                    if (runtimeKey.startsWith(prefix, Qt::CaseInsensitive)) {
                        dashboardRuntimeOpenPositions_.remove(runtimeKey);
                        break;
                    }
                }
            }
        }
        QList<int> rows = selectedRows.values();
        std::sort(rows.begin(), rows.end(), std::greater<int>());
        for (int rowIdx : rows) {
            table->removeRow(rowIdx);
        }
        updateStatusMessage(QString("Positions cleared: %1 selected row(s).").arg(rows.size()));
        applyPositionsViewMode();
    });
    connect(clearAllBtn, &QPushButton::clicked, this, [=]() {
        const int rowCount = table->rowCount();
        table->setRowCount(0);
        dashboardRuntimeOpenPositions_.clear();
        updateStatusMessage(QString("Positions cleared: %1 total row(s).").arg(rowCount));
        applyPositionsViewMode();
    });

    applyPositionsViewMode();

    return page;
}

void TradingBotWindow::refreshPositionsTableSizing(bool resizeColumns, bool resizeRows) {
    if (!positionsTable_) {
        return;
    }

    const bool autoRows = positionsAutoRowHeightCheck_ && positionsAutoRowHeightCheck_->isChecked();
    const bool autoColumns = positionsAutoColumnWidthCheck_ && positionsAutoColumnWidthCheck_->isChecked();

    if (autoRows) {
        if (resizeRows) {
            positionsTable_->verticalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
            positionsTable_->resizeRowsToContents();
        }
        positionsTable_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    } else {
        positionsTable_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
        positionsTable_->verticalHeader()->setDefaultSectionSize(44);
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            positionsTable_->setRowHeight(row, 44);
        }
    }

    QHeaderView *header = positionsTable_->horizontalHeader();
    if (autoColumns) {
        header->setStretchLastSection(false);
        if (resizeColumns) {
            for (int i = 0; i < header->count(); ++i) {
                header->setSectionResizeMode(i, QHeaderView::ResizeToContents);
            }
            positionsTable_->resizeColumnsToContents();
        }
        for (int i = 0; i < header->count(); ++i) {
            header->setSectionResizeMode(i, QHeaderView::Interactive);
        }
        header->setStretchLastSection(true);
    } else {
        header->setStretchLastSection(true);
        for (int i = 0; i < header->count(); ++i) {
            header->setSectionResizeMode(i, QHeaderView::Interactive);
        }
    }
}

void TradingBotWindow::refreshPositionsSummaryLabels() {
    double activePnl = 0.0;
    double closedPnl = 0.0;

    const bool futuresMode = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    const QString modeText = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
    const bool paperTrading = TradingBotWindowSupport::isPaperTradingModeLabel(modeText);
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString liveActivePnlContextKey = QStringLiteral("%1|%2|%3")
                                                .arg(apiKey,
                                                     dashboardAccountTypeCombo_
                                                         ? dashboardAccountTypeCombo_->currentText().trimmed().toLower()
                                                         : QStringLiteral("futures"),
                                                     modeText.trimmed().toLower());

    if (positionsTable_) {
        const auto rawCellText = [](const QTableWidgetItem *item) -> QString {
            if (!item) {
                return {};
            }
            const QVariant raw = item->data(Qt::UserRole);
            return raw.isValid() ? raw.toString() : item->text();
        };
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            const QString pnlText = rawCellText(positionsTable_->item(row, 7));
            const QString status = rawCellText(positionsTable_->item(row, 16)).trimmed().toUpper();
            const QString quantityText = rawCellText(positionsTable_->item(row, 6));
            bool ok = false;
            const double pnlValue = TradingBotWindowSupport::firstNumberInText(pnlText, &ok);
            if (!ok || !qIsFinite(pnlValue)) {
                continue;
            }
            bool qtyOk = false;
            double quantityValue = TradingBotWindowSupport::tableCellRawNumeric(
                positionsTable_->item(row, 6),
                std::numeric_limits<double>::quiet_NaN());
            if (!qIsFinite(quantityValue)) {
                quantityValue = TradingBotWindowSupport::firstNumberInText(quantityText, &qtyOk);
            } else {
                qtyOk = true;
            }
            if (status == QStringLiteral("OPEN")) {
                if (!qtyOk || !qIsFinite(quantityValue) || std::fabs(quantityValue) <= 1e-10) {
                    continue;
                }
                activePnl += pnlValue;
            } else if (status == QStringLiteral("CLOSED")) {
                closedPnl += pnlValue;
            }
        }
    }
    const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
    const bool liveActivePnlFresh = positionsLiveActivePnlValid_
        && positionsLiveActivePnlContextKey_ == liveActivePnlContextKey
        && (nowMs - positionsLiveActivePnlUpdatedMs_) <= 15000;
    if (futuresMode && !paperTrading && !apiKey.isEmpty() && liveActivePnlFresh) {
        activePnl = positionsLiveActivePnlUsdt_;
    }

    const QString activePnlText = QStringLiteral("Total PNL Active Positions: %1 USDT")
                                      .arg(QString::number(activePnl, 'f', 2));
    const QString closedPnlText = QStringLiteral("Total PNL Closed Positions: %1 USDT")
                                      .arg(QString::number(closedPnl, 'f', 2));
    const QString activePnlValueText = QStringLiteral("%1 USDT")
                                           .arg(QString::number(activePnl, 'f', 2));
    const QString closedPnlValueText = QStringLiteral("%1 USDT")
                                           .arg(QString::number(closedPnl, 'f', 2));
    if (chartPnlActiveLabel_) {
        chartPnlActiveLabel_->setText(activePnlText);
    }
    if (chartPnlClosedLabel_) {
        chartPnlClosedLabel_->setText(closedPnlText);
    }
    if (positionsPnlActiveLabel_) {
        positionsPnlActiveLabel_->setText(activePnlText);
    }
    if (positionsPnlClosedLabel_) {
        positionsPnlClosedLabel_->setText(closedPnlText);
    }
    if (backtestPnlActiveLabel_) {
        backtestPnlActiveLabel_->setText(activePnlText);
    }
    if (backtestPnlClosedLabel_) {
        backtestPnlClosedLabel_->setText(closedPnlText);
    }
    if (dashboardPnlActiveLabel_) {
        dashboardPnlActiveLabel_->setText(activePnlValueText);
    }
    if (dashboardPnlClosedLabel_) {
        dashboardPnlClosedLabel_->setText(closedPnlValueText);
    }
    if (codePnlActiveLabel_) {
        codePnlActiveLabel_->setText(activePnlText);
    }
    if (codePnlClosedLabel_) {
        codePnlClosedLabel_->setText(closedPnlText);
    }

    if (positionsTotalBalanceLabel_) {
        if (qIsFinite(positionsLastTotalBalanceUsdt_) && positionsLastTotalBalanceUsdt_ >= 0.0) {
            positionsTotalBalanceLabel_->setText(
                QStringLiteral("Total Balance: %1 USDT")
                    .arg(QString::number(positionsLastTotalBalanceUsdt_, 'f', 3)));
        } else {
            positionsTotalBalanceLabel_->setText(QStringLiteral("Total Balance: --"));
        }
    }
    if (positionsAvailableBalanceLabel_) {
        if (qIsFinite(positionsLastAvailableBalanceUsdt_) && positionsLastAvailableBalanceUsdt_ >= 0.0) {
            positionsAvailableBalanceLabel_->setText(
                QStringLiteral("Available Balance: %1 USDT")
                    .arg(QString::number(positionsLastAvailableBalanceUsdt_, 'f', 3)));
        } else {
            positionsAvailableBalanceLabel_->setText(QStringLiteral("Available Balance: --"));
        }
    }

    QString statusText = botStatusLabel_ ? botStatusLabel_->text().trimmed() : QStringLiteral("Bot Status: OFF");
    if (!statusText.startsWith(QStringLiteral("Bot Status:"), Qt::CaseInsensitive)) {
        statusText = QStringLiteral("Bot Status: %1").arg(statusText);
    }
    QString statusValue = statusText.section(':', 1).trimmed();
    if (statusValue.isEmpty()) {
        statusValue = QStringLiteral("OFF");
    }
    const bool isOn = statusValue.contains(QStringLiteral("ON"), Qt::CaseInsensitive);
    const QString statusStyle = isOn
        ? QStringLiteral("color: #16a34a; font-weight: 700;")
        : QStringLiteral("color: #ef4444; font-weight: 700;");
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
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText(statusValue);
        dashboardBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (codeBotStatusLabel_) {
        codeBotStatusLabel_->setText(statusText);
        codeBotStatusLabel_->setStyleSheet(statusStyle);
    }

    QString activeTimeText = botTimeLabel_ ? botTimeLabel_->text().trimmed() : QStringLiteral("Bot Active Time: --");
    if (!activeTimeText.startsWith(QStringLiteral("Bot Active Time:"), Qt::CaseInsensitive)) {
        activeTimeText = QStringLiteral("Bot Active Time: %1").arg(activeTimeText);
    }
    const QString activeTimeValue = activeTimeText.section(':', 1).trimmed().isEmpty()
        ? QStringLiteral("--")
        : activeTimeText.section(':', 1).trimmed();
    if (botTimeLabel_) {
        botTimeLabel_->setText(activeTimeText);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(activeTimeText);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(activeTimeText);
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText(activeTimeValue);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(activeTimeText);
    }
}

void TradingBotWindow::applyPositionsViewMode(bool resizeColumns, bool resizeRows) {
    if (!positionsTable_) {
        return;
    }
    ScopedTableUpdatesPause updatesPause(positionsTable_);

    const bool cumulativeMode = !positionsViewCombo_
        || positionsViewCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("cumulative"));
    const bool viewModeChanged = positionsCumulativeView_ != cumulativeMode;
    positionsCumulativeView_ = cumulativeMode;

    const bool sortingWasEnabled = positionsTable_->isSortingEnabled();
    positionsTable_->setSortingEnabled(false);

    auto ensureItem = [this](int row, int col) -> QTableWidgetItem * {
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            item = new QTableWidgetItem();
            positionsTable_->setItem(row, col, item);
        }
        return item;
    };
    auto restoreRawText = [](QTableWidgetItem *item) {
        if (!item) {
            return;
        }
        const QVariant raw = item->data(Qt::UserRole);
        if (!raw.isValid()) {
            item->setData(Qt::UserRole, item->text());
            return;
        }
        item->setText(raw.toString());
        const QVariant rawNumeric = item->data(kTableCellRawNumericRole);
        item->setData(kTableCellNumericRole, rawNumeric);
        const QVariant rawRoiBasis = item->data(kTableCellRawRoiBasisRole);
        if (rawRoiBasis.isValid()) {
            item->setData(Qt::UserRole + 1, rawRoiBasis);
        }
    };
    auto rawText = [](QTableWidgetItem *item) -> QString {
        if (!item) {
            return {};
        }
        const QVariant raw = item->data(Qt::UserRole);
        if (raw.isValid()) {
            return raw.toString();
        }
        return item->text();
    };
    auto parseNumeric = [](const QString &text) -> double {
        bool ok = false;
        const double value = TradingBotWindowSupport::firstNumberInText(text, &ok);
        return (ok && qIsFinite(value)) ? value : 0.0;
    };
    auto numericValue = [&rawText, &parseNumeric](QTableWidgetItem *item) -> double {
        if (!item) {
            return 0.0;
        }
        const double storedValue = TradingBotWindowSupport::tableCellRawNumeric(item, std::numeric_limits<double>::quiet_NaN());
        if (qIsFinite(storedValue)) {
            return storedValue;
        }
        return parseNumeric(rawText(item));
    };
    auto rowSequenceFor = [this, &ensureItem](int row) -> qint64 {
        QTableWidgetItem *item = ensureItem(row, 0);
        bool ok = false;
        const qint64 existing = item->data(kPositionsRowSequenceRole).toLongLong(&ok);
        if (ok && existing > 0) {
            return existing;
        }
        const qint64 fallback = static_cast<qint64>(row) + 1;
        item->setData(kPositionsRowSequenceRole, fallback);
        positionsRowSequenceCounter_ = std::max(positionsRowSequenceCounter_, fallback + 1);
        return fallback;
    };
    auto setDisplayText = [&ensureItem](int row, int col, const QString &text) -> QTableWidgetItem * {
        QTableWidgetItem *item = ensureItem(row, col);
        if (!item->data(Qt::UserRole).isValid()) {
            item->setData(Qt::UserRole, item->text());
        }
        item->setText(text);
        return item;
    };

    if (viewModeChanged || !cumulativeMode) {
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            positionsTable_->setRowHidden(row, false);
            for (int col = 0; col < positionsTable_->columnCount(); ++col) {
                restoreRawText(positionsTable_->item(row, col));
            }
        }
    }

    if (!cumulativeMode) {
        positionsTable_->setSortingEnabled(sortingWasEnabled);
        refreshPositionsTableSizing(resizeColumns, resizeRows);
        refreshPositionsSummaryLabels();
        return;
    }

    struct AggregateBucket {
        int primaryRow = -1;
        qint64 primarySequence = std::numeric_limits<qint64>::max();
        QList<int> rows;
        QStringList intervals;
        QStringList indicators;
        QStringList sides;
        QStringList stopLosses;
        QStringList statuses;
        QStringList triggeredValues;
        QStringList currentValues;
        QSet<QString> intervalSet;
        QSet<QString> indicatorSet;
        QSet<QString> sideSet;
        QSet<QString> stopLossSet;
        QSet<QString> statusSet;
        QSet<QString> triggeredSet;
        QSet<QString> currentSet;
        double sizeUsdt = 0.0;
        double lastPrice = 0.0;
        double marginUsdt = 0.0;
        double roiBasisUsdt = 0.0;
        double quantity = 0.0;
        double pnlUsdt = 0.0;
        double marginRatio = 0.0;
        double liqPrice = 0.0;
        int openCount = 0;
        int closedCount = 0;
        QString openTime;
        QString closeTime;
        QStringList connectors;
        QSet<QString> connectorSet;
    };

    QMap<QString, AggregateBucket> groups;
    const auto appendUnique = [](QStringList &ordered, QSet<QString> &seen, const QString &rawValue) {
        const QString value = rawValue.trimmed();
        if (value.isEmpty() || value == QStringLiteral("-")) {
            return;
        }
        const QString key = value.toLower();
        if (seen.contains(key)) {
            return;
        }
        seen.insert(key);
        ordered.append(value);
    };
    const auto appendUniqueLines = [&appendUnique](QStringList &ordered, QSet<QString> &seen, const QString &multiLine) {
        const QStringList parts = multiLine.split('\n', Qt::SkipEmptyParts);
        if (parts.isEmpty()) {
            appendUnique(ordered, seen, multiLine);
            return;
        }
        for (const QString &part : parts) {
            appendUnique(ordered, seen, part);
        }
    };
    const auto connectorBase = [](const QString &rawConnector) -> QString {
        QString text = rawConnector.trimmed();
        const int hashPos = text.indexOf('#');
        if (hashPos > 0) {
            text = text.left(hashPos).trimmed();
        }
        const int pipePos = text.indexOf('|');
        if (pipePos > 0) {
            text = text.left(pipePos).trimmed();
        }
        return text;
    };

    for (int row = 0; row < positionsTable_->rowCount(); ++row) {
        const QString symbol = rawText(positionsTable_->item(row, 0)).trimmed().toUpper();
        const QString side = rawText(positionsTable_->item(row, 12)).trimmed().toUpper();
        const QString status = rawText(positionsTable_->item(row, 16)).trimmed().toUpper();
        if (symbol.isEmpty()) {
            continue;
        }

        const QString groupKey = symbol;
        AggregateBucket &bucket = groups[groupKey];
        const qint64 rowSequence = rowSequenceFor(row);
        if (bucket.primaryRow < 0 || rowSequence < bucket.primarySequence) {
            bucket.primaryRow = row;
            bucket.primarySequence = rowSequence;
        }
        bucket.rows.append(row);
        appendUnique(bucket.intervals, bucket.intervalSet, rawText(positionsTable_->item(row, 8)));
        appendUnique(bucket.indicators, bucket.indicatorSet, rawText(positionsTable_->item(row, 9)));
        appendUnique(bucket.sides, bucket.sideSet, side);
        appendUnique(bucket.stopLosses, bucket.stopLossSet, rawText(positionsTable_->item(row, 15)));
        appendUnique(bucket.statuses, bucket.statusSet, status);
        appendUniqueLines(bucket.triggeredValues, bucket.triggeredSet, rawText(positionsTable_->item(row, 10)));
        appendUniqueLines(bucket.currentValues, bucket.currentSet, rawText(positionsTable_->item(row, 11)));
        appendUnique(bucket.connectors, bucket.connectorSet, connectorBase(rawText(positionsTable_->item(row, 17))));
        bucket.sizeUsdt += numericValue(positionsTable_->item(row, 1));
        const double lastPrice = numericValue(positionsTable_->item(row, 2));
        if (qIsFinite(lastPrice) && lastPrice > 0.0) {
            bucket.lastPrice = lastPrice;
        }
        bucket.marginUsdt += numericValue(positionsTable_->item(row, 5));
        const double roiBasisValue = tableCellRawRoiBasis(positionsTable_->item(row, 7), numericValue(positionsTable_->item(row, 5)));
        if (qIsFinite(roiBasisValue) && roiBasisValue > 0.0) {
            bucket.roiBasisUsdt += roiBasisValue;
        }
        bucket.quantity += numericValue(positionsTable_->item(row, 6));
        bucket.pnlUsdt += numericValue(positionsTable_->item(row, 7));
        bucket.marginRatio = std::max(bucket.marginRatio, numericValue(positionsTable_->item(row, 3)));
        bucket.liqPrice = std::max(bucket.liqPrice, numericValue(positionsTable_->item(row, 4)));
        if (status == QStringLiteral("OPEN")) {
            ++bucket.openCount;
        } else if (status == QStringLiteral("CLOSED")) {
            ++bucket.closedCount;
        }

        const QString openTime = rawText(positionsTable_->item(row, 13)).trimmed();
        if (!openTime.isEmpty() && openTime != QStringLiteral("-")) {
            if (bucket.openTime.isEmpty() || openTime < bucket.openTime) {
                bucket.openTime = openTime;
            }
        }
        const QString closeTime = rawText(positionsTable_->item(row, 14)).trimmed();
        if (!closeTime.isEmpty() && closeTime != QStringLiteral("-")) {
            if (bucket.closeTime.isEmpty() || closeTime > bucket.closeTime) {
                bucket.closeTime = closeTime;
            }
        }
    }

    QSet<int> secondaryRows;
    for (auto it = groups.cbegin(); it != groups.cend(); ++it) {
        const AggregateBucket &bucket = it.value();
        if (bucket.primaryRow < 0 || bucket.rows.isEmpty()) {
            continue;
        }
        for (int bucketRow : bucket.rows) {
            if (bucketRow != bucket.primaryRow) {
                secondaryRows.insert(bucketRow);
            }
        }

        const int row = bucket.primaryRow;
        const int tradeCount = bucket.rows.size();
        const double pnlPct = bucket.roiBasisUsdt > 1e-9 ? (bucket.pnlUsdt / bucket.roiBasisUsdt) * 100.0 : 0.0;
        const QString intervalText = bucket.intervals.isEmpty() ? QStringLiteral("-") : bucket.intervals.join(QStringLiteral(", "));
        const QString indicatorText = bucket.indicators.isEmpty() ? QStringLiteral("-") : bucket.indicators.join(QStringLiteral(", "));
        const QString sideText = bucket.sides.isEmpty() ? QStringLiteral("-") : bucket.sides.join(QStringLiteral(", "));
        const QString stopLossText = bucket.stopLosses.isEmpty() ? QStringLiteral("-") : bucket.stopLosses.join(QStringLiteral(", "));
        const QString triggeredText = bucket.triggeredValues.isEmpty() ? QStringLiteral("-") : bucket.triggeredValues.join(QStringLiteral("\n"));
        const QString currentText = bucket.currentValues.isEmpty() ? QStringLiteral("-") : bucket.currentValues.join(QStringLiteral("\n"));
        const QString marginRatioText = bucket.marginRatio > 0.0
            ? QStringLiteral("%1%").arg(QString::number(bucket.marginRatio, 'f', 2))
            : QStringLiteral("-");
        const QString liqPriceText = bucket.liqPrice > 0.0
            ? QString::number(bucket.liqPrice, 'f', 6)
            : QStringLiteral("-");
        const QString lastPriceText = bucket.lastPrice > 0.0
            ? QString::number(bucket.lastPrice, 'f', 6)
            : QStringLiteral("-");
        QString statusText;
        if (bucket.openCount > 0 && bucket.closedCount > 0) {
            statusText = QStringLiteral("OPEN + CLOSED");
        } else if (bucket.openCount > 0) {
            statusText = QStringLiteral("OPEN");
        } else if (bucket.closedCount > 0) {
            statusText = QStringLiteral("CLOSED");
        } else {
            statusText = bucket.statuses.isEmpty() ? QStringLiteral("-") : bucket.statuses.join(QStringLiteral(", "));
        }
        const QString symbol = rawText(positionsTable_->item(row, 0)).trimmed().toUpper();

        setDisplayText(row, 0, symbol);
        setDisplayText(row, 1, formatPositionSizeText(bucket.sizeUsdt, bucket.quantity, symbol));
        setDisplayText(row, 2, lastPriceText);
        setDisplayText(row, 3, marginRatioText);
        setDisplayText(row, 4, liqPriceText);
        setDisplayText(row, 5, QString::number(bucket.marginUsdt, 'f', 2));
        setDisplayText(row, 6, formatQuantityWithSymbol(bucket.quantity, symbol));
        ensureItem(row, 1)->setData(kTableCellNumericRole, bucket.sizeUsdt);
        ensureItem(row, 2)->setData(kTableCellNumericRole, bucket.lastPrice);
        ensureItem(row, 3)->setData(kTableCellNumericRole, bucket.marginRatio);
        ensureItem(row, 4)->setData(kTableCellNumericRole, bucket.liqPrice);
        ensureItem(row, 5)->setData(kTableCellNumericRole, bucket.marginUsdt);
        ensureItem(row, 6)->setData(kTableCellNumericRole, bucket.quantity);
        QTableWidgetItem *pnlItem = setDisplayText(row, 7, QStringLiteral("%1 (%2%)")
                                                        .arg(QString::number(bucket.pnlUsdt, 'f', 2),
                                                             QString::number(pnlPct, 'f', 2)));
        pnlItem->setData(Qt::UserRole + 1, bucket.roiBasisUsdt);
        pnlItem->setData(kTableCellNumericRole, bucket.pnlUsdt);
        setDisplayText(row, 8, intervalText);
        setDisplayText(row, 9, indicatorText);
        setDisplayText(row, 10, triggeredText);
        setDisplayText(row, 11, currentText);
        setDisplayText(row, 12, sideText);
        setDisplayText(row, 13, bucket.openTime.isEmpty() ? QStringLiteral("-") : bucket.openTime);
        setDisplayText(
            row,
            14,
            bucket.openCount > 0
                ? QStringLiteral("-")
                : (bucket.closeTime.isEmpty() ? QStringLiteral("-") : bucket.closeTime));
        setDisplayText(row, 15, stopLossText);
        setDisplayText(row, 16, statusText);
        const QString connectorText = bucket.connectors.isEmpty()
            ? QStringLiteral("-")
            : bucket.connectors.join(QStringLiteral(", "));
        setDisplayText(row, 17, QStringLiteral("%1 | %2 trade(s)").arg(connectorText).arg(tradeCount));

        for (int i = 0; i < bucket.rows.size(); ++i) {
            const int bucketRow = bucket.rows.at(i);
            if (bucketRow == row) {
                continue;
            }
            for (int col = 0; col < positionsTable_->columnCount(); ++col) {
                QTableWidgetItem *sourceItem = positionsTable_->item(row, col);
                QTableWidgetItem *targetItem = ensureItem(bucketRow, col);
                if (!targetItem->data(Qt::UserRole).isValid()) {
                    targetItem->setData(Qt::UserRole, targetItem->text());
                }
                targetItem->setText(sourceItem ? sourceItem->text() : QString());
                targetItem->setData(
                    kTableCellNumericRole,
                    sourceItem ? sourceItem->data(kTableCellNumericRole) : QVariant());
                if (col == 7) {
                    targetItem->setData(
                        Qt::UserRole + 1,
                        sourceItem ? sourceItem->data(Qt::UserRole + 1) : QVariant());
                }
            }
        }
    }

    for (int row = 0; row < positionsTable_->rowCount(); ++row) {
        positionsTable_->setRowHidden(row, secondaryRows.contains(row));
    }

    positionsTable_->setSortingEnabled(sortingWasEnabled);
    refreshPositionsTableSizing(resizeColumns, resizeRows);
    refreshPositionsSummaryLabels();
}
