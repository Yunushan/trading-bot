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


namespace TradingBotWindowDashboardRuntime {
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

} // namespace TradingBotWindowDashboardRuntime
