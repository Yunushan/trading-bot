#pragma once

#include <QJsonObject>
#include <QMap>
#include <QStringList>
#include <QVector>

namespace NativeIndicatorRuntime {

struct Candle {
    double open = 0.0;
    double high = 0.0;
    double low = 0.0;
    double close = 0.0;
    double volume = 0.0;
};

using ConfigMap = QMap<QString, QJsonObject>;
using Series = QVector<double>;
using SeriesMap = QMap<QString, Series>;

QStringList computedIndicatorKeys();
QStringList unsupportedEnabledIndicatorKeys(const ConfigMap &configs);
SeriesMap computeConfiguredSeries(const QVector<Candle> &candles, const ConfigMap &configs);

} // namespace NativeIndicatorRuntime
