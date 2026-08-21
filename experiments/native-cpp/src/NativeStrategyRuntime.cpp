#include "NativeStrategyRuntime.h"

#include "NativeExchangeConnectors.h"
#include "generated/PythonParityContract.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSet>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <string_view>
#include <tuple>

namespace {

QString textOf(const QJsonValue &value) {
    if (value.isString()) {
        return value.toString().trimmed();
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'g', 15);
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    return {};
}

QString pythonStringOf(const QJsonValue &value) {
    if (value.isString()) {
        return value.toString();
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'g', 15);
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("True") : QStringLiteral("False");
    }
    return {};
}

bool pythonTruthy(const QJsonValue &value) {
    if (value.isUndefined() || value.isNull()) {
        return false;
    }
    if (value.isBool()) {
        return value.toBool();
    }
    if (value.isDouble()) {
        return value.toDouble() != 0.0;
    }
    if (value.isString()) {
        return !value.toString().isEmpty();
    }
    if (value.isArray()) {
        return !value.toArray().isEmpty();
    }
    if (value.isObject()) {
        return !value.toObject().isEmpty();
    }
    return false;
}

QString parityString(std::string_view value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

template <std::size_t N>
QString normalizePythonUiOptionKey(
    const QJsonValue &value,
    const std::array<PythonParityContract::PythonUiOption, N> &options,
    const QString &fallback = {}) {
    const QString raw = textOf(value).trimmed();
    if (raw.isEmpty()) {
        return fallback;
    }
    const QString rawLower = raw.toLower();
    QString rawFirstToken;
    for (const QChar ch : rawLower) {
        if (ch.isLetterOrNumber()) {
            rawFirstToken.append(ch);
        } else if (!rawFirstToken.isEmpty()) {
            break;
        }
    }
    for (const auto &option : options) {
        const QString key = parityString(option.key);
        const QString label = parityString(option.label);
        const QString keyLower = key.toLower();
        const QString labelLower = label.toLower();
        if (raw.compare(key, Qt::CaseInsensitive) == 0
            || raw.compare(label, Qt::CaseInsensitive) == 0
            || keyLower.startsWith(rawLower)
            || labelLower.startsWith(rawLower)
            || labelLower.contains(rawLower)
            || (!rawFirstToken.isEmpty()
                && rawFirstToken != rawLower
                && (keyLower.startsWith(rawFirstToken)
                    || labelLower.startsWith(rawFirstToken)
                    || labelLower.contains(rawFirstToken)))) {
            return key;
        }
    }
    return fallback;
}

template <std::size_t N>
QString normalizePythonStringOption(
    const QJsonValue &value,
    const std::array<std::string_view, N> &options,
    const QString &fallback = {}) {
    const QString raw = textOf(value).trimmed();
    if (raw.isEmpty()) {
        return fallback;
    }
    const QString rawLower = raw.toLower();
    QString rawFirstToken;
    for (const QChar ch : rawLower) {
        if (ch.isLetterOrNumber()) {
            rawFirstToken.append(ch);
        } else if (!rawFirstToken.isEmpty()) {
            break;
        }
    }
    for (std::string_view optionView : options) {
        const QString option = parityString(optionView);
        const QString optionLower = option.toLower();
        if (raw.compare(option, Qt::CaseInsensitive) == 0
            || optionLower.startsWith(rawLower)
            || optionLower.contains(rawLower)
            || (!rawFirstToken.isEmpty()
                && rawFirstToken != rawLower
                && (optionLower.startsWith(rawFirstToken)
                    || optionLower.contains(rawFirstToken)))) {
            return option;
        }
    }
    return fallback;
}

template <std::size_t N>
QString normalizePythonConfigChoice(
    const QJsonValue &value,
    const std::array<PythonParityContract::PythonConfigChoice, N> &choices,
    const QString &fallback = {}) {
    const QString raw = textOf(value).trimmed();
    if (raw.isEmpty()) {
        return fallback;
    }
    for (const auto &choice : choices) {
        const QString key = parityString(choice.key);
        if (raw.compare(key, Qt::CaseInsensitive) == 0) {
            return parityString(choice.value);
        }
    }
    return fallback;
}

template <std::size_t N>
QString pythonUiOptionKeyAt(
    const std::array<PythonParityContract::PythonUiOption, N> &options,
    std::size_t index,
    const QString &fallback = {}) {
    if (index < options.size()) {
        return parityString(options.at(index).key);
    }
    return fallback;
}

template <std::size_t N>
QString pythonStringOptionAt(
    const std::array<std::string_view, N> &options,
    std::size_t index,
    const QString &fallback = {}) {
    if (index < options.size()) {
        return parityString(options.at(index));
    }
    return fallback;
}

QString normalizeSignalLogic(const QJsonValue &value) {
    return normalizePythonUiOptionKey(value, PythonParityContract::kPythonSignalLogicOptions);
}

QString normalizeStrategySignalLogic(const QJsonValue &value) {
    const QString raw = pythonStringOf(value).toUpper();
    if (raw == QStringLiteral("AND") || raw == QStringLiteral("OR")
        || raw == QStringLiteral("SEPARATE")) {
        return raw;
    }
    return {};
}

QString normalizeRuntimeSide(const QJsonValue &value) {
    const QString raw = pythonStringOf(value).toUpper();
    if (raw.isEmpty()) {
        return {};
    }
    for (const auto &option : PythonParityContract::kPythonSideOptions) {
        if (raw == parityString(option.key)) {
            return raw;
        }
    }
    return {};
}

QString normalizeStopLossMode(const QJsonValue &value) {
    return normalizePythonConfigChoice(
        value,
        PythonParityContract::kPythonStopLossModeConfigChoices,
        QStringLiteral("usdt"));
}

QString normalizeStopLossScope(const QJsonValue &value) {
    return normalizePythonConfigChoice(
        value,
        PythonParityContract::kPythonStopLossScopeConfigChoices,
        QStringLiteral("per_trade"));
}

template <std::size_t N>
QString normalizeStrategyStopLossChoice(
    const QJsonValue &value,
    const std::array<PythonParityContract::PythonConfigChoice, N> &choices,
    const QString &fallback) {
    const QString raw = pythonStringOf(value);
    const QString lower = raw.isEmpty() ? QStringLiteral("usdt") : raw.toLower();
    for (const auto &choice : choices) {
        if (lower == parityString(choice.key).toLower()) {
            return parityString(choice.value);
        }
    }
    return fallback;
}

QString normalizeStrategyStopLossMode(const QJsonValue &value) {
    return normalizeStrategyStopLossChoice(
        value,
        PythonParityContract::kPythonStopLossModeConfigChoices,
        QStringLiteral("usdt"));
}

QString normalizeStrategyStopLossScope(const QJsonValue &value) {
    return normalizeStrategyStopLossChoice(
        value,
        PythonParityContract::kPythonStopLossScopeConfigChoices,
        QStringLiteral("per_trade"));
}

std::optional<double> numberOf(const QJsonValue &value) {
    if (value.isDouble()) {
        return value.toDouble();
    }
    bool ok = false;
    const double parsed = textOf(value).toDouble(&ok);
    if (ok) {
        return parsed;
    }
    return std::nullopt;
}

std::optional<double> pythonNumberOf(const QJsonValue &value) {
    if (value.isBool()) {
        return value.toBool() ? 1.0 : 0.0;
    }
    return numberOf(value);
}

std::optional<qint64> intOf(const QJsonValue &value) {
    if (value.isDouble()) {
        return static_cast<qint64>(value.toDouble());
    }
    bool ok = false;
    const qint64 parsed = textOf(value).toLongLong(&ok);
    if (ok) {
        return parsed;
    }
    return std::nullopt;
}

std::optional<qint64> pythonIntOf(const QJsonValue &value) {
    if (value.isBool()) {
        return value.toBool() ? 1 : 0;
    }
    return intOf(value);
}

void appendUnique(QStringList &items, const QStringList &values) {
    for (const QString &value : values) {
        if (!items.contains(value)) {
            items.append(value);
        }
    }
}

bool enabled(const NativeStrategyRuntime::StrategySignalInput &input, const QString &key) {
    return input.rules.value(key).enabled;
}

NativeStrategyRuntime::IndicatorRule rule(
    const NativeStrategyRuntime::StrategySignalInput &input,
    const QString &key) {
    return input.rules.value(key);
}

std::optional<std::tuple<double, double, double>> indicatorValues(
    const NativeStrategyRuntime::StrategySignalInput &input,
    const QString &key) {
    const QVector<double> values = input.indicators.value(key);
    QVector<double> clean;
    for (double value : values) {
        if (!std::isnan(value)) {
            clean.append(value);
        }
    }
    if (clean.isEmpty()) {
        return std::nullopt;
    }
    const double live = clean.last();
    const double prev = clean.size() >= 2 ? clean.at(clean.size() - 2) : live;
    const double selected = input.useLiveValues ? live : prev;
    return std::make_tuple(prev, live, selected);
}

std::optional<double> valueAt(
    const NativeStrategyRuntime::StrategySignalInput &input,
    const QString &key,
    int index) {
    const QVector<double> values = input.indicators.value(key);
    if (index < 0 || index >= values.size()) {
        return std::nullopt;
    }
    const double value = values.at(index);
    // Match pandas Series.dropna(): NaN is missing, while +/-inf remains a
    // value and must flow through the same comparisons and descriptions.
    return !std::isnan(value) ? std::optional<double>(value) : std::nullopt;
}

QString fixed(double value, int decimals) {
    return QString::number(value, 'f', decimals);
}

int decimalsFor(const QString &pattern) {
    if (pattern.contains(QStringLiteral(".8"))) {
        return 8;
    }
    if (pattern.contains(QStringLiteral(".4"))) {
        return 4;
    }
    return 2;
}

void addAction(
    const QString &key,
    const QString &side,
    const QString &description,
    QString &signal,
    QStringList &descriptions,
    QStringList &sources,
    QJsonObject &actions) {
    actions.insert(key, side.toLower());
    descriptions.append(description);
    sources.append(key);
    if (signal.isEmpty()) {
        signal = side;
    }
}

enum class Compare {
    BuyLeSellGe,
    BuyGeSellLe,
    BuyLeSellGeDefaults,
    BuyLeSellGePythonDefaults,
    BuyGeSellLeDefaults,
};

void thresholdExisting(
    const NativeStrategyRuntime::StrategySignalInput &input,
    const QString &key,
    const QString &label,
    const QString &pattern,
    double value,
    Compare compare,
    std::optional<double> defaultBuy,
    std::optional<double> defaultSell,
    bool buyAllowed,
    bool sellAllowed,
    QString &signal,
    QStringList &descriptions,
    QStringList &sources,
    QJsonObject &actions) {
    const auto cfg = rule(input, key);
    const bool pythonFalseyDefaults = compare == Compare::BuyLeSellGePythonDefaults;
    const std::optional<double> buy =
        cfg.buyValue.has_value() && (!pythonFalseyDefaults || *cfg.buyValue != 0.0)
            ? cfg.buyValue
            : defaultBuy;
    const std::optional<double> sell =
        cfg.sellValue.has_value() && (!pythonFalseyDefaults || *cfg.sellValue != 0.0)
            ? cfg.sellValue
            : defaultSell;
    const int decimals = decimalsFor(pattern);
    const bool buyGe = compare == Compare::BuyGeSellLe || compare == Compare::BuyGeSellLeDefaults;
    if (buyGe) {
        if (buy.has_value() && buyAllowed && value >= *buy) {
            addAction(key, QStringLiteral("BUY"), QStringLiteral("%1 >= %2 -> BUY").arg(label, fixed(*buy, decimals)),
                      signal, descriptions, sources, actions);
        } else if (sell.has_value() && sellAllowed && value <= *sell) {
            addAction(key, QStringLiteral("SELL"), QStringLiteral("%1 <= %2 -> SELL").arg(label, fixed(*sell, decimals)),
                      signal, descriptions, sources, actions);
        }
    } else if (buy.has_value() && buyAllowed && value <= *buy) {
        addAction(key, QStringLiteral("BUY"), QStringLiteral("%1 <= %2 -> BUY").arg(label, fixed(*buy, decimals)),
                  signal, descriptions, sources, actions);
    } else if (sell.has_value() && sellAllowed && value >= *sell) {
        addAction(key, QStringLiteral("SELL"), QStringLiteral("%1 >= %2 -> SELL").arg(label, fixed(*sell, decimals)),
                  signal, descriptions, sources, actions);
    }
}

void threshold(
    const NativeStrategyRuntime::StrategySignalInput &input,
    const QString &key,
    const QString &label,
    const QString &pattern,
    Compare compare,
    std::optional<double> defaultBuy,
    std::optional<double> defaultSell,
    bool buyAllowed,
    bool sellAllowed,
    QString &signal,
    QStringList &descriptions,
    QStringList &sources,
    QJsonObject &actions) {
    if (!enabled(input, key)) {
        return;
    }
    const auto values = indicatorValues(input, key);
    if (!values.has_value()) {
        return;
    }
    const double value = std::get<2>(*values);
    if (!std::isfinite(value)) {
        descriptions.append(QStringLiteral("%1=NaN/inf skipped").arg(label));
        return;
    }
    descriptions.append(QStringLiteral("%1=%2").arg(label, fixed(value, decimalsFor(pattern))));
    thresholdExisting(input, key, label, pattern, value, compare, defaultBuy, defaultSell,
                      buyAllowed, sellAllowed, signal, descriptions, sources, actions);
}

QString normalizeLoop(const QJsonValue &value) {
    QString cleaned;
    for (const QChar ch : textOf(value).toLower()) {
        if (!ch.isSpace()) {
            cleaned.append(ch);
        }
    }
    if (cleaned.isEmpty()) {
        return {};
    }
    int idx = 0;
    while (idx < cleaned.size() && cleaned.at(idx).isDigit()) {
        ++idx;
    }
    if (idx == 0) {
        return {};
    }
    const QString suffix = cleaned.mid(idx);
    if (suffix.isEmpty() || suffix == QStringLiteral("s") || suffix == QStringLiteral("m")
        || suffix == QStringLiteral("h") || suffix == QStringLiteral("d") || suffix == QStringLiteral("w")) {
        return cleaned;
    }
    return {};
}

QString normalizePositionPctUnits(const QJsonValue &value) {
    return normalizePythonConfigChoice(
        value,
        PythonParityContract::kPythonPositionPctUnitsConfigChoices);
}

QString canonicalSide(const QJsonValue &value) {
    return normalizePythonUiOptionKey(
        value,
        PythonParityContract::kPythonSideOptions,
        textOf(value).trimmed().isEmpty()
            ? QString()
            : pythonUiOptionKeyAt(PythonParityContract::kPythonSideOptions, 2));
}

QString normalizeAccountMode(const QJsonValue &value) {
    return normalizePythonStringOption(
        value,
        PythonParityContract::kPythonAccountModeOptions,
        textOf(value).trimmed().isEmpty()
            ? QString()
            : pythonStringOptionAt(PythonParityContract::kPythonAccountModeOptions, 0));
}

QString normalizeAssetsMode(const QJsonValue &value) {
    return normalizePythonUiOptionKey(
        value,
        PythonParityContract::kPythonAssetsModeOptions,
        textOf(value).trimmed().isEmpty()
            ? QString()
            : pythonUiOptionKeyAt(PythonParityContract::kPythonAssetsModeOptions, 0));
}

QJsonObject normalizeStopLoss(const QJsonObject &input) {
    const QString mode = normalizeStrategyStopLossMode(input.value(QStringLiteral("mode")));
    const QString scope = normalizeStrategyStopLossScope(input.value(QStringLiteral("scope")));
    return {
        {QStringLiteral("enabled"), NativeStrategyRuntime::coerceStrategyBool(input.value(QStringLiteral("enabled")))},
        {QStringLiteral("mode"), mode},
        {QStringLiteral("scope"), scope},
        {QStringLiteral("usdt"), std::max(0.0, pythonNumberOf(input.value(QStringLiteral("usdt"))).value_or(0.0))},
        {QStringLiteral("percent"), std::max(0.0, pythonNumberOf(input.value(QStringLiteral("percent"))).value_or(0.0))},
    };
}

QJsonObject pythonRiskDefaults() {
    static const QJsonObject defaults = [] {
        const QByteArray encoded(
            PythonParityContract::kPythonRiskDefaultsJson.data(),
            static_cast<int>(PythonParityContract::kPythonRiskDefaultsJson.size()));
        const QJsonDocument document = QJsonDocument::fromJson(encoded);
        return document.isObject() ? document.object() : QJsonObject{};
    }();
    return defaults;
}

QString formatAmount(double value) {
    if (std::abs(value - std::round(value)) < 0.0000001) {
        return QString::number(static_cast<qint64>(std::round(value)));
    }
    QString text = QString::number(value, 'f', 8);
    while (text.contains(QLatin1Char('.')) && text.endsWith(QLatin1Char('0'))) {
        text.chop(1);
    }
    if (text.endsWith(QLatin1Char('.'))) {
        text.chop(1);
    }
    return text;
}

QString normalizeBacktestInterval(const QJsonValue &value) {
    const QString raw = textOf(value).trimmed();
    if (raw.isEmpty()) {
        return {};
    }
    int index = 0;
    while (index < raw.size() && raw.at(index).isDigit()) {
        ++index;
    }
    if (index == 0) {
        return raw.toLower();
    }
    if (index < raw.size() && raw.at(index) == QLatin1Char('.')) {
        ++index;
        const int fractionStart = index;
        while (index < raw.size() && raw.at(index).isDigit()) {
            ++index;
        }
        if (index == fractionStart) {
            return raw.toLower();
        }
    }
    const QString amountRaw = raw.left(index);
    const QString unitRaw = raw.mid(index).trimmed();
    for (const QChar ch : unitRaw) {
        if (!ch.isLetter()) {
            return raw.toLower();
        }
    }
    bool amountIsInteger = !amountRaw.isEmpty();
    for (const QChar ch : amountRaw) {
        if (!ch.isDigit()) {
            amountIsInteger = false;
            break;
        }
    }
    if (unitRaw == QStringLiteral("M") && amountIsInteger) {
        QString normalizedAmount = amountRaw;
        while (normalizedAmount.size() > 1 && normalizedAmount.startsWith(QLatin1Char('0'))) {
            normalizedAmount.remove(0, 1);
        }
        return normalizedAmount + QStringLiteral("mo");
    }
    bool ok = false;
    const double amount = amountRaw.toDouble(&ok);
    if (!ok) {
        return raw.toLower();
    }
    if (QStringList{QStringLiteral("mo"), QStringLiteral("mon"), QStringLiteral("mons"), QStringLiteral("month"), QStringLiteral("months")}.contains(unitRaw.toLower())) {
        return QStringLiteral("%1mo").arg(formatAmount(amount));
    }
    QString unit = unitRaw.toLower();
    if (unit.isEmpty() || QStringList{QStringLiteral("m"), QStringLiteral("min"), QStringLiteral("mins"), QStringLiteral("minute"), QStringLiteral("minutes")}.contains(unit)) {
        unit = QStringLiteral("m");
    } else if (QStringList{QStringLiteral("s"), QStringLiteral("sec"), QStringLiteral("secs"), QStringLiteral("second"), QStringLiteral("seconds")}.contains(unit)) {
        unit = QStringLiteral("s");
    } else if (QStringList{QStringLiteral("h"), QStringLiteral("hr"), QStringLiteral("hrs"), QStringLiteral("hour"), QStringLiteral("hours")}.contains(unit)) {
        unit = QStringLiteral("h");
    } else if (QStringList{QStringLiteral("d"), QStringLiteral("day"), QStringLiteral("days")}.contains(unit)) {
        unit = QStringLiteral("d");
    } else if (QStringList{QStringLiteral("w"), QStringLiteral("wk"), QStringLiteral("wks"), QStringLiteral("week"), QStringLiteral("weeks")}.contains(unit)) {
        unit = QStringLiteral("w");
    } else if (QStringList{QStringLiteral("y"), QStringLiteral("yr"), QStringLiteral("yrs"), QStringLiteral("year"), QStringLiteral("years")}.contains(unit)) {
        unit = QStringLiteral("y");
    } else if (!unit.isEmpty()) {
        return raw.toLower();
    }
    const QMap<double, QString> canonical{
        {30.0, QStringLiteral("30s")},
        {45.0, QStringLiteral("45s")},
        {60.0, QStringLiteral("1m")},
        {180.0, QStringLiteral("3m")},
        {300.0, QStringLiteral("5m")},
        {600.0, QStringLiteral("10m")},
        {900.0, QStringLiteral("15m")},
        {1200.0, QStringLiteral("20m")},
        {1800.0, QStringLiteral("30m")},
        {2700.0, QStringLiteral("45m")},
        {3600.0, QStringLiteral("1h")},
        {7200.0, QStringLiteral("2h")},
        {10800.0, QStringLiteral("3h")},
        {14400.0, QStringLiteral("4h")},
        {18000.0, QStringLiteral("5h")},
        {21600.0, QStringLiteral("6h")},
        {25200.0, QStringLiteral("7h")},
        {28800.0, QStringLiteral("8h")},
        {32400.0, QStringLiteral("9h")},
        {36000.0, QStringLiteral("10h")},
        {39600.0, QStringLiteral("11h")},
        {43200.0, QStringLiteral("12h")},
        {86400.0, QStringLiteral("1d")},
        {172800.0, QStringLiteral("2d")},
        {259200.0, QStringLiteral("3d")},
        {345600.0, QStringLiteral("4d")},
        {432000.0, QStringLiteral("5d")},
        {518400.0, QStringLiteral("6d")},
        {604800.0, QStringLiteral("1w")},
        {1209600.0, QStringLiteral("2w")},
        {1814400.0, QStringLiteral("3w")},
    };
    double seconds = -1.0;
    if (unit == QStringLiteral("s")) seconds = amount;
    if (unit == QStringLiteral("m")) seconds = amount * 60.0;
    if (unit == QStringLiteral("h")) seconds = amount * 3600.0;
    if (unit == QStringLiteral("d")) seconds = amount * 86400.0;
    if (unit == QStringLiteral("w")) seconds = amount * 604800.0;
    if (canonical.contains(seconds)) {
        return canonical.value(seconds);
    }
    return QStringLiteral("%1%2").arg(formatAmount(amount), unit);
}

double intervalSeconds(const QString &interval) {
    const auto parseInteger = [](const QString &text, double multiplier) -> std::optional<double> {
        bool ok = false;
        const qint64 amount = text.toLongLong(&ok);
        if (!ok) {
            return std::nullopt;
        }
        return static_cast<double>(amount) * multiplier;
    };
    const auto parseSuffix = [&](const QString &suffix, double multiplier) -> std::optional<double> {
        if (!interval.endsWith(suffix)) {
            return std::nullopt;
        }
        return parseInteger(interval.left(interval.size() - suffix.size()), multiplier);
    };
    for (const auto &candidate : {
             std::pair<QString, double>{QStringLiteral("s"), 1.0},
             std::pair<QString, double>{QStringLiteral("m"), 60.0},
             std::pair<QString, double>{QStringLiteral("h"), 3600.0},
             std::pair<QString, double>{QStringLiteral("d"), 86400.0},
             std::pair<QString, double>{QStringLiteral("w"), 7.0 * 86400.0},
         }) {
        if (const auto value = parseSuffix(candidate.first, candidate.second); value.has_value()) {
            return *value;
        }
        if (interval.endsWith(candidate.first)) {
            return 60.0;
        }
    }
    if (const auto value = parseInteger(interval, 1.0); value.has_value()) {
        return *value;
    }
    return 60.0;
}

QString displayValue(const QJsonValue &value) {
    if (value.isString()) {
        return value.toString();
    }
    if (value.isDouble()) {
        return formatAmount(value.toDouble());
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    return QString::fromUtf8(QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact));
}

QString formatResultNumber(const QJsonValue &value, const QString &suffix) {
    const auto parsed = numberOf(value);
    if (!parsed.has_value() || !std::isfinite(*parsed)) {
        return {};
    }
    QString text = QString::number(*parsed, 'f', 2);
    while (text.contains(QLatin1Char('.')) && text.endsWith(QLatin1Char('0'))) {
        text.chop(1);
    }
    if (text.endsWith(QLatin1Char('.'))) {
        text.chop(1);
    }
    return text + suffix;
}

QJsonValue integerValue(qint64 value) {
    return QJsonValue(static_cast<int>(value));
}

} // namespace

namespace NativeStrategyRuntime {

double pythonIndicatorIntervalSeconds(const QString &interval) {
    const QString text = interval.isEmpty() ? QStringLiteral("1m") : interval;
    const auto parseInteger = [&](const QString &suffix, double multiplier) -> std::optional<double> {
        if (!text.endsWith(suffix)) {
            return std::nullopt;
        }
        bool ok = false;
        const qint64 amount = text.left(text.size() - suffix.size()).toLongLong(&ok);
        if (!ok) {
            return std::nullopt;
        }
        return static_cast<double>(amount) * multiplier;
    };
    for (const auto &candidate : {
             std::pair<QString, double>{QStringLiteral("s"), 1.0},
             std::pair<QString, double>{QStringLiteral("m"), 60.0},
             std::pair<QString, double>{QStringLiteral("h"), 3600.0},
             std::pair<QString, double>{QStringLiteral("d"), 86400.0},
         }) {
        if (const auto value = parseInteger(candidate.first, candidate.second); value.has_value()) {
            return *value;
        }
        if (text.endsWith(candidate.first)) {
            return 60.0;
        }
    }
    return 60.0;
}

double pythonLoopIntervalSeconds(const QString &interval) {
    return std::max(1.0, intervalSeconds(interval));
}

QString canonicalizeBacktestInterval(const QJsonValue &value) {
    return normalizeBacktestInterval(value);
}

QStringList strategyRuntimeBoundaries() {
    return {
        QStringLiteral("indicator output key expansion"),
        QStringLiteral("live-vs-closed candle signal indexing"),
        QStringLiteral("side-gated threshold actions"),
        QStringLiteral("context-only indicator descriptions"),
        QStringLiteral("runtime/backtest strategy control normalization"),
        QStringLiteral("override provenance preservation"),
        QStringLiteral("worker lifecycle and Python-service execution boundary"),
    };
}

bool coerceStrategyBool(const QJsonValue &value, bool defaultValue) {
    if (value.isUndefined() || value.isNull()) {
        return defaultValue;
    }
    if (value.isBool()) {
        return value.toBool();
    }
    if (value.isDouble()) {
        const double number = value.toDouble();
        return !std::isfinite(number) || std::trunc(number) != 0.0;
    }
    if (value.isArray()) {
        return !value.toArray().isEmpty();
    }
    if (value.isObject()) {
        return !value.toObject().isEmpty();
    }
    const QString lowered = value.toString().trimmed().toLower();
    if (lowered.isEmpty()) {
        return defaultValue;
    }
    if (QStringList{QStringLiteral("0"), QStringLiteral("false"), QStringLiteral("no"), QStringLiteral("off")}.contains(lowered)) {
        return false;
    }
    if (QStringList{QStringLiteral("1"), QStringLiteral("true"), QStringLiteral("yes"), QStringLiteral("on")}.contains(lowered)) {
        return true;
    }
    return defaultValue;
}

QStringList indicatorOutputKeysFromConfig(const QJsonObject &indicators) {
    QStringList keys;
    for (auto it = indicators.begin(); it != indicators.end(); ++it) {
        if (!coerceStrategyBool(it.value().toObject().value(QStringLiteral("enabled")))) {
            continue;
        }
        const QString key = it.key();
        const auto definition = std::find_if(
            PythonParityContract::kPythonIndicatorCatalog.cbegin(),
            PythonParityContract::kPythonIndicatorCatalog.cend(),
            [&key](const PythonParityContract::PythonIndicator &candidate) {
                return parityString(candidate.key) == key;
            });
        if (definition == PythonParityContract::kPythonIndicatorCatalog.cend()) {
            continue;
        }
        appendUnique(
            keys,
            parityString(definition->runtimeOutputKeysCsv).split(
                QLatin1Char(','), Qt::SkipEmptyParts));
    }
    return keys;
}

QJsonObject buildSignalDecision(const StrategySignalInput &input) {
    const int minBars = input.useLiveValues ? 2 : 3;
    const int fromEnd = input.useLiveValues ? 1 : 2;
    if (input.closes.size() < minBars) {
        return {
            {QStringLiteral("signal"), QJsonValue()},
            {QStringLiteral("description"), QStringLiteral("no data")},
            {QStringLiteral("trigger_sources"), QJsonArray{}},
            {QStringLiteral("trigger_actions"), QJsonObject{}},
            {QStringLiteral("min_bars"), minBars},
            {QStringLiteral("signal_index_from_end"), fromEnd},
        };
    }
    const int signalIndex = input.closes.size() - fromEnd;
    const int prevIndex = signalIndex - 1;
    const double sigClose = input.closes.at(signalIndex);
    const double prevClose = input.closes.at(prevIndex);
    if (!std::isfinite(sigClose) || !std::isfinite(prevClose)) {
        return {
            {QStringLiteral("signal"), QJsonValue()},
            {QStringLiteral("description"), QStringLiteral("no data")},
            {QStringLiteral("trigger_price"), QJsonValue()},
            {QStringLiteral("trigger_sources"), QJsonArray{}},
            {QStringLiteral("trigger_actions"), QJsonObject{}},
            {QStringLiteral("min_bars"), minBars},
            {QStringLiteral("signal_index_from_end"), fromEnd},
        };
    }
    QString signal;
    QStringList descriptions;
    QStringList sources;
    QJsonObject actions;
    const QString side = input.side.trimmed().toUpper();
    const bool buyAllowed = side == QStringLiteral("BUY") || side == QStringLiteral("BOTH");
    const bool sellAllowed = side == QStringLiteral("SELL") || side == QStringLiteral("BOTH");

    if (enabled(input, QStringLiteral("rsi"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("rsi"))) {
            const double value = std::get<2>(*values);
            if (std::isfinite(value)) {
                descriptions.append(QStringLiteral("RSI=%1").arg(fixed(value, 2)));
                const auto cfg = rule(input, QStringLiteral("rsi"));
                // Python's RSI path uses ``float(value or default)``; zero is
                // therefore a request for the Python default, not a threshold.
                const double buy = cfg.buyValue.has_value() && *cfg.buyValue != 0.0
                    ? *cfg.buyValue
                    : 30.0;
                const double sell = cfg.sellValue.has_value() && *cfg.sellValue != 0.0
                    ? *cfg.sellValue
                    : 70.0;
                if (buyAllowed && value <= buy) {
                    addAction(QStringLiteral("rsi"), QStringLiteral("BUY"), QStringLiteral("RSI <= %1 -> BUY").arg(fixed(buy, 2)), signal, descriptions, sources, actions);
                } else if (sellAllowed && value >= sell) {
                    addAction(QStringLiteral("rsi"), QStringLiteral("SELL"), QStringLiteral("RSI >= %1 -> SELL").arg(fixed(sell, 2)), signal, descriptions, sources, actions);
                }
            } else {
                descriptions.append(QStringLiteral("RSI=NaN/inf skipped"));
            }
        }
    }
    if (enabled(input, QStringLiteral("stoch_rsi"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("stoch_rsi_k"))) {
            const double previous = std::get<0>(*values);
            const double live = std::get<1>(*values);
            const double selected = std::get<2>(*values);
            descriptions.append(
                QStringLiteral("StochRSI %K=%1 (prev=%2, live=%3)")
                    .arg(fixed(selected, 2), fixed(previous, 2), fixed(live, 2)));
            thresholdExisting(
                input,
                QStringLiteral("stoch_rsi"),
                QStringLiteral("StochRSI %K"),
                QStringLiteral("{:.2}"),
                selected,
                Compare::BuyLeSellGeDefaults,
                20.0,
                80.0,
                buyAllowed,
                sellAllowed,
                signal,
                descriptions,
                sources,
                actions);
        } else if (input.indicators.contains(QStringLiteral("stoch_rsi_k"))) {
            descriptions.append(QStringLiteral("StochRSI error:ValueError('indicator series empty')"));
        }
    }
    if (enabled(input, QStringLiteral("willr"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("willr"))) {
            const double previous = std::get<0>(*values);
            const double live = std::get<1>(*values);
            const double selected = std::get<2>(*values);
            descriptions.append(
                QStringLiteral("Williams %R(prev=%1, live=%2) -> using %3")
                    .arg(fixed(previous, 2), fixed(live, 2), fixed(selected, 2)));
            const auto cfg = rule(input, QStringLiteral("willr"));
            const double buyUpper = std::clamp(cfg.buyValue.value_or(-80.0), -100.0, 0.0);
            const double sellLower = std::clamp(cfg.sellValue.value_or(-20.0), -100.0, 0.0);
            if (buyAllowed && selected >= -100.0 && selected <= buyUpper) {
                addAction(
                    QStringLiteral("willr"),
                    QStringLiteral("BUY"),
                    QStringLiteral("Williams %R in [-100.00, %1] -> BUY").arg(fixed(buyUpper, 2)),
                    signal,
                    descriptions,
                    sources,
                    actions);
            } else if (sellAllowed && selected >= sellLower && selected <= 0.0) {
                addAction(
                    QStringLiteral("willr"),
                    QStringLiteral("SELL"),
                    QStringLiteral("Williams %R in [%1, 0.00] -> SELL").arg(fixed(sellLower, 2)),
                    signal,
                    descriptions,
                    sources,
                    actions);
            }
        } else if (input.indicators.contains(QStringLiteral("willr"))) {
            descriptions.append(QStringLiteral("Williams %R error:ValueError('indicator series empty')"));
        }
    }
    threshold(input, QStringLiteral("natr"), QStringLiteral("NATR"), QStringLiteral("{:.4}"), Compare::BuyGeSellLe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("rvol"), QStringLiteral("RVOL"), QStringLiteral("{:.4}"), Compare::BuyGeSellLe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("cci"), QStringLiteral("CCI"), QStringLiteral("{:.2}"), Compare::BuyLeSellGeDefaults, -100.0, 100.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("bbw"), QStringLiteral("BBW"), QStringLiteral("{:.4}"), Compare::BuyGeSellLe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("roc"), QStringLiteral("ROC"), QStringLiteral("{:.2}"), Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("trix"), QStringLiteral("TRIX"), QStringLiteral("{:.4}"), Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("ao"), QStringLiteral("AO"), QStringLiteral("{:.4}"), Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("mfi"), QStringLiteral("MFI"), QStringLiteral("{:.2}"), Compare::BuyLeSellGePythonDefaults, 20.0, 80.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("chop"), QStringLiteral("CHOP"), QStringLiteral("{:.4}"), Compare::BuyLeSellGe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);

    if (enabled(input, QStringLiteral("ppo"))) {
        const auto histValues = indicatorValues(input, QStringLiteral("ppo_hist"));
        if (histValues.has_value()) {
            const auto lineValues = indicatorValues(input, QStringLiteral("ppo"));
            const auto signalValues = indicatorValues(input, QStringLiteral("ppo_signal"));
            if (!lineValues.has_value() || !signalValues.has_value()) {
                descriptions.append(QStringLiteral("PPO error:ValueError('indicator series missing')"));
            } else {
                const double hist = std::get<2>(*histValues);
                const double line = std::get<2>(*lineValues);
                const double ppoSignal = std::get<2>(*signalValues);
                if (std::isfinite(hist)) {
                    descriptions.append(QStringLiteral("PPO=%1,PPO_signal=%2,hist=%3").arg(fixed(line, 4), fixed(ppoSignal, 4), fixed(hist, 4)));
                    thresholdExisting(input, QStringLiteral("ppo"), QStringLiteral("PPO hist"), QStringLiteral("{:.4}"), hist, Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
                } else {
                    descriptions.append(QStringLiteral("PPO=NaN/inf skipped"));
                }
            }
        }
    }
    if (enabled(input, QStringLiteral("kst"))) {
        const auto spreadValues = indicatorValues(input, QStringLiteral("kst_hist"));
        if (spreadValues.has_value()) {
            const auto lineValues = indicatorValues(input, QStringLiteral("kst"));
            const auto signalValues = indicatorValues(input, QStringLiteral("kst_signal"));
            if (!lineValues.has_value() || !signalValues.has_value()) {
                descriptions.append(QStringLiteral("KST error:ValueError('indicator series missing')"));
            } else {
                const double spread = std::get<2>(*spreadValues);
                const double line = std::get<2>(*lineValues);
                const double kstSignal = std::get<2>(*signalValues);
                if (std::isfinite(spread)) {
                    descriptions.append(QStringLiteral("KST=%1,KST_signal=%2,spread=%3").arg(fixed(line, 4), fixed(kstSignal, 4), fixed(spread, 4)));
                    thresholdExisting(input, QStringLiteral("kst"), QStringLiteral("KST spread"), QStringLiteral("{:.4}"), spread, Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
                } else {
                    descriptions.append(QStringLiteral("KST=NaN/inf skipped"));
                }
            }
        }
    }
    if (enabled(input, QStringLiteral("aroon"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("aroon"))) {
            const auto upValues = indicatorValues(input, QStringLiteral("aroon_up"));
            const auto downValues = indicatorValues(input, QStringLiteral("aroon_down"));
            if (!upValues.has_value() || !downValues.has_value()) {
                descriptions.append(QStringLiteral("Aroon error:ValueError('indicator series missing')"));
            } else {
                const double value = std::get<2>(*values);
                const double up = std::get<2>(*upValues);
                const double down = std::get<2>(*downValues);
                if (std::isfinite(value)) {
                    descriptions.append(QStringLiteral("Aroon=%1 (up=%2, down=%3)").arg(fixed(value, 2), fixed(up, 2), fixed(down, 2)));
                    thresholdExisting(input, QStringLiteral("aroon"), QStringLiteral("Aroon"), QStringLiteral("{:.2}"), value, Compare::BuyGeSellLeDefaults, 50.0, -50.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
                } else {
                    descriptions.append(QStringLiteral("Aroon=NaN/inf skipped"));
                }
            }
        }
    }
    if (enabled(input, QStringLiteral("atr"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("atr"))) {
            const double value = std::get<2>(*values);
            descriptions.append(std::isfinite(value)
                                    ? QStringLiteral("ATR=%1").arg(fixed(value, 8))
                                    : QStringLiteral("ATR=NaN/inf skipped"));
        }
    }
    if (enabled(input, QStringLiteral("vwap"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("vwap"))) {
            const double value = std::get<2>(*values);
            if (std::isfinite(value)) {
                descriptions.append(QStringLiteral("VWAP=%1 (prev=%2, live=%3, close %4)")
                                        .arg(fixed(value, 8), fixed(std::get<0>(*values), 8), fixed(std::get<1>(*values), 8),
                                             sigClose >= value ? QStringLiteral("above") : QStringLiteral("below")));
            } else {
                descriptions.append(QStringLiteral("VWAP=NaN/inf skipped"));
            }
        }
    }
    if (enabled(input, QStringLiteral("cmf"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("cmf"))) {
            const double value = std::get<2>(*values);
            if (std::isfinite(value)) {
                const QString flow = value > 0.0 ? QStringLiteral("accumulation") : value < 0.0 ? QStringLiteral("distribution") : QStringLiteral("neutral");
                descriptions.append(QStringLiteral("CMF=%1 (prev=%2, live=%3, %4)").arg(fixed(value, 4), fixed(std::get<0>(*values), 4), fixed(std::get<1>(*values), 4), flow));
                thresholdExisting(input, QStringLiteral("cmf"), QStringLiteral("CMF"), QStringLiteral("{:.4}"), value,
                                  Compare::BuyGeSellLe, std::nullopt, std::nullopt,
                                  buyAllowed, sellAllowed, signal, descriptions, sources, actions);
            } else {
                descriptions.append(QStringLiteral("CMF=NaN/inf skipped"));
            }
        }
    }
    if (enabled(input, QStringLiteral("obv"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("obv"))) {
            const double prev = std::get<0>(*values);
            const double live = std::get<1>(*values);
            const double value = std::get<2>(*values);
            if (std::isfinite(value)) {
                const QString trend = live > prev ? QStringLiteral("rising") : live < prev ? QStringLiteral("falling") : QStringLiteral("flat");
                descriptions.append(QStringLiteral("OBV=%1 (prev=%2, live=%3, %4)").arg(fixed(value, 2), fixed(prev, 2), fixed(live, 2), trend));
                thresholdExisting(input, QStringLiteral("obv"), QStringLiteral("OBV"), QStringLiteral("{:.2}"), value,
                                  Compare::BuyGeSellLe, std::nullopt, std::nullopt,
                                  buyAllowed, sellAllowed, signal, descriptions, sources, actions);
            } else {
                descriptions.append(QStringLiteral("OBV=NaN/inf skipped"));
            }
        }
    }
    if (enabled(input, QStringLiteral("keltner"))) {
        const auto upper = valueAt(input, QStringLiteral("keltner_upper"), signalIndex);
        const auto mid = valueAt(input, QStringLiteral("keltner_mid"), signalIndex);
        const auto lower = valueAt(input, QStringLiteral("keltner_lower"), signalIndex);
        if (upper && mid && lower) {
            const QString state = sigClose > *upper ? QStringLiteral("above upper") : sigClose < *lower ? QStringLiteral("below lower") : QStringLiteral("inside channel");
            descriptions.append(QStringLiteral("KC_up=%1,KC_mid=%2,KC_low=%3,close %4").arg(fixed(*upper, 8), fixed(*mid, 8), fixed(*lower, 8), state));
        }
    }
    if (enabled(input, QStringLiteral("ichimoku"))) {
        const auto tenkan = valueAt(input, QStringLiteral("ichimoku_tenkan"), signalIndex);
        const auto kijun = valueAt(input, QStringLiteral("ichimoku_kijun"), signalIndex);
        if (tenkan && kijun) {
            const double spanA = valueAt(input, QStringLiteral("ichimoku_span_a"), signalIndex).value_or(std::numeric_limits<double>::quiet_NaN());
            const double spanB = valueAt(input, QStringLiteral("ichimoku_span_b"), signalIndex).value_or(std::numeric_limits<double>::quiet_NaN());
            const double spread = *tenkan - *kijun;
            QString cloud = QStringLiteral("cloud unavailable");
            if (std::isfinite(spanA) && std::isfinite(spanB)) {
                const double top = std::max(spanA, spanB);
                const double bottom = std::min(spanA, spanB);
                cloud = sigClose > top ? QStringLiteral("above cloud") : sigClose < bottom ? QStringLiteral("below cloud") : QStringLiteral("inside cloud");
            }
            descriptions.append(QStringLiteral("IC_tenkan=%1,IC_kijun=%2,IC_span_a=%3,IC_span_b=%4,spread=%5,close %6")
                                    .arg(fixed(*tenkan, 8), fixed(*kijun, 8), fixed(spanA, 8), fixed(spanB, 8), fixed(spread, 8), cloud));
            thresholdExisting(input, QStringLiteral("ichimoku"), QStringLiteral("IC spread"), QStringLiteral("{:.2}"), spread,
                              Compare::BuyGeSellLe, std::nullopt, std::nullopt,
                              buyAllowed, sellAllowed, signal, descriptions, sources, actions);
        }
    }
    if (enabled(input, QStringLiteral("ma"))) {
        const auto lastMa = valueAt(input, QStringLiteral("ma"), signalIndex);
        const auto prevMa = valueAt(input, QStringLiteral("ma"), prevIndex);
        if (lastMa && prevMa) {
            descriptions.append(QStringLiteral("MA_prev=%1,MA_last=%2").arg(fixed(*prevMa, 8), fixed(*lastMa, 8)));
            if (buyAllowed && prevClose < *prevMa && sigClose > *lastMa) {
                addAction(QStringLiteral("ma"), QStringLiteral("BUY"), QStringLiteral("MA crossover -> BUY"), signal, descriptions, sources, actions);
            } else if (sellAllowed && prevClose > *prevMa && sigClose < *lastMa) {
                addAction(QStringLiteral("ma"), QStringLiteral("SELL"), QStringLiteral("MA crossover -> SELL"), signal, descriptions, sources, actions);
            }
        }
    }
    if (enabled(input, QStringLiteral("bb"))) {
        const auto upper = valueAt(input, QStringLiteral("bb_upper"), signalIndex);
        const auto mid = valueAt(input, QStringLiteral("bb_mid"), signalIndex);
        const auto lower = valueAt(input, QStringLiteral("bb_lower"), signalIndex);
        if (upper && mid && lower) {
            descriptions.append(
                QStringLiteral("BB_up=%1,BB_mid=%2,BB_low=%3")
                    .arg(fixed(*upper, 8), fixed(*mid, 8), fixed(*lower, 8)));
        }
    }

    // Keep the presentation order identical to Python even when native helper
    // implementations evaluate indicators in a different order.
    const QStringList pythonDescriptionPriority = {
        QStringLiteral("rsi"),
        QStringLiteral("stoch_rsi"),
        QStringLiteral("willr"),
        QStringLiteral("atr"),
        QStringLiteral("natr"),
        QStringLiteral("vwap"),
        QStringLiteral("mfi"),
        QStringLiteral("obv"),
        QStringLiteral("rvol"),
        QStringLiteral("cmf"),
        QStringLiteral("cci"),
        QStringLiteral("roc"),
        QStringLiteral("trix"),
        QStringLiteral("bbw"),
        QStringLiteral("ppo"),
        QStringLiteral("ao"),
        QStringLiteral("kst"),
        QStringLiteral("aroon"),
        QStringLiteral("chop"),
        QStringLiteral("ma"),
        QStringLiteral("bb"),
        QStringLiteral("keltner"),
        QStringLiteral("ichimoku"),
    };
    const auto descriptionKey = [](const QString &description) {
        if (description.startsWith(QStringLiteral("RSI"))) return QStringLiteral("rsi");
        if (description.startsWith(QStringLiteral("StochRSI"))) return QStringLiteral("stoch_rsi");
        if (description.startsWith(QStringLiteral("Williams %R"))) return QStringLiteral("willr");
        if (description.startsWith(QStringLiteral("ATR"))) return QStringLiteral("atr");
        if (description.startsWith(QStringLiteral("NATR"))) return QStringLiteral("natr");
        if (description.startsWith(QStringLiteral("VWAP"))) return QStringLiteral("vwap");
        if (description.startsWith(QStringLiteral("MFI"))) return QStringLiteral("mfi");
        if (description.startsWith(QStringLiteral("OBV"))) return QStringLiteral("obv");
        if (description.startsWith(QStringLiteral("RVOL"))) return QStringLiteral("rvol");
        if (description.startsWith(QStringLiteral("CMF"))) return QStringLiteral("cmf");
        if (description.startsWith(QStringLiteral("CCI"))) return QStringLiteral("cci");
        if (description.startsWith(QStringLiteral("ROC"))) return QStringLiteral("roc");
        if (description.startsWith(QStringLiteral("TRIX"))) return QStringLiteral("trix");
        if (description.startsWith(QStringLiteral("BBW"))) return QStringLiteral("bbw");
        if (description.startsWith(QStringLiteral("PPO"))) return QStringLiteral("ppo");
        if (description.startsWith(QStringLiteral("AO"))) return QStringLiteral("ao");
        if (description.startsWith(QStringLiteral("KST"))) return QStringLiteral("kst");
        if (description.startsWith(QStringLiteral("Aroon"))) return QStringLiteral("aroon");
        if (description.startsWith(QStringLiteral("CHOP"))) return QStringLiteral("chop");
        if (description.startsWith(QStringLiteral("MA_"))) return QStringLiteral("ma");
        if (description.startsWith(QStringLiteral("BB_"))) return QStringLiteral("bb");
        if (description.startsWith(QStringLiteral("KC_"))) return QStringLiteral("keltner");
        if (description.startsWith(QStringLiteral("IC_"))) return QStringLiteral("ichimoku");
        return QString();
    };
    QMap<QString, QStringList> descriptionsByKey;
    QStringList unclassifiedDescriptions;
    for (const QString &description : descriptions) {
        const QString key = descriptionKey(description);
        if (key.isEmpty()) {
            unclassifiedDescriptions.append(description);
        } else {
            descriptionsByKey[key].append(description);
        }
    }
    QStringList orderedDescriptions;
    for (const QString &key : pythonDescriptionPriority) {
        orderedDescriptions.append(descriptionsByKey.value(key));
    }
    orderedDescriptions.append(unclassifiedDescriptions);
    descriptions = orderedDescriptions;
    if (descriptions.isEmpty()) {
        descriptions.append(QStringLiteral("No triggers evaluated"));
    }
    const QStringList pythonSignalPriority = {
        QStringLiteral("rsi"),
        QStringLiteral("stoch_rsi"),
        QStringLiteral("willr"),
        QStringLiteral("natr"),
        QStringLiteral("mfi"),
        QStringLiteral("obv"),
        QStringLiteral("rvol"),
        QStringLiteral("cmf"),
        QStringLiteral("cci"),
        QStringLiteral("roc"),
        QStringLiteral("trix"),
        QStringLiteral("bbw"),
        QStringLiteral("ppo"),
        QStringLiteral("ao"),
        QStringLiteral("kst"),
        QStringLiteral("aroon"),
        QStringLiteral("chop"),
        QStringLiteral("ma"),
        QStringLiteral("ichimoku"),
    };
    for (const QString &key : pythonSignalPriority) {
        if (actions.contains(key)) {
            signal = actions.value(key).toString().toUpper();
            break;
        }
    }
    QJsonArray sourceArray;
    QSet<QString> seen;
    QStringList orderedSources;
    for (const QString &key : pythonSignalPriority) {
        if (sources.contains(key)) {
            orderedSources.append(key);
        }
    }
    for (const QString &source : sources) {
        if (!orderedSources.contains(source)) {
            orderedSources.append(source);
        }
    }
    for (const QString &source : orderedSources) {
        if (!seen.contains(source)) {
            seen.insert(source);
            sourceArray.append(source);
        }
    }
    return {
        {QStringLiteral("signal"), signal.isEmpty() ? QJsonValue() : QJsonValue(signal)},
        {QStringLiteral("description"), descriptions.join(QStringLiteral(" | "))},
        {QStringLiteral("trigger_price"), signal.isEmpty() ? QJsonValue() : QJsonValue(sigClose)},
        {QStringLiteral("trigger_sources"), sourceArray},
        {QStringLiteral("trigger_actions"), actions},
        {QStringLiteral("min_bars"), minBars},
        {QStringLiteral("signal_index_from_end"), fromEnd},
    };
}

QJsonObject applyIndicatorSignalConfirmation(
    const QJsonObject &decision,
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 signalTimestampMs,
    QMap<QString, IndicatorSignalConfirmationTracker> &trackers) {
    const QJsonObject normalizedRiskControls = normalizeStrategyRiskControls(riskControls);
    const int required = std::max(
        1,
        static_cast<int>(intOf(normalizedRiskControls.value(QStringLiteral("indicator_flip_confirmation_bars")))
                             .value_or(1)));
    const QJsonObject actions = decision.value(QStringLiteral("trigger_actions")).toObject();
    if (required <= 1 || actions.isEmpty()) {
        return decision;
    }

    const double resetWindowSeconds = std::max(1.0, pythonIndicatorIntervalSeconds(interval))
        * static_cast<double>(std::max(required + 1, 2));
    const qint64 resetWindowMs = static_cast<qint64>(std::max(
        1000.0,
        std::ceil(resetWindowSeconds * 1000.0)));
    const QString symbolNorm = symbol.trimmed().toUpper();
    const QString intervalNorm = interval.trimmed().toLower().isEmpty()
        ? QStringLiteral("default")
        : interval.trimmed().toLower();
    QJsonObject confirmedActions;
    QStringList waiting;
    for (auto iterator = actions.constBegin(); iterator != actions.constEnd(); ++iterator) {
        const QString action = iterator.value().toString();
        const QString actionNorm = action.trimmed().toLower();
        if (actionNorm != QStringLiteral("buy") && actionNorm != QStringLiteral("sell")) {
            confirmedActions.insert(iterator.key(), iterator.value());
            continue;
        }

        const QString trackerKey = QStringLiteral("%1|%2|%3")
                                       .arg(symbolNorm, intervalNorm, iterator.key().trimmed().toLower());
        IndicatorSignalConfirmationTracker &tracker = trackers[trackerKey];
        const qint64 elapsedMs = signalTimestampMs - tracker.timestampMs;
        if (tracker.count > 0 && tracker.direction == actionNorm && elapsedMs <= resetWindowMs) {
            ++tracker.count;
        } else {
            tracker.direction = actionNorm;
            tracker.count = 1;
        }
        tracker.timestampMs = signalTimestampMs;
        if (tracker.count >= required) {
            confirmedActions.insert(iterator.key(), iterator.value());
        } else {
            waiting.append(QStringLiteral("%1 %2 %3/%4")
                               .arg(iterator.key(), actionNorm)
                               .arg(tracker.count)
                               .arg(required));
        }
    }

    if (waiting.isEmpty()) {
        return decision;
    }

    QJsonObject out = decision;
    out.insert(QStringLiteral("trigger_actions"), confirmedActions);
    const QJsonArray originalSources = decision.value(QStringLiteral("trigger_sources")).toArray();
    QJsonArray confirmedSources;
    QString confirmedSignal;
    for (const QJsonValue &sourceValue : originalSources) {
        const QString source = sourceValue.toString();
        if (!confirmedActions.contains(source)) {
            continue;
        }
        confirmedSources.append(source);
        if (confirmedSignal.isEmpty()) {
            const QString action = confirmedActions.value(source).toString().trimmed().toLower();
            if (action == QStringLiteral("buy")) {
                confirmedSignal = QStringLiteral("BUY");
            } else if (action == QStringLiteral("sell")) {
                confirmedSignal = QStringLiteral("SELL");
            }
        }
    }
    out.insert(QStringLiteral("trigger_sources"), confirmedSources);
    out.insert(QStringLiteral("signal"), confirmedSignal.isEmpty()
        ? QJsonValue()
        : QJsonValue(confirmedSignal));
    if (confirmedSignal.isEmpty()) {
        out.insert(QStringLiteral("trigger_price"), QJsonValue());
    }
    out.insert(
        QStringLiteral("description"),
        decision.value(QStringLiteral("description")).toString()
            + QStringLiteral(" | Indicator confirmation pending: ")
            + waiting.join(QStringLiteral(", ")));
    return out;
}

namespace {

QString indicatorOrderGuardKey(const QString &symbol, const QString &interval, const QString &indicator) {
    const QString symbolNorm = symbol.trimmed().toUpper();
    const QString intervalNorm = interval.trimmed().toLower().isEmpty()
        ? QStringLiteral("default")
        : interval.trimmed().toLower();
    return QStringLiteral("%1|%2|%3")
        .arg(symbolNorm, intervalNorm, indicator.trimmed().toLower());
}

QString indicatorReentryBlockKey(const QString &symbol, const QString &interval, const QString &side) {
    const QString intervalNorm = interval.trimmed().toLower().isEmpty()
        ? QStringLiteral("default")
        : interval.trimmed().toLower();
    return QStringLiteral("%1|%2|%3")
        .arg(symbol.trimmed().toUpper(), intervalNorm, side.trimmed().toUpper());
}

QStringList rebuildDecisionSourcesAndSignal(QJsonObject &decision) {
    const QJsonObject actions = decision.value(QStringLiteral("trigger_actions")).toObject();
    const QJsonArray originalSources = decision.value(QStringLiteral("trigger_sources")).toArray();
    QJsonArray sources;
    QString signal;
    for (const QJsonValue &sourceValue : originalSources) {
        const QString source = sourceValue.toString();
        if (!actions.contains(source)) {
            continue;
        }
        sources.append(source);
        if (signal.isEmpty()) {
            const QString action = actions.value(source).toString().trimmed().toLower();
            if (action == QStringLiteral("buy")) {
                signal = QStringLiteral("BUY");
            } else if (action == QStringLiteral("sell")) {
                signal = QStringLiteral("SELL");
            }
        }
    }
    decision.insert(QStringLiteral("trigger_sources"), sources);
    decision.insert(QStringLiteral("signal"), signal.isEmpty() ? QJsonValue() : QJsonValue(signal));
    if (signal.isEmpty()) {
        decision.insert(QStringLiteral("trigger_price"), QJsonValue());
    }
    return {};
}

double effectiveIndicatorWindowSeconds(
    const QJsonObject &riskControls,
    const QString &secondsKey,
    const QString &barsKey,
    const QString &interval) {
    const double intervalWindow = std::max(1.0, pythonIndicatorIntervalSeconds(interval));
    const double seconds = std::max(0.0, numberOf(riskControls.value(secondsKey)).value_or(0.0));
    const double bars = std::max(0.0, numberOf(riskControls.value(barsKey)).value_or(0.0));
    return std::max(seconds, bars * intervalWindow);
}

} // namespace

void refreshIndicatorReentrySignalBlocks(
    const QJsonObject &actions,
    const QString &symbol,
    const QString &interval,
    QMap<QString, IndicatorOrderGuardState> &states) {
    QMap<QString, QString> actionSides;
    for (auto iterator = actions.constBegin(); iterator != actions.constEnd(); ++iterator) {
        const QString indicator = iterator.key().trimmed().toLower();
        const QString action = iterator.value().toString().trimmed().toLower();
        if (indicator.isEmpty()) {
            continue;
        }
        if (action == QStringLiteral("buy")) {
            actionSides.insert(indicator, QStringLiteral("BUY"));
        } else if (action == QStringLiteral("sell")) {
            actionSides.insert(indicator, QStringLiteral("SELL"));
        }
    }
    const QString keyPrefix = indicatorOrderGuardKey(symbol, interval, QString());
    for (auto iterator = states.begin(); iterator != states.end(); ++iterator) {
        if (!iterator.key().startsWith(keyPrefix)) {
            continue;
        }
        const QString indicator = iterator.key().mid(keyPrefix.size());
        if (!iterator.value().signalResetSide.isEmpty()
            && actionSides.value(indicator) != iterator.value().signalResetSide) {
            iterator.value().signalResetSide.clear();
        }
    }
}

QJsonObject applyIndicatorOrderGuards(
    const QJsonObject &decision,
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 signalTimestampMs,
    QMap<QString, IndicatorOrderGuardState> &states,
    QMap<QString, qint64> &reentryBlocks) {
    const QJsonObject normalizedRiskControls = normalizeStrategyRiskControls(riskControls);
    const QJsonObject actions = decision.value(QStringLiteral("trigger_actions")).toObject();
    const bool requireSignalReset = coerceStrategyBool(
        normalizedRiskControls.value(QStringLiteral("indicator_reentry_requires_signal_reset")), false);
    if (requireSignalReset) {
        refreshIndicatorReentrySignalBlocks(actions, symbol, interval, states);
    }
    if (actions.isEmpty()) {
        return decision;
    }
    const double cooldownSeconds = effectiveIndicatorWindowSeconds(
        normalizedRiskControls,
        QStringLiteral("indicator_flip_cooldown_seconds"),
        QStringLiteral("indicator_flip_cooldown_bars"),
        interval);
    const double reentrySeconds = effectiveIndicatorWindowSeconds(
        normalizedRiskControls,
        QStringLiteral("indicator_reentry_cooldown_seconds"),
        QStringLiteral("indicator_reentry_cooldown_bars"),
        interval);
    const qint64 recentCloseWindowMs = static_cast<qint64>(std::ceil(
        std::max(5.0, std::min(std::max(1.0, pythonIndicatorIntervalSeconds(interval)) * 1.5, 600.0)) * 1000.0));
    QJsonObject allowedActions;
    QStringList waiting;
    for (auto iterator = actions.constBegin(); iterator != actions.constEnd(); ++iterator) {
        const QString action = iterator.value().toString();
        const QString actionNorm = action.trimmed().toLower();
        if (actionNorm != QStringLiteral("buy") && actionNorm != QStringLiteral("sell")) {
            allowedActions.insert(iterator.key(), iterator.value());
            continue;
        }
        const QString side = actionNorm == QStringLiteral("buy") ? QStringLiteral("BUY") : QStringLiteral("SELL");
        const QString oppositeSide = side == QStringLiteral("BUY")
            ? QStringLiteral("SELL")
            : QStringLiteral("BUY");
        const QString indicator = iterator.key().trimmed().toLower();
        if (indicator.isEmpty()) {
            continue;
        }
        const QString stateKey = indicatorOrderGuardKey(symbol, interval, indicator);
        IndicatorOrderGuardState &state = states[stateKey];
        bool blocked = false;
        if (requireSignalReset && state.signalResetSide == side) {
            waiting.append(QStringLiteral("%1 %2 signal reset").arg(indicator, side));
            blocked = true;
        }
        if (!blocked && cooldownSeconds > 0.0
            && state.lastActionMs > 0
            && state.lastActionSide != side) {
            const qint64 elapsedMs = std::max<qint64>(0, signalTimestampMs - state.lastActionMs);
            const qint64 cooldownMs = static_cast<qint64>(std::ceil(cooldownSeconds * 1000.0));
            const bool recentClose = state.recentCloseMs > 0
                && state.recentCloseSide == oppositeSide
                && signalTimestampMs - state.recentCloseMs <= recentCloseWindowMs;
            if (elapsedMs < cooldownMs && !recentClose) {
                waiting.append(QStringLiteral("%1 %2 cooldown %3s")
                                   .arg(indicator, side)
                                   .arg(std::max(0.0, (cooldownMs - elapsedMs) / 1000.0), 0, 'f', 1));
                blocked = true;
            }
        }
        if (!blocked && reentrySeconds > 0.0) {
            const qint64 blockedUntil = reentryBlocks.value(indicatorReentryBlockKey(symbol, interval, side), 0);
            if (blockedUntil > signalTimestampMs) {
                waiting.append(QStringLiteral("%1 %2 re-entry %3s")
                                   .arg(indicator, side)
                                   .arg(std::max<qint64>(0, blockedUntil - signalTimestampMs) / 1000.0, 0, 'f', 1));
                blocked = true;
            }
        }
        if (!blocked) {
            allowedActions.insert(iterator.key(), iterator.value());
        }
    }
    if (waiting.isEmpty()) {
        return decision;
    }
    QJsonObject out = decision;
    out.insert(QStringLiteral("trigger_actions"), allowedActions);
    rebuildDecisionSourcesAndSignal(out);
    out.insert(
        QStringLiteral("description"),
        decision.value(QStringLiteral("description")).toString()
            + QStringLiteral(" | Indicator order guard pending: ")
            + waiting.join(QStringLiteral(", ")));
    return out;
}

void recordIndicatorOrderAction(
    const QString &symbol,
    const QString &interval,
    const QString &indicator,
    const QString &side,
    qint64 timestampMs,
    QMap<QString, IndicatorOrderGuardState> &states) {
    const QString indicatorNorm = indicator.trimmed().toLower();
    const QString sideNorm = side.trimmed().toUpper();
    if (indicatorNorm.isEmpty() || (sideNorm != QStringLiteral("BUY") && sideNorm != QStringLiteral("SELL"))) {
        return;
    }
    IndicatorOrderGuardState &state = states[indicatorOrderGuardKey(symbol, interval, indicatorNorm)];
    state.lastActionSide = sideNorm;
    state.lastActionMs = timestampMs;
    if (!state.signalResetSide.isEmpty() && state.signalResetSide != sideNorm) {
        state.signalResetSide.clear();
    }
}

void recordIndicatorClose(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QString &indicator,
    const QString &side,
    qint64 timestampMs,
    QMap<QString, IndicatorOrderGuardState> &states,
    QMap<QString, qint64> &reentryBlocks) {
    const QString sideNorm = side.trimmed().toUpper();
    if (sideNorm != QStringLiteral("BUY") && sideNorm != QStringLiteral("SELL")) {
        return;
    }
    const QString indicatorNorm = indicator.trimmed().toLower();
    if (indicatorNorm.isEmpty()) {
        return;
    }
    IndicatorOrderGuardState &state = states[indicatorOrderGuardKey(symbol, interval, indicatorNorm)];
    state.recentCloseMs = timestampMs;
    state.recentCloseSide = sideNorm;
    if (coerceStrategyBool(
            normalizeStrategyRiskControls(riskControls)
                .value(QStringLiteral("indicator_reentry_requires_signal_reset")),
            false)) {
        state.signalResetSide = sideNorm;
    }
    const double reentrySeconds = effectiveIndicatorWindowSeconds(
        normalizeStrategyRiskControls(riskControls),
        QStringLiteral("indicator_reentry_cooldown_seconds"),
        QStringLiteral("indicator_reentry_cooldown_bars"),
        interval);
    if (reentrySeconds > 0.0) {
        reentryBlocks.insert(
            indicatorReentryBlockKey(symbol, interval, sideNorm),
            timestampMs + static_cast<qint64>(std::ceil(reentrySeconds * 1000.0)));
    }
}

void recordIndicatorCloses(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QStringList &indicators,
    const QString &side,
    qint64 timestampMs,
    QMap<QString, IndicatorOrderGuardState> &states,
    QMap<QString, qint64> &reentryBlocks) {
    QSet<QString> seen;
    for (const QString &rawIndicator : indicators) {
        const QString indicator = rawIndicator.trimmed().toLower();
        if (indicator.isEmpty()
            || indicator == QStringLiteral("generic")
            || seen.contains(indicator)) {
            continue;
        }
        seen.insert(indicator);
        recordIndicatorClose(
            riskControls,
            symbol,
            interval,
            indicator,
            side,
            timestampMs,
            states,
            reentryBlocks);
    }
}

void queueIndicatorFlipOnClose(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    const QStringList &indicators,
    const QString &closedSide,
    double quantity,
    qint64 timestampMs,
    QMap<QString, QJsonObject> &pendingRequests) {
    const QJsonObject normalized = normalizeStrategyRiskControls(riskControls);
    if (!coerceStrategyBool(normalized.value(QStringLiteral("auto_flip_on_close")))
        || !qIsFinite(quantity)
        || quantity <= 1e-10) {
        return;
    }
    const QString closedSideNorm = closedSide.trimmed().toUpper();
    const QString openSide = closedSideNorm == QStringLiteral("BUY")
        || closedSideNorm == QStringLiteral("LONG")
        ? QStringLiteral("SELL")
        : closedSideNorm == QStringLiteral("SELL") || closedSideNorm == QStringLiteral("SHORT")
            ? QStringLiteral("BUY")
            : QString();
    const QString symbolNorm = symbol.trimmed().toUpper();
    if (symbolNorm.isEmpty() || openSide.isEmpty()) {
        return;
    }
    QString intervalNorm = interval.trimmed().toLower();
    if (intervalNorm.isEmpty()) {
        intervalNorm = QStringLiteral("default");
    }
    QSet<QString> seen;
    for (const QString &rawIndicator : indicators) {
        const QString indicator = rawIndicator.trimmed().toLower();
        if (indicator.isEmpty() || indicator == QStringLiteral("generic") || seen.contains(indicator)) {
            continue;
        }
        seen.insert(indicator);
        const QString key = QStringLiteral("%1|%2|%3|%4")
                                .arg(symbolNorm, intervalNorm, indicator, openSide);
        pendingRequests.insert(
            key,
            QJsonObject{
                {QStringLiteral("symbol"), symbolNorm},
                {QStringLiteral("interval"), intervalNorm},
                {QStringLiteral("indicator_key"), indicator},
                {QStringLiteral("side"), openSide},
                {QStringLiteral("flip_from"), closedSideNorm},
                {QStringLiteral("qty"), quantity},
                {QStringLiteral("timestamp_ms"), static_cast<double>(timestampMs)},
            });
    }
}

QJsonObject mergeIndicatorFlipOnCloseRequests(
    const QJsonObject &decision,
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 timestampMs,
    QMap<QString, QJsonObject> &pendingRequests) {
    const QJsonObject normalized = normalizeStrategyRiskControls(riskControls);
    if (!coerceStrategyBool(normalized.value(QStringLiteral("auto_flip_on_close")))) {
        return decision;
    }

    QStringList intervalTokens = interval.trimmed().toLower().split(
        QRegularExpression(QStringLiteral("[^a-z0-9]+")),
        Qt::SkipEmptyParts);
    if (intervalTokens.isEmpty()) {
        intervalTokens << QStringLiteral("default");
    }
    const QString symbolNorm = symbol.trimmed().toUpper();
    const double ttlMs = std::max(5'000.0, std::max(1.0, pythonIndicatorIntervalSeconds(interval)) * 2.0 * 1'000.0);
    QList<QString> removeKeys;
    QList<QJsonObject> requests;
    for (auto iterator = pendingRequests.cbegin(); iterator != pendingRequests.cend(); ++iterator) {
        const QJsonObject request = iterator.value();
        if (request.value(QStringLiteral("symbol")).toString().trimmed().toUpper() != symbolNorm) {
            continue;
        }
        const QString requestInterval = request.value(QStringLiteral("interval")).toString().trimmed().toLower();
        const QStringList requestTokens = requestInterval.split(
            QRegularExpression(QStringLiteral("[^a-z0-9]+")),
            Qt::SkipEmptyParts);
        bool intervalMatches = false;
        for (const QString &token : intervalTokens) {
            if (requestTokens.contains(token)) {
                intervalMatches = true;
                break;
            }
        }
        if (!intervalMatches) {
            continue;
        }
        const qint64 requestTimestamp = static_cast<qint64>(
            request.value(QStringLiteral("timestamp_ms")).toDouble());
        const double ageMs = std::max<qint64>(0, timestampMs - requestTimestamp);
        removeKeys.append(iterator.key());
        if (ageMs <= ttlMs) {
            requests.append(request);
        }
    }
    for (const QString &key : removeKeys) {
        pendingRequests.remove(key);
    }
    if (requests.isEmpty()) {
        return decision;
    }

    const bool requireFlipSignal = coerceStrategyBool(
        normalized.value(QStringLiteral("require_indicator_flip_signal")));
    const bool strictFlipGuard = coerceStrategyBool(
        normalized.value(QStringLiteral("strict_indicator_flip_enforcement")));
    const bool allowWithoutSignal = coerceStrategyBool(
        normalized.value(QStringLiteral("allow_indicator_close_without_signal")));
    const bool requireLiveConfirmation = requireFlipSignal && strictFlipGuard && !allowWithoutSignal;
    QJsonObject result = decision;
    QJsonObject actions = result.value(QStringLiteral("trigger_actions")).toObject();
    QJsonArray sources = result.value(QStringLiteral("trigger_sources")).toArray();
    if (requireLiveConfirmation && actions.isEmpty()) {
        return result;
    }

    QString description = result.value(QStringLiteral("description")).toString();
    for (const QJsonObject &request : requests) {
        const QString indicator = request.value(QStringLiteral("indicator_key")).toString().trimmed().toLower();
        const QString side = request.value(QStringLiteral("side")).toString().trimmed().toUpper();
        if (indicator.isEmpty() || (side != QStringLiteral("BUY") && side != QStringLiteral("SELL"))) {
            continue;
        }
        if (actions.contains(indicator)) {
            if (actions.value(indicator).toString().trimmed().compare(side, Qt::CaseInsensitive) == 0) {
                continue;
            }
            continue;
        }
        if (requireLiveConfirmation) {
            continue;
        }
        actions.insert(indicator, side.toLower());
        bool sourcePresent = false;
        for (const QJsonValue &source : sources) {
            if (source.toString().trimmed().compare(indicator, Qt::CaseInsensitive) == 0) {
                sourcePresent = true;
                break;
            }
        }
        if (!sourcePresent) {
            sources.append(indicator);
        }
        description += QStringLiteral(" | %1 flip-on-close -> %2 (from %3)")
                           .arg(indicator.toUpper(), side,
                                request.value(QStringLiteral("flip_from")).toString());
        result.insert(QStringLiteral("flip_qty"), request.value(QStringLiteral("qty")));
        result.insert(QStringLiteral("flip_qty_target"), request.value(QStringLiteral("qty")));
    }

    result.insert(QStringLiteral("trigger_actions"), actions);
    result.insert(QStringLiteral("trigger_sources"), sources);
    result.insert(QStringLiteral("description"), description);
    QString signal;
    for (const QJsonValue &source : sources) {
        const QString action = actions.value(source.toString()).toString().trimmed().toUpper();
        if (action == QStringLiteral("BUY") || action == QStringLiteral("SELL")) {
            signal = action;
            break;
        }
    }
    if (!signal.isEmpty()) {
        result.insert(QStringLiteral("signal"), signal);
    }
    return result;
}

QJsonObject normalizeStrategyControls(const QString &kind, const QJsonObject &controls) {
    QJsonObject out;
    const bool isRuntime = kind == QStringLiteral("runtime");
    const bool isBacktest = kind == QStringLiteral("backtest");
    if (isRuntime) {
        const QString side = normalizeRuntimeSide(controls.value(QStringLiteral("side")));
        if (!side.isEmpty()) out.insert(QStringLiteral("side"), side);
        if (!controls.value(QStringLiteral("position_pct")).isNull()
            && !controls.value(QStringLiteral("position_pct")).isUndefined()) {
            if (auto value = pythonNumberOf(controls.value(QStringLiteral("position_pct")))) {
                out.insert(QStringLiteral("position_pct"), *value);
            }
        }
        QJsonValue unitsValue = controls.value(QStringLiteral("position_pct_units"));
        if (!pythonTruthy(unitsValue)) {
            unitsValue = controls.value(QStringLiteral("_position_pct_units"));
        }
        const QString units = normalizePositionPctUnits(unitsValue);
        if (!units.isEmpty()) out.insert(QStringLiteral("position_pct_units"), units);
        if (!controls.value(QStringLiteral("leverage")).isNull()
            && !controls.value(QStringLiteral("leverage")).isUndefined()) {
            if (auto lev = pythonIntOf(controls.value(QStringLiteral("leverage"))); lev && *lev >= 1) {
                out.insert(QStringLiteral("leverage"), integerValue(*lev));
            }
        }
        const QJsonValue loopValue = controls.value(QStringLiteral("loop_interval_override"));
        const QString loop = pythonTruthy(loopValue) ? normalizeLoop(loopValue) : QString();
        if (!loop.isEmpty()) out.insert(QStringLiteral("loop_interval_override"), loop);
        const QJsonValue addOnly = controls.value(QStringLiteral("add_only"));
        if (!addOnly.isUndefined() && !addOnly.isNull()) {
            out.insert(QStringLiteral("add_only"), pythonTruthy(addOnly));
        }
        const QJsonValue accountValue = controls.value(QStringLiteral("account_mode"));
        if (pythonTruthy(accountValue)) {
            const QString account = normalizeAccountMode(accountValue);
            if (!account.isEmpty()) out.insert(QStringLiteral("account_mode"), account);
        }
    } else if (isBacktest) {
        const QString logic = normalizeStrategySignalLogic(controls.value(QStringLiteral("logic")));
        if (!logic.isEmpty()) out.insert(QStringLiteral("logic"), logic);
        if (!controls.value(QStringLiteral("capital")).isNull()
            && !controls.value(QStringLiteral("capital")).isUndefined()) {
            if (auto value = pythonNumberOf(controls.value(QStringLiteral("capital")))) {
                out.insert(QStringLiteral("capital"), *value);
            }
        }
        if (!controls.value(QStringLiteral("position_pct")).isNull()
            && !controls.value(QStringLiteral("position_pct")).isUndefined()) {
            if (auto value = pythonNumberOf(controls.value(QStringLiteral("position_pct")))) {
                out.insert(QStringLiteral("position_pct"), *value);
            }
        }
        QJsonValue unitsValue = controls.value(QStringLiteral("position_pct_units"));
        if (!pythonTruthy(unitsValue)) {
            unitsValue = controls.value(QStringLiteral("_position_pct_units"));
        }
        const QString units = normalizePositionPctUnits(unitsValue);
        if (!units.isEmpty()) out.insert(QStringLiteral("position_pct_units"), units);
        const QJsonValue sideValue = controls.value(QStringLiteral("side"));
        if (pythonTruthy(sideValue)) {
            const QString side = canonicalSide(sideValue);
            if (!side.isEmpty()) out.insert(QStringLiteral("side"), side);
        }
        const QJsonValue marginValue = controls.value(QStringLiteral("margin_mode"));
        if (pythonTruthy(marginValue)) {
            out.insert(QStringLiteral("margin_mode"), pythonStringOf(marginValue));
        }
        const QJsonValue positionModeValue = controls.value(QStringLiteral("position_mode"));
        if (pythonTruthy(positionModeValue)) {
            out.insert(QStringLiteral("position_mode"), pythonStringOf(positionModeValue));
        }
        const QJsonValue assetsValue = controls.value(QStringLiteral("assets_mode"));
        if (pythonTruthy(assetsValue)) {
            const QString assets = normalizeAssetsMode(assetsValue);
            if (!assets.isEmpty()) out.insert(QStringLiteral("assets_mode"), assets);
        }
        const QJsonValue accountValue = controls.value(QStringLiteral("account_mode"));
        if (pythonTruthy(accountValue)) {
            const QString account = normalizeAccountMode(accountValue);
            if (!account.isEmpty()) out.insert(QStringLiteral("account_mode"), account);
        }
        const QJsonValue loopValue = controls.value(QStringLiteral("loop_interval_override"));
        const QString loop = pythonTruthy(loopValue) ? normalizeLoop(loopValue) : QString();
        if (!loop.isEmpty()) out.insert(QStringLiteral("loop_interval_override"), loop);
        if (!controls.value(QStringLiteral("leverage")).isNull()
            && !controls.value(QStringLiteral("leverage")).isUndefined()) {
            if (auto lev = pythonIntOf(controls.value(QStringLiteral("leverage")))) {
                out.insert(QStringLiteral("leverage"), integerValue(*lev));
            }
        }
    }
    if (isRuntime || isBacktest) {
        if (controls.value(QStringLiteral("stop_loss")).isObject()) {
            out.insert(
                QStringLiteral("stop_loss"),
                normalizeStopLoss(controls.value(QStringLiteral("stop_loss")).toObject()));
        }
        const QJsonValue backendValue = controls.value(QStringLiteral("connector_backend"));
        if (pythonTruthy(backendValue)) {
            out.insert(
                QStringLiteral("connector_backend"),
                NativeExchangeConnectors::normalizeConnectorBackend(pythonStringOf(backendValue)));
        }
    }
    return out;
}

double positionPctFraction(
    const QJsonObject &controls,
    double fallbackPositionPct,
    const QString &fallbackUnits) {
    const QJsonObject normalized = normalizeStrategyControls(QStringLiteral("runtime"), controls);
    double raw = normalized.value(QStringLiteral("position_pct")).toDouble(fallbackPositionPct);
    if (!std::isfinite(raw)) {
        raw = std::isfinite(fallbackPositionPct) ? fallbackPositionPct : 2.0;
    }

    QString units = normalized.value(QStringLiteral("position_pct_units")).toString().trimmed();
    if (units.isEmpty()) {
        units = fallbackUnits.trimmed();
    }
    const QString canonicalUnits = normalizePositionPctUnits(units);
    double fraction = raw;
    if (canonicalUnits == QStringLiteral("percent")) {
        fraction = raw / 100.0;
    } else if (canonicalUnits != QStringLiteral("fraction") && raw > 1.0) {
        fraction = raw / 100.0;
    }
    if (!std::isfinite(fraction)) {
        fraction = 0.0001;
    }
    return std::clamp(fraction, 0.0001, 1.0);
}

QJsonObject normalizeStrategyRiskControls(const QJsonObject &controls) {
    QJsonObject out = pythonRiskDefaults();
    const QJsonObject input = controls.value(QStringLiteral("strategy_controls")).isObject()
        ? controls.value(QStringLiteral("strategy_controls")).toObject()
        : controls;

    const QStringList boolKeys{
        QStringLiteral("indicator_use_live_values"),
        QStringLiteral("require_indicator_flip_signal"),
        QStringLiteral("strict_indicator_flip_enforcement"),
        QStringLiteral("indicator_reentry_requires_signal_reset"),
        QStringLiteral("auto_flip_on_close"),
        QStringLiteral("allow_close_ignoring_hold"),
        QStringLiteral("allow_multi_indicator_close"),
        QStringLiteral("allow_indicator_close_without_signal"),
        QStringLiteral("close_on_exit"),
        QStringLiteral("positions_missing_autoclose"),
        QStringLiteral("allow_opposite_positions"),
        QStringLiteral("hedge_preserve_opposites"),
    };
    for (const QString &key : boolKeys) {
        if (!input.value(key).isUndefined()) {
            out.insert(key, NativeStrategyRuntime::coerceStrategyBool(input.value(key), out.value(key).toBool()));
        }
    }

    const QStringList integerKeys{
        QStringLiteral("indicator_flip_cooldown_bars"),
        QStringLiteral("indicator_min_position_hold_bars"),
        QStringLiteral("indicator_reentry_cooldown_bars"),
        QStringLiteral("indicator_flip_confirmation_bars"),
        QStringLiteral("positions_missing_threshold"),
        QStringLiteral("futures_flat_purge_miss_threshold"),
    };
    for (const QString &key : integerKeys) {
        if (auto value = intOf(input.value(key))) {
            const qint64 minimum = key == QStringLiteral("positions_missing_threshold")
                || key == QStringLiteral("futures_flat_purge_miss_threshold")
                || key == QStringLiteral("indicator_flip_confirmation_bars")
                ? 1
                : 0;
            out.insert(key, integerValue(std::max(minimum, *value)));
        }
    }

    const QStringList numberKeys{
        QStringLiteral("indicator_flip_cooldown_seconds"),
        QStringLiteral("indicator_min_position_hold_seconds"),
        QStringLiteral("indicator_reentry_cooldown_seconds"),
        QStringLiteral("positions_missing_grace_seconds"),
        QStringLiteral("futures_flat_purge_grace_seconds"),
        QStringLiteral("max_auto_bump_percent"),
        QStringLiteral("auto_bump_percent_multiplier"),
    };
    for (const QString &key : numberKeys) {
        if (auto value = numberOf(input.value(key))) {
            out.insert(key, std::max(0.0, *value));
        }
    }

    if (input.value(QStringLiteral("stop_loss")).isObject()) {
        out.insert(
            QStringLiteral("stop_loss"),
            normalizeStopLoss(input.value(QStringLiteral("stop_loss")).toObject()));
    } else if (out.value(QStringLiteral("stop_loss")).isObject()) {
        out.insert(
            QStringLiteral("stop_loss"),
            normalizeStopLoss(out.value(QStringLiteral("stop_loss")).toObject()));
    }
    return out;
}

bool indicatorCloseScopeAllowed(
    const QJsonObject &riskControls,
    const QStringList &indicators,
    bool allowMultiOverride) {
    if (allowMultiOverride) {
        return true;
    }
    const QJsonObject normalized = normalizeStrategyRiskControls(riskControls);
    if (coerceStrategyBool(
            normalized.value(QStringLiteral("allow_multi_indicator_close")),
            false)) {
        return true;
    }

    QSet<QString> normalizedIndicators;
    for (const QString &indicator : indicators) {
        const QString token = indicator.trimmed().toLower();
        if (!token.isEmpty() && token != QStringLiteral("generic")) {
            normalizedIndicators.insert(token);
        }
    }
    return normalizedIndicators.size() <= 1;
}

bool indicatorHoldReady(
    const QJsonObject &riskControls,
    const QString &symbol,
    const QString &interval,
    qint64 openedAtMs,
    qint64 nowMs,
    QString *reason,
    bool ignoreHold) {
    if (reason) {
        reason->clear();
    }
    const QJsonObject normalized = normalizeStrategyRiskControls(riskControls);
    if (ignoreHold
        && coerceStrategyBool(
            normalized.value(QStringLiteral("allow_close_ignoring_hold")),
            false)) {
        return true;
    }
    const double baseHoldSeconds = std::max(
        0.0,
        numberOf(normalized.value(QStringLiteral("indicator_min_position_hold_seconds"))).value_or(0.0));
    const qint64 holdBars = std::max<qint64>(
        0,
        intOf(normalized.value(QStringLiteral("indicator_min_position_hold_bars"))).value_or(0));

    const double intervalSeconds = std::max(1.0, pythonIndicatorIntervalSeconds(interval));
    const double effectiveHoldSeconds = std::max(
        baseHoldSeconds,
        intervalSeconds * static_cast<double>(holdBars));
    if (effectiveHoldSeconds <= 0.0) {
        return true;
    }
    if (openedAtMs <= 0 || nowMs <= 0) {
        if (reason) {
            *reason = QStringLiteral("%1@%2 hold timestamp is missing").arg(symbol.trimmed().toUpper(), interval);
        }
        return false;
    }
    const qint64 ageMs = std::max<qint64>(0, nowMs - openedAtMs);
    const qint64 requiredMs = static_cast<qint64>(std::ceil(effectiveHoldSeconds * 1000.0));
    if (ageMs >= requiredMs) {
        return true;
    }
    if (reason) {
        const double remainingSeconds = static_cast<double>(requiredMs - ageMs) / 1000.0;
        *reason = QStringLiteral("%1@%2 hold guard waiting %3s before indicator flip")
                      .arg(symbol.trimmed().toUpper(), interval, QString::number(remainingSeconds, 'f', 1));
    }
    return false;
}

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
    bool futures) {
    const QJsonObject normalized = normalizeStrategyRiskControls(riskControls);
    const QJsonObject stopLoss = normalized.value(QStringLiteral("stop_loss")).toObject();
    const QString mode = stopLoss.value(QStringLiteral("mode")).toString().trimmed().toLower();
    const QString scope = stopLoss.value(QStringLiteral("scope")).toString().trimmed().toLower();
    const bool enabled = coerceStrategyBool(stopLoss.value(QStringLiteral("enabled")));
    const double stopUsdt = std::max(0.0, numberOf(stopLoss.value(QStringLiteral("usdt"))).value_or(0.0));
    const double stopPercent = std::max(0.0, numberOf(stopLoss.value(QStringLiteral("percent"))).value_or(0.0));
    const bool applyUsdt = enabled && (mode == QStringLiteral("usdt") || mode == QStringLiteral("both"))
        && stopUsdt > 0.0;
    const bool applyPercent = enabled
        && (mode == QStringLiteral("percent") || mode == QStringLiteral("both"))
        && stopPercent > 0.0;
    const QString normalizedSide = side.trimmed().toUpper();
    const bool validSide = normalizedSide == QStringLiteral("LONG") || normalizedSide == QStringLiteral("SHORT");
    if (!futures || scope != QStringLiteral("per_trade") || (!applyUsdt && !applyPercent) || !validSide
        || !qIsFinite(quantity) || quantity <= 0.0 || !qIsFinite(entryPrice) || entryPrice <= 0.0
        || !qIsFinite(markPrice) || markPrice <= 0.0) {
        return {{QStringLiteral("triggered"), false}};
    }

    const double lossUsdt = normalizedSide == QStringLiteral("LONG")
        ? std::max(0.0, (entryPrice - markPrice) * quantity)
        : std::max(0.0, (markPrice - entryPrice) * quantity);
    if (!qIsFinite(lossUsdt)) {
        return {{QStringLiteral("triggered"), false}};
    }
    const double notional = entryPrice * quantity;
    const double priceLossPercent = notional > 0.0 ? (lossUsdt / notional) * 100.0 : 0.0;
    const double effectiveMargin = qIsFinite(marginUsdt) && marginUsdt > 0.0
        ? marginUsdt
        : (qIsFinite(leverage) && leverage > 0.0 ? notional / leverage : notional);
    const double marginLossPercent = effectiveMargin > 0.0 ? (lossUsdt / effectiveMargin) * 100.0 : 0.0;
    const bool triggered = (applyUsdt && lossUsdt >= stopUsdt)
        || (applyPercent && std::max(priceLossPercent, marginLossPercent) >= stopPercent);
    QJsonObject result{{QStringLiteral("triggered"), triggered}};
    if (!triggered) {
        return result;
    }
    result.insert(QStringLiteral("symbol"), symbol.trimmed().toUpper());
    result.insert(QStringLiteral("interval"), interval.trimmed());
    result.insert(QStringLiteral("side"), normalizedSide == QStringLiteral("LONG")
            ? QStringLiteral("BUY")
            : QStringLiteral("SELL"));
    result.insert(QStringLiteral("close_side"), normalizedSide == QStringLiteral("LONG")
            ? QStringLiteral("SELL")
            : QStringLiteral("BUY"));
    result.insert(QStringLiteral("position_side"), normalizedSide);
    result.insert(QStringLiteral("qty"), quantity);
    result.insert(QStringLiteral("reason"), QStringLiteral("per_trade_stop_loss"));
    result.insert(QStringLiteral("loss_usdt"), lossUsdt);
    result.insert(QStringLiteral("price_loss_percent"), priceLossPercent);
    result.insert(QStringLiteral("margin_loss_percent"), marginLossPercent);
    return result;
}

QJsonArray evaluateFuturesStopLoss(
    const QJsonObject &riskControls,
    const QJsonArray &positions,
    const QString &symbol,
    const QString &interval,
    double walletUsdt,
    bool futures) {
    QJsonArray directives;
    if (!futures) {
        return directives;
    }

    const QJsonObject normalized = normalizeStrategyRiskControls(riskControls);
    const QJsonObject stopLoss = normalized.value(QStringLiteral("stop_loss")).toObject();
    const QString mode = stopLoss.value(QStringLiteral("mode")).toString().trimmed().toLower();
    const QString scope = stopLoss.value(QStringLiteral("scope")).toString().trimmed().toLower();
    const bool enabled = coerceStrategyBool(stopLoss.value(QStringLiteral("enabled")));
    const double stopUsdt = std::max(0.0, numberOf(stopLoss.value(QStringLiteral("usdt"))).value_or(0.0));
    const double stopPercent = std::max(0.0, numberOf(stopLoss.value(QStringLiteral("percent"))).value_or(0.0));
    const bool applyUsdt = enabled
        && (mode == QStringLiteral("usdt") || mode == QStringLiteral("both"))
        && stopUsdt > 0.0;
    const bool applyPercent = enabled
        && (mode == QStringLiteral("percent") || mode == QStringLiteral("both"))
        && stopPercent > 0.0;
    if ((!applyUsdt && !applyPercent)
        || !QSet<QString>{QStringLiteral("per_trade"), QStringLiteral("cumulative"),
                          QStringLiteral("entire_account")}
               .contains(scope)) {
        return directives;
    }

    struct SideTotals {
        double quantity = 0.0;
        double lossUsdt = 0.0;
        double notional = 0.0;
        double marginUsdt = 0.0;
        bool dualSide = false;
    } longTotals, shortTotals;
    double totalUnrealized = 0.0;
    const QString targetSymbol = symbol.trimmed().toUpper();

    const auto numberField = [](const QJsonObject &object, const QStringList &keys) {
        for (const QString &key : keys) {
            if (auto value = numberOf(object.value(key))) {
                return *value;
            }
        }
        return 0.0;
    };
    const auto boolField = [](const QJsonObject &object, const QString &key, bool fallback = false) {
        const QJsonValue value = object.value(key);
        return value.isUndefined() ? fallback : coerceStrategyBool(value, fallback);
    };
    const auto shouldTrigger = [applyUsdt, applyPercent, stopUsdt, stopPercent](double lossUsdt, double lossPercent) {
        return (applyUsdt && lossUsdt >= stopUsdt)
            || (applyPercent && lossPercent >= stopPercent);
    };
    const auto appendDirective = [&directives, &interval](
                                    const QString &positionSymbol,
                                    const QString &sideLabel,
                                    const QString &closeSide,
                                    const QString &positionSide,
                                    double quantity,
                                    const QString &reason,
                                    double lossUsdt,
                                    double priceLossPercent,
                                    double marginLossPercent) {
        if (!qIsFinite(quantity) || quantity <= 0.0) {
            return;
        }
        QJsonObject directive{
            {QStringLiteral("symbol"), positionSymbol.trimmed().toUpper()},
            {QStringLiteral("interval"), interval.trimmed()},
            {QStringLiteral("side"), sideLabel},
            {QStringLiteral("close_side"), closeSide},
            {QStringLiteral("qty"), quantity},
            {QStringLiteral("reason"), reason},
            {QStringLiteral("loss_usdt"), lossUsdt},
            {QStringLiteral("price_loss_percent"), priceLossPercent},
            {QStringLiteral("margin_loss_percent"), marginLossPercent},
        };
        if (!positionSide.isEmpty()) {
            directive.insert(QStringLiteral("position_side"), positionSide);
        }
        directives.append(directive);
    };

    for (const QJsonValue &value : positions) {
        const QJsonObject position = value.toObject();
        const QString positionSymbol = position.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        const bool accountScope = scope == QStringLiteral("entire_account");
        if (!accountScope && positionSymbol != targetSymbol) {
            continue;
        }
        const QString side = position.value(QStringLiteral("side")).toString().trimmed().toUpper();
        if (side != QStringLiteral("LONG") && side != QStringLiteral("SHORT")) {
            continue;
        }
        const double quantity = std::fabs(numberField(position, {QStringLiteral("quantity"), QStringLiteral("qty"), QStringLiteral("position_amt")}));
        const double entryPrice = numberField(position, {QStringLiteral("entry_price"), QStringLiteral("entryPrice")});
        const double markPrice = numberField(position, {QStringLiteral("mark_price"), QStringLiteral("markPrice"), QStringLiteral("last_price")});
        if (!qIsFinite(quantity) || quantity <= 0.0 || !qIsFinite(entryPrice) || entryPrice <= 0.0
            || !qIsFinite(markPrice) || markPrice <= 0.0) {
            continue;
        }
        const double notional = entryPrice * quantity;
        const double lossUsdt = side == QStringLiteral("LONG")
            ? std::max(0.0, (entryPrice - markPrice) * quantity)
            : std::max(0.0, (markPrice - entryPrice) * quantity);
        const double unrealized = side == QStringLiteral("LONG")
            ? (markPrice - entryPrice) * quantity
            : (entryPrice - markPrice) * quantity;
        const double leverage = numberField(position, {QStringLiteral("leverage")});
        const double margin = std::max(0.0, numberField(position, {QStringLiteral("margin_usdt"), QStringLiteral("margin"), QStringLiteral("initial_margin")}));
        const double effectiveMargin = margin > 0.0
            ? margin
            : (leverage > 0.0 ? notional / leverage : notional);
        const double priceLossPercent = notional > 0.0 ? lossUsdt / notional * 100.0 : 0.0;
        const double marginLossPercent = effectiveMargin > 0.0 ? lossUsdt / effectiveMargin * 100.0 : 0.0;
        const bool dualSide = boolField(position, QStringLiteral("dual_side"), false);
        totalUnrealized += qIsFinite(unrealized) ? unrealized : 0.0;

        if (scope == QStringLiteral("per_trade")) {
            if (shouldTrigger(lossUsdt, std::max(priceLossPercent, marginLossPercent))) {
                appendDirective(
                    positionSymbol,
                    side,
                    side == QStringLiteral("LONG") ? QStringLiteral("SELL") : QStringLiteral("BUY"),
                    dualSide ? side : QString(),
                    quantity,
                    QStringLiteral("per_trade_stop_loss"),
                    lossUsdt,
                    priceLossPercent,
                    marginLossPercent);
            }
            continue;
        }

        SideTotals &totals = side == QStringLiteral("LONG") ? longTotals : shortTotals;
        totals.quantity += quantity;
        totals.lossUsdt += lossUsdt;
        totals.notional += notional;
        totals.marginUsdt += effectiveMargin;
        totals.dualSide = totals.dualSide || dualSide;
    }

    if (scope == QStringLiteral("entire_account")) {
        const double wallet = qIsFinite(walletUsdt) ? std::max(0.0, walletUsdt) : 0.0;
        const double lossPercent = totalUnrealized < 0.0 && wallet > 0.0
            ? std::fabs(totalUnrealized) / wallet * 100.0
            : 0.0;
        const bool triggered = (applyUsdt && totalUnrealized <= -stopUsdt)
            || (applyPercent && lossPercent >= stopPercent);
        if (triggered) {
            directives.append(QJsonObject{
                {QStringLiteral("symbol"), targetSymbol},
                {QStringLiteral("interval"), interval.trimmed()},
                {QStringLiteral("side"), QStringLiteral("ACCOUNT")},
                {QStringLiteral("close_side"), QStringLiteral("CLOSE_ALL")},
                {QStringLiteral("qty"), 0.0},
                {QStringLiteral("reason"), applyUsdt && totalUnrealized <= -stopUsdt
                        ? QStringLiteral("entire-account-usdt-limit")
                        : QStringLiteral("entire-account-percent-limit")},
                {QStringLiteral("loss_usdt"), std::fabs(totalUnrealized)},
                {QStringLiteral("price_loss_percent"), lossPercent},
                {QStringLiteral("margin_loss_percent"), 0.0},
            });
        }
        return directives;
    }

    const auto appendAggregate = [&appendDirective, &shouldTrigger, &symbol](const SideTotals &totals,
                                                                                const QString &side,
                                                                                const QString &reason) {
        if (totals.quantity <= 0.0) {
            return;
        }
        const double priceLossPercent = 0.0;
        const double marginLossPercent = totals.marginUsdt > 0.0
            ? totals.lossUsdt / totals.marginUsdt * 100.0
            : 0.0;
        if (!shouldTrigger(totals.lossUsdt, std::max(priceLossPercent, marginLossPercent))) {
            return;
        }
        const bool longSide = side == QStringLiteral("LONG");
        appendDirective(
            symbol,
            longSide ? QStringLiteral("BUY") : QStringLiteral("SELL"),
            longSide ? QStringLiteral("SELL") : QStringLiteral("BUY"),
            totals.dualSide ? side : QString(),
            totals.quantity,
            reason,
            totals.lossUsdt,
            priceLossPercent,
            marginLossPercent);
    };
    if (scope == QStringLiteral("cumulative")) {
        appendAggregate(longTotals, QStringLiteral("LONG"), QStringLiteral("cumulative_stop_loss"));
        appendAggregate(shortTotals, QStringLiteral("SHORT"), QStringLiteral("cumulative_stop_loss"));
    }
    return directives;
}

QJsonObject cleanBacktestResultPayload(const QJsonObject &payload) {
    QJsonObject out;
    for (auto it = payload.begin(); it != payload.end(); ++it) {
        if (!it.key().isEmpty() && !it.value().isNull() && !(it.value().isString() && it.value().toString().isEmpty())) {
            out.insert(it.key(), it.value());
        }
    }
    return out;
}

QString formatBacktestResultText(const QJsonObject &payload) {
    const QJsonObject metadata = cleanBacktestResultPayload(payload);
    if (metadata.isEmpty()) {
        return QStringLiteral("-");
    }
    QStringList pieces;
    if (metadata.contains(QStringLiteral("optimizer_rank"))) {
        pieces.append(QStringLiteral("Rank %1").arg(displayValue(metadata.value(QStringLiteral("optimizer_rank")))));
    }
    const QString roi = formatResultNumber(metadata.value(QStringLiteral("roi_percent")), QStringLiteral("%"));
    if (!roi.isEmpty()) pieces.append(QStringLiteral("ROI %1").arg(roi));
    QJsonValue dd = metadata.value(QStringLiteral("max_drawdown_percent"));
    if (dd.isUndefined() || dd.isNull()) dd = metadata.value(QStringLiteral("max_drawdown_during_percent"));
    const QString ddText = formatResultNumber(dd, QStringLiteral("%"));
    if (!ddText.isEmpty()) pieces.append(QStringLiteral("DD %1").arg(ddText));
    if (metadata.contains(QStringLiteral("trades"))) {
        pieces.append(QStringLiteral("Trades %1").arg(displayValue(metadata.value(QStringLiteral("trades")))));
    }
    if (!pieces.isEmpty()) {
        return pieces.join(QStringLiteral(" | "));
    }
    const QString source = textOf(metadata.value(QStringLiteral("source")));
    return source.isEmpty() ? QStringLiteral("Imported") : source;
}

QJsonObject buildCleanOverrideEntry(const QString &kind, const QJsonObject &entry) {
    const QString symbol = textOf(entry.value(QStringLiteral("symbol"))).toUpper();
    const QString interval = kind.trimmed().toLower() == QStringLiteral("backtest")
        ? canonicalizeBacktestInterval(entry.value(QStringLiteral("interval")))
        : textOf(entry.value(QStringLiteral("interval")));
    if (symbol.isEmpty() || interval.isEmpty()) {
        return {{QStringLiteral("entry"), QJsonValue()}, {QStringLiteral("indicator_values"), QJsonArray{}}, {QStringLiteral("controls"), QJsonObject{}}};
    }
    QJsonArray indicators;
    for (const QJsonValue &value : entry.value(QStringLiteral("indicators")).toArray()) {
        const QString text = textOf(value);
        if (!text.isEmpty()) {
            indicators.append(text);
        }
    }
    QJsonObject controls = normalizeStrategyControls(kind, entry.value(QStringLiteral("strategy_controls")).toObject());
    std::optional<qint64> leverage = intOf(controls.value(QStringLiteral("leverage")));
    if (!leverage.has_value()) leverage = intOf(entry.value(QStringLiteral("leverage")));
    if (leverage.has_value()) {
        leverage = std::max<qint64>(1, *leverage);
        controls.insert(QStringLiteral("leverage"), integerValue(*leverage));
    }
    QJsonObject clean{{QStringLiteral("symbol"), symbol}, {QStringLiteral("interval"), interval}};
    if (!indicators.isEmpty()) clean.insert(QStringLiteral("indicators"), indicators);
    const QString loop = normalizeLoop(entry.value(QStringLiteral("loop_interval_override")).isUndefined()
                                           ? controls.value(QStringLiteral("loop_interval_override"))
                                           : entry.value(QStringLiteral("loop_interval_override")));
    if (!loop.isEmpty()) clean.insert(QStringLiteral("loop_interval_override"), loop);
    if (!controls.isEmpty()) {
        if (controls.value(QStringLiteral("stop_loss")).isObject()) clean.insert(QStringLiteral("stop_loss"), controls.value(QStringLiteral("stop_loss")));
        if (!controls.value(QStringLiteral("connector_backend")).isUndefined()) clean.insert(QStringLiteral("connector_backend"), controls.value(QStringLiteral("connector_backend")));
        clean.insert(QStringLiteral("strategy_controls"), controls);
    }
    if (leverage.has_value()) clean.insert(QStringLiteral("leverage"), integerValue(*leverage));
    if (!clean.contains(QStringLiteral("stop_loss")) && entry.value(QStringLiteral("stop_loss")).isObject()) {
        clean.insert(QStringLiteral("stop_loss"), normalizeStopLoss(entry.value(QStringLiteral("stop_loss")).toObject()));
    }
    const QJsonObject backtest = cleanBacktestResultPayload(entry.value(QStringLiteral("backtest_result")).toObject());
    if (!backtest.isEmpty()) clean.insert(QStringLiteral("backtest_result"), backtest);
    return {
        {QStringLiteral("entry"), clean},
        {QStringLiteral("indicator_values"), indicators},
        {QStringLiteral("leverage"), leverage.has_value() ? integerValue(*leverage) : QJsonValue()},
        {QStringLiteral("controls"), controls},
    };
}

double nextNetworkBackoff(double previous) {
    const double safePrevious = std::isfinite(previous) && previous >= 0.0 ? previous : 0.0;
    return safePrevious <= 0.0 ? 5.0 : std::min(90.0, std::max(safePrevious * 1.5, 5.0));
}

QJsonObject buildWorkerLifecycleSnapshot(const StrategyWorkerLifecycleInput &input) {
    const bool stopped = input.stopRequested || input.globalShutdown || input.globalPause;
    QString phase = QStringLiteral("idle");
    if (input.globalShutdown) phase = QStringLiteral("shutdown");
    else if (input.globalPause) phase = QStringLiteral("paused");
    else if (input.stopRequested && input.threadAlive) phase = QStringLiteral("stopping");
    else if (input.threadAlive) phase = QStringLiteral("running");
    const QString effectiveInterval = input.loopIntervalOverride.trimmed().isEmpty() ? input.interval : input.loopIntervalOverride;
    const double seconds = pythonLoopIntervalSeconds(effectiveInterval);
    return {
        {QStringLiteral("symbol"), input.symbol.trimmed().toUpper()},
        {QStringLiteral("interval"), input.interval},
        {QStringLiteral("thread_name"), QStringLiteral("StrategyLoop-%1@%2 ").arg(input.symbol.trimmed().toUpper(), effectiveInterval)},
        {QStringLiteral("stopped"), stopped},
        {QStringLiteral("is_alive"), input.threadAlive},
        {QStringLiteral("lifecycle_phase"), phase},
        {QStringLiteral("active_engine_count"), input.activeEngineCount},
        {QStringLiteral("offline_backoff"), std::isfinite(input.offlineBackoff) && input.offlineBackoff >= 0.0
            ? input.offlineBackoff
            : 0.0},
        {QStringLiteral("next_network_backoff"), nextNetworkBackoff(input.offlineBackoff)},
        {QStringLiteral("emergency_close_triggered"), input.emergencyCloseTriggered},
        {QStringLiteral("loop_interval_seconds"), seconds},
        {QStringLiteral("phase_span_seconds"), std::max(2.0, std::min(seconds * 0.35, 10.0))},
        {QStringLiteral("execution_owner"), QStringLiteral("native-cpp")},
        {QStringLiteral("native_trading_execution_enabled"), true},
        {QStringLiteral("native_trading_execution_scope"), QStringLiteral("binance-spot-usds-and-coin-futures")},
    };
}

} // namespace NativeStrategyRuntime
