#pragma once

#include <QJsonDocument>
#include <QList>
#include <QPair>
#include <QSet>
#include <QString>
#include <QStringList>
#include <QVector>

class BinanceRestClient final {
public:
    struct KlineCandle {
        qint64 openTimeMs = 0;
        double open = 0.0;
        double high = 0.0;
        double low = 0.0;
        double close = 0.0;
        double volume = 0.0;
    };

    struct BalanceResult {
        bool ok = false;
        double usdtBalance = 0.0;
        double totalUsdtBalance = 0.0;
        double availableUsdtBalance = 0.0;
        QString asset = QStringLiteral("USDT");
        QString error;
    };

    struct SymbolsResult {
        bool ok = false;
        QStringList symbols;
        QString error;
    };

    struct KlinesResult {
        bool ok = false;
        QVector<KlineCandle> candles;
        QString error;
    };

    struct FuturesPosition {
        QString symbol;
        QString positionSide;
        double positionAmt = 0.0;
        double notional = 0.0;
        double initialMargin = 0.0;
        double positionInitialMargin = 0.0;
        double openOrderMargin = 0.0;
        double isolatedWallet = 0.0;
        double isolatedMargin = 0.0;
        double maintMargin = 0.0;
        double marginBalance = 0.0;
        double walletBalance = 0.0;
        double marginRatio = 0.0;
        double leverage = 0.0;
        double unrealizedProfit = 0.0;
        double entryPrice = 0.0;
        double markPrice = 0.0;
        double liquidationPrice = 0.0;
    };

    struct FuturesPositionsResult {
        bool ok = false;
        QVector<FuturesPosition> positions;
        QString error;
    };

    struct FuturesSymbolFilters {
        bool ok = false;
        double stepSize = 0.0;
        double minQty = 0.0;
        double maxQty = 0.0;
        double minNotional = 0.0;
        int quantityPrecision = 0;
        QString error;
    };

    struct FuturesOrderResult {
        bool ok = false;
        QString symbol;
        QString side;
        QString positionSide;
        QString orderId;
        QString status;
        double executedQty = 0.0;
        double avgPrice = 0.0;
        QString error;
    };

    static BalanceResult fetchUsdtBalance(
        const QString &apiKey,
        const QString &apiSecret,
        bool futures,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SymbolsResult fetchUsdtSymbols(
        bool futures,
        bool testnet,
        int timeoutMs = 10000,
        bool sortByVolume = false,
        int topN = 0,
        const QString &baseUrlOverride = {});

    static KlinesResult fetchKlines(
        const QString &symbol,
        const QString &interval,
        bool futures,
        bool testnet,
        int limit = 300,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesPositionsResult fetchOpenFuturesPositions(
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesSymbolFilters fetchFuturesSymbolFilters(
        const QString &symbol,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesOrderResult placeFuturesMarketOrder(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        const QString &side,
        double quantity,
        bool testnet,
        bool reduceOnly = false,
        const QString &positionSide = {},
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

private:
    static QString hmacSha256Hex(const QString &secret, const QString &message);
    static QJsonDocument httpGetJson(
        const QString &url,
        const QList<QPair<QByteArray, QByteArray>> &headers,
        int timeoutMs,
        QString *error);
};
