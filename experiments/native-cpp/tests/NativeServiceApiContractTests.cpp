#include "../src/TradingBotWindowSupport.h"
#include "../src/BinanceRestClient.h"
#include "../src/generated/PythonParityContract.h"

#include <QByteArray>
#include <QCoreApplication>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>
#include <QUrl>
#include <QUrlQuery>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <string_view>

namespace {

bool contains(const QStringList &values, const QString &expected) {
    return values.contains(expected);
}

QString parityString(const std::string_view value) {
    return QString::fromUtf8(value.data(), static_cast<qsizetype>(value.size()));
}

QStringList parityCsv(const std::string_view value) {
    const QString text = parityString(value);
    return text.isEmpty() ? QStringList{} : text.split(QStringLiteral(","), Qt::SkipEmptyParts);
}

void writeJsonResponseAndClose(QTcpSocket *socket, const QByteArray &body) {
    QByteArray response =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        "Connection: close\r\n"
        "Content-Length: ";
    response += QByteArray::number(body.size());
    response += "\r\n\r\n";
    response += body;
    QObject::connect(socket, &QTcpSocket::bytesWritten, socket, [socket](qint64) {
        if (socket->bytesToWrite() == 0 && socket->state() != QAbstractSocket::UnconnectedState) {
            socket->disconnectFromHost();
        }
    });
    socket->write(response);
}

} // namespace

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    int failures = 0;
    const auto check = [&failures](bool condition, const QString &message) {
        if (!condition) {
            std::cerr << message.toStdString() << '\n';
            ++failures;
        }
    };

    const QStringList routes = TradingBotWindowSupport::pythonSourceServiceRouteNames();
    check(routes.size() == 36,
          QStringLiteral("generated Python Service API contract should expose all 36 routes"));
    check(contains(routes, QStringLiteral("dashboard")),
          QStringLiteral("generated route names should include dashboard"));
    check(contains(routes, QStringLiteral("config")),
          QStringLiteral("generated route names should include config"));
    check(contains(routes, QStringLiteral("control_start")),
          QStringLiteral("generated route names should include control_start"));
    check(contains(routes, QStringLiteral("prometheus_metrics")),
          QStringLiteral("generated route names should include prometheus_metrics"));
    check(TradingBotWindowSupport::exchangeUsesBinanceApi(QStringLiteral("Binance")),
          QStringLiteral("native exchange guard should accept Binance"));
    check(
        TradingBotWindowSupport::canonicalPythonExchangeKey(
            QStringLiteral("Crypto.com Exchange (ccxt order routing)"))
            == QStringLiteral("Crypto.com Exchange"),
        QStringLiteral("native exchange normalization should preserve Python's Crypto.com Exchange option"));
    check(
        TradingBotWindowSupport::canonicalPythonExchangeKey(QStringLiteral("Bitfinex"))
            == QStringLiteral("Bitfinex"),
        QStringLiteral("native exchange normalization should preserve Python's Bitfinex option"));
    for (const auto &option : PythonParityContract::kPythonExchangeOptions) {
        const QString key = parityString(option.key);
        const QString label = parityString(option.label);
        check(TradingBotWindowSupport::canonicalPythonExchangeKey(key) == key,
              QStringLiteral("native exchange key should match Python: %1").arg(key));
        check(TradingBotWindowSupport::canonicalPythonExchangeKey(label) == key,
              QStringLiteral("native exchange label should normalize to Python key: %1").arg(key));
    }
    check(!TradingBotWindowSupport::exchangeUsesBinanceApi(QStringLiteral("Bybit")),
          QStringLiteral("native exchange guard should reject non-Binance selections"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("binance-sdk-derivatives-trading-usds-futures")),
        QStringLiteral("C++ native runtime should own Python's USD-M futures connector"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("Binance SDK Derivatives Trading COIN-M Futures")),
        QStringLiteral("C++ native runtime should own Python's Coin-M futures connector label"));
    check(
        !TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("ccxt")),
        QStringLiteral("C++ native runtime should delegate Python's CCXT provider alias"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("binance-connector")),
        QStringLiteral("C++ native runtime should accept Python's Binance Connector alias"));
    check(
        !TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("python-binance")),
        QStringLiteral("C++ native runtime should delegate Python's python-binance provider alias"));
    check(
        !TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("custom")),
        QStringLiteral("C++ native runtime should reject unknown connector providers"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("binance-sdk-spot")),
        QStringLiteral("C++ native runtime should own Python's Binance Spot connector"));

    const QMap<QString, QJsonObject> backtestConfigs =
        TradingBotWindowSupport::pythonSourceBacktestIndicatorConfigs();
    check(backtestConfigs.size() == TradingBotWindowSupport::pythonSourceIndicatorKeys().size(),
          QStringLiteral("every generated Python indicator should expose a native backtest config"));
    check(backtestConfigs.value(QStringLiteral("rsi")).value(QStringLiteral("buy_value")).toInt() == 30,
          QStringLiteral("generated RSI backtest config should preserve the Python buy threshold"));
    check(backtestConfigs.value(QStringLiteral("rsi")).value(QStringLiteral("sell_value")).toInt() == 70,
          QStringLiteral("generated RSI backtest config should preserve the Python sell threshold"));
    check(
        backtestConfigs.value(QStringLiteral("volume")).value(QStringLiteral("signal_role")).toString()
            == QStringLiteral("filter"),
        QStringLiteral("generated volume backtest config should preserve the Python filter role"));

    const QVector<TradingBotWindowSupport::LlmProviderRuntimeConfig> llmProviders =
        TradingBotWindowSupport::pythonSourceLlmProviderConfigs();
    check(
        llmProviders.size() == static_cast<int>(PythonParityContract::kPythonLlmProviders.size()),
        QStringLiteral("native LLM provider catalog should preserve every Python provider"));
    const int llmProviderCount = std::min(
        static_cast<int>(llmProviders.size()),
        static_cast<int>(PythonParityContract::kPythonLlmProviders.size()));
    for (int index = 0; index < llmProviderCount; ++index) {
        const auto &actual = llmProviders.at(index);
        const auto &expected = PythonParityContract::kPythonLlmProviders.at(static_cast<size_t>(index));
        const QString providerLabel = parityString(expected.key);
        check(actual.key == providerLabel,
              QStringLiteral("native LLM provider key should match Python: %1").arg(providerLabel));
        check(actual.label == parityString(expected.label),
              QStringLiteral("native LLM provider label should match Python: %1").arg(providerLabel));
        check(actual.mode == parityString(expected.mode),
              QStringLiteral("native LLM provider mode should match Python: %1").arg(providerLabel));
        check(actual.protocol == parityString(expected.protocol),
              QStringLiteral("native LLM provider protocol should match Python: %1").arg(providerLabel));
        check(actual.defaultBaseUrl == parityString(expected.defaultBaseUrl),
              QStringLiteral("native LLM provider endpoint should match Python: %1").arg(providerLabel));
        check(actual.defaultModel == parityString(expected.defaultModel),
              QStringLiteral("native LLM provider default model should match Python: %1").arg(providerLabel));
        check(actual.apiKeyEnv == parityString(expected.apiKeyEnv),
              QStringLiteral("native LLM provider API-key environment should match Python: %1").arg(providerLabel));
        check(actual.modelSuggestions == parityCsv(expected.modelSuggestions),
              QStringLiteral("native LLM model options should match Python: %1").arg(providerLabel));
        check(actual.reasoningEfforts == parityCsv(expected.reasoningEfforts),
              QStringLiteral("native LLM reasoning options should match Python: %1").arg(providerLabel));
        check(actual.defaultReasoningEffort == parityString(expected.defaultReasoningEffort),
              QStringLiteral("native LLM default reasoning option should match Python: %1").arg(providerLabel));
        check(actual.catalogRevision == parityString(expected.catalogRevision),
              QStringLiteral("native LLM catalog revision should match Python: %1").arg(providerLabel));
        check(actual.customModelsEnv == parityString(expected.customModelsEnv),
              QStringLiteral("native LLM custom-model environment should match Python: %1").arg(providerLabel));
        check(actual.customModelsPathEnv == parityString(expected.customModelsPathEnv),
              QStringLiteral("native LLM catalog-path environment should match Python: %1").arg(providerLabel));
        check(actual.notes == parityString(expected.notes).split(QStringLiteral("\n"), Qt::SkipEmptyParts),
              QStringLiteral("native LLM provider notes should match Python: %1").arg(providerLabel));
    }

    const QJsonObject executionDefaults = TradingBotWindowSupport::pythonSourceDefaultExecutionConfig();
    const QJsonObject expectedExecutionDefaults = QJsonDocument::fromJson(
        QByteArray(PythonParityContract::kPythonDefaultExecutionJson.data(),
                   static_cast<qsizetype>(PythonParityContract::kPythonDefaultExecutionJson.size())))
                                                        .object();
    check(executionDefaults == expectedExecutionDefaults,
          QStringLiteral("C++ execution defaults accessor should preserve the complete Python default object"));
    const QJsonObject riskDefaults = TradingBotWindowSupport::pythonSourceRiskDefaults();
    const QJsonObject expectedRiskDefaults = QJsonDocument::fromJson(
        QByteArray(PythonParityContract::kPythonRiskDefaultsJson.data(),
                   static_cast<qsizetype>(PythonParityContract::kPythonRiskDefaultsJson.size())))
                                                     .object();
    check(riskDefaults == expectedRiskDefaults,
          QStringLiteral("C++ risk defaults accessor should preserve the complete Python risk object"));
    check(riskDefaults.value(QStringLiteral("indicator_use_live_values")).toBool(true) == false,
          QStringLiteral("C++ dashboard must consume Python's closed-candle default"));
    check(riskDefaults.value(QStringLiteral("allow_opposite_positions")).toBool(false),
          QStringLiteral("C++ dashboard must consume Python's hedge-stacking default"));
    const QJsonObject uiDefaults = TradingBotWindowSupport::pythonSourceUiDefaults();
    const QJsonObject expectedUiDefaults = QJsonDocument::fromJson(
        QByteArray(PythonParityContract::kPythonUiDefaultsJson.data(),
                   static_cast<qsizetype>(PythonParityContract::kPythonUiDefaultsJson.size())))
                                                    .object();
    check(uiDefaults == expectedUiDefaults,
          QStringLiteral("C++ UI defaults accessor should preserve the complete Python default object"));
    check(uiDefaults.value(QStringLiteral("theme")).toString() == QStringLiteral("Dark"),
          QStringLiteral("C++ dashboard must consume Python's theme default"));
    check(uiDefaults.value(QStringLiteral("design")).toString() == QStringLiteral("Classic"),
          QStringLiteral("C++ dashboard must consume Python's design default"));
    check(uiDefaults.value(QStringLiteral("indicator_source")).toString() == QStringLiteral("Binance futures"),
          QStringLiteral("C++ dashboard must consume Python's indicator-source default"));

    const QStringList configMethods =
        TradingBotWindowSupport::pythonSourceServiceRouteMethods(QStringLiteral("config"));
    check(contains(configMethods, QStringLiteral("GET")),
          QStringLiteral("config route should declare GET"));
    check(contains(configMethods, QStringLiteral("PUT")),
          QStringLiteral("config route should declare PUT"));
    check(contains(configMethods, QStringLiteral("PATCH")),
          QStringLiteral("config route should declare PATCH"));
    const TradingBotWindowSupport::ServiceApiJsonResult rejectedMethod =
        TradingBotWindowSupport::serviceApiRequestJson(QStringLiteral("POST"), QStringLiteral("config"), {}, 5000);
    check(!rejectedMethod.ok,
          QStringLiteral("C++ Service API helper should reject a method absent from the Python contract"));
    check(rejectedMethod.error.contains(QStringLiteral("not declared by the Python contract")),
          QStringLiteral("C++ Service API helper should identify Python contract method violations"));
    const TradingBotWindowSupport::ServiceApiJsonResult rejectedQueryField =
        TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("GET"),
            QStringLiteral("dashboard"),
            QJsonObject{{QStringLiteral("unexpected"), true}},
            5000);
    check(!rejectedQueryField.ok,
          QStringLiteral("C++ Service API helper should reject query fields absent from the Python contract"));
    check(rejectedQueryField.error.contains(QStringLiteral("query field unexpected")),
          QStringLiteral("C++ Service API helper should identify Python contract query violations"));
    const TradingBotWindowSupport::ServiceApiJsonResult rejectedRequestField =
        TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("POST"),
            QStringLiteral("terminal_run"),
            QJsonObject{{QStringLiteral("unexpected"), true}},
            5000);
    check(!rejectedRequestField.ok,
          QStringLiteral("C++ Service API helper should reject request fields absent from the Python contract"));
    check(rejectedRequestField.error.contains(QStringLiteral("request field unexpected")),
          QStringLiteral("C++ Service API helper should identify Python contract request violations"));

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL", QByteArray("http://192.168.1.10:8000"));
    qunsetenv("BOT_DESKTOP_SERVICE_API_ALLOW_PUBLIC_NETWORK");
    qunsetenv("BOT_SERVICE_API_TOKEN");
    const TradingBotWindowSupport::ServiceApiJsonResult rejectedPublicEndpoint =
        TradingBotWindowSupport::serviceApiRequestJson(QStringLiteral("GET"), QStringLiteral("dashboard"), {}, 5000);
    check(!rejectedPublicEndpoint.ok,
          QStringLiteral("C++ Service API helper should reject public endpoints without explicit opt-in"));
    check(rejectedPublicEndpoint.error.contains(QStringLiteral("Public service API endpoints are disabled")),
          QStringLiteral("C++ Service API helper should explain public endpoint opt-in"));
    qputenv("BOT_DESKTOP_SERVICE_API_ALLOW_PUBLIC_NETWORK", QByteArray("1"));
    const TradingBotWindowSupport::ServiceApiJsonResult rejectedPublicEndpointWithoutToken =
        TradingBotWindowSupport::serviceApiRequestJson(QStringLiteral("GET"), QStringLiteral("dashboard"), {}, 5000);
    check(!rejectedPublicEndpointWithoutToken.ok,
          QStringLiteral("C++ Service API helper should require a token for a public endpoint"));
    check(rejectedPublicEndpointWithoutToken.error.contains(QStringLiteral("BOT_SERVICE_API_TOKEN")),
          QStringLiteral("C++ Service API helper should identify the missing public endpoint token"));
    qunsetenv("BOT_DESKTOP_SERVICE_API_ALLOW_PUBLIC_NETWORK");

    const QStringList dashboardQueryFields =
        TradingBotWindowSupport::pythonSourceServiceRouteQueryFields(QStringLiteral("dashboard"));
    check(contains(dashboardQueryFields, QStringLiteral("log_limit")),
          QStringLiteral("dashboard route should expose log_limit query field"));
    check(contains(dashboardQueryFields, QStringLiteral("incident_limit")),
          QStringLiteral("dashboard route should expose incident_limit query field"));

    const QStringList configRequestFields =
        TradingBotWindowSupport::pythonSourceServiceRouteRequestFields(QStringLiteral("config"));
    check(contains(configRequestFields, QStringLiteral("config")),
          QStringLiteral("config route should expose config request field"));

    const QStringList controlStartRequestFields =
        TradingBotWindowSupport::pythonSourceServiceRouteRequestFields(QStringLiteral("control_start"));
    check(contains(controlStartRequestFields, QStringLiteral("requested_job_count")),
          QStringLiteral("control_start route should expose requested_job_count request field"));

    const TradingBotWindowSupport::ConnectorRuntimeConfig coinFutures =
        TradingBotWindowSupport::resolveConnectorConfig(
            QStringLiteral("binance-sdk-derivatives-trading-coin-futures"), true);
    check(coinFutures.ok(), QStringLiteral("C++ should accept Python's Coin-M futures connector"));
    check(coinFutures.key == QStringLiteral("binance-sdk-derivatives-trading-coin-futures"),
          QStringLiteral("C++ should retain Python's Coin-M futures connector selection"));
    check(coinFutures.baseUrl == QStringLiteral("https://dapi.binance.com"),
          QStringLiteral("C++ Coin-M connector should select Binance's DAPI host"));
    check(!coinFutures.warning.contains(QStringLiteral("not implemented"), Qt::CaseInsensitive),
          QStringLiteral("C++ Coin-M connector should not downgrade to USD-M"));

    QTcpServer coinMarketServer;
    check(coinMarketServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local Coin-M HTTP test server should listen"));
    QByteArray observedCoinMarketRequest;
    QObject::connect(&coinMarketServer, &QTcpServer::newConnection, [&coinMarketServer, &observedCoinMarketRequest]() {
        QTcpSocket *socket = coinMarketServer.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, [socket, &observedCoinMarketRequest]() {
            observedCoinMarketRequest += socket->readAll();
            if (!observedCoinMarketRequest.contains("\r\n\r\n")) {
                return;
            }
            const QByteArray body = R"([[1700000000000,"1","2","0.5","1.5","42"]])";
            writeJsonResponseAndClose(socket, body);
        });
    });
    const auto coinKlines = BinanceRestClient::fetchKlines(
        QStringLiteral("BTCUSD_PERP"),
        QStringLiteral("1m"),
        true,
        false,
        2,
        5000,
        QStringLiteral("http://127.0.0.1:%1/dapi").arg(coinMarketServer.serverPort()));
    check(coinKlines.ok && coinKlines.candles.size() == 1,
          QStringLiteral("C++ Coin-M route should parse DAPI kline data"));
    check(observedCoinMarketRequest.startsWith("GET /dapi/v1/klines?"),
          QStringLiteral("C++ Coin-M route should request the DAPI kline endpoint"));

    QTcpServer coinBalanceServer;
    check(coinBalanceServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local Coin-M balance HTTP test server should listen"));
    QByteArray observedCoinBalanceRequest;
    QObject::connect(&coinBalanceServer, &QTcpServer::newConnection,
                     [&coinBalanceServer, &observedCoinBalanceRequest]() {
                         QTcpSocket *socket = coinBalanceServer.nextPendingConnection();
                         QObject::connect(socket, &QTcpSocket::readyRead,
                                          [socket, &observedCoinBalanceRequest]() {
                                              observedCoinBalanceRequest += socket->readAll();
                                              if (!observedCoinBalanceRequest.contains("\r\n\r\n")) {
                                                  return;
                                              }
                                              const QByteArray body =
                                                  R"([{"asset":"BTC","balance":"0.75","availableBalance":"0.50"}])";
                                              writeJsonResponseAndClose(socket, body);
                                          });
                     });
    const auto coinBalance = BinanceRestClient::fetchUsdtBalance(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        true,
        false,
        5000,
        QStringLiteral("http://127.0.0.1:%1/dapi").arg(coinBalanceServer.serverPort()));
    check(coinBalance.ok, QStringLiteral("C++ Coin-M balance should parse a collateral row"));
    check(coinBalance.asset == QStringLiteral("BTC"),
          QStringLiteral("C++ Coin-M balance should preserve the collateral asset"));
    check(std::abs(coinBalance.totalBalance - 0.75) < 1e-9,
          QStringLiteral("C++ Coin-M balance should expose canonical total collateral"));
    check(std::abs(coinBalance.availableBalance - 0.50) < 1e-9,
          QStringLiteral("C++ Coin-M balance should expose canonical available collateral"));
    check(observedCoinBalanceRequest.startsWith("GET /dapi/v1/balance?"),
          QStringLiteral("C++ Coin-M balance should request the DAPI balance endpoint"));

    QTcpServer spotServer;
    check(spotServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local Spot HTTP test server should listen"));
    QByteArray observedSpotExchangeInfoRequest;
    QByteArray observedSpotBalanceRequest;
    QByteArray observedSpotOrderRequest;
    QObject::connect(&spotServer, &QTcpServer::newConnection,
                     [&spotServer, &observedSpotExchangeInfoRequest, &observedSpotBalanceRequest, &observedSpotOrderRequest]() {
        QTcpSocket *socket = spotServer.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead,
                         [socket, &observedSpotExchangeInfoRequest, &observedSpotBalanceRequest, &observedSpotOrderRequest]() {
            const QByteArray request = socket->readAll();
            if (!request.contains("\r\n\r\n")) {
                return;
            }
            const QByteArray requestLine = request.left(request.indexOf('\n')).trimmed();
            if (requestLine.startsWith("GET /api/v3/account?")) {
                observedSpotBalanceRequest = requestLine;
                writeJsonResponseAndClose(
                    socket,
                    R"({"balances":[{"asset":"USDT","free":"100","locked":"0"},{"asset":"ETH","free":"0.25","locked":"0"}]})");
            } else if (requestLine.startsWith("GET /api/v3/exchangeInfo")) {
                observedSpotExchangeInfoRequest = requestLine;
                writeJsonResponseAndClose(
                    socket,
                    R"({"symbols":[{"symbol":"ETHUSDT","status":"TRADING","baseAsset":"ETH","quoteAsset":"USDT","baseAssetPrecision":8,"quotePrecision":8,"filters":[{"filterType":"LOT_SIZE","stepSize":"0.001","minQty":"0.001","maxQty":"100"},{"filterType":"MIN_NOTIONAL","minNotional":"5"},{"filterType":"PRICE_FILTER","tickSize":"0.01"}]}]})");
            } else if (requestLine.startsWith("POST /api/v3/order?")) {
                observedSpotOrderRequest = requestLine;
                writeJsonResponseAndClose(
                    socket,
                    R"({"symbol":"ETHUSDT","side":"BUY","orderId":42,"status":"NEW","executedQty":"0.1","cummulativeQuoteQty":"200"})");
            }
        });
    });
    const QString spotBaseUrl = QStringLiteral("http://127.0.0.1:%1").arg(spotServer.serverPort());
    const auto spotBalances = BinanceRestClient::fetchSpotBalances(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        false,
        5000,
        spotBaseUrl);
    check(spotBalances.ok && spotBalances.balances.size() == 2,
          QStringLiteral("C++ Spot account should parse all balance rows"));
    check(spotBalances.ok && spotBalances.balances.at(1).asset == QStringLiteral("ETH")
              && std::abs(spotBalances.balances.at(1).free - 0.25) < 1e-12,
          QStringLiteral("C++ Spot account should preserve free asset quantities"));
    check(observedSpotBalanceRequest.startsWith("GET /api/v3/account?"),
          QStringLiteral("C++ Spot account should request the signed Spot account endpoint"));
    const auto spotFilters = BinanceRestClient::fetchSpotSymbolFilters(
        QStringLiteral("ethusdt"), false, 5000, spotBaseUrl);
    check(spotFilters.ok, QStringLiteral("C++ Spot exchangeInfo should parse symbol filters"));
    check(std::abs(spotFilters.stepSize - 0.001) < 1e-12,
          QStringLiteral("C++ Spot filters should preserve LOT_SIZE step size"));
    check(std::abs(spotFilters.minNotional - 5.0) < 1e-12,
          QStringLiteral("C++ Spot filters should preserve MIN_NOTIONAL"));
    check(spotFilters.status == QStringLiteral("TRADING")
              && spotFilters.baseAsset == QStringLiteral("ETH")
              && spotFilters.quoteAsset == QStringLiteral("USDT"),
          QStringLiteral("C++ Spot filters should preserve symbol trading metadata"));
    check(spotFilters.quantityPrecision == 8,
          QStringLiteral("C++ Spot filters should fall back to baseAssetPrecision"));
    check(observedSpotExchangeInfoRequest.startsWith("GET /api/v3/exchangeInfo "),
          QStringLiteral("C++ Spot filters should request the Spot exchangeInfo endpoint"));

    const auto spotOrder = BinanceRestClient::placeSpotMarketOrder(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("ethusdt"),
        QStringLiteral("buy"),
        0.1,
        false,
        5000,
        spotBaseUrl);
    check(spotOrder.ok && spotOrder.orderId == QStringLiteral("42")
              && spotOrder.status == QStringLiteral("NEW"),
          QStringLiteral("C++ Spot market order should require and parse a successful response"));
    check(observedSpotOrderRequest.startsWith("POST /api/v3/order?"),
          QStringLiteral("C++ Spot order should request the Spot order endpoint"));
    check(!observedSpotOrderRequest.contains("positionSide")
              && !observedSpotOrderRequest.contains("reduceOnly"),
          QStringLiteral("C++ Spot order should not send Futures-only fields"));

    const QStringList dashboardResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("dashboard"));
    check(contains(dashboardResponseFields, QStringLiteral("runtime")),
          QStringLiteral("dashboard route should expose runtime response field"));
    check(contains(dashboardResponseFields, QStringLiteral("service_api")),
          QStringLiteral("dashboard route should expose service_api response field"));

    const QStringList configResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("config"));
    check(contains(configResponseFields, QStringLiteral("llm")),
          QStringLiteral("config route should expose llm response field"));
    check(contains(configResponseFields, QStringLiteral("exchange_support")),
          QStringLiteral("config route should expose exchange_support response field"));

    const QStringList llmProviderResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("llm_providers"));
    for (const QString &field : {
             QStringLiteral("default_base_url"),
             QStringLiteral("default_model"),
             QStringLiteral("model_suggestions"),
             QStringLiteral("reasoning_efforts"),
             QStringLiteral("default_reasoning_effort"),
             QStringLiteral("catalog_revision"),
             QStringLiteral("catalog_path"),
             QStringLiteral("custom_models_env"),
             QStringLiteral("custom_models_path_env"),
             QStringLiteral("catalog_note"),
             QStringLiteral("notes"),
         }) {
        check(contains(llmProviderResponseFields, field),
              QStringLiteral("llm_providers route should expose Python catalog field %1").arg(field));
    }

    const QStringList llmConfigResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("llm_config"));
    for (const QString &field : {
             QStringLiteral("catalog_revision"),
             QStringLiteral("catalog_path"),
             QStringLiteral("custom_models_env"),
             QStringLiteral("custom_models_path_env"),
             QStringLiteral("default_reasoning_effort"),
             QStringLiteral("reasoning_efforts"),
             QStringLiteral("model_suggestions"),
             QStringLiteral("execution_policy"),
         }) {
        check(contains(llmConfigResponseFields, field),
              QStringLiteral("llm_config route should expose Python catalog field %1").arg(field));
    }

    const QStringList accountResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("account"));
    for (const QString &field : {
             QStringLiteral("balance_currency"),
             QStringLiteral("total_balance"),
             QStringLiteral("available_balance"),
             QStringLiteral("source"),
         }) {
        check(contains(accountResponseFields, field),
              QStringLiteral("account route should expose C++ delegated field %1").arg(field));
    }

    QTcpServer server;
    check(server.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local HTTP test server should listen"));
    QByteArray observedRequest;
    QObject::connect(&server, &QTcpServer::newConnection, [&server, &observedRequest]() {
        QTcpSocket *socket = server.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, [socket, &observedRequest]() {
            observedRequest += socket->readAll();
            if (!observedRequest.contains("\r\n\r\n")) {
                return;
            }
            const QByteArray body =
                R"({"runtime":{"service_name":"Trading Bot Service"},"service_api":{"host_context":"cpp-test"}})";
            writeJsonResponseAndClose(socket, body);
        });
    });

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL",
            QByteArray("http://127.0.0.1:") + QByteArray::number(server.serverPort()) + QByteArray("/"));

    const TradingBotWindowSupport::ServiceApiJsonResult apiResult =
        TradingBotWindowSupport::serviceApiRequestJson(QStringLiteral("GET"), QStringLiteral("dashboard"), {}, 5000);
    check(apiResult.ok, QStringLiteral("C++ Service API helper should parse local JSON response"));
    check(apiResult.statusCode == 200,
          QStringLiteral("C++ Service API helper should expose HTTP status"));
    check(
        apiResult.document.object().value(QStringLiteral("runtime")).toObject().value(QStringLiteral("service_name")).toString()
            == QStringLiteral("Trading Bot Service"),
        QStringLiteral("C++ Service API helper should expose parsed runtime response body"));
    check(observedRequest.startsWith("GET /api/v1/dashboard "),
          QStringLiteral("C++ Service API helper should request generated dashboard route path"));

    QTcpServer terminalServer;
    check(terminalServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local terminal HTTP test server should listen"));
    QByteArray observedTerminalRequest;
    QObject::connect(&terminalServer, &QTcpServer::newConnection, [&terminalServer, &observedTerminalRequest]() {
        QTcpSocket *socket = terminalServer.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, [socket, &observedTerminalRequest]() {
            observedTerminalRequest += socket->readAll();
            if (!observedTerminalRequest.contains("\r\n\r\n")) {
                return;
            }
            const QByteArray body =
                R"({"command":"status api_key=<redacted>","exit_code":0,"output":"{\"state\":\"ready\"}","source":"cpp-test","created_at":"2026-06-18T12:10:00+00:00","command_type":"service-command"})";
            writeJsonResponseAndClose(socket, body);
        });
    });

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL",
            QByteArray("http://127.0.0.1:") + QByteArray::number(terminalServer.serverPort()));
    const TradingBotWindowSupport::ServiceApiJsonResult terminalResult =
        TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("POST"),
            QStringLiteral("terminal_run"),
            QJsonObject{
                {QStringLiteral("command"), QStringLiteral("status api_key=super-secret-value")},
                {QStringLiteral("source"), QStringLiteral("cpp-test")},
            },
            5000);
    check(terminalResult.ok,
          QStringLiteral("C++ Service API helper should parse terminal_run JSON response"));
    check(observedTerminalRequest.startsWith("POST /api/v1/terminal/run "),
          QStringLiteral("C++ Service API helper should request generated terminal_run route path"));
    check(observedTerminalRequest.contains("\"command\""),
          QStringLiteral("C++ Service API helper should send terminal command payload"));
    check(
        terminalResult.document.object().value(QStringLiteral("command")).toString().contains(QStringLiteral("<redacted>")),
        QStringLiteral("terminal_run response should preserve Python redaction marker"));

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL", QByteArray("http://127.0.0.1:8123/"));

    check(
        TradingBotWindowSupport::serviceApiUrlForRoute(QStringLiteral("dashboard"))
            == QStringLiteral("http://127.0.0.1:8123/api/v1/dashboard"),
        QStringLiteral("dashboard route URL should be generated from Python route path"));
    check(TradingBotWindowSupport::pythonSourceServiceRouteRequestFields(QStringLiteral("unknown")).isEmpty(),
          QStringLiteral("unknown route request fields should be empty"));
    check(
        TradingBotWindowSupport::serviceApiUrlForRoute(QStringLiteral("unknown"))
            == QStringLiteral("http://127.0.0.1:8123"),
        QStringLiteral("unknown route URL should return base Service API URL"));

    QTcpServer klineServer;
    check(klineServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local kline HTTP test server should listen"));
    QVector<qint64> observedKlineStarts;
    QStringList observedKlineIntervals;
    QObject::connect(&klineServer, &QTcpServer::newConnection, [&]() {
        QTcpSocket *socket = klineServer.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, [&, socket]() {
            const QByteArray requestBytes = socket->readAll();
            const QList<QByteArray> requestLines = requestBytes.split('\n');
            const QList<QByteArray> requestLineParts = requestLines.value(0).trimmed().split(' ');
            const QByteArray target = requestLineParts.size() >= 2 ? requestLineParts.at(1) : QByteArray("/");
            const QUrl requestUrl(QStringLiteral("http://localhost") + QString::fromUtf8(target));
            const QUrlQuery query(requestUrl);
            const qint64 startTime = query.queryItemValue(QStringLiteral("startTime")).toLongLong();
            const qint64 endTime = query.queryItemValue(QStringLiteral("endTime")).toLongLong();
            const int limit = query.queryItemValue(QStringLiteral("limit")).toInt();
            observedKlineStarts.append(startTime);
            observedKlineIntervals.append(query.queryItemValue(QStringLiteral("interval")));

            QJsonArray candles;
            constexpr qint64 intervalMs = 60'000;
            for (qint64 openTime = startTime;
                 openTime <= endTime && candles.size() < std::max(1, limit);
                 openTime += intervalMs) {
                const double open = 100.0 + static_cast<double>(openTime / intervalMs);
                candles.append(QJsonArray{
                    openTime,
                    QString::number(open, 'f', 2),
                    QString::number(open + 2.0, 'f', 2),
                    QString::number(open - 1.0, 'f', 2),
                    QString::number(open + 1.0, 'f', 2),
                    QStringLiteral("1.0"),
                });
            }
            const QByteArray body = QJsonDocument(candles).toJson(QJsonDocument::Compact);
            writeJsonResponseAndClose(socket, body);
        });
    });
    const QString klineBaseUrl = QStringLiteral("http://127.0.0.1:%1").arg(klineServer.serverPort());
    constexpr qint64 pageStart = 60'000;
    constexpr qint64 minuteMs = 60'000;
    const BinanceRestClient::KlinesResult pagedKlines = BinanceRestClient::fetchKlinesRange(
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        false,
        false,
        pageStart,
        pageStart + 1001 * minuteMs,
        2'000,
        5'000,
        klineBaseUrl);
    check(pagedKlines.ok && pagedKlines.candles.size() == 1002,
          QStringLiteral("native historical loader should page a range larger than Binance spot page size"));
    check(observedKlineStarts.size() >= 2
              && observedKlineStarts.at(1) == pageStart + 1000 * minuteMs,
          QStringLiteral("native historical loader should advance the next page after the last open time"));
    check(observedKlineIntervals.size() >= 2
              && observedKlineIntervals.at(0) == QStringLiteral("1m"),
          QStringLiteral("native historical loader should preserve native Binance intervals"));

    constexpr qint64 customStart = 7 * minuteMs;
    const BinanceRestClient::KlinesResult customKlines = BinanceRestClient::fetchKlinesRange(
        QStringLiteral("ETHUSDT"),
        QStringLiteral("7m"),
        false,
        false,
        customStart,
        customStart + 13 * minuteMs,
        100,
        5'000,
        klineBaseUrl);
    check(customKlines.ok && customKlines.candles.size() == 2,
          QStringLiteral("native historical loader should aggregate custom seven-minute labels"));
    check(customKlines.ok && std::abs(customKlines.candles.constFirst().volume - 7.0) < 1e-12,
          QStringLiteral("native custom interval aggregation should sum source volume"));
    check(observedKlineIntervals.constLast() == QStringLiteral("1m"),
          QStringLiteral("native custom interval aggregation should fetch the supported one-minute base"));

    const int requestsBeforeCancellation = observedKlineStarts.size();
    const BinanceRestClient::KlinesResult cancelledKlines = BinanceRestClient::fetchKlinesRange(
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        false,
        false,
        pageStart,
        pageStart + minuteMs,
        10,
        5'000,
        klineBaseUrl,
        []() { return true; });
    check(!cancelledKlines.ok && cancelledKlines.error.contains(QStringLiteral("cancelled"), Qt::CaseInsensitive),
          QStringLiteral("native historical loader should honor cancellation before issuing a page request"));
    check(observedKlineStarts.size() == requestsBeforeCancellation,
          QStringLiteral("cancelled native historical fetch should not contact the exchange"));

    return failures == 0 ? 0 : 1;
}
