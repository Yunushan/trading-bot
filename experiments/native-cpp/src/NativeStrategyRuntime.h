#pragma once

#include <QJsonObject>
#include <QJsonArray>
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

struct IndicatorSignalConfirmationTracker {
    QString direction;
    int count = 0;
    qint64 timestampMs = 0;
};

struct IndicatorOrderGuardState {
    QString lastActionSide;
    qint64 lastActionMs = 0;
    qint64 recentCloseMs = 0;
    QString recentCloseSide;
    QString signalResetSide;
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
double pythonIndicatorIntervalSeconds(const QString &interval);
double pythonLoopIntervalSeconds(const QString &interval);
QString canonicalizeBacktestInterval(const QJsonValue &value);
bool coerceStrategyBool(const QJsonValue &value, bool defaultValue = false);
QStringList indicatorOutputKeysFromConfig(const QJsonObject &indicators);
QJsonObject buildSignalDecision(const StrategySignalInput &input);
QJsonObject applyIndicatorSignalConfirmation(
    const QJsonObject &decision,
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 signalTimestampMs,
    QMap<QString, IndicatorSignalConfirmationTracker> &trackers);
QJsonObject applyIndicatorOrderGuards(
    const QJsonObject &decision,
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 signalTimestampMs,
    QMap<QString, IndicatorOrderGuardState> &states,
    QMap<QString, qint64> &reentryBlocks);
void refreshIndicatorReentrySignalBlocks(
    const QJsonObject &actions,
    const QString &symbol,
    const QString &interval,
    QMap<QString, IndicatorOrderGuardState> &states);
void recordIndicatorOrderAction(
    const QString &symbol,
    const QString &interval,
    const QString &indicator,
    const QString &side,
    qint64 timestampMs,
    QMap<QString, IndicatorOrderGuardState> &states);
void recordIndicatorClose(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QString &indicator,
    const QString &side,
    qint64 timestampMs,
    QMap<QString, IndicatorOrderGuardState> &states,
    QMap<QString, qint64> &reentryBlocks);
void recordIndicatorCloses(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QStringList &indicators,
    const QString &side,
    qint64 timestampMs,
    QMap<QString, IndicatorOrderGuardState> &states,
    QMap<QString, qint64> &reentryBlocks);
void queueIndicatorFlipOnClose(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QStringList &indicators,
    const QString &closedSide,
    double quantity,
    qint64 timestampMs,
    QMap<QString, QJsonObject> &pendingRequests);
QJsonObject mergeIndicatorFlipOnCloseRequests(
    const QJsonObject &decision,
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 timestampMs,
    QMap<QString, QJsonObject> &pendingRequests);
QJsonObject normalizeStrategyControls(const QString &kind, const QJsonObject &controls);
double positionPctFraction(
    const QJsonObject &controls,
    double fallbackPositionPct,
    const QString &fallbackUnits);
QJsonObject normalizeStrategyRiskControls(const QJsonObject &controls);
bool indicatorCloseScopeAllowed(
    const QJsonObject &riskControls,
    const QStringList &indicators,
    bool allowMultiOverride = false);
bool indicatorHoldReady(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 openedAtMs,
    qint64 nowMs,
    QString *reason = nullptr,
    bool ignoreHold = false);
QJsonObject evaluatePerTradeStopLoss(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QString &side,
    double quantity,
    double entryPrice,
    double markPrice,
    double leverage,
    double marginUsdt,
    bool futures);
QJsonArray evaluateFuturesStopLoss(
    const QJsonObject &riskControls,
    const QJsonArray &positions,
    const QString &symbol,
    const QString &interval,
    double walletUsdt,
    bool futures);
QJsonObject cleanBacktestResultPayload(const QJsonObject &payload);
QString formatBacktestResultText(const QJsonObject &payload);
QJsonObject buildCleanOverrideEntry(const QString &kind, const QJsonObject &entry);
double nextNetworkBackoff(double previous);
QJsonObject buildWorkerLifecycleSnapshot(const StrategyWorkerLifecycleInput &input);

} // namespace NativeStrategyRuntime
