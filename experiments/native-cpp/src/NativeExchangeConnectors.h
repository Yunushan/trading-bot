#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace NativeExchangeConnectors {

struct ExchangeSupportInput {
    QString selectedExchange;
    QString connectorBackend;
    QString selectedForexBroker;
};

QString defaultConnectorBackend();
QString supportKey(const QString &value);
QStringList supportedExchanges();
QStringList supportedConnectorBackends();
QString normalizeConnectorBackend(const QString &value);

QJsonObject buildExchangeSupportPayload(
    const ExchangeSupportInput &config,
    const ExchangeSupportInput &snapshot = {});

double estimateRequestWeight(const QString &path);
QString environmentTag(const QString &modeValue);
QString accountTag(const QString &accountValue);
QJsonObject limiterSettingsFor(const QString &envTag, const QString &accountTag);

double extractBanUntil(const QString &message, double nowEpoch, bool *ok = nullptr);
QJsonObject buildHttpBackoff(
    int statusCode,
    int code,
    const QString &message,
    double retryAfter,
    double nowEpoch);

QJsonObject buildConnectorHealthSnapshot(const QJsonObject &input);

} // namespace NativeExchangeConnectors
