#include "NativeBacktestRuntime.h"
#include "NativePythonParityChoices.h"
#include "NativeStrategyRuntime.h"
#include "generated/PythonParityContract.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <utility>

namespace {

using Candle = NativeIndicatorRuntime::Candle;
using ConfigMap = NativeIndicatorRuntime::ConfigMap;
using Series = NativeIndicatorRuntime::Series;
using SeriesMap = NativeIndicatorRuntime::SeriesMap;

struct IndicatorSignals {
    QString key;
    bool filter = false;
    std::optional<QVector<bool>> buy;
    std::optional<QVector<bool>> sell;
    std::optional<QVector<bool>> gate;
};

struct DrawdownState {
    double peak = 0.0;
    double maxValue = 0.0;
    double maxPct = 0.0;
};

struct TradeState {
    bool active = false;
    QString direction;
    double entryPrice = 0.0;
    double peakPrice = 0.0;
    double troughPrice = 0.0;
    double maxValue = 0.0;
    double maxPct = 0.0;
    double notional = 0.0;
    double units = 0.0;
    double entryFee = 0.0;
};

std::optional<double> configNumber(const QJsonObject &config, const QString &key) {
    const QJsonValue value = config.value(key);
    if (value.isDouble()) {
        const double parsed = value.toDouble();
        if (std::isfinite(parsed)) {
            return parsed;
        }
    }
    if (value.isString()) {
        bool ok = false;
        const double parsed = value.toString().trimmed().toDouble(&ok);
        if (ok && std::isfinite(parsed)) {
            return parsed;
        }
    }
    return std::nullopt;
}

int configInt(const QJsonObject &config, const QString &key, int fallback) {
    return std::max(1, static_cast<int>(configNumber(config, key).value_or(fallback)));
}

QString configText(const QJsonObject &config, const QString &key, const QString &fallback = {}) {
    const QString text = config.value(key).toString().trimmed();
    return text.isEmpty() ? fallback : text;
}

Series filled(const Series &input, int size, double fallback = 0.0) {
    Series output(size, fallback);
    for (int index = 0; index < size && index < input.size(); ++index) {
        output[index] = std::isfinite(input[index]) ? input[index] : fallback;
    }
    return output;
}

Series rawSeries(const SeriesMap &series, const QString &key, int size) {
    const auto it = series.constFind(key);
    if (it == series.cend()) {
        return Series(size, std::numeric_limits<double>::quiet_NaN());
    }
    Series output = *it;
    output.resize(size);
    return output;
}

Series relativeVolume(const QVector<Candle> &candles, int length) {
    length = std::max(1, length);
    Series output(candles.size(), std::numeric_limits<double>::quiet_NaN());
    double rolling = 0.0;
    for (int index = 0; index < candles.size(); ++index) {
        rolling += candles[index].volume;
        if (index >= length) {
            rolling -= candles[index - length].volume;
        }
        const int count = std::min(length, index + 1);
        const double mean = rolling / static_cast<double>(count);
        output[index] = mean == 0.0 ? std::numeric_limits<double>::quiet_NaN() : candles[index].volume / mean;
    }
    return output;
}

Series backtestSeries(
    const QString &key,
    const QJsonObject &config,
    const QVector<Candle> &candles,
    const SeriesMap &computed) {
    const int size = candles.size();
    const QString mode = configText(config, QStringLiteral("signal_mode")).toLower();
    QString outputKey = key;
    if (key == QStringLiteral("bb")) outputKey = QStringLiteral("bb_mid");
    if (key == QStringLiteral("keltner")) outputKey = QStringLiteral("keltner_mid");
    if (key == QStringLiteral("stoch_rsi")) outputKey = QStringLiteral("stoch_rsi_k");
    if (key == QStringLiteral("ppo")) outputKey = QStringLiteral("ppo_hist");
    if (key == QStringLiteral("kst")) outputKey = QStringLiteral("kst_hist");
    if (key == QStringLiteral("stochastic")) outputKey = QStringLiteral("stochastic_k");

    if (key == QStringLiteral("macd")) {
        const Series line = rawSeries(computed, QStringLiteral("macd_line"), size);
        const Series signal = rawSeries(computed, QStringLiteral("macd_signal"), size);
        Series output(size, std::numeric_limits<double>::quiet_NaN());
        for (int index = 0; index < size; ++index) {
            if (std::isfinite(line[index]) && std::isfinite(signal[index])) {
                output[index] = line[index] - signal[index];
            }
        }
        return output;
    }

    if (key == QStringLiteral("volume") && mode == QStringLiteral("relative_to_sma")) {
        return relativeVolume(candles, configInt(config, QStringLiteral("length"), 20));
    }

    Series baseline = rawSeries(computed, outputKey, size);
    if (key == QStringLiteral("obv") && mode == QStringLiteral("slope")) {
        const int length = configInt(config, QStringLiteral("length"), 3);
        Series output(size, 0.0);
        for (int index = length; index < size; ++index) {
            if (std::isfinite(baseline[index]) && std::isfinite(baseline[index - length])) {
                output[index] = baseline[index] - baseline[index - length];
            }
        }
        return output;
    }

    if (mode == QStringLiteral("price_cross")) {
        Series output(size, 0.0);
        for (int index = 0; index < size; ++index) {
            if (std::isfinite(baseline[index])) {
                output[index] = candles[index].close - baseline[index];
            }
        }
        return output;
    }

    if (mode == QStringLiteral("band_position")) {
        QString lowerKey;
        QString upperKey;
        if (key == QStringLiteral("donchian")) {
            lowerKey = QStringLiteral("donchian_low");
            upperKey = QStringLiteral("donchian_high");
        } else if (key == QStringLiteral("bb")) {
            lowerKey = QStringLiteral("bb_lower");
            upperKey = QStringLiteral("bb_upper");
        } else if (key == QStringLiteral("keltner")) {
            lowerKey = QStringLiteral("keltner_lower");
            upperKey = QStringLiteral("keltner_upper");
        }
        if (!lowerKey.isEmpty()) {
            const Series lower = rawSeries(computed, lowerKey, size);
            const Series upper = rawSeries(computed, upperKey, size);
            Series output(size, 0.0);
            for (int index = 0; index < size; ++index) {
                const double range = upper[index] - lower[index];
                if (std::isfinite(range) && range != 0.0 && std::isfinite(lower[index])) {
                    output[index] = ((candles[index].close - lower[index]) / range) * 100.0;
                }
            }
            return output;
        }
    }

    if (mode == QStringLiteral("percent_of_close")) {
        Series output(size, 0.0);
        for (int index = 0; index < size; ++index) {
            if (candles[index].close != 0.0 && std::isfinite(baseline[index])) {
                output[index] = (baseline[index] / candles[index].close) * 100.0;
            }
        }
        return output;
    }
    return baseline;
}

QVector<bool> thresholdEvents(
    const Series &series,
    double threshold,
    bool lessOrEqual,
    qsizetype signalStartIndex = 0) {
    QVector<bool> events(series.size(), false);
    bool previous = false;
    for (int index = 0; index < series.size(); ++index) {
        if (index < signalStartIndex) continue;
        const double value = series[index];
        const bool current = std::isfinite(value) && (lessOrEqual ? value <= threshold : value >= threshold);
        events[index] = current && !previous;
        previous = current;
    }
    return events;
}

QString normalizedFilterOperator(const QJsonObject &config) {
    QString op = configText(config, QStringLiteral("filter_operator"), QStringLiteral("gte")).toLower();
    op.replace(QLatin1Char('-'), QLatin1Char('_'));
    op.replace(QLatin1Char(' '), QLatin1Char('_'));
    if (QStringList{QStringLiteral("greater_than_or_equal"), QStringLiteral("above_or_equal"), QStringLiteral("min")}.contains(op)) return QStringLiteral("gte");
    if (QStringList{QStringLiteral("greater_than"), QStringLiteral("above")}.contains(op)) return QStringLiteral("gt");
    if (QStringList{QStringLiteral("less_than_or_equal"), QStringLiteral("below_or_equal"), QStringLiteral("max")}.contains(op)) return QStringLiteral("lte");
    if (QStringList{QStringLiteral("less_than"), QStringLiteral("below")}.contains(op)) return QStringLiteral("lt");
    return op;
}

std::optional<double> filterThreshold(const QJsonObject &config) {
    if (const auto value = configNumber(config, QStringLiteral("filter_value"))) return value;
    if (const auto value = configNumber(config, QStringLiteral("buy_value"))) return value;
    return configNumber(config, QStringLiteral("sell_value"));
}

std::optional<QVector<bool>> filterState(const Series &series, const QJsonObject &config) {
    const QString op = normalizedFilterOperator(config);
    QVector<bool> output(series.size(), false);
    if (op == QStringLiteral("between") || op == QStringLiteral("outside")) {
        const auto buy = configNumber(config, QStringLiteral("buy_value"));
        const auto sell = configNumber(config, QStringLiteral("sell_value"));
        if (!buy || !sell) return std::nullopt;
        const double lower = std::min(*buy, *sell);
        const double upper = std::max(*buy, *sell);
        for (int index = 0; index < series.size(); ++index) {
            const bool between = std::isfinite(series[index]) && series[index] >= lower && series[index] <= upper;
            output[index] = op == QStringLiteral("outside") ? !between : between;
        }
        return output;
    }
    const auto threshold = filterThreshold(config);
    if (!threshold) return std::nullopt;
    for (int index = 0; index < series.size(); ++index) {
        if (!std::isfinite(series[index])) continue;
        if (op == QStringLiteral("gt")) output[index] = series[index] > *threshold;
        else if (op == QStringLiteral("lte")) output[index] = series[index] <= *threshold;
        else if (op == QStringLiteral("lt")) output[index] = series[index] < *threshold;
        else output[index] = series[index] >= *threshold;
    }
    return output;
}

bool isFilter(const QJsonObject &config) {
    QString role = configText(config, QStringLiteral("signal_role"), configText(config, QStringLiteral("role"), QStringLiteral("signal"))).toLower();
    role.replace(QLatin1Char('-'), QLatin1Char('_'));
    role.replace(QLatin1Char(' '), QLatin1Char('_'));
    return QStringList{QStringLiteral("filter"), QStringLiteral("entry_filter"), QStringLiteral("gate"), QStringLiteral("confirmation")}.contains(role);
}

void updateDrawdown(DrawdownState &state, double equity) {
    const double current = std::isfinite(equity) ? equity : 0.0;
    if (current > state.peak) {
        state.peak = current;
        return;
    }
    if (state.peak <= 0.0) return;
    const double value = state.peak - current;
    if (value <= 0.0) return;
    state.maxValue = std::max(state.maxValue, value);
    state.maxPct = std::max(state.maxPct, value / state.peak * 100.0);
}

QJsonArray stringArray(const QStringList &values) {
    QJsonArray output;
    for (const QString &value : values) output.append(value);
    return output;
}

} // namespace

namespace NativeBacktestRuntime {

Request::Request() {
    const QJsonObject defaults = QJsonDocument::fromJson(QByteArray(
        PythonParityContract::kPythonDefaultBacktestJson.data(),
        static_cast<int>(PythonParityContract::kPythonDefaultBacktestJson.size()))).object();
    const QJsonObject stopLoss = defaults.value(QStringLiteral("stop_loss")).toObject();
    const QJsonArray symbols = defaults.value(QStringLiteral("symbols")).toArray();
    const QJsonArray intervals = defaults.value(QStringLiteral("intervals")).toArray();
    const QJsonObject configuredIndicators = defaults.value(QStringLiteral("indicators")).toObject();
    for (auto iterator = configuredIndicators.constBegin(); iterator != configuredIndicators.constEnd(); ++iterator) {
        indicators.insert(iterator.key(), iterator.value().toObject());
    }
    symbol = symbols.isEmpty() ? QString() : symbols.first().toString();
    interval = intervals.isEmpty() ? QString() : intervals.first().toString();
    logic = defaults.value(QStringLiteral("logic")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonLogicConfigChoices));
    side = defaults.value(QStringLiteral("side")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonSideConfigChoices));
    capital = defaults.value(QStringLiteral("capital")).toDouble(1000.0);
    positionPct = defaults.value(QStringLiteral("position_pct")).toDouble(2.0);
    positionPctUnits = QStringLiteral("percent");
    leverage = defaults.value(QStringLiteral("leverage")).toDouble(20.0);
    marginMode = defaults.value(QStringLiteral("margin_mode")).toString(QStringLiteral("Isolated"));
    positionMode = defaults.value(QStringLiteral("position_mode")).toString(QStringLiteral("Hedge"));
    assetsMode = defaults.value(QStringLiteral("assets_mode")).toString(QStringLiteral("Single-Asset"));
    accountMode = defaults.value(QStringLiteral("account_mode")).toString(QStringLiteral("Classic Trading"));
    mddLogic = defaults.value(QStringLiteral("mdd_logic")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonMddLogicConfigChoices));
    stopLossEnabled = stopLoss.value(QStringLiteral("enabled")).toBool(false);
    stopLossMode = stopLoss.value(QStringLiteral("mode")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonStopLossModeConfigChoices));
    stopLossUsdt = stopLoss.value(QStringLiteral("usdt")).toDouble(0.0);
    stopLossPercent = stopLoss.value(QStringLiteral("percent")).toDouble(0.0);
    stopLossScope = stopLoss.value(QStringLiteral("scope")).toString(
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonStopLossScopeConfigChoices));
    feeBps = defaults.value(QStringLiteral("fee_bps")).toDouble(5.0);
    slippageBps = defaults.value(QStringLiteral("slippage_bps")).toDouble(2.0);
}

QJsonObject Result::toJson() const {
    return {
        {QStringLiteral("ok"), ok},
        {QStringLiteral("error"), error},
        {QStringLiteral("symbol"), symbol},
        {QStringLiteral("interval"), interval},
        {QStringLiteral("indicator_keys"), stringArray(indicatorKeys)},
        {QStringLiteral("trades"), trades},
        {QStringLiteral("roi_value"), roiValue},
        {QStringLiteral("roi_percent"), roiPercent},
        {QStringLiteral("final_equity"), finalEquity},
        {QStringLiteral("max_drawdown_value"), maxDrawdownValue},
        {QStringLiteral("max_drawdown_percent"), maxDrawdownPercent},
        {QStringLiteral("max_drawdown_during_value"), maxDrawdownDuringValue},
        {QStringLiteral("max_drawdown_during_percent"), maxDrawdownDuringPercent},
        {QStringLiteral("max_drawdown_result_value"), maxDrawdownResultValue},
        {QStringLiteral("max_drawdown_result_percent"), maxDrawdownResultPercent},
        {QStringLiteral("logic"), logic},
        {QStringLiteral("leverage"), leverage},
        {QStringLiteral("mdd_logic"), mddLogic},
        {QStringLiteral("side"), side},
        {QStringLiteral("capital"), capital},
        {QStringLiteral("position_pct"), positionPct},
        {QStringLiteral("position_pct_units"), positionPctUnits},
        {QStringLiteral("stop_loss_enabled"), stopLossEnabled},
        {QStringLiteral("stop_loss_mode"), stopLossMode},
        {QStringLiteral("stop_loss_usdt"), stopLossUsdt},
        {QStringLiteral("stop_loss_percent"), stopLossPercent},
        {QStringLiteral("stop_loss_scope"), stopLossScope},
        {QStringLiteral("margin_mode"), marginMode},
        {QStringLiteral("position_mode"), positionMode},
        {QStringLiteral("assets_mode"), assetsMode},
        {QStringLiteral("account_mode"), accountMode},
        {QStringLiteral("fee_bps"), feeBps},
        {QStringLiteral("slippage_bps"), slippageBps},
        {QStringLiteral("fees_paid"), feesPaid},
        {QStringLiteral("source"), QStringLiteral("native-cpp-backtest")},
    };
}

Result run(
    const QVector<Candle> &candles,
    const Request &request,
    const std::function<bool()> &shouldStop) {
    Result result;
    result.symbol = request.symbol.trimmed().toUpper();
    result.interval = NativeStrategyRuntime::canonicalizeBacktestInterval(
        QJsonValue(request.interval));
    result.logic = NativePythonParity::canonicalConfigChoice(
        request.logic,
        PythonParityContract::kPythonLogicConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonLogicConfigChoices));
    result.side = NativePythonParity::canonicalConfigChoice(
        request.side,
        PythonParityContract::kPythonSideConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonSideConfigChoices));
    result.capital = request.capital;
    result.leverage = std::max(1.0, request.leverage);
    result.marginMode = request.marginMode.trimmed().toUpper();
    result.positionMode = request.positionMode.trimmed();
    result.assetsMode = request.assetsMode.trimmed();
    result.accountMode = request.accountMode.trimmed();
    result.mddLogic = NativePythonParity::canonicalConfigChoice(
        request.mddLogic,
        PythonParityContract::kPythonMddLogicConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonMddLogicConfigChoices));
    result.stopLossEnabled = request.stopLossEnabled;
    result.stopLossMode = NativePythonParity::canonicalConfigChoice(
        request.stopLossMode,
        PythonParityContract::kPythonStopLossModeConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonStopLossModeConfigChoices));
    result.stopLossUsdt = std::max(0.0, request.stopLossUsdt);
    result.stopLossPercent = std::max(0.0, request.stopLossPercent);
    result.stopLossScope = NativePythonParity::canonicalConfigChoice(
        request.stopLossScope,
        PythonParityContract::kPythonStopLossScopeConfigChoices,
        NativePythonParity::defaultConfigChoice(PythonParityContract::kPythonStopLossScopeConfigChoices));
    result.feeBps = std::max(0.0, request.feeBps);
    result.slippageBps = std::max(0.0, request.slippageBps);
    const double feeRate = result.feeBps / 10000.0;
    const double slippageRate = result.slippageBps / 10000.0;

    const QString canonicalPctUnits = NativePythonParity::canonicalConfigChoice(
        request.positionPctUnits,
        PythonParityContract::kPythonPositionPctUnitsConfigChoices);
    double pctFraction = request.positionPct;
    if (canonicalPctUnits == QStringLiteral("percent")) pctFraction /= 100.0;
    else if (canonicalPctUnits != QStringLiteral("fraction") && pctFraction > 1.0) pctFraction /= 100.0;
    pctFraction = std::clamp(pctFraction, 0.0001, 1.0);
    result.positionPct = pctFraction;
    result.positionPctUnits = QStringLiteral("fraction");

    if (candles.isEmpty()) {
        result.error = QStringLiteral("Backtest requires at least one candle");
        return result;
    }
    if (result.capital <= 0.0 || !std::isfinite(result.capital)) {
        result.error = QStringLiteral("Backtest capital must be positive");
        return result;
    }
    const QStringList unsupported = NativeIndicatorRuntime::unsupportedEnabledIndicatorKeys(
        request.indicators,
        NativeIndicatorRuntime::IndicatorEnableSemantics::Backtest);
    if (!unsupported.isEmpty()) {
        result.error = QStringLiteral("Unsupported native backtest indicators: %1").arg(unsupported.join(QStringLiteral(", ")));
        return result;
    }

    int executionStartIndex = 0;
    int executionEndIndex = candles.size() - 1;
    bool hasTimestampedCandles = false;
    for (const Candle &candle : candles) {
        if (candle.openTimeMs != 0) {
            hasTimestampedCandles = true;
            break;
        }
    }
    if (hasTimestampedCandles && (request.startTimeMs != 0 || request.endTimeMs != 0)) {
        if (request.startTimeMs != 0 && request.endTimeMs != 0 && request.startTimeMs >= request.endTimeMs) {
            result.error = QStringLiteral("Backtest start must be earlier than backtest end");
            return result;
        }
        if (request.startTimeMs != 0) {
            while (executionStartIndex <= executionEndIndex
                   && candles.at(executionStartIndex).openTimeMs < request.startTimeMs) {
                ++executionStartIndex;
            }
        }
        if (request.endTimeMs != 0) {
            while (executionEndIndex >= executionStartIndex
                   && candles.at(executionEndIndex).openTimeMs > request.endTimeMs) {
                --executionEndIndex;
            }
        }
    }

    const SeriesMap computed = NativeIndicatorRuntime::computeConfiguredSeries(
        candles,
        request.indicators,
        NativeIndicatorRuntime::IndicatorEnableSemantics::Backtest);
    QVector<IndicatorSignals> indicatorSignals;
    for (auto it = request.indicators.cbegin(); it != request.indicators.cend(); ++it) {
        const QJsonObject config = it.value();
        if (!NativeIndicatorRuntime::isIndicatorEnabled(
                config,
                NativeIndicatorRuntime::IndicatorEnableSemantics::Backtest)) {
            continue;
        }
        IndicatorSignals indicatorSignal;
        indicatorSignal.key = it.key();
        indicatorSignal.filter = isFilter(config);
        const Series series = backtestSeries(it.key(), config, candles, computed);
        if (indicatorSignal.filter) {
            indicatorSignal.gate = filterState(series, config);
            if (!indicatorSignal.gate) {
                result.error = QStringLiteral("Backtest filter '%1' is missing a valid threshold rule").arg(it.key());
                return result;
            }
        } else {
            const auto buy = configNumber(config, QStringLiteral("buy_value"));
            const auto sell = configNumber(config, QStringLiteral("sell_value"));
            if (!buy && !sell) {
                result.error = QStringLiteral("Backtest indicator '%1' is missing buy/sell values").arg(it.key());
                return result;
            }
            if (buy) indicatorSignal.buy = thresholdEvents(
                series,
                *buy,
                sell && *buy < *sell,
                executionStartIndex);
            if (sell) indicatorSignal.sell = thresholdEvents(
                series,
                *sell,
                !(buy && *buy < *sell),
                executionStartIndex);
        }
        indicatorSignals.append(indicatorSignal);
        result.indicatorKeys.append(it.key());
    }

    QVector<const QVector<bool> *> buyArrays;
    QVector<const QVector<bool> *> sellArrays;
    QVector<const QVector<bool> *> filterArrays;
    for (const IndicatorSignals &indicatorSignal : indicatorSignals) {
        if (indicatorSignal.buy) buyArrays.append(&*indicatorSignal.buy);
        if (indicatorSignal.sell) sellArrays.append(&*indicatorSignal.sell);
        if (indicatorSignal.gate) filterArrays.append(&*indicatorSignal.gate);
    }
    if (buyArrays.isEmpty() && sellArrays.isEmpty()) {
        result.error = QStringLiteral("At least one signal indicator is required; filter-only indicators cannot open trades.");
        return result;
    }

    const int size = candles.size();
    QVector<bool> rawBuy(size, false);
    QVector<bool> rawSell(size, false);
    QVector<bool> entryFilter(size, true);
    const auto combine = [size](
                             const QVector<const QVector<bool> *> &arrays,
                             const QString &logic) {
        QVector<bool> output(size, false);
        if (arrays.isEmpty()) return output;
        for (int index = 0; index < size; ++index) {
            bool value = logic == QStringLiteral("AND");
            for (const QVector<bool> *array : arrays) {
                if (logic == QStringLiteral("AND")) value = value && array->value(index, false);
                else value = value || array->value(index, false);
            }
            output[index] = value;
        }
        return output;
    };
    rawBuy = combine(buyArrays, result.logic);
    rawSell = combine(sellArrays, QStringLiteral("OR"));
    if (executionStartIndex > executionEndIndex) {
        result.error = QStringLiteral("No candles fall inside the requested backtest window");
        return result;
    }
    for (int index = executionStartIndex; index <= executionEndIndex; ++index) {
        for (const QVector<bool> *array : filterArrays) entryFilter[index] = entryFilter[index] && array->value(index, false);
    }

    const bool canLong = result.side == QStringLiteral("BUY") || result.side == QStringLiteral("BOTH");
    const bool canShort = result.side == QStringLiteral("SELL") || result.side == QStringLiteral("BOTH");
    double equity = result.capital;
    bool positionOpen = false;
    double entryPrice = 0.0;
    double units = 0.0;
    double positionMargin = 0.0;
    double feesPaid = 0.0;
    QString direction;
    DrawdownState cumulative{equity, 0.0, 0.0};
    DrawdownState account{equity, 0.0, 0.0};
    DrawdownState perTrade;
    DrawdownState tradeDuring;
    DrawdownState tradeResult;
    TradeState trade;

    const auto recordEquity = [&cumulative, &account, &result](double value) {
        updateDrawdown(cumulative, value);
        if (result.mddLogic == QStringLiteral("entire_account")) updateDrawdown(account, value);
    };
    const auto resetTrade = [&trade]() { trade = TradeState{}; };
    const auto startTrade = [&trade, &entryPrice](const QString &tradeDirection, double tradeUnits, double entryFee) {
        const double absoluteUnits = std::abs(tradeUnits);
        if (absoluteUnits <= 0.0 || entryPrice <= 0.0) return;
        trade.active = true;
        trade.direction = tradeDirection;
        trade.entryPrice = entryPrice;
        trade.peakPrice = entryPrice;
        trade.troughPrice = entryPrice;
        trade.notional = std::abs(entryPrice * absoluteUnits);
        trade.units = absoluteUnits;
        trade.entryFee = std::max(0.0, entryFee);
    };
    const auto updateTrade = [&trade, &tradeDuring](double price, double high, double low) {
        if (!trade.active || trade.units <= 0.0) return;
        double drawdownPrice = 0.0;
        if (trade.direction == QStringLiteral("LONG")) {
            trade.peakPrice = std::max(trade.peakPrice, high);
            drawdownPrice = std::max(0.0, trade.peakPrice - std::min(low, price));
        } else {
            trade.troughPrice = std::min(trade.troughPrice, low);
            drawdownPrice = std::max(0.0, std::max(high, price) - trade.troughPrice);
        }
        const double value = drawdownPrice * trade.units;
        const double pct = trade.notional > 0.0 ? value / trade.notional * 100.0 : 0.0;
        trade.maxValue = std::max(trade.maxValue, value);
        trade.maxPct = std::max(trade.maxPct, pct);
        tradeDuring.maxValue = std::max(tradeDuring.maxValue, value);
        tradeDuring.maxPct = std::max(tradeDuring.maxPct, pct);
    };
    const auto finalizeTrade = [&trade, &tradeDuring, &tradeResult, &perTrade, &result, &resetTrade](
                                  std::optional<double> exitPrice,
                                  std::optional<double> realizedPnl = std::nullopt) {
        if (!trade.active) return;
        tradeDuring.maxValue = std::max(tradeDuring.maxValue, trade.maxValue);
        tradeDuring.maxPct = std::max(tradeDuring.maxPct, trade.maxPct);
        if (result.mddLogic == QStringLiteral("per_trade") && trade.maxValue > perTrade.maxValue) {
            perTrade.maxValue = trade.maxValue;
            perTrade.maxPct = trade.maxPct;
        }
        double lossValue = 0.0;
        double lossPct = 0.0;
        if (trade.units > 0.0 && trade.entryPrice > 0.0) {
            const double exit = exitPrice.value_or(trade.entryPrice);
            const double pnl = realizedPnl
                ? *realizedPnl - trade.entryFee
                : (trade.direction == QStringLiteral("LONG")
                    ? (exit - trade.entryPrice) * trade.units
                    : (trade.entryPrice - exit) * trade.units);
            if (pnl < 0.0) {
                lossValue = std::abs(pnl);
                if (trade.notional > 0.0) lossPct = lossValue / trade.notional * 100.0;
            }
        }
        tradeResult.maxValue = std::max(tradeResult.maxValue, lossValue);
        tradeResult.maxPct = std::max(tradeResult.maxPct, lossPct);
        resetTrade();
    };
    const auto entryExecutionPrice = [slippageRate](double marketPrice, const QString &tradeDirection) {
        return marketPrice * (tradeDirection == QStringLiteral("LONG") ? 1.0 + slippageRate : 1.0 - slippageRate);
    };
    const auto exitExecutionPrice = [slippageRate](double marketPrice, const QString &tradeDirection) {
        return marketPrice * (tradeDirection == QStringLiteral("LONG") ? 1.0 - slippageRate : 1.0 + slippageRate);
    };
    const auto realizeClose = [&direction, &entryPrice, &units, &feesPaid, feeRate, &exitExecutionPrice](double marketPrice) {
        const double exitPrice = exitExecutionPrice(marketPrice, direction);
        const double grossPnl = direction == QStringLiteral("LONG")
            ? (exitPrice - entryPrice) * units
            : (entryPrice - exitPrice) * units;
        const double exitFee = std::abs(exitPrice * units) * feeRate;
        feesPaid += exitFee;
        return std::make_pair(exitPrice, grossPnl - exitFee);
    };

    resetTrade();
    recordEquity(equity);
    for (int index = executionStartIndex; index <= executionEndIndex; ++index) {
        if (shouldStop && shouldStop()) {
            result.error = QStringLiteral("backtest_cancelled");
            return result;
        }
        const Candle &candle = candles[index];
        const double price = std::isfinite(candle.close) ? candle.close : 0.0;
        if (price <= 0.0) continue;
        const double high = std::isfinite(candle.high) && candle.high > 0.0 ? candle.high : price;
        const double low = std::isfinite(candle.low) && candle.low > 0.0 ? candle.low : price;
        bool entryBuy = rawBuy[index] && entryFilter[index];
        bool entrySell = rawSell[index] && entryFilter[index];
        if (!positionOpen && result.mddLogic == QStringLiteral("entire_account")) updateDrawdown(account, equity);

        if (positionOpen) {
            updateTrade(price, high, low);
            if (result.mddLogic == QStringLiteral("entire_account")) {
                if (units > 0.0) {
                    const double best = direction == QStringLiteral("LONG")
                        ? equity + (std::max(high, price) - entryPrice) * units
                        : equity + (entryPrice - std::min(low, price)) * units;
                    const double worst = direction == QStringLiteral("LONG")
                        ? equity + (std::min(low, price) - entryPrice) * units
                        : equity + (entryPrice - std::max(high, price)) * units;
                    updateDrawdown(account, best);
                    updateDrawdown(account, worst);
                } else updateDrawdown(account, equity);
            }
            double effectiveLeverage = result.leverage;
            if (result.marginMode == QStringLiteral("CROSS")) effectiveLeverage = std::max(1.0, result.leverage * pctFraction);
            if (direction == QStringLiteral("LONG") && effectiveLeverage > 1.0) {
                const double liquidation = std::max(0.0, entryPrice * (1.0 - 1.0 / effectiveLeverage));
                if (low <= liquidation) {
                    const double loss = std::min(equity, positionMargin);
                    equity = std::max(0.0, equity - loss);
                    recordEquity(equity);
                    finalizeTrade(liquidation, -loss);
                    positionOpen = false; units = 0.0; positionMargin = 0.0; direction.clear();
                    continue;
                }
            }
            if (direction == QStringLiteral("SHORT") && effectiveLeverage > 1.0) {
                const double liquidation = entryPrice * (1.0 + 1.0 / effectiveLeverage);
                if (high >= liquidation) {
                    const double loss = std::min(equity, positionMargin);
                    equity = std::max(0.0, equity - loss);
                    recordEquity(equity);
                    finalizeTrade(liquidation, -loss);
                    positionOpen = false; units = 0.0; positionMargin = 0.0; direction.clear();
                    continue;
                }
            }

            if (result.stopLossEnabled && units > 0.0 && entryPrice > 0.0) {
                const double worst = direction == QStringLiteral("LONG") ? std::min(price, low) : std::max(price, high);
                const double worstExit = exitExecutionPrice(worst, direction);
                const double loss = direction == QStringLiteral("LONG")
                    ? std::max(0.0, (entryPrice - worstExit) * units)
                    : std::max(0.0, (worstExit - entryPrice) * units);
                const double denominator = result.stopLossScope == QStringLiteral("per_trade") && positionMargin > 0.0
                    ? positionMargin : entryPrice * units;
                const double lossPct = denominator > 0.0 ? loss / denominator * 100.0 : 0.0;
                bool triggered = (result.stopLossMode == QStringLiteral("usdt") || result.stopLossMode == QStringLiteral("both"))
                    && result.stopLossUsdt > 0.0 && loss >= result.stopLossUsdt;
                if (!triggered && (result.stopLossMode == QStringLiteral("percent") || result.stopLossMode == QStringLiteral("both"))
                    && result.stopLossPercent > 0.0 && lossPct >= result.stopLossPercent) triggered = true;
                if (triggered) {
                    const auto [exitPrice, pnl] = realizeClose(worst);
                    equity = std::max(0.0, equity + pnl);
                    recordEquity(equity);
                    finalizeTrade(exitPrice, pnl);
                    positionOpen = false; units = 0.0; positionMargin = 0.0; direction.clear();
                    ++result.trades;
                    continue;
                }
            }

            if (direction == QStringLiteral("LONG") && rawSell[index]) {
                const auto [exitPrice, pnl] = realizeClose(price);
                equity = std::max(0.0, equity + pnl);
                recordEquity(equity);
                finalizeTrade(exitPrice, pnl);
                positionOpen = false; units = 0.0; positionMargin = 0.0; direction.clear();
                entrySell = canShort && entrySell && equity > 0.0;
            } else if (direction == QStringLiteral("SHORT") && rawBuy[index]) {
                const auto [exitPrice, pnl] = realizeClose(price);
                equity = std::max(0.0, equity + pnl);
                recordEquity(equity);
                finalizeTrade(exitPrice, pnl);
                positionOpen = false; units = 0.0; positionMargin = 0.0; direction.clear();
                entryBuy = canLong && entryBuy && equity > 0.0;
            }
        }

        if (!positionOpen && equity > 0.0) {
            if (entryBuy && canLong) {
                entryPrice = entryExecutionPrice(price, QStringLiteral("LONG"));
                positionMargin = equity * pctFraction;
                units = positionMargin * result.leverage / entryPrice;
                if (units > 0.0) {
                    const double entryFee = std::abs(entryPrice * units) * feeRate;
                    feesPaid += entryFee;
                    equity = std::max(0.0, equity - entryFee);
                    positionOpen = true; direction = QStringLiteral("LONG"); startTrade(direction, units, entryFee); ++result.trades;
                } else positionMargin = 0.0;
            } else if (entrySell && canShort) {
                entryPrice = entryExecutionPrice(price, QStringLiteral("SHORT"));
                positionMargin = equity * pctFraction;
                units = positionMargin * result.leverage / entryPrice;
                if (units > 0.0) {
                    const double entryFee = std::abs(entryPrice * units) * feeRate;
                    feesPaid += entryFee;
                    equity = std::max(0.0, equity - entryFee);
                    positionOpen = true; direction = QStringLiteral("SHORT"); startTrade(direction, units, entryFee); ++result.trades;
                } else positionMargin = 0.0;
            }
        }
    }

    if (positionOpen && units > 0.0) {
        const double last = candles.at(executionEndIndex).close;
        const auto [exitPrice, pnl] = realizeClose(last);
        equity = std::max(0.0, equity + pnl);
        recordEquity(equity);
        finalizeTrade(exitPrice, pnl);
    }

    result.finalEquity = equity;
    result.roiValue = equity - result.capital;
    result.roiPercent = result.capital != 0.0 ? result.roiValue / result.capital * 100.0 : 0.0;
    result.feesPaid = feesPaid;
    result.maxDrawdownDuringValue = tradeDuring.maxValue;
    result.maxDrawdownDuringPercent = tradeDuring.maxPct;
    result.maxDrawdownResultValue = tradeResult.maxValue;
    result.maxDrawdownResultPercent = tradeResult.maxPct;
    if (result.mddLogic == QStringLiteral("per_trade")) {
        result.maxDrawdownValue = perTrade.maxValue;
        result.maxDrawdownPercent = perTrade.maxPct;
    } else if (result.mddLogic == QStringLiteral("entire_account")) {
        result.maxDrawdownValue = account.maxValue;
        result.maxDrawdownPercent = account.maxPct;
    } else {
        result.maxDrawdownValue = cumulative.maxValue;
        result.maxDrawdownPercent = cumulative.maxPct;
    }
    result.ok = true;
    return result;
}

} // namespace NativeBacktestRuntime
