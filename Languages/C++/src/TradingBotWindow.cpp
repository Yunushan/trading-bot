#include "TradingBotWindow.h"
#include "BinanceRestClient.h"
#include "BinanceWsClient.h"

#include <QApplication>
#include <QCheckBox>
#include <QAbstractItemView>
#include <QComboBox>
#include <QDate>
#include <QDateTime>
#include <QDateEdit>
#include <QDesktopServices>
#include <QDoubleSpinBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFileDialog>
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
#include <QLocale>
#include <QMap>
#include <QPushButton>
#include <QMessageBox>
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QFontMetrics>
#include <QEventLoop>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QPainter>
#include <QPainterPath>
#include <QPaintEvent>
#include <QProcess>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QScreen>
#include <QShowEvent>
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
#include <QTextEdit>
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
#include <cmath>
#include <functional>
#include <limits>
#include <memory>
#include <set>

namespace {
constexpr int kTableCellNumericRole = Qt::UserRole + 2;
constexpr int kPositionsRowSequenceRole = Qt::UserRole + 3;
constexpr int kTableCellRawNumericRole = Qt::UserRole + 4;
constexpr int kTableCellRawRoiBasisRole = Qt::UserRole + 5;

void setTableCellText(QTableWidget *table, int row, int col, const QString &text) {
    if (!table) {
        return;
    }
    QTableWidgetItem *item = table->item(row, col);
    if (!item) {
        item = new QTableWidgetItem(text);
        table->setItem(row, col, item);
    } else {
        item->setText(text);
    }
    item->setData(Qt::UserRole, text);
}

void setTableCellNumeric(QTableWidget *table, int row, int col, double value) {
    if (!table) {
        return;
    }
    QTableWidgetItem *item = table->item(row, col);
    if (!item) {
        item = new QTableWidgetItem();
        table->setItem(row, col, item);
    }
    if (qIsFinite(value)) {
        item->setData(kTableCellNumericRole, value);
        item->setData(kTableCellRawNumericRole, value);
    } else {
        item->setData(kTableCellNumericRole, QVariant());
        item->setData(kTableCellRawNumericRole, QVariant());
    }
}

double tableCellNumeric(const QTableWidgetItem *item, double fallback = 0.0) {
    if (!item) {
        return fallback;
    }
    bool ok = false;
    const double value = item->data(kTableCellNumericRole).toDouble(&ok);
    if (ok && qIsFinite(value)) {
        return value;
    }
    return fallback;
}

double tableCellRawNumeric(const QTableWidgetItem *item, double fallback = 0.0) {
    if (!item) {
        return fallback;
    }
    bool ok = false;
    const double rawValue = item->data(kTableCellRawNumericRole).toDouble(&ok);
    if (ok && qIsFinite(rawValue)) {
        return rawValue;
    }
    return tableCellNumeric(item, fallback);
}

void setTableCellRoiBasis(QTableWidgetItem *item, double value) {
    if (!item) {
        return;
    }
    if (qIsFinite(value)) {
        item->setData(Qt::UserRole + 1, value);
        item->setData(kTableCellRawRoiBasisRole, value);
    } else {
        item->setData(Qt::UserRole + 1, QVariant());
        item->setData(kTableCellRawRoiBasisRole, QVariant());
    }
}

double tableCellRawRoiBasis(const QTableWidgetItem *item, double fallback = 0.0) {
    if (!item) {
        return fallback;
    }
    bool ok = false;
    const double rawValue = item->data(kTableCellRawRoiBasisRole).toDouble(&ok);
    if (ok && qIsFinite(rawValue)) {
        return rawValue;
    }
    const double displayValue = item->data(Qt::UserRole + 1).toDouble(&ok);
    if (ok && qIsFinite(displayValue)) {
        return displayValue;
    }
    return fallback;
}

class ScopedTableSortingPause final {
public:
    explicit ScopedTableSortingPause(QTableWidget *table)
        : table_(table),
          restoreSorting_(table_ && table_->isSortingEnabled()) {
        if (restoreSorting_) {
            table_->setSortingEnabled(false);
        }
    }

    ~ScopedTableSortingPause() {
        if (restoreSorting_ && table_) {
            table_->setSortingEnabled(true);
        }
    }

private:
    QTableWidget *table_ = nullptr;
    bool restoreSorting_ = false;
};

class ScopedTableUpdatesPause final {
public:
    explicit ScopedTableUpdatesPause(QTableWidget *table, bool enabled = true)
        : table_(enabled ? table : nullptr),
          tableUpdatesWereEnabled_(table_ && table_->updatesEnabled()),
          viewport_(table_ ? table_->viewport() : nullptr),
          viewportUpdatesWereEnabled_(viewport_ && viewport_->updatesEnabled()) {
        if (tableUpdatesWereEnabled_) {
            table_->setUpdatesEnabled(false);
        }
        if (viewportUpdatesWereEnabled_) {
            viewport_->setUpdatesEnabled(false);
        }
    }

    ~ScopedTableUpdatesPause() {
        if (viewport_ && viewportUpdatesWereEnabled_) {
            viewport_->setUpdatesEnabled(true);
            viewport_->update();
        }
        if (table_ && tableUpdatesWereEnabled_) {
            table_->setUpdatesEnabled(true);
            table_->update();
        }
    }

private:
    QTableWidget *table_ = nullptr;
    bool tableUpdatesWereEnabled_ = false;
    QWidget *viewport_ = nullptr;
    bool viewportUpdatesWereEnabled_ = false;
};

void pumpUiEvents(int maxMs = 5) {
    QCoreApplication::processEvents(QEventLoop::AllEvents, maxMs);
}

struct DashboardTemplatePreset {
    bool valid = false;
    double positionPct = 0.0;
    int leverage = 0;
    QString marginMode;
    QMap<QString, QVariantMap> indicators;
};

DashboardTemplatePreset dashboardTemplatePresetForKey(const QString &templateKey) {
    DashboardTemplatePreset preset;
    auto addDefaultSignalPack = [&preset]() {
        preset.indicators.insert(
            QStringLiteral("rsi"),
            QVariantMap{
                {QStringLiteral("enabled"), true},
                {QStringLiteral("buy_value"), 30.0},
                {QStringLiteral("sell_value"), 70.0},
            });
        preset.indicators.insert(
            QStringLiteral("stoch_rsi"),
            QVariantMap{
                {QStringLiteral("enabled"), true},
                {QStringLiteral("buy_value"), 20.0},
                {QStringLiteral("sell_value"), 80.0},
            });
        preset.indicators.insert(
            QStringLiteral("willr"),
            QVariantMap{
                {QStringLiteral("enabled"), true},
                {QStringLiteral("buy_value"), -80.0},
                {QStringLiteral("sell_value"), -20.0},
            });
    };

    const QString key = templateKey.trimmed().toLower();
    if (key == QStringLiteral("top10")) {
        preset.valid = true;
        preset.positionPct = 2.0;
        preset.leverage = 5;
        preset.marginMode = QStringLiteral("Isolated");
        addDefaultSignalPack();
        return preset;
    }
    if (key == QStringLiteral("top50")) {
        preset.valid = true;
        preset.positionPct = 2.0;
        preset.leverage = 20;
        preset.marginMode = QStringLiteral("Isolated");
        addDefaultSignalPack();
        return preset;
    }
    if (key == QStringLiteral("top100")) {
        preset.valid = true;
        preset.positionPct = 1.0;
        preset.leverage = 5;
        preset.marginMode = QStringLiteral("Isolated");
        addDefaultSignalPack();
        return preset;
    }
    return preset;
}

class LanguageSwitchSplash final : public QWidget {
public:
    explicit LanguageSwitchSplash(const QString &statusText, QWidget *parent = nullptr)
        : QWidget(parent),
          statusText_(statusText.trimmed().isEmpty() ? QStringLiteral("Loading…") : statusText.trimmed()),
          logoPixmap_(QStringLiteral(":/icons/crypto_forex_logo.png")) {
        setWindowFlags(
            Qt::FramelessWindowHint
            | Qt::WindowStaysOnTopHint
            | Qt::Tool
            | Qt::WindowDoesNotAcceptFocus
            | Qt::NoDropShadowWindowHint);
        setAttribute(Qt::WA_TranslucentBackground, true);
        setAttribute(Qt::WA_ShowWithoutActivating, true);
        setAttribute(Qt::WA_TransparentForMouseEvents, true);
        setFixedSize(420, 320);

        if (!logoPixmap_.isNull()) {
            logoPixmap_ = logoPixmap_.scaled(
                72,
                72,
                Qt::KeepAspectRatio,
                Qt::SmoothTransformation);
        }

        if (QScreen *screen = QGuiApplication::primaryScreen()) {
            const QRect geo = screen->geometry();
            move(
                geo.x() + (geo.width() - width()) / 2,
                geo.y() + (geo.height() - height()) / 2);
        }

        spinnerTimer_ = new QTimer(this);
        spinnerTimer_->setInterval(40);
        connect(spinnerTimer_, &QTimer::timeout, this, [this]() {
            spinnerAngle_ = (spinnerAngle_ + 8) % 360;
            update();
        });
        spinnerTimer_->start();

        show();
        raise();
        activateWindow();
        QCoreApplication::processEvents(QEventLoop::AllEvents, 30);
    }

    void setStatusText(const QString &statusText) {
        statusText_ = statusText.trimmed().isEmpty() ? QStringLiteral("Loading…") : statusText.trimmed();
        update();
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
    }

protected:
    void paintEvent(QPaintEvent *event) override {
        Q_UNUSED(event);
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);

        const qreal w = width();
        const qreal h = height();
        const QRectF panelRect(0, 0, w, h);
        QPainterPath panelPath;
        panelPath.addRoundedRect(panelRect, 24.0, 24.0);
        painter.setClipPath(panelPath);

        QLinearGradient bgGrad(0, 0, 0, h);
        bgGrad.setColorAt(0.0, QColor(16, 22, 32, 245));
        bgGrad.setColorAt(1.0, QColor(10, 14, 22, 250));
        painter.fillRect(rect(), bgGrad);

        painter.setClipping(false);
        QPen borderPen(QColor(56, 189, 248, 80));
        borderPen.setWidthF(1.5);
        painter.setPen(borderPen);
        painter.setBrush(Qt::NoBrush);
        painter.drawRoundedRect(QRectF(0.75, 0.75, w - 1.5, h - 1.5), 24.0, 24.0);

        const QRectF accentRect(40.0, 0.0, w - 80.0, 3.0);
        QLinearGradient accentGrad(40.0, 0.0, w - 40.0, 0.0);
        accentGrad.setColorAt(0.0, QColor(56, 189, 248, 0));
        accentGrad.setColorAt(0.3, QColor(56, 189, 248, 180));
        accentGrad.setColorAt(0.5, QColor(52, 211, 153, 200));
        accentGrad.setColorAt(0.7, QColor(56, 189, 248, 180));
        accentGrad.setColorAt(1.0, QColor(56, 189, 248, 0));
        painter.setPen(Qt::NoPen);
        painter.setBrush(accentGrad);
        painter.drawRoundedRect(accentRect, 1.5, 1.5);

        int cy = 40;
        if (!logoPixmap_.isNull()) {
            painter.drawPixmap((width() - logoPixmap_.width()) / 2, cy, logoPixmap_);
            cy += 88;
        } else {
            cy += 20;
        }

        QFont titleFont(QStringLiteral("Segoe UI"), 18, QFont::Bold);
        painter.setFont(titleFont);
        painter.setPen(QColor(230, 237, 243));
        const QString titleText = QGuiApplication::applicationDisplayName().trimmed().isEmpty()
            ? QStringLiteral("Trading Bot")
            : QGuiApplication::applicationDisplayName();
        painter.drawText(
            QRectF(0, cy, w, 30),
            int(Qt::AlignHCenter | Qt::AlignTop),
            titleText);
        cy += 36;

        painter.setFont(QFont(QStringLiteral("Segoe UI"), 11));
        painter.setPen(QColor(148, 163, 184));
        painter.drawText(QRectF(0, cy, w, 22), int(Qt::AlignHCenter | Qt::AlignTop), statusText_);
        cy += 34;

        const QRectF spinnerRect((w - 44.0) / 2.0, cy, 44.0, 44.0);
        QPen trackPen(QColor(148, 163, 184, 40));
        trackPen.setWidthF(3.0);
        trackPen.setCapStyle(Qt::RoundCap);
        painter.setPen(trackPen);
        painter.setBrush(Qt::NoBrush);
        painter.drawEllipse(spinnerRect);

        QPainterPath arcPath;
        arcPath.arcMoveTo(spinnerRect, spinnerAngle_);
        arcPath.arcTo(spinnerRect, spinnerAngle_, 100.0);
        QPen arcPen(QColor(56, 189, 248));
        arcPen.setWidthF(3.0);
        arcPen.setCapStyle(Qt::RoundCap);
        painter.setPen(arcPen);
        painter.drawPath(arcPath);

        QPainterPath arcPath2;
        const int angle2 = (spinnerAngle_ + 180) % 360;
        arcPath2.arcMoveTo(spinnerRect, angle2);
        arcPath2.arcTo(spinnerRect, angle2, 60.0);
        QPen arcPen2(QColor(52, 211, 153, 180));
        arcPen2.setWidthF(3.0);
        arcPen2.setCapStyle(Qt::RoundCap);
        painter.setPen(arcPen2);
        painter.drawPath(arcPath2);
    }

private:
    QString statusText_;
    QPixmap logoPixmap_;
    QTimer *spinnerTimer_ = nullptr;
    int spinnerAngle_ = 0;
};


QString baseAssetFromSymbol(QString symbol) {
    symbol = symbol.trimmed().toUpper();
    if (symbol.isEmpty()) {
        return QString();
    }
    if (symbol.contains('_')) {
        return symbol.section('_', 0, 0).trimmed().toUpper();
    }
    static const QStringList quoteAssets = {
        "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USD", "BTC", "ETH", "BNB",
        "EUR", "TRY", "GBP", "AUD", "BRL", "RUB", "IDR", "UAH", "ZAR", "BIDR", "PAX"
    };
    for (const auto &quote : quoteAssets) {
        if (symbol.endsWith(quote) && symbol.size() > quote.size()) {
            return symbol.left(symbol.size() - quote.size());
        }
    }
    return symbol;
}

QString formatQuantityWithSymbol(double quantity, const QString &symbol) {
    if (!qIsFinite(quantity)) {
        return QStringLiteral("-");
    }
    const QString baseAsset = baseAssetFromSymbol(symbol);
    const double absQty = std::fabs(quantity);
    int decimals = 6;
    if (absQty >= 100000.0) {
        decimals = 0;
    } else if (absQty >= 1000.0) {
        decimals = 3;
    }
    const QString qtyText = QLocale().toString(quantity, 'f', decimals);
    return baseAsset.isEmpty() ? qtyText : QStringLiteral("%1 %2").arg(qtyText, baseAsset);
}

QString formatPositionSizeText(double sizeUsdt, double quantity, const QString &symbol) {
    const QString usdtText = QStringLiteral("%1 USDT").arg(QString::number(std::max(0.0, sizeUsdt), 'f', 2));
    const QString qtyText = formatQuantityWithSymbol(quantity, symbol);
    if (qtyText == QStringLiteral("-")) {
        return usdtText;
    }
    return QStringLiteral("%1\n%2").arg(usdtText, qtyText);
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

QString recommendedConnectorKey(bool futures) {
    return futures ? kConnectorUsdsFutures : kConnectorSpot;
}

bool connectorAllowedForAccount(const QString &connectorKey, bool futures) {
    return futures ? kFuturesConnectorKeys.contains(connectorKey) : kSpotConnectorKeys.contains(connectorKey);
}

QString connectorLabelForKey(const QString &connectorKey) {
    for (const auto &option : kConnectorOptions) {
        if (option.key == connectorKey) {
            return option.label;
        }
    }
    return connectorKey.trimmed();
}

QVector<ConnectorOption> connectorOptionsForAccount(bool futures) {
    const QSet<QString> &allowed = futures ? kFuturesConnectorKeys : kSpotConnectorKeys;
    QVector<ConnectorOption> filtered;
    filtered.reserve(kConnectorOptions.size());
    for (const auto &option : kConnectorOptions) {
        if (allowed.contains(option.key)) {
            filtered.push_back(option);
        }
    }
    return filtered;
}

QString normalizeConnectorBackend(const QString &value) {
    const QString textRaw = value.trimmed();
    if (textRaw.isEmpty()) {
        return kConnectorUsdsFutures;
    }
    const QString text = textRaw.toLower();

    // Legacy C++ labels still supported when loading older rows/configs.
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

void rebuildDashboardConnectorComboForAccount(QComboBox *combo, bool futures, bool forceDefault = false) {
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
    const auto options = connectorOptionsForAccount(futures);
    for (const auto &option : options) {
        combo->addItem(option.label, option.key);
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

struct ConnectorRuntimeConfig {
    QString key;
    QString label;
    QString baseUrl;
    QString warning;
    QString error;

    bool ok() const {
        return error.trimmed().isEmpty();
    }
};

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

    // C++ runtime currently executes native Binance REST endpoints.
    // Community/SDK bridge options are mapped to native equivalents for compatibility.
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

QString existingFilePath(const QString &pathValue) {
    const QFileInfo info(QDir::cleanPath(pathValue.trimmed()));
    if (!info.exists() || !info.isFile()) {
        return QString();
    }
    const QString canonical = info.canonicalFilePath();
    return canonical.isEmpty() ? info.absoluteFilePath() : canonical;
}

QString findFirstExistingFile(const QStringList &rootCandidates, const QStringList &relativeCandidates) {
    for (const QString &rootPath : rootCandidates) {
        const QDir rootDir(rootPath);
        for (const QString &relativePath : relativeCandidates) {
            const QString resolved = existingFilePath(rootDir.filePath(relativePath));
            if (!resolved.isEmpty()) {
                return resolved;
            }
        }
    }
    return QString();
}

QString workspaceProjectRoot() {
    const QStringList roots = dependencyProjectRoots();
    for (const QString &rootPath : roots) {
        if (QFileInfo::exists(QDir(rootPath).filePath(QStringLiteral("Languages")))) {
            return rootPath;
        }
    }
    if (!roots.isEmpty()) {
        return roots.front();
    }
    return QDir::currentPath();
}

QString ensureWorkspaceDirectory(const QString &relativePath, QString *errorOut = nullptr) {
    const QString trimmed = relativePath.trimmed();
    if (trimmed.isEmpty()) {
        if (errorOut != nullptr) {
            *errorOut = QStringLiteral("Workspace path is empty.");
        }
        return QString();
    }
    const QString rootPath = workspaceProjectRoot();
    if (rootPath.trimmed().isEmpty()) {
        if (errorOut != nullptr) {
            *errorOut = QStringLiteral("Could not resolve the project root.");
        }
        return QString();
    }

    const QString absolutePath = QDir(rootPath).filePath(trimmed);
    QDir dir;
    if (!dir.mkpath(absolutePath)) {
        if (errorOut != nullptr) {
            *errorOut = QStringLiteral("Could not create workspace directory: %1").arg(QDir::cleanPath(absolutePath));
        }
        return QString();
    }
    return QDir::cleanPath(absolutePath);
}

QStringList pythonRuntimeRoots() {
    QStringList roots = dependencyProjectRoots();
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    appendUniquePath(roots, env.value(QStringLiteral("TB_PROJECT_ROOT")).trimmed(), true);
    return roots;
}

QStringList pythonInterpreterCandidatesForScript(const QString &scriptPath) {
    QStringList programs;
    const QFileInfo scriptInfo(scriptPath);
    const QDir scriptDir(scriptInfo.absolutePath());
    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();

    auto appendProgram = [&programs](const QString &candidate, bool searchPath = false) {
        QString resolved;
        if (searchPath) {
            resolved = QStandardPaths::findExecutable(candidate.trimmed());
        } else {
            resolved = existingFilePath(candidate);
        }
        if (resolved.isEmpty()) {
            return;
        }
        if (!programs.contains(resolved, Qt::CaseInsensitive)) {
            programs.push_back(resolved);
        }
    };

    appendProgram(scriptDir.filePath(QStringLiteral(".venv/Scripts/pythonw.exe")));
    appendProgram(scriptDir.filePath(QStringLiteral(".venv/Scripts/python.exe")));
    appendProgram(scriptDir.filePath(QStringLiteral(".venv/bin/python3")));
    appendProgram(scriptDir.filePath(QStringLiteral(".venv/bin/python")));
    appendProgram(env.value(QStringLiteral("PYTHON_EXECUTABLE")).trimmed());

#ifdef Q_OS_WIN
    appendProgram(QStringLiteral("pythonw.exe"), true);
    appendProgram(QStringLiteral("pythonw"), true);
    appendProgram(QStringLiteral("python.exe"), true);
    appendProgram(QStringLiteral("python"), true);
    appendProgram(QStringLiteral("py.exe"), true);
    appendProgram(QStringLiteral("py"), true);
#else
    appendProgram(QStringLiteral("python3"), true);
    appendProgram(QStringLiteral("python"), true);
#endif

    return programs;
}

QProcessEnvironment pythonLaunchEnvironment() {
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    env.insert(QStringLiteral("TB_CPP_EXE_DIR"), QCoreApplication::applicationDirPath());
    env.insert(QStringLiteral("TB_CPP_EXE_PATH"), QCoreApplication::applicationFilePath());
    env.remove(QStringLiteral("QT_PLUGIN_PATH"));
    env.remove(QStringLiteral("QT_QPA_PLATFORM_PLUGIN_PATH"));
    env.remove(QStringLiteral("QML_IMPORT_PATH"));
    env.remove(QStringLiteral("QML2_IMPORT_PATH"));
    env.remove(QStringLiteral("QT_CONF_PATH"));
    env.remove(QStringLiteral("QT_QPA_FONTDIR"));
    env.remove(QStringLiteral("QT_QPA_PLATFORMTHEME"));
    env.remove(QStringLiteral("QTWEBENGINEPROCESS_PATH"));
    env.remove(QStringLiteral("QTWEBENGINE_RESOURCES_PATH"));
    env.remove(QStringLiteral("QTWEBENGINE_LOCALES_PATH"));
    env.insert(QStringLiteral("BOT_DISABLE_SPLASH"), QStringLiteral("0"));
    if (env.value(QStringLiteral("TB_PROJECT_ROOT")).trimmed().isEmpty()) {
        const QStringList roots = pythonRuntimeRoots();
        for (const QString &rootPath : roots) {
            if (QFileInfo::exists(QDir(rootPath).filePath(QStringLiteral("Languages")))) {
                env.insert(QStringLiteral("TB_PROJECT_ROOT"), rootPath);
                break;
            }
        }
    }
    return env;
}

bool tryStartDetachedProgram(
    const QString &program,
    const QStringList &arguments,
    const QString &workingDirectory,
    const QProcessEnvironment &environment,
    QStringList *attemptsOut,
    const QString &label) {
    if (program.trimmed().isEmpty()) {
        return false;
    }
    qint64 pid = 0;
    QProcess process;
    process.setProgram(program);
    process.setArguments(arguments);
    process.setWorkingDirectory(workingDirectory);
    process.setProcessEnvironment(environment);
    const bool ok = process.startDetached(&pid);
    if (ok) {
        return true;
    }
    if (attemptsOut != nullptr) {
        const QString renderedArgs = arguments.isEmpty() ? QString() : QStringLiteral(" %1").arg(arguments.join(' '));
        const QString descriptor = label.trimmed().isEmpty()
            ? QStringLiteral("%1%2").arg(program, renderedArgs)
            : label.trimmed();
        attemptsOut->push_back(
            QStringLiteral("%1 (cwd: %2)").arg(descriptor, workingDirectory.trimmed().isEmpty() ? QDir::currentPath() : workingDirectory));
    }
    return false;
}

bool launchPythonRuntime(QString *errorOut = nullptr) {
    const QStringList roots = pythonRuntimeRoots();
    const QProcessEnvironment launchEnv = pythonLaunchEnvironment();
    QStringList failedAttempts;

    const QString hintedFrozenExe = existingFilePath(launchEnv.value(QStringLiteral("TB_PY_FROZEN_EXE")).trimmed());
    if (!hintedFrozenExe.isEmpty()) {
        const QFileInfo hintedInfo(hintedFrozenExe);
        if (tryStartDetachedProgram(
                hintedFrozenExe,
                {QStringLiteral("--direct")},
                hintedInfo.absolutePath(),
                launchEnv,
                &failedAttempts,
                QStringLiteral("Hinted Python runtime"))) {
            return true;
        }
    }

    const QString hintedSourceScript = existingFilePath(launchEnv.value(QStringLiteral("TB_PY_SOURCE_SCRIPT")).trimmed());
    const QString hintedSourcePython = existingFilePath(launchEnv.value(QStringLiteral("TB_PY_SOURCE_PYTHON")).trimmed());
    QString hintedSourceWorkdir = launchEnv.value(QStringLiteral("TB_PY_SOURCE_WORKDIR")).trimmed();
    if (hintedSourceWorkdir.isEmpty() && !hintedSourceScript.isEmpty()) {
        hintedSourceWorkdir = QFileInfo(hintedSourceScript).absolutePath();
    }
    if (!hintedSourceScript.isEmpty() && !hintedSourcePython.isEmpty()) {
        if (tryStartDetachedProgram(
                hintedSourcePython,
                {hintedSourceScript, QStringLiteral("--direct")},
                hintedSourceWorkdir,
                launchEnv,
                &failedAttempts,
                QStringLiteral("Hinted Python source runtime"))) {
            return true;
        }
    }

#ifdef Q_OS_WIN
    const QStringList packagedRelativeCandidates = {
        QStringLiteral("Trading-Bot-Python.exe"),
        QStringLiteral("Trading-Bot-Python-arm64.exe"),
        QStringLiteral("Binance-Trading-Bot.exe"),
        QStringLiteral("dist/Trading-Bot-Python.exe"),
        QStringLiteral("dist/Trading-Bot-Python-arm64.exe"),
        QStringLiteral("dist/Binance-Trading-Bot.exe"),
        QStringLiteral("Languages/Python/dist/Trading-Bot-Python.exe"),
        QStringLiteral("Languages/Python/dist/Trading-Bot-Python-arm64.exe"),
        QStringLiteral("Languages/Python/dist/Binance-Trading-Bot.exe"),
    };
#else
    const QStringList packagedRelativeCandidates = {
        QStringLiteral("Trading-Bot-Python"),
        QStringLiteral("dist/Trading-Bot-Python"),
        QStringLiteral("Languages/Python/dist/Trading-Bot-Python"),
    };
#endif

    const QString packagedRuntime = findFirstExistingFile(roots, packagedRelativeCandidates);
    if (!packagedRuntime.isEmpty()) {
        const QFileInfo packagedInfo(packagedRuntime);
        if (tryStartDetachedProgram(
                packagedRuntime,
                {QStringLiteral("--direct")},
                packagedInfo.absolutePath(),
                launchEnv,
                &failedAttempts,
                QStringLiteral("Packaged Python runtime"))) {
            return true;
        }
    }

    const QString scriptPath = findFirstExistingFile(roots, {QStringLiteral("Languages/Python/main.py")});
    if (!scriptPath.isEmpty()) {
        const QFileInfo scriptInfo(scriptPath);
        const QStringList interpreterCandidates = pythonInterpreterCandidatesForScript(scriptPath);
        for (const QString &program : interpreterCandidates) {
            QStringList arguments;
            const QString fileName = QFileInfo(program).fileName().trimmed().toLower();
            if (fileName == QStringLiteral("py") || fileName == QStringLiteral("py.exe")) {
                arguments << QStringLiteral("-3");
            }
            arguments << scriptPath << QStringLiteral("--direct");
            if (tryStartDetachedProgram(
                    program,
                    arguments,
                    scriptInfo.absolutePath(),
                    launchEnv,
                    &failedAttempts,
                    QStringLiteral("Python script runtime"))) {
                return true;
            }
        }
    }

    QString message = QStringLiteral(
        "Could not launch the Python runtime automatically.\n\n"
        "Looked for Trading-Bot-Python and Languages/Python/main.py with a local/system Python interpreter.");
    if (!failedAttempts.isEmpty()) {
        message += QStringLiteral("\n\nLaunch attempts:\n- %1").arg(failedAttempts.join(QStringLiteral("\n- ")));
    }
    if (errorOut != nullptr) {
        *errorOut = message;
    }
    return false;
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

} // namespace

TradingBotWindow::TradingBotWindow(QWidget *parent)
    : QMainWindow(parent),
      symbolList_(nullptr),
      intervalList_(nullptr),
      customIntervalEdit_(nullptr),
      statusLabel_(nullptr),
      botStatusLabel_(nullptr),
      botTimeLabel_(nullptr),
      backtestPnlActiveLabel_(nullptr),
      backtestPnlClosedLabel_(nullptr),
      runButton_(nullptr),
      stopButton_(nullptr),
      addSelectedBtn_(nullptr),
      addAllBtn_(nullptr),
      symbolSourceCombo_(nullptr),
      backtestRefreshSymbolsBtn_(nullptr),
      backtestSymbolIntervalTable_(nullptr),
      backtestConnectorCombo_(nullptr),
      backtestLoopCombo_(nullptr),
      backtestLeverageSpin_(nullptr),
      backtestStopLossEnableCheck_(nullptr),
      backtestStopLossModeCombo_(nullptr),
      backtestStopLossScopeCombo_(nullptr),
      backtestSideCombo_(nullptr),
      resultsTable_(nullptr),
      botTimer_(nullptr),
      tabs_(nullptr),
      backtestTab_(nullptr),
      dashboardThemeCombo_(nullptr),
      dashboardPage_(nullptr),
      dashboardTemplateCombo_(nullptr),
      dashboardMarginModeCombo_(nullptr),
      dashboardPositionModeCombo_(nullptr),
      dashboardPositionPctSpin_(nullptr),
      dashboardLeverageSpin_(nullptr),
      dashboardConnectorCombo_(nullptr),
      dashboardExchangeCombo_(nullptr),
      dashboardIndicatorSourceCombo_(nullptr),
      dashboardSignalFeedCombo_(nullptr),
      dashboardStartBtn_(nullptr),
      dashboardStopBtn_(nullptr),
      dashboardOverridesTable_(nullptr),
      dashboardAllLogsEdit_(nullptr),
      dashboardPositionLogsEdit_(nullptr),
      dashboardWaitingLogsEdit_(nullptr),
      dashboardWaitingQueueTable_(nullptr),
      dashboardRuntimeTimer_(nullptr),
      codePage_(nullptr),
      dashboardPaperBalanceTitleLabel_(nullptr),
      dashboardPaperBalanceSpin_(nullptr),
      dashboardPnlActiveLabel_(nullptr),
      dashboardPnlClosedLabel_(nullptr),
      dashboardBotStatusLabel_(nullptr),
      dashboardBotTimeLabel_(nullptr),
      codePnlActiveLabel_(nullptr),
      codePnlClosedLabel_(nullptr),
      codeBotStatusLabel_(nullptr),
      codeBotTimeLabel_(nullptr),
      chartMarketCombo_(nullptr),
      chartSymbolCombo_(nullptr),
      chartIntervalCombo_(nullptr),
      chartViewModeCombo_(nullptr),
      chartAutoFollowCheck_(nullptr),
      chartPnlActiveLabel_(nullptr),
      chartPnlClosedLabel_(nullptr),
      chartBotStatusLabel_(nullptr),
      chartBotTimeLabel_(nullptr),
      positionsPnlActiveLabel_(nullptr),
      positionsPnlClosedLabel_(nullptr),
      positionsTotalBalanceLabel_(nullptr),
      positionsAvailableBalanceLabel_(nullptr),
      positionsBotStatusLabel_(nullptr),
      positionsBotTimeLabel_(nullptr),
      positionsLastTotalBalanceUsdt_(std::numeric_limits<double>::quiet_NaN()),
      positionsLastAvailableBalanceUsdt_(std::numeric_limits<double>::quiet_NaN()),
      positionsViewCombo_(nullptr),
      positionsTable_(nullptr),
      dashboardLeadTraderEnableCheck_(nullptr),
      dashboardLeadTraderCombo_(nullptr),
      dashboardStopWithoutCloseCheck_(nullptr),
      dashboardStopLossEnableCheck_(nullptr),
      dashboardStopLossModeCombo_(nullptr),
      dashboardStopLossScopeCombo_(nullptr),
      dashboardStopLossUsdtSpin_(nullptr),
      dashboardStopLossPercentSpin_(nullptr),
      positionsAutoRowHeightCheck_(nullptr),
      positionsAutoColumnWidthCheck_(nullptr) {
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
    QWidget *chartTab = createChartTab();
    tabs_->addTab(chartTab, "Chart");
    tabs_->addTab(createPositionsTab(), "Positions");
    backtestTab_ = createBacktestTab();
    tabs_->addTab(backtestTab_, "Backtest");
    tabs_->addTab(createLiquidationHeatmapTab(), "Liquidation Heatmap");
    tabs_->addTab(createCodeTab(), "Code Languages");
    tabs_->setCurrentIndex(0);

    rootLayout->addWidget(tabs_);

    populateDefaults();
    wireSignals();

    // Warm up Chart/WebEngine once after startup to avoid first user click flicker.
    QTimer::singleShot(0, this, [this, chartTab]() {
        if (!tabs_ || !chartTab) {
            return;
        }
        const int chartIdx = tabs_->indexOf(chartTab);
        const int prevIdx = tabs_->currentIndex();
        if (chartIdx < 0 || prevIdx < 0 || chartIdx == prevIdx) {
            return;
        }
        {
            QSignalBlocker blocker(tabs_);
            tabs_->setCurrentIndex(chartIdx);
            QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
            tabs_->setCurrentIndex(prevIdx);
        }
        tabs_->update();
        update();
    });

    // Ensure the initial theme applies after all tabs/widgets exist.
    if (dashboardThemeCombo_) {
        applyDashboardTheme(dashboardThemeCombo_->currentText());
    }
    refreshPositionsSummaryLabels();

    // Align backtest symbol ordering/selection with Python logic (volume-sorted fetch at startup).
    QTimer::singleShot(0, this, [this]() {
        refreshBacktestSymbols();
    });

    // Force first-frame paint; some Windows/Qt builds can stay white until the first manual resize.
    QTimer::singleShot(0, this, [this]() {
        if (auto *cw = centralWidget()) {
            cw->update();
            cw->repaint();
        }
        update();
        repaint();
    });
}

QWidget *TradingBotWindow::createPlaceholderTab(const QString &title, const QString &body) {
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


QWidget *TradingBotWindow::createCodeTab() {
    auto *page = new QWidget(this);
    page->setObjectName("codePage");
    codePage_ = page;
    codePnlActiveLabel_ = nullptr;
    codePnlClosedLabel_ = nullptr;
    codeBotStatusLabel_ = nullptr;
    codeBotTimeLabel_ = nullptr;
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
        button->setObjectName("codeLangCardButton");
        button->setFlat(true);
        button->setCursor(disabled ? Qt::ArrowCursor : Qt::PointingHandCursor);
        button->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

        auto *card = new QFrame(button);
        card->setObjectName("codeLangCardSurface");
        card->setMinimumHeight(130);
        card->setMaximumHeight(150);
        card->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        if (!disabled) {
            button->setStyleSheet(QString(
                "QPushButton#codeLangCardButton { border: none; padding: 0; margin: 0; text-align: left; background: transparent; }"
                "QPushButton#codeLangCardButton:hover { background: transparent; border: none; }"
                "QPushButton#codeLangCardButton:pressed { background: transparent; border: none; }"
                "QPushButton#codeLangCardButton:focus { outline: none; }"
                "QPushButton#codeLangCardButton QFrame#codeLangCardSurface { border: 2px solid #1f2937; border-radius: 10px; background: #0d1117; padding: 8px; }"
                "QPushButton#codeLangCardButton:hover QFrame#codeLangCardSurface { border-color: %1; }"
                "QPushButton#codeLangCardButton:pressed QFrame#codeLangCardSurface { border-color: %1; background: #0f172a; }"
                "QPushButton#codeLangCardButton QLabel { color: #e6edf3; }")
                                     .arg(border));
        } else {
            button->setStyleSheet(
                "QPushButton#codeLangCardButton { border: none; padding: 0; margin: 0; text-align: left; background: transparent; }"
                "QPushButton#codeLangCardButton:hover { background: transparent; border: none; }"
                "QPushButton#codeLangCardButton:pressed { background: transparent; border: none; }"
                "QPushButton#codeLangCardButton:focus { outline: none; }"
                "QPushButton#codeLangCardButton QFrame#codeLangCardSurface { border: 2px solid #1f2937; border-radius: 10px; background: #0d1117; padding: 8px; }"
                "QPushButton#codeLangCardButton QLabel { color: #6b7280; }");
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
        btnLayout->setSpacing(0);
        btnLayout->addWidget(card);
        button->setMinimumHeight(card->minimumHeight());
        button->setMaximumHeight(card->maximumHeight());

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
                             if (QMessageBox::question(
                                     this,
                                     tr("Switch to Python?"),
                                     tr("This will close the current C++ trading bot window completely and open the Python trading bot instead.\n\nDo you want to continue?"),
                                     QMessageBox::Yes | QMessageBox::No,
                                     QMessageBox::No) != QMessageBox::Yes) {
                                 return;
                             }
                             auto *splash = new LanguageSwitchSplash(QStringLiteral("Launching Python runtime…"));
                             hide();
                             QString launchError;
                             if (!launchPythonRuntime(&launchError)) {
                                 splash->close();
                                 splash->deleteLater();
                                 showMaximized();
                                 raise();
                                 activateWindow();
                                 QMessageBox::warning(
                                     this,
                                     "Python runtime",
                                     launchError);
                                 return;
                             }
                             updateStatusMessage("Launching Python runtime...");
                             QTimer::singleShot(450, splash, [splash]() {
                                 splash->close();
                                 splash->deleteLater();
                             });
                             QTimer::singleShot(450, this, []() {
                                 QCoreApplication::quit();
                             });
                         }),
                makeCard("C++", "Qt native desktop (active)", "#2563eb", "Active", "#1f2937", false, [this]() {
                    if (tabs_ && backtestTab_) {
                        tabs_->setCurrentWidget(backtestTab_);
                    }
                    updateStatusMessage("C++ workspace active.");
                }),
                makeCard("Rust", "Desktop Cargo workspace", "#fb923c", "Scaffold", "#7c2d12", false, [this]() {
                    QString workspaceError;
                    const QString rustWorkspace = ensureWorkspaceDirectory(QStringLiteral("Languages/Rust"), &workspaceError);
                    if (rustWorkspace.isEmpty()) {
                        QMessageBox::warning(this, "Rust workspace", workspaceError);
                        return;
                    }
                    const bool opened = QDesktopServices::openUrl(QUrl::fromLocalFile(rustWorkspace));
                    if (!opened) {
                        QMessageBox::information(
                            this,
                            "Rust workspace",
                            QStringLiteral("Rust workspace prepared at:\n%1").arg(rustWorkspace));
                    }
                    updateStatusMessage(QStringLiteral("Rust workspace ready: %1").arg(rustWorkspace));
                })});

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
        const auto isNativeClientRow = [](const QString &name) {
            const QString key = name.trimmed().toLower();
            return key == QStringLiteral("binance rest client (native)")
                || key == QStringLiteral("binance websocket client (native)");
        };
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
                return QStringLiteral("Unknown");
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
                return QStringLiteral("Unknown");
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
                    const bool nativeClientRow = isNativeClientRow(name);
                    const QString installedLowerInitial = installed.toLower();
                    const QString latestLowerInitial = latest.toLower();

                    if (nativeClientRow
                        && (installedLowerInitial == QStringLiteral("installed")
                            || installedLowerInitial == QStringLiteral("active")
                            || isMissingVersionMarker(installed))) {
                        const QString repairedInstalled = resolveInstalledFromLabel(name);
                        if (!isMissingVersionMarker(repairedInstalled)
                            && repairedInstalled.compare(QStringLiteral("Installed"), Qt::CaseInsensitive) != 0
                            && repairedInstalled.compare(QStringLiteral("Active"), Qt::CaseInsensitive) != 0) {
                            installed = repairedInstalled;
                        }
                    } else if (isMissingVersionMarker(installed)) {
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
                         || isMissingVersionMarker(latest)
                         || (nativeClientRow && (latestLowerInitial == QStringLiteral("installed")
                                                 || latestLowerInitial == QStringLiteral("active"))))
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
        QString nativeClientVersion = releaseTagFromMetadataDirs();
        if (isMissingVersionMarker(nativeClientVersion)) {
            nativeClientVersion = QStringLiteral("Unknown");
        }

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
             nativeClientVersion,
             nativeClientVersion},
            {QStringLiteral("Binance WebSocket client (native)"),
             nativeClientVersion,
             nativeClientVersion},
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
    codePnlActiveLabel_ = new QLabel("Total PNL Active Positions: --", container);
    codePnlClosedLabel_ = new QLabel("Total PNL Closed Positions: --", container);
    codeBotStatusLabel_ = new QLabel("Bot Status: OFF", container);
    codeBotStatusLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
    codeBotTimeLabel_ = new QLabel("Bot Active Time: --", container);
    codeBotTimeLabel_->setStyleSheet("color: #cbd5e1;");
    statusRow->addWidget(codePnlActiveLabel_);
    statusRow->addSpacing(18);
    statusRow->addWidget(codePnlClosedLabel_);
    statusRow->addStretch();
    statusRow->addWidget(codeBotStatusLabel_);
    statusRow->addSpacing(18);
    statusRow->addWidget(codeBotTimeLabel_);
    layout->addLayout(statusRow);

    layout->addStretch();
    return page;
}




