#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QStringList>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QVariant>
#include <QVariantMap>

#include <algorithm>

namespace {

QString jsonValueText(const QJsonValue &value, const QString &fallback = {}) {
    if (value.isString()) {
        const QString text = value.toString().trimmed();
        return text.isEmpty() ? fallback : text;
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble());
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    return fallback;
}

QString comboText(const QComboBox *combo, const QString &fallback = {}) {
    if (!combo) {
        return fallback;
    }
    const QString text = combo->currentText().trimmed();
    return text.isEmpty() ? fallback : text;
}

QString comboDataOrText(const QComboBox *combo, const QString &fallback = {}) {
    if (!combo) {
        return fallback;
    }
    QString value = combo->currentData().toString().trimmed();
    if (value.isEmpty()) {
        const QVariantMap spec = combo->currentData().toMap();
        value = spec.value(QStringLiteral("key")).toString().trimmed();
    }
    if (value.isEmpty()) {
        value = combo->currentText().trimmed();
    }
    return value.isEmpty() ? fallback : value;
}

QString llmProviderKey(const QComboBox *combo) {
    if (!combo) {
        return QStringLiteral("local");
    }
    const QVariantMap providerSpec = combo->currentData().toMap();
    const QString key = providerSpec.value(QStringLiteral("key")).toString().trimmed();
    return key.isEmpty() ? comboDataOrText(combo, QStringLiteral("local")) : key;
}

void setComboValue(QComboBox *combo, const QJsonValue &value) {
    if (!combo || value.isUndefined()) {
        return;
    }
    const QString target = jsonValueText(value).trimmed();
    if (target.isEmpty()) {
        return;
    }

    int index = combo->findData(target);
    if (index < 0) {
        index = combo->findText(target, Qt::MatchFixedString);
    }
    if (index < 0) {
        for (int row = 0; row < combo->count(); ++row) {
            const QVariantMap spec = combo->itemData(row).toMap();
            const QStringList candidates = {
                combo->itemData(row).toString().trimmed(),
                spec.value(QStringLiteral("key")).toString().trimmed(),
                spec.value(QStringLiteral("value")).toString().trimmed(),
                spec.value(QStringLiteral("label")).toString().trimmed(),
                combo->itemText(row).trimmed(),
            };
            for (const QString &candidate : candidates) {
                if (!candidate.isEmpty() && candidate.compare(target, Qt::CaseInsensitive) == 0) {
                    index = row;
                    break;
                }
            }
            if (index >= 0) {
                break;
            }
        }
    }
    if (index >= 0) {
        QSignalBlocker blocker(combo);
        combo->setCurrentIndex(index);
    }
}

void setComboTextAllowingCustom(QComboBox *combo, const QString &textRaw) {
    if (!combo) {
        return;
    }
    const QString text = textRaw.trimmed();
    if (text.isEmpty()) {
        return;
    }
    int index = combo->findText(text, Qt::MatchFixedString);
    if (index < 0) {
        combo->addItem(text);
        index = combo->count() - 1;
    }
    QSignalBlocker blocker(combo);
    combo->setCurrentIndex(index);
}

QJsonArray selectedOrAllListValues(const QListWidget *list, bool uppercase) {
    QJsonArray values;
    if (!list) {
        return values;
    }

    QStringList texts;
    const QList<QListWidgetItem *> selected = list->selectedItems();
    if (!selected.isEmpty()) {
        for (const QListWidgetItem *item : selected) {
            if (item) {
                texts.append(item->text().trimmed());
            }
        }
    } else {
        for (int row = 0; row < list->count(); ++row) {
            const QListWidgetItem *item = list->item(row);
            if (item) {
                texts.append(item->text().trimmed());
            }
        }
    }

    texts.removeAll(QString());
    for (QString text : texts) {
        if (uppercase) {
            text = text.toUpper();
        }
        bool duplicate = false;
        for (const QJsonValue &existing : values) {
            if (existing.toString().compare(text, Qt::CaseInsensitive) == 0) {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) {
            values.append(text);
        }
    }
    return values;
}

QJsonArray stringListJsonArray(QStringList values, bool uppercase) {
    QJsonArray array;
    values.removeAll(QString());
    values.removeDuplicates();
    for (QString value : values) {
        value = value.trimmed();
        if (value.isEmpty()) {
            continue;
        }
        array.append(uppercase ? value.toUpper() : value);
    }
    return array;
}

void selectListValues(QListWidget *list, const QJsonArray &values, bool uppercase) {
    if (!list || values.isEmpty()) {
        return;
    }

    QStringList wanted;
    for (const QJsonValue &value : values) {
        QString text = jsonValueText(value).trimmed();
        if (text.isEmpty()) {
            continue;
        }
        if (uppercase) {
            text = text.toUpper();
        }
        wanted.append(text);
    }
    wanted.removeDuplicates();
    if (wanted.isEmpty()) {
        return;
    }

    QSignalBlocker blocker(list);
    list->clearSelection();
    for (const QString &text : wanted) {
        bool found = false;
        for (int row = 0; row < list->count(); ++row) {
            QListWidgetItem *item = list->item(row);
            if (item && item->text().trimmed().compare(text, Qt::CaseInsensitive) == 0) {
                item->setSelected(true);
                found = true;
            }
        }
        if (!found) {
            auto *item = new QListWidgetItem(text, list);
            item->setSelected(true);
        }
    }
}

QJsonArray dashboardOverrideRows(const QTableWidget *table) {
    QJsonArray rows;
    if (!table) {
        return rows;
    }
    for (int rowIdx = 0; rowIdx < table->rowCount(); ++rowIdx) {
        const QTableWidgetItem *symbolItem = table->item(rowIdx, 0);
        const QTableWidgetItem *intervalItem = table->item(rowIdx, 1);
        const QString symbol = symbolItem ? symbolItem->text().trimmed().toUpper() : QString();
        const QString interval = intervalItem ? intervalItem->text().trimmed() : QString();
        if (symbol.isEmpty() || interval.isEmpty()) {
            continue;
        }
        QJsonObject row = symbolItem
            ? symbolItem->data(Qt::UserRole).toJsonObject()
            : QJsonObject{};
        row.insert(QStringLiteral("symbol"), symbol);
        row.insert(QStringLiteral("interval"), interval);
        rows.append(row);
    }
    return rows;
}

QString jsonObjectText(const QJsonObject &object, const QString &key, const QString &fallback = {}) {
    return jsonValueText(object.value(key), fallback);
}

QString jsonArrayText(const QJsonArray &values, const QString &fallback = {}) {
    QStringList parts;
    for (const QJsonValue &value : values) {
        const QString text = jsonValueText(value).trimmed();
        if (!text.isEmpty()) {
            parts.append(text);
        }
    }
    return parts.isEmpty() ? fallback : parts.join(QStringLiteral(", "));
}

QString overrideStrategySummary(const QJsonObject &controls) {
    QStringList parts;
    const QStringList keys = {
        QStringLiteral("side"),
        QStringLiteral("position_pct"),
        QStringLiteral("margin_mode"),
        QStringLiteral("position_mode"),
        QStringLiteral("assets_mode"),
        QStringLiteral("account_mode"),
    };
    for (const QString &key : keys) {
        const QString value = jsonValueText(controls.value(key)).trimmed();
        if (!value.isEmpty()) {
            parts.append(QStringLiteral("%1 %2").arg(key, value));
        }
    }
    return parts.isEmpty() ? QStringLiteral("Default") : parts.join(QStringLiteral(" | "));
}

QString overrideStopLossSummary(const QJsonObject &stopLoss) {
    if (stopLoss.isEmpty() || !stopLoss.value(QStringLiteral("enabled")).toBool(false)) {
        return QStringLiteral("Disabled");
    }
    const QString mode = jsonObjectText(stopLoss, QStringLiteral("mode"), QStringLiteral("usdt"));
    const QString scope = jsonObjectText(stopLoss, QStringLiteral("scope"), QStringLiteral("per_trade"));
    const QString usdt = QString::number(stopLoss.value(QStringLiteral("usdt")).toDouble(0.0), 'f', 2);
    const QString percent = QString::number(stopLoss.value(QStringLiteral("percent")).toDouble(0.0), 'f', 2);
    return QStringLiteral("Enabled (%1 | %2 | %3 USDT | %4%)").arg(mode, scope, usdt, percent);
}

void setDashboardOverridePayloadFromConfig(QTableWidget *table, int row, const QJsonObject &payload) {
    if (!table || row < 0) {
        return;
    }
    while (table->rowCount() <= row) {
        table->insertRow(table->rowCount());
    }

    const QJsonObject controls = payload.value(QStringLiteral("strategy_controls")).toObject();
    const QJsonObject stopLoss = payload.value(QStringLiteral("stop_loss")).toObject(
        controls.value(QStringLiteral("stop_loss")).toObject());
    const QStringList values = {
        jsonObjectText(payload, QStringLiteral("symbol")),
        jsonObjectText(payload, QStringLiteral("interval")),
        jsonArrayText(payload.value(QStringLiteral("indicators")).toArray(), QStringLiteral("None")),
        jsonObjectText(payload, QStringLiteral("loop_interval_override"), jsonObjectText(controls, QStringLiteral("loop_interval_override"), QStringLiteral("Default"))),
        payload.contains(QStringLiteral("leverage"))
            ? jsonValueText(payload.value(QStringLiteral("leverage")))
            : jsonValueText(controls.value(QStringLiteral("leverage")), QStringLiteral("Default")),
        jsonObjectText(controls, QStringLiteral("connector_backend"), QStringLiteral("Default")),
        overrideStrategySummary(controls),
        overrideStopLossSummary(stopLoss),
    };
    for (int col = 0; col < values.size(); ++col) {
        auto *item = new QTableWidgetItem(values.at(col));
        if (col == 0) {
            item->setData(Qt::UserRole, payload);
        }
        table->setItem(row, col, item);
    }
}

QJsonObject dashboardIndicatorConfig(
    const QMap<QString, QCheckBox *> &checks,
    const QMap<QString, QVariantMap> &params) {
    QJsonObject indicators;
    for (auto it = checks.cbegin(); it != checks.cend(); ++it) {
        const QString key = it.key().trimmed();
        QCheckBox *check = it.value();
        if (key.isEmpty() || !check) {
            continue;
        }
        QJsonObject indicator = QJsonObject::fromVariantMap(params.value(key));
        indicator.insert(QStringLiteral("enabled"), check->isChecked());
        indicators.insert(key, indicator);
    }
    return indicators;
}

QString persistenceSummary(const QJsonObject &status) {
    QStringList parts;
    const QString path = status.value(QStringLiteral("path")).toString().trimmed();
    const QString savedAt = status.value(QStringLiteral("saved_at")).toString(
        status.value(QStringLiteral("last_saved_at")).toString()).trimmed();
    const QString loadedAt = status.value(QStringLiteral("loaded_at")).toString(
        status.value(QStringLiteral("last_loaded_at")).toString()).trimmed();
    if (!path.isEmpty()) {
        parts << path;
    }
    if (!savedAt.isEmpty()) {
        parts << QStringLiteral("saved %1").arg(savedAt);
    }
    if (!loadedAt.isEmpty()) {
        parts << QStringLiteral("loaded %1").arg(loadedAt);
    }
    if (status.contains(QStringLiteral("dirty"))) {
        parts << (status.value(QStringLiteral("dirty")).toBool(false)
            ? QStringLiteral("dirty")
            : QStringLiteral("clean"));
    }
    return parts.join(QStringLiteral(" | "));
}

} // namespace

QString TradingBotWindow::dashboardEnabledIndicatorsSummary() const {
    QStringList enabled;
    for (auto it = dashboardIndicatorChecks_.cbegin(); it != dashboardIndicatorChecks_.cend(); ++it) {
        QCheckBox *check = it.value();
        if (!check || !check->isChecked()) {
            continue;
        }
        enabled.append(check->text().trimmed());
    }
    enabled.removeAll(QString());
    enabled.removeDuplicates();
    enabled.sort();
    return enabled.isEmpty() ? QStringLiteral("None") : enabled.join(", ");
}

QString TradingBotWindow::dashboardStopLossSummary() const {
    if (!dashboardStopLossEnableCheck_ || !dashboardStopLossEnableCheck_->isChecked()) {
        return QStringLiteral("Disabled");
    }

    QString modeKey = dashboardStopLossModeCombo_
        ? dashboardStopLossModeCombo_->currentData().toString().trimmed().toLower()
        : QString();
    if (modeKey.isEmpty()) {
        modeKey = QStringLiteral("usdt");
    }

    const QString modeText = dashboardStopLossModeCombo_
        ? dashboardStopLossModeCombo_->currentText().trimmed()
        : QString();
    QStringList values;
    if ((modeKey == QStringLiteral("usdt") || modeKey == QStringLiteral("both"))
        && dashboardStopLossUsdtSpin_
        && dashboardStopLossUsdtSpin_->value() > 0.0) {
        values << QStringLiteral("%1 USDT").arg(QString::number(dashboardStopLossUsdtSpin_->value(), 'f', 2));
    }
    if ((modeKey == QStringLiteral("percent") || modeKey == QStringLiteral("both"))
        && dashboardStopLossPercentSpin_
        && dashboardStopLossPercentSpin_->value() > 0.0) {
        values << QStringLiteral("%1%").arg(QString::number(dashboardStopLossPercentSpin_->value(), 'f', 2));
    }

    const QString valueText = values.isEmpty() ? QStringLiteral("Enabled") : values.join(QStringLiteral(" / "));
    const QString scope = dashboardStopLossScopeCombo_
        ? dashboardStopLossScopeCombo_->currentText().trimmed()
        : QString();
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
    return QStringLiteral("%1 (%2)").arg(valueText, details.join(QStringLiteral(" | ")));
}

QString TradingBotWindow::dashboardStrategySummary() const {
    QStringList values;
    if (dashboardSideCombo_) {
        values << dashboardSideCombo_->currentText().trimmed();
    }
    if (dashboardLeadTraderEnableCheck_ && dashboardLeadTraderEnableCheck_->isChecked() && dashboardLeadTraderCombo_) {
        values << QStringLiteral("Lead: %1").arg(dashboardLeadTraderCombo_->currentText().trimmed());
    }
    if (dashboardLiveIndicatorValuesCheck_ && dashboardLiveIndicatorValuesCheck_->isChecked()) {
        values << QStringLiteral("Live candles");
    }
    if (dashboardOneWayCheck_ && dashboardOneWayCheck_->isChecked()) {
        values << QStringLiteral("Add-only");
    }
    if (dashboardHedgeStackCheck_ && dashboardHedgeStackCheck_->isChecked()) {
        values << QStringLiteral("Hedge stacking");
    }
    values.removeAll(QString());
    return values.isEmpty() ? QStringLiteral("Default") : values.join(QStringLiteral(" | "));
}

bool TradingBotWindow::dashboardOverridesHasPair(const QString &symbol, const QString &interval) const {
    if (!dashboardOverridesTable_) {
        return false;
    }

    for (int rowIdx = 0; rowIdx < dashboardOverridesTable_->rowCount(); ++rowIdx) {
        const QTableWidgetItem *symbolItem = dashboardOverridesTable_->item(rowIdx, 0);
        const QTableWidgetItem *intervalItem = dashboardOverridesTable_->item(rowIdx, 1);
        if (!symbolItem || !intervalItem) {
            continue;
        }
        if (symbolItem->text().trimmed().compare(symbol, Qt::CaseInsensitive) == 0
            && intervalItem->text().trimmed().compare(interval, Qt::CaseInsensitive) == 0) {
            return true;
        }
    }
    return false;
}

bool TradingBotWindow::addDashboardOverrideRow(const QString &symbolRaw, const QString &intervalRaw) {
    if (!dashboardOverridesTable_) {
        return false;
    }

    const QString symbol = symbolRaw.trimmed().toUpper();
    const QString interval = intervalRaw.trimmed();
    if (symbol.isEmpty() || interval.isEmpty() || dashboardOverridesHasPair(symbol, interval)) {
        return false;
    }

    const int rowIdx = dashboardOverridesTable_->rowCount();
    dashboardOverridesTable_->insertRow(rowIdx);

    const QString connectorText = dashboardConnectorCombo_
        ? dashboardConnectorCombo_->currentText().trimmed()
        : QStringLiteral("Default");
    const QString loopText = dashboardLoopOverrideCombo_
        ? dashboardLoopOverrideCombo_->currentText().trimmed()
        : QStringLiteral("1 minute");
    const QString leverageText = dashboardLeverageSpin_
        ? QString::number(dashboardLeverageSpin_->value())
        : QStringLiteral("20");
    const QStringList values = {
        symbol,
        interval,
        dashboardEnabledIndicatorsSummary(),
        loopText,
        leverageText,
        connectorText,
        dashboardStrategySummary(),
        dashboardStopLossSummary(),
    };
    for (int col = 0; col < values.size(); ++col) {
        dashboardOverridesTable_->setItem(rowIdx, col, new QTableWidgetItem(values.at(col)));
    }
    return true;
}

void TradingBotWindow::addSelectedDashboardOverrideRows() {
    QStringList selectedSymbols;
    QStringList selectedIntervals;
    if (dashboardSymbolList_) {
        for (QListWidgetItem *item : dashboardSymbolList_->selectedItems()) {
            if (item) {
                selectedSymbols.append(item->text().trimmed().toUpper());
            }
        }
    }
    if (dashboardIntervalList_) {
        for (QListWidgetItem *item : dashboardIntervalList_->selectedItems()) {
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
    for (const QString &symbol : selectedSymbols) {
        for (const QString &interval : selectedIntervals) {
            if (addDashboardOverrideRow(symbol, interval)) {
                ++addedCount;
            }
        }
    }

    updateStatusMessage(QStringLiteral("Overrides updated: added %1 row(s).").arg(addedCount));
    appendDashboardAllLog(QStringLiteral("Override rows added: %1").arg(addedCount));
    appendDashboardWaitingLog(QStringLiteral("Queued symbol/interval overrides: +%1").arg(addedCount));
}

void TradingBotWindow::removeSelectedDashboardOverrideRows() {
    if (!dashboardOverridesTable_) {
        return;
    }

    QSet<int> selectedRows;
    const QList<QTableWidgetItem *> selected = dashboardOverridesTable_->selectedItems();
    for (QTableWidgetItem *item : selected) {
        if (item) {
            selectedRows.insert(item->row());
        }
    }

    QList<int> rows = selectedRows.values();
    std::sort(rows.begin(), rows.end(), std::greater<int>());
    for (int rowIdx : rows) {
        dashboardOverridesTable_->removeRow(rowIdx);
    }

    updateStatusMessage(QStringLiteral("Overrides updated: removed %1 row(s).").arg(rows.size()));
    appendDashboardAllLog(QStringLiteral("Override rows removed: %1").arg(rows.size()));
}

void TradingBotWindow::clearDashboardOverrideRows() {
    if (!dashboardOverridesTable_) {
        return;
    }

    const int rowCount = dashboardOverridesTable_->rowCount();
    dashboardOverridesTable_->setRowCount(0);
    updateStatusMessage(QStringLiteral("Overrides cleared (%1 row(s)).").arg(rowCount));
    appendDashboardAllLog(QStringLiteral("Override rows cleared: %1").arg(rowCount));
    appendDashboardWaitingLog(QStringLiteral("Queue cleared (%1 row(s)).").arg(rowCount));
}

QJsonObject TradingBotWindow::buildDashboardServiceConfigPatch() const {
    QJsonObject config;
    config.insert(QStringLiteral("mode"), comboText(dashboardModeCombo_, QStringLiteral("Testnet")));
    config.insert(QStringLiteral("account_type"), comboText(dashboardAccountTypeCombo_, QStringLiteral("Futures")));
    config.insert(QStringLiteral("account_mode"), comboText(dashboardAccountModeCombo_, QStringLiteral("Classic Trading")));
    config.insert(QStringLiteral("margin_mode"), comboDataOrText(dashboardMarginModeCombo_, QStringLiteral("Isolated")));
    config.insert(QStringLiteral("position_mode"), comboDataOrText(dashboardPositionModeCombo_, QStringLiteral("Hedge")));
    config.insert(QStringLiteral("assets_mode"), comboDataOrText(dashboardAssetsModeCombo_, QStringLiteral("Single-Asset")));
    config.insert(QStringLiteral("connector_backend"), comboDataOrText(dashboardConnectorCombo_, QStringLiteral("binance-native")));
    config.insert(QStringLiteral("selected_exchange"), comboDataOrText(dashboardExchangeCombo_, QStringLiteral("Binance")));
    config.insert(QStringLiteral("theme"), comboText(dashboardThemeCombo_));
    config.insert(QStringLiteral("leverage"), dashboardLeverageSpin_ ? dashboardLeverageSpin_->value() : 1);
    config.insert(QStringLiteral("tif"), comboDataOrText(dashboardTimeInForceCombo_, QStringLiteral("GTC")));
    config.insert(QStringLiteral("gtd_minutes"), dashboardGtdMinutesSpin_ ? dashboardGtdMinutesSpin_->value() : 30);
    config.insert(QStringLiteral("indicator_source"), comboDataOrText(dashboardIndicatorSourceCombo_, QStringLiteral("Binance futures")));
    QJsonArray symbols = selectedOrAllListValues(dashboardSymbolList_, true);
    if (symbols.isEmpty()) {
        symbols = stringListJsonArray(TradingBotWindowSupport::pythonSourceDefaultExecutionSymbols(), true);
    }
    QJsonArray intervals = selectedOrAllListValues(dashboardIntervalList_, false);
    if (intervals.isEmpty()) {
        intervals = stringListJsonArray(TradingBotWindowSupport::pythonSourceDefaultExecutionIntervals(), false);
    }
    config.insert(QStringLiteral("symbols"), symbols);
    config.insert(QStringLiteral("intervals"), intervals);
    config.insert(QStringLiteral("runtime_symbol_interval_pairs"), dashboardOverrideRows(dashboardOverridesTable_));
    config.insert(QStringLiteral("position_pct"), dashboardPositionPctSpin_ ? dashboardPositionPctSpin_->value() : 2.0);
    config.insert(QStringLiteral("side"), comboDataOrText(dashboardSideCombo_, QStringLiteral("BOTH")));
    config.insert(QStringLiteral("loop_interval_override"), comboDataOrText(dashboardLoopOverrideCombo_, QStringLiteral("1m")));
    config.insert(QStringLiteral("lead_trader_enabled"), dashboardLeadTraderEnableCheck_ && dashboardLeadTraderEnableCheck_->isChecked());
    config.insert(QStringLiteral("lead_trader_profile"), comboDataOrText(dashboardLeadTraderCombo_));
    config.insert(QStringLiteral("indicator_use_live_values"), dashboardLiveIndicatorValuesCheck_ && dashboardLiveIndicatorValuesCheck_->isChecked());
    config.insert(QStringLiteral("add_only"), dashboardOneWayCheck_ && dashboardOneWayCheck_->isChecked());
    config.insert(QStringLiteral("allow_opposite_positions"), dashboardHedgeStackCheck_ && dashboardHedgeStackCheck_->isChecked());

    const QJsonArray chartSymbols = config.value(QStringLiteral("symbols")).toArray();
    const QJsonArray chartIntervals = config.value(QStringLiteral("intervals")).toArray();
    if (!chartSymbols.isEmpty() && !chartIntervals.isEmpty()) {
        QJsonObject chart;
        chart.insert(QStringLiteral("market"), config.value(QStringLiteral("account_type")));
        chart.insert(QStringLiteral("symbol"), chartSymbols.at(0).toString());
        chart.insert(QStringLiteral("interval"), chartIntervals.at(0).toString());
        chart.insert(QStringLiteral("view_mode"), QStringLiteral("tradingview"));
        chart.insert(QStringLiteral("auto_follow"), true);
        config.insert(QStringLiteral("chart"), chart);
    }

    QJsonObject stopLoss;
    stopLoss.insert(QStringLiteral("enabled"), dashboardStopLossEnableCheck_ && dashboardStopLossEnableCheck_->isChecked());
    stopLoss.insert(QStringLiteral("mode"), comboDataOrText(dashboardStopLossModeCombo_, QStringLiteral("usdt")));
    stopLoss.insert(QStringLiteral("scope"), comboDataOrText(dashboardStopLossScopeCombo_, QStringLiteral("per_trade")));
    stopLoss.insert(QStringLiteral("usdt"), dashboardStopLossUsdtSpin_ ? dashboardStopLossUsdtSpin_->value() : 0.0);
    stopLoss.insert(QStringLiteral("percent"), dashboardStopLossPercentSpin_ ? dashboardStopLossPercentSpin_->value() : 0.0);
    config.insert(QStringLiteral("stop_loss"), stopLoss);
    config.insert(QStringLiteral("indicators"), dashboardIndicatorConfig(dashboardIndicatorChecks_, dashboardIndicatorParams_));

    config.insert(QStringLiteral("llm_enabled"), dashboardLlmEnableCheck_ && dashboardLlmEnableCheck_->isChecked());
    config.insert(QStringLiteral("llm_provider"), llmProviderKey(dashboardLlmProviderCombo_));
    config.insert(QStringLiteral("llm_model"), dashboardLlmModelCombo_ ? dashboardLlmModelCombo_->currentText().trimmed() : QString());
    config.insert(QStringLiteral("llm_base_url"), dashboardLlmBaseUrlEdit_ ? dashboardLlmBaseUrlEdit_->text().trimmed() : QString());
    config.insert(QStringLiteral("llm_api_key_env"), dashboardLlmApiKeyEnvEdit_ ? dashboardLlmApiKeyEnvEdit_->text().trimmed() : QString());
    if (dashboardLlmApiKeyEdit_
        && !dashboardLlmApiKeyEdit_->text().trimmed().isEmpty()
        && dashboardLlmApiKeyEdit_->text().trimmed() != QStringLiteral("********")) {
        config.insert(QStringLiteral("llm_api_key"), dashboardLlmApiKeyEdit_->text().trimmed());
    }
    config.insert(QStringLiteral("llm_use_for"), comboDataOrText(dashboardLlmUseForCombo_, QStringLiteral("advisory")));
    config.insert(QStringLiteral("llm_allow_public_network"), dashboardLlmAllowPublicNetworkCheck_ && dashboardLlmAllowPublicNetworkCheck_->isChecked());
    config.insert(QStringLiteral("llm_reasoning_effort"), comboText(dashboardLlmReasoningCombo_, QStringLiteral("default")));

    if (dashboardApiKey_
        && !dashboardApiKey_->text().trimmed().isEmpty()
        && dashboardApiKey_->text().trimmed() != QStringLiteral("********")) {
        config.insert(QStringLiteral("api_key"), dashboardApiKey_->text().trimmed());
    }
    if (dashboardApiSecret_
        && !dashboardApiSecret_->text().trimmed().isEmpty()
        && dashboardApiSecret_->text().trimmed() != QStringLiteral("********")) {
        config.insert(QStringLiteral("api_secret"), dashboardApiSecret_->text().trimmed());
    }

    return config;
}

bool TradingBotWindow::hydrateDashboardServiceConfig(const QJsonObject &config) {
    if (config.isEmpty()) {
        return false;
    }

    setComboValue(dashboardModeCombo_, config.value(QStringLiteral("mode")));
    setComboValue(dashboardAccountTypeCombo_, config.value(QStringLiteral("account_type")));
    setComboValue(dashboardAccountModeCombo_, config.value(QStringLiteral("account_mode")));
    setComboValue(dashboardMarginModeCombo_, config.value(QStringLiteral("margin_mode")));
    setComboValue(dashboardPositionModeCombo_, config.value(QStringLiteral("position_mode")));
    setComboValue(dashboardAssetsModeCombo_, config.value(QStringLiteral("assets_mode")));
    setComboValue(dashboardConnectorCombo_, config.value(QStringLiteral("connector_backend")));
    setComboValue(dashboardExchangeCombo_, config.value(QStringLiteral("selected_exchange")));
    setComboValue(dashboardThemeCombo_, config.value(QStringLiteral("theme")));
    setComboValue(dashboardIndicatorSourceCombo_, config.value(QStringLiteral("indicator_source")));
    setComboValue(dashboardTimeInForceCombo_, config.value(QStringLiteral("tif")));
    setComboValue(dashboardSideCombo_, config.value(QStringLiteral("side")));
    setComboValue(dashboardLoopOverrideCombo_, config.value(QStringLiteral("loop_interval_override")));
    setComboValue(dashboardLeadTraderCombo_, config.value(QStringLiteral("lead_trader_profile")));

    if (dashboardLeverageSpin_ && config.contains(QStringLiteral("leverage"))) {
        dashboardLeverageSpin_->setValue(config.value(QStringLiteral("leverage")).toInt(dashboardLeverageSpin_->value()));
    }
    if (dashboardGtdMinutesSpin_ && config.contains(QStringLiteral("gtd_minutes"))) {
        dashboardGtdMinutesSpin_->setValue(config.value(QStringLiteral("gtd_minutes")).toInt(dashboardGtdMinutesSpin_->value()));
    }
    if (dashboardPositionPctSpin_ && config.contains(QStringLiteral("position_pct"))) {
        dashboardPositionPctSpin_->setValue(config.value(QStringLiteral("position_pct")).toDouble(dashboardPositionPctSpin_->value()));
    }
    if (dashboardLeadTraderEnableCheck_ && config.contains(QStringLiteral("lead_trader_enabled"))) {
        dashboardLeadTraderEnableCheck_->setChecked(config.value(QStringLiteral("lead_trader_enabled")).toBool(false));
    }
    if (dashboardLeadTraderCombo_) {
        dashboardLeadTraderCombo_->setEnabled(
            !dashboardRuntimeActive_
            && dashboardLeadTraderEnableCheck_
            && dashboardLeadTraderEnableCheck_->isChecked());
    }
    if (dashboardLiveIndicatorValuesCheck_ && config.contains(QStringLiteral("indicator_use_live_values"))) {
        dashboardLiveIndicatorValuesCheck_->setChecked(config.value(QStringLiteral("indicator_use_live_values")).toBool(true));
    }
    if (dashboardOneWayCheck_ && config.contains(QStringLiteral("add_only"))) {
        dashboardOneWayCheck_->setChecked(config.value(QStringLiteral("add_only")).toBool(false));
    }
    if (dashboardHedgeStackCheck_ && config.contains(QStringLiteral("allow_opposite_positions"))) {
        dashboardHedgeStackCheck_->setChecked(config.value(QStringLiteral("allow_opposite_positions")).toBool(true));
    }

    selectListValues(dashboardSymbolList_, config.value(QStringLiteral("symbols")).toArray(), true);
    selectListValues(dashboardIntervalList_, config.value(QStringLiteral("intervals")).toArray(), false);

    const QJsonObject stopLoss = config.value(QStringLiteral("stop_loss")).toObject();
    if (!stopLoss.isEmpty()) {
        if (dashboardStopLossEnableCheck_) {
            dashboardStopLossEnableCheck_->setChecked(stopLoss.value(QStringLiteral("enabled")).toBool(false));
        }
        setComboValue(dashboardStopLossModeCombo_, stopLoss.value(QStringLiteral("mode")));
        setComboValue(dashboardStopLossScopeCombo_, stopLoss.value(QStringLiteral("scope")));
        if (dashboardStopLossUsdtSpin_) {
            dashboardStopLossUsdtSpin_->setValue(stopLoss.value(QStringLiteral("usdt")).toDouble(dashboardStopLossUsdtSpin_->value()));
        }
        if (dashboardStopLossPercentSpin_) {
            dashboardStopLossPercentSpin_->setValue(stopLoss.value(QStringLiteral("percent")).toDouble(dashboardStopLossPercentSpin_->value()));
        }
    }

    const QJsonObject indicators = config.value(QStringLiteral("indicators")).toObject();
    for (auto it = indicators.constBegin(); it != indicators.constEnd(); ++it) {
        QCheckBox *check = dashboardIndicatorChecks_.value(it.key(), nullptr);
        if (!check || !it.value().isObject()) {
            continue;
        }
        const QJsonObject indicator = it.value().toObject();
        if (indicator.contains(QStringLiteral("enabled"))) {
            check->setChecked(indicator.value(QStringLiteral("enabled")).toBool(check->isChecked()));
        }
    }

    if (dashboardOverridesTable_) {
        dashboardOverridesTable_->setRowCount(0);
        const QJsonArray rows = config.value(QStringLiteral("runtime_symbol_interval_pairs")).toArray();
        for (const QJsonValue &value : rows) {
            const QJsonObject row = value.toObject();
            const QString symbol = row.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
            const QString interval = row.value(QStringLiteral("interval")).toString().trimmed();
            if (symbol.isEmpty() || interval.isEmpty()) {
                continue;
            }
            QJsonObject payload = row;
            payload.insert(QStringLiteral("symbol"), symbol);
            payload.insert(QStringLiteral("interval"), interval);
            setDashboardOverridePayloadFromConfig(
                dashboardOverridesTable_,
                dashboardOverridesTable_->rowCount(),
                payload);
        }
    }

    if (dashboardLlmEnableCheck_ && config.contains(QStringLiteral("llm_enabled"))) {
        dashboardLlmEnableCheck_->setChecked(config.value(QStringLiteral("llm_enabled")).toBool(false));
    }
    setComboValue(dashboardLlmProviderCombo_, config.value(QStringLiteral("llm_provider")));
    if (dashboardLlmModelCombo_) {
        setComboTextAllowingCustom(dashboardLlmModelCombo_, config.value(QStringLiteral("llm_model")).toString());
    }
    if (dashboardLlmBaseUrlEdit_ && config.contains(QStringLiteral("llm_base_url"))) {
        dashboardLlmBaseUrlEdit_->setText(config.value(QStringLiteral("llm_base_url")).toString().trimmed());
    }
    if (dashboardLlmApiKeyEnvEdit_ && config.contains(QStringLiteral("llm_api_key_env"))) {
        dashboardLlmApiKeyEnvEdit_->setText(config.value(QStringLiteral("llm_api_key_env")).toString().trimmed());
    }
    if (dashboardLlmApiKeyEdit_) {
        dashboardLlmApiKeyEdit_->setText(config.contains(QStringLiteral("llm_api_key")) ? QStringLiteral("********") : QString());
    }
    setComboValue(dashboardLlmUseForCombo_, config.value(QStringLiteral("llm_use_for")));
    if (dashboardLlmAllowPublicNetworkCheck_ && config.contains(QStringLiteral("llm_allow_public_network"))) {
        dashboardLlmAllowPublicNetworkCheck_->setChecked(config.value(QStringLiteral("llm_allow_public_network")).toBool(false));
    }
    if (dashboardLlmReasoningCombo_) {
        setComboTextAllowingCustom(dashboardLlmReasoningCombo_, config.value(QStringLiteral("llm_reasoning_effort")).toString(QStringLiteral("default")));
    }
    if (dashboardLlmStatusLabel_) {
        dashboardLlmStatusLabel_->setText(QStringLiteral("LLM settings loaded from Python Service API config."));
    }

    if (dashboardApiKey_ && config.contains(QStringLiteral("api_key"))) {
        dashboardApiKey_->setText(config.value(QStringLiteral("api_key")).toString().trimmed().isEmpty() ? QString() : QStringLiteral("********"));
    }
    if (dashboardApiSecret_ && config.contains(QStringLiteral("api_secret"))) {
        dashboardApiSecret_->setText(config.value(QStringLiteral("api_secret")).toString().trimmed().isEmpty() ? QString() : QStringLiteral("********"));
    }

    if (dashboardThemeCombo_) {
        applyDashboardTheme(dashboardThemeCombo_->currentText());
    }
    if (dashboardGtdMinutesSpin_ && dashboardTimeInForceCombo_) {
        dashboardGtdMinutesSpin_->setEnabled(
            !dashboardRuntimeActive_
            && comboDataOrText(dashboardTimeInForceCombo_).compare(QStringLiteral("GTD"), Qt::CaseInsensitive) == 0);
    }
    updateDashboardStopLossWidgetState();
    syncDashboardPaperBalanceUi();
    return true;
}

bool TradingBotWindow::saveDashboardServiceConfig() {
    QJsonObject wrapper;
    wrapper.insert(QStringLiteral("config"), buildDashboardServiceConfigPatch());
    const auto patchResult = TradingBotWindowSupport::serviceApiRequestJson(
        QStringLiteral("PATCH"),
        QStringLiteral("config"),
        wrapper,
        30000);
    if (!patchResult.ok) {
        const QString message = QStringLiteral("Python Service API config patch failed: %1").arg(patchResult.error);
        updateStatusMessage(message);
        appendDashboardAllLog(message);
        return false;
    }

    QJsonObject saveRequest;
    saveRequest.insert(QStringLiteral("source"), QStringLiteral("cpp-desktop"));
    const auto saveResult = TradingBotWindowSupport::serviceApiRequestJson(
        QStringLiteral("POST"),
        QStringLiteral("config_save"),
        saveRequest,
        30000);
    if (!saveResult.ok) {
        const QString message = QStringLiteral("Python Service API config save failed: %1").arg(saveResult.error);
        updateStatusMessage(message);
        appendDashboardAllLog(message);
        return false;
    }

    const QString summary = persistenceSummary(saveResult.document.object());
    updateStatusMessage(
        summary.isEmpty()
            ? QStringLiteral("Dashboard config saved through Python Service API.")
            : QStringLiteral("Dashboard config saved through Python Service API: %1").arg(summary));
    appendDashboardAllLog(QStringLiteral("Dashboard config persisted through Python Service API%1")
        .arg(summary.isEmpty() ? QString() : QStringLiteral(": ") + summary));
    return true;
}

bool TradingBotWindow::loadDashboardServiceConfig() {
    QJsonObject loadRequest;
    loadRequest.insert(QStringLiteral("source"), QStringLiteral("cpp-desktop"));
    const auto loadResult = TradingBotWindowSupport::serviceApiRequestJson(
        QStringLiteral("POST"),
        QStringLiteral("config_load"),
        loadRequest,
        30000);
    if (!loadResult.ok) {
        const QString message = QStringLiteral("Python Service API config load failed: %1").arg(loadResult.error);
        updateStatusMessage(message);
        appendDashboardAllLog(message);
        return false;
    }

    const QJsonObject payload = loadResult.document.object();
    const QJsonObject config = payload.value(QStringLiteral("config")).toObject();
    if (!hydrateDashboardServiceConfig(config)) {
        const QString message = QStringLiteral("Python Service API config load returned no dashboard-compatible config.");
        updateStatusMessage(message);
        appendDashboardAllLog(message);
        return false;
    }

    const QString summary = persistenceSummary(payload.value(QStringLiteral("persistence")).toObject());
    updateStatusMessage(
        summary.isEmpty()
            ? QStringLiteral("Dashboard config loaded through Python Service API.")
            : QStringLiteral("Dashboard config loaded through Python Service API: %1").arg(summary));
    appendDashboardAllLog(QStringLiteral("Dashboard config loaded through Python Service API%1")
        .arg(summary.isEmpty() ? QString() : QStringLiteral(": ") + summary));
    appendDashboardWaitingLog(QStringLiteral("Queue restored from Python Service API config (%1 row(s)).")
        .arg(dashboardOverridesTable_ ? dashboardOverridesTable_->rowCount() : 0));
    return true;
}

void TradingBotWindow::saveDashboardConfig() {
    if (saveDashboardServiceConfig()) {
        return;
    }
    const QMessageBox::StandardButton answer = QMessageBox::question(
        this,
        tr("Save Dashboard Config"),
        tr("Python Service API config save failed. Save a local dashboard override JSON file instead?"));
    if (answer == QMessageBox::Yes) {
        saveDashboardLocalOverrideConfig();
    }
}

void TradingBotWindow::saveDashboardLocalOverrideConfig() {
    if (!dashboardOverridesTable_) {
        return;
    }

    const QString filePath = QFileDialog::getSaveFileName(
        this,
        tr("Save Dashboard Config"),
        QDir::homePath() + QStringLiteral("/dashboard_overrides.json"),
        tr("JSON Files (*.json);;All Files (*)"));
    if (filePath.trimmed().isEmpty()) {
        return;
    }

    QJsonArray rowsJson;
    for (int rowIdx = 0; rowIdx < dashboardOverridesTable_->rowCount(); ++rowIdx) {
        QJsonObject rowObject;
        rowObject.insert(QStringLiteral("symbol"), dashboardOverridesTable_->item(rowIdx, 0)
                ? dashboardOverridesTable_->item(rowIdx, 0)->text()
                : QString());
        rowObject.insert(QStringLiteral("interval"), dashboardOverridesTable_->item(rowIdx, 1)
                ? dashboardOverridesTable_->item(rowIdx, 1)->text()
                : QString());
        rowObject.insert(QStringLiteral("indicators"), dashboardOverridesTable_->item(rowIdx, 2)
                ? dashboardOverridesTable_->item(rowIdx, 2)->text()
                : QString());
        rowObject.insert(QStringLiteral("loop"), dashboardOverridesTable_->item(rowIdx, 3)
                ? dashboardOverridesTable_->item(rowIdx, 3)->text()
                : QString());
        rowObject.insert(QStringLiteral("leverage"), dashboardOverridesTable_->item(rowIdx, 4)
                ? dashboardOverridesTable_->item(rowIdx, 4)->text()
                : QString());
        rowObject.insert(QStringLiteral("connector"), dashboardOverridesTable_->item(rowIdx, 5)
                ? dashboardOverridesTable_->item(rowIdx, 5)->text()
                : QString());
        rowObject.insert(QStringLiteral("strategy_controls"), dashboardOverridesTable_->item(rowIdx, 6)
                ? dashboardOverridesTable_->item(rowIdx, 6)->text()
                : QString());
        rowObject.insert(QStringLiteral("stop_loss"), dashboardOverridesTable_->item(rowIdx, 7)
                ? dashboardOverridesTable_->item(rowIdx, 7)->text()
                : QString());
        rowsJson.append(rowObject);
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("overrides"), rowsJson);
    QJsonObject llmJson;
    if (dashboardLlmProviderCombo_) {
        const QVariantMap providerSpec = dashboardLlmProviderCombo_->currentData().toMap();
        llmJson.insert(QStringLiteral("provider"), providerSpec.value(QStringLiteral("key")).toString());
        llmJson.insert(QStringLiteral("provider_label"), dashboardLlmProviderCombo_->currentText().trimmed());
    }
    if (dashboardLlmEnableCheck_) {
        llmJson.insert(QStringLiteral("enabled"), dashboardLlmEnableCheck_->isChecked());
    }
    if (dashboardLlmModelCombo_) {
        llmJson.insert(QStringLiteral("model"), dashboardLlmModelCombo_->currentText().trimmed());
    }
    if (dashboardLlmReasoningCombo_) {
        llmJson.insert(QStringLiteral("reasoning_effort"), dashboardLlmReasoningCombo_->currentText().trimmed());
    }
    if (dashboardLlmBaseUrlEdit_) {
        llmJson.insert(QStringLiteral("base_url"), dashboardLlmBaseUrlEdit_->text().trimmed());
    }
    if (dashboardLlmApiKeyEnvEdit_) {
        llmJson.insert(QStringLiteral("api_key_env"), dashboardLlmApiKeyEnvEdit_->text().trimmed());
    }
    if (dashboardLlmApiKeyEdit_
        && !dashboardLlmApiKeyEdit_->text().trimmed().isEmpty()
        && dashboardLlmApiKeyEdit_->text().trimmed() != QStringLiteral("********")) {
        llmJson.insert(QStringLiteral("api_key"), dashboardLlmApiKeyEdit_->text().trimmed());
    }
    if (dashboardLlmUseForCombo_) {
        llmJson.insert(QStringLiteral("use_for"), dashboardLlmUseForCombo_->currentData().toString());
    }
    if (dashboardLlmAllowPublicNetworkCheck_) {
        llmJson.insert(QStringLiteral("allow_public_network"), dashboardLlmAllowPublicNetworkCheck_->isChecked());
    }
    payload.insert(QStringLiteral("llm"), llmJson);
    payload.insert(QStringLiteral("saved_at"), QDateTime::currentDateTime().toString(Qt::ISODate));

    QFile out(filePath);
    if (!out.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        QMessageBox::warning(this, tr("Save failed"), tr("Could not write %1").arg(filePath));
        return;
    }

    out.write(QJsonDocument(payload).toJson(QJsonDocument::Indented));
    out.close();

    updateStatusMessage(QStringLiteral("Dashboard config saved: %1").arg(filePath));
    appendDashboardAllLog(QStringLiteral("Dashboard config saved to %1").arg(filePath));
}

void TradingBotWindow::loadDashboardConfig() {
    if (loadDashboardServiceConfig()) {
        return;
    }
    const QMessageBox::StandardButton answer = QMessageBox::question(
        this,
        tr("Load Dashboard Config"),
        tr("Python Service API config load failed. Load a local dashboard override JSON file instead?"));
    if (answer == QMessageBox::Yes) {
        loadDashboardLocalOverrideConfig();
    }
}

void TradingBotWindow::loadDashboardLocalOverrideConfig() {
    if (!dashboardOverridesTable_) {
        return;
    }

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
    const QJsonDocument document = QJsonDocument::fromJson(in.readAll(), &parseError);
    in.close();
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        QMessageBox::warning(this, tr("Load failed"), tr("Invalid JSON file."));
        return;
    }

    const QJsonArray rowsJson = document.object().value(QStringLiteral("overrides")).toArray();
    const QJsonObject llmJson = document.object().value(QStringLiteral("llm")).toObject();
    if (!llmJson.isEmpty()) {
        const QString providerKey = llmJson.value(QStringLiteral("provider")).toString().trimmed();
        if (dashboardLlmProviderCombo_ && !providerKey.isEmpty()) {
            for (int i = 0; i < dashboardLlmProviderCombo_->count(); ++i) {
                const QVariantMap spec = dashboardLlmProviderCombo_->itemData(i).toMap();
                if (spec.value(QStringLiteral("key")).toString().compare(providerKey, Qt::CaseInsensitive) == 0) {
                    dashboardLlmProviderCombo_->setCurrentIndex(i);
                    break;
                }
            }
        }
        if (dashboardLlmEnableCheck_) {
            dashboardLlmEnableCheck_->setChecked(llmJson.value(QStringLiteral("enabled")).toBool(false));
        }
        if (dashboardLlmModelCombo_) {
            dashboardLlmModelCombo_->setCurrentText(llmJson.value(QStringLiteral("model")).toString().trimmed());
        }
        if (dashboardLlmReasoningCombo_) {
            const QString reasoningEffort = llmJson.value(QStringLiteral("reasoning_effort")).toString().trimmed();
            const int idx = dashboardLlmReasoningCombo_->findText(reasoningEffort);
            dashboardLlmReasoningCombo_->setCurrentIndex(idx >= 0 ? idx : 0);
        }
        if (dashboardLlmBaseUrlEdit_) {
            dashboardLlmBaseUrlEdit_->setText(llmJson.value(QStringLiteral("base_url")).toString().trimmed());
        }
        if (dashboardLlmApiKeyEnvEdit_) {
            dashboardLlmApiKeyEnvEdit_->setText(llmJson.value(QStringLiteral("api_key_env")).toString().trimmed());
        }
        if (dashboardLlmApiKeyEdit_) {
            dashboardLlmApiKeyEdit_->setText(llmJson.contains(QStringLiteral("api_key")) ? QStringLiteral("********") : QString());
        }
        if (dashboardLlmUseForCombo_) {
            const QString useFor = llmJson.value(QStringLiteral("use_for")).toString().trimmed();
            const int idx = dashboardLlmUseForCombo_->findData(useFor);
            if (idx >= 0) {
                dashboardLlmUseForCombo_->setCurrentIndex(idx);
            }
        }
        if (dashboardLlmAllowPublicNetworkCheck_) {
            dashboardLlmAllowPublicNetworkCheck_->setChecked(llmJson.value(QStringLiteral("allow_public_network")).toBool(false));
        }
        if (dashboardLlmStatusLabel_) {
            dashboardLlmStatusLabel_->setText(QStringLiteral("LLM settings loaded from dashboard config."));
        }
    }
    dashboardOverridesTable_->setRowCount(0);

    int loadedCount = 0;
    for (const QJsonValue &value : rowsJson) {
        const QJsonObject rowObject = value.toObject();
        const QString symbol = rowObject.value(QStringLiteral("symbol")).toString().trimmed().toUpper();
        const QString interval = rowObject.value(QStringLiteral("interval")).toString().trimmed();
        if (symbol.isEmpty() || interval.isEmpty()) {
            continue;
        }

        const int rowIdx = dashboardOverridesTable_->rowCount();
        dashboardOverridesTable_->insertRow(rowIdx);
        const QStringList values = {
            symbol,
            interval,
            rowObject.value(QStringLiteral("indicators")).toString(),
            rowObject.value(QStringLiteral("loop")).toString(),
            rowObject.value(QStringLiteral("leverage")).toString(),
            rowObject.value(QStringLiteral("connector")).toString(),
            rowObject.value(QStringLiteral("strategy_controls")).toString(),
            rowObject.value(QStringLiteral("stop_loss")).toString(),
        };
        for (int col = 0; col < values.size(); ++col) {
            dashboardOverridesTable_->setItem(rowIdx, col, new QTableWidgetItem(values.at(col)));
        }
        ++loadedCount;
    }

    updateStatusMessage(QStringLiteral("Dashboard config loaded: %1 row(s).").arg(loadedCount));
    appendDashboardAllLog(QStringLiteral("Dashboard config loaded from %1 (%2 row(s)).").arg(filePath).arg(loadedCount));
    appendDashboardWaitingLog(QStringLiteral("Queue restored with %1 row(s).").arg(loadedCount));
}
