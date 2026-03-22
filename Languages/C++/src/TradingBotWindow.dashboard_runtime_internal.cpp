#include "TradingBotWindow.dashboard_runtime_internal.h"

#include "TradingBotWindow.dashboard_runtime_shared.h"

#include <QMap>
#include <QRegularExpression>
#include <QSet>
#include <QStringList>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QVector>
#include <QVariantMap>
#include <QWidget>

#include <algorithm>

namespace TradingBotWindowDashboardRuntimeDetail {

using namespace TradingBotWindowDashboardRuntime;

namespace {
constexpr int kPositionsRowSequenceRole = Qt::UserRole + 3;

QString formatMarginRatioText(double marginRatio) {
    return marginRatio > 0.0
        ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
        : QStringLiteral("-");
}

QString formatLiquidationText(double liqPrice) {
    return liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");
}

void setOrCreatePositionCellText(
    QTableWidget *table,
    bool updateVisibleText,
    int row,
    int col,
    const QString &text,
    bool preserveWhenUnavailable = false) {
    if (!table || row < 0) {
        return;
    }

    QTableWidgetItem *item = table->item(row, col);
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
        table->setItem(row, col, item);
    } else if (updateVisibleText) {
        item->setText(finalText);
    }
    item->setData(Qt::UserRole, finalText);
}
} // namespace

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

ScopedTableSortingPause::ScopedTableSortingPause(QTableWidget *table)
    : table_(table),
      restoreSorting_(table_ && table_->isSortingEnabled()) {
    if (restoreSorting_) {
        table_->setSortingEnabled(false);
    }
}

ScopedTableSortingPause::~ScopedTableSortingPause() {
    if (restoreSorting_ && table_) {
        table_->setSortingEnabled(true);
    }
}

ScopedTableUpdatesPause::ScopedTableUpdatesPause(QTableWidget *table, bool enabled)
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

ScopedTableUpdatesPause::~ScopedTableUpdatesPause() {
    if (viewport_ && viewportUpdatesWereEnabled_) {
        viewport_->setUpdatesEnabled(true);
        viewport_->update();
    }
    if (table_ && tableUpdatesWereEnabled_) {
        table_->setUpdatesEnabled(true);
        table_->update();
    }
}

QString tableCellRaw(const QTableWidget *table, int row, int col) {
    if (!table) {
        return {};
    }
    const QTableWidgetItem *item = table->item(row, col);
    if (!item) {
        return {};
    }
    const QVariant raw = item->data(Qt::UserRole);
    return raw.isValid() ? raw.toString() : item->text();
}

int findOpenPositionRow(const QTableWidget *table, const QString &symbol, const QString &interval, const QString &connectorKey) {
    if (!table) {
        return -1;
    }

    const QString symbolKey = symbol.trimmed().toUpper();
    const QString intervalKey = interval.trimmed();
    const QString connectorKeyNorm = connectorKey.trimmed().toLower();
    for (int row = table->rowCount() - 1; row >= 0; --row) {
        const QString rowSymbol = tableCellRaw(table, row, 0).trimmed().toUpper();
        const QString rowInterval = tableCellRaw(table, row, 8).trimmed();
        const QString rowStatus = tableCellRaw(table, row, 16).trimmed().toUpper();
        const QString rowConnectorHint = tableCellRaw(table, row, 17).toLower();
        if (rowSymbol == symbolKey
            && rowInterval.compare(intervalKey, Qt::CaseInsensitive) == 0
            && rowStatus == QStringLiteral("OPEN")
            && rowConnectorHint.contains(connectorKeyNorm)) {
            return row;
        }
    }
    return -1;
}

void refreshActivePositionRow(QTableWidget *table, bool cumulativeView, int row, const PositionTableActiveRowData &data) {
    if (!table || row < 0) {
        return;
    }

    ScopedTableSortingPause sortingPause(table);
    const bool updateVisibleText = !cumulativeView;
    setOrCreatePositionCellText(table, updateVisibleText, row, 1, formatPositionSizeText(data.sizeUsdt, data.quantity, data.symbol));
    setOrCreatePositionCellText(table, updateVisibleText, row, 2, QString::number(data.markPrice, 'f', 6));
    setOrCreatePositionCellText(table, updateVisibleText, row, 3, formatMarginRatioText(data.marginRatio), true);
    setOrCreatePositionCellText(table, updateVisibleText, row, 4, formatLiquidationText(data.liqPrice), true);
    setOrCreatePositionCellText(table, updateVisibleText, row, 5, QString::number(data.displayMarginUsdt, 'f', 2));
    setOrCreatePositionCellText(table, updateVisibleText, row, 6, formatQuantityWithSymbol(data.quantity, data.symbol));
    setOrCreatePositionCellText(
        table,
        updateVisibleText,
        row,
        7,
        QStringLiteral("%1 (%2%)")
            .arg(QString::number(data.pnlUsdt, 'f', 2),
                 QString::number((data.pnlUsdt / std::max(1e-9, data.roiBasisUsdt)) * 100.0, 'f', 2)));
    setOrCreatePositionCellText(table, updateVisibleText, row, 11, data.indicatorValueSummary, true);
    setTableCellNumeric(table, row, 1, data.sizeUsdt);
    setTableCellNumeric(table, row, 2, data.markPrice);
    setTableCellNumeric(table, row, 3, data.marginRatio);
    setTableCellNumeric(table, row, 4, data.liqPrice);
    setTableCellNumeric(table, row, 5, data.displayMarginUsdt);
    setTableCellNumeric(table, row, 6, data.quantity);
    setTableCellNumeric(table, row, 7, data.pnlUsdt);
    if (QTableWidgetItem *pnlItem = table->item(row, 7)) {
        setTableCellRoiBasis(pnlItem, data.roiBasisUsdt);
    }
}

void setPositionIndicatorValueSummary(QTableWidget *table, bool cumulativeView, int row, const QString &indicatorValueSummary) {
    if (!table || row < 0) {
        return;
    }

    ScopedTableSortingPause sortingPause(table);
    setOrCreatePositionCellText(table, !cumulativeView, row, 11, indicatorValueSummary, true);
}

bool appendOpenPositionRow(QTableWidget *table, qint64 &rowSequenceCounter, const PositionTableOpenRowData &data) {
    if (!table) {
        return false;
    }

    ScopedTableSortingPause sortingPause(table);
    const int row = table->rowCount();
    table->insertRow(row);
    setTableCellText(table, row, 0, data.symbol);
    setTableCellText(table, row, 1, formatPositionSizeText(data.sizeUsdt, data.quantity, data.symbol));
    setTableCellNumeric(table, row, 1, data.sizeUsdt);
    setTableCellText(table, row, 2, QString::number(data.markPrice, 'f', 6));
    setTableCellNumeric(table, row, 2, data.markPrice);
    setTableCellText(table, row, 3, formatMarginRatioText(data.marginRatio));
    setTableCellNumeric(table, row, 3, data.marginRatio);
    setTableCellText(table, row, 4, formatLiquidationText(data.liqPrice));
    setTableCellNumeric(table, row, 4, data.liqPrice);
    setTableCellText(table, row, 5, QString::number(data.displayMarginUsdt, 'f', 2));
    setTableCellNumeric(table, row, 5, data.displayMarginUsdt);
    setTableCellText(table, row, 6, formatQuantityWithSymbol(data.quantity, data.symbol));
    setTableCellNumeric(table, row, 6, data.quantity);
    setTableCellText(table, row, 7, QStringLiteral("0.00 (0.00%)"));
    setTableCellNumeric(table, row, 7, 0.0);
    if (QTableWidgetItem *pnlItem = table->item(row, 7)) {
        setTableCellRoiBasis(pnlItem, data.roiBasisUsdt);
    }
    setTableCellText(table, row, 8, data.interval);
    setTableCellText(table, row, 9, indicatorDisplayName(data.triggerSource));
    setTableCellText(table, row, 10, data.triggerText);
    setTableCellText(table, row, 11, data.indicatorValueSummary);
    setTableCellText(table, row, 12, data.openSide);
    setTableCellText(table, row, 13, data.openedAtText);
    setTableCellText(table, row, 14, QStringLiteral("-"));
    setTableCellText(table, row, 15, data.stopLossText);
    setTableCellText(table, row, 16, QStringLiteral("OPEN"));
    setTableCellText(table, row, 17, QStringLiteral("Auto [%1] #%2").arg(data.connectorKey, data.openOrderId));
    if (QTableWidgetItem *symbolItem = table->item(row, 0)) {
        symbolItem->setData(kPositionsRowSequenceRole, rowSequenceCounter++);
    }
    return true;
}

void markPositionClosedRow(QTableWidget *table, bool cumulativeView, int row, const QString &closedAtText) {
    if (!table || row < 0) {
        return;
    }

    ScopedTableSortingPause sortingPause(table);
    const bool updateVisibleText = !cumulativeView;
    setOrCreatePositionCellText(table, updateVisibleText, row, 14, closedAtText);
    setOrCreatePositionCellText(table, updateVisibleText, row, 16, QStringLiteral("CLOSED"));
}

void applyCloseToPositionRow(QTableWidget *table, bool cumulativeView, int row, const PositionTableCloseRowData &data) {
    if (!table || row < 0) {
        return;
    }

    ScopedTableSortingPause sortingPause(table);
    const bool updateVisibleText = !cumulativeView;
    setOrCreatePositionCellText(table, updateVisibleText, row, 2, QString::number(data.closePrice, 'f', 6));
    setOrCreatePositionCellText(
        table,
        updateVisibleText,
        row,
        7,
        QStringLiteral("%1 (%2%)")
            .arg(QString::number(data.realizedPnlUsdt, 'f', 2),
                 QString::number(data.realizedPnlPct, 'f', 2)));
    setTableCellNumeric(table, row, 2, data.closePrice);
    setTableCellNumeric(table, row, 7, data.realizedPnlUsdt);
    if (QTableWidgetItem *pnlItem = table->item(row, 7)) {
        setTableCellRoiBasis(pnlItem, data.partialClose ? data.remainingRoiBasisUsdt : data.closeRoiBasisUsed);
    }

    if (data.partialClose) {
        setOrCreatePositionCellText(table, updateVisibleText, row, 1, formatPositionSizeText(data.remainingNotional, data.remainingQty, data.symbol));
        setOrCreatePositionCellText(table, updateVisibleText, row, 5, QString::number(data.remainingDisplayMarginUsdt, 'f', 2));
        setOrCreatePositionCellText(table, updateVisibleText, row, 6, formatQuantityWithSymbol(data.remainingQty, data.symbol));
        setTableCellNumeric(table, row, 1, data.remainingNotional);
        setTableCellNumeric(table, row, 5, data.remainingDisplayMarginUsdt);
        setTableCellNumeric(table, row, 6, data.remainingQty);
        if (QTableWidgetItem *pnlItem = table->item(row, 7)) {
            setTableCellRoiBasis(pnlItem, data.remainingRoiBasisUsdt);
        }
        return;
    }

    setOrCreatePositionCellText(table, updateVisibleText, row, 14, data.closedAtText);
    setOrCreatePositionCellText(table, updateVisibleText, row, 16, QStringLiteral("CLOSED"));
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

QString runtimeKeyFor(const QString &symbol, const QString &interval, const QString &connectorToken) {
    return symbol.trimmed().toUpper()
        + QStringLiteral("|")
        + interval.trimmed().toLower()
        + QStringLiteral("|")
        + connectorToken.trimmed().toLower();
}

qint64 loopSecondsFromText(QString loopText) {
    loopText = loopText.trimmed().toLower();
    if (TradingBotWindowDashboardRuntime::loopTextRequestsInstant(loopText)) {
        return 0;
    }
    if (loopText.isEmpty() || loopText == QStringLiteral("off") || loopText == QStringLiteral("auto")) {
        return 60;
    }

    static const QRegularExpression compactRe(QStringLiteral("^(\\d+)\\s*([smhdw])$"));
    QRegularExpressionMatch compactMatch = compactRe.match(loopText);
    if (compactMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = compactMatch.captured(1).toLongLong(&ok);
        if (ok && value > 0) {
            const QString unit = compactMatch.captured(2);
            if (unit == QStringLiteral("s")) return value;
            if (unit == QStringLiteral("m")) return value * 60;
            if (unit == QStringLiteral("h")) return value * 3600;
            if (unit == QStringLiteral("d")) return value * 86400;
            if (unit == QStringLiteral("w")) return value * 604800;
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
            if (unit.startsWith(QStringLiteral("s"))) return value;
            if (unit.startsWith(QStringLiteral("m"))) return value * 60;
            if (unit.startsWith(QStringLiteral("h"))) return value * 3600;
            if (unit.startsWith(QStringLiteral("d"))) return value * 86400;
            if (unit.startsWith(QStringLiteral("w"))) return value * 604800;
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
        if (unit == QStringLiteral("s") || unit == QStringLiteral("sec") || unit == QStringLiteral("second") || unit == QStringLiteral("seconds")) return value;
        if (unit == QStringLiteral("m") || unit == QStringLiteral("min") || unit == QStringLiteral("minute") || unit == QStringLiteral("minutes")) return value * 60;
        if (unit == QStringLiteral("h") || unit == QStringLiteral("hour") || unit == QStringLiteral("hours")) return value * 3600;
        if (unit == QStringLiteral("d") || unit == QStringLiteral("day") || unit == QStringLiteral("days")) return value * 86400;
        if (unit == QStringLiteral("w") || unit == QStringLiteral("week") || unit == QStringLiteral("weeks")) return value * 604800;
        if (unit == QStringLiteral("mo") || unit == QStringLiteral("month") || unit == QStringLiteral("months")) return value * 2592000;
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

QString normalizeBinanceKlineInterval(QString intervalText, QString *warningOut) {
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

IndicatorRuntimeSettings buildIndicatorRuntimeSettings(const QMap<QString, QVariantMap> &indicatorParams) {
    const auto indicatorParamDouble =
        [&indicatorParams](const QString &indicatorKey, const QString &fieldKey, double fallback) -> double {
        const QVariantMap cfg = indicatorParams.value(indicatorKey);
        if (!cfg.contains(fieldKey)) {
            return fallback;
        }
        bool ok = false;
        const double value = cfg.value(fieldKey).toDouble(&ok);
        return (ok && qIsFinite(value)) ? value : fallback;
    };
    const auto indicatorParamInt =
        [&indicatorParams](const QString &indicatorKey, const QString &fieldKey, int fallback) -> int {
        const QVariantMap cfg = indicatorParams.value(indicatorKey);
        if (!cfg.contains(fieldKey)) {
            return fallback;
        }
        bool ok = false;
        const int value = cfg.value(fieldKey).toInt(&ok);
        return (ok && value > 0) ? value : fallback;
    };

    IndicatorRuntimeSettings settings;

    settings.rsiBuyThreshold = indicatorParamDouble(QStringLiteral("rsi"), QStringLiteral("buy_value"), 30.0);
    settings.rsiSellThreshold = indicatorParamDouble(QStringLiteral("rsi"), QStringLiteral("sell_value"), 70.0);
    if (settings.rsiBuyThreshold < 0.0 || settings.rsiBuyThreshold > 100.0
        || settings.rsiSellThreshold < 0.0 || settings.rsiSellThreshold > 100.0
        || settings.rsiBuyThreshold >= settings.rsiSellThreshold) {
        settings.rsiBuyThreshold = 30.0;
        settings.rsiSellThreshold = 70.0;
    }

    settings.stochBuyThreshold = indicatorParamDouble(QStringLiteral("stoch_rsi"), QStringLiteral("buy_value"), 20.0);
    settings.stochSellThreshold = indicatorParamDouble(QStringLiteral("stoch_rsi"), QStringLiteral("sell_value"), 80.0);
    if (settings.stochBuyThreshold < 0.0 || settings.stochBuyThreshold > 100.0
        || settings.stochSellThreshold < 0.0 || settings.stochSellThreshold > 100.0
        || settings.stochBuyThreshold >= settings.stochSellThreshold) {
        settings.stochBuyThreshold = 20.0;
        settings.stochSellThreshold = 80.0;
    }

    settings.willrBuyThreshold = indicatorParamDouble(QStringLiteral("willr"), QStringLiteral("buy_value"), -80.0);
    settings.willrSellThreshold = indicatorParamDouble(QStringLiteral("willr"), QStringLiteral("sell_value"), -20.0);
    settings.willrBuyThreshold = std::max(-100.0, std::min(0.0, settings.willrBuyThreshold));
    settings.willrSellThreshold = std::max(-100.0, std::min(0.0, settings.willrSellThreshold));
    if (settings.willrBuyThreshold >= settings.willrSellThreshold) {
        settings.willrBuyThreshold = -80.0;
        settings.willrSellThreshold = -20.0;
    }

    settings.rsiLength = std::max(2, indicatorParamInt(QStringLiteral("rsi"), QStringLiteral("length"), 14));
    settings.stochLength = std::max(2, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("length"), 14));
    settings.stochSmoothK = std::max(1, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("smooth_k"), 3));
    settings.stochSmoothD = std::max(1, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("smooth_d"), 3));
    settings.willrLength = std::max(2, indicatorParamInt(QStringLiteral("willr"), QStringLiteral("length"), 14));

    return settings;
}

QString formatIndicatorValueSummary(const IndicatorRuntimeValues &values) {
    QStringList parts;
    if (values.useRsi && values.rsiOk) {
        parts << QStringLiteral("RSI %1").arg(QString::number(values.rsi, 'f', 2));
    }
    if (values.useStochRsi && values.stochRsiOk) {
        parts << QStringLiteral("StochRSI %1").arg(QString::number(values.stochRsi, 'f', 2));
    }
    if (values.useWillr && values.willrOk) {
        parts << QStringLiteral("W%R %1").arg(QString::number(values.willr, 'f', 2));
    }
    return parts.isEmpty() ? QStringLiteral("-") : parts.join(QStringLiteral(" | "));
}

QString formatIndicatorValueSummaryForSource(const IndicatorRuntimeValues &values, const QString &indicatorSource) {
    const QString sourceKey = TradingBotWindowDashboardRuntime::normalizedIndicatorKey(indicatorSource);
    if (sourceKey == QStringLiteral("rsi")) {
        return formatIndicatorValueSummary(IndicatorRuntimeValues{
            true,
            false,
            false,
            values.rsiOk,
            false,
            false,
            values.rsi,
            0.0,
            0.0,
        });
    }
    if (sourceKey == QStringLiteral("stoch_rsi")) {
        return formatIndicatorValueSummary(IndicatorRuntimeValues{
            false,
            true,
            false,
            false,
            values.stochRsiOk,
            false,
            0.0,
            values.stochRsi,
            0.0,
        });
    }
    if (sourceKey == QStringLiteral("willr")) {
        return formatIndicatorValueSummary(IndicatorRuntimeValues{
            false,
            false,
            true,
            false,
            false,
            values.willrOk,
            0.0,
            0.0,
            values.willr,
        });
    }
    return formatIndicatorValueSummary(values);
}

OpenSignalDecision determineOpenSignal(
    const IndicatorRuntimeValues &values,
    const IndicatorRuntimeSettings &settings,
    bool allowLong,
    bool allowShort) {
    OpenSignalDecision decision;
    auto setLongTrigger = [&decision](const QString &source, const QString &text) {
        decision.side = QStringLiteral("LONG");
        decision.triggerSource = source;
        decision.triggerText = text;
    };
    auto setShortTrigger = [&decision](const QString &source, const QString &text) {
        decision.side = QStringLiteral("SHORT");
        decision.triggerSource = source;
        decision.triggerText = text;
    };

    if (values.useRsi && values.rsiOk) {
        if (allowLong && values.rsi <= settings.rsiBuyThreshold) {
            setLongTrigger(
                QStringLiteral("rsi"),
                QStringLiteral("RSI %1 <= %2")
                    .arg(QString::number(values.rsi, 'f', 2), QString::number(settings.rsiBuyThreshold, 'f', 2)));
        } else if (allowShort && values.rsi >= settings.rsiSellThreshold) {
            setShortTrigger(
                QStringLiteral("rsi"),
                QStringLiteral("RSI %1 >= %2")
                    .arg(QString::number(values.rsi, 'f', 2), QString::number(settings.rsiSellThreshold, 'f', 2)));
        }
    }
    if (!decision.hasSignal() && values.useStochRsi && values.stochRsiOk) {
        if (allowLong && values.stochRsi <= settings.stochBuyThreshold) {
            setLongTrigger(
                QStringLiteral("stoch_rsi"),
                QStringLiteral("StochRSI %1 <= %2")
                    .arg(QString::number(values.stochRsi, 'f', 2), QString::number(settings.stochBuyThreshold, 'f', 2)));
        } else if (allowShort && values.stochRsi >= settings.stochSellThreshold) {
            setShortTrigger(
                QStringLiteral("stoch_rsi"),
                QStringLiteral("StochRSI %1 >= %2")
                    .arg(QString::number(values.stochRsi, 'f', 2), QString::number(settings.stochSellThreshold, 'f', 2)));
        }
    }
    if (!decision.hasSignal() && values.useWillr && values.willrOk) {
        if (allowLong && values.willr <= settings.willrBuyThreshold) {
            setLongTrigger(
                QStringLiteral("willr"),
                QStringLiteral("Williams %%R %1 <= %2")
                    .arg(QString::number(values.willr, 'f', 2), QString::number(settings.willrBuyThreshold, 'f', 2)));
        } else if (allowShort && values.willr >= settings.willrSellThreshold) {
            setShortTrigger(
                QStringLiteral("willr"),
                QStringLiteral("Williams %%R %1 >= %2")
                    .arg(QString::number(values.willr, 'f', 2), QString::number(settings.willrSellThreshold, 'f', 2)));
        }
    }

    return decision;
}

bool shouldCloseBySource(
    const QString &source,
    bool isLong,
    const IndicatorRuntimeValues &values,
    const IndicatorRuntimeSettings &settings) {
    if (source == QStringLiteral("stoch_rsi")) {
        if (values.stochRsiOk) {
            return isLong
                ? (values.stochRsi >= settings.stochSellThreshold)
                : (values.stochRsi <= settings.stochBuyThreshold);
        }
        if (values.rsiOk) {
            return isLong
                ? (values.rsi >= settings.rsiSellThreshold)
                : (values.rsi <= settings.rsiBuyThreshold);
        }
        return false;
    }
    if (source == QStringLiteral("willr")) {
        if (values.willrOk) {
            return isLong
                ? (values.willr >= settings.willrSellThreshold)
                : (values.willr <= settings.willrBuyThreshold);
        }
        if (values.rsiOk) {
            return isLong
                ? (values.rsi >= settings.rsiSellThreshold)
                : (values.rsi <= settings.rsiBuyThreshold);
        }
        return false;
    }
    if (!values.rsiOk) {
        return false;
    }
    return isLong
        ? (values.rsi >= settings.rsiSellThreshold)
        : (values.rsi <= settings.rsiBuyThreshold);
}

} // namespace TradingBotWindowDashboardRuntimeDetail
