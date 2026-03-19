#include "TradingBotWindow.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QPushButton>
#include <QSignalBlocker>
#include <QSpinBox>

namespace {
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
} // namespace

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
        const QString indicatorKey = it.key();
        if (indicatorKey.trimmed().isEmpty()) {
            continue;
        }
        dashboardIndicatorParams_.insert(indicatorKey, it.value());
        if (auto *check = dashboardIndicatorChecks_.value(indicatorKey, nullptr)) {
            check->setChecked(true);
        }
        if (auto *button = dashboardIndicatorButtons_.value(indicatorKey, nullptr)) {
            button->setEnabled(true);
        }
    }

    updateStatusMessage(QStringLiteral("Dashboard template applied: %1").arg(templateKey.trimmed()));
}
