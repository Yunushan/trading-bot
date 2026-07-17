#include "TradingBotWindow.h"
#include "NativeOrderSafety.h"
#include "TradingBotWindow.dashboard_runtime_shared.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QDoubleSpinBox>
#include <QJsonObject>
#include <QLabel>
#include <QPushButton>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTextEdit>
#include <QWidget>

#include <algorithm>

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

void TradingBotWindow::refreshDashboardOrderAuditStatus() {
    if (!dashboardOrderAuditStatusLabel_) {
        return;
    }
    const QJsonObject status = NativeOrderSafety::currentOrderAuditStatus(
        TradingBotWindowDashboardRuntime::nativeRuntimeOrderAuditLogConfig());
    const QString state = status.value(QStringLiteral("state")).toString(QStringLiteral("unknown")).trimmed();
    const QString path = status.value(QStringLiteral("path")).toString(NativeOrderSafety::defaultOrderAuditPath()).trimmed();
    const QString lastOk = status.value(QStringLiteral("last_write_ok_at")).toString().trimmed();
    const QJsonObject lastError = status.value(QStringLiteral("last_write_error")).toObject();
    const QString errorMessage = lastError.value(QStringLiteral("message")).toString().trimmed();
    const bool enabled = status.value(QStringLiteral("enabled")).toBool(true);
    const bool writeOk = status.value(QStringLiteral("write_ok")).toBool(true);

    QString detail = path.isEmpty() ? QStringLiteral("path unavailable") : path;
    if (!errorMessage.isEmpty()) {
        detail = QStringLiteral("%1 | %2").arg(detail, errorMessage);
    } else if (!lastOk.isEmpty()) {
        detail = QStringLiteral("%1 | last write %2").arg(detail, lastOk);
    }
    dashboardOrderAuditStatusLabel_->setText(
        QStringLiteral("Order audit: %1 | %2").arg(state.isEmpty() ? QStringLiteral("unknown") : state, detail));
    dashboardOrderAuditStatusLabel_->setToolTip(
        QStringLiteral("Order audit JSONL path: %1\nMax bytes: %2\nBackups: %3")
            .arg(path,
                 QString::number(status.value(QStringLiteral("max_bytes")).toVariant().toLongLong()),
                 QString::number(status.value(QStringLiteral("backup_count")).toInt())));
    const QString color = !enabled
        ? QStringLiteral("#f59e0b")
        : (!writeOk || state == QStringLiteral("write_failed"))
            ? QStringLiteral("#ef4444")
            : QStringLiteral("#22c55e");
    dashboardOrderAuditStatusLabel_->setStyleSheet(QStringLiteral("color: %1; font-weight: 700;").arg(color));
}

void TradingBotWindow::appendDashboardAllLog(const QString &message) {
    if (!dashboardAllLogsEdit_) {
        return;
    }
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    dashboardAllLogsEdit_->append(QString("%1 %2").arg(ts, message));
    refreshDashboardOrderAuditStatus();
}

void TradingBotWindow::appendDashboardPositionLog(const QString &message) {
    const QString ts = QDateTime::currentDateTime().toString("[dd.MM.yyyy HH:mm:ss]");
    if (dashboardPositionLogsEdit_) {
        dashboardPositionLogsEdit_->append(QString("%1 %2").arg(ts, message));
    }
    if (dashboardAllLogsEdit_) {
        dashboardAllLogsEdit_->append(QString("%1 [Position] %2").arg(ts, message));
    }
    refreshDashboardOrderAuditStatus();
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
