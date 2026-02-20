#pragma once

#include <QJsonDocument>
#include <QList>
#include <QPair>
#include <QString>
#include <QStringList>
#include <QVector>

class BinanceRestClient final {
public:
    struct KlineCandle {
        qint64 openTimeMs = 0;
        double open = 0.0;
        double high = 0.0;
        double low = 0.0;
        double close = 0.0;
        double volume = 0.0;
    };

    struct BalanceResult {
        bool ok = false;
        double usdtBalance = 0.0;
        QString error;
    };

    struct SymbolsResult {
        bool ok = false;
        QStringList symbols;
        QString error;
    };

    struct KlinesResult {
        bool ok = false;
        QVector<KlineCandle> candles;
        QString error;
    };

    static BalanceResult fetchUsdtBalance(
        const QString &apiKey,
        const QString &apiSecret,
        bool futures,
        bool testnet,
        int timeoutMs = 10000);

    static SymbolsResult fetchUsdtSymbols(
        bool futures,
        bool testnet,
        int timeoutMs = 10000);

    static KlinesResult fetchKlines(
        const QString &symbol,
        const QString &interval,
        bool futures,
        bool testnet,
        int limit = 300,
        int timeoutMs = 10000);

private:
    static QString hmacSha256Hex(const QString &secret, const QString &message);
    static QJsonDocument httpGetJson(
        const QString &url,
        const QList<QPair<QByteArray, QByteArray>> &headers,
        int timeoutMs,
        QString *error);
};
