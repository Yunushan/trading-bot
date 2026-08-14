#pragma once

#include <QJsonDocument>
#include <QList>
#include <QPair>
#include <QSet>
#include <QString>
#include <QStringList>
#include <QVector>

#include <functional>

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
        // Canonical values in `asset`; the legacy USDT fields remain for API compatibility.
        double totalBalance = 0.0;
        double availableBalance = 0.0;
        double usdtBalance = 0.0;
        double totalUsdtBalance = 0.0;
        double availableUsdtBalance = 0.0;
        QString asset = QStringLiteral("USDT");
        QString error;
    };

    struct SpotBalanceRow {
        QString asset;
        double free = 0.0;
        double locked = 0.0;
        double total = 0.0;
    };

    struct SpotBalancesResult {
        bool ok = false;
        QVector<SpotBalanceRow> balances;
        QString error;
    };

    struct SpotAssetBalanceResult {
        bool ok = false;
        QString asset;
        double free = 0.0;
        double locked = 0.0;
        double total = 0.0;
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

    struct TickerPriceResult {
        bool ok = false;
        QString symbol;
        double price = 0.0;
        QString error;
    };

    struct FuturesBookTickerResult {
        bool ok = false;
        QString symbol;
        double bidPrice = 0.0;
        double bidQty = 0.0;
        double askPrice = 0.0;
        double askQty = 0.0;
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
        QString marginType;
    };

    struct FuturesPositionsResult {
        bool ok = false;
        QVector<FuturesPosition> positions;
        QString error;
    };

    struct FuturesSymbolFilters {
        bool ok = false;
        QString status;
        QString baseAsset;
        QString quoteAsset;
        int quoteAssetPrecision = 0;
        double stepSize = 0.0;
        double tickSize = 0.0;
        double minQty = 0.0;
        double maxQty = 0.0;
        double minNotional = 0.0;
        int quantityPrecision = 0;
        int pricePrecision = 0;
        int maxLeverage = 0;
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

    struct FuturesOpenOrder {
        QString symbol;
        QString orderId;
        QString clientOrderId;
        QString status;
        QString side;
        QString type;
        QString positionSide;
        double origQty = 0.0;
        double executedQty = 0.0;
        double price = 0.0;
    };

    struct FuturesOpenOrdersResult {
        bool ok = false;
        QVector<FuturesOpenOrder> orders;
        QString error;
    };

    struct FuturesCancelResult {
        bool ok = false;
        QString symbol;
        QString orderId;
        QString status;
        QString error;
    };

    struct FuturesTrade {
        QString symbol;
        QString tradeId;
        QString orderId;
        double price = 0.0;
        double quantity = 0.0;
        double quoteQuantity = 0.0;
        double realizedPnl = 0.0;
        double commission = 0.0;
        QString commissionAsset;
        qint64 timeMs = 0;
    };

    struct FuturesTradesResult {
        bool ok = false;
        QVector<FuturesTrade> trades;
        QString error;
    };

    struct FuturesLeverageBracket {
        QString symbol;
        int initialLeverage = 0;
        double notionalCap = 0.0;
        double notionalFloor = 0.0;
        double maintMarginRatio = 0.0;
        double cum = 0.0;
    };

    struct FuturesLeverageBracketsResult {
        bool ok = false;
        QVector<FuturesLeverageBracket> brackets;
        QString error;
    };

    struct FuturesMaxLeverageResult {
        bool ok = false;
        QString symbol;
        int maxLeverage = 0;
        QString error;
    };

    struct FuturesPositionModeResult {
        bool ok = false;
        bool dualSidePosition = false;
        QString positionMode;
        QString error;
    };

    struct FuturesMarginModeResult {
        bool ok = false;
        QString symbol;
        QString marginType;
        QString error;
    };

    struct FuturesLeverageResult {
        bool ok = false;
        QString symbol;
        int leverage = 0;
        double maxNotionalValue = 0.0;
        QString error;
    };

    struct FuturesMultiAssetsModeResult {
        bool ok = false;
        bool multiAssetsMargin = false;
        QString error;
    };

    struct FuturesForceOrder {
        QString symbol;
        QString orderId;
        QString side;
        QString positionSide;
        QString status;
        QString type;
        double avgPrice = 0.0;
        double executedQty = 0.0;
        double origQty = 0.0;
        double price = 0.0;
        qint64 timeMs = 0;
        qint64 updateTimeMs = 0;
    };

    struct FuturesForceOrdersResult {
        bool ok = false;
        QVector<FuturesForceOrder> orders;
        QString error;
    };

    struct FuturesPositionMarginResult {
        bool ok = false;
        QString symbol;
        QString positionSide;
        double amount = 0.0;
        int type = 1;
        QString error;
    };

    struct SpotTrade {
        QString symbol;
        QString tradeId;
        QString orderId;
        double price = 0.0;
        double quantity = 0.0;
        double quoteQuantity = 0.0;
        double commission = 0.0;
        QString commissionAsset;
        bool isBuyer = false;
        bool isMaker = false;
        bool isBestMatch = false;
        qint64 timeMs = 0;
    };

    struct SpotTradesResult {
        bool ok = false;
        QVector<SpotTrade> trades;
        QString error;
    };

    struct SpotPositionCostResult {
        bool ok = false;
        bool hasPosition = false;
        QString symbol;
        double quantity = 0.0;
        double cost = 0.0;
        QString error;
    };

    struct QuantityAdjustmentResult {
        bool ok = false;
        double quantity = 0.0;
        QString error;
    };

    using SpotSymbolFilters = FuturesSymbolFilters;
    using SpotOrderResult = FuturesOrderResult;

    static BalanceResult fetchUsdtBalance(
        const QString &apiKey,
        const QString &apiSecret,
        bool futures,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SpotBalancesResult fetchSpotBalances(
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    // Normalized balance helpers mirror Python get_balances/get_spot_balance
    // while retaining one common row shape for Spot and Futures accounts.
    using BalanceRowsResult = SpotBalancesResult;

    static BalanceRowsResult fetchBalanceRows(
        const QString &apiKey,
        const QString &apiSecret,
        bool futures,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SpotAssetBalanceResult fetchSpotBalance(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &asset = QStringLiteral("USDT"),
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SpotBalancesResult fetchSpotNonUsdtBalances(
        const QString &apiKey,
        const QString &apiSecret,
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
        const QString &baseUrlOverride = {},
        qint64 startTimeMs = 0,
        qint64 endTimeMs = 0);

    static KlinesResult fetchKlinesRange(
        const QString &symbol,
        const QString &interval,
        bool futures,
        bool testnet,
        qint64 startTimeMs,
        qint64 endTimeMs,
        int maxCandles = 2'000'000,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {},
        const std::function<bool()> &shouldStop = {});

    static TickerPriceResult fetchTickerPrice(
        const QString &symbol,
        bool futures,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesBookTickerResult fetchFuturesBookTicker(
        const QString &symbol,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesPositionsResult fetchOpenFuturesPositions(
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesOpenOrdersResult fetchOpenFuturesOrders(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol = {},
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesCancelResult cancelAllOpenFuturesOrders(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesCancelResult cancelFuturesOrder(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        const QString &orderId,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesTradesResult fetchFuturesTrades(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        const QString &orderId = {},
        int limit = 100,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesLeverageBracketsResult fetchFuturesLeverageBrackets(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol = {},
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesMaxLeverageResult fetchFuturesMaxLeverage(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        int fallbackMaxLeverage = 125,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static int clampFuturesLeverage(
        int requestedLeverage,
        int configuredMaxLeverage = 125,
        int symbolMaxLeverage = 0,
        bool futuresAccount = true);

    // These pure helpers mirror Python order_sizing_runtime.py. Keeping the
    // filter-adjustment step explicit lets callers test sizing before submit.
    static double floorToStep(double value, double step);
    static double ceilToStep(double value, double step);
    static double floorToDecimals(double value, int decimals);
    static double ceilToDecimals(double value, int decimals);

    static QuantityAdjustmentResult adjustSpotQuantityToFilters(
        const SpotSymbolFilters &filters,
        double quantity,
        double estimatedPrice);

    static QuantityAdjustmentResult adjustFuturesQuantityToFilters(
        const FuturesSymbolFilters &filters,
        double quantity,
        double price = 0.0);

    static double requiredPercentForSymbol(
        double price,
        const FuturesSymbolFilters &filters,
        double futuresBalance,
        double leverage = 5.0);

    static FuturesPositionModeResult fetchFuturesPositionMode(
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesPositionModeResult changeFuturesPositionMode(
        const QString &apiKey,
        const QString &apiSecret,
        bool dualSidePosition,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesMarginModeResult changeFuturesMarginType(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        const QString &marginType,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesLeverageResult changeFuturesLeverage(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        int leverage,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesMultiAssetsModeResult fetchFuturesMultiAssetsMode(
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesMultiAssetsModeResult changeFuturesMultiAssetsMode(
        const QString &apiKey,
        const QString &apiSecret,
        bool enabled,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesForceOrdersResult fetchFuturesForceOrders(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol = {},
        qint64 startTimeMs = 0,
        qint64 endTimeMs = 0,
        int limit = 20,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesPositionMarginResult changeFuturesPositionMargin(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        double amount,
        const QString &positionSide = {},
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SpotTradesResult fetchSpotTrades(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        int limit = 1000,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SpotPositionCostResult fetchSpotPositionCost(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        int limit = 1000,
        bool testnet = false,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesSymbolFilters fetchFuturesSymbolFilters(
        const QString &symbol,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static SpotSymbolFilters fetchSpotSymbolFilters(
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

    static SpotOrderResult placeSpotMarketOrder(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        const QString &side,
        double quantity,
        bool testnet,
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

    static FuturesOrderResult placeFuturesLimitOrder(
        const QString &apiKey,
        const QString &apiSecret,
        const QString &symbol,
        const QString &side,
        double quantity,
        double price,
        bool testnet,
        bool reduceOnly = false,
        const QString &positionSide = {},
        const QString &timeInForce = QStringLiteral("IOC"),
        int timeoutMs = 10000,
        const QString &baseUrlOverride = {});

private:
    static QString hmacSha256Hex(const QString &secret, const QString &message);
    static QJsonDocument signedFuturesRequestJson(
        const QString &method,
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet,
        const QString &baseUrlOverride,
        const QString &endpoint,
        const QList<QPair<QString, QString>> &params,
        int timeoutMs,
        QString *error);
    static QJsonDocument signedSpotRequestJson(
        const QString &method,
        const QString &apiKey,
        const QString &apiSecret,
        bool testnet,
        const QString &baseUrlOverride,
        const QString &endpoint,
        const QList<QPair<QString, QString>> &params,
        int timeoutMs,
        QString *error);
    static QJsonDocument httpGetJson(
        const QString &url,
        const QList<QPair<QByteArray, QByteArray>> &headers,
        int timeoutMs,
        QString *error);
};
