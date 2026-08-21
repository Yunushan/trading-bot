#include "TradingBotWindowSupport.h"

#include "generated/PythonParityContract.h"

#include <QColor>
#include <QComboBox>
#include <QByteArray>
#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QFileInfo>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QSignalBlocker>
#include <QStandardPaths>
#include <QStandardItemModel>
#include <QTableWidgetItem>
#include <QTimer>
#include <QUrl>
#include <QUrlQuery>
#include <QVector>
#include <QtGlobal>

#include <algorithm>

#ifndef TB_NATIVE_PROJECT_ROOT
#define TB_NATIVE_PROJECT_ROOT ""
#endif

namespace {

constexpr int kTableCellNumericRole = Qt::UserRole + 2;
constexpr int kTableCellRawNumericRole = Qt::UserRole + 4;

QString normalizeExchangeKey(QString value) {
    return TradingBotWindowSupport::canonicalPythonExchangeKey(value);
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

QString normalizeConnectorBackendInternal(const QString &value) {
    const QString textRaw = value.trimmed();
    if (textRaw.isEmpty()) {
        return kConnectorUsdsFutures;
    }
    const QString text = textRaw.toLower();

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

QJsonObject parityJsonObject(std::string_view value) {
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(parityString(value).toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        return {};
    }
    return document.object();
}

QVector<ConnectorOption> pythonConnectorOptions() {
    QVector<ConnectorOption> options;
    options.reserve(static_cast<int>(PythonParityContract::kPythonConnectorOptions.size()));
    for (const auto &connector : PythonParityContract::kPythonConnectorOptions) {
        options.append({parityString(connector.label), parityString(connector.key)});
    }
    return options;
}

bool pythonConnectorOptionExists(const QString &key) {
    const QString normalized = key.trimmed().toLower();
    if (normalized.isEmpty()) {
        return false;
    }
    for (const ConnectorOption &option : pythonConnectorOptions()) {
        if (option.key.compare(normalized, Qt::CaseInsensitive) == 0) {
            return true;
        }
    }
    return false;
}

bool connectorAllowedForAccount(const QString &connectorKey, bool futures) {
    const QString normalized = connectorKey.trimmed().toLower();
    for (const auto &mapping : PythonParityContract::kPythonNativeRuntimeConnectorMarketFamilies) {
        if (parityString(mapping.key).compare(normalized, Qt::CaseInsensitive) != 0) {
            continue;
        }
        const QString marketFamily = parityString(mapping.value).toLower();
        if (futures && marketFamily.endsWith(QStringLiteral("-futures"))) {
            return true;
        }
        if (!futures && marketFamily == QStringLiteral("spot")) {
            return true;
        }
    }
    return false;
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

void appendUniqueLlmModel(QStringList &models, const QString &value) {
    const QString normalized = value.trimmed();
    if (!normalized.isEmpty() && !models.contains(normalized)) {
        models.append(normalized);
    }
}

QString pythonCatalogRepr(const QJsonValue &value) {
    if (value.isNull() || value.isUndefined()) {
        return QStringLiteral("None");
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("True") : QStringLiteral("False");
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'g', 15);
    }
    if (value.isString()) {
        QString escaped = value.toString();
        escaped.replace(QStringLiteral("\\"), QStringLiteral("\\\\"));
        escaped.replace(QStringLiteral("'"), QStringLiteral("\\'"));
        escaped.replace(QStringLiteral("\n"), QStringLiteral("\\n"));
        escaped.replace(QStringLiteral("\r"), QStringLiteral("\\r"));
        escaped.replace(QStringLiteral("\t"), QStringLiteral("\\t"));
        return QStringLiteral("'") + escaped + QStringLiteral("'");
    }
    if (value.isArray()) {
        QStringList items;
        for (const QJsonValue &item : value.toArray()) {
            items.append(pythonCatalogRepr(item));
        }
        return QStringLiteral("[") + items.join(QStringLiteral(", ")) + QStringLiteral("]");
    }
    QStringList items;
    const QJsonObject object = value.toObject();
    for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
        items.append(
            pythonCatalogRepr(QJsonValue(it.key()))
            + QStringLiteral(": ")
            + pythonCatalogRepr(it.value()));
    }
    return QStringLiteral("{") + items.join(QStringLiteral(", ")) + QStringLiteral("}");
}

QString catalogValueText(const QJsonValue &value) {
    if (value.isNull() || value.isUndefined()) {
        return {};
    }
    if (value.isString()) {
        return value.toString();
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("True") : QString();
    }
    if (value.isDouble()) {
        const double number = value.toDouble();
        return number == 0.0 ? QString() : QString::number(number, 'g', 15);
    }
    if (value.isArray()) {
        const QJsonArray array = value.toArray();
        return array.isEmpty() ? QString() : pythonCatalogRepr(value);
    }
    const QJsonObject object = value.toObject();
    return object.isEmpty() ? QString() : pythonCatalogRepr(value);
}

QString expandLlmCatalogPath(const QString &value) {
    const QString trimmed = value.trimmed();
    if (trimmed == QStringLiteral("~")) {
        return QDir::homePath();
    }
    if (trimmed.startsWith(QStringLiteral("~/"))
        || trimmed.startsWith(QStringLiteral("~\\"))) {
        return QDir(QDir::homePath()).filePath(trimmed.mid(2));
    }
    return trimmed;
}

QString llmCatalogPath(const QString &catalogPathEnv) {
    const QString envName = catalogPathEnv.trimmed().isEmpty()
        ? QStringLiteral("BOT_LLM_MODEL_CATALOG_PATH")
        : catalogPathEnv.trimmed();
    const QByteArray envNameBytes = envName.toUtf8();
    const QString configured = qEnvironmentVariable(envNameBytes.constData()).trimmed();
    if (!configured.isEmpty()) {
        return expandLlmCatalogPath(configured);
    }
    return QDir(QDir::homePath()).filePath(QStringLiteral(".trading-bot/llm-models.json"));
}

void appendLlmCatalogModels(
    QStringList &models,
    const QString &providerKey,
    const QString &catalogPathEnv) {
    QFile file(llmCatalogPath(catalogPathEnv));
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return;
    }
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        return;
    }
    const QJsonObject payload = document.object();
    QJsonValue rawModels = payload.value(providerKey);
    if (rawModels.isUndefined() || rawModels.isNull()) {
        rawModels = payload.value(QStringLiteral("providers")).toObject().value(providerKey);
    }
    if (!rawModels.isArray()) {
        return;
    }
    for (const QJsonValue &item : rawModels.toArray()) {
        appendUniqueLlmModel(models, catalogValueText(item));
    }
}

QStringList llmModelSuggestions(
    const QString &providerKey,
    const QString &customModelsEnv,
    const QString &customModelsPathEnv,
    std::string_view staticModels) {
    QStringList models = parityCsvStringList(staticModels);
    const QString extra = qEnvironmentVariable(customModelsEnv.toUtf8().constData()).trimmed();
    if (!extra.isEmpty()) {
        QString expanded = extra;
        for (const QString &item : expanded.replace(QLatin1Char(';'), QLatin1Char(','))
                 .split(QLatin1Char(','), Qt::SkipEmptyParts)) {
            appendUniqueLlmModel(models, item);
        }
    }
    appendLlmCatalogModels(models, providerKey, customModelsPathEnv);
    return models;
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

template <typename OptionArray>
QStringList parityStarterOptionKeys(const OptionArray &options) {
    QStringList result;
    result.reserve(static_cast<int>(options.size()));
    for (const auto &option : options) {
        result.append(parityString(option.key));
    }
    return result;
}

template <typename OptionArray>
QStringList parityStarterOptionLabels(const OptionArray &options) {
    QStringList result;
    result.reserve(static_cast<int>(options.size()));
    for (const auto &option : options) {
        result.append(parityString(option.title));
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

QString normalizeConnectorBackend(const QString &value) {
    return normalizeConnectorBackendInternal(value);
}

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

bool nativeRuntimeStandaloneExecutionAllowed(const QString &modeText) {
    // Local paper simulation is safe before promotion; exchange-backed native
    // execution must follow Python's generated readiness boundary.
    return PythonParityContract::kCppStandaloneRuntimeReady
        || isPaperTradingModeLabel(modeText);
}

QString canonicalPythonExchangeKey(const QString &value) {
    QString normalized = value.trimmed();
    const int badgePos = normalized.indexOf('(');
    if (badgePos > 0) {
        normalized = normalized.left(badgePos).trimmed();
    }
    if (normalized.isEmpty()) {
        return normalized;
    }

    for (const auto &option : PythonParityContract::kPythonExchangeOptions) {
        const QString key = parityString(option.key);
        QString label = parityString(option.label);
        const int labelBadgePos = label.indexOf('(');
        if (labelBadgePos > 0) {
            label = label.left(labelBadgePos).trimmed();
        }
        if (normalized.compare(key, Qt::CaseInsensitive) == 0
            || normalized.compare(label, Qt::CaseInsensitive) == 0) {
            return key;
        }
    }
    return normalized;
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
    const QString normalized = normalizeExchangeKey(exchangeKey);
    for (const std::string_view directExchange : PythonParityContract::kPythonNativeRuntimeExchanges) {
        if (normalized.compare(parityString(directExchange), Qt::CaseInsensitive) == 0) {
            return true;
        }
    }
    return false;
}

QString nativeRuntimeIndicatorSourceMarketFamily(const QString &indicatorSourceText) {
    const QString source = indicatorSourceText.trimmed();
    if (source.isEmpty()) {
        return {};
    }

    const auto canonical = [](QString value) {
        value = value.trimmed().toLower();
        value.replace(QRegularExpression(QStringLiteral("[^a-z0-9]+")), QStringLiteral("_"));
        while (value.startsWith(QLatin1Char('_'))) {
            value.remove(0, 1);
        }
        while (value.endsWith(QLatin1Char('_'))) {
            value.chop(1);
        }
        return value;
    };
    const QString sourceKey = canonical(source);
    for (const auto &mapping : PythonParityContract::kPythonNativeRuntimeIndicatorSourceMarketFamilies) {
        const QString mappingKey = parityString(mapping.key);
        if (sourceKey == canonical(mappingKey)) {
            return parityString(mapping.value);
        }
    }
    for (const auto &option : PythonParityContract::kPythonIndicatorSourceOptions) {
        if (sourceKey != canonical(parityString(option.key))
            && sourceKey != canonical(parityString(option.label))) {
            continue;
        }
        const QString optionKey = canonical(parityString(option.key));
        for (const auto &mapping : PythonParityContract::kPythonNativeRuntimeIndicatorSourceMarketFamilies) {
            if (optionKey == canonical(parityString(mapping.key))) {
                return parityString(mapping.value);
            }
        }
    }
    return {};
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

QString pythonDesktopEntrypointPath() {
    QStringList roots;
    const auto appendUniqueRoot = [&roots](const QString &value) {
        const QString trimmed = value.trimmed();
        if (trimmed.isEmpty()) {
            return;
        }
        const QString absolute = QDir(trimmed).absolutePath();
        if (!roots.contains(absolute, Qt::CaseInsensitive)) {
            roots.append(absolute);
        }
    };
    const auto appendAncestors = [&appendUniqueRoot](const QString &start) {
        QDir cursor(start);
        for (int i = 0; i < 10; ++i) {
            appendUniqueRoot(cursor.absolutePath());
            if (!cursor.cdUp()) {
                break;
            }
        }
    };

    appendUniqueRoot(QStringLiteral(TB_NATIVE_PROJECT_ROOT));
    appendUniqueRoot(qEnvironmentVariable("TRADING_BOT_REPO_ROOT"));
    appendUniqueRoot(qEnvironmentVariable("TB_PROJECT_ROOT"));
    appendAncestors(QCoreApplication::applicationDirPath());
    appendAncestors(QDir::currentPath());

    const QStringList relativeCandidates = {
        QStringLiteral("apps/desktop-pyqt/main.py"),
        QStringLiteral("Languages/Python/main.py"),
    };
    for (const QString &root : roots) {
        const QDir rootDir(root);
        for (const QString &relative : relativeCandidates) {
            const QFileInfo candidate(rootDir.filePath(relative));
            if (!candidate.isFile()) {
                continue;
            }
            const QString canonical = candidate.canonicalFilePath();
            return canonical.isEmpty() ? candidate.absoluteFilePath() : canonical;
        }
    }
    return {};
}

QJsonObject projectPythonRemoteServiceConfig(const QJsonObject &config) {
    QJsonObject projected = config;
    for (const std::string_view field : PythonParityContract::kPythonRemoteServiceConfigProtectedFields) {
        projected.remove(QString::fromUtf8(field.data(), static_cast<qsizetype>(field.size())));
    }
    return projected;
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

QVariantMap mergePythonLlmProviderSpec(
    const QVariantMap &current,
    const QJsonObject &pythonProviderPayload) {
    QVariantMap merged = current;
    const auto copyString = [&merged, &pythonProviderPayload](
                                const QString &pythonKey,
                                const QString &localKey) {
        if (!pythonProviderPayload.contains(pythonKey)) {
            return;
        }
        const QString value = pythonProviderPayload.value(pythonKey).toString().trimmed();
        if (!value.isEmpty()) {
            merged.insert(localKey, value);
        }
    };
    copyString(QStringLiteral("key"), QStringLiteral("key"));
    copyString(QStringLiteral("label"), QStringLiteral("label"));
    copyString(QStringLiteral("mode"), QStringLiteral("mode"));
    copyString(QStringLiteral("protocol"), QStringLiteral("protocol"));
    copyString(QStringLiteral("default_base_url"), QStringLiteral("base_url"));
    copyString(QStringLiteral("default_model"), QStringLiteral("default_model"));
    copyString(QStringLiteral("api_key_env"), QStringLiteral("api_key_env"));
    copyString(QStringLiteral("catalog_revision"), QStringLiteral("catalog_revision"));
    copyString(QStringLiteral("custom_models_env"), QStringLiteral("custom_models_env"));
    copyString(QStringLiteral("custom_models_path_env"), QStringLiteral("custom_models_path_env"));
    copyString(QStringLiteral("catalog_path"), QStringLiteral("catalog_path"));
    copyString(QStringLiteral("catalog_note"), QStringLiteral("catalog_note"));
    copyString(QStringLiteral("default_reasoning_effort"), QStringLiteral("default_reasoning"));

    const auto copyUniqueStrings = [&merged, &pythonProviderPayload](
                                       const QString &pythonKey,
                                       const QString &localKey) {
        if (!pythonProviderPayload.contains(pythonKey)) {
            return;
        }
        QStringList values;
        for (const QJsonValue &item : pythonProviderPayload.value(pythonKey).toArray()) {
            const QString value = item.toString().trimmed();
            if (!value.isEmpty() && !values.contains(value)) {
                values.append(value);
            }
        }
        if (!values.isEmpty()) {
            merged.insert(localKey, values);
        }
    };
    copyUniqueStrings(QStringLiteral("model_suggestions"), QStringLiteral("models"));
    copyUniqueStrings(QStringLiteral("reasoning_efforts"), QStringLiteral("reasoning_efforts"));

    if (pythonProviderPayload.contains(QStringLiteral("notes"))) {
        copyUniqueStrings(QStringLiteral("notes"), QStringLiteral("notes"));
    }
    return merged;
}

QVector<LlmProviderRuntimeConfig> pythonSourceLlmProviderConfigs() {
    QVector<LlmProviderRuntimeConfig> configs;
    configs.reserve(static_cast<int>(PythonParityContract::kPythonLlmProviders.size()));
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        const QString providerKey = parityString(provider.key);
        const QString customModelsEnv = parityString(provider.customModelsEnv);
        const QString customModelsPathEnv = parityString(provider.customModelsPathEnv);
        configs.append({
            providerKey,
            parityString(provider.label),
            parityString(provider.mode),
            parityString(provider.protocol),
            parityString(provider.defaultBaseUrl),
            parityString(provider.defaultModel),
            parityString(provider.apiKeyEnv),
            llmModelSuggestions(
                providerKey,
                customModelsEnv,
                customModelsPathEnv,
                provider.modelSuggestions),
            parityCsvStringList(provider.reasoningEfforts),
            parityString(provider.defaultReasoningEffort),
            parityString(provider.catalogRevision),
            parityString(provider.customModelsEnv),
            parityString(provider.customModelsPathEnv),
            parityString(provider.notes).split(QStringLiteral("\n"), Qt::SkipEmptyParts),
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

QJsonObject pythonSourceDefaultExecutionConfig() {
    return parityJsonObject(PythonParityContract::kPythonDefaultExecutionJson);
}

QJsonObject pythonSourceDefaultBacktestConfig() {
    return parityJsonObject(PythonParityContract::kPythonDefaultBacktestJson);
}

QJsonObject pythonSourceRiskDefaults() {
    return parityJsonObject(PythonParityContract::kPythonRiskDefaultsJson);
}

QJsonObject pythonSourceUiDefaults() {
    return parityJsonObject(PythonParityContract::kPythonUiDefaultsJson);
}

namespace {

QString sourceDefaultText(const QJsonObject &defaults, const QString &key, const QString &fallback) {
    const QString value = defaults.value(key).toString().trimmed();
    return value.isEmpty() ? fallback : value;
}

QString sourceDefaultFirstText(const QJsonObject &defaults, const QString &key, const QString &fallback) {
    const QJsonValue value = defaults.value(key);
    if (value.isArray()) {
        const QJsonArray values = value.toArray();
        for (const QJsonValue &item : values) {
            const QString text = item.toString().trimmed();
            if (!text.isEmpty()) {
                return text;
            }
        }
    }
    return sourceDefaultText(defaults, key, fallback);
}

QString firstNonEmptyOption(const QStringList &values, const QString &fallback) {
    for (const QString &value : values) {
        if (!value.trimmed().isEmpty()) {
            return value.trimmed();
        }
    }
    return fallback;
}

} // namespace

QString pythonSourceDefaultExecutionText(const QString &key, const QString &fallback) {
    return sourceDefaultText(pythonSourceDefaultExecutionConfig(), key, fallback);
}

QString pythonSourceDefaultExecutionFirstText(const QString &key, const QString &fallback) {
    return sourceDefaultFirstText(pythonSourceDefaultExecutionConfig(), key, fallback);
}

QString pythonSourceDefaultBacktestText(const QString &key, const QString &fallback) {
    return sourceDefaultText(pythonSourceDefaultBacktestConfig(), key, fallback);
}

QString pythonSourceDefaultUiText(const QString &key, const QString &fallback) {
    return sourceDefaultText(pythonSourceUiDefaults(), key, fallback);
}

QString pythonSourceFirstOptionKey(const QStringList &keys, const QString &fallback) {
    return firstNonEmptyOption(keys, fallback);
}

QString pythonSourceFirstOptionLabel(const QStringList &labels, const QString &fallback) {
    return firstNonEmptyOption(labels, fallback);
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

QStringList pythonSourceLlmReasoningEffortOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonLlmReasoningEffortOptions);
}

QStringList pythonSourceLlmReasoningEffortOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonLlmReasoningEffortOptions);
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

QStringList pythonSourceCodeLanguageOptionKeys() {
    return parityStarterOptionKeys(PythonParityContract::kPythonCodeLanguageOptions);
}

QStringList pythonSourceCodeLanguageOptionLabels() {
    return parityStarterOptionLabels(PythonParityContract::kPythonCodeLanguageOptions);
}

QStringList pythonSourceRustFrameworkOptionKeys() {
    return parityStarterOptionKeys(PythonParityContract::kPythonRustFrameworkOptions);
}

QStringList pythonSourceRustFrameworkOptionLabels() {
    return parityStarterOptionLabels(PythonParityContract::kPythonRustFrameworkOptions);
}

QStringList pythonSourceStarterMarketOptionKeys() {
    return parityStarterOptionKeys(PythonParityContract::kPythonStarterMarketOptions);
}

QStringList pythonSourceStarterMarketOptionLabels() {
    return parityStarterOptionLabels(PythonParityContract::kPythonStarterMarketOptions);
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

QStringList pythonSourcePositionPctUnitsOptionKeys() {
    return parityUiOptionKeys(PythonParityContract::kPythonPositionPctUnitsOptions);
}

QStringList pythonSourcePositionPctUnitsOptionLabels() {
    return parityUiOptionLabels(PythonParityContract::kPythonPositionPctUnitsOptions);
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
    const QString preferredFamily = futures ? QStringLiteral("usd-m-futures") : QStringLiteral("spot");
    for (const auto &mapping : PythonParityContract::kPythonNativeRuntimeConnectorMarketFamilies) {
        if (parityString(mapping.value).compare(preferredFamily, Qt::CaseInsensitive) == 0) {
            return parityString(mapping.key);
        }
    }
    if (!PythonParityContract::kPythonNativeRuntimeConnectorBackends.empty()) {
        return parityString(PythonParityContract::kPythonNativeRuntimeConnectorBackends.front());
    }
    return kConnectorUsdsFutures;
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

    QString currentKey = normalizeConnectorBackendInternal(combo->currentData().toString().trimmed());
    if (currentKey.trimmed().isEmpty()) {
        currentKey = normalizeConnectorBackendInternal(combo->currentText().trimmed());
    }
    const QString recommended = recommendedConnectorKey(futures);
    if (forceDefault || !pythonConnectorOptionExists(currentKey)) {
        currentKey = recommended;
    }

    const QSignalBlocker blocker(combo);
    combo->clear();
    for (const auto &option : pythonConnectorOptions()) {
        // Python's account runtime exposes only connectors declared for the
        // selected market family. Keep the native dropdown identical instead
        // of showing delegated providers that cannot be selected here.
        if (!connectorAllowedForAccount(option.key, futures)) {
            continue;
        }
        combo->addItem(option.label, option.key);
        const int row = combo->count() - 1;
        combo->setItemData(
            row,
            QStringLiteral("Native C++ runtime connector."),
            Qt::ToolTipRole);
        combo->setItemData(row, QStringLiteral("native-cpp"), Qt::UserRole + 1);
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
    const QString selectedKey = normalizeConnectorBackendInternal(connectorText);

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
    const QString key = normalizeConnectorBackendInternal(selected);
    bool nativeBinanceKey = false;
    for (const std::string_view directBackend : PythonParityContract::kPythonNativeRuntimeConnectorBackends) {
        if (key.compare(parityString(directBackend), Qt::CaseInsensitive) == 0) {
            nativeBinanceKey = true;
            break;
        }
    }
    if (!nativeBinanceKey) {
        return false;
    }

    for (const ConnectorOption &option : pythonConnectorOptions()) {
        if (option.key.compare(selected, Qt::CaseInsensitive) != 0
            && option.label.compare(selected, Qt::CaseInsensitive) != 0) {
            continue;
        }
        for (const std::string_view directBackend : PythonParityContract::kPythonNativeRuntimeConnectorBackends) {
            if (option.key.compare(parityString(directBackend), Qt::CaseInsensitive) == 0) {
                return true;
            }
        }
        return false;
    }

    // Non-default native aliases are explicit identities after normalization.
    // The USD-M default needs one extra check because Python intentionally
    // falls back to it for unknown text; unknown or non-native options must
    // not silently enter the Binance REST boundary.
    if (key != kConnectorUsdsFutures) {
        return true;
    }

    const QString text = selected.toLower();
    return text == QStringLiteral("binance_sdk_derivatives_trading_usds_futures")
        || (text.contains(QStringLiteral("sdk"))
            && text.contains(QStringLiteral("future"))
            && (text.contains(QStringLiteral("usd")) || text.contains(QStringLiteral("usds"))));
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
