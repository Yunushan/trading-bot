#include "BacktestWindow.h"
#include "BinanceRestClient.h"

#include <QCheckBox>
#include <QAbstractItemView>
#include <QComboBox>
#include <QDate>
#include <QDateEdit>
#include <QDesktopServices>
#include <QDoubleSpinBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QCoreApplication>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QHeaderView>
#include <QLabel>
#include <QDebug>
#include <QLineEdit>
#include <QListWidget>
#include <QMap>
#include <QPushButton>
#include <QMessageBox>
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QFontMetrics>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QPainter>
#include <QPaintEvent>
#include <QProcess>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QVariant>
#include <QScrollArea>
#include <QSet>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardItemModel>
#include <QSizePolicy>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTabWidget>
#include <QStackedWidget>
#include <QTimer>
#include <QUrl>
#include <QVector>
#ifndef HAS_QT_WEBENGINE
#define HAS_QT_WEBENGINE 0
#endif
#ifndef HAS_QT_WEBSOCKETS
#define HAS_QT_WEBSOCKETS 0
#endif
#include <QVBoxLayout>
#include <QtMath>
#if HAS_QT_WEBENGINE
#include <QWebEngineView>
#endif

#include <algorithm>
#include <functional>
#include <set>

namespace {
class NativeKlineChartWidget final : public QWidget {
public:
    explicit NativeKlineChartWidget(QWidget *parent = nullptr)
        : QWidget(parent) {
        setMinimumHeight(460);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    }

    void setCandles(const QVector<BinanceRestClient::KlineCandle> &candles) {
        candles_ = candles;
        update();
    }

    void setOverlayMessage(const QString &message) {
        overlayMessage_ = message;
        update();
    }

protected:
    void paintEvent(QPaintEvent *event) override {
        QWidget::paintEvent(event);

        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);

        QRect frame = rect().adjusted(0, 0, -1, -1);
        painter.fillRect(frame, QColor("#0b1020"));
        painter.setPen(QPen(QColor("#1f2937"), 1.0));
        painter.drawRect(frame);

        QRect chartRect = frame.adjusted(14, 22, -14, -34);
        if (chartRect.width() < 24 || chartRect.height() < 24) {
            return;
        }

        painter.setPen(QPen(QColor("#1f2937"), 1.0, Qt::DashLine));
        for (int i = 0; i <= 4; ++i) {
            const int y = chartRect.top() + (chartRect.height() * i) / 4;
            painter.drawLine(chartRect.left(), y, chartRect.right(), y);
        }

        if (candles_.isEmpty()) {
            painter.setPen(QColor("#94a3b8"));
            painter.drawText(chartRect, Qt::AlignCenter, "No chart data loaded.");
            return;
        }

        const int candleCount = static_cast<int>(candles_.size());
        const int maxVisible = std::max(25, chartRect.width() / 6);
        const int start = std::max(0, candleCount - maxVisible);
        const int visible = candleCount - start;
        if (visible <= 0) {
            painter.setPen(QColor("#94a3b8"));
            painter.drawText(chartRect, Qt::AlignCenter, "No visible candles.");
            return;
        }

        double low = 0.0;
        double high = 0.0;
        bool initialized = false;
        for (int i = start; i < candleCount; ++i) {
            const auto &c = candles_.at(i);
            if (!qIsFinite(c.low) || !qIsFinite(c.high)) {
                continue;
            }
            if (!initialized) {
                low = c.low;
                high = c.high;
                initialized = true;
                continue;
            }
            low = std::min(low, c.low);
            high = std::max(high, c.high);
        }
        if (!initialized) {
            painter.setPen(QColor("#94a3b8"));
            painter.drawText(chartRect, Qt::AlignCenter, "Invalid candle values.");
            return;
        }

        const double span = std::max(1e-9, high - low);
        auto yFromPrice = [&](double value) {
            const double clamped = std::clamp((value - low) / span, 0.0, 1.0);
            return chartRect.bottom() - clamped * chartRect.height();
        };

        const double spacing = static_cast<double>(chartRect.width()) / std::max(1, visible);
        const double bodyWidth = std::max(2.0, spacing * 0.65);

        for (int i = 0; i < visible; ++i) {
            const auto &candle = candles_.at(start + i);
            if (!qIsFinite(candle.open) || !qIsFinite(candle.close)
                || !qIsFinite(candle.high) || !qIsFinite(candle.low)) {
                continue;
            }

            const double x = chartRect.left() + (i + 0.5) * spacing;
            const double yHigh = yFromPrice(candle.high);
            const double yLow = yFromPrice(candle.low);
            const double yOpen = yFromPrice(candle.open);
            const double yClose = yFromPrice(candle.close);

            const bool bull = candle.close >= candle.open;
            const QColor color = bull ? QColor("#22c55e") : QColor("#ef4444");

            painter.setPen(QPen(color, 1.2));
            painter.drawLine(QPointF(x, yHigh), QPointF(x, yLow));

            const double top = std::min(yOpen, yClose);
            const double bottom = std::max(yOpen, yClose);
            QRectF body(x - bodyWidth / 2.0, top, bodyWidth, std::max(1.0, bottom - top));
            painter.fillRect(body, color);
        }

        painter.setPen(QColor("#e5e7eb"));
        const auto &last = candles_.constLast();
        const QString summary = QString("Candles: %1   Last Close: %2   High: %3   Low: %4")
            .arg(visible)
            .arg(last.close, 0, 'f', 4)
            .arg(high, 0, 'f', 4)
            .arg(low, 0, 'f', 4);
        painter.drawText(frame.adjusted(10, frame.height() - 24, -10, -6), Qt::AlignLeft | Qt::AlignVCenter, summary);

        if (!overlayMessage_.trimmed().isEmpty()) {
            const QRect hintRect = QRect(frame.left() + 10, frame.top() + 6, frame.width() - 20, 16);
            painter.setPen(QColor("#93c5fd"));
            const QFontMetrics metrics(painter.font());
            painter.drawText(hintRect, Qt::AlignLeft | Qt::AlignVCenter, metrics.elidedText(overlayMessage_, Qt::ElideRight, hintRect.width()));
        }
    }

private:
    QVector<BinanceRestClient::KlineCandle> candles_;
    QString overlayMessage_;
};

QString tradingViewIntervalFor(QString interval) {
    interval = interval.trimmed().toLower();
    static const QMap<QString, QString> mapping = {
        {"1m", "1"},
        {"3m", "3"},
        {"5m", "5"},
        {"15m", "15"},
        {"30m", "30"},
        {"1h", "60"},
        {"2h", "120"},
        {"4h", "240"},
        {"6h", "360"},
        {"8h", "480"},
        {"12h", "720"},
        {"1d", "1D"},
        {"3d", "3D"},
        {"1w", "1W"},
        {"1mo", "1M"},
    };
    return mapping.value(interval, "60");
}

QString normalizeChartSymbol(QString symbol) {
    QString out = symbol.trimmed().toUpper();
    out.remove('/');
    if (out.endsWith(".P")) {
        out.chop(2);
    }
    return out;
}

QString spotSymbolWithUnderscore(const QString &symbol) {
    if (symbol.contains('_')) {
        return symbol;
    }
    static const QStringList quoteAssets = {
        "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USD", "BTC", "ETH", "BNB",
        "EUR", "TRY", "GBP", "AUD", "BRL", "RUB", "IDR", "UAH", "ZAR", "BIDR", "PAX"
    };
    for (const auto &quote : quoteAssets) {
        if (symbol.endsWith(quote) && symbol.size() > quote.size()) {
            return symbol.left(symbol.size() - quote.size()) + "_" + quote;
        }
    }
    return symbol;
}

QString buildBinanceWebUrl(const QString &symbol, const QString &interval, const QString &marketKey) {
    QString sym = normalizeChartSymbol(symbol);
    const QString cleanInterval = interval.trimmed();
    QString url;
    if (marketKey.trimmed().toLower() == "spot") {
        sym = spotSymbolWithUnderscore(sym);
        url = QString("https://www.binance.com/en/trade/%1?type=spot").arg(sym);
    } else {
        url = QString("https://www.binance.com/en/futures/%1").arg(sym);
    }
    if (!cleanInterval.isEmpty()) {
        url += (url.contains('?') ? "&" : "?");
        url += QString("interval=%1").arg(cleanInterval);
    }
    return url;
}

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

QString exchangeFromIndicatorSource(const QString &sourceText) {
    const QString normalized = normalizeExchangeKey(sourceText);
    static const QSet<QString> known = {
        QStringLiteral("Binance"),
        QStringLiteral("Bybit"),
        QStringLiteral("OKX"),
        QStringLiteral("Gate"),
        QStringLiteral("Bitget"),
        QStringLiteral("MEXC"),
        QStringLiteral("KuCoin"),
    };
    if (known.contains(normalized)) {
        return normalized;
    }
    return QString();
}

QString preferredIndicatorSourceForExchange(const QString &exchangeKey, const QString &currentSource) {
    const QString normalized = normalizeExchangeKey(exchangeKey);
    if (normalized.compare(QStringLiteral("Binance"), Qt::CaseInsensitive) == 0) {
        if (currentSource.trimmed().toLower().contains(QStringLiteral("binance"))) {
            return currentSource.trimmed();
        }
        return QStringLiteral("Binance futures");
    }
    if (normalized == QStringLiteral("MEXC")) {
        return QStringLiteral("Mexc");
    }
    if (normalized == QStringLiteral("KuCoin")) {
        return QStringLiteral("Kucoin");
    }
    return normalized;
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

QString extractSemverFromText(const QString &value) {
    static const QRegularExpression re(QStringLiteral("(\\d+(?:[._]\\d+){1,3})"));
    const QRegularExpressionMatch match = re.match(value);
    if (!match.hasMatch()) {
        return QString();
    }
    QString out = match.captured(1).trimmed();
    out.replace('_', '.');
    return out;
}

QString normalizeVersionText(const QString &value) {
    const QString trimmed = value.trimmed();
    if (trimmed.isEmpty()) {
        return QString();
    }
    const QString semver = extractSemverFromText(trimmed);
    return semver.isEmpty() ? trimmed : semver;
}

bool isMissingVersionMarker(const QString &value) {
    const QString normalized = value.trimmed().toLower();
    return normalized.isEmpty()
        || normalized == QStringLiteral("not installed")
        || normalized == QStringLiteral("not detected")
        || normalized == QStringLiteral("missing")
        || normalized == QStringLiteral("unknown")
        || normalized == QStringLiteral("disabled")
        || normalized == QStringLiteral("bundle")
        || normalized == QStringLiteral("bundled");
}

QString readTextFile(const QString &path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return QString();
    }
    return QString::fromUtf8(file.readAll());
}

QString extractMacroString(const QString &text, const QString &macroName) {
    if (text.isEmpty() || macroName.trimmed().isEmpty()) {
        return QString();
    }
    const QRegularExpression re(
        QStringLiteral("^\\s*#\\s*define\\s+%1\\s+\"([^\"]+)\"")
            .arg(QRegularExpression::escape(macroName)),
        QRegularExpression::MultilineOption);
    const QRegularExpressionMatch match = re.match(text);
    if (!match.hasMatch()) {
        return QString();
    }
    return normalizeVersionText(match.captured(1));
}

int extractMacroInt(const QString &text, const QString &macroName, bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    if (text.isEmpty() || macroName.trimmed().isEmpty()) {
        return 0;
    }
    const QRegularExpression re(
        QStringLiteral("^\\s*#\\s*define\\s+%1\\s+(\\d+)")
            .arg(QRegularExpression::escape(macroName)),
        QRegularExpression::MultilineOption);
    const QRegularExpressionMatch match = re.match(text);
    if (!match.hasMatch()) {
        return 0;
    }
    bool ok = false;
    const int value = match.captured(1).toInt(&ok);
    if (okOut) {
        *okOut = ok;
    }
    return ok ? value : 0;
}

void appendUniquePath(QStringList &paths, const QString &pathValue, bool mustExist = true) {
    const QString cleaned = QDir::cleanPath(pathValue.trimmed());
    if (cleaned.isEmpty()) {
        return;
    }
    const QFileInfo info(cleaned);
    if (mustExist && !info.exists()) {
        return;
    }
    const QString canonical = info.exists() ? info.canonicalFilePath() : cleaned;
    const QString absolute = canonical.isEmpty() ? info.absoluteFilePath() : canonical;
    if (absolute.isEmpty()) {
        return;
    }
    if (!paths.contains(absolute, Qt::CaseInsensitive)) {
        paths.push_back(absolute);
    }
}

QStringList dependencyProjectRoots() {
    QStringList roots;
    auto addAncestors = [&roots](const QString &startPath) {
        QDir cursor(startPath);
        for (int i = 0; i < 8; ++i) {
            appendUniquePath(roots, cursor.absolutePath(), true);
            if (!cursor.cdUp()) {
                break;
            }
        }
    };
    addAncestors(QCoreApplication::applicationDirPath());
    addAncestors(QDir::currentPath());
    return roots;
}

QStringList dependencyVcpkgRoots() {
    QStringList roots;
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString envRoot = env.value(QStringLiteral("VCPKG_ROOT")).trimmed();
    if (!envRoot.isEmpty()) {
        appendUniquePath(roots, envRoot, true);
    }
    appendUniquePath(roots, QStringLiteral("C:/vcpkg"), true);
    appendUniquePath(roots, QDir(QDir::homePath()).filePath(QStringLiteral("vcpkg")), true);
    for (const QString &projectRoot : dependencyProjectRoots()) {
        appendUniquePath(roots, QDir(projectRoot).filePath(QStringLiteral(".vcpkg")), true);
    }
    return roots;
}

QStringList dependencyIncludeRoots() {
    static QStringList cache;
    static bool ready = false;
    if (ready) {
        return cache;
    }
    ready = true;

    auto addInstalledIncludeDirs = [&](const QString &installedRoot) {
        QDir installedDir(installedRoot);
        if (!installedDir.exists()) {
            return;
        }
        const QFileInfoList archDirs = installedDir.entryInfoList(
            QDir::Dirs | QDir::NoDotAndDotDot | QDir::Readable);
        for (const QFileInfo &archInfo : archDirs) {
            appendUniquePath(cache, QDir(archInfo.absoluteFilePath()).filePath(QStringLiteral("include")), true);
        }
    };

    for (const QString &projectRoot : dependencyProjectRoots()) {
        addInstalledIncludeDirs(QDir(projectRoot).filePath(QStringLiteral("vcpkg_installed")));
        addInstalledIncludeDirs(QDir(projectRoot).filePath(QStringLiteral(".vcpkg/installed")));
    }
    for (const QString &vcpkgRoot : dependencyVcpkgRoots()) {
        addInstalledIncludeDirs(QDir(vcpkgRoot).filePath(QStringLiteral("installed")));
    }
    return cache;
}

QString findHeaderPath(const QStringList &relativeCandidates) {
    if (relativeCandidates.isEmpty()) {
        return QString();
    }
    for (const QString &includeRoot : dependencyIncludeRoots()) {
        QDir base(includeRoot);
        for (const QString &relative : relativeCandidates) {
            QString rel = relative.trimmed();
            if (rel.isEmpty()) {
                continue;
            }
            rel.replace('\\', '/');
            const QString candidate = base.filePath(rel);
            if (QFileInfo::exists(candidate)) {
                return QDir::cleanPath(candidate);
            }
        }
    }
    return QString();
}

void insertInstalledVersionEntry(QMap<QString, QString> &versions, const QString &name, const QString &version) {
    const QString key = name.trimmed().toLower();
    if (key.isEmpty()) {
        return;
    }
    const QString normalizedVersion = normalizeVersionText(version);
    if (isMissingVersionMarker(normalizedVersion)) {
        return;
    }
    if (!versions.contains(key)) {
        versions.insert(key, normalizedVersion);
    }
}

void collectInstalledVersionsFromArray(const QJsonArray &array, QMap<QString, QString> &versions) {
    for (const QJsonValue &entry : array) {
        if (!entry.isObject()) {
            continue;
        }
        const QJsonObject item = entry.toObject();
        const QString name = item.value(QStringLiteral("name")).toString().trimmed().isEmpty()
            ? item.value(QStringLiteral("label")).toString().trimmed()
            : item.value(QStringLiteral("name")).toString().trimmed();
        const QString installed = item.value(QStringLiteral("installed")).toString().trimmed().isEmpty()
            ? item.value(QStringLiteral("version")).toString().trimmed()
            : item.value(QStringLiteral("installed")).toString().trimmed();
        insertInstalledVersionEntry(versions, name, installed);
    }
}

QMap<QString, QString> loadPackagedInstalledVersions() {
    static QMap<QString, QString> cache;
    static bool ready = false;
    if (ready) {
        return cache;
    }
    ready = true;

    QStringList manifestPaths;
    auto addManifestPath = [&manifestPaths](const QString &path) {
        const QString cleaned = QDir::cleanPath(path.trimmed());
        if (cleaned.isEmpty()) {
            return;
        }
        const QFileInfo info(cleaned);
        if (!info.exists() || !info.isFile()) {
            return;
        }
        const QString canonical = info.canonicalFilePath();
        const QString absolute = canonical.isEmpty() ? info.absoluteFilePath() : canonical;
        if (absolute.isEmpty()) {
            return;
        }
        if (!manifestPaths.contains(absolute, Qt::CaseInsensitive)) {
            manifestPaths.push_back(absolute);
        }
    };

    const QString envManifestPath = QString::fromLocal8Bit(qgetenv("TB_CPP_DEPS_JSON")).trimmed();
    if (!envManifestPath.isEmpty()) {
        addManifestPath(envManifestPath);
    }

    const QStringList candidateNames = {
        QStringLiteral("cpp-deps.json"),
        QStringLiteral("cpp-env-versions.json"),
        QStringLiteral("TB_CPP_ENV_VERSIONS.json"),
        QStringLiteral("versions.json"),
    };

    QDir appDir(QCoreApplication::applicationDirPath());
    for (const QString &name : candidateNames) {
        addManifestPath(appDir.filePath(name));
    }

    for (int i = 0; i < 3; ++i) {
        if (!appDir.cdUp()) {
            break;
        }
        for (const QString &name : candidateNames) {
            addManifestPath(appDir.filePath(name));
        }
    }

    for (const QString &manifestPath : manifestPaths) {
        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(readTextFile(manifestPath).toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError || doc.isNull()) {
            continue;
        }

        QMap<QString, QString> parsed;
        if (doc.isObject()) {
            const QJsonObject root = doc.object();
            collectInstalledVersionsFromArray(root.value(QStringLiteral("dependencies")).toArray(), parsed);
            collectInstalledVersionsFromArray(root.value(QStringLiteral("rows")).toArray(), parsed);

            for (auto it = root.constBegin(); it != root.constEnd(); ++it) {
                if (!it.value().isString()) {
                    continue;
                }
                insertInstalledVersionEntry(parsed, it.key(), it.value().toString());
            }
        } else if (doc.isArray()) {
            collectInstalledVersionsFromArray(doc.array(), parsed);
        }

        if (!parsed.isEmpty()) {
            cache = parsed;
            break;
        }
    }
    return cache;
}

QString packagedInstalledVersion(const QStringList &names) {
    if (names.isEmpty()) {
        return QString();
    }
    const QMap<QString, QString> versions = loadPackagedInstalledVersions();
    for (const QString &name : names) {
        const QString key = name.trimmed().toLower();
        if (key.isEmpty()) {
            continue;
        }
        const QString value = versions.value(key).trimmed();
        if (!isMissingVersionMarker(value)) {
            return value;
        }
    }
    return QString();
}

QString releaseTagFromMetadataDirs() {
    static QString cachedTag;
    static bool ready = false;
    if (ready) {
        return cachedTag;
    }
    ready = true;

    const QStringList metadataNames = {
        QStringLiteral("release-info.json"),
        QStringLiteral("tb-release.json"),
        QStringLiteral("release-tag.txt"),
        QStringLiteral("tb-release.txt"),
    };
    const QStringList jsonKeys = {
        QStringLiteral("release_tag"),
        QStringLiteral("tag_name"),
        QStringLiteral("tag"),
        QStringLiteral("version"),
    };

    auto tagFromText = [](const QString &text) -> QString {
        const QString normalized = normalizeVersionText(text);
        return isMissingVersionMarker(normalized) ? QString() : normalized;
    };

    auto tagFromJsonObject = [&](const QJsonObject &obj) -> QString {
        for (const QString &key : jsonKeys) {
            const QString value = obj.value(key).toString();
            const QString normalized = tagFromText(value);
            if (!normalized.isEmpty()) {
                return normalized;
            }
        }
        return QString();
    };

    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 4; ++i) {
        for (const QString &name : metadataNames) {
            const QString path = dir.filePath(name);
            QFile file(path);
            if (!file.exists() || !file.open(QIODevice::ReadOnly | QIODevice::Text)) {
                continue;
            }
            const QByteArray payload = file.readAll();
            file.close();
            if (payload.isEmpty()) {
                continue;
            }

            QString resolvedTag;
            if (name.endsWith(QStringLiteral(".json"), Qt::CaseInsensitive)) {
                QJsonParseError parseError{};
                const QJsonDocument doc = QJsonDocument::fromJson(payload, &parseError);
                if (parseError.error == QJsonParseError::NoError && doc.isObject()) {
                    resolvedTag = tagFromJsonObject(doc.object());
                }
            } else {
                const QStringList lines = QString::fromUtf8(payload).split(QRegularExpression(QStringLiteral("\\r?\\n")));
                for (const QString &line : lines) {
                    const QString normalized = tagFromText(line);
                    if (!normalized.isEmpty()) {
                        resolvedTag = normalized;
                        break;
                    }
                }
            }
            if (!resolvedTag.isEmpty()) {
                cachedTag = resolvedTag;
                return cachedTag;
            }
        }
        if (!dir.cdUp()) {
            break;
        }
    }
    return QString();
}

QMap<QString, QString> loadVcpkgInstalledVersions() {
    static QMap<QString, QString> cache;
    static bool ready = false;
    if (ready) {
        return cache;
    }
    ready = true;

    QStringList statusFiles;
    auto addStatusFile = [&statusFiles](const QString &path) {
        const QFileInfo info(path);
        if (!info.exists() || !info.isFile()) {
            return;
        }
        const QString abs = info.canonicalFilePath().isEmpty() ? info.absoluteFilePath() : info.canonicalFilePath();
        if (!statusFiles.contains(abs, Qt::CaseInsensitive)) {
            statusFiles.push_back(abs);
        }
    };

    for (const QString &projectRoot : dependencyProjectRoots()) {
        addStatusFile(QDir(projectRoot).filePath(QStringLiteral(".vcpkg/installed/vcpkg/status")));
    }
    for (const QString &vcpkgRoot : dependencyVcpkgRoots()) {
        addStatusFile(QDir(vcpkgRoot).filePath(QStringLiteral("installed/vcpkg/status")));
    }

    static const QRegularExpression splitRe(QStringLiteral("\\r?\\n\\r?\\n"));
    for (const QString &statusPath : statusFiles) {
        const QString content = readTextFile(statusPath);
        if (content.trimmed().isEmpty()) {
            continue;
        }
        const QStringList blocks = content.split(splitRe, Qt::SkipEmptyParts);
        for (const QString &block : blocks) {
            QString packageName;
            QString featureName;
            QString versionValue;
            QString statusValue;
            const QStringList lines = block.split(QRegularExpression(QStringLiteral("\\r?\\n")), Qt::SkipEmptyParts);
            for (const QString &line : lines) {
                if (line.startsWith(QStringLiteral("Package: "), Qt::CaseInsensitive)) {
                    packageName = line.section(':', 1).trimmed().toLower();
                    continue;
                }
                if (line.startsWith(QStringLiteral("Feature: "), Qt::CaseInsensitive)) {
                    featureName = line.section(':', 1).trimmed().toLower();
                    continue;
                }
                if (line.startsWith(QStringLiteral("Version: "), Qt::CaseInsensitive)) {
                    versionValue = line.section(':', 1).trimmed();
                    continue;
                }
                if (line.startsWith(QStringLiteral("Status: "), Qt::CaseInsensitive)) {
                    statusValue = line.section(':', 1).trimmed().toLower();
                    continue;
                }
            }
            if (packageName.isEmpty()) {
                continue;
            }
            if (!(featureName.isEmpty() || featureName == QStringLiteral("core"))) {
                continue;
            }
            if (!statusValue.contains(QStringLiteral("install ok installed"))) {
                continue;
            }
            const QString normalizedVersion = normalizeVersionText(versionValue);
            if (!normalizedVersion.isEmpty() && !cache.contains(packageName)) {
                cache.insert(packageName, normalizedVersion);
            }
        }
    }
    return cache;
}

QString vcpkgInstalledVersion(const QStringList &packageNames) {
    if (packageNames.isEmpty()) {
        return QString();
    }
    const QMap<QString, QString> versions = loadVcpkgInstalledVersions();
    for (const QString &name : packageNames) {
        const QString key = name.trimmed().toLower();
        if (key.isEmpty()) {
            continue;
        }
        const QString value = versions.value(key).trimmed();
        if (!value.isEmpty()) {
            return value;
        }
    }
    return QString();
}

QString detectEigenVersion() {
    const QString packagedVersion = packagedInstalledVersion({
        QStringLiteral("eigen"),
        QStringLiteral("eigen3"),
    });
    if (!packagedVersion.isEmpty()) {
        return packagedVersion;
    }
    const QString vcpkgVersion = vcpkgInstalledVersion({QStringLiteral("eigen3")});
    if (!vcpkgVersion.isEmpty()) {
        return vcpkgVersion;
    }
    const QString header = findHeaderPath({
        QStringLiteral("eigen3/Eigen/src/Core/util/Macros.h"),
        QStringLiteral("Eigen/src/Core/util/Macros.h"),
    });
    if (header.isEmpty()) {
        return QString();
    }
    const QString text = readTextFile(header);
    bool okWorld = false;
    bool okMajor = false;
    bool okMinor = false;
    const int world = extractMacroInt(text, QStringLiteral("EIGEN_WORLD_VERSION"), &okWorld);
    const int major = extractMacroInt(text, QStringLiteral("EIGEN_MAJOR_VERSION"), &okMajor);
    const int minor = extractMacroInt(text, QStringLiteral("EIGEN_MINOR_VERSION"), &okMinor);
    if (okWorld && okMajor && okMinor) {
        return QStringLiteral("%1.%2.%3").arg(world).arg(major).arg(minor);
    }
    return QStringLiteral("Installed");
}

QString detectXtensorVersion() {
    const QString packagedVersion = packagedInstalledVersion({QStringLiteral("xtensor")});
    if (!packagedVersion.isEmpty()) {
        return packagedVersion;
    }
    const QString vcpkgVersion = vcpkgInstalledVersion({QStringLiteral("xtensor")});
    if (!vcpkgVersion.isEmpty()) {
        return vcpkgVersion;
    }
    const QString header = findHeaderPath({
        QStringLiteral("xtensor/core/xtensor_config.hpp"),
        QStringLiteral("xtensor/xtensor_config.hpp"),
    });
    if (header.isEmpty()) {
        return QString();
    }
    const QString text = readTextFile(header);
    bool okMajor = false;
    bool okMinor = false;
    bool okPatch = false;
    const int major = extractMacroInt(text, QStringLiteral("XTENSOR_VERSION_MAJOR"), &okMajor);
    const int minor = extractMacroInt(text, QStringLiteral("XTENSOR_VERSION_MINOR"), &okMinor);
    const int patch = extractMacroInt(text, QStringLiteral("XTENSOR_VERSION_PATCH"), &okPatch);
    if (okMajor && okMinor && okPatch) {
        return QStringLiteral("%1.%2.%3").arg(major).arg(minor).arg(patch);
    }
    const QString macroVersion = extractMacroString(text, QStringLiteral("XTENSOR_VERSION"));
    return macroVersion.isEmpty() ? QStringLiteral("Installed") : macroVersion;
}

QString detectTaLibVersion() {
    const QString packagedVersion = packagedInstalledVersion({
        QStringLiteral("ta-lib"),
        QStringLiteral("talib"),
    });
    if (!packagedVersion.isEmpty()) {
        return packagedVersion;
    }
    const QString vcpkgVersion = vcpkgInstalledVersion({QStringLiteral("talib"), QStringLiteral("ta-lib")});
    if (!vcpkgVersion.isEmpty()) {
        return vcpkgVersion;
    }
    const QString header = findHeaderPath({
        QStringLiteral("ta-lib/ta_defs.h"),
        QStringLiteral("ta_defs.h"),
    });
    if (header.isEmpty()) {
        return QString();
    }
    const QString text = readTextFile(header);
    const QString macroString = extractMacroString(text, QStringLiteral("TA_LIB_VERSION_STR"));
    if (!macroString.isEmpty()) {
        return macroString;
    }
    bool okMajor = false;
    bool okMinor = false;
    bool okPatch = false;
    const int major = extractMacroInt(text, QStringLiteral("TA_LIB_VERSION_MAJOR"), &okMajor);
    const int minor = extractMacroInt(text, QStringLiteral("TA_LIB_VERSION_MINOR"), &okMinor);
    const int patch = extractMacroInt(text, QStringLiteral("TA_LIB_VERSION_PATCH"), &okPatch);
    if (okMajor && okMinor && okPatch) {
        return QStringLiteral("%1.%2.%3").arg(major).arg(minor).arg(patch);
    }
    return QStringLiteral("Installed");
}

QString detectCprVersion() {
    const QString packagedVersion = packagedInstalledVersion({QStringLiteral("cpr")});
    if (!packagedVersion.isEmpty()) {
        return packagedVersion;
    }
    const QString vcpkgVersion = vcpkgInstalledVersion({QStringLiteral("cpr")});
    if (!vcpkgVersion.isEmpty()) {
        return vcpkgVersion;
    }
    const QString header = findHeaderPath({QStringLiteral("cpr/cprver.h")});
    if (header.isEmpty()) {
        return QString();
    }
    const QString text = readTextFile(header);
    const QString macroVersion = extractMacroString(text, QStringLiteral("CPR_VERSION"));
    if (!macroVersion.isEmpty()) {
        return macroVersion;
    }
    bool okMajor = false;
    bool okMinor = false;
    bool okPatch = false;
    const int major = extractMacroInt(text, QStringLiteral("CPR_VERSION_MAJOR"), &okMajor);
    const int minor = extractMacroInt(text, QStringLiteral("CPR_VERSION_MINOR"), &okMinor);
    const int patch = extractMacroInt(text, QStringLiteral("CPR_VERSION_PATCH"), &okPatch);
    if (okMajor && okMinor && okPatch) {
        return QStringLiteral("%1.%2.%3").arg(major).arg(minor).arg(patch);
    }
    return QStringLiteral("Installed");
}

QString detectLibcurlVersionFromCli() {
    const QString executable = QStandardPaths::findExecutable(QStringLiteral("curl"));
    if (executable.isEmpty()) {
        return QString();
    }
    QProcess process;
    process.start(executable, {QStringLiteral("--version")});
    if (!process.waitForStarted(1200)) {
        return QString();
    }
    process.waitForFinished(2000);
    const QString output = QString::fromUtf8(process.readAllStandardOutput()) + QString::fromUtf8(process.readAllStandardError());
    static const QRegularExpression libcurlRe(QStringLiteral("libcurl/([0-9]+(?:\\.[0-9]+){1,3})"));
    static const QRegularExpression curlRe(QStringLiteral("\\bcurl\\s+([0-9]+(?:\\.[0-9]+){1,3})"));
    QRegularExpressionMatch match = libcurlRe.match(output);
    if (match.hasMatch()) {
        return normalizeVersionText(match.captured(1));
    }
    match = curlRe.match(output);
    if (match.hasMatch()) {
        return normalizeVersionText(match.captured(1));
    }
    return QString();
}

QString detectLibcurlVersion() {
    const QString packagedVersion = packagedInstalledVersion({
        QStringLiteral("libcurl"),
        QStringLiteral("curl"),
    });
    if (!packagedVersion.isEmpty()) {
        return packagedVersion;
    }
    const QString vcpkgVersion = vcpkgInstalledVersion({QStringLiteral("curl"), QStringLiteral("libcurl")});
    if (!vcpkgVersion.isEmpty()) {
        return vcpkgVersion;
    }
    const QString header = findHeaderPath({QStringLiteral("curl/curlver.h")});
    if (!header.isEmpty()) {
        const QString macroVersion = extractMacroString(readTextFile(header), QStringLiteral("LIBCURL_VERSION"));
        if (!macroVersion.isEmpty()) {
            return macroVersion;
        }
        return QStringLiteral("Installed");
    }
    return detectLibcurlVersionFromCli();
}

QString installedOrMissing(const QString &value) {
    const QString normalized = normalizeVersionText(value);
    if (!normalized.isEmpty()) {
        return normalized;
    }
    return QStringLiteral("Not installed");
}

QString formatDuration(qint64 seconds) {
    const qint64 mins = seconds / 60;
    const qint64 hrs = mins / 60;
    const qint64 days = hrs / 24;
    const qint64 months = days / 30;
    if (months > 0) {
        return QString::number(months) + "mo";
    }
    if (days > 0) {
        return QString::number(days) + "d";
    }
    if (hrs > 0) {
        return QString::number(hrs) + "h";
    }
    if (mins > 0) {
        return QString::number(mins) + "m";
    }
    return QString::number(seconds) + "s";
}
} // namespace

BacktestWindow::BacktestWindow(QWidget *parent)
    : QMainWindow(parent),
      symbolList_(nullptr),
      intervalList_(nullptr),
      customIntervalEdit_(nullptr),
      statusLabel_(nullptr),
      botStatusLabel_(nullptr),
      botTimeLabel_(nullptr),
      runButton_(nullptr),
      stopButton_(nullptr),
      addSelectedBtn_(nullptr),
      addAllBtn_(nullptr),
      symbolSourceCombo_(nullptr),
      resultsTable_(nullptr),
      botTimer_(nullptr),
      tabs_(nullptr),
      backtestTab_(nullptr),
      dashboardThemeCombo_(nullptr),
      dashboardPage_(nullptr),
      dashboardExchangeCombo_(nullptr),
      dashboardIndicatorSourceCombo_(nullptr),
      codePage_(nullptr),
      chartMarketCombo_(nullptr),
      chartSymbolCombo_(nullptr),
      chartIntervalCombo_(nullptr),
      chartViewModeCombo_(nullptr),
      chartAutoFollowCheck_(nullptr),
      chartPnlActiveLabel_(nullptr),
      chartPnlClosedLabel_(nullptr),
      chartBotStatusLabel_(nullptr),
      chartBotTimeLabel_(nullptr) {
    setWindowTitle("Trading Bot");
    setMinimumSize(640, 420);
    resize(1350, 900);

    auto *central = new QWidget(this);
    setCentralWidget(central);
    auto *rootLayout = new QVBoxLayout(central);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    tabs_ = new QTabWidget(central);
    tabs_->setMovable(false);
    tabs_->setDocumentMode(true);
    tabs_->addTab(createDashboardTab(), "Dashboard");
    tabs_->addTab(createChartTab(), "Chart");
    tabs_->addTab(createPositionsTab(), "Positions");
    backtestTab_ = createBacktestTab();
    tabs_->addTab(backtestTab_, "Backtest");
    tabs_->addTab(createCodeTab(), "Code Languages");
    tabs_->setCurrentWidget(backtestTab_);

    rootLayout->addWidget(tabs_);

    populateDefaults();
    wireSignals();

    // Ensure the initial theme applies after all tabs/widgets exist.
    if (dashboardThemeCombo_) {
        applyDashboardTheme(dashboardThemeCombo_->currentText());
    }
}

QWidget *BacktestWindow::createPlaceholderTab(const QString &title, const QString &body) {
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(12);

    auto *heading = new QLabel(title, page);
    heading->setStyleSheet("font-size: 18px; font-weight: 600;");
    layout->addWidget(heading);

    auto *desc = new QLabel(body, page);
    desc->setWordWrap(true);
    layout->addWidget(desc);

    layout->addStretch();
    return page;
}

void BacktestWindow::showIndicatorDialog(const QString &indicatorName) {
    const bool isLight = dashboardThemeCombo_
        && dashboardThemeCombo_->currentText().compare("Light", Qt::CaseInsensitive) == 0;
    const QString bg = isLight ? "#ffffff" : "#0f1624";
    const QString fg = isLight ? "#0f172a" : "#e5e7eb";
    const QString fieldBg = isLight ? "#ffffff" : "#0d1117";
    const QString fieldFg = fg;
    const QString border = isLight ? "#cbd5e1" : "#1f2937";
    const QString btnBg = isLight ? "#e5e7eb" : "#111827";
    const QString btnFg = fg;
    const QString btnHover = isLight ? "#dbeafe" : "#1f2937";

    struct FieldSpec {
        QString key;
        QString label;
        enum Kind { IntField, DoubleField, ComboField } kind;
        double min = -999999;
        double max = 999999;
        double step = 1.0;
        QVariant defaultValue;
        QStringList options;
    };

    auto indicatorKey = indicatorName.toLower();
    auto normalize = [](QString s) {
        s.replace(" ", "").replace("(", "").replace(")", "").replace("%", "").replace("-", "").replace("_", "");
        return s;
    };
    const auto norm = normalize(indicatorKey);
    QString key = norm.contains("stochrsi")          ? "stoch_rsi"
                 : norm.contains("stochastic")        ? "stochastic"
                 : norm.contains("movingaverage")     ? "ma"
                 : norm.contains("donchian")          ? "donchian"
                 : norm.contains("psar")              ? "psar"
                 : norm.contains("bollinger")         ? "bb"
                 : norm.contains("relative") || norm.contains("rsi") ? "rsi"
                 : norm.contains("volume")            ? "volume"
                 : norm.contains("willr") || norm.contains("williams") ? "willr"
                 : norm.contains("macd")              ? "macd"
                 : norm.contains("ultimate")          ? "uo"
                 : norm.contains("adx")               ? "adx"
                 : norm.contains("dmi")               ? "dmi"
                 : norm.contains("supertrend")        ? "supertrend"
                 : norm.contains("ema")               ? "ema"
                 : "generic";

    QVector<FieldSpec> fields;
    auto addBuySell = [&fields]() {
        fields.push_back({"buy_value", "buy_value", FieldSpec::DoubleField, -999999, 999999, 0.1, QVariant()});
        fields.push_back({"sell_value", "sell_value", FieldSpec::DoubleField, -999999, 999999, 0.1, QVariant()});
    };

    if (key == "ma") {
        fields = {
            {"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 20},
            {"type", "type", FieldSpec::ComboField, 0, 0, 0, "SMA", {"SMA", "EMA", "WMA", "VWMA"}}
        };
        addBuySell();
    } else if (key == "donchian") {
        fields = {{"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 20}};
        addBuySell();
    } else if (key == "psar") {
        fields = {
            {"af", "af", FieldSpec::DoubleField, 0.0, 10.0, 0.01, 0.02},
            {"max_af", "max_af", FieldSpec::DoubleField, 0.0, 10.0, 0.01, 0.2}
        };
        addBuySell();
    } else if (key == "bb") {
        fields = {
            {"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 20},
            {"std", "std", FieldSpec::DoubleField, 0.1, 50.0, 0.1, 2.0}
        };
        addBuySell();
    } else if (key == "rsi") {
        fields = {{"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 14}};
        addBuySell();
    } else if (key == "volume") {
        addBuySell();
    } else if (key == "stoch_rsi") {
        fields = {
            {"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 14},
            {"smooth_k", "smooth_k", FieldSpec::IntField, 1, 10000, 1.0, 3},
            {"smooth_d", "smooth_d", FieldSpec::IntField, 1, 10000, 1.0, 3}
        };
        addBuySell();
    } else if (key == "stochastic") {
        fields = {
            {"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 14},
            {"smooth_k", "smooth_k", FieldSpec::IntField, 1, 10000, 1.0, 3},
            {"smooth_d", "smooth_d", FieldSpec::IntField, 1, 10000, 1.0, 3}
        };
        addBuySell();
    } else if (key == "willr") {
        fields = {{"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 14}};
        addBuySell();
    } else if (key == "macd") {
        fields = {
            {"fast", "fast", FieldSpec::IntField, 1, 10000, 1.0, 12},
            {"slow", "slow", FieldSpec::IntField, 1, 10000, 1.0, 26},
            {"signal", "signal", FieldSpec::IntField, 1, 10000, 1.0, 9}
        };
        addBuySell();
    } else if (key == "uo") {
        fields = {
            {"short", "short", FieldSpec::IntField, 1, 10000, 1.0, 7},
            {"medium", "medium", FieldSpec::IntField, 1, 10000, 1.0, 14},
            {"long", "long", FieldSpec::IntField, 1, 10000, 1.0, 28}
        };
        addBuySell();
    } else if (key == "adx" || key == "dmi") {
        fields = {{"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 14}};
        addBuySell();
    } else if (key == "supertrend") {
        fields = {
            {"atr_period", "atr_period", FieldSpec::IntField, 1, 10000, 1.0, 10},
            {"multiplier", "multiplier", FieldSpec::DoubleField, 0.1, 50.0, 0.1, 3.0}
        };
        addBuySell();
    } else { // ema / ema cross / generic
        fields = {{"length", "length", FieldSpec::IntField, 1, 10000, 1.0, 20}};
        addBuySell();
    }

    auto *dialog = new QDialog(this);
    dialog->setWindowTitle(tr("Params: %1").arg(indicatorName));
    dialog->setModal(true);
    dialog->setAttribute(Qt::WA_DeleteOnClose);

    auto *form = new QFormLayout();
    form->setLabelAlignment(Qt::AlignRight | Qt::AlignVCenter);
    form->setFormAlignment(Qt::AlignTop | Qt::AlignLeft);
    form->setHorizontalSpacing(10);
    form->setVerticalSpacing(10);
    form->setContentsMargins(16, 16, 16, 8);

    for (const auto &spec : fields) {
        QWidget *fieldWidget = nullptr;
        switch (spec.kind) {
            case FieldSpec::IntField: {
                auto *spin = new QSpinBox(dialog);
                spin->setRange(static_cast<int>(spec.min), static_cast<int>(spec.max));
                spin->setSingleStep(static_cast<int>(spec.step));
                spin->setValue(spec.defaultValue.isValid() ? spec.defaultValue.toInt() : 0);
                spin->setMinimumWidth(160);
                fieldWidget = spin;
                break;
            }
            case FieldSpec::DoubleField: {
                auto *dspin = new QDoubleSpinBox(dialog);
                dspin->setRange(spec.min, spec.max);
                dspin->setDecimals(6);
                dspin->setSingleStep(spec.step);
                dspin->setValue(spec.defaultValue.isValid() ? spec.defaultValue.toDouble() : 0.0);
                dspin->setMinimumWidth(160);
                dspin->setSpecialValueText(tr("None"));
                fieldWidget = dspin;
                break;
            }
            case FieldSpec::ComboField: {
                auto *combo = new QComboBox(dialog);
                combo->addItems(spec.options);
                if (spec.defaultValue.isValid()) {
                    int idx = combo->findText(spec.defaultValue.toString(), Qt::MatchFixedString);
                    if (idx >= 0) combo->setCurrentIndex(idx);
                }
                combo->setMinimumWidth(160);
                fieldWidget = combo;
                break;
            }
        }

        if (!fieldWidget) {
            fieldWidget = new QLineEdit(dialog);
            static_cast<QLineEdit *>(fieldWidget)->setPlaceholderText(tr("None"));
        }

        // If this is a buy/sell field, prefer plain line edits to allow None text.
        if (spec.key == "buy_value" || spec.key == "sell_value") {
            auto *edit = new QLineEdit(dialog);
            edit->setPlaceholderText(tr("None"));
            edit->setMinimumWidth(160);
            fieldWidget = edit;
        }

        form->addRow(spec.label, fieldWidget);
    }

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, dialog);
    connect(buttons, &QDialogButtonBox::accepted, dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);

    auto *layout = new QVBoxLayout(dialog);
    layout->addLayout(form);
    layout->addWidget(buttons, 0, Qt::AlignRight);

    dialog->setStyleSheet(QStringLiteral(
        "QDialog { background-color: %1; color: %2; }"
        "QLabel { color: %2; font-weight: 500; }"
        "QSpinBox, QComboBox, QLineEdit { background: %3; color: %4; border: 1px solid %5; border-radius: 4px; padding: 4px 6px; }"
        "QComboBox QAbstractItemView { background: %3; color: %4; selection-background-color: %5; }"
        "QDialogButtonBox QPushButton { background: %6; color: %7; border: 1px solid %5; border-radius: 4px; padding: 4px 12px; min-width: 68px; }"
        "QDialogButtonBox QPushButton:hover { background: %8; }"
    ).arg(bg, fg, fieldBg, fieldFg, border, btnBg, btnFg, btnHover));

    dialog->resize(360, dialog->sizeHint().height());
    dialog->exec();
}

void BacktestWindow::refreshDashboardBalance() {
    if (!dashboardRefreshBtn_) {
        return;
    }
    dashboardRefreshBtn_->setEnabled(false);
    dashboardRefreshBtn_->setText("Refreshing...");
    auto resetButton = [this]() {
        if (dashboardRefreshBtn_) {
            dashboardRefreshBtn_->setEnabled(true);
            dashboardRefreshBtn_->setText("Refresh Balance");
        }
    };

    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    if (apiKey.isEmpty() || apiSecret.isEmpty()) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText("API credentials missing");
        }
        resetButton();
        return;
    }

    const QString selectedExchange = selectedDashboardExchange(dashboardExchangeCombo_);
    if (!exchangeUsesBinanceApi(selectedExchange)) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("%1 balance API coming soon").arg(selectedExchange));
            dashboardBalanceLabel_->setStyleSheet("color: #f59e0b; font-weight: 700;");
        }
        resetButton();
        return;
    }

    const QString accountType = dashboardAccountTypeCombo_ ? dashboardAccountTypeCombo_->currentText() : "Futures";
    const QString mode = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : "Live";

    if (dashboardBalanceLabel_) {
        dashboardBalanceLabel_->setText("Refreshing...");
    }

    const QString accountNorm = accountType.trimmed().toLower();
    const QString modeNorm = mode.trimmed().toLower();
    const bool isFutures = accountNorm.startsWith("fut");
    const bool isTestnet = modeNorm.startsWith("paper") || modeNorm.startsWith("test");

    const auto result = BinanceRestClient::fetchUsdtBalance(
        apiKey,
        apiSecret,
        isFutures,
        isTestnet,
        10000);
    if (!result.ok) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("Error: %1").arg(result.error));
            dashboardBalanceLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
        }
        resetButton();
        return;
    }

    const QString balStr = QString::number(result.usdtBalance, 'f', 4);
    if (dashboardBalanceLabel_) {
        dashboardBalanceLabel_->setText(balStr.isEmpty() ? "0" : balStr);
        dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
    }
    resetButton();
}

void BacktestWindow::refreshDashboardSymbols() {
    if (!dashboardRefreshSymbolsBtn_) {
        return;
    }
    dashboardRefreshSymbolsBtn_->setEnabled(false);
    dashboardRefreshSymbolsBtn_->setText("Refreshing...");
    auto resetButton = [this]() {
        if (dashboardRefreshSymbolsBtn_) {
            dashboardRefreshSymbolsBtn_->setEnabled(true);
            dashboardRefreshSymbolsBtn_->setText("Refresh Symbols");
        }
    };

    if (!dashboardSymbolList_) {
        resetButton();
        return;
    }

    QSet<QString> previousSelections;
    if (dashboardSymbolList_) {
        for (auto *item : dashboardSymbolList_->selectedItems()) {
            previousSelections.insert(item->text());
        }
    }
    dashboardSymbolList_->clear();

    auto applySymbols = [this, &previousSelections](const QStringList &symbols) {
        if (!dashboardSymbolList_) {
            return;
        }
        dashboardSymbolList_->clear();
        dashboardSymbolList_->addItems(symbols);

        bool anySelected = false;
        for (int i = 0; i < dashboardSymbolList_->count(); ++i) {
            auto *item = dashboardSymbolList_->item(i);
            if (previousSelections.contains(item->text())) {
                item->setSelected(true);
                anySelected = true;
            }
        }
        if (!anySelected && dashboardSymbolList_->count() > 0) {
            dashboardSymbolList_->item(0)->setSelected(true);
        }
    };

    const QString accountType = dashboardAccountTypeCombo_ ? dashboardAccountTypeCombo_->currentText() : "Futures";
    const QString mode = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : "Live";
    const QString accountNorm = accountType.trimmed().toLower();
    const QString modeNorm = mode.trimmed().toLower();
    const bool isFutures = accountNorm.startsWith("fut");
    const bool isTestnet = modeNorm.startsWith("paper") || modeNorm.startsWith("test");
    const QString selectedExchange = selectedDashboardExchange(dashboardExchangeCombo_);

    if (!exchangeUsesBinanceApi(selectedExchange)) {
        const QStringList fallbackSymbols = placeholderSymbolsForExchange(selectedExchange, isFutures);
        applySymbols(fallbackSymbols);
        updateStatusMessage(
            QString("%1 API symbol sync is coming soon. Showing placeholder symbols.").arg(selectedExchange));
        resetButton();
        return;
    }

    const auto result = BinanceRestClient::fetchUsdtSymbols(isFutures, isTestnet, 10000);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Refresh symbols failed"), result.error);
        resetButton();
        return;
    }

    applySymbols(result.symbols);

    resetButton();
}
QWidget *BacktestWindow::createDashboardTab() {
    auto *page = new QWidget(this);
    page->setObjectName("dashboardPage");
    dashboardPage_ = page;
    dashboardApiKey_ = nullptr;
    dashboardApiSecret_ = nullptr;
    dashboardBalanceLabel_ = nullptr;
    dashboardRefreshBtn_ = nullptr;
    dashboardAccountTypeCombo_ = nullptr;
    dashboardModeCombo_ = nullptr;
    dashboardExchangeCombo_ = nullptr;
    dashboardIndicatorSourceCombo_ = nullptr;
    dashboardSymbolList_ = nullptr;
    dashboardIntervalList_ = nullptr;
    dashboardRefreshSymbolsBtn_ = nullptr;

    auto *pageLayout = new QVBoxLayout(page);
    pageLayout->setContentsMargins(0, 0, 0, 0);
    pageLayout->setSpacing(0);

    auto *scrollArea = new QScrollArea(page);
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scrollArea->setObjectName("dashboardScrollArea");
    pageLayout->addWidget(scrollArea);

    auto *content = new QWidget(scrollArea);
    content->setObjectName("dashboardScrollWidget");
    scrollArea->setWidget(content);

    auto *root = new QVBoxLayout(content);
    root->setContentsMargins(10, 10, 10, 10);
    root->setSpacing(12);

    const QStringList dashboardIndicatorSources = {
        "Binance spot",
        "Binance futures",
        "TradingView",
        "Bybit",
        "Coinbase",
        "OKX",
        "Gate",
        "Bitget",
        "Mexc",
        "Kucoin",
        "HTX",
        "Kraken",
    };

    auto *accountBox = new QGroupBox("Account & Status", page);
    auto *accountGrid = new QGridLayout(accountBox);
    accountGrid->setHorizontalSpacing(10);
    accountGrid->setVerticalSpacing(8);
    accountGrid->setContentsMargins(12, 12, 12, 12);
    root->addWidget(accountBox);

    auto addPair = [accountGrid, accountBox](int row, int &col, const QString &label, QWidget *widget, int span = 1) {
        accountGrid->addWidget(new QLabel(label, accountBox), row, col++);
        accountGrid->addWidget(widget, row, col, 1, span);
        col += span;
    };

    int col = 0;
    dashboardApiKey_ = new QLineEdit(accountBox);
    dashboardApiKey_->setPlaceholderText("API Key");
    dashboardApiKey_->setMinimumWidth(140);
    addPair(0, col, "API Key:", dashboardApiKey_, 2);

    dashboardModeCombo_ = new QComboBox(accountBox);
    dashboardModeCombo_->addItems({"Live", "Paper (Testnet)"});
    addPair(0, col, "Mode:", dashboardModeCombo_);

    dashboardThemeCombo_ = new QComboBox(accountBox);
    dashboardThemeCombo_->addItems({"Dark", "Light"});
    addPair(0, col, "Theme:", dashboardThemeCombo_);
    connect(dashboardThemeCombo_, &QComboBox::currentTextChanged, this, &BacktestWindow::applyDashboardTheme);

    auto *pnlActive = new QLabel("--", accountBox);
    pnlActive->setStyleSheet("color: #a5b4fc;");
    addPair(0, col, "Total PNL Active Positions:", pnlActive);

    auto *pnlClosed = new QLabel("--", accountBox);
    pnlClosed->setStyleSheet("color: #a5b4fc;");
    addPair(0, col, "Total PNL Closed Positions:", pnlClosed);

    auto *botStatus = new QLabel("OFF", accountBox);
    botStatus->setStyleSheet("color: #ef4444; font-weight: 700;");
    addPair(0, col, "Bot Status:", botStatus);

    accountGrid->addWidget(new QLabel("Bot Active Time:", accountBox), 0, col++);
    auto *botTime = new QLabel("--", accountBox);
    botTime->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    accountGrid->addWidget(botTime, 0, col, 1, 2);
    accountGrid->setColumnStretch(col, 1);

    col = 0;
    dashboardApiSecret_ = new QLineEdit(accountBox);
    dashboardApiSecret_->setEchoMode(QLineEdit::Password);
    dashboardApiSecret_->setPlaceholderText("API Secret Key");
    dashboardApiSecret_->setMinimumWidth(140);
    addPair(1, col, "API Secret Key:", dashboardApiSecret_, 2);

    dashboardAccountTypeCombo_ = new QComboBox(accountBox);
    dashboardAccountTypeCombo_->addItems({"Futures", "Spot"});
    addPair(1, col, "Account Type:", dashboardAccountTypeCombo_);

    auto *accountModeCombo = new QComboBox(accountBox);
    accountModeCombo->addItems({"Classic Trading", "Multi-Asset Mode"});
    addPair(1, col, "Account Mode:", accountModeCombo);

    auto *connectorCombo = new QComboBox(accountBox);
    connectorCombo->addItems({
        "Binance SDK Derivatives Trading USDⓈ Futures (Official Recommended)",
        "Binance Gateway",
        "Custom Connector"
    });
    connectorCombo->setMinimumWidth(180);
    addPair(1, col, "Connector:", connectorCombo, 3);

    col = 0;
    dashboardBalanceLabel_ = new QLabel("N/A", accountBox);
    dashboardBalanceLabel_->setStyleSheet("color: #fbbf24; font-weight: 700;");
    addPair(2, col, "Total USDT balance:", dashboardBalanceLabel_);

    dashboardRefreshBtn_ = new QPushButton("Refresh Balance", accountBox);
    connect(dashboardRefreshBtn_, &QPushButton::clicked, this, &BacktestWindow::refreshDashboardBalance);
    accountGrid->addWidget(dashboardRefreshBtn_, 2, col++);

    auto *leverageSpin = new QSpinBox(accountBox);
    leverageSpin->setRange(1, 125);
    leverageSpin->setValue(20);
    addPair(2, col, "Leverage (Futures):", leverageSpin);

    auto *marginModeCombo = new QComboBox(accountBox);
    marginModeCombo->addItems({"Isolated", "Cross"});
    addPair(2, col, "Margin Mode (Futures):", marginModeCombo);

    auto *positionModeCombo = new QComboBox(accountBox);
    positionModeCombo->addItems({"Hedge", "One-way"});
    addPair(2, col, "Position Mode:", positionModeCombo);

    auto *assetsModeCombo = new QComboBox(accountBox);
    assetsModeCombo->addItems({"Single-Asset Mode", "Multi-Asset Mode"});
    addPair(2, col, "Assets Mode:", assetsModeCombo);

    col = 0;
    auto *indicatorSourceCombo = new QComboBox(accountBox);
    indicatorSourceCombo->addItems(dashboardIndicatorSources);
    indicatorSourceCombo->setCurrentText("Binance futures");
    indicatorSourceCombo->setMinimumWidth(140);
    dashboardIndicatorSourceCombo_ = indicatorSourceCombo;
    addPair(3, col, "Indicator Source:", indicatorSourceCombo, 2);

    auto *orderTypeCombo = new QComboBox(accountBox);
    orderTypeCombo->addItems({"GTC", "IOC", "FOK"});
    addPair(3, col, "Order Type:", orderTypeCombo);

    auto *expiryCombo = new QComboBox(accountBox);
    expiryCombo->addItems({"30 min (GTD)", "1h (GTD)", "4h (GTD)", "GTC"});
    addPair(3, col, "Expiry / TIF:", expiryCombo);

    for (int stretchCol : {1, 2, 4, 6, 8, 10, 12}) {
        accountGrid->setColumnStretch(stretchCol, 1);
    }
    accountGrid->setColumnStretch(13, 2);

    auto *exchangeBox = new QGroupBox("Exchange", page);
    auto *exchangeLayout = new QVBoxLayout(exchangeBox);
    exchangeLayout->setSpacing(6);
    exchangeLayout->setContentsMargins(12, 10, 12, 10);
    exchangeLayout->addWidget(new QLabel("Select exchange", exchangeBox));
    auto *exchangeCombo = new QComboBox(exchangeBox);
    dashboardExchangeCombo_ = exchangeCombo;
    exchangeLayout->addWidget(exchangeCombo);
    struct ExchangeOption {
        QString title;
        QString badge;
        bool disabled;
    };
    const QVector<ExchangeOption> exchangeOptions = {
        {"Binance", "", false},
        {"Bybit", "coming soon", true},
        {"OKX", "coming soon", true},
        {"Gate", "coming soon", true},
        {"Bitget", "coming soon", true},
        {"MEXC", "coming soon", true},
        {"KuCoin", "coming soon", true},
    };
    for (const auto &opt : exchangeOptions) {
        QString itemText = opt.title;
        if (!opt.badge.isEmpty()) {
            itemText += QString(" (%1)").arg(opt.badge);
        }
        exchangeCombo->addItem(itemText, opt.title);
        const int idx = exchangeCombo->count() - 1;
        if (opt.disabled) {
            if (auto *model = qobject_cast<QStandardItemModel *>(exchangeCombo->model())) {
                if (auto *item = model->item(idx)) {
                    item->setFlags(item->flags() & ~Qt::ItemFlag::ItemIsEnabled);
                    item->setForeground(QColor("#6b7280"));
                }
            }
        }
    }
    root->addWidget(exchangeBox);

    auto *marketsBox = new QGroupBox("Markets / Intervals", page);
    auto *marketsLayout = new QVBoxLayout(marketsBox);
    marketsLayout->setSpacing(8);
    marketsLayout->setContentsMargins(12, 12, 12, 12);

    auto *listsGrid = new QGridLayout();
    listsGrid->setHorizontalSpacing(12);
    listsGrid->setVerticalSpacing(8);
    listsGrid->addWidget(new QLabel("Symbols (select 1 or more):", marketsBox), 0, 0);
    listsGrid->addWidget(new QLabel("Intervals (select 1 or more):", marketsBox), 0, 1);

    auto *dashboardSymbolList = new QListWidget(marketsBox);
    dashboardSymbolList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardSymbolList->addItems({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"});
    dashboardSymbolList->setMinimumHeight(220);
    dashboardSymbolList->setMaximumHeight(260);
    dashboardSymbolList_ = dashboardSymbolList;
    listsGrid->addWidget(dashboardSymbolList, 1, 0, 2, 1);

    auto *dashboardIntervalList = new QListWidget(marketsBox);
    dashboardIntervalList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardIntervalList->addItems({
        "1m", "3m", "5m", "10m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h"
    });
    dashboardIntervalList->setMinimumHeight(220);
    dashboardIntervalList->setMaximumHeight(260);
    dashboardIntervalList_ = dashboardIntervalList;
    listsGrid->addWidget(dashboardIntervalList, 1, 1, 2, 1);

    dashboardRefreshSymbolsBtn_ = new QPushButton("Refresh Symbols", marketsBox);
    connect(dashboardRefreshSymbolsBtn_, &QPushButton::clicked, this, &BacktestWindow::refreshDashboardSymbols);
    listsGrid->addWidget(dashboardRefreshSymbolsBtn_, 3, 0, 1, 1);

    auto *customIntervalEdit = new QLineEdit(marketsBox);
    customIntervalEdit->setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated");
    listsGrid->addWidget(customIntervalEdit, 3, 1, 1, 1);
    auto *customButton = new QPushButton("Add Custom Interval(s)", marketsBox);
    listsGrid->addWidget(customButton, 3, 2, 1, 1);
    marketsLayout->addLayout(listsGrid);

    auto *marketsHint = new QLabel("Pre-load your Binance futures symbols and multi-timeframe intervals.", marketsBox);
    marketsHint->setStyleSheet("color: #94a3b8; font-size: 12px;");
    marketsLayout->addWidget(marketsHint);
    root->addWidget(marketsBox);

    auto setComboTextIfPresent = [](QComboBox *combo, const QString &text) -> bool {
        if (!combo || text.trimmed().isEmpty()) {
            return false;
        }
        int idx = combo->findText(text, Qt::MatchFixedString);
        if (idx < 0) {
            idx = combo->findText(text, Qt::MatchContains);
        }
        if (idx < 0) {
            return false;
        }
        combo->setCurrentIndex(idx);
        return true;
    };

    auto syncIndicatorSourceCombos = [this, setComboTextIfPresent](const QString &text, QComboBox *origin) {
        if (dashboardIndicatorSourceCombo_ && dashboardIndicatorSourceCombo_ != origin) {
            QSignalBlocker blocker(dashboardIndicatorSourceCombo_);
            setComboTextIfPresent(dashboardIndicatorSourceCombo_, text);
        }
    };

    auto syncExchangeFromIndicatorSource = [this](const QString &sourceText) {
        if (!dashboardExchangeCombo_) {
            return;
        }
        const QString mappedExchange = exchangeFromIndicatorSource(sourceText);
        if (mappedExchange.isEmpty()) {
            return;
        }
        int idx = dashboardExchangeCombo_->findData(mappedExchange);
        if (idx < 0) {
            idx = dashboardExchangeCombo_->findText(mappedExchange, Qt::MatchFixedString);
        }
        if (idx < 0 || idx == dashboardExchangeCombo_->currentIndex()) {
            return;
        }
        {
            QSignalBlocker blocker(dashboardExchangeCombo_);
            dashboardExchangeCombo_->setCurrentIndex(idx);
        }
        refreshDashboardSymbols();
    };

    auto syncIndicatorSourceFromExchange = [this, setComboTextIfPresent](const QString &exchangeText) {
        const QString preferred = preferredIndicatorSourceForExchange(
            exchangeText,
            dashboardIndicatorSourceCombo_ ? dashboardIndicatorSourceCombo_->currentText() : QString());
        if (preferred.trimmed().isEmpty()) {
            return;
        }
        if (dashboardIndicatorSourceCombo_) {
            QSignalBlocker blocker(dashboardIndicatorSourceCombo_);
            setComboTextIfPresent(dashboardIndicatorSourceCombo_, preferred);
        }
    };

    if (dashboardExchangeCombo_) {
        int binanceIdx = dashboardExchangeCombo_->findData("Binance");
        if (binanceIdx < 0) {
            binanceIdx = dashboardExchangeCombo_->findText("Binance", Qt::MatchFixedString);
        }
        if (binanceIdx >= 0) {
            dashboardExchangeCombo_->setCurrentIndex(binanceIdx);
        }
        connect(dashboardExchangeCombo_, &QComboBox::currentTextChanged, this, [this, syncIndicatorSourceFromExchange](const QString &text) {
            syncIndicatorSourceFromExchange(text);
            refreshDashboardSymbols();
        });
    }

    if (dashboardIndicatorSourceCombo_) {
        connect(dashboardIndicatorSourceCombo_, &QComboBox::currentTextChanged, this, [syncIndicatorSourceCombos, syncExchangeFromIndicatorSource, this](const QString &text) {
            syncIndicatorSourceCombos(text, dashboardIndicatorSourceCombo_);
            syncExchangeFromIndicatorSource(text);
        });
    }
    syncIndicatorSourceCombos(
        dashboardIndicatorSourceCombo_ ? dashboardIndicatorSourceCombo_->currentText() : QStringLiteral("Binance futures"),
        dashboardIndicatorSourceCombo_);

    connect(customButton, &QPushButton::clicked, this, [customIntervalEdit, dashboardIntervalList]() {
        const auto parts = customIntervalEdit->text().split(',', Qt::SkipEmptyParts);
        for (QString interval : parts) {
            interval = interval.trimmed();
            if (interval.isEmpty()) {
                continue;
            }
            bool exists = false;
            for (int i = 0; i < dashboardIntervalList->count(); ++i) {
                if (dashboardIntervalList->item(i)->text().compare(interval, Qt::CaseInsensitive) == 0) {
                    exists = true;
                    break;
                }
            }
            if (!exists) {
                dashboardIntervalList->addItem(interval);
            }
        }
        customIntervalEdit->clear();
    });

    auto *strategyBox = new QGroupBox("Strategy Controls", page);
    auto *strategyGrid = new QGridLayout(strategyBox);
    strategyGrid->setHorizontalSpacing(12);
    strategyGrid->setVerticalSpacing(8);
    strategyGrid->setContentsMargins(12, 12, 12, 12);
    root->addWidget(strategyBox);

    int row = 0;
    strategyGrid->addWidget(new QLabel("Side:", strategyBox), row, 0);
    auto *sideCombo = new QComboBox(strategyBox);
    sideCombo->addItems({"Both (Long/Short)", "Long Only", "Short Only"});
    strategyGrid->addWidget(sideCombo, row, 1);

    strategyGrid->addWidget(new QLabel("Position % of Balance:", strategyBox), row, 2);
    auto *positionPct = new QDoubleSpinBox(strategyBox);
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setValue(2.0);
    positionPct->setSuffix(" %");
    strategyGrid->addWidget(positionPct, row, 3);

    strategyGrid->addWidget(new QLabel("Loop Interval Override:", strategyBox), row, 4);
    auto *loopOverride = new QComboBox(strategyBox);
    loopOverride->addItems({"Off", "30 seconds", "1 minute", "5 minutes"});
    loopOverride->setCurrentText("1 minute");
    strategyGrid->addWidget(loopOverride, row, 5);

    ++row;
    auto *enableLeadTrader = new QCheckBox("Enable Lead Trader", strategyBox);
    strategyGrid->addWidget(enableLeadTrader, row, 0, 1, 2);
    auto *leadTraderCombo = new QComboBox(strategyBox);
    leadTraderCombo->addItems({"Futures Public Lead Trader", "Signals Feed", "Manual Lead"});
    leadTraderCombo->setEnabled(false);
    connect(enableLeadTrader, &QCheckBox::toggled, leadTraderCombo, &QWidget::setEnabled);
    strategyGrid->addWidget(leadTraderCombo, row, 2, 1, 2);

    ++row;
    auto *oneWayCheck = new QCheckBox("Add-only in current net direction (one-way)", strategyBox);
    strategyGrid->addWidget(oneWayCheck, row, 0, 1, 3);
    auto *hedgeStackCheck = new QCheckBox("Allow simultaneous long / short positions (hedge stacking)", strategyBox);
    strategyGrid->addWidget(hedgeStackCheck, row, 3, 1, 3);

    ++row;
    auto *stopWithoutCloseCheck = new QCheckBox("Stop Bot Without Closing Active Positions", strategyBox);
    stopWithoutCloseCheck->setToolTip(
        "When checked, the Stop button will halt strategy threads but keep existing positions open."
    );
    strategyGrid->addWidget(stopWithoutCloseCheck, row, 0, 1, 3);
    auto *windowCloseCheck = new QCheckBox("Market Close All Active Positions On Window Close (WIP)", strategyBox);
    windowCloseCheck->setEnabled(false);
    strategyGrid->addWidget(windowCloseCheck, row, 3, 1, 3);

    ++row;
    strategyGrid->addWidget(new QLabel("Stop Loss:", strategyBox), row, 0);
    auto *stopLossEnable = new QCheckBox("Enable", strategyBox);
    strategyGrid->addWidget(stopLossEnable, row, 1);

    auto *stopScopeCombo = new QComboBox(strategyBox);
    stopScopeCombo->addItems({"Per Trade Stop Loss", "Global Portfolio Stop", "Trailing Stop"});
    strategyGrid->addWidget(stopScopeCombo, row, 2, 1, 2);

    auto *stopUsdtSpin = new QDoubleSpinBox(strategyBox);
    stopUsdtSpin->setRange(0.0, 1'000'000.0);
    stopUsdtSpin->setDecimals(2);
    stopUsdtSpin->setSuffix(" USDT");
    stopUsdtSpin->setEnabled(false);
    strategyGrid->addWidget(stopUsdtSpin, row, 4);

    auto *stopPctSpin = new QDoubleSpinBox(strategyBox);
    stopPctSpin->setRange(0.0, 100.0);
    stopPctSpin->setDecimals(2);
    stopPctSpin->setSuffix(" %");
    stopPctSpin->setEnabled(false);
    strategyGrid->addWidget(stopPctSpin, row, 5);

    connect(stopLossEnable, &QCheckBox::toggled, stopScopeCombo, &QWidget::setEnabled);
    connect(stopLossEnable, &QCheckBox::toggled, stopUsdtSpin, &QWidget::setEnabled);
    connect(stopLossEnable, &QCheckBox::toggled, stopPctSpin, &QWidget::setEnabled);

    ++row;
    strategyGrid->addWidget(new QLabel("Template:", strategyBox), row, 0);
    auto *templateCombo = new QComboBox(strategyBox);
    templateCombo->addItems({"No Template", "Futures Public Lead Trader", "Volume Top 50", "RSI Reversal"});
    strategyGrid->addWidget(templateCombo, row, 1, 1, 2);

    strategyGrid->setColumnStretch(1, 1);
    strategyGrid->setColumnStretch(3, 1);
    strategyGrid->setColumnStretch(5, 1);

    auto *indicatorsBox = new QGroupBox("Indicators", page);
    auto *indGrid = new QGridLayout(indicatorsBox);
    indGrid->setHorizontalSpacing(14);
    indGrid->setVerticalSpacing(8);
    indGrid->setContentsMargins(12, 12, 12, 12);

    auto addIndicatorRow = [indicatorsBox, indGrid, this](int rowIndex, const QString &name) {
        auto *cb = new QCheckBox(name, indicatorsBox);
        auto *btn = new QPushButton("Buy-Sell Values", indicatorsBox);
        btn->setMinimumWidth(150);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        QObject::connect(cb, &QCheckBox::toggled, btn, &QWidget::setEnabled);
        QObject::connect(btn, &QPushButton::clicked, this, [this, name]() { showIndicatorDialog(name); });
        indGrid->addWidget(cb, rowIndex, 0);
        indGrid->addWidget(btn, rowIndex, 1);
    };

    QStringList indicators = {
        "Moving Average (MA)", "Donchian Channels (DC)", "Parabolic SAR (PSAR)", "Bollinger Bands (BB)",
        "Relative Strength Index (RSI)", "Volume", "Stochastic RSI", "Williams %R", "MACD",
        "Ultimate Oscillator", "ADX", "DMI", "SuperTrend", "EMA Cross"
    };
    for (int i = 0; i < indicators.size(); ++i) {
        addIndicatorRow(i, indicators[i]);
    }
    indGrid->setColumnStretch(0, 1);
    indGrid->setColumnStretch(1, 1);
    root->addWidget(indicatorsBox);

    root->addStretch();

    applyDashboardTheme(dashboardThemeCombo_ ? dashboardThemeCombo_->currentText() : QString());
    return page;
}

void BacktestWindow::applyDashboardTheme(const QString &themeName) {
    if (!dashboardPage_) {
        return;
    }

    const bool isLight = themeName.compare("Light", Qt::CaseInsensitive) == 0;
    const QString darkCss = R"(
        #dashboardPage { background: #0b0f16; }
        #dashboardPage QLabel { color: #e5e7eb; }
        #dashboardPage QGroupBox { background: #0f1624; border: 1px solid #1f2937; border-radius: 8px; margin-top: 12px; }
        #dashboardPage QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #cbd5e1; }
        #dashboardPage QLineEdit, #dashboardPage QComboBox, #dashboardPage QDoubleSpinBox, #dashboardPage QSpinBox, #dashboardPage QDateEdit {
            background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 4px 6px;
        }
        #dashboardPage QListWidget { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; }
        #dashboardPage QPushButton { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 6px 10px; }
        #dashboardPage QPushButton:hover { background: #1f2937; }
    )";

    const QString lightCss = R"(
        #dashboardPage { background: #f5f7fb; }
        #dashboardPage QLabel { color: #0f172a; }
        #dashboardPage QGroupBox { background: #ffffff; border: 1px solid #d1d5db; border-radius: 8px; margin-top: 12px; }
        #dashboardPage QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #111827; }
        #dashboardPage QLineEdit, #dashboardPage QComboBox, #dashboardPage QDoubleSpinBox, #dashboardPage QSpinBox, #dashboardPage QDateEdit {
            background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 6px;
        }
        #dashboardPage QListWidget { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; }
        #dashboardPage QPushButton { background: #e5e7eb; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 10px; }
        #dashboardPage QPushButton:hover { background: #dbeafe; }
    )";

    const QString darkGlobal = R"(
        QMainWindow { background: #0b0f16; }
        QTabWidget::pane { border: 1px solid #1f2937; background: #0b0f16; }
        QTabBar::tab { background: #111827; color: #e5e7eb; padding: 6px 10px; }
        QTabBar::tab:selected { background: #1f2937; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage, QWidget#dashboardPage { background: #0b0f16; color: #e5e7eb; }
        QScrollArea#dashboardScrollArea { background: #0b0f16; border: none; }
        QWidget#dashboardScrollWidget { background: #0b0f16; }
        QScrollArea#backtestScrollArea { background: #0b0f16; border: none; }
        QWidget#backtestScrollWidget { background: #0b0f16; }
        QGroupBox { color: #e5e7eb; border-color: #1f2937; }
        QLabel { color: #e5e7eb; }
        QLabel:disabled, QCheckBox:disabled, QComboBox:disabled, QLineEdit:disabled { color: #9ca3af; }
        QGroupBox::title { color: #e5e7eb; }
        QCheckBox { color: #e5e7eb; spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #1f2937; background: #0d1117; }
        QCheckBox::indicator:hover { border-color: #2563eb; }
        QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
        QCheckBox::indicator:disabled { background: #111827; border-color: #1f2937; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 3px 6px; }
        QListWidget { background: #0d1117; color: #e5e7eb; border: 1px solid #1f2937; }
        QPushButton { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; border-radius: 4px; padding: 6px 10px; }
        QPushButton:hover { background: #1f2937; }
        QTableWidget { background: #0d1117; color: #e5e7eb; gridline-color: #1f2937; selection-background-color: #1f2937; selection-color: #e5e7eb; }
        QHeaderView::section { background: #111827; color: #e5e7eb; border: 1px solid #1f2937; }
    )";

    const QString lightGlobal = R"(
        QMainWindow { background: #f5f7fb; }
        QTabWidget::pane { border: 1px solid #d1d5db; background: #f5f7fb; }
        QTabBar::tab { background: #e5e7eb; color: #0f172a; padding: 6px 10px; }
        QTabBar::tab:selected { background: #ffffff; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage, QWidget#dashboardPage { background: #f5f7fb; color: #0f172a; }
        QScrollArea#dashboardScrollArea { background: #f5f7fb; border: none; }
        QWidget#dashboardScrollWidget { background: #f5f7fb; }
        QScrollArea#backtestScrollArea { background: #f5f7fb; border: none; }
        QWidget#backtestScrollWidget { background: #f5f7fb; }
        QGroupBox { color: #0f172a; border-color: #d1d5db; }
        QLabel { color: #0f172a; }
        QLabel:disabled, QCheckBox:disabled, QComboBox:disabled, QLineEdit:disabled { color: #6b7280; }
        QGroupBox::title { color: #0f172a; }
        QCheckBox { color: #0f172a; spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #cbd5e1; background: #ffffff; }
        QCheckBox::indicator:hover { border-color: #2563eb; }
        QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
        QCheckBox::indicator:disabled { background: #f1f5f9; border-color: #d1d5db; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; }
        QListWidget { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; }
        QPushButton { background: #e5e7eb; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 10px; }
        QPushButton:hover { background: #dbeafe; }
        QTableWidget { background: #ffffff; color: #0f172a; gridline-color: #d1d5db; selection-background-color: #dbeafe; selection-color: #0f172a; }
        QHeaderView::section { background: #e5e7eb; color: #0f172a; border: 1px solid #d1d5db; }
    )";

    // Apply to the whole window (covers Chart/Positions/Backtest/Code tabs)
    this->setStyleSheet(isLight ? lightGlobal : darkGlobal);

    // Apply dashboard-specific overrides
    dashboardPage_->setStyleSheet(isLight ? lightCss : darkCss);

    // Apply code tab readability (headings + content on matching background)
    if (codePage_) {
        const QString codeCss = isLight
                                    ? QStringLiteral(
                                          "QWidget#codePage { background: #f5f7fb; color: #0f172a; }"
                                          "QScrollArea#codeScrollArea { background: #f5f7fb; border: none; }"
                                          "QWidget#codeContent { background: #f5f7fb; }"
                                          "QLabel { color: #0f172a; }"
                                          "QTableWidget { background: #ffffff; color: #0f172a; gridline-color: #d1d5db; }"
                                          "QHeaderView::section { background: #e5e7eb; color: #0f172a; }")
                                    : QStringLiteral(
                                          "QWidget#codePage { background: #0b0f16; color: #e5e7eb; }"
                                          "QScrollArea#codeScrollArea { background: #0b1220; border: none; }"
                                          "QWidget#codeContent { background: #0b1220; }"
                                          "QLabel { color: #e5e7eb; }"
                                          "QTableWidget { background: #0d1117; color: #e5e7eb; gridline-color: #1f2937; }"
                                          "QHeaderView::section { background: #111827; color: #e5e7eb; }");
        codePage_->setStyleSheet(codeCss);
    }
}

QWidget *BacktestWindow::createChartTab() {
    auto *page = new QWidget(this);
    page->setObjectName("chartPage");
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(10);

    auto *heading = new QLabel("Chart", page);
    heading->setStyleSheet("font-size: 18px; font-weight: 600;");
    layout->addWidget(heading);

    auto *desc = new QLabel(
        "C++ chart tab mirrors Python chart modes: Original (Binance web) and TradingView.",
        page);
    desc->setWordWrap(true);
    layout->addWidget(desc);

    auto *controls = new QHBoxLayout();
    controls->setSpacing(8);
    controls->addWidget(new QLabel("Market:", page));

    auto *marketCombo = new QComboBox(page);
    marketCombo->addItem("Futures", "futures");
    marketCombo->addItem("Spot", "spot");
    chartMarketCombo_ = marketCombo;
    controls->addWidget(marketCombo);

    controls->addWidget(new QLabel("Symbol:", page));
    auto *symbolCombo = new QComboBox(page);
    symbolCombo->setEditable(false);
    symbolCombo->setMinimumContentsLength(10);
    symbolCombo->setSizeAdjustPolicy(QComboBox::SizeAdjustPolicy::AdjustToContents);
    chartSymbolCombo_ = symbolCombo;
    controls->addWidget(symbolCombo);

    controls->addWidget(new QLabel("Interval:", page));
    auto *intervalCombo = new QComboBox(page);
    intervalCombo->addItems({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"});
    intervalCombo->setCurrentText("1m");
    chartIntervalCombo_ = intervalCombo;
    controls->addWidget(intervalCombo);

    controls->addWidget(new QLabel("View:", page));
    auto *viewModeCombo = new QComboBox(page);
    viewModeCombo->addItem("Original", "original");
    viewModeCombo->addItem("TradingView", "tradingview");
    chartViewModeCombo_ = viewModeCombo;
    controls->addWidget(viewModeCombo);

    auto *autoFollowCheck = new QCheckBox("Auto Follow Dashboard", page);
    autoFollowCheck->setChecked(true);
    chartAutoFollowCheck_ = autoFollowCheck;
    controls->addWidget(autoFollowCheck);

    auto *refreshBtn = new QPushButton("Refresh", page);
    controls->addWidget(refreshBtn);

    auto *openBtn = new QPushButton("Open In Browser", page);
    controls->addWidget(openBtn);

    controls->addStretch();

    auto *chartStatusWidget = new QWidget(page);
    auto *chartStatusLayout = new QHBoxLayout(chartStatusWidget);
    chartStatusLayout->setContentsMargins(0, 0, 0, 0);
    chartStatusLayout->setSpacing(8);

    chartPnlActiveLabel_ = new QLabel("Total PNL Active Positions: --", chartStatusWidget);
    chartPnlClosedLabel_ = new QLabel("Total PNL Closed Positions: --", chartStatusWidget);
    chartBotStatusLabel_ = new QLabel("Bot Status: OFF", chartStatusWidget);
    chartBotStatusLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
    chartBotTimeLabel_ = new QLabel("Bot Active Time: --", chartStatusWidget);

    chartStatusLayout->addWidget(chartPnlActiveLabel_);
    chartStatusLayout->addWidget(chartPnlClosedLabel_);
    chartStatusLayout->addWidget(chartBotStatusLabel_);
    chartStatusLayout->addWidget(chartBotTimeLabel_);
    controls->addWidget(chartStatusWidget);

    layout->addLayout(controls);

    auto *status = new QLabel("Chart ready.", page);
    status->setWordWrap(true);
    layout->addWidget(status);

    auto *chartStack = new QStackedWidget(page);
    layout->addWidget(chartStack, 1);

    auto *originalPage = new QWidget(chartStack);
    auto *originalLayout = new QVBoxLayout(originalPage);
    originalLayout->setContentsMargins(0, 0, 0, 0);
#if HAS_QT_WEBENGINE
    auto *binanceView = new QWebEngineView(originalPage);
    binanceView->setContextMenuPolicy(Qt::NoContextMenu);
    binanceView->setMinimumHeight(460);
    originalLayout->addWidget(binanceView, 1);
#else
    auto *chartWidget = new NativeKlineChartWidget(originalPage);
    originalLayout->addWidget(chartWidget, 1);
#endif
    chartStack->addWidget(originalPage);

    auto *tradingPage = new QWidget(chartStack);
    auto *tradingLayout = new QVBoxLayout(tradingPage);
    tradingLayout->setContentsMargins(0, 0, 0, 0);
    tradingLayout->setSpacing(8);
#if HAS_QT_WEBENGINE
    auto *tradingView = new QWebEngineView(tradingPage);
    tradingView->setMinimumHeight(460);
    tradingView->setContextMenuPolicy(Qt::NoContextMenu);
    tradingLayout->addWidget(tradingView, 1);
#else
    auto *tvUnavailable = new QLabel(
        "Qt WebEngine is not available in this C++ build, so embedded TradingView is disabled. "
        "Use the Open TradingView button to view it in your browser.",
        tradingPage);
    tvUnavailable->setWordWrap(true);
    tvUnavailable->setStyleSheet("color: #f59e0b;");
    tradingLayout->addWidget(tvUnavailable);
    tradingLayout->addStretch(1);
#endif
    chartStack->addWidget(tradingPage);

#if !HAS_QT_WEBENGINE
    try {
        const int tvIdx = viewModeCombo->findData("tradingview");
        if (tvIdx >= 0) {
            if (auto *model = qobject_cast<QStandardItemModel *>(viewModeCombo->model())) {
                if (QStandardItem *item = model->item(tvIdx)) {
                    item->setEnabled(false);
                    item->setToolTip("Qt WebEngine not installed in this C++ toolchain.");
                }
            }
        }
        viewModeCombo->setCurrentIndex(viewModeCombo->findData("original"));
    } catch (...) {
    }
#else
    viewModeCombo->setCurrentIndex(viewModeCombo->findData("original"));
#endif

    auto currentRawSymbol = [symbolCombo]() {
        QString raw = symbolCombo->currentData().toString().trimmed().toUpper();
        if (raw.isEmpty()) {
            raw = normalizeChartSymbol(symbolCombo->currentText());
        }
        return raw;
    };

    std::function<void()> refreshCurrent;

    auto loadSymbols = [this, marketCombo, symbolCombo, status, currentRawSymbol]() {
        QString preferredRaw = currentRawSymbol();
        if (chartAutoFollowCheck_ && chartAutoFollowCheck_->isChecked() && dashboardSymbolList_) {
            const auto selected = dashboardSymbolList_->selectedItems();
            if (!selected.isEmpty()) {
                const QString dashRaw = normalizeChartSymbol(selected.first()->text());
                if (!dashRaw.isEmpty()) {
                    preferredRaw = dashRaw;
                }
            }
        }
        const bool futures = marketCombo->currentData().toString() == "futures";

        const auto result = BinanceRestClient::fetchUsdtSymbols(futures, false, 12000);
        QStringList symbols;
        if (result.ok && !result.symbols.isEmpty()) {
            symbols = result.symbols;
            status->setText(QString("Loaded %1 symbols.").arg(symbols.size()));
        } else {
            symbols = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"};
            status->setText(result.error.isEmpty()
                                ? "Using fallback symbol list."
                                : QString("Using fallback symbols: %1").arg(result.error));
        }

        QSignalBlocker blocker(symbolCombo);
        symbolCombo->clear();
        for (const QString &raw : symbols) {
            const QString display = futures ? QString("%1.P").arg(raw) : raw;
            symbolCombo->addItem(display, raw);
        }

        int idx = symbolCombo->findData(preferredRaw);
        if (idx < 0) {
            idx = symbolCombo->findData("BTCUSDT");
        }
        if (idx < 0 && symbolCombo->count() > 0) {
            idx = 0;
        }
        if (idx >= 0) {
            symbolCombo->setCurrentIndex(idx);
        }
    };

    std::function<void()> refreshOriginal;
#if HAS_QT_WEBENGINE
    refreshOriginal = [status, marketCombo, intervalCombo, currentRawSymbol, binanceView]() {
        const QString rawSymbol = normalizeChartSymbol(currentRawSymbol());
        if (rawSymbol.isEmpty()) {
            status->setText("Select a symbol, then refresh.");
            return;
        }
        const QString marketKey = marketCombo->currentData().toString();
        const QString interval = intervalCombo->currentText().trimmed();
        const QString url = buildBinanceWebUrl(rawSymbol, interval, marketKey);
        binanceView->load(QUrl(url));
        status->setText(QString("Original view loaded: %1 (%2)").arg(rawSymbol, interval));
    };
#else
    refreshOriginal = [status, marketCombo, intervalCombo, currentRawSymbol, chartWidget]() {
        const QString rawSymbol = normalizeChartSymbol(currentRawSymbol());
        if (rawSymbol.isEmpty()) {
            status->setText("Select a symbol, then refresh.");
            chartWidget->setCandles({});
            chartWidget->setOverlayMessage("Symbol is required.");
            return;
        }
        const bool futures = marketCombo->currentData().toString() == "futures";
        const QString interval = intervalCombo->currentText().trimmed();
        const auto result = BinanceRestClient::fetchKlines(
            rawSymbol,
            interval,
            futures,
            false,
            320,
            12000);
        if (!result.ok) {
            chartWidget->setCandles({});
            chartWidget->setOverlayMessage(result.error);
            status->setText(QString("Original chart load failed: %1").arg(result.error));
            return;
        }
        chartWidget->setCandles(result.candles);
        chartWidget->setOverlayMessage(futures ? "Source: Binance Futures" : "Source: Binance Spot");
        status->setText(QString("Original view loaded: %1 (%2)").arg(rawSymbol, interval));
    };
#endif

    std::function<void()> refreshTradingView;
#if HAS_QT_WEBENGINE
    refreshTradingView = [status, intervalCombo, currentRawSymbol, tradingView]() {
        const QString rawSymbol = normalizeChartSymbol(currentRawSymbol());
        if (rawSymbol.isEmpty()) {
            status->setText("Select a symbol, then refresh.");
            return;
        }
        const QString tvInterval = tradingViewIntervalFor(intervalCombo->currentText());
        const QString html = QStringLiteral(R"(
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    html, body, #container { width: 100%%; height: 100%%; margin: 0; padding: 0; background: #0b1020; overflow: hidden; }
    ::-webkit-scrollbar { width: 0px; height: 0px; display: none; }
  </style>
</head>
<body>
  <div id="container">
    <div class="tradingview-widget-container" style="height:100%%; width:100%%;">
      <div id="tradingview_embed"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({
          "width": "100%%",
          "height": "100%%",
          "symbol": "BINANCE:%1",
          "interval": "%2",
          "timezone": "Etc/UTC",
          "theme": "dark",
          "style": "1",
          "locale": "en",
          "toolbar_bg": "#0b1020",
          "enable_publishing": false,
          "hide_top_toolbar": false,
          "hide_legend": false,
          "allow_symbol_change": true,
          "container_id": "tradingview_embed"
        });
      </script>
    </div>
  </div>
</body>
</html>
        )").arg(rawSymbol, tvInterval);
        tradingView->setHtml(html, QUrl("https://www.tradingview.com/"));
        status->setText(QString("TradingView loaded: %1 (%2)").arg(rawSymbol, intervalCombo->currentText()));
    };
#else
    refreshTradingView = [status]() {
        status->setText("TradingView embed unavailable: Qt WebEngine is not installed in this build.");
    };
#endif

    refreshCurrent = [refreshOriginal, refreshTradingView, viewModeCombo, chartStack, originalPage, tradingPage]() {
        const QString mode = viewModeCombo->currentData().toString();
        if (mode == "tradingview") {
            chartStack->setCurrentWidget(tradingPage);
            refreshTradingView();
            return;
        }
        chartStack->setCurrentWidget(originalPage);
        refreshOriginal();
    };

    auto syncFromDashboard = [this, symbolCombo, intervalCombo, refreshCurrent]() {
        if (!chartAutoFollowCheck_ || !chartAutoFollowCheck_->isChecked()) {
            return;
        }

        QString dashSymbol;
        if (dashboardSymbolList_) {
            const auto selectedSymbols = dashboardSymbolList_->selectedItems();
            if (!selectedSymbols.isEmpty()) {
                dashSymbol = normalizeChartSymbol(selectedSymbols.first()->text());
            }
        }

        QString dashInterval;
        if (dashboardIntervalList_) {
            const auto selectedIntervals = dashboardIntervalList_->selectedItems();
            if (!selectedIntervals.isEmpty()) {
                dashInterval = selectedIntervals.first()->text().trimmed();
            }
        }

        bool changed = false;
        if (!dashSymbol.isEmpty()) {
            const int symbolIdx = symbolCombo->findData(dashSymbol);
            if (symbolIdx >= 0 && symbolCombo->currentIndex() != symbolIdx) {
                QSignalBlocker blocker(symbolCombo);
                symbolCombo->setCurrentIndex(symbolIdx);
                changed = true;
            }
        }
        if (!dashInterval.isEmpty()) {
            const int intervalIdx = intervalCombo->findText(dashInterval, Qt::MatchFixedString);
            if (intervalIdx >= 0 && intervalCombo->currentIndex() != intervalIdx) {
                QSignalBlocker blocker(intervalCombo);
                intervalCombo->setCurrentIndex(intervalIdx);
                changed = true;
            }
        }

        if (changed) {
            refreshCurrent();
        }
    };

    connect(refreshBtn, &QPushButton::clicked, page, refreshCurrent);
    connect(symbolCombo, &QComboBox::currentTextChanged, page, [refreshCurrent](const QString &) {
        refreshCurrent();
    });
    connect(intervalCombo, &QComboBox::currentTextChanged, page, [refreshCurrent](const QString &) {
        refreshCurrent();
    });
    connect(viewModeCombo, &QComboBox::currentTextChanged, page, [refreshCurrent](const QString &) {
        refreshCurrent();
    });
    connect(marketCombo, &QComboBox::currentTextChanged, page, [loadSymbols, refreshCurrent](const QString &) {
        loadSymbols();
        refreshCurrent();
    });
    connect(autoFollowCheck, &QCheckBox::toggled, page, [syncFromDashboard](bool enabled) {
        if (enabled) {
            syncFromDashboard();
        }
    });
    if (dashboardSymbolList_) {
        connect(dashboardSymbolList_, &QListWidget::itemSelectionChanged, page, syncFromDashboard);
    }
    if (dashboardIntervalList_) {
        connect(dashboardIntervalList_, &QListWidget::itemSelectionChanged, page, syncFromDashboard);
    }

    connect(openBtn, &QPushButton::clicked, page, [marketCombo, intervalCombo, viewModeCombo, currentRawSymbol]() {
        const QString rawSymbol = normalizeChartSymbol(currentRawSymbol());
        if (rawSymbol.isEmpty()) {
            return;
        }
        const QString mode = viewModeCombo->currentData().toString();
        QUrl url;
        if (mode == "tradingview") {
            const QString tvInterval = tradingViewIntervalFor(intervalCombo->currentText());
            url = QUrl(QString("https://www.tradingview.com/chart/?symbol=BINANCE:%1&interval=%2")
                           .arg(rawSymbol, tvInterval));
        } else {
            const QString marketKey = marketCombo->currentData().toString();
            const QString interval = intervalCombo->currentText().trimmed();
            url = QUrl(buildBinanceWebUrl(rawSymbol, interval, marketKey));
        }
        QDesktopServices::openUrl(url);
    });

    loadSymbols();
    syncFromDashboard();
    QTimer::singleShot(0, page, [this, page, refreshCurrent]() {
        if (tabs_ && tabs_->currentWidget() == page) {
            refreshCurrent();
        }
    });
    if (tabs_) {
        connect(tabs_, &QTabWidget::currentChanged, page, [this, page, refreshCurrent](int) {
            if (tabs_ && tabs_->currentWidget() == page) {
                refreshCurrent();
            }
        });
    }

    return page;
}

QWidget *BacktestWindow::createPositionsTab() {
    auto *page = new QWidget(this);
    page->setObjectName("positionsPage");
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(12);

    auto *heading = new QLabel("Positions", page);
    heading->setStyleSheet("font-size: 18px; font-weight: 600;");
    layout->addWidget(heading);

    auto *desc = new QLabel(
        "Live/active positions view to mirror the Python Positions tab. Populate rows from your trading engine.",
        page);
    desc->setWordWrap(true);
    layout->addWidget(desc);

    auto *table = new QTableWidget(0, 10, page);
    table->setHorizontalHeaderLabels({
        "Symbol", "Interval", "Side", "Entry", "Mark", "Position %", "ROI (USDT)", "ROI (%)", "Leverage", "Status"
    });
    table->horizontalHeader()->setStretchLastSection(true);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    layout->addWidget(table, 1);

    return page;
}

QWidget *BacktestWindow::createBacktestTab() {
    auto *page = new QWidget(this);
    page->setObjectName("backtestPage");
    auto *rootLayout = new QVBoxLayout(page);
    rootLayout->setContentsMargins(0, 0, 0, 0);

    auto *scrollArea = new QScrollArea(page);
    scrollArea->setObjectName("backtestScrollArea");
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    rootLayout->addWidget(scrollArea);

    auto *scrollWidget = new QWidget(scrollArea);
    scrollWidget->setObjectName("backtestScrollWidget");
    scrollArea->setWidget(scrollWidget);
    auto *contentLayout = new QVBoxLayout(scrollWidget);
    contentLayout->setContentsMargins(12, 12, 12, 12);
    contentLayout->setSpacing(16);

    auto *topLayout = new QHBoxLayout();
    topLayout->setSpacing(16);
    contentLayout->addLayout(topLayout);

    topLayout->addWidget(createMarketsGroup(), 4);
    topLayout->addWidget(createParametersGroup(), 3);
    topLayout->addWidget(createIndicatorsGroup(), 2);

    auto *controlsLayout = new QHBoxLayout();
    runButton_ = new QPushButton("Run Backtest", page);
    controlsLayout->addWidget(runButton_);
    stopButton_ = new QPushButton("Stop", page);
    stopButton_->setEnabled(false);
    controlsLayout->addWidget(stopButton_);

    statusLabel_ = new QLabel(page);
    statusLabel_->setMinimumWidth(140);
    controlsLayout->addWidget(statusLabel_);

    addSelectedBtn_ = new QPushButton("Add Selected to Dashboard", page);
    controlsLayout->addWidget(addSelectedBtn_);
    addAllBtn_ = new QPushButton("Add All to Dashboard", page);
    controlsLayout->addWidget(addAllBtn_);
    controlsLayout->addStretch();

    auto *botStatusWidget = new QWidget(page);
    auto *botStatusLayout = new QHBoxLayout(botStatusWidget);
    botStatusLayout->setContentsMargins(0, 0, 0, 0);
    botStatusLayout->setSpacing(8);
    botStatusLabel_ = new QLabel("Bot Status: Idle", botStatusWidget);
    botTimeLabel_ = new QLabel("Bot Active Time: --", botStatusWidget);
    botStatusLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    botTimeLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    botStatusLayout->addWidget(botStatusLabel_);
    botStatusLayout->addWidget(botTimeLabel_);
    controlsLayout->addWidget(botStatusWidget);

    contentLayout->addLayout(controlsLayout);
    contentLayout->addWidget(createResultsGroup(), 1);

    return page;
}

QWidget *BacktestWindow::createCodeTab() {
    auto *page = new QWidget(this);
    page->setObjectName("codePage");
    codePage_ = page;
    auto *outer = new QVBoxLayout(page);
    outer->setContentsMargins(16, 16, 16, 16);
    outer->setSpacing(10);

    auto *scroll = new QScrollArea(page);
    scroll->setObjectName("codeScrollArea");
    scroll->setWidgetResizable(true);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    outer->addWidget(scroll);

    auto *container = new QWidget(scroll);
    scroll->setWidget(container);
    auto *layout = new QVBoxLayout(container);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->setSpacing(14);

    // Use explicit theme colors instead of palette-derived colors to avoid gray fallback on Windows.
    const bool isLight = dashboardThemeCombo_
        && dashboardThemeCombo_->currentText().compare("Light", Qt::CaseInsensitive) == 0;
    const QString surfaceColor = isLight ? QString("#f5f7fb") : QString("#0b1220");
    const QString textColor = isLight ? QString("#0f172a") : QString("#e6edf3");
    const QString mutedColor = isLight ? QString("#334155") : QString("#cbd5e1");
    QString surfaceStyle = QString(
        "QWidget#codeContent { background: %1; }"
        "QScrollArea#codeScrollArea { background: %1; border: none; }").arg(surfaceColor);
    container->setObjectName("codeContent");
    container->setStyleSheet(surfaceStyle);
    scroll->setStyleSheet(surfaceStyle);

    auto *heading = new QLabel("Code Languages", container);
    heading->setStyleSheet(QString("font-size: 20px; font-weight: 700; color: %1;").arg(textColor));
    layout->addWidget(heading);

    auto *sub = new QLabel(
        "Select your preferred code language. Folders for each language are created automatically to keep related assets organized.",
        container);
    sub->setWordWrap(true);
    sub->setStyleSheet(QString("color: %1;").arg(mutedColor));
    layout->addWidget(sub);

    auto makeBadge = [](const QString &text, const QString &bg) {
        auto *lbl = new QLabel(text);
        lbl->setStyleSheet(QString("padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 700; "
                                   "color: #cbd5e1; background: %1;")
                               .arg(bg));
        return lbl;
    };
    auto makeCard = [&](const QString &title,
                        const QString &subtitle,
                        const QString &border,
                        const QString &badgeText = QString(),
                        const QString &badgeBg = QString("#1f2937"),
                        bool disabled = false,
                        std::function<void()> onClick = nullptr) {
        auto *button = new QPushButton(container);
        button->setFlat(true);
        button->setCursor(disabled ? Qt::ArrowCursor : Qt::PointingHandCursor);
        button->setStyleSheet("QPushButton { border: none; padding: 0; text-align: left; }");
        button->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);

        auto *card = new QFrame(button);
        card->setMinimumHeight(130);
        card->setMaximumHeight(150);
        card->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::MinimumExpanding);
        if (!disabled) {
            card->setStyleSheet(QString(
                "QFrame { border: 2px solid #1f2937; border-radius: 10px; background: #0d1117; padding: 8px; }"
                "QLabel { color: #e6edf3; }"
                "QPushButton:hover QFrame { border-color: %1; }"
                "QPushButton:pressed QFrame { border-color: %1; background: #0f172a; }").arg(border));
        } else {
            card->setStyleSheet(
                "QFrame { border: 2px solid #1f2937; border-radius: 10px; background: #0d1117; padding: 8px; }"
                "QLabel { color: #6b7280; }");
        }
        auto *v = new QVBoxLayout(card);
        v->setContentsMargins(12, 10, 12, 10);
        v->setSpacing(6);
        if (!badgeText.isEmpty()) {
            v->addWidget(makeBadge(badgeText, badgeBg), 0, Qt::AlignLeft);
        }
        auto *titleLbl = new QLabel(title, card);
        titleLbl->setStyleSheet(QString("font-size: 18px; font-weight: 700; color:%1;")
                                    .arg(disabled ? "#6b7280" : "#e6edf3"));
        v->addWidget(titleLbl);
        auto *subLbl = new QLabel(subtitle, card);
        subLbl->setWordWrap(true);
        subLbl->setStyleSheet(QString("color:%1; font-size: 12px;").arg(disabled ? "#4b5563" : "#94a3b8"));
        v->addWidget(subLbl);
        v->addStretch();

        auto *btnLayout = new QVBoxLayout(button);
        btnLayout->setContentsMargins(0, 0, 0, 0);
        btnLayout->addWidget(card);

        button->setEnabled(!disabled);
        if (onClick && !disabled) {
            connect(button, &QPushButton::clicked, button, [onClick]() { onClick(); });
        }
        return button;
    };

    auto addSection = [&](const QString &title, const QList<QWidget *> &cards) {
        auto *titleLbl = new QLabel(title, container);
        titleLbl->setStyleSheet(QString("font-size: 16px; font-weight: 700; color: %1;").arg(textColor));
        layout->addWidget(titleLbl);

        auto *row = new QGridLayout();
        row->setHorizontalSpacing(12);
        row->setVerticalSpacing(12);

        for (int i = 0; i < cards.size(); ++i) {
            row->addWidget(cards[i], 0, i);
        }
        layout->addLayout(row);
    };

    addSection("Choose your language",
               {makeCard("Python", "Use Languages/Python/main.py for Python runtime", "#1f2937", "External",
                         "#1f2937", false, [this]() {
                             QMessageBox::information(
                                 this,
                                 "Python runtime",
                                 "This C++ app now uses native C++ clients.\n"
                                 "Run Languages/Python/main.py separately for the Python runtime.");
                         }),
                makeCard("C++", "Qt native desktop (active)", "#2563eb", "Active", "#1f2937", false, [this]() {
                    if (tabs_ && backtestTab_) {
                        tabs_->setCurrentWidget(backtestTab_);
                    }
                    updateStatusMessage("C++ workspace active.");
                }),
                makeCard("Rust", "Memory safe - coming soon", "#1f2937", "Coming Soon", "#1f2937", true),
                makeCard("C", "Low-level power - coming soon", "#1f2937", "Coming Soon", "#1f2937", true)});

    auto *envTitle = new QLabel("Environment Versions", container);
    envTitle->setStyleSheet(QString("font-size: 14px; font-weight: 700; color: %1;").arg(textColor));
    layout->addWidget(envTitle);

    auto *envActions = new QHBoxLayout();
    envActions->setContentsMargins(0, 0, 0, 0);
    envActions->addStretch();
    auto *refreshEnvBtn = new QPushButton("Refresh Env Versions", container);
    refreshEnvBtn->setCursor(Qt::PointingHandCursor);
    refreshEnvBtn->setToolTip("Re-evaluate C++ dependency versions.");
    envActions->addWidget(refreshEnvBtn);
    layout->addLayout(envActions);

    auto *table = new QTableWidget(container);
    table->setColumnCount(3);
    table->setHorizontalHeaderLabels({"Dependency", "Installed", "Latest"});
    table->horizontalHeader()->setStretchLastSection(true);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table->setSelectionMode(QAbstractItemView::NoSelection);
    table->verticalHeader()->setVisible(false);
    table->horizontalHeader()->setStyleSheet("font-weight: 700;");

    struct Row {
        QString name;
        QString installed;
        QString latest;
    };

    const auto loadRows = []() -> QVector<Row> {
        QVector<Row> rows;
        bool hasCheckingPlaceholder = false;
        const auto resolveInstalledFromLabel = [](const QString &name) -> QString {
            const QString key = name.trimmed().toLower();
            if (key == QStringLiteral("binance rest client (native)")) {
                const QString packagedVersion = packagedInstalledVersion({QStringLiteral("Binance REST client (native)")});
                if (!isMissingVersionMarker(packagedVersion)) {
                    return packagedVersion;
                }
                const QString releaseTag = releaseTagFromMetadataDirs();
                if (!isMissingVersionMarker(releaseTag)) {
                    return releaseTag;
                }
                const QDir appDir(QCoreApplication::applicationDirPath());
                const bool hasQtNetworkDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6Network.dll")))
                    || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6Networkd.dll")));
                return hasQtNetworkDll ? QStringLiteral("Active") : QStringLiteral("Not installed");
            }
            if (key == QStringLiteral("binance websocket client (native)")) {
                const QString packagedVersion = packagedInstalledVersion({QStringLiteral("Binance WebSocket client (native)")});
                if (!isMissingVersionMarker(packagedVersion)) {
                    return packagedVersion;
                }
                const QString releaseTag = releaseTagFromMetadataDirs();
                if (!isMissingVersionMarker(releaseTag)) {
                    return releaseTag;
                }
                const QDir appDir(QCoreApplication::applicationDirPath());
                const bool hasQtWebSocketsDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSockets.dll")))
                    || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSocketsd.dll")));
                const bool wsReady = (HAS_QT_WEBSOCKETS != 0) && hasQtWebSocketsDll;
                return wsReady ? QStringLiteral("Active") : QStringLiteral("Not installed");
            }
            if (key == QStringLiteral("eigen")) {
                return installedOrMissing(detectEigenVersion());
            }
            if (key == QStringLiteral("xtensor")) {
                return installedOrMissing(detectXtensorVersion());
            }
            if (key == QStringLiteral("ta-lib") || key == QStringLiteral("talib")) {
                return installedOrMissing(detectTaLibVersion());
            }
            if (key == QStringLiteral("libcurl") || key == QStringLiteral("curl")) {
                return installedOrMissing(detectLibcurlVersion());
            }
            if (key == QStringLiteral("cpr")) {
                return installedOrMissing(detectCprVersion());
            }
            return QString();
        };

        const QByteArray envRows = qgetenv("TB_CPP_ENV_VERSIONS_JSON");
        if (!envRows.trimmed().isEmpty()) {
            QJsonParseError parseError{};
            const QJsonDocument doc = QJsonDocument::fromJson(envRows, &parseError);
            if (parseError.error == QJsonParseError::NoError && doc.isArray()) {
                const QJsonArray arr = doc.array();
                rows.reserve(arr.size());
                for (const QJsonValue &entry : arr) {
                    if (!entry.isObject()) {
                        continue;
                    }
                    const QJsonObject obj = entry.toObject();
                    const QString name = obj.value(QStringLiteral("name")).toString().trimmed();
                    if (name.isEmpty()) {
                        continue;
                    }
                    QString installed = obj.value(QStringLiteral("installed")).toString().trimmed();
                    QString latest = obj.value(QStringLiteral("latest")).toString().trimmed();

                    if (isMissingVersionMarker(installed)) {
                        const QString repairedInstalled = resolveInstalledFromLabel(name);
                        if (!isMissingVersionMarker(repairedInstalled)) {
                            installed = repairedInstalled;
                        }
                    }
                    if (installed.isEmpty()) {
                        installed = QStringLiteral("Unknown");
                    }

                    const QString installedLower = installed.toLower();
                    const QString latestLower = latest.toLower();
                    if (installedLower == QStringLiteral("checking...")
                        || installedLower == QStringLiteral("not checked")
                        || latestLower == QStringLiteral("checking...")
                        || latestLower == QStringLiteral("not checked")) {
                        hasCheckingPlaceholder = true;
                    }

                    if ((latest.isEmpty()
                         || latestLower == QStringLiteral("checking...")
                         || latestLower == QStringLiteral("not checked")
                         || isMissingVersionMarker(latest))
                        && !isMissingVersionMarker(installed)) {
                        latest = installed;
                    }
                    if (latest.isEmpty()) {
                        latest = QStringLiteral("Unknown");
                    }
                    rows.push_back({name, installed, latest});
                }
            }
        }

        if (!rows.isEmpty() && !hasCheckingPlaceholder) {
            return rows;
        }

        rows.clear();
        const QDir appDir(QCoreApplication::applicationDirPath());
        const bool hasQtCoreDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6Core.dll")))
            || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6Cored.dll")));
        const bool hasQtNetworkDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6Network.dll")))
            || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6Networkd.dll")));
        const bool hasQtWebSocketsDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSockets.dll")))
            || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSocketsd.dll")));
        const bool wsReady = (HAS_QT_WEBSOCKETS != 0) && hasQtWebSocketsDll;

        const QString qtRuntimeVersion = QString::fromLatin1(QT_VERSION_STR);
        const QString qtInstalled = hasQtCoreDll ? qtRuntimeVersion : QStringLiteral("Not installed");
        const QString qtNetworkInstalled = hasQtNetworkDll ? qtRuntimeVersion : QStringLiteral("Not installed");
        const QString qtWsInstalled = wsReady ? qtRuntimeVersion : QStringLiteral("Not installed");

        const QString eigenInstalled = installedOrMissing(detectEigenVersion());
        const QString xtensorInstalled = installedOrMissing(detectXtensorVersion());
        const QString talibInstalled = installedOrMissing(detectTaLibVersion());
        const QString libcurlInstalled = installedOrMissing(detectLibcurlVersion());
        const QString cprInstalled = installedOrMissing(detectCprVersion());

        const auto latestOrUnknown = [](const QString &installed) {
            return installed.compare(QStringLiteral("Not installed"), Qt::CaseInsensitive) == 0
                ? QStringLiteral("Unknown")
                : installed;
        };

        rows = {
            {QStringLiteral("Qt6 (C++)"), qtInstalled, latestOrUnknown(qtInstalled)},
            {QStringLiteral("Qt6 Network (REST)"), qtNetworkInstalled, latestOrUnknown(qtNetworkInstalled)},
            {QStringLiteral("Qt6 WebSockets"),
             qtWsInstalled,
             wsReady ? qtRuntimeVersion : QStringLiteral("Install Qt WebSockets")},
            {QStringLiteral("Binance REST client (native)"),
             hasQtNetworkDll ? QStringLiteral("Active") : QStringLiteral("Inactive"),
             hasQtNetworkDll ? QStringLiteral("Active") : QStringLiteral("Needs Qt Network")},
            {QStringLiteral("Binance WebSocket client (native)"),
             wsReady ? QStringLiteral("Active") : QStringLiteral("Inactive"),
             wsReady ? QStringLiteral("Active") : QStringLiteral("Needs Qt WebSockets")},
            {QStringLiteral("Eigen"), eigenInstalled, latestOrUnknown(eigenInstalled)},
            {QStringLiteral("xtensor"), xtensorInstalled, latestOrUnknown(xtensorInstalled)},
            {QStringLiteral("TA-Lib"), talibInstalled, latestOrUnknown(talibInstalled)},
            {QStringLiteral("libcurl"), libcurlInstalled, latestOrUnknown(libcurlInstalled)},
            {QStringLiteral("cpr"), cprInstalled, latestOrUnknown(cprInstalled)}};
        return rows;
    };

    const auto applyRows = [table](const QVector<Row> &rows) {
        table->setRowCount(rows.size());
        for (int i = 0; i < rows.size(); ++i) {
            table->setItem(i, 0, new QTableWidgetItem(rows[i].name));
            table->setItem(i, 1, new QTableWidgetItem(rows[i].installed));
            table->setItem(i, 2, new QTableWidgetItem(rows[i].latest));
        }
    };

    applyRows(loadRows());

    connect(refreshEnvBtn, &QPushButton::clicked, this, [this, refreshEnvBtn, loadRows, applyRows]() mutable {
        refreshEnvBtn->setEnabled(false);
        refreshEnvBtn->setText(QStringLiteral("Refreshing..."));
        QCoreApplication::processEvents();
        applyRows(loadRows());
        refreshEnvBtn->setText(QStringLiteral("Refresh Env Versions"));
        refreshEnvBtn->setEnabled(true);
        updateStatusMessage(QStringLiteral("Environment versions refreshed."));
    });
    layout->addWidget(table);

    auto *statusRow = new QHBoxLayout();
    auto *statusLbl = new QLabel("Bot Status: OFF", container);
    statusLbl->setStyleSheet("color: #ef4444; font-weight: 700;");
    auto *activeLbl = new QLabel("Bot Active Time: --", container);
    activeLbl->setStyleSheet("color: #cbd5e1;");
    statusRow->addStretch();
    statusRow->addWidget(statusLbl);
    statusRow->addSpacing(18);
    statusRow->addWidget(activeLbl);
    layout->addLayout(statusRow);

    layout->addStretch();
    return page;
}

QWidget *BacktestWindow::createMarketsGroup() {
    auto *group = new QGroupBox("Markets", this);
    auto *layout = new QGridLayout(group);

    auto *symbolLabel = new QLabel("Symbol Source:", group);
    symbolSourceCombo_ = new QComboBox(group);
    symbolSourceCombo_->addItems({"Futures", "Spot"});
    auto *refreshBtn = new QPushButton("Refresh", group);
    layout->addWidget(symbolLabel, 0, 0);
    layout->addWidget(symbolSourceCombo_, 0, 1);
    layout->addWidget(refreshBtn, 0, 2);

    auto *symbolsInfo = new QLabel("Symbols (select 1 or more):", group);
    layout->addWidget(symbolsInfo, 1, 0, 1, 3);
    symbolList_ = new QListWidget(group);
    symbolList_->setSelectionMode(QAbstractItemView::MultiSelection);
    symbolList_->setMinimumWidth(140);
    symbolList_->setMaximumWidth(220);
    layout->addWidget(symbolList_, 2, 0, 4, 3);

    auto *intervalInfo = new QLabel("Intervals (select 1 or more):", group);
    layout->addWidget(intervalInfo, 1, 3);
    intervalList_ = new QListWidget(group);
    intervalList_->setSelectionMode(QAbstractItemView::MultiSelection);
    intervalList_->setMinimumWidth(120);
    intervalList_->setMaximumWidth(200);
    layout->addWidget(intervalList_, 2, 3, 4, 2);

    customIntervalEdit_ = new QLineEdit(group);
    customIntervalEdit_->setPlaceholderText("e.g., 45s, 7m, 90m");
    layout->addWidget(customIntervalEdit_, 6, 3, 1, 1);
    auto *addBtn = new QPushButton("Add Custom Interval(s)", group);
    layout->addWidget(addBtn, 6, 4, 1, 1);
    connect(addBtn, &QPushButton::clicked, this, &BacktestWindow::handleAddCustomIntervals);
    connect(refreshBtn, &QPushButton::clicked, this, [this]() {
        updateStatusMessage("Symbol catalog refreshed from " + symbolSourceCombo_->currentText());
    });

    return group;
}

QWidget *BacktestWindow::createParametersGroup() {
    auto *group = new QGroupBox("Parameters", this);
    auto *form = new QFormLayout(group);

    auto addCombo = [form](const QString &label, const QStringList &items) {
        auto *combo = new QComboBox(form->parentWidget());
        combo->addItems(items);
        form->addRow(label, combo);
        return combo;
    };

    addCombo("Logic:", {"AND", "OR"});
    auto *startDate = new QDateEdit(QDate::currentDate().addMonths(-1), group);
    startDate->setCalendarPopup(true);
    form->addRow("Start Date:", startDate);
    auto *endDate = new QDateEdit(QDate::currentDate(), group);
    endDate->setCalendarPopup(true);
    form->addRow("End Date:", endDate);

    auto *capitalSpin = new QDoubleSpinBox(group);
    capitalSpin->setSuffix(" USDT");
    capitalSpin->setRange(0.0, 1'000'000.0);
    capitalSpin->setValue(1000.0);
    form->addRow("Capital:", capitalSpin);

    auto *positionPct = new QDoubleSpinBox(group);
    positionPct->setSuffix(" %");
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setValue(2.0);
    form->addRow("Position %:", positionPct);

    auto *sideCombo = addCombo("Side:", {"BOTH", "BUY", "SELL"});
    sideCombo->setCurrentText("BOTH");

    addCombo("Margin Mode:", {"Isolated", "Cross"});
    addCombo("Position Mode:", {"Hedge", "One-way"});
    addCombo("Assets Mode:", {"Single-Asset", "Multi-Asset"});
    addCombo("Account Mode:", {"Classic Trading", "Multi-Asset Mode"});

    auto *leverageSpin = new QSpinBox(group);
    leverageSpin->setRange(1, 125);
    leverageSpin->setValue(5);
    form->addRow("Leverage:", leverageSpin);

    auto *loopSpin = new QSpinBox(group);
    loopSpin->setRange(1, 10'000);
    loopSpin->setSuffix(" ms");
    loopSpin->setValue(500);
    form->addRow("Loop Interval:", loopSpin);

    addCombo("MDD Logic:", {"Per Trade", "Cumulative", "Entire Account"});

    auto *templateEnable = new QCheckBox("Enable Backtest Template", group);
    templateEnable->setChecked(false);
    auto *templateCombo = new QComboBox(group);
    templateCombo->addItems({"Volume Top 50", "RSI Reversal", "StochRSI Sweep"});
    templateCombo->setEnabled(false);

    connect(templateEnable, &QCheckBox::toggled, templateCombo, &QWidget::setEnabled);
    form->addRow(templateEnable);
    form->addRow("Template:", templateCombo);

    return group;
}

QWidget *BacktestWindow::createIndicatorsGroup() {
    auto *group = new QGroupBox("Indicators", this);
    auto *grid = new QGridLayout(group);
    grid->setHorizontalSpacing(14);
    grid->setVerticalSpacing(8);
    grid->setColumnStretch(0, 2);
    grid->setColumnStretch(1, 1);

    const QStringList indicators = {
        "Moving Average (MA)", "Donchian Channels", "Parabolic SAR", "Bollinger Bands",
        "Relative Strength Index", "Volume", "Stochastic RSI", "Williams %R",
        "MACD", "Ultimate Oscillator", "ADX", "DMI", "SuperTrend", "EMA", "Stochastic Oscillator"
    };

    int row = 0;
    for (const auto &ind : indicators) {
        auto *cb = new QCheckBox(ind, group);
        auto *btn = new QPushButton("Params...", group);
        btn->setMinimumWidth(140);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        connect(cb, &QCheckBox::toggled, btn, &QWidget::setEnabled);
        grid->addWidget(cb, row, 0);
        grid->addWidget(btn, row, 1);
        ++row;
    }

    return group;
}

QWidget *BacktestWindow::createResultsGroup() {
    auto *group = new QGroupBox("Backtest Results", this);
    auto *layout = new QVBoxLayout(group);
    resultsTable_ = new QTableWidget(0, 10, group);
    resultsTable_->setHorizontalHeaderLabels({
        "Symbol", "Interval", "Logic", "Trades", "Loop Interval",
        "Start Date", "End Date", "Position %", "ROI (USDT)", "ROI (%)"
    });
    resultsTable_->horizontalHeader()->setStretchLastSection(true);
    resultsTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    layout->addWidget(resultsTable_);
    return group;
}

void BacktestWindow::populateDefaults() {
    if (symbolList_) {
        symbolList_->addItems({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"});
        for (int i = 0; i < symbolList_->count(); ++i) {
            if (i < 2) {
                symbolList_->item(i)->setSelected(true);
            }
        }
    }
    if (intervalList_) {
        intervalList_->addItems({"1m", "3m", "5m", "15m", "1h", "4h", "1d"});
        for (int i = 0; i < intervalList_->count() && i < 2; ++i) {
            intervalList_->item(i)->setSelected(true);
        }
    }
}

void BacktestWindow::wireSignals() {
    connect(runButton_, &QPushButton::clicked, this, &BacktestWindow::handleRunBacktest);
    connect(stopButton_, &QPushButton::clicked, this, &BacktestWindow::handleStopBacktest);
    connect(addSelectedBtn_, &QPushButton::clicked, this, [this]() {
        const int selectedSymbols = symbolList_ ? symbolList_->selectedItems().size() : 0;
        const int selectedIntervals = intervalList_ ? intervalList_->selectedItems().size() : 0;
        updateStatusMessage(
            QString("Added %1 symbol(s) x %2 interval(s) to dashboard.")
                .arg(selectedSymbols)
                .arg(selectedIntervals));
    });
    connect(addAllBtn_, &QPushButton::clicked, this, [this]() {
        const int symbolCount = symbolList_ ? symbolList_->count() : 0;
        const int intervalCount = intervalList_ ? intervalList_->count() : 0;
        updateStatusMessage(
            QString("Added all %1 symbol(s) x %2 interval(s) to dashboard.")
                .arg(symbolCount)
                .arg(intervalCount));
    });
}

void BacktestWindow::handleAddCustomIntervals() {
    if (!intervalList_) {
        return;
    }
    const QString raw = customIntervalEdit_ ? customIntervalEdit_->text().trimmed() : QString();
    if (raw.isEmpty()) {
        updateStatusMessage("No intervals entered.");
        return;
    }
    const auto parts = raw.split(',', Qt::SkipEmptyParts);
    for (QString part : parts) {
        part = part.trimmed();
        appendUniqueInterval(part);
    }
    if (customIntervalEdit_) {
        customIntervalEdit_->clear();
    }
    updateStatusMessage("Custom intervals appended.");
}

void BacktestWindow::handleRunBacktest() {
    botStart_ = std::chrono::steady_clock::now();
    ensureBotTimer(true);
    botStatusLabel_->setText("Bot Status: Running");
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText("Bot Status: ON");
        chartBotStatusLabel_->setStyleSheet("color: #16a34a; font-weight: 700;");
    }
    runButton_->setEnabled(false);
    stopButton_->setEnabled(true);
    updateStatusMessage("Running backtest...");

    const int currentRow = resultsTable_->rowCount();
    resultsTable_->insertRow(currentRow);
    resultsTable_->setItem(currentRow, 0, new QTableWidgetItem("BTCUSDT"));
    resultsTable_->setItem(currentRow, 1, new QTableWidgetItem("1h"));
    resultsTable_->setItem(currentRow, 2, new QTableWidgetItem("AND"));
    resultsTable_->setItem(currentRow, 3, new QTableWidgetItem("42"));
    resultsTable_->setItem(currentRow, 4, new QTableWidgetItem("500 ms"));
    resultsTable_->setItem(currentRow, 5, new QTableWidgetItem("2024-01-01"));
    resultsTable_->setItem(currentRow, 6, new QTableWidgetItem("2024-02-01"));
    resultsTable_->setItem(currentRow, 7, new QTableWidgetItem("2%"));
    resultsTable_->setItem(currentRow, 8, new QTableWidgetItem("+152.4"));
    resultsTable_->setItem(currentRow, 9, new QTableWidgetItem("+15.2%"));
}

void BacktestWindow::handleStopBacktest() {
    ensureBotTimer(false);
    botTimeLabel_->setText("Bot Active Time: --");
    botStatusLabel_->setText("Bot Status: Stopped");
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText("Bot Active Time: --");
    }
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText("Bot Status: OFF");
        chartBotStatusLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
    }
    runButton_->setEnabled(true);
    stopButton_->setEnabled(false);
    updateStatusMessage("Backtest stopped.");
}

void BacktestWindow::updateBotActiveTime() {
    if (!botTimer_) {
        return;
    }
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - botStart_);
    const QString text = "Bot Active Time: " + formatDuration(elapsed.count());
    botTimeLabel_->setText(text);
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(text);
    }
}

void BacktestWindow::ensureBotTimer(bool running) {
    if (!botTimer_) {
        botTimer_ = new QTimer(this);
        botTimer_->setInterval(1000);
        connect(botTimer_, &QTimer::timeout, this, &BacktestWindow::updateBotActiveTime);
    }
    if (running) {
        botTimer_->start();
    } else {
        botTimer_->stop();
    }
}

void BacktestWindow::updateStatusMessage(const QString &message) {
    if (statusLabel_) {
        statusLabel_->setText(message);
    }
}

void BacktestWindow::appendUniqueInterval(const QString &interval) {
    if (!intervalList_ || interval.isEmpty()) {
        return;
    }
    for (int i = 0; i < intervalList_->count(); ++i) {
        if (intervalList_->item(i)->text().compare(interval, Qt::CaseInsensitive) == 0) {
            return;
        }
    }
    intervalList_->addItem(interval);
}
