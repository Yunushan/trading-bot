#include "../src/NativeBacktestRuntime.h"
#include "../src/NativeBacktestBatchRuntime.h"
#include "../src/NativeChartHeatmap.h"
#include "../src/NativeConfigPersistence.h"
#include "../src/NativeDesktopShell.h"
#include "../src/NativeDiagnostics.h"
#include "../src/NativeExchangeConnectors.h"
#include "../src/NativeIndicatorRuntime.h"
#include "../src/NativeLlmAdvisory.h"
#include "../src/NativePythonParityChoices.h"
#include "../src/NativeOrderSafety.h"
#include "../src/NativePortfolio.h"
#include "../src/NativeStartupPackaging.h"
#include "../src/NativeStrategyRuntime.h"
#include "../src/TradingBotWindowSupport.h"
#include "../src/generated/PythonExchangeSupportReference.h"
#include "../src/generated/PythonIndicatorReference.h"
#include "../src/generated/PythonParityContract.h"
#include "../src/generated/PythonPortfolioReference.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QTextStream>
#include <QThread>

#include <iostream>
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace {

QString readText(const QString &path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return {};
    }
    return QString::fromUtf8(file.readAll());
}

bool jsonArrayContains(const QJsonArray &array, const QString &expected) {
    for (const QJsonValue &value : array) {
        if (value.toString() == expected) {
            return true;
        }
    }
    return false;
}

NativeExchangeConnectors::ExchangeSupportInput exchangeSupportInputFromJson(const QJsonValue &value) {
    const QJsonObject object = value.toObject();
    return {
        object.value(QStringLiteral("selected_exchange")).toString(),
        object.value(QStringLiteral("connector_backend")).toString(),
        object.value(QStringLiteral("selected_forex_broker")).toString(),
    };
}

QVector<QPair<QString, QString>> orderParamsFromJson(const QJsonObject &params) {
    QVector<QPair<QString, QString>> result;
    for (const QString &key : params.keys()) {
        result.append({key, params.value(key).toString()});
    }
    return result;
}

QStringList stringListFromJson(const QJsonValue &value) {
    QStringList result;
    for (const QJsonValue &item : value.toArray()) {
        result.append(item.toString());
    }
    return result;
}

QJsonObject orderIntentToJson(const NativeOrderSafety::OrderSubmitIntent &intent) {
    return {
        {QStringLiteral("market"), intent.market},
        {QStringLiteral("symbol"), intent.symbol},
        {QStringLiteral("side"), intent.side},
        {QStringLiteral("order_type"), intent.orderType},
        {QStringLiteral("quantity"), intent.hasQuantity
                ? QJsonValue(intent.quantity)
                : QJsonValue(QJsonValue::Null)},
        {QStringLiteral("price"), intent.hasPrice
                ? QJsonValue(intent.price)
                : QJsonValue(QJsonValue::Null)},
        {QStringLiteral("position_side"), intent.positionSide},
        {QStringLiteral("close_position"), intent.closePosition},
        {QStringLiteral("reduce_only"), intent.reduceOnly},
    };
}

NativeOrderSafety::OrderSymbolFilters orderFiltersFromJson(const QJsonObject &filters) {
    return {
        filters.value(QStringLiteral("stepSize")).toDouble(),
        filters.value(QStringLiteral("tickSize")).toDouble(),
        filters.value(QStringLiteral("minQty")).toDouble(),
        filters.value(QStringLiteral("minNotional")).toDouble(),
    };
}

NativeOrderSafety::LiveOrderGuardInput liveSafetyInputFromJson(const QJsonObject &input) {
    NativeOrderSafety::LiveOrderGuardInput result;
    const QJsonObject config = input.value(QStringLiteral("config")).toObject();
    result.mode = input.value(QStringLiteral("mode")).toString();
    result.apiKey = input.value(QStringLiteral("api_key")).toString();
    result.apiSecret = input.value(QStringLiteral("api_secret")).toString();
    result.accountType = input.value(QStringLiteral("account_type")).toString();
    result.leverage = input.value(QStringLiteral("leverage")).toInt(result.leverage);
    result.marginMode = input.value(QStringLiteral("margin_mode")).toString();
    result.positionPct = input.value(QStringLiteral("position_pct")).toDouble(result.positionPct);
    result.config.liveTradingEnabled = config.value(QStringLiteral("live_trading_enabled"))
                                           .toBool(result.config.liveTradingEnabled);
    result.config.liveTradingAcknowledgement = config.value(QStringLiteral("live_trading_acknowledgement"))
                                                   .toString(result.config.liveTradingAcknowledgement);
    result.config.liveTradingMaxLeverage = config.value(QStringLiteral("live_trading_max_leverage"))
                                               .toInt(result.config.liveTradingMaxLeverage);
    result.config.liveTradingMaxPositionPct = config.value(QStringLiteral("live_trading_max_position_pct"))
                                                  .toDouble(result.config.liveTradingMaxPositionPct);
    result.config.liveTradingMaxSessionOrders = config.value(QStringLiteral("live_trading_max_session_orders"))
                                                   .toInt(result.config.liveTradingMaxSessionOrders);
    return result;
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

    std::size_t pythonUiOptionEntryCount = 0;
    for (const auto &catalog : PythonParityContract::kPythonUiOptionCatalogs) {
        pythonUiOptionEntryCount += catalog.size;
    }
    check(PythonParityContract::kPythonOptionCatalogCount == 44,
          QStringLiteral("generated native contract must contain every Python option catalog"));
    check(PythonParityContract::kPythonOptionCatalogEntryCount == 255,
          QStringLiteral("generated native contract must contain every Python option entry"));
    check(PythonParityContract::kPythonUiOptionCatalogCount
              == PythonParityContract::kPythonUiOptionCatalogs.size(),
          QStringLiteral("generated UI catalog count must match the native catalog projection"));
    check(PythonParityContract::kPythonUiOptionEntryCount == pythonUiOptionEntryCount,
          QStringLiteral("generated UI entry count must match the native catalog projection"));

    for (const auto &referenceCase : PythonParityContract::kPythonStrategyControlsReferenceCases) {
        const QString caseName = QString::fromUtf8(
            referenceCase.name.data(),
            static_cast<qsizetype>(referenceCase.name.size()));
        const QByteArray inputJson(
            referenceCase.inputJson.data(),
            static_cast<qsizetype>(referenceCase.inputJson.size()));
        const QByteArray expectedJson(
            referenceCase.expectedJson.data(),
            static_cast<qsizetype>(referenceCase.expectedJson.size()));
        QJsonParseError inputError;
        const QJsonDocument inputDocument = QJsonDocument::fromJson(inputJson, &inputError);
        check(!inputDocument.isNull() && inputDocument.isObject(),
              QStringLiteral("generated Python strategy-control input should parse: %1 (%2)")
                  .arg(caseName, inputError.errorString()));
        if (inputDocument.isNull() || !inputDocument.isObject()) {
            continue;
        }
        QJsonParseError expectedError;
        const QJsonDocument expectedDocument = QJsonDocument::fromJson(expectedJson, &expectedError);
        check(!expectedDocument.isNull() && expectedDocument.isObject(),
              QStringLiteral("generated Python strategy-control expected output should parse: %1 (%2)")
                  .arg(caseName, expectedError.errorString()));
        if (expectedDocument.isNull() || !expectedDocument.isObject()) {
            continue;
        }
        const QString kind = QString::fromUtf8(
            referenceCase.kind.data(),
            static_cast<qsizetype>(referenceCase.kind.size()));
        check(
            NativeStrategyRuntime::normalizeStrategyControls(kind, inputDocument.object())
                == expectedDocument.object(),
            QStringLiteral("C++ strategy-control normalization should match Python: %1")
                .arg(caseName));
    }

    for (const auto &referenceCase : PythonParityContract::kPythonStrategyRiskReferenceCases) {
        const QString caseName = QString::fromUtf8(
            referenceCase.name.data(),
            static_cast<qsizetype>(referenceCase.name.size()));
        const QByteArray inputJson(
            referenceCase.inputJson.data(),
            static_cast<qsizetype>(referenceCase.inputJson.size()));
        const QByteArray expectedJson(
            referenceCase.expectedJson.data(),
            static_cast<qsizetype>(referenceCase.expectedJson.size()));
        QJsonParseError inputError;
        const QJsonDocument inputDocument = QJsonDocument::fromJson(inputJson, &inputError);
        check(!inputDocument.isNull() && inputDocument.isObject(),
              QStringLiteral("generated Python strategy-risk input should parse: %1 (%2)")
                  .arg(caseName, inputError.errorString()));
        if (inputDocument.isNull() || !inputDocument.isObject()) {
            continue;
        }
        QJsonParseError expectedError;
        const QJsonDocument expectedDocument = QJsonDocument::fromJson(expectedJson, &expectedError);
        check(!expectedDocument.isNull() && expectedDocument.isObject(),
              QStringLiteral("generated Python strategy-risk expected output should parse: %1 (%2)")
                  .arg(caseName, expectedError.errorString()));
        if (expectedDocument.isNull() || !expectedDocument.isObject()) {
            continue;
        }
        check(
            NativeStrategyRuntime::normalizeStrategyRiskControls(inputDocument.object())
                == expectedDocument.object(),
            QStringLiteral("C++ strategy-risk normalization should match Python: %1")
                .arg(caseName));
    }

    for (const auto &referenceCase : PythonParityContract::kPythonStrategyRiskLooseReferenceCases) {
        const QString caseName = QString::fromUtf8(
            referenceCase.name.data(),
            static_cast<qsizetype>(referenceCase.name.size()));
        const QByteArray inputJson(
            referenceCase.inputJson.data(),
            static_cast<qsizetype>(referenceCase.inputJson.size()));
        const QByteArray expectedJson(
            referenceCase.expectedJson.data(),
            static_cast<qsizetype>(referenceCase.expectedJson.size()));
        QJsonParseError inputError;
        const QJsonDocument inputDocument = QJsonDocument::fromJson(inputJson, &inputError);
        check(!inputDocument.isNull() && inputDocument.isObject(),
              QStringLiteral("generated Python loose strategy-risk input should parse: %1 (%2)")
                  .arg(caseName, inputError.errorString()));
        if (inputDocument.isNull() || !inputDocument.isObject()) {
            continue;
        }
        QJsonParseError expectedError;
        const QJsonDocument expectedDocument = QJsonDocument::fromJson(expectedJson, &expectedError);
        check(!expectedDocument.isNull() && expectedDocument.isObject(),
              QStringLiteral("generated Python loose strategy-risk expected output should parse: %1 (%2)")
                  .arg(caseName, expectedError.errorString()));
        if (expectedDocument.isNull() || !expectedDocument.isObject()) {
            continue;
        }
        check(
            NativeStrategyRuntime::normalizeStrategyRiskControls(inputDocument.object())
                == expectedDocument.object(),
            QStringLiteral("C++ loose strategy-risk normalization should match Python: %1")
                .arg(caseName));
    }

    const QByteArray intervalSecondsReferenceJson(
        PythonParityContract::kPythonIntervalSecondsReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonIntervalSecondsReferenceJson.size()));
    QJsonParseError intervalSecondsParseError;
    const QJsonDocument intervalSecondsDocument = QJsonDocument::fromJson(
        intervalSecondsReferenceJson,
        &intervalSecondsParseError);
    check(intervalSecondsParseError.error == QJsonParseError::NoError
              && intervalSecondsDocument.isArray(),
          QStringLiteral("generated Python interval timing reference should be valid JSON: %1")
              .arg(intervalSecondsParseError.errorString()));
    if (intervalSecondsDocument.isArray()) {
        for (const QJsonValue &caseValue : intervalSecondsDocument.array()) {
            const QJsonObject referenceCase = caseValue.toObject();
            const QString caseName = referenceCase.value(QStringLiteral("input")).toString();
            const QString input = caseName;
            check(qFuzzyCompare(
                      NativeStrategyRuntime::pythonIndicatorIntervalSeconds(input) + 1.0,
                      referenceCase.value(QStringLiteral("indicator_seconds")).toDouble() + 1.0),
                  QStringLiteral("C++ indicator interval timing should match Python: %1").arg(caseName));
            check(qFuzzyCompare(
                      NativeStrategyRuntime::pythonLoopIntervalSeconds(input) + 1.0,
                      referenceCase.value(QStringLiteral("loop_seconds")).toDouble() + 1.0),
                  QStringLiteral("C++ loop interval timing should match Python: %1").arg(caseName));
        }
    }

    const QByteArray backtestIntervalSecondsReferenceJson(
        PythonParityContract::kPythonBacktestIntervalSecondsReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonBacktestIntervalSecondsReferenceJson.size()));
    QJsonParseError backtestIntervalSecondsParseError;
    const QJsonDocument backtestIntervalSecondsDocument = QJsonDocument::fromJson(
        backtestIntervalSecondsReferenceJson,
        &backtestIntervalSecondsParseError);
    check(backtestIntervalSecondsParseError.error == QJsonParseError::NoError
              && backtestIntervalSecondsDocument.isArray(),
          QStringLiteral("generated Python backtest interval timing reference should be valid JSON: %1")
              .arg(backtestIntervalSecondsParseError.errorString()));
    if (backtestIntervalSecondsDocument.isArray()) {
        constexpr qint64 startTimeMs = 1'000'000'000;
        for (const QJsonValue &caseValue : backtestIntervalSecondsDocument.array()) {
            const QJsonObject referenceCase = caseValue.toObject();
            const QString input = referenceCase.value(QStringLiteral("input")).toString();
            const double expectedSeconds = referenceCase.value(QStringLiteral("seconds")).toDouble();
            const qint64 expectedDeltaMs = static_cast<qint64>(expectedSeconds * 2.0 * 1000.0);
            const qint64 expectedStartTimeMs = startTimeMs > expectedDeltaMs
                ? startTimeMs - expectedDeltaMs
                : 1;
            check(
                NativeBacktestBatchRuntime::bufferedStartTimeMs(startTimeMs, input, 1)
                    == expectedStartTimeMs,
                QStringLiteral("C++ backtest interval timing should match Python: %1").arg(input));
        }
    }

    const QByteArray orderIntentReferenceJson(
        PythonParityContract::kPythonOrderIntentReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonOrderIntentReferenceJson.size()));
    QJsonParseError orderIntentParseError;
    const QJsonDocument orderIntentDocument = QJsonDocument::fromJson(
        orderIntentReferenceJson,
        &orderIntentParseError);
    check(orderIntentParseError.error == QJsonParseError::NoError
              && orderIntentDocument.isObject(),
          QStringLiteral("generated Python order-intent reference should be valid JSON: %1")
              .arg(orderIntentParseError.errorString()));
    if (orderIntentDocument.isObject()) {
        for (const QJsonValue &caseValue : orderIntentDocument.object().value(QStringLiteral("cases")).toArray()) {
            const QJsonObject referenceCase = caseValue.toObject();
            const QString caseName = referenceCase.value(QStringLiteral("name")).toString();
            const QString market = referenceCase.value(QStringLiteral("market")).toString();
            const QVector<QPair<QString, QString>> params = orderParamsFromJson(
                referenceCase.value(QStringLiteral("params")).toObject());
            const NativeOrderSafety::OrderSubmitIntent intent =
                NativeOrderSafety::orderSubmitIntentFromParams(market, params);
            const QJsonObject expected = referenceCase.value(QStringLiteral("expected")).toObject();
            check(
                orderIntentToJson(intent) == expected.value(QStringLiteral("intent")).toObject(),
                QStringLiteral("C++ order-intent normalization should match Python: %1")
                    .arg(caseName));
            check(
                NativeOrderSafety::validateOrderSubmitIntent(intent)
                    == stringListFromJson(expected.value(QStringLiteral("intent_errors"))),
                QStringLiteral("C++ order-intent validation should match Python: %1")
                    .arg(caseName));
            const QJsonObject filterObject = referenceCase.value(QStringLiteral("filters")).toObject();
            const QJsonValue lastPriceValue = referenceCase.value(QStringLiteral("last_price"));
            const QStringList filterErrors = NativeOrderSafety::validateOrderFilterConstraintsWithRawParams(
                intent,
                orderFiltersFromJson(filterObject),
                lastPriceValue.isDouble(),
                lastPriceValue.toDouble(),
                params);
            check(
                filterErrors == stringListFromJson(expected.value(QStringLiteral("filter_errors"))),
                QStringLiteral("C++ order-filter validation should match Python: %1")
                    .arg(caseName));
        }
    }

    const QByteArray liveSafetyReferenceJson(
        PythonParityContract::kPythonLiveSafetyReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonLiveSafetyReferenceJson.size()));
    QJsonParseError liveSafetyParseError;
    const QJsonDocument liveSafetyDocument = QJsonDocument::fromJson(
        liveSafetyReferenceJson,
        &liveSafetyParseError);
    check(liveSafetyParseError.error == QJsonParseError::NoError
              && liveSafetyDocument.isObject(),
          QStringLiteral("generated Python live-safety reference should be valid JSON: %1")
              .arg(liveSafetyParseError.errorString()));
    if (liveSafetyDocument.isObject()) {
        struct SavedEnvironmentValue {
            QByteArray name;
            bool wasSet = false;
            QByteArray value;
        };
        const QVector<QByteArray> environmentNames = {
            QByteArray("BOT_ENABLE_LIVE_TRADING"),
            QByteArray("BOT_LIVE_TRADING_ACKNOWLEDGEMENT"),
            QByteArray("BOT_LIVE_TRADING_ACK"),
            QByteArray("BOT_LIVE_MAX_LEVERAGE"),
            QByteArray("BOT_LIVE_MAX_POSITION_PCT"),
            QByteArray("BOT_LIVE_MAX_SESSION_ORDERS"),
        };
        QVector<SavedEnvironmentValue> savedEnvironment;
        savedEnvironment.reserve(environmentNames.size());
        for (const QByteArray &name : environmentNames) {
            savedEnvironment.push_back({name, qEnvironmentVariableIsSet(name.constData()), qgetenv(name.constData())});
            qunsetenv(name.constData());
        }

        for (const QJsonValue &caseValue : liveSafetyDocument.object().value(QStringLiteral("cases")).toArray()) {
            const QJsonObject referenceCase = caseValue.toObject();
            const QString caseName = referenceCase.value(QStringLiteral("name")).toString();
            const QStringList expectedErrors = stringListFromJson(
                referenceCase.value(QStringLiteral("expected_errors")));
            check(
                NativeOrderSafety::validateLiveTradingSafety(
                    liveSafetyInputFromJson(referenceCase.value(QStringLiteral("input")).toObject()))
                    == expectedErrors,
                QStringLiteral("C++ live-safety validation should match Python: %1").arg(caseName));
        }

        for (const SavedEnvironmentValue &saved : savedEnvironment) {
            if (saved.wasSet) {
                qputenv(saved.name.constData(), saved.value);
            } else {
                qunsetenv(saved.name.constData());
            }
        }
    }

    const QByteArray connectorHealthReferenceJson(
        PythonParityContract::kPythonConnectorHealthReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonConnectorHealthReferenceJson.size()));
    QJsonParseError connectorHealthParseError;
    const QJsonDocument connectorHealthDocument = QJsonDocument::fromJson(
        connectorHealthReferenceJson,
        &connectorHealthParseError);
    check(connectorHealthParseError.error == QJsonParseError::NoError
              && connectorHealthDocument.isObject(),
          QStringLiteral("generated Python connector-health reference should be valid JSON: %1")
              .arg(connectorHealthParseError.errorString()));
    if (connectorHealthDocument.isObject()) {
        for (const QJsonValue &caseValue : connectorHealthDocument.object().value(QStringLiteral("cases")).toArray()) {
            const QJsonObject referenceCase = caseValue.toObject();
            const QString caseName = referenceCase.value(QStringLiteral("name")).toString();
            const QJsonObject snapshot = referenceCase.value(QStringLiteral("snapshot")).toObject();
            check(
                NativeOrderSafety::validateConnectorHealthErrors(
                    snapshot.value(QStringLiteral("state")).toString(),
                    snapshot.value(QStringLiteral("health")).toString())
                    == stringListFromJson(referenceCase.value(QStringLiteral("expected_errors"))),
                QStringLiteral("C++ connector-health validation should match Python: %1")
                    .arg(caseName));
        }
    }

    QTemporaryDir dir;
    check(dir.isValid(), QStringLiteral("temporary directory should be valid"));
    if (!dir.isValid()) {
        return 1;
    }

    const QString pythonOrderGuardBehavior = QString::fromUtf8(
        PythonParityContract::kPythonOrderGuardBehaviorJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonOrderGuardBehaviorJson.size()));
    check(PythonParityContract::kPythonOrderGuardValidateIntentAllModes,
          QStringLiteral("generated Python contract should validate order intent in every mode"));
    check(PythonParityContract::kPythonOrderGuardValidateExchangeFiltersAllModes,
          QStringLiteral("generated Python contract should validate exchange filters in every mode"));
    check(PythonParityContract::kPythonOrderGuardValidateConnectorHealthAllModes,
          QStringLiteral("generated Python contract should validate connector health in every mode"));
    check(PythonParityContract::kPythonOrderGuardValidateAuditEnabledAllModes,
          QStringLiteral("generated Python contract should require enabled audit in every mode"));
    check(PythonParityContract::kPythonOrderGuardValidateAuditWritableAllModes,
          QStringLiteral("generated Python contract should require writable audit in every mode"));
    check(pythonOrderGuardBehavior.contains(QStringLiteral("\"validate_exchange_filters_all_modes\":true")),
          QStringLiteral("generated Python contract should require exchange filter validation in paper mode"));
    check(pythonOrderGuardBehavior.contains(QStringLiteral("session_order_count_increment")),
          QStringLiteral("generated Python contract should identify live-only session accounting"));

    const QString indicatorReferenceHash = QString::fromUtf8(
        PythonIndicatorReference::kPythonSourceContractHash.data(),
        static_cast<qsizetype>(PythonIndicatorReference::kPythonSourceContractHash.size()));
    const QString parityContractHash = QString::fromUtf8(
        PythonParityContract::kPythonSourceContractHash.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonSourceContractHash.size()));
    check(indicatorReferenceHash == parityContractHash,
          QStringLiteral("generated C++ indicator reference should match the Python source contract hash"));

    const QByteArray indicatorReferenceJson(
        PythonIndicatorReference::kReferenceJson.data(),
        static_cast<qsizetype>(PythonIndicatorReference::kReferenceJson.size()));
    QJsonParseError indicatorReferenceParseError;
    const QJsonDocument indicatorReferenceDocument = QJsonDocument::fromJson(
        indicatorReferenceJson,
        &indicatorReferenceParseError);
    check(indicatorReferenceParseError.error == QJsonParseError::NoError
              && indicatorReferenceDocument.isObject(),
          QStringLiteral("generated C++ indicator reference should contain valid JSON"));
    const QJsonObject indicatorReference = indicatorReferenceDocument.object();
    check(indicatorReference.value(QStringLiteral("python_source_contract_hash")).toString()
              == parityContractHash,
          QStringLiteral("indicator fixture payload should identify the active Python source contract"));

    const QString exchangeSupportReferenceHash = QString::fromUtf8(
        PythonExchangeSupportReference::kPythonSourceContractHash.data(),
        static_cast<qsizetype>(PythonExchangeSupportReference::kPythonSourceContractHash.size()));
    check(exchangeSupportReferenceHash == parityContractHash,
          QStringLiteral("generated C++ exchange support reference should match the Python source contract hash"));
    const QByteArray exchangeSupportReferenceJson(
        PythonExchangeSupportReference::kReferenceJson.data(),
        static_cast<qsizetype>(PythonExchangeSupportReference::kReferenceJson.size()));
    QJsonParseError exchangeSupportReferenceParseError;
    const QJsonDocument exchangeSupportReferenceDocument = QJsonDocument::fromJson(
        exchangeSupportReferenceJson,
        &exchangeSupportReferenceParseError);
    check(exchangeSupportReferenceParseError.error == QJsonParseError::NoError
              && exchangeSupportReferenceDocument.isObject(),
          QStringLiteral("generated C++ exchange support reference should contain valid JSON"));
    const QJsonObject exchangeSupportReference = exchangeSupportReferenceDocument.object();
    check(exchangeSupportReference.value(QStringLiteral("python_source_contract_hash")).toString()
              == parityContractHash,
          QStringLiteral("exchange support fixture should identify the active Python source contract"));
    const QJsonArray exchangeSupportCases = exchangeSupportReference
        .value(QStringLiteral("exchange_support_cases"))
        .toArray();
    check(exchangeSupportCases.size() >= 60,
          QStringLiteral("generated Python exchange support reference should include the complete matrix"));
    for (qsizetype caseIndex = 0; caseIndex < exchangeSupportCases.size(); ++caseIndex) {
        const QJsonObject exchangeSupportCase = exchangeSupportCases.at(caseIndex).toObject();
        const QString caseName = exchangeSupportCase.value(QStringLiteral("name")).toString(
            QStringLiteral("exchange-support-fixture-%1").arg(caseIndex));
        const NativeExchangeConnectors::ExchangeSupportInput config = exchangeSupportInputFromJson(
            exchangeSupportCase.value(QStringLiteral("config")));
        const QJsonValue snapshotValue = exchangeSupportCase.value(QStringLiteral("snapshot"));
        const NativeExchangeConnectors::ExchangeSupportInput snapshot = exchangeSupportInputFromJson(snapshotValue);
        const QJsonObject actual = NativeExchangeConnectors::buildExchangeSupportPayload(
            config,
            snapshotValue.isNull() ? NativeExchangeConnectors::ExchangeSupportInput{} : snapshot);
        const QJsonObject expected = exchangeSupportCase.value(QStringLiteral("expected")).toObject();
        check(actual == expected,
              QStringLiteral("native C++ exchange support payload should exactly match Python case %1").arg(caseName));
    }

    const QString portfolioReferenceHash = QString::fromUtf8(
        PythonPortfolioReference::kPythonSourceContractHash.data(),
        static_cast<qsizetype>(PythonPortfolioReference::kPythonSourceContractHash.size()));
    check(portfolioReferenceHash == parityContractHash,
          QStringLiteral("generated C++ portfolio reference should match the Python source contract hash"));
    const QByteArray portfolioReferenceJson(
        PythonPortfolioReference::kReferenceJson.data(),
        static_cast<qsizetype>(PythonPortfolioReference::kReferenceJson.size()));
    QJsonParseError portfolioReferenceParseError;
    const QJsonDocument portfolioReferenceDocument = QJsonDocument::fromJson(
        portfolioReferenceJson,
        &portfolioReferenceParseError);
    check(portfolioReferenceParseError.error == QJsonParseError::NoError
              && portfolioReferenceDocument.isObject(),
          QStringLiteral("generated C++ portfolio reference should contain valid JSON"));
    const QJsonObject portfolioReference = portfolioReferenceDocument.object();
    check(portfolioReference.value(QStringLiteral("python_source_contract_hash")).toString()
              == parityContractHash,
          QStringLiteral("portfolio fixture should identify the active Python source contract"));
    const QJsonArray portfolioCases = portfolioReference
        .value(QStringLiteral("position_reconciliation_cases"))
        .toArray();
    check(portfolioCases.size() >= 5,
          QStringLiteral("generated Python portfolio reference should cover the missing-position policy paths"));
    for (qsizetype caseIndex = 0; caseIndex < portfolioCases.size(); ++caseIndex) {
        const QJsonObject portfolioCase = portfolioCases.at(caseIndex).toObject();
        const QString caseName = portfolioCase.value(QStringLiteral("name")).toString(
            QStringLiteral("portfolio-fixture-%1").arg(caseIndex));
        const QJsonObject initialState = portfolioCase.value(QStringLiteral("initial_state")).toObject();
        QJsonObject openRecords = initialState.value(QStringLiteral("open_position_records")).toObject();
        QJsonObject entryAllocations = initialState.value(QStringLiteral("entry_allocations")).toObject();
        QJsonArray closedRecords = initialState.value(QStringLiteral("closed_position_records")).toArray();
        QJsonObject missingCounts = initialState.value(QStringLiteral("missing_counts")).toObject();
        QJsonObject pendingCloseTimes = initialState.value(QStringLiteral("pending_close_times")).toObject();
        const QJsonArray steps = portfolioCase.value(QStringLiteral("steps")).toArray();
        const QJsonArray expectedSteps = portfolioCase.value(QStringLiteral("expected_steps")).toArray();
        check(steps.size() == expectedSteps.size(),
              QStringLiteral("Python portfolio fixture should provide one expected state per step for %1")
                  .arg(caseName));
        const qsizetype stepCount = std::min(steps.size(), expectedSteps.size());
        for (qsizetype stepIndex = 0; stepIndex < stepCount; ++stepIndex) {
            const QJsonObject step = steps.at(stepIndex).toObject();
            const QJsonObject policy = step.value(QStringLiteral("policy")).toObject();
            const QJsonObject actualSummary = NativePortfolio::reconcileMissingPositionState(
                openRecords,
                entryAllocations,
                closedRecords,
                missingCounts,
                pendingCloseTimes,
                step.value(QStringLiteral("live_position_records")).toObject(),
                policy,
                step.value(QStringLiteral("close_time")).toString(),
                step.value(QStringLiteral("max_history")).toInt(500));
            const QJsonObject expectedStep = expectedSteps.at(stepIndex).toObject();
            const QJsonObject expectedSummary = expectedStep.value(QStringLiteral("summary")).toObject();
            for (const QString &summaryKey : {QStringLiteral("closed_keys"),
                                               QStringLiteral("dropped_keys"),
                                               QStringLiteral("waiting_keys"),
                                               QStringLiteral("live_keys")}) {
                check(actualSummary.value(summaryKey).toArray()
                          == expectedSummary.value(summaryKey).toArray(),
                      QStringLiteral("native C++ portfolio summary diverged from Python for %1 step %2/%3")
                          .arg(caseName, QString::number(stepIndex), summaryKey));
            }
            check(actualSummary.value(QStringLiteral("closed_count")).toInt()
                      == expectedSummary.value(QStringLiteral("closed_keys")).toArray().size(),
                  QStringLiteral("native C++ portfolio closed count diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            check(actualSummary.value(QStringLiteral("dropped_count")).toInt()
                      == expectedSummary.value(QStringLiteral("dropped_keys")).toArray().size(),
                  QStringLiteral("native C++ portfolio dropped count diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            check(actualSummary.value(QStringLiteral("waiting_count")).toInt()
                      == expectedSummary.value(QStringLiteral("waiting_keys")).toArray().size(),
                  QStringLiteral("native C++ portfolio waiting count diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            const QJsonObject expectedState = expectedStep.value(QStringLiteral("state")).toObject();
            check(openRecords == expectedState.value(QStringLiteral("open_position_records")).toObject(),
                  QStringLiteral("native C++ open portfolio state diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            check(entryAllocations == expectedState.value(QStringLiteral("entry_allocations")).toObject(),
                  QStringLiteral("native C++ allocation state diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            check(closedRecords == expectedState.value(QStringLiteral("closed_position_records")).toArray(),
                  QStringLiteral("native C++ closed portfolio history diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            check(missingCounts == expectedState.value(QStringLiteral("missing_counts")).toObject(),
                  QStringLiteral("native C++ missing-count state diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
            check(pendingCloseTimes == expectedState.value(QStringLiteral("pending_close_times")).toObject(),
                  QStringLiteral("native C++ pending-close state diverged from Python for %1 step %2")
                      .arg(caseName).arg(stepIndex));
        }
    }

    QJsonArray indicatorCases = indicatorReference.value(QStringLiteral("indicator_cases")).toArray();
    if (indicatorCases.isEmpty()) {
        // Keep older generated fixtures readable while requiring the current generator to emit cases.
        indicatorCases.append(indicatorReference);
    }
    check(indicatorCases.size() >= 7,
          QStringLiteral("generated Python indicator reference should include normal, edge, and coercion scenarios"));

    QVector<NativeIndicatorRuntime::Candle> indicatorCandles;
    NativeIndicatorRuntime::ConfigMap indicatorConfigs;
    for (qsizetype caseIndex = 0; caseIndex < indicatorCases.size(); ++caseIndex) {
        const QJsonObject indicatorCase = indicatorCases.at(caseIndex).toObject();
        const QString caseName = indicatorCase.value(QStringLiteral("name")).toString(
            QStringLiteral("fixture-%1").arg(caseIndex));
        QVector<NativeIndicatorRuntime::Candle> caseCandles;
        const QJsonArray indicatorCandleValues = indicatorCase.value(QStringLiteral("candles")).toArray();
        caseCandles.reserve(indicatorCandleValues.size());
        for (const QJsonValue &value : indicatorCandleValues) {
            const QJsonObject candle = value.toObject();
            caseCandles.push_back({
                candle.value(QStringLiteral("open")).toDouble(),
                candle.value(QStringLiteral("high")).toDouble(),
                candle.value(QStringLiteral("low")).toDouble(),
                candle.value(QStringLiteral("close")).toDouble(),
                candle.value(QStringLiteral("volume")).toDouble(),
            });
        }
        NativeIndicatorRuntime::ConfigMap caseConfigs;
        const QJsonObject indicatorConfigValues = indicatorCase.value(QStringLiteral("configs")).toObject();
        for (auto iterator = indicatorConfigValues.constBegin(); iterator != indicatorConfigValues.constEnd(); ++iterator) {
            caseConfigs.insert(iterator.key(), iterator.value().toObject());
        }
        const NativeIndicatorRuntime::SeriesMap indicatorActual =
            NativeIndicatorRuntime::computeConfiguredSeries(caseCandles, caseConfigs);
        const QJsonObject indicatorExpected = indicatorCase.value(QStringLiteral("expected")).toObject();
        QStringList actualOutputKeys = indicatorActual.keys();
        QStringList expectedOutputKeys = indicatorExpected.keys();
        actualOutputKeys.sort();
        expectedOutputKeys.sort();
        check(actualOutputKeys == expectedOutputKeys,
              QStringLiteral("native C++ indicator outputs should exactly cover Python reference output keys for %1")
                  .arg(caseName));
        for (const QString &key : expectedOutputKeys) {
            const QJsonArray expectedSeries = indicatorExpected.value(key).toArray();
            const NativeIndicatorRuntime::Series actualSeries = indicatorActual.value(key);
            check(actualSeries.size() == expectedSeries.size(),
                  QStringLiteral("native C++ indicator series length should match Python for %1/%2")
                      .arg(caseName, key));
            const qsizetype comparableSize = std::min(actualSeries.size(), expectedSeries.size());
            for (qsizetype index = 0; index < comparableSize; ++index) {
                const QJsonValue expectedValue = expectedSeries.at(index);
                const double actualValue = actualSeries.at(index);
                if (expectedValue.isNull()) {
                    check(!std::isfinite(actualValue),
                          QStringLiteral("native C++ indicator warm-up should be NaN for %1/%2[%3]")
                              .arg(caseName, key).arg(index));
                    continue;
                }
                const double expectedNumber = expectedValue.toDouble();
                const double tolerance = 1e-9 * std::max(1.0, std::abs(expectedNumber));
                check(std::isfinite(actualValue)
                          && std::abs(actualValue - expectedNumber) <= tolerance,
                      QStringLiteral("native C++ indicator should match Python for %1/%2[%3]: expected %4, got %5")
                          .arg(caseName, key)
                          .arg(index)
                          .arg(expectedNumber, 0, 'g', 16)
                          .arg(actualValue, 0, 'g', 16));
            }
        }
        if (caseIndex == 0) {
            indicatorCandles = caseCandles;
            indicatorConfigs = caseConfigs;
        }
    }
    QStringList nativeComputedIndicatorKeys = NativeIndicatorRuntime::computedIndicatorKeys();
    QStringList pythonIndicatorKeys;
    for (const std::string_view key : PythonParityContract::kPythonIndicatorKeys) {
        pythonIndicatorKeys.push_back(QString::fromUtf8(key.data(), static_cast<qsizetype>(key.size())));
    }
    nativeComputedIndicatorKeys.sort();
    pythonIndicatorKeys.sort();
    check(nativeComputedIndicatorKeys == pythonIndicatorKeys,
          QStringLiteral("native C++ calculator should explicitly implement every Python indicator key"));
    check(NativeIndicatorRuntime::unsupportedEnabledIndicatorKeys(indicatorConfigs).isEmpty(),
          QStringLiteral("native C++ calculator should support every enabled Python fixture indicator"));

    const auto assertIndicatorEnabledCases = [&](std::string_view fixture,
                                                  NativeIndicatorRuntime::IndicatorEnableSemantics semantics,
                                                  const QString &label) {
        const QByteArray fixtureJson(fixture.data(), static_cast<qsizetype>(fixture.size()));
        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(fixtureJson, &parseError);
        check(parseError.error == QJsonParseError::NoError && document.isArray(),
              QStringLiteral("generated Python %1 indicator-enabled fixture should contain valid JSON")
                  .arg(label));
        if (parseError.error != QJsonParseError::NoError || !document.isArray()) {
            return;
        }
        for (const QJsonValue &caseValue : document.array()) {
            const QJsonObject testCase = caseValue.toObject();
            const QJsonObject input = testCase.value(QStringLiteral("input")).toObject();
            QJsonObject config;
            config.insert(QStringLiteral("length"), 2);
            if (input.contains(QStringLiteral("enabled"))) {
                config.insert(QStringLiteral("enabled"), input.value(QStringLiteral("enabled")));
            }
            const bool expected = testCase.value(QStringLiteral("expected")).toBool();
            check(NativeIndicatorRuntime::isIndicatorEnabled(config, semantics) == expected,
                  QStringLiteral("native C++ %1 indicator-enabled coercion should match Python for %2")
                      .arg(label, testCase.value(QStringLiteral("name")).toString()));
            NativeIndicatorRuntime::ConfigMap configs;
            configs.insert(QStringLiteral("ma"), config);
            const NativeIndicatorRuntime::SeriesMap actual =
                NativeIndicatorRuntime::computeConfiguredSeries(indicatorCandles, configs, semantics);
            check(actual.contains(QStringLiteral("ma")) == expected,
                  QStringLiteral("native C++ %1 indicator selection should match Python for %2")
                      .arg(label, testCase.value(QStringLiteral("name")).toString()));
        }
    };
    assertIndicatorEnabledCases(
        PythonParityContract::kPythonIndicatorEnabledReferenceJson,
        NativeIndicatorRuntime::IndicatorEnableSemantics::Strategy,
        QStringLiteral("strategy"));
    assertIndicatorEnabledCases(
        PythonParityContract::kPythonBacktestIndicatorEnabledReferenceJson,
        NativeIndicatorRuntime::IndicatorEnableSemantics::Backtest,
        QStringLiteral("backtest"));

    const QJsonArray backtestCases = indicatorReference.value(QStringLiteral("backtest_cases")).toArray();
    check(!backtestCases.isEmpty(),
          QStringLiteral("generated Python fixture should include native backtest parity cases"));
    check(backtestCases.size() >= 27,
          QStringLiteral("generated Python fixture should cover every backtest case across multiple market scenarios"));
    for (const QJsonValue &caseValue : backtestCases) {
        const QJsonObject testCase = caseValue.toObject();
        const QString fixtureName = testCase.value(QStringLiteral("fixture_name")).toString(
            QStringLiteral("baseline"));
        const QString caseName = QStringLiteral("%1/%2")
                                     .arg(fixtureName, testCase.value(QStringLiteral("name")).toString());
        QVector<NativeIndicatorRuntime::Candle> caseCandles = indicatorCandles;
        const QJsonArray caseCandleValues = testCase.value(QStringLiteral("candles")).toArray();
        if (!caseCandleValues.isEmpty()) {
            caseCandles.clear();
            caseCandles.reserve(caseCandleValues.size());
            const bool hasExecutionWindow = testCase.contains(QStringLiteral("execution_start_offset"));
            for (qsizetype candleIndex = 0; candleIndex < caseCandleValues.size(); ++candleIndex) {
                const QJsonValue &value = caseCandleValues.at(candleIndex);
                const QJsonObject candle = value.toObject();
                caseCandles.push_back({
                    candle.value(QStringLiteral("open")).toDouble(),
                    candle.value(QStringLiteral("high")).toDouble(),
                    candle.value(QStringLiteral("low")).toDouble(),
                    candle.value(QStringLiteral("close")).toDouble(),
                    candle.value(QStringLiteral("volume")).toDouble(),
                    hasExecutionWindow ? candleIndex * 60'000 : 0,
                });
            }
        }
        NativeBacktestRuntime::Request request;
        request.symbol = QStringLiteral("FIXTUREUSDT");
        request.interval = QStringLiteral("1m");
        request.logic = testCase.value(QStringLiteral("logic")).toString();
        request.side = testCase.value(QStringLiteral("side")).toString();
        request.capital = testCase.value(QStringLiteral("capital")).toDouble();
        request.positionPct = testCase.value(QStringLiteral("position_pct")).toDouble();
        request.positionPctUnits = testCase.value(QStringLiteral("position_pct_units")).toString();
        request.leverage = testCase.value(QStringLiteral("leverage")).toDouble();
        request.marginMode = testCase.value(QStringLiteral("margin_mode")).toString();
        request.positionMode = QStringLiteral("Hedge");
        request.assetsMode = QStringLiteral("Single-Asset");
        request.accountMode = QStringLiteral("Classic Trading");
        request.mddLogic = testCase.value(QStringLiteral("mdd_logic")).toString();
        const QJsonObject stopLoss = testCase.value(QStringLiteral("stop_loss")).toObject();
        request.stopLossEnabled = stopLoss.value(QStringLiteral("enabled")).toBool();
        request.stopLossMode = stopLoss.value(QStringLiteral("mode")).toString();
        request.stopLossUsdt = stopLoss.value(QStringLiteral("usdt")).toDouble();
        request.stopLossPercent = stopLoss.value(QStringLiteral("percent")).toDouble();
        request.stopLossScope = stopLoss.value(QStringLiteral("scope")).toString();
        const QJsonObject expected = testCase.value(QStringLiteral("expected")).toObject();
        request.feeBps = expected.value(QStringLiteral("fee_bps")).toDouble(5.0);
        request.slippageBps = expected.value(QStringLiteral("slippage_bps")).toDouble(2.0);
        request.indicators.clear();
        const QJsonObject caseConfigs = testCase.value(QStringLiteral("configs")).toObject();
        for (auto iterator = caseConfigs.constBegin(); iterator != caseConfigs.constEnd(); ++iterator) {
            request.indicators.insert(iterator.key(), iterator.value().toObject());
        }
        if (testCase.contains(QStringLiteral("execution_start_offset"))) {
            const qint64 startOffset = testCase.value(QStringLiteral("execution_start_offset")).toInteger();
            request.startTimeMs = std::max<qint64>(0, startOffset) * 60'000;
            request.endTimeMs = std::max<qint64>(0, caseCandles.size() - 1) * 60'000;
        }

        const NativeBacktestRuntime::Result actual = NativeBacktestRuntime::run(caseCandles, request);
        check(actual.ok,
              QStringLiteral("native C++ backtest should run Python fixture case %1: %2")
                  .arg(caseName, actual.error));
        check(actual.trades == expected.value(QStringLiteral("trades")).toInt(),
              QStringLiteral("native C++ backtest trade count should match Python for %1").arg(caseName));
        const QStringList numericKeys = {
            QStringLiteral("roi_value"),
            QStringLiteral("roi_percent"),
            QStringLiteral("final_equity"),
            QStringLiteral("max_drawdown_value"),
            QStringLiteral("max_drawdown_percent"),
            QStringLiteral("max_drawdown_during_value"),
            QStringLiteral("max_drawdown_during_percent"),
            QStringLiteral("max_drawdown_result_value"),
            QStringLiteral("max_drawdown_result_percent"),
            QStringLiteral("leverage"),
            QStringLiteral("capital"),
            QStringLiteral("position_pct"),
            QStringLiteral("stop_loss_usdt"),
            QStringLiteral("stop_loss_percent"),
            QStringLiteral("fee_bps"),
            QStringLiteral("slippage_bps"),
            QStringLiteral("fees_paid"),
        };
        const QJsonObject actualJson = actual.toJson();
        for (const QString &key : numericKeys) {
            const double expectedNumber = expected.value(key).toDouble();
            const double actualNumber = actualJson.value(key).toDouble();
            const double tolerance = 1e-9 * std::max(1.0, std::abs(expectedNumber));
            check(std::isfinite(actualNumber) && std::abs(actualNumber - expectedNumber) <= tolerance,
                  QStringLiteral("native C++ backtest should match Python %1 for %2: expected %3, got %4")
                      .arg(key, caseName)
                      .arg(expectedNumber, 0, 'g', 16)
                      .arg(actualNumber, 0, 'g', 16));
        }
        const QStringList textKeys = {
            QStringLiteral("logic"),
            QStringLiteral("mdd_logic"),
            QStringLiteral("side"),
            QStringLiteral("position_pct_units"),
            QStringLiteral("stop_loss_mode"),
            QStringLiteral("stop_loss_scope"),
            QStringLiteral("margin_mode"),
            QStringLiteral("position_mode"),
            QStringLiteral("assets_mode"),
            QStringLiteral("account_mode"),
        };
        for (const QString &key : textKeys) {
            check(actualJson.value(key).toString() == expected.value(key).toString(),
                  QStringLiteral("native C++ backtest should match Python %1 for %2")
                      .arg(key, caseName));
        }
        check(actual.stopLossEnabled == expected.value(QStringLiteral("stop_loss_enabled")).toBool(),
              QStringLiteral("native C++ backtest stop-loss enabled state should match Python for %1")
                  .arg(caseName));
        check(actualJson.value(QStringLiteral("indicator_keys")).toArray()
                  == expected.value(QStringLiteral("indicator_keys")).toArray(),
              QStringLiteral("native C++ backtest indicator keys should match Python for %1")
                  .arg(caseName));
    }

    NativeBacktestRuntime::Request cancelledBacktest;
    cancelledBacktest.capital = 1000.0;
    cancelledBacktest.indicators.insert(
        QStringLiteral("rsi"),
        QJsonObject{
            {QStringLiteral("enabled"), true},
            {QStringLiteral("length"), 3},
            {QStringLiteral("buy_value"), 45.0},
            {QStringLiteral("sell_value"), 55.0},
        });
    NativeBacktestRuntime::Request directIntervalBacktest = cancelledBacktest;
    directIntervalBacktest.interval = QStringLiteral("60 minutes");
    const NativeBacktestRuntime::Result directIntervalResult = NativeBacktestRuntime::run(
        indicatorCandles,
        directIntervalBacktest,
        []() { return false; });
    check(directIntervalResult.interval == QStringLiteral("1h"),
          QStringLiteral("native C++ direct backtest results should expose Python-canonical intervals"));
    const NativeBacktestRuntime::Result cancelledResult = NativeBacktestRuntime::run(
        indicatorCandles,
        cancelledBacktest,
        []() { return true; });
    check(!cancelledResult.ok && cancelledResult.error == QStringLiteral("backtest_cancelled"),
          QStringLiteral("native C++ backtest should preserve cooperative cancellation"));

    QVector<NativeIndicatorRuntime::Candle> timestampedWindowCandles{
        {100.0, 101.0, 99.0, 100.0, 20.0, 0},
        {100.0, 101.0, 99.0, 100.0, 30.0, 60'000},
        {109.0, 111.0, 108.0, 110.0, 30.0, 120'000},
        {109.0, 111.0, 108.0, 110.0, 30.0, 180'000},
    };
    NativeBacktestRuntime::Request timestampedWindowRequest;
    timestampedWindowRequest.symbol = QStringLiteral("WINDOWUSDT");
    timestampedWindowRequest.interval = QStringLiteral("1m");
    timestampedWindowRequest.capital = 1'000.0;
    timestampedWindowRequest.positionPct = 1.0;
    timestampedWindowRequest.positionPctUnits = QStringLiteral("fraction");
    timestampedWindowRequest.leverage = 1.0;
    timestampedWindowRequest.feeBps = 0.0;
    timestampedWindowRequest.slippageBps = 0.0;
    timestampedWindowRequest.startTimeMs = 60'000;
    timestampedWindowRequest.endTimeMs = 180'000;
    timestampedWindowRequest.indicators.clear();
    timestampedWindowRequest.indicators.insert(
        QStringLiteral("volume"),
        QJsonObject{
            {QStringLiteral("enabled"), true},
            {QStringLiteral("buy_value"), 10.0},
        });
    const NativeBacktestRuntime::Result timestampedWindowResult = NativeBacktestRuntime::run(
        timestampedWindowCandles,
        timestampedWindowRequest);
    check(timestampedWindowResult.ok
              && timestampedWindowResult.trades == 1
              && std::abs(timestampedWindowResult.finalEquity - 1'100.0) <= 1e-9,
          QStringLiteral("native C++ window mismatch: ok=%1 error=%2 trades=%3 final=%4")
              .arg(timestampedWindowResult.ok)
              .arg(timestampedWindowResult.error)
              .arg(timestampedWindowResult.trades)
              .arg(timestampedWindowResult.finalEquity, 0, 'f', 12));
    NativeBacktestRuntime::Request percentageAliasRequest = timestampedWindowRequest;
    percentageAliasRequest.positionPct = 0.25;
    percentageAliasRequest.positionPctUnits = QStringLiteral("percentage");
    const NativeBacktestRuntime::Result percentageAliasResult = NativeBacktestRuntime::run(
        timestampedWindowCandles,
        percentageAliasRequest);
    check(percentageAliasResult.ok
              && std::abs(percentageAliasResult.positionPct - 0.0025) <= 1e-12
              && percentageAliasResult.positionPctUnits == QStringLiteral("fraction"),
          QStringLiteral("native C++ backtest should consume Python percentage-unit alias"));
    NativeBacktestRuntime::Request noWindowRequest = timestampedWindowRequest;
    noWindowRequest.startTimeMs = 300'000;
    noWindowRequest.endTimeMs = 360'000;
    const NativeBacktestRuntime::Result noWindowResult = NativeBacktestRuntime::run(
        timestampedWindowCandles,
        noWindowRequest);
    check(!noWindowResult.ok
              && noWindowResult.error == QStringLiteral("No candles fall inside the requested backtest window"),
          QStringLiteral("native C++ empty window mismatch: ok=%1 error=%2")
              .arg(noWindowResult.ok)
              .arg(noWindowResult.error));
    check(NativeBacktestBatchRuntime::estimateWarmupBars(timestampedWindowRequest.indicators) == 50,
          QStringLiteral("native C++ indicator warmup mismatch: actual=%1")
              .arg(NativeBacktestBatchRuntime::estimateWarmupBars(timestampedWindowRequest.indicators)));
    check(NativeBacktestBatchRuntime::estimateWarmupBars({}) == 100,
          QStringLiteral("native C++ empty warmup mismatch: actual=%1")
              .arg(NativeBacktestBatchRuntime::estimateWarmupBars({})));
    NativeIndicatorRuntime::ConfigMap explicitWarmupConfigs;
    explicitWarmupConfigs.insert(
        QStringLiteral("macd"),
        QJsonObject{{QStringLiteral("enabled"), true}, {QStringLiteral("fast"), 12}, {QStringLiteral("slow"), 26}});
    explicitWarmupConfigs.insert(
        QStringLiteral("ichimoku"),
        QJsonObject{{QStringLiteral("enabled"), false}, {QStringLiteral("span_b_length"), 52}});
    check(NativeBacktestBatchRuntime::estimateWarmupBars(explicitWarmupConfigs) == 26,
          QStringLiteral("native C++ explicit warmup mismatch: actual=%1")
              .arg(NativeBacktestBatchRuntime::estimateWarmupBars(explicitWarmupConfigs)));
    check(NativeBacktestBatchRuntime::bufferedStartTimeMs(100'000'000, QStringLiteral("5m"), 50)
              == 70'000'000,
          QStringLiteral("native C++ warmup start should match Python's two-window interval buffer"));

    NativeIndicatorRuntime::ConfigMap optimizerConfigs;
    optimizerConfigs.insert(
        QStringLiteral("rsi"),
        QJsonObject{
            {QStringLiteral("enabled"), true},
            {QStringLiteral("length"), 3},
            {QStringLiteral("buy_value"), 45.0},
            {QStringLiteral("sell_value"), 55.0},
        });
    optimizerConfigs.insert(
        QStringLiteral("macd"),
        QJsonObject{
            {QStringLiteral("enabled"), true},
            {QStringLiteral("fast"), 3},
            {QStringLiteral("slow"), 6},
            {QStringLiteral("signal"), 2},
            {QStringLiteral("buy_value"), 0.0},
            {QStringLiteral("sell_value"), 0.0},
        });
    optimizerConfigs.insert(
        QStringLiteral("volume"),
        QJsonObject{
            {QStringLiteral("enabled"), true},
            {QStringLiteral("length"), 3},
            {QStringLiteral("buy_value"), 0.5},
            {QStringLiteral("signal_mode"), QStringLiteral("relative_to_sma")},
            {QStringLiteral("signal_role"), QStringLiteral("filter")},
            {QStringLiteral("filter_operator"), QStringLiteral("gte")},
        });
    const QVector<QStringList> singleGroups =
        NativeBacktestBatchRuntime::buildIndicatorGroups(
            optimizerConfigs,
            QStringLiteral("single"),
            2,
            QStringLiteral("AND"));
    check(singleGroups.size() == 2,
          QStringLiteral("native optimizer single mode should create one group per signal indicator"));
    check(singleGroups.at(0).contains(QStringLiteral("volume"))
              && singleGroups.at(1).contains(QStringLiteral("volume")),
          QStringLiteral("native optimizer should append enabled filters to every signal group like Python"));
    const QVector<QStringList> pairGroups =
        NativeBacktestBatchRuntime::buildIndicatorGroups(
            optimizerConfigs,
            QStringLiteral("pairs"),
            2,
            QStringLiteral("AND"));
    check(pairGroups.size() == 1 && pairGroups.constFirst().size() == 3,
          QStringLiteral("native optimizer pair mode should combine two signals plus shared filters"));
    const QVector<QStringList> combinationGroups =
        NativeBacktestBatchRuntime::buildIndicatorGroups(
            optimizerConfigs,
            QStringLiteral("combinations"),
            2,
            QStringLiteral("AND"));
    check(combinationGroups.size() == 3,
          QStringLiteral("native optimizer combinations mode should include sizes one through Max Combo"));
    const QVector<QStringList> separateGroups =
        NativeBacktestBatchRuntime::buildIndicatorGroups(
            optimizerConfigs,
            QStringLiteral("current"),
            2,
            QStringLiteral("SEPARATE"));
    check(separateGroups.size() == 2,
          QStringLiteral("native current optimizer should split signal indicators for SEPARATE logic"));
    check(NativeBacktestBatchRuntime::estimateRunCount(200, 20, 435) == 1'740'000,
          QStringLiteral("native optimizer run estimate should match the Python Cartesian plan"));

    for (const auto &intervalCase : {
             std::pair<QString, QString>{QStringLiteral("60 minutes"), QStringLiteral("1h")},
             std::pair<QString, QString>{QStringLiteral("20 minutes"), QStringLiteral("20m")},
             std::pair<QString, QString>{QStringLiteral("3 hours"), QStringLiteral("3h")},
             std::pair<QString, QString>{QStringLiteral("2 days"), QStringLiteral("2d")},
             std::pair<QString, QString>{QStringLiteral("3 weeks"), QStringLiteral("3w")},
             std::pair<QString, QString>{QStringLiteral("1M"), QStringLiteral("1mo")},
             std::pair<QString, QString>{QStringLiteral("1 M"), QStringLiteral("1mo")},
             std::pair<QString, QString>{QStringLiteral("1 year"), QStringLiteral("1y")},
             std::pair<QString, QString>{QStringLiteral("1 q"), QStringLiteral("1 q")},
         }) {
        check(
            NativeStrategyRuntime::canonicalizeBacktestInterval(QJsonValue(intervalCase.first))
                == intervalCase.second,
            QStringLiteral("native C++ interval alias %1 should match Python canonicalization")
                .arg(intervalCase.first));
    }
    check(
        NativePythonParity::canonicalConfigChoice(
            QStringLiteral("top n"),
            PythonParityContract::kPythonScanScopeConfigChoices)
            == QStringLiteral("top_n"),
        QStringLiteral("native C++ choice normalization should match Python underscore aliases"));
    check(
        NativePythonParity::canonicalConfigChoice(
            QStringLiteral("roi percent mdd"),
            PythonParityContract::kPythonOptimizerMetricConfigChoices)
            == QStringLiteral("roi_percent_mdd"),
        QStringLiteral("native C++ choice normalization should match Python space aliases"));

    NativeBacktestRuntime::Result scoreFixture;
    scoreFixture.trades = 5;
    scoreFixture.roiPercent = 12.0;
    scoreFixture.roiValue = 120.0;
    scoreFixture.maxDrawdownPercent = 4.0;
    const NativeBacktestBatchRuntime::Score drawdownScore =
        NativeBacktestBatchRuntime::optimizerScore(
            scoreFixture,
            QStringLiteral("roi_drawdown"),
            20.0,
            1);
    check(drawdownScore.eligible && !drawdownScore.values.isEmpty()
              && std::abs(drawdownScore.values.constFirst() - 3.0) < 1e-12,
          QStringLiteral("native optimizer ROI/drawdown score should match Python"));
    const NativeBacktestBatchRuntime::Score mddRejected =
        NativeBacktestBatchRuntime::optimizerScore(
            scoreFixture,
            QStringLiteral("roi_percent"),
            3.0,
            1);
    check(!mddRejected.eligible && mddRejected.rejectionReason.contains(QStringLiteral("MDD")),
          QStringLiteral("native optimizer should reject runs above the configured MDD for every metric"));

    NativeBacktestBatchRuntime::BatchRequest batchRequest;
    const QJsonObject pythonBacktestDefaults = QJsonDocument::fromJson(QByteArray(
        PythonParityContract::kPythonDefaultBacktestJson.data(),
        static_cast<int>(PythonParityContract::kPythonDefaultBacktestJson.size()))).object();
    check(
        batchRequest.optimizerMaxDurationSeconds
            == static_cast<qint64>(pythonBacktestDefaults.value(QStringLiteral("optimizer_max_duration_seconds")).toDouble()),
        QStringLiteral("native C++ optimizer duration default should match Python"));
    batchRequest.symbols = {QStringLiteral("BTCUSDT"), QStringLiteral("ETHUSDT")};
    batchRequest.intervals = {QStringLiteral("1m"), QStringLiteral("1 minute"), QStringLiteral("60 seconds")};
    batchRequest.indicatorConfigs.insert(QStringLiteral("rsi"), optimizerConfigs.value(QStringLiteral("rsi")));
    batchRequest.runTemplate = cancelledBacktest;
    batchRequest.optimizerMinTrades = 0;
    batchRequest.optimizerMddLimit = 0.0;
    batchRequest.startDisplay = QStringLiteral("2026-01-01");
    batchRequest.endDisplay = QStringLiteral("2026-02-01");
    check(NativeBacktestBatchRuntime::estimateRunCount(batchRequest) == 2,
          QStringLiteral("native batch run estimate should deduplicate Python-equivalent symbol and interval aliases"));
    const QJsonObject batchSnapshot = NativeBacktestBatchRuntime::runBatch(
        batchRequest,
        [&indicatorCandles](const QString &, const QString &, const NativeBacktestBatchRuntime::StopCallback &) {
            return NativeBacktestBatchRuntime::CandleLoadResult{true, indicatorCandles, {}};
        });
    check(batchSnapshot.value(QStringLiteral("state")).toString() == QStringLiteral("completed"),
          QStringLiteral("native batch backtest should complete with an injected candle loader"));
    check(batchSnapshot.value(QStringLiteral("processed_count")).toInt() == 2,
          QStringLiteral("native batch backtest should execute each symbol/interval/group run"));
    check(batchSnapshot.value(QStringLiteral("top_runs")).toArray().size() == 2,
          QStringLiteral("native batch backtest should return ranked result rows"));
    check(batchSnapshot.value(QStringLiteral("top_run")).toObject().value(QStringLiteral("source")).toString()
              == QStringLiteral("native-cpp-backtest"),
          QStringLiteral("native batch backtest should identify its native C++ source"));

    NativeBacktestBatchRuntime::BatchRequest budgetBatchRequest = batchRequest;
    budgetBatchRequest.symbols = {QStringLiteral("BTCUSDT"), QStringLiteral("ETHUSDT")};
    budgetBatchRequest.optimizerMode = QStringLiteral("single");
    budgetBatchRequest.optimizerEnabled = true;
    budgetBatchRequest.optimizerMaxDurationSeconds = 1;
    const QJsonObject budgetSnapshot = NativeBacktestBatchRuntime::runBatch(
        budgetBatchRequest,
        [](const QString &, const QString &, const NativeBacktestBatchRuntime::StopCallback &stop) {
            while (!stop()) QThread::msleep(10);
            return NativeBacktestBatchRuntime::CandleLoadResult{false, {}, QStringLiteral("backtest_cancelled")};
        });
    check(budgetSnapshot.value(QStringLiteral("state")).toString() == QStringLiteral("budget_exhausted"),
          QStringLiteral("native C++ optimizer should enforce its Python time budget"));
    check(!budgetSnapshot.value(QStringLiteral("cancelled")).toBool(true),
          QStringLiteral("native C++ optimizer budget exhaustion should not be reported as user cancellation"));
    check(budgetSnapshot.value(QStringLiteral("errors")).toArray().last().toObject().value(QStringLiteral("error")).toString()
              == QStringLiteral("backtest_optimizer_time_budget_exhausted"),
          QStringLiteral("native C++ optimizer budget exhaustion should preserve the Python error contract"));

    NativeBacktestBatchRuntime::BatchRequest separateBatchRequest = batchRequest;
    separateBatchRequest.symbols = {QStringLiteral("BTCUSDT")};
    separateBatchRequest.indicatorConfigs = optimizerConfigs;
    separateBatchRequest.runTemplate.logic = QStringLiteral("SEPARATE");
    const QJsonObject separateBatchSnapshot = NativeBacktestBatchRuntime::runBatch(
        separateBatchRequest,
        [&indicatorCandles](const QString &, const QString &, const NativeBacktestBatchRuntime::StopCallback &) {
            return NativeBacktestBatchRuntime::CandleLoadResult{true, indicatorCandles, {}};
        });
    check(separateBatchSnapshot.value(QStringLiteral("state")).toString() == QStringLiteral("completed")
              && separateBatchSnapshot.value(QStringLiteral("optimizer_run_count")).toInt() == 2
              && separateBatchSnapshot.value(QStringLiteral("processed_count")).toInt() == 2,
          QStringLiteral("native C++ SEPARATE backtest should execute one run per signal indicator"));
    const QJsonArray separateRuns = separateBatchSnapshot.value(QStringLiteral("top_runs")).toArray();
    check(separateRuns.size() == 2,
          QStringLiteral("native C++ SEPARATE backtest should return every split signal run"));
    for (const QJsonValue &value : separateRuns) {
        const QJsonObject row = value.toObject();
        check(row.value(QStringLiteral("logic")).toString() == QStringLiteral("SEPARATE")
                  && row.value(QStringLiteral("strategy_controls")).toObject().value(QStringLiteral("logic")).toString()
                         == QStringLiteral("SEPARATE"),
              QStringLiteral("native C++ SEPARATE rows should preserve Python logic metadata"));
    }

    NativeBacktestBatchRuntime::BatchRequest overrideBatchRequest = batchRequest;
    overrideBatchRequest.indicatorConfigs = optimizerConfigs;
    overrideBatchRequest.optimizerMode = QStringLiteral("combinations");
    overrideBatchRequest.optimizerComboSize = 2;
    const QJsonObject pairStopLoss{
        {QStringLiteral("enabled"), true},
        {QStringLiteral("mode"), QStringLiteral("percent")},
        {QStringLiteral("percent"), 2.5},
        {QStringLiteral("scope"), QStringLiteral("per_trade")},
    };
    const QJsonObject pairControls{
        {QStringLiteral("logic"), QStringLiteral("AND")},
        {QStringLiteral("capital"), 500.0},
        {QStringLiteral("side"), QStringLiteral("SELL")},
        {QStringLiteral("position_pct"), 25.0},
        {QStringLiteral("position_pct_units"), QStringLiteral("percent")},
        {QStringLiteral("leverage"), 4.0},
        {QStringLiteral("stop_loss"), pairStopLoss},
    };
    const QJsonObject pairOverride{
        {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
        {QStringLiteral("interval"), QStringLiteral("1m")},
        {QStringLiteral("indicators"), QJsonArray{QStringLiteral("rsi")}},
        {QStringLiteral("strategy_controls"), pairControls},
        {QStringLiteral("loop_interval_override"), QStringLiteral("5m")},
        {QStringLiteral("connector_backend"), QStringLiteral("binance-rest")},
    };
    overrideBatchRequest.pairOverrides = QJsonArray{pairOverride, pairOverride};
    check(NativeBacktestBatchRuntime::estimateRunCount(overrideBatchRequest) == 1,
          QStringLiteral("native pair overrides should replace the Cartesian optimizer plan and deduplicate like Python"));
    int pairOverrideLoads = 0;
    const QJsonObject overrideBatchSnapshot = NativeBacktestBatchRuntime::runBatch(
        overrideBatchRequest,
        [&indicatorCandles, &pairOverrideLoads](
            const QString &,
            const QString &,
            const NativeBacktestBatchRuntime::StopCallback &) {
            ++pairOverrideLoads;
            return NativeBacktestBatchRuntime::CandleLoadResult{true, indicatorCandles, {}};
        });
    check(overrideBatchSnapshot.value(QStringLiteral("state")).toString() == QStringLiteral("completed")
              && overrideBatchSnapshot.value(QStringLiteral("processed_count")).toInt() == 1,
          QStringLiteral("native pair override batch should execute the explicit override exactly once"));
    check(pairOverrideLoads == 1,
          QStringLiteral("native pair override batch should reuse candle data for duplicate pair plans"));
    const QJsonObject overrideTopRun = overrideBatchSnapshot.value(QStringLiteral("top_run")).toObject();
    const QJsonArray overrideIndicatorKeys = overrideTopRun.value(QStringLiteral("indicator_keys")).toArray();
    check(overrideIndicatorKeys.contains(QStringLiteral("rsi"))
              && overrideIndicatorKeys.contains(QStringLiteral("volume"))
              && !overrideIndicatorKeys.contains(QStringLiteral("macd")),
          QStringLiteral("native pair override should select requested signals and retain global filters like Python"));
    check(overrideTopRun.value(QStringLiteral("side")).toString() == QStringLiteral("SELL")
              && std::abs(overrideTopRun.value(QStringLiteral("capital")).toDouble() - 500.0) < 1e-12
              && std::abs(overrideTopRun.value(QStringLiteral("leverage")).toDouble() - 4.0) < 1e-12,
          QStringLiteral("native pair override should apply side, capital, and leverage controls"));
    check(overrideTopRun.value(QStringLiteral("stop_loss_enabled")).toBool(false)
              && overrideTopRun.value(QStringLiteral("stop_loss_mode")).toString() == QStringLiteral("percent")
              && std::abs(overrideTopRun.value(QStringLiteral("stop_loss_percent")).toDouble() - 2.5) < 1e-12,
          QStringLiteral("native pair override should apply nested stop-loss controls"));
    check(overrideTopRun.value(QStringLiteral("loop_interval_override")).toString() == QStringLiteral("5m")
              && overrideTopRun.value(QStringLiteral("connector_backend")).toString() == QStringLiteral("binance-rest"),
          QStringLiteral("native pair override should preserve pair-specific execution metadata"));

    NativeOrderSafety::LiveOrderGuardInput paperInvalidOrder;
    paperInvalidOrder.mode = QStringLiteral("Demo/Testnet");
    paperInvalidOrder.params = {
        {QStringLiteral("symbol"), QStringLiteral("ETHUSDT")},
        {QStringLiteral("side"), QStringLiteral("BUY")},
        {QStringLiteral("type"), QStringLiteral("MARKET")},
        {QStringLiteral("quantity"), QStringLiteral("0.1")},
    };
    const NativeOrderSafety::LiveOrderGuardResult paperInvalidResult =
        NativeOrderSafety::guardLiveOrderSubmit(paperInvalidOrder);
    check(!paperInvalidResult.allowed,
          QStringLiteral("paper order guard should keep exchange filter validation enabled"));
    check(paperInvalidResult.errors.contains(QStringLiteral("futures symbol filters unavailable for ETHUSDT")),
          QStringLiteral("paper order guard should report unavailable exchange filters"));
    check(paperInvalidResult.nextSubmitAttemptCount == 0,
          QStringLiteral("paper order guard should not consume the live session order count"));

    NativeOrderSafety::LiveOrderGuardInput paperValidOrder = paperInvalidOrder;
    paperValidOrder.hasFilters = true;
    paperValidOrder.filters = {0.001, 0.1, 0.001, 5.0};
    paperValidOrder.hasLastPrice = true;
    paperValidOrder.lastPrice = 100.0;
    paperValidOrder.connectorState = QStringLiteral("ready");
    paperValidOrder.connectorHealth = QStringLiteral("ok");
    paperValidOrder.liveSubmitAttemptCount = 3;
    const NativeOrderSafety::LiveOrderGuardResult paperValidResult =
        NativeOrderSafety::guardLiveOrderSubmit(paperValidOrder);
    check(paperValidResult.allowed,
          QStringLiteral("paper order guard should allow a valid structurally safe order"));
    check(paperValidResult.nextSubmitAttemptCount == 3,
          QStringLiteral("paper order guard should preserve the live session order count"));

    NativeOrderSafety::LiveOrderGuardInput nonFiniteQuantity = paperValidOrder;
    nonFiniteQuantity.params = {
        {QStringLiteral("symbol"), QStringLiteral("ETHUSDT")},
        {QStringLiteral("side"), QStringLiteral("BUY")},
        {QStringLiteral("type"), QStringLiteral("MARKET")},
        {QStringLiteral("quantity"), QStringLiteral("NaN")},
    };
    const NativeOrderSafety::LiveOrderGuardResult nonFiniteQuantityResult =
        NativeOrderSafety::guardLiveOrderSubmit(nonFiniteQuantity);
    check(nonFiniteQuantityResult.errors.contains(
              QStringLiteral("order quantity must be a finite number for ETHUSDT")),
          QStringLiteral("C++ order guard should preserve Python non-finite quantity errors"));
    check(!nonFiniteQuantityResult.errors.contains(QStringLiteral("order quantity must be > 0")),
          QStringLiteral("C++ order guard should not treat Python NaN as an omitted quantity"));

    NativeOrderSafety::LiveOrderGuardInput nonFinitePrice = paperValidOrder;
    nonFinitePrice.params = {
        {QStringLiteral("symbol"), QStringLiteral("ETHUSDT")},
        {QStringLiteral("side"), QStringLiteral("BUY")},
        {QStringLiteral("type"), QStringLiteral("LIMIT")},
        {QStringLiteral("quantity"), QStringLiteral("0.10")},
        {QStringLiteral("price"), QStringLiteral("Infinity")},
    };
    const NativeOrderSafety::LiveOrderGuardResult nonFinitePriceResult =
        NativeOrderSafety::guardLiveOrderSubmit(nonFinitePrice);
    check(nonFinitePriceResult.errors.contains(
              QStringLiteral("order price must be a finite number for ETHUSDT")),
          QStringLiteral("C++ order guard should preserve Python non-finite price errors"));
    check(!nonFinitePriceResult.errors.contains(QStringLiteral("limit order price must be > 0")),
          QStringLiteral("C++ order guard should not treat Python Infinity as an omitted price"));

    qputenv("BOT_ENABLE_LIVE_TRADING", QByteArray("true"));
    qputenv("BOT_LIVE_TRADING_ACKNOWLEDGEMENT", QByteArray("I_UNDERSTAND_LIVE_TRADING_RISK"));
    qputenv("BOT_LIVE_MAX_LEVERAGE", QByteArray("5"));
    qputenv("BOT_LIVE_MAX_POSITION_PCT", QByteArray("4"));
    qputenv("BOT_LIVE_MAX_SESSION_ORDERS", QByteArray("1"));
    NativeOrderSafety::LiveOrderGuardInput environmentConfirmedOrder;
    environmentConfirmedOrder.mode = QStringLiteral("Live");
    environmentConfirmedOrder.apiKey = QStringLiteral("real-api-key");
    environmentConfirmedOrder.apiSecret = QStringLiteral("real-api-secret");
    environmentConfirmedOrder.accountType = QStringLiteral("FUTURES");
    environmentConfirmedOrder.leverage = 5;
    environmentConfirmedOrder.marginMode = QStringLiteral("Isolated");
    environmentConfirmedOrder.positionPct = 4.0;
    environmentConfirmedOrder.params = {
        {QStringLiteral("symbol"), QStringLiteral("ETHUSDT")},
        {QStringLiteral("side"), QStringLiteral("BUY")},
        {QStringLiteral("type"), QStringLiteral("MARKET")},
        {QStringLiteral("quantity"), QStringLiteral("0.10")},
    };
    environmentConfirmedOrder.hasFilters = true;
    environmentConfirmedOrder.filters = {0.001, 0.1, 0.01, 5.0};
    environmentConfirmedOrder.hasLastPrice = true;
    environmentConfirmedOrder.lastPrice = 100.0;
    environmentConfirmedOrder.connectorState = QStringLiteral("ready");
    environmentConfirmedOrder.connectorHealth = QStringLiteral("ok");
    const NativeOrderSafety::LiveOrderGuardResult environmentConfirmedResult =
        NativeOrderSafety::guardLiveOrderSubmit(environmentConfirmedOrder);
    check(environmentConfirmedResult.allowed,
          QStringLiteral("C++ order guard should honor Python live-safety environment overrides"));
    check(environmentConfirmedResult.nextSubmitAttemptCount == 1,
          QStringLiteral("C++ order guard should apply the Python environment session cap"));
    qunsetenv("BOT_ENABLE_LIVE_TRADING");
    qunsetenv("BOT_LIVE_TRADING_ACKNOWLEDGEMENT");
    qunsetenv("BOT_LIVE_MAX_LEVERAGE");
    qunsetenv("BOT_LIVE_MAX_POSITION_PCT");
    qunsetenv("BOT_LIVE_MAX_SESSION_ORDERS");

    NativeOrderSafety::MinimumOrderAutoBumpGuardInput liveAutoBump;
    liveAutoBump.mode = QStringLiteral("Live");
    liveAutoBump.requestedQuantity = 0.001;
    liveAutoBump.normalizedQuantity = 0.01;
    liveAutoBump.price = 100.0;
    liveAutoBump.availableUsdt = 100.0;
    liveAutoBump.leverage = 2;
    liveAutoBump.requestedPositionPct = 0.1;
    const NativeOrderSafety::MinimumOrderAutoBumpGuardResult liveAutoBumpBlocked =
        NativeOrderSafety::guardFuturesMinimumOrderAutoBump(liveAutoBump);
    check(!liveAutoBumpBlocked.allowed && liveAutoBumpBlocked.autoBumpRequired,
          QStringLiteral("live minimum-order auto-bump should be denied unless explicitly enabled"));
    check(liveAutoBumpBlocked.errors.join(QStringLiteral(" ")).contains(
              QStringLiteral("live_allow_auto_bump_to_min_order")),
          QStringLiteral("live minimum-order auto-bump denial should explain the explicit opt-in"));

    liveAutoBump.config.liveAllowAutoBumpToMinOrder = true;
    const NativeOrderSafety::MinimumOrderAutoBumpGuardResult liveAutoBumpAllowed =
        NativeOrderSafety::guardFuturesMinimumOrderAutoBump(liveAutoBump);
    check(liveAutoBumpAllowed.allowed && liveAutoBumpAllowed.autoBumpRequired,
          QStringLiteral("explicit live minimum-order auto-bump opt-in should allow a funded order"));

    liveAutoBump.config.maxAutoBumpPercent = 0.25;
    liveAutoBump.config.autoBumpPercentMultiplier = 1.0;
    const NativeOrderSafety::MinimumOrderAutoBumpGuardResult autoBumpCapBlocked =
        NativeOrderSafety::guardFuturesMinimumOrderAutoBump(liveAutoBump);
    check(!autoBumpCapBlocked.allowed
              && autoBumpCapBlocked.errors.join(QStringLiteral(" ")).contains(QStringLiteral("insufficient funds")),
          QStringLiteral("minimum-order auto-bump should enforce the configured percentage cap"));

    NativeOrderSafety::CapitalExposureGuardInput capitalGuard;
    capitalGuard.market = QStringLiteral("futures");
    capitalGuard.symbol = QStringLiteral("BTCUSDT");
    capitalGuard.interval = QStringLiteral("1m");
    capitalGuard.side = QStringLiteral("BUY");
    capitalGuard.positionPctFraction = 0.02;
    capitalGuard.availableUsdt = 100.0;
    capitalGuard.walletUsdt = 1000.0;
    capitalGuard.price = 100.0;
    capitalGuard.leverage = 5;
    capitalGuard.hasFilters = true;
    capitalGuard.filters = {0.001, 0.1, 0.001, 5.0};
    capitalGuard.requestedQuantity = 1.0;
    capitalGuard.normalizedQuantity = 1.0;
    capitalGuard.marginOverTargetTolerance = 0.05;
    capitalGuard.marginFilterSlippage = 0.1;
    capitalGuard.dualSide = true;
    const NativeOrderSafety::CapitalExposureGuardResult capitalAllowed =
        NativeOrderSafety::guardFuturesCapitalExposure(capitalGuard);
    check(capitalAllowed.allowed
              && capitalAllowed.reason == QStringLiteral("capital guard: allowed")
              && std::abs(capitalAllowed.targetMarginUsdt - 20.0) < 1e-12
              && std::abs(capitalAllowed.marginEstimateUsdt - 20.0) < 1e-12
              && capitalAllowed.desiredPositionSide == QStringLiteral("LONG"),
          QStringLiteral("C++ capital guard should allow a position within the Python allocation cap"));

    NativeOrderSafety::CapitalExposureGuardInput flipQuantityGuard = capitalGuard;
    flipQuantityGuard.flipCloseQuantity = 0.5;
    flipQuantityGuard.hasFlipCloseQuantity = true;
    flipQuantityGuard.requestedQuantity = 0.5;
    flipQuantityGuard.normalizedQuantity = 0.5;
    const NativeOrderSafety::CapitalExposureGuardResult flipQuantityAllowed =
        NativeOrderSafety::guardFuturesCapitalExposure(flipQuantityGuard);
    check(flipQuantityAllowed.allowed
              && std::abs(flipQuantityAllowed.quantityEstimate - 0.5) < 1e-12
              && std::abs(flipQuantityAllowed.marginEstimateUsdt - 10.0) < 1e-12,
          QStringLiteral("C++ capital guard should preserve Python flip quantity instead of recomputing the target"));

    NativeOrderSafety::CapitalExposureGuardInput stepRoundedFilterFloor = capitalGuard;
    stepRoundedFilterFloor.positionPctFraction = 0.05;
    stepRoundedFilterFloor.availableUsdt = 124.0;
    stepRoundedFilterFloor.walletUsdt = 124.0;
    stepRoundedFilterFloor.leverage = 1;
    stepRoundedFilterFloor.filters.stepSize = 0.03;
    stepRoundedFilterFloor.filters.minQty = 0.01;
    stepRoundedFilterFloor.filters.minNotional = 5.0;
    stepRoundedFilterFloor.price = 100.0;
    stepRoundedFilterFloor.requestedQuantity = 0.06;
    stepRoundedFilterFloor.normalizedQuantity = 0.06;
    stepRoundedFilterFloor.existingIndicatorMargin = 2.0;
    const NativeOrderSafety::CapitalExposureGuardResult stepRoundedFilterAllowed =
        NativeOrderSafety::guardFuturesCapitalExposure(stepRoundedFilterFloor);
    check(stepRoundedFilterAllowed.allowed
              && std::abs(stepRoundedFilterAllowed.maxIndicatorMarginUsdt - 7.76) < 1e-12,
          QStringLiteral("C++ capital guard should round a minimum-notional quantity up to the exchange step like Python"));

    NativeOrderSafety::CapitalExposureGuardInput indicatorOverCap = capitalGuard;
    indicatorOverCap.existingIndicatorMargin = 22.0;
    const NativeOrderSafety::CapitalExposureGuardResult indicatorBlocked =
        NativeOrderSafety::guardFuturesCapitalExposure(indicatorOverCap);
    check(!indicatorBlocked.allowed
              && indicatorBlocked.reason.contains(QStringLiteral("existing BUY margin already >= cap")),
          QStringLiteral("C++ capital guard should block existing indicator margin over the Python cap"));

    NativeOrderSafety::CapitalExposureGuardInput sideOverCap = capitalGuard;
    sideOverCap.existingSideMargin = 100.0;
    const NativeOrderSafety::CapitalExposureGuardResult sideBlocked =
        NativeOrderSafety::guardFuturesCapitalExposure(sideOverCap);
    check(!sideBlocked.allowed
              && sideBlocked.reason.contains(QStringLiteral("projected side margin exceeds cap")),
          QStringLiteral("C++ capital guard should block projected same-side margin over the Python cap"));

    NativeOrderSafety::CapitalExposureGuardInput unavailableMargin = capitalGuard;
    unavailableMargin.availableUsdt = 10.0;
    const NativeOrderSafety::CapitalExposureGuardResult unavailableBlocked =
        NativeOrderSafety::guardFuturesCapitalExposure(unavailableMargin);
    check(!unavailableBlocked.allowed
              && unavailableBlocked.reason == QStringLiteral("capital guard: requested margin exceeds available USDT"),
          QStringLiteral("C++ capital guard should block unavailable margin like Python"));

    NativeOrderSafety::CapitalExposureGuardInput liveMinimum = capitalGuard;
    liveMinimum.positionPctFraction = 0.0001;
    liveMinimum.requestedQuantity = 0.0001;
    liveMinimum.normalizedQuantity = 0.05;
    liveMinimum.filters.minNotional = 5.0;
    liveMinimum.liveMode = true;
    const NativeOrderSafety::CapitalExposureGuardResult liveMinimumBlocked =
        NativeOrderSafety::guardFuturesCapitalExposure(liveMinimum);
    check(!liveMinimumBlocked.allowed
              && liveMinimumBlocked.reason.contains(QStringLiteral("live auto-bump")),
          QStringLiteral("C++ capital guard should require explicit live minimum-order auto-bump opt-in"));
    liveMinimum.liveAllowAutoBumpToMinOrder = true;
    const NativeOrderSafety::CapitalExposureGuardResult liveMinimumAllowed =
        NativeOrderSafety::guardFuturesCapitalExposure(liveMinimum);
    check(liveMinimumAllowed.allowed
              && std::abs(liveMinimumAllowed.quantityEstimate - 0.05) < 1e-12,
          QStringLiteral("C++ capital guard should allow explicitly opted-in funded minimum order"));

    NativeOrderSafety::CapitalExposureGuardInput addOnlyFlip = capitalGuard;
    addOnlyFlip.side = QStringLiteral("SELL");
    addOnlyFlip.dualSide = false;
    addOnlyFlip.addOnly = true;
    addOnlyFlip.netPositionAmt = 0.5;
    const NativeOrderSafety::CapitalExposureGuardResult addOnlyResult =
        NativeOrderSafety::guardFuturesCapitalExposure(addOnlyFlip);
    check(addOnlyResult.allowed && addOnlyResult.reduceOnly
              && std::abs(addOnlyResult.quantityEstimate - 0.5) < 1e-12
              && addOnlyResult.desiredPositionSide.isEmpty(),
          QStringLiteral("C++ capital guard should convert one-way add-only flips into reduce-only orders"));

    NativeOrderSafety::ConnectorOrderCircuitBreaker connectorCircuit(
        NativeOrderSafety::ConnectorOrderCircuitConfig{true, 2, 60.0});
    const QDateTime circuitNow = QDateTime::fromString(QStringLiteral("2026-06-18T12:00:00.000Z"), Qt::ISODateWithMs);
    NativeOrderSafety::ConnectorOrderBlockEvent circuitEvent;
    circuitEvent.timestamp = circuitNow.toSecsSinceEpoch();
    circuitEvent.symbol = QStringLiteral("BTCUSDT");
    circuitEvent.interval = QStringLiteral("1m");
    circuitEvent.side = QStringLiteral("LONG");
    circuitEvent.connectorHealth = QStringLiteral("error");
    circuitEvent.connectorState = QStringLiteral("error");
    circuitEvent.connectorMessage = QStringLiteral("exchange timeout");
    check(connectorCircuit.recordConnectorOrderBlock(circuitEvent, circuitNow).isEmpty(),
          QStringLiteral("connector order circuit should remain closed below its threshold"));
    const QJsonObject circuitOpened = connectorCircuit.recordConnectorOrderBlock(circuitEvent, circuitNow.addSecs(1));
    check(circuitOpened.value(QStringLiteral("active")).toBool(false) && connectorCircuit.isOpen(),
          QStringLiteral("connector order circuit should open after repeated failed submissions"));
    const QJsonObject circuitReset = connectorCircuit.resetConnectorOrderCircuitBreaker(
        QStringLiteral("native-test"), true, QString(), circuitNow.addSecs(2));
    check(!circuitReset.value(QStringLiteral("active")).toBool(true) && !connectorCircuit.isOpen(),
          QStringLiteral("forced connector order circuit reset should restore entry eligibility"));

    const QJsonObject desktopEntrypoint = NativeStartupPackaging::desktopEntrypointContract();
    check(desktopEntrypoint.value(QStringLiteral("canonical_repo_path")).toString() == QStringLiteral("apps/desktop-pyqt/main.py"),
          QStringLiteral("native startup contract should mirror Python desktop canonical wrapper"));
    check(desktopEntrypoint.value(QStringLiteral("canonical_module")).toString() == QStringLiteral("app.desktop.product_main"),
          QStringLiteral("native startup contract should mirror Python desktop canonical module"));
    check(desktopEntrypoint.value(QStringLiteral("compatibility_notice")).toString().contains(QStringLiteral("Deprecated compatibility desktop entrypoint")),
          QStringLiteral("native startup contract should mirror Python desktop compatibility notice"));
    const QJsonObject serviceEntrypoint = NativeStartupPackaging::serviceEntrypointContract();
    check(serviceEntrypoint.value(QStringLiteral("canonical_repo_path")).toString() == QStringLiteral("apps/service-api/main.py"),
          QStringLiteral("native startup contract should mirror Python service canonical wrapper"));
    check(serviceEntrypoint.value(QStringLiteral("installed_command")).toString() == QStringLiteral("trading-bot-service"),
          QStringLiteral("native startup contract should mirror Python service installed command"));
    const QJsonObject cppStartupContract = NativeStartupPackaging::cppStartupPackagingContract();
    check(cppStartupContract.value(QStringLiteral("app_user_model_id")).toString() == QStringLiteral("TradingBot.Desktop.Cpp"),
          QStringLiteral("native startup contract should expose stable Windows AppUserModelID"));
    check(cppStartupContract.value(QStringLiteral("icon_resource")).toString() == QStringLiteral(":/app_icon.ico"),
          QStringLiteral("native startup contract should expose packaged icon resource"));
    check(!cppStartupContract.value(QStringLiteral("delegates_trading_execution_to_python")).toBool(true),
          QStringLiteral("native startup contract should not delegate implemented Binance execution to Python"));
    check(cppStartupContract.value(QStringLiteral("native_trading_execution_scope")).toString()
              == QStringLiteral("binance-spot-usds-and-coin-futures"),
          QStringLiteral("native startup contract should report its exact trading execution scope"));
    check(jsonArrayContains(
              cppStartupContract.value(QStringLiteral("startup_suppression_env")).toArray(),
              QStringLiteral("BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH")),
          QStringLiteral("native startup contract should require shell shortcut suppression env"));
    check(NativeStartupPackaging::startupSuppressionEnvIsRequired(QStringLiteral("BOT_DISABLE_PYTHONW_RELAUNCH")),
          QStringLiteral("native startup contract should require pythonw relaunch suppression env"));
    check(jsonArrayContains(
              cppStartupContract.value(QStringLiteral("release_smoke_commands")).toArray(),
              QStringLiteral("build/binance_cpp/Release/Trading-Bot-C++.exe --smoke")),
          QStringLiteral("native startup contract should expose C++ release smoke command"));

    check(NativeChartHeatmap::canonicalizeChartInterval(QStringLiteral("60m")) == QStringLiteral("1h"),
          QStringLiteral("native chart interval canonicalization should collapse minute aliases like Python"));
    check(NativeChartHeatmap::mapTradingViewInterval(QStringLiteral("1M")) == QStringLiteral("1M"),
          QStringLiteral("native chart TradingView interval mapping should preserve uppercase month alias"));
    check(NativeChartHeatmap::mapTradingViewInterval(QStringLiteral("2 years")) == QStringLiteral("24M"),
          QStringLiteral("native chart TradingView interval mapping should support year aliases"));
    const QJsonObject chartState = NativeChartHeatmap::buildChartStatePayload(
        QStringLiteral("futures"),
        QStringLiteral("btcusdt"),
        QStringLiteral("60m"),
        QStringLiteral("TradingView"),
        true);
    check(chartState.value(QStringLiteral("market")).toString() == QStringLiteral("Futures"),
          QStringLiteral("native chart state should normalize market like Python"));
    check(chartState.value(QStringLiteral("symbol")).toString() == QStringLiteral("BTCUSDT.P"),
          QStringLiteral("native chart state should display futures symbols with .P like Python"));
    check(chartState.value(QStringLiteral("api_symbol")).toString() == QStringLiteral("BTCUSDT"),
          QStringLiteral("native chart state should resolve futures display symbols for API calls"));
    check(chartState.value(QStringLiteral("interval")).toString() == QStringLiteral("1h"),
          QStringLiteral("native chart state should canonicalize interval aliases"));
    check(chartState.value(QStringLiteral("tradingview_interval")).toString() == QStringLiteral("60"),
          QStringLiteral("native chart state should expose TradingView interval code"));
    check(chartState.value(QStringLiteral("tradingview_symbol")).toString() == QStringLiteral("BINANCE:BTCUSDT"),
          QStringLiteral("native chart state should expose TradingView symbol"));
    check(chartState.value(QStringLiteral("default_symbols")).toArray().contains(QStringLiteral("BTCUSDT")),
          QStringLiteral("native chart state should expose Python default chart symbols"));
    const QJsonObject lightweightPayload = NativeChartHeatmap::buildLightweightPayload(
        QJsonArray{
            QJsonObject{
                {QStringLiteral("time"), 1},
                {QStringLiteral("open"), 100.0},
                {QStringLiteral("high"), 110.0},
                {QStringLiteral("low"), 90.0},
                {QStringLiteral("close"), 105.0},
                {QStringLiteral("volume"), 12.0},
            },
            QJsonObject{
                {QStringLiteral("time"), 2},
                {QStringLiteral("open"), 105.0},
                {QStringLiteral("high"), 106.0},
                {QStringLiteral("low"), 95.0},
                {QStringLiteral("close"), 96.0},
                {QStringLiteral("volume"), 7.5},
            },
        },
        QStringList{QStringLiteral("volume")},
        QStringLiteral("Light"));
    check(lightweightPayload.value(QStringLiteral("theme")).toString() == QStringLiteral("light"),
          QStringLiteral("native lightweight chart payload should normalize light theme"));
    check(lightweightPayload.value(QStringLiteral("volume")).toArray().at(0).toObject().value(QStringLiteral("color")).toString() == QStringLiteral("#0ebb7a"),
          QStringLiteral("native lightweight chart payload should color rising volume like Python"));
    check(lightweightPayload.value(QStringLiteral("volume")).toArray().at(1).toObject().value(QStringLiteral("color")).toString() == QStringLiteral("#f75467"),
          QStringLiteral("native lightweight chart payload should color falling volume like Python"));
    const QStringList chartAssetSources = NativeChartHeatmap::lightweightAssetSources(true);
    check(chartAssetSources.size() == 3 && chartAssetSources.at(0).startsWith(QStringLiteral("file://")),
          QStringLiteral("native lightweight asset sources should prefer local asset before CDNs"));
    check(chartAssetSources.at(1).contains(QStringLiteral("unpkg.com/lightweight-charts")),
          QStringLiteral("native lightweight asset sources should include unpkg fallback"));
    check(chartAssetSources.at(2).contains(QStringLiteral("cdn.jsdelivr.net/npm/lightweight-charts")),
          QStringLiteral("native lightweight asset sources should include jsdelivr fallback"));
    const QJsonObject chartGuard = NativeChartHeatmap::buildChartViewModeGuardDecision(
        QStringLiteral("lightweight"),
        true,
        false);
    check(chartGuard.value(QStringLiteral("actual_mode")).toString() == QStringLiteral("original"),
          QStringLiteral("native chart safe-mode guard should fall back to original"));
    check(chartGuard.value(QStringLiteral("status_message")).toString().contains(QStringLiteral("BOT_SAFE_CHART_TAB=0")),
          QStringLiteral("native chart safe-mode guard should use Python status guidance"));
    const QJsonArray heatmapProviders = NativeChartHeatmap::liquidationHeatmapProviders();
    check(heatmapProviders.size() == 8,
          QStringLiteral("native heatmap provider catalog should mirror Python provider count"));
    bool hasCoinank = false;
    bool hasHyperliquid = false;
    for (const QJsonValue &providerValue : heatmapProviders) {
        const QJsonObject provider = providerValue.toObject();
        hasCoinank = hasCoinank
            || (provider.value(QStringLiteral("label")).toString() == QStringLiteral("Coinank")
                && provider.value(QStringLiteral("url")).toString() == QStringLiteral("https://coinank.com/chart/derivatives/liq-heat-map"));
        hasHyperliquid = hasHyperliquid
            || (provider.value(QStringLiteral("label")).toString() == QStringLiteral("Hyperliquid Map")
                && provider.value(QStringLiteral("url")).toString() == QStringLiteral("https://www.coinglass.com/hyperliquid-liquidation-map"));
    }
    check(hasCoinank, QStringLiteral("native heatmap provider catalog should include Coinank URL"));
    check(hasHyperliquid, QStringLiteral("native heatmap provider catalog should include Hyperliquid URL"));

    check(NativeDesktopShell::primaryTabTitles() == QStringList{
              QStringLiteral("Dashboard"),
              QStringLiteral("Chart"),
              QStringLiteral("Positions"),
              QStringLiteral("Backtest"),
              QStringLiteral("Liquidation Heatmap"),
              QStringLiteral("Code Languages"),
          },
          QStringLiteral("native desktop shell should mirror Python primary tab order"));
    check(NativeDesktopShell::lazySecondaryTabKeys() == QStringList{
              QStringLiteral("backtest"),
              QStringLiteral("liquidation"),
              QStringLiteral("code"),
          },
          QStringLiteral("native desktop shell should mirror Python lazy secondary tab keys"));
    check(NativeDesktopShell::lazySecondaryTabLoadDelayMs(QStringLiteral("code"), QStringLiteral("win32")) == 90,
          QStringLiteral("native desktop shell should mirror Windows code-tab lazy delay"));
    check(NativeDesktopShell::lazySecondaryTabLoadDelayMs(QStringLiteral("code"), QStringLiteral("win32"), QStringLiteral("1500")) == 1000,
          QStringLiteral("native desktop shell should clamp code-tab lazy delay"));
    check(NativeDesktopShell::lazySecondaryTabPrewarmEnabled(QStringLiteral("win32"), QStringLiteral("true")),
          QStringLiteral("native desktop shell should honor lazy prewarm flag on Windows"));
    const QJsonObject desktopStartup = NativeDesktopShell::buildDesktopStartupContract(
        QStringLiteral("win32"),
        QStringLiteral("1"));
    check(desktopStartup.value(QStringLiteral("startup_tab")).toString() == QStringLiteral("Dashboard"),
          QStringLiteral("native desktop shell startup contract should start on dashboard"));
    check(desktopStartup.value(QStringLiteral("lazy_property")).toString() == QStringLiteral("_bot_lazy_secondary_tab_key"),
          QStringLiteral("native desktop shell should mirror Python lazy tab property"));
    check(desktopStartup.value(QStringLiteral("prewarm_keys")).toArray().at(0).toString() == QStringLiteral("code"),
          QStringLiteral("native desktop shell should mirror Python lazy prewarm queue order"));
    const QJsonObject codeActivation = NativeDesktopShell::buildTabActivationEffect(
        QStringLiteral("code"),
        {},
        false,
        false,
        true);
    check(codeActivation.value(QStringLiteral("start_dependency_usage_auto_poll")).toBool(false),
          QStringLiteral("native desktop shell code tab should start dependency usage polling"));
    check(codeActivation.value(QStringLiteral("maybe_auto_prepare_cpp_environment")).toBool(false),
          QStringLiteral("native desktop shell code tab should auto-prepare C++ environment when selected"));
    const QJsonObject chartActivation = NativeDesktopShell::buildTabActivationEffect(
        QStringLiteral("chart"),
        QStringLiteral("tradingview"),
        true,
        true,
        false);
    check(chartActivation.value(QStringLiteral("safe_mode_redirect")).toBool(false),
          QStringLiteral("native desktop shell chart tab should mirror Python safe-mode redirect"));
    check(chartActivation.value(QStringLiteral("defer_after_code_switch")).toBool(false),
          QStringLiteral("native desktop shell chart tab should defer after code switch"));
    const QJsonObject greenTheme = NativeDesktopShell::normalizeDesktopTheme(QStringLiteral("gren"));
    check(greenTheme.value(QStringLiteral("stored_name")).toString() == QStringLiteral("Green"),
          QStringLiteral("native desktop shell should preserve Python gren->green compatibility"));
    check(greenTheme.value(QStringLiteral("chart_theme")).toString() == QStringLiteral("dark"),
          QStringLiteral("native desktop shell should forward accent themes as dark chart theme"));
    const QJsonObject cppShellOwnership = NativeDesktopShell::cppDesktopShellOwnershipContract();
    check(cppShellOwnership.value(QStringLiteral("owns_desktop_tab_lifecycle")).toBool(false),
          QStringLiteral("native desktop shell should own the C++ tab lifecycle"));
    check(cppShellOwnership.value(QStringLiteral("owns_trading_execution")).toBool(false),
          QStringLiteral("native desktop shell should own its implemented Binance trading paths"));
    check(cppShellOwnership.value(QStringLiteral("native_trading_execution_scope")).toString()
              == QStringLiteral("binance-spot-usds-and-coin-futures"),
          QStringLiteral("native desktop shell should bound native execution ownership to implemented Binance markets"));

    const QJsonObject supportedExchange = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            QStringLiteral("Binance"),
            NativeExchangeConnectors::defaultConnectorBackend(),
            {},
        });
    check(supportedExchange.value(QStringLiteral("trading_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept default Binance connector"));
    check(supportedExchange.value(QStringLiteral("order_execution_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose Binance order execution"));
    check(jsonArrayContains(
              supportedExchange.value(QStringLiteral("supported_connector_backends")).toArray(),
              QStringLiteral("ccxt")),
          QStringLiteral("native exchange support payload should expose Python connector backend catalog"));
    const QJsonObject ccxtDiagnosticsExchange = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            QStringLiteral("Bybit"),
            QStringLiteral("ccxt"),
            {},
        });
    check(ccxtDiagnosticsExchange.value(QStringLiteral("exchange_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept Python ccxt diagnostic venues"));
    check(ccxtDiagnosticsExchange.value(QStringLiteral("market_data_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose ccxt market-data diagnostics"));
    check(ccxtDiagnosticsExchange.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose ccxt order routing"));
    check(ccxtDiagnosticsExchange.value(QStringLiteral("order_execution_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose ccxt order execution routing"));
    check(ccxtDiagnosticsExchange.value(QStringLiteral("live_evidence_required")).toBool(false),
          QStringLiteral("native exchange support payload should require live evidence for ccxt venues"));
    const QJsonObject oandaBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("oanda-rest"),
            QStringLiteral("OANDA"),
        });
    check(oandaBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept OANDA broker routing"));
    check(oandaBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose OANDA order routing"));
    check(oandaBroker.value(QStringLiteral("live_evidence_required")).toBool(false),
          QStringLiteral("native exchange support payload should require live evidence for OANDA"));
    const QJsonObject fxcmBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("fxcmpy"),
            QStringLiteral("FXCM"),
        });
    check(fxcmBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept FXCM broker routing"));
    check(fxcmBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose FXCM order routing"));
    check(fxcmBroker.value(QStringLiteral("live_evidence_required")).toBool(false),
          QStringLiteral("native exchange support payload should require live evidence for FXCM"));
    const QJsonObject igBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("ig-rest"),
            QStringLiteral("IG"),
        });
    check(igBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept IG broker routing"));
    check(igBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose IG order routing"));
    check(igBroker.value(QStringLiteral("live_evidence_required")).toBool(false),
          QStringLiteral("native exchange support payload should require live evidence for IG"));
    const QJsonObject aiGoldAlias = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("metatrader5"),
            QStringLiteral("AI Gold"),
        });
    check(aiGoldAlias.value(QStringLiteral("selected_forex_broker")).toString()
              == QStringLiteral("AI Gold Securities"),
          QStringLiteral("native exchange support payload should canonicalize Python broker aliases"));
    check(aiGoldAlias.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should route canonicalized AI Gold"));
    check(aiGoldAlias.value(QStringLiteral("broker_market_scope")).toString()
              == QStringLiteral("otc-commodity-derivatives"),
          QStringLiteral("native exchange support payload should preserve canonical broker scope"));
    check(!aiGoldAlias.value(QStringLiteral("forex_order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload should preserve canonical non-forex scope"));
    const QJsonObject phillipAlias = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("metatrader5"),
            QStringLiteral("Philip Securities"),
        });
    check(phillipAlias.value(QStringLiteral("selected_forex_broker")).toString()
              == QStringLiteral("PhillipCapital (Phillip Nova)"),
          QStringLiteral("native exchange support payload should canonicalize the Python Philip alias"));
    check(phillipAlias.value(QStringLiteral("order_execution_supported")).toBool(false),
          QStringLiteral("native exchange support payload should route canonicalized Philip"));
    const QJsonObject brokerBackends = igBroker.value(QStringLiteral("broker_order_routing_backends")).toObject();
    int mt5BrokerCount = 0;
    for (const QJsonValue &brokerValue : igBroker.value(QStringLiteral("supported_forex_brokers")).toArray()) {
        const QString broker = brokerValue.toString();
        const QString backend = brokerBackends.value(NativeExchangeConnectors::supportKey(broker)).toString();
        if (backend != QStringLiteral("metatrader5")) {
            continue;
        }
        ++mt5BrokerCount;
        const QJsonObject mt5Broker = NativeExchangeConnectors::buildExchangeSupportPayload(
            NativeExchangeConnectors::ExchangeSupportInput{
                {},
                QStringLiteral("metatrader5"),
                broker,
            });
        check(mt5Broker.value(QStringLiteral("broker_supported")).toBool(false),
              QStringLiteral("native exchange support payload should accept %1 MT5 routing").arg(broker));
        check(mt5Broker.value(QStringLiteral("order_routing_supported")).toBool(false),
              QStringLiteral("native exchange support payload should expose %1 MT5 order routing").arg(broker));
        check(mt5Broker.value(QStringLiteral("order_execution_supported")).toBool(false),
              QStringLiteral("native exchange support payload should expose %1 MT5 execution routing").arg(broker));
        check(mt5Broker.value(QStringLiteral("live_evidence_required")).toBool(false),
              QStringLiteral("native exchange support payload should require live evidence for %1").arg(broker));
    }
    check(mt5BrokerCount >= 34,
          QStringLiteral("native exchange support payload should consume the complete generated MT5 broker catalog"));
    int mt4BrokerCount = 0;
    for (const QJsonValue &brokerValue : igBroker.value(QStringLiteral("supported_forex_brokers")).toArray()) {
        const QString broker = brokerValue.toString();
        const QString backend = brokerBackends.value(NativeExchangeConnectors::supportKey(broker)).toString();
        if (backend != QStringLiteral("metatrader4-bridge")) {
            continue;
        }
        ++mt4BrokerCount;
        const QJsonObject mt4Broker = NativeExchangeConnectors::buildExchangeSupportPayload(
            NativeExchangeConnectors::ExchangeSupportInput{
                {},
                QStringLiteral("metatrader4-bridge"),
                broker,
            });
        check(mt4Broker.value(QStringLiteral("broker_supported")).toBool(false),
              QStringLiteral("native exchange support payload should accept %1 MT4 bridge routing").arg(broker));
        check(mt4Broker.value(QStringLiteral("order_routing_supported")).toBool(false),
              QStringLiteral("native exchange support payload should expose %1 MT4 order routing").arg(broker));
        check(mt4Broker.value(QStringLiteral("forex_order_routing_supported")).toBool(false),
              QStringLiteral("native exchange support payload should retain %1 forex scope").arg(broker));
        check(mt4Broker.value(QStringLiteral("live_evidence_required")).toBool(false),
              QStringLiteral("native exchange support payload should evidence-gate %1").arg(broker));
    }
    check(mt4BrokerCount == 3,
          QStringLiteral("native exchange support payload should consume all generated MT4 bridge brokers"));
    const QJsonObject trading212Broker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("trading212-public-api"),
            QStringLiteral("Trading 212"),
        });
    check(trading212Broker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept Trading 212 broker routing"));
    check(trading212Broker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose Trading 212 equity order routing"));
    check(!trading212Broker.value(QStringLiteral("forex_order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload must not claim Trading 212 forex routing"));
    check(trading212Broker.value(QStringLiteral("broker_market_scope")).toString()
              == QStringLiteral("invest-and-stocks-isa-equities-only"),
          QStringLiteral("native exchange support payload should retain Trading 212 public API scope"));
    check(jsonArrayContains(
              trading212Broker.value(QStringLiteral("supported_brokers")).toArray(),
              QStringLiteral("Trading 212")),
          QStringLiteral("native exchange support payload should include Trading 212 in general brokers"));
    check(!jsonArrayContains(
              trading212Broker.value(QStringLiteral("supported_forex_brokers")).toArray(),
              QStringLiteral("Trading 212")),
          QStringLiteral("native exchange support payload must keep Trading 212 outside forex brokers"));
    const QJsonObject moomooBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("moomoo-opend"),
            QStringLiteral("moomoo"),
        });
    check(moomooBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept moomoo OpenD routing"));
    check(moomooBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose moomoo order routing"));
    check(!moomooBroker.value(QStringLiteral("forex_order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload must not claim moomoo forex routing"));
    check(moomooBroker.value(QStringLiteral("broker_market_scope")).toString()
              == QStringLiteral("stocks-etfs-options-futures-funds-and-supported-crypto"),
          QStringLiteral("native exchange support payload should retain moomoo market scope"));
    const QJsonObject stoneXBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("metatrader5"),
            QStringLiteral("StoneX"),
        });
    check(stoneXBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept StoneX MT5 routing"));
    check(stoneXBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose StoneX futures routing"));
    check(!stoneXBroker.value(QStringLiteral("forex_order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload must not claim StoneX forex routing"));
    check(stoneXBroker.value(QStringLiteral("broker_market_scope")).toString()
              == QStringLiteral("futures-and-options-on-futures"),
          QStringLiteral("native exchange support payload should retain StoneX futures scope"));
    check(jsonArrayContains(
              stoneXBroker.value(QStringLiteral("supported_brokers")).toArray(),
              QStringLiteral("StoneX")),
          QStringLiteral("native exchange support payload should include StoneX in general brokers"));
    check(!jsonArrayContains(
              stoneXBroker.value(QStringLiteral("supported_forex_brokers")).toArray(),
              QStringLiteral("StoneX")),
          QStringLiteral("native exchange support payload must keep StoneX outside forex brokers"));
    const QJsonObject aiGoldBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("metatrader5"),
            QStringLiteral("AI Gold Securities"),
        });
    check(aiGoldBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept AI Gold MT5 routing"));
    check(aiGoldBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose AI Gold commodity routing"));
    check(!aiGoldBroker.value(QStringLiteral("forex_order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload must not claim AI Gold forex routing"));
    check(aiGoldBroker.value(QStringLiteral("broker_market_scope")).toString()
              == QStringLiteral("otc-commodity-derivatives"),
          QStringLiteral("native exchange support payload should retain AI Gold commodity scope"));
    const QJsonObject citicBroker = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("citic-ctp"),
            QStringLiteral("CITIC Futures"),
        });
    check(citicBroker.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should accept CITIC Futures CTP routing"));
    check(citicBroker.value(QStringLiteral("order_routing_supported")).toBool(false),
          QStringLiteral("native exchange support payload should expose CITIC Futures order routing"));
    check(!citicBroker.value(QStringLiteral("forex_order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload must not claim CITIC Futures forex routing"));
    check(citicBroker.value(QStringLiteral("broker_market_scope")).toString()
              == QStringLiteral("china-futures-and-options"),
          QStringLiteral("native exchange support payload should retain CITIC Futures scope"));
    check(jsonArrayContains(
              citicBroker.value(QStringLiteral("supported_brokers")).toArray(),
              QStringLiteral("CITIC Futures")),
          QStringLiteral("native exchange support payload should include CITIC Futures in general brokers"));
    check(!jsonArrayContains(
              citicBroker.value(QStringLiteral("supported_forex_brokers")).toArray(),
              QStringLiteral("CITIC Futures")),
          QStringLiteral("native exchange support payload must keep CITIC Futures outside forex brokers"));
    const QJsonObject wrongBrokerBackend = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            {},
            QStringLiteral("ccxt"),
            QStringLiteral("IG"),
        });
    check(wrongBrokerBackend.value(QStringLiteral("broker_supported")).toBool(false),
          QStringLiteral("native exchange support payload should recognize IG with wrong backend"));
    check(!wrongBrokerBackend.value(QStringLiteral("order_routing_supported")).toBool(true),
          QStringLiteral("native exchange support payload should reject generic broker backend"));
    const QJsonObject unsupportedExchange = NativeExchangeConnectors::buildExchangeSupportPayload(
        NativeExchangeConnectors::ExchangeSupportInput{
            QStringLiteral("Unlisted"),
            QStringLiteral("custom-native"),
            {},
        });
    check(!unsupportedExchange.value(QStringLiteral("trading_supported")).toBool(true),
          QStringLiteral("native exchange support payload should reject non-Python exchange/backend/broker"));
    check(jsonArrayContains(
              unsupportedExchange.value(QStringLiteral("unsupported_reasons")).toArray(),
              QStringLiteral("Exchange 'Unlisted' is not implemented by this runtime.")),
          QStringLiteral("native exchange support payload should report unsupported exchanges like Python"));
    check(NativeExchangeConnectors::estimateRequestWeight(QStringLiteral("/fapi/v1/exchangeInfo")) == 10.0,
          QStringLiteral("native connector request weight should match Python exchangeInfo weight"));
    check(NativeExchangeConnectors::estimateRequestWeight(QStringLiteral("/fapi/v1/ticker/price")) == 1.0,
          QStringLiteral("native connector request weight should match Python ticker price weight"));
    const QJsonObject testnetLimiter = NativeExchangeConnectors::limiterSettingsFor(
        NativeExchangeConnectors::environmentTag(QStringLiteral("Demo/Testnet")),
        NativeExchangeConnectors::accountTag(QStringLiteral("Futures")));
    check(testnetLimiter.value(QStringLiteral("max_per_minute")).toDouble() == 180.0,
          QStringLiteral("native connector limiter should match Python testnet max_per_minute"));
    const QJsonObject spotLimiter = NativeExchangeConnectors::limiterSettingsFor(
        QStringLiteral("live"),
        NativeExchangeConnectors::accountTag(QStringLiteral("Spot")));
    check(spotLimiter.value(QStringLiteral("min_interval")).toDouble() == 0.25,
          QStringLiteral("native connector limiter should match Python spot min_interval"));
    const QJsonObject banBackoff = NativeExchangeConnectors::buildHttpBackoff(
        418,
        -1003,
        QStringLiteral("IP banned until 1770000100000"),
        -1.0,
        1770000000.0);
    check(banBackoff.value(QStringLiteral("triggered")).toBool(false),
          QStringLiteral("native connector backoff should trigger on Binance ban"));
    check(banBackoff.value(QStringLiteral("seconds_until_unban")).toDouble() == 100.0,
          QStringLiteral("native connector backoff should parse millisecond ban epoch"));
    const QJsonObject retryBackoff = NativeExchangeConnectors::buildHttpBackoff(
        429,
        0,
        QStringLiteral("Too many requests"),
        12.5,
        1770000000.0);
    check(retryBackoff.value(QStringLiteral("seconds_until_unban")).toDouble() == 12.5,
          QStringLiteral("native connector backoff should honor Retry-After seconds"));
    const QJsonObject connectorHealth = NativeExchangeConnectors::buildConnectorHealthSnapshot(QJsonObject{
        {QStringLiteral("credentials_present"), true},
        {QStringLiteral("connector_backend"), QStringLiteral("binance-sdk-spot")},
        {QStringLiteral("account_type"), QStringLiteral("Spot")},
        {QStringLiteral("mode"), QStringLiteral("Live")},
        {QStringLiteral("seconds_until_unban"), 12.5},
        {QStringLiteral("generated_at"), 1770000000.0},
        {QStringLiteral("last_error"), QJsonObject{
            {QStringLiteral("category"), QStringLiteral("rate_limited")},
            {QStringLiteral("message"), QStringLiteral("Too many requests signature=leaked")},
            {QStringLiteral("retryable"), true},
        }},
    });
    check(connectorHealth.value(QStringLiteral("health")).toString() == QStringLiteral("warning"),
          QStringLiteral("native connector health should warn while rate limited"));
    check(connectorHealth.value(QStringLiteral("state")).toString() == QStringLiteral("rate_limited"),
          QStringLiteral("native connector health should expose rate_limited state"));
    check(connectorHealth.value(QStringLiteral("last_error")).toObject().value(QStringLiteral("message")).toString().contains(QStringLiteral("<redacted>")),
          QStringLiteral("native connector health should redact diagnostic error text"));
    check(!QString::fromUtf8(QJsonDocument(connectorHealth).toJson(QJsonDocument::Compact)).contains(QStringLiteral("leaked")),
          QStringLiteral("native connector health should not leak secrets"));

    const QStringList indicatorKeys = NativeStrategyRuntime::indicatorOutputKeysFromConfig(QJsonObject{
        {QStringLiteral("rsi"), QJsonObject{{QStringLiteral("enabled"), QStringLiteral("false")}}},
        {QStringLiteral("ema"), QJsonObject{{QStringLiteral("enabled"), QStringLiteral("true")}}},
        {QStringLiteral("atr"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("natr"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("vwap"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("mfi"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("keltner"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("ichimoku"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("obv"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("rvol"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("cmf"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("cci"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("bbw"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("roc"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("trix"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("ppo"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("ao"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("kst"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("aroon"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("chop"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("stoch_rsi"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("willr"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("dmi"), QJsonObject{{QStringLiteral("enabled"), true}}},
        {QStringLiteral("stochastic"), QJsonObject{{QStringLiteral("enabled"), true}}},
    });
    check(!indicatorKeys.contains(QStringLiteral("rsi")),
          QStringLiteral("native strategy indicator output keys should respect false string enabled flag"));
    for (const QString &key : QStringList{
             QStringLiteral("ema"),
             QStringLiteral("atr"),
             QStringLiteral("natr"),
             QStringLiteral("vwap"),
             QStringLiteral("mfi"),
             QStringLiteral("keltner_upper"),
             QStringLiteral("ichimoku_tenkan"),
             QStringLiteral("ichimoku"),
             QStringLiteral("obv"),
             QStringLiteral("rvol"),
             QStringLiteral("cmf"),
             QStringLiteral("cci"),
             QStringLiteral("bbw"),
             QStringLiteral("roc"),
             QStringLiteral("trix"),
             QStringLiteral("ppo_hist"),
             QStringLiteral("ao"),
             QStringLiteral("kst_hist"),
             QStringLiteral("aroon_up"),
             QStringLiteral("chop"),
             QStringLiteral("stoch_rsi_k"),
             QStringLiteral("willr"),
             QStringLiteral("dmi_plus"),
             QStringLiteral("stochastic_d"),
         }) {
        check(indicatorKeys.contains(key), QStringLiteral("native strategy indicator output keys should include %1").arg(key));
    }

    QJsonObject allEnabledIndicatorConfigs;
    for (const auto &indicator : PythonParityContract::kPythonIndicatorCatalog) {
        const QString key = QString::fromUtf8(
            indicator.key.data(), static_cast<qsizetype>(indicator.key.size()));
        allEnabledIndicatorConfigs.insert(key, QJsonObject{{QStringLiteral("enabled"), true}});
    }
    const QStringList allIndicatorOutputKeys =
        NativeStrategyRuntime::indicatorOutputKeysFromConfig(allEnabledIndicatorConfigs);
    for (const auto &indicator : PythonParityContract::kPythonIndicatorCatalog) {
        const QString indicatorKey = QString::fromUtf8(
            indicator.key.data(), static_cast<qsizetype>(indicator.key.size()));
        const QStringList expectedOutputKeys = QString::fromUtf8(
            indicator.runtimeOutputKeysCsv.data(),
            static_cast<qsizetype>(indicator.runtimeOutputKeysCsv.size()))
            .split(QLatin1Char(','), Qt::SkipEmptyParts);
        check(!expectedOutputKeys.isEmpty(),
              QStringLiteral("Python indicator '%1' should declare runtime output keys").arg(indicatorKey));
        for (const QString &outputKey : expectedOutputKeys) {
            check(allIndicatorOutputKeys.contains(outputKey),
                  QStringLiteral("native strategy output keys should cover %1 -> %2")
                      .arg(indicatorKey, outputKey));
        }
    }

    NativeStrategyRuntime::StrategySignalInput signalInput;
    signalInput.closes = {100.0, 101.0, 106.0};
    signalInput.side = QStringLiteral("BUY");
    signalInput.useLiveValues = true;
    const auto mkRule = [](bool enabled, std::optional<double> buy, std::optional<double> sell) {
        NativeStrategyRuntime::IndicatorRule rule;
        rule.enabled = enabled;
        rule.buyValue = buy;
        rule.sellValue = sell;
        return rule;
    };
    signalInput.rules = {
        {QStringLiteral("rsi"), mkRule(true, 30.0, 70.0)},
        {QStringLiteral("natr"), mkRule(true, 2.0, 1.0)},
        {QStringLiteral("rvol"), mkRule(true, 1.5, 0.75)},
        {QStringLiteral("cci"), mkRule(true, -100.0, 100.0)},
        {QStringLiteral("bbw"), mkRule(true, 5.0, 2.0)},
        {QStringLiteral("roc"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("trix"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("ppo"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("ao"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("kst"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("aroon"), mkRule(true, 50.0, -50.0)},
        {QStringLiteral("chop"), mkRule(true, 38.2, 61.8)},
        {QStringLiteral("mfi"), mkRule(true, 20.0, 80.0)},
        {QStringLiteral("atr"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("vwap"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("cmf"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("obv"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("keltner"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("ichimoku"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("bb"), mkRule(true, std::nullopt, std::nullopt)},
    };
    signalInput.indicators = {
        {QStringLiteral("rsi"), {50.0, 25.0, 20.0}},
        {QStringLiteral("natr"), {0.5, 1.5, 2.5}},
        {QStringLiteral("rvol"), {0.9, 1.2, 1.6}},
        {QStringLiteral("cci"), {0.0, -120.0, -130.0}},
        {QStringLiteral("bbw"), {1.0, 4.0, 6.0}},
        {QStringLiteral("roc"), {-1.0, 0.5, 2.0}},
        {QStringLiteral("trix"), {-0.1, 0.2, 0.4}},
        {QStringLiteral("ppo"), {0.0, 0.5, 1.0}},
        {QStringLiteral("ppo_signal"), {0.0, 0.25, 0.5}},
        {QStringLiteral("ppo_hist"), {0.0, 0.25, 0.5}},
        {QStringLiteral("ao"), {-0.1, 0.2, 0.4}},
        {QStringLiteral("kst"), {0.0, 1.0, 2.0}},
        {QStringLiteral("kst_signal"), {0.0, 0.5, 1.0}},
        {QStringLiteral("kst_hist"), {0.0, 0.5, 1.0}},
        {QStringLiteral("aroon"), {0.0, 60.0, 80.0}},
        {QStringLiteral("aroon_up"), {50.0, 100.0, 100.0}},
        {QStringLiteral("aroon_down"), {50.0, 40.0, 20.0}},
        {QStringLiteral("chop"), {70.0, 45.0, 30.0}},
        {QStringLiteral("mfi"), {50.0, 18.0, 15.0}},
        {QStringLiteral("atr"), {1.0, 2.0, 3.0}},
        {QStringLiteral("vwap"), {100.0, 100.5, 101.5}},
        {QStringLiteral("cmf"), {0.1, 0.2, 0.25}},
        {QStringLiteral("obv"), {0.0, 1000.0, 2000.0}},
        {QStringLiteral("keltner_upper"), {103.0, 104.0, 105.0}},
        {QStringLiteral("keltner_mid"), {100.0, 101.0, 102.0}},
        {QStringLiteral("keltner_lower"), {97.0, 98.0, 99.0}},
        {QStringLiteral("ichimoku_tenkan"), {100.0, 101.0, 105.0}},
        {QStringLiteral("ichimoku_kijun"), {99.0, 100.0, 103.0}},
        {QStringLiteral("ichimoku_span_a"), {98.0, 100.0, 104.0}},
        {QStringLiteral("ichimoku_span_b"), {97.0, 99.0, 102.0}},
        {QStringLiteral("bb_upper"), {101.0, 104.0, 108.0}},
        {QStringLiteral("bb_mid"), {99.0, 101.0, 105.0}},
        {QStringLiteral("bb_lower"), {97.0, 98.0, 102.0}},
    };
    const QJsonObject signalDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    const QString signalDescription = signalDecision.value(QStringLiteral("description")).toString();
    check(signalDecision.value(QStringLiteral("signal")).toString() == QStringLiteral("BUY"),
          QStringLiteral("native strategy signal should choose first BUY trigger like Python"));
    check(signalDecision.value(QStringLiteral("trigger_sources")).toArray().at(0).toString() == QStringLiteral("rsi"),
          QStringLiteral("native strategy signal should preserve first trigger source"));
    for (const QString &fragment : QStringList{
             QStringLiteral("RSI=20.00"),
             QStringLiteral("NATR=2.5000"),
             QStringLiteral("RVOL >= 1.5000 -> BUY"),
             QStringLiteral("CCI <= -100.00 -> BUY"),
             QStringLiteral("BBW >= 5.0000 -> BUY"),
             QStringLiteral("ROC >= 0.00 -> BUY"),
             QStringLiteral("TRIX >= 0.0000 -> BUY"),
             QStringLiteral("PPO hist >= 0.0000 -> BUY"),
             QStringLiteral("AO >= 0.0000 -> BUY"),
             QStringLiteral("KST spread >= 0.0000 -> BUY"),
             QStringLiteral("Aroon >= 50.00 -> BUY"),
             QStringLiteral("CHOP <= 38.2000 -> BUY"),
             QStringLiteral("MFI <= 20.00 -> BUY"),
             QStringLiteral("ATR=3.00000000"),
             QStringLiteral("VWAP=101.50000000"),
             QStringLiteral("CMF=0.2500"),
             QStringLiteral("OBV=2000.00"),
             QStringLiteral("KC_up=105.00000000"),
             QStringLiteral("IC_tenkan=105.00000000"),
             QStringLiteral("close above cloud"),
             QStringLiteral("BB_up=108.00000000,BB_mid=105.00000000,BB_low=102.00000000"),
         }) {
        check(signalDescription.contains(fragment), QStringLiteral("native strategy signal description should include %1").arg(fragment));
    }
    const QStringList descriptionSegments = signalDescription.split(QStringLiteral(" | "));
    int previousDescriptionSegment = -1;
    for (const QString &prefix : QStringList{
             QStringLiteral("RSI="),
             QStringLiteral("ATR="),
             QStringLiteral("NATR="),
             QStringLiteral("VWAP="),
             QStringLiteral("MFI="),
             QStringLiteral("OBV="),
             QStringLiteral("RVOL="),
             QStringLiteral("CMF="),
             QStringLiteral("CCI="),
             QStringLiteral("ROC="),
             QStringLiteral("TRIX="),
             QStringLiteral("BBW="),
             QStringLiteral("PPO="),
             QStringLiteral("AO="),
             QStringLiteral("KST="),
             QStringLiteral("Aroon="),
             QStringLiteral("CHOP="),
             QStringLiteral("BB_up="),
             QStringLiteral("KC_up="),
             QStringLiteral("IC_tenkan="),
         }) {
        int currentDescriptionSegment = -1;
        for (int index = 0; index < descriptionSegments.size(); ++index) {
            if (descriptionSegments.at(index).startsWith(prefix)) {
                currentDescriptionSegment = index;
                break;
            }
        }
        if (currentDescriptionSegment >= 0) {
            check(currentDescriptionSegment > previousDescriptionSegment,
                  QStringLiteral("native strategy description order should match Python at %1").arg(prefix));
            previousDescriptionSegment = currentDescriptionSegment;
        }
    }
    signalInput.useLiveValues = false;
    signalInput.rules = {{QStringLiteral("rsi"), mkRule(true, 30.0, 70.0)}};
    signalInput.indicators = {{QStringLiteral("rsi"), {80.0, 20.0, 90.0}}};
    signalInput.closes = {100.0, 101.0, 102.0};
    const QJsonObject closedCandleDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    check(closedCandleDecision.value(QStringLiteral("trigger_price")).toDouble() == 101.0,
          QStringLiteral("native strategy signal should use closed candle trigger price when live values are disabled"));
    check(closedCandleDecision.value(QStringLiteral("description")).toString().contains(QStringLiteral("RSI=20.00")),
          QStringLiteral("native strategy signal should use previous indicator value when live values are disabled"));

    signalInput.useLiveValues = true;
    signalInput.side = QStringLiteral("BOTH");
    signalInput.rules = {{QStringLiteral("rsi"), mkRule(true, 30.0, 70.0)}};
    signalInput.indicators = {{QStringLiteral("rsi"), {20.0, std::numeric_limits<double>::infinity()}}};
    const QJsonObject nonFiniteRsiDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    check(nonFiniteRsiDecision.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("native strategy signal should skip non-finite RSI like Python"));
    check(nonFiniteRsiDecision.value(QStringLiteral("description")).toString() == QStringLiteral("RSI=NaN/inf skipped"),
          QStringLiteral("native strategy signal should describe skipped non-finite RSI like Python"));

    signalInput.closes = {100.0, std::numeric_limits<double>::quiet_NaN()};
    signalInput.rules = {{QStringLiteral("rsi"), mkRule(true, 30.0, 70.0)}};
    signalInput.indicators = {{QStringLiteral("rsi"), {50.0, 20.0}}};
    const QJsonObject nonFiniteCloseDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    check(nonFiniteCloseDecision.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("native strategy signal should reject non-finite candle closes like Python"));
    check(nonFiniteCloseDecision.value(QStringLiteral("description")).toString() == QStringLiteral("no data"),
          QStringLiteral("native strategy signal should report no data for non-finite candle closes"));
    check(nonFiniteCloseDecision.value(QStringLiteral("trigger_price")).isNull(),
          QStringLiteral("native strategy signal should omit a trigger price for non-finite candle closes"));

    signalInput.useLiveValues = true;
    signalInput.side = QStringLiteral("BOTH");
    signalInput.closes = {100.0, 101.0};
    signalInput.rules = {
        {QStringLiteral("atr"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("vwap"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("cmf"), mkRule(true, 0.2, std::nullopt)},
        {QStringLiteral("obv"), mkRule(true, 1500.0, std::nullopt)},
        {QStringLiteral("ppo"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("kst"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("aroon"), mkRule(true, 50.0, -50.0)},
    };
    const double nonFinite = std::numeric_limits<double>::infinity();
    signalInput.indicators = {
        {QStringLiteral("atr"), {1.0, nonFinite}},
        {QStringLiteral("vwap"), {100.0, nonFinite}},
        {QStringLiteral("cmf"), {0.0, nonFinite}},
        {QStringLiteral("obv"), {0.0, nonFinite}},
        {QStringLiteral("ppo"), {0.0, nonFinite}},
        {QStringLiteral("ppo_signal"), {0.0, nonFinite}},
        {QStringLiteral("ppo_hist"), {0.0, nonFinite}},
        {QStringLiteral("kst"), {0.0, nonFinite}},
        {QStringLiteral("kst_signal"), {0.0, nonFinite}},
        {QStringLiteral("kst_hist"), {0.0, nonFinite}},
        {QStringLiteral("aroon"), {0.0, nonFinite}},
        {QStringLiteral("aroon_up"), {0.0, nonFinite}},
        {QStringLiteral("aroon_down"), {0.0, nonFinite}},
    };
    const QJsonObject nonFiniteContextDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    const QString nonFiniteContextDescription = nonFiniteContextDecision.value(QStringLiteral("description")).toString();
    check(nonFiniteContextDecision.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("native strategy should not trigger from non-finite context indicators"));
    for (const QString &fragment : QStringList{
             QStringLiteral("ATR=NaN/inf skipped"),
             QStringLiteral("VWAP=NaN/inf skipped"),
             QStringLiteral("CMF=NaN/inf skipped"),
             QStringLiteral("OBV=NaN/inf skipped"),
             QStringLiteral("PPO=NaN/inf skipped"),
             QStringLiteral("KST=NaN/inf skipped"),
             QStringLiteral("Aroon=NaN/inf skipped"),
         }) {
        check(nonFiniteContextDescription.contains(fragment),
              QStringLiteral("native strategy should describe skipped non-finite %1 like Python").arg(fragment));
    }

    signalInput.rules = {
        {QStringLiteral("ma"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("bb"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("keltner"), mkRule(true, std::nullopt, std::nullopt)},
        {QStringLiteral("ichimoku"), mkRule(true, std::nullopt, std::nullopt)},
    };
    signalInput.indicators = {
        {QStringLiteral("ma"), {100.0, nonFinite}},
        {QStringLiteral("bb_upper"), {101.0, nonFinite}},
        {QStringLiteral("bb_mid"), {100.0, nonFinite}},
        {QStringLiteral("bb_lower"), {99.0, nonFinite}},
        {QStringLiteral("keltner_upper"), {101.0, nonFinite}},
        {QStringLiteral("keltner_mid"), {100.0, nonFinite}},
        {QStringLiteral("keltner_lower"), {99.0, nonFinite}},
        {QStringLiteral("ichimoku_tenkan"), {100.0, nonFinite}},
        {QStringLiteral("ichimoku_kijun"), {99.0, 100.0}},
        {QStringLiteral("ichimoku_span_a"), {98.0, nonFinite}},
        {QStringLiteral("ichimoku_span_b"), {97.0, nonFinite}},
    };
    const QJsonObject indexedInfinityDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    const QString indexedInfinityDescription = indexedInfinityDecision.value(QStringLiteral("description")).toString();
    check(indexedInfinityDecision.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("native strategy should not trigger from context-only indexed infinity values"));
    for (const QString &fragment : QStringList{
             QStringLiteral("MA_prev=100.00000000,MA_last=inf"),
             QStringLiteral("BB_up=inf,BB_mid=inf,BB_low=inf"),
             QStringLiteral("KC_up=inf,KC_mid=inf,KC_low=inf"),
             QStringLiteral("IC_tenkan=inf,IC_kijun=100.00000000"),
             QStringLiteral("cloud unavailable"),
         }) {
        check(indexedInfinityDescription.contains(fragment),
              QStringLiteral("native strategy should preserve indexed infinity context %1 like Python").arg(fragment));
    }

    signalInput.rules = {
        {QStringLiteral("ppo"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("kst"), mkRule(true, 0.0, 0.0)},
        {QStringLiteral("aroon"), mkRule(true, 50.0, -50.0)},
    };
    signalInput.indicators = {
        {QStringLiteral("ppo_hist"), {0.0, 1.0}},
        {QStringLiteral("kst_hist"), {0.0, 1.0}},
        {QStringLiteral("aroon"), {0.0, 60.0}},
    };
    const QJsonObject missingCompositeDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    const QString missingCompositeDescription = missingCompositeDecision.value(QStringLiteral("description")).toString();
    check(missingCompositeDecision.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("native strategy should not evaluate incomplete composite indicators"));
    for (const QString &fragment : QStringList{
             QStringLiteral("PPO error:ValueError('indicator series missing')"),
             QStringLiteral("KST error:ValueError('indicator series missing')"),
             QStringLiteral("Aroon error:ValueError('indicator series missing')"),
         }) {
        check(missingCompositeDescription.contains(fragment),
              QStringLiteral("native strategy should preserve Python missing composite diagnostic %1").arg(fragment));
    }

    signalInput.useLiveValues = true;
    signalInput.side = QStringLiteral("BOTH");
    signalInput.closes = {100.0, 101.0, 102.0};
    signalInput.rules = {
        {QStringLiteral("stoch_rsi"), mkRule(true, 20.0, 80.0)},
        {QStringLiteral("willr"), mkRule(true, -80.0, -20.0)},
        {QStringLiteral("cmf"), mkRule(true, 0.2, std::nullopt)},
        {QStringLiteral("obv"), mkRule(true, 1500.0, std::nullopt)},
        {QStringLiteral("ichimoku"), mkRule(true, 1.0, std::nullopt)},
    };
    signalInput.indicators = {
        {QStringLiteral("stoch_rsi_k"), {50.0, 15.0, 10.0}},
        {QStringLiteral("willr"), {-50.0, -85.0, -90.0}},
        {QStringLiteral("cmf"), {0.0, 0.1, 0.25}},
        {QStringLiteral("obv"), {0.0, 1000.0, 2000.0}},
        {QStringLiteral("ichimoku_tenkan"), {100.0, 101.0, 105.0}},
        {QStringLiteral("ichimoku_kijun"), {100.0, 100.0, 103.0}},
        {QStringLiteral("ichimoku_span_a"), {99.0, 100.0, 104.0}},
        {QStringLiteral("ichimoku_span_b"), {98.0, 99.0, 102.0}},
    };
    const QJsonObject expandedSignalDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    const QJsonObject expandedTriggerActions =
        expandedSignalDecision.value(QStringLiteral("trigger_actions")).toObject();
    check(expandedSignalDecision.value(QStringLiteral("signal")).toString() == QStringLiteral("BUY"),
          QStringLiteral("native strategy should preserve Python StochRSI first-trigger behavior"));
    for (const QString &source : QStringList{
             QStringLiteral("stoch_rsi"),
             QStringLiteral("willr"),
             QStringLiteral("cmf"),
             QStringLiteral("obv"),
             QStringLiteral("ichimoku"),
         }) {
        check(expandedTriggerActions.value(source).toString() == QStringLiteral("buy"),
              QStringLiteral("native strategy should emit Python-compatible one-sided BUY action for %1")
                  .arg(source));
    }

    signalInput.side = QStringLiteral("BOTH");
    signalInput.useLiveValues = true;
    signalInput.closes = {100.0, 101.0, 102.0};
    signalInput.rules = {
        {QStringLiteral("mfi"), mkRule(true, 20.0, 80.0)},
        {QStringLiteral("rvol"), mkRule(true, 1.5, 0.75)},
    };
    signalInput.indicators = {
        {QStringLiteral("mfi"), {50.0, 18.0, 15.0}},
        {QStringLiteral("rvol"), {0.9, 1.2, 1.6}},
    };
    const QJsonObject priorityDecision = NativeStrategyRuntime::buildSignalDecision(signalInput);
    check(priorityDecision.value(QStringLiteral("signal")).toString() == QStringLiteral("BUY"),
          QStringLiteral("native strategy should choose Python's first signal when multiple indicators trigger"));
    check(priorityDecision.value(QStringLiteral("trigger_sources")).toArray().at(0).toString()
              == QStringLiteral("mfi"),
          QStringLiteral("native strategy trigger source order should follow Python indicator priority"));

    const QJsonArray liveSignalCases = indicatorReference.value(QStringLiteral("live_signal_cases")).toArray();
    check(liveSignalCases.size() >= 44,
          QStringLiteral("generated Python fixture should cover BUY, SELL, BOTH, side-blocked, and closed-candle live signal behavior"));
    for (const QJsonValue &caseValue : liveSignalCases) {
        const QJsonObject liveCase = caseValue.toObject();
        const QString caseName = liveCase.value(QStringLiteral("name")).toString();
        NativeStrategyRuntime::StrategySignalInput liveInput;
        liveInput.side = liveCase.value(QStringLiteral("side")).toString();
        liveInput.useLiveValues = liveCase.value(QStringLiteral("use_live_values")).toBool();

        for (const QJsonValue &candleValue : liveCase.value(QStringLiteral("candles")).toArray()) {
            liveInput.closes.append(candleValue.toObject().value(QStringLiteral("close")).toDouble());
        }
        const QJsonObject configObject = liveCase.value(QStringLiteral("configs")).toObject();
        for (auto iterator = configObject.constBegin(); iterator != configObject.constEnd(); ++iterator) {
            const QJsonObject config = iterator.value().toObject();
            NativeStrategyRuntime::IndicatorRule rule;
            rule.enabled = config.value(QStringLiteral("enabled")).toBool();
            if (config.value(QStringLiteral("buy_value")).isDouble()) {
                rule.buyValue = config.value(QStringLiteral("buy_value")).toDouble();
            }
            if (config.value(QStringLiteral("sell_value")).isDouble()) {
                rule.sellValue = config.value(QStringLiteral("sell_value")).toDouble();
            }
            liveInput.rules.insert(iterator.key(), rule);
        }
        const QJsonObject indicatorObject = liveCase.value(QStringLiteral("indicators")).toObject();
        for (auto iterator = indicatorObject.constBegin(); iterator != indicatorObject.constEnd(); ++iterator) {
            QVector<double> values;
            const QJsonArray series = iterator.value().toArray();
            values.reserve(series.size());
            for (const QJsonValue &value : series) {
                values.append(value.isNull() ? std::numeric_limits<double>::quiet_NaN() : value.toDouble());
            }
            liveInput.indicators.insert(iterator.key(), values);
        }

        const QJsonObject expected = liveCase.value(QStringLiteral("expected")).toObject();
        const QJsonObject actual = NativeStrategyRuntime::buildSignalDecision(liveInput);
        const QJsonValue expectedSignal = expected.value(QStringLiteral("signal"));
        const QJsonValue actualSignal = actual.value(QStringLiteral("signal"));
        check((expectedSignal.isNull() && actualSignal.isNull())
                  || (!expectedSignal.isNull() && actualSignal.toString() == expectedSignal.toString()),
              QStringLiteral("native C++ live signal should match Python for %1").arg(caseName));
        check(actual.value(QStringLiteral("description")) == expected.value(QStringLiteral("description")),
              QStringLiteral("native C++ live signal description should match Python for %1").arg(caseName));
        const QJsonValue expectedPrice = expected.value(QStringLiteral("trigger_price"));
        const QJsonValue actualPrice = actual.value(QStringLiteral("trigger_price"));
        if (expectedPrice.isNull()) {
            check(actualPrice.isNull(),
                  QStringLiteral("native C++ live signal trigger price should be null like Python for %1")
                      .arg(caseName));
        } else {
            const double expectedNumber = expectedPrice.toDouble();
            const double actualNumber = actualPrice.toDouble();
            check(std::isfinite(actualNumber)
                      && std::abs(actualNumber - expectedNumber) <= 1e-9 * std::max(1.0, std::abs(expectedNumber)),
                  QStringLiteral("native C++ live signal trigger price should match Python for %1")
                      .arg(caseName));
        }
        check(actual.value(QStringLiteral("trigger_sources")) == expected.value(QStringLiteral("trigger_sources")),
              QStringLiteral("native C++ live signal trigger sources should match Python for %1").arg(caseName));
        check(actual.value(QStringLiteral("trigger_actions")) == expected.value(QStringLiteral("trigger_actions")),
              QStringLiteral("native C++ live signal trigger actions should match Python for %1").arg(caseName));
        check(actual.value(QStringLiteral("min_bars")).toInt() == expected.value(QStringLiteral("min_bars")).toInt(),
              QStringLiteral("native C++ live signal minimum bars should match Python for %1").arg(caseName));
        check(actual.value(QStringLiteral("signal_index_from_end")).toInt()
                  == expected.value(QStringLiteral("signal_index_from_end")).toInt(),
              QStringLiteral("native C++ live signal index should match Python for %1").arg(caseName));
    }

    const QJsonObject normalizedRuntimeControls = NativeStrategyRuntime::normalizeStrategyControls(
        QStringLiteral("runtime"),
        QJsonObject{
            {QStringLiteral("side"), QStringLiteral("buy")},
            {QStringLiteral("position_pct"), QStringLiteral("12.5")},
            {QStringLiteral("position_pct_units"), QStringLiteral("ratio")},
            {QStringLiteral("leverage"), QStringLiteral("3")},
            {QStringLiteral("loop_interval_override"), QStringLiteral(" 5 M ")},
            {QStringLiteral("add_only"), QStringLiteral("false")},
            {QStringLiteral("account_mode"), QStringLiteral("portfolio margin")},
            {QStringLiteral("connector_backend"), QStringLiteral("CCXT")},
            {QStringLiteral("stop_loss"), QJsonObject{
                {QStringLiteral("enabled"), QStringLiteral("true")},
                {QStringLiteral("mode"), QStringLiteral("both")},
                {QStringLiteral("scope"), QStringLiteral("bad")},
                {QStringLiteral("usdt"), QStringLiteral("50")},
                {QStringLiteral("percent"), QStringLiteral("2.5")},
            }},
        });
    check(normalizedRuntimeControls.value(QStringLiteral("side")).toString() == QStringLiteral("BUY"),
          QStringLiteral("native strategy controls should canonicalize runtime side"));
    check(normalizedRuntimeControls.value(QStringLiteral("position_pct_units")).toString() == QStringLiteral("fraction"),
          QStringLiteral("native strategy controls should normalize position units"));
    check(normalizedRuntimeControls.value(QStringLiteral("loop_interval_override")).toString() == QStringLiteral("5m"),
          QStringLiteral("native strategy controls should normalize loop override"));
    check(normalizedRuntimeControls.value(QStringLiteral("add_only")).toBool(false),
          QStringLiteral("native strategy controls should preserve Python truthiness for string add_only"));
    check(normalizedRuntimeControls.value(QStringLiteral("account_mode")).toString() == QStringLiteral("Portfolio Margin"),
          QStringLiteral("native strategy controls should normalize account mode"));
    check(normalizedRuntimeControls.value(QStringLiteral("connector_backend")).toString() == QStringLiteral("ccxt"),
          QStringLiteral("native strategy controls should normalize connector backend"));
    check(normalizedRuntimeControls.value(QStringLiteral("stop_loss")).toObject().value(QStringLiteral("scope")).toString() == QStringLiteral("per_trade"),
          QStringLiteral("native strategy controls should normalize invalid stop-loss scope"));

    check(qFuzzyCompare(
              NativeStrategyRuntime::positionPctFraction(
                  QJsonObject{{QStringLiteral("position_pct"), 25.0},
                              {QStringLiteral("position_pct_units"), QStringLiteral("percent")}},
                  2.0,
                  QStringLiteral("percent")),
              0.25),
          QStringLiteral("native runtime sizing should apply Python percent position units"));
    check(qFuzzyCompare(
              NativeStrategyRuntime::positionPctFraction(
                  QJsonObject{{QStringLiteral("position_pct"), 0.4},
                              {QStringLiteral("position_pct_units"), QStringLiteral("ratio")}},
                  2.0,
                  QStringLiteral("percent")),
              0.4),
          QStringLiteral("native runtime sizing should apply Python ratio position units"));
    check(qFuzzyCompare(
              NativeStrategyRuntime::positionPctFraction(
                  QJsonObject{{QStringLiteral("position_pct"), 0.4}},
                  2.0,
                  QStringLiteral("percent")),
              0.004),
          QStringLiteral("native runtime sizing should fall back to the Python global position units"));

    const QJsonObject normalizedBacktestControls = NativeStrategyRuntime::normalizeStrategyControls(
        QStringLiteral("backtest"),
        QJsonObject{
            {QStringLiteral("loop_interval_override"), QStringLiteral(" 1 h ")},
            {QStringLiteral("leverage"), QStringLiteral("3")},
        });
    check(normalizedBacktestControls.value(QStringLiteral("loop_interval_override")).toString() == QStringLiteral("1h"),
          QStringLiteral("native backtest controls should preserve Python loop interval overrides"));

    const QJsonObject normalizedRiskControls = NativeStrategyRuntime::normalizeStrategyRiskControls(
        QJsonObject{
            {QStringLiteral("indicator_use_live_values"), QStringLiteral("true")},
            {QStringLiteral("allow_opposite_positions"), false},
            {QStringLiteral("indicator_flip_cooldown_bars"), QStringLiteral("4")},
            {QStringLiteral("positions_missing_grace_seconds"), QStringLiteral("12.75")},
            {QStringLiteral("stop_loss"), QJsonObject{
                {QStringLiteral("enabled"), QStringLiteral("true")},
                {QStringLiteral("mode"), QStringLiteral("both")},
                {QStringLiteral("scope"), QStringLiteral("entire_account")},
                {QStringLiteral("percent"), QStringLiteral("2.5")},
            }},
        });
    check(normalizedRiskControls.value(QStringLiteral("indicator_use_live_values")).toBool(),
          QStringLiteral("C++ native risk normalization should consume Python live-candle controls"));
    check(!normalizedRiskControls.value(QStringLiteral("allow_opposite_positions")).toBool(),
          QStringLiteral("C++ native risk normalization should consume Python opposite-position controls"));
    check(normalizedRiskControls.value(QStringLiteral("indicator_flip_cooldown_bars")).toInt() == 4,
          QStringLiteral("C++ native risk normalization should preserve Python cooldown bars"));
    check(qFuzzyCompare(
              normalizedRiskControls.value(QStringLiteral("positions_missing_grace_seconds")).toDouble(),
              12.75),
          QStringLiteral("C++ native risk normalization should preserve Python fractional missing-position grace"));
    check(normalizedRiskControls.value(QStringLiteral("stop_loss")).toObject()
              .value(QStringLiteral("enabled")).toBool(),
          QStringLiteral("C++ native risk normalization should preserve Python stop-loss enablement"));
    check(normalizedRiskControls.value(QStringLiteral("stop_loss")).toObject()
              .value(QStringLiteral("scope")).toString() == QStringLiteral("entire_account"),
          QStringLiteral("C++ native risk normalization should canonicalize Python stop-loss scope"));

    check(
        !NativeStrategyRuntime::indicatorCloseScopeAllowed(
            normalizedRiskControls,
            QStringList{QStringLiteral("rsi"), QStringLiteral("macd")}),
        QStringLiteral("multi-indicator close should remain blocked by Python default"));
    check(
        NativeStrategyRuntime::indicatorCloseScopeAllowed(
            QJsonObject{{QStringLiteral("allow_multi_indicator_close"), true}},
            QStringList{QStringLiteral("rsi"), QStringLiteral("macd")}),
        QStringLiteral("allow_multi_indicator_close should permit multi-indicator close"));
    check(
        NativeStrategyRuntime::indicatorCloseScopeAllowed(
            normalizedRiskControls,
            QStringList{QStringLiteral("rsi"), QStringLiteral("macd")},
            true),
        QStringLiteral("explicit close override should permit multi-indicator close"));

    QString holdReason;
    check(!NativeStrategyRuntime::indicatorHoldReady(
              normalizedRiskControls,
              QStringLiteral("BTCUSDT"),
              QStringLiteral("1m"),
              1'700'000'000'000,
              1'700'000'030'000,
              &holdReason),
          QStringLiteral("C++ indicator hold guard should block a flip before one Python-configured bar"));
    check(holdReason.contains(QStringLiteral("hold guard")),
          QStringLiteral("C++ indicator hold guard should expose a diagnostic reason"));
    check(NativeStrategyRuntime::indicatorHoldReady(
              normalizedRiskControls,
              QStringLiteral("BTCUSDT"),
              QStringLiteral("1m"),
              1'700'000'000'000,
              1'700'000'060'000,
              &holdReason),
          QStringLiteral("C++ indicator hold guard should release a flip after one Python-configured bar"));
    check(!NativeStrategyRuntime::indicatorHoldReady(
              normalizedRiskControls,
              QStringLiteral("BTCUSDT"),
              QStringLiteral("1m"),
              0,
              1'700'000'060'000,
              &holdReason),
          QStringLiteral("C++ indicator hold guard should fail closed when the open timestamp is missing"));
    check(NativeStrategyRuntime::indicatorHoldReady(
              QJsonObject{{QStringLiteral("allow_close_ignoring_hold"), true}},
              QStringLiteral("BTCUSDT"),
              QStringLiteral("1m"),
              1'700'000'000'000,
              1'700'000'001'000,
              &holdReason,
              true),
          QStringLiteral("C++ opposite-close hold override should match Python allow_close_ignoring_hold"));

    QMap<QString, NativeStrategyRuntime::IndicatorSignalConfirmationTracker> confirmationTrackers;
    const QJsonObject confirmationDecision{
        {QStringLiteral("signal"), QStringLiteral("BUY")},
        {QStringLiteral("description"), QStringLiteral("RSI <= 30.00 -> BUY")},
        {QStringLiteral("trigger_price"), 100.0},
        {QStringLiteral("trigger_sources"), QJsonArray{QStringLiteral("rsi")}},
        {QStringLiteral("trigger_actions"), QJsonObject{{QStringLiteral("rsi"), QStringLiteral("buy")}}},
    };
    const QJsonObject confirmationControls{
        {QStringLiteral("indicator_flip_confirmation_bars"), 2},
    };
    const QJsonObject firstConfirmation = NativeStrategyRuntime::applyIndicatorSignalConfirmation(
        confirmationDecision,
        confirmationControls,
        QStringLiteral("btcusdt"),
        QStringLiteral("1m"),
        1'700'000'000'000,
        confirmationTrackers);
    check(firstConfirmation.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("C++ confirmation guard should suppress the first unconfirmed signal"));
    check(firstConfirmation.value(QStringLiteral("trigger_actions")).toObject().isEmpty(),
          QStringLiteral("C++ confirmation guard should remove unconfirmed trigger actions"));
    check(firstConfirmation.value(QStringLiteral("description")).toString().contains(QStringLiteral("1/2")),
          QStringLiteral("C++ confirmation guard should expose its pending count"));

    const QJsonObject secondConfirmation = NativeStrategyRuntime::applyIndicatorSignalConfirmation(
        confirmationDecision,
        confirmationControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'060'000,
        confirmationTrackers);
    check(secondConfirmation.value(QStringLiteral("signal")).toString() == QStringLiteral("BUY"),
          QStringLiteral("C++ confirmation guard should release the signal on the required bar"));
    check(secondConfirmation.value(QStringLiteral("trigger_actions")).toObject().value(QStringLiteral("rsi"))
              .toString() == QStringLiteral("buy"),
          QStringLiteral("C++ confirmation guard should preserve the confirmed action"));

    const QJsonObject resetConfirmation = NativeStrategyRuntime::applyIndicatorSignalConfirmation(
        confirmationDecision,
        confirmationControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'240'001,
        confirmationTrackers);
    check(resetConfirmation.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("C++ confirmation guard should reset after the Python confirmation window"));

    QMap<QString, NativeStrategyRuntime::IndicatorOrderGuardState> orderGuardStates;
    QMap<QString, qint64> reentryBlocks;
    const QJsonObject orderGuardControls{
        {QStringLiteral("indicator_flip_cooldown_seconds"), 120.0},
        {QStringLiteral("indicator_reentry_cooldown_seconds"), 60.0},
        {QStringLiteral("indicator_reentry_requires_signal_reset"), true},
    };
    const QJsonObject firstGuardedOrder = NativeStrategyRuntime::applyIndicatorOrderGuards(
        confirmationDecision,
        orderGuardControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'000'000,
        orderGuardStates,
        reentryBlocks);
    check(firstGuardedOrder.value(QStringLiteral("signal")).toString() == QStringLiteral("BUY"),
          QStringLiteral("C++ order guard should allow the first Python-equivalent indicator action"));
    NativeStrategyRuntime::recordIndicatorOrderAction(
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("rsi"),
        QStringLiteral("BUY"),
        1'700'000'000'000,
        orderGuardStates);
    const QJsonObject oppositeDecision{
        {QStringLiteral("signal"), QStringLiteral("SELL")},
        {QStringLiteral("description"), QStringLiteral("RSI >= 70.00 -> SELL")},
        {QStringLiteral("trigger_price"), 100.0},
        {QStringLiteral("trigger_sources"), QJsonArray{QStringLiteral("rsi")}},
        {QStringLiteral("trigger_actions"), QJsonObject{{QStringLiteral("rsi"), QStringLiteral("sell")}}},
    };
    const QJsonObject cooldownBlocked = NativeStrategyRuntime::applyIndicatorOrderGuards(
        oppositeDecision,
        orderGuardControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'010'000,
        orderGuardStates,
        reentryBlocks);
    check(cooldownBlocked.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("C++ order guard should block an opposite action during Python cooldown"));
    NativeStrategyRuntime::recordIndicatorClose(
        orderGuardControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("rsi"),
        QStringLiteral("BUY"),
        1'700'000'020'000,
        orderGuardStates,
        reentryBlocks);
    const QJsonObject flipAfterClose = NativeStrategyRuntime::applyIndicatorOrderGuards(
        oppositeDecision,
        orderGuardControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'021'000,
        orderGuardStates,
        reentryBlocks);
    check(flipAfterClose.value(QStringLiteral("signal")).toString() == QStringLiteral("SELL"),
          QStringLiteral("C++ order guard should preserve Python recent-close cooldown bypass"));
    const QJsonObject reentryBlocked = NativeStrategyRuntime::applyIndicatorOrderGuards(
        confirmationDecision,
        orderGuardControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'021'000,
        orderGuardStates,
        reentryBlocks);
    check(reentryBlocked.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("C++ order guard should block same-side re-entry until signal reset/cooldown"));

    const QJsonObject sideAwareCooldownControls{
        {QStringLiteral("indicator_flip_cooldown_seconds"), 120.0},
        {QStringLiteral("indicator_reentry_cooldown_seconds"), 0.0},
        {QStringLiteral("indicator_reentry_cooldown_bars"), 0},
        {QStringLiteral("indicator_reentry_requires_signal_reset"), false},
    };
    QMap<QString, NativeStrategyRuntime::IndicatorOrderGuardState> sideAwareStates;
    QMap<QString, qint64> sideAwareReentryBlocks;
    NativeStrategyRuntime::recordIndicatorOrderAction(
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("rsi"),
        QStringLiteral("BUY"),
        1'700'000'000'000,
        sideAwareStates);
    NativeStrategyRuntime::recordIndicatorClose(
        sideAwareCooldownControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("rsi"),
        QStringLiteral("SELL"),
        1'700'000'020'000,
        sideAwareStates,
        sideAwareReentryBlocks);
    const QJsonObject wrongSideRecentClose = NativeStrategyRuntime::applyIndicatorOrderGuards(
        oppositeDecision,
        sideAwareCooldownControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'021'000,
        sideAwareStates,
        sideAwareReentryBlocks);
    check(wrongSideRecentClose.value(QStringLiteral("signal")).isNull(),
          QStringLiteral("C++ recent-close bypass must require the Python opposite closed side"));
    NativeStrategyRuntime::recordIndicatorClose(
        sideAwareCooldownControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("rsi"),
        QStringLiteral("BUY"),
        1'700'000'022'000,
        sideAwareStates,
        sideAwareReentryBlocks);
    const QJsonObject matchingSideRecentClose = NativeStrategyRuntime::applyIndicatorOrderGuards(
        oppositeDecision,
        sideAwareCooldownControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'023'000,
        sideAwareStates,
        sideAwareReentryBlocks);
    check(matchingSideRecentClose.value(QStringLiteral("signal")).toString() == QStringLiteral("SELL"),
          QStringLiteral("C++ recent-close bypass should allow the Python matching opposite close"));

    const QJsonObject resetOnlyControls{
        {QStringLiteral("indicator_flip_cooldown_seconds"), 0.0},
        {QStringLiteral("indicator_reentry_cooldown_seconds"), 0.0},
        {QStringLiteral("indicator_reentry_cooldown_bars"), 0},
        {QStringLiteral("indicator_reentry_requires_signal_reset"), true},
    };
    QMap<QString, NativeStrategyRuntime::IndicatorOrderGuardState> resetRefreshStates;
    QMap<QString, qint64> resetRefreshReentryBlocks;
    NativeStrategyRuntime::recordIndicatorClose(
        resetOnlyControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("rsi"),
        QStringLiteral("BUY"),
        1'700'000'000'000,
        resetRefreshStates,
        resetRefreshReentryBlocks);
    const QJsonObject unrelatedIndicatorDecision{
        {QStringLiteral("signal"), QStringLiteral("SELL")},
        {QStringLiteral("description"), QStringLiteral("MACD -> SELL")},
        {QStringLiteral("trigger_price"), 100.0},
        {QStringLiteral("trigger_sources"), QJsonArray{QStringLiteral("macd")}},
        {QStringLiteral("trigger_actions"), QJsonObject{{QStringLiteral("macd"), QStringLiteral("sell")}}},
    };
    const QJsonObject refreshResult = NativeStrategyRuntime::applyIndicatorOrderGuards(
        unrelatedIndicatorDecision,
        resetOnlyControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'001'000,
        resetRefreshStates,
        resetRefreshReentryBlocks);
    check(refreshResult.value(QStringLiteral("signal")).toString() == QStringLiteral("SELL"),
          QStringLiteral("C++ reset refresh should allow an unrelated indicator action"));
    const QJsonObject resetClearedResult = NativeStrategyRuntime::applyIndicatorOrderGuards(
        confirmationDecision,
        resetOnlyControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'002'000,
        resetRefreshStates,
        resetRefreshReentryBlocks);
    check(resetClearedResult.value(QStringLiteral("signal")).toString() == QStringLiteral("BUY"),
          QStringLiteral("C++ reset refresh should clear a Python block when its indicator action is absent"));

    NativeStrategyRuntime::recordIndicatorCloses(
        orderGuardControls,
        QStringLiteral("btcusdt"),
        QStringLiteral("1m"),
        QStringList{QStringLiteral("RSI"), QStringLiteral("macd"), QStringLiteral("generic"), QStringLiteral("rsi")},
        QStringLiteral("SELL"),
        1'700'000'030'000,
        orderGuardStates,
        reentryBlocks);
    check(orderGuardStates.contains(QStringLiteral("BTCUSDT|1m|rsi")),
          QStringLiteral("C++ close ledger should record every Python-owned indicator source"));
    check(orderGuardStates.contains(QStringLiteral("BTCUSDT|1m|macd")),
          QStringLiteral("C++ close ledger should preserve multi-indicator ownership"));
    check(orderGuardStates.value(QStringLiteral("BTCUSDT|1m|rsi")).recentCloseMs == 1'700'000'030'000,
          QStringLiteral("C++ multi-indicator close ledger should preserve the close timestamp"));
    check(reentryBlocks.value(QStringLiteral("BTCUSDT|1m|SELL")) == 1'700'000'090'000,
          QStringLiteral("C++ multi-indicator close ledger should apply Python re-entry cooldown"));

    QMap<QString, QJsonObject> pendingFlipRequests;
    const QJsonObject autoFlipControls{
        {QStringLiteral("auto_flip_on_close"), true},
        {QStringLiteral("require_indicator_flip_signal"), false},
        {QStringLiteral("strict_indicator_flip_enforcement"), false},
    };
    NativeStrategyRuntime::queueIndicatorFlipOnClose(
        autoFlipControls,
        QStringLiteral("btcusdt"),
        QStringLiteral("1m"),
        QStringList{QStringLiteral("rsi")},
        QStringLiteral("BUY"),
        1.0,
        1'700'000'000'000,
        pendingFlipRequests);
    check(pendingFlipRequests.size() == 1,
          QStringLiteral("C++ auto-flip should queue a fully closed Python indicator slot"));
    const QJsonObject noSignalDecision{
        {QStringLiteral("description"), QStringLiteral("no data")},
        {QStringLiteral("trigger_sources"), QJsonArray{}},
        {QStringLiteral("trigger_actions"), QJsonObject{}},
    };
    const QJsonObject mergedFlip = NativeStrategyRuntime::mergeIndicatorFlipOnCloseRequests(
        noSignalDecision,
        autoFlipControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'000'001,
        pendingFlipRequests);
    check(mergedFlip.value(QStringLiteral("signal")).toString() == QStringLiteral("SELL"),
          QStringLiteral("C++ auto-flip should create the Python-equivalent opposite signal"));
    check(mergedFlip.value(QStringLiteral("trigger_actions")).toObject()
                  .value(QStringLiteral("rsi"))
                  .toString() == QStringLiteral("sell"),
          QStringLiteral("C++ auto-flip should preserve the indicator action source"));
    check(std::abs(mergedFlip.value(QStringLiteral("flip_qty")).toDouble() - 1.0) < 1e-12
              && std::abs(mergedFlip.value(QStringLiteral("flip_qty_target")).toDouble() - 1.0) < 1e-12,
          QStringLiteral("C++ auto-flip should preserve Python's exact close quantity metadata"));
    check(pendingFlipRequests.isEmpty(),
          QStringLiteral("C++ auto-flip should consume a matching pending request"));

    NativeStrategyRuntime::queueIndicatorFlipOnClose(
        autoFlipControls,
        QStringLiteral("btcusdt"),
        QStringLiteral("1m"),
        QStringList{QStringLiteral("rsi")},
        QStringLiteral("BUY"),
        1.0,
        1'700'000'000'000,
        pendingFlipRequests);
    const QJsonObject expiredFlip = NativeStrategyRuntime::mergeIndicatorFlipOnCloseRequests(
        noSignalDecision,
        autoFlipControls,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'700'000'120'001,
        pendingFlipRequests);
    check(expiredFlip.value(QStringLiteral("signal")).isNull()
              || expiredFlip.value(QStringLiteral("signal")).isUndefined(),
          QStringLiteral("C++ auto-flip should expire requests using the Python interval TTL"));
    check(pendingFlipRequests.isEmpty(),
          QStringLiteral("C++ expired auto-flip requests should be removed"));

    QMap<QString, QJsonObject> disabledFlipRequests;
    NativeStrategyRuntime::queueIndicatorFlipOnClose(
        QJsonObject{{QStringLiteral("auto_flip_on_close"), false}},
        QStringLiteral("btcusdt"),
        QStringLiteral("1m"),
        QStringList{QStringLiteral("rsi")},
        QStringLiteral("BUY"),
        1.0,
        1'700'000'000'000,
        disabledFlipRequests);
    check(disabledFlipRequests.isEmpty(),
          QStringLiteral("C++ auto-flip should honor Python's disabled option"));

    const QJsonObject stopLossDecision = NativeStrategyRuntime::evaluatePerTradeStopLoss(
        QJsonObject{
            {QStringLiteral("stop_loss"), QJsonObject{
                {QStringLiteral("enabled"), true},
                {QStringLiteral("mode"), QStringLiteral("both")},
                {QStringLiteral("scope"), QStringLiteral("per_trade")},
                {QStringLiteral("usdt"), 4.0},
                {QStringLiteral("percent"), 10.0},
            }},
        },
        QStringLiteral("btcusdt"),
        QStringLiteral("1m"),
        QStringLiteral("LONG"),
        1.0,
        100.0,
        94.0,
        5.0,
        20.0,
        true);
    check(stopLossDecision.value(QStringLiteral("triggered")).toBool(),
          QStringLiteral("C++ native per-trade stop-loss should trigger at the Python threshold"));
    check(stopLossDecision.value(QStringLiteral("close_side")).toString() == QStringLiteral("SELL"),
          QStringLiteral("C++ native per-trade stop-loss should close a long with SELL"));
    check(stopLossDecision.value(QStringLiteral("reason")).toString() == QStringLiteral("per_trade_stop_loss"),
          QStringLiteral("C++ native per-trade stop-loss should preserve Python reason"));
    check(qFuzzyCompare(stopLossDecision.value(QStringLiteral("loss_usdt")).toDouble(), 6.0),
          QStringLiteral("C++ native per-trade stop-loss should calculate loss in USDT"));
    check(qFuzzyCompare(stopLossDecision.value(QStringLiteral("margin_loss_percent")).toDouble(), 30.0),
          QStringLiteral("C++ native per-trade stop-loss should calculate margin loss percent"));

    const QJsonArray aggregateStopPositions{
        QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
            {QStringLiteral("side"), QStringLiteral("LONG")},
            {QStringLiteral("quantity"), 1.0},
            {QStringLiteral("entry_price"), 100.0},
            {QStringLiteral("mark_price"), 94.0},
            {QStringLiteral("margin_usdt"), 20.0},
            {QStringLiteral("dual_side"), true},
        },
        QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
            {QStringLiteral("side"), QStringLiteral("LONG")},
            {QStringLiteral("quantity"), 1.0},
            {QStringLiteral("entry_price"), 100.0},
            {QStringLiteral("mark_price"), 94.0},
            {QStringLiteral("margin_usdt"), 20.0},
            {QStringLiteral("dual_side"), true},
        },
    };
    const QJsonObject cumulativeControls{{QStringLiteral("stop_loss"), QJsonObject{
        {QStringLiteral("enabled"), true},
        {QStringLiteral("mode"), QStringLiteral("usdt")},
        {QStringLiteral("scope"), QStringLiteral("cumulative")},
        {QStringLiteral("usdt"), 10.0},
    }}};
    const QJsonArray cumulativeDirectives = NativeStrategyRuntime::evaluateFuturesStopLoss(
        cumulativeControls,
        aggregateStopPositions,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        1'000.0,
        true);
    check(cumulativeDirectives.size() == 1,
          QStringLiteral("C++ cumulative stop-loss should emit one side aggregate"));
    check(cumulativeDirectives.first().toObject().value(QStringLiteral("qty")).toDouble() == 2.0,
          QStringLiteral("C++ cumulative stop-loss should close the full aggregated side quantity"));
    check(cumulativeDirectives.first().toObject().value(QStringLiteral("reason")).toString()
              == QStringLiteral("cumulative_stop_loss"),
          QStringLiteral("C++ cumulative stop-loss should preserve Python reason"));

    const QJsonObject accountControls{{QStringLiteral("stop_loss"), QJsonObject{
        {QStringLiteral("enabled"), true},
        {QStringLiteral("mode"), QStringLiteral("percent")},
        {QStringLiteral("scope"), QStringLiteral("entire_account")},
        {QStringLiteral("percent"), 1.0},
    }}};
    const QJsonArray accountDirectives = NativeStrategyRuntime::evaluateFuturesStopLoss(
        accountControls,
        aggregateStopPositions,
        QStringLiteral("ETHUSDT"),
        QStringLiteral("1m"),
        1'000.0,
        true);
    check(accountDirectives.size() == 1
              && accountDirectives.first().toObject().value(QStringLiteral("close_side")).toString()
                     == QStringLiteral("CLOSE_ALL"),
          QStringLiteral("C++ entire-account stop-loss should close all account positions"));

    const QJsonObject spotStopLossDecision = NativeStrategyRuntime::evaluatePerTradeStopLoss(
        QJsonObject{{QStringLiteral("stop_loss"), QJsonObject{
            {QStringLiteral("enabled"), true},
            {QStringLiteral("mode"), QStringLiteral("usdt")},
            {QStringLiteral("scope"), QStringLiteral("per_trade")},
            {QStringLiteral("usdt"), 1.0},
        }}},
        QStringLiteral("BTCUSDT"),
        QStringLiteral("1m"),
        QStringLiteral("LONG"),
        1.0,
        100.0,
        90.0,
        1.0,
        100.0,
        false);
    check(!spotStopLossDecision.value(QStringLiteral("triggered")).toBool(),
          QStringLiteral("C++ native per-trade futures stop-loss should remain disabled for spot"));

    const QJsonObject overrideResult = NativeStrategyRuntime::buildCleanOverrideEntry(
        QStringLiteral("backtest"),
        QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral(" btcusdt ")},
            {QStringLiteral("interval"), QStringLiteral("1M")},
            {QStringLiteral("indicators"), QJsonArray{QStringLiteral("ema"), QString(), QStringLiteral("volume")}},
            {QStringLiteral("strategy_controls"), QJsonObject{
                {QStringLiteral("logic"), QStringLiteral("or")},
                {QStringLiteral("position_pct"), QStringLiteral("20")},
                {QStringLiteral("position_pct_units"), QStringLiteral("%")},
                {QStringLiteral("leverage"), 0},
                {QStringLiteral("connector_backend"), QStringLiteral("binance-sdk-spot")},
            }},
            {QStringLiteral("leverage"), 3},
            {QStringLiteral("backtest_result"), QJsonObject{
                {QStringLiteral("source"), QStringLiteral("python-backtest")},
                {QStringLiteral("optimizer_rank"), 1},
                {QStringLiteral("roi_percent"), 12.5},
                {QStringLiteral("max_drawdown_percent"), 3.25},
                {QStringLiteral("trades"), 4},
                {QStringLiteral("empty"), QString()},
            }},
        });
    const QJsonObject cleanOverride = overrideResult.value(QStringLiteral("entry")).toObject();
    check(cleanOverride.value(QStringLiteral("symbol")).toString() == QStringLiteral("BTCUSDT"),
          QStringLiteral("native override cleanup should uppercase symbols"));
    check(cleanOverride.value(QStringLiteral("interval")).toString() == QStringLiteral("1mo"),
          QStringLiteral("native override cleanup should normalize backtest month interval"));
    check(cleanOverride.value(QStringLiteral("strategy_controls")).toObject().value(QStringLiteral("leverage")).toInt() == 1,
          QStringLiteral("native override cleanup should clamp present backtest control leverage like Python"));
    check(cleanOverride.value(QStringLiteral("backtest_result")).toObject().value(QStringLiteral("source")).toString() == QStringLiteral("python-backtest"),
          QStringLiteral("native override cleanup should preserve backtest provenance"));
    check(!cleanOverride.value(QStringLiteral("backtest_result")).toObject().contains(QStringLiteral("empty")),
          QStringLiteral("native override cleanup should drop empty backtest metadata"));
    check(NativeStrategyRuntime::formatBacktestResultText(cleanOverride.value(QStringLiteral("backtest_result")).toObject())
              == QStringLiteral("Rank 1 | ROI 12.5% | DD 3.25% | Trades 4"),
          QStringLiteral("native override cleanup should format backtest provenance summary like Python"));

    NativeStrategyRuntime::StrategyWorkerLifecycleInput lifecycleInput;
    lifecycleInput.symbol = QStringLiteral("btcusdt");
    lifecycleInput.interval = QStringLiteral("1m");
    lifecycleInput.loopIntervalOverride = QStringLiteral("5m");
    lifecycleInput.threadAlive = true;
    lifecycleInput.activeEngineCount = 2;
    lifecycleInput.offlineBackoff = 5.0;
    const QJsonObject lifecycleSnapshot = NativeStrategyRuntime::buildWorkerLifecycleSnapshot(lifecycleInput);
    check(lifecycleSnapshot.value(QStringLiteral("lifecycle_phase")).toString() == QStringLiteral("running"),
          QStringLiteral("native strategy lifecycle should report running thread"));
    check(lifecycleSnapshot.value(QStringLiteral("thread_name")).toString() == QStringLiteral("StrategyLoop-BTCUSDT@5m "),
          QStringLiteral("native strategy lifecycle should mirror Python thread naming"));
    check(lifecycleSnapshot.value(QStringLiteral("loop_interval_seconds")).toDouble() == 300.0,
          QStringLiteral("native strategy lifecycle should use loop override seconds"));
    check(lifecycleSnapshot.value(QStringLiteral("execution_owner")).toString() == QStringLiteral("native-cpp"),
          QStringLiteral("native strategy lifecycle should report the C++ execution owner"));
    check(lifecycleSnapshot.value(QStringLiteral("native_trading_execution_enabled")).toBool(false),
          QStringLiteral("native strategy lifecycle should enable its native Binance market path"));
    check(lifecycleSnapshot.value(QStringLiteral("native_trading_execution_scope")).toString()
              == QStringLiteral("binance-spot-usds-and-coin-futures"),
          QStringLiteral("native strategy lifecycle should report its exact execution scope"));

    NativeStrategyRuntime::StrategyWorkerLifecycleInput invalidBackoffInput;
    invalidBackoffInput.offlineBackoff = std::numeric_limits<double>::quiet_NaN();
    const QJsonObject invalidBackoffSnapshot =
        NativeStrategyRuntime::buildWorkerLifecycleSnapshot(invalidBackoffInput);
    check(invalidBackoffSnapshot.value(QStringLiteral("offline_backoff")).toDouble() == 0.0,
          QStringLiteral("native strategy lifecycle should reset non-finite outage state"));
    check(invalidBackoffSnapshot.value(QStringLiteral("next_network_backoff")).toDouble() == 5.0,
          QStringLiteral("native strategy lifecycle should use the initial retry delay for invalid outage state"));

    const QDateTime diagnosticsAt =
        QDateTime::fromString(QStringLiteral("2026-06-18T12:10:00.000Z"), Qt::ISODateWithMs);
    const QJsonObject serviceLogEvent = NativeDiagnostics::buildServiceLogEvent(
        QStringLiteral("Connector failed with api_secret=super-secret-value"),
        QStringLiteral("service api_key=super-secret-value"),
        QStringLiteral("WARNING"),
        -12,
        diagnosticsAt);
    check(serviceLogEvent.value(QStringLiteral("sequence_id")).toInt(-1) == 0,
          QStringLiteral("service log event should clamp negative sequence ids like Python"));
    check(serviceLogEvent.value(QStringLiteral("level")).toString() == QStringLiteral("warning"),
          QStringLiteral("service log event should lowercase levels like Python"));
    check(serviceLogEvent.value(QStringLiteral("message")).toString().contains(QStringLiteral("<redacted>")),
          QStringLiteral("service log event should redact secret-bearing messages"));
    check(!serviceLogEvent.value(QStringLiteral("message")).toString().contains(QStringLiteral("super-secret-value")),
          QStringLiteral("service log event should not leak secret values"));
    check(serviceLogEvent.value(QStringLiteral("source")).toString().contains(QStringLiteral("<redacted>")),
          QStringLiteral("service log event should redact secret-bearing sources"));
    check(NativeDiagnostics::formatServiceLogLine(serviceLogEvent).contains(QStringLiteral("[WARNING]")),
          QStringLiteral("service log formatter should include normalized level"));

    const QJsonObject terminalResult = NativeDiagnostics::buildServiceTerminalCommandResult(
        true,
        QStringLiteral("status api_key=super-secret-value"),
        QStringLiteral("Bearer super-secret-value\nstate=ready"),
        QStringLiteral("terminal token=super-secret-value"),
        0,
        diagnosticsAt);
    check(terminalResult.value(QStringLiteral("accepted")).toBool(false),
          QStringLiteral("terminal result should expose accepted state"));
    check(terminalResult.value(QStringLiteral("command_type")).toString() == QStringLiteral("service-command"),
          QStringLiteral("terminal result should mirror Python command_type"));
    check(terminalResult.value(QStringLiteral("command")).toString().contains(QStringLiteral("<redacted>")),
          QStringLiteral("terminal result command should be redacted"));
    check(terminalResult.value(QStringLiteral("output")).toString().contains(QStringLiteral("Bearer <redacted>")),
          QStringLiteral("terminal result output should redact bearer tokens"));
    check(!terminalResult.value(QStringLiteral("source")).toString().contains(QStringLiteral("super-secret-value")),
          QStringLiteral("terminal result source should not leak secret values"));

    const QJsonObject llmPromptPayload = NativeLlmAdvisory::buildPromptRoutePayload(
        QStringLiteral(" Summarize BTC risk "),
        QStringLiteral(" Keep it advisory "),
        true,
        QStringLiteral("cpp-test-llm"));
    check(llmPromptPayload.value(QStringLiteral("prompt")).toString() == QStringLiteral("Summarize BTC risk"),
          QStringLiteral("native LLM prompt payload should trim prompt like Python Service API"));
    check(llmPromptPayload.value(QStringLiteral("system_prompt")).toString() == QStringLiteral("Keep it advisory"),
          QStringLiteral("native LLM prompt payload should trim system prompt"));
    check(llmPromptPayload.value(QStringLiteral("dry_run")).toBool(false),
          QStringLiteral("native LLM prompt payload should preserve dry_run"));
    check(llmPromptPayload.value(QStringLiteral("source")).toString() == QStringLiteral("cpp-test-llm"),
          QStringLiteral("native LLM prompt payload should preserve source"));
    const QJsonObject llmRendered = NativeLlmAdvisory::renderPromptResult(QJsonObject{
        {QStringLiteral("ok"), true},
        {QStringLiteral("dry_run"), true},
        {QStringLiteral("text"), QStringLiteral("Prepared request with api_key=super-secret-value. Execution boundary: advisory only.")},
    });
    check(llmRendered.value(QStringLiteral("status")).toString() == QStringLiteral("LLM advisory dry run ok"),
          QStringLiteral("native LLM render should expose dry-run ok status"));
    check(llmRendered.value(QStringLiteral("text")).toString().contains(QStringLiteral("<redacted>")),
          QStringLiteral("native LLM render should redact secret-bearing text"));
    check(llmRendered.value(QStringLiteral("execution_boundary")).toString().contains(QStringLiteral("advisory only")),
          QStringLiteral("native LLM render should expose advisory-only boundary"));
    const QStringList llmViolations = NativeLlmAdvisory::outputPolicyViolations(
        QStringLiteral(R"({"action":"place_order","status":"executed"})"));
    const QJsonDocument llmPolicyReferenceDocument = QJsonDocument::fromJson(QByteArray(
        PythonParityContract::kPythonLlmOutputPolicyReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonLlmOutputPolicyReferenceJson.size())));
    check(llmPolicyReferenceDocument.isObject(),
          QStringLiteral("Python LLM output-policy reference fixture should be valid JSON"));
    for (const QJsonValue &referenceValue : llmPolicyReferenceDocument.object()
                                                    .value(QStringLiteral("cases"))
                                                    .toArray()) {
        const QJsonObject referenceCase = referenceValue.toObject();
        QStringList expectedViolations;
        for (const QJsonValue &violation : referenceCase.value(QStringLiteral("expected_violations")).toArray()) {
            expectedViolations.append(violation.toString());
        }
        const QString text = referenceCase.value(QStringLiteral("text")).toString();
        check(NativeLlmAdvisory::outputPolicyViolations(text) == expectedViolations,
              QStringLiteral("C++ LLM output policy should match Python case %1")
                  .arg(referenceCase.value(QStringLiteral("name")).toString()));
    }
    const QJsonDocument llmChatReferenceDocument = QJsonDocument::fromJson(QByteArray(
        PythonParityContract::kPythonLlmChatRequestReferenceJson.data(),
        static_cast<qsizetype>(PythonParityContract::kPythonLlmChatRequestReferenceJson.size())));
    check(llmChatReferenceDocument.isObject(),
          QStringLiteral("Python LLM chat-request reference fixture should be valid JSON"));
    for (const QJsonValue &referenceValue : llmChatReferenceDocument.object()
                                                    .value(QStringLiteral("cases"))
                                                    .toArray()) {
        const QJsonObject referenceCase = referenceValue.toObject();
        QString error;
        const QJsonObject actual = NativeLlmAdvisory::buildChatRequest(
            referenceCase.value(QStringLiteral("config")).toObject(),
            referenceCase.value(QStringLiteral("prompt")).toString(),
            referenceCase.value(QStringLiteral("system_prompt")).toString(),
            referenceCase.value(QStringLiteral("context")),
            &error);
        check(!actual.isEmpty(),
              QStringLiteral("C++ LLM request should build Python case %1: %2")
                  .arg(referenceCase.value(QStringLiteral("name")).toString(), error));
        check(actual == referenceCase.value(QStringLiteral("expected")).toObject(),
              QStringLiteral("C++ LLM request should match Python case %1")
                  .arg(referenceCase.value(QStringLiteral("name")).toString()));
    }
    const auto parityText = [](std::string_view value) {
        return QString::fromUtf8(value.data(), static_cast<int>(value.size()));
    };
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        QJsonObject providerConfig{
            {QStringLiteral("llm_provider"), parityText(provider.key)},
            {QStringLiteral("llm_model"), parityText(provider.defaultModel)},
            {QStringLiteral("llm_base_url"), parityText(provider.defaultBaseUrl)},
            {QStringLiteral("llm_api_key"), parityText(provider.mode) == QStringLiteral("cloud") ? QStringLiteral("parity-test-key") : QString()},
        };
        const QStringList reasoningEfforts = QString::fromUtf8(
            provider.reasoningEfforts.data(), static_cast<int>(provider.reasoningEfforts.size())).split(',');
        for (const QString &reasoningEffort : reasoningEfforts) {
            providerConfig.insert(QStringLiteral("llm_reasoning_effort"), reasoningEffort);
            QString error;
            const QJsonObject actual = NativeLlmAdvisory::buildChatRequest(
                providerConfig,
                QStringLiteral("Explain risk"),
                QStringLiteral("Be concise"),
                {},
                &error);
            check(!actual.isEmpty(),
                  QStringLiteral("C++ should build every Python provider/reasoning option (%1/%2): %3")
                      .arg(parityText(provider.key), reasoningEffort, error));
            check(actual.value(QStringLiteral("provider")).toString() == parityText(provider.key),
                  QStringLiteral("C++ provider request should preserve Python provider key: %1")
                      .arg(parityText(provider.key)));
            check(actual.value(QStringLiteral("protocol")).toString() == parityText(provider.protocol),
                  QStringLiteral("C++ provider request should preserve Python protocol: %1")
                      .arg(parityText(provider.key)));
        }
    }
    check(llmViolations == QStringList{
              QStringLiteral("order_execution_claim"),
              QStringLiteral("direct_order_action"),
          },
          QStringLiteral("native LLM policy violation ordering should match Python source"));
    check(llmViolations.contains(QStringLiteral("direct_order_action")),
          QStringLiteral("native LLM policy should block direct order actions"));
    check(llmViolations.contains(QStringLiteral("order_execution_claim")),
          QStringLiteral("native LLM policy should block execution claims"));
    const QStringList structuredLlmViolations = NativeLlmAdvisory::outputPolicyViolations(
        QStringLiteral(R"(prefix {"command":"create_order","disable_stop_loss":true} suffix)"));
    check(structuredLlmViolations.contains(QStringLiteral("direct_order_action")),
          QStringLiteral("native LLM policy should scan Python-equivalent command actions"));
    check(structuredLlmViolations.contains(QStringLiteral("risk_override")),
          QStringLiteral("native LLM policy should scan boolean risk overrides"));
    const QStringList fencedLlmViolations = NativeLlmAdvisory::outputPolicyViolations(
        QStringLiteral("```json\n{\"tool\":\"market_sell\",\"status\":\"placed\"}\n```"));
    check(fencedLlmViolations.contains(QStringLiteral("direct_order_action")),
          QStringLiteral("native LLM policy should scan fenced JSON candidates"));
    check(fencedLlmViolations.contains(QStringLiteral("order_execution_claim")),
          QStringLiteral("native LLM policy should scan placed execution claims"));
    const QVariantMap currentLlmProviderSpec{
        {QStringLiteral("key"), QStringLiteral("local")},
        {QStringLiteral("label"), QStringLiteral("Local")},
        {QStringLiteral("base_url"), QStringLiteral("http://127.0.0.1:11434/v1")},
        {QStringLiteral("default_reasoning"), QStringLiteral("default")},
        {QStringLiteral("models"), QStringList{QStringLiteral("qwen3:8b")}},
    };
    const QVariantMap mergedLlmProviderSpec = TradingBotWindowSupport::mergePythonLlmProviderSpec(
        currentLlmProviderSpec,
        QJsonObject{
            {QStringLiteral("key"), QStringLiteral("local")},
            {QStringLiteral("label"), QStringLiteral("Local / Ollama")},
            {QStringLiteral("protocol"), QStringLiteral("openai-chat-completions")},
            {QStringLiteral("default_base_url"), QStringLiteral("http://127.0.0.1:11434/v1")},
            {QStringLiteral("default_model"), QStringLiteral("qwen3:8b")},
            {QStringLiteral("default_reasoning_effort"), QStringLiteral("medium")},
            {QStringLiteral("custom_models_env"), QStringLiteral("BOT_LLM_EXTRA_MODELS_LOCAL")},
            {QStringLiteral("custom_models_path_env"), QStringLiteral("BOT_LLM_MODEL_CATALOG_PATH")},
            {QStringLiteral("catalog_path"), QStringLiteral("C:/Users/test/.trading-bot/llm-models.json")},
            {QStringLiteral("catalog_note"), QStringLiteral("Local catalog overrides are supported")},
            {QStringLiteral("model_suggestions"), QJsonArray{
                QStringLiteral("qwen3:8b"), QStringLiteral("qwen3:32b"), QStringLiteral("qwen3:32b")}},
            {QStringLiteral("reasoning_efforts"), QJsonArray{
                QStringLiteral("default"), QStringLiteral("medium"), QStringLiteral("medium")}},
            {QStringLiteral("notes"), QJsonArray{QStringLiteral("Local/private endpoint")}},
        });
    check(mergedLlmProviderSpec.value(QStringLiteral("base_url")).toString()
              == QStringLiteral("http://127.0.0.1:11434/v1"),
          QStringLiteral("C++ LLM catalog merge should map Python default_base_url"));
    check(mergedLlmProviderSpec.value(QStringLiteral("default_reasoning")).toString()
              == QStringLiteral("medium"),
          QStringLiteral("C++ LLM catalog merge should map Python default_reasoning_effort"));
    check(mergedLlmProviderSpec.value(QStringLiteral("models")).toStringList()
              == QStringList{QStringLiteral("qwen3:8b"), QStringLiteral("qwen3:32b")},
          QStringLiteral("C++ LLM catalog merge should deduplicate Python model_suggestions"));
    check(mergedLlmProviderSpec.value(QStringLiteral("reasoning_efforts")).toStringList()
              == QStringList{QStringLiteral("default"), QStringLiteral("medium")},
          QStringLiteral("C++ LLM catalog merge should deduplicate reasoning_efforts"));
    check(mergedLlmProviderSpec.value(QStringLiteral("custom_models_path_env")).toString()
              == QStringLiteral("BOT_LLM_MODEL_CATALOG_PATH"),
          QStringLiteral("C++ LLM catalog merge should preserve Python catalog path metadata"));
    check(mergedLlmProviderSpec.value(QStringLiteral("catalog_note")).toString()
              == QStringLiteral("Local catalog overrides are supported"),
          QStringLiteral("C++ LLM catalog merge should preserve Python catalog note metadata"));
    check(mergedLlmProviderSpec.value(QStringLiteral("notes")).toStringList()
              == QStringList{QStringLiteral("Local/private endpoint")},
          QStringLiteral("C++ LLM catalog merge should preserve provider notes"));
    QTemporaryDir llmCatalogDir;
    const QByteArray previousLocalModels = qgetenv("BOT_LLM_EXTRA_MODELS_LOCAL");
    const QByteArray previousCatalogPath = qgetenv("BOT_LLM_MODEL_CATALOG_PATH");
    const QString llmCatalogFilePath = llmCatalogDir.filePath(QStringLiteral("llm-models.json"));
    {
        QFile catalogFile(llmCatalogFilePath);
        check(catalogFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text),
              QStringLiteral("C++ LLM catalog parity fixture should be writable"));
        catalogFile.write(R"({"local":["qwen3:8b","custom-file-model"]})");
    }
    qputenv("BOT_LLM_EXTRA_MODELS_LOCAL", QByteArray("custom-env-model;qwen3:8b"));
    qputenv("BOT_LLM_MODEL_CATALOG_PATH", llmCatalogFilePath.toUtf8());
    const auto dynamicLlmConfigs = TradingBotWindowSupport::pythonSourceLlmProviderConfigs();
    for (const auto &provider : dynamicLlmConfigs) {
        if (provider.key != QStringLiteral("local")) {
            continue;
        }
        check(provider.modelSuggestions.contains(QStringLiteral("custom-env-model")),
              QStringLiteral("C++ LLM fallback catalog should include environment model additions"));
        check(provider.modelSuggestions.contains(QStringLiteral("custom-file-model")),
              QStringLiteral("C++ LLM fallback catalog should include file model additions"));
        check(provider.modelSuggestions.count(QStringLiteral("custom-file-model")) == 1,
              QStringLiteral("C++ LLM fallback catalog should deduplicate environment and file models"));
        break;
    }
    {
        QFile catalogFile(llmCatalogFilePath);
        check(catalogFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text),
              QStringLiteral("C++ nested LLM catalog parity fixture should be writable"));
        catalogFile.write(R"({"providers":{"local":["nested-file-model"]}})");
    }
    const auto nestedDynamicLlmConfigs = TradingBotWindowSupport::pythonSourceLlmProviderConfigs();
    for (const auto &provider : nestedDynamicLlmConfigs) {
        if (provider.key != QStringLiteral("local")) {
            continue;
        }
        check(provider.modelSuggestions.contains(QStringLiteral("nested-file-model")),
              QStringLiteral("C++ LLM fallback catalog should read providers-file model additions"));
        break;
    }
    {
        QFile catalogFile(llmCatalogFilePath);
        check(catalogFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text),
              QStringLiteral("C++ null-top-level LLM catalog fixture should be writable"));
        catalogFile.write(R"({"local":null,"providers":{"local":["null-fallback-model"]}})");
    }
    const auto nullTopLevelLlmConfigs = TradingBotWindowSupport::pythonSourceLlmProviderConfigs();
    for (const auto &provider : nullTopLevelLlmConfigs) {
        if (provider.key != QStringLiteral("local")) {
            continue;
        }
        check(provider.modelSuggestions.contains(QStringLiteral("null-fallback-model")),
              QStringLiteral("C++ LLM fallback catalog should fall back on Python null top-level values"));
        break;
    }
    {
        QFile catalogFile(llmCatalogFilePath);
        check(catalogFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text),
              QStringLiteral("C++ invalid-top-level LLM catalog fixture should be writable"));
        catalogFile.write(R"({"local":"not-a-list","providers":{"local":["ignored-nested-model"]}})");
    }
    const auto invalidTopLevelLlmConfigs = TradingBotWindowSupport::pythonSourceLlmProviderConfigs();
    for (const auto &provider : invalidTopLevelLlmConfigs) {
        if (provider.key != QStringLiteral("local")) {
            continue;
        }
        check(!provider.modelSuggestions.contains(QStringLiteral("ignored-nested-model")),
              QStringLiteral("C++ LLM fallback catalog should preserve Python top-level precedence"));
        break;
    }
    {
        QFile catalogFile(llmCatalogFilePath);
        check(catalogFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text),
              QStringLiteral("C++ coercion LLM catalog fixture should be writable"));
        catalogFile.write(R"({"local":["qwen3:8b",0,false,true,1,[1],{"x":1}]})");
    }
    const auto coercionLlmConfigs = TradingBotWindowSupport::pythonSourceLlmProviderConfigs();
    for (const auto &provider : coercionLlmConfigs) {
        if (provider.key != QStringLiteral("local")) {
            continue;
        }
        check(!provider.modelSuggestions.contains(QStringLiteral("0")),
              QStringLiteral("C++ LLM fallback catalog should omit Python-falsy numeric zero"));
        check(provider.modelSuggestions.contains(QStringLiteral("True")),
              QStringLiteral("C++ LLM fallback catalog should preserve Python true coercion"));
        check(provider.modelSuggestions.contains(QStringLiteral("1")),
              QStringLiteral("C++ LLM fallback catalog should preserve Python numeric coercion"));
        check(provider.modelSuggestions.contains(QStringLiteral("[1]")),
              QStringLiteral("C++ LLM fallback catalog should preserve Python list coercion"));
        check(provider.modelSuggestions.contains(QStringLiteral("{'x': 1}")),
              QStringLiteral("C++ LLM fallback catalog should preserve Python object coercion"));
        break;
    }
    if (previousLocalModels.isNull()) {
        qunsetenv("BOT_LLM_EXTRA_MODELS_LOCAL");
    } else {
        qputenv("BOT_LLM_EXTRA_MODELS_LOCAL", previousLocalModels);
    }
    if (previousCatalogPath.isNull()) {
        qunsetenv("BOT_LLM_MODEL_CATALOG_PATH");
    } else {
        qputenv("BOT_LLM_MODEL_CATALOG_PATH", previousCatalogPath);
    }
    const QJsonObject localModelPayload = NativeLlmAdvisory::buildLocalModelRoutePayload(
        QStringLiteral("http://127.0.0.1:11434/v1"),
        QStringLiteral("qwen3:8b"),
        QStringLiteral("cpp-test-llm"));
    check(localModelPayload.value(QStringLiteral("base_url")).toString() == QStringLiteral("http://127.0.0.1:11434/v1"),
          QStringLiteral("native local model payload should preserve base_url"));
    check(localModelPayload.value(QStringLiteral("model")).toString() == QStringLiteral("qwen3:8b"),
          QStringLiteral("native local model payload should preserve model"));
    const QString localModelStatus = NativeLlmAdvisory::describeLocalModelStatus(QJsonObject{
        {QStringLiteral("model"), QStringLiteral("qwen3:8b")},
        {QStringLiteral("server_kind"), QStringLiteral("ollama")},
        {QStringLiteral("installed"), false},
        {QStringLiteral("estimated_size_label"), QStringLiteral("about 5 GB")},
        {QStringLiteral("storage_paths"), QJsonArray{QStringLiteral("C:/Users/Yunus/.ollama/models")}},
        {QStringLiteral("disk_space_warning"), QStringLiteral("Low disk space")},
        {QStringLiteral("error"), QStringLiteral("Bearer super-secret-value")},
    });
    check(localModelStatus.contains(QStringLiteral("not installed on ollama")),
          QStringLiteral("native local model status should describe install state"));
    check(localModelStatus.contains(QStringLiteral("estimated about 5 GB")),
          QStringLiteral("native local model status should describe size estimate"));
    check(localModelStatus.contains(QStringLiteral("<redacted>")),
          QStringLiteral("native local model status should redact server errors"));

    QJsonObject openPositionRecords{
        {QStringLiteral("ETHUSDT:S"), QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("ethusdt")},
            {QStringLiteral("side_key"), QStringLiteral("s")},
            {QStringLiteral("entry_tf"), QStringLiteral("5m")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("open_time"), QStringLiteral("2026-06-18T10:00:00+00:00")},
            {QStringLiteral("data"), QJsonObject{
                {QStringLiteral("qty"), 0.5},
                {QStringLiteral("mark"), 3000.0},
                {QStringLiteral("size_usdt"), 1500.0},
                {QStringLiteral("margin_usdt"), 150.0},
                {QStringLiteral("pnl_value"), -12.0},
                {QStringLiteral("roi_percent"), -8.0},
                {QStringLiteral("leverage"), 10},
            }},
        }},
        {QStringLiteral("BTCUSDT:L"), QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("btcusdt")},
            {QStringLiteral("side_key"), QStringLiteral("l")},
            {QStringLiteral("entry_tf"), QStringLiteral("1m")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("open_time"), QStringLiteral("2026-06-18T09:00:00+00:00")},
            {QStringLiteral("data"), QJsonObject{
                {QStringLiteral("qty"), 0.25},
                {QStringLiteral("mark"), 60000.0},
                {QStringLiteral("size_usdt"), 15000.0},
                {QStringLiteral("margin_usdt"), 500.0},
                {QStringLiteral("pnl_value"), 42.0},
                {QStringLiteral("roi_percent"), 8.4},
                {QStringLiteral("leverage"), 20},
            }},
        }},
    };
    QJsonArray closedPositionRecords{
        QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("SOLUSDT")},
            {QStringLiteral("side_key"), QStringLiteral("L")},
            {QStringLiteral("status"), QStringLiteral("Closed")},
        },
    };
    const QJsonObject closedTradeRegistry{
        {QStringLiteral("SOLUSDT:L"), QJsonObject{
            {QStringLiteral("pnl_value"), 5.5},
            {QStringLiteral("margin_usdt"), 50.0},
        }},
    };
    const QJsonObject portfolioSnapshot = NativePortfolio::buildPortfolioSnapshot(
        QJsonObject{{QStringLiteral("account_type"), QStringLiteral("Futures")}},
        openPositionRecords,
        closedPositionRecords,
        closedTradeRegistry,
        1000.0,
        800.0,
        QStringLiteral("cpp-test"),
        diagnosticsAt.toUTC().toString(Qt::ISODateWithMs));
    check(portfolioSnapshot.value(QStringLiteral("open_position_count")).toInt() == 2,
          QStringLiteral("native portfolio snapshot should count open records"));
    check(portfolioSnapshot.value(QStringLiteral("closed_position_count")).toInt() == 1,
          QStringLiteral("native portfolio snapshot should count closed records"));
    check(portfolioSnapshot.value(QStringLiteral("active_pnl")).toDouble() == 30.0,
          QStringLiteral("native portfolio snapshot should compute active PNL like Python"));
    check(portfolioSnapshot.value(QStringLiteral("active_margin")).toDouble() == 650.0,
          QStringLiteral("native portfolio snapshot should compute active margin like Python"));
    check(portfolioSnapshot.value(QStringLiteral("closed_pnl")).toDouble() == 5.5,
          QStringLiteral("native portfolio snapshot should compute closed PNL like Python"));
    const QJsonArray portfolioPositions = portfolioSnapshot.value(QStringLiteral("positions")).toArray();
    check(portfolioPositions.at(0).toObject().value(QStringLiteral("symbol")).toString() == QStringLiteral("BTCUSDT"),
          QStringLiteral("native portfolio positions should sort by symbol/side/interval/open time"));
    check(portfolioPositions.at(0).toObject().value(QStringLiteral("side_label")).toString() == QStringLiteral("Long"),
          QStringLiteral("native portfolio position should expose Python side label"));

    QJsonObject entryAllocations{
        {QStringLiteral("BTCUSDT:L"), QJsonArray{
            QJsonObject{
                {QStringLiteral("ledger_id"), QStringLiteral("ledger-1")},
                {QStringLiteral("interval"), QStringLiteral("1m")},
                {QStringLiteral("trade_id"), QStringLiteral("trade-1")},
                {QStringLiteral("qty"), 0.10},
                {QStringLiteral("margin_usdt"), 100.0},
                {QStringLiteral("trigger_indicators"), QJsonArray{QStringLiteral("RSI"), QStringLiteral(" rsi ")}},
            },
            QJsonObject{
                {QStringLiteral("ledger_id"), QStringLiteral("ledger-2")},
                {QStringLiteral("interval"), QStringLiteral("5m")},
                {QStringLiteral("trade_id"), QStringLiteral("trade-2")},
                {QStringLiteral("qty"), 0.20},
                {QStringLiteral("margin_usdt"), 200.0},
            },
        }},
    };
    openPositionRecords.insert(
        QStringLiteral("BTCUSDT:L"),
        QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
            {QStringLiteral("side_key"), QStringLiteral("L")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("data"), QJsonObject{{QStringLiteral("qty"), 0.30}}},
        });
    const QJsonObject persistencePayload = NativePortfolio::buildAllocationPersistencePayload(
        QStringLiteral("live"),
        1770000000.0,
        entryAllocations,
        QJsonObject{
            {QStringLiteral("BTCUSDT:L"), openPositionRecords.value(QStringLiteral("BTCUSDT:L"))},
            {QStringLiteral("ADAUSDT:S"), QJsonObject{{QStringLiteral("status"), QStringLiteral("Closed")}}},
        });
    check(persistencePayload.value(QStringLiteral("version")).toInt() == 1,
          QStringLiteral("native allocation persistence should expose version 1"));
    check(persistencePayload.value(QStringLiteral("open_position_records")).toObject().size() == 1,
          QStringLiteral("native allocation persistence should persist active records only"));
    check(persistencePayload.value(QStringLiteral("entry_allocations")).toObject()
              .value(QStringLiteral("BTCUSDT:L")).toArray().at(0).toObject()
              .value(QStringLiteral("trigger_indicators")).toArray().size() == 1,
          QStringLiteral("native allocation persistence should de-duplicate trigger indicators"));

    const QJsonObject reduced = NativePortfolio::reducePositionAllocationState(
        entryAllocations,
        openPositionRecords,
        QStringLiteral("BTCUSDT"),
        QStringLiteral("L"),
        QStringLiteral("1m"),
        0.05);
    check(reduced.value(QStringLiteral("changed")).toBool(false),
          QStringLiteral("native allocation reduction should report changes for interval match"));
    check(reduced.value(QStringLiteral("closed_allocations")).toArray().size() == 1,
          QStringLiteral("native allocation reduction should return closed allocation slice"));
    check(entryAllocations.value(QStringLiteral("BTCUSDT:L")).toArray().size() == 2,
          QStringLiteral("native allocation reduction should keep survivor and partial allocation"));
    check(entryAllocations.value(QStringLiteral("BTCUSDT:L")).toArray().at(0).toObject().value(QStringLiteral("qty")).toDouble() == 0.05,
          QStringLiteral("native allocation reduction should keep residual quantity"));

    QJsonArray closeAllHistory;
    const QJsonObject closeAllResult = NativePortfolio::applyCloseAllToPositionState(
        openPositionRecords,
        entryAllocations,
        closeAllHistory,
        QJsonArray{QJsonObject{{QStringLiteral("symbol"), QStringLiteral("BTCUSDT")}, {QStringLiteral("ok"), true}}},
        QStringLiteral("2026-06-18T12:15:00+00:00"));
    check(closeAllResult.value(QStringLiteral("closed_count")).toInt() == 1,
          QStringLiteral("native close-all reconciliation should close matching open record"));
    check(!openPositionRecords.contains(QStringLiteral("BTCUSDT:L")),
          QStringLiteral("native close-all reconciliation should remove closed open record"));
    check(!entryAllocations.contains(QStringLiteral("BTCUSDT:L")),
          QStringLiteral("native close-all reconciliation should remove closed allocations"));
    check(closeAllHistory.at(0).toObject().value(QStringLiteral("status")).toString() == QStringLiteral("Closed"),
          QStringLiteral("native close-all reconciliation should add closed history snapshot"));

    QJsonObject metadataOpenRecords{
        {QStringLiteral("BTCUSDT:L"), QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
            {QStringLiteral("side_key"), QStringLiteral("L")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("interval"), QStringLiteral("5m")},
            {QStringLiteral("open_time"), QStringLiteral("2026-06-18T12:00:00Z")},
            {QStringLiteral("stop_loss_enabled"), true},
            {QStringLiteral("data"), QJsonObject{{QStringLiteral("trigger_desc"), QStringLiteral("RSI")}}},
            {QStringLiteral("allocations"), QJsonArray{QJsonObject{
                {QStringLiteral("ledger_id"), QStringLiteral("ledger-1")},
                {QStringLiteral("interval"), QStringLiteral("5m")},
            }}},
        }},
    };
    QJsonObject metadataAllocations;
    QJsonArray metadataHistory;
    QJsonObject metadataMissingCounts;
    QJsonObject metadataPendingClose{
        {QStringLiteral("BTCUSDT:L"), QStringLiteral("2026-06-18T12:00:01Z")},
    };
    const QJsonObject metadataLiveRecords{
        {QStringLiteral("BTCUSDT:L"), QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
            {QStringLiteral("side_key"), QStringLiteral("L")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("data"), QJsonObject{{QStringLiteral("qty"), 1.0}}},
        }},
    };
    const QJsonObject metadataPolicy{
        {QStringLiteral("positions_missing_threshold"), 2},
        {QStringLiteral("positions_missing_grace_seconds"), 30.0},
        {QStringLiteral("positions_missing_autoclose"), true},
    };
    NativePortfolio::reconcileMissingPositionState(
        metadataOpenRecords,
        metadataAllocations,
        metadataHistory,
        metadataMissingCounts,
        metadataPendingClose,
        metadataLiveRecords,
        metadataPolicy,
        QStringLiteral("2026-06-18T12:00:02Z"));
    const QJsonObject metadataCurrent = metadataOpenRecords.value(QStringLiteral("BTCUSDT:L")).toObject();
    check(!metadataPendingClose.contains(QStringLiteral("BTCUSDT:L")),
          QStringLiteral("native live reconciliation should clear a recovered pending close"));
    check(metadataCurrent.value(QStringLiteral("interval")).toString() == QStringLiteral("5m")
              && metadataCurrent.value(QStringLiteral("stop_loss_enabled")).toBool(false),
          QStringLiteral("native live reconciliation should preserve position metadata"));
    check(metadataCurrent.value(QStringLiteral("data")).toObject().value(QStringLiteral("trigger_desc")).toString()
              == QStringLiteral("RSI"),
          QStringLiteral("native live reconciliation should merge prior position data"));
    check(metadataCurrent.value(QStringLiteral("allocations")).toArray().size() == 1,
          QStringLiteral("native live reconciliation should preserve position allocations"));

    QJsonObject missingOpenRecords{
        {QStringLiteral("BTCUSDT:L"), QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
            {QStringLiteral("side_key"), QStringLiteral("L")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("open_time"), QStringLiteral("2026-06-18T12:00:00Z")},
        }},
    };
    QJsonObject missingCounts;
    QJsonObject pendingCloseTimes;
    QJsonArray missingHistory;
    QJsonObject emptyAllocations;
    const QJsonObject missingPolicy{
        {QStringLiteral("positions_missing_threshold"), 2},
        {QStringLiteral("positions_missing_grace_seconds"), 30.0},
        {QStringLiteral("positions_missing_autoclose"), true},
    };
    const QJsonObject missingFirst = NativePortfolio::reconcileMissingPositionState(
        missingOpenRecords,
        emptyAllocations,
        missingHistory,
        missingCounts,
        pendingCloseTimes,
        {},
        missingPolicy,
        QStringLiteral("2026-06-18T12:01:00Z"));
    check(missingFirst.value(QStringLiteral("waiting_count")).toInt() == 1,
          QStringLiteral("native missing-position policy should wait for Python threshold"));
    check(missingOpenRecords.contains(QStringLiteral("BTCUSDT:L")),
          QStringLiteral("native missing-position policy should preserve a below-threshold record"));
    const QJsonObject missingSecond = NativePortfolio::reconcileMissingPositionState(
        missingOpenRecords,
        emptyAllocations,
        missingHistory,
        missingCounts,
        pendingCloseTimes,
        {},
        missingPolicy,
        QStringLiteral("2026-06-18T12:01:01Z"));
    check(missingSecond.value(QStringLiteral("closed_count")).toInt() == 1,
          QStringLiteral("native missing-position policy should close at Python threshold"));
    check(missingHistory.size() == 1 && !missingOpenRecords.contains(QStringLiteral("BTCUSDT:L")),
          QStringLiteral("native missing-position policy should move confirmed rows to closed history"));

    QJsonObject graceOpenRecords{
        {QStringLiteral("ETHUSDT:S"), QJsonObject{
            {QStringLiteral("symbol"), QStringLiteral("ETHUSDT")},
            {QStringLiteral("side_key"), QStringLiteral("S")},
            {QStringLiteral("status"), QStringLiteral("Active")},
            {QStringLiteral("open_time"), QStringLiteral("2026-06-18T12:00:00Z")},
        }},
    };
    missingCounts = {};
    missingHistory = {};
    const QJsonObject gracePolicy{
        {QStringLiteral("positions_missing_threshold"), 1},
        {QStringLiteral("positions_missing_grace_seconds"), 120.0},
        {QStringLiteral("positions_missing_autoclose"), true},
    };
    const QJsonObject graceResult = NativePortfolio::reconcileMissingPositionState(
        graceOpenRecords,
        emptyAllocations,
        missingHistory,
        missingCounts,
        pendingCloseTimes,
        {},
        gracePolicy,
        QStringLiteral("2026-06-18T12:01:00Z"));
    check(graceResult.value(QStringLiteral("waiting_count")).toInt() == 1
              && missingHistory.isEmpty(),
          QStringLiteral("native missing-position policy should honor Python grace seconds"));

    QJsonObject serviceConfig{
        {QStringLiteral("symbols"), QJsonArray{QStringLiteral("ETHUSDT")}},
        {QStringLiteral("api_key"), QStringLiteral("exchange-key")},
        {QStringLiteral("api_secret"), QStringLiteral("exchange-secret")},
        {QStringLiteral("api_key_env"), QStringLiteral("BINANCE_API_KEY")},
        {QStringLiteral("llm"), QJsonObject{
            {QStringLiteral("llm_api_key"), QStringLiteral("llm-secret")},
            {QStringLiteral("token_env_var"), QStringLiteral("TOKEN_ENV")},
        }},
        {QStringLiteral("providers"), QJsonArray{
            QJsonObject{{QStringLiteral("authorization"), QStringLiteral("bearer-token")}},
            QJsonObject{{QStringLiteral("password"), QString()}},
        }},
    };
    const QJsonObject secretMetadata = NativeConfigPersistence::serviceConfigSecretMetadata(serviceConfig);
    check(secretMetadata.value(QStringLiteral("contains_secrets")).toBool(false),
          QStringLiteral("service config metadata should detect secret-bearing fields"));
    const QJsonArray secretFields = secretMetadata.value(QStringLiteral("secret_fields")).toArray();
    check(jsonArrayContains(secretFields, QStringLiteral("api_key")),
          QStringLiteral("service config secret fields should include api_key"));
    check(jsonArrayContains(secretFields, QStringLiteral("api_secret")),
          QStringLiteral("service config secret fields should include api_secret"));
    check(jsonArrayContains(secretFields, QStringLiteral("llm.llm_api_key")),
          QStringLiteral("service config secret fields should include nested llm_api_key"));
    check(jsonArrayContains(secretFields, QStringLiteral("providers[0].authorization")),
          QStringLiteral("service config secret fields should include array authorization path"));
    check(!jsonArrayContains(secretFields, QStringLiteral("api_key_env")),
          QStringLiteral("service config secret fields should exclude env indirection keys"));
    check(secretMetadata.value(QStringLiteral("secret_storage")).toString() == QStringLiteral("redacted-json-config"),
          QStringLiteral("service config secret storage should mirror Python redaction marker"));
    check(secretMetadata.value(QStringLiteral("secret_storage_warning")).toString().contains(QStringLiteral("redacted")),
          QStringLiteral("service config secret warning should mirror Python redaction warning"));

    const QDateTime savedAt = QDateTime::fromString(QStringLiteral("2026-06-18T12:00:00.000Z"), Qt::ISODateWithMs);
    const QJsonObject redactedPayload = NativeConfigPersistence::buildServiceConfigPersistencePayload(
        serviceConfig,
        savedAt,
        false);
    check(redactedPayload.value(QStringLiteral("kind")).toString() == QStringLiteral("trading-bot-service-config"),
          QStringLiteral("service config payload should include Python file kind"));
    check(redactedPayload.value(QStringLiteral("format_version")).toInt() == 1,
          QStringLiteral("service config payload should include Python format version"));
    check(!redactedPayload.value(QStringLiteral("inline_secrets_persisted")).toBool(true),
          QStringLiteral("service config payload should not persist inline secrets by default"));
    const QJsonObject redactedConfig = redactedPayload.value(QStringLiteral("config")).toObject();
    check(redactedConfig.value(QStringLiteral("api_key")).toString() == QString(),
          QStringLiteral("service config payload should blank api_key by default"));
    check(redactedConfig.value(QStringLiteral("api_secret")).toString() == QString(),
          QStringLiteral("service config payload should blank api_secret by default"));
    check(redactedConfig.value(QStringLiteral("llm")).toObject().value(QStringLiteral("llm_api_key")).toString() == QString(),
          QStringLiteral("service config payload should blank nested llm_api_key by default"));
    check(redactedConfig.value(QStringLiteral("providers")).toArray().at(0).toObject().value(QStringLiteral("authorization")).toString() == QString(),
          QStringLiteral("service config payload should blank array authorization secret by default"));
    check(redactedConfig.value(QStringLiteral("api_key_env")).toString() == QStringLiteral("BINANCE_API_KEY"),
          QStringLiteral("service config payload should preserve env indirection values"));

    const QJsonObject inlinePayload = NativeConfigPersistence::buildServiceConfigPersistencePayload(
        serviceConfig,
        savedAt,
        true);
    check(!inlinePayload.value(QStringLiteral("inline_secrets_persisted")).toBool(true),
          QStringLiteral("service config payload should ignore legacy inline secret persistence requests"));
    check(inlinePayload.value(QStringLiteral("config")).toObject().value(QStringLiteral("api_key")).toString()
              == QString(),
          QStringLiteral("service config payload should redact api_key despite a legacy override"));

    const NativeConfigPersistence::ServiceConfigLoadResult legacySecretConfig =
        NativeConfigPersistence::coerceServiceConfigPersistencePayload(
            QJsonObject{
                {QStringLiteral("kind"), QStringLiteral("trading-bot-service-config")},
                {QStringLiteral("format_version"), 1},
                {QStringLiteral("config"), QJsonObject{
                    {QStringLiteral("symbols"), QJsonArray{QStringLiteral("ETHUSDT")}},
                    {QStringLiteral("api_key"), QStringLiteral("legacy-exchange-key")},
                    {QStringLiteral("api_secret"), QStringLiteral("legacy-exchange-secret")},
                }},
            },
            QStringLiteral("service-config.json"));
    check(legacySecretConfig.ok,
          QStringLiteral("legacy service config with inline secrets should load after redaction"));
    check(legacySecretConfig.config.value(QStringLiteral("api_key")).toString().isEmpty(),
          QStringLiteral("legacy service config loading should redact api_key"));
    check(legacySecretConfig.config.value(QStringLiteral("api_secret")).toString().isEmpty(),
          QStringLiteral("legacy service config loading should redact api_secret"));

    const QJsonObject legacyEnvelope{
        {QStringLiteral("kind"), QStringLiteral("trading-bot-service-config")},
        {QStringLiteral("format_version"), 0},
        {QStringLiteral("saved_at"), QStringLiteral("2026-06-18T12:00:00+00:00")},
        {QStringLiteral("config"), QJsonObject{{QStringLiteral("symbols"), QJsonArray{QStringLiteral("ETHUSDT")}}}},
    };
    const NativeConfigPersistence::ServiceConfigLoadResult migrated =
        NativeConfigPersistence::coerceServiceConfigPersistencePayload(legacyEnvelope, QStringLiteral("service-config.json"));
    check(migrated.ok, QStringLiteral("old service config envelope should be accepted for migration"));
    check(migrated.metadata.value(QStringLiteral("format_version")).toInt() == 1,
          QStringLiteral("old service config envelope should report current format version"));
    check(migrated.metadata.value(QStringLiteral("migrated_from_format_version")).toInt(-1) == 0,
          QStringLiteral("old service config envelope should report migrated source version"));

    const QJsonObject futureEnvelope{
        {QStringLiteral("kind"), QStringLiteral("trading-bot-service-config")},
        {QStringLiteral("format_version"), 999},
        {QStringLiteral("config"), QJsonObject{{QStringLiteral("symbols"), QJsonArray{QStringLiteral("ETHUSDT")}}}},
    };
    const NativeConfigPersistence::ServiceConfigLoadResult rejectedFuture =
        NativeConfigPersistence::coerceServiceConfigPersistencePayload(futureEnvelope, QStringLiteral("service-config.json"));
    check(!rejectedFuture.ok && rejectedFuture.error.contains(QStringLiteral("unsupported format_version")),
          QStringLiteral("future service config envelope should be rejected"));

    const QJsonObject persistedServiceConfig{
        {QStringLiteral("symbols"), QJsonArray{QStringLiteral("ETHUSDT")}},
        {QStringLiteral("intervals"), QJsonArray{QStringLiteral("1h")}},
        {QStringLiteral("api_key"), QStringLiteral("exchange-key")},
        {QStringLiteral("api_secret"), QStringLiteral("exchange-secret")},
        {QStringLiteral("llm_api_key"), QStringLiteral("llm-secret")},
    };
    const QString serviceConfigPath = dir.filePath(QStringLiteral("service-config.json"));
    const QJsonObject savedConfigStatus = NativeConfigPersistence::writeServiceConfigFile(
        persistedServiceConfig,
        serviceConfigPath,
        true,
        false,
        savedAt);
    check(savedConfigStatus.value(QStringLiteral("exists")).toBool(false),
          QStringLiteral("service config save status should report exists"));
    check(savedConfigStatus.value(QStringLiteral("contains_secrets")).toBool(false),
          QStringLiteral("service config save status should report secret-bearing file"));
    check(!savedConfigStatus.value(QStringLiteral("inline_secrets_persisted")).toBool(true),
          QStringLiteral("service config save status should report default inline redaction"));
    const QString persistedConfigText = readText(serviceConfigPath);
    check(persistedConfigText.contains(QStringLiteral("trading-bot-service-config")),
          QStringLiteral("service config file should include Python envelope kind"));
    check(!persistedConfigText.contains(QStringLiteral("exchange-key")),
          QStringLiteral("service config file should not persist inline api_key by default"));
    const NativeConfigPersistence::ServiceConfigLoadResult loadedConfig =
        NativeConfigPersistence::loadServiceConfigFile(serviceConfigPath);
    check(loadedConfig.ok, QStringLiteral("service config file should load after save"));
    check(loadedConfig.config.value(QStringLiteral("symbols")).toArray().at(0).toString() == QStringLiteral("ETHUSDT"),
          QStringLiteral("service config load should return persisted config object"));
    const QJsonObject fileStatus = NativeConfigPersistence::serviceConfigFileStatus(serviceConfigPath);
    NativeConfigPersistence::ServiceConfigRuntimeState runtimeState;
    runtimeState.loaded = true;
    runtimeState.dirty = false;
    runtimeState.lastLoadedAt = QStringLiteral("2026-06-18T12:05:00+00:00");
    runtimeState.lastSavedAt = QStringLiteral("2026-06-18T12:00:00+00:00");
    const QJsonObject runtimeStatus =
        NativeConfigPersistence::buildServiceConfigPersistenceStatus(fileStatus, runtimeState);
    check(runtimeStatus.value(QStringLiteral("loaded")).toBool(false),
          QStringLiteral("service config runtime status should expose loaded state"));
    check(!runtimeStatus.value(QStringLiteral("dirty")).toBool(true),
          QStringLiteral("service config runtime status should expose clean dirty state"));
    check(runtimeStatus.value(QStringLiteral("last_saved_at")).toString() == QStringLiteral("2026-06-18T12:00:00+00:00"),
          QStringLiteral("service config runtime status should expose last_saved_at"));
    check(runtimeStatus.value(QStringLiteral("contains_secrets")).toBool(false),
          QStringLiteral("service config file status should surface secret metadata"));

    bool blockedUnsafePath = false;
    try {
        NativeConfigPersistence::writeServiceConfigFile(persistedServiceConfig, serviceConfigPath, false, false, savedAt);
    } catch (const std::runtime_error &exc) {
        blockedUnsafePath = QString::fromStdString(exc.what()).contains(QStringLiteral("BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH"));
    }
    check(blockedUnsafePath,
          QStringLiteral("explicit service config paths outside safe root should require trusted override"));

    const NativeConfigPersistence::ServiceConfigValidationResult normalizedConfig =
        NativeConfigPersistence::validateServiceRuntimeConfig(QJsonObject{
            {QStringLiteral("symbols"), QJsonArray{QStringLiteral("ethusdt"), QStringLiteral("ETHUSDT")}},
            {QStringLiteral("intervals"), QJsonArray{QStringLiteral("1M"), QStringLiteral("2 hours")}},
            {QStringLiteral("mode"), QStringLiteral("live")},
            {QStringLiteral("account_type"), QStringLiteral("futures")},
            {QStringLiteral("margin_mode"), QStringLiteral("cross")},
            {QStringLiteral("position_mode"), QStringLiteral("oneway")},
            {QStringLiteral("assets_mode"), QStringLiteral("multi-asset")},
            {QStringLiteral("account_mode"), QStringLiteral("portfolio margin")},
            {QStringLiteral("side"), QStringLiteral("sell")},
            {QStringLiteral("order_type"), QStringLiteral("limit")},
            {QStringLiteral("tif"), QStringLiteral("ioc")},
            {QStringLiteral("position_pct"), QStringLiteral("2.5")},
            {QStringLiteral("connector_backend"), QStringLiteral("CCXT (Unified)")},
            {QStringLiteral("indicator_source"), QStringLiteral("binance futures")},
            {QStringLiteral("theme"), QStringLiteral("green")},
            {QStringLiteral("design"), QStringLiteral("workstation")},
            {QStringLiteral("selected_exchange"), QStringLiteral("kucoin")},
            {QStringLiteral("llm_provider"), QStringLiteral("chatgpt")},
            {QStringLiteral("llm_use_for"), QStringLiteral("risk_review")},
            {QStringLiteral("llm_reasoning_effort"), QStringLiteral("extra-high")},
            {QStringLiteral("chart"), QJsonObject{
                {QStringLiteral("market"), QStringLiteral("spot")},
                {QStringLiteral("view_mode"), QStringLiteral("TradingView Lightweight")},
                {QStringLiteral("symbol"), QStringLiteral("ethusdt")},
                {QStringLiteral("interval"), QStringLiteral("1M")},
                {QStringLiteral("auto_follow"), QStringLiteral("yes")},
            }},
            {QStringLiteral("backtest"), QJsonObject{
                {QStringLiteral("symbols"), QJsonArray{QStringLiteral("btcusdt"), QStringLiteral("BTCUSDT")}},
                {QStringLiteral("intervals"), QJsonArray{QStringLiteral("15 minutes"), QStringLiteral("1M")}},
                {QStringLiteral("capital"), QStringLiteral("1000")},
                {QStringLiteral("execution_backend"), QStringLiteral("desktop-local")},
                {QStringLiteral("logic"), QStringLiteral("or")},
                {QStringLiteral("symbol_source"), QStringLiteral("futures")},
                {QStringLiteral("start_date"), QStringLiteral("2026-01-01")},
                {QStringLiteral("end_date"), QStringLiteral("2026-02-01")},
                {QStringLiteral("position_pct"), QStringLiteral("2.0")},
                {QStringLiteral("side"), QStringLiteral("both")},
                {QStringLiteral("margin_mode"), QStringLiteral("isolated")},
                {QStringLiteral("position_mode"), QStringLiteral("hedge")},
                {QStringLiteral("assets_mode"), QStringLiteral("single-asset mode")},
                {QStringLiteral("account_mode"), QStringLiteral("classic trading")},
                {QStringLiteral("connector_backend"), QStringLiteral("binance-sdk-spot")},
                {QStringLiteral("leverage"), 20},
                {QStringLiteral("mdd_logic"), QStringLiteral("per_trade")},
                {QStringLiteral("scan_scope"), QStringLiteral("top_n")},
                {QStringLiteral("scan_top_n"), 200},
                {QStringLiteral("scan_mdd_limit"), 20},
                {QStringLiteral("scan_auto_apply"), QStringLiteral("false")},
                {QStringLiteral("optimizer_mode"), QStringLiteral("pairs")},
                {QStringLiteral("optimizer_metric"), QStringLiteral("roi-percent-mdd")},
                {QStringLiteral("optimizer_combo_size"), 2},
                {QStringLiteral("optimizer_max_duration_seconds"), 7200},
                {QStringLiteral("optimizer_min_trades"), 1},
                {QStringLiteral("fee_bps"), 5.0},
                {QStringLiteral("slippage_bps"), 2.0},
                {QStringLiteral("template"), QJsonObject{}},
                {QStringLiteral("indicators"), QJsonObject{}},
                {QStringLiteral("stop_loss"), QJsonObject{
                    {QStringLiteral("mode"), QStringLiteral("percent")},
                    {QStringLiteral("scope"), QStringLiteral("entire_account")},
                }},
            }},
            {QStringLiteral("runtime_symbol_interval_pairs"), QJsonArray{
                QJsonObject{
                    {QStringLiteral("symbol"), QStringLiteral("btcusdt")},
                    {QStringLiteral("interval"), QStringLiteral("15 minutes")},
                    {QStringLiteral("strategy_controls"), QJsonObject{
                        {QStringLiteral("side"), QStringLiteral("buy")},
                        {QStringLiteral("leverage"), 20},
                        {QStringLiteral("loop_interval_override"), QStringLiteral("1 hour")},
                        {QStringLiteral("stop_loss"), QJsonObject{{QStringLiteral("scope"), QStringLiteral("bad-scope")}}},
                    }},
                },
            }},
        });
    check(normalizedConfig.ok, QStringLiteral("native service config validation should accept Python-compatible runtime values"));
    check(normalizedConfig.config.value(QStringLiteral("symbols")).toArray().size() == 1,
          QStringLiteral("native service config validation should de-duplicate symbols like Python"));
    check(normalizedConfig.config.value(QStringLiteral("symbols")).toArray().at(0).toString() == QStringLiteral("ETHUSDT"),
          QStringLiteral("native service config validation should uppercase symbols like Python"));
    check(normalizedConfig.config.value(QStringLiteral("intervals")).toArray().at(0).toString() == QStringLiteral("1mo"),
          QStringLiteral("native service config validation should normalize uppercase month intervals like Python"));
    check(normalizedConfig.config.value(QStringLiteral("mode")).toString() == QStringLiteral("live"),
          QStringLiteral("native service config validation should preserve Python text fields"));
    check(normalizedConfig.config.value(QStringLiteral("account_type")).toString() == QStringLiteral("Futures"),
          QStringLiteral("native service config validation should normalize account type choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("margin_mode")).toString() == QStringLiteral("Cross"),
          QStringLiteral("native service config validation should normalize margin mode choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("position_mode")).toString() == QStringLiteral("One-way"),
          QStringLiteral("native service config validation should normalize position mode aliases from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("assets_mode")).toString() == QStringLiteral("Multi-Assets"),
          QStringLiteral("native service config validation should normalize assets mode aliases from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("account_mode")).toString() == QStringLiteral("Portfolio Margin"),
          QStringLiteral("native service config validation should normalize account mode choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("side")).toString() == QStringLiteral("SELL"),
          QStringLiteral("native service config validation should normalize side choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("order_type")).toString() == QStringLiteral("LIMIT"),
          QStringLiteral("native service config validation should normalize order type choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("tif")).toString() == QStringLiteral("IOC"),
          QStringLiteral("native service config validation should normalize time-in-force choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("connector_backend")).toString() == QStringLiteral("CCXT (Unified)"),
          QStringLiteral("native service config validation should preserve connector backend text like Python"));
    check(normalizedConfig.config.value(QStringLiteral("indicator_source")).toString() == QStringLiteral("binance futures"),
          QStringLiteral("native service config validation should preserve indicator source text like Python"));
    check(normalizedConfig.config.value(QStringLiteral("theme")).toString() == QStringLiteral("green"),
          QStringLiteral("native service config validation should preserve theme text like Python"));
    check(normalizedConfig.config.value(QStringLiteral("design")).toString() == QStringLiteral("workstation"),
          QStringLiteral("native service config validation should preserve design text like Python"));
    check(normalizedConfig.config.value(QStringLiteral("selected_exchange")).toString() == QStringLiteral("kucoin"),
          QStringLiteral("native service config validation should preserve exchange text like Python"));
    check(normalizedConfig.config.value(QStringLiteral("llm_provider")).toString() == QStringLiteral("openai"),
          QStringLiteral("native service config validation should normalize LLM provider aliases from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("llm_use_for")).toString() == QStringLiteral("risk_review"),
          QStringLiteral("native service config validation should normalize LLM use choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("llm_reasoning_effort")).toString() == QStringLiteral("xhigh"),
          QStringLiteral("native service config validation should normalize LLM reasoning aliases from Python source"));
    const QJsonObject normalizedChart = normalizedConfig.config.value(QStringLiteral("chart")).toObject();
    check(normalizedChart.value(QStringLiteral("market")).toString() == QStringLiteral("Spot"),
          QStringLiteral("native service config validation should normalize chart market choices from Python source"));
    check(normalizedChart.value(QStringLiteral("view_mode")).toString() == QStringLiteral("lightweight"),
          QStringLiteral("native service config validation should normalize chart view choices from Python source"));
    check(normalizedChart.value(QStringLiteral("symbol")).toString() == QStringLiteral("ETHUSDT"),
          QStringLiteral("native service config validation should normalize chart symbol values"));
    check(normalizedChart.value(QStringLiteral("interval")).toString() == QStringLiteral("1mo"),
          QStringLiteral("native service config validation should normalize chart intervals"));
    check(normalizedChart.value(QStringLiteral("auto_follow")).toBool(false),
          QStringLiteral("native service config validation should coerce chart booleans"));
    const QJsonObject normalizedBacktest = normalizedConfig.config.value(QStringLiteral("backtest")).toObject();
    check(normalizedBacktest.value(QStringLiteral("symbols")).toArray().size() == 1,
          QStringLiteral("native service config validation should de-duplicate backtest symbols"));
    check(normalizedBacktest.value(QStringLiteral("symbols")).toArray().at(0).toString() == QStringLiteral("BTCUSDT"),
          QStringLiteral("native service config validation should uppercase backtest symbols"));
    check(normalizedBacktest.value(QStringLiteral("intervals")).toArray().at(0).toString() == QStringLiteral("15m"),
          QStringLiteral("native service config validation should normalize backtest intervals"));
    check(normalizedBacktest.value(QStringLiteral("execution_backend")).toString() == QStringLiteral("local"),
          QStringLiteral("native service config validation should normalize backtest execution backend aliases"));
    check(normalizedBacktest.value(QStringLiteral("logic")).toString() == QStringLiteral("OR"),
          QStringLiteral("native service config validation should normalize backtest signal logic choices"));
    check(normalizedBacktest.value(QStringLiteral("symbol_source")).toString() == QStringLiteral("futures"),
          QStringLiteral("native service config validation should normalize backtest symbol source choices"));
    check(normalizedBacktest.value(QStringLiteral("side")).toString() == QStringLiteral("BOTH"),
          QStringLiteral("native service config validation should normalize backtest side choices"));
    check(normalizedBacktest.value(QStringLiteral("margin_mode")).toString() == QStringLiteral("Isolated"),
          QStringLiteral("native service config validation should normalize backtest margin mode choices"));
    check(normalizedBacktest.value(QStringLiteral("position_mode")).toString() == QStringLiteral("Hedge"),
          QStringLiteral("native service config validation should normalize backtest position mode choices"));
    check(normalizedBacktest.value(QStringLiteral("assets_mode")).toString() == QStringLiteral("Single-Asset"),
          QStringLiteral("native service config validation should normalize backtest assets mode labels"));
    check(normalizedBacktest.value(QStringLiteral("account_mode")).toString() == QStringLiteral("Classic Trading"),
          QStringLiteral("native service config validation should normalize backtest account mode choices"));
    check(normalizedBacktest.value(QStringLiteral("connector_backend")).toString() == QStringLiteral("binance-sdk-spot"),
          QStringLiteral("native service config validation should normalize backtest connector choices"));
    check(normalizedBacktest.value(QStringLiteral("mdd_logic")).toString() == QStringLiteral("per_trade"),
          QStringLiteral("native service config validation should normalize backtest MDD logic labels"));
    check(normalizedBacktest.value(QStringLiteral("scan_scope")).toString() == QStringLiteral("top_n"),
          QStringLiteral("native service config validation should normalize optimizer scan scope choices"));
    check(!normalizedBacktest.value(QStringLiteral("scan_auto_apply")).toBool(true),
          QStringLiteral("native service config validation should coerce optimizer scan booleans"));
    check(normalizedBacktest.value(QStringLiteral("optimizer_mode")).toString() == QStringLiteral("pairs"),
          QStringLiteral("native service config validation should normalize optimizer mode choices"));
    check(normalizedBacktest.value(QStringLiteral("optimizer_metric")).toString() == QStringLiteral("roi_percent_mdd"),
          QStringLiteral("native service config validation should normalize optimizer metric aliases"));
    check(normalizedBacktest.value(QStringLiteral("optimizer_max_duration_seconds")).toInt() == 7200,
          QStringLiteral("native service config validation should preserve optimizer duration like Python"));
    check(qFuzzyCompare(normalizedBacktest.value(QStringLiteral("fee_bps")).toDouble(), 5.0),
          QStringLiteral("native service config validation should preserve Python fee basis points"));
    check(qFuzzyCompare(normalizedBacktest.value(QStringLiteral("slippage_bps")).toDouble(), 2.0),
          QStringLiteral("native service config validation should preserve Python slippage basis points"));
    const QJsonObject normalizedBacktestStop = normalizedBacktest.value(QStringLiteral("stop_loss")).toObject();
    check(normalizedBacktestStop.value(QStringLiteral("mode")).toString() == QStringLiteral("percent"),
          QStringLiteral("native service config validation should normalize backtest stop-loss modes from Python source"));
    check(normalizedBacktestStop.value(QStringLiteral("scope")).toString() == QStringLiteral("entire_account"),
          QStringLiteral("native service config validation should normalize backtest stop-loss scopes from Python source"));
    const QJsonObject normalizedPairControls =
        normalizedConfig.config.value(QStringLiteral("runtime_symbol_interval_pairs")).toArray().at(0).toObject()
            .value(QStringLiteral("strategy_controls")).toObject();
    check(normalizedPairControls.value(QStringLiteral("side")).toString() == QStringLiteral("BUY"),
          QStringLiteral("native service config validation should normalize symbol-pair side choices"));
    check(normalizedPairControls.value(QStringLiteral("loop_interval_override")).toString() == QStringLiteral("1h"),
          QStringLiteral("native service config validation should normalize symbol-pair loop interval overrides"));
    check(normalizedPairControls.value(QStringLiteral("stop_loss")).toObject().value(QStringLiteral("scope")).toString() == QStringLiteral("per_trade"),
          QStringLiteral("native service config validation should normalize symbol-pair stop-loss scopes"));

    const NativeConfigPersistence::ServiceConfigValidationResult invalidConfig =
        NativeConfigPersistence::validateServiceRuntimeConfig(QJsonObject{
            {QStringLiteral("unknown_key"), true},
            {QStringLiteral("symbols"), QJsonArray{QStringLiteral("BAD SYMBOL")}},
            {QStringLiteral("intervals"), QJsonArray{QStringLiteral("0m")}},
            {QStringLiteral("leverage"), 126},
            {QStringLiteral("stop_loss"), QStringLiteral("not-object")},
            {QStringLiteral("llm_provider"), QStringLiteral("ghost-ai")},
            {QStringLiteral("chart"), QJsonObject{{QStringLiteral("view_mode"), QStringLiteral("external")}}},
            {QStringLiteral("backtest"), QJsonObject{{QStringLiteral("symbol_source"), QStringLiteral("margin")}}},
        });
    check(!invalidConfig.ok,
          QStringLiteral("native service config validation should reject values Python validate_runtime_config rejects"));
    const QString invalidMessage = NativeConfigPersistence::formatServiceConfigValidationIssues(invalidConfig.issues);
    check(invalidMessage.contains(QStringLiteral("unknown_key: is not a supported config key")),
          QStringLiteral("native config validation should report unsupported keys"));
    check(invalidMessage.contains(QStringLiteral("leverage: must be between 1 and 125")),
          QStringLiteral("native config validation should report leverage bounds"));
    check(invalidMessage.contains(QStringLiteral("llm_provider: must be one of:")),
          QStringLiteral("native config validation should report invalid LLM providers"));
    check(invalidMessage.contains(QStringLiteral("chart.view_mode: must be one of:")),
          QStringLiteral("native config validation should report invalid chart view choices"));
    check(!invalidMessage.contains(QStringLiteral("backtest.symbol_source:")),
          QStringLiteral("native config validation should preserve Python-compatible backtest symbol sources"));

    NativeOrderSafety::OrderAuditLogConfig config;
    config.path = dir.filePath(QStringLiteral("order_audit.jsonl"));
    config.maxBytes = 1;
    config.backupCount = 2;

    const QVector<QPair<QString, QString>> params = {
        {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
        {QStringLiteral("side"), QStringLiteral("BUY")},
        {QStringLiteral("type"), QStringLiteral("MARKET")},
        {QStringLiteral("quantity"), QStringLiteral("0.10000000")},
        {QStringLiteral("apiSecret"), QStringLiteral("super-secret-value")},
    };
    QJsonObject first = NativeOrderSafety::buildOrderAuditEvent(
        QStringLiteral("order_intent"),
        QStringLiteral("futures"),
        params,
        QDateTime::fromString(QStringLiteral("2026-06-18T12:00:00.000Z"), Qt::ISODateWithMs),
        QStringLiteral("native-test"));
    first.insert(QStringLiteral("error"), QStringLiteral("signature=super-secret-value"));

    const QJsonObject firstStatus = NativeOrderSafety::appendOrderAuditEvent(first, config);
    check(firstStatus.value(QStringLiteral("state")).toString() == QStringLiteral("ready"),
          QStringLiteral("first audit append should be ready"));
    check(firstStatus.value(QStringLiteral("write_ok")).toBool(false),
          QStringLiteral("first audit append should report write_ok"));
    const QJsonObject currentStatus = NativeOrderSafety::currentOrderAuditStatus(config);
    check(currentStatus.value(QStringLiteral("path")).toString() == firstStatus.value(QStringLiteral("path")).toString(),
          QStringLiteral("current audit status should expose the latest append status path"));
    const QString firstText = readText(config.path);
    check(firstText.contains(QStringLiteral("order_intent")),
          QStringLiteral("audit line should include event name"));
    check(firstText.contains(QStringLiteral("BTCUSDT")),
          QStringLiteral("audit line should include symbol"));
    check(!firstText.contains(QStringLiteral("super-secret-value")),
          QStringLiteral("audit line should redact sensitive values"));
    check(firstText.contains(QStringLiteral("<redacted>")),
          QStringLiteral("audit line should include redaction marker"));

    QJsonObject accepted = NativeOrderSafety::buildOrderAuditEvent(
        QStringLiteral("order_accepted"),
        QStringLiteral("futures"),
        params,
        QDateTime::fromString(QStringLiteral("2026-06-18T12:00:01.000Z"), Qt::ISODateWithMs),
        QStringLiteral("native-test"));
    accepted.insert(QStringLiteral("result"), QJsonObject{
        {QStringLiteral("ok"), true},
        {QStringLiteral("orderId"), QStringLiteral("12345")},
        {QStringLiteral("status"), QStringLiteral("FILLED")},
    });
    NativeOrderSafety::appendOrderAuditEvent(accepted, config);

    QJsonObject rejected = NativeOrderSafety::buildOrderAuditEvent(
        QStringLiteral("order_rejected"),
        QStringLiteral("futures"),
        params,
        QDateTime::fromString(QStringLiteral("2026-06-18T12:00:02.000Z"), Qt::ISODateWithMs),
        QStringLiteral("native-test"));
    rejected.insert(QStringLiteral("error"), QStringLiteral("apiSecret=super-secret-value"));
    NativeOrderSafety::appendOrderAuditEvent(rejected, config);

    check(QFile::exists(config.path), QStringLiteral("active audit log should exist after rotation"));
    check(QFile::exists(NativeOrderSafety::orderAuditBackupPath(config.path, 1)),
          QStringLiteral("first audit backup should exist after rotation"));
    check(QFile::exists(NativeOrderSafety::orderAuditBackupPath(config.path, 2)),
          QStringLiteral("second audit backup should exist after repeated rotation"));

    NativeOrderSafety::OrderAuditLogConfig disabled;
    disabled.enabled = false;
    disabled.path = dir.filePath(QStringLiteral("disabled_order_audit.jsonl"));
    const QJsonObject disabledStatus = NativeOrderSafety::appendOrderAuditEvent(first, disabled);
    check(disabledStatus.value(QStringLiteral("state")).toString() == QStringLiteral("disabled"),
          QStringLiteral("disabled audit status should be disabled"));
    check(!QFile::exists(disabled.path), QStringLiteral("disabled audit should not create a file"));

    const QDateTime preflightNow = QDateTime::fromString(QStringLiteral("2026-06-18T12:10:00.000Z"), Qt::ISODateWithMs);
    auto freshness = [preflightNow](
                         int ageSeconds,
                         double maxAgeSeconds,
                         const QString &state = {},
                         const QString &source = {},
                         const QString &timestampField = QStringLiteral("generated_at")) {
        NativeOrderSafety::OperationalFreshnessInput input;
        input.timestampField = timestampField;
        input.timestamp = preflightNow.addSecs(-ageSeconds);
        input.maxAgeSeconds = maxAgeSeconds;
        input.shouldWarn = true;
        input.state = state;
        input.source = source;
        return input;
    };

    NativeOrderSafety::OperationalPreflightInput livePreflight;
    livePreflight.mode = QStringLiteral("Live");
    livePreflight.health = QStringLiteral("ok");
    livePreflight.generatedAt = preflightNow;
    livePreflight.exchangeConnector = freshness(121, 120.0, QStringLiteral("ready"), QStringLiteral("service"));
    livePreflight.execution = freshness(
        11,
        10.0,
        QStringLiteral("running"),
        QStringLiteral("runtime"),
        QStringLiteral("heartbeat_at"));
    livePreflight.account = freshness(301, 300.0, {}, QStringLiteral("account"));
    livePreflight.portfolio = freshness(301, 300.0, {}, QStringLiteral("portfolio"));
    livePreflight.connectorOrderCircuitBreaker = QJsonObject{
        {QStringLiteral("active"), true},
        {QStringLiteral("state"), QStringLiteral("open")},
        {QStringLiteral("message"), QStringLiteral("apiSecret=super-secret-value")},
    };

    const QJsonObject blockedPreflight = NativeOrderSafety::buildOperationalPreflightSnapshot(livePreflight);
    check(blockedPreflight.value(QStringLiteral("state")).toString() == QStringLiteral("blocked"),
          QStringLiteral("live operational preflight should be blocked"));
    check(blockedPreflight.value(QStringLiteral("message")).toString()
              == QStringLiteral("Live preflight blocked. Review the reasons before starting or submitting orders."),
          QStringLiteral("blocked preflight should use Python source blocked message"));
    check(!NativeOrderSafety::operationalPreflightStartAllowed(blockedPreflight),
          QStringLiteral("live start gate should be blocked"));
    check(!NativeOrderSafety::operationalPreflightOrdersAllowed(blockedPreflight),
          QStringLiteral("live order gate should be blocked"));
    check(blockedPreflight.value(QStringLiteral("live_mode")).toBool(false),
          QStringLiteral("live preflight should report live_mode"));
    const QJsonArray blockedReasons = blockedPreflight.value(QStringLiteral("reasons")).toArray();
    check(jsonArrayContains(blockedReasons, QStringLiteral("operational health is error")),
          QStringLiteral("active connector circuit should force operational health error"));
    check(jsonArrayContains(
              blockedReasons,
              QStringLiteral("critical snapshots are stale: exchange connector, account, portfolio, execution heartbeat")),
          QStringLiteral("start gate should include stale execution heartbeat"));
    check(jsonArrayContains(
              blockedReasons,
              QStringLiteral("critical snapshots are stale: exchange connector, account, portfolio")),
          QStringLiteral("order gate should include stale account/portfolio/connector snapshots"));
    check(jsonArrayContains(
              blockedPreflight.value(QStringLiteral("critical_stale")).toObject().value(QStringLiteral("start")).toArray(),
              QStringLiteral("execution heartbeat")),
          QStringLiteral("critical_stale.start should include execution heartbeat"));
    check(!jsonArrayContains(
              blockedPreflight.value(QStringLiteral("critical_stale")).toObject().value(QStringLiteral("orders")).toArray(),
              QStringLiteral("execution heartbeat")),
          QStringLiteral("critical_stale.orders should not require execution heartbeat"));

    NativeOrderSafety::OperationalPreflightInput demoPreflight = livePreflight;
    demoPreflight.mode = QStringLiteral("Demo/Testnet");
    const QJsonObject warningPreflight = NativeOrderSafety::buildOperationalPreflightSnapshot(demoPreflight);
    check(warningPreflight.value(QStringLiteral("state")).toString() == QStringLiteral("warning"),
          QStringLiteral("demo/test operational preflight should warn instead of block"));
    check(NativeOrderSafety::operationalPreflightStartAllowed(warningPreflight),
          QStringLiteral("demo/test start should remain allowed"));
    check(NativeOrderSafety::operationalPreflightOrdersAllowed(warningPreflight),
          QStringLiteral("demo/test order should remain allowed"));
    const QJsonArray warningReasons = warningPreflight.value(QStringLiteral("reasons")).toArray();
    check(jsonArrayContains(warningReasons, QStringLiteral("Demo/test mode start remains allowed.")),
          QStringLiteral("demo/test preflight should include start allowance reason"));
    check(jsonArrayContains(warningReasons, QStringLiteral("Demo/test mode order remains allowed.")),
          QStringLiteral("demo/test preflight should include order allowance reason"));

    NativeOrderSafety::OperationalPreflightInput disabledGatePreflight = livePreflight;
    disabledGatePreflight.startGateEnabled = false;
    disabledGatePreflight.orderGateEnabled = false;
    const QJsonObject disabledPreflight = NativeOrderSafety::buildOperationalPreflightSnapshot(disabledGatePreflight);
    check(disabledPreflight.value(QStringLiteral("state")).toString() == QStringLiteral("warning"),
          QStringLiteral("disabled preflight gates should report warning"));
    check(NativeOrderSafety::operationalPreflightStartAllowed(disabledPreflight),
          QStringLiteral("disabled start gate should remain allowed"));
    check(NativeOrderSafety::operationalPreflightOrdersAllowed(disabledPreflight),
          QStringLiteral("disabled order gate should remain allowed"));
    check(!disabledPreflight.value(QStringLiteral("start")).toObject().value(QStringLiteral("gate_enabled")).toBool(true),
          QStringLiteral("disabled start gate should report gate_enabled=false"));
    check(!disabledPreflight.value(QStringLiteral("orders")).toObject().value(QStringLiteral("gate_enabled")).toBool(true),
          QStringLiteral("disabled order gate should report gate_enabled=false"));
    const QJsonArray disabledReasons = disabledPreflight.value(QStringLiteral("reasons")).toArray();
    check(jsonArrayContains(disabledReasons, QStringLiteral("Operational live start safety gate is disabled.")),
          QStringLiteral("disabled preflight should include start disabled reason"));
    check(jsonArrayContains(disabledReasons, QStringLiteral("Operational live order safety gate is disabled.")),
          QStringLiteral("disabled preflight should include order disabled reason"));

    const auto checkStopIntentReference = [&](std::string_view referenceJson,
                                               const QString &referenceLabel) {
        const QByteArray stopIntentReferenceJson(
            referenceJson.data(),
            static_cast<qsizetype>(referenceJson.size()));
        QJsonParseError stopIntentParseError;
        const QJsonDocument stopIntentDocument = QJsonDocument::fromJson(
            stopIntentReferenceJson,
            &stopIntentParseError);
        check(stopIntentParseError.error == QJsonParseError::NoError
                  && stopIntentDocument.isObject(),
              QStringLiteral("generated Python %1 stop intent reference should be valid JSON: %2")
                  .arg(referenceLabel, stopIntentParseError.errorString()));
        if (stopIntentDocument.isObject()) {
            for (const QJsonValue &caseValue : stopIntentDocument.object().value(QStringLiteral("cases")).toArray()) {
                const QJsonObject stopCase = caseValue.toObject();
                const QString caseName = stopCase.value(QStringLiteral("name")).toString();
                const bool expectedClosePositions = stopCase.value(QStringLiteral("expected"))
                    .toObject().value(QStringLiteral("close_positions")).toBool(false);
                const bool closePositions = NativeOrderSafety::closePositionsFromPythonConfig(
                    stopCase.value(QStringLiteral("input")).toObject());
                check(closePositions == expectedClosePositions,
                      QStringLiteral("C++ %1 stop-intent mapping should match Python: %2")
                          .arg(referenceLabel, caseName));

                NativeOrderSafety::RuntimeStopGuardInput stopIntentGuard;
                stopIntentGuard.runtimeActive = true;
                stopIntentGuard.activeEngineCount = 1;
                stopIntentGuard.closePositions = closePositions;
                const QJsonObject stopIntentResult = NativeOrderSafety::buildRuntimeStopGuardResult(
                    stopIntentGuard);
                check(stopIntentResult.value(QStringLiteral("close_positions_requested")).toBool(false)
                          == expectedClosePositions,
                      QStringLiteral("C++ %1 stop guard should preserve Python stop intent: %2")
                          .arg(referenceLabel, caseName));
            }
        }
    };
    checkStopIntentReference(
        PythonParityContract::kPythonStopIntentReferenceJson,
        QStringLiteral("validated"));
    checkStopIntentReference(
        PythonParityContract::kPythonStopIntentLooseReferenceJson,
        QStringLiteral("loose"));

    NativeOrderSafety::RuntimeStopGuardInput stopWithClose;
    stopWithClose.runtimeActive = true;
    stopWithClose.activeEngineCount = 3;
    stopWithClose.closePositions = true;
    stopWithClose.source = QStringLiteral("web-ui");
    const QJsonObject stopWithCloseResult = NativeOrderSafety::buildRuntimeStopGuardResult(stopWithClose);
    check(stopWithCloseResult.value(QStringLiteral("accepted")).toBool(false),
          QStringLiteral("accepted stop with close positions should be accepted"));
    check(stopWithCloseResult.value(QStringLiteral("lifecycle_phase")).toString() == QStringLiteral("stopping"),
          QStringLiteral("accepted stop should enter stopping phase"));
    check(stopWithCloseResult.value(QStringLiteral("runtime_active")).toBool(false),
          QStringLiteral("accepted stop should preserve current runtime_active in result"));
    check(stopWithCloseResult.value(QStringLiteral("active_engine_count")).toInt(0) == 3,
          QStringLiteral("accepted stop should preserve active engine count in result"));
    check(stopWithCloseResult.value(QStringLiteral("close_positions_requested")).toBool(false),
          QStringLiteral("accepted stop should preserve close-all request"));
    check(stopWithCloseResult.value(QStringLiteral("status_message")).toString()
              == QStringLiteral("Stop requested with close-all positions."),
          QStringLiteral("stop with close-all should use Python source status message"));

    NativeOrderSafety::RuntimeStopGuardInput stopWithoutClose = stopWithClose;
    stopWithoutClose.closePositions = false;
    stopWithoutClose.dispatchMessage = QStringLiteral("Forwarded to desktop GUI.");
    const QJsonObject stopWithoutCloseResult = NativeOrderSafety::buildRuntimeStopGuardResult(stopWithoutClose);
    check(stopWithoutCloseResult.value(QStringLiteral("close_positions_requested")).toBool(true) == false,
          QStringLiteral("stop without close should clear close-all request"));
    check(stopWithoutCloseResult.value(QStringLiteral("status_message")).toString()
              == QStringLiteral("Stop requested. Forwarded to desktop GUI."),
          QStringLiteral("accepted stop should append dispatch message"));

    NativeOrderSafety::RuntimeStopGuardInput rejectedStop = stopWithClose;
    rejectedStop.dispatchAccepted = false;
    rejectedStop.dispatchMessage = QStringLiteral("Desktop dispatch unavailable apiSecret=super-secret-value");
    const QJsonObject rejectedStopResult = NativeOrderSafety::buildRuntimeStopGuardResult(rejectedStop);
    check(!rejectedStopResult.value(QStringLiteral("accepted")).toBool(true),
          QStringLiteral("rejected stop dispatch should be rejected"));
    check(rejectedStopResult.value(QStringLiteral("lifecycle_phase")).toString() == QStringLiteral("running"),
          QStringLiteral("rejected active stop should roll lifecycle back to running"));
    check(!rejectedStopResult.value(QStringLiteral("close_positions_requested")).toBool(true),
          QStringLiteral("rejected stop should clear close-all request"));
    check(rejectedStopResult.value(QStringLiteral("status_message")).toString().contains(QStringLiteral("<redacted>")),
          QStringLiteral("rejected stop message should be redacted"));
    check(!rejectedStopResult.value(QStringLiteral("status_message")).toString().contains(QStringLiteral("super-secret-value")),
          QStringLiteral("rejected stop message should not leak secrets"));

    NativeOrderSafety::RuntimeStopGuardInput alreadyStopping = stopWithClose;
    alreadyStopping.stopAlreadyInProgress = true;
    const QJsonObject alreadyStoppingResult = NativeOrderSafety::buildRuntimeStopGuardResult(alreadyStopping);
    check(!alreadyStoppingResult.value(QStringLiteral("accepted")).toBool(true),
          QStringLiteral("already-stopping stop should be rejected as duplicate"));
    check(alreadyStoppingResult.value(QStringLiteral("lifecycle_phase")).toString() == QStringLiteral("stopping"),
          QStringLiteral("already-stopping stop should stay in stopping phase"));
    check(alreadyStoppingResult.value(QStringLiteral("status_message")).toString()
              == QStringLiteral("Stop request already in progress."),
          QStringLiteral("already-stopping stop should use idempotency status"));

    const QJsonObject idleAfterClose = NativeOrderSafety::buildRuntimeIdleAfterStopResult(
        true,
        QStringLiteral("desktop-stop"));
    check(idleAfterClose.value(QStringLiteral("lifecycle_phase")).toString() == QStringLiteral("idle"),
          QStringLiteral("idle stop result should report idle lifecycle"));
    check(!idleAfterClose.value(QStringLiteral("close_positions_requested")).toBool(true),
          QStringLiteral("idle stop result should clear close-all request"));
    check(idleAfterClose.value(QStringLiteral("status_message")).toString()
              == QStringLiteral("Runtime idle after stop request."),
          QStringLiteral("idle after close-all stop should use Python source idle message"));

    const QJsonObject idleWithoutClose = NativeOrderSafety::buildRuntimeIdleAfterStopResult(
        false,
        QStringLiteral("desktop-stop"));
    check(idleWithoutClose.value(QStringLiteral("status_message")).toString() == QStringLiteral("Runtime idle."),
          QStringLiteral("idle without close-all stop should use Python source idle message"));

    return failures == 0 ? 0 : 1;
}
