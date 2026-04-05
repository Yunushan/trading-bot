#pragma once

#include <QString>
#include <QStringList>

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

bool isTestnetModeLabel(const QString &modeText);
bool isPaperTradingModeLabel(const QString &modeText);
QString selectedDashboardExchange(const QComboBox *combo);
bool exchangeUsesBinanceApi(const QString &exchangeKey);
QStringList placeholderSymbolsForExchange(const QString &exchangeKey, bool futures);
QString recommendedConnectorKey(bool futures);
QString connectorLabelForKey(const QString &connectorKey);
void rebuildConnectorComboForAccount(QComboBox *combo, bool futures, bool forceDefault = false);
ConnectorRuntimeConfig resolveConnectorConfig(const QString &connectorText, bool futures);
double firstNumberInText(const QString &text, bool *okOut = nullptr);
double tableCellRawNumeric(const QTableWidgetItem *item, double fallback = 0.0);

} // namespace TradingBotWindowSupport
