#include "NativeIndicatorRuntime.h"

#include <QJsonValue>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <tuple>

namespace {

using Candle = NativeIndicatorRuntime::Candle;
using Series = NativeIndicatorRuntime::Series;

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

Series filled(qsizetype size, double value = kNaN) {
    return Series(size, value);
}

bool configEnabled(const QJsonObject &config) {
    const QJsonValue value = config.value(QStringLiteral("enabled"));
    if (value.isBool()) {
        return value.toBool();
    }
    if (value.isDouble()) {
        return value.toDouble() != 0.0;
    }
    if (value.isString()) {
        const QString normalized = value.toString().trimmed().toLower();
        return normalized == QStringLiteral("1")
            || normalized == QStringLiteral("true")
            || normalized == QStringLiteral("yes")
            || normalized == QStringLiteral("on")
            || normalized == QStringLiteral("y");
    }
    return false;
}

qsizetype configLength(const QJsonObject &config, const QString &key, qsizetype fallback) {
    const QJsonValue value = config.value(key);
    if (value.isDouble()) {
        const double candidate = value.toDouble();
        if (std::isfinite(candidate) && candidate > 0.0) {
            return std::max<qsizetype>(1, static_cast<qsizetype>(candidate));
        }
    }
    return fallback;
}

double configDouble(const QJsonObject &config, const QString &key, double fallback) {
    const QJsonValue value = config.value(key);
    bool ok = false;
    const double candidate = value.isDouble()
        ? value.toDouble()
        : value.toString().trimmed().toDouble(&ok);
    if ((value.isDouble() || ok) && std::isfinite(candidate) && candidate != 0.0) {
        return candidate;
    }
    return fallback;
}

QString configString(const QJsonObject &config, const QString &key) {
    return config.value(key).toString().trimmed().toUpper();
}

Series closes(const QVector<Candle> &candles) {
    Series result;
    result.reserve(candles.size());
    for (const Candle &candle : candles) {
        result.push_back(candle.close);
    }
    return result;
}

Series volumes(const QVector<Candle> &candles) {
    Series result;
    result.reserve(candles.size());
    for (const Candle &candle : candles) {
        result.push_back(candle.volume);
    }
    return result;
}

Series emaSeries(const Series &values, qsizetype length) {
    const double alpha = 2.0 / (static_cast<double>(std::max<qsizetype>(1, length)) + 1.0);
    double previous = kNaN;
    Series result;
    result.reserve(values.size());
    for (double value : values) {
        if (!std::isfinite(value)) {
            previous = kNaN;
        } else if (std::isfinite(previous)) {
            previous = alpha * value + (1.0 - alpha) * previous;
        } else {
            previous = value;
        }
        result.push_back(previous);
    }
    return result;
}

Series ewmAlphaSeries(const Series &values, double alpha) {
    double previous = kNaN;
    Series result;
    result.reserve(values.size());
    for (double value : values) {
        previous = std::isfinite(previous)
            ? alpha * value + (1.0 - alpha) * previous
            : value;
        result.push_back(previous);
    }
    return result;
}

Series rollingMeanMin(const Series &values, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result;
    result.reserve(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        const qsizetype start = index + 1 - std::min(length, index + 1);
        double sum = 0.0;
        qsizetype count = 0;
        for (qsizetype cursor = start; cursor <= index; ++cursor) {
            if (std::isfinite(values[cursor])) {
                sum += values[cursor];
                ++count;
            }
        }
        result.push_back(count > 0 ? sum / static_cast<double>(count) : kNaN);
    }
    return result;
}

Series rollingSumMin(const Series &values, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result;
    result.reserve(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        const qsizetype start = index + 1 - std::min(length, index + 1);
        double sum = 0.0;
        qsizetype count = 0;
        for (qsizetype cursor = start; cursor <= index; ++cursor) {
            if (std::isfinite(values[cursor])) {
                sum += values[cursor];
                ++count;
            }
        }
        result.push_back(count > 0 ? sum : kNaN);
    }
    return result;
}

Series rollingMeanExact(const Series &values, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result = filled(values.size());
    for (qsizetype index = length - 1; index < values.size(); ++index) {
        double sum = 0.0;
        bool finite = true;
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            if (!std::isfinite(values[cursor])) {
                finite = false;
                break;
            }
            sum += values[cursor];
        }
        if (finite) {
            result[index] = sum / static_cast<double>(length);
        }
    }
    return result;
}

std::tuple<Series, Series, Series> bollingerBands(
    const Series &values,
    qsizetype length,
    double multiplier
) {
    length = std::max<qsizetype>(1, length);
    Series middle = rollingMeanExact(values, length);
    Series deviation = filled(values.size());
    for (qsizetype index = length - 1; index < values.size(); ++index) {
        if (length < 2 || !std::isfinite(middle[index])) {
            continue;
        }
        double squared = 0.0;
        bool finite = true;
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            if (!std::isfinite(values[cursor])) {
                finite = false;
                break;
            }
            squared += std::pow(values[cursor] - middle[index], 2.0);
        }
        if (finite) {
            deviation[index] = std::sqrt(squared / static_cast<double>(length - 1));
        }
    }
    Series upper(values.size());
    Series lower(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        upper[index] = middle[index] + multiplier * deviation[index];
        lower[index] = middle[index] - multiplier * deviation[index];
    }
    return {upper, middle, lower};
}

Series bollingerBandWidth(const Series &values, qsizetype length, double multiplier) {
    auto [upper, middle, lower] = bollingerBands(values, length, multiplier);
    Series result(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        result[index] = std::isfinite(middle[index]) && middle[index] != 0.0
                && std::isfinite(upper[index]) && std::isfinite(lower[index])
            ? (upper[index] - lower[index]) / middle[index] * 100.0
            : 0.0;
    }
    return result;
}

Series trueRangeSeries(const QVector<Candle> &candles) {
    Series result;
    result.reserve(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        const Candle &candle = candles[index];
        double range = std::abs(candle.high - candle.low);
        if (index > 0) {
            range = std::max(range, std::abs(candle.high - candles[index - 1].close));
            range = std::max(range, std::abs(candle.low - candles[index - 1].close));
        }
        result.push_back(range);
    }
    return result;
}

Series atrSeries(const QVector<Candle> &candles, qsizetype length) {
    const Series ranges = trueRangeSeries(candles);
    const double alpha = 1.0 / static_cast<double>(std::max<qsizetype>(1, length));
    double previous = kNaN;
    Series result;
    result.reserve(ranges.size());
    for (double value : ranges) {
        previous = std::isfinite(previous)
            ? alpha * value + (1.0 - alpha) * previous
            : value;
        result.push_back(previous);
    }
    return result;
}

Series natrSeries(const QVector<Candle> &candles, qsizetype length) {
    Series result = atrSeries(candles, length);
    for (qsizetype index = 0; index < result.size(); ++index) {
        result[index] = std::isfinite(result[index]) && std::isfinite(candles[index].close)
                && candles[index].close != 0.0
            ? result[index] / candles[index].close * 100.0
            : 0.0;
    }
    return result;
}

Series obvSeries(const QVector<Candle> &candles) {
    double cumulative = 0.0;
    Series result;
    result.reserve(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        if (index > 0) {
            if (candles[index].close > candles[index - 1].close) {
                cumulative += candles[index].volume;
            } else if (candles[index].close < candles[index - 1].close) {
                cumulative -= candles[index].volume;
            }
        }
        result.push_back(cumulative);
    }
    return result;
}

Series relativeVolumeSeries(const QVector<Candle> &candles, qsizetype length) {
    const Series volume = volumes(candles);
    const Series average = rollingMeanMin(volume, length);
    Series result(volume.size());
    for (qsizetype index = 0; index < volume.size(); ++index) {
        result[index] = std::isfinite(average[index]) && average[index] != 0.0
            ? volume[index] / average[index]
            : 0.0;
    }
    return result;
}

Series chaikinMoneyFlowSeries(const QVector<Candle> &candles, qsizetype length) {
    Series moneyFlow;
    moneyFlow.reserve(candles.size());
    for (const Candle &candle : candles) {
        const double range = candle.high - candle.low;
        moneyFlow.push_back(range == 0.0
            ? 0.0
            : ((candle.close - candle.low) - (candle.high - candle.close))
                / range * candle.volume);
    }
    const Series flowSum = rollingSumMin(moneyFlow, length);
    const Series volumeSum = rollingSumMin(volumes(candles), length);
    Series result(candles.size());
    for (qsizetype index = 0; index < result.size(); ++index) {
        result[index] = std::isfinite(flowSum[index]) && std::isfinite(volumeSum[index])
                && volumeSum[index] != 0.0
            ? flowSum[index] / volumeSum[index]
            : 0.0;
    }
    return result;
}

Series cciSeries(const QVector<Candle> &candles, qsizetype length, double constant) {
    length = std::max<qsizetype>(1, length);
    Series typical;
    typical.reserve(candles.size());
    for (const Candle &candle : candles) {
        typical.push_back((candle.high + candle.low + candle.close) / 3.0);
    }
    const Series average = rollingMeanMin(typical, length);
    Series result(typical.size());
    for (qsizetype index = 0; index < typical.size(); ++index) {
        const qsizetype start = index + 1 - std::min(length, index + 1);
        double deviation = 0.0;
        for (qsizetype cursor = start; cursor <= index; ++cursor) {
            deviation += std::abs(typical[cursor] - average[index]);
        }
        deviation /= static_cast<double>(index + 1 - start);
        const double denominator = constant * deviation;
        result[index] = std::isfinite(denominator) && denominator != 0.0
            ? (typical[index] - average[index]) / denominator
            : 0.0;
    }
    return result;
}

Series rocSeries(const Series &values, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        result[index] = index < length || values[index - length] == 0.0
            ? 0.0
            : (values[index] - values[index - length]) / values[index - length] * 100.0;
    }
    return result;
}

Series trixSeries(const Series &values, qsizetype length) {
    const Series third = emaSeries(emaSeries(emaSeries(values, length), length), length);
    Series result(third.size());
    for (qsizetype index = 1; index < third.size(); ++index) {
        result[index] = third[index - 1] == 0.0
            ? 0.0
            : (third[index] / third[index - 1] - 1.0) * 100.0;
    }
    return result;
}

std::tuple<Series, Series, Series> macdSeries(
    const Series &values,
    qsizetype fastLength,
    qsizetype slowLength,
    qsizetype signalLength
) {
    const Series fast = emaSeries(values, fastLength);
    const Series slow = emaSeries(values, slowLength);
    Series line(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        line[index] = fast[index] - slow[index];
    }
    const Series signal = emaSeries(line, signalLength);
    Series histogram(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        histogram[index] = line[index] - signal[index];
    }
    return {line, signal, histogram};
}

std::tuple<Series, Series, Series> ppoSeries(
    const Series &values,
    qsizetype fastLength,
    qsizetype slowLength,
    qsizetype signalLength
) {
    const Series fast = emaSeries(values, fastLength);
    const Series slow = emaSeries(values, slowLength);
    Series line(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        line[index] = slow[index] != 0.0
            ? (fast[index] - slow[index]) / slow[index] * 100.0
            : 0.0;
    }
    const Series signal = emaSeries(line, signalLength);
    Series histogram(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        histogram[index] = line[index] - signal[index];
    }
    return {line, signal, histogram};
}

Series awesomeOscillatorSeries(
    const QVector<Candle> &candles,
    qsizetype fastLength,
    qsizetype slowLength
) {
    Series median;
    median.reserve(candles.size());
    for (const Candle &candle : candles) {
        median.push_back((candle.high + candle.low) / 2.0);
    }
    const Series fast = rollingMeanMin(median, fastLength);
    const Series slow = rollingMeanMin(median, slowLength);
    Series result(candles.size());
    for (qsizetype index = 0; index < result.size(); ++index) {
        result[index] = std::isfinite(fast[index]) && std::isfinite(slow[index])
            ? fast[index] - slow[index]
            : 0.0;
    }
    return result;
}

Series vwapSeries(const QVector<Candle> &candles, qsizetype length) {
    Series weighted;
    Series volume;
    weighted.reserve(candles.size());
    volume.reserve(candles.size());
    for (const Candle &candle : candles) {
        const double typical = (candle.high + candle.low + candle.close) / 3.0;
        weighted.push_back(typical * candle.volume);
        volume.push_back(candle.volume);
    }
    const Series weightedSum = rollingSumMin(weighted, length);
    const Series volumeSum = rollingSumMin(volume, length);
    Series result(candles.size());
    for (qsizetype index = 0; index < result.size(); ++index) {
        result[index] = std::isfinite(weightedSum[index]) && std::isfinite(volumeSum[index])
                && volumeSum[index] != 0.0
            ? weightedSum[index] / volumeSum[index]
            : kNaN;
    }
    return result;
}

Series mfiSeries(const QVector<Candle> &candles, qsizetype length) {
    Series typical;
    Series raw;
    typical.reserve(candles.size());
    raw.reserve(candles.size());
    for (const Candle &candle : candles) {
        const double price = (candle.high + candle.low + candle.close) / 3.0;
        typical.push_back(price);
        raw.push_back(price * candle.volume);
    }
    Series positive(candles.size());
    Series negative(candles.size());
    for (qsizetype index = 1; index < candles.size(); ++index) {
        if (typical[index] > typical[index - 1]) {
            positive[index] = raw[index];
        } else if (typical[index] < typical[index - 1]) {
            negative[index] = raw[index];
        }
    }
    const Series positiveSum = rollingSumMin(positive, length);
    const Series negativeSum = rollingSumMin(negative, length);
    Series result(candles.size());
    for (qsizetype index = 0; index < result.size(); ++index) {
        if (positiveSum[index] == 0.0 && negativeSum[index] == 0.0) {
            result[index] = 50.0;
        } else if (positiveSum[index] == 0.0) {
            result[index] = 0.0;
        } else if (negativeSum[index] == 0.0) {
            result[index] = 100.0;
        } else {
            result[index] = 100.0 - 100.0 / (1.0 + positiveSum[index] / negativeSum[index]);
        }
    }
    return result;
}

Series rsiSeries(const QVector<Candle> &candles, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result = filled(candles.size());
    if (candles.size() < 2) {
        return result;
    }
    const double alpha = 1.0 / static_cast<double>(length);
    double averageGain = 0.0;
    double averageLoss = 0.0;
    for (qsizetype index = 1; index < candles.size(); ++index) {
        const double delta = candles[index].close - candles[index - 1].close;
        if (!std::isfinite(delta)) {
            continue;
        }
        const double gain = std::max(delta, 0.0);
        const double loss = std::max(-delta, 0.0);
        if (index == 1) {
            averageGain = gain;
            averageLoss = loss;
        } else {
            averageGain = alpha * gain + (1.0 - alpha) * averageGain;
            averageLoss = alpha * loss + (1.0 - alpha) * averageLoss;
        }
        if (averageLoss == 0.0) {
            result[index] = averageGain == 0.0 ? kNaN : 100.0;
        } else {
            result[index] = 100.0 - 100.0 / (1.0 + averageGain / averageLoss);
        }
    }
    return result;
}

std::pair<Series, Series> stochRsiSeries(
    const QVector<Candle> &candles,
    qsizetype length,
    qsizetype smoothK,
    qsizetype smoothD
) {
    length = std::max<qsizetype>(1, length);
    const Series rsi = rsiSeries(candles, length);
    Series stochastic = filled(rsi.size());
    for (qsizetype index = length - 1; index < rsi.size(); ++index) {
        double minimum = std::numeric_limits<double>::infinity();
        double maximum = -std::numeric_limits<double>::infinity();
        bool finite = true;
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            if (!std::isfinite(rsi[cursor])) {
                finite = false;
                break;
            }
            minimum = std::min(minimum, rsi[cursor]);
            maximum = std::max(maximum, rsi[cursor]);
        }
        if (finite && maximum != minimum) {
            stochastic[index] = 100.0 * (rsi[index] - minimum) / (maximum - minimum);
        }
    }
    Series k = rollingMeanExact(stochastic, smoothK);
    Series d = rollingMeanExact(k, smoothD);
    return {k, d};
}

Series williamsRSeries(const QVector<Candle> &candles, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result = filled(candles.size());
    for (qsizetype index = length - 1; index < candles.size(); ++index) {
        double highest = -std::numeric_limits<double>::infinity();
        double lowest = std::numeric_limits<double>::infinity();
        bool finite = true;
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            const Candle &candle = candles[cursor];
            if (!std::isfinite(candle.high) || !std::isfinite(candle.low)
                || !std::isfinite(candle.close)) {
                finite = false;
                break;
            }
            highest = std::max(highest, candle.high);
            lowest = std::min(lowest, candle.low);
        }
        if (finite && highest != lowest) {
            result[index] = (highest - candles[index].close) / (highest - lowest) * -100.0;
        }
    }
    return result;
}

std::pair<Series, Series> stochasticSeries(
    const QVector<Candle> &candles,
    qsizetype length,
    qsizetype smoothK,
    qsizetype smoothD
) {
    length = std::max<qsizetype>(1, length);
    Series raw = filled(candles.size());
    for (qsizetype index = length - 1; index < candles.size(); ++index) {
        double high = -std::numeric_limits<double>::infinity();
        double low = std::numeric_limits<double>::infinity();
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            high = std::max(high, candles[cursor].high);
            low = std::min(low, candles[cursor].low);
        }
        if (high != low) {
            raw[index] = 100.0 * (candles[index].close - low) / (high - low);
        }
    }
    Series k = rollingMeanMin(raw, smoothK);
    Series d = rollingMeanMin(k, smoothD);
    for (double &value : k) {
        if (!std::isfinite(value)) {
            value = 0.0;
        }
    }
    for (double &value : d) {
        if (!std::isfinite(value)) {
            value = 0.0;
        }
    }
    return {k, d};
}

std::tuple<Series, Series, Series> keltnerChannels(
    const QVector<Candle> &candles,
    qsizetype length,
    qsizetype atrLength,
    double multiplier
) {
    Series middle = emaSeries(closes(candles), length);
    const Series range = atrSeries(candles, atrLength);
    Series upper(candles.size());
    Series lower(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        upper[index] = middle[index] + range[index] * multiplier;
        lower[index] = middle[index] - range[index] * multiplier;
    }
    return {upper, middle, lower};
}

Series rollingMidpoint(const QVector<Candle> &candles, qsizetype length) {
    length = std::max<qsizetype>(1, length);
    Series result = filled(candles.size());
    for (qsizetype index = length - 1; index < candles.size(); ++index) {
        double high = -std::numeric_limits<double>::infinity();
        double low = std::numeric_limits<double>::infinity();
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            high = std::max(high, candles[cursor].high);
            low = std::min(low, candles[cursor].low);
        }
        result[index] = (high + low) / 2.0;
    }
    return result;
}

std::tuple<Series, Series, Series> donchianChannels(
    const QVector<Candle> &candles,
    qsizetype length
) {
    length = std::max<qsizetype>(1, length);
    Series high = filled(candles.size());
    Series low = filled(candles.size());
    for (qsizetype index = length - 1; index < candles.size(); ++index) {
        double highest = -std::numeric_limits<double>::infinity();
        double lowest = std::numeric_limits<double>::infinity();
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            highest = std::max(highest, candles[cursor].high);
            lowest = std::min(lowest, candles[cursor].low);
        }
        high[index] = highest;
        low[index] = lowest;
    }
    Series middle(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        middle[index] = (high[index] + low[index]) / 2.0;
    }
    return {high, low, middle};
}

Series parabolicSarSeries(const QVector<Candle> &candles, double af, double maxAf) {
    if (candles.isEmpty()) {
        return {};
    }
    Series result = closes(candles);
    bool bullish = true;
    double acceleration = af;
    double extremePoint = candles.first().high;
    result[0] = candles.first().low;
    for (qsizetype index = 1; index < candles.size(); ++index) {
        result[index] = result[index - 1]
            + acceleration * (extremePoint - result[index - 1]);
        if (bullish) {
            if (candles[index].low < result[index]) {
                bullish = false;
                result[index] = extremePoint;
                acceleration = af;
                extremePoint = candles[index].low;
            } else if (candles[index].high > extremePoint) {
                extremePoint = candles[index].high;
                acceleration = std::min(acceleration + af, maxAf);
            }
        } else if (candles[index].high > result[index]) {
            bullish = true;
            result[index] = extremePoint;
            acceleration = af;
            extremePoint = candles[index].high;
        } else if (candles[index].low < extremePoint) {
            extremePoint = candles[index].low;
            acceleration = std::min(acceleration + af, maxAf);
        }
    }
    return result;
}

Series shiftRight(const Series &values, qsizetype offset) {
    Series result = filled(values.size());
    for (qsizetype index = offset; index < values.size(); ++index) {
        result[index] = values[index - offset];
    }
    return result;
}

Series shiftLeft(const Series &values, qsizetype offset) {
    Series result = filled(values.size());
    for (qsizetype index = 0; index + offset < values.size(); ++index) {
        result[index] = values[index + offset];
    }
    return result;
}

std::tuple<Series, Series, Series, Series, Series> ichimokuCloud(
    const QVector<Candle> &candles,
    qsizetype conversionLength,
    qsizetype baseLength,
    qsizetype spanBLength,
    qsizetype displacement
) {
    Series tenkan = rollingMidpoint(candles, conversionLength);
    Series kijun = rollingMidpoint(candles, baseLength);
    Series unshiftedSpanA(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        unshiftedSpanA[index] = (tenkan[index] + kijun[index]) / 2.0;
    }
    Series spanA = shiftRight(unshiftedSpanA, displacement);
    Series spanB = shiftRight(rollingMidpoint(candles, spanBLength), displacement);
    Series chikou = shiftLeft(closes(candles), displacement);
    return {tenkan, kijun, spanA, spanB, chikou};
}

std::tuple<Series, Series, Series> kstSeries(
    const Series &values,
    qsizetype roc1,
    qsizetype roc2,
    qsizetype roc3,
    qsizetype roc4,
    qsizetype sma1,
    qsizetype sma2,
    qsizetype sma3,
    qsizetype sma4,
    qsizetype signalLength
) {
    const Series first = rollingMeanMin(rocSeries(values, roc1), sma1);
    const Series second = rollingMeanMin(rocSeries(values, roc2), sma2);
    const Series third = rollingMeanMin(rocSeries(values, roc3), sma3);
    const Series fourth = rollingMeanMin(rocSeries(values, roc4), sma4);
    Series line(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        line[index] = first[index] + 2.0 * second[index]
            + 3.0 * third[index] + 4.0 * fourth[index];
    }
    Series signal = rollingMeanMin(line, signalLength);
    Series histogram(values.size());
    for (qsizetype index = 0; index < values.size(); ++index) {
        histogram[index] = line[index] - signal[index];
    }
    return {line, signal, histogram};
}

std::tuple<Series, Series, Series> aroonSeries(
    const QVector<Candle> &candles,
    qsizetype length
) {
    length = std::max<qsizetype>(1, length);
    const auto score = [length](const Series &values, bool findHigh) {
        Series result;
        result.reserve(values.size());
        for (qsizetype index = 0; index < values.size(); ++index) {
            const qsizetype start = index + 1 - std::min(length, index + 1);
            const qsizetype windowSize = index + 1 - start;
            if (windowSize <= 1) {
                result.push_back(100.0);
                continue;
            }
            qsizetype chosen = start;
            for (qsizetype cursor = start; cursor <= index; ++cursor) {
                if ((findHigh && values[cursor] >= values[chosen])
                    || (!findHigh && values[cursor] <= values[chosen])) {
                    chosen = cursor;
                }
            }
            result.push_back(
                100.0 * static_cast<double>(chosen - start)
                / static_cast<double>(windowSize - 1));
        }
        return result;
    };
    Series highs;
    Series lows;
    highs.reserve(candles.size());
    lows.reserve(candles.size());
    for (const Candle &candle : candles) {
        highs.push_back(candle.high);
        lows.push_back(candle.low);
    }
    Series up = score(highs, true);
    Series down = score(lows, false);
    Series oscillator(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        oscillator[index] = up[index] - down[index];
    }
    return {up, down, oscillator};
}

Series choppinessIndexSeries(const QVector<Candle> &candles, qsizetype length) {
    length = std::max<qsizetype>(2, length);
    const Series trueRange = trueRangeSeries(candles);
    Series result(candles.size());
    for (qsizetype index = length - 1; index < candles.size(); ++index) {
        double high = -std::numeric_limits<double>::infinity();
        double low = std::numeric_limits<double>::infinity();
        double rangeSum = 0.0;
        for (qsizetype cursor = index + 1 - length; cursor <= index; ++cursor) {
            high = std::max(high, candles[cursor].high);
            low = std::min(low, candles[cursor].low);
            rangeSum += trueRange[cursor];
        }
        const double priceRange = high - low;
        if (priceRange > 0.0 && rangeSum > 0.0) {
            result[index] = 100.0 * std::log10(rangeSum / priceRange)
                / std::log10(static_cast<double>(length));
        }
    }
    return result;
}

Series ultimateOscillatorSeries(
    const QVector<Candle> &candles,
    qsizetype shortLength,
    qsizetype mediumLength,
    qsizetype longLength
) {
    Series buyingPressure;
    Series trueRange;
    buyingPressure.reserve(candles.size());
    trueRange.reserve(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        const Candle &candle = candles[index];
        const double previousClose = index == 0 ? candle.close : candles[index - 1].close;
        const double trueLow = std::min(candle.low, previousClose);
        const double trueHigh = std::max(candle.high, previousClose);
        buyingPressure.push_back(candle.close - trueLow);
        trueRange.push_back(trueHigh - trueLow);
    }
    const auto ratio = [&buyingPressure, &trueRange](qsizetype length) {
        const Series pressure = rollingSumMin(buyingPressure, length);
        const Series range = rollingSumMin(trueRange, length);
        Series result(pressure.size());
        for (qsizetype index = 0; index < result.size(); ++index) {
            result[index] = range[index] != 0.0 ? pressure[index] / range[index] : 0.0;
        }
        return result;
    };
    const Series shortRatio = ratio(shortLength);
    const Series mediumRatio = ratio(mediumLength);
    const Series longRatio = ratio(longLength);
    Series result(candles.size());
    for (qsizetype index = 0; index < result.size(); ++index) {
        result[index] = 100.0 * (
            4.0 * shortRatio[index] + 2.0 * mediumRatio[index] + longRatio[index]) / 7.0;
    }
    return result;
}

std::tuple<Series, Series, Series> dmiSeries(
    const QVector<Candle> &candles,
    qsizetype length
) {
    length = std::max<qsizetype>(1, length);
    Series plusDm(candles.size());
    Series minusDm(candles.size());
    for (qsizetype index = 1; index < candles.size(); ++index) {
        const double upMove = candles[index].high - candles[index - 1].high;
        const double downMove = candles[index - 1].low - candles[index].low;
        plusDm[index] = upMove > downMove && upMove > 0.0 ? upMove : 0.0;
        minusDm[index] = downMove > upMove && downMove > 0.0 ? downMove : 0.0;
    }
    const Series atr = atrSeries(candles, length);
    const Series plusSmoothed = ewmAlphaSeries(plusDm, 1.0 / static_cast<double>(length));
    const Series minusSmoothed = ewmAlphaSeries(minusDm, 1.0 / static_cast<double>(length));
    Series plus(candles.size());
    Series minus(candles.size());
    Series dx(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        plus[index] = atr[index] != 0.0 ? 100.0 * plusSmoothed[index] / atr[index] : 0.0;
        minus[index] = atr[index] != 0.0 ? 100.0 * minusSmoothed[index] / atr[index] : 0.0;
        const double sum = plus[index] + minus[index];
        dx[index] = sum != 0.0
            ? std::abs(plus[index] - minus[index]) / sum * 100.0
            : 0.0;
    }
    return {plus, minus, ewmAlphaSeries(dx, 1.0 / static_cast<double>(length))};
}

Series supertrendSeries(
    const QVector<Candle> &candles,
    qsizetype atrPeriod,
    double multiplier
) {
    if (candles.isEmpty()) {
        return {};
    }
    const Series atr = atrSeries(candles, atrPeriod);
    Series basicUpper(candles.size());
    Series basicLower(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        const double middle = (candles[index].high + candles[index].low) / 2.0;
        basicUpper[index] = middle + multiplier * atr[index];
        basicLower[index] = middle - multiplier * atr[index];
    }
    Series finalUpper = basicUpper;
    Series finalLower = basicLower;
    for (qsizetype index = 1; index < candles.size(); ++index) {
        finalUpper[index] = candles[index - 1].close > finalUpper[index - 1]
            ? basicUpper[index]
            : std::min(basicUpper[index], finalUpper[index - 1]);
        finalLower[index] = candles[index - 1].close < finalLower[index - 1]
            ? basicLower[index]
            : std::max(basicLower[index], finalLower[index - 1]);
    }
    Series line;
    line.reserve(candles.size());
    line.push_back((candles.first().high + candles.first().low) / 2.0);
    for (qsizetype index = 1; index < candles.size(); ++index) {
        if (line[index - 1] == finalUpper[index - 1]) {
            line.push_back(candles[index].close <= finalUpper[index]
                ? finalUpper[index]
                : finalLower[index]);
        } else {
            line.push_back(candles[index].close >= finalLower[index]
                ? finalLower[index]
                : finalUpper[index]);
        }
    }
    Series result(candles.size());
    for (qsizetype index = 0; index < candles.size(); ++index) {
        result[index] = candles[index].close - line[index];
    }
    return result;
}

} // namespace

namespace NativeIndicatorRuntime {

QStringList computedIndicatorKeys() {
    return {
        QStringLiteral("ma"),
        QStringLiteral("donchian"),
        QStringLiteral("psar"),
        QStringLiteral("ema"),
        QStringLiteral("bb"),
        QStringLiteral("bbw"),
        QStringLiteral("rsi"),
        QStringLiteral("volume"),
        QStringLiteral("obv"),
        QStringLiteral("rvol"),
        QStringLiteral("cmf"),
        QStringLiteral("cci"),
        QStringLiteral("roc"),
        QStringLiteral("trix"),
        QStringLiteral("ppo"),
        QStringLiteral("ao"),
        QStringLiteral("atr"),
        QStringLiteral("natr"),
        QStringLiteral("vwap"),
        QStringLiteral("mfi"),
        QStringLiteral("keltner"),
        QStringLiteral("ichimoku"),
        QStringLiteral("kst"),
        QStringLiteral("aroon"),
        QStringLiteral("chop"),
        QStringLiteral("uo"),
        QStringLiteral("adx"),
        QStringLiteral("dmi"),
        QStringLiteral("supertrend"),
        QStringLiteral("stoch_rsi"),
        QStringLiteral("willr"),
        QStringLiteral("macd"),
        QStringLiteral("stochastic"),
    };
}

QStringList unsupportedEnabledIndicatorKeys(const ConfigMap &configs) {
    const QStringList supported = computedIndicatorKeys();
    QStringList unsupported;
    for (auto iterator = configs.cbegin(); iterator != configs.cend(); ++iterator) {
        if (configEnabled(iterator.value()) && !supported.contains(iterator.key())) {
            unsupported.push_back(iterator.key());
        }
    }
    return unsupported;
}

SeriesMap computeConfiguredSeries(const QVector<Candle> &candles, const ConfigMap &configs) {
    SeriesMap output;
    for (auto iterator = configs.cbegin(); iterator != configs.cend(); ++iterator) {
        const QString &key = iterator.key();
        const QJsonObject &config = iterator.value();
        if (!configEnabled(config)) {
            continue;
        }
        if (key == QStringLiteral("donchian")) {
            auto [high, low, middle] = donchianChannels(
                candles, configLength(config, QStringLiteral("length"), 20));
            output.insert(QStringLiteral("donchian_high"), high);
            output.insert(QStringLiteral("donchian_low"), low);
            output.insert(QStringLiteral("donchian"), middle);
        } else if (key == QStringLiteral("psar")) {
            output.insert(QStringLiteral("psar"), parabolicSarSeries(
                candles,
                configDouble(config, QStringLiteral("af"), 0.02),
                configDouble(config, QStringLiteral("max_af"), 0.2)));
        } else if (key == QStringLiteral("ma")) {
            const Series values = closes(candles);
            const qsizetype length = configLength(config, QStringLiteral("length"), 20);
            output.insert(QStringLiteral("ma"), configString(config, QStringLiteral("type"))
                    == QStringLiteral("EMA")
                ? emaSeries(values, length)
                : rollingMeanExact(values, length));
        } else if (key == QStringLiteral("ema")) {
            output.insert(QStringLiteral("ema"), emaSeries(
                closes(candles), configLength(config, QStringLiteral("length"), 20)));
        } else if (key == QStringLiteral("bb")) {
            auto [upper, middle, lower] = bollingerBands(
                closes(candles),
                configLength(config, QStringLiteral("length"), 20),
                configDouble(config, QStringLiteral("std"), 2.0));
            output.insert(QStringLiteral("bb_upper"), upper);
            output.insert(QStringLiteral("bb_mid"), middle);
            output.insert(QStringLiteral("bb_lower"), lower);
        } else if (key == QStringLiteral("bbw")) {
            output.insert(QStringLiteral("bbw"), bollingerBandWidth(
                closes(candles),
                configLength(config, QStringLiteral("length"), 20),
                configDouble(config, QStringLiteral("std"), 2.0)));
        } else if (key == QStringLiteral("keltner")) {
            auto [upper, middle, lower] = keltnerChannels(
                candles,
                configLength(config, QStringLiteral("length"), 20),
                configLength(config, QStringLiteral("atr_length"), 10),
                configDouble(config, QStringLiteral("multiplier"), 2.0));
            output.insert(QStringLiteral("keltner_upper"), upper);
            output.insert(QStringLiteral("keltner_mid"), middle);
            output.insert(QStringLiteral("keltner_lower"), lower);
        } else if (key == QStringLiteral("ichimoku")) {
            auto [tenkan, kijun, spanA, spanB, chikou] = ichimokuCloud(
                candles,
                configLength(config, QStringLiteral("conversion_length"), 9),
                configLength(config, QStringLiteral("base_length"), 26),
                configLength(config, QStringLiteral("span_b_length"), 52),
                configLength(config, QStringLiteral("displacement"), 26));
            Series difference(candles.size());
            for (qsizetype index = 0; index < candles.size(); ++index) {
                difference[index] = tenkan[index] - kijun[index];
            }
            output.insert(QStringLiteral("ichimoku_tenkan"), tenkan);
            output.insert(QStringLiteral("ichimoku_kijun"), kijun);
            output.insert(QStringLiteral("ichimoku_span_a"), spanA);
            output.insert(QStringLiteral("ichimoku_span_b"), spanB);
            output.insert(QStringLiteral("ichimoku_chikou"), chikou);
            output.insert(QStringLiteral("ichimoku"), difference);
        } else if (key == QStringLiteral("rsi")) {
            output.insert(QStringLiteral("rsi"), rsiSeries(
                candles, configLength(config, QStringLiteral("length"), 14)));
        } else if (key == QStringLiteral("stoch_rsi")) {
            auto [k, d] = stochRsiSeries(
                candles,
                configLength(config, QStringLiteral("length"), 14),
                configLength(config, QStringLiteral("smooth_k"), 3),
                configLength(config, QStringLiteral("smooth_d"), 3));
            output.insert(QStringLiteral("stoch_rsi"), k);
            output.insert(QStringLiteral("stoch_rsi_k"), k);
            output.insert(QStringLiteral("stoch_rsi_d"), d);
        } else if (key == QStringLiteral("willr")) {
            output.insert(QStringLiteral("willr"), williamsRSeries(
                candles, configLength(config, QStringLiteral("length"), 14)));
        } else if (key == QStringLiteral("volume")) {
            output.insert(QStringLiteral("volume"), volumes(candles));
        } else if (key == QStringLiteral("obv")) {
            output.insert(QStringLiteral("obv"), obvSeries(candles));
        } else if (key == QStringLiteral("rvol")) {
            output.insert(QStringLiteral("rvol"), relativeVolumeSeries(
                candles, configLength(config, QStringLiteral("length"), 20)));
        } else if (key == QStringLiteral("cmf")) {
            output.insert(QStringLiteral("cmf"), chaikinMoneyFlowSeries(
                candles, configLength(config, QStringLiteral("length"), 20)));
        } else if (key == QStringLiteral("cci")) {
            output.insert(QStringLiteral("cci"), cciSeries(
                candles,
                configLength(config, QStringLiteral("length"), 20),
                configDouble(config, QStringLiteral("constant"), 0.015)));
        } else if (key == QStringLiteral("roc")) {
            output.insert(QStringLiteral("roc"), rocSeries(
                closes(candles), configLength(config, QStringLiteral("length"), 12)));
        } else if (key == QStringLiteral("trix")) {
            output.insert(QStringLiteral("trix"), trixSeries(
                closes(candles), configLength(config, QStringLiteral("length"), 15)));
        } else if (key == QStringLiteral("ppo")) {
            auto [line, signal, histogram] = ppoSeries(
                closes(candles),
                configLength(config, QStringLiteral("fast"), 12),
                configLength(config, QStringLiteral("slow"), 26),
                configLength(config, QStringLiteral("signal"), 9));
            output.insert(QStringLiteral("ppo"), line);
            output.insert(QStringLiteral("ppo_signal"), signal);
            output.insert(QStringLiteral("ppo_hist"), histogram);
        } else if (key == QStringLiteral("ao")) {
            output.insert(QStringLiteral("ao"), awesomeOscillatorSeries(
                candles,
                configLength(config, QStringLiteral("fast"), 5),
                configLength(config, QStringLiteral("slow"), 34)));
        } else if (key == QStringLiteral("kst")) {
            auto [line, signal, histogram] = kstSeries(
                closes(candles),
                configLength(config, QStringLiteral("roc1"), 10),
                configLength(config, QStringLiteral("roc2"), 15),
                configLength(config, QStringLiteral("roc3"), 20),
                configLength(config, QStringLiteral("roc4"), 30),
                configLength(config, QStringLiteral("sma1"), 10),
                configLength(config, QStringLiteral("sma2"), 10),
                configLength(config, QStringLiteral("sma3"), 10),
                configLength(config, QStringLiteral("sma4"), 15),
                configLength(config, QStringLiteral("signal"), 9));
            output.insert(QStringLiteral("kst"), line);
            output.insert(QStringLiteral("kst_signal"), signal);
            output.insert(QStringLiteral("kst_hist"), histogram);
        } else if (key == QStringLiteral("aroon")) {
            auto [up, down, oscillator] = aroonSeries(
                candles, configLength(config, QStringLiteral("length"), 25));
            output.insert(QStringLiteral("aroon_up"), up);
            output.insert(QStringLiteral("aroon_down"), down);
            output.insert(QStringLiteral("aroon"), oscillator);
        } else if (key == QStringLiteral("chop")) {
            output.insert(QStringLiteral("chop"), choppinessIndexSeries(
                candles, configLength(config, QStringLiteral("length"), 14)));
        } else if (key == QStringLiteral("atr")) {
            output.insert(QStringLiteral("atr"), atrSeries(
                candles, configLength(config, QStringLiteral("length"), 14)));
        } else if (key == QStringLiteral("natr")) {
            output.insert(QStringLiteral("natr"), natrSeries(
                candles, configLength(config, QStringLiteral("length"), 14)));
        } else if (key == QStringLiteral("vwap")) {
            output.insert(QStringLiteral("vwap"), vwapSeries(
                candles, configLength(config, QStringLiteral("length"), 20)));
        } else if (key == QStringLiteral("mfi")) {
            output.insert(QStringLiteral("mfi"), mfiSeries(
                candles, configLength(config, QStringLiteral("length"), 14)));
        } else if (key == QStringLiteral("uo")) {
            output.insert(QStringLiteral("uo"), ultimateOscillatorSeries(
                candles,
                configLength(config, QStringLiteral("short"), 7),
                configLength(config, QStringLiteral("medium"), 14),
                configLength(config, QStringLiteral("long"), 28)));
        } else if (key == QStringLiteral("macd")) {
            auto [line, signal, histogram] = macdSeries(
                closes(candles),
                configLength(config, QStringLiteral("fast"), 12),
                configLength(config, QStringLiteral("slow"), 26),
                configLength(config, QStringLiteral("signal"), 9));
            Q_UNUSED(histogram);
            output.insert(QStringLiteral("macd_line"), line);
            output.insert(QStringLiteral("macd_signal"), signal);
        } else if (key == QStringLiteral("adx")) {
            auto [plus, minus, adx] = dmiSeries(
                candles, configLength(config, QStringLiteral("length"), 14));
            Q_UNUSED(plus);
            Q_UNUSED(minus);
            output.insert(QStringLiteral("adx"), adx);
        } else if (key == QStringLiteral("dmi")) {
            auto [plus, minus, adx] = dmiSeries(
                candles, configLength(config, QStringLiteral("length"), 14));
            Q_UNUSED(adx);
            Series difference(candles.size());
            for (qsizetype index = 0; index < candles.size(); ++index) {
                difference[index] = plus[index] - minus[index];
            }
            output.insert(QStringLiteral("dmi_plus"), plus);
            output.insert(QStringLiteral("dmi_minus"), minus);
            output.insert(QStringLiteral("dmi"), difference);
        } else if (key == QStringLiteral("supertrend")) {
            output.insert(QStringLiteral("supertrend"), supertrendSeries(
                candles,
                configLength(config, QStringLiteral("atr_period"), 10),
                configDouble(config, QStringLiteral("multiplier"), 3.0)));
        } else if (key == QStringLiteral("stochastic")) {
            auto [k, d] = stochasticSeries(
                candles,
                configLength(config, QStringLiteral("length"), 14),
                configLength(config, QStringLiteral("smooth_k"), 3),
                configLength(config, QStringLiteral("smooth_d"), 3));
            output.insert(QStringLiteral("stochastic"), k);
            output.insert(QStringLiteral("stochastic_k"), k);
            output.insert(QStringLiteral("stochastic_d"), d);
        }
    }
    return output;
}

} // namespace NativeIndicatorRuntime
