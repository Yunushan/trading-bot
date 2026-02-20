#include "BinanceWsClient.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QUrl>

#if HAS_QT_WEBSOCKETS
#include <QWebSocket>
#endif

namespace {
QString normalizedStreamSymbol(const QString &symbol) {
    QString stream = symbol.trimmed().toLower();
    stream.remove(' ');
    return stream;
}
} // namespace

BinanceWsClient::BinanceWsClient(QObject *parent)
    : QObject(parent)
#if HAS_QT_WEBSOCKETS
    , socket_(new QWebSocket())
#endif
{
#if HAS_QT_WEBSOCKETS
    socket_->setParent(this);
    connect(socket_, &QWebSocket::connected, this, &BinanceWsClient::connected);
    connect(socket_, &QWebSocket::disconnected, this, &BinanceWsClient::disconnected);
    connect(socket_, &QWebSocket::textMessageReceived, this, [this](const QString &message) {
        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
            return;
        }
        const QJsonObject obj = doc.object();
        const QString symbol = obj.value(QStringLiteral("s")).toString();
        bool bidOk = false;
        bool askOk = false;
        const double bid = obj.value(QStringLiteral("b")).toVariant().toDouble(&bidOk);
        const double ask = obj.value(QStringLiteral("a")).toVariant().toDouble(&askOk);
        if (!symbol.isEmpty() && bidOk && askOk) {
            emit bookTicker(symbol, bid, ask);
        }
    });
    connect(
        socket_,
        qOverload<QAbstractSocket::SocketError>(&QWebSocket::errorOccurred),
        this,
        [this](QAbstractSocket::SocketError) { emit errorOccurred(socket_->errorString()); });
#endif
}

BinanceWsClient::~BinanceWsClient() {
    disconnectFromStream();
}

void BinanceWsClient::connectBookTicker(const QString &symbol, bool futures, bool testnet) {
#if HAS_QT_WEBSOCKETS
    if (!socket_) {
        emit errorOccurred(QStringLiteral("WebSocket client is not initialized."));
        return;
    }
    const QString streamSymbol = normalizedStreamSymbol(symbol);
    if (streamSymbol.isEmpty()) {
        emit errorOccurred(QStringLiteral("Symbol is empty."));
        return;
    }
    const QString stream = streamSymbol + QStringLiteral("@bookTicker");
    const QString base = futures
        ? (testnet ? QStringLiteral("wss://stream.binancefuture.com/ws")
                   : QStringLiteral("wss://fstream.binance.com/ws"))
        : (testnet ? QStringLiteral("wss://testnet.binance.vision/ws")
                   : QStringLiteral("wss://stream.binance.com:9443/ws"));
    const QUrl url(base + QStringLiteral("/") + stream);
    if (socket_->state() != QAbstractSocket::UnconnectedState) {
        socket_->close();
    }
    socket_->open(url);
#else
    Q_UNUSED(symbol)
    Q_UNUSED(futures)
    Q_UNUSED(testnet)
    emit errorOccurred(QStringLiteral("Qt WebSockets module is not available in this build."));
#endif
}

void BinanceWsClient::disconnectFromStream() {
#if HAS_QT_WEBSOCKETS
    if (socket_ && socket_->state() != QAbstractSocket::UnconnectedState) {
        socket_->close();
    }
#endif
}
