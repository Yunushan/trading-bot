#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "TradingBotWindow.dashboard_runtime_shared.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QColor>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QGridLayout>
#include <QGroupBox>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMap>
#include <QPushButton>
#include <QScrollArea>
#include <QSet>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardItemModel>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTabWidget>
#include <QTextEdit>
#include <QVariant>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>

namespace {
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

} // namespace

void TradingBotWindow::registerDashboardRuntimeLockWidget(QWidget *widget) {
    if (!widget) {
        return;
    }
    if (!dashboardRuntimeLockWidgets_.contains(widget)) {
        dashboardRuntimeLockWidgets_.append(widget);
    }
}

void TradingBotWindow::createDashboardAccountStatusSection(QWidget *page, QVBoxLayout *root) {
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
    registerDashboardRuntimeLockWidget(dashboardApiKey_);
    addPair(0, col, "API Key:", dashboardApiKey_, 2);

    dashboardModeCombo_ = new QComboBox(accountBox);
    dashboardModeCombo_->addItems({"Live", "Paper Local", "Demo/Testnet"});
    dashboardModeCombo_->setToolTip(
        "Live: real Binance Futures orders.\n"
        "Paper Local: live market data with app-local paper positions.\n"
        "Demo/Testnet: Binance Futures Testnet orders and positions.");
    registerDashboardRuntimeLockWidget(dashboardModeCombo_);
    addPair(0, col, "Mode:", dashboardModeCombo_);

    dashboardThemeCombo_ = new QComboBox(accountBox);
    dashboardThemeCombo_->addItems({"Light", "Dark", "Blue", "Yellow", "Green", "Red"});
    dashboardThemeCombo_->setCurrentText("Dark");
    registerDashboardRuntimeLockWidget(dashboardThemeCombo_);
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
    registerDashboardRuntimeLockWidget(dashboardApiSecret_);
    addPair(1, col, "API Secret Key:", dashboardApiSecret_, 2);

    dashboardAccountTypeCombo_ = new QComboBox(accountBox);
    dashboardAccountTypeCombo_->addItems({"Futures", "Spot"});
    registerDashboardRuntimeLockWidget(dashboardAccountTypeCombo_);
    addPair(1, col, "Account Type:", dashboardAccountTypeCombo_);

    auto *accountModeCombo = new QComboBox(accountBox);
    accountModeCombo->addItems({"Classic Trading", "Multi-Asset Mode"});
    registerDashboardRuntimeLockWidget(accountModeCombo);
    addPair(1, col, "Account Mode:", accountModeCombo);

    auto *connectorCombo = new QComboBox(accountBox);
    TradingBotWindowSupport::rebuildConnectorComboForAccount(connectorCombo, true, true);
    connectorCombo->setToolTip(
        "Matches Python connector options.\n"
        "C++ currently runs native Binance REST under the hood.\n"
        "Unsupported connector backends are auto-mapped to native equivalents.");
    connectorCombo->setMinimumWidth(340);
    dashboardConnectorCombo_ = connectorCombo;
    registerDashboardRuntimeLockWidget(connectorCombo);
    addPair(1, col, "Connector:", connectorCombo, 3);
    if (dashboardAccountTypeCombo_) {
        connect(dashboardAccountTypeCombo_, &QComboBox::currentTextChanged, this, [this](const QString &accountText) {
            const bool isFutures = accountText.trimmed().toLower().startsWith(QStringLiteral("fut"));
            TradingBotWindowSupport::rebuildConnectorComboForAccount(dashboardConnectorCombo_, isFutures, false);
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
    registerDashboardRuntimeLockWidget(dashboardRefreshBtn_);
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
    registerDashboardRuntimeLockWidget(paperBalanceSpin);
    connect(paperBalanceSpin, &QDoubleSpinBox::valueChanged, this, [this](double) {
        if (dashboardModeCombo_ && TradingBotWindowSupport::isPaperTradingModeLabel(dashboardModeCombo_->currentText())) {
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
    registerDashboardRuntimeLockWidget(leverageSpin);
    addPair(2, col, "Leverage (Futures):", leverageSpin);

    auto *marginModeCombo = new QComboBox(accountBox);
    marginModeCombo->addItems({"Isolated", "Cross"});
    dashboardMarginModeCombo_ = marginModeCombo;
    registerDashboardRuntimeLockWidget(marginModeCombo);
    addPair(2, col, "Margin Mode (Futures):", marginModeCombo);

    auto *positionModeCombo = new QComboBox(accountBox);
    positionModeCombo->addItems({"Hedge", "One-way"});
    dashboardPositionModeCombo_ = positionModeCombo;
    registerDashboardRuntimeLockWidget(positionModeCombo);
    addPair(2, col, "Position Mode:", positionModeCombo);

    auto *assetsModeCombo = new QComboBox(accountBox);
    assetsModeCombo->addItems({"Single-Asset Mode", "Multi-Asset Mode"});
    registerDashboardRuntimeLockWidget(assetsModeCombo);
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
    registerDashboardRuntimeLockWidget(indicatorSourceCombo);
    addPair(3, col, "Indicator Source:", indicatorSourceCombo, 2);

    auto *signalFeedCombo = new QComboBox(accountBox);
    signalFeedCombo->addItem("REST Poll");
    signalFeedCombo->addItem("WebSocket Stream");
    signalFeedCombo->setCurrentText("REST Poll");
    signalFeedCombo->setToolTip(
        "Choose how the dashboard runtime gets signal candles.\n"
        "REST Poll: scheduled REST requests.\n"
        "WebSocket Stream: stream-driven Binance kline updates with local candle cache.");
    if (!TradingBotWindowDashboardRuntime::qtWebSocketsRuntimeAvailable()) {
        if (auto *model = qobject_cast<QStandardItemModel *>(signalFeedCombo->model())) {
            if (QStandardItem *item = model->item(1)) {
                item->setEnabled(false);
            }
        }
        signalFeedCombo->setToolTip(signalFeedCombo->toolTip() + QStringLiteral("\nQt WebSockets runtime is not available in this build."));
    }
    dashboardSignalFeedCombo_ = signalFeedCombo;
    registerDashboardRuntimeLockWidget(signalFeedCombo);
    addPair(3, col, "Signal Feed:", signalFeedCombo);

    auto *orderTypeCombo = new QComboBox(accountBox);
    orderTypeCombo->addItems({"GTC", "IOC", "FOK"});
    registerDashboardRuntimeLockWidget(orderTypeCombo);
    addPair(3, col, "Order Type:", orderTypeCombo);

    auto *expiryCombo = new QComboBox(accountBox);
    expiryCombo->addItems({"30 min (GTD)", "1h (GTD)", "4h (GTD)", "GTC"});
    registerDashboardRuntimeLockWidget(expiryCombo);
    addPair(3, col, "Expiry / TIF:", expiryCombo);

    for (int stretchCol : {1, 2, 4, 6, 8, 10, 12}) {
        accountGrid->setColumnStretch(stretchCol, 1);
    }
    accountGrid->setColumnStretch(13, 2);
    syncDashboardPaperBalanceUi();
}

void TradingBotWindow::createDashboardExchangeAndMarketsSections(QWidget *page, QVBoxLayout *root) {
    auto *exchangeBox = new QGroupBox("Exchange", page);
    auto *exchangeLayout = new QVBoxLayout(exchangeBox);
    exchangeLayout->setSpacing(6);
    exchangeLayout->setContentsMargins(12, 10, 12, 10);
    exchangeLayout->addWidget(new QLabel("Select exchange", exchangeBox));
    auto *exchangeCombo = new QComboBox(exchangeBox);
    dashboardExchangeCombo_ = exchangeCombo;
    registerDashboardRuntimeLockWidget(exchangeCombo);
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
    registerDashboardRuntimeLockWidget(dashboardSymbolList);
    listsGrid->addWidget(dashboardSymbolList, 1, 0, 2, 1);

    auto *dashboardIntervalList = new QListWidget(marketsBox);
    dashboardIntervalList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardIntervalList->addItems({
        "1m", "3m", "5m", "10m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h"
    });
    dashboardIntervalList->setMinimumHeight(220);
    dashboardIntervalList->setMaximumHeight(260);
    dashboardIntervalList_ = dashboardIntervalList;
    registerDashboardRuntimeLockWidget(dashboardIntervalList);
    listsGrid->addWidget(dashboardIntervalList, 1, 1, 2, 1);

    dashboardRefreshSymbolsBtn_ = new QPushButton("Refresh Symbols", marketsBox);
    registerDashboardRuntimeLockWidget(dashboardRefreshSymbolsBtn_);
    connect(dashboardRefreshSymbolsBtn_, &QPushButton::clicked, this, &TradingBotWindow::refreshDashboardSymbols);
    listsGrid->addWidget(dashboardRefreshSymbolsBtn_, 3, 0, 1, 1);

    auto *customIntervalEdit = new QLineEdit(marketsBox);
    customIntervalEdit->setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated");
    registerDashboardRuntimeLockWidget(customIntervalEdit);
    listsGrid->addWidget(customIntervalEdit, 3, 1, 1, 1);
    auto *customButton = new QPushButton("Add Custom Interval(s)", marketsBox);
    registerDashboardRuntimeLockWidget(customButton);
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
        connect(dashboardExchangeCombo_, &QComboBox::currentTextChanged, this, [syncIndicatorSourceFromExchange, this](const QString &text) {
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
}

void TradingBotWindow::createDashboardStrategySection(QWidget *page, QVBoxLayout *root) {

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
    dashboardSideCombo_ = sideCombo;
    registerDashboardRuntimeLockWidget(sideCombo);
    strategyGrid->addWidget(sideCombo, row, 1);

    strategyGrid->addWidget(new QLabel("Position % of Balance:", strategyBox), row, 2);
    auto *positionPct = new QDoubleSpinBox(strategyBox);
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setValue(2.0);
    positionPct->setSuffix(" %");
    dashboardPositionPctSpin_ = positionPct;
    registerDashboardRuntimeLockWidget(positionPct);
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
    dashboardLoopOverrideCombo_ = loopOverride;
    registerDashboardRuntimeLockWidget(loopOverride);
    strategyGrid->addWidget(loopOverride, row, 5);

    ++row;
    auto *enableLeadTrader = new QCheckBox("Enable Lead Trader", strategyBox);
    dashboardLeadTraderEnableCheck_ = enableLeadTrader;
    registerDashboardRuntimeLockWidget(enableLeadTrader);
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
    dashboardLiveIndicatorValuesCheck_ = liveIndicatorValuesCheck;
    registerDashboardRuntimeLockWidget(liveIndicatorValuesCheck);
    strategyGrid->addWidget(liveIndicatorValuesCheck, row, 0, 1, 6);

    ++row;
    auto *oneWayCheck = new QCheckBox("Add-only in current net direction (one-way)", strategyBox);
    dashboardOneWayCheck_ = oneWayCheck;
    registerDashboardRuntimeLockWidget(oneWayCheck);
    strategyGrid->addWidget(oneWayCheck, row, 0, 1, 6);

    ++row;
    auto *hedgeStackCheck = new QCheckBox("Allow simultaneous long & short positions (hedge stacking)", strategyBox);
    hedgeStackCheck->setChecked(true);
    dashboardHedgeStackCheck_ = hedgeStackCheck;
    registerDashboardRuntimeLockWidget(hedgeStackCheck);
    strategyGrid->addWidget(hedgeStackCheck, row, 0, 1, 6);

    ++row;
    auto *stopWithoutCloseCheck = new QCheckBox("Stop Bot Without Closing Active Positions", strategyBox);
    stopWithoutCloseCheck->setToolTip(
        "When checked, the Stop button will halt strategy threads but keep existing positions open."
    );
    dashboardStopWithoutCloseCheck_ = stopWithoutCloseCheck;
    registerDashboardRuntimeLockWidget(stopWithoutCloseCheck);
    strategyGrid->addWidget(stopWithoutCloseCheck, row, 0, 1, 6);

    ++row;
    auto *windowCloseCheck = new QCheckBox("Market Close All Active Positions On Window Close (Working in progress)", strategyBox);
    windowCloseCheck->setEnabled(false);
    strategyGrid->addWidget(windowCloseCheck, row, 0, 1, 6);

    ++row;
    strategyGrid->addWidget(new QLabel("Stop Loss:", strategyBox), row, 0);
    auto *stopLossEnable = new QCheckBox("Enable", strategyBox);
    dashboardStopLossEnableCheck_ = stopLossEnable;
    registerDashboardRuntimeLockWidget(stopLossEnable);
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
    registerDashboardRuntimeLockWidget(templateCombo);
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
        registerDashboardRuntimeLockWidget(cb);
        registerDashboardRuntimeLockWidget(btn);
        btn->setMinimumWidth(150);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        QObject::connect(cb, &QCheckBox::toggled, btn, &QWidget::setEnabled);
        QObject::connect(btn, &QPushButton::clicked, this, [this, name]() { showIndicatorDialog(name); });
        const QString indicatorKey = TradingBotWindowDashboardRuntime::normalizedIndicatorKey(name);
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

    const QStringList indicators = {
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
}

void TradingBotWindow::createDashboardRuntimeSection(QWidget *page, QVBoxLayout *root) {

    auto *overridesBox = new QGroupBox("Symbol / Interval Overrides", page);
    auto *overridesLayout = new QVBoxLayout(overridesBox);
    overridesLayout->setContentsMargins(10, 10, 10, 10);
    overridesLayout->setSpacing(8);

    auto *overridesTable = new QTableWidget(overridesBox);
    registerDashboardRuntimeLockWidget(overridesTable);
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
    registerDashboardRuntimeLockWidget(addSelectedOverrideBtn);
    registerDashboardRuntimeLockWidget(removeSelectedOverrideBtn);
    registerDashboardRuntimeLockWidget(clearOverridesBtn);
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
    registerDashboardRuntimeLockWidget(dashSaveBtn);
    registerDashboardRuntimeLockWidget(dashLoadBtn);
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

    dashboardAddSelectedOverrideBtn_ = addSelectedOverrideBtn;
    dashboardRemoveSelectedOverrideBtn_ = removeSelectedOverrideBtn;
    dashboardClearOverridesBtn_ = clearOverridesBtn;
    dashboardStartBtn_ = dashStartBtn;
    dashboardStopBtn_ = dashStopBtn;
    dashboardSaveConfigBtn_ = dashSaveBtn;
    dashboardLoadConfigBtn_ = dashLoadBtn;
    dashboardOverridesTable_ = overridesTable;
    dashboardAllLogsEdit_ = allLogsEdit;
    dashboardPositionLogsEdit_ = positionLogsEdit;
    dashboardWaitingLogsEdit_ = nullptr;
    dashboardWaitingQueueTable_ = waitingQueueTable;
    refreshDashboardWaitingQueueTable();
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
    dashboardThemeCombo_ = nullptr;
    dashboardAccountTypeCombo_ = nullptr;
    dashboardModeCombo_ = nullptr;
    dashboardConnectorCombo_ = nullptr;
    dashboardExchangeCombo_ = nullptr;
    dashboardIndicatorSourceCombo_ = nullptr;
    dashboardSignalFeedCombo_ = nullptr;
    dashboardTemplateCombo_ = nullptr;
    dashboardMarginModeCombo_ = nullptr;
    dashboardPositionModeCombo_ = nullptr;
    dashboardSideCombo_ = nullptr;
    dashboardLoopOverrideCombo_ = nullptr;
    dashboardPaperBalanceTitleLabel_ = nullptr;
    dashboardPositionPctSpin_ = nullptr;
    dashboardLeverageSpin_ = nullptr;
    dashboardSymbolList_ = nullptr;
    dashboardIntervalList_ = nullptr;
    dashboardRefreshSymbolsBtn_ = nullptr;
    dashboardAddSelectedOverrideBtn_ = nullptr;
    dashboardRemoveSelectedOverrideBtn_ = nullptr;
    dashboardClearOverridesBtn_ = nullptr;
    dashboardStartBtn_ = nullptr;
    dashboardStopBtn_ = nullptr;
    dashboardSaveConfigBtn_ = nullptr;
    dashboardLoadConfigBtn_ = nullptr;
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
    TradingBotWindowDashboardRuntime::clearRuntimeSignalSockets(dashboardRuntimeSignalSockets_);
    dashboardRuntimeSignalCandles_.clear();
    dashboardRuntimeSignalLastClosed_.clear();
    dashboardRuntimeSignalUpdateMs_.clear();
    dashboardRuntimeLockWidgets_.clear();
    dashboardLeadTraderEnableCheck_ = nullptr;
    dashboardLeadTraderCombo_ = nullptr;
    dashboardStopWithoutCloseCheck_ = nullptr;
    dashboardLiveIndicatorValuesCheck_ = nullptr;
    dashboardOneWayCheck_ = nullptr;
    dashboardHedgeStackCheck_ = nullptr;
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

    createDashboardAccountStatusSection(page, root);
    createDashboardExchangeAndMarketsSections(page, root);
    createDashboardStrategySection(page, root);
    createDashboardRuntimeSection(page, root);

    if (dashboardAddSelectedOverrideBtn_) {
        connect(dashboardAddSelectedOverrideBtn_, &QPushButton::clicked, this, &TradingBotWindow::addSelectedDashboardOverrideRows);
    }
    if (dashboardRemoveSelectedOverrideBtn_) {
        connect(
            dashboardRemoveSelectedOverrideBtn_,
            &QPushButton::clicked,
            this,
            &TradingBotWindow::removeSelectedDashboardOverrideRows);
    }
    if (dashboardClearOverridesBtn_) {
        connect(dashboardClearOverridesBtn_, &QPushButton::clicked, this, &TradingBotWindow::clearDashboardOverrideRows);
    }

    if (dashboardStartBtn_) {
        connect(dashboardStartBtn_, &QPushButton::clicked, this, &TradingBotWindow::startDashboardRuntime);
    }
    if (dashboardStopBtn_) {
        connect(dashboardStopBtn_, &QPushButton::clicked, this, &TradingBotWindow::stopDashboardRuntime);
    }
    if (dashboardSaveConfigBtn_) {
        connect(dashboardSaveConfigBtn_, &QPushButton::clicked, this, &TradingBotWindow::saveDashboardConfig);
    }
    if (dashboardLoadConfigBtn_) {
        connect(dashboardLoadConfigBtn_, &QPushButton::clicked, this, &TradingBotWindow::loadDashboardConfig);
    }

    appendDashboardAllLog(QStringLiteral("Dashboard overrides and log sections are ready."));

    root->addStretch();

    setDashboardRuntimeControlsEnabled(true);
    applyDashboardTheme(dashboardThemeCombo_ ? dashboardThemeCombo_->currentText() : QString());
    return page;
}
