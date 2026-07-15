#pragma once

#include "NativeBacktestRuntime.h"

#include <QJsonObject>
#include <QStringList>
#include <QVector>

#include <functional>

namespace NativeBacktestBatchRuntime {

inline constexpr qint64 kMaxOptimizerRuns = 100'000'000'000LL;
inline constexpr int kDefaultResultLimit = 5'000;

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
    QStringList symbols;
    QStringList intervals;
    NativeIndicatorRuntime::ConfigMap indicatorConfigs;
    NativeBacktestRuntime::Request runTemplate;
    QString optimizerMode = QStringLiteral("current");
    QString optimizerMetric = QStringLiteral("roi_percent");
    QString optimizerScope = QStringLiteral("selected");
    int optimizerComboSize = 2;
    int optimizerMinTrades = 1;
    double optimizerMddLimit = 0.0;
    int resultLimit = kDefaultResultLimit;
    qint64 maxRunCount = kMaxOptimizerRuns;
    QString startDisplay;
    QString endDisplay;
    QString loopIntervalOverride;
    QString connectorBackend;
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

qint64 estimateRunCount(
    qsizetype symbolCount,
    qsizetype intervalCount,
    qsizetype indicatorGroupCount);

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
