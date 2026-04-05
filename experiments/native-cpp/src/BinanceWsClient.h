#pragma once

#ifndef HAS_QT_WEBSOCKETS
#define HAS_QT_WEBSOCKETS 0
#endif

#include <QObject>
#include <QString>

#if HAS_QT_WEBSOCKETS
class QWebSocket;
#endif

class BinanceWsClient final : public QObject {
    Q_OBJECT

public:
    explicit BinanceWsClient(QObject *parent = nullptr);
    ~BinanceWsClient() override;

    void connectBookTicker(const QString &symbol, bool futures, bool testnet);
    void connectKline(const QString &symbol, const QString &interval, bool futures, bool testnet);
    void disconnectFromStream();

signals:
    void connected();
    void disconnected();
    void errorOccurred(const QString &message);
    void bookTicker(const QString &symbol, double bidPrice, double askPrice);
    void kline(
        const QString &symbol,
        const QString &interval,
        qint64 openTimeMs,
        double open,
        double high,
        double low,
        double close,
        double volume,
        bool isClosed);

private:
#if HAS_QT_WEBSOCKETS
    QWebSocket *socket_;
#endif
};
