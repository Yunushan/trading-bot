#include "TradingBotWindow.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QListWidget>
#include <QMessageBox>
#include <QSpinBox>
#include <QStringList>
#include <QTableWidget>
#include <QTableWidgetItem>

#include <algorithm>

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

void TradingBotWindow::saveDashboardConfig() {
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
