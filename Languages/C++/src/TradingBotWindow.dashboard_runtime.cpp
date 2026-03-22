#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "BinanceWsClient.h"
#include "TradingBotWindow.dashboard_runtime_internal.h"
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
#include <QTextEdit>
#include <QTimer>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <limits>


using namespace TradingBotWindowDashboardRuntime;
using namespace TradingBotWindowDashboardRuntimeDetail;
using ConnectorRuntimeConfig = TradingBotWindowSupport::ConnectorRuntimeConfig;

void TradingBotWindow::refreshDashboardOpenPositionIndicatorValuesForSignalKey(
    const QString &signalKey,
    const QVector<BinanceRestClient::KlineCandle> &marketCandles) {
    if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_ || !positionsTable_ || marketCandles.isEmpty()) {
        return;
    }

    const QString normalizedSignalKey = signalKey.trimmed().toLower();
    if (normalizedSignalKey.isEmpty()) {
        return;
    }

    const IndicatorRuntimeSettings indicatorSettings = buildIndicatorRuntimeSettings(dashboardIndicatorParams_);
    bool positionsTableMutated = false;
    for (auto it = dashboardRuntimeOpenPositions_.cbegin(); it != dashboardRuntimeOpenPositions_.cend(); ++it) {
        const QString runtimeKey = it.key();
        const RuntimePosition &openPos = it.value();
        const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
        if (symbol.isEmpty()) {
            continue;
        }

        const QString connectorToken = QStringLiteral("%1|%2")
                                           .arg(openPos.connectorKey.trimmed(),
                                                openPos.connectorBaseUrl.trimmed());
        const QString requestInterval = normalizeBinanceKlineInterval(openPos.interval);
        const QString positionSignalKey = runtimeKeyFor(symbol, requestInterval, connectorToken);
        if (positionSignalKey.trimmed().toLower() != normalizedSignalKey) {
            continue;
        }

        const QString sourceKey = normalizedIndicatorKey(openPos.signalSource);
        IndicatorRuntimeValues displayValues;
        displayValues.useRsi = (sourceKey == QStringLiteral("rsi"));
        displayValues.useStochRsi = (sourceKey == QStringLiteral("stoch_rsi"));
        displayValues.useWillr = (sourceKey == QStringLiteral("willr"));
        if (sourceKey == QStringLiteral("generic")) {
            displayValues.useRsi = true;
            displayValues.useStochRsi = true;
            displayValues.useWillr = true;
        }

        if (displayValues.useRsi) {
            displayValues.rsi = latestRsiValue(marketCandles, indicatorSettings.rsiLength, &displayValues.rsiOk);
        }
        if (displayValues.useStochRsi) {
            displayValues.stochRsi = latestStochRsiValue(
                marketCandles,
                indicatorSettings.stochLength,
                indicatorSettings.stochSmoothK,
                indicatorSettings.stochSmoothD,
                &displayValues.stochRsiOk);
        }
        if (displayValues.useWillr) {
            displayValues.willr = latestWilliamsRValue(
                marketCandles,
                indicatorSettings.willrLength,
                &displayValues.willrOk);
        }

        const int targetRow = findOpenPositionRow(positionsTable_, symbol, openPos.interval, openPos.connectorKey);
        if (targetRow < 0) {
            continue;
        }

        setPositionIndicatorValueSummary(
            positionsTable_,
            positionsCumulativeView_,
            targetRow,
            formatIndicatorValueSummaryForSource(displayValues, openPos.signalSource));
        positionsTableMutated = true;
    }

    if (!positionsTableMutated || !positionsCumulativeView_) {
        return;
    }
    applyPositionsViewMode(false, false);
}

void TradingBotWindow::runDashboardRuntimeCycle() {
    if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_ || dashboardRuntimeCycleInProgress_) {
        return;
    }
    if (!dashboardOverridesTable_ || dashboardOverridesTable_->rowCount() <= 0) {
        return;
    }
    dashboardRuntimeCycleInProgress_ = true;
    struct RuntimeCycleGuard final {
        bool *flag = nullptr;
        ~RuntimeCycleGuard() {
            if (flag) {
                *flag = false;
            }
        }
    } runtimeCycleGuard{&dashboardRuntimeCycleInProgress_};

    bool positionsTableMutated = false;
    bool positionsTableStructureChanged = false;
    auto flushPendingPositionsView = [&]() {
        if (!positionsTableMutated) {
            return;
        }
        if (positionsCumulativeView_) {
            applyPositionsViewMode(positionsTableStructureChanged, positionsTableStructureChanged);
        } else {
            refreshPositionsSummaryLabels();
            if (positionsTableStructureChanged) {
                refreshPositionsTableSizing();
            }
        }
        positionsTableMutated = false;
        positionsTableStructureChanged = false;
    };
    auto applyCumulativeViewImmediately = [&]() {
        if (!positionsCumulativeView_ || !positionsTable_ || !positionsTableMutated) {
            return;
        }
        ScopedTableUpdatesPause updatesPause(positionsTable_);
        applyPositionsViewMode(false, false);
    };
    QSet<QString> waitingSeenThisCycle;
    const qint64 cycleNowMs = QDateTime::currentMSecsSinceEpoch();

    const bool futures = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith("fut")
        : true;
    const QString modeText = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
    const bool paperTrading = TradingBotWindowSupport::isPaperTradingModeLabel(modeText);
    const bool isTestnet = TradingBotWindowSupport::isTestnetModeLabel(modeText);
    const QString indicatorSourceText = dashboardIndicatorSourceCombo_
        ? dashboardIndicatorSourceCombo_->currentText().trimmed()
        : QStringLiteral("Binance futures");
    const QString indicatorSourceKey = normalizedIndicatorSourceKey(indicatorSourceText);
    const QString signalFeedText = dashboardSignalFeedCombo_
        ? dashboardSignalFeedCombo_->currentText().trimmed()
        : QStringLiteral("REST Poll");
    const QString signalFeedKey = normalizedSignalFeedKey(signalFeedText);
    const bool websocketFeedRequested = signalFeedKey == QStringLiteral("websocket");
    const bool useWebSocketFeed = websocketFeedRequested && qtWebSocketsRuntimeAvailable();
    const QString defaultConnectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : TradingBotWindowSupport::connectorLabelForKey(TradingBotWindowSupport::recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig defaultConnectorCfg = TradingBotWindowSupport::resolveConnectorConfig(defaultConnectorText, futures);
    const IndicatorRuntimeSettings indicatorSettings = buildIndicatorRuntimeSettings(dashboardIndicatorParams_);

    double availableUsdt = currentDashboardPaperBalanceUsdt();
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const bool hasApiCredentials = !apiKey.isEmpty() && !apiSecret.isEmpty();
    const bool hedgeMode = dashboardPositionModeCombo_
        ? dashboardPositionModeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("hedge"))
        : true;
    const QString liveActivePnlContextKey = QStringLiteral("%1|%2|%3")
                                                .arg(apiKey.trimmed(),
                                                     dashboardAccountTypeCombo_
                                                         ? dashboardAccountTypeCombo_->currentText().trimmed().toLower()
                                                         : QStringLiteral("futures"),
                                                     modeText.trimmed().toLower());
    QMap<QString, BinanceRestClient::FuturesSymbolFilters> symbolFiltersCache;
    QMap<QString, BinanceRestClient::TickerPriceResult> tickerPriceCache;
    QMap<QString, BinanceRestClient::FuturesPositionsResult> livePositionsCache;
    static QMap<QString, BinanceRestClient::FuturesPositionsResult> s_stickyLivePositionsCache;
    static QMap<QString, qint64> s_stickyLivePositionsCacheMs;
    const auto sumSnapshotActivePnl =
        [](const BinanceRestClient::FuturesPositionsResult &snapshot) -> double {
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
    };
    const auto connectorCacheKeyFor = [isTestnet](const ConnectorRuntimeConfig &cfg) {
        return QStringLiteral("%1|%2|%3")
            .arg(cfg.key.trimmed().toLower(),
                 cfg.baseUrl.trimmed().toLower(),
                 isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"));
    };
    const auto tickerCacheKeyFor = [isTestnet](const QString &symbol, const ConnectorRuntimeConfig &cfg) {
        return QStringLiteral("%1|%2|%3|%4")
            .arg(symbol.trimmed().toUpper(),
                 cfg.key.trimmed().toLower(),
                 cfg.baseUrl.trimmed().toLower(),
                 isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"));
    };
    const auto fetchExecutionTickerPrice =
        [isTestnet, &tickerPriceCache, &tickerCacheKeyFor](
            const QString &symbol,
            const ConnectorRuntimeConfig &cfg) -> const BinanceRestClient::TickerPriceResult * {
        if (!cfg.ok()) {
            return nullptr;
        }
        const QString cacheKey = tickerCacheKeyFor(symbol, cfg);
        auto it = tickerPriceCache.find(cacheKey);
        if (it == tickerPriceCache.end()) {
            it = tickerPriceCache.insert(
                cacheKey,
                BinanceRestClient::fetchTickerPrice(
                    symbol,
                    true,
                    isTestnet,
                    5000,
                    cfg.baseUrl));
        }
        return &it.value();
    };
    const auto hasTrackedOpenPositionsForConnector =
        [this](const ConnectorRuntimeConfig &cfg) -> bool {
        const QString connectorKey = cfg.key.trimmed().toLower();
        const QString connectorBaseUrl = cfg.baseUrl.trimmed().toLower();
        for (auto it = dashboardRuntimeOpenPositions_.cbegin(); it != dashboardRuntimeOpenPositions_.cend(); ++it) {
            const RuntimePosition &pos = it.value();
            if (pos.connectorKey.trimmed().toLower() == connectorKey
                && pos.connectorBaseUrl.trimmed().toLower() == connectorBaseUrl) {
                return true;
            }
        }
        return false;
    };
    const auto fetchLivePositionsForConnector =
        [this, futures, hasApiCredentials, paperTrading, &apiKey, &apiSecret, isTestnet, &livePositionsCache, &connectorCacheKeyFor, &hasTrackedOpenPositionsForConnector](
            const ConnectorRuntimeConfig &cfg) -> const BinanceRestClient::FuturesPositionsResult * {
        if (paperTrading || !futures || !hasApiCredentials || !cfg.ok()) {
            return nullptr;
        }
        const QString cacheKey = connectorCacheKeyFor(cfg);
        auto it = livePositionsCache.find(cacheKey);
        if (it == livePositionsCache.end()) {
            const auto result = BinanceRestClient::fetchOpenFuturesPositions(
                apiKey,
                apiSecret,
                isTestnet,
                10000,
                cfg.baseUrl);
            it = livePositionsCache.insert(cacheKey, result);
            if (!result.ok) {
                const QString warningKey = QStringLiteral("live-positions|%1|%2")
                                               .arg(cacheKey, result.error);
                if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                    dashboardRuntimeConnectorWarnings_.insert(warningKey);
                    appendDashboardPositionLog(
                        QString("Live position snapshot failed (%1): %2")
                            .arg(cfg.key, result.error));
                }
            }
            const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
            if (result.ok && !result.positions.isEmpty()) {
                s_stickyLivePositionsCache.insert(cacheKey, result);
                s_stickyLivePositionsCacheMs.insert(cacheKey, nowMs);
            } else if (hasTrackedOpenPositionsForConnector(cfg)) {
                const qint64 cachedMs = s_stickyLivePositionsCacheMs.value(cacheKey, 0);
                const bool cachedFresh = cachedMs > 0 && (nowMs - cachedMs) <= 15000;
                if (cachedFresh && s_stickyLivePositionsCache.contains(cacheKey)) {
                    it.value() = s_stickyLivePositionsCache.value(cacheKey);
                }
            } else if (result.ok && result.positions.isEmpty()) {
                s_stickyLivePositionsCache.remove(cacheKey);
                s_stickyLivePositionsCacheMs.remove(cacheKey);
            }
        }
        return &it.value();
    };
    const auto pickLivePosition =
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
            if (absAmt <= 1e-10) {
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
    QMap<QString, double> runtimeQtyByExposureKey;
    for (auto it = dashboardRuntimeOpenPositions_.cbegin(); it != dashboardRuntimeOpenPositions_.cend(); ++it) {
        const QString runtimeSymbol = it.key().section('|', 0, 0).trimmed().toUpper();
        const RuntimePosition &pos = it.value();
        const QString connectorToken = QStringLiteral("%1|%2")
                                           .arg(pos.connectorKey.trimmed().toLower(),
                                                pos.connectorBaseUrl.trimmed().toLower());
        const QString exposureKey = QStringLiteral("%1|%2|%3")
                                        .arg(runtimeSymbol,
                                             pos.side.trimmed().toUpper(),
                                             connectorToken);
        const double qty = std::max(0.0, pos.quantity);
        if (qty > 0.0) {
            runtimeQtyByExposureKey[exposureKey] += qty;
        }
    }
    const auto ensureSignalStreamForKey =
        [this, useWebSocketFeed, isTestnet]
        (const QString &signalKey,
         const QString &symbol,
         const QString &requestInterval,
         bool signalUsesFutures,
         const QString &baseUrl) -> bool {
        if (!useWebSocketFeed) {
            return false;
        }

        if (!dashboardRuntimeSignalCandles_.contains(signalKey)) {
            const auto seed = BinanceRestClient::fetchKlines(
                symbol,
                requestInterval,
                signalUsesFutures,
                isTestnet && signalUsesFutures,
                240,
                10000,
                baseUrl);
            if (seed.ok && !seed.candles.isEmpty()) {
                dashboardRuntimeSignalCandles_.insert(signalKey, seed.candles);
                dashboardRuntimeSignalLastClosed_.insert(signalKey, false);
                dashboardRuntimeSignalUpdateMs_.insert(signalKey, QDateTime::currentMSecsSinceEpoch());
            } else {
                const QString warningKey = QStringLiteral("signal-seed|%1|%2").arg(signalKey, seed.error);
                if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                    dashboardRuntimeConnectorWarnings_.insert(warningKey);
                    appendDashboardAllLog(
                        QString("Signal stream seed failed for %1@%2: %3")
                            .arg(symbol, requestInterval, seed.error));
                }
            }
        }

        if (dashboardRuntimeSignalSockets_.contains(signalKey)) {
            return dashboardRuntimeSignalCandles_.contains(signalKey)
                && !dashboardRuntimeSignalCandles_.value(signalKey).isEmpty();
        }

        auto *client = new BinanceWsClient(this);
        const QString symbolKey = symbol.trimmed().toUpper();
        const QString intervalKey = requestInterval.trimmed().toLower();
        connect(client, &BinanceWsClient::kline, this, [this, signalKey, symbolKey, intervalKey](
                                                        const QString &streamSymbol,
                                                        const QString &streamInterval,
                                                        qint64 openTimeMs,
                                                        double open,
                                                        double high,
                                                        double low,
                                                        double close,
                                                        double volume,
                                                        bool isClosed) {
            if (streamSymbol.trimmed().toUpper() != symbolKey
                || streamInterval.trimmed().toLower() != intervalKey) {
                return;
            }
            BinanceRestClient::KlineCandle candle;
            candle.openTimeMs = openTimeMs;
            candle.open = open;
            candle.high = high;
            candle.low = low;
            candle.close = close;
            candle.volume = volume;
            auto &cache = dashboardRuntimeSignalCandles_[signalKey];
            if (!cache.isEmpty() && cache.constLast().openTimeMs == openTimeMs) {
                cache.last() = candle;
            } else {
                cache.push_back(candle);
                if (cache.size() > 240) {
                    cache.remove(0, cache.size() - 240);
                }
            }
            dashboardRuntimeSignalLastClosed_[signalKey] = isClosed;
            dashboardRuntimeSignalUpdateMs_[signalKey] = QDateTime::currentMSecsSinceEpoch();
            refreshDashboardOpenPositionIndicatorValuesForSignalKey(signalKey, cache);
        });
        connect(client, &BinanceWsClient::errorOccurred, this, [this, signalKey, symbolKey, intervalKey](const QString &message) {
            const QString warningKey = QStringLiteral("signal-stream|%1|%2").arg(signalKey, message);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Signal stream error for %1@%2: %3")
                        .arg(symbolKey, intervalKey, message));
            }
        });
        dashboardRuntimeSignalSockets_.insert(signalKey, client);
        client->connectKline(symbol, requestInterval, signalUsesFutures, isTestnet && signalUsesFutures);
        return dashboardRuntimeSignalCandles_.contains(signalKey)
            && !dashboardRuntimeSignalCandles_.value(signalKey).isEmpty();
    };

    if (!futures) {
        const QString warningKey = QStringLiteral("runtime-account-type|spot-unsupported");
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog("Runtime warning: C++ auto-trading currently supports Futures mode only.");
        }
    }
    if (websocketFeedRequested && !useWebSocketFeed) {
        const QString warningKey = QStringLiteral("signal-feed|websocket-unavailable");
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog("Signal feed warning: WebSocket Stream requested but Qt WebSockets runtime is unavailable. Falling back to REST Poll.");
        }
    }
    if (!hasApiCredentials && !paperTrading) {
        const QString warningKey = QStringLiteral("runtime-auth|missing-credentials");
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog("Runtime warning: API key/secret required. Trades will not be submitted.");
        }
    }

    if (!defaultConnectorCfg.ok()) {
        const QString warningKey = QStringLiteral("balance-connector|") + defaultConnectorCfg.error;
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog(QString("Connector warning: %1").arg(defaultConnectorCfg.error));
        }
    } else {
        if (!defaultConnectorCfg.warning.trimmed().isEmpty()) {
            const QString warningKey = QStringLiteral("balance-connector-warning|") + defaultConnectorCfg.warning;
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(QString("Connector fallback: %1").arg(defaultConnectorCfg.warning));
            }
        }
        if (paperTrading) {
            const double paperBalance = currentDashboardPaperBalanceUsdt();
            positionsLastTotalBalanceUsdt_ = paperBalance;
            positionsLastAvailableBalanceUsdt_ = paperBalance;
            availableUsdt = paperBalance;
        } else if (hasApiCredentials) {
            static QString s_balanceCacheKey;
            static qint64 s_balanceCacheMs = 0;
            static bool s_balanceCacheValid = false;
            static double s_balanceCacheTotal = 0.0;
            static double s_balanceCacheAvailable = 0.0;

            const QString balanceCacheKey = QStringLiteral("%1|%2|%3|%4")
                                                .arg(apiKey.trimmed(),
                                                     futures ? QStringLiteral("futures") : QStringLiteral("spot"),
                                                     isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"),
                                                     defaultConnectorCfg.baseUrl.trimmed().toLower());
            const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
            const bool useCachedBalance = s_balanceCacheValid
                && s_balanceCacheKey == balanceCacheKey
                && (nowMs - s_balanceCacheMs) <= 5000;

            if (useCachedBalance) {
                if (qIsFinite(s_balanceCacheTotal) && s_balanceCacheTotal >= 0.0) {
                    positionsLastTotalBalanceUsdt_ = s_balanceCacheTotal;
                }
                if (qIsFinite(s_balanceCacheAvailable) && s_balanceCacheAvailable >= 0.0) {
                    positionsLastAvailableBalanceUsdt_ = s_balanceCacheAvailable;
                    if (s_balanceCacheAvailable > 0.0) {
                        availableUsdt = s_balanceCacheAvailable;
                    }
                }
            } else {
                const auto balance = BinanceRestClient::fetchUsdtBalance(
                    apiKey,
                    apiSecret,
                    futures,
                    isTestnet,
                    6000,
                    defaultConnectorCfg.baseUrl);
                if (!balance.ok) {
                    appendDashboardPositionLog(
                        QString("Balance fetch failed (%1): %2")
                            .arg(defaultConnectorText, balance.error));
                } else {
                    const double totalBalance = std::max(
                        0.0,
                        (balance.totalUsdtBalance > 0.0) ? balance.totalUsdtBalance : balance.usdtBalance);
                    const double availableBalance = std::max(
                        0.0,
                        (balance.availableUsdtBalance > 0.0) ? balance.availableUsdtBalance : totalBalance);
                    s_balanceCacheKey = balanceCacheKey;
                    s_balanceCacheMs = nowMs;
                    s_balanceCacheValid = true;
                    s_balanceCacheTotal = totalBalance;
                    s_balanceCacheAvailable = availableBalance;
                    if (qIsFinite(totalBalance) && totalBalance >= 0.0) {
                        positionsLastTotalBalanceUsdt_ = totalBalance;
                    }
                    if (qIsFinite(availableBalance) && availableBalance >= 0.0) {
                        positionsLastAvailableBalanceUsdt_ = availableBalance;
                    }
                    if (qIsFinite(availableBalance) && availableBalance > 0.0) {
                        availableUsdt = availableBalance;
                    }
                }
            }
        }
    }

    auto touchWaitingEntry = [this, &waitingSeenThisCycle](const QString &waitingKey, qint64 nowMs) {
        auto waitingIt = dashboardWaitingActiveEntries_.find(waitingKey);
        if (waitingIt == dashboardWaitingActiveEntries_.end()) {
            return;
        }
        waitingSeenThisCycle.insert(waitingKey);
        QVariantMap waitingEntry = waitingIt.value();
        qint64 firstSeenMs = waitingEntry.value(QStringLiteral("first_seen_ms")).toLongLong();
        if (firstSeenMs <= 0) {
            firstSeenMs = nowMs;
        }
        const qint64 elapsedMs = std::max<qint64>(0, nowMs - firstSeenMs);
        const double ageSeconds = static_cast<double>(elapsedMs) / 1000.0;
        waitingEntry.insert(QStringLiteral("first_seen_ms"), firstSeenMs);
        waitingEntry.insert(QStringLiteral("updated_ms"), nowMs);
        waitingEntry.insert(QStringLiteral("age"), ageSeconds);
        waitingEntry.insert(QStringLiteral("age_seconds"), static_cast<int>(elapsedMs / 1000));
        waitingEntry.insert(
            QStringLiteral("state"),
            ageSeconds >= kWaitingPositionLateThresholdSec
                ? QStringLiteral("Late")
                : QStringLiteral("Queued"));
        waitingIt.value() = waitingEntry;
    };

    for (int row = 0; row < dashboardOverridesTable_->rowCount(); ++row) {
        if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_) {
            break;
        }
        if (row > 0) {
            flushPendingPositionsView();
            pumpUiEvents();
            if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_) {
                break;
            }
        }
        const auto *symbolItem = dashboardOverridesTable_->item(row, 0);
        const auto *intervalItem = dashboardOverridesTable_->item(row, 1);
        if (!symbolItem || !intervalItem) {
            continue;
        }

        const QString symbol = symbolItem->text().trimmed().toUpper();
        const QString interval = intervalItem->text().trimmed();
        if (symbol.isEmpty() || interval.isEmpty()) {
            continue;
        }

        const auto *connectorItem = dashboardOverridesTable_->item(row, 5);
        const QString rowConnectorText = connectorItem && !connectorItem->text().trimmed().isEmpty()
            ? connectorItem->text().trimmed()
            : defaultConnectorText;
        const ConnectorRuntimeConfig rowConnectorCfg = TradingBotWindowSupport::resolveConnectorConfig(rowConnectorText, futures);
        if (!rowConnectorCfg.ok()) {
            const QString warningKey = QStringLiteral("row-connector|%1|%2").arg(rowConnectorText, rowConnectorCfg.error);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Connector warning (%1): %2").arg(rowConnectorText, rowConnectorCfg.error));
            }
            continue;
        }
        if (!rowConnectorCfg.warning.trimmed().isEmpty()) {
            const QString warningKey = QStringLiteral("row-connector-warning|%1|%2")
                                           .arg(rowConnectorText, rowConnectorCfg.warning);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Connector fallback (%1): %2").arg(rowConnectorText, rowConnectorCfg.warning));
            }
        }
        const QString connectorToken = rowConnectorCfg.key + "|" + rowConnectorCfg.baseUrl;
        const QString key = runtimeKeyFor(symbol, interval, connectorToken);
        const auto *loopItem = dashboardOverridesTable_->item(row, 3);
        const qint64 loopSeconds = std::max<qint64>(0, loopSecondsFromText(loopItem ? loopItem->text() : QString()));
        const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
        const qint64 retryAfterMs = dashboardRuntimeEntryRetryAfterMs_.value(key, 0);
        if (retryAfterMs > nowMs) {
            touchWaitingEntry(key, nowMs);
            continue;
        }
        if (retryAfterMs > 0) {
            dashboardRuntimeEntryRetryAfterMs_.remove(key);
        }
        const qint64 lastMs = dashboardRuntimeLastEvalMs_.value(key, 0);
        auto openIt = dashboardRuntimeOpenPositions_.find(key);
        const bool evaluationDue = !(loopSeconds > 0 && lastMs > 0 && (nowMs - lastMs) < (loopSeconds * 1000));
        if (!evaluationDue && openIt == dashboardRuntimeOpenPositions_.end()) {
            touchWaitingEntry(key, nowMs);
            continue;
        }

        const auto *indicatorItem = dashboardOverridesTable_->item(row, 2);
        const QString indicatorSummary = indicatorItem ? indicatorItem->text() : QString();
        const auto *strategyControlsItem = dashboardOverridesTable_->item(row, 6);
        const QString strategySummary = strategyControlsItem ? strategyControlsItem->text() : QString();
        const bool useLiveSignalCandles = strategyUsesLiveCandles(strategySummary);
        QSet<QString> indicatorKeys = parseIndicatorKeysFromSummary(indicatorSummary);
        if (openIt != dashboardRuntimeOpenPositions_.end()) {
            const QString runtimeIndicatorKey = normalizedIndicatorKey(openIt.value().signalSource);
            if (!runtimeIndicatorKey.isEmpty() && runtimeIndicatorKey != QStringLiteral("generic")) {
                indicatorKeys.insert(runtimeIndicatorKey);
            }
        }
        const bool useRsi = indicatorKeys.contains(QStringLiteral("rsi"));
        const bool useStochRsi = indicatorKeys.contains(QStringLiteral("stoch_rsi"));
        const bool useWillr = indicatorKeys.contains(QStringLiteral("willr"));
        if (!useRsi && !useStochRsi && !useWillr) {
            continue;
        }

        QString intervalWarning;
        const QString requestInterval = normalizeBinanceKlineInterval(interval, &intervalWarning);
        if (!intervalWarning.isEmpty()) {
            const QString warningKey = QStringLiteral("%1|%2")
                                           .arg(interval.trimmed().toLower(), requestInterval.trimmed().toLower());
            if (!dashboardRuntimeIntervalWarnings_.contains(warningKey)) {
                dashboardRuntimeIntervalWarnings_.insert(warningKey);
                appendDashboardAllLog(intervalWarning);
            }
        }

        const bool indicatorUsesBinanceFutures = indicatorSourceKey == QStringLiteral("binance_futures");
        const bool indicatorUsesBinanceSpot = indicatorSourceKey == QStringLiteral("binance_spot");
        if (!indicatorUsesBinanceFutures && !indicatorUsesBinanceSpot) {
            const QString warningKey = QStringLiteral("indicator-source|unsupported|%1").arg(indicatorSourceKey);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Indicator source '%1' is not wired for C++ runtime signals yet. Select 'Binance futures' or 'Binance spot'.")
                        .arg(indicatorSourceText));
            }
            touchWaitingEntry(key, nowMs);
            continue;
        }
        if (indicatorUsesBinanceSpot && futures && !paperTrading) {
            const QString warningKey = QStringLiteral("indicator-source|spot-vs-futures-execution");
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    "Binance spot signal source selected: indicators use spot candles, but futures orders execute on Binance Futures "
                    "using the current futures price.");
            }
        }

        const QString signalKey = runtimeKeyFor(symbol, requestInterval, connectorToken);
        QVector<BinanceRestClient::KlineCandle> marketCandles;
        bool latestCandleClosed = false;
        if (useWebSocketFeed) {
            ensureSignalStreamForKey(
                signalKey,
                symbol,
                requestInterval,
                indicatorUsesBinanceFutures,
                rowConnectorCfg.baseUrl);
            marketCandles = dashboardRuntimeSignalCandles_.value(signalKey);
            latestCandleClosed = dashboardRuntimeSignalLastClosed_.value(signalKey, false);
            if (marketCandles.isEmpty()) {
                touchWaitingEntry(key, nowMs);
                continue;
            }
        } else {
            const auto candles = BinanceRestClient::fetchKlines(
                symbol,
                requestInterval,
                indicatorUsesBinanceFutures,
                isTestnet && indicatorUsesBinanceFutures,
                240,
                10000,
                rowConnectorCfg.baseUrl);
            if (!candles.ok || candles.candles.isEmpty()) {
                const QString intervalLabel = requestInterval.compare(interval, Qt::CaseInsensitive) == 0
                    ? interval
                    : QString("%1->%2").arg(interval, requestInterval);
                appendDashboardPositionLog(
                    QString("%1@%2 data fetch failed (%3): %4")
                        .arg(symbol, intervalLabel, rowConnectorText, candles.error));
                touchWaitingEntry(key, nowMs);
                continue;
            }
            marketCandles = candles.candles;
        }

        const QVector<BinanceRestClient::KlineCandle> signalCandles =
            signalCandlesFromSnapshot(marketCandles, useLiveSignalCandles, latestCandleClosed);
        if (signalCandles.isEmpty()) {
            touchWaitingEntry(key, nowMs);
            continue;
        }

        const double price = marketCandles.constLast().close;
        if (!qIsFinite(price) || price <= 0.0) {
            appendDashboardPositionLog(QString("%1@%2 skipped: invalid price data.").arg(symbol, interval));
            touchWaitingEntry(key, nowMs);
            continue;
        }

        const auto buildIndicatorRuntimeValues =
            [useRsi, useStochRsi, useWillr, &indicatorSettings](
                const QVector<BinanceRestClient::KlineCandle> &candles) -> IndicatorRuntimeValues {
            bool rsiOk = false;
            double rsi = 0.0;
            if (useRsi) {
                rsi = latestRsiValue(candles, indicatorSettings.rsiLength, &rsiOk);
            }

            bool stochRsiOk = false;
            double stochRsi = 0.0;
            if (useStochRsi) {
                stochRsi = latestStochRsiValue(
                    candles,
                    indicatorSettings.stochLength,
                    indicatorSettings.stochSmoothK,
                    indicatorSettings.stochSmoothD,
                    &stochRsiOk);
            }

            bool willrOk = false;
            double willr = 0.0;
            if (useWillr) {
                willr = latestWilliamsRValue(candles, indicatorSettings.willrLength, &willrOk);
            }

            return IndicatorRuntimeValues{
                useRsi,
                useStochRsi,
                useWillr,
                rsiOk,
                stochRsiOk,
                willrOk,
                rsi,
                stochRsi,
                willr,
            };
        };
        const IndicatorRuntimeValues indicatorValues = buildIndicatorRuntimeValues(signalCandles);
        const IndicatorRuntimeValues displayIndicatorValues =
            (signalCandles.size() == marketCandles.size())
            ? indicatorValues
            : buildIndicatorRuntimeValues(marketCandles);
        const QString indicatorValueSummary = formatIndicatorValueSummary(indicatorValues);
        if (openIt != dashboardRuntimeOpenPositions_.end() && !evaluationDue) {
            if (positionsTable_) {
                RuntimePosition &openPos = openIt.value();
                const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                const auto *livePos = pickLivePosition(liveSnapshot, symbol, openPos.side);
                if ((!qIsFinite(openPos.quantity) || openPos.quantity <= 1e-10)
                    && livePos
                    && qIsFinite(livePos->positionAmt)
                    && std::fabs(livePos->positionAmt) > 1e-10) {
                    openPos.quantity = std::fabs(livePos->positionAmt);
                    if (qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                        openPos.entryPrice = livePos->entryPrice;
                    }
                }

                const bool exchangePositionMissing = !paperTrading && liveSnapshot && liveSnapshot->ok && !livePos;
                const double rowQty = std::max(0.0, openPos.quantity);
                const QString exposureKey = QStringLiteral("%1|%2|%3")
                                                .arg(symbol,
                                                     openPos.side.trimmed().toUpper(),
                                                     connectorToken.toLower());
                const double groupQty = runtimeQtyByExposureKey.value(exposureKey, rowQty);
                const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                    ? livePos->markPrice
                    : price;
                const double fallbackPnlUsdt = (openPos.side == QStringLiteral("LONG"))
                    ? (markPrice - openPos.entryPrice) * rowQty
                    : (openPos.entryPrice - markPrice) * rowQty;
                const double fallbackMarginUsdt = std::max(
                    1e-9,
                    (openPos.entryPrice * rowQty) / std::max(1.0, openPos.leverage));
                const LivePositionMetricsShare liveShare = allocateLivePositionShare(
                    livePos,
                    rowQty,
                    groupQty,
                    std::max(0.0, rowQty * markPrice),
                    std::max(fallbackMarginUsdt, openPos.displayMarginUsdt),
                    std::max(fallbackMarginUsdt, openPos.roiBasisUsdt),
                    fallbackPnlUsdt);
                openPos.displayMarginUsdt = std::max(1e-9, liveShare.displayMarginUsdt);
                openPos.roiBasisUsdt = std::max(1e-9, liveShare.roiBasisUsdt);

                const double displayQty = rowQty;
                const double displaySizeUsdt = std::max(0.0, liveShare.sizeUsdt);
                const double displayMarginUsdt = openPos.displayMarginUsdt;
                const double displayPnlUsdt = liveShare.pnlUsdt;
                const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
                const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
                const int targetRow = findOpenPositionRow(positionsTable_, symbol, interval, rowConnectorCfg.key);

                if (targetRow >= 0) {
                    refreshActivePositionRow(
                        positionsTable_,
                        positionsCumulativeView_,
                        targetRow,
                        PositionTableActiveRowData{
                            symbol,
                            formatIndicatorValueSummaryForSource(displayIndicatorValues, openPos.signalSource),
                            displaySizeUsdt,
                            displayQty,
                            markPrice,
                            marginRatio,
                            liqPrice,
                            displayMarginUsdt,
                            displayPnlUsdt,
                            openPos.roiBasisUsdt,
                        });
                    positionsTableMutated = true;
                }
            }
            touchWaitingEntry(key, nowMs);
            continue;
        }

        dashboardRuntimeLastEvalMs_.insert(key, nowMs);

        const bool allowLong = strategyAllowsLong(strategySummary);
        const bool allowShort = strategyAllowsShort(strategySummary);
        if (!allowLong && !allowShort) {
            continue;
        }

        const auto *levItem = dashboardOverridesTable_->item(row, 4);
        bool levOk = false;
        double leverage = levItem ? levItem->text().toDouble(&levOk) : 0.0;
        if (!levOk || leverage <= 0.0) {
            leverage = dashboardLeverageSpin_ ? dashboardLeverageSpin_->value() : 1.0;
        }
        leverage = std::max(1.0, leverage);

        if (openIt == dashboardRuntimeOpenPositions_.end()) {
            const OpenSignalDecision openSignal = determineOpenSignal(
                indicatorValues,
                indicatorSettings,
                allowLong,
                allowShort);
            const QString openSide = openSignal.side;
            const QString triggerText = openSignal.triggerText;
            const QString triggerSource = openSignal.triggerSource;
            const QString rowIndicatorValueSummary =
                formatIndicatorValueSummaryForSource(displayIndicatorValues, triggerSource);

            if (!openSignal.hasSignal()) {
                // "No trigger yet" is a normal monitoring state, not a pending queue item.
                // Keeping these in waiting queue caused rows to stay Late indefinitely.
                continue;
            }

            if (!futures) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 signal ignored: runtime trading supports Futures only.")
                        .arg(openSide, symbol, interval));
                touchWaitingEntry(key, nowMs);
                continue;
            }
            if (!paperTrading && !hasApiCredentials) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 signal queued: API credentials are missing.")
                        .arg(openSide, symbol, interval));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            const QString filterCacheKey = QStringLiteral("%1|%2|%3")
                                               .arg(symbol, rowConnectorCfg.baseUrl, isTestnet ? QStringLiteral("testnet")
                                                                                                 : QStringLiteral("live"));
            BinanceRestClient::FuturesSymbolFilters symbolFilters = symbolFiltersCache.value(filterCacheKey);
            if (!symbolFilters.ok) {
                symbolFilters = BinanceRestClient::fetchFuturesSymbolFilters(
                    symbol,
                    isTestnet,
                    10000,
                    rowConnectorCfg.baseUrl);
                symbolFiltersCache.insert(filterCacheKey, symbolFilters);
            }
            if (!symbolFilters.ok) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked: symbol filters fetch failed (%4): %5")
                        .arg(openSide, symbol, interval, rowConnectorCfg.key, symbolFilters.error));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            double orderSizingPrice = price;
            if (!paperTrading) {
                const auto *tickerPrice = fetchExecutionTickerPrice(symbol, rowConnectorCfg);
                if (tickerPrice && tickerPrice->ok && qIsFinite(tickerPrice->price) && tickerPrice->price > 0.0) {
                    orderSizingPrice = tickerPrice->price;
                    if (std::fabs(orderSizingPrice - price) / std::max(price, 1e-12) >= 0.05) {
                        const QString warningKey = QStringLiteral("order-sizing-price|%1|%2")
                                                       .arg(symbol, rowConnectorCfg.key);
                        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                            dashboardRuntimeConnectorWarnings_.insert(warningKey);
                            appendDashboardPositionLog(
                                QString("%1 %2@%3 sizing uses current futures price %4 instead of signal close %5 (%6).")
                                    .arg(openSide,
                                         symbol,
                                         interval,
                                         QString::number(orderSizingPrice, 'f', 8),
                                         QString::number(price, 'f', 8),
                                         rowConnectorCfg.key));
                        }
                    }
                }
            }

            const double positionPct = dashboardPositionPctSpin_ ? dashboardPositionPctSpin_->value() : 2.0;
            const double targetNotionalUsdt = std::max(
                10.0,
                availableUsdt * (std::max(0.1, positionPct) / 100.0) * leverage);
            const double requestedQty = std::max(0.000001, targetNotionalUsdt / orderSizingPrice);
            double cappedRequestedQty = requestedQty;
            const double storedQtyCap = dashboardRuntimeOpenQtyCaps_.value(key, 0.0);
            if (qIsFinite(storedQtyCap) && storedQtyCap > 0.0) {
                cappedRequestedQty = std::min(cappedRequestedQty, storedQtyCap);
            }
            const double orderQty = normalizeFuturesOrderQuantity(cappedRequestedQty, orderSizingPrice, symbolFilters);
            if (!qIsFinite(orderQty) || orderQty <= 0.0) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked: normalized order quantity is invalid (requested=%4, sizingPrice=%5).")
                        .arg(openSide,
                             symbol,
                             interval,
                             QString::number(cappedRequestedQty, 'f', 8),
                             QString::number(orderSizingPrice, 'f', 8)));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            const QString openOrderSide = (openSide == QStringLiteral("LONG")) ? QStringLiteral("BUY") : QStringLiteral("SELL");
            const QString openPositionSide = hedgeMode ? openSide : QString();
            QString openOrderId;
            double filledQty = orderQty;
            double entryPrice = price;
            QString openOrderInfo;
            const BinanceRestClient::FuturesPosition *livePos = nullptr;
            if (paperTrading) {
                openOrderId = QStringLiteral("paper-open-%1").arg(QDateTime::currentMSecsSinceEpoch());
            } else {
                const auto openOrder = placeFuturesOpenOrderWithFallback(
                    apiKey,
                    apiSecret,
                    symbol,
                    openOrderSide,
                    orderQty,
                    isTestnet,
                    openPositionSide,
                    10000,
                    rowConnectorCfg.baseUrl);
                if (!openOrder.ok) {
                    if (isPercentPriceFilterError(openOrder.error)) {
                        double reducedQtyCap = orderQty * 0.5;
                        if (qIsFinite(symbolFilters.stepSize) && symbolFilters.stepSize > 0.0) {
                            reducedQtyCap = floorToOrderStep(
                                reducedQtyCap,
                                symbolFilters.stepSize,
                                symbolFilters.quantityPrecision);
                        }
                        const double minQtyCap = (qIsFinite(symbolFilters.minQty) && symbolFilters.minQty > 0.0)
                            ? symbolFilters.minQty
                            : (qIsFinite(symbolFilters.stepSize) && symbolFilters.stepSize > 0.0
                                   ? symbolFilters.stepSize
                                   : 0.0);
                        if (reducedQtyCap > 0.0) {
                            reducedQtyCap = std::max(minQtyCap, reducedQtyCap);
                            dashboardRuntimeOpenQtyCaps_.insert(key, reducedQtyCap);
                        }
                        const qint64 retryDelayMs = isTestnet ? 15000 : 5000;
                        dashboardRuntimeEntryRetryAfterMs_.insert(key, nowMs + retryDelayMs);
                        appendDashboardPositionLog(
                            QString("%1 %2@%3 entry delayed (%4): %5 Retrying with smaller size in %6s.")
                                .arg(openSide,
                                     symbol,
                                     interval,
                                     rowConnectorCfg.key,
                                     openOrder.error,
                                     QString::number(retryDelayMs / 1000)));
                    } else {
                        dashboardRuntimeOpenQtyCaps_.remove(key);
                        appendDashboardPositionLog(
                            QString("%1 %2@%3 order failed (%4): %5")
                                .arg(openSide, symbol, interval, rowConnectorCfg.key, openOrder.error));
                    }
                    touchWaitingEntry(key, nowMs);
                    continue;
                }

                openOrderId = openOrder.orderId;
                openOrderInfo = openOrder.error;
                filledQty = (qIsFinite(openOrder.executedQty) && openOrder.executedQty > 0.0)
                    ? openOrder.executedQty
                    : orderQty;
                dashboardRuntimeEntryRetryAfterMs_.remove(key);
                if (!openOrderInfo.trimmed().isEmpty() && isPercentPriceFilterError(openOrderInfo)) {
                    dashboardRuntimeOpenQtyCaps_.insert(key, std::max(filledQty, 0.0));
                } else {
                    dashboardRuntimeOpenQtyCaps_.remove(key);
                }
                entryPrice = (qIsFinite(openOrder.avgPrice) && openOrder.avgPrice > 0.0)
                    ? openOrder.avgPrice
                    : price;
                livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
                const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                livePos = pickLivePosition(liveSnapshot, symbol, openSide);
                if (livePos && qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                    entryPrice = livePos->entryPrice;
                }
            }
            double rowQty = filledQty;
            if ((!qIsFinite(rowQty) || rowQty <= 1e-10)
                && livePos
                && qIsFinite(livePos->positionAmt)
                && std::fabs(livePos->positionAmt) > 1e-10) {
                rowQty = std::fabs(livePos->positionAmt);
            }
            const QString exposureKey = QStringLiteral("%1|%2|%3")
                                            .arg(symbol,
                                                 openSide,
                                                 connectorToken.toLower());
            const double existingGroupQty = runtimeQtyByExposureKey.value(exposureKey, 0.0);
            const double groupQty = existingGroupQty + std::max(0.0, rowQty);
            const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                ? livePos->markPrice
                : price;
            const double fallbackMarginUsdt = std::max(0.0, (entryPrice * rowQty) / leverage);
            const LivePositionMetricsShare liveShare = allocateLivePositionShare(
                livePos,
                rowQty,
                groupQty,
                std::max(0.0, rowQty * markPrice),
                fallbackMarginUsdt,
                fallbackMarginUsdt,
                0.0);
            const double sizeUsdt = std::max(0.0, liveShare.sizeUsdt);
            const double displayMarginUsdt = std::max(0.0, liveShare.displayMarginUsdt);
            const double roiBasisUsdt = std::max(1e-9, liveShare.roiBasisUsdt);
            const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
            const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
            dashboardRuntimeOpenPositions_.insert(
                key,
                RuntimePosition{
                    openSide,
                    interval,
                    triggerSource,
                    rowConnectorCfg.key,
                    rowConnectorCfg.baseUrl,
                    entryPrice,
                    rowQty,
                    leverage,
                    roiBasisUsdt,
                    displayMarginUsdt,
                });
            runtimeQtyByExposureKey[exposureKey] = groupQty;

            if (positionsTable_) {
                if (appendOpenPositionRow(
                        positionsTable_,
                        positionsRowSequenceCounter_,
                        PositionTableOpenRowData{
                            symbol,
                            interval,
                            triggerSource,
                            triggerText,
                            rowIndicatorValueSummary,
                            openSide,
                            QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
                            dashboardOverridesTable_->item(row, 7)
                                ? dashboardOverridesTable_->item(row, 7)->text()
                                : QStringLiteral("Disabled"),
                            rowConnectorCfg.key,
                            openOrderId,
                            sizeUsdt,
                            rowQty,
                            markPrice,
                            marginRatio,
                            liqPrice,
                            displayMarginUsdt,
                            roiBasisUsdt,
                        })) {
                    positionsTableStructureChanged = true;
                    positionsTableMutated = true;
                }
            }
            applyCumulativeViewImmediately();
            appendDashboardPositionLog(
                QString("%1 %2@%3 opened at %4 qty=%5 (%6, values: %7, connector=%8, orderId=%9%10)")
                    .arg(openSide,
                         symbol,
                         interval,
                         QString::number(entryPrice, 'f', 6),
                         QString::number(rowQty, 'f', 6),
                         triggerText,
                         indicatorValueSummary,
                         rowConnectorCfg.key,
                         openOrderId,
                         openOrderInfo.trimmed().isEmpty() ? QString() : QStringLiteral(", note=%1").arg(openOrderInfo.trimmed())));
            continue;
        }

        RuntimePosition &openPos = openIt.value();
        const QString signalSource = openPos.signalSource.trimmed().toLower();
        const bool shouldCloseLong = (openPos.side == "LONG")
            && TradingBotWindowDashboardRuntimeDetail::shouldCloseBySource(
                signalSource,
                true,
                indicatorValues,
                indicatorSettings);
        const bool shouldCloseShort = (openPos.side == "SHORT")
            && TradingBotWindowDashboardRuntimeDetail::shouldCloseBySource(
                signalSource,
                false,
                indicatorValues,
                indicatorSettings);
        const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
        const auto *livePos = pickLivePosition(liveSnapshot, symbol, openPos.side);
        if ((!qIsFinite(openPos.quantity) || openPos.quantity <= 1e-10)
            && livePos
            && qIsFinite(livePos->positionAmt)
            && std::fabs(livePos->positionAmt) > 1e-10) {
            openPos.quantity = std::fabs(livePos->positionAmt);
            if (qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                openPos.entryPrice = livePos->entryPrice;
            }
        }
        const double rowQty = std::max(0.0, openPos.quantity);
        const QString exposureKey = QStringLiteral("%1|%2|%3")
                                        .arg(symbol,
                                             openPos.side.trimmed().toUpper(),
                                             connectorToken.toLower());
        const double groupQty = runtimeQtyByExposureKey.value(exposureKey, rowQty);
        const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
            ? livePos->markPrice
            : price;
        const double fallbackPnlUsdt = (openPos.side == QStringLiteral("LONG"))
            ? (markPrice - openPos.entryPrice) * rowQty
            : (openPos.entryPrice - markPrice) * rowQty;
        const double fallbackMarginUsdt = std::max(
            1e-9,
            (openPos.entryPrice * rowQty) / std::max(1.0, openPos.leverage));
        const LivePositionMetricsShare liveShare = allocateLivePositionShare(
            livePos,
            rowQty,
            groupQty,
            std::max(0.0, rowQty * markPrice),
            std::max(fallbackMarginUsdt, openPos.displayMarginUsdt),
            std::max(fallbackMarginUsdt, openPos.roiBasisUsdt),
            fallbackPnlUsdt);
        openPos.displayMarginUsdt = std::max(1e-9, liveShare.displayMarginUsdt);
        openPos.roiBasisUsdt = std::max(1e-9, liveShare.roiBasisUsdt);
        const double displayQty = rowQty;
        const double displayPnlUsdt = liveShare.pnlUsdt;
        const double displaySizeUsdt = std::max(0.0, liveShare.sizeUsdt);
        const double displayMarginUsdt = openPos.displayMarginUsdt;
        const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
        const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
        const int targetRow = findOpenPositionRow(positionsTable_, symbol, interval, rowConnectorCfg.key);

        if (targetRow >= 0 && positionsTable_) {
            refreshActivePositionRow(
                positionsTable_,
                positionsCumulativeView_,
                targetRow,
                PositionTableActiveRowData{
                    symbol,
                    formatIndicatorValueSummaryForSource(displayIndicatorValues, openPos.signalSource),
                    displaySizeUsdt,
                    displayQty,
                    markPrice,
                    marginRatio,
                    liqPrice,
                    displayMarginUsdt,
                    displayPnlUsdt,
                    openPos.roiBasisUsdt,
                });
            positionsTableMutated = true;
        }

        if (!shouldCloseLong && !shouldCloseShort) {
            continue;
        }

        if (!futures || (!paperTrading && !hasApiCredentials)) {
            appendDashboardPositionLog(
                QString("%1 %2@%3 close signal deferred: %4.")
                    .arg(openPos.side,
                         symbol,
                         interval,
                         !futures ? QStringLiteral("Futures mode is required")
                                  : QStringLiteral("missing API credentials")));
            continue;
        }

        const QString closeOrderSide = (openPos.side == QStringLiteral("LONG")) ? QStringLiteral("SELL")
                                                                                 : QStringLiteral("BUY");
        const QString closePositionSide = hedgeMode ? openPos.side : QString();
        const bool closeReduceOnly = !hedgeMode;
        QString closeOrderId;
        QString closeOrderError;
        double closePrice = price;
        double closeQty = openPos.quantity;
        if (paperTrading) {
            closeOrderId = QStringLiteral("paper-close-%1").arg(QDateTime::currentMSecsSinceEpoch());
        } else {
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
                rowConnectorCfg.baseUrl,
                price);
            if (!closeOrder.ok) {
                if (isReduceOnlyRejectedError(closeOrder.error)) {
                    livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
                    const auto *latestSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                    if (!hasMatchingOpenFuturesPosition(latestSnapshot, symbol, openPos.side, hedgeMode)) {
                        if (targetRow >= 0 && positionsTable_) {
                            markPositionClosedRow(
                                positionsTable_,
                                positionsCumulativeView_,
                                targetRow,
                                QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
                            positionsTableMutated = true;
                        }
                        applyCumulativeViewImmediately();
                        appendDashboardPositionLog(
                            QString("%1 %2@%3 close confirmed (%4): position is already flat on exchange.")
                                .arg(openPos.side, symbol, interval, rowConnectorCfg.key));
                        dashboardRuntimeLastEvalMs_.remove(key);
                        dashboardRuntimeEntryRetryAfterMs_.remove(key);
                        dashboardRuntimeOpenQtyCaps_.remove(key);
                        dashboardRuntimeOpenPositions_.remove(key);
                        continue;
                    }
                }
                appendDashboardPositionLog(
                    QString("%1 %2@%3 close order failed (%4): %5")
                        .arg(openPos.side, symbol, interval, rowConnectorCfg.key, closeOrder.error));
                continue;
            }
            livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
            closeOrderId = closeOrder.orderId;
            closeOrderError = closeOrder.error;
            closePrice = (qIsFinite(closeOrder.avgPrice) && closeOrder.avgPrice > 0.0)
                ? closeOrder.avgPrice
                : price;
            closeQty = (qIsFinite(closeOrder.executedQty) && closeOrder.executedQty > 0.0)
                ? closeOrder.executedQty
                : openPos.quantity;
        }
        const double effectiveCloseQty = std::max(0.0, std::min(openPos.quantity, closeQty));
        if (effectiveCloseQty <= 0.0) {
            appendDashboardPositionLog(
                QString("%1 %2@%3 close order returned zero fill; keeping position open.")
                    .arg(openPos.side, symbol, interval));
            continue;
        }
        const double realizedPnlUsdt = (openPos.side == "LONG")
            ? (closePrice - openPos.entryPrice) * effectiveCloseQty
            : (openPos.entryPrice - closePrice) * effectiveCloseQty;
        const double closeShareRatio = rowQty > 1e-9
            ? std::min(1.0, std::max(0.0, effectiveCloseQty / rowQty))
            : 1.0;
        const double closeRoiBasisUsed = std::max(1e-9, openPos.roiBasisUsdt * closeShareRatio);
        const double realizedPnlPct = (realizedPnlUsdt / closeRoiBasisUsed) * 100.0;
        const bool partialClose = (effectiveCloseQty + 1e-9) < openPos.quantity;
        double remainingQty = 0.0;
        double remainingNotional = 0.0;
        double remainingDisplayMarginUsdt = 0.0;
        double remainingRoiBasisUsdt = 0.0;

        if (partialClose) {
            remainingQty = std::max(0.0, openPos.quantity - effectiveCloseQty);
            const double remainingRatio = rowQty > 1e-9
                ? std::min(1.0, std::max(0.0, remainingQty / rowQty))
                : 0.0;
            remainingNotional = std::max(0.0, remainingQty * closePrice);
            remainingDisplayMarginUsdt = std::max(0.0, openPos.displayMarginUsdt * remainingRatio);
            remainingRoiBasisUsdt = std::max(0.0, openPos.roiBasisUsdt * remainingRatio);
            openPos.displayMarginUsdt = std::max(1e-9, remainingDisplayMarginUsdt);
            openPos.roiBasisUsdt = std::max(1e-9, remainingRoiBasisUsdt);
        }

        if (targetRow >= 0 && positionsTable_) {
            applyCloseToPositionRow(
                positionsTable_,
                positionsCumulativeView_,
                targetRow,
                PositionTableCloseRowData{
                    symbol,
                    QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
                    closePrice,
                    realizedPnlUsdt,
                    realizedPnlPct,
                    closeRoiBasisUsed,
                    partialClose,
                    remainingQty,
                    remainingNotional,
                    remainingDisplayMarginUsdt,
                    remainingRoiBasisUsdt,
                });
            positionsTableMutated = true;
        }
        applyCumulativeViewImmediately();

        if (partialClose) {
            openPos.quantity = std::max(0.0, openPos.quantity - effectiveCloseQty);
            if (openPos.quantity <= 1e-9) {
                openPos.quantity = 0.0;
            }
            appendDashboardPositionLog(
                QString("%1 %2@%3 partially closed at %4, qty=%5 remaining=%6, PNL=%7 USDT (%8%%), connector=%9, orderId=%10: %11")
                    .arg(openPos.side,
                         symbol,
                         interval,
                         QString::number(closePrice, 'f', 6),
                         QString::number(effectiveCloseQty, 'f', 6),
                         QString::number(openPos.quantity, 'f', 6),
                         QString::number(realizedPnlUsdt, 'f', 2),
                         QString::number(realizedPnlPct, 'f', 2),
                         rowConnectorCfg.key,
                         closeOrderId,
                         closeOrderError.isEmpty() ? QStringLiteral("remaining exposure still open")
                                                   : closeOrderError));
            continue;
        }

        appendDashboardPositionLog(
            QString("%1 %2@%3 closed at %4, PNL=%5 USDT (%6%%), connector=%7, orderId=%8")
                .arg(openPos.side,
                     symbol,
                     interval,
                     QString::number(closePrice, 'f', 6),
                     QString::number(realizedPnlUsdt, 'f', 2),
                     QString::number(realizedPnlPct, 'f', 2),
                     rowConnectorCfg.key,
                     closeOrderId));
        dashboardRuntimeLastEvalMs_.remove(key);
        dashboardRuntimeEntryRetryAfterMs_.remove(key);
        dashboardRuntimeOpenQtyCaps_.remove(key);
        dashboardRuntimeOpenPositions_.remove(key);
    }

    if (!dashboardWaitingActiveEntries_.isEmpty()) {
        const QList<QString> activeKeys = dashboardWaitingActiveEntries_.keys();
        for (const QString &activeKey : activeKeys) {
            if (waitingSeenThisCycle.contains(activeKey)) {
                continue;
            }
            QVariantMap endedEntry = dashboardWaitingActiveEntries_.take(activeKey);
            qint64 firstSeenMs = endedEntry.value(QStringLiteral("first_seen_ms")).toLongLong();
            if (firstSeenMs <= 0) {
                firstSeenMs = cycleNowMs;
            }
            const qint64 elapsedMs = std::max<qint64>(0, cycleNowMs - firstSeenMs);
            endedEntry.insert(QStringLiteral("first_seen_ms"), firstSeenMs);
            endedEntry.insert(QStringLiteral("updated_ms"), cycleNowMs);
            endedEntry.insert(QStringLiteral("ended_at_ms"), cycleNowMs);
            endedEntry.insert(QStringLiteral("age"), static_cast<double>(elapsedMs) / 1000.0);
            endedEntry.insert(QStringLiteral("age_seconds"), static_cast<int>(elapsedMs / 1000));
            endedEntry.insert(QStringLiteral("state"), QStringLiteral("Ended"));
            dashboardWaitingHistoryEntries_.append(endedEntry);
        }
    }
    if (dashboardWaitingHistoryEntries_.size() > dashboardWaitingHistoryMax_) {
        const int extra = dashboardWaitingHistoryEntries_.size() - dashboardWaitingHistoryMax_;
        dashboardWaitingHistoryEntries_.erase(
            dashboardWaitingHistoryEntries_.begin(),
            dashboardWaitingHistoryEntries_.begin() + extra);
    }

    if (paperTrading || !futures || !hasApiCredentials) {
        positionsLiveActivePnlValid_ = false;
        positionsLiveActivePnlUpdatedMs_ = 0;
        positionsLiveActivePnlUsdt_ = 0.0;
        positionsLiveActivePnlContextKey_.clear();
    } else {
        bool anyLiveSnapshotOk = false;
        double aggregatedLiveActivePnl = 0.0;
        for (auto it = livePositionsCache.cbegin(); it != livePositionsCache.cend(); ++it) {
            if (!it.value().ok) {
                continue;
            }
            anyLiveSnapshotOk = true;
            aggregatedLiveActivePnl += sumSnapshotActivePnl(it.value());
        }
        if (anyLiveSnapshotOk) {
            positionsLiveActivePnlContextKey_ = liveActivePnlContextKey;
            positionsLiveActivePnlUsdt_ = aggregatedLiveActivePnl;
            positionsLiveActivePnlUpdatedMs_ = QDateTime::currentMSecsSinceEpoch();
            positionsLiveActivePnlValid_ = true;
        } else if (dashboardRuntimeOpenPositions_.isEmpty()) {
            positionsLiveActivePnlContextKey_ = liveActivePnlContextKey;
            positionsLiveActivePnlUsdt_ = 0.0;
            positionsLiveActivePnlUpdatedMs_ = QDateTime::currentMSecsSinceEpoch();
            positionsLiveActivePnlValid_ = true;
        }
    }

    refreshDashboardWaitingQueueTable();

    flushPendingPositionsView();
    refreshPositionsSummaryLabels();
}


