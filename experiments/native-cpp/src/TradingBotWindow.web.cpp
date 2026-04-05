#include "TradingBotWindow.h"

#include <QDesktopServices>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTabWidget>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>
#include <QVector>

#if HAS_QT_WEBENGINE
#include <QWebEngineView>
#endif

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
