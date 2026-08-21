#pragma once

#include "NativeBacktestRuntime.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QVector>

#include <functional>

namespace NativeBacktestBatchRuntime {

inline constexpr qint64 kMaxOptimizerRuns = 100'000'000'000LL;
inline constexpr int kDefaultResultLimit = 5'000;
inline constexpr qint64 kMinOptimizerDurationSeconds = 60;
inline constexpr qint64 kDefaultOptimizerDurationSeconds = 4 * 60 * 60;
inline constexpr qint64 kMaxOptimizerDurationSeconds = 7 * 24 * 60 * 60;

struct CandleLoadResult {
    bool ok = false;
    QVector<NativeIndicatorRuntime::Candle> candles;
    QString error;
};

using StopCallback = std::function<bool()>;
using CandleLoader = std::function<CandleLoadResult(
    const QString &symbol,
    const QString &interval,
    const StopCallback &shouldStop)>;

struct BatchRequest {
    BatchRequest();
    QStringList symbols;
    QStringList intervals;
    NativeIndicatorRuntime::ConfigMap indicatorConfigs;
    NativeBacktestRuntime::Request runTemplate;
    QString optimizerMode = QStringLiteral("current");
    QString optimizerMetric = QStringLiteral("roi_percent");
    QString optimizerScope = QStringLiteral("selected");
    bool optimizerEnabled = false;
    int scanTopN = 200;
    int optimizerComboSize = 2;
    int optimizerMinTrades = 1;
    double optimizerMddLimit = 10.0;
    qint64 optimizerMaxDurationSeconds = kDefaultOptimizerDurationSeconds;
    int resultLimit = kDefaultResultLimit;
    qint64 maxRunCount = kMaxOptimizerRuns;
    QString startDisplay;
    QString endDisplay;
    qint64 warmupBars = 100;
    QString loopIntervalOverride;
    QString connectorBackend;
    QJsonArray pairOverrides;
};

struct Score {
    bool eligible = false;
    QVector<double> values;
    QString rejectionReason;
};

QVector<QStringList> buildIndicatorGroups(
    const NativeIndicatorRuntime::ConfigMap &configs,
    const QString &mode,
    int comboSize,
    const QString &logic);

qint64 estimateWarmupBars(const NativeIndicatorRuntime::ConfigMap &configs);

qint64 bufferedStartTimeMs(
    qint64 startTimeMs,
    const QString &interval,
    qint64 warmupBars);

qint64 estimateRunCount(
    qsizetype symbolCount,
    qsizetype intervalCount,
    qsizetype indicatorGroupCount);

qint64 estimateRunCount(const BatchRequest &request);

Score optimizerScore(
    const NativeBacktestRuntime::Result &result,
    const QString &metric,
    double mddLimit,
    int minTrades);

QJsonObject runBatch(
    const BatchRequest &request,
    const CandleLoader &loadCandles,
    const StopCallback &shouldStop = {});

} // namespace NativeBacktestBatchRuntime
