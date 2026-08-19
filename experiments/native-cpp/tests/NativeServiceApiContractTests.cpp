#include "../src/TradingBotWindowSupport.h"
#include "../src/BinanceRestClient.h"
#include "../src/NativeConfigPersistence.h"
#include "../src/generated/PythonParityContract.h"

#include <QByteArray>
#include <QCoreApplication>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSet>
#include <QTcpServer>
#include <QTcpSocket>
#include <QUrl>
#include <QUrlQuery>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <span>
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

    for (const auto &referenceCase : PythonParityContract::kPythonRuntimeConfigReferenceCases) {
        const QString caseName = parityString(referenceCase.name);
        const QByteArray inputJson(referenceCase.inputJson.data(),
                                   static_cast<int>(referenceCase.inputJson.size()));
        const QByteArray expectedJson(referenceCase.expectedJson.data(),
                                      static_cast<int>(referenceCase.expectedJson.size()));
        QJsonParseError inputError;
        const QJsonDocument inputDocument = QJsonDocument::fromJson(inputJson, &inputError);
        check(!inputDocument.isNull() && inputDocument.isObject(),
              QStringLiteral("generated Python config input should parse: %1 (%2)")
                  .arg(caseName, inputError.errorString()));
        if (inputDocument.isNull() || !inputDocument.isObject()) {
            continue;
        }
        QJsonParseError expectedError;
        const QJsonDocument expectedDocument = QJsonDocument::fromJson(expectedJson, &expectedError);
        check(!expectedDocument.isNull() && expectedDocument.isObject(),
              QStringLiteral("generated Python config expected output should parse: %1 (%2)")
                  .arg(caseName, expectedError.errorString()));
        if (expectedDocument.isNull() || !expectedDocument.isObject()) {
            continue;
        }
        const NativeConfigPersistence::ServiceConfigValidationResult result =
            NativeConfigPersistence::validateServiceRuntimeConfig(inputDocument.object());
        check(result.ok == referenceCase.valid,
              QStringLiteral("C++ runtime config acceptance should match Python: %1")
                  .arg(caseName));
        if (referenceCase.valid) {
            check(result.config == expectedDocument.object(),
                  QStringLiteral("C++ runtime config normalization should match Python: %1")
                      .arg(caseName));
        } else {
            check(result.error == parityString(referenceCase.expectedError),
                  QStringLiteral("C++ runtime config rejection should match Python: %1 (actual=%2 expected=%3)")
                      .arg(caseName, result.error, parityString(referenceCase.expectedError)));
        }
    }

    for (const auto &referenceCase : PythonParityContract::kPythonConnectorNormalizationReferenceCases) {
        const QString caseName = parityString(referenceCase.name);
        const QString actual =
            TradingBotWindowSupport::normalizeConnectorBackend(parityString(referenceCase.input));
        check(actual == parityString(referenceCase.expected),
              QStringLiteral("C++ connector normalization should match Python: %1").arg(caseName));
    }

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
    const auto checkStarterCatalog = [&check](const auto &options, const QString &catalogName) {
        check(!options.empty(), QStringLiteral("Python starter catalog should not be empty: %1").arg(catalogName));
        for (const auto &option : options) {
            const QString key = parityString(option.key);
            check(!key.isEmpty(), QStringLiteral("Python starter catalog key should be present: %1").arg(catalogName));
            check(!parityString(option.title).isEmpty(),
                  QStringLiteral("Python starter catalog title should be present: %1").arg(key));
            check(!parityString(option.subtitle).isEmpty(),
                  QStringLiteral("Python starter catalog subtitle should be present: %1").arg(key));
        }
    };
    checkStarterCatalog(
        PythonParityContract::kPythonCodeLanguageOptions,
        QStringLiteral("code languages"));
    checkStarterCatalog(
        PythonParityContract::kPythonRustFrameworkOptions,
        QStringLiteral("Rust frameworks"));
    checkStarterCatalog(
        PythonParityContract::kPythonStarterMarketOptions,
        QStringLiteral("starter markets"));

    const auto checkUiCatalog = [&check](const auto &options, const QString &catalogName) {
        check(!options.empty(), QStringLiteral("Python UI catalog should not be empty: %1").arg(catalogName));
        QSet<QString> keys;
        for (const auto &option : options) {
            const QString key = parityString(option.key);
            const QString label = parityString(option.label);
            check(!label.isEmpty(),
                  QStringLiteral("Python UI catalog label should be present: %1").arg(key));
            if (key.isEmpty()) {
                check(catalogName == QStringLiteral("dashboard strategy templates")
                          && label == QStringLiteral("No Template"),
                      QStringLiteral("only Python's No Template sentinel may have an empty key"));
            }
            check(!keys.contains(key),
                  QStringLiteral("Python UI catalog key should be unique: %1 (%2)").arg(catalogName, key));
            keys.insert(key);
        }
    };
    for (const auto &catalog : PythonParityContract::kPythonUiOptionCatalogs) {
        checkUiCatalog(
            std::span<const PythonParityContract::PythonUiOption>(catalog.options, catalog.size),
            parityString(catalog.name));
    }
    check(PythonParityContract::kPythonCodeLanguageOptions.size() == 3,
          QStringLiteral("Python code-language catalog should expose Python, C++, and Rust"));
    check(PythonParityContract::kPythonRustFrameworkOptions.size() == 1
              && parityString(PythonParityContract::kPythonRustFrameworkOptions.front().key)
                     == QStringLiteral("Tauri"),
          QStringLiteral("Python Rust framework catalog should expose Tauri"));
    check(PythonParityContract::kPythonStarterMarketOptions.size() == 2,
          QStringLiteral("Python starter-market catalog should expose crypto and forex"));
    check(TradingBotWindowSupport::pythonSourceCodeLanguageOptionKeys().size() == 3
              && TradingBotWindowSupport::pythonSourceCodeLanguageOptionLabels().size() == 3,
          QStringLiteral("C++ code-language accessors should expose the generated Python catalog"));
    check(TradingBotWindowSupport::pythonSourceRustFrameworkOptionKeys()
              == QStringList{QStringLiteral("Tauri")}
              && TradingBotWindowSupport::pythonSourceRustFrameworkOptionLabels()
                     == QStringList{QStringLiteral("Tauri")},
          QStringLiteral("C++ Rust-framework accessors should expose Python's Tauri option"));
    check(TradingBotWindowSupport::pythonSourceStarterMarketOptionKeys()
              == QStringList{QStringLiteral("crypto"), QStringLiteral("forex")},
          QStringLiteral("C++ starter-market accessors should expose Python's crypto and forex options"));
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
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("ccxt")),
        QStringLiteral("C++ native runtime should own Python's Binance CCXT provider alias"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("binance-connector")),
        QStringLiteral("C++ native runtime should accept Python's Binance Connector alias"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("python-binance")),
        QStringLiteral("C++ native runtime should own Python's python-binance provider alias"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("CCXT Unified")),
        QStringLiteral("C++ native runtime should own Python's normalized CCXT alias"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("Binance SDK USD-M Futures")),
        QStringLiteral("C++ native runtime should own Python's normalized USD-M alias"));
    check(
        !TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(QStringLiteral("custom")),
        QStringLiteral("C++ native runtime should reject unknown connector providers"));
    check(
        !TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("OANDA REST-v20")),
        QStringLiteral("C++ native runtime should delegate Python's non-native OANDA connector"));
    check(
        !TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("unknown backend")),
        QStringLiteral("C++ native runtime should reject unknown connector text"));
    check(
        TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(
            QStringLiteral("binance-sdk-spot")),
        QStringLiteral("C++ native runtime should own Python's Binance Spot connector"));
    for (const auto &mapping : PythonParityContract::kPythonNativeRuntimeConnectorMarketFamilies) {
        const QString backend = parityString(mapping.key);
        check(
            TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(backend),
            QStringLiteral("every Python-declared native connector market mapping should be owned: %1")
                .arg(backend));
    }
    for (const auto &option : PythonParityContract::kPythonConnectorOptions) {
        const QString key = parityString(option.key);
        const QString label = parityString(option.label);
        const bool declaredNative = std::any_of(
            PythonParityContract::kPythonNativeRuntimeConnectorBackends.begin(),
            PythonParityContract::kPythonNativeRuntimeConnectorBackends.end(),
            [&key](const std::string_view backend) {
                return parityString(backend).compare(key, Qt::CaseInsensitive) == 0;
            });
        check(
            TradingBotWindowSupport::nativeRuntimeOwnsBinanceFuturesConnector(label) == declaredNative,
            QStringLiteral("C++ connector ownership should match Python for option: %1").arg(key));
    }

    const auto checkGeneratedChoiceGroup = [&failures, &check](
        const QString &field,
        const auto &choices,
        const QString &section = QString()) {
        for (const auto &choice : choices) {
            if (parityString(choice.key).isEmpty()) {
                continue;
            }
            QJsonObject target;
            target.insert(field, parityString(choice.key));
            QJsonObject config;
            if (section.isEmpty()) {
                config = target;
            } else {
                config.insert(section, target);
            }
            const NativeConfigPersistence::ServiceConfigValidationResult result =
                NativeConfigPersistence::validateServiceRuntimeConfig(config);
            check(result.ok,
                  QStringLiteral("C++ Python config choice should validate: %1=%2")
                      .arg(field, parityString(choice.key)));
            if (!result.ok) {
                continue;
            }
            const QJsonObject normalized = section.isEmpty()
                ? result.config
                : result.config.value(section).toObject();
            check(normalized.value(field).toString() == parityString(choice.value),
                  QStringLiteral("C++ Python config choice should normalize: %1=%2")
                      .arg(field, parityString(choice.key)));
        }
    };
    checkGeneratedChoiceGroup(QStringLiteral("account_type"), PythonParityContract::kPythonAccountTypeConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("margin_mode"), PythonParityContract::kPythonMarginModeConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("position_mode"), PythonParityContract::kPythonPositionModeConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("assets_mode"), PythonParityContract::kPythonAssetsModeConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("account_mode"), PythonParityContract::kPythonAccountModeConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("side"), PythonParityContract::kPythonSideConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("order_type"), PythonParityContract::kPythonOrderTypeConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("tif"), PythonParityContract::kPythonTifConfigChoices);
    checkGeneratedChoiceGroup(QStringLiteral("llm_provider"), PythonParityContract::kPythonLlmProviderChoices);
    checkGeneratedChoiceGroup(QStringLiteral("llm_use_for"), PythonParityContract::kPythonLlmUseForConfigChoices);
    checkGeneratedChoiceGroup(
        QStringLiteral("llm_reasoning_effort"),
        PythonParityContract::kPythonLlmReasoningEffortConfigChoices);
    for (const std::string_view market : PythonParityContract::kPythonChartMarketOptions) {
        const QString marketValue = parityString(market);
        QJsonObject chartConfig;
        chartConfig.insert(QStringLiteral("market"), marketValue);
        const NativeConfigPersistence::ServiceConfigValidationResult result =
            NativeConfigPersistence::validateServiceRuntimeConfig(
                QJsonObject{{QStringLiteral("chart"), chartConfig}});
        check(result.ok,
              QStringLiteral("C++ Python chart market choice should validate: %1").arg(marketValue));
        if (!result.ok) {
            continue;
        }
        const QJsonObject normalized = result.config.value(QStringLiteral("chart")).toObject();
        check(normalized.value(QStringLiteral("market")).toString() == marketValue,
              QStringLiteral("C++ Python chart market choice should normalize: %1").arg(marketValue));
    }
    checkGeneratedChoiceGroup(
        QStringLiteral("view_mode"),
        PythonParityContract::kPythonChartViewModeConfigChoices,
        QStringLiteral("chart"));
    checkGeneratedChoiceGroup(
        QStringLiteral("execution_backend"),
        PythonParityContract::kPythonBacktestExecutionBackendConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("logic"),
        PythonParityContract::kPythonLogicConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("side"),
        PythonParityContract::kPythonSideConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("margin_mode"),
        PythonParityContract::kPythonMarginModeConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("position_mode"),
        PythonParityContract::kPythonPositionModeConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("assets_mode"),
        PythonParityContract::kPythonAssetsModeConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("account_mode"),
        PythonParityContract::kPythonAccountModeConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("mdd_logic"),
        PythonParityContract::kPythonMddLogicConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("scan_scope"),
        PythonParityContract::kPythonScanScopeConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("optimizer_mode"),
        PythonParityContract::kPythonOptimizerModeConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("optimizer_metric"),
        PythonParityContract::kPythonOptimizerMetricConfigChoices,
        QStringLiteral("backtest"));
    checkGeneratedChoiceGroup(
        QStringLiteral("mode"),
        PythonParityContract::kPythonStopLossModeConfigChoices,
        QStringLiteral("stop_loss"));
    checkGeneratedChoiceGroup(
        QStringLiteral("scope"),
        PythonParityContract::kPythonStopLossScopeConfigChoices,
        QStringLiteral("stop_loss"));

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
    const auto coinBalanceRows = BinanceRestClient::fetchBalanceRows(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        true,
        false,
        5000,
        QStringLiteral("http://127.0.0.1:%1/dapi").arg(coinBalanceServer.serverPort()));
    check(coinBalanceRows.ok && coinBalanceRows.balances.size() == 1
              && coinBalanceRows.balances.first().asset == QStringLiteral("BTC")
              && std::abs(coinBalanceRows.balances.first().free - 0.50) < 1e-12
              && std::abs(coinBalanceRows.balances.first().total - 0.75) < 1e-12,
          QStringLiteral("C++ normalized futures balance rows should match Python free/total semantics"));

    QTcpServer coinOrderLifecycleServer;
    check(coinOrderLifecycleServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local Coin-M order lifecycle HTTP test server should listen"));
    QByteArray observedCoinOpenOrdersRequest;
    QByteArray observedCoinCancelAllRequest;
    QByteArray observedCoinCancelOneRequest;
    QByteArray observedCoinBookTickerRequest;
    QByteArray observedCoinTradesRequest;
    QByteArray observedCoinLeverageBracketRequest;
    QByteArray observedCoinPositionModeGetRequest;
    QByteArray observedCoinPositionModeChangeRequest;
    QByteArray observedCoinMarginTypeRequest;
    QByteArray observedCoinLeverageRequest;
    QByteArray observedCoinMultiAssetsGetRequest;
    QByteArray observedCoinMultiAssetsChangeRequest;
    QByteArray observedCoinForceOrdersRequest;
    QByteArray observedCoinPositionMarginRequest;
    QObject::connect(&coinOrderLifecycleServer, &QTcpServer::newConnection,
                     [&coinOrderLifecycleServer, &observedCoinOpenOrdersRequest,
                      &observedCoinCancelAllRequest, &observedCoinCancelOneRequest,
                      &observedCoinBookTickerRequest, &observedCoinTradesRequest,
                      &observedCoinLeverageBracketRequest, &observedCoinPositionModeGetRequest,
                      &observedCoinPositionModeChangeRequest, &observedCoinMarginTypeRequest,
                      &observedCoinLeverageRequest, &observedCoinMultiAssetsGetRequest,
                      &observedCoinMultiAssetsChangeRequest, &observedCoinForceOrdersRequest,
                      &observedCoinPositionMarginRequest]() {
                         QTcpSocket *socket = coinOrderLifecycleServer.nextPendingConnection();
                         QObject::connect(socket, &QTcpSocket::readyRead,
                                          [socket, &observedCoinOpenOrdersRequest,
                                           &observedCoinCancelAllRequest,
                                           &observedCoinCancelOneRequest,
                                           &observedCoinBookTickerRequest,
                                           &observedCoinTradesRequest,
                                           &observedCoinLeverageBracketRequest,
                                           &observedCoinPositionModeGetRequest,
                                           &observedCoinPositionModeChangeRequest,
                                           &observedCoinMarginTypeRequest,
                                           &observedCoinLeverageRequest,
                                           &observedCoinMultiAssetsGetRequest,
                                           &observedCoinMultiAssetsChangeRequest,
                                           &observedCoinForceOrdersRequest,
                                           &observedCoinPositionMarginRequest]() {
                                              const QByteArray request = socket->readAll();
                                              if (!request.contains("\r\n\r\n")) {
                                                  return;
                                              }
                                              const QByteArray requestLine =
                                                  request.left(request.indexOf('\n')).trimmed();
                                              if (requestLine.startsWith("GET /dapi/v1/openOrders?")) {
                                                  observedCoinOpenOrdersRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"([{"symbol":"BTCUSD_PERP","orderId":123,"clientOrderId":"client-1","status":"NEW","side":"SELL","type":"LIMIT","positionSide":"LONG","origQty":"2","executedQty":"0","price":"40000"}])");
                                              } else if (requestLine.startsWith(
                                                             "DELETE /dapi/v1/allOpenOrders?")) {
                                                  observedCoinCancelAllRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"code":200,"msg":"The liquidation is successful."})");
                                              } else if (requestLine.startsWith("DELETE /dapi/v1/order?")) {
                                                  observedCoinCancelOneRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"symbol":"BTCUSD_PERP","orderId":123,"status":"CANCELED"})");
                                              } else if (requestLine.startsWith("GET /dapi/v1/ticker/bookTicker?")) {
                                                  observedCoinBookTickerRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"symbol":"BTCUSD_PERP","bidPrice":"40000","bidQty":"2","askPrice":"40001","askQty":"3"})");
                                              } else if (requestLine.startsWith("GET /dapi/v1/userTrades?")) {
                                                  observedCoinTradesRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"([{"symbol":"BTCUSD_PERP","id":1,"orderId":123,"price":"40000","qty":"2","quoteQty":"80000","realizedPnl":"4","commission":"0.1","commissionAsset":"USDT","time":1700000000000}])");
                                              } else if (requestLine.startsWith("GET /dapi/v1/leverageBracket?")) {
                                                  observedCoinLeverageBracketRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"([{"symbol":"BTCUSD_PERP","brackets":[{"initialLeverage":50,"notionalCap":"100000","notionalFloor":"0","maintMarginRatio":"0.01","cum":"0"}]}])");
                                              } else if (requestLine.startsWith(
                                                             "GET /dapi/v1/positionSide/dual?")) {
                                                  observedCoinPositionModeGetRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"dualSidePosition":true})");
                                              } else if (requestLine.startsWith(
                                                             "POST /dapi/v1/positionSide/dual?")) {
                                                  observedCoinPositionModeChangeRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"code":200,"msg":"success"})");
                                              } else if (requestLine.startsWith("POST /dapi/v1/marginType?")) {
                                                  observedCoinMarginTypeRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"code":200,"msg":"success"})");
                                              } else if (requestLine.startsWith("POST /dapi/v1/leverage?")) {
                                                  observedCoinLeverageRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"symbol":"BTCUSD_PERP","leverage":25,"maxNotionalValue":"100000"})");
                                              } else if (requestLine.startsWith(
                                                             "GET /dapi/v1/multiAssetsMargin?")) {
                                                  observedCoinMultiAssetsGetRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"multiAssetsMargin":false})");
                                              } else if (requestLine.startsWith(
                                                             "POST /dapi/v1/multiAssetsMargin?")) {
                                                  observedCoinMultiAssetsChangeRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"code":200,"msg":"success"})");
                                              } else if (requestLine.startsWith("GET /dapi/v1/forceOrders?")) {
                                                  observedCoinForceOrdersRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"forceOrders":[{"symbol":"BTCUSD_PERP","orderId":456,"side":"SELL","positionSide":"LONG","status":"FILLED","type":"LIMIT","avgPrice":"40000","executedQty":"2","origQty":"2","price":"39900","time":1700000000000,"updateTime":1700000001000}]})");
                                              } else if (requestLine.startsWith("POST /dapi/v1/positionMargin?")) {
                                                  observedCoinPositionMarginRequest = requestLine;
                                                  writeJsonResponseAndClose(
                                                      socket,
                                                      R"({"code":200,"msg":"success"})");
                                              }
                                          });
                     });
    const QString coinOrderLifecycleBaseUrl =
        QStringLiteral("http://127.0.0.1:%1/dapi").arg(coinOrderLifecycleServer.serverPort());
    const auto coinOpenOrders = BinanceRestClient::fetchOpenFuturesOrders(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("btcusd_perp"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinOpenOrders.ok && coinOpenOrders.orders.size() == 1,
          QStringLiteral("C++ Coin-M open-orders endpoint should parse a symbol-scoped row"));
    check(coinOpenOrders.ok && coinOpenOrders.orders.first().orderId == QStringLiteral("123")
              && coinOpenOrders.orders.first().positionSide == QStringLiteral("LONG"),
          QStringLiteral("C++ Coin-M open-orders parser should preserve order identity and hedge leg"));
    check(observedCoinOpenOrdersRequest.startsWith("GET /dapi/v1/openOrders?"),
          QStringLiteral("C++ Coin-M open-orders request should use the DAPI endpoint"));

    const auto coinCancelAll = BinanceRestClient::cancelAllOpenFuturesOrders(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinCancelAll.ok && coinCancelAll.status == QStringLiteral("CANCELED"),
          QStringLiteral("C++ Coin-M bulk cancellation should accept Binance success code 200"));
    check(observedCoinCancelAllRequest.startsWith("DELETE /dapi/v1/allOpenOrders?"),
          QStringLiteral("C++ Coin-M bulk cancellation should use the DAPI endpoint"));

    const auto coinCancelOne = BinanceRestClient::cancelFuturesOrder(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        QStringLiteral("123"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinCancelOne.ok && coinCancelOne.orderId == QStringLiteral("123")
              && coinCancelOne.status == QStringLiteral("CANCELED"),
          QStringLiteral("C++ Coin-M individual cancellation should parse the acknowledged order"));
    check(observedCoinCancelOneRequest.startsWith("DELETE /dapi/v1/order?"),
          QStringLiteral("C++ Coin-M individual cancellation should use the DAPI endpoint"));

    const auto coinBookTicker = BinanceRestClient::fetchFuturesBookTicker(
        QStringLiteral("BTCUSD_PERP"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinBookTicker.ok && coinBookTicker.symbol == QStringLiteral("BTCUSD_PERP")
              && std::abs(coinBookTicker.bidPrice - 40000.0) < 1e-9
              && std::abs(coinBookTicker.askPrice - 40001.0) < 1e-9,
          QStringLiteral("C++ Coin-M book ticker should preserve Python bid/ask fields"));
    check(observedCoinBookTickerRequest.startsWith("GET /dapi/v1/ticker/bookTicker?"),
          QStringLiteral("C++ Coin-M book ticker should use the DAPI public endpoint"));

    const auto coinTrades = BinanceRestClient::fetchFuturesTrades(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        QStringLiteral("123"),
        100,
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinTrades.ok && coinTrades.trades.size() == 1
              && coinTrades.trades.first().orderId == QStringLiteral("123")
              && std::abs(coinTrades.trades.first().quantity - 2.0) < 1e-9
              && std::abs(coinTrades.trades.first().realizedPnl - 4.0) < 1e-9,
          QStringLiteral("C++ Coin-M trade history should preserve Python fill fields"));
    check(observedCoinTradesRequest.startsWith("GET /dapi/v1/userTrades?"),
          QStringLiteral("C++ Coin-M trade history should use the signed DAPI endpoint"));

    const auto coinLeverageBrackets = BinanceRestClient::fetchFuturesLeverageBrackets(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinLeverageBrackets.ok && coinLeverageBrackets.brackets.size() == 1
              && coinLeverageBrackets.brackets.first().initialLeverage == 50
              && std::abs(coinLeverageBrackets.brackets.first().maintMarginRatio - 0.01) < 1e-12,
          QStringLiteral("C++ Coin-M leverage brackets should preserve Python risk metadata"));
    check(observedCoinLeverageBracketRequest.startsWith("GET /dapi/v1/leverageBracket?"),
          QStringLiteral("C++ Coin-M leverage brackets should use the signed DAPI endpoint"));

    const auto coinMaxLeverage = BinanceRestClient::fetchFuturesMaxLeverage(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        125,
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinMaxLeverage.ok && coinMaxLeverage.symbol == QStringLiteral("BTCUSD_PERP")
              && coinMaxLeverage.maxLeverage == 50,
          QStringLiteral("C++ Coin-M max leverage should match Python leverage-bracket selection"));
    check(BinanceRestClient::clampFuturesLeverage(80, 125, 50, true) == 50
              && BinanceRestClient::clampFuturesLeverage(80, 20, 0, false) == 20
              && BinanceRestClient::clampFuturesLeverage(0, 125, 0, true) == 1,
          QStringLiteral("C++ leverage clamping should match Python configured and symbol caps"));

    const QJsonObject orderSizingReference = QJsonDocument::fromJson(
        QByteArray(PythonParityContract::kPythonOrderSizingReferenceJson.data(),
                   static_cast<qsizetype>(PythonParityContract::kPythonOrderSizingReferenceJson.size())))
                                                       .object();
    const QJsonArray orderSizingCases = orderSizingReference.value(QStringLiteral("cases")).toArray();
    check(orderSizingReference.value(QStringLiteral("schema_version")).toInt() == 1
              && orderSizingCases.size() >= 5,
          QStringLiteral("generated Python order-sizing fixture should expose its complete case set"));
    for (const QJsonValue &caseValue : orderSizingCases) {
        const QJsonObject sizingCase = caseValue.toObject();
        const QString caseName = sizingCase.value(QStringLiteral("name")).toString();
        const QJsonObject filterObject = sizingCase.value(QStringLiteral("filters")).toObject();
        BinanceRestClient::FuturesSymbolFilters sizingFilters;
        sizingFilters.stepSize = filterObject.value(QStringLiteral("stepSize")).toDouble();
        sizingFilters.minQty = filterObject.value(QStringLiteral("minQty")).toDouble();
        sizingFilters.minNotional = filterObject.value(QStringLiteral("minNotional")).toDouble();
        const QString market = sizingCase.value(QStringLiteral("market")).toString();
        if (sizingCase.contains(QStringLiteral("expected_percent"))) {
            const double actual = BinanceRestClient::requiredPercentForSymbol(
                sizingCase.value(QStringLiteral("price")).toDouble(),
                sizingFilters,
                sizingCase.value(QStringLiteral("balance")).toDouble(),
                sizingCase.value(QStringLiteral("leverage")).toDouble());
            check(std::abs(actual - sizingCase.value(QStringLiteral("expected_percent")).toDouble()) < 1e-12,
                  QStringLiteral("C++ required-percent sizing should match Python fixture: %1").arg(caseName));
            continue;
        }
        const auto adjustment = market == QStringLiteral("spot")
            ? BinanceRestClient::adjustSpotQuantityToFilters(
                  sizingFilters,
                  sizingCase.value(QStringLiteral("quantity")).toDouble(),
                  sizingCase.value(QStringLiteral("price")).toDouble())
            : BinanceRestClient::adjustFuturesQuantityToFilters(
                  sizingFilters,
                  sizingCase.value(QStringLiteral("quantity")).toDouble(),
                  sizingCase.value(QStringLiteral("price")).toDouble());
        const QString expectedError = sizingCase.value(QStringLiteral("expected_error")).toString();
        const double expectedQuantity = sizingCase.value(QStringLiteral("expected_quantity")).toDouble();
        check(adjustment.ok == expectedError.isEmpty()
                  && std::abs(adjustment.quantity - expectedQuantity) < 1e-12
                  && (expectedError.isEmpty() || adjustment.error == expectedError),
              QStringLiteral("C++ quantity adjustment should match Python fixture: %1").arg(caseName));
    }
    check(std::abs(BinanceRestClient::floorToStep(1.239, 0.01) - 1.23) < 1e-12
              && std::abs(BinanceRestClient::ceilToStep(1.231, 0.01) - 1.24) < 1e-12
              && std::abs(BinanceRestClient::floorToDecimals(1.239, 2) - 1.23) < 1e-12
              && std::abs(BinanceRestClient::ceilToDecimals(1.231, 2) - 1.24) < 1e-12,
          QStringLiteral("C++ decimal and step helpers should match Python rounding semantics"));
    const QJsonArray roundingCases = orderSizingReference.value(QStringLiteral("rounding_cases")).toArray();
    check(roundingCases.size() >= 3,
          QStringLiteral("generated Python order-sizing fixture should expose decimal rounding cases"));
    for (const QJsonValue &caseValue : roundingCases) {
        const QJsonObject roundingCase = caseValue.toObject();
        const double value = roundingCase.value(QStringLiteral("value")).toDouble();
        const int decimals = roundingCase.value(QStringLiteral("decimals")).toInt();
        const double actualFloor = BinanceRestClient::floorToDecimals(value, decimals);
        const double actualCeil = BinanceRestClient::ceilToDecimals(value, decimals);
        check(std::abs(actualFloor - roundingCase.value(QStringLiteral("expected_floor")).toDouble()) < 1e-12
                  && std::abs(actualCeil - roundingCase.value(QStringLiteral("expected_ceil")).toDouble()) < 1e-12,
              QStringLiteral("C++ decimal rounding should match Python fixture: %1")
                  .arg(roundingCase.value(QStringLiteral("name")).toString()));
    }
    const auto coinPositionMode = BinanceRestClient::fetchFuturesPositionMode(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinPositionMode.ok && coinPositionMode.dualSidePosition
              && coinPositionMode.positionMode == QStringLiteral("HEDGE"),
          QStringLiteral("C++ Coin-M position mode should preserve Python hedge-mode state"));
    check(observedCoinPositionModeGetRequest.startsWith("GET /dapi/v1/positionSide/dual?"),
          QStringLiteral("C++ Coin-M position mode should use the signed DAPI endpoint"));

    const auto changedCoinPositionMode = BinanceRestClient::changeFuturesPositionMode(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        false,
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(changedCoinPositionMode.ok && !changedCoinPositionMode.dualSidePosition
              && changedCoinPositionMode.positionMode == QStringLiteral("ONE_WAY")
              && observedCoinPositionModeChangeRequest.contains("dualSidePosition=false"),
          QStringLiteral("C++ Coin-M position-mode mutation should mirror Python request options"));

    const auto changedCoinMarginType = BinanceRestClient::changeFuturesMarginType(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("btcusd_perp"),
        QStringLiteral("cross"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(changedCoinMarginType.ok && changedCoinMarginType.symbol == QStringLiteral("BTCUSD_PERP")
              && changedCoinMarginType.marginType == QStringLiteral("CROSSED")
              && observedCoinMarginTypeRequest.contains("symbol=BTCUSD_PERP")
              && observedCoinMarginTypeRequest.contains("marginType=CROSSED"),
          QStringLiteral("C++ Coin-M margin mode should normalize and send Python-compatible options"));

    const auto changedCoinLeverage = BinanceRestClient::changeFuturesLeverage(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        25,
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(changedCoinLeverage.ok && changedCoinLeverage.leverage == 25
              && std::abs(changedCoinLeverage.maxNotionalValue - 100000.0) < 1e-9
              && observedCoinLeverageRequest.contains("symbol=BTCUSD_PERP")
              && observedCoinLeverageRequest.contains("leverage=25"),
          QStringLiteral("C++ Coin-M leverage mutation should preserve Python risk settings"));

    const auto coinMultiAssetsMode = BinanceRestClient::fetchFuturesMultiAssetsMode(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinMultiAssetsMode.ok && !coinMultiAssetsMode.multiAssetsMargin
              && observedCoinMultiAssetsGetRequest.startsWith("GET /dapi/v1/multiAssetsMargin?"),
          QStringLiteral("C++ Coin-M multi-assets mode should parse the Python account setting"));

    const auto changedCoinMultiAssetsMode = BinanceRestClient::changeFuturesMultiAssetsMode(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        true,
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(changedCoinMultiAssetsMode.ok && changedCoinMultiAssetsMode.multiAssetsMargin
              && observedCoinMultiAssetsChangeRequest.contains("multiAssetsMargin=true"),
          QStringLiteral("C++ Coin-M multi-assets mutation should mirror Python request options"));

    const auto coinForceOrders = BinanceRestClient::fetchFuturesForceOrders(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        1'700'000'000'000,
        1'700'000'001'000,
        20,
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinForceOrders.ok && coinForceOrders.orders.size() == 1
              && coinForceOrders.orders.first().orderId == QStringLiteral("456")
              && coinForceOrders.orders.first().positionSide == QStringLiteral("LONG")
              && std::abs(coinForceOrders.orders.first().executedQty - 2.0) < 1e-9,
          QStringLiteral("C++ Coin-M force-order history should preserve Python liquidation metadata"));
    check(observedCoinForceOrdersRequest.startsWith("GET /dapi/v1/forceOrders?")
              && observedCoinForceOrdersRequest.contains("symbol=BTCUSD_PERP")
              && observedCoinForceOrdersRequest.contains("startTime=1700000000000")
              && observedCoinForceOrdersRequest.contains("endTime=1700000001000"),
          QStringLiteral("C++ Coin-M force-order history should use the signed DAPI request options"));

    const auto coinPositionMargin = BinanceRestClient::changeFuturesPositionMargin(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("BTCUSD_PERP"),
        1.25,
        QStringLiteral("LONG"),
        false,
        5000,
        coinOrderLifecycleBaseUrl);
    check(coinPositionMargin.ok && coinPositionMargin.symbol == QStringLiteral("BTCUSD_PERP")
              && std::abs(coinPositionMargin.amount - 1.25) < 1e-9
              && observedCoinPositionMarginRequest.contains("symbol=BTCUSD_PERP")
              && observedCoinPositionMarginRequest.contains("amount=1.25")
              && observedCoinPositionMarginRequest.contains("type=1")
              && observedCoinPositionMarginRequest.contains("positionSide=LONG"),
          QStringLiteral("C++ Coin-M position-margin cleanup should mirror Python signed options"));

    QTcpServer spotServer;
    check(spotServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local Spot HTTP test server should listen"));
    QByteArray observedSpotExchangeInfoRequest;
    QByteArray observedSpotBalanceRequest;
    QByteArray observedSpotOrderRequest;
    QByteArray observedSpotTradesRequest;
    QObject::connect(&spotServer, &QTcpServer::newConnection,
                     [&spotServer, &observedSpotExchangeInfoRequest, &observedSpotBalanceRequest,
                      &observedSpotOrderRequest, &observedSpotTradesRequest]() {
        QTcpSocket *socket = spotServer.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead,
                         [socket, &observedSpotExchangeInfoRequest, &observedSpotBalanceRequest,
                          &observedSpotOrderRequest, &observedSpotTradesRequest]() {
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
            } else if (requestLine.startsWith("GET /api/v3/myTrades?")) {
                observedSpotTradesRequest = requestLine;
                writeJsonResponseAndClose(
                    socket,
                    R"([{"symbol":"ETHUSDT","id":7,"orderId":42,"price":"2000","qty":"0.25","quoteQty":"500","commission":"0.001","commissionAsset":"ETH","isBuyer":true,"isMaker":false,"isBestMatch":true,"time":1700000000000}])");
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
    const auto usdtBalance = BinanceRestClient::fetchSpotBalance(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("usdt"),
        false,
        5000,
        spotBaseUrl);
    const auto missingSpotBalance = BinanceRestClient::fetchSpotBalance(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("ADA"),
        false,
        5000,
        spotBaseUrl);
    const auto nonUsdtBalances = BinanceRestClient::fetchSpotNonUsdtBalances(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        false,
        5000,
        spotBaseUrl);
    check(usdtBalance.ok && std::abs(usdtBalance.free - 100.0) < 1e-12
              && std::abs(usdtBalance.total - 100.0) < 1e-12
              && missingSpotBalance.ok && std::abs(missingSpotBalance.free) < 1e-12
              && nonUsdtBalances.ok && nonUsdtBalances.balances.size() == 1
              && nonUsdtBalances.balances.first().asset == QStringLiteral("ETH"),
          QStringLiteral("C++ Spot balance helpers should match Python selection and non-USDT filtering"));
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
    check(spotFilters.quoteAssetPrecision == 8,
          QStringLiteral("C++ Spot filters should preserve Python quote-asset precision"));
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

    const auto spotTrades = BinanceRestClient::fetchSpotTrades(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("ethusdt"),
        1000,
        false,
        5000,
        spotBaseUrl);
    check(spotTrades.ok && spotTrades.trades.size() == 1
              && spotTrades.trades.first().orderId == QStringLiteral("42")
              && std::abs(spotTrades.trades.first().quantity - 0.25) < 1e-12
              && std::abs(spotTrades.trades.first().quoteQuantity - 500.0) < 1e-12
              && spotTrades.trades.first().isBuyer,
          QStringLiteral("C++ Spot trade history should preserve Python cost-basis fields"));
    check(observedSpotTradesRequest.startsWith("GET /api/v3/myTrades?")
              && observedSpotTradesRequest.contains("symbol=ETHUSDT")
              && observedSpotTradesRequest.contains("limit=1000"),
          QStringLiteral("C++ Spot trade history should use the signed myTrades request"));

    const auto spotPositionCost = BinanceRestClient::fetchSpotPositionCost(
        QStringLiteral("key"),
        QStringLiteral("secret"),
        QStringLiteral("ethusdt"),
        1000,
        false,
        5000,
        spotBaseUrl);
    check(spotPositionCost.ok && spotPositionCost.hasPosition
              && std::abs(spotPositionCost.quantity - 0.25) < 1e-12
              && std::abs(spotPositionCost.cost - 500.0) < 1e-12,
          QStringLiteral("C++ Spot cost basis should aggregate Python buyer trades"));

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
            const bool shortPage = query.queryItemValue(QStringLiteral("symbol")) == QStringLiteral("SHORTUSDT");
            observedKlineStarts.append(startTime);
            observedKlineIntervals.append(query.queryItemValue(QStringLiteral("interval")));

            QJsonArray candles;
            constexpr qint64 intervalMs = 60'000;
            for (qint64 openTime = startTime;
                 openTime <= endTime && candles.size() < (shortPage ? 1 : std::max(1, limit));
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

    const BinanceRestClient::KlinesResult shortPageKlines = BinanceRestClient::fetchKlinesRange(
        QStringLiteral("SHORTUSDT"),
        QStringLiteral("1m"),
        false,
        false,
        pageStart,
        pageStart + 3 * minuteMs,
        100,
        5'000,
        klineBaseUrl);
    check(shortPageKlines.ok && shortPageKlines.candles.size() == 3,
          QStringLiteral("native historical loader should continue after a short non-empty page"));

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

    const BinanceRestClient::KlinesResult fractionalCustomKlines = BinanceRestClient::fetchKlinesRange(
        QStringLiteral("ETHUSDT"),
        QStringLiteral("0.5h"),
        false,
        false,
        customStart,
        customStart + 61 * minuteMs,
        100,
        5'000,
        klineBaseUrl);
    check(fractionalCustomKlines.ok && fractionalCustomKlines.candles.size() == 2,
          QStringLiteral("native historical loader should accept Python-compatible fractional hour intervals"));
    check(fractionalCustomKlines.ok
              && std::abs(fractionalCustomKlines.candles.constFirst().volume - 30.0) < 1e-12,
          QStringLiteral("fractional custom interval aggregation should preserve Python candle volume"));
    check(observedKlineIntervals.constLast() == QStringLiteral("1m"),
          QStringLiteral("fractional custom interval aggregation should fetch the one-minute base"));

    const BinanceRestClient::KlinesResult pythonMonthAliasKlines = BinanceRestClient::fetchKlinesRange(
        QStringLiteral("ETHUSDT"),
        QStringLiteral("1mo"),
        false,
        false,
        customStart,
        customStart + 13 * minuteMs,
        100,
        5'000,
        klineBaseUrl);
    check(pythonMonthAliasKlines.ok && pythonMonthAliasKlines.candles.size() == 14,
          QStringLiteral("native historical loader should preserve Python one-minute fallback for month aliases"));
    check(observedKlineIntervals.constLast() == QStringLiteral("1m"),
          QStringLiteral("Python month aliases should request the one-minute base interval"));

    const BinanceRestClient::KlinesResult directCustomKlines = BinanceRestClient::fetchKlines(
        QStringLiteral("ETHUSDT"),
        QStringLiteral("7m"),
        false,
        false,
        2,
        5'000,
        klineBaseUrl);
    check(directCustomKlines.ok && directCustomKlines.candles.size() == 2,
          QStringLiteral("native direct kline loading should aggregate Python custom intervals"));
    check(observedKlineIntervals.constLast() == QStringLiteral("1m"),
          QStringLiteral("native direct custom loading should request the supported one-minute base"));

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
