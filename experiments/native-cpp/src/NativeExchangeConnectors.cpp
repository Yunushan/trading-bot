#include "NativeExchangeConnectors.h"

#include "NativeOrderSafety.h"
#include "generated/PythonParityContract.h"

#include <QJsonArray>
#include <QRegularExpression>

namespace {

QString parityString(std::string_view value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

QString firstNonEmpty(const QStringList &values, const QString &fallback = {}) {
    for (const QString &value : values) {
        const QString text = value.trimmed();
        if (!text.isEmpty()) {
            return text;
        }
    }
    return fallback;
}

bool containsSupportKey(const QStringList &values, const QString &target) {
    const QString key = NativeExchangeConnectors::supportKey(target);
    for (const QString &value : values) {
        if (NativeExchangeConnectors::supportKey(value) == key) {
            return true;
        }
    }
    return false;
}

double numberAfter(const QString &message, const QString &prefix, bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    const QString lower = message.toLower();
    const int idx = lower.indexOf(prefix.toLower());
    if (idx < 0) {
        return 0.0;
    }
    QString tail = lower.mid(idx + prefix.size()).trimmed();
    QString digits;
    for (const QChar ch : tail) {
        if (ch.isDigit() || ch == QLatin1Char('.')) {
            digits.append(ch);
        } else if (!digits.isEmpty()) {
            break;
        }
    }
    bool ok = false;
    const double parsed = digits.toDouble(&ok);
    if (okOut) {
        *okOut = ok;
    }
    return ok ? parsed : 0.0;
}

QJsonObject redactedObject(const QJsonValue &value) {
    return NativeOrderSafety::redactValue(value).toObject();
}

QString nonEmptyOrRedacted(const QString &value, const QString &fallback) {
    const QString text = value.trimmed();
    return text.isEmpty() ? fallback : NativeOrderSafety::redactText(text);
}

} // namespace

namespace NativeExchangeConnectors {

QString defaultConnectorBackend() {
    return QStringLiteral("binance-sdk-derivatives-trading-usds-futures");
}

QString supportKey(const QString &value) {
    return QString(value).trimmed().toLower().replace(QLatin1Char('_'), QLatin1Char('-'));
}

QStringList supportedExchanges() {
    return {
        QStringLiteral("Binance"),
        QStringLiteral("Bybit"),
        QStringLiteral("OKX"),
        QStringLiteral("Bitget"),
        QStringLiteral("Gate"),
        QStringLiteral("MEXC"),
        QStringLiteral("KuCoin"),
        QStringLiteral("HTX"),
        QStringLiteral("Crypto.com Exchange"),
        QStringLiteral("Kraken"),
        QStringLiteral("Bitfinex"),
    };
}

QStringList supportedConnectorBackends() {
    QStringList values;
    for (const auto &option : PythonParityContract::kPythonConnectorOptions) {
        values.append(parityString(option.key));
    }
    return values;
}

QString ccxtExchangeIdFor(const QString &exchange) {
    const QString key = supportKey(exchange);
    if (key == QStringLiteral("bybit")) return QStringLiteral("bybit");
    if (key == QStringLiteral("okx")) return QStringLiteral("okx");
    if (key == QStringLiteral("bitget")) return QStringLiteral("bitget");
    if (key == QStringLiteral("gate") || key == QStringLiteral("gate.io") || key == QStringLiteral("gateio")) {
        return QStringLiteral("gateio");
    }
    if (key == QStringLiteral("mexc")) return QStringLiteral("mexc");
    if (key == QStringLiteral("kucoin")) return QStringLiteral("kucoin");
    if (key == QStringLiteral("htx")) return QStringLiteral("htx");
    if (key == QStringLiteral("crypto.com")
        || key == QStringLiteral("crypto.com exchange")
        || key == QStringLiteral("cryptocom")) {
        return QStringLiteral("cryptocom");
    }
    if (key == QStringLiteral("kraken")) return QStringLiteral("kraken");
    if (key == QStringLiteral("bitfinex")) return QStringLiteral("bitfinex");
    return {};
}

QString normalizeConnectorBackend(const QString &value) {
    const QString key = supportKey(value);
    if (key.isEmpty()) {
        return defaultConnectorBackend();
    }
    for (const auto &option : PythonParityContract::kPythonConnectorOptions) {
        const QString optionKey = parityString(option.key);
        if (supportKey(optionKey) == key) {
            return optionKey;
        }
    }
    return key;
}

QJsonObject buildExchangeSupportPayload(
    const ExchangeSupportInput &config,
    const ExchangeSupportInput &snapshot) {
    const QString selectedExchange = firstNonEmpty(
        {snapshot.selectedExchange, config.selectedExchange},
        QStringLiteral("Unknown"));
    const QString connectorBackend = firstNonEmpty(
        {snapshot.connectorBackend, config.connectorBackend},
        QStringLiteral("Unknown"));
    const QString selectedForexBroker = firstNonEmpty(
        {snapshot.selectedForexBroker, config.selectedForexBroker});

    const QStringList exchanges = supportedExchanges();
    const QStringList backends = supportedConnectorBackends();
    const QStringList brokers = {QStringLiteral("OANDA"), QStringLiteral("FXCM"), QStringLiteral("IG")};
    const QString exchangeKey = supportKey(selectedExchange);
    const QString backendKey = supportKey(connectorBackend);
    const QString brokerKey = supportKey(selectedForexBroker);
    const QString ccxtExchangeId = ccxtExchangeIdFor(selectedExchange);
    const bool usesBroker = !selectedForexBroker.trimmed().isEmpty();
    const bool exchangeSupported = containsSupportKey(exchanges, selectedExchange);
    const bool backendSupported = containsSupportKey(backends, connectorBackend);
    const bool brokerSupported = selectedForexBroker.trimmed().isEmpty()
        || containsSupportKey(brokers, selectedForexBroker);
    const bool usesCcxtDiagnostics = !ccxtExchangeId.isEmpty() && backendKey == QStringLiteral("ccxt");
    const bool usesCcxtOrderRouting = usesCcxtDiagnostics;
    QString expectedBrokerBackend;
    if (brokerKey == QStringLiteral("oanda")) {
        expectedBrokerBackend = QStringLiteral("oanda-rest");
    } else if (brokerKey == QStringLiteral("fxcm")) {
        expectedBrokerBackend = QStringLiteral("fxcmpy");
    } else if (brokerKey == QStringLiteral("ig")) {
        expectedBrokerBackend = QStringLiteral("ig-rest");
    }
    const bool usesBrokerOrderRouting = !expectedBrokerBackend.isEmpty() && backendKey == expectedBrokerBackend;
    const bool orderExecutionExchange = exchangeKey == QStringLiteral("binance");
    const bool marketDataSupported = backendSupported
        && ((!usesBroker && brokerSupported && (orderExecutionExchange || usesCcxtDiagnostics))
            || (usesBroker && usesBrokerOrderRouting));
    const bool accountSnapshotSupported = marketDataSupported;
    const bool orderRoutingSupported = backendSupported
        && ((!usesBroker && brokerSupported && (orderExecutionExchange || usesCcxtOrderRouting))
            || (usesBroker && usesBrokerOrderRouting));
    const bool orderExecutionSupported =
        (!usesBroker && exchangeSupported && brokerSupported && orderRoutingSupported)
        || (usesBroker && brokerSupported && orderRoutingSupported);
    const bool liveEvidenceRequired = orderExecutionSupported && (usesBroker || !orderExecutionExchange);

    QJsonArray reasons;
    QJsonArray capabilityGaps;
    if (!usesBroker && !exchangeSupported) {
        reasons.append(QStringLiteral("Exchange '%1' is not implemented by this runtime.").arg(selectedExchange));
    }
    if (!backendSupported) {
        reasons.append(QStringLiteral("Connector backend '%1' is not implemented by this runtime.").arg(connectorBackend));
    }
    if (!brokerSupported) {
        reasons.append(QStringLiteral("Forex broker '%1' is not implemented by this runtime.").arg(selectedForexBroker));
    }
    if (usesBroker && brokerSupported && backendSupported && !usesBrokerOrderRouting) {
        if (!expectedBrokerBackend.isEmpty()) {
            capabilityGaps.append(
                QStringLiteral("Broker '%1' order routing requires connector backend '%2'.")
                    .arg(selectedForexBroker, expectedBrokerBackend));
        } else {
            capabilityGaps.append(
                QStringLiteral("Broker '%1' order routing requires a provider connector.")
                    .arg(selectedForexBroker));
        }
    }
    if (!usesBroker && exchangeSupported && backendSupported && brokerSupported && !orderExecutionSupported) {
        capabilityGaps.append(
            QStringLiteral("Order routing for exchange '%1' requires a provider connector backend.")
                .arg(selectedExchange));
    }
    if (liveEvidenceRequired) {
        if (usesBroker) {
            capabilityGaps.append(
                QStringLiteral("Official live support for broker '%1' requires a passed connector evidence artifact.")
                    .arg(selectedForexBroker));
        } else {
            capabilityGaps.append(
                QStringLiteral("Official live support for exchange '%1' requires a passed connector evidence artifact.")
                    .arg(selectedExchange));
        }
    }
    QJsonArray exchangeArray;
    for (const QString &exchange : exchanges) {
        exchangeArray.append(exchange);
    }
    QJsonArray backendArray;
    for (const QString &backend : backends) {
        backendArray.append(backend);
    }
    QJsonArray ccxtDiagnosticArray;
    for (const QString &exchange : {
             QStringLiteral("Bybit"),
             QStringLiteral("OKX"),
             QStringLiteral("Bitget"),
             QStringLiteral("Gate"),
             QStringLiteral("MEXC"),
             QStringLiteral("KuCoin"),
             QStringLiteral("HTX"),
             QStringLiteral("Crypto.com Exchange"),
             QStringLiteral("Kraken"),
             QStringLiteral("Bitfinex"),
         }) {
        ccxtDiagnosticArray.append(exchange);
    }
    return {
        {QStringLiteral("selected_exchange"), selectedExchange},
        {QStringLiteral("connector_backend"), connectorBackend},
        {QStringLiteral("selected_forex_broker"), selectedForexBroker},
        {QStringLiteral("ccxt_exchange_id"), ccxtExchangeId},
        {QStringLiteral("exchange_supported"), exchangeSupported},
        {QStringLiteral("connector_backend_supported"), backendSupported},
        {QStringLiteral("broker_supported"), brokerSupported},
        {QStringLiteral("market_data_supported"), marketDataSupported},
        {QStringLiteral("account_snapshot_supported"), accountSnapshotSupported},
        {QStringLiteral("order_routing_supported"), orderRoutingSupported},
        {QStringLiteral("order_execution_supported"), orderExecutionSupported},
        {QStringLiteral("live_evidence_required"), liveEvidenceRequired},
        {QStringLiteral("trading_supported"), orderExecutionSupported},
        {QStringLiteral("support_tier"), orderExecutionSupported
            ? (liveEvidenceRequired ? QStringLiteral("order-routing-evidence-required") : QStringLiteral("full-trading"))
            : (marketDataSupported || accountSnapshotSupported ? QStringLiteral("diagnostics-only") : QStringLiteral("unsupported"))},
        {QStringLiteral("capability_gaps"), capabilityGaps},
        {QStringLiteral("unsupported_reasons"), reasons},
        {QStringLiteral("supported_exchanges"), exchangeArray},
        {QStringLiteral("supported_connector_backends"), backendArray},
        {QStringLiteral("supported_forex_brokers"), QJsonArray{
            QStringLiteral("OANDA"),
            QStringLiteral("FXCM"),
            QStringLiteral("IG"),
        }},
        {QStringLiteral("ccxt_diagnostic_exchanges"), ccxtDiagnosticArray},
        {QStringLiteral("ccxt_order_routing_exchanges"), ccxtDiagnosticArray},
        {QStringLiteral("order_execution_exchanges"), QJsonArray{QStringLiteral("Binance")}},
        {QStringLiteral("broker_order_routing_brokers"), QJsonArray{
            QStringLiteral("OANDA"),
            QStringLiteral("FXCM"),
            QStringLiteral("IG"),
        }},
        {QStringLiteral("broker_order_routing_backends"), QJsonObject{
            {QStringLiteral("oanda"), QStringLiteral("oanda-rest")},
            {QStringLiteral("fxcm"), QStringLiteral("fxcmpy")},
            {QStringLiteral("ig"), QStringLiteral("ig-rest")},
        }},
    };
}

double estimateRequestWeight(const QString &path) {
    const QString lower = path.trimmed().toLower();
    if (lower.isEmpty()) {
        return 1.0;
    }
    if (lower.contains(QStringLiteral("exchangeinfo"))) {
        return 10.0;
    }
    if (lower.contains(QStringLiteral("balance")) || lower.contains(QStringLiteral("account"))) {
        return 5.0;
    }
    if (lower.contains(QStringLiteral("position"))) {
        return 5.0;
    }
    if (lower.contains(QStringLiteral("klines"))) {
        return 4.0;
    }
    if (lower.contains(QStringLiteral("ticker"))) {
        return lower.contains(QStringLiteral("price")) ? 1.0 : 2.0;
    }
    if (lower.contains(QStringLiteral("margin")) || lower.contains(QStringLiteral("leverage")) || lower.contains(QStringLiteral("order"))) {
        return 1.0;
    }
    return 2.0;
}

QString environmentTag(const QString &modeValue) {
    const QString text = modeValue.toLower();
    return (text.contains(QStringLiteral("test")) || text.contains(QStringLiteral("demo")))
        ? QStringLiteral("testnet")
        : QStringLiteral("live");
}

QString accountTag(const QString &accountValue) {
    return accountValue.trimmed().toUpper().startsWith(QStringLiteral("SPOT"))
        ? QStringLiteral("spot")
        : QStringLiteral("futures");
}

QJsonObject limiterSettingsFor(const QString &envTag, const QString &accountTagValue) {
    if (envTag == QStringLiteral("testnet")) {
        return {
            {QStringLiteral("max_per_minute"), 180.0},
            {QStringLiteral("min_interval"), 0.65},
            {QStringLiteral("safety_margin"), 0.8},
        };
    }
    if (accountTagValue == QStringLiteral("spot")) {
        return {
            {QStringLiteral("max_per_minute"), 900.0},
            {QStringLiteral("min_interval"), 0.25},
            {QStringLiteral("safety_margin"), 0.85},
        };
    }
    return {
        {QStringLiteral("max_per_minute"), 1100.0},
        {QStringLiteral("min_interval"), 0.2},
        {QStringLiteral("safety_margin"), 0.9},
    };
}

double extractBanUntil(const QString &message, double nowEpoch, bool *ok) {
    if (ok) {
        *ok = false;
    }
    const QString text = message.trimmed();
    if (text.isEmpty()) {
        return 0.0;
    }
    bool parsed = false;
    const double banned = numberAfter(text, QStringLiteral("banned until "), &parsed);
    if (parsed) {
        if (ok) {
            *ok = true;
        }
        if (banned > 1e12) {
            return banned / 1000.0;
        }
        if (banned > 1e5) {
            return banned;
        }
        return nowEpoch + banned;
    }
    const QString lower = text.toLower();
    const double after = numberAfter(text, QStringLiteral("after "), &parsed);
    double wait = parsed ? after : numberAfter(text, QStringLiteral("wait "), &parsed);
    if (parsed) {
        if (ok) {
            *ok = true;
        }
        if (lower.contains(QStringLiteral("ms")) || lower.contains(QStringLiteral("milliseconds"))) {
            return nowEpoch + qMax(wait / 1000.0, 0.0);
        }
        if (lower.contains(QLatin1Char('s')) || lower.contains(QStringLiteral("seconds"))) {
            return nowEpoch + qMax(wait, 0.0);
        }
    }
    return 0.0;
}

QJsonObject buildHttpBackoff(
    int statusCode,
    int code,
    const QString &message,
    double retryAfter,
    double nowEpoch) {
    const QString lower = message.toLower();
    const bool triggered = code == -1003
        || code == 429
        || statusCode == 418
        || statusCode == 429
        || lower.contains(QStringLiteral("banned until"))
        || lower.contains(QStringLiteral("too many requests"))
        || lower.contains(QStringLiteral("too frequent"))
        || lower.contains(QStringLiteral("frequency"));
    if (!triggered) {
        return {{QStringLiteral("triggered"), false}};
    }
    bool parsed = false;
    double until = extractBanUntil(message, nowEpoch, &parsed);
    if (!parsed && retryAfter >= 0.0) {
        until = nowEpoch + qMax(retryAfter, 0.0);
        parsed = true;
    }
    if (!parsed) {
        until = nowEpoch + 8.0;
    }
    return {
        {QStringLiteral("triggered"), true},
        {QStringLiteral("ban_until"), until},
        {QStringLiteral("seconds_until_unban"), qMax(until - nowEpoch, 0.0)},
        {QStringLiteral("category"), QStringLiteral("rate_limited")},
    };
}

QJsonObject buildConnectorHealthSnapshot(const QJsonObject &input) {
    QJsonObject lastError;
    const bool hasLastError = input.value(QStringLiteral("last_error")).isObject();
    if (hasLastError) {
        lastError = redactedObject(input.value(QStringLiteral("last_error")));
    }
    const QString category = lastError.value(QStringLiteral("category")).toString().trimmed().toLower();
    const bool retryable = lastError.value(QStringLiteral("retryable")).toBool(false);
    const bool credentialsPresent = input.value(QStringLiteral("credentials_present")).toBool(false);
    const double secondsUntilUnban = qMax(0.0, input.value(QStringLiteral("seconds_until_unban")).toDouble(0.0));
    const bool networkOffline = input.value(QStringLiteral("network_offline")).toBool(false);

    QString health = credentialsPresent ? QStringLiteral("ok") : QStringLiteral("unknown");
    QString state = credentialsPresent ? QStringLiteral("ready") : QStringLiteral("missing_credentials");
    if (networkOffline) {
        health = QStringLiteral("error");
        state = QStringLiteral("network_offline");
    } else if (secondsUntilUnban > 0.0) {
        health = QStringLiteral("warning");
        state = QStringLiteral("rate_limited");
    } else if (hasLastError) {
        if (category == QStringLiteral("auth")) {
            health = QStringLiteral("error");
            state = QStringLiteral("auth_error");
        } else if (category == QStringLiteral("rate_limited")) {
            health = QStringLiteral("warning");
            state = QStringLiteral("rate_limited");
        } else if (retryable) {
            health = QStringLiteral("warning");
            state = category.isEmpty() ? QStringLiteral("exchange_warning") : category;
        } else {
            health = QStringLiteral("error");
            state = category.isEmpty() ? QStringLiteral("exchange_error") : category;
        }
    }

    QJsonObject orderAudit;
    const bool hasOrderAudit = input.value(QStringLiteral("order_audit")).isObject();
    if (hasOrderAudit) {
        orderAudit = redactedObject(input.value(QStringLiteral("order_audit")));
        if (orderAudit.contains(QStringLiteral("last_write_error")) && health != QStringLiteral("error")) {
            health = QStringLiteral("warning");
            if (state == QStringLiteral("ready")
                || state == QStringLiteral("missing_credentials")
                || state == QStringLiteral("unknown")) {
                state = QStringLiteral("order_audit_write_failed");
            }
        }
    }

    QJsonObject payload{
        {QStringLiteral("health"), health},
        {QStringLiteral("state"), state},
        {QStringLiteral("generated_at"), input.value(QStringLiteral("generated_at")).toDouble()},
        {QStringLiteral("source"), QStringLiteral("binance-wrapper")},
        {QStringLiteral("selected_exchange"), QStringLiteral("Binance")},
        {QStringLiteral("connector_backend"), nonEmptyOrRedacted(input.value(QStringLiteral("connector_backend")).toString(), QStringLiteral("Unknown"))},
        {QStringLiteral("account_type"), nonEmptyOrRedacted(input.value(QStringLiteral("account_type")).toString(), QStringLiteral("Unknown"))},
        {QStringLiteral("mode"), nonEmptyOrRedacted(input.value(QStringLiteral("mode")).toString(), QStringLiteral("Unknown"))},
        {QStringLiteral("rate_limit"), QJsonObject{
            {QStringLiteral("active"), secondsUntilUnban > 0.0},
            {QStringLiteral("seconds_until_unban"), secondsUntilUnban},
            {QStringLiteral("ban_until"), secondsUntilUnban > 0.0
                ? QJsonValue(input.value(QStringLiteral("generated_at")).toDouble() + secondsUntilUnban)
                : QJsonValue{}},
        }},
        {QStringLiteral("network"), QJsonObject{
            {QStringLiteral("offline"), networkOffline},
            {QStringLiteral("offline_since"), input.value(QStringLiteral("network_offline_since"))},
            {QStringLiteral("offline_hits"), input.value(QStringLiteral("network_offline_hits")).toInt(0)},
        }},
        {QStringLiteral("last_error"), hasLastError ? QJsonValue(lastError) : QJsonValue{}},
    };
    if (hasOrderAudit) {
        payload.insert(QStringLiteral("order_audit"), orderAudit);
    }
    return NativeOrderSafety::redactValue(payload).toObject();
}

} // namespace NativeExchangeConnectors
