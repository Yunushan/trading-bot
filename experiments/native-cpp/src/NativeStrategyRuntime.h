#pragma once

#include <QJsonObject>
#include <QJsonValue>
#include <QMap>
#include <QString>
#include <QStringList>
#include <QVector>

#include <optional>

namespace NativeStrategyRuntime {

struct IndicatorRule {
    bool enabled = false;
    std::optional<double> buyValue;
    std::optional<double> sellValue;
};

struct StrategySignalInput {
    QVector<double> closes;
    QMap<QString, QVector<double>> indicators;
    QMap<QString, IndicatorRule> rules;
    QString side = QStringLiteral("BOTH");
    bool useLiveValues = false;
};

struct StrategyWorkerLifecycleInput {
    QString symbol;
    QString interval;
    QString loopIntervalOverride;
    bool threadAlive = false;
    bool stopRequested = false;
    bool globalShutdown = false;
    bool globalPause = false;
    int activeEngineCount = 0;
    double offlineBackoff = 0.0;
    bool emergencyCloseTriggered = false;
};

QStringList strategyRuntimeBoundaries();
bool coerceStrategyBool(const QJsonValue &value, bool defaultValue = false);
QStringList indicatorOutputKeysFromConfig(const QJsonObject &indicators);
QJsonObject buildSignalDecision(const StrategySignalInput &input);
QJsonObject normalizeStrategyControls(const QString &kind, const QJsonObject &controls);
QJsonObject cleanBacktestResultPayload(const QJsonObject &payload);
QString formatBacktestResultText(const QJsonObject &payload);
QJsonObject buildCleanOverrideEntry(const QString &kind, const QJsonObject &entry);
double nextNetworkBackoff(double previous);
QJsonObject buildWorkerLifecycleSnapshot(const StrategyWorkerLifecycleInput &input);

} // namespace NativeStrategyRuntime
