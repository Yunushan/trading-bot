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

void pumpUiEvents(int maxMs) {
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

bool strategyUsesLiveCandles(const QString &summary) {
    return summary.trimmed().toLower().contains(QStringLiteral("live candles"));
}

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

double latestRsiValue(const QVector<BinanceRestClient::KlineCandle> &candles, int period, bool *okOut) {
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
    bool *okOut) {
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

double latestWilliamsRValue(const QVector<BinanceRestClient::KlineCandle> &candles, int length, bool *okOut) {
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
    double referencePrice) {
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

} // namespace TradingBotWindowDashboardRuntime
