#pragma once

#include "BinanceRestClient.h"

#include <QMap>
#include <QString>

class BinanceWsClient;
class QTableWidget;
class QTableWidgetItem;

namespace TradingBotWindowDashboardRuntime {

QString normalizedSignalFeedKey(const QString &feedText);
bool qtWebSocketsRuntimeAvailable();
int dashboardRuntimePollIntervalMs(const QTableWidget *table, bool useWebSocketFeed);
void clearRuntimeSignalSockets(QMap<QString, BinanceWsClient *> &sockets);

void setTableCellNumeric(QTableWidget *table, int row, int col, double value);
void setTableCellRoiBasis(QTableWidgetItem *item, double value);
void pumpUiEvents(int maxMs = 5);

QString formatQuantityWithSymbol(double quantity, const QString &symbol);
QString formatPositionSizeText(double sizeUsdt, double quantity, const QString &symbol);
double livePositionTotalDisplayMargin(const BinanceRestClient::FuturesPosition *livePos, double fallback);
double livePositionTotalRoiBasis(const BinanceRestClient::FuturesPosition *livePos, double fallback);

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

} // namespace TradingBotWindowDashboardRuntime
