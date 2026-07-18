#include "TradingBotWindow.h"
#include "NativeBacktestBatchRuntime.h"
#include "TradingBotWindowSupport.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QComboBox>
#include <QCoreApplication>
#include <QDate>
#include <QDateEdit>
#include <QDateTime>
#include <QDoubleSpinBox>
#include <QEventLoop>
#include <QFontMetrics>
#include <QFormLayout>
#include <QGroupBox>
#include <QGridLayout>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QItemSelectionModel>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QScrollArea>
#include <QSpinBox>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTimer>
#include <QTime>
#include <QVariant>
#include <QVBoxLayout>
#include <QtConcurrent>

#include <algorithm>

namespace {

QJsonArray stringArray(const QStringList &values) {
    QJsonArray array;
    for (const QString &value : values) {
        const QString clean = value.trimmed();
        if (!clean.isEmpty()) {
            array.append(clean);
        }
    }
    return array;
}

QStringList selectedListValues(const QListWidget *list) {
    QStringList values;
    if (!list) {
        return values;
    }
    for (const auto *item : list->selectedItems()) {
        if (!item) {
            continue;
        }
        const QString value = item->text().trimmed();
        if (!value.isEmpty()) {
            values.push_back(value);
        }
    }
    values.removeDuplicates();
    return values;
}

QStringList allListValues(const QListWidget *list) {
    QStringList values;
    if (!list) return values;
    for (int index = 0; index < list->count(); ++index) {
        const auto *item = list->item(index);
        if (!item) continue;
        const QString value = item->text().trimmed();
        if (!value.isEmpty() && !values.contains(value)) values.append(value);
    }
    return values;
}

QString comboValue(const QComboBox *combo, const QString &fallback = {}) {
    if (!combo) {
        return fallback;
    }
    const QString data = combo->currentData().toString().trimmed();
    if (!data.isEmpty()) {
        return data;
    }
    const QString text = combo->currentText().trimmed();
    return text.isEmpty() ? fallback : text;
}

double doubleSpinValue(const QDoubleSpinBox *spin, double fallback) {
    return spin ? spin->value() : fallback;
}

int spinValue(const QSpinBox *spin, int fallback) {
    return spin ? spin->value() : fallback;
}

QString jsonText(const QJsonObject &object, const QString &key, const QString &fallback = {}) {
    const QJsonValue value = object.value(key);
    if (value.isString()) {
        const QString text = value.toString().trimmed();
        return text.isEmpty() ? fallback : text;
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'f', 2);
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    return fallback;
}

QString jsonValueText(const QJsonValue &value, const QString &fallback = {}) {
    if (value.isString()) {
        const QString text = value.toString().trimmed();
        return text.isEmpty() ? fallback : text;
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'f', 2);
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    return fallback;
}

double jsonNumber(const QJsonObject &object, const QString &key, double fallback = 0.0) {
    const QJsonValue value = object.value(key);
    if (value.isDouble()) {
        return value.toDouble();
    }
    if (value.isString()) {
        bool ok = false;
        const double parsed = value.toString().toDouble(&ok);
        if (ok) {
            return parsed;
        }
    }
    return fallback;
}

bool jsonBool(const QJsonObject &object, const QString &key, bool fallback = false) {
    const QJsonValue value = object.value(key);
    if (value.isBool()) {
        return value.toBool();
    }
    if (value.isDouble()) {
        return value.toDouble() != 0.0;
    }
    if (value.isString()) {
        const QString text = value.toString().trimmed().toLower();
        if (text == QStringLiteral("true") || text == QStringLiteral("1") || text == QStringLiteral("yes") || text == QStringLiteral("on")) {
            return true;
        }
        if (text == QStringLiteral("false") || text == QStringLiteral("0") || text == QStringLiteral("no") || text == QStringLiteral("off") || text.isEmpty()) {
            return false;
        }
    }
    return fallback;
}

QString jsonNumberText(const QJsonObject &object, const QString &key, int decimals = 2, const QString &suffix = {}) {
    return QStringLiteral("%1%2").arg(QString::number(jsonNumber(object, key), 'f', decimals), suffix);
}

QString positionPercentText(const QJsonObject &row) {
    const QString display = jsonText(row, QStringLiteral("position_pct_display")).trimmed();
    if (!display.isEmpty()) {
        return display.contains(QLatin1Char('%')) ? display : display + QLatin1Char('%');
    }

    double percent = jsonNumber(row, QStringLiteral("position_pct"), 0.0);
    const QString units = jsonText(row, QStringLiteral("position_pct_units"), QStringLiteral("percent"))
                              .trimmed()
                              .toLower();
    if (QStringList{QStringLiteral("fraction"), QStringLiteral("decimal"), QStringLiteral("ratio")}.contains(units)) {
        percent *= 100.0;
    }
    return QStringLiteral("%1%").arg(QString::number(percent, 'f', 2));
}

QString jsonIntText(const QJsonObject &object, const QString &key) {
    return QString::number(static_cast<int>(jsonNumber(object, key)));
}

QString jsonStringArrayText(const QJsonObject &object, const QString &key, const QString &fallback = {}) {
    QStringList values;
    for (const QJsonValue &value : object.value(key).toArray()) {
        const QString text = value.toString().trimmed();
        if (!text.isEmpty()) {
            values.push_back(text);
        }
    }
    return values.isEmpty() ? fallback : values.join(QStringLiteral(", "));
}

QJsonArray jsonStringArrayValue(const QJsonValue &rawValue) {
    QJsonArray values;
    if (rawValue.isArray()) {
        for (const QJsonValue &value : rawValue.toArray()) {
            const QString text = jsonValueText(value).trimmed();
            if (!text.isEmpty()) {
                values.append(text);
            }
        }
    } else if (rawValue.isString()) {
        const QStringList parts = rawValue.toString().split(',', Qt::SkipEmptyParts);
        for (const QString &part : parts) {
            const QString text = part.trimmed();
            if (!text.isEmpty()) {
                values.append(text);
            }
        }
    }
    return values;
}

QJsonArray backtestIndicatorKeys(const QJsonObject &row) {
    QJsonArray indicators = jsonStringArrayValue(row.value(QStringLiteral("indicator_keys")));
    if (indicators.isEmpty()) {
        indicators = jsonStringArrayValue(row.value(QStringLiteral("indicators")));
    }
    if (indicators.isEmpty()) {
        indicators = jsonStringArrayValue(row.value(QStringLiteral("indicator")));
    }
    return indicators;
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

QString stopLossSummary(const QJsonObject &row) {
    const bool enabled = row.value(QStringLiteral("stop_loss_enabled")).toBool(false);
    if (!enabled) {
        return QStringLiteral("Disabled");
    }
    const QString mode = jsonText(row, QStringLiteral("stop_loss_mode"), QStringLiteral("usdt"));
    const QString scope = jsonText(row, QStringLiteral("stop_loss_scope"), QStringLiteral("per_trade"));
    const QString usdt = jsonNumberText(row, QStringLiteral("stop_loss_usdt"), 2, QStringLiteral(" USDT"));
    const QString percent = jsonNumberText(row, QStringLiteral("stop_loss_percent"), 2, QStringLiteral("%"));
    return QStringLiteral("Enabled (%1 | %2 | %3 | %4)").arg(mode, scope, usdt, percent);
}

QJsonObject stopLossFromBacktestResult(const QJsonObject &row) {
    const QJsonObject direct = row.value(QStringLiteral("stop_loss")).toObject();
    if (!direct.isEmpty()) {
        return direct;
    }
    const QStringList keys = {
        QStringLiteral("stop_loss_enabled"),
        QStringLiteral("stop_loss_mode"),
        QStringLiteral("stop_loss_scope"),
        QStringLiteral("stop_loss_usdt"),
        QStringLiteral("stop_loss_percent"),
    };
    bool hasStopLossPayload = false;
    for (const QString &key : keys) {
        if (row.contains(key)) {
            hasStopLossPayload = true;
            break;
        }
    }
    if (!hasStopLossPayload) {
        return {};
    }

    QJsonObject stopLoss;
    stopLoss.insert(QStringLiteral("enabled"), jsonBool(row, QStringLiteral("stop_loss_enabled"), false));
    stopLoss.insert(QStringLiteral("mode"), jsonText(row, QStringLiteral("stop_loss_mode"), QStringLiteral("usdt")).toLower());
    stopLoss.insert(QStringLiteral("scope"), jsonText(row, QStringLiteral("stop_loss_scope"), QStringLiteral("per_trade")).toLower());
    stopLoss.insert(QStringLiteral("usdt"), jsonNumber(row, QStringLiteral("stop_loss_usdt"), 0.0));
    stopLoss.insert(QStringLiteral("percent"), jsonNumber(row, QStringLiteral("stop_loss_percent"), 0.0));
    return stopLoss;
}

QString stopLossObjectSummary(const QJsonObject &stopLoss) {
    if (stopLoss.isEmpty() || !stopLoss.value(QStringLiteral("enabled")).toBool(false)) {
        return QStringLiteral("Disabled");
    }
    const QString mode = jsonText(stopLoss, QStringLiteral("mode"), QStringLiteral("usdt"));
    const QString scope = jsonText(stopLoss, QStringLiteral("scope"), QStringLiteral("per_trade"));
    const QString usdt = jsonNumberText(stopLoss, QStringLiteral("usdt"), 2, QStringLiteral(" USDT"));
    const QString percent = jsonNumberText(stopLoss, QStringLiteral("percent"), 2, QStringLiteral("%"));
    return QStringLiteral("Enabled (%1 | %2 | %3 | %4)").arg(mode, scope, usdt, percent);
}

bool backtestSnapshotActive(const QJsonObject &snapshot) {
    const QString state = jsonText(snapshot, QStringLiteral("state")).toLower();
    return state == QStringLiteral("queued") || state == QStringLiteral("running") || state == QStringLiteral("starting");
}

bool backtestSnapshotCancelled(const QJsonObject &snapshot) {
    const QString state = jsonText(snapshot, QStringLiteral("state")).toLower();
    return state == QStringLiteral("cancelled") || snapshot.value(QStringLiteral("cancelled")).toBool(false);
}

QString backtestSnapshotStatusText(const QJsonObject &snapshot, const QString &fallback) {
    QString message = jsonText(snapshot, QStringLiteral("status_message"), fallback);
    const double progress = jsonNumber(snapshot, QStringLiteral("progress_percent"), -1.0);
    if (progress >= 0.0) {
        message = QStringLiteral("%1 (%2%)").arg(message, QString::number(progress, 'f', 1));
    }
    if (backtestSnapshotCancelled(snapshot) && !message.toLower().contains(QStringLiteral("cancel"))) {
        message = QStringLiteral("Backtest cancelled. %1").arg(message);
    }
    return message;
}

QJsonObject cleanBacktestResultMetadata(const QJsonObject &row) {
    const QStringList metadataKeys = {
        QStringLiteral("symbol"),
        QStringLiteral("interval"),
        QStringLiteral("indicator_keys"),
        QStringLiteral("logic"),
        QStringLiteral("trades"),
        QStringLiteral("roi_value"),
        QStringLiteral("roi_percent"),
        QStringLiteral("max_drawdown_percent"),
        QStringLiteral("max_drawdown_value"),
        QStringLiteral("max_drawdown_during_percent"),
        QStringLiteral("max_drawdown_during_value"),
        QStringLiteral("max_drawdown_result_percent"),
        QStringLiteral("max_drawdown_result_value"),
        QStringLiteral("mdd_logic"),
        QStringLiteral("mdd_logic_display"),
        QStringLiteral("start"),
        QStringLiteral("start_display"),
        QStringLiteral("end"),
        QStringLiteral("end_display"),
        QStringLiteral("side"),
        QStringLiteral("capital"),
        QStringLiteral("position_pct"),
        QStringLiteral("position_pct_display"),
        QStringLiteral("position_pct_units"),
        QStringLiteral("leverage"),
        QStringLiteral("leverage_display"),
        QStringLiteral("margin_mode"),
        QStringLiteral("position_mode"),
        QStringLiteral("assets_mode"),
        QStringLiteral("account_mode"),
        QStringLiteral("stop_loss_enabled"),
        QStringLiteral("stop_loss_mode"),
        QStringLiteral("stop_loss_scope"),
        QStringLiteral("stop_loss_usdt"),
        QStringLiteral("stop_loss_percent"),
        QStringLiteral("stop_loss_display"),
        QStringLiteral("loop_interval_override"),
        QStringLiteral("connector_backend"),
        QStringLiteral("strategy_controls"),
        QStringLiteral("optimizer_rank"),
        QStringLiteral("optimizer_metric"),
        QStringLiteral("optimizer_primary_score"),
        QStringLiteral("optimizer_eligible"),
        QStringLiteral("optimizer_mode"),
        QStringLiteral("optimizer_scope"),
        QStringLiteral("optimizer_mdd_limit"),
        QStringLiteral("optimizer_min_trades"),
        QStringLiteral("optimizer_candidate_count"),
        QStringLiteral("optimizer_eligible_count"),
        QStringLiteral("optimizer_filtered_count"),
        QStringLiteral("optimizer_run_count"),
        QStringLiteral("source"),
    };

    QJsonObject metadata;
    for (const QString &key : metadataKeys) {
        const QJsonValue value = row.value(key);
        if (!value.isUndefined() && !value.isNull()) {
            metadata.insert(key, value);
        }
    }
    if (!metadata.contains(QStringLiteral("source"))) {
        metadata.insert(QStringLiteral("source"), QStringLiteral("python-backtest"));
    }
    return metadata;
}

QJsonObject strategyControlsFromBacktestResult(const QJsonObject &row) {
    QJsonObject controls = row.value(QStringLiteral("strategy_controls")).toObject();
    const auto insertTextIfPresent = [&controls, &row](const QString &sourceKey, const QString &targetKey) {
        const QString text = jsonText(row, sourceKey).trimmed();
        if (!text.isEmpty() && !controls.contains(targetKey)) {
            controls.insert(targetKey, text);
        }
    };

    insertTextIfPresent(QStringLiteral("side"), QStringLiteral("side"));
    insertTextIfPresent(QStringLiteral("position_pct_units"), QStringLiteral("position_pct_units"));
    insertTextIfPresent(QStringLiteral("loop_interval_override"), QStringLiteral("loop_interval_override"));
    insertTextIfPresent(QStringLiteral("account_mode"), QStringLiteral("account_mode"));
    insertTextIfPresent(QStringLiteral("connector_backend"), QStringLiteral("connector_backend"));
    insertTextIfPresent(QStringLiteral("margin_mode"), QStringLiteral("margin_mode"));
    insertTextIfPresent(QStringLiteral("position_mode"), QStringLiteral("position_mode"));
    insertTextIfPresent(QStringLiteral("assets_mode"), QStringLiteral("assets_mode"));

    if (row.contains(QStringLiteral("position_pct")) && !controls.contains(QStringLiteral("position_pct"))) {
        controls.insert(QStringLiteral("position_pct"), jsonNumber(row, QStringLiteral("position_pct"), 0.0));
    }
    if (row.contains(QStringLiteral("leverage")) && !controls.contains(QStringLiteral("leverage"))) {
        controls.insert(QStringLiteral("leverage"), static_cast<int>(std::max(1.0, jsonNumber(row, QStringLiteral("leverage"), 1.0))));
    }
    const QJsonObject stopLoss = stopLossFromBacktestResult(row);
    if (!stopLoss.isEmpty() && !controls.contains(QStringLiteral("stop_loss"))) {
        controls.insert(QStringLiteral("stop_loss"), stopLoss);
    }
    return controls;
}

QJsonObject dashboardOverridePayloadFromBacktestResult(const QJsonObject &row) {
    QJsonObject payload;
    const QString symbol = jsonText(row, QStringLiteral("symbol")).toUpper();
    const QString interval = jsonText(row, QStringLiteral("interval"));
    if (symbol.isEmpty() || interval.isEmpty()) {
        return payload;
    }

    payload.insert(QStringLiteral("symbol"), symbol);
    payload.insert(QStringLiteral("interval"), interval);
    const QJsonArray indicators = backtestIndicatorKeys(row);
    if (!indicators.isEmpty()) {
        payload.insert(QStringLiteral("indicators"), indicators);
    }
    const QJsonObject metadata = cleanBacktestResultMetadata(row);
    if (!metadata.isEmpty()) {
        payload.insert(QStringLiteral("backtest_result"), metadata);
    }
    const QJsonObject controls = strategyControlsFromBacktestResult(row);
    if (!controls.isEmpty()) {
        payload.insert(QStringLiteral("strategy_controls"), controls);
    }
    const QJsonObject stopLoss = stopLossFromBacktestResult(row);
    if (!stopLoss.isEmpty()) {
        payload.insert(QStringLiteral("stop_loss"), stopLoss);
    }
    if (row.contains(QStringLiteral("loop_interval_override"))) {
        payload.insert(QStringLiteral("loop_interval_override"), jsonText(row, QStringLiteral("loop_interval_override")));
    }
    if (row.contains(QStringLiteral("leverage"))) {
        payload.insert(QStringLiteral("leverage"), static_cast<int>(std::max(1.0, jsonNumber(row, QStringLiteral("leverage"), 1.0))));
    }
    return payload;
}

QJsonObject dashboardOverridePayloadFromTableRow(const QTableWidget *table, int row) {
    if (!table || row < 0 || row >= table->rowCount()) {
        return {};
    }
    const QTableWidgetItem *symbolItem = table->item(row, 0);
    if (symbolItem) {
        const QJsonObject payload = symbolItem->data(Qt::UserRole).toJsonObject();
        if (!payload.isEmpty()) {
            return payload;
        }
    }
    QJsonObject payload;
    const QTableWidgetItem *intervalItem = table->item(row, 1);
    const QString symbol = symbolItem ? symbolItem->text().trimmed().toUpper() : QString();
    const QString interval = intervalItem ? intervalItem->text().trimmed() : QString();
    if (!symbol.isEmpty() && !interval.isEmpty()) {
        payload.insert(QStringLiteral("symbol"), symbol);
        payload.insert(QStringLiteral("interval"), interval);
    }
    return payload;
}

QJsonObject backtestResultPayloadFromTableRow(const QTableWidget *table, int row) {
    if (!table || row < 0 || row >= table->rowCount()) {
        return {};
    }
    if (const QTableWidgetItem *symbolItem = table->item(row, 0)) {
        const QJsonObject payload = symbolItem->data(Qt::UserRole).toJsonObject();
        if (!payload.isEmpty()) {
            return payload;
        }
    }

    QJsonObject payload;
    const QStringList keys = {
        QStringLiteral("symbol"),
        QStringLiteral("interval"),
        QStringLiteral("logic"),
        QStringLiteral("indicator_keys"),
        QStringLiteral("trades"),
        QStringLiteral("loop_interval_override"),
        QStringLiteral("start"),
        QStringLiteral("end"),
        QStringLiteral("position_pct"),
        QStringLiteral("stop_loss_display"),
        QStringLiteral("margin_mode"),
        QStringLiteral("position_mode"),
        QStringLiteral("assets_mode"),
        QStringLiteral("account_mode"),
        QStringLiteral("leverage_display"),
        QStringLiteral("roi_value"),
        QStringLiteral("roi_percent"),
        QStringLiteral("max_drawdown_during_value"),
        QStringLiteral("max_drawdown_during_percent"),
        QStringLiteral("max_drawdown_result_value"),
        QStringLiteral("max_drawdown_result_percent"),
    };
    for (int col = 0; col < keys.size() && col < table->columnCount(); ++col) {
        const QTableWidgetItem *item = table->item(row, col);
        if (item) {
            payload.insert(keys.at(col), item->text().trimmed());
        }
    }
    return payload;
}

QString dashboardOverrideKey(const QJsonObject &payload) {
    const QJsonObject controls = payload.value(QStringLiteral("strategy_controls")).toObject();
    const QString leverage = payload.contains(QStringLiteral("leverage"))
        ? jsonValueText(payload.value(QStringLiteral("leverage")))
        : jsonValueText(controls.value(QStringLiteral("leverage")));
    return QStringList{
        jsonText(payload, QStringLiteral("symbol")).toUpper(),
        jsonText(payload, QStringLiteral("interval")),
        jsonArrayText(payload.value(QStringLiteral("indicators")).toArray()),
        leverage,
    }.join(QStringLiteral("|"));
}

QString strategyControlsSummary(const QJsonObject &controls) {
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
        const QString text = jsonValueText(controls.value(key)).trimmed();
        if (!text.isEmpty()) {
            parts.append(QStringLiteral("%1 %2").arg(key, text));
        }
    }
    return parts.isEmpty() ? QStringLiteral("Default") : parts.join(QStringLiteral(" | "));
}

void setDashboardOverridePayload(QTableWidget *table, int row, const QJsonObject &payload) {
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
        jsonText(payload, QStringLiteral("symbol")),
        jsonText(payload, QStringLiteral("interval")),
        jsonArrayText(payload.value(QStringLiteral("indicators")).toArray(), QStringLiteral("None")),
        jsonText(payload, QStringLiteral("loop_interval_override"), jsonText(controls, QStringLiteral("loop_interval_override"), QStringLiteral("Default"))),
        payload.contains(QStringLiteral("leverage"))
            ? jsonValueText(payload.value(QStringLiteral("leverage")))
            : jsonValueText(controls.value(QStringLiteral("leverage")), QStringLiteral("Default")),
        jsonText(controls, QStringLiteral("connector_backend"), QStringLiteral("Default")),
        strategyControlsSummary(controls),
        stopLossObjectSummary(stopLoss),
    };
    for (int col = 0; col < values.size(); ++col) {
        auto *item = new QTableWidgetItem(values.at(col));
        if (col == 0) {
            item->setData(Qt::UserRole, payload);
        }
        table->setItem(row, col, item);
    }
}

int appendBacktestRows(QTableWidget *table, const QJsonObject &snapshot, const QString &loopIntervalLabel) {
    if (!table) {
        return 0;
    }
    QJsonArray rows = snapshot.value(QStringLiteral("top_runs")).toArray();
    if (rows.isEmpty()) {
        rows = snapshot.value(QStringLiteral("runs")).toArray();
    }

    int added = 0;
    for (const QJsonValue &value : rows) {
        const QJsonObject row = value.toObject();
        if (row.isEmpty()) {
            continue;
        }
        const int currentRow = table->rowCount();
        table->insertRow(currentRow);
        const QStringList values = {
            jsonText(row, QStringLiteral("symbol")),
            jsonText(row, QStringLiteral("interval")),
            jsonText(row, QStringLiteral("logic")),
            jsonStringArrayText(row, QStringLiteral("indicator_keys")),
            jsonIntText(row, QStringLiteral("trades")),
            jsonText(row, QStringLiteral("loop_interval_override"), loopIntervalLabel),
            jsonText(row, QStringLiteral("start")),
            jsonText(row, QStringLiteral("end")),
            positionPercentText(row),
            stopLossSummary(row),
            jsonText(row, QStringLiteral("margin_mode")),
            jsonText(row, QStringLiteral("position_mode")),
            jsonText(row, QStringLiteral("assets_mode")),
            jsonText(row, QStringLiteral("account_mode")),
            jsonNumberText(row, QStringLiteral("leverage"), 0, QStringLiteral("x")),
            jsonNumberText(row, QStringLiteral("roi_value")),
            jsonNumberText(row, QStringLiteral("roi_percent"), 2, QStringLiteral("%")),
            jsonNumberText(row, QStringLiteral("max_drawdown_during_value")),
            jsonNumberText(row, QStringLiteral("max_drawdown_during_percent"), 2, QStringLiteral("%")),
            jsonNumberText(row, QStringLiteral("max_drawdown_result_value")),
            jsonNumberText(row, QStringLiteral("max_drawdown_result_percent"), 2, QStringLiteral("%")),
        };
        for (int col = 0; col < values.size() && col < table->columnCount(); ++col) {
            auto *item = new QTableWidgetItem(values.at(col));
            if (col == 0) {
                item->setData(Qt::UserRole, row);
            }
            table->setItem(currentRow, col, item);
        }
        ++added;
    }
    return added;
}

} // namespace

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
    const bool isTestnet = dashboardModeCombo_
        ? TradingBotWindowSupport::isTestnetModeLabel(dashboardModeCombo_->currentText())
        : false;
    const QString selectedExchange = TradingBotWindowSupport::selectedDashboardExchange(dashboardExchangeCombo_);
    if (!TradingBotWindowSupport::exchangeUsesBinanceApi(selectedExchange)) {
        const auto serviceResult = TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("GET"), QStringLiteral("config"), {}, 10000);
        if (!serviceResult.ok) {
            updateStatusMessage(
                QStringLiteral("Python Service API symbol request failed for %1: %2")
                    .arg(selectedExchange, serviceResult.error));
            resetButton();
            return;
        }
        QJsonObject payload = serviceResult.document.object();
        if (payload.value(QStringLiteral("config")).isObject()) {
            payload = payload.value(QStringLiteral("config")).toObject();
        }
        QStringList configuredSymbols;
        for (const QJsonValue &value : payload.value(QStringLiteral("symbols")).toArray()) {
            const QString symbol = value.toString().trimmed().toUpper();
            if (!symbol.isEmpty() && !configuredSymbols.contains(symbol)) {
                configuredSymbols.push_back(symbol);
            }
        }
        if (configuredSymbols.isEmpty()) {
            updateStatusMessage(
                QStringLiteral("Python Service API has no configured backtest symbols for %1.").arg(selectedExchange));
            resetButton();
            return;
        }
        symbolList_->clear();
        symbolList_->addItems(configuredSymbols);
        bool anySelected = false;
        for (int i = 0; i < symbolList_->count(); ++i) {
            auto *item = symbolList_->item(i);
            if (item && previousSelections.contains(item->text().trimmed().toUpper())) {
                item->setSelected(true);
                anySelected = true;
            }
        }
        if (!anySelected && symbolList_->count() > 0) {
            symbolList_->item(0)->setSelected(true);
        }
        updateStatusMessage(
            QStringLiteral("Loaded %1 %2 symbols from the canonical Python Service API configuration for backtest.")
                .arg(configuredSymbols.size())
                .arg(selectedExchange));
        resetButton();
        return;
    }
    const QString connectorText = backtestConnectorCombo_
        ? backtestConnectorCombo_->currentText().trimmed()
        : TradingBotWindowSupport::connectorLabelForKey(TradingBotWindowSupport::recommendedConnectorKey(futures));
    const TradingBotWindowSupport::ConnectorRuntimeConfig connectorCfg =
        TradingBotWindowSupport::resolveConnectorConfig(connectorText, futures);
    if (!connectorCfg.ok()) {
        updateStatusMessage(QString("Backtest symbols: connector error: %1").arg(connectorCfg.error));
        if (symbolList_->count() == 0) {
            symbolList_->addItems(TradingBotWindowSupport::placeholderSymbolsForExchange(QStringLiteral("Binance"), futures));
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
            symbolList_->addItems(TradingBotWindowSupport::placeholderSymbolsForExchange(QStringLiteral("Binance"), futures));
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
    resumeBacktestButton_ = new QPushButton("Resume Optimizer", outputGroup);
    resumeBacktestButton_->setEnabled(false);
    resumeBacktestButton_->setToolTip(
        "Available after the Python Service API saves an optimizer time-budget checkpoint.");
    controlsLayout->addWidget(resumeBacktestButton_);
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

void TradingBotWindow::handleRunBacktest() {
    startBacktest(false);
}

void TradingBotWindow::setBacktestRunningUi(bool running) {
    const QString statusText = running ? QStringLiteral("Bot Status: ON") : QStringLiteral("Bot Status: OFF");
    const QString statusStyle = running
        ? QStringLiteral("color: #16a34a; font-weight: 700;")
        : QStringLiteral("color: #ef4444; font-weight: 700;");
    const QString activeTimeText = running ? QStringLiteral("Bot Active Time: 0s") : QStringLiteral("Bot Active Time: --");
    if (running) botStart_ = std::chrono::steady_clock::now();
    ensureBotTimer(running);
    const QList<QLabel *> statusLabels = {
        botStatusLabel_,
        chartBotStatusLabel_,
        positionsBotStatusLabel_,
        codeBotStatusLabel_,
    };
    for (QLabel *label : statusLabels) {
        if (!label) continue;
        label->setText(statusText);
        label->setStyleSheet(statusStyle);
    }
    const QList<QLabel *> timeLabels = {
        botTimeLabel_,
        chartBotTimeLabel_,
        positionsBotTimeLabel_,
        codeBotTimeLabel_,
    };
    for (QLabel *label : timeLabels) {
        if (label) label->setText(activeTimeText);
    }
    if (runButton_) runButton_->setEnabled(!running);
    if (stopButton_) stopButton_->setEnabled(running);
    if (resumeBacktestButton_) {
        resumeBacktestButton_->setEnabled(
            !running && resumeBacktestButton_->property("checkpointAvailable").toBool());
    }
    if (backtestExecutionBackendCombo_) backtestExecutionBackendCombo_->setEnabled(!running);
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::startBacktest(bool optimizerRequested) {
    if (backtestFutureWatcher_ && backtestFutureWatcher_->isRunning()) {
        updateStatusMessage(QStringLiteral("A native C++ backtest is already running."));
        return;
    }
    if (resumeBacktestButton_) {
        resumeBacktestButton_->setProperty("checkpointAvailable", false);
        resumeBacktestButton_->setEnabled(false);
    }

    const QString backend = comboValue(backtestExecutionBackendCombo_, QStringLiteral("local")).toLower();
    const QString selectedExchange = TradingBotWindowSupport::selectedDashboardExchange(dashboardExchangeCombo_);
    const bool nativeBinanceBacktest = TradingBotWindowSupport::exchangeUsesBinanceApi(selectedExchange);
    const QString optimizerMode = optimizerRequested
        ? comboValue(backtestOptimizerModeCombo_, QStringLiteral("current"))
        : QStringLiteral("current");
    const QString scanScope = optimizerRequested
        ? comboValue(backtestScanScopeCombo_, QStringLiteral("selected"))
        : QStringLiteral("selected");
    const QStringList selectedSymbols = selectedListValues(symbolList_);
    const QStringList loadedSymbols = allListValues(symbolList_);
    QStringList symbols = selectedSymbols;
    if (scanScope == QStringLiteral("top_n")) {
        symbols = loadedSymbols.mid(0, spinValue(backtestScanTopNSpin_, 200));
    } else if (scanScope == QStringLiteral("all_loaded")) {
        symbols = loadedSymbols;
    }
    const QStringList intervals = selectedListValues(intervalList_);
    if (symbols.isEmpty() || intervals.isEmpty()) {
        updateStatusMessage(QStringLiteral("Select at least one symbol and interval before running a backtest."));
        return;
    }

    NativeIndicatorRuntime::ConfigMap selectedIndicatorConfigs;
    const QMap<QString, QJsonObject> sourceIndicatorConfigs =
        TradingBotWindowSupport::pythonSourceBacktestIndicatorConfigs();
    QJsonArray indicators;
    for (const QString &key : TradingBotWindowSupport::pythonSourceIndicatorKeys()) {
        const auto *check = backtestIndicatorChecks_.value(key, nullptr);
        if (!check || !check->isChecked()) {
            continue;
        }
        QJsonObject params = sourceIndicatorConfigs.value(key);
        params.insert(QStringLiteral("enabled"), true);
        selectedIndicatorConfigs.insert(key, params);
        QJsonObject indicator;
        indicator.insert(QStringLiteral("key"), key);
        indicator.insert(QStringLiteral("params"), params);
        indicators.append(indicator);
    }
    if (indicators.isEmpty()) {
        updateStatusMessage(QStringLiteral("Select at least one backtest indicator before running a backtest."));
        return;
    }
    if (selectedIndicatorConfigs.size() != indicators.size()) {
        updateStatusMessage(QStringLiteral("Generated Python backtest indicator defaults are incomplete; regenerate native parity contracts."));
        return;
    }

    const QDate startDate = backtestStartDateEdit_ ? backtestStartDateEdit_->date() : QDate();
    const QDate endDate = backtestEndDateEdit_ ? backtestEndDateEdit_->date() : QDate();
    if (!startDate.isValid() || !endDate.isValid() || endDate < startDate) {
        updateStatusMessage(QStringLiteral("Backtest date range is invalid; End Date must not precede Start Date."));
        return;
    }

    const QString loopInterval = comboValue(backtestLoopCombo_, QStringLiteral("1m"));
    QJsonObject stopLoss;
    stopLoss.insert(QStringLiteral("enabled"), backtestStopLossEnableCheck_ && backtestStopLossEnableCheck_->isChecked());
    stopLoss.insert(QStringLiteral("mode"), comboValue(backtestStopLossModeCombo_, QStringLiteral("usdt")));
    stopLoss.insert(QStringLiteral("scope"), comboValue(backtestStopLossScopeCombo_, QStringLiteral("per_trade")));
    stopLoss.insert(QStringLiteral("usdt"), doubleSpinValue(backtestStopLossUsdtSpin_, 0.0));
    stopLoss.insert(QStringLiteral("percent"), doubleSpinValue(backtestStopLossPercentSpin_, 0.0));

    const QString symbolSource = symbolSourceCombo_ ? symbolSourceCombo_->currentText().trimmed() : QStringLiteral("Futures");
    QJsonObject request;
    request.insert(QStringLiteral("symbols"), stringArray(symbols));
    request.insert(QStringLiteral("intervals"), stringArray(intervals));
    request.insert(QStringLiteral("indicators"), indicators);
    request.insert(QStringLiteral("logic"), comboValue(backtestSignalLogicCombo_, QStringLiteral("AND")));
    request.insert(QStringLiteral("symbol_source"), symbolSource.isEmpty() ? QStringLiteral("Futures") : symbolSource);
    request.insert(QStringLiteral("account_type"), symbolSource.toLower().startsWith(QStringLiteral("spot")) ? QStringLiteral("Spot") : QStringLiteral("Futures"));
    request.insert(QStringLiteral("mode"), comboValue(dashboardModeCombo_, QStringLiteral("Demo/Testnet")));
    request.insert(QStringLiteral("backtest"), true);
    request.insert(QStringLiteral("capital"), doubleSpinValue(backtestCapitalSpin_, 1000.0));
    request.insert(QStringLiteral("start"), startDate.toString(Qt::ISODate));
    request.insert(QStringLiteral("end"), endDate.toString(Qt::ISODate));
    request.insert(QStringLiteral("start_date"), request.value(QStringLiteral("start")));
    request.insert(QStringLiteral("end_date"), request.value(QStringLiteral("end")));
    request.insert(QStringLiteral("position_pct"), doubleSpinValue(backtestPositionPctSpin_, 2.0));
    request.insert(QStringLiteral("position_pct_units"), QStringLiteral("percent"));
    request.insert(QStringLiteral("loop_interval_override"), loopInterval);
    request.insert(QStringLiteral("side"), comboValue(backtestSideCombo_, QStringLiteral("BOTH")));
    request.insert(QStringLiteral("margin_mode"), comboValue(backtestMarginModeCombo_, QStringLiteral("Isolated")));
    request.insert(QStringLiteral("position_mode"), comboValue(backtestPositionModeCombo_, QStringLiteral("Hedge")));
    request.insert(QStringLiteral("assets_mode"), comboValue(backtestAssetsModeCombo_, QStringLiteral("Single-Asset")));
    request.insert(QStringLiteral("account_mode"), comboValue(backtestAccountModeCombo_, QStringLiteral("Classic Trading")));
    request.insert(QStringLiteral("connector_backend"), comboValue(backtestConnectorCombo_));
    request.insert(QStringLiteral("selected_exchange"), selectedExchange);
    request.insert(QStringLiteral("leverage"), spinValue(backtestLeverageSpin_, 1));
    request.insert(QStringLiteral("mdd_logic"), comboValue(backtestMddLogicCombo_, QStringLiteral("per_trade")));
    request.insert(QStringLiteral("scan_scope"), scanScope);
    request.insert(QStringLiteral("scan_top_n"), spinValue(backtestScanTopNSpin_, 200));
    request.insert(QStringLiteral("scan_mdd_limit"), doubleSpinValue(backtestScanMddSpin_, 10.0));
    request.insert(QStringLiteral("optimizer_mode"), optimizerMode);
    request.insert(
        QStringLiteral("optimizer_max_duration_seconds"),
        spinValue(backtestOptimizerMaxDurationSpin_, 240) * 60);
    request.insert(QStringLiteral("optimizer_metric"), comboValue(backtestOptimizerMetricCombo_, QStringLiteral("roi_percent")));
    request.insert(QStringLiteral("optimizer_combo_size"), spinValue(backtestOptimizerComboSizeSpin_, 2));
    request.insert(QStringLiteral("optimizer_min_trades"), spinValue(backtestOptimizerMinTradesSpin_, 1));
    request.insert(
        QStringLiteral("queue_if_busy"),
        backtestQueueIfBusyCheck_ && backtestQueueIfBusyCheck_->isChecked());
    request.insert(QStringLiteral("resume_checkpoint"), false);
    request.insert(QStringLiteral("stop_loss"), stopLoss);

    if (backend == QStringLiteral("local") && nativeBinanceBacktest) {
        NativeBacktestRuntime::Request runTemplate;
        runTemplate.logic = jsonText(request, QStringLiteral("logic"), QStringLiteral("AND"));
        runTemplate.side = jsonText(request, QStringLiteral("side"), QStringLiteral("BOTH"));
        runTemplate.capital = jsonNumber(request, QStringLiteral("capital"), 1000.0);
        runTemplate.positionPct = jsonNumber(request, QStringLiteral("position_pct"), 2.0);
        runTemplate.positionPctUnits = QStringLiteral("percent");
        runTemplate.leverage = jsonNumber(request, QStringLiteral("leverage"), 1.0);
        runTemplate.marginMode = jsonText(request, QStringLiteral("margin_mode"), QStringLiteral("Isolated"));
        runTemplate.positionMode = jsonText(request, QStringLiteral("position_mode"), QStringLiteral("Hedge"));
        runTemplate.assetsMode = jsonText(request, QStringLiteral("assets_mode"), QStringLiteral("Single-Asset"));
        runTemplate.accountMode = jsonText(request, QStringLiteral("account_mode"), QStringLiteral("Classic Trading"));
        runTemplate.mddLogic = jsonText(request, QStringLiteral("mdd_logic"), QStringLiteral("per_trade"));
        runTemplate.stopLossEnabled = stopLoss.value(QStringLiteral("enabled")).toBool(false);
        runTemplate.stopLossMode = jsonText(stopLoss, QStringLiteral("mode"), QStringLiteral("usdt"));
        runTemplate.stopLossScope = jsonText(stopLoss, QStringLiteral("scope"), QStringLiteral("per_trade"));
        runTemplate.stopLossUsdt = jsonNumber(stopLoss, QStringLiteral("usdt"), 0.0);
        runTemplate.stopLossPercent = jsonNumber(stopLoss, QStringLiteral("percent"), 0.0);

        NativeBacktestBatchRuntime::BatchRequest batchRequest;
        batchRequest.symbols = symbols;
        batchRequest.intervals = intervals;
        batchRequest.indicatorConfigs = selectedIndicatorConfigs;
        batchRequest.runTemplate = runTemplate;
        batchRequest.optimizerMode = optimizerMode;
        batchRequest.optimizerMetric = jsonText(request, QStringLiteral("optimizer_metric"), QStringLiteral("roi_percent"));
        batchRequest.optimizerScope = scanScope;
        batchRequest.optimizerComboSize = static_cast<int>(jsonNumber(request, QStringLiteral("optimizer_combo_size"), 2.0));
        batchRequest.optimizerMinTrades = static_cast<int>(jsonNumber(request, QStringLiteral("optimizer_min_trades"), 1.0));
        batchRequest.optimizerMddLimit = jsonNumber(request, QStringLiteral("scan_mdd_limit"), 0.0);
        batchRequest.startDisplay = startDate.toString(Qt::ISODate);
        batchRequest.endDisplay = endDate.toString(Qt::ISODate);
        batchRequest.loopIntervalOverride = loopInterval;
        batchRequest.connectorBackend = jsonText(request, QStringLiteral("connector_backend"));

        const QVector<QStringList> groups = NativeBacktestBatchRuntime::buildIndicatorGroups(
            batchRequest.indicatorConfigs,
            batchRequest.optimizerMode,
            batchRequest.optimizerComboSize,
            batchRequest.runTemplate.logic);
        const qint64 estimatedRuns = NativeBacktestBatchRuntime::estimateRunCount(
            batchRequest.symbols.size(),
            batchRequest.intervals.size(),
            groups.size());
        if (groups.isEmpty()) {
            updateStatusMessage(QStringLiteral("The selected optimizer mode has no valid signal-indicator groups."));
            return;
        }
        if (estimatedRuns > NativeBacktestBatchRuntime::kMaxOptimizerRuns) {
            updateStatusMessage(
                QStringLiteral("Estimated native C++ runs %1 exceed the 100-billion hard cap.")
                    .arg(estimatedRuns));
            return;
        }

        const bool futures = !symbolSource.toLower().startsWith(QStringLiteral("spot"));
        const bool testnet = TradingBotWindowSupport::isTestnetModeLabel(
            jsonText(request, QStringLiteral("mode"), QStringLiteral("Demo/Testnet")));
        QString baseUrlOverride;
        if (backtestConnectorCombo_) {
            const auto connector = TradingBotWindowSupport::resolveConnectorConfig(
                backtestConnectorCombo_->currentText(),
                futures);
            if (connector.ok()) baseUrlOverride = connector.baseUrl;
        }
        const qint64 startTimeMs = QDateTime(startDate, QTime(0, 0), Qt::UTC).toMSecsSinceEpoch();
        const qint64 endTimeMs = QDateTime(endDate.addDays(1), QTime(0, 0), Qt::UTC).toMSecsSinceEpoch() - 1;
        const auto stopFlag = std::make_shared<std::atomic_bool>(false);
        backtestStopFlag_ = stopFlag;

        if (!backtestFutureWatcher_) {
            backtestFutureWatcher_ = new QFutureWatcher<QJsonObject>(this);
            connect(backtestFutureWatcher_, &QFutureWatcher<QJsonObject>::finished, this, [this]() {
                const QJsonObject snapshot = backtestFutureWatcher_->result();
                const int addedRows = appendBacktestRows(resultsTable_, snapshot, QString());
                backtestStopFlag_.reset();
                setBacktestRunningUi(false);
                const QString state = jsonText(snapshot, QStringLiteral("state"), QStringLiteral("failed")).toLower();
                const QString status = backtestSnapshotStatusText(snapshot, QStringLiteral("Native C++ backtest finished."));
                if (state == QStringLiteral("cancelled")) {
                    updateStatusMessage(
                        QStringLiteral("Native C++ backtest cancelled: %1 row(s) imported. %2")
                            .arg(addedRows)
                            .arg(status));
                } else if (state == QStringLiteral("failed")) {
                    updateStatusMessage(QStringLiteral("Native C++ backtest failed: %1").arg(status));
                } else {
                    updateStatusMessage(
                        QStringLiteral("Native C++ backtest complete: %1 row(s) imported. %2")
                            .arg(addedRows)
                            .arg(status));
                }
            });
        }

        setBacktestRunningUi(true);
        updateStatusMessage(
            QStringLiteral("Native C++ backtest started: %1 run(s), %2 indicator group(s).")
                .arg(estimatedRuns)
                .arg(groups.size()));
        backtestFutureWatcher_->setFuture(QtConcurrent::run(
            [batchRequest, futures, testnet, startTimeMs, endTimeMs, baseUrlOverride, stopFlag]() {
                const NativeBacktestBatchRuntime::StopCallback shouldStop = [stopFlag]() {
                    return stopFlag->load(std::memory_order_relaxed);
                };
                const NativeBacktestBatchRuntime::CandleLoader loader =
                    [futures, testnet, startTimeMs, endTimeMs, baseUrlOverride](
                        const QString &symbol,
                        const QString &interval,
                        const NativeBacktestBatchRuntime::StopCallback &stopRequested) {
                        const BinanceRestClient::KlinesResult fetched = BinanceRestClient::fetchKlinesRange(
                            symbol,
                            interval,
                            futures,
                            testnet,
                            startTimeMs,
                            endTimeMs,
                            2'000'000,
                            15'000,
                            baseUrlOverride,
                            stopRequested);
                        NativeBacktestBatchRuntime::CandleLoadResult loaded;
                        loaded.ok = fetched.ok;
                        loaded.error = fetched.error;
                        loaded.candles.reserve(fetched.candles.size());
                        for (const BinanceRestClient::KlineCandle &candle : fetched.candles) {
                            loaded.candles.append({
                                candle.open,
                                candle.high,
                                candle.low,
                                candle.close,
                                candle.volume,
                            });
                        }
                        return loaded;
                    };
                return NativeBacktestBatchRuntime::runBatch(batchRequest, loader, shouldStop);
            }));
        return;
    }

    if (backend == QStringLiteral("local") && !nativeBinanceBacktest) {
        updateStatusMessage(
            QStringLiteral("%1 backtest is delegated to the Python Service API; the local C++ backtest loader is Binance-only.")
                .arg(selectedExchange));
    }
    submitServiceBacktest(
        request,
        loopInterval,
        QStringLiteral("Submitting C++ backtest to Python Service API..."));
}

void TradingBotWindow::resumeBacktestCheckpoint() {
    if ((backtestFutureWatcher_ && backtestFutureWatcher_->isRunning()) || backtestServiceRunActive_) {
        updateStatusMessage(QStringLiteral("A backtest is already running."));
        return;
    }
    if (!resumeBacktestButton_ || !resumeBacktestButton_->property("checkpointAvailable").toBool()) {
        updateStatusMessage(QStringLiteral("No saved optimizer checkpoint is available to resume."));
        return;
    }

    QJsonObject request;
    request.insert(QStringLiteral("queue_if_busy"), false);
    request.insert(QStringLiteral("resume_checkpoint"), true);
    resumeBacktestButton_->setProperty("checkpointAvailable", false);
    submitServiceBacktest(
        request,
        comboValue(backtestLoopCombo_, QStringLiteral("1m")),
        QStringLiteral("Resuming saved optimizer through the Python Service API..."));
}

void TradingBotWindow::submitServiceBacktest(
    const QJsonObject &request,
    const QString &loopInterval,
    const QString &startMessage) {
    const bool resumingCheckpoint = request.value(QStringLiteral("resume_checkpoint")).toBool(false);
    const auto restoreResumeAvailability = [this, resumingCheckpoint]() {
        if (resumeBacktestButton_) {
            resumeBacktestButton_->setProperty("checkpointAvailable", resumingCheckpoint);
        }
    };
    setBacktestRunningUi(true);
    backtestServiceRunActive_ = true;
    updateStatusMessage(startMessage);
    QCoreApplication::processEvents();

    QJsonObject wrapper;
    wrapper.insert(QStringLiteral("request"), request);
    wrapper.insert(QStringLiteral("source"), QStringLiteral("cpp-desktop"));

    const auto submitResult = TradingBotWindowSupport::serviceApiRequestJson(
        QStringLiteral("POST"),
        QStringLiteral("backtest_run"),
        wrapper,
        45000);
    if (!submitResult.ok) {
        backtestServiceRunActive_ = false;
        restoreResumeAvailability();
        setBacktestRunningUi(false);
        updateStatusMessage(QStringLiteral("Python Service API backtest submit failed: %1").arg(submitResult.error));
        return;
    }
    const QJsonObject submitPayload = submitResult.document.object();
    if (submitPayload.contains(QStringLiteral("accepted")) && !submitPayload.value(QStringLiteral("accepted")).toBool(true)) {
        backtestServiceRunActive_ = false;
        restoreResumeAvailability();
        setBacktestRunningUi(false);
        updateStatusMessage(
            QStringLiteral("Python Service API rejected backtest: %1")
                .arg(jsonText(submitPayload, QStringLiteral("status_message"), QStringLiteral("request rejected"))));
        return;
    }

    QJsonObject snapshot;
    for (int attempt = 0; attempt < 60; ++attempt) {
        const auto snapshotResult = TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("GET"),
            QStringLiteral("backtest"),
            {},
            30000);
        if (!snapshotResult.ok) {
            backtestServiceRunActive_ = false;
            restoreResumeAvailability();
            setBacktestRunningUi(false);
            updateStatusMessage(QStringLiteral("Python Service API backtest snapshot failed: %1").arg(snapshotResult.error));
            return;
        }
        snapshot = snapshotResult.document.object();
        if (!backtestSnapshotActive(snapshot)) {
            break;
        }
        updateStatusMessage(
            QStringLiteral("Python Service API backtest running: %1")
                .arg(backtestSnapshotStatusText(snapshot, QStringLiteral("waiting for results"))));
        QEventLoop delayLoop;
        QTimer::singleShot(500, &delayLoop, &QEventLoop::quit);
        delayLoop.exec();
        QCoreApplication::processEvents();
    }

    const bool stillActive = backtestSnapshotActive(snapshot);
    backtestServiceRunActive_ = stillActive;
    const int addedRows = appendBacktestRows(resultsTable_, snapshot, loopInterval);
    const QString state = jsonText(snapshot, QStringLiteral("state")).toLower();
    const bool checkpointAvailable = state == QStringLiteral("budget_exhausted");
    if (resumeBacktestButton_) {
        resumeBacktestButton_->setProperty("checkpointAvailable", checkpointAvailable);
        resumeBacktestButton_->setToolTip(checkpointAvailable
            ? QStringLiteral("Resume the saved optimizer checkpoint using current Python Service API credentials.")
            : QStringLiteral("Available after the Python Service API saves an optimizer time-budget checkpoint."));
    }
    setBacktestRunningUi(stillActive);
    if (stillActive) {
        updateStatusMessage(
            QStringLiteral("Python Service API backtest is still running: %1")
                .arg(jsonText(snapshot, QStringLiteral("status_message"), QStringLiteral("poll again later"))));
        return;
    }

    const QString status = backtestSnapshotStatusText(snapshot, QStringLiteral("Backtest complete."));
    if (checkpointAvailable) {
        updateStatusMessage(
            QStringLiteral("Python Service API optimizer reached its time budget: %1 row(s) imported. %2 Use Resume Optimizer to continue.")
                .arg(addedRows)
                .arg(status));
    } else if (backtestSnapshotCancelled(snapshot)) {
        updateStatusMessage(QStringLiteral("Python Service API backtest cancelled: %1 row(s) imported. %2").arg(addedRows).arg(status));
    } else {
        updateStatusMessage(QStringLiteral("Python Service API backtest complete: %1 row(s) imported. %2").arg(addedRows).arg(status));
    }
}

void TradingBotWindow::handleStopBacktest() {
    if (backtestFutureWatcher_ && backtestFutureWatcher_->isRunning()) {
        if (backtestStopFlag_) backtestStopFlag_->store(true, std::memory_order_relaxed);
        if (stopButton_) stopButton_->setEnabled(false);
        updateStatusMessage(QStringLiteral("Native C++ backtest cancellation requested; finishing the active candle fetch/run."));
        return;
    }
    if (!backtestServiceRunActive_) {
        setBacktestRunningUi(false);
        updateStatusMessage(QStringLiteral("No backtest is currently running."));
        return;
    }

    QJsonObject stopPayload;
    stopPayload.insert(QStringLiteral("source"), QStringLiteral("cpp-desktop"));
    const auto stopResult = TradingBotWindowSupport::serviceApiRequestJson(
        QStringLiteral("POST"),
        QStringLiteral("backtest_stop"),
        stopPayload,
        10000);
    backtestServiceRunActive_ = false;
    setBacktestRunningUi(false);
    const QString statusStyle = QStringLiteral("color: #ef4444; font-weight: 700;");
    if (!dashboardRuntimeActive_ && dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText("--");
    }
    if (!dashboardRuntimeActive_ && dashboardBotStatusLabel_) {
        dashboardBotStatusLabel_->setText("OFF");
        dashboardBotStatusLabel_->setStyleSheet(statusStyle);
    }
    if (stopResult.ok) {
        updateStatusMessage("Backtest stopped through Python Service API.");
    } else {
        updateStatusMessage(QStringLiteral("Backtest stopped locally; Python Service API stop failed: %1").arg(stopResult.error));
    }
}

QWidget *TradingBotWindow::createMarketsGroup() {
    auto *group = new QGroupBox("Markets & Intervals", this);
    auto *layout = new QGridLayout(group);
    layout->setHorizontalSpacing(10);
    layout->setVerticalSpacing(8);

    auto *symbolLabel = new QLabel("Symbol Source:", group);
    symbolSourceCombo_ = new QComboBox(group);
    symbolSourceCombo_->addItems(TradingBotWindowSupport::pythonSourceChartMarketOptions());
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
                TradingBotWindowSupport::rebuildConnectorComboForAccount(backtestConnectorCombo_, futures, true);
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

    auto *executionBackendCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        executionBackendCombo,
        TradingBotWindowSupport::pythonSourceBacktestExecutionBackendOptionKeys(),
        TradingBotWindowSupport::pythonSourceBacktestExecutionBackendOptionLabels(),
        {},
        QStringLiteral("local"));
    executionBackendCombo->setToolTip(
        QStringLiteral("local runs the native C++ simulator; service uses the Python Service API compatibility backend."));
    backtestExecutionBackendCombo_ = executionBackendCombo;
    form->addRow("Execution Backend:", executionBackendCombo);

    auto *signalLogicCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        signalLogicCombo,
        TradingBotWindowSupport::pythonSourceSignalLogicOptionKeys(),
        TradingBotWindowSupport::pythonSourceSignalLogicOptionLabels(),
        {},
        QStringLiteral("AND"));
    backtestSignalLogicCombo_ = signalLogicCombo;
    form->addRow("Signal Logic:", signalLogicCombo);

    auto *mddLogicCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        mddLogicCombo,
        TradingBotWindowSupport::pythonSourceMddLogicOptionKeys(),
        TradingBotWindowSupport::pythonSourceMddLogicOptionLabels(),
        {},
        QStringLiteral("per_trade"));
    backtestMddLogicCombo_ = mddLogicCombo;
    form->addRow("MDD Logic:", mddLogicCombo);

    auto *startDate = new QDateEdit(QDate::currentDate().addMonths(-1), group);
    startDate->setCalendarPopup(true);
    startDate->setDisplayFormat("yyyy-MM-dd");
    form->addRow("Start Date:", startDate);
    backtestStartDateEdit_ = startDate;
    auto *endDate = new QDateEdit(QDate::currentDate(), group);
    endDate->setCalendarPopup(true);
    endDate->setDisplayFormat("yyyy-MM-dd");
    form->addRow("End Date:", endDate);
    backtestEndDateEdit_ = endDate;

    auto *capitalSpin = new QDoubleSpinBox(group);
    capitalSpin->setSuffix(" USDT");
    capitalSpin->setRange(0.0, 1'000'000.0);
    capitalSpin->setDecimals(2);
    capitalSpin->setValue(1000.0);
    form->addRow("Capital (USDT):", capitalSpin);
    backtestCapitalSpin_ = capitalSpin;

    auto *positionPct = new QDoubleSpinBox(group);
    positionPct->setSuffix(" %");
    positionPct->setRange(0.1, 100.0);
    positionPct->setSingleStep(0.1);
    positionPct->setDecimals(2);
    positionPct->setValue(2.0);
    form->addRow("Position % of Balance:", positionPct);
    backtestPositionPctSpin_ = positionPct;

    auto *loopCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        loopCombo,
        TradingBotWindowSupport::pythonSourceDashboardLoopChoiceKeys(),
        TradingBotWindowSupport::pythonSourceDashboardLoopChoiceLabels(),
        {},
        QStringLiteral("1m"),
        QStringLiteral("1 minute"));
    backtestLoopCombo_ = loopCombo;
    form->addRow("Loop Interval Override:", loopCombo);

    auto *stopLossRow = new QWidget(group);
    auto *stopLossLayout = new QHBoxLayout(stopLossRow);
    stopLossLayout->setContentsMargins(0, 0, 0, 0);
    stopLossLayout->setSpacing(6);
    auto *stopEnable = new QCheckBox("Enable", stopLossRow);
    auto *stopMode = new QComboBox(stopLossRow);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        stopMode,
        TradingBotWindowSupport::pythonSourceStopLossModeKeys(),
        TradingBotWindowSupport::pythonSourceStopLossModeLabels(),
        {},
        QStringLiteral("usdt"));
    auto *stopScope = new QComboBox(stopLossRow);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        stopScope,
        TradingBotWindowSupport::pythonSourceStopLossScopeKeys(),
        TradingBotWindowSupport::pythonSourceStopLossScopeLabels(),
        {},
        QStringLiteral("per_trade"));
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
    backtestStopLossUsdtSpin_ = stopUsdt;
    backtestStopLossPercentSpin_ = stopPct;

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

    auto *sideCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        sideCombo,
        TradingBotWindowSupport::pythonSourceSideOptionKeys(),
        TradingBotWindowSupport::pythonSourceSideOptionLabels(),
        {},
        {},
        QStringLiteral("Both (Long/Short)"));
    form->addRow("Side:", sideCombo);
    backtestSideCombo_ = sideCombo;

    auto *marginModeCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        marginModeCombo,
        TradingBotWindowSupport::pythonSourceMarginModeOptionKeys(),
        TradingBotWindowSupport::pythonSourceMarginModeOptionLabels(),
        {},
        QStringLiteral("Isolated"));
    form->addRow("Margin Mode (Futures):", marginModeCombo);
    backtestMarginModeCombo_ = marginModeCombo;
    auto *positionModeCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        positionModeCombo,
        TradingBotWindowSupport::pythonSourcePositionModeOptionKeys(),
        TradingBotWindowSupport::pythonSourcePositionModeOptionLabels(),
        {},
        QStringLiteral("Hedge"));
    form->addRow("Position Mode:", positionModeCombo);
    backtestPositionModeCombo_ = positionModeCombo;
    auto *assetsCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        assetsCombo,
        TradingBotWindowSupport::pythonSourceAssetsModeOptionKeys(),
        TradingBotWindowSupport::pythonSourceAssetsModeOptionLabels());
    form->addRow("Assets Mode:", assetsCombo);
    backtestAssetsModeCombo_ = assetsCombo;
    backtestAccountModeCombo_ = addCombo("Account Mode:", TradingBotWindowSupport::pythonSourceAccountModeOptions());

    auto *connectorCombo = new QComboBox(group);
    const bool sourceFutures = symbolSourceCombo_
        ? symbolSourceCombo_->currentText().trimmed().toLower().startsWith(QStringLiteral("fut"))
        : true;
    TradingBotWindowSupport::rebuildConnectorComboForAccount(connectorCombo, sourceFutures, true);
    connectorCombo->setMinimumWidth(220);
    form->addRow("Connector:", connectorCombo);
    backtestConnectorCombo_ = connectorCombo;
    connect(connectorCombo, &QComboBox::currentTextChanged, this, [this](const QString &) {
        refreshBacktestSymbols();
    });

    auto *leverageSpin = new QSpinBox(group);
    leverageSpin->setRange(1, 150);
    leverageSpin->setValue(1);
    backtestLeverageSpin_ = leverageSpin;
    form->addRow("Leverage (Futures):", leverageSpin);

    auto *templateEnable = new QCheckBox("Enable", group);
    templateEnable->setChecked(false);
    auto *templateCombo = new QComboBox(group);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        templateCombo,
        TradingBotWindowSupport::pythonSourceBacktestTemplateKeys(),
        TradingBotWindowSupport::pythonSourceBacktestTemplateLabels());
    templateCombo->setEnabled(false);

    connect(templateEnable, &QCheckBox::toggled, templateCombo, &QWidget::setEnabled);
    form->addRow("Template:", templateCombo);
    form->addRow("", templateEnable);

    auto *optimizerRow = new QWidget(group);
    auto *optimizerGrid = new QGridLayout(optimizerRow);
    optimizerGrid->setContentsMargins(0, 0, 0, 0);
    optimizerGrid->setHorizontalSpacing(6);
    optimizerGrid->setVerticalSpacing(6);
    auto addOptimizerWidget = [optimizerGrid, optimizerRow](int row, int col, const QString &label, QWidget *widget) {
        optimizerGrid->addWidget(new QLabel(label, optimizerRow), row, col);
        optimizerGrid->addWidget(widget, row, col + 1);
    };

    auto *scanScopeCombo = new QComboBox(optimizerRow);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        scanScopeCombo,
        TradingBotWindowSupport::pythonSourceScanScopeOptionKeys(),
        TradingBotWindowSupport::pythonSourceScanScopeOptionLabels(),
        {},
        QStringLiteral("selected"));
    backtestScanScopeCombo_ = scanScopeCombo;
    addOptimizerWidget(0, 0, "Scope:", scanScopeCombo);

    auto *scanTopNSpin = new QSpinBox(optimizerRow);
    scanTopNSpin->setRange(1, 1'000'000);
    scanTopNSpin->setValue(200);
    backtestScanTopNSpin_ = scanTopNSpin;
    addOptimizerWidget(0, 2, "Top N:", scanTopNSpin);

    auto *scanMddSpin = new QDoubleSpinBox(optimizerRow);
    scanMddSpin->setRange(0.0, 100.0);
    scanMddSpin->setDecimals(2);
    scanMddSpin->setSuffix(" %");
    scanMddSpin->setValue(10.0);
    backtestScanMddSpin_ = scanMddSpin;
    addOptimizerWidget(0, 4, "Max MDD:", scanMddSpin);

    auto *optimizerModeCombo = new QComboBox(optimizerRow);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        optimizerModeCombo,
        TradingBotWindowSupport::pythonSourceOptimizerModeOptionKeys(),
        TradingBotWindowSupport::pythonSourceOptimizerModeOptionLabels(),
        {},
        QStringLiteral("current"));
    backtestOptimizerModeCombo_ = optimizerModeCombo;
    addOptimizerWidget(1, 0, "Mode:", optimizerModeCombo);

    auto *optimizerMetricCombo = new QComboBox(optimizerRow);
    TradingBotWindowSupport::populateComboFromPythonSourceOptions(
        optimizerMetricCombo,
        TradingBotWindowSupport::pythonSourceOptimizerMetricOptionKeys(),
        TradingBotWindowSupport::pythonSourceOptimizerMetricOptionLabels(),
        {},
        QStringLiteral("roi_percent"));
    backtestOptimizerMetricCombo_ = optimizerMetricCombo;
    addOptimizerWidget(1, 2, "Optimize for:", optimizerMetricCombo);

    auto *optimizerComboSizeSpin = new QSpinBox(optimizerRow);
    optimizerComboSizeSpin->setRange(1, 5);
    optimizerComboSizeSpin->setValue(2);
    backtestOptimizerComboSizeSpin_ = optimizerComboSizeSpin;
    addOptimizerWidget(2, 0, "Max Combo:", optimizerComboSizeSpin);

    auto *optimizerMinTradesSpin = new QSpinBox(optimizerRow);
    optimizerMinTradesSpin->setRange(0, 1'000'000);
    optimizerMinTradesSpin->setValue(1);
    backtestOptimizerMinTradesSpin_ = optimizerMinTradesSpin;
    addOptimizerWidget(2, 2, "Min Trades:", optimizerMinTradesSpin);

    auto *optimizerMaxDurationSpin = new QSpinBox(optimizerRow);
    optimizerMaxDurationSpin->setRange(1, 10'080);
    optimizerMaxDurationSpin->setSuffix(" min");
    optimizerMaxDurationSpin->setValue(240);
    optimizerMaxDurationSpin->setToolTip(
        "Stop an optimizer batch after this time and make it available for checkpoint resume.");
    backtestOptimizerMaxDurationSpin_ = optimizerMaxDurationSpin;
    addOptimizerWidget(2, 4, "Max Time:", optimizerMaxDurationSpin);

    auto *queueIfBusyCheck = new QCheckBox("Queue if another backtest is running", optimizerRow);
    queueIfBusyCheck->setToolTip(
        "Ask the Python Service API to queue this run instead of rejecting it when another backtest is active.");
    backtestQueueIfBusyCheck_ = queueIfBusyCheck;
    optimizerGrid->addWidget(queueIfBusyCheck, 3, 0, 1, 4);

    auto *scanBtn = new QPushButton("Run Optimizer", optimizerRow);
    optimizerGrid->addWidget(scanBtn, 3, 4, 1, 2);
    auto updateOptimizerModeWidgets = [optimizerModeCombo, optimizerComboSizeSpin]() {
        const QString mode = optimizerModeCombo->currentData().toString().trimmed();
        optimizerComboSizeSpin->setEnabled(mode != QStringLiteral("current") && mode != QStringLiteral("off"));
    };
    connect(optimizerModeCombo, &QComboBox::currentIndexChanged, this, [updateOptimizerModeWidgets](int) {
        updateOptimizerModeWidgets();
    });
    updateOptimizerModeWidgets();
    connect(scanBtn, &QPushButton::clicked, this, [this]() {
        startBacktest(true);
    });
    form->addRow("ROI Optimizer / Scanner:", optimizerRow);

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

    const QStringList indicatorKeys = TradingBotWindowSupport::pythonSourceIndicatorKeys();
    const QStringList indicators = TradingBotWindowSupport::pythonSourceIndicatorDisplayNames();
    const QStringList defaultEnabledIndicatorKeys = TradingBotWindowSupport::pythonSourceDefaultEnabledIndicatorKeys();
    const QSet<QString> defaultEnabledIndicators(defaultEnabledIndicatorKeys.begin(), defaultEnabledIndicatorKeys.end());

    int row = 0;
    for (int index = 0; index < indicators.size(); ++index) {
        const QString ind = indicators.at(index);
        const QString key = index < indicatorKeys.size() ? indicatorKeys.at(index) : ind;
        auto *cb = new QCheckBox(ind, group);
        auto *btn = new QPushButton("Buy-Sell Values", group);
        btn->setMinimumWidth(140);
        btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
        btn->setEnabled(false);
        if (defaultEnabledIndicators.contains(key)) {
            cb->setChecked(true);
            btn->setEnabled(true);
        }
        backtestIndicatorChecks_.insert(key, cb);
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
        symbolList_->addItems(TradingBotWindowSupport::pythonSourceDefaultBacktestSymbols());
        for (int i = 0; i < symbolList_->count(); ++i) {
            if (i < 2) {
                symbolList_->item(i)->setSelected(true);
            }
        }
    }
    if (intervalList_) {
        intervalList_->addItems(TradingBotWindowSupport::pythonSourceBacktestIntervals());
        for (int i = 0; i < intervalList_->count() && i < 2; ++i) {
            intervalList_->item(i)->setSelected(true);
        }
    }
}

void TradingBotWindow::wireSignals() {
    connect(runButton_, &QPushButton::clicked, this, &TradingBotWindow::handleRunBacktest);
    connect(resumeBacktestButton_, &QPushButton::clicked, this, &TradingBotWindow::resumeBacktestCheckpoint);
    connect(stopButton_, &QPushButton::clicked, this, &TradingBotWindow::handleStopBacktest);
    auto importBacktestRowsToDashboard = [this](const QList<int> &targetRows) {
        if (!resultsTable_ || !dashboardOverridesTable_) {
            updateStatusMessage(QStringLiteral("Backtest import failed: dashboard or results table is unavailable."));
            return;
        }
        if (targetRows.isEmpty()) {
            updateStatusMessage(QStringLiteral("Select one or more backtest result rows to add."));
            return;
        }

        QMap<QString, int> existingRows;
        for (int row = 0; row < dashboardOverridesTable_->rowCount(); ++row) {
            const QJsonObject payload = dashboardOverridePayloadFromTableRow(dashboardOverridesTable_, row);
            const QString key = dashboardOverrideKey(payload);
            if (!key.trimmed().isEmpty()) {
                existingRows.insert(key, row);
            }
        }

        int added = 0;
        int updated = 0;
        int skipped = 0;
        for (int row : targetRows) {
            const QJsonObject result = backtestResultPayloadFromTableRow(resultsTable_, row);
            if (result.contains(QStringLiteral("optimizer_eligible"))
                && !jsonBool(result, QStringLiteral("optimizer_eligible"), true)) {
                ++skipped;
                continue;
            }
            const QJsonObject payload = dashboardOverridePayloadFromBacktestResult(result);
            const QString key = dashboardOverrideKey(payload);
            if (payload.isEmpty() || key.trimmed().isEmpty()) {
                ++skipped;
                continue;
            }
            if (existingRows.contains(key)) {
                setDashboardOverridePayload(dashboardOverridesTable_, existingRows.value(key), payload);
                ++updated;
                continue;
            }

            const int dashboardRow = dashboardOverridesTable_->rowCount();
            setDashboardOverridePayload(dashboardOverridesTable_, dashboardRow, payload);
            existingRows.insert(key, dashboardRow);
            ++added;
        }

        const QString status = QStringLiteral("Backtest import: added %1 row(s), updated %2, skipped %3.")
            .arg(added)
            .arg(updated)
            .arg(skipped);
        updateStatusMessage(status);
        appendDashboardAllLog(status);
        appendDashboardWaitingLog(status);
    };

    connect(addSelectedBtn_, &QPushButton::clicked, this, [this, importBacktestRowsToDashboard]() {
        QSet<int> selectedRows;
        if (resultsTable_) {
            const QModelIndexList rows = resultsTable_->selectionModel()
                ? resultsTable_->selectionModel()->selectedRows()
                : QModelIndexList{};
            for (const QModelIndex &index : rows) {
                selectedRows.insert(index.row());
            }
        }
        QList<int> rows = selectedRows.values();
        std::sort(rows.begin(), rows.end());
        importBacktestRowsToDashboard(rows);
    });
    connect(addAllBtn_, &QPushButton::clicked, this, [this, importBacktestRowsToDashboard]() {
        QList<int> rows;
        if (resultsTable_) {
            for (int row = 0; row < resultsTable_->rowCount(); ++row) {
                rows.append(row);
            }
        }
        importBacktestRowsToDashboard(rows);
    });
}
