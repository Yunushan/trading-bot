#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"

#include <QComboBox>
#include <QCoreApplication>
#include <QDoubleSpinBox>
#include <QJsonArray>
#include <QJsonObject>
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
        const auto serviceResult = TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("GET"), QStringLiteral("account"), {}, 10000);
        if (dashboardBalanceLabel_) {
            if (!serviceResult.ok) {
                dashboardBalanceLabel_->setText(
                    QStringLiteral("%1 account snapshot unavailable: %2")
                        .arg(selectedExchange, serviceResult.error));
                dashboardBalanceLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
            } else {
                const QJsonObject payload = serviceResult.document.object();
                bool totalOk = false;
                bool availableOk = false;
                const double total = payload.value(QStringLiteral("total_balance")).toVariant().toDouble(&totalOk);
                const double available = payload.value(QStringLiteral("available_balance")).toVariant().toDouble(&availableOk);
                const QString currency = payload.value(QStringLiteral("balance_currency")).toString(QStringLiteral("USDT"));
                const QString source = payload.value(QStringLiteral("source")).toString(QStringLiteral("Python Service API"));
                if (totalOk && qIsFinite(total)) {
                    positionsLastTotalBalanceUsdt_ = std::max(0.0, total);
                }
                if (availableOk && qIsFinite(available)) {
                    positionsLastAvailableBalanceUsdt_ = std::max(0.0, available);
                }
                if (totalOk || availableOk) {
                    const double totalValue = totalOk && qIsFinite(total) ? std::max(0.0, total) : 0.0;
                    const double availableValue = availableOk && qIsFinite(available) ? std::max(0.0, available) : totalValue;
                    dashboardBalanceLabel_->setText(
                        QStringLiteral("%1 total %2 | available %3")
                            .arg(currency,
                                 QString::number(totalValue, 'f', 3),
                                 QString::number(availableValue, 'f', 3)));
                    dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
                    refreshPositionsSummaryLabels();
                } else {
                    dashboardBalanceLabel_->setText(
                        QStringLiteral("%1 account snapshot is not populated by %2.").arg(selectedExchange, source));
                    dashboardBalanceLabel_->setStyleSheet("color: #f59e0b; font-weight: 700;");
                }
                updateStatusMessage(
                    QStringLiteral("%1 account snapshot loaded through Python Service API (%2).").arg(selectedExchange, source));
            }
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
        const auto serviceResult = TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("GET"), QStringLiteral("config"), {}, 10000);
        if (!serviceResult.ok) {
            QMessageBox::warning(
                this,
                tr("Refresh symbols failed"),
                QStringLiteral("Python Service API config request failed: %1").arg(serviceResult.error));
            resetButton();
            return;
        }
        QJsonObject payload = serviceResult.document.object();
        if (payload.value(QStringLiteral("config")).isObject()) {
            payload = payload.value(QStringLiteral("config")).toObject();
        }
        QStringList configuredSymbols;
        for (const QJsonValue &value : payload.value(QStringLiteral("symbols")).toArray()) {
            const QString symbol = value.toString().trimmed().toUpper();
            if (!symbol.isEmpty() && !configuredSymbols.contains(symbol)) {
                configuredSymbols.push_back(symbol);
            }
        }
        if (configuredSymbols.isEmpty()) {
            QMessageBox::warning(
                this,
                tr("Refresh symbols failed"),
                QStringLiteral("Python Service API has no configured symbols for %1.").arg(selectedExchange));
            resetButton();
            return;
        }
        applySymbols(configuredSymbols);
        updateStatusMessage(
            QStringLiteral("%1 symbols loaded from the canonical Python Service API configuration.").arg(selectedExchange));
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
