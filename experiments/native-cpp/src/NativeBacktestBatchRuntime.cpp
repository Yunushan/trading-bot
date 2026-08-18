#include "NativeBacktestBatchRuntime.h"
#include "NativePythonParityChoices.h"
#include "NativeStrategyRuntime.h"
#include "generated/PythonParityContract.h"

#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>
#include <QMap>
#include <QSet>

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
    return NativePythonParity::canonicalConfigChoice(
        metric,
        PythonParityContract::kPythonOptimizerMetricConfigChoices,
        NativePythonParity::defaultConfigChoice(
            PythonParityContract::kPythonOptimizerMetricConfigChoices));
}

QString jsonText(const QJsonObject &object, const QString &key, const QString &fallback = {}) {
    const QString value = object.value(key).toString().trimmed();
    return value.isEmpty() ? fallback : value;
}

double jsonNumber(const QJsonObject &object, const QString &key, double fallback) {
    const QJsonValue value = object.value(key);
    if (value.isDouble()) return value.toDouble(fallback);
    bool ok = false;
    const double parsed = value.toString().trimmed().toDouble(&ok);
    return ok ? parsed : fallback;
}

double pythonIntervalSeconds(const QString &interval) {
    QString value = interval.trimmed().toLower();
    if (value.isEmpty()) return 60.0;
    const QChar unit = value.at(value.size() - 1);
    const bool hasUnit = unit.isLetter();
    const QString valuePart = hasUnit ? value.left(value.size() - 1) : value;
    bool ok = false;
    const double amount = valuePart.toDouble(&ok);
    if (!ok || !std::isfinite(amount)) return 60.0;
    double seconds = amount;
    if (unit == QLatin1Char('s')) seconds = amount;
    else if (unit == QLatin1Char('m')) seconds = amount * 60.0;
    else if (unit == QLatin1Char('h')) seconds = amount * 3600.0;
    else if (unit == QLatin1Char('d')) seconds = amount * 86400.0;
    else if (unit == QLatin1Char('w')) seconds = amount * 7.0 * 86400.0;
    return std::max(seconds, 1.0);
}

const QStringList &pythonWarmupParameterKeys() {
    static const QStringList keys = {
        QStringLiteral("length"),
        QStringLiteral("fast"),
        QStringLiteral("slow"),
        QStringLiteral("signal"),
        QStringLiteral("smooth_k"),
        QStringLiteral("smooth_d"),
        QStringLiteral("short"),
        QStringLiteral("medium"),
        QStringLiteral("long"),
        QStringLiteral("atr_period"),
        QStringLiteral("atr_length"),
        QStringLiteral("conversion_length"),
        QStringLiteral("base_length"),
        QStringLiteral("span_b_length"),
        QStringLiteral("displacement"),
        QStringLiteral("roc1"),
        QStringLiteral("roc2"),
        QStringLiteral("roc3"),
        QStringLiteral("roc4"),
        QStringLiteral("sma1"),
        QStringLiteral("sma2"),
        QStringLiteral("sma3"),
        QStringLiteral("sma4"),
    };
    return keys;
}

void inspectWarmupObject(const QJsonObject &object, qint64 &maximum, bool &hasCandidate) {
    for (const QString &key : pythonWarmupParameterKeys()) {
        const QJsonValue value = object.value(key);
        double parsed = 0.0;
        if (value.isDouble()) {
            parsed = value.toDouble();
        } else if (value.isString()) {
            bool ok = false;
            parsed = value.toString().trimmed().toDouble(&ok);
            if (!ok) continue;
        } else {
            continue;
        }
        if (!std::isfinite(parsed) || parsed < 0.0) continue;
        parsed = std::trunc(parsed);
        if (parsed > static_cast<double>(std::numeric_limits<qint64>::max())) continue;
        hasCandidate = true;
        maximum = std::max(maximum, static_cast<qint64>(parsed));
    }
}

bool jsonBool(const QJsonObject &object, const QString &key, bool fallback) {
    const QJsonValue value = object.value(key);
    if (value.isBool()) return value.toBool(fallback);
    if (value.isDouble()) return value.toDouble() != 0.0;
    const QString normalized = value.toString().trimmed().toLower();
    if (QStringList{QStringLiteral("true"), QStringLiteral("1"), QStringLiteral("yes"), QStringLiteral("on")}.contains(normalized)) {
        return true;
    }
    if (QStringList{QStringLiteral("false"), QStringLiteral("0"), QStringLiteral("no"), QStringLiteral("off")}.contains(normalized)) {
        return false;
    }
    return fallback;
}

QJsonObject mergedPairControls(const QJsonObject &entry) {
    QJsonObject controls = entry.value(QStringLiteral("strategy_controls")).toObject();
    const QStringList directKeys = {
        QStringLiteral("logic"),
        QStringLiteral("capital"),
        QStringLiteral("side"),
        QStringLiteral("position_pct"),
        QStringLiteral("position_pct_units"),
        QStringLiteral("margin_mode"),
        QStringLiteral("position_mode"),
        QStringLiteral("assets_mode"),
        QStringLiteral("account_mode"),
        QStringLiteral("mdd_logic"),
        QStringLiteral("leverage"),
        QStringLiteral("stop_loss_enabled"),
        QStringLiteral("stop_loss_mode"),
        QStringLiteral("stop_loss_usdt"),
        QStringLiteral("stop_loss_percent"),
        QStringLiteral("stop_loss_scope"),
    };
    for (const QString &key : directKeys) {
        if (entry.contains(key) && !entry.value(key).isNull()) controls.insert(key, entry.value(key));
    }
    if (entry.value(QStringLiteral("stop_loss")).isObject()) {
        controls.insert(QStringLiteral("stop_loss"), entry.value(QStringLiteral("stop_loss")));
    }
    return controls;
}

QStringList normalizedIndicatorKeys(const QJsonObject &entry) {
    QStringList keys;
    for (const QJsonValue &value : entry.value(QStringLiteral("indicators")).toArray()) {
        const QString key = value.toString().trimmed();
        if (!key.isEmpty() && !keys.contains(key)) keys.append(key);
    }
    std::sort(keys.begin(), keys.end());
    return keys;
}

ConfigMap resolveIndicatorBundle(const ConfigMap &activeConfigs, const QStringList &overrideKeys) {
    if (overrideKeys.isEmpty()) return activeConfigs;
    ConfigMap resolved;
    QSet<QString> overrideKeySet;
    for (const QString &key : overrideKeys) {
        const auto iterator = activeConfigs.constFind(key);
        if (iterator == activeConfigs.constEnd()) continue;
        QJsonObject config = iterator.value();
        config.insert(QStringLiteral("enabled"), true);
        resolved.insert(key, config);
        overrideKeySet.insert(key);
    }
    for (auto iterator = activeConfigs.cbegin(); iterator != activeConfigs.cend(); ++iterator) {
        if (!overrideKeySet.contains(iterator.key())
            && configEnabled(iterator.value())
            && configIsFilter(iterator.value())) {
            resolved.insert(iterator.key(), iterator.value());
        }
    }
    return resolved.isEmpty() ? activeConfigs : resolved;
}

NativeBacktestRuntime::Request applyPairControls(
    NativeBacktestRuntime::Request request,
    const QJsonObject &controls) {
    const QString logic = NativePythonParity::canonicalConfigChoice(
        jsonText(controls, QStringLiteral("logic")),
        PythonParityContract::kPythonLogicConfigChoices);
    if (!logic.isEmpty()) {
        request.logic = logic;
    }
    const double capital = jsonNumber(controls, QStringLiteral("capital"), -1.0);
    if (capital > 0.0 && std::isfinite(capital)) request.capital = capital;
    const QString side = NativePythonParity::canonicalConfigChoice(
        jsonText(controls, QStringLiteral("side")),
        PythonParityContract::kPythonSideConfigChoices);
    if (!side.isEmpty()) {
        request.side = side;
    }
    const double positionPct = jsonNumber(controls, QStringLiteral("position_pct"), -1.0);
    if (positionPct > 0.0 && std::isfinite(positionPct)) request.positionPct = positionPct;
    const QString positionPctUnits = jsonText(controls, QStringLiteral("position_pct_units"));
    if (!positionPctUnits.isEmpty()) request.positionPctUnits = positionPctUnits;
    const double leverage = jsonNumber(controls, QStringLiteral("leverage"), -1.0);
    if (leverage > 0.0 && std::isfinite(leverage)) request.leverage = std::max(1.0, leverage);

    const auto applyText = [&controls](QString &target, const QString &key) {
        const QString value = jsonText(controls, key);
        if (!value.isEmpty()) target = value;
    };
    applyText(request.marginMode, QStringLiteral("margin_mode"));
    applyText(request.positionMode, QStringLiteral("position_mode"));
    applyText(request.assetsMode, QStringLiteral("assets_mode"));
    applyText(request.accountMode, QStringLiteral("account_mode"));
    const QString mddLogic = NativePythonParity::canonicalConfigChoice(
        jsonText(controls, QStringLiteral("mdd_logic")),
        PythonParityContract::kPythonMddLogicConfigChoices);
    if (!mddLogic.isEmpty()) request.mddLogic = mddLogic;

    QJsonObject stopLoss = controls.value(QStringLiteral("stop_loss")).toObject();
    if (controls.contains(QStringLiteral("stop_loss_enabled"))) {
        stopLoss.insert(QStringLiteral("enabled"), controls.value(QStringLiteral("stop_loss_enabled")));
    }
    if (controls.contains(QStringLiteral("stop_loss_mode"))) {
        stopLoss.insert(QStringLiteral("mode"), controls.value(QStringLiteral("stop_loss_mode")));
    }
    if (controls.contains(QStringLiteral("stop_loss_usdt"))) {
        stopLoss.insert(QStringLiteral("usdt"), controls.value(QStringLiteral("stop_loss_usdt")));
    }
    if (controls.contains(QStringLiteral("stop_loss_percent"))) {
        stopLoss.insert(QStringLiteral("percent"), controls.value(QStringLiteral("stop_loss_percent")));
    }
    if (controls.contains(QStringLiteral("stop_loss_scope"))) {
        stopLoss.insert(QStringLiteral("scope"), controls.value(QStringLiteral("stop_loss_scope")));
    }
    if (!stopLoss.isEmpty()) {
        request.stopLossEnabled = jsonBool(stopLoss, QStringLiteral("enabled"), request.stopLossEnabled);
        const QString stopLossMode = NativePythonParity::canonicalConfigChoice(
            jsonText(stopLoss, QStringLiteral("mode")),
            PythonParityContract::kPythonStopLossModeConfigChoices);
        if (!stopLossMode.isEmpty()) request.stopLossMode = stopLossMode;
        request.stopLossUsdt = std::max(0.0, jsonNumber(stopLoss, QStringLiteral("usdt"), request.stopLossUsdt));
        request.stopLossPercent = std::max(0.0, jsonNumber(stopLoss, QStringLiteral("percent"), request.stopLossPercent));
        const QString stopLossScope = NativePythonParity::canonicalConfigChoice(
            jsonText(stopLoss, QStringLiteral("scope")),
            PythonParityContract::kPythonStopLossScopeConfigChoices);
        if (!stopLossScope.isEmpty()) request.stopLossScope = stopLossScope;
    }
    return request;
}

QJsonObject strategyControls(const NativeBacktestRuntime::Request &request) {
    return {
        {QStringLiteral("logic"), request.logic},
        {QStringLiteral("capital"), request.capital},
        {QStringLiteral("side"), request.side},
        {QStringLiteral("position_pct"), request.positionPct},
        {QStringLiteral("position_pct_units"), request.positionPctUnits},
        {QStringLiteral("leverage"), request.leverage},
        {QStringLiteral("margin_mode"), request.marginMode},
        {QStringLiteral("position_mode"), request.positionMode},
        {QStringLiteral("assets_mode"), request.assetsMode},
        {QStringLiteral("account_mode"), request.accountMode},
        {QStringLiteral("mdd_logic"), request.mddLogic},
        {QStringLiteral("stop_loss"), QJsonObject{
            {QStringLiteral("enabled"), request.stopLossEnabled},
            {QStringLiteral("mode"), request.stopLossMode},
            {QStringLiteral("usdt"), request.stopLossUsdt},
            {QStringLiteral("percent"), request.stopLossPercent},
            {QStringLiteral("scope"), request.stopLossScope},
        }},
    };
}

struct OverridePlan {
    QString symbol;
    QString interval;
    QStringList indicatorKeys;
    NativeBacktestRuntime::Request runTemplate;
    QString reportedLogic;
    QString loopIntervalOverride;
    QString connectorBackend;
};

struct OverridePlanSet {
    bool hasValidOverrides = false;
    QVector<OverridePlan> plans;
};

OverridePlanSet buildOverridePlans(const NativeBacktestBatchRuntime::BatchRequest &request) {
    OverridePlanSet result;
    QSet<QString> seen;
    for (const QJsonValue &value : request.pairOverrides) {
        if (!value.isObject()) continue;
        const QJsonObject entry = value.toObject();
        const QString symbol = jsonText(entry, QStringLiteral("symbol")).toUpper();
        const QString interval = NativeStrategyRuntime::canonicalizeBacktestInterval(
            QJsonValue(jsonText(entry, QStringLiteral("interval"))));
        if (symbol.isEmpty() || interval.isEmpty()) continue;
        const QStringList overrideKeys = normalizedIndicatorKeys(entry);
        const QString dedupeKey = symbol + QChar(0x1f) + interval + QChar(0x1f) + overrideKeys.join(QChar(0x1e));
        if (seen.contains(dedupeKey)) continue;
        seen.insert(dedupeKey);
        result.hasValidOverrides = true;

        const QJsonObject controls = mergedPairControls(entry);
        NativeBacktestRuntime::Request runTemplate = applyPairControls(request.runTemplate, controls);
        const ConfigMap bundle = resolveIndicatorBundle(request.indicatorConfigs, overrideKeys);
        const QVector<QStringList> groups = NativeBacktestBatchRuntime::buildIndicatorGroups(
            bundle,
            QStringLiteral("current"),
            request.optimizerComboSize,
            runTemplate.logic);
        const QString reportedLogic = NativePythonParity::canonicalConfigChoice(
            runTemplate.logic,
            PythonParityContract::kPythonLogicConfigChoices,
            NativePythonParity::defaultConfigChoice(
                PythonParityContract::kPythonLogicConfigChoices));
        const QString separateLogic = NativePythonParity::canonicalConfigChoice(
            QStringLiteral("separate"),
            PythonParityContract::kPythonLogicConfigChoices,
            reportedLogic);
        const QString andLogic = NativePythonParity::canonicalConfigChoice(
            QStringLiteral("and"),
            PythonParityContract::kPythonLogicConfigChoices,
            reportedLogic);
        const QString effectiveLogic = reportedLogic.compare(separateLogic, Qt::CaseInsensitive) == 0
            ? andLogic
            : reportedLogic;
        for (const QStringList &group : groups) {
            NativeBacktestRuntime::Request effectiveTemplate = runTemplate;
            effectiveTemplate.logic = effectiveLogic;
            result.plans.append(OverridePlan{
                symbol,
                interval,
                group,
                effectiveTemplate,
                reportedLogic,
                jsonText(entry, QStringLiteral("loop_interval_override"),
                         jsonText(controls, QStringLiteral("loop_interval_override"), request.loopIntervalOverride)),
                jsonText(entry, QStringLiteral("connector_backend"),
                         jsonText(controls, QStringLiteral("connector_backend"), request.connectorBackend)),
            });
        }
    }
    return result;
}

} // namespace

namespace NativeBacktestBatchRuntime {

BatchRequest::BatchRequest() {
    const QJsonObject defaults = QJsonDocument::fromJson(QByteArray(
        PythonParityContract::kPythonDefaultBacktestJson.data(),
        static_cast<int>(PythonParityContract::kPythonDefaultBacktestJson.size()))).object();
    const QJsonObject executionDefaults = QJsonDocument::fromJson(QByteArray(
        PythonParityContract::kPythonDefaultExecutionJson.data(),
        static_cast<int>(PythonParityContract::kPythonDefaultExecutionJson.size()))).object();
    for (const QJsonValue &value : defaults.value(QStringLiteral("symbols")).toArray()) {
        const QString symbol = value.toString().trimmed();
        if (!symbol.isEmpty()) symbols.append(symbol);
    }
    for (const QJsonValue &value : defaults.value(QStringLiteral("intervals")).toArray()) {
        const QString interval = NativeStrategyRuntime::canonicalizeBacktestInterval(value);
        if (!interval.isEmpty()) intervals.append(interval);
    }
    const QJsonObject configuredIndicators = defaults.value(QStringLiteral("indicators")).toObject();
    for (auto iterator = configuredIndicators.constBegin(); iterator != configuredIndicators.constEnd(); ++iterator) {
        indicatorConfigs.insert(iterator.key(), iterator.value().toObject());
    }
    warmupBars = estimateWarmupBars(indicatorConfigs);
    optimizerMode = defaults.value(QStringLiteral("optimizer_mode")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonOptimizerModeConfigChoices));
    optimizerMetric = defaults.value(QStringLiteral("optimizer_metric")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonOptimizerMetricConfigChoices));
    optimizerScope = defaults.value(QStringLiteral("scan_scope")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonScanScopeConfigChoices));
    optimizerComboSize = defaults.value(QStringLiteral("optimizer_combo_size")).toInt(2);
    optimizerMinTrades = defaults.value(QStringLiteral("optimizer_min_trades")).toInt(1);
    optimizerMddLimit = defaults.value(QStringLiteral("scan_mdd_limit")).toDouble(10.0);
    double durationSeconds = defaults.value(QStringLiteral("optimizer_max_duration_seconds"))
                                 .toDouble(static_cast<double>(kDefaultOptimizerDurationSeconds));
    if (!std::isfinite(durationSeconds)) durationSeconds = kDefaultOptimizerDurationSeconds;
    durationSeconds = std::trunc(durationSeconds);
    optimizerMaxDurationSeconds = static_cast<qint64>(std::clamp(
        durationSeconds,
        static_cast<double>(kMinOptimizerDurationSeconds),
        static_cast<double>(kMaxOptimizerDurationSeconds)));
    loopIntervalOverride = executionDefaults.value(QStringLiteral("loop_interval_override")).toString(QStringLiteral("1m"));
    connectorBackend = defaults.value(QStringLiteral("connector_backend")).toString();
}

qint64 estimateWarmupBars(const ConfigMap &configs) {
    qint64 maximum = 0;
    for (auto iterator = configs.cbegin(); iterator != configs.cend(); ++iterator) {
        if (!configEnabled(iterator.value())) continue;
        qint64 indicatorMaximum = 0;
        bool hasCandidate = false;
        inspectWarmupObject(iterator.value(), indicatorMaximum, hasCandidate);
        inspectWarmupObject(iterator.value().value(QStringLiteral("params")).toObject(), indicatorMaximum, hasCandidate);
        maximum = std::max(maximum, hasCandidate ? indicatorMaximum : 50);
    }
    return maximum == 0 ? 100 : maximum;
}

qint64 bufferedStartTimeMs(qint64 startTimeMs, const QString &interval, qint64 warmupBars) {
    if (startTimeMs <= 0 || warmupBars <= 0) return startTimeMs;
    const double bufferMs = static_cast<double>(warmupBars)
        * pythonIntervalSeconds(interval)
        * 2.0
        * 1000.0;
    if (!std::isfinite(bufferMs) || bufferMs <= 0.0) return startTimeMs;
    const double maxQint64 = static_cast<double>(std::numeric_limits<qint64>::max());
    const qint64 deltaMs = static_cast<qint64>(std::min(bufferMs, maxQint64));
    if (deltaMs <= 0) return startTimeMs;
    return startTimeMs > deltaMs ? startTimeMs - deltaMs : 1;
}

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
    const QString modeNormalized = NativePythonParity::canonicalConfigChoice(
        mode,
        PythonParityContract::kPythonOptimizerModeConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonOptimizerModeConfigChoices));
    const QString logicNormalized = NativePythonParity::canonicalConfigChoice(
        logic,
        PythonParityContract::kPythonLogicConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonLogicConfigChoices));
    if (modeNormalized == QStringLiteral("current")) {
        if (logicNormalized.compare(
                NativePythonParity::canonicalConfigChoice(
                    QStringLiteral("separate"),
                    PythonParityContract::kPythonLogicConfigChoices),
                Qt::CaseInsensitive) == 0) {
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

QStringList normalizedBatchSymbols(const QStringList &values) {
    QStringList normalized;
    for (const QString &value : values) {
        const QString symbol = value.trimmed().toUpper();
        if (!symbol.isEmpty() && !normalized.contains(symbol)) normalized.append(symbol);
    }
    return normalized;
}

QStringList normalizedBatchIntervals(const QStringList &values) {
    QStringList normalized;
    for (const QString &value : values) {
        const QString interval = NativeStrategyRuntime::canonicalizeBacktestInterval(QJsonValue(value));
        if (!interval.isEmpty() && !normalized.contains(interval)) normalized.append(interval);
    }
    return normalized;
}

qint64 estimateRunCount(const BatchRequest &request) {
    const OverridePlanSet overrides = buildOverridePlans(request);
    if (overrides.hasValidOverrides) {
        return overrides.plans.size();
    }
    const QVector<QStringList> groups = buildIndicatorGroups(
        request.indicatorConfigs,
        request.optimizerMode,
        request.optimizerComboSize,
        request.runTemplate.logic);
    const QStringList symbols = normalizedBatchSymbols(request.symbols);
    const QStringList intervals = normalizedBatchIntervals(request.intervals);
    return estimateRunCount(symbols.size(), intervals.size(), groups.size());
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

    const QStringList symbols = normalizedBatchSymbols(request.symbols);
    const QStringList intervals = normalizedBatchIntervals(request.intervals);
    const QVector<QStringList> groups = buildIndicatorGroups(
        request.indicatorConfigs,
        request.optimizerMode,
        request.optimizerComboSize,
        request.runTemplate.logic);
    const OverridePlanSet overridePlans = buildOverridePlans(request);
    const bool optimizerEnabled = request.optimizerEnabled && !overridePlans.hasValidOverrides;
    snapshot.insert(QStringLiteral("optimizer_enabled"), optimizerEnabled);
    snapshot.insert(
        QStringLiteral("optimizer_max_duration_seconds"),
        optimizerEnabled ? static_cast<double>(request.optimizerMaxDurationSeconds) : 0.0);
    QStringList plannedSymbols = symbols;
    QStringList plannedIntervals = intervals;
    if (overridePlans.hasValidOverrides) {
        plannedSymbols.clear();
        plannedIntervals.clear();
        for (const OverridePlan &plan : overridePlans.plans) {
            if (!plannedSymbols.contains(plan.symbol)) plannedSymbols.append(plan.symbol);
            if (!plannedIntervals.contains(plan.interval)) plannedIntervals.append(plan.interval);
        }
    }
    const qint64 runCount = overridePlans.hasValidOverrides
        ? static_cast<qint64>(overridePlans.plans.size())
        : estimateRunCount(symbols.size(), intervals.size(), groups.size());
    snapshot.insert(QStringLiteral("optimizer_run_count"), static_cast<double>(runCount));
    snapshot.insert(
        QStringLiteral("indicator_group_count"),
        overridePlans.hasValidOverrides ? overridePlans.plans.size() : groups.size());
    snapshot.insert(QStringLiteral("symbol_count"), plannedSymbols.size());
    snapshot.insert(QStringLiteral("interval_count"), plannedIntervals.size());
    snapshot.insert(
        QStringLiteral("pair_override_count"),
        overridePlans.hasValidOverrides ? overridePlans.plans.size() : 0);

    if (!overridePlans.hasValidOverrides && (symbols.isEmpty() || intervals.isEmpty())) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("failed"));
        snapshot.insert(QStringLiteral("status_message"), QStringLiteral("Select at least one symbol and interval."));
        return snapshot;
    }
    if ((overridePlans.hasValidOverrides && overridePlans.plans.isEmpty())
        || (!overridePlans.hasValidOverrides && groups.isEmpty())) {
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
    const QString mode = NativePythonParity::canonicalConfigChoice(
        request.optimizerMode,
        PythonParityContract::kPythonOptimizerModeConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonOptimizerModeConfigChoices));
    const QString scope = NativePythonParity::canonicalConfigChoice(
        request.optimizerScope,
        PythonParityContract::kPythonScanScopeConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonScanScopeConfigChoices));
    const QString originalLogic = NativePythonParity::canonicalConfigChoice(
        request.runTemplate.logic,
        PythonParityContract::kPythonLogicConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonLogicConfigChoices));
    const QString effectiveLogic = originalLogic.compare(
        NativePythonParity::canonicalConfigChoice(
            QStringLiteral("separate"),
            PythonParityContract::kPythonLogicConfigChoices),
        Qt::CaseInsensitive) == 0
        ? NativePythonParity::canonicalConfigChoice(
            QStringLiteral("and"),
            PythonParityContract::kPythonLogicConfigChoices)
        : originalLogic;
    QElapsedTimer optimizerTimer;
    optimizerTimer.start();
    const qint64 optimizerBudgetMilliseconds = request.optimizerMaxDurationSeconds > 0
        ? request.optimizerMaxDurationSeconds * 1000
        : 0;
    const auto budgetExceeded = [&]() {
        return optimizerEnabled
            && optimizerBudgetMilliseconds > 0
            && optimizerTimer.elapsed() >= optimizerBudgetMilliseconds;
    };
    const auto effectiveShouldStop = [&]() {
        return (shouldStop && shouldStop()) || budgetExceeded();
    };
    std::multiset<RankedRow, BestFirst> eligibleRows;
    QVector<QJsonObject> rejectedSamples;
    QVector<QJsonObject> plainRows;
    QJsonArray errors;
    qint64 processedCount = 0;
    qint64 candidateCount = 0;
    qint64 eligibleCount = 0;
    qint64 filteredCount = 0;
    bool cancelled = false;
    bool budgetExhausted = false;

    QMap<QString, CandleLoadResult> candleCache;
    const auto processRun = [&](const QString &symbol,
                                const QString &interval,
                                const QStringList &group,
                                NativeBacktestRuntime::Request runTemplate,
                                const QString &reportedLogic,
                                const QString &loopIntervalOverride,
                                const QString &connectorBackend) {
        if (effectiveShouldStop()) {
            cancelled = true;
            budgetExhausted = budgetExceeded();
            return false;
        }
        const QString cacheKey = symbol + QChar(0x1f) + interval;
        auto loadedIterator = candleCache.constFind(cacheKey);
        if (loadedIterator == candleCache.constEnd()) {
            candleCache.insert(cacheKey, loadCandles(symbol, interval, effectiveShouldStop));
            loadedIterator = candleCache.constFind(cacheKey);
        }
        const CandleLoadResult &loaded = loadedIterator.value();
        if (!loaded.ok) {
            if (effectiveShouldStop() || loaded.error == QStringLiteral("backtest_cancelled")) {
                cancelled = true;
                budgetExhausted = budgetExceeded();
                return false;
            }
            errors.append(QJsonObject{
                {QStringLiteral("symbol"), symbol},
                {QStringLiteral("interval"), interval},
                {QStringLiteral("indicator_keys"), QJsonArray::fromStringList(group)},
                {QStringLiteral("error"), loaded.error},
            });
            ++processedCount;
            return true;
        }

        runTemplate.symbol = symbol;
        runTemplate.interval = interval;
        runTemplate.indicators.clear();
        for (const QString &key : group) {
            QJsonObject config = request.indicatorConfigs.value(key);
            config.insert(QStringLiteral("enabled"), true);
            runTemplate.indicators.insert(key, config);
        }

        NativeBacktestRuntime::Result result = NativeBacktestRuntime::run(
            loaded.candles,
            runTemplate,
            effectiveShouldStop);
        ++processedCount;
        if (!result.ok) {
            if (effectiveShouldStop() || result.error == QStringLiteral("backtest_cancelled")) {
                cancelled = true;
                budgetExhausted = budgetExceeded();
                return false;
            }
            errors.append(QJsonObject{
                {QStringLiteral("symbol"), symbol},
                {QStringLiteral("interval"), interval},
                {QStringLiteral("indicator_keys"), QJsonArray::fromStringList(group)},
                {QStringLiteral("error"), result.error},
            });
            return true;
        }

        QJsonObject row = result.toJson();
        const QString visibleLogic = reportedLogic.isEmpty() ? result.logic : reportedLogic;
        row.insert(QStringLiteral("logic"), visibleLogic);
        row.insert(QStringLiteral("start"), request.startDisplay);
        row.insert(QStringLiteral("end"), request.endDisplay);
        row.insert(QStringLiteral("loop_interval_override"), loopIntervalOverride);
        row.insert(QStringLiteral("connector_backend"), connectorBackend);
        QJsonObject controls = strategyControls(runTemplate);
        controls.insert(QStringLiteral("logic"), visibleLogic);
        row.insert(QStringLiteral("strategy_controls"), controls);
        if (!optimizerEnabled) {
            ++candidateCount;
            ++eligibleCount;
            plainRows.append(row);
            return true;
        }
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
        return true;
    };

    snapshot.insert(QStringLiteral("state"), QStringLiteral("running"));
    if (overridePlans.hasValidOverrides) {
        for (const OverridePlan &plan : overridePlans.plans) {
            if (!processRun(
                    plan.symbol,
                    plan.interval,
                    plan.indicatorKeys,
                    plan.runTemplate,
                    plan.reportedLogic,
                    plan.loopIntervalOverride,
                    plan.connectorBackend)) {
                break;
            }
        }
    } else {
        for (const QString &symbol : symbols) {
            for (const QString &interval : intervals) {
                for (const QStringList &group : groups) {
                    NativeBacktestRuntime::Request runTemplate = request.runTemplate;
                    runTemplate.logic = effectiveLogic;
                    if (!processRun(
                            symbol,
                            interval,
                            group,
                            runTemplate,
                            originalLogic,
                            request.loopIntervalOverride,
                            request.connectorBackend)) {
                        break;
                    }
                }
                if (cancelled) break;
            }
            if (cancelled) break;
        }
    }

    QVector<QJsonObject> finalRows;
    if (!optimizerEnabled) {
        finalRows = plainRows;
        if (finalRows.size() > resultLimit) finalRows.resize(resultLimit);
    } else if (!eligibleRows.empty()) {
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
    if (optimizerEnabled) {
        for (QJsonObject &row : finalRows) {
            row.insert(QStringLiteral("optimizer_candidate_count"), static_cast<double>(candidateCount));
            row.insert(QStringLiteral("optimizer_eligible_count"), static_cast<double>(eligibleCount));
            row.insert(QStringLiteral("optimizer_filtered_count"), static_cast<double>(filteredCount));
            row.insert(QStringLiteral("optimizer_run_count"), static_cast<double>(runCount));
        }
    }

    if (budgetExhausted) {
        errors.append(QJsonObject{
            {QStringLiteral("error"), QStringLiteral("backtest_optimizer_time_budget_exhausted")},
            {QStringLiteral("processed_runs"), static_cast<double>(processedCount)},
            {QStringLiteral("max_duration_seconds"), static_cast<double>(request.optimizerMaxDurationSeconds)},
        });
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

    if (budgetExhausted) {
        snapshot.insert(QStringLiteral("state"), QStringLiteral("budget_exhausted"));
        snapshot.insert(QStringLiteral("cancelled"), false);
        snapshot.insert(
            QStringLiteral("status_message"),
            QStringLiteral("Native C++ optimizer time budget reached after %1 of %2 run(s). A checkpoint is available for resume.")
                .arg(processedCount)
                .arg(runCount));
    } else if (cancelled) {
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
