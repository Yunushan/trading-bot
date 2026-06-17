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
#include <QGraphicsOpacityEffect>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMap>
#include <QMessageBox>
#include <QPushButton>
#include <QScrollArea>
#include <QSet>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardItemModel>
#include <QStringList>
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        dashboardModeCombo_,
        TradingBotWindowSupport::pythonSourceConfigModeOptionKeys(),
        TradingBotWindowSupport::pythonSourceConfigModeOptionLabels(),
        {},
        QStringLiteral("Demo"));
    dashboardModeCombo_->setToolTip(
        "Live: real Binance Futures orders.\n"
        "Demo: compatibility mode for the configured test environment.\n"
        "Testnet: Binance Futures Testnet orders and positions.");
    registerDashboardRuntimeLockWidget(dashboardModeCombo_);
    addPair(0, col, "Mode:", dashboardModeCombo_);

    dashboardThemeCombo_ = new QComboBox(accountBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        dashboardThemeCombo_,
        TradingBotWindowSupport::pythonSourceThemeOptionKeys(),
        TradingBotWindowSupport::pythonSourceThemeOptionLabels(),
        {},
        QStringLiteral("Dark"));
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        dashboardAccountTypeCombo_,
        TradingBotWindowSupport::pythonSourceAccountTypeOptionKeys(),
        TradingBotWindowSupport::pythonSourceAccountTypeOptionLabels(),
        {},
        QStringLiteral("Futures"));
    registerDashboardRuntimeLockWidget(dashboardAccountTypeCombo_);
    addPair(1, col, "Account Type:", dashboardAccountTypeCombo_);

    auto *accountModeCombo = new QComboBox(accountBox);
    accountModeCombo->addItems(TradingBotWindowSupport::pythonSourceAccountModeOptions());
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
    leverageSpin->setRange(1, 150);
    leverageSpin->setValue(1);
    dashboardLeverageSpin_ = leverageSpin;
    registerDashboardRuntimeLockWidget(leverageSpin);
    addPair(2, col, "Leverage (Futures):", leverageSpin);

    auto *marginModeCombo = new QComboBox(accountBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        marginModeCombo,
        TradingBotWindowSupport::pythonSourceMarginModeOptionKeys(),
        TradingBotWindowSupport::pythonSourceMarginModeOptionLabels(),
        {},
        QStringLiteral("Isolated"));
    dashboardMarginModeCombo_ = marginModeCombo;
    registerDashboardRuntimeLockWidget(marginModeCombo);
    addPair(2, col, "Margin Mode (Futures):", marginModeCombo);

    auto *positionModeCombo = new QComboBox(accountBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        positionModeCombo,
        TradingBotWindowSupport::pythonSourcePositionModeOptionKeys(),
        TradingBotWindowSupport::pythonSourcePositionModeOptionLabels(),
        {},
        QStringLiteral("Hedge"));
    dashboardPositionModeCombo_ = positionModeCombo;
    registerDashboardRuntimeLockWidget(positionModeCombo);
    addPair(2, col, "Position Mode:", positionModeCombo);

    auto *assetsModeCombo = new QComboBox(accountBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        assetsModeCombo,
        TradingBotWindowSupport::pythonSourceAssetsModeOptionKeys(),
        TradingBotWindowSupport::pythonSourceAssetsModeOptionLabels());
    registerDashboardRuntimeLockWidget(assetsModeCombo);
    addPair(2, col, "Assets Mode:", assetsModeCombo);

    col = 0;
    auto *indicatorSourceCombo = new QComboBox(accountBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        indicatorSourceCombo,
        TradingBotWindowSupport::pythonSourceIndicatorSourceOptionKeys(),
        TradingBotWindowSupport::pythonSourceIndicatorSourceOptionLabels(),
        {},
        QStringLiteral("Binance futures"));
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

    auto *tifCombo = new QComboBox(accountBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        tifCombo,
        TradingBotWindowSupport::pythonSourceTimeInForceOptionKeys(),
        TradingBotWindowSupport::pythonSourceTimeInForceOptionLabels(),
        {},
        QStringLiteral("GTC"));
    registerDashboardRuntimeLockWidget(tifCombo);
    addPair(3, col, "Time-in-Force:", tifCombo);

    auto *gtdMinutesSpin = new QSpinBox(accountBox);
    gtdMinutesSpin->setRange(1, 1440);
    gtdMinutesSpin->setValue(30);
    gtdMinutesSpin->setSuffix(" min (GTD)");
    gtdMinutesSpin->setEnabled(false);
    registerDashboardRuntimeLockWidget(gtdMinutesSpin);
    connect(tifCombo, &QComboBox::currentTextChanged, this, [gtdMinutesSpin](const QString &text) {
        gtdMinutesSpin->setEnabled(text.trimmed() == QStringLiteral("GTD"));
    });
    addPair(3, col, "GTD minutes:", gtdMinutesSpin);

    for (int stretchCol : {1, 2, 4, 6, 8, 10, 12}) {
        accountGrid->setColumnStretch(stretchCol, 1);
    }
    accountGrid->setColumnStretch(13, 2);
    syncDashboardPaperBalanceUi();
}

void TradingBotWindow::createDashboardLlmSection(QWidget *page, QVBoxLayout *root) {
    auto *llmBox = new QGroupBox("AI / LLM Settings (C++ GUI)", page);
    auto *llmGrid = new QGridLayout(llmBox);
    llmGrid->setHorizontalSpacing(10);
    llmGrid->setVerticalSpacing(8);
    llmGrid->setContentsMargins(12, 12, 12, 12);
    root->addWidget(llmBox);

    auto *enabledCheck = new QCheckBox("Enable LLM assistance", llmBox);
    dashboardLlmEnableCheck_ = enabledCheck;
    registerDashboardRuntimeLockWidget(enabledCheck);
    llmGrid->addWidget(enabledCheck, 0, 0, 1, 2);

    auto *allowPublicCheck = new QCheckBox("Allow public network endpoint", llmBox);
    allowPublicCheck->setToolTip(
        "Keep unchecked for local/private IP endpoints. Enable for cloud LLM providers.");
    dashboardLlmAllowPublicNetworkCheck_ = allowPublicCheck;
    registerDashboardRuntimeLockWidget(allowPublicCheck);
    llmGrid->addWidget(allowPublicCheck, 0, 2, 1, 2);

    auto *providerCombo = new QComboBox(llmBox);
    for (const auto &provider : TradingBotWindowSupport::pythonSourceLlmProviderConfigs()) {
        QVariantMap spec;
        spec.insert(QStringLiteral("key"), provider.key);
        spec.insert(QStringLiteral("label"), provider.label);
        spec.insert(QStringLiteral("mode"), provider.mode);
        spec.insert(QStringLiteral("protocol"), provider.protocol);
        spec.insert(QStringLiteral("base_url"), provider.defaultBaseUrl);
        spec.insert(QStringLiteral("default_model"), provider.defaultModel);
        spec.insert(QStringLiteral("api_key_env"), provider.apiKeyEnv);
        spec.insert(QStringLiteral("models"), provider.modelSuggestions);
        spec.insert(
            QStringLiteral("reasoning_efforts"),
            provider.reasoningEfforts.isEmpty()
                ? QStringList{QStringLiteral("default")}
                : provider.reasoningEfforts);
        spec.insert(
            QStringLiteral("default_reasoning"),
            provider.defaultReasoningEffort.isEmpty()
                ? QStringLiteral("default")
                : provider.defaultReasoningEffort);
        providerCombo->addItem(provider.label, spec);
    }
    dashboardLlmProviderCombo_ = providerCombo;
    registerDashboardRuntimeLockWidget(providerCombo);
    llmGrid->addWidget(new QLabel("Provider:", llmBox), 1, 0);
    llmGrid->addWidget(providerCombo, 1, 1);

    auto *modelCombo = new QComboBox(llmBox);
    modelCombo->setEditable(false);
    dashboardLlmModelCombo_ = modelCombo;
    registerDashboardRuntimeLockWidget(modelCombo);
    llmGrid->addWidget(new QLabel("Model:", llmBox), 1, 2);
    llmGrid->addWidget(modelCombo, 1, 3);

    auto *baseUrlEdit = new QLineEdit(llmBox);
    baseUrlEdit->setPlaceholderText("https://api.openai.com/v1 or http://192.168.1.20:11434/v1");
    dashboardLlmBaseUrlEdit_ = baseUrlEdit;
    registerDashboardRuntimeLockWidget(baseUrlEdit);
    llmGrid->addWidget(new QLabel("Base URL / IP:", llmBox), 2, 0);
    llmGrid->addWidget(baseUrlEdit, 2, 1, 1, 3);

    auto *apiKeyEnvEdit = new QLineEdit(llmBox);
    apiKeyEnvEdit->setPlaceholderText("OPENAI_API_KEY");
    dashboardLlmApiKeyEnvEdit_ = apiKeyEnvEdit;
    registerDashboardRuntimeLockWidget(apiKeyEnvEdit);
    llmGrid->addWidget(new QLabel("API key env:", llmBox), 3, 0);
    llmGrid->addWidget(apiKeyEnvEdit, 3, 1);

    auto *apiKeyEdit = new QLineEdit(llmBox);
    apiKeyEdit->setEchoMode(QLineEdit::Password);
    apiKeyEdit->setPlaceholderText("Optional token; env var is preferred");
    dashboardLlmApiKeyEdit_ = apiKeyEdit;
    registerDashboardRuntimeLockWidget(apiKeyEdit);
    llmGrid->addWidget(new QLabel("API token:", llmBox), 3, 2);
    llmGrid->addWidget(apiKeyEdit, 3, 3);

    auto *useForCombo = new QComboBox(llmBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        useForCombo,
        TradingBotWindowSupport::pythonSourceLlmUseForOptionKeys(),
        TradingBotWindowSupport::pythonSourceLlmUseForOptionLabels(),
        {},
        QStringLiteral("advisory"));
    dashboardLlmUseForCombo_ = useForCombo;
    registerDashboardRuntimeLockWidget(useForCombo);
    llmGrid->addWidget(new QLabel("Use for:", llmBox), 4, 0);
    llmGrid->addWidget(useForCombo, 4, 1);

    auto *reasoningCombo = new QComboBox(llmBox);
    reasoningCombo->setEditable(false);
    dashboardLlmReasoningCombo_ = reasoningCombo;
    registerDashboardRuntimeLockWidget(reasoningCombo);
    llmGrid->addWidget(new QLabel("Reasoning / Thinking:", llmBox), 4, 2);
    llmGrid->addWidget(reasoningCombo, 4, 3);

    auto *promptEdit = new QTextEdit(llmBox);
    promptEdit->setPlaceholderText("Ask for advisory-only market analysis. The LLM cannot place orders.");
    promptEdit->setFixedHeight(72);
    registerDashboardRuntimeLockWidget(promptEdit);
    llmGrid->addWidget(new QLabel("Advisory prompt:", llmBox), 5, 0);
    llmGrid->addWidget(promptEdit, 5, 1, 1, 3);

    auto *systemPromptEdit = new QTextEdit(llmBox);
    systemPromptEdit->setPlaceholderText("Optional system prompt; default advisory safety prompt is used when empty.");
    systemPromptEdit->setFixedHeight(58);
    registerDashboardRuntimeLockWidget(systemPromptEdit);
    llmGrid->addWidget(new QLabel("System prompt:", llmBox), 6, 0);
    llmGrid->addWidget(systemPromptEdit, 6, 1, 1, 3);

    auto *applyLlmBtn = new QPushButton("Apply LLM Settings", llmBox);
    auto *prepareLlmBtn = new QPushButton("Prepare Advisory", llmBox);
    auto *sendLlmBtn = new QPushButton("Send Advisory", llmBox);
    auto *checkLocalModelBtn = new QPushButton("Check Local Model", llmBox);
    auto *startLocalModelBtn = new QPushButton("Start Local Server", llmBox);
    auto *downloadLocalModelBtn = new QPushButton("Download Local Model", llmBox);
    auto *deleteLocalModelBtn = new QPushButton("Delete Local Model", llmBox);
    registerDashboardRuntimeLockWidget(applyLlmBtn);
    registerDashboardRuntimeLockWidget(prepareLlmBtn);
    registerDashboardRuntimeLockWidget(sendLlmBtn);
    registerDashboardRuntimeLockWidget(checkLocalModelBtn);
    registerDashboardRuntimeLockWidget(startLocalModelBtn);
    registerDashboardRuntimeLockWidget(downloadLocalModelBtn);
    registerDashboardRuntimeLockWidget(deleteLocalModelBtn);
    llmGrid->addWidget(applyLlmBtn, 7, 0);
    llmGrid->addWidget(prepareLlmBtn, 7, 1);
    llmGrid->addWidget(sendLlmBtn, 7, 2);
    llmGrid->addWidget(checkLocalModelBtn, 8, 0);
    llmGrid->addWidget(startLocalModelBtn, 8, 1);
    llmGrid->addWidget(downloadLocalModelBtn, 8, 2);
    llmGrid->addWidget(deleteLocalModelBtn, 8, 3);

    auto *statusLabel = new QLabel("LLM settings are saved with dashboard config.", llmBox);
    statusLabel->setStyleSheet("color: #94a3b8; font-weight: 600;");
    dashboardLlmStatusLabel_ = statusLabel;
    llmGrid->addWidget(statusLabel, 9, 0, 1, 4);

    auto applyProviderDefaults = [this](bool forceText) {
        if (!dashboardLlmProviderCombo_) {
            return;
        }
        const QVariantMap spec = dashboardLlmProviderCombo_->currentData().toMap();
        const QStringList models = spec.value(QStringLiteral("models")).toStringList();
        const QString defaultModel = spec.value(QStringLiteral("default_model")).toString().trimmed();
        const QString currentModel = dashboardLlmModelCombo_
            ? dashboardLlmModelCombo_->currentText().trimmed()
            : QString();
        if (dashboardLlmModelCombo_) {
            QSignalBlocker blocker(dashboardLlmModelCombo_);
            dashboardLlmModelCombo_->clear();
            dashboardLlmModelCombo_->addItems(models);
            dashboardLlmModelCombo_->setCurrentText(
                !forceText && !currentModel.isEmpty()
                    ? currentModel
                    : (!defaultModel.isEmpty() ? defaultModel : (models.isEmpty() ? QString() : models.first())));
        }
        const QStringList reasoningEfforts = spec.value(QStringLiteral("reasoning_efforts")).toStringList();
        const QString defaultReasoning = spec.value(QStringLiteral("default_reasoning")).toString().trimmed();
        const QString currentReasoning = dashboardLlmReasoningCombo_
            ? dashboardLlmReasoningCombo_->currentText().trimmed()
            : QString();
        if (dashboardLlmReasoningCombo_) {
            QSignalBlocker blocker(dashboardLlmReasoningCombo_);
            dashboardLlmReasoningCombo_->clear();
            dashboardLlmReasoningCombo_->addItems(reasoningEfforts);
            dashboardLlmReasoningCombo_->setCurrentText(
                !forceText && !currentReasoning.isEmpty()
                    ? currentReasoning
                    : (!defaultReasoning.isEmpty()
                        ? defaultReasoning
                        : (reasoningEfforts.isEmpty() ? QStringLiteral("default") : reasoningEfforts.first())));
        }
        if (dashboardLlmBaseUrlEdit_ && (forceText || dashboardLlmBaseUrlEdit_->text().trimmed().isEmpty())) {
            dashboardLlmBaseUrlEdit_->setText(spec.value(QStringLiteral("base_url")).toString());
        }
        if (dashboardLlmApiKeyEnvEdit_ && (forceText || dashboardLlmApiKeyEnvEdit_->text().trimmed().isEmpty())) {
            dashboardLlmApiKeyEnvEdit_->setText(spec.value(QStringLiteral("api_key_env")).toString());
        }
        if (dashboardLlmAllowPublicNetworkCheck_) {
            dashboardLlmAllowPublicNetworkCheck_->setChecked(spec.value(QStringLiteral("mode")).toString() == QStringLiteral("cloud"));
        }
        if (dashboardLlmStatusLabel_) {
            dashboardLlmStatusLabel_->setText(
                QStringLiteral("%1 selected (%2, reasoning: %3).")
                    .arg(dashboardLlmProviderCombo_->currentText().trimmed())
                    .arg(spec.value(QStringLiteral("mode")).toString())
                    .arg(dashboardLlmReasoningCombo_ ? dashboardLlmReasoningCombo_->currentText().trimmed() : QStringLiteral("default")));
        }
    };
    auto syncProviderNetworkAccess = [this]() {
        if (!dashboardLlmProviderCombo_) {
            return;
        }
        const bool allowPublicNetwork = dashboardLlmAllowPublicNetworkCheck_
            && dashboardLlmAllowPublicNetworkCheck_->isChecked();
        int fallbackIndex = -1;
        if (auto *model = qobject_cast<QStandardItemModel *>(dashboardLlmProviderCombo_->model())) {
            for (int row = 0; row < dashboardLlmProviderCombo_->count(); ++row) {
                const QVariantMap spec = dashboardLlmProviderCombo_->itemData(row).toMap();
                const bool isCloud = spec.value(QStringLiteral("mode")).toString() == QStringLiteral("cloud");
                const bool allowed = allowPublicNetwork || !isCloud;
                if (!isCloud && fallbackIndex < 0) {
                    fallbackIndex = row;
                }
                if (QStandardItem *item = model->item(row)) {
                    item->setEnabled(allowed);
                    item->setForeground(QColor(allowed ? "#f8fafc" : "#64748b"));
                }
            }
        }
        const QVariantMap currentSpec = dashboardLlmProviderCombo_->currentData().toMap();
        const bool currentIsCloud = currentSpec.value(QStringLiteral("mode")).toString() == QStringLiteral("cloud");
        if (!allowPublicNetwork && currentIsCloud && fallbackIndex >= 0) {
            dashboardLlmProviderCombo_->setCurrentIndex(fallbackIndex);
        }
    };
    auto buildLlmConfigPatch = [this]() {
        const QVariantMap providerSpec = dashboardLlmProviderCombo_
            ? dashboardLlmProviderCombo_->currentData().toMap()
            : QVariantMap{};
        QJsonObject config;
        config.insert(QStringLiteral("llm_enabled"), dashboardLlmEnableCheck_ && dashboardLlmEnableCheck_->isChecked());
        config.insert(QStringLiteral("llm_provider"), providerSpec.value(QStringLiteral("key")).toString().trimmed());
        config.insert(
            QStringLiteral("llm_model"),
            dashboardLlmModelCombo_ ? dashboardLlmModelCombo_->currentText().trimmed() : QString());
        config.insert(
            QStringLiteral("llm_base_url"),
            dashboardLlmBaseUrlEdit_ ? dashboardLlmBaseUrlEdit_->text().trimmed() : QString());
        config.insert(
            QStringLiteral("llm_api_key_env"),
            dashboardLlmApiKeyEnvEdit_ ? dashboardLlmApiKeyEnvEdit_->text().trimmed() : QString());
        config.insert(
            QStringLiteral("llm_api_key"),
            dashboardLlmApiKeyEdit_ ? dashboardLlmApiKeyEdit_->text().trimmed() : QString());
        config.insert(
            QStringLiteral("llm_use_for"),
            dashboardLlmUseForCombo_ ? dashboardLlmUseForCombo_->currentData().toString().trimmed() : QStringLiteral("advisory"));
        config.insert(
            QStringLiteral("llm_allow_public_network"),
            dashboardLlmAllowPublicNetworkCheck_ && dashboardLlmAllowPublicNetworkCheck_->isChecked());
        config.insert(
            QStringLiteral("llm_reasoning_effort"),
            dashboardLlmReasoningCombo_ ? dashboardLlmReasoningCombo_->currentText().trimmed() : QStringLiteral("default"));
        QJsonObject wrapper;
        wrapper.insert(QStringLiteral("config"), config);
        return wrapper;
    };

    auto updateLlmEnabledState = [this,
                                  applyLlmBtn,
                                  checkLocalModelBtn,
                                  deleteLocalModelBtn,
                                  downloadLocalModelBtn,
                                  prepareLlmBtn,
                                  promptEdit,
                                  sendLlmBtn,
                                  startLocalModelBtn,
                                  systemPromptEdit]() {
        const bool enabled = dashboardLlmEnableCheck_ && dashboardLlmEnableCheck_->isChecked();
        const QVariantMap providerSpec = dashboardLlmProviderCombo_
            ? dashboardLlmProviderCombo_->currentData().toMap()
            : QVariantMap{};
        const QString providerMode = providerSpec.value(QStringLiteral("mode")).toString().trimmed().toLower();
        const QString providerKey = providerSpec.value(QStringLiteral("key")).toString().trimmed().toLower();
        const bool localProvider = providerMode == QStringLiteral("local")
            || providerKey.contains(QStringLiteral("local"))
            || providerKey.contains(QStringLiteral("ollama"))
            || providerKey.contains(QStringLiteral("custom"));
        const QVector<QWidget *> widgets = {
            dashboardLlmAllowPublicNetworkCheck_,
            dashboardLlmProviderCombo_,
            dashboardLlmModelCombo_,
            dashboardLlmReasoningCombo_,
            dashboardLlmBaseUrlEdit_,
            dashboardLlmApiKeyEnvEdit_,
            dashboardLlmApiKeyEdit_,
            dashboardLlmUseForCombo_,
            applyLlmBtn,
            checkLocalModelBtn,
            deleteLocalModelBtn,
            downloadLocalModelBtn,
            prepareLlmBtn,
            promptEdit,
            sendLlmBtn,
            startLocalModelBtn,
            systemPromptEdit,
        };
        for (QWidget *widget : widgets) {
            if (!widget) {
                continue;
            }
            widget->setEnabled(enabled);
            if (enabled) {
                widget->setGraphicsEffect(nullptr);
            } else {
                auto *effect = new QGraphicsOpacityEffect(widget);
                effect->setOpacity(0.42);
                widget->setGraphicsEffect(effect);
            }
        }
        for (QWidget *widget : {checkLocalModelBtn, startLocalModelBtn, downloadLocalModelBtn, deleteLocalModelBtn}) {
            if (widget) {
                widget->setEnabled(enabled && localProvider);
            }
        }
        if (!dashboardLlmStatusLabel_) {
            return;
        }
        if (!enabled) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("LLM assistance disabled - enable it to edit provider and model settings."));
            return;
        }
        if (dashboardLlmProviderCombo_) {
            const QVariantMap spec = dashboardLlmProviderCombo_->currentData().toMap();
            dashboardLlmStatusLabel_->setText(
                QStringLiteral("%1 selected (%2, reasoning: %3).")
                    .arg(dashboardLlmProviderCombo_->currentText().trimmed())
                    .arg(spec.value(QStringLiteral("mode")).toString())
                    .arg(dashboardLlmReasoningCombo_ ? dashboardLlmReasoningCombo_->currentText().trimmed() : QStringLiteral("default")));
        }
    };
    connect(enabledCheck, &QCheckBox::toggled, this, [updateLlmEnabledState](bool) {
        updateLlmEnabledState();
    });
    connect(allowPublicCheck, &QCheckBox::toggled, this, [syncProviderNetworkAccess, updateLlmEnabledState](bool) {
        syncProviderNetworkAccess();
        updateLlmEnabledState();
    });
    connect(providerCombo, &QComboBox::currentIndexChanged, this, [applyProviderDefaults, syncProviderNetworkAccess, updateLlmEnabledState](int) {
        applyProviderDefaults(true);
        syncProviderNetworkAccess();
        updateLlmEnabledState();
    });
    connect(reasoningCombo, &QComboBox::currentIndexChanged, this, [updateLlmEnabledState](int) {
        updateLlmEnabledState();
    });
    auto applyLlmSettings = [this, buildLlmConfigPatch](bool quiet) {
        if (dashboardLlmStatusLabel_) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("Applying LLM settings through Python Service API..."));
        }
        const auto result = TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("PATCH"),
            QStringLiteral("llm_config"),
            buildLlmConfigPatch(),
            30000);
        if (!dashboardLlmStatusLabel_) {
            return result.ok;
        }
        if (result.ok) {
            const QJsonObject payload = result.document.object();
            const QString provider = payload.value(QStringLiteral("provider_label")).toString(
                dashboardLlmProviderCombo_ ? dashboardLlmProviderCombo_->currentText().trimmed() : QStringLiteral("LLM"));
            const QString model = payload.value(QStringLiteral("model")).toString(
                dashboardLlmModelCombo_ ? dashboardLlmModelCombo_->currentText().trimmed() : QString());
            if (!quiet) {
                dashboardLlmStatusLabel_->setText(
                    QStringLiteral("LLM settings applied through Python Service API: %1 %2.")
                        .arg(provider, model));
            }
        } else {
            dashboardLlmStatusLabel_->setText(QStringLiteral("LLM settings apply failed: %1").arg(result.error));
        }
        return result.ok;
    };
    connect(applyLlmBtn, &QPushButton::clicked, this, [applyLlmSettings]() {
        applyLlmSettings(false);
    });
    auto runLlmPrompt = [this, applyLlmSettings, promptEdit, systemPromptEdit](bool dryRun) {
        const QString prompt = promptEdit ? promptEdit->toPlainText().trimmed() : QString();
        if (prompt.isEmpty()) {
            if (dashboardLlmStatusLabel_) {
                dashboardLlmStatusLabel_->setText(QStringLiteral("LLM advisory: enter a prompt first."));
            }
            return;
        }
        if (!dryRun) {
            const QMessageBox::StandardButton answer = QMessageBox::question(
                this,
                QStringLiteral("Send LLM Advisory"),
                QStringLiteral("Send this advisory prompt to the selected LLM provider? The LLM remains advisory-only and cannot execute trades."));
            if (answer != QMessageBox::Yes) {
                if (dashboardLlmStatusLabel_) {
                    dashboardLlmStatusLabel_->setText(QStringLiteral("LLM advisory send cancelled."));
                }
                return;
            }
        }
        if (!applyLlmSettings(true)) {
            return;
        }
        QJsonObject request;
        request.insert(QStringLiteral("prompt"), prompt);
        request.insert(QStringLiteral("system_prompt"), systemPromptEdit ? systemPromptEdit->toPlainText().trimmed() : QString());
        request.insert(QStringLiteral("dry_run"), dryRun);
        request.insert(
            QStringLiteral("source"),
            dryRun ? QStringLiteral("cpp-desktop-llm-dry-run") : QStringLiteral("cpp-desktop-llm-advisory"));

        if (dashboardLlmStatusLabel_) {
            dashboardLlmStatusLabel_->setText(
                dryRun
                    ? QStringLiteral("Preparing LLM advisory request through Python Service API...")
                    : QStringLiteral("Sending LLM advisory request through Python Service API..."));
        }
        const auto result = TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("POST"),
            QStringLiteral("llm_prompt"),
            request,
            45000);
        if (!dashboardLlmStatusLabel_) {
            return;
        }
        if (!result.ok) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("LLM advisory failed: %1").arg(result.error));
            return;
        }
        const QJsonObject payload = result.document.object();
        const bool ok = payload.value(QStringLiteral("ok")).toBool(false);
        const QString text = payload.value(QStringLiteral("text")).toString().trimmed();
        const QString error = payload.value(QStringLiteral("error")).toString().trimmed();
        if (ok && dryRun) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("LLM advisory request prepared; provider payload was validated by Python Service API."));
        } else if (ok) {
            dashboardLlmStatusLabel_->setText(
                text.isEmpty()
                    ? QStringLiteral("LLM advisory completed; provider returned no text.")
                    : QStringLiteral("LLM advisory: %1").arg(text.left(500)));
        } else {
            dashboardLlmStatusLabel_->setText(
                error.isEmpty()
                    ? QStringLiteral("LLM advisory blocked or failed by Python Service API policy.")
                    : QStringLiteral("LLM advisory blocked or failed: %1").arg(error.left(500)));
        }
    };
    connect(prepareLlmBtn, &QPushButton::clicked, this, [runLlmPrompt]() {
        runLlmPrompt(true);
    });
    connect(sendLlmBtn, &QPushButton::clicked, this, [runLlmPrompt]() {
        runLlmPrompt(false);
    });
    auto localModelPayload = [this]() {
        QJsonObject request;
        request.insert(
            QStringLiteral("base_url"),
            dashboardLlmBaseUrlEdit_ ? dashboardLlmBaseUrlEdit_->text().trimmed() : QStringLiteral("http://127.0.0.1:11434/v1"));
        request.insert(
            QStringLiteral("model"),
            dashboardLlmModelCombo_ ? dashboardLlmModelCombo_->currentText().trimmed() : QString());
        request.insert(QStringLiteral("source"), QStringLiteral("cpp-desktop-llm-local-model"));
        return request;
    };
    auto localModelSummary = [](QJsonObject payload) {
        if (payload.contains(QStringLiteral("status")) && payload.value(QStringLiteral("status")).isObject()) {
            payload = payload.value(QStringLiteral("status")).toObject();
        }
        QStringList storagePaths;
        for (const QJsonValue &value : payload.value(QStringLiteral("storage_paths")).toArray()) {
            const QString path = value.toString().trimmed();
            if (!path.isEmpty()) {
                storagePaths.push_back(path);
            }
        }
        QStringList parts;
        const QString model = payload.value(QStringLiteral("model")).toString().trimmed();
        const QString kind = payload.value(QStringLiteral("server_kind")).toString().trimmed();
        const QString size = payload.value(QStringLiteral("estimated_size_label")).toString().trimmed();
        const QString warning = payload.value(QStringLiteral("disk_space_warning")).toString().trimmed();
        const QString error = payload.value(QStringLiteral("error")).toString().trimmed();
        if (!model.isEmpty()) {
            parts.push_back(QStringLiteral("model %1").arg(model));
        }
        if (!kind.isEmpty()) {
            parts.push_back(kind);
        }
        if (payload.contains(QStringLiteral("installed"))) {
            parts.push_back(payload.value(QStringLiteral("installed")).toBool(false) ? QStringLiteral("installed") : QStringLiteral("not installed"));
        }
        if (!size.isEmpty()) {
            parts.push_back(size);
        }
        if (!storagePaths.isEmpty()) {
            parts.push_back(QStringLiteral("storage: %1").arg(storagePaths.join(QStringLiteral("; "))));
        }
        if (!warning.isEmpty()) {
            parts.push_back(warning);
        }
        if (!error.isEmpty()) {
            parts.push_back(QStringLiteral("error: %1").arg(error));
        }
        if (parts.isEmpty() && payload.contains(QStringLiteral("started"))) {
            parts.push_back(payload.value(QStringLiteral("started")).toBool(false) ? QStringLiteral("local server started") : QStringLiteral("local server not started"));
        }
        return parts.isEmpty() ? QStringLiteral("Local model response received.") : parts.join(QStringLiteral(" | "));
    };
    auto runLocalModelAction = [this, localModelPayload, localModelSummary](
                                   const QString &label,
                                   const QString &routeName,
                                   const QString &method,
                                   int timeoutMs,
                                   bool confirm) {
        const QJsonObject request = localModelPayload();
        const QString model = request.value(QStringLiteral("model")).toString().trimmed();
        if (model.isEmpty()) {
            if (dashboardLlmStatusLabel_) {
                dashboardLlmStatusLabel_->setText(QStringLiteral("Select a concrete local model first."));
            }
            return;
        }
        if (confirm) {
            const QMessageBox::StandardButton answer = QMessageBox::question(
                this,
                label,
                QStringLiteral("%1 for '%2' on this PC?").arg(label, model));
            if (answer != QMessageBox::Yes) {
                if (dashboardLlmStatusLabel_) {
                    dashboardLlmStatusLabel_->setText(QStringLiteral("%1 cancelled for '%2'.").arg(label, model));
                }
                return;
            }
        }
        if (dashboardLlmStatusLabel_) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("%1 through Python Service API...").arg(label));
        }
        const auto result = TradingBotWindowSupport::serviceApiRequestJson(method, routeName, request, timeoutMs);
        if (!dashboardLlmStatusLabel_) {
            return;
        }
        if (!result.ok) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("%1 failed: %2").arg(label, result.error));
            return;
        }
        dashboardLlmStatusLabel_->setText(QStringLiteral("%1: %2").arg(label, localModelSummary(result.document.object())));
    };
    connect(checkLocalModelBtn, &QPushButton::clicked, this, [runLocalModelAction]() {
        runLocalModelAction(
            QStringLiteral("Check local model"),
            QStringLiteral("llm_local_model_status"),
            QStringLiteral("GET"),
            10000,
            false);
    });
    connect(startLocalModelBtn, &QPushButton::clicked, this, [runLocalModelAction]() {
        runLocalModelAction(
            QStringLiteral("Start local model server"),
            QStringLiteral("llm_local_model_start"),
            QStringLiteral("POST"),
            30000,
            true);
    });
    connect(downloadLocalModelBtn, &QPushButton::clicked, this, [runLocalModelAction]() {
        runLocalModelAction(
            QStringLiteral("Download local model"),
            QStringLiteral("llm_local_model_pull"),
            QStringLiteral("POST"),
            1'800'000,
            true);
    });
    connect(deleteLocalModelBtn, &QPushButton::clicked, this, [runLocalModelAction]() {
        runLocalModelAction(
            QStringLiteral("Delete local model"),
            QStringLiteral("llm_local_model_delete"),
            QStringLiteral("POST"),
            60000,
            true);
    });
    applyProviderDefaults(true);
    syncProviderNetworkAccess();
    updateLlmEnabledState();

    llmGrid->setColumnStretch(1, 1);
    llmGrid->setColumnStretch(3, 2);
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        exchangeCombo,
        TradingBotWindowSupport::pythonSourceExchangeOptionKeys(),
        TradingBotWindowSupport::pythonSourceExchangeOptionLabels(),
        TradingBotWindowSupport::pythonSourceExchangeOptionDisabledLabels(),
        QStringLiteral("Binance"));
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
    dashboardSymbolList->addItems(TradingBotWindowSupport::pythonSourceDefaultExecutionSymbols());
    dashboardSymbolList->setMinimumHeight(220);
    dashboardSymbolList->setMaximumHeight(260);
    dashboardSymbolList_ = dashboardSymbolList;
    registerDashboardRuntimeLockWidget(dashboardSymbolList);
    listsGrid->addWidget(dashboardSymbolList, 1, 0, 2, 1);

    auto *dashboardIntervalList = new QListWidget(marketsBox);
    dashboardIntervalList->setSelectionMode(QAbstractItemView::MultiSelection);
    dashboardIntervalList->addItems(TradingBotWindowSupport::pythonSourceBacktestIntervals());
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        sideCombo,
        TradingBotWindowSupport::pythonSourceSideOptionKeys(),
        TradingBotWindowSupport::pythonSourceSideOptionLabels(),
        {},
        {},
        QStringLiteral("Both (Long/Short)"));
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        loopOverride,
        TradingBotWindowSupport::pythonSourceDashboardLoopChoiceKeys(),
        TradingBotWindowSupport::pythonSourceDashboardLoopChoiceLabels(),
        {},
        QStringLiteral("1m"),
        QStringLiteral("1 minute"));
    dashboardLoopOverrideCombo_ = loopOverride;
    registerDashboardRuntimeLockWidget(loopOverride);
    strategyGrid->addWidget(loopOverride, row, 5);

    ++row;
    auto *enableLeadTrader = new QCheckBox("Enable Lead Trader", strategyBox);
    dashboardLeadTraderEnableCheck_ = enableLeadTrader;
    registerDashboardRuntimeLockWidget(enableLeadTrader);
    strategyGrid->addWidget(enableLeadTrader, row, 0, 1, 2);
    auto *leadTraderCombo = new QComboBox(strategyBox);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        leadTraderCombo,
        TradingBotWindowSupport::pythonSourceLeadTraderOptionKeys(),
        TradingBotWindowSupport::pythonSourceLeadTraderOptionLabels());
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        stopModeCombo,
        TradingBotWindowSupport::pythonSourceStopLossModeKeys(),
        TradingBotWindowSupport::pythonSourceStopLossModeLabels(),
        {},
        QStringLiteral("usdt"));
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        stopScopeCombo,
        TradingBotWindowSupport::pythonSourceStopLossScopeKeys(),
        TradingBotWindowSupport::pythonSourceStopLossScopeLabels(),
        {},
        QStringLiteral("per_trade"));
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
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        templateCombo,
        TradingBotWindowSupport::pythonSourceDashboardStrategyTemplateKeys(),
        TradingBotWindowSupport::pythonSourceDashboardStrategyTemplateLabels());
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

    const QStringList defaultEnabledIndicatorKeys =
        TradingBotWindowSupport::pythonSourceDefaultEnabledIndicatorKeys();
    auto addIndicatorRow = [defaultEnabledIndicatorKeys, indicatorsBox, indGrid, this](
                               int rowIndex,
                               const QString &name) {
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
            const bool checkedByDefault = defaultEnabledIndicatorKeys.contains(indicatorKey);
            cb->setChecked(checkedByDefault);
            btn->setEnabled(checkedByDefault);
            dashboardIndicatorChecks_.insert(indicatorKey, cb);
            dashboardIndicatorButtons_.insert(indicatorKey, btn);
            if (!dashboardIndicatorParams_.contains(indicatorKey)) {
                dashboardIndicatorParams_.insert(indicatorKey, QVariantMap{});
            }
        }
        indGrid->addWidget(cb, rowIndex, 0);
        indGrid->addWidget(btn, rowIndex, 1);
    };

    const QStringList indicators = TradingBotWindowSupport::pythonSourceIndicatorDisplayNames();
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
    dashboardLlmEnableCheck_ = nullptr;
    dashboardLlmProviderCombo_ = nullptr;
    dashboardLlmModelCombo_ = nullptr;
    dashboardLlmReasoningCombo_ = nullptr;
    dashboardLlmBaseUrlEdit_ = nullptr;
    dashboardLlmApiKeyEnvEdit_ = nullptr;
    dashboardLlmApiKeyEdit_ = nullptr;
    dashboardLlmUseForCombo_ = nullptr;
    dashboardLlmAllowPublicNetworkCheck_ = nullptr;
    dashboardLlmStatusLabel_ = nullptr;
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
    createDashboardLlmSection(page, root);
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
