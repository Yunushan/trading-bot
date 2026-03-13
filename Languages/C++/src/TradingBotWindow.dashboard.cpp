#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "BinanceWsClient.h"

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

namespace {

QString normalizedSignalFeedKey(const QString &feedText) {
    const QString feedNorm = feedText.trimmed().toLower();
    if (feedNorm.contains(QStringLiteral("websocket")) || feedNorm.contains(QStringLiteral("stream"))) {
        return QStringLiteral("websocket");
    }
    return QStringLiteral("rest");
}

bool qtWebSocketsRuntimeAvailable() {
    const QDir appDir(QCoreApplication::applicationDirPath());
    const bool hasQtWebSocketsDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSockets.dll")))
        || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSocketsd.dll")));
    return (HAS_QT_WEBSOCKETS != 0) && hasQtWebSocketsDll;
}

bool loopTextRequestsInstant(const QString &text) {
    const QString normalized = text.trimmed().toLower();
    return normalized == QStringLiteral("instant")
        || normalized == QStringLiteral("0")
        || normalized == QStringLiteral("0s")
        || normalized == QStringLiteral("0 sec")
        || normalized == QStringLiteral("0 second")
        || normalized == QStringLiteral("0 seconds")
        || normalized == QStringLiteral("asap");
}

int dashboardRuntimePollIntervalMs(const QTableWidget *table, bool useWebSocketFeed) {
    constexpr int kDefaultPollMs = 1500;
    constexpr int kInstantPollMs = 1000;
    constexpr int kInstantWsPollMs = 250;
    if (!table) {
        return kDefaultPollMs;
    }
    bool hasInstant = false;
    for (int row = 0; row < table->rowCount(); ++row) {
        const QTableWidgetItem *loopItem = table->item(row, 3);
        if (loopItem && loopTextRequestsInstant(loopItem->text())) {
            hasInstant = true;
            break;
        }
    }
    if (!hasInstant) {
        return kDefaultPollMs;
    }
    return useWebSocketFeed ? kInstantWsPollMs : kInstantPollMs;
}

void clearRuntimeSignalSockets(QMap<QString, BinanceWsClient *> &sockets) {
    for (auto it = sockets.cbegin(); it != sockets.cend(); ++it) {
        BinanceWsClient *client = it.value();
        if (!client) {
            continue;
        }
        client->disconnectFromStream();
        client->deleteLater();
    }
    sockets.clear();
}

using ConnectorRuntimeConfig = TradingBotWindowSupport::ConnectorRuntimeConfig;

constexpr int kTableCellNumericRole = Qt::UserRole + 2;
constexpr int kTableCellRawNumericRole = Qt::UserRole + 4;
constexpr int kTableCellRawRoiBasisRole = Qt::UserRole + 5;

void setTableCellNumeric(QTableWidget *table, int row, int col, double value) {
    if (!table) {
        return;
    }
    QTableWidgetItem *item = table->item(row, col);
    if (!item) {
        item = new QTableWidgetItem();
        table->setItem(row, col, item);
    }
    if (qIsFinite(value)) {
        item->setData(kTableCellNumericRole, value);
        item->setData(kTableCellRawNumericRole, value);
    } else {
        item->setData(kTableCellNumericRole, QVariant());
        item->setData(kTableCellRawNumericRole, QVariant());
    }
}

void setTableCellRoiBasis(QTableWidgetItem *item, double value) {
    if (!item) {
        return;
    }
    if (qIsFinite(value)) {
        item->setData(Qt::UserRole + 1, value);
        item->setData(kTableCellRawRoiBasisRole, value);
    } else {
        item->setData(Qt::UserRole + 1, QVariant());
        item->setData(kTableCellRawRoiBasisRole, QVariant());
    }
}

void pumpUiEvents(int maxMs = 5) {
    QCoreApplication::processEvents(QEventLoop::AllEvents, maxMs);
}

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

double livePositionTotalDisplayMargin(const BinanceRestClient::FuturesPosition *livePos, double fallback) {
    if (!livePos) {
        return fallback;
    }
    const QList<double> candidates = {
        livePos->isolatedWallet,
        livePos->isolatedMargin,
        livePos->positionInitialMargin,
        livePos->initialMargin,
        fallback,
    };
    for (double value : candidates) {
        if (qIsFinite(value) && value > 0.0) {
            return value;
        }
    }
    return fallback;
}

double livePositionTotalRoiBasis(const BinanceRestClient::FuturesPosition *livePos, double fallback) {
    if (!livePos) {
        return fallback;
    }
    const QList<double> candidates = {
        livePos->positionInitialMargin,
        livePos->initialMargin,
        fallback,
        livePos->isolatedWallet,
        livePos->isolatedMargin,
    };
    for (double value : candidates) {
        if (qIsFinite(value) && value > 0.0) {
            return value;
        }
    }
    return fallback;
}

double floorToOrderStep(double qty, double step, int precisionHint) {
    if (!qIsFinite(qty) || qty <= 0.0) {
        return 0.0;
    }

    double normalized = qty;
    if (qIsFinite(step) && step > 0.0) {
        normalized = std::floor((normalized / step) + 1e-12) * step;
    }

    const int precision = std::max(0, std::min(16, precisionHint));
    if (precision > 0) {
        const double scale = std::pow(10.0, precision);
        normalized = std::floor((normalized * scale) + 1e-9) / scale;
    }

    if (qIsFinite(step) && step > 0.0) {
        normalized = std::floor((normalized / step) + 1e-12) * step;
    }

    return (qIsFinite(normalized) && normalized > 0.0) ? normalized : 0.0;
}

double normalizePriceToTick(double price, double tickSize, int precisionHint, bool roundUp) {
    if (!qIsFinite(price) || price <= 0.0) {
        return 0.0;
    }

    double normalized = price;
    if (qIsFinite(tickSize) && tickSize > 0.0) {
        normalized = roundUp
            ? (std::ceil((normalized / tickSize) - 1e-12) * tickSize)
            : (std::floor((normalized / tickSize) + 1e-12) * tickSize);
    }

    const int precision = std::max(0, std::min(16, precisionHint));
    if (precision > 0) {
        const double scale = std::pow(10.0, precision);
        normalized = roundUp
            ? (std::ceil((normalized * scale) - 1e-9) / scale)
            : (std::floor((normalized * scale) + 1e-9) / scale);
    }

    if (qIsFinite(tickSize) && tickSize > 0.0) {
        normalized = roundUp
            ? (std::ceil((normalized / tickSize) - 1e-12) * tickSize)
            : (std::floor((normalized / tickSize) + 1e-12) * tickSize);
    }

    return (qIsFinite(normalized) && normalized > 0.0) ? normalized : 0.0;
}

bool isPercentPriceFilterError(const QString &errorText) {
    const QString err = errorText.trimmed().toLower();
    return err.contains(QStringLiteral("-4131"))
        || err.contains(QStringLiteral("percent_price"))
        || err.contains(QStringLiteral("best price does not meet"));
}

bool isMaxQuantityExceededError(const QString &errorText) {
    const QString err = errorText.trimmed().toLower();
    return err.contains(QStringLiteral("-4005"))
        || err.contains(QStringLiteral("greater than max quantity"))
        || err.contains(QStringLiteral("max quantity"));
}

bool isReduceOnlyRejectedError(const QString &errorText) {
    const QString err = errorText.trimmed().toLower();
    return err.contains(QStringLiteral("-2022"))
        || err.contains(QStringLiteral("reduceonly order is rejected"))
        || err.contains(QStringLiteral("reduce only order is rejected"));
}

bool hasMatchingOpenFuturesPosition(
    const BinanceRestClient::FuturesPositionsResult *snapshot,
    const QString &symbol,
    const QString &runtimeSide,
    bool hedgeMode) {
    if (!snapshot || !snapshot->ok) {
        return false;
    }

    const QString sym = symbol.trimmed().toUpper();
    const QString side = runtimeSide.trimmed().toUpper();
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
                return true;
            }
        } else if ((posSide.isEmpty() || posSide == QStringLiteral("BOTH")) && sideMatches) {
            return true;
        } else if (sideMatches) {
            return true;
        }
    }

    return false;
}

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
    double referencePrice = 0.0) {
    BinanceRestClient::FuturesOrderResult aggregated;
    aggregated.symbol = symbol.trimmed().toUpper();
    aggregated.side = side.trimmed().toUpper();
    aggregated.positionSide = positionSide.trimmed().toUpper();
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        aggregated.error = QStringLiteral("Missing API credentials");
        return aggregated;
    }
    if (aggregated.symbol.isEmpty()) {
        aggregated.error = QStringLiteral("Symbol is required");
        return aggregated;
    }
    if (aggregated.side != QStringLiteral("BUY") && aggregated.side != QStringLiteral("SELL")) {
        aggregated.error = QStringLiteral("Side must be BUY or SELL");
        return aggregated;
    }
    if (!qIsFinite(quantity) || quantity <= 0.0) {
        aggregated.error = QStringLiteral("Quantity must be > 0");
        return aggregated;
    }

    constexpr double kQtyEpsilon = 1e-10;

    const auto filters = BinanceRestClient::fetchFuturesSymbolFilters(
        aggregated.symbol,
        testnet,
        timeoutMs,
        baseUrlOverride);
    const double stepSize = (filters.ok && qIsFinite(filters.stepSize) && filters.stepSize > 0.0) ? filters.stepSize : 0.0;
    const double tickSize = (filters.ok && qIsFinite(filters.tickSize) && filters.tickSize > 0.0) ? filters.tickSize : 0.0;
    const double minQty = (filters.ok && qIsFinite(filters.minQty) && filters.minQty > 0.0)
        ? filters.minQty
        : (stepSize > 0.0 ? stepSize : 0.0);
    const double maxQty = (filters.ok && qIsFinite(filters.maxQty) && filters.maxQty > 0.0) ? filters.maxQty : 0.0;
    const int quantityPrecision = (filters.ok && filters.quantityPrecision > 0) ? filters.quantityPrecision : 8;
    const int pricePrecision = (filters.ok && filters.pricePrecision > 0) ? filters.pricePrecision : 8;
    int maxAttempts = 20;
    if (maxQty > 0.0) {
        maxAttempts = std::max(
            maxAttempts,
            std::min(400, static_cast<int>(std::ceil(quantity / maxQty)) + 8));
    }

    double remainingQty = quantity;
    double chunkQty = (maxQty > 0.0) ? std::min(remainingQty, maxQty) : remainingQty;
    double weightedPriceSum = 0.0;
    double totalExecutedQty = 0.0;
    QStringList orderIds;
    int attempts = 0;
    bool limitFallbackAttempted = false;

    auto consumeOrderFill = [&](const BinanceRestClient::FuturesOrderResult &order, double requestedQty) -> bool {
        const double filledQty = (qIsFinite(order.executedQty) && order.executedQty > 0.0)
            ? std::min(requestedQty, order.executedQty)
            : requestedQty;
        if (!qIsFinite(filledQty) || filledQty <= kQtyEpsilon) {
            aggregated.error = QStringLiteral("Close order returned zero fill.");
            return false;
        }

        totalExecutedQty += filledQty;
        const double fillPrice = (qIsFinite(order.avgPrice) && order.avgPrice > 0.0) ? order.avgPrice : 0.0;
        if (fillPrice > 0.0) {
            weightedPriceSum += (fillPrice * filledQty);
        }
        if (!order.orderId.trimmed().isEmpty()) {
            orderIds.append(order.orderId.trimmed());
        }

        remainingQty = std::max(0.0, remainingQty - filledQty);
        chunkQty = remainingQty;
        return true;
    };

    auto nextChunkFrom = [&](double desired) -> double {
        double chunk = desired;
        if (maxQty > 0.0) {
            chunk = std::min(chunk, maxQty);
        }
        if (stepSize > 0.0) {
            chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
        }
        if (chunk <= 0.0 && desired > 0.0) {
            chunk = (maxQty > 0.0) ? std::min(desired, maxQty) : desired;
        }
        if (minQty > 0.0 && chunk + kQtyEpsilon < minQty) {
            if (remainingQty + kQtyEpsilon < minQty) {
                chunk = remainingQty;
            } else {
                chunk = minQty;
            }
            if (maxQty > 0.0) {
                chunk = std::min(chunk, maxQty);
            }
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (maxQty > 0.0 && chunk > maxQty) {
            chunk = maxQty;
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (chunk > remainingQty) {
            chunk = remainingQty;
        }
        return (qIsFinite(chunk) && chunk > 0.0) ? chunk : 0.0;
    };

    while (remainingQty > kQtyEpsilon && attempts < maxAttempts) {
        chunkQty = nextChunkFrom(chunkQty > 0.0 ? chunkQty : remainingQty);
        if (chunkQty <= 0.0) {
            aggregated.error = QStringLiteral("Unable to derive valid close quantity.");
            break;
        }

        ++attempts;
        const auto order = BinanceRestClient::placeFuturesMarketOrder(
            apiKey,
            apiSecret,
            aggregated.symbol,
            aggregated.side,
            chunkQty,
            testnet,
            reduceOnly,
            aggregated.positionSide,
            timeoutMs,
            baseUrlOverride);
        if (order.ok) {
            if (!consumeOrderFill(order, chunkQty)) {
                break;
            }
            limitFallbackAttempted = false;
            continue;
        }

        const QString orderError = order.error.trimmed();
        if (isPercentPriceFilterError(orderError)) {
            double reducedChunk = chunkQty * 0.5;
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Close fallback activated due to PERCENT_PRICE filter.");
                }
                continue;
            }
            if (!limitFallbackAttempted && qIsFinite(referencePrice) && referencePrice > 0.0) {
                limitFallbackAttempted = true;
                const bool isBuy = aggregated.side == QStringLiteral("BUY");
                const double aggressiveReference = referencePrice * (isBuy ? 1.01 : 0.99);
                const double limitPrice = normalizePriceToTick(
                    aggressiveReference,
                    tickSize,
                    pricePrecision,
                    isBuy);
                if (limitPrice > 0.0) {
                    const auto limitOrder = BinanceRestClient::placeFuturesLimitOrder(
                        apiKey,
                        apiSecret,
                        aggregated.symbol,
                        aggregated.side,
                        chunkQty,
                        limitPrice,
                        testnet,
                        reduceOnly,
                        aggregated.positionSide,
                        QStringLiteral("IOC"),
                        timeoutMs,
                        baseUrlOverride);
                    if (limitOrder.ok) {
                        if (!consumeOrderFill(limitOrder, chunkQty)) {
                            break;
                        }
                        if (aggregated.error.isEmpty()) {
                            aggregated.error = QStringLiteral("Close IOC limit fallback activated due to PERCENT_PRICE filter.");
                        }
                        continue;
                    }
                    const QString limitErrorDetail = limitOrder.error.trimmed().isEmpty()
                        ? QStringLiteral("unknown error")
                        : limitOrder.error.trimmed();
                    aggregated.error = QStringLiteral("%1 | IOC limit fallback failed at %2: %3")
                                           .arg(orderError,
                                                QString::number(limitPrice, 'f', std::max(0, std::min(8, pricePrecision))),
                                                limitErrorDetail);
                    break;
                }
            }
        } else if (isMaxQuantityExceededError(orderError)) {
            double reducedChunk = maxQty > 0.0 ? std::min(chunkQty * 0.5, maxQty) : (chunkQty * 0.5);
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Close fallback activated due to MAX_QTY filter.");
                }
                continue;
            }
        }

        aggregated.error = orderError.isEmpty() ? QStringLiteral("Close order failed") : orderError;
        break;
    }

    aggregated.executedQty = totalExecutedQty;
    if (totalExecutedQty > 0.0 && weightedPriceSum > 0.0) {
        aggregated.avgPrice = weightedPriceSum / totalExecutedQty;
    }
    aggregated.orderId = orderIds.join(QStringLiteral(","));
    if (remainingQty <= kQtyEpsilon && totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("FILLED");
        if (aggregated.error.startsWith(QStringLiteral("Close fallback activated"))
            || aggregated.error.startsWith(QStringLiteral("Close IOC limit fallback activated"))) {
            aggregated.error.clear();
        }
        return aggregated;
    }
    if (totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("PARTIALLY_FILLED");
        const QString partialMessage = QStringLiteral(
            "Partial close: executed=%1 requested=%2 remaining=%3 attempts=%4")
                                           .arg(QString::number(totalExecutedQty, 'f', 8),
                                                QString::number(quantity, 'f', 8),
                                                QString::number(std::max(0.0, remainingQty), 'f', 8),
                                                QString::number(attempts));
        if (aggregated.error.isEmpty()) {
            aggregated.error = partialMessage;
        } else {
            aggregated.error = partialMessage + QStringLiteral(" | ") + aggregated.error;
        }
        return aggregated;
    }

    if (aggregated.error.isEmpty()) {
        aggregated.error = QStringLiteral("Close order failed without fill.");
    }
    aggregated.status = QStringLiteral("FAILED");
    return aggregated;
}

constexpr int kPositionsRowSequenceRole = Qt::UserRole + 3;

void setTableCellText(QTableWidget *table, int row, int col, const QString &text) {
    if (!table) {
        return;
    }
    QTableWidgetItem *item = table->item(row, col);
    if (!item) {
        item = new QTableWidgetItem(text);
        table->setItem(row, col, item);
    } else {
        item->setText(text);
    }
    item->setData(Qt::UserRole, text);
}

class ScopedTableSortingPause final {
public:
    explicit ScopedTableSortingPause(QTableWidget *table)
        : table_(table),
          restoreSorting_(table_ && table_->isSortingEnabled()) {
        if (restoreSorting_) {
            table_->setSortingEnabled(false);
        }
    }

    ~ScopedTableSortingPause() {
        if (restoreSorting_ && table_) {
            table_->setSortingEnabled(true);
        }
    }

private:
    QTableWidget *table_ = nullptr;
    bool restoreSorting_ = false;
};

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

bool isTestnetModeLabel(const QString &modeText) {
    const QString modeNorm = modeText.trimmed().toLower();
    return modeNorm == QStringLiteral("demo")
        || modeNorm.contains("testnet")
        || modeNorm == QStringLiteral("test")
        || modeNorm.contains("sandbox")
        || modeNorm.contains("binance demo");
}

bool isPaperTradingModeLabel(const QString &modeText) {
    const QString modeNorm = modeText.trimmed().toLower();
    if (isTestnetModeLabel(modeText)) {
        return false;
    }
    return modeNorm == QStringLiteral("paper")
        || modeNorm == QStringLiteral("paper local")
        || modeNorm.contains("paper local")
        || modeNorm.contains("paper trading");
}

QString normalizedIndicatorSourceKey(const QString &sourceText) {
    const QString sourceNorm = sourceText.trimmed().toLower();
    if (sourceNorm.contains(QStringLiteral("binance futures"))) {
        return QStringLiteral("binance_futures");
    }
    if (sourceNorm.contains(QStringLiteral("binance spot"))) {
        return QStringLiteral("binance_spot");
    }
    if (sourceNorm.contains(QStringLiteral("tradingview"))) {
        return QStringLiteral("tradingview");
    }
    if (sourceNorm.contains(QStringLiteral("bybit"))) {
        return QStringLiteral("bybit");
    }
    if (sourceNorm.contains(QStringLiteral("coinbase"))) {
        return QStringLiteral("coinbase");
    }
    if (sourceNorm.contains(QStringLiteral("okx"))) {
        return QStringLiteral("okx");
    }
    if (sourceNorm.contains(QStringLiteral("gate"))) {
        return QStringLiteral("gate");
    }
    if (sourceNorm.contains(QStringLiteral("bitget"))) {
        return QStringLiteral("bitget");
    }
    if (sourceNorm.contains(QStringLiteral("mexc"))) {
        return QStringLiteral("mexc");
    }
    if (sourceNorm.contains(QStringLiteral("kucoin"))) {
        return QStringLiteral("kucoin");
    }
    if (sourceNorm.contains(QStringLiteral("htx"))) {
        return QStringLiteral("htx");
    }
    if (sourceNorm.contains(QStringLiteral("kraken"))) {
        return QStringLiteral("kraken");
    }
    return sourceNorm;
}

bool strategyUsesLiveCandles(const QString &summary) {
    return summary.trimmed().toLower().contains(QStringLiteral("live candles"));
}

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
    double fallbackPnlUsdt) {
    LivePositionMetricsShare share;
    share.sizeUsdt = fallbackSizeUsdt;
    share.displayMarginUsdt = fallbackDisplayMarginUsdt;
    share.roiBasisUsdt = fallbackRoiBasisUsdt;
    share.pnlUsdt = fallbackPnlUsdt;
    if (!livePos || !qIsFinite(rowQty) || rowQty <= 0.0) {
        return share;
    }

    const double liveQtyAbs = std::fabs(livePos->positionAmt);
    double shareRatio = 0.0;
    if (qIsFinite(localGroupQty) && localGroupQty > 1e-10) {
        shareRatio = rowQty / localGroupQty;
    } else if (qIsFinite(liveQtyAbs) && liveQtyAbs > 1e-10) {
        shareRatio = rowQty / liveQtyAbs;
    }
    if (!qIsFinite(shareRatio) || shareRatio <= 0.0) {
        return share;
    }
    shareRatio = std::min(1.0, std::max(0.0, shareRatio));

    const double totalSizeUsdt = (qIsFinite(livePos->notional) && std::fabs(livePos->notional) > 0.0)
        ? std::fabs(livePos->notional)
        : fallbackSizeUsdt;
    const double totalDisplayMarginUsdt = livePositionTotalDisplayMargin(livePos, fallbackDisplayMarginUsdt);
    const double totalRoiBasisUsdt = livePositionTotalRoiBasis(livePos, fallbackRoiBasisUsdt);
    const double totalPnlUsdt = qIsFinite(livePos->unrealizedProfit) ? livePos->unrealizedProfit : fallbackPnlUsdt;

    share.sizeUsdt = totalSizeUsdt * shareRatio;
    share.displayMarginUsdt = totalDisplayMarginUsdt * shareRatio;
    share.roiBasisUsdt = totalRoiBasisUsdt * shareRatio;
    share.pnlUsdt = totalPnlUsdt * shareRatio;
    return share;
}

QVector<BinanceRestClient::KlineCandle> signalCandlesFromSnapshot(
    QVector<BinanceRestClient::KlineCandle> candles,
    bool useLiveCandles,
    bool latestCandleClosed) {
    if (candles.isEmpty()) {
        return candles;
    }
    if (!useLiveCandles && !latestCandleClosed && candles.size() > 1) {
        candles.removeLast();
    }
    return candles;
}

QString normalizedIndicatorKey(QString indicatorName) {
    indicatorName = indicatorName.toLower();
    indicatorName.replace(" ", "").replace("(", "").replace(")", "").replace("%", "").replace("-", "").replace("_", "");
    if (indicatorName.contains("stochrsi") || indicatorName.contains("stochasticrsi")) {
        return QStringLiteral("stoch_rsi");
    }
    if (indicatorName.contains("stochastic")) {
        return QStringLiteral("stochastic");
    }
    if (indicatorName.contains("movingaverage")) {
        return QStringLiteral("ma");
    }
    if (indicatorName.contains("donchian")) {
        return QStringLiteral("donchian");
    }
    if (indicatorName.contains("psar")) {
        return QStringLiteral("psar");
    }
    if (indicatorName.contains("bollinger")) {
        return QStringLiteral("bb");
    }
    if (indicatorName.contains("relative") || indicatorName.contains("rsi")) {
        return QStringLiteral("rsi");
    }
    if (indicatorName.contains("volume")) {
        return QStringLiteral("volume");
    }
    if (indicatorName.contains("willr") || indicatorName.contains("williams")) {
        return QStringLiteral("willr");
    }
    if (indicatorName.contains("macd")) {
        return QStringLiteral("macd");
    }
    if (indicatorName.contains("ultimate")) {
        return QStringLiteral("uo");
    }
    if (indicatorName.contains("adx")) {
        return QStringLiteral("adx");
    }
    if (indicatorName.contains("dmi")) {
        return QStringLiteral("dmi");
    }
    if (indicatorName.contains("supertrend")) {
        return QStringLiteral("supertrend");
    }
    if (indicatorName.contains("ema")) {
        return QStringLiteral("ema");
    }
    return QStringLiteral("generic");
}

QString runtimeKeyFor(const QString &symbol, const QString &interval, const QString &connectorToken = QString()) {
    return symbol.trimmed().toUpper()
        + "|"
        + interval.trimmed().toLower()
        + "|"
        + connectorToken.trimmed().toLower();
}

qint64 loopSecondsFromText(QString loopText) {
    loopText = loopText.trimmed().toLower();
    if (loopTextRequestsInstant(loopText)) {
        return 0;
    }
    if (loopText.isEmpty() || loopText == "off" || loopText == "auto") {
        return 60;
    }

    static const QRegularExpression compactRe(QStringLiteral("^(\\d+)\\s*([smhdw])$"));
    QRegularExpressionMatch compactMatch = compactRe.match(loopText);
    if (compactMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = compactMatch.captured(1).toLongLong(&ok);
        if (ok && value > 0) {
            const QString unit = compactMatch.captured(2);
            if (unit == "s") return value;
            if (unit == "m") return value * 60;
            if (unit == "h") return value * 3600;
            if (unit == "d") return value * 86400;
            if (unit == "w") return value * 604800;
        }
    }

    static const QRegularExpression longRe(
        QStringLiteral("(\\d+)\\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|h|day|days|d|week|weeks|w)"));
    QRegularExpressionMatch longMatch = longRe.match(loopText);
    if (longMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = longMatch.captured(1).toLongLong(&ok);
        if (ok && value > 0) {
            const QString unit = longMatch.captured(2);
            if (unit.startsWith("s")) return value;
            if (unit.startsWith("m")) return value * 60;
            if (unit.startsWith("h")) return value * 3600;
            if (unit.startsWith("d")) return value * 86400;
            if (unit.startsWith("w")) return value * 604800;
        }
    }

    return 60;
}

qint64 intervalTokenToSeconds(QString intervalText) {
    intervalText = intervalText.trimmed().toLower();
    if (intervalText.isEmpty()) {
        return 0;
    }
    static const QRegularExpression compactRe(QStringLiteral("^(\\d+)\\s*(s|m|h|d|w|mo)$"));
    QRegularExpressionMatch compactMatch = compactRe.match(intervalText);
    if (!compactMatch.hasMatch()) {
        static const QRegularExpression longRe(
            QStringLiteral("^(\\d+)\\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|h|day|days|d|week|weeks|w|month|months|mo)$"));
        compactMatch = longRe.match(intervalText);
    }
    if (compactMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = compactMatch.captured(1).toLongLong(&ok);
        if (!ok || value <= 0) {
            return 0;
        }
        const QString unit = compactMatch.captured(2).toLower();
        if (unit == "s" || unit == "sec" || unit == "second" || unit == "seconds") return value;
        if (unit == "m" || unit == "min" || unit == "minute" || unit == "minutes") return value * 60;
        if (unit == "h" || unit == "hour" || unit == "hours") return value * 3600;
        if (unit == "d" || unit == "day" || unit == "days") return value * 86400;
        if (unit == "w" || unit == "week" || unit == "weeks") return value * 604800;
        if (unit == "mo" || unit == "month" || unit == "months") return value * 2592000;
    }
    return 0;
}

QString intervalFloorToBinanceToken(qint64 seconds) {
    static const QVector<QPair<qint64, QString>> kSupported = {
        {60, QStringLiteral("1m")},
        {180, QStringLiteral("3m")},
        {300, QStringLiteral("5m")},
        {900, QStringLiteral("15m")},
        {1800, QStringLiteral("30m")},
        {3600, QStringLiteral("1h")},
        {7200, QStringLiteral("2h")},
        {14400, QStringLiteral("4h")},
        {21600, QStringLiteral("6h")},
        {28800, QStringLiteral("8h")},
        {43200, QStringLiteral("12h")},
        {86400, QStringLiteral("1d")},
        {259200, QStringLiteral("3d")},
        {604800, QStringLiteral("1w")},
        {2592000, QStringLiteral("1M")},
    };
    if (seconds <= 0) {
        return QStringLiteral("1m");
    }
    QString best = kSupported.first().second;
    for (const auto &entry : kSupported) {
        if (seconds < entry.first) {
            break;
        }
        best = entry.second;
    }
    return best;
}

QString normalizeBinanceKlineInterval(QString intervalText, QString *warningOut = nullptr) {
    const QString original = intervalText.trimmed();
    if (warningOut) {
        warningOut->clear();
    }
    if (original.isEmpty()) {
        return original;
    }
    if (original == QStringLiteral("1M")) {
        return QStringLiteral("1M");
    }

    const QString lower = original.toLower();
    static const QSet<QString> kSupportedLower = {
        QStringLiteral("1m"),
        QStringLiteral("3m"),
        QStringLiteral("5m"),
        QStringLiteral("15m"),
        QStringLiteral("30m"),
        QStringLiteral("1h"),
        QStringLiteral("2h"),
        QStringLiteral("4h"),
        QStringLiteral("6h"),
        QStringLiteral("8h"),
        QStringLiteral("12h"),
        QStringLiteral("1d"),
        QStringLiteral("3d"),
        QStringLiteral("1w"),
    };
    if (kSupportedLower.contains(lower)) {
        return lower;
    }
    if (lower == QStringLiteral("1mo")
        || lower == QStringLiteral("1month")
        || lower == QStringLiteral("1months")) {
        return QStringLiteral("1M");
    }

    const qint64 seconds = intervalTokenToSeconds(lower);
    if (seconds <= 0) {
        return original;
    }
    const QString fallback = intervalFloorToBinanceToken(seconds);
    if (warningOut && fallback.compare(original, Qt::CaseInsensitive) != 0) {
        *warningOut = QStringLiteral("Interval '%1' is not supported by Binance REST; using '%2' fallback.")
                          .arg(original, fallback);
    }
    return fallback;
}

double latestRsiValue(const QVector<BinanceRestClient::KlineCandle> &candles, int period, bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    if (period <= 0 || candles.size() <= period) {
        return 0.0;
    }

    double gains = 0.0;
    double losses = 0.0;
    for (int i = 1; i <= period; ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            return 0.0;
        }
        if (diff >= 0.0) {
            gains += diff;
        } else {
            losses += -diff;
        }
    }
    double avgGain = gains / period;
    double avgLoss = losses / period;

    for (int i = period + 1; i < candles.size(); ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            return 0.0;
        }
        const double gain = diff > 0.0 ? diff : 0.0;
        const double loss = diff < 0.0 ? -diff : 0.0;
        avgGain = ((avgGain * (period - 1)) + gain) / period;
        avgLoss = ((avgLoss * (period - 1)) + loss) / period;
    }

    if (avgLoss <= 1e-12) {
        if (okOut) {
            *okOut = true;
        }
        return 100.0;
    }
    const double rs = avgGain / avgLoss;
    const double rsi = 100.0 - (100.0 / (1.0 + rs));
    if (okOut) {
        *okOut = qIsFinite(rsi);
    }
    return qIsFinite(rsi) ? rsi : 0.0;
}

QSet<QString> parseIndicatorKeysFromSummary(const QString &summary) {
    QSet<QString> keys;
    const QString text = summary.trimmed();
    if (text.isEmpty()) {
        return keys;
    }

    const QStringList parts = text.split(',', Qt::SkipEmptyParts);
    for (const QString &raw : parts) {
        const QString segment = raw.trimmed();
        if (segment.isEmpty()) {
            continue;
        }
        const QString lower = segment.toLower();
        if (lower == QStringLiteral("none") || lower == QStringLiteral("default")) {
            continue;
        }
        const QString key = normalizedIndicatorKey(segment);
        if (!key.isEmpty() && key != QStringLiteral("generic")) {
            keys.insert(key);
        }
    }

    const QString lower = text.toLower();
    if (lower.contains(QStringLiteral("relative strength index"))) {
        keys.insert(QStringLiteral("rsi"));
    }
    if (lower.contains(QStringLiteral("stochastic rsi"))
        || lower.contains(QStringLiteral("stoch rsi"))
        || lower.contains(QStringLiteral("stoch_rsi"))
        || lower.contains(QStringLiteral("stochrsi"))) {
        keys.insert(QStringLiteral("stoch_rsi"));
    }
    if (lower.contains(QStringLiteral("williams"))
        || lower.contains(QStringLiteral("willr"))
        || lower.contains(QStringLiteral("%r"))) {
        keys.insert(QStringLiteral("willr"));
    }

    if (keys.isEmpty()
        && lower.contains(QStringLiteral("rsi"))
        && !lower.contains(QStringLiteral("stoch"))) {
        keys.insert(QStringLiteral("rsi"));
    }

    return keys;
}

QVector<double> computeRsiSeries(const QVector<BinanceRestClient::KlineCandle> &candles, int period) {
    QVector<double> out(candles.size(), qQNaN());
    if (period <= 0 || candles.size() <= period) {
        return out;
    }

    double gains = 0.0;
    double losses = 0.0;
    for (int i = 1; i <= period; ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            return out;
        }
        if (diff >= 0.0) {
            gains += diff;
        } else {
            losses += -diff;
        }
    }

    double avgGain = gains / period;
    double avgLoss = losses / period;

    auto toRsi = [](double gain, double loss) -> double {
        if (loss <= 1e-12) {
            return 100.0;
        }
        const double rs = gain / loss;
        const double rsi = 100.0 - (100.0 / (1.0 + rs));
        return qIsFinite(rsi) ? rsi : qQNaN();
    };

    out[period] = toRsi(avgGain, avgLoss);
    for (int i = period + 1; i < candles.size(); ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            continue;
        }
        const double gain = diff > 0.0 ? diff : 0.0;
        const double loss = diff < 0.0 ? -diff : 0.0;
        avgGain = ((avgGain * (period - 1)) + gain) / period;
        avgLoss = ((avgLoss * (period - 1)) + loss) / period;
        out[i] = toRsi(avgGain, avgLoss);
    }
    return out;
}

double latestFiniteValue(const QVector<double> &values, bool *okOut = nullptr) {
    for (int i = values.size() - 1; i >= 0; --i) {
        const double v = values.at(i);
        if (qIsFinite(v)) {
            if (okOut) {
                *okOut = true;
            }
            return v;
        }
    }
    if (okOut) {
        *okOut = false;
    }
    return 0.0;
}

double latestStochRsiValue(
    const QVector<BinanceRestClient::KlineCandle> &candles,
    int length,
    int smoothK,
    int /*smoothD*/,
    bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    length = std::max(2, length);
    smoothK = std::max(1, smoothK);
    if (candles.size() <= (length + smoothK)) {
        return 0.0;
    }

    const QVector<double> rsiSeries = computeRsiSeries(candles, length);
    if (rsiSeries.isEmpty()) {
        return 0.0;
    }

    QVector<double> raw(rsiSeries.size(), qQNaN());
    for (int i = length - 1; i < rsiSeries.size(); ++i) {
        const int start = std::max(0, i - length + 1);
        double minV = std::numeric_limits<double>::infinity();
        double maxV = -std::numeric_limits<double>::infinity();
        int valid = 0;
        for (int j = start; j <= i; ++j) {
            const double v = rsiSeries.at(j);
            if (!qIsFinite(v)) {
                continue;
            }
            minV = std::min(minV, v);
            maxV = std::max(maxV, v);
            ++valid;
        }
        const double current = rsiSeries.at(i);
        if (valid < length || !qIsFinite(current)) {
            continue;
        }
        const double denom = maxV - minV;
        if (!qIsFinite(denom) || denom <= 1e-12) {
            raw[i] = 50.0;
            continue;
        }
        raw[i] = ((current - minV) / denom) * 100.0;
    }

    QVector<double> smooth(raw.size(), qQNaN());
    for (int i = smoothK - 1; i < raw.size(); ++i) {
        double sum = 0.0;
        int valid = 0;
        for (int j = i - smoothK + 1; j <= i; ++j) {
            const double v = raw.at(j);
            if (!qIsFinite(v)) {
                continue;
            }
            sum += v;
            ++valid;
        }
        if (valid < smoothK) {
            continue;
        }
        smooth[i] = sum / smoothK;
    }

    return latestFiniteValue(smooth, okOut);
}

double latestWilliamsRValue(const QVector<BinanceRestClient::KlineCandle> &candles, int length, bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    length = std::max(2, length);
    if (candles.size() < length) {
        return 0.0;
    }

    const int start = candles.size() - length;
    double highest = -std::numeric_limits<double>::infinity();
    double lowest = std::numeric_limits<double>::infinity();
    for (int i = start; i < candles.size(); ++i) {
        const auto &c = candles.at(i);
        if (!qIsFinite(c.high) || !qIsFinite(c.low)) {
            return 0.0;
        }
        highest = std::max(highest, c.high);
        lowest = std::min(lowest, c.low);
    }
    const double close = candles.constLast().close;
    if (!qIsFinite(highest) || !qIsFinite(lowest) || !qIsFinite(close)) {
        return 0.0;
    }
    const double range = highest - lowest;
    if (range <= 1e-12) {
        if (okOut) {
            *okOut = true;
        }
        return -50.0;
    }
    double wr = -100.0 * ((highest - close) / range);
    wr = std::max(-100.0, std::min(0.0, wr));
    if (okOut) {
        *okOut = qIsFinite(wr);
    }
    return qIsFinite(wr) ? wr : 0.0;
}

QString indicatorDisplayName(const QString &key) {
    const QString normalized = key.trimmed().toLower();
    if (normalized == QStringLiteral("rsi")) {
        return QStringLiteral("RSI");
    }
    if (normalized == QStringLiteral("stoch_rsi")) {
        return QStringLiteral("StochRSI");
    }
    if (normalized == QStringLiteral("willr")) {
        return QStringLiteral("Williams %R");
    }
    return normalized.toUpper();
}

bool strategyAllowsLong(const QString &summary) {
    const QString s = summary.trimmed().toLower();
    if (s.contains("both")) {
        return true;
    }
    if (s.contains("short") && !s.contains("long")) {
        return false;
    }
    return true;
}

bool strategyAllowsShort(const QString &summary) {
    const QString s = summary.trimmed().toLower();
    if (s.contains("both")) {
        return true;
    }
    if (s.contains("long") && !s.contains("short")) {
        return false;
    }
    return true;
}

double normalizeFuturesOrderQuantity(
    double desiredQty,
    double markPrice,
    const BinanceRestClient::FuturesSymbolFilters &filters) {
    if (!qIsFinite(desiredQty) || desiredQty <= 0.0 || !qIsFinite(markPrice) || markPrice <= 0.0) {
        return 0.0;
    }

    const double minQty = (qIsFinite(filters.minQty) && filters.minQty > 0.0) ? filters.minQty : 0.0;
    const double maxQty = (qIsFinite(filters.maxQty) && filters.maxQty > 0.0) ? filters.maxQty : 0.0;
    const double minNotionalQty = (qIsFinite(filters.minNotional) && filters.minNotional > 0.0)
        ? (filters.minNotional / markPrice)
        : 0.0;
    const double requiredQty = std::max(minQty, minNotionalQty);
    double qty = std::max(desiredQty, requiredQty);
    if (maxQty > 0.0) {
        qty = std::min(qty, maxQty);
    }

    const double step = (qIsFinite(filters.stepSize) && filters.stepSize > 0.0) ? filters.stepSize : 0.0;
    if (step > 0.0) {
        qty = std::ceil((qty / step) - 1e-12) * step;
    }

    if (maxQty > 0.0 && qty > maxQty) {
        if (step > 0.0) {
            qty = std::floor((maxQty / step) + 1e-12) * step;
        } else {
            qty = maxQty;
        }
    }

    const int precision = std::max(0, std::min(16, filters.quantityPrecision));
    if (precision > 0) {
        const double scale = std::pow(10.0, precision);
        qty = std::ceil((qty * scale) - 1e-9) / scale;
    }

    if (step > 0.0) {
        qty = std::ceil((qty / step) - 1e-12) * step;
    }

    if (!qIsFinite(qty) || qty <= 0.0) {
        return 0.0;
    }

    if (requiredQty > 0.0 && qty + 1e-12 < requiredQty) {
        return 0.0;
    }
    return qty;
}

BinanceRestClient::FuturesOrderResult placeFuturesOpenOrderWithFallback(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    bool testnet,
    const QString &positionSide,
    int timeoutMs,
    const QString &baseUrlOverride) {
    BinanceRestClient::FuturesOrderResult aggregated;
    aggregated.symbol = symbol.trimmed().toUpper();
    aggregated.side = side.trimmed().toUpper();
    aggregated.positionSide = positionSide.trimmed().toUpper();
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        aggregated.error = QStringLiteral("Missing API credentials");
        return aggregated;
    }
    if (aggregated.symbol.isEmpty()) {
        aggregated.error = QStringLiteral("Symbol is required");
        return aggregated;
    }
    if (aggregated.side != QStringLiteral("BUY") && aggregated.side != QStringLiteral("SELL")) {
        aggregated.error = QStringLiteral("Side must be BUY or SELL");
        return aggregated;
    }
    if (!qIsFinite(quantity) || quantity <= 0.0) {
        aggregated.error = QStringLiteral("Quantity must be > 0");
        return aggregated;
    }

    constexpr double kQtyEpsilon = 1e-10;

    const auto filters = BinanceRestClient::fetchFuturesSymbolFilters(
        aggregated.symbol,
        testnet,
        timeoutMs,
        baseUrlOverride);
    const double stepSize = (filters.ok && qIsFinite(filters.stepSize) && filters.stepSize > 0.0) ? filters.stepSize : 0.0;
    const double minQty = (filters.ok && qIsFinite(filters.minQty) && filters.minQty > 0.0)
        ? filters.minQty
        : (stepSize > 0.0 ? stepSize : 0.0);
    const double maxQty = (filters.ok && qIsFinite(filters.maxQty) && filters.maxQty > 0.0) ? filters.maxQty : 0.0;
    const int quantityPrecision = (filters.ok && filters.quantityPrecision > 0) ? filters.quantityPrecision : 8;
    int maxAttempts = 20;
    if (maxQty > 0.0) {
        maxAttempts = std::max(
            maxAttempts,
            std::min(400, static_cast<int>(std::ceil(quantity / maxQty)) + 8));
    }

    double remainingQty = quantity;
    double chunkQty = (maxQty > 0.0) ? std::min(remainingQty, maxQty) : remainingQty;
    double weightedPriceSum = 0.0;
    double totalExecutedQty = 0.0;
    QStringList orderIds;
    int attempts = 0;

    auto nextChunkFrom = [&](double desired) -> double {
        double chunk = desired;
        if (maxQty > 0.0) {
            chunk = std::min(chunk, maxQty);
        }
        if (stepSize > 0.0) {
            chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
        }
        if (chunk <= 0.0 && desired > 0.0) {
            chunk = (maxQty > 0.0) ? std::min(desired, maxQty) : desired;
        }
        if (minQty > 0.0 && chunk + kQtyEpsilon < minQty) {
            if (remainingQty + kQtyEpsilon < minQty) {
                chunk = remainingQty;
            } else {
                chunk = minQty;
            }
            if (maxQty > 0.0) {
                chunk = std::min(chunk, maxQty);
            }
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (maxQty > 0.0 && chunk > maxQty) {
            chunk = maxQty;
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (chunk > remainingQty) {
            chunk = remainingQty;
        }
        return (qIsFinite(chunk) && chunk > 0.0) ? chunk : 0.0;
    };

    while (remainingQty > kQtyEpsilon && attempts < maxAttempts) {
        chunkQty = nextChunkFrom(chunkQty > 0.0 ? chunkQty : remainingQty);
        if (chunkQty <= 0.0) {
            aggregated.error = QStringLiteral("Unable to derive valid open quantity.");
            break;
        }

        ++attempts;
        const auto order = BinanceRestClient::placeFuturesMarketOrder(
            apiKey,
            apiSecret,
            aggregated.symbol,
            aggregated.side,
            chunkQty,
            testnet,
            false,
            aggregated.positionSide,
            timeoutMs,
            baseUrlOverride);
        if (order.ok) {
            const double filledQty = (qIsFinite(order.executedQty) && order.executedQty > 0.0)
                ? std::min(chunkQty, order.executedQty)
                : chunkQty;
            if (!qIsFinite(filledQty) || filledQty <= kQtyEpsilon) {
                aggregated.error = QStringLiteral("Open order returned zero fill.");
                break;
            }

            totalExecutedQty += filledQty;
            const double fillPrice = (qIsFinite(order.avgPrice) && order.avgPrice > 0.0) ? order.avgPrice : 0.0;
            if (fillPrice > 0.0) {
                weightedPriceSum += (fillPrice * filledQty);
            }
            if (!order.orderId.trimmed().isEmpty()) {
                orderIds.append(order.orderId.trimmed());
            }

            remainingQty = std::max(0.0, remainingQty - filledQty);
            chunkQty = remainingQty;
            continue;
        }

        const QString orderError = order.error.trimmed();
        if (isPercentPriceFilterError(orderError)) {
            double reducedChunk = chunkQty * 0.5;
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Open fallback activated due to PERCENT_PRICE filter.");
                }
                continue;
            }
        } else if (isMaxQuantityExceededError(orderError)) {
            double reducedChunk = maxQty > 0.0 ? std::min(chunkQty * 0.5, maxQty) : (chunkQty * 0.5);
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Open fallback activated due to MAX_QTY filter.");
                }
                continue;
            }
        }

        aggregated.error = orderError.isEmpty() ? QStringLiteral("Open order failed") : orderError;
        break;
    }

    aggregated.executedQty = totalExecutedQty;
    if (totalExecutedQty > 0.0 && weightedPriceSum > 0.0) {
        aggregated.avgPrice = weightedPriceSum / totalExecutedQty;
    }
    aggregated.orderId = orderIds.join(QStringLiteral(","));
    if (remainingQty <= kQtyEpsilon && totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("FILLED");
        if (aggregated.error.startsWith(QStringLiteral("Open fallback activated"))) {
            aggregated.error.clear();
        }
        return aggregated;
    }
    if (totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("PARTIALLY_FILLED");
        const QString partialMessage = QStringLiteral(
            "Partial open: executed=%1 requested=%2 remaining=%3 attempts=%4")
                                           .arg(QString::number(totalExecutedQty, 'f', 8),
                                                QString::number(quantity, 'f', 8),
                                                QString::number(std::max(0.0, remainingQty), 'f', 8),
                                                QString::number(attempts));
        if (aggregated.error.isEmpty()) {
            aggregated.error = partialMessage;
        } else {
            aggregated.error = partialMessage + QStringLiteral(" | ") + aggregated.error;
        }
        return aggregated;
    }

    if (aggregated.error.isEmpty()) {
        aggregated.error = QStringLiteral("Open order failed without fill.");
    }
    aggregated.status = QStringLiteral("FAILED");
    return aggregated;
}

constexpr double kWaitingPositionLateThresholdSec = 45.0;

} // namespace

void TradingBotWindow::updateDashboardStopLossWidgetState() {
    if (!dashboardStopLossEnableCheck_) {
        return;
    }
    const bool runtimeActive = dashboardRuntimeActive_;
    const bool stopLossEnabled = dashboardStopLossEnableCheck_->isChecked() && !runtimeActive;

    if (dashboardStopLossModeCombo_) {
        dashboardStopLossModeCombo_->setEnabled(stopLossEnabled);
    }
    if (dashboardStopLossScopeCombo_) {
        dashboardStopLossScopeCombo_->setEnabled(stopLossEnabled);
    }

    QString mode = dashboardStopLossModeCombo_
        ? dashboardStopLossModeCombo_->currentData().toString().trimmed().toLower()
        : QString();
    if (mode.isEmpty()) {
        mode = QStringLiteral("usdt");
    }
    const bool enableUsdt = stopLossEnabled && (mode == "usdt" || mode == "both");
    const bool enablePercent = stopLossEnabled && (mode == "percent" || mode == "both");

    if (dashboardStopLossUsdtSpin_) {
        dashboardStopLossUsdtSpin_->setEnabled(enableUsdt);
    }
    if (dashboardStopLossPercentSpin_) {
        dashboardStopLossPercentSpin_->setEnabled(enablePercent);
    }
}

void TradingBotWindow::setDashboardRuntimeControlsEnabled(bool enabled) {
    for (QWidget *widget : dashboardRuntimeLockWidgets_) {
        if (widget) {
            widget->setEnabled(enabled);
        }
    }

    if (dashboardLeadTraderCombo_) {
        const bool leadEnabled = enabled
            && dashboardLeadTraderEnableCheck_
            && dashboardLeadTraderEnableCheck_->isChecked();
        dashboardLeadTraderCombo_->setEnabled(leadEnabled);
    }

    for (auto it = dashboardIndicatorChecks_.begin(); it != dashboardIndicatorChecks_.end(); ++it) {
        if (QCheckBox *cb = it.value()) {
            cb->setEnabled(enabled);
        }
    }
    for (auto it = dashboardIndicatorButtons_.begin(); it != dashboardIndicatorButtons_.end(); ++it) {
        QPushButton *btn = it.value();
        QCheckBox *cb = dashboardIndicatorChecks_.value(it.key(), nullptr);
        if (btn) {
            btn->setEnabled(enabled && cb && cb->isChecked());
        }
    }

    if (dashboardStopLossEnableCheck_) {
        dashboardStopLossEnableCheck_->setEnabled(enabled);
    }
    updateDashboardStopLossWidgetState();

    if (dashboardStartBtn_) {
        dashboardStartBtn_->setEnabled(enabled);
    }
    if (dashboardStopBtn_) {
        dashboardStopBtn_->setEnabled(!enabled);
    }
    syncDashboardPaperBalanceUi();
}

void TradingBotWindow::appendDashboardAllLog(const QString &message) {
    if (!dashboardAllLogsEdit_) {
        return;
    }
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    dashboardAllLogsEdit_->append(QString("%1 %2").arg(ts, message));
}

void TradingBotWindow::appendDashboardPositionLog(const QString &message) {
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    if (dashboardPositionLogsEdit_) {
        dashboardPositionLogsEdit_->append(QString("%1 %2").arg(ts, message));
    }
    if (dashboardAllLogsEdit_) {
        dashboardAllLogsEdit_->append(QString("%1 [Position] %2").arg(ts, message));
    }
}

void TradingBotWindow::appendDashboardWaitingLog(const QString &message) {
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    if (dashboardWaitingLogsEdit_) {
        dashboardWaitingLogsEdit_->append(QString("%1 %2").arg(ts, message));
    }
    if (dashboardAllLogsEdit_) {
        dashboardAllLogsEdit_->append(QString("%1 [Waiting] %2").arg(ts, message));
    }
}

void TradingBotWindow::refreshDashboardWaitingQueueTable() {
    if (!dashboardWaitingQueueTable_) {
        return;
    }

    QList<QVariantMap> combinedEntries = dashboardWaitingActiveEntries_.values();
    combinedEntries.append(dashboardWaitingHistoryEntries_);

    std::sort(combinedEntries.begin(), combinedEntries.end(), [](const QVariantMap &a, const QVariantMap &b) {
        const QString stateA = a.value(QStringLiteral("state")).toString().trimmed().toLower();
        const QString stateB = b.value(QStringLiteral("state")).toString().trimmed().toLower();
        const int endedRankA = stateA == QStringLiteral("ended") ? 1 : 0;
        const int endedRankB = stateB == QStringLiteral("ended") ? 1 : 0;
        if (endedRankA != endedRankB) {
            return endedRankA < endedRankB;
        }
        const double ageA = a.value(QStringLiteral("age")).toDouble();
        const double ageB = b.value(QStringLiteral("age")).toDouble();
        if (!qFuzzyCompare(ageA + 1.0, ageB + 1.0)) {
            return ageA > ageB;
        }
        const QString symbolA = a.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        const QString symbolB = b.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        return symbolA < symbolB;
    });

    dashboardWaitingQueueTable_->setSortingEnabled(false);
    dashboardWaitingQueueTable_->clearContents();
    dashboardWaitingQueueTable_->setRowCount(combinedEntries.size());

    for (int row = 0; row < combinedEntries.size(); ++row) {
        const QVariantMap &entry = combinedEntries.at(row);
        const QString symbol = entry.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        const QString interval = entry.value(QStringLiteral("interval")).toString().trimmed().toUpper();
        const QString side = entry.value(QStringLiteral("side")).toString().trimmed().toUpper();
        const QString context = entry.value(QStringLiteral("context")).toString().trimmed();
        const QString state = entry.value(QStringLiteral("state")).toString().trimmed();
        int ageSeconds = entry.value(QStringLiteral("age_seconds")).toInt();
        if (ageSeconds < 0) {
            ageSeconds = 0;
        }

        auto makeItem = [](const QString &text, bool centered = false) -> QTableWidgetItem * {
            auto *item = new QTableWidgetItem(text);
            if (centered) {
                item->setTextAlignment(Qt::AlignCenter);
            }
            return item;
        };

        dashboardWaitingQueueTable_->setItem(row, 0, makeItem(symbol.isEmpty() ? QStringLiteral("-") : symbol, true));
        dashboardWaitingQueueTable_->setItem(row, 1, makeItem(interval.isEmpty() ? QStringLiteral("-") : interval, true));
        dashboardWaitingQueueTable_->setItem(row, 2, makeItem(side.isEmpty() ? QStringLiteral("-") : side, true));
        dashboardWaitingQueueTable_->setItem(row, 3, makeItem(context.isEmpty() ? QStringLiteral("-") : context, false));
        dashboardWaitingQueueTable_->setItem(row, 4, makeItem(state.isEmpty() ? QStringLiteral("-") : state, true));
        dashboardWaitingQueueTable_->setItem(row, 5, makeItem(QString::number(ageSeconds), true));
    }

    dashboardWaitingQueueTable_->setSortingEnabled(true);
}

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
    if (staleOpenCount > 0) {
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
        appendDashboardAllLog("Demo active: using Binance Futures Testnet market data and testnet execution.");
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

    const auto indicatorParamDouble =
        [this](const QString &indicatorKey, const QString &fieldKey, double fallback) -> double {
        const QVariantMap cfg = dashboardIndicatorParams_.value(indicatorKey);
        if (!cfg.contains(fieldKey)) {
            return fallback;
        }
        bool ok = false;
        const double value = cfg.value(fieldKey).toDouble(&ok);
        return (ok && qIsFinite(value)) ? value : fallback;
    };
    const auto indicatorParamInt =
        [this](const QString &indicatorKey, const QString &fieldKey, int fallback) -> int {
        const QVariantMap cfg = dashboardIndicatorParams_.value(indicatorKey);
        if (!cfg.contains(fieldKey)) {
            return fallback;
        }
        bool ok = false;
        const int value = cfg.value(fieldKey).toInt(&ok);
        return (ok && value > 0) ? value : fallback;
    };

    double rsiBuyThreshold = indicatorParamDouble(QStringLiteral("rsi"), QStringLiteral("buy_value"), 30.0);
    double rsiSellThreshold = indicatorParamDouble(QStringLiteral("rsi"), QStringLiteral("sell_value"), 70.0);
    if (rsiBuyThreshold < 0.0 || rsiBuyThreshold > 100.0
        || rsiSellThreshold < 0.0 || rsiSellThreshold > 100.0
        || rsiBuyThreshold >= rsiSellThreshold) {
        rsiBuyThreshold = 30.0;
        rsiSellThreshold = 70.0;
    }

    double stochBuyThreshold = indicatorParamDouble(QStringLiteral("stoch_rsi"), QStringLiteral("buy_value"), 20.0);
    double stochSellThreshold = indicatorParamDouble(QStringLiteral("stoch_rsi"), QStringLiteral("sell_value"), 80.0);
    if (stochBuyThreshold < 0.0 || stochBuyThreshold > 100.0
        || stochSellThreshold < 0.0 || stochSellThreshold > 100.0
        || stochBuyThreshold >= stochSellThreshold) {
        stochBuyThreshold = 20.0;
        stochSellThreshold = 80.0;
    }

    double willrBuyThreshold = indicatorParamDouble(QStringLiteral("willr"), QStringLiteral("buy_value"), -80.0);
    double willrSellThreshold = indicatorParamDouble(QStringLiteral("willr"), QStringLiteral("sell_value"), -20.0);
    willrBuyThreshold = std::max(-100.0, std::min(0.0, willrBuyThreshold));
    willrSellThreshold = std::max(-100.0, std::min(0.0, willrSellThreshold));
    if (willrBuyThreshold >= willrSellThreshold) {
        willrBuyThreshold = -80.0;
        willrSellThreshold = -20.0;
    }

    const int rsiLength = std::max(2, indicatorParamInt(QStringLiteral("rsi"), QStringLiteral("length"), 14));
    const int stochLength = std::max(2, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("length"), 14));
    const int stochSmoothK = std::max(1, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("smooth_k"), 3));
    const int stochSmoothD = std::max(1, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("smooth_d"), 3));
    const int willrLength = std::max(2, indicatorParamInt(QStringLiteral("willr"), QStringLiteral("length"), 14));

    double availableUsdt = currentDashboardPaperBalanceUsdt();
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const bool hasApiCredentials = !apiKey.isEmpty() && !apiSecret.isEmpty();
    const bool hedgeMode = dashboardPositionModeCombo_
        ? dashboardPositionModeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("hedge"))
        : true;
    QMap<QString, BinanceRestClient::FuturesSymbolFilters> symbolFiltersCache;
    QMap<QString, BinanceRestClient::FuturesPositionsResult> livePositionsCache;
    const auto connectorCacheKeyFor = [isTestnet](const ConnectorRuntimeConfig &cfg) {
        return QStringLiteral("%1|%2|%3")
            .arg(cfg.key.trimmed().toLower(),
                 cfg.baseUrl.trimmed().toLower(),
                 isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"));
    };
    const auto fetchLivePositionsForConnector =
        [this, futures, hasApiCredentials, paperTrading, &apiKey, &apiSecret, isTestnet, &livePositionsCache, &connectorCacheKeyFor](
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
    const auto tableCellRaw = [this](int row, int col) -> QString {
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
        if (loopSeconds > 0 && lastMs > 0 && (nowMs - lastMs) < (loopSeconds * 1000)) {
            if (openIt != dashboardRuntimeOpenPositions_.end() && positionsTable_) {
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

                const double rowQty = std::max(0.0, openPos.quantity);
                const QString exposureKey = QStringLiteral("%1|%2|%3")
                                                .arg(symbol,
                                                     openPos.side.trimmed().toUpper(),
                                                     connectorToken.toLower());
                const double groupQty = runtimeQtyByExposureKey.value(exposureKey, rowQty);
                const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                    ? livePos->markPrice
                    : openPos.entryPrice;
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
                const double markPnlUsdt = liveShare.pnlUsdt;
                const double markPnlPct = (markPnlUsdt / std::max(1e-9, openPos.roiBasisUsdt)) * 100.0;
                const double sizeUsdt = std::max(0.0, liveShare.sizeUsdt);
                const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
                const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
                const QString marginRatioText = marginRatio > 0.0
                    ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
                    : QStringLiteral("-");
                const QString liqText = liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");

                int targetRow = -1;
                for (int t = positionsTable_->rowCount() - 1; t >= 0; --t) {
                    const QString rowSymbol = tableCellRaw(t, 0).trimmed().toUpper();
                    const QString rowInterval = tableCellRaw(t, 8).trimmed();
                    const QString rowStatus = tableCellRaw(t, 16).trimmed().toUpper();
                    const QString rowConnectorHint = tableCellRaw(t, 17).toLower();
                    if (rowSymbol == symbol
                        && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                        && rowStatus == QStringLiteral("OPEN")
                        && rowConnectorHint.contains(rowConnectorCfg.key.toLower())) {
                        targetRow = t;
                        break;
                    }
                }

                if (targetRow >= 0) {
                    ScopedTableSortingPause sortingPause(positionsTable_);
                    const bool updateVisibleText = !positionsCumulativeView_;
                    auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text, bool preserveWhenUnavailable = false) {
                        QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                        QString finalText = text;
                        if (preserveWhenUnavailable && (text.trimmed().isEmpty() || text.trimmed() == QStringLiteral("-"))) {
                            QString existing;
                            if (item) {
                                const QVariant raw = item->data(Qt::UserRole);
                                existing = raw.isValid() ? raw.toString() : item->text();
                            }
                            existing = existing.trimmed();
                            if (!existing.isEmpty() && existing != QStringLiteral("-")) {
                                finalText = existing;
                            }
                        }
                        if (!item) {
                            item = new QTableWidgetItem(finalText);
                            positionsTable_->setItem(targetRow, col, item);
                        } else if (updateVisibleText) {
                            item->setText(finalText);
                        }
                        item->setData(Qt::UserRole, finalText);
                    };
                    setOrCreate(1, formatPositionSizeText(sizeUsdt, rowQty, symbol));
                    setOrCreate(2, QString::number(markPrice, 'f', 6));
                    setOrCreate(3, marginRatioText, true);
                    setOrCreate(4, liqText, true);
                    setOrCreate(5, QString::number(openPos.displayMarginUsdt, 'f', 2));
                    setOrCreate(6, formatQuantityWithSymbol(rowQty, symbol));
                    setOrCreate(7, QString("%1 (%2%)")
                                    .arg(QString::number(markPnlUsdt, 'f', 2),
                                         QString::number(markPnlPct, 'f', 2)));
                    setTableCellNumeric(positionsTable_, targetRow, 1, sizeUsdt);
                    setTableCellNumeric(positionsTable_, targetRow, 2, markPrice);
                    setTableCellNumeric(positionsTable_, targetRow, 3, marginRatio);
                    setTableCellNumeric(positionsTable_, targetRow, 4, liqPrice);
                    setTableCellNumeric(positionsTable_, targetRow, 5, openPos.displayMarginUsdt);
                    setTableCellNumeric(positionsTable_, targetRow, 6, rowQty);
                    setTableCellNumeric(positionsTable_, targetRow, 7, markPnlUsdt);
                    if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                        setTableCellRoiBasis(pnlItem, openPos.roiBasisUsdt);
                    }
                    positionsTableMutated = true;
                }
            }
            touchWaitingEntry(key, nowMs);
            continue;
        }
        dashboardRuntimeLastEvalMs_.insert(key, nowMs);

        const auto *indicatorItem = dashboardOverridesTable_->item(row, 2);
        const QString indicatorSummary = indicatorItem ? indicatorItem->text() : QString();
        const auto *strategyControlsItem = dashboardOverridesTable_->item(row, 6);
        const QString strategySummary = strategyControlsItem ? strategyControlsItem->text() : QString();
        const bool useLiveSignalCandles = strategyUsesLiveCandles(strategySummary);
        const QSet<QString> indicatorKeys = parseIndicatorKeysFromSummary(indicatorSummary);
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

        bool rsiOk = false;
        double rsi = 0.0;
        if (useRsi) {
            rsi = latestRsiValue(signalCandles, rsiLength, &rsiOk);
        }

        bool stochRsiOk = false;
        double stochRsi = 0.0;
        if (useStochRsi) {
            stochRsi = latestStochRsiValue(signalCandles, stochLength, stochSmoothK, stochSmoothD, &stochRsiOk);
        }

        bool willrOk = false;
        double willr = 0.0;
        if (useWillr) {
            willr = latestWilliamsRValue(signalCandles, willrLength, &willrOk);
        }

        QStringList indicatorValueParts;
        if (useRsi && rsiOk) {
            indicatorValueParts << QString("RSI %1").arg(QString::number(rsi, 'f', 2));
        }
        if (useStochRsi && stochRsiOk) {
            indicatorValueParts << QString("StochRSI %1").arg(QString::number(stochRsi, 'f', 2));
        }
        if (useWillr && willrOk) {
            indicatorValueParts << QString("W%R %1").arg(QString::number(willr, 'f', 2));
        }
        const QString indicatorValueSummary = indicatorValueParts.isEmpty()
            ? QStringLiteral("-")
            : indicatorValueParts.join(QStringLiteral(" | "));

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

        const double positionPct = dashboardPositionPctSpin_ ? dashboardPositionPctSpin_->value() : 2.0;
        const double targetNotionalUsdt = std::max(10.0, availableUsdt * (std::max(0.1, positionPct) / 100.0) * leverage);
        const double requestedQty = std::max(0.000001, targetNotionalUsdt / price);

        if (openIt == dashboardRuntimeOpenPositions_.end()) {
            QString openSide;
            QString triggerText;
            QString triggerSource = QStringLiteral("rsi");
            auto setLongTrigger = [&openSide, &triggerText, &triggerSource](const QString &src, const QString &txt) {
                openSide = QStringLiteral("LONG");
                triggerSource = src;
                triggerText = txt;
            };
            auto setShortTrigger = [&openSide, &triggerText, &triggerSource](const QString &src, const QString &txt) {
                openSide = QStringLiteral("SHORT");
                triggerSource = src;
                triggerText = txt;
            };

            if (useRsi && rsiOk) {
                if (allowLong && rsi <= rsiBuyThreshold) {
                    setLongTrigger(
                        QStringLiteral("rsi"),
                        QString("RSI %1 <= %2")
                            .arg(QString::number(rsi, 'f', 2), QString::number(rsiBuyThreshold, 'f', 2)));
                } else if (allowShort && rsi >= rsiSellThreshold) {
                    setShortTrigger(
                        QStringLiteral("rsi"),
                        QString("RSI %1 >= %2")
                            .arg(QString::number(rsi, 'f', 2), QString::number(rsiSellThreshold, 'f', 2)));
                }
            }
            if (openSide.isEmpty() && useStochRsi && stochRsiOk) {
                if (allowLong && stochRsi <= stochBuyThreshold) {
                    setLongTrigger(
                        QStringLiteral("stoch_rsi"),
                        QString("StochRSI %1 <= %2")
                            .arg(QString::number(stochRsi, 'f', 2), QString::number(stochBuyThreshold, 'f', 2)));
                } else if (allowShort && stochRsi >= stochSellThreshold) {
                    setShortTrigger(
                        QStringLiteral("stoch_rsi"),
                        QString("StochRSI %1 >= %2")
                            .arg(QString::number(stochRsi, 'f', 2), QString::number(stochSellThreshold, 'f', 2)));
                }
            }
            if (openSide.isEmpty() && useWillr && willrOk) {
                if (allowLong && willr <= willrBuyThreshold) {
                    setLongTrigger(
                        QStringLiteral("willr"),
                        QString("Williams %%R %1 <= %2")
                            .arg(QString::number(willr, 'f', 2), QString::number(willrBuyThreshold, 'f', 2)));
                } else if (allowShort && willr >= willrSellThreshold) {
                    setShortTrigger(
                        QStringLiteral("willr"),
                        QString("Williams %%R %1 >= %2")
                            .arg(QString::number(willr, 'f', 2), QString::number(willrSellThreshold, 'f', 2)));
                }
            }

            if (openSide.isEmpty()) {
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

            double cappedRequestedQty = requestedQty;
            const double storedQtyCap = dashboardRuntimeOpenQtyCaps_.value(key, 0.0);
            if (qIsFinite(storedQtyCap) && storedQtyCap > 0.0) {
                cappedRequestedQty = std::min(cappedRequestedQty, storedQtyCap);
            }
            const double orderQty = normalizeFuturesOrderQuantity(cappedRequestedQty, price, symbolFilters);
            if (!qIsFinite(orderQty) || orderQty <= 0.0) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked: normalized order quantity is invalid (requested=%4).")
                        .arg(openSide, symbol, interval, QString::number(cappedRequestedQty, 'f', 8)));
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
            const QString marginRatioText = marginRatio > 0.0
                ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
                : QStringLiteral("-");
            const QString liqText = liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");

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
                ScopedTableSortingPause sortingPause(positionsTable_);
                const int rowIdx = positionsTable_->rowCount();
                positionsTable_->insertRow(rowIdx);
                positionsTableStructureChanged = true;
                const QString nowText = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
                setTableCellText(positionsTable_, rowIdx, 0, symbol);
                setTableCellText(positionsTable_, rowIdx, 1, formatPositionSizeText(sizeUsdt, rowQty, symbol));
                setTableCellNumeric(positionsTable_, rowIdx, 1, sizeUsdt);
                setTableCellText(positionsTable_, rowIdx, 2, QString::number(markPrice, 'f', 6));
                setTableCellNumeric(positionsTable_, rowIdx, 2, markPrice);
                setTableCellText(positionsTable_, rowIdx, 3, marginRatioText);
                setTableCellNumeric(positionsTable_, rowIdx, 3, marginRatio);
                setTableCellText(positionsTable_, rowIdx, 4, liqText);
                setTableCellNumeric(positionsTable_, rowIdx, 4, liqPrice);
                setTableCellText(positionsTable_, rowIdx, 5, QString::number(displayMarginUsdt, 'f', 2));
                setTableCellNumeric(positionsTable_, rowIdx, 5, displayMarginUsdt);
                setTableCellText(positionsTable_, rowIdx, 6, formatQuantityWithSymbol(rowQty, symbol));
                setTableCellNumeric(positionsTable_, rowIdx, 6, rowQty);
                setTableCellText(positionsTable_, rowIdx, 7, "0.00 (0.00%)");
                setTableCellNumeric(positionsTable_, rowIdx, 7, 0.0);
                if (QTableWidgetItem *pnlItem = positionsTable_->item(rowIdx, 7)) {
                    setTableCellRoiBasis(pnlItem, roiBasisUsdt);
                }
                setTableCellText(positionsTable_, rowIdx, 8, interval);
                setTableCellText(positionsTable_, rowIdx, 9, indicatorDisplayName(triggerSource));
                setTableCellText(positionsTable_, rowIdx, 10, triggerText);
                setTableCellText(positionsTable_, rowIdx, 11, indicatorValueSummary);
                setTableCellText(positionsTable_, rowIdx, 12, openSide);
                setTableCellText(positionsTable_, rowIdx, 13, nowText);
                setTableCellText(positionsTable_, rowIdx, 14, "-");
                setTableCellText(
                    positionsTable_,
                    rowIdx,
                    15,
                    dashboardOverridesTable_->item(row, 7) ? dashboardOverridesTable_->item(row, 7)->text() : QStringLiteral("Disabled"));
                setTableCellText(positionsTable_, rowIdx, 16, "OPEN");
                setTableCellText(positionsTable_, rowIdx, 17, QString("Auto [%1] #%2").arg(rowConnectorCfg.key, openOrderId));
                if (QTableWidgetItem *symbolItem = positionsTable_->item(rowIdx, 0)) {
                    symbolItem->setData(kPositionsRowSequenceRole, positionsRowSequenceCounter_++);
                }
                positionsTableMutated = true;
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
        const auto shouldCloseBySource = [&](const QString &source, bool isLong) -> bool {
            if (source == QStringLiteral("stoch_rsi")) {
                if (stochRsiOk) {
                    return isLong ? (stochRsi >= stochSellThreshold) : (stochRsi <= stochBuyThreshold);
                }
                if (rsiOk) {
                    return isLong ? (rsi >= rsiSellThreshold) : (rsi <= rsiBuyThreshold);
                }
                return false;
            }
            if (source == QStringLiteral("willr")) {
                if (willrOk) {
                    return isLong ? (willr >= willrSellThreshold) : (willr <= willrBuyThreshold);
                }
                if (rsiOk) {
                    return isLong ? (rsi >= rsiSellThreshold) : (rsi <= rsiBuyThreshold);
                }
                return false;
            }
            if (!rsiOk) {
                return false;
            }
            return isLong ? (rsi >= rsiSellThreshold) : (rsi <= rsiBuyThreshold);
        };
        const bool shouldCloseLong = (openPos.side == "LONG") && shouldCloseBySource(signalSource, true);
        const bool shouldCloseShort = (openPos.side == "SHORT") && shouldCloseBySource(signalSource, false);
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
        const double markPnlUsdt = liveShare.pnlUsdt;
        const double markPnlPct = (markPnlUsdt / std::max(1e-9, openPos.roiBasisUsdt)) * 100.0;
        const double sizeUsdt = std::max(0.0, liveShare.sizeUsdt);
        const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
        const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
        const QString marginRatioText = marginRatio > 0.0
            ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
            : QStringLiteral("-");
        const QString liqText = liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");

        int targetRow = -1;
        if (positionsTable_) {
            for (int t = positionsTable_->rowCount() - 1; t >= 0; --t) {
                const QString rowSymbol = tableCellRaw(t, 0).trimmed().toUpper();
                const QString rowInterval = tableCellRaw(t, 8).trimmed();
                const QString rowStatus = tableCellRaw(t, 16).trimmed().toUpper();
                const QString rowConnectorHint = tableCellRaw(t, 17).toLower();
                if (rowSymbol == symbol
                    && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                    && rowStatus == "OPEN"
                    && rowConnectorHint.contains(rowConnectorCfg.key.toLower())) {
                    targetRow = t;
                    break;
                }
            }
        }

        if (targetRow >= 0 && positionsTable_) {
            ScopedTableSortingPause sortingPause(positionsTable_);
            const bool updateVisibleText = !positionsCumulativeView_;
            auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text, bool preserveWhenUnavailable = false) {
                QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                QString finalText = text;
                if (preserveWhenUnavailable && (text.trimmed().isEmpty() || text.trimmed() == QStringLiteral("-"))) {
                    QString existing;
                    if (item) {
                        const QVariant raw = item->data(Qt::UserRole);
                        existing = raw.isValid() ? raw.toString() : item->text();
                    }
                    existing = existing.trimmed();
                    if (!existing.isEmpty() && existing != QStringLiteral("-")) {
                        finalText = existing;
                    }
                }
                if (!item) {
                    item = new QTableWidgetItem(finalText);
                    positionsTable_->setItem(targetRow, col, item);
                } else if (updateVisibleText) {
                    item->setText(finalText);
                }
                item->setData(Qt::UserRole, finalText);
            };
            setOrCreate(1, formatPositionSizeText(sizeUsdt, rowQty, symbol));
            setOrCreate(2, QString::number(markPrice, 'f', 6));
            setOrCreate(3, marginRatioText, true);
            setOrCreate(4, liqText, true);
            setOrCreate(5, QString::number(openPos.displayMarginUsdt, 'f', 2));
            setOrCreate(6, formatQuantityWithSymbol(rowQty, symbol));
            setOrCreate(7, QString("%1 (%2%)")
                            .arg(QString::number(markPnlUsdt, 'f', 2),
                                 QString::number(markPnlPct, 'f', 2)));
            setTableCellNumeric(positionsTable_, targetRow, 1, sizeUsdt);
            setTableCellNumeric(positionsTable_, targetRow, 2, markPrice);
            setTableCellNumeric(positionsTable_, targetRow, 3, marginRatio);
            setTableCellNumeric(positionsTable_, targetRow, 4, liqPrice);
            setTableCellNumeric(positionsTable_, targetRow, 5, openPos.displayMarginUsdt);
            setTableCellNumeric(positionsTable_, targetRow, 6, rowQty);
            setTableCellNumeric(positionsTable_, targetRow, 7, markPnlUsdt);
            if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                setTableCellRoiBasis(pnlItem, openPos.roiBasisUsdt);
            }
            setOrCreate(11, indicatorValueSummary);
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
                            ScopedTableSortingPause sortingPause(positionsTable_);
                            const bool updateVisibleText = !positionsCumulativeView_;
                            auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text) {
                                QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                                if (!item) {
                                    item = new QTableWidgetItem(text);
                                    positionsTable_->setItem(targetRow, col, item);
                                } else if (updateVisibleText) {
                                    item->setText(text);
                                }
                                item->setData(Qt::UserRole, text);
                            };
                            setOrCreate(14, QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
                            setOrCreate(16, "CLOSED");
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

        if (targetRow >= 0 && positionsTable_) {
            ScopedTableSortingPause sortingPause(positionsTable_);
            const bool updateVisibleText = !positionsCumulativeView_;
            auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text) {
                QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                if (!item) {
                    item = new QTableWidgetItem(text);
                    positionsTable_->setItem(targetRow, col, item);
                } else if (updateVisibleText) {
                    item->setText(text);
                }
                item->setData(Qt::UserRole, text);
            };
            setOrCreate(2, QString::number(closePrice, 'f', 6));
            setOrCreate(7, QString("%1 (%2%)")
                            .arg(QString::number(realizedPnlUsdt, 'f', 2),
                                 QString::number(realizedPnlPct, 'f', 2)));
            setTableCellNumeric(positionsTable_, targetRow, 2, closePrice);
            setTableCellNumeric(positionsTable_, targetRow, 7, realizedPnlUsdt);
            if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                setTableCellRoiBasis(pnlItem, closeRoiBasisUsed);
            }
            if (partialClose) {
                const double remainingQty = std::max(0.0, openPos.quantity - effectiveCloseQty);
                const double remainingRatio = rowQty > 1e-9
                    ? std::min(1.0, std::max(0.0, remainingQty / rowQty))
                    : 0.0;
                const double remainingNotional = std::max(0.0, remainingQty * closePrice);
                const double remainingDisplayMarginUsdt = std::max(0.0, openPos.displayMarginUsdt * remainingRatio);
                const double remainingRoiBasisUsdt = std::max(0.0, openPos.roiBasisUsdt * remainingRatio);
                openPos.displayMarginUsdt = std::max(1e-9, remainingDisplayMarginUsdt);
                openPos.roiBasisUsdt = std::max(1e-9, remainingRoiBasisUsdt);
                setOrCreate(1, formatPositionSizeText(remainingNotional, remainingQty, symbol));
                setOrCreate(5, QString::number(remainingDisplayMarginUsdt, 'f', 2));
                setOrCreate(6, formatQuantityWithSymbol(remainingQty, symbol));
                setTableCellNumeric(positionsTable_, targetRow, 1, remainingNotional);
                setTableCellNumeric(positionsTable_, targetRow, 5, remainingDisplayMarginUsdt);
                setTableCellNumeric(positionsTable_, targetRow, 6, remainingQty);
                if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                    setTableCellRoiBasis(pnlItem, remainingRoiBasisUsdt);
                }
            } else {
                setOrCreate(14, QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
                setOrCreate(16, "CLOSED");
            }
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
    refreshDashboardWaitingQueueTable();

    flushPendingPositionsView();
    refreshPositionsSummaryLabels();
}


