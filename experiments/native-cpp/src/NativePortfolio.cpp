#include "NativePortfolio.h"

#include <QDateTime>
#include <QMap>
#include <QSet>
#include <QStringList>

#include <algorithm>
#include <cmath>
#include <limits>

namespace {

QString nonEmptyOr(const QString &value, const QString &fallback) {
    const QString text = value.trimmed();
    return text.isEmpty() ? fallback : text;
}

QString normalizedSymbol(const QString &value) {
    const QString symbol = value.trimmed().toUpper();
    return symbol.isEmpty() ? QStringLiteral("Unknown") : symbol;
}

QString normalizedSide(const QString &value) {
    const QString side = value.trimmed().toUpper();
    return side.isEmpty() ? QStringLiteral("Unknown") : side;
}

QJsonValue finiteNumberOrNull(const QJsonValue &value) {
    if (value.isNull() || value.isUndefined()) {
        return QJsonValue();
    }
    bool ok = false;
    const double number = value.isDouble()
        ? value.toDouble()
        : value.toVariant().toString().trimmed().toDouble(&ok);
    if ((value.isDouble() || ok) && std::isfinite(number)) {
        return number;
    }
    return QJsonValue();
}

double finiteNumberOr(const QJsonValue &value, double fallback = 0.0) {
    const QJsonValue number = finiteNumberOrNull(value);
    return number.isDouble() ? number.toDouble() : fallback;
}

QString nowIso() {
    return QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
}

QJsonObject compactObject(const std::initializer_list<QPair<QString, QJsonValue>> &items) {
    QJsonObject out;
    for (const auto &item : items) {
        out.insert(item.first, item.second);
    }
    return out;
}

QJsonObject recordData(const QJsonObject &record) {
    return record.value(QStringLiteral("data")).toObject();
}

QString recordSymbol(const QJsonObject &record) {
    const QJsonObject data = recordData(record);
    return normalizedSymbol(record.value(QStringLiteral("symbol")).toString(data.value(QStringLiteral("symbol")).toString()));
}

QString recordSide(const QJsonObject &record) {
    const QJsonObject data = recordData(record);
    return normalizedSide(record.value(QStringLiteral("side_key")).toString(data.value(QStringLiteral("side_key")).toString()));
}

QString recordKey(const QJsonObject &record) {
    return NativePortfolio::serializePositionKey(recordSymbol(record), recordSide(record));
}

QJsonArray normalizedTriggerIndicators(const QJsonArray &values) {
    QStringList items;
    for (const QJsonValue &value : values) {
        const QString text = value.toString().trimmed().toLower();
        if (!text.isEmpty() && !items.contains(text)) {
            items.append(text);
        }
    }
    items.sort();
    QJsonArray out;
    for (const QString &item : items) {
        out.append(item);
    }
    return out;
}

QString allocationInterval(const QJsonObject &entry) {
    return nonEmptyOr(
        entry.value(QStringLiteral("interval_display")).toString(),
        entry.value(QStringLiteral("interval")).toString());
}

QString allocationIdentity(const QJsonObject &entry) {
    QStringList tokens;
    for (const QString &field : {
             QStringLiteral("trade_id"),
             QStringLiteral("client_order_id"),
             QStringLiteral("order_id"),
             QStringLiteral("event_uid"),
             QStringLiteral("context_key"),
             QStringLiteral("slot_id"),
             QStringLiteral("open_time"),
         }) {
        const QString value = entry.value(field).toString().trimmed();
        if (!value.isEmpty()) {
            tokens.append(field + QStringLiteral("=") + value);
        }
    }
    return tokens.join(QLatin1Char('|'));
}

bool identityMatches(const QJsonObject &entry, const QJsonObject &target) {
    if (target.isEmpty()) {
        return false;
    }
    for (const QString &field : {
             QStringLiteral("trade_id"),
             QStringLiteral("client_order_id"),
             QStringLiteral("order_id"),
             QStringLiteral("event_uid"),
         }) {
        const QString expected = target.value(field).toString().trimmed();
        if (!expected.isEmpty() && entry.value(field).toString().trimmed() == expected) {
            return true;
        }
    }
    const QString targetSlot = target.value(QStringLiteral("slot_id")).toString().trimmed();
    if (!targetSlot.isEmpty() && entry.value(QStringLiteral("slot_id")).toString().trimmed() == targetSlot) {
        const QString targetContext = target.value(QStringLiteral("context_key")).toString().trimmed();
        const QString entryContext = entry.value(QStringLiteral("context_key")).toString().trimmed();
        return targetContext.isEmpty() || entryContext.isEmpty() || targetContext == entryContext;
    }
    const QString targetContext = target.value(QStringLiteral("context_key")).toString().trimmed();
    if (!targetContext.isEmpty() && entry.value(QStringLiteral("context_key")).toString().trimmed() == targetContext) {
        const QString targetOpen = target.value(QStringLiteral("open_time")).toString().trimmed();
        const QString entryOpen = entry.value(QStringLiteral("open_time")).toString().trimmed();
        return targetOpen.isEmpty() || entryOpen.isEmpty() || targetOpen == entryOpen;
    }
    const QString targetOpen = target.value(QStringLiteral("open_time")).toString().trimmed();
    return !targetOpen.isEmpty() && entry.value(QStringLiteral("open_time")).toString().trimmed() == targetOpen;
}

bool intervalMatches(const QJsonObject &entry, const QString &interval) {
    return interval.trimmed().isEmpty()
        || allocationInterval(entry).compare(interval.trimmed(), Qt::CaseInsensitive) == 0;
}

void scaleAllocationFields(QJsonObject &entry, double ratio) {
    if (!std::isfinite(ratio) || ratio < 0.0) {
        return;
    }
    for (const QString &field : {
             QStringLiteral("margin_usdt"),
             QStringLiteral("margin_balance"),
             QStringLiteral("notional"),
             QStringLiteral("size_usdt"),
         }) {
        const double value = finiteNumberOr(entry.value(field));
        if (value > 0.0) {
            entry.insert(field, std::max(0.0, value * ratio));
        }
    }
}

QJsonArray collectAllocations(const QJsonArray &allocations) {
    QMap<QString, QJsonObject> byKey;
    for (const QJsonValue &value : allocations) {
        if (!value.isObject()) {
            continue;
        }
        QJsonObject entry = value.toObject();
        if (entry.value(QStringLiteral("interval")).toString().trimmed().isEmpty()) {
            const QString display = entry.value(QStringLiteral("interval_display")).toString().trimmed();
            if (!display.isEmpty()) {
                entry.insert(QStringLiteral("interval"), display);
            }
        }
        entry.insert(
            QStringLiteral("trigger_indicators"),
            normalizedTriggerIndicators(entry.value(QStringLiteral("trigger_indicators")).toArray()));
        const QString key = QStringLiteral("%1|%2|%3")
            .arg(entry.value(QStringLiteral("ledger_id")).toString().trimmed(),
                 allocationInterval(entry).toLower(),
                 allocationIdentity(entry));
        if (byKey.contains(key)) {
            QJsonObject existing = byKey.value(key);
            existing.insert(
                QStringLiteral("qty"),
                std::max(finiteNumberOr(existing.value(QStringLiteral("qty"))), finiteNumberOr(entry.value(QStringLiteral("qty")))));
            existing.insert(
                QStringLiteral("margin_usdt"),
                std::max(finiteNumberOr(existing.value(QStringLiteral("margin_usdt"))), finiteNumberOr(entry.value(QStringLiteral("margin_usdt")))));
            existing.insert(
                QStringLiteral("notional"),
                std::max(finiteNumberOr(existing.value(QStringLiteral("notional"))), finiteNumberOr(entry.value(QStringLiteral("notional")))));
            byKey.insert(key, existing);
        } else {
            byKey.insert(key, entry);
        }
    }
    QJsonArray out;
    for (const QJsonObject &entry : byKey) {
        out.append(entry);
    }
    return out;
}

} // namespace

namespace NativePortfolio {

QString serializePositionKey(const QString &symbol, const QString &sideKey) {
    return QStringLiteral("%1:%2").arg(symbol.trimmed().toUpper(), sideKey.trimmed().toUpper());
}

QString sideLabel(const QString &sideKey) {
    const QString side = sideKey.trimmed().toUpper();
    if (side == QStringLiteral("L")) return QStringLiteral("Long");
    if (side == QStringLiteral("S")) return QStringLiteral("Short");
    if (side == QStringLiteral("SPOT")) return QStringLiteral("Spot");
    return side.isEmpty() ? QStringLiteral("Unknown") : side;
}

QJsonObject buildPositionSnapshot(const QJsonObject &record) {
    const QJsonObject data = recordData(record);
    const QString sideKey = recordSide(record);
    QJsonValue leverage = finiteNumberOrNull(record.value(QStringLiteral("leverage")));
    if (leverage.isNull() || leverage.toDouble() <= 0.0) {
        leverage = finiteNumberOrNull(data.value(QStringLiteral("leverage")));
    }
    return compactObject({
        {QStringLiteral("symbol"), recordSymbol(record)},
        {QStringLiteral("side_key"), sideKey},
        {QStringLiteral("side_label"), sideLabel(sideKey)},
        {QStringLiteral("interval"), nonEmptyOr(
             record.value(QStringLiteral("entry_tf")).toString(),
             nonEmptyOr(data.value(QStringLiteral("interval_display")).toString(), data.value(QStringLiteral("interval")).toString(QStringLiteral("-"))))},
        {QStringLiteral("quantity"), finiteNumberOrNull(data.value(QStringLiteral("qty")))},
        {QStringLiteral("mark_price"), finiteNumberOrNull(data.value(QStringLiteral("mark")))},
        {QStringLiteral("size_usdt"), finiteNumberOrNull(data.value(QStringLiteral("size_usdt")).isUndefined() ? data.value(QStringLiteral("value")) : data.value(QStringLiteral("size_usdt")))},
        {QStringLiteral("margin_usdt"), finiteNumberOrNull(data.value(QStringLiteral("margin_usdt")))},
        {QStringLiteral("pnl_value"), finiteNumberOrNull(data.value(QStringLiteral("pnl_value")))},
        {QStringLiteral("roi_percent"), finiteNumberOrNull(data.value(QStringLiteral("roi_percent")))},
        {QStringLiteral("leverage"), leverage.isDouble() && leverage.toDouble() > 0.0 ? QJsonValue(static_cast<int>(leverage.toDouble())) : QJsonValue()},
        {QStringLiteral("liquidation_price"), finiteNumberOrNull(record.value(QStringLiteral("liquidation_price")).isUndefined()
             ? data.value(QStringLiteral("liquidation_price"))
             : record.value(QStringLiteral("liquidation_price")))},
        {QStringLiteral("status"), nonEmptyOr(record.value(QStringLiteral("status")).toString(), QStringLiteral("Active"))},
        {QStringLiteral("stop_loss_enabled"), record.value(QStringLiteral("stop_loss_enabled")).toBool(false)},
        {QStringLiteral("open_time"), nonEmptyOr(record.value(QStringLiteral("open_time")).toString(), data.value(QStringLiteral("open_time")).toString(QStringLiteral("-")))},
        {QStringLiteral("close_time"), nonEmptyOr(record.value(QStringLiteral("close_time")).toString(), data.value(QStringLiteral("close_time")).toString(QStringLiteral("-")))},
    });
}

QJsonObject buildPortfolioSnapshot(
    const QJsonObject &config,
    const QJsonObject &openPositionRecords,
    const QJsonArray &closedPositionRecords,
    const QJsonObject &closedTradeRegistry,
    const QJsonValue &totalBalance,
    const QJsonValue &availableBalance,
    const QString &source,
    const QString &generatedAt) {
    QJsonArray positions;
    QStringList sortable;
    QMap<QString, QJsonObject> sorted;
    double activePnl = 0.0;
    double activeMargin = 0.0;
    bool activePnlFound = false;
    bool activeMarginFound = false;
    for (auto it = openPositionRecords.constBegin(); it != openPositionRecords.constEnd(); ++it) {
        if (!it.value().isObject()) {
            continue;
        }
        const QJsonObject record = it.value().toObject();
        const QJsonObject snapshot = buildPositionSnapshot(record);
        const QString key = QStringLiteral("%1|%2|%3|%4")
            .arg(snapshot.value(QStringLiteral("symbol")).toString(),
                 snapshot.value(QStringLiteral("side_key")).toString(),
                 snapshot.value(QStringLiteral("interval")).toString(),
                 snapshot.value(QStringLiteral("open_time")).toString());
        sortable.append(key);
        sorted.insert(key, snapshot);
        const QJsonObject data = recordData(record);
        const QJsonValue pnl = finiteNumberOrNull(data.value(QStringLiteral("pnl_value")));
        if (pnl.isDouble()) {
            activePnl += pnl.toDouble();
            activePnlFound = true;
        }
        const QJsonValue margin = finiteNumberOrNull(data.value(QStringLiteral("margin_usdt")));
        if (margin.isDouble() && margin.toDouble() > 0.0) {
            activeMargin += margin.toDouble();
            activeMarginFound = true;
        }
    }
    sortable.sort();
    for (const QString &key : sortable) {
        positions.append(sorted.value(key));
    }

    double closedPnl = 0.0;
    double closedMargin = 0.0;
    bool closedPnlFound = false;
    bool closedMarginFound = false;
    for (auto it = closedTradeRegistry.constBegin(); it != closedTradeRegistry.constEnd(); ++it) {
        if (!it.value().isObject()) {
            continue;
        }
        const QJsonObject entry = it.value().toObject();
        const QJsonValue pnl = finiteNumberOrNull(entry.value(QStringLiteral("pnl_value")));
        if (pnl.isDouble()) {
            closedPnl += pnl.toDouble();
            closedPnlFound = true;
        }
        const QJsonValue margin = finiteNumberOrNull(entry.value(QStringLiteral("margin_usdt")));
        if (margin.isDouble() && margin.toDouble() > 0.0) {
            closedMargin += margin.toDouble();
            closedMarginFound = true;
        }
    }

    int closedCount = closedPositionRecords.size();
    if (closedCount <= 0) {
        closedCount = closedTradeRegistry.size();
    }
    return compactObject({
        {QStringLiteral("account_type"), nonEmptyOr(config.value(QStringLiteral("account_type")).toString(), QStringLiteral("Unknown"))},
        {QStringLiteral("open_position_count"), positions.size()},
        {QStringLiteral("closed_position_count"), std::max(0, closedCount)},
        {QStringLiteral("active_pnl"), activePnlFound ? QJsonValue(activePnl) : QJsonValue()},
        {QStringLiteral("active_margin"), activeMarginFound && activeMargin > 0.0 ? QJsonValue(activeMargin) : QJsonValue()},
        {QStringLiteral("closed_pnl"), closedPnlFound ? QJsonValue(closedPnl) : QJsonValue()},
        {QStringLiteral("closed_margin"), closedMarginFound && closedMargin > 0.0 ? QJsonValue(closedMargin) : QJsonValue()},
        {QStringLiteral("total_balance"), finiteNumberOrNull(totalBalance)},
        {QStringLiteral("available_balance"), finiteNumberOrNull(availableBalance)},
        {QStringLiteral("positions"), positions},
        {QStringLiteral("source"), nonEmptyOr(source, QStringLiteral("service"))},
        {QStringLiteral("generated_at"), generatedAt.trimmed().isEmpty() ? nowIso() : generatedAt.trimmed()},
    });
}

QJsonObject buildAllocationPersistencePayload(
    const QString &mode,
    double timestamp,
    const QJsonObject &entryAllocations,
    const QJsonObject &openPositionRecords) {
    QJsonObject allocationsOut;
    for (auto it = entryAllocations.constBegin(); it != entryAllocations.constEnd(); ++it) {
        allocationsOut.insert(it.key(), collectAllocations(it.value().toArray()));
    }
    QJsonObject recordsOut;
    for (auto it = openPositionRecords.constBegin(); it != openPositionRecords.constEnd(); ++it) {
        if (!it.value().isObject()) {
            continue;
        }
        const QJsonObject record = it.value().toObject();
        if (record.value(QStringLiteral("status")).toString(QStringLiteral("Active")).compare(QStringLiteral("Active"), Qt::CaseInsensitive) != 0) {
            continue;
        }
        recordsOut.insert(it.key(), record);
    }
    return compactObject({
        {QStringLiteral("version"), 1},
        {QStringLiteral("mode"), nonEmptyOr(mode, QStringLiteral("unknown"))},
        {QStringLiteral("timestamp"), timestamp},
        {QStringLiteral("entry_allocations"), allocationsOut},
        {QStringLiteral("open_position_records"), recordsOut},
    });
}

QJsonObject reducePositionAllocationState(
    QJsonObject &entryAllocations,
    QJsonObject &openPositionRecords,
    const QString &symbol,
    const QString &sideKey,
    const QString &interval,
    double qty,
    const QJsonObject &targetIdentity) {
    const QString key = serializePositionKey(symbol, sideKey);
    const QJsonArray entries = entryAllocations.value(key).toArray();
    if (entries.isEmpty()) {
        return compactObject({{QStringLiteral("changed"), false}, {QStringLiteral("closed_allocations"), QJsonArray{}}, {QStringLiteral("survivor_allocations"), QJsonArray{}}});
    }
    double remaining = qty > 0.0 && std::isfinite(qty) ? qty : std::numeric_limits<double>::infinity();
    QJsonArray closed;
    QJsonArray survivors;
    bool matched = false;
    for (const QJsonValue &value : entries) {
        if (!value.isObject()) {
            continue;
        }
        QJsonObject entry = value.toObject();
        const bool identityMatch = !targetIdentity.isEmpty() && identityMatches(entry, targetIdentity);
        const bool intervalMatch = targetIdentity.isEmpty() && intervalMatches(entry, interval);
        if ((identityMatch || intervalMatch) && remaining > 0.0) {
            matched = true;
            const double entryQty = std::fabs(finiteNumberOr(entry.value(QStringLiteral("qty"))));
            if (std::isinf(remaining) || entryQty <= remaining + 1e-9) {
                entry.insert(QStringLiteral("status"), QStringLiteral("Closed"));
                closed.append(entry);
                if (!std::isinf(remaining)) {
                    remaining -= entryQty;
                }
                continue;
            }
            QJsonObject closedPart = entry;
            closedPart.insert(QStringLiteral("qty"), remaining);
            closedPart.insert(QStringLiteral("status"), QStringLiteral("Closed"));
            scaleAllocationFields(closedPart, entryQty > 0.0 ? remaining / entryQty : 1.0);
            closed.append(closedPart);
            const double survivorQty = entryQty - remaining;
            entry.insert(QStringLiteral("qty"), survivorQty);
            scaleAllocationFields(entry, entryQty > 0.0 ? survivorQty / entryQty : 1.0);
            remaining = 0.0;
        }
        survivors.append(entry);
    }
    if (!matched) {
        return compactObject({{QStringLiteral("changed"), false}, {QStringLiteral("closed_allocations"), QJsonArray{}}, {QStringLiteral("survivor_allocations"), entries}});
    }
    if (survivors.isEmpty()) {
        entryAllocations.remove(key);
        openPositionRecords.remove(key);
    } else {
        entryAllocations.insert(key, survivors);
        QJsonObject record = openPositionRecords.value(key).toObject();
        if (!record.isEmpty()) {
            record.insert(QStringLiteral("allocations"), survivors);
            openPositionRecords.insert(key, record);
        }
    }
    return compactObject({{QStringLiteral("changed"), true}, {QStringLiteral("closed_allocations"), closed}, {QStringLiteral("survivor_allocations"), survivors}});
}

QJsonObject applyCloseAllToPositionState(
    QJsonObject &openPositionRecords,
    QJsonObject &entryAllocations,
    QJsonArray &closedPositionRecords,
    const QJsonArray &closeResults,
    const QString &closeTime,
    int maxHistory) {
    QSet<QString> symbols;
    bool hadError = false;
    for (const QJsonValue &value : closeResults) {
        if (!value.isObject()) {
            continue;
        }
        const QJsonObject item = value.toObject();
        const QString symbol = item.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        if (symbol.isEmpty()) {
            continue;
        }
        if (item.value(QStringLiteral("ok")).toBool(false) || item.value(QStringLiteral("skipped")).toBool(false)) {
            symbols.insert(symbol);
        } else {
            hadError = true;
        }
    }
    if (symbols.isEmpty() && !hadError && !openPositionRecords.isEmpty()) {
        for (auto it = openPositionRecords.constBegin(); it != openPositionRecords.constEnd(); ++it) {
            symbols.insert(recordSymbol(it.value().toObject()));
        }
    }
    QJsonObject closedByKey;
    QStringList removedKeys;
    for (auto it = openPositionRecords.constBegin(); it != openPositionRecords.constEnd(); ++it) {
        if (!it.value().isObject()) {
            continue;
        }
        QJsonObject record = it.value().toObject();
        const QString symbol = recordSymbol(record);
        if (!symbols.contains(symbol)) {
            continue;
        }
        record.insert(QStringLiteral("status"), QStringLiteral("Closed"));
        record.insert(QStringLiteral("close_time"), nonEmptyOr(closeTime, nowIso()));
        const QJsonArray allocations = entryAllocations.value(it.key()).toArray();
        if (!allocations.isEmpty()) {
            record.insert(QStringLiteral("allocations"), allocations);
        }
        closedByKey.insert(it.key(), record);
        removedKeys.append(it.key());
    }
    for (const QString &key : removedKeys) {
        openPositionRecords.remove(key);
        entryAllocations.remove(key);
    }
    for (const QString &key : removedKeys) {
        QJsonArray next;
        next.append(closedByKey.value(key));
        for (const QJsonValue &existing : closedPositionRecords) {
            if (next.size() >= std::max(1, maxHistory)) {
                break;
            }
            next.append(existing);
        }
        closedPositionRecords = next;
    }
    QStringList symbolList;
    for (const QString &symbol : symbols) {
        symbolList.append(symbol);
    }
    symbolList.sort();
    QJsonArray closedSymbols;
    for (const QString &symbol : symbolList) {
        closedSymbols.append(symbol);
    }
    return compactObject({
        {QStringLiteral("closed_count"), removedKeys.size()},
        {QStringLiteral("remaining_open_count"), openPositionRecords.size()},
        {QStringLiteral("closed_symbols"), closedSymbols},
    });
}

} // namespace NativePortfolio
