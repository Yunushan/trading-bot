#include "BinanceRestClient.h"

#include <QDateTime>
#include <QEventLoop>
#include <QJsonArray>
#include <QJsonObject>
#include <QMessageAuthenticationCode>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>
#include <algorithm>

namespace {
bool parseJsonNumber(const QJsonValue &value, double *out) {
    if (!out) {
        return false;
    }
    bool ok = false;
    double parsed = value.toVariant().toDouble(&ok);
    if (!ok) {
        return false;
    }
    *out = parsed;
    return true;
}
} // namespace

QString BinanceRestClient::hmacSha256Hex(const QString &secret, const QString &message) {
    const QByteArray sig = QMessageAuthenticationCode::hash(
        message.toUtf8(), secret.toUtf8(), QCryptographicHash::Sha256);
    return QString::fromLatin1(sig.toHex());
}

QJsonDocument BinanceRestClient::httpGetJson(
    const QString &url,
    const QList<QPair<QByteArray, QByteArray>> &headers,
    int timeoutMs,
    QString *error) {
    QNetworkAccessManager manager;
    QNetworkRequest request{QUrl(url)};
    request.setHeader(QNetworkRequest::UserAgentHeader, QStringLiteral("trading-bot-cpp/1.0"));
    for (const auto &header : headers) {
        request.setRawHeader(header.first, header.second);
    }

    QNetworkReply *reply = manager.get(request);
    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, &QEventLoop::quit);
    timer.start(std::max(1000, timeoutMs));
    loop.exec();

    if (!reply->isFinished()) {
        reply->abort();
        reply->deleteLater();
        if (error) {
            *error = QStringLiteral("Request timeout");
        }
        return {};
    }

    const QByteArray payload = reply->readAll();
    if (reply->error() != QNetworkReply::NoError) {
        if (error) {
            QString message = reply->errorString();
            if (!payload.isEmpty()) {
                message += QStringLiteral(" | %1").arg(QString::fromUtf8(payload));
            }
            *error = message;
        }
        reply->deleteLater();
        return {};
    }
    reply->deleteLater();

    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(payload, &parseError);
    if (parseError.error != QJsonParseError::NoError || document.isNull()) {
        if (error) {
            *error = QStringLiteral("Invalid JSON response");
        }
        return {};
    }
    return document;
}

BinanceRestClient::BalanceResult BinanceRestClient::fetchUsdtBalance(
    const QString &apiKey,
    const QString &apiSecret,
    bool futures,
    bool testnet,
    int timeoutMs) {
    BalanceResult result;
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        result.error = QStringLiteral("Missing API credentials");
        return result;
    }

    const QString base = futures
        ? (testnet ? QStringLiteral("https://testnet.binancefuture.com")
                   : QStringLiteral("https://fapi.binance.com"))
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString endpoint = futures ? QStringLiteral("/fapi/v2/account") : QStringLiteral("/api/v3/account");
    const QString query = QStringLiteral("timestamp=%1").arg(QDateTime::currentMSecsSinceEpoch());
    const QString signature = hmacSha256Hex(apiSecret, query);
    const QString url = QStringLiteral("%1%2?%3&signature=%4").arg(base, endpoint, query, signature);

    QString requestError;
    const QJsonDocument document = httpGetJson(
        url,
        {{QByteArrayLiteral("X-MBX-APIKEY"), apiKey.toUtf8()}},
        timeoutMs,
        &requestError);
    if (document.isNull() || !document.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance response") : requestError;
        return result;
    }

    const QJsonObject obj = document.object();
    if (obj.contains(QStringLiteral("msg"))) {
        result.error = obj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
        return result;
    }

    if (futures) {
        const QJsonArray assets = obj.value(QStringLiteral("assets")).toArray();
        for (const QJsonValue &entry : assets) {
            const QJsonObject asset = entry.toObject();
            if (asset.value(QStringLiteral("asset")).toString() != QStringLiteral("USDT")) {
                continue;
            }
            for (const char *key : {"walletBalance", "marginBalance", "availableBalance"}) {
                double value = 0.0;
                if (parseJsonNumber(asset.value(QString::fromLatin1(key)), &value)) {
                    result.ok = true;
                    result.usdtBalance = value;
                    return result;
                }
            }
        }
    } else {
        const QJsonArray balances = obj.value(QStringLiteral("balances")).toArray();
        for (const QJsonValue &entry : balances) {
            const QJsonObject balance = entry.toObject();
            if (balance.value(QStringLiteral("asset")).toString() != QStringLiteral("USDT")) {
                continue;
            }
            double value = 0.0;
            if (parseJsonNumber(balance.value(QStringLiteral("free")), &value)) {
                result.ok = true;
                result.usdtBalance = value;
                return result;
            }
        }
    }

    result.error = QStringLiteral("USDT balance not found");
    return result;
}

BinanceRestClient::SymbolsResult BinanceRestClient::fetchUsdtSymbols(
    bool futures,
    bool testnet,
    int timeoutMs) {
    SymbolsResult result;
    const QString base = futures
        ? (testnet ? QStringLiteral("https://testnet.binancefuture.com")
                   : QStringLiteral("https://fapi.binance.com"))
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString endpoint = futures ? QStringLiteral("/fapi/v1/exchangeInfo") : QStringLiteral("/api/v3/exchangeInfo");
    const QString url = QStringLiteral("%1%2").arg(base, endpoint);

    QString requestError;
    const QJsonDocument document = httpGetJson(url, {}, timeoutMs, &requestError);
    if (document.isNull() || !document.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance response") : requestError;
        return result;
    }

    const QJsonObject obj = document.object();
    if (obj.contains(QStringLiteral("msg"))) {
        result.error = obj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
        return result;
    }

    const QJsonArray symbols = obj.value(QStringLiteral("symbols")).toArray();
    QStringList collected;
    for (const QJsonValue &entry : symbols) {
        const QJsonObject sym = entry.toObject();
        if (sym.value(QStringLiteral("quoteAsset")).toString() != QStringLiteral("USDT")) {
            continue;
        }
        const QString status = sym.value(QStringLiteral("status")).toString().toUpper();
        if (status != QStringLiteral("TRADING") && status != QStringLiteral("PENDING_TRADING")) {
            continue;
        }
        if (futures) {
            const QString contractType = sym.value(QStringLiteral("contractType")).toString().toUpper();
            if (contractType != QStringLiteral("PERPETUAL")
                && contractType != QStringLiteral("CURRENT_QUARTER")
                && contractType != QStringLiteral("NEXT_QUARTER")) {
                continue;
            }
        }
        const QString symbol = sym.value(QStringLiteral("symbol")).toString();
        if (!symbol.isEmpty()) {
            collected.append(symbol);
        }
    }

    collected.removeDuplicates();
    std::sort(collected.begin(), collected.end(), [](const QString &a, const QString &b) {
        return a < b;
    });
    result.ok = true;
    result.symbols = collected;
    return result;
}

BinanceRestClient::KlinesResult BinanceRestClient::fetchKlines(
    const QString &symbol,
    const QString &interval,
    bool futures,
    bool testnet,
    int limit,
    int timeoutMs) {
    KlinesResult result;

    const QString cleanSymbol = symbol.trimmed().toUpper();
    const QString cleanInterval = interval.trimmed();
    if (cleanSymbol.isEmpty()) {
        result.error = QStringLiteral("Symbol is required");
        return result;
    }
    if (cleanInterval.isEmpty()) {
        result.error = QStringLiteral("Interval is required");
        return result;
    }

    const int safeLimit = std::clamp(limit, 10, 1000);
    const QString base = futures
        ? (testnet ? QStringLiteral("https://testnet.binancefuture.com")
                   : QStringLiteral("https://fapi.binance.com"))
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString endpoint = futures ? QStringLiteral("/fapi/v1/klines") : QStringLiteral("/api/v3/klines");
    const QString url = QStringLiteral("%1%2?symbol=%3&interval=%4&limit=%5")
        .arg(base, endpoint, cleanSymbol, cleanInterval, QString::number(safeLimit));

    QString requestError;
    const QJsonDocument document = httpGetJson(url, {}, timeoutMs, &requestError);
    if (document.isNull() || !document.isArray()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance kline response") : requestError;
        return result;
    }

    const QJsonArray candles = document.array();
    QVector<KlineCandle> parsed;
    parsed.reserve(candles.size());
    for (const QJsonValue &entry : candles) {
        if (!entry.isArray()) {
            continue;
        }
        const QJsonArray row = entry.toArray();
        if (row.size() < 6) {
            continue;
        }

        bool timeOk = false;
        const qint64 openTimeMs = row.at(0).toVariant().toLongLong(&timeOk);
        double open = 0.0;
        double high = 0.0;
        double low = 0.0;
        double close = 0.0;
        double volume = 0.0;
        if (!timeOk
            || !parseJsonNumber(row.at(1), &open)
            || !parseJsonNumber(row.at(2), &high)
            || !parseJsonNumber(row.at(3), &low)
            || !parseJsonNumber(row.at(4), &close)
            || !parseJsonNumber(row.at(5), &volume)) {
            continue;
        }

        KlineCandle candle;
        candle.openTimeMs = openTimeMs;
        candle.open = open;
        candle.high = high;
        candle.low = low;
        candle.close = close;
        candle.volume = volume;
        parsed.push_back(candle);
    }

    if (parsed.isEmpty()) {
        result.error = QStringLiteral("No candle data returned for %1 (%2)").arg(cleanSymbol, cleanInterval);
        return result;
    }

    result.ok = true;
    result.candles = parsed;
    return result;
}
