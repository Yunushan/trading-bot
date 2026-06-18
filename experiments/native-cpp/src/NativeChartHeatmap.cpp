#include "NativeChartHeatmap.h"

#include "generated/PythonParityContract.h"

#include <QJsonValue>
#include <QRegularExpression>
#include <QSet>

namespace {

constexpr auto kLightweightLocalAsset = "Languages/Python/app/assets/lightweight-charts.standalone.production.js";
constexpr auto kSafeModeStatus = "Web charts disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable.";
constexpr auto kSafeTradingViewExternalStatus = "TradingView opened in your browser. Set BOT_SAFE_CHART_TAB=0 to embed.";
constexpr auto kSafeTradingViewBlockedStatus = "TradingView embed disabled. Set BOT_SAFE_CHART_TAB=0 to embed.";

QString parityString(std::string_view value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

QString normalizeMinuteInterval(qint64 minutes) {
    if (minutes > 0 && minutes % 60 == 0) {
        return QStringLiteral("%1h").arg(minutes / 60);
    }
    if (minutes > 0) {
        return QStringLiteral("%1m").arg(minutes);
    }
    return {};
}

qint64 digitsOrOne(const QString &value) {
    QString digits;
    for (const QChar ch : value) {
        if (ch.isDigit()) {
            digits.append(ch);
        }
    }
    bool ok = false;
    const qint64 parsed = digits.toLongLong(&ok);
    return ok && parsed > 0 ? parsed : 1;
}

QString parseIntervalToTradingViewCode(const QString &key) {
    bool ok = false;
    if (key.endsWith(QLatin1Char('m'))) {
        const double minutes = key.left(key.size() - 1).toDouble(&ok);
        return ok && minutes > 0.0 ? QString::number(static_cast<qint64>(minutes)) : QString();
    }
    if (key.endsWith(QLatin1Char('h'))) {
        const double hours = key.left(key.size() - 1).toDouble(&ok);
        return ok && hours > 0.0 ? QString::number(static_cast<qint64>(hours * 60.0)) : QString();
    }
    if (key.endsWith(QLatin1Char('d'))) {
        const double days = key.left(key.size() - 1).toDouble(&ok);
        return ok && days > 0.0 ? QStringLiteral("%1D").arg(static_cast<qint64>(days)) : QString();
    }
    if (key.endsWith(QLatin1Char('w'))) {
        const double weeks = key.left(key.size() - 1).toDouble(&ok);
        return ok && weeks > 0.0 ? QStringLiteral("%1W").arg(static_cast<qint64>(weeks)) : QString();
    }
    if (key.endsWith(QStringLiteral("mo"))
        || key.endsWith(QStringLiteral("month"))
        || key.endsWith(QStringLiteral("months"))) {
        return QStringLiteral("%1M").arg(digitsOrOne(key));
    }
    if (key.endsWith(QLatin1Char('y'))
        || key.endsWith(QStringLiteral("year"))
        || key.endsWith(QStringLiteral("years"))) {
        return QStringLiteral("%1M").arg(digitsOrOne(key) * 12);
    }
    return {};
}

} // namespace

namespace NativeChartHeatmap {

QString normalizeChartMarket(const QString &value) {
    const QString text = value.trimmed().toLower();
    return text.startsWith(QStringLiteral("spot")) ? QStringLiteral("Spot") : QStringLiteral("Futures");
}

QString normalizeChartIntervalKey(const QString &value) {
    const QString source = value.trimmed();
    if (source.isEmpty()) {
        return {};
    }
    if (source.endsWith(QLatin1Char('M'))) {
        const QString digits = source.left(source.size() - 1);
        bool ok = false;
        const qint64 months = digits.toLongLong(&ok);
        if (ok && months > 0) {
            return QStringLiteral("%1mo").arg(months);
        }
    }
    QString collapsed = source.toLower();
    collapsed.replace(QStringLiteral("minutes"), QStringLiteral("m"));
    collapsed.replace(QStringLiteral("minute"), QStringLiteral("m"));
    collapsed.replace(QStringLiteral("mins"), QStringLiteral("m"));
    collapsed.replace(QStringLiteral("min"), QStringLiteral("m"));
    collapsed.replace(QStringLiteral("hours"), QStringLiteral("h"));
    collapsed.replace(QStringLiteral("hour"), QStringLiteral("h"));
    collapsed.replace(QStringLiteral("days"), QStringLiteral("d"));
    collapsed.replace(QStringLiteral("day"), QStringLiteral("d"));
    collapsed.replace(QStringLiteral("weeks"), QStringLiteral("w"));
    collapsed.replace(QStringLiteral("week"), QStringLiteral("w"));
    collapsed.remove(QLatin1Char(' '));

    static const QRegularExpression digitsOnly(QStringLiteral("^\\d+$"));
    const QRegularExpressionMatch digitsMatch = digitsOnly.match(collapsed);
    if (digitsMatch.hasMatch()) {
        return normalizeMinuteInterval(collapsed.toLongLong());
    }
    static const QRegularExpression minutesOnly(QStringLiteral("^(\\d+)m$"));
    const QRegularExpressionMatch minutesMatch = minutesOnly.match(collapsed);
    if (minutesMatch.hasMatch()) {
        return normalizeMinuteInterval(minutesMatch.captured(1).toLongLong());
    }
    if (collapsed == QStringLiteral("1month") || collapsed == QStringLiteral("1months")) {
        return QStringLiteral("1mo");
    }
    return collapsed;
}

QString canonicalizeChartInterval(const QString &value) {
    const QString normalized = normalizeChartIntervalKey(value);
    return normalized == QStringLiteral("1mo") ? QStringLiteral("1M") : normalized;
}

QString mapTradingViewInterval(const QString &value) {
    const QString key = normalizeChartIntervalKey(value);
    if (key.isEmpty()) {
        return {};
    }
    for (const auto &item : PythonParityContract::kPythonTradingViewIntervalMap) {
        if (parityString(item.interval).compare(key, Qt::CaseInsensitive) == 0) {
            return parityString(item.code);
        }
    }
    return parseIntervalToTradingViewCode(key);
}

QString futuresDisplaySymbol(const QString &symbol) {
    const QString sym = symbol.trimmed().toUpper();
    if (sym.isEmpty() || sym.endsWith(QStringLiteral(".P"))) {
        return sym;
    }
    if (sym.endsWith(QStringLiteral("USDT")) && !sym.endsWith(QStringLiteral("BUSD"))) {
        return sym + QStringLiteral(".P");
    }
    return sym;
}

QString resolveChartSymbolForApi(
    const QString &symbol,
    const QString &market,
    const QJsonObject &aliasMap) {
    const QString sym = symbol.trimmed().toUpper();
    if (normalizeChartMarket(market) == QStringLiteral("Futures")) {
        for (auto it = aliasMap.constBegin(); it != aliasMap.constEnd(); ++it) {
            if (it.key().trimmed().compare(sym, Qt::CaseInsensitive) == 0) {
                return it.value().toString().trimmed().toUpper();
            }
        }
        if (sym.endsWith(QStringLiteral(".P"))) {
            return sym.left(sym.size() - 2);
        }
    }
    return sym;
}

QString formatTradingViewSymbol(const QString &symbol, const QString &accountHint) {
    const QString raw = QString(symbol).trimmed().toUpper().remove(QLatin1Char('/'));
    if (raw.contains(QLatin1Char(':'))) {
        return raw;
    }
    const QString account = accountHint.trimmed().toLower();
    const QString prefix = account.contains(QStringLiteral("bybit")) ? QStringLiteral("BYBIT:") : QStringLiteral("BINANCE:");
    return prefix + raw;
}

QString buildTradingViewUrl(const QString &symbol, const QString &intervalCode) {
    return QStringLiteral("https://www.tradingview.com/chart/?symbol=%1&interval=%2")
        .arg(symbol.trimmed(), intervalCode.trimmed());
}

QJsonObject buildChartStatePayload(
    const QString &market,
    const QString &symbol,
    const QString &interval,
    const QString &viewMode,
    bool autoFollow) {
    const QString marketNorm = normalizeChartMarket(market);
    const QString displaySymbol = marketNorm == QStringLiteral("Futures")
        ? futuresDisplaySymbol(symbol)
        : symbol.trimmed().toUpper();
    const QString apiSymbol = resolveChartSymbolForApi(displaySymbol, marketNorm);
    const QString intervalNorm = canonicalizeChartInterval(interval);
    QJsonArray defaults;
    for (const auto &item : PythonParityContract::kPythonDefaultChartSymbols) {
        defaults.append(parityString(item));
    }
    return {
        {QStringLiteral("market"), marketNorm},
        {QStringLiteral("symbol"), displaySymbol},
        {QStringLiteral("api_symbol"), apiSymbol},
        {QStringLiteral("display_symbol"), displaySymbol},
        {QStringLiteral("interval"), intervalNorm},
        {QStringLiteral("tradingview_interval"), mapTradingViewInterval(intervalNorm)},
        {QStringLiteral("view_mode"), viewMode.trimmed().toLower()},
        {QStringLiteral("tradingview_symbol"), formatTradingViewSymbol(apiSymbol, QStringLiteral("futures"))},
        {QStringLiteral("auto_follow"), autoFollow},
        {QStringLiteral("default_symbols"), defaults},
    };
}

QJsonObject buildLightweightPayload(
    const QJsonArray &candles,
    const QStringList &enabledIndicators,
    const QString &themeName,
    const QJsonArray &overlays,
    const QJsonArray &panes) {
    QSet<QString> enabled;
    for (const QString &indicator : enabledIndicators) {
        const QString key = indicator.trimmed().toLower();
        if (!key.isEmpty()) {
            enabled.insert(key);
        }
    }
    QJsonArray candlePayload;
    QJsonArray volumePayload;
    for (const QJsonValue &value : candles) {
        const QJsonObject candle = value.toObject();
        candlePayload.append(QJsonObject{
            {QStringLiteral("time"), candle.value(QStringLiteral("time"))},
            {QStringLiteral("open"), candle.value(QStringLiteral("open"))},
            {QStringLiteral("high"), candle.value(QStringLiteral("high"))},
            {QStringLiteral("low"), candle.value(QStringLiteral("low"))},
            {QStringLiteral("close"), candle.value(QStringLiteral("close"))},
        });
        if (enabled.contains(QStringLiteral("volume"))) {
            volumePayload.append(QJsonObject{
                {QStringLiteral("time"), candle.value(QStringLiteral("time"))},
                {QStringLiteral("value"), candle.value(QStringLiteral("volume"))},
                {QStringLiteral("color"), candle.value(QStringLiteral("close")).toDouble() >= candle.value(QStringLiteral("open")).toDouble()
                    ? QStringLiteral("#0ebb7a")
                    : QStringLiteral("#f75467")},
            });
        }
    }
    return {
        {QStringLiteral("candles"), candlePayload},
        {QStringLiteral("volume"), volumePayload},
        {QStringLiteral("overlays"), overlays},
        {QStringLiteral("panes"), panes},
        {QStringLiteral("theme"), themeName.trimmed().toLower().startsWith(QStringLiteral("light"))
            ? QStringLiteral("light")
            : QStringLiteral("dark")},
    };
}

QStringList lightweightAssetSources(bool localAssetAvailable) {
    QStringList sources;
    if (localAssetAvailable) {
        sources.append(QStringLiteral("file://%1").arg(QString::fromLatin1(kLightweightLocalAsset)));
    }
    sources.append(QStringLiteral("https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"));
    sources.append(QStringLiteral("https://cdn.jsdelivr.net/npm/lightweight-charts/dist/lightweight-charts.standalone.production.js"));
    return sources;
}

QJsonObject buildChartViewModeGuardDecision(
    const QString &requestedMode,
    bool safeModeEnabled,
    bool externalOpened) {
    const QString mode = requestedMode.trimmed().toLower();
    if (safeModeEnabled
        && (mode == QStringLiteral("tradingview")
            || mode == QStringLiteral("original")
            || mode == QStringLiteral("lightweight"))) {
        QString status;
        QString externalUrl;
        if (mode == QStringLiteral("tradingview") && externalOpened) {
            status = QString::fromLatin1(kSafeTradingViewExternalStatus);
            externalUrl = buildTradingViewUrl(QStringLiteral("BINANCE:BTCUSDT"), QStringLiteral("60"));
        } else if (mode == QStringLiteral("tradingview")) {
            status = QString::fromLatin1(kSafeTradingViewBlockedStatus);
        } else {
            status = QString::fromLatin1(kSafeModeStatus);
        }
        return {
            {QStringLiteral("requested_mode"), mode},
            {QStringLiteral("actual_mode"), QStringLiteral("original")},
            {QStringLiteral("external_url"), externalUrl},
            {QStringLiteral("status_message"), status},
            {QStringLiteral("fallback_reason"), QStringLiteral("BOT_SAFE_CHART_TAB")},
            {QStringLiteral("render_legacy_chart"), true},
            {QStringLiteral("should_reload"), true},
        };
    }
    return {
        {QStringLiteral("requested_mode"), mode},
        {QStringLiteral("actual_mode"), mode},
        {QStringLiteral("external_url"), QString()},
        {QStringLiteral("status_message"), QString()},
        {QStringLiteral("fallback_reason"), QString()},
        {QStringLiteral("render_legacy_chart"), false},
        {QStringLiteral("should_reload"), false},
    };
}

QJsonArray liquidationHeatmapProviders() {
    return {
        QJsonObject{{QStringLiteral("key"), QStringLiteral("coinglass-model-1")}, {QStringLiteral("label"), QStringLiteral("Model 1")}, {QStringLiteral("title"), QStringLiteral("Coinglass Heatmap Model 1")}, {QStringLiteral("url"), QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationHeatMap")}, {QStringLiteral("parent_tab"), QStringLiteral("Coinglass Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("coinglass-model-2")}, {QStringLiteral("label"), QStringLiteral("Model 2")}, {QStringLiteral("title"), QStringLiteral("Coinglass Heatmap Model 2")}, {QStringLiteral("url"), QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationHeatMapNew")}, {QStringLiteral("parent_tab"), QStringLiteral("Coinglass Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("coinglass-model-3")}, {QStringLiteral("label"), QStringLiteral("Model 3")}, {QStringLiteral("title"), QStringLiteral("Coinglass Heatmap Model 3")}, {QStringLiteral("url"), QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3")}, {QStringLiteral("parent_tab"), QStringLiteral("Coinglass Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("coinank")}, {QStringLiteral("label"), QStringLiteral("Coinank")}, {QStringLiteral("title"), QStringLiteral("Coinank Liquidation Heatmap")}, {QStringLiteral("url"), QStringLiteral("https://coinank.com/chart/derivatives/liq-heat-map")}, {QStringLiteral("parent_tab"), QStringLiteral("Liquidation Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("bitcoin-counterflow")}, {QStringLiteral("label"), QStringLiteral("Bitcoin Counterflow")}, {QStringLiteral("title"), QStringLiteral("Bitcoin Counterflow Liquidation Heatmap")}, {QStringLiteral("url"), QStringLiteral("https://www.bitcoincounterflow.com/liquidation-heatmap/")}, {QStringLiteral("parent_tab"), QStringLiteral("Liquidation Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("hyblock-capital")}, {QStringLiteral("label"), QStringLiteral("Hyblock Capital")}, {QStringLiteral("title"), QStringLiteral("Hyblock Capital Liquidation Heatmap")}, {QStringLiteral("url"), QStringLiteral("https://hyblockcapital.com/")}, {QStringLiteral("parent_tab"), QStringLiteral("Liquidation Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("coinglass-map")}, {QStringLiteral("label"), QStringLiteral("Coinglass Map")}, {QStringLiteral("title"), QStringLiteral("Coinglass Liquidation Map")}, {QStringLiteral("url"), QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationMap")}, {QStringLiteral("parent_tab"), QStringLiteral("Liquidation Heatmap")}},
        QJsonObject{{QStringLiteral("key"), QStringLiteral("hyperliquid-map")}, {QStringLiteral("label"), QStringLiteral("Hyperliquid Map")}, {QStringLiteral("title"), QStringLiteral("Hyperliquid Liquidation Map")}, {QStringLiteral("url"), QStringLiteral("https://www.coinglass.com/hyperliquid-liquidation-map")}, {QStringLiteral("parent_tab"), QStringLiteral("Liquidation Heatmap")}},
    };
}

} // namespace NativeChartHeatmap
