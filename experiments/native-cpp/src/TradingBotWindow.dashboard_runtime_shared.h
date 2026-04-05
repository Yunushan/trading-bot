#pragma once

#include "BinanceRestClient.h"

#include <QMap>
#include <QSet>
#include <QString>
#include <QVector>

class BinanceWsClient;
class QTableWidget;
class QTableWidgetItem;

namespace TradingBotWindowDashboardRuntime {

QString normalizedSignalFeedKey(const QString &feedText);
bool qtWebSocketsRuntimeAvailable();
bool loopTextRequestsInstant(const QString &text);
int dashboardRuntimePollIntervalMs(const QTableWidget *table, bool useWebSocketFeed);
void clearRuntimeSignalSockets(QMap<QString, BinanceWsClient *> &sockets);

void setTableCellNumeric(QTableWidget *table, int row, int col, double value);
void setTableCellRoiBasis(QTableWidgetItem *item, double value);
void pumpUiEvents(int maxMs = 5);

QString formatQuantityWithSymbol(double quantity, const QString &symbol);
QString formatPositionSizeText(double sizeUsdt, double quantity, const QString &symbol);
double livePositionTotalDisplayMargin(const BinanceRestClient::FuturesPosition *livePos, double fallback);
double livePositionTotalRoiBasis(const BinanceRestClient::FuturesPosition *livePos, double fallback);
double floorToOrderStep(double qty, double step, int precisionHint);
double normalizePriceToTick(double price, double tickSize, int precisionHint, bool roundUp);

bool strategyUsesLiveCandles(const QString &summary);

struct LivePositionMetricsShare {
    double sizeUsdt = 0.0;
    double displayMarginUsdt = 0.0;
    double roiBasisUsdt = 0.0;
    double pnlUsdt = 0.0;
};

LivePositionMetricsShare allocateLivePositionShare(
    const BinanceRestClient::FuturesPosition *livePos,
    double rowQty,
    double localGroupQty,
    double fallbackSizeUsdt,
    double fallbackDisplayMarginUsdt,
    double fallbackRoiBasisUsdt,
    double fallbackPnlUsdt);

QVector<BinanceRestClient::KlineCandle> signalCandlesFromSnapshot(
    QVector<BinanceRestClient::KlineCandle> candles,
    bool useLiveCandles,
    bool latestCandleClosed);
QString normalizedIndicatorKey(QString indicatorName);
QSet<QString> parseIndicatorKeysFromSummary(const QString &summary);
double latestRsiValue(const QVector<BinanceRestClient::KlineCandle> &candles, int period, bool *okOut = nullptr);
double latestStochRsiValue(
    const QVector<BinanceRestClient::KlineCandle> &candles,
    int length,
    int smoothK,
    int smoothD,
    bool *okOut = nullptr);
double latestWilliamsRValue(const QVector<BinanceRestClient::KlineCandle> &candles, int length, bool *okOut = nullptr);
QString indicatorDisplayName(const QString &key);
bool strategyAllowsLong(const QString &summary);
bool strategyAllowsShort(const QString &summary);
double normalizeFuturesOrderQuantity(
    double desiredQty,
    double markPrice,
    const BinanceRestClient::FuturesSymbolFilters &filters);

bool isPercentPriceFilterError(const QString &errorText);
bool isMaxQuantityExceededError(const QString &errorText);
bool isReduceOnlyRejectedError(const QString &errorText);
bool hasMatchingOpenFuturesPosition(
    const BinanceRestClient::FuturesPositionsResult *snapshot,
    const QString &symbol,
    const QString &runtimeSide,
    bool hedgeMode);

BinanceRestClient::FuturesOrderResult placeFuturesCloseOrderWithFallback(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    bool testnet,
    bool reduceOnly,
    const QString &positionSide,
    int timeoutMs,
    const QString &baseUrlOverride,
    double referencePrice = 0.0);
BinanceRestClient::FuturesOrderResult placeFuturesOpenOrderWithFallback(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    bool testnet,
    const QString &positionSide,
    int timeoutMs,
    const QString &baseUrlOverride);

} // namespace TradingBotWindowDashboardRuntime
