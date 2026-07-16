#include "BinanceRestClient.h"

#include <QDateTime>
#include <QEventLoop>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QMap>
#include <QMessageAuthenticationCode>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QTimer>
#include <QThread>
#include <QUrl>
#include <QUrlQuery>
#include <algorithm>
#include <cmath>
#include <limits>

namespace {
qint64 intervalMilliseconds(QString interval) {
    interval = interval.trimmed().toLower();
    if (interval.isEmpty()) {
        return 0;
    }

    qint64 multiplier = 0;
    QString number = interval;
    if (interval.endsWith(QStringLiteral("months"))) {
        number.chop(6);
        multiplier = 30LL * 24 * 60 * 60 * 1000;
    } else if (interval.endsWith(QStringLiteral("month"))) {
        number.chop(5);
        multiplier = 30LL * 24 * 60 * 60 * 1000;
    } else if (interval.endsWith(QStringLiteral("mo"))) {
        number.chop(2);
        multiplier = 30LL * 24 * 60 * 60 * 1000;
    } else {
        const QChar unit = interval.back();
        number.chop(1);
        if (unit == QLatin1Char('s')) multiplier = 1000;
        else if (unit == QLatin1Char('m')) multiplier = 60LL * 1000;
        else if (unit == QLatin1Char('h')) multiplier = 60LL * 60 * 1000;
        else if (unit == QLatin1Char('d')) multiplier = 24LL * 60 * 60 * 1000;
        else if (unit == QLatin1Char('w')) multiplier = 7LL * 24 * 60 * 60 * 1000;
        else if (unit == QLatin1Char('y')) multiplier = 365LL * 24 * 60 * 60 * 1000;
        else return 0;
    }

    bool ok = false;
    const qint64 count = number.toLongLong(&ok);
    if (!ok || count <= 0 || multiplier <= 0
        || count > std::numeric_limits<qint64>::max() / multiplier) {
        return 0;
    }
    return count * multiplier;
}

bool isNativeBinanceInterval(const QString &interval) {
    static const QSet<QString> kNativeIntervals = {
        QStringLiteral("1m"), QStringLiteral("3m"), QStringLiteral("5m"),
        QStringLiteral("15m"), QStringLiteral("30m"), QStringLiteral("1h"),
        QStringLiteral("2h"), QStringLiteral("4h"), QStringLiteral("6h"),
        QStringLiteral("8h"), QStringLiteral("12h"), QStringLiteral("1d"),
        QStringLiteral("3d"), QStringLiteral("1w"), QStringLiteral("1M"),
    };
    return kNativeIntervals.contains(interval);
}

QString baseIntervalFor(qint64 intervalMs) {
    if (intervalMs < 60LL * 60 * 1000) return QStringLiteral("1m");
    if (intervalMs < 24LL * 60 * 60 * 1000) return QStringLiteral("1h");
    return QStringLiteral("1d");
}

QVector<BinanceRestClient::KlineCandle> aggregateKlines(
    const QVector<BinanceRestClient::KlineCandle> &source,
    qint64 targetIntervalMs,
    qint64 startTimeMs,
    qint64 endTimeMs) {
    QMap<qint64, BinanceRestClient::KlineCandle> buckets;
    for (const auto &candle : source) {
        const qint64 bucketTime = (candle.openTimeMs / targetIntervalMs) * targetIntervalMs;
        auto it = buckets.find(bucketTime);
        if (it == buckets.end()) {
            BinanceRestClient::KlineCandle aggregate = candle;
            aggregate.openTimeMs = bucketTime;
            buckets.insert(bucketTime, aggregate);
            continue;
        }
        it->high = std::max(it->high, candle.high);
        it->low = std::min(it->low, candle.low);
        it->close = candle.close;
        it->volume += candle.volume;
    }

    QVector<BinanceRestClient::KlineCandle> result;
    result.reserve(buckets.size());
    for (auto it = buckets.cbegin(); it != buckets.cend(); ++it) {
        if (it.key() >= startTimeMs && it.key() <= endTimeMs) {
            result.append(it.value());
        }
    }
    return result;
}

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

QJsonDocument httpRequestJson(
    const QString &method,
    const QString &url,
    const QList<QPair<QByteArray, QByteArray>> &headers,
    int timeoutMs,
    QString *error,
    const QByteArray &body = {}) {
    QNetworkAccessManager manager;
    QNetworkRequest request{QUrl(url)};
    request.setHeader(QNetworkRequest::UserAgentHeader, QStringLiteral("trading-bot-cpp/1.0"));
    if (!body.isEmpty()) {
        request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/x-www-form-urlencoded"));
    }
    for (const auto &header : headers) {
        request.setRawHeader(header.first, header.second);
    }

    const QString verb = method.trimmed().toUpper();
    QNetworkReply *reply = nullptr;
    if (verb == QStringLiteral("POST")) {
        reply = manager.post(request, body);
    } else if (verb == QStringLiteral("DELETE")) {
        reply = manager.sendCustomRequest(request, QByteArrayLiteral("DELETE"), body);
    } else if (verb == QStringLiteral("PUT")) {
        reply = manager.put(request, body);
    } else {
        reply = manager.get(request);
    }
    if (!reply) {
        if (error) {
            *error = QStringLiteral("Failed to create network request");
        }
        return {};
    }

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

QString formatDecimalForOrder(double value, int precisionHint = 8) {
    if (!qIsFinite(value) || value <= 0.0) {
        return QStringLiteral("0");
    }
    const int precision = std::max(0, std::min(16, precisionHint));
    QString text = QString::number(value, 'f', precision);
    while (text.contains('.') && (text.endsWith('0') || text.endsWith('.'))) {
        text.chop(1);
    }
    return text.isEmpty() ? QStringLiteral("0") : text;
}

double normalizeMarginRatioPercent(double value) {
    if (!qIsFinite(value) || value <= 0.0) {
        return 0.0;
    }
    return value <= 1.0 ? (value * 100.0) : value;
}

bool isCoinMarginedFuturesBase(const QString &baseUrlOverride) {
    const QUrl parsed(baseUrlOverride.trimmed());
    const QString host = parsed.host().trimmed().toLower();
    if (host == QStringLiteral("dapi.binance.com")) {
        return true;
    }
    const QStringList pathParts = parsed.path().split(QLatin1Char('/'), Qt::SkipEmptyParts);
    return pathParts.contains(QStringLiteral("dapi"), Qt::CaseInsensitive);
}

bool isDefaultCoinMarginedBase(const QString &baseUrlOverride) {
    const QUrl parsed(baseUrlOverride.trimmed());
    return parsed.host().compare(QStringLiteral("dapi.binance.com"), Qt::CaseInsensitive) == 0
        && parsed.path().trimmed().isEmpty();
}

QString futuresBaseUrl(bool testnet, const QString &baseUrlOverride) {
    const QString overrideBase = baseUrlOverride.trimmed();
    const bool coinMargined = isCoinMarginedFuturesBase(overrideBase);
    if (testnet && (overrideBase.isEmpty() || isDefaultCoinMarginedBase(overrideBase))) {
        return QStringLiteral("https://testnet.binancefuture.com");
    }
    if (!overrideBase.isEmpty()) {
        QUrl parsed(overrideBase);
        QStringList pathParts = parsed.path().split(QLatin1Char('/'), Qt::SkipEmptyParts);
        if (pathParts.contains(QStringLiteral("dapi"), Qt::CaseInsensitive)) {
            pathParts.erase(
                std::remove_if(pathParts.begin(), pathParts.end(), [](const QString &part) {
                    return part.compare(QStringLiteral("dapi"), Qt::CaseInsensitive) == 0;
                }),
                pathParts.end());
            parsed.setPath(pathParts.isEmpty() ? QString() : QStringLiteral("/") + pathParts.join(QLatin1Char('/')));
        }
        return parsed.toString(QUrl::RemoveQuery | QUrl::RemoveFragment).remove(QRegularExpression(QStringLiteral("/$")));
    }
    return coinMargined ? QStringLiteral("https://dapi.binance.com")
                        : QStringLiteral("https://fapi.binance.com");
}

QString futuresApiPath(const QString &baseUrlOverride, const QString &suffix) {
    const QString prefix = isCoinMarginedFuturesBase(baseUrlOverride)
        ? QStringLiteral("/dapi")
        : QStringLiteral("/fapi");
    return prefix + suffix;
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
    return httpRequestJson(QStringLiteral("GET"), url, headers, timeoutMs, error);
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
        ? futuresBaseUrl(testnet, baseUrlOverride)
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futures ? defaultBase : (overrideBase.isEmpty() ? defaultBase : overrideBase);
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

    auto applySnapshot = [&](double available, double totalBalance, const QString &assetCode) {
        double normalizedTotal = std::max(0.0, totalBalance);
        double normalizedAvailable = std::max(0.0, available);
        if (normalizedTotal <= 0.0 && normalizedAvailable > 0.0) {
            normalizedTotal = normalizedAvailable;
        }
        if (normalizedTotal > 0.0 && normalizedAvailable > normalizedTotal) {
            normalizedAvailable = normalizedTotal;
        }
        result.ok = true;
        result.asset = assetCode.isEmpty() ? QStringLiteral("USDT") : assetCode;
        result.availableUsdtBalance = normalizedAvailable;
        result.totalUsdtBalance = normalizedTotal;
        result.usdtBalance = result.totalUsdtBalance;
    };

    if (futures) {
        QString balanceError;
        const QJsonDocument balanceDoc = signedGet(futuresApiPath(overrideBase, QStringLiteral("/v1/balance")), &balanceError);
        bool hasBalanceSnapshot = false;
        double balanceSnapshotAvailable = 0.0;
        double balanceSnapshotWallet = 0.0;
        QString balanceSnapshotAsset;
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
                hasBalanceSnapshot = true;
                balanceSnapshotAvailable = available;
                balanceSnapshotWallet = wallet;
                balanceSnapshotAsset = assetCode;
                const bool suspiciousDemoAvailable = wallet > 0.0 && available > (wallet + 1e-6);
                if (!suspiciousDemoAvailable) {
                    applySnapshot(available, wallet, assetCode);
                    return result;
                }
            }
        }

        QString accountError;
        const QJsonDocument accountDoc = signedGet(
            futuresApiPath(overrideBase, isCoinMarginedFuturesBase(overrideBase)
                ? QStringLiteral("/v1/account") : QStringLiteral("/v2/account")),
            &accountError);
        if (accountDoc.isNull() || !accountDoc.isObject()) {
            if (hasBalanceSnapshot) {
                applySnapshot(balanceSnapshotAvailable, balanceSnapshotWallet, balanceSnapshotAsset);
                return result;
            }
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
        double totalBalance = 0.0;
        bool hasAvailable = parseFirstNumber(accountObj, {"availableBalance", "maxWithdrawAmount"}, &available);
        bool hasTotalBalance = parseFirstNumber(
            accountObj,
            {"totalMarginBalance", "totalWalletBalance", "totalCrossWalletBalance", "totalCrossBalance"},
            &totalBalance);
        QString assetCode = QStringLiteral("USDT");
        if (!hasAvailable || !hasTotalBalance) {
            const QJsonArray assets = accountObj.value(QStringLiteral("assets")).toArray();
            double rowAvailable = 0.0;
            double rowWallet = 0.0;
            QString rowAsset;
            if (parsePreferredAssetRow(assets, &rowAvailable, &rowWallet, &rowAsset)) {
                if (!hasAvailable) {
                    available = rowAvailable;
                    hasAvailable = true;
                }
                if (!hasTotalBalance) {
                    totalBalance = rowWallet;
                    hasTotalBalance = true;
                }
                if (!rowAsset.isEmpty()) {
                    assetCode = rowAsset;
                }
            }
        }

        if (hasAvailable || hasTotalBalance) {
            applySnapshot(hasAvailable ? available : 0.0, hasTotalBalance ? totalBalance : 0.0, assetCode);
            return result;
        }

        if (hasBalanceSnapshot) {
            applySnapshot(balanceSnapshotAvailable, balanceSnapshotWallet, balanceSnapshotAsset);
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
        ? futuresBaseUrl(testnet, baseUrlOverride)
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futures ? defaultBase : (overrideBase.isEmpty() ? defaultBase : overrideBase);
    const QString endpoint = futures ? futuresApiPath(overrideBase, QStringLiteral("/v1/exchangeInfo"))
                                     : QStringLiteral("/api/v3/exchangeInfo");
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
        const QString tickerEndpoint = futures ? futuresApiPath(overrideBase, QStringLiteral("/v1/ticker/24hr"))
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
    const QString &baseUrlOverride,
    qint64 startTimeMs,
    qint64 endTimeMs) {
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

    const int safeLimit = std::clamp(limit, 1, futures ? 1500 : 1000);
    const QString defaultBase = futures
        ? futuresBaseUrl(testnet, baseUrlOverride)
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futures ? defaultBase : (overrideBase.isEmpty() ? defaultBase : overrideBase);
    const QString endpoint = futures ? futuresApiPath(overrideBase, QStringLiteral("/v1/klines"))
                                     : QStringLiteral("/api/v3/klines");
    QUrl url(base + endpoint);
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("symbol"), cleanSymbol);
    query.addQueryItem(QStringLiteral("interval"), cleanInterval);
    query.addQueryItem(QStringLiteral("limit"), QString::number(safeLimit));
    if (startTimeMs > 0) query.addQueryItem(QStringLiteral("startTime"), QString::number(startTimeMs));
    if (endTimeMs > 0) query.addQueryItem(QStringLiteral("endTime"), QString::number(endTimeMs));
    url.setQuery(query);

    QString requestError;
    const QJsonDocument document = httpGetJson(url.toString(), {}, timeoutMs, &requestError);
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

BinanceRestClient::TickerPriceResult BinanceRestClient::fetchTickerPrice(
    const QString &symbol,
    bool futures,
    bool testnet,
    int timeoutMs,
    const QString &baseUrlOverride) {
    TickerPriceResult result;
    result.symbol = symbol.trimmed().toUpper();
    if (result.symbol.isEmpty()) {
        result.error = QStringLiteral("Symbol is required");
        return result;
    }

    const QString defaultBase = futures
        ? futuresBaseUrl(testnet, baseUrlOverride)
        : (testnet ? QStringLiteral("https://testnet.binance.vision")
                   : QStringLiteral("https://api.binance.com"));
    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futures ? defaultBase : (overrideBase.isEmpty() ? defaultBase : overrideBase);
    const QString endpoint = futures ? futuresApiPath(overrideBase, QStringLiteral("/v1/ticker/price"))
                                     : QStringLiteral("/api/v3/ticker/price");
    const QString url = QStringLiteral("%1%2?symbol=%3").arg(base, endpoint, result.symbol);

    QString requestError;
    const QJsonDocument document = httpGetJson(url, {}, timeoutMs, &requestError);
    if (document.isNull() || !document.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance ticker response") : requestError;
        return result;
    }

    const QJsonObject obj = document.object();
    if (obj.contains(QStringLiteral("msg"))) {
        result.error = obj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
        return result;
    }
    if (obj.contains(QStringLiteral("code")) && obj.contains(QStringLiteral("msg"))) {
        result.error = obj.value(QStringLiteral("msg")).toString(QStringLiteral("Binance API error"));
        return result;
    }

    if (!parseJsonNumber(obj.value(QStringLiteral("price")), &result.price)
        || !qIsFinite(result.price)
        || result.price <= 0.0) {
        result.error = QStringLiteral("Ticker price missing for %1").arg(result.symbol);
        result.price = 0.0;
        return result;
    }

    const QString responseSymbol = obj.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
    if (!responseSymbol.isEmpty()) {
        result.symbol = responseSymbol;
    }
    result.ok = true;
    return result;
}

BinanceRestClient::KlinesResult BinanceRestClient::fetchKlinesRange(
    const QString &symbol,
    const QString &interval,
    bool futures,
    bool testnet,
    qint64 startTimeMs,
    qint64 endTimeMs,
    int maxCandles,
    int timeoutMs,
    const QString &baseUrlOverride,
    const std::function<bool()> &shouldStop) {
    KlinesResult result;
    if (startTimeMs <= 0 || endTimeMs <= startTimeMs) {
        result.error = QStringLiteral("Historical kline range requires endTime > startTime > 0");
        return result;
    }

    const QString requestedInterval = interval.trimmed();
    const qint64 requestedIntervalMs = intervalMilliseconds(requestedInterval == QStringLiteral("1M")
        ? QStringLiteral("1mo")
        : requestedInterval);
    if (requestedIntervalMs < 60LL * 1000) {
        result.error = QStringLiteral("Historical interval '%1' must be at least one minute").arg(requestedInterval);
        return result;
    }

    const bool nativeInterval = isNativeBinanceInterval(requestedInterval);
    const QString fetchInterval = nativeInterval ? requestedInterval : baseIntervalFor(requestedIntervalMs);
    const qint64 fetchIntervalMs = intervalMilliseconds(fetchInterval);
    if (fetchIntervalMs <= 0 || requestedIntervalMs % fetchIntervalMs != 0) {
        result.error = QStringLiteral("Custom interval '%1' is not a multiple of %2")
                           .arg(requestedInterval, fetchInterval);
        return result;
    }

    const int safeMaxCandles = std::max(1, maxCandles);
    const qint64 fetchEndTimeMs = nativeInterval
        ? endTimeMs
        : std::min(
              std::numeric_limits<qint64>::max() - requestedIntervalMs,
              endTimeMs) + requestedIntervalMs;
    const int pageLimit = futures ? 1500 : 1000;
    QMap<qint64, KlineCandle> candlesByTime;
    qint64 current = startTimeMs;
    int pageGuard = 0;

    while (current < fetchEndTimeMs && pageGuard++ < 10000) {
        if (shouldStop && shouldStop()) {
            result.error = QStringLiteral("Historical kline fetch cancelled");
            return result;
        }

        KlinesResult page;
        for (int attempt = 0; attempt < 4; ++attempt) {
            page = fetchKlines(
                symbol,
                fetchInterval,
                futures,
                testnet,
                pageLimit,
                timeoutMs,
                baseUrlOverride,
                current,
                fetchEndTimeMs);
            if (page.ok || (shouldStop && shouldStop())) break;
            QThread::msleep(static_cast<unsigned long>(250 * (attempt + 1)));
        }
        if (!page.ok) {
            result.error = page.error.isEmpty()
                ? QStringLiteral("Historical kline page request failed")
                : page.error;
            return result;
        }

        qint64 lastOpenTime = current;
        for (const KlineCandle &candle : page.candles) {
            if (candle.openTimeMs >= startTimeMs && candle.openTimeMs <= fetchEndTimeMs) {
                candlesByTime.insert(candle.openTimeMs, candle);
            }
            lastOpenTime = std::max(lastOpenTime, candle.openTimeMs);
        }
        if (candlesByTime.size() > safeMaxCandles) {
            result.error = QStringLiteral("Historical range exceeded the native candle safety limit (%1)")
                               .arg(safeMaxCandles);
            return result;
        }
        if (page.candles.size() < pageLimit) break;
        const qint64 next = lastOpenTime + fetchIntervalMs;
        if (next <= current) break;
        current = next;
    }

    QVector<KlineCandle> fetched;
    fetched.reserve(candlesByTime.size());
    for (auto it = candlesByTime.cbegin(); it != candlesByTime.cend(); ++it) {
        if (it.key() >= startTimeMs && it.key() <= fetchEndTimeMs) {
            fetched.append(it.value());
        }
    }
    if (fetched.isEmpty()) {
        result.error = QStringLiteral("No candle data returned for %1 (%2)")
                           .arg(symbol.trimmed().toUpper(), requestedInterval);
        return result;
    }

    result.candles = nativeInterval
        ? fetched
        : aggregateKlines(fetched, requestedIntervalMs, startTimeMs, endTimeMs);
    if (result.candles.isEmpty()) {
        result.error = QStringLiteral("Custom interval aggregation returned no candles for %1 (%2)")
                           .arg(symbol.trimmed().toUpper(), requestedInterval);
        return result;
    }
    result.ok = true;
    return result;
}

BinanceRestClient::FuturesPositionsResult BinanceRestClient::fetchOpenFuturesPositions(
    const QString &apiKey,
    const QString &apiSecret,
    bool testnet,
    int timeoutMs,
    const QString &baseUrlOverride) {
    FuturesPositionsResult result;
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        result.error = QStringLiteral("Missing API credentials");
        return result;
    }

    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futuresBaseUrl(testnet, overrideBase);

    const QString query = QStringLiteral("timestamp=%1").arg(QDateTime::currentMSecsSinceEpoch());
    const QString signature = hmacSha256Hex(apiSecret, query);
    const QString url = QStringLiteral("%1%2?%3&signature=%4")
                            .arg(base, futuresApiPath(overrideBase,
                                isCoinMarginedFuturesBase(overrideBase)
                                    ? QStringLiteral("/v1/positionRisk") : QStringLiteral("/v2/positionRisk")),
                                query, signature);

    QString requestError;
    const QJsonDocument document = httpGetJson(
        url,
        {{QByteArrayLiteral("X-MBX-APIKEY"), apiKey.toUtf8()}},
        timeoutMs,
        &requestError);
    if (document.isNull() || !document.isArray()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance response") : requestError;
        return result;
    }

    QHash<QString, QJsonObject> accountPositionMap;
    {
        const QString accountQuery = QStringLiteral("timestamp=%1").arg(QDateTime::currentMSecsSinceEpoch());
        const QString accountSignature = hmacSha256Hex(apiSecret, accountQuery);
        const QString accountUrl = QStringLiteral("%1%2?%3&signature=%4")
                                       .arg(base, futuresApiPath(overrideBase,
                                           isCoinMarginedFuturesBase(overrideBase)
                                               ? QStringLiteral("/v1/account") : QStringLiteral("/v2/account")),
                                           accountQuery, accountSignature);
        QString accountError;
        const QJsonDocument accountDoc = httpGetJson(
            accountUrl,
            {{QByteArrayLiteral("X-MBX-APIKEY"), apiKey.toUtf8()}},
            timeoutMs,
            &accountError);
        if (!accountDoc.isNull() && accountDoc.isObject()) {
            const QJsonArray accountPositions = accountDoc.object().value(QStringLiteral("positions")).toArray();
            for (const QJsonValue &apValue : accountPositions) {
                const QJsonObject apObj = apValue.toObject();
                const QString apSymbol = apObj.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
                if (apSymbol.isEmpty()) {
                    continue;
                }
                QString apSide = apObj.value(QStringLiteral("positionSide")).toString().trimmed().toUpper();
                if (apSide.isEmpty()) {
                    apSide = QStringLiteral("BOTH");
                }
                accountPositionMap.insert(QStringLiteral("%1|%2").arg(apSymbol, apSide), apObj);
                if (apSide != QStringLiteral("BOTH")) {
                    const QString fallbackKey = QStringLiteral("%1|BOTH").arg(apSymbol);
                    if (!accountPositionMap.contains(fallbackKey)) {
                        accountPositionMap.insert(fallbackKey, apObj);
                    }
                }
            }
        }
    }

    const QJsonArray rows = document.array();
    QVector<FuturesPosition> parsed;
    parsed.reserve(rows.size());
    for (const QJsonValue &value : rows) {
        const QJsonObject obj = value.toObject();
        const QString symbol = obj.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        if (symbol.isEmpty()) {
            continue;
        }
        double positionAmt = 0.0;
        if (!parseJsonNumber(obj.value(QStringLiteral("positionAmt")), &positionAmt)) {
            continue;
        }
        // Ignore zero-sized ghost entries (like orphaned symbols with no active size).
        if (std::fabs(positionAmt) <= 1e-10) {
            continue;
        }

        FuturesPosition pos;
        pos.symbol = symbol;
        pos.positionSide = obj.value(QStringLiteral("positionSide")).toString().trimmed().toUpper();
        pos.positionAmt = positionAmt;
        parseJsonNumber(obj.value(QStringLiteral("notional")), &pos.notional);
        parseJsonNumber(obj.value(QStringLiteral("initialMargin")), &pos.initialMargin);
        parseJsonNumber(obj.value(QStringLiteral("positionInitialMargin")), &pos.positionInitialMargin);
        parseJsonNumber(obj.value(QStringLiteral("openOrderInitialMargin")), &pos.openOrderMargin);
        parseJsonNumber(obj.value(QStringLiteral("isolatedWallet")), &pos.isolatedWallet);
        parseJsonNumber(obj.value(QStringLiteral("isolatedMargin")), &pos.isolatedMargin);
        if (!parseJsonNumber(obj.value(QStringLiteral("maintMargin")), &pos.maintMargin)) {
            parseJsonNumber(obj.value(QStringLiteral("maintenanceMargin")), &pos.maintMargin);
        }
        parseJsonNumber(obj.value(QStringLiteral("marginBalance")), &pos.marginBalance);
        parseJsonNumber(obj.value(QStringLiteral("walletBalance")), &pos.walletBalance);
        parseJsonNumber(obj.value(QStringLiteral("marginRatio")), &pos.marginRatio);
        pos.marginRatio = normalizeMarginRatioPercent(pos.marginRatio);
        parseJsonNumber(obj.value(QStringLiteral("leverage")), &pos.leverage);
        parseJsonNumber(obj.value(QStringLiteral("unRealizedProfit")), &pos.unrealizedProfit);
        parseJsonNumber(obj.value(QStringLiteral("entryPrice")), &pos.entryPrice);
        parseJsonNumber(obj.value(QStringLiteral("markPrice")), &pos.markPrice);
        parseJsonNumber(obj.value(QStringLiteral("liquidationPrice")), &pos.liquidationPrice);

        const QString accountLookupKey = QStringLiteral("%1|%2")
                                             .arg(symbol, pos.positionSide.isEmpty() ? QStringLiteral("BOTH")
                                                                                     : pos.positionSide);
        const QJsonObject accountPos = accountPositionMap.value(
            accountLookupKey,
            accountPositionMap.value(QStringLiteral("%1|BOTH").arg(symbol)));
        if (!accountPos.isEmpty()) {
            auto mergePositiveNumber = [&](const QString &field, double *target) {
                if (!target) {
                    return;
                }
                double value = 0.0;
                if (!parseJsonNumber(accountPos.value(field), &value)) {
                    return;
                }
                if (qIsFinite(value) && value > 0.0) {
                    *target = value;
                }
            };
            auto mergeNumber = [&](const QString &field, double *target) {
                if (!target) {
                    return;
                }
                double value = 0.0;
                if (!parseJsonNumber(accountPos.value(field), &value)) {
                    return;
                }
                if (qIsFinite(value)) {
                    *target = value;
                }
            };

            mergePositiveNumber(QStringLiteral("initialMargin"), &pos.initialMargin);
            mergePositiveNumber(QStringLiteral("positionInitialMargin"), &pos.positionInitialMargin);
            mergePositiveNumber(QStringLiteral("openOrderInitialMargin"), &pos.openOrderMargin);
            mergePositiveNumber(QStringLiteral("isolatedWallet"), &pos.isolatedWallet);
            mergePositiveNumber(QStringLiteral("isolatedMargin"), &pos.isolatedMargin);
            if (!qIsFinite(pos.maintMargin) || pos.maintMargin <= 0.0) {
                mergePositiveNumber(QStringLiteral("maintMargin"), &pos.maintMargin);
                if (!qIsFinite(pos.maintMargin) || pos.maintMargin <= 0.0) {
                    mergePositiveNumber(QStringLiteral("maintenanceMargin"), &pos.maintMargin);
                }
            }
            if (!qIsFinite(pos.marginBalance) || pos.marginBalance <= 0.0) {
                mergePositiveNumber(QStringLiteral("marginBalance"), &pos.marginBalance);
            }
            if (!qIsFinite(pos.walletBalance) || pos.walletBalance <= 0.0) {
                mergePositiveNumber(QStringLiteral("walletBalance"), &pos.walletBalance);
            }
            if (!qIsFinite(pos.notional) || pos.notional <= 0.0) {
                mergePositiveNumber(QStringLiteral("notional"), &pos.notional);
            }
            if (!qIsFinite(pos.entryPrice) || pos.entryPrice <= 0.0) {
                mergePositiveNumber(QStringLiteral("entryPrice"), &pos.entryPrice);
            }
            if (!qIsFinite(pos.markPrice) || pos.markPrice <= 0.0) {
                mergePositiveNumber(QStringLiteral("markPrice"), &pos.markPrice);
            }
            if (!qIsFinite(pos.liquidationPrice) || pos.liquidationPrice <= 0.0) {
                mergePositiveNumber(QStringLiteral("liquidationPrice"), &pos.liquidationPrice);
            }
            if (!qIsFinite(pos.leverage) || pos.leverage <= 0.0) {
                mergePositiveNumber(QStringLiteral("leverage"), &pos.leverage);
            }
            if (!qIsFinite(pos.unrealizedProfit)) {
                mergeNumber(QStringLiteral("unRealizedProfit"), &pos.unrealizedProfit);
            }
            if (!qIsFinite(pos.marginRatio) || pos.marginRatio <= 0.0) {
                mergePositiveNumber(QStringLiteral("marginRatio"), &pos.marginRatio);
                pos.marginRatio = normalizeMarginRatioPercent(pos.marginRatio);
            }
        }

        double maintMarginRate = 0.0;
        if (!parseJsonNumber(obj.value(QStringLiteral("maintMarginRate")), &maintMarginRate)) {
            if (!parseJsonNumber(obj.value(QStringLiteral("maintenanceMarginRate")), &maintMarginRate)) {
                parseJsonNumber(obj.value(QStringLiteral("maintMarginRatio")), &maintMarginRate);
            }
        }
        if (!qIsFinite(maintMarginRate) || maintMarginRate <= 0.0) {
            maintMarginRate = 0.0;
        }

        if (pos.notional <= 0.0 && qIsFinite(pos.markPrice) && qIsFinite(pos.positionAmt)) {
            pos.notional = std::fabs(pos.positionAmt) * std::max(0.0, pos.markPrice);
        }
        const double absNotional = std::fabs(pos.notional);
        if (pos.maintMargin <= 0.0 && maintMarginRate > 0.0 && absNotional > 0.0) {
            pos.maintMargin = absNotional * maintMarginRate;
        }

        double derivedMargin = 0.0;
        if (pos.positionInitialMargin > 0.0 || pos.openOrderMargin > 0.0) {
            derivedMargin = std::max(0.0, pos.positionInitialMargin) + std::max(0.0, pos.openOrderMargin);
        }
        if (derivedMargin <= 0.0 && pos.initialMargin > 0.0) {
            derivedMargin = pos.initialMargin;
        }
        if (derivedMargin <= 0.0 && pos.isolatedMargin > 0.0) {
            derivedMargin = pos.isolatedMargin;
        }
        if (derivedMargin <= 0.0 && pos.isolatedWallet > 0.0) {
            const double marginFromIso = pos.isolatedWallet - pos.unrealizedProfit;
            derivedMargin = marginFromIso > 0.0 ? marginFromIso : pos.isolatedWallet;
        }
        if (derivedMargin <= 0.0 && pos.entryPrice > 0.0 && std::fabs(pos.positionAmt) > 0.0 && pos.leverage > 0.0) {
            derivedMargin = (std::fabs(pos.positionAmt) * pos.entryPrice) / std::max(1.0, pos.leverage);
        }
        if (derivedMargin <= 0.0 && absNotional > 0.0 && pos.leverage > 0.0) {
            derivedMargin = absNotional / std::max(1.0, pos.leverage);
        }
        derivedMargin = std::max(0.0, derivedMargin);

        if (pos.initialMargin <= 0.0 && derivedMargin > 0.0) {
            pos.initialMargin = derivedMargin;
        }
        if (pos.marginBalance <= 0.0) {
            if (pos.isolatedWallet > 0.0) {
                pos.marginBalance = std::max(0.0, pos.isolatedWallet);
            } else if (derivedMargin > 0.0) {
                pos.marginBalance = std::max(0.0, derivedMargin + pos.unrealizedProfit);
            }
        }
        if (pos.walletBalance <= 0.0) {
            if (pos.marginBalance > 0.0) {
                pos.walletBalance = pos.marginBalance;
            } else if (derivedMargin > 0.0) {
                pos.walletBalance = std::max(0.0, derivedMargin + pos.unrealizedProfit);
            }
        }
        if (pos.marginRatio <= 0.0) {
            const double balance = std::max(0.0, pos.walletBalance > 0.0 ? pos.walletBalance : pos.marginBalance);
            const double unrealizedLoss = pos.unrealizedProfit < 0.0 ? std::fabs(pos.unrealizedProfit) : 0.0;
            const double maintForRatio = std::max(0.0, pos.maintMargin);
            const double numerator = maintForRatio + std::max(0.0, pos.openOrderMargin) + unrealizedLoss;
            if (balance > 0.0 && numerator > 0.0) {
                pos.marginRatio = (numerator / balance) * 100.0;
            }
        }
        pos.marginRatio = normalizeMarginRatioPercent(pos.marginRatio);
        if (!qIsFinite(pos.marginRatio) || pos.marginRatio < 0.0) {
            pos.marginRatio = 0.0;
        }
        parsed.push_back(pos);
    }

    result.ok = true;
    result.positions = parsed;
    return result;
}

BinanceRestClient::FuturesSymbolFilters BinanceRestClient::fetchFuturesSymbolFilters(
    const QString &symbol,
    bool testnet,
    int timeoutMs,
    const QString &baseUrlOverride) {
    FuturesSymbolFilters result;
    const QString cleanSymbol = symbol.trimmed().toUpper();
    if (cleanSymbol.isEmpty()) {
        result.error = QStringLiteral("Symbol is required");
        return result;
    }

    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futuresBaseUrl(testnet, overrideBase);
    const QString url = QStringLiteral("%1%2").arg(base, futuresApiPath(overrideBase, QStringLiteral("/v1/exchangeInfo")));

    QString requestError;
    const QJsonDocument document = httpGetJson(url, {}, timeoutMs, &requestError);
    if (document.isNull() || !document.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance response") : requestError;
        return result;
    }

    const QJsonArray symbols = document.object().value(QStringLiteral("symbols")).toArray();
    for (const QJsonValue &value : symbols) {
        const QJsonObject symObj = value.toObject();
        const QString current = symObj.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        if (current != cleanSymbol) {
            continue;
        }

        bool qpOk = false;
        const int quantityPrecision = symObj.value(QStringLiteral("quantityPrecision")).toVariant().toInt(&qpOk);
        result.quantityPrecision = qpOk ? std::max(0, quantityPrecision) : 0;
        bool ppOk = false;
        const int pricePrecision = symObj.value(QStringLiteral("pricePrecision")).toVariant().toInt(&ppOk);
        result.pricePrecision = ppOk ? std::max(0, pricePrecision) : 0;

        double lotStepSize = 0.0;
        double lotMinQty = 0.0;
        double lotMaxQty = 0.0;
        double marketStepSize = 0.0;
        double marketMinQty = 0.0;
        double marketMaxQty = 0.0;
        double priceTickSize = 0.0;
        const QJsonArray filters = symObj.value(QStringLiteral("filters")).toArray();
        for (const QJsonValue &fValue : filters) {
            const QJsonObject f = fValue.toObject();
            const QString filterType = f.value(QStringLiteral("filterType")).toString().trimmed().toUpper();
            if (filterType == QStringLiteral("LOT_SIZE")) {
                parseJsonNumber(f.value(QStringLiteral("stepSize")), &lotStepSize);
                parseJsonNumber(f.value(QStringLiteral("minQty")), &lotMinQty);
                parseJsonNumber(f.value(QStringLiteral("maxQty")), &lotMaxQty);
            } else if (filterType == QStringLiteral("MARKET_LOT_SIZE")) {
                parseJsonNumber(f.value(QStringLiteral("stepSize")), &marketStepSize);
                parseJsonNumber(f.value(QStringLiteral("minQty")), &marketMinQty);
                parseJsonNumber(f.value(QStringLiteral("maxQty")), &marketMaxQty);
            } else if (filterType == QStringLiteral("MIN_NOTIONAL")
                       || filterType == QStringLiteral("NOTIONAL")) {
                if (!parseJsonNumber(f.value(QStringLiteral("notional")), &result.minNotional)) {
                    parseJsonNumber(f.value(QStringLiteral("minNotional")), &result.minNotional);
                }
            } else if (filterType == QStringLiteral("PRICE_FILTER")) {
                parseJsonNumber(f.value(QStringLiteral("tickSize")), &priceTickSize);
            }
        }

        result.stepSize = marketStepSize > 0.0 ? marketStepSize : lotStepSize;
        result.tickSize = std::max(0.0, priceTickSize);
        result.minQty = marketMinQty > 0.0 ? marketMinQty : lotMinQty;
        result.maxQty = marketMaxQty > 0.0 ? marketMaxQty : lotMaxQty;
        result.stepSize = std::max(0.0, result.stepSize);
        result.minQty = std::max(0.0, result.minQty);
        result.maxQty = std::max(0.0, result.maxQty);
        result.minNotional = std::max(0.0, result.minNotional);
        result.ok = true;
        return result;
    }

    result.error = QStringLiteral("Symbol %1 not found in futures exchangeInfo").arg(cleanSymbol);
    return result;
}

BinanceRestClient::FuturesOrderResult BinanceRestClient::placeFuturesMarketOrder(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    bool testnet,
    bool reduceOnly,
    const QString &positionSide,
    int timeoutMs,
    const QString &baseUrlOverride) {
    FuturesOrderResult result;
    result.symbol = symbol.trimmed().toUpper();
    result.side = side.trimmed().toUpper();
    result.positionSide = positionSide.trimmed().toUpper();
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        result.error = QStringLiteral("Missing API credentials");
        return result;
    }
    if (result.symbol.isEmpty()) {
        result.error = QStringLiteral("Symbol is required");
        return result;
    }
    if (result.side != QStringLiteral("BUY") && result.side != QStringLiteral("SELL")) {
        result.error = QStringLiteral("Side must be BUY or SELL");
        return result;
    }
    if (!qIsFinite(quantity) || quantity <= 0.0) {
        result.error = QStringLiteral("Quantity must be > 0");
        return result;
    }

    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futuresBaseUrl(testnet, overrideBase);

    QUrlQuery query;
    query.addQueryItem(QStringLiteral("symbol"), result.symbol);
    query.addQueryItem(QStringLiteral("side"), result.side);
    query.addQueryItem(QStringLiteral("type"), QStringLiteral("MARKET"));
    query.addQueryItem(QStringLiteral("quantity"), formatDecimalForOrder(quantity, 8));
    const bool hasDirectionalPositionSide = !result.positionSide.isEmpty()
        && result.positionSide != QStringLiteral("BOTH")
        && (result.positionSide == QStringLiteral("LONG") || result.positionSide == QStringLiteral("SHORT"));
    // Binance Futures rejects `reduceOnly` in hedge-mode orders with LONG/SHORT `positionSide`.
    if (reduceOnly && !hasDirectionalPositionSide) {
        query.addQueryItem(QStringLiteral("reduceOnly"), QStringLiteral("true"));
    }
    if (hasDirectionalPositionSide) {
        query.addQueryItem(QStringLiteral("positionSide"), result.positionSide);
    }
    query.addQueryItem(QStringLiteral("timestamp"), QString::number(QDateTime::currentMSecsSinceEpoch()));
    query.addQueryItem(QStringLiteral("recvWindow"), QStringLiteral("5000"));

    const QString queryString = query.toString(QUrl::FullyEncoded);
    const QString signature = hmacSha256Hex(apiSecret, queryString);
    const QString url = QStringLiteral("%1%2?%3&signature=%4")
                            .arg(base, futuresApiPath(overrideBase, QStringLiteral("/v1/order")), queryString, signature);

    QString requestError;
    const QJsonDocument doc = httpRequestJson(
        QStringLiteral("POST"),
        url,
        {{QByteArrayLiteral("X-MBX-APIKEY"), apiKey.toUtf8()}},
        timeoutMs,
        &requestError);
    if (doc.isNull() || !doc.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance order response") : requestError;
        return result;
    }

    const QJsonObject obj = doc.object();
    if (obj.contains(QStringLiteral("code")) || obj.contains(QStringLiteral("msg"))) {
        result.error = QStringLiteral("Binance order error: %1")
                           .arg(obj.value(QStringLiteral("msg")).toString(QStringLiteral("unknown")));
        return result;
    }

    result.status = obj.value(QStringLiteral("status")).toString().trimmed().toUpper();
    result.orderId = obj.value(QStringLiteral("orderId")).toVariant().toString();
    parseJsonNumber(obj.value(QStringLiteral("executedQty")), &result.executedQty);
    parseJsonNumber(obj.value(QStringLiteral("avgPrice")), &result.avgPrice);
    if (!qIsFinite(result.avgPrice) || result.avgPrice <= 0.0) {
        parseJsonNumber(obj.value(QStringLiteral("price")), &result.avgPrice);
    }
    if (!qIsFinite(result.executedQty) || result.executedQty <= 0.0) {
        parseJsonNumber(obj.value(QStringLiteral("origQty")), &result.executedQty);
    }
    result.ok = true;
    return result;
}

BinanceRestClient::FuturesOrderResult BinanceRestClient::placeFuturesLimitOrder(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    double price,
    bool testnet,
    bool reduceOnly,
    const QString &positionSide,
    const QString &timeInForce,
    int timeoutMs,
    const QString &baseUrlOverride) {
    FuturesOrderResult result;
    result.symbol = symbol.trimmed().toUpper();
    result.side = side.trimmed().toUpper();
    result.positionSide = positionSide.trimmed().toUpper();
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        result.error = QStringLiteral("Missing API credentials");
        return result;
    }
    if (result.symbol.isEmpty()) {
        result.error = QStringLiteral("Symbol is required");
        return result;
    }
    if (result.side != QStringLiteral("BUY") && result.side != QStringLiteral("SELL")) {
        result.error = QStringLiteral("Side must be BUY or SELL");
        return result;
    }
    if (!qIsFinite(quantity) || quantity <= 0.0) {
        result.error = QStringLiteral("Quantity must be > 0");
        return result;
    }
    if (!qIsFinite(price) || price <= 0.0) {
        result.error = QStringLiteral("Price must be > 0");
        return result;
    }

    const QString overrideBase = baseUrlOverride.trimmed();
    const QString base = futuresBaseUrl(testnet, overrideBase);

    QUrlQuery query;
    query.addQueryItem(QStringLiteral("symbol"), result.symbol);
    query.addQueryItem(QStringLiteral("side"), result.side);
    query.addQueryItem(QStringLiteral("type"), QStringLiteral("LIMIT"));
    query.addQueryItem(QStringLiteral("timeInForce"), timeInForce.trimmed().isEmpty() ? QStringLiteral("IOC")
                                                                                      : timeInForce.trimmed().toUpper());
    query.addQueryItem(QStringLiteral("quantity"), formatDecimalForOrder(quantity, 8));
    query.addQueryItem(QStringLiteral("price"), formatDecimalForOrder(price, 8));
    const bool hasDirectionalPositionSide = !result.positionSide.isEmpty()
        && result.positionSide != QStringLiteral("BOTH")
        && (result.positionSide == QStringLiteral("LONG") || result.positionSide == QStringLiteral("SHORT"));
    if (reduceOnly && !hasDirectionalPositionSide) {
        query.addQueryItem(QStringLiteral("reduceOnly"), QStringLiteral("true"));
    }
    if (hasDirectionalPositionSide) {
        query.addQueryItem(QStringLiteral("positionSide"), result.positionSide);
    }
    query.addQueryItem(QStringLiteral("timestamp"), QString::number(QDateTime::currentMSecsSinceEpoch()));
    query.addQueryItem(QStringLiteral("recvWindow"), QStringLiteral("5000"));

    const QString queryString = query.toString(QUrl::FullyEncoded);
    const QString signature = hmacSha256Hex(apiSecret, queryString);
    const QString url = QStringLiteral("%1%2?%3&signature=%4")
                            .arg(base, futuresApiPath(overrideBase, QStringLiteral("/v1/order")), queryString, signature);

    QString requestError;
    const QJsonDocument doc = httpRequestJson(
        QStringLiteral("POST"),
        url,
        {{QByteArrayLiteral("X-MBX-APIKEY"), apiKey.toUtf8()}},
        timeoutMs,
        &requestError);
    if (doc.isNull() || !doc.isObject()) {
        result.error = requestError.isEmpty() ? QStringLiteral("Unexpected Binance order response") : requestError;
        return result;
    }

    const QJsonObject obj = doc.object();
    if (obj.contains(QStringLiteral("code")) || obj.contains(QStringLiteral("msg"))) {
        result.error = QStringLiteral("Binance order error: %1")
                           .arg(obj.value(QStringLiteral("msg")).toString(QStringLiteral("unknown")));
        return result;
    }

    result.status = obj.value(QStringLiteral("status")).toString().trimmed().toUpper();
    result.orderId = obj.value(QStringLiteral("orderId")).toVariant().toString();
    parseJsonNumber(obj.value(QStringLiteral("executedQty")), &result.executedQty);
    parseJsonNumber(obj.value(QStringLiteral("avgPrice")), &result.avgPrice);
    if (!qIsFinite(result.avgPrice) || result.avgPrice <= 0.0) {
        parseJsonNumber(obj.value(QStringLiteral("price")), &result.avgPrice);
    }
    if (!qIsFinite(result.executedQty) || result.executedQty <= 0.0) {
        parseJsonNumber(obj.value(QStringLiteral("origQty")), &result.executedQty);
    }
    result.ok = true;
    return result;
}
