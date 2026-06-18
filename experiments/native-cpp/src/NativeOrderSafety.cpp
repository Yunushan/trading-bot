#include "NativeOrderSafety.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QSet>
#include <QtGlobal>

#include <algorithm>
#include <cmath>

namespace {

constexpr int kDefaultOrderAuditMaxBytes = 10 * 1024 * 1024;
constexpr int kDefaultOrderAuditBackupCount = 1;
constexpr int kMaxLiveSessionOrders = 100000;
constexpr int kBinanceMaxFuturesLeverage = 125;
QJsonObject gOrderAuditStatus;

QString normalizedKey(QString value) {
    value = value.trimmed().toLower();
    QString out;
    out.reserve(value.size());
    for (const QChar ch : value) {
        if (ch.isLetterOrNumber()) {
            out.append(ch);
        }
    }
    return out;
}

QString normalizedDecimal(double value) {
    if (!qIsFinite(value)) {
        return QStringLiteral("0");
    }
    QString text = QString::number(value, 'f', 12);
    while (text.contains('.') && text.endsWith('0')) {
        text.chop(1);
    }
    if (text.endsWith('.')) {
        text.chop(1);
    }
    return text.isEmpty() ? QStringLiteral("0") : text;
}

QString paramValue(const QVector<QPair<QString, QString>> &params, const QStringList &keys) {
    for (const QString &key : keys) {
        for (const auto &item : params) {
            if (item.first.trimmed().compare(key, Qt::CaseInsensitive) == 0) {
                return item.second;
            }
        }
    }
    return {};
}

bool boolParam(const QString &value) {
    const QString text = value.trimmed().toLower();
    return text == QStringLiteral("1")
        || text == QStringLiteral("true")
        || text == QStringLiteral("yes")
        || text == QStringLiteral("y")
        || text == QStringLiteral("on");
}

bool doubleParam(const QString &value, double *out) {
    bool ok = false;
    const double parsed = value.trimmed().toDouble(&ok);
    if (!ok || !qIsFinite(parsed)) {
        return false;
    }
    if (out) {
        *out = parsed;
    }
    return true;
}

bool alignedToStep(double value, double step) {
    if (!qIsFinite(value) || !qIsFinite(step) || step <= 0.0) {
        return true;
    }
    const double ratio = value / step;
    return std::fabs(ratio - std::round(ratio)) <= 1e-9;
}

bool credentialIsReal(const QString &value) {
    const QString text = value.trimmed();
    if (text.isEmpty()) {
        return false;
    }
    static const QSet<QString> placeholders = {
        QStringLiteral("api_key"),
        QStringLiteral("api-secret"),
        QStringLiteral("api_secret"),
        QStringLiteral("binance_api_key"),
        QStringLiteral("binance_api_secret"),
        QStringLiteral("changeme"),
        QStringLiteral("demo"),
        QStringLiteral("example"),
        QStringLiteral("sandbox"),
        QStringLiteral("secret"),
        QStringLiteral("test"),
        QStringLiteral("testnet"),
        QStringLiteral("your-api-key"),
        QStringLiteral("your-api-secret"),
        QStringLiteral("your_api_key"),
        QStringLiteral("your_api_secret"),
    };
    return !placeholders.contains(text.toLower());
}

QStringList connectorHealthErrors(const QString &state, const QString &health) {
    const QString stateNorm = state.trimmed().toLower();
    const QString healthNorm = health.trimmed().toLower();
    if (!stateNorm.isEmpty() && stateNorm != QStringLiteral("ready")) {
        return {
            QStringLiteral("connector health is %1 / %2")
                .arg(healthNorm.isEmpty() ? QStringLiteral("unknown") : healthNorm, stateNorm),
        };
    }
    if (!healthNorm.isEmpty()
        && healthNorm != QStringLiteral("ok")
        && healthNorm != QStringLiteral("unknown")) {
        return {QStringLiteral("connector health is %1").arg(healthNorm)};
    }
    return {};
}

QJsonValue extractOrderId(const QJsonObject &payload) {
    QJsonObject candidates = payload;
    const QJsonObject info = payload.value(QStringLiteral("info")).toObject();
    if (!info.isEmpty()) {
        candidates = info;
    }
    for (const QString &key : {
             QStringLiteral("orderId"),
             QStringLiteral("order_id"),
             QStringLiteral("id"),
             QStringLiteral("clientOrderId"),
             QStringLiteral("client_order_id"),
             QStringLiteral("clientOrderID"),
         }) {
        const QJsonValue value = candidates.value(key);
        if (!value.isUndefined() && !value.isNull() && value.toVariant().toString() != QString()) {
            return value;
        }
    }
    return {};
}

QString currentIso(const QDateTime &timestamp) {
    const QDateTime value = timestamp.isValid() ? timestamp.toUTC() : QDateTime::currentDateTimeUtc();
    return value.toString(Qt::ISODateWithMs);
}

QString envValue(const char *name) {
    return qEnvironmentVariable(name).trimmed();
}

bool envBool(QString value, bool defaultValue = false) {
    value = value.trimmed().toLower();
    if (value.isEmpty()) {
        return defaultValue;
    }
    return value == QStringLiteral("1")
        || value == QStringLiteral("true")
        || value == QStringLiteral("yes")
        || value == QStringLiteral("y")
        || value == QStringLiteral("on");
}

NativeOrderSafety::OrderAuditLogConfig sanitizedOrderAuditConfig(
    NativeOrderSafety::OrderAuditLogConfig config) {
    if (config.path.trimmed().isEmpty()) {
        config.path = NativeOrderSafety::defaultOrderAuditPath();
    } else {
        config.path = QDir::cleanPath(config.path.trimmed());
    }
    if (config.maxBytes == 0) {
        config.maxBytes = kDefaultOrderAuditMaxBytes;
    }
    config.backupCount = std::max(0, std::min(100, config.backupCount));
    return config;
}

QJsonObject compactObject(QJsonObject object) {
    for (auto it = object.begin(); it != object.end();) {
        const QJsonValue value = it.value();
        const bool remove = value.isUndefined()
            || value.isNull()
            || (value.isString() && value.toString().isEmpty())
            || (value.isObject() && value.toObject().isEmpty())
            || (value.isArray() && value.toArray().isEmpty());
        if (remove) {
            it = object.erase(it);
        } else {
            ++it;
        }
    }
    return object;
}

QString stateFromRaw(const QJsonObject &raw) {
    return raw.value(QStringLiteral("state")).toString().trimmed().toLower();
}

} // namespace

namespace NativeOrderSafety {

ConnectorOrderCircuitBreaker::ConnectorOrderCircuitBreaker(ConnectorOrderCircuitConfig config)
    : config_(config) {
    config_.blockThreshold = std::max(1, config_.blockThreshold);
    config_.blockWindowSeconds = qIsFinite(config_.blockWindowSeconds)
        ? std::max(1.0, config_.blockWindowSeconds)
        : 60.0;
    snapshot_ = buildConnectorOrderCircuitBreakerSnapshot(
        {
            {QStringLiteral("active"), false},
            {QStringLiteral("state"), QStringLiteral("closed")},
            {QStringLiteral("block_threshold"), config_.blockThreshold},
            {QStringLiteral("block_window_seconds"), config_.blockWindowSeconds},
        },
        QStringLiteral("service-bootstrap"),
        QDateTime::currentDateTimeUtc());
}

QJsonObject ConnectorOrderCircuitBreaker::recordConnectorOrderBlock(
    const ConnectorOrderBlockEvent &event,
    const QDateTime &now) {
    if (!config_.enabled) {
        return {};
    }
    const double cutoff = event.timestamp - config_.blockWindowSeconds;
    events_.erase(
        std::remove_if(
            events_.begin(),
            events_.end(),
            [cutoff](const ConnectorOrderBlockEvent &item) {
                return !qIsFinite(item.timestamp) || item.timestamp < cutoff;
            }),
        events_.end());
    ConnectorOrderBlockEvent safeEvent = event;
    safeEvent.symbol = safeEvent.symbol.trimmed().toUpper();
    safeEvent.side = safeEvent.side.trimmed().toUpper();
    safeEvent.accountType = safeEvent.accountType.trimmed().toUpper();
    safeEvent.connectorMessage = redactText(safeEvent.connectorMessage);
    safeEvent.signature = redactText(safeEvent.signature);
    events_.append(safeEvent);

    if (open_ || events_.size() < config_.blockThreshold) {
        return {};
    }
    open_ = true;
    const QString message = safeEvent.connectorMessage.trimmed().isEmpty()
        ? QStringLiteral("Connector health circuit breaker paused trading.")
        : safeEvent.connectorMessage;
    snapshot_ = buildConnectorOrderCircuitBreakerSnapshot(
        {
            {QStringLiteral("active"), true},
            {QStringLiteral("state"), QStringLiteral("open")},
            {QStringLiteral("reason"), QStringLiteral("connector_order_block")},
            {QStringLiteral("message"), message},
            {QStringLiteral("block_count"), events_.size()},
            {QStringLiteral("block_threshold"), config_.blockThreshold},
            {QStringLiteral("block_window_seconds"), config_.blockWindowSeconds},
            {QStringLiteral("symbol"), safeEvent.symbol},
            {QStringLiteral("interval"), safeEvent.interval},
            {QStringLiteral("side"), safeEvent.side},
            {QStringLiteral("account_type"), safeEvent.accountType},
            {QStringLiteral("connector_health"), safeEvent.connectorHealth},
            {QStringLiteral("connector_state"), safeEvent.connectorState},
        },
        QStringLiteral("strategy"),
        now);
    return snapshot_;
}

QJsonObject ConnectorOrderCircuitBreaker::snapshot(const QDateTime &now) const {
    QJsonObject raw = snapshot_;
    raw.insert(QStringLiteral("block_threshold"), config_.blockThreshold);
    raw.insert(QStringLiteral("block_window_seconds"), config_.blockWindowSeconds);
    raw.insert(QStringLiteral("block_count"), events_.size());
    return buildConnectorOrderCircuitBreakerSnapshot(raw, raw.value(QStringLiteral("source")).toString(), now);
}

QJsonObject ConnectorOrderCircuitBreaker::resetConnectorOrderCircuitBreaker(
    const QString &source,
    bool force,
    const QString &resetBlockReason,
    const QDateTime &now) {
    const QString sourceNorm = source.trimmed().isEmpty() ? QStringLiteral("service") : source.trimmed();
    if (open_ && !force && !resetBlockReason.trimmed().isEmpty()) {
        QJsonObject raw = snapshot_;
        raw.insert(QStringLiteral("active"), true);
        raw.insert(QStringLiteral("state"), QStringLiteral("open"));
        raw.insert(QStringLiteral("message"), redactText(resetBlockReason));
        raw.insert(QStringLiteral("reset_blocked"), true);
        raw.insert(QStringLiteral("reset_blocked_reason"), redactText(resetBlockReason));
        raw.insert(QStringLiteral("reset_blocked_at"), currentIso(now));
        raw.insert(QStringLiteral("source"), sourceNorm);
        snapshot_ = buildConnectorOrderCircuitBreakerSnapshot(raw, sourceNorm, now);
        return snapshot_;
    }
    open_ = false;
    events_.clear();
    QJsonObject raw = snapshot_;
    raw.insert(QStringLiteral("active"), false);
    raw.insert(QStringLiteral("state"), QStringLiteral("closed"));
    raw.insert(QStringLiteral("message"), QStringLiteral("Connector health circuit breaker reset."));
    raw.insert(QStringLiteral("cleared_at"), currentIso(now));
    raw.insert(QStringLiteral("reset_blocked"), false);
    raw.insert(QStringLiteral("reset_blocked_reason"), QString());
    raw.insert(QStringLiteral("reset_blocked_at"), QString());
    raw.insert(QStringLiteral("source"), sourceNorm);
    snapshot_ = buildConnectorOrderCircuitBreakerSnapshot(raw, sourceNorm, now);
    return snapshot_;
}

bool ConnectorOrderCircuitBreaker::isOpen() const {
    return open_;
}

int ConnectorOrderCircuitBreaker::eventCount() const {
    return events_.size();
}

bool isSensitiveKey(const QString &key) {
    const QString normalized = normalizedKey(key);
    for (const QString &suffix : {
             QStringLiteral("env"),
             QStringLiteral("environment"),
             QStringLiteral("present"),
         }) {
        if (normalized.endsWith(suffix)) {
            return false;
        }
    }
    for (const QString &part : {
             QStringLiteral("apikey"),
             QStringLiteral("apisecret"),
             QStringLiteral("authorization"),
             QStringLiteral("bearer"),
             QStringLiteral("passphrase"),
             QStringLiteral("password"),
             QStringLiteral("privatekey"),
             QStringLiteral("secret"),
             QStringLiteral("signature"),
             QStringLiteral("token"),
             QStringLiteral("xmbxapikey"),
         }) {
        if (normalized.contains(part)) {
            return true;
        }
    }
    return false;
}

QString redactText(QString text) {
    if (text.isEmpty()) {
        return text;
    }
    static const QRegularExpression bearerRe(QStringLiteral("(?i)\\bbearer\\s+[A-Za-z0-9._~+/=-]+"));
    text.replace(bearerRe, QStringLiteral("Bearer <redacted>"));
    static const QRegularExpression assignmentRe(
        QStringLiteral("(?i)(x-mbx-apikey|api[_-]?key|api[_-]?secret|llm[_-]?api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|signature|password|passphrase|private[_-]?key)(\\s*[:=]\\s*)(['\\\"]?)([^'\\\"\\s,;&}]+)(\\3)"));
    text.replace(assignmentRe, QStringLiteral("\\1\\2\\3<redacted>\\5"));
    return text;
}

QJsonValue redactValue(const QJsonValue &value, int depth) {
    if (depth > 8) {
        return QStringLiteral("...");
    }
    if (value.isObject()) {
        QJsonObject out;
        const QJsonObject object = value.toObject();
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            if (isSensitiveKey(it.key())) {
                out.insert(it.key(), it.value().isNull() ? QJsonValue{} : QJsonValue(QStringLiteral("<redacted>")));
            } else {
                out.insert(it.key(), redactValue(it.value(), depth + 1));
            }
        }
        return out;
    }
    if (value.isArray()) {
        QJsonArray out;
        const QJsonArray array = value.toArray();
        for (const QJsonValue &item : array) {
            out.append(redactValue(item, depth + 1));
        }
        return out;
    }
    if (value.isString()) {
        return redactText(value.toString());
    }
    return value;
}

QJsonObject redactOrderParams(const QVector<QPair<QString, QString>> &params) {
    QJsonObject out;
    for (const auto &item : params) {
        out.insert(
            item.first,
            isSensitiveKey(item.first) && !item.second.isEmpty()
                ? QJsonValue(QStringLiteral("<redacted>"))
                : QJsonValue(redactText(item.second)));
    }
    return out;
}

OrderSubmitIntent orderSubmitIntentFromParams(
    const QString &market,
    const QVector<QPair<QString, QString>> &params) {
    OrderSubmitIntent intent;
    intent.market = market.trimmed().toLower();
    intent.symbol = paramValue(params, {QStringLiteral("symbol")}).trimmed().toUpper();
    intent.side = paramValue(params, {QStringLiteral("side")}).trimmed().toUpper();
    intent.orderType = paramValue(params, {QStringLiteral("type")}).trimmed().toUpper();
    intent.hasQuantity = doubleParam(paramValue(params, {QStringLiteral("quantity")}), &intent.quantity);
    intent.hasPrice = doubleParam(paramValue(params, {QStringLiteral("price")}), &intent.price);
    intent.positionSide = paramValue(params, {QStringLiteral("positionSide"), QStringLiteral("position_side")}).trimmed().toUpper();
    intent.closePosition = boolParam(paramValue(params, {QStringLiteral("closePosition"), QStringLiteral("close_position")}));
    intent.reduceOnly = boolParam(paramValue(params, {QStringLiteral("reduceOnly"), QStringLiteral("reduce_only")}));
    return intent;
}

QStringList validateOrderSubmitIntent(const OrderSubmitIntent &intent) {
    QStringList errors;
    if (intent.market != QStringLiteral("futures") && intent.market != QStringLiteral("spot")) {
        errors.append(QStringLiteral("order market must be futures or spot"));
    }
    if (intent.symbol.isEmpty()) {
        errors.append(QStringLiteral("order symbol is required"));
    }
    if (intent.side != QStringLiteral("BUY") && intent.side != QStringLiteral("SELL")) {
        errors.append(QStringLiteral("order side must be BUY or SELL"));
    }
    if (intent.orderType.isEmpty()) {
        errors.append(QStringLiteral("order type is required"));
    } else if (intent.orderType != QStringLiteral("LIMIT") && intent.orderType != QStringLiteral("MARKET")) {
        errors.append(QStringLiteral("order type must be LIMIT or MARKET"));
    }
    if (!intent.positionSide.isEmpty()
        && intent.positionSide != QStringLiteral("BOTH")
        && intent.positionSide != QStringLiteral("LONG")
        && intent.positionSide != QStringLiteral("SHORT")) {
        errors.append(QStringLiteral("positionSide must be BOTH, LONG, or SHORT"));
    }
    if (!intent.positionSide.isEmpty() && intent.market != QStringLiteral("futures")) {
        errors.append(QStringLiteral("positionSide is only supported for futures"));
    }
    if (intent.closePosition && intent.market != QStringLiteral("futures")) {
        errors.append(QStringLiteral("closePosition orders are only supported for futures"));
    }
    if (intent.reduceOnly && intent.market != QStringLiteral("futures")) {
        errors.append(QStringLiteral("reduceOnly orders are only supported for futures"));
    }
    if (intent.closePosition && intent.reduceOnly) {
        errors.append(QStringLiteral("closePosition and reduceOnly cannot be used together"));
    }
    const bool quantityRequired = intent.market != QStringLiteral("futures") || !intent.closePosition;
    if (quantityRequired && (!intent.hasQuantity || intent.quantity <= 0.0)) {
        errors.append(QStringLiteral("order quantity must be > 0"));
    }
    if (intent.orderType == QStringLiteral("LIMIT") && (!intent.hasPrice || intent.price <= 0.0)) {
        errors.append(QStringLiteral("limit order price must be > 0"));
    }
    return errors;
}

QStringList validateOrderFilterConstraints(
    const OrderSubmitIntent &intent,
    const OrderSymbolFilters &filters,
    bool hasLastPrice,
    double lastPrice) {
    if (!intent.hasQuantity || !qIsFinite(intent.quantity)) {
        return {};
    }
    QStringList errors;
    const bool riskReducingExit = intent.market == QStringLiteral("futures")
        && (intent.reduceOnly || intent.closePosition);
    if (filters.minQty > 0.0 && intent.quantity < filters.minQty && !riskReducingExit) {
        errors.append(
            QStringLiteral("order quantity %1 is below %2 minQty %3")
                .arg(normalizedDecimal(intent.quantity), intent.symbol, normalizedDecimal(filters.minQty)));
    }
    if (filters.stepSize > 0.0 && !alignedToStep(intent.quantity, filters.stepSize)) {
        errors.append(
            QStringLiteral("order quantity %1 is not aligned to %2 stepSize %3")
                .arg(normalizedDecimal(intent.quantity), intent.symbol, normalizedDecimal(filters.stepSize)));
    }
    const double price = intent.hasPrice ? intent.price : (hasLastPrice ? lastPrice : 0.0);
    const bool hasPrice = price > 0.0;
    if (filters.tickSize > 0.0 && hasPrice && !alignedToStep(price, filters.tickSize)) {
        errors.append(
            QStringLiteral("order price %1 is not aligned to %2 tickSize %3")
                .arg(normalizedDecimal(price), intent.symbol, normalizedDecimal(filters.tickSize)));
    }
    if (filters.minNotional > 0.0 && !riskReducingExit) {
        if (!hasPrice) {
            errors.append(QStringLiteral("last price unavailable for %1 minNotional validation").arg(intent.symbol));
        } else {
            const double notional = intent.quantity * price;
            if (notional < filters.minNotional) {
                errors.append(
                    QStringLiteral("order notional %1 is below %2 minNotional %3")
                        .arg(normalizedDecimal(notional), intent.symbol, normalizedDecimal(filters.minNotional)));
            }
        }
    }
    return errors;
}

bool isLiveTradingMode(const QString &mode) {
    const QString text = mode.trimmed().toLower();
    if (text.isEmpty()) {
        return false;
    }
    for (const QString &token : {
             QStringLiteral("demo"),
             QStringLiteral("test"),
             QStringLiteral("sandbox"),
             QStringLiteral("paper"),
         }) {
        if (text.contains(token)) {
            return false;
        }
    }
    return true;
}

QStringList validateLiveTradingSafety(const LiveOrderGuardInput &input) {
    if (!isLiveTradingMode(input.mode)) {
        return {};
    }
    QStringList errors;
    if (!input.config.liveTradingEnabled
        || input.config.liveTradingAcknowledgement.trimmed() != QString::fromLatin1(LiveTradingAcknowledgement)) {
        errors.append(QStringLiteral("set live_trading_enabled=true and live_trading_acknowledgement=\"%1\"")
                          .arg(QString::fromLatin1(LiveTradingAcknowledgement)));
    }
    if (!credentialIsReal(input.apiKey) || !credentialIsReal(input.apiSecret)) {
        errors.append(QStringLiteral("provide non-placeholder Binance API credentials"));
    }
    if (input.config.liveTradingMaxLeverage < 1 || input.config.liveTradingMaxLeverage > kBinanceMaxFuturesLeverage) {
        errors.append(QStringLiteral("live_trading_max_leverage must be between 1 and %1").arg(kBinanceMaxFuturesLeverage));
    }
    if (input.config.liveTradingMaxPositionPct <= 0.0 || input.config.liveTradingMaxPositionPct > 100.0) {
        errors.append(QStringLiteral("live_trading_max_position_pct must be > 0 and <= 100"));
    }
    if (input.config.liveTradingMaxSessionOrders < 1
        || input.config.liveTradingMaxSessionOrders > kMaxLiveSessionOrders) {
        errors.append(QStringLiteral("live_trading_max_session_orders must be between 1 and %1").arg(kMaxLiveSessionOrders));
    }
    if (input.positionPct <= 0.0 || input.positionPct > 100.0) {
        errors.append(QStringLiteral("position_pct must be > 0 and <= 100 for live trading"));
    } else if (input.positionPct > input.config.liveTradingMaxPositionPct) {
        errors.append(
            QStringLiteral("position_pct %1% exceeds live cap %2%")
                .arg(normalizedDecimal(input.positionPct), normalizedDecimal(input.config.liveTradingMaxPositionPct)));
    }
    if (input.accountType.trimmed().toUpper().startsWith(QStringLiteral("FUT"))) {
        if (input.leverage < 1) {
            errors.append(QStringLiteral("leverage must be >= 1 for live futures trading"));
        } else if (input.leverage > input.config.liveTradingMaxLeverage) {
            errors.append(
                QStringLiteral("leverage %1 exceeds live cap %2")
                    .arg(input.leverage)
                    .arg(input.config.liveTradingMaxLeverage));
        }
        const QString margin = input.marginMode.trimmed().toUpper();
        if (!margin.isEmpty() && margin != QStringLiteral("ISOLATED") && margin != QStringLiteral("CROSS")) {
            errors.append(QStringLiteral("margin_mode must be Isolated or Cross for live futures trading"));
        }
    }
    return errors;
}

LiveOrderGuardResult guardLiveOrderSubmit(const LiveOrderGuardInput &input) {
    const int currentCount = std::max(0, input.liveSubmitAttemptCount);
    if (!isLiveTradingMode(input.mode)) {
        return {true, {}, currentCount};
    }
    QStringList errors = validateLiveTradingSafety(input);
    if (!input.orderAuditEnabled) {
        errors.append(QStringLiteral("order audit is disabled"));
    }
    if (!input.orderAuditWritable) {
        errors.append(QStringLiteral("order audit is not writable"));
    }
    errors.append(connectorHealthErrors(input.connectorState, input.connectorHealth));
    const OrderSubmitIntent intent = orderSubmitIntentFromParams(input.market, input.params);
    errors.append(validateOrderSubmitIntent(intent));
    if (!intent.symbol.isEmpty()
        && intent.hasQuantity
        && (intent.market == QStringLiteral("futures") || intent.market == QStringLiteral("spot"))) {
        if (input.hasFilters) {
            errors.append(validateOrderFilterConstraints(intent, input.filters, input.hasLastPrice, input.lastPrice));
        } else {
            errors.append(QStringLiteral("%1 symbol filters unavailable for %2").arg(intent.market, intent.symbol));
        }
    }
    if (currentCount >= input.config.liveTradingMaxSessionOrders) {
        errors.append(QStringLiteral("live session order cap %1 reached").arg(input.config.liveTradingMaxSessionOrders));
    }
    const bool allowed = errors.isEmpty();
    return {allowed, errors, allowed ? currentCount + 1 : currentCount};
}

QJsonObject buildOrderAuditEvent(
    const QString &event,
    const QString &market,
    const QVector<QPair<QString, QString>> &params,
    const QDateTime &timestamp,
    const QString &source) {
    const OrderSubmitIntent intent = orderSubmitIntentFromParams(market, params);
    return compactObject({
        {QStringLiteral("ts"), currentIso(timestamp)},
        {QStringLiteral("event"), event.trimmed().isEmpty() ? QStringLiteral("order_event") : event.trimmed()},
        {QStringLiteral("symbol"), intent.symbol},
        {QStringLiteral("side"), intent.side},
        {QStringLiteral("market"), market.trimmed()},
        {QStringLiteral("source"), source.trimmed()},
        {QStringLiteral("params"), redactOrderParams(params)},
    });
}

QString orderAuditEventJsonLine(const QJsonObject &event) {
    QJsonObject safe = event;
    if (safe.value(QStringLiteral("event")).toString().trimmed().isEmpty()) {
        safe.insert(QStringLiteral("event"), QStringLiteral("order_event"));
    }
    if (safe.contains(QStringLiteral("params"))) {
        safe.insert(QStringLiteral("params"), redactValue(safe.value(QStringLiteral("params"))));
    }
    if (safe.contains(QStringLiteral("computed"))) {
        safe.insert(QStringLiteral("computed"), redactValue(safe.value(QStringLiteral("computed"))));
    }
    if (safe.contains(QStringLiteral("result"))) {
        const QJsonObject result = redactValue(safe.value(QStringLiteral("result"))).toObject();
        safe.insert(QStringLiteral("result"), result);
        const QJsonValue orderId = extractOrderId(result);
        if (!orderId.isUndefined() && !safe.contains(QStringLiteral("order_id"))) {
            safe.insert(QStringLiteral("order_id"), orderId);
        }
    }
    if (safe.contains(QStringLiteral("error"))) {
        safe.insert(QStringLiteral("error"), redactText(safe.value(QStringLiteral("error")).toString()));
    }
    if (safe.contains(QStringLiteral("extra"))) {
        safe.insert(QStringLiteral("extra"), redactValue(safe.value(QStringLiteral("extra"))));
    }
    return QString::fromUtf8(QJsonDocument(compactObject(safe)).toJson(QJsonDocument::Compact));
}

QJsonObject buildOrderAuditStatus(
    bool enabled,
    const QString &path,
    quint64 maxBytes,
    int backupCount,
    const QString &lastWriteError,
    const QString &lastWriteErrorAt,
    const QString &lastWriteOkAt) {
    const bool writeOk = lastWriteError.trimmed().isEmpty();
    QJsonObject error;
    if (!writeOk) {
        error.insert(QStringLiteral("message"), redactText(lastWriteError));
        error.insert(QStringLiteral("path"), redactText(path));
    }
    return compactObject({
        {QStringLiteral("enabled"), enabled},
        {QStringLiteral("state"), !enabled ? QStringLiteral("disabled") : writeOk ? QStringLiteral("ready") : QStringLiteral("write_failed")},
        {QStringLiteral("path"), redactText(path)},
        {QStringLiteral("max_bytes"), static_cast<qint64>(std::max<quint64>(1, maxBytes ? maxBytes : kDefaultOrderAuditMaxBytes))},
        {QStringLiteral("backup_count"), std::max(0, std::min(100, backupCount < 0 ? kDefaultOrderAuditBackupCount : backupCount))},
        {QStringLiteral("write_ok"), writeOk},
        {QStringLiteral("last_write_error"), error},
        {QStringLiteral("last_write_error_at"), lastWriteErrorAt},
        {QStringLiteral("last_write_ok_at"), lastWriteOkAt},
    });
}

QString defaultOrderAuditPath() {
    return QDir::home().filePath(QStringLiteral(".trading-bot/order_audit.jsonl"));
}

QString orderAuditBackupPath(const QString &path, int index) {
    const QFileInfo info(path);
    const QString fileName = info.fileName();
    const QString backupName = QStringLiteral("%1.%2").arg(fileName, QString::number(std::max(1, index)));
    return info.dir().filePath(backupName);
}

OrderAuditLogConfig orderAuditLogConfigFromEnvironment() {
    OrderAuditLogConfig config;
    const QString disabled = envValue("BOT_ORDER_AUDIT_DISABLED");
    config.enabled = !envBool(disabled, false);
    const QString configuredPath = envValue("BOT_ORDER_AUDIT_LOG_PATH");
    const QString legacyPath = envValue("BOT_ORDER_AUDIT_LOG");
    config.path = configuredPath.isEmpty() ? legacyPath : configuredPath;
    return sanitizedOrderAuditConfig(config);
}

bool rotateOrderAuditLogIfNeeded(
    const QString &path,
    qint64 incomingBytes,
    quint64 maxBytes,
    int backupCount,
    QString *error) {
    if (error) {
        error->clear();
    }
    if (path.trimmed().isEmpty() || maxBytes == 0 || backupCount < 0) {
        return false;
    }

    const QFileInfo currentInfo(path);
    if (!currentInfo.exists()) {
        return false;
    }
    const quint64 currentSize = static_cast<quint64>(std::max<qint64>(0, currentInfo.size()));
    const quint64 incoming = static_cast<quint64>(std::max<qint64>(0, incomingBytes));
    if (currentSize + incoming <= maxBytes) {
        return false;
    }

    if (backupCount == 0) {
        if (!QFile::remove(path)) {
            if (error) {
                *error = QStringLiteral("Could not remove %1 before order audit rotation.").arg(path);
            }
        }
        return true;
    }

    QDir parent = currentInfo.dir();
    if (!parent.exists() && !parent.mkpath(QStringLiteral("."))) {
        if (error) {
            *error = QStringLiteral("Could not create order audit directory %1.").arg(parent.absolutePath());
        }
        return false;
    }

    for (int index = backupCount; index >= 1; --index) {
        const QString source = index == 1 ? path : orderAuditBackupPath(path, index - 1);
        const QString target = orderAuditBackupPath(path, index);
        if (!QFileInfo::exists(source)) {
            continue;
        }
        if (QFileInfo::exists(target) && !QFile::remove(target)) {
            if (error) {
                *error = QStringLiteral("Could not remove stale order audit backup %1.").arg(target);
            }
            return false;
        }
        QFile sourceFile(source);
        if (!sourceFile.rename(target)) {
            if (error) {
                *error = QStringLiteral("Could not rotate order audit log %1 to %2.").arg(source, target);
            }
            return false;
        }
    }
    return true;
}

QJsonObject appendOrderAuditEvent(
    const QJsonObject &event,
    const OrderAuditLogConfig &config) {
    const OrderAuditLogConfig safeConfig = sanitizedOrderAuditConfig(config);
    const QString path = safeConfig.path;
    if (!safeConfig.enabled) {
        gOrderAuditStatus = buildOrderAuditStatus(false, path, safeConfig.maxBytes, safeConfig.backupCount);
        return gOrderAuditStatus;
    }

    const QString line = orderAuditEventJsonLine(event) + QStringLiteral("\n");
    const QByteArray encoded = line.toUtf8();
    QFileInfo info(path);
    QDir parent = info.dir();
    const QString now = currentIso(QDateTime::currentDateTimeUtc());
    if (!parent.exists() && !parent.mkpath(QStringLiteral("."))) {
        gOrderAuditStatus = buildOrderAuditStatus(
            true,
            path,
            safeConfig.maxBytes,
            safeConfig.backupCount,
            QStringLiteral("Could not create order audit directory %1.").arg(parent.absolutePath()),
            now);
        return gOrderAuditStatus;
    }

    QString rotationError;
    if (!rotateOrderAuditLogIfNeeded(
            path,
            encoded.size(),
            safeConfig.maxBytes,
            safeConfig.backupCount,
            &rotationError)
        && !rotationError.isEmpty()) {
        gOrderAuditStatus = buildOrderAuditStatus(
            true,
            path,
            safeConfig.maxBytes,
            safeConfig.backupCount,
            rotationError,
            now);
        return gOrderAuditStatus;
    }

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
        gOrderAuditStatus = buildOrderAuditStatus(
            true,
            path,
            safeConfig.maxBytes,
            safeConfig.backupCount,
            file.errorString(),
            now);
        return gOrderAuditStatus;
    }
    const qint64 written = file.write(encoded);
    file.close();
    if (written != encoded.size()) {
        gOrderAuditStatus = buildOrderAuditStatus(
            true,
            path,
            safeConfig.maxBytes,
            safeConfig.backupCount,
            QStringLiteral("Order audit write was incomplete."),
            now);
        return gOrderAuditStatus;
    }

    gOrderAuditStatus = buildOrderAuditStatus(
        true,
        path,
        safeConfig.maxBytes,
        safeConfig.backupCount,
        {},
        {},
        now);
    return gOrderAuditStatus;
}

QJsonObject currentOrderAuditStatus(const OrderAuditLogConfig &config) {
    const OrderAuditLogConfig safeConfig = sanitizedOrderAuditConfig(config);
    const QString configuredPath = QDir::cleanPath(safeConfig.path);
    const QString lastPath = QDir::cleanPath(gOrderAuditStatus.value(QStringLiteral("path")).toString());
    if (!gOrderAuditStatus.isEmpty() && (lastPath.isEmpty() || lastPath == configuredPath)) {
        return gOrderAuditStatus;
    }
    return buildOrderAuditStatus(
        safeConfig.enabled,
        safeConfig.path,
        safeConfig.maxBytes,
        safeConfig.backupCount);
}

namespace {

QJsonArray stringArray(const QStringList &values) {
    QJsonArray out;
    for (const QString &value : values) {
        const QString text = value.trimmed();
        if (!text.isEmpty()) {
            out.append(text);
        }
    }
    return out;
}

QJsonObject buildFreshnessPayload(
    const OperationalFreshnessInput &input,
    const QDateTime &now) {
    const QDateTime nowUtc = now.isValid() ? now.toUTC() : QDateTime::currentDateTimeUtc();
    const QDateTime timestampUtc = input.timestamp.isValid() ? input.timestamp.toUTC() : QDateTime();
    const QString timestampField = input.timestampField.trimmed().isEmpty()
        ? QStringLiteral("generated_at")
        : input.timestampField.trimmed();
    const double maxAgeSeconds = qIsFinite(input.maxAgeSeconds)
        ? std::max(1.0, input.maxAgeSeconds)
        : 1.0;
    double ageSeconds = -1.0;
    if (timestampUtc.isValid()) {
        ageSeconds = std::max(0.0, static_cast<double>(timestampUtc.msecsTo(nowUtc)) / 1000.0);
    }
    const bool stale = input.shouldWarn && (!timestampUtc.isValid() || ageSeconds > maxAgeSeconds);
    const QString timestampText = input.timestampText.trimmed().isEmpty()
        ? (timestampUtc.isValid() ? currentIso(timestampUtc) : QString())
        : input.timestampText.trimmed();

    QJsonObject payload{
        {QStringLiteral("stale"), stale},
        {QStringLiteral("max_age_seconds"), maxAgeSeconds},
    };
    if (!timestampText.isEmpty()) {
        payload.insert(timestampField, timestampText);
    }
    if (ageSeconds >= 0.0) {
        payload.insert(QStringLiteral("age_seconds"), std::round(ageSeconds * 1000.0) / 1000.0);
    }
    if (!input.state.trimmed().isEmpty()) {
        payload.insert(QStringLiteral("state"), input.state.trimmed());
    }
    if (!input.source.trimmed().isEmpty()) {
        payload.insert(QStringLiteral("source"), input.source.trimmed());
    }
    return payload;
}

bool freshnessIsStale(const QJsonObject &payload) {
    return payload.value(QStringLiteral("stale")).toBool(false);
}

QJsonObject buildPreflightGate(
    bool enabled,
    bool liveMode,
    const QStringList &issues,
    const QString &disabledMessage,
    const QString &demoMessage) {
    if (!enabled) {
        return {
            {QStringLiteral("allowed"), true},
            {QStringLiteral("state"), QStringLiteral("warning")},
            {QStringLiteral("gate_enabled"), false},
            {QStringLiteral("reasons"), stringArray({disabledMessage})},
        };
    }
    if (issues.isEmpty()) {
        return {
            {QStringLiteral("allowed"), true},
            {QStringLiteral("state"), QStringLiteral("ok")},
            {QStringLiteral("gate_enabled"), true},
            {QStringLiteral("reasons"), QJsonArray{}},
        };
    }
    if (liveMode) {
        return {
            {QStringLiteral("allowed"), false},
            {QStringLiteral("state"), QStringLiteral("blocked")},
            {QStringLiteral("gate_enabled"), true},
            {QStringLiteral("reasons"), stringArray(issues)},
        };
    }

    QStringList reasons = issues;
    reasons.append(demoMessage);
    return {
        {QStringLiteral("allowed"), true},
        {QStringLiteral("state"), QStringLiteral("warning")},
        {QStringLiteral("gate_enabled"), true},
        {QStringLiteral("reasons"), stringArray(reasons)},
    };
}

void appendUniqueReason(QStringList *reasons, const QJsonObject &gate) {
    const QJsonArray values = gate.value(QStringLiteral("reasons")).toArray();
    for (const QJsonValue &value : values) {
        const QString text = value.toString().trimmed();
        if (!text.isEmpty() && !reasons->contains(text)) {
            reasons->append(text);
        }
    }
}

} // namespace

QJsonObject buildOperationalPreflightSnapshot(const OperationalPreflightInput &input) {
    const QDateTime now = input.generatedAt.isValid()
        ? input.generatedAt.toUTC()
        : QDateTime::currentDateTimeUtc();
    const bool circuitActive = input.connectorOrderCircuitBreaker.value(QStringLiteral("active")).toBool(false)
        || stateFromRaw(input.connectorOrderCircuitBreaker) == QStringLiteral("open")
        || stateFromRaw(input.connectorOrderCircuitBreaker) == QStringLiteral("paused")
        || stateFromRaw(input.connectorOrderCircuitBreaker) == QStringLiteral("tripped");
    QString health = input.health.trimmed().toLower();
    if (health.isEmpty()) {
        health = QStringLiteral("unknown");
    }
    if (circuitActive) {
        health = QStringLiteral("error");
    }

    QJsonObject freshness{
        {QStringLiteral("exchange_connector"), buildFreshnessPayload(input.exchangeConnector, now)},
        {QStringLiteral("execution"), buildFreshnessPayload(input.execution, now)},
        {QStringLiteral("account"), buildFreshnessPayload(input.account, now)},
        {QStringLiteral("portfolio"), buildFreshnessPayload(input.portfolio, now)},
    };

    QStringList startStaleLabels;
    QStringList orderStaleLabels;
    for (const auto &item : {
             QPair<QString, QString>{QStringLiteral("exchange_connector"), QStringLiteral("exchange connector")},
             QPair<QString, QString>{QStringLiteral("account"), QStringLiteral("account")},
             QPair<QString, QString>{QStringLiteral("portfolio"), QStringLiteral("portfolio")},
         }) {
        if (freshnessIsStale(freshness.value(item.first).toObject())) {
            startStaleLabels.append(item.second);
            orderStaleLabels.append(item.second);
        }
    }
    if (freshnessIsStale(freshness.value(QStringLiteral("execution")).toObject())) {
        startStaleLabels.append(QStringLiteral("execution heartbeat"));
    }

    auto issuesFor = [health](const QStringList &staleLabels) {
        QStringList issues;
        if (health == QStringLiteral("error")) {
            issues.append(QStringLiteral("operational health is error"));
        }
        if (!staleLabels.isEmpty()) {
            issues.append(QStringLiteral("critical snapshots are stale: %1").arg(staleLabels.join(QStringLiteral(", "))));
        }
        return issues;
    };

    const bool liveMode = isLiveTradingMode(input.mode);
    const QJsonObject startGate = buildPreflightGate(
        input.startGateEnabled,
        liveMode,
        issuesFor(startStaleLabels),
        QStringLiteral("Operational live start safety gate is disabled."),
        QStringLiteral("Demo/test mode start remains allowed."));
    const QJsonObject ordersGate = buildPreflightGate(
        input.orderGateEnabled,
        liveMode,
        issuesFor(orderStaleLabels),
        QStringLiteral("Operational live order safety gate is disabled."),
        QStringLiteral("Demo/test mode order remains allowed."));

    QStringList reasons;
    appendUniqueReason(&reasons, startGate);
    appendUniqueReason(&reasons, ordersGate);

    QString state = QStringLiteral("ok");
    if (startGate.value(QStringLiteral("state")).toString() == QStringLiteral("blocked")
        || ordersGate.value(QStringLiteral("state")).toString() == QStringLiteral("blocked")) {
        state = QStringLiteral("blocked");
    } else if (startGate.value(QStringLiteral("state")).toString() != QStringLiteral("ok")
        || ordersGate.value(QStringLiteral("state")).toString() != QStringLiteral("ok")) {
        state = QStringLiteral("warning");
    }

    QString message;
    if (state == QStringLiteral("blocked")) {
        message = QStringLiteral("Live preflight blocked. Review the reasons before starting or submitting orders.");
    } else if (state == QStringLiteral("warning")) {
        message = QStringLiteral("Preflight has warnings. Live gate behavior depends on the enabled safety gates.");
    } else {
        message = QStringLiteral("Preflight passed. Start and order gates have fresh critical snapshots.");
    }

    return {
        {QStringLiteral("state"), state},
        {QStringLiteral("message"), message},
        {QStringLiteral("mode"), input.mode},
        {QStringLiteral("live_mode"), liveMode},
        {QStringLiteral("generated_at"), currentIso(now)},
        {QStringLiteral("start"), startGate},
        {QStringLiteral("orders"), ordersGate},
        {QStringLiteral("freshness"), freshness},
        {QStringLiteral("critical_stale"), QJsonObject{
            {QStringLiteral("start"), stringArray(startStaleLabels)},
            {QStringLiteral("orders"), stringArray(orderStaleLabels)},
        }},
        {QStringLiteral("reasons"), stringArray(reasons)},
    };
}

bool operationalPreflightStartAllowed(const QJsonObject &preflight) {
    return preflight.value(QStringLiteral("start"))
        .toObject()
        .value(QStringLiteral("allowed"))
        .toBool(false);
}

bool operationalPreflightOrdersAllowed(const QJsonObject &preflight) {
    return preflight.value(QStringLiteral("orders"))
        .toObject()
        .value(QStringLiteral("allowed"))
        .toBool(false);
}

QJsonObject buildRuntimeStopGuardResult(const RuntimeStopGuardInput &input) {
    const QString source = input.source.trimmed().isEmpty()
        ? QStringLiteral("service")
        : redactText(input.source.trimmed());
    const int activeEngineCount = std::max(0, input.activeEngineCount);
    if (input.stopAlreadyInProgress) {
        return {
            {QStringLiteral("accepted"), false},
            {QStringLiteral("action"), QStringLiteral("stop")},
            {QStringLiteral("lifecycle_phase"), QStringLiteral("stopping")},
            {QStringLiteral("runtime_active"), input.runtimeActive},
            {QStringLiteral("active_engine_count"), activeEngineCount},
            {QStringLiteral("requested_job_count"), 0},
            {QStringLiteral("close_positions_requested"), input.closePositions},
            {QStringLiteral("source"), source},
            {QStringLiteral("status_message"), QStringLiteral("Stop request already in progress.")},
        };
    }
    if (!input.dispatchAccepted) {
        QString message = redactText(input.dispatchMessage.trimmed());
        if (message.isEmpty()) {
            message = QStringLiteral("Stop request could not be dispatched.");
        }
        return {
            {QStringLiteral("accepted"), false},
            {QStringLiteral("action"), QStringLiteral("stop")},
            {QStringLiteral("lifecycle_phase"), input.runtimeActive ? QStringLiteral("running") : QStringLiteral("idle")},
            {QStringLiteral("runtime_active"), input.runtimeActive},
            {QStringLiteral("active_engine_count"), activeEngineCount},
            {QStringLiteral("requested_job_count"), 0},
            {QStringLiteral("close_positions_requested"), false},
            {QStringLiteral("source"), source},
            {QStringLiteral("status_message"), message},
        };
    }

    QString message = input.closePositions
        ? QStringLiteral("Stop requested with close-all positions.")
        : QStringLiteral("Stop requested.");
    const QString dispatchMessage = redactText(input.dispatchMessage.trimmed());
    if (!dispatchMessage.isEmpty()) {
        message = QStringLiteral("%1 %2").arg(message, dispatchMessage).trimmed();
    }
    return {
        {QStringLiteral("accepted"), true},
        {QStringLiteral("action"), QStringLiteral("stop")},
        {QStringLiteral("lifecycle_phase"), QStringLiteral("stopping")},
        {QStringLiteral("runtime_active"), input.runtimeActive},
        {QStringLiteral("active_engine_count"), activeEngineCount},
        {QStringLiteral("requested_job_count"), 0},
        {QStringLiteral("close_positions_requested"), input.closePositions},
        {QStringLiteral("source"), source},
        {QStringLiteral("status_message"), message},
    };
}

QJsonObject buildRuntimeIdleAfterStopResult(
    bool closePositionsRequested,
    const QString &source,
    const QString &statusMessage) {
    QString message = redactText(statusMessage.trimmed());
    if (message.isEmpty()) {
        message = closePositionsRequested
            ? QStringLiteral("Runtime idle after stop request.")
            : QStringLiteral("Runtime idle.");
    }
    return {
        {QStringLiteral("accepted"), true},
        {QStringLiteral("action"), QStringLiteral("sync")},
        {QStringLiteral("lifecycle_phase"), QStringLiteral("idle")},
        {QStringLiteral("runtime_active"), false},
        {QStringLiteral("active_engine_count"), 0},
        {QStringLiteral("requested_job_count"), 0},
        {QStringLiteral("close_positions_requested"), false},
        {QStringLiteral("source"), source.trimmed().isEmpty() ? QStringLiteral("service") : redactText(source.trimmed())},
        {QStringLiteral("status_message"), message},
    };
}

QJsonObject buildConnectorOrderCircuitBreakerSnapshot(
    const QJsonObject &raw,
    const QString &source,
    const QDateTime &now) {
    const QString rawState = stateFromRaw(raw);
    const bool active = raw.value(QStringLiteral("active")).toBool(false)
        || rawState == QStringLiteral("open")
        || rawState == QStringLiteral("paused")
        || rawState == QStringLiteral("tripped");
    QString message = redactText(raw.value(QStringLiteral("message")).toString().trimmed());
    if (active && message.isEmpty()) {
        message = QStringLiteral("Connector health circuit breaker paused trading.");
    }
    const QString nowText = currentIso(now);
    const int threshold = std::max(1, raw.value(QStringLiteral("block_threshold")).toInt(2));
    const double window = qIsFinite(raw.value(QStringLiteral("block_window_seconds")).toDouble(60.0))
        ? std::max(1.0, raw.value(QStringLiteral("block_window_seconds")).toDouble(60.0))
        : 60.0;
    return compactObject({
        {QStringLiteral("active"), active},
        {QStringLiteral("state"), active ? QStringLiteral("open") : QStringLiteral("closed")},
        {QStringLiteral("reason"), raw.value(QStringLiteral("reason")).toString().trimmed()},
        {QStringLiteral("message"), message},
        {QStringLiteral("block_count"), std::max(0, raw.value(QStringLiteral("block_count")).toInt(0))},
        {QStringLiteral("block_threshold"), threshold},
        {QStringLiteral("block_window_seconds"), window},
        {QStringLiteral("tripped_at"), raw.value(QStringLiteral("tripped_at")).toString(active ? nowText : QString())},
        {QStringLiteral("cleared_at"), raw.value(QStringLiteral("cleared_at")).toString()},
        {QStringLiteral("source"), raw.value(QStringLiteral("source")).toString(source.trimmed().isEmpty() ? QStringLiteral("service") : source.trimmed())},
        {QStringLiteral("symbol"), raw.value(QStringLiteral("symbol")).toString().trimmed().toUpper()},
        {QStringLiteral("interval"), raw.value(QStringLiteral("interval")).toString().trimmed()},
        {QStringLiteral("side"), raw.value(QStringLiteral("side")).toString().trimmed().toUpper()},
        {QStringLiteral("account_type"), raw.value(QStringLiteral("account_type")).toString().trimmed()},
        {QStringLiteral("connector_health"), redactValue(raw.value(QStringLiteral("connector_health")))},
        {QStringLiteral("connector_state"), redactValue(raw.value(QStringLiteral("connector_state")))},
        {QStringLiteral("reset_blocked"), raw.value(QStringLiteral("reset_blocked")).toBool(false)},
        {QStringLiteral("reset_blocked_reason"), redactText(raw.value(QStringLiteral("reset_blocked_reason")).toString().trimmed())},
        {QStringLiteral("reset_blocked_at"), raw.value(QStringLiteral("reset_blocked_at")).toString().trimmed()},
        {QStringLiteral("last_event"), redactValue(raw.value(QStringLiteral("last_event")))},
        {QStringLiteral("generated_at"), nowText},
    });
}

QJsonObject buildConnectorOrderCircuitIncident(
    const QString &action,
    const QJsonObject &snapshot,
    const QString &source,
    const QString &message,
    const QDateTime &timestamp) {
    const QString actionText = action.trimmed().isEmpty() ? QStringLiteral("trip") : action.trimmed();
    return compactObject({
        {QStringLiteral("ts"), currentIso(timestamp)},
        {QStringLiteral("event"), QStringLiteral("connector_order_circuit_%1").arg(actionText)},
        {QStringLiteral("action"), actionText},
        {QStringLiteral("source"), source.trimmed().isEmpty() ? QStringLiteral("service") : source.trimmed()},
        {QStringLiteral("message"), redactText(message)},
        {QStringLiteral("active"), snapshot.value(QStringLiteral("active")).toBool(false)},
        {QStringLiteral("state"), snapshot.value(QStringLiteral("state")).toString()},
        {QStringLiteral("reason"), snapshot.value(QStringLiteral("reason")).toString()},
        {QStringLiteral("block_count"), snapshot.value(QStringLiteral("block_count")).toInt(0)},
        {QStringLiteral("block_threshold"), snapshot.value(QStringLiteral("block_threshold")).toInt(2)},
        {QStringLiteral("symbol"), snapshot.value(QStringLiteral("symbol")).toString()},
        {QStringLiteral("interval"), snapshot.value(QStringLiteral("interval")).toString()},
        {QStringLiteral("side"), snapshot.value(QStringLiteral("side")).toString()},
        {QStringLiteral("connector_health"), redactValue(snapshot.value(QStringLiteral("connector_health")))},
        {QStringLiteral("connector_state"), redactValue(snapshot.value(QStringLiteral("connector_state")))},
        {QStringLiteral("circuit"), redactValue(snapshot)},
    });
}

QString connectorOrderCircuitIncidentJsonLine(const QJsonObject &incident) {
    return QString::fromUtf8(QJsonDocument(compactObject(incident)).toJson(QJsonDocument::Compact));
}

QJsonObject parseConnectorOrderCircuitIncidentLines(const QStringList &lines, int limit) {
    const int maxItems = std::max(1, std::min(200, limit));
    QJsonArray events;
    int totalRead = 0;
    auto appendEvent = [&events, maxItems](const QJsonObject &event) {
        while (events.size() >= maxItems) {
            events.removeAt(0);
        }
        events.append(redactValue(event));
    };
    for (int i = 0; i < lines.size(); ++i) {
        const QString text = lines.at(i).trimmed();
        if (text.isEmpty()) {
            continue;
        }
        ++totalRead;
        QJsonParseError error{};
        const QJsonDocument doc = QJsonDocument::fromJson(text.toUtf8(), &error);
        if (error.error != QJsonParseError::NoError) {
            appendEvent({
                {QStringLiteral("event"), QStringLiteral("connector_order_circuit_log_parse_error")},
                {QStringLiteral("action"), QStringLiteral("parse_error")},
                {QStringLiteral("line_number"), i + 1},
                {QStringLiteral("message"), QStringLiteral("Could not parse incident log line: %1").arg(redactText(error.errorString()))},
                {QStringLiteral("raw"), redactText(text.left(500))},
            });
            continue;
        }
        if (!doc.isObject()) {
            appendEvent({
                {QStringLiteral("event"), QStringLiteral("connector_order_circuit_log_parse_error")},
                {QStringLiteral("action"), QStringLiteral("parse_error")},
                {QStringLiteral("line_number"), i + 1},
                {QStringLiteral("message"), QStringLiteral("Incident log line was not a JSON object.")},
                {QStringLiteral("value"), redactValue(doc.isArray() ? QJsonValue(doc.array()) : QJsonValue())},
            });
            continue;
        }
        appendEvent(doc.object());
    }
    return compactObject({
        {QStringLiteral("limit"), maxItems},
        {QStringLiteral("count"), events.size()},
        {QStringLiteral("total_read"), totalRead},
        {QStringLiteral("events"), events},
        {QStringLiteral("last_event"), events.isEmpty() ? QJsonValue{} : events.last()},
    });
}

} // namespace NativeOrderSafety
