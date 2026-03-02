#include "BinanceRestClient.h"

#include <QDateTime>
#include <QEventLoop>
#include <QHash>
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

bool parseFirstNumber(
    const QJsonObject &obj,
    std::initializer_list<const char *> keys,
    double *out) {
    for (const char *key : keys) {
        if (parseJsonNumber(obj.value(QString::fromLatin1(key)), out)) {
            return true;
        }
    }
    return false;
}

QJsonArray extractBalanceEntries(const QJsonDocument &document) {
    if (document.isArray()) {
        return document.array();
    }
    if (!document.isObject()) {
        return {};
    }
    const QJsonObject obj = document.object();
    for (const char *key : {"balances", "accountBalance", "data"}) {
        const QJsonValue value = obj.value(QString::fromLatin1(key));
        if (value.isArray()) {
            return value.toArray();
        }
    }
    return {};
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
    int timeoutMs,
    const QString &baseUrlOverride) {
    BalanceResult result;
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        result.error = QStringLiteral("Missing API credentials");
        return result;
    }

    const QString defaultBase = futures
        ? (testnet ? QStringLiteral("https://testnet.binancefuture.com")
                   : QStringLiteral("https://fapi.binance.com"))
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = overrideBase.isEmpty() ? defaultBase : overrideBase;
    auto signedGet = [&](const QString &endpoint, QString *requestError) -> QJsonDocument {
        const QString query = QStringLiteral("timestamp=%1").arg(QDateTime::currentMSecsSinceEpoch());
        const QString signature = hmacSha256Hex(apiSecret, query);
        const QString url = QStringLiteral("%1%2?%3&signature=%4").arg(base, endpoint, query, signature);
        return httpGetJson(
            url,
            {{QByteArrayLiteral("X-MBX-APIKEY"), apiKey.toUtf8()}},
            timeoutMs,
            requestError);
    };

    const QStringList preferredAssets{QStringLiteral("USDT"), QStringLiteral("BUSD"), QStringLiteral("USD")};
    auto parsePreferredAssetRow = [&](const QJsonArray &rows, double *available, double *wallet, QString *assetCode) -> bool {
        QHash<QString, QJsonObject> byAsset;
        for (const QJsonValue &entry : rows) {
            const QJsonObject row = entry.toObject();
            const QString code = row.value(QStringLiteral("asset")).toString().trimmed().toUpper();
            if (code.isEmpty() || !preferredAssets.contains(code) || byAsset.contains(code)) {
                continue;
            }
            byAsset.insert(code, row);
        }

        for (const QString &code : preferredAssets) {
            if (!byAsset.contains(code)) {
                continue;
            }
            const QJsonObject row = byAsset.value(code);
            double availableValue = 0.0;
            double walletValue = 0.0;
            const bool hasAvailable = parseFirstNumber(
                row,
                {"availableBalance", "maxWithdrawAmount", "crossWalletBalance"},
                &availableValue);
            const bool hasWallet = parseFirstNumber(
                row,
                {"walletBalance", "marginBalance", "balance", "crossWalletBalance"},
                &walletValue);
            if (!hasAvailable && !hasWallet) {
                continue;
            }
            if (available) {
                *available = hasAvailable ? availableValue : 0.0;
            }
            if (wallet) {
                *wallet = hasWallet ? walletValue : 0.0;
            }
            if (assetCode) {
                *assetCode = code;
            }
            return true;
        }
        return false;
    };

    auto applySnapshot = [&](double available, double wallet, const QString &assetCode) {
        result.ok = true;
        result.asset = assetCode.isEmpty() ? QStringLiteral("USDT") : assetCode;
        result.availableUsdtBalance = std::max(0.0, available);
        result.totalUsdtBalance = std::max(result.availableUsdtBalance, std::max(0.0, wallet));
        result.usdtBalance = result.totalUsdtBalance;
    };

    if (futures) {
        QString balanceError;
        const QJsonDocument balanceDoc = signedGet(QStringLiteral("/fapi/v2/balance"), &balanceError);
        if (!balanceDoc.isNull()) {
            if (balanceDoc.isObject()) {
                const QJsonObject obj = balanceDoc.object();
                if (obj.contains(QStringLiteral("msg")) && balanceError.isEmpty()) {
                    balanceError = obj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
                }
            }
            double available = 0.0;
            double wallet = 0.0;
            QString assetCode;
            const QJsonArray entries = extractBalanceEntries(balanceDoc);
            if (parsePreferredAssetRow(entries, &available, &wallet, &assetCode)) {
                applySnapshot(available, wallet, assetCode);
                return result;
            }
        }

        QString accountError;
        const QJsonDocument accountDoc = signedGet(QStringLiteral("/fapi/v2/account"), &accountError);
        if (accountDoc.isNull() || !accountDoc.isObject()) {
            QString merged = accountError;
            if (merged.isEmpty()) {
                merged = balanceError;
            }
            result.error = merged.isEmpty() ? QStringLiteral("Unexpected Binance response") : merged;
            return result;
        }

        const QJsonObject accountObj = accountDoc.object();
        if (accountObj.contains(QStringLiteral("msg"))) {
            result.error = accountObj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
            return result;
        }

        double available = 0.0;
        double wallet = 0.0;
        bool hasAvailable = parseFirstNumber(accountObj, {"availableBalance", "maxWithdrawAmount"}, &available);
        bool hasWallet = parseFirstNumber(
            accountObj,
            {"totalWalletBalance", "totalMarginBalance", "totalCrossWalletBalance", "totalCrossBalance"},
            &wallet);
        QString assetCode = QStringLiteral("USDT");
        if (!hasAvailable || !hasWallet) {
            const QJsonArray assets = accountObj.value(QStringLiteral("assets")).toArray();
            double rowAvailable = 0.0;
            double rowWallet = 0.0;
            QString rowAsset;
            if (parsePreferredAssetRow(assets, &rowAvailable, &rowWallet, &rowAsset)) {
                if (!hasAvailable) {
                    available = rowAvailable;
                    hasAvailable = true;
                }
                if (!hasWallet) {
                    wallet = rowWallet;
                    hasWallet = true;
                }
                if (!rowAsset.isEmpty()) {
                    assetCode = rowAsset;
                }
            }
        }

        if (hasAvailable || hasWallet) {
            applySnapshot(hasAvailable ? available : 0.0, hasWallet ? wallet : 0.0, assetCode);
            return result;
        }

        result.error = balanceError.isEmpty() ? QStringLiteral("USDT balance not found") : balanceError;
        return result;
    }

    QString requestError;
    const QJsonDocument document = signedGet(QStringLiteral("/api/v3/account"), &requestError);
    if (document.isNull() || !document.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance response") : requestError;
        return result;
    }

    const QJsonObject obj = document.object();
    if (obj.contains(QStringLiteral("msg"))) {
        result.error = obj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
        return result;
    }

    const QJsonArray balances = obj.value(QStringLiteral("balances")).toArray();
    for (const QJsonValue &entry : balances) {
        const QJsonObject balance = entry.toObject();
        if (balance.value(QStringLiteral("asset")).toString() != QStringLiteral("USDT")) {
            continue;
        }
        double value = 0.0;
        if (parseJsonNumber(balance.value(QStringLiteral("free")), &value)) {
            result.ok = true;
            result.asset = QStringLiteral("USDT");
            result.availableUsdtBalance = value;
            result.totalUsdtBalance = value;
            result.usdtBalance = value;
            return result;
        }
    }

    result.error = QStringLiteral("USDT balance not found");
    return result;
}

BinanceRestClient::SymbolsResult BinanceRestClient::fetchUsdtSymbols(
    bool futures,
    bool testnet,
    int timeoutMs,
    bool sortByVolume,
    int topN,
    const QString &baseUrlOverride) {
    SymbolsResult result;
    const QString defaultBase = futures
        ? (testnet ? QStringLiteral("https://testnet.binancefuture.com")
                   : QStringLiteral("https://fapi.binance.com"))
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = overrideBase.isEmpty() ? defaultBase : overrideBase;
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
        if (status != QStringLiteral("TRADING")) {
            continue;
        }
        if (futures) {
            const QString contractType = sym.value(QStringLiteral("contractType")).toString().toUpper();
            if (contractType != QStringLiteral("PERPETUAL")) {
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

    if (sortByVolume && !collected.isEmpty()) {
        const QString tickerEndpoint = futures ? QStringLiteral("/fapi/v1/ticker/24hr")
                                               : QStringLiteral("/api/v3/ticker/24hr");
        const QString tickerUrl = QStringLiteral("%1%2").arg(base, tickerEndpoint);
        QString tickerError;
        const QJsonDocument tickerDocument = httpGetJson(tickerUrl, {}, timeoutMs, &tickerError);
        if (!tickerDocument.isNull() && tickerDocument.isArray()) {
            const QJsonArray tickers = tickerDocument.array();
            QHash<QString, double> quoteVolumeBySymbol;
            quoteVolumeBySymbol.reserve(tickers.size());
            for (const QJsonValue &entry : tickers) {
                const QJsonObject ticker = entry.toObject();
                const QString symbol = ticker.value(QStringLiteral("symbol")).toString().toUpper();
                if (symbol.isEmpty()) {
                    continue;
                }
                double quoteVolume = 0.0;
                if (!parseJsonNumber(ticker.value(QStringLiteral("quoteVolume")), &quoteVolume)) {
                    continue;
                }
                quoteVolumeBySymbol.insert(symbol, quoteVolume);
            }
            std::sort(collected.begin(), collected.end(), [&quoteVolumeBySymbol](const QString &a, const QString &b) {
                const double aVol = quoteVolumeBySymbol.value(a.toUpper(), 0.0);
                const double bVol = quoteVolumeBySymbol.value(b.toUpper(), 0.0);
                if (aVol == bVol) {
                    return a < b;
                }
                return aVol > bVol;
            });
        }
    }

    if (topN > 0 && collected.size() > topN) {
        collected = collected.mid(0, topN);
    }

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
    int timeoutMs,
    const QString &baseUrlOverride) {
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
    const QString defaultBase = futures
        ? (testnet ? QStringLiteral("https://testnet.binancefuture.com")
                   : QStringLiteral("https://fapi.binance.com"))
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = overrideBase.isEmpty() ? defaultBase : overrideBase;
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
