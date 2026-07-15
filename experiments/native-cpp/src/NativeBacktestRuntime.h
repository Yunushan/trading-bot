#pragma once

#include "NativeIndicatorRuntime.h"

#include <QJsonObject>
#include <QString>
#include <QStringList>

#include <functional>

namespace NativeBacktestRuntime {

struct Request {
    QString symbol;
    QString interval;
    NativeIndicatorRuntime::ConfigMap indicators;
    QString logic = QStringLiteral("AND");
    QString side = QStringLiteral("BOTH");
    double capital = 1000.0;
    double positionPct = 1.0;
    QString positionPctUnits;
    double leverage = 1.0;
    QString marginMode = QStringLiteral("Isolated");
    QString positionMode = QStringLiteral("Hedge");
    QString assetsMode = QStringLiteral("Single-Asset");
    QString accountMode = QStringLiteral("Classic Trading");
    QString mddLogic = QStringLiteral("per_trade");
    bool stopLossEnabled = false;
    QString stopLossMode = QStringLiteral("usdt");
    double stopLossUsdt = 0.0;
    double stopLossPercent = 0.0;
    QString stopLossScope = QStringLiteral("per_trade");
};

struct Result {
    bool ok = false;
    QString error;
    QString symbol;
    QString interval;
    QStringList indicatorKeys;
    int trades = 0;
    double roiValue = 0.0;
    double roiPercent = 0.0;
    double finalEquity = 0.0;
    double maxDrawdownValue = 0.0;
    double maxDrawdownPercent = 0.0;
    double maxDrawdownDuringValue = 0.0;
    double maxDrawdownDuringPercent = 0.0;
    double maxDrawdownResultValue = 0.0;
    double maxDrawdownResultPercent = 0.0;
    QString logic;
    double leverage = 1.0;
    QString mddLogic;
    QString side;
    double capital = 0.0;
    double positionPct = 0.0;
    QString positionPctUnits = QStringLiteral("fraction");
    bool stopLossEnabled = false;
    QString stopLossMode;
    double stopLossUsdt = 0.0;
    double stopLossPercent = 0.0;
    QString stopLossScope;
    QString marginMode;
    QString positionMode;
    QString assetsMode;
    QString accountMode;

    QJsonObject toJson() const;
};

Result run(
    const QVector<NativeIndicatorRuntime::Candle> &candles,
    const Request &request,
    const std::function<bool()> &shouldStop = {});

} // namespace NativeBacktestRuntime
