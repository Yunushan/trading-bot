#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"

#include <QComboBox>
#include <QCoreApplication>
#include <QDoubleSpinBox>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QPushButton>
#include <QtGlobal>

#include <algorithm>
#include <limits>

void TradingBotWindow::refreshDashboardBalance() {
    if (!dashboardRefreshBtn_) {
        return;
    }
    dashboardRefreshBtn_->setEnabled(false);
    dashboardRefreshBtn_->setText("Refreshing...");
    auto resetButton = [this]() {
        if (dashboardRefreshBtn_) {
            dashboardRefreshBtn_->setEnabled(true);
            dashboardRefreshBtn_->setText("Refresh Balance");
        }
    };

    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const QString selectedExchange = TradingBotWindowSupport::selectedDashboardExchange(dashboardExchangeCombo_);
    if (!TradingBotWindowSupport::exchangeUsesBinanceApi(selectedExchange)) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("%1 balance API coming soon").arg(selectedExchange));
            dashboardBalanceLabel_->setStyleSheet("color: #f59e0b; font-weight: 700;");
        }
        resetButton();
        return;
    }

    const QString accountType = dashboardAccountTypeCombo_ ? dashboardAccountTypeCombo_->currentText() : "Futures";
    const QString mode = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : "Live";

    if (dashboardBalanceLabel_) {
        dashboardBalanceLabel_->setText("Refreshing...");
    }

    const QString accountNorm = accountType.trimmed().toLower();
    const bool isFutures = accountNorm.startsWith("fut");
    const bool paperTrading = TradingBotWindowSupport::isPaperTradingModeLabel(mode);
    const bool isTestnet = TradingBotWindowSupport::isTestnetModeLabel(mode);
    const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
    const TradingBotWindowSupport::ConnectorRuntimeConfig connectorCfg =
        TradingBotWindowSupport::resolveConnectorConfig(connectorText, isFutures);
    if (!connectorCfg.ok()) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("Connector error: %1").arg(connectorCfg.error));
            dashboardBalanceLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
        }
        resetButton();
        return;
    }
    if (!connectorCfg.warning.trimmed().isEmpty()) {
        updateStatusMessage(QString("Connector fallback: %1").arg(connectorCfg.warning));
    }

    if (paperTrading) {
        syncDashboardPaperBalanceUi();
        updateStatusMessage(QStringLiteral("Paper Local uses live market data with a configurable paper balance."));
        resetButton();
        return;
    }

    if (apiKey.isEmpty() || apiSecret.isEmpty()) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText("API credentials missing");
        }
        resetButton();
        return;
    }

    const auto result = BinanceRestClient::fetchUsdtBalance(
        apiKey,
        apiSecret,
        isFutures,
        isTestnet,
        10000,
        connectorCfg.baseUrl);
    if (!result.ok) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("Error: %1").arg(result.error));
            dashboardBalanceLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
        }
        resetButton();
        return;
    }

    if (dashboardBalanceLabel_) {
        const double totalValue = std::max(0.0, (result.totalUsdtBalance > 0.0) ? result.totalUsdtBalance : result.usdtBalance);
        const double availableValue = std::max(0.0, (result.availableUsdtBalance > 0.0) ? result.availableUsdtBalance : totalValue);
        positionsLastTotalBalanceUsdt_ = totalValue;
        positionsLastAvailableBalanceUsdt_ = availableValue;
        const QString totalText = QString::number(totalValue, 'f', 3);
        const QString availableText = QString::number(availableValue, 'f', 3);
        if (qAbs(totalValue - availableValue) > 1e-6) {
            dashboardBalanceLabel_->setText(QString("Total %1 USDT | Available %2 USDT").arg(totalText, availableText));
        } else {
            dashboardBalanceLabel_->setText(QString("%1 USDT").arg(totalText));
        }
        dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
    }
    refreshPositionsSummaryLabels();
    resetButton();
}

double TradingBotWindow::currentDashboardPaperBalanceUsdt() const {
    if (dashboardPaperBalanceSpin_) {
        const double value = dashboardPaperBalanceSpin_->value();
        if (qIsFinite(value) && value > 0.0) {
            return value;
        }
    }
    return 1000.0;
}

void TradingBotWindow::syncDashboardPaperBalanceUi() {
    const bool paperTrading = dashboardModeCombo_
        && TradingBotWindowSupport::isPaperTradingModeLabel(dashboardModeCombo_->currentText());
    if (dashboardPaperBalanceTitleLabel_) {
        dashboardPaperBalanceTitleLabel_->setVisible(paperTrading);
    }
    if (dashboardPaperBalanceSpin_) {
        dashboardPaperBalanceSpin_->setVisible(paperTrading);
        dashboardPaperBalanceSpin_->setEnabled(paperTrading && !dashboardRuntimeActive_);
    }

    if (!paperTrading) {
        positionsLastTotalBalanceUsdt_ = std::numeric_limits<double>::quiet_NaN();
        positionsLastAvailableBalanceUsdt_ = std::numeric_limits<double>::quiet_NaN();
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QStringLiteral("N/A"));
            dashboardBalanceLabel_->setStyleSheet("color: #fbbf24; font-weight: 700;");
        }
        refreshPositionsSummaryLabels();
        return;
    }

    const double paperBalance = currentDashboardPaperBalanceUsdt();
    positionsLastTotalBalanceUsdt_ = paperBalance;
    positionsLastAvailableBalanceUsdt_ = paperBalance;
    if (dashboardBalanceLabel_) {
        dashboardBalanceLabel_->setText(
            QStringLiteral("Paper balance: %1 USDT")
                .arg(QString::number(paperBalance, 'f', 3)));
        dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
    }
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::refreshDashboardSymbols() {
    if (!dashboardRefreshSymbolsBtn_) {
        return;
    }
    dashboardRefreshSymbolsBtn_->setEnabled(false);
    dashboardRefreshSymbolsBtn_->setText("Refreshing...");
    auto resetButton = [this]() {
        if (dashboardRefreshSymbolsBtn_) {
            dashboardRefreshSymbolsBtn_->setEnabled(true);
            dashboardRefreshSymbolsBtn_->setText("Refresh Symbols");
        }
    };

    if (!dashboardSymbolList_) {
        resetButton();
        return;
    }

    QSet<QString> previousSelections;
    if (dashboardSymbolList_) {
        for (auto *item : dashboardSymbolList_->selectedItems()) {
            previousSelections.insert(item->text());
        }
    }
    dashboardSymbolList_->clear();
    QCoreApplication::processEvents();

    auto applySymbols = [this, &previousSelections](const QStringList &symbols) {
        if (!dashboardSymbolList_) {
            return;
        }
        dashboardSymbolList_->clear();
        dashboardSymbolList_->addItems(symbols);

        bool anySelected = false;
        for (int i = 0; i < dashboardSymbolList_->count(); ++i) {
            auto *item = dashboardSymbolList_->item(i);
            if (previousSelections.contains(item->text())) {
                item->setSelected(true);
                anySelected = true;
            }
        }
        if (!anySelected && dashboardSymbolList_->count() > 0) {
            dashboardSymbolList_->item(0)->setSelected(true);
        }
    };

    const QString accountType = dashboardAccountTypeCombo_ ? dashboardAccountTypeCombo_->currentText() : "Futures";
    const QString mode = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : "Live";
    const QString accountNorm = accountType.trimmed().toLower();
    const bool isFutures = accountNorm.startsWith("fut");
    const bool isTestnet = TradingBotWindowSupport::isTestnetModeLabel(mode);
    const QString selectedExchange = TradingBotWindowSupport::selectedDashboardExchange(dashboardExchangeCombo_);

    if (!TradingBotWindowSupport::exchangeUsesBinanceApi(selectedExchange)) {
        const QStringList fallbackSymbols =
            TradingBotWindowSupport::placeholderSymbolsForExchange(selectedExchange, isFutures);
        applySymbols(fallbackSymbols);
        updateStatusMessage(
            QString("%1 API symbol sync is coming soon. Showing placeholder symbols.").arg(selectedExchange));
        resetButton();
        return;
    }

    const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
    const TradingBotWindowSupport::ConnectorRuntimeConfig connectorCfg =
        TradingBotWindowSupport::resolveConnectorConfig(connectorText, isFutures);
    if (!connectorCfg.ok()) {
        QMessageBox::warning(this, tr("Connector error"), connectorCfg.error);
        resetButton();
        return;
    }
    if (!connectorCfg.warning.trimmed().isEmpty()) {
        updateStatusMessage(QString("Connector fallback: %1").arg(connectorCfg.warning));
    }

    const auto result = BinanceRestClient::fetchUsdtSymbols(isFutures, isTestnet, 10000, true, 0, connectorCfg.baseUrl);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Refresh symbols failed"), result.error);
        resetButton();
        return;
    }

    applySymbols(result.symbols);

    resetButton();
}
