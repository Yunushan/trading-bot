#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "BinanceWsClient.h"
#include "NativeIndicatorRuntime.h"
#include "NativeOrderSafety.h"
#include "NativeStrategyRuntime.h"
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
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QMessageBox>
#include <QVector>
#include <QRegularExpression>
#include <QPushButton>
#include <QSet>
#include <QTableWidget>
#include <QTextEdit>
#include <QTimer>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>


using namespace TradingBotWindowDashboardRuntime;
using namespace TradingBotWindowDashboardRuntimeDetail;
using ConnectorRuntimeConfig = TradingBotWindowSupport::ConnectorRuntimeConfig;

namespace {

QVector<NativeIndicatorRuntime::Candle> toNativeIndicatorCandles(
    const QVector<BinanceRestClient::KlineCandle> &candles
) {
    QVector<NativeIndicatorRuntime::Candle> result;
    result.reserve(candles.size());
    for (const BinanceRestClient::KlineCandle &candle : candles) {
        result.push_back({
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
        });
    }
    return result;
}

NativeIndicatorRuntime::ConfigMap nativeIndicatorConfigsForKeys(
    const QSet<QString> &indicatorKeys,
    const QMap<QString, QVariantMap> &indicatorParams
) {
    NativeIndicatorRuntime::ConfigMap configs;
    for (const QString &key : indicatorKeys) {
        QJsonObject config = QJsonObject::fromVariantMap(indicatorParams.value(key));
        config.insert(QStringLiteral("enabled"), true);
        configs.insert(key, config);
    }
    return configs;
}

std::optional<double> optionalIndicatorThreshold(
    const QVariantMap &config,
    const QString &key
) {
    if (!config.contains(key) || config.value(key).isNull()) {
        return std::nullopt;
    }
    bool ok = false;
    const double value = config.value(key).toDouble(&ok);
    return ok && std::isfinite(value) ? std::optional<double>(value) : std::nullopt;
}

NativeStrategyRuntime::StrategySignalInput nativeSignalInput(
    const QVector<NativeIndicatorRuntime::Candle> &candles,
    const NativeIndicatorRuntime::ConfigMap &configs,
    const QMap<QString, QVariantMap> &indicatorParams,
    const QString &side,
    bool useLiveValues
) {
    NativeStrategyRuntime::StrategySignalInput input;
    input.side = side;
    // Closed-candle mode removes the incomplete candle before this conversion.
    input.useLiveValues = useLiveValues;
    input.indicators = NativeIndicatorRuntime::computeConfiguredSeries(candles, configs);
    input.closes.reserve(candles.size());
    for (const NativeIndicatorRuntime::Candle &candle : candles) {
        input.closes.push_back(candle.close);
    }
    for (auto iterator = configs.cbegin(); iterator != configs.cend(); ++iterator) {
        const QVariantMap config = indicatorParams.value(iterator.key());
        input.rules.insert(iterator.key(), NativeStrategyRuntime::IndicatorRule{
            true,
            optionalIndicatorThreshold(config, QStringLiteral("buy_value")),
            optionalIndicatorThreshold(config, QStringLiteral("sell_value")),
        });
    }
    return input;
}

QString signalSideForAllowedDirections(bool allowLong, bool allowShort) {
    if (allowLong && allowShort) {
        return QStringLiteral("BOTH");
    }
    return allowLong ? QStringLiteral("BUY") : QStringLiteral("SELL");
}

QString firstDecisionSource(const QJsonObject &decision) {
    const QJsonArray sources = decision.value(QStringLiteral("trigger_sources")).toArray();
    return sources.isEmpty() ? QStringLiteral("generic") : sources.first().toString();
}

QStringList normalizedSignalSources(const QStringList &rawSources) {
    QStringList sources;
    QSet<QString> seen;
    for (const QString &rawSource : rawSources) {
        const QString source = normalizedIndicatorKey(rawSource);
        if (source.isEmpty() || source == QStringLiteral("generic") || seen.contains(source)) {
            continue;
        }
        seen.insert(source);
        sources.append(source);
    }
    return sources;
}

QStringList decisionSignalSources(const QJsonObject &decision) {
    QStringList rawSources;
    const QJsonArray sources = decision.value(QStringLiteral("trigger_sources")).toArray();
    for (const QJsonValue &source : sources) {
        rawSources.append(source.toString());
    }
    return normalizedSignalSources(rawSources);
}

QString primaryOutputKey(const QString &indicatorKey) {
    static const QMap<QString, QString> outputOverrides = {
        {QStringLiteral("bb"), QStringLiteral("bb_mid")},
        {QStringLiteral("keltner"), QStringLiteral("keltner_mid")},
        {QStringLiteral("stoch_rsi"), QStringLiteral("stoch_rsi_k")},
        {QStringLiteral("macd"), QStringLiteral("macd_line")},
        {QStringLiteral("stochastic"), QStringLiteral("stochastic_k")},
    };
    return outputOverrides.value(indicatorKey, indicatorKey);
}

QString formatNativeIndicatorSummary(
    const NativeIndicatorRuntime::SeriesMap &series,
    const QSet<QString> &indicatorKeys
) {
    QStringList parts;
    QStringList sortedKeys = indicatorKeys.values();
    sortedKeys.sort();
    for (const QString &indicatorKey : sortedKeys) {
        const NativeIndicatorRuntime::Series values = series.value(primaryOutputKey(indicatorKey));
        auto iterator = values.crbegin();
        while (iterator != values.crend() && !std::isfinite(*iterator)) {
            ++iterator;
        }
        if (iterator == values.crend()) {
            continue;
        }
        parts.push_back(
            QStringLiteral("%1 %2")
                .arg(indicatorKey.toUpper(), QString::number(*iterator, 'f', 2)));
        if (parts.size() >= 8) {
            break;
        }
    }
    return parts.isEmpty() ? QStringLiteral("-") : parts.join(QStringLiteral(" | "));
}

} // namespace

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
        QSet<QString> displayIndicatorKeys;
        if (sourceKey == QStringLiteral("generic")) {
            displayIndicatorKeys = {
                QStringLiteral("rsi"),
                QStringLiteral("stoch_rsi"),
                QStringLiteral("willr"),
            };
        } else if (!sourceKey.isEmpty()) {
            displayIndicatorKeys.insert(sourceKey);
        }
        const NativeIndicatorRuntime::ConfigMap displayConfigs =
            nativeIndicatorConfigsForKeys(displayIndicatorKeys, dashboardIndicatorParams_);
        const NativeIndicatorRuntime::SeriesMap displaySeries =
            NativeIndicatorRuntime::computeConfiguredSeries(
                toNativeIndicatorCandles(marketCandles),
                displayConfigs);

        const int targetRow = findOpenPositionRow(positionsTable_, symbol, openPos.interval, openPos.connectorKey);
        if (targetRow < 0) {
            continue;
        }

        setPositionIndicatorValueSummary(
            positionsTable_,
            positionsCumulativeView_,
            targetRow,
            formatNativeIndicatorSummary(displaySeries, displayIndicatorKeys));
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
    if (dashboardServiceRuntimeActive_) {
        runDashboardServiceRuntimeCycle();
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
    QSet<QString> accountStopLossConnectors;
    const qint64 cycleNowMs = QDateTime::currentMSecsSinceEpoch();
    const QJsonObject executionDefaults = TradingBotWindowSupport::pythonSourceDefaultExecutionConfig();
    const QJsonObject effectiveDashboardConfig = buildDashboardServiceConfigPatch();
    const QString defaultAccountType = executionDefaults.value(QStringLiteral("account_type")).toString(QStringLiteral("Futures"));
    const QString defaultMode = executionDefaults.value(QStringLiteral("mode")).toString(QStringLiteral("Demo/Testnet"));
    const QString defaultIndicatorSource = executionDefaults.value(QStringLiteral("indicator_source")).toString(QStringLiteral("Binance futures"));
    const QString defaultPositionMode = executionDefaults.value(QStringLiteral("position_mode")).toString(QStringLiteral("Hedge"));

    const bool futures = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith("fut")
        : defaultAccountType.trimmed().toLower().startsWith("fut");
    const QString modeText = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : defaultMode;
    const bool paperTrading = TradingBotWindowSupport::isPaperTradingModeLabel(modeText);
    const bool isTestnet = TradingBotWindowSupport::isTestnetModeLabel(modeText);
    const QString indicatorSourceText = dashboardIndicatorSourceCombo_
        ? dashboardIndicatorSourceCombo_->currentText().trimmed()
        : defaultIndicatorSource;
    const QString indicatorSourceKey = normalizedIndicatorSourceKey(indicatorSourceText);
    // Python does not expose a separate signal-feed setting. Its native
    // connector enables this path only through the two environment flags.
    const bool websocketFeedRequested = pythonSourceUseWebSocketFeed(indicatorSourceText, isTestnet);
    const bool useWebSocketFeed = websocketFeedRequested;
    const bool signalDataTestnet = pythonSourceIndicatorDataUsesTestnet(indicatorSourceText, isTestnet);
    const int lookback = dashboardLookbackSpin_
        ? dashboardLookbackSpin_->value()
        : executionDefaults.value(QStringLiteral("lookback")).toInt(200);
    const QString defaultConnectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : TradingBotWindowSupport::connectorLabelForKey(TradingBotWindowSupport::recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig defaultConnectorCfg = TradingBotWindowSupport::resolveConnectorConfig(defaultConnectorText, futures);
    double availableUsdt = currentDashboardPaperBalanceUsdt();
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const bool hasApiCredentials = !apiKey.isEmpty() && !apiSecret.isEmpty();
    const bool hedgeMode = dashboardPositionModeCombo_
        ? dashboardPositionModeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("hedge"))
        : defaultPositionMode.trimmed().toLower().startsWith(QStringLiteral("hedge"));
    const QString liveActivePnlContextKey = QStringLiteral("%1|%2|%3")
                                                .arg(apiKey.trimmed(),
                                                     dashboardAccountTypeCombo_
                                                         ? dashboardAccountTypeCombo_->currentText().trimmed().toLower()
                                                         : defaultAccountType.trimmed().toLower(),
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
        [futures, isTestnet, &tickerPriceCache, &tickerCacheKeyFor](
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
                    futures,
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
    const auto positionMarginUsdt = [](const BinanceRestClient::FuturesPosition &position) {
        double margin = 0.0;
        if (qIsFinite(position.positionInitialMargin) && position.positionInitialMargin > 0.0) {
            margin += position.positionInitialMargin;
        }
        if (qIsFinite(position.openOrderMargin) && position.openOrderMargin > 0.0) {
            margin += position.openOrderMargin;
        }
        if (margin <= 0.0 && qIsFinite(position.initialMargin) && position.initialMargin > 0.0) {
            margin = position.initialMargin;
        }
        if (margin <= 0.0 && qIsFinite(position.isolatedMargin) && position.isolatedMargin > 0.0) {
            margin = position.isolatedMargin;
        }
        if (margin <= 0.0 && qIsFinite(position.notional) && std::fabs(position.notional) > 0.0
            && qIsFinite(position.leverage) && position.leverage > 0.0) {
            margin = std::fabs(position.notional) / std::max(1.0, position.leverage);
        }
        if (margin <= 0.0 && qIsFinite(position.positionAmt) && std::fabs(position.positionAmt) > 0.0
            && qIsFinite(position.entryPrice) && position.entryPrice > 0.0
            && qIsFinite(position.leverage) && position.leverage > 0.0) {
            margin = (std::fabs(position.positionAmt) * position.entryPrice)
                / std::max(1.0, position.leverage);
        }
        return qIsFinite(margin) ? std::max(0.0, margin) : 0.0;
    };
    const auto positionSideForExposure = [](const BinanceRestClient::FuturesPosition &position) {
        const QString explicitSide = position.positionSide.trimmed().toUpper();
        if (explicitSide == QStringLiteral("LONG") || explicitSide == QStringLiteral("SHORT")) {
            return explicitSide;
        }
        if (qIsFinite(position.positionAmt) && position.positionAmt > 0.0) {
            return QStringLiteral("LONG");
        }
        if (qIsFinite(position.positionAmt) && position.positionAmt < 0.0) {
            return QStringLiteral("SHORT");
        }
        return QString();
    };
    const auto trackedPositionMarginUsdt = [](const RuntimePosition &position) {
        if (qIsFinite(position.displayMarginUsdt) && position.displayMarginUsdt > 0.0) {
            return position.displayMarginUsdt;
        }
        if (qIsFinite(position.entryPrice) && position.entryPrice > 0.0
            && qIsFinite(position.quantity) && position.quantity > 0.0
            && qIsFinite(position.leverage) && position.leverage > 0.0) {
            return (position.entryPrice * position.quantity) / std::max(1.0, position.leverage);
        }
        return 0.0;
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
        [this, useWebSocketFeed, signalDataTestnet, lookback]
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
                signalDataTestnet,
                lookback,
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
        connect(client, &BinanceWsClient::kline, this, [this, signalKey, symbolKey, intervalKey, lookback](
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
                if (cache.size() > lookback) {
                    cache.remove(0, cache.size() - lookback);
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
        client->connectKline(symbol, requestInterval, signalUsesFutures, signalDataTestnet);
        return dashboardRuntimeSignalCandles_.contains(signalKey)
            && !dashboardRuntimeSignalCandles_.value(signalKey).isEmpty();
    };

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
            static QString s_balanceCacheAsset = QStringLiteral("USDT");

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
                positionsBalanceAsset_ = s_balanceCacheAsset;
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
                        (balance.totalBalance > 0.0) ? balance.totalBalance : balance.totalUsdtBalance);
                    const double availableBalance = std::max(
                        0.0,
                        (balance.availableBalance > 0.0) ? balance.availableBalance : totalBalance);
                    positionsBalanceAsset_ = balance.asset.trimmed().isEmpty()
                        ? QStringLiteral("USDT")
                        : balance.asset.trimmed().toUpper();
                    s_balanceCacheKey = balanceCacheKey;
                    s_balanceCacheMs = nowMs;
                    s_balanceCacheValid = true;
                    s_balanceCacheTotal = totalBalance;
                    s_balanceCacheAvailable = availableBalance;
                    s_balanceCacheAsset = positionsBalanceAsset_;
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
        const QJsonObject rowPayload = symbolItem->data(Qt::UserRole).toJsonObject();
        const QJsonObject rowStrategyControls = rowPayload.value(QStringLiteral("strategy_controls")).toObject();
        const QJsonObject normalizedStrategyControls =
            NativeStrategyRuntime::normalizeStrategyControls(QStringLiteral("runtime"), rowStrategyControls);
        QJsonObject effectiveRiskInput = effectiveDashboardConfig;
        for (auto riskIt = rowStrategyControls.constBegin(); riskIt != rowStrategyControls.constEnd(); ++riskIt) {
            effectiveRiskInput.insert(riskIt.key(), riskIt.value());
        }
        const QJsonObject normalizedRiskControls =
            NativeStrategyRuntime::normalizeStrategyRiskControls(effectiveRiskInput);
        const bool useLiveSignalCandles = normalizedRiskControls.value(QStringLiteral("indicator_use_live_values"))
                                              .toBool(strategyUsesLiveCandles(strategySummary));
        QSet<QString> indicatorKeys = parseIndicatorKeysFromSummary(indicatorSummary);
        if (openIt != dashboardRuntimeOpenPositions_.end()) {
            const RuntimePosition &runtimePosition = openIt.value();
            QStringList runtimeSources = runtimePosition.signalSources;
            if (runtimeSources.isEmpty()) {
                runtimeSources.append(runtimePosition.signalSource);
            }
            for (const QString &runtimeSource : normalizedSignalSources(runtimeSources)) {
                indicatorKeys.insert(runtimeSource);
            }
        }
        if (indicatorKeys.isEmpty()) {
            continue;
        }
        const NativeIndicatorRuntime::ConfigMap nativeConfigs =
            nativeIndicatorConfigsForKeys(indicatorKeys, dashboardIndicatorParams_);
        const QStringList unsupportedIndicatorKeys =
            NativeIndicatorRuntime::unsupportedEnabledIndicatorKeys(nativeConfigs);
        if (!unsupportedIndicatorKeys.isEmpty()) {
            const QString warningKey = QStringLiteral("unsupported-indicators|%1")
                                           .arg(unsupportedIndicatorKeys.join(QLatin1Char(',')));
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QStringLiteral("Native C++ runtime skipped unsupported indicators: %1")
                        .arg(unsupportedIndicatorKeys.join(QStringLiteral(", "))));
            }
            touchWaitingEntry(key, nowMs);
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

        const QString indicatorMarketFamily = nativeIndicatorMarketFamily(indicatorSourceText);
        const bool indicatorUsesBinanceFutures = indicatorMarketFamily == QStringLiteral("usd-m-futures");
        const bool indicatorUsesBinanceSpot = indicatorMarketFamily == QStringLiteral("spot");
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
                signalDataTestnet,
                lookback,
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

        const QVector<NativeIndicatorRuntime::Candle> nativeSignalCandles =
            toNativeIndicatorCandles(signalCandles);
        const NativeStrategyRuntime::StrategySignalInput fullSignalInput = nativeSignalInput(
            nativeSignalCandles,
            nativeConfigs,
            dashboardIndicatorParams_,
            QStringLiteral("BOTH"),
            useLiveSignalCandles);
        const NativeIndicatorRuntime::SeriesMap displayIndicatorSeries =
            signalCandles.size() == marketCandles.size()
            ? fullSignalInput.indicators
            : NativeIndicatorRuntime::computeConfiguredSeries(
                  toNativeIndicatorCandles(marketCandles),
                  nativeConfigs);
        const QString indicatorValueSummary =
            formatNativeIndicatorSummary(fullSignalInput.indicators, indicatorKeys);
        const QString displayIndicatorValueSummary =
            formatNativeIndicatorSummary(displayIndicatorSeries, indicatorKeys);
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

                const bool exchangePositionMissing = futures && !paperTrading && liveSnapshot && liveSnapshot->ok && !livePos;
                const QString purgeKey = key;
                if (!exchangePositionMissing) {
                    dashboardRuntimeFlatPurgeMissCounts_.remove(purgeKey);
                } else {
                    double purgeGraceSeconds = std::max(
                        0.0,
                        normalizedRiskControls
                            .value(QStringLiteral("futures_flat_purge_grace_seconds"))
                            .toDouble(12.0));
                    const QString purgeMode = dashboardModeCombo_
                        ? dashboardModeCombo_->currentText().trimmed().toLower()
                        : defaultMode.trimmed().toLower();
                    if (purgeMode.contains(QStringLiteral("demo"))
                        || purgeMode.contains(QStringLiteral("test"))
                        || purgeMode.contains(QStringLiteral("paper"))) {
                        purgeGraceSeconds = std::max(purgeGraceSeconds, 30.0);
                    }
                    const int purgeThreshold = std::max(
                        1,
                        normalizedRiskControls
                            .value(QStringLiteral("futures_flat_purge_miss_threshold"))
                            .toInt(2));
                    const bool graceElapsed = openPos.openedAtMs <= 0
                        || (static_cast<double>(nowMs) - static_cast<double>(openPos.openedAtMs))
                            >= (purgeGraceSeconds * 1000.0);
                    if (graceElapsed) {
                        const int missCount = dashboardRuntimeFlatPurgeMissCounts_.value(purgeKey, 0) + 1;
                        dashboardRuntimeFlatPurgeMissCounts_.insert(purgeKey, missCount);
                        if (missCount >= purgeThreshold) {
                            dashboardRuntimeFlatPurgeMissCounts_.remove(purgeKey);
                            const int purgeTargetRow = findOpenPositionRow(
                                positionsTable_,
                                symbol,
                                interval,
                                rowConnectorCfg.key);
                            const QString closeSignalSide = openPos.side == QStringLiteral("LONG")
                                ? QStringLiteral("BUY")
                                : QStringLiteral("SELL");
                            QStringList purgeSources = openPos.signalSources;
                            if (purgeSources.isEmpty()) {
                                purgeSources.append(openPos.signalSource);
                            }
                            purgeSources = normalizedSignalSources(purgeSources);
                            if (purgeTargetRow >= 0 && positionsTable_) {
                                markPositionClosedRow(
                                    positionsTable_,
                                    positionsCumulativeView_,
                                    purgeTargetRow,
                                    QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
                                positionsTableMutated = true;
                            }
                            applyCumulativeViewImmediately();
                            NativeStrategyRuntime::recordIndicatorCloses(
                                normalizedRiskControls,
                                symbol,
                                interval,
                                purgeSources,
                                closeSignalSide,
                                nowMs,
                                dashboardRuntimeIndicatorOrderGuardStates_,
                                dashboardRuntimeIndicatorReentryBlocks_);
                            NativeStrategyRuntime::queueIndicatorFlipOnClose(
                                normalizedRiskControls,
                                symbol,
                                interval,
                                purgeSources,
                                closeSignalSide,
                                std::max(0.0, openPos.quantity),
                                nowMs,
                                dashboardRuntimePendingFlipRequests_);
                            appendDashboardPositionLog(
                                QStringLiteral("Purged stale %1 leg for %2@%3 after exchange flat-leg grace and miss threshold.")
                                    .arg(openPos.side, symbol, interval));
                            dashboardRuntimeLastEvalMs_.remove(key);
                            dashboardRuntimeEntryRetryAfterMs_.remove(key);
                            dashboardRuntimeOpenQtyCaps_.remove(key);
                            dashboardRuntimeOpenPositions_.remove(key);
                            continue;
                        }
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
                            displayIndicatorValueSummary,
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

        const QString normalizedSide = normalizedStrategyControls.value(QStringLiteral("side"))
                                           .toString()
                                           .trimmed()
                                           .toUpper();
        const bool allowLong = normalizedSide.isEmpty()
            ? strategyAllowsLong(strategySummary)
            : normalizedSide == QStringLiteral("BUY") || normalizedSide == QStringLiteral("BOTH");
        const bool allowShort = normalizedSide.isEmpty()
            ? strategyAllowsShort(strategySummary)
            : normalizedSide == QStringLiteral("SELL") || normalizedSide == QStringLiteral("BOTH");
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
            if (accountStopLossConnectors.contains(connectorToken.trimmed().toLower())) {
                appendDashboardPositionLog(
                    QStringLiteral("%1@%2 entry blocked while account-wide stop-loss close is in progress.")
                        .arg(symbol, interval));
                touchWaitingEntry(key, nowMs);
                continue;
            }
            NativeStrategyRuntime::StrategySignalInput openSignalInput = fullSignalInput;
            openSignalInput.side = signalSideForAllowedDirections(allowLong, allowShort);
            const QJsonObject nativeOpenDecision = NativeStrategyRuntime::applyIndicatorOrderGuards(
                NativeStrategyRuntime::applyIndicatorSignalConfirmation(
                    NativeStrategyRuntime::mergeIndicatorFlipOnCloseRequests(
                        NativeStrategyRuntime::buildSignalDecision(openSignalInput),
                        normalizedRiskControls,
                        symbol,
                        requestInterval,
                        nowMs,
                        dashboardRuntimePendingFlipRequests_),
                    normalizedRiskControls,
                    symbol,
                    requestInterval,
                    nowMs,
                    dashboardRuntimeIndicatorSignalTrackers_),
                normalizedRiskControls,
                symbol,
                requestInterval,
                nowMs,
                dashboardRuntimeIndicatorOrderGuardStates_,
                dashboardRuntimeIndicatorReentryBlocks_);
            OpenSignalDecision openSignal;
            const QString nativeSignal =
                nativeOpenDecision.value(QStringLiteral("signal")).toString().toUpper();
            if (nativeSignal == QStringLiteral("BUY")) {
                openSignal.side = QStringLiteral("LONG");
            } else if (nativeSignal == QStringLiteral("SELL")) {
                openSignal.side = QStringLiteral("SHORT");
            }
            openSignal.triggerText =
                nativeOpenDecision.value(QStringLiteral("description")).toString();
            openSignal.triggerSource = firstDecisionSource(nativeOpenDecision);
            const QString openSide = openSignal.side;
            const QString triggerText = openSignal.triggerText;
            const QString triggerSource = openSignal.triggerSource;
            const QString rowIndicatorValueSummary = displayIndicatorValueSummary;
            const QJsonValue rawFlipQty = nativeOpenDecision.value(QStringLiteral("flip_qty"));
            const double flipCloseQty = rawFlipQty.isDouble() ? rawFlipQty.toDouble() : 0.0;
            const bool hasFlipCloseQuantity = qIsFinite(flipCloseQty) && flipCloseQty > 0.0;

            if (!openSignal.hasSignal()) {
                // "No trigger yet" is a normal monitoring state, not a pending queue item.
                // Keeping these in waiting queue caused rows to stay Late indefinitely.
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
                symbolFilters = futures
                    ? BinanceRestClient::fetchFuturesSymbolFilters(
                          symbol,
                          isTestnet,
                          10000,
                          rowConnectorCfg.baseUrl)
                    : BinanceRestClient::fetchSpotSymbolFilters(
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

            const double globalPositionPct = dashboardPositionPctSpin_ ? dashboardPositionPctSpin_->value() : 2.0;
            const double positionPctFraction = NativeStrategyRuntime::positionPctFraction(
                normalizedStrategyControls,
                globalPositionPct,
                QStringLiteral("percent"));
            const double positionLeverage = futures ? leverage : 1.0;
            const double targetNotionalUsdt = futures
                ? std::max(10.0, availableUsdt * positionPctFraction * positionLeverage)
                : std::max(0.0, availableUsdt * positionPctFraction);
            const double requestedQty = std::max(0.000001, targetNotionalUsdt / orderSizingPrice);
            double cappedRequestedQty = hasFlipCloseQuantity ? flipCloseQty : requestedQty;
            const double storedQtyCap = dashboardRuntimeOpenQtyCaps_.value(key, 0.0);
            if (qIsFinite(storedQtyCap) && storedQtyCap > 0.0) {
                cappedRequestedQty = std::min(cappedRequestedQty, storedQtyCap);
            }
            const double requestedLegalQty = floorToOrderStep(
                cappedRequestedQty,
                symbolFilters.stepSize,
                symbolFilters.quantityPrecision);
            const BinanceRestClient::QuantityAdjustmentResult quantityAdjustment = futures
                ? BinanceRestClient::adjustFuturesQuantityToFilters(
                      symbolFilters,
                      cappedRequestedQty,
                      orderSizingPrice)
                : BinanceRestClient::adjustSpotQuantityToFilters(
                      symbolFilters,
                      cappedRequestedQty,
                      orderSizingPrice);
            double orderQty = quantityAdjustment.ok ? quantityAdjustment.quantity : 0.0;
            if (!qIsFinite(orderQty) || orderQty <= 0.0) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked: Python-parity order quantity is invalid (requested=%4, sizingPrice=%5): %6")
                        .arg(openSide,
                             symbol,
                             interval,
                             QString::number(cappedRequestedQty, 'f', 8),
                             QString::number(orderSizingPrice, 'f', 8),
                             quantityAdjustment.error));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            NativeOrderSafety::LiveTradingSafetyConfig liveSafetyConfig;
            liveSafetyConfig.liveTradingEnabled = dashboardLiveTradingEnabledCheck_
                && dashboardLiveTradingEnabledCheck_->isChecked();
            liveSafetyConfig.liveTradingAcknowledgement = dashboardLiveTradingAcknowledgementEdit_
                ? dashboardLiveTradingAcknowledgementEdit_->text().trimmed()
                : QString();
            liveSafetyConfig.liveTradingMaxLeverage = dashboardLiveTradingMaxLeverageSpin_
                ? dashboardLiveTradingMaxLeverageSpin_->value()
                : 20;
            liveSafetyConfig.liveTradingMaxPositionPct = dashboardLiveTradingMaxPositionPctSpin_
                ? dashboardLiveTradingMaxPositionPctSpin_->value()
                : 10.0;
            liveSafetyConfig.liveTradingMaxSessionOrders = dashboardLiveTradingMaxSessionOrdersSpin_
                ? dashboardLiveTradingMaxSessionOrdersSpin_->value()
                : 100;
            liveSafetyConfig.liveAllowAutoBumpToMinOrder = dashboardLiveAllowAutoBumpCheck_
                && dashboardLiveAllowAutoBumpCheck_->isChecked();
            liveSafetyConfig.maxAutoBumpPercent = dashboardMaxAutoBumpPercentSpin_
                ? dashboardMaxAutoBumpPercentSpin_->value()
                : 5.0;
            liveSafetyConfig.autoBumpPercentMultiplier = dashboardAutoBumpPercentMultiplierSpin_
                ? dashboardAutoBumpPercentMultiplierSpin_->value()
                : 10.0;
            const NativeOrderSafety::MinimumOrderAutoBumpGuardResult minimumOrderGuard =
                NativeOrderSafety::guardFuturesMinimumOrderAutoBump({
                    modeText,
                    requestedLegalQty,
                    orderQty,
                    orderSizingPrice,
                    availableUsdt,
                static_cast<int>(positionLeverage),
                    positionPctFraction * 100.0,
                    false,
                    liveSafetyConfig,
                });
            if (!minimumOrderGuard.allowed) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked by minimum-order safety: %4")
                        .arg(openSide, symbol, interval, minimumOrderGuard.errors.join(QStringLiteral(" | "))));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            const QString openOrderSide = (openSide == QStringLiteral("LONG"))
                ? QStringLiteral("BUY")
                : QStringLiteral("SELL");
            bool openReduceOnly = false;
            if (futures) {
                const auto *exposureSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                const bool hasVerifiedExposureSnapshot = exposureSnapshot && exposureSnapshot->ok;
                if (!paperTrading && (!exposureSnapshot || !exposureSnapshot->ok)) {
                    appendDashboardPositionLog(
                        QString("%1 %2@%3 blocked: futures exposure snapshot is unavailable; refusing an unverified order.")
                            .arg(openSide, symbol, interval));
                    touchWaitingEntry(key, nowMs);
                    continue;
                }

                const QString targetIndicatorKey = normalizedIndicatorKey(triggerSource);
                const QString targetIntervalKey = requestInterval.trimmed().toLower();
                double liveSideMargin = 0.0;
                double trackedSideMargin = 0.0;
                double existingIndicatorMargin = 0.0;
                double ledgerMarginTotal = 0.0;
                double netPositionAmt = 0.0;
                QSet<QString> activeSlotKeys;

                if (hasVerifiedExposureSnapshot) {
                    for (const BinanceRestClient::FuturesPosition &position : exposureSnapshot->positions) {
                        if (position.symbol.trimmed().toUpper() != symbol) {
                            continue;
                        }
                        const double margin = positionMarginUsdt(position);
                        ledgerMarginTotal += margin;
                        if (positionSideForExposure(position) == openSide) {
                            liveSideMargin += margin;
                        }
                        if (!hedgeMode
                            && (position.positionSide.trimmed().isEmpty()
                                || position.positionSide.trimmed().compare(QStringLiteral("BOTH"), Qt::CaseInsensitive) == 0)
                            && qIsFinite(position.positionAmt)) {
                            netPositionAmt += position.positionAmt;
                        }
                    }
                }

                for (auto positionIt = dashboardRuntimeOpenPositions_.cbegin();
                     positionIt != dashboardRuntimeOpenPositions_.cend();
                     ++positionIt) {
                    const RuntimePosition &trackedPosition = positionIt.value();
                    if (trackedPosition.connectorKey.trimmed().compare(rowConnectorCfg.key, Qt::CaseInsensitive) != 0
                        || trackedPosition.connectorBaseUrl.trimmed().compare(rowConnectorCfg.baseUrl, Qt::CaseInsensitive) != 0
                        || positionIt.key().section('|', 0, 0).trimmed().toUpper() != symbol) {
                        continue;
                    }
                    const QString trackedSide = trackedPosition.side.trimmed().toUpper();
                    const double margin = trackedPositionMarginUsdt(trackedPosition);
                    trackedSideMargin += trackedSide == openSide ? margin : 0.0;
                    if (!hasVerifiedExposureSnapshot) {
                        ledgerMarginTotal += margin;
                    }
                    if (trackedSide != openSide
                        || trackedPosition.interval.trimmed().toLower() != targetIntervalKey) {
                        if (!hasVerifiedExposureSnapshot && !hedgeMode
                            && trackedSide == QStringLiteral("LONG")) {
                            netPositionAmt += std::max(0.0, trackedPosition.quantity);
                        } else if (!hasVerifiedExposureSnapshot && !hedgeMode
                                   && trackedSide == QStringLiteral("SHORT")) {
                            netPositionAmt -= std::max(0.0, trackedPosition.quantity);
                        }
                        continue;
                    }
                    const QString trackedIndicatorKey = normalizedIndicatorKey(trackedPosition.signalSource);
                    const bool indicatorMatches = targetIndicatorKey.isEmpty()
                        || targetIndicatorKey == QStringLiteral("generic")
                        || trackedIndicatorKey == targetIndicatorKey;
                    if (indicatorMatches) {
                        existingIndicatorMargin += margin;
                        const QString slotKey = QStringLiteral("%1|%2")
                                                    .arg(trackedIndicatorKey, trackedPosition.interval.trimmed().toLower());
                        activeSlotKeys.insert(slotKey);
                    }
                    if (!hasVerifiedExposureSnapshot && !hedgeMode
                        && trackedSide == QStringLiteral("LONG")) {
                        netPositionAmt += std::max(0.0, trackedPosition.quantity);
                    } else if (!hasVerifiedExposureSnapshot && !hedgeMode
                               && trackedSide == QStringLiteral("SHORT")) {
                        netPositionAmt -= std::max(0.0, trackedPosition.quantity);
                    }
                }

                const double existingSideMargin = hasVerifiedExposureSnapshot
                    ? std::max(liveSideMargin, trackedSideMargin)
                    : trackedSideMargin;
                const bool slotAlreadyActive = !activeSlotKeys.isEmpty();
                if (slotAlreadyActive) {
                    appendDashboardPositionLog(
                        QString("%1 %2@%3 blocked: indicator slot is already active for this side and interval.")
                            .arg(openSide, symbol, interval));
                    touchWaitingEntry(key, nowMs);
                    continue;
                }

                const auto ratioControl = [&rowStrategyControls](const QString &name, double fallback) {
                    const QJsonValue raw = rowStrategyControls.value(name);
                    double value = raw.isDouble() ? raw.toDouble() : fallback;
                    if (!qIsFinite(value) || value <= 0.0) {
                        return 0.0;
                    }
                    return value > 1.0 ? value / 100.0 : value;
                };
                const double walletUsdt = qIsFinite(positionsLastTotalBalanceUsdt_)
                    && positionsLastTotalBalanceUsdt_ > 0.0
                    ? positionsLastTotalBalanceUsdt_
                    : availableUsdt;
                NativeOrderSafety::CapitalExposureGuardInput exposureInput;
                exposureInput.market = QStringLiteral("futures");
                exposureInput.symbol = symbol;
                exposureInput.interval = interval;
                exposureInput.side = openOrderSide;
                exposureInput.positionPctFraction = positionPctFraction;
                exposureInput.availableUsdt = availableUsdt;
                exposureInput.walletUsdt = walletUsdt;
                exposureInput.ledgerMarginTotal = ledgerMarginTotal;
                exposureInput.existingIndicatorMargin = existingIndicatorMargin;
                exposureInput.existingSideMargin = existingSideMargin;
                exposureInput.activeSlotCount = activeSlotKeys.size();
                exposureInput.slotAlreadyActive = false;
                exposureInput.price = orderSizingPrice;
                exposureInput.leverage = static_cast<int>(positionLeverage);
                exposureInput.hasFilters = true;
                exposureInput.filters = {
                    symbolFilters.stepSize,
                    symbolFilters.tickSize,
                    symbolFilters.minQty,
                    symbolFilters.minNotional,
                };
                exposureInput.requestedQuantity = cappedRequestedQty;
                exposureInput.normalizedQuantity = orderQty;
                exposureInput.flipCloseQuantity = flipCloseQty;
                exposureInput.hasFlipCloseQuantity = hasFlipCloseQuantity;
                exposureInput.liveMode = modeText.trimmed().compare(QStringLiteral("Live"), Qt::CaseInsensitive) == 0;
                exposureInput.liveAllowAutoBumpToMinOrder = liveSafetyConfig.liveAllowAutoBumpToMinOrder;
                exposureInput.maxAutoBumpPercent = normalizedRiskControls.value(QStringLiteral("max_auto_bump_percent"))
                    .toDouble(liveSafetyConfig.maxAutoBumpPercent);
                exposureInput.autoBumpPercentMultiplier = normalizedRiskControls.value(QStringLiteral("auto_bump_percent_multiplier"))
                    .toDouble(liveSafetyConfig.autoBumpPercentMultiplier);
                exposureInput.marginOverTargetTolerance = ratioControl(
                    QStringLiteral("margin_over_target_tolerance"),
                    0.05);
                exposureInput.marginFilterSlippage = ratioControl(
                    QStringLiteral("margin_filter_slippage"),
                    0.1);
                exposureInput.addOnly = normalizedStrategyControls.value(QStringLiteral("add_only")).toBool(false);
                exposureInput.dualSide = hedgeMode;
                exposureInput.netPositionAmt = netPositionAmt;
                const NativeOrderSafety::CapitalExposureGuardResult exposureGuard =
                    NativeOrderSafety::guardFuturesCapitalExposure(exposureInput);
                if (!exposureGuard.allowed) {
                    appendDashboardPositionLog(
                        QString("%1 %2@%3 blocked by Python-parity capital guard: %4")
                            .arg(openSide, symbol, interval, exposureGuard.reason));
                    touchWaitingEntry(key, nowMs);
                    continue;
                }
                orderQty = exposureGuard.quantityEstimate;
                openReduceOnly = exposureGuard.reduceOnly;
            }

            const QString openPositionSide = futures && hedgeMode ? openSide : QString();
            QString openOrderId;
            double filledQty = orderQty;
            double entryPrice = price;
            QString openOrderInfo;
            const BinanceRestClient::FuturesPosition *livePos = nullptr;
            if (paperTrading) {
                openOrderId = QStringLiteral("paper-open-%1").arg(QDateTime::currentMSecsSinceEpoch());
            } else {
                if (dashboardRuntimeConnectorOrderCircuit_ && dashboardRuntimeConnectorOrderCircuit_->isOpen()) {
                    const QJsonObject snapshot = dashboardRuntimeConnectorOrderCircuit_->snapshot(
                        QDateTime::currentDateTimeUtc());
                    appendDashboardPositionLog(
                        QString("%1 %2@%3 blocked by connector order circuit: %4")
                            .arg(openSide,
                                 symbol,
                                 interval,
                                 snapshot.value(QStringLiteral("message")).toString(
                                     QStringLiteral("connector health circuit breaker paused trading"))));
                    touchWaitingEntry(key, nowMs);
                    continue;
                }
                const NativeOrderSafety::OrderAuditLogConfig orderAuditConfig = nativeRuntimeOrderAuditLogConfig();
                const QJsonObject orderAuditStatus = NativeOrderSafety::currentOrderAuditStatus(orderAuditConfig);
                NativeOrderSafety::LiveOrderGuardInput orderGuardInput;
                orderGuardInput.mode = modeText;
                orderGuardInput.market = futures ? QStringLiteral("futures") : QStringLiteral("spot");
                orderGuardInput.params = {
                    {QStringLiteral("symbol"), symbol},
                    {QStringLiteral("side"), openOrderSide},
                    {QStringLiteral("type"), QStringLiteral("MARKET")},
                    {QStringLiteral("quantity"), QString::number(orderQty, 'f', 12)},
                };
                if (openReduceOnly) {
                    orderGuardInput.params.append({QStringLiteral("reduceOnly"), QStringLiteral("true")});
                }
                if (!openPositionSide.isEmpty()) {
                    orderGuardInput.params.append({QStringLiteral("positionSide"), openPositionSide});
                }
                orderGuardInput.apiKey = apiKey;
                orderGuardInput.apiSecret = apiSecret;
                orderGuardInput.accountType = futures ? QStringLiteral("FUTURES") : QStringLiteral("SPOT");
                orderGuardInput.leverage = static_cast<int>(positionLeverage);
                orderGuardInput.marginMode = dashboardMarginModeCombo_
                    ? dashboardMarginModeCombo_->currentText()
                    : QStringLiteral("Isolated");
                // Python's submit guard validates the top-level live safety
                // percentage; pair controls affect sizing above, not this cap.
                orderGuardInput.positionPct = globalPositionPct;
                orderGuardInput.config = liveSafetyConfig;
                orderGuardInput.hasFilters = true;
                orderGuardInput.filters = {
                    symbolFilters.stepSize,
                    symbolFilters.tickSize,
                    symbolFilters.minQty,
                    symbolFilters.minNotional,
                };
                orderGuardInput.hasLastPrice = true;
                orderGuardInput.lastPrice = orderSizingPrice;
                orderGuardInput.orderAuditEnabled = orderAuditStatus.value(QStringLiteral("enabled")).toBool(true);
                orderGuardInput.orderAuditWritable = orderAuditStatus.value(QStringLiteral("write_ok")).toBool(true);
                orderGuardInput.connectorState = rowConnectorCfg.ok() ? QStringLiteral("ready") : QStringLiteral("error");
                orderGuardInput.connectorHealth = rowConnectorCfg.ok() ? QStringLiteral("ok") : QStringLiteral("error");
                orderGuardInput.liveSubmitAttemptCount = dashboardRuntimeLiveSubmitAttemptCount_;
                const NativeOrderSafety::LiveOrderGuardResult orderGuard =
                    NativeOrderSafety::guardLiveOrderSubmit(orderGuardInput);
                if (!orderGuard.allowed) {
                    appendDashboardPositionLog(
                        QString("%1 %2@%3 blocked by order safety: %4")
                            .arg(openSide, symbol, interval, orderGuard.errors.join(QStringLiteral(" | "))));
                    touchWaitingEntry(key, nowMs);
                    continue;
                }
                dashboardRuntimeLiveSubmitAttemptCount_ = orderGuard.nextSubmitAttemptCount;
                const auto openOrder = futures
                    ? placeFuturesOpenOrderWithFallback(
                          apiKey,
                          apiSecret,
                          symbol,
                          openOrderSide,
                          orderQty,
                          isTestnet,
                          openPositionSide,
                          10000,
                          rowConnectorCfg.baseUrl,
                          openReduceOnly)
                    : BinanceRestClient::placeSpotMarketOrder(
                          apiKey,
                          apiSecret,
                          symbol,
                          openOrderSide,
                          orderQty,
                          isTestnet,
                          10000,
                          rowConnectorCfg.baseUrl);
                if (!openOrder.ok) {
                    if (dashboardRuntimeConnectorOrderCircuit_) {
                        const NativeOrderSafety::ConnectorOrderBlockEvent circuitEvent{
                            static_cast<double>(QDateTime::currentMSecsSinceEpoch()) / 1000.0,
                            symbol,
                            interval,
                            openSide,
                            futures ? QStringLiteral("FUTURES") : QStringLiteral("SPOT"),
                            QStringLiteral("error"),
                            QStringLiteral("error"),
                            openOrder.error,
                            key,
                            futures ? QStringLiteral("cpp-futures-open") : QStringLiteral("cpp-spot-open"),
                        };
                        const QJsonObject circuitSnapshot = dashboardRuntimeConnectorOrderCircuit_->recordConnectorOrderBlock(
                            circuitEvent,
                            QDateTime::currentDateTimeUtc());
                        if (!circuitSnapshot.isEmpty()) {
                            NativeOrderSafety::OrderAuditLogConfig incidentLogConfig;
                            incidentLogConfig.enabled = true;
                            incidentLogConfig.path = dashboardConnectorOrderIncidentLogPathEdit_
                                ? dashboardConnectorOrderIncidentLogPathEdit_->text().trimmed()
                                : QString();
                            incidentLogConfig.maxBytes = static_cast<quint64>(dashboardConnectorOrderIncidentMaxBytesSpin_
                                ? dashboardConnectorOrderIncidentMaxBytesSpin_->value()
                                : 2 * 1024 * 1024);
                            incidentLogConfig.backupCount = dashboardConnectorOrderIncidentBackupCountSpin_
                                ? dashboardConnectorOrderIncidentBackupCountSpin_->value()
                                : 1;
                            const QJsonObject incident = NativeOrderSafety::buildConnectorOrderCircuitIncident(
                                QStringLiteral("opened"),
                                circuitSnapshot,
                                QStringLiteral("cpp-dashboard"),
                                openOrder.error,
                                QDateTime::currentDateTimeUtc());
                            NativeOrderSafety::appendOrderAuditEvent(incident, incidentLogConfig);
                            appendDashboardAllLog(
                                QStringLiteral("Connector order circuit opened: %1")
                                    .arg(circuitSnapshot.value(QStringLiteral("message")).toString()));
                        }
                    }
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
                if (futures) {
                    livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
                    const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                    livePos = pickLivePosition(liveSnapshot, symbol, openSide);
                }
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
            const double fallbackMarginUsdt = std::max(0.0, (entryPrice * rowQty) / positionLeverage);
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
            const QStringList triggerSources = decisionSignalSources(nativeOpenDecision);
            dashboardRuntimeFlatPurgeMissCounts_.remove(key);
            dashboardRuntimeOpenPositions_.insert(
                key,
                RuntimePosition{
                    openSide,
                    interval,
                    triggerSource,
                    triggerSources,
                    rowConnectorCfg.key,
                    rowConnectorCfg.baseUrl,
                    entryPrice,
                    rowQty,
                    positionLeverage,
                    roiBasisUsdt,
                    displayMarginUsdt,
                    nowMs,
                });
            const QJsonObject openedActions = nativeOpenDecision.value(QStringLiteral("trigger_actions")).toObject();
            for (auto actionIt = openedActions.constBegin(); actionIt != openedActions.constEnd(); ++actionIt) {
                const QString action = actionIt.value().toString().trimmed().toUpper();
                NativeStrategyRuntime::recordIndicatorOrderAction(
                    symbol,
                    requestInterval,
                    actionIt.key(),
                    action,
                    nowMs,
                    dashboardRuntimeIndicatorOrderGuardStates_);
            }
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
        QStringList signalSources = normalizedSignalSources(openPos.signalSources);
        if (signalSources.isEmpty()) {
            signalSources = normalizedSignalSources(QStringList{openPos.signalSource});
        }
        NativeStrategyRuntime::StrategySignalInput closeSignalInput = fullSignalInput;
        if (!signalSources.isEmpty()) {
            for (auto iterator = closeSignalInput.rules.begin(); iterator != closeSignalInput.rules.end(); ++iterator) {
                iterator.value().enabled = signalSources.contains(iterator.key());
            }
        }
        closeSignalInput.side = openPos.side == QStringLiteral("LONG")
            ? QStringLiteral("SELL")
            : QStringLiteral("BUY");
        const QJsonObject nativeCloseDecision = NativeStrategyRuntime::applyIndicatorSignalConfirmation(
            NativeStrategyRuntime::buildSignalDecision(closeSignalInput),
            normalizedRiskControls,
            symbol,
            requestInterval,
            nowMs,
            dashboardRuntimeIndicatorSignalTrackers_);
        const QString nativeCloseSignal =
            nativeCloseDecision.value(QStringLiteral("signal")).toString().toUpper();
        const bool shouldCloseLong = openPos.side == QStringLiteral("LONG")
            && nativeCloseSignal == QStringLiteral("SELL");
        const bool shouldCloseShort = openPos.side == QStringLiteral("SHORT")
            && nativeCloseSignal == QStringLiteral("BUY");
        const bool indicatorCloseScopeAllowed = NativeStrategyRuntime::indicatorCloseScopeAllowed(
            normalizedRiskControls,
            signalSources);
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
        const QString stopLossScope = normalizedRiskControls
            .value(QStringLiteral("stop_loss"))
            .toObject()
            .value(QStringLiteral("scope"))
            .toString()
            .trimmed()
            .toLower();
        QJsonObject stopLossDecision;
        if (stopLossScope == QStringLiteral("cumulative")
            || stopLossScope == QStringLiteral("entire_account")) {
            QJsonArray stopLossPositions;
            const QString connectorKey = rowConnectorCfg.key.trimmed().toLower();
            const QString connectorBaseUrl = rowConnectorCfg.baseUrl.trimmed().toLower();
            if (liveSnapshot && liveSnapshot->ok) {
                for (const BinanceRestClient::FuturesPosition &livePosition : liveSnapshot->positions) {
                    const double quantity = std::fabs(livePosition.positionAmt);
                    const QString positionSide = livePosition.positionSide.trimmed().toUpper();
                    const QString side = positionSide == QStringLiteral("LONG")
                        ? QStringLiteral("LONG")
                        : positionSide == QStringLiteral("SHORT")
                            ? QStringLiteral("SHORT")
                            : livePosition.positionAmt > 0.0
                                ? QStringLiteral("LONG")
                                : QStringLiteral("SHORT");
                    if (quantity <= 1e-10
                        || !qIsFinite(livePosition.entryPrice)
                        || livePosition.entryPrice <= 0.0
                        || !qIsFinite(livePosition.markPrice)
                        || livePosition.markPrice <= 0.0) {
                        continue;
                    }
                    stopLossPositions.append(QJsonObject{
                        {QStringLiteral("symbol"), livePosition.symbol.trimmed().toUpper()},
                        {QStringLiteral("side"), side},
                        {QStringLiteral("quantity"), quantity},
                        {QStringLiteral("entry_price"), livePosition.entryPrice},
                        {QStringLiteral("mark_price"), livePosition.markPrice},
                        {QStringLiteral("leverage"), livePosition.leverage},
                        {QStringLiteral("margin_usdt"), livePosition.initialMargin},
                        {QStringLiteral("dual_side"), hedgeMode},
                    });
                }
            } else {
                for (auto positionIt = dashboardRuntimeOpenPositions_.cbegin();
                     positionIt != dashboardRuntimeOpenPositions_.cend();
                     ++positionIt) {
                    const RuntimePosition &trackedPosition = positionIt.value();
                    if (trackedPosition.connectorKey.trimmed().toLower() != connectorKey
                        || trackedPosition.connectorBaseUrl.trimmed().toLower() != connectorBaseUrl) {
                        continue;
                    }
                    const QString trackedSymbol = positionIt.key().section('|', 0, 0).trimmed().toUpper();
                    const double trackedQuantity = std::max(0.0, trackedPosition.quantity);
                    const double trackedEntry = trackedPosition.entryPrice;
                    double trackedMark = trackedSymbol == symbol ? markPrice : trackedEntry;
                    const auto *trackedTicker = fetchExecutionTickerPrice(trackedSymbol, rowConnectorCfg);
                    if (trackedTicker && trackedTicker->ok
                        && qIsFinite(trackedTicker->price)
                        && trackedTicker->price > 0.0) {
                        trackedMark = trackedTicker->price;
                    }
                    if (trackedQuantity <= 1e-10
                        || !qIsFinite(trackedEntry)
                        || trackedEntry <= 0.0
                        || !qIsFinite(trackedMark)
                        || trackedMark <= 0.0) {
                        continue;
                    }
                    stopLossPositions.append(QJsonObject{
                        {QStringLiteral("symbol"), trackedSymbol},
                        {QStringLiteral("side"), trackedPosition.side.trimmed().toUpper()},
                        {QStringLiteral("quantity"), trackedQuantity},
                        {QStringLiteral("entry_price"), trackedEntry},
                        {QStringLiteral("mark_price"), trackedMark},
                        {QStringLiteral("leverage"), trackedPosition.leverage},
                        {QStringLiteral("margin_usdt"), trackedPosition.displayMarginUsdt},
                        {QStringLiteral("dual_side"), hedgeMode},
                    });
                }
            }

            const QJsonArray aggregateDirectives = NativeStrategyRuntime::evaluateFuturesStopLoss(
                normalizedRiskControls,
                stopLossPositions,
                symbol,
                interval,
                qIsFinite(positionsLastTotalBalanceUsdt_) && positionsLastTotalBalanceUsdt_ > 0.0
                    ? positionsLastTotalBalanceUsdt_
                    : availableUsdt,
                futures);
            const QString expectedCloseSide = openPos.side == QStringLiteral("LONG")
                ? QStringLiteral("SELL")
                : QStringLiteral("BUY");
            for (const QJsonValue &directiveValue : aggregateDirectives) {
                const QJsonObject directive = directiveValue.toObject();
                const QString directiveCloseSide = directive.value(QStringLiteral("close_side"))
                    .toString()
                    .trimmed()
                    .toUpper();
                const QString directivePositionSide = directive.value(QStringLiteral("position_side"))
                    .toString()
                    .trimmed()
                    .toUpper();
                const bool accountDirective = directiveCloseSide == QStringLiteral("CLOSE_ALL");
                const bool currentPositionDirective = directive.value(QStringLiteral("symbol"))
                        .toString()
                        .trimmed()
                        .toUpper() == symbol
                    && directiveCloseSide == expectedCloseSide
                    && (directivePositionSide.isEmpty() || directivePositionSide == openPos.side);
                if (accountDirective || currentPositionDirective) {
                    if (accountDirective) {
                        accountStopLossConnectors.insert(connectorToken.trimmed().toLower());
                    }
                    stopLossDecision = directive;
                    stopLossDecision.insert(QStringLiteral("triggered"), true);
                    break;
                }
            }
        } else {
            stopLossDecision = NativeStrategyRuntime::evaluatePerTradeStopLoss(
                normalizedRiskControls,
                symbol,
                interval,
                openPos.side,
                rowQty,
                openPos.entryPrice,
                markPrice,
                openPos.leverage,
                displayMarginUsdt,
                futures);
        }
        const bool stopLossTriggered = stopLossDecision.value(QStringLiteral("triggered")).toBool(false);
        bool indicatorCloseTriggered = (shouldCloseLong || shouldCloseShort)
            && indicatorCloseScopeAllowed;
        if ((shouldCloseLong || shouldCloseShort) && !indicatorCloseScopeAllowed) {
            appendDashboardPositionLog(
                QStringLiteral("%1 %2@%3 indicator close blocked: multi-indicator entry requires allow_multi_indicator_close.")
                    .arg(openPos.side, symbol, interval));
        }
        if (indicatorCloseTriggered) {
            QString holdReason;
            if (!NativeStrategyRuntime::indicatorHoldReady(
                    normalizedRiskControls,
                    symbol,
                    interval,
                    openPos.openedAtMs,
                    nowMs,
                    &holdReason,
                    true)) {
                appendDashboardPositionLog(
                    QStringLiteral("%1 %2: indicator close blocked: %3")
                        .arg(openPos.side, symbol, holdReason));
                indicatorCloseTriggered = false;
            }
        }

        if (targetRow >= 0 && positionsTable_) {
            refreshActivePositionRow(
                positionsTable_,
                positionsCumulativeView_,
                targetRow,
                PositionTableActiveRowData{
                    symbol,
                    displayIndicatorValueSummary,
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

        if (!indicatorCloseTriggered && !stopLossTriggered) {
            continue;
        }

        const QString closeReason = stopLossTriggered
            ? stopLossDecision.value(QStringLiteral("reason")).toString(QStringLiteral("per_trade_stop_loss"))
            : QStringLiteral("indicator_signal");

        if (!paperTrading && !hasApiCredentials) {
            appendDashboardPositionLog(
                QString("%1 %2@%3 close deferred (%4): %5.")
                    .arg(openPos.side,
                         symbol,
                         interval,
                         closeReason,
                         QStringLiteral("missing API credentials")));
            continue;
        }

        const QString closeOrderSide = (openPos.side == QStringLiteral("LONG")) ? QStringLiteral("SELL")
                                                                                 : QStringLiteral("BUY");
        const QString closePositionSide = futures && hedgeMode ? openPos.side : QString();
        const bool closeReduceOnly = futures && !hedgeMode;
        QString closeOrderId;
        QString closeOrderError;
        double closePrice = price;
        double closeQty = openPos.quantity;
        if (paperTrading) {
            closeOrderId = QStringLiteral("paper-close-%1").arg(QDateTime::currentMSecsSinceEpoch());
        } else {
            const auto closeOrder = futures
                ? placeFuturesCloseOrderWithFallback(
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
                      price)
                : BinanceRestClient::placeSpotMarketOrder(
                      apiKey,
                      apiSecret,
                      symbol,
                      closeOrderSide,
                      openPos.quantity,
                      isTestnet,
                      10000,
                      rowConnectorCfg.baseUrl);
            if (!closeOrder.ok) {
                if (futures && isReduceOnlyRejectedError(closeOrder.error)) {
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
                        if ((indicatorCloseTriggered || stopLossTriggered) && !signalSources.isEmpty()) {
                            NativeStrategyRuntime::recordIndicatorCloses(
                                normalizedRiskControls,
                                symbol,
                                interval,
                                signalSources,
                                openPos.side == QStringLiteral("LONG") ? QStringLiteral("BUY") : QStringLiteral("SELL"),
                                nowMs,
                                dashboardRuntimeIndicatorOrderGuardStates_,
                                dashboardRuntimeIndicatorReentryBlocks_);
                            NativeStrategyRuntime::queueIndicatorFlipOnClose(
                                normalizedRiskControls,
                                symbol,
                                interval,
                                signalSources,
                                openPos.side == QStringLiteral("LONG") ? QStringLiteral("BUY") : QStringLiteral("SELL"),
                                openPos.quantity,
                                nowMs,
                                dashboardRuntimePendingFlipRequests_);
                        }
                        dashboardRuntimeLastEvalMs_.remove(key);
                        dashboardRuntimeEntryRetryAfterMs_.remove(key);
                        dashboardRuntimeOpenQtyCaps_.remove(key);
                        dashboardRuntimeFlatPurgeMissCounts_.remove(key);
                        dashboardRuntimeOpenPositions_.remove(key);
                        continue;
                    }
                }
                appendDashboardPositionLog(
                    QString("%1 %2@%3 close order failed (%4): %5")
                        .arg(openPos.side, symbol, interval, rowConnectorCfg.key, closeOrder.error));
                continue;
            }
            if (futures) {
                livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
            }
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
        const double closeCompletionTolerance = std::max(1e-9, openPos.quantity * 1e-6);
        const bool partialClose = (effectiveCloseQty + closeCompletionTolerance) < openPos.quantity;
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
            QString("%1 %2@%3 closed at %4, PNL=%5 USDT (%6%%), reason=%7, connector=%8, orderId=%9")
                .arg(openPos.side,
                     symbol,
                     interval,
                     QString::number(closePrice, 'f', 6),
                     QString::number(realizedPnlUsdt, 'f', 2),
                     QString::number(realizedPnlPct, 'f', 2),
                     closeReason,
                     rowConnectorCfg.key,
                     closeOrderId));
        if ((indicatorCloseTriggered || stopLossTriggered) && !signalSources.isEmpty()) {
            NativeStrategyRuntime::recordIndicatorCloses(
                normalizedRiskControls,
                symbol,
                interval,
                signalSources,
                openPos.side == QStringLiteral("LONG") ? QStringLiteral("BUY") : QStringLiteral("SELL"),
                nowMs,
                dashboardRuntimeIndicatorOrderGuardStates_,
                dashboardRuntimeIndicatorReentryBlocks_);
            NativeStrategyRuntime::queueIndicatorFlipOnClose(
                normalizedRiskControls,
                symbol,
                interval,
                signalSources,
                openPos.side == QStringLiteral("LONG") ? QStringLiteral("BUY") : QStringLiteral("SELL"),
                openPos.quantity,
                nowMs,
                dashboardRuntimePendingFlipRequests_);
        }
        dashboardRuntimeLastEvalMs_.remove(key);
        dashboardRuntimeEntryRetryAfterMs_.remove(key);
        dashboardRuntimeOpenQtyCaps_.remove(key);
        dashboardRuntimeFlatPurgeMissCounts_.remove(key);
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

void TradingBotWindow::runDashboardServiceRuntimeCycle() {
    if (!dashboardServiceRuntimeActive_ || dashboardRuntimeStopping_ || dashboardRuntimeCycleInProgress_) {
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

    QJsonObject query;
    query.insert(QStringLiteral("log_limit"), 20);
    query.insert(QStringLiteral("incident_limit"), 20);
    const auto result = TradingBotWindowSupport::serviceApiRequestJson(
        QStringLiteral("GET"),
        QStringLiteral("dashboard"),
        query,
        10000);
    if (!result.ok) {
        const QString warningKey = QStringLiteral("service-runtime-cycle|") + result.error;
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog(QStringLiteral("Python Service API runtime snapshot failed: %1").arg(result.error));
        }
        updateStatusMessage(QStringLiteral("Python Service API runtime snapshot unavailable: %1").arg(result.error));
        return;
    }

    const QJsonObject payload = result.document.object();
    const QJsonObject status = payload.value(QStringLiteral("status")).toObject();
    const QJsonObject runtime = payload.value(QStringLiteral("runtime")).toObject();
    const QJsonObject account = payload.value(QStringLiteral("account")).toObject();
    const QJsonObject portfolio = payload.value(QStringLiteral("portfolio")).toObject();
    const QJsonArray logs = payload.value(QStringLiteral("logs")).toArray();
    for (const QJsonValue &logValue : logs) {
        if (!logValue.isObject()) {
            continue;
        }
        const QJsonObject log = logValue.toObject();
        const qint64 sequenceId = static_cast<qint64>(log.value(QStringLiteral("sequence_id")).toDouble(0.0));
        if (sequenceId > 0 && sequenceId <= dashboardServiceLastLogSequenceId_) {
            continue;
        }
        const QString message = log.value(QStringLiteral("message")).toString().trimmed();
        if (!message.isEmpty()) {
            const QString level = log.value(QStringLiteral("level")).toString(QStringLiteral("info")).trimmed();
            const QString source = log.value(QStringLiteral("source")).toString(QStringLiteral("python-service")).trimmed();
            appendDashboardAllLog(QStringLiteral("[%1/%2] %3").arg(source, level, message));
        }
        dashboardServiceLastLogSequenceId_ = std::max(dashboardServiceLastLogSequenceId_, sequenceId);
    }
    const bool runtimeActive = status.value(QStringLiteral("state")).toString().compare(
                                   QStringLiteral("running"), Qt::CaseInsensitive) == 0
        || runtime.value(QStringLiteral("runtime_active")).toBool(false);
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText(runtimeActive ? QStringLiteral("ON (Python Service)") : QStringLiteral("OFF"));
        dashboardBotStatusLabel_->setStyleSheet(runtimeActive
                ? "color: #16a34a; font-weight: 700;"
                : "color: #ef4444; font-weight: 700;");
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText(
            runtimeActive
                ? QStringLiteral("%1 engine(s)").arg(status.value(QStringLiteral("active_engine_count")).toInt(
                      runtime.value(QStringLiteral("active_engine_count")).toInt(0)))
                : QStringLiteral("0s"));
    }

    const QJsonValue totalBalanceValue = account.value(QStringLiteral("total_balance"));
    const QJsonValue availableBalanceValue = account.value(QStringLiteral("available_balance"));
    if (dashboardBalanceLabel_ && (totalBalanceValue.isDouble() || availableBalanceValue.isDouble())) {
        const QString currency = account.value(QStringLiteral("balance_currency")).toString(QStringLiteral("USDT"));
        const QString total = totalBalanceValue.isDouble()
            ? QString::number(totalBalanceValue.toDouble(), 'f', 3)
            : QStringLiteral("N/A");
        const QString available = availableBalanceValue.isDouble()
            ? QString::number(availableBalanceValue.toDouble(), 'f', 3)
            : QStringLiteral("N/A");
        dashboardBalanceLabel_->setText(QStringLiteral("%1 total %2 | available %3").arg(currency, total, available));
        dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
        positionsBalanceAsset_ = currency.trimmed().isEmpty() ? QStringLiteral("USDT") : currency.trimmed().toUpper();
        if (totalBalanceValue.isDouble()) {
            positionsLastTotalBalanceUsdt_ = totalBalanceValue.toDouble();
        }
        if (availableBalanceValue.isDouble()) {
            positionsLastAvailableBalanceUsdt_ = availableBalanceValue.toDouble();
        }
    }

    auto setPnlLabel = [](QLabel *label, const QJsonValue &value, const QString &prefix) {
        if (!label) {
            return;
        }
        if (value.isDouble()) {
            label->setText(QStringLiteral("%1 %2").arg(prefix, QString::number(value.toDouble(), 'f', 3)));
        } else {
            label->setText(QStringLiteral("%1 N/A").arg(prefix));
        }
    };
    hydrateDashboardServicePortfolio(portfolio);
    setPnlLabel(dashboardPnlActiveLabel_, portfolio.value(QStringLiteral("active_pnl")), QStringLiteral("Active PNL:"));
    setPnlLabel(dashboardPnlClosedLabel_, portfolio.value(QStringLiteral("closed_pnl")), QStringLiteral("Closed PNL:"));
    refreshPositionsSummaryLabels();
    setPnlLabel(dashboardPnlActiveLabel_, portfolio.value(QStringLiteral("active_pnl")), QStringLiteral("Active PNL:"));
    setPnlLabel(dashboardPnlClosedLabel_, portfolio.value(QStringLiteral("closed_pnl")), QStringLiteral("Closed PNL:"));

    const auto servicePnlText = [](const QJsonValue &value) {
        return value.isDouble()
            ? QString::number(value.toDouble(), 'f', 2)
            : QStringLiteral("N/A");
    };
    const QString activePnlText = servicePnlText(portfolio.value(QStringLiteral("active_pnl")));
    const QString closedPnlText = servicePnlText(portfolio.value(QStringLiteral("closed_pnl")));
    for (QLabel *label : {positionsPnlActiveLabel_, chartPnlActiveLabel_, backtestPnlActiveLabel_, codePnlActiveLabel_}) {
        if (label) {
            label->setText(QStringLiteral("Total PNL Active Positions: %1 USDT").arg(activePnlText));
        }
    }
    for (QLabel *label : {positionsPnlClosedLabel_, chartPnlClosedLabel_, backtestPnlClosedLabel_, codePnlClosedLabel_}) {
        if (label) {
            label->setText(QStringLiteral("Total PNL Closed Positions: %1 USDT").arg(closedPnlText));
        }
    }
    const QString serviceStatusText = runtimeActive ? QStringLiteral("ON (Python Service)") : QStringLiteral("OFF");
    const QString serviceStatusStyle = runtimeActive
        ? QStringLiteral("color: #16a34a; font-weight: 700;")
        : QStringLiteral("color: #ef4444; font-weight: 700;");
    if (botStatusLabel_) {
        botStatusLabel_->setText(QStringLiteral("Bot Status: %1").arg(serviceStatusText));
        botStatusLabel_->setStyleSheet(serviceStatusStyle);
    }
    for (QLabel *label : {chartBotStatusLabel_, positionsBotStatusLabel_, codeBotStatusLabel_}) {
        if (label) {
            label->setText(QStringLiteral("Bot Status: %1").arg(serviceStatusText));
            label->setStyleSheet(serviceStatusStyle);
        }
    }
    const QString serviceTimeText = runtimeActive
        ? QStringLiteral("Bot Active Time: %1 engine(s)").arg(status.value(QStringLiteral("active_engine_count")).toInt(
              runtime.value(QStringLiteral("active_engine_count")).toInt(0)))
        : QStringLiteral("Bot Active Time: 0s");
    for (QLabel *label : {botTimeLabel_, chartBotTimeLabel_, positionsBotTimeLabel_, codeBotTimeLabel_}) {
        if (label) {
            label->setText(serviceTimeText);
        }
    }
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText(serviceStatusText);
        dashboardBotStatusLabel_->setStyleSheet(serviceStatusStyle);
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText(runtimeActive
                ? QStringLiteral("%1 engine(s)").arg(status.value(QStringLiteral("active_engine_count")).toInt(
                      runtime.value(QStringLiteral("active_engine_count")).toInt(0)))
                : QStringLiteral("0s"));
    }

    const QString message = status.value(QStringLiteral("status_message")).toString(
        QStringLiteral("Python Service API runtime snapshot refreshed."));
    updateStatusMessage(message);
}
