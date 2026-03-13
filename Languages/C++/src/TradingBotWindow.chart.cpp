#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "BinanceRestClient.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QComboBox>
#include <QDesktopServices>
#include <QFontMetrics>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPaintEvent>
#include <QPainter>
#include <QPushButton>
#include <QResizeEvent>
#include <QShowEvent>
#include <QSignalBlocker>
#include <QSizePolicy>
#include <QStackedWidget>
#include <QStandardItemModel>
#include <QTabWidget>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>
#include <QtMath>
#if HAS_QT_WEBENGINE
#include <QWebEngineView>
#endif

#include <algorithm>
#include <cmath>
#include <functional>

namespace {
using ConnectorRuntimeConfig = TradingBotWindowSupport::ConnectorRuntimeConfig;

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

} // namespace

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
        const bool isTestnet = dashboardModeCombo_ ? TradingBotWindowSupport::isTestnetModeLabel(dashboardModeCombo_->currentText()) : false;
        const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
        const ConnectorRuntimeConfig connectorCfg = TradingBotWindowSupport::resolveConnectorConfig(connectorText, futures);

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
        const bool isTestnet = dashboardModeCombo_ ? TradingBotWindowSupport::isTestnetModeLabel(dashboardModeCombo_->currentText()) : false;
        const QString connectorText = dashboardConnectorCombo_ ? dashboardConnectorCombo_->currentText() : QString();
        const ConnectorRuntimeConfig connectorCfg = TradingBotWindowSupport::resolveConnectorConfig(connectorText, futures);
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
