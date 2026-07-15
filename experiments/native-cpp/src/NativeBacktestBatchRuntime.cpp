#include "NativeBacktestBatchRuntime.h"

#include <QJsonArray>
#include <QJsonValue>

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>

namespace {

using ConfigMap = NativeIndicatorRuntime::ConfigMap;

QString normalizedToken(const QString &value, const QString &fallback = {}) {
    QString token = value.trimmed().toLower();
    token.replace(QLatin1Char('-'), QLatin1Char('_'));
    token.replace(QLatin1Char(' '), QLatin1Char('_'));
    return token.isEmpty() ? fallback : token;
}

bool configEnabled(const QJsonObject &config) {
    const QJsonValue value = config.value(QStringLiteral("enabled"));
    if (value.isBool()) return value.toBool();
    if (value.isDouble()) return value.toDouble() != 0.0;
    return QStringList{
        QStringLiteral("true"),
        QStringLiteral("1"),
        QStringLiteral("yes"),
        QStringLiteral("on"),
    }.contains(value.toString().trimmed().toLower());
}

bool configIsFilter(const QJsonObject &config) {
    const QString role = normalizedToken(
        config.value(QStringLiteral("signal_role")).toString(),
        normalizedToken(config.value(QStringLiteral("role")).toString(), QStringLiteral("signal")));
    return QStringList{
        QStringLiteral("filter"),
        QStringLiteral("entry_filter"),
        QStringLiteral("gate"),
        QStringLiteral("confirmation"),
    }.contains(role);
}

void appendCombinations(
    const QStringList &keys,
    int targetSize,
    int start,
    QStringList &current,
    QVector<QStringList> &groups) {
    if (current.size() == targetSize) {
        groups.append(current);
        return;
    }
    const int remaining = targetSize - current.size();
    for (int index = start; index <= keys.size() - remaining; ++index) {
        current.append(keys.at(index));
        appendCombinations(keys, targetSize, index + 1, current, groups);
        current.removeLast();
    }
}

QStringList withFilters(const QStringList &signalKeys, const QStringList &filterKeys) {
    QStringList combined = signalKeys;
    for (const QString &filterKey : filterKeys) {
        if (!combined.contains(filterKey)) combined.append(filterKey);
    }
    return combined;
}

int compareScoreValues(const QVector<double> &left, const QVector<double> &right) {
    const qsizetype count = std::min(left.size(), right.size());
    for (qsizetype index = 0; index < count; ++index) {
        if (left.at(index) > right.at(index)) return 1;
        if (left.at(index) < right.at(index)) return -1;
    }
    if (left.size() > right.size()) return 1;
    if (left.size() < right.size()) return -1;
    return 0;
}

struct RankedRow {
    QVector<double> score;
    qint64 originalIndex = 0;
    QJsonObject row;
};

struct BestFirst {
    bool operator()(const RankedRow &left, const RankedRow &right) const {
        const int scoreOrder = compareScoreValues(left.score, right.score);
        if (scoreOrder != 0) return scoreOrder > 0;
        if (left.originalIndex != right.originalIndex) return left.originalIndex < right.originalIndex;
        return false;
    }
};

QJsonArray rowsToArray(const QVector<QJsonObject> &rows) {
    QJsonArray array;
    for (const QJsonObject &row : rows) array.append(row);
    return array;
}

qint64 saturatingMultiply(qint64 left, qint64 right) {
    if (left <= 0 || right <= 0) return 0;
    if (left > std::numeric_limits<qint64>::max() / right) {
        return std::numeric_limits<qint64>::max();
    }
    return left * right;
}

QString normalizedOptimizerMetric(const QString &metric) {
    const QString normalized = normalizedToken(metric, QStringLiteral("roi_percent"));
    if (QStringList{
            QStringLiteral("roi_percent"),
            QStringLiteral("roi_percent_mdd"),
            QStringLiteral("roi_drawdown"),
            QStringLiteral("roi_value"),
        }.contains(normalized)) {
        return normalized;
    }
    return QStringLiteral("roi_percent");
}

} // namespace

namespace NativeBacktestBatchRuntime {

QVector<QStringList> buildIndicatorGroups(
    const ConfigMap &configs,
    const QString &mode,
    int comboSize,
    const QString &logic) {
    QStringList signalKeys;
    QStringList filterKeys;
    for (auto iterator = configs.cbegin(); iterator != configs.cend(); ++iterator) {
        if (!configEnabled(iterator.value())) continue;
        if (configIsFilter(iterator.value())) filterKeys.append(iterator.key());
        else signalKeys.append(iterator.key());
    }
    signalKeys.removeDuplicates();
    filterKeys.removeDuplicates();
    if (signalKeys.isEmpty()) return {};

    QVector<QStringList> signalGroups;
    const QString modeNormalized = normalizedToken(mode, QStringLiteral("current"));
    const QString logicNormalized = normalizedToken(logic, QStringLiteral("and")).toUpper();
    if (modeNormalized == QStringLiteral("current")) {
        if (logicNormalized == QStringLiteral("SEPARATE")) {
            for (const QString &key : signalKeys) signalGroups.append(QStringList{key});
        } else if (!signalKeys.isEmpty()) {
            signalGroups.append(signalKeys);
        }
    } else if (modeNormalized == QStringLiteral("single")) {
        for (const QString &key : signalKeys) signalGroups.append(QStringList{key});
    } else if (modeNormalized == QStringLiteral("pairs")) {
        QStringList current;
        appendCombinations(signalKeys, 2, 0, current, signalGroups);
    } else {
        const int maximum = std::clamp(comboSize, 1, static_cast<int>(signalKeys.size()));
        for (int size = 1; size <= maximum; ++size) {
            QStringList current;
            appendCombinations(signalKeys, size, 0, current, signalGroups);
        }
    }

    QVector<QStringList> groups;
    groups.reserve(signalGroups.size());
    for (const QStringList &signalGroup : signalGroups) {
        groups.append(withFilters(signalGroup, filterKeys));
    }
    return groups;
}

qint64 estimateRunCount(
    qsizetype symbolCount,
    qsizetype intervalCount,
    qsizetype indicatorGroupCount) {
    const qint64 pairCount = saturatingMultiply(
        std::max<qint64>(0, symbolCount),
        std::max<qint64>(0, intervalCount));
    return saturatingMultiply(pairCount, std::max<qint64>(0, indicatorGroupCount));
}

Score optimizerScore(
    const NativeBacktestRuntime::Result &result,
    const QString &metric,
    double mddLimit,
    int minTrades) {
    Score score;
    QStringList reasons;
    const int tradeFloor = std::max(0, minTrades);
    const double limit = std::max(0.0, mddLimit);
    if (result.trades < tradeFloor) {
        reasons.append(QStringLiteral("trades %1 < %2").arg(result.trades).arg(tradeFloor));
    }
    if (limit > 0.0 && result.maxDrawdownPercent > limit) {
        reasons.append(
            QStringLiteral("MDD %1% > %2%")
                .arg(result.maxDrawdownPercent, 0, 'f', 2)
                .arg(limit, 0, 'f', 2));
    }
    if (!reasons.isEmpty()) {
        score.rejectionReason = reasons.join(QStringLiteral("; "));
        return score;
    }

    score.eligible = true;
    const QString metricNormalized = normalizedOptimizerMetric(metric);
    if (metricNormalized == QStringLiteral("roi_value")) {
        score.values = {
            result.roiValue,
            result.roiPercent,
            static_cast<double>(result.trades),
            -result.maxDrawdownPercent,
        };
    } else if (metricNormalized == QStringLiteral("roi_drawdown")) {
        score.values = {
            result.roiPercent / std::max(std::abs(result.maxDrawdownPercent), 1.0),
            result.roiPercent,
            result.roiValue,
            static_cast<double>(result.trades),
            -result.maxDrawdownPercent,
        };
    } else {
        score.values = {
            result.roiPercent,
            result.roiValue,
            static_cast<double>(result.trades),
            -result.maxDrawdownPercent,
        };
    }
    return score;
}

QJsonObject runBatch(
    const BatchRequest &request,
    const CandleLoader &loadCandles,
    const StopCallback &shouldStop) {
    QJsonObject snapshot;
    snapshot.insert(QStringLiteral("source"), QStringLiteral("native-cpp-backtest"));
    snapshot.insert(QStringLiteral("state"), QStringLiteral("starting"));
    snapshot.insert(QStringLiteral("cancelled"), false);

    QStringList symbols;
    for (const QString &value : request.symbols) {
        const QString symbol = value.trimmed().toUpper();
        if (!symbol.isEmpty() && !symbols.contains(symbol)) symbols.append(symbol);
    }
    QStringList intervals;
    for (const QString &value : request.intervals) {
        const QString interval = value.trimmed();
        if (!interval.isEmpty() && !intervals.contains(interval)) intervals.append(interval);
    }
    const QVector<QStringList> groups = buildIndicatorGroups(
        request.indicatorConfigs,
        request.optimizerMode,
        request.optimizerComboSize,
        request.runTemplate.logic);
    const qint64 runCount = estimateRunCount(symbols.size(), intervals.size(), groups.size());
    snapshot.insert(QStringLiteral("optimizer_run_count"), static_cast<double>(runCount));
    snapshot.insert(QStringLiteral("indicator_group_count"), groups.size());
    snapshot.insert(QStringLiteral("symbol_count"), symbols.size());
    snapshot.insert(QStringLiteral("interval_count"), intervals.size());

    if (symbols.isEmpty() || intervals.isEmpty()) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("failed"));
        snapshot.insert(QStringLiteral("status_message"), QStringLiteral("Select at least one symbol and interval."));
        return snapshot;
    }
    if (groups.isEmpty()) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("failed"));
        snapshot.insert(
            QStringLiteral("status_message"),
            QStringLiteral("Optimizer mode needs enabled signal indicators for the selected combination type."));
        return snapshot;
    }
    if (!loadCandles) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("failed"));
        snapshot.insert(QStringLiteral("status_message"), QStringLiteral("Native candle loader is unavailable."));
        return snapshot;
    }
    const qint64 maxRuns = request.maxRunCount > 0 ? request.maxRunCount : kMaxOptimizerRuns;
    if (runCount > maxRuns) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("failed"));
        snapshot.insert(
            QStringLiteral("status_message"),
            QStringLiteral("Estimated optimizer runs %1 exceed the native hard cap %2.")
                .arg(runCount)
                .arg(maxRuns));
        return snapshot;
    }

    const int resultLimit = std::max(1, request.resultLimit);
    const QString metric = normalizedOptimizerMetric(request.optimizerMetric);
    const QString mode = normalizedToken(request.optimizerMode, QStringLiteral("current"));
    const QString scope = normalizedToken(request.optimizerScope, QStringLiteral("selected"));
    const QString originalLogic = request.runTemplate.logic.trimmed().toUpper();
    const QString effectiveLogic = originalLogic == QStringLiteral("SEPARATE")
        ? QStringLiteral("AND")
        : originalLogic;
    std::multiset<RankedRow, BestFirst> eligibleRows;
    QVector<QJsonObject> rejectedSamples;
    QJsonArray errors;
    qint64 processedCount = 0;
    qint64 candidateCount = 0;
    qint64 eligibleCount = 0;
    qint64 filteredCount = 0;
    bool cancelled = false;

    snapshot.insert(QStringLiteral("state"), QStringLiteral("running"));
    for (const QString &symbol : symbols) {
        for (const QString &interval : intervals) {
            if (shouldStop && shouldStop()) {
                cancelled = true;
                break;
            }
            const CandleLoadResult loaded = loadCandles(symbol, interval, shouldStop);
            if (!loaded.ok) {
                if ((shouldStop && shouldStop()) || loaded.error == QStringLiteral("backtest_cancelled")) {
                    cancelled = true;
                    break;
                }
                errors.append(QJsonObject{
                    {QStringLiteral("symbol"), symbol},
                    {QStringLiteral("interval"), interval},
                    {QStringLiteral("error"), loaded.error},
                });
                processedCount += groups.size();
                continue;
            }

            for (const QStringList &group : groups) {
                if (shouldStop && shouldStop()) {
                    cancelled = true;
                    break;
                }
                NativeBacktestRuntime::Request runRequest = request.runTemplate;
                runRequest.symbol = symbol;
                runRequest.interval = interval;
                runRequest.logic = effectiveLogic;
                runRequest.indicators.clear();
                for (const QString &key : group) {
                    QJsonObject config = request.indicatorConfigs.value(key);
                    config.insert(QStringLiteral("enabled"), true);
                    runRequest.indicators.insert(key, config);
                }

                NativeBacktestRuntime::Result result = NativeBacktestRuntime::run(
                    loaded.candles,
                    runRequest,
                    shouldStop);
                ++processedCount;
                if (!result.ok) {
                    if (result.error == QStringLiteral("backtest_cancelled")) {
                        cancelled = true;
                        break;
                    }
                    errors.append(QJsonObject{
                        {QStringLiteral("symbol"), symbol},
                        {QStringLiteral("interval"), interval},
                        {QStringLiteral("indicator_keys"), QJsonArray::fromStringList(group)},
                        {QStringLiteral("error"), result.error},
                    });
                    continue;
                }

                QJsonObject row = result.toJson();
                row.insert(QStringLiteral("start"), request.startDisplay);
                row.insert(QStringLiteral("end"), request.endDisplay);
                row.insert(QStringLiteral("loop_interval_override"), request.loopIntervalOverride);
                row.insert(QStringLiteral("connector_backend"), request.connectorBackend);
                const Score score = optimizerScore(
                    result,
                    metric,
                    request.optimizerMddLimit,
                    request.optimizerMinTrades);
                row.insert(QStringLiteral("optimizer_metric"), metric);
                row.insert(QStringLiteral("optimizer_mode"), mode);
                row.insert(QStringLiteral("optimizer_scope"), scope);
                row.insert(QStringLiteral("optimizer_mdd_limit"), request.optimizerMddLimit);
                row.insert(QStringLiteral("optimizer_min_trades"), request.optimizerMinTrades);
                row.insert(QStringLiteral("optimizer_eligible"), score.eligible);
                row.insert(
                    QStringLiteral("optimizer_primary_score"),
                    score.eligible && !score.values.isEmpty()
                        ? QJsonValue(score.values.constFirst())
                        : QJsonValue(QJsonValue::Null));
                row.insert(QStringLiteral("optimizer_rejection_reason"), score.rejectionReason);
                const qint64 originalIndex = candidateCount++;
                if (score.eligible) {
                    ++eligibleCount;
                    eligibleRows.insert(RankedRow{score.values, originalIndex, row});
                    if (eligibleRows.size() > static_cast<std::size_t>(resultLimit)) {
                        eligibleRows.erase(std::prev(eligibleRows.end()));
                    }
                } else {
                    ++filteredCount;
                    if (rejectedSamples.size() < resultLimit) rejectedSamples.append(row);
                }
            }
            if (cancelled) break;
        }
        if (cancelled) break;
    }

    QVector<QJsonObject> finalRows;
    if (!eligibleRows.empty()) {
        finalRows.reserve(static_cast<qsizetype>(eligibleRows.size()));
        int rank = 1;
        for (const RankedRow &ranked : eligibleRows) {
            QJsonObject row = ranked.row;
            row.insert(QStringLiteral("optimizer_rank"), rank++);
            finalRows.append(row);
        }
    } else {
        finalRows = rejectedSamples;
        for (QJsonObject &row : finalRows) {
            row.insert(QStringLiteral("optimizer_rank"), QJsonValue(QJsonValue::Null));
        }
    }
    for (QJsonObject &row : finalRows) {
        row.insert(QStringLiteral("optimizer_candidate_count"), static_cast<double>(candidateCount));
        row.insert(QStringLiteral("optimizer_eligible_count"), static_cast<double>(eligibleCount));
        row.insert(QStringLiteral("optimizer_filtered_count"), static_cast<double>(filteredCount));
        row.insert(QStringLiteral("optimizer_run_count"), static_cast<double>(runCount));
    }

    const QJsonArray rows = rowsToArray(finalRows);
    snapshot.insert(QStringLiteral("runs"), rows);
    snapshot.insert(QStringLiteral("top_runs"), rows);
    if (!rows.isEmpty()) snapshot.insert(QStringLiteral("top_run"), rows.at(0));
    snapshot.insert(QStringLiteral("errors"), errors);
    snapshot.insert(QStringLiteral("processed_count"), static_cast<double>(processedCount));
    snapshot.insert(QStringLiteral("optimizer_candidate_count"), static_cast<double>(candidateCount));
    snapshot.insert(QStringLiteral("optimizer_eligible_count"), static_cast<double>(eligibleCount));
    snapshot.insert(QStringLiteral("optimizer_filtered_count"), static_cast<double>(filteredCount));
    snapshot.insert(
        QStringLiteral("progress_percent"),
        runCount > 0 ? std::min(100.0, static_cast<double>(processedCount) / static_cast<double>(runCount) * 100.0) : 100.0);

    if (cancelled) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("cancelled"));
        snapshot.insert(QStringLiteral("cancelled"), true);
        snapshot.insert(
            QStringLiteral("status_message"),
            QStringLiteral("Native C++ backtest cancelled after %1 of %2 run(s).")
                .arg(processedCount)
                .arg(runCount));
    } else if (candidateCount == 0 && !errors.isEmpty()) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("failed"));
        snapshot.insert(
            QStringLiteral("status_message"),
            QStringLiteral("Native C++ backtest produced no valid runs; %1 error(s).")
                .arg(errors.size()));
    } else {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("completed"));
        snapshot.insert(QStringLiteral("progress_percent"), 100.0);
        snapshot.insert(
            QStringLiteral("status_message"),
            QStringLiteral("Native C++ backtest completed %1 run(s); %2 eligible, %3 filtered, %4 error(s).")
                .arg(processedCount)
                .arg(eligibleCount)
                .arg(filteredCount)
                .arg(errors.size()));
    }
    return snapshot;
}

} // namespace NativeBacktestBatchRuntime
