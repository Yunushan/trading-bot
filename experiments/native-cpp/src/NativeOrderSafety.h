#pragma once

#include <QDateTime>
#include <QJsonObject>
#include <QJsonValue>
#include <QPair>
#include <QString>
#include <QStringList>
#include <QVector>

namespace NativeOrderSafety {

inline constexpr const char *LiveTradingAcknowledgement = "I_UNDERSTAND_LIVE_TRADING_RISK";

struct OrderSubmitIntent {
    QString market;
    QString symbol;
    QString side;
    QString orderType;
    double quantity = 0.0;
    bool hasQuantity = false;
    double price = 0.0;
    bool hasPrice = false;
    QString positionSide;
    bool closePosition = false;
    bool reduceOnly = false;
};

struct OrderSymbolFilters {
    double stepSize = 0.0;
    double tickSize = 0.0;
    double minQty = 0.0;
    double minNotional = 0.0;
};

struct LiveTradingSafetyConfig {
    bool liveTradingEnabled = false;
    QString liveTradingAcknowledgement;
    int liveTradingMaxLeverage = 20;
    double liveTradingMaxPositionPct = 10.0;
    int liveTradingMaxSessionOrders = 100;
    bool liveAllowAutoBumpToMinOrder = false;
    double maxAutoBumpPercent = 5.0;
    double autoBumpPercentMultiplier = 10.0;
};

struct LiveOrderGuardInput {
    QString mode;
    QString market = QStringLiteral("futures");
    QVector<QPair<QString, QString>> params;
    QString apiKey;
    QString apiSecret;
    QString accountType = QStringLiteral("FUTURES");
    int leverage = 1;
    QString marginMode;
    double positionPct = 2.0;
    LiveTradingSafetyConfig config;
    bool hasFilters = false;
    OrderSymbolFilters filters;
    bool hasLastPrice = false;
    double lastPrice = 0.0;
    bool orderAuditEnabled = true;
    bool orderAuditWritable = true;
    QString connectorState;
    QString connectorHealth;
    int liveSubmitAttemptCount = 0;
};

struct LiveOrderGuardResult {
    bool allowed = false;
    QStringList errors;
    int nextSubmitAttemptCount = 0;
};

struct MinimumOrderAutoBumpGuardInput {
    QString mode;
    double requestedQuantity = 0.0;
    double normalizedQuantity = 0.0;
    double price = 0.0;
    double availableUsdt = 0.0;
    int leverage = 1;
    double requestedPositionPct = 0.0;
    bool reduceOnly = false;
    LiveTradingSafetyConfig config;
};

struct MinimumOrderAutoBumpGuardResult {
    bool allowed = false;
    bool autoBumpRequired = false;
    QStringList errors;
};

struct OrderAuditLogConfig {
    bool enabled = true;
    QString path;
    quint64 maxBytes = 10 * 1024 * 1024;
    int backupCount = 1;
};

struct ConnectorOrderCircuitConfig {
    bool enabled = true;
    int blockThreshold = 2;
    double blockWindowSeconds = 60.0;
};

struct ConnectorOrderBlockEvent {
    double timestamp = 0.0;
    QString symbol;
    QString interval;
    QString side;
    QString accountType = QStringLiteral("FUTURES");
    QString connectorHealth;
    QString connectorState;
    QString connectorMessage;
    QString contextKey;
    QString signature;
};

struct OperationalFreshnessInput {
    QString timestampField = QStringLiteral("generated_at");
    QDateTime timestamp;
    QString timestampText;
    double maxAgeSeconds = 1.0;
    bool shouldWarn = true;
    QString state;
    QString source;
};

struct OperationalPreflightInput {
    QString mode;
    QString health = QStringLiteral("ok");
    bool startGateEnabled = true;
    bool orderGateEnabled = true;
    QDateTime generatedAt;
    OperationalFreshnessInput exchangeConnector;
    OperationalFreshnessInput execution;
    OperationalFreshnessInput account;
    OperationalFreshnessInput portfolio;
    QJsonObject connectorOrderCircuitBreaker;
};

struct RuntimeStopGuardInput {
    bool runtimeActive = false;
    int activeEngineCount = 0;
    bool stopAlreadyInProgress = false;
    bool closePositions = false;
    bool dispatchAccepted = true;
    QString dispatchMessage;
    QString source = QStringLiteral("service");
};

class ConnectorOrderCircuitBreaker {
public:
    explicit ConnectorOrderCircuitBreaker(ConnectorOrderCircuitConfig config = {});

    QJsonObject recordConnectorOrderBlock(const ConnectorOrderBlockEvent &event, const QDateTime &now);
    QJsonObject snapshot(const QDateTime &now) const;
    QJsonObject resetConnectorOrderCircuitBreaker(
        const QString &source,
        bool force,
        const QString &resetBlockReason,
        const QDateTime &now);
    bool isOpen() const;
    int eventCount() const;

private:
    ConnectorOrderCircuitConfig config_;
    QVector<ConnectorOrderBlockEvent> events_;
    QJsonObject snapshot_;
    bool open_ = false;
};

bool isSensitiveKey(const QString &key);
QString redactText(QString text);
QJsonValue redactValue(const QJsonValue &value, int depth = 0);
QJsonObject redactOrderParams(const QVector<QPair<QString, QString>> &params);

OrderSubmitIntent orderSubmitIntentFromParams(
    const QString &market,
    const QVector<QPair<QString, QString>> &params);
QStringList validateOrderSubmitIntent(const OrderSubmitIntent &intent);
QStringList validateOrderFilterConstraints(
    const OrderSubmitIntent &intent,
    const OrderSymbolFilters &filters,
    bool hasLastPrice,
    double lastPrice);
bool isLiveTradingMode(const QString &mode);
QStringList validateLiveTradingSafety(const LiveOrderGuardInput &input);
LiveOrderGuardResult guardLiveOrderSubmit(const LiveOrderGuardInput &input);
MinimumOrderAutoBumpGuardResult guardFuturesMinimumOrderAutoBump(
    const MinimumOrderAutoBumpGuardInput &input);

QJsonObject buildOrderAuditEvent(
    const QString &event,
    const QString &market,
    const QVector<QPair<QString, QString>> &params,
    const QDateTime &timestamp,
    const QString &source = {});
QString orderAuditEventJsonLine(const QJsonObject &event);
QJsonObject buildOrderAuditStatus(
    bool enabled,
    const QString &path,
    quint64 maxBytes,
    int backupCount,
    const QString &lastWriteError = {},
    const QString &lastWriteErrorAt = {},
    const QString &lastWriteOkAt = {});
QString defaultOrderAuditPath();
QString orderAuditBackupPath(const QString &path, int index = 1);
OrderAuditLogConfig orderAuditLogConfigFromEnvironment();
bool rotateOrderAuditLogIfNeeded(
    const QString &path,
    qint64 incomingBytes,
    quint64 maxBytes,
    int backupCount,
    QString *error = nullptr);
QJsonObject appendOrderAuditEvent(
    const QJsonObject &event,
    const OrderAuditLogConfig &config = {});
QJsonObject currentOrderAuditStatus(const OrderAuditLogConfig &config = {});

QJsonObject buildOperationalPreflightSnapshot(const OperationalPreflightInput &input);
bool operationalPreflightStartAllowed(const QJsonObject &preflight);
bool operationalPreflightOrdersAllowed(const QJsonObject &preflight);
QJsonObject buildRuntimeStopGuardResult(const RuntimeStopGuardInput &input);
QJsonObject buildRuntimeIdleAfterStopResult(
    bool closePositionsRequested,
    const QString &source = QStringLiteral("service"),
    const QString &statusMessage = {});

QJsonObject buildConnectorOrderCircuitBreakerSnapshot(
    const QJsonObject &raw,
    const QString &source,
    const QDateTime &now);
QJsonObject buildConnectorOrderCircuitIncident(
    const QString &action,
    const QJsonObject &snapshot,
    const QString &source,
    const QString &message,
    const QDateTime &timestamp);
QString connectorOrderCircuitIncidentJsonLine(const QJsonObject &incident);
QJsonObject parseConnectorOrderCircuitIncidentLines(const QStringList &lines, int limit = 20);

} // namespace NativeOrderSafety
