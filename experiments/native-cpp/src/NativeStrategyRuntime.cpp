#include "NativeStrategyRuntime.h"

#include "NativeExchangeConnectors.h"
#include "generated/PythonParityContract.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QSet>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
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

QString normalizeStopLossMode(const QJsonValue &value) {
    return normalizePythonUiOptionKey(value, PythonParityContract::kPythonStopLossModes, QStringLiteral("usdt"));
}

QString normalizeStopLossScope(const QJsonValue &value) {
    return normalizePythonUiOptionKey(value, PythonParityContract::kPythonStopLossScopes, QStringLiteral("per_trade"));
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
    return std::isfinite(value) ? std::optional<double>(value) : std::nullopt;
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
    const std::optional<double> buy =
        cfg.buyValue.has_value() ? cfg.buyValue : defaultBuy;
    const std::optional<double> sell =
        cfg.sellValue.has_value() ? cfg.sellValue : defaultSell;
    if (!buy.has_value() || !sell.has_value()) {
        return;
    }
    const int decimals = decimalsFor(pattern);
    const bool buyGe = compare == Compare::BuyGeSellLe || compare == Compare::BuyGeSellLeDefaults;
    if (buyGe) {
        if (buyAllowed && value >= *buy) {
            addAction(key, QStringLiteral("BUY"), QStringLiteral("%1 >= %2 -> BUY").arg(label, fixed(*buy, decimals)),
                      signal, descriptions, sources, actions);
        } else if (sellAllowed && value <= *sell) {
            addAction(key, QStringLiteral("SELL"), QStringLiteral("%1 <= %2 -> SELL").arg(label, fixed(*sell, decimals)),
                      signal, descriptions, sources, actions);
        }
    } else if (buyAllowed && value <= *buy) {
        addAction(key, QStringLiteral("BUY"), QStringLiteral("%1 <= %2 -> BUY").arg(label, fixed(*buy, decimals)),
                  signal, descriptions, sources, actions);
    } else if (sellAllowed && value >= *sell) {
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
    const QString text = textOf(value).toLower();
    if (QStringList{QStringLiteral("percent"), QStringLiteral("%"), QStringLiteral("perc"), QStringLiteral("percentage")}.contains(text)) {
        return QStringLiteral("percent");
    }
    if (QStringList{QStringLiteral("fraction"), QStringLiteral("decimal"), QStringLiteral("ratio")}.contains(text)) {
        return QStringLiteral("fraction");
    }
    return {};
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
    const QString mode = normalizeStopLossMode(input.value(QStringLiteral("mode")));
    const QString scope = normalizeStopLossScope(input.value(QStringLiteral("scope")));
    return {
        {QStringLiteral("enabled"), NativeStrategyRuntime::coerceStrategyBool(input.value(QStringLiteral("enabled")))},
        {QStringLiteral("mode"), mode},
        {QStringLiteral("scope"), scope},
        {QStringLiteral("usdt"), std::max(0.0, numberOf(input.value(QStringLiteral("usdt"))).value_or(0.0))},
        {QStringLiteral("percent"), std::max(0.0, numberOf(input.value(QStringLiteral("percent"))).value_or(0.0))},
    };
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
    if (raw.endsWith(QLatin1Char('M')) && raw.left(raw.size() - 1).toInt() > 0) {
        return QStringLiteral("%1mo").arg(raw.left(raw.size() - 1).toInt());
    }
    QString compact;
    for (const QChar ch : raw.toLower()) {
        if (!ch.isSpace()) {
            compact.append(ch);
        }
    }
    int idx = 0;
    while (idx < compact.size() && (compact.at(idx).isDigit() || compact.at(idx) == QLatin1Char('.'))) {
        ++idx;
    }
    bool ok = false;
    const double amount = compact.left(idx).toDouble(&ok);
    if (!ok) {
        return compact;
    }
    const QString unitRaw = compact.mid(idx);
    if (QStringList{QStringLiteral("mo"), QStringLiteral("mon"), QStringLiteral("mons"), QStringLiteral("month"), QStringLiteral("months")}.contains(unitRaw)) {
        return QStringLiteral("%1mo").arg(formatAmount(amount));
    }
    QString unit = unitRaw;
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
    }
    const QMap<double, QString> canonical{
        {60.0, QStringLiteral("1m")},
        {300.0, QStringLiteral("5m")},
        {600.0, QStringLiteral("10m")},
        {900.0, QStringLiteral("15m")},
        {1800.0, QStringLiteral("30m")},
        {3600.0, QStringLiteral("1h")},
        {14400.0, QStringLiteral("4h")},
        {86400.0, QStringLiteral("1d")},
        {604800.0, QStringLiteral("1w")},
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
    QString compact;
    for (const QChar ch : interval.toLower()) {
        if (!ch.isSpace()) {
            compact.append(ch);
        }
    }
    int idx = 0;
    while (idx < compact.size() && (compact.at(idx).isDigit() || compact.at(idx) == QLatin1Char('.'))) {
        ++idx;
    }
    bool ok = false;
    const double amount = compact.left(idx).toDouble(&ok);
    if (!ok) {
        return 60.0;
    }
    const QString unit = compact.mid(idx);
    if (unit == QStringLiteral("s")) return amount;
    if (unit == QStringLiteral("h")) return amount * 3600.0;
    if (unit == QStringLiteral("d")) return amount * 86400.0;
    if (unit == QStringLiteral("w")) return amount * 7.0 * 86400.0;
    return amount * 60.0;
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
        return value.toDouble() != 0.0;
    }
    const QString lowered = value.toString().trimmed().toLower();
    if (lowered.isEmpty()) {
        return defaultValue;
    }
    if (QStringList{QStringLiteral("0"), QStringLiteral("false"), QStringLiteral("no"), QStringLiteral("off"), QStringLiteral("n")}.contains(lowered)) {
        return false;
    }
    if (QStringList{QStringLiteral("1"), QStringLiteral("true"), QStringLiteral("yes"), QStringLiteral("on"), QStringLiteral("y")}.contains(lowered)) {
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
            descriptions.append(QStringLiteral("RSI=%1").arg(fixed(value, 2)));
            const auto cfg = rule(input, QStringLiteral("rsi"));
            const double buy = cfg.buyValue.value_or(30.0);
            const double sell = cfg.sellValue.value_or(70.0);
            if (buyAllowed && value <= buy) {
                addAction(QStringLiteral("rsi"), QStringLiteral("BUY"), QStringLiteral("RSI <= %1 -> BUY").arg(fixed(buy, 2)), signal, descriptions, sources, actions);
            } else if (sellAllowed && value >= sell) {
                addAction(QStringLiteral("rsi"), QStringLiteral("SELL"), QStringLiteral("RSI >= %1 -> SELL").arg(fixed(sell, 2)), signal, descriptions, sources, actions);
            }
        }
    }
    threshold(input, QStringLiteral("natr"), QStringLiteral("NATR"), QStringLiteral("{:.4}"), Compare::BuyGeSellLe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("rvol"), QStringLiteral("RVOL"), QStringLiteral("{:.4}"), Compare::BuyGeSellLe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("cci"), QStringLiteral("CCI"), QStringLiteral("{:.2}"), Compare::BuyLeSellGeDefaults, -100.0, 100.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("bbw"), QStringLiteral("BBW"), QStringLiteral("{:.4}"), Compare::BuyGeSellLe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("roc"), QStringLiteral("ROC"), QStringLiteral("{:.2}"), Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("trix"), QStringLiteral("TRIX"), QStringLiteral("{:.4}"), Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("ao"), QStringLiteral("AO"), QStringLiteral("{:.4}"), Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("mfi"), QStringLiteral("MFI"), QStringLiteral("{:.2}"), Compare::BuyLeSellGeDefaults, 20.0, 80.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    threshold(input, QStringLiteral("chop"), QStringLiteral("CHOP"), QStringLiteral("{:.4}"), Compare::BuyLeSellGe, std::nullopt, std::nullopt, buyAllowed, sellAllowed, signal, descriptions, sources, actions);

    if (enabled(input, QStringLiteral("ppo"))) {
        const double hist = indicatorValues(input, QStringLiteral("ppo_hist")).has_value()
            ? std::get<2>(*indicatorValues(input, QStringLiteral("ppo_hist"))) : std::numeric_limits<double>::quiet_NaN();
        const double line = indicatorValues(input, QStringLiteral("ppo")).has_value()
            ? std::get<2>(*indicatorValues(input, QStringLiteral("ppo"))) : std::numeric_limits<double>::quiet_NaN();
        const double ppoSignal = indicatorValues(input, QStringLiteral("ppo_signal")).has_value()
            ? std::get<2>(*indicatorValues(input, QStringLiteral("ppo_signal"))) : std::numeric_limits<double>::quiet_NaN();
        descriptions.append(QStringLiteral("PPO=%1,PPO_signal=%2,hist=%3").arg(fixed(line, 4), fixed(ppoSignal, 4), fixed(hist, 4)));
        thresholdExisting(input, QStringLiteral("ppo"), QStringLiteral("PPO hist"), QStringLiteral("{:.4}"), hist, Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    }
    if (enabled(input, QStringLiteral("kst"))) {
        const double spread = indicatorValues(input, QStringLiteral("kst_hist")).has_value()
            ? std::get<2>(*indicatorValues(input, QStringLiteral("kst_hist"))) : std::numeric_limits<double>::quiet_NaN();
        const double line = indicatorValues(input, QStringLiteral("kst")).has_value()
            ? std::get<2>(*indicatorValues(input, QStringLiteral("kst"))) : std::numeric_limits<double>::quiet_NaN();
        const double kstSignal = indicatorValues(input, QStringLiteral("kst_signal")).has_value()
            ? std::get<2>(*indicatorValues(input, QStringLiteral("kst_signal"))) : std::numeric_limits<double>::quiet_NaN();
        descriptions.append(QStringLiteral("KST=%1,KST_signal=%2,spread=%3").arg(fixed(line, 4), fixed(kstSignal, 4), fixed(spread, 4)));
        thresholdExisting(input, QStringLiteral("kst"), QStringLiteral("KST spread"), QStringLiteral("{:.4}"), spread, Compare::BuyGeSellLeDefaults, 0.0, 0.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
    }
    if (enabled(input, QStringLiteral("aroon"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("aroon"))) {
            const double value = std::get<2>(*values);
            const double up = indicatorValues(input, QStringLiteral("aroon_up")).has_value() ? std::get<2>(*indicatorValues(input, QStringLiteral("aroon_up"))) : std::numeric_limits<double>::quiet_NaN();
            const double down = indicatorValues(input, QStringLiteral("aroon_down")).has_value() ? std::get<2>(*indicatorValues(input, QStringLiteral("aroon_down"))) : std::numeric_limits<double>::quiet_NaN();
            descriptions.append(QStringLiteral("Aroon=%1 (up=%2, down=%3)").arg(fixed(value, 2), fixed(up, 2), fixed(down, 2)));
            thresholdExisting(input, QStringLiteral("aroon"), QStringLiteral("Aroon"), QStringLiteral("{:.2}"), value, Compare::BuyGeSellLeDefaults, 50.0, -50.0, buyAllowed, sellAllowed, signal, descriptions, sources, actions);
        }
    }
    if (enabled(input, QStringLiteral("atr"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("atr"))) {
            descriptions.append(QStringLiteral("ATR=%1").arg(fixed(std::get<2>(*values), 8)));
        }
    }
    if (enabled(input, QStringLiteral("vwap"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("vwap"))) {
            const double value = std::get<2>(*values);
            descriptions.append(QStringLiteral("VWAP=%1 (prev=%2, live=%3, close %4)")
                                    .arg(fixed(value, 8), fixed(std::get<0>(*values), 8), fixed(std::get<1>(*values), 8),
                                         sigClose >= value ? QStringLiteral("above") : QStringLiteral("below")));
        }
    }
    if (enabled(input, QStringLiteral("cmf"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("cmf"))) {
            const double value = std::get<2>(*values);
            const QString flow = value > 0.0 ? QStringLiteral("accumulation") : value < 0.0 ? QStringLiteral("distribution") : QStringLiteral("neutral");
            descriptions.append(QStringLiteral("CMF=%1 (prev=%2, live=%3, %4)").arg(fixed(value, 4), fixed(std::get<0>(*values), 4), fixed(std::get<1>(*values), 4), flow));
        }
    }
    if (enabled(input, QStringLiteral("obv"))) {
        if (const auto values = indicatorValues(input, QStringLiteral("obv"))) {
            const double prev = std::get<0>(*values);
            const double live = std::get<1>(*values);
            const QString trend = live > prev ? QStringLiteral("rising") : live < prev ? QStringLiteral("falling") : QStringLiteral("flat");
            descriptions.append(QStringLiteral("OBV=%1 (prev=%2, live=%3, %4)").arg(fixed(std::get<2>(*values), 2), fixed(prev, 2), fixed(live, 2), trend));
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
    if (descriptions.isEmpty()) {
        descriptions.append(QStringLiteral("No triggers evaluated"));
    }
    QJsonArray sourceArray;
    QSet<QString> seen;
    for (const QString &source : sources) {
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

QJsonObject normalizeStrategyControls(const QString &kind, const QJsonObject &controls) {
    QJsonObject out;
    const QString kindNorm = kind.trimmed().toLower();
    if (kindNorm == QStringLiteral("runtime")) {
        const QString side = canonicalSide(controls.value(QStringLiteral("side")));
        if (!side.isEmpty()) out.insert(QStringLiteral("side"), side);
        if (auto value = numberOf(controls.value(QStringLiteral("position_pct")))) out.insert(QStringLiteral("position_pct"), *value);
        const QString units = normalizePositionPctUnits(controls.value(QStringLiteral("position_pct_units")).isUndefined()
                                                            ? controls.value(QStringLiteral("_position_pct_units"))
                                                            : controls.value(QStringLiteral("position_pct_units")));
        if (!units.isEmpty()) out.insert(QStringLiteral("position_pct_units"), units);
        if (auto lev = intOf(controls.value(QStringLiteral("leverage"))); lev && *lev >= 1) out.insert(QStringLiteral("leverage"), integerValue(*lev));
        const QString loop = normalizeLoop(controls.value(QStringLiteral("loop_interval_override")));
        if (!loop.isEmpty()) out.insert(QStringLiteral("loop_interval_override"), loop);
        if (!controls.value(QStringLiteral("add_only")).isUndefined()) out.insert(QStringLiteral("add_only"), coerceStrategyBool(controls.value(QStringLiteral("add_only"))));
        const QString account = normalizeAccountMode(controls.value(QStringLiteral("account_mode")));
        if (!account.isEmpty()) out.insert(QStringLiteral("account_mode"), account);
    } else if (kindNorm == QStringLiteral("backtest")) {
        const QString logic = normalizeSignalLogic(controls.value(QStringLiteral("logic")));
        if (!logic.isEmpty()) out.insert(QStringLiteral("logic"), logic);
        if (auto value = numberOf(controls.value(QStringLiteral("capital")))) out.insert(QStringLiteral("capital"), *value);
        if (auto value = numberOf(controls.value(QStringLiteral("position_pct")))) out.insert(QStringLiteral("position_pct"), *value);
        const QString units = normalizePositionPctUnits(controls.value(QStringLiteral("position_pct_units")));
        if (!units.isEmpty()) out.insert(QStringLiteral("position_pct_units"), units);
        const QString side = canonicalSide(controls.value(QStringLiteral("side")));
        if (!side.isEmpty()) out.insert(QStringLiteral("side"), side);
        if (!textOf(controls.value(QStringLiteral("margin_mode"))).isEmpty()) out.insert(QStringLiteral("margin_mode"), textOf(controls.value(QStringLiteral("margin_mode"))));
        if (!textOf(controls.value(QStringLiteral("position_mode"))).isEmpty()) out.insert(QStringLiteral("position_mode"), textOf(controls.value(QStringLiteral("position_mode"))));
        const QString assets = normalizeAssetsMode(controls.value(QStringLiteral("assets_mode")));
        if (!assets.isEmpty()) out.insert(QStringLiteral("assets_mode"), assets);
        const QString account = normalizeAccountMode(controls.value(QStringLiteral("account_mode")));
        if (!account.isEmpty()) out.insert(QStringLiteral("account_mode"), account);
        if (auto lev = intOf(controls.value(QStringLiteral("leverage")))) out.insert(QStringLiteral("leverage"), integerValue(*lev));
    }
    if (controls.value(QStringLiteral("stop_loss")).isObject()) out.insert(QStringLiteral("stop_loss"), normalizeStopLoss(controls.value(QStringLiteral("stop_loss")).toObject()));
    const QString backend = textOf(controls.value(QStringLiteral("connector_backend")));
    if (!backend.isEmpty()) out.insert(QStringLiteral("connector_backend"), NativeExchangeConnectors::normalizeConnectorBackend(backend));
    return out;
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
        ? normalizeBacktestInterval(entry.value(QStringLiteral("interval")))
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
    return previous <= 0.0 ? 5.0 : std::min(90.0, std::max(previous * 1.5, 5.0));
}

QJsonObject buildWorkerLifecycleSnapshot(const StrategyWorkerLifecycleInput &input) {
    const bool stopped = input.stopRequested || input.globalShutdown || input.globalPause;
    QString phase = QStringLiteral("idle");
    if (input.globalShutdown) phase = QStringLiteral("shutdown");
    else if (input.globalPause) phase = QStringLiteral("paused");
    else if (input.stopRequested && input.threadAlive) phase = QStringLiteral("stopping");
    else if (input.threadAlive) phase = QStringLiteral("running");
    const QString effectiveInterval = input.loopIntervalOverride.trimmed().isEmpty() ? input.interval : input.loopIntervalOverride;
    const double seconds = intervalSeconds(effectiveInterval);
    return {
        {QStringLiteral("symbol"), input.symbol.trimmed().toUpper()},
        {QStringLiteral("interval"), input.interval},
        {QStringLiteral("thread_name"), QStringLiteral("StrategyLoop-%1@%2 ").arg(input.symbol.trimmed().toUpper(), effectiveInterval)},
        {QStringLiteral("stopped"), stopped},
        {QStringLiteral("is_alive"), input.threadAlive},
        {QStringLiteral("lifecycle_phase"), phase},
        {QStringLiteral("active_engine_count"), input.activeEngineCount},
        {QStringLiteral("offline_backoff"), std::max(0.0, input.offlineBackoff)},
        {QStringLiteral("next_network_backoff"), nextNetworkBackoff(input.offlineBackoff)},
        {QStringLiteral("emergency_close_triggered"), input.emergencyCloseTriggered},
        {QStringLiteral("loop_interval_seconds"), seconds},
        {QStringLiteral("phase_span_seconds"), std::max(2.0, std::min(seconds * 0.35, 10.0))},
        {QStringLiteral("execution_owner"), QStringLiteral("python-service")},
        {QStringLiteral("native_trading_execution_enabled"), false},
    };
}

} // namespace NativeStrategyRuntime
