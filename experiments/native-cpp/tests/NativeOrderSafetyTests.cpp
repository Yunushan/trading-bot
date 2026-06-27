#include "../src/NativeChartHeatmap.h"
#include "../src/NativeConfigPersistence.h"
#include "../src/NativeDesktopShell.h"
#include "../src/NativeDiagnostics.h"
#include "../src/NativeExchangeConnectors.h"
#include "../src/NativeLlmAdvisory.h"
#include "../src/NativeOrderSafety.h"
#include "../src/NativePortfolio.h"
#include "../src/NativeStartupPackaging.h"
#include "../src/NativeStrategyRuntime.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QTextStream>

#include <iostream>
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

    QTemporaryDir dir;
    check(dir.isValid(), QStringLiteral("temporary directory should be valid"));
    if (!dir.isValid()) {
        return 1;
    }

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
    check(cppStartupContract.value(QStringLiteral("delegates_trading_execution_to_python")).toBool(false),
          QStringLiteral("native startup contract should keep Python as trading execution owner"));
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
    check(!cppShellOwnership.value(QStringLiteral("owns_trading_execution")).toBool(true),
          QStringLiteral("native desktop shell should keep Python as trading execution owner"));

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
         }) {
        check(signalDescription.contains(fragment), QStringLiteral("native strategy signal description should include %1").arg(fragment));
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

    const QJsonObject normalizedRuntimeControls = NativeStrategyRuntime::normalizeStrategyControls(
        QStringLiteral("runtime"),
        QJsonObject{
            {QStringLiteral("side"), QStringLiteral("buy only")},
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
    check(!normalizedRuntimeControls.value(QStringLiteral("add_only")).toBool(true),
          QStringLiteral("native strategy controls should coerce false string add_only"));
    check(normalizedRuntimeControls.value(QStringLiteral("account_mode")).toString() == QStringLiteral("Portfolio Margin"),
          QStringLiteral("native strategy controls should normalize account mode"));
    check(normalizedRuntimeControls.value(QStringLiteral("connector_backend")).toString() == QStringLiteral("ccxt"),
          QStringLiteral("native strategy controls should normalize connector backend"));
    check(normalizedRuntimeControls.value(QStringLiteral("stop_loss")).toObject().value(QStringLiteral("scope")).toString() == QStringLiteral("per_trade"),
          QStringLiteral("native strategy controls should normalize invalid stop-loss scope"));

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
    check(lifecycleSnapshot.value(QStringLiteral("execution_owner")).toString() == QStringLiteral("python-service"),
          QStringLiteral("native strategy lifecycle should keep Python as execution owner"));
    check(!lifecycleSnapshot.value(QStringLiteral("native_trading_execution_enabled")).toBool(true),
          QStringLiteral("native strategy lifecycle should not enable standalone native trading"));

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
    check(llmViolations.contains(QStringLiteral("direct_order_action")),
          QStringLiteral("native LLM policy should block direct order actions"));
    check(llmViolations.contains(QStringLiteral("order_execution_claim")),
          QStringLiteral("native LLM policy should block execution claims"));
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
    check(secretMetadata.value(QStringLiteral("secret_storage")).toString() == QStringLiteral("plain-json-on-disk"),
          QStringLiteral("service config secret storage should mirror Python plain-json marker"));
    check(secretMetadata.value(QStringLiteral("secret_storage_warning")).toString().contains(QStringLiteral("plain JSON")),
          QStringLiteral("service config secret warning should mirror Python plain JSON warning"));

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
    check(inlinePayload.value(QStringLiteral("inline_secrets_persisted")).toBool(false),
          QStringLiteral("service config payload should allow explicit inline secret persistence"));
    check(inlinePayload.value(QStringLiteral("config")).toObject().value(QStringLiteral("api_key")).toString()
              == QStringLiteral("exchange-key"),
          QStringLiteral("service config payload should keep api_key when inline persistence is explicit"));

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
            {QStringLiteral("indicator_source"), QStringLiteral("tradingview")},
            {QStringLiteral("theme"), QStringLiteral("green")},
            {QStringLiteral("design"), QStringLiteral("workstation")},
            {QStringLiteral("selected_exchange"), QStringLiteral("kucoin")},
            {QStringLiteral("llm_provider"), QStringLiteral("chatgpt")},
            {QStringLiteral("llm_use_for"), QStringLiteral("Risk review")},
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
                {QStringLiteral("mdd_logic"), QStringLiteral("Per Trade MDD")},
                {QStringLiteral("scan_scope"), QStringLiteral("top_n")},
                {QStringLiteral("scan_top_n"), 200},
                {QStringLiteral("scan_mdd_limit"), 20},
                {QStringLiteral("scan_auto_apply"), QStringLiteral("false")},
                {QStringLiteral("optimizer_mode"), QStringLiteral("pairs")},
                {QStringLiteral("optimizer_metric"), QStringLiteral("roi-percent-mdd")},
                {QStringLiteral("optimizer_combo_size"), 2},
                {QStringLiteral("optimizer_min_trades"), 1},
                {QStringLiteral("template"), QJsonObject{}},
                {QStringLiteral("indicators"), QJsonObject{}},
                {QStringLiteral("stop_loss"), QJsonObject{
                    {QStringLiteral("mode"), QStringLiteral("Percentage Based Stop Loss")},
                    {QStringLiteral("scope"), QStringLiteral("Entire Account Stop Loss")},
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
    check(normalizedConfig.config.value(QStringLiteral("mode")).toString() == QStringLiteral("Live"),
          QStringLiteral("native service config validation should normalize mode choices from Python source"));
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
    check(normalizedConfig.config.value(QStringLiteral("connector_backend")).toString() == QStringLiteral("ccxt"),
          QStringLiteral("native service config validation should normalize connector backend labels from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("indicator_source")).toString() == QStringLiteral("TradingView"),
          QStringLiteral("native service config validation should normalize indicator source choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("theme")).toString() == QStringLiteral("Green"),
          QStringLiteral("native service config validation should normalize theme choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("design")).toString() == QStringLiteral("Workstation"),
          QStringLiteral("native service config validation should normalize design choices from Python source"));
    check(normalizedConfig.config.value(QStringLiteral("selected_exchange")).toString() == QStringLiteral("KuCoin"),
          QStringLiteral("native service config validation should normalize exchange choices from Python source"));
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
    check(normalizedBacktest.value(QStringLiteral("symbol_source")).toString() == QStringLiteral("Futures"),
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
    check(invalidMessage.contains(QStringLiteral("backtest.symbol_source: must be one of:")),
          QStringLiteral("native config validation should report invalid backtest symbol source choices"));

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
