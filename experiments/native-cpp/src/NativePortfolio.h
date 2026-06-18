#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>

namespace NativePortfolio {

QJsonObject buildPositionSnapshot(const QJsonObject &record);

QJsonObject buildPortfolioSnapshot(
    const QJsonObject &config,
    const QJsonObject &openPositionRecords,
    const QJsonArray &closedPositionRecords,
    const QJsonObject &closedTradeRegistry,
    const QJsonValue &totalBalance = {},
    const QJsonValue &availableBalance = {},
    const QString &source = QStringLiteral("service"),
    const QString &generatedAt = {});

QJsonObject buildAllocationPersistencePayload(
    const QString &mode,
    double timestamp,
    const QJsonObject &entryAllocations,
    const QJsonObject &openPositionRecords);

QJsonObject reducePositionAllocationState(
    QJsonObject &entryAllocations,
    QJsonObject &openPositionRecords,
    const QString &symbol,
    const QString &sideKey,
    const QString &interval = {},
    double qty = 0.0,
    const QJsonObject &targetIdentity = {});

QJsonObject applyCloseAllToPositionState(
    QJsonObject &openPositionRecords,
    QJsonObject &entryAllocations,
    QJsonArray &closedPositionRecords,
    const QJsonArray &closeResults,
    const QString &closeTime,
    int maxHistory = 500);

QString serializePositionKey(const QString &symbol, const QString &sideKey);
QString sideLabel(const QString &sideKey);

} // namespace NativePortfolio
