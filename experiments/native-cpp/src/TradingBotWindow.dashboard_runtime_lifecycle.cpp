#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "BinanceWsClient.h"
#include "TradingBotWindow.dashboard_runtime_shared.h"

#include <QCheckBox>
#include <QComboBox>
#include <QCoreApplication>
#include <QDateTime>
#include <QDoubleSpinBox>
#include <QDir>
#include <QEventLoop>
#include <QFileInfo>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QMessageBox>
#include <QVector>
#include <QRegularExpression>
#include <QPushButton>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTextEdit>
#include <QTimer>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <limits>


using namespace TradingBotWindowDashboardRuntime;
using ConnectorRuntimeConfig = TradingBotWindowSupport::ConnectorRuntimeConfig;

void TradingBotWindow::startDashboardRuntime() {
    if (dashboardRuntimeStopping_) {
        appendDashboardAllLog("Start ignored: runtime stop/close sequence is still in progress.");
        return;
    }
    if (!dashboardOverridesTable_) {
        return;
    }
    if (dashboardOverridesTable_->rowCount() <= 0) {
        appendDashboardAllLog("Start blocked: no symbol/interval override rows found.");
        appendDashboardWaitingLog("No overrides queued. Add at least one pair first.");
        QMessageBox::information(this, tr("Start blocked"), tr("Add at least one Symbol / Interval override row first."));
        return;
    }

    if (dashboardStartBtn_) {
        dashboardStartBtn_->setEnabled(false);
    }
    if (dashboardStopBtn_) {
        dashboardStopBtn_->setEnabled(true);
    }

    handleRunBacktest();
    dashboardRuntimeActive_ = true;
    dashboardRuntimeStopping_ = false;
    setDashboardRuntimeControlsEnabled(false);
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("ON");
        dashboardBotStatusLabel_->setStyleSheet("color: #16a34a; font-weight: 700;");
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("0s");
    }
    refreshPositionsSummaryLabels();

    if (!dashboardRuntimeTimer_) {
        dashboardRuntimeTimer_ = new QTimer(this);
        connect(dashboardRuntimeTimer_, &QTimer::timeout, this, &TradingBotWindow::runDashboardRuntimeCycle);
    }
    const bool useWebSocketFeed = dashboardSignalFeedCombo_
        && normalizedSignalFeedKey(dashboardSignalFeedCombo_->currentText()) == QStringLiteral("websocket")
        && qtWebSocketsRuntimeAvailable();
    const bool futures = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    const QString defaultConnectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : TradingBotWindowSupport::connectorLabelForKey(TradingBotWindowSupport::recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig defaultConnectorCfg = TradingBotWindowSupport::resolveConnectorConfig(defaultConnectorText, futures);
    dashboardRuntimeTimer_->setInterval(dashboardRuntimePollIntervalMs(dashboardOverridesTable_, useWebSocketFeed));
    dashboardRuntimeLastEvalMs_.clear();
    dashboardRuntimeEntryRetryAfterMs_.clear();
    dashboardRuntimeOpenQtyCaps_.clear();
    dashboardRuntimeConnectorWarnings_.clear();
    dashboardRuntimeIntervalWarnings_.clear();
    clearRuntimeSignalSockets(dashboardRuntimeSignalSockets_);
    dashboardRuntimeSignalCandles_.clear();
    dashboardRuntimeSignalLastClosed_.clear();
    dashboardRuntimeSignalUpdateMs_.clear();
    const int staleOpenCount = dashboardRuntimeOpenPositions_.size();
    dashboardRuntimeOpenPositions_.clear();
    int restoredOpenCount = 0;
    if (positionsTable_) {
        auto rawCellText = [this](int row, int col) -> QString {
            if (!positionsTable_) {
                return {};
            }
            const QTableWidgetItem *item = positionsTable_->item(row, col);
            if (!item) {
                return {};
            }
            const QVariant raw = item->data(Qt::UserRole);
            return raw.isValid() ? raw.toString() : item->text();
        };
        const QRegularExpression connectorKeyRe(QStringLiteral("\\[([^\\]]+)\\]"));
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            const QString status = rawCellText(row, 16).trimmed().toUpper();
            if (status != QStringLiteral("OPEN")) {
                continue;
            }

            const QString symbol = rawCellText(row, 0).trimmed().toUpper();
            const QString interval = rawCellText(row, 8).trimmed();
            const QString side = rawCellText(row, 12).trimmed().toUpper();
            if (symbol.isEmpty() || interval.isEmpty()) {
                continue;
            }
            if (side != QStringLiteral("LONG") && side != QStringLiteral("SHORT")) {
                continue;
            }

            bool qtyOk = false;
            double quantity = TradingBotWindowSupport::tableCellRawNumeric(
                positionsTable_->item(row, 6),
                std::numeric_limits<double>::quiet_NaN());
            if (!qIsFinite(quantity)) {
                quantity = TradingBotWindowSupport::firstNumberInText(rawCellText(row, 6), &qtyOk);
            } else {
                qtyOk = true;
            }
            if (!qtyOk || !qIsFinite(quantity) || quantity <= 1e-10) {
                continue;
            }

            bool priceOk = false;
            double entryPrice = TradingBotWindowSupport::tableCellRawNumeric(
                positionsTable_->item(row, 2),
                std::numeric_limits<double>::quiet_NaN());
            if (!qIsFinite(entryPrice)) {
                entryPrice = TradingBotWindowSupport::firstNumberInText(rawCellText(row, 2), &priceOk);
            } else {
                priceOk = true;
            }
            if (!priceOk || !qIsFinite(entryPrice) || entryPrice <= 0.0) {
                entryPrice = 0.0;
            }

            double marginUsdt = TradingBotWindowSupport::tableCellRawNumeric(
                positionsTable_->item(row, 5),
                std::numeric_limits<double>::quiet_NaN());
            if (!qIsFinite(marginUsdt) || marginUsdt < 0.0) {
                bool marginOk = false;
                marginUsdt = TradingBotWindowSupport::firstNumberInText(rawCellText(row, 5), &marginOk);
                if (!marginOk || !qIsFinite(marginUsdt) || marginUsdt < 0.0) {
                    marginUsdt = 0.0;
                }
            }

            double sizeUsdt = TradingBotWindowSupport::tableCellRawNumeric(
                positionsTable_->item(row, 1),
                std::numeric_limits<double>::quiet_NaN());
            if (!qIsFinite(sizeUsdt) || sizeUsdt < 0.0) {
                bool sizeOk = false;
                sizeUsdt = TradingBotWindowSupport::firstNumberInText(rawCellText(row, 1), &sizeOk);
                if (!sizeOk || !qIsFinite(sizeUsdt) || sizeUsdt < 0.0) {
                    sizeUsdt = 0.0;
                }
            }

            double leverage = dashboardLeverageSpin_ ? static_cast<double>(dashboardLeverageSpin_->value()) : 1.0;
            if (marginUsdt > 1e-9 && sizeUsdt > 0.0) {
                leverage = std::max(1.0, sizeUsdt / marginUsdt);
            }

            QString connectorKey = defaultConnectorCfg.key.trimmed();
            const QRegularExpressionMatch connectorMatch = connectorKeyRe.match(rawCellText(row, 17));
            if (connectorMatch.hasMatch()) {
                const QString parsed = connectorMatch.captured(1).trimmed();
                if (!parsed.isEmpty()) {
                    connectorKey = parsed;
                }
            }
            ConnectorRuntimeConfig rowConnectorCfg = TradingBotWindowSupport::resolveConnectorConfig(
                TradingBotWindowSupport::connectorLabelForKey(connectorKey),
                futures);
            if (!rowConnectorCfg.ok()) {
                rowConnectorCfg = defaultConnectorCfg;
            }
            if (!rowConnectorCfg.ok()) {
                continue;
            }

            const QString connectorToken = QStringLiteral("%1|%2").arg(rowConnectorCfg.key, rowConnectorCfg.baseUrl);
            const QString runtimeKey = symbol.trimmed().toUpper()
                + QStringLiteral("|")
                + interval.trimmed().toLower()
                + QStringLiteral("|")
                + connectorToken.trimmed().toLower();
            if (dashboardRuntimeOpenPositions_.contains(runtimeKey)) {
                continue;
            }

            dashboardRuntimeOpenPositions_.insert(
                runtimeKey,
                RuntimePosition{
                    side,
                    interval,
                    rawCellText(row, 9).trimmed(),
                    rowConnectorCfg.key,
                    rowConnectorCfg.baseUrl,
                    entryPrice,
                    quantity,
                    leverage,
                    std::max(1e-9, marginUsdt),
                    std::max(0.0, marginUsdt),
                });
            ++restoredOpenCount;
        }
    }
    if (restoredOpenCount > 0) {
        appendDashboardPositionLog(
            QString("Restored %1 open position(s) from the Positions tab before start.")
                .arg(restoredOpenCount));
    } else if (staleOpenCount > 0) {
        appendDashboardPositionLog(QString("Reset %1 stale in-memory open position(s) before start.").arg(staleOpenCount));
    }
    dashboardWaitingActiveEntries_.clear();
    dashboardWaitingHistoryEntries_.clear();
    refreshDashboardWaitingQueueTable();
    dashboardRuntimeTimer_->start();

    appendDashboardAllLog("Start triggered from Dashboard.");
    if (dashboardModeCombo_ && TradingBotWindowSupport::isPaperTradingModeLabel(dashboardModeCombo_->currentText())) {
        appendDashboardAllLog("Paper Local active: using live Binance market data with local paper execution.");
    } else if (dashboardModeCombo_ && TradingBotWindowSupport::isTestnetModeLabel(dashboardModeCombo_->currentText())) {
        appendDashboardAllLog("Demo/Testnet active: using Binance Futures Testnet market data and testnet execution.");
    }
    appendDashboardAllLog(
        QString("Signal feed: %1")
            .arg(useWebSocketFeed
                     ? QStringLiteral("WebSocket Stream")
                     : ((dashboardSignalFeedCombo_
                             && normalizedSignalFeedKey(dashboardSignalFeedCombo_->currentText()) == QStringLiteral("websocket"))
                            ? QStringLiteral("REST Poll (WebSocket unavailable fallback)")
                            : QStringLiteral("REST Poll"))));
    if (dashboardConnectorCombo_) {
        appendDashboardAllLog(QString("Active default connector: %1").arg(dashboardConnectorCombo_->currentText().trimmed()));
    }
    appendDashboardPositionLog(QString("Runtime strategy loop started with %1 override row(s).").arg(dashboardOverridesTable_->rowCount()));
    runDashboardRuntimeCycle();
}

void TradingBotWindow::stopDashboardRuntime() {
    if (dashboardRuntimeStopping_) {
        return;
    }
    dashboardRuntimeStopping_ = true;
    dashboardRuntimeActive_ = false;
    positionsLiveActivePnlValid_ = false;
    positionsLiveActivePnlUpdatedMs_ = 0;
    positionsLiveActivePnlUsdt_ = 0.0;
    positionsLiveActivePnlContextKey_.clear();
    if (dashboardRuntimeTimer_) {
        dashboardRuntimeTimer_->stop();
    }

    const QString modeText = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
    const bool paperTrading = TradingBotWindowSupport::isPaperTradingModeLabel(modeText);
    const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
    for (auto it = dashboardWaitingActiveEntries_.begin(); it != dashboardWaitingActiveEntries_.end(); ++it) {
        QVariantMap endedEntry = it.value();
        endedEntry.insert(QStringLiteral("state"), QStringLiteral("Ended"));
        endedEntry.insert(QStringLiteral("ended_at_ms"), nowMs);
        const qint64 firstSeenMs = endedEntry.value(QStringLiteral("first_seen_ms")).toLongLong();
        const qint64 elapsedMs = firstSeenMs > 0 ? std::max<qint64>(0, nowMs - firstSeenMs) : 0;
        endedEntry.insert(QStringLiteral("age"), static_cast<double>(elapsedMs) / 1000.0);
        endedEntry.insert(QStringLiteral("age_seconds"), static_cast<int>(elapsedMs / 1000));
        dashboardWaitingHistoryEntries_.append(endedEntry);
    }
    dashboardWaitingActiveEntries_.clear();
    if (dashboardWaitingHistoryEntries_.size() > dashboardWaitingHistoryMax_) {
        const int extra = dashboardWaitingHistoryEntries_.size() - dashboardWaitingHistoryMax_;
        dashboardWaitingHistoryEntries_.erase(
            dashboardWaitingHistoryEntries_.begin(),
            dashboardWaitingHistoryEntries_.begin() + extra);
    }
    refreshDashboardWaitingQueueTable();

    const bool keepOpenPositions = dashboardStopWithoutCloseCheck_ && dashboardStopWithoutCloseCheck_->isChecked();
    const bool futures = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    const bool isTestnet = TradingBotWindowSupport::isTestnetModeLabel(modeText);
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const bool hasApiCredentials = !apiKey.isEmpty() && !apiSecret.isEmpty();
    const bool hedgeMode = dashboardPositionModeCombo_
        ? dashboardPositionModeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("hedge"))
        : true;
    const QString defaultConnectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : TradingBotWindowSupport::connectorLabelForKey(TradingBotWindowSupport::recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig defaultConnectorCfg = TradingBotWindowSupport::resolveConnectorConfig(defaultConnectorText, futures);
    QMap<QString, ConnectorRuntimeConfig> closeConnectorConfigs;
    auto addCloseConnectorConfig = [&closeConnectorConfigs](const ConnectorRuntimeConfig &cfg) {
        if (!cfg.ok()) {
            return;
        }
        const QString dedupeKey = QStringLiteral("%1|%2")
                                      .arg(cfg.key.trimmed().toLower(), cfg.baseUrl.trimmed().toLower());
        if (!closeConnectorConfigs.contains(dedupeKey)) {
            closeConnectorConfigs.insert(dedupeKey, cfg);
        }
    };
    addCloseConnectorConfig(defaultConnectorCfg);

    auto setOrCreateCell = [this](int row, int col, const QString &text) {
        if (!positionsTable_) {
            return;
        }
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            item = new QTableWidgetItem(text);
            positionsTable_->setItem(row, col, item);
        } else {
            item->setText(text);
        }
        item->setData(Qt::UserRole, text);
    };
    auto tableCellRaw = [this](int row, int col) -> QString {
        if (!positionsTable_) {
            return {};
        }
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            return {};
        }
        const QVariant raw = item->data(Qt::UserRole);
        return raw.isValid() ? raw.toString() : item->text();
    };
    if (dashboardOverridesTable_) {
        for (int row = 0; row < dashboardOverridesTable_->rowCount(); ++row) {
            const QTableWidgetItem *connectorItem = dashboardOverridesTable_->item(row, 5);
            const QString rowConnectorText = connectorItem && !connectorItem->text().trimmed().isEmpty()
                ? connectorItem->text().trimmed()
                : defaultConnectorText;
            addCloseConnectorConfig(TradingBotWindowSupport::resolveConnectorConfig(rowConnectorText, futures));
        }
    }
    for (auto it = dashboardRuntimeOpenPositions_.cbegin(); it != dashboardRuntimeOpenPositions_.cend(); ++it) {
        const RuntimePosition &openPos = it.value();
        ConnectorRuntimeConfig cfg;
        cfg.key = openPos.connectorKey.trimmed();
        cfg.label = cfg.key;
        cfg.baseUrl = openPos.connectorBaseUrl.trimmed();
        addCloseConnectorConfig(cfg);
    }

    int closeRequested = 0;
    int closeSucceeded = 0;
    int closePartial = 0;
    int closeFailed = 0;
    QMap<QString, BinanceRestClient::FuturesPositionsResult> stopLivePositionsCache;
    const auto stopSnapshotCacheKeyFor = [isTestnet](const QString &baseUrl) {
        return QStringLiteral("%1|%2")
            .arg(baseUrl.trimmed().toLower(),
                 isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"));
    };
    const auto fetchStopLivePositions =
        [&apiKey, &apiSecret, isTestnet, &stopLivePositionsCache, &stopSnapshotCacheKeyFor](
            const QString &baseUrl) -> const BinanceRestClient::FuturesPositionsResult * {
        const QString cacheKey = stopSnapshotCacheKeyFor(baseUrl);
        auto it = stopLivePositionsCache.find(cacheKey);
        if (it == stopLivePositionsCache.end()) {
            it = stopLivePositionsCache.insert(
                cacheKey,
                BinanceRestClient::fetchOpenFuturesPositions(
                    apiKey,
                    apiSecret,
                    isTestnet,
                    10000,
                    baseUrl));
        }
        return &it.value();
    };
    const auto clearStopLivePositionsCache = [&stopLivePositionsCache, &stopSnapshotCacheKeyFor](const QString &baseUrl) {
        stopLivePositionsCache.remove(stopSnapshotCacheKeyFor(baseUrl));
    };
    const auto pickStopLivePosition =
        [hedgeMode](
            const BinanceRestClient::FuturesPositionsResult *snapshot,
            const QString &symbol,
            const QString &runtimeSide) -> const BinanceRestClient::FuturesPosition * {
        if (!snapshot || !snapshot->ok) {
            return nullptr;
        }
        const QString sym = symbol.trimmed().toUpper();
        const QString side = runtimeSide.trimmed().toUpper();
        const BinanceRestClient::FuturesPosition *best = nullptr;
        double bestAbsAmt = 0.0;
        for (const auto &pos : snapshot->positions) {
            if (pos.symbol.trimmed().toUpper() != sym) {
                continue;
            }
            const double absAmt = std::fabs(pos.positionAmt);
            if (!qIsFinite(absAmt) || absAmt <= 1e-10) {
                continue;
            }
            const QString posSide = pos.positionSide.trimmed().toUpper();
            const bool sideMatches = (side == QStringLiteral("LONG") && pos.positionAmt > 0.0)
                || (side == QStringLiteral("SHORT") && pos.positionAmt < 0.0)
                || side.isEmpty();
            if (hedgeMode) {
                if ((side == QStringLiteral("LONG") && posSide == QStringLiteral("LONG"))
                    || (side == QStringLiteral("SHORT") && posSide == QStringLiteral("SHORT"))) {
                    return &pos;
                }
            } else if ((posSide.isEmpty() || posSide == QStringLiteral("BOTH")) && sideMatches) {
                return &pos;
            }
            if (sideMatches && absAmt > bestAbsAmt) {
                bestAbsAmt = absAmt;
                best = &pos;
            }
        }
        return best;
    };
    QSet<QString> fullyClosedKeys;
    const QString stopNowText = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
    if (keepOpenPositions) {
        appendDashboardPositionLog("Stop requested with 'Stop Without Closing Active Positions' enabled: keeping exchange positions open.");
    } else if (paperTrading) {
        int paperClosed = 0;
        const QList<QString> runtimeKeys = dashboardRuntimeOpenPositions_.keys();
        for (const QString &runtimeKey : runtimeKeys) {
            pumpUiEvents();
            const RuntimePosition openPos = dashboardRuntimeOpenPositions_.value(runtimeKey);
            const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
            const QString interval = openPos.interval.trimmed();
            int targetRow = -1;
            if (positionsTable_) {
                for (int row = positionsTable_->rowCount() - 1; row >= 0; --row) {
                    const QString rowSymbol = tableCellRaw(row, 0).trimmed().toUpper();
                    const QString rowInterval = tableCellRaw(row, 8).trimmed();
                    const QString rowStatus = tableCellRaw(row, 16).trimmed().toUpper();
                    if (rowSymbol == symbol
                        && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                        && rowStatus == QStringLiteral("OPEN")) {
                        targetRow = row;
                        break;
                    }
                }
            }

            QString closePriceText = qIsFinite(openPos.entryPrice) && openPos.entryPrice > 0.0
                ? QString::number(openPos.entryPrice, 'f', 6)
                : QStringLiteral("-");
            if (targetRow >= 0) {
                const QString tablePrice = tableCellRaw(targetRow, 2).trimmed();
                if (!tablePrice.isEmpty() && tablePrice != QStringLiteral("-")) {
                    closePriceText = tablePrice;
                }
                setOrCreateCell(targetRow, 14, stopNowText);
                setOrCreateCell(targetRow, 16, QStringLiteral("CLOSED"));
            }

            ++paperClosed;
            appendDashboardPositionLog(
                QString("Stop paper closed %1 %2@%3 at %4.")
                    .arg(openPos.side.trimmed().isEmpty() ? QStringLiteral("POSITION") : openPos.side.trimmed(),
                         symbol.isEmpty() ? QStringLiteral("-") : symbol,
                         interval.isEmpty() ? QStringLiteral("-") : interval,
                         closePriceText));
            dashboardRuntimeOpenPositions_.remove(runtimeKey);
        }
        if (paperClosed > 0) {
            appendDashboardPositionLog(QString("Stop paper close summary: closed=%1.").arg(paperClosed));
        } else {
            appendDashboardPositionLog("Stop paper close summary: no active paper positions to close.");
        }
    } else if (!dashboardRuntimeOpenPositions_.isEmpty()) {
        if (!futures) {
            appendDashboardPositionLog("Stop close skipped: auto-close is supported for Futures account type only.");
            closeFailed = dashboardRuntimeOpenPositions_.size();
        } else if (!hasApiCredentials) {
            appendDashboardPositionLog("Stop close skipped: missing API credentials.");
            closeFailed = dashboardRuntimeOpenPositions_.size();
        } else {
            for (auto it = dashboardRuntimeOpenPositions_.begin(); it != dashboardRuntimeOpenPositions_.end(); ++it) {
                pumpUiEvents();
                const QString runtimeKey = it.key();
                RuntimePosition &openPos = it.value();
                const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
                const QString interval = openPos.interval.trimmed();
                const QStringList keyParts = runtimeKey.split('|');
                QString connectorKey = openPos.connectorKey.trimmed().toLower();
                QString connectorBaseUrl = openPos.connectorBaseUrl.trimmed();
                if (connectorKey.isEmpty() && keyParts.size() >= 3) {
                    connectorKey = keyParts.at(2).trimmed().toLower();
                }
                if (connectorBaseUrl.isEmpty() && keyParts.size() >= 4) {
                    connectorBaseUrl = keyParts.mid(3).join(QStringLiteral("|")).trimmed();
                }

                const auto *liveSnapshot = fetchStopLivePositions(connectorBaseUrl);
                const auto *livePos = pickStopLivePosition(liveSnapshot, symbol, openPos.side);
                if (livePos) {
                    const double liveQty = std::fabs(livePos->positionAmt);
                    if (qIsFinite(liveQty) && liveQty > 1e-10) {
                        openPos.quantity = liveQty;
                    }
                    if (qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                        openPos.entryPrice = livePos->entryPrice;
                    }
                    if (qIsFinite(livePos->leverage) && livePos->leverage > 0.0) {
                        openPos.leverage = livePos->leverage;
                    }
                    const double marginFallback = std::max(
                        1e-9,
                        (std::max(0.0, openPos.entryPrice) * std::max(0.0, openPos.quantity))
                            / std::max(1.0, openPos.leverage));
                    openPos.displayMarginUsdt = std::max(
                        1e-9,
                        livePositionTotalDisplayMargin(
                            livePos,
                            std::max(marginFallback, openPos.displayMarginUsdt)));
                    openPos.roiBasisUsdt = std::max(
                        1e-9,
                        livePositionTotalRoiBasis(
                            livePos,
                            std::max(marginFallback, openPos.roiBasisUsdt)));
                }

                if (symbol.isEmpty() || !qIsFinite(openPos.quantity) || openPos.quantity <= 0.0) {
                    ++closeFailed;
                    appendDashboardPositionLog(
                        QString("Stop close skipped: invalid runtime position key=%1 symbol=%2 qty=%3")
                            .arg(runtimeKey, symbol, QString::number(openPos.quantity, 'f', 8)));
                    continue;
                }

                const QString closeOrderSide = (openPos.side == QStringLiteral("LONG")) ? QStringLiteral("SELL")
                                                                                         : QStringLiteral("BUY");
                const QString closePositionSide = hedgeMode ? openPos.side : QString();
                const bool closeReduceOnly = !hedgeMode;
                int targetRow = -1;
                if (positionsTable_) {
                    for (int row = positionsTable_->rowCount() - 1; row >= 0; --row) {
                        const QString rowSymbol = tableCellRaw(row, 0).trimmed().toUpper();
                        const QString rowInterval = tableCellRaw(row, 8).trimmed();
                        const QString rowStatus = tableCellRaw(row, 16).trimmed().toUpper();
                        const QString rowConnectorHint = tableCellRaw(row, 17).trimmed().toLower();
                        if (rowSymbol == symbol
                            && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                            && rowStatus == QStringLiteral("OPEN")
                            && (connectorKey.isEmpty() || rowConnectorHint.contains(connectorKey))) {
                            targetRow = row;
                            break;
                        }
                    }
                }
                double fallbackClosePrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                    ? livePos->markPrice
                    : 0.0;
                if (fallbackClosePrice <= 0.0 && targetRow >= 0) {
                    bool tablePriceOk = false;
                    const double tablePrice = TradingBotWindowSupport::firstNumberInText(tableCellRaw(targetRow, 2), &tablePriceOk);
                    if (tablePriceOk && qIsFinite(tablePrice) && tablePrice > 0.0) {
                        fallbackClosePrice = tablePrice;
                    }
                }
                if (fallbackClosePrice <= 0.0 && qIsFinite(openPos.entryPrice) && openPos.entryPrice > 0.0) {
                    fallbackClosePrice = openPos.entryPrice;
                }
                ++closeRequested;
                const auto closeOrder = placeFuturesCloseOrderWithFallback(
                    apiKey,
                    apiSecret,
                    symbol,
                    closeOrderSide,
                    openPos.quantity,
                    isTestnet,
                    closeReduceOnly,
                    closePositionSide,
                    10000,
                    connectorBaseUrl,
                    fallbackClosePrice);

                if (!closeOrder.ok) {
                    if (isReduceOnlyRejectedError(closeOrder.error)) {
                        clearStopLivePositionsCache(connectorBaseUrl);
                        const auto *snapshot = fetchStopLivePositions(connectorBaseUrl);
                        if (!hasMatchingOpenFuturesPosition(snapshot, symbol, openPos.side, hedgeMode)) {
                            ++closeSucceeded;
                            fullyClosedKeys.insert(runtimeKey);
                            if (targetRow >= 0) {
                                setOrCreateCell(targetRow, 14, stopNowText);
                                setOrCreateCell(targetRow, 16, QStringLiteral("CLOSED"));
                            }
                            appendDashboardPositionLog(
                                QString("Stop close confirmed %1 %2@%3 (%4): position is already flat on exchange.")
                                    .arg(openPos.side,
                                         symbol,
                                         interval,
                                         connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey));
                            continue;
                        }
                    }
                    ++closeFailed;
                    appendDashboardPositionLog(
                        QString("Stop close failed %1 %2@%3 (%4): %5")
                            .arg(openPos.side,
                                 symbol,
                                 interval,
                                 connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey,
                                 closeOrder.error));
                    continue;
                }
                clearStopLivePositionsCache(connectorBaseUrl);

                const double closePrice = (qIsFinite(closeOrder.avgPrice) && closeOrder.avgPrice > 0.0)
                    ? closeOrder.avgPrice
                    : fallbackClosePrice;
                const double closeQty = (qIsFinite(closeOrder.executedQty) && closeOrder.executedQty > 0.0)
                    ? closeOrder.executedQty
                    : openPos.quantity;
                const double effectiveCloseQty = std::max(0.0, std::min(openPos.quantity, closeQty));
                if (effectiveCloseQty <= 0.0) {
                    ++closeFailed;
                    appendDashboardPositionLog(
                        QString("Stop close failed %1 %2@%3: zero filled quantity.")
                            .arg(openPos.side, symbol, interval));
                    continue;
                }

                const double realizedPnlUsdt = (openPos.side == QStringLiteral("LONG"))
                    ? (closePrice - openPos.entryPrice) * effectiveCloseQty
                    : (openPos.entryPrice - closePrice) * effectiveCloseQty;
                const double totalQtyBeforeClose = std::max(0.0, openPos.quantity);
                const double fallbackCloseMarginUsed = std::max(
                    1e-9,
                    (openPos.entryPrice * effectiveCloseQty) / std::max(1.0, openPos.leverage));
                const double closeShareRatio = totalQtyBeforeClose > 1e-9
                    ? std::min(1.0, std::max(0.0, effectiveCloseQty / totalQtyBeforeClose))
                    : 1.0;
                const double closeRoiBasisUsed = std::max(
                    1e-9,
                    std::max(fallbackCloseMarginUsed, openPos.roiBasisUsdt) * closeShareRatio);
                const double realizedPnlPct = (realizedPnlUsdt / closeRoiBasisUsed) * 100.0;

                if (targetRow >= 0) {
                    setOrCreateCell(targetRow, 2, QString::number(closePrice, 'f', 6));
                    setOrCreateCell(
                        targetRow,
                        7,
                        QStringLiteral("%1 (%2%)")
                            .arg(QString::number(realizedPnlUsdt, 'f', 2),
                                 QString::number(realizedPnlPct, 'f', 2)));
                    setTableCellNumeric(positionsTable_, targetRow, 2, closePrice);
                    setTableCellNumeric(positionsTable_, targetRow, 7, realizedPnlUsdt);
                    if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                        setTableCellRoiBasis(pnlItem, closeRoiBasisUsed);
                    }
                }

                const bool partialClose = (effectiveCloseQty + 1e-9) < openPos.quantity;
                if (partialClose) {
                    ++closePartial;
                    openPos.quantity = std::max(0.0, openPos.quantity - effectiveCloseQty);
                    if (targetRow >= 0) {
                        const double remainingRatio = totalQtyBeforeClose > 1e-9
                            ? std::min(1.0, std::max(0.0, openPos.quantity / totalQtyBeforeClose))
                            : 0.0;
                        const double remainingNotional = std::max(0.0, openPos.quantity * closePrice);
                        const double remainingDisplayMarginUsdt = std::max(
                            0.0,
                            std::max(fallbackCloseMarginUsed, openPos.displayMarginUsdt) * remainingRatio);
                        const double remainingRoiBasisUsdt = std::max(
                            0.0,
                            std::max(fallbackCloseMarginUsed, openPos.roiBasisUsdt) * remainingRatio);
                        openPos.displayMarginUsdt = std::max(1e-9, remainingDisplayMarginUsdt);
                        openPos.roiBasisUsdt = std::max(1e-9, remainingRoiBasisUsdt);
                        setOrCreateCell(targetRow, 1, formatPositionSizeText(remainingNotional, openPos.quantity, symbol));
                        setOrCreateCell(
                            targetRow,
                            5,
                            QString::number(remainingDisplayMarginUsdt, 'f', 2));
                        setOrCreateCell(targetRow, 6, formatQuantityWithSymbol(openPos.quantity, symbol));
                        setTableCellNumeric(positionsTable_, targetRow, 1, remainingNotional);
                        setTableCellNumeric(positionsTable_, targetRow, 5, remainingDisplayMarginUsdt);
                        setTableCellNumeric(positionsTable_, targetRow, 6, openPos.quantity);
                        if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                            setTableCellRoiBasis(pnlItem, remainingRoiBasisUsdt);
                        }
                    }
                    appendDashboardPositionLog(
                        QString("Stop partially closed %1 %2@%3 qty=%4 remaining=%5 (connector=%6, orderId=%7): %8")
                            .arg(openPos.side,
                                 symbol,
                                 interval,
                                 QString::number(effectiveCloseQty, 'f', 6),
                                 QString::number(openPos.quantity, 'f', 6),
                                 connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey,
                                 closeOrder.orderId,
                                 closeOrder.error.isEmpty() ? QStringLiteral("remaining exposure still open")
                                                            : closeOrder.error));
                    } else {
                        ++closeSucceeded;
                        fullyClosedKeys.insert(runtimeKey);
                        if (targetRow >= 0) {
                            setOrCreateCell(targetRow, 14, stopNowText);
                            setOrCreateCell(targetRow, 16, QStringLiteral("CLOSED"));
                        }
                    appendDashboardPositionLog(
                        QString("Stop closed %1 %2@%3 at %4 PNL=%5 USDT (%6%%) (connector=%7, orderId=%8)")
                            .arg(openPos.side,
                                 symbol,
                                 interval,
                                 QString::number(closePrice, 'f', 6),
                                 QString::number(realizedPnlUsdt, 'f', 2),
                                 QString::number(realizedPnlPct, 'f', 2),
                                 connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey,
                                 closeOrder.orderId));
                }
            }
            for (const QString &closedKey : fullyClosedKeys) {
                dashboardRuntimeOpenPositions_.remove(closedKey);
            }
        }
    }

    int sweepRequested = 0;
    int sweepSucceeded = 0;
    int sweepPartial = 0;
    int sweepFailed = 0;
    const bool stopNeedsSweep = closeRequested == 0
        || !dashboardRuntimeOpenPositions_.isEmpty()
        || closeFailed > 0
        || closePartial > 0;
    if (!keepOpenPositions && !paperTrading && futures && hasApiCredentials && !closeConnectorConfigs.isEmpty() && stopNeedsSweep) {
        QSet<QString> attemptedSweepKeys;
        for (auto cfgIt = closeConnectorConfigs.cbegin(); cfgIt != closeConnectorConfigs.cend(); ++cfgIt) {
            pumpUiEvents();
            const ConnectorRuntimeConfig &cfg = cfgIt.value();
            const auto snapshot = BinanceRestClient::fetchOpenFuturesPositions(
                apiKey,
                apiSecret,
                isTestnet,
                10000,
                cfg.baseUrl);
            if (!snapshot.ok) {
                ++sweepFailed;
                appendDashboardPositionLog(
                    QString("Stop sweep fetch failed (%1): %2")
                        .arg(cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                             snapshot.error));
                continue;
            }
            for (const auto &pos : snapshot.positions) {
                pumpUiEvents();
                const QString symbol = pos.symbol.trimmed().toUpper();
                if (symbol.isEmpty()) {
                    continue;
                }
                const double qty = std::fabs(pos.positionAmt);
                if (!qIsFinite(qty) || qty <= 1e-10) {
                    continue;
                }
                const bool isLong = pos.positionAmt > 0.0;
                const QString runtimeSide = isLong ? QStringLiteral("LONG") : QStringLiteral("SHORT");
                QString positionSide = pos.positionSide.trimmed().toUpper();
                if (hedgeMode) {
                    if (positionSide != QStringLiteral("LONG") && positionSide != QStringLiteral("SHORT")) {
                        positionSide = runtimeSide;
                    }
                } else {
                    positionSide.clear();
                }
                const QString closeOrderSide = isLong ? QStringLiteral("SELL") : QStringLiteral("BUY");
                const bool closeReduceOnly = !hedgeMode;
                const QString dedupeKey = QStringLiteral("%1|%2|%3|%4|%5")
                                              .arg(cfg.key.trimmed().toLower(),
                                                   cfg.baseUrl.trimmed().toLower(),
                                                   symbol,
                                                   closeOrderSide,
                                                   positionSide);
                if (attemptedSweepKeys.contains(dedupeKey)) {
                    continue;
                }
                attemptedSweepKeys.insert(dedupeKey);
                ++sweepRequested;
                const auto closeOrder = placeFuturesCloseOrderWithFallback(
                    apiKey,
                    apiSecret,
                    symbol,
                    closeOrderSide,
                    qty,
                    isTestnet,
                    closeReduceOnly,
                    positionSide,
                    10000,
                    cfg.baseUrl,
                    (qIsFinite(pos.markPrice) && pos.markPrice > 0.0)
                        ? pos.markPrice
                        : pos.entryPrice);
                if (!closeOrder.ok) {
                    if (isReduceOnlyRejectedError(closeOrder.error)) {
                        clearStopLivePositionsCache(cfg.baseUrl);
                        const auto *snapshot = fetchStopLivePositions(cfg.baseUrl);
                        if (!hasMatchingOpenFuturesPosition(snapshot, symbol, runtimeSide, hedgeMode)) {
                            ++sweepSucceeded;
                            appendDashboardPositionLog(
                                QString("Stop sweep confirmed %1 %2 (%3): position is already flat on exchange.")
                                    .arg(runtimeSide,
                                         symbol,
                                         cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key));
                            continue;
                        }
                    }
                    ++sweepFailed;
                    appendDashboardPositionLog(
                        QString("Stop sweep close failed %1 %2 qty=%3 (%4): %5")
                            .arg(runtimeSide,
                                 symbol,
                                 QString::number(qty, 'f', 6),
                                 cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                                 closeOrder.error));
                    continue;
                }
                clearStopLivePositionsCache(cfg.baseUrl);
                const double filledQty = (qIsFinite(closeOrder.executedQty) && closeOrder.executedQty > 0.0)
                    ? std::min(qty, closeOrder.executedQty)
                    : qty;
                if (!qIsFinite(filledQty) || filledQty <= 1e-10) {
                    ++sweepFailed;
                    appendDashboardPositionLog(
                        QString("Stop sweep close failed %1 %2 qty=%3 (%4): zero fill.")
                            .arg(runtimeSide,
                                 symbol,
                                 QString::number(qty, 'f', 6),
                                 cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key));
                    continue;
                }
                const bool partialSweep = (filledQty + 1e-9) < qty;
                if (partialSweep) {
                    ++sweepPartial;
                    appendDashboardPositionLog(
                        QString("Stop sweep partially closed %1 %2 filled=%3 requested=%4 (%5, orderId=%6): %7")
                            .arg(runtimeSide,
                                 symbol,
                                 QString::number(filledQty, 'f', 6),
                                 QString::number(qty, 'f', 6),
                                 cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                                 closeOrder.orderId,
                                 closeOrder.error.isEmpty() ? QStringLiteral("remaining exposure still open")
                                                            : closeOrder.error));
                    continue;
                }
                ++sweepSucceeded;
                appendDashboardPositionLog(
                    QString("Stop sweep closed %1 %2 qty=%3 (%4, orderId=%5)")
                        .arg(runtimeSide,
                             symbol,
                             QString::number(qty, 'f', 6),
                             cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                             closeOrder.orderId));

                if (positionsTable_) {
                    for (int row = 0; row < positionsTable_->rowCount(); ++row) {
                        const QString rowSymbol = tableCellRaw(row, 0).trimmed().toUpper();
                        const QString rowStatus = tableCellRaw(row, 16).trimmed().toUpper();
                        if (rowSymbol != symbol || rowStatus != QStringLiteral("OPEN")) {
                            continue;
                        }
                        setOrCreateCell(row, 14, stopNowText);
                        setOrCreateCell(row, 16, QStringLiteral("CLOSED"));
                    }
                }
                const QList<QString> runtimeKeys = dashboardRuntimeOpenPositions_.keys();
                for (const QString &runtimeKey : runtimeKeys) {
                    const RuntimePosition runtimePos = dashboardRuntimeOpenPositions_.value(runtimeKey);
                    const QString runtimeSymbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
                    if (runtimeSymbol != symbol) {
                        continue;
                    }
                    if (runtimePos.side.trimmed().toUpper() != runtimeSide) {
                        continue;
                    }
                    dashboardRuntimeOpenPositions_.remove(runtimeKey);
                }
            }
        }
    }

    if (!keepOpenPositions && !paperTrading) {
        if (closeRequested > 0 || closeFailed > 0) {
            appendDashboardPositionLog(
                QString("Stop close summary: requested=%1 succeeded=%2 partial=%3 failed=%4.")
                    .arg(closeRequested)
                    .arg(closeSucceeded)
                    .arg(closePartial)
                    .arg(closeFailed));
        } else if (dashboardRuntimeOpenPositions_.isEmpty()) {
            appendDashboardPositionLog("Stop close summary: no active runtime positions to close.");
        }
        if (sweepRequested > 0 || sweepFailed > 0) {
            appendDashboardPositionLog(
                QString("Stop sweep summary: requested=%1 succeeded=%2 partial=%3 failed=%4.")
                    .arg(sweepRequested)
                    .arg(sweepSucceeded)
                    .arg(sweepPartial)
                    .arg(sweepFailed));
        }
    }
    applyPositionsViewMode();

    if (dashboardStopBtn_) {
        dashboardStopBtn_->setEnabled(false);
    }
    if (dashboardStartBtn_) {
        dashboardStartBtn_->setEnabled(true);
    }
    setDashboardRuntimeControlsEnabled(true);
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("OFF");
        dashboardBotStatusLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("--");
    }
    handleStopBacktest();
    appendDashboardAllLog("Stop triggered from Dashboard.");
    appendDashboardPositionLog("Runtime strategy loop stopped.");
    clearRuntimeSignalSockets(dashboardRuntimeSignalSockets_);
    dashboardRuntimeSignalCandles_.clear();
    dashboardRuntimeSignalLastClosed_.clear();
    dashboardRuntimeSignalUpdateMs_.clear();
    dashboardRuntimeStopping_ = false;
}

