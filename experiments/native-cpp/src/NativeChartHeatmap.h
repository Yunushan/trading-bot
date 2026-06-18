#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace NativeChartHeatmap {

QString normalizeChartMarket(const QString &value);
QString normalizeChartIntervalKey(const QString &value);
QString canonicalizeChartInterval(const QString &value);
QString mapTradingViewInterval(const QString &value);
QString futuresDisplaySymbol(const QString &symbol);
QString resolveChartSymbolForApi(
    const QString &symbol,
    const QString &market,
    const QJsonObject &aliasMap = {});
QString formatTradingViewSymbol(const QString &symbol, const QString &accountHint = {});
QString buildTradingViewUrl(const QString &symbol, const QString &intervalCode);

QJsonObject buildChartStatePayload(
    const QString &market,
    const QString &symbol,
    const QString &interval,
    const QString &viewMode,
    bool autoFollow);

QJsonObject buildLightweightPayload(
    const QJsonArray &candles,
    const QStringList &enabledIndicators,
    const QString &themeName,
    const QJsonArray &overlays = {},
    const QJsonArray &panes = {});

QStringList lightweightAssetSources(bool localAssetAvailable);
QJsonObject buildChartViewModeGuardDecision(
    const QString &requestedMode,
    bool safeModeEnabled,
    bool externalOpened = false);
QJsonArray liquidationHeatmapProviders();

} // namespace NativeChartHeatmap
