#include "TradingBotWindowSupport.h"

#include "generated/PythonParityContract.h"

#include <QColor>
#include <QComboBox>
#include <QByteArray>
#include <QEventLoop>
#include <QHostAddress>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QSet>
#include <QSignalBlocker>
#include <QStandardItemModel>
#include <QTableWidgetItem>
#include <QTimer>
#include <QUrl>
#include <QUrlQuery>
#include <QVector>
#include <QtGlobal>

#include <algorithm>

namespace {

constexpr int kTableCellNumericRole = Qt::UserRole + 2;
constexpr int kTableCellRawNumericRole = Qt::UserRole + 4;

QString normalizeExchangeKey(QString value) {
    value = value.trimmed();
    const int badgePos = value.indexOf('(');
    if (badgePos > 0) {
        value = value.left(badgePos).trimmed();
    }

    const QString key = value.toLower();
    if (key == "binance") return "Binance";
    if (key == "bybit") return "Bybit";
    if (key == "okx") return "OKX";
    if (key == "gate") return "Gate";
    if (key == "bitget") return "Bitget";
    if (key == "mexc") return "MEXC";
    if (key == "kucoin") return "KuCoin";
    if (key == "coinbase") return "Coinbase";
    if (key == "htx") return "HTX";
    if (key == "kraken") return "Kraken";
    if (key == "tradingview") return "TradingView";
    return value;
}

struct ConnectorOption {
    QString label;
    QString key;
};

const QString kConnectorUsdsFutures = QStringLiteral("binance-sdk-derivatives-trading-usds-futures");
const QString kConnectorCoinFutures = QStringLiteral("binance-sdk-derivatives-trading-coin-futures");
const QString kConnectorSpot = QStringLiteral("binance-sdk-spot");
const QString kConnectorBinanceConnector = QStringLiteral("binance-connector");
const QString kConnectorCcxt = QStringLiteral("ccxt");
const QString kConnectorPyBinance = QStringLiteral("python-binance");
const QString kConnectorLegacyGateway = QStringLiteral("gateway");
const QString kConnectorLegacyCustom = QStringLiteral("custom");

const QSet<QString> kFuturesConnectorKeys = {
    kConnectorUsdsFutures,
    kConnectorCoinFutures,
    kConnectorBinanceConnector,
    kConnectorCcxt,
    kConnectorPyBinance,
};

const QSet<QString> kSpotConnectorKeys = {
    kConnectorSpot,
    kConnectorBinanceConnector,
    kConnectorCcxt,
    kConnectorPyBinance,
};

bool connectorAllowedForAccount(const QString &connectorKey, bool futures) {
    return futures ? kFuturesConnectorKeys.contains(connectorKey) : kSpotConnectorKeys.contains(connectorKey);
}

QString normalizeConnectorBackend(const QString &value) {
    const QString textRaw = value.trimmed();
    if (textRaw.isEmpty()) {
        return kConnectorUsdsFutures;
    }
    const QString text = textRaw.toLower();

    if (text.contains(QStringLiteral("gateway"))) {
        return kConnectorLegacyGateway;
    }
    if (text.contains(QStringLiteral("custom")) || text.startsWith(QStringLiteral("http"))) {
        return kConnectorLegacyCustom;
    }

    if (text == kConnectorUsdsFutures
        || text == QStringLiteral("binance_sdk_derivatives_trading_usds_futures")
        || (text.contains(QStringLiteral("sdk"))
            && text.contains(QStringLiteral("future"))
            && (text.contains(QStringLiteral("usd")) || text.contains(QStringLiteral("usds"))))) {
        return kConnectorUsdsFutures;
    }
    if (text == kConnectorCoinFutures
        || text == QStringLiteral("binance_sdk_derivatives_trading_coin_futures")
        || (text.contains(QStringLiteral("sdk"))
            && text.contains(QStringLiteral("coin"))
            && text.contains(QStringLiteral("future")))) {
        return kConnectorCoinFutures;
    }
    if (text == kConnectorSpot
        || text == QStringLiteral("binance_sdk_spot")
        || (text.contains(QStringLiteral("sdk")) && text.contains(QStringLiteral("spot")))) {
        return kConnectorSpot;
    }
    if (text == QStringLiteral("ccxt") || text.contains(QStringLiteral("ccxt"))) {
        return kConnectorCcxt;
    }
    if (text == kConnectorBinanceConnector
        || text.contains(QStringLiteral("connector"))
        || text.contains(QStringLiteral("official"))) {
        return kConnectorBinanceConnector;
    }
    if (text.contains(QStringLiteral("python")) && text.contains(QStringLiteral("binance"))) {
        return kConnectorPyBinance;
    }
    return kConnectorUsdsFutures;
}

QString normalizeBaseUrl(QString url) {
    url = url.trimmed();
    while (url.endsWith('/')) {
        url.chop(1);
    }
    return url;
}

QString firstEnvValue(const QStringList &keys) {
    for (const QString &key : keys) {
        const QString value = qEnvironmentVariable(key.toUtf8().constData()).trimmed();
        if (!value.isEmpty()) {
            return value;
        }
    }
    return QString();
}

QString environmentValue(const char *name, const QString &fallback = {}) {
    const QString value = qEnvironmentVariable(name).trimmed();
    return value.isEmpty() ? fallback : value;
}

bool environmentFlag(const char *name) {
    const QString value = environmentValue(name).toLower();
    return value == QStringLiteral("1") || value == QStringLiteral("true")
        || value == QStringLiteral("yes") || value == QStringLiteral("on");
}

bool isLoopbackServiceApiHost(const QString &host) {
    if (host.compare(QStringLiteral("localhost"), Qt::CaseInsensitive) == 0) {
        return true;
    }
    QHostAddress address;
    return address.setAddress(host) && address.isLoopback();
}

QString validateServiceApiEndpoint(const QString &baseUrl, const QString &token) {
    const QUrl parsed(baseUrl);
    if (!parsed.isValid() || parsed.host().trimmed().isEmpty()) {
        return QStringLiteral("Invalid Service API base URL: %1").arg(baseUrl);
    }
    const QString scheme = parsed.scheme().toLower();
    if (scheme != QStringLiteral("http") && scheme != QStringLiteral("https")) {
        return QStringLiteral("Unsupported Service API URL scheme: %1").arg(parsed.scheme());
    }
    if (isLoopbackServiceApiHost(parsed.host())) {
        return QString();
    }
    if (!environmentFlag("BOT_DESKTOP_SERVICE_API_ALLOW_PUBLIC_NETWORK")) {
        return QStringLiteral(
            "Public service API endpoints are disabled. Use localhost/127.0.0.1 or set "
            "BOT_DESKTOP_SERVICE_API_ALLOW_PUBLIC_NETWORK=1.");
    }
    if (token.trimmed().isEmpty()) {
        return QStringLiteral("BOT_SERVICE_API_TOKEN is required for a non-loopback service API endpoint.");
    }
    return QString();
}

QString parityString(std::string_view value) {
    return QString::fromUtf8(value.data(), static_cast<int>(value.size()));
}

QVector<ConnectorOption> pythonConnectorOptions() {
    QVector<ConnectorOption> options;
    options.reserve(static_cast<int>(PythonParityContract::kPythonConnectorOptions.size()));
    for (const auto &connector : PythonParityContract::kPythonConnectorOptions) {
        options.append({parityString(connector.label), parityString(connector.key)});
    }
    return options;
}

template <std::size_t N>
QStringList parityStringList(const std::array<std::string_view, N> &values) {
    QStringList result;
    result.reserve(static_cast<int>(values.size()));
    for (const std::string_view value : values) {
        result.append(parityString(value));
    }
    return result;
}

QStringList parityCsvStringList(std::string_view value) {
    return parityString(value).split(QLatin1Char(','), Qt::SkipEmptyParts);
}

template <typename OptionArray>
QStringList parityUiOptionKeys(const OptionArray &options) {
    QStringList result;
    result.reserve(static_cast<int>(options.size()));
    for (const auto &option : options) {
        result.append(parityString(option.key));
    }
    return result;
}

template <typename OptionArray>
QStringList parityUiOptionLabels(const OptionArray &options) {
    QStringList result;
    result.reserve(static_cast<int>(options.size()));
    for (const auto &option : options) {
        result.append(parityString(option.label));
    }
    return result;
}

const PythonParityContract::PythonParityDomain *parityDomainByKey(const QString &domainKey) {
    const QString normalized = domainKey.trimmed();
    for (const auto &domain : PythonParityContract::kPythonParityDomains) {
        if (parityString(domain.key) == normalized) {
            return &domain;
        }
    }
    return nullptr;
}

const PythonParityContract::PythonServiceRouteSchema *serviceRouteSchemaByName(const QString &routeName) {
    const QString normalized = routeName.trimmed();
    for (const auto &schema : PythonParityContract::kPythonServiceRouteSchemas) {
        if (parityString(schema.name) == normalized) {
            return &schema;
        }
    }
    return nullptr;
}

} // namespace

namespace TradingBotWindowSupport {

bool isTestnetModeLabel(const QString &modeText) {
    const QString modeNorm = modeText.trimmed().toLower();
    return modeNorm == QStringLiteral("demo")
        || modeNorm.contains("testnet")
        || modeNorm == QStringLiteral("test")
        || modeNorm.contains("sandbox")
        || modeNorm.contains("binance demo");
}

bool isPaperTradingModeLabel(const QString &modeText) {
    const QString modeNorm = modeText.trimmed().toLower();
    if (isTestnetModeLabel(modeText)) {
        return false;
    }
    return modeNorm == QStringLiteral("paper")
        || modeNorm == QStringLiteral("paper local")
        || modeNorm.contains("paper local")
        || modeNorm.contains("paper trading");
}

QString selectedDashboardExchange(const QComboBox *combo) {
    if (!combo) {
        return QStringLiteral("Binance");
    }
    QString value = combo->currentData().toString().trimmed();
    if (value.isEmpty()) {
        value = combo->currentText().trimmed();
    }
    value = normalizeExchangeKey(value);
    return value.isEmpty() ? QStringLiteral("Binance") : value;
}

bool exchangeUsesBinanceApi(const QString &exchangeKey) {
    return normalizeExchangeKey(exchangeKey).compare(QStringLiteral("Binance"), Qt::CaseInsensitive) == 0;
}

QStringList placeholderSymbolsForExchange(const QString &exchangeKey, bool futures) {
    const QStringList pythonDefaults = pythonSourceDefaultExecutionSymbols();
    if (!pythonDefaults.isEmpty()) {
        return pythonDefaults;
    }
    Q_UNUSED(exchangeKey);
    Q_UNUSED(futures);
    return {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"};
}

QString pythonSourceParityContractHash() {
    return parityString(PythonParityContract::kPythonSourceContractHash);
}

QStringList pythonSourceParityDomainKeys() {
    return parityStringList(PythonParityContract::kPythonParityDomainKeys);
}

QStringList pythonSourceParityDomainTitles() {
    QStringList result;
    result.reserve(static_cast<int>(PythonParityContract::kPythonParityDomains.size()));
    for (const auto &domain : PythonParityContract::kPythonParityDomains) {
        result.append(parityString(domain.title));
    }
    return result;
}

QString pythonSourceParityDomainTitle(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? parityString(domain->title) : QString();
}

QString pythonSourceParityDomainPythonSurface(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? parityString(domain->pythonSurface) : QString();
}

QString pythonSourceParityDomainCppStatus(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? parityString(domain->cppStatus) : QString();
}

QString pythonSourceParityDomainRustStatus(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? parityString(domain->rustStatus) : QString();
}

QString pythonSourceParityDomainRequiredBeforeFullParity(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? parityString(domain->requiredBeforeFullParity) : QString();
}

bool pythonSourceParityDomainCppFullParity(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? domain->cppFullParity : false;
}

bool pythonSourceParityDomainRustFullParity(const QString &domainKey) {
    const auto *domain = parityDomainByKey(domainKey);
    return domain ? domain->rustFullParity : false;
}

QStringList pythonSourceServiceRouteNames() {
    return parityStringList(PythonParityContract::kPythonServiceRouteNames);
}

QString pythonSourceServiceRoutePath(const QString &routeName) {
    const QString normalized = routeName.trimmed();
    for (const auto &route : PythonParityContract::kPythonServiceRoutes) {
        if (parityString(route.name) == normalized) {
            return parityString(route.path);
        }
    }
    return QString();
}

QStringList pythonSourceServiceRouteMethods(const QString &routeName) {
    const QString normalized = routeName.trimmed();
    for (const auto &route : PythonParityContract::kPythonServiceRoutes) {
        if (parityString(route.name) == normalized) {
            return parityCsvStringList(route.methods);
        }
    }
    return {};
}

QStringList pythonSourceServiceRouteQueryFields(const QString &routeName) {
    const auto *schema = serviceRouteSchemaByName(routeName);
    return schema ? parityCsvStringList(schema->queryFields) : QStringList();
}

QStringList pythonSourceServiceRouteRequestFields(const QString &routeName) {
    const auto *schema = serviceRouteSchemaByName(routeName);
    return schema ? parityCsvStringList(schema->requestFields) : QStringList();
}

QStringList pythonSourceServiceRouteResponseFields(const QString &routeName) {
    const auto *schema = serviceRouteSchemaByName(routeName);
    return schema ? parityCsvStringList(schema->responseFields) : QStringList();
}

QString serviceApiBaseUrl() {
    QString base = environmentValue("BOT_DESKTOP_SERVICE_API_BASE_URL");
    if (base.isEmpty()) {
        const QString host = environmentValue("BOT_DESKTOP_SERVICE_API_HOST", QStringLiteral("127.0.0.1"));
        const QString port = environmentValue("BOT_DESKTOP_SERVICE_API_PORT", QStringLiteral("8000"));
        const QString displayHost = host.contains(u':') && !host.startsWith(u'[')
            ? QStringLiteral("[%1]").arg(host)
            : host;
        base = QStringLiteral("http://%1:%2").arg(displayHost, port);
    }
    return normalizeBaseUrl(base);
}

QString serviceApiUrlForRoute(const QString &routeName) {
    const QString path = pythonSourceServiceRoutePath(routeName);
    const QString base = serviceApiBaseUrl();
    if (path.trimmed().isEmpty()) {
        return base;
    }
    return base + (path.startsWith(u'/') ? path : QStringLiteral("/") + path);
}

ServiceApiJsonResult serviceApiRequestJson(
    const QString &method,
    const QString &routeName,
    const QJsonObject &body,
    int timeoutMs) {
    ServiceApiJsonResult result;
    const QString normalizedMethod = method.trimmed().toUpper();
    const QString url = serviceApiUrlForRoute(routeName);

    if (pythonSourceServiceRoutePath(routeName).trimmed().isEmpty()) {
        result.error = QStringLiteral("Unknown Python Service API route '%1'.").arg(routeName);
        return result;
    }
    if (normalizedMethod.isEmpty()) {
        result.error = QStringLiteral("Missing Service API method for route '%1'.").arg(routeName);
        return result;
    }
    const QStringList declaredMethods = pythonSourceServiceRouteMethods(routeName);
    if (!declaredMethods.contains(normalizedMethod)) {
        result.error = QStringLiteral("Service API method %1 is not declared by the Python contract for route '%2'.")
                           .arg(normalizedMethod, routeName);
        return result;
    }
    const QStringList declaredFields = normalizedMethod == QStringLiteral("GET")
        ? pythonSourceServiceRouteQueryFields(routeName)
        : pythonSourceServiceRouteRequestFields(routeName);
    for (auto it = body.constBegin(); it != body.constEnd(); ++it) {
        if (declaredFields.contains(it.key())) {
            continue;
        }
        const QString fieldKind = normalizedMethod == QStringLiteral("GET")
            ? QStringLiteral("query")
            : QStringLiteral("request");
        result.error = QStringLiteral("Service API %1 field %2 is not declared by the Python contract for route '%3'.")
                           .arg(fieldKind, it.key(), routeName);
        return result;
    }

    const QString token = environmentValue("BOT_SERVICE_API_TOKEN");
    if (const QString endpointError = validateServiceApiEndpoint(serviceApiBaseUrl(), token); !endpointError.isEmpty()) {
        result.error = endpointError;
        return result;
    }

    QUrl requestUrl(url);
    if (normalizedMethod == QStringLiteral("GET") && !body.isEmpty()) {
        QUrlQuery query(requestUrl);
        for (auto it = body.constBegin(); it != body.constEnd(); ++it) {
            const QJsonValue value = it.value();
            if (value.isString()) {
                query.addQueryItem(it.key(), value.toString());
            } else if (value.isDouble()) {
                query.addQueryItem(it.key(), QString::number(value.toDouble(), 'g', 15));
            } else if (value.isBool()) {
                query.addQueryItem(it.key(), value.toBool() ? QStringLiteral("true") : QStringLiteral("false"));
            }
        }
        requestUrl.setQuery(query);
    }

    QNetworkAccessManager manager;
    QNetworkRequest request{requestUrl};
    request.setHeader(QNetworkRequest::UserAgentHeader, QStringLiteral("trading-bot-cpp/1.0"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    if (!token.isEmpty()) {
        request.setRawHeader(QByteArrayLiteral("Authorization"), QByteArrayLiteral("Bearer ") + token.toUtf8());
    }

    QNetworkReply *reply = nullptr;
    const QByteArray payload = body.isEmpty() ? QByteArrayLiteral("{}") : QJsonDocument(body).toJson(QJsonDocument::Compact);
    if (normalizedMethod == QStringLiteral("GET")) {
        reply = manager.get(request);
    } else if (normalizedMethod == QStringLiteral("POST")) {
        reply = manager.post(request, payload);
    } else if (normalizedMethod == QStringLiteral("PATCH")) {
        reply = manager.sendCustomRequest(request, QByteArrayLiteral("PATCH"), payload);
    } else if (normalizedMethod == QStringLiteral("PUT")) {
        reply = manager.put(request, payload);
    } else if (normalizedMethod == QStringLiteral("DELETE")) {
        reply = manager.sendCustomRequest(request, QByteArrayLiteral("DELETE"), payload);
    } else {
        result.error = QStringLiteral("Unsupported Service API method %1").arg(normalizedMethod);
        return result;
    }

    QEventLoop loop;
    QTimer timer;
    bool timedOut = false;
    timer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, [&]() {
        timedOut = true;
        reply->abort();
        loop.quit();
    });
    timer.start(timeoutMs);
    loop.exec();

    const QByteArray responseBody = reply->readAll();
    result.statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    const QNetworkReply::NetworkError networkError = reply->error();
    const QString networkErrorText = reply->errorString();
    reply->deleteLater();

    if (timedOut) {
        result.error = QStringLiteral("Service API request timed out: %1").arg(url);
        return result;
    }
    if (result.statusCode >= 400) {
        const QString detail = QString::fromUtf8(responseBody).trimmed();
        result.error = QStringLiteral("Service API HTTP %1 for %2%3")
                           .arg(result.statusCode)
                           .arg(url, detail.isEmpty() ? QString() : QStringLiteral(": ") + detail);
        return result;
    }
    if (networkError != QNetworkReply::NoError) {
        result.error = QStringLiteral("Service API request failed (%1): %2").arg(url, networkErrorText);
        return result;
    }

    QJsonParseError parseError{};
    result.document = QJsonDocument::fromJson(responseBody, &parseError);
    if (parseError.error != QJsonParseError::NoError || result.document.isNull()) {
        result.error = QStringLiteral("Service API returned invalid JSON for %1: %2").arg(url, parseError.errorString());
        return result;
    }
    result.ok = true;
    return result;
}

QStringList pythonSourceBacktestRunRequestFields() {
    return parityStringList(PythonParityContract::kPythonBacktestRunRequestFields);
}

QStringList pythonSourceIndicatorKeys() {
    return parityStringList(PythonParityContract::kPythonIndicatorKeys);
}

QStringList pythonSourceIndicatorDisplayNames() {
    QStringList names;
    for (const auto &indicator : PythonParityContract::kPythonIndicatorCatalog) {
        names.append(parityString(indicator.displayName));
    }
    return names;
}

QStringList pythonSourceDefaultEnabledIndicatorKeys() {
    QStringList keys;
    for (const auto &indicator : PythonParityContract::kPythonIndicatorCatalog) {
        if (indicator.defaultEnabled) {
            keys.append(parityString(indicator.key));
        }
    }
    return keys;
}

QMap<QString, QJsonObject> pythonSourceBacktestIndicatorConfigs() {
    QMap<QString, QJsonObject> configs;
    for (const auto &indicator : PythonParityContract::kPythonIndicatorCatalog) {
        const QString key = parityString(indicator.key);
        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(
            parityString(indicator.backtestConfigJson).toUtf8(),
            &parseError);
        if (!key.isEmpty() && parseError.error == QJsonParseError::NoError && document.isObject()) {
            configs.insert(key, document.object());
        }
    }
    return configs;
}

QStringList pythonSourceLlmProviderKeys() {
    return parityStringList(PythonParityContract::kPythonLlmProviderKeys);
}

QStringList pythonSourceLlmProviderLabels() {
    QStringList labels;
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        labels.append(parityString(provider.label));
    }
    return labels;
}

QStringList pythonSourceLlmProviderDefaultModels() {
    QStringList models;
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        models.append(parityString(provider.defaultModel));
    }
    return models;
}

QStringList pythonSourceLlmProviderApiKeyEnvs() {
    QStringList envs;
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        envs.append(parityString(provider.apiKeyEnv));
    }
    return envs;
}

QVector<LlmProviderRuntimeConfig> pythonSourceLlmProviderConfigs() {
    QVector<LlmProviderRuntimeConfig> configs;
    configs.reserve(static_cast<int>(PythonParityContract::kPythonLlmProviders.size()));
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        configs.append({
            parityString(provider.key),
            parityString(provider.label),
            parityString(provider.mode),
            parityString(provider.protocol),
            parityString(provider.defaultBaseUrl),
            parityString(provider.defaultModel),
            parityString(provider.apiKeyEnv),
            parityCsvStringList(provider.modelSuggestions),
            parityCsvStringList(provider.reasoningEfforts),
            parityString(provider.defaultReasoningEffort),
        });
    }
    return configs;
}

QStringList pythonSourceConnectorKeys() {
    return parityStringList(PythonParityContract::kPythonConnectorKeys);
}

QStringList pythonSourceConnectorLabels() {
    QStringList labels;
    for (const auto &connector : PythonParityContract::kPythonConnectorOptions) {
        labels.append(parityString(connector.label));
    }
    return labels;
}

QStringList pythonSourceBacktestIntervals() {
    return parityStringList(PythonParityContract::kPythonBacktestIntervals);
}

QStringList pythonSourceTradingViewIntervalKeys() {
    QStringList keys;
    keys.reserve(static_cast<int>(PythonParityContract::kPythonTradingViewIntervalMap.size()));
    for (const auto &interval : PythonParityContract::kPythonTradingViewIntervalMap) {
        keys.append(parityString(interval.interval));
    }
    return keys;
}

QStringList pythonSourceTradingViewIntervalCodes() {
    QStringList codes;
    codes.reserve(static_cast<int>(PythonParityContract::kPythonTradingViewIntervalMap.size()));
    for (const auto &interval : PythonParityContract::kPythonTradingViewIntervalMap) {
        codes.append(parityString(interval.code));
    }
    return codes;
}

QStringList pythonSourceDefaultChartSymbols() {
    return parityStringList(PythonParityContract::kPythonDefaultChartSymbols);
}

QStringList pythonSourceDefaultExecutionSymbols() {
    return parityStringList(PythonParityContract::kPythonDefaultExecutionSymbols);
}

QStringList pythonSourceDefaultExecutionIntervals() {
    return parityStringList(PythonParityContract::kPythonDefaultExecutionIntervals);
}

QStringList pythonSourceDefaultBacktestSymbols() {
    return parityStringList(PythonParityContract::kPythonDefaultBacktestSymbols);
}

QStringList pythonSourceDefaultBacktestIntervals() {
    return parityStringList(PythonParityContract::kPythonDefaultBacktestIntervals);
}

QStringList pythonSourceChartMarketOptions() {
    return parityStringList(PythonParityContract::kPythonChartMarketOptions);
}

QStringList pythonSourceAccountModeOptions() {
    return parityStringList(PythonParityContract::kPythonAccountModeOptions);
}

QStringList pythonSourceDashboardLoopChoiceKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonDashboardLoopChoices);
}

QStringList pythonSourceDashboardLoopChoiceLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonDashboardLoopChoices);
}

QStringList pythonSourceLeadTraderOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonLeadTraderOptions);
}

QStringList pythonSourceLeadTraderOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonLeadTraderOptions);
}

QStringList pythonSourceLlmUseForOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonLlmUseForOptions);
}

QStringList pythonSourceLlmUseForOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonLlmUseForOptions);
}

QStringList pythonSourceDashboardStrategyTemplateKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonDashboardStrategyTemplates);
}

QStringList pythonSourceDashboardStrategyTemplateLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonDashboardStrategyTemplates);
}

QStringList pythonSourceBacktestTemplateKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonBacktestTemplates);
}

QStringList pythonSourceBacktestTemplateLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonBacktestTemplates);
}

QStringList pythonSourceSideOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonSideOptions);
}

QStringList pythonSourceSideOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonSideOptions);
}

QStringList pythonSourceConfigModeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonConfigModeOptions);
}

QStringList pythonSourceConfigModeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonConfigModeOptions);
}

QStringList pythonSourceThemeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonThemeOptions);
}

QStringList pythonSourceThemeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonThemeOptions);
}

QStringList pythonSourceDesignOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonDesignOptions);
}

QStringList pythonSourceDesignOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonDesignOptions);
}

QStringList pythonSourceIndicatorSourceOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonIndicatorSourceOptions);
}

QStringList pythonSourceIndicatorSourceOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonIndicatorSourceOptions);
}

QStringList pythonSourceExchangeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonExchangeOptions);
}

QStringList pythonSourceExchangeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonExchangeOptions);
}

QStringList pythonSourceExchangeOptionDisabledLabels() {
    QStringList labels;
    for (const auto &option : PythonParityContract::kPythonExchangeOptions) {
        if (option.disabled) {
            labels.append(parityString(option.label));
        }
    }
    return labels;
}

QStringList pythonSourceAccountTypeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonAccountTypeOptions);
}

QStringList pythonSourceAccountTypeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonAccountTypeOptions);
}

QStringList pythonSourceMarginModeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonMarginModeOptions);
}

QStringList pythonSourceMarginModeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonMarginModeOptions);
}

QStringList pythonSourcePositionModeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonPositionModeOptions);
}

QStringList pythonSourcePositionModeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonPositionModeOptions);
}

QStringList pythonSourceAssetsModeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonAssetsModeOptions);
}

QStringList pythonSourceAssetsModeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonAssetsModeOptions);
}

QStringList pythonSourceOrderTypeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonOrderTypeOptions);
}

QStringList pythonSourceOrderTypeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonOrderTypeOptions);
}

QStringList pythonSourceTimeInForceOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonTimeInForceOptions);
}

QStringList pythonSourceTimeInForceOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonTimeInForceOptions);
}

QStringList pythonSourceSignalLogicOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonSignalLogicOptions);
}

QStringList pythonSourceSignalLogicOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonSignalLogicOptions);
}

QStringList pythonSourceMddLogicOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonMddLogicOptions);
}

QStringList pythonSourceMddLogicOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonMddLogicOptions);
}

QStringList pythonSourceStopLossModeKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonStopLossModes);
}

QStringList pythonSourceStopLossModeLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonStopLossModes);
}

QStringList pythonSourceStopLossScopeKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonStopLossScopes);
}

QStringList pythonSourceStopLossScopeLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonStopLossScopes);
}

QStringList pythonSourceScanScopeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonScanScopeOptions);
}

QStringList pythonSourceScanScopeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonScanScopeOptions);
}

QStringList pythonSourceOptimizerModeOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonOptimizerModeOptions);
}

QStringList pythonSourceOptimizerModeOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonOptimizerModeOptions);
}

QStringList pythonSourceOptimizerMetricOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonOptimizerMetricOptions);
}

QStringList pythonSourceOptimizerMetricOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonOptimizerMetricOptions);
}

QStringList pythonSourceBacktestExecutionBackendOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonBacktestExecutionBackendOptions);
}

QStringList pythonSourceBacktestExecutionBackendOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonBacktestExecutionBackendOptions);
}

QStringList pythonSourceChartViewOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonChartViewOptions);
}

QStringList pythonSourceChartViewOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonChartViewOptions);
}

QStringList pythonSourcePositionsViewOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonPositionsViewOptions);
}

QStringList pythonSourcePositionsViewOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonPositionsViewOptions);
}

void populateComboFromPythonSourceOptions(
    QComboBox *combo,
    const QStringList &keys,
    const QStringList &labels,
    const QStringList &disabledLabels,
    const QString &currentKey,
    const QString &currentLabel) {
    if (!combo) {
        return;
    }
    combo->clear();
    const int count = std::max(keys.size(), labels.size());
    for (int i = 0; i < count; ++i) {
        const QString key = keys.value(i).trimmed();
        QString label = labels.value(i).trimmed();
        if (label.isEmpty()) {
            label = key;
        }
        if (label.isEmpty()) {
            continue;
        }
        combo->addItem(label, key);
        if (disabledLabels.contains(label)) {
            const int idx = combo->count() - 1;
            if (auto *model = qobject_cast<QStandardItemModel *>(combo->model())) {
                if (auto *item = model->item(idx)) {
                    item->setFlags(item->flags() & ~Qt::ItemFlag::ItemIsEnabled);
                    item->setForeground(QColor("#6b7280"));
                }
            }
        }
    }
    if (!currentKey.trimmed().isEmpty()) {
        const int idx = combo->findData(currentKey.trimmed());
        if (idx >= 0) {
            combo->setCurrentIndex(idx);
            return;
        }
    }
    if (!currentLabel.trimmed().isEmpty()) {
        const int idx = combo->findText(currentLabel.trimmed());
        if (idx >= 0) {
            combo->setCurrentIndex(idx);
        }
    }
}

bool cppPythonSourceParityReady() {
    return PythonParityContract::kCppFullParityReady;
}

bool rustPythonSourceParityReady() {
    return PythonParityContract::kRustFullParityReady;
}

QString recommendedConnectorKey(bool futures) {
    return futures ? kConnectorUsdsFutures : kConnectorSpot;
}

QString connectorLabelForKey(const QString &connectorKey) {
    for (const auto &option : pythonConnectorOptions()) {
        if (option.key == connectorKey) {
            return option.label;
        }
    }
    return connectorKey.trimmed();
}

void rebuildConnectorComboForAccount(QComboBox *combo, bool futures, bool forceDefault) {
    if (!combo) {
        return;
    }

    QString currentKey = normalizeConnectorBackend(combo->currentData().toString().trimmed());
    if (currentKey.trimmed().isEmpty()) {
        currentKey = normalizeConnectorBackend(combo->currentText().trimmed());
    }
    const QString recommended = recommendedConnectorKey(futures);
    if (forceDefault || !connectorAllowedForAccount(currentKey, futures)) {
        currentKey = recommended;
    }

    const QSignalBlocker blocker(combo);
    combo->clear();
    const QSet<QString> &allowed = futures ? kFuturesConnectorKeys : kSpotConnectorKeys;
    for (const auto &option : pythonConnectorOptions()) {
        if (allowed.contains(option.key)) {
            combo->addItem(option.label, option.key);
        }
    }

    if (combo->count() <= 0) {
        return;
    }

    int idx = combo->findData(currentKey);
    if (idx < 0) {
        idx = combo->findData(recommended);
    }
    if (idx < 0) {
        idx = 0;
    }
    combo->setCurrentIndex(idx);
}

ConnectorRuntimeConfig resolveConnectorConfig(const QString &connectorText, bool futures) {
    ConnectorRuntimeConfig cfg;
    cfg.label = connectorText.trimmed();
    const QString normalized = connectorText.trimmed().toLower();
    const QString selectedKey = normalizeConnectorBackend(connectorText);

    if (selectedKey == kConnectorLegacyGateway) {
        cfg.key = kConnectorLegacyGateway;
        const QString raw = firstEnvValue(
            futures
                ? QStringList{
                      QStringLiteral("BINANCE_GATEWAY_FUTURES_BASE_URL"),
                      QStringLiteral("BINANCE_GATEWAY_BASE_URL"),
                      QStringLiteral("BINANCE_GATEWAY_URL"),
                  }
                : QStringList{
                      QStringLiteral("BINANCE_GATEWAY_SPOT_BASE_URL"),
                      QStringLiteral("BINANCE_GATEWAY_BASE_URL"),
                      QStringLiteral("BINANCE_GATEWAY_URL"),
                  });
        cfg.baseUrl = normalizeBaseUrl(raw);
        if (cfg.baseUrl.isEmpty()) {
            cfg.error = futures
                ? QStringLiteral("Gateway connector requires BINANCE_GATEWAY_FUTURES_BASE_URL (or BINANCE_GATEWAY_BASE_URL).")
                : QStringLiteral("Gateway connector requires BINANCE_GATEWAY_SPOT_BASE_URL (or BINANCE_GATEWAY_BASE_URL).");
        }
        return cfg;
    }

    if (selectedKey == kConnectorLegacyCustom || normalized.startsWith(QStringLiteral("http"))) {
        cfg.key = kConnectorLegacyCustom;
        QString raw = normalized.startsWith(QStringLiteral("http")) ? connectorText.trimmed() : QString();
        if (raw.isEmpty()) {
            raw = firstEnvValue(
                futures
                    ? QStringList{
                          QStringLiteral("CUSTOM_CONNECTOR_FUTURES_BASE_URL"),
                          QStringLiteral("CUSTOM_CONNECTOR_BASE_URL"),
                          QStringLiteral("CUSTOM_CONNECTOR_URL"),
                      }
                    : QStringList{
                          QStringLiteral("CUSTOM_CONNECTOR_SPOT_BASE_URL"),
                          QStringLiteral("CUSTOM_CONNECTOR_BASE_URL"),
                          QStringLiteral("CUSTOM_CONNECTOR_URL"),
                      });
        }
        cfg.baseUrl = normalizeBaseUrl(raw);
        if (cfg.baseUrl.isEmpty()) {
            cfg.error = futures
                ? QStringLiteral("Custom connector requires CUSTOM_CONNECTOR_FUTURES_BASE_URL (or CUSTOM_CONNECTOR_BASE_URL).")
                : QStringLiteral("Custom connector requires CUSTOM_CONNECTOR_SPOT_BASE_URL (or CUSTOM_CONNECTOR_BASE_URL).");
        }
        return cfg;
    }

    auto setWarning = [&cfg](const QString &message) {
        if (cfg.warning.trimmed().isEmpty()) {
            cfg.warning = message;
        }
    };

    const QString recommended = recommendedConnectorKey(futures);
    QString effectiveKey = cfg.label.isEmpty() ? recommended : selectedKey;
    if (effectiveKey.trimmed().isEmpty()) {
        effectiveKey = recommended;
    }

    if (!connectorAllowedForAccount(effectiveKey, futures)) {
        const QString chosenLabel = cfg.label.isEmpty() ? connectorLabelForKey(effectiveKey) : cfg.label;
        setWarning(
            QStringLiteral("Connector '%1' is not available for %2. Using '%3'.")
                .arg(chosenLabel,
                     futures ? QStringLiteral("Futures") : QStringLiteral("Spot"),
                     connectorLabelForKey(recommended)));
        effectiveKey = recommended;
    }

    if (effectiveKey == kConnectorCoinFutures) {
        // BinanceRestClient recognizes the DAPI host and routes all futures operations to Coin-M endpoints.
        cfg.baseUrl = QStringLiteral("https://dapi.binance.com");
    } else if (effectiveKey == kConnectorBinanceConnector
               || effectiveKey == kConnectorCcxt
               || effectiveKey == kConnectorPyBinance) {
        setWarning(
            QStringLiteral("Connector '%1' maps to native Binance REST in C++ runtime.")
                .arg(cfg.label.isEmpty() ? connectorLabelForKey(effectiveKey) : cfg.label));
        effectiveKey = recommended;
    }

    cfg.key = effectiveKey;
    if (cfg.label.isEmpty()) {
        cfg.label = connectorLabelForKey(effectiveKey);
    }
    if (effectiveKey != kConnectorCoinFutures) {
        cfg.baseUrl.clear();
    }
    return cfg;
}

bool nativeRuntimeOwnsBinanceFuturesConnector(const QString &connectorText) {
    const QString selected = connectorText.trimmed();
    const QString key = normalizeConnectorBackend(selected);
    if (key != kConnectorUsdsFutures && key != kConnectorCoinFutures) {
        return false;
    }

    // Only accept the key or label emitted by the generated Python connector catalog.
    // This keeps provider aliases from silently becoming native Binance execution.
    for (const ConnectorOption &option : pythonConnectorOptions()) {
        if (option.key != key) {
            continue;
        }
        return selected.compare(option.key, Qt::CaseInsensitive) == 0
            || selected.compare(option.label, Qt::CaseInsensitive) == 0;
    }
    return false;
}

double firstNumberInText(const QString &text, bool *okOut) {
    static const QRegularExpression numRe(QStringLiteral("[-+]?\\d+(?:\\.\\d+)?"));
    const QRegularExpressionMatch match = numRe.match(text);
    if (!match.hasMatch()) {
        if (okOut) {
            *okOut = false;
        }
        return 0.0;
    }
    bool ok = false;
    const double value = match.captured(0).toDouble(&ok);
    if (okOut) {
        *okOut = ok;
    }
    return ok ? value : 0.0;
}

double tableCellRawNumeric(const QTableWidgetItem *item, double fallback) {
    if (!item) {
        return fallback;
    }

    bool ok = false;
    const double rawValue = item->data(kTableCellRawNumericRole).toDouble(&ok);
    if (ok && qIsFinite(rawValue)) {
        return rawValue;
    }

    const double displayValue = item->data(kTableCellNumericRole).toDouble(&ok);
    if (ok && qIsFinite(displayValue)) {
        return displayValue;
    }
    return fallback;
}

} // namespace TradingBotWindowSupport
