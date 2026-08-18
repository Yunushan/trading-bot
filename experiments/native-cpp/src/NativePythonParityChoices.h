#pragma once

#include "generated/PythonParityContract.h"

#include <QString>
#include <QStringList>

#include <array>
#include <string_view>

namespace NativePythonParity {

inline QString fromStringView(std::string_view value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

inline QString normalizeConfigChoiceToken(QString value) {
    value = value.trimmed().toLower();
    value.replace(QLatin1Char('-'), QLatin1Char('_'));
    value.replace(QLatin1Char(' '), QLatin1Char('_'));
    return value;
}

template <std::size_t N>
QString defaultConfigChoice(
    const std::array<PythonParityContract::PythonConfigChoice, N> &choices,
    const QString &fallback = {}) {
    if (!choices.empty()) {
        return fromStringView(choices.front().value);
    }
    return fallback;
}

template <std::size_t N>
QString canonicalConfigChoice(
    const QString &value,
    const std::array<PythonParityContract::PythonConfigChoice, N> &choices,
    const QString &fallback = {}) {
    const QString raw = normalizeConfigChoiceToken(value);
    if (raw.isEmpty()) {
        return fallback;
    }
    for (const auto &choice : choices) {
        const QString key = normalizeConfigChoiceToken(fromStringView(choice.key));
        const QString canonical = normalizeConfigChoiceToken(fromStringView(choice.value));
        if (raw.compare(key, Qt::CaseInsensitive) == 0
            || raw.compare(canonical, Qt::CaseInsensitive) == 0) {
            return fromStringView(choice.value);
        }
    }
    return fallback;
}

template <std::size_t N>
QStringList canonicalConfigChoiceValues(
    const std::array<PythonParityContract::PythonConfigChoice, N> &choices) {
    QStringList values;
    for (const auto &choice : choices) {
        const QString canonical = fromStringView(choice.value);
        if (!values.contains(canonical)) {
            values.append(canonical);
        }
    }
    return values;
}

} // namespace NativePythonParity
