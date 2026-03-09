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

bool isTestnetModeLabel(const QString &modeText) {
    const QString modeNorm = modeText.trimmed().toLower();
    return modeNorm == QStringLiteral("demo")
        || modeNorm.contains("testnet")
        || modeNorm == QStringLiteral("test")
        || modeNorm.contains("sandbox")
        || modeNorm.contains("binance demo");
}

bool isPaperTradingModeLabel(const QString &modeText) {
    const QString modeNorm = modeText.trimmed().toLower();
    if (isTestnetModeLabel(modeText)) {
        return false;
    }
    return modeNorm == QStringLiteral("paper")
        || modeNorm == QStringLiteral("paper local")
        || modeNorm.contains("paper local")
        || modeNorm.contains("paper trading");
}

QString normalizedIndicatorSourceKey(const QString &sourceText) {
    const QString sourceNorm = sourceText.trimmed().toLower();
    if (sourceNorm.contains(QStringLiteral("binance futures"))) {
        return QStringLiteral("binance_futures");
    }
    if (sourceNorm.contains(QStringLiteral("binance spot"))) {
        return QStringLiteral("binance_spot");
    }
    if (sourceNorm.contains(QStringLiteral("tradingview"))) {
        return QStringLiteral("tradingview");
    }
    if (sourceNorm.contains(QStringLiteral("bybit"))) {
        return QStringLiteral("bybit");
    }
    if (sourceNorm.contains(QStringLiteral("coinbase"))) {
        return QStringLiteral("coinbase");
    }
    if (sourceNorm.contains(QStringLiteral("okx"))) {
        return QStringLiteral("okx");
    }
    if (sourceNorm.contains(QStringLiteral("gate"))) {
        return QStringLiteral("gate");
    }
    if (sourceNorm.contains(QStringLiteral("bitget"))) {
        return QStringLiteral("bitget");
    }
    if (sourceNorm.contains(QStringLiteral("mexc"))) {
        return QStringLiteral("mexc");
    }
    if (sourceNorm.contains(QStringLiteral("kucoin"))) {
        return QStringLiteral("kucoin");
    }
    if (sourceNorm.contains(QStringLiteral("htx"))) {
        return QStringLiteral("htx");
    }
    if (sourceNorm.contains(QStringLiteral("kraken"))) {
        return QStringLiteral("kraken");
    }
    return sourceNorm;
}

QString normalizedSignalFeedKey(const QString &feedText) {
    const QString feedNorm = feedText.trimmed().toLower();
    if (feedNorm.contains(QStringLiteral("websocket")) || feedNorm.contains(QStringLiteral("stream"))) {
        return QStringLiteral("websocket");
    }
    return QStringLiteral("rest");
}

bool strategyUsesLiveCandles(const QString &summary) {
    return summary.trimmed().toLower().contains(QStringLiteral("live candles"));
}

struct LivePositionMetricsShare {
    double sizeUsdt = 0.0;
    double displayMarginUsdt = 0.0;
    double roiBasisUsdt = 0.0;
    double pnlUsdt = 0.0;
};

double livePositionTotalDisplayMargin(const BinanceRestClient::FuturesPosition *livePos, double fallback) {
    if (!livePos) {
        return fallback;
    }
    const QList<double> candidates = {
        livePos->isolatedWallet,
        livePos->isolatedMargin,
        livePos->positionInitialMargin,
        livePos->initialMargin,
        fallback,
    };
    for (double value : candidates) {
        if (qIsFinite(value) && value > 0.0) {
            return value;
        }
    }
    return fallback;
}

double livePositionTotalRoiBasis(const BinanceRestClient::FuturesPosition *livePos, double fallback) {
    if (!livePos) {
        return fallback;
    }
    const QList<double> candidates = {
        livePos->positionInitialMargin,
        livePos->initialMargin,
        fallback,
        livePos->isolatedWallet,
        livePos->isolatedMargin,
    };
    for (double value : candidates) {
        if (qIsFinite(value) && value > 0.0) {
            return value;
        }
    }
    return fallback;
}

LivePositionMetricsShare allocateLivePositionShare(
    const BinanceRestClient::FuturesPosition *livePos,
    double rowQty,
    double localGroupQty,
    double fallbackSizeUsdt,
    double fallbackDisplayMarginUsdt,
    double fallbackRoiBasisUsdt,
    double fallbackPnlUsdt) {
    LivePositionMetricsShare share;
    share.sizeUsdt = fallbackSizeUsdt;
    share.displayMarginUsdt = fallbackDisplayMarginUsdt;
    share.roiBasisUsdt = fallbackRoiBasisUsdt;
    share.pnlUsdt = fallbackPnlUsdt;
    if (!livePos || !qIsFinite(rowQty) || rowQty <= 0.0) {
        return share;
    }

    const double liveQtyAbs = std::fabs(livePos->positionAmt);
    double shareRatio = 0.0;
    if (qIsFinite(localGroupQty) && localGroupQty > 1e-10) {
        shareRatio = rowQty / localGroupQty;
    } else if (qIsFinite(liveQtyAbs) && liveQtyAbs > 1e-10) {
        shareRatio = rowQty / liveQtyAbs;
    }
    if (!qIsFinite(shareRatio) || shareRatio <= 0.0) {
        return share;
    }
    shareRatio = std::min(1.0, std::max(0.0, shareRatio));

    const double totalSizeUsdt = (qIsFinite(livePos->notional) && std::fabs(livePos->notional) > 0.0)
        ? std::fabs(livePos->notional)
        : fallbackSizeUsdt;
    const double totalDisplayMarginUsdt = livePositionTotalDisplayMargin(livePos, fallbackDisplayMarginUsdt);
    const double totalRoiBasisUsdt = livePositionTotalRoiBasis(livePos, fallbackRoiBasisUsdt);
    const double totalPnlUsdt = qIsFinite(livePos->unrealizedProfit) ? livePos->unrealizedProfit : fallbackPnlUsdt;

    share.sizeUsdt = totalSizeUsdt * shareRatio;
    share.displayMarginUsdt = totalDisplayMarginUsdt * shareRatio;
    share.roiBasisUsdt = totalRoiBasisUsdt * shareRatio;
    share.pnlUsdt = totalPnlUsdt * shareRatio;
    return share;
}

bool qtWebSocketsRuntimeAvailable() {
    const QDir appDir(QCoreApplication::applicationDirPath());
    const bool hasQtWebSocketsDll = QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSockets.dll")))
        || QFileInfo::exists(appDir.filePath(QStringLiteral("Qt6WebSocketsd.dll")));
    return (HAS_QT_WEBSOCKETS != 0) && hasQtWebSocketsDll;
}

QVector<BinanceRestClient::KlineCandle> signalCandlesFromSnapshot(
    QVector<BinanceRestClient::KlineCandle> candles,
    bool useLiveCandles,
    bool latestCandleClosed) {
    if (candles.isEmpty()) {
        return candles;
    }
    if (!useLiveCandles && !latestCandleClosed && candles.size() > 1) {
        candles.removeLast();
    }
    return candles;
}

QString normalizedIndicatorKey(QString indicatorName) {
    indicatorName = indicatorName.toLower();
    indicatorName.replace(" ", "").replace("(", "").replace(")", "").replace("%", "").replace("-", "").replace("_", "");
    if (indicatorName.contains("stochrsi") || indicatorName.contains("stochasticrsi")) {
        return QStringLiteral("stoch_rsi");
    }
    if (indicatorName.contains("stochastic")) {
        return QStringLiteral("stochastic");
    }
    if (indicatorName.contains("movingaverage")) {
        return QStringLiteral("ma");
    }
    if (indicatorName.contains("donchian")) {
        return QStringLiteral("donchian");
    }
    if (indicatorName.contains("psar")) {
        return QStringLiteral("psar");
    }
    if (indicatorName.contains("bollinger")) {
        return QStringLiteral("bb");
    }
    if (indicatorName.contains("relative") || indicatorName.contains("rsi")) {
        return QStringLiteral("rsi");
    }
    if (indicatorName.contains("volume")) {
        return QStringLiteral("volume");
    }
    if (indicatorName.contains("willr") || indicatorName.contains("williams")) {
        return QStringLiteral("willr");
    }
    if (indicatorName.contains("macd")) {
        return QStringLiteral("macd");
    }
    if (indicatorName.contains("ultimate")) {
        return QStringLiteral("uo");
    }
    if (indicatorName.contains("adx")) {
        return QStringLiteral("adx");
    }
    if (indicatorName.contains("dmi")) {
        return QStringLiteral("dmi");
    }
    if (indicatorName.contains("supertrend")) {
        return QStringLiteral("supertrend");
    }
    if (indicatorName.contains("ema")) {
        return QStringLiteral("ema");
    }
    return QStringLiteral("generic");
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

#if HAS_QT_WEBENGINE
class ResizeAwareWebEngineView final : public QWebEngineView {
public:
    explicit ResizeAwareWebEngineView(QWidget *parent = nullptr)
        : QWebEngineView(parent) {
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    }

    void setResizeCallback(std::function<void()> callback) {
        resizeCallback_ = std::move(callback);
    }

protected:
    void showEvent(QShowEvent *event) override {
        QWebEngineView::showEvent(event);
        notifyResize();
    }

    void resizeEvent(QResizeEvent *event) override {
        QWebEngineView::resizeEvent(event);
        notifyResize();
    }

private:
    void notifyResize() {
        if (resizeCallback_) {
            resizeCallback_();
        }
    }

    std::function<void()> resizeCallback_;
};
#endif

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
    static const QStringList quoteAssets = {
        "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USD", "BTC", "ETH", "BNB",
        "EUR", "TRY", "GBP", "AUD", "BRL", "RUB", "IDR", "UAH", "ZAR", "BIDR", "PAX"
    };
    if (symbol.contains('_')) {
        return symbol;
    }
    for (const auto &quote : quoteAssets) {
        if (symbol.endsWith(quote) && symbol.size() > quote.size()) {
            return symbol.left(symbol.size() - quote.size()) + "_" + quote;
        }
    }
    return symbol;
}

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

QString runtimeKeyFor(const QString &symbol, const QString &interval, const QString &connectorToken = QString()) {
    return symbol.trimmed().toUpper()
        + "|"
        + interval.trimmed().toLower()
        + "|"
        + connectorToken.trimmed().toLower();
}

bool loopTextRequestsInstant(QString loopText) {
    loopText = loopText.trimmed().toLower();
    return loopText == QStringLiteral("instant")
        || loopText == QStringLiteral("now")
        || loopText == QStringLiteral("realtime")
        || loopText == QStringLiteral("real-time");
}

qint64 loopSecondsFromText(QString loopText) {
    loopText = loopText.trimmed().toLower();
    if (loopTextRequestsInstant(loopText)) {
        return 0;
    }
    if (loopText.isEmpty() || loopText == "off" || loopText == "auto") {
        return 60;
    }

    static const QRegularExpression compactRe(QStringLiteral("^(\\d+)\\s*([smhdw])$"));
    QRegularExpressionMatch compactMatch = compactRe.match(loopText);
    if (compactMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = compactMatch.captured(1).toLongLong(&ok);
        if (ok && value > 0) {
            const QString unit = compactMatch.captured(2);
            if (unit == "s") return value;
            if (unit == "m") return value * 60;
            if (unit == "h") return value * 3600;
            if (unit == "d") return value * 86400;
            if (unit == "w") return value * 604800;
        }
    }

    static const QRegularExpression longRe(
        QStringLiteral("(\\d+)\\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|h|day|days|d|week|weeks|w)"));
    QRegularExpressionMatch longMatch = longRe.match(loopText);
    if (longMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = longMatch.captured(1).toLongLong(&ok);
        if (ok && value > 0) {
            const QString unit = longMatch.captured(2);
            if (unit.startsWith("s")) return value;
            if (unit.startsWith("m")) return value * 60;
            if (unit.startsWith("h")) return value * 3600;
            if (unit.startsWith("d")) return value * 86400;
            if (unit.startsWith("w")) return value * 604800;
        }
    }

    return 60;
}

int dashboardRuntimePollIntervalMs(const QTableWidget *table, bool useWebSocketFeed) {
    constexpr int kDefaultPollMs = 1500;
    constexpr int kInstantPollMs = 1000;
    constexpr int kInstantWsPollMs = 250;
    if (!table) {
        return kDefaultPollMs;
    }
    bool hasInstant = false;
    for (int row = 0; row < table->rowCount(); ++row) {
        const QTableWidgetItem *loopItem = table->item(row, 3);
        if (loopItem && loopTextRequestsInstant(loopItem->text())) {
            hasInstant = true;
            break;
        }
    }
    if (!hasInstant) {
        return kDefaultPollMs;
    }
    return useWebSocketFeed ? kInstantWsPollMs : kInstantPollMs;
}

void clearRuntimeSignalSockets(QMap<QString, BinanceWsClient *> &sockets) {
    for (auto it = sockets.cbegin(); it != sockets.cend(); ++it) {
        BinanceWsClient *client = it.value();
        if (!client) {
            continue;
        }
        client->disconnectFromStream();
        client->deleteLater();
    }
    sockets.clear();
}

qint64 intervalTokenToSeconds(QString intervalText) {
    intervalText = intervalText.trimmed().toLower();
    if (intervalText.isEmpty()) {
        return 0;
    }
    static const QRegularExpression compactRe(QStringLiteral("^(\\d+)\\s*(s|m|h|d|w|mo)$"));
    QRegularExpressionMatch compactMatch = compactRe.match(intervalText);
    if (!compactMatch.hasMatch()) {
        static const QRegularExpression longRe(
            QStringLiteral("^(\\d+)\\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|h|day|days|d|week|weeks|w|month|months|mo)$"));
        compactMatch = longRe.match(intervalText);
    }
    if (compactMatch.hasMatch()) {
        bool ok = false;
        const qint64 value = compactMatch.captured(1).toLongLong(&ok);
        if (!ok || value <= 0) {
            return 0;
        }
        const QString unit = compactMatch.captured(2).toLower();
        if (unit == "s" || unit == "sec" || unit == "second" || unit == "seconds") return value;
        if (unit == "m" || unit == "min" || unit == "minute" || unit == "minutes") return value * 60;
        if (unit == "h" || unit == "hour" || unit == "hours") return value * 3600;
        if (unit == "d" || unit == "day" || unit == "days") return value * 86400;
        if (unit == "w" || unit == "week" || unit == "weeks") return value * 604800;
        if (unit == "mo" || unit == "month" || unit == "months") return value * 2592000;
    }
    return 0;
}

QString intervalFloorToBinanceToken(qint64 seconds) {
    static const QVector<QPair<qint64, QString>> kSupported = {
        {60, QStringLiteral("1m")},
        {180, QStringLiteral("3m")},
        {300, QStringLiteral("5m")},
        {900, QStringLiteral("15m")},
        {1800, QStringLiteral("30m")},
        {3600, QStringLiteral("1h")},
        {7200, QStringLiteral("2h")},
        {14400, QStringLiteral("4h")},
        {21600, QStringLiteral("6h")},
        {28800, QStringLiteral("8h")},
        {43200, QStringLiteral("12h")},
        {86400, QStringLiteral("1d")},
        {259200, QStringLiteral("3d")},
        {604800, QStringLiteral("1w")},
        {2592000, QStringLiteral("1M")},
    };
    if (seconds <= 0) {
        return QStringLiteral("1m");
    }
    QString best = kSupported.first().second;
    for (const auto &entry : kSupported) {
        if (seconds < entry.first) {
            break;
        }
        best = entry.second;
    }
    return best;
}

QString normalizeBinanceKlineInterval(QString intervalText, QString *warningOut = nullptr) {
    const QString original = intervalText.trimmed();
    if (warningOut) {
        warningOut->clear();
    }
    if (original.isEmpty()) {
        return original;
    }
    if (original == QStringLiteral("1M")) {
        return QStringLiteral("1M");
    }

    const QString lower = original.toLower();
    static const QSet<QString> kSupportedLower = {
        QStringLiteral("1m"),
        QStringLiteral("3m"),
        QStringLiteral("5m"),
        QStringLiteral("15m"),
        QStringLiteral("30m"),
        QStringLiteral("1h"),
        QStringLiteral("2h"),
        QStringLiteral("4h"),
        QStringLiteral("6h"),
        QStringLiteral("8h"),
        QStringLiteral("12h"),
        QStringLiteral("1d"),
        QStringLiteral("3d"),
        QStringLiteral("1w"),
    };
    if (kSupportedLower.contains(lower)) {
        return lower;
    }
    if (lower == QStringLiteral("1mo")
        || lower == QStringLiteral("1month")
        || lower == QStringLiteral("1months")) {
        return QStringLiteral("1M");
    }

    const qint64 seconds = intervalTokenToSeconds(lower);
    if (seconds <= 0) {
        return original;
    }
    const QString fallback = intervalFloorToBinanceToken(seconds);
    if (warningOut && fallback.compare(original, Qt::CaseInsensitive) != 0) {
        *warningOut = QStringLiteral("Interval '%1' is not supported by Binance REST; using '%2' fallback.")
                          .arg(original, fallback);
    }
    return fallback;
}

constexpr double kWaitingPositionLateThresholdSec = 45.0;

double latestRsiValue(const QVector<BinanceRestClient::KlineCandle> &candles, int period, bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    if (period <= 0 || candles.size() <= period) {
        return 0.0;
    }

    double gains = 0.0;
    double losses = 0.0;
    for (int i = 1; i <= period; ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            return 0.0;
        }
        if (diff >= 0.0) {
            gains += diff;
        } else {
            losses += -diff;
        }
    }
    double avgGain = gains / period;
    double avgLoss = losses / period;

    for (int i = period + 1; i < candles.size(); ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            return 0.0;
        }
        const double gain = diff > 0.0 ? diff : 0.0;
        const double loss = diff < 0.0 ? -diff : 0.0;
        avgGain = ((avgGain * (period - 1)) + gain) / period;
        avgLoss = ((avgLoss * (period - 1)) + loss) / period;
    }

    if (avgLoss <= 1e-12) {
        if (okOut) {
            *okOut = true;
        }
        return 100.0;
    }
    const double rs = avgGain / avgLoss;
    const double rsi = 100.0 - (100.0 / (1.0 + rs));
    if (okOut) {
        *okOut = qIsFinite(rsi);
    }
    return qIsFinite(rsi) ? rsi : 0.0;
}

QSet<QString> parseIndicatorKeysFromSummary(const QString &summary) {
    QSet<QString> keys;
    const QString text = summary.trimmed();
    if (text.isEmpty()) {
        return keys;
    }

    const QStringList parts = text.split(',', Qt::SkipEmptyParts);
    for (const QString &raw : parts) {
        const QString segment = raw.trimmed();
        if (segment.isEmpty()) {
            continue;
        }
        const QString lower = segment.toLower();
        if (lower == QStringLiteral("none") || lower == QStringLiteral("default")) {
            continue;
        }
        const QString key = normalizedIndicatorKey(segment);
        if (!key.isEmpty() && key != QStringLiteral("generic")) {
            keys.insert(key);
        }
    }

    const QString lower = text.toLower();
    if (lower.contains(QStringLiteral("relative strength index"))) {
        keys.insert(QStringLiteral("rsi"));
    }
    if (lower.contains(QStringLiteral("stochastic rsi"))
        || lower.contains(QStringLiteral("stoch rsi"))
        || lower.contains(QStringLiteral("stoch_rsi"))
        || lower.contains(QStringLiteral("stochrsi"))) {
        keys.insert(QStringLiteral("stoch_rsi"));
    }
    if (lower.contains(QStringLiteral("williams"))
        || lower.contains(QStringLiteral("willr"))
        || lower.contains(QStringLiteral("%r"))) {
        keys.insert(QStringLiteral("willr"));
    }

    if (keys.isEmpty()
        && lower.contains(QStringLiteral("rsi"))
        && !lower.contains(QStringLiteral("stoch"))) {
        keys.insert(QStringLiteral("rsi"));
    }

    return keys;
}

QVector<double> computeRsiSeries(const QVector<BinanceRestClient::KlineCandle> &candles, int period) {
    QVector<double> out(candles.size(), qQNaN());
    if (period <= 0 || candles.size() <= period) {
        return out;
    }

    double gains = 0.0;
    double losses = 0.0;
    for (int i = 1; i <= period; ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            return out;
        }
        if (diff >= 0.0) {
            gains += diff;
        } else {
            losses += -diff;
        }
    }

    double avgGain = gains / period;
    double avgLoss = losses / period;

    auto toRsi = [](double gain, double loss) -> double {
        if (loss <= 1e-12) {
            return 100.0;
        }
        const double rs = gain / loss;
        const double rsi = 100.0 - (100.0 / (1.0 + rs));
        return qIsFinite(rsi) ? rsi : qQNaN();
    };

    out[period] = toRsi(avgGain, avgLoss);
    for (int i = period + 1; i < candles.size(); ++i) {
        const double diff = candles.at(i).close - candles.at(i - 1).close;
        if (!qIsFinite(diff)) {
            continue;
        }
        const double gain = diff > 0.0 ? diff : 0.0;
        const double loss = diff < 0.0 ? -diff : 0.0;
        avgGain = ((avgGain * (period - 1)) + gain) / period;
        avgLoss = ((avgLoss * (period - 1)) + loss) / period;
        out[i] = toRsi(avgGain, avgLoss);
    }
    return out;
}

double latestFiniteValue(const QVector<double> &values, bool *okOut = nullptr) {
    for (int i = values.size() - 1; i >= 0; --i) {
        const double v = values.at(i);
        if (qIsFinite(v)) {
            if (okOut) {
                *okOut = true;
            }
            return v;
        }
    }
    if (okOut) {
        *okOut = false;
    }
    return 0.0;
}

double latestStochRsiValue(
    const QVector<BinanceRestClient::KlineCandle> &candles,
    int length,
    int smoothK,
    int /*smoothD*/,
    bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    length = std::max(2, length);
    smoothK = std::max(1, smoothK);
    if (candles.size() <= (length + smoothK)) {
        return 0.0;
    }

    const QVector<double> rsiSeries = computeRsiSeries(candles, length);
    if (rsiSeries.isEmpty()) {
        return 0.0;
    }

    QVector<double> raw(rsiSeries.size(), qQNaN());
    for (int i = length - 1; i < rsiSeries.size(); ++i) {
        const int start = std::max(0, i - length + 1);
        double minV = std::numeric_limits<double>::infinity();
        double maxV = -std::numeric_limits<double>::infinity();
        int valid = 0;
        for (int j = start; j <= i; ++j) {
            const double v = rsiSeries.at(j);
            if (!qIsFinite(v)) {
                continue;
            }
            minV = std::min(minV, v);
            maxV = std::max(maxV, v);
            ++valid;
        }
        const double current = rsiSeries.at(i);
        if (valid < length || !qIsFinite(current)) {
            continue;
        }
        const double denom = maxV - minV;
        if (!qIsFinite(denom) || denom <= 1e-12) {
            raw[i] = 50.0;
            continue;
        }
        raw[i] = ((current - minV) / denom) * 100.0;
    }

    QVector<double> smooth(raw.size(), qQNaN());
    for (int i = smoothK - 1; i < raw.size(); ++i) {
        double sum = 0.0;
        int valid = 0;
        for (int j = i - smoothK + 1; j <= i; ++j) {
            const double v = raw.at(j);
            if (!qIsFinite(v)) {
                continue;
            }
            sum += v;
            ++valid;
        }
        if (valid < smoothK) {
            continue;
        }
        smooth[i] = sum / smoothK;
    }

    return latestFiniteValue(smooth, okOut);
}

double latestWilliamsRValue(const QVector<BinanceRestClient::KlineCandle> &candles, int length, bool *okOut = nullptr) {
    if (okOut) {
        *okOut = false;
    }
    length = std::max(2, length);
    if (candles.size() < length) {
        return 0.0;
    }

    const int start = candles.size() - length;
    double highest = -std::numeric_limits<double>::infinity();
    double lowest = std::numeric_limits<double>::infinity();
    for (int i = start; i < candles.size(); ++i) {
        const auto &c = candles.at(i);
        if (!qIsFinite(c.high) || !qIsFinite(c.low)) {
            return 0.0;
        }
        highest = std::max(highest, c.high);
        lowest = std::min(lowest, c.low);
    }
    const double close = candles.constLast().close;
    if (!qIsFinite(highest) || !qIsFinite(lowest) || !qIsFinite(close)) {
        return 0.0;
    }
    const double range = highest - lowest;
    if (range <= 1e-12) {
        if (okOut) {
            *okOut = true;
        }
        return -50.0;
    }
    double wr = -100.0 * ((highest - close) / range);
    wr = std::max(-100.0, std::min(0.0, wr));
    if (okOut) {
        *okOut = qIsFinite(wr);
    }
    return qIsFinite(wr) ? wr : 0.0;
}

QString indicatorDisplayName(const QString &key) {
    const QString normalized = key.trimmed().toLower();
    if (normalized == QStringLiteral("rsi")) {
        return QStringLiteral("RSI");
    }
    if (normalized == QStringLiteral("stoch_rsi")) {
        return QStringLiteral("StochRSI");
    }
    if (normalized == QStringLiteral("willr")) {
        return QStringLiteral("Williams %R");
    }
    return normalized.toUpper();
}

bool strategyAllowsLong(const QString &summary) {
    const QString s = summary.trimmed().toLower();
    if (s.contains("both")) {
        return true;
    }
    if (s.contains("short") && !s.contains("long")) {
        return false;
    }
    return true;
}

bool strategyAllowsShort(const QString &summary) {
    const QString s = summary.trimmed().toLower();
    if (s.contains("both")) {
        return true;
    }
    if (s.contains("long") && !s.contains("short")) {
        return false;
    }
    return true;
}

double firstNumberInText(const QString &text, bool *okOut = nullptr) {
    static const QRegularExpression numRe(QStringLiteral("[-+]?\\d+(?:\\.\\d+)?"));
    QRegularExpressionMatch m = numRe.match(text);
    if (!m.hasMatch()) {
        if (okOut) {
            *okOut = false;
        }
        return 0.0;
    }
    bool ok = false;
    const double value = m.captured(0).toDouble(&ok);
    if (okOut) {
        *okOut = ok;
    }
    return ok ? value : 0.0;
}

double normalizeFuturesOrderQuantity(
    double desiredQty,
    double markPrice,
    const BinanceRestClient::FuturesSymbolFilters &filters) {
    if (!qIsFinite(desiredQty) || desiredQty <= 0.0 || !qIsFinite(markPrice) || markPrice <= 0.0) {
        return 0.0;
    }

    const double minQty = (qIsFinite(filters.minQty) && filters.minQty > 0.0) ? filters.minQty : 0.0;
    const double maxQty = (qIsFinite(filters.maxQty) && filters.maxQty > 0.0) ? filters.maxQty : 0.0;
    const double minNotionalQty = (qIsFinite(filters.minNotional) && filters.minNotional > 0.0)
        ? (filters.minNotional / markPrice)
        : 0.0;
    const double requiredQty = std::max(minQty, minNotionalQty);
    double qty = std::max(desiredQty, requiredQty);
    if (maxQty > 0.0) {
        qty = std::min(qty, maxQty);
    }

    const double step = (qIsFinite(filters.stepSize) && filters.stepSize > 0.0) ? filters.stepSize : 0.0;
    if (step > 0.0) {
        qty = std::ceil((qty / step) - 1e-12) * step;
    }

    if (maxQty > 0.0 && qty > maxQty) {
        if (step > 0.0) {
            qty = std::floor((maxQty / step) + 1e-12) * step;
        } else {
            qty = maxQty;
        }
    }

    const int precision = std::max(0, std::min(16, filters.quantityPrecision));
    if (precision > 0) {
        const double scale = std::pow(10.0, precision);
        qty = std::ceil((qty * scale) - 1e-9) / scale;
    }

    if (step > 0.0) {
        qty = std::ceil((qty / step) - 1e-12) * step;
    }

    if (!qIsFinite(qty) || qty <= 0.0) {
        return 0.0;
    }

    if (requiredQty > 0.0 && qty + 1e-12 < requiredQty) {
        return 0.0;
    }
    return qty;
}

double floorToOrderStep(double qty, double step, int precisionHint) {
    if (!qIsFinite(qty) || qty <= 0.0) {
        return 0.0;
    }

    double normalized = qty;
    if (qIsFinite(step) && step > 0.0) {
        normalized = std::floor((normalized / step) + 1e-12) * step;
    }

    const int precision = std::max(0, std::min(16, precisionHint));
    if (precision > 0) {
        const double scale = std::pow(10.0, precision);
        normalized = std::floor((normalized * scale) + 1e-9) / scale;
    }

    if (qIsFinite(step) && step > 0.0) {
        normalized = std::floor((normalized / step) + 1e-12) * step;
    }

    return (qIsFinite(normalized) && normalized > 0.0) ? normalized : 0.0;
}

double normalizePriceToTick(double price, double tickSize, int precisionHint, bool roundUp) {
    if (!qIsFinite(price) || price <= 0.0) {
        return 0.0;
    }

    double normalized = price;
    if (qIsFinite(tickSize) && tickSize > 0.0) {
        normalized = roundUp
            ? (std::ceil((normalized / tickSize) - 1e-12) * tickSize)
            : (std::floor((normalized / tickSize) + 1e-12) * tickSize);
    }

    const int precision = std::max(0, std::min(16, precisionHint));
    if (precision > 0) {
        const double scale = std::pow(10.0, precision);
        normalized = roundUp
            ? (std::ceil((normalized * scale) - 1e-9) / scale)
            : (std::floor((normalized * scale) + 1e-9) / scale);
    }

    if (qIsFinite(tickSize) && tickSize > 0.0) {
        normalized = roundUp
            ? (std::ceil((normalized / tickSize) - 1e-12) * tickSize)
            : (std::floor((normalized / tickSize) + 1e-12) * tickSize);
    }

    return (qIsFinite(normalized) && normalized > 0.0) ? normalized : 0.0;
}

bool isPercentPriceFilterError(const QString &errorText) {
    const QString err = errorText.trimmed().toLower();
    return err.contains(QStringLiteral("-4131"))
        || err.contains(QStringLiteral("percent_price"))
        || err.contains(QStringLiteral("best price does not meet"));
}

bool isMaxQuantityExceededError(const QString &errorText) {
    const QString err = errorText.trimmed().toLower();
    return err.contains(QStringLiteral("-4005"))
        || err.contains(QStringLiteral("greater than max quantity"))
        || err.contains(QStringLiteral("max quantity"));
}

bool isReduceOnlyRejectedError(const QString &errorText) {
    const QString err = errorText.trimmed().toLower();
    return err.contains(QStringLiteral("-2022"))
        || err.contains(QStringLiteral("reduceonly order is rejected"))
        || err.contains(QStringLiteral("reduce only order is rejected"));
}

bool hasMatchingOpenFuturesPosition(
    const BinanceRestClient::FuturesPositionsResult *snapshot,
    const QString &symbol,
    const QString &runtimeSide,
    bool hedgeMode) {
    if (!snapshot || !snapshot->ok) {
        return false;
    }

    const QString sym = symbol.trimmed().toUpper();
    const QString side = runtimeSide.trimmed().toUpper();
    for (const auto &pos : snapshot->positions) {
        if (pos.symbol.trimmed().toUpper() != sym) {
            continue;
        }
        const double absAmt = std::fabs(pos.positionAmt);
        if (!qIsFinite(absAmt) || absAmt <= 1e-10) {
            continue;
        }

        const QString posSide = pos.positionSide.trimmed().toUpper();
        const bool sideMatches = (side == QStringLiteral("LONG") && pos.positionAmt > 0.0)
            || (side == QStringLiteral("SHORT") && pos.positionAmt < 0.0)
            || side.isEmpty();
        if (hedgeMode) {
            if ((side == QStringLiteral("LONG") && posSide == QStringLiteral("LONG"))
                || (side == QStringLiteral("SHORT") && posSide == QStringLiteral("SHORT"))) {
                return true;
            }
        } else if ((posSide.isEmpty() || posSide == QStringLiteral("BOTH")) && sideMatches) {
            return true;
        } else if (sideMatches) {
            return true;
        }
    }

    return false;
}

BinanceRestClient::FuturesOrderResult placeFuturesCloseOrderWithFallback(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    bool testnet,
    bool reduceOnly,
    const QString &positionSide,
    int timeoutMs,
    const QString &baseUrlOverride,
    double referencePrice = 0.0) {
    BinanceRestClient::FuturesOrderResult aggregated;
    aggregated.symbol = symbol.trimmed().toUpper();
    aggregated.side = side.trimmed().toUpper();
    aggregated.positionSide = positionSide.trimmed().toUpper();
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        aggregated.error = QStringLiteral("Missing API credentials");
        return aggregated;
    }
    if (aggregated.symbol.isEmpty()) {
        aggregated.error = QStringLiteral("Symbol is required");
        return aggregated;
    }
    if (aggregated.side != QStringLiteral("BUY") && aggregated.side != QStringLiteral("SELL")) {
        aggregated.error = QStringLiteral("Side must be BUY or SELL");
        return aggregated;
    }
    if (!qIsFinite(quantity) || quantity <= 0.0) {
        aggregated.error = QStringLiteral("Quantity must be > 0");
        return aggregated;
    }

    constexpr double kQtyEpsilon = 1e-10;

    const auto filters = BinanceRestClient::fetchFuturesSymbolFilters(
        aggregated.symbol,
        testnet,
        timeoutMs,
        baseUrlOverride);
    const double stepSize = (filters.ok && qIsFinite(filters.stepSize) && filters.stepSize > 0.0) ? filters.stepSize : 0.0;
    const double tickSize = (filters.ok && qIsFinite(filters.tickSize) && filters.tickSize > 0.0) ? filters.tickSize : 0.0;
    const double minQty = (filters.ok && qIsFinite(filters.minQty) && filters.minQty > 0.0)
        ? filters.minQty
        : (stepSize > 0.0 ? stepSize : 0.0);
    const double maxQty = (filters.ok && qIsFinite(filters.maxQty) && filters.maxQty > 0.0) ? filters.maxQty : 0.0;
    const int quantityPrecision = (filters.ok && filters.quantityPrecision > 0) ? filters.quantityPrecision : 8;
    const int pricePrecision = (filters.ok && filters.pricePrecision > 0) ? filters.pricePrecision : 8;
    int maxAttempts = 20;
    if (maxQty > 0.0) {
        maxAttempts = std::max(
            maxAttempts,
            std::min(400, static_cast<int>(std::ceil(quantity / maxQty)) + 8));
    }

    double remainingQty = quantity;
    double chunkQty = (maxQty > 0.0) ? std::min(remainingQty, maxQty) : remainingQty;
    double weightedPriceSum = 0.0;
    double totalExecutedQty = 0.0;
    QStringList orderIds;
    int attempts = 0;
    bool limitFallbackAttempted = false;

    auto consumeOrderFill = [&](const BinanceRestClient::FuturesOrderResult &order, double requestedQty) -> bool {
        const double filledQty = (qIsFinite(order.executedQty) && order.executedQty > 0.0)
            ? std::min(requestedQty, order.executedQty)
            : requestedQty;
        if (!qIsFinite(filledQty) || filledQty <= kQtyEpsilon) {
            aggregated.error = QStringLiteral("Close order returned zero fill.");
            return false;
        }

        totalExecutedQty += filledQty;
        const double fillPrice = (qIsFinite(order.avgPrice) && order.avgPrice > 0.0) ? order.avgPrice : 0.0;
        if (fillPrice > 0.0) {
            weightedPriceSum += (fillPrice * filledQty);
        }
        if (!order.orderId.trimmed().isEmpty()) {
            orderIds.append(order.orderId.trimmed());
        }

        remainingQty = std::max(0.0, remainingQty - filledQty);
        chunkQty = remainingQty;
        return true;
    };

    auto nextChunkFrom = [&](double desired) -> double {
        double chunk = desired;
        if (maxQty > 0.0) {
            chunk = std::min(chunk, maxQty);
        }
        if (stepSize > 0.0) {
            chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
        }
        if (chunk <= 0.0 && desired > 0.0) {
            chunk = (maxQty > 0.0) ? std::min(desired, maxQty) : desired;
        }
        if (minQty > 0.0 && chunk + kQtyEpsilon < minQty) {
            if (remainingQty + kQtyEpsilon < minQty) {
                chunk = remainingQty;
            } else {
                chunk = minQty;
            }
            if (maxQty > 0.0) {
                chunk = std::min(chunk, maxQty);
            }
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (maxQty > 0.0 && chunk > maxQty) {
            chunk = maxQty;
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (chunk > remainingQty) {
            chunk = remainingQty;
        }
        return (qIsFinite(chunk) && chunk > 0.0) ? chunk : 0.0;
    };

    while (remainingQty > kQtyEpsilon && attempts < maxAttempts) {
        chunkQty = nextChunkFrom(chunkQty > 0.0 ? chunkQty : remainingQty);
        if (chunkQty <= 0.0) {
            aggregated.error = QStringLiteral("Unable to derive valid close quantity.");
            break;
        }

        ++attempts;
        const auto order = BinanceRestClient::placeFuturesMarketOrder(
            apiKey,
            apiSecret,
            aggregated.symbol,
            aggregated.side,
            chunkQty,
            testnet,
            reduceOnly,
            aggregated.positionSide,
            timeoutMs,
            baseUrlOverride);
        if (order.ok) {
            if (!consumeOrderFill(order, chunkQty)) {
                break;
            }
            limitFallbackAttempted = false;
            continue;
        }

        const QString orderError = order.error.trimmed();
        if (isPercentPriceFilterError(orderError)) {
            double reducedChunk = chunkQty * 0.5;
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Close fallback activated due to PERCENT_PRICE filter.");
                }
                continue;
            }
            if (!limitFallbackAttempted && qIsFinite(referencePrice) && referencePrice > 0.0) {
                limitFallbackAttempted = true;
                const bool isBuy = aggregated.side == QStringLiteral("BUY");
                const double aggressiveReference = referencePrice * (isBuy ? 1.01 : 0.99);
                const double limitPrice = normalizePriceToTick(
                    aggressiveReference,
                    tickSize,
                    pricePrecision,
                    isBuy);
                if (limitPrice > 0.0) {
                    const auto limitOrder = BinanceRestClient::placeFuturesLimitOrder(
                        apiKey,
                        apiSecret,
                        aggregated.symbol,
                        aggregated.side,
                        chunkQty,
                        limitPrice,
                        testnet,
                        reduceOnly,
                        aggregated.positionSide,
                        QStringLiteral("IOC"),
                        timeoutMs,
                        baseUrlOverride);
                    if (limitOrder.ok) {
                        if (!consumeOrderFill(limitOrder, chunkQty)) {
                            break;
                        }
                        if (aggregated.error.isEmpty()) {
                            aggregated.error = QStringLiteral("Close IOC limit fallback activated due to PERCENT_PRICE filter.");
                        }
                        continue;
                    }
                    const QString limitErrorDetail = limitOrder.error.trimmed().isEmpty()
                        ? QStringLiteral("unknown error")
                        : limitOrder.error.trimmed();
                    aggregated.error = QStringLiteral("%1 | IOC limit fallback failed at %2: %3")
                                           .arg(orderError,
                                                QString::number(limitPrice, 'f', std::max(0, std::min(8, pricePrecision))),
                                                limitErrorDetail);
                    break;
                }
            }
        } else if (isMaxQuantityExceededError(orderError)) {
            double reducedChunk = maxQty > 0.0 ? std::min(chunkQty * 0.5, maxQty) : (chunkQty * 0.5);
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Close fallback activated due to MAX_QTY filter.");
                }
                continue;
            }
        }

        aggregated.error = orderError.isEmpty() ? QStringLiteral("Close order failed") : orderError;
        break;
    }

    aggregated.executedQty = totalExecutedQty;
    if (totalExecutedQty > 0.0 && weightedPriceSum > 0.0) {
        aggregated.avgPrice = weightedPriceSum / totalExecutedQty;
    }
    aggregated.orderId = orderIds.join(QStringLiteral(","));
    if (remainingQty <= kQtyEpsilon && totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("FILLED");
        if (aggregated.error.startsWith(QStringLiteral("Close fallback activated"))
            || aggregated.error.startsWith(QStringLiteral("Close IOC limit fallback activated"))) {
            aggregated.error.clear();
        }
        return aggregated;
    }
    if (totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("PARTIALLY_FILLED");
        const QString partialMessage = QStringLiteral(
            "Partial close: executed=%1 requested=%2 remaining=%3 attempts=%4")
                                           .arg(QString::number(totalExecutedQty, 'f', 8),
                                                QString::number(quantity, 'f', 8),
                                                QString::number(std::max(0.0, remainingQty), 'f', 8),
                                                QString::number(attempts));
        if (aggregated.error.isEmpty()) {
            aggregated.error = partialMessage;
        } else {
            aggregated.error = partialMessage + QStringLiteral(" | ") + aggregated.error;
        }
        return aggregated;
    }

    if (aggregated.error.isEmpty()) {
        aggregated.error = QStringLiteral("Close order failed without fill.");
    }
    aggregated.status = QStringLiteral("FAILED");
    return aggregated;
}

BinanceRestClient::FuturesOrderResult placeFuturesOpenOrderWithFallback(
    const QString &apiKey,
    const QString &apiSecret,
    const QString &symbol,
    const QString &side,
    double quantity,
    bool testnet,
    const QString &positionSide,
    int timeoutMs,
    const QString &baseUrlOverride) {
    BinanceRestClient::FuturesOrderResult aggregated;
    aggregated.symbol = symbol.trimmed().toUpper();
    aggregated.side = side.trimmed().toUpper();
    aggregated.positionSide = positionSide.trimmed().toUpper();
    if (apiKey.trimmed().isEmpty() || apiSecret.trimmed().isEmpty()) {
        aggregated.error = QStringLiteral("Missing API credentials");
        return aggregated;
    }
    if (aggregated.symbol.isEmpty()) {
        aggregated.error = QStringLiteral("Symbol is required");
        return aggregated;
    }
    if (aggregated.side != QStringLiteral("BUY") && aggregated.side != QStringLiteral("SELL")) {
        aggregated.error = QStringLiteral("Side must be BUY or SELL");
        return aggregated;
    }
    if (!qIsFinite(quantity) || quantity <= 0.0) {
        aggregated.error = QStringLiteral("Quantity must be > 0");
        return aggregated;
    }

    constexpr double kQtyEpsilon = 1e-10;

    const auto filters = BinanceRestClient::fetchFuturesSymbolFilters(
        aggregated.symbol,
        testnet,
        timeoutMs,
        baseUrlOverride);
    const double stepSize = (filters.ok && qIsFinite(filters.stepSize) && filters.stepSize > 0.0) ? filters.stepSize : 0.0;
    const double minQty = (filters.ok && qIsFinite(filters.minQty) && filters.minQty > 0.0)
        ? filters.minQty
        : (stepSize > 0.0 ? stepSize : 0.0);
    const double maxQty = (filters.ok && qIsFinite(filters.maxQty) && filters.maxQty > 0.0) ? filters.maxQty : 0.0;
    const int quantityPrecision = (filters.ok && filters.quantityPrecision > 0) ? filters.quantityPrecision : 8;
    int maxAttempts = 20;
    if (maxQty > 0.0) {
        maxAttempts = std::max(
            maxAttempts,
            std::min(400, static_cast<int>(std::ceil(quantity / maxQty)) + 8));
    }

    double remainingQty = quantity;
    double chunkQty = (maxQty > 0.0) ? std::min(remainingQty, maxQty) : remainingQty;
    double weightedPriceSum = 0.0;
    double totalExecutedQty = 0.0;
    QStringList orderIds;
    int attempts = 0;

    auto nextChunkFrom = [&](double desired) -> double {
        double chunk = desired;
        if (maxQty > 0.0) {
            chunk = std::min(chunk, maxQty);
        }
        if (stepSize > 0.0) {
            chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
        }
        if (chunk <= 0.0 && desired > 0.0) {
            chunk = (maxQty > 0.0) ? std::min(desired, maxQty) : desired;
        }
        if (minQty > 0.0 && chunk + kQtyEpsilon < minQty) {
            if (remainingQty + kQtyEpsilon < minQty) {
                chunk = remainingQty;
            } else {
                chunk = minQty;
            }
            if (maxQty > 0.0) {
                chunk = std::min(chunk, maxQty);
            }
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (maxQty > 0.0 && chunk > maxQty) {
            chunk = maxQty;
            if (stepSize > 0.0) {
                chunk = floorToOrderStep(chunk, stepSize, quantityPrecision);
            }
        }
        if (chunk > remainingQty) {
            chunk = remainingQty;
        }
        return (qIsFinite(chunk) && chunk > 0.0) ? chunk : 0.0;
    };

    while (remainingQty > kQtyEpsilon && attempts < maxAttempts) {
        chunkQty = nextChunkFrom(chunkQty > 0.0 ? chunkQty : remainingQty);
        if (chunkQty <= 0.0) {
            aggregated.error = QStringLiteral("Unable to derive valid open quantity.");
            break;
        }

        ++attempts;
        const auto order = BinanceRestClient::placeFuturesMarketOrder(
            apiKey,
            apiSecret,
            aggregated.symbol,
            aggregated.side,
            chunkQty,
            testnet,
            false,
            aggregated.positionSide,
            timeoutMs,
            baseUrlOverride);
        if (order.ok) {
            const double filledQty = (qIsFinite(order.executedQty) && order.executedQty > 0.0)
                ? std::min(chunkQty, order.executedQty)
                : chunkQty;
            if (!qIsFinite(filledQty) || filledQty <= kQtyEpsilon) {
                aggregated.error = QStringLiteral("Open order returned zero fill.");
                break;
            }

            totalExecutedQty += filledQty;
            const double fillPrice = (qIsFinite(order.avgPrice) && order.avgPrice > 0.0) ? order.avgPrice : 0.0;
            if (fillPrice > 0.0) {
                weightedPriceSum += (fillPrice * filledQty);
            }
            if (!order.orderId.trimmed().isEmpty()) {
                orderIds.append(order.orderId.trimmed());
            }

            remainingQty = std::max(0.0, remainingQty - filledQty);
            chunkQty = remainingQty;
            continue;
        }

        const QString orderError = order.error.trimmed();
        if (isPercentPriceFilterError(orderError)) {
            double reducedChunk = chunkQty * 0.5;
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Open fallback activated due to PERCENT_PRICE filter.");
                }
                continue;
            }
        } else if (isMaxQuantityExceededError(orderError)) {
            double reducedChunk = maxQty > 0.0 ? std::min(chunkQty * 0.5, maxQty) : (chunkQty * 0.5);
            if (stepSize > 0.0) {
                reducedChunk = floorToOrderStep(reducedChunk, stepSize, quantityPrecision);
            }
            if (reducedChunk > kQtyEpsilon && reducedChunk + kQtyEpsilon < chunkQty) {
                chunkQty = reducedChunk;
                if (aggregated.error.isEmpty()) {
                    aggregated.error = QStringLiteral("Open fallback activated due to MAX_QTY filter.");
                }
                continue;
            }
        }

        aggregated.error = orderError.isEmpty() ? QStringLiteral("Open order failed") : orderError;
        break;
    }

    aggregated.executedQty = totalExecutedQty;
    if (totalExecutedQty > 0.0 && weightedPriceSum > 0.0) {
        aggregated.avgPrice = weightedPriceSum / totalExecutedQty;
    }
    aggregated.orderId = orderIds.join(QStringLiteral(","));
    if (remainingQty <= kQtyEpsilon && totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("FILLED");
        if (aggregated.error.startsWith(QStringLiteral("Open fallback activated"))) {
            aggregated.error.clear();
        }
        return aggregated;
    }
    if (totalExecutedQty > 0.0) {
        aggregated.ok = true;
        aggregated.status = QStringLiteral("PARTIALLY_FILLED");
        const QString partialMessage = QStringLiteral(
            "Partial open: executed=%1 requested=%2 remaining=%3 attempts=%4")
                                           .arg(QString::number(totalExecutedQty, 'f', 8),
                                                QString::number(quantity, 'f', 8),
                                                QString::number(std::max(0.0, remainingQty), 'f', 8),
                                                QString::number(attempts));
        if (aggregated.error.isEmpty()) {
            aggregated.error = partialMessage;
        } else {
            aggregated.error = partialMessage + QStringLiteral(" | ") + aggregated.error;
        }
        return aggregated;
    }

    if (aggregated.error.isEmpty()) {
        aggregated.error = QStringLiteral("Open order failed without fill.");
    }
    aggregated.status = QStringLiteral("FAILED");
    return aggregated;
}

QString formatDuration(qint64 seconds) {
    seconds = std::max<qint64>(0, seconds);

    constexpr qint64 kMinute = 60;
    constexpr qint64 kHour = 60 * kMinute;
    constexpr qint64 kDay = 24 * kHour;
    constexpr qint64 kMonth = 30 * kDay;

    const qint64 months = seconds / kMonth;
    seconds %= kMonth;
    const qint64 days = seconds / kDay;
    seconds %= kDay;
    const qint64 hours = seconds / kHour;
    seconds %= kHour;
    const qint64 minutes = seconds / kMinute;
    seconds %= kMinute;

    QStringList parts;
    if (months > 0) {
        parts.append(QStringLiteral("%1mo").arg(months));
    }
    if (!parts.isEmpty() || days > 0) {
        parts.append(QStringLiteral("%1d").arg(days));
    }
    if (!parts.isEmpty() || hours > 0) {
        parts.append(QStringLiteral("%1h").arg(hours));
    }
    if (!parts.isEmpty() || minutes > 0) {
        parts.append(QStringLiteral("%1m").arg(minutes));
    }
    parts.append(QStringLiteral("%1s").arg(seconds));
    return parts.join(QStringLiteral(" "));
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

void TradingBotWindow::showIndicatorDialog(const QString &indicatorName) {
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

    const QString key = normalizedIndicatorKey(indicatorName);

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

    const QVariantMap storedParams = dashboardIndicatorParams_.value(key);
    for (auto &field : fields) {
        if (!storedParams.contains(field.key)) {
            continue;
        }
        const QVariant value = storedParams.value(field.key);
        if (!value.isValid()) {
            field.defaultValue = QVariant();
            continue;
        }
        field.defaultValue = value;
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

    struct BoundField {
        QString key;
        FieldSpec::Kind kind;
        QWidget *widget = nullptr;
        bool nullableText = false;
    };
    QVector<BoundField> boundFields;
    boundFields.reserve(fields.size());

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
            if (spec.defaultValue.isValid()) {
                edit->setText(spec.defaultValue.toString());
            }
            fieldWidget = edit;
        }

        form->addRow(spec.label, fieldWidget);
        boundFields.push_back({spec.key, spec.kind, fieldWidget, spec.key == "buy_value" || spec.key == "sell_value"});
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
    if (dialog->exec() == QDialog::Accepted) {
        QVariantMap updated = dashboardIndicatorParams_.value(key);
        for (const auto &bound : boundFields) {
            if (!bound.widget || bound.key.trimmed().isEmpty()) {
                continue;
            }
            QVariant value;
            if (bound.nullableText) {
                const QString text = qobject_cast<QLineEdit *>(bound.widget)
                                         ? qobject_cast<QLineEdit *>(bound.widget)->text().trimmed()
                                         : QString();
                if (text.isEmpty() || text.compare(QStringLiteral("none"), Qt::CaseInsensitive) == 0) {
                    value = QVariant();
                } else {
                    bool ok = false;
                    const double parsed = text.toDouble(&ok);
                    value = ok ? QVariant(parsed) : QVariant(text);
                }
            } else if (bound.kind == FieldSpec::IntField) {
                if (const auto *spin = qobject_cast<QSpinBox *>(bound.widget)) {
                    value = spin->value();
                }
            } else if (bound.kind == FieldSpec::DoubleField) {
                if (const auto *dspin = qobject_cast<QDoubleSpinBox *>(bound.widget)) {
                    value = dspin->value();
                }
            } else if (bound.kind == FieldSpec::ComboField) {
                if (const auto *combo = qobject_cast<QComboBox *>(bound.widget)) {
                    value = combo->currentText();
                }
            }
            updated.insert(bound.key, value);
        }
        dashboardIndicatorParams_.insert(key, updated);
    }
}

void TradingBotWindow::refreshDashboardBalance() {
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
    const bool isFutures = accountNorm.startsWith("fut");
    const bool paperTrading = isPaperTradingModeLabel(mode);
    const bool isTestnet = isTestnetModeLabel(mode);
    const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
    const ConnectorRuntimeConfig connectorCfg = resolveConnectorConfig(connectorText, isFutures);
    if (!connectorCfg.ok()) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("Connector error: %1").arg(connectorCfg.error));
            dashboardBalanceLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
        }
        resetButton();
        return;
    }
    if (!connectorCfg.warning.trimmed().isEmpty()) {
        updateStatusMessage(QString("Connector fallback: %1").arg(connectorCfg.warning));
    }

    if (paperTrading) {
        syncDashboardPaperBalanceUi();
        updateStatusMessage(QStringLiteral("Paper Local uses live market data with a configurable paper balance."));
        resetButton();
        return;
    }

    if (apiKey.isEmpty() || apiSecret.isEmpty()) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText("API credentials missing");
        }
        resetButton();
        return;
    }

    const auto result = BinanceRestClient::fetchUsdtBalance(
        apiKey,
        apiSecret,
        isFutures,
        isTestnet,
        10000,
        connectorCfg.baseUrl);
    if (!result.ok) {
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QString("Error: %1").arg(result.error));
            dashboardBalanceLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
        }
        resetButton();
        return;
    }

    if (dashboardBalanceLabel_) {
        const double totalValue = std::max(0.0, (result.totalUsdtBalance > 0.0) ? result.totalUsdtBalance : result.usdtBalance);
        const double availableValue = std::max(0.0, (result.availableUsdtBalance > 0.0) ? result.availableUsdtBalance : totalValue);
        positionsLastTotalBalanceUsdt_ = totalValue;
        positionsLastAvailableBalanceUsdt_ = availableValue;
        const QString totalText = QString::number(totalValue, 'f', 3);
        const QString availableText = QString::number(availableValue, 'f', 3);
        if (qAbs(totalValue - availableValue) > 1e-6) {
            dashboardBalanceLabel_->setText(QString("Total %1 USDT | Available %2 USDT").arg(totalText, availableText));
        } else {
            dashboardBalanceLabel_->setText(QString("%1 USDT").arg(totalText));
        }
        dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
    }
    refreshPositionsSummaryLabels();
    resetButton();
}

double TradingBotWindow::currentDashboardPaperBalanceUsdt() const {
    if (dashboardPaperBalanceSpin_) {
        const double value = dashboardPaperBalanceSpin_->value();
        if (qIsFinite(value) && value > 0.0) {
            return value;
        }
    }
    return 1000.0;
}

void TradingBotWindow::syncDashboardPaperBalanceUi() {
    const bool paperTrading = dashboardModeCombo_
        && isPaperTradingModeLabel(dashboardModeCombo_->currentText());
    if (dashboardPaperBalanceTitleLabel_) {
        dashboardPaperBalanceTitleLabel_->setVisible(paperTrading);
    }
    if (dashboardPaperBalanceSpin_) {
        dashboardPaperBalanceSpin_->setVisible(paperTrading);
        dashboardPaperBalanceSpin_->setEnabled(paperTrading && !dashboardRuntimeActive_);
    }

    if (!paperTrading) {
        positionsLastTotalBalanceUsdt_ = std::numeric_limits<double>::quiet_NaN();
        positionsLastAvailableBalanceUsdt_ = std::numeric_limits<double>::quiet_NaN();
        if (dashboardBalanceLabel_) {
            dashboardBalanceLabel_->setText(QStringLiteral("N/A"));
            dashboardBalanceLabel_->setStyleSheet("color: #fbbf24; font-weight: 700;");
        }
        refreshPositionsSummaryLabels();
        return;
    }

    const double paperBalance = currentDashboardPaperBalanceUsdt();
    positionsLastTotalBalanceUsdt_ = paperBalance;
    positionsLastAvailableBalanceUsdt_ = paperBalance;
    if (dashboardBalanceLabel_) {
        dashboardBalanceLabel_->setText(
            QStringLiteral("Paper balance: %1 USDT")
                .arg(QString::number(paperBalance, 'f', 3)));
        dashboardBalanceLabel_->setStyleSheet("color: #22c55e; font-weight: 700;");
    }
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::refreshDashboardSymbols() {
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
    QCoreApplication::processEvents();

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
    const bool isFutures = accountNorm.startsWith("fut");
    const bool isTestnet = isTestnetModeLabel(mode);
    const QString selectedExchange = selectedDashboardExchange(dashboardExchangeCombo_);

    if (!exchangeUsesBinanceApi(selectedExchange)) {
        const QStringList fallbackSymbols = placeholderSymbolsForExchange(selectedExchange, isFutures);
        applySymbols(fallbackSymbols);
        updateStatusMessage(
            QString("%1 API symbol sync is coming soon. Showing placeholder symbols.").arg(selectedExchange));
        resetButton();
        return;
    }

    const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
    const ConnectorRuntimeConfig connectorCfg = resolveConnectorConfig(connectorText, isFutures);
    if (!connectorCfg.ok()) {
        QMessageBox::warning(this, tr("Connector error"), connectorCfg.error);
        resetButton();
        return;
    }
    if (!connectorCfg.warning.trimmed().isEmpty()) {
        updateStatusMessage(QString("Connector fallback: %1").arg(connectorCfg.warning));
    }

    const auto result = BinanceRestClient::fetchUsdtSymbols(isFutures, isTestnet, 10000, true, 0, connectorCfg.baseUrl);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Refresh symbols failed"), result.error);
        resetButton();
        return;
    }

    applySymbols(result.symbols);

    resetButton();
}

void TradingBotWindow::refreshBacktestSymbols() {
    if (!symbolList_) {
        return;
    }

    if (backtestRefreshSymbolsBtn_) {
        backtestRefreshSymbolsBtn_->setEnabled(false);
        backtestRefreshSymbolsBtn_->setText("Refreshing...");
    }
    auto resetButton = [this]() {
        if (backtestRefreshSymbolsBtn_) {
            backtestRefreshSymbolsBtn_->setEnabled(true);
            backtestRefreshSymbolsBtn_->setText("Refresh Symbols");
        }
    };

    QSet<QString> previousSelections;
    for (auto *item : symbolList_->selectedItems()) {
        if (item) {
            previousSelections.insert(item->text().trimmed().toUpper());
        }
    }

    const bool futures = symbolSourceCombo_
        ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    const bool isTestnet = dashboardModeCombo_ ? isTestnetModeLabel(dashboardModeCombo_->currentText()) : false;
    const QString connectorText = backtestConnectorCombo_
        ? backtestConnectorCombo_->currentText().trimmed()
        : connectorLabelForKey(recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig connectorCfg = resolveConnectorConfig(connectorText, futures);
    if (!connectorCfg.ok()) {
        updateStatusMessage(QString("Backtest symbols: connector error: %1").arg(connectorCfg.error));
        if (symbolList_->count() == 0) {
            symbolList_->addItems(placeholderSymbolsForExchange(QStringLiteral("Binance"), futures));
            if (symbolList_->count() > 0) {
                symbolList_->item(0)->setSelected(true);
            }
        }
        resetButton();
        return;
    }

    constexpr int kBacktestSymbolTopN = 200;
    const auto result = BinanceRestClient::fetchUsdtSymbols(
        futures,
        isTestnet,
        10000,
        true,
        kBacktestSymbolTopN,
        connectorCfg.baseUrl);

    if (!result.ok || result.symbols.isEmpty()) {
        if (symbolList_->count() == 0) {
            symbolList_->clear();
            symbolList_->addItems(placeholderSymbolsForExchange(QStringLiteral("Binance"), futures));
            if (symbolList_->count() > 0) {
                symbolList_->item(0)->setSelected(true);
            }
        }
        const QString err = result.error.trimmed().isEmpty() ? QStringLiteral("no symbols returned") : result.error.trimmed();
        updateStatusMessage(QString("Backtest symbol refresh failed: %1").arg(err));
        resetButton();
        return;
    }

    symbolList_->clear();
    symbolList_->addItems(result.symbols);

    bool anySelected = false;
    for (int i = 0; i < symbolList_->count(); ++i) {
        auto *item = symbolList_->item(i);
        if (!item) {
            continue;
        }
        const QString key = item->text().trimmed().toUpper();
        if (previousSelections.contains(key)) {
            item->setSelected(true);
            anySelected = true;
        }
    }
    if (!anySelected && symbolList_->count() > 0) {
        symbolList_->item(0)->setSelected(true);
    }

    updateStatusMessage(QString("Loaded %1 %2 symbols for backtest.")
                            .arg(result.symbols.size())
                            .arg(futures ? QStringLiteral("FUTURES") : QStringLiteral("SPOT")));
    resetButton();
}

void TradingBotWindow::refreshBacktestSymbolIntervalTable() {
    if (!backtestSymbolIntervalTable_) {
        return;
    }
    backtestSymbolIntervalTable_->resizeColumnsToContents();
}

void TradingBotWindow::addSelectedBacktestSymbolIntervalPairs() {
    if (!backtestSymbolIntervalTable_ || !symbolList_ || !intervalList_) {
        return;
    }

    QStringList symbols;
    for (auto *item : symbolList_->selectedItems()) {
        if (!item) {
            continue;
        }
        const QString value = item->text().trimmed().toUpper();
        if (!value.isEmpty()) {
            symbols.push_back(value);
        }
    }
    symbols.removeDuplicates();

    QStringList intervals;
    for (auto *item : intervalList_->selectedItems()) {
        if (!item) {
            continue;
        }
        const QString value = item->text().trimmed();
        if (!value.isEmpty()) {
            intervals.push_back(value);
        }
    }
    intervals.removeDuplicates();

    if (symbols.isEmpty() || intervals.isEmpty()) {
        updateStatusMessage("Select at least one symbol and interval before adding overrides.");
        return;
    }

    QSet<QString> existingKeys;
    for (int row = 0; row < backtestSymbolIntervalTable_->rowCount(); ++row) {
        const auto *symItem = backtestSymbolIntervalTable_->item(row, 0);
        const auto *intItem = backtestSymbolIntervalTable_->item(row, 1);
        const QString sym = symItem ? symItem->text().trimmed().toUpper() : QString();
        const QString iv = intItem ? intItem->text().trimmed() : QString();
        if (!sym.isEmpty() && !iv.isEmpty()) {
            existingKeys.insert(sym + "|" + iv);
        }
    }

    const QString connectorText = backtestConnectorCombo_
        ? backtestConnectorCombo_->currentText().trimmed()
        : QStringLiteral("-");
    const QString loopText = backtestLoopCombo_
        ? backtestLoopCombo_->currentText().trimmed()
        : QStringLiteral("-");
    const QString leverageText = backtestLeverageSpin_
        ? QString("%1x").arg(backtestLeverageSpin_->value())
        : QStringLiteral("-");
    const QString sideText = backtestSideCombo_
        ? backtestSideCombo_->currentText().trimmed()
        : QStringLiteral("Default");
    QString stopLossText = QStringLiteral("No");
    if (backtestStopLossEnableCheck_ && backtestStopLossEnableCheck_->isChecked()) {
        const QString mode = backtestStopLossModeCombo_
            ? backtestStopLossModeCombo_->currentData().toString().trimmed().toLower()
            : QStringLiteral("usdt");
        const QString scope = backtestStopLossScopeCombo_
            ? backtestStopLossScopeCombo_->currentData().toString().trimmed().toLower().replace('_', '-')
            : QStringLiteral("per-trade");
        stopLossText = QString("Yes (%1 | %2)")
                           .arg(mode.isEmpty() ? QStringLiteral("usdt") : mode,
                                scope.isEmpty() ? QStringLiteral("per-trade") : scope);
    }
    const QString strategyText = QString("Side: %1").arg(sideText);

    int added = 0;
    const bool wasSorting = backtestSymbolIntervalTable_->isSortingEnabled();
    backtestSymbolIntervalTable_->setSortingEnabled(false);
    for (const QString &sym : symbols) {
        for (const QString &iv : intervals) {
            const QString key = sym + "|" + iv;
            if (existingKeys.contains(key)) {
                continue;
            }
            existingKeys.insert(key);
            const int row = backtestSymbolIntervalTable_->rowCount();
            backtestSymbolIntervalTable_->insertRow(row);
            backtestSymbolIntervalTable_->setItem(row, 0, new QTableWidgetItem(sym));
            backtestSymbolIntervalTable_->setItem(row, 1, new QTableWidgetItem(iv));
            backtestSymbolIntervalTable_->setItem(row, 2, new QTableWidgetItem("Default"));
            backtestSymbolIntervalTable_->setItem(row, 3, new QTableWidgetItem(loopText));
            backtestSymbolIntervalTable_->setItem(row, 4, new QTableWidgetItem(leverageText));
            backtestSymbolIntervalTable_->setItem(row, 5, new QTableWidgetItem(connectorText.isEmpty() ? "-" : connectorText));
            backtestSymbolIntervalTable_->setItem(row, 6, new QTableWidgetItem(strategyText));
            backtestSymbolIntervalTable_->setItem(row, 7, new QTableWidgetItem(stopLossText));
            ++added;
        }
    }
    backtestSymbolIntervalTable_->setSortingEnabled(wasSorting);
    refreshBacktestSymbolIntervalTable();
    updateStatusMessage(QString("Backtest overrides updated: added %1 row(s).").arg(added));
}

void TradingBotWindow::removeSelectedBacktestSymbolIntervalPairs() {
    if (!backtestSymbolIntervalTable_) {
        return;
    }

    QList<int> rows;
    const auto selectedRows = backtestSymbolIntervalTable_->selectionModel()
        ? backtestSymbolIntervalTable_->selectionModel()->selectedRows()
        : QModelIndexList{};
    for (const QModelIndex &idx : selectedRows) {
        if (idx.isValid()) {
            rows.push_back(idx.row());
        }
    }
    std::sort(rows.begin(), rows.end(), std::greater<int>());
    rows.erase(std::unique(rows.begin(), rows.end()), rows.end());

    for (int row : rows) {
        if (row >= 0 && row < backtestSymbolIntervalTable_->rowCount()) {
            backtestSymbolIntervalTable_->removeRow(row);
        }
    }
    refreshBacktestSymbolIntervalTable();
    updateStatusMessage(QString("Backtest overrides updated: removed %1 row(s).").arg(rows.size()));
}

void TradingBotWindow::clearBacktestSymbolIntervalPairs() {
    if (!backtestSymbolIntervalTable_) {
        return;
    }
    const int rowCount = backtestSymbolIntervalTable_->rowCount();
    backtestSymbolIntervalTable_->setRowCount(0);
    updateStatusMessage(QString("Backtest overrides cleared: %1 row(s).").arg(rowCount));
}

void TradingBotWindow::applyDashboardTemplate(const QString &templateKey) {
    const QString key = templateKey.trimmed().toLower();
    if (key.isEmpty()) {
        return;
    }

    const DashboardTemplatePreset preset = dashboardTemplatePresetForKey(key);
    if (!preset.valid) {
        return;
    }

    if (dashboardPositionPctSpin_) {
        QSignalBlocker blocker(dashboardPositionPctSpin_);
        dashboardPositionPctSpin_->setValue(preset.positionPct);
    }
    if (dashboardLeverageSpin_) {
        QSignalBlocker blocker(dashboardLeverageSpin_);
        dashboardLeverageSpin_->setValue(preset.leverage);
    }
    if (dashboardMarginModeCombo_ && !preset.marginMode.trimmed().isEmpty()) {
        int idx = dashboardMarginModeCombo_->findText(preset.marginMode, Qt::MatchFixedString);
        if (idx < 0) {
            idx = dashboardMarginModeCombo_->findText(preset.marginMode, Qt::MatchContains);
        }
        if (idx >= 0) {
            QSignalBlocker blocker(dashboardMarginModeCombo_);
            dashboardMarginModeCombo_->setCurrentIndex(idx);
        }
    }

    for (auto it = preset.indicators.constBegin(); it != preset.indicators.constEnd(); ++it) {
        const QString indKey = it.key();
        if (indKey.trimmed().isEmpty()) {
            continue;
        }
        dashboardIndicatorParams_.insert(indKey, it.value());
        if (auto *check = dashboardIndicatorChecks_.value(indKey, nullptr)) {
            check->setChecked(true);
        }
        if (auto *btn = dashboardIndicatorButtons_.value(indKey, nullptr)) {
            btn->setEnabled(true);
        }
    }

    updateStatusMessage(QStringLiteral("Dashboard template applied: %1").arg(templateKey.trimmed()));
}

QWidget *TradingBotWindow::createDashboardTab() {
    auto *page = new QWidget(this);
    page->setObjectName("dashboardPage");
    dashboardPage_ = page;
    dashboardApiKey_ = nullptr;
    dashboardApiSecret_ = nullptr;
    dashboardBalanceLabel_ = nullptr;
    dashboardPaperBalanceSpin_ = nullptr;
    dashboardPnlActiveLabel_ = nullptr;
    dashboardPnlClosedLabel_ = nullptr;
    dashboardBotStatusLabel_ = nullptr;
    dashboardBotTimeLabel_ = nullptr;
    dashboardRefreshBtn_ = nullptr;
    dashboardAccountTypeCombo_ = nullptr;
    dashboardModeCombo_ = nullptr;
    dashboardConnectorCombo_ = nullptr;
    dashboardExchangeCombo_ = nullptr;
    dashboardIndicatorSourceCombo_ = nullptr;
    dashboardSignalFeedCombo_ = nullptr;
    dashboardTemplateCombo_ = nullptr;
    dashboardMarginModeCombo_ = nullptr;
    dashboardPositionPctSpin_ = nullptr;
    dashboardLeverageSpin_ = nullptr;
    dashboardSymbolList_ = nullptr;
    dashboardIntervalList_ = nullptr;
    dashboardRefreshSymbolsBtn_ = nullptr;
    dashboardStartBtn_ = nullptr;
    dashboardStopBtn_ = nullptr;
    dashboardOverridesTable_ = nullptr;
    dashboardAllLogsEdit_ = nullptr;
    dashboardPositionLogsEdit_ = nullptr;
    dashboardWaitingLogsEdit_ = nullptr;
    dashboardWaitingQueueTable_ = nullptr;
    dashboardRuntimeLastEvalMs_.clear();
    dashboardRuntimeEntryRetryAfterMs_.clear();
    dashboardRuntimeOpenQtyCaps_.clear();
    dashboardRuntimeConnectorWarnings_.clear();
    dashboardRuntimeIntervalWarnings_.clear();
    clearRuntimeSignalSockets(dashboardRuntimeSignalSockets_);
    dashboardRuntimeSignalCandles_.clear();
    dashboardRuntimeSignalLastClosed_.clear();
    dashboardRuntimeSignalUpdateMs_.clear();
    dashboardRuntimeLockWidgets_.clear();
    dashboardLeadTraderEnableCheck_ = nullptr;
    dashboardLeadTraderCombo_ = nullptr;
    dashboardStopLossEnableCheck_ = nullptr;
    dashboardStopLossModeCombo_ = nullptr;
    dashboardStopLossScopeCombo_ = nullptr;
    dashboardStopLossUsdtSpin_ = nullptr;
    dashboardStopLossPercentSpin_ = nullptr;
    dashboardRuntimeActive_ = false;
    dashboardWaitingActiveEntries_.clear();
    dashboardWaitingHistoryEntries_.clear();
    dashboardWaitingHistoryMax_ = 500;
    dashboardRuntimeOpenPositions_.clear();
    dashboardIndicatorChecks_.clear();
    dashboardIndicatorButtons_.clear();
    dashboardIndicatorParams_.clear();

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

    auto registerRuntimeLockWidget = [this](QWidget *widget) {
        if (!widget) {
            return;
        }
        if (!dashboardRuntimeLockWidgets_.contains(widget)) {
            dashboardRuntimeLockWidgets_.append(widget);
        }
    };

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
    registerRuntimeLockWidget(dashboardApiKey_);
    addPair(0, col, "API Key:", dashboardApiKey_, 2);

    dashboardModeCombo_ = new QComboBox(accountBox);
    dashboardModeCombo_->addItems({"Live", "Paper Local", "Demo"});
    dashboardModeCombo_->setToolTip(
        "Live: real Binance Futures orders.\n"
        "Paper Local: live market data with app-local paper positions.\n"
        "Demo: Binance Futures Testnet/Demo orders and positions.");
    registerRuntimeLockWidget(dashboardModeCombo_);
    addPair(0, col, "Mode:", dashboardModeCombo_);

    dashboardThemeCombo_ = new QComboBox(accountBox);
    dashboardThemeCombo_->addItems({"Light", "Dark", "Blue", "Yellow", "Green", "Red"});
    dashboardThemeCombo_->setCurrentText("Dark");
    registerRuntimeLockWidget(dashboardThemeCombo_);
    addPair(0, col, "Theme:", dashboardThemeCombo_);
    connect(dashboardThemeCombo_, &QComboBox::currentTextChanged, this, &TradingBotWindow::applyDashboardTheme);

    auto *pnlActive = new QLabel("--", accountBox);
    pnlActive->setStyleSheet("color: #a5b4fc;");
    dashboardPnlActiveLabel_ = pnlActive;
    addPair(0, col, "Total PNL Active Positions:", pnlActive);

    auto *pnlClosed = new QLabel("--", accountBox);
    pnlClosed->setStyleSheet("color: #a5b4fc;");
    dashboardPnlClosedLabel_ = pnlClosed;
    addPair(0, col, "Total PNL Closed Positions:", pnlClosed);

    auto *botStatus = new QLabel("OFF", accountBox);
    botStatus->setStyleSheet("color: #ef4444; font-weight: 700;");
    dashboardBotStatusLabel_ = botStatus;
    addPair(0, col, "Bot Status:", botStatus);

    accountGrid->addWidget(new QLabel("Bot Active Time:", accountBox), 0, col++);
    auto *botTime = new QLabel("--", accountBox);
    botTime->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    dashboardBotTimeLabel_ = botTime;
    accountGrid->addWidget(botTime, 0, col, 1, 2);
    accountGrid->setColumnStretch(col, 1);

    col = 0;
    dashboardApiSecret_ = new QLineEdit(accountBox);
    dashboardApiSecret_->setEchoMode(QLineEdit::Password);
    dashboardApiSecret_->setPlaceholderText("API Secret Key");
    dashboardApiSecret_->setMinimumWidth(140);
    registerRuntimeLockWidget(dashboardApiSecret_);
    addPair(1, col, "API Secret Key:", dashboardApiSecret_, 2);

    dashboardAccountTypeCombo_ = new QComboBox(accountBox);
    dashboardAccountTypeCombo_->addItems({"Futures", "Spot"});
    registerRuntimeLockWidget(dashboardAccountTypeCombo_);
    addPair(1, col, "Account Type:", dashboardAccountTypeCombo_);

    auto *accountModeCombo = new QComboBox(accountBox);
    accountModeCombo->addItems({"Classic Trading", "Multi-Asset Mode"});
    registerRuntimeLockWidget(accountModeCombo);
    addPair(1, col, "Account Mode:", accountModeCombo);

    auto *connectorCombo = new QComboBox(accountBox);
    rebuildDashboardConnectorComboForAccount(connectorCombo, true, true);
    connectorCombo->setToolTip(
        "Matches Python connector options.\n"
        "C++ currently runs native Binance REST under the hood.\n"
        "Unsupported connector backends are auto-mapped to native equivalents.");
    connectorCombo->setMinimumWidth(340);
    dashboardConnectorCombo_ = connectorCombo;
    registerRuntimeLockWidget(connectorCombo);
    addPair(1, col, "Connector:", connectorCombo, 3);
    if (dashboardAccountTypeCombo_) {
        connect(dashboardAccountTypeCombo_, &QComboBox::currentTextChanged, this, [this](const QString &accountText) {
            const bool isFutures = accountText.trimmed().toLower().startsWith(QStringLiteral("fut"));
            rebuildDashboardConnectorComboForAccount(dashboardConnectorCombo_, isFutures, false);
        });
    }
    if (dashboardModeCombo_) {
        connect(dashboardModeCombo_, &QComboBox::currentTextChanged, this, [this](const QString &) {
            syncDashboardPaperBalanceUi();
        });
    }

    col = 0;
    dashboardBalanceLabel_ = new QLabel("N/A", accountBox);
    dashboardBalanceLabel_->setStyleSheet("color: #fbbf24; font-weight: 700;");
    addPair(2, col, "Total USDT balance:", dashboardBalanceLabel_);

    dashboardRefreshBtn_ = new QPushButton("Refresh Balance", accountBox);
    registerRuntimeLockWidget(dashboardRefreshBtn_);
    connect(dashboardRefreshBtn_, &QPushButton::clicked, this, &TradingBotWindow::refreshDashboardBalance);
    accountGrid->addWidget(dashboardRefreshBtn_, 2, col++);

    auto *paperBalanceSpin = new QDoubleSpinBox(accountBox);
    paperBalanceSpin->setRange(1.0, 1000000000.0);
    paperBalanceSpin->setDecimals(3);
    paperBalanceSpin->setSingleStep(100.0);
    paperBalanceSpin->setValue(1000.0);
    paperBalanceSpin->setSuffix(" USDT");
    paperBalanceSpin->setToolTip("Virtual paper balance used for Paper Local position sizing.");
    dashboardPaperBalanceSpin_ = paperBalanceSpin;
    registerRuntimeLockWidget(paperBalanceSpin);
    connect(paperBalanceSpin, &QDoubleSpinBox::valueChanged, this, [this](double) {
        if (dashboardModeCombo_ && isPaperTradingModeLabel(dashboardModeCombo_->currentText())) {
            syncDashboardPaperBalanceUi();
        }
    });
    auto *paperBalanceLabel = new QLabel("Paper Local Balance:", accountBox);
    dashboardPaperBalanceTitleLabel_ = paperBalanceLabel;
    accountGrid->addWidget(paperBalanceLabel, 2, col++);
    accountGrid->addWidget(paperBalanceSpin, 2, col++);

    auto *leverageSpin = new QSpinBox(accountBox);
    leverageSpin->setRange(1, 125);
    leverageSpin->setValue(20);
    dashboardLeverageSpin_ = leverageSpin;
    registerRuntimeLockWidget(leverageSpin);
    addPair(2, col, "Leverage (Futures):", leverageSpin);

    auto *marginModeCombo = new QComboBox(accountBox);
    marginModeCombo->addItems({"Isolated", "Cross"});
    dashboardMarginModeCombo_ = marginModeCombo;
    registerRuntimeLockWidget(marginModeCombo);
    addPair(2, col, "Margin Mode (Futures):", marginModeCombo);

    auto *positionModeCombo = new QComboBox(accountBox);
    positionModeCombo->addItems({"Hedge", "One-way"});
    dashboardPositionModeCombo_ = positionModeCombo;
    registerRuntimeLockWidget(positionModeCombo);
    addPair(2, col, "Position Mode:", positionModeCombo);

    auto *assetsModeCombo = new QComboBox(accountBox);
    assetsModeCombo->addItems({"Single-Asset Mode", "Multi-Asset Mode"});
    registerRuntimeLockWidget(assetsModeCombo);
    addPair(2, col, "Assets Mode:", assetsModeCombo);

    col = 0;
    auto *indicatorSourceCombo = new QComboBox(accountBox);
    indicatorSourceCombo->addItems(dashboardIndicatorSources);
    indicatorSourceCombo->setCurrentText("Binance futures");
    indicatorSourceCombo->setMinimumWidth(140);
    indicatorSourceCombo->setToolTip(
        "Signal candles currently use Binance market data.\n"
        "Selecting Binance futures uses Binance Futures candles for indicator calculations.");
    dashboardIndicatorSourceCombo_ = indicatorSourceCombo;
    registerRuntimeLockWidget(indicatorSourceCombo);
    addPair(3, col, "Indicator Source:", indicatorSourceCombo, 2);

    auto *signalFeedCombo = new QComboBox(accountBox);
    signalFeedCombo->addItem("REST Poll");
    signalFeedCombo->addItem("WebSocket Stream");
    signalFeedCombo->setCurrentText("REST Poll");
    signalFeedCombo->setToolTip(
        "Choose how the dashboard runtime gets signal candles.\n"
        "REST Poll: scheduled REST requests.\n"
        "WebSocket Stream: stream-driven Binance kline updates with local candle cache.");
    if (!qtWebSocketsRuntimeAvailable()) {
        if (auto *model = qobject_cast<QStandardItemModel *>(signalFeedCombo->model())) {
            if (QStandardItem *item = model->item(1)) {
                item->setEnabled(false);
            }
        }
        signalFeedCombo->setToolTip(signalFeedCombo->toolTip() + QStringLiteral("\nQt WebSockets runtime is not available in this build."));
    }
    dashboardSignalFeedCombo_ = signalFeedCombo;
    registerRuntimeLockWidget(signalFeedCombo);
    addPair(3, col, "Signal Feed:", signalFeedCombo);

    auto *orderTypeCombo = new QComboBox(accountBox);
    orderTypeCombo->addItems({"GTC", "IOC", "FOK"});
    registerRuntimeLockWidget(orderTypeCombo);
    addPair(3, col, "Order Type:", orderTypeCombo);

    auto *expiryCombo = new QComboBox(accountBox);
    expiryCombo->addItems({"30 min (GTD)", "1h (GTD)", "4h (GTD)", "GTC"});
    registerRuntimeLockWidget(expiryCombo);
    addPair(3, col, "Expiry / TIF:", expiryCombo);

    for (int stretchCol : {1, 2, 4, 6, 8, 10, 12}) {
        accountGrid->setColumnStretch(stretchCol, 1);
    }
    accountGrid->setColumnStretch(13, 2);
    syncDashboardPaperBalanceUi();

    auto *exchangeBox = new QGroupBox("Exchange", page);
    auto *exchangeLayout = new QVBoxLayout(exchangeBox);
    exchangeLayout->setSpacing(6);
    exchangeLayout->setContentsMargins(12, 10, 12, 10);
    exchangeLayout->addWidget(new QLabel("Select exchange", exchangeBox));
    auto *exchangeCombo = new QComboBox(exchangeBox);
    dashboardExchangeCombo_ = exchangeCombo;
    registerRuntimeLockWidget(exchangeCombo);
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
    registerRuntimeLockWidget(dashboardSymbolList);
    listsGrid->addWidget(dashboardSymbolList, 1, 0, 2, 1);

    auto *dashboardIntervalList = new QListWidget(marketsBox);
    dashboardIntervalList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardIntervalList->addItems({
        "1m", "3m", "5m", "10m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h"
    });
    dashboardIntervalList->setMinimumHeight(220);
    dashboardIntervalList->setMaximumHeight(260);
    dashboardIntervalList_ = dashboardIntervalList;
    registerRuntimeLockWidget(dashboardIntervalList);
    listsGrid->addWidget(dashboardIntervalList, 1, 1, 2, 1);

    dashboardRefreshSymbolsBtn_ = new QPushButton("Refresh Symbols", marketsBox);
    registerRuntimeLockWidget(dashboardRefreshSymbolsBtn_);
    connect(dashboardRefreshSymbolsBtn_, &QPushButton::clicked, this, &TradingBotWindow::refreshDashboardSymbols);
    listsGrid->addWidget(dashboardRefreshSymbolsBtn_, 3, 0, 1, 1);

    auto *customIntervalEdit = new QLineEdit(marketsBox);
    customIntervalEdit->setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated");
    registerRuntimeLockWidget(customIntervalEdit);
    listsGrid->addWidget(customIntervalEdit, 3, 1, 1, 1);
    auto *customButton = new QPushButton("Add Custom Interval(s)", marketsBox);
    registerRuntimeLockWidget(customButton);
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
    sideCombo->addItems({"Buy (Long)", "Sell (Short)", "Both (Long/Short)"});
    sideCombo->setCurrentText("Both (Long/Short)");
    registerRuntimeLockWidget(sideCombo);
    strategyGrid->addWidget(sideCombo, row, 1);

    strategyGrid->addWidget(new QLabel("Position % of Balance:", strategyBox), row, 2);
    auto *positionPct = new QDoubleSpinBox(strategyBox);
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setValue(2.0);
    positionPct->setSuffix(" %");
    dashboardPositionPctSpin_ = positionPct;
    registerRuntimeLockWidget(positionPct);
    strategyGrid->addWidget(positionPct, row, 3);

    strategyGrid->addWidget(new QLabel("Loop Interval Override:", strategyBox), row, 4);
    auto *loopOverride = new QComboBox(strategyBox);
    loopOverride->addItems({
        "Instant",
        "30 seconds",
        "45 seconds",
        "1 minute",
        "2 minutes",
        "3 minutes",
        "5 minutes",
        "10 minutes",
        "30 minutes",
        "1 hour",
        "2 hours",
    });
    loopOverride->setCurrentText("1 minute");
    registerRuntimeLockWidget(loopOverride);
    strategyGrid->addWidget(loopOverride, row, 5);

    ++row;
    auto *enableLeadTrader = new QCheckBox("Enable Lead Trader", strategyBox);
    dashboardLeadTraderEnableCheck_ = enableLeadTrader;
    registerRuntimeLockWidget(enableLeadTrader);
    strategyGrid->addWidget(enableLeadTrader, row, 0, 1, 2);
    auto *leadTraderCombo = new QComboBox(strategyBox);
    leadTraderCombo->addItems({
        "Futures Public Lead Trader",
        "Futures Private Lead Trader",
        "Spot Public Lead Trader",
        "Spot Private Lead Trader",
    });
    dashboardLeadTraderCombo_ = leadTraderCombo;
    leadTraderCombo->setEnabled(false);
    strategyGrid->addWidget(leadTraderCombo, row, 2, 1, 2);
    connect(enableLeadTrader, &QCheckBox::toggled, this, [this](bool checked) {
        if (dashboardLeadTraderCombo_) {
            dashboardLeadTraderCombo_->setEnabled(!dashboardRuntimeActive_ && checked);
        }
    });

    ++row;
    auto *liveIndicatorValuesCheck = new QCheckBox("Use live candle values for signals (repaints)", strategyBox);
    liveIndicatorValuesCheck->setToolTip(
        "When unchecked, signals use the previous closed candle (no repaint), matching candle-close backtests."
    );
    liveIndicatorValuesCheck->setChecked(true);
    registerRuntimeLockWidget(liveIndicatorValuesCheck);
    strategyGrid->addWidget(liveIndicatorValuesCheck, row, 0, 1, 6);

    ++row;
    auto *oneWayCheck = new QCheckBox("Add-only in current net direction (one-way)", strategyBox);
    registerRuntimeLockWidget(oneWayCheck);
    strategyGrid->addWidget(oneWayCheck, row, 0, 1, 6);

    ++row;
    auto *hedgeStackCheck = new QCheckBox("Allow simultaneous long & short positions (hedge stacking)", strategyBox);
    hedgeStackCheck->setChecked(true);
    registerRuntimeLockWidget(hedgeStackCheck);
    strategyGrid->addWidget(hedgeStackCheck, row, 0, 1, 6);

    ++row;
    auto *stopWithoutCloseCheck = new QCheckBox("Stop Bot Without Closing Active Positions", strategyBox);
    stopWithoutCloseCheck->setToolTip(
        "When checked, the Stop button will halt strategy threads but keep existing positions open."
    );
    dashboardStopWithoutCloseCheck_ = stopWithoutCloseCheck;
    registerRuntimeLockWidget(stopWithoutCloseCheck);
    strategyGrid->addWidget(stopWithoutCloseCheck, row, 0, 1, 6);

    ++row;
    auto *windowCloseCheck = new QCheckBox("Market Close All Active Positions On Window Close (Working in progress)", strategyBox);
    windowCloseCheck->setEnabled(false);
    strategyGrid->addWidget(windowCloseCheck, row, 0, 1, 6);

    ++row;
    strategyGrid->addWidget(new QLabel("Stop Loss:", strategyBox), row, 0);
    auto *stopLossEnable = new QCheckBox("Enable", strategyBox);
    dashboardStopLossEnableCheck_ = stopLossEnable;
    registerRuntimeLockWidget(stopLossEnable);
    strategyGrid->addWidget(stopLossEnable, row, 1);

    auto *stopModeCombo = new QComboBox(strategyBox);
    stopModeCombo->addItem("USDT Based Stop Loss", "usdt");
    stopModeCombo->addItem("Percentage Based Stop Loss", "percent");
    stopModeCombo->addItem("Both Stop Loss (USDT & Percentage)", "both");
    stopModeCombo->setCurrentIndex(0);
    dashboardStopLossModeCombo_ = stopModeCombo;
    strategyGrid->addWidget(stopModeCombo, row, 2, 1, 2);

    auto *stopUsdtSpin = new QDoubleSpinBox(strategyBox);
    stopUsdtSpin->setRange(0.0, 1'000'000'000.0);
    stopUsdtSpin->setDecimals(2);
    stopUsdtSpin->setSuffix(" USDT");
    stopUsdtSpin->setEnabled(false);
    dashboardStopLossUsdtSpin_ = stopUsdtSpin;
    strategyGrid->addWidget(stopUsdtSpin, row, 4);

    auto *stopPctSpin = new QDoubleSpinBox(strategyBox);
    stopPctSpin->setRange(0.0, 100.0);
    stopPctSpin->setDecimals(2);
    stopPctSpin->setSuffix(" %");
    stopPctSpin->setEnabled(false);
    dashboardStopLossPercentSpin_ = stopPctSpin;
    strategyGrid->addWidget(stopPctSpin, row, 5);

    ++row;
    strategyGrid->addWidget(new QLabel("Stop Loss Scope:", strategyBox), row, 0);
    auto *stopScopeCombo = new QComboBox(strategyBox);
    stopScopeCombo->addItems({"Per Trade Stop Loss", "Cumulative Stop Loss", "Entire Account Stop Loss"});
    dashboardStopLossScopeCombo_ = stopScopeCombo;
    strategyGrid->addWidget(stopScopeCombo, row, 1, 1, 2);

    connect(stopLossEnable, &QCheckBox::toggled, this, [this](bool) {
        updateDashboardStopLossWidgetState();
    });
    connect(stopModeCombo, &QComboBox::currentTextChanged, this, [this](const QString &) {
        updateDashboardStopLossWidgetState();
    });
    updateDashboardStopLossWidgetState();

    ++row;
    strategyGrid->addWidget(new QLabel("Template:", strategyBox), row, 0);
    auto *templateCombo = new QComboBox(strategyBox);
    templateCombo->addItem("No Template", "");
    templateCombo->addItem("Top 10 %2 per trade 5x Isolated", "top10");
    templateCombo->addItem("Top 50 %2 per trade 20x", "top50");
    templateCombo->addItem("Top 100 %1 per trade 5x", "top100");
    dashboardTemplateCombo_ = templateCombo;
    registerRuntimeLockWidget(templateCombo);
    connect(templateCombo, qOverload<int>(&QComboBox::currentIndexChanged), this, [this, templateCombo](int) {
        applyDashboardTemplate(templateCombo->currentData().toString());
    });
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
        if (!dashboardRuntimeLockWidgets_.contains(cb)) {
            dashboardRuntimeLockWidgets_.append(cb);
        }
        if (!dashboardRuntimeLockWidgets_.contains(btn)) {
            dashboardRuntimeLockWidgets_.append(btn);
        }
        btn->setMinimumWidth(150);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        QObject::connect(cb, &QCheckBox::toggled, btn, &QWidget::setEnabled);
        QObject::connect(btn, &QPushButton::clicked, this, [this, name]() { showIndicatorDialog(name); });
        const QString indicatorKey = normalizedIndicatorKey(name);
        if (!indicatorKey.trimmed().isEmpty()) {
            dashboardIndicatorChecks_.insert(indicatorKey, cb);
            dashboardIndicatorButtons_.insert(indicatorKey, btn);
            if (!dashboardIndicatorParams_.contains(indicatorKey)) {
                dashboardIndicatorParams_.insert(indicatorKey, QVariantMap{});
            }
        }
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

    auto *overridesBox = new QGroupBox("Symbol / Interval Overrides", page);
    auto *overridesLayout = new QVBoxLayout(overridesBox);
    overridesLayout->setContentsMargins(10, 10, 10, 10);
    overridesLayout->setSpacing(8);

    auto *overridesTable = new QTableWidget(overridesBox);
    registerRuntimeLockWidget(overridesTable);
    overridesTable->setColumnCount(8);
    overridesTable->setHorizontalHeaderLabels({
        "Symbol",
        "Interval",
        "Indicators",
        "Loop",
        "Leverage",
        "Connector",
        "Strategy Controls",
        "Stop-Loss",
    });
    overridesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    overridesTable->setSelectionMode(QAbstractItemView::ExtendedSelection);
    overridesTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    overridesTable->setMinimumHeight(200);
    overridesTable->setAlternatingRowColors(false);
    overridesTable->horizontalHeader()->setStretchLastSection(true);
    overridesLayout->addWidget(overridesTable);

    auto *overrideActions = new QHBoxLayout();
    overrideActions->setContentsMargins(0, 0, 0, 0);
    overrideActions->setSpacing(8);
    auto *addSelectedOverrideBtn = new QPushButton("Add Selected", overridesBox);
    auto *removeSelectedOverrideBtn = new QPushButton("Remove Selected", overridesBox);
    auto *clearOverridesBtn = new QPushButton("Clear All", overridesBox);
    registerRuntimeLockWidget(addSelectedOverrideBtn);
    registerRuntimeLockWidget(removeSelectedOverrideBtn);
    registerRuntimeLockWidget(clearOverridesBtn);
    overrideActions->addWidget(addSelectedOverrideBtn);
    overrideActions->addWidget(removeSelectedOverrideBtn);
    overrideActions->addWidget(clearOverridesBtn);
    overrideActions->addStretch();
    overridesLayout->addLayout(overrideActions);
    root->addWidget(overridesBox);

    auto *runtimeActions = new QHBoxLayout();
    runtimeActions->setContentsMargins(0, 4, 0, 0);
    runtimeActions->setSpacing(10);
    auto *dashStartBtn = new QPushButton("Start", page);
    auto *dashStopBtn = new QPushButton("Stop", page);
    dashStopBtn->setEnabled(false);
    auto *dashSaveBtn = new QPushButton("Save Config", page);
    auto *dashLoadBtn = new QPushButton("Load Config", page);
    registerRuntimeLockWidget(dashSaveBtn);
    registerRuntimeLockWidget(dashLoadBtn);
    runtimeActions->addWidget(dashStartBtn);
    runtimeActions->addWidget(dashStopBtn);
    runtimeActions->addWidget(dashSaveBtn);
    runtimeActions->addWidget(dashLoadBtn);
    root->addLayout(runtimeActions);

    auto *logsBox = new QGroupBox("Logs", page);
    auto *logsLayout = new QVBoxLayout(logsBox);
    logsLayout->setContentsMargins(10, 10, 10, 10);
    logsLayout->setSpacing(8);
    auto *logsTabs = new QTabWidget(logsBox);
    auto *allLogsEdit = new QTextEdit(logsTabs);
    auto *positionLogsEdit = new QTextEdit(logsTabs);
    for (QTextEdit *edit : {allLogsEdit, positionLogsEdit}) {
        edit->setReadOnly(true);
        edit->setMinimumHeight(130);
    }
    auto *waitingQueueTable = new QTableWidget(logsTabs);
    waitingQueueTable->setColumnCount(6);
    waitingQueueTable->setHorizontalHeaderLabels({
        "Symbol",
        "Interval",
        "Side",
        "Context",
        "State",
        "Age (s)",
    });
    waitingQueueTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    waitingQueueTable->setSelectionMode(QAbstractItemView::NoSelection);
    waitingQueueTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    waitingQueueTable->setFocusPolicy(Qt::NoFocus);
    waitingQueueTable->setMinimumHeight(130);
    waitingQueueTable->setAlternatingRowColors(false);
    if (auto *header = waitingQueueTable->horizontalHeader()) {
        header->setStretchLastSection(true);
        header->setSectionResizeMode(QHeaderView::Stretch);
    }
    if (auto *vHeader = waitingQueueTable->verticalHeader()) {
        vHeader->setVisible(false);
    }

    logsTabs->addTab(allLogsEdit, "All Logs");
    logsTabs->addTab(positionLogsEdit, "Position Trigger Logs");
    logsTabs->addTab(waitingQueueTable, "Waiting Positions (Queue)");
    logsLayout->addWidget(logsTabs);
    root->addWidget(logsBox);

    dashboardStartBtn_ = dashStartBtn;
    dashboardStopBtn_ = dashStopBtn;
    dashboardOverridesTable_ = overridesTable;
    dashboardAllLogsEdit_ = allLogsEdit;
    dashboardPositionLogsEdit_ = positionLogsEdit;
    dashboardWaitingLogsEdit_ = nullptr;
    dashboardWaitingQueueTable_ = waitingQueueTable;
    refreshDashboardWaitingQueueTable();

    auto appendLog = [allLogsEdit](const QString &msg) {
        const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
        allLogsEdit->append(QString("%1 %2").arg(ts, msg));
    };
    auto appendPositionLog = [positionLogsEdit](const QString &msg) {
        const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
        positionLogsEdit->append(QString("%1 %2").arg(ts, msg));
    };
    auto appendWaitingLog = [allLogsEdit](const QString &msg) {
        const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
        allLogsEdit->append(QString("%1 [Waiting] %2").arg(ts, msg));
    };

    auto enabledIndicatorsSummary = [this]() -> QString {
        QStringList enabled;
        for (auto it = dashboardIndicatorChecks_.cbegin(); it != dashboardIndicatorChecks_.cend(); ++it) {
            QCheckBox *cb = it.value();
            if (!cb || !cb->isChecked()) {
                continue;
            }
            enabled.append(cb->text().trimmed());
        }
        enabled.removeDuplicates();
        enabled.sort();
        return enabled.isEmpty() ? QStringLiteral("None") : enabled.join(", ");
    };

    auto stopLossSummary = [stopLossEnable, stopModeCombo, stopScopeCombo, stopUsdtSpin, stopPctSpin]() -> QString {
        if (!stopLossEnable || !stopLossEnable->isChecked()) {
            return QStringLiteral("Disabled");
        }
        QString modeKey = stopModeCombo ? stopModeCombo->currentData().toString().trimmed().toLower() : QString();
        if (modeKey.isEmpty()) {
            modeKey = QStringLiteral("usdt");
        }
        const QString modeText = stopModeCombo ? stopModeCombo->currentText().trimmed() : QString();
        QStringList values;
        if ((modeKey == "usdt" || modeKey == "both") && stopUsdtSpin && stopUsdtSpin->value() > 0.0) {
            values << QString("%1 USDT").arg(QString::number(stopUsdtSpin->value(), 'f', 2));
        }
        if ((modeKey == "percent" || modeKey == "both") && stopPctSpin && stopPctSpin->value() > 0.0) {
            values << QString("%1%").arg(QString::number(stopPctSpin->value(), 'f', 2));
        }
        const QString valueText = values.isEmpty() ? QStringLiteral("Enabled") : values.join(" / ");
        const QString scope = stopScopeCombo ? stopScopeCombo->currentText().trimmed() : QString();
        if (modeText.isEmpty() && scope.isEmpty()) {
            return valueText;
        }
        QStringList details;
        if (!modeText.isEmpty()) {
            details << modeText;
        }
        if (!scope.isEmpty()) {
            details << scope;
        }
        return QString("%1 (%2)").arg(valueText, details.join(" | "));
    };

    auto strategySummary = [sideCombo, enableLeadTrader, leadTraderCombo, liveIndicatorValuesCheck, oneWayCheck, hedgeStackCheck]() -> QString {
        QStringList values;
        if (sideCombo) {
            values << sideCombo->currentText().trimmed();
        }
        if (enableLeadTrader && enableLeadTrader->isChecked() && leadTraderCombo) {
            values << QString("Lead: %1").arg(leadTraderCombo->currentText().trimmed());
        }
        if (liveIndicatorValuesCheck && liveIndicatorValuesCheck->isChecked()) {
            values << QStringLiteral("Live candles");
        }
        if (oneWayCheck && oneWayCheck->isChecked()) {
            values << QStringLiteral("Add-only");
        }
        if (hedgeStackCheck && hedgeStackCheck->isChecked()) {
            values << QStringLiteral("Hedge stacking");
        }
        values.removeAll(QString());
        return values.isEmpty() ? QStringLiteral("Default") : values.join(" | ");
    };

    auto hasPair = [overridesTable](const QString &symbol, const QString &interval) -> bool {
        for (int rowIdx = 0; rowIdx < overridesTable->rowCount(); ++rowIdx) {
            const auto *symbolItem = overridesTable->item(rowIdx, 0);
            const auto *intervalItem = overridesTable->item(rowIdx, 1);
            if (!symbolItem || !intervalItem) {
                continue;
            }
            if (symbolItem->text().trimmed().compare(symbol, Qt::CaseInsensitive) == 0
                && intervalItem->text().trimmed().compare(interval, Qt::CaseInsensitive) == 0) {
                return true;
            }
        }
        return false;
    };

    auto addOverrideRow = [=](const QString &symbolRaw, const QString &intervalRaw) -> bool {
        const QString symbol = symbolRaw.trimmed().toUpper();
        const QString interval = intervalRaw.trimmed();
        if (symbol.isEmpty() || interval.isEmpty() || hasPair(symbol, interval)) {
            return false;
        }
        const int rowIdx = overridesTable->rowCount();
        overridesTable->insertRow(rowIdx);
        const QString connectorText = connectorCombo ? connectorCombo->currentText().trimmed() : QStringLiteral("Default");
        const QString loopText = loopOverride ? loopOverride->currentText().trimmed() : QStringLiteral("1 minute");
        const QString leverageText = dashboardLeverageSpin_ ? QString::number(dashboardLeverageSpin_->value()) : QStringLiteral("20");
        const QString indicatorsText = enabledIndicatorsSummary();
        const QString strategyText = strategySummary();
        const QString slText = stopLossSummary();
        const QStringList values = {
            symbol,
            interval,
            indicatorsText,
            loopText,
            leverageText,
            connectorText,
            strategyText,
            slText,
        };
        for (int col = 0; col < values.size(); ++col) {
            overridesTable->setItem(rowIdx, col, new QTableWidgetItem(values.at(col)));
        }
        return true;
    };

    connect(addSelectedOverrideBtn, &QPushButton::clicked, this, [=]() {
        QStringList selectedSymbols;
        QStringList selectedIntervals;
        if (dashboardSymbolList_) {
            for (auto *item : dashboardSymbolList_->selectedItems()) {
                if (item) {
                    selectedSymbols.append(item->text().trimmed().toUpper());
                }
            }
        }
        if (dashboardIntervalList_) {
            for (auto *item : dashboardIntervalList_->selectedItems()) {
                if (item) {
                    selectedIntervals.append(item->text().trimmed());
                }
            }
        }

        selectedSymbols.removeAll(QString());
        selectedIntervals.removeAll(QString());
        selectedSymbols.removeDuplicates();
        selectedIntervals.removeDuplicates();

        if (selectedSymbols.isEmpty() || selectedIntervals.isEmpty()) {
            QMessageBox::information(this, tr("Overrides"), tr("Select at least one symbol and one interval first."));
            return;
        }

        int addedCount = 0;
        for (const QString &sym : selectedSymbols) {
            for (const QString &intv : selectedIntervals) {
                if (addOverrideRow(sym, intv)) {
                    ++addedCount;
                }
            }
        }
        updateStatusMessage(QString("Overrides updated: added %1 row(s).").arg(addedCount));
        appendLog(QString("Override rows added: %1").arg(addedCount));
        appendWaitingLog(QString("Queued symbol/interval overrides: +%1").arg(addedCount));
    });

    connect(removeSelectedOverrideBtn, &QPushButton::clicked, this, [=]() {
        QSet<int> selectedRows;
        const auto selected = overridesTable->selectedItems();
        for (auto *item : selected) {
            if (item) {
                selectedRows.insert(item->row());
            }
        }
        QList<int> rows = selectedRows.values();
        std::sort(rows.begin(), rows.end(), std::greater<int>());
        for (int rowIdx : rows) {
            overridesTable->removeRow(rowIdx);
        }
        updateStatusMessage(QString("Overrides updated: removed %1 row(s).").arg(rows.size()));
        appendLog(QString("Override rows removed: %1").arg(rows.size()));
    });

    connect(clearOverridesBtn, &QPushButton::clicked, this, [=]() {
        const int rowCount = overridesTable->rowCount();
        overridesTable->setRowCount(0);
        updateStatusMessage(QString("Overrides cleared (%1 row(s)).").arg(rowCount));
        appendLog(QString("Override rows cleared: %1").arg(rowCount));
        appendWaitingLog(QString("Queue cleared (%1 row(s)).").arg(rowCount));
    });

    connect(dashStartBtn, &QPushButton::clicked, this, [this]() {
        startDashboardRuntime();
    });
    connect(dashStopBtn, &QPushButton::clicked, this, [this]() {
        stopDashboardRuntime();
    });

    connect(dashSaveBtn, &QPushButton::clicked, this, [=]() {
        const QString filePath = QFileDialog::getSaveFileName(
            this,
            tr("Save Dashboard Config"),
            QDir::homePath() + "/dashboard_overrides.json",
            tr("JSON Files (*.json);;All Files (*)"));
        if (filePath.trimmed().isEmpty()) {
            return;
        }

        QJsonArray rowsJson;
        for (int rowIdx = 0; rowIdx < overridesTable->rowCount(); ++rowIdx) {
            QJsonObject rowObj;
            rowObj.insert("symbol", overridesTable->item(rowIdx, 0) ? overridesTable->item(rowIdx, 0)->text() : QString());
            rowObj.insert("interval", overridesTable->item(rowIdx, 1) ? overridesTable->item(rowIdx, 1)->text() : QString());
            rowObj.insert("indicators", overridesTable->item(rowIdx, 2) ? overridesTable->item(rowIdx, 2)->text() : QString());
            rowObj.insert("loop", overridesTable->item(rowIdx, 3) ? overridesTable->item(rowIdx, 3)->text() : QString());
            rowObj.insert("leverage", overridesTable->item(rowIdx, 4) ? overridesTable->item(rowIdx, 4)->text() : QString());
            rowObj.insert("connector", overridesTable->item(rowIdx, 5) ? overridesTable->item(rowIdx, 5)->text() : QString());
            rowObj.insert("strategy_controls", overridesTable->item(rowIdx, 6) ? overridesTable->item(rowIdx, 6)->text() : QString());
            rowObj.insert("stop_loss", overridesTable->item(rowIdx, 7) ? overridesTable->item(rowIdx, 7)->text() : QString());
            rowsJson.append(rowObj);
        }
        QJsonObject payload;
        payload.insert("overrides", rowsJson);
        payload.insert("saved_at", QDateTime::currentDateTime().toString(Qt::ISODate));

        QFile out(filePath);
        if (!out.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
            QMessageBox::warning(this, tr("Save failed"), tr("Could not write %1").arg(filePath));
            return;
        }
        out.write(QJsonDocument(payload).toJson(QJsonDocument::Indented));
        out.close();
        updateStatusMessage(QString("Dashboard config saved: %1").arg(filePath));
        appendLog(QString("Dashboard config saved to %1").arg(filePath));
    });

    connect(dashLoadBtn, &QPushButton::clicked, this, [=]() {
        const QString filePath = QFileDialog::getOpenFileName(
            this,
            tr("Load Dashboard Config"),
            QDir::homePath(),
            tr("JSON Files (*.json);;All Files (*)"));
        if (filePath.trimmed().isEmpty()) {
            return;
        }

        QFile in(filePath);
        if (!in.open(QIODevice::ReadOnly | QIODevice::Text)) {
            QMessageBox::warning(this, tr("Load failed"), tr("Could not read %1").arg(filePath));
            return;
        }
        QJsonParseError parseError{};
        const QJsonDocument doc = QJsonDocument::fromJson(in.readAll(), &parseError);
        in.close();
        if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
            QMessageBox::warning(this, tr("Load failed"), tr("Invalid JSON file."));
            return;
        }

        const QJsonArray rowsJson = doc.object().value("overrides").toArray();
        overridesTable->setRowCount(0);
        int loadedCount = 0;
        for (const QJsonValue &value : rowsJson) {
            const QJsonObject rowObj = value.toObject();
            const QString symbol = rowObj.value("symbol").toString().trimmed().toUpper();
            const QString interval = rowObj.value("interval").toString().trimmed();
            if (symbol.isEmpty() || interval.isEmpty()) {
                continue;
            }
            const int rowIdx = overridesTable->rowCount();
            overridesTable->insertRow(rowIdx);
            const QStringList values = {
                symbol,
                interval,
                rowObj.value("indicators").toString(),
                rowObj.value("loop").toString(),
                rowObj.value("leverage").toString(),
                rowObj.value("connector").toString(),
                rowObj.value("strategy_controls").toString(),
                rowObj.value("stop_loss").toString(),
            };
            for (int col = 0; col < values.size(); ++col) {
                overridesTable->setItem(rowIdx, col, new QTableWidgetItem(values.at(col)));
            }
            ++loadedCount;
        }
        updateStatusMessage(QString("Dashboard config loaded: %1 row(s).").arg(loadedCount));
        appendLog(QString("Dashboard config loaded from %1 (%2 row(s)).").arg(filePath).arg(loadedCount));
        appendWaitingLog(QString("Queue restored with %1 row(s).").arg(loadedCount));
    });

    appendLog("Dashboard overrides and log sections are ready.");

    root->addStretch();

    setDashboardRuntimeControlsEnabled(true);
    applyDashboardTheme(dashboardThemeCombo_ ? dashboardThemeCombo_->currentText() : QString());
    return page;
}

void TradingBotWindow::applyDashboardTheme(const QString &themeName) {
    if (!dashboardPage_) {
        return;
    }

    QString themeNorm = themeName.trimmed().toLower();
    if (themeNorm == QStringLiteral("gren")) {
        themeNorm = QStringLiteral("green");
    }
    const bool isLight = themeNorm == QStringLiteral("light");
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
        #dashboardPage QLineEdit:disabled, #dashboardPage QComboBox:disabled, #dashboardPage QDoubleSpinBox:disabled,
        #dashboardPage QSpinBox:disabled, #dashboardPage QDateEdit:disabled, #dashboardPage QListWidget:disabled {
            background: #0b1020; color: #94a3b8; border: 1px solid #334155;
        }
        #dashboardPage QPushButton:disabled {
            background: #101826; color: #94a3b8; border: 1px solid #334155;
        }
        #dashboardPage QCheckBox:disabled { color: #9ca3af; }
        #dashboardPage QCheckBox::indicator:disabled { background: #0b1020; border: 1px solid #475569; }
        #dashboardPage QCheckBox::indicator:checked:disabled {
            background: #2563eb; border-color: #2563eb;
            image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
        }
        #dashboardPage QComboBox::drop-down:disabled, #dashboardPage QDateEdit::drop-down:disabled,
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QSpinBox::down-button:disabled,
        #dashboardPage QDoubleSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::down-button:disabled {
            background: #101826; border-left: 1px solid #334155;
        }
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::up-button:disabled {
            border-bottom: 1px solid #334155;
        }
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
        #dashboardPage QLineEdit:disabled, #dashboardPage QComboBox:disabled, #dashboardPage QDoubleSpinBox:disabled,
        #dashboardPage QSpinBox:disabled, #dashboardPage QDateEdit:disabled, #dashboardPage QListWidget:disabled {
            background: #eef2f7; color: #64748b; border: 1px solid #94a3b8;
        }
        #dashboardPage QPushButton:disabled {
            background: #e5e7eb; color: #64748b; border: 1px solid #94a3b8;
        }
        #dashboardPage QCheckBox:disabled { color: #6b7280; }
        #dashboardPage QCheckBox::indicator:disabled { background: #f8fafc; border: 1px solid #94a3b8; }
        #dashboardPage QCheckBox::indicator:checked:disabled {
            background: #2563eb; border-color: #2563eb;
            image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
        }
        #dashboardPage QComboBox::drop-down:disabled, #dashboardPage QDateEdit::drop-down:disabled,
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QSpinBox::down-button:disabled,
        #dashboardPage QDoubleSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::down-button:disabled {
            background: #e5e7eb; border-left: 1px solid #94a3b8;
        }
        #dashboardPage QSpinBox::up-button:disabled, #dashboardPage QDoubleSpinBox::up-button:disabled {
            border-bottom: 1px solid #94a3b8;
        }
    )";

    const QString darkGlobal = R"(
        QMainWindow { background: #0b0f16; }
        QTabWidget::pane { border: 1px solid #1f2937; background: #0b0f16; }
        QTabBar::tab { background: #111827; color: #e5e7eb; padding: 6px 10px; }
        QTabBar::tab:selected { background: #1f2937; }
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage, QWidget#dashboardPage, QWidget#liquidationPage { background: #0b0f16; color: #e5e7eb; }
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
        QWidget#chartPage, QWidget#positionsPage, QWidget#backtestPage, QWidget#codePage, QWidget#dashboardPage, QWidget#liquidationPage { background: #f5f7fb; color: #0f172a; }
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

    QString accent;
    QString accentHover;
    QString accentPressed;
    QString accentOutline;
    QString accentText = QStringLiteral("#ffffff");
    if (themeNorm == QStringLiteral("blue")) {
        accent = QStringLiteral("#2563eb");
        accentHover = QStringLiteral("#3b82f6");
        accentPressed = QStringLiteral("#1d4ed8");
        accentOutline = QStringLiteral("#1e40af");
    } else if (themeNorm == QStringLiteral("yellow")) {
        accent = QStringLiteral("#fbbf24");
        accentHover = QStringLiteral("#fcd34d");
        accentPressed = QStringLiteral("#d97706");
        accentOutline = QStringLiteral("#92400e");
        accentText = QStringLiteral("#0c0f16");
    } else if (themeNorm == QStringLiteral("green")) {
        accent = QStringLiteral("#22c55e");
        accentHover = QStringLiteral("#4ade80");
        accentPressed = QStringLiteral("#16a34a");
        accentOutline = QStringLiteral("#166534");
    } else if (themeNorm == QStringLiteral("red")) {
        accent = QStringLiteral("#ef4444");
        accentHover = QStringLiteral("#f87171");
        accentPressed = QStringLiteral("#dc2626");
        accentOutline = QStringLiteral("#991b1b");
    }

    QString accentCss;
    if (!accent.isEmpty()) {
        const QColor accentColor(accent);
        if (accentColor.isValid()) {
            accentOutline = accentColor.darker(230).name();
        }
        const QString hoverFill = QStringLiteral("rgba(%1, %2, %3, 52)")
                                      .arg(accentColor.red())
                                      .arg(accentColor.green())
                                      .arg(accentColor.blue());
        const QString controlBg = isLight ? QStringLiteral("#ffffff") : QStringLiteral("#0d1117");
        const QString controlHoverBg = isLight ? QStringLiteral("#f8fafc") : QStringLiteral("#18202d");
        const QString headerBg = isLight ? QStringLiteral("#f1f5f9") : QStringLiteral("#111827");
        const QString disabledBg = isLight ? QStringLiteral("#f1f5f9") : QStringLiteral("#0b1020");
        const QString disabledBorder = isLight ? QStringLiteral("#d1d5db") : QStringLiteral("#1f2937");
        const QString baseText = isLight ? QStringLiteral("#0f172a") : QStringLiteral("#e5e7eb");

        accentCss = QStringLiteral(
                        "QPushButton { background-color: %1; border: 1px solid %1; color: %4; }"
                        "QPushButton:hover { background-color: %2; border-color: %2; }"
                        "QPushButton:pressed, QPushButton:checked { background-color: %3; border-color: %3; }"
                        "QPushButton:disabled { background-color: %9; border: 1px solid %10; color: #808080; }"
                        "QLineEdit QToolButton, QComboBox QToolButton, QAbstractSpinBox QToolButton {"
                        "background: transparent; border: none; padding: 0px; margin: 0px; }"
                        "QLineEdit QToolButton:hover, QComboBox QToolButton:hover, QAbstractSpinBox QToolButton:hover {"
                        "background: transparent; border: none; }"
                        "QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QPlainTextEdit {"
                        "selection-background-color: %1; selection-color: %4; }"
                        "QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover "
                        "{ border: 1px solid %1; }"
                        "QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus "
                        "{ border: 1px solid %1; outline: none; }"
                        "QCheckBox::indicator:checked { background-color: %1; border-color: %1; }"
                        "QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %1; }"
                        "QRadioButton::indicator:checked { background-color: %1; border: 1px solid %1; }"
                        "QTabBar::tab:selected { background-color: %1; border: 1px solid %1; color: %4; }"
                        "QTabBar::tab:hover { border: 1px solid %1; }"
                        "QTabWidget::pane { border: 1px solid %5; }"
                        "QGroupBox::title { color: %1; }"
                        "QGroupBox { border: 1px solid %5; }"
                        "QAbstractItemView { selection-background-color: %1; selection-color: %4; }"
                        "QAbstractItemView::item:selected { background-color: %1; color: %4; }"
                        "QAbstractItemView::item:hover { background-color: %6; color: %11; }"
                        "QHeaderView::section { background-color: %12; border: 1px solid %5; }"
                        "QProgressBar { border: 1px solid %5; background-color: %7; }"
                        "QProgressBar::chunk { background-color: %1; }"
                        "QSlider::handle:horizontal, QSlider::handle:vertical { background: %1; border: 1px solid %5; }"
                        "QSlider::sub-page:horizontal, QSlider::sub-page:vertical { background: %1; }"
                        "QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: %2; border: 1px solid %5; border-radius: 4px; }"
                        "QMenu::item:selected { background-color: %1; color: %4; }")
                        .arg(accent)
                        .arg(accentHover)
                        .arg(accentPressed)
                        .arg(accentText)
                        .arg(accentOutline)
                        .arg(hoverFill)
                        .arg(controlBg)
                        .arg(controlHoverBg)
                        .arg(disabledBg)
                        .arg(disabledBorder)
                        .arg(baseText)
                        .arg(headerBg);
    }

    // Apply to the whole window (covers Chart/Positions/Backtest/Code tabs)
    this->setStyleSheet((isLight ? lightGlobal : darkGlobal) + accentCss);

    // Apply dashboard-specific overrides
    dashboardPage_->setStyleSheet((isLight ? lightCss : darkCss) + accentCss);

    // Apply code tab readability (headings + content on matching background)
    if (codePage_) {
        QString codeCss = isLight
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
        codeCss += accentCss;
        codePage_->setStyleSheet(codeCss);
    }
}

QWidget *TradingBotWindow::createChartTab() {
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
    chartStack->setMinimumHeight(560);
    chartStack->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    layout->addWidget(chartStack, 1);

    auto *originalPage = new QWidget(chartStack);
    originalPage->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    auto *originalLayout = new QVBoxLayout(originalPage);
    originalLayout->setContentsMargins(0, 0, 0, 0);
#if HAS_QT_WEBENGINE
    auto *binanceView = new QWebEngineView(originalPage);
    binanceView->setContextMenuPolicy(Qt::NoContextMenu);
    binanceView->setMinimumHeight(520);
    binanceView->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    originalLayout->addWidget(binanceView, 1);
#else
    auto *chartWidget = new NativeKlineChartWidget(originalPage);
    originalLayout->addWidget(chartWidget, 1);
#endif
    chartStack->addWidget(originalPage);

    auto *tradingPage = new QWidget(chartStack);
    tradingPage->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    auto *tradingLayout = new QVBoxLayout(tradingPage);
    tradingLayout->setContentsMargins(0, 0, 0, 0);
    tradingLayout->setSpacing(8);
#if HAS_QT_WEBENGINE
    auto *tradingView = new ResizeAwareWebEngineView(tradingPage);
    tradingView->setMinimumHeight(560);
    tradingView->setContextMenuPolicy(Qt::NoContextMenu);
    tradingLayout->addWidget(tradingView, 1);
    auto syncTradingViewEmbed = [tradingView]() {
        if (!tradingView || !tradingView->page()) {
            return;
        }
        const int hostHeight = std::max(560, tradingView->height());
        const QString js = QStringLiteral(R"JS(
(function(hostHeight) {
  if (typeof window.__tv_sync_host === "function") {
    window.__tv_sync_host(hostHeight);
  }
})(%1);
        )JS").arg(hostHeight);
        tradingView->page()->runJavaScript(js);
    };
    auto *tradingViewResizeTimer = new QTimer(tradingView);
    tradingViewResizeTimer->setSingleShot(true);
    tradingViewResizeTimer->setInterval(90);
    connect(tradingViewResizeTimer, &QTimer::timeout, tradingPage, [syncTradingViewEmbed]() {
        syncTradingViewEmbed();
    });
    tradingView->setResizeCallback([tradingViewResizeTimer]() {
        tradingViewResizeTimer->start();
    });
    connect(tradingView, &QWebEngineView::loadFinished, tradingPage, [tradingView, syncTradingViewEmbed](bool ok) {
        if (!ok) {
            return;
        }
        syncTradingViewEmbed();
        QTimer::singleShot(120, tradingView, [syncTradingViewEmbed]() {
            syncTradingViewEmbed();
        });
        QTimer::singleShot(500, tradingView, [syncTradingViewEmbed]() {
            syncTradingViewEmbed();
        });
    });
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

    struct ChartRefreshState {
        bool initialized = false;
        bool dirty = true;
        QString mode;
        QString market;
        QString symbol;
        QString interval;
    };
    auto refreshState = std::make_shared<ChartRefreshState>();

    std::function<void(bool)> refreshCurrent;

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
        const bool isTestnet = dashboardModeCombo_ ? isTestnetModeLabel(dashboardModeCombo_->currentText()) : false;
        const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
        const ConnectorRuntimeConfig connectorCfg = resolveConnectorConfig(connectorText, futures);

        const auto result = connectorCfg.ok()
            ? BinanceRestClient::fetchUsdtSymbols(futures, isTestnet, 12000, false, 0, connectorCfg.baseUrl)
            : BinanceRestClient::SymbolsResult{false, {}, connectorCfg.error};
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
    refreshOriginal = [this, status, marketCombo, intervalCombo, currentRawSymbol, chartWidget]() {
        const QString rawSymbol = normalizeChartSymbol(currentRawSymbol());
        if (rawSymbol.isEmpty()) {
            status->setText("Select a symbol, then refresh.");
            chartWidget->setCandles({});
            chartWidget->setOverlayMessage("Symbol is required.");
            return;
        }
        const bool futures = marketCombo->currentData().toString() == "futures";
        const bool isTestnet = dashboardModeCombo_ ? isTestnetModeLabel(dashboardModeCombo_->currentText()) : false;
        const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
        const ConnectorRuntimeConfig connectorCfg = resolveConnectorConfig(connectorText, futures);
        if (!connectorCfg.ok()) {
            chartWidget->setCandles({});
            chartWidget->setOverlayMessage(connectorCfg.error);
            status->setText(QString("Original chart load failed: %1").arg(connectorCfg.error));
            return;
        }
        const QString interval = intervalCombo->currentText().trimmed();
        const auto result = BinanceRestClient::fetchKlines(
            rawSymbol,
            interval,
            futures,
            isTestnet,
            320,
            12000,
            connectorCfg.baseUrl);
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
        const int hostHeight = std::max(560, tradingView->height());
        const QString html = QStringLiteral(R"(
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    html, body {
      margin: 0;
      padding: 0;
      width: 100%%;
      height: 100%%;
      overflow: hidden;
      background: #0b1020;
      color: #d1d4dc;
      font-family: "Segoe UI", sans-serif;
    }
    #tv_container {
      position: absolute;
      inset: 0;
      width: 100%%;
      height: 100%%;
      min-height: %3px;
    }
    #tv_container iframe {
      width: 100%% !important;
      height: 100%% !important;
      min-height: %3px !important;
    }
    #fallback {
      display: none;
      align-items: center;
      justify-content: center;
      width: 100%%;
      height: 100%%;
      background: #0b1020;
      color: #94a3b8;
      font-size: 14px;
    }
    ::-webkit-scrollbar { width: 0px; height: 0px; display: none; }
  </style>
</head>
<body>
  <script type="text/javascript">
    window.open = function(_url) { return null; };
    window.close = function() { return false; };
  </script>
  <div id="tv_container"></div>
  <div id="fallback">Loading TradingView...</div>
  <script type="text/javascript">
    (function() {
      const minimumHeight = %3;

      function resolveHeight(requested) {
        const viewport = Math.max(
          window.innerHeight || 0,
          document.documentElement ? document.documentElement.clientHeight : 0,
          document.body ? document.body.clientHeight : 0,
          minimumHeight);
        return Math.max(minimumHeight, requested || 0, viewport);
      }

      function syncHostSize(requested) {
        const height = resolveHeight(requested);
        [document.documentElement, document.body, document.getElementById("tv_container")].forEach(function(el) {
          if (!el) {
            return;
          }
          el.style.width = "100%%";
          el.style.height = height + "px";
          el.style.minHeight = height + "px";
          el.style.overflow = "hidden";
        });
        const iframe = document.querySelector("#tv_container iframe");
        if (iframe) {
          iframe.style.width = "100%%";
          iframe.style.height = height + "px";
          iframe.style.minHeight = height + "px";
        }
        return height;
      }

      window.__tv_sync_host = syncHostSize;

      function ensureTradingView(callback) {
        if (window.TradingView && typeof window.TradingView.widget === "function") {
          callback();
          return;
        }
        setTimeout(function() { ensureTradingView(callback); }, 120);
      }

      function mountWidget() {
        ensureTradingView(function() {
          try {
            document.getElementById("fallback").style.display = "none";
            const resolvedHeight = syncHostSize();
            new TradingView.widget({
              "autosize": true,
              "width": "100%%",
              "height": resolvedHeight,
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
              "container_id": "tv_container",
              "support_host": "https://www.tradingview.com"
            });
            syncHostSize(resolvedHeight);
            setTimeout(function() { syncHostSize(resolvedHeight); }, 120);
            setTimeout(function() { syncHostSize(resolvedHeight); }, 600);
            window.addEventListener("resize", function() { syncHostSize(); }, { passive: true });
            if (typeof ResizeObserver === "function") {
              const observer = new ResizeObserver(function() { syncHostSize(); });
              observer.observe(document.documentElement);
              observer.observe(document.body);
            }
          } catch (_err) {
            const fallback = document.getElementById("fallback");
            if (fallback) {
              fallback.style.display = "flex";
              fallback.textContent = "TradingView failed to load.";
            }
          }
        });
      }

      const fallback = document.getElementById("fallback");
      if (fallback) {
        fallback.style.display = "flex";
      }
      mountWidget();
    })();
  </script>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
</body>
</html>
        )").arg(rawSymbol, tvInterval, QString::number(hostHeight));
        tradingView->setHtml(html, QUrl("https://www.tradingview.com/"));
        status->setText(QString("TradingView loaded: %1 (%2)").arg(rawSymbol, intervalCombo->currentText()));
    };
#else
    refreshTradingView = [status]() {
        status->setText("TradingView embed unavailable: Qt WebEngine is not installed in this build.");
    };
#endif

    refreshCurrent = [refreshOriginal,
                      refreshTradingView,
                      viewModeCombo,
                      chartStack,
                      originalPage,
                      tradingPage,
                      marketCombo,
                      intervalCombo,
                      currentRawSymbol,
                      refreshState](bool force) {
        const QString mode = viewModeCombo->currentData().toString();
        const QString market = marketCombo->currentData().toString();
        const QString symbol = normalizeChartSymbol(currentRawSymbol());
        const QString interval = intervalCombo->currentText().trimmed();
        const bool changed = !refreshState->initialized
            || refreshState->mode != mode
            || refreshState->market != market
            || refreshState->symbol != symbol
            || refreshState->interval != interval;
        if (!force && !refreshState->dirty && !changed) {
            return;
        }
        if (mode == "tradingview") {
            chartStack->setCurrentWidget(tradingPage);
            refreshTradingView();
        } else {
            chartStack->setCurrentWidget(originalPage);
            refreshOriginal();
        }
        refreshState->mode = mode;
        refreshState->market = market;
        refreshState->symbol = symbol;
        refreshState->interval = interval;
        refreshState->initialized = true;
        refreshState->dirty = false;
    };

    auto markDirtyAndRefreshIfVisible = [this, page, refreshCurrent, refreshState](bool force) {
        refreshState->dirty = true;
        if (force || (tabs_ && tabs_->currentWidget() == page)) {
            refreshCurrent(force);
        }
    };

    auto syncFromDashboard = [this, page, symbolCombo, intervalCombo, refreshCurrent, refreshState]() {
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
            refreshState->dirty = true;
        }
        const bool chartVisible = tabs_ && tabs_->currentWidget() == page;
        if (changed && chartVisible) {
            refreshCurrent(false);
        }
    };

    connect(refreshBtn, &QPushButton::clicked, page, [markDirtyAndRefreshIfVisible]() {
        markDirtyAndRefreshIfVisible(true);
    });
    connect(symbolCombo, &QComboBox::currentTextChanged, page, [markDirtyAndRefreshIfVisible](const QString &) {
        markDirtyAndRefreshIfVisible(false);
    });
    connect(intervalCombo, &QComboBox::currentTextChanged, page, [markDirtyAndRefreshIfVisible](const QString &) {
        markDirtyAndRefreshIfVisible(false);
    });
    connect(viewModeCombo, &QComboBox::currentTextChanged, page, [markDirtyAndRefreshIfVisible](const QString &) {
        markDirtyAndRefreshIfVisible(false);
    });
    connect(marketCombo, &QComboBox::currentTextChanged, page, [loadSymbols, markDirtyAndRefreshIfVisible](const QString &) {
        loadSymbols();
        markDirtyAndRefreshIfVisible(false);
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
            refreshCurrent(false);
        }
    });
    if (tabs_) {
        connect(tabs_, &QTabWidget::currentChanged, page, [this, page, refreshCurrent](int) {
            if (tabs_ && tabs_->currentWidget() == page) {
                refreshCurrent(false);
            }
        });
    }

    return page;
}

QWidget *TradingBotWindow::createPositionsTab() {
    auto *page = new QWidget(this);
    page->setObjectName("positionsPage");
    positionsPnlActiveLabel_ = nullptr;
    positionsPnlClosedLabel_ = nullptr;
    positionsTotalBalanceLabel_ = nullptr;
    positionsAvailableBalanceLabel_ = nullptr;
    positionsBotStatusLabel_ = nullptr;
    positionsBotTimeLabel_ = nullptr;
    auto *layout = new QVBoxLayout(page);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(12);

    auto *ctrlLayout = new QHBoxLayout();
    ctrlLayout->setContentsMargins(0, 0, 0, 0);
    ctrlLayout->setSpacing(8);

    auto *refreshPosBtn = new QPushButton("Refresh Positions", page);
    auto *closeAllBtn = new QPushButton("Market Close ALL Positions", page);
    auto *positionsViewLabel = new QLabel("Positions View:", page);
    auto *positionsViewCombo = new QComboBox(page);
    positionsViewCombo->addItems({"Cumulative View", "Per Trade View"});
    positionsViewCombo->setCurrentIndex(0);
    positionsViewCombo_ = positionsViewCombo;
    positionsCumulativeView_ = true;
    auto *autoRowHeightCheck = new QCheckBox("Auto Row Height", page);
    autoRowHeightCheck->setToolTip("Resize rows to fit multi-line indicator values.");
    autoRowHeightCheck->setChecked(true);
    positionsAutoRowHeightCheck_ = autoRowHeightCheck;
    auto *autoColumnWidthCheck = new QCheckBox("Auto Column Width", page);
    autoColumnWidthCheck->setToolTip("Resize columns to fit full indicator text.");
    autoColumnWidthCheck->setChecked(true);
    positionsAutoColumnWidthCheck_ = autoColumnWidthCheck;

    ctrlLayout->addWidget(refreshPosBtn);
    ctrlLayout->addWidget(closeAllBtn);
    ctrlLayout->addWidget(positionsViewLabel);
    ctrlLayout->addWidget(positionsViewCombo);
    ctrlLayout->addWidget(autoRowHeightCheck);
    ctrlLayout->addWidget(autoColumnWidthCheck);
    ctrlLayout->addStretch();
    layout->addLayout(ctrlLayout);

    auto *statusWidget = new QWidget(page);
    statusWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    auto *statusLayout = new QHBoxLayout(statusWidget);
    statusLayout->setContentsMargins(0, 0, 0, 0);
    statusLayout->setSpacing(12);

    auto *pnlActiveLabel = new QLabel("Total PNL Active Positions: --", statusWidget);
    auto *pnlClosedLabel = new QLabel("Total PNL Closed Positions: --", statusWidget);
    auto *totalBalanceLabel = new QLabel("Total Balance: --", statusWidget);
    auto *availableBalanceLabel = new QLabel("Available Balance: --", statusWidget);
    auto *botStatusLabel = new QLabel("Bot Status: OFF", statusWidget);
    auto *botTimeLabel = new QLabel("Bot Active Time: --", statusWidget);
    positionsPnlActiveLabel_ = pnlActiveLabel;
    positionsPnlClosedLabel_ = pnlClosedLabel;
    positionsTotalBalanceLabel_ = totalBalanceLabel;
    positionsAvailableBalanceLabel_ = availableBalanceLabel;
    positionsBotStatusLabel_ = botStatusLabel;
    positionsBotTimeLabel_ = botTimeLabel;

    for (QLabel *lbl : {pnlActiveLabel, pnlClosedLabel, totalBalanceLabel, availableBalanceLabel}) {
        lbl->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
        lbl->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        statusLayout->addWidget(lbl);
    }
    statusLayout->addStretch();
    for (QLabel *lbl : {botStatusLabel, botTimeLabel}) {
        lbl->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
        lbl->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Preferred);
        statusLayout->addWidget(lbl);
    }
    layout->addWidget(statusWidget);

    auto *table = new QTableWidget(0, 18, page);
    positionsTable_ = table;
    table->setHorizontalHeaderLabels({
        "Symbol",
        "Size",
        "Last Price (USDT)",
        "Margin Ratio",
        "Liq Price (USDT)",
        "Margin (USDT)",
        "Quantity",
        "PNL (ROI%)",
        "Interval",
        "Indicator",
        "Triggered Indicator Value",
        "Current Indicator Value",
        "Side",
        "Open Time",
        "Close Time",
        "Stop-Loss",
        "Status",
        "Close",
    });
    auto *posHeader = table->horizontalHeader();
    posHeader->setStretchLastSection(true);
    posHeader->setSectionsMovable(true);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table->setSortingEnabled(true);
    table->setWordWrap(true);
    table->setTextElideMode(Qt::ElideNone);
    table->verticalHeader()->setDefaultSectionSize(44);
    layout->addWidget(table, 1);

    auto *buttonsLayout = new QHBoxLayout();
    buttonsLayout->setContentsMargins(0, 0, 0, 0);
    buttonsLayout->setSpacing(8);
    auto *clearSelectedBtn = new QPushButton("Clear Selected", page);
    auto *clearAllBtn = new QPushButton("Clear All", page);
    buttonsLayout->addWidget(clearSelectedBtn);
    buttonsLayout->addWidget(clearAllBtn);
    buttonsLayout->addStretch();
    layout->addLayout(buttonsLayout);

    refreshPositionsTableSizing();

    connect(refreshPosBtn, &QPushButton::clicked, this, [=]() {
        const bool futuresMode = dashboardAccountTypeCombo_
            ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
            : true;
        if (!futuresMode) {
            updateStatusMessage("Positions refresh currently supports Futures account only.");
            return;
        }

        const QString mode = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
        if (isPaperTradingModeLabel(mode)) {
            const double paperBalance = currentDashboardPaperBalanceUsdt();
            positionsLastTotalBalanceUsdt_ = paperBalance;
            positionsLastAvailableBalanceUsdt_ = paperBalance;
            updateStatusMessage(QStringLiteral("Positions refresh synced from local paper positions."));
            applyPositionsViewMode();
            return;
        }

        const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
        const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
        if (apiKey.isEmpty() || apiSecret.isEmpty()) {
            updateStatusMessage("Positions refresh skipped: missing API credentials.");
            return;
        }

        const bool isTestnet = dashboardModeCombo_ ? isTestnetModeLabel(dashboardModeCombo_->currentText()) : false;
        const QString connectorText = dashboardConnectorCombo_
            ? dashboardConnectorCombo_->currentText().trimmed()
            : connectorLabelForKey(recommendedConnectorKey(true));
        const ConnectorRuntimeConfig connectorCfg = resolveConnectorConfig(connectorText, true);
        if (!connectorCfg.ok()) {
            updateStatusMessage(QString("Positions refresh connector error: %1").arg(connectorCfg.error));
            return;
        }

        const auto livePositions = BinanceRestClient::fetchOpenFuturesPositions(
            apiKey,
            apiSecret,
            isTestnet,
            10000,
            connectorCfg.baseUrl);
        if (!livePositions.ok) {
            updateStatusMessage(QString("Positions refresh failed: %1").arg(livePositions.error));
            return;
        }
        const auto balance = BinanceRestClient::fetchUsdtBalance(
            apiKey,
            apiSecret,
            true,
            isTestnet,
            10000,
            connectorCfg.baseUrl);
        if (balance.ok) {
            const double totalBalance = std::max(
                0.0,
                (balance.totalUsdtBalance > 0.0) ? balance.totalUsdtBalance : balance.usdtBalance);
            const double availableBalance = std::max(
                0.0,
                (balance.availableUsdtBalance > 0.0) ? balance.availableUsdtBalance : totalBalance);
            positionsLastTotalBalanceUsdt_ = totalBalance;
            positionsLastAvailableBalanceUsdt_ = availableBalance;
        }

        QSet<QString> liveSymbols;
        for (const auto &pos : livePositions.positions) {
            const QString sym = pos.symbol.trimmed().toUpper();
            if (!sym.isEmpty()) {
                liveSymbols.insert(sym);
            }
        }

        auto setOrCreateCell = [table](int row, int col, const QString &text) {
            QTableWidgetItem *item = table->item(row, col);
            if (!item) {
                item = new QTableWidgetItem(text);
                table->setItem(row, col, item);
            } else {
                item->setText(text);
            }
            item->setData(Qt::UserRole, text);
        };

        int closedCount = 0;
        QSet<QString> staleSymbols;
        const QString nowText = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
        for (int row = 0; row < table->rowCount(); ++row) {
            const QString status = table->item(row, 16) ? table->item(row, 16)->text().trimmed().toUpper() : QString();
            if (status != QStringLiteral("OPEN")) {
                continue;
            }
            const QString symbol = table->item(row, 0) ? table->item(row, 0)->text().trimmed().toUpper() : QString();
            if (symbol.isEmpty() || liveSymbols.contains(symbol)) {
                continue;
            }
            staleSymbols.insert(symbol);
            setOrCreateCell(row, 16, QStringLiteral("CLOSED"));
            const QString existingClose = table->item(row, 14) ? table->item(row, 14)->text().trimmed() : QString();
            if (existingClose.isEmpty() || existingClose == QStringLiteral("-")) {
                setOrCreateCell(row, 14, nowText);
            }
            ++closedCount;
        }

        if (!staleSymbols.isEmpty()) {
            QList<QString> runtimeKeys = dashboardRuntimeOpenPositions_.keys();
            for (const QString &runtimeKey : runtimeKeys) {
                const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
                if (staleSymbols.contains(symbol)) {
                    dashboardRuntimeOpenPositions_.remove(runtimeKey);
                }
            }
        }

        updateStatusMessage(
            QString("Positions synced from Binance: %1 live symbol(s), %2 stale local row(s) closed.")
                .arg(liveSymbols.size())
                .arg(closedCount));
        applyPositionsViewMode();
    });
    connect(closeAllBtn, &QPushButton::clicked, this, [=]() {
        const int rowCount = table->rowCount();
        table->setRowCount(0);
        dashboardRuntimeOpenPositions_.clear();
        updateStatusMessage(QString("Market close-all simulated for %1 row(s).").arg(rowCount));
        applyPositionsViewMode();
    });
    connect(positionsViewCombo, &QComboBox::currentTextChanged, this, [=](const QString &viewText) {
        updateStatusMessage(QString("Positions view changed to %1.").arg(viewText));
        applyPositionsViewMode();
    });
    connect(autoRowHeightCheck, &QCheckBox::toggled, this, [=](bool enabled) {
        Q_UNUSED(enabled);
        refreshPositionsTableSizing();
    });
    connect(autoColumnWidthCheck, &QCheckBox::toggled, this, [=](bool enabled) {
        Q_UNUSED(enabled);
        refreshPositionsTableSizing();
    });
    connect(clearSelectedBtn, &QPushButton::clicked, this, [=]() {
        QSet<int> selectedRows;
        const auto selected = table->selectedItems();
        for (auto *item : selected) {
            if (item) {
                selectedRows.insert(item->row());
            }
        }
        QSet<QString> clearedPrefixes;
        for (int row : selectedRows) {
            const auto rawText = [table](int r, int c) -> QString {
                QTableWidgetItem *item = table->item(r, c);
                if (!item) {
                    return {};
                }
                const QVariant raw = item->data(Qt::UserRole);
                return raw.isValid() ? raw.toString() : item->text();
            };
            const QString symbol = rawText(row, 0).trimmed().toUpper();
            const QString interval = rawText(row, 8).trimmed().toLower();
            if (!symbol.isEmpty() && !interval.isEmpty()) {
                clearedPrefixes.insert(QStringLiteral("%1|%2|").arg(symbol, interval));
            }
        }
        if (!clearedPrefixes.isEmpty()) {
            const QList<QString> keys = dashboardRuntimeOpenPositions_.keys();
            for (const QString &runtimeKey : keys) {
                for (const QString &prefix : clearedPrefixes) {
                    if (runtimeKey.startsWith(prefix, Qt::CaseInsensitive)) {
                        dashboardRuntimeOpenPositions_.remove(runtimeKey);
                        break;
                    }
                }
            }
        }
        QList<int> rows = selectedRows.values();
        std::sort(rows.begin(), rows.end(), std::greater<int>());
        for (int rowIdx : rows) {
            table->removeRow(rowIdx);
        }
        updateStatusMessage(QString("Positions cleared: %1 selected row(s).").arg(rows.size()));
        applyPositionsViewMode();
    });
    connect(clearAllBtn, &QPushButton::clicked, this, [=]() {
        const int rowCount = table->rowCount();
        table->setRowCount(0);
        dashboardRuntimeOpenPositions_.clear();
        updateStatusMessage(QString("Positions cleared: %1 total row(s).").arg(rowCount));
        applyPositionsViewMode();
    });

    applyPositionsViewMode();

    return page;
}

QWidget *TradingBotWindow::createBacktestTab() {
    auto *page = new QWidget(this);
    page->setObjectName("backtestPage");
    backtestPnlActiveLabel_ = nullptr;
    backtestPnlClosedLabel_ = nullptr;
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
    topLayout->addWidget(createParametersGroup(), 5);
    topLayout->addWidget(createIndicatorsGroup(), 3);

    auto *outputGroup = new QGroupBox("Backtest Output", page);
    auto *outputLayout = new QVBoxLayout(outputGroup);
    outputLayout->setContentsMargins(12, 12, 12, 12);
    outputLayout->setSpacing(12);

    auto *controlsLayout = new QHBoxLayout();
    runButton_ = new QPushButton("Run Backtest", outputGroup);
    controlsLayout->addWidget(runButton_);
    stopButton_ = new QPushButton("Stop", outputGroup);
    stopButton_->setEnabled(false);
    controlsLayout->addWidget(stopButton_);

    statusLabel_ = new QLabel(outputGroup);
    statusLabel_->setMinimumWidth(180);
    controlsLayout->addWidget(statusLabel_);

    addSelectedBtn_ = new QPushButton("Add Selected to Dashboard", outputGroup);
    controlsLayout->addWidget(addSelectedBtn_);
    addAllBtn_ = new QPushButton("Add All to Dashboard", outputGroup);
    controlsLayout->addWidget(addAllBtn_);
    controlsLayout->addStretch();

    auto *tabStatusWidget = new QWidget(outputGroup);
    auto *tabStatusLayout = new QHBoxLayout(tabStatusWidget);
    tabStatusLayout->setContentsMargins(0, 0, 0, 0);
    tabStatusLayout->setSpacing(8);

    auto *pnlActiveLabel = new QLabel("Total PNL Active Positions: --", tabStatusWidget);
    auto *pnlClosedLabel = new QLabel("Total PNL Closed Positions: --", tabStatusWidget);
    backtestPnlActiveLabel_ = pnlActiveLabel;
    backtestPnlClosedLabel_ = pnlClosedLabel;
    pnlActiveLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    pnlClosedLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    tabStatusLayout->addWidget(pnlActiveLabel);
    tabStatusLayout->addWidget(pnlClosedLabel);
    tabStatusLayout->addStretch();

    botStatusLabel_ = new QLabel("Bot Status: OFF", tabStatusWidget);
    botTimeLabel_ = new QLabel("Bot Active Time: --", tabStatusWidget);
    botStatusLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    botTimeLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    tabStatusLayout->addWidget(botStatusLabel_);
    tabStatusLayout->addWidget(botTimeLabel_);
    controlsLayout->addWidget(tabStatusWidget);

    outputLayout->addLayout(controlsLayout);
    outputLayout->addWidget(createResultsGroup(), 1);

    contentLayout->addWidget(outputGroup, 1);

    return page;
}

bool TradingBotWindow::openExternalUrl(const QString &url) {
    const QString target = url.trimmed();
    if (target.isEmpty()) {
        return false;
    }
    return QDesktopServices::openUrl(QUrl::fromUserInput(target));
}

QWidget *TradingBotWindow::createLiquidationWebPanel(const QString &title, const QString &url, const QString &note) {
    auto *panel = new QWidget(this);
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(8);

    auto *headerLayout = new QHBoxLayout();
    auto *titleLabel = new QLabel(title, panel);
    titleLabel->setStyleSheet("font-size: 16px; font-weight: 600;");
    headerLayout->addWidget(titleLabel);
    headerLayout->addStretch();
    auto *openBtn = new QPushButton("Open in Browser", panel);
    headerLayout->addWidget(openBtn);
    auto *reloadBtn = new QPushButton("Reload", panel);
    headerLayout->addWidget(reloadBtn);
    layout->addLayout(headerLayout);

    if (!note.trimmed().isEmpty()) {
        auto *noteLabel = new QLabel(note, panel);
        noteLabel->setWordWrap(true);
        noteLabel->setStyleSheet("color: #94a3b8;");
        layout->addWidget(noteLabel);
    }

    auto *urlRow = new QHBoxLayout();
    urlRow->addWidget(new QLabel("URL:", panel));
    auto *urlEdit = new QLineEdit(panel);
    urlEdit->setPlaceholderText("https://");
    urlEdit->setText(url.trimmed());
    urlRow->addWidget(urlEdit, 1);
    auto *goBtn = new QPushButton("Go", panel);
    urlRow->addWidget(goBtn);
    layout->addLayout(urlRow);

    const auto normalizedUrlText = [urlEdit]() -> QString {
        const QString raw = urlEdit ? urlEdit->text().trimmed() : QString();
        if (raw.isEmpty()) {
            return QString();
        }
        const QUrl parsed = QUrl::fromUserInput(raw);
        return parsed.isValid() ? parsed.toString() : raw;
    };

    connect(openBtn, &QPushButton::clicked, this, [this, normalizedUrlText]() {
        const QString target = normalizedUrlText();
        if (!openExternalUrl(target)) {
            updateStatusMessage(QString("Could not open URL: %1").arg(target));
        }
    });

#if HAS_QT_WEBENGINE
    auto *webView = new QWebEngineView(panel);
    layout->addWidget(webView, 1);

    const auto applyUrl = [this, urlEdit, webView]() {
        const QString raw = urlEdit ? urlEdit->text().trimmed() : QString();
        if (raw.isEmpty()) {
            return;
        }
        const QUrl parsed = QUrl::fromUserInput(raw);
        if (!parsed.isValid()) {
            updateStatusMessage(QString("Invalid URL: %1").arg(raw));
            return;
        }
        if (urlEdit) {
            urlEdit->setText(parsed.toString());
        }
        webView->load(parsed);
    };

    connect(goBtn, &QPushButton::clicked, this, [applyUrl]() {
        applyUrl();
    });
    connect(urlEdit, &QLineEdit::returnPressed, this, [applyUrl]() {
        applyUrl();
    });
    connect(reloadBtn, &QPushButton::clicked, webView, &QWebEngineView::reload);

    QTimer::singleShot(0, this, [applyUrl]() {
        applyUrl();
    });
#else
    auto *fallback = new QLabel(
        "Qt WebEngine is not available in this C++ build.\n"
        "Use 'Open in Browser' to view the heatmap.",
        panel);
    fallback->setWordWrap(true);
    fallback->setStyleSheet("color: #f59e0b;");
    layout->addWidget(fallback, 1);

    connect(goBtn, &QPushButton::clicked, this, [this, normalizedUrlText]() {
        const QString target = normalizedUrlText();
        if (!openExternalUrl(target)) {
            updateStatusMessage(QString("Could not open URL: %1").arg(target));
        }
    });
    connect(urlEdit, &QLineEdit::returnPressed, this, [this, normalizedUrlText]() {
        const QString target = normalizedUrlText();
        if (!openExternalUrl(target)) {
            updateStatusMessage(QString("Could not open URL: %1").arg(target));
        }
    });
    connect(reloadBtn, &QPushButton::clicked, this, [this]() {
        updateStatusMessage("Reload is unavailable: Qt WebEngine is not enabled in this build.");
    });
#endif

    return panel;
}

QWidget *TradingBotWindow::createLiquidationHeatmapTab() {
    auto *tab = new QWidget(this);
    tab->setObjectName("liquidationPage");

    auto *outerLayout = new QVBoxLayout(tab);
    outerLayout->setContentsMargins(10, 10, 10, 10);
    outerLayout->setSpacing(12);

    auto *intro = new QLabel(
        "Liquidation heatmaps from multiple providers. "
        "If a heatmap does not load, use 'Open in Browser'.",
        tab);
    intro->setWordWrap(true);
    outerLayout->addWidget(intro);

    auto *tabs = new QTabWidget(tab);
    outerLayout->addWidget(tabs, 1);

    auto *coinglassTab = new QWidget(tab);
    auto *coinglassLayout = new QVBoxLayout(coinglassTab);
    coinglassLayout->setContentsMargins(0, 0, 0, 0);
    auto *coinglassNote = new QLabel(
        "Use the on-page controls for Model 1/2/3, pair, symbol, and time selection.",
        coinglassTab);
    coinglassNote->setWordWrap(true);
    coinglassLayout->addWidget(coinglassNote);

    auto *coinglassModels = new QTabWidget(coinglassTab);
    coinglassLayout->addWidget(coinglassModels, 1);
    const QVector<QPair<int, QString>> coinglassModelUrls = {
        {1, QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationHeatMap")},
        {2, QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationHeatMapNew")},
        {3, QStringLiteral("https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3")},
    };
    for (const auto &entry : coinglassModelUrls) {
        const int model = entry.first;
        const QString modelUrl = entry.second;
        coinglassModels->addTab(
            createLiquidationWebPanel(
                QString("Coinglass Heatmap Model %1").arg(model),
                modelUrl),
            QString("Model %1").arg(model));
    }
    tabs->addTab(coinglassTab, "Coinglass Heatmap");

    tabs->addTab(
        createLiquidationWebPanel(
            "Coinank Liquidation Heatmap",
            "https://coinank.com/chart/derivatives/liq-heat-map"),
        "Coinank");

    tabs->addTab(
        createLiquidationWebPanel(
            "Bitcoin Counterflow Liquidation Heatmap",
            "https://www.bitcoincounterflow.com/liquidation-heatmap/"),
        "Bitcoin Counterflow");

    tabs->addTab(
        createLiquidationWebPanel(
            "Hyblock Capital Liquidation Heatmap",
            "https://hyblockcapital.com/"),
        "Hyblock Capital");

    tabs->addTab(
        createLiquidationWebPanel(
            "Coinglass Liquidation Map",
            "https://www.coinglass.com/pro/futures/LiquidationMap"),
        "Coinglass Map");

    tabs->addTab(
        createLiquidationWebPanel(
            "Hyperliquid Liquidation Map",
            "https://www.coinglass.com/hyperliquid-liquidation-map"),
        "Hyperliquid Map");

    return tab;
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

QWidget *TradingBotWindow::createMarketsGroup() {
    auto *group = new QGroupBox("Markets & Intervals", this);
    auto *layout = new QGridLayout(group);
    layout->setHorizontalSpacing(10);
    layout->setVerticalSpacing(8);

    auto *symbolLabel = new QLabel("Symbol Source:", group);
    symbolSourceCombo_ = new QComboBox(group);
    symbolSourceCombo_->addItems({"Futures", "Spot"});
    auto *refreshBtn = new QPushButton("Refresh Symbols", group);
    backtestRefreshSymbolsBtn_ = refreshBtn;
    layout->addWidget(symbolLabel, 0, 0);
    layout->addWidget(symbolSourceCombo_, 0, 1);
    layout->addWidget(refreshBtn, 0, 2);

    auto *symbolsInfo = new QLabel("Symbols (select 1 or more):", group);
    layout->addWidget(symbolsInfo, 1, 0, 1, 3);
    symbolList_ = new QListWidget(group);
    symbolList_->setSelectionMode(QAbstractItemView::MultiSelection);
    symbolList_->setMinimumHeight(260);
    layout->addWidget(symbolList_, 2, 0, 4, 3);

    auto *intervalInfo = new QLabel("Intervals (select 1 or more):", group);
    layout->addWidget(intervalInfo, 1, 3);
    intervalList_ = new QListWidget(group);
    intervalList_->setSelectionMode(QAbstractItemView::MultiSelection);
    intervalList_->setMinimumHeight(260);
    layout->addWidget(intervalList_, 2, 3, 4, 2);

    customIntervalEdit_ = new QLineEdit(group);
    customIntervalEdit_->setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated");
    layout->addWidget(customIntervalEdit_, 6, 0, 1, 4);
    auto *addBtn = new QPushButton("Add Custom Interval(s)", group);
    layout->addWidget(addBtn, 6, 4, 1, 1);
    connect(addBtn, &QPushButton::clicked, this, &TradingBotWindow::handleAddCustomIntervals);
    connect(refreshBtn, &QPushButton::clicked, this, &TradingBotWindow::refreshBacktestSymbols);
    if (symbolSourceCombo_) {
        connect(symbolSourceCombo_, &QComboBox::currentTextChanged, this, [this](const QString &) {
            if (backtestConnectorCombo_) {
                const bool futures = symbolSourceCombo_
                    ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
                    : true;
                rebuildDashboardConnectorComboForAccount(backtestConnectorCombo_, futures, true);
            }
            refreshBacktestSymbols();
        });
    }

    auto *pairGroup = new QGroupBox("Symbol / Interval Overrides", group);
    auto *pairLayout = new QVBoxLayout(pairGroup);
    pairLayout->setContentsMargins(8, 8, 8, 8);
    pairLayout->setSpacing(8);

    backtestSymbolIntervalTable_ = new QTableWidget(0, 8, pairGroup);
    backtestSymbolIntervalTable_->setHorizontalHeaderLabels({
        "Symbol",
        "Interval",
        "Indicators",
        "Loop",
        "Leverage",
        "Connector",
        "Strategy Controls",
        "Stop-Loss",
    });
    QHeaderView *overrideHeader = backtestSymbolIntervalTable_->horizontalHeader();
    overrideHeader->setStretchLastSection(false);
    overrideHeader->setSectionResizeMode(QHeaderView::ResizeToContents);
    overrideHeader->setSectionsMovable(true);
    backtestSymbolIntervalTable_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    backtestSymbolIntervalTable_->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    backtestSymbolIntervalTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    backtestSymbolIntervalTable_->setSelectionMode(QAbstractItemView::MultiSelection);
    backtestSymbolIntervalTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    backtestSymbolIntervalTable_->setSortingEnabled(true);
    backtestSymbolIntervalTable_->setMinimumHeight(180);
    backtestSymbolIntervalTable_->verticalHeader()->setDefaultSectionSize(28);
    pairLayout->addWidget(backtestSymbolIntervalTable_);

    auto *pairButtons = new QHBoxLayout();
    auto *addPairBtn = new QPushButton("Add Selected", pairGroup);
    auto *removePairBtn = new QPushButton("Remove Selected", pairGroup);
    auto *clearPairBtn = new QPushButton("Clear All", pairGroup);
    pairButtons->addWidget(addPairBtn);
    pairButtons->addWidget(removePairBtn);
    pairButtons->addWidget(clearPairBtn);
    pairButtons->addStretch();
    pairLayout->addLayout(pairButtons);
    connect(addPairBtn, &QPushButton::clicked, this, &TradingBotWindow::addSelectedBacktestSymbolIntervalPairs);
    connect(removePairBtn, &QPushButton::clicked, this, &TradingBotWindow::removeSelectedBacktestSymbolIntervalPairs);
    connect(clearPairBtn, &QPushButton::clicked, this, &TradingBotWindow::clearBacktestSymbolIntervalPairs);
    layout->addWidget(pairGroup, 7, 0, 1, 5);

    return group;
}

QWidget *TradingBotWindow::createParametersGroup() {
    auto *group = new QGroupBox("Backtest Parameters", this);
    auto *form = new QFormLayout(group);
    form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    form->setLabelAlignment(Qt::AlignLeft | Qt::AlignVCenter);

    auto addCombo = [form](const QString &label, const QStringList &items) {
        auto *combo = new QComboBox(form->parentWidget());
        combo->addItems(items);
        form->addRow(label, combo);
        return combo;
    };

    addCombo("Signal Logic:", {"AND", "OR", "SEPARATE"});
    addCombo("MDD Logic:", {"Per Trade MDD", "Cumulative MDD", "Entire Account MDD"});

    auto *startDate = new QDateEdit(QDate::currentDate().addMonths(-1), group);
    startDate->setCalendarPopup(true);
    startDate->setDisplayFormat("yyyy-MM-dd");
    form->addRow("Start Date:", startDate);
    auto *endDate = new QDateEdit(QDate::currentDate(), group);
    endDate->setCalendarPopup(true);
    endDate->setDisplayFormat("yyyy-MM-dd");
    form->addRow("End Date:", endDate);

    auto *capitalSpin = new QDoubleSpinBox(group);
    capitalSpin->setSuffix(" USDT");
    capitalSpin->setRange(0.0, 1'000'000.0);
    capitalSpin->setDecimals(2);
    capitalSpin->setValue(1000.0);
    form->addRow("Capital (USDT):", capitalSpin);

    auto *positionPct = new QDoubleSpinBox(group);
    positionPct->setSuffix(" %");
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setDecimals(2);
    positionPct->setValue(2.0);
    form->addRow("Position % of Balance:", positionPct);

    auto *loopCombo = new QComboBox(group);
    loopCombo->addItem("30 seconds", "30s");
    loopCombo->addItem("45 seconds", "45s");
    loopCombo->addItem("1 minute", "1m");
    loopCombo->addItem("2 minutes", "2m");
    loopCombo->addItem("3 minutes", "3m");
    loopCombo->addItem("5 minutes", "5m");
    loopCombo->addItem("10 minutes", "10m");
    loopCombo->addItem("30 minutes", "30m");
    loopCombo->addItem("1 hour", "1h");
    loopCombo->addItem("2 hours", "2h");
    loopCombo->setCurrentIndex(loopCombo->findData("1m"));
    backtestLoopCombo_ = loopCombo;
    form->addRow("Loop Interval Override:", loopCombo);

    auto *stopLossRow = new QWidget(group);
    auto *stopLossLayout = new QHBoxLayout(stopLossRow);
    stopLossLayout->setContentsMargins(0, 0, 0, 0);
    stopLossLayout->setSpacing(6);
    auto *stopEnable = new QCheckBox("Enable", stopLossRow);
    auto *stopMode = new QComboBox(stopLossRow);
    stopMode->addItem("USDT Based Stop Loss", "usdt");
    stopMode->addItem("Percentage Based Stop Loss", "percent");
    stopMode->addItem("Both Stop Loss (USDT & Percentage)", "both");
    auto *stopScope = new QComboBox(stopLossRow);
    stopScope->addItem("Per Trade Stop Loss", "per_trade");
    stopScope->addItem("Cumulative Stop Loss", "cumulative");
    stopScope->addItem("Entire Account Stop Loss", "entire_account");
    auto *stopUsdt = new QDoubleSpinBox(stopLossRow);
    stopUsdt->setPrefix("USDT ");
    stopUsdt->setRange(0.0, 1'000'000.0);
    stopUsdt->setDecimals(2);
    stopUsdt->setSingleStep(1.0);
    stopUsdt->setValue(25.0);
    auto *stopPct = new QDoubleSpinBox(stopLossRow);
    stopPct->setSuffix(" %");
    stopPct->setRange(0.0, 100.0);
    stopPct->setDecimals(2);
    stopPct->setSingleStep(0.1);
    stopPct->setValue(2.0);

    stopLossLayout->addWidget(stopEnable);
    stopLossLayout->addWidget(stopMode, 1);
    stopLossLayout->addWidget(stopScope, 1);
    stopLossLayout->addWidget(stopUsdt);
    stopLossLayout->addWidget(stopPct);
    form->addRow("Stop Loss:", stopLossRow);
    backtestStopLossEnableCheck_ = stopEnable;
    backtestStopLossModeCombo_ = stopMode;
    backtestStopLossScopeCombo_ = stopScope;

    const auto updateStopLossWidgets = [stopEnable, stopMode, stopScope, stopUsdt, stopPct]() {
        const bool enabled = stopEnable->isChecked();
        stopMode->setEnabled(enabled);
        stopScope->setEnabled(enabled);
        stopUsdt->setEnabled(enabled);
        stopPct->setEnabled(enabled);
        const QString mode = stopMode->currentData().toString();
        stopUsdt->setVisible(enabled && (mode == "usdt" || mode == "both"));
        stopPct->setVisible(enabled && (mode == "percent" || mode == "both"));
    };
    connect(stopEnable, &QCheckBox::toggled, this, [updateStopLossWidgets](bool) {
        updateStopLossWidgets();
    });
    connect(stopMode, &QComboBox::currentIndexChanged, this, [updateStopLossWidgets](int) {
        updateStopLossWidgets();
    });
    updateStopLossWidgets();

    auto *sideCombo = addCombo("Side:", {"Buy (Long)", "Sell (Short)", "Both (Long/Short)"});
    sideCombo->setCurrentText("Both (Long/Short)");
    backtestSideCombo_ = sideCombo;

    addCombo("Margin Mode (Futures):", {"Isolated", "Cross"});
    addCombo("Position Mode:", {"Hedge", "One-way"});
    auto *assetsCombo = new QComboBox(group);
    assetsCombo->addItem("Single-Asset Mode", "Single-Asset");
    assetsCombo->addItem("Multi-Assets Mode", "Multi-Assets");
    form->addRow("Assets Mode:", assetsCombo);
    addCombo("Account Mode:", {"Classic Trading", "Multi-Asset Mode"});

    auto *connectorCombo = new QComboBox(group);
    const bool sourceFutures = symbolSourceCombo_
        ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    rebuildDashboardConnectorComboForAccount(connectorCombo, sourceFutures, true);
    connectorCombo->setMinimumWidth(220);
    form->addRow("Connector:", connectorCombo);
    backtestConnectorCombo_ = connectorCombo;
    connect(connectorCombo, &QComboBox::currentTextChanged, this, [this](const QString &) {
        refreshBacktestSymbols();
    });

    auto *leverageSpin = new QSpinBox(group);
    leverageSpin->setRange(1, 150);
    leverageSpin->setValue(5);
    backtestLeverageSpin_ = leverageSpin;
    form->addRow("Leverage (Futures):", leverageSpin);

    auto *templateEnable = new QCheckBox("Enable", group);
    templateEnable->setChecked(false);
    auto *templateCombo = new QComboBox(group);
    templateCombo->addItems({
        "First 50 Highest Volume",
        "Last 1 week · 2% per trade · 50 highest volume",
        "Top 100, %2 per trade, isolated, %20 (%1 Actual Move) per trade SL",
    });
    templateCombo->setEnabled(false);

    connect(templateEnable, &QCheckBox::toggled, templateCombo, &QWidget::setEnabled);
    form->addRow("Template:", templateCombo);
    form->addRow("", templateEnable);

    auto *scanRow = new QWidget(group);
    auto *scanLayout = new QHBoxLayout(scanRow);
    scanLayout->setContentsMargins(0, 0, 0, 0);
    scanLayout->setSpacing(6);
    auto *scanMddSpin = new QDoubleSpinBox(scanRow);
    scanMddSpin->setRange(0.0, 100.0);
    scanMddSpin->setDecimals(2);
    scanMddSpin->setSuffix(" %");
    scanMddSpin->setValue(0.0);
    auto *scanBtn = new QPushButton("Scan Symbols", scanRow);
    scanLayout->addWidget(scanMddSpin);
    scanLayout->addWidget(scanBtn);
    scanLayout->addStretch();
    connect(scanBtn, &QPushButton::clicked, this, [this, scanMddSpin]() {
        updateStatusMessage(QString("Backtest symbol scan simulated (Max MDD: %1%).").arg(scanMddSpin->value(), 0, 'f', 2));
    });
    form->addRow("Max MDD Scanner:", scanRow);

    return group;
}

QWidget *TradingBotWindow::createIndicatorsGroup() {
    auto *group = new QGroupBox("Indicators", this);
    group->setMinimumWidth(220);
    group->setMaximumWidth(340);
    group->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
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
        auto *btn = new QPushButton("Buy-Sell Values", group);
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

QWidget *TradingBotWindow::createResultsGroup() {
    auto *group = new QGroupBox("Backtest Results", this);
    auto *layout = new QVBoxLayout(group);
    resultsTable_ = new QTableWidget(0, 21, group);
    resultsTable_->setHorizontalHeaderLabels({
        "Symbol",
        "Interval",
        "Logic",
        "Indicators",
        "Trades",
        "Loop Interval",
        "Start Date",
        "End Date",
        "Position % Of Balance",
        "Stop-Loss Options",
        "Margin Mode (Futures)",
        "Position Mode",
        "Assets Mode",
        "Account Mode",
        "Leverage (Futures)",
        "ROI (USDT)",
        "ROI (%)",
        "Max Drawdown During Position (USDT)",
        "Max Drawdown During Position (%)",
        "Max Drawdown Results (USDT)",
        "Max Drawdown Results (%)",
    });
    QHeaderView *header = resultsTable_->horizontalHeader();
    header->setStretchLastSection(false);
    header->setSectionsMovable(true);
    header->setSectionResizeMode(QHeaderView::Interactive);
    QFontMetrics fm(header->font());
    for (int col = 0; col < resultsTable_->columnCount(); ++col) {
        const auto *item = resultsTable_->horizontalHeaderItem(col);
        const QString text = item ? item->text() : QString();
        header->resizeSection(col, std::max(80, fm.horizontalAdvance(text) + 28));
    }
    resultsTable_->setSortingEnabled(true);
    resultsTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    resultsTable_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    resultsTable_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    resultsTable_->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    resultsTable_->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    resultsTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    resultsTable_->setSelectionMode(QAbstractItemView::MultiSelection);
    resultsTable_->setMinimumHeight(420);
    layout->addWidget(resultsTable_);
    return group;
}

void TradingBotWindow::populateDefaults() {
    if (symbolList_) {
        symbolList_->addItems({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"});
        for (int i = 0; i < symbolList_->count(); ++i) {
            if (i < 2) {
                symbolList_->item(i)->setSelected(true);
            }
        }
    }
    if (intervalList_) {
        intervalList_->addItems({
            "1m", "3m", "5m", "10m", "15m", "20m", "30m",
            "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h",
        });
        for (int i = 0; i < intervalList_->count() && i < 2; ++i) {
            intervalList_->item(i)->setSelected(true);
        }
    }
}

void TradingBotWindow::wireSignals() {
    connect(runButton_, &QPushButton::clicked, this, &TradingBotWindow::handleRunBacktest);
    connect(stopButton_, &QPushButton::clicked, this, &TradingBotWindow::handleStopBacktest);
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

void TradingBotWindow::handleAddCustomIntervals() {
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

void TradingBotWindow::handleRunBacktest() {
    botStart_ = std::chrono::steady_clock::now();
    ensureBotTimer(true);
    const QString statusText = QStringLiteral("Bot Status: ON");
    const QString statusStyle = QStringLiteral("color: #16a34a; font-weight: 700;");
    const QString activeTimeText = QStringLiteral("Bot Active Time: 0s");
    if (botStatusLabel_) {
        botStatusLabel_->setText(statusText);
        botStatusLabel_->setStyleSheet(statusStyle);
    }
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText(statusText);
        chartBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (positionsBotStatusLabel_) {
        positionsBotStatusLabel_->setText(statusText);
        positionsBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (codeBotStatusLabel_) {
        codeBotStatusLabel_->setText(statusText);
        codeBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (botTimeLabel_) {
        botTimeLabel_->setText(activeTimeText);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(activeTimeText);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(activeTimeText);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(activeTimeText);
    }
    runButton_->setEnabled(false);
    stopButton_->setEnabled(true);
    updateStatusMessage("Running backtest...");
    refreshPositionsSummaryLabels();

    const int currentRow = resultsTable_->rowCount();
    resultsTable_->insertRow(currentRow);
    const QStringList values = {
        "BTCUSDT",
        "1h",
        "AND",
        "RSI, Stochastic RSI, MACD",
        "42",
        "1 minute",
        "2024-01-01",
        "2024-02-01",
        "2.00%",
        "Enabled (USDT 25.00 | Per Trade)",
        "Isolated",
        "Hedge",
        "Single-Asset",
        "Classic Trading",
        "20x",
        "+152.40",
        "+15.24%",
        "-38.12",
        "-3.81%",
        "-74.85",
        "-7.49%",
    };
    for (int col = 0; col < values.size() && col < resultsTable_->columnCount(); ++col) {
        resultsTable_->setItem(currentRow, col, new QTableWidgetItem(values.at(col)));
    }
}

void TradingBotWindow::handleStopBacktest() {
    ensureBotTimer(false);
    const QString statusText = QStringLiteral("Bot Status: OFF");
    const QString statusStyle = QStringLiteral("color: #ef4444; font-weight: 700;");
    const QString activeTimeText = QStringLiteral("Bot Active Time: --");
    if (botTimeLabel_) {
        botTimeLabel_->setText(activeTimeText);
    }
    if (botStatusLabel_) {
        botStatusLabel_->setText(statusText);
        botStatusLabel_->setStyleSheet(statusStyle);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(activeTimeText);
    }
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText(statusText);
        chartBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(activeTimeText);
    }
    if (positionsBotStatusLabel_) {
        positionsBotStatusLabel_->setText(statusText);
        positionsBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(activeTimeText);
    }
    if (codeBotStatusLabel_) {
        codeBotStatusLabel_->setText(statusText);
        codeBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (!dashboardRuntimeActive_ && dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("--");
    }
    if (!dashboardRuntimeActive_ && dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("OFF");
        dashboardBotStatusLabel_->setStyleSheet(statusStyle);
    }
    runButton_->setEnabled(true);
    stopButton_->setEnabled(false);
    updateStatusMessage("Backtest stopped.");
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::updateBotActiveTime() {
    if (!botTimer_) {
        return;
    }
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - botStart_);
    const QString text = "Bot Active Time: " + formatDuration(elapsed.count());
    if (botTimeLabel_) {
        botTimeLabel_->setText(text);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(text);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(text);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(text);
    }
    if (dashboardRuntimeActive_ && dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText(formatDuration(elapsed.count()));
    }
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::ensureBotTimer(bool running) {
    if (!botTimer_) {
        botTimer_ = new QTimer(this);
        botTimer_->setInterval(1000);
        connect(botTimer_, &QTimer::timeout, this, &TradingBotWindow::updateBotActiveTime);
    }
    if (running) {
        botTimer_->start();
    } else {
        botTimer_->stop();
    }
}

void TradingBotWindow::refreshPositionsTableSizing(bool resizeColumns, bool resizeRows) {
    if (!positionsTable_) {
        return;
    }

    const bool autoRows = positionsAutoRowHeightCheck_ && positionsAutoRowHeightCheck_->isChecked();
    const bool autoColumns = positionsAutoColumnWidthCheck_ && positionsAutoColumnWidthCheck_->isChecked();

    if (autoRows) {
        if (resizeRows) {
            positionsTable_->verticalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
            positionsTable_->resizeRowsToContents();
        }
        positionsTable_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    } else {
        positionsTable_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
        positionsTable_->verticalHeader()->setDefaultSectionSize(44);
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            positionsTable_->setRowHeight(row, 44);
        }
    }

    QHeaderView *header = positionsTable_->horizontalHeader();
    if (autoColumns) {
        header->setStretchLastSection(false);
        if (resizeColumns) {
            for (int i = 0; i < header->count(); ++i) {
                header->setSectionResizeMode(i, QHeaderView::ResizeToContents);
            }
            positionsTable_->resizeColumnsToContents();
        }
        for (int i = 0; i < header->count(); ++i) {
            header->setSectionResizeMode(i, QHeaderView::Interactive);
        }
        header->setStretchLastSection(true);
    } else {
        header->setStretchLastSection(true);
        for (int i = 0; i < header->count(); ++i) {
            header->setSectionResizeMode(i, QHeaderView::Interactive);
        }
    }
}

void TradingBotWindow::refreshPositionsSummaryLabels() {
    double activePnl = 0.0;
    double closedPnl = 0.0;
    if (positionsTable_) {
        const auto rawCellText = [](const QTableWidgetItem *item) -> QString {
            if (!item) {
                return {};
            }
            const QVariant raw = item->data(Qt::UserRole);
            return raw.isValid() ? raw.toString() : item->text();
        };
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            const QString pnlText = rawCellText(positionsTable_->item(row, 7));
            const QString status = rawCellText(positionsTable_->item(row, 16)).trimmed().toUpper();
            const QString quantityText = rawCellText(positionsTable_->item(row, 6));
            bool ok = false;
            const double pnlValue = firstNumberInText(pnlText, &ok);
            if (!ok || !qIsFinite(pnlValue)) {
                continue;
            }
            bool qtyOk = false;
            double quantityValue = tableCellRawNumeric(positionsTable_->item(row, 6), std::numeric_limits<double>::quiet_NaN());
            if (!qIsFinite(quantityValue)) {
                quantityValue = firstNumberInText(quantityText, &qtyOk);
            } else {
                qtyOk = true;
            }
            if (status == QStringLiteral("OPEN")) {
                if (!qtyOk || !qIsFinite(quantityValue) || std::fabs(quantityValue) <= 1e-10) {
                    continue;
                }
                activePnl += pnlValue;
            } else if (status == QStringLiteral("CLOSED")) {
                closedPnl += pnlValue;
            }
        }
    }

    const QString activePnlText = QStringLiteral("Total PNL Active Positions: %1 USDT")
                                      .arg(QString::number(activePnl, 'f', 2));
    const QString closedPnlText = QStringLiteral("Total PNL Closed Positions: %1 USDT")
                                      .arg(QString::number(closedPnl, 'f', 2));
    const QString activePnlValueText = QStringLiteral("%1 USDT")
                                           .arg(QString::number(activePnl, 'f', 2));
    const QString closedPnlValueText = QStringLiteral("%1 USDT")
                                           .arg(QString::number(closedPnl, 'f', 2));
    if (chartPnlActiveLabel_) {
        chartPnlActiveLabel_->setText(activePnlText);
    }
    if (chartPnlClosedLabel_) {
        chartPnlClosedLabel_->setText(closedPnlText);
    }
    if (positionsPnlActiveLabel_) {
        positionsPnlActiveLabel_->setText(activePnlText);
    }
    if (positionsPnlClosedLabel_) {
        positionsPnlClosedLabel_->setText(closedPnlText);
    }
    if (backtestPnlActiveLabel_) {
        backtestPnlActiveLabel_->setText(activePnlText);
    }
    if (backtestPnlClosedLabel_) {
        backtestPnlClosedLabel_->setText(closedPnlText);
    }
    if (dashboardPnlActiveLabel_) {
        dashboardPnlActiveLabel_->setText(activePnlValueText);
    }
    if (dashboardPnlClosedLabel_) {
        dashboardPnlClosedLabel_->setText(closedPnlValueText);
    }
    if (codePnlActiveLabel_) {
        codePnlActiveLabel_->setText(activePnlText);
    }
    if (codePnlClosedLabel_) {
        codePnlClosedLabel_->setText(closedPnlText);
    }

    if (positionsTotalBalanceLabel_) {
        if (qIsFinite(positionsLastTotalBalanceUsdt_) && positionsLastTotalBalanceUsdt_ >= 0.0) {
            positionsTotalBalanceLabel_->setText(
                QStringLiteral("Total Balance: %1 USDT")
                    .arg(QString::number(positionsLastTotalBalanceUsdt_, 'f', 3)));
        } else {
            positionsTotalBalanceLabel_->setText(QStringLiteral("Total Balance: --"));
        }
    }
    if (positionsAvailableBalanceLabel_) {
        if (qIsFinite(positionsLastAvailableBalanceUsdt_) && positionsLastAvailableBalanceUsdt_ >= 0.0) {
            positionsAvailableBalanceLabel_->setText(
                QStringLiteral("Available Balance: %1 USDT")
                    .arg(QString::number(positionsLastAvailableBalanceUsdt_, 'f', 3)));
        } else {
            positionsAvailableBalanceLabel_->setText(QStringLiteral("Available Balance: --"));
        }
    }

    QString statusText = botStatusLabel_ ? botStatusLabel_->text().trimmed() : QStringLiteral("Bot Status: OFF");
    if (!statusText.startsWith(QStringLiteral("Bot Status:"), Qt::CaseInsensitive)) {
        statusText = QStringLiteral("Bot Status: %1").arg(statusText);
    }
    QString statusValue = statusText.section(':', 1).trimmed();
    if (statusValue.isEmpty()) {
        statusValue = QStringLiteral("OFF");
    }
    const bool isOn = statusValue.contains(QStringLiteral("ON"), Qt::CaseInsensitive);
    const QString statusStyle = isOn
        ? QStringLiteral("color: #16a34a; font-weight: 700;")
        : QStringLiteral("color: #ef4444; font-weight: 700;");
    if (botStatusLabel_) {
        botStatusLabel_->setText(statusText);
        botStatusLabel_->setStyleSheet(statusStyle);
    }
    if (chartBotStatusLabel_) {
        chartBotStatusLabel_->setText(statusText);
        chartBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (positionsBotStatusLabel_) {
        positionsBotStatusLabel_->setText(statusText);
        positionsBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText(statusValue);
        dashboardBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (codeBotStatusLabel_) {
        codeBotStatusLabel_->setText(statusText);
        codeBotStatusLabel_->setStyleSheet(statusStyle);
    }

    QString activeTimeText = botTimeLabel_ ? botTimeLabel_->text().trimmed() : QStringLiteral("Bot Active Time: --");
    if (!activeTimeText.startsWith(QStringLiteral("Bot Active Time:"), Qt::CaseInsensitive)) {
        activeTimeText = QStringLiteral("Bot Active Time: %1").arg(activeTimeText);
    }
    const QString activeTimeValue = activeTimeText.section(':', 1).trimmed().isEmpty()
        ? QStringLiteral("--")
        : activeTimeText.section(':', 1).trimmed();
    if (botTimeLabel_) {
        botTimeLabel_->setText(activeTimeText);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(activeTimeText);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(activeTimeText);
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText(activeTimeValue);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(activeTimeText);
    }
}

void TradingBotWindow::applyPositionsViewMode(bool resizeColumns, bool resizeRows) {
    if (!positionsTable_) {
        return;
    }
    ScopedTableUpdatesPause updatesPause(positionsTable_);

    const bool cumulativeMode = !positionsViewCombo_
        || positionsViewCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("cumulative"));
    const bool viewModeChanged = positionsCumulativeView_ != cumulativeMode;
    positionsCumulativeView_ = cumulativeMode;

    const bool sortingWasEnabled = positionsTable_->isSortingEnabled();
    positionsTable_->setSortingEnabled(false);

    auto ensureItem = [this](int row, int col) -> QTableWidgetItem * {
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            item = new QTableWidgetItem();
            positionsTable_->setItem(row, col, item);
        }
        return item;
    };
    auto restoreRawText = [](QTableWidgetItem *item) {
        if (!item) {
            return;
        }
        const QVariant raw = item->data(Qt::UserRole);
        if (!raw.isValid()) {
            item->setData(Qt::UserRole, item->text());
            return;
        }
        item->setText(raw.toString());
        const QVariant rawNumeric = item->data(kTableCellRawNumericRole);
        item->setData(kTableCellNumericRole, rawNumeric);
        const QVariant rawRoiBasis = item->data(kTableCellRawRoiBasisRole);
        if (rawRoiBasis.isValid()) {
            item->setData(Qt::UserRole + 1, rawRoiBasis);
        }
    };
    auto rawText = [](QTableWidgetItem *item) -> QString {
        if (!item) {
            return {};
        }
        const QVariant raw = item->data(Qt::UserRole);
        if (raw.isValid()) {
            return raw.toString();
        }
        return item->text();
    };
    auto parseNumeric = [](const QString &text) -> double {
        bool ok = false;
        const double value = firstNumberInText(text, &ok);
        return (ok && qIsFinite(value)) ? value : 0.0;
    };
    auto numericValue = [&rawText, &parseNumeric](QTableWidgetItem *item) -> double {
        if (!item) {
            return 0.0;
        }
        const double storedValue = tableCellRawNumeric(item, std::numeric_limits<double>::quiet_NaN());
        if (qIsFinite(storedValue)) {
            return storedValue;
        }
        return parseNumeric(rawText(item));
    };
    auto rowSequenceFor = [this, &ensureItem](int row) -> qint64 {
        QTableWidgetItem *item = ensureItem(row, 0);
        bool ok = false;
        const qint64 existing = item->data(kPositionsRowSequenceRole).toLongLong(&ok);
        if (ok && existing > 0) {
            return existing;
        }
        const qint64 fallback = static_cast<qint64>(row) + 1;
        item->setData(kPositionsRowSequenceRole, fallback);
        positionsRowSequenceCounter_ = std::max(positionsRowSequenceCounter_, fallback + 1);
        return fallback;
    };
    auto setDisplayText = [&ensureItem](int row, int col, const QString &text) -> QTableWidgetItem * {
        QTableWidgetItem *item = ensureItem(row, col);
        if (!item->data(Qt::UserRole).isValid()) {
            item->setData(Qt::UserRole, item->text());
        }
        item->setText(text);
        return item;
    };

    if (viewModeChanged || !cumulativeMode) {
        for (int row = 0; row < positionsTable_->rowCount(); ++row) {
            positionsTable_->setRowHidden(row, false);
            for (int col = 0; col < positionsTable_->columnCount(); ++col) {
                restoreRawText(positionsTable_->item(row, col));
            }
        }
    }

    if (!cumulativeMode) {
        positionsTable_->setSortingEnabled(sortingWasEnabled);
        refreshPositionsTableSizing(resizeColumns, resizeRows);
        refreshPositionsSummaryLabels();
        return;
    }

    struct AggregateBucket {
        int primaryRow = -1;
        qint64 primarySequence = std::numeric_limits<qint64>::max();
        QList<int> rows;
        QStringList intervals;
        QStringList indicators;
        QStringList sides;
        QStringList stopLosses;
        QStringList statuses;
        QStringList triggeredValues;
        QStringList currentValues;
        QSet<QString> intervalSet;
        QSet<QString> indicatorSet;
        QSet<QString> sideSet;
        QSet<QString> stopLossSet;
        QSet<QString> statusSet;
        QSet<QString> triggeredSet;
        QSet<QString> currentSet;
        double sizeUsdt = 0.0;
        double lastPrice = 0.0;
        double marginUsdt = 0.0;
        double roiBasisUsdt = 0.0;
        double quantity = 0.0;
        double pnlUsdt = 0.0;
        double marginRatio = 0.0;
        double liqPrice = 0.0;
        int openCount = 0;
        int closedCount = 0;
        QString openTime;
        QString closeTime;
        QStringList connectors;
        QSet<QString> connectorSet;
    };

    QMap<QString, AggregateBucket> groups;
    const auto appendUnique = [](QStringList &ordered, QSet<QString> &seen, const QString &rawValue) {
        const QString value = rawValue.trimmed();
        if (value.isEmpty() || value == QStringLiteral("-")) {
            return;
        }
        const QString key = value.toLower();
        if (seen.contains(key)) {
            return;
        }
        seen.insert(key);
        ordered.append(value);
    };
    const auto appendUniqueLines = [&appendUnique](QStringList &ordered, QSet<QString> &seen, const QString &multiLine) {
        const QStringList parts = multiLine.split('\n', Qt::SkipEmptyParts);
        if (parts.isEmpty()) {
            appendUnique(ordered, seen, multiLine);
            return;
        }
        for (const QString &part : parts) {
            appendUnique(ordered, seen, part);
        }
    };
    const auto connectorBase = [](const QString &rawConnector) -> QString {
        QString text = rawConnector.trimmed();
        const int hashPos = text.indexOf('#');
        if (hashPos > 0) {
            text = text.left(hashPos).trimmed();
        }
        const int pipePos = text.indexOf('|');
        if (pipePos > 0) {
            text = text.left(pipePos).trimmed();
        }
        return text;
    };

    for (int row = 0; row < positionsTable_->rowCount(); ++row) {
        const QString symbol = rawText(positionsTable_->item(row, 0)).trimmed().toUpper();
        const QString side = rawText(positionsTable_->item(row, 12)).trimmed().toUpper();
        const QString status = rawText(positionsTable_->item(row, 16)).trimmed().toUpper();
        if (symbol.isEmpty()) {
            continue;
        }

        const QString groupKey = symbol;
        AggregateBucket &bucket = groups[groupKey];
        const qint64 rowSequence = rowSequenceFor(row);
        if (bucket.primaryRow < 0 || rowSequence < bucket.primarySequence) {
            bucket.primaryRow = row;
            bucket.primarySequence = rowSequence;
        }
        bucket.rows.append(row);
        appendUnique(bucket.intervals, bucket.intervalSet, rawText(positionsTable_->item(row, 8)));
        appendUnique(bucket.indicators, bucket.indicatorSet, rawText(positionsTable_->item(row, 9)));
        appendUnique(bucket.sides, bucket.sideSet, side);
        appendUnique(bucket.stopLosses, bucket.stopLossSet, rawText(positionsTable_->item(row, 15)));
        appendUnique(bucket.statuses, bucket.statusSet, status);
        appendUniqueLines(bucket.triggeredValues, bucket.triggeredSet, rawText(positionsTable_->item(row, 10)));
        appendUniqueLines(bucket.currentValues, bucket.currentSet, rawText(positionsTable_->item(row, 11)));
        appendUnique(bucket.connectors, bucket.connectorSet, connectorBase(rawText(positionsTable_->item(row, 17))));
        bucket.sizeUsdt += numericValue(positionsTable_->item(row, 1));
        const double lastPrice = numericValue(positionsTable_->item(row, 2));
        if (qIsFinite(lastPrice) && lastPrice > 0.0) {
            bucket.lastPrice = lastPrice;
        }
        bucket.marginUsdt += numericValue(positionsTable_->item(row, 5));
        const double roiBasisValue = tableCellRawRoiBasis(positionsTable_->item(row, 7), numericValue(positionsTable_->item(row, 5)));
        if (qIsFinite(roiBasisValue) && roiBasisValue > 0.0) {
            bucket.roiBasisUsdt += roiBasisValue;
        }
        bucket.quantity += numericValue(positionsTable_->item(row, 6));
        bucket.pnlUsdt += numericValue(positionsTable_->item(row, 7));
        bucket.marginRatio = std::max(bucket.marginRatio, numericValue(positionsTable_->item(row, 3)));
        bucket.liqPrice = std::max(bucket.liqPrice, numericValue(positionsTable_->item(row, 4)));
        if (status == QStringLiteral("OPEN")) {
            ++bucket.openCount;
        } else if (status == QStringLiteral("CLOSED")) {
            ++bucket.closedCount;
        }

        const QString openTime = rawText(positionsTable_->item(row, 13)).trimmed();
        if (!openTime.isEmpty() && openTime != QStringLiteral("-")) {
            if (bucket.openTime.isEmpty() || openTime < bucket.openTime) {
                bucket.openTime = openTime;
            }
        }
        const QString closeTime = rawText(positionsTable_->item(row, 14)).trimmed();
        if (!closeTime.isEmpty() && closeTime != QStringLiteral("-")) {
            if (bucket.closeTime.isEmpty() || closeTime > bucket.closeTime) {
                bucket.closeTime = closeTime;
            }
        }
    }

    QSet<int> secondaryRows;
    for (auto it = groups.cbegin(); it != groups.cend(); ++it) {
        const AggregateBucket &bucket = it.value();
        if (bucket.primaryRow < 0 || bucket.rows.isEmpty()) {
            continue;
        }
        for (int bucketRow : bucket.rows) {
            if (bucketRow != bucket.primaryRow) {
                secondaryRows.insert(bucketRow);
            }
        }

        const int row = bucket.primaryRow;
        const int tradeCount = bucket.rows.size();
        const double pnlPct = bucket.roiBasisUsdt > 1e-9 ? (bucket.pnlUsdt / bucket.roiBasisUsdt) * 100.0 : 0.0;
        const QString intervalText = bucket.intervals.isEmpty() ? QStringLiteral("-") : bucket.intervals.join(QStringLiteral(", "));
        const QString indicatorText = bucket.indicators.isEmpty() ? QStringLiteral("-") : bucket.indicators.join(QStringLiteral(", "));
        const QString sideText = bucket.sides.isEmpty() ? QStringLiteral("-") : bucket.sides.join(QStringLiteral(", "));
        const QString stopLossText = bucket.stopLosses.isEmpty() ? QStringLiteral("-") : bucket.stopLosses.join(QStringLiteral(", "));
        const QString triggeredText = bucket.triggeredValues.isEmpty() ? QStringLiteral("-") : bucket.triggeredValues.join(QStringLiteral("\n"));
        const QString currentText = bucket.currentValues.isEmpty() ? QStringLiteral("-") : bucket.currentValues.join(QStringLiteral("\n"));
        const QString marginRatioText = bucket.marginRatio > 0.0
            ? QStringLiteral("%1%").arg(QString::number(bucket.marginRatio, 'f', 2))
            : QStringLiteral("-");
        const QString liqPriceText = bucket.liqPrice > 0.0
            ? QString::number(bucket.liqPrice, 'f', 6)
            : QStringLiteral("-");
        const QString lastPriceText = bucket.lastPrice > 0.0
            ? QString::number(bucket.lastPrice, 'f', 6)
            : QStringLiteral("-");
        QString statusText;
        if (bucket.openCount > 0 && bucket.closedCount > 0) {
            statusText = QStringLiteral("OPEN + CLOSED");
        } else if (bucket.openCount > 0) {
            statusText = QStringLiteral("OPEN");
        } else if (bucket.closedCount > 0) {
            statusText = QStringLiteral("CLOSED");
        } else {
            statusText = bucket.statuses.isEmpty() ? QStringLiteral("-") : bucket.statuses.join(QStringLiteral(", "));
        }
        const QString symbol = rawText(positionsTable_->item(row, 0)).trimmed().toUpper();

        setDisplayText(row, 0, symbol);
        setDisplayText(row, 1, formatPositionSizeText(bucket.sizeUsdt, bucket.quantity, symbol));
        setDisplayText(row, 2, lastPriceText);
        setDisplayText(row, 3, marginRatioText);
        setDisplayText(row, 4, liqPriceText);
        setDisplayText(row, 5, QString::number(bucket.marginUsdt, 'f', 2));
        setDisplayText(row, 6, formatQuantityWithSymbol(bucket.quantity, symbol));
        ensureItem(row, 1)->setData(kTableCellNumericRole, bucket.sizeUsdt);
        ensureItem(row, 2)->setData(kTableCellNumericRole, bucket.lastPrice);
        ensureItem(row, 3)->setData(kTableCellNumericRole, bucket.marginRatio);
        ensureItem(row, 4)->setData(kTableCellNumericRole, bucket.liqPrice);
        ensureItem(row, 5)->setData(kTableCellNumericRole, bucket.marginUsdt);
        ensureItem(row, 6)->setData(kTableCellNumericRole, bucket.quantity);
        QTableWidgetItem *pnlItem = setDisplayText(row, 7, QStringLiteral("%1 (%2%)")
                                                        .arg(QString::number(bucket.pnlUsdt, 'f', 2),
                                                             QString::number(pnlPct, 'f', 2)));
        pnlItem->setData(Qt::UserRole + 1, bucket.roiBasisUsdt);
        pnlItem->setData(kTableCellNumericRole, bucket.pnlUsdt);
        setDisplayText(row, 8, intervalText);
        setDisplayText(row, 9, indicatorText);
        setDisplayText(row, 10, triggeredText);
        setDisplayText(row, 11, currentText);
        setDisplayText(row, 12, sideText);
        setDisplayText(row, 13, bucket.openTime.isEmpty() ? QStringLiteral("-") : bucket.openTime);
        setDisplayText(
            row,
            14,
            bucket.openCount > 0
                ? QStringLiteral("-")
                : (bucket.closeTime.isEmpty() ? QStringLiteral("-") : bucket.closeTime));
        setDisplayText(row, 15, stopLossText);
        setDisplayText(row, 16, statusText);
        const QString connectorText = bucket.connectors.isEmpty()
            ? QStringLiteral("-")
            : bucket.connectors.join(QStringLiteral(", "));
        setDisplayText(row, 17, QStringLiteral("%1 | %2 trade(s)").arg(connectorText).arg(tradeCount));

        for (int i = 0; i < bucket.rows.size(); ++i) {
            const int bucketRow = bucket.rows.at(i);
            if (bucketRow == row) {
                continue;
            }
            for (int col = 0; col < positionsTable_->columnCount(); ++col) {
                QTableWidgetItem *sourceItem = positionsTable_->item(row, col);
                QTableWidgetItem *targetItem = ensureItem(bucketRow, col);
                if (!targetItem->data(Qt::UserRole).isValid()) {
                    targetItem->setData(Qt::UserRole, targetItem->text());
                }
                targetItem->setText(sourceItem ? sourceItem->text() : QString());
                targetItem->setData(
                    kTableCellNumericRole,
                    sourceItem ? sourceItem->data(kTableCellNumericRole) : QVariant());
                if (col == 7) {
                    targetItem->setData(
                        Qt::UserRole + 1,
                        sourceItem ? sourceItem->data(Qt::UserRole + 1) : QVariant());
                }
            }
        }
    }

    for (int row = 0; row < positionsTable_->rowCount(); ++row) {
        positionsTable_->setRowHidden(row, secondaryRows.contains(row));
    }

    positionsTable_->setSortingEnabled(sortingWasEnabled);
    refreshPositionsTableSizing(resizeColumns, resizeRows);
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::updateDashboardStopLossWidgetState() {
    if (!dashboardStopLossEnableCheck_) {
        return;
    }
    const bool runtimeActive = dashboardRuntimeActive_;
    const bool stopLossEnabled = dashboardStopLossEnableCheck_->isChecked() && !runtimeActive;

    if (dashboardStopLossModeCombo_) {
        dashboardStopLossModeCombo_->setEnabled(stopLossEnabled);
    }
    if (dashboardStopLossScopeCombo_) {
        dashboardStopLossScopeCombo_->setEnabled(stopLossEnabled);
    }

    QString mode = dashboardStopLossModeCombo_
        ? dashboardStopLossModeCombo_->currentData().toString().trimmed().toLower()
        : QString();
    if (mode.isEmpty()) {
        mode = QStringLiteral("usdt");
    }
    const bool enableUsdt = stopLossEnabled && (mode == "usdt" || mode == "both");
    const bool enablePercent = stopLossEnabled && (mode == "percent" || mode == "both");

    if (dashboardStopLossUsdtSpin_) {
        dashboardStopLossUsdtSpin_->setEnabled(enableUsdt);
    }
    if (dashboardStopLossPercentSpin_) {
        dashboardStopLossPercentSpin_->setEnabled(enablePercent);
    }
}

void TradingBotWindow::setDashboardRuntimeControlsEnabled(bool enabled) {
    for (QWidget *widget : dashboardRuntimeLockWidgets_) {
        if (widget) {
            widget->setEnabled(enabled);
        }
    }

    if (dashboardLeadTraderCombo_) {
        const bool leadEnabled = enabled
            && dashboardLeadTraderEnableCheck_
            && dashboardLeadTraderEnableCheck_->isChecked();
        dashboardLeadTraderCombo_->setEnabled(leadEnabled);
    }

    for (auto it = dashboardIndicatorChecks_.begin(); it != dashboardIndicatorChecks_.end(); ++it) {
        if (QCheckBox *cb = it.value()) {
            cb->setEnabled(enabled);
        }
    }
    for (auto it = dashboardIndicatorButtons_.begin(); it != dashboardIndicatorButtons_.end(); ++it) {
        QPushButton *btn = it.value();
        QCheckBox *cb = dashboardIndicatorChecks_.value(it.key(), nullptr);
        if (btn) {
            btn->setEnabled(enabled && cb && cb->isChecked());
        }
    }

    if (dashboardStopLossEnableCheck_) {
        dashboardStopLossEnableCheck_->setEnabled(enabled);
    }
    updateDashboardStopLossWidgetState();

    if (dashboardStartBtn_) {
        dashboardStartBtn_->setEnabled(enabled);
    }
    if (dashboardStopBtn_) {
        dashboardStopBtn_->setEnabled(!enabled);
    }
    syncDashboardPaperBalanceUi();
}

void TradingBotWindow::updateStatusMessage(const QString &message) {
    if (statusLabel_) {
        statusLabel_->setText(message);
    }
}

void TradingBotWindow::appendUniqueInterval(const QString &interval) {
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

void TradingBotWindow::appendDashboardAllLog(const QString &message) {
    if (!dashboardAllLogsEdit_) {
        return;
    }
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    dashboardAllLogsEdit_->append(QString("%1 %2").arg(ts, message));
}

void TradingBotWindow::appendDashboardPositionLog(const QString &message) {
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    if (dashboardPositionLogsEdit_) {
        dashboardPositionLogsEdit_->append(QString("%1 %2").arg(ts, message));
    }
    if (dashboardAllLogsEdit_) {
        dashboardAllLogsEdit_->append(QString("%1 [Position] %2").arg(ts, message));
    }
}

void TradingBotWindow::appendDashboardWaitingLog(const QString &message) {
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    if (dashboardWaitingLogsEdit_) {
        dashboardWaitingLogsEdit_->append(QString("%1 %2").arg(ts, message));
    }
    if (dashboardAllLogsEdit_) {
        dashboardAllLogsEdit_->append(QString("%1 [Waiting] %2").arg(ts, message));
    }
}

void TradingBotWindow::refreshDashboardWaitingQueueTable() {
    if (!dashboardWaitingQueueTable_) {
        return;
    }

    QList<QVariantMap> combinedEntries = dashboardWaitingActiveEntries_.values();
    combinedEntries.append(dashboardWaitingHistoryEntries_);

    std::sort(combinedEntries.begin(), combinedEntries.end(), [](const QVariantMap &a, const QVariantMap &b) {
        const QString stateA = a.value(QStringLiteral("state")).toString().trimmed().toLower();
        const QString stateB = b.value(QStringLiteral("state")).toString().trimmed().toLower();
        const int endedRankA = stateA == QStringLiteral("ended") ? 1 : 0;
        const int endedRankB = stateB == QStringLiteral("ended") ? 1 : 0;
        if (endedRankA != endedRankB) {
            return endedRankA < endedRankB;
        }
        const double ageA = a.value(QStringLiteral("age")).toDouble();
        const double ageB = b.value(QStringLiteral("age")).toDouble();
        if (!qFuzzyCompare(ageA + 1.0, ageB + 1.0)) {
            return ageA > ageB;
        }
        const QString symbolA = a.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        const QString symbolB = b.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        return symbolA < symbolB;
    });

    dashboardWaitingQueueTable_->setSortingEnabled(false);
    dashboardWaitingQueueTable_->clearContents();
    dashboardWaitingQueueTable_->setRowCount(combinedEntries.size());

    for (int row = 0; row < combinedEntries.size(); ++row) {
        const QVariantMap &entry = combinedEntries.at(row);
        const QString symbol = entry.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        const QString interval = entry.value(QStringLiteral("interval")).toString().trimmed().toUpper();
        const QString side = entry.value(QStringLiteral("side")).toString().trimmed().toUpper();
        const QString context = entry.value(QStringLiteral("context")).toString().trimmed();
        const QString state = entry.value(QStringLiteral("state")).toString().trimmed();
        int ageSeconds = entry.value(QStringLiteral("age_seconds")).toInt();
        if (ageSeconds < 0) {
            ageSeconds = 0;
        }

        auto makeItem = [](const QString &text, bool centered = false) -> QTableWidgetItem * {
            auto *item = new QTableWidgetItem(text);
            if (centered) {
                item->setTextAlignment(Qt::AlignCenter);
            }
            return item;
        };

        dashboardWaitingQueueTable_->setItem(row, 0, makeItem(symbol.isEmpty() ? QStringLiteral("-") : symbol, true));
        dashboardWaitingQueueTable_->setItem(row, 1, makeItem(interval.isEmpty() ? QStringLiteral("-") : interval, true));
        dashboardWaitingQueueTable_->setItem(row, 2, makeItem(side.isEmpty() ? QStringLiteral("-") : side, true));
        dashboardWaitingQueueTable_->setItem(row, 3, makeItem(context.isEmpty() ? QStringLiteral("-") : context, false));
        dashboardWaitingQueueTable_->setItem(row, 4, makeItem(state.isEmpty() ? QStringLiteral("-") : state, true));
        dashboardWaitingQueueTable_->setItem(row, 5, makeItem(QString::number(ageSeconds), true));
    }

    dashboardWaitingQueueTable_->setSortingEnabled(true);
}

void TradingBotWindow::startDashboardRuntime() {
    if (dashboardRuntimeStopping_) {
        appendDashboardAllLog("Start ignored: runtime stop/close sequence is still in progress.");
        return;
    }
    if (!dashboardOverridesTable_) {
        return;
    }
    if (dashboardOverridesTable_->rowCount() <= 0) {
        appendDashboardAllLog("Start blocked: no symbol/interval override rows found.");
        appendDashboardWaitingLog("No overrides queued. Add at least one pair first.");
        QMessageBox::information(this, tr("Start blocked"), tr("Add at least one Symbol / Interval override row first."));
        return;
    }

    if (dashboardStartBtn_) {
        dashboardStartBtn_->setEnabled(false);
    }
    if (dashboardStopBtn_) {
        dashboardStopBtn_->setEnabled(true);
    }

    handleRunBacktest();
    dashboardRuntimeActive_ = true;
    dashboardRuntimeStopping_ = false;
    setDashboardRuntimeControlsEnabled(false);
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("ON");
        dashboardBotStatusLabel_->setStyleSheet("color: #16a34a; font-weight: 700;");
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("0s");
    }
    refreshPositionsSummaryLabels();

    if (!dashboardRuntimeTimer_) {
        dashboardRuntimeTimer_ = new QTimer(this);
        connect(dashboardRuntimeTimer_, &QTimer::timeout, this, &TradingBotWindow::runDashboardRuntimeCycle);
    }
    const bool useWebSocketFeed = dashboardSignalFeedCombo_
        && normalizedSignalFeedKey(dashboardSignalFeedCombo_->currentText()) == QStringLiteral("websocket")
        && qtWebSocketsRuntimeAvailable();
    dashboardRuntimeTimer_->setInterval(dashboardRuntimePollIntervalMs(dashboardOverridesTable_, useWebSocketFeed));
    dashboardRuntimeLastEvalMs_.clear();
    dashboardRuntimeEntryRetryAfterMs_.clear();
    dashboardRuntimeOpenQtyCaps_.clear();
    dashboardRuntimeConnectorWarnings_.clear();
    dashboardRuntimeIntervalWarnings_.clear();
    clearRuntimeSignalSockets(dashboardRuntimeSignalSockets_);
    dashboardRuntimeSignalCandles_.clear();
    dashboardRuntimeSignalLastClosed_.clear();
    dashboardRuntimeSignalUpdateMs_.clear();
    const int staleOpenCount = dashboardRuntimeOpenPositions_.size();
    dashboardRuntimeOpenPositions_.clear();
    if (staleOpenCount > 0) {
        appendDashboardPositionLog(QString("Reset %1 stale in-memory open position(s) before start.").arg(staleOpenCount));
    }
    dashboardWaitingActiveEntries_.clear();
    dashboardWaitingHistoryEntries_.clear();
    refreshDashboardWaitingQueueTable();
    dashboardRuntimeTimer_->start();

    appendDashboardAllLog("Start triggered from Dashboard.");
    if (dashboardModeCombo_ && isPaperTradingModeLabel(dashboardModeCombo_->currentText())) {
        appendDashboardAllLog("Paper Local active: using live Binance market data with local paper execution.");
    } else if (dashboardModeCombo_ && isTestnetModeLabel(dashboardModeCombo_->currentText())) {
        appendDashboardAllLog("Demo active: using Binance Futures Testnet market data and testnet execution.");
    }
    appendDashboardAllLog(
        QString("Signal feed: %1")
            .arg(useWebSocketFeed
                     ? QStringLiteral("WebSocket Stream")
                     : ((dashboardSignalFeedCombo_
                             && normalizedSignalFeedKey(dashboardSignalFeedCombo_->currentText()) == QStringLiteral("websocket"))
                            ? QStringLiteral("REST Poll (WebSocket unavailable fallback)")
                            : QStringLiteral("REST Poll"))));
    if (dashboardConnectorCombo_) {
        appendDashboardAllLog(QString("Active default connector: %1").arg(dashboardConnectorCombo_->currentText().trimmed()));
    }
    appendDashboardPositionLog(QString("Runtime strategy loop started with %1 override row(s).").arg(dashboardOverridesTable_->rowCount()));
    runDashboardRuntimeCycle();
}

void TradingBotWindow::stopDashboardRuntime() {
    if (dashboardRuntimeStopping_) {
        return;
    }
    dashboardRuntimeStopping_ = true;
    dashboardRuntimeActive_ = false;
    if (dashboardRuntimeTimer_) {
        dashboardRuntimeTimer_->stop();
    }

    const QString modeText = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
    const bool paperTrading = isPaperTradingModeLabel(modeText);
    const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
    for (auto it = dashboardWaitingActiveEntries_.begin(); it != dashboardWaitingActiveEntries_.end(); ++it) {
        QVariantMap endedEntry = it.value();
        endedEntry.insert(QStringLiteral("state"), QStringLiteral("Ended"));
        endedEntry.insert(QStringLiteral("ended_at_ms"), nowMs);
        const qint64 firstSeenMs = endedEntry.value(QStringLiteral("first_seen_ms")).toLongLong();
        const qint64 elapsedMs = firstSeenMs > 0 ? std::max<qint64>(0, nowMs - firstSeenMs) : 0;
        endedEntry.insert(QStringLiteral("age"), static_cast<double>(elapsedMs) / 1000.0);
        endedEntry.insert(QStringLiteral("age_seconds"), static_cast<int>(elapsedMs / 1000));
        dashboardWaitingHistoryEntries_.append(endedEntry);
    }
    dashboardWaitingActiveEntries_.clear();
    if (dashboardWaitingHistoryEntries_.size() > dashboardWaitingHistoryMax_) {
        const int extra = dashboardWaitingHistoryEntries_.size() - dashboardWaitingHistoryMax_;
        dashboardWaitingHistoryEntries_.erase(
            dashboardWaitingHistoryEntries_.begin(),
            dashboardWaitingHistoryEntries_.begin() + extra);
    }
    refreshDashboardWaitingQueueTable();

    const bool keepOpenPositions = dashboardStopWithoutCloseCheck_ && dashboardStopWithoutCloseCheck_->isChecked();
    const bool futures = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    const bool isTestnet = isTestnetModeLabel(modeText);
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const bool hasApiCredentials = !apiKey.isEmpty() && !apiSecret.isEmpty();
    const bool hedgeMode = dashboardPositionModeCombo_
        ? dashboardPositionModeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("hedge"))
        : true;
    const QString defaultConnectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : connectorLabelForKey(recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig defaultConnectorCfg = resolveConnectorConfig(defaultConnectorText, futures);
    QMap<QString, ConnectorRuntimeConfig> closeConnectorConfigs;
    auto addCloseConnectorConfig = [&closeConnectorConfigs](const ConnectorRuntimeConfig &cfg) {
        if (!cfg.ok()) {
            return;
        }
        const QString dedupeKey = QStringLiteral("%1|%2")
                                      .arg(cfg.key.trimmed().toLower(), cfg.baseUrl.trimmed().toLower());
        if (!closeConnectorConfigs.contains(dedupeKey)) {
            closeConnectorConfigs.insert(dedupeKey, cfg);
        }
    };
    addCloseConnectorConfig(defaultConnectorCfg);

    auto setOrCreateCell = [this](int row, int col, const QString &text) {
        if (!positionsTable_) {
            return;
        }
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            item = new QTableWidgetItem(text);
            positionsTable_->setItem(row, col, item);
        } else {
            item->setText(text);
        }
        item->setData(Qt::UserRole, text);
    };
    auto tableCellRaw = [this](int row, int col) -> QString {
        if (!positionsTable_) {
            return {};
        }
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            return {};
        }
        const QVariant raw = item->data(Qt::UserRole);
        return raw.isValid() ? raw.toString() : item->text();
    };
    if (dashboardOverridesTable_) {
        for (int row = 0; row < dashboardOverridesTable_->rowCount(); ++row) {
            const QTableWidgetItem *connectorItem = dashboardOverridesTable_->item(row, 5);
            const QString rowConnectorText = connectorItem && !connectorItem->text().trimmed().isEmpty()
                ? connectorItem->text().trimmed()
                : defaultConnectorText;
            addCloseConnectorConfig(resolveConnectorConfig(rowConnectorText, futures));
        }
    }
    for (auto it = dashboardRuntimeOpenPositions_.cbegin(); it != dashboardRuntimeOpenPositions_.cend(); ++it) {
        const RuntimePosition &openPos = it.value();
        ConnectorRuntimeConfig cfg;
        cfg.key = openPos.connectorKey.trimmed();
        cfg.label = cfg.key;
        cfg.baseUrl = openPos.connectorBaseUrl.trimmed();
        addCloseConnectorConfig(cfg);
    }

    int closeRequested = 0;
    int closeSucceeded = 0;
    int closePartial = 0;
    int closeFailed = 0;
    QMap<QString, BinanceRestClient::FuturesPositionsResult> stopLivePositionsCache;
    const auto stopSnapshotCacheKeyFor = [isTestnet](const QString &baseUrl) {
        return QStringLiteral("%1|%2")
            .arg(baseUrl.trimmed().toLower(),
                 isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"));
    };
    const auto fetchStopLivePositions =
        [&apiKey, &apiSecret, isTestnet, &stopLivePositionsCache, &stopSnapshotCacheKeyFor](
            const QString &baseUrl) -> const BinanceRestClient::FuturesPositionsResult * {
        const QString cacheKey = stopSnapshotCacheKeyFor(baseUrl);
        auto it = stopLivePositionsCache.find(cacheKey);
        if (it == stopLivePositionsCache.end()) {
            it = stopLivePositionsCache.insert(
                cacheKey,
                BinanceRestClient::fetchOpenFuturesPositions(
                    apiKey,
                    apiSecret,
                    isTestnet,
                    10000,
                    baseUrl));
        }
        return &it.value();
    };
    const auto clearStopLivePositionsCache = [&stopLivePositionsCache, &stopSnapshotCacheKeyFor](const QString &baseUrl) {
        stopLivePositionsCache.remove(stopSnapshotCacheKeyFor(baseUrl));
    };
    const auto pickStopLivePosition =
        [hedgeMode](
            const BinanceRestClient::FuturesPositionsResult *snapshot,
            const QString &symbol,
            const QString &runtimeSide) -> const BinanceRestClient::FuturesPosition * {
        if (!snapshot || !snapshot->ok) {
            return nullptr;
        }
        const QString sym = symbol.trimmed().toUpper();
        const QString side = runtimeSide.trimmed().toUpper();
        const BinanceRestClient::FuturesPosition *best = nullptr;
        double bestAbsAmt = 0.0;
        for (const auto &pos : snapshot->positions) {
            if (pos.symbol.trimmed().toUpper() != sym) {
                continue;
            }
            const double absAmt = std::fabs(pos.positionAmt);
            if (!qIsFinite(absAmt) || absAmt <= 1e-10) {
                continue;
            }
            const QString posSide = pos.positionSide.trimmed().toUpper();
            const bool sideMatches = (side == QStringLiteral("LONG") && pos.positionAmt > 0.0)
                || (side == QStringLiteral("SHORT") && pos.positionAmt < 0.0)
                || side.isEmpty();
            if (hedgeMode) {
                if ((side == QStringLiteral("LONG") && posSide == QStringLiteral("LONG"))
                    || (side == QStringLiteral("SHORT") && posSide == QStringLiteral("SHORT"))) {
                    return &pos;
                }
            } else if ((posSide.isEmpty() || posSide == QStringLiteral("BOTH")) && sideMatches) {
                return &pos;
            }
            if (sideMatches && absAmt > bestAbsAmt) {
                bestAbsAmt = absAmt;
                best = &pos;
            }
        }
        return best;
    };
    QSet<QString> fullyClosedKeys;
    const QString stopNowText = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
    if (keepOpenPositions) {
        appendDashboardPositionLog("Stop requested with 'Stop Without Closing Active Positions' enabled: keeping exchange positions open.");
    } else if (paperTrading) {
        int paperClosed = 0;
        const QList<QString> runtimeKeys = dashboardRuntimeOpenPositions_.keys();
        for (const QString &runtimeKey : runtimeKeys) {
            pumpUiEvents();
            const RuntimePosition openPos = dashboardRuntimeOpenPositions_.value(runtimeKey);
            const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
            const QString interval = openPos.interval.trimmed();
            int targetRow = -1;
            if (positionsTable_) {
                for (int row = positionsTable_->rowCount() - 1; row >= 0; --row) {
                    const QString rowSymbol = tableCellRaw(row, 0).trimmed().toUpper();
                    const QString rowInterval = tableCellRaw(row, 8).trimmed();
                    const QString rowStatus = tableCellRaw(row, 16).trimmed().toUpper();
                    if (rowSymbol == symbol
                        && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                        && rowStatus == QStringLiteral("OPEN")) {
                        targetRow = row;
                        break;
                    }
                }
            }

            QString closePriceText = qIsFinite(openPos.entryPrice) && openPos.entryPrice > 0.0
                ? QString::number(openPos.entryPrice, 'f', 6)
                : QStringLiteral("-");
            if (targetRow >= 0) {
                const QString tablePrice = tableCellRaw(targetRow, 2).trimmed();
                if (!tablePrice.isEmpty() && tablePrice != QStringLiteral("-")) {
                    closePriceText = tablePrice;
                }
                setOrCreateCell(targetRow, 14, stopNowText);
                setOrCreateCell(targetRow, 16, QStringLiteral("CLOSED"));
            }

            ++paperClosed;
            appendDashboardPositionLog(
                QString("Stop paper closed %1 %2@%3 at %4.")
                    .arg(openPos.side.trimmed().isEmpty() ? QStringLiteral("POSITION") : openPos.side.trimmed(),
                         symbol.isEmpty() ? QStringLiteral("-") : symbol,
                         interval.isEmpty() ? QStringLiteral("-") : interval,
                         closePriceText));
            dashboardRuntimeOpenPositions_.remove(runtimeKey);
        }
        if (paperClosed > 0) {
            appendDashboardPositionLog(QString("Stop paper close summary: closed=%1.").arg(paperClosed));
        } else {
            appendDashboardPositionLog("Stop paper close summary: no active paper positions to close.");
        }
    } else if (!dashboardRuntimeOpenPositions_.isEmpty()) {
        if (!futures) {
            appendDashboardPositionLog("Stop close skipped: auto-close is supported for Futures account type only.");
            closeFailed = dashboardRuntimeOpenPositions_.size();
        } else if (!hasApiCredentials) {
            appendDashboardPositionLog("Stop close skipped: missing API credentials.");
            closeFailed = dashboardRuntimeOpenPositions_.size();
        } else {
            for (auto it = dashboardRuntimeOpenPositions_.begin(); it != dashboardRuntimeOpenPositions_.end(); ++it) {
                pumpUiEvents();
                const QString runtimeKey = it.key();
                RuntimePosition &openPos = it.value();
                const QString symbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
                const QString interval = openPos.interval.trimmed();
                const QStringList keyParts = runtimeKey.split('|');
                QString connectorKey = openPos.connectorKey.trimmed().toLower();
                QString connectorBaseUrl = openPos.connectorBaseUrl.trimmed();
                if (connectorKey.isEmpty() && keyParts.size() >= 3) {
                    connectorKey = keyParts.at(2).trimmed().toLower();
                }
                if (connectorBaseUrl.isEmpty() && keyParts.size() >= 4) {
                    connectorBaseUrl = keyParts.mid(3).join(QStringLiteral("|")).trimmed();
                }

                const auto *liveSnapshot = fetchStopLivePositions(connectorBaseUrl);
                const auto *livePos = pickStopLivePosition(liveSnapshot, symbol, openPos.side);
                if (livePos) {
                    const double liveQty = std::fabs(livePos->positionAmt);
                    if (qIsFinite(liveQty) && liveQty > 1e-10) {
                        openPos.quantity = liveQty;
                    }
                    if (qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                        openPos.entryPrice = livePos->entryPrice;
                    }
                    if (qIsFinite(livePos->leverage) && livePos->leverage > 0.0) {
                        openPos.leverage = livePos->leverage;
                    }
                    const double marginFallback = std::max(
                        1e-9,
                        (std::max(0.0, openPos.entryPrice) * std::max(0.0, openPos.quantity))
                            / std::max(1.0, openPos.leverage));
                    openPos.displayMarginUsdt = std::max(
                        1e-9,
                        livePositionTotalDisplayMargin(
                            livePos,
                            std::max(marginFallback, openPos.displayMarginUsdt)));
                    openPos.roiBasisUsdt = std::max(
                        1e-9,
                        livePositionTotalRoiBasis(
                            livePos,
                            std::max(marginFallback, openPos.roiBasisUsdt)));
                }

                if (symbol.isEmpty() || !qIsFinite(openPos.quantity) || openPos.quantity <= 0.0) {
                    ++closeFailed;
                    appendDashboardPositionLog(
                        QString("Stop close skipped: invalid runtime position key=%1 symbol=%2 qty=%3")
                            .arg(runtimeKey, symbol, QString::number(openPos.quantity, 'f', 8)));
                    continue;
                }

                const QString closeOrderSide = (openPos.side == QStringLiteral("LONG")) ? QStringLiteral("SELL")
                                                                                         : QStringLiteral("BUY");
                const QString closePositionSide = hedgeMode ? openPos.side : QString();
                const bool closeReduceOnly = !hedgeMode;
                int targetRow = -1;
                if (positionsTable_) {
                    for (int row = positionsTable_->rowCount() - 1; row >= 0; --row) {
                        const QString rowSymbol = tableCellRaw(row, 0).trimmed().toUpper();
                        const QString rowInterval = tableCellRaw(row, 8).trimmed();
                        const QString rowStatus = tableCellRaw(row, 16).trimmed().toUpper();
                        const QString rowConnectorHint = tableCellRaw(row, 17).trimmed().toLower();
                        if (rowSymbol == symbol
                            && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                            && rowStatus == QStringLiteral("OPEN")
                            && (connectorKey.isEmpty() || rowConnectorHint.contains(connectorKey))) {
                            targetRow = row;
                            break;
                        }
                    }
                }
                double fallbackClosePrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                    ? livePos->markPrice
                    : 0.0;
                if (fallbackClosePrice <= 0.0 && targetRow >= 0) {
                    bool tablePriceOk = false;
                    const double tablePrice = firstNumberInText(tableCellRaw(targetRow, 2), &tablePriceOk);
                    if (tablePriceOk && qIsFinite(tablePrice) && tablePrice > 0.0) {
                        fallbackClosePrice = tablePrice;
                    }
                }
                if (fallbackClosePrice <= 0.0 && qIsFinite(openPos.entryPrice) && openPos.entryPrice > 0.0) {
                    fallbackClosePrice = openPos.entryPrice;
                }
                ++closeRequested;
                const auto closeOrder = placeFuturesCloseOrderWithFallback(
                    apiKey,
                    apiSecret,
                    symbol,
                    closeOrderSide,
                    openPos.quantity,
                    isTestnet,
                    closeReduceOnly,
                    closePositionSide,
                    10000,
                    connectorBaseUrl,
                    fallbackClosePrice);

                if (!closeOrder.ok) {
                    if (isReduceOnlyRejectedError(closeOrder.error)) {
                        clearStopLivePositionsCache(connectorBaseUrl);
                        const auto *snapshot = fetchStopLivePositions(connectorBaseUrl);
                        if (!hasMatchingOpenFuturesPosition(snapshot, symbol, openPos.side, hedgeMode)) {
                            ++closeSucceeded;
                            fullyClosedKeys.insert(runtimeKey);
                            if (targetRow >= 0) {
                                setOrCreateCell(targetRow, 14, stopNowText);
                                setOrCreateCell(targetRow, 16, QStringLiteral("CLOSED"));
                            }
                            appendDashboardPositionLog(
                                QString("Stop close confirmed %1 %2@%3 (%4): position is already flat on exchange.")
                                    .arg(openPos.side,
                                         symbol,
                                         interval,
                                         connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey));
                            continue;
                        }
                    }
                    ++closeFailed;
                    appendDashboardPositionLog(
                        QString("Stop close failed %1 %2@%3 (%4): %5")
                            .arg(openPos.side,
                                 symbol,
                                 interval,
                                 connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey,
                                 closeOrder.error));
                    continue;
                }
                clearStopLivePositionsCache(connectorBaseUrl);

                const double closePrice = (qIsFinite(closeOrder.avgPrice) && closeOrder.avgPrice > 0.0)
                    ? closeOrder.avgPrice
                    : fallbackClosePrice;
                const double closeQty = (qIsFinite(closeOrder.executedQty) && closeOrder.executedQty > 0.0)
                    ? closeOrder.executedQty
                    : openPos.quantity;
                const double effectiveCloseQty = std::max(0.0, std::min(openPos.quantity, closeQty));
                if (effectiveCloseQty <= 0.0) {
                    ++closeFailed;
                    appendDashboardPositionLog(
                        QString("Stop close failed %1 %2@%3: zero filled quantity.")
                            .arg(openPos.side, symbol, interval));
                    continue;
                }

                const double realizedPnlUsdt = (openPos.side == QStringLiteral("LONG"))
                    ? (closePrice - openPos.entryPrice) * effectiveCloseQty
                    : (openPos.entryPrice - closePrice) * effectiveCloseQty;
                const double totalQtyBeforeClose = std::max(0.0, openPos.quantity);
                const double fallbackCloseMarginUsed = std::max(
                    1e-9,
                    (openPos.entryPrice * effectiveCloseQty) / std::max(1.0, openPos.leverage));
                const double closeShareRatio = totalQtyBeforeClose > 1e-9
                    ? std::min(1.0, std::max(0.0, effectiveCloseQty / totalQtyBeforeClose))
                    : 1.0;
                const double closeRoiBasisUsed = std::max(
                    1e-9,
                    std::max(fallbackCloseMarginUsed, openPos.roiBasisUsdt) * closeShareRatio);
                const double realizedPnlPct = (realizedPnlUsdt / closeRoiBasisUsed) * 100.0;

                if (targetRow >= 0) {
                    setOrCreateCell(targetRow, 2, QString::number(closePrice, 'f', 6));
                    setOrCreateCell(
                        targetRow,
                        7,
                        QStringLiteral("%1 (%2%)")
                            .arg(QString::number(realizedPnlUsdt, 'f', 2),
                                 QString::number(realizedPnlPct, 'f', 2)));
                    setTableCellNumeric(positionsTable_, targetRow, 2, closePrice);
                    setTableCellNumeric(positionsTable_, targetRow, 7, realizedPnlUsdt);
                    if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                        setTableCellRoiBasis(pnlItem, closeRoiBasisUsed);
                    }
                }

                const bool partialClose = (effectiveCloseQty + 1e-9) < openPos.quantity;
                if (partialClose) {
                    ++closePartial;
                    openPos.quantity = std::max(0.0, openPos.quantity - effectiveCloseQty);
                    if (targetRow >= 0) {
                        const double remainingRatio = totalQtyBeforeClose > 1e-9
                            ? std::min(1.0, std::max(0.0, openPos.quantity / totalQtyBeforeClose))
                            : 0.0;
                        const double remainingNotional = std::max(0.0, openPos.quantity * closePrice);
                        const double remainingDisplayMarginUsdt = std::max(
                            0.0,
                            std::max(fallbackCloseMarginUsed, openPos.displayMarginUsdt) * remainingRatio);
                        const double remainingRoiBasisUsdt = std::max(
                            0.0,
                            std::max(fallbackCloseMarginUsed, openPos.roiBasisUsdt) * remainingRatio);
                        openPos.displayMarginUsdt = std::max(1e-9, remainingDisplayMarginUsdt);
                        openPos.roiBasisUsdt = std::max(1e-9, remainingRoiBasisUsdt);
                        setOrCreateCell(targetRow, 1, formatPositionSizeText(remainingNotional, openPos.quantity, symbol));
                        setOrCreateCell(
                            targetRow,
                            5,
                            QString::number(remainingDisplayMarginUsdt, 'f', 2));
                        setOrCreateCell(targetRow, 6, formatQuantityWithSymbol(openPos.quantity, symbol));
                        setTableCellNumeric(positionsTable_, targetRow, 1, remainingNotional);
                        setTableCellNumeric(positionsTable_, targetRow, 5, remainingDisplayMarginUsdt);
                        setTableCellNumeric(positionsTable_, targetRow, 6, openPos.quantity);
                        if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                            setTableCellRoiBasis(pnlItem, remainingRoiBasisUsdt);
                        }
                    }
                    appendDashboardPositionLog(
                        QString("Stop partially closed %1 %2@%3 qty=%4 remaining=%5 (connector=%6, orderId=%7): %8")
                            .arg(openPos.side,
                                 symbol,
                                 interval,
                                 QString::number(effectiveCloseQty, 'f', 6),
                                 QString::number(openPos.quantity, 'f', 6),
                                 connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey,
                                 closeOrder.orderId,
                                 closeOrder.error.isEmpty() ? QStringLiteral("remaining exposure still open")
                                                            : closeOrder.error));
                    } else {
                        ++closeSucceeded;
                        fullyClosedKeys.insert(runtimeKey);
                        if (targetRow >= 0) {
                            setOrCreateCell(targetRow, 14, stopNowText);
                            setOrCreateCell(targetRow, 16, QStringLiteral("CLOSED"));
                        }
                    appendDashboardPositionLog(
                        QString("Stop closed %1 %2@%3 at %4 PNL=%5 USDT (%6%%) (connector=%7, orderId=%8)")
                            .arg(openPos.side,
                                 symbol,
                                 interval,
                                 QString::number(closePrice, 'f', 6),
                                 QString::number(realizedPnlUsdt, 'f', 2),
                                 QString::number(realizedPnlPct, 'f', 2),
                                 connectorKey.isEmpty() ? QStringLiteral("default") : connectorKey,
                                 closeOrder.orderId));
                }
            }
            for (const QString &closedKey : fullyClosedKeys) {
                dashboardRuntimeOpenPositions_.remove(closedKey);
            }
        }
    }

    int sweepRequested = 0;
    int sweepSucceeded = 0;
    int sweepPartial = 0;
    int sweepFailed = 0;
    const bool stopNeedsSweep = closeRequested == 0
        || !dashboardRuntimeOpenPositions_.isEmpty()
        || closeFailed > 0
        || closePartial > 0;
    if (!keepOpenPositions && !paperTrading && futures && hasApiCredentials && !closeConnectorConfigs.isEmpty() && stopNeedsSweep) {
        QSet<QString> attemptedSweepKeys;
        for (auto cfgIt = closeConnectorConfigs.cbegin(); cfgIt != closeConnectorConfigs.cend(); ++cfgIt) {
            pumpUiEvents();
            const ConnectorRuntimeConfig &cfg = cfgIt.value();
            const auto snapshot = BinanceRestClient::fetchOpenFuturesPositions(
                apiKey,
                apiSecret,
                isTestnet,
                10000,
                cfg.baseUrl);
            if (!snapshot.ok) {
                ++sweepFailed;
                appendDashboardPositionLog(
                    QString("Stop sweep fetch failed (%1): %2")
                        .arg(cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                             snapshot.error));
                continue;
            }
            for (const auto &pos : snapshot.positions) {
                pumpUiEvents();
                const QString symbol = pos.symbol.trimmed().toUpper();
                if (symbol.isEmpty()) {
                    continue;
                }
                const double qty = std::fabs(pos.positionAmt);
                if (!qIsFinite(qty) || qty <= 1e-10) {
                    continue;
                }
                const bool isLong = pos.positionAmt > 0.0;
                const QString runtimeSide = isLong ? QStringLiteral("LONG") : QStringLiteral("SHORT");
                QString positionSide = pos.positionSide.trimmed().toUpper();
                if (hedgeMode) {
                    if (positionSide != QStringLiteral("LONG") && positionSide != QStringLiteral("SHORT")) {
                        positionSide = runtimeSide;
                    }
                } else {
                    positionSide.clear();
                }
                const QString closeOrderSide = isLong ? QStringLiteral("SELL") : QStringLiteral("BUY");
                const bool closeReduceOnly = !hedgeMode;
                const QString dedupeKey = QStringLiteral("%1|%2|%3|%4|%5")
                                              .arg(cfg.key.trimmed().toLower(),
                                                   cfg.baseUrl.trimmed().toLower(),
                                                   symbol,
                                                   closeOrderSide,
                                                   positionSide);
                if (attemptedSweepKeys.contains(dedupeKey)) {
                    continue;
                }
                attemptedSweepKeys.insert(dedupeKey);
                ++sweepRequested;
                const auto closeOrder = placeFuturesCloseOrderWithFallback(
                    apiKey,
                    apiSecret,
                    symbol,
                    closeOrderSide,
                    qty,
                    isTestnet,
                    closeReduceOnly,
                    positionSide,
                    10000,
                    cfg.baseUrl,
                    (qIsFinite(pos.markPrice) && pos.markPrice > 0.0)
                        ? pos.markPrice
                        : pos.entryPrice);
                if (!closeOrder.ok) {
                    if (isReduceOnlyRejectedError(closeOrder.error)) {
                        clearStopLivePositionsCache(cfg.baseUrl);
                        const auto *snapshot = fetchStopLivePositions(cfg.baseUrl);
                        if (!hasMatchingOpenFuturesPosition(snapshot, symbol, runtimeSide, hedgeMode)) {
                            ++sweepSucceeded;
                            appendDashboardPositionLog(
                                QString("Stop sweep confirmed %1 %2 (%3): position is already flat on exchange.")
                                    .arg(runtimeSide,
                                         symbol,
                                         cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key));
                            continue;
                        }
                    }
                    ++sweepFailed;
                    appendDashboardPositionLog(
                        QString("Stop sweep close failed %1 %2 qty=%3 (%4): %5")
                            .arg(runtimeSide,
                                 symbol,
                                 QString::number(qty, 'f', 6),
                                 cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                                 closeOrder.error));
                    continue;
                }
                clearStopLivePositionsCache(cfg.baseUrl);
                const double filledQty = (qIsFinite(closeOrder.executedQty) && closeOrder.executedQty > 0.0)
                    ? std::min(qty, closeOrder.executedQty)
                    : qty;
                if (!qIsFinite(filledQty) || filledQty <= 1e-10) {
                    ++sweepFailed;
                    appendDashboardPositionLog(
                        QString("Stop sweep close failed %1 %2 qty=%3 (%4): zero fill.")
                            .arg(runtimeSide,
                                 symbol,
                                 QString::number(qty, 'f', 6),
                                 cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key));
                    continue;
                }
                const bool partialSweep = (filledQty + 1e-9) < qty;
                if (partialSweep) {
                    ++sweepPartial;
                    appendDashboardPositionLog(
                        QString("Stop sweep partially closed %1 %2 filled=%3 requested=%4 (%5, orderId=%6): %7")
                            .arg(runtimeSide,
                                 symbol,
                                 QString::number(filledQty, 'f', 6),
                                 QString::number(qty, 'f', 6),
                                 cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                                 closeOrder.orderId,
                                 closeOrder.error.isEmpty() ? QStringLiteral("remaining exposure still open")
                                                            : closeOrder.error));
                    continue;
                }
                ++sweepSucceeded;
                appendDashboardPositionLog(
                    QString("Stop sweep closed %1 %2 qty=%3 (%4, orderId=%5)")
                        .arg(runtimeSide,
                             symbol,
                             QString::number(qty, 'f', 6),
                             cfg.key.isEmpty() ? QStringLiteral("default") : cfg.key,
                             closeOrder.orderId));

                if (positionsTable_) {
                    for (int row = 0; row < positionsTable_->rowCount(); ++row) {
                        const QString rowSymbol = tableCellRaw(row, 0).trimmed().toUpper();
                        const QString rowStatus = tableCellRaw(row, 16).trimmed().toUpper();
                        if (rowSymbol != symbol || rowStatus != QStringLiteral("OPEN")) {
                            continue;
                        }
                        setOrCreateCell(row, 14, stopNowText);
                        setOrCreateCell(row, 16, QStringLiteral("CLOSED"));
                    }
                }
                const QList<QString> runtimeKeys = dashboardRuntimeOpenPositions_.keys();
                for (const QString &runtimeKey : runtimeKeys) {
                    const RuntimePosition runtimePos = dashboardRuntimeOpenPositions_.value(runtimeKey);
                    const QString runtimeSymbol = runtimeKey.section('|', 0, 0).trimmed().toUpper();
                    if (runtimeSymbol != symbol) {
                        continue;
                    }
                    if (runtimePos.side.trimmed().toUpper() != runtimeSide) {
                        continue;
                    }
                    dashboardRuntimeOpenPositions_.remove(runtimeKey);
                }
            }
        }
    }

    if (!keepOpenPositions && !paperTrading) {
        if (closeRequested > 0 || closeFailed > 0) {
            appendDashboardPositionLog(
                QString("Stop close summary: requested=%1 succeeded=%2 partial=%3 failed=%4.")
                    .arg(closeRequested)
                    .arg(closeSucceeded)
                    .arg(closePartial)
                    .arg(closeFailed));
        } else if (dashboardRuntimeOpenPositions_.isEmpty()) {
            appendDashboardPositionLog("Stop close summary: no active runtime positions to close.");
        }
        if (sweepRequested > 0 || sweepFailed > 0) {
            appendDashboardPositionLog(
                QString("Stop sweep summary: requested=%1 succeeded=%2 partial=%3 failed=%4.")
                    .arg(sweepRequested)
                    .arg(sweepSucceeded)
                    .arg(sweepPartial)
                    .arg(sweepFailed));
        }
    }
    applyPositionsViewMode();

    if (dashboardStopBtn_) {
        dashboardStopBtn_->setEnabled(false);
    }
    if (dashboardStartBtn_) {
        dashboardStartBtn_->setEnabled(true);
    }
    setDashboardRuntimeControlsEnabled(true);
    if (dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("OFF");
        dashboardBotStatusLabel_->setStyleSheet("color: #ef4444; font-weight: 700;");
    }
    if (dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("--");
    }
    handleStopBacktest();
    appendDashboardAllLog("Stop triggered from Dashboard.");
    appendDashboardPositionLog("Runtime strategy loop stopped.");
    clearRuntimeSignalSockets(dashboardRuntimeSignalSockets_);
    dashboardRuntimeSignalCandles_.clear();
    dashboardRuntimeSignalLastClosed_.clear();
    dashboardRuntimeSignalUpdateMs_.clear();
    dashboardRuntimeStopping_ = false;
}

void TradingBotWindow::runDashboardRuntimeCycle() {
    if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_ || dashboardRuntimeCycleInProgress_) {
        return;
    }
    if (!dashboardOverridesTable_ || dashboardOverridesTable_->rowCount() <= 0) {
        return;
    }
    dashboardRuntimeCycleInProgress_ = true;
    struct RuntimeCycleGuard final {
        bool *flag = nullptr;
        ~RuntimeCycleGuard() {
            if (flag) {
                *flag = false;
            }
        }
    } runtimeCycleGuard{&dashboardRuntimeCycleInProgress_};

    bool positionsTableMutated = false;
    bool positionsTableStructureChanged = false;
    auto flushPendingPositionsView = [&]() {
        if (!positionsTableMutated) {
            return;
        }
        if (positionsCumulativeView_) {
            applyPositionsViewMode(positionsTableStructureChanged, positionsTableStructureChanged);
        } else {
            refreshPositionsSummaryLabels();
            if (positionsTableStructureChanged) {
                refreshPositionsTableSizing();
            }
        }
        positionsTableMutated = false;
        positionsTableStructureChanged = false;
    };
    auto applyCumulativeViewImmediately = [&]() {
        if (!positionsCumulativeView_ || !positionsTable_ || !positionsTableMutated) {
            return;
        }
        ScopedTableUpdatesPause updatesPause(positionsTable_);
        applyPositionsViewMode(false, false);
    };
    QSet<QString> waitingSeenThisCycle;
    const qint64 cycleNowMs = QDateTime::currentMSecsSinceEpoch();

    const bool futures = dashboardAccountTypeCombo_
        ? dashboardAccountTypeCombo_->currentText().trimmed().toLower().startsWith("fut")
        : true;
    const QString modeText = dashboardModeCombo_ ? dashboardModeCombo_->currentText() : QStringLiteral("Live");
    const bool paperTrading = isPaperTradingModeLabel(modeText);
    const bool isTestnet = isTestnetModeLabel(modeText);
    const QString indicatorSourceText = dashboardIndicatorSourceCombo_
        ? dashboardIndicatorSourceCombo_->currentText().trimmed()
        : QStringLiteral("Binance futures");
    const QString indicatorSourceKey = normalizedIndicatorSourceKey(indicatorSourceText);
    const QString signalFeedText = dashboardSignalFeedCombo_
        ? dashboardSignalFeedCombo_->currentText().trimmed()
        : QStringLiteral("REST Poll");
    const QString signalFeedKey = normalizedSignalFeedKey(signalFeedText);
    const bool websocketFeedRequested = signalFeedKey == QStringLiteral("websocket");
    const bool useWebSocketFeed = websocketFeedRequested && qtWebSocketsRuntimeAvailable();
    const QString defaultConnectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : connectorLabelForKey(recommendedConnectorKey(futures));
    const ConnectorRuntimeConfig defaultConnectorCfg = resolveConnectorConfig(defaultConnectorText, futures);

    const auto indicatorParamDouble =
        [this](const QString &indicatorKey, const QString &fieldKey, double fallback) -> double {
        const QVariantMap cfg = dashboardIndicatorParams_.value(indicatorKey);
        if (!cfg.contains(fieldKey)) {
            return fallback;
        }
        bool ok = false;
        const double value = cfg.value(fieldKey).toDouble(&ok);
        return (ok && qIsFinite(value)) ? value : fallback;
    };
    const auto indicatorParamInt =
        [this](const QString &indicatorKey, const QString &fieldKey, int fallback) -> int {
        const QVariantMap cfg = dashboardIndicatorParams_.value(indicatorKey);
        if (!cfg.contains(fieldKey)) {
            return fallback;
        }
        bool ok = false;
        const int value = cfg.value(fieldKey).toInt(&ok);
        return (ok && value > 0) ? value : fallback;
    };

    double rsiBuyThreshold = indicatorParamDouble(QStringLiteral("rsi"), QStringLiteral("buy_value"), 30.0);
    double rsiSellThreshold = indicatorParamDouble(QStringLiteral("rsi"), QStringLiteral("sell_value"), 70.0);
    if (rsiBuyThreshold < 0.0 || rsiBuyThreshold > 100.0
        || rsiSellThreshold < 0.0 || rsiSellThreshold > 100.0
        || rsiBuyThreshold >= rsiSellThreshold) {
        rsiBuyThreshold = 30.0;
        rsiSellThreshold = 70.0;
    }

    double stochBuyThreshold = indicatorParamDouble(QStringLiteral("stoch_rsi"), QStringLiteral("buy_value"), 20.0);
    double stochSellThreshold = indicatorParamDouble(QStringLiteral("stoch_rsi"), QStringLiteral("sell_value"), 80.0);
    if (stochBuyThreshold < 0.0 || stochBuyThreshold > 100.0
        || stochSellThreshold < 0.0 || stochSellThreshold > 100.0
        || stochBuyThreshold >= stochSellThreshold) {
        stochBuyThreshold = 20.0;
        stochSellThreshold = 80.0;
    }

    double willrBuyThreshold = indicatorParamDouble(QStringLiteral("willr"), QStringLiteral("buy_value"), -80.0);
    double willrSellThreshold = indicatorParamDouble(QStringLiteral("willr"), QStringLiteral("sell_value"), -20.0);
    willrBuyThreshold = std::max(-100.0, std::min(0.0, willrBuyThreshold));
    willrSellThreshold = std::max(-100.0, std::min(0.0, willrSellThreshold));
    if (willrBuyThreshold >= willrSellThreshold) {
        willrBuyThreshold = -80.0;
        willrSellThreshold = -20.0;
    }

    const int rsiLength = std::max(2, indicatorParamInt(QStringLiteral("rsi"), QStringLiteral("length"), 14));
    const int stochLength = std::max(2, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("length"), 14));
    const int stochSmoothK = std::max(1, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("smooth_k"), 3));
    const int stochSmoothD = std::max(1, indicatorParamInt(QStringLiteral("stoch_rsi"), QStringLiteral("smooth_d"), 3));
    const int willrLength = std::max(2, indicatorParamInt(QStringLiteral("willr"), QStringLiteral("length"), 14));

    double availableUsdt = currentDashboardPaperBalanceUsdt();
    const QString apiKey = dashboardApiKey_ ? dashboardApiKey_->text().trimmed() : QString();
    const QString apiSecret = dashboardApiSecret_ ? dashboardApiSecret_->text().trimmed() : QString();
    const bool hasApiCredentials = !apiKey.isEmpty() && !apiSecret.isEmpty();
    const bool hedgeMode = dashboardPositionModeCombo_
        ? dashboardPositionModeCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("hedge"))
        : true;
    QMap<QString, BinanceRestClient::FuturesSymbolFilters> symbolFiltersCache;
    QMap<QString, BinanceRestClient::FuturesPositionsResult> livePositionsCache;
    const auto connectorCacheKeyFor = [isTestnet](const ConnectorRuntimeConfig &cfg) {
        return QStringLiteral("%1|%2|%3")
            .arg(cfg.key.trimmed().toLower(),
                 cfg.baseUrl.trimmed().toLower(),
                 isTestnet ? QStringLiteral("testnet") : QStringLiteral("live"));
    };
    const auto fetchLivePositionsForConnector =
        [this, futures, hasApiCredentials, paperTrading, &apiKey, &apiSecret, isTestnet, &livePositionsCache, &connectorCacheKeyFor](
            const ConnectorRuntimeConfig &cfg) -> const BinanceRestClient::FuturesPositionsResult * {
        if (paperTrading || !futures || !hasApiCredentials || !cfg.ok()) {
            return nullptr;
        }
        const QString cacheKey = connectorCacheKeyFor(cfg);
        auto it = livePositionsCache.find(cacheKey);
        if (it == livePositionsCache.end()) {
            const auto result = BinanceRestClient::fetchOpenFuturesPositions(
                apiKey,
                apiSecret,
                isTestnet,
                10000,
                cfg.baseUrl);
            it = livePositionsCache.insert(cacheKey, result);
            if (!result.ok) {
                const QString warningKey = QStringLiteral("live-positions|%1|%2")
                                               .arg(cacheKey, result.error);
                if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                    dashboardRuntimeConnectorWarnings_.insert(warningKey);
                    appendDashboardPositionLog(
                        QString("Live position snapshot failed (%1): %2")
                            .arg(cfg.key, result.error));
                }
            }
        }
        return &it.value();
    };
    const auto pickLivePosition =
        [hedgeMode](
            const BinanceRestClient::FuturesPositionsResult *snapshot,
            const QString &symbol,
            const QString &runtimeSide) -> const BinanceRestClient::FuturesPosition * {
        if (!snapshot || !snapshot->ok) {
            return nullptr;
        }
        const QString sym = symbol.trimmed().toUpper();
        const QString side = runtimeSide.trimmed().toUpper();
        const BinanceRestClient::FuturesPosition *best = nullptr;
        double bestAbsAmt = 0.0;
        for (const auto &pos : snapshot->positions) {
            if (pos.symbol.trimmed().toUpper() != sym) {
                continue;
            }
            const double absAmt = std::fabs(pos.positionAmt);
            if (absAmt <= 1e-10) {
                continue;
            }
            const QString posSide = pos.positionSide.trimmed().toUpper();
            const bool sideMatches = (side == QStringLiteral("LONG") && pos.positionAmt > 0.0)
                || (side == QStringLiteral("SHORT") && pos.positionAmt < 0.0)
                || side.isEmpty();
            if (hedgeMode) {
                if ((side == QStringLiteral("LONG") && posSide == QStringLiteral("LONG"))
                    || (side == QStringLiteral("SHORT") && posSide == QStringLiteral("SHORT"))) {
                    return &pos;
                }
            } else if ((posSide.isEmpty() || posSide == QStringLiteral("BOTH")) && sideMatches) {
                return &pos;
            }
            if (sideMatches && absAmt > bestAbsAmt) {
                bestAbsAmt = absAmt;
                best = &pos;
            }
        }
        return best;
    };
    QMap<QString, double> runtimeQtyByExposureKey;
    for (auto it = dashboardRuntimeOpenPositions_.cbegin(); it != dashboardRuntimeOpenPositions_.cend(); ++it) {
        const QString runtimeSymbol = it.key().section('|', 0, 0).trimmed().toUpper();
        const RuntimePosition &pos = it.value();
        const QString connectorToken = QStringLiteral("%1|%2")
                                           .arg(pos.connectorKey.trimmed().toLower(),
                                                pos.connectorBaseUrl.trimmed().toLower());
        const QString exposureKey = QStringLiteral("%1|%2|%3")
                                        .arg(runtimeSymbol,
                                             pos.side.trimmed().toUpper(),
                                             connectorToken);
        const double qty = std::max(0.0, pos.quantity);
        if (qty > 0.0) {
            runtimeQtyByExposureKey[exposureKey] += qty;
        }
    }
    const auto ensureSignalStreamForKey =
        [this, useWebSocketFeed, isTestnet]
        (const QString &signalKey,
         const QString &symbol,
         const QString &requestInterval,
         bool signalUsesFutures,
         const QString &baseUrl) -> bool {
        if (!useWebSocketFeed) {
            return false;
        }

        if (!dashboardRuntimeSignalCandles_.contains(signalKey)) {
            const auto seed = BinanceRestClient::fetchKlines(
                symbol,
                requestInterval,
                signalUsesFutures,
                isTestnet && signalUsesFutures,
                240,
                10000,
                baseUrl);
            if (seed.ok && !seed.candles.isEmpty()) {
                dashboardRuntimeSignalCandles_.insert(signalKey, seed.candles);
                dashboardRuntimeSignalLastClosed_.insert(signalKey, false);
                dashboardRuntimeSignalUpdateMs_.insert(signalKey, QDateTime::currentMSecsSinceEpoch());
            } else {
                const QString warningKey = QStringLiteral("signal-seed|%1|%2").arg(signalKey, seed.error);
                if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                    dashboardRuntimeConnectorWarnings_.insert(warningKey);
                    appendDashboardAllLog(
                        QString("Signal stream seed failed for %1@%2: %3")
                            .arg(symbol, requestInterval, seed.error));
                }
            }
        }

        if (dashboardRuntimeSignalSockets_.contains(signalKey)) {
            return dashboardRuntimeSignalCandles_.contains(signalKey)
                && !dashboardRuntimeSignalCandles_.value(signalKey).isEmpty();
        }

        auto *client = new BinanceWsClient(this);
        const QString symbolKey = symbol.trimmed().toUpper();
        const QString intervalKey = requestInterval.trimmed().toLower();
        connect(client, &BinanceWsClient::kline, this, [this, signalKey, symbolKey, intervalKey](
                                                        const QString &streamSymbol,
                                                        const QString &streamInterval,
                                                        qint64 openTimeMs,
                                                        double open,
                                                        double high,
                                                        double low,
                                                        double close,
                                                        double volume,
                                                        bool isClosed) {
            if (streamSymbol.trimmed().toUpper() != symbolKey
                || streamInterval.trimmed().toLower() != intervalKey) {
                return;
            }
            BinanceRestClient::KlineCandle candle;
            candle.openTimeMs = openTimeMs;
            candle.open = open;
            candle.high = high;
            candle.low = low;
            candle.close = close;
            candle.volume = volume;
            auto &cache = dashboardRuntimeSignalCandles_[signalKey];
            if (!cache.isEmpty() && cache.constLast().openTimeMs == openTimeMs) {
                cache.last() = candle;
            } else {
                cache.push_back(candle);
                if (cache.size() > 240) {
                    cache.remove(0, cache.size() - 240);
                }
            }
            dashboardRuntimeSignalLastClosed_[signalKey] = isClosed;
            dashboardRuntimeSignalUpdateMs_[signalKey] = QDateTime::currentMSecsSinceEpoch();
        });
        connect(client, &BinanceWsClient::errorOccurred, this, [this, signalKey, symbolKey, intervalKey](const QString &message) {
            const QString warningKey = QStringLiteral("signal-stream|%1|%2").arg(signalKey, message);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Signal stream error for %1@%2: %3")
                        .arg(symbolKey, intervalKey, message));
            }
        });
        dashboardRuntimeSignalSockets_.insert(signalKey, client);
        client->connectKline(symbol, requestInterval, signalUsesFutures, isTestnet && signalUsesFutures);
        return dashboardRuntimeSignalCandles_.contains(signalKey)
            && !dashboardRuntimeSignalCandles_.value(signalKey).isEmpty();
    };

    if (!futures) {
        const QString warningKey = QStringLiteral("runtime-account-type|spot-unsupported");
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog("Runtime warning: C++ auto-trading currently supports Futures mode only.");
        }
    }
    if (websocketFeedRequested && !useWebSocketFeed) {
        const QString warningKey = QStringLiteral("signal-feed|websocket-unavailable");
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog("Signal feed warning: WebSocket Stream requested but Qt WebSockets runtime is unavailable. Falling back to REST Poll.");
        }
    }
    if (!hasApiCredentials && !paperTrading) {
        const QString warningKey = QStringLiteral("runtime-auth|missing-credentials");
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog("Runtime warning: API key/secret required. Trades will not be submitted.");
        }
    }

    if (!defaultConnectorCfg.ok()) {
        const QString warningKey = QStringLiteral("balance-connector|") + defaultConnectorCfg.error;
        if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
            dashboardRuntimeConnectorWarnings_.insert(warningKey);
            appendDashboardAllLog(QString("Connector warning: %1").arg(defaultConnectorCfg.error));
        }
    } else {
        if (!defaultConnectorCfg.warning.trimmed().isEmpty()) {
            const QString warningKey = QStringLiteral("balance-connector-warning|") + defaultConnectorCfg.warning;
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(QString("Connector fallback: %1").arg(defaultConnectorCfg.warning));
            }
        }
        if (paperTrading) {
            const double paperBalance = currentDashboardPaperBalanceUsdt();
            positionsLastTotalBalanceUsdt_ = paperBalance;
            positionsLastAvailableBalanceUsdt_ = paperBalance;
            availableUsdt = paperBalance;
        } else if (hasApiCredentials) {
            const auto balance = BinanceRestClient::fetchUsdtBalance(
                apiKey,
                apiSecret,
                futures,
                isTestnet,
                6000,
                defaultConnectorCfg.baseUrl);
            if (!balance.ok) {
                appendDashboardPositionLog(
                    QString("Balance fetch failed (%1): %2")
                        .arg(defaultConnectorText, balance.error));
            } else {
                const double totalBalance = std::max(
                    0.0,
                    (balance.totalUsdtBalance > 0.0) ? balance.totalUsdtBalance : balance.usdtBalance);
                const double availableBalance = std::max(
                    0.0,
                    (balance.availableUsdtBalance > 0.0) ? balance.availableUsdtBalance : totalBalance);
                if (qIsFinite(totalBalance) && totalBalance >= 0.0) {
                    positionsLastTotalBalanceUsdt_ = totalBalance;
                }
                if (qIsFinite(availableBalance) && availableBalance >= 0.0) {
                    positionsLastAvailableBalanceUsdt_ = availableBalance;
                }
                if (qIsFinite(availableBalance) && availableBalance > 0.0) {
                    availableUsdt = availableBalance;
                }
            }
        }
    }

    auto touchWaitingEntry = [this, &waitingSeenThisCycle](const QString &waitingKey, qint64 nowMs) {
        auto waitingIt = dashboardWaitingActiveEntries_.find(waitingKey);
        if (waitingIt == dashboardWaitingActiveEntries_.end()) {
            return;
        }
        waitingSeenThisCycle.insert(waitingKey);
        QVariantMap waitingEntry = waitingIt.value();
        qint64 firstSeenMs = waitingEntry.value(QStringLiteral("first_seen_ms")).toLongLong();
        if (firstSeenMs <= 0) {
            firstSeenMs = nowMs;
        }
        const qint64 elapsedMs = std::max<qint64>(0, nowMs - firstSeenMs);
        const double ageSeconds = static_cast<double>(elapsedMs) / 1000.0;
        waitingEntry.insert(QStringLiteral("first_seen_ms"), firstSeenMs);
        waitingEntry.insert(QStringLiteral("updated_ms"), nowMs);
        waitingEntry.insert(QStringLiteral("age"), ageSeconds);
        waitingEntry.insert(QStringLiteral("age_seconds"), static_cast<int>(elapsedMs / 1000));
        waitingEntry.insert(
            QStringLiteral("state"),
            ageSeconds >= kWaitingPositionLateThresholdSec
                ? QStringLiteral("Late")
                : QStringLiteral("Queued"));
        waitingIt.value() = waitingEntry;
    };
    const auto tableCellRaw = [this](int row, int col) -> QString {
        if (!positionsTable_) {
            return {};
        }
        QTableWidgetItem *item = positionsTable_->item(row, col);
        if (!item) {
            return {};
        }
        const QVariant raw = item->data(Qt::UserRole);
        return raw.isValid() ? raw.toString() : item->text();
    };

    for (int row = 0; row < dashboardOverridesTable_->rowCount(); ++row) {
        if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_) {
            break;
        }
        if (row > 0) {
            flushPendingPositionsView();
            pumpUiEvents();
            if (!dashboardRuntimeActive_ || dashboardRuntimeStopping_) {
                break;
            }
        }
        const auto *symbolItem = dashboardOverridesTable_->item(row, 0);
        const auto *intervalItem = dashboardOverridesTable_->item(row, 1);
        if (!symbolItem || !intervalItem) {
            continue;
        }

        const QString symbol = symbolItem->text().trimmed().toUpper();
        const QString interval = intervalItem->text().trimmed();
        if (symbol.isEmpty() || interval.isEmpty()) {
            continue;
        }

        const auto *connectorItem = dashboardOverridesTable_->item(row, 5);
        const QString rowConnectorText = connectorItem && !connectorItem->text().trimmed().isEmpty()
            ? connectorItem->text().trimmed()
            : defaultConnectorText;
        const ConnectorRuntimeConfig rowConnectorCfg = resolveConnectorConfig(rowConnectorText, futures);
        if (!rowConnectorCfg.ok()) {
            const QString warningKey = QStringLiteral("row-connector|%1|%2").arg(rowConnectorText, rowConnectorCfg.error);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Connector warning (%1): %2").arg(rowConnectorText, rowConnectorCfg.error));
            }
            continue;
        }
        if (!rowConnectorCfg.warning.trimmed().isEmpty()) {
            const QString warningKey = QStringLiteral("row-connector-warning|%1|%2")
                                           .arg(rowConnectorText, rowConnectorCfg.warning);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Connector fallback (%1): %2").arg(rowConnectorText, rowConnectorCfg.warning));
            }
        }
        const QString connectorToken = rowConnectorCfg.key + "|" + rowConnectorCfg.baseUrl;
        const QString key = runtimeKeyFor(symbol, interval, connectorToken);
        const auto *loopItem = dashboardOverridesTable_->item(row, 3);
        const qint64 loopSeconds = std::max<qint64>(0, loopSecondsFromText(loopItem ? loopItem->text() : QString()));
        const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
        const qint64 retryAfterMs = dashboardRuntimeEntryRetryAfterMs_.value(key, 0);
        if (retryAfterMs > nowMs) {
            touchWaitingEntry(key, nowMs);
            continue;
        }
        if (retryAfterMs > 0) {
            dashboardRuntimeEntryRetryAfterMs_.remove(key);
        }
        const qint64 lastMs = dashboardRuntimeLastEvalMs_.value(key, 0);
        auto openIt = dashboardRuntimeOpenPositions_.find(key);
        if (loopSeconds > 0 && lastMs > 0 && (nowMs - lastMs) < (loopSeconds * 1000)) {
            if (openIt != dashboardRuntimeOpenPositions_.end() && positionsTable_) {
                RuntimePosition &openPos = openIt.value();
                const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                const auto *livePos = pickLivePosition(liveSnapshot, symbol, openPos.side);
                if ((!qIsFinite(openPos.quantity) || openPos.quantity <= 1e-10)
                    && livePos
                    && qIsFinite(livePos->positionAmt)
                    && std::fabs(livePos->positionAmt) > 1e-10) {
                    openPos.quantity = std::fabs(livePos->positionAmt);
                    if (qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                        openPos.entryPrice = livePos->entryPrice;
                    }
                }

                const double rowQty = std::max(0.0, openPos.quantity);
                const QString exposureKey = QStringLiteral("%1|%2|%3")
                                                .arg(symbol,
                                                     openPos.side.trimmed().toUpper(),
                                                     connectorToken.toLower());
                const double groupQty = runtimeQtyByExposureKey.value(exposureKey, rowQty);
                const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                    ? livePos->markPrice
                    : openPos.entryPrice;
                const double fallbackPnlUsdt = (openPos.side == QStringLiteral("LONG"))
                    ? (markPrice - openPos.entryPrice) * rowQty
                    : (openPos.entryPrice - markPrice) * rowQty;
                const double fallbackMarginUsdt = std::max(
                    1e-9,
                    (openPos.entryPrice * rowQty) / std::max(1.0, openPos.leverage));
                const LivePositionMetricsShare liveShare = allocateLivePositionShare(
                    livePos,
                    rowQty,
                    groupQty,
                    std::max(0.0, rowQty * markPrice),
                    std::max(fallbackMarginUsdt, openPos.displayMarginUsdt),
                    std::max(fallbackMarginUsdt, openPos.roiBasisUsdt),
                    fallbackPnlUsdt);
                openPos.displayMarginUsdt = std::max(1e-9, liveShare.displayMarginUsdt);
                openPos.roiBasisUsdt = std::max(1e-9, liveShare.roiBasisUsdt);
                const double markPnlUsdt = liveShare.pnlUsdt;
                const double markPnlPct = (markPnlUsdt / std::max(1e-9, openPos.roiBasisUsdt)) * 100.0;
                const double sizeUsdt = std::max(0.0, liveShare.sizeUsdt);
                const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
                const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
                const QString marginRatioText = marginRatio > 0.0
                    ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
                    : QStringLiteral("-");
                const QString liqText = liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");

                int targetRow = -1;
                for (int t = positionsTable_->rowCount() - 1; t >= 0; --t) {
                    const QString rowSymbol = tableCellRaw(t, 0).trimmed().toUpper();
                    const QString rowInterval = tableCellRaw(t, 8).trimmed();
                    const QString rowStatus = tableCellRaw(t, 16).trimmed().toUpper();
                    const QString rowConnectorHint = tableCellRaw(t, 17).toLower();
                    if (rowSymbol == symbol
                        && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                        && rowStatus == QStringLiteral("OPEN")
                        && rowConnectorHint.contains(rowConnectorCfg.key.toLower())) {
                        targetRow = t;
                        break;
                    }
                }

                if (targetRow >= 0) {
                    ScopedTableSortingPause sortingPause(positionsTable_);
                    const bool updateVisibleText = !positionsCumulativeView_;
                    auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text, bool preserveWhenUnavailable = false) {
                        QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                        QString finalText = text;
                        if (preserveWhenUnavailable && (text.trimmed().isEmpty() || text.trimmed() == QStringLiteral("-"))) {
                            QString existing;
                            if (item) {
                                const QVariant raw = item->data(Qt::UserRole);
                                existing = raw.isValid() ? raw.toString() : item->text();
                            }
                            existing = existing.trimmed();
                            if (!existing.isEmpty() && existing != QStringLiteral("-")) {
                                finalText = existing;
                            }
                        }
                        if (!item) {
                            item = new QTableWidgetItem(finalText);
                            positionsTable_->setItem(targetRow, col, item);
                        } else if (updateVisibleText) {
                            item->setText(finalText);
                        }
                        item->setData(Qt::UserRole, finalText);
                    };
                    setOrCreate(1, formatPositionSizeText(sizeUsdt, rowQty, symbol));
                    setOrCreate(2, QString::number(markPrice, 'f', 6));
                    setOrCreate(3, marginRatioText, true);
                    setOrCreate(4, liqText, true);
                    setOrCreate(5, QString::number(openPos.displayMarginUsdt, 'f', 2));
                    setOrCreate(6, formatQuantityWithSymbol(rowQty, symbol));
                    setOrCreate(7, QString("%1 (%2%)")
                                    .arg(QString::number(markPnlUsdt, 'f', 2),
                                         QString::number(markPnlPct, 'f', 2)));
                    setTableCellNumeric(positionsTable_, targetRow, 1, sizeUsdt);
                    setTableCellNumeric(positionsTable_, targetRow, 2, markPrice);
                    setTableCellNumeric(positionsTable_, targetRow, 3, marginRatio);
                    setTableCellNumeric(positionsTable_, targetRow, 4, liqPrice);
                    setTableCellNumeric(positionsTable_, targetRow, 5, openPos.displayMarginUsdt);
                    setTableCellNumeric(positionsTable_, targetRow, 6, rowQty);
                    setTableCellNumeric(positionsTable_, targetRow, 7, markPnlUsdt);
                    if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                        setTableCellRoiBasis(pnlItem, openPos.roiBasisUsdt);
                    }
                    positionsTableMutated = true;
                }
            }
            touchWaitingEntry(key, nowMs);
            continue;
        }
        dashboardRuntimeLastEvalMs_.insert(key, nowMs);

        const auto *indicatorItem = dashboardOverridesTable_->item(row, 2);
        const QString indicatorSummary = indicatorItem ? indicatorItem->text() : QString();
        const auto *strategyControlsItem = dashboardOverridesTable_->item(row, 6);
        const QString strategySummary = strategyControlsItem ? strategyControlsItem->text() : QString();
        const bool useLiveSignalCandles = strategyUsesLiveCandles(strategySummary);
        const QSet<QString> indicatorKeys = parseIndicatorKeysFromSummary(indicatorSummary);
        const bool useRsi = indicatorKeys.contains(QStringLiteral("rsi"));
        const bool useStochRsi = indicatorKeys.contains(QStringLiteral("stoch_rsi"));
        const bool useWillr = indicatorKeys.contains(QStringLiteral("willr"));
        if (!useRsi && !useStochRsi && !useWillr) {
            continue;
        }

        QString intervalWarning;
        const QString requestInterval = normalizeBinanceKlineInterval(interval, &intervalWarning);
        if (!intervalWarning.isEmpty()) {
            const QString warningKey = QStringLiteral("%1|%2")
                                           .arg(interval.trimmed().toLower(), requestInterval.trimmed().toLower());
            if (!dashboardRuntimeIntervalWarnings_.contains(warningKey)) {
                dashboardRuntimeIntervalWarnings_.insert(warningKey);
                appendDashboardAllLog(intervalWarning);
            }
        }

        const bool indicatorUsesBinanceFutures = indicatorSourceKey == QStringLiteral("binance_futures");
        const bool indicatorUsesBinanceSpot = indicatorSourceKey == QStringLiteral("binance_spot");
        if (!indicatorUsesBinanceFutures && !indicatorUsesBinanceSpot) {
            const QString warningKey = QStringLiteral("indicator-source|unsupported|%1").arg(indicatorSourceKey);
            if (!dashboardRuntimeConnectorWarnings_.contains(warningKey)) {
                dashboardRuntimeConnectorWarnings_.insert(warningKey);
                appendDashboardAllLog(
                    QString("Indicator source '%1' is not wired for C++ runtime signals yet. Select 'Binance futures' or 'Binance spot'.")
                        .arg(indicatorSourceText));
            }
            touchWaitingEntry(key, nowMs);
            continue;
        }

        const QString signalKey = runtimeKeyFor(symbol, requestInterval, connectorToken);
        QVector<BinanceRestClient::KlineCandle> marketCandles;
        bool latestCandleClosed = false;
        if (useWebSocketFeed) {
            ensureSignalStreamForKey(
                signalKey,
                symbol,
                requestInterval,
                indicatorUsesBinanceFutures,
                rowConnectorCfg.baseUrl);
            marketCandles = dashboardRuntimeSignalCandles_.value(signalKey);
            latestCandleClosed = dashboardRuntimeSignalLastClosed_.value(signalKey, false);
            if (marketCandles.isEmpty()) {
                touchWaitingEntry(key, nowMs);
                continue;
            }
        } else {
            const auto candles = BinanceRestClient::fetchKlines(
                symbol,
                requestInterval,
                indicatorUsesBinanceFutures,
                isTestnet && indicatorUsesBinanceFutures,
                240,
                10000,
                rowConnectorCfg.baseUrl);
            if (!candles.ok || candles.candles.isEmpty()) {
                const QString intervalLabel = requestInterval.compare(interval, Qt::CaseInsensitive) == 0
                    ? interval
                    : QString("%1->%2").arg(interval, requestInterval);
                appendDashboardPositionLog(
                    QString("%1@%2 data fetch failed (%3): %4")
                        .arg(symbol, intervalLabel, rowConnectorText, candles.error));
                touchWaitingEntry(key, nowMs);
                continue;
            }
            marketCandles = candles.candles;
        }

        const QVector<BinanceRestClient::KlineCandle> signalCandles =
            signalCandlesFromSnapshot(marketCandles, useLiveSignalCandles, latestCandleClosed);
        if (signalCandles.isEmpty()) {
            touchWaitingEntry(key, nowMs);
            continue;
        }

        const double price = marketCandles.constLast().close;
        if (!qIsFinite(price) || price <= 0.0) {
            appendDashboardPositionLog(QString("%1@%2 skipped: invalid price data.").arg(symbol, interval));
            touchWaitingEntry(key, nowMs);
            continue;
        }

        bool rsiOk = false;
        double rsi = 0.0;
        if (useRsi) {
            rsi = latestRsiValue(signalCandles, rsiLength, &rsiOk);
        }

        bool stochRsiOk = false;
        double stochRsi = 0.0;
        if (useStochRsi) {
            stochRsi = latestStochRsiValue(signalCandles, stochLength, stochSmoothK, stochSmoothD, &stochRsiOk);
        }

        bool willrOk = false;
        double willr = 0.0;
        if (useWillr) {
            willr = latestWilliamsRValue(signalCandles, willrLength, &willrOk);
        }

        QStringList indicatorValueParts;
        if (useRsi && rsiOk) {
            indicatorValueParts << QString("RSI %1").arg(QString::number(rsi, 'f', 2));
        }
        if (useStochRsi && stochRsiOk) {
            indicatorValueParts << QString("StochRSI %1").arg(QString::number(stochRsi, 'f', 2));
        }
        if (useWillr && willrOk) {
            indicatorValueParts << QString("W%R %1").arg(QString::number(willr, 'f', 2));
        }
        const QString indicatorValueSummary = indicatorValueParts.isEmpty()
            ? QStringLiteral("-")
            : indicatorValueParts.join(QStringLiteral(" | "));

        const bool allowLong = strategyAllowsLong(strategySummary);
        const bool allowShort = strategyAllowsShort(strategySummary);
        if (!allowLong && !allowShort) {
            continue;
        }

        const auto *levItem = dashboardOverridesTable_->item(row, 4);
        bool levOk = false;
        double leverage = levItem ? levItem->text().toDouble(&levOk) : 0.0;
        if (!levOk || leverage <= 0.0) {
            leverage = dashboardLeverageSpin_ ? dashboardLeverageSpin_->value() : 1.0;
        }
        leverage = std::max(1.0, leverage);

        const double positionPct = dashboardPositionPctSpin_ ? dashboardPositionPctSpin_->value() : 2.0;
        const double targetNotionalUsdt = std::max(10.0, availableUsdt * (std::max(0.1, positionPct) / 100.0) * leverage);
        const double requestedQty = std::max(0.000001, targetNotionalUsdt / price);

        if (openIt == dashboardRuntimeOpenPositions_.end()) {
            QString openSide;
            QString triggerText;
            QString triggerSource = QStringLiteral("rsi");
            auto setLongTrigger = [&openSide, &triggerText, &triggerSource](const QString &src, const QString &txt) {
                openSide = QStringLiteral("LONG");
                triggerSource = src;
                triggerText = txt;
            };
            auto setShortTrigger = [&openSide, &triggerText, &triggerSource](const QString &src, const QString &txt) {
                openSide = QStringLiteral("SHORT");
                triggerSource = src;
                triggerText = txt;
            };

            if (useRsi && rsiOk) {
                if (allowLong && rsi <= rsiBuyThreshold) {
                    setLongTrigger(
                        QStringLiteral("rsi"),
                        QString("RSI %1 <= %2")
                            .arg(QString::number(rsi, 'f', 2), QString::number(rsiBuyThreshold, 'f', 2)));
                } else if (allowShort && rsi >= rsiSellThreshold) {
                    setShortTrigger(
                        QStringLiteral("rsi"),
                        QString("RSI %1 >= %2")
                            .arg(QString::number(rsi, 'f', 2), QString::number(rsiSellThreshold, 'f', 2)));
                }
            }
            if (openSide.isEmpty() && useStochRsi && stochRsiOk) {
                if (allowLong && stochRsi <= stochBuyThreshold) {
                    setLongTrigger(
                        QStringLiteral("stoch_rsi"),
                        QString("StochRSI %1 <= %2")
                            .arg(QString::number(stochRsi, 'f', 2), QString::number(stochBuyThreshold, 'f', 2)));
                } else if (allowShort && stochRsi >= stochSellThreshold) {
                    setShortTrigger(
                        QStringLiteral("stoch_rsi"),
                        QString("StochRSI %1 >= %2")
                            .arg(QString::number(stochRsi, 'f', 2), QString::number(stochSellThreshold, 'f', 2)));
                }
            }
            if (openSide.isEmpty() && useWillr && willrOk) {
                if (allowLong && willr <= willrBuyThreshold) {
                    setLongTrigger(
                        QStringLiteral("willr"),
                        QString("Williams %%R %1 <= %2")
                            .arg(QString::number(willr, 'f', 2), QString::number(willrBuyThreshold, 'f', 2)));
                } else if (allowShort && willr >= willrSellThreshold) {
                    setShortTrigger(
                        QStringLiteral("willr"),
                        QString("Williams %%R %1 >= %2")
                            .arg(QString::number(willr, 'f', 2), QString::number(willrSellThreshold, 'f', 2)));
                }
            }

            if (openSide.isEmpty()) {
                // "No trigger yet" is a normal monitoring state, not a pending queue item.
                // Keeping these in waiting queue caused rows to stay Late indefinitely.
                continue;
            }

            if (!futures) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 signal ignored: runtime trading supports Futures only.")
                        .arg(openSide, symbol, interval));
                touchWaitingEntry(key, nowMs);
                continue;
            }
            if (!paperTrading && !hasApiCredentials) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 signal queued: API credentials are missing.")
                        .arg(openSide, symbol, interval));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            const QString filterCacheKey = QStringLiteral("%1|%2|%3")
                                               .arg(symbol, rowConnectorCfg.baseUrl, isTestnet ? QStringLiteral("testnet")
                                                                                                 : QStringLiteral("live"));
            BinanceRestClient::FuturesSymbolFilters symbolFilters = symbolFiltersCache.value(filterCacheKey);
            if (!symbolFilters.ok) {
                symbolFilters = BinanceRestClient::fetchFuturesSymbolFilters(
                    symbol,
                    isTestnet,
                    10000,
                    rowConnectorCfg.baseUrl);
                symbolFiltersCache.insert(filterCacheKey, symbolFilters);
            }
            if (!symbolFilters.ok) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked: symbol filters fetch failed (%4): %5")
                        .arg(openSide, symbol, interval, rowConnectorCfg.key, symbolFilters.error));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            double cappedRequestedQty = requestedQty;
            const double storedQtyCap = dashboardRuntimeOpenQtyCaps_.value(key, 0.0);
            if (qIsFinite(storedQtyCap) && storedQtyCap > 0.0) {
                cappedRequestedQty = std::min(cappedRequestedQty, storedQtyCap);
            }
            const double orderQty = normalizeFuturesOrderQuantity(cappedRequestedQty, price, symbolFilters);
            if (!qIsFinite(orderQty) || orderQty <= 0.0) {
                appendDashboardPositionLog(
                    QString("%1 %2@%3 blocked: normalized order quantity is invalid (requested=%4).")
                        .arg(openSide, symbol, interval, QString::number(cappedRequestedQty, 'f', 8)));
                touchWaitingEntry(key, nowMs);
                continue;
            }

            const QString openOrderSide = (openSide == QStringLiteral("LONG")) ? QStringLiteral("BUY") : QStringLiteral("SELL");
            const QString openPositionSide = hedgeMode ? openSide : QString();
            QString openOrderId;
            double filledQty = orderQty;
            double entryPrice = price;
            QString openOrderInfo;
            const BinanceRestClient::FuturesPosition *livePos = nullptr;
            if (paperTrading) {
                openOrderId = QStringLiteral("paper-open-%1").arg(QDateTime::currentMSecsSinceEpoch());
            } else {
                const auto openOrder = placeFuturesOpenOrderWithFallback(
                    apiKey,
                    apiSecret,
                    symbol,
                    openOrderSide,
                    orderQty,
                    isTestnet,
                    openPositionSide,
                    10000,
                    rowConnectorCfg.baseUrl);
                if (!openOrder.ok) {
                    if (isPercentPriceFilterError(openOrder.error)) {
                        double reducedQtyCap = orderQty * 0.5;
                        if (qIsFinite(symbolFilters.stepSize) && symbolFilters.stepSize > 0.0) {
                            reducedQtyCap = floorToOrderStep(
                                reducedQtyCap,
                                symbolFilters.stepSize,
                                symbolFilters.quantityPrecision);
                        }
                        const double minQtyCap = (qIsFinite(symbolFilters.minQty) && symbolFilters.minQty > 0.0)
                            ? symbolFilters.minQty
                            : (qIsFinite(symbolFilters.stepSize) && symbolFilters.stepSize > 0.0
                                   ? symbolFilters.stepSize
                                   : 0.0);
                        if (reducedQtyCap > 0.0) {
                            reducedQtyCap = std::max(minQtyCap, reducedQtyCap);
                            dashboardRuntimeOpenQtyCaps_.insert(key, reducedQtyCap);
                        }
                        const qint64 retryDelayMs = isTestnet ? 15000 : 5000;
                        dashboardRuntimeEntryRetryAfterMs_.insert(key, nowMs + retryDelayMs);
                        appendDashboardPositionLog(
                            QString("%1 %2@%3 entry delayed (%4): %5 Retrying with smaller size in %6s.")
                                .arg(openSide,
                                     symbol,
                                     interval,
                                     rowConnectorCfg.key,
                                     openOrder.error,
                                     QString::number(retryDelayMs / 1000)));
                    } else {
                        dashboardRuntimeOpenQtyCaps_.remove(key);
                        appendDashboardPositionLog(
                            QString("%1 %2@%3 order failed (%4): %5")
                                .arg(openSide, symbol, interval, rowConnectorCfg.key, openOrder.error));
                    }
                    touchWaitingEntry(key, nowMs);
                    continue;
                }

                openOrderId = openOrder.orderId;
                openOrderInfo = openOrder.error;
                filledQty = (qIsFinite(openOrder.executedQty) && openOrder.executedQty > 0.0)
                    ? openOrder.executedQty
                    : orderQty;
                dashboardRuntimeEntryRetryAfterMs_.remove(key);
                if (!openOrderInfo.trimmed().isEmpty() && isPercentPriceFilterError(openOrderInfo)) {
                    dashboardRuntimeOpenQtyCaps_.insert(key, std::max(filledQty, 0.0));
                } else {
                    dashboardRuntimeOpenQtyCaps_.remove(key);
                }
                entryPrice = (qIsFinite(openOrder.avgPrice) && openOrder.avgPrice > 0.0)
                    ? openOrder.avgPrice
                    : price;
                livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
                const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                livePos = pickLivePosition(liveSnapshot, symbol, openSide);
                if (livePos && qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                    entryPrice = livePos->entryPrice;
                }
            }
            double rowQty = filledQty;
            if ((!qIsFinite(rowQty) || rowQty <= 1e-10)
                && livePos
                && qIsFinite(livePos->positionAmt)
                && std::fabs(livePos->positionAmt) > 1e-10) {
                rowQty = std::fabs(livePos->positionAmt);
            }
            const QString exposureKey = QStringLiteral("%1|%2|%3")
                                            .arg(symbol,
                                                 openSide,
                                                 connectorToken.toLower());
            const double existingGroupQty = runtimeQtyByExposureKey.value(exposureKey, 0.0);
            const double groupQty = existingGroupQty + std::max(0.0, rowQty);
            const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
                ? livePos->markPrice
                : price;
            const double fallbackMarginUsdt = std::max(0.0, (entryPrice * rowQty) / leverage);
            const LivePositionMetricsShare liveShare = allocateLivePositionShare(
                livePos,
                rowQty,
                groupQty,
                std::max(0.0, rowQty * markPrice),
                fallbackMarginUsdt,
                fallbackMarginUsdt,
                0.0);
            const double sizeUsdt = std::max(0.0, liveShare.sizeUsdt);
            const double displayMarginUsdt = std::max(0.0, liveShare.displayMarginUsdt);
            const double roiBasisUsdt = std::max(1e-9, liveShare.roiBasisUsdt);
            const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
            const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
            const QString marginRatioText = marginRatio > 0.0
                ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
                : QStringLiteral("-");
            const QString liqText = liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");

            dashboardRuntimeOpenPositions_.insert(
                key,
                RuntimePosition{
                    openSide,
                    interval,
                    triggerSource,
                    rowConnectorCfg.key,
                    rowConnectorCfg.baseUrl,
                    entryPrice,
                    rowQty,
                    leverage,
                    roiBasisUsdt,
                    displayMarginUsdt,
                });
            runtimeQtyByExposureKey[exposureKey] = groupQty;

            if (positionsTable_) {
                ScopedTableSortingPause sortingPause(positionsTable_);
                const int rowIdx = positionsTable_->rowCount();
                positionsTable_->insertRow(rowIdx);
                positionsTableStructureChanged = true;
                const QString nowText = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
                setTableCellText(positionsTable_, rowIdx, 0, symbol);
                setTableCellText(positionsTable_, rowIdx, 1, formatPositionSizeText(sizeUsdt, rowQty, symbol));
                setTableCellNumeric(positionsTable_, rowIdx, 1, sizeUsdt);
                setTableCellText(positionsTable_, rowIdx, 2, QString::number(markPrice, 'f', 6));
                setTableCellNumeric(positionsTable_, rowIdx, 2, markPrice);
                setTableCellText(positionsTable_, rowIdx, 3, marginRatioText);
                setTableCellNumeric(positionsTable_, rowIdx, 3, marginRatio);
                setTableCellText(positionsTable_, rowIdx, 4, liqText);
                setTableCellNumeric(positionsTable_, rowIdx, 4, liqPrice);
                setTableCellText(positionsTable_, rowIdx, 5, QString::number(displayMarginUsdt, 'f', 2));
                setTableCellNumeric(positionsTable_, rowIdx, 5, displayMarginUsdt);
                setTableCellText(positionsTable_, rowIdx, 6, formatQuantityWithSymbol(rowQty, symbol));
                setTableCellNumeric(positionsTable_, rowIdx, 6, rowQty);
                setTableCellText(positionsTable_, rowIdx, 7, "0.00 (0.00%)");
                setTableCellNumeric(positionsTable_, rowIdx, 7, 0.0);
                if (QTableWidgetItem *pnlItem = positionsTable_->item(rowIdx, 7)) {
                    setTableCellRoiBasis(pnlItem, roiBasisUsdt);
                }
                setTableCellText(positionsTable_, rowIdx, 8, interval);
                setTableCellText(positionsTable_, rowIdx, 9, indicatorDisplayName(triggerSource));
                setTableCellText(positionsTable_, rowIdx, 10, triggerText);
                setTableCellText(positionsTable_, rowIdx, 11, indicatorValueSummary);
                setTableCellText(positionsTable_, rowIdx, 12, openSide);
                setTableCellText(positionsTable_, rowIdx, 13, nowText);
                setTableCellText(positionsTable_, rowIdx, 14, "-");
                setTableCellText(
                    positionsTable_,
                    rowIdx,
                    15,
                    dashboardOverridesTable_->item(row, 7) ? dashboardOverridesTable_->item(row, 7)->text() : QStringLiteral("Disabled"));
                setTableCellText(positionsTable_, rowIdx, 16, "OPEN");
                setTableCellText(positionsTable_, rowIdx, 17, QString("Auto [%1] #%2").arg(rowConnectorCfg.key, openOrderId));
                if (QTableWidgetItem *symbolItem = positionsTable_->item(rowIdx, 0)) {
                    symbolItem->setData(kPositionsRowSequenceRole, positionsRowSequenceCounter_++);
                }
                positionsTableMutated = true;
            }
            applyCumulativeViewImmediately();
            appendDashboardPositionLog(
                QString("%1 %2@%3 opened at %4 qty=%5 (%6, values: %7, connector=%8, orderId=%9%10)")
                    .arg(openSide,
                         symbol,
                         interval,
                         QString::number(entryPrice, 'f', 6),
                         QString::number(rowQty, 'f', 6),
                         triggerText,
                         indicatorValueSummary,
                         rowConnectorCfg.key,
                         openOrderId,
                         openOrderInfo.trimmed().isEmpty() ? QString() : QStringLiteral(", note=%1").arg(openOrderInfo.trimmed())));
            continue;
        }

        RuntimePosition &openPos = openIt.value();
        const QString signalSource = openPos.signalSource.trimmed().toLower();
        const auto shouldCloseBySource = [&](const QString &source, bool isLong) -> bool {
            if (source == QStringLiteral("stoch_rsi")) {
                if (stochRsiOk) {
                    return isLong ? (stochRsi >= stochSellThreshold) : (stochRsi <= stochBuyThreshold);
                }
                if (rsiOk) {
                    return isLong ? (rsi >= rsiSellThreshold) : (rsi <= rsiBuyThreshold);
                }
                return false;
            }
            if (source == QStringLiteral("willr")) {
                if (willrOk) {
                    return isLong ? (willr >= willrSellThreshold) : (willr <= willrBuyThreshold);
                }
                if (rsiOk) {
                    return isLong ? (rsi >= rsiSellThreshold) : (rsi <= rsiBuyThreshold);
                }
                return false;
            }
            if (!rsiOk) {
                return false;
            }
            return isLong ? (rsi >= rsiSellThreshold) : (rsi <= rsiBuyThreshold);
        };
        const bool shouldCloseLong = (openPos.side == "LONG") && shouldCloseBySource(signalSource, true);
        const bool shouldCloseShort = (openPos.side == "SHORT") && shouldCloseBySource(signalSource, false);
        const auto *liveSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
        const auto *livePos = pickLivePosition(liveSnapshot, symbol, openPos.side);
        if ((!qIsFinite(openPos.quantity) || openPos.quantity <= 1e-10)
            && livePos
            && qIsFinite(livePos->positionAmt)
            && std::fabs(livePos->positionAmt) > 1e-10) {
            openPos.quantity = std::fabs(livePos->positionAmt);
            if (qIsFinite(livePos->entryPrice) && livePos->entryPrice > 0.0) {
                openPos.entryPrice = livePos->entryPrice;
            }
        }
        const double rowQty = std::max(0.0, openPos.quantity);
        const QString exposureKey = QStringLiteral("%1|%2|%3")
                                        .arg(symbol,
                                             openPos.side.trimmed().toUpper(),
                                             connectorToken.toLower());
        const double groupQty = runtimeQtyByExposureKey.value(exposureKey, rowQty);
        const double markPrice = (livePos && qIsFinite(livePos->markPrice) && livePos->markPrice > 0.0)
            ? livePos->markPrice
            : price;
        const double fallbackPnlUsdt = (openPos.side == QStringLiteral("LONG"))
            ? (markPrice - openPos.entryPrice) * rowQty
            : (openPos.entryPrice - markPrice) * rowQty;
        const double fallbackMarginUsdt = std::max(
            1e-9,
            (openPos.entryPrice * rowQty) / std::max(1.0, openPos.leverage));
        const LivePositionMetricsShare liveShare = allocateLivePositionShare(
            livePos,
            rowQty,
            groupQty,
            std::max(0.0, rowQty * markPrice),
            std::max(fallbackMarginUsdt, openPos.displayMarginUsdt),
            std::max(fallbackMarginUsdt, openPos.roiBasisUsdt),
            fallbackPnlUsdt);
        openPos.displayMarginUsdt = std::max(1e-9, liveShare.displayMarginUsdt);
        openPos.roiBasisUsdt = std::max(1e-9, liveShare.roiBasisUsdt);
        const double markPnlUsdt = liveShare.pnlUsdt;
        const double markPnlPct = (markPnlUsdt / std::max(1e-9, openPos.roiBasisUsdt)) * 100.0;
        const double sizeUsdt = std::max(0.0, liveShare.sizeUsdt);
        const double liqPrice = (livePos && livePos->liquidationPrice > 0.0) ? livePos->liquidationPrice : 0.0;
        const double marginRatio = (livePos && livePos->marginRatio > 0.0) ? livePos->marginRatio : 0.0;
        const QString marginRatioText = marginRatio > 0.0
            ? QStringLiteral("%1%").arg(QString::number(marginRatio, 'f', 2))
            : QStringLiteral("-");
        const QString liqText = liqPrice > 0.0 ? QString::number(liqPrice, 'f', 6) : QStringLiteral("-");

        int targetRow = -1;
        if (positionsTable_) {
            for (int t = positionsTable_->rowCount() - 1; t >= 0; --t) {
                const QString rowSymbol = tableCellRaw(t, 0).trimmed().toUpper();
                const QString rowInterval = tableCellRaw(t, 8).trimmed();
                const QString rowStatus = tableCellRaw(t, 16).trimmed().toUpper();
                const QString rowConnectorHint = tableCellRaw(t, 17).toLower();
                if (rowSymbol == symbol
                    && rowInterval.compare(interval, Qt::CaseInsensitive) == 0
                    && rowStatus == "OPEN"
                    && rowConnectorHint.contains(rowConnectorCfg.key.toLower())) {
                    targetRow = t;
                    break;
                }
            }
        }

        if (targetRow >= 0 && positionsTable_) {
            ScopedTableSortingPause sortingPause(positionsTable_);
            const bool updateVisibleText = !positionsCumulativeView_;
            auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text, bool preserveWhenUnavailable = false) {
                QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                QString finalText = text;
                if (preserveWhenUnavailable && (text.trimmed().isEmpty() || text.trimmed() == QStringLiteral("-"))) {
                    QString existing;
                    if (item) {
                        const QVariant raw = item->data(Qt::UserRole);
                        existing = raw.isValid() ? raw.toString() : item->text();
                    }
                    existing = existing.trimmed();
                    if (!existing.isEmpty() && existing != QStringLiteral("-")) {
                        finalText = existing;
                    }
                }
                if (!item) {
                    item = new QTableWidgetItem(finalText);
                    positionsTable_->setItem(targetRow, col, item);
                } else if (updateVisibleText) {
                    item->setText(finalText);
                }
                item->setData(Qt::UserRole, finalText);
            };
            setOrCreate(1, formatPositionSizeText(sizeUsdt, rowQty, symbol));
            setOrCreate(2, QString::number(markPrice, 'f', 6));
            setOrCreate(3, marginRatioText, true);
            setOrCreate(4, liqText, true);
            setOrCreate(5, QString::number(openPos.displayMarginUsdt, 'f', 2));
            setOrCreate(6, formatQuantityWithSymbol(rowQty, symbol));
            setOrCreate(7, QString("%1 (%2%)")
                            .arg(QString::number(markPnlUsdt, 'f', 2),
                                 QString::number(markPnlPct, 'f', 2)));
            setTableCellNumeric(positionsTable_, targetRow, 1, sizeUsdt);
            setTableCellNumeric(positionsTable_, targetRow, 2, markPrice);
            setTableCellNumeric(positionsTable_, targetRow, 3, marginRatio);
            setTableCellNumeric(positionsTable_, targetRow, 4, liqPrice);
            setTableCellNumeric(positionsTable_, targetRow, 5, openPos.displayMarginUsdt);
            setTableCellNumeric(positionsTable_, targetRow, 6, rowQty);
            setTableCellNumeric(positionsTable_, targetRow, 7, markPnlUsdt);
            if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                setTableCellRoiBasis(pnlItem, openPos.roiBasisUsdt);
            }
            setOrCreate(11, indicatorValueSummary);
            positionsTableMutated = true;
        }

        if (!shouldCloseLong && !shouldCloseShort) {
            continue;
        }

        if (!futures || (!paperTrading && !hasApiCredentials)) {
            appendDashboardPositionLog(
                QString("%1 %2@%3 close signal deferred: %4.")
                    .arg(openPos.side,
                         symbol,
                         interval,
                         !futures ? QStringLiteral("Futures mode is required")
                                  : QStringLiteral("missing API credentials")));
            continue;
        }

        const QString closeOrderSide = (openPos.side == QStringLiteral("LONG")) ? QStringLiteral("SELL")
                                                                                 : QStringLiteral("BUY");
        const QString closePositionSide = hedgeMode ? openPos.side : QString();
        const bool closeReduceOnly = !hedgeMode;
        QString closeOrderId;
        QString closeOrderError;
        double closePrice = price;
        double closeQty = openPos.quantity;
        if (paperTrading) {
            closeOrderId = QStringLiteral("paper-close-%1").arg(QDateTime::currentMSecsSinceEpoch());
        } else {
            const auto closeOrder = placeFuturesCloseOrderWithFallback(
                apiKey,
                apiSecret,
                symbol,
                closeOrderSide,
                openPos.quantity,
                isTestnet,
                closeReduceOnly,
                closePositionSide,
                10000,
                rowConnectorCfg.baseUrl,
                price);
            if (!closeOrder.ok) {
                if (isReduceOnlyRejectedError(closeOrder.error)) {
                    livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
                    const auto *latestSnapshot = fetchLivePositionsForConnector(rowConnectorCfg);
                    if (!hasMatchingOpenFuturesPosition(latestSnapshot, symbol, openPos.side, hedgeMode)) {
                        if (targetRow >= 0 && positionsTable_) {
                            ScopedTableSortingPause sortingPause(positionsTable_);
                            const bool updateVisibleText = !positionsCumulativeView_;
                            auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text) {
                                QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                                if (!item) {
                                    item = new QTableWidgetItem(text);
                                    positionsTable_->setItem(targetRow, col, item);
                                } else if (updateVisibleText) {
                                    item->setText(text);
                                }
                                item->setData(Qt::UserRole, text);
                            };
                            setOrCreate(14, QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
                            setOrCreate(16, "CLOSED");
                            positionsTableMutated = true;
                        }
                        applyCumulativeViewImmediately();
                        appendDashboardPositionLog(
                            QString("%1 %2@%3 close confirmed (%4): position is already flat on exchange.")
                                .arg(openPos.side, symbol, interval, rowConnectorCfg.key));
                        dashboardRuntimeLastEvalMs_.remove(key);
                        dashboardRuntimeEntryRetryAfterMs_.remove(key);
                        dashboardRuntimeOpenQtyCaps_.remove(key);
                        dashboardRuntimeOpenPositions_.remove(key);
                        continue;
                    }
                }
                appendDashboardPositionLog(
                    QString("%1 %2@%3 close order failed (%4): %5")
                        .arg(openPos.side, symbol, interval, rowConnectorCfg.key, closeOrder.error));
                continue;
            }
            livePositionsCache.remove(connectorCacheKeyFor(rowConnectorCfg));
            closeOrderId = closeOrder.orderId;
            closeOrderError = closeOrder.error;
            closePrice = (qIsFinite(closeOrder.avgPrice) && closeOrder.avgPrice > 0.0)
                ? closeOrder.avgPrice
                : price;
            closeQty = (qIsFinite(closeOrder.executedQty) && closeOrder.executedQty > 0.0)
                ? closeOrder.executedQty
                : openPos.quantity;
        }
        const double effectiveCloseQty = std::max(0.0, std::min(openPos.quantity, closeQty));
        if (effectiveCloseQty <= 0.0) {
            appendDashboardPositionLog(
                QString("%1 %2@%3 close order returned zero fill; keeping position open.")
                    .arg(openPos.side, symbol, interval));
            continue;
        }
        const double realizedPnlUsdt = (openPos.side == "LONG")
            ? (closePrice - openPos.entryPrice) * effectiveCloseQty
            : (openPos.entryPrice - closePrice) * effectiveCloseQty;
        const double closeShareRatio = rowQty > 1e-9
            ? std::min(1.0, std::max(0.0, effectiveCloseQty / rowQty))
            : 1.0;
        const double closeRoiBasisUsed = std::max(1e-9, openPos.roiBasisUsdt * closeShareRatio);
        const double realizedPnlPct = (realizedPnlUsdt / closeRoiBasisUsed) * 100.0;
        const bool partialClose = (effectiveCloseQty + 1e-9) < openPos.quantity;

        if (targetRow >= 0 && positionsTable_) {
            ScopedTableSortingPause sortingPause(positionsTable_);
            const bool updateVisibleText = !positionsCumulativeView_;
            auto setOrCreate = [this, targetRow, updateVisibleText](int col, const QString &text) {
                QTableWidgetItem *item = positionsTable_->item(targetRow, col);
                if (!item) {
                    item = new QTableWidgetItem(text);
                    positionsTable_->setItem(targetRow, col, item);
                } else if (updateVisibleText) {
                    item->setText(text);
                }
                item->setData(Qt::UserRole, text);
            };
            setOrCreate(2, QString::number(closePrice, 'f', 6));
            setOrCreate(7, QString("%1 (%2%)")
                            .arg(QString::number(realizedPnlUsdt, 'f', 2),
                                 QString::number(realizedPnlPct, 'f', 2)));
            setTableCellNumeric(positionsTable_, targetRow, 2, closePrice);
            setTableCellNumeric(positionsTable_, targetRow, 7, realizedPnlUsdt);
            if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                setTableCellRoiBasis(pnlItem, closeRoiBasisUsed);
            }
            if (partialClose) {
                const double remainingQty = std::max(0.0, openPos.quantity - effectiveCloseQty);
                const double remainingRatio = rowQty > 1e-9
                    ? std::min(1.0, std::max(0.0, remainingQty / rowQty))
                    : 0.0;
                const double remainingNotional = std::max(0.0, remainingQty * closePrice);
                const double remainingDisplayMarginUsdt = std::max(0.0, openPos.displayMarginUsdt * remainingRatio);
                const double remainingRoiBasisUsdt = std::max(0.0, openPos.roiBasisUsdt * remainingRatio);
                openPos.displayMarginUsdt = std::max(1e-9, remainingDisplayMarginUsdt);
                openPos.roiBasisUsdt = std::max(1e-9, remainingRoiBasisUsdt);
                setOrCreate(1, formatPositionSizeText(remainingNotional, remainingQty, symbol));
                setOrCreate(5, QString::number(remainingDisplayMarginUsdt, 'f', 2));
                setOrCreate(6, formatQuantityWithSymbol(remainingQty, symbol));
                setTableCellNumeric(positionsTable_, targetRow, 1, remainingNotional);
                setTableCellNumeric(positionsTable_, targetRow, 5, remainingDisplayMarginUsdt);
                setTableCellNumeric(positionsTable_, targetRow, 6, remainingQty);
                if (QTableWidgetItem *pnlItem = positionsTable_->item(targetRow, 7)) {
                    setTableCellRoiBasis(pnlItem, remainingRoiBasisUsdt);
                }
            } else {
                setOrCreate(14, QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss"));
                setOrCreate(16, "CLOSED");
            }
            positionsTableMutated = true;
        }
        applyCumulativeViewImmediately();

        if (partialClose) {
            openPos.quantity = std::max(0.0, openPos.quantity - effectiveCloseQty);
            if (openPos.quantity <= 1e-9) {
                openPos.quantity = 0.0;
            }
            appendDashboardPositionLog(
                QString("%1 %2@%3 partially closed at %4, qty=%5 remaining=%6, PNL=%7 USDT (%8%%), connector=%9, orderId=%10: %11")
                    .arg(openPos.side,
                         symbol,
                         interval,
                         QString::number(closePrice, 'f', 6),
                         QString::number(effectiveCloseQty, 'f', 6),
                         QString::number(openPos.quantity, 'f', 6),
                         QString::number(realizedPnlUsdt, 'f', 2),
                         QString::number(realizedPnlPct, 'f', 2),
                         rowConnectorCfg.key,
                         closeOrderId,
                         closeOrderError.isEmpty() ? QStringLiteral("remaining exposure still open")
                                                   : closeOrderError));
            continue;
        }

        appendDashboardPositionLog(
            QString("%1 %2@%3 closed at %4, PNL=%5 USDT (%6%%), connector=%7, orderId=%8")
                .arg(openPos.side,
                     symbol,
                     interval,
                     QString::number(closePrice, 'f', 6),
                     QString::number(realizedPnlUsdt, 'f', 2),
                     QString::number(realizedPnlPct, 'f', 2),
                     rowConnectorCfg.key,
                     closeOrderId));
        dashboardRuntimeLastEvalMs_.remove(key);
        dashboardRuntimeEntryRetryAfterMs_.remove(key);
        dashboardRuntimeOpenQtyCaps_.remove(key);
        dashboardRuntimeOpenPositions_.remove(key);
    }

    if (!dashboardWaitingActiveEntries_.isEmpty()) {
        const QList<QString> activeKeys = dashboardWaitingActiveEntries_.keys();
        for (const QString &activeKey : activeKeys) {
            if (waitingSeenThisCycle.contains(activeKey)) {
                continue;
            }
            QVariantMap endedEntry = dashboardWaitingActiveEntries_.take(activeKey);
            qint64 firstSeenMs = endedEntry.value(QStringLiteral("first_seen_ms")).toLongLong();
            if (firstSeenMs <= 0) {
                firstSeenMs = cycleNowMs;
            }
            const qint64 elapsedMs = std::max<qint64>(0, cycleNowMs - firstSeenMs);
            endedEntry.insert(QStringLiteral("first_seen_ms"), firstSeenMs);
            endedEntry.insert(QStringLiteral("updated_ms"), cycleNowMs);
            endedEntry.insert(QStringLiteral("ended_at_ms"), cycleNowMs);
            endedEntry.insert(QStringLiteral("age"), static_cast<double>(elapsedMs) / 1000.0);
            endedEntry.insert(QStringLiteral("age_seconds"), static_cast<int>(elapsedMs / 1000));
            endedEntry.insert(QStringLiteral("state"), QStringLiteral("Ended"));
            dashboardWaitingHistoryEntries_.append(endedEntry);
        }
    }
    if (dashboardWaitingHistoryEntries_.size() > dashboardWaitingHistoryMax_) {
        const int extra = dashboardWaitingHistoryEntries_.size() - dashboardWaitingHistoryMax_;
        dashboardWaitingHistoryEntries_.erase(
            dashboardWaitingHistoryEntries_.begin(),
            dashboardWaitingHistoryEntries_.begin() + extra);
    }
    refreshDashboardWaitingQueueTable();

    flushPendingPositionsView();
    refreshPositionsSummaryLabels();
}

