#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"
#include "BinanceWsClient.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QColor>
#include <QComboBox>
#include <QCoreApplication>
#include <QDateTime>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QGridLayout>
#include <QGroupBox>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMap>
#include <QMessageBox>
#include <QPushButton>
#include <QRegularExpression>
#include <QScrollArea>
#include <QSet>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStandardItemModel>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTabWidget>
#include <QTextEdit>
#include <QTimer>
#include <QVariant>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>

namespace {
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

} // namespace

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
    TradingBotWindowSupport::rebuildConnectorComboForAccount(connectorCombo, true, true);
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
