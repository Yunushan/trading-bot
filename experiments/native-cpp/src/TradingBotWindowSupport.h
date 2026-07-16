#pragma once

#include <QString>
#include <QStringList>
#include <QVector>
#include <QJsonDocument>
#include <QMap>
#include <QJsonObject>

class QComboBox;
class QTableWidgetItem;

namespace TradingBotWindowSupport {

struct ConnectorRuntimeConfig {
    QString key;
    QString label;
    QString baseUrl;
    QString warning;
    QString error;

    bool ok() const {
        return error.trimmed().isEmpty();
    }
};

struct LlmProviderRuntimeConfig {
    QString key;
    QString label;
    QString mode;
    QString protocol;
    QString defaultBaseUrl;
    QString defaultModel;
    QString apiKeyEnv;
    QStringList modelSuggestions;
    QStringList reasoningEfforts;
    QString defaultReasoningEffort;
};

struct ServiceApiJsonResult {
    bool ok = false;
    int statusCode = 0;
    QJsonDocument document;
    QString error;
};

bool isTestnetModeLabel(const QString &modeText);
bool isPaperTradingModeLabel(const QString &modeText);
QString selectedDashboardExchange(const QComboBox *combo);
bool exchangeUsesBinanceApi(const QString &exchangeKey);
QStringList placeholderSymbolsForExchange(const QString &exchangeKey, bool futures);
QString pythonSourceParityContractHash();
QStringList pythonSourceParityDomainKeys();
QStringList pythonSourceParityDomainTitles();
QString pythonSourceParityDomainTitle(const QString &domainKey);
QString pythonSourceParityDomainPythonSurface(const QString &domainKey);
QString pythonSourceParityDomainCppStatus(const QString &domainKey);
QString pythonSourceParityDomainRustStatus(const QString &domainKey);
QString pythonSourceParityDomainRequiredBeforeFullParity(const QString &domainKey);
bool pythonSourceParityDomainCppFullParity(const QString &domainKey);
bool pythonSourceParityDomainRustFullParity(const QString &domainKey);
QStringList pythonSourceServiceRouteNames();
QString pythonSourceServiceRoutePath(const QString &routeName);
QStringList pythonSourceServiceRouteMethods(const QString &routeName);
QStringList pythonSourceServiceRouteQueryFields(const QString &routeName);
QStringList pythonSourceServiceRouteRequestFields(const QString &routeName);
QStringList pythonSourceServiceRouteResponseFields(const QString &routeName);
QString serviceApiBaseUrl();
QString serviceApiUrlForRoute(const QString &routeName);
ServiceApiJsonResult serviceApiRequestJson(
    const QString &method,
    const QString &routeName,
    const QJsonObject &body = {},
    int timeoutMs = 30000);
QStringList pythonSourceBacktestRunRequestFields();
QStringList pythonSourceIndicatorKeys();
QStringList pythonSourceIndicatorDisplayNames();
QStringList pythonSourceDefaultEnabledIndicatorKeys();
QMap<QString, QJsonObject> pythonSourceBacktestIndicatorConfigs();
QStringList pythonSourceLlmProviderKeys();
QStringList pythonSourceLlmProviderLabels();
QStringList pythonSourceLlmProviderDefaultModels();
QStringList pythonSourceLlmProviderApiKeyEnvs();
QVector<LlmProviderRuntimeConfig> pythonSourceLlmProviderConfigs();
QStringList pythonSourceConnectorKeys();
QStringList pythonSourceConnectorLabels();
QStringList pythonSourceBacktestIntervals();
QStringList pythonSourceTradingViewIntervalKeys();
QStringList pythonSourceTradingViewIntervalCodes();
QStringList pythonSourceDefaultChartSymbols();
QStringList pythonSourceDefaultExecutionSymbols();
QStringList pythonSourceDefaultExecutionIntervals();
QStringList pythonSourceDefaultBacktestSymbols();
QStringList pythonSourceDefaultBacktestIntervals();
QStringList pythonSourceChartMarketOptions();
QStringList pythonSourceAccountModeOptions();
QStringList pythonSourceDashboardLoopChoiceKeys();
QStringList pythonSourceDashboardLoopChoiceLabels();
QStringList pythonSourceLeadTraderOptionKeys();
QStringList pythonSourceLeadTraderOptionLabels();
QStringList pythonSourceLlmUseForOptionKeys();
QStringList pythonSourceLlmUseForOptionLabels();
QStringList pythonSourceDashboardStrategyTemplateKeys();
QStringList pythonSourceDashboardStrategyTemplateLabels();
QStringList pythonSourceBacktestTemplateKeys();
QStringList pythonSourceBacktestTemplateLabels();
QStringList pythonSourceSideOptionKeys();
QStringList pythonSourceSideOptionLabels();
QStringList pythonSourceConfigModeOptionKeys();
QStringList pythonSourceConfigModeOptionLabels();
QStringList pythonSourceThemeOptionKeys();
QStringList pythonSourceThemeOptionLabels();
QStringList pythonSourceDesignOptionKeys();
QStringList pythonSourceDesignOptionLabels();
QStringList pythonSourceIndicatorSourceOptionKeys();
QStringList pythonSourceIndicatorSourceOptionLabels();
QStringList pythonSourceExchangeOptionKeys();
QStringList pythonSourceExchangeOptionLabels();
QStringList pythonSourceAccountTypeOptionKeys();
QStringList pythonSourceAccountTypeOptionLabels();
QStringList pythonSourceMarginModeOptionKeys();
QStringList pythonSourceMarginModeOptionLabels();
QStringList pythonSourcePositionModeOptionKeys();
QStringList pythonSourcePositionModeOptionLabels();
QStringList pythonSourceAssetsModeOptionKeys();
QStringList pythonSourceAssetsModeOptionLabels();
QStringList pythonSourceOrderTypeOptionKeys();
QStringList pythonSourceOrderTypeOptionLabels();
QStringList pythonSourceTimeInForceOptionKeys();
QStringList pythonSourceTimeInForceOptionLabels();
QStringList pythonSourceSignalLogicOptionKeys();
QStringList pythonSourceSignalLogicOptionLabels();
QStringList pythonSourceMddLogicOptionKeys();
QStringList pythonSourceMddLogicOptionLabels();
QStringList pythonSourceStopLossModeKeys();
QStringList pythonSourceStopLossModeLabels();
QStringList pythonSourceStopLossScopeKeys();
QStringList pythonSourceStopLossScopeLabels();
QStringList pythonSourceScanScopeOptionKeys();
QStringList pythonSourceScanScopeOptionLabels();
QStringList pythonSourceOptimizerModeOptionKeys();
QStringList pythonSourceOptimizerModeOptionLabels();
QStringList pythonSourceOptimizerMetricOptionKeys();
QStringList pythonSourceOptimizerMetricOptionLabels();
QStringList pythonSourceBacktestExecutionBackendOptionKeys();
QStringList pythonSourceBacktestExecutionBackendOptionLabels();
QStringList pythonSourceChartViewOptionKeys();
QStringList pythonSourceChartViewOptionLabels();
QStringList pythonSourcePositionsViewOptionKeys();
QStringList pythonSourcePositionsViewOptionLabels();
QStringList pythonSourceExchangeOptionDisabledLabels();
void populateComboFromPythonSourceOptions(
    QComboBox *combo,
    const QStringList &keys,
    const QStringList &labels,
    const QStringList &disabledLabels = {},
    const QString &currentKey = {},
    const QString &currentLabel = {});
bool cppPythonSourceParityReady();
bool rustPythonSourceParityReady();
QString recommendedConnectorKey(bool futures);
QString connectorLabelForKey(const QString &connectorKey);
void rebuildConnectorComboForAccount(QComboBox *combo, bool futures, bool forceDefault = false);
ConnectorRuntimeConfig resolveConnectorConfig(const QString &connectorText, bool futures);
bool nativeRuntimeOwnsBinanceFuturesConnector(const QString &connectorText);
double firstNumberInText(const QString &text, bool *okOut = nullptr);
double tableCellRawNumeric(const QTableWidgetItem *item, double fallback = 0.0);

} // namespace TradingBotWindowSupport
