#include "TradingBotWindowSupport.h"

#include <QComboBox>
#include <QRegularExpression>
#include <QSet>
#include <QSignalBlocker>
#include <QTableWidgetItem>
#include <QVector>
#include <QtGlobal>

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

const QVector<ConnectorOption> kConnectorOptions = {
    {QStringLiteral("Binance SDK Derivatives Trading USDⓈ Futures (Official Recommended)"), kConnectorUsdsFutures},
    {QStringLiteral("Binance SDK Derivatives Trading COIN-M Futures"), kConnectorCoinFutures},
    {QStringLiteral("Binance SDK Spot (Official Recommended)"), kConnectorSpot},
    {QStringLiteral("Binance Connector Python"), kConnectorBinanceConnector},
    {QStringLiteral("CCXT (Unified)"), kConnectorCcxt},
    {QStringLiteral("python-binance (Community)"), kConnectorPyBinance},
};

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
    Q_UNUSED(futures);
    const QString normalized = normalizeExchangeKey(exchangeKey);
    if (normalized == QStringLiteral("Bybit")) {
        return {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"};
    }
    if (normalized == QStringLiteral("OKX")) {
        return {"BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "LTCUSDT"};
    }
    if (normalized == QStringLiteral("Gate")) {
        return {"BTCUSDT", "ETHUSDT", "XRPUSDT", "TRXUSDT", "ETCUSDT"};
    }
    if (normalized == QStringLiteral("Bitget")) {
        return {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOTUSDT"};
    }
    if (normalized == QStringLiteral("MEXC")) {
        return {"BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "NEARUSDT"};
    }
    if (normalized == QStringLiteral("KuCoin")) {
        return {"BTCUSDT", "ETHUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT"};
    }
    return {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"};
}

QString recommendedConnectorKey(bool futures) {
    return futures ? kConnectorUsdsFutures : kConnectorSpot;
}

QString connectorLabelForKey(const QString &connectorKey) {
    for (const auto &option : kConnectorOptions) {
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
    for (const auto &option : kConnectorOptions) {
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
        setWarning(
            QStringLiteral("Connector '%1' is not implemented in C++ yet. Using '%2'.")
                .arg(cfg.label.isEmpty() ? connectorLabelForKey(kConnectorCoinFutures) : cfg.label,
                     connectorLabelForKey(kConnectorUsdsFutures)));
        effectiveKey = kConnectorUsdsFutures;
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
    cfg.baseUrl.clear();
    return cfg;
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
